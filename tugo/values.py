# -*- coding: utf-8 -*-
"""입력한 정보(프로젝트 데이터)를 양식 칸에 들어갈 글로 바꾸는 부분."""
import re

from .rules import volume_basis

# 슬롯별 사람이 읽는 이름 (보고서용)
SLOT_NAMES = {
    'real_pen': '실명/필명', 'real_pen_paren': '본명(필명)', 'title_pen': '제목/필명', 'contact_email': '연락처·이메일',
    'serial_career': '연재 여부·경력', 'logline_intent': '로그라인/기획 의도', 'intro_logline': '작품 소개/로그라인',
    'intro_intent': '작품 소개(기획 의도)', 'intro_selling': '작품 소개 및 특징', 'intro_chars': '작품·등장인물 소개', 'intent_selling': '기획 의도·셀링 포인트',
    'genre_rating': '장르·연령가', 'genre_episodes': '장르/회차', 'genre_volume': '장르/분량', 'genre_date': '장르/완결 시기', 'vol_both': '투고/완결 분량',
    'eps_or_vol': '회차·분량', 'adult19_ox': '19세 이용가 여부', 'published_yn': '출간 경험 유무', 'birth_gender': '생년월일/성별',
    'char_gong': '공(남주)', 'char_su': '수(여주)', 'char_other': '그 외 인물', 'char_lead1': '주인공1', 'char_lead2': '주인공2',
    'char_lead': '주인공', 'char_sup1': '조연1', 'char_sup2': '조연2', 'char_sup3': '조연3', 'char_fsup1': '여자 조연',
    'char_msup1': '남자 조연', 'char_lead_group': '주연', 'char_sup_group': '조연', 'chars_all': '등장인물',
    'pen': '필명', 'real_name': '실명', 'email': '이메일', 'phone': '전화번호', 'contact': '연락처', 'adult': '성인 여부',
    'address': '거주지', 'bio': '작가 소개', 'awards': '수상 경력', 'other_career': '기타 경력', 'career': '출간 이력',
    'author_type': '작가 구분', 'title': '작품명', 'sub_genre': '세부 장르', 'genre': '장르', 'rating': '연령가',
    'keywords': '키워드', 'logline': '로그라인', 'intro': '작품 소개', 'intent': '기획 의도', 'selling': '셀링 포인트',
    'target': '타깃 독자', 'material': '소재', 'setting': '배경·세계관', 'twist': '반전 요소', 'when_to_read': '이럴 때 보세요',
    'quote': '공감 글귀', 'syn_ki': '기', 'syn_seung': '승', 'syn_crisis': '위기', 'syn_jeon': '전', 'syn_gyeol': '결',
    'summary': '줄거리 요약', 'synopsis': '시놉시스', 'vol_current': '투고 분량', 'vol_total': '완결 분량', 'episodes': '회차',
    'complete_date': '완결 시기', 'delivery_date': '완고 인도일', 'serial_yn': '연재 여부', 'serial_stats': '연재 성적',
    'serial_url': '연재처 주소', 'serial_site': '연재처', 'paid_serial': '유료 연재 여부', 'platform': '희망 플랫폼',
    'pub_type': '희망 출간 형태', 'pub_date': '희망 출간 시기', 'price': '판매 가격', 'reference': '참고 사항',
    'notes': '요청 사항·비고', 'card_name': '인물 이름', 'card_gender': '인물 성별', 'card_age': '인물 나이',
    'card_appearance': '인물 외모', 'card_personality': '인물 성격', 'card_extra': '인물 기타',
    'ox_parody': '패러디 여부', 'ox_incest': '근친 묘사', 'ox_minor': '미성년자 성애 묘사', 'ox_ethics': '윤리 문제 소재',
    'ox_rps': 'RPS/리네이밍', 'ox_published': '출간·유료연재 이력', 'title_bracket': '제목 자리',
}

# BL의 공/수 ↔ 로맨스의 남주/여주: 양식이 어느 쪽으로 물어도 같은 인물을 찾는다
POS_SAME = {'공': ('공', '남주'), '수': ('수', '여주'), '남주': ('남주', '공'), '여주': ('여주', '수')}

STAGES = [('ki', '기'), ('seung', '승'), ('crisis', '위기'), ('jeon', '전'), ('gyeol', '결')]


# ---------------------------------------------------------------------------
# 숫자/분량 표기
# ---------------------------------------------------------------------------
def parse_count(raw):
    """'30만', '4.5만 자', '300,000', '52341' -> int. 못 읽으면 None"""
    if raw is None:
        return None
    s = str(raw).strip().replace(',', '').replace(' ', '')
    s = re.sub(r'(자|글자)$', '', s)
    m = re.fullmatch(r'약?(\d+(?:\.\d+)?)만(\d{1,4})?', s)
    if m:
        v = float(m.group(1)) * 10000 + (int(m.group(2)) if m.group(2) else 0)
        return int(round(v))
    m = re.fullmatch(r'약?(\d+)', s)
    if m:
        return int(m.group(1))
    return None


def fmt_count(raw):
    n = parse_count(raw)
    if n is None:
        s = str(raw).strip()
        return s if not s or s.endswith('자') else s + '자'
    if n >= 10000:
        if n % 10000 == 0:
            return '%d만 자' % (n // 10000)
        if n % 1000 == 0:
            return ('%.1f' % (n / 10000)).rstrip('0').rstrip('.') + '만 자'
    return '{:,}자'.format(n)


def fmt_eps(raw):
    s = str(raw or '').strip()
    if not s:
        return ''
    if re.fullmatch(r'\d+', s):
        return '%s화' % s
    return s


class Resolver:
    """프로젝트 데이터(dict)를 받아 슬롯별 글을 만든다.

    form_slots: 이 양식에 등장한 슬롯 집합(같은 정보를 다른 칸에 중복으로 넣지 않으려고 사용)
    """

    def __init__(self, data, form_slots=None):
        self.d = data or {}
        self.form_slots = set(form_slots or ())
        self.warnings = []
        chars = [c for c in (self.d.get('characters') or []) if (c.get('name') or '').strip()]
        self.chars = chars
        self._used_chars = set()
        self.accessed = set()   # 이 양식이 실제로 읽은 입력 항목(화면의 '양식 N곳' 표시에 사용)

    # ---------------- 기본 접근 ----------------
    def g(self, key):
        self.accessed.add(key)
        v = self.d.get(key)
        if v is None:
            return ''
        return str(v).strip()

    @staticmethod
    def lines(text):
        if text is None:
            return None
        text = str(text).replace('\r\n', '\n').replace('\r', '\n').replace('\t', '    ').strip('\n')
        if not text.strip():
            return None
        return text.split('\n')

    # ---------------- 등장인물 ----------------
    def leads(self):
        self.accessed.add('characters')
        ls = [c for c in self.chars if c.get('kind') == '주연']
        if not ls:
            ls = [c for c in self.chars if c.get('pos') in ('공', '수', '남주', '여주')]
        if not ls:
            ls = self.chars[:2]
        # 공 -> 수 -> 나머지 순서
        order = {'공': 0, '남주': 0, '수': 1, '여주': 1}
        return sorted(ls, key=lambda c: (order.get(c.get('pos'), 2), self.chars.index(c)))

    def supports(self):
        lead_ids = {id(c) for c in self.leads()}
        return [c for c in self.chars if id(c) not in lead_ids]

    def by_pos(self, pos):
        self.accessed.add('characters')
        same = POS_SAME.get(pos, (pos,))
        for c in self.chars:
            if c.get('pos') in same:
                return c
        # 공/수 표시가 없으면: 공 = 주인공1, 수 = 주인공2
        leads = self.leads()
        if pos == '공' and leads:
            return leads[0]
        if pos == '수' and len(leads) > 1:
            return leads[1]
        return None

    def char_head(self, c, with_pos=True):
        bits = []
        if with_pos and c.get('pos'):
            bits.append(c['pos'])
        if (c.get('age') or '').strip():
            age = c['age'].strip()
            bits.append(age if re.search(r'[세살대]', age) else age + '세')
        if (c.get('gender') or '').strip():
            bits.append(c['gender'].strip())
        name = c.get('name', '').strip()
        return '%s (%s)' % (name, ', '.join(bits)) if bits else name

    def char_desc_lines(self, c, include_extra=True):
        out = []
        if (c.get('intro') or '').strip():
            out += self.lines(c['intro'])
        if (c.get('appearance') or '').strip():
            out += ['외모: ' + l if i == 0 else l for i, l in enumerate(self.lines(c['appearance']))]
        if (c.get('personality') or '').strip():
            out += ['성격: ' + l if i == 0 else l for i, l in enumerate(self.lines(c['personality']))]
        if include_extra and (c.get('extra') or '').strip():
            out += ['기타: ' + l if i == 0 else l for i, l in enumerate(self.lines(c['extra']))]
        return out

    def char_block(self, c, with_pos=True):
        desc = self.char_desc_lines(c)
        head = self.char_head(c, with_pos)
        if not desc:
            return [head]
        return [head + ' : ' + desc[0]] + desc[1:]

    def chars_block(self, cs):
        out = []
        for c in cs:
            if out:
                out.append('')
            out += self.char_block(c)
        return out or None

    def take(self, c):
        if c is not None:
            self._used_chars.add(id(c))
        return c

    def remaining(self):
        return [c for c in self.chars if id(c) not in self._used_chars]

    def char_for_slot(self, slot):
        leads, sups = self.leads(), self.supports()
        if slot == 'char_gong':
            return self.take(self.by_pos('공'))
        if slot == 'char_su':
            return self.take(self.by_pos('수'))
        if slot == 'char_lead1':
            return self.take(leads[0] if leads else None)
        if slot == 'char_lead2':
            return self.take(leads[1] if len(leads) > 1 else None)
        if slot.startswith('char_sup') and slot[-1].isdigit():
            i = int(slot[-1]) - 1
            return self.take(sups[i] if len(sups) > i else None)
        if slot in ('char_fsup1', 'char_msup1'):
            want = '여' if slot == 'char_fsup1' else '남'
            for c in sups:
                if id(c) not in self._used_chars and (c.get('gender') or '').startswith(want):
                    return self.take(c)
            for c in sups:
                if id(c) not in self._used_chars:
                    return self.take(c)
            return None
        return None

    def next_char(self, pool):
        for c in pool:
            if id(c) not in self._used_chars:
                return self.take(c)
        return None

    # ---------------- 줄거리 ----------------
    def stage(self, key):
        return self.lines(self.g(key))

    def has_stages(self):
        return any(self.g(k) for k, _ in STAGES)

    def composed_synopsis(self):
        out = []
        for key, name in STAGES:
            t = self.lines(self.g(key))
            if not t:
                continue
            if out:
                out.append('')
            out.append('[%s] %s' % (name, t[0]))
            out += t[1:]
        return out or None

    def form_has_stage_cells(self):
        return any(s in self.form_slots for s in ('syn_ki', 'syn_seung', 'syn_jeon', 'syn_gyeol'))

    # ---------------- 분량 ----------------
    def volume(self, which, hint=''):
        """which: 'cur' | 'tot'"""
        basis = volume_basis(hint)
        s, n = self.g(which + '_space'), self.g(which + '_nospace')
        eps = self.g(which + '_eps')
        parts = []
        if basis == 'n':
            if n:
                parts.append('공백 미포함 ' + fmt_count(n))
            elif s:
                parts.append('공백 포함 ' + fmt_count(s))
                self.warnings.append('공백 미포함 분량을 요구하지만 공백 포함 분량만 있어 그대로 넣었어요')
        elif basis == 's':
            if s:
                parts.append('공백 포함 ' + fmt_count(s))
            elif n:
                parts.append('공백 미포함 ' + fmt_count(n))
                self.warnings.append('공백 포함 분량을 요구하지만 공백 미포함 분량만 있어 그대로 넣었어요')
        else:
            if s and n:
                parts.append('공백 포함 %s (공백 미포함 %s)' % (fmt_count(s), fmt_count(n)))
            elif s:
                parts.append('공백 포함 ' + fmt_count(s))
            elif n:
                parts.append('공백 미포함 ' + fmt_count(n))
        if eps:
            parts.append('총 ' + fmt_eps(eps) if re.fullmatch(r'\d+', eps) else fmt_eps(eps))
        if not parts:
            return None
        text = ' / '.join(parts)
        if which == 'tot' and self.g('status') and self.g('status') != '완결':
            text += ' (예상)'
        return text

    # ---------------- 연재 ----------------
    def serial_line(self, ox_style=False):
        st, site, url = self.g('serial_status'), self.g('serial_site'), self.g('serial_url')
        if not (st or site or url):
            return None
        active = st in ('연재 중', '연재 완결') or (not st and (site or url))
        if not active:
            word = 'X' if ox_style else (st or '연재 안 함')
            if st == '연재 예정' and site:
                return ['%s (%s 연재 예정)' % ('X' if ox_style else '연재 예정', site)]
            return [word]
        head = ('O (%s)' % ' '.join(x for x in (site, st or '연재 중') if x)) if ox_style else \
            ' '.join(x for x in (site, st or '연재 중') if x)
        out = [head]
        if url:
            out.append(url)
        return out

    # ---------------- O/X ----------------
    def ox(self, key):
        v = self.g(key)
        return v if v in ('O', 'X') else None

    # ---------------- 메인 ----------------
    def value(self, slot, hint=''):
        """슬롯 -> 줄 목록(list[str]) 또는 None(넣을 내용 없음)"""
        g, L = self.g, self.lines
        hint = hint or ''
        if slot == 'pen':
            # '기성 작가는 기출간작 제목을 적어 주세요' 같은 안내가 있으면 출간작을 함께
            if '출간작' in hint and g('career') and 'career' not in self.form_slots:
                return [g('pen') + ' (출간작: ' + ', '.join(l.strip() for l in L(g('career'))) + ')']
            return L(g('pen'))
        if slot == 'real_name':
            return L(g('real_name'))
        if slot == 'real_pen':
            r, p = g('real_name'), g('pen')
            if not (r or p):
                return None
            return ['%s / %s' % (r, p) if r else '(필명) %s' % p]
        if slot == 'real_pen_paren':
            r, p = g('real_name'), g('pen')
            if not (r or p):
                return None
            return ['%s (필명: %s)' % (r, p) if r else '(필명: %s)' % p]
        if slot == 'title_pen':
            t, p = g('title'), g('pen')
            return ['%s / %s' % (t, p)] if (t or p) else None
        if slot == 'email':
            return L(g('email'))
        if slot == 'phone':
            return L(g('phone'))
        if slot == 'contact':
            ph, em = g('phone'), g('email')
            if 'email' in self.form_slots or 'contact_email' in self.form_slots:
                return L(ph) if ph else None
            if '@' in hint and em:
                return [em + (' / ' + ph if ph else '')]
            v = ' / '.join(x for x in (ph, em) if x)
            return L(v)
        if slot == 'contact_email':
            v = ' / '.join(x for x in (g('phone'), g('email')) if x)
            return L(v)
        if slot == 'adult':
            return L(g('adult'))
        if slot == 'birth_gender':
            b, s = g('birth'), g('author_gender')
            return ['%s / %s' % (b, s)] if (b or s) else None
        if slot == 'address':
            return L(g('address'))
        if slot == 'author_type':
            return L(g('author_type'))
        if slot == 'career':
            c = g('career')
            if c:
                return L(c)
            if g('author_type') == '신인':
                return None if ('공란' in hint or '비워' in hint) else ['없음 (신인)']
            return None
        if slot == 'bio':
            b, c = g('bio'), g('career')
            out = L(b) or []
            if c and ('전작' in hint or '출간' in hint or '이력' in hint or not out):
                out += (['', '[출간 이력]'] if out else []) + L(c)
            return out or None
        if slot == 'awards':
            return L(g('awards'))
        if slot == 'other_career':
            return L(g('other_career'))
        if slot == 'published_yn':
            t = g('author_type')
            if t == '기성' or (g('career') and t != '신인'):
                return ['유']
            if t == '신인':
                return ['무']
            return None
        if slot == 'serial_career':
            out = self.serial_line() or []
            if g('career'):
                out += (['[출간 이력]'] if out else []) + L(g('career'))
            return out or None
        if slot == 'title':
            return L(g('title'))
        if slot == 'genre':
            ge, sub = g('genre'), g('sub_genre')
            if 'sub_genre' not in self.form_slots and sub and ge:
                return ['%s (%s)' % (ge, sub)]
            return L(ge)
        if slot == 'sub_genre':
            return L(g('sub_genre'))
        if slot == 'rating':
            return L(g('rating'))
        if slot == 'adult19_ox':
            r = g('rating')
            if not r:
                return None
            return ['O'] if '19' in r else ['X']
        if slot == 'genre_rating':
            v = ' / '.join(x for x in (g('genre'), g('rating')) if x)
            return L(v)
        if slot == 'genre_episodes':
            v = ' / '.join(x for x in (g('genre'), fmt_eps(g('tot_eps'))) if x)
            return L(v)
        if slot == 'genre_date':
            d = g('complete_date')
            v = ' / '.join(x for x in (g('genre'), (d + (' 송고 예정' if '송고' in hint else '')) if d else '') if x)
            return L(v)
        if slot == 'genre_volume':
            v = ' / '.join(x for x in (g('genre'), self.volume('tot', hint)) if x)
            return L(v)
        if slot == 'keywords':
            return L(g('keywords'))
        if slot == 'logline':
            return L(g('logline'))
        if slot == 'intro':
            return L(g('intro'))
        if slot == 'intent':
            out = L(g('intent')) or []
            extra = []
            if ('독자' in hint or '타깃' in hint or '타겟' in hint) and g('target') and 'target' not in self.form_slots:
                extra.append('타깃 독자: ' + g('target'))
            if '플랫폼' in hint and g('platform') and 'platform' not in self.form_slots:
                extra.append('희망 플랫폼: ' + g('platform'))
            if '프로모션' in hint and g('notes') and 'notes' not in self.form_slots:
                extra.append(g('notes'))
            if extra:
                out += ([''] if out else []) + extra
            return out or None
        if slot == 'selling':
            return L(g('selling'))
        if slot == 'intent_selling':
            out = L(g('intent')) or []
            if g('selling'):
                out += ([''] if out else []) + ['[셀링 포인트]'] + L(g('selling'))
            return out or None
        if slot == 'intro_selling':
            out = L(g('intro')) or []
            if g('selling'):
                out += ([''] if out else []) + ['[작품 특징]'] + L(g('selling'))
            return out or None
        if slot == 'intro_chars':
            out = L(g('intro')) or []
            cb = self.chars_block(self.chars)
            if cb:
                out += ([''] if out else []) + ['[등장인물]'] + cb
            return out or None
        if slot == 'intro_intent':
            out = L(g('intro')) or []
            if g('intent'):
                out += ([''] if out else []) + ['[기획 의도]'] + L(g('intent'))
            return out or None
        if slot == 'logline_intent':
            out = L(g('logline')) or []
            if g('intent'):
                out += ([''] if out else []) + L(g('intent'))
            return out or None
        if slot == 'intro_logline':
            out = []
            if g('logline') and 'logline' not in self.form_slots:
                out += L(g('logline')) + ['']
            out += L(g('intro')) or []
            return out or None
        if slot == 'target':
            return L(g('target'))
        if slot == 'material':
            return L(g('material'))
        if slot == 'setting':
            return L(g('setting'))
        if slot == 'twist':
            return L(g('twist'))
        if slot == 'when_to_read':
            return L(g('when_to_read'))
        if slot == 'quote':
            return L(g('quote'))
        if slot in ('syn_ki', 'syn_seung', 'syn_crisis', 'syn_jeon', 'syn_gyeol'):
            return self.stage(slot[4:])
        if slot == 'summary':
            return L(g('summary')) or (None if self.form_has_stage_cells() else self.composed_synopsis())
        if slot == 'synopsis':
            if self.form_has_stage_cells():
                return L(g('summary')) or None
            return self.composed_synopsis() or L(g('summary'))
        if slot == 'vol_current':
            return L(self.volume('cur', hint))
        if slot == 'vol_total':
            return L(self.volume('tot', hint))
        if slot == 'vol_both':
            a, b = self.volume('cur', hint), self.volume('tot', hint)
            return ['%s / %s' % (a or '-', b or '-')] if (a or b) else None
        if slot == 'episodes':
            e = g('tot_eps')
            if not e:
                return None
            t = fmt_eps(e)
            if g('status') and g('status') != '완결':
                t += ' (예상)'
            return [t]
        if slot == 'eps_or_vol':
            return L(self.volume('tot', hint))
        if slot == 'complete_date':
            return L(g('complete_date') or ('완결' if g('status') == '완결' else ''))
        if slot == 'delivery_date':
            return L(g('delivery_date') or g('complete_date') or ('완결 원고 (즉시 가능)' if g('status') == '완결' else ''))
        if slot == 'serial_yn':
            ox_style = bool(re.search(r'O\s*[,/]\s*X|O/X', hint))
            return self.serial_line(ox_style)
        if slot == 'serial_site':
            return self.serial_line()
        if slot == 'serial_url':
            u = g('serial_url')
            if u:
                return [(g('serial_site') + ' ' if g('serial_site') else '') + u]
            return self.serial_line()
        if slot == 'serial_stats':
            out = []
            if g('serial_site') or g('serial_url'):
                out += self.serial_line() or []
            if g('serial_stats'):
                out += L(g('serial_stats'))
            return out or None
        if slot == 'paid_serial':
            return [self.ox('ox_published')] if self.ox('ox_published') else None
        if slot == 'platform':
            return L(g('platform'))
        if slot == 'pub_type':
            return L(g('pub_type'))
        if slot == 'pub_date':
            return L(g('pub_date'))
        if slot == 'price':
            return L(g('price'))
        if slot == 'reference':
            out = []
            if g('serial_site') or g('serial_stats'):
                out += ['[연재]'] + (self.serial_line() or []) + (L(g('serial_stats')) or [])
            if g('career') and 'career' not in self.form_slots:
                out += ([''] if out else []) + ['[출간 이력]'] + L(g('career'))
            if g('notes') and 'notes' not in self.form_slots:
                out += ([''] if out else []) + L(g('notes'))
            return out or None
        if slot == 'notes':
            out = L(g('notes')) or []
            extra = []
            if '연재' in hint and 'serial_site' not in self.form_slots and 'serial_yn' not in self.form_slots:
                sl = self.serial_line()
                if sl and (g('serial_site') or g('serial_url')):
                    extra.append('연재처: ' + ' / '.join(sl))
                if g('serial_stats'):
                    extra.append('연재 성적: ' + g('serial_stats'))
            if '플랫폼' in hint and g('platform') and 'platform' not in self.form_slots:
                extra.append('희망 플랫폼: ' + g('platform'))
            if extra:
                out = extra + ([''] + out if out else [])
            return out or None
        # ---- 등장인물 ----
        if slot == 'chars_all':
            self.accessed.add('characters')
            return self.chars_block([self.take(c) for c in self.chars])
        if slot == 'char_lead_group':
            return self.chars_block([self.take(c) for c in self.leads()])
        if slot == 'char_sup_group':
            return self.chars_block([self.take(c) for c in self.supports() if id(c) not in self._used_chars])
        if slot == 'char_other':
            return self.chars_block(self.remaining())
        if slot == 'char_lead':
            c = self.next_char(self.leads())
            return self.char_block(c) if c else None
        if slot.startswith('char_'):
            c = self.char_for_slot(slot)
            return self.char_block(c) if c else None
        return None

    def ox_value(self, key):
        v = self.ox(key)
        if v and key == 'ox_incest' and v == 'O' and self.g('incest_relation'):
            return v
        return v
