# -*- coding: utf-8 -*-
"""양식 묶음(양식목록.json)의 레이블마다 투고처(이메일·구글 폼·자체 사이트·투고하다 폼)를 찾는다.

출처 우선순위
 1) 투고하다 레이블 페이지의 「투고처」 칸 (출판사가 직접 쓴 내용)
 2) 투고하다 자체 투고 폼 사용 여부(togoForm)
 3) 양식 파일 안내문에 적힌 '투고' 이메일·주소
 4) 투고 안내 글 주소(source / 블로그)
공개 페이지만 읽고, 요청 사이 1초 쉰다.

사용: python tools/collect_submit.py <양식목록.json> <양식 묶음 zip> <출력 투고처.json>
"""
import html
import json
import re
import sys
import time
import urllib.request
import zipfile

sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
from tugo.engine import HwpxDoc, para_text  # noqa: E402

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) tugo-form-collector'
EMAIL = re.compile(r'[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+')
URL = re.compile(r'https?://[^\s"\'<>()\\]+')
FORM_HOST = re.compile(r'forms\.gle|docs\.google\.com/forms|naver\.me|form\.naver|typeform|tally\.so|walla\.my')


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read().decode('utf-8', 'replace')
    time.sleep(1.0)
    return data


def key(s):
    s = (s or '').lower().replace('(주)', '').replace('주식회사', '')
    return re.sub(r'[^0-9a-z가-힣]', '', s)


def unescape_page(p):
    return html.unescape(p.replace('\\"', '"').replace('\\u003c', '<').replace('\\u003e', '>')
                         .replace('\\u0026', '&').replace('\\\\', '\\'))


def label_info(pid, lid):
    url = 'https://toogohada.com/publisher/%s/label/%s' % (pid, lid)
    page = get(url)
    q = unescape_page(page)
    info = {'toogo': url}
    # 화면에 그려진 「투고처」 상자(TogoContent)
    from lxml import html as lhtml
    doc = lhtml.fromstring(page)
    for bad in doc.xpath('//style|//script'):
        bad.drop_tree()
    info['emails'], info['urls'] = [], []
    for box in doc.xpath('//div[contains(@class,"TogoContent")]'):
        head = box.getprevious()
        if head is None or re.sub(r'\s', '', head.text_content()) != '투고처':
            continue
        info['raw'] = re.sub(r'\s+', ' ', box.text_content()).strip()[:300]
        hrefs = [a.get('href') for a in box.xpath('.//a[@href]')]
        info['emails'] = sorted(set([h[7:] for h in hrefs if h.lower().startswith('mailto:')] +
                                    EMAIL.findall(info['raw'])))
        info['urls'] = [h for h in dict.fromkeys(hrefs) if h.startswith('http')]
        break
    # 데이터의 method 목록: [{"property":"email"|"link", "content": ...}] — 출판사가 등록한 값
    mm = re.search(r'"id":%s,"name":"[^"]*","method":(\[.*?\])' % lid, q)
    if mm:
        info['method'] = [{'property': a, 'content': b.strip()} for a, b in
                          re.findall(r'"property":"([^"]+)","content":"([^"]*)"', mm.group(1))]
    # 기타사항 글 속 '투고처: …' (조아라처럼 안내문에 적은 경우)
    if not info.get('emails') and not info.get('urls'):
        m2 = re.search(r'투고\s*처[^<]{0,20}(?:<[^>]+>)*\s*([^<]{0,80})', q)
        seg = q[m2.start(): m2.start() + 400] if m2 else ''
        em = EMAIL.findall(seg)
        if em:
            info['emails'] = sorted(set(em))
            info['raw'] = (info.get('raw') or '') + ' [기타사항] ' + re.sub(r'<[^>]+>', ' ', seg)[:120]
    # 현재 레이블 블록에서만 togoForm / source / togoStatus 읽기
    blk = q[q.find('"id":%s,' % lid):] if ('"id":%s,' % lid) in q else q
    for k in ('togoForm', 'source', 'togoStatus'):
        mm = re.search(r'"%s":("([^"]*)"|null|\d+)' % k, blk)
        if mm:
            info[k] = mm.group(2) if mm.group(2) is not None else (None if mm.group(1) == 'null' else mm.group(1))
    return info


def form_text_contacts(zf, files):
    """양식 안내문에서 '투고'와 함께 적힌 이메일·주소"""
    emails, urls = [], []
    for f in files:
        try:
            doc = HwpxDoc(zf.read(f))
        except Exception:
            continue
        lines = [para_text(p) for _, p in doc.body]
        for t in doc.tables:
            for c in t.cells:
                lines += c.lines
        for ln in lines:
            if not re.search(r'투고|접수|보내|제출', ln) or re.search(r'문의', ln):
                continue
            emails += EMAIL.findall(ln)
            urls += [u.rstrip('.,') for u in URL.findall(ln) if FORM_HOST.search(u)]
    return list(dict.fromkeys(emails)), list(dict.fromkeys(urls))


def blog_contacts(url):
    """네이버 블로그 안내 글에서 '투고/접수/보내' 줄에 있는 이메일·폼 주소(문의용 줄은 제외)"""
    m = re.search(r'blog\.naver\.com/(?:PostView\.naver\?blogId=)?([\w\-]+)[/&](?:logNo=)?(\d{6,})', url or '')
    if not m:
        return [], []
    page = get('https://blog.naver.com/PostView.naver?blogId=%s&logNo=%s' % (m.group(1), m.group(2)))
    from lxml import html as lhtml
    doc = lhtml.fromstring(page)
    main = doc.xpath('//div[contains(@class,"se-main-container")]') or doc.xpath('//div[@id="postViewArea"]')
    if not main:
        return [], []
    hrefs = [a.get('href') or '' for a in main[0].xpath('.//a[@href]')]
    lines = [re.sub(r'\s+', ' ', p.text_content()).strip() for p in main[0].xpath('.//p|.//li|.//td')]
    emails, urls = [], []
    for ln in lines:
        if re.search(r'투고|접수|보내|제출|원고', ln) and not re.search(r'문의|질문', ln):
            emails += EMAIL.findall(ln)
            urls += [u.rstrip('.,') for u in URL.findall(ln) if FORM_HOST.search(u)]
    urls += [h for h in hrefs if FORM_HOST.search(h)]
    return list(dict.fromkeys(emails)), list(dict.fromkeys(urls))


VALID_EMAIL = re.compile(r'[A-Za-z0-9][\w.+\-]*@[\w\-]+(?:\.[\w\-]+)+')


def finalize(rec):
    """여러 출처를 하나의 투고처 목록으로: methods=[{type,value,note,check}]"""
    methods, origin = [], ''

    def add(kind, value, note=''):
        value = (value or '').strip()
        if not value or any(m['value'] == value for m in methods):
            return
        check = False
        if kind == 'email':
            mm = VALID_EMAIL.search(value)
            if not mm:
                return
            check = mm.group(0) != value.strip(' :') and not note
            value = mm.group(0)
        methods.append({'type': kind, 'value': value, 'note': note, 'check': check})

    for m in rec.get('method', []):
        c = m['content']
        if c.startswith('http'):
            add('form' if FORM_HOST.search(c) else 'site', c)
        else:
            e = VALID_EMAIL.search(c)
            note = c[:e.start()].strip(' :') if e else ''
            if e and e.start() > 0 and not re.search(r'[0-9A-Za-z가-힣]', note):
                note = '등록된 주소가 「%s」라 확인 필요' % c.strip()
            if e:
                add('email', e.group(0), note)
                if c.strip() != e.group(0) and '확인 필요' in note:
                    methods[-1]['check'] = True
    if methods:
        origin = '투고하다(출판사 등록 정보)'
    if rec.get('togoForm'):
        methods.append({'type': 'toogohada', 'value': rec['toogo'], 'note': '투고하다 「투고하기」 버튼', 'check': False})
        origin = origin or '투고하다(출판사 등록 정보)'
    if not methods:
        for e in rec.get('form_emails', []):
            add('email', e)
        for u in rec.get('form_urls', []):
            add('form', u)
        if methods:
            origin = '양식 파일 안내문'
    if not methods:
        for e in rec.get('blog_emails', []):
            add('email', e)
        for u in rec.get('blog_urls', []):
            add('form' if FORM_HOST.search(u) else 'site', u)
        if methods:
            origin = '출판사 블로그 안내 글'
    guide = rec.get('source') if (rec.get('source') or '').startswith('http') else (rec.get('csv_source') or '')
    if not guide.startswith('http'):
        guide = rec.get('toogo', '')
    return {'dir': rec['dir'], 'publisher': rec['publisher'], 'label': rec['label'], 'methods': methods,
            'origin': origin, 'guide': guide, 'toogo': rec.get('toogo', '')}


def main():
    index = json.load(open(sys.argv[1], encoding='utf-8'))
    zf = zipfile.ZipFile(sys.argv[2])
    names = [i.filename for i in zf.infolist()]
    pubs = json.loads(get('https://toogohada.com/api/publisher/labels'))['data']
    # 출판사 번호 → 그 출판사의 아무 레이블 번호(목록 화면에서 모은 것: tools/toogo_publishers.txt)
    here = __import__('os').path.dirname(__import__('os').path.abspath(__file__))
    any_label = dict(x.split('.') for x in open(__import__('os').path.join(here, 'toogo_publishers.txt'),
                                               encoding='utf-8').read().strip().split(','))
    pub_by_key = {key(p['name']): p for p in pubs}
    cache_labellist = {}
    csv_src = {}
    for n in names:
        if n.endswith('다운로드_목록.csv'):
            import csv
            import io
            for row in csv.DictReader(io.StringIO(zf.read(n).decode('utf-8-sig', 'replace'))):
                try:
                    csv_src[int(row.get('XLSX 대상 순서', '').strip())] = (row.get('공식 출처') or '').strip()
                except ValueError:
                    pass
    out = []
    for g in index['groups']:
        rec = {'dir': g['dir'], 'publisher': g['publisher'], 'label': g['label']}
        # 투고하다 출판사 찾기
        pk = key(g['publisher'])
        pub = pub_by_key.get(pk) or next((p for k, p in pub_by_key.items() if pk and (pk in k or k in pk)), None)
        lid = None
        pid = None
        if g.get('url'):
            m = re.search(r'/publisher/(\d+)/label/(\d+)', g['url'])
            if m:
                pid, lid = m.group(1), m.group(2)
        if lid is None and pub:
            pid = str(pub['id'])
            if pid not in cache_labellist and pid in any_label:
                page = unescape_page(get('https://toogohada.com/publisher/%s/label/%s' % (pid, any_label[pid])))
                ll = re.search(r'"labelList":(\[.*?\])\s*,\s*"', page)
                lst = []
                if ll:
                    for mm in re.finditer(r'\{"id":(\d+),"name":"([^"]+)"', ll.group(1)):
                        lst.append((mm.group(1), mm.group(2)))
                cache_labellist[pid] = lst
            lk = key(g['label'])
            for i, n in cache_labellist.get(pid, []):
                if key(n) == lk or (lk and (lk in key(n) or key(n) in lk)):
                    lid = i
                    break
        if lid:
            try:
                rec.update(label_info(pid, lid))
            except Exception as ex:
                rec['error'] = str(ex)
        files = [n for n in names if n.startswith('투고양식_묶음_202611/' + g['dir'] + '/') and n.endswith('.hwpx')]
        fe, fu = form_text_contacts(zf, files)
        rec['form_emails'], rec['form_urls'] = fe, fu
        # 기존 BL 묶음의 '공식 출처'(다운로드_목록.csv)
        mnum = re.match(r'BL/(\d+)_', g['dir'])
        if mnum and int(mnum.group(1)) in csv_src:
            rec['csv_source'] = csv_src[int(mnum.group(1))]
        if not rec.get('method') and not rec.get('togoForm') and not fe and not fu:
            for u in (rec.get('source'), rec.get('csv_source')):
                if u and 'blog.naver.com' in u:
                    try:
                        be, bu = blog_contacts(u)
                    except Exception:
                        be, bu = [], []
                    if be or bu:
                        rec['blog_emails'], rec['blog_urls'] = be, bu
                        break
        out.append(rec)
        print(len(out), g['publisher'], g['label'], 'lid=%s' % lid, rec.get('togoForm'), file=sys.stderr)
    json.dump(out, open(sys.argv[3] + '.raw.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    final = {'checked': __import__('datetime').date.today().isoformat(),
             'note': '투고처는 출판사 사정에 따라 바뀔 수 있음. 보내기 전에 안내 글(guide)을 한 번 확인할 것.',
             'labels': [finalize(r) for r in out]}
    # 투고처를 못 찾은 레이블: 같은 출판사 다른 레이블의 투고처를 '확인 필요'로 빌려 온다
    by_pub = {}
    for lab in final['labels']:
        if lab['methods']:
            by_pub.setdefault(key(lab['publisher']), lab)
    for lab in final['labels']:
        if not lab['methods'] and key(lab['publisher']) in by_pub:
            src = by_pub[key(lab['publisher'])]
            lab['methods'] = [dict(m, check=True, note=('같은 출판사 「%s」 레이블 기준' % src['label'])
                                   + (' · ' + m['note'] if m['note'] else '')) for m in src['methods']]
            lab['origin'] = '같은 출판사 다른 레이블(확인 필요)'
    json.dump(final, open(sys.argv[3], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
