# -*- coding: utf-8 -*-
"""
Farben und Logos einer Wehr.

Eine Wehr wählt nur ihre Hauptfarbe (brand) und optional eine dunkle Variante (brand_dark).
palette() leitet daraus alle Farb-Tokens der Oberfläche ab (Namen wie in static/app.css) und
sorgt dabei selbst für lesbare Kontraste; check() meldet, wenn die gewählten Farben für weiße
Schrift zu hell sind. Ohne eigene Farben gelten die Werte aus app.css (das bisherige Rot).
"""
import re

HEX = re.compile(r"#[0-9A-Fa-f]{6}")
WHITE, BLACK = (255, 255, 255), (0, 0, 0)
MIN_TEXT_CONTRAST = 4.5        # weiße Schrift auf Kopfzeile, Knöpfen, Tabellenköpfen (WCAG AA)
MIN_CHART_CONTRAST = 3.0       # Diagrammfarben gegen den weißen Hintergrund

# Neutrales Farbschema: Anmeldung, Gesamtansicht einer VG, Wehren ohne Zuordnung. Leer, weil dort keine Farben
# überschrieben werden; die Standardwerte in app.css entsprechen palette({"brand": "#7C2734"}) mit Sand (#E9D6CE) für
# die Flächentöne (tests/test_theme.py prüft die Übereinstimmung).
NEUTRAL = {}   # = die Standardfarben aus static/app.css (Bordeaux mit Sand, docs/marke.md)

# Logos: Name -> Bezeichnung; erlaubte Bildformate (am Inhalt erkannt, kein SVG wegen eingebetteter Skripte)
ASSETS = {"logo-light": "Logo hell (für die farbige Kopfzeile)", "logo-dark": "Logo dunkel (Fußzeile)",
          "icon": "Symbol (Browser-Tab)"}
MAX_ASSET_BYTES = 512 * 1024

# Schriftdateien einer Wehr (Tabelle asset, wie die Logos): normal und fett; ohne Datei gilt die Systemschrift
FONTS = {"font": "Schrift (normal)", "font-bold": "Schrift (fett)"}
FONT_WEIGHTS = {"font": 400, "font-bold": 700}
MAX_FONT_BYTES = 1024 * 1024
FONT_FAMILY = "Wehrschrift"
FONT_FORMATS = {"font/woff2": "woff2", "font/woff": "woff", "font/ttf": "truetype", "font/otf": "opentype"}
# Systemschriften wie im BKS-Portal des Landes; muss zu --font in static/app.css passen
SYSTEM_FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'


def _rgb(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def _hex(rgb):
    return "#" + "".join(f"{round(c):02X}" for c in rgb)


def _mix(color, other, share):
    """share Anteil von other in color (sRGB), auf ganze Werte gerundet – geprüft wird, was ausgegeben wird."""
    return tuple(round(c + (o - c) * share) for c, o in zip(color, other))


def _luminance(rgb):
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    """Kontrastverhältnis nach WCAG zwischen zwei Farben (#RRGGBB oder RGB-Tupel)."""
    la, lb = (_luminance(_rgb(c) if isinstance(c, str) else c) for c in (a, b))
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _darken_until(color, minimum, against=WHITE):
    """Farbe so weit abdunkeln, bis sie gegen against den Mindestkontrast hat."""
    step = 0
    while contrast(color, against) < minimum and step < 20:
        color, step = _mix(color, BLACK, 0.08), step + 1
    return color


def normalize(colors):
    """{"brand": "#rrggbb", "brand_dark": "#rrggbb" | None} prüfen und vereinheitlichen; ValueError bei Unsinn."""
    result = {}
    for key in ("brand", "brand_dark"):
        value = (colors or {}).get(key)
        if value in (None, ""):
            continue
        if not isinstance(value, str) or not HEX.fullmatch(value):
            raise ValueError(f"Farbe „{value}“: bitte als #RRGGBB angeben.")
        result[key] = value.upper()
    if result and "brand" not in result:
        raise ValueError("Bitte zuerst die Hauptfarbe wählen.")
    return result


def check(colors):
    """Probleme der gewählten Farben als Texte (leer = in Ordnung)."""
    problems = []
    labels = {"brand": "Hauptfarbe", "brand_dark": "Dunkle Farbe"}
    for key, value in normalize(colors).items():
        ratio = contrast(value, WHITE)
        if ratio < MIN_TEXT_CONTRAST:
            problems.append(f"{labels[key]} {value} ist zu hell: weiße Schrift hat nur {ratio:.1f}:1 Kontrast "
                            f"(mindestens {MIN_TEXT_CONTRAST}:1). Bitte eine dunklere Farbe wählen.".replace(".", ",", 2))
    return problems


def palette(colors):
    """Alle Farb-Tokens der Oberfläche aus Haupt- und dunkler Farbe."""
    colors = normalize(colors)
    brand = _rgb(colors["brand"])
    dark = _rgb(colors["brand_dark"]) if "brand_dark" in colors else _darken_until(_mix(brand, BLACK, 0.45), 7)
    mid = _darken_until(_mix(brand, WHITE, 0.12), MIN_TEXT_CONTRAST)
    r, g, b = (round(c) for c in dark)
    deep = lambda share: ",".join(str(round(c)) for c in _mix(dark, BLACK, share))   # noqa: E731
    return {
        "--brand": _hex(brand),
        "--brand-dark": _hex(dark),
        "--brand-mid": _hex(mid),
        "--brand-accent": _hex(_darken_until(_mix(brand, WHITE, 0.3), MIN_CHART_CONTRAST)),   # Fokusring und Rahmen: mindestens 3:1
        "--brand-light": _hex(_mix(brand, WHITE, 0.85)),
        "--brand-pale": _hex(_mix(brand, WHITE, 0.93)),
        "--brand-gradient": _hex(_mix(brand, dark, 0.5)),
        "--brand-hover": _hex(_mix(brand, BLACK, 0.15)),
        "--brand-light-hover": _hex(_mix(brand, WHITE, 0.76)),
        "--brand-mid-hover": _hex(_mix(mid, BLACK, 0.1)),
        "--brand-shadow": f"rgba({','.join(str(round(c)) for c in brand)},.25)",
        "--shadow": f"0 1px 2px rgba({deep(0.58)},.06), 0 6px 20px rgba({r},{g},{b},.06)",
        "--dialog-shadow": f"0 30px 80px rgba({deep(0.5)},.35)",
        "--backdrop": f"rgba({deep(0.67)},.45)",
        "--track": _hex(_mix(brand, WHITE, 0.89)),
    }


def font_css(files):
    """@font-face und --font für die Schriftdateien einer Wehr; files = [(Name in FONTS, Adresse, MIME-Typ)]."""
    faces = ""
    for name, url, mime in files:
        if name in FONTS and mime in FONT_FORMATS:
            faces += (f'@font-face{{font-family:"{FONT_FAMILY}";font-style:normal;font-weight:{FONT_WEIGHTS[name]};'
                      f'font-display:swap;src:url("{url}") format("{FONT_FORMATS[mime]}")}}\n')
    if not faces:
        return ""
    return faces + f':root{{--font:"{FONT_FAMILY}",{SYSTEM_FONT};}}\n'


def css(colors, fonts=()):
    """Stylesheet, das die Tokens aus app.css überschreibt (Farben, Schrift der Wehr); leer ohne beides."""
    out = font_css(fonts)
    if normalize(colors):
        out += ":root{" + "".join(f"{name}:{value};" for name, value in palette(colors).items()) + "}\n"
    return out


def image_type(data):
    """Bildformat am Dateianfang -> MIME-Typ, sonst None (nur PNG, JPEG, WebP)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def font_type(data):
    """Schriftformat am Dateianfang -> MIME-Typ, sonst None (WOFF2, WOFF, TrueType, OpenType). Bei WOFF/WOFF2 muss die
    im Kopf angegebene Länge zur Datei passen (schützt vor abgeschnittenen oder untergeschobenen Dateien)."""
    head = data[:4]
    if head in (b"wOF2", b"wOFF"):
        if len(data) < 48 or int.from_bytes(data[8:12], "big") != len(data):
            return None
        return "font/woff2" if head == b"wOF2" else "font/woff"
    if len(data) >= 12 and head in (b"\x00\x01\x00\x00", b"true"):
        return "font/ttf"
    if len(data) >= 12 and head == b"OTTO":
        return "font/otf"
    return None
