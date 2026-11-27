# -*- coding: utf-8 -*-
"""양식 묶음(zip 또는 폴더) 읽기, 결과 파일 이름 짓기, 일괄 작성."""
import csv
import datetime
import hashlib
import io
import json
import os
import re
import zipfile

from .engine import fill_hwpx


GENRE_ORDER = ['BL', '로맨스', '로맨스판타지', '현대로맨스', '19단편', 'GL']
INDEX_NAME = '양식목록.json'
SUBMIT_NAME = '투고처.json'   # 레이블별 투고처(이메일·폼·사이트)


class FormEntry(object):
    def __init__(self, key, folder, filename, loader, publisher='', brand='', number=None, genres=None, source=''):
        self.key = key              # 고유 키(원본 경로)
        self.folder = folder        # 예: 01_해피북스투유_해피북스투유
        self.filename = filename    # 예: 해피북스투유_작품 기획안.hwpx
        self._loader = loader
        self.publisher = publisher
        self.brand = brand
        self.number = number
        self.genres = list(genres or [])
        self.source = source        # 양식을 받은 곳(출판사 직접 제공 등)
        self.submit = None          # 투고처 정보 {methods:[{type,value,note,check}], guide, origin}

    def read(self):
        return self._loader()

    @property
    def display(self):
        num = '%02d ' % self.number if self.number is not None else ''
        who = self.publisher + (' · ' + self.brand if self.brand and self.brand != self.publisher else '')
        return '%s%s' % (num, who or self.folder)

    @property
    def genre_text(self):
        short = {'로맨스판타지': '로판', '현대로맨스': '현로'}
        return ', '.join(short.get(g, g) for g in GENRE_ORDER if g in self.genres) or '-'

    @property
    def stem(self):
        return os.path.splitext(self.filename)[0]


def _decode_name(info):
    """한글 파일 이름이 cp437로 깨져 있으면 cp949로 다시 읽는다."""
    name = info.filename
    if info.flag_bits & 0x800:
        return name
    try:
        return name.encode('cp437').decode('cp949')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def _label_key(s):
    s = (s or '').lower().replace('(주)', '').replace('주식회사', '')
    return re.sub(r'[^0-9a-z가-힣]', '', s)


def _split_folder(folder):
    m = re.match(r'^(\d{1,3})_(.+)$', folder)
    if not m:
        return None, folder, ''
    num, rest = int(m.group(1)), m.group(2)
    parts = rest.split('_', 1)
    return num, parts[0], (parts[1] if len(parts) > 1 else '')


def _meta_from_csv(text):
    meta = {}
    try:
        rd = csv.DictReader(io.StringIO(text))
        for row in rd:
            try:
                n = int((row.get('XLSX 대상 순서') or row.get('﻿XLSX 대상 순서') or '').strip())
            except ValueError:
                continue
            meta[n] = ((row.get('출판사') or '').strip(), (row.get('브랜드') or '').strip())
    except Exception:
        pass
    return meta


def load_forms(path):
    """zip 파일 또는 폴더에서 .hwpx 양식 목록을 만든다(같은 출판사 폴더 안 중복 파일은 하나만)."""
    entries = []
    meta = {}
    if os.path.isdir(path):
        files = []
        for base, _, names in os.walk(path):
            for n in names:
                full = os.path.join(base, n)
                rel = os.path.relpath(full, path).replace('\\', '/')
                files.append((rel, full))
                if n.endswith('.csv') and '목록' in n:
                    with open(full, encoding='utf-8-sig', errors='replace') as f:
                        meta.update(_meta_from_csv(f.read()))
        items = [(rel, (lambda f=full: open(f, 'rb').read())) for rel, full in files]
    else:
        zf = zipfile.ZipFile(path)
        items = []
        nested = []
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = _decode_name(info)
            if name.lower().endswith('.zip'):
                nested.append(info)
                continue
            items.append((name, (lambda i=info, z=zf: z.read(i))))
            if name.endswith('.csv') and '목록' in name:
                meta.update(_meta_from_csv(zf.read(info).decode('utf-8-sig', errors='replace')))
        # zip 안에 zip(양식 묶음을 한 번 더 압축한 경우)
        for info in nested:
            inner = zipfile.ZipFile(io.BytesIO(zf.read(info)))
            for ii in inner.infolist():
                if ii.is_dir():
                    continue
                name = _decode_name(ii)
                items.append((name, (lambda i=ii, z=inner: z.read(i))))
                if name.endswith('.csv') and '목록' in name:
                    meta.update(_meta_from_csv(inner.read(ii).decode('utf-8-sig', errors='replace')))
    # 장르 정보가 담긴 목록 파일(양식목록.json): {"groups": [{"dir": "로맨스계열/01_청어람_청어람", "publisher":..,
    #   "label":.., "genres": [..], "source": ..}, ...]}
    index, submits = {}, {}
    for rel, loader in items:
        if rel.split('/')[-1] == SUBMIT_NAME:
            try:
                data = json.loads(loader().decode('utf-8-sig'))
                prefix = rel[:-len(SUBMIT_NAME)]
                for lab in data.get('labels', []):
                    lab['checked'] = data.get('checked', '')
                    submits[(prefix + lab['dir']).strip('/')] = lab
            except Exception:
                pass
        if rel.split('/')[-1] == INDEX_NAME:
            try:
                data = json.loads(loader().decode('utf-8-sig'))
                prefix = rel[:-len(INDEX_NAME)]
                for g in data.get('groups', []):
                    index[(prefix + g['dir']).strip('/')] = g
            except Exception:
                pass
    guess_bl = (not index) and bool(re.search(r'BL', os.path.basename(str(path)), re.I))

    seen = {}
    for rel, loader in sorted(items, key=lambda x: x[0]):
        if not rel.lower().endswith('.hwpx'):
            continue
        parts = rel.split('/')
        folder = ''
        for seg in parts[:-1]:
            if re.match(r'^\d{1,3}_', seg):
                folder = seg
                break
        if not folder:
            folder = parts[-2] if len(parts) >= 2 else ''
        info = None
        dir_rel = '/'.join(parts[:-1])
        for k in sorted(index, key=len, reverse=True):
            if dir_rel == k or dir_rel.startswith(k + '/'):
                info = index[k]
                break
        num, pub, brand = _split_folder(folder)
        genres, source = [], ''
        if info:
            pub, brand = info.get('publisher', pub), info.get('label', brand)
            genres, source = info.get('genres', []), info.get('source', '')
            num = None
        else:
            if num is not None and num in meta:
                pub, brand = meta[num]
            if guess_bl:
                genres = ['BL']
        data = loader()
        h = hashlib.sha1(data).hexdigest()
        dup_key = (_label_key(pub) + '|' + _label_key(brand), h)
        if dup_key in seen:
            # 같은 레이블의 같은 양식이 여러 장르 묶음에 있으면 하나로 합치고 장르만 더한다
            e = seen[dup_key]
            e.genres += [g for g in genres if g not in e.genres]
            continue
        e = FormEntry(rel, folder, parts[-1], (lambda d=data: d), pub, brand.replace('_', '/'), num, genres, source)
        for k in sorted(submits, key=len, reverse=True):
            if dir_rel == k or dir_rel.startswith(k + '/'):
                e.submit = submits[k]
                break
        seen[dup_key] = e
        entries.append(e)
    entries.sort(key=lambda e: (e.number if e.number is not None else 999, e.publisher, e.brand, e.filename))
    return entries


# ---------------------------------------------------------------------------
# 결과 파일 이름
# ---------------------------------------------------------------------------
_BAD = re.compile(r'[\\/:*?"<>|\r\n\t]')

SPECIAL_NAMES = [
    # (파일 이름에 들어 있는 글자, 출판사 안내 규칙)
    ('[리케]투고', '{pen}({title})_{ymd}'),
    ('원고+투고+양식', '{genre}_{pen}_{title}'),
]


def _safe(s, limit=40):
    s = _BAD.sub(' ', s or '').strip()
    s = re.sub(r'\s+', ' ', s)
    return s[:limit].strip()


def output_name(entry, project, today=None):
    today = today or datetime.date.today()
    title = _safe(project.get('title')) or '작품명'
    pen = _safe(project.get('pen')) or '필명'
    genre = _safe(project.get('genre'), 15) or '장르'
    stem = entry.stem.strip()
    for key, pattern in SPECIAL_NAMES:
        if key in stem:
            return _safe(pattern.format(pen=pen, title=title, genre=genre, ymd=today.strftime('%Y%m%d')), 120) + '.hwpx'
    s = stem
    original = s
    s = re.sub(r'장르\([^)]*\)', genre, s)
    s = s.replace('2000.00.00', today.strftime('%Y.%m.%d'))
    s = re.sub(r'(?<![가-힣])20\d\d\.\d\d\.\d\d', today.strftime('%Y.%m.%d'), s) if '2000.00.00' in original else s
    tokens = [('작품제목', title), ('작품명', title), ('제목', title), ('작가필명', pen), ('작가명', pen), ('필명', pen),
              ('장르', genre)]
    for tok, val in tokens:
        s = re.sub(r'(?<=[\s_\-\[\(\]\)])%s(?=[\s_\-\]\)\[\(]|$)|^%s(?=[\s_\-\]\)\[\(]|$)' % (tok, tok), val, s)
    s = re.sub(r'(?<=[_\-\s])작가(?=[_\-\s\)\]]|$)', pen, s)
    if s == original:
        s = '%s_%s_%s' % (original, title, pen)
    else:
        if title not in s:
            s += '_' + title
        if pen not in s:
            s += '_' + pen
    return _safe(s, 120) + '.hwpx'


# ---------------------------------------------------------------------------
# 일괄 작성
# ---------------------------------------------------------------------------
def run_batch(entries, project, out_dir, progress=None, dry_run=False):
    """entries를 모두 채워 out_dir에 저장. 진행 상황은 progress(i, total, entry, report) 콜백."""
    results = []
    if not dry_run:
        os.makedirs(out_dir, exist_ok=True)
    used_names = set()
    for i, e in enumerate(entries):
        rep = None
        out_path = None
        try:
            data, rep = fill_hwpx(e.read(), project, e.display, dry_run=dry_run)
            if not dry_run:
                sub = os.path.join(out_dir, _safe(e.folder, 60) or '기타')
                os.makedirs(sub, exist_ok=True)
                name = output_name(e, project)
                base, ext = os.path.splitext(name)
                k = 2
                while os.path.join(sub, name).lower() in used_names:
                    name = '%s (%d)%s' % (base, k, ext)
                    k += 1
                out_path = os.path.join(sub, name)
                used_names.add(out_path.lower())
                with open(out_path, 'wb') as f:
                    f.write(data)
        except Exception as ex:  # 한 양식이 실패해도 나머지는 계속
            from .engine import FormReport
            rep = rep or FormReport(e.display)
            rep.error = '%s: %s' % (type(ex).__name__, ex)
        results.append((e, rep, out_path))
        if progress:
            progress(i + 1, len(entries), e, rep)
    return results


def bundle_version(path):
    """양식 묶음(zip/폴더)의 버전(양식목록.json의 made 날짜). 없으면 ''"""
    try:
        if os.path.isdir(path):
            for base, _, names in os.walk(path):
                if INDEX_NAME in names:
                    with open(os.path.join(base, INDEX_NAME), encoding='utf-8-sig') as f:
                        return str(json.load(f).get('made', ''))
            return ''
        with zipfile.ZipFile(path) as zf:
            for n in zf.namelist():
                if n.endswith('/' + INDEX_NAME) or n == INDEX_NAME:
                    return str(json.loads(zf.read(n).decode('utf-8-sig')).get('made', ''))
    except Exception:
        pass
    return ''
