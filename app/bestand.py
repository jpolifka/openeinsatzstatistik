# -*- coding: utf-8 -*-
"""Einsätze speichern, laden, ändern – und der einmalige Import aus der Einsatzübersicht."""
import datetime as dt, glob, json, logging, os, re, unicodedata

import openpyxl
from openpyxl.utils import column_index_from_string

from app import core
from app.feiertage import ist_wochenende_oder_feiertag

log = logging.getLogger("einsatzberichte")
BLOECKE = list(core.FAHRZEUG_SPALTEN)          # 02/45, 02/24, 02/71, 02/19, 01/10


# ---------------------------------------------------------------- Hilfsfunktionen
def _zeit_text(x):
    if isinstance(x, dt.datetime):
        x = x.time()
    return x.strftime("%H:%M:%S") if isinstance(x, dt.time) else None


def _iso(x):
    return x.isoformat(timespec="seconds") if isinstance(x, dt.datetime) else None


def _ganzzahl(x):
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, (int, float)):
        return int(x)
    if isinstance(x, str) and x.strip().isdigit():
        return int(x.strip())
    return None


def _name_teile(text):
    """'Nachname, Vorname' oder 'Vorname Nachname' -> (nachname, vorname)."""
    text = " ".join(text.split())
    if "," in text:
        n, v = [t.strip() for t in text.split(",", 1)]
        return n, v
    t = text.split()
    return (t[-1], " ".join(t[:-1])) if len(t) > 1 else (text, "")


# ---------------------------------------------------------------- Kameraden
class Kameraden:
    """Namensabgleich gegen alle bekannten Kameraden (Logik aus dem Script)."""

    def __init__(self, con):
        self.con = con
        self._laden()

    def _laden(self):
        zeilen = self.con.execute("SELECT id, name, vorname FROM kamerad").fetchall()
        self.vorname = {z["id"]: z["vorname"] for z in zeilen}
        self.abgleich = core.Namensabgleich([(z["id"], z["name"]) for z in zeilen]) if zeilen else None

    def finde(self, nachname, vorname):
        if not self.abgleich:
            return None
        kid = self.abgleich.finde(nachname, vorname)
        # Das Script ordnet bei eindeutigem Nachnamen ohne Blick auf den Vornamen zu –
        # ein neues Mitglied mit gleichem Nachnamen darf nicht beim Verwandten landen.
        if kid is not None and vorname and self.vorname.get(kid):
            a, b = core.norm(vorname)[:1], core.norm(self.vorname[kid])[:1]
            if a and b and a != b and core.norm(nachname)[:1] != b:
                return None
        return kid

    def finde_oder_anlegen(self, nachname, vorname, name=None):
        kid = self.finde(nachname, vorname)
        if kid is None:
            name = name or f"{nachname}, {vorname}".strip(", ")
            vorhanden = self.con.execute("SELECT id FROM kamerad WHERE name = ?", (name,)).fetchone()
            if vorhanden:
                return vorhanden["id"]
            kid = self.con.execute(
                "INSERT INTO kamerad (name, nachname, vorname, reihenfolge) "
                "VALUES (?, ?, ?, (SELECT COALESCE(MAX(reihenfolge), 0) + 1 FROM kamerad))",
                (name, nachname, vorname)).lastrowid
            self._laden()
        return kid


# ---------------------------------------------------------------- Laden
def einsaetze(con, jahr=None, ids=None):
    """Einsätze inkl. Fahrzeuge und Anwesenheit als Dicts."""
    sql, param = "SELECT * FROM einsatz", []
    if jahr is not None:
        sql, param = sql + " WHERE jahr = ?", [jahr]
    elif ids is not None:
        sql, param = sql + f" WHERE id IN ({','.join('?' * len(ids))})", list(ids)
    zeilen = [dict(z) for z in con.execute(sql + " ORDER BY jahr, nr IS NULL, nr, beginn", param)]
    if not zeilen:
        return []
    nach_id = {z["id"]: z for z in zeilen}
    for z in zeilen:
        z["hinweise"] = json.loads(z["hinweise"] or "[]")
        z["fahrzeuge"] = {}
        z["personen"] = []
    platz = ",".join("?" * len(nach_id))
    for f in con.execute(f"SELECT * FROM fahrzeug WHERE einsatz_id IN ({platz})", list(nach_id)):
        nach_id[f["einsatz_id"]]["fahrzeuge"][f["block"]] = dict(f)
    for p in con.execute(
            f"SELECT a.einsatz_id, a.funktion, a.fahrzeug, k.id, k.name, k.nachname, k.vorname "
            f"FROM anwesenheit a JOIN kamerad k ON k.id = a.kamerad_id "
            f"WHERE a.einsatz_id IN ({platz}) ORDER BY k.reihenfolge, k.name", list(nach_id)):
        nach_id[p["einsatz_id"]]["personen"].append(dict(p))
    return zeilen


def einsatz(con, eid):
    e = einsaetze(con, ids=[eid])
    return e[0] if e else None


def jahre(con):
    return [dict(z) for z in con.execute(
        "SELECT jahr, COUNT(*) AS anzahl, MAX(nr) AS letzte_nr FROM einsatz GROUP BY jahr ORDER BY jahr")]


def finde(con, jahr, nr):
    if nr is None:
        return None
    z = con.execute("SELECT id FROM einsatz WHERE jahr = ? AND nr = ?", (jahr, nr)).fetchone()
    return z["id"] if z else None


# ---------------------------------------------------------------- Speichern
FELDER = ("nr", "beginn", "ende", "stichwort", "stufe", "einsatz", "ort", "ehf", "personen_gh")


def aus_bericht(b):
    """Geparsten Bericht (core.berechne) in Datenbank-Felder übersetzen."""
    return {
        "nr": b["nr"], "beginn": _iso(b["beginn"]), "ende": _iso(b["ende"]),
        "stichwort": b["stichwort"], "stufe": b["stufe"], "einsatz": b["einsatz_text"],
        "ort": b["ort_liste"], "ehf": b["ehf"], "personen_gh": b["personen_gh"],
    }


def _normieren(felder):
    f = {k: felder.get(k) for k in FELDER}
    f["nr"] = _ganzzahl(f["nr"])
    f["personen_gh"] = _ganzzahl(f["personen_gh"]) or 0
    for k in ("beginn", "ende"):
        if f[k]:
            f[k] = dt.datetime.fromisoformat(f[k]).isoformat(timespec="seconds")
    for k in ("stichwort", "stufe", "einsatz", "ort", "ehf"):
        f[k] = (f[k] or "").strip()
    beginn = dt.datetime.fromisoformat(f["beginn"]) if f["beginn"] else None
    f["jahr"] = beginn.year if beginn else dt.date.today().year
    f["wochenende"] = int(bool(beginn and ist_wochenende_oder_feiertag(beginn.date())))
    return f


def speichern_bericht(con, b, felder, ersetzen_id=None):
    """Einsatz aus PDF anlegen (oder einen vorhandenen ersetzen)."""
    f = _normieren(felder)
    if ersetzen_id:
        con.execute("DELETE FROM einsatz WHERE id = ?", (ersetzen_id,))
    elif finde(con, f["jahr"], f["nr"]):
        raise ValueError(f"Einsatz Nr. {f['nr']}/{f['jahr']} ist bereits vorhanden.")
    eid = con.execute(
        "INSERT INTO einsatz (jahr, nr, beginn, ende, stichwort, stufe, einsatz, ort, ehf, personen_gh, "
        "wochenende, quelle, datei, hinweise) VALUES (?,?,?,?,?,?,?,?,?,?,?, 'pdf', ?, ?)",
        (f["jahr"], f["nr"], f["beginn"], f["ende"], f["stichwort"], f["stufe"], f["einsatz"], f["ort"],
         f["ehf"], f["personen_gh"], f["wochenende"], b["datei"], json.dumps(b["hinweise"], ensure_ascii=False))
    ).lastrowid
    for kenn, fz in b["bloecke"].items():
        con.execute("INSERT INTO fahrzeug VALUES (?,?,?,?,?,?)",
                    (eid, kenn, fz["name"], fz["staerke"], _zeit_text(fz["aus"]), _zeit_text(fz["ein"])))
    kam = Kameraden(con)
    for p in b["personen"]:
        kid = kam.finde_oder_anlegen(p["nachname"], p["vorname"])
        con.execute("INSERT OR IGNORE INTO anwesenheit VALUES (?,?,?,?)",
                    (eid, kid, p["funktion"] or None, p["fahrzeug"]))
    return eid


def aendern(con, eid, felder):
    alt = con.execute("SELECT * FROM einsatz WHERE id = ?", (eid,)).fetchone()
    if not alt:
        raise KeyError(eid)
    f = _normieren({**dict(alt), **felder})
    andere = finde(con, f["jahr"], f["nr"])
    if andere and andere != eid:
        raise ValueError(f"Einsatz Nr. {f['nr']}/{f['jahr']} ist bereits vorhanden.")
    con.execute(
        "UPDATE einsatz SET jahr=?, nr=?, beginn=?, ende=?, stichwort=?, stufe=?, einsatz=?, ort=?, ehf=?, "
        "personen_gh=?, wochenende=?, geaendert=datetime('now','localtime') WHERE id=?",
        (f["jahr"], f["nr"], f["beginn"], f["ende"], f["stichwort"], f["stufe"], f["einsatz"], f["ort"],
         f["ehf"], f["personen_gh"], f["wochenende"], eid))


def loeschen(con, eid):
    con.execute("DELETE FROM einsatz WHERE id = ?", (eid,))


# ---------------------------------------------------------------- Import Einsatzübersicht
def _zeit(x):
    if isinstance(x, dt.datetime):
        return x.time()
    return x if isinstance(x, dt.time) else None


def _dauer(x):
    if isinstance(x, dt.timedelta):
        return x
    if isinstance(x, dt.time):
        return dt.timedelta(hours=x.hour, minutes=x.minute, seconds=x.second)
    if isinstance(x, (int, float)):
        return dt.timedelta(days=float(x))
    return None


def importiere_excel(con, pfad):
    """Einsatzübersicht_JJJJ.xlsx einlesen. Bereits vorhandene Nummern werden übersprungen."""
    wb = openpyxl.load_workbook(pfad, data_only=True)
    ue = wb.worksheets[0]
    anw = next((ws for ws in wb.worksheets if ws.title.lower().startswith("anwesenheit")), None)
    sp = lambda buchstabe: column_index_from_string(buchstabe)

    neu, uebersprungen, nr_zu_id = 0, 0, {}
    for r in range(4, ue.max_row + 1):
        datum = ue.cell(r, 2).value
        if not isinstance(datum, dt.datetime):
            continue
        w = lambda b: ue.cell(r, sp(b)).value
        nr = _ganzzahl(w("A"))
        e_zeit, f_zeit = _zeit(w("E")), _zeit(w("F"))
        beginn = dt.datetime.combine(datum.date(), e_zeit) if e_zeit else dt.datetime.combine(datum.date(), dt.time())
        dauer = _dauer(w("G"))
        if dauer is not None:
            ende = beginn + dauer
        elif f_zeit:
            ende = dt.datetime.combine(datum.date(), f_zeit)
            ende += dt.timedelta(days=1) if ende < beginn else dt.timedelta()
        else:
            ende = None
        jahr = datum.year
        if finde(con, jahr, nr):
            uebersprungen += 1
            nr_zu_id[nr] = None
            continue
        eid = con.execute(
            "INSERT INTO einsatz (jahr, nr, beginn, ende, stichwort, stufe, einsatz, ort, ehf, personen_gh, "
            "wochenende, quelle, datei) VALUES (?,?,?,?,?,?,?,?,?,?,?, 'excel', ?)",
            (jahr, nr, _iso(beginn), _iso(ende), str(w("H") or "").strip(), str(w("I") or "").strip(),
             str(w("J") or "").strip(), str(w("K") or "").strip(), str(w("L") or "").strip(),
             _ganzzahl(w("AL")) or 0,
             _ganzzahl(w("AV")) if _ganzzahl(w("AV")) is not None else int(ist_wochenende_oder_feiertag(datum.date())),
             os.path.basename(pfad))).lastrowid
        for kenn, (s, a, e) in core.FAHRZEUG_SPALTEN.items():
            staerke, aus, ein = _ganzzahl(w(s)), _zeit(w(a)), _zeit(w(e))
            if staerke or aus or ein:
                con.execute("INSERT INTO fahrzeug VALUES (?,?,?,?,?,?)",
                            (eid, kenn, None, staerke, _zeit_text(aus), _zeit_text(ein)))
        nr_zu_id[nr] = eid
        neu += 1

    personen = 0
    if anw:
        kam = Kameraden(con)
        kopf = []
        for c in anw[3]:
            if c.column >= 6 and isinstance(c.value, str) and c.value.strip():
                if c.value.strip() in ("Stärke", "Gesamtstunden"):
                    break
                n, v = _name_teile(c.value)
                kopf.append((c.column, kam.finde_oder_anlegen(n, v, name=" ".join(c.value.split()))))
        for r in range(4, anw.max_row + 1):
            eid = nr_zu_id.get(_ganzzahl(anw.cell(r, 1).value))
            if not eid:
                continue
            for col, kid in kopf:
                if _ganzzahl(anw.cell(r, col).value) == 1:
                    con.execute("INSERT OR IGNORE INTO anwesenheit (einsatz_id, kamerad_id) VALUES (?,?)", (eid, kid))
                    personen += 1
    log.info("Import %s: %d Einsätze neu, %d übersprungen, %d Anwesenheiten", pfad, neu, uebersprungen, personen)
    return {"datei": os.path.basename(pfad), "neu": neu, "uebersprungen": uebersprungen, "anwesenheiten": personen}


def erstimport(con, ordner):
    """Beim ersten Start alle Einsatzübersicht_JJJJ.xlsx aus dem Import-Ordner übernehmen."""
    if con.execute("SELECT COUNT(*) FROM einsatz").fetchone()[0]:
        return []
    dateien = []
    for p in glob.glob(os.path.join(ordner, "**", "*.xlsx"), recursive=True):
        name = unicodedata.normalize("NFC", os.path.basename(p))
        if re.match(r"Einsatzübersicht_20\d\d\.xlsx$", name):
            dateien.append(p)
    return [importiere_excel(con, p) for p in sorted(dateien)]
