# -*- coding: utf-8 -*-
"""화면에 보여 줄 입력 항목 정의."""

GENRES = ['BL', '로맨스', '로맨스판타지', '현대로맨스', '현대판타지', '판타지', '무협', 'GL']
SUB_GENRES = ['현대물', '동양풍', '서양풍', '판타지물', '오메가버스', '가이드버스', '캠퍼스물', '오피스물', '학원물', '아포칼립스', '게임판타지']
RATINGS = ['전체 이용가', '15세 이용가', '19세 이용가']
PLATFORMS = ['리디', '카카오페이지', '네이버 시리즈', '리디, 카카오페이지', '리디, 네이버 시리즈', '상관없음']

# (key, 이름, 종류, 필수, 도움말, 선택지/높이)
#  종류: line 한 줄 | text 여러 줄 | choice 고르기 | combo 고르기+직접 입력 | volume 분량 묶음 | ox O/X
STEPS = [
    {
        'id': 'author', 'title': '작가 정보', 'icon': '✎',
        'desc': '투고 메일을 받을 연락처와 경력이에요. 한 번만 적어 두면 다음 작품에도 그대로 쓸 수 있어요.',
        'fields': [
            ('pen', '필명', 'line', True, '양식의 「작가명」「저자」「필명」 칸에 들어가요.', None),
            ('email', '이메일', 'line', True, '', None),
            ('phone', '휴대폰 번호', 'line', False, '「연락처」 칸에 들어가요. 이메일 칸이 따로 없는 양식에는 이메일도 함께 적혀요.', None),
            ('author_type', '작가 구분', 'choice', False, '신인이면 출간 이력 칸에 「없음 (신인)」이 들어가요. 「공란」을 요구하는 양식은 비워 둬요.', ['', '신인', '기성']),
            ('career', '출간 이력', 'text', False, '한 줄에 한 작품씩: 작품명 (출간 연도, 플랫폼·프로모션)\n예) 《유리 온실》 (2024, 리디 단행본)', 4),
            ('bio', '작가 소개', 'text', False, '「작가 소개」 칸이 있는 양식용. 비워 두면 출간 이력이 대신 들어가요.', 3),
            ('awards', '수상 경력', 'text', False, '공모전 수상 등. 묻는 양식에만 들어가요.', 2),
        ],
        'extra_title': '일부 출판사만 묻는 항목',
        'extra': [
            ('real_name', '실명(본명)', 'line', False, '「실명/필명」을 함께 묻는 양식(위즈덤하우스, KW북스 등)에 쓰여요.', None),
            ('adult', '성인 여부', 'choice', False, 'g노벨 등 「성인/미성년자」 칸용', ['', '성인', '미성년자']),
            ('birth', '생년월일', 'line', False, '', None),
            ('author_gender', '성별', 'choice', False, '', ['', '여', '남', '밝히지 않음']),
            ('address', '거주지', 'line', False, '', None),
            ('other_career', '기타 경력', 'text', False, '집필 외 관련 경력(게임 시나리오, 강의 등)', 2),
        ],
    },
    {
        'id': 'work', 'title': '작품 기본 정보', 'icon': '❏',
        'desc': '거의 모든 양식에 들어가는 기본 항목이에요.',
        'fields': [
            ('title', '작품명', 'line', True, '결과 파일 이름에도 쓰여요.', None),
            ('genre', '장르', 'combo', True, '목록에서 고르거나 직접 입력하세요.', GENRES),
            ('sub_genre', '세부 장르', 'combo', False, '「세부 장르」 칸이 없는 양식은 「BL (현대물)」처럼 장르 옆에 붙여 넣어요.', SUB_GENRES),
            ('rating', '연령가', 'choice', True, '체크박스(□) 양식은 맞는 칸에 ■ 표시가 돼요.', [''] + RATINGS),
            ('keywords', '키워드', 'text', True, '#키워드 형식으로 5~10개 추천. 공·수 키워드를 꼭 넣어 주세요.\n예) #현대물 #재회물 #집착공 #상처수', 3),
            ('logline', '로그라인 (한 줄 소개)', 'text', False, '한 문장으로 작품을 소개해 주세요.', 2),
        ],
    },
    {
        'id': 'pitch', 'title': '소개 · 기획', 'icon': '✦',
        'desc': '작품의 매력을 보여 주는 칸이에요. 위의 두 칸이 가장 많이 쓰여요.',
        'fields': [
            ('intro', '작품 소개글', 'text', True, '플랫폼 책 소개처럼 써 주세요.', 6),
            ('intent', '기획 의도', 'text', True, '쓰게 된 계기, 보여 주고 싶은 것.', 4),
            ('selling', '셀링 포인트 · 작품 특징', 'text', False, '「기획 의도 및 셀링포인트」처럼 묶인 칸에는 기획 의도 아래에 붙어요.', 3),
            ('target', '타깃 독자', 'text', False, '', 2),
            ('setting', '배경 · 세계관', 'text', False, '', 3),
            ('twist', '반전 요소', 'text', False, 'g노벨 시놉시스 양식 등', 2),
            ('when_to_read', '이럴 때 보세요', 'text', False, '유펜비·가로수길·이플북스 등', 2),
        ],
        'extra_title': '그 밖의 항목',
        'extra': [
            ('material', '소재', 'line', False, '레드큐 양식', None),
            ('quote', '공감 글귀', 'line', False, '가로수길 양식', None),
        ],
    },
    {
        'id': 'chars', 'title': '등장인물', 'icon': '☺',
        'desc': '인물을 추가하면 「공」「수」「주인공1」「조연」 같은 칸에 알맞게 나눠 들어가요.',
        'fields': [],
    },
    {
        'id': 'story', 'title': '줄거리', 'icon': '☰',
        'desc': '기·승·전·결로 나눠 쓰면, 한 칸짜리 「시놉시스」 칸에는 네 단계가 이어 붙여져 들어가요.',
        'fields': [
            ('summary', '줄거리 요약', 'text', True, '3~5줄 요약. 「간단한 줄거리」「작품 줄거리」 칸에 들어가요.', 4),
            ('ki', '기 (발단)', 'text', True, '', 5),
            ('seung', '승 (전개)', 'text', True, '', 5),
            ('jeon', '전 (절정)', 'text', True, '', 5),
            ('gyeol', '결 (결말)', 'text', True, '결말까지 분명하게 써 주세요(출판사 검토용).', 5),
        ],
        'extra_title': '5단 구성 양식용',
        'extra': [
            ('crisis', '위기', 'text', False, '레드큐 「중(위기)」, 나인스펙트럼 「위기」 칸용. 비워 두면 그 칸만 비어요.', 4),
        ],
    },
    {
        'id': 'volume', 'title': '분량 · 연재 · 출간', 'icon': '▤',
        'desc': '분량은 아는 만큼만 적으세요. 양식이 「공백 미포함」을 요구하면 그 숫자를 골라 넣어요.',
        'fields': [
            ('status', '집필 상태', 'choice', True, '「집필 중」이면 완결 분량 뒤에 (예상)이 붙어요.', ['', '집필 중', '완결']),
            ('cur', '지금까지 쓴 분량 (투고 분량)', 'volume', False, '예) 62000 또는 6.2만', None),
            ('tot', '완결 (예상) 분량', 'volume', True, '예) 400000 또는 40만', None),
            ('complete_date', '완결 (예정) 시기', 'line', False, '예) 2027년 3월', None),
            ('serial_status', '연재 상태', 'choice', False, '', ['', '연재 중', '연재 완결', '연재 예정', '연재 안 함']),
            ('serial_site', '연재처', 'line', False, '예) 조아라 / 디리토 / 포스타입', None),
            ('serial_url', '연재 주소(URL)', 'line', False, '', None),
            ('serial_stats', '연재 성적', 'line', False, '예) 선작 1,200 / 평균 조회수 800', None),
            ('pub_type', '희망 출간 형태', 'choice', False, '', ['', '연재', '단행본', '연재·단행본 모두 가능']),
            ('platform', '희망 플랫폼', 'combo', False, '', PLATFORMS),
            ('pub_date', '희망 출간 시기', 'line', False, '예) 2027년 상반기', None),
            ('notes', '요청 사항 · 비고', 'text', False, '「요청사항」「비고」「건의 사항」 칸에 들어가요.', 3),
        ],
        'extra_title': '일부 출판사만 묻는 항목',
        'extra': [
            ('delivery_date', '완고 인도 가능일', 'line', False, '소이미디어·바로나글. 비워 두면 완결 시기가 들어가요.', None),
            ('price', '희망 판매 가격', 'line', False, '비단잉어 등', None),
        ],
    },
    {
        'id': 'check', 'title': '확인 사항', 'icon': '✓',
        'desc': '사슴의 풀밭 등 O/X 확인 질문이 있는 양식에 들어가요. 해당하는 쪽을 골라 주세요.',
        'fields': [
            ('ox_parody', '패러디 작품인가요?', 'ox', False, '', None),
            ('ox_incest', '주인공의 근친 성애 장면이 있나요?', 'ox', False, '', None),
            ('incest_relation', '└ 있다면 어떤 관계인가요?', 'line', False, '', None),
            ('ox_minor', '미성년자의 성애 장면이 있나요?', 'ox', False, '', None),
            ('ox_ethics', '강제적 관계·범죄 미화 등 윤리 문제 소재가 있나요?', 'ox', False, '', None),
            ('ox_rps', 'RPS 또는 리네이밍 작품인가요?', 'ox', False, '', None),
            ('ox_published', '출간했거나 유료 연재한 작품인가요?', 'ox', False, '「유료 연재 여부」 칸에도 쓰여요.', None),
        ],
    },
    {
        'id': 'make', 'title': '일괄 작성 · 저장', 'icon': '▶',
        'desc': '', 'fields': [],
    },
]

CHAR_FIELDS = [
    ('name', '이름', 'line', None),
    ('kind', '구분', 'choice', ['주연', '조연', '기타']),
    ('pos', '공/수·남주/여주', 'choice', ['', '공', '수', '남주', '여주']),
    ('age', '나이', 'line', None),
    ('gender', '성별', 'choice', ['', '남', '여', '기타']),
    ('intro', '인물 소개', 'text', 4),
    ('appearance', '외모', 'text', 2),
    ('personality', '성격', 'text', 2),
    ('extra', '기타 (습관·말투·특이사항)', 'text', 2),
    ('goal', '목표 · 욕망 · 결핍', 'line', None),
    ('backstory', '과거 · 비하인드', 'text', 2),
]

VOLUME_PARTS = [('_space', '공백 포함', '자'), ('_nospace', '공백 미포함', '자'), ('_eps', '회차', '화')]


def all_keys():
    keys = []
    for st in STEPS:
        for f in st['fields'] + st.get('extra', []):
            if f[2] == 'volume':
                keys += [f[0] + suf for suf, _, _ in VOLUME_PARTS]
            else:
                keys.append(f[0])
    return keys


def required_keys():
    out = []
    for st in STEPS:
        for f in st['fields']:
            if f[3]:
                out.append((st['id'], f[0], f[1], f[2]))
    return out


def empty_project():
    p = {k: '' for k in all_keys()}
    p['characters'] = []
    p['_format'] = 'bl-tugo-writer'
    p['_version'] = 2
    return p
