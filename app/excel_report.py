# -*- coding: utf-8 -*-
"""
Excel-Auswertung: die Auswertungen der Oberfläche als Mappe, dazu alle Einsätze und Fahrzeuge als Tabelle.

Blätter: Übersicht (Kennzahlen je Wehr, `excel_export.write_summary`), Statistik, Eintreffen und Zeiten, Belastung,
Abbrüche und Anlagen, Fahrzeuge und Atemschutz, Brand und Rettung, Personal (nur mit Recht auf Personen) sowie die
Listen Einsätze und Einsatzfahrzeuge (nur für Wehren, deren Einsätze der Benutzer sehen darf). Die Zahlen stammen aus
demselben Ergebnis wie `/api/evaluation`; es wird nichts neu berechnet. Fehlende Angaben bleiben leer (nie null).
"""
import openpyxl
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from app import domain
from app.excel_export import BORDER, FIRST_ROW, HEADER_ROW, _style_header, write_summary
from app.metrics import WEEKDAYS
from app.timeutil import parse_iso, parse_time

BOLD = Font(name="Calibri", size=11, bold=True)
COVERAGE = {"duration": "Einsatzdauer", "turnout": "Ausrückdauer", "arrival": "Zeit bis Eintreffen",
            "crew": "Besatzungsstärke", "attendance": "Anwesenheitsliste", "leader": "Einheitsführung"}
CASUALTIES = {"rescued": "Menschen gerettet", "rescued_animals": "Tiere gerettet", "injured": "Verletzte",
              "injured_firefighters": "Verletzte Feuerwehrangehörige", "deceased": "Verstorbene"}
PERCENT, ONE, INT, TIME, STAMP = "0%", "0.0", "0", "h:mm:ss", "DD.MM.YYYY hh:mm"


class Page:
    """Ein Blatt aus untereinander stehenden Tabellen mit Überschrift."""

    def __init__(self, ws, title):
        self.ws, self.row, self.columns = ws, 1, 1
        ws["A1"] = title
        ws["A1"].font = Font(name="Calibri", size=14, bold=True)
        self.row = 3

    def text(self, note):
        self.ws.cell(self.row, 1, note).data_type = "s"
        self.row += 2

    def table(self, title, headers, rows, formats=()):
        """Tabelle mit Titel; leere Tabellen entfallen. formats: Zahlenformat je Spalte (None = Standard)."""
        rows = [r for r in rows]
        if not rows:
            return
        self.ws.cell(self.row, 1, title).font = BOLD
        self.row += 1
        for i, header in enumerate(headers, start=1):
            _style_header(self.ws.cell(self.row, i, header), horizontal="center", vertical="center")
        self.row += 1
        for values in rows:
            for i, value in enumerate(values, start=1):
                _put(self.ws, self.row, i, value, formats[i - 1] if i <= len(formats) else None)
            self.row += 1
        self.row += 1
        self.columns = max(self.columns, len(headers))

    def facts(self, title, pairs):
        """Kennzahlen als Liste „Bezeichnung – Wert“; pairs: (Bezeichnung, Wert, Zahlenformat)."""
        self.table(title, ["Kennzahl", "Wert"], [(label, value) for label, value, _ in pairs if value is not None],
                   [None, None])
        # Zahlenformate nachtragen (die Tabelle steht direkt über der aktuellen Zeile)
        shown = [f for _, value, f in pairs if value is not None]
        start = self.row - 1 - len(shown)
        for offset, number_format in enumerate(shown):
            if number_format:
                self.ws.cell(start + offset, 2).number_format = number_format

    def finish(self, first_width=38):
        self.ws.column_dimensions["A"].width = first_width
        for i in range(2, max(self.columns, 2) + 1):
            self.ws.column_dimensions[get_column_letter(i)].width = 16


def _put(ws, row, column, value, number_format=None):
    cell = ws.cell(row, column, value)
    if isinstance(value, str):
        cell.data_type = "s"             # Text nie als Formel auslegen
    elif isinstance(value, bool):
        cell.value = "Ja" if value else "Nein"
    cell.border = BORDER
    if number_format:
        cell.number_format = number_format
    return cell


def _dist(label, d):
    return [label, d["valid"], d["total"], d["average"], d["median"], d["p90"]]


DIST_HEADERS = ["", "Einsätze mit Angabe", "Einsätze gesamt", "Ø (min)", "Median (min)", "90 % ≤ (min)"]
DIST_FORMATS = [None, INT, INT, ONE, ONE, ONE]


# ---------------------------------------------------------------- Blätter der Auswertung
def _statistics(ws, r, year):
    s = r["statistics"]
    page = Page(ws, f"Statistik {year}")
    page.facts("Überblick", [
        ("Einsätze", s["count"], INT), ("Einsätze im Vorjahr (ganzes Jahr)", s["previous_total"], INT),
        ("Einsätze im Vorjahr bis zum gleichen Tag", s["previous_to_date"], INT),
        ("Einsätze je Woche", s["per_week"], "0.00"),
        ("Einsatzstunden", round(s["duration_total_min"] / 60, 1), ONE),
        ("Ø Einsatzdauer (min)", s["duration_avg_min"], ONE),
        ("Personalstunden", s["staff_hours"], ONE), ("Ø Personen je Einsatz", s["attendees_avg"], ONE),
        ("Anteil am Tag", s["daytime_share"], PERCENT),
        ("Brandmeldeanlagen", s["fire_alarm_systems"], INT), ("Brandsicherheitswachen", s["fire_watches"], INT)])
    page.table("Einsatzarten", ["Art", "Bezeichnung", "Einsätze"], [(c["code"], c["name"], c["count"])
                                                                   for c in s["categories"]], [None, None, INT])
    levels = [lv["level"] for lv in s["levels"]]
    page.table("Stichworte nach Art und Stufe", ["Art", *[f"Stufe {lv}" for lv in levels]],
               [(c["code"], *[c["keywords"].get(f"{c['code']}{lv}", 0) for lv in levels]) for c in s["categories"]],
               [None] + [INT] * len(levels))
    page.table("Alarmstufen", ["Stufe", "Einsätze"], [(lv["level"], lv["count"]) for lv in s["levels"]], [INT, INT])
    page.table("Einsatzorte", ["Gebiet", "Einsätze"], [(a["name"], a["count"]) for a in s["areas"]], [None, INT])
    page.table("Monate", ["Monat", "Einsätze", "Vorjahr"], [(m["name"], m["count"], m["previous"])
                                                           for m in s["months"]], [None, INT, INT])
    page.table("Wochentage", ["Wochentag", "Einsätze"], [(d["name"], d["count"]) for d in s["weekdays"]], [None, INT])
    page.table("Alarmierungen nach Uhrzeit", ["Stunde", "Einsätze", "Tagzeit"],
               [(f"{h['hour']:02d}–{h['hour'] + 1:02d} Uhr", h["count"], h["daytime"]) for h in s["hours"]],
               [None, INT, None])
    page.table("Verlauf über alle Jahre", ["Monat", "Einsätze", "Ø der letzten 12 Monate"],
               [(f"{h['year']}-{h['month']:02d}", h["count"], h["average"]) for h in r["history"]], [None, INT, "0.00"])
    page.finish()


def _response(ws, r, year, limit):
    page = Page(ws, f"Eintreffen und Zeiten {year} (Zeitgrenze {limit} Minuten)")
    plan, timing = r["response_plan"], r["timing"]
    if not plan and not timing:
        page.text("Der Bedarfsplan ist für die gewählten Wehren nicht freigegeben.")
    if r["response_plan_hidden"]:
        page.text("Nicht enthalten (nicht freigegeben): " + ", ".join(r["response_plan_hidden"]))
    if plan:
        headers = ["Zeitfenster", "Einsätze", "Ø Ausrückdauer (min)", "Ø Zeit bis Eintreffen (min)", "in der Zeitgrenze",
                   "darüber", "Erreichungsgrad", "Ø Kräfte beim Eintreffen", "Ø weitere Kräfte in der Zeitgrenze",
                   "Ø weitere Kräfte in der zweiten Zeitgrenze", "Ø Kräfte gesamt"]
        keys = ("count", "turnout_min", "arrival_min", "on_time", "late", "rate", "crew_on_arrival",
                "crew_within_limit", "crew_within_second", "crew_total")
        rows = [(f"{w['day_type']} {w['hours']}", *[w[k] for k in keys]) for w in plan["windows"]]
        rows.append(("Gesamt", *[plan["total"][k] for k in keys]))
        formats = [None, INT, ONE, ONE, INT, INT, PERCENT, ONE, ONE, ONE, ONE]
        page.table(f"Eintreffen und verfügbare Kräfte ({', '.join(plan['places'])})", headers, rows, formats)
        if plan["without_times"]:
            page.text(f"{plan['without_times']} Einsätze ohne Eintreffzeit sind nicht enthalten.")
    if timing:
        page.table("Zeiten aller Einsätze", DIST_HEADERS,
                   [_dist("Ausrückdauer (Alarm bis erstes Fahrzeug unterwegs)", timing["turnout"]),
                    _dist("Zeit bis zum Eintreffen (erstes Fahrzeug)", timing["arrival"]),
                    _dist("Anfahrtdauer je Fahrzeug", timing["travel"])], DIST_FORMATS)
        page.table("Kräfteaufbau", ["Minuten nach Alarm", "Ø Kräfte vor Ort", "Einsätze mit Angabe", "Einsätze gesamt"],
                   [(b["minutes"], b["crew"], b["valid"], b["total"]) for b in timing["build_up"]],
                   [INT, ONE, INT, INT])
        for title, key, label in (("Zeiten nach Gebiet", "by_area", "name"), ("Zeiten nach Zeitfenster", "by_window", "key")):
            page.table(title, ["", "Einsätze", "Ausrückdauer: Ø (min)", "Median", "90 % ≤",
                               "Eintreffen: Ø (min)", "Median", "90 % ≤"],
                       [((g["name"] if key == "by_area" else f"{g['day_type']} {g['hours']}"), g["count"],
                         g["turnout"]["average"], g["turnout"]["median"], g["turnout"]["p90"],
                         g["arrival"]["average"], g["arrival"]["median"], g["arrival"]["p90"])
                        for g in timing[key]], [None, INT, ONE, ONE, ONE, ONE, ONE, ONE])
    page.finish(48)


def _workload(ws, r, year):
    w = r["workload"]
    page = Page(ws, f"Belastung {year}")
    page.table("Dauer der Einsätze", DIST_HEADERS, [_dist("Alarm bis Einsatzende", w["duration"])], DIST_FORMATS)
    parts = (("Lange Einsätze (ab %d min)" % w["long"]["minutes"], w["long"]), ("Nachts", w["night"]),
             ("Wochenende / Feiertag", w["weekend"]))
    page.table("Belastung nach Art", ["", "Einsätze", "Anteil", "Stunden", "Einsätze mit Dauer", "Personalstunden",
                                      "Einsätze mit Anwesenheit"],
               [(label, p["count"], p["share"], p["hours"], p["hours_valid"], p["staff_hours"], p["staff_recorded"])
                for label, p in parts], [None, INT, PERCENT, ONE, INT, ONE, INT])
    page.table("Dauer in Klassen", ["Dauer", "Einsätze"], [(b["label"], b["count"]) for b in w["buckets"]], [None, INT])
    o = w["overlap"]
    page.facts("Gleichzeitige Einsätze", [
        ("Einsätze mit Überschneidung", o["incidents_with_overlap"], INT),
        ("Höchstens gleichzeitig", o["max_concurrent"], INT), ("Minuten mit Überschneidung", o["overlap_minutes"], INT),
        ("Einsätze mit Beginn und Ende", o["valid"], INT), ("Einsätze gesamt", o["total"], INT)])
    page.table("Datenvollständigkeit", ["Angabe", "Einsätze mit Angabe", "Einsätze gesamt"],
               [(COVERAGE.get(c["key"], c["key"]), c["valid"], r["coverage"]["total"]) for c in r["coverage"]["rows"]],
               [None, INT, INT])
    page.finish()


def _aborts(ws, r, year):
    a, systems = r["aborts"], r["alarm_systems"]
    page = Page(ws, f"Abbrüche und Anlagen {year}")
    page.facts("Einsatzabbrüche", [("Einsätze", a["total"], INT), ("mit Abbruchgrund", a["aborted"], INT),
                                   ("Anteil", a["share"], PERCENT)])
    page.table("Gründe nach Gruppe", ["Gruppe", "Einsätze", "Anteil an den Abbrüchen"],
               [(k["label"], k["count"], k["share"]) for k in a["kinds"]], [None, INT, PERCENT])
    page.table("Häufigste Gründe", ["Grund", "Gruppe", "Einsätze"],
               [(x["reason"], dict(domain.ABORT_KINDS).get(x["kind"], ""), x["count"]) for x in a["reasons"]],
               [None, None, INT])
    page.table("Abbrüche nach Einsatzart", ["Art", "Bezeichnung", "Einsätze", "davon abgebrochen", "Anteil"],
               [(c["code"], c["name"], c["count"], c["aborted"], c["share"]) for c in a["categories"]],
               [None, None, INT, INT, PERCENT])
    f = a["fire_alarm_systems"]
    page.facts("Brandmeldeanlagen", [("Einsätze", f["count"], INT), ("davon abgebrochen", f["aborted"], INT),
                                     ("davon Fehlalarm / kein Ereignis", f["false_alarms"], INT),
                                     ("Anteil abgebrochen", f["share"], PERCENT)])
    page.table(f"Brandmeldeanlagen je Anlage ({systems['identified']} von {systems['total']} Einsätzen zugeordnet)",
               ["Anlage", "Objekt", "Einsätze", "abgebrochen", "Fehlalarme", "Anteil Fehlalarme", "letzter Einsatz"],
               [(x["system"] or "ohne Angabe", x["building"], x["count"], x["aborted"], x["false_alarms"],
                 x["false_share"], parse_iso(x["last"])) for x in systems["rows"]],
               [None, None, INT, INT, INT, PERCENT, STAMP])
    page.finish()


def _resources(ws, r, year):
    page = Page(ws, f"Fahrzeuge und Atemschutz {year}")
    page.table("Fahrzeuge", ["Fahrzeug", "Typ", "alarmiert", "ausgerückt", "eingesetzt", "nur bereitgestellt",
                             "ohne Angabe", "Anteil bereitgestellt", "Ø Besatzung", "Stunden im Einsatz"],
               [(u["call_sign"], u["label"], u["alerted"], u["drove"], u["deployed"], u["standby"], u["unknown"],
                 u["standby_share"], u["crew_avg"], u["hours"]) for u in r["vehicle_usage"]["rows"]],
               [None, None, INT, INT, INT, INT, INT, PERCENT, ONE, ONE])
    a = r["respiratory"]
    page.facts("Atemschutz", [
        ("Einsätze gesamt", a["total"], INT), ("Einsätze mit Angabe", a["known"], INT),
        ("davon mit Atemschutz", a["with_agt"], INT), ("Anteil", a["share"], PERCENT),
        ("Geräteträger (laut Fahrzeugen)", a["carriers"], INT), ("Geräteträger (laut Anwesenheit)", a["persons"], INT),
        ("Minuten unter Atemschutz", a["minutes"], INT), ("Ø Minuten je Träger", a["average_minutes"], ONE),
        ("Längster Einsatz (min)", a["longest_minutes"], INT)])
    page.finish()


def _fire(ws, r, year):
    page = Page(ws, f"Brand und Rettung {year}")
    f = r["fire_course"]
    page.table(f"Brandverlauf ({f['total']} Brandeinsätze ohne Abbruch, Anlagen und Wachen)", DIST_HEADERS,
               [_dist("Eintreffen bis „Brand unter Kontrolle“", f["to_control"]),
                _dist("Eintreffen bis „Feuer aus“", f["to_out"])], DIST_FORMATS)
    page.table("Einsatztaktik", DIST_HEADERS[:1] + ["Einsätze", "Mit Angabe „unter Kontrolle“", "Ø (min)", "Median (min)",
                                                    "90 % ≤ (min)"],
               [(t["tactic"], t["count"], t["control"]["valid"], t["control"]["average"], t["control"]["median"],
                 t["control"]["p90"]) for t in f["tactics"]], [None, INT, INT, ONE, ONE, ONE])
    page.facts("Brandwachen", [("Einsätze mit Brandwache", f["fire_watches"], INT),
                               ("Stunden nach Feuer aus", f["fire_watch_hours"], ONE),
                               ("Einsätze mit auswertbarer Dauer", f["fire_watch_valid"], INT)])
    c = r["casualties"]
    page.table("Rettung und Verletzte", ["Angabe", "Personen / Tiere", "Einsätze mit Wert über 0", "Einsätze mit Angabe"],
               [(label, c["fields"][key]["total"], c["fields"][key]["incidents"], c["fields"][key]["reported"])
                for key, label in CASUALTIES.items()], [None, INT, INT, INT])
    page.facts("Gesamt", [("Einsätze mit Personenschaden oder Rettung", c["incidents_with_persons"], INT),
                          ("Einsätze gesamt", c["total"], INT)])
    page.finish()


def _people(ws, r, year):
    a = r["attendance"]
    page = Page(ws, f"Personal {year}")
    page.table("Funktionen", ["Funktion", "Einsatzteilnahmen", "Personen"],
               [(f["role"], f["count"], f["people"]) for f in a["functions"]], [None, INT, INT])
    page.table(f"Einsatzteilnahmen ({a['incident_count']} Einsätze)",
               ["Name", "Einsätze", "Anteil", "Stunden", "Nachts", "Wochenende / Feiertag", "Atemschutz: Einsätze",
                "Atemschutz: Minuten", "Zuletzt"],
               [(m["name"], m["incidents"], m["rate"], m["hours"], m["nights"], m["weekends"], m["agt_incidents"],
                 m["agt_minutes"], parse_iso(m["last"])) for m in a["members"]],
               [None, INT, PERCENT, ONE, INT, INT, INT, INT, STAMP])
    page.finish()


# ---------------------------------------------------------------- Listen: alle Einsätze und Fahrzeuge
def _incident_columns(with_leader):
    """(Überschrift, Wert, Format, Breite); Wert: f(einsatz, kennzahlen, teil) – teil["plan"] false = Zeiten ausgeblendet."""
    def plan(key):
        return lambda i, m, p: m[key] if p["plan"] else None

    def stamp(key):
        return lambda i, m, p: parse_iso(i.get(key))

    def minutes(key):
        return lambda i, m, p: round(m[key], 1) if p["plan"] and m[key] is not None else None

    columns = [
        ("Wehr", lambda i, m, p: p["name"], None, 22),
        ("Nr.", lambda i, m, p: i["number"], INT, 6),
        ("Beginn", stamp("started_at"), STAMP, 17),
        ("Ende", stamp("ended_at"), STAMP, 17),
        ("Dauer (min)", lambda i, m, p: None if m["duration_min"] is None else round(m["duration_min"]), INT, 9),
        ("Wochentag", lambda i, m, p: weekday_of(i), None, 11),
        ("Tag / Nacht", lambda i, m, p: "Tag" if m["daytime"] else "Nacht" if i["started_at"] else None, None, 9),
        ("Wochenende / Feiertag", lambda i, m, p: bool(i["weekend_or_holiday"]), None, 11),
        ("Stichwort", lambda i, m, p: i["keyword"], None, 9),
        ("Stufe", lambda i, m, p: i["subcode"], None, 6),
        ("Einsatz", lambda i, m, p: i["description"], None, 44),
        ("Ort", lambda i, m, p: i["place"], None, 18),
        ("Gebiet", lambda i, m, p: m["area"], None, 14),
        ("Leitstellen-Nr.", lambda i, m, p: i.get("dispatch_number"), None, 16),
        ("Gerätehaus", lambda i, m, p: i["station_staff"], INT, 10),
        ("Stärke gesamt", lambda i, m, p: m["crew_total"], INT, 9),
        ("Anwesende", lambda i, m, p: m["attendees"], INT, 10),
        ("Ausrückdauer (min)", minutes("turnout_min"), ONE, 10),
        ("Zeit bis Eintreffen (min)", minutes("arrival_min"), ONE, 11),
        ("In der Zeitgrenze", lambda i, m, p: m["on_time"] if p["plan"] else None, None, 10),
        ("Kräfte beim Eintreffen", plan("crew_on_arrival"), INT, 10),
        ("Weitere Kräfte in der Zeitgrenze", plan("crew_within_limit"), INT, 12),
        ("Weitere Kräfte in der zweiten Zeitgrenze", plan("crew_within_second"), INT, 12),
        ("Kräfte gesamt (Bedarfsplan)", plan("crew_plan_total"), INT, 11),
        ("Bedarfsplan-relevant", lambda i, m, p: m["plan_relevant"] if p["plan"] else None, None, 11),
        ("Abbruchgrund", lambda i, m, p: i.get("abort_reason"), None, 30),
        ("Objekt", lambda i, m, p: i.get("building"), None, 24),
        ("Brandmelde-Nr.", lambda i, m, p: i.get("alarm_system"), None, 14),
        ("Einsatztaktik", lambda i, m, p: i.get("tactic"), None, 16),
        ("Brand unter Kontrolle", stamp("fire_controlled_at"), STAMP, 17),
        ("Feuer aus", stamp("fire_out_at"), STAMP, 17),
        ("Brandwache bis", stamp("fire_watch_until"), STAMP, 17),
        ("Menschen gerettet", lambda i, m, p: i.get("rescued"), INT, 10),
        ("Tiere gerettet", lambda i, m, p: i.get("rescued_animals"), INT, 10),
        ("Verletzte", lambda i, m, p: i.get("injured"), INT, 9),
        ("Verletzte FW", lambda i, m, p: i.get("injured_firefighters"), INT, 9),
        ("Verstorbene", lambda i, m, p: i.get("deceased"), INT, 10),
        ("Fahrzeuge", lambda i, m, p: ", ".join(cs for cs in p["cfg"].vehicles_for(i) if cs in i["vehicles"]), None, 22),
        ("BKS-Bericht", lambda i, m, p: i.get("bks_report_id"), None, 14),
        ("Prüfhinweise", lambda i, m, p: "; ".join(i["warnings"]), None, 50),
    ]
    if with_leader:
        columns.insert(14, ("Einheitsführung", lambda i, m, p: i["unit_leader"], None, 18))
    return columns


def weekday_of(incident):
    start = parse_iso(incident["started_at"])
    return WEEKDAYS[start.weekday()] if start else None


def _write_list(ws, columns, rows):
    for i, (header, _, _, width) in enumerate(columns, start=1):
        _style_header(ws.cell(HEADER_ROW, i, header), horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.row_dimensions[HEADER_ROW].height = 48
    for r, values in enumerate(rows, start=FIRST_ROW):
        for i, ((_, _, number_format, _), value) in enumerate(zip(columns, values), start=1):
            cell = _put(ws, r, i, value, number_format)
            cell.alignment = Alignment(vertical="center")
    ws.freeze_panes = ws.cell(FIRST_ROW, 3)
    ws.auto_filter.ref = f"A{HEADER_ROW}:{get_column_letter(len(columns))}{FIRST_ROW + max(len(rows), 1) - 1}"


def _vehicle_columns():
    return [
        ("Wehr", lambda p, i, m, cs, v, vm: p["name"], None, 22),
        ("Nr.", lambda p, i, m, cs, v, vm: i["number"], INT, 6),
        ("Beginn", lambda p, i, m, cs, v, vm: parse_iso(i["started_at"]), STAMP, 17),
        ("Stichwort", lambda p, i, m, cs, v, vm: i["keyword"], None, 9),
        ("Fahrzeug", lambda p, i, m, cs, v, vm: cs, None, 10),
        ("Funkrufname", lambda p, i, m, cs, v, vm: v.get("name"), None, 24),
        ("Besatzung", lambda p, i, m, cs, v, vm: v.get("crew"), INT, 10),
        ("Alarmiert", lambda p, i, m, cs, v, vm: parse_time(v.get("alerted")), TIME, 10),
        ("Ausgerückt", lambda p, i, m, cs, v, vm: parse_time(v.get("departed")), TIME, 10),
        ("Eingetroffen", lambda p, i, m, cs, v, vm: parse_time(v.get("arrived")), TIME, 10),
        ("Einsatzende", lambda p, i, m, cs, v, vm: parse_time(v.get("finished")), TIME, 10),
        ("Ausrückdauer (min)", lambda p, i, m, cs, v, vm: _minutes(p, vm, "turnout_min"), ONE, 10),
        ("Zeit bis Eintreffen (min)", lambda p, i, m, cs, v, vm: _minutes(p, vm, "arrival_min"), ONE, 11),
        ("Eingesetzt", lambda p, i, m, cs, v, vm: {1: "Ja", 0: "Nur bereitgestellt"}.get(v.get("deployed")), None, 16),
        ("Atemschutzträger", lambda p, i, m, cs, v, vm: v.get("respiratory"), INT, 11),
    ]


def _minutes(part, vehicle_metrics, key):
    value = vehicle_metrics.get(key) if part["plan"] else None
    return None if value is None else round(value, 1)


def _vehicle_rows(parts):
    columns = _vehicle_columns()
    rows = []
    for p in parts:
        for i, m in p["evaluated"]:
            for cs in p["cfg"].vehicles_for(i):
                if cs in i["vehicles"]:
                    v, vm = i["vehicles"][cs], m["vehicles"].get(cs) or {}
                    rows.append([get(p, i, m, cs, v, vm) for _, get, _, _ in columns])
    return columns, rows


# ---------------------------------------------------------------- Mappe
def write_report_workbook(result, rows, total, year, limit, target, notes=(), parts=()):
    """result: Ergebnis von `api.evaluation.build_evaluation`; rows/total: metrics.summary je Wehr und Summe.

    parts: [{"name", "cfg", "evaluated", "plan", "people"}] der Wehren, deren Einsätze der Benutzer sehen darf
    (plan: Eintreffzeiten und Bedarfsplan sichtbar, people: Einheitsführung sichtbar)."""
    wb = openpyxl.Workbook()
    wb.active.title = "Übersicht"
    write_summary(wb.active, rows, total, year, limit, notes)
    for title, write, args in (("Statistik", _statistics, (year,)),
                               ("Eintreffen und Zeiten", _response, (year, limit)),
                               ("Belastung", _workload, (year,)),
                               ("Abbrüche und Anlagen", _aborts, (year,)),
                               ("Fahrzeuge und Atemschutz", _resources, (year,)),
                               ("Brand und Rettung", _fire, (year,))):
        write(wb.create_sheet(title), result, *args)
    if result["attendance"]:
        _people(wb.create_sheet("Personal"), result, year)
    if parts:
        columns = _incident_columns(any(p["people"] for p in parts))
        table = [[get(i, m, p) for _, get, _, _ in columns] for p in parts for i, m in p["evaluated"]]
        # Einheitsführung nur für Wehren mit Recht auf Personen; sonst leer
        leader = next((n for n, c in enumerate(columns) if c[0] == "Einheitsführung"), None)
        if leader is not None:
            flags = [p["people"] for p in parts for _ in p["evaluated"]]
            for row, allowed in zip(table, flags):
                if not allowed:
                    row[leader] = None
        _write_list(wb.create_sheet("Einsätze"), columns, table)
        columns, table = _vehicle_rows(parts)
        _write_list(wb.create_sheet("Einsatzfahrzeuge"), columns, table)
    wb.save(target)
