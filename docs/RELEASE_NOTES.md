# Release notes: PQ-SSE Desktop 0.1.0

First packaged release. Until now the app could only be run from source with Python.

## What is included

| File | What it is | Size |
| --- | --- | --- |
| `PQ-SSE-Desktop-Setup-0.1.0.exe` | Installer, Standard build (CPU) | about 46 MB |
| `PQ-SSE-Desktop-Setup-0.1.0-GPU.exe` | Installer, GPU build | about 115 MB |
| `PQ-SSE-Desktop-0.1.0-portable-standard.zip` | Portable folder, Standard build | about 66 MB |
| `PQ-SSE-Desktop-0.1.0-portable-gpu.zip` | Portable folder, GPU build | about 180 MB |
| `SHA256SUMS.txt` | Checksums of the four files above | |

Installed size: Standard about 170 MB, GPU about 370 MB.
The exact checksums are in `SHA256SUMS.txt`; they change with every build.

New in the program:

- Installer: per-user by default (no admin rights), Start Menu entry, optional desktop
  shortcut, entry under "Installed apps", upgrade in place, uninstaller that asks before
  touching your data and keeps it by default.
- The cloud part can no longer be left running by accident: it ends whenever the app ends.
- Help menu: **About** (version, backend, GPU status, data folder, licenses),
  **Open data folder**, **Open log folder**.
- Log file with rotation: `%LOCALAPPDATA%\PQ-SSE-Desktop\logs\app.log` (1 MB, 3 older files kept).
- App icon and Windows version information.
- Command-line checks without a window: `--smoke-test`, `--gpu-selftest`, `--version`.
- GPU build that needs only an NVIDIA driver. It ships the CUDA 12.0 run-time compiler
  (NVRTC), the CUDA runtime DLL and headers (50 MB) and does not use a CUDA Toolkit even
  if one is installed.

No protocol, wire format or cryptography change.

## The two builds

- **Standard**: runs on the CPU. No graphics chip is used.
- **GPU**: the same program plus CuPy 14.2 and the bundled CUDA compiler. With a usable
  NVIDIA chip it speeds up the symmetric batch work when a large index is built. It does
  not speed up ML-KEM or ML-DSA. Without a usable chip, or with `PQSSE_FORCE_CPU=1`, it
  runs on the CPU and says why.

Both use the pure Python post-quantum backend (kyber-py, dilithium-py), which is slow and
not constant time. This is research and teaching software, not audited.

## Tested on

One machine, the development PC:

| | |
| --- | --- |
| Windows | Windows 11 Home Single Language, version 10.0.26300 (an Insider preview build) |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU, 8 GB |
| NVIDIA driver | 610.62 |
| Python used for the build | 3.11.9 |
| Build tools | PyInstaller 6.22.3, Inno Setup 6.7.3 |

What `build_release.ps1 -WithGpu` ran and passed there, on 2026-11-15:

- The pytest suite: 125 passed.
- For each of the two builds, on the built `PQ-SSE-Desktop.exe`:
  - scan of the build folder: no database, key, settings or pairing file;
  - `--smoke-test`, 14 steps, also with `PQSSE_FORCE_CPU=1`: the real cloud child process,
    Setup, Join, BuildIndex, Publish, TokenGen, Search, Verify (8 checks), Decrypt,
    update, Revoke; the cloud listens on 127.0.0.1 only; the cloud database holds no
    plaintext word; the install folder is not written to.
- GPU build: `--gpu-selftest` with the CUDA Toolkit removed from PATH and CUDA_PATH:
  8,611 digests equal to `hashlib` and `hmac`, 0 mismatches. The NVRTC library loaded by
  the process was the bundled one. Measured speedup of the raw PRF batch:
  about 100 times faster than the CPU at 65,536 messages, about 25 times at 4,096, and slower than the CPU at 64.
- Each portable zip: unzipped into a folder with spaces and non-ASCII characters, with a
  simulated user profile path containing non-ASCII characters: smoke test passed, the
  real window opened, the log file was written, nothing was left running, no firewall
  rule appeared.
- Each installer: silent per-user install without admin rights into a path with a
  space, over a running older install (0.0.1, with the app window and a cloud process
  open): both were closed, files replaced, stale file removed; Start Menu entries and the
  uninstall entry present and correct; smoke test from the installed location passed;
  the installed app opened its window; silent uninstall while the app was running removed
  the folder, the shortcuts and the uninstall entry and left the user data folder untouched.

## Known limits found by the tests

- **GPU build, Windows user name or folder with non-ASCII characters.** When the path of
  the user profile contains characters such as accented or Japanese letters, the NVIDIA
  run-time compiler cannot open its work files and the GPU engine is not used. The app
  then runs on the CPU, says so, and everything else works (the portable test ran exactly
  this case: smoke test passed on the CPU). This is not fixed in this release.
- **The About dialog and the self-test show "CUDA runtime 12.9"** on the test PC. That is
  the CUDA version the installed driver reports, not the version of the bundled compiler (12.0).

## Not verified

Please read this list before giving the files to someone.

- **A clean PC without Python.** Everything ran on the development PC, which has Python,
  the CUDA Toolkit and Visual C++ runtimes installed. The build bundles its own Python and
  runtime DLLs, and the GPU test hid the Toolkit, but no machine without them was available.
- **A PC without an NVIDIA GPU, and a PC without an NVIDIA driver.** The fallback to the
  CPU was tested only by forcing it (`PQSSE_FORCE_CPU=1`) and with the Standard build. The
  message for a missing driver was not seen on a real machine.
- **Older NVIDIA drivers.** Only 610.62 was tested. NVIDIA states 528.33 or newer for the
  bundled CUDA 12.0 Update 1 compiler. Whether the oldest such driver really works was not tested.
- **Other GPUs.** Only the RTX 4060 Laptop GPU.
- **Windows 10**, and a regular (non-preview) Windows 11. Only one Windows 11 Insider build.
- **ARM64 Windows.** The build is x64 only. Not tried under emulation.
- **A real Windows account with a non-ASCII name.** Simulated through environment
  variables only.
- **The installer's pages clicked by hand**: welcome, license, "for me only / for all
  users", the desktop shortcut option, "Launch" at the end. Only silent installs were run.
- **Install for all users** (the elevated path into Program Files). Not run: it needs admin rights.
- **The uninstaller's question "delete your data too?"** and its Yes answer. Only the
  silent uninstall (data always kept) is tested automatically.
- **Start Menu and "Installed apps" as seen in the real Windows shell.** The build session
  ran inside an app container that redirects per-user folders and registry, so the
  installer test checked the entries in that view. Run `scripts\test_installer.ps1` from a
  normal PowerShell window to repeat it for real.
- **SmartScreen and antivirus behavior.** The files were never downloaded through a
  browser on another PC, and no antivirus other than the one on the development PC saw them.
- **Code signing.** The files are unsigned. The `-SignCert` option of the build script was
  never run: there is no certificate.
- **The GitHub Actions workflow** (`.github/workflows/release.yml`). Written, never run:
  the project has no GitHub remote.
- **Long sessions and large data in the packaged app.** The smoke test uses 9 small documents.
- **Third-party files inside `_internal`** were shipped as they come. They were not
  reviewed line by line; only the license collection was cleaned of long dashes.
- **Reproducible bytes.** Versions are pinned, but two builds do not give identical
  files (time stamps), so checksums differ between builds.
