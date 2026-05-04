#define MyAppName      "Avid Transcription"
#define MyAppVersion   "1.0.0"
#define MyAppPublisher "AvidTranscription Contributors"
#define MyAppURL       "https://github.com/golisfat85/AvidTranscription"
#define MyAppGUID      "{{8F4A3C2B-1D5E-4F7A-9B0C-2E6D8A3F5C1D}"

[Setup]
AppId={#MyAppGUID}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=AvidTranscription-{#MyAppVersion}-Windows-Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=120
MinVersion=10.0
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\launch_gui.bat
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel1=Welcome to the [name] Setup Wizard
WelcomeLabel2=This will install [name/ver] on your computer.%n%nThis plugin lets you transcribe and subtitle video clips directly inside Avid Media Composer using AI (OpenAI Whisper).%n%nClick Next to continue.

[Dirs]
; Create Avid panels directory in case Avid hasn't created it yet
Name: "{userappdata}\Avid\Avid Media Composer\SupportingFiles\Panels\AvidTranscription"

[Files]
; Python wheel – bundled by the CI workflow before running ISCC
Source: "avid_transcription-{#MyAppVersion}-py3-none-any.whl"; DestDir: "{tmp}"; Flags: deleteafterinstall

; Avid panel files → installed to both {app} and Avid's panels directory
Source: "..\..\avid_panel\*"; DestDir: "{app}\avid_panel"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\..\avid_panel\*"; DestDir: "{userappdata}\Avid\Avid Media Composer\SupportingFiles\Panels\AvidTranscription"; Flags: recursesubdirs createallsubdirs ignoreversion

; Launcher batch files written to {app}
Source: "start_server.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "launch_gui.bat";   DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Desktop
Name: "{userdesktop}\Start Avid Transcription Server"; Filename: "{app}\start_server.bat"; WorkingDir: "{app}"; Comment: "Start the Avid Transcription local server"

; Start Menu
Name: "{userprograms}\{#MyAppName}\Start Server";  Filename: "{app}\start_server.bat"; WorkingDir: "{app}"
Name: "{userprograms}\{#MyAppName}\Open GUI";       Filename: "{app}\launch_gui.bat";   WorkingDir: "{app}"
Name: "{userprograms}\{#MyAppName}\Uninstall";      Filename: "{uninstallexe}"

[Run]
; Install the Python package
Filename: "cmd.exe"; \
  Parameters: "/C python -m pip install --upgrade pip && python -m pip install ""{tmp}\avid_transcription-{#MyAppVersion}-py3-none-any.whl"""; \
  StatusMsg: "Installing Python package (this may take a minute)..."; \
  Flags: runhidden waituntilterminated

; Offer to start the server immediately
Filename: "{app}\start_server.bat"; \
  Description: "Start the Avid Transcription server now"; \
  Flags: postinstall nowait skipifsilent unchecked

[UninstallRun]
Filename: "cmd.exe"; Parameters: "/C pip uninstall -y avid-transcription"; Flags: runhidden

[Code]

// ── Python detection ────────────────────────────────────────────────────────

function PythonAvailable(): Boolean;
var
  ResultCode: Integer;
begin
  Result :=
    Exec('cmd.exe', '/C python --version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
    and (ResultCode = 0);
  if not Result then
    Result :=
      Exec('cmd.exe', '/C python3 --version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
      and (ResultCode = 0);
end;

function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  if not PythonAvailable() then
  begin
    if MsgBox(
      'Python 3.9 or later is required but was not found.' + #13#10 + #13#10 +
      'Please install Python from https://www.python.org/downloads/' + #13#10 +
      'and tick "Add Python to PATH" during installation.' + #13#10 + #13#10 +
      'Open the Python download page now?',
      mbConfirmation, MB_YESNO
    ) = IDYES then
      ShellExec('open', 'https://www.python.org/downloads/', '', '', SW_SHOW, ewNoWait, ResultCode);
    Result := False;
  end
  else
    Result := True;
end;

// ── FFmpeg warning ──────────────────────────────────────────────────────────

function FFmpegAvailable(): Boolean;
var
  ResultCode: Integer;
begin
  Result :=
    Exec('cmd.exe', '/C ffmpeg -version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
    and (ResultCode = 0);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    if not FFmpegAvailable() then
    begin
      if MsgBox(
        'FFmpeg was not found on your system.' + #13#10 + #13#10 +
        'FFmpeg is required to extract audio from video files.' + #13#10 +
        'Download it from https://ffmpeg.org/download.html and add it to PATH.' + #13#10 + #13#10 +
        'Open the FFmpeg download page now?',
        mbConfirmation, MB_YESNO
      ) = IDYES then
        ShellExec('open', 'https://ffmpeg.org/download.html', '', '', SW_SHOW, ewNoWait, ResultCode);
    end;
  end;
end;
