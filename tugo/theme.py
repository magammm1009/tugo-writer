# -*- coding: utf-8 -*-
"""테마 색: 대표 색(포인트 색) 하나로 화면 전체 색을 만든다."""
import colorsys

# 미리 준비한 팔레트 (이름, 포인트 색)
PRESETS = [
    ('라벤더', '#6D4FD0'),
    ('블루베리', '#3B5BDB'),
    ('하늘', '#1C7ED6'),
    ('민트', '#0C8F7A'),
    ('올리브', '#5C7C2F'),
    ('호박', '#D9480F'),
    ('코랄', '#E8590C'),
    ('체리', '#D6336C'),
    ('자두', '#9C36B5'),
    ('먹', '#495057'),
]
DEFAULT = PRESETS[0][1]


def _rgb(hexs):
    hexs = hexs.lstrip('#')
    return tuple(int(hexs[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _hex(rgb):
    return '#%02X%02X%02X' % tuple(max(0, min(255, int(round(c * 255)))) for c in rgb)


def _hls(h, l, s):
    return _hex(colorsys.hls_to_rgb(h, max(0.0, min(1.0, l)), max(0.0, min(1.0, s))))


def valid(hexs):
    try:
        _rgb(hexs)
        return len(hexs.lstrip('#')) == 6
    except (ValueError, AttributeError):
        return False


def palette(accent):
    """포인트 색 → 화면에 쓰는 색 이름들"""
    if not valid(accent):
        accent = DEFAULT
    h, l, s = colorsys.rgb_to_hls(*_rgb(accent))
    # 너무 밝은 색을 골라도 글씨가 보이도록 포인트 색 밝기를 제한
    l_acc = min(l, 0.55)
    acc = _hls(h, l_acc, s)
    ts = min(s, 0.6)          # 연한 색들의 채도
    return {
        'ACCENT': acc,
        'ACCENT_D': _hls(h, l_acc * 0.85, s),
        'BG': _hls(h, 0.972, ts * 0.55),
        'CARD': '#FFFFFF',
        'SIDE': _hls(h, 0.20, min(s, 0.32)),
        'SIDE_SEL': _hls(h, 0.29, min(s, 0.28)),
        'SIDE_FG': _hls(h, 0.85, ts * 0.55),
        'SIDE_MUTED': _hls(h, 0.66, ts * 0.35),
        'SIDE_OK': '#8FE0B4',
        'INK': _hls(h, 0.15, ts * 0.3),
        'SUB': _hls(h, 0.45, ts * 0.18),
        'LINE': _hls(h, 0.90, ts * 0.45),
        'CHIP': _hls(h, 0.94, ts * 0.55),
        'CHIP_HOV': _hls(h, 0.90, ts * 0.55),
        'SEL': _hls(h, 0.90, ts * 0.85),
        'HEAD': _hls(h, 0.95, ts * 0.6),
        'BADGE': _hls(h, 0.95, min(1.0, ts * 1.6)),
        'TROUGH': _hls(h, 0.92, ts * 0.4),
        'ACC_DIS': _hls(h, 0.80, ts * 0.8),
        'ACC_DIS_FG': _hls(h, 0.97, ts * 0.8),
        'BTN_DIS': _hls(h, 0.96, ts * 0.3),
        'DIM': _hls(h, 0.70, ts * 0.18),
        'MUTED': _hls(h, 0.65, ts * 0.15),
        'MUTED2': _hls(h, 0.74, ts * 0.18),
        'OK': '#1F8A5B',
        'WARN': '#B7791F',
    }
