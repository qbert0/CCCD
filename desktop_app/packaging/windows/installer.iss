; Inno Setup script for CCCD Report on Windows.
; Packages the onedir PyInstaller output from product/CCCDReport into a
; single installer .exe. Build the app first (desktop_app/build.sh), then:
;   iscc /DMyAppVersion=1.2.3 desktop_app\packaging\windows\installer.iss
; MyAppVersion defaults to a dev placeholder so local double-click builds
; still work without passing /D.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif
#define MyAppName "CCCD Report"
#define MyAppPublisher "Vietnamobile"
#define MyAppExeName "CCCDReport.exe"

[Setup]
AppId={{B6E1C9C4-6F0A-4B8E-9B7B-2B6B7C9B8F1A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\..\dist_installers
OutputBaseFilename=CCCDReport-{#MyAppVersion}-windows-setup
Compression=lzma2
SolidCompression=yes
SetupIconFile=..\..\..\build\icons\icon.ico
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Tạo biểu tượng trên màn hình nền"; GroupDescription: "Biểu tượng bổ sung:"

[Files]
Source: "..\..\..\product\CCCDReport\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Custom fonts baked into the docx templates (see scripts/apply_signature_font.py,
; scripts/apply_value_font.py) render correctly in the app's own preview inside a
; real Word/LibreOffice install, but the bundled LibreOffice's headless PDF export
; (used to turn each generated .docx into the JPGs this app actually ships) only
; picks up fonts genuinely registered with Windows -- an embedded-in-the-docx font
; is silently substituted otherwise (confirmed directly: pdffonts on the exported
; PDF showed neither font at all before this, a generic serif in their place).
; Installing them for real here is what fixes that.
Source: "..\..\..\desktop_app\data\source\fonts\GreatVibes-Regular.ttf"; DestDir: "{autofonts}"; FontInstall: "Great Vibes"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "..\..\..\desktop_app\data\source\fonts\JetBrainsMonoNFExtraBold-Regular.ttf"; DestDir: "{autofonts}"; FontInstall: "JetBrainsMono NF ExtraBold"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Gỡ cài đặt {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Chạy {#MyAppName}"; Flags: nowait postinstall skipifsilent
