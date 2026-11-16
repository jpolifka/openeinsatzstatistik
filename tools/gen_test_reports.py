# -*- coding: utf-8 -*-
"""
Erfundene Einsatzberichte (Excel-Export des BKS-Portals) für Tests der Importstrecke – für beliebige VG.

Aufruf (Docker, nichts wird lokal installiert):
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONUSERBASE=/tmp/pu -v "$PWD:/w" -w /w \
    python:3.14-slim sh -c "pip install -q --user openpyxl && python tools/gen_test_reports.py Martin MAR"

Argumente: Name der Verbandsgemeinde und Kennung (z. B. MAR, wie in „FW NR#.MAR 02“). Optional: --wehren (1–14,
Standard 4), --orte „A,B,C“ (Namen der Wehren; Standard: erfundene Orte, die erste Wehr heißt wie die VG),
--jahr, --ziel (Ordner), --seed.

Wehr N ist „Florian <VG> N“, Einheit „FW <Kreis>.<Kennung> 0N <Ort>“. Fahrzeuge, Personen, Orte und Einsätze sind
ausgedacht. Gleiche Argumente liefern dieselben Dateien. Wehrübergreifende Einsätze haben einen Stammdatensatz,
je Wehr einen Haupt- bzw. Nebenbericht und dieselbe Einsatznummer der Leitstelle. Bei weniger als vier Wehren
werden die Vorlagen zusammengelegt, bei mehr als vier verteilt. Neben den Berichten entsteht `_Einrichtung.txt`
mit den Angaben, die man für Wehren und Fahrzeuge in der App braucht.
"""
import argparse
import datetime as dt
import io
import random
import re
import sys
import zipfile
import zlib
from pathlib import Path

import openpyxl

FIRST_NAMES = ("Anna", "Ben", "Clara", "David", "Emma", "Felix", "Greta", "Hans", "Ida", "Jonas", "Klara", "Leon",
               "Mia", "Nico", "Olga", "Paul", "Rita", "Sven", "Tina", "Uwe")
LAST_NAMES = ("Fiktiv", "Beispiel", "Muster", "Probe", "Demo", "Sample", "Dummy", "Platzhalter", "Erfunden", "Test")
DEFAULT_PLACES = ("Oberbach", "Niederhausen", "Bergheim", "Waldstein", "Seeblick", "Auenhof", "Steinfeld", "Rosenthal",
                  "Hohenfels", "Lindenau", "Mühlbach", "Neudorf", "Kirchwald")
MAX_WEHREN = 14
# Kreiskürzel in den Einheiten und Funkrufnamen; die Berichtsleser (pdf_report, xlsx_report) kennen nur NR#
COUNTY = "NR#"
# Fahrzeugausstattung: vier Profile, Wehr N nutzt Profil ((N - 1) % 4) + 1 (Kennzahl -> laufende Nr.)
PROFILES = {
    1: {"46": 1, "23": 1, "34": 1, "11": 1, "19": 1, "65": 1, "91": 1},
    2: {"45": 1, "41": 1, "53": 1, "56": 1, "18": 1, "19": 1},
    3: {"24": 1, "51": 1, "58": 1, "77": 1, "69": 1, "67": 1},
    4: {"42": 1, "44": 1, "71": 1, "16": 1, "10": 1},
}
LABELS = {"10": "Kommandowagen", "11": "ELW 1", "16": "Krad", "18": "ATV", "19": "MTF", "23": "TLF 3000",
          "24": "TLF 4000", "34": "DLK 23/12", "41": "TSF", "42": "TSF-W", "44": "MLF", "45": "LF 10",
          "46": "HLF 20", "51": "RW 1", "53": "GW-Mess", "56": "GW-A", "58": "GW-WR", "65": "WLF",
          "67": "SW 2000", "69": "GW-Tech", "71": "MZF 1", "77": "RTB 1", "91": "Wehrführer"}
STREETS = ("Musterweg", "Beispielstraße", "Probegasse", "Demoallee", "Hauptstraße", "Am Sportplatz", "Bahnhofstraße",
           "Mühlenweg", "Kirchstraße", "Im Wiesengrund", "Lindenallee", "Römerstraße")
ROLES = ("Maschinist", "Angriffstrupp", "Wassertrupp", "Schlauchtrupp", "Melder", "Gruppenführer")
LEADERS = ("Einheitsführer", "Gruppenführer", "Zugführer")


class Setup:
    """Eingaben eines Laufs und die daraus abgeleiteten Wehren."""

    def __init__(self, vg, code, count, places, county, year):
        self.vg, self.code, self.county, self.year = vg, code, county, year
        names = list(places) or [vg, *DEFAULT_PLACES]
        names += [n for n in DEFAULT_PLACES if n not in names]
        self.wehren = {}
        for i in range(1, count + 1):
            name = names[i - 1]
            self.wehren[i] = (name, (name, f"{name}-Nord", f"{name}-Süd"), dict(PROFILES[(i - 1) % 4 + 1]))

    def sign(self, wehr, code, number):
        return f"FL {self.county}.{self.code} {wehr:02d}/{code}-{number:02d}"

    def unit(self, wehr):
        return f"FW {self.county}.{self.code} {wehr:02d} {self.wehren[wehr][0]}"

    def target(self, rng, template_wehr, shift):
        """Wehr dieses Laufs für die Wehr der Vorlage (1–4)."""
        n = len(self.wehren)
        return template_wehr + shift if n >= 4 else (template_wehr - 1) % n + 1

    def crews(self, rng, crews_by_wehr, place_wehr):
        """Vorlage auf die vorhandenen Wehren abbilden: (Wehr der Einsatzstelle, {Wehr: [Kennzahlen]})."""
        n = len(self.wehren)
        shift = 4 * rng.randrange(0, (n - 4) // 4 + 1) if n >= 4 else 0
        mapped = {}
        for wehr, codes in crews_by_wehr.items():
            target = self.target(rng, wehr, shift)
            fleet = self.wehren[target][2]
            keep = [c for c in codes if c in fleet and c not in mapped.get(target, [])] or \
                ([] if target in mapped else [next(iter(fleet))])
            mapped.setdefault(target, []).extend(keep)
        return self.target(rng, place_wehr, shift), {w: c for w, c in mapped.items() if c}

    def instructions(self):
        lines = [f"Verbandsgemeinde {self.vg} (Kennung {self.code}, Kreis {self.county})", ""]
        for number, (name, _places, fleet) in self.wehren.items():
            lines += [f"Wehr {number}: Florian {self.vg} {number} – {name}",
                      f"  Einheit (unit_marker): FW {self.county}.{self.code} {number:02d}",
                      f"  Präfix der Fahrzeugnamen (unit_prefix): FL {self.county}.{self.code} ",
                      f"  Eigener Block (own_prefix): {number:02d}/", "  Fahrzeuge:"]
            lines += [f"    {self.sign(number, c, nr)}  ({LABELS.get(c, c)})" for c, nr in fleet.items()]
            lines.append("")
        return "\n".join(lines)


def pool(rng, count):
    """Je Wehr 14 erfundene Personen; Namen sind über alle Wehren verschieden."""
    names = [(last, first) for last in LAST_NAMES for first in FIRST_NAMES]
    rng.shuffle(names)
    return {w: names[(w - 1) * 14:w * 14] for w in range(1, count + 1)}


# Einsätze: (Beginn, Stichwort, Meldebild, Wehr der Einsatzstelle, Objekt, Dauer min, {Wehr: [Kennzahlen]}, Extras)
# Die Wehr mit der ersten Alarmierung (erste in `crews`) schreibt den Hauptbericht, die anderen Nebenberichte.
D = dt.datetime
INCIDENTS = [
    (D(2026, 1, 9, 7, 42), "H1.07", "Baum auf Fahrbahn", 1, "", 38, {1: ["46"]}, {}),
    (D(2026, 1, 17, 23, 15), "B2.07", "BMA Seniorenresidenz", 2, "Seniorenresidenz Sonnenhof", 31,
     {2: ["45", "41"]}, {"bma": "4711", "abort": "Fehlalarm, technischer Defekt Melder", "deployed": 0}),
    (D(2026, 2, 3, 18, 20), "H1.09", "Keller unter Wasser", 3, "", 95, {3: ["24", "51", "67"]}, {}),
    (D(2026, 2, 14, 3, 5), "B2.04", "Kaminbrand", 4, "", 62, {4: ["42", "44", "71"]},
     {"tactic": "Außenangriff", "out": 40}),
    (D(2026, 2, 22, 12, 30), "H2.01", "Türöffnung hilflose Person", 1, "", 44, {1: ["46", "91"]}, {"rescued": ("sonstiges", 1)}),
    (D(2026, 3, 27, 9, 48), "B1.03", "PKW-Brand", 3, "", 52, {3: ["24"]}, {"tactic": "Außenangriff", "out": 25}),
    (D(2026, 4, 5, 14, 0), "B2.07", "BMA Gymnasium Martin", 1, "Gymnasium Martin", 24,
     {1: ["46", "34", "11"]}, {"bma": "2088", "abort": "Blinder Alarm, kein Ereignis", "deployed": 0}),
    (D(2026, 4, 18, 21, 34), "B1.02", "Wiesenbrand", 2, "", 58, {2: ["45", "41", "18"]},
     {"tactic": "Außenangriff", "out": 35}),
    (D(2026, 5, 1, 15, 20), "H1.03", "Wespennest an Kindergarten", 4, "Kita Regenbogen", 28, {4: ["44"]}, {}),
    (D(2026, 5, 23, 20, 0), "S1.00", "Brandsicherheitswache Open-Air", 3, "Festplatz Flussau", 310,
     {3: ["24", "69"]}, {"watch": True}),
    (D(2026, 6, 12, 22, 10), "G1.01", "Ölspur nach Unwetter", 1, "", 66, {1: ["46", "65"]}, {}),
    (D(2026, 7, 2, 17, 45), "H1.06", "Person im Aufzug", 2, "Wohnanlage Am Kirchberg", 41, {2: ["45"]},
     {"rescued": ("sonstiges", 2)}),
    (D(2026, 8, 9, 11, 11), "B1.05", "Rauchentwicklung im Freien", 4, "", 27, {4: ["42", "16"]},
     {"abort": "Nicht erforderlich, Gartenabfälle", "deployed": 1}),
    (D(2026, 9, 14, 5, 40), "H1.05", "Pferd in Graben", 3, "Reiterhof Weidenbruch", 118, {3: ["24", "51"]},
     {"animals": 1}),
    (D(2026, 10, 3, 13, 5), "B2.06", "Rauchwarnmelder piept", 1, "", 21, {1: ["46"]}, {}),
    (D(2026, 10, 26, 19, 30), "H1.02", "Absicherung Gefahrenstelle", 2, "", 49, {2: ["41", "53"]}, {}),
    (D(2026, 11, 8, 8, 15), "B2.01", "Rauchentwicklung aus Gebäude", 4, "", 47, {4: ["42", "44", "71"]},
     {"tactic": "Innenangriff", "agt": True}),
    # wehrübergreifend
    (D(2026, 2, 28, 1, 30), "B3.01", "Scheunenbrand", 3, "Landwirtschaft Weidenbruch", 410,
     {3: ["24", "51", "67"], 2: ["45", "41", "56"], 1: ["34", "11", "46"], 4: ["44", "71"]},
     {"tactic": "Innenangriff", "agt": True, "out": 300, "controlled": 170, "watch_hours": 14, "injured_ff": 1,
      "master": True, "fez": True, "foreign": "34"}),
    (D(2026, 4, 24, 17, 25), "H2.03", "Verkehrsunfall, Person eingeklemmt", 2, "B 999 Höhe Kreuzmühle", 96,
     {2: ["45", "41", "53"], 3: ["51", "24"]}, {"rescued": ("Schere/Spreizer/Heber", 1), "injured": 2}),
    (D(2026, 6, 20, 14, 40), "B2.08", "Wohnungsbrand, Person am Fenster", 1, "Mehrfamilienhaus Martin-Süd", 118,
     {1: ["46", "34", "11", "19"], 2: ["45", "19"]},
     {"tactic": "Innenangriff", "agt": True, "rescued": ("Hubrettungsfahrzeug", 1), "injured": 1, "out": 75,
      "controlled": 45}),
    (D(2026, 7, 19, 15, 55), "B2.02", "Waldbrand", 4, "Hochwald", 380,
     {4: ["42", "44", "71", "16"], 2: ["45", "41", "18"], 3: ["24", "69"]},
     {"tactic": "Außenangriff", "out": 290, "controlled": 160, "watch_hours": 20, "master": True}),
    (D(2026, 8, 30, 2, 15), "W2.01", "Person im Wasser", 3, "Flussufer Flussau", 135,
     {3: ["77", "58", "24"], 4: ["44", "71"]}, {"rescued": ("Boot/Eisschlitten", 1)}),
    (D(2026, 9, 26, 10, 5), "H1.09", "Starkregen, Straßen überflutet", 1, "", 205,
     {1: ["46", "23", "65"], 3: ["24", "67"], 4: ["44", "42"]}, {}),
    (D(2026, 11, 11, 21, 50), "B3.03", "Brand Tischlerei", 2, "Tischlerei Beispiel GmbH", 255,
     {2: ["45", "41", "56"], 1: ["46", "34", "11", "23"], 4: ["44"]},
     {"tactic": "Innenangriff", "agt": True, "out": 200, "controlled": 120, "watch_hours": 9, "master": True,
      "injured_ff": 1}),
]

HEADER = ("ID", "Datensatz", "Feuerwehrhaus", "Name", "Einsatznummer Leitstelle", "Einsatzbericht-Nr.",
          "Haupt-/Nebenbericht", "Einsatzstichwort", "Meldebild", "Einsatzstelle - Ort", "Einsatzstelle - Ortsteil",
          "Einsatzstelle - Straße", "Einsatzstelle - Objekt", "Zeitpunkt der Alarmierung der ersten Einheit",
          "Einsatzleiter", "Einsatzabbruch", "Nummer der Gefahrenmeldeanlage", "Einatztaktik",
          "Brand unter Kontrolle", "Feuer aus", "Brandwache gestellt bis", "Menschenrettung über sonstiges",
          "Menschenrettung über Hubrettungsfahrzeug", "Menschenrettung mit Schere/Spreizer/Heber",
          "Menschenrettung über Boot/Eisschlitten", "Rettung von Großvieh", "Verletzte Feuerwehrangehörige",
          "Verletzte andere Personen")
RESCUE_COLUMN = {"sonstiges": "Menschenrettung über sonstiges",
                 "Hubrettungsfahrzeug": "Menschenrettung über Hubrettungsfahrzeug",
                 "Schere/Spreizer/Heber": "Menschenrettung mit Schere/Spreizer/Heber",
                 "Boot/Eisschlitten": "Menschenrettung über Boot/Eisschlitten"}
VEHICLE_HEADER = ("Fahrzeuge", "Einheitsführer", "Unterfuehrer", "Mannschaft", "Gesamt", "AGT", "Alarmiert",
                  "Ausrücken", "Eintreffen an E-Stelle", "Eingesetzt", "Rückkehr von E-Stelle", "Einsatzende",
                  "Gesamtzeit")
PEOPLE_HEADER = ("Name", "Vorname", "Fahrzeug", "Von", "Bis", "Funktion", "AGT", "Min (AGT)", "Bemerkung", None)


def stamp(t, seconds=True):
    return t.strftime("%d.%m.%y %H:%M:%S" if seconds else "%d.%m.%y %H:%M")


def vehicle_rows(rng, setup, wehr, codes, alarm, end, arrival_base, agt, deployed=1):
    """Fahrzeugzeilen einer Wehr; Rückgabe (Zeilen, früheste Alarmierung)."""
    rows, crews = [], []
    for i, code in enumerate(codes):
        alerted = alarm + dt.timedelta(seconds=rng.randrange(0, 90) + i * rng.randrange(0, 40))
        departed = alerted + dt.timedelta(seconds=rng.randrange(150, 480))
        travel = dt.timedelta(minutes=arrival_base + rng.randrange(0, 5))
        arrived = departed + travel
        finished = max(end - dt.timedelta(minutes=rng.randrange(0, 15)), arrived + dt.timedelta(minutes=5))
        back = finished - dt.timedelta(minutes=rng.randrange(1, 6))
        chief, sub, crew = (1 if code in ("46", "45", "24", "34", "11", "91", "10") else 0), rng.randrange(0, 2), \
            rng.randrange(1, 6)
        if code in ("42", "44", "41", "16", "18", "71", "19", "65", "69", "56", "53", "77", "58", "91", "10"):
            crew = min(crew, 3)
        total = chief + sub + crew
        resp = rng.randrange(0, min(total, 4) + 1) if agt and code in ("46", "45", "24", "42", "44", "41") else 0
        rows.append((setup.sign(wehr, code, setup.wehren[wehr][2][code]), chief, sub, crew, total, resp, stamp(alerted),
                     stamp(departed), stamp(arrived), deployed, stamp(back), stamp(finished), None))
        crews.append((code, total, alerted, departed, finished, resp))
    return rows, crews


def people_rows(rng, setup, members, crews, wehr):
    """Anwesenheitsliste passend zur Stärke der Fahrzeuge; Werte wie im Export eine Spalte nach rechts versetzt."""
    free = list(members)
    rng.shuffle(free)
    rows, leader = [], None
    for code, total, alerted, _departed, finished, resp in crews:
        sign = setup.sign(wehr, code, setup.wehren[wehr][2][code])
        for k in range(total):
            if not free:
                break
            last, first = free.pop()
            role = LEADERS[0] if k == 0 and total > 2 else rng.choice(ROLES[:5])
            if role == LEADERS[0] and leader is None:
                leader = f"{first} {last}"
            on_agt = k < resp
            rows.append((last, first, 1, sign, stamp(alerted, False), stamp(finished, False), role,
                         "AGT" if on_agt else "nein", rng.randrange(12, 40) if on_agt else 0, None, None))
    return rows, leader or (f"{rows[0][1]} {rows[0][0]}" if rows else "")


def workbook(main, vehicles, people):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, header, rows in (("Einsatzbericht", HEADER, [main]),
                                ("Ausger. Fahrzeuge und Personen", VEHICLE_HEADER, vehicles),
                                ("Anw. Dienststellen", ("Verständigt", "Anwesend", "Dienststelle", "Name"), []),
                                ("Anwesenheitsliste", PEOPLE_HEADER, people)):
        ws = wb.create_sheet(title)
        ws.append(header)
        for row in rows:
            ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def main_row(values):
    return tuple(values.get(h) for h in HEADER)


def build(setup, target, seed):
    rng = random.Random(f"{seed}-{setup.vg}-{setup.code}")
    members = pool(rng, len(setup.wehren))
    counter = {w: 0 for w in setup.wehren}
    yy = setup.year % 100
    offset = zlib.crc32(setup.code.encode()) % 900 * 10000        # getrennte ID-Bereiche je VG
    bks_id, record_id, dispatch = 2010000 + offset, 2009000 + offset, int(f"1{yy}0040100") + offset
    county = setup.county.rstrip("#")
    files = []
    incidents = sorted(((i[0].replace(year=setup.year),) + i[1:] for i in INCIDENTS), key=lambda i: i[0])
    for start, kw, reported_as, place_wehr, obj, minutes, crews_by_wehr, extra in incidents:
        place_wehr, crews_by_wehr = setup.crews(rng, crews_by_wehr, place_wehr)
        record_id += 7
        dispatch += rng.randrange(3, 40)
        town, district = setup.wehren[place_wehr][1][0], rng.choice(setup.wehren[place_wehr][1])
        street = f"{rng.choice(STREETS)} {rng.randrange(1, 60)}" if not extra.get("bma") else f"{rng.choice(STREETS)} 1"
        end = start + dt.timedelta(minutes=minutes)
        slug = f"{start:%Y-%m-%d}_{kw.replace('.', '')}_{reported_as.split(',')[0].split()[0]}"
        common = {"Datensatz": str(record_id), "Einsatznummer Leitstelle": str(dispatch), "Einsatzstichwort": kw,
                  "Meldebild": reported_as, "Einsatzstelle - Ort": town, "Einsatzstelle - Ortsteil": f"{district} ({county})",
                  "Einsatzstelle - Straße": street, "Einsatzstelle - Objekt": obj or None,
                  "Zeitpunkt der Alarmierung der ersten Einheit": start.strftime("%d.%m.%Y %H:%M"),
                  "Einsatzabbruch": extra.get("abort"), "Nummer der Gefahrenmeldeanlage": extra.get("bma"),
                  "Einatztaktik": extra.get("tactic")}
        if "controlled" in extra:
            common["Brand unter Kontrolle"] = (start + dt.timedelta(minutes=extra["controlled"])).strftime("%d.%m.%Y %H:%M")
        if "out" in extra:
            common["Feuer aus"] = (start + dt.timedelta(minutes=extra["out"])).strftime("%d.%m.%Y %H:%M")
        if "watch_hours" in extra:
            common["Brandwache gestellt bis"] = (end + dt.timedelta(hours=extra["watch_hours"])).strftime("%d.%m.%Y %H:%M")
        if "rescued" in extra:
            common[RESCUE_COLUMN[extra["rescued"][0]]] = extra["rescued"][1]
        if "animals" in extra:
            common["Rettung von Großvieh"] = extra["animals"]
        if extra.get("injured_ff"):
            common["Verletzte Feuerwehrangehörige"] = extra["injured_ff"]
        if extra.get("injured"):
            common["Verletzte andere Personen"] = extra["injured"]

        if extra.get("master"):
            bks_id += 1
            master = {**common, "ID": str(record_id), "Datensatz": None, "Einsatzbericht-Nr.": None}
            files.append((f"{slug}_Stammdatensatz.xlsx", workbook(main_row(master), [], [])))
        first_alarm = start
        for index, (wehr, codes) in enumerate(crews_by_wehr.items()):
            bks_id += 1
            counter[wehr] += 1
            alarm = first_alarm + dt.timedelta(minutes=0 if index == 0 else rng.randrange(8, 35))
            # Fahrzeuge der anderen Wehr kommen später an, der Einsatz endet für alle etwa gleichzeitig
            arrival_base = 4 + (0 if wehr == place_wehr else 5)
            vehicles, crews = vehicle_rows(rng, setup, wehr, codes, alarm, end, arrival_base, extra.get("agt"),
                                           extra.get("deployed", 1))
            people, leader = people_rows(rng, setup, members[wehr], crews, wehr)
            if index == 0:                                   # Hauptbericht listet auch die Fahrzeuge der anderen
                for other, other_codes in list(crews_by_wehr.items())[1:]:
                    rows, _ = vehicle_rows(rng, setup, other, other_codes, alarm + dt.timedelta(minutes=12), end,
                                           arrival_base + 4, extra.get("agt"), 1)
                    vehicles += rows
                if extra.get("foreign"):                    # Überlandhilfe aus der Nachbar-VG
                    vehicles.append((f"FL {county}.NBV 01/{extra['foreign']}-01", 1, 0, 2, 3, 0, stamp(alarm + dt.timedelta(minutes=30)),
                                     stamp(alarm + dt.timedelta(minutes=37)), stamp(alarm + dt.timedelta(minutes=62)),
                                     1, stamp(end - dt.timedelta(minutes=20)), stamp(end - dt.timedelta(minutes=25)), None))
            row = {**common, "ID": str(bks_id), "Feuerwehrhaus": setup.unit(wehr), "Name": setup.unit(wehr),
                   "Einsatzbericht-Nr.": f"{counter[wehr]}/{yy}",
                   "Haupt-/Nebenbericht": "Hauptbericht (HB)" if index == 0 else "Nebenbericht (NB)",
                   "Einsatzleiter": leader}
            files.append((f"{slug}_Florian-{wehr}_{counter[wehr]:02d}-{yy}.xlsx",
                          workbook(main_row(row), vehicles, people)))
        if extra.get("fez"):                                 # Bericht der Leitstelle/FEZ: wird beim Import übersprungen
            bks_id += 1
            row = {**common, "ID": str(bks_id), "Feuerwehrhaus": f"FW {setup.county}.{setup.code} 00 FEZ VG",
                   "Name": f"FW {setup.county}.{setup.code} 00 FEZ VG", "Einsatzbericht-Nr.": f"FEZ 4/{setup.year}",
                   "Haupt-/Nebenbericht": "Nebenbericht (NB)", "Einsatzleiter": None}
            files.append((f"{slug}_FEZ.xlsx", workbook(main_row(row), [], [])))
    target.mkdir(parents=True, exist_ok=True)
    (target / "_Einrichtung.txt").write_text(setup.instructions(), encoding="utf-8")
    for name, data in files:
        (target / name).write_bytes(data)
    with zipfile.ZipFile(target / "alle-Berichte.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files:
            archive.writestr(name, data)
    return files


def main():
    ap = argparse.ArgumentParser(description="Erfundene BKS-Einsatzberichte (xlsx) für eine Verbandsgemeinde erzeugen.")
    ap.add_argument("vg", help="Name der Verbandsgemeinde, z. B. Martin")
    ap.add_argument("kennung", help="Kennung wie in „FW NR#.MAR 02“, z. B. MAR")
    ap.add_argument("--wehren", type=int, default=4, help=f"Anzahl der Wehren (1–{MAX_WEHREN}, Standard 4)")
    ap.add_argument("--orte", default="", help="Namen der Wehren, kommagetrennt (Standard: erfundene Orte)")
    ap.add_argument("--jahr", type=int, default=2026)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--ziel", help="Ausgabeordner (Standard: Einsatzberichte/Test-<VG>)")
    args = ap.parse_args()
    code = args.kennung.upper()
    if not re.fullmatch(r"[A-Z0-9ÄÖÜ]{2,6}", code):
        ap.error("Die Kennung besteht aus 2 bis 6 Großbuchstaben oder Ziffern (z. B. MAR).")
    if not 1 <= args.wehren <= MAX_WEHREN:
        ap.error(f"Die Zahl der Wehren liegt zwischen 1 und {MAX_WEHREN}.")
    if not 2000 <= args.jahr <= 2100:
        ap.error("Das Jahr liegt zwischen 2000 und 2100.")
    places = [p.strip() for p in args.orte.split(",") if p.strip()]
    if len(places) > args.wehren:
        ap.error("Es sind mehr Orte als Wehren angegeben.")
    setup = Setup(args.vg.strip(), code, args.wehren, places, COUNTY, args.jahr)
    target = Path(args.ziel or "Einsatzberichte/Test-" + re.sub(r"[^\w-]+", "-", args.vg.strip()))
    files = build(setup, target, args.seed)
    print(f"{len(files)} Dateien in {target} (Einrichtungsangaben: {target / '_Einrichtung.txt'})")


if __name__ == "__main__":
    main()
