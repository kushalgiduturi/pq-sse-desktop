# PQ-SSE Desktop: Windows one-folder build with PyInstaller.
#
#   .\build_windows.ps1                 CPU build (small, runs everywhere)
#   .\build_windows.ps1 -WithGpu        also bundles CuPy (large; needs the NVIDIA driver on the target PC)
#   .\build_windows.ps1 -OutDir D:\out  choose the output folder
#
# No admin rights needed. The output folder defaults to a place outside OneDrive.

param(
    [switch]$WithGpu,
    [string]$Python = "$env:USERPROFILE\.venvs\pqsse\Scripts\python.exe",
    [string]$OutDir = "$env:LOCALAPPDATA\PQ-SSE-Desktop-build"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path $Python)) {
    Write-Host "Python not found at $Python. Pass -Python <path to python.exe of your virtual environment>."
    exit 1
}

$PyiArgs = @(
    "-m", "PyInstaller", "--noconfirm", "--clean",
    "--name", "PQ-SSE-Desktop",
    "--onedir", "--windowed",
    "--distpath", (Join-Path $OutDir "dist"),
    "--workpath", (Join-Path $OutDir "work"),
    "--specpath", $OutDir,
    "--paths", $Root,
    "--collect-submodules", "pqsse",
    "--collect-submodules", "app",
    "--collect-submodules", "kyber_py",
    "--collect-submodules", "dilithium_py",
    "--hidden-import", "pypdf",
    "--exclude-module", "matplotlib",
    "--exclude-module", "tkinter",
    "--exclude-module", "PySide6.QtWebEngineCore",
    "--exclude-module", "PySide6.QtWebEngineWidgets",
    "--exclude-module", "PySide6.QtQuick",
    "--exclude-module", "PySide6.QtQml"
)

if ($WithGpu) {
    Write-Host "Bundling CuPy (GPU build). This is large and takes several minutes."
    $PyiArgs += @("--collect-all", "cupy", "--collect-all", "cupy_backends", "--collect-all", "fastrlock")
} else {
    Write-Host "CPU build: CuPy is not bundled. The packaged app runs on the CPU and says so."
    $PyiArgs += @("--exclude-module", "cupy", "--exclude-module", "cupy_backends")
}

$PyiArgs += (Join-Path $Root "run_pqsse.py")

Write-Host "Building with $Python ..."
& $Python @PyiArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "Build FAILED (PyInstaller exit code $LASTEXITCODE)."
    exit $LASTEXITCODE
}

$Exe = Join-Path $OutDir "dist\PQ-SSE-Desktop\PQ-SSE-Desktop.exe"
if (Test-Path $Exe) {
    Write-Host ""
    Write-Host "Build OK."
    Write-Host "Run:  $Exe"
    Write-Host "The same executable is the cloud server when started with --cloud (the app does this for you)."
} else {
    Write-Host "Build finished but the executable was not found at $Exe."
    exit 1
}
