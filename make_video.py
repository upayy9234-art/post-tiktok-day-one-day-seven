#!/usr/bin/env python3
"""Pocket Grove — "Day one, day seven" video renderer (Python stdlib only).

Draws a tiny top-down village game twice on the SAME map: the sparse day-one
village and the same place after a week of daily updates, with a hard cut
between identical framing. Frames are written as PNGs at 540x960, 24 fps;
ffmpeg then encodes the body and the make.fun referral end card is laid over
the last 2.5 s (see the press pack guide). No downloaded code or assets:
every pixel below is drawn by this script.
"""
import math
import os
import struct
import sys
import zlib

W, H, FPS = 540, 960, 24
FRAMES_DIR = sys.argv[1] if len(sys.argv) > 1 else "frames"

# --------------------------------------------------------------------------
# Shared layout — identical to game.html: the map never moves between days.
# --------------------------------------------------------------------------
RIVER_X = 462
SPAWN = (110, 740)
LOOP = [(110, 740), (110, 260), (350, 260), (350, 740), (110, 740), (230, 500)]
HUT = (128, 268, 62, 50)
FIRST_TREES = [(66, 128), (414, 690)]
DIRT = (96, 846, 252, 78)
BUILDINGS = [
    (128, 268, 62, 50, "hut"), (238, 268, 62, 50, "house"),
    (128, 428, 62, 50, "house"), (238, 428, 62, 50, "bakery"),
    (306, 428, 56, 50, "smith"), (306, 268, 56, 50, "inn"),
    (140, 612, 56, 40, "stall"), (224, 612, 56, 40, "stall"),
]
WELL = (216, 486, 30, 30)
MORE_TREES = FIRST_TREES + [(404, 150), (60, 560), (420, 420), (380, 830)]
LANTERNS = [(110, 480), (230, 260), (350, 480), (230, 740), (110, 640), (350, 640)]
NPC_COLOURS = [(0xD9, 0x4F, 0x4F), (0x9B, 0x59, 0xB6), (0x3F, 0x8F, 0xD2),
               (0xE6, 0x7E, 0x22), (0x2E, 0xCC, 0x71), (0xEC, 0xF0, 0xF1)]
HERO_COLOUR = (0x3F, 0x6F, 0xD2)

GRASS_A = (0x7C, 0xC4, 0x63)
GRASS_B = (0x74, 0xBA, 0x5A)
WATER = (0x4A, 0xA3, 0xD8)
WATER_HI = (0x8E, 0xCD, 0xF0)
SAND = (0xC9, 0xB0, 0x83)
PATH = (0xC9, 0xA8, 0x6A)
PATH_EDGE = (0xB5, 0x93, 0x58)
DIRT_COL = (0xA9, 0x80, 0x5A)
WHITE = (0xFF, 0xFF, 0xFF)
INK = (0x19, 0x14, 0x19)
SHADOW = (0x1A, 0x2E, 0x16)


# --------------------------------------------------------------------------
# Framebuffer: an RGB bytearray with rect / circle / line fills.
# --------------------------------------------------------------------------
class FB:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.px = bytearray(w * h * 3)

    def rect(self, x, y, w, h, col):
        x, y, w, h = int(x), int(y), int(w), int(h)
        if w <= 0 or h <= 0:
            return
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + w, self.w), min(y + h, self.h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(col) * (x1 - x0)
        stride = self.w * 3
        off = (y0 * self.w + x0) * 3
        for _ in range(y0, y1):
            self.px[off:off + len(row)] = row
            off += stride

    def circle(self, cx, cy, r, col):
        cx, cy, r = int(cx), int(cy), int(r)
        for dy in range(-r, r + 1):
            dx = int(math.sqrt(max(0, r * r - dy * dy)))
            self.rect(cx - dx, cy + dy, 2 * dx + 1, 1, col)

    def line(self, x0, y0, x1, y1, col, thick=2):
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        for i in range(steps + 1):
            t = i / steps
            self.rect(x0 + (x1 - x0) * t - thick // 2,
                      y0 + (y1 - y0) * t - thick // 2, thick, thick, col)

    def save_png(self, path):
        raw = bytearray()
        stride = self.w * 3
        for y in range(self.h):
            raw.append(0)
            raw += self.px[y * stride:(y + 1) * stride]

        def chunk(tag, data):
            out = struct.pack(">I", len(data)) + tag + data
            return out + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

        png = b"\x89PNG\r\n\x1a\n"
        png += chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        png += chunk(b"IEND", b"")
        with open(path, "wb") as f:
            f.write(png)


# --------------------------------------------------------------------------
# A 5x7 bitmap font, drawn by hand below — enough for the on-screen lines.
# --------------------------------------------------------------------------
FONT = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".####", "#....", "#....", "#....", "#....", "#....", ".####"),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".####", "#....", "#....", "#.###", "#...#", "#...#", ".###."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "J": ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "#.#.#", ".#.#."),
    "X": ("#...#", ".#.#.", "..#..", "..#..", "..#..", ".#.#.", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "Z": ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    "a": (".....", ".....", ".###.", "....#", ".####", "#...#", ".####"),
    "b": ("#....", "#....", "####.", "#...#", "#...#", "#...#", "####."),
    "c": (".....", ".....", ".####", "#....", "#....", "#....", ".####"),
    "d": ("....#", "....#", ".####", "#...#", "#...#", "#...#", ".####"),
    "e": (".....", ".....", ".###.", "#...#", "#####", "#....", ".###."),
    "f": ("..##.", ".#...", "####.", ".#...", ".#...", ".#...", ".#..."),
    "g": (".....", ".####", "#...#", "#...#", ".####", "....#", ".###."),
    "h": ("#....", "#....", "####.", "#...#", "#...#", "#...#", "#...#"),
    "i": ("..#..", ".....", ".##..", "..#..", "..#..", "..#..", ".###."),
    "j": ("...#.", ".....", "..##.", "...#.", "...#.", "#..#.", ".##.."),
    "k": ("#....", "#....", "#..#.", "#.#..", "##...", "#.#..", "#..#."),
    "l": (".##..", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "m": (".....", ".....", "##.#.", "#.#.#", "#.#.#", "#.#.#", "#.#.#"),
    "n": (".....", ".....", "####.", "#...#", "#...#", "#...#", "#...#"),
    "o": (".....", ".....", ".###.", "#...#", "#...#", "#...#", ".###."),
    "p": (".....", ".....", "####.", "#...#", "#...#", "####.", "#...."),
    "q": (".....", ".....", ".####", "#...#", "#...#", ".####", "....#"),
    "r": (".....", ".....", "#.##.", "##..#", "#....", "#....", "#...."),
    "s": (".....", ".....", ".####", "#....", ".###.", "....#", "####."),
    "t": (".#...", ".#...", "####.", ".#...", ".#...", ".#..#", "..##."),
    "u": (".....", ".....", "#...#", "#...#", "#...#", "#..##", ".##.#"),
    "v": (".....", ".....", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "w": (".....", ".....", "#...#", "#.#.#", "#.#.#", "#.#.#", ".#.#."),
    "x": (".....", ".....", "#...#", ".#.#.", "..#..", ".#.#.", "#...#"),
    "y": (".....", ".....", "#...#", "#...#", "#...#", ".####", "....#"),
    "z": (".....", ".....", "#####", "...#.", "..#..", ".#...", "#####"),
    "0": (".###.", "#..##", "#.#.#", "##..#", "#...#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "..##.", ".#...", "#....", "#####"),
    "3": ("####.", "....#", "....#", ".###.", "....#", "....#", "####."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": (".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."),
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
    ".": (".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    ",": (".....", ".....", ".....", ".....", ".##..", ".##..", ".#..."),
    "!": ("..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."),
    "'": ("..#..", "..#..", ".#...", ".....", ".....", ".....", "....."),
    "-": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
}


def text_width(s, scale):
    return len(s) * 6 * scale - scale


def draw_text(fb, s, cx, y, scale, col, shadow=True):
    x = int(cx - text_width(s, scale) / 2)
    for layer, (ox, oy, c) in enumerate([(max(2, scale // 2),) * 2 + (SHADOW,), (0, 0, col)]):
        if layer == 0 and not shadow:
            continue
        for i, ch in enumerate(s):
            glyph = FONT.get(ch, FONT[" "])
            gx = x + i * 6 * scale + ox
            for row in range(7):
                for col_i in range(5):
                    if glyph[row][col_i] == "#":
                        fb.rect(gx + col_i * scale, y + row * scale + oy, scale, scale, c)


# --------------------------------------------------------------------------
# Scene pieces. Everything is drawn from the shared layout, so the day-one
# and day-seven frames are the same camera on the same map.
# --------------------------------------------------------------------------
def draw_map(fb, day, frame):
    for ty in range(H // 30):
        for tx in range(W // 30):
            fb.rect(tx * 30, ty * 30, 30, 30, GRASS_A if (tx + ty) % 2 == 0 else GRASS_B)
    # river down the right edge, sand bank, drifting shimmer
    fb.rect(RIVER_X, 0, W - RIVER_X, H, WATER)
    fb.rect(RIVER_X, 0, 6, H, SAND)
    for k in range(12):
        y = (k * 83 + frame * 2) % H
        fb.rect(RIVER_X + 20 + (k % 3) * 14, y, 20, 4, WATER_HI)
    # sun and two slow clouds — the same morning on both days
    fb.circle(56, 58, 24, (0xFF, 0xD9, 0x4A))
    fb.circle(56, 58, 18, (0xFF, 0xE2, 0x73))
    for i, (base_x, cy) in enumerate([(150, 196), (330, 228)]):
        cx = (base_x + frame * (0.25 + 0.1 * i)) % (W + 160) - 80
        for dx, dy, r in [(0, 0, 16), (20, 3, 12), (-20, 4, 11), (6, -6, 12)]:
            fb.circle(cx + dx, cy + dy, r, (0xF4, 0xF9, 0xF0))
    # the dirt loop path (drawn wide in the edge colour, then the middle)
    pts = LOOP[:5]
    for width, col in [(28, PATH_EDGE), (22, PATH)]:
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 == x1:
                fb.rect(x0 - width // 2, min(y0, y1), width, abs(y1 - y0), col)
            else:
                fb.rect(min(x0, x1), y0 - width // 2, abs(x1 - x0), width, col)
    # dirt patch on day one; fenced, planted field on day seven
    dx, dy, dw, dh = DIRT
    fb.rect(dx, dy, dw, dh, DIRT_COL)
    if day == 7:
        fb.rect(dx - 4, dy - 4, dw + 8, 5, (0x8D, 0x6E, 0x63))
        fb.rect(dx - 4, dy + dh - 1, dw + 8, 5, (0x8D, 0x6E, 0x63))
        fb.rect(dx - 4, dy - 4, 5, dh + 8, (0x8D, 0x6E, 0x63))
        fb.rect(dx + dw - 1, dy - 4, 5, dh + 8, (0x8D, 0x6E, 0x63))
        for r in range(4):
            for i in range(12):
                cx, cy = dx + 14 + i * 20, dy + 13 + r * 18
                main = (0xF4, 0xD0, 0x3F) if r % 2 else (0x58, 0xB3, 0x68)
                lite = (0xF7, 0xDC, 0x6F) if r % 2 else (0x6F, 0xCE, 0x7E)
                fb.circle(cx, cy, 5, main)
                fb.circle(cx, cy - 4, 3, lite)


def draw_tree(fb, x, y, grown):
    fb.rect(x - 3, y, 6, 14, (0x7A, 0x4A, 0x21))
    big = 17 if grown else 13
    fb.circle(x, y - 8, big, (0x2E, 0x7D, 0x32))
    fb.circle(x - 10, y - 2, big - 5, (0x38, 0x8E, 0x3C))
    fb.circle(x + 10, y - 2, big - 5, (0x43, 0xA0, 0x47))


def draw_building(fb, b):
    x, y, w, h, kind = b
    fb.rect(x, y + 14, w, h - 14, (0xF3, 0xE2, 0xB8))
    roof = (0x5D, 0x40, 0x37) if kind == "smith" else (0xB5, 0x52, 0x2D)
    for i in range(13):  # roof: rows widening from the apex
        half = int((i / 12) * (w / 2 + 5))
        fb.rect(x + w // 2 - half, y - 10 + i * 2, 2 * half, 2, roof)
    fb.rect(x + w // 2 - 7, y + h - 22, 14, 22, (0x6D, 0x44, 0x21))
    fb.rect(x + 8, y + 24, 10, 10, (0xFF, 0xE0, 0x82))
    if kind in ("bakery", "stall"):
        for i in range(6):
            fb.rect(x + i * (w // 6), y + 12, w // 6, 7,
                    (0xFF, 0xFF, 0xFF) if i % 2 else (0xD9, 0x4F, 0x4F))
    if kind == "stall":  # goods on the counter
        for i, c in enumerate([(0xF4, 0xD0, 0x3F), (0x58, 0xB3, 0x68), (0xD9, 0x4F, 0x4F)]):
            fb.circle(x + 12 + i * 16, y + 32, 4, c)
    if kind == "inn":
        fb.rect(x + w - 20, y + 22, 12, 12, (0xFF, 0xD9, 0x4A))


def draw_person(fb, x, y, colour, frame):
    step = 2 if math.sin(frame / 6) > 0 else -2
    fb.rect(x - 4, y + 8, 3, 6 + step, (0x37, 0x47, 0x4F))
    fb.rect(x + 1, y + 8, 3, 6 - step, (0x37, 0x47, 0x4F))
    fb.rect(x - 5, y - 2, 10, 11, colour)
    fb.circle(x, y - 7, 5, (0xF2, 0xC8, 0x94))


def draw_day7_life(fb, frame):
    wx, wy, ww, wh = WELL
    fb.rect(wx, wy + 8, ww, wh - 8, (0x9E, 0x9E, 0x9E))
    fb.circle(wx + ww // 2, wy + 12, 9, (0x37, 0x47, 0x4F))
    fb.rect(wx - 2, wy, 4, 12, (0x6D, 0x44, 0x21))
    fb.rect(wx + ww - 2, wy, 4, 12, (0x6D, 0x44, 0x21))
    fb.rect(wx - 4, wy - 4, ww + 8, 5, (0xB5, 0x52, 0x2D))
    for i, (lx, ly) in enumerate(LANTERNS):
        fb.rect(lx - 1, ly - 12, 3, 14, (0x4E, 0x34, 0x2E))
        flick = 4 + int(math.sin(frame / 8 + i) * 0.7)
        fb.circle(lx, ly - 16, flick, (0xFF, 0xD9, 0x4A))
    # a cart crossing the middle of the village, back and forth
    p = (frame * 3) % 800
    cx = 30 + (p if p < 400 else 800 - p)
    fb.rect(cx, 490, 36, 13, (0x8D, 0x6E, 0x63))
    fb.rect(cx + 5, 482, 24, 9, (0xD9, 0x4F, 0x4F))
    fb.circle(cx + 8, 508, 6, (0x4E, 0x34, 0x2E))
    fb.circle(cx + 29, 508, 6, (0x4E, 0x34, 0x2E))
    # birds overhead
    for i in range(3):
        bx = (frame * 4 + i * 180) % (W + 160) - 80
        by = 150 + i * 36
        flap = int(math.sin(frame * 0.4 + i) * 3)
        fb.line(bx - 8, by + flap, bx, by, INK, 2)
        fb.line(bx, by, bx + 8, by + flap, INK, 2)


# --------------------------------------------------------------------------
# Walking: positions along a polyline by distance travelled.
# --------------------------------------------------------------------------
def polyline(points):
    segs, total = [], 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        ln = math.hypot(x1 - x0, y1 - y0)
        segs.append((x0, y0, x1, y1, ln))
        total += ln
    return segs, total


LOOP_SEGS, LOOP_LEN = polyline(LOOP[:5])       # the rectangle, for the NPCs
FULL_SEGS, FULL_LEN = polyline(LOOP)           # hero: rectangle + walk to centre


def pos_at(segs, dist):
    for x0, y0, x1, y1, ln in segs:
        if dist <= ln:
            t = dist / ln if ln else 0
            return x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        dist -= ln
    x0, y0, x1, y1, _ = segs[-1]
    return x1, y1


# --------------------------------------------------------------------------
# Timeline: 480 frames at 24 fps = 20 s.
#   frames   0-143  DAY 1  (6 s)  the hero sets out across an empty map
#   frames 144-359  DAY 7  (9 s)  hard cut, identical framing: a whole village
#   frames 360-479  close  (5 s)  the hero walks to the village centre
# The referral end card is laid over the last 2.5 s later, by ffmpeg.
# --------------------------------------------------------------------------
TOTAL_FRAMES = 480
CUT = 144
NPC_SPEEDS = [1.7, 2.1, 2.5, 1.9, 2.3, 2.7]


def render_frame(frame):
    day = 1 if frame < CUT else 7
    fb = FB(W, H)
    draw_map(fb, day, frame)
    for tx, ty in (FIRST_TREES if day == 1 else MORE_TREES):
        draw_tree(fb, tx, ty, grown=(day == 7))
    if day == 1:
        draw_building(fb, BUILDINGS[0])
    else:
        for b in BUILDINGS:
            draw_building(fb, b)
        draw_day7_life(fb, frame)
        for i, col in enumerate(NPC_COLOURS):
            dist = (frame * NPC_SPEEDS[i] + i * 240) % LOOP_LEN
            nx, ny = pos_at(LOOP_SEGS, dist)
            draw_person(fb, nx, ny, col, frame + i * 9)
    # the hero walks the same route on both days, without a break at the cut
    hx, hy = pos_at(FULL_SEGS, min(frame * 4.0, FULL_LEN))
    draw_person(fb, hx, hy, HERO_COLOUR, frame)
    # on-screen text
    if 4 <= frame < CUT:
        draw_text(fb, "DAY 1", W // 2, 34, 9, WHITE)
        draw_text(fb, "one hut. one hero.", W // 2, 112, 3, WHITE)
        draw_text(fb, "big dreams.", W // 2, 144, 3, WHITE)
    elif CUT + 4 <= frame <= 352:
        draw_text(fb, "DAY 7", W // 2, 34, 9, WHITE)
        draw_text(fb, "same start.", W // 2, 112, 3, WHITE)
        draw_text(fb, "a whole village.", W // 2, 144, 3, WHITE)
    if frame >= 366:
        draw_text(fb, "Built by my AI agent", W // 2, 380, 3, WHITE)
    if frame >= 380:
        draw_text(fb, "in 7 days", W // 2, 416, 3, WHITE)
    if frame >= 396:
        draw_text(fb, "Start yours at make.fun", W // 2, 452, 3, WHITE)
    return fb


def main():
    os.makedirs(FRAMES_DIR, exist_ok=True)
    for frame in range(TOTAL_FRAMES):
        render_frame(frame).save_png(os.path.join(FRAMES_DIR, "%04d.png" % frame))
        if frame % 48 == 0:
            print("frame", frame, flush=True)
    print("done:", TOTAL_FRAMES, "frames in", FRAMES_DIR)


if __name__ == "__main__":
    main()
