; ============================================================
;  Arrabona Naptar - telepito (Inno Setup 6/7)
;  Nem kezzel kell futtatni: a build\build.bat forditja le, a verziot is az adja at.
;  FONTOS: az adatok (%APPDATA%\ArrabonaNaptar) NEM a program mappajaban vannak,
;  ezert frissiteskor es eltavolitaskor is megmarad.
; ============================================================

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName   "Arrabona Naptár"
#define AppExe    "Arrabona Naptar.exe"

[Setup]
AppId={{6F2C9B1E-5A47-4C8E-9D3B-1E7A4F0C2B91}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher=Lokypapa
DefaultDirName={autopf}\Arrabona Naptar
DefaultGroupName=Arrabona Naptár
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release
OutputBaseFilename=ArrabonaNaptar_Setup_{#AppVersion}
SetupIconFile=..\assets\logo_naptar.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
CloseApplications=no
SetupLogging=yes
VersionInfoVersion={#AppVersion}

[Languages]
Name: "hungarian"; MessagesFile: "compiler:Languages\Hungarian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; mappas build: a regi verzio konyvtarai ne keveredjenek az ujakkal
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\Arrabona Naptar\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; a Naptar a felhasznalo sajat (nem rendszergazdai) jogaval induljon
Filename: "{app}\{#AppExe}"; Description: "Arrabona Naptár indítása"; Flags: nowait postinstall skipifsilent runasoriginaluser
; onfrissites (csendes telepites) utan automatikus ujrainditas
Filename: "{app}\{#AppExe}"; Flags: nowait runasoriginaluser; Check: WizardSilent

[Code]
procedure NaptarLeallitasa();
var
  RC: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/im "{#AppExe}"', '', SW_HIDE, ewWaitUntilTerminated, RC);
  Sleep(1500);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/f /im "{#AppExe}"', '', SW_HIDE, ewWaitUntilTerminated, RC);
  Sleep(500);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  NaptarLeallitasa();
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    NaptarLeallitasa();
    { "Inditas a Windows-szal" bejegyzes torlese (ha be volt kapcsolva) }
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'ArrabonaNaptar');
  end;
end;
