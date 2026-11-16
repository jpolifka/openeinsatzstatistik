# -*- coding: utf-8 -*-
"""
Demo-Daten: eine erfundene VG mit zwei Wehren und rund zwei Jahren Einsätzen.

Alles ist ausgedacht (Namen, Orte, Fahrzeuge, Zeiten); es gibt keinen Bezug zu echten Personen oder Einsätzen.
Die Werte sind mit festem Startwert erzeugt, jeder Lauf liefert also dieselben Daten.
Aufruf: python -m app.demo   (legt in DATA_DIR an, was fehlt; ist die Demo-VG schon da, passiert nichts)
Gedacht für Vorführungen und Nutzertests, nicht für den Betrieb.
"""
import datetime as dt
import random

from app import db, store, tenancy
from app.tenant_config import TenantConfig, Vehicle

VG_SLUG, VG_NAME = "vg-musterland", "VG Musterland"
SEED = 20260101
TODAY = dt.date(2026, 11, 15)

LAST_NAMES = ("Fiktiv", "Beispiel", "Muster", "Probe", "Demo", "Sample", "Dummy", "Platzhalter", "Erfunden", "Test")
FIRST_NAMES = ("Anna", "Ben", "Clara", "David", "Emma", "Felix", "Greta", "Hans", "Ida", "Jonas", "Klara", "Leon",
               "Mia", "Nico", "Olga", "Paul", "Rita", "Sven", "Tina", "Uwe")
ROLES = ("Gruppenführer", "Maschinist", "Angriffstrupp", "Wassertrupp", "Melder", "Schlauchtrupp")
STREETS = ("Musterweg", "Beispielstraße", "Probegasse", "Demoallee", "Hauptstraße", "Am Sportplatz", "Bahnhofstraße")

# (Stichwort, Stufe, Anteil, Dauer in Minuten von/bis, braucht Atemschutz, Beschreibung)
KINDS = (
    ("B1", "03", 6, (25, 70), False, "Fahrzeugbrand klein"),
    ("B1", "02", 5, (20, 60), False, "Flächenbrand klein"),
    ("B2", "04", 3, (30, 80), True, "Kaminbrand"),
    ("B2", "07", 14, (20, 55), False, "BMA"),
    ("B2", "08", 5, (45, 120), True, "Wohnungsbrand"),
    ("B3", "01", 2, (90, 240), True, "Gebäudebrand"),
    ("H1", "01", 20, (20, 70), False, "Technische Hilfeleistung klein"),
    ("H1", "02", 10, (25, 80), False, "Ölspur / Fahrbahnreinigung"),
    ("H2", "01", 6, (40, 120), False, "Verkehrsunfall, eingeklemmte Person"),
    ("H1", "05", 8, (20, 60), False, "Türöffnung Notfall"),
    ("S1", "00", 4, (120, 300), False, "Brandsicherheitswache"),
    ("U1", "01", 9, (30, 150), False, "Unwetter, Wasser im Keller"),
    ("B2", "06", 6, (15, 40), False, "Rauchwarnmelder"),
)


def make_config(name, code, places, fleet):
    """Fachkonfiguration einer Wehr; Funkrufnamen wie im BKS-Bericht (erfunden)."""
    vehicles = tuple(Vehicle(f"02/{number}", label=label, name=f"FL NR#.{code} 02/{number}-01")
                     for number, label in fleet)
    return TenantConfig(name=name, fleet=vehicles, unit_prefix=f"FL NR#.{code} ", own_prefix="02/",
                        unit_marker=f"FW NR#.{code} 02", places=places, plan_places=places[:2])


MUSTERSTADT = ("Feuerwehr Musterstadt", "MUS", ("Musterstadt", "Nebenhausen", "Probenhausen", "Demobach"),
               (("46", "HLF 20"), ("23", "TLF 3000"), ("34", "DLK 23/12"), ("41", "TSF"), ("19", "MTF")))
NEBENHAUSEN = ("Feuerwehr Nebenhausen", "NEB", ("Nebenhausen", "Demobach"),
                (("43", "LF 8"), ("71", "MZF 1"), ("19", "MTF")))


def _members(con, rng, count):
    """Erfundene Namen "Nachname, Vorname" (Kombination aus Platzhalterlisten, keine echten Personen)."""
    names = [f"{last}, {first}" for last in LAST_NAMES for first in FIRST_NAMES]
    rng.shuffle(names)
    ids = []
    for order, name in enumerate(names[:count], start=1):
        last, first = name.split(", ")
        ids.append(con.execute("INSERT INTO member (name, last_name, first_name, sort_order) VALUES (?,?,?,?)",
                               (name, last, first, order)).lastrowid)
    return ids


def _start_times(rng, year, count):
    """Einsatzbeginne über das Jahr: abends und am Wochenende etwas häufiger."""
    last = TODAY if year == TODAY.year else dt.date(year, 12, 31)
    days = (last - dt.date(year, 1, 1)).days + 1
    times = []
    for _ in range(count):
        day = dt.date(year, 1, 1) + dt.timedelta(days=rng.randrange(days))
        hour = rng.choices(range(24), weights=[2, 2, 2, 1, 1, 2, 3, 4, 5, 5, 5, 5, 5, 5, 5, 6, 6, 7, 7, 6, 5, 4, 3, 2])[0]
        times.append(dt.datetime.combine(day, dt.time(hour, rng.randrange(60), rng.randrange(60))))
    return sorted(times)


def _incident(con, rng, cfg, members, start, number, shared=None):
    """Einen Einsatz mit Fahrzeugen und Anwesenheit anlegen; shared = (Leitstellen-Nr., Berichts-Nr.) bei Gemeinschaftseinsätzen."""
    keyword, sub, _, (low, high), needs_breathing, text = rng.choices(KINDS, weights=[k[2] for k in KINDS])[0]
    aborted = keyword == "B2" and sub in ("07", "06") and rng.random() < 0.7   # meist Fehlalarm
    minutes = rng.randint(10, 25) if aborted else rng.randint(low, high)
    end = start + dt.timedelta(minutes=minutes)
    place = rng.choice(cfg.places)
    fields = {"number": number, "started_at": start.isoformat(), "ended_at": end.isoformat(),
              "keyword": keyword, "subcode": sub, "description": f"{text} / {rng.choice(STREETS)} {rng.randint(1, 40)}",
              "place": place, "unit_leader": "", "station_staff": rng.randint(0, 3),
              "dispatch_number": shared[0] if shared else f"{start:%y%m%d}{rng.randint(1000, 9999)}",
              "bks_record_id": shared[1] if shared else None}
    if aborted:
        fields["abort_reason"] = rng.choice(("Fehlalarm, Anlage zurückgesetzt", "Fehlalarm durch Staub", "Fehlalarm"))
    if sub == "07":
        fields["alarm_system"] = str(rng.choice((1204, 1318, 2207, 3101, 4410)))
        fields["building"] = rng.choice(("Pflegeheim", "Schule", "Gewerbepark", "Rathaus"))
    if keyword in ("B1", "B2", "B3") and not aborted and sub in ("02", "03", "04", "08", "01"):
        controlled = start + dt.timedelta(minutes=rng.randint(12, max(14, minutes - 5)))
        fields.update(fire_controlled_at=controlled.isoformat(), fire_out_at=(controlled + dt.timedelta(minutes=rng.randint(5, 25))).isoformat(),
                      tactic=rng.choice(("Innenangriff", "Außenangriff")), rescued=0, injured=0, deceased=0)
    incident_id = store.create_incident(con, fields, "demo", filename=f"{number:02d}-{start:%y}_{keyword}{sub}_Demo.pdf")

    # Fahrzeuge: je nach Art ein bis vier; Zeiten wie im Bericht (Ausrücken 2–9 Min., Anfahrt 3–12 Min.)
    count = 1 if keyword == "H1" and rng.random() < 0.5 else min(len(cfg.fleet), 2 + (keyword in ("B2", "B3", "H2")) + (keyword == "B3"))
    chosen = [cfg.fleet[0], *rng.sample(cfg.fleet[1:], count - 1)] if count > 1 else [rng.choice(cfg.fleet)]
    crew_pool = rng.sample(members, min(len(members), sum(rng.randint(3, 6) for _ in chosen)))
    crew_pool.reverse()
    for vehicle in chosen:
        crew = rng.randint(3, 6) if vehicle.label not in ("MTF", "MZF 1") else rng.randint(1, 3)
        alerted = start
        departed = alerted + dt.timedelta(minutes=rng.randint(2, 9), seconds=rng.randrange(60))
        arrived = departed + dt.timedelta(minutes=rng.randint(2, 11), seconds=rng.randrange(60))
        arrived = None if aborted and rng.random() < 0.4 else arrived
        store.add_vehicle(con, incident_id, vehicle.call_sign, vehicle.name, crew,
                          f"{departed:%H:%M:%S}", f"{arrived:%H:%M:%S}" if arrived else None,
                          alerted=f"{alerted:%H:%M:%S}", finished=f"{end:%H:%M:%S}", deployed=0 if aborted else 1,
                          respiratory=rng.randint(0, 2) if needs_breathing else 0)
        for role_no in range(min(crew, len(crew_pool))):
            member = crew_pool.pop()
            breathing = needs_breathing and role_no in (2, 3)
            store.add_attendance(con, incident_id, member, ROLES[role_no % len(ROLES)], vehicle.call_sign,
                                 agt=int(breathing), agt_min=rng.randint(8, 25) if breathing else None)
    return incident_id


def seed():
    """Legt VG und Wehren an, falls es die Demo-VG noch nicht gibt. Gibt True zurück, wenn etwas angelegt wurde."""
    tenancy.setup()
    with tenancy.central() as con:
        if con.execute("SELECT 1 FROM vg WHERE slug = ?", (VG_SLUG,)).fetchone():
            return False
        vg_id = tenancy.create_vg(con, VG_SLUG, VG_NAME)
        # Auftragsverarbeitung gilt als abgeschlossen, sonst wären die Wehren gesperrt
        con.execute("INSERT INTO dpa (vg_id, status) VALUES (?, 'signed')", (vg_id,))
    rng = random.Random(SEED)
    plans = (("musterstadt", MUSTERSTADT, {2025: 118, 2026: 104}, 28),
             ("nebenhausen", NEBENHAUSEN, {2025: 44, 2026: 39}, 16))
    joint = []   # Gemeinschaftseinsätze der ersten Wehr: (Beginn, Leitstellen-Nr., Berichts-Nr.)
    for slug, (name, code, places, fleet), per_year, member_count in plans:
        cfg = make_config(name, code, places, fleet)
        with tenancy.central() as con:
            tenancy.create_tenant(con, slug, name, vg_id, cfg)
        with db.connection(tenancy.tenant_path(slug)) as con:
            members = _members(con, rng, member_count)
            for year, count in per_year.items():
                starts = _start_times(rng, year, count)
                for number, start in enumerate(starts, start=1):
                    incident_id = _incident(con, rng, cfg, members, start, number)
                    if slug == "musterstadt" and rng.random() < 0.12:
                        row = con.execute("SELECT dispatch_number FROM incident WHERE id = ?", (incident_id,)).fetchone()
                        record = f"DEMO-{year}-{number:03d}"
                        con.execute("UPDATE incident SET bks_record_id = ? WHERE id = ?", (record, incident_id))
                        joint.append((start, row["dispatch_number"], record))
    # dieselben Einsätze noch einmal in der zweiten Wehr, mit gleicher Leitstellen- und Berichtsnummer
    with db.connection(tenancy.tenant_path("nebenhausen")) as con:
        cfg = make_config(*NEBENHAUSEN)
        members = [r["id"] for r in con.execute("SELECT id FROM member")]
        for start, dispatch, record in joint[::2]:
            _incident(con, rng, cfg, members, start, store.next_number(con, start.year), shared=(dispatch, record))
    return True


if __name__ == "__main__":
    print("Demo-Daten angelegt." if seed() else "Demo-Daten sind schon vorhanden.")
