# -*- coding: utf-8 -*-
"""프로그램 아이콘 그리기: 원고지 칸이 비치는 종이비행기가 원고를 싣고 날아가는 모양.

사용: python tools/make_icon.py   → assets/icon.png, assets/icon.ico
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

N = 1024
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, 'assets')


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def rounded_mask(size, r):
    m = Image.new('L', (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size - 1, size - 1), radius=r, fill=255)
    return m


def background():
    # 왼쪽 위 보라 → 오른쪽 아래 코랄 대각선 그라데이션
    top, bot = (93, 63, 211), (247, 112, 120)
    img = Image.new('RGBA', (N, N))
    px = img.load()
    for y in range(N):
        for x in range(N):
            t = (x * 0.45 + y * 0.55) / N
            px[x, y] = lerp(top, bot, min(1, max(0, t))) + (255,)
    # 위쪽 은은한 빛
    glow = Image.new('L', (N, N), 0)
    ImageDraw.Draw(glow).ellipse((-200, -380, 900, 420), fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    white = Image.new('RGBA', (N, N), (255, 255, 255, 255))
    img = Image.composite(white, img, glow)
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    img = background()
    d = ImageDraw.Draw(img, 'RGBA')

    # 날아온 길: 점선 곡선
    pts = []
    for i in range(0, 101):
        t = i / 100.0
        x = 150 + 420 * t
        y = 800 - 170 * math.sin(t * math.pi * 0.9) - 120 * t
        pts.append((x, y))
    for i in range(0, len(pts) - 1, 6):
        d.line([pts[i], pts[min(i + 3, len(pts) - 1)]], fill=(255, 255, 255, 170), width=22)

    # 종이비행기(세 면): 코, 왼쪽 날개 끝, 꼬리, 가운데 접힘
    nose = (845, 215)
    left = (210, 470)
    tail = (560, 840)
    fold = (500, 560)
    mid = (620, 600)
    # 아래 그림자
    shadow = Image.new('L', (N, N), 0)
    ImageDraw.Draw(shadow).polygon([(nose[0] + 18, nose[1] + 30), (left[0] + 18, left[1] + 30),
                                    (tail[0] + 18, tail[1] + 30)], fill=110)
    shadow = shadow.filter(ImageFilter.GaussianBlur(28))
    img.paste((40, 20, 80), (0, 0), shadow)
    d = ImageDraw.Draw(img, 'RGBA')
    # 큰 날개(원고지 면)
    wing = [nose, left, fold]
    d.polygon(wing, fill=(255, 255, 255, 255))
    # 아래 날개
    d.polygon([nose, fold, tail], fill=(236, 230, 252, 255))
    # 접힌 몸통
    d.polygon([nose, fold, mid], fill=(205, 192, 245, 255))

    # 큰 날개 위 원고지 칸: 날개 안쪽만 보이게 마스크
    grid = Image.new('RGBA', (N, N), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    step = 58
    for k in range(-20, 30):
        # 날개 방향(코→왼쪽 끝)과 나란한 줄 / 수직 줄
        ax, ay = left[0] - nose[0], left[1] - nose[1]
        L = math.hypot(ax, ay)
        ux, uy = ax / L, ay / L
        vx, vy = -uy, ux
        cx, cy = nose[0] + vx * k * step, nose[1] + vy * k * step
        gd.line([(cx - ux * 2000, cy - uy * 2000), (cx + ux * 2000, cy + uy * 2000)], fill=(196, 170, 240, 255),
                width=7)
        cx, cy = nose[0] + ux * k * step, nose[1] + uy * k * step
        gd.line([(cx - vx * 2000, cy - vy * 2000), (cx + vx * 2000, cy + vy * 2000)], fill=(196, 170, 240, 160),
                width=5)
    m = Image.new('L', (N, N), 0)
    inset = [(nose[0] - 60, nose[1] + 40), (left[0] + 95, left[1] - 5), (fold[0] - 20, fold[1] - 50)]
    ImageDraw.Draw(m).polygon(inset, fill=255)
    img.paste(grid, (0, 0), Image.composite(grid.split()[3], Image.new('L', (N, N), 0), m))
    d = ImageDraw.Draw(img, 'RGBA')
    # 접는 선
    d.line([nose, fold], fill=(150, 125, 225, 255), width=12)

    # 반짝임(네 갈래 별)
    def sparkle(cx, cy, r, a=255):
        d.polygon([(cx, cy - r), (cx + r * 0.22, cy - r * 0.22), (cx + r, cy), (cx + r * 0.22, cy + r * 0.22),
                   (cx, cy + r), (cx - r * 0.22, cy + r * 0.22), (cx - r, cy), (cx - r * 0.22, cy - r * 0.22)],
                  fill=(255, 255, 255, a))
    sparkle(220, 230, 70)
    sparkle(860, 560, 42, 220)

    # 둥근 사각형으로 잘라내기
    out = Image.new('RGBA', (N, N), (0, 0, 0, 0))
    out.paste(img, (0, 0), rounded_mask(N, 230))
    out.resize((512, 512), Image.LANCZOS).save(os.path.join(OUT, 'icon.png'))
    out.save(os.path.join(OUT, 'icon.ico'), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128),
                                                     (256, 256)])
    # 작은 크기 미리보기(확인용)
    prev = Image.new('RGBA', (16 + 24 + 32 + 48 + 256 + 60, 260), (245, 245, 245, 255))
    x = 10
    for sz in (16, 24, 32, 48, 256):
        prev.paste(out.resize((sz, sz), Image.LANCZOS), (x, 260 - sz - 2), out.resize((sz, sz), Image.LANCZOS))
        x += sz + 10
    prev.save(os.path.join(OUT, '_icon_preview.png'))
    print('saved', OUT)


if __name__ == '__main__':
    main()
