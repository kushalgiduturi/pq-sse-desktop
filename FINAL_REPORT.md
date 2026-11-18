# PQ-SSE: from a one-PC demo to a client-server system, final report

Milestone 8 of `REALLIFE_PLAN.md`. Branch `reallife` (worktree `C:\Users\Kushal\pqsse-reallife`), 18 to 19
November 2026, 16 commits after `af4759b` (this report included). **Nothing is pushed, merged into `master`, released or published.**
Every number below was measured on one laptop (Intel Core i7-13620H, Windows 11 Home, Python 3.11.9, OpenSSL
4.0.3 through cryptography 50.0.2), unless the line says otherwise.

## 1. In short

- The paper's scheme now runs as three real parties over a network: a **server program** (Windows console
  program, Python package or Docker image) with TLS and a pinned certificate, and the **desktop app** in
  Data owner or Receiver mode. People join with an **invite** and a one-time code, and compare six
  fingerprint words.
- The code was checked against the paper item by item. Three deviations were fixed in the code, and five
  became suggested text changes for the paper. Each protocol change has a design note that you approved.
- Post-quantum operations are 17 to 76 times faster: OpenSSL's ML-KEM and ML-DSA are now the default. A
  search with verification takes about 8 ms instead of about 70 ms (section 5).
- The keys have a lifecycle: passphrase change, encrypted backups, auto-lock, private file permissions, a
  write-ahead journal, recovery from an old backup, and an activity log.
- **336 tests** pass, plus the smoke, network, Docker, portable, installer and web-installer tests.
- The author did one security review, which is **not an audit**: 8 findings fixed and 4 accepted limits.
  Both builds are bit-for-bit reproducible on this PC.
- **Not done:** a test on separate computers. That needs you (section 8).

## 2. What works across machines, and how to run it

| Piece | How | Doc |
| --- | --- | --- |
| Server | `python -m pqsse.server init` then `run`, or `pqsse-server.exe` (`build_server.ps1`), or `docker compose -f docker/docker-compose.yml up` | `docs/SERVER.md` |
| Data owner | the app: welcome sheet, then **Data owner**; connect with the server's address, port and two fingerprints; give `owner.pqpub` to the operator (`pqsse-server pair-owner`) | `docs/MULTI_MACHINE_TEST.md` |
| Receiver | the app: **Receiver**; paste the invite, type the one-time code; read the six words to the owner | the same |
| Several owners on one server | `pqsse-server pair-owner FILE --add`; each owner gets its own store | `docs/SERVER.md` |
| Keys | Insights: Keys and passphrases (change, back up, restore, lock); Workspace: Activity, export and import, change a person's groups, recover after a backup | `docs/KEYS.md` |

Shown on one PC: three separate processes over TLS on loopback, every step a fresh process, and the
server killed and restarted mid-run (`scripts/network_e2e.py`). The server also ran in Docker with the
clients on the host (`scripts/docker_e2e.py`). **Not shown:** two or three real computers on a network
(section 7).

## 3. Milestones

| # | What | Commit |
| --- | --- | --- |
| 0 | Plain role names (Data owner, Receiver, Cloud server), neutral demo data, the lesson cast only behind "Teaching names" | `d55abf4` |
| 1 | Paper conformance: every definition, algorithm, theorem, leakage statement and evaluation claim mapped to code and tests; 8 items for you | `f2df5b5` |
| 1 | Your decisions applied: design note 001 (P-01, P-02, P-06 in the code), suggested paper changes | `3f48894` |
| 2 | Server: HTTPS with pinning, admin interface, limits, WAL store, document files, backup and restore, Windows program, Docker | `fe2e16f`, `58b190e` |
| 3 | Client modes, retrying HTTPS client, safe resends, clock check; design note 002 (invites, closed endpoints, documents in parts) | `c021d05`, `086f5c0` |
| 4 | Network, fault and abuse tests; three bugs they found, fixed | `bc59a7c` |
| 5 | Native post-quantum code by default; key lifecycle | `6dff7d8` |
| 6 | Part D: notes 003 to 007; large collections, journal, export and import, activity log; then 003, 004 A, 006 C | `1345adf`, `4c5c003`, `5cd18cf` |
| 7 | Part E: threat model, review, fuzzing, TLS probes, `pip-audit`, SBOM, reproducible builds, installer tests, README | `2154263`, `2820a88`, `78b5a89` |

Every decision made along the way is in `REALLIFE_PLAN.md` section 7 (M0-1 to M7-6).

## 4. Conformance with the paper

From `docs/PAPER_CONFORMANCE.md`. The ten algorithms and Theorems 1, 3, 4, 5 and 6 match. Theorem 2 deviated
for the network part of the attacker's view until P-01 and P-02 were fixed, and now matches. The proofs were
not re-checked.

| # | What differed | Your decision | State now |
| --- | --- | --- | --- |
| P-01 | Search responses signed but not encrypted | code to the paper | fixed, tested |
| P-02 | Control messages signed but not sealed to the server | code to the paper | fixed, tested |
| P-03 | `N_max` doubles instead of being fixed (the server learns the power-of-two range of a group's keyword count) | keep, paper text changes | as decided, tested |
| P-04 | Join nonce chosen by the receiver, plus a timestamp | paper text changes | `docs/PAPER_CHANGES.md` |
| P-05 | Rekey boxes also signed | keep, paper cost formula changes | `docs/PAPER_CHANGES.md` |
| P-06 | A revoked credential was kept at the server | code to the paper | fixed, tested |
| P-07 | The paper's numbers cannot be reproduced from this repository | name the artifact; add baselines | **partly**: a primitive benchmark with classical baselines now exists (`pqsse/bench_primitives.py`). The paper used liboqs 0.16 on a Linux VM; this code uses OpenSSL on Windows, so the numbers are comparable, not the same |
| P-08 | Test counts differ from Table I | align after P-07 | **not done** (planned for milestone 5 and missed). Still 300 queries instead of 375, and 100 trials per tamper type instead of 150 |

Protocol additions, each approved in a design note: invites and closed endpoints (002), changing a receiver's
groups (003), several owners (004 A), state fetched only when changed (005 B), owner recovery escrow and
owner-only reads (006 C). None changes a theorem's statement; `docs/PAPER_CHANGES.md` lists them as
implementation notes. One side effect to know: since 006 C, document keywords travel inside the encryption,
so a receiver who can open a document sees the owner's explicit keywords for it (decision M6-9).

## 5. Measurements

Per operation, ML-KEM-768 with ML-DSA-65, the app's own benchmark (`python -m pqsse.bench`), in milliseconds.
The left column is the released v0.1.1 (pure Python, `site/data/facts.json`); the right is this branch
(native, `docs/measurements/facts-reallife.json`). Same laptop, one day apart.

| Operation | v0.1.1, pure Python | `reallife`, native |
| --- | ---: | ---: |
| Setup | 23.3 | 8.8 |
| Join | 260.0 | 27.3 |
| Update (add, 20 keywords) | 117.4 | 14.4 |
| Publish | 62.3 | 10.9 |
| Search | 54.2 | 3.0 |
| Verify | 14.8 | 4.5 |
| Decrypt | 11.0 | 1.1 |
| Revoke R (30 documents) | 538.8 | 58.2 |
| Revoke RE (30 documents) | 1,937.0 | 171.5 |

Primitives (`docs/measurements/primitives.md`, median microseconds): ML-DSA-65 sign 44,080 (pure) against
901 (native); ML-KEM-768 decapsulate 6,896 against 220. The classical baselines from the same OpenSSL:
Ed25519 sign 35, X25519 exchange 45, RSA-2048 PSS sign 750. Native sign and decapsulate include deriving the
key from its stored seed on every call.

Large collections (design note 005), at 50,000 distinct keywords: the padded state is 2.9 MB. Three
searches downloaded 8.7 MB before note 005 B and 2.9 MB after it. A result with 20,000 hits is 0.74 MB and
takes 260 ms.

## 6. Tests and checks

| Check | Result |
| --- | --- |
| `pytest` (33 files) | 336 of 336 passed |
| Server smoke test (separate process) | pass |
| Network end-to-end (three processes, server killed and restarted) | pass, 11 checks |
| Docker end-to-end (server in a container, non-root, read-only root) | pass, 14 checks, the container on the native backend |
| Fault and abuse tests (drops, delays, lost replies, full disk, crash during join, skew, replay, floods, garbage) | pass (`tests/test_m19_network_faults.py`) |
| Fuzzing, Hypothesis (wire format, invites, every endpoint, tampered replies, document and PDF import) | 14 tests, run 9 times with fresh inputs: pass after 4 fixes |
| TLS probed from outside | TLS 1.2 and 1.3 only, ECDHE with AES-GCM or ChaCha20 only, no compression |
| `pip-audit` of the three lock files | no known vulnerabilities (2026-11-18) |
| Portable test (spaces and non-ASCII paths, fresh data folder) | pass |
| Installer test (twin install, upgrade, uninstall while running) and web installer real run | pass |
| Reproducible builds (two builds of one commit) | server 123 of 123 files, desktop 2,127 of 2,127 files identical |
| Security Lab | 10 of 10 attacks caught; the collusion scenario shows R and RE as designed |

## 7. Not verified

- **Separate computers on a real network**, including firewalls, NAT and real latency. Everything ran on one PC.
- **A clean Windows PC.** Windows Home has no Sandbox and there is no VM image here. The portable and
  installer tests use fresh folders on this PC.
- **Reproducibility across PCs** (shown on this PC only).
- **Independent review or audit** of the code, the scheme or the threat model.
- **Constant-time behaviour** of the native code (OpenSSL's claim). The pure-Python fallback is not constant time.
- **liboqs** (supported, not installed here).
- **Post-quantum TLS:** TLS key exchange is classical. The data inside is protected by ML-KEM and ML-DSA, but
  traffic metadata only by classical TLS.
- **Load** beyond the flood test. The server is meant for small groups.
- **Windows 10**, other GPUs, older drivers (unchanged from `docs/RELEASE_NOTES.md`).
- **Code-signing prices**, which could not be refreshed (`docs/DISTRIBUTION.md`).
- **The paper's proofs** (not re-checked) and **P-08** (section 4).

## 8. What you must decide or set up

1. **Try it on separate machines** with `docs/MULTI_MACHINE_TEST.md`. It needs two or three PCs, the code
   (`git archive` as the page shows), and a firewall rule for port 8443 on the Private profile that you add
   yourself, then remove.
2. **Merge and push.** `reallife` is 16 commits ahead of `af4759b` and unpushed. `master` also carries the
   site rewrite (`0e9ae4c`) that the site session left for your approval. Your choices: merge `reallife` into
   `master`, push both, or keep them apart.
3. **A release (0.2)** with these features. The site copy for it is not written yet (decision M7-5): the
   public site still describes 0.1.1. A release needs the version number, release notes, the signed
   `latest.json`, and your yes to publish.
4. **Code signing:** buy a certificate or use a signing service, or stay unsigned (`docs/DISTRIBUTION.md`).
   Recheck the prices first.
5. **The paper:**
   - accept or edit the text changes in `docs/PAPER_CHANGES.md`;
   - decide which artifact backs the paper's numbers (P-07);
   - decide whether to align the test counts with Table I (P-08).
6. **liboqs:** whether you still want it built in CI. OpenSSL now covers every parameter set except
   ML-KEM-512.

## 9. For the paper's future work

- **Several writers in one group** (design note 004 C): per-writer chains that the receiver merges and checks.
  This changes Algorithms 4, 5 and 8 and the security games.
- **One owner on several devices** (004 B): owner-state synchronisation without a single writer.
- **States in buckets** (005 C): searches fetch one bucket, at the price of a coarse new leakage. It needs a
  new leakage function.
- **Post-quantum transport:** hybrid or ML-KEM TLS, so that metadata is protected against harvest-now
  attacks too.
- **Freshness without the 24-hour window:** a server-independent way to learn that a state was superseded.
- **Owner key rotation** and **server key replacement** with automatic re-pairing (now manual,
  `docs/SERVER.md`).
- **Escrowed invites,** so that recovery from an old backup keeps invites made after it (006 C limit).

## 10. Where things are

`REALLIFE_PLAN.md` (plan and decisions), `docs/PAPER_CONFORMANCE.md`, `docs/PAPER_CHANGES.md`,
`docs/design-notes/` (001 to 007), `docs/SERVER.md`, `docs/MULTI_MACHINE_TEST.md`, `docs/KEYS.md`,
`docs/THREAT_MODEL.md`, `docs/SECURITY_REVIEW.md`, `docs/SBOM.cdx.json`, `docs/wire-format.md`,
`docs/measurements/`.
