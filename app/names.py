# -*- coding: utf-8 -*-
"""Personennamen vergleichen: Schreibweisen aus BKS-Bericht und Einsatzübersicht zusammenführen."""
import difflib
import re
import unicodedata


def normalize(text):
    """Kleinbuchstaben ohne Akzente, Leer- und Satzzeichen; ß -> ss."""
    text = unicodedata.normalize("NFKD", (text or "").lower().replace("ß", "ss"))
    return "".join(c for c in text if c.isalnum())


def short_name(first_name, last_name):
    """Schreibweise der Spalte Einheitsführung: 'M. Mustermann' (bei Ch… zwei Buchstaben)."""
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


def matches_leader(text, last_name, first_name):
    """Passt eine Einheitsführung-Angabe zur Person? Erkannt werden u. a. 'M. Muster', 'Ch. Muster', 'Muster, M.',
    'Max Muster', 'Muster Max' und nur 'Muster'; bei Doppelnamen reicht ein Namensteil."""
    words = [w for w in (normalize(t) for t in re.split(r"[\s,]+", text or "")) if w]
    first = normalize(first_name)
    last_names = {normalize(last_name)} | {normalize(part) for part in re.split(r"[-\s]+", last_name or "")
                                           if len(normalize(part)) >= 3}
    last_names.discard("")
    for i in range(len(words)):
        for j in range(i + 1, len(words) + 1):
            if "".join(words[i:j]) in last_names:
                rest = "".join(words[:i] + words[j:])  # Vorname oder Initiale, falls angegeben
                if not rest or not first or first.startswith(rest):
                    return True
    return False


def leader_spelling(spellings, last_name, first_name):
    """Einheitsführung-Schreibweise einer Person: die bisher am häufigsten für sie verwendete, sonst 'V. Nachname'.

    spellings: {schreibweise: anzahl} aus den vorhandenen Einsätzen.
    """
    used = [(count, text) for text, count in spellings.items() if matches_leader(text, last_name, first_name)]
    if used:
        return max(used)[1]
    return short_name(first_name, last_name) if first_name else last_name


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
        # 1. Nachname exakt (auch vertauscht); der Vorname muss passen (Initiale, Anfang oder ähnlich),
        #    sonst ist es ein Verwandter mit gleichem Nachnamen bzw. jemand, dessen Vorname ein Nachname ist
        exact = set()
        for last, first in ((last_name, first_name), (first_name, last_name)):
            last, first = normalize(last), normalize(first)
            candidates = [r for r in self.readings if r[1] == last]
            exact |= {key for key, _, _ in candidates}
            fitting = [r for r in candidates if _first_names_fit(r[2], first)]
            if fitting:
                return max(fitting, key=lambda r: (_prefix_match(r[2], first), _similarity(r[2], first)))[0]
        # 2. Tippfehler im Nachnamen: höchstens ein Buchstabe (Fehler, Auslassung, Zusatz, Dreher) Unterschied.
        #    Kein Treffer bei längeren Abweichungen: 'Röttgen' ist nicht 'Rott'.
        best = None
        for last, first in ((last_name, first_name), (first_name, last_name)):
            last, first = normalize(last), normalize(first)
            if len(last) < 4:
                continue
            for key, known_last, known_first in self.readings:
                if key in exact or len(known_last) < 4 or not _first_names_fit(known_first, first):
                    continue
                if _edit_distance(known_last, last) <= 1:
                    score = (_prefix_match(known_first, first), _similarity(known_first, first))
                    if best is None or score > best[0]:
                        best = (score, key)
        return best[1] if best else None


def _edit_distance(a, b):
    """Anzahl Einzelbuchstaben-Änderungen (Ersetzen, Einfügen, Löschen, Vertauschen benachbarter Buchstaben)."""
    rows = [list(range(len(b) + 1))]
    for i, ca in enumerate(a, 1):
        row = [i]
        for j, cb in enumerate(b, 1):
            cost = min(rows[-1][j] + 1, row[j - 1] + 1, rows[-1][j - 1] + (ca != cb))
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cost = min(cost, rows[-2][j - 2] + 1)
            row.append(cost)
        rows.append(row)
    return rows[-1][-1]


def _first_names_fit(known, given):
    """Vornamen passen: einer fehlt, einer ist Anfang des anderen (Initiale, Kurzform) oder kleiner Tippfehler."""
    return not known or not given or _prefix_match(known, given) or _similarity(known, given) >= 0.7
