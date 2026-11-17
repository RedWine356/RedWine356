#!/usr/bin/env python3
"""
Chess profile generator for GitHub.

Your profile is a position on the board. Your piece hops around a mini board,
your skills are pieces you have developed, your projects are games you have
played, and your contribution graph is a board that a snake of pieces sweeps.

Reads profile.json and writes:
  README.md                 the profile README
  assets/player.svg         player card: piece, rank, progress, attributes
  assets/snake.svg          commit snake over your contribution board
  assets/stats.svg          stats bar (language board + numbers)
  assets/skilltree.svg      skills as a neural net of chess pieces
  assets/game-N.svg         one clickable card per project
  assets/btn-*.svg          link buttons

Usage:
  python build.py                   build from profile.json (offline, sample data)
  python build.py --live            pull real numbers from the GitHub API
                                    (set GITHUB_TOKEN for contributions and streaks)
  python build.py --snapshot 12     write static frames (time in seconds) to ./preview

Standard library only.
"""
import argparse
import datetime
import glob
import hashlib
import json
import math
import os
import random
import re
import textwrap
import urllib.request
from html import escape

ROOT = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(ROOT, "assets")
SNAP = None  # when set, animations are replaced by one static frame at this time

MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"
CW = 0.6  # monospace glyph width as a fraction of font size

THEMES = {
    # dark walnut board, like a late-night game on a wooden set
    "walnut": dict(bg="#211e1b", panel="#2b2723", line="#4a4036", edge="#b58863", text="#f0d9b5",
                   dim="#a99a82", hi="#9fcf6a", warn="#e8c547", mute="#5a4f42",
                   sqL="#f0d9b5", sqD="#b58863", pw="#fffaf0", pb="#1c1a17"),
    # green and cream tournament board on light paper
    "classic": dict(bg="#f5f3e7", panel="#fcfbf4", line="#c9c6a8", edge="#2f4a2a", text="#262421",
                    dim="#6b6a58", hi="#3f7d2c", warn="#b07d00", mute="#b5b49a",
                    sqL="#eeeed2", sqD="#769656", pw="#ffffff", pb="#262421"),
    # black and white newspaper diagram
    "ink": dict(bg="#fafafa", panel="#ffffff", line="#c8c8c8", edge="#111111", text="#111111",
                dim="#666666", hi="#111111", warn="#c2410c", mute="#bdbdbd",
                sqL="#ffffff", sqD="#9a9a9a", pw="#ffffff", pb="#111111"),
}

LANG_COLORS = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6", "Java": "#b07219",
    "C++": "#f34b7d", "C": "#8a8a8a", "C#": "#178600", "Go": "#00ADD8", "Rust": "#dea584",
    "HTML": "#e34c26", "CSS": "#663399", "Shell": "#89e051", "Jupyter Notebook": "#DA5B0B",
    "Kotlin": "#A97BFF", "Swift": "#F05138", "Dart": "#00B4AB", "PHP": "#4F5D95",
    "Ruby": "#701516", "MATLAB": "#e16737", "Dockerfile": "#384d54", "SQL": "#e38c00",
}

# 9x9 pixel pieces
PIECES = {
    "pawn": ["....#....", "...###...", "...###...", "....#....", "...###...",
             "..#####..", "...###...", "..#####..", ".#######."],
    "knight": ["..##.....", ".####....", "######...", "##.###...", "....###..",
               "...####..", "..#####..", ".#######.", "#########"],
    "bishop": ["....#....", "...###...", "..##.##..", "..#####..", "..#####..",
               "...###...", "....#....", "..#####..", ".#######."],
    "rook": ["#.#.#.#.#", "#########", ".#######.", "..#####..", "..#####..",
             "..#####..", "..#####..", ".#######.", "#########"],
    "queen": ["#...#...#", "#.#.#.#.#", "#########", ".#######.", "..#####..",
              "..#####..", "...###...", ".#######.", "#########"],
    "king": ["....#....", "...###...", "....#....", ".#######.", ".#######.",
             "..#####..", "..#####..", ".#######.", "#########"],
}
PIECE_VALUE = {"pawn": 1, "knight": 3, "bishop": 3, "rook": 5, "queen": 9, "king": 0}
DIFF_PIECES = ["pawn", "knight", "bishop", "rook", "queen"]
LAYER_PIECES = ["pawn", "knight", "bishop", "rook", "queen", "king"]

# Legal-move loops on a 4x4 board, as (column, row) with row 0 at the top
CYCLES = {
    "knight": [(0, 0), (1, 2), (3, 3), (2, 1)],
    "rook": [(0, 0), (3, 0), (3, 3), (0, 3)],
    "bishop": [(1, 0), (3, 2), (2, 3), (0, 1)],
    "queen": [(0, 0), (3, 0), (1, 2), (1, 0)],
    "king": [(1, 1), (2, 1), (2, 2), (1, 2)],
}


# --------------------------------------------------------------------------- helpers
def esc(s):
    return escape(str(s), quote=True)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-") or "link"


def trunc(s, n):
    s = str(s)
    return s if len(s) <= n else s[: max(0, n - 1)] + "…"


def fmt_date(d):
    return d.strftime("%b %d, %Y")


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def css(extra=""):
    return (
        f"text{{font-family:{MONO}}}"
        ".lbl{font-size:10px;letter-spacing:1.5px}"
        ".blink{animation:bl 1s steps(1) infinite}"
        "@keyframes bl{50%{opacity:0}}"
        ".pulse{animation:pl 1.4s steps(1) infinite}"
        "@keyframes pl{50%{opacity:.45}}"
        "@keyframes pop{from{opacity:0}}"
        "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
        + extra
    )


def svg_open(w, h, title, extra_css=""):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{w}" height="{h}" viewBox="0 0 {w} {h}" shape-rendering="crispEdges" role="img" '
        f'aria-label="{esc(title)}"><title>{esc(title)}</title><style>{css(extra_css)}</style>'
    )


def pbox(x, y, w, h, fill, stroke, n=4, sw=2, shadow=None):
    """Rectangle with stepped (pixel) corners. n = notch size in px."""
    pts = [(x + n, y), (x + w - n, y), (x + w - n, y + n), (x + w, y + n), (x + w, y + h - n),
           (x + w - n, y + h - n), (x + w - n, y + h), (x + n, y + h), (x + n, y + h - n),
           (x, y + h - n), (x, y + n), (x + n, y + n)]
    poly = " ".join(f"{a},{b}" for a, b in pts)
    out = ""
    if shadow:
        sh = " ".join(f"{a + 4},{b + 4}" for a, b in pts)
        out += f'<polygon points="{sh}" fill="{shadow}"/>'
    out += f'<polygon points="{poly}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" stroke-linejoin="miter"/>'
    return out


def segbar(x, y, count, filled, w, h, gap, on, off, animate=False):
    out = []
    for i in range(count):
        col = on if i < filled else off
        style = f' style="animation:pop .01s both;animation-delay:{i * 0.03:.2f}s"' if animate and i < filled else ""
        out.append(f'<rect x="{x + i * (w + gap):.1f}" y="{y}" width="{w}" height="{h}" fill="{col}"{style}/>')
    return "".join(out)


def checker(x, y, w, h, sq, t, opacity=0.55):
    """A strip of chessboard squares."""
    cols, rows = int(w // sq), max(1, int(h // sq))
    out = [f'<g opacity="{opacity}"><rect x="{x}" y="{y}" width="{cols * sq}" height="{rows * sq}" fill="{t["sqL"]}"/>']
    for r in range(rows):
        for c in range(cols):
            if (r + c) % 2 == 1:
                out.append(f'<rect x="{x + c * sq}" y="{y + r * sq}" width="{sq}" height="{sq}" fill="{t["sqD"]}"/>')
    out.append("</g>")
    return "".join(out)


def discrete(values, dur, attr=None, transform=None):
    n = len(values)
    kt = ";".join(f"{i / n:.4f}" for i in range(n))
    vals = ";".join(values)
    if transform:
        return (f'<animateTransform attributeName="transform" type="{transform}" values="{vals}" keyTimes="{kt}" '
                f'calcMode="discrete" dur="{dur}s" repeatCount="indefinite"/>')
    return (f'<animate attributeName="{attr}" values="{vals}" keyTimes="{kt}" calcMode="discrete" '
            f'dur="{dur}s" repeatCount="indefinite"/>')


# --------------------------------------------------------------------------- pixel pieces
def _runs(cells, x, y, s, fill):
    rows = {}
    for c, r in cells:
        rows.setdefault(r, []).append(c)
    out = []
    for r in sorted(rows):
        cols = sorted(rows[r])
        start = prev = cols[0]
        for c in cols[1:] + [None]:
            if c is not None and c == prev + 1:
                prev = c
                continue
            out.append(f'<rect x="{x + start * s:g}" y="{y + r * s:g}" width="{(prev - start + 1) * s:g}" height="{s:g}" fill="{fill}"/>')
            if c is not None:
                start = prev = c
    return "".join(out)


def piece_svg(name, x, y, s, fill, outline=None):
    """Pixel piece with its top-left at (x, y), each pixel s units wide."""
    cells = {(c, r) for r, row in enumerate(PIECES[name]) for c, ch in enumerate(row) if ch == "#"}
    out = ""
    if outline:
        ring = {(c + dc, r + dr) for c, r in cells for dc in (-1, 0, 1) for dr in (-1, 0, 1)} - cells
        out += _runs(ring, x, y, s, outline)
    return out + _runs(cells, x, y, s, fill)


def rank_title(level):
    for limit, name in ((10, "Pawn"), (20, "Knight"), (30, "Bishop"), (40, "Rook"), (50, "Queen")):
        if level < limit:
            return name
    return "King"


# --------------------------------------------------------------------------- player card
SQ = 34


def frames_for(piece):
    if piece == "pawn":  # the pawn walks up the board and promotes
        return [("pawn", (2, 3)), ("pawn", (2, 2)), ("pawn", (2, 1)), ("pawn", (2, 0)), ("queen", (2, 0))]
    return [(piece, p) for p in CYCLES[piece]]


def board_portrait(cfg, t, px, py):
    piece = cfg.get("piece", "knight")
    if piece not in CYCLES and piece != "pawn":
        piece = "knight"
    bx, by = px + 26, py + 14
    o = []
    for r in range(4):
        for c in range(4):
            col = t["sqL"] if (r + c) % 2 == 0 else t["sqD"]
            o.append(f'<rect x="{bx + c * SQ}" y="{by + r * SQ}" width="{SQ}" height="{SQ}" fill="{col}"/>')
    for i, f in enumerate("abcd"):
        o.append(f'<text x="{bx + i * SQ + SQ / 2}" y="{by + 4 * SQ + 14}" text-anchor="middle" style="font-size:10px;fill:{t["dim"]}">{f}</text>')
    for r in range(4):
        o.append(f'<text x="{px + 14}" y="{by + r * SQ + SQ / 2 + 4}" text-anchor="middle" style="font-size:10px;fill:{t["dim"]}">{4 - r}</text>')

    frames = frames_for(piece)
    n = len(frames)
    at = lambda p: (bx + p[0] * SQ, by + p[1] * SQ)
    froms = [frames[k - 1][1] for k in range(n)]
    if piece == "pawn":
        froms[0] = frames[0][1]
    off = (SQ - 27) / 2

    if SNAP is not None:
        k = int(SNAP) % n
        fx, fy = at(froms[k])
        tx, ty = at(frames[k][1])
        o.append(f'<rect x="{fx}" y="{fy}" width="{SQ}" height="{SQ}" fill="{t["warn"]}" opacity=".55"/>')
        o.append(f'<rect x="{tx}" y="{ty}" width="{SQ}" height="{SQ}" fill="{t["warn"]}" opacity=".55"/>')
        o.append(f'<g transform="translate({tx},{ty})">{piece_svg(frames[k][0], off, off, 3, t["pw"], t["pb"])}</g>')
        return "".join(o)

    for which, plist in (("from", froms), ("to", [f[1] for f in frames])):
        xs = [f"{at(p)[0]}" for p in plist]
        ys = [f"{at(p)[1]}" for p in plist]
        o.append(f'<rect x="{xs[0]}" y="{ys[0]}" width="{SQ}" height="{SQ}" fill="{t["warn"]}" opacity=".55">'
                 f'{discrete(xs, n, attr="x")}{discrete(ys, n, attr="y")}</rect>')
    names = list(dict.fromkeys(f[0] for f in frames))
    for name in names:
        vals = [f"{at(p)[0]},{at(p)[1]}" for _, p in frames]
        extra = ""
        if len(names) > 1:
            extra = discrete(["1" if f[0] == name else "0" for f in frames], n, attr="opacity")
        o.append(f'<g transform="translate({vals[0]})">{discrete(vals, n, transform="translate")}{extra}'
                 f'{piece_svg(name, off, off, 3, t["pw"], t["pb"])}</g>')
    return "".join(o)


def build_player(cfg, t, s):
    W = 900
    handle = cfg["github"]
    name = cfg.get("name", handle)
    total = int(s.get("total_contributions", 0))
    level = int(cfg.get("level") or max(1, math.isqrt(total)))
    lo, nxt = level * level, (level + 1) ** 2
    frac = float(cfg.get("level_progress", 0.5)) if cfg.get("level") else (total - lo) / (nxt - lo)
    frac = max(0.0, min(1.0, frac))
    H = 386

    o = []
    o.append(f'<line x1="3" y1="40" x2="{W - 3}" y2="40" stroke="{t["line"]}" stroke-width="2"/>')
    o.append(f'<text x="28" y="26" style="font-size:12px;font-weight:700;letter-spacing:2px;fill:{t["edge"]}">WHITE TO MOVE</text>')
    coin = cfg.get("coin", "open to work")
    o.append(f'<text x="{W - 32}" y="26" text-anchor="end" style="font-size:12px;fill:{t["text"]}">{esc(coin)}</text>')
    o.append(f'<rect class="blink" x="{W - 32 - len(coin) * 12 * CW - 18:.0f}" y="17" width="10" height="10" fill="{t["warn"]}"/>')

    # portrait: mini board, your piece, rank
    px, py, pw, ph = 28, 58, 176, 176
    o.append(pbox(px, py, pw, ph, t["panel"], t["edge"], n=6))
    o.append(board_portrait(cfg, t, px, py))
    o.append(pbox(px + 8, py + ph + 10, pw - 16, 30, t["edge"], t["edge"], n=4))
    o.append(f'<text x="{px + pw / 2}" y="{py + ph + 30}" text-anchor="middle" style="font-size:14px;font-weight:700;fill:{t["bg"]}">LV {level} · {rank_title(level)}</text>')

    # identity + next move
    x0, x1 = 228, W - 32
    o.append(f'<text x="{x0}" y="84" style="font-size:26px;font-weight:700;fill:{t["text"]}">{esc(trunc(name, 30))}</text>')
    o.append(f'<text x="{x0}" y="108" style="font-size:13px;fill:{t["dim"]}">{esc(cfg.get("class", "ML engineer, playing the long game"))}</text>')
    o.append(pbox(x0, 122, x1 - x0, 46, t["panel"], t["warn"], n=4))
    o.append(f'<text class="lbl" x="{x0 + 14}" y="140" style="fill:{t["warn"]};font-weight:700">NEXT MOVE</text>')
    o.append(f'<text x="{x0 + 14}" y="158" style="font-size:12.5px;fill:{t["text"]}">{esc(trunc(cfg.get("next_move", ""), 78))}</text>')

    # progress toward the next level
    segs = 34
    bx, bend = x0 + 34, x1 - 132
    step = (bend - bx) / segs
    o.append(f'<text x="{x0}" y="200" style="font-size:13px;font-weight:700;fill:{t["edge"]}">XP</text>')
    o.append(segbar(bx, 188, segs, round(frac * segs), step - 3, 15, 3, t["hi"], t["line"], animate=True))
    o.append(f'<text x="{x1}" y="200" text-anchor="end" style="font-size:12px;fill:{t["text"]}">{total:,} / {nxt:,}</text>')
    o.append(f'<text x="{x0}" y="224" style="font-size:11px;fill:{t["dim"]}">{max(0, nxt - total):,} xp to level {level + 1}. 1 contribution = 1 xp.</text>')

    # attributes
    attrs = cfg.get("attributes", [])[:6]
    o.append(f'<text class="lbl" x="{x0}" y="262" style="fill:{t["dim"]}">ATTRIBUTES</text>')
    o.append(f'<line x1="{x0 + 100}" y1="258" x2="{x1}" y2="258" stroke="{t["line"]}" stroke-width="2"/>')
    for i, (label, val) in enumerate(attrs):
        cx, cy = x0 + (i % 2) * 320, 288 + (i // 2) * 28
        val = max(0, min(10, int(val)))
        o.append(f'<text x="{cx}" y="{cy}" style="font-size:12px;font-weight:700;fill:{t["text"]}">{esc(label)}</text>')
        o.append(segbar(cx + 72, cy - 11, 10, val, 12, 12, 3, t["hi"], t["line"]))
        o.append(f'<text x="{cx + 232}" y="{cy}" style="font-size:11px;fill:{t["dim"]}">{val}/10</text>')

    head = svg_open(W, H, f"{name}: player card")
    head += pbox(2, 2, W - 4, H - 4, t["bg"], t["edge"], n=8, sw=3)
    return head + "".join(o) + checker(14, H - 22, W - 28, 8, 8, t) + "</svg>"


# --------------------------------------------------------------------------- commit snake
def sample_calendar(handle, today):
    rnd = random.Random(int(hashlib.md5(handle.encode()).hexdigest()[:8], 16))
    dow = (today.weekday() + 1) % 7
    start = today - datetime.timedelta(days=dow + 52 * 7)
    weeks = []
    for w in range(53):
        burst = rnd.random() < 0.28
        wk = []
        for d in range(7):
            day = start + datetime.timedelta(days=w * 7 + d)
            if day > today:
                wk.append(None)
                continue
            p = (0.85 if burst else 0.32) * (0.45 if d in (0, 6) else 1)
            wk.append(rnd.choice([1, 1, 2, 3, 4, 6, 9]) if rnd.random() < p else 0)
        weeks.append(wk)
    return weeks, start


def build_snake(cfg, t, s):
    if s.get("calendar"):
        weeks = s["calendar"]
        start = datetime.date.fromisoformat(s["calendar_start"])
    else:
        weeks, start = sample_calendar(cfg["github"], datetime.date.today())
    W, x0, y0, pitch, cell = 900, 36, 78, 16, 14
    nw = len(weeks)
    vals = [c for wk in weeks for c in wk if c]
    mx = max(vals) if vals else 1
    level = lambda c: 0 if not c else min(4, max(1, math.ceil(4 * c / mx)))
    op = [0, 0.38, 0.58, 0.8, 1.0]
    head_piece = cfg.get("piece", "knight")
    head_piece = head_piece if head_piece in PIECES else "knight"

    # serpentine path over the board, with run-in and run-out off the board
    order = [(w, d) for w in range(nw) for d in (range(7) if w % 2 == 0 else range(6, -1, -1))]
    runin, runout, st = 8, 9, 0.08
    pt = lambda w, d: (x0 + w * pitch, y0 + d * pitch)
    pts = [(x0 - (runin - i) * pitch, y0) for i in range(runin)]
    pts += [pt(w, d) for w, d in order]
    lx, ly = pts[-1]
    pts += [(lx + (i + 1) * pitch, ly) for i in range(runout)]
    T = (len(pts) - 1) * st
    real = bool(s.get("calendar"))
    n_active = sum(1 for v in vals if v)
    n_total = sum(1 for wk in weeks for c in wk if c is not None)
    idx_now = int(SNAP / st) if SNAP is not None else None

    o = []
    # board squares + commits
    for k, (w, d) in enumerate(order):
        c = weeks[w][d]
        if c is None:
            continue
        cx, cy = pt(w, d)
        base = t["sqL"] if (w + d) % 2 == 0 else t["sqD"]
        o.append(f'<rect x="{cx}" y="{cy}" width="{cell}" height="{cell}" fill="{base}" opacity="{0.14 if (w + d) % 2 == 0 else 0.3}"/>')
        l = level(c)
        if l:
            if idx_now is not None:
                eaten = (runin + k) <= idx_now
                o.append(f'<rect x="{cx}" y="{cy}" width="{cell}" height="{cell}" fill="{t["hi"]}" opacity="{0.1 if eaten else op[l]}"/>')
            else:
                frac = (runin + k) * st / T
                o.append(f'<rect x="{cx}" y="{cy}" width="{cell}" height="{cell}" fill="{t["hi"]}" opacity="{op[l]}">'
                         f'<animate attributeName="opacity" values="{op[l]};0.1" keyTimes="0;{frac:.4f}" calcMode="discrete" dur="{T:.2f}s" repeatCount="indefinite"/></rect>')

    # month and weekday labels
    lastw, lastm = -9, None
    for w in range(nw):
        d = start + datetime.timedelta(days=7 * w)
        if d.month != lastm and w - lastw >= 3:
            o.append(f'<text x="{x0 + w * pitch}" y="{y0 - 8}" style="font-size:10px;fill:{t["dim"]}">{d.strftime("%b")}</text>')
            lastw = w
        lastm = d.month
    for row, label in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        o.append(f'<text x="{x0 - 8}" y="{y0 + row * pitch + 11}" text-anchor="end" style="font-size:9px;fill:{t["dim"]}">{label}</text>')

    # the snake: a trail of squares led by your piece
    nseg = 8

    def body(i):
        return f'<rect x="2" y="2" width="10" height="10" fill="{t["warn"]}" opacity="{0.95 - i * 0.09:.2f}"/>'

    headg = piece_svg(head_piece, 2, 2, 1, t["pw"], t["pb"])
    snake = []
    if SNAP is not None:
        for i in range(nseg, 0, -1):
            j = idx_now - i
            if 0 <= j < len(pts):
                snake.append(f'<g transform="translate({pts[j][0]},{pts[j][1]})">{body(i - 1)}</g>')
        j = min(idx_now, len(pts) - 1)
        snake.append(f'<g transform="translate({pts[j][0]},{pts[j][1]})">{headg}</g>')
    else:
        def mover(content, i):
            begin = -(T - i * st) if i else 0
            return (f'<g><animateMotion dur="{T:.2f}s" repeatCount="indefinite" begin="{begin:.2f}s">'
                    f'<mpath href="#rail" xlink:href="#rail"/></animateMotion>{content}</g>')
        for i in range(nseg, 0, -1):
            snake.append(mover(body(i - 1), i))
        snake.append(mover(headg, 0))
    path_d = "M" + " L".join(f"{x},{y}" for x, y in pts)

    H = y0 + 7 * pitch + 56
    head = svg_open(W, H, "Commit snake over the contribution board")
    head += f'<defs><path id="rail" d="{path_d}" fill="none"/><clipPath id="board"><rect x="{x0 - 1}" y="{y0 - 1}" width="{nw * pitch + 1}" height="{7 * pitch + 1}"/></clipPath></defs>'
    head += pbox(2, 2, W - 4, H - 4, t["bg"], t["edge"], n=8, sw=3)
    head += f'<text x="28" y="30" style="font-size:12px;font-weight:700;letter-spacing:2px;fill:{t["edge"]}">COMMIT SNAKE</text>'
    head += f'<text x="{W - 28}" y="30" text-anchor="end" style="font-size:11px;fill:{t["dim"]}">1 square = 1 day. the snake captures what you shipped</text>'
    head += f'<line x1="3" y1="44" x2="{W - 3}" y2="44" stroke="{t["line"]}" stroke-width="2"/>'
    head += "".join(o) + f'<g clip-path="url(#board)">{"".join(snake)}</g>'
    # legend
    ly = y0 + 7 * pitch + 28
    head += f'<text x="{x0}" y="{ly}" style="font-size:10px;fill:{t["dim"]}">less</text>'
    for i in range(1, 5):
        head += f'<rect x="{x0 + 30 + (i - 1) * 16}" y="{ly - 10}" width="12" height="12" fill="{t["hi"]}" opacity="{op[i]}"/>'
    head += f'<text x="{x0 + 100}" y="{ly}" style="font-size:10px;fill:{t["dim"]}">more</text>'
    head += f'<text x="{x0 + nw * pitch - 16}" y="{ly}" text-anchor="end" style="font-size:10px;fill:{t["dim"]}">{esc(f"{n_active} of {n_total} squares captured this year" if real else "sample board: run with --live and a token for your real data")}</text>'
    return head + checker(14, H - 22, W - 28, 8, 8, t) + "</svg>"


# --------------------------------------------------------------------------- stats bar
def lang_color(name, i, t):
    return LANG_COLORS.get(name) or [t["hi"], t["warn"], t["edge"], t["dim"], "#f472b6", "#60a5fa"][i % 6]


def norm_langs(d, top=7):
    items = sorted(d.items(), key=lambda kv: kv[1], reverse=True)
    tot = sum(v for _, v in items) or 1
    out = [(k, 100 * v / tot) for k, v in items[:top]]
    rest = sum(v for _, v in items[top:])
    if rest:
        out.append(("Other", 100 * rest / tot))
    return out


def alloc64(langs):
    raw = [p * 64 / 100 for _, p in langs]
    base = [int(r) for r in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - base[i], reverse=True)[: 64 - sum(base)]:
        base[i] += 1
    return base


def build_stats(cfg, t, s):
    W, H = 900, 238
    o = []
    langs = norm_langs(s.get("languages", {}))
    if langs:
        counts = alloc64(langs)
        seq = [i for i, n in enumerate(counts) for _ in range(n)]
        for k, li in enumerate(seq):
            r, c = divmod(k, 8)
            o.append(f'<rect x="{28 + c * 14}" y="{60 + r * 14}" width="13" height="13" fill="{lang_color(langs[li][0], li, t)}" opacity="{1 if (r + c) % 2 == 0 else 0.82}"/>')
        o.append(f'<rect x="27" y="59" width="114" height="114" fill="none" stroke="{t["edge"]}" stroke-width="2"/>')
        o.append(f'<text x="28" y="192" style="font-size:10px;fill:{t["dim"]}">language board, 64 squares</text>')
        for i, (k, p) in enumerate(langs):
            col, row = divmod(i, 4)
            lx, ly = 166 + col * 128, 72 + row * 26
            o.append(f'<rect x="{lx}" y="{ly - 10}" width="11" height="11" fill="{lang_color(k, i, t)}"/>'
                     f'<text x="{lx + 18}" y="{ly}" style="font-size:11.5px;fill:{t["text"]}">{esc(trunc(k, 11))}</text>'
                     f'<text x="{lx + 18}" y="{ly + 13}" style="font-size:10px;fill:{t["dim"]}">{p:.1f}%</text>')
    o.append(f'<line x1="428" y1="62" x2="428" y2="{H - 44}" stroke="{t["line"]}" stroke-width="2"/>')
    cells = [("total_contributions", "contributions"), ("commits", "commits"), ("prs", "pull requests"),
             ("issues", "issues"), ("repos", "public repos"), ("stars", "stars"),
             ("followers", "followers"), ("current_streak", "current streak"), ("longest_streak", "best streak")]
    for i, (k, label) in enumerate(cells):
        r, c = divmod(i, 3)
        cx, cy = 452 + c * 148, 84 + r * 48
        o.append(f'<text x="{cx}" y="{cy}" style="font-size:22px;font-weight:700;fill:{t["text"]}">{int(s.get(k, 0)):,}</text>'
                 f'<text x="{cx}" y="{cy + 15}" style="font-size:10px;fill:{t["dim"]}">{label}</text>')
    head = svg_open(W, H, "Stats bar")
    head += pbox(2, 2, W - 4, H - 4, t["bg"], t["edge"], n=8, sw=3)
    head += f'<text x="28" y="30" style="font-size:12px;font-weight:700;letter-spacing:2px;fill:{t["edge"]}">STATS BAR</text>'
    if s.get("updated"):
        head += f'<text x="{W - 28}" y="30" text-anchor="end" style="font-size:11px;fill:{t["dim"]}">refreshed {esc(s["updated"])}</text>'
    head += f'<line x1="3" y1="44" x2="{W - 3}" y2="44" stroke="{t["line"]}" stroke-width="2"/>'
    return head + "".join(o) + checker(14, H - 22, W - 28, 8, 8, t) + "</svg>"


# --------------------------------------------------------------------------- skill tree
def build_tree(cfg, t):
    layers = cfg.get("skill_layers", [])
    if not layers:
        return None
    W = 900
    L = len(layers)
    maxn = max(len(l["skills"]) for l in layers)
    sp, top = 70, 96
    H = top + maxn * sp + 52
    xs = [100 + i * (W - 200) / (L - 1) for i in range(L)] if L > 1 else [W / 2]
    pos = {}
    for i, l in enumerate(layers):
        off = (maxn - len(l["skills"])) * sp / 2
        for k in range(len(l["skills"])):
            pos[(i, k)] = (xs[i], top + off + k * sp + 14)
    state = lambda i, k: layers[i]["skills"][k].get("state", "locked")

    faint, lit = [], []
    for i in range(L - 1):
        for a in range(len(layers[i]["skills"])):
            for b in range(len(layers[i + 1]["skills"])):
                (xa, ya), (xb, yb) = pos[(i, a)], pos[(i + 1, b)]
                sa, sb = state(i, a), state(i + 1, b)
                geo = f'x1="{xa + 19:.0f}" y1="{ya:.0f}" x2="{xb - 19:.0f}" y2="{yb:.0f}"'
                if sa == "done" and sb == "done":
                    lit.append(f'<line class="flow" {geo} stroke="{t["hi"]}" stroke-width="2" stroke-dasharray="4 8" opacity=".85"/>')
                elif "locked" in (sa, sb):
                    faint.append(f'<line {geo} stroke="{t["mute"]}" stroke-width="1" opacity=".4"/>')
                else:
                    faint.append(f'<line {geo} stroke="{t["warn"]}" stroke-width="1.5" stroke-dasharray="2 6" opacity=".7"/>')

    nodes = []
    for (i, k), (x, y) in pos.items():
        sk = layers[i]["skills"][k]
        st = state(i, k)
        pname = sk.get("piece") or layers[i].get("piece") or LAYER_PIECES[min(i, 5)]
        ox, oy = x - 13.5, y - 13.5
        if st == "done":
            nodes.append(piece_svg(pname, ox, oy, 3, t["pw"], t["pb"]))
            col = t["text"]
        elif st == "training":
            nodes.append(f'<g class="pulse">{piece_svg(pname, ox, oy, 3, t["warn"], t["pb"])}</g>')
            col = t["warn"]
        else:
            nodes.append(f'<g opacity=".55">{piece_svg(pname, ox, oy, 3, t["mute"])}</g>')
            col = t["dim"]
        label = trunc(sk["name"], 16)
        lw = len(label) * 11.5 * CW + 8
        nodes.append(f'<rect x="{x - lw / 2:.0f}" y="{y + 21:.0f}" width="{lw:.0f}" height="17" fill="{t["bg"]}"/>'
                     f'<text x="{x:.0f}" y="{y + 34:.0f}" text-anchor="middle" style="font-size:11.5px;fill:{col}">{esc(label)}</text>')

    titles = "".join(
        f'<text class="lbl" x="{xs[i]:.0f}" y="76" text-anchor="middle" style="fill:{t["dim"]}">{esc(l["name"])}</text>'
        for i, l in enumerate(layers)
    )
    head = svg_open(W, H, "Skill tree drawn as a neural network of chess pieces",
                    "@keyframes flow{to{stroke-dashoffset:-12}}.flow{animation:flow 1s linear infinite}")
    head += pbox(2, 2, W - 4, H - 4, t["bg"], t["edge"], n=8, sw=3)
    head += f'<text x="28" y="32" style="font-size:12px;font-weight:700;letter-spacing:2px;fill:{t["edge"]}">SKILL TREE</text>'
    head += f'<text x="{W - 28}" y="32" text-anchor="end" style="font-size:11px;fill:{t["dim"]}">a lit line joins developed pieces: a skill chain I can run end to end</text>'
    head += f'<line x1="3" y1="46" x2="{W - 3}" y2="46" stroke="{t["line"]}" stroke-width="2"/>'
    ly = H - 36
    leg = (
        f'<g>{piece_svg("pawn", 28, ly - 11, 1, t["pw"], t["pb"])}</g><text x="46" y="{ly}" style="font-size:11px;fill:{t["dim"]}">developed</text>'
        f'<g>{piece_svg("pawn", 140, ly - 11, 1, t["warn"], t["pb"])}</g><text x="158" y="{ly}" style="font-size:11px;fill:{t["dim"]}">developing now</text>'
        f'<g opacity=".55">{piece_svg("pawn", 288, ly - 11, 1, t["mute"])}</g><text x="306" y="{ly}" style="font-size:11px;fill:{t["dim"]}">not yet on the board</text>'
    )
    return head + titles + "".join(faint) + "".join(lit) + "".join(nodes) + leg + checker(14, H - 22, W - 28, 8, 8, t) + "</svg>"


# --------------------------------------------------------------------------- game cards
STATUS = {"won": "hi", "in play": "warn", "puzzle": "dim"}


def build_game(p, t):
    W, H = 440, 218
    status = p.get("status", "won").lower()
    scol = t[STATUS.get(status, "dim")]
    label = status + (f" {int(p['progress'])}%" if status == "in play" and "progress" in p else "")
    d = max(1, min(5, int(p.get("difficulty", 3))))
    dpiece = DIFF_PIECES[d - 1]
    o = [svg_open(W, H, p["name"])]
    o.append(pbox(0, 0, W - 4, H - 4, t["panel"], t["edge"], n=6, shadow=t["line"]))
    o.append(f'<line x1="2" y1="30" x2="{W - 6}" y2="30" stroke="{t["line"]}" stroke-width="2"/>')
    o.append(f'<text x="20" y="20" style="font-size:11px;fill:{t["dim"]}">{esc(trunc(p.get("repo", p["name"]), 34))}</text>')
    cw_ = len(label) * 10 * CW + 16
    o.append(f'<rect x="{W - 22 - cw_:.0f}" y="7" width="{cw_:.0f}" height="17" fill="{scol}"/>'
             f'<text x="{W - 22 - cw_ / 2:.0f}" y="19.5" text-anchor="middle" style="font-size:10px;font-weight:700;letter-spacing:.5px;fill:{t["bg"]}">{esc(label)}</text>')
    o.append(piece_svg(dpiece, 20, 42, 2, t["pw"], t["pb"]))
    o.append(f'<text x="54" y="60" style="font-size:17px;font-weight:700;fill:{t["text"]}">{esc(trunc(p["name"], 33))}</text>')
    for i, ln in enumerate(textwrap.wrap(p.get("desc", ""), 54)[:3]):
        o.append(f'<text x="20" y="{88 + i * 15}" style="font-size:11.5px;fill:{t["text"]}" opacity=".8">{esc(ln)}</text>')
    if p.get("result"):
        o.append(f'<rect x="20" y="136" width="8" height="8" fill="{t["warn"]}"/>'
                 f'<text x="36" y="144" style="font-size:10.5px;fill:{t["dim"]}">result</text>'
                 f'<text x="86" y="144" style="font-size:12.5px;font-weight:700;fill:{t["hi"]}">{esc(trunc(p["result"], 40))}</text>')
    tx = 20.0
    for tag in p.get("tags", []):
        w = len(tag) * 10.5 * CW + 16
        if tx + w > W - 24:
            break
        o.append(f'<rect x="{tx:.0f}" y="154" width="{w:.0f}" height="20" fill="none" stroke="{t["line"]}" stroke-width="2"/>'
                 f'<text x="{tx + w / 2:.0f}" y="168" text-anchor="middle" style="font-size:10.5px;fill:{t["text"]}">{esc(tag)}</text>')
        tx += w + 8
    o.append(f'<text x="20" y="194" style="font-size:10px;fill:{t["dim"]}">difficulty: {dpiece} ({PIECE_VALUE[dpiece]} pts)</text>')
    meta = f'{p.get("lang", "")}, {int(p.get("stars", 0))} stars, {p.get("updated", "")}'.strip(", ")
    o.append(f'<text x="{W - 22}" y="194" text-anchor="end" style="font-size:10px;fill:{t["dim"]}">{esc(trunc(meta, 34))}</text>')
    o.append(checker(12, H - 20, W - 28, 8, 8, t, 0.45))
    return "".join(o) + "</svg>"


# --------------------------------------------------------------------------- buttons
def build_button(label, t):
    h = 38
    w = int(len(label) * 13 * CW + 62)
    return (
        svg_open(w, h, label)
        + pbox(1, 1, w - 6, h - 6, t["panel"], t["edge"], n=4, shadow=t["line"])
        + piece_svg("pawn", 12, 9, 2, t["pw"], t["pb"])
        + f'<text x="42" y="23" style="font-size:13px;font-weight:700;fill:{t["text"]}">{esc(label)}</text>'
        + "</svg>"
    )


# --------------------------------------------------------------------------- README
def build_readme(cfg, n_games, has_tree):
    name = cfg.get("name", cfg["github"])
    img = lambda f, alt: f'<img src="assets/{f}" alt="{esc(alt)}" width="100%">'
    L = [
        "<!-- Generated by build.py from profile.json. Edit profile.json, then run: python build.py -->",
        '<div align="center">', "", img("player.svg", f"{name}: player card"), "", "</div>", "",
    ]
    nb = cfg.get("now_building")
    if nb:
        L += [f"### Next move: {nb['title']}", ""]
        if nb.get("tagline"):
            L += [f"*{nb['tagline']}*", ""]
        L += [f"- {b}" for b in nb.get("bullets", [])]
        if nb.get("links"):
            L += ["", " · ".join(f"[{l['label']}]({l['url']})" for l in nb["links"])]
        L.append("")
    L += ['<div align="center">', "", img("snake.svg", "Commit snake over my contribution board"), "", "</div>", ""]
    L += ['<div align="center">', "", img("stats.svg", "GitHub stats bar"), "", "</div>", ""]
    if has_tree:
        L += ['<div align="center">', "", img("skilltree.svg", "Skill tree as a neural network of chess pieces"), "", "</div>", ""]
    if n_games:
        L += ['<div align="center">', ""]
        for i, p in enumerate(cfg["projects"], 1):
            url = p.get("url") or (f"https://github.com/{p['repo']}" if p.get("repo") else "#")
            L.append(f'<a href="{esc(url)}"><img src="assets/game-{i}.svg" width="48.5%" alt="{esc(p["name"])}"></a>')
        L += ["", "</div>", ""]
    for sec in cfg.get("sections", []):
        L += ["<details>", f"<summary><b>{sec['title']}</b></summary>", ""]
        L += [f"- {it}" for it in sec.get("items", [])]
        L += ["", "</details>", ""]
    links = cfg.get("links", [])
    if links:
        L += ['<p align="center">']
        for l in links:
            L.append(f'<a href="{esc(l["url"])}"><img src="assets/btn-{slug(l["label"])}.svg" height="38" alt="{esc(l["label"])}"></a>')
        L += ["</p>", ""]
    if cfg.get("footer"):
        L += [f'<p align="center"><sub>{cfg["footer"]}</sub></p>', ""]
    if cfg.get("extra_markdown"):
        L += [cfg["extra_markdown"], ""]
    return "\n".join(L)


# --------------------------------------------------------------------------- live data
def gh(url, token=None, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "chess-profile")
    if data:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def rel_time(iso):
    dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    days = (datetime.datetime.now(datetime.timezone.utc) - dt).days
    if days < 1:
        return "today"
    if days < 30:
        return f"{days}d ago"
    if days < 365:
        return f"{days // 30}mo ago"
    return f"{days // 365}y ago"


def compute_streaks(days, today):
    longest = cur = 0
    for _, c in days:
        cur = cur + 1 if c > 0 else 0
        longest = max(longest, cur)
    i = len(days) - 1
    if i >= 0 and days[i][1] == 0 and days[i][0] == today:
        i -= 1
    current = 0
    while i >= 0 and days[i][1] > 0:
        current += 1
        i -= 1
    return longest, current


GQL = """query($login:String!,$from:DateTime!,$to:DateTime!){user(login:$login){contributionsCollection(from:$from,to:$to){
totalCommitContributions totalPullRequestContributions totalIssueContributions
contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}}}}"""
GQL_CAL = """query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{weeks{contributionDays{date contributionCount weekday}}}}}}"""


def fetch_stats(login, token):
    s = {"updated": fmt_date(datetime.date.today())}
    user = gh(f"https://api.github.com/users/{login}", token)
    s["repos"], s["followers"] = user["public_repos"], user["followers"]
    repos, page = [], 1
    while page <= 5:
        chunk = gh(f"https://api.github.com/users/{login}/repos?per_page=100&type=owner&page={page}", token)
        repos += chunk
        if len(chunk) < 100:
            break
        page += 1
    own = [r for r in repos if not r["fork"]]
    s["stars"] = sum(r["stargazers_count"] for r in own)
    langs = {}
    for r in own[:40]:
        try:
            for k, v in gh(r["languages_url"], token).items():
                langs[k] = langs.get(k, 0) + v
        except Exception:
            pass
    if langs:
        s["languages"] = langs
    if not token:
        print("! No GITHUB_TOKEN set: skipping XP, commits, streaks and the snake's real calendar.")
        return s
    today = datetime.date.today()
    days, commits, prs, issues, total = [], 0, 0, 0, 0
    for y in range(int(user["created_at"][:4]), today.year + 1):
        res = gh("https://api.github.com/graphql", token, {
            "query": GQL,
            "variables": {"login": login, "from": f"{y}-01-01T00:00:00Z", "to": f"{y}-12-31T23:59:59Z"},
        })
        cc = res["data"]["user"]["contributionsCollection"]
        commits += cc["totalCommitContributions"]
        prs += cc["totalPullRequestContributions"]
        issues += cc["totalIssueContributions"]
        total += cc["contributionCalendar"]["totalContributions"]
        for w in cc["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                dd = datetime.date.fromisoformat(d["date"])
                if dd <= today:
                    days.append((dd, d["contributionCount"]))
    days.sort()
    longest, current = compute_streaks(days, today)
    s.update(commits=commits, prs=prs, issues=issues, total_contributions=total,
             longest_streak=longest, current_streak=current)
    cal = gh("https://api.github.com/graphql", token, {"query": GQL_CAL, "variables": {"login": login}})
    weeks_raw = cal["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"][-53:]
    weeks, start = [], None
    for w in weeks_raw:
        row = [None] * 7
        for d in w["contributionDays"]:
            row[d["weekday"]] = d["contributionCount"]
            if start is None:
                start = datetime.date.fromisoformat(d["date"]) - datetime.timedelta(days=d["weekday"])
        weeks.append(row)
    s["calendar"], s["calendar_start"] = weeks, start.isoformat()
    return s


def enrich_project(p, token):
    repo = p.get("repo")
    if not repo:
        return
    try:
        r = gh(f"https://api.github.com/repos/{repo}", token)
        p["stars"] = r["stargazers_count"]
        p["updated"] = "updated " + rel_time(r["pushed_at"])
        langs = gh(r["languages_url"], token)
        if langs:
            p["lang"] = max(langs.items(), key=lambda kv: kv[1])[0]
    except Exception as e:
        print(f"! Could not refresh {repo}: {e}")


# --------------------------------------------------------------------------- main
def main():
    global SNAP
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(ROOT, "profile.json"))
    ap.add_argument("--live", action="store_true", help="refresh numbers from the GitHub API")
    ap.add_argument("--snapshot", type=float, default=None, help="write static frames at this time (s) to ./preview")
    args = ap.parse_args()
    SNAP = args.snapshot

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    t = THEMES.get(cfg.get("theme", "walnut"), THEMES["walnut"])
    stats = dict(cfg.get("stats", {}))
    projects = cfg.get("projects", [])

    if args.live:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        try:
            stats.update(fetch_stats(cfg["github"], token))
        except Exception as e:
            print(f"! Live stats failed, using values from profile.json: {e}")
        for p in projects:
            enrich_project(p, token)

    out = os.path.join(ROOT, "preview") if SNAP is not None else ASSETS
    os.makedirs(out, exist_ok=True)
    for old in glob.glob(os.path.join(out, "game-*.svg")) + glob.glob(os.path.join(out, "btn-*.svg")):
        os.remove(old)

    write(os.path.join(out, "player.svg"), build_player(cfg, t, stats))
    write(os.path.join(out, "snake.svg"), build_snake(cfg, t, stats))
    write(os.path.join(out, "stats.svg"), build_stats(cfg, t, stats))
    tree = build_tree(cfg, t)
    if tree:
        write(os.path.join(out, "skilltree.svg"), tree)
    for i, p in enumerate(projects, 1):
        write(os.path.join(out, f"game-{i}.svg"), build_game(p, t))
    for l in cfg.get("links", []):
        write(os.path.join(out, f"btn-{slug(l['label'])}.svg"), build_button(l["label"], t))
    if SNAP is None:
        write(os.path.join(ROOT, "README.md"), build_readme(cfg, len(projects), bool(tree)))
    print(f"Built player card, snake, stats bar, {'skill tree, ' if tree else ''}{len(projects)} games, "
          f"{len(cfg.get('links', []))} buttons" + (" (static snapshot)" if SNAP is not None else ", README.md"))


if __name__ == "__main__":
    main()
