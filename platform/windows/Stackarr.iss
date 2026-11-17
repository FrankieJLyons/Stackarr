; Per-user package installation. Runtime state and media are never installer files.
#ifndef PayloadDir
  #error PayloadDir must name a verified package staged by tools.build_windows_installer
#endif
#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef OutputDir
  #error OutputDir is required
#endif
#ifndef OutputName
  #error OutputName is required
#endif

[Setup]
AppId={{21EBF1CE-1719-43D5-BE53-534A83C75B28}
AppName=Stackarr
AppVersion={#AppVersion}
VersionInfoProductName=Stackarr
VersionInfoProductVersion={#AppVersion}
VersionInfoVersion={#AppVersion}
AppPublisher=Stackarr contributors
AppPublisherURL=https://github.com/FrankieJLyons/Stackarr
DefaultDirName={localappdata}\Programs\Stackarr
DefaultGroupName=Stackarr
UsePreviousAppDir=no
UsePreviousGroup=no
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.22000
CloseApplications=no
RestartApplications=no
UninstallFilesDir={app}\uninstall
UninstallDisplayIcon={app}\StackarrPreview.exe
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
#ifdef SignedBuild
SignTool=publisher
SignedUninstaller=yes
#endif
#ifdef ExternalSigningDir
; Two-pass cloud signing: export the exact uninstaller, then embed its signature.
SignedUninstaller=yes
SignedUninstallerDir={#ExternalSigningDir}
#endif

[Files]
Source: "{#PayloadDir}\StackarrPreview.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\stackarr-image.tar"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\Start-StackarrPreview.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\Start Stackarr.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\Recover Stackarr.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\README.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\THIRD-PARTY-NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\manifest.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\stackarr-installer-owner.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Stackarr"; Filename: "{app}\StackarrPreview.exe"; Parameters: "--package-first-run"; WorkingDir: "{app}"
Name: "{group}\Startup settings"; Filename: "{app}\StackarrPreview.exe"; Parameters: "--startup-settings ""{localappdata}\Stackarr\DockerPreview"""; WorkingDir: "{app}"
Name: "{group}\Recover Stackarr"; Filename: "{app}\StackarrPreview.exe"; Parameters: "--host-recovery"; WorkingDir: "{app}"

[Run]
Filename: "{app}\StackarrPreview.exe"; Parameters: "--package-first-run"; Description: "Open Stackarr setup"; Flags: nowait postinstall skipifsilent unchecked

[UninstallRun]
Filename: "{app}\StackarrPreview.exe"; Parameters: "--startup-disable ""{localappdata}\Stackarr\DockerPreview"""; Flags: runhidden waituntilterminated; RunOnceId: "DisableOwnedSigninStartup"

[Code]
function GetFileAttributesW(Name: String): LongWord;
  external 'GetFileAttributesW@kernel32.dll stdcall';

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Target, Parent: String;
  Marker: AnsiString;
  Attributes: LongWord;
begin
  Result := '';
  Target := ExpandConstant('{localappdata}\Programs\Stackarr');
  if CompareText(RemoveBackslashUnlessRoot(ExpandConstant('{app}')), Target) <> 0 then begin
    Result := 'Stackarr installs only in its dedicated current-user application folder.';
    Exit;
  end;
  Parent := Target;
  while Length(Parent) > 3 do begin
    Attributes := GetFileAttributesW(Parent);
    if (Attributes <> $FFFFFFFF) and ((Attributes and $400) <> 0) then begin
      Result := 'The application folder uses a filesystem link. Choose an ordinary Windows profile.';
      Exit;
    end;
    Parent := ExtractFileDir(Parent);
  end;
  if DirExists(Target) then begin
    if not LoadStringFromFile(Target + '\stackarr-installer-owner.txt', Marker) or
       (Trim(Marker) <> 'Stackarr per-user installer v1') then
      Result := 'The application folder already exists without a matching Stackarr installer receipt. Its contents were left unchanged.';
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usDone) and not UninstallSilent then
    MsgBox('The installed launcher and shortcuts have been removed. Your Stackarr settings, backups, Docker applications and media were retained. Scheduled Stackarr work requires a running controller. Use Stackarr''s reviewed removal flow to remove its runtime separately.', mbInformation, MB_OK);
end;
