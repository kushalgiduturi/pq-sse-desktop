; A tiny stand-in for the full installer, used only by tests/test_m13_web_setup.py.
; It installs one file and records the command line it was given in marker.txt.

[Setup]
AppId={{D3C1A0B2-7E44-4F2A-9B6E-11A0C0FFEE01}
AppName=PQ-SSE Fake Package
AppVersion=9.9.9
DefaultDirName={localappdata}\PQ-SSE-Fake-Package
PrivilegesRequired=lowest
Uninstallable=no
DisableProgramGroupPage=yes
OutputBaseFilename=fake-package
Compression=lzma2/fast

[Files]
Source: "fake-package.iss"; DestDir: "{app}"; DestName: "PQ-SSE-Desktop.exe"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    SaveStringToFile(ExpandConstant('{app}\marker.txt'), GetCmdTail, False);
end;
