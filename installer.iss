; Instalador de Nyx (Inno Setup 6).
; Antes: .venv\Scripts\pyinstaller.exe nyx.spec --noconfirm
; Luego: ISCC.exe installer.iss   ->   dist\installer\Nyx-Setup.exe

#define AppName "Nyx"
#define AppVersion "1.0"

[Setup]
AppId={{7C1E2B9A-5D4F-4E8B-9A31-6F0C2D8E4B17}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=cIZeroN
DefaultDirName={localappdata}\Programs\Nyx
DefaultGroupName=Nyx
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist\installer
OutputBaseFilename=Nyx-Setup
SetupIconFile=assets\nyx.ico
UninstallDisplayIcon={app}\Nyx.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un icono en el escritorio"; GroupDescription: "Iconos:"
Name: "startup"; Description: "Abrir Nyx al encender el ordenador"; GroupDescription: "Inicio:"; Flags: unchecked

[Files]
Source: "dist\Nyx\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Nyx"; Filename: "{app}\Nyx.exe"
Name: "{group}\Desinstalar Nyx"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Nyx"; Filename: "{app}\Nyx.exe"; Tasks: desktopicon
Name: "{userstartup}\Nyx"; Filename: "{app}\Nyx.exe"; Tasks: startup

[Run]
Filename: "{app}\Nyx.exe"; Description: "Abrir Nyx ahora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM Nyx.exe /F"; Flags: runhidden; RunOnceId: "CerrarNyx"
