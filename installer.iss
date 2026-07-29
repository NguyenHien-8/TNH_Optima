; Manual installer build:
; 1. Run: python -m PyInstaller --clean --noconfirm .\TNH_Optima.spec
; 2. Open this file in Inno Setup Compiler.
; 3. Select Build > Compile to create the setup executable.

#define MyAppName "TNH Optima"
#define MyAppVersion "1.1.2"
#define MyAppPublisher "TiNiHi"
#define MyAppURL "https://github.com/NguyenHien-8/VCA_Optima"
#define MyAppExeName "TNH Optima.exe"
#define MyAppUserModelID "TNH.Optima"

[Setup]
AppId={{8E7B8E25-4E3B-4E75-8C2E-2E53F5B91601}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableDirPage=no
DisableProgramGroupPage=yes
LicenseFile=LICENSE
OutputDir=Download Software
OutputBaseFilename=TNH_Optima_Setup_{#MyAppVersion}
SetupIconFile=App\ReSource\Icon\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "dist\TNH Optima\*"; DestDir: "{app}"; Excludes: "ConfigStorage.db,ConfigStorage.db-*,ConfigStorage.db.*,SessionData.db,SessionData.db-*,SessionData.db.*"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Remove runtime databases left inside the application directory by a legacy build.
Type: files; Name: "{app}\ConfigStorage.db*"
Type: files; Name: "{app}\SessionData.db*"
Type: files; Name: "{app}\_internal\App\Infrastructure\Persistence\ConfigStorage.db*"
Type: files; Name: "{app}\_internal\App\Infrastructure\Persistence\SessionData.db*"
; A legacy uninstaller did not clear Local App Data. Remove that stale state on
; the first clean install of this fixed version, but preserve it during upgrades.
Type: files; Name: "{localappdata}\{#MyAppName}\Data\ConfigStorage.db"; Check: IsCleanInstall
Type: files; Name: "{localappdata}\{#MyAppName}\Data\ConfigStorage.db-*"; Check: IsCleanInstall
Type: files; Name: "{localappdata}\{#MyAppName}\Data\SessionData.db"; Check: IsCleanInstall
Type: files; Name: "{localappdata}\{#MyAppName}\Data\SessionData.db-*"; Check: IsCleanInstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; AppUserModelID: "{#MyAppUserModelID}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; AppUserModelID: "{#MyAppUserModelID}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Inno Setup does not remove per-user Local App Data automatically. Clear only
; application-owned databases so reinstall starts without stale Project/Item data.
Type: files; Name: "{localappdata}\{#MyAppName}\Data\ConfigStorage.db"
Type: files; Name: "{localappdata}\{#MyAppName}\Data\ConfigStorage.db-*"
Type: files; Name: "{localappdata}\{#MyAppName}\Data\SessionData.db"
Type: files; Name: "{localappdata}\{#MyAppName}\Data\SessionData.db-*"
Type: dirifempty; Name: "{localappdata}\{#MyAppName}\Data"
Type: dirifempty; Name: "{localappdata}\{#MyAppName}"

[Code]
function IsCleanInstall: Boolean;
begin
  { The existing uninstaller is still present while InstallDelete is processed. }
  Result := not FileExists(
    AddBackslash(ExpandConstant('{app}')) + 'unins000.exe'
  );
end;
