# Create the release signing key for the manifest and the packages (run once, by you).
#
#   .\scripts\new_signing_key.ps1                      key in %USERPROFILE%\.pqsse-signing\
#   .\scripts\new_signing_key.ps1 -KeyFile D:\safe\pqsse-release.key
#
# The private key is an ECDSA P-256 key made by Inno Setup's ISSigTool. It stays outside the
# project folder and is never committed. Only the public key is written into the project
# (installer\issig-public-key.txt), where the web installer and the app's update check read it.
# Anyone with the private key can sign a manifest that the web installer trusts: back it up
# offline and give it to nobody. To sign in GitHub Actions, you add it as a repository secret
# yourself (see docs\RELEASE_CHECKLIST.md); this script does not do that.

param(
    [string]$KeyFile = (Join-Path $env:USERPROFILE ".pqsse-signing\pqsse-release.key")
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$PublicKey = Join-Path $Root "installer\issig-public-key.txt"

$Tool = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISSigTool.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISSigTool.exe",
          "$env:ProgramFiles\Inno Setup 6\ISSigTool.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Tool) { Write-Host "ISSigTool.exe (Inno Setup 6.5 or newer) was not found." -ForegroundColor Red; exit 1 }

if ($KeyFile.StartsWith($Root, [StringComparison]::OrdinalIgnoreCase)) {
    Write-Host "Refusing to put the private key inside the project folder: $KeyFile" -ForegroundColor Red; exit 1
}
if (Test-Path $KeyFile) {
    Write-Host "A key already exists at $KeyFile. Not overwritten." -ForegroundColor Yellow
} else {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $KeyFile) | Out-Null
    & $Tool "--key-file=$KeyFile" generate-private-key
    if ($LASTEXITCODE -ne 0) { exit 1 }
}
& $Tool "--key-file=$KeyFile" --allow-overwrite export-public-key $PublicKey
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host ""
Write-Host "Private key : $KeyFile   (keep it secret, back it up offline)"
Write-Host "Public key  : $PublicKey   (commit this one)"
Write-Host ""
Write-Host "To sign a release on this PC:"
Write-Host "  `$env:ISSIGTOOL_KEY_FILE = `"$KeyFile`""
Write-Host "  .\build_release.ps1 -SignManifest"
