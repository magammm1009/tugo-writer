# -*- coding: utf-8 -*-
"""투고하다(toogohada.com) 레이블 상세 페이지에서 투고 안내·양식 링크를 모은다.

사용: python tools/toogo_crawl.py tools/toogo_ids.txt <결과.json>
- 공개 페이지만 읽고, 로그인·우회는 하지 않는다. 요청 사이 1초 쉰다.
"""
import json
import re
import sys
import time
import urllib.request

from lxml import html

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) tugo-form-collector'
GENRE = {'R': '로맨스', 'F': '로맨스판타지', 'M': '현대로맨스', 'S': '19단편'}
SNS = re.compile(r'twitter\.com|//x\.com|instagram|facebook|youtube|pf\.kakao|apps\.apple|play\.google|toogohada\.com')


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', 'replace')


def parse(pid, lid, page):
    raw_files = []
    # 출판사가 직접 올린 첨부파일: 페이지 안 데이터의 "attachments":[{"name":..,"href":..}]
    for name, href in re.findall(r'\\"name\\":\\"([^"\\]+)\\",\\"href\\":\\"(https://[^"\\]+)\\"', page):
        if (name, href) not in raw_files:
            raw_files.append((name, href))
    for u in re.findall(r'https?://[^"\'\s<>]*?/attp/[^"\'\s<>\\]+', page):
        if u not in [h for _, h in raw_files]:
            raw_files.append((u.rsplit('/', 1)[-1], u))
    doc = html.fromstring(page)
    for bad in doc.xpath('//style|//script'):
        bad.drop_tree()
    text = re.sub(r'\s+', ' ', doc.text_content())
    s = text.find('출판사 직접 제공')
    e = text.find('레이블 선택')
    core = text[s:e] if s >= 0 else ''
    title = (doc.xpath('//title/text()') or [''])[0]
    links = []
    for a in doc.xpath('//a[@href]'):
        h = a.get('href')
        if h.startswith('http') and not SNS.search(h) and h not in links:
            links.append(h)
    files = [[n, h] for n, h in raw_files]
    for h in links:
        if re.search(r'\.(hwpx?|docx?|pdf|zip)(\?|$)', h, re.I) and h not in [x[1] for x in files]:
            files.append([h.rsplit('/', 1)[-1], h])
    attach_names = re.findall(r'첨부파일(.+?)(?:레이블 선택|$)', text[:20000])
    mails = sorted({m for m in re.findall(r'[\w.\-]+@[\w\-]+(?:\.[\w\-]+)+', page)
                    if not re.search(r'toogohada|sentry|example|u003e', m)})
    # 레이블 이름: '레이블 선택' 앞부분의 현재 이름은 h 태그에서
    heads = [re.sub(r'\s+', ' ', h.text_content()).strip() for h in doc.xpath('//h1|//h2|//h3|//h4|//h5|//h6')]
    return {
        'pid': pid, 'lid': lid, 'title': title, 'heads': heads[:6],
        'open': '투고 받는 중' in text, 'core': core[:600], 'links': links, 'files': files, 'mails': mails,
        'attach_names': attach_names[:1],
    }


def main():
    ids = open(sys.argv[1], encoding='utf-8').read().strip().split(',')
    out = []
    for item in ids:
        m = re.match(r'(\d+)\.(\d+)([RFMS]+)', item.strip())
        pid, lid, gs = m.group(1), m.group(2), m.group(3)
        url = 'https://toogohada.com/publisher/%s/label/%s' % (pid, lid)
        try:
            rec = parse(pid, lid, get(url))
        except Exception as ex:
            rec = {'pid': pid, 'lid': lid, 'error': str(ex)}
        rec['genres'] = [GENRE[c] for c in gs]
        rec['url'] = url
        out.append(rec)
        print(len(out), pid, lid, len(rec.get('files', [])), file=sys.stderr)
        time.sleep(1.0)
    with open(sys.argv[2], 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
