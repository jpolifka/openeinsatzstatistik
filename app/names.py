# -*- coding: utf-8 -*-
"""Personennamen vergleichen: Schreibweisen aus BKS-Bericht und Einsatzübersicht zusammenführen."""
import difflib
import unicodedata


def normalize(text):
    """Kleinbuchstaben ohne Akzente, Leer- und Satzzeichen; ß -> ss."""
    text = unicodedata.normalize("NFKD", (text or "").lower().replace("ß", "ss"))
    return "".join(c for c in text if c.isalnum())


def short_name(first_name, last_name):
    """Schreibweise der Spalte EHF: 'M. Mustermann' (bei Ch… zwei Buchstaben)."""
    initial = "Ch" if first_name.lower().startswith("ch") else first_name[:1]
    return f"{initial}. {last_name}"


def name_readings(text):
    """Mögliche Lesarten (nachname, vorname) eines Namens.

    'Nachname, Vorname' ist eindeutig. Ohne Komma sind 'Nachname Vorname' und
    'Vorname Nachname' möglich; die zweite Lesart steht am Ende.
    """
    text = " ".join(text.split())
    if "," in text:
        last, first = (t.strip() for t in text.split(",", 1))
        return [(last, first)]
    words = text.split()
    return [(words[0], " ".join(words[1:])), (words[-1], " ".join(words[:-1]))]


def split_name(text):
    """'Nachname, Vorname' oder 'Vorname Nachname' -> (nachname, vorname)."""
    return name_readings(text)[-1]


def _similarity(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def _prefix_match(a, b):
    return a.startswith(b) or b.startswith(a)


class NameMatcher:
    """Ordnet einen Namen einem Schlüssel zu (z. B. Kamerad-ID), tolerant gegenüber Schreibweisen."""

    def __init__(self, entries):
        """entries: [(schlüssel, 'Name wie in der Liste')]"""
        self.readings = [(key, normalize(last), normalize(first))
                         for key, text in entries for last, first in name_readings(text)]

    def match(self, last_name, first_name):
        # 1. Nachname exakt (auch vertauscht); bei mehreren Treffern entscheidet der Vorname
        for last, first in ((last_name, first_name), (first_name, last_name)):
            last, first = normalize(last), normalize(first)
            candidates = [r for r in self.readings if r[1] == last]
            if len({key for key, _, _ in candidates}) == 1:
                return candidates[0][0]
            if candidates:
                best = max(candidates, key=lambda r: (_prefix_match(r[2], first), _similarity(r[2], first)))
                if _prefix_match(best[2], first) or _similarity(best[2], first) >= 0.7:
                    return best[0]
        # 2. Ähnlichkeit des ganzen Namens (Tippfehler)
        full = normalize(last_name) + normalize(first_name)
        best = max(self.readings, key=lambda r: _similarity(r[1] + r[2], full))
        return best[0] if _similarity(best[1] + best[2], full) >= 0.85 else None
