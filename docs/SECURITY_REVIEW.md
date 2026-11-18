# Security review (milestone 7)

The author's own review of branch `reallife`, done with the checklist below, the threat model
(`docs/THREAT_MODEL.md`), property-based fuzzing and the existing tests. **This is not an audit.** Nobody
independent has reviewed the code, the scheme or this document. Read the findings as "what one careful pass
found and fixed", not as "what is left".

Date: 2026-11-18. Scope: `pqsse/` (core, owner, receiver, cloud, server, transport, invites, backend, key store,
import), `app/session.py`, `app/spatial/bridge.py`, `app/update_check.py`, the build and Docker files.
Not reviewed line by line: the QML screens, the Learn mode lesson text, the benchmark and site scripts.

## 1. Checklist

| Area | Checked | Result |
| --- | --- | --- |
| Who may call each endpoint | every public endpoint against the table in section 2 | as designed |
| Input parsing | the wire decoder, invites, every endpoint, server replies at the receiver, document and PDF import: Hypothesis fuzzing (`tests/test_m28_fuzz.py`), 14 tests, run 9 times with fresh random inputs | 4 findings, fixed (SR-01, SR-04, SR-05, SR-06) |
| Resource limits | request bodies, connections, rate, slow clients (server); reply size and download progress (client); file and PDF size (import) | 3 findings, fixed (SR-01, SR-02, SR-03) |
| Cryptographic use | randomness only from `os.urandom` (the `random` module only for simulations and retry jitter); AES-GCM with fresh 96-bit nonces and associated data naming the record; HKDF labels separate every key; every signature has a domain label (`pqsse/v3/sig/<label>`); secret comparisons with `hmac.compare_digest` | 1 finding, fixed (SR-07) |
| Secrets at rest | vaults, server store, `server.key`, admin token, backups, exports: encrypted where they hold secrets, private file permissions | as designed (`tests/test_m21_keys.py`) |
| Secrets in logs and replies | `grep` of every logging call; admin replies searched for document words; secret scan of the builds | none found |
| Error handling | every refusal is a short reason; unexpected errors are 500 without details; the store rolls back on any failure | 1 finding, fixed (SR-06) |
| Dangerous calls | `eval`, `exec`, `pickle`, `marshal`, `shell=True`, SQL built from input | none (the two f-string queries use fixed table names) |
| TLS | versions, cipher suites, compression, renegotiation, certificate: probed from outside (`tests/test_m29_tls_config.py`) | as designed: TLS 1.2 and 1.3, ECDHE with AES-GCM or ChaCha20 only |
| Dependencies | `pip-audit` of `requirements-lock.txt`, `requirements-lock-gpu.txt`, `requirements-server.txt`; SBOM (`docs/SBOM.cdx.json`, `scripts/make_sbom.py`) | no known vulnerabilities on 2026-11-18 |
| Build | secret scan of every build; two builds of the same commit compared file by file (`scripts/repro_compare.py`) | 1 finding, fixed for the server build (SR-08) |
| Updates | the update check and web installer check SHA-256 and the Inno Setup signature (ECDSA P-256) before running anything | as designed (`tests/test_m13_update_check.py`) |

## 2. Who may call what

| Endpoint | Caller | How the server checks |
| --- | --- | --- |
| `pub`, `info`, `owner_pub`, `GET /v1/time` | anyone | public data only |
| `join_post` | a receiver with an invite | its signature over the request; the invite registered, unexpired and unused; HMAC proof under `k_server` |
| `join_list`, `owner_sync`, `owner_doc` | the data owner | ML-DSA signature over the request with a timestamp inside 300 s |
| `ctl`, `update`, `state_put` | the data owner | ML-DSA signature; sequence numbers; `duplicate` for exact resends |
| `mail_get` | one receiver | that receiver's signature (key from its join request) over `uid` and a timestamp |
| `states_get`, `search`, `doc_get` | an approved receiver | the request decrypts under its credential `a_u`; not revoked; the group in its scope |
| `admin_*` (port 8444) | the operator | only from 127.0.0.1, with the admin token |

## 3. Findings

Severity is the author's estimate for this application's use (small groups, a server you run yourself).

| ID | Severity | Where | Finding | Status |
| --- | --- | --- | --- | --- |
| SR-01 | Medium | import (`app/common.py`) | Any file size was read and any PDF parsed with no limit; a pypdf error escaped as an unexpected error. A hostile PDF could hang or exhaust the app | **Fixed**: `pqsse/docimport.py` refuses files over 50 MB and PDFs over 2,000 pages, cuts text at 8 M characters and turns every parser error into a plain refusal. Tested and fuzzed |
| SR-02 | Medium | receiver download in parts | A malicious server could answer every part with no data and a large total, so the receiver asked forever | **Fixed**: no progress, or a total over 256 MiB, is refused (`test_a_server_that_sends_no_progress_or_a_huge_total_is_refused`) |
| SR-03 | Low | HTTPS client | Replies were read without a size limit, so a malicious server could make a client hold any amount of memory | **Fixed**: 128 MiB per reply (`test_the_https_client_refuses_an_oversized_reply`) |
| SR-04 | Low | receiver | A malformed document reply escaped as `KeyError` instead of a failed check | **Fixed**: becomes `VerifyError` (found by fuzzing) |
| SR-05 | Low | invites | An invite file with fields of the wrong type (for example `null`) escaped as `TypeError` | **Fixed**: every field's type is checked (found by fuzzing) |
| SR-06 | Low | server core | A request with an identifier of the wrong type (for example a list as `uid`) became a database error and HTTP 500 instead of `malformed`; nothing was applied | **Fixed**: mapped to `malformed` (found by fuzzing) |
| SR-07 | Low | key store | The vault's passphrase check compared keys with `==` | **Fixed**: `hmac.compare_digest`. It only runs on the user's own computer |
| SR-08 | Low | builds | Two builds of the same commit differed: file order (Python's hash seed) and the build time in the program header | **Fixed for the server build**: `PYTHONHASHSEED=0` and `SOURCE_DATE_EPOCH` (the commit's time). Two server builds are now identical in all 123 files (`docs/measurements/reproducible-server.md`). The desktop build: section 5 |
| SR-09 | Info | local demo | The desktop app starts its local demo cloud with the cloud passphrase in the child process's environment, which other programs of the same account can read | Accepted: the local demo is for learning, on one PC, under one account. The networked server reads its passphrase from a file |
| SR-10 | Info | documents | Since design note 006 C the keywords travel inside each document's encryption, so a receiver who can open a document sees the owner's explicit keywords for it | Accepted (decision M6-9) |
| SR-11 | Info | TLS | TLS key exchange is classical | Accepted and documented (threat 13): the data inside is protected by ML-KEM and ML-DSA |
| SR-12 | Info | backend | The pure-Python fallback is not constant time | Documented; the app, the server and the logs warn when it is used |

Found earlier by the milestone 4 and 6 tests and fixed then (listed for completeness): the server's rollback on
non-protocol errors and the deletion of document files before commit (M4-2), the lost reply to a join (M4-1),
an interrupted RE rebuild (M4-3), a stuck batch blocking a revocation (M6-4).

## 4. Not done, and why

- **No independent review or audit.** It would need someone else.
- **No side-channel testing.** The native code is OpenSSL's; its constant-time properties are the OpenSSL
  project's claims, not checked here.
- **No formal verification** of the scheme or the code; the paper's proofs were not re-checked
  (`docs/PAPER_CONFORMANCE.md`).
- **Fuzzing is property-based in Python, not coverage-guided.** 14 tests, a few hundred inputs each per run.
  pypdf itself was fuzzed only through its file input, with small files.
- **Load testing** beyond the flood test was not done; the standard-library server is meant for small groups.

## 5. Reproducible builds

| Build | Result | Notes |
| --- | --- | --- |
| Server (`build_server.ps1`) | identical, 123 of 123 files | same PC and build environment, two output folders |
| Desktop (`build_windows.ps1`) | 2,126 of 2,127 files identical; the launcher differs in its embedded code archive | open: `docs/measurements/reproducible-desktop.md` |

Bit-for-bit identity was shown on one PC with one Python environment. Identity across PCs needs the same
Python build, the same pinned packages and the same path layout; that was not tested.
