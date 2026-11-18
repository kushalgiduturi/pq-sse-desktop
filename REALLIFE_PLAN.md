# From a one-PC demo to a real client-server system

Status: plan only. Nothing below is built yet. Written 2026-11-18 from your brief, the code as it is
at commit 0e9ae4c, and a first look at the paper (`docs/paper/MU-PQ-SSE_v3_Journal_Paper.pdf`, 13 pages:
12 definitions, 10 algorithms, 6 theorems and a corollary, a leakage section, 6 tables, 9 figures).

## 1. Where we start (facts, checked in the code)

- One program holds all three roles. The cloud is a child process (`python -m pqsse.cloud`) on
  `127.0.0.1` over plain HTTP (`pqsse/cloud/server.py`: stdlib `ThreadingHTTPServer`, body limit 512 MB,
  admin endpoints behind a token, loopback-only check).
- Owner and receiver talk to the cloud only through `CloudAPI.call(endpoint, obj)` with the canonical
  wire encoding (`pqsse/transport.py`). Two transports exist: in-process and HTTP. This seam is where
  the network mode plugs in; `pqsse/owner` and `pqsse/receiver` need no protocol change for it.
- Cloud storage: one SQLite file; its own secret keys and the credentials `a_u` are wrapped under a
  key from the cloud passphrase (D12, D13 in PLAN.md).
- Post-quantum code: pure Python `kyber-py` and `dilithium-py`; the `liboqs` path exists in
  `pqsse/pqbackend.py` but `oqs` is not installed and was never tested.
- The app still uses the Alice, Bob, Carol and Cloud story everywhere (copy.py, lesson, challenges,
  demo data, docs, the website).
- On this PC: Docker Desktop 28.1 is installed but its engine is not running; no C compiler or CMake
  (so liboqs cannot be built here); VirtualBox was not found under `C:\Program Files\Oracle`; checking
  for Windows Sandbox needs admin rights, which I do not use.

## 2. Architecture (target)

```
 Data owner PC                       Server (Windows, or Docker on Linux)           Receiver PCs
 +----------------------+   HTTPS    +-----------------------------------+  HTTPS  +------------------+
 | PQ-SSE Desktop       |  /v1/...   | pqsse-server                      | /v1/... | PQ-SSE Desktop   |
 | mode: Data owner     | ---------> |  public port: protocol API, TLS   | <------ | mode: Receiver   |
 | owner.sqlite (enc.)  |  pinned    |  admin port: 127.0.0.1, token     |  pinned | receiver.sqlite  |
 +----------------------+  cert fp   |  store: SQLite WAL + blob folder  | cert fp +------------------+
                                     |  limits, rate limits, backups     |
          invite file (server address, cert fingerprint, owner key fingerprint, expiry, one-time code)
          travels owner -> receiver by any channel; short fingerprints compared out of band in words
```

The protocol objects stay as they are. What changes is the transport (HTTPS with a pinned
certificate), the server program around `CloudCore`, the client modes, and the operations around them.
`docs/architecture.md` gets this diagram and the data flows.

## 3. Decisions (made now; tell me if you disagree)

| # | Decision | Why |
| --- | --- | --- |
| R1 | Work on a branch `reallife` in a separate git worktree outside OneDrive (`C:\Users\Kushal\pqsse-reallife`). `master` stays releasable and the site session keeps working in the OneDrive folder without branch switches under it | Two sessions, one folder; build output outside OneDrive |
| R2 | The paper PDF is kept out of git (`docs/paper/*.pdf` in `.gitignore`), because the repository is public and the paper may not be published yet. `PAPER_CONFORMANCE.md` quotes item numbers and short phrases only | Ask before publishing your paper |
| R3 | Milestone 0 is done, and it wins over the site's "How the lesson tells it" section: the site session's Home will be changed to plain role names when M0 lands | Your newer brief |
| R4 | Server stays on the standard library HTTP server, wrapped with `ssl` (TLS 1.2 minimum, TLS 1.3 preferred, ECDHE with AES-GCM or ChaCha20 only), with per-connection read timeouts, a cap on open connections, a body limit per endpoint and a request rate limit. For exposure to the internet the docs recommend a reverse proxy (Caddy) in front. Alternative considered: an ASGI server (uvicorn); more dependencies for little gain at this size | Few dependencies, CloudCore unchanged, testable |
| R5 | Certificates: a self-signed ECDSA P-256 certificate made at first start with the `cryptography` package (already a dependency); its SHA-256 fingerprint is printed to the operator and written into invites. Clients pin it: the connection is checked before any request byte is sent. An operator-supplied certificate also works (pin it, or trust the system store when the operator says so) | No public CA needed |
| R6 | One desktop program with three modes chosen at first run: Use as Data owner, Use as Receiver, Local demo (today's teaching mode, unchanged). Same installer for all | One build, fewer installers to test |
| R7 | Server program `pqsse-server`: console exe for Windows (its own PyInstaller spec, no Qt), Python package for Linux, Docker image from `python:3.11-slim`. Config: one TOML file plus `PQSSE_*` environment variables; the passphrase from a file or a Docker secret, never a command-line argument | Brief |
| R8 | Storage: SQLite in WAL mode; large documents in a blob folder named by their handle, written atomically (temp file, fsync, rename), with a SHA-256 in the database that `--check` verifies. Online backup with SQLite's backup API plus a copy of the blobs | Brief |
| R9 | Invites need one new piece of data in the join flow (the invite id, so an invite is single use). That touches the Join message, so it gets a design note and waits for your approval in M3 (rule 2). Until then joins work as today: request, fingerprint check, approval | Rule 2 |
| R10 | Fingerprints in words: 6 words from a public-domain word list (PGP word list); the source and license are recorded before use | Brief: words, not only hex |
| R11 | liboqs is built in GitHub Actions (Windows and Linux, pinned release and commit, checksums recorded), because this PC has no compiler. The built DLL is bundled in installers and the Docker image; the pure-Python backend stays as an explicit fallback with a warning in the app, server and logs | No local toolchain |
| R12 | Clean-machine tests: Docker on this PC for the Linux server once you start Docker Desktop; a Windows clean-machine test as a `.wsb` file for Windows Sandbox (you start it; it needs the Windows feature, which needs admin to switch on) and a VirtualBox script if you tell me where VirtualBox is installed | No admin rights for me |
| R13 | Recovery option (Part C): a second encrypted copy of the key file (export with its own passphrase) rather than a printed recovery code. Trade-offs written in the design note; the rule stays: if the owner loses keys and every backup, the data cannot be recovered | Simpler, testable, no new crypto |
| R14 | Nothing in `pqsse/core`, the wire format or the ten algorithms changes in M2 to M4. Every change there goes through a design note and your approval | Rule 2 |

## 4. Milestones and stops

| # | Milestone | Main outputs | Stop |
| --- | --- | --- | --- |
| 0 | Plain role names and neutral demo data | Data owner, Receiver, Cloud server in app, docs and site; demo data such as "Contract A", "Report Q3"; the story only behind an off-by-default "Teaching names" option in Journey; tests updated | no |
| 1 | Part A: paper conformance | `docs/PAPER_CONFORMANCE.md` (every definition, algorithm, theorem, leakage statement: requirement, code, test, verdict); review of PLAN.md D1 to D20 and the wire format; new or stronger tests (correctness, forward privacy, Type-II backward privacy, verifiability per tamper type, scope, update authenticity, R and RE with collusion, a recorded leakage profile compared with the paper's leakage function) | **yes: you decide each deviation** |
| 2 | Server program | `pqsse-server` package and exe, TLS and pinning, admin port and CLI (status, storage, connections, rotate token, backup, delete group), limits and rate limits, WAL store, blobs, `--check`, backup and restore, Dockerfile and compose, unattended key loading | no |
| 3 | Client modes and joining over the network | first-run mode choice; HTTPS client with timeouts, retries with backoff, resumable large downloads, offline state, clock-skew check; invite design note (**stop for approval** before the Join message changes), then invites | yes, for the invite note |
| 4 | Network tests | three processes over TLS on loopback; server in Docker with clients on the host; fault injection (drops, delays, restart mid-batch, crash during join, full disk, corrupt store, skew, wrong pin, expired and replayed invite, concurrent search and update, large documents and results); abuse (oversized and malformed bodies, slow clients, floods, wrong and revoked credentials, admin from a non-local address) | **yes: you try it on separate machines** |
| 5 | Part C: liboqs default, key lifecycle | liboqs built in CI and bundled; fallback warning; measured speedups (sign, verify, encapsulate, decapsulate) and rerun benchmarks; change passphrase, encrypted key backup and import, auto-lock, best-effort wiping, ACLs on key files, server key handling documented and tested | **yes, before any protocol change** |
| 6 | Part D | design notes for: group access change without revocation, more than one owner, large collections, export and import, owner activity log (**stop for approval**); then build items 3, 4 and 5 | yes, for the notes |
| 7 | Part E | `THREAT_MODEL.md`, review checklist and `SECURITY_REVIEW.md` (my own review, not an audit), TLS configuration test, `pip-audit` and an SBOM, fuzzing (Hypothesis) of wire parsers and document and PDF import, signing research update, reproducible build comparison, clean-machine tests, docs and site updated from regenerated facts (site not pushed before your yes) | yes, before pushing the site |
| 8 | Final report | what works across machines and how to run it, conformance verdicts, measurements, what was not verified, what you must decide or set up, what belongs in the paper's future work | |

Every milestone ends with all tests green (the existing suite, smoke tests, installer tests and the
new ones) and a commit on `reallife`. Nothing is pushed, merged into `master` or published without your yes.

## 5. Risks and open questions

- **The paper and the code may differ in ways that matter** (D6, D7, D9 already differ in form). M1
  decides; until then nothing in the scheme changes.
- **liboqs on Windows** without a local compiler depends on the CI build working; if `liboqs-python`
  changes its loading, the fallback stays default until it is fixed. Constant time is claimed only as
  far as liboqs documents it for that build.
- **The standard library server under load**: fine for a small group; the abuse tests will show the
  limits, and the docs will say to put a reverse proxy in front when it faces the internet.
- **Clock skew**: Join timestamps, token timestamps and the freshness window all need clocks that
  roughly agree. The skew check warns; it cannot fix a wrong clock.
- **Separate-machine testing** needs you (two or three PCs or VMs on one network, a firewall rule for
  the server port that you allow yourself).
- **Two sessions in one project**: the site session works on `master` in the OneDrive folder; this work
  goes to the `reallife` worktree, so merging M0 changes into the site is a later, explicit step.
- **Scope**: Parts B to E are large. I will report honestly where a milestone runs long rather than cut tests.

## 6. What I need from you

1. Your yes (or changes) to this plan, especially R1 (separate worktree and branch), R2 (paper kept out
   of git), R3 (role names replace the lesson cast on the new site), R4 (stdlib server with TLS) and R13.
2. Later: start Docker Desktop when M2 needs it; tell me where VirtualBox is, or switch on Windows Sandbox;
   machines for the M4 test.

## 7. Decisions made during the milestones

| # | Decision | Why |
| --- | --- | --- |
| M0-1 | The roles are shown as Data owner, Receiver (Receiver A and Receiver B in the practice area) and Cloud server. In running text "the cloud" stays as the common noun for the server, as in the paper | Plain, and the paper's own term |
| M0-2 | Internal ids that never reach the screen keep their names (the role key `alice`, variables such as `ctx.bob`); every displayed name goes through `pqsse/roles.py` (`display`). The demo receivers' user ids are now `receiver-a` and `receiver-b` | Small, safe change; one place decides what is shown |
| M0-3 | "Teaching names" (Journey, off by default, saved in settings) is a display filter: a fixed list of plain phrases is shown with the cast's names. Labels, lesson, challenges, narrator, Step Inspector, glossary and Security Lab texts pass through it; ids, data and the protocol do not change | One source of text, no second copy of every string |
| M0-4 | Demo data: groups Finance and Legal; documents such as "Invoice 1042, server hardware", "Contract A", "Report Q3"; the search word stays "invoice" so the lesson's checks are unchanged | Brief: neutral demo data |
| M0-5 | Historical plan documents (PLAN.md, SPATIAL_PLAN.md, LEARN_PLAN.md, RESTYLE_PLAN.md, WEB_PLAN.md) keep their original wording; user documents (README, START_HERE, cheatsheet, concepts), the site and the feature inventory use role names | Plans are records of what was decided then |
| M0-6 | The site text on this branch (Home, How it works, Features, the lesson section) uses role names, and the app screenshots were retaken. The site session on `master` still has the cast; merging the two is a later, explicit step | R3 |
| M1-1 | Conformance decisions accepted: P-01, P-02, P-06 changed in the code (design note 001); P-03 keeps the doubling with a 4,096-record default; P-04, P-05, P-07, P-08 are paper text changes (`docs/PAPER_CHANGES.md`) | Your "Accept all" |
| M1-2 | Milestone 5 also adds a benchmark harness with classical baselines (X25519/Ed25519, ECDH/ECDSA P-256, RSA-2048 from `cryptography`) next to liboqs, so the paper's tables can be reproduced from this repository; Table I counts are aligned there | P-07, P-08 |
| M2-1 | The server is a new package `pqsse/server/` around the unchanged `CloudCore`; the local child-process server (`pqsse/cloud/server.py`) stays for the desktop app's Local demo mode | No protocol change; the teaching mode keeps working |
| M2-2 | Documents are stored as content-addressed files (`blobs/ab/<sha256>`), the database keeps a reference; reads check the hash, `check` lists missing, damaged and unreferenced files. The local demo store keeps documents in SQLite as before | Brief: blob directory, integrity checks |
| M2-3 | Clients pin the server certificate's SHA-256 and check it in `connect()` before sending anything; CA verification is off on purpose because the pin is the stronger check. The admin port is plain HTTP on 127.0.0.1 with a token file readable by the operator's account | No public CA needed; admin never leaves the machine |
| M2-4 | Not changed (protocol, for the threat model in milestone 7): `join_post`, `join_list` and `mail_get` need no authentication, so anyone who can reach the server can post join requests, list pending ones (names and public keys) and fetch sealed mail. The rate limits apply; the invite design (milestone 3) addresses who may post joins | Rule 2 |
| M2-5 | The Docker image (219 MB, python:3.11-slim, non-root uid 10001, read-only root, no capabilities) is built and tested end to end by `scripts/docker_e2e.py` with Docker 28.1 on this PC; the Windows console exe is built by `build_server.ps1` and smoke-tested as a separate process | Tested here; another machine is milestone 4 |
| M3-1 | Client modes are a `use` setting (`demo`, `owner`, `receiver`); the networked modes keep their data in the `network` subfolder, apart from the demo; the guided lesson always runs locally with its own cloud, whatever the mode | Real keys never mix with the demo's |
| M3-2 | Until design note 002 is approved, a networked client connects by typing the server address, port, certificate fingerprint and (recommended) server key fingerprint; the owner's `owner.pqpub` reaches the operator and the receivers by hand | No protocol change before approval |
| M3-3 | Retransmission: the exact last accepted message is refused as `duplicate` (never applied twice, still visible as a refused replay); the owner treats its own `duplicate` as accepted. The HTTPS client retries 4 times with backoff and jitter, honours Retry-After, and never retries a wrong pin, 403 or 413 | Lost replies must not desynchronise the owner and the server |
| M3-4 | Design note 002 approved (A to D) with two changes: two keys derived from the one-time code (one checked by the server, one by the owner, so the server cannot forge the owner's proof) and a self-written 256-word list for fingerprint words | The user's approval, 2026-11-18 |
| M3-5 | Invites are single use, expire after 7 days by default, and the `.pqinvite` file never holds the code; the code goes by a second channel. Expiry travels in milliseconds because the wire format has no floats | A leaked file alone cannot join |
| M3-6 | Listing join requests needs the owner's signature and fetching mail needs the receiver's, each over a timestamp within the clock window; `owner_pub` is public so a receiver can check it against the invite | Closes endpoints that leaked who asked to join and who has mail |
| M3-7 | Documents download in 4 MiB parts; the parts received so far are kept in the receiver's encrypted vault and a broken download resumes; the owner's signature is checked over the whole ciphertext only | Large files over a weak network, without weakening the check |
| M4-1 | An exact resend of a stored join request is refused as `duplicate` (the M3-3 rule), and the receiver counts it as sent; a new request on a used invite stays `invite_used` | A lost reply to a join made the automatic retry fail with "invite already used" |
| M4-2 | The server rolls back the database on any failure, not only on refusals, and deletes document files only after the commit; a failed file write leaves no partial file | A full disk during a policy RE rebuild deleted files the rolled-back database still needed |
| M4-3 | The owner marks a group `reset_pending` before the policy RE rebuild and finishes it before the next change or publish of that group (or with `resume_pending()`); same messages, no protocol change | Without it, a failed rebuild left the owner unable to update the group (`bad_reset`) |
| M4-4 | Network tests on one PC: `scripts/network_e2e.py` (server, owner and receiver as separate processes, every step a fresh process, server killed and restarted), `tests/test_m19_network_faults.py` (faults and abuse) and `scripts/docker_e2e.py`. Across machines: `docs/MULTI_MACHINE_TEST.md`, run by you | Separate machines need your hardware and your firewall rule |
| M5-1 | The native post-quantum code is OpenSSL's ML-KEM and ML-DSA through `cryptography` 50.0.2 (OpenSSL 4.0.3 in its wheels), not a liboqs build in CI as R11 planned. liboqs stays supported (`PQSSE_PQ_BACKEND=oqs`, or when OpenSSL lacks the algorithms) | Already a pinned dependency on Windows, Linux and in Docker; no compiler or CI build needed; byte-compatible with the pure Python code in every direction (tested). It changes no protocol bytes |
| M5-2 | New private keys are stored as their FIPS seed (ML-KEM d || z, 64 bytes; ML-DSA xi, 32 bytes): OpenSSL loads private keys only from seeds. Expanded keys from version 0.1 keep working on the pure Python code. ML-KEM-512 (no OpenSSL support) also stays pure Python | No migration; old vaults open unchanged |
| M5-3 | No cache of expanded private keys: native decapsulate and sign derive the key from its seed on each call (about 0.2 ms) | Keeps private key material in memory as briefly as Python allows |
| M5-4 | Key files (vaults, server store, `server.key`, admin token, key backups) are made readable by their account only: icacls on Windows (no admin rights), 0600/0700 elsewhere | Other ordinary accounts on the same computer |
| M5-5 | Key backup: one `.pqkeys` file, scrypt N = 2^17 and AES-256-GCM under a separate passphrase of 12 or more characters, never imported over existing keys; passphrase change re-encrypts in one transaction; vault master key held in a bytearray and overwritten on close and on a wrong passphrase (best effort) | Part C brief |
| M5-6 | Auto-lock after 15 minutes without an action (setting; 0 = off), plus a Lock button | Part C brief |
| M5-7 | No protocol change was needed in milestone 5, so there is no stop for one. Restoring an owner backup older than the server's state is a known gap, documented in `docs/KEYS.md`, for the Part D notes | Rule 2 |
| M6-1 | Part D design notes written: 003 group access change, 004 more than one owner, 005 large collections, 006 export, import and owner recovery, 007 owner activity log. Waiting for your decision on each; nothing of Part D is built yet | Rule 2 and the M6 stop |
| M6-2 | Measured before proposing (native backend, ML-KEM-768 with ML-DSA-65): every search downloads the whole padded state (2.9 MB at 50,000 keywords); a 20,000-hit result is 0.74 MB; BuildIndex is about 1.2 ms per document | Numbers in note 005 |
| M6-3 | You approved all five notes (recommended options), 2026-11-18. Built in M6: 005 A and B, 006 A and B, 007. Approved for a later milestone: 003 (grant and take away groups), 004 A (several owners on one server), 006 C (recovery from an old owner backup) | Your decision |
| M6-4 | The write-ahead journal has channels (`ctl`, and `group:<g>` per group) instead of one record, and pending rotations live in the owner record, so a batch stuck at the server never blocks a revocation, and new documents never go under a key a revoked receiver holds | Found while building note 006 B |
| M6-5 | An interrupted, split RE rebuild remembers the documents still to send (`rebuild_rest`) | Without it, a crash after the reset batch would lose the rest |
| M6-6 | Activity log entries are written right after the action commits, not in the same transaction; a crash in between loses that one entry | Simpler and safer than merging two kinds of commit |
