# 윈도우용 실행 파일 + 설치 파일 만들기
# 사용: powershell -ExecutionPolicy Bypass -File tools\build_windows.ps1 -Version 2.3
# 결과: dist\TugoWriter.exe, dist\TugoWriter-Setup-<버전>.exe
param([Parameter(Mandatory = $true)][string]$Version)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# 1) app.py의 VERSION과 맞는지 확인
$v = (Select-String -Path app.py -Pattern "^VERSION = '([^']+)'").Matches[0].Groups[1].Value
if ($v -ne $Version) { throw "app.py VERSION($v) != -Version($Version). app.py first." }

# 2) 실행 파일(PyInstaller) - 경로는 모두 절대 경로(PyInstaller는 상대 경로를 spec 폴더 기준으로 읽음)
python -m PyInstaller --noconfirm --onefile --windowed --name TugoWriter `
    --icon "$root\assets\icon.ico" `
    --add-data "$root\assets\icon.ico;assets" --add-data "$root\assets\icon.png;assets" `
    --add-data "$root\update_source.json;." `
    --distpath "$root\dist" --workpath "$root\build" --specpath "$root\build" `
    --exclude-module numpy --exclude-module PIL --exclude-module matplotlib `
    "$root\app.py"
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }

# 3) 함께 넣을 양식 묶음 이름: update/manifest.json의 data.version 날짜
$m = Get-Content "$root\update\manifest.json" -Raw -Encoding UTF8 | ConvertFrom-Json
$bundleName = '투고양식_묶음_' + ($m.data.version -replace '[^0-9]', '') + '.zip'

# 4) 설치 파일(Inno Setup)
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
          "C:\Program Files\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw 'Inno Setup 6 (ISCC.exe) not found: winget install JRSoftware.InnoSetup' }
# Dropbox 폴더 안에서 바로 만들면 동기화가 파일을 잠가 실패할 수 있어 임시 폴더에서 만든 뒤 복사
$tmpOut = Join-Path $env:TEMP 'tugo_setup_out'
New-Item -ItemType Directory -Force $tmpOut | Out-Null
& $iscc "/DAppVersion=$Version" "/DBundleFile=$root\update\forms_bundle.zip" "/DBundleName=$bundleName" "/O$tmpOut" "$root\installer\TugoWriter.iss"
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed' }
Copy-Item (Join-Path $tmpOut "TugoWriter-Setup-$Version.exe") "$root\dist\" -Force

Get-ChildItem "$root\dist" | Select-Object Name, Length
