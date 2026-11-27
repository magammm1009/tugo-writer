# -*- coding: utf-8 -*-
"""화면 자동 점검: 창을 띄워 모든 단계를 열어 보고, 양식을 읽어 실제로 만들어 본 뒤 닫는다."""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import app as A
from tkinter import messagebox
messagebox.askyesno = lambda *a, **k: False
messagebox.showinfo = messagebox.showwarning = lambda *a, **k: None
errors = []
messagebox.showerror = lambda *a, **k: errors.append(a)
A.AUTOSAVE = os.path.join(sys.argv[2], 'autosave.json')
A.SETTINGS = os.path.join(sys.argv[2], 'settings.json')
app = A.App()
app.report_callback_exception = lambda *a: errors.append(a)
proj = json.load(open(os.path.join(ROOT, '예시_작품.json'), encoding='utf-8'))
app.project.update(proj)
app.load_into_widgets()
for i in range(len(A.F.STEPS)):
    app.show_step(i); app.update()
# 입력 변경이 프로젝트에 반영되는지
app.vars['title'][1]('테스트 제목'); app.update()
assert app.project['title'] == '테스트 제목', app.project['title']
app.vars['intro'][1]('소개 한 줄'); app.vars['intro'][1]
app.char_list.selection_clear(0, 'end'); app.char_list.selection_set(1); app.char_select(); app.char_vars['age'][1]('30'); app.update()
assert app.project['characters'][1]['age'] == '30'
app.out_var.set(sys.argv[2])
app.load_forms_async(sys.argv[1])
t0 = time.time()
while (not app.forms or not app.usage) and time.time() - t0 < 120:
    app.update(); time.sleep(0.05)
print('forms', len(app.forms), 'usage keys', len(app.usage), 'pen usage', app.usage.get('pen'), 'took %.1fs' % (time.time()-t0))
app.tree.selection_set(app.forms[0].key); app.preview(); app.update()
app.run()
t0 = time.time()
while app.results is None and time.time() - t0 < 120:
    app.update(); time.sleep(0.05)
print('results', len(app.results or []), 'out', app.last_out, 'report', os.path.exists(app.last_report or ''))
print('status:', app.run_status.cget('text'))
print('errors:', errors)
app.on_close()
