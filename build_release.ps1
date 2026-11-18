# PQ-SSE Desktop: build the whole release with one command.
#
#   .\build_release.ps1                    Standard build: installer, portable zip, checksums
#   .\build_release.ps1 -WithGpu           also the GPU build (needs an NVIDIA GPU on this PC for its self-test)
#   .\build_release.ps1 -CopyTo D:\out     copy the release files to another folder at the end
#   .\build_release.ps1 -SkipTests         skip the pytest suite (the built programs are still tested)
#
# Steps, in order. The script stops at the first failure and says which step failed.
#    1. build environment outside OneDrive, exact package versions from requirements-lock.txt
#    2. source checks and the full pytest suite
#    3. one-folder build(s) with build_windows.ps1, which also scans each build for databases
#       and key files and runs the built program with --smoke-test (normal and forced CPU)
#    4. installer(s) with Inno Setup, portable zip(s)
#    5. tests of the release files: portable zip from a folder with spaces, silent install,
#       upgrade over an older version, smoke test from the installed location, silent uninstall
#    6. latest.json (the manifest the site, the web installer and the update check read),
#       SHA256SUMS.txt and a table of the files. With -SignManifest, latest.json and every
#       package also get an Inno Setup signature (.issig); the private key file is named by the
#       environment variable ISSIGTOOL_KEY_FILE and never written anywhere by this script.
#
# Output: %LOCALAPPDATA%\PQ-SSE-Desktop-build\release\<version>\   (change with -BuildRoot)
# No admin rights needed. Nothing is written into the project folder.
#
# Code signing is off by default. To sign, pass -SignCert <path to .pfx> and put the
# certificate password in the environment variable PQSSE_SIGN_PASSWORD (never in a file).

param(
    [switch]$WithGpu,
    [switch]$SkipTests,
    [switch]$SkipInstallerTest,
    [switch]$SignManifest,
    [string]$CopyTo = "",
    [string]$BuildRoot = "$env:LOCALAPPDATA\PQ-SSE-Desktop-build",
    [string]$Python = "",
    [string]$SignCert = "",
    [string]$SignPasswordEnv = "PQSSE_SIGN_PASSWORD",
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Helper = Join-Path $Root "scripts\build_helpers.py"
$Started = Get-Date
$script:StepName = "start"

function Step([string]$Name) {
    $script:StepName = $Name
    Write-Host ""
    Write-Host ("=" * 78)
    Write-Host $Name
    Write-Host ("=" * 78)
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "RELEASE BUILD FAILED in step: $script:StepName"
    Write-Host $Message
    try { Stop-Transcript | Out-Null } catch { }
    exit 1
}

function Run-Helper {
    & $VenvPython $Helper @args | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "build helper step '$($args[0])' failed." }
}

function Find-BasePython {
    if ($Python) { return $Python }
    $Launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($Launcher) {
        $Found = & py -3.11 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $Found) { return "$Found".Trim() }
    }
    foreach ($Candidate in @("$env:ProgramFiles\Python311\python.exe", "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
                             "$env:USERPROFILE\.venvs\pqsse\Scripts\python.exe")) {
        if (Test-Path $Candidate) { return $Candidate }
    }
    $OnPath = Get-Command python -ErrorAction SilentlyContinue
    if ($OnPath) { return $OnPath.Source }
    return ""
}

function Find-Iscc {
    $OnPath = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($OnPath) { return $OnPath.Source }
    foreach ($Candidate in @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
                             "$env:ProgramFiles\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $Candidate) { return $Candidate }
    }
    return ""
}

function Find-SignTool {
    $OnPath = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($OnPath) { return $OnPath.Source }
    $Kits = "${env:ProgramFiles(x86)}\Windows Kits\10\bin"
    if (Test-Path $Kits) {
        $Found = Get-ChildItem $Kits -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "\\x64\\" } | Sort-Object FullName -Descending | Select-Object -First 1
        if ($Found) { return $Found.FullName }
    }
    return ""
}

# Signs a file when -SignCert was given. Off by default.
function Sign-File([string]$Path) {
    if (-not $SignCert) { return }
    $Password = [Environment]::GetEnvironmentVariable($SignPasswordEnv)
    if (-not $Password) { Fail "-SignCert was given but the environment variable $SignPasswordEnv is empty." }
    & $script:SignTool sign /fd SHA256 /f $SignCert /p $Password /tr $TimestampUrl /td SHA256 /d "PQ-SSE Desktop" $Path | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "signtool could not sign $Path." }
    Write-Host "Signed: $Path"
}

function Build-Variant([string]$Name, [string]$OutDir, [switch]$Gpu) {
    Step "Build: $Name variant"
    if ($Gpu) { & (Join-Path $Root "build_windows.ps1") -Python $VenvPython -OutDir $OutDir -WithGpu | Out-Host }
    else { & (Join-Path $Root "build_windows.ps1") -Python $VenvPython -OutDir $OutDir | Out-Host }
    if ($LASTEXITCODE -ne 0) { Fail "the $Name build or one of its checks failed (see above)." }
    $Dist = Join-Path $OutDir "dist\PQ-SSE-Desktop"
    Sign-File (Join-Path $Dist "PQ-SSE-Desktop.exe")
    return $Dist
}

function Compile-Installer([string]$Dist, [string]$Variant, [string]$AppVersion, [string]$OutDir, [string]$Base, [switch]$Twin) {
    $Extra = @()
    if ($Twin) { $Extra = @("/DTestInstall=1") }
    & $Iscc /Q @Extra "/DAppVersion=$AppVersion" "/DVariant=$Variant" "/DSourceDir=$Dist" "/DOutputDir=$OutDir" "/DOutputBase=$Base" `
        (Join-Path $Root "installer\pqsse.iss") | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "Inno Setup could not compile the $Variant installer." }
    $File = Join-Path $OutDir "$Base.exe"
    if (-not (Test-Path $File)) { Fail "the installer $File was not created." }
    return $File
}

function Make-Zip([string]$Dist, [string]$Variant, [string]$Note) {
    $Tag = $Variant.ToLower()
    $Readme = Join-Path $Dist "PORTABLE-README.txt"
    $Text = (Get-Content (Join-Path $Root "installer\PORTABLE-README.txt") -Raw)
    $Text = $Text.Replace("@VERSION@", $Version).Replace("@VARIANT@", $Variant).Replace("@VARIANT_NOTE@", $Note)
    Set-Content -Path $Readme -Value $Text -Encoding ASCII
    $Zip = Join-Path $ReleaseDir "PQ-SSE-Desktop-$Version-portable-$Tag.zip"
    try { Run-Helper zip $Dist $Zip "PQ-SSE-Desktop-$Version-$Tag" }
    finally { Remove-Item $Readme -Force -ErrorAction SilentlyContinue }
    return $Zip
}

if ($BuildRoot -like "*OneDrive*") { Write-Host "The build folder must be outside OneDrive. Choose another -BuildRoot."; exit 1 }
New-Item -ItemType Directory -Force -Path $BuildRoot, (Join-Path $BuildRoot "logs") | Out-Null
$LogFile = Join-Path $BuildRoot ("logs\release-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
try { Start-Transcript -Path $LogFile | Out-Null } catch { }
$env:PYTHONPYCACHEPREFIX = Join-Path $BuildRoot "pycache"       # no compiled Python files in the project folder

# ---------------------------------------------------------------------------------------
Step "1. Build environment"
$BasePython = Find-BasePython
if (-not $BasePython -or -not (Test-Path $BasePython)) {
    Fail "Python 3.11 was not found. Install it from python.org, or pass -Python <path to python.exe>."
}
$VenvDir = Join-Path $BuildRoot "venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating the build environment in $VenvDir (from $BasePython)"
    & $BasePython -m venv $VenvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) { Fail "could not create the virtual environment." }
} else {
    Write-Host "Reusing the build environment in $VenvDir"
}
& $VenvPython -m pip install --disable-pip-version-check --quiet -r (Join-Path $Root "requirements-lock.txt")
if ($LASTEXITCODE -ne 0) { Fail "pip could not install requirements-lock.txt." }
if ($WithGpu) {
    & $VenvPython -m pip install --disable-pip-version-check --quiet -r (Join-Path $Root "requirements-lock-gpu.txt")
    if ($LASTEXITCODE -ne 0) { Fail "pip could not install requirements-lock-gpu.txt." }
}
$Version = "$(& $VenvPython $Helper version)".Trim()
if ($LASTEXITCODE -ne 0 -or -not $Version) { Fail "could not read the version from pyproject.toml." }
$Os = Get-CimInstance Win32_OperatingSystem
Write-Host "Version to build : $Version"
Write-Host "Python           : $(& $VenvPython -c 'import sys; print(sys.version.split()[0])')"
Write-Host "Windows          : $($Os.Caption), build $($Os.BuildNumber)"
$Smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($Smi) { Write-Host "GPU              : $(& nvidia-smi --query-gpu=name,driver_version --format=csv,noheader)" }
else { Write-Host "GPU              : no NVIDIA tool (nvidia-smi) found on this PC" }

$Iscc = Find-Iscc
if (-not $Iscc) {
    Fail ("Inno Setup 6 (ISCC.exe) was not found on PATH, in %LOCALAPPDATA%\Programs\Inno Setup 6 or in Program Files.`n" +
          "Install it without admin rights with this one command, then run the build again:`n" +
          "  winget install -e --id JRSoftware.InnoSetup --source winget --override `"/VERYSILENT /CURRENTUSER /NORESTART`"")
}
Write-Host "Inno Setup       : $Iscc"
if ($SignCert) {
    if (-not (Test-Path $SignCert)) { Fail "the certificate file $SignCert does not exist." }
    $script:SignTool = Find-SignTool
    if (-not $script:SignTool) { Fail "-SignCert was given but signtool.exe (Windows SDK) was not found." }
    Write-Host "Code signing     : ON, with $SignCert"
} else {
    Write-Host "Code signing     : off (the files will be unsigned)"
}

# ---------------------------------------------------------------------------------------
Step "2. Source checks and tests"
Run-Helper emdash $Root
if ($SkipTests) {
    Write-Host "pytest: SKIPPED (-SkipTests)"
} else {
    Push-Location $Root
    try { & $VenvPython -m pytest tests -p no:cacheprovider | Out-Host }
    finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { Fail "the pytest suite did not pass." }
}

# ---------------------------------------------------------------------------------------
$Builds = @()
$Dist = Build-Variant "Standard" (Join-Path $BuildRoot "standard")
$Builds += @{ Variant = "Standard"; Dist = $Dist; Base = "PQ-SSE-Desktop-Setup-$Version"
              Note = "  Standard build. It runs on the normal processor (CPU) and does not use a graphics`r`n  chip. It works on any 64-bit Windows 10 or 11 PC." }
if ($WithGpu) {
    $Dist = Build-Variant "GPU" (Join-Path $BuildRoot "gpu") -Gpu
    $Builds += @{ Variant = "GPU"; Dist = $Dist; Base = "PQ-SSE-Desktop-Setup-$Version-GPU"
                  Note = "  GPU build. It can use an NVIDIA graphics chip to speed up one step (building a`r`n  large index). It needs a current NVIDIA driver; the CUDA Toolkit is not needed.`r`n  Without a usable NVIDIA chip it runs on the normal processor and says so." }
}

# ---------------------------------------------------------------------------------------
Step "4. Installer(s) and portable zip(s)"
$ReleaseDir = Join-Path $BuildRoot "release\$Version"
if (Test-Path $ReleaseDir) { Remove-Item $ReleaseDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
foreach ($Build in $Builds) {
    $Size = (Get-ChildItem $Build.Dist -Recurse -File | Measure-Object Length -Sum).Sum
    Write-Host ("{0} build folder: {1:N0} MB" -f $Build.Variant, ($Size / 1MB))
    if ($Size -gt 1.5GB) { Write-Host "WARNING: this build is larger than 1.5 GB. Check what was bundled." }
    $Build.Setup = Compile-Installer $Build.Dist $Build.Variant $Version $ReleaseDir $Build.Base
    Sign-File $Build.Setup
    Write-Host "Installer: $($Build.Setup)"
    $Build.Zip = Make-Zip $Build.Dist $Build.Variant $Build.Note
}
# The web installer (a few MB): built when the public signing key is in the project.
$PublicKey = Join-Path $Root "installer\issig-public-key.txt"
if (Test-Path $PublicKey) {
    & $VenvPython (Join-Path $Root "scripts\build_web_setup.py") --out $ReleaseDir --version $Version | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "the web installer did not build." }
    Sign-File (Join-Path $ReleaseDir "PQ-SSE-Web-Setup.exe")
    if (-not $SignManifest) { Write-Host "WARNING: the web installer was built, but without -SignManifest it cannot install this release." }
} else {
    Write-Host "Web installer: SKIPPED (no installer\issig-public-key.txt yet; run scripts\new_signing_key.ps1 once)."
}

# The cloud server as a Windows console program (since 0.2.0). build_server.ps1 builds it, scans it for
# keys and databases, and runs its smoke test; the zip also carries the server guide.
& (Join-Path $Root "build_server.ps1") -BuildRoot $BuildRoot -Python $VenvPython | Out-Host
if ($LASTEXITCODE -ne 0) { Fail "the server program did not build or did not pass its smoke test." }
$ServerDist = Join-Path $BuildRoot "server\dist\pqsse-server"
Sign-File (Join-Path $ServerDist "pqsse-server.exe")
Copy-Item (Join-Path $Root "docs\SERVER.md") (Join-Path $ServerDist "SERVER.md") -Force
$ServerZip = Join-Path $ReleaseDir "PQ-SSE-Server-$Version-windows.zip"
Compress-Archive -Path $ServerDist -DestinationPath $ServerZip -Force
Write-Host ("Server zip: {0} ({1:N1} MB)" -f $ServerZip, ((Get-Item $ServerZip).Length / 1MB))

# ---------------------------------------------------------------------------------------
Step "5. Tests of the release files"
foreach ($Build in $Builds) {
    Write-Host ""
    Write-Host "Portable zip, $($Build.Variant):"
    & (Join-Path $Root "scripts\test_portable.ps1") -Zip $Build.Zip -WorkDir (Join-Path $BuildRoot "portable-test") | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "the portable test of $($Build.Zip) did not pass." }
}
if ($SkipInstallerTest) {
    Write-Host "Installer test: SKIPPED (-SkipInstallerTest)"
} else {
    # A throwaway installer with an older version number, from the same files, to test upgrade in place.
    $OlderDir = Join-Path $BuildRoot "work-older-setup"
    if (Test-Path $OlderDir) { Remove-Item $OlderDir -Recurse -Force }
    # If PQ-SSE Desktop is really installed on this PC, the test must not upgrade and remove it.
    # Then twin installers are tested instead: the same script and the same files, compiled
    # with a separate name and AppId. Otherwise the release files themselves are tested.
    $RealKey = "Software\Microsoft\Windows\CurrentVersion\Uninstall\{6E0B2C54-9D7A-4F5E-8B21-3C4A7D95E1F0}_is1"
    $UseTwin = (Test-Path "HKCU:\$RealKey") -or (Test-Path "HKLM:\$RealKey")
    if ($UseTwin) {
        Write-Host "PQ-SSE Desktop is installed on this PC. Testing twin installers (name 'PQ-SSE Desktop Test') so that install stays untouched."
        $Older = Compile-Installer $Builds[0].Dist "Standard" "0.0.1" $OlderDir "older-setup-for-upgrade-test" -Twin
    } else {
        $Older = Compile-Installer $Builds[0].Dist "Standard" "0.0.1" $OlderDir "older-setup-for-upgrade-test"
    }
    foreach ($Build in $Builds) {
        Write-Host ""
        Write-Host "Installer, $($Build.Variant) (upgrade over an older Standard install):"
        $UnderTest = $Build.Setup
        if ($UseTwin) { $UnderTest = Compile-Installer $Build.Dist $Build.Variant $Version $OlderDir ("twin-" + $Build.Base) -Twin }
        & (Join-Path $Root "scripts\test_installer.ps1") -Setup $UnderTest -OlderSetup $Older -WorkDir (Join-Path $BuildRoot "installer-test") -Twin:$UseTwin | Out-Host
        if ($LASTEXITCODE -ne 0) { Fail "the installer test of $($Build.Setup) did not pass." }
    }
    Remove-Item $OlderDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host ""
    Write-Host "Web installer, real run against a local server (twin identity, throwaway key):"
    & $VenvPython (Join-Path $Root "scripts\test_web_setup_real.py") --dist $Builds[0].Dist | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "the web installer real run did not pass." }
}

# ---------------------------------------------------------------------------------------
Step "6. Manifest, checksums and result"
$ManifestArgs = @((Join-Path $Root "scripts\make_manifest.py"), $ReleaseDir, "--version", $Version)
if ($SignManifest) {
    if (-not $env:ISSIGTOOL_KEY_FILE) { Fail "-SignManifest was given but the environment variable ISSIGTOOL_KEY_FILE is empty." }
    $ManifestArgs += "--sign"
}
& $VenvPython @ManifestArgs | Out-Host
if ($LASTEXITCODE -ne 0) { Fail "the manifest could not be written." }
if (-not $SignManifest) { Write-Host "latest.json is NOT signed (no -SignManifest). The web installer refuses an unsigned manifest." }
Run-Helper emdash $ReleaseDir (Join-Path $Root "installer")
if ($CopyTo) {
    $Target = Join-Path $CopyTo $Version
    New-Item -ItemType Directory -Force -Path $Target | Out-Null
    Copy-Item (Join-Path $ReleaseDir "*") $Target -Force
    Write-Host "Copied to $Target"
}

$Minutes = ((Get-Date) - $Started).TotalMinutes
Write-Host ""
Write-Host ("RELEASE BUILD OK: PQ-SSE Desktop {0}, {1:N1} minutes" -f $Version, $Minutes)
Write-Host "Folder: $ReleaseDir"
Write-Host ""
Write-Host ("{0,-52} {1,10}  {2}" -f "File", "Size", "SHA-256")
foreach ($File in (Get-ChildItem $ReleaseDir -File | Sort-Object Name)) {
    $Hash = ""
    if ($File.Name -ne "SHA256SUMS.txt") { $Hash = (Get-FileHash $File.FullName -Algorithm SHA256).Hash.ToLower() }
    Write-Host ("{0,-52} {1,7:N1} MB  {2}" -f $File.Name, ($File.Length / 1MB), $Hash)
}
Write-Host ""
Write-Host "Log of this build: $LogFile"
if (-not $SignCert) { Write-Host "The files are not code signed. See docs\DISTRIBUTION.md." }
try { Stop-Transcript | Out-Null } catch { }
exit 0
