#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{3E33A31B-5C5C-4B35-A278-F9E0C423230C}
AppName=FokusWache
AppVersion={#AppVersion}
AppPublisher=Falk Pfisterer
AppPublisherURL=https://github.com/Dolcruz/Fokuswache
AppSupportURL=https://github.com/Dolcruz/Fokuswache/issues
AppUpdatesURL=https://github.com/Dolcruz/Fokuswache/releases/latest
DefaultDirName={autopf}\FokusWache
DisableDirPage=yes
DisableProgramGroupPage=yes
UsePreviousAppDir=no
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\dist
OutputBaseFilename=FokusWache-Setup-{#AppVersion}-x64
SetupIconFile=..\src\FokusWache.ico
UninstallDisplayIcon={app}\FokusWache.exe
LicenseFile=..\LICENSE
InfoBeforeFile=Hinweise.txt
WizardStyle=modern
Compression=zip/7
CompressionThreads=1
SolidCompression=no
CloseApplications=no
RestartApplications=no
RestartIfNeededByRun=no

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Desktop-Symbol erstellen"; Flags: unchecked

[Files]
Source: "..\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\extensions\*"; DestDir: "{app}\extensions"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "Windows.ps1"; DestDir: "{app}\installer"; Flags: ignoreversion
Source: "Windows.ps1"; Flags: dontcopy
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\Installation.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\Betrieb.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\Drittanbieter.md"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{commonprograms}\FokusWache"; Filename: "{app}\FokusWache.exe"; WorkingDir: "{app}"
Name: "{commondesktop}\FokusWache"; Filename: "{app}\FokusWache.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\FokusWache.exe"; Description: "FokusWache öffnen"; Flags: postinstall nowait skipifsilent runasoriginaluser

[InstallDelete]
Type: files; Name: "{app}\Deinstallieren.ps1"

[UninstallDelete]
Type: files; Name: "{app}\native-chromium.json"
Type: files; Name: "{app}\native-firefox.json"

[Code]
var
  Prepared: Boolean;
  Configured: Boolean;
  FailureText: String;
  InstallerMutex: THandle;

function CreateInstallerMutex(Attributes: Integer; InitialOwner: Boolean; Name: String): THandle;
  external 'CreateMutexW@kernel32.dll stdcall';

function AcquireInstallerMutex: Boolean;
begin
  InstallerMutex := CreateInstallerMutex(0, False, 'Global\FokusWache.Installer');
  Result := (InstallerMutex <> 0) and (DLLGetLastError <> 183);
  if not Result then
    SuppressibleMsgBox('Eine FokusWache-Installation oder Deinstallation läuft bereits. Bitte beende sie zuerst.', mbError, MB_OK, IDOK);
end;

function InitializeSetup: Boolean;
begin
  Result := AcquireInstallerMutex;
end;

function Lifecycle(const Action: String): Boolean;
var
  ScriptPath, ErrorPath: String;
  Raw: AnsiString;
  ExitCode: Integer;
begin
  if IsUninstaller then
    ScriptPath := ExpandConstant('{app}\installer\Windows.ps1')
  else begin
    ExtractTemporaryFile('Windows.ps1');
    ScriptPath := ExpandConstant('{tmp}\Windows.ps1');
  end;
  ErrorPath := ExpandConstant('{tmp}\fokuswache-error.txt');
  Result := Exec(ExpandConstant('{sysnative}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + ScriptPath +
    '" -Action ' + Action + ' -InstallRoot "' + ExpandConstant('{app}') +
    '" -ErrorFile "' + ErrorPath + '"', '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
  Result := Result and (ExitCode = 0);
  FailureText := 'Die Windows-Einrichtung konnte nicht abgeschlossen werden.';
  if LoadStringFromFile(ErrorPath, Raw) and (Raw <> '') then
    FailureText := UTF8Decode(Raw);
  if not Result then Log(FailureText);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not Lifecycle('Prepare') then
    Result := FailureText
  else
    Prepared := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    if not Lifecycle('Configure') then RaiseException(FailureText);
    Configured := True;
  end;
end;

procedure DeinitializeSetup;
begin
  if Prepared and not Configured then Lifecycle('Resume');
end;

function InitializeUninstall: Boolean;
begin
  Result := AcquireInstallerMutex;
  if not Result then Exit;
  Result := Lifecycle('Check');
  if not Result then SuppressibleMsgBox(FailureText, mbError, MB_OK, IDOK);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    if not Lifecycle('Uninstall') then RaiseException(FailureText);
end;
