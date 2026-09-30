# -*- coding: utf-8 -*-
"""
Einsatzberichte (BKS-Portal RLP, PDF) automatisch einlesen
===========================================================
Liest alle Einsatzbericht-PDFs eines Ordners aus und erzeugt eine Import-Datei,
deren Spalten 1:1 dem Aufbau der "Einsatzübersicht_2026.xlsx" entsprechen
(Blatt Einsatzübersicht A:AV und Blatt Anwesenheit F:AS).

Die Original-Einsatzübersicht wird NUR GELESEN (Namen der Kameraden, Feiertage,
bereits erfasste Einsätze) und nie verändert – so bleiben Diagramme, Tabellen
und Formeln darin garantiert erhalten.

Aufruf (oder einfach "Einsatzberichte_einlesen.bat" doppelklicken):
    python einsatzberichte_import.py                  -> nur neue Einsätze
    python einsatzberichte_import.py --alle           -> alle PDFs
    python einsatzberichte_import.py "C:\\...\\54-26_....pdf"  -> nur diese PDF(s) (auch Drag & Drop auf die .bat)
    python einsatzberichte_import.py --pdf-ordner "C:\\...\\2026" --vorlage "C:\\...\\Einsatzübersicht_2026.xlsx"

Benötigt: Python 3.9+, pdfplumber, openpyxl   (pip install pdfplumber openpyxl)
"""
import argparse, datetime as dt, difflib, glob, os, re, sys, unicodedata

try:
    import pdfplumber
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.comments import Comment
except ImportError:
    sys.exit("Fehlende Pakete. Bitte einmalig ausführen:  pip install pdfplumber openpyxl")

# ---------------------------------------------------------------- Einstellungen
# Fahrzeug -> Spaltenblock in der Einsatzübersicht (Stärke, Ausrücken, Eintreffen)
FAHRZEUG_SPALTEN = {
    "02/45": ("M", "N", "P"),
    "02/24": ("R", "S", "U"),
    "02/71": ("W", "X", "Z"),
    "02/19": ("AB", "AC", "AE"),
    "01/10": ("AG", "AH", "AJ"),
}
# Ersatzfahrzeuge, die bei Werkstattaufenthalt in den Block eines anderen gehen
ERSATZ_FUER = {"01/23": "02/45"}
BEKANNTE_ORTE = ["Rheinbrohl", "Arienheller", "Hammerstein", "Ariendorf",
                 "Bad Hönningen", "Leutesdorf"]
ZEIT_RE = r"(\d\d\.\d\d\.\d\d \d\d:\d\d:\d\d)"


# ---------------------------------------------------------------- Hilfsfunktionen
def norm(s):
    s = (s or "").lower().replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if c.isalnum())


def zeit(s):
    return dt.datetime.strptime(s, "%d.%m.%y %H:%M:%S") if s else None


def kurzname(vorname, nachname):
    kurz = "Ch" if vorname.lower().startswith("ch") else vorname[:1]
    return f"{kurz}. {nachname}"


def feld(text, label):
    m = re.search(re.escape(label) + r":\s*(.*)", text)
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------- PDF auslesen
def lies_pdf(pfad):
    with pdfplumber.open(pfad) as pdf:
        seiten = [p.extract_text() or "" for p in pdf.pages]
        p1 = pdf.pages[0]
        links = p1.crop((0, 0, p1.width * 0.495, p1.height)).extract_text() or ""
        rechts = p1.crop((p1.width * 0.495, 0, p1.width, p1.height)).extract_text() or ""
    voll = "\n".join(seiten)
    b = {"datei": os.path.basename(pfad), "hinweise": []}

    nr = feld(voll, "Einsatzbericht-Nr.")
    m = re.match(r"(\d+)\s*/\s*(\d+)", nr)
    b["nr"] = int(m.group(1)) if m else None
    b["nr_text"] = nr

    stw = feld(links, "Einsatzstichwort") or feld(voll, "Einsatzstichwort")
    m = re.match(r"([A-Z])(\d)\.(\d\d)", stw)
    if m:
        b["stichwort"], b["stufe"] = m.group(1) + m.group(2), m.group(3)
    elif "sicherheitswache" in stw.lower():
        b["stichwort"], b["stufe"] = "S1", "00"
    else:
        b["stichwort"], b["stufe"] = stw, ""
        b["hinweise"].append(f"Stichwort '{stw}' nicht erkannt")

    b["meldebild"] = feld(links, "Meldebild")
    b["anlass"] = feld(links, "Einsatzstelle - Bemerkung Einsatzanlass")
    b["ort"] = feld(links, "Einsatzstelle - Ort")
    b["ortsteil"] = re.sub(r"\s*\(.*\)\s*$", "", feld(links, "Einsatzstelle - Ortsteil"))
    b["strasse"] = feld(links, "Einsatzstelle - Straße")
    b["objekt"] = feld(links, "Einsatzstelle - Objekt") or feld(rechts, "Einsatzstelle - Objekt")
    b["einsatzleiter"] = feld(voll, "Einsatzleiter")
    m = re.search(r"Zeitpunkt der Alarmierung der ersten Einheit:\s*(\d\d\.\d\d\.\d{4} \d\d:\d\d)", voll)
    b["erste_alarmierung"] = dt.datetime.strptime(m.group(1), "%d.%m.%Y %H:%M") if m else None

    # Fahrzeugtabelle
    b["fahrzeuge"] = []
    for zeile in voll.splitlines():
        m = re.match(r"^(FL NR#\.\w+(?: \d\d/\d\d-\d\d)?|WW [\d/-]+|KO [\d/-]+|H CH \d+)\s+"
                     r"(\d+) / (\d+) / (\d+) / (\d+) / (\d+)\s+(.*)$", zeile)
        if not m:
            continue
        rest = re.findall(ZEIT_RE + r"\d?|(?<!\S)(-)(?!\S)|\b(Ja|Nein)\b", m.group(7))
        werte = [z or s or j for z, s, j in rest]
        if len(werte) < 6:
            b["hinweise"].append(f"Fahrzeugzeile unvollständig: {zeile[:60]}")
            werte += ["-"] * (6 - len(werte))
        alarm, aus, ein, eingesetzt, rueck, ende = werte[:6]
        f = lambda v: zeit(v) if v not in ("-", "Ja", "Nein") else None
        kenn = re.search(r"^FL NR#\.BHÖ (\d\d/\d\d)-\d\d", m.group(1))
        b["fahrzeuge"].append({
            "name": m.group(1), "kenn": kenn.group(1) if kenn else None,
            "staerke": int(m.group(5)), "agt": int(m.group(6)),
            "alarm": f(alarm), "aus": f(aus), "ein": f(ein), "ende": f(ende),
        })

    # Anwesenheitsliste
    b["personen"] = []
    teil = voll.split("Anwesenheitsliste:", 1)[-1]
    teil = teil.split("Unterschriften zu Einsatzbericht")[0]
    for zeile in teil.splitlines():
        m = re.match(r"^(\S+) (\S+)(.*?)\s(nein|ja|AGT)\s(\d+)\s*(.*)$", zeile)
        if not m or m.group(1) in ("Name", "FW", "EINSATZBERICHT"):
            continue
        mitte = m.group(3)
        fzg = re.search(r"FL NR#\.\w+ (\d\d/\d\d)-\d\d", mitte)
        funktion = re.sub(r"FL NR#\.\S+ \S+|\d\d\.\d\d\.\d\d \d\d:\d\d", "", mitte).strip()
        b["personen"].append({"nachname": m.group(1), "vorname": m.group(2),
                              "fahrzeug": fzg.group(1) if fzg else None,
                              "funktion": funktion})
    return b


# ---------------------------------------------------------------- Zuordnung
def fahrzeug_bloecke(b):
    """Ordnet Fahrzeuge den Spaltenblöcken zu (inkl. Ersatzfahrzeuge)."""
    bloecke = {}
    eigene_fzg = {p["fahrzeug"] for p in b["personen"] if p["fahrzeug"]}
    for f in b["fahrzeuge"]:
        if f["kenn"] in FAHRZEUG_SPALTEN:
            bloecke[f["kenn"]] = f
    for f in b["fahrzeuge"]:
        ziel = ERSATZ_FUER.get(f["kenn"])
        if ziel and ziel not in bloecke and f["kenn"] in eigene_fzg:
            bloecke[ziel] = f
            b["hinweise"].append(f"{f['name']} als Ersatz für {ziel} eingetragen")
    rest = [f["name"] for f in b["fahrzeuge"]
            if f["name"].startswith("FL NR#.BHÖ 02/") and f not in bloecke.values()]
    if rest:
        b["hinweise"].append("Nicht in Liste abgebildete Fahrzeuge: " + ", ".join(rest))
    return bloecke


def berechne(b, feiertage):
    bl = fahrzeug_bloecke(b)
    b["bloecke"] = bl
    eigene = [f for f in b["fahrzeuge"] if f["name"].startswith("FL NR#.BHÖ 02/")] or \
             [f for f in b["fahrzeuge"] if f["kenn"]]
    alarme = [f["alarm"] for f in eigene if f["alarm"]] or \
             [f["alarm"] for f in bl.values() if f["alarm"]]
    beginn = min(alarme) if alarme else b["erste_alarmierung"]
    enden = [f["ende"] for f in b["fahrzeuge"]
             if f["ende"] and (f["kenn"] or f["name"] == "FL NR#.LIN")]
    b["beginn"], b["ende"] = beginn, (max(enden) if enden else None)
    if not beginn:
        b["hinweise"].append("Einsatzbeginn nicht ermittelbar")
    if not b["ende"]:
        b["hinweise"].append("Einsatzende nicht ermittelbar")

    ortsteil, ort = b["ortsteil"], b["ort"]
    b["ort_liste"] = ortsteil if ortsteil in BEKANNTE_ORTE else (
        ort if ort in BEKANNTE_ORTE else (ortsteil or ort))

    ziel = b["objekt"] or b["strasse"]
    zusatz = re.sub(r"^(WH|HG|AH)\s+", "", ziel) if b["objekt"] else ziel
    bild = b["meldebild"]
    if b["stichwort"] == "S1" and b["stufe"] == "00":
        bild = "BSW"
    b["einsatz_text"] = f"{bild} / {zusatz}" if zusatz else bild

    ef = [p for p in b["personen"] if "Einheitsführer" in p["funktion"]]
    if ef:
        b["ehf"] = kurzname(ef[0]["vorname"], ef[0]["nachname"])
    else:
        el = b["einsatzleiter"].split()
        treffer = [p for p in b["personen"] if len(el) >= 2 and
                   norm(p["nachname"]) == norm(el[-1]) and norm(p["vorname"]) == norm(el[0])]
        b["ehf"] = kurzname(el[0], el[-1]) if treffer else ""
        b["hinweise"].append("Kein Einheitsführer im Bericht – " +
                             ("Einsatzleiter eingetragen, bitte prüfen" if treffer else "EHF bitte manuell eintragen"))

    anzahl = len({(norm(p["nachname"]), norm(p["vorname"])) for p in b["personen"]})
    b["personen_gh"] = max(0, anzahl - sum(f["staerke"] for f in bl.values()))
    d = beginn.date() if beginn else None
    b["wochenende"] = int(bool(d and (d.weekday() >= 5 or d in feiertage)))
    return b


class Namensabgleich:
    def __init__(self, kopfzeilen):
        self.spalten = []  # (spalte, nachname, vorname) in beiden Lesarten
        for col, text in kopfzeilen:
            if "," in text:
                n, v = [t.strip() for t in text.split(",", 1)]
                lesarten = [(n, v)]
            else:
                t = text.split()
                lesarten = [(t[0], " ".join(t[1:])), (t[-1], " ".join(t[:-1]))]
            for n, v in lesarten:
                self.spalten.append((col, norm(n), norm(v)))

    def finde(self, nachname, vorname):
        for n, v in ((nachname, vorname), (vorname, nachname)):
            n, v = norm(n), norm(v)
            kand = [s for s in self.spalten if s[1] == n]
            if len({s[0] for s in kand}) == 1:
                return kand[0][0]
            if kand:
                best = max(kand, key=lambda s: (s[2].startswith(v) or v.startswith(s[2]),
                                                difflib.SequenceMatcher(None, s[2], v).ratio()))
                if best[2].startswith(v) or v.startswith(best[2]) or \
                        difflib.SequenceMatcher(None, best[2], v).ratio() >= 0.7:
                    return best[0]
        n, v = norm(nachname), norm(vorname)
        best = max(self.spalten, key=lambda s: difflib.SequenceMatcher(None, s[1] + s[2], n + v).ratio())
        if difflib.SequenceMatcher(None, best[1] + best[2], n + v).ratio() >= 0.85:
            return best[0]
        return None


# ---------------------------------------------------------------- Vorlage lesen
def lies_vorlage(pfad):
    wb = openpyxl.load_workbook(pfad, data_only=True)
    uebersicht = wb.worksheets[0]
    anwesenheit = next((ws for ws in wb.worksheets if ws.title.lower().startswith("anwesenheit")), None)
    feier = next((ws for ws in wb.worksheets if ws.title.lower().startswith("feiertag")), None)

    feiertage = set()
    if feier:
        for (wert,) in feier.iter_rows(min_col=2, max_col=2, values_only=True):
            if isinstance(wert, dt.datetime):
                feiertage.add(wert.date())

    kopf = []
    if anwesenheit:
        for c in anwesenheit[3]:
            if c.column >= 6 and isinstance(c.value, str) and c.value not in ("Stärke", "Gesamtstunden"):
                kopf.append((c.column, c.value))

    vorhanden = {}
    nr_lauf = 0
    for r in range(4, uebersicht.max_row + 1):
        datum = uebersicht.cell(r, 2).value
        if not isinstance(datum, dt.datetime):
            continue
        nr_lauf += 1
        nr = uebersicht.cell(r, 1).value
        nr = nr if isinstance(nr, int) else nr_lauf
        vorhanden[nr] = {get_column_letter(c): uebersicht.cell(r, c).value for c in range(1, 49)}
    return {"feiertage": feiertage, "kopf": kopf, "vorhanden": vorhanden,
            "titel": uebersicht["A1"].value, "blatt": uebersicht.title}


# ---------------------------------------------------------------- Ausgabe
BLAU = "FF0070C0"
KOPF_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFFFF")
KOPF_FILL = PatternFill("solid", fgColor=BLAU)
FORMEL_FILL = PatternFill("solid", fgColor="FFF2F2F2")
DUENN = Side(style="thin", color="FFBFBFBF")
RAHMEN = Border(left=DUENN, right=DUENN, top=DUENN, bottom=DUENN)
MITTE = Alignment(horizontal="center", vertical="center")

UEBERSICHT_KOPF = ["Nr.", "Datum", "Tag", "Tag / Nacht", "Einsatzbeginn", "Einsatzende", "Einsatzdauer",
    "Einsatzstichwort", "Stufe", "Einsatz", "Ort", "EHF",
    "Stärke (45)", "Ausrückezeit (45)", "Azeit (45) min.", "Eintreffzeit (45)", "Ezeit (8/15 min)\n(45)",
    "Stärke (24)", "Ausrückezeit (24)", "Azeit (24) min.", "Eintreffzeit (24)", "Ezeit (8/15 min)\n(24) ",
    "Stärke (71)", "Ausrückezeit (71)", "Azeit (71) min.", "Eintreffzeit (71)", "Zeit (8/15 min)\n(71)",
    "Stärke (19)", "Ausrückezeit (19)", "Azeit (19) min.", "Eintreffzeit (19)", "Zeit (8/15 min)\n(19)",
    "Stärke (10)", "Ausrückezeit (10)", "Azeit (10) min.", "Eintreffzeit (10)", "Zeit (8/15 min)\n(10)",
    "Personen Gerätehaus", "Gesamtstärke", "", "Azeit min.", "Ezeit", "8 Min. erreicht",
    "Stärke bei E-Treffen", "Stärke nach 8 Min.", "Stärke nach 15Min.", "Gesamtsärke",
    "Wochenende / Feiertag"]
FORMEL_SPALTEN = {"C", "D", "G", "O", "Q", "T", "V", "Y", "AA", "AD", "AF", "AI", "AK", "AM",
                  "AO", "AP", "AQ", "AR", "AS", "AT", "AU"}


def formeln(r):
    f = {
        "C": f'=TEXT(B{r},"TTTT")',
        "D": f'=IF(AND(E{r}>0.25,E{r}<0.75),"Tag","Nacht")',
        "G": f"=MOD((F{r}-E{r}),1)",
        "AM": f"=SUM(M{r},R{r},W{r},AB{r},AG{r},AL{r})",
        "AO": f"=SUM(MIN(O{r},T{r},Y{r},AD{r},AI{r}))",
        "AP": f"=SUM(MIN(Q{r},V{r},AA{r},AF{r},AK{r}))",
        "AQ": f"=IF(AP{r}<=8.0001,1,0)",
        "AR": f"=SUMIF(Q{r},AP{r},M{r})+SUMIF(V{r},AP{r},R{r})+SUMIF(AA{r},AP{r},W{r})+SUMIF(AF{r},AP{r},AB{r})+SUMIF(AK{r},AP{r},AG{r})",
        "AS": "=" + "+".join(f'SUMIFS({s}{r},{z}{r},">"&AP{r},{z}{r},"<=8,001")'
                             for s, z in (("M", "Q"), ("R", "V"), ("W", "AA"), ("AB", "AF"), ("AG", "AK"))),
        "AT": "=" + "+".join(f'SUMIFS({s}{r},{z}{r},">"&AP{r},{z}{r},">8",{z}{r},"<=15,001")'
                             for s, z in (("M", "Q"), ("R", "V"), ("W", "AA"), ("AB", "AF"), ("AG", "AK"))),
        "AU": f"=M{r}+R{r}+W{r}+AB{r}",
    }
    for aus, dif in (("N", "O"), ("P", "Q"), ("S", "T"), ("U", "V"), ("X", "Y"), ("Z", "AA"),
                     ("AC", "AD"), ("AE", "AF"), ("AH", "AI"), ("AJ", "AK")):
        f[dif] = f'=IFERROR((MOD(({aus}{r}-E{r}),1))*24*60,"")'
    return f


def werte(b):
    v = {"A": b["nr"], "B": b["beginn"].replace(hour=0, minute=0, second=0) if b["beginn"] else None,
         "E": b["beginn"].time() if b["beginn"] else None,
         "F": b["ende"].time() if b["ende"] else None,
         "H": b["stichwort"], "I": b["stufe"], "J": b["einsatz_text"], "K": b["ort_liste"],
         "L": b["ehf"], "AL": b["personen_gh"], "AV": b["wochenende"]}
    for kenn, (s, a, e) in FAHRZEUG_SPALTEN.items():
        f = b["bloecke"].get(kenn)
        v[s] = f["staerke"] if f and f["staerke"] else None
        v[a] = f["aus"].time() if f and f["aus"] else "-"
        v[e] = f["ein"].time() if f and f["ein"] else "-"
    return v


def formatiere(c, spalte):
    c.border = RAHMEN
    c.font = Font(name="Calibri", size=11)
    c.alignment = Alignment(horizontal="left" if spalte in ("J", "K", "L") else "center", vertical="center")
    if spalte == "B":
        c.number_format = "DD.MM.YYYY"
    elif spalte == "C":
        c.number_format = "@"
    elif spalte in ("E", "F", "G"):
        c.number_format = "h:mm;@"
    elif spalte in ("N", "P", "S", "U", "X", "Z", "AC", "AE", "AH", "AJ"):
        c.number_format = "h:mm"
    elif spalte in ("H", "I"):
        c.number_format = "@"
    elif spalte not in ("J", "K", "L", "AQ", "AV", "A"):
        c.number_format = "0"
    if spalte in FORMEL_SPALTEN:
        c.fill = FORMEL_FILL


def vergleiche(b, alt):
    """Vergleich PDF-Werte mit bereits erfasster Zeile (Zeiten minutengenau)."""
    neu = werte(b)
    diffs = []
    for sp, w in neu.items():
        a = alt.get(sp)
        if sp in ("J",):  # Freitext wird nicht verglichen
            continue
        def kurz(x):
            if isinstance(x, dt.datetime):
                return x.strftime("%d.%m.%Y")
            if isinstance(x, dt.time):
                return x.strftime("%H:%M")
            if x in (None, "", "-", "."):
                return "-"
            return str(x).strip()
        ka, kn = kurz(a), kurz(w)
        if sp in ("AL", "AV") and ka == "-":
            ka = "0"
        if sp in ("M", "R", "W", "AB", "AG") and ka in ("-", "0") and kn == "-":
            continue
        if ka != kn:
            diffs.append((sp, ka, kn))
    return diffs


def schreibe(berichte, vorlage, ziel, abgleich):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Einsatzübersicht_Import"
    ws["A1"] = "Import aus Einsatzberichten – Spalten A:AV entsprechen 1:1 dem Blatt " + (vorlage["blatt"] or "")
    ws["A1"].font = Font(name="Calibri", size=16, bold=True)
    for sp, t in (("M", "02-45-1"), ("R", "02-24-1"), ("W", "02-71-1"), ("AB", "02-19-1"), ("AG", "01-10-1"),
                  ("AO", "Berechnung für Auswertung")):
        ws[f"{sp}2"] = t
        ws[f"{sp}2"].font = Font(name="Calibri", size=11, bold=True)
        ws[f"{sp}2"].alignment = MITTE
    for rng in ("M2:Q2", "R2:V2", "W2:AA2", "AB2:AF2", "AG2:AK2", "AO2:AV2"):
        ws.merge_cells(rng)
    for i, t in enumerate(UEBERSICHT_KOPF + ["", "PDF-Datei", "Prüfhinweise"], start=1):
        c = ws.cell(3, i, t)
        if t:
            c.font, c.fill = KOPF_FONT, KOPF_FILL
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            c.border = RAHMEN
    ws.row_dimensions[3].height = 60

    r = 4
    for b in berichte:
        v = werte(b)
        f = formeln(r)
        for i in range(1, 49):
            sp = get_column_letter(i)
            if sp == "AN":
                continue
            c = ws.cell(r, i, f.get(sp, v.get(sp)))
            formatiere(c, sp)
        ws.cell(r, 50, b["datei"])
        h = ws.cell(r, 51, "; ".join(b["hinweise"]))
        if b["hinweise"]:
            h.fill = PatternFill("solid", fgColor="FFFFF2CC")
        r += 1
    breiten = {"A": 6, "B": 11, "C": 11, "D": 8, "J": 48, "K": 15, "L": 16, "AN": 3, "AX": 40, "AY": 70}
    for i in range(1, 52):
        sp = get_column_letter(i)
        ws.column_dimensions[sp].width = breiten.get(sp, 9)
    ws.freeze_panes = "E4"

    # --- Anwesenheit
    wa = wb.create_sheet("Anwesenheit_Import")
    wa["A1"] = "Anwesenheit – Spalten F:AS entsprechen 1:1 dem Blatt Anwesenheit (Werte kopieren)"
    wa["A1"].font = Font(name="Calibri", size=14, bold=True)
    kopf = vorlage["kopf"]
    letzte = max([c for c, _ in kopf] or [5])
    titel = {1: "Nr.", 2: "Datum", 3: "Tag", 4: "Tag / Nacht", 5: "Einsatzdauer"}
    titel.update({c: t for c, t in kopf})
    titel[letzte + 1], titel[letzte + 2], titel[letzte + 4] = "Stärke", "Gesamtstunden", "Nicht zugeordnete Namen"
    for c, t in titel.items():
        z = wa.cell(3, c, t)
        z.font, z.fill, z.border = KOPF_FONT, KOPF_FILL, RAHMEN
        z.alignment = Alignment(horizontal="center", vertical="bottom",
                                text_rotation=90 if 6 <= c <= letzte else 0, wrap_text=True)
    wa.row_dimensions[3].height = 120
    abgleich_namen = Namensabgleich(kopf)
    for i, b in enumerate(berichte):
        r = 4 + i
        q = f"Einsatzübersicht_Import!"
        for c, sp, fmt in ((1, "A", "0"), (2, "B", "DD.MM.YYYY"), (3, "C", "@"), (4, "D", "@"), (5, "G", "h:mm")):
            z = wa.cell(r, c, f"={q}{sp}{r}")
            z.number_format, z.fill, z.border, z.alignment = fmt, FORMEL_FILL, RAHMEN, MITTE
        for c in range(6, letzte + 1):
            wa.cell(r, c).border = RAHMEN
            wa.cell(r, c).alignment = MITTE
        offen, gesehen = [], set()
        for p in b["personen"]:
            col = abgleich_namen.finde(p["nachname"], p["vorname"])
            if col is None:
                offen.append(f'{p["nachname"]} {p["vorname"]}')
            elif col not in gesehen:
                wa.cell(r, col, 1)
                gesehen.add(col)
        if offen:
            b["hinweise"].append("Name(n) ohne Spalte in Anwesenheitsliste: " + ", ".join(offen))
            ws.cell(r, 51, "; ".join(b["hinweise"])).fill = PatternFill("solid", fgColor="FFFFF2CC")
        L = get_column_letter
        z = wa.cell(r, letzte + 1, f"=SUM(F{r}:{L(letzte)}{r})")
        z.fill, z.border, z.alignment = FORMEL_FILL, RAHMEN, MITTE
        z = wa.cell(r, letzte + 2, f"={L(letzte + 1)}{r}*E{r}")
        z.number_format, z.fill, z.border, z.alignment = "[h]:mm", FORMEL_FILL, RAHMEN, MITTE
        wa.cell(r, letzte + 4, ", ".join(offen))
    for c in range(1, letzte + 5):
        wa.column_dimensions[get_column_letter(c)].width = 4.5 if 6 <= c <= letzte else 11
    wa.column_dimensions[get_column_letter(letzte + 4)].width = 40
    wa.freeze_panes = "F4"

    # --- Abgleich mit bereits erfassten Einsätzen
    wv = wb.create_sheet("Abgleich")
    wv.append(["Abgleich der PDF-Daten mit den bereits in der Einsatzübersicht erfassten Einsätzen "
               "(Zeiten minutengenau, Spalte J 'Einsatz' wird nicht verglichen)"])
    wv["A1"].font = Font(name="Calibri", size=12, bold=True)
    wv.append([])
    wv.append(["Nr.", "Spalte", "Spaltenname", "Wert in Liste", "Wert laut PDF", "PDF-Datei"])
    for c in wv[3]:
        c.font, c.fill, c.border = KOPF_FONT, KOPF_FILL, RAHMEN
    for b, diffs in abgleich:
        if not diffs:
            wv.append([b["nr"], "", "keine Abweichungen", "", "", b["datei"]])
        for sp, alt, neu in diffs:
            idx = openpyxl.utils.column_index_from_string(sp) - 1
            wv.append([b["nr"], sp, UEBERSICHT_KOPF[idx].replace("\n", " "), alt, neu, b["datei"]])
    for sp, w in zip("ABCDEF", (6, 8, 26, 34, 34, 55)):
        wv.column_dimensions[sp].width = w
    wv.freeze_panes = "A4"

    # --- Anleitung
    wl = wb.create_sheet("Anleitung")
    zeilen = [
        "So kommen die Daten in die Einsatzübersicht",
        "",
        "1. Blatt 'Einsatzübersicht_Import': Zeilen markieren (Spalten A bis AV), kopieren und in der "
        "Einsatzübersicht in die erste freie Tabellenzeile einfügen (Strg+V). Die Formeln passen sich automatisch an.",
        "2. Blatt 'Anwesenheit_Import': Spalten F bis AS der gleichen Zeilen kopieren und im Blatt "
        "Anwesenheit ab Spalte F einfügen (Rechtsklick > Einfügeoptionen > Werte).",
        "3. Spalte 'Prüfhinweise' (AY) beachten – gelb markierte Zeilen bitte kontrollieren.",
        "4. Blatt 'Abgleich' zeigt Unterschiede zwischen PDF und bereits erfassten Einsätzen.",
        "",
        "Regeln der automatischen Übernahme",
        "• Einsatzbeginn = frühester Alarmierungszeitpunkt der Rheinbrohler Fahrzeuge (02/..).",
        "• Einsatzende = spätestes Einsatzende der eigenen Fahrzeuge bzw. der FEZ (FL NR#.LIN).",
        "• Stichwort 'H2.03' -> Einsatzstichwort H2, Stufe 03; Brandsicherheitswache -> S1 / 00.",
        "• Stärke = Gesamtstärke je Fahrzeug aus dem Bericht; Zeiten mit Sekunden (Anzeige hh:mm).",
        "• Personen Gerätehaus = Anwesende laut Liste minus Besatzung der erfassten Fahrzeuge.",
        "• EHF = Person mit Funktion 'Einheitsführer'; fehlt diese, der Einsatzleiter (mit Hinweis).",
        "• Wochenende/Feiertag = Sa/So oder Datum im Blatt Feiertage der Einsatzübersicht.",
        "• 01/23-01 wird bei Einsatz mit Rheinbrohler Besatzung im Block 02-45-1 eingetragen.",
        "• Grau hinterlegte Zellen enthalten Formeln wie in der Einsatzübersicht.",
    ]
    for z in zeilen:
        wl.append([z])
    wl["A1"].font = Font(name="Calibri", size=14, bold=True)
    wl["A8"].font = Font(name="Calibri", size=12, bold=True)
    wl.column_dimensions["A"].width = 130
    for row in wl.iter_rows():
        row[0].alignment = Alignment(wrap_text=True, vertical="top")
    from openpyxl.workbook.properties import CalcProperties
    wb.calculation = CalcProperties(fullCalcOnLoad=True)
    wb.save(ziel)


# ---------------------------------------------------------------- Hauptprogramm
def main():
    hier = os.path.dirname(os.path.abspath(sys.argv[0]))
    ap = argparse.ArgumentParser(description="Einsatzbericht-PDFs in Import-Tabelle übertragen")
    ap.add_argument("pfade", nargs="*",
                    help="einzelne PDF-Dateien oder Ordner (auch per Drag & Drop auf die .bat)")
    ap.add_argument("--pdf-ordner", default=None)
    ap.add_argument("--vorlage", default=None, help="Einsatzübersicht_JJJJ.xlsx (wird nur gelesen)")
    ap.add_argument("--ausgabe", default=None)
    ap.add_argument("--alle", action="store_true", help="auch bereits erfasste Einsätze übernehmen")
    a = ap.parse_args()

    # PDF-Quellen bestimmen: übergebene Dateien/Ordner, sonst Ordner, sonst Skriptordner
    pdfs, ordner = [], []
    for p in a.pfade + ([a.pdf_ordner] if a.pdf_ordner else []):
        p = os.path.abspath(p.strip('"'))
        if os.path.isdir(p):
            ordner.append(p)
            pdfs += glob.glob(os.path.join(p, "*.pdf"))
        elif p.lower().endswith(".pdf") and os.path.isfile(p):
            ordner.append(os.path.dirname(p))
            pdfs.append(p)
        else:
            print(f"  ! ignoriert (keine PDF / kein Ordner): {p}")
    einzeldateien = bool(a.pfade) and all(not os.path.isdir(p.strip('"')) for p in a.pfade)
    if not pdfs and not a.pfade:
        ordner = [hier]
        pdfs = glob.glob(os.path.join(hier, "*.pdf"))
    pdfs = sorted(set(pdfs))
    if not pdfs:
        sys.exit("Keine PDF-Dateien gefunden.")

    suchorte = [hier] + ordner
    kandidaten = []
    for o in suchorte:
        kandidaten += sorted(glob.glob(os.path.join(o, "Einsatzübersicht*.xlsx")))
    vorlage_pfad = a.vorlage or (kandidaten[0] if kandidaten else None)
    if not vorlage_pfad:
        sys.exit("Einsatzübersicht_*.xlsx nicht gefunden – bitte in denselben Ordner legen "
                 "oder mit --vorlage angeben.")
    print("Vorlage:", vorlage_pfad)
    vorlage = lies_vorlage(vorlage_pfad)

    berichte = []
    for p in pdfs:
        try:
            berichte.append(berechne(lies_pdf(p), vorlage["feiertage"]))
        except Exception as e:  # defekte/fremde PDF überspringen
            print(f"  ! {os.path.basename(p)} übersprungen: {e}")
    berichte.sort(key=lambda b: (b["nr"] or 999, b["beginn"] or dt.datetime.max))

    abgleich = [(b, vergleiche(b, vorlage["vorhanden"][b["nr"]]))
                for b in berichte if b["nr"] in vorlage["vorhanden"]]
    # Einzeln übergebene PDFs werden immer übernommen, sonst nur neue Einsätze
    neu = berichte if (a.alle or einzeldateien) else \
        [b for b in berichte if b["nr"] not in vorlage["vorhanden"]]

    ziel = a.ausgabe or os.path.join(hier, f"Import_Einsatzberichte_{dt.datetime.now():%Y-%m-%d_%H%M}.xlsx")
    schreibe(neu, vorlage, ziel, abgleich)
    print(f"{len(berichte)} PDF gelesen, {len(neu)} Einsätze in Import übernommen, "
          f"{sum(1 for _, d in abgleich if d)} bereits erfasste mit Abweichungen.")
    print("Ergebnis:", ziel)


if __name__ == "__main__":
    main()
