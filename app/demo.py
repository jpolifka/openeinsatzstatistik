# -*- coding: utf-8 -*-
"""
Demo-Daten: eine erfundene VG mit zwei vollständig eingerichteten Wehren, aber ohne Einsätze.

Alles ist ausgedacht. Die Einrichtung (Kennung, Fahrzeuge, Personen) passt zu den Testberichten von
`tools/gen_test_reports.py Musterland MUS --wehren 2 --orte Musterstadt,Nebenhausen`; wer sie hochlädt, sieht bis auf zwei
gewollte Abweichungen nur sauber gepflegte Daten:
  1. Eine Person (Fiktiv, Mia) steht nicht im Personalstamm und wird beim Einlesen neu angelegt.
  2. Im Scheunenbrand hilft ein Fahrzeug einer Nachbar-VG (FL NR#.NBV), das keiner Wehr gehört.
Aufruf: python -m app.demo   (legt in DATA_DIR an, was fehlt; ist die Demo-VG schon da, passiert nichts)
Gedacht für Vorführungen und Nutzertests, nicht für den Betrieb.
"""
from app import db, fees, tenancy
from app.tenant_config import TenantConfig, Vehicle

VG_SLUG, VG_NAME = "vg-musterland", "VG Musterland"
# Kennung der VG im BKS-Bericht: Kreis (Kfz-Zeichen) und Kürzel der VG; die Wehren haben die Standorte 01, 02 …
BKS_CODE = "NR#.MUS"
PLACES = ("Musterstadt", "Nebenhausen")

# Fahrzeuge und Personen wie in den Testberichten; weggelassen ist „Fiktiv, Mia“ (Abweichung 1)
WEHREN = (
    ("musterstadt", "Feuerwehr Musterstadt", "01",
     (("46", "HLF 20"), ("23", "TLF 3000"), ("34", "DLK 23/12"), ("11", "ELW 1"), ("19", "MTF"), ("65", "WLF"),
      ("91", "Wehrführer")),
     ("Sample, Paul", "Beispiel, Jonas", "Dummy, Paul", "Beispiel, Leon", "Demo, Klara", "Dummy, Uwe", "Sample, Jonas",
      "Platzhalter, Sven", "Test, Mia", "Beispiel, Olga", "Demo, Uwe", "Test, Clara", "Platzhalter, Uwe",
      "Muster, Sven")),
    ("nebenhausen", "Feuerwehr Nebenhausen", "02",
     (("45", "LF 10"), ("41", "TSF"), ("53", "GW-Mess"), ("56", "GW-A"), ("18", "ATV"), ("19", "MTF")),
     ("Test, Anna", "Sample, Nico", "Fiktiv, Nico", "Test, Klara", "Fiktiv, Rita", "Demo, Ida", "Demo, Jonas",
      "Beispiel, Clara", "Muster, Greta", "Platzhalter, Nico", "Beispiel, Uwe", "Beispiel, David", "Erfunden, Sven")),
)

# Erfundene Gebührenordnung (Stundensätze in Euro); der Fahrzeugtyp ist die Bezeichnung des Fahrzeugs
FEE_SCHEDULE = {
    "name": "Gebührensatzung der VG Musterland vom 12.02.2026", "valid_from": "2026-03-01",
    "rates": {
        "personnel": 36.00, "personnel_bma": 36.00, "fire_watch": 14.00, "bma_flat_max": 450.00, "admin_surcharge": 10,
        "vehicles": [
            {"code": "HLF 20", "name": "Hilfeleistungs-Löschgruppenfahrzeug 20", "rate": 462.00},
            {"code": "LF 10", "name": "Löschgruppenfahrzeug 10", "rate": 316.00},
            {"code": "TSF", "name": "Tragkraftspritzenfahrzeug", "rate": 69.00},
            {"code": "TLF 3000", "name": "Tanklöschfahrzeug 3000", "rate": 318.00},
            {"code": "DLK 23/12", "name": "Drehleiter mit Korb 23/12", "rate": 372.00},
            {"code": "ELW 1", "name": "Einsatzleitwagen 1", "rate": 108.00},
            {"code": "MTF", "name": "Mannschaftstransportfahrzeug", "rate": 38.00},
            {"code": "WLF", "name": "Wechselladerfahrzeug", "rate": 215.00},
            {"code": "GW-Mess", "name": "Gerätewagen Messtechnik", "rate": 95.00},
            {"code": "GW-A", "name": "Gerätewagen Atemschutz", "rate": 88.00},
            {"code": "ATV", "name": "All-Terrain-Vehicle", "rate": 41.00},
            {"code": "Wehrführer", "name": "Kommandowagen Wehrführer", "rate": 43.00},
        ],
    },
}


def make_config(name, station, fleet, vg_layer):
    """Fachkonfiguration einer Wehr; Funkrufnamen wie im BKS-Bericht (erfunden). Orte, Zeitgrenzen und Tageszeit
    kommen als Vorgabe von der VG, der Ausrückebereich ist je Wehr der eigene Ort."""
    prefix = f"FL {BKS_CODE} "
    vehicles = tuple(Vehicle(f"{station}/{number}", label=label, name=f"{prefix}{station}/{number}-01")
                     for number, label in fleet)
    values = {key: vg_layer.value(key) for key in ("control_center", "places", "plan_min_level", "response_limits",
                                                   "default_limit", "second_limit", "day_hours", "numbering")}
    return TenantConfig(name=name, fleet=vehicles, unit_prefix=prefix, own_prefix=f"{station}/",
                        unit_marker=f"FW {BKS_CODE} {station}", plan_places=(name.split()[-1],),
                        response_plan_public=True, **values)


def seed():
    """Legt VG, Wehren, Personal und Gebührenordnung an, falls es die Demo-VG noch nicht gibt (keine Einsätze).
    Gibt True zurück, wenn etwas angelegt wurde."""
    tenancy.setup()
    with tenancy.central() as con:
        if con.execute("SELECT 1 FROM vg WHERE slug = ?", (VG_SLUG,)).fetchone():
            return False
        vg_id = tenancy.create_vg(con, VG_SLUG, VG_NAME)
        # Auftragsverarbeitung gilt als abgeschlossen, sonst wären die Wehren gesperrt
        con.execute("INSERT INTO dpa (vg_id, status) VALUES (?, 'signed')", (vg_id,))
        # Vorgaben der VG, die alle Wehren erben: Kennung, Orte, Zeitgrenzen (10 und 15 Minuten), Tag 06–18 Uhr
        tenancy.save_vg_settings(con, vg_id, {
            "bks_code": BKS_CODE, "places": PLACES, "plan_min_level": 2, "response_limits": (10, 15),
            "default_limit": 10, "second_limit": 15, "day_hours": (6, 18), "numbering": "bks"})
        layer = tenancy.load_vg_layer(con, vg_id)
        fees.save_schedule(con, vg_id, FEE_SCHEDULE["name"], FEE_SCHEDULE["valid_from"], FEE_SCHEDULE["rates"], "Demo")
        for slug, name, station, fleet, people in WEHREN:
            cfg = make_config(name, station, fleet, layer)
            tenancy.create_tenant(con, slug, name, vg_id, cfg)
            with db.connection(tenancy.tenant_path(slug)) as tenant_con:
                for order, full in enumerate(people, start=1):
                    last, first = full.split(", ")
                    tenant_con.execute("INSERT INTO member (name, last_name, first_name, sort_order) VALUES (?,?,?,?)",
                                       (full, last, first, order))
    return True


if __name__ == "__main__":
    print("Demo-Daten angelegt." if seed() else "Demo-Daten sind schon vorhanden.")
