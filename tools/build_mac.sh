#!/bin/bash
# 맥용 앱(.app)과 배포용 디스크 이미지(.dmg) 만들기
# 사용(맥 터미널에서 저장소 폴더로 이동한 뒤):  bash tools/build_mac.sh 2.3
# 결과: dist/TugoWriter-<버전>.dmg  (앱 자체는 작업 폴더의 dist/ 안에 남는다)
#
# 작업 폴더(기본 ~/Library/Caches/tugo-writer-build)를 저장소 밖에 두는 까닭:
#   Dropbox·iCloud 같은 동기화 폴더 안에서 만들면 파일에 붙는 부가 정보 때문에 서명이 깨지고,
#   파일 수천 개(파이썬 환경·앱 내부)가 동기화돼요. 바꾸려면 TUGO_BUILD_DIR=<폴더>.
# 파이썬을 직접 고르려면 PYTHON=<경로>.
set -euo pipefail
VERSION="${1:?버전을 적어 주세요. 예: bash tools/build_mac.sh 2.3}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP_NAME="투고 양식 자동 작성기"
EXE_NAME="TugoWriter"
BUNDLE_ID="io.github.magammm1009.tugowriter"
WORK="${TUGO_BUILD_DIR:-$HOME/Library/Caches/tugo-writer-build}"

APPV=$(grep -E "^VERSION = '" app.py | sed -E "s/VERSION = '([^']+)'/\1/")
if [ "$APPV" != "$VERSION" ]; then echo "app.py VERSION($APPV)과 입력한 버전($VERSION)이 달라요"; exit 1; fi

# 1) 파이썬 고르기: Tk 8.6 이상이 들어 있어야 한다(python.org 설치본).
#    Homebrew python3에는 Tk가 없고, 맥 기본 python3는 Tk 8.5라 화면이 깨진다.
has_tk() { "$1" -c "import tkinter, sys; sys.exit(0 if tkinter.TkVersion >= 8.6 else 1)" >/dev/null 2>&1; }
PY=""
for cand in "${PYTHON:-}" \
    /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
    "$(command -v python3 || true)"; do
  if [ -n "$cand" ] && [ -x "$cand" ] && has_tk "$cand"; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  echo "Tk 8.6 이상이 든 파이썬을 찾지 못했어요. https://www.python.org/downloads/macos/ 에서 설치해 주세요."
  exit 1
fi
echo "파이썬: $PY ($("$PY" -c 'import platform, tkinter; print(platform.python_version(), "/ Tk", tkinter.Tcl().eval("info patchlevel"))'))"

# 2) 빌드용 파이썬 환경(처음 한 번만 오래 걸림)
mkdir -p "$WORK"
VENV="$WORK/venv"
if [ -d "$VENV" ] && ! has_tk "$VENV/bin/python"; then rm -rf "$VENV"; fi
if [ ! -d "$VENV" ]; then "$PY" -m venv "$VENV"; fi
VPY="$VENV/bin/python"
"$VPY" -m pip install --quiet --upgrade pip
# certifi: 맥용 앱이 https(자동 업데이트)에 쓸 인증서 묶음
"$VPY" -m pip install --quiet --upgrade lxml pyinstaller certifi

# 3) 인텔·애플 실리콘 겸용(universal2)으로 만들 수 있는지: 파이썬과 lxml이 둘 다 겸용이어야 한다
both_archs() { a=$(lipo -archs "$1" 2>/dev/null || true); [[ "$a" == *x86_64* && "$a" == *arm64* ]]; }
ARCH_OPT=()
ARCH_LABEL="$(uname -m) 전용"
REAL_PY=$("$VPY" -c "import os, sys; print(os.path.realpath(sys.executable))")
ETREE=$("$VPY" -c "import lxml.etree as e; print(e.__file__)")
if both_archs "$REAL_PY" && both_archs "$ETREE"; then
  ARCH_OPT=(--target-arch universal2)
  ARCH_LABEL="인텔·애플 실리콘 겸용(universal2)"
fi
echo "대상: $ARCH_LABEL"

# 4) 맥 아이콘(.icns): assets/icon.png에서 만든다
rm -rf "$WORK/icon.iconset" && mkdir -p "$WORK/icon.iconset"
for s in 16 32 128 256 512; do
  sips -z $s $s assets/icon.png --out "$WORK/icon.iconset/icon_${s}x${s}.png" >/dev/null
  d=$((s*2)); sips -z $d $d assets/icon.png --out "$WORK/icon.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$WORK/icon.iconset" -o "$WORK/icon.icns"

# 5) 함께 넣을 양식 묶음(이름에 '투고양식_묶음'이 있어야 프로그램이 찾음)
DATAV=$("$VPY" -c "import json;print(json.load(open('update/manifest.json', encoding='utf-8'))['data']['version'].replace('-',''))")
BUNDLE_ZIP="$WORK/투고양식_묶음_${DATAV}.zip"
rm -f "$WORK"/투고양식_묶음_*.zip
cp update/forms_bundle.zip "$BUNDLE_ZIP"

# 6) 앱 만들기 - 경로는 모두 절대 경로(PyInstaller는 상대 경로를 spec 폴더 기준으로 읽음)
#    실행 파일 이름은 영문(TugoWriter)이어야 한다. 한글이면 codesign --deep이 실행 파일을
#    앱 안의 또 다른 코드로 잘못 보고 끝없이 되풀이하다 죽는다(Bus error). 앱 이름은 7)에서 한글로 바꾼다.
rm -rf "$WORK/dist" "$WORK/pyi"
"$VPY" -m PyInstaller --noconfirm --windowed --name "$EXE_NAME" \
  --icon "$WORK/icon.icns" \
  --osx-bundle-identifier "$BUNDLE_ID" \
  ${ARCH_OPT[@]+"${ARCH_OPT[@]}"} \
  --add-data "$ROOT/assets/icon.png:assets" \
  --add-data "$ROOT/update_source.json:." \
  --add-data "$BUNDLE_ZIP:." \
  --exclude-module numpy --exclude-module PIL --exclude-module matplotlib \
  --distpath "$WORK/dist" --workpath "$WORK/pyi" --specpath "$WORK" \
  "$ROOT/app.py"
rm -rf "$WORK/dist/$EXE_NAME"            # 앱 묶음만 남긴다(같은 내용의 폴더판)
APP="$WORK/dist/$APP_NAME.app"
mv "$WORK/dist/$EXE_NAME.app" "$APP"

# 7) 앱 이름(한글)·버전 정보(Finder의 「정보 가져오기」에 보임)를 넣고 다시 서명(인증서 없는 임시 서명)
PLIST="$APP/Contents/Info.plist"
plutil -replace CFBundleName -string "$APP_NAME" "$PLIST"
plutil -replace CFBundleDisplayName -string "$APP_NAME" "$PLIST"
plutil -replace CFBundleShortVersionString -string "$VERSION" "$PLIST"
plutil -replace CFBundleVersion -string "$VERSION" "$PLIST"
plutil -replace LSApplicationCategoryType -string "public.app-category.productivity" "$PLIST"
xattr -cr "$APP"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

# 8) .dmg(앱 + 응용 프로그램 폴더 바로가기)
rm -rf "$WORK/dmg" && mkdir -p "$WORK/dmg"
ditto "$APP" "$WORK/dmg/$APP_NAME.app"
ln -s /Applications "$WORK/dmg/Applications"
DMG="$WORK/TugoWriter-${VERSION}.dmg"
rm -f "$DMG"
hdiutil create -volname "$APP_NAME ${VERSION}" -srcfolder "$WORK/dmg" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$WORK/dmg"

mkdir -p "$ROOT/dist"
cp -f "$DMG" "$ROOT/dist/TugoWriter-${VERSION}.dmg"

echo
echo "완료: dist/TugoWriter-${VERSION}.dmg  ($ARCH_LABEL)"
echo "앱(바로 열어 볼 수 있음): $APP"
echo "다음: GitHub Releases의 v${VERSION}에 이 dmg를 올리고,"
echo "      python3 tools/publish_update.py app --version ${VERSION} --mac dist/TugoWriter-${VERSION}.dmg 로 manifest를 고친 뒤 push"
