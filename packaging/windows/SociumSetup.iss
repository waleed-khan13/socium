#ifndef MyAppVersion
  #error MyAppVersion is required
#endif
#ifndef MyTarget
  #error MyTarget is required
#endif
#ifndef RuntimeDir
  #error RuntimeDir is required
#endif
#ifndef OutputDir
  #error OutputDir is required
#endif
#ifndef OutputBaseFilename
  #error OutputBaseFilename is required
#endif
#ifndef IconFile
  #error IconFile is required
#endif
#ifndef LicenseFile
  #error LicenseFile is required
#endif
#ifndef ManifestUrl
  #error ManifestUrl is required
#endif

#define RuntimePath "{app}\runtimes\" + MyAppVersion + "\" + MyTarget
#define RuntimeNode RuntimePath + "\bin\node.exe"
#define OfflineInstall RuntimePath + "\controller\offline-install.mjs"
#if MyTarget == "win32-arm64"
  #define AllowedArchitectures "arm64"
  #define InstallModeArchitectures "arm64"
#else
  #define AllowedArchitectures "x64compatible and not arm64"
  #define InstallModeArchitectures "x64compatible"
#endif

[Setup]
AppId={{E8412350-5D6A-4BA5-B537-ED644E4DDC30}
AppName=Socium
AppVersion={#MyAppVersion}
AppVerName=Socium {#MyAppVersion}
AppPublisher=Socium contributors
AppPublisherURL=https://github.com/waleed-khan13/socium
AppSupportURL=https://github.com/waleed-khan13/socium/issues
AppUpdatesURL=https://github.com/waleed-khan13/socium/releases/latest
AppCopyright=Copyright (c) Socium contributors
DefaultDirName={localappdata}\Socium
DefaultGroupName=Socium
DisableDirPage=no
DisableWelcomePage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
UsePreviousAppDir=yes
UsePreviousTasks=yes
AllowNoIcons=yes
AllowRootDirectory=no
AllowUNCPath=no
CloseApplications=yes
RestartApplications=no
MinVersion=10.0
WizardStyle=modern
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\socium.ico
LicenseFile={#LicenseFile}
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBaseFilename}
Compression=lzma2/max
SolidCompression=yes
SetupLogging=yes
DisableReadyPage=no
AlwaysShowDirOnReadyPage=yes
DisableFinishedPage=no
ArchitecturesInstallIn64BitMode={#InstallModeArchitectures}
ArchitecturesAllowed={#AllowedArchitectures}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startmenuicon"; Description: "Create a Start Menu shortcut"; GroupDescription: "Shortcuts:"; Flags: checkedonce
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "autostart"; Description: "Start Socium automatically when I sign in"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
Source: "{#RuntimeDir}\*"; DestDir: "{#RuntimePath}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#IconFile}"; DestDir: "{app}"; DestName: "socium.ico"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\Socium"; Filename: "{app}\launcher\node.exe"; Parameters: """{app}\launcher\launch.mjs"""; WorkingDir: "{app}\launcher"; IconFilename: "{app}\socium.ico"; Comment: "Open Socium"; Tasks: startmenuicon
Name: "{userdesktop}\Socium"; Filename: "{app}\launcher\node.exe"; Parameters: """{app}\launcher\launch.mjs"""; WorkingDir: "{app}\launcher"; IconFilename: "{app}\socium.ico"; Comment: "Open Socium"; Tasks: desktopicon
Name: "{userstartup}\Socium"; Filename: "{app}\launcher\node.exe"; Parameters: """{app}\launcher\launch.mjs"""; WorkingDir: "{app}\launcher"; IconFilename: "{app}\socium.ico"; Comment: "Start Socium"; Tasks: autostart

[Run]
Filename: "{#RuntimeNode}"; Parameters: """{#OfflineInstall}"" --home ""{app}"" --runtime-path ""{#RuntimePath}"" --version ""{#MyAppVersion}"" --target ""{#MyTarget}"" --manifest ""{#ManifestUrl}"" --no-shortcuts"; StatusMsg: "Finalizing your private Socium installation..."; Flags: runhidden waituntilterminated; AfterInstall: VerifyInstallation
Filename: "{app}\launcher\node.exe"; Parameters: """{app}\launcher\launch.mjs"""; WorkingDir: "{app}\launcher"; Description: "Launch Socium"; Flags: nowait postinstall skipifsilent runhidden

[UninstallRun]
Filename: "{#RuntimeNode}"; Parameters: """{#RuntimePath}\controller\controller.mjs"" stop"; Flags: runhidden waituntilterminated skipifdoesntexist; RunOnceId: "StopSocium"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\runtimes"
Type: filesandordirs; Name: "{app}\launcher"
Type: filesandordirs; Name: "{app}\downloads"
Type: files; Name: "{app}\installation.json"
Type: files; Name: "{app}\socium.ico"
Type: dirifempty; Name: "{app}"

[Code]
var
  InstallPercentLabel: TNewStaticText;
  LastInstallPercent: Integer;

procedure InitializeWizard;
begin
  LastInstallPercent := -1;
  InstallPercentLabel := TNewStaticText.Create(WizardForm);
  InstallPercentLabel.Parent := WizardForm.ProgressGauge.Parent;
  InstallPercentLabel.Left := WizardForm.ProgressGauge.Left;
  InstallPercentLabel.Top := WizardForm.ProgressGauge.Top + WizardForm.ProgressGauge.Height + ScaleY(8);
  InstallPercentLabel.Width := WizardForm.ProgressGauge.Width;
  InstallPercentLabel.Caption := '0% installed';
end;

procedure CurInstallProgressChanged(CurProgress, MaxProgress: Integer);
var
  Percent: Integer;
begin
  if MaxProgress <= 0 then
    Percent := 0
  else
    Percent := Round((100.0 * CurProgress) / MaxProgress);

  if Percent <> LastInstallPercent then
  begin
    LastInstallPercent := Percent;
    InstallPercentLabel.Caption := IntToStr(Percent) + '% installed';
  end;
end;

procedure VerifyInstallation;
begin
  if not FileExists(ExpandConstant('{app}\installation.json')) then
    RaiseException('Socium could not finalize its local installation. Your existing data was not removed.');
  InstallPercentLabel.Caption := '100% installed';
end;
