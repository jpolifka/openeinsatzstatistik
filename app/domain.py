# -*- coding: utf-8 -*-
"""
Fachkonstanten der FF Rheinbrohl – einzige Quelle für Backend und Oberfläche.

Die Oberfläche bekommt diese Werte über /api/config (siehe client_config) und führt
keine eigenen Kopien.
"""
import datetime as dt

# Funkrufnamen der eigenen Fahrzeuge in der Reihenfolge der Einsatzübersicht
VEHICLES = ("02/45", "02/24", "02/71", "02/19", "01/10")
# Ersatzfahrzeuge, die bei Werkstattaufenthalt im Block eines anderen geführt werden
SUBSTITUTES = {"01/23": "02/45"}
# Fahrzeuge, die in der Gesamtstärke des Bedarfsplans fehlen (Excel-Spalte AU)
EXCLUDED_FROM_PLAN_CREW = {"01/10"}

# Kennungen im BKS-Bericht
UNIT_PREFIX = "FL NR#.BHÖ "              # Fahrzeuge der Verbandsgemeinde Bad Hönningen
OWN_VEHICLE_PREFIX = UNIT_PREFIX + "02/"  # Fahrzeuge des Löschzugs Rheinbrohl
CONTROL_CENTER = "FL NR#.LIN"             # Feuerwehreinsatzzentrale (FEZ)

# Einsatzarten: erster Buchstabe des Stichworts
CATEGORIES = (("H", "Hilfeleistung"), ("B", "Brand"), ("W", "Wasser"), ("G", "Gefahrstoff"), ("S", "Sonderlage"))
ALARM_LEVELS = (1, 2, 3, 4)               # Ziffer im Stichwort
# Gesondert gezählte Stichwort-Stufen
FIRE_ALARM_SYSTEM = ("B2", "07")          # Brandmeldeanlage
FIRE_WATCH = ("S1", "00")                 # Brandsicherheitswache

# Orte mit dem Namensanfang, über den das Einsatzgebiet zugeordnet wird
PLACES = (("Rheinbrohl", "rhein"), ("Arienheller", "arienh"), ("Hammerstein", "hammer"),
          ("Ariendorf", "ariend"), ("Bad Hönningen", "bad hönn"), ("Leutesdorf", "leutes"))
PLACE_NAMES = tuple(name for name, _ in PLACES)
OTHER_AREA = "sonstige"
# Ausrückebereich laut Feuerwehrbedarfsplan Pos. 8.4
PLAN_PLACES = ("Rheinbrohl", "Hammerstein", "Arienheller")
PLAN_MIN_LEVEL = 2                        # Bedarfsplan ab Alarmstufe 2

# Zeitgrenzen des Bedarfsplans in Minuten
RESPONSE_LIMITS = (8, 10)
DEFAULT_LIMIT = 8
SECOND_LIMIT = 15                         # Stärke nach 15 Minuten
# Tag = Einsatzbeginn zwischen 06:00 und 18:00 Uhr (Excel-Spalte D)
DAY_START_HOUR, DAY_END_HOUR = 6, 18


def category_of(keyword):
    """Einsatzart (Buchstabe) aus dem Stichwort, z. B. 'H2' -> 'H'."""
    return (keyword or "")[:1]


def alarm_level(keyword):
    """Alarmstufe aus dem Stichwort, z. B. 'H2' -> 2; None, wenn keine Ziffer folgt."""
    digit = (keyword or "")[1:2]
    return int(digit) if digit.isdigit() else None


def is_fire_watch(keyword, subcode):
    return (keyword, subcode) == FIRE_WATCH


def is_fire_alarm_system(keyword, subcode):
    return (keyword, subcode) == FIRE_ALARM_SYSTEM


def is_daytime(t: dt.time):
    """Wie Excel =UND(E>0,25;E<0,75): die Grenzen selbst zählen zur Nacht."""
    start, end = dt.time(DAY_START_HOUR), dt.time(DAY_END_HOUR)
    return start < t < end


def area_of(place):
    """Einsatzgebiet anhand des Anfangs des Ortsnamens."""
    text = (place or "").lower()
    return next((name for name, prefix in PLACES if text.startswith(prefix)), OTHER_AREA)


def is_plan_relevant(incident):
    """Einsatz zählt für den Bedarfsplan: ab Alarmstufe 2 im eigenen Ausrückebereich."""
    level = alarm_level(incident["keyword"])
    return level in ALARM_LEVELS and level >= PLAN_MIN_LEVEL and incident["place"] in PLAN_PLACES


def substitute_label(vehicle_name, call_sign):
    """Kurzname eines Ersatzfahrzeugs im Block (z. B. '01/23-01'); None, wenn das Stammfahrzeug fuhr."""
    if not vehicle_name or call_sign in vehicle_name:
        return None
    return vehicle_name.replace(UNIT_PREFIX, "")


def client_config():
    """Fachkonstanten für die Oberfläche."""
    return {
        "vehicles": list(VEHICLES),
        "categories": [{"code": code, "name": name} for code, name in CATEGORIES],
        "places": list(PLACE_NAMES),
        "plan_places": list(PLAN_PLACES),
        "plan_min_level": PLAN_MIN_LEVEL,
        "plan_excluded_vehicles": sorted(EXCLUDED_FROM_PLAN_CREW),
        "limits": list(RESPONSE_LIMITS),
        "default_limit": DEFAULT_LIMIT,
        "second_limit": SECOND_LIMIT,
        "day_hours": [DAY_START_HOUR, DAY_END_HOUR],
        "fire_alarm_system": ".".join(FIRE_ALARM_SYSTEM),
        "fire_watch": ".".join(FIRE_WATCH),
    }
