; â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
; Ponfolio â€” Fully Self-Contained Portable Installer
; Single EXE: Flutter app + Python backend + all dependencies
; Works on ANY Windows 10/11 x64 laptop â€” no Python required!
; â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

#define MyAppName "Ponfolio"
#define MyAppVersion "1.7.0"
#define MyAppPublisher "AIEI Technologies"
#define MyAppURL "https://aiei.tech"
#define MyAppExeName "aiei_wealth.exe"
#define MyAppId "{{B7A4E2D1-9F3C-4A5B-8E6D-1C2F3A4B5C6D}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=Ponfolio_Setup_v{#MyAppVersion}
SetupIconFile=windows\runner\resources\app_icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; â”€â”€ Desktop App (Flutter Release) â”€â”€
Source: "build\windows\x64\runner\Release\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "build\windows\x64\runner\Release\*.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "build\windows\x64\runner\Release\data\*"; DestDir: "{app}\data"; Flags: ignoreversion recursesubdirs createallsubdirs

; â”€â”€ App Icon (for system tray) â”€â”€
Source: "windows\runner\resources\app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

; â”€â”€ Bundled Python Runtime (embedded, pre-configured with all deps) â”€â”€
Source: "installer\python-embed\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs createallsubdirs

; â”€â”€ Backend Server (all Python source; excludes tests) â”€â”€
Source: "backend\*.py"; DestDir: "{app}\backend"; Excludes: "test_*.py"; Flags: ignoreversion
Source: "backend\requirements.txt"; DestDir: "{app}\backend"; Flags: ignoreversion
; Google OAuth client (git-ignored, see backend/google_auth.py); skipped when absent
Source: "backend\google_oauth.json"; DestDir: "{app}\backend"; Flags: ignoreversion skipifsourcedoesntexist

; â”€â”€ Backend Data â”€â”€
; Fresh installs start clean. We deliberately bundle NO data: no credentials
; (auth.json), no per-user portfolio/expense data (users\), and no paper-trading
; seed. The backend creates data\ and per-user folders on first run (see the
; [Dirs] section, which preserves an existing install's data on upgrade).

; â”€â”€ README â”€â”€
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; Ensure an empty backend data folder exists; the backend populates it at runtime.
Name: "{app}\backend\data"

[Icons]
; Start Menu
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "Launch Ponfolio"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

; Desktop
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// The app launches its backend as a DETACHED python.exe from {app}\python.
// Killing only the Flutter exe leaves that backend running, so it keeps a lock
// on {app}\python\* and Inno's file-in-use scanner shows a "Python is using
// files" prompt (and file copies fail if the user declines). Terminate our own
// backend first â€” matched by its executable path under the AIEI folder so we
// never touch an unrelated Python install on the machine.
procedure KillAppProcesses();
var
  ResultCode: Integer;
begin
  // Flutter shell
  Exec('taskkill', '/F /IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  // Bundled backend: any python.exe whose image path is inside our app folder.
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
       '-NoProfile -NonInteractive -Command "Get-Process python,pythonw -ErrorAction SilentlyContinue | ' +
       'Where-Object { $_.Path -like ''*AIEI Wealth*'' -or $_.Path -like ''*Ponfolio*'' } | Stop-Process -Force -ErrorAction SilentlyContinue; ' +
       'Start-Sleep -Milliseconds 400"',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function InitializeSetup(): Boolean;
begin
  KillAppProcesses();
  Result := True;
end;

function InitializeUninstall(): Boolean;
begin
  KillAppProcesses();
  Result := True;
end;
