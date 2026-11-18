# Design note 001: confidential search responses and control messages, revoked credentials

Status: approved 2026-11-18 ("Accept all" on the recommendations in `docs/PAPER_CONFORMANCE.md`,
items P-01, P-02, P-06). Implemented on branch `reallife`.

## Why

The conformance review found three places where the code is weaker than the paper:

- P-01: the server's search response travelled in clear text (only signed). The paper encrypts it
  under the receiver's credential (Algorithm 7, step 5).
- P-02: control messages from the data owner to the server were signed but not encrypted. The paper
  seals them to the server's ML-KEM key (Section II-A, `Ctl`).
- P-06: a revoked receiver's credential stayed stored at the server (wrapped). The paper deletes it
  (Algorithm 10, step 1).

## Changes

### Search response (P-01)

Before: `{body: enc({g, segs}), sig: Sig_C("resp", H(token) || body)}`.

After: `{ct, sig}` with

    ct  = AES-256-GCM(K_tok(a_u), enc({g, segs}), aad = uid || "/" || "search-response")
    sig = Sig_C("resp", H(token) || H(ct))

`K_tok(a_u) = HKDF-SHA3-256(a_u, "pqsse/v3/token")` is the key that already protects the receiver's
requests. The receiver checks the signature first, then decrypts; a response that does not decrypt is
rejected under the check "response signature". This is the paper's `rho = AE.Enc(a_u, R; res||u)`,
`sigma_R = Sign(sskCS, resp || H(T) || H(rho))`, with the key derived from `a_u` as for tokens.

### Control messages (P-02)

Before: `{msg: enc({seq, op, ...}), sig: Sig_O("ctl", msg)}`.

After: `{msg: box, sig: Sig_O("ctl", box)}` with `box = Seal(ek_C, enc({seq, op, ...}), aad = "ctl")`.
The server checks the owner's signature on the box, opens it with its ML-KEM key, then checks the
sequence number exactly as before. This is the paper's `Ctl(m) = (Seal_pkCS(DO-CS, n||m), Sign(skDO, ct||box))`.

### Revoked credentials (P-06)

On `deauth` the server now erases the wrapped `a_u` and keeps only the user id with a revoked flag, so
it can still answer "this receiver has been revoked" instead of "unknown user".

## Security impact

- A network observer no longer sees which addresses a search touched or what came back, nor group
  names, user ids, epochs and scopes in control messages. Theorem 2's network view and the leakage
  claims of Sections II-G and IV-A now hold for this code.
- A revoked receiver who still holds old-epoch keys and watches the network can no longer unmask other
  receivers' results (it would need `a_v` of the searching receiver).
- The server's view is unchanged (it holds every `a_u` and its own ML-KEM key), so the leakage function
  to the server and every server-side check stay as they were.
- Nothing about the stored index, documents or states changes; existing data stays readable.

## Compatibility

Client and server must be the same version: an old receiver cannot read a new response and an old
server cannot open a sealed control message. Both are in one program today; the networked server
(milestone 2) will carry a protocol version in its API path (`/v1/`), and these message formats are
version 1.

## Cost

One extra AES-GCM encryption and decryption per search, and one ML-KEM encapsulation and decapsulation
per control message (control messages are rare: group setup, join, revoke).

## Tests

- `tests/test_m15_paper.py::test_search_response_hides_the_searched_addresses_from_the_network`
  and `::test_control_messages_are_confidential_on_the_network` (previously expected failures) now pass.
- `::test_revoked_credential_is_erased_at_the_server` (new).
- Every existing tamper, revocation and Security Lab test runs against the new formats.
