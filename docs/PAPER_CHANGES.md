# Suggested changes to the paper

From the decisions on `docs/PAPER_CONFORMANCE.md` (accepted 2026-11-18). These are text changes for
the authors; nothing in the paper file was edited. Section and item numbers refer to
`MU-PQ-SSE_v3_Journal_Paper.pdf`.

| # | Where in the paper | Suggested change | Why |
| --- | --- | --- | --- |
| P-03 | Design goal G7 (Section II-B); Algorithm 5 line 2; Section II-G, third sentence | Say that the state is padded to a capacity `N_max` that doubles when a group outgrows it, so the server learns the power-of-two range of the keyword count of each group, and nothing finer. Example wording for G7: "the CS learns only the power-of-two range of the number of keywords" | The implementation doubles `N_max` (default 4,096 records) instead of refusing updates; a fixed capacity would block a growing collection |
| P-04 | Algorithm 2 lines 1 and 3; Table I row "Join with unapproved key or invalid proof" | Replace the owner's nonce by: the receiver signs `join || u || pk_u || vk_u || n || t` with a fresh random `n` and its clock time `t`; the owner rejects a request older than a window (600 s in the implementation) or a nonce it has already seen | The join request travels through the server's mailbox before any owner-to-receiver channel exists, so a challenge would need an extra round trip |
| P-05 | Revocation paragraph after Algorithm 10; Section III-F ("rekey messages ... rather than signed"); Table IV row Revoke (R); Section IV-B ("rekey messages need no signature") | State that each rekey box is bound to `m_v` and also signed by the owner, and add `N * T_S` to the Revoke cost formula | The implementation keeps the signature as a second layer of authentication; the paper's cost and the code should agree |
| P-07 | Section III-A and every measured number (Abstract, Tables II to IV, Figs. 5 to 9) | Name the artifact that produced the numbers (version or commit, liboqs version, the baseline harness) and where it can be obtained. Until milestone 5 of `REALLIFE_PLAN.md` adds liboqs and a classical-baseline benchmark to this repository, the numbers cannot be reproduced from it | Reproducibility |
| P-08 | Table I | Align the counts with the published test suite (or the reverse) once P-07 is settled | The code's tests use different counts (for example at least 300 queries instead of 375, 100 trials per tamper type instead of 150) |

Items that need no paper change: P-01, P-02 and P-06 were changes in the code to match the paper
(design note `docs/design-notes/001-paper-conformance-fixes.md`).

Optional additions, all in the code's favour and not required:

- The server stores documents under a handle `F(K_doc, "handle" || id)[0:16]`, so it never sees
  document identifiers; the paper's `L_Upd` lets it see them. The paper could mention this as a
  leakage reduction.
- The receiver also rejects a response whose newest state is older than a key it holds ("hiding a
  new epoch"), and the server refuses an epoch change without a final state of the old epoch.

## Implementation notes from design note 002 (networked joining)

These add steps around the paper's Join; they change no theorem. For the paper's implementation section:

- The receiver learns the server address, the server's TLS certificate fingerprint and the fingerprints of
  the server's and the owner's post-quantum keys from an **invite** made by the owner (the paper's
  "public verification keys are distributed authentically").
- A join request names a single-use invite and carries two proofs of its one-time code (HMAC-SHA3-256 under
  two keys derived from the code: one checked by the server, one by the owner). The server stores join
  requests only for registered, unexpired, unused invites.
- Listing join requests needs the owner's ML-DSA signature, and fetching mail needs the receiver's, each over
  a fresh timestamp.
- Documents can be fetched in parts; the owner's signature is still checked over the whole ciphertext.

## Implementation notes from design notes 005 to 007 (milestone 6)

These change no algorithm's security argument. For the paper's implementation section:

- Large updates are sent as several signed batches and published once. Receivers search only up to the
  counters of the published state, so a partly sent update is invisible to them.
- A receiver may ask for the group's states "only if changed". A cached state goes through every check of
  Algorithm 8, including freshness, so the server gains nothing it could not get by serving the old state.
- The owner keeps a write-ahead journal and an encrypted, hash-chained activity log on its own computer.
