# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projekt

Einsatzstatistik der FF Rheinbrohl: Einsatzbericht-PDFs aus dem BKS-Portal RLP einlesen, in SQLite speichern und die Auswertungen der früheren Excel-„Einsatzübersicht“ nachrechnen. FastAPI-Backend und eine Vanilla-JS-Oberfläche ohne Build-Schritt.

**Sprachkonvention:** Code ist **englisch** (Bezeichner, Funktionen, Module, DB-Tabellen und -Spalten, API-Pfade und JSON-Felder, CSS-Klassen, IDs). **Kommentare, Docstrings und alle Texte der Oberfläche sind deutsch.** Funktionsnamen beschreiben, was sie tun (`load_incidents`, `assign_vehicles`, `renderPreviews`).

## Befehle

Bevorzugt mit Docker arbeiten:

```bash
docker compose up -d --build          # bauen + starten → http://localhost:8112
docker compose logs -f                # Logs (u. a. Erstimport, Migration)
curl localhost:8112/health            # Health-Check (ohne Passwortschutz erreichbar)
docker build --target test -t pdf2einsatz-test . && docker run --rm pdf2einsatz-test   # Tests (pytest)
docker run --rm -v "$PWD/static:/s:ro" node:22-alpine node --check /s/app.js          # JS-Syntax
```

`static/` ist nicht gemountet, sondern ins Image kopiert. Nach Änderungen an Python- oder Frontend-Dateien ist deshalb `--build` nötig.

Lokal ohne Docker: `DB_PATH=daten/einsaetze.db IMPORT_DIR=Einsatzberichte uvicorn app.main:app --reload --port 8112`, Tests mit `pip install -r requirements-dev.txt && pytest`.

## Architektur

**Datenfluss beim PDF-Import (zweistufig):**
1. `POST /api/reports` → `report.read_pdf` (`pdf_report.read_report` → `complete_number` → `derive` → `check_plausibility`). Der Bericht liegt nur im Speicher (`main.PreviewSessions`, TTL 1 h, daher nur ein uvicorn-Worker). `report.preview` liefert den Einsatz für die Vorschau mit Namensabgleich und dem bereits erfassten Einsatz (gleiches `year` + `number`), `report.differences` die Abweichungen.
2. `POST /api/reports/accept` mit Token, Dateiname und vom Nutzer korrigierten `fields` → `report.save`. Unbekannte Personen werden als neue `member`-Zeilen angelegt.

**Module (`app/`):**
- `domain.py`: **einzige Quelle der Fachkonstanten** (Fahrzeuge `02/45, 02/24, 02/71, 02/19, 01/10`, Ersatzfahrzeuge, Orte, Bedarfsplan-Orte, Zeitgrenzen 8/10/15 Min., Tag 06–18 Uhr, Sonderstichworte B2.07/S1.00) und kleine Fachregeln (`alarm_level`, `is_daytime`, `is_plan_relevant`). Die Oberfläche bekommt sie über `GET /api/config` (`client_config`) und hält keine eigenen Kopien.
- `pdf_report.py`: Text aus der PDF holen (`extract_text`) und auswerten (`parse_report`). Getrennt, damit Tests ohne PDF auskommen.
- `report.py`: Ableitungsregeln (Einsatzbeginn = früheste Alarmierung der eigenen Fahrzeuge `02/..`, EHF, Gerätehaus, Wochenende/Feiertag), Prüfhinweise und Umwandlung Bericht → Einsatz.
- `metrics.py`: rechnet die Excel-Formeln nach. Kommentare nennen die Excel-Spalten (AO = Azeit, AP = Ezeit, AR–AU = Stärken, AM = Gesamtstärke). Kennzahlen werden **nie gespeichert**. `evaluate()` berechnet sie einmal je Einsatz für `statistics`, `response_plan` und `attendance_overview`. Minuten laufen wie in Excel per Modulo 24 h ab Einsatzbeginn.
- `store.py`: Datenbankzugriff. `FIELDS` ist die Liste der bearbeitbaren Einsatzfelder; INSERT/UPDATE, das Pydantic-Modell in `main.py` und der Abgleich bauen darauf auf. `MemberDirectory` gleicht Namen über `names.NameMatcher` ab.
- `db.py`: Verbindung und **Migrationen** (`MIGRATIONS`, gezählt über `PRAGMA user_version`). Schemaänderungen nur als neuen Schritt hinten anfügen. Schritt 1 ist das ursprüngliche deutsche Schema, Schritt 2 benennt es ins Englische um. Eindeutigkeit gilt über `(year, number)`.
- `excel_layout.py`: Spaltenaufbau der Einsatzübersicht (A:AV), aus `domain.VEHICLES` erzeugt. Gemeinsam genutzt von `excel_import.py` (Erstimport aller `Einsatzübersicht_JJJJ.xlsx` aus `IMPORT_DIR`, wenn die DB leer ist) und `excel_export.py` (Export mit Formeln wie im Original).
- `names.py`, `timeutil.py`, `holidays.py`: Namensvergleich, Zeitumwandlungen, Feiertage RLP.
- `main.py`: nur HTTP: Endpunkte, optionales HTTP-Basic-Auth (aktiv, wenn `APP_PASSWORD` gesetzt ist), JSON-Aufbereitung (`incident_json`).

**Frontend** (`static/`): `app.js` erzeugt alle Ansichten als Template-Strings mit `esc()` für Nutzerdaten. Der Zustand liegt im globalen Objekt `state`, die Fachkonstanten in `config` (von `/api/config`). Ansichten sind in `VIEWS` registriert (Reiter, Laden, Zeichnen). Routing über den URL-Hash (`#evaluation`, `#incidents`, `#members`). Tooltips kommen generisch über `data-tip`. `help.js` ist die **einzige Quelle für die Online-Hilfe**: `HELP_SECTIONS` liefert Tooltip-Kurztexte und das Hilfefenster, Schlüssel sind die Feld- bzw. Kennzahlnamen der API. `helpButton(key)` erzeugt das `?`-Symbol, statische Elemente bekommen es über `data-help-key`. Neue Felder oder Kennzahlen bekommen dort einen Eintrag. `help.js` wird vor `app.js` geladen und nutzt dessen `$` und `esc` erst zur Laufzeit.

**Neues Einsatzfeld:** Migration in `db.py`, Eintrag in `store.FIELDS` (ggf. `INT_FIELDS`), Ableitung in `report.derive`, ggf. `report.COMPARED_FIELDS`, `FORM_FIELDS` in `app.js`, Hilfetext in `help.js`.

## Daten und Datenschutz

`Einsatzberichte/` (PDFs, Excel) und `daten/` (SQLite) enthalten Namen und Anwesenheiten. Sie sind per `.gitignore` ausgeschlossen und dürfen nicht eingecheckt werden. Auch im Code und in Tests keine echten Namen verwenden (Beispiele: „M. Muster“, „Beispiel, Erika“). Konfiguration: `.env` (Vorlage `.env.example`: `APP_PORT`, `APP_USER`, `APP_PASSWORD`).

Bewusste Abweichungen zur Excel-Datei sind im README dokumentiert. Einsätze ohne Eintreffzeit fließen zum Beispiel nicht in den Bedarfsplan ein.
