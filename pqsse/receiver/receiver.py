"""A receiver (search user).

Implements the receiver side of Setup, Join, TokenGen, Verify and Decrypt, plus the
handling of rekey boxes after a revocation. A receiver trusts only the owner's
verification key and its own keys; everything that comes from the cloud is verified.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .. import pqbackend
from ..core import index, seal, signing, wire
from ..core.chain import CHAIN_START, chain_fold
from ..core.index import doc_aad, doc_handle, token_aad, token_key
from ..core.errors import AccessDenied, PQSSEError, Rejected, VerifyError, WireError
from ..core.pairing import PublicIdentity
from ..core.prims import H, aead_decrypt, aead_encrypt, group_subkeys
from ..core.state import StateHeader, check_state_signature, open_state
from ..gpu.batchprf import BatchPRF, CpuPRF
from ..pqbackend import DEFAULT_PARAMS, Params
from ..transport import CloudAPI

CHECKS = (
    "state signature",
    "segments complete",
    "older segments final",
    "freshness",
    "no rollback",
    "response signature",
    "completeness",
    "hash chain",
)


@dataclass
class Report:
    """Outcome of algorithm Verify, one line per check, for the verification panel."""

    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    fresh_until: float = 0.0

    def ok(self, name: str, detail: str = "") -> None:
        self.checks.append((name, True, detail))

    def fail(self, name: str, detail: str) -> VerifyError:
        self.checks.append((name, False, detail))
        err = VerifyError(name, detail)
        err.report = self  # type: ignore[attr-defined]
        return err

    @property
    def all_ok(self) -> bool:
        return bool(self.checks) and all(ok for _, ok, _ in self.checks)


@dataclass
class SearchResult:
    group: str
    keyword: str
    hits: list[tuple[int, int]]          # (document id, epoch the document was added in)
    report: Report
    entries: int = 0                     # index entries returned and verified

    @property
    def ids(self) -> set[int]:
        return {doc_id for doc_id, _ in self.hits}


@dataclass
class Document:
    doc_id: int
    epoch: int
    title: str
    text: str


class Receiver:
    """Receiver role."""

    def __init__(self, vault: Any, cloud: CloudAPI | None = None, prf: BatchPRF | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        me = vault.get("receiver")
        if me is None:
            raise PQSSEError("receiver is not set up in this vault")
        self.vault = vault
        self.cloud = cloud
        self.prf = prf or CpuPRF()
        self.clock = clock
        self._me = me
        self.params = Params(me["kem"], me["sig"])
        self.name: str = me["name"]
        self.ek, self._dk = me["ek"], me["dk"]
        self.vk, self._sk = me["vk"], me["sk"]
        self.uid: str = H(self.ek, self.vk)[:16].hex()
        self._sig_cache: dict[bytes, StateHeader] = {}
        self._open_cache: dict[bytes, dict] = {}

    # ------------------------------------------------------------------ Setup
    @classmethod
    def create(cls, vault: Any, params: Params = DEFAULT_PARAMS, name: str = "receiver", **kwargs: Any) -> "Receiver":
        """Algorithm 1 Setup (receiver part): ML-KEM key pair and ML-DSA key pair."""
        if vault.get("receiver") is not None:
            raise PQSSEError("receiver already exists in this vault")
        ek, dk = pqbackend.kem_keygen(params.kem)
        vk, sk = pqbackend.sig_keygen(params.sig)
        vault.put("receiver", {"name": name, "kem": params.kem, "sig": params.sig, "ek": ek, "dk": dk,
                               "vk": vk, "sk": sk, "owner_pub": None, "cloud_pub": None, "cap": None,
                               "seen": {}, "mail_done": []})
        return cls(vault, **kwargs)

    @staticmethod
    def exists(vault: Any) -> bool:
        return vault.get("receiver") is not None

    def _save(self) -> None:
        self.vault.put("receiver", self._me)

    def public_identity(self) -> PublicIdentity:
        return PublicIdentity("receiver", self.name, self.params, self.vk, self.ek)

    def pair(self, owner: PublicIdentity, cloud: PublicIdentity) -> None:
        """Pair devices: install the authentic public keys of owner and cloud."""
        if owner.role != "owner" or cloud.role != "cloud":
            raise PQSSEError("wrong key file roles")
        if owner.params != self.params or cloud.params != self.params:
            raise PQSSEError("parameter set mismatch")
        self._me["owner_pub"] = owner.to_wire()
        self._me["cloud_pub"] = cloud.to_wire()
        self._save()

    @property
    def paired(self) -> bool:
        return self._me["owner_pub"] is not None and self._me["cloud_pub"] is not None

    def _owner_vk(self) -> bytes:
        if self._me["owner_pub"] is None:
            raise PQSSEError("receiver is not paired with an owner")
        return self._me["owner_pub"]["vk"]

    def _cloud_vk(self) -> bytes:
        if self._me["cloud_pub"] is None:
            raise PQSSEError("receiver is not paired with a cloud")
        return self._me["cloud_pub"]["vk"]

    def _cloud(self) -> CloudAPI:
        if self.cloud is None:
            raise PQSSEError("receiver is not connected to a cloud")
        return self.cloud

    # ------------------------------------------------------------------ Join
    def join_request(self) -> dict:
        """Algorithm 2 Join (receiver part): keys plus an ML-DSA signature over a fresh nonce."""
        req = wire.enc({"name": self.name, "kem": self.params.kem, "sig": self.params.sig, "ek": self.ek,
                        "vk": self.vk, "nonce": os.urandom(32), "ts": int(self.clock() * 1000)})
        return {"req": req, "sig": signing.sign_bytes(self.params, self._sk, "join", req)}

    def send_join(self) -> str:
        return self._cloud().call("join_post", self.join_request())["uid"]

    @property
    def joined(self) -> bool:
        return self._me["cap"] is not None

    @property
    def groups(self) -> list[str]:
        cap = self._me["cap"]
        return sorted(cap["groups"]) if cap else []

    def fetch_mail(self) -> list[str]:
        """Fetch and process mailbox items: the sealed capability and rekey boxes.

        Returns a human readable line per processed item. Items that fail to verify are
        ignored (they cannot have come from the owner).
        """
        events: list[str] = []
        for item in self._cloud().call("mail_get", {"uid": self.uid}):
            mark = H(item["body"])[:12]
            if mark in self._me["mail_done"]:
                continue
            try:
                if item["kind"] == "cap":
                    self.accept_capability(item["body"], item["sig"])
                    events.append("capability received for groups: " + ", ".join(self.groups))
                elif item["kind"] == "rekey":
                    events.append(self._accept_rekey(item["body"], item["sig"]))
            except (VerifyError, KeyError, TypeError, WireError):
                events.append("ignored a mailbox item that failed verification")
                continue
            self._me["mail_done"] = (self._me["mail_done"] + [mark])[-200:]
        self._save()
        return events

    def accept_capability(self, box: bytes, sig: bytes) -> None:
        """Join: check the owner's signature, unseal the capability with ML-KEM, store it."""
        if not signing.check_obj(self.params, self._owner_vk(), "cap", [self.uid, box], sig):
            raise VerifyError("capability", "capability is not signed by the owner")
        cap = wire.dec(seal.unseal(self.params, self._dk, box, b"cap" + self.uid.encode("ascii")))
        if cap["uid"] != self.uid:
            raise VerifyError("capability", "capability is for another receiver")
        self._me["cap"] = cap
        self._me["seen"] = {}
        self._save()

    def _accept_rekey(self, box: bytes, sig: bytes) -> str:
        """Revoke (receiver part): open a rekey box bound to the pre-shared m_u."""
        cap = self._me["cap"]
        if cap is None:
            raise VerifyError("rekey", "no capability yet")
        if not signing.check_obj(self.params, self._owner_vk(), "rekey", [self.uid, box], sig):
            raise VerifyError("rekey", "rekey box is not signed by the owner")
        body = wire.dec(seal.unseal(self.params, self._dk, box, b"rekey" + self.uid.encode("ascii"), psk=cap["m"]))
        g, epoch = body["g"], body["e"]
        group = cap["groups"].get(g)
        if group is None:
            raise VerifyError("rekey", "rekey for a group outside the capability")
        group["keys"][str(epoch)] = body["key"]
        if body["reset"]:
            group["base"] = body["base"]
            group["keys"] = {k: v for k, v in group["keys"].items() if int(k) >= body["base"]}
        self._save()
        return f"new key for group {g}, epoch {epoch}" + (" (re-encrypted, old segments dropped)" if body["reset"] else "")

    # ------------------------------------------------------------------ requests
    def _cap(self) -> dict:
        cap = self._me["cap"]
        if cap is None:
            raise AccessDenied("this receiver has no capability yet (join not approved)")
        return cap

    def _group_keys(self, g: str) -> dict[int, bytes]:
        group = self._cap()["groups"].get(g)
        if group is None:
            raise AccessDenied(f"group {g} is outside this receiver's capability")
        return {int(e): k for e, k in group["keys"].items()}

    def _request(self, endpoint: str, req: dict) -> tuple[bytes, Any]:
        """Encrypt a request under the credential a_u so only the cloud can read it."""
        cap = self._cap()
        req = {**req, "ts": int(self.clock() * 1000), "nonce": os.urandom(12)}
        ct = aead_encrypt(token_key(cap["a"]), wire.enc(req), token_aad(self.uid, endpoint))
        return ct, self._cloud().call(endpoint, {"uid": self.uid, "ct": ct})

    # ------------------------------------------------------------------ states
    def _verified_states(self, g: str, report: Report, retry: bool = True) -> dict[int, dict]:
        """Verify checks on the published states. Returns epoch -> decrypted record table."""
        keys = self._group_keys(g)
        _, reply = self._request("states_get", {"g": g})
        headers: dict[int, StateHeader] = {}
        messages: dict[int, dict] = {}
        try:
            for msg in reply["states"]:
                cache_key = H(msg["hdr"], H(msg["ct"]), msg["sig"])
                hdr = self._sig_cache.get(cache_key)
                if hdr is None:
                    hdr = check_state_signature(self.params, self._owner_vk(), msg)
                    self._sig_cache[cache_key] = hdr
                if hdr.g != g or hdr.e in headers:
                    raise VerifyError("state signature", "state is for another group or duplicated")
                headers[hdr.e] = hdr
                messages[hdr.e] = msg
        except VerifyError as exc:
            raise report.fail("state signature", exc.detail) from exc
        except (KeyError, TypeError) as exc:
            raise report.fail("state signature", "malformed states reply") from exc
        if not headers:
            raise report.fail("state signature", "the cloud returned no state")
        report.ok("state signature", f"{len(headers)} state(s) signed by the owner")

        newest = max(headers)
        top = headers[newest]
        if newest > max(keys) and retry:
            # A rekey box may be waiting in the mailbox.
            self.fetch_mail()
            if max(self._group_keys(g)) > max(keys):
                report.checks.clear()
                return self._verified_states(g, report, retry=False)
        missing = [e for e in range(top.base, newest + 1) if e not in headers]
        if missing:
            raise report.fail("segments complete", f"missing state for epoch(s) {missing}")
        report.ok("segments complete", f"epochs {top.base} to {newest}")
        not_final = [e for e in range(top.base, newest) if not headers[e].final]
        if not_final:
            raise report.fail("older segments final", f"epoch(s) {not_final} are not final")
        report.ok("older segments final", "all closed segments carry a final state")
        now_ms = int(self.clock() * 1000)
        if top.final:
            raise report.fail("freshness", "the newest state is final: the cloud is hiding a newer epoch")
        if now_ms > top.exp:
            raise report.fail("freshness", "the current state has expired")
        report.fresh_until = top.exp / 1000.0
        report.ok("freshness", "current state is within its validity window")
        seen = self._me["seen"].get(g, {})
        if newest < max(keys):
            raise report.fail("no rollback", f"cloud presented epoch {newest}, a key for epoch {max(keys)} is held")
        if top.ver < seen.get("top", 0):
            raise report.fail("no rollback", f"version {top.ver} is older than {seen['top']} seen before")
        for e, hdr in headers.items():
            if hdr.ver < seen.get(str(e), 0):
                raise report.fail("no rollback", f"epoch {e}: version {hdr.ver} is older than {seen[str(e)]} seen before")
        report.ok("no rollback", f"version {top.ver}")

        tables: dict[int, dict] = {}
        for e in range(top.base, newest + 1):
            if e not in keys:
                raise AccessDenied(f"no key for group {g}, epoch {e}")
            cache_key = H(messages[e]["hdr"], H(messages[e]["ct"]))
            table = self._open_cache.get(cache_key)
            if table is None:
                k_st = group_subkeys(keys[e], g, e)[2]
                try:
                    table = open_state(k_st, messages[e])
                except VerifyError as exc:
                    raise report.fail("state signature", "state does not decrypt under the group key") from exc
                self._open_cache[cache_key] = table
            tables[e] = table
        self._pending_seen = (g, {"top": top.ver, **{str(e): h.ver for e, h in headers.items()}})
        return tables

    def _commit_seen(self) -> None:
        g, versions = self._pending_seen
        self._me["seen"][g] = versions
        self._save()

    # ------------------------------------------------------------------ TokenGen + Verify
    def search(self, g: str, keyword: str) -> SearchResult:
        """Algorithms 6 TokenGen and 8 Verify around the cloud's Search.

        TokenGen: for every live segment take c_w from the verified state, derive the
        addresses a_0..a_{c_w-1} and encrypt the token under a_u.
        Verify: state signature, segments complete, older segments final, freshness,
        no rollback, response signature, completeness, hash chain. Then unmask and apply
        add and delete entries in order.
        """
        report = Report()
        keyword = keyword.strip().lower()
        tables = self._verified_states(g, report)
        keys = self._group_keys(g)
        tag = index.keyword_tag(keyword)
        epochs = sorted(tables)
        plan: dict[int, tuple[int, bytes]] = {e: tables[e].get(tag, (0, CHAIN_START)) for e in epochs}
        derived: dict[int, tuple[bytes, bytes]] = {}
        segs = []
        for e in epochs:
            count = plan[e][0]
            k_idx = group_subkeys(keys[e], g, e)[0]
            addrs, masks = index.derive(self.prf, k_idx, [(keyword, i) for i in range(count)])
            derived[e] = (addrs.tobytes(), masks.tobytes())
            segs.append([e, derived[e][0]])
        token_ct, reply = self._request("search", {"g": g, "cur": max(epochs), "segs": segs})

        try:
            body_raw, sig = reply["body"], reply["sig"]
        except (KeyError, TypeError) as exc:
            raise report.fail("response signature", "malformed response") from exc
        if not signing.check_bytes(self.params, self._cloud_vk(), "resp", H(token_ct) + body_raw, sig):
            raise report.fail("response signature", "the cloud's ML-DSA signature is invalid")
        report.ok("response signature", "signed by the cloud, bound to this token")
        try:
            body = wire.dec(body_raw)
            got = {seg[0]: (seg[1], seg[2]) for seg in body["segs"]}
            if body["g"] != g or len(got) != len(body["segs"]):
                raise KeyError("group")
        except (WireError, KeyError, TypeError, IndexError) as exc:
            raise report.fail("completeness", "malformed response body") from exc
        total = 0
        for e in epochs:
            want_addrs = derived[e][0]
            have = got.get(e)
            if have is None or have[0] != want_addrs or len(have[1]) != plan[e][0] * index.VAL_LEN:
                returned = 0 if have is None else len(have[0]) // index.ADDR_LEN
                raise report.fail("completeness", f"epoch {e}: expected {plan[e][0]} entries in order, got {returned}")
            total += plan[e][0]
        if set(got) != set(epochs):
            raise report.fail("completeness", "response contains unexpected segments")
        report.ok("completeness", f"{total} entries, all expected addresses present")

        hits: dict[int, int] = {}
        for e in epochs:
            addrs, masks = derived[e]
            vals = got[e][1]
            count = plan[e][0]
            pairs = [(addrs[i * 32:(i + 1) * 32], vals[i * 5:(i + 1) * 5]) for i in range(count)]
            if chain_fold(CHAIN_START, pairs) != plan[e][1]:
                raise report.fail("hash chain", f"epoch {e}: chain head does not match the signed state")
            for i, (_, value) in enumerate(pairs):
                op, doc_id = index.unpack_value(index.xor5(value, masks[i * 5:(i + 1) * 5]))
                if op == index.OP_ADD:
                    hits[doc_id] = e
                elif op == index.OP_DEL:
                    hits.pop(doc_id, None)
                else:
                    raise report.fail("hash chain", "entry does not unmask to a valid operation")
        report.ok("hash chain", "chain heads match the signed state")
        self._commit_seen()
        return SearchResult(g, keyword, sorted(hits.items()), report, total)

    # ------------------------------------------------------------------ Decrypt
    def open_document(self, g: str, doc_id: int, epoch: int) -> Document:
        """Algorithm 9 Decrypt: verify the owner's document signature, then AES-GCM decrypt.

        Works only for documents whose group and epoch key this receiver holds.
        """
        keys = self._group_keys(g)
        if epoch not in keys:
            raise AccessDenied(f"no key for group {g}, epoch {epoch}")
        k_doc = group_subkeys(keys[epoch], g, epoch)[1]
        handle = doc_handle(k_doc, doc_id)
        _, reply = self._request("doc_get", {"g": g, "e": epoch, "handle": handle})
        return self.decrypt_document(g, doc_id, epoch, reply)

    def decrypt_document(self, g: str, doc_id: int, epoch: int, reply: dict) -> Document:
        """Decrypt a fetched document reply {blob, sig} after checking the owner's signature."""
        keys = self._group_keys(g)
        if epoch not in keys:
            raise AccessDenied(f"no key for group {g}, epoch {epoch}")
        k_doc = group_subkeys(keys[epoch], g, epoch)[1]
        handle = doc_handle(k_doc, doc_id)
        try:
            blob, sig = reply["blob"], reply["sig"]
        except (KeyError, TypeError) as exc:
            raise VerifyError("document signature", "malformed document reply") from exc
        if not signing.check_obj(self.params, self._owner_vk(), "doc", [g, epoch, handle, H(blob)], sig):
            raise VerifyError("document signature", "document is not the one signed by the owner")
        plain = wire.dec(aead_decrypt(k_doc, blob, doc_aad(g, epoch, doc_id), what="document decryption"))
        return Document(doc_id, epoch, plain["title"], plain["text"])


def describe_rejection(exc: Rejected) -> str:
    """Clear user facing text for a cloud rejection (shown in the Receiver tab)."""
    messages = {
        "revoked": "Access denied: this receiver has been revoked by the data owner.",
        "unknown_user": "Access denied: the owner has not approved this receiver.",
        "scope": "Access denied: this group is outside your capability.",
        "stale_epoch": "The group moved to a new epoch. Fetch your mailbox and search again.",
        "bad_token": "The cloud could not authenticate the request (wrong credential).",
        "stale_token": "The request timestamp is outside the allowed window (check the clock).",
        "no_such_doc": "The document is no longer stored at the cloud.",
        "bad_segment": "The requested segment was dropped (group re-encrypted).",
        "unknown_group": "The cloud does not know this group.",
    }
    return messages.get(exc.reason, f"The cloud rejected the request: {exc}")
