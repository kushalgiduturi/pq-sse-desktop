# Design note 004: more than one data owner

Status: **proposed, waiting for approval**. Milestone 6 of `REALLIFE_PLAN.md`. Not built in M6.

## The problem

The paper and the code have exactly one data owner per server: the server stores one owner key
(`pair-owner` refuses a second unless `--replace`), one control sequence number and one set of groups.
Three different wishes hide behind "more than one owner":

1. **Several independent owners on one server**: two departments share one machine, and neither sees
   the other's groups, receivers or invites.
2. **One owner on several devices**: the same person works from a desktop and a laptop.
3. **Several writers in one group**: two people add documents to the same group.

## Options

### A. Several independent owners on one server (recommended; a protocol change, but not to the scheme)

- The server keeps a table of owners, each identified by its key fingerprint. The operator pairs each one
  (`pair-owner` adds instead of replacing).
- Every owner-signed message (`ctl`, `update`, `state_put`, `join_list`) carries the owner id. The server
  checks the signature against that owner's key. Sequence numbers, groups, invites, join requests,
  credentials and mail are kept per owner.
- Receiver requests name the owner too. A receiver identity can join several owners, with a separate
  capability for each.
- Each owner's part works exactly as today's single-owner scheme. The paper's theorems hold per owner
  unchanged, because no key or index structure is shared.
- Leakage: the server already sees which owner sends what. It now also stores which owner each receiver
  request is for. That is visible today too, because there is only one owner.
- Cost: every table gains an owner column, plus a store migration. The app needs an owner choice in
  Receiver mode. There are two new admin views: owners and their storage.

### B. One owner on several devices (not recommended now)

- The owner's state (counters, chain heads, epoch keys, receivers) changes with every batch. Two devices
  signing batches with the same key race for the same sequence number. The server refuses one, and that
  device's state is then wrong.
- Doing this safely needs state synchronisation between devices (a lock at the server, or a device that
  is the single writer at a time with hand-over). That is a design of its own.
- Until then: one device writes. The other gets the owner's keys only through the key backup of milestone 5,
  used as a hand-over: stop on one device, back up, restore on the other.

### C. Several writers in one group (not recommended)

- The scheme's index is one hash chain and one counter per keyword, kept by the single owner, and
  verification (Theorem 3) assumes one signer. Several writers need either one shared signing key (no
  accountability, and the race of B) or per-writer chains that the receiver merges and checks, which
  changes Algorithms 4, 5 and 8 and the paper's security games.
- This is research, not engineering. It belongs to the paper's future work.

## Security impact of A

- Isolation between owners rests on the server's checks: owner X cannot sign for owner Y's groups. A
  malicious server could mix them up, but it can already serve wrong data; receivers still verify every
  answer with the owner key from their invite, so a mixed answer fails verification.
- The admin interface shows per-owner counts, never content.

## Tests it would get

Two owners on one server with groups of the same name, kept apart; owner X's message refused for owner
Y's group; a receiver in both, with the right capability used for each; per-owner sequence numbers; a
store migration from a one-owner store.

## Decision needed

A (recommended, built in a later milestone), or keep one owner per server and document "run one server
per owner" (no work; Docker makes that cheap). B and C stay future work either way.
