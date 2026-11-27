# -*- coding: utf-8 -*-
"""collect_forms.py가 만든 목록에서 양식 파일을 내려받는다(실행하지 않고 파일로 저장만).

- 레이블마다: hwpx가 있으면 hwpx, 없으면 hwp, 둘 다 없으면 docx
- 저장: <out>/<번호>_<출판사>_<레이블>/<파일>
- 같은 내용 파일(해시)이 이미 있으면 중복 저장하지 않고 목록에만 기록
사용: python tools/download_forms.py <manifest.json> <out_dir> <index.json>
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.request

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) tugo-form-collector'
BAD = re.compile(r'[\\/:*?"<>|]')
SKIP = re.compile(r'script|원고\s*양식|writer', re.I)   # 원고 본문용 서식은 제외(시놉시스·투고 양식만)


def safe(s):
    return re.sub(r'\s+', ' ', BAD.sub(' ', s)).strip()


def pick(files):
    by_stem = {}
    for f in files:
        stem, ext = os.path.splitext(f['name'])
        by_stem.setdefault(re.sub(r'\s+', '', stem), []).append((ext.lower(), f))
    chosen = []
    for stem, lst in by_stem.items():
        lst.sort(key=lambda x: {'.hwpx': 0, '.hwp': 1, '.docx': 2, '.doc': 3}.get(x[0], 9))
        chosen.append(lst[0][1])
    forms = [f for f in chosen if not SKIP.search(f['name'])]
    return forms or chosen


def main():
    manifest = json.load(open(sys.argv[1], encoding='utf-8'))
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    index, hashes = [], {}
    n = 0
    for rec in manifest:
        if not rec['files']:
            continue
        n += 1
        folder = '%02d_%s_%s' % (n, safe(rec['publisher']), safe(rec['label']))
        os.makedirs(os.path.join(out, folder), exist_ok=True)
        for f in pick(rec['files']):
            req = urllib.request.Request(f['url'], headers={'User-Agent': UA, 'Referer': 'https://blog.naver.com/'})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
            except Exception as ex:
                index.append({'folder': folder, 'name': f['name'], 'error': str(ex), **_meta(rec, f)})
                continue
            time.sleep(1.0)
            h = hashlib.sha1(data).hexdigest()
            path = os.path.join(folder, safe(f['name']))
            with open(os.path.join(out, path), 'wb') as fo:
                fo.write(data)
            index.append({'folder': folder, 'name': safe(f['name']), 'bytes': len(data), 'sha1': h,
                          'same_as': hashes.get(h), **_meta(rec, f)})
            hashes.setdefault(h, path)
            print(folder, f['name'], len(data), file=sys.stderr)
    with open(sys.argv[3], 'w', encoding='utf-8') as fo:
        json.dump(index, fo, ensure_ascii=False, indent=1)


def _meta(rec, f):
    return {'publisher': rec['publisher'], 'label': rec['label'], 'genres': rec['genres'], 'url': f['url'],
            'source': f['source'], 'toogo': rec['toogo']}


if __name__ == '__main__':
    main()
