; [v3.0] CNC Watcher 설치 파일 (Inno Setup 6) — build.ps1이 exe 빌드 뒤 이 스크립트로 Setup exe를 만든다.
; 사용자 폴더에 설치(관리자 권한 불필요). 가공 이력·설정은 %LOCALAPPDATA%\CNC Watcher라 업데이트·삭제해도 남는다.
; [v3.1] 앱 안 업데이트(updater.py)는 /VERYSILENT /UPDATE=1 /RELAUNCH="<다시 켤 때 인자>"로 실행한다:
;   앱이 스스로 정상 종료할 때까지 기다렸다 설치하고, 자동 실행 값은 건드리지 않고, 끝나면 앱을 다시 켠다.
#ifndef AppVersion
  #define AppVersion "v3.0"
#endif
#ifndef AppVersionNum
  #define AppVersionNum "3.0"
#endif
; 시험 빌드는 /DDistDir=<다른 폴더>로 — dist에서 실행 중인 앱을 끄지 않고 설치 파일을 만들 수 있다
#ifndef DistDir
  #define DistDir "dist\CNC_Watcher"
#endif

[Setup]
AppId={{BC4D901E-620B-4E5C-BC21-B464A1795A92}
AppName=CNC Watcher
AppVersion={#AppVersion}
AppVerName=CNC Watcher {#AppVersion}
VersionInfoVersion={#AppVersionNum}
SourceDir=..
OutputDir=dist
OutputBaseFilename=CNC_Watcher_Setup_{#AppVersion}
PrivilegesRequired=lowest
DefaultDirName={autopf}\CNC Watcher
DefaultGroupName=CNC Watcher
DisableProgramGroupPage=yes
DisableWelcomePage=no
DisableReadyPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=icons\watcher_icon.ico
UninstallDisplayIcon={app}\CNC_Watcher.exe
UninstallDisplayName=CNC Watcher
WizardStyle=modern
WizardImageFile=build\installer\wizard.bmp,build\installer\wizard200.bmp
WizardSmallImageFile=build\installer\small.bmp,build\installer\small200.bmp
Compression=lzma2/max
SolidCompression=yes
; 실행 중인 앱은 [Code]에서 설치 폴더 것만 직접 종료 (닫기를 누르면 트레이로 숨는 앱이라 재시작 관리자로는 안 닫힘)
CloseApplications=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Messages]
korean.ClickNext=계속하려면 [다음]을 누르세요.
korean.WelcomeLabel2=FANUC 장비 상태를 실시간으로 보여주는 [name/ver]을(를) 설치합니다.%n%n이미 실행 중이면 설치하면서 자동으로 종료합니다. 가공 이력과 설정은 그대로 남습니다.

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로 가기 만들기"; GroupDescription: "추가 작업:"
Name: "autostart"; Description: "윈도우 시작 시 자동 실행 (트레이로 숨겨서)"; GroupDescription: "추가 작업:"

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CNC Watcher"; Filename: "{app}\CNC_Watcher.exe"
Name: "{autodesktop}\CNC Watcher"; Filename: "{app}\CNC_Watcher.exe"; Tasks: desktopicon

[Registry]
; 앱의 ⚙ 설정 '윈도우 시작 시 자동 실행'과 같은 값 (startup.py)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "CNC Watcher"; ValueData: """{app}\CNC_Watcher.exe"" --tray"; Tasks: autostart; Check: not IsUpdate
; ↑ 앱 안 업데이트는 지난번 선택(UsePreviousTasks)을 따르므로, 그 뒤 ⚙ 설정에서 끈 자동 실행을 다시 켜지 않게

[Run]
Filename: "{app}\CNC_Watcher.exe"; Description: "지금 CNC Watcher 실행"; Flags: nowait postinstall skipifsilent
Filename: "{app}\CNC_Watcher.exe"; Parameters: "{param:RELAUNCH}"; Flags: nowait; Check: IsUpdate

[Code]
const
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';
  WebView2Key = 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function HasWebView2: Boolean;
var
  V: String;
begin
  Result := (RegQueryStringValue(HKLM32, WebView2Key, 'pv', V) and (V <> '') and (V <> '0.0.0.0'))
         or (RegQueryStringValue(HKCU, WebView2Key, 'pv', V) and (V <> '') and (V <> '0.0.0.0'));
end;

function InitializeSetup: Boolean;
var
  ErrorCode: Integer;
begin
  Result := True;
  // 윈도우 11은 기본 포함, 윈도우 10은 없을 수 있다 — 없으면 화면이 안 뜨므로 안내만 하고 설치는 계속
  if not HasWebView2 then
    if SuppressibleMsgBox('이 PC에는 Microsoft WebView2 런타임이 없어 CNC Watcher 화면이 뜨지 않을 수 있습니다.' + #13#10 +
                          '다운로드 페이지를 열까요? (설치는 계속 진행됩니다)', mbConfirmation, MB_YESNO, IDNO) = IDYES then
      ShellExec('open', 'https://developer.microsoft.com/microsoft-edge/webview2/', '', '', SW_SHOWNORMAL, ewNoWait, ErrorCode);
end;

function IsUpdate: Boolean;
begin
  Result := ExpandConstant('{param:UPDATE|0}') = '1';
end;

procedure StopRunningApp;
var
  Code: Integer;
  Wait: String;
begin
  // 설치 폴더에서 실행 중인 CNC Watcher만 종료 (다른 폴더의 exe는 건드리지 않음).
  // 앱 안 업데이트는 앱이 스스로 정상 종료(가동 기록 마감·장비 연결 해제)하는 중이라 30초까지 기다린 뒤 남아 있으면 종료
  if IsUpdate then
    Wait := 'try { $p | Wait-Process -Timeout 30 -ErrorAction Stop } catch {}; '
  else
    Wait := '';
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
       '-NoProfile -NonInteractive -Command "$p = @(Get-Process CNC_Watcher -ErrorAction SilentlyContinue | ' +
       'Where-Object { $_.Path -like ''' + ExpandConstant('{app}') + '\*'' }); if ($p) { ' + Wait +
       '$p | Stop-Process -Force -ErrorAction SilentlyContinue }"',
       '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopRunningApp;
  Result := '';
end;

function InitializeUninstall: Boolean;
begin
  StopRunningApp;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  V: String;
begin
  // 자동 실행이 이 설치본을 가리키면 지운다 (앱 ⚙ 설정에서 켠 경우 포함). 기록 폴더(AppData\Local\CNC Watcher)는 남긴다.
  if (CurUninstallStep = usPostUninstall) and RegQueryStringValue(HKCU, RunKey, 'CNC Watcher', V)
     and (Pos(Lowercase(ExpandConstant('{app}')), Lowercase(V)) > 0) then
    RegDeleteValue(HKCU, RunKey, 'CNC Watcher');
end;
