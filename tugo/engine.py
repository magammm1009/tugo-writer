# -*- coding: utf-8 -*-
"""HWPX 양식을 열어 칸을 찾아 채우고 다시 저장하는 엔진."""
import io
import re
import zipfile
from collections import Counter

from lxml import etree

from . import rules as R
from .values import Resolver, SLOT_NAMES

NS_HP = 'http://www.hancom.co.kr/hwpml/2011/paragraph'
NS_HH = 'http://www.hancom.co.kr/hwpml/2011/head'
HP = '{%s}' % NS_HP
HH = '{%s}' % NS_HH
TEXT_RUN_CHILDREN = {HP + 't'}
OBJECT_TAGS = {HP + 'tbl', HP + 'pic', HP + 'container', HP + 'ole', HP + 'equation', HP + 'rect', HP + 'line',
               HP + 'ellipse', HP + 'arc', HP + 'polygon', HP + 'curve', HP + 'connectLine', HP + 'textart'}
XML_DECL = b'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'


# ---------------------------------------------------------------------------
# 문단 도우미
# ---------------------------------------------------------------------------
def para_text(p):
    out = []
    for run in p.findall(HP + 'run'):
        for t in run.findall(HP + 't'):
            out.append(''.join(t.itertext()))
    return ''.join(out)


def para_has_object(p):
    for run in p.findall(HP + 'run'):
        for ch in run:
            if ch.tag in OBJECT_TAGS:
                return True
    return False


def first_charpr(p, default='0'):
    for run in p.findall(HP + 'run'):
        if run.find(HP + 't') is not None:
            return run.get('charPrIDRef', default)
    for run in p.findall(HP + 'run'):
        return run.get('charPrIDRef', default)
    return default


def last_charpr(p, default='0'):
    cp = default
    for run in p.findall(HP + 'run'):
        if run.find(HP + 't') is not None:
            cp = run.get('charPrIDRef', cp)
    return cp


def drop_lineseg(p):
    for ls in p.findall(HP + 'linesegarray'):
        p.remove(ls)


def clear_text_runs(p):
    """문단의 글자 run만 지운다(구역 설정·컨트롤 run은 남긴다)."""
    for run in list(p.findall(HP + 'run')):
        kids = list(run)
        if all(k.tag in TEXT_RUN_CHILDREN for k in kids):
            p.remove(run)
        else:
            for k in kids:
                if k.tag in TEXT_RUN_CHILDREN:
                    run.remove(k)
    drop_lineseg(p)


def add_run(p, text, charpr):
    run = etree.SubElement(p, HP + 'run')
    run.set('charPrIDRef', str(charpr))
    if text:
        t = etree.SubElement(run, HP + 't')
        t.text = _clean(text)
    # linesegarray는 항상 마지막에 와야 하므로 run 뒤로 정리
    for ls in p.findall(HP + 'linesegarray'):
        p.remove(ls)
        p.append(ls)
    return run


def _clean(text):
    text = (text or '').replace('\t', '    ')
    return ''.join(ch for ch in text if ch == '\n' or ord(ch) >= 32)


def set_para_text(p, text, charpr=None):
    cp = charpr or first_charpr(p)
    clear_text_runs(p)
    add_run(p, text, cp)


def new_para_after(ref, text, charpr, template=None):
    """ref 문단 바로 뒤에 새 문단을 만든다(같은 부모, 같은 문단 모양)."""
    parent = ref.getparent()
    tmpl = template if template is not None else ref
    p = etree.SubElement(parent, HP + 'p')
    for k, v in tmpl.attrib.items():
        p.set(k, v)
    p.set('pageBreak', '0')
    p.set('columnBreak', '0')
    if 'id' in p.attrib:
        p.set('id', '0')
    add_run(p, text, charpr)
    parent.remove(p)
    parent.insert(parent.index(ref) + 1, p)
    return p


# ---------------------------------------------------------------------------
# 표/셀 모델
# ---------------------------------------------------------------------------
class Cell(object):
    def __init__(self, tc, table):
        self.tc = tc
        self.table = table
        a, s = tc.find(HP + 'cellAddr'), tc.find(HP + 'cellSpan')
        self.r, self.c = int(a.get('rowAddr', 0)), int(a.get('colAddr', 0))
        self.rs = int(s.get('rowSpan', 1)) if s is not None else 1
        self.cs = int(s.get('colSpan', 1)) if s is not None else 1
        self.sub = tc.find(HP + 'subList')
        self.used = False          # 이미 채웠거나 라벨로 사용함
        self.role = None
        self.slot = None
        self.label_text = None
        self.group_slot = None     # 묶음 라벨(예: 캐릭터 설정) 아래 소항목인지
        self.refresh()

    def refresh(self):
        self.paras = [p for p in self.sub if p.tag == HP + 'p'] if self.sub is not None else []
        self.lines = [para_text(p) for p in self.paras]
        self.has_nested = any(para_has_object(p) for p in self.paras)

    @property
    def text(self):
        return '\n'.join(self.lines).strip()

    @property
    def empty(self):
        return not self.text and not self.has_nested

    @property
    def has_checkbox(self):
        return '□' in self.text or '☐' in self.text

    def rows(self):
        return range(self.r, self.r + self.rs)

    def cols(self):
        return range(self.c, self.c + self.cs)

    def __repr__(self):
        return '<Cell %d,%d %s>' % (self.r, self.c, self.text[:15])


class Table(object):
    def __init__(self, el, index, prev_text=''):
        self.el = el
        self.index = index
        self.prev_text = prev_text
        self.rows = int(el.get('rowCnt', 0))
        self.cols = int(el.get('colCnt', 0))
        self.cells = []
        for tr in el.findall(HP + 'tr'):
            for tc in tr.findall(HP + 'tc'):
                self.cells.append(Cell(tc, self))
        self.cells.sort(key=lambda c: (c.r, c.c))
        self.kind = 'normal'

    def right_of(self, cell):
        col = cell.c + cell.cs
        out = [c for c in self.cells if c.c == col and c.r < cell.r + cell.rs and c.r + c.rs > cell.r]
        return sorted(out, key=lambda c: c.r)

    def left_of(self, cell):
        out = [c for c in self.cells if c.c + c.cs == cell.c and c.r < cell.r + cell.rs and c.r + c.rs > cell.r]
        return sorted(out, key=lambda c: c.r)

    def below(self, cell):
        row = cell.r + cell.rs
        out = [c for c in self.cells if c.r == row and c.c < cell.c + cell.cs and c.c + c.cs > cell.c]
        return sorted(out, key=lambda c: c.c)

    def row_cells(self, r):
        return sorted([c for c in self.cells if c.r == r], key=lambda c: c.c)


# ---------------------------------------------------------------------------
# 보고서
# ---------------------------------------------------------------------------
class FormReport(object):
    def __init__(self, name):
        self.name = name
        self.filled = []      # (라벨, 슬롯, 미리보기)
        self.nodata = []      # (라벨, 슬롯)  — 칸은 찾았지만 입력한 정보가 없음
        self.manual = []      # (라벨, 설명) — 프로그램이 판단하지 못한 칸
        self.notes = []       # 투고 안내 문장
        self.warnings = []
        self.slots = set()
        self.error = None
        self.fields_used = set()

    def add_filled(self, label, slot, lines):
        prev = ' '.join(l for l in (lines or []) if l)[:60]
        self.filled.append((_short(label), slot, prev))

    def add_nodata(self, label, slot):
        key = (_short(label), slot)
        if key not in self.nodata:
            self.nodata.append(key)

    def add_manual(self, label, why):
        key = (_short(label), why)
        if key not in self.manual:
            self.manual.append(key)

    @property
    def total(self):
        return len(self.filled) + len(self.nodata) + len(self.manual)


def _short(s):
    s = re.sub(r'\s+', ' ', (s or '').replace('\n', ' ')).strip()
    return s[:40]


# ---------------------------------------------------------------------------
# 문서
# ---------------------------------------------------------------------------
class HwpxDoc(object):
    def __init__(self, data_bytes):
        self.zin = zipfile.ZipFile(io.BytesIO(data_bytes))
        names = self.zin.namelist()
        self.section_names = sorted([n for n in names if re.match(r'Contents/section\d+\.xml$', n)],
                                    key=lambda n: int(re.findall(r'\d+', n)[-1]))
        self.sections = {}
        for n in self.section_names:
            parser = etree.XMLParser(remove_blank_text=False, huge_tree=True)
            self.sections[n] = etree.fromstring(self.zin.read(n), parser)
        self.charpr = self._read_charpr(names)
        self.tables = []
        self.body = []     # (section_root, p) 표 밖의 본문 문단
        self._collect()

    def _read_charpr(self, names):
        info = {}
        if 'Contents/header.xml' not in names:
            return info
        try:
            root = etree.fromstring(self.zin.read('Contents/header.xml'))
        except etree.XMLSyntaxError:
            return info
        for cp in root.iter(HH + 'charPr'):
            info[cp.get('id')] = {
                'color': (cp.get('textColor') or '#000000').upper(),
                'bold': cp.find(HH + 'bold') is not None,
                'height': int(cp.get('height') or 1000),
            }
        return info

    def _collect(self):
        idx = 0
        for n in self.section_names:
            root = self.sections[n]
            prev_text = ''
            for p in root.findall(HP + 'p'):
                self.body.append((root, p))
                t = para_text(p).strip()
                for run in p.findall(HP + 'run'):
                    for tbl in run.findall(HP + 'tbl'):
                        idx = self._add_table(tbl, idx, t or prev_text)
                if t:
                    prev_text = t

    def _add_table(self, tbl, idx, prev_text):
        t = Table(tbl, idx, prev_text)
        self.tables.append(t)
        idx += 1
        for cell in t.cells:
            inner_prev = ''
            for p in cell.paras:
                pt = para_text(p).strip()
                for run in p.findall(HP + 'run'):
                    for sub in run.findall(HP + 'tbl'):
                        idx = self._add_table(sub, idx, inner_prev)
                if pt:
                    inner_prev = pt
        return idx

    def is_plain(self, charpr_id):
        info = self.charpr.get(str(charpr_id))
        if not info:
            return True
        c = info['color']
        dark = c in ('#000000', '#000', 'NONE') or c.startswith('#0000') or c.startswith('#1') or c == '#000000'
        return dark and not info['bold']

    def plain_charpr_for(self, cell):
        """안내문을 지우고 쓸 때 쓸 글자 모양: 같은 표의 빈 칸 → 셀 자신 → 문서에서 흔한 검은 글자"""
        cnt = Counter()
        for c in cell.table.cells:
            if c.empty and c.paras:
                cnt[first_charpr(c.paras[0])] += 1
        for cp, _ in cnt.most_common():
            if self.is_plain(cp):
                return cp
        own = first_charpr(cell.paras[0]) if cell.paras else '0'
        if self.is_plain(own):
            return own
        return self.doc_plain_charpr(own)

    def doc_plain_charpr(self, fallback='0'):
        cnt = Counter()
        for root in self.sections.values():
            for run in root.iter(HP + 'run'):
                if run.find(HP + 't') is not None:
                    cnt[run.get('charPrIDRef')] += 1
        for cp, _ in cnt.most_common():
            if self.is_plain(cp):
                return cp
        return fallback

    def plain_para_template(self):
        """본문용 문단 모양: 표 밖 본문에서 제목이 아닌(빈 줄 또는 긴 문장) 문단 중 가장 흔한 모양"""
        cnt = Counter()
        rep = {}
        for _, p in self.body:
            if para_has_object(p) or p.find('.//' + HP + 'secPr') is not None:
                continue
            t = para_text(p).strip()
            if t and (len(t) < 25 or Filler.HEADING_RX.match(t)):
                continue
            key = (p.get('paraPrIDRef'), p.get('styleIDRef'))
            cnt[key] += 1
            rep.setdefault(key, p)
        if not cnt:
            return None
        return rep[cnt.most_common(1)[0][0]]

    def to_bytes(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as zout:
            infos = self.zin.infolist()
            infos.sort(key=lambda i: 0 if i.filename == 'mimetype' else 1)
            for info in infos:
                if info.filename in self.sections:
                    data = XML_DECL + etree.tostring(self.sections[info.filename], encoding='UTF-8')
                else:
                    data = self.zin.read(info.filename)
                zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                zi.external_attr = info.external_attr
                zi.compress_type = zipfile.ZIP_STORED if info.filename == 'mimetype' else info.compress_type
                zout.writestr(zi, data)
        return out.getvalue()


# ---------------------------------------------------------------------------
# 채우기
# ---------------------------------------------------------------------------
class Filler(object):
    def __init__(self, doc, data, name=''):
        self.doc = doc
        self.data = data
        self.rep = FormReport(name)
        self.res = None

    # ---- 쓰기 ----
    def write_cell(self, cell, lines, keep_head=None):
        """셀 내용을 lines로 바꾼다. keep_head: 맨 앞에 남길 문단 수(예: '<핵심 설정>')"""
        if not cell.paras or cell.has_nested:
            return False
        guide = R.is_guide_text(cell.lines) or bool(cell.text)
        tmpl = cell.paras[0]
        cp = self.doc.plain_charpr_for(cell) if guide else first_charpr(tmpl)
        keep = cell.paras[:keep_head] if keep_head else []
        for p in cell.paras:
            if p not in keep:
                cell.sub.remove(p)
        if keep:
            tmpl = keep[-1]
            for p in keep:
                drop_lineseg(p)
        ref = keep[-1] if keep else None
        for i, line in enumerate(lines or ['']):
            if ref is None:
                p = etree.SubElement(cell.sub, HP + 'p')
                for k, v in tmpl.attrib.items():
                    p.set(k, v)
                p.set('pageBreak', '0')
                p.set('columnBreak', '0')
                add_run(p, line, cp)
                ref = p
            else:
                ref = new_para_after(ref, line, cp, template=tmpl if keep else ref)
        cell.used = True
        cell.role = 'written'
        cell.refresh()
        return True

    def fill(self, cell, slot, label, hint=''):
        lines = self.res.value(slot, hint)
        if lines:
            if self.write_cell(cell, lines):
                self.rep.add_filled(label, slot, lines)
                return True
        else:
            # 넣을 내용이 없는데 칸에 출판사 '예시' 글이 있으면 지운다(예시가 그대로 제출되는 사고 방지)
            first = next((l for l in cell.lines if l.strip()), '')
            if R.is_example_line(first) or first.strip() in ('예)', '(예)', '예시)'):
                self.write_cell(cell, [''])
            self.rep.add_nodata(label, slot)
        cell.used = True
        return False

    # ---- 판정 ----
    def fillable(self, cell):
        if cell.used or cell.has_nested or cell.has_checkbox:
            return False
        if cell.slot and not R.is_guide_text(cell.lines):
            return False
        return cell.empty or R.is_guide_text(cell.lines)

    def subform_lines(self, cell):
        """셀 안의 '라벨 : ' 형식 줄 중 아는 항목이 있으면 그 목록을 돌려준다."""
        out = []
        for p, line in zip(cell.paras, cell.lines):
            pc = R.parse_colon_line(line)
            if not pc:
                continue
            head, rest = pc
            slot = self.colon_slot(head, cell)
            if slot:
                out.append((p, head, rest, slot))
        return out

    def colon_slot(self, head, cell=None):
        slot = R.match_slot(head)
        group = cell.group_slot if cell is not None else None
        n = R.norm(head)
        inner = ' '.join(R.paren_inner(n))
        if slot is None and inner:
            if re.search(r'남주|공', inner) and not re.search(r'여주|수', inner):
                slot = 'char_gong'
            elif re.search(r'여주|수', inner):
                slot = 'char_su'
            elif '나이' in inner and R.strip_paren(n) in ('주인공', '조연'):
                slot = 'char_lead' if R.strip_paren(n) == '주인공' else 'char_sup_next'
        if slot == 'char_sup_group' and '나이' in inner:
            slot = 'char_sup_next'
        if slot == 'notes' and (group or '').startswith(('chars', 'char')):
            slot = 'char_other'
        return slot

    # ---- 메인 ----
    def run(self):
        tables = self.doc.tables
        # 1) 라벨 읽기
        for t in tables:
            self.classify_table(t)
        form_slots = set()
        for t in tables:
            for c in t.cells:
                if c.slot:
                    form_slots.add(c.slot)
                for line in c.lines:
                    pc = R.parse_colon_line(line)
                    if pc:
                        s = R.match_slot(pc[0])
                        if s:
                            form_slots.add(s)
        for _, p in self.doc.body:
            txt = para_text(p)
            pc = R.parse_colon_line(txt)
            s = R.match_slot(pc[0]) if pc else R.match_slot(txt)
            if s:
                form_slots.add(s)
        self.rep.slots = form_slots
        self.res = Resolver(self.data, form_slots)

        # 2) 특수 표
        for t in tables:
            if t.kind == 'card':
                self.fill_card(t)
        for t in tables:
            self.fill_char_grid(t)
        # 3) 체크박스, O/X 질문
        for t in tables:
            self.fill_checkboxes(t)
            self.fill_ox(t)
        # 4) 일반 라벨 → 옆/아래 칸
        for t in tables:
            if t.kind == 'card':
                continue
            if t.kind == 'episode':
                continue
            for cell in t.cells:
                self.fill_label(t, cell)
        # 5) '라벨 :' 형식 줄
        for t in tables:
            for cell in t.cells:
                if cell.role in ('label', 'written', 'group') or cell.has_nested:
                    continue
                self.fill_colon_lines(cell.paras, cell)
        self.fill_colon_lines([p for _, p in self.doc.body], None)
        # 6) 본문 제목(■줄거리 등) 아래에 내용 넣기
        self.fill_headings()
        # 7) 제목 자리표시([작품명])
        self.fill_title_placeholders()
        # 8) 못 채운 칸·안내문 정리
        self.collect_manual(tables)
        self.collect_notes()
        self.rep.warnings += sorted(set(self.res.warnings))
        self.rep.fields_used = set(self.res.accessed)
        return self.rep

    # ---- 1) 라벨 분류 ----
    def classify_table(self, t):
        card_hits = set()
        for cell in t.cells:
            if cell.has_nested:
                continue
            lines = [l for l in cell.lines if l.strip()]
            if not lines:
                continue
            slot, label = R.match_label_lines(lines)
            if slot and R.is_guide_text(lines) and not R.match_slot(lines[0]):
                slot = None
            if slot:
                cell.slot, cell.label_text = slot, label
            cs = None
            for cand in R.label_candidates(lines):
                cs = R.match_card(cand)
                if cs:
                    break
            if cs:
                card_hits.add(cs)
        if any(re.search(r'에피소드\d|^\d+권\(', R.norm(c.text)) for c in t.cells):
            t.kind = 'episode'
            for c in t.cells:
                c.slot = None
                c.used = True
            self.rep.add_manual('에피소드 진행안 표', '선택 항목 — 필요하면 직접 작성')
            return
        core = card_hits & {'card_gender', 'card_age', 'card_appearance', 'card_personality'}
        if len(card_hits) >= 3 and core and len(t.cells) <= 20:
            t.kind = 'card'

    # ---- 2) 등장인물 카드 ----
    def fill_card(self, t):
        prev = R.norm(t.prev_text or '')
        res = self.res
        res.accessed.add('characters')
        ch = None
        if re.search(r'메인수|\(수\)|수$|여주|여자주인공', prev):
            ch = res.by_pos('수')
        elif re.search(r'메인공|\(공\)|공$|남주|남자주인공', prev):
            ch = res.by_pos('공')
        if ch is None or id(ch) in res._used_chars:
            ch = res.next_char(res.leads()) or res.next_char(res.chars)
        else:
            res.take(ch)
        label = '인물 카드' + (' (%s)' % t.prev_text.strip(' []()') if t.prev_text else '')
        for cell in t.cells:
            if cell.used or not cell.lines:
                continue
            slot = None
            for cand in R.label_candidates(cell.lines):
                slot = R.match_card(cand)
                if slot:
                    break
            if not slot:
                continue
            cell.used, cell.role = True, 'label'
            rights = [c for c in t.right_of(cell) if not c.used]
            target = next((c for c in rights if c.empty or R.is_guide_text(c.lines)), None)
            if target is None:
                continue
            if ch is None:
                self.rep.add_nodata(label + ' - ' + cell.text, slot)
                target.used = True
                continue
            lines = self.card_value(ch, slot)
            if lines:
                self.write_cell(target, lines)
                self.rep.add_filled(label + ' - ' + R.norm(cell.text), slot, lines)
            else:
                self.rep.add_nodata(label + ' - ' + cell.text, slot)
                target.used = True

    def card_value(self, ch, slot):
        L = Resolver.lines
        if slot == 'card_name':
            name = ch.get('name', '').strip()
            pos = ch.get('pos') or ch.get('kind') or ''
            return [name + (' (%s)' % pos if pos else '')]
        if slot == 'card_gender':
            return L(ch.get('gender'))
        if slot == 'card_age':
            return L(ch.get('age'))
        if slot == 'card_appearance':
            return L(ch.get('appearance')) or None
        if slot == 'card_personality':
            out = L(ch.get('personality')) or []
            if ch.get('intro'):
                out = (out + ['']) if out else out
                out += L(ch.get('intro'))
            return out or None
        if slot == 'card_extra':
            out = L(ch.get('extra')) or []
            if ch.get('backstory'):
                out += ([''] if out else []) + L(ch.get('backstory'))
            return out or None
        return None

    # ---- 2-2) 인물 표(헤더 줄 + 여러 줄), 비하인드 표 ----
    def fill_char_grid(self, t):
        for cell in t.cells:
            n = R.norm(cell.text)
            if cell.used or not n:
                continue
            if n.startswith('이름/나이') or n.startswith('이름/성별'):
                self._grid(t, cell, kind='profile')
                return
            if '비하인드' in n:
                self._grid(t, cell, kind='backstory')
                return

    def _grid(self, t, head, kind):
        res = self.res
        res.accessed.add('characters')
        if kind == 'profile':
            header_row = head.r
            headers = t.row_cells(header_row)
            for h in headers:
                h.used, h.role = True, 'label'
            col_map = {}
            for h in headers:
                n = R.norm(h.text)
                if n.startswith('이름'):
                    col_map[h.c] = 'head'
                elif '외모' in n or '성격' in n:
                    col_map[h.c] = 'look'
                elif '습관' in n or '말투' in n or '트라우마' in n:
                    col_map[h.c] = 'extra'
                elif '목표' in n or '욕망' in n or '결핍' in n:
                    col_map[h.c] = 'goal'
                else:
                    col_map[h.c] = 'intro'
            rows = sorted({c.r for c in t.cells if c.r > header_row})
            chars = list(res.chars)
            label = '주요 등장인물 표'
            for i, r in enumerate(rows):
                ch = chars[i] if i < len(chars) else None
                for c in t.row_cells(r):
                    what = col_map.get(c.c)
                    if what is None:
                        continue
                    if ch is None:
                        if c.text:
                            self.write_cell(c, [''])
                        c.used = True
                        continue
                    if what == 'head':
                        bits = [x for x in (ch.get('age'), ch.get('gender')) if (x or '').strip()]
                        lines = [ch.get('name', '')] + (['(%s)' % ', '.join(bits)] if bits else [])
                    elif what == 'look':
                        lines = (Resolver.lines(ch.get('appearance')) or []) + (Resolver.lines(ch.get('personality')) or [])
                        if not lines:
                            lines = Resolver.lines(ch.get('intro')) or ['']
                    elif what == 'extra':
                        lines = Resolver.lines(ch.get('extra')) or ['']
                    elif what == 'goal':
                        lines = Resolver.lines(ch.get('goal')) or ['']
                    else:
                        lines = Resolver.lines(ch.get('intro')) or ['']
                    self.write_cell(c, lines)
                if ch is not None:
                    self.rep.add_filled(label, 'chars_all', [ch.get('name', '')])
            if len(chars) > len(rows):
                self.rep.warnings.append('등장인물 표 칸이 모자라 %d명은 넣지 못했어요(직접 줄 추가 필요)' % (len(chars) - len(rows)))
            if not chars:
                self.rep.add_nodata(label, 'chars_all')
            for c in t.cells:
                if c.r > header_row:
                    c.used = True
            # 같은 표의 '주요 등장인물' 안내 라벨이 전체 인물을 또 넣지 않도록
            for c in t.cells:
                if c.slot == 'chars_all' and c.r < header_row:
                    c.role = 'label'
                    c.used = True
                    for x in t.right_of(c):
                        x.used = True
        else:  # backstory
            head.used, head.role = True, 'label'
            for x in t.right_of(head):
                x.used = True
            rows = sorted({c.r for c in t.cells if c.r > head.r})
            chars = [c for c in res.chars if (c.get('backstory') or '').strip()] or []
            for i, r in enumerate(rows):
                cells = t.row_cells(r)
                ch = chars[i] if i < len(chars) else None
                if len(cells) >= 2:
                    if ch:
                        self.write_cell(cells[0], [ch.get('name', '')])
                        self.write_cell(cells[1], Resolver.lines(ch.get('backstory')))
                        self.rep.add_filled('비하인드 스토리', 'chars_all', [ch.get('name', '')])
                    else:
                        for c in cells:
                            if c.text:
                                self.write_cell(c, [''])
                for c in cells:
                    c.used = True
            if not chars:
                self.rep.add_nodata('메인 캐릭터 비하인드 스토리', 'char_backstory')

    # ---- 3) 체크박스 ----
    def fill_checkboxes(self, t):
        for cell in t.cells:
            if not cell.has_checkbox or cell.used or cell.has_nested:
                continue
            slot, label = self.context_slot(t, cell)
            cell.used = True
            if slot == 'skip':
                continue
            if not slot:
                self.rep.add_manual(cell.text, '체크 항목(직접 표시)')
                continue
            value = ' '.join(self.res.value(slot) or [])
            if not value:
                self.rep.add_nodata(label or cell.text, slot)
                continue
            changed = False
            for p, line in zip(cell.paras, cell.lines):
                new = self.check_options(line, value)
                if new != line:
                    set_para_text(p, new)
                    changed = True
            cell.refresh()
            if changed:
                cell.role = 'written'
                self.rep.add_filled(label or cell.text, slot, [value])
            else:
                self.rep.add_manual(label or cell.text, '선택지에 맞는 항목이 없어 직접 체크 필요 (입력값: %s)' % value[:20])

    def context_slot(self, t, cell):
        lefts = t.left_of(cell)
        hops = 0
        while lefts and hops < 3:
            lc = lefts[0]
            n = R.norm(lc.text)
            if n in ('웹툰', '장르문학'):
                return 'skip', None
            if lc.slot:
                return lc.slot, lc.text
            lefts = t.left_of(lc)
            hops += 1
        return None, None

    # 체크박스 선택지와 입력값의 같은 말
    OPTION_SYNONYMS = {'로맨스판타지': ['로판'], '로판': ['로맨스판타지'], '현대로맨스': ['현로', '현대물'],
                       '현로': ['현대로맨스'], 'o': ['있음', '예', '유', '해당'], 'x': ['없음', '아니오', '무', '해당없음'],
                       '단행본': ['단행'], '연재': ['연재'], '전체이용가': ['전체', '전연령'], '15세이용가': ['15세', '15금'],
                       '19세이용가': ['19세', '19금', '성인']}

    @classmethod
    def check_options(cls, line, value):  # noqa: C901
        if '□' not in line and '☐' not in line:
            return line
        val_tokens = [R.norm(x) for x in re.split(r'[,/·\s()]+', value) if x.strip()]
        joined = R.norm(value)
        for t in list(val_tokens) + [joined]:
            val_tokens += [R.norm(s) for s in cls.OPTION_SYNONYMS.get(t, [])]
        val_norm = R.norm(value)
        parts = re.split(r'([□☐])', line)
        # parts: [앞, □, 옵션1, □, 옵션2 ...]
        opts = []
        for i in range(1, len(parts), 2):
            opt = parts[i + 1] if i + 1 < len(parts) else ''
            opts.append((i, opt))
        chosen = set()
        for i, opt in opts:
            on = R.norm(opt)
            if not on:
                continue
            on_core = re.sub(r'(이용가|세이용가)$', '', on)
            for tok in val_tokens + [val_norm]:
                if not tok:
                    continue
                tok_core = re.sub(r'(이용가|세이용가)$', '', tok)
                if on == tok or on_core == tok_core or (tok_core and tok_core == on_core.split('또는')[0]):
                    chosen.add(i)
                elif len(tok_core) >= 2 and ('또는' in on and tok_core in on.split('또는')):
                    chosen.add(i)
        # 정확히 맞는 선택지가 없는 낱말은 부분 일치(예: '카카오페이지' ↔ '카카오', 'BL' ↔ 'BL 또는 GL')로 하나씩
        for tok in val_tokens:
            if len(tok) < 2 or any(R.norm(parts[i + 1] if i + 1 < len(parts) else '') == tok for i in chosen):
                continue
            best, best_len = None, 0
            for i, opt in opts:
                on = R.norm(opt)
                if on and (tok in on or on in tok):
                    l = min(len(tok), len(on))
                    if l > best_len:
                        best, best_len = i, l
            if best is not None and best_len >= 2:
                chosen.add(best)
        for i in chosen:
            parts[i] = '■'
        return ''.join(parts)

    # ---- 3-2) O/X 확인 질문 ----
    OX_PATTERNS = [
        ('ox_parody', r'패러디'),
        ('ox_incest', r'근친'),
        ('ox_minor', r'미성년자?의?\s*성애|미성년.*성적'),
        ('ox_ethics', r'강제적\s*관계|범죄\s*미화|윤리'),
        ('ox_rps', r'RPS|리네이밍'),
        ('ox_published', r'출간작|유료\s*연재'),
    ]

    def fill_ox(self, t):
        for cell in t.cells:
            if cell.used or cell.has_nested or '(O/X)' not in cell.text.replace(' ', ''):
                continue
            key = None
            for k, pat in self.OX_PATTERNS:
                if re.search(pat, cell.lines[0] if cell.lines else ''):
                    key = k
                    break
            if key is None:
                for k, pat in self.OX_PATTERNS:
                    if re.search(pat, cell.text):
                        key = k
                        break
            cell.used = True
            if key is None:
                self.rep.add_manual(cell.text, 'O/X 질문(직접 답변)')
                continue
            ans = self.res.ox(key)
            if not ans:
                self.rep.add_nodata(cell.lines[0], key)
                continue
            for p, line in zip(cell.paras, cell.lines):
                if '(O/X)' in line.replace(' ', ''):
                    set_para_text(p, re.sub(r'\(\s*O\s*/\s*X\s*\)', '(O/X)  ▶ %s' % ans, line, count=1))
                    break
            if key == 'ox_incest' and ans == 'O' and self.res.g('incest_relation'):
                for p, line in zip(cell.paras, cell.lines):
                    if line.strip() in (':', '：'):
                        set_para_text(p, ': ' + self.res.g('incest_relation'))
                        break
            cell.refresh()
            cell.role = 'written'
            self.rep.add_filled(cell.lines[0], key, [ans])

    # ---- 4) 일반 라벨 ----
    def fill_label(self, t, cell):
        if cell.slot is None or cell.used or cell.has_nested or cell.slot.startswith('card_'):
            return
        slot = cell.slot
        label = cell.label_text or cell.text
        rights = t.right_of(cell)
        right_labels = [c for c in rights if c.slot and not R.is_guide_text(c.lines)]
        # 묶음 라벨(여러 줄에 걸친 '연락처', '캐릭터 설정', '시놉시스' 등)
        if cell.rs > 1 and right_labels:
            cell.role, cell.used = 'group', True
            for c in rights:
                c.group_slot = slot
                if c.slot == 'notes' and slot in ('chars_all', 'char_lead_group', 'char_sup_group'):
                    c.slot = 'char_other'
            return
        if self.subform_lines_any(rights):
            cell.role, cell.used = 'label', True
            for c in rights:
                c.group_slot = slot
            return
        # 등장인물 여러 줄(주연/조연/주요 캐릭터)
        if slot in ('chars_all', 'char_lead_group', 'char_sup_group') and len(rights) > 1 \
                and not right_labels:
            cell.role, cell.used = 'label', True
            self.fill_char_rows(t, cell, rights, slot)
            return
        # 기승전결 단계가 두 줄(핵심 설정 + 세부) — 나인스펙트럼형
        if slot in R.STAGE_SLOTS and len(rights) > 1:
            cell.role, cell.used = 'label', True
            self.fill_stage_rows(cell, rights, slot, label)
            return
        if rights and all(c.used for c in rights):
            return
        target = None
        r_cands = [c for c in rights if not c.used]
        r0 = r_cands[0] if r_cands else None
        if r0 is not None and self.fillable(r0):
            target = r0
            if R.is_guide_text(r0.lines) and r0.text:
                wide = [b for b in t.below(cell) if b.c <= cell.c and b.c + b.cs >= r0.c + r0.cs]
                if wide and self.fillable(wide[0]) and not wide[0].slot:
                    target = wide[0]
                    r0.used = True
        elif r0 is None or (r0.slot and not R.is_guide_text(r0.lines)):
            # 오른쪽이 없거나 또 라벨 → 아래 칸(같은 너비)
            belows = t.below(cell)
            if len(belows) == 1 and self.fillable(belows[0]) and belows[0].c == cell.c \
                    and belows[0].cs >= cell.cs:
                target = belows[0]
        if target is None:
            if r0 is not None and not r0.used and not r0.slot and not r0.has_checkbox and r0.text \
                    and not R.is_guide_text(r0.lines):
                # 오른쪽 칸에 이미 고정 문구가 있음(정책 안내 등) → 손대지 않음
                return
            return
        cell.role, cell.used = 'label', True
        hint = ' '.join([cell.text] + (target.lines if target is not None else []) +
                        [c.text for c in rights[1:2] if not c.slot])
        self.fill(target, slot, label, hint)

    def subform_lines_any(self, rights):
        for c in rights:
            if not c.used and not c.has_nested and len(self.subform_lines(c)) >= 1 and len(c.paras) >= 2:
                return True
        return False

    def fill_char_rows(self, t, cell, rights, slot):
        res = self.res
        pool = res.leads() if slot == 'char_lead_group' else res.supports() if slot == 'char_sup_group' else res.chars
        label = cell.label_text or cell.text
        any_filled = False
        for rc in rights:
            row_cells = [x for x in t.row_cells(rc.r) if x.c >= rc.c]
            ch = res.next_char(pool)
            if ch is None:
                for x in row_cells:
                    x.used = True
                continue
            desc = res.char_desc_lines(ch)
            if len(row_cells) >= 2 and self.fillable(row_cells[0]):
                self.write_cell(row_cells[0], [res.char_head(ch)])
                if self.fillable(row_cells[1]):
                    self.write_cell(row_cells[1], desc or [''])
            elif self.fillable(rc):
                self.write_cell(rc, res.char_block(ch))
            any_filled = True
            self.rep.add_filled(label, slot, [ch.get('name', '')])
        if not any_filled:
            self.rep.add_nodata(label, slot)
        left = [c for c in pool if id(c) not in res._used_chars]
        if left:
            self.rep.warnings.append('「%s」 칸이 모자라 %s 은(는) 넣지 못했어요(필요하면 줄 추가)' % (R.norm(label), ', '.join(c.get('name', '') for c in left)))
        for rc in rights:
            for x in t.row_cells(rc.r):
                if x.c >= rc.c:
                    x.used = True

    def fill_stage_rows(self, cell, rights, slot, label):
        lines = self.res.value(slot)
        first, rest = rights[0], rights[1:]
        if lines:
            keep = 1 if first.lines and re.match(r'^\s*<.*>\s*$', first.lines[0] or '') else None
            self.write_cell(first, lines, keep_head=keep)
            self.rep.add_filled(label, slot, lines)
        else:
            self.rep.add_nodata(label, slot)
            first.used = True
        for c in rest:
            # 예시 문장(1. ○○○)만 지우고 번호 틀은 남긴다
            if c.text and any(re.match(r'^\s*\d+\.\s*\S', l) for l in c.lines):
                nums = [re.match(r'^\s*(\d+\.)', l).group(1) for l in c.lines if re.match(r'^\s*\d+\.', l)]
                self.write_cell(c, nums or [''])
            c.used = True

    # ---- 5) '라벨 :' 줄 ----
    def fill_colon_lines(self, paras, cell):
        filled_any = False
        guide_paras = []
        for p in list(paras):
            if para_has_object(p):
                continue
            line = para_text(p)
            pc = R.parse_colon_line(line)
            if not pc:
                if cell is not None and R.is_guide_line(line):
                    guide_paras.append(p)
                continue
            head, rest = pc
            numbered = bool(R.NUMBERED.match(head))
            slot = self.colon_slot(head, cell)
            if not slot or not R.rest_is_fillable(rest, numbered):
                continue
            if slot == 'char_sup_next':
                ch = self.res.next_char(self.res.supports())
                lines = self.res.char_desc_lines(ch) if ch else None
            elif slot.startswith('char_') and slot not in ('char_lead_group', 'char_sup_group', 'char_other'):
                ch = self.res.char_for_slot(slot) if slot != 'char_lead' else self.res.next_char(self.res.leads())
                lines = self.res.char_desc_lines(ch) if ch else None
            else:
                ch = None
                lines = self.res.value(slot, line)
            if not lines:
                self.rep.add_nodata(head, slot)
                continue
            new_head = self.colon_head(head, ch)
            sep = ' : ' if re.search(r'\s[:：]', line) else ': '
            if ch is not None and new_head == head.rstrip():
                lines = [self.res.char_head(ch) + (' - ' + lines[0] if lines and lines[0] else '')] + lines[1:]
            elif ch is not None and not lines:
                lines = ['']
            cp_label = first_charpr(p)
            cp_val = last_charpr(p)
            clear_text_runs(p)
            add_run(p, new_head.rstrip() + sep, cp_label)
            add_run(p, lines[0], cp_val)
            ref = p
            for extra in lines[1:]:
                ref = new_para_after(ref, extra, cp_val)
            self.rep.add_filled(head, slot if slot != 'char_sup_next' else 'char_sup_group', lines)
            filled_any = True
        if cell is not None and filled_any:
            for gp in guide_paras:
                if gp.getparent() is not None:
                    gp.getparent().remove(gp)
            cell.used = True
            cell.role = 'written'
            cell.refresh()

    def colon_head(self, head, ch):
        if ch is None:
            return head
        n = R.norm(head)
        name = ch.get('name', '').strip()
        m = re.match(r'^(\s*)([^(]+?)\s*\(([^)]*)\)\s*$', head)
        if m:
            base, inner = m.group(2), m.group(3)
            if '나이' in inner:
                age = (ch.get('age') or '').strip()
                return '%s%s(%s)' % (m.group(1), name, age or '나이')
            if R.match_slot(R.strip_paren(n)) is None:
                # '이몽룡(남주)' 같은 예시 이름 → 실제 이름
                return '%s%s(%s)' % (m.group(1), name, inner)
        return head

    # ---- 6) 본문 제목 아래 ----
    HEADING_RX = re.compile('^\\s*(?:■|▶|►|◆|◇|●|○|\\[|<|【|[-]|\\d{1,2}\\s*[\\.\\)])')
    # 본문 제목 아래에 넣어도 되는 항목(문서 제목·안내 문구에 잘못 넣지 않도록 한정)
    HEADING_SLOTS = {'chars_all', 'intro', 'intro_selling', 'intro_chars', 'intro_intent', 'intent', 'intent_selling',
                     'synopsis', 'summary', 'logline', 'bio', 'career', 'keywords', 'setting', 'selling', 'target',
                     'when_to_read', 'twist'}
    TABLE_ONLY_SLOTS = {'notes', 'reference', 'awards'}

    def fill_headings(self):
        for root, p in list(self.doc.body):
            if p.getparent() is None:
                continue
            text = para_text(p).strip()
            if not text or R.parse_colon_line(text):
                continue
            if para_has_object(p):
                slot = R.match_slot(text)
                if slot in self.HEADING_SLOTS or slot in self.TABLE_ONLY_SLOTS:
                    for run in p.findall(HP + 'run'):
                        for tb in run.findall(HP + 'tbl'):
                            self._fill_single_cell_table(tb, slot, text)
                continue
            marker = bool(self.HEADING_RX.match(text))
            if not marker and len(text) > 20:
                continue
            slot = R.match_slot(text) or R.match_slot(re.sub(r'\(.*?\)|\[.*?\]$', '', text))
            if slot is None or (slot not in self.HEADING_SLOTS and slot not in self.TABLE_ONLY_SLOTS):
                continue
            self.fill_after_heading(root, p, slot, text, marker)

    def fill_after_heading(self, root, head, slot, text, marker=True):
        parent = head.getparent()
        siblings = [x for x in parent if x.tag == HP + 'p']
        idx = siblings.index(head)
        following = siblings[idx + 1:]
        # 뒤에 오는 1x1 표(이플북스형). 다른 표가 곧바로 나오면 그 표가 이미 칸을 갖고 있으므로 건너뜀
        texts_seen = 0
        for q in following[:6]:
            qt = para_text(q).strip()
            tbls = [tb for run in q.findall(HP + 'run') for tb in run.findall(HP + 'tbl')]
            if tbls:
                tb = tbls[0]
                if texts_seen == 0:
                    self._fill_single_cell_table(tb, slot, text)
                return
            if qt:
                if self.HEADING_RX.match(qt) and not qt.startswith(('-', '*', '※')) and texts_seen == 0 \
                        and len(qt) <= 20:
                    texts_seen += 1   # '[ 기승전결 ]' 같은 소제목 뒤의 표도 확인
                    continue
                break
        if not marker or slot in self.TABLE_ONLY_SLOTS:
            return
        lines = self.res.value(slot, text)
        if not lines:
            self.rep.add_nodata(text, slot)
            return
        # 바로 뒤 안내('-…', '*…') 건너뛰고, 자리표시/예시/빈 줄을 찾는다
        insert_after = head
        j = 0
        while j < len(following):
            q = following[j]
            qt = para_text(q).strip()
            if para_has_object(q):
                break
            if qt.startswith(('-', '*', '※')) and len(qt) > 3 and '여기에' not in qt:
                insert_after = q
                j += 1
                continue
            break
        rest = following[j:]
        cp = self.doc.doc_plain_charpr(first_charpr(head))
        if rest:
            q = rest[0]
            qt = para_text(q).strip()
            # 빈 줄 뒤에 자리표시·예시·하위 항목이 오면 그것을 기준으로 판단
            if not qt and not para_has_object(q):
                for z in rest[1:4]:
                    zt = para_text(z).strip()
                    if para_has_object(z):
                        break
                    if not zt:
                        continue
                    pcz = R.parse_colon_line(zt)
                    if ('여기에' in zt and ('작성' in zt or '입력' in zt)) or R.is_example_line(zt) or \
                            (pcz and R.match_slot(pcz[0])):
                        q, qt = z, zt
                        rest = rest[rest.index(z):]
                    break
            if '여기에' in qt and ('작성' in qt or '입력' in qt) and not para_has_object(q):
                cp = first_charpr(q) if self.doc.is_plain(first_charpr(q)) else cp
                self._replace_para_with_lines(q, lines, cp)
                self.rep.add_filled(text, slot, lines)
                return
            if R.is_example_line(qt) and not para_has_object(q):
                # [ex … ] 예시 묶음 전체를 바꾼다
                block = [q]
                if qt.startswith('[') and not qt.endswith(']'):
                    for z in rest[1:]:
                        if para_has_object(z):
                            break
                        block.append(z)
                        if para_text(z).strip().endswith(']'):
                            break
                cp = self.doc.doc_plain_charpr(cp)
                for z in block[1:]:
                    parent.remove(z)
                self._replace_para_with_lines(q, lines, cp)
                self.rep.add_filled(text, slot, lines)
                return
            # 이미 뒤에 '기:' 같은 하위 항목이 있으면 제목은 건너뛴다
            pc = R.parse_colon_line(qt)
            if pc and R.match_slot(pc[0]):
                return
            if not qt and not para_has_object(q):
                cp2 = first_charpr(q)
                if self.doc.is_plain(cp2):
                    cp = cp2
                self._replace_para_with_lines(q, lines, cp)
                self.rep.add_filled(text, slot, lines)
                return
        ref = insert_after
        tmpl = self.doc.plain_para_template()
        for line in lines:
            ref = new_para_after(ref, line, cp, template=tmpl)
        self.rep.add_filled(text, slot, lines)

    def _fill_single_cell_table(self, tb, slot, text):
        if tb.get('rowCnt') != '1' or tb.get('colCnt') != '1':
            return
        table = next((t for t in self.doc.tables if t.el is tb), None)
        if not table or not table.cells:
            return
        c = table.cells[0]
        if c.used or c.has_nested or self.subform_lines(c):
            return
        if c.text and not R.is_guide_text(c.lines) and '(링크)' not in c.text:
            return
        self.fill(c, slot, text, ' '.join(c.lines))

    def _replace_para_with_lines(self, p, lines, cp):
        set_para_text(p, lines[0], cp)
        ref = p
        for line in lines[1:]:
            ref = new_para_after(ref, line, cp)

    # ---- 7) [작품명] 자리표시 ----
    def fill_title_placeholders(self):
        title = self.res.g('title')
        if not title:
            return
        for _, p in self.doc.body:
            t = para_text(p)
            if '[작품명]' in t or '[제목]' in t:
                set_para_text(p, t.replace('[작품명]', '[%s]' % title).replace('[제목]', '[%s]' % title))
                self.rep.add_filled('[작품명] 자리', 'title', [title])
            elif re.match(r'^\s*<\s*투고\s*>\s*작품명\s*_\s*작가명\s*$', t):
                # 우신출판사: 「<투고> 작품명_작가명」 제목 줄
                pen = self.res.g('pen') or '작가명'
                set_para_text(p, re.sub(r'작품명\s*_\s*작가명', '%s_%s' % (title, pen), t))
                self.rep.add_filled('<투고> 작품명_작가명 자리', 'title', [title])

    # ---- 8) 정리 ----
    def collect_manual(self, tables):
        for t in tables:
            if t.kind == 'card':
                continue
            for cell in t.cells:
                if cell.used or cell.has_nested or cell.role:
                    continue
                txt = cell.text
                n = R.norm(txt)
                if not n or len(n) > 24 or R.is_guide_text(cell.lines) or cell.slot:
                    continue
                if cell.cs >= t.cols and t.cols > 1:
                    continue
                if re.search(r'에피소드|^\d+권', n):
                    self.rep.add_manual(txt, '에피소드 진행안(선택 항목) — 직접 작성')
                    continue
                rights = [c for c in t.right_of(cell) if not c.used]
                belows = [c for c in t.below(cell) if not c.used and c.cs >= cell.cs]
                tgt = rights[0] if rights else (belows[0] if len(belows) == 1 else None)
                if tgt is None or tgt.slot or tgt.has_nested:
                    continue
                if tgt.empty or R.is_guide_text(tgt.lines) or R.is_example_line(tgt.lines[0] if tgt.lines else ''):
                    self.rep.add_manual(txt, '프로그램이 모르는 항목 — 직접 작성')
        for t in tables:
            for cell in t.cells:
                if cell.slot and not cell.used and cell.role is None and not cell.has_nested \
                        and not cell.slot.startswith('card_'):
                    rights = t.right_of(cell)
                    if rights and not rights[0].used and rights[0].text and not rights[0].slot \
                            and not R.is_guide_text(rights[0].lines) and not rights[0].has_checkbox:
                        continue
                    if not rights and not t.below(cell):
                        continue

    def collect_notes(self):
        seen = set()
        cands = [para_text(p) for _, p in self.doc.body]
        for t in self.doc.tables:
            for c in t.cells:
                if not c.used and not c.slot:
                    cands += c.lines
        for line in cands:
            s = line.strip()
            if not s or len(s) > 120 or s in seen:
                continue
            if R.REQ_PATTERNS.search(s) and not R.match_slot(s):
                if re.match(r'^[\(\[]?\s*(원고|본문)\s*[\)\]]?$', s):
                    continue
                seen.add(s)
                self.rep.notes.append(s)
        self.rep.notes = self.rep.notes[:8]


def fill_hwpx(data_bytes, project, name='', dry_run=False):
    doc = HwpxDoc(data_bytes)
    filler = Filler(doc, project, name)
    rep = filler.run()
    if dry_run:
        return None, rep
    return doc.to_bytes(), rep


def describe_slot(slot):
    return SLOT_NAMES.get(slot, slot)
