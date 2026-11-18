# Design note 005: large collections

Status: **proposed, waiting for approval**. Milestone 6 of `REALLIFE_PLAN.md`. Parts A and B are built
in M6 once approved.

## Measured now

ML-KEM-768 with ML-DSA-65 on the native backend, in-process server (`World`), one group. The
"downloaded" column counts the bytes of the server's replies.

| Distinct keywords | State (padded) | First search | Next searches | Downloaded for 3 searches |
| ---: | ---: | ---: | ---: | ---: |
| 1,000 | 180 KB (N_max 4,096) | 5 ms | 2 ms | 0.56 MB |
| 10,000 | 721 KB (N_max 16,384) | 20 ms | 6 ms | 2.2 MB |
| 50,000 | 2.9 MB (N_max 65,536) | 62 ms | 25 to 30 ms | 8.7 MB |

| Documents with one shared keyword | BuildIndex | Search | Search reply |
| ---: | ---: | ---: | ---: |
| 1,000 | 1.3 s | 15 ms | 40 KB |
| 20,000 | 24.5 s | 260 ms | 0.74 MB |

What this shows:

1. **Every search downloads the whole state again** (`states_get`): about 44 bytes per padded record.
   Over a network this dominates: 2.9 MB per search at 50,000 keywords.
2. Large results are fine: 20,000 hits is 0.74 MB. The server's limit of 100,000 documents per group
   bounds a reply at about 3.7 MB.
3. BuildIndex costs about 1.2 ms per document, mostly the per-document ML-DSA signature. A batch must fit
   the server's 64 MiB body limit, so a large import of large documents does not fit in one batch today.

## Proposal

### A. Split large updates into several batches (no protocol change)

The owner splits a BuildIndex or Update into batches that fit the body limit (default target 32 MiB,
or 5,000 documents), each with its own sequence number, and publishes once at the end.

Why this is safe: a receiver derives addresses only up to the counters `c_w` in the **published**
state, so entries of batches sent but not yet published are never searched. A crash between batches
leaves entries beyond the published counters, invisible to receivers. The owner finishes or resends
them (design note 006, write-ahead journal).

### B. Fetch the state only when it changed (small protocol change)

- `states_get` gains an optional `have: {epoch: version}` inside the receiver's encrypted request.
- For each segment whose stored version equals the one the receiver has, the server answers
  `{e, same: true}` instead of the state. Otherwise it answers as today.
- The receiver uses its cached state (already verified) for `same` segments. **All of Algorithm 8's
  checks still run on it**, including freshness (`exp`): a cached state past its expiry is refused
  exactly like an old state served by the server.
- Security: the server could answer `same` for a segment that changed. That is the same as serving the
  older state, which it can already do. The freshness window bounds both in the same way, and the
  receiver's no-rollback check is unchanged. No new trust.
- Leakage: the server learns which state version a receiver holds. It can already infer this from when
  the receiver last fetched it.
- Effect, measured on the case above: at 50,000 keywords, a second search downloads tens of bytes for the
  state instead of 2.9 MB. Only the first search after each publish pays.

### C. A state in buckets (protocol change to Algorithm 5; not recommended now)

The state is split into `B` buckets by a keyed hash of the keyword. The signed header carries the hash of
each bucket, and a search fetches the header and one bucket (about 45 KB instead of 2.9 MB at 50,000
keywords with `B = 64`).

- Leakage: the server learns the bucket of each search, a keyed `log2(B)`-bit function of the keyword per
  epoch. Repeated searches of one keyword are already linkable (search pattern), but two **different**
  keywords in the same bucket become linkable, which the paper's `L_Srch` does not include.
- Padding: each bucket is padded to the same size, so the bucket sizes hide the keyword distribution only
  up to `N_max / B` per bucket, and an overflow doubles all of them.
- It changes Algorithm 5, check 1 of Algorithm 8 and the leakage function. With B in place, the first
  search after a publish is the only expensive one, so C is kept for later, with numbers from real use.

### D. Results in parts (not needed)

A reply of up to 3.7 MB is within limits and is retried whole if lost. Not proposed.

## Tests it would get

A: an import larger than one batch, with a crash between batches and receivers that see nothing new
until the publish. B: bytes downloaded for repeated searches; a changed state fetched again; a cached
state past `exp` refused; a server that falsely answers `same` treated exactly like one that serves the
old state; old clients without `have` still served.

## Decision needed

Approve A and B (recommended). C stays future work. D is not needed.
