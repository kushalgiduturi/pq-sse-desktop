; PQ-SSE Desktop installer (Inno Setup 6).
;
; Compiled by build_release.ps1, once per variant:
;   ISCC /DAppVersion=0.1.0 /DVariant=Standard /DSourceDir=<one-folder build> /DOutputDir=<folder>
;        /DOutputBase=PQ-SSE-Desktop-Setup-0.1.0 installer\pqsse.iss
;
; Per-user install by default, no admin rights. "Install for all users" asks for elevation.
; The same AppId is used for every version and both variants, so a new setup upgrades
; the existing install in place (also Standard over GPU and the other way round).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef Variant
  #define Variant "Standard"
#endif
#ifndef SourceDir
  #error Pass /DSourceDir=<folder that contains PQ-SSE-Desktop.exe>
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif
#ifndef OutputBase
  #define OutputBase "PQ-SSE-Desktop-Setup-" + AppVersion
#endif

#define AppName "PQ-SSE Desktop"
#define AppExe "PQ-SSE-Desktop.exe"
#define DataFolder "PQ-SSE-Desktop"

[Setup]
AppId={{6E0B2C54-9D7A-4F5E-8B21-3C4A7D95E1F0}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=PQ-SSE
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} Setup ({#Variant} build)
VersionInfoCompany=PQ-SSE
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableWelcomePage=no
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile=..\LICENSE
SetupIconFile=..\assets\pqsse.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBase}
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=yes
ShowLanguageDialog=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel1=Install {#AppName} {#AppVersion}
#if Variant == "GPU"
WelcomeLabel2=This installs {#AppName} {#AppVersion}, GPU build, for your Windows account. No admin rights are needed.%n%nWhat it is: a program for learning how encrypted documents can be searched through an untrusted cloud. It is research software. It has not been audited by security experts. Do not use it to protect real records.%n%nGPU build: it can use an NVIDIA graphics chip to speed up one step (building a large index). It needs a current NVIDIA driver for that. Without one it runs on the normal processor and tells you so.%n%nThis installer is not code signed, so Windows may have shown a warning before it started.%n%nYour data is kept separately in %LOCALAPPDATA%\{#DataFolder}. Installing, updating and uninstalling do not delete it.
#else
WelcomeLabel2=This installs {#AppName} {#AppVersion} for your Windows account. No admin rights are needed.%n%nWhat it is: a program for learning how encrypted documents can be searched through an untrusted cloud. It is research software. It has not been audited by security experts. Do not use it to protect real records.%n%nThis is the Standard build. It runs on the normal processor and does not use a graphics chip.%n%nThis installer is not code signed, so Windows may have shown a warning before it started.%n%nYour data is kept separately in %LOCALAPPDATA%\{#DataFolder}. Installing, updating and uninstalling do not delete it.
#endif

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[InstallDelete]
; Remove the libraries of the previous version so that no stale file stays behind
; (this also makes a switch between the Standard and the GPU build clean).
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\docs"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\scripts\stop_app.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "..\scripts\stop_app.ps1"; Flags: dontcopy

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
// Close the running app and its cloud child process, but only copies that run from the
// install folder. Restart Manager (CloseApplications) cannot close the windowless cloud
// child politely, so this runs first. If PowerShell is not allowed to run, fall back to
// ending every process with the program's name.
procedure StopRunningApp(const Script: String);
var
  ResultCode: Integer;
  Done: Boolean;
begin
  Done := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
               '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + Script + '" -Dir "' + ExpandConstant('{app}') + '"',
               '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if (not Done) or (ResultCode <> 0) then
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM {#AppExe}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if FileExists(ExpandConstant('{app}\{#AppExe}')) then
  begin
    ExtractTemporaryFile('stop_app.ps1');
    StopRunningApp(ExpandConstant('{tmp}\stop_app.ps1'));
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  if FileExists(ExpandConstant('{app}\tools\stop_app.ps1')) then
    StopRunningApp(ExpandConstant('{app}\tools\stop_app.ps1'));
end;

// The user's data (encrypted keys, databases, settings, logs) is never deleted silently.
// An interactive uninstall asks, and the default answer is No.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\{#DataFolder}');
    if DirExists(DataDir) and (not UninstallSilent) then
    begin
      if MsgBox('{#AppName} was removed.' + #13#10 + #13#10 +
                'Your data is still on this computer:' + #13#10 + DataDir + #13#10 + #13#10 +
                'It holds your encrypted keys, the stored documents, your settings and the log files. ' +
                'If you delete it, it cannot be brought back.' + #13#10 + #13#10 +
                'Delete this data too? Choose No to keep it (for example if you want to install again later).',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
