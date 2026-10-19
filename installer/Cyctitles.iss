; Inno Setup script for Cyctitles.
;
; Build the app first (single-file "lite"/CPU build), then compile this script:
;   1. powershell -ExecutionPolicy Bypass -File build.ps1 -Lite
;   2. powershell -ExecutionPolicy Bypass -File installer\make_cuda_pack.ps1
;      -> upload installer\Output\cuda.zip to a GitHub Release
;   3. Put that download URL into CudaPackUrl below.
;   4. Open this file in Inno Setup Compiler (or run ISCC.exe installer\Cyctitles.iss)
;
; Output: installer\Output\Cyctitles-Setup-<version>.exe
;
; The wizard installs the CPU build always, and (by default) downloads and
; unpacks an optional CUDA pack so NVIDIA users get GPU acceleration.

#define MyAppName "Cyctitles"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "ClassicCyc"
#define MyAppURL "https://github.com/ClassicCyc/Cyctitles"
#define MyAppExeName "Cyctitles.exe"

; >>> EDIT THIS: direct download URL of cuda.zip from your GitHub Release <<<
; e.g. https://github.com/ClassicCyc/Cyctitles/releases/download/v1.0.0/cuda.zip
#define CudaPackUrl "https://github.com/ClassicCyc/Cyctitles/releases/download/v1.0.0/cuda.zip"
[Setup]
AppId={{8F3B2E7A-6C4D-4A1E-9B2F-7D5C1A9E4B63}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=Output
OutputBaseFilename=Cyctitles-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Components]
Name: "cuda"; Description: "NVIDIA GPU support (CUDA) — recommended for GeForce/Quadro"; Types: full; Flags: checkablealone

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  CudaPackUrl = '{#CudaPackUrl}';

var
  DownloadPage: TDownloadWizardPage;
  CudaZip: String;

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  Result := True;
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), @OnDownloadProgress);
end;

// Look for a cuda.zip shipped next to the setup executable (offline install).
function LocalCudaZip: String;
var
  Candidate: String;
begin
  Candidate := ExtractFilePath(ExpandConstant('{srcexe}')) + 'cuda.zip';
  if FileExists(Candidate) then
    Result := Candidate
  else
    Result := '';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpSelectComponents) and WizardIsComponentSelected('cuda') then begin
    // 1. Prefer a local cuda.zip next to the installer (works offline).
    CudaZip := LocalCudaZip;
    if CudaZip <> '' then begin
      if MsgBox('Found a local cuda.zip next to the installer.' + #13#10 +
        'Use it for NVIDIA GPU support (no download needed)?', mbConfirmation,
        MB_YESNO) = IDNO then
        CudaZip := '';
    end;
    // 2. Otherwise download it.
    if CudaZip = '' then begin
      DownloadPage.Clear;
      DownloadPage.Add(CudaPackUrl, 'cuda.zip', '');
      DownloadPage.Show;
      try
        try
          DownloadPage.Download;
          CudaZip := DownloadPage.Files[0].Filename;
        except
          SuppressibleMsgBox('Could not download the NVIDIA CUDA pack from:'#13#10 + CudaPackUrl +
            #13#10#13#10'The app will still install and run on CPU. You can add CUDA later by ' +
            'placing cuda.zip next to the installer and running it again, or by unpacking ' +
            'cuda.zip next to Cyctitles.exe.', mbError, MB_OK, IDOK);
        end;
      finally
        DownloadPage.Hide;
      end;
    end;
  end;
end;

procedure ExtractCudaPack;
var
  ResultCode: Integer;
  CudaDir: String;
begin
  if CudaZip = '' then exit;
  CudaDir := ExpandConstant('{app}\cuda');
  ForceDirectories(CudaDir);
  // Unpack with PowerShell (available on all supported Windows versions).
  if not Exec('powershell.exe',
    '-NoProfile -ExecutionPolicy Bypass -Command ' +
    '"Expand-Archive -LiteralPath ''' + CudaZip + ''' -DestinationPath ''' + ExpandConstant('{app}') + ''' -Force"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
  begin
    SuppressibleMsgBox('CUDA pack found, but could not be unpacked automatically.'#13#10 +
      'You can unzip it manually next to Cyctitles.exe.', mbInformation, MB_OK, IDOK);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and WizardIsComponentSelected('cuda') then
    ExtractCudaPack;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  CudaDir: String;
begin
  if CurUninstallStep = usUninstall then begin
    CudaDir := ExpandConstant('{app}\cuda');
    if DirExists(CudaDir) then
      DelTree(CudaDir, True, True, True);
  end;
end;
