"""The data owner.

Implements the owner side of Setup, Join, BuildIndex, Update, Publish and Revoke
(policies R and RE). The owner is the only party that creates group keys.
All state is kept in a vault (encrypted at rest); nothing secret is ever logged.
"""
from __future__ import annotations

import copy
import csv
import functools
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

from .. import invite as invites
from .. import narrator, pqbackend
from ..core import chain, index, seal, signing, wire
from ..core.chain import CHAIN_START
from ..core.errors import PQSSEError, Rejected, VerifyError
from ..core.pairing import PublicIdentity
from ..core.index import doc_aad, doc_handle
from ..core.prims import H, aead_decrypt, aead_encrypt, group_subkeys, random_key
from ..core.state import DEFAULT_NMAX, StateHeader, check_state_signature, fit_nmax, make_state
from ..gpu.batchprf import BatchPRF, CpuPRF
from ..pqbackend import DEFAULT_PARAMS, Params
from ..transport import CloudAPI, OwnerTagged

JOIN_WINDOW = 600.0
POLICY_R = "R"
BATCH_DOCS = 5_000                     # design note 005 A: a batch holds at most this many documents ...
BATCH_BYTES = 32 * 1024 * 1024         # ... and about this many bytes (the server accepts 64 MiB)
POLICY_RE = "RE"
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def extract_keywords(text: str) -> list[str]:
    """Keywords of a document: lower case word tokens of 2 to 40 characters, unique."""
    return sorted({w for w in _WORD.findall(text.lower()) if 2 <= len(w) <= 40})


def _logged(what: str, detail: Callable[..., dict], skip_empty: bool = False):
    """Design note 007: record an owner action in the activity log once it is accepted or refused.
    Only the outermost action is recorded (a revocation's own publishes are part of the revocation)."""
    def wrap(fn):
        @functools.wraps(fn)
        def inner(self, *args, **kwargs):
            if self._log_depth:
                return fn(self, *args, **kwargs)
            self._log_depth += 1
            try:
                result = fn(self, *args, **kwargs)
            except Rejected as exc:
                self._log_depth -= 1
                self.log_event(what, _safe_detail(detail, self, args, kwargs, None), exc.reason)
                raise
            except BaseException:
                self._log_depth -= 1
                raise
            self._log_depth -= 1
            if not (skip_empty and not result):
                self.log_event(what, _safe_detail(detail, self, args, kwargs, result), "accepted")
            return result
        return inner
    return wrap


def _safe_detail(detail: Callable[..., dict], owner, args, kwargs, result) -> dict:
    try:
        return detail(owner, *args, result=result, **kwargs)
    except Exception:  # noqa: BLE001 - a log line must never break the action it records
        return {}


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
        self._log_depth = 0
        if "recovery_key" not in self._meta:          # design note 006 C; older keys get escrowed by resume_pending
            self._meta["recovery_key"] = random_key()
            self._meta["escrow_pending"] = True
            self._save_meta()

    # ------------------------------------------------------------------ Setup
    @classmethod
    def create(cls, vault: Any, params: Params = DEFAULT_PARAMS, name: str = "owner", **kwargs: Any) -> "Owner":
        """Algorithm 1 Setup (owner part): ML-DSA signing key pair and empty state."""
        if vault.get("owner") is not None:
            raise PQSSEError("owner already exists in this vault")
        vk, sk = pqbackend.sig_keygen(params.sig)
        vault.put("owner", {"name": name, "kem": params.kem, "sig": params.sig, "vk": vk, "sk": sk,
                            "ctl_seq": 0, "cloud_pub": None, "receivers": {}, "nonces": [],
                            "recovery_key": random_key()})
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
        return OwnerTagged(self.cloud, H(self.vk)[:8].hex())

    # ------------------------------------------------------------------ write-ahead journal (design note 006 B)
    # Two kinds of channel, each with at most one message in flight: "ctl" (control messages; they change the
    # owner record, and "epoch" also the group's record) and "group:<g>" (update batches and states of one group;
    # they change only that group's record). A channel is settled before any message that touches its records,
    # so a batch stuck at the server never blocks a revocation, and two committed effects never overwrite each other.
    def _commit_send(self, channel: str, endpoint: str, obj: Any, change: Callable[["_Draft"], None]) -> Any:
        """Send one signed message and commit its local effect together with the server's acceptance.

        ``change`` applies the effect to a draft (deep copies of the records it touches). The signed bytes and the
        resulting records are stored as one vault record before sending. Accepted or ``duplicate``: the records
        are installed and the journal record removed. A definite refusal: nothing changes. No answer: the journal
        record stays and is sent again, the same bytes, before the next message on that channel."""
        if self.vault.get(JOURNAL + channel) is not None:
            raise PQSSEError("internal: a message is still unsettled on " + channel)
        draft = _Draft(self)
        change(draft)
        records = draft.records()
        self.vault.put(JOURNAL + channel, {"endpoint": endpoint, "obj": obj, "records": records})
        try:
            reply = self._send(endpoint, obj)
        except Rejected:
            self.vault.delete(JOURNAL + channel)
            raise
        self._install(channel, records)
        return reply

    def _install(self, channel: str, records: dict) -> None:
        """Write the committed records, then drop the journal record. Installed in place, so references stay valid."""
        for name, value in records.items():
            self.vault.put(name, value)
        for name, value in records.items():
            if name == "owner":
                self._meta.clear()
                self._meta.update(value)
            elif name.startswith("group:"):
                g = name[len("group:"):]
                if g in self.groups:
                    self.groups[g].clear()
                    self.groups[g].update(value)
                else:
                    self.groups[g] = value
        self.vault.delete(JOURNAL + channel)

    def _settle(self, channel: str) -> str:
        """Settle a message whose answer never arrived: send the same bytes again. Returns what happened.
        Raises CloudUnavailable (and keeps the record) when the server still cannot be reached."""
        pending = self.vault.get(JOURNAL + channel)
        if pending is None:
            return ""
        try:
            self._send(pending["endpoint"], pending["obj"])
        except Rejected:
            self.vault.delete(JOURNAL + channel)      # the server never applied it: nothing to commit
            return "dropped"
        self._install(channel, pending["records"])
        return "committed"

    def _settle_group(self, g: str) -> None:
        """Before anything is built for group g: settle a control message (an epoch change touches the group) and the
        group's own channel."""
        self._settle("ctl")
        self._settle("group:" + g)

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

    def _ctl(self, op: str, change: Callable[["_Draft"], None] | None = None, **fields: Any) -> None:
        """Send one control message: sealed to the cloud's ML-KEM key, signed, sequence numbered (paper Ctl).
        ``change`` is the local effect, committed together with the server's acceptance."""
        cloud_pub = self.cloud_pub
        if cloud_pub is None:
            self._cloud().call("info", None)   # an unreachable cloud is the first thing to report
            raise PQSSEError("pair with the cloud before sending control messages")
        self._settle("ctl")                    # the sequence number below must follow the settled one
        if "g" in fields and fields["g"] in self.groups:
            self._settle("group:" + fields["g"])
        seq = self._meta["ctl_seq"] + 1
        box = seal.seal(self.params, cloud_pub.ek, wire.enc({"seq": seq, "op": op, **fields}), b"ctl")
        sig = signing.sign_bytes(self.params, self._sk, "ctl", box)

        def effect(d: _Draft) -> None:
            d.meta["ctl_seq"] = seq
            if change is not None:
                change(d)
        self._commit_send("ctl", "ctl", {"msg": box, "sig": sig}, effect)

    def _group(self, g: str) -> dict:
        if g not in self.groups:
            raise PQSSEError(f"unknown group {g}")
        return self.groups[g]

    # ------------------------------------------------------------------ groups
    @_logged("group.create", lambda o, g, nmax=0, result=None: {"group": g})
    def create_group(self, g: str, nmax: int = DEFAULT_NMAX) -> None:
        """Create a group at epoch 1 with a fresh random key K_g^1 and publish its empty state."""
        if not g or len(g) > 64:
            raise PQSSEError("group name must be 1 to 64 characters")
        if g in self.groups:
            raise PQSSEError(f"group {g} already exists")
        fresh = {"epoch": 1, "base": 1, "keys": {"1": random_key()}, "seq": 0, "ver": 0,
                 "next_id": 1, "nmax": nmax, "kw": {"1": {}}, "docs": {}, "dirty": False, "exp": 0}
        self._ctl("group", change=lambda d: d.new_group(g, fresh), g=g, okeys=[self._okey(g, 1, fresh["keys"]["1"])])
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
    @_logged("invite.create", lambda o, host, port, tls, name="", days=0, result=None:
             {"name": name, "invite": result.id if result else "", "server": f"{host}:{port}"})
    def create_invite(self, host: str, port: int, tls: str, name: str = "", days: float = invites.DEFAULT_DAYS) -> invites.Invite:
        """Make an invite for one person and register it at the cloud. The returned invite holds the one-time code."""
        cloud_pub = self.cloud_pub
        if cloud_pub is None:
            raise PQSSEError("pair with the cloud before inviting people")
        inv = invites.new_invite(host, port, tls, cloud_pub.fingerprint(), self.public_identity().fingerprint(), name, days)
        k_server, k_owner = invites.keys_from_code(inv.code)
        exp_ms = int(inv.expires * 1000)                 # the wire encoding has integers only
        def effect(d: _Draft) -> None:
            d.meta.setdefault("invites", {})[inv.id] = {"k": k_owner, "exp": exp_ms, "name": name, "used": False}
        self._ctl("invite", change=effect, id=inv.id, k=k_server, exp=exp_ms)
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

    @_logged("join.approve", lambda o, item, groups, result=None:
             {"receiver": o.receivers.get(result, {}).get("name", ""), "uid": result or "", "groups": sorted(groups),
              "fingerprint": PublicIdentity("receiver", "", o.params, o.receivers[result]["vk"],
                                            o.receivers[result]["ek"]).fingerprint() if result else ""})
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
        record = {"name": req.name, "ek": req.ek, "vk": req.vk, "a": a_u, "m": m_u, "groups": sorted(groups), "revoked": False}

        def effect(d: _Draft) -> None:
            d.meta["nonces"] = (d.meta["nonces"] + [req.nonce])[-500:]
            if req.invite:
                d.meta["invites"][req.invite]["used"] = True
            d.meta["receivers"][req.uid] = record
        self._ctl("cred", change=effect, uid=req.uid, box=cred_box, cap=cap_box, cap_sig=cap_sig,
                  orecs=[self._orec(req.uid, record)])
        narrator.emit("join.approved", req.name, groups=sorted(groups), cap_bytes=len(cap_box))
        return req.uid

    # ------------------------------------------------------------------ BuildIndex / Update
    @_logged("doc.add", lambda o, g, docs, result=None:
             {"group": g, "count": len(docs), "titles": [d.title for d in list(docs)[:20]], "ids": (result or [])[:20]})
    def build_index(self, g: str, docs: Sequence[DocInput]) -> list[int]:
        """Algorithm 3 BuildIndex: encrypt and index a document set, in as many signed batches as it needs.

        Receivers search only up to the counters of the published state, so batches sent but not yet
        published are invisible to them (design note 005 A). Publish once at the end."""
        ids: list[int] = []
        for n, chunk in enumerate(_chunks(list(docs))):
            ids += self._apply(g, chunk, [], kind="build_index" if n == 0 else "update")
        return ids

    @_logged("doc.add", lambda o, g, title, text, keywords=None, result=None: {"group": g, "title": title, "id": result})
    def add_document(self, g: str, title: str, text: str, keywords: Sequence[str] | None = None) -> int:
        """Algorithm 4 Update (add)."""
        return self._apply(g, [DocInput(title, text, keywords)], [])[0]

    @_logged("doc.delete", lambda o, g, doc_id, result=None: {"group": g, "id": doc_id})
    def delete_document(self, g: str, doc_id: int) -> None:
        """Algorithm 4 Update (delete): append masked delete entries, remove the ciphertext."""
        self._apply(g, [], [doc_id])

    @_logged("doc.edit", lambda o, g, doc_id, title, text, result=None: {"group": g, "old_id": doc_id, "id": result, "title": title})
    def edit_document(self, g: str, doc_id: int, title: str, text: str) -> int:
        """Edit = delete followed by add under a fresh id, in one batch."""
        return self._apply(g, [DocInput(title, text)], [doc_id])[0]

    def _apply(self, g: str, adds: list[DocInput], dels: list[int], reset: bool = False,
               kind: str = "update", rest: dict | None = None, rebuilding: bool = False) -> list[int]:
        """Build, sign and send one update batch; commit local state only if accepted.

        For keyword w with counter c_w: address a = F(K_idx, sstr(w) || u32(c_w) || 0),
        value v = (op || id) XOR F(K_idx, sstr(w) || u32(c_w) || 1)[0:5],
        chain d_w = H(d_w || a || v).
        """
        self._group(g)
        self._settle_group(g)                # counters and sequence numbers below must follow the settled state
        if not reset and g in self._meta.get("rotations", {}):
            self._rotate(g, self._meta["rotations"][g])   # never new content under a key a revoked receiver holds
        gs = self._group(g)
        if not reset and not rebuilding and (gs.get("reset_pending") or gs.get("rebuild_rest")):
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
            blob = aead_encrypt(k_doc, wire.enc({"title": doc.title, "text": doc.text, "kws": kws}), doc_aad(g, e, doc_id))
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
        def effect(d: _Draft) -> None:          # committed only once the cloud accepted the batch
            ds = d.group(g)
            if reset:
                ds["kw"] = {str(e): {}}
                ds["keys"] = {str(e): ds["keys"][str(e)]}
                ds["docs"] = {}
                ds["base"] = e
                ds.pop("reset_pending", None)
                if rest:
                    ds["rebuild_rest"] = copy.deepcopy(rest)   # documents of the rebuild still to send
            if rebuilding:
                for doc_id in new_docs:
                    ds.get("rebuild_rest", {}).pop(doc_id, None)
                if not ds.get("rebuild_rest"):
                    ds.pop("rebuild_rest", None)
            ds["kw"].setdefault(str(e), {}).update(copy.deepcopy(work))
            for doc_id in dels:
                ds["docs"].pop(str(doc_id), None)
            ds["docs"].update(copy.deepcopy(new_docs))
            ds["seq"] += 1
            ds["next_id"] = next_id
            ds["dirty"] = True
        self._commit_send("group:" + g, "update", {"msg": msg, "sig": sig}, effect)
        self._tick("cloud store", t0)
        narrator.emit("reencrypt" if reset else kind, "The data owner", g=g, e=e, docs=len(adds), adds=len(adds),
                      deletes=len(dels), entries=n, bytes=len(msg), engine=self.prf.name)
        return [int(i) for i in new_docs]

    # ------------------------------------------------------------------ Publish
    @_logged("publish", lambda o, g, final=False, result=None: {"group": g, "version": result, "final": final})
    def publish(self, g: str, final: bool = False) -> int:
        """Algorithm 5 Publish: signed, encrypted, padded state ST_{g,e} of the current epoch.

        Returns the published version. ``final`` marks the segment as closed (Revoke).
        """
        self._group(g)
        self._settle_group(g)
        if not final and g in self._meta.get("rotations", {}):
            self._rotate(g, self._meta["rotations"][g])   # finishes with its own publish
            return self._group(g)["ver"]
        gs = self._group(g)
        if (gs.get("reset_pending") or gs.get("rebuild_rest")) and not final:
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
        def effect(d: _Draft) -> None:
            ds = d.group(g)
            ds["ver"] += 1
            ds["nmax"] = nmax
            ds["exp"] = exp
            ds["dirty"] = False
        self._commit_send("group:" + g, "state_put", msg, effect)
        narrator.emit("publish", "The data owner", g=g, e=e, ver=gs["ver"], records=len(records), bytes=len(msg["ct"]),
                      final="yes" if final else "no")
        return gs["ver"]

    # ------------------------------------------------------------------ recovery escrow (design note 006 C)
    def _okey(self, g: str, e: int, key: bytes) -> list:
        return [g, e, aead_encrypt(self._meta["recovery_key"], key, b"okey" + wire.sstr(g) + wire.u32(e))]

    def _orec(self, uid: str, rec: dict) -> list:
        return [uid, aead_encrypt(self._meta["recovery_key"], wire.enc(rec), b"orec" + uid.encode("ascii"))]

    def escrow_all(self) -> None:
        """Seal every live epoch key and every receiver record under the recovery key and store them at the server
        (once, for owners made before design note 006 C)."""
        okeys = [self._okey(g, int(e), k) for g, gs in sorted(self.groups.items()) for e, k in sorted(gs["keys"].items())]
        orecs = [self._orec(uid, rec) for uid, rec in sorted(self.receivers.items())]

        def effect(d: _Draft) -> None:
            d.meta.pop("escrow_pending", None)
        self._ctl("escrow", change=effect, okeys=okeys, orecs=orecs)

    def _sync_request(self, label: str, fields: dict) -> dict:
        ts = int(self.clock() * 1000)
        sig = signing.sign_bytes(self.params, self._sk, label, wire.enc({**fields, "ts": ts}))
        return {**fields, "ts": ts, "sig": sig}

    @_logged("recovery", lambda o, result=None: {"done": result or []})
    def recover(self) -> list[str]:
        """Design note 006 C: bring an owner restored from an older backup back in line with the server.

        Fetches the server's view (owner-signed request), opens the escrowed epoch keys and receiver records with
        the recovery key, downloads and checks every stored document, and then rebuilds each group with policy RE
        (no one removed): a clean index under a new epoch, with rekey boxes for every receiver the server still
        accepts. Returns a line per finding. Documents of an epoch whose key cannot be recovered are reported."""
        for channel in ["ctl"] + ["group:" + g for g in sorted(self.groups)]:
            try:
                self._settle(channel)
            except Rejected:
                pass
        sync = self._cloud().call("owner_sync", self._sync_request("owner_sync", {}))
        notes: list[str] = []
        rkey = self._meta["recovery_key"]
        receivers = dict(self.receivers)
        for uid, box, revoked in sync["receivers"]:
            try:
                rec = wire.dec(aead_decrypt(rkey, box, b"orec" + uid.encode("ascii")))
            except VerifyError:
                notes.append(f"receiver {uid[:8]}: record not readable with this recovery key")
                continue
            rec["revoked"] = bool(revoked) or rec.get("revoked", False)
            receivers[uid] = rec
        groups: dict[str, dict] = {}
        for sg in sync["groups"]:
            g = sg["g"]
            local = self.groups.get(g, {})
            keys = dict(local.get("keys", {}))
            for e, box in sg["okeys"]:
                try:
                    keys.setdefault(str(e), aead_decrypt(rkey, box, b"okey" + wire.sstr(g) + wire.u32(int(e))))
                except VerifyError:
                    notes.append(f"{g}: the key of epoch {e} is not readable with this recovery key")
            docs, lost = self._recover_docs(g, sg, keys, local.get("docs", {}))
            if lost:
                notes.append(f"{g}: {lost} document(s) could not be recovered (no key for their epoch)")
            ver = max([check_state_signature(self.params, self.vk, s).ver for s in sg["states"]
                       if "hdr" in s and StateHeader.decode(s["hdr"]).e == sg["epoch"]] or [0])
            groups[g] = {"epoch": sg["epoch"], "base": sg["base"], "seq": sg["seq"], "ver": ver,
                         "keys": {e: k for e, k in keys.items() if int(e) >= sg["base"]},
                         "next_id": max([int(i) for i in docs] + [local.get("next_id", 1) - 1]) + 1,
                         "nmax": local.get("nmax", DEFAULT_NMAX), "kw": {str(sg["epoch"]): {}}, "docs": docs,
                         "dirty": True, "exp": 0}
            if sg["reset_pending"]:
                groups[g]["reset_pending"] = True
        # install the rebuilt state in one step, then rebuild every group's index under a new epoch
        meta = copy.deepcopy(self._meta)
        meta["receivers"] = receivers
        meta["ctl_seq"] = sync["ctl_seq"]
        meta["rotations"] = {g: POLICY_RE for g in groups if not groups[g].get("reset_pending")}
        meta.pop("escrow_pending", None)
        for name in list(self.vault.names("group:")):
            if name[len("group:"):] not in groups:
                self.vault.delete(name)
        self.vault.put("owner", meta)
        for g, gs in groups.items():
            self.vault.put("group:" + g, gs)
        self._meta.clear()
        self._meta.update(meta)
        self.groups.clear()
        self.groups.update(groups)
        for g in sorted(groups):
            if g in self._meta.get("rotations", {}):
                self._rotate(g, POLICY_RE)
            elif groups[g].get("reset_pending"):
                self._finish_reset(g)
                self.publish(g)
            notes.append(f"{g}: rebuilt with {len(self.groups[g]['docs'])} document(s) at epoch {self.groups[g]['epoch']}")
        return notes

    def _recover_docs(self, g: str, sg: dict, keys: dict, local_docs: dict) -> tuple[dict, int]:
        """Download and check every stored document of a group; ids are found by recomputing handles."""
        docs: dict[str, dict] = {}
        lost = 0
        by_epoch: dict[int, list[bytes]] = {}
        for e, handle in sg["handles"]:
            by_epoch.setdefault(int(e), []).append(handle)
        for e, handles in sorted(by_epoch.items()):
            key = keys.get(str(e))
            if key is None:
                lost += len(handles)
                continue
            k_doc = group_subkeys(key, g, e)[1]
            wanted = set(handles)
            limit = max(len(handles) * 4 + 1000, max([int(i) for i in local_docs] + [0]) + len(handles) + 1000)
            for doc_id in range(1, limit + 1):
                if not wanted:
                    break
                handle = doc_handle(k_doc, doc_id)
                if handle not in wanted:
                    continue
                wanted.discard(handle)
                got = self._cloud().call("owner_doc", self._sync_request("owner_doc", {"g": g, "e": e, "handle": handle}))
                if not signing.check_obj(self.params, self.vk, "doc", [g, e, handle, H(got["blob"])], got["sig"]):
                    raise VerifyError("recovery", f"document {doc_id} of {g} is not signed by this owner")
                plain = wire.dec(aead_decrypt(k_doc, got["blob"], doc_aad(g, e, doc_id), what="document"))
                kws = plain.get("kws") or local_docs.get(str(doc_id), {}).get("kws") \
                    or extract_keywords(plain["title"] + " " + plain["text"])
                docs[str(doc_id)] = {"e": e, "title": plain["title"], "text": plain["text"], "kws": sorted(kws)}
            lost += len(wanted)
        return docs, lost

    # ------------------------------------------------------------------ access change without revocation (design note 003)
    def _live_receiver(self, uid: str) -> dict:
        rec = self.receivers.get(uid)
        if rec is None or rec["revoked"]:
            raise PQSSEError("unknown or revoked receiver")
        return rec

    @_logged("access.grant", lambda o, uid, groups, result=None:
             {"receiver": o.receivers.get(uid, {}).get("name", ""), "uid": uid, "groups": sorted(groups)})
    def grant(self, uid: str, groups: Sequence[str]) -> list[str]:
        """Give an approved receiver more groups (note 003 A). The server widens its scope; the receiver gets a grant
        box with the keys of every live segment of the new groups, sealed to it and bound to its m_u, and signed."""
        rec = self._live_receiver(uid)
        new = sorted(set(groups) - set(rec["groups"]))
        for g in new:
            self._group(g)
        if not new:
            return []
        for g in new:                         # nothing for these groups may be waiting, so the keys are current
            self._settle_group(g)
        body = wire.enc({"groups": {g: {"base": self.groups[g]["base"],
                                        "keys": {str(e): self.groups[g]["keys"][str(e)]
                                                 for e in range(self.groups[g]["base"], self.groups[g]["epoch"] + 1)}}
                                    for g in new}})
        box = seal.seal(self.params, rec["ek"], body, b"grant" + uid.encode("ascii"), psk=rec["m"])
        sig = signing.sign_obj(self.params, self._sk, "grant", [uid, box])
        scope = sorted(set(rec["groups"]) | set(new))

        def effect(d: _Draft) -> None:
            d.meta["receivers"][uid]["groups"] = scope
        self._ctl("scope", change=effect, uid=uid, groups=scope, grant=[box, sig],
                  orecs=[self._orec(uid, {**rec, "groups": scope})])
        return new

    @_logged("access.remove", lambda o, uid, groups, policy="R", result=None:
             {"receiver": o.receivers.get(uid, {}).get("name", ""), "uid": uid, "groups": sorted(groups), "policy": policy})
    def take_away(self, uid: str, groups: Sequence[str], policy: str = POLICY_R) -> list[str]:
        """Remove groups from a receiver that keeps its others (note 003 B): the server narrows the scope at once,
        then each removed group is rotated (policy R or RE) without a rekey box for this receiver."""
        if policy not in (POLICY_R, POLICY_RE):
            raise PQSSEError("policy must be R or RE")
        rec = self._live_receiver(uid)
        gone = sorted(set(groups) & set(rec["groups"]))
        if not gone:
            return []
        scope = sorted(set(rec["groups"]) - set(gone))

        def effect(d: _Draft) -> None:
            d.meta["receivers"][uid]["groups"] = scope
            d.meta.setdefault("rotations", {}).update({g: policy for g in gone if g in self.groups})
        self._ctl("scope", change=effect, uid=uid, groups=scope, orecs=[self._orec(uid, {**rec, "groups": scope})])
        for g in gone:
            if g in self.groups:
                self._rotate(g, policy)
        return gone

    # ------------------------------------------------------------------ export and import (design note 006 A)
    @_logged("export", lambda o, g, dest, passphrase, result=None: {"group": g, "file": str(dest),
                                                                       "count": len(o._group(g)["docs"])})
    def export_group(self, g: str, dest: str | Path, passphrase: str) -> Path:
        """Write the live documents of a group (title, text, keywords; no keys, receivers or index) to one file
        encrypted under a passphrase of 12 or more characters."""
        from ..core.keystore import seal_file
        docs = [{"title": d["title"], "text": d["text"], "keywords": list(d["kws"])}
                for _, d in sorted(self._group(g)["docs"].items(), key=lambda kv: int(kv[0]))]
        return seal_file(dest, GROUP_MAGIC, {"v": 1, "group": g, "docs": docs}, passphrase)

    @_logged("import", lambda o, source, passphrase, g=None, result=None:
             {"file": str(source), "group": result[0] if result else (g or ""), "count": len(result[1]) if result else 0})
    def import_group(self, source: str | Path, passphrase: str, g: str | None = None) -> tuple[str, list[int]]:
        """Read a group export into group ``g`` (default: the exported name), creating it if needed, as ordinary
        update batches (split as large imports are). Publish afterwards. Returns (group, new document ids)."""
        from ..core.keystore import open_file
        data = open_file(source, GROUP_MAGIC, passphrase, "group export")
        if not isinstance(data, dict) or data.get("v") != 1:
            raise PQSSEError("unsupported group export version")
        g = (g or data["group"]).strip()
        if g not in self.groups:
            self.create_group(g)
        docs = [DocInput(d["title"], d["text"], d["keywords"]) for d in data["docs"]]
        return g, self.build_index(g, docs) if docs else []

    # ------------------------------------------------------------------ Revoke
    @_logged("revoke", lambda o, uid, policy="R", result=None:
             {"receiver": o.receivers.get(uid, {}).get("name", ""), "uid": uid, "policy": policy, "groups": result or []})
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
        targets = [g for g in rec["groups"] if g in self.groups]

        def effect(d: _Draft) -> None:          # the rotations still to do are remembered with the deauth
            d.meta["receivers"][uid]["revoked"] = True
            d.meta.setdefault("rotations", {}).update({g: policy for g in targets})
        self._ctl("deauth", change=effect, uid=uid)
        rotated = []
        for g in targets:
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
        def effect(d: _Draft) -> None:
            ds = d.group(g)
            ds["epoch"] = new
            ds["keys"][str(new)] = new_key
            ds["kw"][str(new)] = {}
            d.meta.get("rotations", {}).pop(g, None)
            if reset:
                ds["reset_pending"] = True  # the server now expects the reset batch; remembered across a failure
        self._ctl("epoch", change=effect, g=g, e=new, reset=reset, boxes=boxes, okeys=[self._okey(g, new, new_key)])
        if reset:
            self._finish_reset(g)
        self.publish(g)

    def _finish_reset(self, g: str) -> None:
        """Send the policy RE rebuild of a group. If it fails (no network, a full disk at the server), the group stays
        marked and the next change to it, or resume_pending(), sends the rebuild first. Same messages, no protocol change."""
        gs = self._group(g)
        if gs.get("reset_pending"):
            live = [DocInput(d["title"], d["text"], d["kws"], int(i))
                    for i, d in sorted(gs["docs"].items(), key=lambda kv: int(kv[0]))]
            chunks = _chunks(live) or [[]]
            first_ids = {str(d.doc_id) for d in chunks[0]}
            rest = {i: d for i, d in gs["docs"].items() if i not in first_ids}
            self._apply(g, chunks[0], [], reset=True, rest=rest)    # its commit clears reset_pending
        while self._group(g).get("rebuild_rest"):                 # the rest, batch by batch, resumable
            left = self._group(g)["rebuild_rest"]
            todo = [DocInput(d["title"], d["text"], d["kws"], int(i)) for i, d in sorted(left.items(), key=lambda kv: int(kv[0]))]
            self._apply(g, _chunks(todo)[0], [], kind="reencrypt", rebuilding=True)

    @_logged("recovery", lambda o, result=None: {"done": result or []}, skip_empty=True)
    def resume_pending(self) -> list[str]:
        """After a crash or a lost connection: settle the journal, then finish interrupted revocations (rotations
        and RE rebuilds) and publish them. Returns a line per thing finished; empty when nothing was pending."""
        done = []
        for channel in ["ctl"] + ["group:" + g for g in sorted(self.groups)]:
            outcome = self._settle(channel)
            if outcome:
                done.append(f"{channel}: last message {outcome}")
        if self._meta.get("escrow_pending") and self.cloud_pub is not None:
            self.escrow_all()
            done.append("recovery keys stored at the server")
        for g in sorted(self.groups):
            policy = self._meta.get("rotations", {}).get(g)
            if policy:
                self._rotate(g, policy)
                done.append(f"{g}: rotation finished")
            elif self.groups[g].get("reset_pending") or self.groups[g].get("rebuild_rest"):
                self._finish_reset(g)
                self.publish(g)
                done.append(f"{g}: rebuild finished")
        return done

    # ------------------------------------------------------------------ activity log (design note 007)
    def log_event(self, what: str, detail: dict, server: str = "accepted") -> int:
        """Append one entry to the hash-chained activity log in the vault. Returns its number."""
        head = self.vault.get(LOG_HEAD) or {"n": 0, "h": b""}
        entry = {"n": head["n"] + 1, "t": int(self.clock() * 1000), "what": what, "detail": _plain(detail),
                 "server": server, "prev": head["h"]}
        self.vault.put(f"{LOG_PREFIX}{entry['n']:012d}", entry)
        self.vault.put(LOG_HEAD, {"n": entry["n"], "h": H(wire.enc(entry))})
        return entry["n"]

    def activity(self, limit: int = 200, group: str | None = None, receiver: str | None = None) -> list[dict]:
        """Newest first, optionally only entries about one group or one receiver (name or id)."""
        out = []
        for name in sorted(self.vault.names(LOG_PREFIX), reverse=True):
            entry = self.vault.get(name)
            d = entry["detail"]
            if group and d.get("group") != group and group not in d.get("groups", []):
                continue
            if receiver and receiver not in (d.get("receiver"), d.get("uid"), d.get("name")):
                continue
            out.append(entry)
            if len(out) >= limit:
                break
        return out

    def verify_activity(self) -> tuple[bool, str]:
        """Check the chain: every entry present, in order, linked to the one before, ending at the stored head."""
        head = self.vault.get(LOG_HEAD) or {"n": 0, "h": b""}
        names = sorted(self.vault.names(LOG_PREFIX))
        if len(names) != head["n"]:
            return False, f"{head['n']} entries expected, {len(names)} found"
        prev = b""
        for i, name in enumerate(names, start=1):
            entry = self.vault.get(name)
            if entry["n"] != i or name != f"{LOG_PREFIX}{i:012d}":
                return False, f"entry {i} is missing or out of place"
            if entry["prev"] != prev:
                return False, f"entry {i} does not follow entry {i - 1}"
            prev = H(wire.enc(entry))
        if prev != head["h"]:
            return False, "the last entry does not match the stored head"
        return True, f"{head['n']} entries, chain intact"

    def export_activity_csv(self, dest: str | Path) -> Path:
        """Write the log to CSV (plain text: it holds titles and names, so the app warns before this)."""
        dest = Path(dest)
        with open(dest, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["n", "time_utc", "what", "server", "detail"])
            for entry in reversed(self.activity(limit=10**9)):
                when = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(entry["t"] / 1000))
                detail = "; ".join(f"{k}={v}" for k, v in sorted(entry["detail"].items()))
                writer.writerow([entry["n"], when, entry["what"], entry["server"], detail])
        return dest

    @property
    def has_pending(self) -> bool:
        return (any(True for _ in self.vault.names(JOURNAL)) or bool(self._meta.get("rotations"))
                or bool(self._meta.get("escrow_pending") and self.cloud_pub is not None)
                or any(gs.get("reset_pending") or gs.get("rebuild_rest") for gs in self.groups.values()))

    # ------------------------------------------------------------------ reference (tests, UI)
    def plaintext_search(self, g: str, keyword: str) -> set[int]:
        """Plaintext reference result: ids of live documents containing the keyword."""
        return {int(i) for i, d in self._group(g)["docs"].items() if keyword in d["kws"]}


JOURNAL = "journal:"
LOG_PREFIX = "log:"
LOG_HEAD = "loghead"


def _plain(value: Any) -> Any:
    """Detail values the wire encoding accepts (no floats, no None): numbers, text, bytes, lists, dicts."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, str, bytes)):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(v) for v in value]
    return str(value)
GROUP_MAGIC = b"PQSSE-GROUP-EXPORT-1\n"


def _doc_size(doc: DocInput) -> int:
    """A generous estimate of a document's share of a batch: ciphertext, signature, handle and index entries."""
    words = len(doc.keywords) if doc.keywords is not None else len(set(doc.text.split())) + len(doc.title.split())
    return len(doc.title.encode()) + len(doc.text.encode()) + 5_000 + 64 * words


def _chunks(docs: list[DocInput]) -> list[list[DocInput]]:
    """Split documents into batches of at most BATCH_DOCS documents and about BATCH_BYTES bytes (one large
    document still gets a batch of its own; the server's own limit then decides)."""
    out: list[list[DocInput]] = []
    current: list[DocInput] = []
    size = 0
    for doc in docs:
        cost = _doc_size(doc)
        if current and (len(current) >= BATCH_DOCS or size + cost > BATCH_BYTES):
            out.append(current)
            current, size = [], 0
        current.append(doc)
        size += cost
    if current:
        out.append(current)
    return out


class _Draft:
    """Copies of the owner's records that a signed message will change, edited before it is sent."""

    def __init__(self, owner: "Owner") -> None:
        self._owner = owner
        self._meta: dict | None = None
        self._groups: dict[str, dict] = {}

    @property
    def meta(self) -> dict:
        if self._meta is None:
            self._meta = copy.deepcopy(self._owner._meta)
        return self._meta

    def group(self, g: str) -> dict:
        if g not in self._groups:
            self._groups[g] = copy.deepcopy(self._owner.groups[g])
        return self._groups[g]

    def new_group(self, g: str, value: dict) -> None:
        self._groups[g] = value

    def records(self) -> dict:
        out = {} if self._meta is None else {"owner": self._meta}
        out.update({"group:" + g: v for g, v in self._groups.items()})
        return out


def new_owner_id() -> str:
    """Random label for throwaway owners (benchmarks, Attack Lab)."""
    return "owner-" + os.urandom(3).hex()
