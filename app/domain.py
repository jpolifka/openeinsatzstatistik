# -*- coding: utf-8 -*-
"""
Fachkonstanten der FF Rheinbrohl – einzige Quelle für Backend und Oberfläche.

Die Oberfläche bekommt diese Werte über /api/config (siehe client_config) und führt
keine eigenen Kopien.
"""
import datetime as dt

# Funkrufnamen der eigenen Fahrzeuge in der Reihenfolge der Einsatzübersicht
VEHICLES = ("02/45", "02/24", "02/71", "02/19", "01/10")
# Ersatzfahrzeuge, die bei Werkstattaufenthalt im Block eines anderen geführt werden
SUBSTITUTES = {"01/23": "02/45"}
# Fahrzeuge, die in der Gesamtstärke des Bedarfsplans fehlen (Excel-Spalte AU)
EXCLUDED_FROM_PLAN_CREW = {"01/10"}

# Kennungen im BKS-Bericht
UNIT_PREFIX = "FL NR#.BHÖ "              # Fahrzeuge der Verbandsgemeinde Bad Hönningen
OWN_VEHICLE_PREFIX = UNIT_PREFIX + "02/"  # Fahrzeuge des Löschzugs Rheinbrohl
CONTROL_CENTER = "FL NR#.LIN"             # Feuerwehreinsatzzentrale (FEZ)

# Einsatzarten: erster Buchstabe des Stichworts
CATEGORIES = (("H", "Hilfeleistung"), ("B", "Brand"), ("W", "Wasser"), ("G", "Gefahrstoff"), ("S", "Sonderlage"))
ALARM_LEVELS = (1, 2, 3, 4)               # Ziffer im Stichwort
# Gesondert gezählte Stichwort-Stufen
FIRE_ALARM_SYSTEM = ("B2", "07")          # Brandmeldeanlage
FIRE_WATCH = ("S1", "00")                 # Brandsicherheitswache

# Stichwortkatalog der AAO (Blatt "aktuelle_AAO" der AAO Rheinbrohl) für die Suche im Feld Stichwort:
# (Stichwort.Stufe, Bezeichnung, Meldebilder als weitere Suchbegriffe). Ohne Stufe = Grundstufe.
# Gestrichene Stichworte (B4.1, H4.01, S1.04, S1.08, S1.13) fehlen bewusst; S1.00 ist keine AAO-Stufe,
# wird aber für Brandsicherheitswachen genutzt.
KEYWORD_CATALOG = (
    ("B1", "Grundstufe", ""),
    ("B1.01", "Müllbrand", "Sperrmüllbrand, Müllcontainer, Mülltonne, Altpapierbrand"),
    ("B1.02", "Flächenbrand klein", "Wiesenbrand, Böschungsbrand, Heckenbrand, Gebüschbrand, Baumbrand"),
    ("B1.03", "Fahrzeugbrand klein", "Fahrzeugbrand innerorts, PKW-Brand innerorts, Motorradbrand, Zweiradbrand"),
    ("B1.04", "Brandnachschau", "gelöschtes Feuer, erloschenes Feuer"),
    ("B1.05", "Rauchentwicklung im Freien",
     "unklare Rauchentwicklung im Freien, Brandgeruch im Freien, Rauchsäule im Gelände"),
    ("B2", "Grundstufe", ""),
    ("B2.01", "Rauchentwicklung aus Gebäude",
     "Rauchentwicklung in / aus Gebäude unklar, ungewöhnlicher Geruch im Gebäude"),
    ("B2.02", "Flächenbrand groß", "Waldbrand, Rundballenbrand"),
    ("B2.03", "Fahrzeugbrand groß",
     "Fahrzeugbrand außerorts, PKW-Brand außerorts, LKW-Brand, Bus-Brand, mehrere Fahrzeuge"),
    ("B2.04", "Kaminbrand", "Schornsteinbrand"),
    ("B2.05", "Nebengebäude",
     "Nebengebäudebrand, Gartenhausbrand, Laubenbrand, Garagenbrand, Barackenbrand, Wohnwagenbrand, Bauwagenbrand,"
     " Schuppenbrand"),
    ("B2.06", "Rauchwarnmelder", "piepsender Heimrauchmelder, Heimrauchmelder, Rauchmelder"),
    ("B2.07", "BMA", ""),
    ("B2.08", "Wohnungsbrand", "Zimmerbrand, Küchenbrand, Kellerbrand"),
    ("B2.09", "Wohnungsbrand mit Personenrettung",
     "Zimmerbrand mit Personenrettung, Küchenbrand mit Personenrettung, Kellerbrand mit Personenrettung"),
    ("B3", "Grundstufe", ""),
    ("B3.01", "Gebäudebrand",
     "Gebäudevollbrand, Dachstuhlbrand, Feuer mit Personenrettung, landwirtschaftliches Gebäude"),
    ("B3.02", "Hotel, Event", "Hotelbrand, Festzeltbrand, Großereignis, Versammlungsstätte, Pensionsbrand"),
    ("B3.03", "Industriebrand", "Hallenbrand, Industriegebäudebrand, Werkstattbrand"),
    ("B3.04", "Explosion", ""),
    ("B3.05", "Fahrzeugbrand mit Gefahrgut", "Brand Gefahrguttransport"),
    ("B3.06", "Brand Zug", "Rauchentwicklung Zug, Brand Lokomotive, Rauchentwicklung Lokomotive"),
    ("B3.07", "Brand Straßenbahn", "Rauchentwicklung Straßenbahn"),
    ("B4", "Grundstufe", ""),
    ("H1", "Grundstufe", ""),
    ("H1.02", "Absicherung",
     "Absicherung Gefahrenstelle, Absicherung herabfallende Teile, Eigentumssicherung, Türe verschließen, Fenster "
     "verschließen, Schaufenster verschließen, Bergung eines Gegenstands, Sicherung eines Gegenstands, "
     "Sicherstellung von Gegenständen"),
    ("H1.03", "Insekten", "Bienen, Wespen, Hornissen"),
    ("H1.04", "Tierbergung", "Tierkadaver, Kadaver, totes Tier, toter Großfisch"),
    ("H1.05", "Tierrettung", "Tier in Notlage, Tierhilfe, freilaufende Tiere, Fundtiere"),
    ("H1.06", "Person in Aufzug", "Person in Aufzug ohne Dringlichkeit"),
    ("H1.07", "einfache Hilfeleistung",
     "Ast auf Fahrbahn, umgestürzter Baum, ausgehobener Kanaldeckel, Beseitigung Verkehrshindernis, Beseitigung "
     "etwaige Gefährdung"),
    ("H1.08", "Unterstützung Rettungsdienst", "Unterstützung Personenrettung"),
    ("H1.09", "Wassereinbruch",
     "Wasser in Gebäude, Wasserrohrbruch, tropfendes Wasser von Decke, Wasser aus Tür, Wasser in Keller, "
     "Wassereinbruch in Boot, Pumparbeiten klein"),
    ("H2", "Grundstufe", ""),
    ("H2.01", "Tür öffnen dringend", "Türöffnung, Türöffnung hilflose Person, Türöffnung RD"),
    ("H2.02", "Leichenbergung", "Leichenbergung als Amtshilfe"),
    ("H2.03", "Verkehrsunfall",
     "VU Person eingeklemmt, VU P Klemm, Person eingeklemmt, VU unklar, Verkehrsunfall unklar, Notrufmeldung über "
     "eCall"),
    ("H2.04", "Person in Zwangslage",
     "Person in Spielgerüst, Person steckt fest, Arbeitsunfall, Person in Aufzug mit Dringlichkeit, Forstunfall"),
    ("H2.05", "Person droht zu springen", "Person droht von Bauwerk zu springen, Springer, Suizidabsicht"),
    ("H2.06", "Einsturz klein",
     "Deckeneinsturz, Teileinsturz, herabgestürzte Teile, absturzgefährdete Teile, Einsturzgefahr"),
    ("H2.07", "größere Hilfeleistung", "Baum auf Gebäude, Baum in Stromleitung, Baum auf Fahrzeug"),
    ("H2.08", "Unterstützung Rettungsdienst HRF", "HRF hilft Rettungsdienst"),
    ("H2.09", "Unterstützung Rettungsdienst Gelände", "Personenrettung aus unwegsamen Gelände"),
    ("H2.10", "Person unter Zug", "Person von Zug erfasst, Person vor Zug, Person im / am Gleis"),
    ("H2.11", "Person unter Straßenbahn",
     "Person von Straßenbahn erfasst, Person vor Straßenbahn, Person im / am Gleis"),
    ("H3", "Grundstufe", ""),
    ("H3.01", "Verkehrsunfall groß", "Verkehrsunfall >3 PKW, Verkehrsunfall LKW, Verkehrsunfall Bus"),
    ("H3.02", "Höhen-, Tiefenrettung",
     "Höhenrettung, Tiefenrettung, Höhensicherung, Person droht abzustürzen, Person auf Gerüst, Kletterunfall, "
     "Gleitschirmflieger, Paraglider"),
    ("H3.03", "Einsturz groß", "Gebäudeeinsturz, Person verschüttet"),
    ("H3.04", "Verkehrsunfall Zug",
     "Zusammenstoß Zug, Entgleisung Zug, Kollision Zug, Umsturz Zug, PKW von Zug erfasst, Fahrzeug von Zug erfasst"),
    ("H3.05", "Verkehrsunfall Straßenbahn",
     "Zusammenstoß Straßenbahn, Entgleisung Straßenbahn, Kollision Straßenbahn, Umsturz Straßenbahn"),
    ("H4", "Grundstufe", ""),
    ("G1", "Grundstufe", ""),
    ("G1.01", "Ölspur", "Absicherung Gefahrenstelle"),
    ("G1.02", "ausl. Betriebsstoffe PKW < 50 l", "auslaufende Betriebsstoffe < 50 l, ausl. Benzin, ausl. Tank"),
    ("G1.03", "sonstige Kleinmengen < 10 l", "Kanister"),
    ("G1.04", "AEP-GS Alarmstufe 1", "Gefahrstoff klein"),
    ("G2", "Grundstufe", ""),
    ("G2.01", "ausl. Betriebsstoffe LKW > 50 l", "auslaufende Betriebsstoffe > 50 l, ausl. Diesel, ausl. Tank"),
    ("G2.02", "AEP-GS Alarmstufe 2", "Gefahrstoff mittel, Gefahrstoffgruppe, Teileinheit Gefahrstoffzug"),
    ("G2.03", "Gasgeruch", "Erdgasgeruch, ausgelöster CO-Warner RD, ausgelöster CO-Melder, Geruch chemisch unklar"),
    ("G3", "Grundstufe", ""),
    ("G3.01", "AEP-GS Alarmstufe 3", "Gefahrstoff groß, Gefahrstoffzug, Strahlenschutzeinsatz"),
    ("G3.02", "Gefahrstoffaustritt",
     "Gefahrstoffunfall Straße, Gefahrgutunfall Straße, Tanklastzug, Tankunfall, Produktaustritt"),
    ("G3.03", "Gasausströmung", "Erdgasaustritt, undichte Gasleitung"),
    ("G3.04", "Gefahrstoffaustritt Schienenfahrzeug",
     "Gefahrstoffaustritt Schiene, Gefahrstoffunfall Schiene, Gefahrgutunfall Schiene"),
    ("G4", "Grundstufe", ""),
    ("G4.01", "AEP-GS Alarmstufe 4", "weiterer Gefahrstoffzug"),
    ("W1", "Grundstufe", ""),
    ("W1.01", "Hochwasser", "langsam steigender Wasserstand"),
    ("W1.02", "Gewässerverunreinigung", "unklare Gewässerverunreinigung"),
    ("W2", "Grundstufe", ""),
    ("W2.01", "Wasser- / Eisrettung klein",
     "Wasserrettung stehendes Gewässer, Wasserrettung See, Person droht in stehendes Gewässer zu springen, Person "
     "in stehendem Gewässer, Eisrettung stehendes Gewässer, Person im Eis stehendes Gewässer, Person eingebrochen "
     "stehendes Gewässer, Eiseinbruch stehendes Gewässer"),
    ("W2.02", "Taucheinsatz", "Fahrzeug in Gewässer"),
    ("W2.03", "Bootsunfall",
     "Sportbootunfall, gekentertes Boot, manövrierunfähiges Boot, Yachtunfall, gekenterte Yacht, manövrierunfähige"
     " Yacht"),
    ("W2.04", "Öl auf Gewässer", "Ölfilm"),
    ("W2.05", "Bootsbrand", "Yachtbrand"),
    ("W3", "Grundstufe", ""),
    ("W3.01", "Schiffsbrand", ""),
    ("W3.02", "Schiffshavarie", "Schiffsunfall, Schiffskollision, manövrierunfähiges Schiff"),
    ("W3.03", "Wasser- / Eisrettung groß",
     "Wasserrettung 3+, Personen in Wasser 3+, Wasserrettung in fließendem Gewässer, Person droht in fließendes "
     "Gewässer zu springen, Person in fließendem Gewässer, Person im Eis fließendes Gewässer, Person eingebrochen "
     "fließendes Gewässer, Eiseinbruch fließendes Gewässer"),
    ("W4", "Grundstufe", ""),
    ("S1", "Grundstufe", ""),
    ("S1.00", "Brandsicherheitswache", ""),
    ("S1.01", "Einsatz nach Rücksprache",
     "Amtshilfe, Anforderungen, Einsatz Messleitkomponente, Wachbesetzung, Besetzung Feuerwehrhaus"),
    ("S1.03", "Bombenfund", "Bombe aus den Weltkriegen, Fliegerbombe, Blindgänger"),
    ("S1.05", "Personensuche", "vermisste Person"),
    ("S1.06", "PSNV", "Notfallseelsorge"),
    ("S1.07", "Stromausfall", "Flächenlage"),
    ("S1.09", "Erkundung", "Geruchsbelästigung, undefinierter Geruch"),
    ("S1.11", "Schwerlasttransport", "Transport adipöser Personen, Adipösentransport"),
    ("S1.14", "Hubschrauberlandung", "Landung Rettungshubschrauber, Ausleuchtung Landeplatz"),
    ("S1.15", "Zubringerdienst",
     "Zubringerdienst LNA, Zubringerdienst Schornsteinfeger, Lotsendienst, Transport besonderer Qualifikationen "
     "zur Einsatzstelle"),
    ("S1.16", "Kommunikationsausfall", "Ausfall Telekommunikationsnetze, Ausfall Alarmierungsnetze"),
    ("S1.17", "Sonstige Gefahrenmeldung", ""),
    ("S1.18", "D1-Störfallmeldung", "D1-Meldung nach Störfallverordnung"),
    ("S2", "Grundstufe", ""),
    ("S2.01", "Flugzeugunfall klein", "Ultraleichtflieger, Kleinflugzeug, Notwasserung Kleinfluggerät"),
    ("S2.02", "Unwetter", "Hochwasser, Sturm, Voralarm FEZ"),
    ("S2.03", "D2-Störfallmeldung", "D2-Meldung nach Störfallverordnung"),
    ("S3", "Grundstufe", ""),
    ("S3.01", "D3-Störfallmeldung", "D3-Meldung nach Störfallverordnung"),
    ("S4", "Grundstufe", ""),
    ("S4.01", "Flugzeugunfall groß", "Flugzeug auf Gebäude, Personenflugzeugunfall"),
    ("S4.02", "AEP Kernkraftwerk", "Kernkraftwerk, Atomunfall"),
    ("S4.03", "Gefahrenlage polizeilicher Einsatz",
     "Amok, Geiselnahme, sonstige Gefahrenlage durch polizeilichen Einsatz, LebEL"),
    ("S4.04", "LebEL Extern St.1 B-Raum",
     "LebEL Extern Stufe 1 B-Raum, LebEL Extern S1 B-Raum, Unterstützungskonzept LebEL extern S1 "
     "Bereitstellungsraum"),
    ("S4.05", "LebEL Extern St.2 Bereitschaft",
     "LebEL Extern Stufe 2 Bereitschaft, LebEL Extern S2 Bereitschaft, Unterstützungskonzept LebEL extern S2 "
     "Bereitschaft Unterkunft"),
    ("S4.06", "Überörtliche Hilfe größeren Umfanges", "externe Unterstützung durch Verbände"),
    ("S4.07", "D4-Störfallmeldung", "D4-Meldung nach Störfallverordnung"),
    ("U1.01", "lose Objekte ohne Dringlichkeit", ""),
    ("U1.02", "abgebrochener Ast ohne Dringlichkeit", "Ast im Garten, Ast neben der Fahrbahn, Ast auf Waldweg"),
    ("U1.03", "Wasser in Gebäude klein", "Wasser in Gebäude < 10 cm"),
    ("U1.04", "umgestürzter Baum ohne Dringlichkeit", "Baum in Garten, Baum auf Waldweg, Baum auf Nebenstraße"),
    ("U2.01", "übergetretener Bach", "Bach überflutet Fahrbahn, Bach überflutet Grundstück"),
    ("U2.02", "Wasser in Gebäude", "Wasser in Gebäude > 10 cm < 50 cm"),
    ("U2.03", "lose Objekte mit Dringlichkeit", "Baugerüst, Werbetafel, einzelne Dachpfannen, Fassadenelemente"),
    ("U2.04", "abgebrochener Ast mit Dringlichkeit",
     "Ast auf Fahrzeug, Ast auf Haus, Ast auf Dach, Ast auf Stromleitung"),
    ("U2.05", "Wasser in Gebäude", "Wasser in Gebäude > 50 cm"),
    ("U2.06", "überflutete Fahrbahn", "Wasser auf Fahrbahn, Fahrbahnüberflutung"),
    ("U2.07", "umgestürzter Baum mit Dringlichkeit",
     "Baum auf Fahrbahn, Baum auf Stromleitung, Baum auf Haus, Baum auf Dach, Baum auf Fahrzeug, eingeschlossenes "
     "Fahrzeug, abgeschnittene Ortszufahrt"),
    ("U2.08", "abgedecktes Dach", ""),
    ("U3.01", "Hangrutsch", ""),
)

# Orte mit dem Namensanfang, über den das Einsatzgebiet zugeordnet wird
PLACES = (("Rheinbrohl", "rhein"), ("Arienheller", "arienh"), ("Hammerstein", "hammer"),
          ("Ariendorf", "ariend"), ("Bad Hönningen", "bad hönn"), ("Leutesdorf", "leutes"))
PLACE_NAMES = tuple(name for name, _ in PLACES)
OTHER_AREA = "sonstige"
# Ausrückebereich laut Feuerwehrbedarfsplan Pos. 8.4
PLAN_PLACES = ("Rheinbrohl", "Hammerstein", "Arienheller")
PLAN_MIN_LEVEL = 2                        # Bedarfsplan ab Alarmstufe 2

# Zeitgrenzen des Bedarfsplans in Minuten
RESPONSE_LIMITS = (8, 10)
DEFAULT_LIMIT = 8
SECOND_LIMIT = 15                         # Stärke nach 15 Minuten
# Tag = Einsatzbeginn zwischen 06:00 und 18:00 Uhr (Excel-Spalte D)
DAY_START_HOUR, DAY_END_HOUR = 6, 18


def category_of(keyword):
    """Einsatzart (Buchstabe) aus dem Stichwort, z. B. 'H2' -> 'H'."""
    return (keyword or "")[:1]


def alarm_level(keyword):
    """Alarmstufe aus dem Stichwort, z. B. 'H2' -> 2; None, wenn keine Ziffer folgt."""
    digit = (keyword or "")[1:2]
    return int(digit) if digit.isdigit() else None


def is_fire_watch(keyword, subcode):
    return (keyword, subcode) == FIRE_WATCH


def is_fire_alarm_system(keyword, subcode):
    return (keyword, subcode) == FIRE_ALARM_SYSTEM


def is_daytime(t: dt.time):
    """Wie Excel =UND(E>0,25;E<0,75): die Grenzen selbst zählen zur Nacht."""
    start, end = dt.time(DAY_START_HOUR), dt.time(DAY_END_HOUR)
    return start < t < end


def area_of(place):
    """Einsatzgebiet anhand des Anfangs des Ortsnamens."""
    text = (place or "").lower()
    return next((name for name, prefix in PLACES if text.startswith(prefix)), OTHER_AREA)


def is_plan_relevant(incident):
    """Einsatz zählt für den Bedarfsplan: ab Alarmstufe 2 im eigenen Ausrückebereich."""
    level = alarm_level(incident["keyword"])
    return level in ALARM_LEVELS and level >= PLAN_MIN_LEVEL and incident["place"] in PLAN_PLACES


def substitute_label(vehicle_name, call_sign):
    """Kurzname eines Ersatzfahrzeugs im Block (z. B. '01/23-01'); None, wenn das Stammfahrzeug fuhr."""
    if not vehicle_name or call_sign in vehicle_name:
        return None
    return vehicle_name.replace(UNIT_PREFIX, "")


def client_config():
    """Fachkonstanten für die Oberfläche."""
    return {
        "vehicles": list(VEHICLES),
        "categories": [{"code": code, "name": name} for code, name in CATEGORIES],
        "places": list(PLACE_NAMES),
        "plan_places": list(PLAN_PLACES),
        "plan_min_level": PLAN_MIN_LEVEL,
        "plan_excluded_vehicles": sorted(EXCLUDED_FROM_PLAN_CREW),
        "limits": list(RESPONSE_LIMITS),
        "default_limit": DEFAULT_LIMIT,
        "second_limit": SECOND_LIMIT,
        "day_hours": [DAY_START_HOUR, DAY_END_HOUR],
        "fire_alarm_system": ".".join(FIRE_ALARM_SYSTEM),
        "fire_watch": ".".join(FIRE_WATCH),
        "keyword_catalog": [{"code": code, "name": name, "terms": terms} for code, name, terms in KEYWORD_CATALOG],
    }
