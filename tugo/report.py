# -*- coding: utf-8 -*-
"""결과 보고서(HTML) 만들기."""
import datetime
import html
import os

from .values import SLOT_NAMES

# 칸 종류 -> 입력 화면의 어느 탭에서 채우는지
SLOT_TAB = {
    'author': {'pen', 'real_name', 'email', 'phone', 'contact', 'contact_email', 'adult', 'address', 'bio', 'awards',
               'other_career', 'career', 'author_type', 'real_pen', 'real_pen_paren', 'birth_gender', 'published_yn'},
    'work': {'title', 'genre', 'sub_genre', 'rating', 'keywords', 'logline', 'genre_rating', 'adult19_ox', 'title_pen'},
    'pitch': {'intro', 'intent', 'selling', 'target', 'material', 'setting', 'twist', 'when_to_read', 'quote',
              'intent_selling', 'intro_selling', 'intro_intent', 'logline_intent', 'intro_logline', 'intro_chars'},
    'story': {'summary', 'synopsis', 'syn_ki', 'syn_seung', 'syn_crisis', 'syn_jeon', 'syn_gyeol'},
    'volume': {'vol_current', 'vol_total', 'vol_both', 'episodes', 'eps_or_vol', 'complete_date', 'delivery_date',
               'serial_yn', 'serial_site', 'serial_url', 'serial_stats', 'paid_serial', 'platform', 'pub_type',
               'pub_date', 'price', 'notes', 'reference', 'serial_career', 'genre_episodes', 'genre_volume'},
    'check': {'ox_parody', 'ox_incest', 'ox_minor', 'ox_ethics', 'ox_rps', 'ox_published'},
}
TAB_NAMES = {'author': '작가 정보', 'work': '작품 기본 정보', 'pitch': '소개·기획', 'chars': '등장인물',
             'story': '줄거리', 'volume': '분량·연재·출간', 'check': '확인 사항'}


def slot_tab(slot):
    if slot.startswith(('char', 'card_')):
        return 'chars'
    for tab, slots in SLOT_TAB.items():
        if slot in slots:
            return tab
    return None


CSS = """
:root{--bg:#f6f4fa;--card:#fff;--ink:#231f2e;--sub:#6b6680;--line:#e6e1f0;--acc:#6d4fd0;--ok:#1f8a5b;--warn:#b7791f;--bad:#c2410c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 'Malgun Gothic','맑은 고딕',sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:28px 16px 60px}
h1{font-size:24px;margin:0 0 4px}.meta{color:var(--sub);margin-bottom:22px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:24px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.stat b{display:block;font-size:26px}.stat span{color:var(--sub);font-size:13px}
.box{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:22px}
.box h2{font-size:17px;margin:0 0 8px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top;font-size:14px}
th{background:#efebf8;font-weight:600}
.pill{display:inline-block;border-radius:99px;padding:1px 9px;font-size:12px;margin:2px 4px 2px 0;background:#f1eef9}
.pill.warn{background:#fdf3e1;color:#7a4c06}.pill.bad{background:#fde8df;color:#8a2c07}.pill.ok{background:#e3f4ea;color:#14603f}
details{background:var(--card);border:1px solid var(--line);border-radius:12px;margin-bottom:10px}
summary{cursor:pointer;padding:12px 16px;font-weight:600;list-style:none;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
summary::-webkit-details-marker{display:none}
details[open] summary{border-bottom:1px solid var(--line)}
.inner{padding:10px 16px 14px}.inner ul{margin:6px 0 12px;padding-left:20px}.inner li{margin:2px 0}
.file{color:var(--sub);font-weight:400;font-size:13px}
.lab{font-weight:600}.val{color:var(--sub)}
.k{font-size:13px;color:var(--sub);margin:10px 0 2px;font-weight:600}
"""


def _e(s):
    return html.escape(str(s or ''))


def build_report(results, project, out_dir, path=None):
    """results: run_batch 결과 [(entry, report, out_path)]"""
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    ok = [r for r in results if not r[1].error]
    filled = sum(len(r[1].filled) for r in ok)
    nodata = sum(len(r[1].nodata) for r in ok)
    manual = sum(len(r[1].manual) for r in ok)
    errors = [r for r in results if r[1].error]

    # 빈칸이 생긴 이유를 입력 항목별로 모으기 → "이것만 채우면 N개 양식이 더 채워져요"
    missing = {}
    for e, rep, _ in ok:
        for lab, slot in rep.nodata:
            name = SLOT_NAMES.get(slot, slot)
            missing.setdefault(name, {'tab': TAB_NAMES.get(slot_tab(slot), ''), 'forms': set()})
            missing[name]['forms'].add(e.display)
    miss_rows = sorted(missing.items(), key=lambda kv: -len(kv[1]['forms']))

    h = ['<!doctype html><html lang="ko"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         '<title>투고 양식 작성 결과</title><style>%s</style></head><body><div class="wrap">' % CSS,
         '<h1>투고 양식 작성 결과</h1>',
         '<div class="meta">《%s》 · %s · %s</div>' % (_e(project.get('title')), _e(project.get('pen')), now),
         '<div class="stats">',
         '<div class="stat"><b>%d</b><span>만든 양식</span></div>' % len(ok),
         '<div class="stat"><b>%d</b><span>자동으로 채운 칸</span></div>' % filled,
         '<div class="stat"><b>%d</b><span>입력 정보가 없어 빈 칸</span></div>' % nodata,
         '<div class="stat"><b>%d</b><span>직접 확인할 칸</span></div>' % manual,
         '</div>']
    if errors:
        h.append('<div class="box"><h2>⚠ 만들지 못한 양식</h2><ul>')
        for e, rep, _ in errors:
            h.append('<li>%s — %s</li>' % (_e(e.display), _e(rep.error)))
        h.append('</ul></div>')
    if miss_rows:
        h.append('<div class="box"><h2>이 항목을 채우면 빈칸이 줄어요</h2><table><tr><th>입력 항목</th><th>어느 탭</th><th>쓰는 양식</th></tr>')
        for name, info in miss_rows:
            forms = sorted(info['forms'])
            h.append('<tr><td class="lab">%s</td><td>%s</td><td>%d곳 <span class="val">(%s)</span></td></tr>' % (
                _e(name), _e(info['tab']), len(forms), _e(', '.join(forms[:6]) + (' 외' if len(forms) > 6 else ''))))
        h.append('</table></div>')
    h.append('<div class="box"><h2>꼭 확인해 주세요</h2><ul>'
             '<li>원고 본문은 양식에 들어가지 않아요. 출판사 안내대로 원고를 붙이거나 따로 첨부해 주세요.</li>'
             '<li>파일을 한컴오피스로 한 번 열어 보고, 칸 크기·줄바꿈이 괜찮은지 확인한 뒤 저장해 주세요.</li>'
             '<li>PDF 제출을 요구하는 곳은 한컴오피스에서 「PDF로 저장」해 주세요.</li></ul></div>')
    h.append('<h2 style="font-size:18px;margin:26px 0 10px">양식별 상세</h2>')
    for e, rep, out_path in results:
        if rep.error:
            continue
        tags = ['<span class="pill ok">채움 %d</span>' % len(rep.filled)]
        if rep.nodata:
            tags.append('<span class="pill warn">빈칸 %d</span>' % len(rep.nodata))
        if rep.manual:
            tags.append('<span class="pill bad">직접 확인 %d</span>' % len(rep.manual))
        fname = os.path.basename(out_path) if out_path else ''
        h.append('<details><summary>%s %s <span class="file">%s</span></summary><div class="inner">' % (
            _e(e.display), ''.join(tags), _e(fname)))
        sub = getattr(e, 'submit', None) or {}
        if sub.get('methods') or sub.get('guide'):
            names = {'email': '이메일', 'form': '구글 폼', 'site': '홈페이지 접수', 'toogohada': '투고하다'}
            h.append('<div class="k">투고처</div><ul>')
            for m in sub.get('methods') or []:
                href = ('mailto:' + m['value']) if m['type'] == 'email' else m['value']
                warn = ' <span class="pill warn">확인 필요</span>' if m.get('check') else ''
                note = (' <span class="val">%s</span>' % _e(m['note'])) if m.get('note') else ''
                h.append('<li><span class="lab">%s</span> <a href="%s">%s</a>%s%s</li>' % (
                    _e(names.get(m['type'], m['type'])), _e(href), _e(m['value']), warn, note))
            if sub.get('guide'):
                h.append('<li><span class="lab">안내 글</span> <a href="%s">%s</a></li>' % (
                    _e(sub['guide']), _e(sub['guide'][:70])))
            h.append('</ul>')
        if rep.manual:
            h.append('<div class="k">직접 확인할 칸</div><ul>')
            for lab, why in rep.manual:
                h.append('<li><span class="lab">%s</span> — %s</li>' % (_e(lab), _e(why)))
            h.append('</ul>')
        if rep.nodata:
            h.append('<div class="k">입력 정보가 없어 비워 둔 칸</div><ul>')
            for lab, slot in rep.nodata:
                tab = TAB_NAMES.get(slot_tab(slot), '')
                h.append('<li><span class="lab">%s</span> <span class="val">→ 「%s」%s</span></li>' % (
                    _e(lab), _e(SLOT_NAMES.get(slot, slot)), (' (%s 탭)' % _e(tab)) if tab else ''))
            h.append('</ul>')
        if rep.warnings:
            h.append('<div class="k">참고</div><ul>')
            for w in rep.warnings:
                h.append('<li>%s</li>' % _e(w))
            h.append('</ul>')
        if rep.notes:
            h.append('<div class="k">출판사 투고 안내 (양식에서 발췌)</div><ul>')
            for n in rep.notes:
                h.append('<li>%s</li>' % _e(n))
            h.append('</ul>')
        h.append('<div class="k">채운 칸</div><ul>')
        for lab, slot, prev in rep.filled:
            h.append('<li><span class="lab">%s</span> <span class="val">← %s</span></li>' % (_e(lab), _e(prev)))
        h.append('</ul></div></details>')
    h.append('</div></body></html>')
    path = path or os.path.join(out_dir, '결과_보고서.html')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(h))
    return path
