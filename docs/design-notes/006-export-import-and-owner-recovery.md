# Design note 006: export, import, and recovering the data owner's state

Status: **proposed, waiting for approval**. Milestone 6 of `REALLIFE_PLAN.md`. Parts A and B are built in
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
restart; a crash before sending (dropped); the RE rebuild case. C: restore a backup from before two
updates and one epoch change, then recover everything; a server serving an older state; a batch
applied but not published, resolved by the RE rebuild.

## Decision needed

Approve A and B (recommended, built in M6), and C (recommended, built later; it changes the epoch control
message and adds `owner_sync`). The alternative to C: document "back up after every revocation", with no
recovery.
