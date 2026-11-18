# Wire formats

## Canonical encoding (`pqsse.core.wire`)

Every message, every signature input and every stored record uses one encoding.
The decoder rejects anything non-canonical, so `enc(dec(b)) == b`.

| Tag | Type | Body |
| --- | --- | --- |
| 0 | None | empty |
| 1 | False | empty |
| 2 | True | empty |
| 3 | int (0 to 2^64 - 1) | 8 bytes big endian |
| 4 | bytes | u32 length, bytes |
| 5 | str | u32 length, UTF-8 |
| 6 | list | u32 count, items |
| 7 | dict (str keys) | u32 count, then for each key in sorted order: u32 length, UTF-8 key, value |

Helpers used inside PRF inputs: `u32(i)` = 4 bytes big endian, `sstr(w)` = `u32(len) || UTF-8(w)`.

## Symmetric layouts

| Object | Layout |
| --- | --- |
| PRF input | `sstr(w) || u32(i) || selector` with selector 0x00 (address) or 0x01 (mask) |
| Address `a_i` | `HMAC-SHA3-256(K_idx, sstr(w) || u32(i) || 0x00)`, 32 bytes |
| Value `v_i` | `(op || u32(id)) XOR HMAC-SHA3-256(K_idx, sstr(w) || u32(i) || 0x01)[0:5]`, op 1 = add, 2 = delete |
| Chain | `d_i = SHA3-256(d_{i-1} || a_i || v_i)`, `d_{-1}` = 32 zero bytes |
| Subkeys | `HKDF-SHA3-256(K_g^e, "pqsse/v3/" + label + sstr(g) + u32(e))`, label in idx, doc, st |
| Document | `nonce(12) || AES-256-GCM(K_doc, enc({title, text}), aad = sstr(g) || u32(e) || u32(id))` |
| Document handle | `HMAC-SHA3-256(K_doc, "handle" || u32(id))[0:16]` |
| State plaintext | `u32(count) || count * (H(sstr(w))[0:8] || u32(c_w) || d_w)`, zero padded to `N_max` records of 44 bytes |
| Token key | `HKDF-SHA3-256(a_u, "pqsse/v3/token")`, AAD of a request = `uid || "/" || endpoint` |
| Sealed box | `enc({k: ML-KEM ciphertext, c: nonce || AES-GCM})`, key = `HKDF(ss, salt = psk, info = "pqsse/v3/seal" || H(k))` |
| Signature input | `"pqsse/v3/sig/" || label || 0x00 || SHA3-256(payload)` |

## Messages

`Sig_O` = owner ML-DSA, `Sig_C` = cloud ML-DSA, `Sig_u` = receiver ML-DSA.
`E_a(x)` = AES-GCM under the token key of `a_u`.

| Algorithm | Endpoint | Request | Reply |
| --- | --- | --- | --- |
| Setup | `pub` | none | cloud public identity |
| Setup (pair) | `admin_pair_owner` | `{ident, replace}` | `{ok}` |
| Join | `join_post` | `{req: enc({name, kem, sig, ek, vk, nonce, ts}), sig: Sig_u("join", req)}` | `{uid}` |
| Join | `join_list` | none | list of `{uid, req, sig}` |
| Join | `ctl` op `cred` | `{msg: Seal(ek_C, enc({seq, op, uid, box, cap, cap_sig}), aad = "ctl"), sig: Sig_O("ctl", msg)}` where `box = Seal(ek_C, {a, groups})`, `cap = Seal(ek_u, {uid, a, m, groups: {g: {base, keys}}})`, `cap_sig = Sig_O("cap", [uid, cap])` | `{ok}` |
| Join, Revoke | `mail_get` | `{uid}` | list of `{id, kind: cap or rekey, body, sig}` |
| group setup | `ctl` op `group` | `{seq, op, g}` sealed and signed as above | `{ok}` |
| BuildIndex, Update | `update` | `{msg: enc({g, e, seq, addrs: n*32 bytes, vals: n*5 bytes, docs: [[handle, blob, Sig_O("doc", [g, e, handle, H(blob)])]], del: [[e, handle]], reset}), sig: Sig_O("batch", msg)}` | `{ok, seq}` |
| Publish | `state_put` | `{hdr: enc({g, e, ver, exp, final, base}), ct, sig: Sig_O("state", hdr || H(ct))}` | `{ok}` |
| TokenGen | `states_get` | `{uid, ct: E_a({g, ts, nonce})}` | `{cur, base, states: [{hdr, ct, sig}]}` |
| TokenGen, Search | `search` | `{uid, ct: E_a({g, cur, segs: [[e, addresses]], ts, nonce})}` | `{ct: rho, sig: Sig_C("resp", H(request ct) || H(rho))}` with `rho = AES-GCM(token key of a_u, enc({g, segs: [[e, addresses, values]]}), aad = uid || "/search-response")` |
| Decrypt | `doc_get` | `{uid, ct: E_a({g, e, handle, ts, nonce})}` | `{blob, sig}` |
| Revoke | `ctl` op `deauth` | `{seq, op, uid}` sealed and signed; the cloud erases the wrapped `a_u` | `{ok}` |
| Revoke | `ctl` op `epoch` | `{seq, op, g, e, reset, boxes: {uid: [box, Sig_O("rekey", [uid, box])]}}` with `box = Seal(ek_v, {g, e, key, base, reset}, psk = m_v)` | `{ok}` |

## Rejection reasons of the cloud

HTTP 403 with `enc({reason, detail})`.

| Reason | Meaning |
| --- | --- |
| `bad_signature` | owner signature on a batch, state or control message is invalid |
| `bad_control` | a control message does not open under the cloud's ML-KEM key |
| `bad_sequence` | batch or control message is replayed or out of order |
| `bad_epoch`, `bad_reset`, `not_final` | wrong epoch, reset flag mismatch, epoch change without a final state |
| `stale_state` | state version not newer, or the segment is already final |
| `unknown_user`, `revoked` | no credential for this receiver, or it was revoked |
| `bad_token`, `stale_token` | request does not authenticate under `a_u`, or its timestamp is outside the window |
| `scope` | group outside the receiver's capability |
| `stale_epoch`, `bad_segment` | token for an old epoch, or a segment that is no longer live |
| `no_such_doc`, `unknown_group`, `duplicate_address`, `malformed` | as named |
| `admin_only`, `not_local` | operator endpoint without the admin token, non-loopback client |
