# -*- coding: utf-8 -*-
"""
Auswertungen – dieselben Regeln wie die Formeln der Einsatzübersicht:

  Einsatz je Zeile   D, G, O/Q/T/V/…, AM, AO–AU     -> kennzahlen()
  Blatt Statistik    Stichworte, Stufen, Orte, …     -> statistik()
  Blatt Auswertung   Feuerwehrbedarfsplan Pos. 8.4   -> bedarfsplan()
  Blatt Anwesenheit  Stärke, Gesamtstunden           -> anwesenheit()
"""
import datetime as dt

from app.bestand import BLOECKE

KATEGORIEN = [("H", "Hilfeleistung"), ("B", "Brand"), ("W", "Wasser"), ("G", "Gefahrstoff"), ("S", "Sonderlage")]
GEBIETE = [("Rheinbrohl", "rhein"), ("Arienheller", "arienh"), ("Hammerstein", "hammer"),
           ("Ariendorf", "ariend"), ("Bad Hönningen", "bad hönn"), ("Leutesdorf", "leutes")]
BEDARF_ORTE = ("Rheinbrohl", "Hammerstein", "Arienheller")
ZEITFENSTER = [
    ("werktag_tag", "Werktag", "06:00 – 18:00 Uhr", 0, True),
    ("werktag_nacht", "Werktag", "18:00 – 06:00 Uhr", 0, False),
    ("we_tag", "Sa, So, Feiertag", "06:00 – 18:00 Uhr", 1, True),
    ("we_nacht", "Sa, So, Feiertag", "18:00 – 06:00 Uhr", 1, False),
]
WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONATE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]


def _sek(t):
    h, m, s = (int(x) for x in t.split(":"))
    return h * 3600 + m * 60 + s


def _dt(iso):
    return dt.datetime.fromisoformat(iso) if iso else None


def _mittel(werte):
    werte = [w for w in werte if w is not None]
    return round(sum(werte) / len(werte), 2) if werte else None


# ---------------------------------------------------------------- je Einsatz
def kennzahlen(e, grenze=8):
    """Formeln der Einsatzzeile. Minuten werden wie in Excel per MOD(…;1) ab Einsatzbeginn gerechnet."""
    beginn, ende = _dt(e["beginn"]), _dt(e["ende"])
    b_sek = beginn.hour * 3600 + beginn.minute * 60 + beginn.second if beginn else None
    # D: =WENN(UND(E>0,25;E<0,75);"Tag";"Nacht")
    tag = b_sek is not None and 6 * 3600 < b_sek < 18 * 3600
    dauer = (ende - beginn).total_seconds() / 60 if beginn and ende and ende >= beginn else None

    fz = {}
    for kenn in BLOECKE:
        f = e["fahrzeuge"].get(kenn)
        if not f:
            continue
        az = ((_sek(f["aus"]) - b_sek) % 86400) / 60 if f["aus"] and b_sek is not None else None
        ez = ((_sek(f["ein"]) - b_sek) % 86400) / 60 if f["ein"] and b_sek is not None else None
        fz[kenn] = {"staerke": f["staerke"] or 0, "azeit": az, "ezeit": ez}

    azeiten = [f["azeit"] for f in fz.values() if f["azeit"] is not None]
    ezeiten = [f["ezeit"] for f in fz.values() if f["ezeit"] is not None]
    ao = min(azeiten) if azeiten else None                       # AO Azeit (schnellstes Fahrzeug)
    ap = min(ezeiten) if ezeiten else None                       # AP Ezeit (erstes Fahrzeug vor Ort)
    g = grenze + 0.001
    ar = as_ = at = None
    if ap is not None:
        ar = sum(f["staerke"] for f in fz.values() if f["ezeit"] == ap)                        # bei Eintreffen
        as_ = sum(f["staerke"] for f in fz.values() if f["ezeit"] is not None and ap < f["ezeit"] <= g)
        at = sum(f["staerke"] for f in fz.values()
                 if f["ezeit"] is not None and f["ezeit"] > ap and grenze < f["ezeit"] <= 15.001)
    return {
        "tag": tag,
        "dauer_min": dauer,
        "fahrzeuge": fz,
        "azeit": ao, "ezeit": ap,
        "erreicht": (ap <= grenze + 0.0001) if ap is not None else None,     # AQ
        "staerke_eintreffen": ar, "staerke_grenze": as_, "staerke_15": at,  # AR, AS, AT
        "staerke_ohne_10": sum(f["staerke"] for k, f in fz.items() if k != "01/10"),  # AU
        "staerke_gesamt": sum(f["staerke"] for f in fz.values()) + (e["personen_gh"] or 0),  # AM
        "anwesend": len(e["personen"]),
    }


def _gebiet(ort):
    o = (ort or "").lower()
    for name, praefix in GEBIETE:
        if o.startswith(praefix):
            return name
    return "sonstige"


# ---------------------------------------------------------------- Blatt Statistik
def statistik(einsaetze, jahr, vorjahr=None, heute=None):
    heute = heute or dt.date.today()
    n = len(einsaetze)
    kz = [(e, kennzahlen(e)) for e in einsaetze]

    stichworte = {}
    for e in einsaetze:
        stichworte[e["stichwort"] or "?"] = stichworte.get(e["stichwort"] or "?", 0) + 1
    kategorien = [{"kuerzel": k, "name": name,
                   "anzahl": sum(1 for e in einsaetze if (e["stichwort"] or "").startswith(k)),
                   "stichworte": {f"{k}{i}": stichworte.get(f"{k}{i}", 0) for i in range(1, 5)}}
                  for k, name in KATEGORIEN]
    bma = sum(1 for e in einsaetze if e["stichwort"] == "B2" and e["stufe"] == "07")
    bsw = sum(1 for e in einsaetze if e["stichwort"] == "S1" and e["stufe"] == "00")
    stufen = [{"stufe": i, "anzahl": sum(1 for e in einsaetze
                                         if len(e["stichwort"] or "") >= 2 and e["stichwort"][1] == str(i))}
              for i in range(1, 5)]

    gebiete = {name: 0 for name, _ in GEBIETE}
    gebiete["sonstige"] = 0
    for e in einsaetze:
        gebiete[_gebiet(e["ort"])] += 1

    wochentage = [0] * 7
    stunden = [0] * 24
    monate = [0] * 12
    for e in einsaetze:
        b = _dt(e["beginn"])
        if b:
            wochentage[b.weekday()] += 1
            stunden[b.hour] += 1
            monate[b.month - 1] += 1
    monate_vj = [0] * 12
    vj_bis_heute = None
    if vorjahr is not None:
        stichtag = heute.replace(year=jahr - 1) if not (heute.month == 2 and heute.day == 29) else dt.date(jahr - 1, 2, 28)
        vj_bis_heute = 0
        for e in vorjahr:
            b = _dt(e["beginn"])
            if b:
                monate_vj[b.month - 1] += 1
                vj_bis_heute += b.date() <= stichtag

    dauer = [k["dauer_min"] for _, k in kz if k["dauer_min"] is not None]
    personal_min = sum(k["dauer_min"] * k["anwesend"] for _, k in kz if k["dauer_min"] is not None)
    # Einsätze / Woche: laufendes Jahr wie Excel (=Gesamt/ISOKALENDERWOCHE(HEUTE())), sonst ganzes Jahr
    wochen = heute.isocalendar()[1] if jahr == heute.year else dt.date(jahr, 12, 28).isocalendar()[1]
    tagsueber = sum(stunden[6:18])
    return {
        "jahr": jahr,
        "anzahl": n,
        "vorjahr_bis_heute": vj_bis_heute,
        "vorjahr_gesamt": len(vorjahr) if vorjahr is not None else None,
        "pro_woche": round(n / wochen, 2) if wochen else None,
        "dauer_gesamt_min": round(sum(dauer)),
        "dauer_mittel_min": round(sum(dauer) / len(dauer), 1) if dauer else None,
        "personal_std": round(personal_min / 60, 1),
        "anwesend_mittel": _mittel([k["anwesend"] for _, k in kz if k["anwesend"]]),
        "kategorien": kategorien, "bma": bma, "bsw": bsw, "stufen": stufen,
        "gebiete": [{"name": k, "anzahl": v} for k, v in gebiete.items()],
        "wochentage": [{"name": WOCHENTAGE[i], "anzahl": wochentage[i]} for i in range(7)],
        "stunden": [{"stunde": i, "anzahl": stunden[i], "tag": 6 <= i < 18} for i in range(24)],
        "anteil_tag": round(tagsueber / n, 3) if n else None,
        "monate": [{"name": MONATE[i], "anzahl": monate[i], "vorjahr": monate_vj[i] if vorjahr is not None else None}
                   for i in range(12)],
    }


# ---------------------------------------------------------------- Blatt Auswertung (Bedarfsplan)
def bedarfsplan(einsaetze, grenze=8):
    """Pos. 8.4: ab Alarmstufe 2 (Stichwort ?2–?4) in Rheinbrohl / Hammerstein / Arienheller."""
    relevant, ohne_zeiten = [], 0
    for e in einsaetze:
        sw = e["stichwort"] or ""
        if len(sw) >= 2 and sw[1] in "234" and e["ort"] in BEDARF_ORTE:
            k = kennzahlen(e, grenze)
            if k["ezeit"] is None:
                ohne_zeiten += 1   # Excel zählt diese mit 0 min als "erreicht" – hier ausgenommen
                continue
            relevant.append((e, k))

    def zusammenfassen(liste):
        erreicht = sum(1 for _, k in liste if k["erreicht"])
        return {
            "anzahl": len(liste),
            "azeit": _mittel([k["azeit"] for _, k in liste]),
            "ezeit": _mittel([k["ezeit"] for _, k in liste]),
            "erreicht": erreicht,
            "nicht_erreicht": len(liste) - erreicht,
            "quote": round(erreicht / len(liste), 3) if liste else None,
            "staerke_eintreffen": _mittel([k["staerke_eintreffen"] for _, k in liste]),
            "staerke_grenze": _mittel([k["staerke_grenze"] for _, k in liste]),
            "staerke_15": _mittel([k["staerke_15"] for _, k in liste]),
            "staerke_gesamt": _mittel([k["staerke_ohne_10"] for _, k in liste]),
            "einsaetze": [{"id": e["id"], "nr": e["nr"], "ezeit": round(k["ezeit"], 1), "erreicht": k["erreicht"]}
                          for e, k in liste],
        }

    fenster = []
    for key, tagart, zeit, we, tag in ZEITFENSTER:
        liste = [(e, k) for e, k in relevant if bool(e["wochenende"]) == bool(we) and k["tag"] == tag]
        fenster.append({"key": key, "tagart": tagart, "zeit": zeit, **zusammenfassen(liste)})
    return {"grenze": grenze, "orte": BEDARF_ORTE, "fenster": fenster, "gesamt": zusammenfassen(relevant),
            "ohne_zeiten": ohne_zeiten}


# ---------------------------------------------------------------- Blatt Anwesenheit
def anwesenheit(einsaetze):
    n = len(einsaetze)
    pro = {}
    for e in einsaetze:
        k = kennzahlen(e)
        for p in e["personen"]:
            z = pro.setdefault(p["id"], {"id": p["id"], "name": p["name"], "einsaetze": 0, "minuten": 0.0,
                                         "nacht": 0, "wochenende": 0, "zuletzt": None})
            z["einsaetze"] += 1
            z["minuten"] += k["dauer_min"] or 0
            z["nacht"] += not k["tag"]
            z["wochenende"] += bool(e["wochenende"])
            if e["beginn"] and (z["zuletzt"] is None or e["beginn"] > z["zuletzt"]):
                z["zuletzt"] = e["beginn"]
    liste = sorted(pro.values(), key=lambda z: (-z["einsaetze"], z["name"]))
    for z in liste:
        z["stunden"] = round(z.pop("minuten") / 60, 1)
        z["quote"] = round(z["einsaetze"] / n, 3) if n else None
    return {"anzahl_einsaetze": n, "kameraden": liste}
