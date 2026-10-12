; SPDX-License-Identifier: GPL-3.0-only
; Copyright (c) 2026 hmodymac8-droid
; Inno Setup script for Downloads Sorter. build.py compiles it and passes
; AppVersion and DistDir (the packaged program folder) on the command line.
;
; A standard per-user setup wizard: no administrator rights, proper uninstaller,
; English and Arabic. The program updates itself by running this setup with
; /VERYSILENT (see apply_update in sort_downloads.py).

#define AppName "Downloads Sorter"
#define AppExe "DownloadsSorter.exe"
#define RunKey "Software\Microsoft\Windows\CurrentVersion\Run"
#define RunValue "DownloadsSorter"
#ifndef AppVersion
  #define AppVersion "0.0"
#endif
#ifndef DistDir
  #define DistDir "dist\DownloadsSorter"
#endif
; TestBuild makes a copy that is safe to install into a scratch folder: it uses
; its own identity, never closes or starts the real program, and leaves the
; shortcuts and the startup entry alone.
#ifdef TestBuild
  #define AppId "{{6B0E6C5E-TEST-4C1B-9A57-DOWNLOADSORT}"
#else
  #define AppId "{{6B0E6C5E-7C2A-4C1B-9A57-3F1D2E8B4A10}"
#endif

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=hmodymac8-droid
AppCopyright=Copyright (c) 2026 hmodymac8-droid
AppPublisherURL=https://github.com/hmodymac8-droid/downloads-sorter
AppSupportURL=https://github.com/hmodymac8-droid/downloads-sorter/issues
AppUpdatesURL=https://github.com/hmodymac8-droid/downloads-sorter/releases
; "lowest" installs for the current user only, under AppData\Local\Programs.
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputBaseFilename=DownloadsSorterSetup
SetupIconFile=icon.ico
LicenseFile=LICENSE
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
; The program is closed by PrepareToInstall below, so skip the Restart Manager prompt.
CloseApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"

[CustomMessages]
english.AutoSort=Sort automatically in the background (starts when you sign in)
arabic.AutoSort=الفرز التلقائي في الخلفية (يبدأ عند تسجيل الدخول)
english.OpenApp=Open {#AppName}
arabic.OpenApp=فتح {#AppName}

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"
Name: "autostart"; Description: "{cm:AutoSort}"; Flags: unchecked

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
#ifndef TestBuild
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
#endif

[Registry]
#ifndef TestBuild
Root: HKCU; Subkey: "{#RunKey}"; ValueType: string; ValueName: "{#RunValue}"; \
    ValueData: """{app}\{#AppExe}"" --background"; Check: WantAutostart
; Entry left in "Installed apps" by the pre-1.5 setup program.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\DownloadsSorter"; Flags: deletekey
#endif

[Run]
#ifndef TestBuild
; The background process shows the tray icon. After a silent update it always comes
; back as it was; in the wizard it starts with automatic sorting on if that was ticked.
Filename: "{app}\{#AppExe}"; Parameters: "--background"; Flags: nowait; Check: WizardSilent
Filename: "{app}\{#AppExe}"; Parameters: "--background --auto-on"; Flags: nowait; Check: TickedAutostart
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: ReopenRequested
#endif
Filename: "{app}\{#AppExe}"; Description: "{cm:OpenApp}"; Flags: nowait postinstall skipifsilent

[Code]
var
  AutostartWasOn: Boolean;

procedure CloseProgram;
var
  ResultCode: Integer;
begin
#ifndef TestBuild
  // Every running copy (window, report, background sorter) locks the program files.
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM {#AppExe} /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1500);
#endif
end;

function InitializeSetup: Boolean;
begin
  // Remember the state before anything is changed.
  AutostartWasOn := RegValueExists(HKEY_CURRENT_USER, '{#RunKey}', '{#RunValue}');
  Result := True;
end;

function WantAutostart: Boolean;
begin
  // A silent run is the program updating itself: keep automatic sorting as the
  // user has it now. (They may have switched it in the program since installing.)
  if WizardSilent then
    Result := AutostartWasOn
  else
    Result := WizardIsTaskSelected('autostart');
end;

function TickedAutostart: Boolean;
begin
  Result := (not WizardSilent) and WizardIsTaskSelected('autostart');
end;

function ReopenRequested: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:reopen|0}') = '1');
end;

procedure InitializeWizard;
begin
  // Updating over an existing install: offer the automatic option as it is now.
  if AutostartWasOn then
    WizardSelectTasks('autostart');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  CloseProgram;
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDir: String;
begin
  // Lets the background sorter announce "Updated to version X" when it starts again.
  if (CurStep = ssPostInstall) and WizardSilent then
  begin
    DataDir := ExpandConstant('{userappdata}\DownloadsSorter');
    ForceDirectories(DataDir);
    SaveStringToFile(DataDir + '\updated.txt', '{#AppVersion}', False);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    CloseProgram;
#ifndef TestBuild
    // The program may have added this itself ("Turn on automatic sorting").
    RegDeleteValue(HKEY_CURRENT_USER, '{#RunKey}', '{#RunValue}');
#endif
  end;
end;
