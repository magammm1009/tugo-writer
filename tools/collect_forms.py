# -*- coding: utf-8 -*-
"""투고하다 레이블 정보(toogo_crawl.py 결과)를 바탕으로 출판사 공식 양식 파일 후보를 찾는다.

출처 우선순위
 1) 투고하다에 출판사가 직접 올린 첨부파일
 2) 투고하다에 연결된 네이버 블로그 글의 첨부파일
 3) 연결된 블로그 홈이면, 제목에 '투고'가 들어간 최근 글의 첨부파일
 4) 연결된 홈페이지에 바로 걸린 hwp/hwpx/docx 링크
공개된 페이지만 읽고 로그인·우회는 하지 않는다. 요청 사이 1초 쉰다.

사용: python tools/collect_forms.py <toogo.json> <manifest.json>
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) tugo-form-collector'
EXT = re.compile(r'\.(hwpx|hwp|docx|doc)$', re.I)
FORMISH = re.compile(r'양식|시놉|기획|투고|synop|form|서식|원고|script|writer|hangeul|word', re.I)


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Referer': 'https://blog.naver.com/'})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    time.sleep(1.0)
    return data.decode('utf-8', 'replace')


def fname_from_url(u):
    return urllib.parse.unquote(u.split('?')[0].rsplit('/', 1)[-1])


def naver_ids(u):
    p = urllib.parse.urlparse(u)
    if 'blog.naver.com' not in p.netloc:
        return None, None
    q = urllib.parse.parse_qs(p.query)
    if 'blogId' in q:
        return q['blogId'][0], (q.get('logNo') or [None])[0]
    parts = [x for x in p.path.split('/') if x]
    if not parts:
        return None, None
    return parts[0], (parts[1] if len(parts) > 1 and parts[1].isdigit() else None)


def post_files(blog, log):
    url = 'https://blog.naver.com/PostView.naver?blogId=%s&logNo=%s' % (blog, log)
    page = get(url)
    out = []
    for raw in re.findall(r"data-linkdata='([^']+)'", page):
        try:
            d = json.loads(html.unescape(raw))
        except ValueError:
            continue
        link = d.get('link') or ''
        if 'download.blog.naver.com' in link or 'blogattach' in link:
            name = fname_from_url(link)
            if EXT.search(name):
                out.append({'name': name, 'url': link, 'source': url})
    m = re.search(r'<title>(.*?)</title>', page, re.S)
    title = html.unescape(m.group(1)).strip() if m else ''
    return out, title


def recent_tugo_posts(blog, limit=3):
    url = ('https://blog.naver.com/PostTitleListAsync.naver?blogId=%s&viewdate=&currentPage=1&categoryNo=0'
           '&parentCategoryNo=&countPerPage=30' % blog)
    try:
        t = get(url)
        data = json.loads(t.replace("\\'", "'"))
    except Exception:
        return []
    posts = []
    for p in data.get('postList', []):
        title = urllib.parse.unquote_plus(p.get('title', ''))
        if re.search(r'투고|원고 모집|원고모집|공모', title):
            posts.append((p['logNo'], html.unescape(title)))
    return posts[:limit]


def site_files(url):
    try:
        page = get(url)
    except Exception:
        return []
    out = []
    for h in re.findall(r'href=["\']([^"\']+)["\']', page):
        full = urllib.parse.urljoin(url, html.unescape(h))
        name = fname_from_url(full)
        if EXT.search(name):
            out.append({'name': name, 'url': full, 'source': url})
    return out


def main():
    labels = json.load(open(sys.argv[1], encoding='utf-8'))
    manifest = []
    seen_posts = {}
    for x in labels:
        heads = [h for h in x.get('heads', []) if h]
        rec = {'pid': x['pid'], 'lid': x['lid'], 'publisher': heads[0] if heads else '',
               'label': heads[1] if len(heads) > 1 else '', 'genres': x['genres'], 'toogo': x['url'],
               'files': [], 'checked': [], 'core': x.get('core', '')}
        for name, href in x.get('files', []):
            name = urllib.parse.unquote(name)
            if '%' in name or name == '도서출판':
                name = fname_from_url(href)
            if EXT.search(name):
                rec['files'].append({'name': name, 'url': href, 'source': 'toogohada(출판사 직접 제공)'})
        if not rec['files']:
            for link in x.get('links', []):
                if 'notion' in link:
                    continue
                blog, log = naver_ids(link)
                try:
                    if blog and log:
                        key = (blog, log)
                        if key not in seen_posts:
                            seen_posts[key] = post_files(blog, log)
                        files, title = seen_posts[key]
                        rec['checked'].append('blog post: %s/%s %s' % (blog, log, title[:40]))
                        rec['files'] += files
                    elif blog:
                        for log2, title in recent_tugo_posts(blog):
                            key = (blog, log2)
                            if key not in seen_posts:
                                seen_posts[key] = post_files(blog, log2)
                            files, _ = seen_posts[key]
                            rec['checked'].append('blog search: %s/%s %s' % (blog, log2, title[:40]))
                            if files:
                                rec['files'] += files
                                break
                    elif link.startswith('http'):
                        rec['checked'].append('site: ' + link)
                        rec['files'] += site_files(link)
                except Exception as ex:
                    rec['checked'].append('error %s: %s' % (link, ex))
        # 같은 이름 중복 제거, 양식다운 이름 우선
        uniq = {}
        for f in rec['files']:
            uniq.setdefault(f['name'], f)
        rec['files'] = sorted(uniq.values(), key=lambda f: (not FORMISH.search(f['name']), f['name']))
        manifest.append(rec)
        print(len(manifest), rec['publisher'], rec['label'], len(rec['files']), file=sys.stderr)
    with open(sys.argv[2], 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
