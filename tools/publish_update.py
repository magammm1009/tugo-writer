# -*- coding: utf-8 -*-
"""자동 업데이트용 파일(update/manifest.json, update/forms_bundle.zip)을 만든다.

1) 양식·투고처 새로 올리기
   python tools/publish_update.py data --bundle ../투고양식_묶음_202611 --version 2026-12-15 --notes "투고처 갱신"
   → update/forms_bundle.zip(양식목록.json의 made를 version으로) + manifest의 data 갱신

2) 프로그램 새 버전 올리기 (설치 파일을 먼저 만든 뒤)
   python tools/publish_update.py app --version 2.4 --windows dist/TugoWriter-Setup-2.4.exe \
          [--mac dist/TugoWriter-2.4.dmg] --notes "무엇이 바뀌었는지" --notes "한 줄 더"
   → manifest의 app 갱신. 설치 파일은 GitHub Releases의 태그 v<버전>에 같은 이름으로 올려야 한다.

그다음: git add update && git commit && git push (Releases 업로드는 웹에서)
"""
import argparse
import datetime
import hashlib
import io
import json
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPD = os.path.join(ROOT, 'update')
MANIFEST = os.path.join(UPD, 'manifest.json')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def repo():
    with open(os.path.join(ROOT, 'update_source.json'), encoding='utf-8') as f:
        return json.load(f)['repo']


def load_manifest():
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_manifest(m):
    os.makedirs(UPD, exist_ok=True)
    with open(MANIFEST, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
        f.write('\n')


def publish_data(bundle, version, notes):
    """bundle: 묶음 폴더(안에 양식목록.json, 투고처.json, BL/, 로맨스계열/ …)"""
    top = os.path.basename(os.path.normpath(bundle))
    out = os.path.join(UPD, 'forms_bundle.zip')
    os.makedirs(UPD, exist_ok=True)
    # 고정 시각으로 묶어서 내용이 같으면 zip도 같게
    stamp = (2026, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for base, dirs, names in os.walk(bundle):
            dirs.sort()
            for n in sorted(names):
                full = os.path.join(base, n)
                rel = os.path.relpath(full, os.path.dirname(os.path.normpath(bundle))).replace('\\', '/')
                data = open(full, 'rb').read()
                if n == '양식목록.json':
                    idx = json.loads(data.decode('utf-8-sig'))
                    idx['made'] = version
                    data = json.dumps(idx, ensure_ascii=False, indent=1).encode('utf-8')
                zi = zipfile.ZipInfo(rel, date_time=stamp)
                zi.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(zi, data)
    m = load_manifest()
    m['data'] = {
        'version': version,
        'url': 'https://raw.githubusercontent.com/%s/main/update/forms_bundle.zip' % repo(),
        'sha256': sha256(out),
        'size': os.path.getsize(out),
        'notes': ' / '.join(notes) if notes else '',
        'bundle': top,
    }
    save_manifest(m)
    print('data', version, m['data']['sha256'][:12], m['data']['size'], 'bytes')


def publish_app(version, windows, mac, notes):
    m = load_manifest()
    base = 'https://github.com/%s/releases/download/v%s/' % (repo(), version)
    app = {'version': version, 'date': datetime.date.today().isoformat(), 'notes': notes or [],
           'page': 'https://github.com/%s/releases/latest' % repo()}
    for key, path in (('windows', windows), ('mac', mac)):
        if path:
            app[key] = {'url': base + os.path.basename(path), 'sha256': sha256(path), 'size': os.path.getsize(path)}
        elif (m.get('app') or {}).get('version') == version and (m.get('app') or {}).get(key):
            app[key] = m['app'][key]          # 같은 버전에 다른 쪽만 추가하는 경우 기존 값 유지
    m['app'] = app
    save_manifest(m)
    print('app', version, [k for k in ('windows', 'mac') if k in app])


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    d = sp.add_parser('data')
    d.add_argument('--bundle', required=True)
    d.add_argument('--version', required=True)
    d.add_argument('--notes', action='append')
    a = sp.add_parser('app')
    a.add_argument('--version', required=True)
    a.add_argument('--windows')
    a.add_argument('--mac')
    a.add_argument('--notes', action='append')
    args = ap.parse_args()
    if args.cmd == 'data':
        publish_data(args.bundle, args.version, args.notes)
    else:
        publish_app(args.version, args.windows, args.mac, args.notes)


if __name__ == '__main__':
    main()
