# -*- coding: utf-8 -*-
"""
Aufbau der Excel-Einsatzübersicht einer Wehr.

Blatt Einsatzübersicht: Kopf in Zeile 3, Einsätze ab Zeile 4. Die Fahrzeugblöcke (je Stärke,
Ausrücken, Ausrückdauer, Eintreffen, Zeit bis Eintreffen) werden aus der Fahrzeugliste der Wehr erzeugt – bei fünf
Fahrzeugen sind das wie im Original die Spalten A:AV.
Blatt Anwesenheit: Personen ab Spalte F, danach die Summenspalten Stärke und Gesamtstunden.
"""
from openpyxl.utils import get_column_letter

HEADER_ROW = 3
FIRST_ROW = 4
ATTENDANCE_FIRST_COLUMN = 6
ATTENDANCE_TOTALS = ("Stärke", "Gesamtstunden")

VEHICLE_PARTS = ("crew", "departed", "turnout", "arrived", "arrival")


class Layout:
    """Spalten der Einsatzübersicht für eine Fahrzeugliste und die Zeitgrenzen der Wehr."""

    def __init__(self, vehicles, limit, second_limit):
        self.vehicles = tuple(vehicles)
        self.columns = self._columns(limit, second_limit)
        self.headers = [header for _, header in self.columns]
        # Schlüssel -> Spaltenbuchstabe, z. B. column["number"] == "A", column["02/45.crew"] == "M"
        self.column = {key: get_column_letter(i) for i, (key, _) in enumerate(self.columns, start=1)}
        self.last_column = len(self.columns)

    @staticmethod
    def _vehicle_headers(call_sign, limit, second_limit):
        short = call_sign.split("/")[-1]
        return (f"Stärke ({short})", f"Ausrücken ({short})", f"Ausrückdauer ({short}) min.",
                f"Eintreffen ({short})", f"Zeit bis Eintreffen ({limit}/{second_limit} min)\n({short})")

    def _columns(self, limit, second_limit):
        """[(schlüssel, Überschrift)] in Spaltenreihenfolge ab A."""
        columns = [("number", "Nr."), ("date", "Datum"), ("weekday", "Tag"), ("day_night", "Tag / Nacht"),
                   ("start", "Einsatzbeginn"), ("end", "Einsatzende"), ("duration", "Einsatzdauer"),
                   ("keyword", "Einsatzstichwort"), ("subcode", "Stufe"), ("description", "Einsatz"),
                   ("place", "Ort"), ("unit_leader", "Einheitsführung")]
        for call_sign in self.vehicles:
            columns += [(f"{call_sign}.{part}", header)
                        for part, header in zip(VEHICLE_PARTS, self._vehicle_headers(call_sign, limit, second_limit))]
        columns += [("station_staff", "Personen Gerätehaus"), ("crew_total", "Gesamtstärke"), ("gap", ""),
                    ("turnout", "Ausrückdauer min."), ("arrival", "Zeit bis Eintreffen"), ("on_time", f"{limit} Min. erreicht"),
                    ("crew_on_arrival", "Stärke bei Eintreffen"), ("crew_within_limit", f"Zusätzlich bis {limit} Min."),
                    ("crew_within_second", f"Zusätzlich {limit}–{second_limit} Min."), ("crew_plan_total", "Gesamtstärke"),
                    ("weekend_or_holiday", "Wochenende / Feiertag")]
        return columns

    def vehicle_column(self, call_sign, part):
        return self.column[f"{call_sign}.{part}"]
