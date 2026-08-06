; Peel (win-bg-tool) — Windows installer (Inno Setup 6+)
; Wizard lets the user pick the install directory.
;
; Build: scripts\build_installer.bat
; Requires: dist\Peel\ from PyInstaller (scripts\build_exe.bat)

#define MyAppName "Peel"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "wyf-777"
#define MyAppURL "https://github.com/wyf-777/win-bg-tool"
#define MyAppExeName "Peel.exe"

[Setup]
AppId={{A7C8E2F1-4B3D-4E9A-9C1F-8D6E5A2B0F17}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
; User can change install path on the wizard page
DisableDirPage=no
AllowNoIcons=yes
; 64-bit only (matches PyInstaller win_amd64 build)
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Prefer per-user install when possible; still allows Program Files with elevation
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=Peel-Setup-{#MyAppVersion}
; Installer wizard + uninstaller icon (from 导出\图标.jpg → packaging\peel.ico)
SetupIconFile=peel.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Prefer standalone peel.ico for shell icons (more reliable than exe index 0)
UninstallDisplayIcon={app}\peel.ico
; Large onedir payload
DiskSpanning=no
CloseApplications=yes
RestartApplications=no
; Chinese + English UI (system language picks if available)
ShowLanguageDialog=auto

[Languages]
; Bundled zh-CN (not always shipped with winget Inno Setup)
Name: "chinesesimplified"; MessagesFile: "languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Default ON — desktop shortcut with app icon after install
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; Ship entire PyInstaller onedir; skip incomplete model downloads
Source: "..\dist\Peel\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.part"
; Explicit icon for desktop/start-menu shortcuts (avoid Python default logo)
Source: "peel.ico"; DestDir: "{app}"; DestName: "peel.ico"; Flags: ignoreversion

[Icons]
; IconFilename = peel.ico — do not rely only on Peel.exe resource index
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\peel.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\peel.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
  if not FileExists(ExpandConstant('{src}\..\dist\Peel\Peel.exe')) and
     not FileExists(ExpandConstant('{#SourcePath}\..\dist\Peel\Peel.exe')) then
  begin
    // Compile-time Source path is used for Files; runtime check is soft
  end;
end;
