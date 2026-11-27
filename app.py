# -*- coding: utf-8 -*-
"""BL 투고 양식 자동 작성기 v2 — 화면(GUI)

내용을 한 번 입력하면 출판사별 투고 양식(HWPX)을 한꺼번에 채워 준다.
"""
import copy
import datetime
import glob
import json
import os
import queue
import re
import sys
import threading
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, ttk

if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, APP_DIR)

from tugo import fields as F  # noqa: E402
from tugo.engine import fill_hwpx  # noqa: E402
from tugo.forms import GENRE_ORDER, bundle_version, load_forms, run_batch  # noqa: E402
from tugo import updater as UP  # noqa: E402
from tugo.report import build_report  # noqa: E402

APP_NAME = '투고 양식 자동 작성기'
GENRE_TABS = [g for g in GENRE_ORDER if g != 'GL']
VERSION = '2.3'
IS_MAC = sys.platform == 'darwin'
if IS_MAC:
    DATA_DIR = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'BL투고양식작성기')
else:
    DATA_DIR = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'BL투고양식작성기')
FORMS_DIR = os.path.join(DATA_DIR, 'forms')          # 자동 업데이트로 받은 양식 묶음
BUNDLE_DIR = getattr(sys, '_MEIPASS', APP_DIR)       # 프로그램 안에 함께 넣은 파일
AUTOSAVE = os.path.join(DATA_DIR, 'autosave.json')
SETTINGS = os.path.join(DATA_DIR, 'settings.json')

# ---- 색·글꼴 ----
from tugo import theme as TH  # noqa: E402


def apply_theme(accent):
    """포인트 색으로 화면 색(모듈 전역 상수)을 바꾼다. 화면은 다시 그려야 반영된다."""
    globals().update(TH.palette(accent))


apply_theme(TH.DEFAULT)
FONT_FAMILY = 'Apple SD Gothic Neo' if IS_MAC else '맑은 고딕'


def F_(size=10, weight='normal'):
    return (FONT_FAMILY, size, weight)


def read_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def open_path(path):
    try:
        os.startfile(path)  # type: ignore[attr-defined]
    except AttributeError:
        import subprocess
        subprocess.Popen(['xdg-open' if sys.platform.startswith('linux') else 'open', path])


def full_sample_project():
    """양식 분석용: 모든 칸을 채운 가짜 데이터(어떤 입력 항목이 몇 개 양식에 쓰이는지 세기 위함)"""
    p = F.empty_project()
    for k in list(p):
        if not k.startswith('_') and k != 'characters':
            p[k] = '가'
    p.update({'rating': '19세 이용가', 'status': '집필 중', 'serial_status': '연재 중', 'author_type': '기성',
              'cur_space': '100000', 'cur_nospace': '80000', 'tot_space': '400000', 'tot_nospace': '300000',
              'cur_eps': '20', 'tot_eps': '100'})
    for k in ('ox_parody', 'ox_incest', 'ox_minor', 'ox_ethics', 'ox_rps', 'ox_published'):
        p[k] = 'X'
    p['characters'] = [
        {'name': n, 'kind': kd, 'pos': ps, 'age': '20', 'gender': '남', 'intro': '가', 'appearance': '가',
         'personality': '가', 'extra': '가', 'goal': '가', 'backstory': '가'}
        for n, kd, ps in (('가', '주연', '공'), ('나', '주연', '수'), ('다', '조연', ''), ('라', '조연', ''))]
    return p


# ===========================================================================
# 스크롤 되는 영역
# ===========================================================================
class ScrollArea(tk.Frame):
    def __init__(self, master, **kw):
        super().__init__(master, bg=BG, **kw)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        self.vsb = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor='nw')
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.vsb.pack(side='right', fill='y')
        self.inner.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        # 1픽셀 단위로 움직여서 부드럽게 스크롤
        self.canvas.configure(yscrollincrement=1)
        self._pending = 0.0
        self._anim = None
        try:
            self._step = int(70 * max(1.0, float(self.tk.call('tk', 'scaling')) / 1.3333))
        except Exception:
            self._step = 70
        ScrollArea.instances.append(self)
        if not ScrollArea._bound:
            # 휠·포커스 처리는 앱 전체에 한 번만 묶고, 지금 살아 있는 스크롤 영역에 나눠 준다
            # (테마를 바꿔 화면을 다시 그려도 예전 영역이 반응하지 않게)
            self.bind_all('<MouseWheel>', ScrollArea._on_wheel, add='+')
            self.bind_all('<FocusIn>', ScrollArea._on_focus, add='+')
            ScrollArea._bound = True

    instances = []
    _bound = False

    @classmethod
    def _owner(cls, w):
        try:
            path = str(w)
        except Exception:
            return None
        alive = []
        owner = None
        for sa in cls.instances:
            try:
                if not sa.winfo_exists():
                    continue
            except tk.TclError:
                continue
            alive.append(sa)
            if path.startswith(str(sa) + '.') and (owner is None or len(str(sa)) > len(str(owner))):
                owner = sa
        cls.instances[:] = alive
        return owner

    @classmethod
    def _on_wheel(cls, e):
        try:
            if e.widget.winfo_class() in ('Treeview', 'Listbox'):
                return      # 목록은 자기 안에서 스크롤
        except Exception:
            pass
        sa = cls._owner(e.widget)
        if sa is not None:
            d = e.delta if IS_MAC else e.delta / 120.0
            sa.smooth_by(-d * sa._step * (0.35 if IS_MAC else 1.0))

    @classmethod
    def _on_focus(cls, e):
        # Tab으로 다음 칸에 가면, 그 칸이 화면 밖일 때 부드럽게 따라 내려간다
        sa = cls._owner(e.widget)
        if sa is not None and e.widget is not sa.canvas:
            sa.after(10, lambda w=e.widget: sa.scroll_to_widget(w))

    def smooth_by(self, px):
        self._pending += px
        if self._anim is None:
            self._anim = self.after(0, self._tick)

    def _tick(self):
        self._anim = None
        if abs(self._pending) < 1:
            self._pending = 0.0
            return
        move = self._pending * 0.3
        move = int(move) if abs(move) >= 1 else (1 if self._pending > 0 else -1)
        before = self.canvas.yview()
        self.canvas.yview_scroll(move, 'units')
        self._pending -= move
        if self.canvas.yview() == before:   # 맨 위/맨 아래에 닿음
            self._pending = 0.0
            return
        self._anim = self.after(12, self._tick)

    def scroll_to_widget(self, w):
        try:
            if not w.winfo_ismapped():
                return
            y = w.winfo_rooty() - self.inner.winfo_rooty()
            h = w.winfo_height()
            top = self.canvas.canvasy(0)
            vh = self.canvas.winfo_height()
        except tk.TclError:
            return
        margin = 60
        if y < top + 10:
            self._pending = 0.0
            self.smooth_by(y - margin - top)
        elif y + h > top + vh - 10:
            self._pending = 0.0
            self.smooth_by(min(y - margin - top, y + h + margin - (top + vh)))

    def to_top(self):
        self._pending = 0.0
        self.canvas.yview_moveto(0)


# ===========================================================================
# 자동으로 높이가 늘어나는 여러 줄 입력 칸
# ===========================================================================
class AutoText(tk.Text):
    def __init__(self, master, min_lines=3, max_lines=22, on_change=None, **kw):
        super().__init__(master, height=min_lines, wrap='word', undo=True, font=F_(10), relief='flat', bd=0,
                         padx=10, pady=8, highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT,
                         bg=CARD, fg=INK, insertbackground=INK, spacing1=2, spacing3=2, **kw)
        self.min_lines, self.max_lines = min_lines, max_lines
        self.on_change = on_change
        self._mute = False
        self.bind('<<Modified>>', self._modified)
        self.bind('<Configure>', lambda e: self.after_idle(self.fit))
        self.bind('<Tab>', self._focus_next)

    def _focus_next(self, e):
        e.widget.tk_focusNext().focus_set()
        return 'break'

    def _modified(self, _e=None):
        if not self.edit_modified():
            return
        self.edit_modified(False)
        self.fit()
        if self.on_change and not self._mute:
            self.on_change(self.get_value())

    def fit(self):
        try:
            n = self.count('1.0', 'end', 'displaylines')
            n = n[0] if isinstance(n, tuple) else (n or 1)
        except tk.TclError:
            n = int(self.index('end-1c').split('.')[0])
        n = max(self.min_lines, min(self.max_lines, n + 1))
        if int(self.cget('height')) != n:
            self.configure(height=n)

    def get_value(self):
        return self.get('1.0', 'end-1c')

    def set_value(self, v):
        self._mute = True
        self.delete('1.0', 'end')
        self.insert('1.0', v or '')
        self.edit_reset()
        self.edit_modified(False)
        self._mute = False
        self.after_idle(self.fit)


# ===========================================================================
# 메인 창
# ===========================================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('%s v%s' % (APP_NAME, VERSION))
        self.settings = read_json(SETTINGS, {}) or {}
        apply_theme(self.settings.get('theme_accent') or TH.DEFAULT)
        self.configure(bg=BG)
        self._set_icon()
        try:
            self.ui = max(1.0, float(self.tk.call('tk', 'scaling')) / 1.3333)
        except Exception:
            self.ui = 1.0
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(int(1180 * self.ui), sw - 40), min(int(800 * self.ui), sh - 80)
        self.geometry('%dx%d+%d+%d' % (w, h, max(0, (sw - w) // 2), max(0, (sh - h) // 3)))
        self.minsize(min(int(960 * self.ui), sw - 40), min(int(620 * self.ui), sh - 80))
        self.project = F.empty_project()
        auto = read_json(AUTOSAVE)
        if isinstance(auto, dict):
            self.project.update(auto)
        self.project_path = self.settings.get('project_path') if self.settings.get('project_path') and \
            os.path.exists(self.settings.get('project_path')) else None
        self.vars = {}            # key -> (getter, setter)
        self.req_labels = {}
        self.usage = {}           # 입력 항목 -> 사용하는 양식 수
        self.usage_labels = {}    # key -> Label
        self.forms = []
        self.checked = {}
        self.form_info = {}       # key -> {'cap': 칸 수}
        self.results = None
        self.q = queue.Queue()
        self._save_job = None
        self._loading = False
        self.step_idx = 0

        self._style()
        self._build()
        self.load_into_widgets()
        self.show_step(0)
        self.after(100, self._poll)
        self.after(300, self.autodetect_forms)
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self.bind_all('<Control-s>', lambda e: self.save_project())

    # ------------------------------------------------------------------ 스타일
    def _style(self):
        st = ttk.Style(self)
        try:
            st.theme_use('clam')
        except tk.TclError:
            pass
        self.option_add('*Font', F_(10))
        # 콤보박스 위에서 휠을 굴려도 값이 바뀌지 않고 화면이 스크롤되게
        self.bind_class('TCombobox', '<MouseWheel>', lambda e: None)
        self.option_add('*TCombobox*Listbox.font', F_(10))
        st.configure('.', font=F_(10), background=BG, foreground=INK)
        st.configure('TEntry', fieldbackground=CARD, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, padding=7)
        st.map('TEntry', bordercolor=[('focus', ACCENT)], lightcolor=[('focus', ACCENT)])
        st.configure('TCombobox', fieldbackground=CARD, background=CARD, bordercolor=LINE, lightcolor=LINE,
                     darkcolor=LINE, padding=6, arrowsize=14)
        st.map('TCombobox', fieldbackground=[('readonly', CARD)], bordercolor=[('focus', ACCENT)])
        st.configure('TButton', padding=(14, 7), background=CHIP, bordercolor=LINE, lightcolor=CHIP,
                     darkcolor=CHIP, foreground=INK)
        st.map('TButton', background=[('active', CHIP_HOV), ('disabled', BTN_DIS)],
               foreground=[('disabled', DIM)])
        st.configure('Accent.TButton', background=ACCENT, foreground='white', bordercolor=ACCENT,
                     lightcolor=ACCENT, darkcolor=ACCENT, font=F_(11, 'bold'), padding=(22, 10))
        st.map('Accent.TButton', background=[('active', ACCENT_D), ('disabled', ACC_DIS)],
               foreground=[('disabled', ACC_DIS_FG)])
        st.configure('Small.TButton', padding=(10, 4), font=F_(9))
        st.configure('TRadiobutton', background=CARD, font=F_(10))
        st.configure('TCheckbutton', background=BG)
        st.configure('Treeview', rowheight=30, fieldbackground=CARD, background=CARD, bordercolor=LINE, font=F_(10))
        st.configure('Treeview.Heading', font=F_(10, 'bold'), background=HEAD, bordercolor=LINE, padding=6)
        st.map('Treeview', background=[('selected', SEL)], foreground=[('selected', INK)])
        st.configure('TProgressbar', background=ACCENT, troughcolor=TROUGH, bordercolor=LINE, lightcolor=ACCENT,
                     darkcolor=ACCENT, thickness=10)

    # ------------------------------------------------------------------ 뼈대
    def _build(self):
        # 위쪽 막대
        top = tk.Frame(self, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        top.pack(side='top', fill='x')
        tk.Label(top, text=APP_NAME, bg=CARD, fg=INK, font=F_(14, 'bold')).pack(side='left', padx=(20, 8), pady=12)
        self.subtitle_lbl = tk.Label(top, text='한 번 쓰고, 여러 출판사 양식을 한꺼번에', bg=CARD, fg=SUB, font=F_(10))
        self.subtitle_lbl.pack(side='left')
        for txt, cmd in (('도움말', self.show_help), ('다른 이름으로 저장', self.save_project_as),
                         ('저장', self.save_project), ('불러오기', self.open_project), ('새 작품', self.new_project)):
            ttk.Button(top, text=txt, command=cmd, style='Small.TButton').pack(side='right', padx=(0, 8), pady=10)
        self.theme_btn = tk.Label(top, text='  ●  테마  ', bg=CHIP, fg=ACCENT, font=F_(9, 'bold'), cursor='hand2',
                                  padx=4, pady=5)
        self.theme_btn.pack(side='right', padx=(0, 10), pady=10)
        self.theme_btn.bind('<Button-1>', lambda e: self.show_theme_picker())
        self.save_lbl = tk.Label(top, text='', bg=CARD, fg=SUB, font=F_(9))
        self.save_lbl.pack(side='right', padx=12)
        self.update_banner = tk.Label(top, text='', bg=ACCENT, fg='white', font=F_(9, 'bold'), cursor='hand2',
                                      padx=10, pady=5)
        self.update_banner.bind('<Button-1>', lambda e: self.install_update())
        if getattr(self, '_app_update', None):
            self.after(50, self.show_update_banner)

        body = tk.Frame(self, bg=BG)
        body.pack(fill='both', expand=True)
        # 왼쪽 단계 목록
        side = tk.Frame(body, bg=SIDE, width=int(232 * self.ui))
        side.pack(side='left', fill='y')
        side.pack_propagate(False)
        tk.Label(side, text='작성 순서', bg=SIDE, fg=SIDE_MUTED, font=F_(9, 'bold')).pack(anchor='w', padx=22, pady=(20, 6))
        self.side_items = []
        for i, st in enumerate(F.STEPS):
            row = tk.Frame(side, bg=SIDE, cursor='hand2')
            row.pack(fill='x', padx=10, pady=1)
            num = tk.Label(row, text=st['icon'], bg=SIDE, fg=SIDE_FG, font=F_(11), width=2)
            num.pack(side='left', padx=(10, 6), pady=9)
            name = tk.Label(row, text=st['title'], bg=SIDE, fg=SIDE_FG, font=F_(10, 'bold'), anchor='w')
            name.pack(side='left', fill='x', expand=True)
            badge = tk.Label(row, text='', bg=SIDE, fg=SIDE_MUTED, font=F_(9))
            badge.pack(side='right', padx=10)
            for w in (row, num, name, badge):
                w.bind('<Button-1>', lambda e, k=i: self.show_step(k))
            self.side_items.append((row, num, name, badge))
        self.side_progress_lbl = tk.Label(side, text='', bg=SIDE, fg=SIDE_FG, font=F_(9), justify='left', anchor='w')
        self.side_progress_lbl.pack(side='bottom', fill='x', padx=22, pady=(4, 20))
        self.side_bar = ttk.Progressbar(side, mode='determinate', maximum=100)
        self.side_bar.pack(side='bottom', fill='x', padx=22)
        tk.Label(side, text='필수 항목', bg=SIDE, fg=SIDE_MUTED, font=F_(9, 'bold')).pack(side='bottom', anchor='w',
                                                                                     padx=22, pady=(0, 6))

        # 오른쪽 내용
        main = tk.Frame(body, bg=BG)
        main.pack(side='left', fill='both', expand=True)
        nav = tk.Frame(main, bg=BG)
        nav.pack(side='bottom', fill='x', padx=28, pady=(6, 14))
        self.prev_btn = ttk.Button(nav, text='◀  이전', command=lambda: self.show_step(self.step_idx - 1))
        self.prev_btn.pack(side='left')
        self.next_btn = ttk.Button(nav, text='다음  ▶', command=lambda: self.show_step(self.step_idx + 1),
                                   style='Accent.TButton')
        self.next_btn.pack(side='right')
        self.nav_hint = tk.Label(nav, text='', bg=BG, fg=SUB, font=F_(9))
        self.nav_hint.pack(side='right', padx=14)

        self.pages = []
        holder = tk.Frame(main, bg=BG)
        holder.pack(fill='both', expand=True)
        for st in F.STEPS:
            if st['id'] == 'make':
                page = ScrollArea(holder)
                self._build_make(page.inner)
            else:
                page = ScrollArea(holder)
                self._build_step(page.inner, st)
            page.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.pages.append(page)

    # ------------------------------------------------------------------ 입력 단계
    def _header(self, parent, st):
        box = tk.Frame(parent, bg=BG)
        box.pack(fill='x', padx=34, pady=(26, 6))
        tk.Label(box, text=st['title'], bg=BG, fg=INK, font=F_(17, 'bold')).pack(anchor='w')
        if st.get('desc'):
            tk.Label(box, text=st['desc'], bg=BG, fg=SUB, font=F_(10), justify='left', wraplength=760).pack(
                anchor='w', pady=(4, 0))

    def _build_step(self, parent, st):
        self._header(parent, st)
        if st['id'] == 'chars':
            self._build_chars(parent)
            return
        card = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        card.pack(fill='x', padx=34, pady=(12, 10))
        for f in st['fields']:
            self._field(card, *f)
        if st.get('extra'):
            wrap = tk.Frame(parent, bg=BG)
            wrap.pack(fill='x', padx=34, pady=(4, 24))
            extra_card = tk.Frame(wrap, bg=CARD, highlightthickness=1, highlightbackground=LINE)
            shown = tk.BooleanVar(value=False)
            any_filled = any((self.project.get(f[0]) or '').strip() for f in st['extra'])

            def toggle(sv=shown, c=extra_card, b=None):
                sv.set(not sv.get())
                if sv.get():
                    c.pack(fill='x', pady=(8, 0))
                    btn.configure(text='▾  %s 숨기기' % st['extra_title'])
                else:
                    c.pack_forget()
                    btn.configure(text='▸  %s 보기' % st['extra_title'])
            btn = ttk.Button(wrap, text='▸  %s 보기' % st['extra_title'], command=toggle, style='Small.TButton')
            btn.pack(anchor='w')
            for f in st['extra']:
                self._field(extra_card, *f)
            if any_filled:
                toggle()
        else:
            tk.Frame(parent, bg=BG, height=24).pack()

    def _field(self, parent, key, label, kind, required, help_text, opt):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill='x', padx=22, pady=(14, 4))
        head = tk.Frame(row, bg=CARD)
        head.pack(fill='x')
        tk.Label(head, text=label, bg=CARD, fg=INK, font=F_(10, 'bold')).pack(side='left')
        if required:
            tk.Label(head, text='필수', bg=BADGE, fg=ACCENT, font=F_(8, 'bold'), padx=6).pack(side='left', padx=6)
        ul = tk.Label(head, text='', bg=CARD, fg=SUB, font=F_(8))
        ul.pack(side='left', padx=4)
        self.usage_labels[key] = ul
        counter = None
        if kind == 'text':
            counter = tk.Label(head, text='', bg=CARD, fg=MUTED, font=F_(8))
            counter.pack(side='right')
        if help_text:
            tk.Label(row, text=help_text, bg=CARD, fg=SUB, font=F_(9), justify='left', anchor='w',
                     wraplength=720).pack(fill='x', pady=(2, 4))

        def changed(v, k=key, c=counter):
            if self._loading:
                return
            self.project[k] = v
            if c is not None:
                c.configure(text=self._count_text(v))
            self.on_data_change()

        if kind == 'line':
            var = tk.StringVar()
            ent = ttk.Entry(row, textvariable=var, font=F_(10))
            ent.pack(fill='x')
            var.trace_add('write', lambda *a, v=var: changed(v.get()))
            self.vars[key] = (var.get, var.set)
        elif kind in ('choice', 'combo'):
            var = tk.StringVar()
            cb = ttk.Combobox(row, textvariable=var, values=opt or [], font=F_(10),
                              state='readonly' if kind == 'choice' else 'normal', width=30)
            cb.pack(anchor='w')
            var.trace_add('write', lambda *a, v=var: changed(v.get()))
            self.vars[key] = (var.get, var.set)
        elif kind == 'text':
            t = AutoText(row, min_lines=opt or 3, on_change=changed)
            t.pack(fill='x')
            self.vars[key] = (t.get_value, t.set_value)
            if counter is not None:
                self.vars[key + '__counter'] = (lambda: '', lambda v, c=counter: c.configure(text=self._count_text(v)))
        elif kind == 'volume':
            box = tk.Frame(row, bg=CARD)
            box.pack(anchor='w', fill='x')
            for suf, lab, unit in F.VOLUME_PARTS:
                k2 = key + suf
                cell = tk.Frame(box, bg=CARD)
                cell.pack(side='left', padx=(0, 18))
                tk.Label(cell, text=lab, bg=CARD, fg=SUB, font=F_(9)).pack(anchor='w')
                inner = tk.Frame(cell, bg=CARD)
                inner.pack(anchor='w')
                var = tk.StringVar()
                ttk.Entry(inner, textvariable=var, width=12 if suf != '_eps' else 7, font=F_(10)).pack(side='left')
                tk.Label(inner, text=unit, bg=CARD, fg=SUB).pack(side='left', padx=4)
                var.trace_add('write', lambda *a, v=var, kk=k2: changed(v.get(), kk))
                self.vars[k2] = (var.get, var.set)
        elif kind == 'ox':
            var = tk.StringVar()
            box = tk.Frame(row, bg=CARD)
            box.pack(anchor='w')
            for val, lab in (('O', 'O  (예)'), ('X', 'X  (아니요)'), ('', '선택 안 함')):
                ttk.Radiobutton(box, text=lab, value=val, variable=var).pack(side='left', padx=(0, 18))
            var.trace_add('write', lambda *a, v=var: changed(v.get()))
            self.vars[key] = (var.get, var.set)
        tk.Frame(parent, bg=CARD, height=6).pack(fill='x')

    @staticmethod
    def _count_text(v):
        v = v or ''
        if not v.strip():
            return ''
        return '공백 포함 {:,}자 · 미포함 {:,}자'.format(len(v.replace('\n', '')), len(re.sub(r'\s', '', v)))

    # ------------------------------------------------------------------ 등장인물
    def _build_chars(self, parent):
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill='both', expand=True, padx=34, pady=(12, 24))
        left = tk.Frame(wrap, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        left.pack(side='left', fill='y', anchor='n')
        tk.Label(left, text='인물 목록', bg=CARD, fg=INK, font=F_(10, 'bold')).pack(anchor='w', padx=14, pady=(12, 6))
        self.char_list = tk.Listbox(left, width=24, height=14, activestyle='none', relief='flat', bd=0,
                                    highlightthickness=0, font=F_(10), selectbackground=SEL,
                                    selectforeground=INK, bg=CARD, fg=INK, exportselection=False)
        self.char_list.pack(fill='both', expand=True, padx=8)
        self.char_list.bind('<<ListboxSelect>>', lambda e: self.char_select())
        btns = tk.Frame(left, bg=CARD)
        btns.pack(fill='x', padx=8, pady=10)
        ttk.Button(btns, text='+ 추가', command=self.char_add, style='Small.TButton').pack(side='left')
        ttk.Button(btns, text='삭제', command=self.char_del, style='Small.TButton').pack(side='left', padx=4)
        ttk.Button(btns, text='▲', width=3, command=lambda: self.char_move(-1), style='Small.TButton').pack(side='left')
        ttk.Button(btns, text='▼', width=3, command=lambda: self.char_move(1), style='Small.TButton').pack(side='left',
                                                                                                         padx=2)
        tk.Label(left, text='팁: 주인공 둘에게 「공」「수」를\n정해 두면 「공」「수」 칸에\n정확히 들어가요.',
                 bg=CARD, fg=SUB, font=F_(9), justify='left').pack(anchor='w', padx=14, pady=(0, 14))

        right = tk.Frame(wrap, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        right.pack(side='left', fill='both', expand=True, padx=(14, 0))
        self.char_empty = tk.Label(right, text='왼쪽 「+ 추가」를 눌러 인물을 넣어 주세요.', bg=CARD, fg=SUB, font=F_(11))
        self.char_form = tk.Frame(right, bg=CARD)
        self.char_vars = {}
        grid = tk.Frame(self.char_form, bg=CARD)
        grid.pack(fill='x', padx=20, pady=(16, 0))
        short = [f for f in F.CHAR_FIELDS if f[2] in ('line', 'choice') and f[0] != 'goal']
        for i, (k, lab, kind, opt) in enumerate(short):
            c = tk.Frame(grid, bg=CARD)
            c.grid(row=0, column=i, sticky='w', padx=(0, 12))
            tk.Label(c, text=lab, bg=CARD, fg=INK, font=F_(9, 'bold')).pack(anchor='w')
            var = tk.StringVar()
            if kind == 'choice':
                w = ttk.Combobox(c, textvariable=var, values=opt, state='readonly', width=6 if k != 'kind' else 7)
            else:
                w = ttk.Entry(c, textvariable=var, width=16 if k == 'name' else 7)
            w.pack(anchor='w')
            var.trace_add('write', lambda *a, kk=k, v=var: self.char_changed(kk, v.get()))
            self.char_vars[k] = (var.get, var.set)
        for k, lab, kind, opt in F.CHAR_FIELDS:
            if (k, lab, kind, opt) in short:
                continue
            r = tk.Frame(self.char_form, bg=CARD)
            r.pack(fill='x', padx=20, pady=(12, 0))
            tk.Label(r, text=lab, bg=CARD, fg=INK, font=F_(9, 'bold')).pack(anchor='w')
            if kind == 'text':
                t = AutoText(r, min_lines=opt or 2, on_change=lambda v, kk=k: self.char_changed(kk, v))
                t.pack(fill='x')
                self.char_vars[k] = (t.get_value, t.set_value)
            else:
                var = tk.StringVar()
                ttk.Entry(r, textvariable=var).pack(fill='x')
                var.trace_add('write', lambda *a, kk=k, v=var: self.char_changed(kk, v.get()))
                self.char_vars[k] = (var.get, var.set)
        tk.Label(self.char_form, text='인물 소개만 써도 충분해요. 외모·성격 칸은 「외형 묘사」「성격」 칸이 따로 있는 양식에 쓰여요.',
                 bg=CARD, fg=SUB, font=F_(9), wraplength=620, justify='left').pack(anchor='w', padx=20, pady=(10, 18))
        self.char_idx = None

    def char_refresh(self, keep=None):
        self.char_list.delete(0, 'end')
        for c in self.project.get('characters', []):
            tag = c.get('pos') or c.get('kind') or ''
            self.char_list.insert('end', '  %s%s' % (c.get('name') or '(이름 없음)', '  · ' + tag if tag else ''))
        n = len(self.project.get('characters', []))
        if keep is not None and n:
            keep = max(0, min(n - 1, keep))
            self.char_list.selection_clear(0, 'end')
            self.char_list.selection_set(keep)
            self.char_select()
        elif not n:
            self.char_idx = None
            self.char_form.pack_forget()
            self.char_empty.pack(expand=True, pady=60)

    def char_select(self):
        sel = self.char_list.curselection()
        if not sel:
            return
        self.char_idx = sel[0]
        c = self.project['characters'][self.char_idx]
        self._loading = True
        for k, (_, setter) in self.char_vars.items():
            setter(c.get(k, ''))
        self._loading = False
        self.char_empty.pack_forget()
        self.char_form.pack(fill='both', expand=True)

    def char_changed(self, key, value):
        if self._loading or self.char_idx is None:
            return
        chars = self.project['characters']
        if self.char_idx >= len(chars):
            return
        chars[self.char_idx][key] = value
        if key in ('name', 'pos', 'kind'):
            c = chars[self.char_idx]
            tag = c.get('pos') or c.get('kind') or ''
            self.char_list.delete(self.char_idx)
            self.char_list.insert(self.char_idx, '  %s%s' % (c.get('name') or '(이름 없음)', '  · ' + tag if tag else ''))
            self.char_list.selection_set(self.char_idx)
        self.on_data_change()

    def char_add(self):
        chars = self.project.setdefault('characters', [])
        n_leads = sum(1 for c in chars if c.get('kind') == '주연')
        new = {k: '' for k, *_ in F.CHAR_FIELDS}
        new['kind'] = '주연' if n_leads < 2 else '조연'
        if new['kind'] == '주연':
            has = {c.get('pos') for c in chars}
            if (self.project.get('genre') or 'BL').upper().startswith(('BL', 'GL')):
                new['pos'] = '공' if '공' not in has else ('수' if '수' not in has else '')
            else:
                new['pos'] = '남주' if '남주' not in has else ('여주' if '여주' not in has else '')
        chars.append(new)
        self.char_refresh(keep=len(chars) - 1)
        self.on_data_change()

    def char_del(self):
        if self.char_idx is None:
            return
        c = self.project['characters'][self.char_idx]
        if (c.get('name') or c.get('intro')) and not messagebox.askyesno(
                APP_NAME, '「%s」 인물을 삭제할까요?' % (c.get('name') or '이름 없음')):
            return
        del self.project['characters'][self.char_idx]
        self.char_refresh(keep=self.char_idx)
        self.on_data_change()

    def char_move(self, d):
        i = self.char_idx
        chars = self.project.get('characters', [])
        if i is None or not (0 <= i + d < len(chars)):
            return
        chars[i], chars[i + d] = chars[i + d], chars[i]
        self.char_refresh(keep=i + d)
        self.on_data_change()

    # ------------------------------------------------------------------ 양식 만들기 단계
    def _build_make(self, page):
        self._header(page, {'title': '일괄 작성 · 저장',
                            'desc': '양식 묶음을 고르고 맨 아래 「▶ 선택한 양식 일괄 저장」을 누르면, 고른 양식이 모두 채워져 '
                                    '저장 위치에 한꺼번에 저장돼요. 원본 양식 파일은 바뀌지 않아요.'})
        top = tk.Frame(page, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        top.pack(fill='x', padx=34, pady=(10, 8))
        # 양식 묶음
        r1 = tk.Frame(top, bg=CARD)
        r1.pack(fill='x', padx=18, pady=(14, 4))
        tk.Label(r1, text='① 양식 묶음', bg=CARD, fg=INK, font=F_(10, 'bold'), width=12, anchor='w').pack(side='left')
        self.forms_var = tk.StringVar(value=self.settings.get('forms_path', ''))
        ttk.Entry(r1, textvariable=self.forms_var, state='readonly').pack(side='left', fill='x', expand=True)
        ttk.Button(r1, text='폴더 선택', command=self.pick_forms_dir, style='Small.TButton').pack(side='right', padx=(6, 0))
        ttk.Button(r1, text='ZIP 선택', command=self.pick_forms_zip, style='Small.TButton').pack(side='right', padx=(6, 0))
        self.forms_info = tk.Label(top, text='받은 양식 묶음 zip을 그대로 고르면 돼요(압축을 풀 필요 없음).', bg=CARD, fg=SUB,
                                   font=F_(9), anchor='w')
        self.forms_info.pack(fill='x', padx=(150, 18))
        # 저장 폴더
        r2 = tk.Frame(top, bg=CARD)
        r2.pack(fill='x', padx=18, pady=(10, 4))
        tk.Label(r2, text='② 저장 위치', bg=CARD, fg=INK, font=F_(10, 'bold'), width=12, anchor='w').pack(side='left')
        default_out = self.settings.get('out_base') or os.path.join(os.path.expanduser('~'), 'Documents', '투고양식_결과')
        self.out_var = tk.StringVar(value=default_out)
        ttk.Entry(r2, textvariable=self.out_var, state='readonly').pack(side='left', fill='x', expand=True)
        ttk.Button(r2, text='폴더 선택', command=self.pick_out_dir, style='Small.TButton').pack(side='right', padx=(6, 0))
        tk.Label(top, text='만들 때마다 이 안에 「작품명_날짜」 폴더가 새로 생겨서 이전 결과를 덮어쓰지 않아요.', bg=CARD, fg=SUB,
                 font=F_(9), anchor='w').pack(fill='x', padx=(150, 18), pady=(0, 14))

        # 양식 목록
        mid = tk.Frame(page, bg=BG)
        mid.pack(fill='x', padx=34)
        bar = tk.Frame(mid, bg=BG)
        bar.pack(fill='x', pady=(6, 6))
        tk.Label(bar, text='③ 만들 양식', bg=BG, fg=INK, font=F_(10, 'bold')).pack(side='left')
        self.sel_lbl = tk.Label(bar, text='', bg=BG, fg=SUB, font=F_(9))
        self.sel_lbl.pack(side='left', padx=10)
        ttk.Button(bar, text='미리보기', command=self.preview, style='Small.TButton').pack(side='right')
        ttk.Button(bar, text='모두 해제', command=lambda: self.check_all(False), style='Small.TButton').pack(side='right',
                                                                                                       padx=6)
        ttk.Button(bar, text='모두 선택', command=lambda: self.check_all(True), style='Small.TButton').pack(side='right')
        self.search_var = tk.StringVar()
        se = ttk.Entry(bar, textvariable=self.search_var, width=18)
        se.pack(side='right', padx=10)
        tk.Label(bar, text='검색', bg=BG, fg=SUB, font=F_(9)).pack(side='right')
        self.search_var.trace_add('write', lambda *a: self.fill_tree())

        # 장르 탭: 고른 장르의 양식만 목록에 보이고, 그 양식만 만든다
        tabs = tk.Frame(mid, bg=BG)
        tabs.pack(fill='x', pady=(0, 6))
        self.genre_var = tk.StringVar(value='전체')
        self.genre_auto = True
        self.genre_tabs = {}
        for g in ['전체'] + GENRE_TABS:
            lb = tk.Label(tabs, text=g, bg=CHIP, fg=INK, font=F_(9, 'bold'), padx=12, pady=5, cursor='hand2')
            lb.pack(side='left', padx=(0, 6))
            lb.bind('<Button-1>', lambda e, gg=g: self.set_genre(gg, manual=True))
            self.genre_tabs[g] = lb
        self.genre_hint = tk.Label(tabs, text='', bg=BG, fg=SUB, font=F_(9))
        self.genre_hint.pack(side='left', padx=8)

        tv_wrap = tk.Frame(mid, bg=BG)
        tv_wrap.pack(fill='x')
        cols = ('use', 'name', 'genre', 'file', 'result')
        self.tree = ttk.Treeview(tv_wrap, columns=cols, show='headings', selectmode='browse', height=9)
        for c, t, w, anchor in (('use', '선택', 56, 'center'), ('name', '출판사 · 레이블', 230, 'w'),
                                ('genre', '장르', 190, 'w'), ('file', '양식 파일', 260, 'w'), ('result', '결과', 170, 'w')):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor=anchor, stretch=(c in ('file', 'result')))
        vsb = ttk.Scrollbar(tv_wrap, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        self.tree.bind('<Button-1>', self.tree_click)
        self.tree.bind('<Double-1>', lambda e: self.preview())
        self.tree.tag_configure('off', foreground=DIM)
        self.tree.tag_configure('warn', foreground=WARN)

        # 실행
        bottom = tk.Frame(page, bg=BG)
        bottom.pack(fill='x', padx=34, pady=(12, 6))
        self.run_btn = ttk.Button(bottom, text='▶  선택한 양식 일괄 저장', command=self.run, style='Accent.TButton')
        self.run_btn.pack(side='left')
        self.open_dir_btn = ttk.Button(bottom, text='결과 폴더 열기', command=self.open_result_dir, state='disabled')
        self.open_dir_btn.pack(side='left', padx=(12, 0))
        self.open_rep_btn = ttk.Button(bottom, text='결과 보고서 열기', command=self.open_report, state='disabled')
        self.open_rep_btn.pack(side='left', padx=6)
        right = tk.Frame(bottom, bg=BG)
        right.pack(side='right', fill='x', expand=True, padx=(20, 0))
        self.run_status = tk.Label(right, text='', bg=BG, fg=SUB, font=F_(9), anchor='e')
        self.run_status.pack(fill='x')
        self.run_bar = ttk.Progressbar(right, mode='determinate')
        self.run_bar.pack(fill='x', pady=(4, 0))
        self.last_out = None
        self.last_report = None

        # ④ 투고하기: 고른 양식의 투고처(이메일 복사 / 사이트 바로가기)
        sub_head = tk.Frame(page, bg=BG)
        sub_head.pack(fill='x', padx=34, pady=(18, 4))
        tk.Label(sub_head, text='④ 투고하기', bg=BG, fg=INK, font=F_(10, 'bold')).pack(side='left')
        self.submit_info = tk.Label(sub_head, text='', bg=BG, fg=SUB, font=F_(9))
        self.submit_info.pack(side='left', padx=10)
        self.toast = tk.Label(sub_head, text='', bg=BG, fg=OK, font=F_(9, 'bold'))
        self.toast.pack(side='right')
        self.submit_box = tk.Frame(page, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        self.submit_box.pack(fill='x', padx=34, pady=(0, 24))
        self._submit_job = None

    # ------------------------------------------------------------------ ④ 투고하기
    SUBMIT_LABEL = {'email': '이메일', 'form': '구글 폼', 'site': '홈페이지 접수', 'toogohada': '투고하다'}

    def refresh_submit(self):
        """목록이 바뀔 때마다 너무 자주 그리지 않도록 잠깐 모아서 다시 그린다"""
        if not hasattr(self, 'submit_box'):
            return
        if self._submit_job:
            self.after_cancel(self._submit_job)
        self._submit_job = self.after(120, self._draw_submit)

    def _draw_submit(self):
        self._submit_job = None
        box = self.submit_box
        if not box.winfo_exists():
            return
        for w in box.winfo_children():
            w.destroy()
        rows, seen = [], set()
        for e in self.visible_forms():
            if not self.checked.get(e.key, True) or not e.submit:
                continue
            k = (e.publisher, e.brand)
            if k in seen:
                continue
            seen.add(k)
            rows.append(e)
        n_methods = sum(1 for e in rows if e.submit.get('methods'))
        checked = next((e.submit.get('checked') for e in rows if e.submit.get('checked')), '')
        if rows:
            info = '선택한 %d곳 중 %d곳은 바로 투고할 수 있어요' % (len(rows), n_methods)
            if checked:
                info += ' · %s 확인' % checked
        else:
            info = '투고처 정보가 있는 양식 묶음을 고르면 여기에 나와요' if self.forms else ''
        self.submit_info.configure(text=info)
        if not rows:
            tk.Label(box, text='표시할 투고처가 없어요.', bg=CARD, fg=SUB, font=F_(9)).pack(anchor='w', padx=16, pady=12)
            return
        for i, e in enumerate(rows):
            sub = e.submit
            row = tk.Frame(box, bg=CARD)
            row.pack(fill='x', padx=14, pady=(10 if i == 0 else 4, 2))
            name = e.publisher + (' · ' + e.brand if e.brand and e.brand != e.publisher else '')
            tk.Label(row, text=name, bg=CARD, fg=INK, font=F_(10, 'bold'), width=24, anchor='w').pack(side='left',
                                                                                                anchor='n')
            guide = sub.get('guide') or ''
            if guide:
                ttk.Button(row, text='안내 글', style='Small.TButton',
                           command=lambda v=guide: self.open_url(v)).pack(side='right', padx=(6, 0), anchor='n')
            body = tk.Frame(row, bg=CARD)
            body.pack(side='left', fill='x', expand=True)
            methods = sub.get('methods') or []
            if not methods:
                tk.Label(body, text='등록된 투고처가 없어요 — 「안내 글」에서 확인', bg=CARD, fg=SUB, font=F_(9),
                         anchor='w').pack(anchor='w', pady=3)
            for m in methods:
                line = tk.Frame(body, bg=CARD)
                line.pack(fill='x', pady=1)
                kind = self.SUBMIT_LABEL.get(m['type'], m['type'])
                tk.Label(line, text=kind, bg=BADGE, fg=ACCENT, font=F_(8, 'bold'), padx=6).pack(side='left')
                shown = m['value'] if m['type'] == 'email' else self._short_url(m['value'])
                tk.Label(line, text=shown, bg=CARD, fg=INK, font=F_(9), anchor='w').pack(side='left', padx=6)
                if m['type'] == 'email':
                    ttk.Button(line, text='주소 복사', style='Small.TButton',
                               command=lambda v=m['value']: self.copy_text(v)).pack(side='right', padx=(4, 0))
                else:
                    ttk.Button(line, text='사이트 열기', style='Small.TButton',
                               command=lambda v=m['value']: self.open_url(v)).pack(side='right', padx=(4, 0))
                note = m.get('note') or ''
                if m.get('check'):
                    note = '⚠ ' + (note or '주소를 한 번 확인해 주세요')
                if note:
                    tk.Label(body, text=note, bg=CARD, fg=WARN if m.get('check') else SUB, font=F_(8),
                             anchor='w', justify='left', wraplength=520).pack(anchor='w', padx=(2, 0))
            if i < len(rows) - 1:
                tk.Frame(box, bg=LINE, height=1).pack(fill='x', padx=14, pady=(8, 0))
        tk.Label(box, text='투고처는 출판사 사정에 따라 바뀔 수 있어요. 보내기 전에 「안내 글」을 한 번 확인해 주세요.',
                 bg=CARD, fg=SUB, font=F_(8)).pack(anchor='w', padx=16, pady=(10, 12))

    @staticmethod
    def _short_url(u):
        u = re.sub(r'^https?://(www[.])?', '', u)
        return u if len(u) <= 46 else u[:43] + '…'

    def copy_text(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        self.show_toast('✓ 「%s」 복사했어요' % text)

    def open_url(self, url):
        import webbrowser
        if url.startswith(('http://', 'https://')):
            webbrowser.open(url)
            self.show_toast('↗ 브라우저에서 열었어요')

    def show_toast(self, msg):
        self.toast.configure(text=msg)
        if getattr(self, '_toast_job', None):
            self.after_cancel(self._toast_job)
        self._toast_job = self.after(2600, lambda: self.toast.winfo_exists() and self.toast.configure(text=''))

    # ------------------------------------------------------------------ 단계 이동
    def show_step(self, i):
        if not (0 <= i < len(F.STEPS)):
            return
        self.step_idx = i
        self.pages[i].tkraise()
        if isinstance(self.pages[i], ScrollArea):
            self.pages[i].to_top()
        for k, (row, num, name, badge) in enumerate(self.side_items):
            sel = (k == i)
            bg = SIDE_SEL if sel else SIDE
            for w in (row, num, name, badge):
                w.configure(bg=bg)
            name.configure(fg='white' if sel else SIDE_FG)
        self.prev_btn.configure(state='normal' if i > 0 else 'disabled')
        last = (i == len(F.STEPS) - 1)
        if last:
            self.next_btn.pack_forget()
        elif not self.next_btn.winfo_ismapped():
            self.next_btn.pack(side='right', before=self.nav_hint)
        self.nav_hint.configure(text=('다음: ' + F.STEPS[i + 1]['title']) if not last else '')
        if F.STEPS[i]['id'] == 'make':
            self.auto_genre()
        self.refresh_progress()

    # ------------------------------------------------------------------ 데이터 ↔ 화면
    def load_into_widgets(self):
        self._loading = True
        try:
            for k, (getter, setter) in self.vars.items():
                if k.endswith('__counter'):
                    continue
                setter(self.project.get(k, '') or '')
                if k + '__counter' in self.vars:
                    self.vars[k + '__counter'][1](self.project.get(k, '') or '')
        finally:
            self._loading = False
        self.char_refresh(keep=0 if self.project.get('characters') else None)
        self.refresh_progress()

    def on_data_change(self):
        self.refresh_progress()
        if self._save_job:
            self.after_cancel(self._save_job)
        self._save_job = self.after(700, self.autosave)
        self.save_lbl.configure(text='입력 중…')

    def autosave(self):
        self._save_job = None
        try:
            write_json(AUTOSAVE, self.project)
            if self.project_path:
                write_json(self.project_path, self.project)
                where = os.path.basename(self.project_path)
            else:
                where = '자동 저장'
            self.save_lbl.configure(text='✓ %s  %s' % (where, datetime.datetime.now().strftime('%H:%M:%S')))
        except Exception as ex:
            self.save_lbl.configure(text='저장 실패: %s' % ex)

    def refresh_progress(self):
        req = F.required_keys()
        done_total = 0
        per_step = {}
        for sid, key, label, kind in req:
            if kind == 'volume':
                ok = any((self.project.get(key + s) or '').strip() for s, _, _ in F.VOLUME_PARTS)
            else:
                ok = bool((self.project.get(key) or '').strip())
            per_step.setdefault(sid, [0, 0])
            per_step[sid][1] += 1
            if ok:
                per_step[sid][0] += 1
                done_total += 1
        n_chars = len([c for c in self.project.get('characters', []) if (c.get('name') or '').strip()])
        for k, st in enumerate(F.STEPS):
            badge = self.side_items[k][3]
            if st['id'] == 'chars':
                badge.configure(text=('%d명' % n_chars) if n_chars else '—', fg=SIDE_OK if n_chars >= 2 else SIDE_MUTED)
            elif st['id'] in per_step:
                d, t = per_step[st['id']]
                badge.configure(text='✓' if d == t else '%d/%d' % (d, t), fg=SIDE_OK if d == t else SIDE_MUTED)
            elif st['id'] == 'make':
                badge.configure(text=('%d개' % sum(1 for e in self.visible_forms() if self.checked.get(e.key, True)))
                                if self.forms else '')
            else:
                badge.configure(text='')
        total = len(req) + 1
        done = done_total + (1 if n_chars >= 2 else 0)
        self.side_bar['value'] = 100.0 * done / total
        self.side_progress_lbl.configure(text='%d / %d 완료' % (done, total))

    # ------------------------------------------------------------------ 파일
    def new_project(self):
        if not messagebox.askyesno(APP_NAME, '새 작품을 시작할까요?\n\n작가 정보(필명·연락처·경력)는 그대로 두고\n작품 내용만 비워요.'):
            return
        keep = {k: self.project.get(k, '') for k in ('pen', 'email', 'phone', 'real_name', 'author_type', 'career',
                                                    'bio', 'awards', 'adult', 'birth', 'author_gender', 'address',
                                                    'other_career')}
        self.project = F.empty_project()
        self.project.update(keep)
        self.project_path = None
        self.settings['project_path'] = None
        write_json(SETTINGS, self.settings)
        self.load_into_widgets()
        self.autosave()
        self.show_step(1)

    def open_project(self):
        path = filedialog.askopenfilename(title='작품 파일 불러오기', filetypes=[('작품 파일', '*.json'), ('모든 파일', '*.*')])
        if not path:
            return
        data = read_json(path)
        if not isinstance(data, dict):
            messagebox.showerror(APP_NAME, '이 파일을 읽을 수 없어요.')
            return
        self.project = F.empty_project()
        self.project.update(data)
        self.project_path = path
        self.settings['project_path'] = path
        write_json(SETTINGS, self.settings)
        self.load_into_widgets()
        self.autosave()
        self.show_step(self.step_idx)

    def save_project(self):
        if not self.project_path:
            return self.save_project_as()
        self.autosave()

    def save_project_as(self):
        name = '%s_투고정보.json' % (re.sub(r'[\\/:*?"<>|]', ' ', self.project.get('title') or '작품').strip() or '작품')
        path = filedialog.asksaveasfilename(title='작품 파일 저장', defaultextension='.json', initialfile=name,
                                            filetypes=[('작품 파일', '*.json')])
        if not path:
            return
        self.project_path = path
        self.settings['project_path'] = path
        write_json(SETTINGS, self.settings)
        self.autosave()

    def on_close(self):
        if self._save_job:
            self.after_cancel(self._save_job)
            self.autosave()
        self.destroy()

    # ------------------------------------------------------------------ 양식 묶음
    def autodetect_forms(self):
        path = self.settings.get('forms_path')
        cands, bundles = [], []
        dirs = [FORMS_DIR, APP_DIR, BUNDLE_DIR, os.path.dirname(APP_DIR), os.getcwd()]
        home = os.path.expanduser('~')
        dirs += [os.path.join(home, d) for d in ('Downloads', 'Desktop', 'Documents', '다운로드', '바탕 화면')]
        for d in dirs:
            for z in glob.glob(os.path.join(d, '*.zip')):
                n = os.path.basename(z)
                if re.search(r'양식|hwpx|투고|자동', n, re.I):
                    cands.append(z)
                if re.search(r'투고양식_묶음', n):
                    bundles.append(z)
        bundles = sorted(set(bundles), key=lambda p: (UP.version_tuple(bundle_version(p)), os.path.getmtime(p)),
                         reverse=True)
        # 저장된 경로보다 더 새 버전 묶음이 있으면(자동 업데이트·새 설치) 그것을 쓴다
        if path and bundles and re.search(r'투고양식_묶음', os.path.basename(path)) and \
                UP.is_newer(bundle_version(bundles[0]), bundle_version(path)):
            path = bundles[0]
        # 장르 정보가 든 통합 묶음이 있으면, 예전 BL 전용 zip보다 그것을 먼저 쓴다
        if path and os.path.exists(path) and (re.search(r'투고양식_묶음', os.path.basename(path)) or not bundles):
            self.load_forms_async(path)
            return
        if bundles:
            self.load_forms_async(bundles[0], quiet=True)
            return
        cands = sorted(set(cands), key=lambda p: os.path.getmtime(p), reverse=True)
        if cands:
            self.load_forms_async(cands[0], quiet=True)

    def pick_forms_zip(self):
        p = filedialog.askopenfilename(title='양식 묶음 zip 선택', filetypes=[('zip 파일', '*.zip')])
        if p:
            self.load_forms_async(p)

    def pick_forms_dir(self):
        p = filedialog.askdirectory(title='양식이 들어 있는 폴더 선택')
        if p:
            self.load_forms_async(p)

    def pick_out_dir(self):
        p = filedialog.askdirectory(title='결과를 저장할 폴더 선택')
        if p:
            self.out_var.set(p)
            self.settings['out_base'] = p
            write_json(SETTINGS, self.settings)

    def load_forms_async(self, path, quiet=False):
        self.forms_info.configure(text='양식을 읽는 중…', fg=SUB)

        def work():
            try:
                forms = load_forms(path)
                self.q.put(('forms', path, forms, quiet))
                # 각 양식이 어떤 입력 항목을 쓰는지 분석
                sample = full_sample_project()
                usage, info = {}, {}
                for e in forms:
                    try:
                        _, rep = fill_hwpx(e.read(), sample, e.display, dry_run=True)
                        info[e.key] = {'cap': len(rep.filled) + len(rep.nodata), 'manual': len(rep.manual)}
                        for fk in rep.fields_used:
                            usage[fk] = usage.get(fk, 0) + 1
                    except Exception:
                        info[e.key] = {'cap': 0, 'manual': 0}
                self.q.put(('usage', usage, info))
            except Exception as ex:
                self.q.put(('forms_error', path, ex, quiet))
        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == 'forms':
                    _, path, forms, quiet = msg
                    if not forms:
                        if not quiet:
                            messagebox.showwarning(APP_NAME, '이 안에서 .hwpx 양식을 찾지 못했어요.')
                        self.forms_info.configure(text='hwpx 양식을 찾지 못했어요. 다른 zip/폴더를 골라 주세요.', fg=WARN)
                        continue
                    self.forms = forms
                    prev = self.settings.get('unchecked', [])
                    self.checked = {e.key: (e.key not in prev) for e in forms}
                    self.forms_var.set(path)
                    self.settings['forms_path'] = path
                    write_json(SETTINGS, self.settings)
                    pubs = len({e.folder for e in forms})
                    self.forms_info.configure(text='✓ 양식 %d개 (출판사·브랜드 %d곳)를 찾았어요.' % (len(forms), pubs), fg=OK)
                    self.results = None
                    self.data_version = bundle_version(path)
                    self.auto_genre()
                    self.refresh_progress()
                    if not getattr(self, '_update_checked', False) and self.settings.get('auto_update', True):
                        self._update_checked = True
                        self.check_updates(manual=False)
                elif kind == 'forms_error':
                    _, path, ex, quiet = msg
                    if not quiet:
                        messagebox.showerror(APP_NAME, '양식을 읽지 못했어요.\n%s' % ex)
                    self.forms_info.configure(text='양식을 읽지 못했어요: %s' % ex, fg=WARN)
                elif kind == 'usage':
                    _, usage, info = msg
                    self.usage, self.form_info = usage, info
                    self.update_usage_labels()
                    self.fill_tree()
                elif kind == 'upd_data':
                    _, path, ver = msg
                    self.load_forms_async(path, quiet=True)
                    self.show_toast('⬇ 양식·투고처를 새로 받았어요 (%s 기준)' % ver)
                    self._upd_msg = '양식·투고처를 %s 기준으로 새로 받았어요.' % ver
                elif kind == 'upd_app':
                    self._app_update = msg[1]
                    self.show_update_banner()
                elif kind == 'upd_done':
                    _, manual, text = msg
                    self._upd_msg = text
                    if manual:
                        messagebox.showinfo(APP_NAME, text)
                elif kind == 'upd_dl':
                    _, done, total = msg
                    if getattr(self, '_dl_bar', None) is not None and self._dl_bar.winfo_exists():
                        self._dl_bar['maximum'] = max(total, 1)
                        self._dl_bar['value'] = done
                elif kind == 'upd_installer':
                    self._installer_ready(*msg[1:])
                elif kind == 'progress':
                    _, i, n, e, rep = msg
                    self.run_bar['maximum'] = n
                    self.run_bar['value'] = i
                    self.run_status.configure(text='%d / %d  %s' % (i, n, e.display))
                elif kind == 'done':
                    self.on_done(*msg[1:])
                elif kind == 'error':
                    self.run_btn.configure(state='normal')
                    messagebox.showerror(APP_NAME, '만드는 중 문제가 생겼어요.\n\n%s' % msg[1])
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def update_usage_labels(self):
        n = len(self.forms)
        for key, lbl in self.usage_labels.items():
            if key in ('cur', 'tot'):
                c = max([self.usage.get(key + s, 0) for s, _, _ in F.VOLUME_PARTS] + [0])
            elif key == 'incest_relation':
                c = self.usage.get('ox_incest', 0)
            elif key == 'author_type':
                c = max(self.usage.get('author_type', 0), self.usage.get('career', 0))
            else:
                c = self.usage.get(key, 0)
            if not n:
                lbl.configure(text='')
            elif c:
                lbl.configure(text='· 양식 %d곳에서 사용' % c, fg=SUB)
            else:
                lbl.configure(text='· 이번 양식 묶음에선 안 쓰여요', fg=MUTED2)

    # ------------------------------------------------------------------ 장르 탭
    def in_genre(self, e):
        g = self.genre_var.get() if hasattr(self, 'genre_var') else '전체'
        return g == '전체' or not e.genres or g in e.genres

    def visible_forms(self):
        return [e for e in self.forms if self.in_genre(e)]

    def set_genre(self, g, manual=False):
        if manual:
            self.genre_auto = False
        self.genre_var.set(g)
        for name, lb in self.genre_tabs.items():
            n = len(self.forms) if name == '전체' else sum(1 for e in self.forms if name in e.genres)
            lb.configure(text='%s %d' % (name, n) if self.forms else name,
                         bg=ACCENT if name == g else CHIP, fg='white' if name == g else INK)
        tagged = any(e.genres for e in self.forms)
        if self.forms and not tagged:
            self.genre_hint.configure(text='이 양식 묶음에는 장르 정보가 없어 모두 보여요')
        elif not manual and self.genre_auto and g != '전체':
            self.genre_hint.configure(text='작품 장르에 맞춰 골랐어요')
        else:
            self.genre_hint.configure(text='')
        self.fill_tree()

    def auto_genre(self):
        if not getattr(self, 'genre_auto', True) or not self.forms:
            self.set_genre(self.genre_var.get())
            return
        pg = (self.project.get('genre') or '').replace(' ', '')
        g = '전체'
        for cand in GENRE_TABS:
            if pg.upper().startswith(cand.upper()) or pg == cand:
                g = cand
        if pg in ('로판',):
            g = '로맨스판타지'
        if pg in ('현로', '현대물'):
            g = '현대로맨스'
        if g != '전체' and not any(g in e.genres for e in self.forms):
            g = '전체'
        self.set_genre(g)

    def fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        q = (self.search_var.get() if hasattr(self, 'search_var') else '').strip().lower()
        res = {e.key: (rep, path) for e, rep, path in (self.results or [])}
        for e in self.forms:
            if not self.in_genre(e):
                continue
            if q and q not in (e.display + e.filename).lower():
                continue
            on = self.checked.get(e.key, True)
            result = ''
            tags = () if on else ('off',)
            if e.key in res:
                rep, _ = res[e.key]
                if rep.error:
                    result = '⚠ 실패'
                    tags = ('warn',)
                else:
                    result = '채움 %d' % len(rep.filled)
                    if rep.nodata:
                        result += ' · 빈칸 %d' % len(rep.nodata)
                    if rep.manual:
                        result += ' · 확인 %d' % len(rep.manual)
                        tags = ('warn',)
            elif e.key in self.form_info:
                result = '칸 %d개' % self.form_info[e.key]['cap']
            self.tree.insert('', 'end', iid=e.key, values=('☑' if on else '☐', e.display, e.genre_text, e.filename, result),
                             tags=tags)
        self.update_sel_label()

    def tree_click(self, ev):
        if self.tree.identify_region(ev.x, ev.y) != 'cell':
            return
        iid = self.tree.identify_row(ev.y)
        col = self.tree.identify_column(ev.x)
        if iid and col == '#1':
            self.checked[iid] = not self.checked.get(iid, True)
            v = list(self.tree.item(iid, 'values'))
            v[0] = '☑' if self.checked[iid] else '☐'
            self.tree.item(iid, values=v, tags=() if self.checked[iid] else ('off',))
            self.update_sel_label()
            self.remember_checks()
            return 'break'

    def check_all(self, on):
        for e in self.visible_forms():
            self.checked[e.key] = on
        self.fill_tree()
        self.remember_checks()

    def remember_checks(self):
        self.settings['unchecked'] = [k for k, v in self.checked.items() if not v]
        write_json(SETTINGS, self.settings)
        self.refresh_progress()

    def update_sel_label(self):
        if not hasattr(self, 'sel_lbl'):
            return
        vis = self.visible_forms()
        n = sum(1 for e in vis if self.checked.get(e.key, True))
        self.refresh_submit()
        self.sel_lbl.configure(text=('%d / %d개 선택' % (n, len(vis))) if self.forms else '양식 묶음을 먼저 골라 주세요')

    # ------------------------------------------------------------------ 미리보기
    def preview(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, '목록에서 양식을 하나 클릭한 뒤 「미리보기」를 눌러 주세요.')
            return
        e = next((x for x in self.forms if x.key == sel[0]), None)
        if e is None:
            return
        try:
            _, rep = fill_hwpx(e.read(), copy.deepcopy(self.project), e.display, dry_run=True)
        except Exception as ex:
            messagebox.showerror(APP_NAME, '미리보기 실패: %s' % ex)
            return
        win = tk.Toplevel(self)
        win.title('미리보기 — %s' % e.display)
        win.geometry('760x640')
        win.configure(bg=BG)
        tk.Label(win, text=e.display, bg=BG, fg=INK, font=F_(14, 'bold')).pack(anchor='w', padx=20, pady=(16, 0))
        tk.Label(win, text=e.filename, bg=BG, fg=SUB, font=F_(9)).pack(anchor='w', padx=20)
        t = tk.Text(win, wrap='word', font=F_(10), relief='flat', bg=CARD, padx=16, pady=12,
                    highlightthickness=1, highlightbackground=LINE)
        t.pack(fill='both', expand=True, padx=20, pady=12)
        t.tag_configure('h', font=F_(11, 'bold'), spacing1=10, spacing3=4)
        t.tag_configure('lab', font=F_(10, 'bold'))
        t.tag_configure('sub', foreground=SUB)
        t.tag_configure('warn', foreground=WARN)
        from tugo.values import SLOT_NAMES
        if rep.manual:
            t.insert('end', '직접 확인할 칸\n', 'h')
            for lab, why in rep.manual:
                t.insert('end', '• %s' % lab, 'lab')
                t.insert('end', ' — %s\n' % why, 'warn')
        if rep.nodata:
            t.insert('end', '입력한 정보가 없어 비워 둘 칸\n', 'h')
            for lab, slot in rep.nodata:
                t.insert('end', '• %s' % lab, 'lab')
                t.insert('end', '  → 「%s」을(를) 입력하면 채워져요\n' % SLOT_NAMES.get(slot, slot), 'sub')
        t.insert('end', '자동으로 채울 칸 (%d)\n' % len(rep.filled), 'h')
        for lab, slot, prev in rep.filled:
            t.insert('end', '• %s' % lab, 'lab')
            t.insert('end', '  ← %s\n' % prev, 'sub')
        if rep.warnings:
            t.insert('end', '참고\n', 'h')
            for w in rep.warnings:
                t.insert('end', '• %s\n' % w, 'warn')
        if rep.notes:
            t.insert('end', '출판사 투고 안내 (양식에서 발췌)\n', 'h')
            for n in rep.notes:
                t.insert('end', '• %s\n' % n, 'sub')
        t.configure(state='disabled')
        ttk.Button(win, text='닫기', command=win.destroy).pack(pady=(0, 14))

    # ------------------------------------------------------------------ 실행
    def missing_required(self):
        miss = []
        for sid, key, label, kind in F.required_keys():
            if kind == 'volume':
                ok = any((self.project.get(key + s) or '').strip() for s, _, _ in F.VOLUME_PARTS)
            else:
                ok = bool((self.project.get(key) or '').strip())
            if not ok:
                miss.append(label)
        if len([c for c in self.project.get('characters', []) if (c.get('name') or '').strip()]) < 1:
            miss.append('등장인물')
        return miss

    def run(self):
        if not self.forms:
            messagebox.showinfo(APP_NAME, '먼저 ① 양식 묶음(zip 또는 폴더)을 골라 주세요.')
            return
        targets = [e for e in self.visible_forms() if self.checked.get(e.key, True)]
        if not targets:
            messagebox.showinfo(APP_NAME, '만들 양식을 하나 이상 선택해 주세요.')
            return
        miss = self.missing_required()
        if miss:
            if not messagebox.askyesno(APP_NAME, '아직 비어 있는 필수 항목이 있어요:\n\n· %s\n\n비어 있는 칸은 양식에서도 빈칸으로 남아요.\n그래도 만들까요?'
                                       % '\n· '.join(miss[:10])):
                return
        base = self.out_var.get() or os.path.join(os.path.expanduser('~'), 'Documents', '투고양식_결과')
        title = re.sub(r'[\\/:*?"<>|]', ' ', self.project.get('title') or '작품').strip()[:30] or '작품'
        out_dir = os.path.join(base, '%s_%s' % (title, datetime.datetime.now().strftime('%Y%m%d_%H%M')))
        self.run_btn.configure(state='disabled')
        self.open_dir_btn.configure(state='disabled')
        self.open_rep_btn.configure(state='disabled')
        self.run_bar['value'] = 0
        self.run_status.configure(text='시작하는 중…')
        project = copy.deepcopy(self.project)

        def work():
            try:
                results = run_batch(targets, project, out_dir,
                                    progress=lambda i, n, e, rep: self.q.put(('progress', i, n, e, rep)))
                report = build_report(results, project, out_dir)
                write_json(os.path.join(out_dir, '입력한_작품정보(백업).json'), project)
                self.q.put(('done', results, out_dir, report))
            except Exception:
                self.q.put(('error', traceback.format_exc(limit=3)))
        threading.Thread(target=work, daemon=True).start()

    def on_done(self, results, out_dir, report):
        self.results = results
        self.last_out, self.last_report = out_dir, report
        self.run_btn.configure(state='normal')
        self.open_dir_btn.configure(state='normal')
        self.open_rep_btn.configure(state='normal')
        ok = [r for r in results if not r[1].error]
        bad = len(results) - len(ok)
        filled = sum(len(r[1].filled) for r in ok)
        nodata = sum(len(r[1].nodata) for r in ok)
        manual = sum(len(r[1].manual) for r in ok)
        self.run_status.configure(text='끝! 양식 %d개 완성 · 채운 칸 %d%s' % (len(ok), filled, (' · 실패 %d' % bad) if bad else ''))
        self.fill_tree()
        msg = '양식 %d개를 만들었어요.\n\n· 자동으로 채운 칸: %d\n· 입력 정보가 없어 빈 칸: %d\n· 직접 확인할 칸: %d' % (
            len(ok), filled, nodata, manual)
        if bad:
            msg += '\n· 만들지 못한 양식: %d (보고서 참고)' % bad
        msg += '\n\n결과 보고서를 열어 볼까요?'
        if messagebox.askyesno(APP_NAME, msg):
            open_path(report)

    def open_result_dir(self):
        if self.last_out and os.path.isdir(self.last_out):
            open_path(self.last_out)

    def open_report(self):
        if self.last_report and os.path.exists(self.last_report):
            open_path(self.last_report)

    # ------------------------------------------------------------------ 테마 색
    def show_theme_picker(self):
        win = tk.Toplevel(self)
        win.title('테마 색상')
        win.configure(bg=CARD)
        win.resizable(False, False)
        win.transient(self)
        tk.Label(win, text='테마 색상', bg=CARD, fg=INK, font=F_(13, 'bold')).pack(anchor='w', padx=20, pady=(16, 2))
        tk.Label(win, text='고른 색에 맞춰 사이드바·버튼·배경 색이 함께 바뀌어요.', bg=CARD, fg=SUB,
                 font=F_(9)).pack(anchor='w', padx=20, pady=(0, 10))
        grid = tk.Frame(win, bg=CARD)
        grid.pack(padx=16, pady=4)
        current = (self.settings.get('theme_accent') or TH.DEFAULT).upper()
        for i, (name, color) in enumerate(TH.PRESETS):
            cell = tk.Frame(grid, bg=CARD, cursor='hand2')
            cell.grid(row=i // 5, column=i % 5, padx=6, pady=6)
            pal = TH.palette(color)
            sw = tk.Canvas(cell, width=56, height=40, bg=CARD, highlightthickness=2,
                           highlightbackground=INK if color.upper() == current else LINE)
            sw.create_rectangle(0, 0, 20, 42, fill=pal['SIDE'], outline='')
            sw.create_rectangle(20, 0, 58, 42, fill=pal['BG'], outline='')
            sw.create_rectangle(26, 22, 52, 34, fill=pal['ACCENT'], outline='')
            sw.pack()
            lb = tk.Label(cell, text=name, bg=CARD, fg=INK, font=F_(8))
            lb.pack()
            for w in (cell, sw, lb):
                w.bind('<Button-1>', lambda e, c=color: (win.destroy(), self.set_theme(c)))
        row = tk.Frame(win, bg=CARD)
        row.pack(fill='x', padx=20, pady=(10, 16))

        def custom():
            from tkinter import colorchooser
            c = colorchooser.askcolor(color=current, title='포인트 색 고르기', parent=win)
            if c and c[1]:
                win.destroy()
                self.set_theme(c[1])
        ttk.Button(row, text='직접 고르기…', command=custom, style='Small.TButton').pack(side='left')
        ttk.Button(row, text='기본으로', command=lambda: (win.destroy(), self.set_theme(TH.DEFAULT)),
                   style='Small.TButton').pack(side='left', padx=6)
        ttk.Button(row, text='닫기', command=win.destroy, style='Small.TButton').pack(side='right')

    def set_theme(self, accent):
        if not TH.valid(accent):
            return
        self.settings['theme_accent'] = accent.upper()
        write_json(SETTINGS, self.settings)
        apply_theme(accent)
        self.rebuild_ui()

    def rebuild_ui(self):
        """화면을 새 색으로 다시 그린다(입력 내용·양식 목록·선택 상태는 그대로)."""
        step = self.step_idx
        genre, genre_auto = self.genre_var.get(), self.genre_auto
        search = self.search_var.get()
        run_text = self.run_status.cget('text')
        last_out, last_report = self.last_out, self.last_report
        forms_text, forms_fg = self.forms_info.cget('text'), self.forms_info.cget('fg')
        for w in self.winfo_children():
            w.destroy()
        self.vars, self.usage_labels = {}, {}
        self.configure(bg=BG)
        self._style()
        self._build()
        self.load_into_widgets()
        self.search_var.set(search)
        self.forms_info.configure(text=forms_text, fg=OK if forms_fg not in (WARN, SUB) and self.forms else forms_fg)
        self.last_out, self.last_report = last_out, last_report
        self.run_status.configure(text=run_text)
        if last_out:
            self.open_dir_btn.configure(state='normal')
            self.open_rep_btn.configure(state='normal')
        self.update_usage_labels()
        self.genre_auto = genre_auto
        if self.forms:
            self.set_genre(genre)
        self.show_step(step)

    def _set_icon(self):
        base = getattr(sys, '_MEIPASS', APP_DIR)
        png = os.path.join(base, 'assets', 'icon.png')
        ico = os.path.join(base, 'assets', 'icon.ico')
        try:
            if os.path.exists(ico) and sys.platform == 'win32':
                self.iconbitmap(default=ico)
            elif os.path.exists(png):
                self._icon_img = tk.PhotoImage(file=png)
                self.iconphoto(True, self._icon_img)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ 자동 업데이트
    def manifest_url(self):
        return UP.source_url(APP_DIR, BUNDLE_DIR)

    def check_updates(self, manual=False):
        url = self.manifest_url()
        if not url:
            if manual:
                messagebox.showinfo(APP_NAME, '업데이트 주소가 설정돼 있지 않아요(update_source.json).')
            return
        cur_data = getattr(self, 'data_version', '') or ''
        auto_data = self.settings.get('auto_update', True) or manual

        def work():
            try:
                res = UP.check(url, VERSION, cur_data)
            except Exception as ex:
                self.q.put(('upd_done', manual, '업데이트를 확인하지 못했어요.\n(인터넷 연결을 확인해 주세요: %s)' % ex))
                return
            lines = []
            if res['data'] and auto_data:
                d = res['data']
                dest = os.path.join(FORMS_DIR, '투고양식_묶음_%s.zip' % re.sub(r'[^0-9]', '', d['version']))
                try:
                    UP.download(d['url'], dest, d.get('sha256'))
                    self.q.put(('upd_data', dest, d['version']))
                    lines.append('양식·투고처를 %s 기준으로 새로 받았어요.' % d['version'])
                except Exception as ex:
                    lines.append('새 양식을 받지 못했어요: %s' % ex)
            else:
                lines.append('양식·투고처는 최신이에요(%s 기준).' % (cur_data or '-'))
            if res['app']:
                self.q.put(('upd_app', res['app']))
                lines.append('프로그램 새 버전 v%s이 있어요. 위쪽 알림을 눌러 설치하세요.' % res['app']['version'])
            else:
                lines.append('프로그램은 최신 버전(v%s)이에요.' % VERSION)
            self.q.put(('upd_done', manual, '\n'.join(lines)))
        threading.Thread(target=work, daemon=True).start()

    def show_update_banner(self):
        info = getattr(self, '_app_update', None)
        if not info or not self.update_banner.winfo_exists():
            return
        self.update_banner.configure(text='⬆ 새 버전 v%s 받기' % info['version'], bg=ACCENT)
        if not self.update_banner.winfo_ismapped():
            # 창이 좁아도 버튼이 밀려나지 않게 부제 자리에 알림을 띄운다
            self.subtitle_lbl.pack_forget()
            self.update_banner.pack(side='left', padx=(4, 0), pady=10)

    def install_update(self):
        info = getattr(self, '_app_update', None)
        if not info:
            return
        notes = info.get('notes') or []
        text = '새 버전 v%s이 있어요.%s' % (info['version'], ('\n\n· ' + '\n· '.join(notes)) if notes else '')
        pkg = info.get(UP.platform_key()) or {}
        if IS_MAC or not pkg.get('url'):
            if messagebox.askyesno(APP_NAME, text + '\n\n내려받는 페이지를 열까요?'):
                self.open_url(pkg.get('url') or info.get('page', ''))
            return
        if not messagebox.askyesno(APP_NAME, text + '\n\n설치 파일을 내려받을까요?'):
            return
        win = tk.Toplevel(self)
        win.title('새 버전 받는 중')
        win.configure(bg=CARD)
        win.transient(self)
        tk.Label(win, text='v%s 설치 파일을 받는 중이에요…' % info['version'], bg=CARD, fg=INK,
                 font=F_(10)).pack(padx=24, pady=(18, 8))
        self._dl_bar = ttk.Progressbar(win, length=320, mode='determinate')
        self._dl_bar.pack(padx=24, pady=(0, 20))
        self._dl_win = win
        dest = os.path.join(os.path.expanduser('~'), 'Downloads', os.path.basename(pkg['url'].split('?')[0]))

        def work():
            try:
                UP.download(pkg['url'], dest, pkg.get('sha256'),
                            progress=lambda d, t: self.q.put(('upd_dl', d, t)), timeout=60)
                self.q.put(('upd_installer', dest, None))
            except Exception as ex:
                self.q.put(('upd_installer', None, str(ex)))
        threading.Thread(target=work, daemon=True).start()

    def _installer_ready(self, path, err):
        if getattr(self, '_dl_win', None) is not None and self._dl_win.winfo_exists():
            self._dl_win.destroy()
        if err or not path:
            messagebox.showerror(APP_NAME, '새 버전을 받지 못했어요.\n%s' % (err or ''))
            return
        if messagebox.askyesno(APP_NAME, '받기 완료: %s\n\n지금 설치할까요? 프로그램이 닫히고 설치가 시작돼요.\n'
                                         '(입력한 내용은 자동 저장돼 그대로 남아요)' % os.path.basename(path)):
            self.autosave()
            open_path(path)
            self.after(300, self.on_close)
        else:
            open_path(os.path.dirname(path))

    # ------------------------------------------------------------------ 도움말
    def show_help(self):
        win = tk.Toplevel(self)
        win.title('도움말')
        win.geometry('640x560')
        win.configure(bg=BG)
        t = tk.Text(win, wrap='word', font=F_(10), relief='flat', bg=CARD, padx=18, pady=14, spacing1=3,
                    highlightthickness=1, highlightbackground=LINE)
        t.pack(fill='both', expand=True, padx=18, pady=18)
        t.tag_configure('h', font=F_(12, 'bold'), spacing1=12, spacing3=4)
        parts = [
            ('h', '이렇게 쓰면 돼요\n'),
            ('', '1. 왼쪽 순서대로 내용을 채워요. 「필수」 표시가 있는 칸이 가장 많이 쓰여요.\n'
                 '2. 칸 이름 옆 「양식 N곳에서 사용」을 보면 어떤 칸이 중요한지 알 수 있어요.\n'
                 '3. 마지막 「일괄 작성 · 저장」에서 양식 묶음 zip을 고르고 「▶ 선택한 양식 일괄 저장」을 눌러요.\n'
                 '   고른 양식이 모두 채워져 저장 위치의 새 폴더에 한꺼번에 저장돼요.\n'
                 '4. 결과 보고서에서 빈칸·직접 확인할 칸을 확인하고, 한컴오피스로 열어 마무리해요.\n'),
            ('h', '저장은 어떻게 되나요?\n'),
            ('', '입력하는 즉시 자동 저장돼요. 프로그램을 껐다 켜도 그대로 남아 있어요.\n'
                 '작품별로 따로 보관하려면 「다른 이름으로 저장」으로 작품 파일(.json)을 만들어 두세요.\n'
                 '「새 작품」을 누르면 작가 정보는 남기고 작품 내용만 비워요.\n'),
            ('h', '정확하게 들어가게 하는 요령\n'),
            ('', '· 등장인물의 주인공 두 명에게 「공」「수」를 정해 주세요.\n'
                 '· 분량은 공백 포함/미포함을 둘 다 적으면, 양식이 요구하는 기준에 맞춰 들어가요.\n'
                 '· 줄거리는 기·승·전·결로 나눠 쓰고, 「줄거리 요약」도 따로 써 두세요.\n'
                 '· 양식 목록에서 하나를 고르고 「미리보기」를 누르면 어디에 무엇이 들어갈지 미리 볼 수 있어요.\n'),
            ('h', '업데이트\n'),
            ('', '· 켤 때 새 양식·투고처가 있으면 알아서 받아 반영해요(아래에서 끌 수 있어요).\n'
                 '· 프로그램 새 버전이 나오면 위쪽에 「⬆ 새 버전 받기」가 보여요. 누를 때만 받아서 설치해요.\n'),
            ('h', '만든 곳\n'),
            ('', '· 「BL 투고 양식 자동 작성기」(제작: 정체불명위스키)의 흐름을 바탕으로 새로 만든 프로그램이에요.\n'
                 '· 양식은 각 출판사가 공개한 투고 양식이고, 투고처는 투고하다(toogohada.com)·출판사 안내를 참고했어요.\n'),
            ('h', '알아 두세요\n'),
            ('', '· 원본 양식 파일은 바뀌지 않아요. 결과는 저장 위치에 새 폴더로 만들어져요.\n'
                 '· 원고 본문은 넣지 않아요. 출판사 안내대로 원고를 붙이거나 첨부해 주세요.\n'
                 '· 출판사마다 특이한 칸(에피소드 진행안 등)은 보고서에 「직접 확인」으로 표시돼요.\n'),
        ]
        for tag, txt in parts:
            t.insert('end', txt, tag)
        t.configure(state='disabled')
        bar = tk.Frame(win, bg=BG)
        bar.pack(fill='x', padx=18, pady=(0, 14))
        ver = '프로그램 v%s · 양식·투고처 %s 기준' % (VERSION, getattr(self, 'data_version', '') or '-')
        tk.Label(bar, text=ver, bg=BG, fg=SUB, font=F_(9)).pack(side='left')
        auto = tk.BooleanVar(value=self.settings.get('auto_update', True))

        def toggle():
            self.settings['auto_update'] = bool(auto.get())
            write_json(SETTINGS, self.settings)
        ttk.Checkbutton(bar, text='켤 때 자동 업데이트', variable=auto, command=toggle).pack(side='left', padx=12)
        ttk.Button(bar, text='닫기', command=win.destroy).pack(side='right')
        ttk.Button(bar, text='지금 업데이트 확인', command=lambda: self.check_updates(manual=True)).pack(side='right',
                                                                                                padx=6)


def main():
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    app = App()
    app.mainloop()


if __name__ == '__main__':
    main()
