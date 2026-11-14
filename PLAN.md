# PQ-SSE Desktop: build plan

Implementation of MU-PQ-SSE v3 ("PQ-SSE: Integrating ML-KEM into Searchable Symmetric
Encryption: A Three-Party, Multi-User, Dynamic and Verifiable Construction") as a Windows
desktop application with three real parties and a GPU batch engine.

## 1. Environment found on this machine

| Item | Value |
| --- | --- |
| Python | 3.11.9 |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU, 8 GB, driver 610.62 |
| CUDA toolkit | 12.3 (CUDA_PATH set), CuPy 14.2 `RawKernel` compiles and runs |
| PQ backend | `kyber-py` 1.2 and `dilithium-py` 1.5 (pure Python). `oqs` is not installed |
| GUI | PySide6 6.12 (QtCharts included) |
| Virtual env | `%USERPROFILE%\.venvs\pqsse` (kept outside OneDrive on purpose) |

## 2. Architecture

Three components, no shared in-memory state. They exchange only wire messages
(`pqsse.core.wire` canonical binary encoding), either in process (tests, benchmarks)
or over HTTP on 127.0.0.1 (the app).

```
pqsse/
  pqbackend.py        ML-KEM / ML-DSA abstraction (oqs preferred, kyber-py/dilithium-py fallback)
  paths.py            %LOCALAPPDATA%\PQ-SSE-Desktop data folder
  core/
    wire.py           canonical encoding, sstr(), u32()
    prims.py          H = SHA3-256, F = HMAC-SHA3-256, HKDF-SHA3-256, AES-256-GCM helpers
    seal.py           seal / unseal: ML-KEM + HKDF + AES-GCM, optional pre-shared key
    signing.py        domain-separated ML-DSA sign / verify helpers
    chain.py          per-keyword hash chain d_i = H(d_{i-1} || a_i || v_i)
    index.py          address / mask message layout shared by owner and receiver
    keystore.py       scrypt + AES-GCM encrypted key-value store in SQLite
    pairing.py        .pqpub export / import
    errors.py         typed errors (VerifyError, Rejected, ...)
  gpu/
    keccak_host.py    tiny host Keccak-f used only to precompute keyed HMAC states
    cuda_kernel.py    CUDA C RawKernel: batched Keccak-f[1600] / SHA3-256 / HMAC-SHA3-256
    batchprf.py       BatchPRF interface: CpuPRF, GpuPRF, auto policy with threshold
    calibrate.py      first-run calibration of the GPU batch threshold
    selftest.py       python -m pqsse.gpu.selftest
  cloud/
    core.py           CloudCore: the server logic and its SQLite store
    server.py         local-only HTTP API (http.server, 127.0.0.1)
    __main__.py       python -m pqsse.cloud
  owner/owner.py      Setup, Join approval, BuildIndex, Update, Publish, Revoke
  receiver/receiver.py  Join request, TokenGen, Verify, Decrypt, rekey handling
  transport.py        CloudAPI protocol: InProcessCloud and HttpCloud
  attacks.py          tampering cloud wrappers and Attack Lab scenarios
  bench.py            benchmark runners (also python -m pqsse.bench)
app/
  main.py             PySide6 window, tabs: Owner, Receiver, Cloud, Attack Lab, Benchmarks, Settings
  workers.py          QThreadPool worker helper
  tab_*.py            one module per tab
tests/                pytest suite, one file per acceptance area
docs/                 architecture.md (Mermaid), wire-format.md
build_windows.ps1     PyInstaller one-folder build
```

## 3. Protocol design (how the 10 algorithms are realised)

Notation: H = SHA3-256, F = HMAC-SHA3-256, `sstr(w)` = u32 length then UTF-8 bytes,
`u32(i)` big endian.

1. **Setup.** Owner: ML-DSA key pair. Cloud: ML-KEM key pair and ML-DSA key pair.
   Each receiver: ML-KEM and ML-DSA key pairs. Public keys travel in `.pqpub` files
   (pair devices step). Each group starts at epoch 1 with random `K_g^1`.
2. **Join.** Receiver signs `(ek_u, vk_u, nonce, timestamp, name)` with its ML-DSA key.
   Owner checks the proof, the timestamp window and nonce reuse, then on approval creates
   `a_u`, `m_u` and a capability with the group keys of all live epochs of the chosen
   groups. The capability is sealed with ML-KEM to `ek_u` and signed by the owner. The
   credential `(uid, a_u, scope)` is sealed to the cloud's ML-KEM key and owner signed.
3. **BuildIndex.** `K_idx, K_doc, K_st = HKDF(K_g^e, label)` with labels idx, doc, st.
   `a_i = F(K_idx, sstr(w) || u32(i) || 0x00)`,
   `v_i = (op || id) XOR F(K_idx, sstr(w) || u32(i) || 0x01)[0:5]`,
   `d_i = H(d_{i-1} || a_i || v_i)`. Documents: AES-256-GCM, random 96-bit nonce,
   AAD `g || e || id`, owner signed. All F evaluations of a batch go through `BatchPRF`.
4. **Update.** Add or delete produces a batch `(g, e, seq, entries, docs, doc_del, reset)`
   signed by the owner. The cloud accepts only `seq = last + 1` for the current epoch.
5. **Publish.** Records `(H(w)[:8], c_w, d_w)` padded to `N_max`, encrypted under `K_st`,
   header `(g, e, version, t_exp, final, base)`, signature over header and `H(ciphertext)`.
6. **TokenGen.** Receiver reads the verified states of all live segments, takes `c_w`,
   derives the address list per segment, and encrypts the token under `a_u`.
7. **Search.** Cloud authenticates the token under `a_u`, checks revocation, scope and
   epoch, returns the stored entries and signs `(H(token), response)` with ML-DSA.
8. **Verify.** State signature, all segments `base..current` present, older segments final,
   current one not final and not expired, version monotonic, cloud signature,
   completeness against `c_w`, hash chain against `d_w`, then unmask and apply add/delete.
9. **Decrypt.** Fetch by handle, verify owner document signature, AES-GCM decrypt with
   the epoch key the receiver holds.
10. **Revoke.** R: deauthorize at cloud, final state for the old epoch, new epoch key,
    rekey boxes sealed with ML-KEM and bound to `m_v`, old segments stay.
    RE: additionally rebuild the whole group under the new epoch in a batch with the
    reset flag, and the cloud drops older segments and documents.

## 4. Milestones

1. Skeleton, `pqbackend`, wire formats, seal/unseal, signing helpers, keystore, tests.
2. All 10 algorithms on CPU, in process, with correctness, tamper, update, state, join,
   scope, revocation and forward privacy tests.
3. Cloud as a separate local HTTP process, encrypted key storage, HTTP tests,
   cloud DB plaintext scan.
4. GPU engine with CPU fallback, self-test, calibration, benchmark script.
5. PySide6 app with all tabs.
6. Attack Lab and Benchmarks tabs, CSV export, charts.
7. `build_windows.ps1`, README, docs, 5 minute demo script.

Each milestone ends with: run its tests, fix, commit, short status.

## 5. Decisions

- **D1 Paper text.** The paper file is not in the project folder, so the construction is
  built from the specification in the request. Where the request is silent, the choice
  is listed here.
- **D2 Virtual env outside OneDrive.** `%USERPROFILE%\.venvs\pqsse`, to avoid OneDrive
  syncing and locking thousands of package files. `requirements.txt` is the source of truth.
- **D3 HTTP server.** `http.server.ThreadingHTTPServer` from the standard library, bound
  to 127.0.0.1 only. No extra dependency, simple to package.
- **D4 Wire format.** One small canonical binary encoding (`wire.enc` / `wire.dec`) for
  every message. Signatures are always over `label || H(enc(message))`.
- **D5 Mailbox through the cloud.** Join requests, sealed capabilities and rekey boxes are
  relayed by the cloud (it only sees sealed and signed blobs). The owner still approves
  each join in the UI after checking the key fingerprint.
- **D6 Capability contents.** "Group keys at their base epoch" is implemented as the keys
  of every live segment (`base..current`) so a new receiver can search existing data.
  After RE the base equals the new epoch.
- **D7 State header.** One extra field `base` (oldest live epoch) next to
  `(g, e, version, t_exp, final)` so the receiver can check "all segments present".
- **D8 Token set.** A token is the explicit list of addresses `a_0..a_{c_w-1}` per segment,
  never a key. This is what gives forward privacy: a later entry for `w` uses index `c_w`,
  which the cloud cannot derive.
- **D9 Document handles.** The cloud stores a document under
  `F(K_doc, "handle" || u32(id))[:16]`, not under the plain id.
- **D10 Edit document** is delete followed by add with a fresh id.
- **D11 Freshness.** `t_exp = publish time + delta` (default 24 h, configurable). The owner
  republishes to refresh. Final states do not expire.
- **D12 Cloud passphrase.** The cloud process reads it from the `PQSSE_CLOUD_PASSPHRASE`
  environment variable (set by the app for the child process) or prompts on the console.
- **D13 Storage.** Owner and receiver keep all state as AES-GCM encrypted records in their
  SQLite file (key from scrypt). The cloud DB has plain tables for ciphertext and
  encrypts its own secret keys and the credentials `a_u`.
- **D14 GPU scope.** Only F (HMAC-SHA3-256) batches and SHA3-256 batches run on the GPU.
  The hash chain is sequential per keyword, so it runs as a batched GPU step across
  keywords only when it pays off, otherwise on the CPU. ML-KEM and ML-DSA stay on the CPU.
- **D15 Charts.** QtCharts (ships with PySide6), no matplotlib in the bundle.
- **D16 Test speed.** The pure Python ML-DSA takes about 35 to 90 ms per signature, so
  the large randomized tests use ML-KEM-512 / ML-DSA-44; one test runs every parameter set.

## 6. Risks

- Pure Python PQ backend is slow for signing. Mitigation: caching of verified states,
  smallest parameter set in bulk tests, `oqs` used automatically when present.
- GPU speedup on small batches is negative (transfer and launch overhead). Mitigation:
  calibrated threshold, honest numbers in the Benchmarks tab.
- Host side message packing in Python can dominate BuildIndex time. Mitigation: NumPy
  fixed-length fast path grouped by keyword length.
- PyInstaller with CuPy is large and fragile. Mitigation: the build script makes the GPU
  bundle optional; the frozen app still runs on CPU.
- Loosely synchronized clocks: all three roles run on one PC here, so clock skew is not
  exercised outside the unit tests that inject a clock.
