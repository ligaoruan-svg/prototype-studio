; Windows 安装程序（Inno Setup）：装到当前用户自己的目录，不要管理员权限；开始菜单和桌面放快捷方式，带卸载。
; 由 desktop/build_windows.py 调用：ISCC /DAppVersion=6.0 /DSourceDir=... /DOutputDir=... installer.iss
#ifndef AppVersion
  #define AppVersion "0.0"
#endif

[Setup]
AppId={{6B0E8F52-6C1B-4D7E-9A57-3F0D2C8B1A44}
AppName=原型工坊
AppVersion={#AppVersion}
AppPublisher=原型工坊
DefaultDirName={localappdata}\Programs\原型工坊
DefaultGroupName=原型工坊
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=原型工坊-{#AppVersion}-Windows安装程序
SetupIconFile={#SourceDir}\..\..\icon.ico
UninstallDisplayIcon={app}\PrototypeStudio.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
#if FileExists(AddBackslash(CompilerPath) + "Languages\ChineseSimplified.isl")
Name: "zh"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
#else
Name: "en"; MessagesFile: "compiler:Default.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\原型工坊"; Filename: "{app}\PrototypeStudio.exe"
Name: "{group}\卸载 原型工坊"; Filename: "{uninstallexe}"
Name: "{userdesktop}\原型工坊"; Filename: "{app}\PrototypeStudio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PrototypeStudio.exe"; Description: "{cm:LaunchProgram,原型工坊}"; Flags: nowait postinstall skipifsilent

; 卸载只删程序本身。项目和模型设置在 %LOCALAPPDATA%\原型工坊，留着，重装后还在
