# Release checklist

Everything public (the repository, a release, the website, winget) is done by you with the commands
below. The scripts build, test and prepare; none of them publishes on its own, and none stores a
token or password (`gh auth login` keeps the GitHub sign-in in Windows' credential store).

## Placeholders and known gaps

- **SmartScreen picture.** The install guide shows a *drawing* of the "Windows protected your PC"
  window, captioned as a drawing. A real screenshot needs a file downloaded through a browser on a PC
  that has not seen it; take one after the first release with the web installer and replace the
  drawing (`SMARTSCREEN_SVG` in `scripts/build_site.py`).
- **App screenshots** on the website are real, from the restyled app (`docs/design/restyle/after/`).
- **Release v0.1.0** has only the two full installers, no `latest.json`, no signatures and no web
  installer, and its GPU installer holds NVIDIA headers that may not be redistributed (see
  `docs/DISTRIBUTION.md`). Recommended: publish **v0.1.1** through the workflow below rather than
  editing v0.1.0, then decide whether to delete v0.1.0's GPU file:
  `gh release delete-asset v0.1.0 PQ-SSE-Desktop-Setup-0.1.0-GPU.exe --repo kushalgiduturi/pq-sse-desktop`

## One-time setup (you)

1. **Signing key.** Creates the private key outside the project and writes the public key into it:

   ```powershell
   .\scripts\new_signing_key.ps1
   ```

   Back up `%USERPROFILE%\.pqsse-signing\pqsse-release.key` offline (for example on a USB stick in a
   drawer). Commit `installer\issig-public-key.txt`. Losing the key means the web installers already
   out there cannot install new releases; a stolen key means someone else can sign a release.

2. **The key as a repository secret** (only if the release workflow should sign):

   ```powershell
   Get-Content "$env:USERPROFILE\.pqsse-signing\pqsse-release.key" -Raw | gh secret set ISSIG_PRIVATE_KEY --repo kushalgiduturi/pq-sse-desktop
   ```

3. **GitHub Pages** from GitHub Actions (site address `https://kushalgiduturi.github.io/pq-sse-desktop/`):

   ```powershell
   gh api -X POST repos/kushalgiduturi/pq-sse-desktop/pages -f build_type=workflow
   ```

4. **Private vulnerability reporting**, so the Security page's "Report a vulnerability" link works:

   ```powershell
   gh api -X PUT repos/kushalgiduturi/pq-sse-desktop/private-vulnerability-reporting
   ```

5. **Optional custom domain** (not set up; only if you buy one): add a `CNAME` record from
   `www.<your domain>` to `kushalgiduturi.github.io`, then set it with
   `gh api -X PUT repos/kushalgiduturi/pq-sse-desktop/pages -f cname=www.<your domain>`, and change
   `site_url`, `manifest_url` and `allowed_hosts` in `packaging/release.toml`. Web installers built
   before that change keep using the old address.

## Each release

1. Set the version in `pyproject.toml` and write the notes in `docs/RELEASE_NOTES.md` (keep the
   "Not verified" section honest).
2. Full local dry run, signed with your key (nothing is published):

   ```powershell
   $env:ISSIGTOOL_KEY_FILE = "$env:USERPROFILE\.pqsse-signing\pqsse-release.key"
   .\build_release.ps1 -WithGpu -SignManifest
   ```

   It runs the tests, builds both variants and the web installer, runs the smoke tests, the installer
   tests and a real web-installer install against a local server, writes `latest.json`,
   `SHA256SUMS.txt` and the signatures, and prints the table of files.
3. Commit, tag and push. The `release` workflow then builds and tests the Standard variant and the web
   installer on GitHub, creates the release with every file and deploys the website:

   ```powershell
   git push origin master
   git tag v0.1.1
   git push origin v0.1.1
   ```

4. GPU build, from this PC (it asks before uploading):

   ```powershell
   .\scripts\publish_gpu.ps1
   ```

   Then review `site\public`, commit and push; the `pages` workflow deploys the site with the GPU
   build listed.
5. winget (optional). Writes and checks the manifests; submitting them is a pull request to
   `microsoft/winget-pkgs` that you open yourself:

   ```powershell
   python scripts\make_winget.py site\public\latest.json
   winget validate --manifest packaging\winget\manifests\p\PQSSE\PQSSEDesktop\<version>
   ```

   When it is accepted, set `[winget] published = true` and `id = "PQSSE.PQSSEDesktop"` in
   `packaging/release.toml` so the Download page shows the `winget install` command.

## What each command does

| Command | Does | Publishes |
| --- | --- | --- |
| `scripts\new_signing_key.ps1` | private key outside the project, public key into `installer\` | nothing |
| `build_release.ps1 [-WithGpu] [-SignManifest]` | build, test, package, manifest, signatures, file table | nothing |
| `scripts\build_site.py --manifest <latest.json>` | the website into `site\public` | nothing |
| `scripts\check_site.py` | HTML, links, contrast, accessible names, no requests to other hosts | nothing |
| `scripts\publish_gpu.ps1 [-DryRun]` | GPU build and self-test, sign, then `gh release upload` after you type yes | the GPU files, only after yes |
| `git push origin v<version>` | starts the release workflow | the release and the website |
