# -*- coding: utf-8 -*-
"""Erzeugt die Marke openEinsatzstatistik: SVG-Logos, Icons, Social-Bilder. Text wird zu Pfaden (keine Schriftabhängigkeit).

Schreibt nach brand/ und static/ des Projekts (Ausgabeordner /out = Projektwurzel). Aufruf aus der Projektwurzel:
  docker build -q -t brand-tools -f tools/Dockerfile.brand tools
  docker run --rm -v "$PWD/tools:/t:ro" -v "$PWD/tools/fonts:/fonts:ro" -v "$PWD:/out" brand-tools python /t/build_brand.py
Die Schriften VT323 und Courier Prime (SIL Open Font License, Lizenztexte in tools/fonts) liegen unter tools/fonts.
"""
import os

import cairosvg
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image

FONTS = "/fonts"
OUT = "/out"

BLAU, TIEF, HELL, AKZENT, INK = "#2F6D92", "#1B3F55", "#E3EEF5", "#E0A43A", "#14293A"

_fonts = {}


def font(name):
    if name not in _fonts:
        f = TTFont(os.path.join(FONTS, name))
        _fonts[name] = (f, f.getGlyphSet(), f.getBestCmap(), f["head"].unitsPerEm)
    return _fonts[name]


def text_path(name, text, size, x, y, tracking=0.0):
    """Pfad (d) und Breite eines Textes; y = Grundlinie."""
    f, gs, cmap, upm = font(name)
    s = size / upm
    pen = SVGPathPen(gs)
    cx = x
    for ch in text:
        g = cmap[ord(ch)]
        tp = TransformPen(pen, (s, 0, 0, -s, cx, y))
        gs[g].draw(tp)
        cx += f["hmtx"][g][0] * s + tracking
    return pen.getCommands(), cx - x - tracking


def text_width(name, text, size, tracking=0.0):
    f, gs, cmap, upm = font(name)
    return sum(f["hmtx"][cmap[ord(c)]][0] for c in text) * size / upm + tracking * (len(text) - 1)


# ---------------------------------------------------------------- Bildmarke (64 × 64)
# Gehäuse wie beim Rechner im Polifka-Logo (weich gerundet), darin zwei Balken und eine Flamme als höchster „Balken“.
CASE = "M14 2h36a12 12 0 0 1 12 12v36a12 12 0 0 1-12 12H14A12 12 0 0 1 2 50V14A12 12 0 0 1 14 2Z"
BAR1 = "M12 37h9a2.5 2.5 0 0 1 2.5 2.5V50a2.5 2.5 0 0 1-2.5 2.5h-9A2.5 2.5 0 0 1 9.5 50V39.5A2.5 2.5 0 0 1 12 37Z"
BAR2 = "M28 29h9a2.5 2.5 0 0 1 2.5 2.5V50a2.5 2.5 0 0 1-2.5 2.5h-9A2.5 2.5 0 0 1 25.5 50V31.5A2.5 2.5 0 0 1 28 29Z"
# Flamme: Spitze oben, Körper endet unten bündig mit den Balken
FLAME = ("M49.5 8C50.5 17 56 22 56 37c0 9-3.5 15.5-8 15.5S40 46 40 37c0-8.5 6.5-12 7.5-20 .3-3 1-6 2-9Z"
         "M48 34c2.6 3.4 4 6.6 4 9.6 0 3.2-1.8 5.4-4 5.4s-4-2.2-4-5.4c0-3 1.4-6.2 4-9.6Z")


FLAME_SMALL = FLAME.split("M48 34")[0]   # ohne Aussparung: bleibt bei 16 px lesbar


def mark(case=BLAU, bars="#fff", flame=AKZENT, size=64, extra="", small=False):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="{size}" height="{size}" '
            f'role="img" aria-label="openEinsatzstatistik">{extra}'
            f'<path d="{CASE}" fill="{case}"/><path d="{BAR1}" fill="{bars}"/><path d="{BAR2}" fill="{bars}"/>'
            f'<path fill-rule="evenodd" d="{FLAME_SMALL if small else FLAME}" fill="{flame}"/></svg>')


def mark_inner(case=BLAU, bars="#fff", flame=AKZENT):
    return (f'<path d="{CASE}" fill="{case}"/><path d="{BAR1}" fill="{bars}"/><path d="{BAR2}" fill="{bars}"/>'
            f'<path fill-rule="evenodd" d="{FLAME}" fill="{flame}"/>')


def mark_white():
    """Einfarbig weiß, für Blau, Rot und Fotos: Gehäuse als Kontur, Balken und Flamme gefüllt."""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="openEinsatzstatistik">'
            f'<path d="{CASE}" fill="none" stroke="#fff" stroke-width="3" transform="translate(32 32) scale(.94) translate(-32 -32)"/>'
            f'<path d="{BAR1}" fill="#fff"/><path d="{BAR2}" fill="#fff"/><path fill-rule="evenodd" d="{FLAME}" fill="#fff"/></svg>')


def mark_mono(color="currentColor"):
    """Einfarbig mit ausgestanzten Balken und Flamme (Stempel, Gravur, Faxe): Gehäuse gefüllt."""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="openEinsatzstatistik">'
            f'<path fill-rule="evenodd" fill="{color}" d="{CASE} {BAR1} {BAR2} {FLAME}"/></svg>')


# ---------------------------------------------------------------- Wortmarke
NAME = "openEinsatzstatistik"
SUB = "FREIE EINSATZSTATISTIK FÜR FEUERWEHREN"
DISPLAY, LABEL = "VT323-Regular.ttf", "CourierPrime-Bold.ttf"


def wordmark_parts(color, size=56, x=0, y=0):
    """Name in VT323 und Unterzeile in Courier Prime Bold, auf die Breite des Namens gespreizt."""
    d1, w1 = text_path(DISPLAY, NAME, size, x, y)
    sub_size = size * 0.215
    n = len(SUB)
    base = text_width(LABEL, SUB, sub_size)
    tracking = (w1 - base) / (n - 1)
    d2, w2 = text_path(LABEL, SUB, sub_size, x, y + size * 0.36, tracking)
    return (f'<path d="{d1}" fill="{color}"/><path d="{d2}" fill="{color}"/>', w1, size * 0.36 + sub_size * 0.2)


def svg(w, h, body, bg=None, label="openEinsatzstatistik"):
    rect = f'<rect width="{w}" height="{h}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:g} {h:g}" width="{w:g}" height="{h:g}" '
            f'role="img" aria-label="{label}">{rect}{body}</svg>')


def horizontal(color, white=False):
    size = 56
    parts, w1, h2 = wordmark_parts(color, size, x=88, y=40)
    m = mark_inner() if not white else ""
    if white:
        m = (f'<path d="{CASE}" fill="none" stroke="#fff" stroke-width="3" transform="translate(32 32) scale(.94) translate(-32 -32)"/>'
             f'<path d="{BAR1}" fill="#fff"/><path d="{BAR2}" fill="#fff"/><path fill-rule="evenodd" d="{FLAME}" fill="#fff"/>')
    mk = f'<g transform="translate(0 0)">{m}</g>'
    return svg(88 + w1, 64, mk + parts)


def stacked(color, white=False):
    size = 56
    parts, w1, h2 = wordmark_parts(color, size)
    W = w1 + 0
    mk = mark_inner() if not white else (
        f'<path d="{CASE}" fill="none" stroke="#fff" stroke-width="3" transform="translate(32 32) scale(.94) translate(-32 -32)"/>'
        f'<path d="{BAR1}" fill="#fff"/><path d="{BAR2}" fill="#fff"/><path fill-rule="evenodd" d="{FLAME}" fill="#fff"/>')
    scale = 1.5
    mw = 64 * scale
    parts, w1, h2 = wordmark_parts(color, size, x=0, y=mw + 20 + 40)
    body = f'<g transform="translate({(w1 - mw) / 2:g} 0) scale({scale})">{mk}</g>' + parts
    return svg(w1, mw + 20 + 40 + size * 0.36 + 6, body)


def wordmark(color):
    parts, w1, h2 = wordmark_parts(color, 56, 0, 44)
    return svg(w1, 44 + h2 + 4, parts)


# ---------------------------------------------------------------- Icons
def app_tile(bg=BLAU, inset=0.0, rounded=False):
    """Quadratische App-Kachel (ohne Transparenz) für Apple/Android; inset verkleinert die Marke (Maskable-Sicherheitszone)."""
    s = 64
    scale = (1 - inset * 2)
    off = s * inset
    # Marke ohne Gehäuse, weiß auf Vollfläche: Balken und Flamme zentriert
    inner = (f'<g transform="translate({off:g} {off:g}) scale({scale:g})">'
             f'<path d="{BAR1}" fill="#fff"/><path d="{BAR2}" fill="#fff"/><path fill-rule="evenodd" d="{FLAME}" fill="{AKZENT}"/></g>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" fill="{bg}"/>{inner}</svg>'


def dots(x, y, cols, rows, pitch, color, r=2, opacity=1):
    return "".join(f'<circle cx="{x + c * pitch}" cy="{y + r_ * pitch}" r="{r}" fill="{color}" opacity="{opacity}"/>'
                   for c in range(cols) for r_ in range(rows))


def social(w=1280, h=640):
    """GitHub-Vorschau / Open Graph: Bernstein nur einmal (Flamme), Rest Blau, Weiß und Nachtblau."""
    body = f'<rect width="{w}" height="{h}" fill="{TIEF}"/>'
    body += dots(w - 420, 48, 14, 11, 24, "#7AB3D6", 2, .3)
    body += f'<g transform="translate(790 150) scale(5.6)">{mark_inner(case=BLAU)}</g>'
    parts, w1, _ = wordmark_parts("#fff", 76, x=72, y=262)
    body += parts
    f = "CourierPrime-Regular.ttf"
    for i, line in enumerate(("Aus dem BKS-Einsatzbericht", "wird die Auswertung.")):
        d, _ = text_path(f, line, 32, 72, 372 + i * 46)
        body += f'<path d="{d}" fill="#fff"/>'
    for i, line in enumerate(("Frei, quelloffen, mandantenfähig.",)):
        d, _ = text_path(f, line, 26, 72, 486 + i * 40)
        body += f'<path d="{d}" fill="{HELL}"/>'
    cr, _ = text_path(LABEL, "AGPL-3.0  ·  POLIFKA IT BERATUNG", 18, 72, h - 52, 2)
    body += f'<path d="{cr}" fill="#7AB3D6"/>'
    return svg(w, h, body)


def write(path, data):
    full = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(data)
    return full


def png(svg_text, path, width, height=None, bg=None):
    full = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    cairosvg.svg2png(bytestring=svg_text.encode(), write_to=full, output_width=width,
                     output_height=height or width, background_color=bg)
    return full


def proof():
    x = 20
    parts = ['<rect width="1500" height="900" fill="#fff"/>']
    for size in (16, 32):
        parts.append(f'<g transform="translate({x} 20) scale({size * 4 / 64})">{mark(small=True).split(">", 1)[1].rsplit("</svg", 1)[0]}</g>')
        x += size * 4 + 20
    parts.append(f'<g transform="translate(20 220)">{horizontal(BLAU).split(">", 1)[1].rsplit("</svg", 1)[0]}</g>')
    parts.append('<rect x="0" y="330" width="760" height="130" fill="#2F6D92"/>')
    parts.append(f'<g transform="translate(20 360)">{horizontal("#fff", white=True).split(">", 1)[1].rsplit("</svg", 1)[0]}</g>')
    parts.append(f'<g transform="translate(900 20) scale(2)">{app_tile().split(">", 1)[1].rsplit("</svg", 1)[0]}</g>')
    parts.append(f'<g transform="translate(20 500) scale(1.2)">{stacked(BLAU).split(">", 1)[1].rsplit("</svg", 1)[0]}</g>')
    parts.append(f'<g transform="translate(640 500) scale(3)">{mark_mono(INK).split(">", 1)[1].rsplit("</svg", 1)[0]}</g>')
    parts.append('<rect x="900" y="500" width="260" height="260" fill="#B3261E"/>')
    parts.append(f'<g transform="translate(940 540) scale(2.6)">{mark_white().split(">", 1)[1].rsplit("</svg", 1)[0]}</g>')
    return svg(1500, 900, "".join(parts))


def main():
    # Vektor
    write("brand/mark.svg", mark())
    write("brand/mark-white.svg", mark_white())
    write("brand/mark-mono.svg", mark_mono())
    write("brand/logo-horizontal.svg", horizontal(BLAU))
    write("brand/logo-horizontal-white.svg", horizontal("#fff", white=True))
    write("brand/logo-stacked.svg", stacked(BLAU))
    write("brand/logo-stacked-white.svg", stacked("#fff", white=True))
    write("brand/wordmark.svg", wordmark(BLAU))
    write("brand/wordmark-white.svg", wordmark("#fff"))
    write("brand/social-preview.svg", social())

    # App (Oberfläche): Marke auf hellen Flächen bzw. weiß auf Farbflächen
    write("static/img/app-icon.svg", mark())
    write("static/img/app-icon-light.svg", mark_white())
    write("static/favicon.svg", mark(small=True))

    # Pixel
    png(social(), "brand/social-preview.png", 1280, 640)
    png(social(), "brand/og-image.png", 1200, 600)
    for s in (16, 32, 48):
        png(mark(small=True), f"brand/png/favicon-{s}.png", s)
    png(app_tile(), "static/apple-touch-icon.png", 180)
    png(app_tile(), "static/icon-192.png", 192)
    png(app_tile(), "static/icon-512.png", 512)
    png(app_tile(inset=0.14), "static/icon-maskable-512.png", 512)
    hz = horizontal(BLAU)
    import re
    vw = float(re.search(r'viewBox="0 0 ([\d.]+) 64"', hz).group(1))
    png(hz, "brand/png/logo-horizontal.png", 1600, int(1600 * 64 / vw))
    # favicon.ico (16/32/48)
    imgs = [Image.open(os.path.join(OUT, f"brand/png/favicon-{s}.png")).convert("RGBA") for s in (16, 32, 48)]
    imgs[2].save(os.path.join(OUT, "static/favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)], append_images=imgs[:2])


if __name__ == "__main__":
    main()
