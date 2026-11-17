# Add the GPU build to an existing GitHub Release (run by the maintainer, on a PC with an NVIDIA GPU).
#
#   $env:ISSIGTOOL_KEY_FILE = "$env:USERPROFILE\.pqsse-signing\pqsse-release.key"
#   .\scripts\publish_gpu.ps1                  build, test, sign, then ask before uploading
#   .\scripts\publish_gpu.ps1 -DryRun          everything except the upload
#
# Steps:
#   1. GPU build with build_windows.ps1 -WithGpu: smoke test, NVIDIA redistribution check, and the
#      GPU self-test on this PC (with the CUDA Toolkit hidden)
#   2. GPU installer and portable zip
#   3. the release's latest.json is downloaded with the GitHub CLI, the GPU entries are added and
#      latest.json and the two GPU files are signed (Inno Setup .issig, key from the environment)
#   4. after you type yes: gh release upload of the GPU files, their signatures, latest.json,
#      latest.json.issig and an updated SHA256SUMS.txt (existing names are replaced)
#   5. the website is rebuilt from the new latest.json into site\public; commit and push it to
#      publish (the pages workflow deploys it). This script never commits or pushes.
# GitHub sign-in: `gh auth login` beforehand. No token is read or written by this script.

param(
    [string]$Version = "",
    [string]$BuildRoot = "$env:LOCALAPPDATA\PQ-SSE-Desktop-build",
    [string]$Repo = "kushalgiduturi/pq-sse-desktop",
    [switch]$SkipBuild,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
function Fail([string]$Message) { Write-Host "FAILED: $Message" -ForegroundColor Red; exit 1 }
function Step([string]$Name) { Write-Host ""; Write-Host "== $Name" -ForegroundColor Cyan }

$Python = Join-Path $BuildRoot "venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { Fail "no build environment at $BuildRoot (run build_release.ps1 -WithGpu once first)." }
if (-not $Version) { $Version = "$(& $Python (Join-Path $Root 'scripts\build_helpers.py') version)".Trim() }
if (-not $env:ISSIGTOOL_KEY_FILE -or -not (Test-Path $env:ISSIGTOOL_KEY_FILE)) { Fail "set ISSIGTOOL_KEY_FILE to the private signing key file." }
if (-not $DryRun) {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { Fail "the GitHub CLI (gh) is not installed." }
    & gh auth status *> $null
    if ($LASTEXITCODE -ne 0) { Fail "the GitHub CLI is not signed in: run gh auth login." }
}
$Iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Iscc) { Fail "Inno Setup 6 (ISCC.exe) was not found." }

$Work = Join-Path $BuildRoot "publish-gpu\$Version"
if (Test-Path $Work) { Remove-Item $Work -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Work | Out-Null
$Dist = Join-Path $BuildRoot "gpu\dist\PQ-SSE-Desktop"

Step "1. GPU build and its self-test on this PC"
if (-not $SkipBuild) {
    & (Join-Path $Root "build_windows.ps1") -Python $Python -OutDir (Join-Path $BuildRoot "gpu") -WithGpu | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "the GPU build or one of its checks failed." }
}
if (-not (Test-Path (Join-Path $Dist "PQ-SSE-Desktop.exe"))) { Fail "no GPU build at $Dist." }
& $Python (Join-Path $Root "scripts\build_helpers.py") cuda-check $Dist | Out-Host
if ($LASTEXITCODE -ne 0) { Fail "the GPU build holds NVIDIA files that may not be redistributed." }

Step "2. GPU installer and portable zip"
$Setup = "PQ-SSE-Desktop-Setup-$Version-GPU"
& $Iscc /Q "/DAppVersion=$Version" "/DVariant=GPU" "/DSourceDir=$Dist" "/DOutputDir=$Work" "/DOutputBase=$Setup" (Join-Path $Root "installer\pqsse.iss") | Out-Host
if ($LASTEXITCODE -ne 0) { Fail "Inno Setup could not compile the GPU installer." }
$Readme = Join-Path $Dist "PORTABLE-README.txt"
$Note = "  GPU build. It can use an NVIDIA graphics chip to speed up one step (building a`r`n  large index). It needs a current NVIDIA driver; the CUDA Toolkit is not needed.`r`n  Without a usable NVIDIA chip it runs on the normal processor and says so."
$Text = (Get-Content (Join-Path $Root "installer\PORTABLE-README.txt") -Raw).Replace("@VERSION@", $Version).Replace("@VARIANT@", "GPU").Replace("@VARIANT_NOTE@", $Note)
Set-Content -Path $Readme -Value $Text -Encoding ASCII
try { & $Python (Join-Path $Root "scripts\build_helpers.py") zip $Dist (Join-Path $Work "PQ-SSE-Desktop-$Version-portable-gpu.zip") "PQ-SSE-Desktop-$Version-gpu" | Out-Host }
finally { Remove-Item $Readme -Force -ErrorAction SilentlyContinue }

Step "3. The release's file list, with the GPU build added and signed"
$Manifest = Join-Path $Work "latest.json"
$Online = $false
if (Get-Command gh -ErrorAction SilentlyContinue) { & gh auth status *> $null; $Online = ($LASTEXITCODE -eq 0) }
if ($Online) {
    # also in a dry run, so the prepared files are exactly what a real run would upload
    & gh release download "v$Version" --repo $Repo --pattern "latest.json" --pattern "SHA256SUMS.txt" --dir $Work --clobber
    if ($LASTEXITCODE -ne 0) { Fail "could not download latest.json from release v$Version." }
} elseif ($DryRun) {
    $Local = Join-Path $Root "site\public\latest.json"
    Copy-Item $Local $Manifest
    Write-Host "Dry run without the GitHub CLI: using $Local; SHA256SUMS.txt will list only the GPU files."
} else {
    Fail "the GitHub CLI is not signed in."
}
& $Python (Join-Path $Root "scripts\make_manifest.py") $Work --add-gpu $Manifest --sign | Out-Host
if ($LASTEXITCODE -ne 0) { Fail "the file list could not be updated or signed." }
$Sums = Join-Path $Work "SHA256SUMS.txt"
$Lines = @()
if (Test-Path $Sums) { $Lines = Get-Content $Sums | Where-Object { $_ -and $_ -notmatch "(-GPU\.exe|portable-gpu\.zip|latest\.json)$" } }
foreach ($File in (Get-ChildItem $Work -File | Where-Object { $_.Name -match "(-GPU\.exe|portable-gpu\.zip|latest\.json)$" })) {
    $Lines += "{0}  {1}" -f (Get-FileHash $File.FullName -Algorithm SHA256).Hash.ToLower(), $File.Name
}
Set-Content -Path $Sums -Value ($Lines | Sort-Object { $_.Split(" ")[-1] }) -Encoding ascii

$Upload = Get-ChildItem $Work -File | Where-Object { $_.Name -match "(-GPU\.exe|portable-gpu\.zip)(\.issig)?$|^latest\.json(\.issig)?$|^SHA256SUMS\.txt$" }
Write-Host ""
Write-Host ("{0,-52} {1,10}  {2}" -f "File", "Size", "SHA-256")
foreach ($File in $Upload) {
    Write-Host ("{0,-52} {1,7:N1} MB  {2}" -f $File.Name, ($File.Length / 1MB), (Get-FileHash $File.FullName -Algorithm SHA256).Hash.ToLower())
}

Step "4. Upload to release v$Version"
if ($DryRun) {
    Write-Host "Dry run: nothing uploaded. The command would be:"
    Write-Host ("  gh release upload v$Version --repo $Repo --clobber " + (($Upload | ForEach-Object { '"' + $_.FullName + '"' }) -join " "))
} else {
    $Answer = Read-Host "Upload these $($Upload.Count) files to the public release v$Version on $Repo? Type yes to continue"
    if ($Answer -ne "yes") { Fail "not uploaded (you did not type yes)." }
    & gh release upload "v$Version" --repo $Repo --clobber ($Upload | ForEach-Object { $_.FullName })
    if ($LASTEXITCODE -ne 0) { Fail "the upload failed." }
}

Step "5. Website from the new file list"
$SiteOut = if ($DryRun) { Join-Path $Work "site" } else { Join-Path $Root "site\public" }
& $Python (Join-Path $Root "scripts\build_site.py") --manifest $Manifest --out $SiteOut | Out-Host
if ($LASTEXITCODE -ne 0) { Fail "the website could not be rebuilt." }
if ($DryRun) { Write-Host "Dry run: the website was built into $SiteOut, not into site\public." }
Write-Host ""
Write-Host "Done. To publish the website: review site\public, then commit and push (the pages workflow deploys it)."
