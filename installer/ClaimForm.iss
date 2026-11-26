; Inno Setup script: builds dist\installer\ClaimForm-Setup-<version>.exe
; Run build_installer.bat rather than compiling this by hand: it builds the app first.
; For a new release, raise AppVersion below (keep AppId unchanged so it upgrades in place).

#define AppName "DBT Claim Form"
#define AppVersion "1.0.0"
#define AppPublisher "DBT Technologies"
#define AppExe "ClaimForm.exe"

[Setup]
AppId={{682570A1-CDEC-4E01-8EE2-EEB169D68CF5}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
; No admin rights needed: installs for the current user by default,
; with an option in the wizard to install for everyone (asks for admin).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=ClaimForm-Setup-{#AppVersion}
SetupIconFile=..\build\ClaimForm.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Clear the previous version's libraries so an upgrade leaves no stale files.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\ClaimForm\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
