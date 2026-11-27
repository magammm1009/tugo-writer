# -*- coding: utf-8 -*-
"""모든 양식을 예시 데이터로 채워 보고, 결과 파일이 깨지지 않았는지 검사한다.

사용: python tests/run_all.py <양식 zip 또는 폴더> <결과 폴더> [프로젝트.json]
"""
import io
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from lxml import etree  # noqa: E402

from tugo.forms import load_forms, run_batch  # noqa: E402
from tugo.engine import describe_slot  # noqa: E402


def check_hwpx(path):
    problems = []
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        if infos[0].filename != 'mimetype' or infos[0].compress_type != zipfile.ZIP_STORED:
            problems.append('mimetype 위치/압축')
        for i in infos:
            if i.filename.startswith('Contents/section'):
                raw = z.read(i)
                try:
                    etree.fromstring(raw)
                except etree.XMLSyntaxError as ex:
                    problems.append('XML 오류 %s: %s' % (i.filename, ex))
                if b'ns0:' in raw or b'xmlns:ns' in raw:
                    problems.append('이상한 네임스페이스 접두어')
    return problems


def main():
    src, out = sys.argv[1], sys.argv[2]
    proj_path = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(HERE), '예시_작품.json')
    with open(proj_path, encoding='utf-8') as f:
        project = json.load(f)
    entries = load_forms(src)
    print('양식 수:', len(entries))
    results = run_batch(entries, project, out)
    tot_f = tot_n = tot_m = 0
    lines = []
    bad = 0
    for e, rep, path in results:
        if rep.error:
            bad += 1
            lines.append('!! %s  ERROR %s' % (e.display, rep.error))
            continue
        probs = check_hwpx(path) if path else ['파일 없음']
        if probs:
            bad += 1
        tot_f += len(rep.filled)
        tot_n += len(rep.nodata)
        tot_m += len(rep.manual)
        lines.append('== %s | %s -> %s' % (e.display, e.filename, os.path.basename(path or '')))
        lines.append('   채움 %d / 정보없음 %d / 직접확인 %d %s' % (len(rep.filled), len(rep.nodata), len(rep.manual),
                                                         ('  문제: ' + ', '.join(probs)) if probs else ''))
        for lab, slot, prev in rep.filled:
            lines.append('     + [%s] %s => %s' % (describe_slot(slot), lab, prev))
        for lab, slot in rep.nodata:
            lines.append('     - [%s] %s (정보 없음)' % (describe_slot(slot), lab))
        for lab, why in rep.manual:
            lines.append('     ? %s : %s' % (lab, why))
        for w in rep.warnings:
            lines.append('     ! %s' % w)
    lines.append('')
    lines.append('합계: 채움 %d, 정보없음 %d, 직접확인 %d, 문제 파일 %d' % (tot_f, tot_n, tot_m, bad))
    with open(os.path.join(out, '_test_summary.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(lines[-1])


if __name__ == '__main__':
    main()
