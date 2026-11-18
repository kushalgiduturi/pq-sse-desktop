# Release notes: PQ-SSE Desktop 0.2.0

The networked release: a separate server program, the app as a data owner or a receiver on
different computers, invites, native post-quantum code, and the key handling that real use needs.
This release **changes the protocol** (design notes 001 to 006 in `docs/design-notes/`): a 0.2 app
and a 0.1 app cannot talk to each other. Data made by 0.1.x opens and keeps working in 0.2.0 (see
"Upgrading"). Notes of earlier releases: `docs/release-notes/`.

## What is included

| File | What it is |
| --- | --- |
| `PQ-SSE-Web-Setup.exe` | Web installer: downloads the right package for this PC and checks it |
| `PQ-SSE-Desktop-Setup-0.2.0.exe` | Installer, Standard build (CPU) |
| `PQ-SSE-Desktop-0.2.0-portable-standard.zip` | Portable folder, Standard build |
| `PQ-SSE-Desktop-Setup-0.2.0-GPU.exe`, `PQ-SSE-Desktop-0.2.0-portable-gpu.zip` | GPU build (added after its self-test on a PC with an NVIDIA GPU) |
| `PQ-SSE-Server-0.2.0-windows.zip` | **New**: the cloud server as a Windows console program, with `SERVER.md` |
| `latest.json`, `*.issig`, `SHA256SUMS.txt` | Signed file list, signatures (ECDSA P-256, not Windows code signing) and checksums |

The server also runs from source (`python -m pqsse.server`) or in Docker
(`docker compose -f docker/docker-compose.yml up`, built from the repository; no image is published).

## New

- **Across computers.** A server program with TLS 1.2 or 1.3 and a pinned certificate, an operator
  interface on the server's own machine, limits on size, rate and connections, backup and restore. The app
  has three modes: Local demo (as before), Data owner and Receiver. See `docs/SERVER.md` and
  `docs/MULTI_MACHINE_TEST.md`.
- **Invites.** The data owner makes an invite for one person. The `.pqinvite` file or link carries the
  server's address and fingerprints, and a one-time code goes by a second channel. Both sides compare six
  fingerprint words before approval. Join requests, the list of requests and each receiver's mail are now
  closed to everyone else.
- **Native post-quantum code.** ML-KEM and ML-DSA run in OpenSSL (through `cryptography`) by default:
  17 to 76 times faster than the pure Python code. A search with all checks takes about 8 ms instead of
  about 70 ms on the test laptop. ML-KEM-512 and keys made by 0.1.x still use the pure Python code.
- **Keys and passphrases** (Insights): change a passphrase, back up keys to an encrypted file, restore
  them on another computer, lock them now. The keys also lock after 15 idle minutes. Key files are
  readable by your Windows account only.
- **Change a person's groups** without revoking them. Groups that are taken away get new keys.
- **Activity log** of every data owner action, with the server's answer. Hash-chained and kept in the
  encrypted key file, with CSV export.
- **Export and import a group** as one encrypted `.pqgroup` file.
- **Recovery.** The data owner's app finishes interrupted work after a crash. "Recover after restoring a
  backup" rebuilds the owner's state from the server after an older key backup is restored.
- **Large collections.** Large imports are sent in batches. A receiver downloads a group's state again
  only when it changed (2.9 MB instead of 8.7 MB for three searches at 50,000 keywords).
- **Several data owners on one server** (`pqsse-server pair-owner FILE --add`), each in its own store.

## Changed

- **Closer to the paper** (`docs/PAPER_CONFORMANCE.md`): search answers are encrypted to the receiver;
  control messages are sealed to the server; a revoked credential is erased at the server.
- New private keys are stored as their FIPS seeds. Document keywords now travel inside each document's
  encryption, so a receiver who can open a document sees its keywords.
- Document and PDF import refuses files over 50 MB and PDFs over 2,000 pages, and turns a damaged file into
  a plain message.
- The builds are reproducible: two builds of the same commit on one PC give identical files.

## Upgrading

Installing 0.2.0 over 0.1.x keeps your data, and the local demo's data opens as before. Tested by making
data with the 0.1.1 code and opening it with 0.2.0. Search, open, add, publish, groups, grants, the log and
revocation all worked. The first time the data owner's keys are opened, the app stores recovery copies of
its existing group keys at the cloud, once.

## Tested on

The development PC (Windows 11 Insider 10.0.26300, Intel Core i7-13620H, RTX 4060 Laptop GPU), 2026-11-19:
336 tests; the server smoke test; three-process network test with the server killed and restarted; the
server in Docker; fault and abuse tests; fuzzing (Hypothesis); TLS configuration probes; `pip-audit` (no
known vulnerabilities); portable test; installer test with upgrade and uninstall; web installer real run.
GitHub Actions repeats the build, the tests and the installer tests before publishing.

## Not verified

- **Separate computers on a real network.** Everything ran on one PC (`docs/MULTI_MACHINE_TEST.md` is the
  test to run).
- **A clean PC** without Python, Windows 10, ARM64, other GPUs, older drivers.
- **Independent review.** `docs/SECURITY_REVIEW.md` is the author's own review, not an audit.
  `docs/THREAT_MODEL.md` says what is protected and what is not.
- **Constant-time behaviour** of the native code (OpenSSL's claim). The pure Python fallback is not
  constant time.
- **Post-quantum TLS.** TLS key exchange is classical. The data inside is protected by ML-KEM and ML-DSA,
  but traffic metadata only by classical TLS.
- **Code signing.** The files are not code signed.
- **The server under real load.** It is meant for small groups; put a reverse proxy in front of it if it
  faces the internet.
- **This release's own files on a real PC.** They are built by GitHub Actions. Nobody has installed the
  published files by hand yet.
