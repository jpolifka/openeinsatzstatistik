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

# Stichwortkatalog (Alarm- und Ausrückeordnung) für die Suche im Feld Stichwort: (Stichwort.Stufe, Bezeichnung).
# Ohne Stufe = Grundstufe. Gestrichene Stichworte (B4.1, H4.01, S1.04, S1.08, S1.13) fehlen bewusst.
KEYWORD_CATALOG = (
    ("B1", "Grundstufe"), ("B1.01", "Müllbrand"), ("B1.02", "Flächenbrand klein"), ("B1.03", "Fahrzeugbrand klein"),
    ("B1.04", "Brandnachschau"), ("B1.05", "Rauchentwicklung im Freien"),
    ("B2", "Grundstufe"), ("B2.01", "Rauchentwicklung aus Gebäude"), ("B2.02", "Flächenbrand groß"),
    ("B2.03", "Fahrzeugbrand groß"), ("B2.04", "Kaminbrand"), ("B2.05", "Nebengebäude"),
    ("B2.06", "Rauchwarnmelder"), ("B2.07", "BMA"), ("B2.08", "Wohnungsbrand"),
    ("B2.09", "Wohnungsbrand mit Personenrettung"),
    ("B3", "Grundstufe"), ("B3.01", "Gebäudebrand"), ("B3.02", "Hotel, Event"), ("B3.03", "Industriebrand"),
    ("B3.04", "Explosion"), ("B3.05", "Fahrzeugbrand mit Gefahrgut"), ("B3.06", "Brand Zug"),
    ("B3.07", "Brand Straßenbahn"),
    ("B4", "Grundstufe"),
    ("H1", "Grundstufe"), ("H1.02", "Absicherung"), ("H1.03", "Insekten"), ("H1.04", "Tierbergung"),
    ("H1.05", "Tierrettung"), ("H1.06", "Person in Aufzug"), ("H1.07", "einfache Hilfeleistung"),
    ("H1.08", "Unterstützung Rettungsdienst"), ("H1.09", "Wassereinbruch"),
    ("H2", "Grundstufe"), ("H2.01", "Tür öffnen dringend"), ("H2.02", "Leichenbergung"), ("H2.03", "Verkehrsunfall"),
    ("H2.04", "Person in Zwangslage"), ("H2.05", "Person droht zu springen"), ("H2.06", "Einsturz klein"),
    ("H2.07", "größere Hilfeleistung"), ("H2.08", "Unterstützung Rettungsdienst HRF"),
    ("H2.09", "Unterstützung Rettungsdienst Gelände"), ("H2.10", "Person unter Zug"),
    ("H2.11", "Person unter Straßenbahn"),
    ("H3", "Grundstufe"), ("H3.01", "Verkehrsunfall groß"), ("H3.02", "Höhen-, Tiefenrettung"),
    ("H3.03", "Einsturz groß"), ("H3.04", "Verkehrsunfall Zug"), ("H3.05", "Verkehrsunfall Straßenbahn"),
    ("H4", "Grundstufe"),
    ("G1", "Grundstufe"), ("G1.01", "Ölspur"), ("G1.02", "ausl. Betriebsstoffe PKW < 50 l"),
    ("G1.03", "sonstige Kleinmengen < 10 l"), ("G1.04", "AEP-GS Alarmstufe 1"),
    ("G2", "Grundstufe"), ("G2.01", "ausl. Betriebsstoffe LKW > 50 l"), ("G2.02", "AEP-GS Alarmstufe 2"),
    ("G2.03", "Gasgeruch"),
    ("G3", "Grundstufe"), ("G3.01", "AEP-GS Alarmstufe 3"), ("G3.02", "Gefahrstoffaustritt"),
    ("G3.03", "Gasausströmung"), ("G3.04", "Gefahrstoffaustritt Schienenfahrzeug"),
    ("G4", "Grundstufe"), ("G4.01", "AEP-GS Alarmstufe 4"),
    ("W1", "Grundstufe"), ("W1.01", "Hochwasser"), ("W1.02", "Gewässerverunreinigung"),
    ("W2", "Grundstufe"), ("W2.01", "Wasser- / Eisrettung klein"), ("W2.02", "Taucheinsatz"),
    ("W2.03", "Bootsunfall"), ("W2.04", "Öl auf Gewässer"), ("W2.05", "Bootsbrand"),
    ("W3", "Grundstufe"), ("W3.01", "Schiffsbrand"), ("W3.02", "Schiffshavarie"),
    ("W3.03", "Wasser- / Eisrettung groß"),
    ("W4", "Grundstufe"),
    ("S1", "Grundstufe"), ("S1.00", "Brandsicherheitswache"), ("S1.01", "Einsatz nach Rücksprache"),
    ("S1.03", "Bombenfund"), ("S1.05", "Personensuche"), ("S1.06", "PSNV"), ("S1.07", "Stromausfall"),
    ("S1.09", "Erkundung"), ("S1.11", "Schwerlasttransport"), ("S1.14", "Hubschrauberlandung"),
    ("S1.15", "Zubringerdienst"), ("S1.16", "Kommunikationsausfall"), ("S1.17", "Sonstige Gefahrenmeldung"),
    ("S1.18", "D1-Störfallmeldung"),
    ("S2", "Grundstufe"), ("S2.01", "Flugzeugunfall klein"), ("S2.02", "Unwetter"), ("S2.03", "D2-Störfallmeldung"),
    ("S3", "Grundstufe"), ("S3.01", "D3-Störfallmeldung"),
    ("S4", "Grundstufe"), ("S4.01", "Flugzeugunfall groß"), ("S4.02", "AEP Kernkraftwerk"),
    ("S4.03", "Gefahrenlage polizeilicher Einsatz"), ("S4.04", "LebEL Extern St.1 B-Raum"),
    ("S4.05", "LebEL Extern St.2 Bereitschaft"), ("S4.06", "Überörtliche Hilfe größeren Umfanges"),
    ("S4.07", "D4-Störfallmeldung"),
    ("U1.01", "lose Objekte ohne Dringlichkeit"), ("U1.02", "abgebrochener Ast ohne Dringlichkeit"),
    ("U1.03", "Wasser in Gebäude klein"), ("U1.04", "umgestürzter Baum ohne Dringlichkeit"),
    ("U2.01", "übergetretener Bach"), ("U2.02", "Wasser in Gebäude"), ("U2.03", "lose Objekte mit Dringlichkeit"),
    ("U2.04", "abgebrochener Ast mit Dringlichkeit"), ("U2.05", "Wasser in Gebäude"),
    ("U2.06", "überflutete Fahrbahn"), ("U2.07", "umgestürzter Baum mit Dringlichkeit"),
    ("U2.08", "abgedecktes Dach"), ("U3.01", "Hangrutsch"),
)

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
        "keyword_catalog": [{"code": code, "name": name} for code, name in KEYWORD_CATALOG],
    }
