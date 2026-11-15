# Automated test of the installer on this PC. No admin rights, no clicks.
#
#   .\scripts\test_installer.ps1 -Setup <PQ-SSE-Desktop-Setup-x.y.z.exe> [-OlderSetup <older setup exe>]
#
# What it does:
#   1. (with -OlderSetup) installs the older version silently into a folder whose path has
#      a space, plants a stale file, starts the app and a cloud process from it
#   2. installs -Setup silently into the same folder (upgrade in place when step 1 ran)
#      and checks: running processes were closed, version updated, stale file removed
#   3. checks the Start Menu entries and the "Apps and features" uninstall entry
#   4. runs --smoke-test from the installed location and opens the real window
#   5. uninstalls silently while the app is running and checks: processes closed, files,
#      shortcuts and the uninstall entry are gone, the user data folder is untouched,
#      no Windows Firewall rule exists for the program
#
# The app is started with a temporary data folder, so your own data is never used.
# The test refuses to run if PQ-SSE Desktop is already installed (it would remove it);
# pass -Force to run anyway. Exit code 0 = every check passed.

param(
    [Parameter(Mandatory = $true)][string]$Setup,
    [string]$OlderSetup = "",
    [string]$WorkDir = "$env:LOCALAPPDATA\PQ-SSE-Desktop-build\installer-test",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$AppId = "{6E0B2C54-9D7A-4F5E-8B21-3C4A7D95E1F0}_is1"
$UninstallKeys = @("HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppId",
                   "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppId")
$Failures = 0

function Check([bool]$Ok, [string]$Text) {
    if ($Ok) { Write-Host "  PASS  $Text" } else { Write-Host "  FAIL  $Text"; $script:Failures++ }
}

function Get-Entry { foreach ($Key in $UninstallKeys) { if (Test-Path $Key) { return Get-ItemProperty $Key } }; return $null }

function Get-Ours([string]$Dir) {
    @(Get-CimInstance Win32_Process -Filter "Name='PQ-SSE-Desktop.exe'" |
        Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($Dir, [System.StringComparison]::OrdinalIgnoreCase) })
}

function Get-Snapshot([string]$Dir) {
    if (-not (Test-Path $Dir)) { return "absent" }
    $Lines = Get-ChildItem $Dir -Recurse -File -ErrorAction SilentlyContinue | Sort-Object FullName |
        ForEach-Object { "{0}|{1}|{2}" -f $_.FullName, $_.Length, $_.LastWriteTimeUtc.Ticks }
    return ($Lines -join "`n")
}

function Get-FreePort {
    $Listener = New-Object System.Net.Sockets.TcpListener ([System.Net.IPAddress]::Loopback, 0)
    $Listener.Start(); $Port = $Listener.LocalEndpoint.Port; $Listener.Stop()
    return $Port
}

function Install([string]$Exe, [string]$Dir, [string]$Log) {
    $Arguments = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", "/DIR=`"$Dir`"", "/LOG=`"$Log`"")
    return (Start-Process -FilePath $Exe -ArgumentList $Arguments -Wait -PassThru).ExitCode
}

function Start-AppWindow([string]$Exe) {
    $App = Start-Process -FilePath $Exe -PassThru
    $Deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $Deadline -and -not $App.HasExited) {
        $App.Refresh()
        if ($App.MainWindowHandle -ne 0) { break }
        Start-Sleep -Milliseconds 300
    }
    return $App
}

if (-not (Test-Path $Setup)) { Write-Host "Setup file not found: $Setup"; exit 1 }
if ((Get-Entry) -and -not $Force) {
    Write-Host "PQ-SSE Desktop is already installed on this PC. This test would upgrade and then remove it."
    Write-Host "Uninstall it first, or pass -Force if that is what you want."
    exit 1
}

$Admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
$InstallDir = Join-Path $WorkDir "Install Test Dir\PQ-SSE Desktop"
$Exe = Join-Path $InstallDir "PQ-SSE-Desktop.exe"
$TempData = Join-Path $WorkDir "temp-data"
$RealData = Join-Path $env:LOCALAPPDATA "PQ-SSE-Desktop"
$StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\PQ-SSE Desktop"
$Desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "PQ-SSE Desktop.lnk"
$NewVersion = (Get-Item $Setup).VersionInfo.ProductVersion.Trim()

if (Test-Path $WorkDir) { Remove-Item $WorkDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $WorkDir, $TempData | Out-Null
$DataBefore = Get-Snapshot $RealData
$SavedData = $env:PQSSE_DATA_DIR
$env:PQSSE_DATA_DIR = $TempData

Write-Host "Installer under test: $Setup (version $NewVersion)"
Write-Host "Install folder:        $InstallDir"
Check (-not $Admin) "running without admin rights"

try {
    if ($OlderSetup) {
        $OldVersion = (Get-Item $OlderSetup).VersionInfo.ProductVersion.Trim()
        Write-Host ""
        Write-Host "1. Install the older version $OldVersion and start it"
        $Code = Install $OlderSetup $InstallDir (Join-Path $WorkDir "install-older.log")
        Check ($Code -eq 0) "older setup exit code is 0 (was $Code)"
        Check (Test-Path $Exe) "older version installed"
        $Entry = Get-Entry
        Check ($Entry -and $Entry.DisplayVersion -eq $OldVersion) "uninstall entry shows version $OldVersion"
        Set-Content (Join-Path $InstallDir "_internal\stale-from-older-version.txt") "left over" -Encoding ASCII
        $OldApp = Start-AppWindow $Exe
        Check ($OldApp.MainWindowHandle -ne 0) "the older app window is open"
        $env:PQSSE_CLOUD_PASSPHRASE = "installer-test-only"
        $Port = Get-FreePort
        $CloudArgs = @("--cloud", "--port", "$Port", "--db", "`"$(Join-Path $TempData 'cloud-test.sqlite')`"",
                       "--pub", "`"$(Join-Path $TempData 'cloud-test.pqpub')`"")
        $OldCloud = Start-Process -FilePath $Exe -ArgumentList $CloudArgs -PassThru -WindowStyle Hidden
        Remove-Item Env:PQSSE_CLOUD_PASSPHRASE
        Start-Sleep -Seconds 4
        Check (-not $OldCloud.HasExited) "a cloud process of the older version is running (port $Port)"
        Check ((Get-Ours $InstallDir).Count -ge 2) "app and cloud process are running from the install folder"
        Write-Host ""
        Write-Host "2. Upgrade in place to $NewVersion while both are running"
    } else {
        Write-Host ""
        Write-Host "2. Install $NewVersion"
    }

    $Code = Install $Setup $InstallDir (Join-Path $WorkDir "install.log")
    Check ($Code -eq 0) "setup exit code is 0 (was $Code)"
    Check (Test-Path $Exe) "program file exists: $Exe"
    Check ($InstallDir -match " ") "the install path contains a space"
    if ($OlderSetup) {
        Check ((Get-Ours $InstallDir).Count -eq 0) "the running app and its cloud process were closed by the installer"
        Check (-not (Test-Path (Join-Path $InstallDir "_internal\stale-from-older-version.txt"))) "stale file of the older version was removed"
    }
    if (Test-Path $Exe) {
        $FileVersion = (Get-Item $Exe).VersionInfo.ProductVersion.Trim()
        Check ($FileVersion -eq $NewVersion) "installed program reports version $NewVersion (reports $FileVersion)"
        Check ((Get-Item $Exe).VersionInfo.CompanyName -eq "PQ-SSE") "version resource has the company name PQ-SSE"
    }

    Write-Host ""
    Write-Host "3. Start Menu and uninstall entry"
    $Entry = Get-Entry
    Check ($null -ne $Entry) "uninstall entry exists (Apps and features)"
    if ($Entry) {
        Check ($Entry.DisplayName -eq "PQ-SSE Desktop") "entry name is 'PQ-SSE Desktop'"
        Check ($Entry.DisplayVersion -eq $NewVersion) "entry version is $NewVersion (is $($Entry.DisplayVersion))"
        Check ($Entry.PSPath -like "*HKEY_CURRENT_USER*") "entry is per user (HKCU), no admin install"
        Check (Test-Path ($Entry.UninstallString.Trim('"'))) "the uninstaller exists"
    }
    $AppLink = Join-Path $StartMenu "PQ-SSE Desktop.lnk"
    Check (Test-Path $AppLink) "Start Menu shortcut exists"
    Check (Test-Path (Join-Path $StartMenu "Uninstall PQ-SSE Desktop.lnk")) "Start Menu uninstall shortcut exists"
    if (Test-Path $AppLink) {
        $Target = (New-Object -ComObject WScript.Shell).CreateShortcut($AppLink).TargetPath
        Check ($Target -eq $Exe) "the shortcut points to the installed program"
    }
    Check (-not (Test-Path $Desktop)) "no desktop shortcut by default"

    Write-Host ""
    Write-Host "4. Run the installed program"
    $Report = Join-Path $WorkDir "smoke-installed.txt"
    $Proc = Start-Process -FilePath $Exe -ArgumentList @("--smoke-test", "--report", "`"$Report`"") -Wait -PassThru -WindowStyle Hidden
    if (Test-Path $Report) { Get-Content $Report | ForEach-Object { Write-Host "    $_" } }
    Check ($Proc.ExitCode -eq 0) "smoke test from the installed location passes (exit code $($Proc.ExitCode))"
    $App = Start-AppWindow $Exe
    Check ($App.MainWindowHandle -ne 0) "the installed app opens its window (title: '$($App.MainWindowTitle)')"
    Start-Sleep -Seconds 2
    $Written = @(Get-ChildItem $InstallDir -Recurse -File | Where-Object { $_.Extension -in ".sqlite", ".log", ".json" -and $_.FullName -notmatch "\\_internal\\" })
    Check ($Written.Count -eq 0) "the program wrote nothing into its install folder"

    Write-Host ""
    Write-Host "5. Uninstall silently while the app is running"
    $Uninstaller = Join-Path $InstallDir "unins000.exe"
    $Code = (Start-Process -FilePath $Uninstaller -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -Wait -PassThru).ExitCode
    Check ($Code -eq 0) "uninstaller exit code is 0 (was $Code)"
    $Deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $Deadline -and (Test-Path $InstallDir)) { Start-Sleep -Milliseconds 500 }
    Check ((Get-Ours $InstallDir).Count -eq 0) "the running app was closed by the uninstaller"
    Check (-not (Test-Path $InstallDir)) "the install folder is gone"
    Check (-not (Test-Path $StartMenu)) "the Start Menu entries are gone"
    Check (-not (Test-Path $Desktop)) "no desktop shortcut is left"
    Check ($null -eq (Get-Entry)) "the uninstall entry is gone"
    Check ((Get-Snapshot $RealData) -eq $DataBefore) "the user data folder $RealData is untouched (silent uninstall never deletes it)"
    Check (Test-Path $TempData) "the data folder the test app used is still there (uninstall keeps data)"
    try {
        $Rules = @(Get-NetFirewallApplicationFilter -ErrorAction Stop | Where-Object { $_.Program -eq $Exe })
        Check ($Rules.Count -eq 0) "no Windows Firewall rule exists for the program (a firewall prompt would have created one)"
    } catch {
        Write-Host "  NOTE  the firewall rules could not be read on this PC: $($_.Exception.Message)"
    }
}
finally {
    if ($SavedData) { $env:PQSSE_DATA_DIR = $SavedData } else { Remove-Item Env:PQSSE_DATA_DIR -ErrorAction SilentlyContinue }
    Remove-Item Env:PQSSE_CLOUD_PASSPHRASE -ErrorAction SilentlyContinue
    Get-Ours $InstallDir | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

Write-Host ""
if ($Failures -eq 0) {
    Remove-Item $WorkDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "INSTALLER TEST: PASS"
    exit 0
}
Write-Host "INSTALLER TEST: FAIL ($Failures check(s) failed). Logs are in $WorkDir"
exit 1
