# -*- coding: utf-8 -*-
"""자동 업데이트: GitHub에 올린 manifest.json을 읽어 양식 묶음·프로그램 새 버전을 확인한다.

manifest.json 모양
{
  "app":  {"version": "2.3", "date": "2026-11-28", "notes": ["..."],
           "page": "https://github.com/<사용자>/<저장소>/releases/latest",
           "windows": {"url": "...TugoWriter-Setup-2.3.exe", "sha256": "..."},
           "mac":     {"url": "...TugoWriter-2.3.dmg", "sha256": "..."}},
  "data": {"version": "2026-11-28", "url": ".../update/forms_bundle.zip", "sha256": "...", "size": 123,
           "notes": "..."}
}
- 받은 파일은 sha256이 맞을 때만 쓴다.
- 주소는 GitHub 도메인만 허용한다.
- 프로그램 설치 파일은 받기만 하고, 실행은 사용자가 누를 때만 한다(화면 쪽에서 처리).
"""
import hashlib
import json
import os
import re
import ssl
import sys
import tempfile
import urllib.parse
import urllib.request

ALLOWED = ('github.com', 'raw.githubusercontent.com', 'objects.githubusercontent.com',
           'release-assets.githubusercontent.com', 'githubusercontent.com')
UA = 'tugo-writer-updater'


class UpdateError(Exception):
    pass


def _check_url(url):
    p = urllib.parse.urlparse(url or '')
    host = (p.hostname or '').lower()
    if p.scheme != 'https' or not any(host == h or host.endswith('.' + h) for h in ALLOWED):
        raise UpdateError('허용되지 않은 주소: %s' % url)


def _ssl_context():
    """맥용 앱은 시스템 인증서와 연결돼 있지 않아 https가 실패한다. 함께 넣은 certifi 인증서 묶음을 쓴다.
    (윈도우는 시스템 인증서 저장소를 그대로 쓰므로 기본값)"""
    if sys.platform != 'darwin':
        return None
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


def version_tuple(v):
    """'2.3' / '2026-11-28' → 비교 가능한 숫자 튜플"""
    return tuple(int(x) for x in re.findall(r'\d+', str(v or '0')))


def is_newer(remote, local):
    return version_tuple(remote) > version_tuple(local)


def source_url(app_dir, bundle_dir=None):
    """업데이트 확인 주소: 실행 파일 옆 update_source.json → 프로그램 안에 넣은 것 순서로 찾는다."""
    for base in (app_dir, bundle_dir):
        if not base:
            continue
        p = os.path.join(base, 'update_source.json')
        if os.path.exists(p):
            try:
                with open(p, encoding='utf-8') as f:
                    url = json.load(f).get('manifest', '')
                if url:
                    return url
            except (OSError, ValueError):
                pass
    return ''


def fetch_manifest(url, timeout=8):
    _check_url(url)
    # GitHub raw 캐시를 피하려고 시각을 붙인다
    sep = '&' if '?' in url else '?'
    req = urllib.request.Request('%s%st=%d' % (url, sep, int(__import__('time').time() // 300)),
                                 headers={'User-Agent': UA, 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r:
        data = json.loads(r.read().decode('utf-8-sig'))
    if not isinstance(data, dict):
        raise UpdateError('manifest 형식이 아니에요')
    return data


def download(url, dest, sha256=None, progress=None, timeout=30):
    """url을 dest로 받는다. sha256이 다르면 지우고 오류."""
    _check_url(url)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    h = hashlib.sha256()
    fd, tmp = tempfile.mkstemp(prefix='.dl_', dir=os.path.dirname(dest))
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r, os.fdopen(fd, 'wb') as f:
            _check_url(r.geturl())          # 다른 곳으로 넘겨졌어도 GitHub 안이어야 함
            total = int(r.headers.get('Content-Length') or 0)
            done = 0
            while True:
                chunk = r.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        if sha256 and h.hexdigest().lower() != sha256.lower():
            raise UpdateError('받은 파일이 손상됐어요(확인값 불일치)')
        os.replace(tmp, dest)
        return dest
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def platform_key():
    return 'mac' if sys.platform == 'darwin' else 'windows'


def check(manifest_url, app_version, data_version):
    """→ {'app': {...}|None, 'data': {...}|None} (새것만)"""
    m = fetch_manifest(manifest_url)
    out = {'app': None, 'data': None, 'manifest': m}
    app = m.get('app') or {}
    if app.get('version') and is_newer(app['version'], app_version):
        out['app'] = app
    data = m.get('data') or {}
    if data.get('version') and data.get('url') and is_newer(data['version'], data_version or '0'):
        out['data'] = data
    return out
