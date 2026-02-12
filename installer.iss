; Script di esempio Inno Setup per l'installer PySide6

#define MyAppVersion "0.5.4"


[Setup]
AppId={{0f0058d8-3cc1-4707-b86a-ed74d880c26a}}
AppMutex=pylizmutex
AppName=Pyliz
AppVersion={#MyAppVersion}
DefaultDirName={commonpf}\Pyliz
DefaultGroupName=Pyliz
OutputDir=Output
OutputBaseFilename=Pyliz-setup
Compression=lzma
SolidCompression=yes
DisableProgramGroupPage=yes
SetupIconFile=resources\logo.ico

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[Files]
Source: "dist\pyliz-windows\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "dist\qtliz-windows\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "dist\pyliz-media-windows\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\pyliz"; Filename: "{app}\pyliz-windows.exe"
Name: "{group}\qtliz"; Filename: "{app}\qtliz-windows.exe"
Name: "{group}\pyliz-media"; Filename: "{app}\pyliz-media-windows.exe"

[Run]
Filename: "{app}\pyliz-windows.exe"; Description: "Avvia Pyliz"; Flags: nowait postinstall skipifsilent
