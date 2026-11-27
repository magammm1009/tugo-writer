# -*- coding: utf-8 -*-
"""BL 양식 묶음 + 새로 받은 로맨스 계열 양식을 장르 정보와 함께 하나의 묶음(zip)으로 만든다.

사용: python tools/build_bundle.py <BL zip> <manifest.json> <dl_index.json> <hwpx 폴더> <출력 폴더>
"""
import datetime
import json
import os
import re
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tugo.forms import load_forms, INDEX_NAME  # noqa: E402


def key(s):
    return re.sub(r'[^0-9a-z가-힣]', '', (s or '').lower().replace('(주)', '').replace('주식회사', ''))


def main():
    bl_zip, manifest_p, dl_p, hwpx_dir, out = sys.argv[1:6]
    manifest = json.load(open(manifest_p, encoding='utf-8'))
    dl = json.load(open(dl_p, encoding='utf-8'))
    # 투고하다 레이블 → 장르
    label_genres = {}
    for r in manifest:
        label_genres[(key(r['publisher']), key(r['label']))] = r['genres']
    by_label_only = {}
    for (p, l), g in label_genres.items():
        by_label_only.setdefault(l, []).append((p, g))

    def lookup(pub, label):
        g = label_genres.get((key(pub), key(label)))
        if g:
            return g
        cands = by_label_only.get(key(label), [])
        for p, g in cands:
            if p in key(pub) or key(pub) in p:
                return g
        return None

    if os.path.exists(out):
        raise SystemExit('출력 폴더가 이미 있어요: ' + out)
    os.makedirs(out)
    groups = []

    # 1) 새로 받은 양식(로맨스 계열)
    new_labels = set()
    folders = {}
    for x in dl:
        if 'error' in x:
            continue
        folders.setdefault(x['folder'], x)
    for folder, x in sorted(folders.items()):
        src = os.path.join(hwpx_dir, folder)
        files = [f for f in os.listdir(src) if f.lower().endswith('.hwpx')] if os.path.isdir(src) else []
        if not files:
            continue
        genres = list(x['genres'])
        new_labels.add((key(x['publisher']), key(x['label'])))
        dst = os.path.join(out, '로맨스계열', folder)
        os.makedirs(dst)
        for f in files:
            shutil.copy2(os.path.join(src, f), os.path.join(dst, f))
        groups.append({'dir': '로맨스계열/' + folder, 'publisher': x['publisher'], 'label': x['label'],
                       'genres': genres, 'source': x['source'], 'url': x.get('toogo', '')})

    # 2) 기존 BL 묶음
    bl = load_forms(bl_zip)
    bl_dirs = {}
    for e in bl:
        k = (key(e.publisher), key(e.brand))
        romance = lookup(e.publisher, e.brand)
        if k in new_labels:
            # 같은 레이블의 최신 공식 양식을 새로 받았으므로 그쪽에 BL을 더하고 옛 파일은 뺀다
            for g in groups:
                if (key(g['publisher']), key(g['label'])) == k and 'BL' not in g['genres']:
                    g['genres'].insert(0, 'BL')
            continue
        genres = ['BL']
        if romance and not re.search(r'BL', e.filename, re.I):
            genres += [g for g in romance if g not in genres]
        folder = e.folder or re.sub(r'[\\/:*?"<>|]', ' ', e.publisher + '_' + e.brand)
        dst = os.path.join(out, 'BL', folder)
        os.makedirs(dst, exist_ok=True)
        with open(os.path.join(dst, e.filename), 'wb') as f:
            f.write(e.read())
        if folder not in bl_dirs:
            bl_dirs[folder] = {'dir': 'BL/' + folder, 'publisher': e.publisher, 'label': e.brand,
                               'genres': genres, 'source': '기존 BL 양식 묶음(2026-10 수집)'}
            groups.append(bl_dirs[folder])
        else:
            bl_dirs[folder]['genres'] += [g for g in genres if g not in bl_dirs[folder]['genres']]

    index = {'made': datetime.date.today().isoformat(),
             'note': '출판사 공식 투고 양식 묶음. 로맨스계열은 투고하다(toogohada.com) 「투고 접수중」 레이블 중 '
                     '출판사가 양식 파일을 공개한 곳에서 받아 한컴오피스로 hwpx로 바꾼 것.',
             'groups': groups}
    with open(os.path.join(out, INDEX_NAME), 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    zpath = out.rstrip('/\\') + '.zip'
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        for base, _, names in os.walk(out):
            for n in names:
                full = os.path.join(base, n)
                z.write(full, os.path.relpath(full, os.path.dirname(out)))
    from collections import Counter
    c = Counter(g for x in groups for g in x['genres'])
    print('groups', len(groups), dict(c), '->', zpath)


if __name__ == '__main__':
    main()
