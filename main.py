#!/usr/bin/env python3
"""news-image-20261124: one day's world news, Tuesday 24 November 2026.

Pure Python stdlib. Draws a 1024x1024 newspaper front page from glyph
atlases (atlas_blob.py, generated at build time from Liberation fonts) and
writes exactly one file: $MAKEFUN_OUTPUT_DIR/entry.png. No network, no
writes anywhere else, deterministic output.
"""
import base64
import binascii
import io
import json
import math
import os
import struct
import sys
import zipfile
import zlib

import importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
_SPEC = importlib.util.spec_from_file_location(
    "atlas_blob_20261124", os.path.join(_HERE, "atlas_blob.py"))
_BLOB_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_BLOB_MOD)
BLOB = _BLOB_MOD.BLOB

W = 1024
H = 1024

CREAM = (247, 241, 227)
CREAM2 = (241, 233, 214)
NAVY = (27, 42, 74)
NAVY2 = (38, 56, 96)
RED = (176, 58, 46)
RED_D = (138, 38, 30)
SAGE = (122, 139, 111)
SAGE_D = (96, 112, 86)
GOLD = (198, 158, 72)
SKY = (169, 201, 215)
SKY_D = (110, 152, 178)
SKY_N = (24, 38, 66)
SAND = (233, 215, 179)
SAND_D = (214, 190, 150)
INK = (28, 28, 26)
GREY = (90, 86, 78)
WHITE = (255, 255, 255)
TEAL = (64, 122, 122)
ORANGE = (214, 116, 44)
FLAME = (232, 122, 40)
SMOKE = (120, 118, 110)


# ---------------------------------------------------------------- PNG codec
def _chunk(typ, data):
    out = struct.pack(">I", len(data)) + typ + data
    return out + struct.pack(">I", binascii.crc32(typ + data) & 0xFFFFFFFF)


def encode_png(w, h, rgb):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += rgb[y * w * 3:(y + 1) * w * 3]
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", ihdr)
    png += _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += _chunk(b"IEND", b"")
    return png


def decode_gray_png(data):
    """Decode an 8-bit grayscale non-interlaced PNG. Returns (w, h, bytes)."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8
    w = h = None
    idat = bytearray()
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", body[:10])
            assert depth == 8 and ctype == 0, "atlas must be 8-bit gray"
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
        pos += 12 + ln
    raw = zlib.decompress(bytes(idat))
    stride = w + 1
    assert len(raw) == h * stride
    out = bytearray(w * h)
    prev = bytearray(w)
    for y in range(h):
        f = raw[y * stride]
        row = bytearray(raw[y * stride + 1:(y + 1) * stride])
        if f == 0:
            pass
        elif f == 1:
            for i in range(1, w):
                row[i] = (row[i] + row[i - 1]) & 0xFF
        elif f == 2:
            for i in range(w):
                row[i] = (row[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(w):
                left = row[i - 1] if i else 0
                row[i] = (row[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(w):
                a = row[i - 1] if i else 0
                b = prev[i]
                c = prev[i - 1] if i else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                row[i] = (row[i] + pr) & 0xFF
        else:
            raise ValueError("bad filter %d" % f)
        out[y * w:(y + 1) * w] = row
        prev = row
    return w, h, bytes(out)


# ------------------------------------------------------------------- canvas
class Canvas:
    def __init__(self, w, h, bg):
        self.w = w
        self.h = h
        self.buf = bytearray(w * h * 3)
        self.rect(0, 0, w, h, bg)

    def _px(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.buf[i] = c[0]
            self.buf[i + 1] = c[1]
            self.buf[i + 2] = c[2]

    def rect(self, x, y, w, h, c):
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.w, x + w)
        y1 = min(self.h, y + h)
        for yy in range(y0, y1):
            i = (yy * self.w + x0) * 3
            for xx in range(x0, x1):
                self.buf[i] = c[0]
                self.buf[i + 1] = c[1]
                self.buf[i + 2] = c[2]
                i += 3

    def hline(self, x, y, w, c):
        self.rect(x, y, w, 1, c)

    def vline(self, x, y, h, c):
        self.rect(x, y, 1, h, c)

    def circle(self, cx, cy, r, c):
        self.ellipse(cx, cy, r, r, c)

    def ellipse(self, cx, cy, rx, ry, c):
        if rx <= 0 or ry <= 0:
            return
        for dy in range(-ry, ry + 1):
            t = 1.0 - (dy * dy) / float(ry * ry)
            if t < 0:
                continue
            dx = int(rx * math.sqrt(t))
            self.rect(cx - dx, cy + dy, dx * 2 + 1, 1, c)

    def ring(self, cx, cy, r, c, t=2):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                d = math.sqrt(dx * dx + dy * dy)
                if r - t < d <= r:
                    self._px(cx + dx, cy + dy, c)

    def line(self, x0, y0, x1, y1, c, t=1):
        dx = x1 - x0
        dy = y1 - y0
        steps = max(abs(dx), abs(dy), 1)
        for i in range(steps + 1):
            x = x0 + dx * i // steps
            y = y0 + dy * i // steps
            if t <= 1:
                self._px(x, y, c)
            else:
                self.circle(x, y, t // 2, c)

    def poly(self, pts, c):
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        for y in range(max(0, min(ys)), min(self.h, max(ys) + 1)):
            xs = []
            n = len(pts)
            for i in range(n):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % n]
                if (y0 <= y < y1) or (y1 <= y < y0):
                    xs.append(x0 + (y - y0) * (x1 - x0) / float(y1 - y0))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                self.rect(int(math.ceil(xs[k])), y,
                          int(math.floor(xs[k + 1])) - int(math.ceil(xs[k])) + 1,
                          1, c)

    def tri(self, x0, y0, x1, y1, x2, y2, c):
        self.poly([(x0, y0), (x1, y1), (x2, y2)], c)

    def vgrad(self, x, y, w, h, top, bot):
        for j in range(h):
            t = j / float(max(1, h - 1))
            c = (int(top[0] + (bot[0] - top[0]) * t),
                 int(top[1] + (bot[1] - top[1]) * t),
                 int(top[2] + (bot[2] - top[2]) * t))
            self.rect(x, y + j, w, 1, c)


# -------------------------------------------------------------------- fonts
class Font:
    def __init__(self, name, aw, ah, pixels, glyphs):
        self.name = name
        self.aw = aw
        self.ah = ah
        self.px = pixels
        self.g = glyphs

    def width(self, text):
        tot = 0
        for ch in text:
            m = self.g.get(str(ord(ch)))
            if m is None:
                raise ValueError("missing glyph %r in %s" % (ch, self.name))
            tot += m[4]
        return tot


def load_fonts():
    raw = zlib.decompress(base64.b64decode(BLOB))
    zf = zipfile.ZipFile(io.BytesIO(raw))
    metrics = json.loads(zf.read("metrics.json"))
    order = json.loads(zf.read("order.json"))
    fonts = {}
    for i, name in enumerate(order):
        w, h, px = decode_gray_png(zf.read("a%d.png" % i))
        assert (w, h) == (metrics[name]["w"], metrics[name]["h"])
        fonts[name] = Font(name, w, h, px, metrics[name]["g"])
    return fonts


FONTS = None


def F(name):
    return FONTS[name]


def blit_text(cv, x, baseline, font, text, color):
    """Draw text left-aligned at pen x, given baseline y. Returns end x."""
    pen = x
    for ch in text:
        m = font.g[str(ord(ch))]
        ax, ay, gw, gh, adv, dx, dy = m
        if gw and gh:
            for row in range(gh):
                sy = ay + row
                dy0 = baseline + dy + row
                if dy0 < 0 or dy0 >= cv.h:
                    continue
                for col in range(gw):
                    a = font.px[sy * font.aw + ax + col]
                    if a == 0:
                        continue
                    dx0 = pen + dx + col
                    if dx0 < 0 or dx0 >= cv.w:
                        continue
                    i = (dy0 * cv.w + dx0) * 3
                    if a == 255:
                        cv.buf[i] = color[0]
                        cv.buf[i + 1] = color[1]
                        cv.buf[i + 2] = color[2]
                    else:
                        cv.buf[i] = (color[0] * a + cv.buf[i] * (255 - a)) // 255
                        cv.buf[i + 1] = (color[1] * a + cv.buf[i + 1] * (255 - a)) // 255
                        cv.buf[i + 2] = (color[2] * a + cv.buf[i + 2] * (255 - a)) // 255
        pen += adv
    return pen


def text(cv, x, baseline, fname, s, color, align="l"):
    f = F(fname)
    if align == "c":
        x -= f.width(s) // 2
    elif align == "r":
        x -= f.width(s)
    return blit_text(cv, x, baseline, f, s, color)


def wrap(s, fname, maxw):
    """Greedy word wrap. Fails loudly on a split word or an overfull line."""
    f = F(fname)
    words = s.split(" ")
    lines = []
    cur = ""
    for wd in words:
        if f.width(wd) > maxw:
            raise ValueError("word too wide for column: %r (%s)" % (wd, fname))
        trial = wd if not cur else cur + " " + wd
        if f.width(trial) <= maxw:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    # Audit: no word may be split, no word lost, no line overfull.
    assert " ".join(lines) == " ".join(s.split(" ")), "wrap lost/split a word"
    for ln in lines:
        assert f.width(ln) <= maxw, "overfull line: %r" % ln
        for wd in ln.split(" "):
            assert wd in s.split(" "), "split word in line: %r" % wd
    return lines


def para(cv, x, y, fname, s, color, maxw, leading):
    """Draw a wrapped paragraph; y is the first baseline. Returns next y."""
    lines = wrap(s, fname, maxw)
    for ln in lines:
        text(cv, x, y, fname, ln, color)
        y += leading
    return y


# ------------------------------------------------------------------- scenes
def buildings(cv, x, y, w, h, cols, win):
    """Row of flat buildings filling (x,y,w,h); cols = list of (bw, bh, c)."""
    cx = x
    for bw, bh, c in cols:
        cv.rect(cx, y + h - bh, bw, bh, c)
        for wy in range(y + h - bh + 5, y + h - 4, 9):
            for wx in range(cx + 4, cx + bw - 3, 8):
                cv.rect(wx, wy, 4, 5, win)
        cx += bw


def flames(cv, x, y, s):
    """A cluster of flat flames, base at (x, y), scale s."""
    cv.tri(x - 3 * s, y, x, y - 7 * s, x + 3 * s, y, FLAME)
    cv.tri(x - 1 * s, y, x + 2 * s, y - 5 * s, x + 4 * s, y, ORANGE)
    cv.tri(x + 1 * s, y, x + 3 * s, y - 4 * s, x + 5 * s, y, GOLD)


def smoke(cv, x, y, r, c=SMOKE):
    cv.circle(x, y, r, c)
    cv.circle(x + r, y - r // 2, r * 3 // 4, c)
    cv.circle(x - r, y - r // 2, r * 2 // 3, c)


def waves(cv, x, y, w, c, n=6):
    for i in range(n):
        wx = x + (i * w) // n
        cv.line(wx, y + 3, wx + w // (n * 2), y, c, 2)


def ship(cv, x, y, w, h, hull, deck):
    cv.poly([(x, y), (x + w, y), (x + w - w // 8, y + h),
             (x + w // 8, y + h)], hull)
    cv.rect(x + w // 4, y - h // 2, w // 2, h // 2, deck)
    cv.rect(x + w // 3, y - h, w // 6, h // 2, deck)


def jet(cv, x, y, s, c):
    cv.poly([(x, y), (x + 9 * s, y - 2 * s), (x + 12 * s, y),
             (x + 9 * s, y + 2 * s)], c)
    cv.tri(x + 3 * s, y, x + 6 * s, y - 4 * s, x + 7 * s, y, c)
    cv.tri(x + 3 * s, y, x + 6 * s, y + 4 * s, x + 7 * s, y, c)


def person(cv, x, y, s, shirt, skin=(214, 178, 140)):
    cv.circle(x, y - 3 * s, 2 * s, skin)
    cv.rect(x - 2 * s, y - s, 4 * s, 5 * s, shirt)


def scene_nvidia(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (214, 228, 232), (247, 241, 227))
    cv.circle(x + w - 34, y + 46, 12, GOLD)
    cv.rect(x + 18, y + h - 78, w - 36, 78, NAVY)
    cv.rect(x + 18, y + h - 78, w - 36, 8, NAVY2)
    for wy in range(y + h - 64, y + h - 6, 12):
        for wx in range(x + 26, x + w - 14, 14):
            cv.rect(wx, wy, 8, 6, (120, 190, 120))
    cv.rect(x + w // 2 - 26, y + h - 30, 52, 30, (20, 32, 58))
    cv.tri(x + 30, y + 34, x + 52, y + 34, x + 41, y + 52, (118, 185, 0))
    cv.line(x + 14, y + h - 22, x + w - 96, y + 40, (34, 139, 34), 3)
    cv.tri(x + w - 102, y + 32, x + w - 80, y + 40, x + w - 102, y + 48,
           (34, 139, 34))
    cv.rect(x + 10, y + h - 12, w - 20, 4, SAGE_D)


def scene_sea(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, SKY_N, (58, 74, 110))
    for sx, sy in [(28, 18), (90, 30), (170, 14), (240, 26), (290, 16)]:
        cv.circle(x + sx, y + sy, 2, WHITE)
    cv.circle(x + w - 40, y + 30, 14, (232, 226, 200))
    cv.rect(x, y + h - 46, w, 46, (18, 52, 66))
    waves(cv, x + 6, y + h - 40, w - 12, (90, 140, 160))
    ship(cv, x + 24, y + h - 58, 118, 24, (86, 92, 100), (120, 126, 134))
    cv.line(x + 20, y + h - 32, x + 150, y + h - 32, (150, 190, 210), 2)
    cv.rect(x + 76, y + h - 82, 4, 18, (120, 126, 134))
    flames(cv, x + 56, y + h - 58, 4)
    flames(cv, x + 112, y + h - 58, 3)
    smoke(cv, x + 60, y + h - 96, 7)
    smoke(cv, x + 116, y + h - 92, 6)
    for dx, dy in [(200, 34), (236, 52), (268, 30)]:
        cv.circle(x + dx, y + dy, 4, (200, 200, 200))
        cv.line(x + dx, y + dy + 4, x + dx - 8, y + dy + 26, (200, 200, 200), 1)
        cv.line(x + dx, y + dy + 4, x + dx + 8, y + dy + 26, (200, 200, 200), 1)


def scene_tehran(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (226, 138, 74), (120, 60, 70))
    cv.circle(x + w - 44, y + 30, 18, (240, 200, 120))
    buildings(cv, x, y + 18, w, h - 66, [
        (34, 40, (74, 52, 66)), (26, 58, (58, 42, 54)),
        (40, 34, (74, 52, 66)), (30, 52, (58, 42, 54)),
        (36, 44, (74, 52, 66))], (240, 200, 120))
    cv.rect(x, y + h - 48, w, 48, (24, 52, 74))
    waves(cv, x + 6, y + h - 42, w - 12, (110, 160, 190))
    ship(cv, x + 26, y + h - 74, 120, 26, (196, 166, 116), (226, 202, 158))
    cv.rect(x + 190, y + h - 88, 3, 40, (200, 200, 200))
    cv.tri(x + 193, y + h - 88, x + 226, y + h - 80, x + 193, y + h - 72, RED)
    cv.rect(x + 210, y + h - 66, 60, 10, (110, 116, 124))
    flames(cv, x + 230, y + h - 66, 3)


def scene_nato(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, SKY, (226, 236, 238))
    cv.circle(x + 30, y + 18, 12, WHITE)
    cv.circle(x + 52, y + 24, 9, WHITE)
    cv.circle(x + w - 40, y + 16, 10, WHITE)
    cv.rect(x, y + h - 10, w, 10, SAGE)
    cv.ellipse(x + 46, y + 18, 44, 8, (150, 154, 158))
    cv.poly([(x + 46, y + 22), (x + 70, y + 14), (x + 134, y + 20),
             (x + 134, y + 24), (x + 70, y + 28)], (170, 174, 178))
    cv.tri(x + 60, y + 20, x + 78, y + 8, x + 84, y + 20, (150, 154, 158))
    cv.rect(x + 82, y + 10, 20, 4, (150, 154, 158))
    cv.circle(x + 92, y + 8, 7, (170, 174, 178))
    cv.line(x + 20, y + h - 6, x + 170, y + h - 6, RED, 2)
    cv.tri(x + 20, y + h - 11, x + 20, y + h - 1, x + 30, y + h - 6, RED)


def scene_cop(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (238, 232, 210), CREAM)
    cv.circle(x + 30, y + 38, 13, (80, 140, 190))
    cv.ellipse(x + 25, y + 33, 7, 4, SAGE)
    cv.ellipse(x + 34, y + 41, 5, 3, SAGE)
    cv.rect(x + 66, y + 14, 6, 22, RED)
    cv.circle(x + 69, y + 40, 6, RED)
    cv.rect(x + 96, y + 12, 30, 30, WHITE)
    cv.circle(x + 111, y + 27, 9, (40, 40, 40))
    cv.line(x + 103, y + 27, x + 111, y + 27, INK, 1)
    cv.line(x + 111, y + 27, x + 111, y + 21, INK, 1)
    cv.rect(x + 14, y + h - 26, w - 28, 8, (120, 84, 52))
    for i, sh in enumerate([(52, 110, 130), (76, 170, 90), (100, 60, 60),
                            (124, 200, 120), (148, 90, 160)]):
        person(cv, x + sh[0], y + h - 26, 3, (sh[1], sh[2], 140))
    cv.rect(x + w - 22, y + 14, 10, 30, (200, 200, 200))


def scene_flog(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (96, 30, 34), (52, 18, 22))
    cv.rect(x, y, 12, h, RED_D)
    cv.rect(x + w - 12, y, 12, h, RED_D)
    cv.poly([(x + w // 2 - 26, y), (x + w // 2 + 26, y),
             (x + w // 2 + 12, y + h - 20), (x + w // 2 - 12, y + h - 20)],
            (240, 220, 140))
    cv.rect(x + 14, y + h - 20, w - 28, 20, (40, 26, 20))
    cv.circle(x + w // 2, y + h - 36, 6, (214, 178, 140))
    cv.rect(x + w // 2 - 6, y + h - 30, 12, 18, (232, 228, 220))
    cv.rect(x + w // 2 + 12, y + h - 42, 3, 22, (200, 200, 200))
    cv.circle(x + w // 2 + 13, y + h - 46, 4, (220, 220, 220))
    cv.tri(x + 30, y + 22, x + 36, y + 14, x + 40, y + 24, GOLD)
    cv.tri(x + w - 40, y + 26, x + w - 34, y + 18, x + w - 30, y + 28, GOLD)


def scene_korea(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, SKY, (210, 226, 230))
    cv.circle(x + w - 30, y + 14, 10, (240, 230, 170))
    cv.rect(x, y + h - 16, w, 16, (40, 110, 150))
    waves(cv, x + 6, y + h - 12, w - 12, (160, 210, 230))
    cv.ellipse(x + 52, y + h - 22, 40, 12, SAGE_D)
    cv.tri(x + 72, y + h - 34, x + 96, y + h - 34, x + 84, y + h - 16, SAGE)
    jet(cv, x + 100, y + 14, 2, (60, 60, 66))
    cv.tri(x + 138, y + 10, x + 158, y + 10, x + 148, y + 26, RED)
    cv.rect(x + 146, y + 14, 4, 8, WHITE)
    cv.rect(x + 20, y + 12, 26, 12, WHITE)
    cv.rect(x + 20, y + 12, 26, 4, RED)


def scene_mexico(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (240, 200, 130), (232, 180, 110))
    cv.circle(x + 26, y + 14, 11, (250, 220, 130))
    cv.tri(x + 10, y + h - 14, x + 60, y + h - 14, x + 35, y + h - 30, (150, 110, 70))
    cv.tri(x + 60, y + h - 14, x + 120, y + h - 14, x + 90, y + h - 28, (170, 125, 80))
    cv.rect(x, y + h - 14, w, 14, (196, 150, 96))
    cv.rect(x + 24, y + h - 30, 66, 14, (150, 40, 36))
    cv.rect(x + 84, y + h - 27, 22, 11, (120, 30, 28))
    cv.circle(x + 40, y + h - 15, 5, INK)
    cv.circle(x + 92, y + h - 15, 5, INK)
    cv.rect(x + 130, y + h - 34, 6, 22, SAGE_D)
    cv.rect(x + 122, y + h - 28, 22, 5, SAGE_D)
    cv.circle(x + 150, y + 22, 3, (60, 60, 60))
    cv.line(x + 146, y + 26, x + 154, y + 34, (60, 60, 60), 1)


def scene_gaza(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (232, 190, 140), (200, 150, 110))
    buildings(cv, x, y + 6, w, 26, [
        (30, 20, (120, 100, 80)), (24, 26, (100, 84, 66)),
        (34, 18, (120, 100, 80)), (28, 24, (100, 84, 66))], (240, 220, 170))
    smoke(cv, x + 40, y + 10, 8)
    smoke(cv, x + 120, y + 10, 9)
    cv.rect(x, y + h - 14, w, 14, SAND_D)
    cv.tri(x + 60, y + h - 30, x + 96, y + h - 30, x + 78, y + h - 44, WHITE)
    cv.rect(x + 74, y + h - 40, 8, 7, RED)
    cv.rect(x + 70, y + h - 37, 16, 4, RED)
    cv.rect(x + 120, y + h - 28, 34, 14, (200, 200, 200))


def scene_delta(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, SKY, (228, 236, 240))
    cv.circle(x + 24, y + 16, 10, WHITE)
    cv.circle(x + 44, y + 22, 8, WHITE)
    cv.rect(x + 16, y + h - 40, 6, 40, (120, 120, 124))
    cv.rect(x + 10, y + h - 46, 18, 8, (90, 90, 96))
    cv.rect(x, y + h - 14, w, 14, (90, 96, 100))
    cv.rect(x, y + h - 10, w, 3, WHITE)
    cv.ellipse(x + 52, y + h - 34, 52, 9, WHITE)
    cv.rect(x + 96, y + h - 46, 10, 14, (180, 30, 40))
    cv.rect(x + 52, y + h - 38, 44, 6, (30, 60, 120))
    cv.tri(x + 60, y + h - 38, x + 78, y + h - 48, x + 84, y + h - 38, (30, 60, 120))
    cv.circle(x + 150, y + h - 50, 4, GOLD)


def scene_berlin(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (200, 208, 212), (226, 228, 226))
    cv.rect(x + 20, y + h - 30, w - 40, 30, (150, 146, 138))
    cv.tri(x + 40, y + h - 30, x + w - 40, y + h - 30,
           x + w // 2, y + h - 44, (120, 116, 110))
    for wx in range(x + 30, x + w - 16, 14):
        cv.rect(wx, y + h - 24, 7, 10, (60, 60, 64))
    cv.rect(x + w - 52, y + 12, 38, 26, NAVY)
    cv.line(x + w - 48, y + 32, x + w - 38, y + 22, (80, 200, 120), 2)
    cv.line(x + w - 38, y + 22, x + w - 28, y + 28, (240, 200, 80), 2)
    cv.line(x + w - 28, y + 28, x + w - 18, y + 18, (80, 200, 120), 2)
    cv.rect(x + 16, y + 12, 4, 26, (200, 200, 200))
    cv.tri(x + 20, y + 12, x + 40, y + 17, x + 20, y + 22, (210, 170, 40))


def scene_grok(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (30, 30, 40), (70, 60, 80))
    cv.rect(x + w // 2 - 26, y + 8, 52, h - 16, (20, 20, 26))
    cv.rect(x + w // 2 - 22, y + 12, 44, h - 24, (240, 242, 245))
    cv.rect(x + w // 2 - 16, y + 20, 32, 10, (200, 60, 60))
    cv.rect(x + w // 2 - 16, y + 34, 26, 8, (180, 180, 185))
    cv.rect(x + w // 2 - 16, y + 46, 30, 8, (180, 180, 185))
    cv.circle(x + w // 2, y + h - 18, 8, (40, 40, 48))
    cv.circle(x + w // 2 - 3, y + h - 20, 2, (120, 220, 120))
    cv.circle(x + w // 2 + 3, y + h - 20, 2, (120, 220, 120))
    cv.tri(x + 22, y + 16, x + 34, y + 16, x + 28, y + 30, RED)
    cv.rect(x + 26, y + 20, 4, 6, WHITE)
    cv.tri(x + w - 34, y + h - 30, x + w - 22, y + h - 30,
           x + w - 28, y + h - 44, GOLD)


def scene_quake(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (200, 220, 228), (150, 190, 205))
    cv.circle(x + 26, y + 16, 11, (250, 230, 150))
    cv.rect(x, y + h - 22, w, 22, (30, 100, 140))
    waves(cv, x + 6, y + h - 18, w - 12, (190, 230, 245))
    cv.ellipse(x + 96, y + h - 24, 26, 10, (170, 200, 215))
    cv.ellipse(x + 102, y + h - 26, 14, 7, (150, 185, 200))
    cv.tri(x + 56, y + h - 34, x + 96, y + h - 34, x + 76, y + h - 46, (90, 80, 70))
    smoke(cv, x + 76, y + h - 40, 4)
    cv.line(x + 14, y + 36, x + 34, y + 36, RED, 2)
    cv.line(x + 34, y + 36, x + 44, y + 28, RED, 2)
    cv.line(x + 44, y + 28, x + 54, y + 44, RED, 2)
    cv.line(x + 54, y + 44, x + 66, y + 36, RED, 2)


def motif(cv, x, y, w, h, kind):
    """Tiny scene strip for a brief tile: coloured band + 2 small shapes."""
    bands = {"sea": (40, 110, 150), "fire": (200, 90, 40),
             "city": (90, 96, 104), "plane": (110, 152, 178),
             "flag": (176, 58, 46), "quake": (30, 100, 140),
             "court": (96, 112, 86), "sport": (64, 122, 122),
             "tech": (38, 56, 96), "money": (198, 158, 72),
             "health": (150, 60, 60), "nature": (122, 139, 111)}
    cv.rect(x, y, w, h, bands.get(kind, (120, 118, 110)))
    mid = y + h // 2
    if kind == "sea":
        cv.line(x + 3, mid + 1, x + w - 3, mid + 1, WHITE, 1)
        cv.tri(x + w // 2 - 4, mid - 2, x + w // 2 + 4, mid - 2,
               x + w // 2, mid - 5, WHITE)
    elif kind == "fire":
        cv.tri(x + w // 2 - 3, mid + 2, x + w // 2, mid - 4,
               x + w // 2 + 3, mid + 2, GOLD)
    elif kind == "plane":
        jet(cv, x + 3, mid, 1, WHITE)
    elif kind == "quake":
        cv.line(x + 3, mid, x + w - 3, mid, WHITE, 1)
        cv.line(x + w // 2 - 2, mid, x + w // 2, mid - 3, WHITE, 1)
    elif kind == "sport":
        cv.circle(x + w // 2, mid, 3, WHITE)
    elif kind == "tech":
        cv.rect(x + w // 2 - 3, mid - 3, 6, 6, WHITE)
    elif kind == "money":
        cv.circle(x + w // 2, mid, 3, WHITE)
    elif kind == "flag":
        cv.rect(x + w // 2 - 1, mid - 4, 1, 8, WHITE)
        cv.tri(x + w // 2, mid - 4, x + w // 2 + 5, mid - 2,
               x + w // 2, mid, WHITE)
    else:
        cv.circle(x + w // 2, mid, 3, WHITE)


# ------------------------------------------------------------------ stories
HEROES = [
    dict(num=1, loc="SANTA CLARA, US", topic="BUSINESS", region="AMERICAS",
         flag="HUANG RETURNS", chip="+31% SHARES", source="Reuters",
         head="Huang back at Nvidia as shares soar 31%",
         deck="Nvidia reinstates Jensen Huang as chief executive eleven days "
              "after his ouster, and shares jump 31 percent in their best day "
              "since 2003. (Reuters, CNN)",
         scene="nvidia"),
    dict(num=2, loc="ODESA, UKRAINE", topic="WAR", region="EUROPE",
         flag="UKRAINE: SEA DRONES", chip="WARSHIP SUNK", source="Reuters",
         head="Ukraine sinks Russian warship off Libya",
         deck="Ukraine sinks a Russian corvette in a Libyan port with sea "
              "drones, as Russian strikes leave Odesa without power, heat or "
              "water. (Reuters, Zelenskyy)",
         scene="sea"),
    dict(num=3, loc="TEHRAN, IRAN", topic="IRAN WAR", region="MIDDLE EAST",
         flag="IRAN: DEFIANCE", chip="BLOCKADE", source="Reuters",
         head="Iran vows to defy US blockade",
         deck="Iran says it will use all its tools against the US naval "
              "blockade as Washington sanctions dozens tied to its shadow "
              "banking networks. (Reuters, Treasury)",
         scene="tehran"),
]

MIDS = [
    dict(num=4, loc="POLAND", region="EUROPE", chip="AWACS DEPLOYED",
         source="Reuters", head="NATO sends early-warning plane to Poland",
         deck="NATO sends an AWACS early-warning aircraft to Poland after "
              "three Russian missiles landed there on Friday. (Reuters)",
         scene="nato"),
    dict(num=5, loc="ANTALYA, TURKEY · CLIMATE", region="EUROPE",
         chip="COP FALLOUT", source="Reuters",
         head="COP31 collapse brings backlash",
         deck="Blame spreads for the collapse of the UN climate talks as "
              "Australia and Pacific nations voice despair. (Reuters)",
         scene="cop"),
    dict(num=6, loc="TEHRAN, IRAN", region="MIDDLE EAST", chip="74 LASHES",
         source="Al Jazeera", head="Iran flogs singer over concert",
         deck="Iran flogs singer Parastoo Ahmadi and four of her team, 74 "
              "lashes each, over a virtual concert. (Al Jazeera)",
         scene="flog"),
    dict(num=7, loc="SEOUL, SOUTH KOREA", region="ASIA-PACIFIC",
         chip="AIRSPACE ALERT", source="Reuters",
         head="Korea warns island over Russian jet",
         deck="South Korea briefly warns Ulleung island to evacuate after a "
              "Russian aircraft enters its airspace. (Reuters)",
         scene="korea"),
    dict(num=8, loc="MEXICO", region="AMERICAS", chip="16 KILLED",
         source="Reuters", head="Mexico nabs \u2018Chapo Isidro\u2019",
         deck="Troops capture cartel boss Chapo Isidro as 16 suspected "
              "cartel gunmen are killed in the raid. (Reuters)",
         scene="mexico"),
    dict(num=9, loc="GAZA", region="MIDDLE EAST", chip="3 KILLED",
         source="Al Jazeera", head="Strikes kill three in Gaza",
         deck="Israeli strikes kill three in Gaza, including an aid worker, "
              "as Israel pushes into southern Syria. (Al Jazeera)",
         scene="gaza"),
    dict(num=10, loc="ATLANTA, US", region="AMERICAS", chip="3,000+ DELAYED",
         source="Delta", head="Delta failure grounds US flights",
         deck="A Delta computer failure delays more than 3,000 flights at "
              "busy US airports. (Delta)",
         scene="delta"),
    dict(num=11, loc="BERLIN, GERMANY", region="EUROPE", chip="DELTA DEAL",
         source="Reuters", head="Germany to use Kyiv\u2019s Delta system",
         deck="Germany signs a deal to use Kyiv\u2019s Delta battle system for "
              "its own armed forces. (Reuters)",
         scene="berlin"),
    dict(num=12, loc="WASHINGTON, US", region="AMERICAS", chip="GROK SUED",
         source="Al Jazeera", head="States sue SpaceX over Grok",
         deck="US states sue SpaceX over its Grok AI making child sexual "
              "abuse images. (Al Jazeera)",
         scene="grok"),
    dict(num=13, loc="VANUATU", region="ASIA-PACIFIC", chip="6.5 QUAKE",
         source="AP", head="Quake strikes off Vanuatu",
         deck="A 6.5 magnitude earthquake strikes off Vanuatu, with no "
              "tsunami threat issued. (AP)",
         scene="quake"),
]

BRIEFS = [
    (14, "MURMANSK, RUSSIA", "EUROPE", "city",
     "Russia detains the Murmansk governor on suspicion of embezzlement. (Reuters)"),
    (15, "SUDAN", "AFRICA", "flag",
     "An SPLA-IO attack kills 24 people in South Sudan. (AP)"),
    (16, "BRUSSELS", "EUROPE", "tech",
     "A cyberattack hits the EU Academy platform, exposing personal data. (EU)"),
    (17, "DENMARK", "EUROPE", "flag",
     "Bomb threats at academies across Denmark prove unfounded. (Police)"),
    (18, "PANAMA", "AMERICAS", "money",
     "Panama and First Quantum resume talks over the Cobre Panama mine. (Reuters)"),
    (19, "ISTANBUL", "EUROPE", "nature",
     "Police hunt a lioness on the loose near Istanbul. (Al Jazeera)"),
    (20, "KANSAS CITY, US", "AMERICAS", "sport",
     "Kansas City Current win their first NWSL championship, 2\u20131 over Washington. (NWSL)"),
    (21, "SEOUL", "ASIA-PACIFIC", "flag",
     "South Korea\u2019s president names a new foreign minister and intelligence chief. (Yonhap)"),
    (22, "SEOUL", "ASIA-PACIFIC", "flag",
     "South Korea\u2019s education minister quits over AI cheating rules. (Yonhap)"),
    (23, "BRAS\u00cdLIA", "AMERICAS", "court",
     "Brazil\u2019s top court summons Fl\u00e1vio Bolsonaro over alleged slander of Lula. (MercoPress)"),
    (24, "BRAS\u00cdLIA", "AMERICAS", "money",
     "Brazil cuts its 2027 growth forecast to 1.8 percent. (MercoPress)"),
    (25, "NEW YORK", "WORLD", "flag",
     "The UN warns Black Sea drone attacks threaten food exports. (UN)"),
    (26, "WASHINGTON", "AMERICAS", "health",
     "The US has lost its measles elimination status after 25 years. (CDC)"),
    (27, "NEW YORK", "AMERICAS", "court",
     "An appeals court hands Trump a win on tossing his hush-money convictions. (AP)"),
    (28, "BEIJING", "ASIA-PACIFIC", "flag",
     "China sentences a state official to death for revealing state secrets. (Reuters)"),
    (29, "YEREVAN", "ASIA-PACIFIC", "flag",
     "The US and Armenia launch the TRIPP transport project. (US State Dept)"),
    (30, "DHAKA", "ASIA-PACIFIC", "flag",
     "Bangladesh garment workers reject a pay offer and keep protesting. (Al Jazeera)"),
    (31, "TEHRAN", "MIDDLE EAST", "flag",
     "Iran warns EU bases with missiles it claims can reach 4,500 km. (Al Jazeera)"),
    (32, "TALLINN", "EUROPE", "flag",
     "Estonia issues a firm statement after Russia\u2019s airspace allegation. (Estonian govt)"),
    (33, "MOSCOW", "EUROPE", "flag",
     "Russia accuses Estonia of provocations nearing full-scale war. (Kremlin)"),
    (34, "TAIPEI", "ASIA-PACIFIC", "tech",
     "Fake personas aligned with China target Taiwan\u2019s election, researchers say. (NYT)"),
    (35, "DALLAS, US", "AMERICAS", "sport",
     "Dallas routs Tennessee 51\u201330 in the NFL\u2019s first-ever 51\u201330 final score. (CBS)"),
]

SCENES = {"nvidia": scene_nvidia, "sea": scene_sea, "tehran": scene_tehran,
          "nato": scene_nato, "cop": scene_cop, "flog": scene_flog,
          "korea": scene_korea, "mexico": scene_mexico, "gaza": scene_gaza,
          "delta": scene_delta, "berlin": scene_berlin, "grok": scene_grok,
          "quake": scene_quake}

STATS = [("+31.5%", "NVIDIA SHARES"),
         ("$952BN", "VALUE GAINED IN ONE DAY"),
         ("3", "RUSSIAN MISSILES LANDED IN POLAND"),
         ("74", "LASHES FOR SINGER AND HER TEAM"),
         ("3,000+", "US FLIGHTS DELAYED"),
         ("240,000", "PEOPLE WITHOUT HEAT IN ODESA")]

REGIONS = [("EUROPE", 10, NAVY2), ("MIDDLE EAST", 4, RED),
           ("AMERICAS", 11, SAGE_D), ("ASIA-PACIFIC", 8, (176, 132, 52)),
           ("AFRICA", 1, (96, 62, 118)), ("WORLD", 1, (70, 70, 72))]

MX = 28
CW = 968


def chip(cv, x, y, s, bg, fg=WHITE):
    w = F("snb11").width(s) + 12
    cv.rect(x, y, w, 17, bg)
    text(cv, x + 6, y + 13, "snb11", s, fg)
    return w


def draw_header(cv):
    cv.rect(0, 0, W, 24, NAVY)
    text(cv, MX, 17, "snb11", "THE WORLD IN ONE DAY", WHITE)
    text(cv, W - MX, 17, "snb11",
         "35 STORIES  \u00b7  6 REGIONS  \u00b7  EVERY ONE DATED TUESDAY 24 NOVEMBER 2026",
         WHITE, align="r")
    text(cv, W // 2, 82, "sb58", "Tuesday 24 November 2026", INK, align="c")
    text(cv, W // 2, 106, "si17",
         "Huang back at Nvidia as shares soar 31%  \u00b7  Ukraine sinks "
         "Russian warship off Libya  \u00b7  Iran vows to defy US blockade",
         RED_D, align="c")
    cv.hline(MX, 114, CW, INK)
    cv.hline(MX, 117, CW, INK)


def draw_stats(cv, y):
    widths = [161, 161, 162, 161, 161, 162]
    x = MX
    for (num, lab), wdt in zip(STATS, widths):
        text(cv, x + wdt // 2, y + 26, "sb26", num, RED, align="c")
        lines = wrap(lab, "snb9", wdt - 12)
        ly = y + 40
        for ln in lines:
            text(cv, x + wdt // 2, ly, "snb9", ln, INK, align="c")
            ly += 11
        x += wdt
        if x < MX + CW:
            cv.vline(x, y + 6, 48, (200, 192, 172))


def draw_regions(cv, y):
    widths = [247, 99, 272, 198, 76, 76]
    x = MX
    for (name, n, c), wdt in zip(REGIONS, widths):
        cv.rect(x, y, wdt, 18, c)
        text(cv, x + wdt // 2, y + 13, "snb11", "%s %d" % (name, n), WHITE,
             align="c")
        x += wdt


def draw_heroes(cv, y):
    colw, gap = 312, 16
    for i, st in enumerate(HEROES):
        x = MX + i * (colw + gap)
        SCENES[st["scene"]](cv, x, y, colw, 112)
        chip(cv, x + 5, y + 5, st["flag"], RED)
        cw = F("snb11").width(st["chip"]) + 12
        cv.rect(x + colw - 5 - cw, y + 5, cw, 17, WHITE)
        text(cv, x + colw - 5 - cw + 6, y + 18, "snb11", st["chip"], INK)
        chip(cv, x + 5, y + 112 - 22, st["source"], INK)
        yy = y + 112 + 16
        text(cv, x, yy, "snb11",
             "%d  %s  \u00b7  %s" % (st["num"], st["loc"], st["topic"]), RED)
        yy += 8
        lines = wrap(st["head"], "sb26", colw)
        assert len(lines) <= 2, "hero headline too long: %r" % st["head"]
        for ln in lines:
            yy += 27
            text(cv, x, yy, "sb26", ln, INK)
        yy += 6
        lines = wrap(st["deck"], "sr14", colw)
        assert len(lines) <= 3, "hero deck too long: %r" % st["deck"]
        for ln in lines:
            yy += 15
            text(cv, x, yy, "sr14", ln, INK)
    return y + 112 + 16 + 8 + 2 * 27 + 6 + 3 * 15


def draw_mids(cv, y):
    colw, gap = 185, 11
    for row in range(2):
        for col in range(5):
            st = MIDS[row * 5 + col]
            x = MX + col * (colw + gap)
            SCENES[st["scene"]](cv, x, y, colw, 48)
            chip(cv, x + 4, y + 4, st["chip"], RED)
            cv.circle(x + colw - 11, y + 11, 9, WHITE)
            cv.ring(x + colw - 11, y + 11, 9, RED, 2)
            text(cv, x + colw - 11, y + 15, "snb9", str(st["num"]), RED,
                 align="c")
            chip(cv, x + 4, y + 48 - 18, st["source"], INK)
            yy = y + 48 + 12
            text(cv, x, yy, "snb11", "%d  %s" % (st["num"], st["loc"]), RED)
            yy += 5
            lines = wrap(st["head"], "sb15", colw)
            assert len(lines) <= 2, "mid headline too long: %r" % st["head"]
            for ln in lines:
                yy += 17
                text(cv, x, yy, "sb15", ln, INK)
            yy += 3
            lines = wrap(st["deck"], "sr10", colw)
            assert len(lines) <= 3, "mid deck too long: %r" % st["deck"]
            for ln in lines:
                yy += 11
                text(cv, x, yy, "sr10", ln, INK)
        y += 48 + 12 + 5 + 2 * 17 + 3 + 3 * 11 + 7
    return y


# ------------------------------------------------------------------- bottom
LAND = [(-100, 48, 28, 14), (-95, 32, 18, 9), (-85, 20, 8, 6),
        (-152, 64, 12, 6), (-42, 74, 10, 7), (-60, -12, 14, 16),
        (-65, -30, 8, 10), (15, 54, 18, 8), (25, 62, 12, 6),
        (10, 45, 10, 5), (-2, 54, 3, 4), (18, 8, 16, 14),
        (25, -18, 11, 10), (32, 28, 10, 6), (60, 55, 30, 12),
        (90, 50, 25, 12), (110, 35, 18, 11), (78, 22, 10, 8),
        (105, 15, 8, 7), (139, 37, 7, 8), (122, 30, 6, 5),
        (115, -2, 10, 4), (134, -25, 15, 8)]

PINS = [(1, -122, 37.4, -6, -4), (2, 13.5, 32.9, -8, 6), (3, 51.4, 35.7, 0, -7),
        (4, 19, 52, 8, -6), (5, 30.7, 36.9, -4, 9), (6, 51.4, 35.7, 8, 5),
        (7, 130.9, 37.5, 0, 0), (8, -106, 25, -8, 5), (9, 34.5, 31.5, 9, -3),
        (10, -84.4, 33.7, -7, 3), (11, 13.4, 52.5, -10, 6),
        (12, -77, 38.9, -9, -7), (13, 167, -16, 0, 0), (14, 33, 69, 0, -3),
        (15, 31.6, 7.9, 0, 0), (16, 4.35, 50.85, -11, -3),
        (17, 10, 56, 1, -9), (18, -79.5, 9, 0, 0), (19, 29, 41, 7, 9),
        (20, -94.6, 39.1, 2, -9), (21, 127, 37.5, -5, -6),
        (22, 127, 37.5, 7, 6), (23, -47.9, -15.8, -6, -5),
        (24, -47.9, -15.8, 7, 6), (25, -74, 40.7, -5, -9),
        (26, -77, 38.9, 9, 7), (27, -74, 40.7, 9, 3),
        (28, 116.4, 39.9, 0, 0), (29, 44.5, 40.2, 11, -5),
        (30, 90.4, 23.8, 0, 0), (31, 51.4, 35.7, -8, 5),
        (32, 24.7, 59.4, 7, -3), (33, 37.6, 55.75, 10, 4),
        (34, 121.6, 25, 0, 0), (35, -96.8, 32.8, 9, 5)]


def draw_bottom(cv, y):
    """y = header baseline. Returns y just below the tiles/map block."""
    text(cv, MX, y, "snb11", "WHERE IT HAPPENED", INK)
    text(cv, MX + 130, y, "snb9", "pins match story numbers", GREY)
    text(cv, MX + 436, y, "snb11", "THE REST OF THE DAY \u2014 22 MORE STORIES",
         INK)
    top = y + 8
    mh = 240
    # --- dotted world map (left panel)
    cv.rect(MX, top, 420, mh, (250, 246, 236))
    cv.rect(MX, top, 420, 1, (200, 192, 172))
    cv.rect(MX, top + mh - 1, 420, 1, (200, 192, 172))
    scale = 416 / 360.0
    map_top = top + int(mh - 140 * scale) // 2
    for gy in range(0, int(140 * scale), 6):
        lat = 82 - gy / scale
        for gx in range(0, 416, 6):
            lon = -180 + gx / scale
            on = False
            for clon, clat, rl, rt in LAND:
                if ((lon - clon) / rl) ** 2 + ((lat - clat) / rt) ** 2 <= 1:
                    on = True
                    break
            if on:
                cv.rect(MX + 2 + gx, map_top + gy, 3, 3, (150, 140, 110))
    for num, lon, lat, ox, oy in PINS:
        px = MX + 2 + int((lon + 180) * scale) + ox
        py = map_top + int((82 - lat) * scale) + oy
        cv.circle(px, py, 6, RED)
        cv.ring(px, py, 6, WHITE, 1)
        text(cv, px, py + 3, "snb9", str(num), WHITE, align="c")
    # --- brief mini-tiles (right panel, 2 cols x 11 rows)
    tx0 = MX + 436
    tw, th, gapx, gapy = 262, 20, 8, 2
    for i, (num, loc, region, kind, deck) in enumerate(BRIEFS):
        col, row = i % 2, i // 2
        x = tx0 + col * (tw + gapx)
        yy = top + row * (th + gapy)
        cv.rect(x, yy, tw, th, (252, 248, 240))
        motif(cv, x, yy, 5, th, kind)
        nw = F("snb9").width(str(num))
        dx = x + 10 + nw + 5
        lines = wrap(deck, "sr9", x + tw - 4 - dx)
        assert len(lines) <= 2, "brief too long: %d" % num
        text(cv, x + 10, yy + 9, "snb9", str(num), RED)
        text(cv, dx, yy + 9, "sr9", lines[0], INK)
        if len(lines) > 1:
            text(cv, dx, yy + 18, "sr9", lines[1], INK)
    return top + mh


def draw_datecheck(cv, y):
    cv.rect(MX, y, CW, 28, CREAM)
    cv.rect(MX, y, CW, 1, RED)
    cv.rect(MX, y + 27, CW, 1, RED)
    cv.rect(MX, y, 1, 28, RED)
    cv.rect(MX + CW - 1, y, 1, 28, RED)
    head = "DATE CHECK"
    text(cv, MX + 8, y + 12, "snb11", head, RED)
    body = ("Wires read up to 06:00 UTC, Tuesday 24 November 2026. Every "
            "story here was reported or still developing on 24 November in "
            "at least one time zone. Left out as other days\u2019 news: the "
            "Zanzibar hotel fire (21 Nov), the Peru earthquake (20 Nov) and "
            "the Kerch Bridge strikes (earlier this week).")
    bx = MX + 8 + F("snb11").width(head) + 10
    lines = wrap(body, "sr11", MX + CW - 8 - bx)
    assert len(lines) <= 2, "date check too long"
    yy = y + 12
    for ln in lines:
        text(cv, bx, yy, "sr11", ln, INK)
        yy += 11
        if yy > y + 12:
            bx = MX + 8


def build():
    global FONTS
    FONTS = load_fonts()
    cv = Canvas(W, H, CREAM)
    draw_header(cv)
    draw_stats(cv, 112)
    draw_regions(cv, 166)
    y = draw_heroes(cv, 184)
    y = draw_mids(cv, y + 8)
    by = draw_bottom(cv, y + 8)
    draw_datecheck(cv, by + 6)
    cv.rect(0, 1008, W, 16, NAVY)
    text(cv, W // 2, 1020, "snb9",
         "Sources: Reuters, BBC, Al Jazeera, CNN, WSJ, AP, Yonhap, "
         "MercoPress, NWSL, CBS. Every story names its outlet. Pictures "
         "and map: original, drawn in code.", WHITE, align="c")
    return cv


def main():
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR")
    if not outdir:
        raise SystemExit("MAKEFUN_OUTPUT_DIR is not set")
    cv = build()
    # ---- audits
    assert len(HEROES) == 3 and len(MIDS) == 10 and len(BRIEFS) == 22
    assert len(HEROES) + len(MIDS) + len(BRIEFS) == 35
    counts = {}
    for st in HEROES + MIDS:
        counts[st["region"]] = counts.get(st["region"], 0) + 1
    for _, _, region, _, _ in BRIEFS:
        counts[region] = counts.get(region, 0) + 1
    expect = {"EUROPE": 10, "MIDDLE EAST": 4, "AMERICAS": 11,
              "ASIA-PACIFIC": 8, "AFRICA": 1, "WORLD": 1}
    assert counts == expect, "region counts %r" % counts
    assert sum(counts.values()) == 35
    assert len(PINS) == 35
    png = encode_png(W, H, bytes(cv.buf))
    assert len(png) <= 1048576, "PNG too big: %d" % len(png)
    path = os.path.join(outdir, "entry.png")
    with open(path, "wb") as fh:
        fh.write(png)


if __name__ == "__main__":
    main()
