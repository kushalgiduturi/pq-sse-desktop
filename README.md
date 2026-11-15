# PQ-SSE Desktop

A working implementation of **MU-PQ-SSE v3** from the paper "PQ-SSE: Integrating ML-KEM into
Searchable Symmetric Encryption: A Three-Party, Multi-User, Dynamic and Verifiable
Construction".

It is a Windows desktop application with three real parties (data owner, receivers,
cloud server), real post-quantum cryptography (ML-KEM, ML-DSA), and a GPU batch engine
for the heavy symmetric work.

## Install (no Python needed)

For people who just want to use the app on Windows 10 or 11 (64-bit):

1. Get `PQ-SSE-Desktop-Setup-<version>.exe` (or the portable zip) from the release folder.
2. Double-click it. If Windows shows "Windows protected your PC", click **More info**, then
   **Run anyway**: the app is not code signed.
3. Choose "Install for me only". No admin rights are needed. Start it from the Start Menu.

Full guide with update, uninstall and troubleshooting: [docs/INSTALL.md](docs/INSTALL.md).
Why the warning appears, checksums, signing: [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md).
What was tested and what was not: [docs/RELEASE_NOTES.md](docs/RELEASE_NOTES.md).

To build the installer and the zip yourself (developers), one command:

```powershell
.\build_release.ps1 -WithGpu
```

The developer setup from source is further down, under "Setup".

## Two windows: spatial (new, default) and classic

`python -m app` now opens the **spatial window**: a dock with five destinations (Journey,
Stage, Workspace, Security Lab, Insights), a Story bar that says in one sentence what is
happening, and a Step Inspector that replays every real step at four levels of detail.
It is under construction: see [SPATIAL_PLAN.md](SPATIAL_PLAN.md) for what is finished.

`python -m app --classic` opens the earlier six-tab window with every feature, including
the Attack Lab, Benchmarks and the full settings, which have not moved to the new window yet.
The packaged build still opens the classic window until its packaging milestone.

## New here? Start with Learn Mode

You do not need to know any cryptography. Start the app and press **Start the guided lesson**
on the welcome screen. Installed app: Start Menu > PQ-SSE Desktop. From source:

```powershell
& "$env:USERPROFILE\.venvs\pqsse\Scripts\python.exe" -m app
```

- **The story.** Alice is a hospital records manager (the data owner). Bob and Carol are
  doctors (receivers). The Cloud is a rented storage company that is not trusted.
- **The idea.** Alice keeps her files locked, yet Bob can still search them through the
  cloud, and the cloud learns almost nothing, even against future quantum computers.
- **The Learn tab** walks through 13 steps on the real system (about 15 minutes), with
  "Do it for me" and "Let me try" for each step. It uses its own practice area, so your
  own data is untouched; every passphrase there is the word `lesson`.
- **The Narrator** on the right says in plain words what just happened, and a small
  diagram shows what travelled between Alice, the doctors and the Cloud.
- **Who sees what** (a page on the Learn tab) puts Alice's view, a doctor's view and the
  Cloud's view of the same data side by side.
- **Beginner Mode / Expert Mode** is a toggle in the toolbar. Press **F1** for the glossary.

Read next: [docs/START_HERE.md](docs/START_HERE.md) (one page, with a FAQ),
[docs/cheatsheet.md](docs/cheatsheet.md) (the ten steps, one sentence each) and
[docs/concepts.md](docs/concepts.md) (analogy, real name, code location).

## What the GPU does, and what it does not

- The GPU accelerates **only the symmetric batch work**: the PRF `F = HMAC-SHA3-256` for
  index addresses and masks, and batched SHA3-256 for hash chain levels.
- **ML-KEM and ML-DSA are per event operations and always run on the CPU.** So do AES-GCM
  document encryption, HKDF, scrypt, and everything inside the cloud server.
- The GPU path is used only after a self-test showed its output is byte for byte equal to
  `hashlib` and `hmac`. If CUDA is missing or the self-test fails, the app runs fully on
  the CPU and says so in the header.

Measured on the development machine (RTX 4060 Laptop GPU 8 GB, driver 610.62, CUDA toolkit
12.3, CuPy 14.2, Python 3.11, pure Python PQ backend, ML-KEM-512 + ML-DSA-44):

| Workload | CPU | GPU | Speedup |
| --- | --- | --- | --- |
| Raw PRF batch, 65,536 messages of 21 bytes | 141.8 ms | 1.29 ms | 110x |
| Raw PRF batch, 4,096 messages | 8.6 ms | 0.47 ms | 18x |
| Raw PRF batch, 64 messages | 0.155 ms | 0.212 ms | 0.73x (GPU slower) |
| BuildIndex 100,000 occurrences, PRF phase | 0.486 s | 0.054 s | 9.0x |
| BuildIndex 100,000 occurrences, PRF + hash chain | 0.623 s | 0.116 s | 5.4x |
| BuildIndex 100,000 occurrences, whole operation | 4.97 s | 4.67 s | 1.06x |
| BuildIndex 10,000 occurrences, whole operation | 0.59 s | 0.39 s | 1.5x |
| BuildIndex 1,000 occurrences, whole operation | 0.11 s | 0.13 s | 0.9x (GPU slower) |

Read this table honestly: the kernel itself is about 100 times faster than `hashlib` on
large batches, but inside BuildIndex the host side message packing limits the PRF phase
to about 9x, and the whole BuildIndex barely changes because one ML-DSA signature per
document (pure Python, about 40 ms each) dominates. With `liboqs` installed the signing
cost drops and the GPU share of the total grows. Run the Benchmarks tab to get the
numbers for your own machine; nothing in the app shows a number it did not measure.

## Setup

Requirements: Windows 10 or 11, Python 3.11 or newer. No admin rights needed.

```powershell
python -m venv "$env:USERPROFILE\.venvs\pqsse"
& "$env:USERPROFILE\.venvs\pqsse\Scripts\python.exe" -m pip install -r requirements.txt
```

The virtual environment is kept outside the project folder because the project lives in
OneDrive, which would otherwise sync thousands of package files. Any location works.

### GPU (optional)

1. NVIDIA driver that supports CUDA 12: version 525.60 or newer (`nvidia-smi` shows it).
2. CuPy for CUDA 12:
   ```powershell
   & "$env:USERPROFILE\.venvs\pqsse\Scripts\python.exe" -m pip install cupy-cuda12x
   ```
3. The CUDA kernel is compiled at run time, which needs the CUDA runtime compiler (NVRTC).
   Either install the CUDA Toolkit 12.x from NVIDIA (this is what was tested: 12.3), or
   install the runtime wheels with `pip install "cupy-cuda12x[ctk]"` (the wheel route was
   not tested here).
4. Verify the GPU:
   ```powershell
   & "$env:USERPROFILE\.venvs\pqsse\Scripts\python.exe" -m pqsse.gpu.selftest
   ```
   It prints the device, the byte for byte comparison with `hashlib` and `hmac`, a CPU vs
   GPU timing table, and `RESULT: PASS` (exit code 0). Exit code 2 means no usable GPU
   (the app still works on the CPU), exit code 1 means the self-test failed and the GPU
   path is disabled.

To force the CPU: set `CUDA_VISIBLE_DEVICES=-1` or `PQSSE_FORCE_CPU=1`, or choose
"CPU only" on the Settings tab.

### Faster PQ backend (optional)

If `liboqs-python` (`oqs`) is importable and passes a round trip it is used automatically;
otherwise the pure Python `kyber-py` and `dilithium-py` are used. The app header shows the
active backend. `liboqs` was not available on the development machine, so that path is
implemented but untested here.

## Run

```powershell
& "$env:USERPROFILE\.venvs\pqsse\Scripts\python.exe" -m app                 # the desktop app
& "$env:USERPROFILE\.venvs\pqsse\Scripts\python.exe" -m pytest tests        # all tests (about 4 minutes)
& "$env:USERPROFILE\.venvs\pqsse\Scripts\python.exe" -m pqsse.gpu.selftest  # GPU self-test
& "$env:USERPROFILE\.venvs\pqsse\Scripts\python.exe" -m pqsse.bench         # benchmarks to CSV
& "$env:USERPROFILE\.venvs\pqsse\Scripts\python.exe" -m pqsse.cloud --port 8765   # cloud server alone
.\build_windows.ps1                                                         # one-folder build, then smoke test of the built exe
.\build_release.ps1 -WithGpu                                                # everything: tests, both builds, installers, zips, checksums
```

The packaged program has three extra flags for checking it without a window. They write
their report to the file given with `--report`:

```powershell
PQ-SSE-Desktop.exe --smoke-test   --report report.txt   # whole protocol against the real cloud child process
PQ-SSE-Desktop.exe --gpu-selftest --report report.txt   # GPU engine against hashlib and hmac, with timings
PQ-SSE-Desktop.exe --version      --report report.txt
```

From source the same flags work with `python -m app` and print to the console.

Data lives in `%LOCALAPPDATA%\PQ-SSE-Desktop` (one SQLite file per role, `pubkeys\`,
`settings.json`). Delete that folder to start from scratch.

## Demo script (5 minutes)

Use any passphrases you like; each role asks for its own.

1. **Cloud tab.** Type a cloud passphrase, press **Start server**. The light turns green
   and the cloud's key fingerprint appears. The server is a separate process on 127.0.0.1.
2. **Owner tab.** Type an owner passphrase, press **Open or create owner**. Press
   **Pair: import cloud key (.pqpub)** and pick `cloud.pqpub`.
3. **Cloud tab.** Press **Pair: import owner key (.pqpub)** and pick `owner.pqpub`.
   The two devices are now paired through public key files.
4. **Owner tab.** Type `research` and press **Create group**. Press **Add document**,
   paste some text (or **Import files** for `.txt`, `.md`, `.pdf`), then press **Publish**.
5. **Receiver tab.** Type the user name `alice` and a passphrase, press **Unlock or
   create**, then **Pair devices**, then **Send join request**.
6. **Owner tab.** Press **Refresh join requests**, select alice, press **Approve selected**,
   tick `research`, OK.
7. **Receiver tab.** Press **Fetch mailbox** (the capability arrives, sealed with ML-KEM).
   Choose group `research`, type a word from your document, press **Search**. All eight
   indicators in the Verification panel turn green and "Fresh until" shows the expiry.
   Click a result to fetch, verify and decrypt the document.
8. **Cloud tab.** Look at the live request log and the "What the server can see" panel:
   only addresses, masked values and ciphertext, none of your words.
9. **Receiver tab.** Create a second user `bob` the same way (steps 5 to 7).
10. **Owner tab.** Select alice under "Approved receivers", choose a policy, press
    **Revoke selected receiver** and confirm. As alice, search again: "Access denied: this
    receiver has been revoked by the data owner." As bob, **Fetch mailbox** then search:
    it still works, in the new epoch.
11. **Attack Lab tab.** Press **Run all attacks**. Each of the 11 demos shows what the
    attacker did and which check caught it, including the R vs RE collusion demo.
12. **Benchmarks tab.** Press **Run BuildIndex benchmark**, then **Export CSV**.

## How this maps to the paper

| Paper algorithm | Code | Notes |
| --- | --- | --- |
| 1 Setup | `Owner.create`, `CloudCore._setup`, `Receiver.create`, `core/pairing.py` | owner ML-DSA key; cloud ML-KEM + ML-DSA keys; `.pqpub` files model authentic public keys |
| 2 Join | `Receiver.join_request`, `Owner.check_join`, `Owner.approve_join`, `CloudCore._ctl_cred`, `Receiver.accept_capability` | ML-DSA proof over a fresh nonce; capability sealed with ML-KEM and owner signed; `a_u` shared with the cloud, `m_u` with the owner |
| 3 BuildIndex | `Owner.build_index`, `Owner._apply`, `core/index.derive`, `core/chain.update_heads` | HKDF labels idx, doc, st; addresses, masks and chain exactly as in the paper; batch goes through `BatchPRF` |
| 4 Update | `Owner.add_document`, `delete_document`, `edit_document`, `CloudCore._h_update` | owner signed, sequence numbered; forged, modified, replayed and out of order batches rejected |
| 5 Publish | `Owner.publish`, `core/state.py`, `CloudCore._h_state_put` | records `H(w)[:8], c_w, d_w` padded to `N_max`, header signed over `H(ciphertext)` |
| 6 TokenGen | `Receiver.search` (first half) | per keyword address set from the capability, encrypted under `a_u` |
| 7 Search | `CloudCore._h_search` | credential, scope and epoch checks; ML-DSA signature over the response |
| 8 Verify | `Receiver._verified_states`, `Receiver.search` (second half) | eight checks, shown one by one in the Verification panel |
| 9 Decrypt | `Receiver.open_document`, `Receiver.decrypt_document` | owner document signature, then AES-256-GCM |
| 10 Revoke R / RE | `Owner.revoke`, `Owner._rotate`, `CloudCore._ctl_deauth`, `_ctl_epoch`, `Receiver._accept_rekey` | R rotates and keeps old segments; RE re-encrypts with the reset flag and the cloud drops older segments |

Security properties and the tests that exercise them:

| Property | Test |
| --- | --- |
| Correctness against a plaintext index (336 queries) | `tests/test_m2_correctness.py` |
| Tamper detection: drop, modify, reorder, truncate, substitute (100 trials each), unsigned response, modified and swapped documents | `tests/test_m2_tamper.py` |
| Update authenticity, state checks (forged, rollback, expired), join, scope, forward privacy | `tests/test_m2_protocol.py` |
| Revocation R and RE | `tests/test_m2_revocation.py` |
| Cloud over HTTP, encrypted key stores, cloud DB plaintext scan | `tests/test_m3_http.py` |
| GPU equals CPU, self-test, CPU fallback with CUDA hidden | `tests/test_m4_gpu.py` |
| App smoke test (offscreen), Attack Lab, Benchmarks | `tests/test_m5_app.py` |

More detail: [docs/architecture.md](docs/architecture.md) (diagram) and
[docs/wire-format.md](docs/wire-format.md) (every message). Design choices that the paper
text does not fix are listed in [PLAN.md](PLAN.md) under "Decisions".

## Known limits

- **Model limit of the scheme.** Scope is per group. Under policy **R**, data written
  before a revocation stays readable by a revoked user who colludes with the cloud (the
  old segment is still stored under the old key). Policy **RE** re-encrypts the group
  and drops the old segments, so it does not have this limit. The Attack Lab and
  `tests/test_m2_revocation.py` show both sides.
- **Built from the specification, not from the paper file.** The paper was not in the
  project folder. Check the items in PLAN.md "Decisions" against the paper, in particular
  D6 (the capability carries the keys of all live segments), D7 (the state header has an
  extra `base` field) and D9 (documents are stored under a PRF handle).
- **Freshness** relies on loosely synchronized clocks and a window delta (default 24
  hours, Settings tab). Within the window a cloud can serve the latest state the receiver
  has not yet seen superseded. The owner must republish before expiry.
- **Leakage** is the usual one for this class of schemes: the cloud sees which addresses
  are queried together (search pattern, result size), batch sizes and timing. The state
  is padded to `N_max` (grows by doubling); tokens and batches are not padded.
- **Pure Python PQ backend** is slow (ML-DSA signing about 35 to 90 ms) and not constant
  time. It is also not thread-safe on its own; the backend serializes calls with a lock.
  Use `liboqs` for anything beyond a research demo.
- **Local demo deployment.** The cloud listens on 127.0.0.1 only, without TLS. Operator
  endpoints (log, statistics) need a token that the app passes to its child process.
  `a_u` is stored at the cloud wrapped under the cloud passphrase key.
- **Single owner, no capability update.** A receiver's group list is fixed at approval;
  to change it, revoke and approve a new join request.
- **Not audited.** This is research software. Do not use it to protect real data.

## Not verified by the author of this build

- `liboqs-python` backend (not installed on the development machine).
- The packaged builds are now tested by the build itself (smoke test, GPU self-test,
  installer test). What is still unverified for them is listed in
  [docs/RELEASE_NOTES.md](docs/RELEASE_NOTES.md) under "Not verified": a clean PC without
  Python, a PC without an NVIDIA GPU, Windows 10, older drivers, code signing.
- Any GPU other than the RTX 4060 Laptop GPU, and CuPy builds other than `cupy-cuda12x`.
- The app was exercised through the offscreen test; visual layout on screen was not reviewed.
