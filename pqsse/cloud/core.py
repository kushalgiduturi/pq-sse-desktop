"""The cloud server logic (untrusted party).

The cloud stores encrypted index segments, encrypted documents, signed states,
per receiver credentials a_u and mailbox items (join requests, sealed capabilities,
rekey boxes). It holds its own ML-KEM and ML-DSA key pairs. It never holds a group key,
an index key or a document key.

Algorithms implemented here: the cloud side of Setup, Join, Update, Publish, Search and
Revoke. Every request enters through ``handle(endpoint, body)`` with a wire encoded body,
both in process and over HTTP, so the two transports behave identically.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Callable

from .. import pqbackend
from ..core import seal, signing, wire
from ..core.errors import Rejected, VerifyError, WireError
from ..core.index import ADDR_LEN, VAL_LEN, token_aad, token_key
from ..core.pairing import PublicIdentity
from ..core.prims import H, aead_decrypt
from ..pqbackend import DEFAULT_PARAMS, Params

TOKEN_WINDOW = 300.0

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v BLOB);
CREATE TABLE IF NOT EXISTS groups (g TEXT PRIMARY KEY, cur INTEGER, base INTEGER, seq INTEGER, reset_pending INTEGER);
CREATE TABLE IF NOT EXISTS entries (g TEXT, e INTEGER, addr BLOB, val BLOB, PRIMARY KEY (g, e, addr)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS docs (g TEXT, e INTEGER, handle BLOB, blob BLOB, sig BLOB, PRIMARY KEY (g, e, handle));
CREATE TABLE IF NOT EXISTS states (g TEXT, e INTEGER, ver INTEGER, final INTEGER, hdr BLOB, ct BLOB, sig BLOB, PRIMARY KEY (g, e));
CREATE TABLE IF NOT EXISTS creds (uid TEXT PRIMARY KEY, enc_a BLOB, scope TEXT, revoked INTEGER);
CREATE TABLE IF NOT EXISTS mail (id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT, kind TEXT, body BLOB, sig BLOB);
CREATE TABLE IF NOT EXISTS joins (uid TEXT PRIMARY KEY, req BLOB, sig BLOB);
CREATE TABLE IF NOT EXISTS log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, endpoint TEXT, in_bytes INTEGER, out_bytes INTEGER, ok INTEGER, reason TEXT);
"""


class CloudCore:
    """Server state and request handlers."""

    def __init__(self, vault: Any, params: Params = DEFAULT_PARAMS, name: str = "cloud",
                 clock: Callable[[], float] = time.time, keep_log: bool = True) -> None:
        self.vault = vault
        self.clock = clock
        self.keep_log = keep_log
        self._lock = threading.RLock()
        self.db: sqlite3.Connection = getattr(vault, "db", None) or sqlite3.connect(":memory:", check_same_thread=False)
        self.db.execute("PRAGMA secure_delete = ON")
        self.db.executescript(_SCHEMA)
        self.trace_tokens: list[bytes] | None = None  # test hook: addresses seen in tokens
        ident = vault.get("identity")
        if ident is None:
            ident = self._setup(params, name)
        self.params = Params(ident["kem"], ident["sig"])
        self.name = ident["name"]
        self.ek, self._dk = ident["ek"], ident["dk"]
        self.vk, self._sk = ident["vk"], ident["sk"]

    # ------------------------------------------------------------------ Setup
    def _setup(self, params: Params, name: str) -> dict:
        """Algorithm 1 Setup (cloud part): ML-KEM key pair and ML-DSA key pair."""
        ek, dk = pqbackend.kem_keygen(params.kem)
        vk, sk = pqbackend.sig_keygen(params.sig)
        ident = {"name": name, "kem": params.kem, "sig": params.sig, "ek": ek, "dk": dk, "vk": vk, "sk": sk}
        self.vault.put("identity", ident)
        return ident

    def public_identity(self) -> PublicIdentity:
        return PublicIdentity("cloud", self.name, self.params, self.vk, self.ek)

    def owner_identity(self) -> PublicIdentity | None:
        raw = self._meta_get("owner_pub")
        return None if raw is None else PublicIdentity.from_wire(wire.dec(raw))

    def pair_owner(self, ident: PublicIdentity, replace: bool = False) -> None:
        """Pair devices: install the owner's authentic verification key."""
        if ident.role != "owner":
            raise Rejected("pairing", "not an owner key file")
        if ident.params != self.params:
            raise Rejected("pairing", "parameter set mismatch")
        current = self.owner_identity()
        if current is not None and current.vk != ident.vk and not replace:
            raise Rejected("pairing", "a different owner is already paired")
        self._meta_put("owner_pub", wire.enc(ident.to_wire()))

    # ------------------------------------------------------------- small helpers
    def _meta_get(self, key: str) -> bytes | None:
        row = self.db.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
        return None if row is None else row[0]

    def _meta_put(self, key: str, value: bytes) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))
        self.db.commit()

    def _owner_vk(self) -> bytes:
        ident = self.owner_identity()
        if ident is None:
            raise Rejected("not_paired", "no owner key installed")
        return ident.vk

    def _group(self, g: str) -> tuple[int, int, int, int]:
        row = self.db.execute("SELECT cur, base, seq, reset_pending FROM groups WHERE g=?", (g,)).fetchone()
        if row is None:
            raise Rejected("unknown_group", g)
        return row

    def _owner_signed(self, obj: dict, label: str) -> dict:
        """Check the owner's signature on obj["msg"] and return the decoded message."""
        msg, sig = obj["msg"], obj["sig"]
        if not signing.check_bytes(self.params, self._owner_vk(), label, msg, sig):
            raise Rejected("bad_signature", f"owner {label} signature invalid")
        return wire.dec(msg)

    # ------------------------------------------------------------------ dispatch
    def handle(self, endpoint: str, body: bytes) -> bytes:
        """Single entry point. Returns the wire encoded reply or raises Rejected."""
        with self._lock:
            handler = getattr(self, "_h_" + endpoint, None)
            try:
                if handler is None:
                    raise Rejected("unknown_endpoint", endpoint)
                try:
                    reply = wire.enc(handler(wire.dec(body)))
                except (WireError, KeyError, TypeError, IndexError, ValueError) as exc:
                    raise Rejected("malformed", type(exc).__name__) from exc
            except Rejected as exc:
                self.db.rollback()
                self._log(endpoint, len(body), 0, False, exc.reason)
                raise
            self._log(endpoint, len(body), len(reply), True, "")
            return reply

    def _log(self, endpoint: str, in_bytes: int, out_bytes: int, ok: bool, reason: str) -> None:
        if not self.keep_log or endpoint.startswith("admin_"):
            return
        self.db.execute("INSERT INTO log (ts, endpoint, in_bytes, out_bytes, ok, reason) VALUES (?,?,?,?,?,?)",
                        (self.clock(), endpoint, in_bytes, out_bytes, int(ok), reason))
        self.db.commit()

    # ------------------------------------------------------------------ public info
    def _h_pub(self, obj: Any) -> dict:
        return self.public_identity().to_wire()

    def _h_info(self, obj: Any) -> dict:
        owner = self.owner_identity()
        return {"paired": owner is not None, "backend": pqbackend.backend_name(),
                "kem": self.params.kem, "sig": self.params.sig,
                "owner_fp": owner.fingerprint() if owner else ""}

    # ------------------------------------------------------------------ Join (mailbox)
    def _h_join_post(self, obj: dict) -> dict:
        """Join: store a receiver's join request for the owner. Content is public."""
        req = wire.dec(obj["req"])
        uid = H(req["ek"], req["vk"])[:16].hex()
        self.db.execute("INSERT OR REPLACE INTO joins VALUES (?, ?, ?)", (uid, obj["req"], obj["sig"]))
        self.db.commit()
        return {"uid": uid}

    def _h_join_list(self, obj: Any) -> list:
        rows = self.db.execute("SELECT uid, req, sig FROM joins ORDER BY uid").fetchall()
        return [{"uid": uid, "req": req, "sig": sig} for uid, req, sig in rows]

    def _h_mail_get(self, obj: dict) -> list:
        """Return sealed mailbox items (capability, rekey boxes) for a receiver."""
        rows = self.db.execute("SELECT id, kind, body, sig FROM mail WHERE uid=? ORDER BY id", (obj["uid"],)).fetchall()
        return [{"id": i, "kind": kind, "body": body, "sig": sig} for i, kind, body, sig in rows]

    # ------------------------------------------------------------------ owner control
    def _h_ctl(self, obj: dict) -> dict:
        """Owner signed, sequence numbered control messages (Join, Revoke, group setup)."""
        msg = self._owner_signed(obj, "ctl")
        last = int(self._meta_get("ctl_seq") or b"0")
        if msg["seq"] != last + 1:
            raise Rejected("bad_sequence", f"expected control seq {last + 1}")
        op = msg["op"]
        if op == "group":
            self._ctl_group(msg)
        elif op == "cred":
            self._ctl_cred(msg)
        elif op == "deauth":
            self._ctl_deauth(msg)
        elif op == "epoch":
            self._ctl_epoch(msg)
        else:
            raise Rejected("malformed", "unknown control op")
        self.db.execute("INSERT OR REPLACE INTO meta VALUES ('ctl_seq', ?)", (str(msg["seq"]).encode(),))
        self.db.commit()
        return {"ok": True}

    def _ctl_group(self, msg: dict) -> None:
        if self.db.execute("SELECT 1 FROM groups WHERE g=?", (msg["g"],)).fetchone():
            raise Rejected("group_exists", msg["g"])
        self.db.execute("INSERT INTO groups VALUES (?, 1, 1, 0, 0)", (msg["g"],))

    def _ctl_cred(self, msg: dict) -> None:
        """Join: install the credential a_u and scope, queue the sealed capability."""
        uid = msg["uid"]
        try:
            cred = wire.dec(seal.unseal(self.params, self._dk, msg["box"], b"cred" + uid.encode("ascii")))
        except VerifyError as exc:
            raise Rejected("bad_credential", "cannot open credential box") from exc
        enc_a = self.vault.encrypt("cred:" + uid, cred["a"])
        self.db.execute("INSERT OR REPLACE INTO creds VALUES (?, ?, ?, 0)", (uid, enc_a, json.dumps(sorted(cred["groups"]))))
        self.db.execute("DELETE FROM mail WHERE uid=?", (uid,))
        self.db.execute("INSERT INTO mail (uid, kind, body, sig) VALUES (?, 'cap', ?, ?)", (uid, msg["cap"], msg["cap_sig"]))
        self.db.execute("DELETE FROM joins WHERE uid=?", (uid,))

    def _ctl_deauth(self, msg: dict) -> None:
        """Revoke: deauthorize a receiver. Its credential stops working at once."""
        self.db.execute("UPDATE creds SET revoked=1 WHERE uid=?", (msg["uid"],))
        self.db.execute("DELETE FROM mail WHERE uid=?", (msg["uid"],))
        self.db.execute("DELETE FROM joins WHERE uid=?", (msg["uid"],))

    def _ctl_epoch(self, msg: dict) -> None:
        """Revoke: advance a group to a new epoch and queue the rekey boxes."""
        g, new = msg["g"], msg["e"]
        cur, _base, _seq, _pending = self._group(g)
        if new != cur + 1:
            raise Rejected("bad_epoch", f"expected epoch {cur + 1}")
        row = self.db.execute("SELECT final FROM states WHERE g=? AND e=?", (g, cur)).fetchone()
        if row is None or not row[0]:
            raise Rejected("not_final", "old epoch has no final state")
        self.db.execute("UPDATE groups SET cur=?, reset_pending=? WHERE g=?", (new, int(bool(msg["reset"])), g))
        for uid, pair in msg["boxes"].items():
            self.db.execute("INSERT INTO mail (uid, kind, body, sig) VALUES (?, 'rekey', ?, ?)", (uid, pair[0], pair[1]))

    # ------------------------------------------------------------------ Update
    def _h_update(self, obj: dict) -> dict:
        """Algorithm 4 Update (cloud part): accept only signed, in order batches."""
        batch = self._owner_signed(obj, "batch")
        g = batch["g"]
        cur, base, seq, pending = self._group(g)
        if batch["e"] != cur:
            raise Rejected("bad_epoch", "batch is not for the current epoch")
        if batch["seq"] != seq + 1:
            raise Rejected("bad_sequence", f"expected seq {seq + 1}, got {batch['seq']}")
        if bool(batch["reset"]) != bool(pending):
            raise Rejected("bad_reset", "reset flag does not match the epoch change")
        addrs, vals = batch["addrs"], batch["vals"]
        n = len(addrs) // ADDR_LEN
        if len(addrs) != n * ADDR_LEN or len(vals) != n * VAL_LEN:
            raise Rejected("malformed", "entry arrays have inconsistent lengths")
        if batch["reset"]:
            # Policy RE: drop every older segment and its documents.
            self.db.execute("DELETE FROM entries WHERE g=? AND e<?", (g, cur))
            self.db.execute("DELETE FROM docs WHERE g=? AND e<?", (g, cur))
            self.db.execute("DELETE FROM states WHERE g=? AND e<?", (g, cur))
            base = cur
        rows = [(g, cur, addrs[i * ADDR_LEN:(i + 1) * ADDR_LEN], vals[i * VAL_LEN:(i + 1) * VAL_LEN]) for i in range(n)]
        try:
            self.db.executemany("INSERT INTO entries VALUES (?, ?, ?, ?)", rows)
        except sqlite3.IntegrityError as exc:
            raise Rejected("duplicate_address", "address already stored") from exc
        for handle, blob, sig in batch["docs"]:
            self.db.execute("INSERT OR REPLACE INTO docs VALUES (?, ?, ?, ?, ?)", (g, cur, handle, blob, sig))
        for epoch, handle in batch["del"]:
            self.db.execute("DELETE FROM docs WHERE g=? AND e=? AND handle=?", (g, epoch, handle))
        self.db.execute("UPDATE groups SET seq=?, base=?, reset_pending=0 WHERE g=?", (batch["seq"], base, g))
        self.db.commit()
        return {"ok": True, "seq": batch["seq"]}

    # ------------------------------------------------------------------ Publish
    def _h_state_put(self, obj: dict) -> dict:
        """Algorithm 5 Publish (cloud part): store a signed state, newest version wins."""
        hdr_raw, ct, sig = obj["hdr"], obj["ct"], obj["sig"]
        if not signing.check_bytes(self.params, self._owner_vk(), "state", hdr_raw + H(ct), sig):
            raise Rejected("bad_signature", "owner state signature invalid")
        hdr = wire.dec(hdr_raw)
        g, e = hdr["g"], hdr["e"]
        cur, _base, _seq, _pending = self._group(g)
        if e > cur:
            raise Rejected("bad_epoch", "state is for a future epoch")
        row = self.db.execute("SELECT ver, final FROM states WHERE g=? AND e=?", (g, e)).fetchone()
        if row is not None and (hdr["ver"] <= row[0] or row[1]):
            raise Rejected("stale_state", "version not newer or segment already final")
        self.db.execute("INSERT OR REPLACE INTO states VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (g, e, hdr["ver"], int(bool(hdr["final"])), hdr_raw, ct, sig))
        self.db.commit()
        return {"ok": True}

    # ------------------------------------------------------------------ receiver requests
    def _open_request(self, endpoint: str, obj: dict) -> tuple[str, list[str], dict]:
        """Authenticate a receiver request: it must decrypt under the credential a_u."""
        uid = obj["uid"]
        row = self.db.execute("SELECT enc_a, scope, revoked FROM creds WHERE uid=?", (uid,)).fetchone()
        if row is None:
            raise Rejected("unknown_user", "no credential for this receiver")
        if row[2]:
            raise Rejected("revoked", "this receiver has been revoked")
        a_u = self.vault.decrypt("cred:" + uid, row[0])
        try:
            req = wire.dec(aead_decrypt(token_key(a_u), obj["ct"], token_aad(uid, endpoint)))
        except VerifyError as exc:
            raise Rejected("bad_token", "request does not authenticate under the credential") from exc
        if abs(self.clock() - req["ts"] / 1000.0) > TOKEN_WINDOW:
            raise Rejected("stale_token", "request timestamp outside the window")
        return uid, json.loads(row[1]), req

    def _scoped_group(self, scope: list[str], g: str) -> tuple[int, int]:
        if g not in scope:
            raise Rejected("scope", "group is outside this receiver's capability")
        cur, base, _seq, _pending = self._group(g)
        return cur, base

    def _h_states_get(self, obj: dict) -> dict:
        """Return the signed, encrypted states of all live segments of a group."""
        _uid, scope, req = self._open_request("states_get", obj)
        cur, base = self._scoped_group(scope, req["g"])
        return self.read_states(req["g"], cur, base)

    def read_states(self, g: str, cur: int, base: int) -> dict:
        rows = self.db.execute("SELECT hdr, ct, sig FROM states WHERE g=? AND e>=? AND e<=? ORDER BY e", (g, base, cur)).fetchall()
        return {"cur": cur, "base": base, "states": [{"hdr": h, "ct": c, "sig": s} for h, c, s in rows]}

    def _h_search(self, obj: dict) -> dict:
        """Algorithm 7 Search: check credential, scope and epoch, return entries, sign."""
        _uid, scope, req = self._open_request("search", obj)
        g = req["g"]
        cur, base = self._scoped_group(scope, g)
        if req["cur"] != cur:
            raise Rejected("stale_epoch", "token is not for the current epoch")
        segs = []
        for epoch, addrs in req["segs"]:
            if not base <= epoch <= cur:
                raise Rejected("bad_segment", "segment is not live")
            found_a, found_v = bytearray(), bytearray()
            for i in range(0, len(addrs), ADDR_LEN):
                addr = addrs[i:i + ADDR_LEN]
                if self.trace_tokens is not None:
                    self.trace_tokens.append(addr)
                row = self.db.execute("SELECT val FROM entries WHERE g=? AND e=? AND addr=?", (g, epoch, addr)).fetchone()
                if row is not None:
                    found_a += addr
                    found_v += row[0]
            segs.append([epoch, bytes(found_a), bytes(found_v)])
        body = wire.enc({"g": g, "segs": segs})
        return self.sign_response(obj["ct"], body)

    def sign_response(self, request_ct: bytes, body: bytes) -> dict:
        """ML-DSA signature of the cloud over (H(token), response body)."""
        sig = signing.sign_bytes(self.params, self._sk, "resp", H(request_ct) + body)
        return {"body": body, "sig": sig}

    def _h_doc_get(self, obj: dict) -> dict:
        """Return one encrypted document with the owner's signature."""
        _uid, scope, req = self._open_request("doc_get", obj)
        cur, base = self._scoped_group(scope, req["g"])
        if not base <= req["e"] <= cur:
            raise Rejected("bad_segment", "segment is not live")
        row = self.db.execute("SELECT blob, sig FROM docs WHERE g=? AND e=? AND handle=?", (req["g"], req["e"], req["handle"])).fetchone()
        if row is None:
            raise Rejected("no_such_doc", "document not stored")
        return {"blob": row[0], "sig": row[1]}

    # ------------------------------------------------------------------ operator view
    def _h_admin_log(self, obj: dict) -> list:
        rows = self.db.execute("SELECT id, ts, endpoint, in_bytes, out_bytes, ok, reason FROM log WHERE id>? ORDER BY id LIMIT 500",
                               (obj.get("since", 0),)).fetchall()
        return [list(r) for r in rows]

    def _h_admin_stats(self, obj: Any) -> dict:
        def one(sql: str) -> int:
            return int(self.db.execute(sql).fetchone()[0] or 0)
        groups = self.db.execute("SELECT g, cur, base, seq FROM groups ORDER BY g").fetchall()
        return {
            "entries": one("SELECT COUNT(*) FROM entries"),
            "docs": one("SELECT COUNT(*) FROM docs"),
            "doc_bytes": one("SELECT SUM(LENGTH(blob)) FROM docs"),
            "states": one("SELECT COUNT(*) FROM states"),
            "state_bytes": one("SELECT SUM(LENGTH(ct)) FROM states"),
            "receivers": one("SELECT COUNT(*) FROM creds WHERE revoked=0"),
            "revoked": one("SELECT COUNT(*) FROM creds WHERE revoked=1"),
            "mail": one("SELECT COUNT(*) FROM mail"),
            "requests": one("SELECT COUNT(*) FROM log"),
            "rejected": one("SELECT COUNT(*) FROM log WHERE ok=0"),
            "groups": [{"g": g, "cur": c, "base": b, "seq": s} for g, c, b, s in groups],
        }

    def _h_admin_peek(self, obj: Any) -> dict:
        """What the server can see: raw samples of every table, hex encoded."""
        entries = self.db.execute("SELECT g, e, addr, val FROM entries LIMIT 12").fetchall()
        docs = self.db.execute("SELECT g, e, handle, blob FROM docs LIMIT 6").fetchall()
        states = self.db.execute("SELECT g, e, ver, final, ct FROM states ORDER BY g, e LIMIT 6").fetchall()
        creds = self.db.execute("SELECT uid, scope, revoked, enc_a FROM creds LIMIT 6").fetchall()
        return {
            "entries": [[g, e, a.hex(), v.hex()] for g, e, a, v in entries],
            "docs": [[g, e, h.hex(), b[:48].hex(), len(b)] for g, e, h, b in docs],
            "states": [[g, e, ver, final, ct[:48].hex(), len(ct)] for g, e, ver, final, ct in states],
            "creds": [[uid, scope, revoked, a[:24].hex()] for uid, scope, revoked, a in creds],
        }

    def _h_admin_pair_owner(self, obj: dict) -> dict:
        self.pair_owner(PublicIdentity.from_wire(obj["ident"]), replace=bool(obj.get("replace")))
        return {"ok": True}
