# Design note 002: invites, joining over the network, and large downloads

Status: **proposal, waiting for approval** (rule 2: protocol changes need a note, tests and your yes).
Milestone 3 of `REALLIFE_PLAN.md`. Nothing in this note is implemented yet.

## The problem

On one PC, joining needs no setup: the receiver imports `owner.pqpub` and `cloud.pqpub` from the same
folder, and the owner approves after comparing a fingerprint on the same screen. Across machines:

1. The receiver must learn, from someone it trusts, where the server is, which TLS certificate it has,
   and which owner and server keys are genuine. The paper assumes this ("public verification keys are
   distributed authentically", "vk_u approved out of band").
2. Today anyone who can reach the server can post a join request, list all pending requests (names and
   public keys) and fetch any receiver's sealed mail (`REALLIFE_PLAN.md` M2-4).
3. Large documents and large result sets come back in one response; a broken connection means starting over.

## Proposal

### A. The invite (no protocol change)

The data owner makes an invite for one person. It is a small file (`*.pqinvite`, JSON) or a link of the
form `pqsse://host:port/join?...` that carries:

| Field | Purpose |
| --- | --- |
| `v` | invite format version (1) |
| `server` | host and port of the HTTPS API |
| `tls` | SHA-256 of the server's TLS certificate (the receiver pins it) |
| `server_fp`, `owner_fp` | fingerprints of the server's and the owner's post-quantum public keys |
| `id` | random 16-byte invite id |
| `code` | random one-time code (shown separately, see below) |
| `expires` | expiry time (default 7 days) |
| `name` | the receiver name the owner expects (shown, not enforced) |

The receiver's app fetches the server's and the owner's public keys over the pinned connection and
accepts them only if their fingerprints equal `server_fp` and `owner_fp`. This replaces copying the two
`.pqpub` files by hand and adds no cryptography.

The code can travel with the invite (convenient) or separately (safer: someone who intercepts only
the file cannot use it). The app suggests sending the code by a second channel.

### B. Single-use invites, enforced at the owner and at the server (protocol change)

1. A new control message `Ctl(invite, id, H(code), expires)` registers the invite at the server (sealed
   and signed like every control message, design note 001).
2. The join request gets two more fields inside the receiver's signed request: `invite_id` and
   `proof = HMAC-SHA3-256(code, "pqsse/v3/join" || H(request without proof))`. The code itself is never sent.
3. The server stores a join request only if `invite_id` is registered, unexpired and unused, and the
   proof verifies; it then marks the invite used. A wrong, expired or replayed invite is refused with a
   clear reason, before anything is stored.
4. The owner checks the same proof again in `check_join` (defence in depth) and shows the receiver's key
   fingerprint and the invite it used before approving.
5. Both sides compare the receiver's key fingerprint out of band, shown as **six words** as well as hex
   (PGP word list; its licence is checked before it is added).

### C. Close the open endpoints (protocol change)

- `join_list` requires the owner's ML-DSA signature over `("join_list", timestamp)`; the server checks
  it against the paired owner key and a 300 s window.
- `mail_get` requires the receiver's ML-DSA signature over `("mail_get", uid, timestamp)`, checked
  against the verification key in that receiver's join request.
- Effect: only the owner can see pending requests; only a receiver can fetch its own sealed mail.

### D. Large downloads in parts (protocol change)

`doc_get` gets optional `offset` and `length` inside the receiver's encrypted request; the server answers
with that slice of the ciphertext plus the total length and the owner's document signature. The client
keeps the parts on disk and asks again from where it stopped; it checks the owner's signature over the
whole ciphertext before decrypting, exactly as now. Search responses stay one message (they are signed as
a whole); the client retries them.

## Security impact

- A and C reduce what an outsider can do or learn; nothing in the scheme's keys, index or checks changes.
- B adds an authentication step before the paper's Join. A stolen invite file without the code is useless;
  file and code together allow one join, which the owner still approves after the fingerprint check.
- D changes only transport; integrity still comes from the owner's signature over the full ciphertext.
- The server learns invite ids, their expiry and which invite a receiver used (it already sees join
  requests). It never learns the code.
- Paper: B and C are additions to Algorithm 2 and to the server's request checks; they go into
  `docs/PAPER_CHANGES.md` as implementation notes, not as changes to the theorems.

## What does not change

The ten algorithms, the capability, the index, the states, the eight verification checks, revocation.

## Already built without this note (no protocol change)

- **Retries** with exponential backoff and jitter for connection failures, 429 and 503.
- **Safe retransmission:** the exact last accepted batch, control message or state (the same signed bytes)
  is refused with the reason `duplicate` and never applied twice. A replay by anyone else is therefore
  still a refusal (the Security Lab's "Replay an update" stays caught). The owner, resending its own
  message after a lost reply, treats `duplicate` as accepted and commits. Older replays get `bad_sequence`.
  Not covered: an owner app that crashes after the server applied a batch but before it saved its own
  state; on restart it signs a new batch with the same number, which is refused, and the owner must
  re-sync (to be designed with Part D's export and import).
- **Clock-skew check** at connect time (`GET /v1/time`) with a warning above 2 minutes and a refusal
  above the 5-minute token window.
- **Client modes:** Data owner, Receiver, Local demo; the server address and pinned certificate are
  typed in (or come from an invite once B is approved).

## Decision needed

Approve A to D (recommended), or A to C without D (large documents then need a retry of the whole
document), or A only (invites as a convenience; endpoints stay open as today).
