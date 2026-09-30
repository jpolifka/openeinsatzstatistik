# -*- coding: utf-8 -*-
"""
Einsatzberichte – Weboberfläche mit eigener Datenbank und Auswertung.

Die PDF-Auswertung (lies_pdf, berechne) kommt unverändert aus core.py
(= einsatzberichte_import.py). Die Einsätze liegen in SQLite (bestand.py), die
Auswertungen der Einsatzübersicht werden in berechnung.py nachgerechnet.

Beim ersten Start werden die vorhandenen Einsatzübersicht_JJJJ.xlsx aus IMPORT_ORDNER
übernommen; danach kommen neue Einsätze per PDF dazu.
"""
import base64, copy, datetime as dt, io, logging, os, re, secrets, tempfile, threading, time, unicodedata, uuid
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import bestand, berechnung, core, db
from app.feiertage import feiertage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("einsatzberichte")

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(BASIS, "static")
IMPORT_ORDNER = os.environ.get("IMPORT_ORDNER", "/import")
BENUTZER = os.environ.get("APP_BENUTZER", "feuerwehr")
PASSWORT = os.environ.get("APP_PASSWORT", "")
SITZUNG_TTL = 60 * 60
MAX_DAUER_H = 24

app = FastAPI(title="Einsatzberichte – FF Rheinbrohl")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_sitzungen = {}
_lock = threading.Lock()


@app.on_event("startup")
def start():
    db.einrichten()
    if os.path.isdir(IMPORT_ORDNER):
        with db.verbindung() as con:
            for erg in bestand.erstimport(con, IMPORT_ORDNER):
                log.info("Erstimport: %s", erg)


@app.middleware("http")
async def anmeldung(request: Request, call_next):
    """Einfacher Passwortschutz (HTTP Basic), wenn APP_PASSWORT gesetzt ist."""
    if PASSWORT and request.url.path != "/health":
        kopf = request.headers.get("authorization", "")
        ok = False
        if kopf.lower().startswith("basic "):
            try:
                user, _, pw = base64.b64decode(kopf[6:]).decode("utf-8").partition(":")
                ok = secrets.compare_digest(user, BENUTZER) and secrets.compare_digest(pw, PASSWORT)
            except Exception:
                ok = False
        if not ok:
            return Response("Anmeldung erforderlich", status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="Einsatzberichte", charset="UTF-8"'})
    return await call_next(request)


# ---------------------------------------------------------------- Hilfsfunktionen
class _AlleFeiertage:
    """Für core.berechne: 'datum in feiertage' für jedes Jahr."""
    def __contains__(self, d):
        return d in feiertage(d.year)


def _sicherer_name(name):
    name = unicodedata.normalize("NFC", name or "").replace("\\", "/").split("/")[-1]
    return re.sub(r"[^\w.\- äöüÄÖÜß()]", "_", name) or "datei"


def _nummer_ergaenzen(b):
    """Einsatz-Nr. ergänzen, wenn das Script sie nicht erkennt.

    Manche Berichte schreiben "17-25" statt "17/25", bei anderen fehlt das Feld
    ganz – dann bleibt nur die Nr. vorn im Dateinamen ("61-25_B1_....pdf").
    """
    datei = re.match(r"(\d{1,3})[-_/](\d\d)(?!\d)", b["datei"])
    datei_nr = int(datei.group(1)) if datei else None
    if b["nr"] is None:
        m = re.match(r"(\d+)\s*-\s*(\d+)", b["nr_text"])
        if m:
            b["nr"] = int(m.group(1))
        elif datei_nr is not None:
            b["nr"] = datei_nr
            b["hinweise"].append(f"Einsatzbericht-Nr. fehlt im PDF – Nr. {datei_nr} aus Dateiname übernommen")
    if b["nr"] is not None and datei_nr is not None and b["nr"] != datei_nr:
        b["hinweise"].append(f"Nr. im PDF ({b['nr']}) weicht vom Dateinamen ({datei_nr}) ab")


def _plausibilitaet(b):
    """Zusätzliche Prüfhinweise, die das Script selbst nicht erzeugt."""
    if b["nr"] is None:
        b["hinweise"].append("Einsatzbericht-Nr. nicht erkannt")
    if b["beginn"] and b["ende"]:
        if b["ende"] < b["beginn"]:
            b["hinweise"].append("Einsatzende liegt vor Einsatzbeginn – Datum im Bericht prüfen")
        elif b["ende"] - b["beginn"] > dt.timedelta(hours=MAX_DAUER_H):
            b["hinweise"].append(f"Einsatzdauer über {MAX_DAUER_H} Stunden – bitte prüfen")
    if not b["personen"]:
        b["hinweise"].append("Anwesenheitsliste leer")


def _runden(x, stellen=1):
    return round(x, stellen) if isinstance(x, float) else x


def _einsatz_json(e, grenze=8):
    k = berechnung.kennzahlen(e, grenze)
    fahrzeuge = []
    for kenn in bestand.BLOECKE:
        f, kf = e["fahrzeuge"].get(kenn), k["fahrzeuge"].get(kenn)
        fahrzeuge.append({"block": kenn, "name": f["name"] if f else None,
                          "staerke": f["staerke"] if f else None,
                          "aus": f["aus"] if f else None, "ein": f["ein"] if f else None,
                          "azeit": _runden(kf["azeit"]) if kf else None,
                          "ezeit": _runden(kf["ezeit"]) if kf else None})
    return {
        **{f: e.get(f) for f in ("id", "jahr", "nr", "beginn", "ende", "stichwort", "stufe", "einsatz", "ort",
                                 "ehf", "personen_gh", "quelle", "datei", "hinweise")},
        "wochenende": bool(e.get("wochenende")),
        "tag": k["tag"], "dauer_min": _runden(k["dauer_min"]),
        "azeit": _runden(k["azeit"]), "ezeit": _runden(k["ezeit"]), "erreicht": k["erreicht"],
        "staerke_eintreffen": k["staerke_eintreffen"], "staerke_grenze": k["staerke_grenze"],
        "staerke_15": k["staerke_15"], "staerke_gesamt": k["staerke_gesamt"],
        "fahrzeuge": fahrzeuge,
        "personen": [{"id": p["id"], "name": p["name"], "funktion": p.get("funktion"),
                      "fahrzeug": p.get("fahrzeug"), "neu": p.get("neu", False)} for p in e["personen"]],
    }


def _als_einsatz(b, felder):
    """Geparsten Bericht in die Form bringen, die kennzahlen() erwartet (für die Vorschau)."""
    zt = bestand._zeit_text
    return {**felder, "wochenende": 0,
            "fahrzeuge": {k: {"name": f["name"], "staerke": f["staerke"], "aus": zt(f["aus"]), "ein": zt(f["ein"])}
                          for k, f in b["bloecke"].items()},
            "personen": b["personen"]}


def _vergleich(alt, neu):
    """Unterschiede zwischen gespeichertem Einsatz und PDF (Zeiten minutengenau)."""
    def kurz(feld, x):
        if x in (None, ""):
            return "–"
        if feld in ("beginn", "ende"):
            return dt.datetime.fromisoformat(x).strftime("%d.%m.%Y %H:%M")
        if feld.endswith((".aus", ".ein")):
            return x[:5]
        return str(x)
    namen = {"nr": "Nr.", "beginn": "Beginn", "ende": "Ende", "stichwort": "Stichwort", "stufe": "Stufe",
             "ort": "Ort", "ehf": "EHF", "personen_gh": "Personen Gerätehaus"}
    diffs = []
    for f, n in namen.items():
        a, b = kurz(f, alt.get(f)), kurz(f, neu.get(f))
        if a != b:
            diffs.append({"feld": n, "liste": a, "pdf": b})
    for kenn in bestand.BLOECKE:
        fa, fb = alt["fahrzeuge"].get(kenn) or {}, neu["fahrzeuge"].get(kenn) or {}
        for teil, n in (("staerke", "Stärke"), ("aus", "Ausrücken"), ("ein", "Eintreffen")):
            a, b = kurz(f"{kenn}.{teil}", fa.get(teil)), kurz(f"{kenn}.{teil}", fb.get(teil))
            if a != b:
                diffs.append({"feld": f"{n} {kenn}", "liste": a, "pdf": b})
    if len(alt["personen"]) != len(neu["personen"]):
        diffs.append({"feld": "Anwesende", "liste": str(len(alt["personen"])), "pdf": str(len(neu["personen"]))})
    return diffs


def _aufraeumen():
    grenze = time.time() - SITZUNG_TTL
    with _lock:
        for k in [k for k, s in _sitzungen.items() if s["zeit"] < grenze]:
            del _sitzungen[k]


def _jahr_oder_aktuell(con, jahr):
    if jahr:
        return jahr
    j = bestand.jahre(con)
    return j[-1]["jahr"] if j else dt.date.today().year


# ---------------------------------------------------------------- Seiten
@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------- Auswertung
@app.get("/api/jahre")
def api_jahre():
    with db.verbindung() as con:
        return {"jahre": bestand.jahre(con), "heute": dt.date.today().isoformat()}


@app.get("/api/auswertung")
def api_auswertung(jahr: Optional[int] = None, grenze: int = 8):
    if grenze not in (8, 10):
        raise HTTPException(400, "Grenze muss 8 oder 10 Minuten sein.")
    with db.verbindung() as con:
        jahr = _jahr_oder_aktuell(con, jahr)
        liste = bestand.einsaetze(con, jahr=jahr)
        vj = bestand.einsaetze(con, jahr=jahr - 1) or None
    return {"jahr": jahr,
            "statistik": berechnung.statistik(liste, jahr, vj),
            "bedarfsplan": berechnung.bedarfsplan(liste, grenze),
            "bedarfsplan_vorjahr": berechnung.bedarfsplan(vj, grenze) if vj else None,
            "anwesenheit": berechnung.anwesenheit(liste)}


# ---------------------------------------------------------------- Einsätze
@app.get("/api/einsaetze")
def api_einsaetze(jahr: Optional[int] = None):
    with db.verbindung() as con:
        jahr = _jahr_oder_aktuell(con, jahr)
        return {"jahr": jahr, "einsaetze": [_einsatz_json(e) for e in bestand.einsaetze(con, jahr=jahr)]}


class Felder(BaseModel):
    nr: Optional[int] = None
    beginn: Optional[str] = None
    ende: Optional[str] = None
    stichwort: Optional[str] = None
    stufe: Optional[str] = None
    einsatz: Optional[str] = None
    ort: Optional[str] = None
    ehf: Optional[str] = None
    personen_gh: Optional[int] = None


@app.put("/api/einsatz/{eid}")
def api_aendern(eid: int, felder: Felder):
    with db.verbindung() as con:
        try:
            bestand.aendern(con, eid, felder.model_dump(exclude_unset=True))
        except KeyError:
            raise HTTPException(404, "Einsatz nicht gefunden.")
        except ValueError as e:
            raise HTTPException(409, str(e))
        return _einsatz_json(bestand.einsatz(con, eid))


@app.delete("/api/einsatz/{eid}")
def api_loeschen(eid: int):
    with db.verbindung() as con:
        bestand.loeschen(con, eid)
    return {"ok": True}


# ---------------------------------------------------------------- PDF einlesen
@app.post("/api/pdf")
def api_pdf(pdfs: List[UploadFile] = File(...)):
    _aufraeumen()
    pdfs = [p for p in pdfs if p.filename.lower().endswith(".pdf")]
    if not pdfs:
        raise HTTPException(400, "Bitte eine PDF-Datei (Einsatzbericht aus dem BKS-Portal) auswählen.")
    berichte, fehler = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for up in pdfs:
            pfad = os.path.join(tmp, _sicherer_name(up.filename))
            with open(pfad, "wb") as fh:
                fh.write(up.file.read())
            try:
                b = core.lies_pdf(pfad)
                _nummer_ergaenzen(b)
                b = core.berechne(b, _AlleFeiertage())
                _plausibilitaet(b)
                berichte.append(b)
            except Exception as e:
                log.exception("PDF %s", up.filename)
                fehler.append({"datei": _sicherer_name(up.filename), "meldung": str(e) or type(e).__name__})

    token = uuid.uuid4().hex
    vorschau = []
    with db.verbindung() as con:
        kam = bestand.Kameraden(con)
        for b in berichte:
            felder = bestand.aus_bericht(b)
            e = _als_einsatz(b, felder)
            e["personen"] = []
            for p in b["personen"]:
                kid = kam.finde(p["nachname"], p["vorname"])
                name = con.execute("SELECT name FROM kamerad WHERE id=?", (kid,)).fetchone()["name"] if kid else \
                    f"{p['nachname']}, {p['vorname']}"
                e["personen"].append({"id": kid, "name": name, "funktion": p["funktion"], "fahrzeug": p["fahrzeug"],
                                      "neu": kid is None})
            jahr = b["beginn"].year if b["beginn"] else dt.date.today().year
            vorhanden_id = bestand.finde(con, jahr, b["nr"])
            vorhanden = bestand.einsatz(con, vorhanden_id) if vorhanden_id else None
            j = _einsatz_json({**e, "id": None, "jahr": jahr, "quelle": "pdf", "datei": b["datei"],
                               "hinweise": b["hinweise"],
                               "wochenende": bool(b["wochenende"])})
            j["meldebild"] = b["meldebild"]
            j["einsatzleiter"] = b["einsatzleiter"]
            j["vorhanden"] = {"id": vorhanden_id, "quelle": vorhanden["quelle"],
                              "abweichungen": _vergleich(vorhanden, e)} if vorhanden else None
            vorschau.append(j)
    with _lock:
        _sitzungen[token] = {"zeit": time.time(), "berichte": {b["datei"]: b for b in berichte}}
    return {"token": token, "berichte": vorschau, "fehler": fehler}


class Uebernahme(BaseModel):
    token: str
    datei: str
    felder: Felder
    ersetzen: bool = False


@app.post("/api/pdf/uebernehmen")
def api_uebernehmen(u: Uebernahme):
    with _lock:
        s = _sitzungen.get(u.token)
    b = s and s["berichte"].get(u.datei)
    if not b:
        raise HTTPException(410, "Die Vorschau ist abgelaufen – bitte die PDF erneut einlesen.")
    felder = {**bestand.aus_bericht(b), **u.felder.model_dump(exclude_unset=True)}
    with db.verbindung() as con:
        beginn = dt.datetime.fromisoformat(felder["beginn"]) if felder.get("beginn") else None
        ersetzen_id = bestand.finde(con, beginn.year if beginn else dt.date.today().year,
                                    felder.get("nr")) if u.ersetzen else None
        try:
            eid = bestand.speichern_bericht(con, copy.deepcopy(b), felder, ersetzen_id)
        except ValueError as e:
            raise HTTPException(409, str(e))
        return _einsatz_json(bestand.einsatz(con, eid))


# ---------------------------------------------------------------- Export
def _als_bericht(e):
    """Gespeicherten Einsatz in die Form von core.berechne bringen (für core.schreibe)."""
    beginn, ende = (dt.datetime.fromisoformat(x) if x else None for x in (e["beginn"], e["ende"]))
    tag = beginn.date() if beginn else dt.date.today()
    zeit = lambda t: dt.datetime.combine(tag, dt.time.fromisoformat(t)) if t else None
    return {
        "nr": e["nr"], "beginn": beginn, "ende": ende, "stichwort": e["stichwort"], "stufe": e["stufe"],
        "einsatz_text": e["einsatz"], "ort_liste": e["ort"], "ehf": e["ehf"], "personen_gh": e["personen_gh"],
        "wochenende": e["wochenende"], "datei": e["datei"] or "", "hinweise": list(e["hinweise"]),
        "bloecke": {k: {"staerke": f["staerke"], "aus": zeit(f["aus"]), "ein": zeit(f["ein"])}
                    for k, f in e["fahrzeuge"].items()},
        "personen": [{"nachname": p["nachname"], "vorname": p["vorname"]} for p in e["personen"]],
    }


@app.get("/api/export")
def api_export(jahr: Optional[int] = None, ids: Optional[str] = None):
    """Excel im Format der Einsatzübersicht (Spalten A:AV + Anwesenheit), erzeugt mit core.schreibe."""
    with db.verbindung() as con:
        jahr = _jahr_oder_aktuell(con, jahr)
        liste = bestand.einsaetze(con, jahr=jahr)
        if ids:
            gewaehlt = {int(i) for i in ids.split(",") if i.strip().isdigit()}
            liste = [e for e in liste if e["id"] in gewaehlt]
        kameraden = con.execute(
            "SELECT DISTINCT k.id, k.name FROM kamerad k JOIN anwesenheit a ON a.kamerad_id = k.id "
            "JOIN einsatz e ON e.id = a.einsatz_id WHERE e.jahr = ? ORDER BY k.reihenfolge, k.name", (jahr,)).fetchall()
    if not liste:
        raise HTTPException(404, "Keine Einsätze für den Export.")
    vorlage = {"kopf": [(6 + i, k["name"]) for i, k in enumerate(kameraden)], "blatt": f"Einsatzübersicht_{jahr}"}
    buf = io.BytesIO()
    core.schreibe([_als_bericht(e) for e in liste], vorlage, buf, [])
    buf.seek(0)
    name = f"Einsaetze_{jahr}_{dt.datetime.now():%Y-%m-%d_%H%M}.xlsx" if not ids else \
        f"Import_Einsatzberichte_{dt.datetime.now():%Y-%m-%d_%H%M}.xlsx"
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"'})
