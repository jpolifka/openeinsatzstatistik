# -*- coding: utf-8 -*-
"""
Erfundene Einsatzberichte der VG Martin (Excel-Export des BKS-Portals) für Tests der Importstrecke.

Vier Wehren („Florian Martin 1“ bis „4“, Einheit FW NR#.MAR 01 … 04), Fahrzeuge, Personen, Orte und Einsätze
sind ausgedacht. Jeder Lauf liefert dieselben Dateien (fester Startwert). Wehrübergreifende Einsätze haben
einen Stammdatensatz, je Wehr einen Haupt- bzw. Nebenbericht und dieselbe Einsatznummer der Leitstelle.

Aufruf (Docker, nichts wird lokal installiert):
  docker run --rm -v "$PWD:/w" -w /w python:3.14-slim sh -c \
    "pip install -q openpyxl && python tools/gen_vg_martin_reports.py Einsatzberichte/Test-VG-Martin"
"""
import datetime as dt
import io
import random
import sys
import zipfile
from pathlib import Path

import openpyxl

SEED = 2026116
CODE = "MAR"
FIRST_NAMES = ("Anna", "Ben", "Clara", "David", "Emma", "Felix", "Greta", "Hans", "Ida", "Jonas", "Klara", "Leon",
               "Mia", "Nico", "Olga", "Paul", "Rita", "Sven", "Tina", "Uwe")
LAST_NAMES = ("Fiktiv", "Beispiel", "Muster", "Probe", "Demo", "Sample", "Dummy", "Platzhalter", "Erfunden", "Test")

# Wehr -> Name, Orte (Einsatzstellen), Fahrzeuge {Kennzahl: Nr.}, Bezeichnung nur zur Info
WEHREN = {
    1: ("Martin", ("Martin", "Martin-Süd", "Altstadt"),
        {"46": 1, "23": 1, "34": 1, "11": 1, "19": 1, "65": 1, "91": 1}),
    2: ("Oberbach", ("Oberbach", "Hasselhof", "Kreuzmühle"),
        {"45": 1, "41": 1, "53": 1, "56": 1, "18": 1, "19": 1}),
    3: ("Niederhausen", ("Niederhausen", "Flussau", "Weidenbruch"),
        {"24": 1, "51": 1, "58": 1, "77": 1, "69": 1, "67": 1}),
    4: ("Bergheim", ("Bergheim", "Hochwald", "Lindenhof"),
        {"42": 1, "44": 1, "71": 1, "16": 1, "10": 1}),
}
STREETS = ("Musterweg", "Beispielstraße", "Probegasse", "Demoallee", "Hauptstraße", "Am Sportplatz", "Bahnhofstraße",
           "Mühlenweg", "Kirchstraße", "Im Wiesengrund", "Lindenallee", "Römerstraße")
ROLES = ("Maschinist", "Angriffstrupp", "Wassertrupp", "Schlauchtrupp", "Melder", "Gruppenführer")
LEADERS = ("Einheitsführer", "Gruppenführer", "Zugführer")


def pool(rng, wehr):
    """14 erfundene Personen je Wehr (Namen sind je Wehr verschieden)."""
    names = [(last, first) for last in LAST_NAMES for first in FIRST_NAMES]
    rng.shuffle(names)
    return names[(wehr - 1) * 40:(wehr - 1) * 40 + 14]


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
      "master": True, "fez": True, "foreign": "FL NR#.LIN 01/34-01"}),
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


def call_sign(wehr, code, number):
    return f"FL NR#.{CODE} {wehr:02d}/{code}-{number:02d}"


def vehicle_rows(rng, wehr, codes, alarm, end, arrival_base, agt, deployed=1):
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
        rows.append((call_sign(wehr, code, WEHREN[wehr][2][code]), chief, sub, crew, total, resp, stamp(alerted),
                     stamp(departed), stamp(arrived), deployed, stamp(back), stamp(finished), None))
        crews.append((code, total, alerted, departed, finished, resp))
    return rows, crews


def people_rows(rng, members, crews, wehr):
    """Anwesenheitsliste passend zur Stärke der Fahrzeuge; Werte wie im Export eine Spalte nach rechts versetzt."""
    free = list(members)
    rng.shuffle(free)
    rows, leader = [], None
    for code, total, alerted, _departed, finished, resp in crews:
        sign = call_sign(wehr, code, WEHREN[wehr][2][code])
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


def build(target):
    rng = random.Random(SEED)
    members = {w: pool(rng, w) for w in WEHREN}
    counter = {w: 0 for w in WEHREN}
    bks_id, record_id, dispatch = 2010000, 2009000, 1260040100
    files = []
    for start, kw, reported_as, place_wehr, obj, minutes, crews_by_wehr, extra in sorted(INCIDENTS, key=lambda i: i[0]):
        record_id += 7
        dispatch += rng.randrange(3, 40)
        town, district = WEHREN[place_wehr][1][0], rng.choice(WEHREN[place_wehr][1])
        street = f"{rng.choice(STREETS)} {rng.randrange(1, 60)}" if not extra.get("bma") else f"{rng.choice(STREETS)} 1"
        end = start + dt.timedelta(minutes=minutes)
        slug = f"{start:%Y-%m-%d}_{kw.replace('.', '')}_{reported_as.split(',')[0].split()[0]}"
        common = {"Datensatz": str(record_id), "Einsatznummer Leitstelle": str(dispatch), "Einsatzstichwort": kw,
                  "Meldebild": reported_as, "Einsatzstelle - Ort": town, "Einsatzstelle - Ortsteil": f"{district} (NR)",
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
            for key in ("Datensatz",):
                master[key] = None
            files.append((f"{slug}_Stammdatensatz.xlsx", workbook(main_row({**master, "ID": str(record_id)}), [], [])))
        first_alarm = start
        for index, (wehr, codes) in enumerate(crews_by_wehr.items()):
            bks_id += 1
            counter[wehr] += 1
            alarm = first_alarm + dt.timedelta(minutes=0 if index == 0 else rng.randrange(8, 35))
            # Fahrzeuge der anderen Wehr kommen später an, der Einsatz endet für alle etwa gleichzeitig
            arrival_base = 4 + (0 if wehr == place_wehr else 5)
            vehicles, crews = vehicle_rows(rng, wehr, codes, alarm, end, arrival_base, extra.get("agt"),
                                           extra.get("deployed", 1))
            people, leader = people_rows(rng, members[wehr], crews, wehr)
            if index == 0:                                   # Hauptbericht listet auch die Fahrzeuge der anderen
                for other, other_codes in list(crews_by_wehr.items())[1:]:
                    rows, _ = vehicle_rows(rng, other, other_codes, alarm + dt.timedelta(minutes=12), end,
                                           arrival_base + 4, extra.get("agt"), 1)
                    vehicles += rows
                if extra.get("foreign"):                    # Überlandhilfe aus der Nachbar-VG
                    vehicles.append((extra["foreign"], 1, 0, 2, 3, 0, stamp(alarm + dt.timedelta(minutes=30)),
                                     stamp(alarm + dt.timedelta(minutes=37)), stamp(alarm + dt.timedelta(minutes=62)),
                                     1, stamp(end - dt.timedelta(minutes=20)), stamp(end - dt.timedelta(minutes=25)), None))
            row = {**common, "ID": str(bks_id), "Feuerwehrhaus": f"FW NR#.{CODE} {wehr:02d} {WEHREN[wehr][0]}",
                   "Name": f"FW NR#.{CODE} {wehr:02d} {WEHREN[wehr][0]}",
                   "Einsatzbericht-Nr.": f"{counter[wehr]}/26",
                   "Haupt-/Nebenbericht": "Hauptbericht (HB)" if index == 0 else "Nebenbericht (NB)",
                   "Einsatzleiter": leader}
            files.append((f"{slug}_Florian-Martin-{wehr}_{counter[wehr]:02d}-26.xlsx",
                          workbook(main_row(row), vehicles, people)))
        if extra.get("fez"):                                 # Bericht der Leitstelle/FEZ: wird beim Import übersprungen
            bks_id += 1
            row = {**common, "ID": str(bks_id), "Feuerwehrhaus": f"FW NR#.{CODE} 00 FEZ VG",
                   "Name": f"FW NR#.{CODE} 00 FEZ VG", "Einsatzbericht-Nr.": "FEZ 4/2026",
                   "Haupt-/Nebenbericht": "Nebenbericht (NB)", "Einsatzleiter": None}
            files.append((f"{slug}_FEZ.xlsx", workbook(main_row(row), [], [])))
    target.mkdir(parents=True, exist_ok=True)
    for name, data in files:
        (target / name).write_bytes(data)
    with zipfile.ZipFile(target / "alle-Berichte.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files:
            archive.writestr(name, data)
    return files


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "Einsatzberichte/Test-VG-Martin")
    print(f"{len(build(out))} Dateien in {out}")
