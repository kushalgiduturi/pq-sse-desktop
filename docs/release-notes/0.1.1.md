# Release notes: PQ-SSE Desktop 0.1.1

A distribution release: a small web installer, a signed file list, an update check you start
yourself, a website, and a GPU build that holds only NVIDIA files that may be passed on.
No protocol, wire format or cryptography change. Notes of earlier releases:
`docs/release-notes/`.

## What is included

| File | What it is | Size |
| --- | --- | --- |
| `PQ-SSE-Web-Setup.exe` | Web installer: downloads the right package for this PC and checks it | about 2 MB |
| `PQ-SSE-Desktop-Setup-0.1.1.exe` | Installer, Standard build (CPU) | about 54 MB |
| `PQ-SSE-Desktop-0.1.1-portable-standard.zip` | Portable folder, Standard build | about 82 MB |
| `PQ-SSE-Desktop-Setup-0.1.1-GPU.exe` | Installer, GPU build (added after its self-test, see below) | about 123 MB |
| `PQ-SSE-Desktop-0.1.1-portable-gpu.zip` | Portable folder, GPU build (added with the GPU installer) | about 198 MB |
| `latest.json` | The file list: version, and the address, size and SHA-256 of every file | |
| `*.issig` | Signatures of `latest.json` and of every package | |
| `SHA256SUMS.txt` | Checksums of all files | |

## New

- **Web installer** (`PQ-SSE-Web-Setup.exe`). It reads the signed file list from the website,
  checks its signature against the public key built into it, finds out whether this PC has a
  usable NVIDIA driver, downloads the Standard or the GPU installer, checks its size, SHA-256
  and signature, then installs and starts the app. It follows redirects itself and refuses any
  host that is not on its list. It refuses an unsigned or wrongly signed list and any file that
  does not match. Silent install: `/VERYSILENT`, with `/CHANNEL=standard` or `gpu` and `/DIR=`.
- **Signed file list.** Every release carries `latest.json` and Inno Setup signatures
  (`.issig`, ECDSA P-256) for it and for every package. This is not Windows code signing:
  Windows still shows "Unknown publisher". What it proves and what it does not is on the
  website's Security page and in `docs/DISTRIBUTION.md`.
- **Check for updates**, in Insights > About and in the classic window's About dialog. It goes
  online only when you click it: it reads the signed file list over HTTPS, checks the
  signature, compares versions, and offers the Download page or the web installer. A setting
  hides the button. The app still never goes online on its own.
- **Website**: https://kushalgiduturi.github.io/pq-sse-desktop/ with download, install guide,
  how it works, security and privacy, release notes and a page that checks a download's
  SHA-256 in your browser. No cookies, no analytics, nothing loaded from other sites.

## Changed

- **GPU build: only redistributable NVIDIA files.** The 0.1.0 GPU build carried 888 CUDA header
  files that NVIDIA's license does not let others pass on. This build ships only the files the
  CUDA 12.0 license lists as redistributable (the CUDA runtime and NVRTC DLLs and four headers)
  plus an empty marker file of its own. The build fails if any other NVIDIA file is found.
  The GPU self-test still passes with this set.
- The GPU build is made and self-tested on a PC with an NVIDIA GPU and added to the release
  after the Standard build; GitHub's build machines have no GPU.

## Tested on

The Standard installer, the portable zip and the web installer in this release are built by
GitHub Actions (`windows-latest`), which runs the full test suite, the smoke test of the built
program, the installer test (install, run, uninstall) and a real web-installer install against
a local server before anything is published.

The same steps were run on the development PC (Windows 11 Insider 10.0.26300, RTX 4060 Laptop
GPU, driver 610.62) on 2026-11-18, with the GPU build and a throwaway signing key:

- pytest: 190 passed, 1 skipped (the site's browser check, which needs Qt WebEngine and runs in
  the development environment, where it passes).
- Both builds: smoke test (14 steps); GPU self-test with the CUDA Toolkit hidden.
- Standard installer: silent install, smoke test from the installed place, window opens,
  uninstall leaves the user data.
- Web installer: real install of the Standard package from a local server; WMI reported the
  driver as 610.62. Fake-server tests: wrong hash, swapped file, unsigned list, truncated
  download, redirect to another host, offline, GPU detection.
- The signatures of the file list and all packages were checked a second time by the app's own
  Python code.

## Known limits found by the tests

- **GPU build, Windows user name or folder with non-ASCII characters.** The NVIDIA run-time
  compiler cannot open its work files there; the app then runs on the CPU and says so.
- **The About dialog shows the CUDA version the driver reports** (12.9 on the test PC), not
  the version of the bundled compiler (12.0).

## Not verified

- **This release's own files on a real PC.** They are built on GitHub's machine; the tests
  there run before publishing, but nobody has installed the published files by hand yet.
- **The web installer on a clean PC, behind a proxy, and through a browser download**
  (SmartScreen). Its first real download from GitHub happens with this release.
- **The update check against the live website.** Tested against a local server only.
- **A clean PC without Python, a PC without an NVIDIA GPU or driver, older NVIDIA drivers,
  other GPUs, Windows 10, ARM64.** Unchanged from 0.1.0.
- **The installer's pages clicked by hand, install for all users, the uninstaller's "delete
  your data too?" answer.** Only silent installs are tested automatically.
- **Code signing.** The files are not code signed. No certificate exists.
- **The spatial window used by hand, with a keyboard only or a screen reader.**
- **Reproducible bytes.** Two builds do not give identical files.
