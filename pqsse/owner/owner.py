"""The data owner.

Implements the owner side of Setup, Join, BuildIndex, Update, Publish and Revoke
(policies R and RE). The owner is the only party that creates group keys.
All state is kept in a vault (encrypted at rest); nothing secret is ever logged.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import numpy as np

from .. import invite as invites
from .. import narrator, pqbackend
from ..core import chain, index, seal, signing, wire
from ..core.chain import CHAIN_START
from ..core.errors import PQSSEError, Rejected, VerifyError
from ..core.pairing import PublicIdentity
from ..core.index import doc_aad, doc_handle
from ..core.prims import H, aead_encrypt, group_subkeys, random_key
from ..core.state import DEFAULT_NMAX, StateHeader, fit_nmax, make_state
from ..gpu.batchprf import BatchPRF, CpuPRF
from ..pqbackend import DEFAULT_PARAMS, Params
from ..transport import CloudAPI

JOIN_WINDOW = 600.0
POLICY_R = "R"
POLICY_RE = "RE"
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def extract_keywords(text: str) -> list[str]:
    """Keywords of a document: lower case word tokens of 2 to 40 characters, unique."""
    return sorted({w for w in _WORD.findall(text.lower()) if 2 <= len(w) <= 40})


@dataclass
class DocInput:
    """A document to add. ``keywords`` overrides extraction (used by benchmarks)."""

    title: str
    text: str
    keywords: Sequence[str] | None = None
    doc_id: int | None = None


@dataclass
class JoinRequest:
    """A checked join request, shown to the owner for approval."""

    uid: str
    name: str
    ek: bytes
    vk: bytes
    fingerprint: str
    ts: float
    nonce: bytes = field(repr=False, default=b"")
    invite: str = ""                     # the invite id the request used (design note 002), or empty
    invite_name: str = ""                # whom the owner made that invite for


class Owner:
    """Data owner role."""

    def __init__(self, vault: Any, cloud: CloudAPI | None = None, prf: BatchPRF | None = None,
                 clock: Callable[[], float] = time.time, state_ttl: float = 86400.0) -> None:
        meta = vault.get("owner")
        if meta is None:
            raise PQSSEError("owner is not set up in this vault")
        self.vault = vault
        self.cloud = cloud
        self.prf = prf or CpuPRF()
        self.clock = clock
        self.state_ttl = state_ttl
        self.timings: dict[str, float] | None = None
        self._meta = meta
        self.params = Params(meta["kem"], meta["sig"])
        self.name: str = meta["name"]
        self.vk: bytes = meta["vk"]
        self._sk: bytes = meta["sk"]
        self.groups: dict[str, dict] = {n[len("group:"):]: vault.get(n) for n in vault.names("group:")}

    # ------------------------------------------------------------------ Setup
    @classmethod
    def create(cls, vault: Any, params: Params = DEFAULT_PARAMS, name: str = "owner", **kwargs: Any) -> "Owner":
        """Algorithm 1 Setup (owner part): ML-DSA signing key pair and empty state."""
        if vault.get("owner") is not None:
            raise PQSSEError("owner already exists in this vault")
        vk, sk = pqbackend.sig_keygen(params.sig)
        vault.put("owner", {"name": name, "kem": params.kem, "sig": params.sig, "vk": vk, "sk": sk,
                            "ctl_seq": 0, "cloud_pub": None, "receivers": {}, "nonces": []})
        narrator.emit("setup.owner", "The data owner", sig=params.sig, vk_bytes=len(vk))
        return cls(vault, **kwargs)

    @staticmethod
    def exists(vault: Any) -> bool:
        return vault.get("owner") is not None

    def public_identity(self) -> PublicIdentity:
        return PublicIdentity("owner", self.name, self.params, self.vk)

    def pair_cloud(self, ident: PublicIdentity) -> None:
        """Pair devices: install the cloud's authentic public keys."""
        if ident.role != "cloud":
            raise PQSSEError("not a cloud key file")
        if ident.params != self.params:
            raise PQSSEError("cloud uses a different parameter set")
        self._meta["cloud_pub"] = ident.to_wire()
        self._save_meta()
        narrator.emit("pair", "The data owner", other="the cloud")

    @property
    def cloud_pub(self) -> PublicIdentity | None:
        raw = self._meta["cloud_pub"]
        return None if raw is None else PublicIdentity.from_wire(raw)

    @property
    def receivers(self) -> dict[str, dict]:
        return self._meta["receivers"]

    # ------------------------------------------------------------------ helpers
    def _save_meta(self) -> None:
        self.vault.put("owner", self._meta)

    def _save_group(self, g: str) -> None:
        self.vault.put("group:" + g, self.groups[g])

    def _cloud(self) -> CloudAPI:
        if self.cloud is None:
            raise PQSSEError("owner is not connected to a cloud")
        return self.cloud

    def _send(self, endpoint: str, obj: Any) -> Any:
        """Send one of the owner's own signed messages. "duplicate" means the server already applied these exact
        bytes: the reply to an earlier attempt was lost and the transport sent them again, so it counts as accepted.
        Only the owner holds the signing key, so these bytes can only be the owner's own message."""
        try:
            return self._cloud().call(endpoint, obj)
        except Rejected as exc:
            if exc.reason == "duplicate":
                return {"ok": True, "repeat": True}
            raise

    def _tick(self, name: str, start: float) -> None:
        if self.timings is not None:
            self.timings[name] = self.timings.get(name, 0.0) + time.perf_counter() - start

    def _ctl(self, op: str, **fields: Any) -> None:
        """Send one control message: sealed to the cloud's ML-KEM key, signed, sequence numbered (paper Ctl)."""
        cloud_pub = self.cloud_pub
        if cloud_pub is None:
            self._cloud().call("info", None)   # an unreachable cloud is the first thing to report
            raise PQSSEError("pair with the cloud before sending control messages")
        seq = self._meta["ctl_seq"] + 1
        box = seal.seal(self.params, cloud_pub.ek, wire.enc({"seq": seq, "op": op, **fields}), b"ctl")
        sig = signing.sign_bytes(self.params, self._sk, "ctl", box)
        self._send("ctl", {"msg": box, "sig": sig})
        self._meta["ctl_seq"] = seq
        self._save_meta()

    def _group(self, g: str) -> dict:
        if g not in self.groups:
            raise PQSSEError(f"unknown group {g}")
        return self.groups[g]

    # ------------------------------------------------------------------ groups
    def create_group(self, g: str, nmax: int = DEFAULT_NMAX) -> None:
        """Create a group at epoch 1 with a fresh random key K_g^1 and publish its empty state."""
        if not g or len(g) > 64:
            raise PQSSEError("group name must be 1 to 64 characters")
        if g in self.groups:
            raise PQSSEError(f"group {g} already exists")
        self._ctl("group", g=g)
        self.groups[g] = {"epoch": 1, "base": 1, "keys": {"1": random_key()}, "seq": 0, "ver": 0,
                          "next_id": 1, "nmax": nmax, "kw": {"1": {}}, "docs": {}, "dirty": False, "exp": 0}
        self._save_group(g)
        narrator.emit("group", "The data owner", g=g)
        self.publish(g)

    def documents(self, g: str) -> list[dict]:
        """Live documents of a group, for the owner UI."""
        docs = self._group(g)["docs"]
        return [{"id": int(i), "title": d["title"], "text": d["text"], "epoch": d["e"], "keywords": len(d["kws"])}
                for i, d in sorted(docs.items(), key=lambda kv: int(kv[0]))]

    def overview(self, g: str) -> dict:
        """Epoch and segment overview of a group."""
        gs = self._group(g)
        segments = []
        for e in range(gs["base"], gs["epoch"] + 1):
            table = gs["kw"].get(str(e), {})
            segments.append({"epoch": e, "keywords": len(table), "entries": sum(v[0] for v in table.values()),
                             "final": e < gs["epoch"],
                             "docs": sum(1 for d in gs["docs"].values() if d["e"] == e)})
        return {"group": g, "epoch": gs["epoch"], "base": gs["base"], "version": gs["ver"], "seq": gs["seq"],
                "dirty": gs["dirty"], "expires": gs["exp"] / 1000.0, "segments": segments,
                "members": [u for u, r in self.receivers.items() if g in r["groups"] and not r["revoked"]]}

    # ------------------------------------------------------------------ Join
    def pending_joins(self) -> list[dict]:
        """Raw join requests waiting at the cloud mailbox. Only the owner may list them (design note 002 C)."""
        ts = int(self.clock() * 1000)
        sig = signing.sign_bytes(self.params, self._sk, "join_list", wire.enc({"ts": ts}))
        return self._cloud().call("join_list", {"ts": ts, "sig": sig})

    # ------------------------------------------------------------------ invites (design note 002)
    def create_invite(self, host: str, port: int, tls: str, name: str = "", days: float = invites.DEFAULT_DAYS) -> invites.Invite:
        """Make an invite for one person and register it at the cloud. The returned invite holds the one-time code."""
        cloud_pub = self.cloud_pub
        if cloud_pub is None:
            raise PQSSEError("pair with the cloud before inviting people")
        inv = invites.new_invite(host, port, tls, cloud_pub.fingerprint(), self.public_identity().fingerprint(), name, days)
        k_server, k_owner = invites.keys_from_code(inv.code)
        exp_ms = int(inv.expires * 1000)                 # the wire encoding has integers only
        self._ctl("invite", id=inv.id, k=k_server, exp=exp_ms)
        self._meta.setdefault("invites", {})[inv.id] = {"k": k_owner, "exp": exp_ms, "name": name, "used": False}
        self._save_meta()
        return inv

    def invites(self) -> list[dict]:
        """Invites made so far: id, name, expiry, used (the codes are not kept)."""
        return [{"id": i, "name": v["name"], "expires": v["exp"] / 1000.0, "used": v["used"]}
                for i, v in sorted(self._meta.get("invites", {}).items(), key=lambda kv: kv[1]["exp"])]

    def check_join(self, item: dict) -> JoinRequest:
        """Algorithm 2 Join (owner check): verify the proof of key ownership.

        The receiver signed (keys, nonce, timestamp) with the ML-DSA key in the request.
        Rejects a wrong proof, a stale timestamp, a reused nonce and foreign parameters.
        """
        try:
            req = wire.dec(item["req"])
            ek, vk, nonce, ts, name = req["ek"], req["vk"], req["nonce"], req["ts"], req["name"]
            kem, sig_alg = req["kem"], req["sig"]
        except (PQSSEError, KeyError, TypeError) as exc:
            raise VerifyError("join proof", "malformed join request") from exc
        if (kem, sig_alg) != (self.params.kem, self.params.sig):
            raise VerifyError("join proof", "parameter set mismatch")
        if not signing.check_bytes(self.params, vk, "join", item["req"], item["sig"]):
            raise VerifyError("join proof", "proof of key ownership is invalid")
        if abs(self.clock() - ts / 1000.0) > JOIN_WINDOW:
            raise VerifyError("join proof", "join request is not fresh")
        if nonce in self._meta["nonces"]:
            raise VerifyError("join proof", "join nonce was already used")
        invite_id = req.get("invite")
        invite_name = ""
        if invite_id is not None:
            record = self._meta.get("invites", {}).get(str(invite_id))
            if record is None:
                raise VerifyError("join proof", "the request names an invite this owner did not make")
            if record["used"]:
                raise VerifyError("join proof", "this invite was already used")
            if self.clock() * 1000 > record["exp"]:
                raise VerifyError("join proof", "this invite has expired")
            if not invites.check_proof(record["k"], item["req"], item.get("proof_o", b"")):
                raise VerifyError("join proof", "the invite code does not match")
            invite_name = record["name"]
        ident = PublicIdentity("receiver", name, self.params, vk, ek)
        return JoinRequest(H(ek, vk)[:16].hex(), name, ek, vk, ident.fingerprint(), ts / 1000.0, nonce,
                           str(invite_id or ""), invite_name)

    def approve_join(self, item: dict, groups: Sequence[str]) -> str:
        """Algorithm 2 Join (owner approval): issue the capability and the credential.

        Capability (sealed with ML-KEM to the receiver, signed by the owner):
        a_u, m_u and the keys of every live segment of the permitted groups.
        Credential (sealed to the cloud): a_u and the scope.
        """
        req = self.check_join(item)
        cloud_pub = self.cloud_pub
        if cloud_pub is None:
            raise PQSSEError("pair with the cloud before approving receivers")
        a_u, m_u = random_key(), random_key()
        cap_groups = {}
        for g in groups:
            gs = self._group(g)
            cap_groups[g] = {"base": gs["base"],
                             "keys": {str(e): gs["keys"][str(e)] for e in range(gs["base"], gs["epoch"] + 1)}}
        uid_raw = req.uid.encode("ascii")
        cap = wire.enc({"uid": req.uid, "a": a_u, "m": m_u, "groups": cap_groups})
        cap_box = seal.seal(self.params, req.ek, cap, b"cap" + uid_raw)
        cap_sig = signing.sign_obj(self.params, self._sk, "cap", [req.uid, cap_box])
        cred = wire.enc({"a": a_u, "groups": sorted(groups)})
        cred_box = seal.seal(self.params, cloud_pub.ek, cred, b"cred" + uid_raw)
        self._ctl("cred", uid=req.uid, box=cred_box, cap=cap_box, cap_sig=cap_sig)
        self._meta["nonces"] = (self._meta["nonces"] + [req.nonce])[-500:]
        if req.invite:
            self._meta["invites"][req.invite]["used"] = True
        self.receivers[req.uid] = {"name": req.name, "ek": req.ek, "vk": req.vk, "a": a_u, "m": m_u,
                                   "groups": sorted(groups), "revoked": False}
        self._save_meta()
        narrator.emit("join.approved", req.name, groups=sorted(groups), cap_bytes=len(cap_box))
        return req.uid

    # ------------------------------------------------------------------ BuildIndex / Update
    def build_index(self, g: str, docs: Sequence[DocInput]) -> list[int]:
        """Algorithm 3 BuildIndex: encrypt and index a document set as one signed batch."""
        return self._apply(g, list(docs), [], kind="build_index")

    def add_document(self, g: str, title: str, text: str, keywords: Sequence[str] | None = None) -> int:
        """Algorithm 4 Update (add)."""
        return self._apply(g, [DocInput(title, text, keywords)], [])[0]

    def delete_document(self, g: str, doc_id: int) -> None:
        """Algorithm 4 Update (delete): append masked delete entries, remove the ciphertext."""
        self._apply(g, [], [doc_id])

    def edit_document(self, g: str, doc_id: int, title: str, text: str) -> int:
        """Edit = delete followed by add under a fresh id, in one batch."""
        return self._apply(g, [DocInput(title, text)], [doc_id])[0]

    def _apply(self, g: str, adds: list[DocInput], dels: list[int], reset: bool = False,
               kind: str = "update") -> list[int]:
        """Build, sign and send one update batch; commit local state only if accepted.

        For keyword w with counter c_w: address a = F(K_idx, sstr(w) || u32(c_w) || 0),
        value v = (op || id) XOR F(K_idx, sstr(w) || u32(c_w) || 1)[0:5],
        chain d_w = H(d_w || a || v).
        """
        gs = self._group(g)
        if not reset and gs.get("reset_pending"):
            self._finish_reset(g)            # an interrupted revocation (policy RE) goes first
            gs = self._group(g)
        e = gs["epoch"]
        k_idx, k_doc, _ = group_subkeys(gs["keys"][str(e)], g, e)
        table: dict[str, list] = {} if reset else gs["kw"].setdefault(str(e), {})
        work: dict[str, list] = {}
        slot_of: dict[str, int] = {}
        items: list[tuple[str, int]] = []
        slots: list[int] = []
        ops: list[int] = []
        ids: list[int] = []

        def touch(word: str, op: int, doc_id: int) -> None:
            state = work.get(word)
            if state is None:
                state = work[word] = list(table.get(word, (0, CHAIN_START)))
                slot_of[word] = len(slot_of)
            items.append((word, state[0]))
            slots.append(slot_of[word])
            state[0] += 1
            ops.append(op)
            ids.append(doc_id)

        next_id = gs["next_id"]
        new_docs: dict[str, dict] = {}
        wire_docs: list[list[bytes]] = []
        t0 = time.perf_counter()
        for doc in adds:
            if doc.doc_id is None:
                doc_id, next_id = next_id, next_id + 1
            else:
                doc_id = doc.doc_id
            kws = sorted(set(doc.keywords)) if doc.keywords is not None else extract_keywords(doc.title + " " + doc.text)
            for word in kws:
                touch(word, index.OP_ADD, doc_id)
            blob = aead_encrypt(k_doc, wire.enc({"title": doc.title, "text": doc.text}), doc_aad(g, e, doc_id))
            handle = doc_handle(k_doc, doc_id)
            sig = signing.sign_obj(self.params, self._sk, "doc", [g, e, handle, H(blob)])
            wire_docs.append([handle, blob, sig])
            new_docs[str(doc_id)] = {"e": e, "title": doc.title, "text": doc.text, "kws": kws}
        self._tick("documents (AES-GCM + ML-DSA)", t0)
        wire_del: list[list] = []
        for doc_id in dels:
            rec = gs["docs"].get(str(doc_id))
            if rec is None:
                raise PQSSEError(f"no document {doc_id} in group {g}")
            for word in rec["kws"]:
                touch(word, index.OP_DEL, doc_id)
            old_doc_key = group_subkeys(gs["keys"][str(rec["e"])], g, rec["e"])[1]
            wire_del.append([rec["e"], doc_handle(old_doc_key, doc_id)])

        t0 = time.perf_counter()
        addrs, masks = index.derive(self.prf, k_idx, items)
        self._tick("PRF addresses and masks", t0)
        n = len(items)
        plain = np.zeros((n, index.VAL_LEN), dtype=np.uint8)
        if n:
            plain[:, 0] = np.array(ops, dtype=np.uint8)
            plain[:, 1:] = np.array(ids, dtype=">u4").view(np.uint8).reshape(n, 4)
        vals = plain ^ masks
        t0 = time.perf_counter()
        heads = [None] * len(slot_of)
        for word, slot in slot_of.items():
            heads[slot] = work[word][1]
        chain.update_heads(self.prf, heads, slots, addrs, vals)
        for word, slot in slot_of.items():
            work[word][1] = heads[slot]
        self._tick("hash chain", t0)

        t0 = time.perf_counter()
        msg = wire.enc({"g": g, "e": e, "seq": gs["seq"] + 1, "addrs": addrs.tobytes(), "vals": vals.tobytes(),
                        "docs": wire_docs, "del": wire_del, "reset": reset})
        sig = signing.sign_bytes(self.params, self._sk, "batch", msg)
        self._tick("batch signature (ML-DSA)", t0)
        t0 = time.perf_counter()
        self._send("update", {"msg": msg, "sig": sig})
        self._tick("cloud store", t0)

        # The cloud accepted the batch: commit.
        if reset:
            gs["kw"] = {str(e): {}}
            gs["keys"] = {str(e): gs["keys"][str(e)]}
            gs["docs"] = {}
            gs["base"] = e
        gs["kw"][str(e)].update(work)
        for doc_id in dels:
            gs["docs"].pop(str(doc_id), None)
        gs["docs"].update(new_docs)
        gs["seq"] += 1
        gs["next_id"] = next_id
        gs["dirty"] = True
        self._save_group(g)
        narrator.emit("reencrypt" if reset else kind, "The data owner", g=g, e=e, docs=len(adds), adds=len(adds),
                      deletes=len(dels), entries=n, bytes=len(msg), engine=self.prf.name)
        return [int(i) for i in new_docs]

    # ------------------------------------------------------------------ Publish
    def publish(self, g: str, final: bool = False) -> int:
        """Algorithm 5 Publish: signed, encrypted, padded state ST_{g,e} of the current epoch.

        Returns the published version. ``final`` marks the segment as closed (Revoke).
        """
        gs = self._group(g)
        if gs.get("reset_pending") and not final:
            self._finish_reset(g)            # never publish the new epoch before its rebuild is stored
            gs = self._group(g)
        e = gs["epoch"]
        k_st = group_subkeys(gs["keys"][str(e)], g, e)[2]
        records: dict[bytes, tuple[int, bytes]] = {}
        for word, (count, head) in gs["kw"].get(str(e), {}).items():
            tag = index.keyword_tag(word)
            if tag in records:
                raise PQSSEError("keyword tag collision, cannot publish")
            records[tag] = (count, head)
        nmax = fit_nmax(len(records), gs["nmax"])
        exp = int((self.clock() + self.state_ttl) * 1000)
        header = StateHeader(g, e, gs["ver"] + 1, exp, final, gs["base"])
        t0 = time.perf_counter()
        msg = make_state(self.params, self._sk, k_st, header, records, nmax)
        self._tick("state (AES-GCM + ML-DSA)", t0)
        self._send("state_put", msg)
        gs["ver"] += 1
        gs["nmax"] = nmax
        gs["exp"] = exp
        gs["dirty"] = False
        self._save_group(g)
        narrator.emit("publish", "The data owner", g=g, e=e, ver=gs["ver"], records=len(records), bytes=len(msg["ct"]),
                      final="yes" if final else "no")
        return gs["ver"]

    # ------------------------------------------------------------------ Revoke
    def revoke(self, uid: str, policy: str = POLICY_R) -> list[str]:
        """Algorithm 10 Revoke with policy R (rotate) or RE (rotate and re-encrypt).

        R:  deauthorize at the cloud, publish the final state of the old epoch, new epoch
            key, rekey boxes sealed with ML-KEM and bound to each remaining receiver's m_v.
            Old segments stay.
        RE: additionally rebuild the whole group under the new epoch in a reset batch;
            the cloud drops all older segments and documents.
        Returns the list of rotated groups.
        """
        if policy not in (POLICY_R, POLICY_RE):
            raise PQSSEError("policy must be R or RE")
        rec = self.receivers.get(uid)
        if rec is None or rec["revoked"]:
            raise PQSSEError("unknown or already revoked receiver")
        self._ctl("deauth", uid=uid)
        rec["revoked"] = True
        self._save_meta()
        rotated = []
        for g in rec["groups"]:
            if g in self.groups:
                self._rotate(g, policy)
                rotated.append(g)
        remaining = sorted({r["name"] for r in self.receivers.values()
                            if not r["revoked"] and any(g in r["groups"] for g in rotated)})
        narrator.emit("revoke", rec["name"], policy=policy, groups=rotated,
                      remaining=[narrator.display_name(n) for n in remaining])
        return rotated

    def _rotate(self, g: str, policy: str) -> None:
        gs = self._group(g)
        old = gs["epoch"]
        new = old + 1
        reset = policy == POLICY_RE
        self.publish(g, final=True)
        new_key = random_key()
        base = new if reset else gs["base"]
        boxes = {}
        for uid, rec in self.receivers.items():
            if rec["revoked"] or g not in rec["groups"]:
                continue
            body = wire.enc({"g": g, "e": new, "key": new_key, "base": base, "reset": reset})
            box = seal.seal(self.params, rec["ek"], body, b"rekey" + uid.encode("ascii"), psk=rec["m"])
            boxes[uid] = [box, signing.sign_obj(self.params, self._sk, "rekey", [uid, box])]
        self._ctl("epoch", g=g, e=new, reset=reset, boxes=boxes)
        gs["epoch"] = new
        gs["keys"][str(new)] = new_key
        gs["kw"][str(new)] = {}
        self._save_group(g)
        if reset:
            gs["reset_pending"] = True      # the server now expects the reset batch; remembered across a failure
            self._save_group(g)
            self._finish_reset(g)
        self.publish(g)

    def _finish_reset(self, g: str) -> None:
        """Send the policy RE rebuild of a group. If it fails (no network, a full disk at the server), the group stays
        marked and the next change to it, or resume_pending(), sends the rebuild first. Same messages, no protocol change."""
        gs = self._group(g)
        live = [DocInput(d["title"], d["text"], d["kws"], int(i))
                for i, d in sorted(gs["docs"].items(), key=lambda kv: int(kv[0]))]
        self._apply(g, live, [], reset=True)
        gs = self._group(g)
        gs.pop("reset_pending", None)
        self._save_group(g)

    def resume_pending(self) -> list[str]:
        """Finish every interrupted policy RE rebuild and publish it. Returns the groups that were finished."""
        done = []
        for g in sorted(self.groups):
            if self.groups[g].get("reset_pending"):
                self._finish_reset(g)
                self.publish(g)
                done.append(g)
        return done

    # ------------------------------------------------------------------ reference (tests, UI)
    def plaintext_search(self, g: str, keyword: str) -> set[int]:
        """Plaintext reference result: ids of live documents containing the keyword."""
        return {int(i) for i, d in self._group(g)["docs"].items() if keyword in d["kws"]}


def new_owner_id() -> str:
    """Random label for throwaway owners (benchmarks, Attack Lab)."""
    return "owner-" + os.urandom(3).hex()
