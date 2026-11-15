# Giving PQ-SSE Desktop to other people

Plain facts about what a user will see, why, and what would change it.

## The files are not code signed

Neither the setup file nor the program carries a digital signature from a publisher.
Nothing in the build pretends otherwise.

### What the user sees

When a setup file was downloaded from the internet and has no signature, or has a
signature Windows has not seen often, Microsoft Defender SmartScreen shows a blue box:

> Windows protected your PC

It means "Windows does not know this file yet". It does not mean a virus was found.

To continue:

1. Click **More info** (small link in the text).
2. Check that the file name is the one you downloaded.
3. Click **Run anyway**.

Some browsers also warn at download time ("is not commonly downloaded"). Choose **Keep**.

A copy that did not come through a browser (a USB stick, a shared folder) usually shows
no SmartScreen box, because the file has no "downloaded from the internet" mark.

### What real code signing would need

| Option | What it is | Rough cost | Effect on SmartScreen |
| --- | --- | --- | --- |
| OV code signing certificate | A certificate issued to a verified person or company. The key must live on a hardware token or in a cloud key store. | A few hundred US dollars per year, depending on the seller | The publisher name is shown instead of "Unknown publisher". The warning can still appear until the signed file has built up reputation. |
| EV code signing certificate | Stricter identity check, hardware token | Microsoft's page speaks of 400 US dollars per year and more | The same as OV today. Years ago an EV signature removed the warning at once. Microsoft's documentation says this is no longer the case, and that paying extra for EV only to avoid the warning is no longer justified. |
| Azure Artifact Signing (formerly Azure Trusted Signing) | Microsoft's signing service. Identity is verified once, certificates are short-lived and managed for you. | Reported as 9.99 US dollars per month for the small plan (January 2026) | Publisher name shown, reputation builds like with OV. In January 2026 it was reported as available in the USA, Canada and Europe. Whether you can use it from your country, and as a private person, must be checked with Microsoft. |

Signing does not make the warning disappear on the first day. Microsoft describes
SmartScreen reputation as tied to each file, so a new build starts without reputation
even when it is signed. What signing does give at once: the publisher's name in the
dialogs, and proof that the file was not changed after signing.

Prices and rules change. The figures above were looked up in November 2026, not tested
by buying anything. Check the seller's and Microsoft's current pages first:
https://learn.microsoft.com/windows/apps/package-and-deploy/code-signing-options and
https://learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation .
A self-made (self-signed) certificate does not help: other PCs do not trust it.

### Signing hook in the build

`build_release.ps1` can sign, but does not by default:

```powershell
$env:PQSSE_SIGN_PASSWORD = "<password of the .pfx file>"
.\build_release.ps1 -SignCert C:\path\to\certificate.pfx
```

It then signs `PQ-SSE-Desktop.exe` before packaging and each setup file afterwards, with
`signtool` from the Windows SDK and a time stamp. The password is read from the
environment variable and is never written to a file. This hook has **not been tested**:
no certificate was available. Certificates on a hardware token or in a cloud service
need a different `signtool` call than a `.pfx` file.

## Antivirus false positives

The program is built with PyInstaller as a folder (not as one self-extracting file,
which antivirus tools flag far more often). Even so, a new unsigned program built this
way can be flagged by mistake by some antivirus products.

If that happens:

1. **Check the checksum first** (next section). If it does not match, do not run the file.
2. If it matches, report the false positive to the antivirus maker. For Microsoft
   Defender: https://www.microsoft.com/wdsi/filesubmission (choose "Software developer"
   or "Home customer", upload the file, select "Incorrectly detected as malware").
   Other makers have a similar "submit a sample" or "report false positive" page.
3. Until it is cleared, restore the file from quarantine and add an exception for the
   install folder.

## Checking a download with its SHA-256 checksum

Every release comes with `SHA256SUMS.txt`. It lists one line per file: a long code, then
the file name. To check a download, open PowerShell in the folder with the file and run:

```powershell
Get-FileHash .\PQ-SSE-Desktop-Setup-0.1.0.exe -Algorithm SHA256
```

Compare the **Hash** it prints with the line for that file in `SHA256SUMS.txt`. Capital
or small letters do not matter. If every character matches, the file is exactly the one
that was built. If not, the download is damaged or was changed: delete it.

A checksum proves the file was not changed after it was built. It does not prove who
built it. Only code signing does that. So get `SHA256SUMS.txt` from a place you trust.

## What is inside a release

- `PQ-SSE-Desktop-Setup-<version>.exe`: installer, Standard build (CPU).
- `PQ-SSE-Desktop-Setup-<version>-GPU.exe`: installer, GPU build (only when built with `-WithGpu`).
- `PQ-SSE-Desktop-<version>-portable-standard.zip` and `...-portable-gpu.zip`: the same programs as folders.
- `SHA256SUMS.txt`.

No build contains keys, passphrases, databases or settings. The build script scans every
build folder for such files and fails if it finds one.

## Network and firewall

The program does not go online. Its cloud part is a second process on the same PC that
listens on `127.0.0.1` only, so it cannot be reached from other computers, and Windows
does not ask for a firewall permission. The installer adds no firewall rule.

## Rebuilding

```powershell
.\build_release.ps1 -WithGpu
```

Needs Python 3.11 and Inno Setup 6
(`winget install -e --id JRSoftware.InnoSetup --source winget --override "/VERYSILENT /CURRENTUSER /NORESTART"`).
The script prints the list of files with sizes and checksums at the end.
