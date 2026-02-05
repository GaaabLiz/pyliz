; Script di esempio Inno Setup per l'installer PySide6

#define MyAppVersion "0.1.4"


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
Source: "dist\pyliz\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "dist\qtliz\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\pyliz"; Filename: "{app}\pyliz.exe"; IconFilename: "{app}\pyliz.exe"

[Run]
Filename: "{app}\pyliz.exe"; Description: "Avvia Devliz"; Flags: nowait postinstall skipifsilent
