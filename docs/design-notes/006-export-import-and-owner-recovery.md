# Design note 006: export, import, and recovering the data owner's state

Status: **approved 2026-11-18 (recommended options)**. Milestone 6 of `REALLIFE_PLAN.md`. Parts A and B are built in
M6 once approved. Part C is built later.

## The problems

1. **Moving a group**: there is no way to take a group's documents out of PQ-SSE (to another server,
   another owner, or an offline archive) or to bring a set of documents in, except one by one.
2. **A crash after the server applied a change** (noted since M3): the owner sends a signed batch, the
   server applies it, and the owner app dies before saving its new counters. On restart it builds a new
   batch with the same sequence number, which the server refuses (`bad_sequence`). The group is stuck.
3. **Restoring an old owner backup** (noted in M5): the server is ahead of the backup. The next batch is
   refused, and documents and epoch keys made after the backup are not on this computer. Epoch keys are
   the worst part: without them the owner cannot read those segments again, though receivers can.

## Proposal

### A. Group export and import (no protocol change)

- **Export**: the owner already holds every live document of a group in plain form in its vault (title,
  text, keywords). It writes them to one `.pqgroup` file, encrypted under an export passphrase of 12 or
  more characters, in the same format as the milestone 5 key backup (scrypt N = 2^17, AES-256-GCM). The
  file holds documents only: no keys, no receivers, no index.
- **Import**: read a `.pqgroup` file (or a folder of `.txt` and `.pdf` files, which the app already
  reads one by one) into a new or existing group as ordinary BuildIndex or Update batches, split as in
  design note 005 A.
- The server sees only ordinary update batches. The import does not reveal that the documents came from
  an export.

### B. A write-ahead journal on the owner's computer (no protocol change)

- Before sending any signed message (`update`, `ctl`, `state_put`), the owner stores in its vault the
  exact signed bytes and the local state it will have once the message is accepted, all in one record.
- On success it saves the new state and deletes the record, in that order.
- At the next start, if a record is left over, it sends the same bytes again:
  - `duplicate` or `ok`: the server has them. Apply the stored state.
  - Any other refusal: the server never applied them. Drop the record.
  This is the M3 retransmission rule, now across a restart.
- This fixes problem 2 completely, and the RE rebuild of milestone 4 becomes one case of it.

### C. Recovering from an old backup (protocol change)

1. **An owner recovery key `R`**: a random 32-byte key in the owner's vault, so it is in every backup.
   Each `Ctl(epoch, ...)` also carries `AE.Enc(R, epoch key, aad = g || e)`, stored by the server. The
   server cannot open it, because `R` never leaves the owner's vault or its backups.
2. **`owner_sync`**: a new owner-signed request (timestamp-checked like `join_list`). The server answers,
   per group: current epoch, base, sequence number, the latest owner-signed state of each live segment,
   the stored epoch-key boxes, and the document handles per segment. It also returns the control sequence
   number.
3. **The owner app rebuilds**:
   - It recovers epoch keys from the boxes with `R`, and counters and chain heads from the latest state
     of each segment (owner-signed, so the server cannot forge them).
   - It fetches the documents it does not have through an owner-signed `doc_get`, then decrypts them.
   - If the server's sequence number is beyond the newest published state (a batch was applied but never
     published), the counters for that batch are unknown. The owner then rotates the group with policy RE
     (no receiver removed), which writes a clean index from the documents it now has and sends rekey
     boxes to the receivers. This is costly but always correct.
- What the server could do: serve an older state, or hide documents. The owner then rebuilds an older
  view, the same power the server already has against receivers. The owner signs everything it accepts,
  so the server cannot insert anything.
- Leakage: the server stores one extra ciphertext per epoch and learns when the owner recovers.

## Security impact

A and B add nothing visible to the server. C adds an owner-only read endpoint and stored boxes that only
the owner can open. The paper's model has an honest owner with perfect state. C is an
implementation-level recovery procedure that `docs/PAPER_CHANGES.md` would describe as such.

## Tests it would get

A: export and import round trip, a wrong passphrase, a damaged file, an import split across batches.
B: a crash after the server applied an update, a control message and a state, each recovered at
restart; a crash before the message reached the server (sent at restart, applied once); the RE rebuild case. C: restore a backup from before two
updates and one epoch change, then recover everything; a server serving an older state; a batch
applied but not published, resolved by the RE rebuild.

## Decision needed

Approve A and B (recommended, built in M6), and C (recommended, built later; it changes the epoch control
message and adds `owner_sync`). The alternative to C: document "back up after every revocation", with no
recovery.

## As built (milestone 6): A and B

- A: `Owner.export_group` and `import_group`. The `.pqgroup` file uses the key backup's format (one sealed
  file: scrypt N = 2^17, AES-256-GCM, a magic line as associated data, a passphrase of 12 or more characters,
  never overwritten, private file permissions). The app has an "Export or import a group" card.
- B: one change to the proposal, found while building it. The journal has **channels**: `ctl` for control
  messages, and one `group:<g>` per group for update batches and states. Each channel has at most one
  message in flight. A single journal would have let a batch stuck at the server (for example a full disk)
  block a later revocation. Now the deauth goes through at once, and the rotation that must follow waits
  in the owner record (`rotations`) until the group's channel is settled. A pending rotation also runs before
  any new document goes into that group, so new content is never written under a key that the revoked
  receiver holds. A channel is settled (the same bytes sent again) before any message that touches its
  records. The app does this when the owner's keys are unlocked.
- Tests: `tests/test_m22_journal.py` (crashes after the server applied an update, an approval and a
  publish; a crash before the server; a refusal; no answer while a revocation goes through), and the
  full-disk test in `tests/test_m19_network_faults.py`, now with the stronger expectation that the stuck
  document is delivered later rather than lost.
- C (owner recovery from an old backup) is approved and comes in a later milestone.

## As built (after milestone 6): C

- Every owner has a 32-byte recovery key in its vault (new owners at creation; older owners get one when opened,
  and `resume_pending` then escrows their existing keys and receivers once with the control op `escrow`).
- Control messages carry escrow boxes: `okeys: [[g, e, AE(R, key, "okey" || g || e)]]` with `group` and `epoch`,
  `orecs: [[uid, AE(R, record, "orec" || uid)]]` with `cred` and `scope`. The server stores them in `okeys` and
  `orecs` and cannot open them.
- New owner-only, timestamped, signed reads: `owner_sync` (per group: epoch, base, sequence number, states,
  escrowed keys, document handles; the escrowed receiver records with the server's revoked flag; the control
  sequence number) and `owner_doc` (one stored document with its signature).
- `Owner.recover()` settles the journal, opens the escrow with `R`, downloads and checks every document (the
  owner's own signature; ids found by recomputing handles), then rebuilds every group with policy RE, so the
  index is clean whatever was applied or published after the backup. Documents now carry their keywords inside
  the encryption (`kws`), so the rebuilt index matches the original exactly. Documents from before this change
  fall back to the backup's keywords or to keyword extraction.
- Limits: invites made after the backup must be made again (their owner-side key is not escrowed). Epoch keys
  made before this change by an owner that never ran `escrow` are lost if that owner's backup lacks them.
- The app: a "Recover after restoring a backup" card (Data owner mode).
- Tests: `tests/test_m26_recovery.py`.
