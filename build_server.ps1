# Build pqsse-server.exe, the cloud server as a Windows console program, and smoke-test it.
#
#   .\build_server.ps1                    build into %LOCALAPPDATA%\PQ-SSE-Desktop-build\server
#
# The program is a one-folder PyInstaller build without Qt, CuPy or the desktop app. It holds no keys and
# no data: those are made in the data folder named by its configuration at first start.
param(
    [string]$BuildRoot = "$env:LOCALAPPDATA\PQ-SSE-Desktop-build",
    [string]$Python = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Python) { $Python = Join-Path $BuildRoot "venv\Scripts\python.exe" }
if (-not (Test-Path $Python)) { Write-Host "FAILED: no build environment at $Python (run build_release.ps1 once)." -ForegroundColor Red; exit 1 }
$Out = Join-Path $BuildRoot "server"
if (Test-Path $Out) { Remove-Item $Out -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Out | Out-Null

& $Python -m PyInstaller --noconfirm --clean --console --onedir --name pqsse-server `
    --distpath (Join-Path $Out "dist") --workpath (Join-Path $Out "work") --specpath $Out `
    --paths $Root --add-data "$Root\pyproject.toml;." `
    --exclude-module PySide6 --exclude-module cupy --exclude-module pypdf --exclude-module tkinter `
    (Join-Path $Root "packaging\pqsse_server_entry.py") | Out-Host
if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: PyInstaller" -ForegroundColor Red; exit 1 }
$Exe = Join-Path $Out "dist\pqsse-server\pqsse-server.exe"
& $Python (Join-Path $Root "scripts\build_helpers.py") scan (Join-Path $Out "dist\pqsse-server") | Out-Host
if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: the build holds a key, database or settings file" -ForegroundColor Red; exit 1 }
& $Python (Join-Path $Root "scripts\server_smoke.py") --exe $Exe | Out-Host
if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: the server smoke test" -ForegroundColor Red; exit 1 }
$Size = (Get-ChildItem (Join-Path $Out "dist\pqsse-server") -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("SERVER BUILD OK: {0} ({1:N1} MB folder)" -f $Exe, $Size)
