; Manual installer build:
; 1. Run: python -m PyInstaller --clean --noconfirm .\TNH_Optima.spec
; 2. Open this file in Inno Setup Compiler.
; 3. Select Build > Compile to create the setup executable.

#define MyAppName "TNH Optima"
#define MyAppVersion "1.1.2"
#define MyAppPublisher "TNH"
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
Source: "dist\TNH Optima\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; AppUserModelID: "{#MyAppUserModelID}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; AppUserModelID: "{#MyAppUserModelID}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
