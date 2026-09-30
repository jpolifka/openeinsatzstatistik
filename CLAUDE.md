# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projekt

Einsatzstatistik der FF Rheinbrohl: Einsatzbericht-PDFs aus dem BKS-Portal RLP einlesen, in SQLite speichern und die Auswertungen der früheren Excel-„Einsatzübersicht“ nachrechnen. FastAPI-Backend und eine Vanilla-JS-Oberfläche ohne Build-Schritt. Code, Bezeichner, Kommentare und die Oberfläche sind durchgehend **deutsch**. Neuer Code folgt dieser Konvention (z. B. `einsatz`, `staerke`, `hinweise`).

## Befehle

Bevorzugt mit Docker arbeiten:

```bash
docker compose up -d --build          # bauen + starten → http://localhost:8112
docker compose logs -f                # Logs (u. a. Erstimport)
curl localhost:8112/health            # Health-Check (ohne Passwortschutz erreichbar)
```

`static/` ist nicht gemountet, sondern ins Image kopiert. Nach Änderungen an Python- oder Frontend-Dateien ist deshalb `--build` nötig.

Lokal ohne Docker:

```bash
DB_PFAD=daten/einsaetze.db IMPORT_ORDNER=Einsatzberichte uvicorn app.main:app --reload --port 8112
python app/core.py --pdf-ordner Einsatzberichte/2026   # eigenständiges CLI: erzeugt eine Excel-Importdatei
```

Es gibt keine Tests, keinen Linter und kein Node-Tooling. JS-Syntax lässt sich per Docker prüfen:
`docker run --rm -v "$PWD/static:/s:ro" node:22-alpine node --check /s/app.js`

## Architektur

**Datenfluss beim PDF-Import (zweistufig):**
1. `POST /api/pdf` → `core.lies_pdf` → `main._nummer_ergaenzen` → `core.berechne` → `main._plausibilitaet`. Das Ergebnis ist ein Bericht-Dict. Es wird **nur im Speicher** unter einem Token abgelegt (`_sitzungen`, TTL 1 h) und als Vorschau zurückgegeben. Die Vorschau enthält den Namensabgleich der Kameraden und die Abweichungen zu einem bereits erfassten Einsatz (gleiches `jahr` + `nr`).
2. `POST /api/pdf/uebernehmen` mit Token, Datei und vom Nutzer korrigierten `felder` → `bestand.speichern_bericht`. Unbekannte Personen werden dabei als neue `kamerad`-Zeilen angelegt.

**Module und ihre Rollen:**
- `app/core.py`: PDF-Parsing und Ableitungsregeln (Einsatzbeginn = früheste Alarmierung der eigenen Fahrzeuge `02/..`, EHF-Ermittlung, `personen_gh`, Wochenende/Feiertag) sowie das Schreiben der Excel-Datei (`schreibe`). Die Datei ist **zugleich das eigenständige Windows-CLI-Script** (`einsatzberichte_import.py`, liegt als Kopie in `Einsatzberichte/2026/` mit `.bat`). Es muss ohne FastAPI lauffähig bleiben. Web-spezifische Logik gehört nach `main.py`, nicht hierher.
- `app/bestand.py`: Zugriff auf die Datenbank, Namensabgleich (`Kameraden`, nutzt `core.Namensabgleich`) und der **Erstimport**. Beim Start mit leerer DB werden alle `Einsatzübersicht_JJJJ.xlsx` aus `IMPORT_ORDNER` eingelesen.
- `app/berechnung.py`: Rechnet die Excel-Formeln nach. Die Kommentare verweisen auf die Excel-Spalten (AO = Azeit, AP = Ezeit, AR–AU = Stärken, AM = Gesamtstärke). Kennzahlen werden **nie gespeichert**, sondern bei jeder Anfrage aus Beginn/Ende und den Fahrzeugzeiten berechnet. Minuten laufen wie in Excel per Modulo 24 h ab Einsatzbeginn.
- `app/db.py`: SQLite-Schema (`einsatz`, `fahrzeug`, `kamerad`, `anwesenheit`). Die Spaltenkommentare nennen die zugehörige Excel-Spalte. Eindeutigkeit gilt über `(jahr, nr)`.
- `app/main.py`: API, optionales HTTP-Basic-Auth als Middleware (aktiv, wenn `APP_PASSWORT` gesetzt ist), Excel-Export über `core.schreibe`.

**Feste Fachkonstanten** stehen mehrfach im Code und müssen gemeinsam geändert werden: die Fahrzeugblöcke `02/45, 02/24, 02/71, 02/19, 01/10` (`core.FAHRZEUG_SPALTEN`, `static/app.js` `BLOECKE`), die bekannten Orte (`core.BEKANNTE_ORTE`, `berechnung.GEBIETE`, `app.js` `auswahllisten`) und die Bedarfsplan-Orte Rheinbrohl/Hammerstein/Arienheller.

**Frontend** (`static/`): `app.js` erzeugt alle Ansichten als Template-Strings mit `esc()` für Nutzerdaten. Der Zustand liegt im globalen Objekt `z`, das Routing läuft über den URL-Hash (`#auswertung`, `#einsaetze`, `#kameraden`). Tooltips kommen generisch über das Attribut `data-tip`. `hilfe.js` ist die **einzige Quelle für die Online-Hilfe**: `HILFE_ABSCHNITTE` liefert die Tooltip-Kurztexte und das Hilfefenster. `hilfe(schluessel)` erzeugt das `?`-Symbol, bei Formularfeldern ist der Schlüssel der Feldname. Neue Felder oder Kennzahlen bekommen dort einen Eintrag. `hilfe.js` wird vor `app.js` geladen und nutzt dessen globale Funktionen `$` und `esc` erst zur Laufzeit.

## Daten und Datenschutz

`Einsatzberichte/` (PDFs, Excel) und `daten/` (SQLite) enthalten Namen und Anwesenheiten. Sie sind per `.gitignore` ausgeschlossen und dürfen nicht eingecheckt werden. Auch im Code keine echten Namen verwenden, etwa als Beispiele oder Platzhalter. Konfiguration: `.env` (Vorlage `.env.example`: `APP_PORT`, `APP_BENUTZER`, `APP_PASSWORT`).

Bewusste Abweichungen zur Excel-Datei sind im README dokumentiert. Einsätze ohne Eintreffzeit fließen zum Beispiel nicht in den Bedarfsplan ein.
