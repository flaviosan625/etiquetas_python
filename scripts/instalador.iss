; =====================================================================
; Script Inno Setup 6 - AutoPrint Automation
; Especialista em Empacotamento, Compilação Nativa e Release (ISSUE-15)
; =====================================================================

#define MyAppName "AutoPrint Automation"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Soluções Gráficas"
#define MyAppExeName "AutoPrint.exe"
#define MyAppAssocName MyAppName + " File"
#define MyAppAssocExt ".autoprint"
#define MyAppAssocKey StringChange(MyAppAssocName, " ", "") + MyAppAssocExt

[Setup]
; Identificador exclusivo da aplicação gerado para instalações isoladas
AppId={{8B17E7A9-1D5B-4C98-A8A2-E3F57B95C601}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=..\assets\termos_de_uso.txt
OutputDir=..\dist\installer
OutputBaseFilename=AutoPrint_Setup_v{#MyAppVersion}
SetupIconFile=..\assets\icone.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
DisableProgramGroupPage=auto
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; Binários compilados nativamente (Nuitka / PyInstaller)
; Nuitka standalone gera pasta 'main.dist' ou executável direto renomeado para AutoPrint.exe
Source: "..\dist\main.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: DirExists(ExpandConstant('{src}\..\dist\main.dist'))
Source: "..\dist\AutoPrint\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: DirExists(ExpandConstant('{src}\..\dist\AutoPrint'))
; Executável direto caso compilado em arquivo único
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion; Check: FileExists(ExpandConstant('{src}\..\dist\{#MyAppExeName}'))
; Assets e recursos auxiliares
Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\assets\icone.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
; Banco e schemas SQL essenciais
Source: "..\banco\esquema.sql"; DestDir: "{app}\banco"; Flags: ignoreversion; Check: FileExists(ExpandConstant('{src}\..\banco\esquema.sql'))

[Icons]
Name: "{autoprograms}\{#MyAppName}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icone.ico"
Name: "{autoprograms}\{#MyAppName}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\assets\icone.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Limpeza profunda de logs, temporários e caches gerados durante a execução
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\*.dist-info"
Type: files; Name: "{app}\*.log"
Type: files; Name: "{app}\*.tmp"
Type: files; Name: "{app}\*.lock"
Type: dirifempty; Name: "{app}\logs"
Type: dirifempty; Name: "{app}\banco"
Type: dirifempty; Name: "{app}\assets"
Type: dirifempty; Name: "{app}"

[Code]
// Funções auxiliares para verificação dinâmica de arquivos durante o empacotamento
function DirExists(DirName: string): Boolean;
begin
  Result := DirExists(DirName);
end;
