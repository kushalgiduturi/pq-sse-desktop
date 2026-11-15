# Close PQ-SSE Desktop and its cloud child process, but only the copies that run from
# one given folder. Used by the installer (before files are replaced) and by the
# uninstaller. A portable copy running from another folder is left alone.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File stop_app.ps1 -Dir "C:\...\PQ-SSE Desktop"
#
# Order: ask each window to close (the app then stops its cloud child cleanly), wait,
# then end whatever is still running. Exit code 0 = nothing is left running.
# Plain ASCII on purpose: it must run under Windows PowerShell 5.1.

param(
    [Parameter(Mandatory = $true)][string]$Dir,
    [int]$WaitSeconds = 8
)

$ErrorActionPreference = "SilentlyContinue"
$Prefix = $Dir.TrimEnd("\") + "\"

function Get-Ours {
    @(Get-CimInstance Win32_Process -Filter "Name='PQ-SSE-Desktop.exe'" | Where-Object {
        $_.ExecutablePath -and $_.ExecutablePath.StartsWith($Prefix, [System.StringComparison]::OrdinalIgnoreCase)
    })
}

$Running = Get-Ours
if ($Running.Count -eq 0) { exit 0 }

foreach ($Item in $Running) {
    if ($Item.CommandLine -notmatch "--cloud") {
        $Proc = Get-Process -Id $Item.ProcessId
        if ($Proc -and $Proc.MainWindowHandle -ne 0) { [void]$Proc.CloseMainWindow() }
    }
}

$Deadline = (Get-Date).AddSeconds($WaitSeconds)
while ((Get-Date) -lt $Deadline -and (Get-Ours).Count -gt 0) { Start-Sleep -Milliseconds 250 }

foreach ($Item in Get-Ours) { Stop-Process -Id $Item.ProcessId -Force }

$Deadline = (Get-Date).AddSeconds(5)
while ((Get-Date) -lt $Deadline -and (Get-Ours).Count -gt 0) { Start-Sleep -Milliseconds 250 }

if ((Get-Ours).Count -eq 0) { exit 0 }
exit 1
