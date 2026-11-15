# Test a portable build (a folder or a portable zip) the way a user would have it:
#   - in a folder whose path has spaces and non-ASCII characters
#   - with a user profile whose path has non-ASCII characters (simulated through the
#     environment: LOCALAPPDATA, APPDATA, USERPROFILE, TEMP, TMP)
#   - the smoke test (which starts the cloud child process) must pass
#   - the window must really open, write its log, and leave no process behind
#   - no Windows Firewall rule for the program may appear
#
#   .\scripts\test_portable.ps1 -Zip <portable zip>
#   .\scripts\test_portable.ps1 -Folder <one-folder build>
#
# Nothing is installed and the real data folder is not used. Exit code 0 = all passed.

param(
    [string]$Zip = "",
    [string]$Folder = "",
    [string]$WorkDir = "$env:LOCALAPPDATA\PQ-SSE-Desktop-build\portable-test"
)

$ErrorActionPreference = "Stop"
$Failures = 0

function Check([bool]$Ok, [string]$Text) {
    if ($Ok) { Write-Host "  PASS  $Text" } else { Write-Host "  FAIL  $Text"; $script:Failures++ }
}

if (-not $Zip -and -not $Folder) { Write-Host "Pass -Zip <file> or -Folder <folder>."; exit 1 }

# Non-ASCII names are built from character codes so this script stays plain ASCII.
$Accent = [string][char]0x00E9                                             # e with acute accent
$Kana = ([string][char]0x30E6) + ([string][char]0x30FC) + ([string][char]0x30B6)   # three Japanese letters
$AppParent = Join-Path $WorkDir ("My Apps t" + $Accent + "st " + $Kana)
$Profile2 = Join-Path $WorkDir ("Us" + $Accent + "r " + $Kana)

if (Test-Path $WorkDir) { Remove-Item $WorkDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $AppParent, $Profile2 | Out-Null

if ($Zip) {
    Write-Host "Extracting $Zip"
    Expand-Archive -LiteralPath $Zip -DestinationPath $AppParent
    $Exe = Get-ChildItem $AppParent -Recurse -Filter "PQ-SSE-Desktop.exe" | Select-Object -First 1 -ExpandProperty FullName
} else {
    $Target = Join-Path $AppParent "PQ-SSE Desktop"
    Copy-Item $Folder $Target -Recurse
    $Exe = Join-Path $Target "PQ-SSE-Desktop.exe"
}
if (-not $Exe -or -not (Test-Path $Exe)) { Write-Host "FAIL: PQ-SSE-Desktop.exe not found in the test folder."; exit 1 }
Write-Host "Program under test: $Exe"
Check ($Exe -match " ") "the path contains spaces"
Check ($Exe -match "[^\x00-\x7F]") "the path contains non-ASCII characters"
if ($Zip) { Check (Test-Path (Join-Path (Split-Path $Exe) "PORTABLE-README.txt")) "PORTABLE-README.txt is in the zip" }

$SavedEnv = @{}
foreach ($Name in @("LOCALAPPDATA", "APPDATA", "USERPROFILE", "TEMP", "TMP", "PQSSE_DATA_DIR")) {
    $SavedEnv[$Name] = [Environment]::GetEnvironmentVariable($Name)
}
$Local2 = Join-Path $Profile2 "AppData\Local"
$Roaming2 = Join-Path $Profile2 "AppData\Roaming"
$Temp2 = Join-Path $Local2 "Temp"
New-Item -ItemType Directory -Force -Path $Local2, $Roaming2, $Temp2 | Out-Null
$DataDir = Join-Path $Local2 "PQ-SSE-Desktop"
$Report = Join-Path $WorkDir "smoke.txt"

try {
    $env:LOCALAPPDATA = $Local2; $env:APPDATA = $Roaming2; $env:USERPROFILE = $Profile2
    $env:TEMP = $Temp2; $env:TMP = $Temp2
    Remove-Item Env:PQSSE_DATA_DIR -ErrorAction SilentlyContinue

    Write-Host ""
    Write-Host "Smoke test (simulated profile: $Profile2):"
    $Proc = Start-Process -FilePath $Exe -ArgumentList @("--smoke-test", "--report", "`"$Report`"") -Wait -PassThru -WindowStyle Hidden
    if (Test-Path $Report) { Get-Content $Report | ForEach-Object { Write-Host "    $_" } }
    Check ($Proc.ExitCode -eq 0) "smoke test exit code is 0 (was $($Proc.ExitCode))"

    Write-Host ""
    Write-Host "Opening the real window:"
    $App = Start-Process -FilePath $Exe -PassThru
    $Deadline = (Get-Date).AddSeconds(60)
    $Shown = $false
    while ((Get-Date) -lt $Deadline -and -not $App.HasExited) {
        $App.Refresh()
        if ($App.MainWindowHandle -ne 0) { $Shown = $true; break }
        Start-Sleep -Milliseconds 300
    }
    Check $Shown "a window appeared (title: '$($App.MainWindowTitle)')"
    Start-Sleep -Seconds 3
    $App.Refresh()
    Check (-not $App.HasExited) "the program is still running after 3 seconds"
    Check $App.Responding "the window responds"
    $Log = Join-Path $DataDir "logs\app.log"
    Check (Test-Path $Log) "log file written to $Log"
    if (Test-Path $Log) { Check ((Get-Content $Log -Raw) -match "starting \(packaged\)") "the log has the start line" }
    Check (Test-Path (Join-Path $DataDir "settings.json")) "settings were written to the data folder under the profile"
    if (-not $App.HasExited) { Stop-Process -Id $App.Id -Force }
    Start-Sleep -Seconds 2
    $Left = @(Get-CimInstance Win32_Process -Filter "Name='PQ-SSE-Desktop.exe'" | Where-Object { $_.ExecutablePath -eq $Exe })
    Check ($Left.Count -eq 0) "no process of this copy is left running"
}
finally {
    foreach ($Name in $SavedEnv.Keys) { [Environment]::SetEnvironmentVariable($Name, $SavedEnv[$Name]) }
}

$AppDir = Split-Path $Exe
$Written = @(Get-ChildItem $AppDir -Recurse -File | Where-Object { $_.Extension -in ".sqlite", ".log", ".json" -and $_.FullName -notmatch "\\_internal\\" })
Check ($Written.Count -eq 0) "the program wrote nothing into its own folder"

try {
    $Rules = @(Get-NetFirewallApplicationFilter -ErrorAction Stop | Where-Object { $_.Program -eq $Exe })
    Check ($Rules.Count -eq 0) "no Windows Firewall rule exists for the program (a firewall prompt would have created one)"
} catch {
    Write-Host "  NOTE  the firewall rules could not be read on this PC: $($_.Exception.Message)"
}

Remove-Item $WorkDir -Recurse -Force -ErrorAction SilentlyContinue
Write-Host ""
if ($Failures -eq 0) { Write-Host "PORTABLE TEST: PASS"; exit 0 }
Write-Host "PORTABLE TEST: FAIL ($Failures check(s) failed)"
exit 1
