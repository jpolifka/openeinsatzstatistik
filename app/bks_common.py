"""Formatunabhängige BKS-Kennungen, Stichworte und Funkrufnamen."""
import functools
import re

KINDS = {"Stammdatensatz": "master", "Hauptbericht": "main", "Nebenbericht": "secondary"}
# Ortsteil/Kennung höchstens 30 Zeichen: ohne Grenze wächst der Aufwand auf langen Zeilen quadratisch
PERSON_VEHICLE = re.compile(r"(?:[A-Z]{2} )?[A-Z][A-Z0-9#.ÄÖÜ]{0,29} \d\d/\d\d-\d\d")
SHORT_CALL_SIGN = re.compile(r"(\d\d/\d\d)-\d\d$")

@functools.lru_cache(maxsize=32)
def _call_sign_pattern(unit_prefix):
    """Funkrufname eines Fahrzeugs der Einheit, z. B. "FL NR#.ABC 02/45-01" -> 02/45."""
    return re.compile("^" + re.escape(unit_prefix) + r"(\d\d/\d\d)-\d\d")



def _parse_keyword(text, report):
    m = re.match(r"([A-Z])(\d)\.(\d\d)", text)
    if m:
        return m.group(1) + m.group(2), m.group(3)
    if "sicherheitswache" in text.lower():
        return "S1", "00"
    report["warnings"].append(f"Stichwort '{text}' nicht erkannt")
    return text, ""


def parse_number(text):
    """Laufende Nr. aus der Einsatzbericht-Nr. "34/26", auch mit Kürzel davor wie "B67/2026" oder "FEZ 36/2026"."""
    m = re.match(r"[A-Za-zÄÖÜäöü]*\s*(\d+)\s*/\s*(\d+)", text)
    return int(m.group(1)) if m else None


def clean_alarm_system(text):
    """Nummer der Gefahrenmeldeanlage; „0“ und „-“ heißen: keine angegeben."""
    text = (text or "").strip()
    return None if text in ("", "0", "-") else text


TACTICS = ("Innenangriff", "Außenangriff")


def clean_tactic(text):
    """Einsatztaktik wie im Bericht („Innenangriff“, „Außenangriff“); anderes bleibt unverändert, leer -> None."""
    text = (text or "").strip()
    return next((t for t in TACTICS if t.lower() == text.lower()), text) or None
