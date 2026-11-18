# Design note 007: the data owner's activity log

Status: **approved 2026-11-18 (recommended options)**. Milestone 6 of `REALLIFE_PLAN.md`. Built in M6 once approved.

## The problem

A data owner cannot answer "who did I give access to, when, and what changed since?" The app's log
file records events for support, but it is plain text, it rotates, and it must not hold document titles.
The server's request log (`admin log`) holds sizes and endpoints only, by design.

## Proposal (no protocol change)

An append-only, hash-chained log in the owner's vault, readable only with the owner's passphrase.

| Field | Example |
| --- | --- |
| `n` | 41 (sequence number of the entry) |
| `t` | time, unix milliseconds |
| `what` | `group.create`, `doc.add`, `doc.delete`, `invite.create`, `join.approve`, `revoke`, `access.change`, `publish`, `passphrase.change`, `backup`, `export`, `import`, `recovery` |
| `detail` | group, document title and id, receiver name and fingerprint, policy, invite name, counts |
| `server` | the server's answer: accepted, `duplicate` (recovered resend), or the refusal reason |
| `prev` | `H(previous entry)`: the hash chain |

- **Where**: vault records `log:<n>`, each encrypted like every vault record. The owner's state stores the
  head `(n, H(entry n))` and updates it in the same transaction as the action. Deleting, editing or
  reordering entries breaks the chain against the head, which the app checks when it shows the log.
- **What it protects against**: accidental damage, and anyone who changes the vault file without the
  passphrase (AES-GCM already refuses changed records; the chain also catches deleted or swapped
  ones). It does not protect against the owner, who holds the key and could rewrite the whole chain.
  It is a record for the owner, not evidence for third parties. Signing entries would not change that,
  because the owner holds the signing key too.
- **Size**: about 200 bytes per entry. The app keeps everything. An export writes the log to CSV (plain,
  so the app warns that it contains titles and names) or to an encrypted `.pqgroup`-style file.
- **In the app**: a "Activity" card in Workspace for the data owner, newest first, filtered by group or
  receiver.
- **What it does not log**: searches by receivers. The owner never sees them, and the server sees only
  tokens. Receivers get no log in this proposal.

## Security impact

None at the server or on the network. Locally, the log is one more copy of titles and names inside the
encrypted vault, covered by the passphrase, the key backup and the file permissions of milestone 5.

## Tests it would get

Every owner action writes exactly one entry, with the server's answer. The chain is checked; a deleted, an
edited (re-encrypted with the right key) and a swapped entry are each detected. The log survives a
passphrase change and a backup round trip. The CSV export holds what the card shows.

## Decision needed

Approve (recommended), or keep only the support log file.

## As built (milestone 6)

- `Owner.log_event`, `activity`, `verify_activity` and `export_activity_csv`; vault records `log:<n>` and
  `loghead`. Every owner action is logged once, as the outermost call, with the server's answer: accepted,
  or the refusal reason. A revocation's own publishes are part of the revocation entry.
- One change from the proposal: an entry is written right **after** its action commits, not in the same
  database transaction. A crash in between loses that one entry, and the chain stays intact. Making them
  one transaction would mean merging the vault's records into the journal's commit, which is more risk
  than an occasional missing entry is worth.
- One-time invite codes are never logged. Passphrase changes and key backups made in the app are logged.
- Tests: `tests/test_m24_export_and_log.py`.
