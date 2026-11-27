#!/bin/bash
# 맥용 앱(.app)과 배포용 디스크 이미지(.dmg) 만들기
# 사용(맥 터미널에서 저장소 폴더로 이동한 뒤):  bash tools/build_mac.sh 2.3
# 결과: dist/투고 양식 자동 작성기.app, dist/TugoWriter-<버전>.dmg
set -euo pipefail
VERSION="${1:?버전을 적어 주세요. 예: bash tools/build_mac.sh 2.3}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APPV=$(grep -E "^VERSION = '" app.py | sed -E "s/VERSION = '([^']+)'/\1/")
if [ "$APPV" != "$VERSION" ]; then echo "app.py VERSION($APPV)과 입력한 버전($VERSION)이 달라요"; exit 1; fi

# 1) 빌드용 파이썬 환경(처음 한 번만 오래 걸림). 파이썬은 python.org 설치본(Tk 포함)을 권장
if [ ! -d .venv-mac ]; then
  python3 -m venv .venv-mac
fi
source .venv-mac/bin/activate
pip install --quiet --upgrade pip
pip install --quiet lxml pyinstaller pillow

# 2) 맥 아이콘(.icns): assets/icon.png에서 만든다
mkdir -p build/icon.iconset
for s in 16 32 64 128 256 512; do
  sips -z $s $s assets/icon.png --out build/icon.iconset/icon_${s}x${s}.png >/dev/null
  d=$((s*2)); sips -z $d $d assets/icon.png --out build/icon.iconset/icon_${s}x${s}@2x.png >/dev/null
done
iconutil -c icns build/icon.iconset -o build/icon.icns

# 3) 함께 넣을 양식 묶음(이름에 '투고양식_묶음'이 있어야 프로그램이 찾음)
DATAV=$(python3 -c "import json;print(json.load(open('update/manifest.json'))['data']['version'].replace('-',''))")
cp update/forms_bundle.zip "build/투고양식_묶음_${DATAV}.zip"

# 4) 앱 만들기
python3 -m PyInstaller --noconfirm --windowed --name "투고 양식 자동 작성기" \
  --icon build/icon.icns \
  --osx-bundle-identifier io.github.magammm1009.tugowriter \
  --add-data "assets/icon.png:assets" \
  --add-data "update_source.json:." \
  --add-data "build/투고양식_묶음_${DATAV}.zip:." \
  --distpath dist --workpath build/pyi --specpath build \
  app.py

# 5) .dmg(앱 + 응용 프로그램 폴더 바로가기)
rm -rf build/dmg && mkdir -p build/dmg
cp -R "dist/투고 양식 자동 작성기.app" build/dmg/
ln -s /Applications build/dmg/Applications
rm -f "dist/TugoWriter-${VERSION}.dmg"
hdiutil create -volname "투고 양식 자동 작성기 ${VERSION}" -srcfolder build/dmg -ov -format UDZO "dist/TugoWriter-${VERSION}.dmg"

echo
echo "완료: dist/TugoWriter-${VERSION}.dmg"
echo "다음: GitHub Releases의 v${VERSION}에 이 dmg를 올리고,"
echo "      python3 tools/publish_update.py app --version ${VERSION} --mac dist/TugoWriter-${VERSION}.dmg 로 manifest를 고친 뒤 push"
