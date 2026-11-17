; PQ-SSE Desktop web installer (Inno Setup 6.7): a small setup that downloads the right full
; installer for this PC from the official release, checks it, runs it and offers to start the app.
;
; Built by scripts/build_web_setup.py, which passes every value below from packaging/release.toml
; and the public signing key. Do not compile by hand without those defines.
;
; What it checks, in this order:
;   1. latest.json is downloaded from ManifestUrl only, over HTTPS, and must carry a valid
;      Inno Setup signature (.issig) made with the private key that belongs to the public key
;      built into this file. An unsigned or changed manifest is refused.
;   2. Every URL, and every redirect, must stay on the hosts in AllowedHosts. Redirects are
;      followed one by one by this script (WinHTTP, redirects switched off) and checked before
;      the next request.
;   3. The package must match the SHA-256 and size in the signed manifest, and its own .issig.
;      Nothing is run before both checks pass.
; This is not Authenticode code signing: Windows still names the publisher as unknown.

#ifndef AppVersion
  #error Pass /DAppVersion (scripts/build_web_setup.py does this)
#endif
#ifndef ManifestUrl
  #error Pass /DManifestUrl
#endif
#ifndef AllowedHosts
  #error Pass /DAllowedHosts=host1;host2
#endif
#ifndef MinDriver
  #define MinDriver "528.33"
#endif
#ifndef KeyInclude
  #error Pass /DKeyInclude=<file with the [ISSigKeys] entry>
#endif
#ifndef DownloadPageUrl
  #define DownloadPageUrl "https://kushalgiduturi.github.io/pq-sse-desktop/download.html"
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif
#ifndef OutputBase
  #define OutputBase "PQ-SSE-Web-Setup"
#endif
; TestBuild: allows http:// and the /TESTGPU= and /LOGFILE= parameters, for the local tests only.

[Setup]
AppId={{2B7E4F61-0C3A-4D9B-9E58-7A1F3C6D2E90}
AppName=PQ-SSE Desktop web installer
AppVersion={#AppVersion}
AppVerName=PQ-SSE Desktop web installer {#AppVersion}
AppPublisher=PQ-SSE
VersionInfoVersion={#AppVersion}
VersionInfoProductName=PQ-SSE Desktop
VersionInfoDescription=PQ-SSE Desktop web installer
VersionInfoCompany=PQ-SSE
CreateAppDir=no
Uninstallable=no
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableWelcomePage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
SetupIconFile=..\assets\pqsse.ico
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBase}
ShowLanguageDialog=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
SetupAppTitle=PQ-SSE Desktop setup
SetupWindowTitle=PQ-SSE Desktop setup
WelcomeLabel1=Install PQ-SSE Desktop
WelcomeLabel2=This small setup downloads PQ-SSE Desktop for your Windows account and installs it. No admin rights are needed.%n%nWhat it is: a program for learning how encrypted documents can be searched through an untrusted cloud. It is research software and has not been audited. Do not use it to protect real records.%n%nWhat happens next: it reads the list of current files from the PQ-SSE website, checks that list's signature, downloads the right installer for this PC, and checks the download against the list before running anything.%n%nThis setup is not code signed, so Windows may have shown a warning before it started.
WinVersionTooLowError=PQ-SSE Desktop needs 64-bit Windows 10 version 1809 or newer, or Windows 11.
FinishedHeadingLabel=PQ-SSE Desktop is installed
FinishedLabelNoIcons=PQ-SSE Desktop was downloaded, checked and installed for your Windows account.
FinishedLabel=PQ-SSE Desktop was downloaded, checked and installed for your Windows account.

#include KeyInclude

[Run]
Filename: "{code:InstalledExe}"; Description: "Start PQ-SSE Desktop"; Flags: postinstall nowait skipifsilent; Check: AppInstalled

[Code]
const
  AppUninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{6E0B2C54-9D7A-4F5E-8B21-3C4A7D95E1F0}_is1';
  WinHttpOptionEnableRedirects = 6;

var
  ChoicePage: TInputOptionWizardPage;
  DownloadPage: TDownloadWizardPage;
  Manifest: String;
  ManifestLoaded, GpuUsable, GpuInManifest: Boolean;
  GpuReason, InstallError, InstalledPath, LogFile: String;
  StdUrl, StdSha, StdSize, GpuUrl, GpuSha, GpuSize, Version: String;
  CopyButton: TNewButton;

// ------------------------------------------------------------------ log
procedure Note(const Text: String);
begin
  Log(Text);
  if LogFile <> '' then
    SaveStringToFile(LogFile, GetDateTimeString('yyyy/mm/dd hh:nn:ss', '-', ':') + '  ' + Text + #13#10, True);
end;

procedure InitLog;
begin
  LogFile := '';
#ifdef TestBuild
  LogFile := ExpandConstant('{param:LOGFILE|}');
#endif
  if LogFile = '' then
    LogFile := ExpandConstant('{localappdata}\PQ-SSE-Desktop\logs\web-setup.log');
  ForceDirectories(ExtractFileDir(LogFile));
  Note('PQ-SSE Desktop web installer {#AppVersion} started');
end;

// ------------------------------------------------------------------ small JSON reader
// Reads the fields this setup needs from latest.json, which scripts/make_manifest.py writes.
// Values are strings, numbers or true/false; objects are found by name inside their parent.
function JsonObject(const Json, Name: String): String;
var P, Depth, I: Integer;
begin
  Result := '';
  P := Pos('"' + Name + '"', Json);
  if P = 0 then exit;
  I := P + Length(Name) + 2;
  while (I <= Length(Json)) and (Json[I] <> '{') do begin
    if (Json[I] <> ' ') and (Json[I] <> ':') and (Json[I] <> #13) and (Json[I] <> #10) and (Json[I] <> #9) then exit;
    I := I + 1;
  end;
  Depth := 0;
  P := I;
  while I <= Length(Json) do begin
    if Json[I] = '{' then Depth := Depth + 1
    else if Json[I] = '}' then begin
      Depth := Depth - 1;
      if Depth = 0 then begin Result := Copy(Json, P, I - P + 1); exit; end;
    end;
    I := I + 1;
  end;
end;

function JsonValue(const Obj, Name: String): String;
var P, I: Integer;
begin
  Result := '';
  P := Pos('"' + Name + '"', Obj);
  if P = 0 then exit;
  I := P + Length(Name) + 2;
  while (I <= Length(Obj)) and ((Obj[I] = ' ') or (Obj[I] = ':')) do I := I + 1;
  if (I <= Length(Obj)) and (Obj[I] = '"') then begin
    I := I + 1;
    P := I;
    while (I <= Length(Obj)) and (Obj[I] <> '"') do I := I + 1;
    Result := Copy(Obj, P, I - P);
  end else begin
    P := I;
    while (I <= Length(Obj)) and (Obj[I] <> ',') and (Obj[I] <> '}') and (Obj[I] <> #13) and (Obj[I] <> #10) do I := I + 1;
    Result := Trim(Copy(Obj, P, I - P));
  end;
end;

function SizeText(const Bytes: String): String;
var B: Int64;
begin
  B := StrToInt64Def(Bytes, 0);
  Result := Format('%d.%d MB', [B div 1048576, (B mod 1048576) * 10 div 1048576]);
end;

// ------------------------------------------------------------------ hosts and redirects
function UrlHost(const Url: String): String;
var Rest: String; P: Integer;
begin
  Result := '';
  P := Pos('://', Url);
  if P = 0 then exit;
  Rest := Copy(Url, P + 3, Length(Url));
  P := Pos('/', Rest);
  if P > 0 then Rest := Copy(Rest, 1, P - 1);
  P := Pos('@', Rest);
  if P > 0 then exit;                      // no user info in URLs
  P := Pos(':', Rest);
  if P > 0 then Rest := Copy(Rest, 1, P - 1);
  Result := Lowercase(Rest);
end;

function UrlAllowed(const Url: String): Boolean;
var Hosts, Host: String;
begin
  Result := False;
#ifdef TestBuild
  if (Pos('https://', Lowercase(Url)) <> 1) and (Pos('http://', Lowercase(Url)) <> 1) then exit;
#else
  if Pos('https://', Lowercase(Url)) <> 1 then exit;
#endif
  Host := UrlHost(Url);
  if Host = '' then exit;
  Hosts := ';' + Lowercase('{#AllowedHosts}') + ';';
  Result := Pos(';' + Host + ';', Hosts) > 0;
end;

// Follows redirects one at a time with WinHTTP (its own redirect following switched off), so
// that a redirect to a host outside the list is refused before anything is fetched from it.
function ResolveUrl(const Url: String; var Final, Error: String): Boolean;
var Req: Variant; Hop, Status: Integer; Current, Location: String;
begin
  Result := False;
  Current := Url;
  for Hop := 1 to 8 do begin
    if not UrlAllowed(Current) then begin
      Error := 'The address ' + Current + ' is not on the list of official PQ-SSE hosts, so it was not used.';
      Note('Refused host: ' + Current);
      exit;
    end;
    try
      Req := CreateOleObject('WinHttp.WinHttpRequest.5.1');
      Req.Option(WinHttpOptionEnableRedirects) := False;
      Req.SetTimeouts(15000, 15000, 15000, 30000);
      Req.Open('HEAD', Current, False);
      Req.Send('');
      Status := Req.Status;
    except
      Error := 'No connection to the PQ-SSE download server (' + GetExceptionMessage + ').';
      Note('HEAD failed: ' + Current + ': ' + GetExceptionMessage);
      exit;
    end;
    if (Status >= 300) and (Status < 400) then begin
      Location := Req.GetResponseHeader('Location');
      Note(Format('Redirect %d: %s -> %s', [Status, Current, Location]));
      if Pos('://', Location) = 0 then begin
        Error := 'The server sent a redirect this setup does not follow.';
        exit;
      end;
      Current := Location;
    end else if (Status >= 200) and (Status < 300) then begin
      Final := Current;
      Result := True;
      exit;
    end else begin
      Error := Format('The download server answered with HTTP status %d.', [Status]);
      Note(Format('HTTP %d for %s', [Status, Current]));
      exit;
    end;
  end;
  Error := 'Too many redirects.';
end;

// ------------------------------------------------------------------ GPU detection
// Reads the video controllers through WMI. NVIDIA's Windows driver version such as
// 31.0.15.2833 corresponds to the driver release 528.33 (the last five digits).
function DriverRelease(const DriverVersion: String): Integer;
var S, Digits: String; I: Integer;
begin
  Result := 0;
  S := DriverVersion;
  Digits := '';
  for I := 1 to Length(S) do
    if (S[I] >= '0') and (S[I] <= '9') then Digits := Digits + S[I]
    else if S[I] = '.' then Digits := Digits + '.';
  // keep the last two parts and join them
  I := Length(Digits);
  while (I > 0) and (Digits[I] <> '.') do I := I - 1;
  S := Copy(Digits, I + 1, Length(Digits));
  Digits := Copy(Digits, 1, I - 1);
  I := Length(Digits);
  while (I > 0) and (Digits[I] <> '.') do I := I - 1;
  S := Copy(Digits, I + 1, Length(Digits)) + S;
  if Length(S) < 5 then exit;
  S := Copy(S, Length(S) - 4, 5);
  Result := StrToIntDef(S, 0);              // 52833 for 528.33
end;

function MinDriverRelease: Integer;
var S: String; P: Integer;
begin
  S := '{#MinDriver}';
  P := Pos('.', S);
  Result := StrToIntDef(Copy(S, 1, P - 1), 0) * 100 + StrToIntDef(Copy(S, P + 1, 2), 0);
end;

procedure DetectGpu;
var Locator, Service, Items, Item: Variant; I, Best, Release: Integer; Name, Ver, Simulated: String;
begin
  GpuUsable := False;
  GpuReason := 'No NVIDIA graphics chip was found.';
  Best := 0;
#ifdef TestBuild
  Simulated := ExpandConstant('{param:TESTGPU|}');
  if Simulated <> '' then begin
    if Simulated = 'none' then begin Note('GPU detection (test): none'); exit; end;
    Best := DriverRelease(Simulated);
    Note('GPU detection (test): driver ' + Simulated);
  end else begin
#endif
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Service := Locator.ConnectServer('.', 'root\CIMV2');
    Items := Service.ExecQuery('SELECT Name, DriverVersion FROM Win32_VideoController');
    for I := 0 to Items.Count - 1 do begin
      Item := Items.ItemIndex(I);
      Name := Item.Name;
      Ver := Item.DriverVersion;
      Note('Video controller: ' + Name + ', driver ' + Ver);
      if Pos('NVIDIA', Uppercase(Name)) > 0 then begin
        Release := DriverRelease(Ver);
        if Release > Best then Best := Release;
      end;
    end;
  except
    Note('GPU detection failed: ' + GetExceptionMessage);
    GpuReason := 'The graphics chip could not be detected.';
    exit;
  end;
#ifdef TestBuild
  end;
#endif
  if Best = 0 then exit;
  if Best >= MinDriverRelease then begin
    GpuUsable := True;
    GpuReason := Format('NVIDIA driver %d.%.2d found.', [Best div 100, Best mod 100]);
  end else
    GpuReason := Format('NVIDIA driver %d.%.2d is older than {#MinDriver}, the minimum for the GPU build.', [Best div 100, Best mod 100]);
  Note('GPU: ' + GpuReason);
end;

// ------------------------------------------------------------------ downloads
function AllowedKeys: TStringList;
begin
  Result := TStringList.Create;
  Result.Add('pqsse_release');
end;

// Downloads Url (and its .issig) into {tmp}\BaseName after checking every host on the way.
function Fetch(const Url, BaseName: String; var Error: String): Boolean;
var FinalUrl, FinalSig, Unused: String; Keys: TStringList;
begin
  Result := False;
  if not ResolveUrl(Url, FinalUrl, Error) then begin
    Note('Stopped: ' + Error);
    exit;
  end;
  if not ResolveUrl(Url + '.issig', FinalSig, Unused) then begin
    Error := 'The signature file for ' + BaseName + ' could not be reached. ' + Unused;
    Note('Stopped: ' + Error);
    exit;
  end;
  Keys := AllowedKeys;
  DownloadPage.Clear;
  DownloadPage.AddWithISSigVerify(FinalUrl, FinalSig, BaseName, Keys);
  if not WizardSilent then DownloadPage.Show;
  try
    try
      DownloadPage.Download;
      Result := True;
      Note('Downloaded and signature checked: ' + BaseName);
    except
      if DownloadPage.AbortedByUser then
        Error := 'The download was cancelled.'
      else
        Error := 'The download of ' + BaseName + ' failed or did not pass the signature check: ' + GetExceptionMessage;
      Note(Error);
    end;
  finally
    if not WizardSilent then DownloadPage.Hide;
    Keys.Free;
  end;
end;

function LoadManifest(var Error: String): Boolean;
var Channels, Std, Gpu: String; Raw: AnsiString;
begin
  Result := ManifestLoaded;
  if ManifestLoaded then exit;
  Note('Manifest: {#ManifestUrl}');
  if not Fetch('{#ManifestUrl}', 'latest.json', Error) then exit;
  if not LoadStringFromFile(ExpandConstant('{tmp}\latest.json'), Raw) then begin
    Error := 'The file list could not be read.';
    exit;
  end;
  Manifest := String(Raw);
  if JsonValue(Manifest, 'schema') <> '1' then begin
    Error := 'The file list has a format this setup does not know. Download the full installer instead.';
    exit;
  end;
  Version := JsonValue(Manifest, 'version');
  Channels := JsonObject(Manifest, 'channels');
  Std := JsonObject(Channels, 'standard');
  Gpu := JsonObject(Channels, 'gpu');
  StdUrl := JsonValue(Std, 'url'); StdSha := Lowercase(JsonValue(Std, 'sha256')); StdSize := JsonValue(Std, 'size');
  GpuInManifest := JsonValue(Gpu, 'available') = 'true';
  if GpuInManifest then begin
    GpuUrl := JsonValue(Gpu, 'url'); GpuSha := Lowercase(JsonValue(Gpu, 'sha256')); GpuSize := JsonValue(Gpu, 'size');
  end;
  if (StdUrl = '') or (Length(StdSha) <> 64) then begin
    Error := 'The file list is incomplete.';
    exit;
  end;
  if GpuInManifest then Note('Manifest OK: version ' + Version + ', GPU build available')
  else Note('Manifest OK: version ' + Version + ', GPU build not available');
  ManifestLoaded := True;
  Result := True;
end;

// ------------------------------------------------------------------ choice
function BuildName(Gpu: Boolean): String;
begin
  if Gpu then Result := 'GPU' else Result := 'Standard';
end;

function LastPart(const Url: String): String;
var I: Integer;
begin
  I := Length(Url);
  while (I > 0) and (Url[I] <> '/') do I := I - 1;
  Result := Copy(Url, I + 1, Length(Url));
end;

function ChosenGpu: Boolean;
var Forced: String;
begin
  Forced := Lowercase(ExpandConstant('{param:CHANNEL|}'));
  if Forced = 'gpu' then Result := GpuInManifest
  else if Forced = 'standard' then Result := False
  else if WizardSilent or (ChoicePage = nil) then Result := GpuUsable and GpuInManifest
  else Result := ChoicePage.Values[1] and GpuInManifest;
end;

procedure FillChoices;
begin
  ChoicePage.CheckListBox.ItemCaption[0] := 'Standard build (' + SizeText(StdSize) + ')';
  ChoicePage.CheckListBox.ItemSubItem[0] := 'Runs on the normal processor. Works on every PC.';
  if GpuInManifest then begin
    ChoicePage.CheckListBox.ItemCaption[1] := 'GPU build (' + SizeText(GpuSize) + ')';
    ChoicePage.CheckListBox.ItemSubItem[1] := 'Can use an NVIDIA graphics chip for one step. ' + GpuReason;
    ChoicePage.CheckListBox.ItemEnabled[1] := True;
  end else begin
    ChoicePage.CheckListBox.ItemCaption[1] := 'GPU build (not available yet)';
    ChoicePage.CheckListBox.ItemSubItem[1] := 'This release has no GPU build. The Standard build runs on every PC.';
    ChoicePage.CheckListBox.ItemEnabled[1] := False;
  end;
  if GpuUsable and GpuInManifest then ChoicePage.SelectedValueIndex := 1 else ChoicePage.SelectedValueIndex := 0;
  ChoicePage.SubCaptionLabel.Caption := 'PQ-SSE Desktop ' + Version + '. Recommended for this PC: '
    + BuildName(GpuUsable and GpuInManifest) + ' build. You can change this.';
end;

procedure InitializeWizard;
begin
  InitLog;
  DetectGpu;
  DownloadPage := CreateDownloadPage('Downloading', 'The file is checked against the signed list before anything runs.', nil);
  DownloadPage.ShowBaseNameInsteadOfUrl := True;
  ChoicePage := CreateInputOptionPage(wpWelcome, 'Choose the build', '', '', True, False);
  ChoicePage.Add('Standard build');
  ChoicePage.Add('GPU build');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var Error: String;
begin
  Result := True;
  if CurPageID = wpWelcome then begin
    if not LoadManifest(Error) then begin
      InstallError := Error;
      Note('Stopped: ' + Error);
      SuppressibleMsgBox(Error + #13#10#13#10 + 'You can download the full installer instead: {#DownloadPageUrl}', mbError, MB_OK, IDOK);
      Result := False;
      exit;
    end;
    FillChoices;
  end;
end;

// ------------------------------------------------------------------ install
function SilentSwitch: String;
var I: Integer;
begin
  Result := '/VERYSILENT';
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/SILENT') = 0 then Result := '/SILENT';
  if not WizardSilent then Result := '/VERYSILENT';
end;

function RunInstaller(const Path: String; var Error: String): Boolean;
var Params, Dir: String; Code: Integer;
begin
  Result := False;
  Params := SilentSwitch + ' /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER /CLOSEAPPLICATIONS';
  Dir := ExpandConstant('{param:DIR|}');
  if Dir <> '' then Params := Params + ' /DIR="' + Dir + '"';
  Params := Params + ' /LOG="' + ExtractFileDir(LogFile) + '\setup-run.log"';
  Note('Running ' + ExtractFileName(Path) + ' ' + Params);
  if not Exec(Path, Params, '', SW_SHOWNORMAL, ewWaitUntilTerminated, Code) then begin
    Error := 'The installer could not be started: ' + SysErrorMessage(Code);
    Note(Error);
    exit;
  end;
  Note(Format('Installer exit code %d', [Code]));
  if Code <> 0 then begin
    Error := Format('The installer stopped with exit code %d. Its log is setup-run.log next to web-setup.log.', [Code]);
    exit;
  end;
  if Dir <> '' then InstalledPath := AddBackslash(Dir) + 'PQ-SSE-Desktop.exe'
  else if RegQueryStringValue(HKCU, AppUninstallKey, 'InstallLocation', InstalledPath) then
    InstalledPath := AddBackslash(InstalledPath) + 'PQ-SSE-Desktop.exe';
  Result := True;
end;

// If the package carries an Authenticode signature, Windows must find it valid. An unsigned
// package is accepted (the SHA-256 and .issig checks have already passed); a signature that is
// present but broken (changed file, revoked or untrusted certificate) is refused.
function AuthenticodeOk(const Path: String; var Error: String): Boolean;
var Code: Integer; Text: AnsiString; Status, OutFile, Command: String;
begin
  Result := True;
  OutFile := ExpandConstant('{tmp}\authenticode.txt');
  Command := '-NoProfile -NonInteractive -Command "(Get-AuthenticodeSignature -LiteralPath ''' + Path
    + ''').Status | Out-File -Encoding ascii ''' + OutFile + '''"';
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Command, '', SW_HIDE, ewWaitUntilTerminated, Code)
     or (Code <> 0) or not LoadStringFromFile(OutFile, Text) then begin
    Note('Authenticode: could not be checked on this PC');
    exit;
  end;
  Status := Trim(String(Text));
  Note('Authenticode: ' + Status);
  if (Status <> 'NotSigned') and (Status <> 'Valid') then begin
    Error := 'The installer carries a code signature that Windows does not accept (' + Status + '). It was not run.';
    Result := False;
  end;
end;

function FileBytes(const Path: String): String;
var Bytes: Int64;
begin
  if FileSize64(Path, Bytes) then Result := IntToStr(Bytes) else Result := '';
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var Url, Sha, Size, BaseName, Path, Error: String; Gpu: Boolean;
begin
  Result := '';
  if not LoadManifest(Error) then begin
    InstallError := Error;
    Result := Error + #13#10#13#10 + 'Nothing was installed. You can download the full installer instead: {#DownloadPageUrl}';
    exit;
  end;
  Gpu := ChosenGpu;
  if Gpu then begin Url := GpuUrl; Sha := GpuSha; Size := GpuSize; end
  else begin Url := StdUrl; Sha := StdSha; Size := StdSize; end;
  BaseName := LastPart(Url);
  if (BaseName = '') or (Pos('?', BaseName) > 0) or (Pos('', BaseName) > 0) then begin
    InstallError := 'The file list names a file this setup does not accept.';
    Result := InstallError;
    exit;
  end;
  Note(Format('Chosen: %s build, %s, %s bytes', [BuildName(Gpu), BaseName, Size]));
  if not Fetch(Url, BaseName, Error) then begin
    InstallError := Error;
    Result := Error + #13#10#13#10 + 'Nothing was run. You can download the full installer instead: {#DownloadPageUrl}';
    exit;
  end;
  Path := ExpandConstant('{tmp}\' + BaseName);
  if (Lowercase(GetSHA256OfFile(Path)) <> Sha) or (FileBytes(Path) <> Size) then begin
    DeleteFile(Path);
    Error := 'The download does not match the SHA-256 in the signed file list. It was deleted and not run.';
    Note(Error);
    InstallError := Error;
    Result := Error;
    exit;
  end;
  Note('SHA-256 matches the manifest: ' + Sha);
  if not AuthenticodeOk(Path, Error) then begin
    DeleteFile(Path);
    InstallError := Error;
    Result := Error;
    exit;
  end;
  if not RunInstaller(Path, Error) then begin
    InstallError := Error;
    Result := Error;
  end;
  DeleteFile(Path);
end;

function AppInstalled: Boolean;
begin
  Result := (InstalledPath <> '') and FileExists(InstalledPath);
end;

function InstalledExe(Param: String): String;
begin
  Result := InstalledPath;
end;

procedure CopyDetails(Sender: TObject);
var Code: Integer;
begin
  Exec(ExpandConstant('{cmd}'), '/c type "' + LogFile + '" | clip', '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpPreparing) and (InstallError <> '') and (CopyButton = nil) then begin
    CopyButton := TNewButton.Create(WizardForm);
    CopyButton.Parent := WizardForm;
    CopyButton.Caption := 'Copy details';
    CopyButton.Left := WizardForm.ClientWidth - WizardForm.CancelButton.Left - WizardForm.CancelButton.Width + ScaleX(0);
    CopyButton.Top := WizardForm.CancelButton.Top;
    CopyButton.Width := ScaleX(100);
    CopyButton.Height := WizardForm.CancelButton.Height;
    CopyButton.OnClick := @CopyDetails;
  end;
end;

procedure DeinitializeSetup;
begin
  if InstallError <> '' then Note('Web installer finished with an error: ' + InstallError)
  else Note('Web installer finished');
end;
