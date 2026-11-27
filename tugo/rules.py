# -*- coding: utf-8 -*-
"""양식의 '항목 이름(라벨)'을 읽어 어떤 정보를 넣을 칸인지 판단하는 규칙 모음."""
import re

# ---------------------------------------------------------------------------
# 라벨 정규화
# ---------------------------------------------------------------------------
_NUM_PREFIX = re.compile(r'^\s*(?:\d{1,2}\s*[\.\)]|[①-⑳]|\(\d{1,2}\)|[가-하]\.)\s*')
_DECOR = re.compile(r'[\s　 *※◈■□▶▷►●○◆◇★☆♥♡<>〈〉《》「」『』【】\[\]:：·‧・•\-–—_~"\'“”‘’▮]')
_PAREN = re.compile(r'\([^()]*\)')
_PUA = re.compile('[-]')   # 한글 문서의 글머리 기호(사용자 정의 영역 글자)


def norm(text):
    """공백·장식 기호를 지우고 소문자로 만든다. 괄호는 남긴다."""
    s = _NUM_PREFIX.sub('', _PUA.sub('', text or '').strip())
    s = s.replace('&', '및').replace('（', '(').replace('）', ')')
    s = _DECOR.sub('', s)
    return s.lower()


def strip_paren(s):
    prev = None
    while prev != s:
        prev = s
        s = _PAREN.sub('', s)
    return s


def paren_inner(s):
    return re.findall(r'\(([^()]*)\)', s)


# ---------------------------------------------------------------------------
# 라벨 -> 슬롯 규칙 (위에서부터 먼저 맞는 규칙을 쓴다: 구체적인 것을 앞에)
# ---------------------------------------------------------------------------
RULES = [
    # --- 묶음(복합) 항목 ---
    ('real_pen', r'(작가명|저자|작가|성명|작가이름|이름)\((실명|본명)/필명\)'),
    ('real_pen_paren', r'작가본명\(필명\)|본명\(필명\)|실명\(필명\)'),
    ('title_pen', r'제목/필명|작품명/필명'),
    ('contact_email', r'연락처및이메일(주소)?|연락처/이메일(주소)?'),
    ('serial_career', r'연재여부및경력|연재및출간이력'),
    ('logline_intent', r'로그라인/기획의도'),
    ('intro_logline', r'작품소개글?/로그라인'),
    ('intro_intent', r'작품소개\(기획의도.*\)'),
    ('intro_selling', r'작품소개및특징'),
    ('intro_chars', r'작품및등장인물소개|작품및인물소개'),
    ('intent_selling', r'기획의도및(셀링포인트|작품특징|특징|매력)'),
    ('genre_rating', r'장르\(수위\)|장르\(연령가\)|장르및(수위|연령가)|장르/(수위|연령가|연령)'),
    ('genre_episodes', r'장르/회차'),
    ('genre_volume', r'장르/(예상)?분량'),
    ('genre_date', r'장르/송고일정|장르/(예상)?완결시기'),
    ('vol_both', r'투고분량/(예상)?완결분량'),
    ('eps_or_vol', r'완결예상회차or분량.*|(예상)?완결회차/분량|전체회차분량|회차/분량'),
    ('adult19_ox', r'19세(이하)?이용불가여부'),
    ('published_yn', r'출간경험유/?무|출간경험(여부)?'),
    ('birth_gender', r'생년월일/성별'),
    # --- 등장인물 슬롯 ---
    ('char_gong', r'등장인물소개\(공\)|주인공1\(남주/공\)|\(?메인공\)?|공|남주|남자주인공|남주인공|메인남주'),
    ('char_su', r'등장인물소개\(수\)|주인공2\(여주/수\)|\(?메인수\)?|수|여주|여자주인공|여주인공|메인여주'),
    ('char_other', r'등장인물소개\(기타중요인물\)|그외|그외인물|기타조연|기타인물|기타중요인물'),
    ('char_lead1', r'주인공1'),
    ('char_lead2', r'주인공2'),
    ('char_lead', r'주인공'),
    ('char_sup1', r'조연1'),
    ('char_sup2', r'조연2'),
    ('char_sup3', r'조연3'),
    ('char_fsup1', r'여조1|여조연1?'),
    ('char_msup1', r'남조1|남조연1?'),
    ('char_lead_group', r'주연'),
    ('char_sup_group', r'조연'),
    ('chars_all', r'주요인물소개|등장인물|주요인물|인물소개|인물설정(\(주조연\))?|캐릭터소개|주요캐릭터소개|'
                  r'등장인물소개|주요등장인물|캐릭터설정|주요등장인물소개|캐릭터|주요캐릭터'),
    # --- 작가 ---
    ('pen', r'필명|작가명|작가명\(필명\)|필명\(작가명\)|작가|저자|저자필명|이름/필명|성명/필명|작가이름/필명|작가필명|작가이름'),
    ('real_name', r'실명|성함|본명|성명'),
    ('email', r'이메일|메일주소|e?mail|이메일주소|메일|전자우편|emailaddress'),
    ('phone', r'전화번호|핸드폰|핸드폰번호|휴대폰|휴대폰번호|휴대전화|mobile|전화|phone'),
    ('contact', r'연락처'),
    ('adult', r'성인/미성년자|성인여부'),
    ('address', r'거주지|주소'),
    ('bio', r'작가소개|작가소개글|작가프로필'),
    ('awards', r'(집필관련)?수상경력|수상이력'),
    ('other_career', r'기타경력'),
    ('career', r'작가경력사항|작가경력|경력|이력|작가이력|출간이력|출간경력|이전출간작|출간작|출간작품|출간작정보'),
    ('author_type', r'작가구분'),
    # --- 작품 기본 ---
    ('title', r'작품명|작품제목|제목|투고작품명|작품명\(가제\)'),
    ('sub_genre', r'세부장르'),
    ('genre', r'장르|분야|분야\(장르\)|장르\(.*\)'),
    ('rating', r'이용연령가|연령가|이용등급|작품연령가|콘텐츠연령가|수위|이용연령|이용가|희망연령가|연령등급|등급|연령|희망이용가|작품이용가능연령|이용가능연령'),
    ('keywords', r'키워드|주요키워드|작품키워드|키워드검색어|검색키워드|태그'),
    ('logline', r'로그라인|한줄시놉시스|한줄소개|한줄요약'),
    ('intro', r'작품소개|소개글|작품소개글|책소개|소개|플랫폼소개글|작품소개\(책소개\)'),
    ('intent', r'기획의도|집필의도및주제|작품기획의도|집필의도|기획의도및주제'),
    ('selling', r'셀링포인트|감상포인트|작품의매력|매력포인트|작품특이사항|차별성|차별점|작품의차별성'),
    ('target', r'타겟독자|타깃독자|예상주독자층|주독자층|타겟층|타깃층|예상독자'),
    ('material', r'소재'),
    ('setting', r'작품세계관|세계관|배경설정|배경|배경/분야|세계관설정'),
    ('twist', r'반전요소'),
    ('when_to_read', r'이도서를읽어야할때|이럴때보세요|이럴때읽어주세요'),
    ('quote', r'공감글귀'),
    # --- 줄거리 ---
    ('syn_ki', r'기|기\(발단\)|발단'),
    ('syn_seung', r'승|승\(전개\)|전개'),
    ('syn_crisis', r'중\(위기\)|위기'),
    ('syn_jeon', r'전|전\(절정\)|절정'),
    ('syn_gyeol', r'결|결\(결말\)|결말'),
    ('summary', r'간단줄거리|간단한줄거리|간단한줄거리요약|줄거리요약|간략줄거리|작품소개\(줄거리\)|작품줄거리|간략시놉시스|원고간단요약'),
    ('synopsis', r'시놉시스|줄거리|내용전개및줄거리|스토리라인|서사구조|줄거리\(결말포함\)|줄거리\(구체적으로\)|'
                 r'전체줄거리|시놉시스\(기승전결\)|시놉시스차트|기승전결|줄거리소개|줄거리\(기승전결\)'),
    # --- 분량·일정 ---
    ('vol_current', r'투고분량|현재완고분량|현재집필한원고|현재분량|현재원고분량|투고원고분량'),
    ('vol_total', r'예상완결분량|완결분량|분량|예상분량|완결\(예상\)분량|완결원고량|완고기준글자수.*|원고분량|'
                  r'작품분량|전체분량|총분량|완결예상분량'),
    ('episodes', r'완결회차|예상완결회차|예상화수|총화수|예상회차|완결예상회차|회차|총회차|화수'),
    ('complete_date', r'예상완결시기|완결시기|예상완결일자|완결예정일|완결예상시기|완결예정시기'),
    ('delivery_date', r'완고인도일|완결고인도일|원고인도일'),
    # --- 연재 ---
    ('serial_yn', r'연재여부|무료연재여부|연재여부및사이트|연재여부및연재처|연재유무'),
    ('serial_stats', r'연재처성적.*|연재성적|선호작및즐겨찾기수|선호작수|선작수|즐겨찾기수'),
    ('serial_url', r'연재처url|무료연재처url|연재사이트링크|연재링크|연재url|연재주소'),
    ('serial_site', r'연재처|연재사이트|무료연재처'),
    ('paid_serial', r'유료연재여부|유료연재이력|투고작유료연재이력|유료연재경험'),
    # --- 출간 희망 ---
    ('platform', r'희망플랫폼|희망출간플랫폼|원하시는플랫폼|출간희망플랫폼|예상플랫폼|희망연재처|희망출간처|플랫폼|희망연재플랫폼|선호플랫폼|희망유통처'),
    ('pub_type', r'희망출간형태|희망출간방향|출간형태|출간방향|출간형식|희망출간형식'),
    ('pub_date', r'희망출간일정|출간희망일자|희망출간일|희망론칭시기|희망출간시기|출간희망일|출간희망시기'),
    ('price', r'판매가격|가격책정|가격'),
    ('reference', r'참고사항'),
    ('notes', r'요청사항|요구사항|그외출판사건의사항|비고|기타사항|건의사항|기타|기타요청사항|문의사항'),
]
_COMPILED = [(slot, re.compile(r'(?:%s)' % pat)) for slot, pat in RULES]

# 등장인물 카드(한 인물당 표 하나) 안에서만 쓰는 라벨
CARD_RULES = [
    ('card_name', r'이름|캐릭터|캐릭터명|인물'),
    ('card_gender', r'성별'),
    ('card_age', r'나이'),
    ('card_appearance', r'외모적특징|외형묘사|외모|외형'),
    ('card_personality', r'성격적특징|성격및특징|성격'),
    ('card_extra', r'기타사항|특이사항및반전요소|특이사항|기타'),
]
_CARD_COMPILED = [(slot, re.compile(r'(?:%s)' % pat)) for slot, pat in CARD_RULES]

GROUP_SLOTS = {'chars_all', 'char_lead_group', 'char_sup_group', 'synopsis', 'summary'}
STAGE_SLOTS = ('syn_ki', 'syn_seung', 'syn_crisis', 'syn_jeon', 'syn_gyeol')
CHAR_SLOTS_PREFIX = 'char_'


def _variants(text):
    """라벨 원문 -> 비교용 문자열 후보들"""
    full = norm(text)
    out = [full]
    np_ = strip_paren(full)
    if np_ and np_ != full:
        out.append(np_)
    return out


def match_slot(text, rules=None):
    if not text:
        return None
    rules = rules or _COMPILED
    vs = _variants(text)
    for v in vs:
        if not v or len(v) > 40:
            continue
        for slot, rx in rules:
            if rx.fullmatch(v):
                return slot
    return None


def match_card(text):
    return match_slot(text, _CARD_COMPILED)


def label_candidates(lines):
    """셀의 문단 목록에서 라벨로 볼 만한 문자열 후보: 전체 합친 것, 첫 문단."""
    lines = [l for l in (x.strip() for x in lines) if l]
    if not lines:
        return []
    cands = []
    joined = ''.join(lines)
    if len(norm(joined)) <= 40:
        cands.append(joined)
    cands.append(lines[0])
    if len(lines) >= 2:
        cands.append(lines[0] + lines[1])
    return cands


def match_label_lines(lines):
    for c in label_candidates(lines):
        s = match_slot(c)
        if s:
            return s, c
    return None, None


# ---------------------------------------------------------------------------
# 안내문/예시/빈 틀 판별: 이런 글은 지우고 내용을 넣어도 된다
# ---------------------------------------------------------------------------
_GUIDE_WORDS = ['적어', '기재', '작성', '입력', '써주', '써 주', '택1', '택 1', '중 택', '선택', '기입', '표기',
                '부탁', '알려주', '주세요', '해주세요', '바랍니다', '없을 경우', '해당 사항', '공란', '필수',
                '체크해', '첨부해', '해당되는', '하시면', '경우에만', '가능합니다', '좋습니다', '참고하세요',
                '됩니다', '않아도', '생략 가능', '서술', '개 이상', '개 이하', '참고:', '참고 :', '최소 ']
_GUIDE_EXACT = {'/', '-', '링크', '없음', 'o/x', 'ox', '공미포', '공포', '제목입니다', '필명입니다', '???', '?',
                '(필명)', '예)', '예시)', 'ex)', 'url', '주소', '연락처', '/ /'}
_STAGE_WORDS = {'기', '승', '전', '결', '기:', '승:', '전:', '결:'}
_TEMPLATE = re.compile(r'0{3,}|O{2}|○{2}|~~|\?{3}|_{3,}|\s{2,}만\s?자|OO|○○|\*{3}')
_OPTION_SEP = re.compile(r'\s*(?:/|,|·|\bor\b|또는|혹은|\|)\s*')


def is_guide_line(line):
    t = (line or '').strip()
    if not t:
        return False
    low = t.lower()
    n = norm(t)
    if n in _GUIDE_EXACT or low in _GUIDE_EXACT:
        return True
    if t[0] in '*※(（[<〈《▶' or low.startswith(('ex', '예)', '예시', '(예', '예:', '예 )', 'e.g')):
        return True
    if any(w in t for w in _GUIDE_WORDS):
        return True
    if _TEMPLATE.search(t):
        return True
    if t.endswith('입니다') and len(t) <= 12:
        return True
    if t.endswith(' 등') or t.endswith('등)'):
        return True
    # 선택지 나열: "전체/15세/19세", "단행 or 연재", "O / X"
    parts = [p for p in _OPTION_SEP.split(t) if p.strip()]
    if len(parts) >= 2 and len(t) <= 60 and all(len(norm(p)) <= 12 for p in parts):
        if re.search(r'/|\bor\b|또는|혹은', t):
            return True
    return False


def is_guide_text(lines):
    """셀(또는 문단 묶음) 전체가 안내문/예시/빈 틀인지."""
    lines = [l.strip() for l in lines if l and l.strip()]
    if not lines:
        return False
    if len(lines) >= 2 and all(l.replace(' ', '') in _STAGE_WORDS for l in lines):
        return True
    if len(lines) == 1 and lines[0].replace(' ', '') in _STAGE_WORDS:
        return False
    return is_guide_line(lines[0])


def is_example_line(line):
    t = (line or '').strip().lower()
    return t.startswith(('예)', '(예)', '예시)', 'ex)', 'ex.', 'ex ', '[ex', 'e.g'))


# 콜론 형식 한 줄: "■ 작품명 :" / "기 :" / "핸드폰 :"
COLON_LINE = re.compile(r'^(?P<head>\s*[^:：]{1,40}?)\s*[:：]\s*(?P<rest>.*)$')
NUMBERED = re.compile(r'^\s*(?:\d{1,2}\s*[\.\)]|[①-⑳])')


def parse_colon_line(text):
    m = COLON_LINE.match(text or '')
    if not m:
        return None
    head, rest = m.group('head'), m.group('rest').strip()
    if 'http' in head.lower():
        return None
    return head, rest


def rest_is_fillable(rest, numbered):
    if not rest:
        return True
    r = rest.strip()
    if numbered:
        # 번호 붙은 안내 목록("3. 장르: 무협, 판타지…")은 괄호 안내문일 때만 채운다
        return r.startswith('(') and r.endswith(')')
    return is_guide_line(r) or bool(_TEMPLATE.search(r)) or bool(re.fullmatch(r'[\s/]*', r))


# ---------------------------------------------------------------------------
# 분량 기준(공백 포함/미포함) 판별
# ---------------------------------------------------------------------------
def volume_basis(text):
    t = (text or '').replace(' ', '')
    nospace = bool(re.search(r'공미포|공백미포함|공백제외|미포함', t))
    space = bool(re.search(r'공포(?!함)|공백포함|공포기준', t.replace('공백미포함', '').replace('미포함', '')))
    if nospace and space:
        return 'both'
    if nospace:
        return 'n'
    if space:
        return 's'
    return None


# 투고 안내(분량·파일 형식 등) 문장 추출
REQ_PATTERNS = re.compile(r'(\d[\d,\.]*\s*만?\s*자\s*(이상|내외|이내)|\d+\s*화\s*(분량|이상)|PDF|파일\s*명|파일명|파일\s*제목|하나의\s*파일|원고.*(첨부|붙여)|분량)')
