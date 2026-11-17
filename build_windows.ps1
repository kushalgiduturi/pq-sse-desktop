# PQ-SSE Desktop: Windows one-folder build with PyInstaller.
#
#   .\build_windows.ps1                 Standard build (CPU only, small, runs everywhere)
#   .\build_windows.ps1 -WithGpu        GPU build: bundles CuPy and the NVIDIA runtime compiler (large).
#                                       The target PC then only needs an NVIDIA driver.
#   .\build_windows.ps1 -OutDir D:\out  choose the output folder
#   .\build_windows.ps1 -SkipSmoke      build only, do not run the built program
#
# The build embeds the icon and the version (from pyproject.toml), scans the output for
# databases and key files, and then runs the built program with --smoke-test (also with
# PQSSE_FORCE_CPU=1). A failed check fails the build.
#
# No admin rights needed. The output folder defaults to a place outside OneDrive.
# For the installer, the zip and the checksums use build_release.ps1.

param(
    [switch]$WithGpu,
    [string]$Python = "$env:USERPROFILE\.venvs\pqsse\Scripts\python.exe",
    [string]$OutDir = "$env:LOCALAPPDATA\PQ-SSE-Desktop-build",
    [switch]$SkipSmoke,
    [switch]$SkipGpuSelfTest
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Helper = Join-Path $Root "scripts\build_helpers.py"

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "BUILD FAILED: $Message"
    exit 1
}

function Invoke-Helper {
    & $Python $Helper @args
    if ($LASTEXITCODE -ne 0) { Fail "build helper step '$($args[0])' failed." }
}

# Runs the windowed program without a console, waits, prints its report file, returns the exit code.
# With -Visible the window is shown (the spatial window self-test must really draw frames).
function Invoke-App([string]$Exe, [string]$Flag, [string]$Report, [switch]$Visible) {
    if (Test-Path $Report) { Remove-Item $Report -Force }
    $Style = "Hidden"
    if ($Visible) { $Style = "Normal" }
    $proc = Start-Process -FilePath $Exe -ArgumentList @($Flag, "--report", "`"$Report`"") -Wait -PassThru -WindowStyle $Style
    if (Test-Path $Report) { Get-Content $Report | ForEach-Object { Write-Host "    $_" } }
    else { Write-Host "    (the program wrote no report)" }
    return $proc.ExitCode
}

# Hide an installed CUDA Toolkit from this process (PATH, CUDA_PATH, CUDA_HOME, CUDA_PATH_V*).
# Used while packaging the GPU build, so that PyInstaller cannot pull Toolkit DLLs (cuBLAS,
# cuFFT and others, more than 1 GB) into the app, and while testing it, so that the test
# proves the bundled runtime is the one in use. Returns what Restore-Cuda needs.
function Hide-Cuda {
    $Saved = @{ PATH = $env:PATH }
    Get-ChildItem Env: | Where-Object { $_.Name -like "CUDA_PATH*" -or $_.Name -eq "CUDA_HOME" } |
        ForEach-Object { $Saved[$_.Name] = $_.Value; Remove-Item "Env:$($_.Name)" }
    $env:PATH = (($env:PATH -split ";") | Where-Object { $_ -and ($_ -notmatch "(?i)cuda|nvidia gpu computing") }) -join ";"
    return $Saved
}

function Restore-Cuda($Saved) {
    foreach ($Name in $Saved.Keys) { Set-Item "Env:$Name" $Saved[$Name] }
}

if (-not (Test-Path $Python)) {
    Write-Host "Python not found at $Python. Pass -Python <path to python.exe of your virtual environment>."
    exit 1
}
if ($OutDir -like "*OneDrive*") {
    Write-Host "Warning: the output folder is inside OneDrive. Choose a folder outside it with -OutDir."
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$Version = "$(& $Python $Helper version)".Trim()
if ($LASTEXITCODE -ne 0 -or -not $Version) { Fail "could not read the version from pyproject.toml." }
$Variant = "Standard"
if ($WithGpu) { $Variant = "GPU" }
Write-Host "PQ-SSE Desktop $Version, $Variant build"

$VersionFile = Join-Path $OutDir "version_info.txt"
$LicenseFile = Join-Path $OutDir "THIRD-PARTY-LICENSES.txt"
Invoke-Helper version-file $VersionFile --variant $Variant
if ($WithGpu) { Invoke-Helper licenses $LicenseFile --gpu } else { Invoke-Helper licenses $LicenseFile }

$PyiArgs = @(
    "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
    "--name", "PQ-SSE-Desktop",
    "--onedir", "--windowed",
    "--distpath", (Join-Path $OutDir "dist"),
    "--workpath", (Join-Path $OutDir "work"),
    "--specpath", $OutDir,
    "--paths", $Root,
    "--icon", (Join-Path $Root "assets\pqsse.ico"),
    "--version-file", $VersionFile,
    "--add-data", ((Join-Path $Root "pyproject.toml") + ";."),
    "--add-data", ((Join-Path $Root "LICENSE") + ";."),
    "--add-data", ($LicenseFile + ";."),
    "--add-data", ((Join-Path $Root "assets") + ";assets"),
    "--collect-submodules", "pqsse",
    "--collect-submodules", "app",
    "--collect-submodules", "kyber_py",
    "--collect-submodules", "dilithium_py",
    "--hidden-import", "pypdf",
    "--exclude-module", "matplotlib",
    "--exclude-module", "tkinter",
    "--exclude-module", "pytest",
    "--exclude-module", "PySide6.QtWebEngineCore",
    "--exclude-module", "PySide6.QtWebEngineWidgets",
    "--exclude-module", "PySide6.QtQuick3D",
    "--add-data", ((Join-Path $Root "app\spatial\qml") + ";app/spatial/qml"),
    "--add-data", ((Join-Path $Root "app\spatial\fonts") + ";app/spatial/fonts"),
    "--hidden-import", "PySide6.QtQuick",
    "--hidden-import", "PySide6.QtQml",
    "--hidden-import", "PySide6.QtQuickControls2"
)

if ($WithGpu) {
    Write-Host "Bundling CuPy and the NVIDIA runtime compiler (GPU build). This is large and takes several minutes."
    $CudaDir = Join-Path $OutDir "cuda_runtime"
    Invoke-Helper cuda-runtime $CudaDir
    $PyiArgs += @("--collect-all", "cupy", "--collect-all", "cupy_backends",
                  "--collect-submodules", "cuda", "--copy-metadata", "cuda-pathfinder",
                  "--hidden-import", "graphlib",
                  "--add-data", ($CudaDir + ";cuda_runtime"))
} else {
    Write-Host "Standard build: CuPy is not bundled. The packaged app runs on the CPU and says so."
    $PyiArgs += @("--exclude-module", "cupy", "--exclude-module", "cupy_backends", "--exclude-module", "cuda")
}

$PyiArgs += (Join-Path $Root "run_pqsse.py")

Write-Host "Building with $Python ..."
$SavedCuda = $null
if ($WithGpu) { $SavedCuda = Hide-Cuda }
try { & $Python @PyiArgs }
finally { if ($SavedCuda) { Restore-Cuda $SavedCuda } }
if ($LASTEXITCODE -ne 0) {
    Write-Host "Build FAILED (PyInstaller exit code $LASTEXITCODE)."
    exit $LASTEXITCODE
}

$Dist = Join-Path $OutDir "dist\PQ-SSE-Desktop"
$Exe = Join-Path $Dist "PQ-SSE-Desktop.exe"
if (-not (Test-Path $Exe)) {
    Write-Host "Build finished but the executable was not found at $Exe."
    exit 1
}

# The spatial window uses Qt Quick. PyInstaller collects every QML module of the Qt
# install; the app imports only QtQuick, QtQuick.Window, QtQuick.Effects and
# QtQuick.Dialogs (which needs Controls). Remove the unrelated modules and their
# libraries. The UI self-test below proves that nothing needed was removed.
$QtDir = Join-Path $Dist "_internal\PySide6"
$Before = (Get-ChildItem $Dist -Recurse -File | Measure-Object Length -Sum).Sum
$QmlRemove = @("Qt3D", "QtQuick3D", "QtWebEngine", "QtWebView", "QtWebChannel", "QtWebSockets", "QtMultimedia", "QtLocation",
               "QtPositioning", "QtSensors", "QtCharts", "QtDataVisualization", "QtGraphs", "QtScxml", "QtRemoteObjects",
               "QtTextToSpeech", "QtTest", "QtPdf", "QtQuick\Pdf", "QtQuick\VirtualKeyboard", "QtQuick\Scene2D", "QtQuick\Scene3D",
               "QtQuick\Timeline", "QtQuick\Particles", "QtQuick\LocalStorage", "QtQuick\VectorImage", "QtQuick\tooling")
foreach ($Name in $QmlRemove) {
    $Path = Join-Path $QtDir "qml\$Name"
    if (Test-Path $Path) { Remove-Item $Path -Recurse -Force }
}
$DllRemove = @("Qt6Quick3D*.dll", "Qt63D*.dll", "Qt6VirtualKeyboard*.dll", "Qt6Multimedia*.dll", "Qt6Location*.dll", "Qt6Positioning*.dll",
               "Qt6Sensors*.dll", "Qt6DataVisualization*.dll", "Qt6Graphs*.dll", "Qt6Scxml*.dll", "Qt6RemoteObjects*.dll",
               "Qt6TextToSpeech*.dll", "Qt6WebChannel*.dll", "Qt6WebSockets*.dll", "Qt6WebView*.dll", "Qt6Pdf*.dll", "Qt6SpatialAudio*.dll",
               "Qt6QuickTimeline*.dll", "Qt6QuickParticles*.dll", "Qt6QuickVectorImage*.dll", "Qt6StateMachine*.dll", "Qt6Test*.dll", "Qt6QuickTest*.dll")
foreach ($Pattern in $DllRemove) { Get-ChildItem $QtDir -Filter $Pattern -File -ErrorAction SilentlyContinue | Remove-Item -Force }
$After = (Get-ChildItem $Dist -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host ("Unused Qt modules removed: {0:N0} MB before, {1:N0} MB after." -f ($Before / 1MB), ($After / 1MB))

# Readable files next to the exe: licenses and the user documentation.
Copy-Item (Join-Path $Root "LICENSE") (Join-Path $Dist "LICENSE.txt") -Force
Copy-Item $LicenseFile (Join-Path $Dist "THIRD-PARTY-LICENSES.txt") -Force
$DocsOut = Join-Path $Dist "docs"
New-Item -ItemType Directory -Force -Path $DocsOut | Out-Null
foreach ($Doc in @("INSTALL.md", "START_HERE.md", "cheatsheet.md", "concepts.md", "DISTRIBUTION.md", "RELEASE_NOTES.md")) {
    $Source = Join-Path $Root "docs\$Doc"
    if (Test-Path $Source) { Copy-Item $Source (Join-Path $DocsOut $Doc) -Force }
}

Write-Host ""
Write-Host "Checks on the build output:"
if ($WithGpu) {
    # PyInstaller also collects the NVIDIA pip packages as they are. The app uses its own
    # cuda_runtime folder (see pqsse/gpu/runtime.py), so drop the second copy (about 50 MB).
    $Duplicate = Join-Path $Dist "_internal\nvidia"
    if (Test-Path $Duplicate) { Remove-Item $Duplicate -Recurse -Force }
    # Only the bundled compiler and runtime may be in the app, never Toolkit libraries from this PC.
    $Stray = @(Get-ChildItem $Dist -Recurse -File -Include "cublas*.dll", "cufft*.dll", "curand*.dll", "cusolver*.dll",
                             "cusparse*.dll", "nvjitlink*.dll", "cudnn*.dll", "cutensor*.dll")
    if ($Stray.Count -gt 0) {
        Fail ("CUDA Toolkit libraries from this PC were pulled into the build: " + (($Stray | ForEach-Object Name) -join ", "))
    }
    Write-Host "CUDA check OK: only the bundled NVRTC compiler and CUDA runtime are in the build."
}
Invoke-Helper scan $Dist
Invoke-Helper emdash $Dist

if (-not $SkipSmoke) {
    $Reports = Join-Path $OutDir "reports"
    New-Item -ItemType Directory -Force -Path $Reports | Out-Null
    $Tag = $Variant.ToLower()

    Write-Host ""
    Write-Host "Smoke test of the built program:"
    $Code = Invoke-App $Exe "--smoke-test" (Join-Path $Reports "smoke-$Tag.txt")
    if ($Code -ne 0) { Fail "the smoke test of the built program did not pass (exit code $Code)." }

    Write-Host ""
    Write-Host "Smoke test of the built program with PQSSE_FORCE_CPU=1:"
    $env:PQSSE_FORCE_CPU = "1"
    try { $Code = Invoke-App $Exe "--smoke-test" (Join-Path $Reports "smoke-$Tag-forced-cpu.txt") }
    finally { Remove-Item Env:PQSSE_FORCE_CPU -ErrorAction SilentlyContinue }
    if ($Code -ne 0) { Fail "the smoke test with PQSSE_FORCE_CPU=1 did not pass (exit code $Code)." }

    # The spatial window: must load from the built program, with the graphics chip and without it.
    Write-Host ""
    Write-Host "Spatial window self-test of the built program:"
    $Code = Invoke-App $Exe "--ui-selftest" (Join-Path $Reports "ui-$Tag.txt") -Visible
    if ($Code -ne 0) { Fail "the spatial window did not pass its self-test in the built program (exit code $Code)." }
    Write-Host ""
    Write-Host "Spatial window self-test with the software renderer (QT_QUICK_BACKEND=software):"
    $env:QT_QUICK_BACKEND = "software"
    try { $Code = Invoke-App $Exe "--ui-selftest" (Join-Path $Reports "ui-$Tag-software.txt") -Visible }
    finally { Remove-Item Env:QT_QUICK_BACKEND -ErrorAction SilentlyContinue }
    if ($Code -ne 0) { Fail "the spatial window did not pass its self-test with the software renderer (exit code $Code)." }

    if ($WithGpu -and -not $SkipGpuSelfTest) {
        # Prove that the bundled runtime is what is used: hide any installed CUDA Toolkit first.
        Write-Host ""
        Write-Host "GPU self-test of the built program, with the CUDA Toolkit hidden (PATH, CUDA_PATH, CUDA_HOME):"
        $SavedCuda = Hide-Cuda
        $SavedData = $env:PQSSE_DATA_DIR
        $env:PQSSE_DATA_DIR = Join-Path $OutDir "selftest-data"
        try {
            $Code = Invoke-App $Exe "--gpu-selftest" (Join-Path $Reports "gpu-selftest.txt")
            $SelfTestLog = Join-Path $env:PQSSE_DATA_DIR "logs\app.log"
            if ($Code -ne 0 -and (Test-Path $SelfTestLog)) {
                Write-Host "    Log of the failed self-test:"
                Get-Content $SelfTestLog | Select-Object -First 40 | ForEach-Object { Write-Host "    $_" }
            }
        }
        finally {
            Restore-Cuda $SavedCuda
            if ($SavedData) { $env:PQSSE_DATA_DIR = $SavedData } else { Remove-Item Env:PQSSE_DATA_DIR -ErrorAction SilentlyContinue }
            Remove-Item (Join-Path $OutDir "selftest-data") -Recurse -Force -ErrorAction SilentlyContinue
        }
        if ($Code -ne 0) {
            Fail "the GPU self-test of the built program did not pass (exit code $Code). On a PC without an NVIDIA GPU pass -SkipGpuSelfTest."
        }
    }
}

$Size = (Get-ChildItem $Dist -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host ""
Write-Host ("Build OK: PQ-SSE Desktop $Version, $Variant, {0:N0} MB in {1} files." -f ($Size / 1MB), (Get-ChildItem $Dist -Recurse -File).Count)
Write-Host "Run:  $Exe"
Write-Host "The same executable is the cloud server when started with --cloud (the app does this for you)."
