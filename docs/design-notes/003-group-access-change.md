# Design note 003: changing a receiver's groups without revoking them

Status: **approved 2026-11-18 (recommended options)**. Milestone 6 of `REALLIFE_PLAN.md`. Not built in M6
(the plan builds notes 005 to 007); built later only if approved.

## The problem

Today a receiver's groups are fixed at Join. The data owner can only revoke the receiver from
everything (Algorithm 10) and approve a new join. In practice people change teams: Dana should
gain access to "Legal", or lose "Finance" but keep "Legal".

What exists that this can build on:

- The server keeps each receiver's scope (`creds.scope`) and refuses any request outside it (`scope`).
- The receiver's capability holds `a_u`, `m_u` and, per group, the keys of every live segment.
- Revocation rotates a group to a new epoch and sends rekey boxes, bound to each remaining receiver's
  `m_u` and signed, to the receivers that keep the group.

## Proposal

### A. Grant a group (protocol change: one control op, one mail kind)

1. The owner sends `Ctl(scope, uid, groups)`, sealed and signed like every control message. The server
   replaces that receiver's scope. It refuses an unknown or revoked `uid`.
2. In the same control message the owner queues a **grant box** for the receiver:
   `seal(ek_u, {g: {base, keys of live segments}}, aad = "grant" || uid, psk = m_u)`, signed by the owner
   over `("grant", uid, box)`. This has the same form as a rekey box, and is also bound to `m_u`, so only
   the receiver that holds `m_u` from its own Join can open it.
3. The receiver adds the groups to its capability. `a_u` and `m_u` do not change, so nothing else about
   that receiver changes.

### B. Take a group away (protocol change: the same op, then an existing step)

1. The owner sends `Ctl(scope, uid, groups)` with the smaller set. From then on the server refuses
   that receiver's requests for the removed group: a **policy** cut, effective at once.
2. The receiver still holds the keys of the group's current segments, so the owner then **rotates that
   group only** (Algorithm 10's rotation, without `deauth`). Policy R or RE, chosen as for a revocation.
   The removed receiver gets no rekey box for that group. The others do.
3. After the rotation, new documents in that group are beyond the removed receiver's keys (R). With RE,
   old segments are dropped too. This is the same guarantee as revocation, for one group.

The app asks "R or RE" exactly as it does for revocation, and explains that B.1 alone stops searches but
leaves the receiver able to decrypt ciphertexts it already downloaded.

### C. What is not proposed

- Read-only or per-document access: the scheme has one kind of access per group.
- Taking a group away without a rotation: possible (B.1 only), but the app would have to call it a
  server-enforced restriction, not a cryptographic one. Recommended only as a first step before the rotation.

## Security and leakage impact

- The server learns scope changes and when they happen. It already learns the scope at Join.
- Grant: the grant box is sealed with ML-KEM to the receiver and bound to `m_u`, like rekey boxes. A
  server that replays an old grant box gains nothing: the receiver ignores keys for groups and epochs
  it already has, and the server's scope check is independent.
- Removal: the server's refusal is Theorem 5 (scope confinement) with the smaller scope. Hiding new data
  from the removed receiver comes from the rotation, as in Theorem 6 (ii) for R and (iii) for RE, applied
  to one group. Until the rotation finishes, only the server's scope check protects new content.
- Paper: an addition to Algorithm 10 ("partial revocation"); Theorems 5 and 6 apply per group. It goes to
  `docs/PAPER_CHANGES.md` as an extension, not a change to a theorem.

## Tests it would get

Grant, then search the new group; removal, then a refusal (`scope`) before the rotation and a
cryptographic failure after it (old keys cannot open new segments); R and RE variants; a replayed grant
box; a grant to a revoked receiver refused; the other receivers of the group unaffected.

## Decision needed

Approve A and B (recommended), A only (grants only; removal stays revoke-and-rejoin), or neither.
