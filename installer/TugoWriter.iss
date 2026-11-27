; 투고 양식 자동 작성기 — 윈도우 설치 파일 (Inno Setup 6)
; 만들기: tools\build_windows.ps1 (AppVersion·Bundle 값을 넘겨 줌)
;   ISCC.exe /DAppVersion=2.3 /DBundleFile=..\update\forms_bundle.zip /DBundleName=투고양식_묶음_20261128.zip TugoWriter.iss

#ifndef AppVersion
  #define AppVersion "0.0"
#endif
#ifndef BundleFile
  #define BundleFile "..\update\forms_bundle.zip"
#endif
#ifndef BundleName
  #define BundleName "투고양식_묶음.zip"
#endif

[Setup]
AppId={{6E4B2C1A-7D3F-4E8B-9A51-2F0C8D7E3B14}
AppName=투고 양식 자동 작성기
AppVersion={#AppVersion}
AppVerName=투고 양식 자동 작성기 {#AppVersion}
AppPublisher=tugo-writer
AppPublisherURL=https://github.com/magammm1009/tugo-writer
AppSupportURL=https://github.com/magammm1009/tugo-writer
AppUpdatesURL=https://github.com/magammm1009/tugo-writer/releases
; 관리자 권한 없이 사용자 폴더에 설치
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\TugoWriter
DefaultGroupName=투고 양식 자동 작성기
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=TugoWriter-Setup-{#AppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\TugoWriter.exe
UninstallDisplayName=투고 양식 자동 작성기
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; 새 버전을 덮어 설치할 때 실행 중이면 닫도록 안내
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕 화면에 바로가기 만들기"; GroupDescription: "바로가기:"

[InstallDelete]
; 예전 버전의 양식 묶음은 지우고 새 것으로(사용자가 받은 업데이트는 AppData에 따로 있음)
Type: files; Name: "{app}\투고양식_묶음_*.zip"

[Files]
Source: "..\dist\TugoWriter.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#BundleFile}"; DestDir: "{app}"; DestName: "{#BundleName}"; Flags: ignoreversion
Source: "..\update_source.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\사용법.md"; DestDir: "{app}"; DestName: "사용법.txt"; Flags: ignoreversion
Source: "..\예시_작품.json"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\투고 양식 자동 작성기"; Filename: "{app}\TugoWriter.exe"
Name: "{group}\사용법"; Filename: "{app}\사용법.txt"
Name: "{group}\투고 양식 자동 작성기 제거"; Filename: "{uninstallexe}"
Name: "{userdesktop}\투고 양식 자동 작성기"; Filename: "{app}\TugoWriter.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\TugoWriter.exe"; Description: "지금 실행하기"; Flags: nowait postinstall skipifsilent

; 제거할 때 작가님이 입력한 내용(%APPDATA%\BL투고양식작성기)은 지우지 않는다.
