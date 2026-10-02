# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projekt

Einsatzstatistik für Feuerwehren (mandantenfähig, erste Wehr: FF Rheinbrohl): Einsatzbericht-PDFs aus dem BKS-Portal RLP einlesen, in SQLite speichern und die Auswertungen der früheren Excel-„Einsatzübersicht“ nachrechnen. FastAPI-Backend und eine Vanilla-JS-Oberfläche ohne Build-Schritt.

**Sprachkonvention:** Code ist **englisch** (Bezeichner, Funktionen, Module, DB-Tabellen und -Spalten, API-Pfade und JSON-Felder, CSS-Klassen, IDs). **Kommentare, Docstrings und alle Texte der Oberfläche sind deutsch.** Funktionsnamen beschreiben, was sie tun (`load_incidents`, `assign_vehicles`, `renderPreviews`).

## Befehle

Bevorzugt mit Docker arbeiten:

```bash
docker compose up -d --build          # bauen + starten → http://localhost:8112
docker compose logs -f                # Logs (u. a. Migration)
curl localhost:8112/health            # Health-Check (ohne Anmeldung erreichbar)
docker build --target test -t pdf2einsatz-test . && docker run --rm pdf2einsatz-test   # Tests (pytest)
docker run --rm -v "$PWD/static:/s:ro" node:22-alpine node --check /s/app.js          # JS-Syntax
```

`static/` ist nicht gemountet, sondern ins Image kopiert. Nach Änderungen an Python- oder Frontend-Dateien ist deshalb `--build` nötig.

Lokal ohne Docker: `DATA_DIR=daten uvicorn app.main:app --reload --port 8112`, Tests mit `pip install -r requirements-dev.txt && pytest`.

## Architektur

**Datenfluss beim PDF-Import (zweistufig):**
Jeder Endpunkt mit Einsatzdaten holt sich per `Depends(access)` ein `tenancy.Access` (Rechte des Benutzers, ausgewählte Wehr aus dem Cookie `scope`) und verlangt ein Recht: `a.current(STATS|INCIDENTS|WRITE)` für die ausgewählte Wehr bzw. `a.tenant(slug, …)` für eine bestimmte. Fehlt es, wirft das `tenancy.Forbidden` (403). Gearbeitet wird nur mit `tenant.connection()` und `tenant.config`. Einsatz-IDs der API sind `"<slug>:<id>"`.

1. `POST /api/reports` → `main._read_pdf`: Text holen, Berichtsart erkennen (`report_kind`: Stammdatensatz / Haupt- / Nebenbericht, mit `bks_report_id` und `bks_record_id`). Ein Stammdatensatz geht über `records.save_master` in die zentrale DB. Sonst wählt `report.match_tenant` die Wehr (Einheit, Fahrzeuge nur bei Wehren ohne `unit_marker`). Berichte einer anderen Wehr der VG (ohne Schreibrecht in der Auswahl) gehen per `main._forward` in deren `pending_report` und bekommen einen Hinweis; Berichte von Einheiten ohne Wehr (FEZ) werden als `notes` übersprungen. Danach `report.read_text` (`parse_report` → `complete_number` → `derive` → `check_plausibility`). Der Bericht liegt nur im Speicher (`main.PreviewSessions`, TTL 1 h, daher nur ein uvicorn-Worker), gebunden an Benutzer und Wehr. `report.preview` liefert den Einsatz für die Vorschau mit Namensabgleich und dem bereits erfassten Einsatz (`store.find_existing`: gleicher BKS-Bericht, sonst gleiches `year` + `number`), `report.differences` die Abweichungen.
2. `POST /api/reports/accept` mit Token, Dateiname und vom Nutzer korrigierten `fields` → `report.save`, mit `replace` als Aktualisierung des erfassten Einsatzes (gleiche ID; `store.replace_report_rows` ersetzt Fahrzeuge und Anwesenheit aus dem Bericht, Zeilen mit `manual = 1` bleiben). Unbekannte Personen werden als neue `member`-Zeilen angelegt. `main._after_import` vermerkt den Bericht im zentralen Verzeichnis (`records.register_report`) und legt Hinweise an (`records.notify`, `records.notify_others`).

**Module (`app/`):**
- `domain.py`: Fachkonstanten, die **für alle Wehren** gelten (Einsatzarten, Alarmstufen, Sonderstichworte B2.07/S1.00, Vorlage des Stichwortkatalogs) und Standardwerte für neue Wehren (Zeitgrenzen 10/15 Min., Tag 06–18 Uhr), Link ins BKS-Portal (`BKS_REPORT_URL`).
- `tenant_config.py`: `TenantConfig`, die **Fachkonfiguration einer Wehr** (Fahrzeuge als `Vehicle` mit Dienstzeitraum, Ersatzfahrzeuge, BKS-Kennungen, Orte, Bedarfsplan-Orte, Zeitgrenzen, Stichwortkatalog) mit den Regeln, die davon abhängen (`area_of`, `is_daytime`, `is_plan_relevant`, `substitute_label`). Sie wird als `cfg` durch `report`, `metrics`, `excel_export` und `main.incident_json` gereicht, nie als Modul-Global gelesen. Die Oberfläche bekommt sie über `GET /api/config` (`client_config`) und hält keine eigenen Kopien.
- `tenancy.py`: Mandanten. Zentral-DB (`vg`, `tenant`, `account`, `membership`), Rollen `vg_lead`/`vg_stats` (VG) und `lead`/`editor`/`viewer` (Wehr) mit den Rechten `stats`, `incidents`, `write`, `admin`, Superadmins aus `ADMIN_EMAILS`. `access_for` baut das `Access`, `load_config`/`save_config` lesen und schreiben die `TenantConfig` einer Wehr (Tabellen `setting`, `fleet`, `keyword`), zwischengespeichert je Slug (`forget_config` nach dem Speichern).
- `legacy.py`: `rheinbrohl_config()` (Werte der früheren Einzel-Installation, in Tests `conftest.CFG`) und `migrate_single_install`, die einmalige Übernahme von `DATA_DIR/einsaetze.db` als Wehr Rheinbrohl beim Start.
- `records.py`: zentrale, personenfreie Daten über Wehren hinweg: Stammdatensätze (`master_record`), Verzeichnis der eingelesenen Berichte (`record_report`), Hinweise an Wehren (`notice`) und Prüfvermerke (`record_review`). `check` gleicht je Stammdatensatz die Wehren ab (Grundlage des Prüfprotokolls, nur Wehrleiter über `Access.manages_vg`); dafür liest es die Wehr-DBs über `tenancy.vg_tenants` ohne Benutzerrechte und gibt nur personenfreie Befunde aus. Gemeinsame Einsätze erkennt `metrics.unique_incidents` über `bks_record_id` oder `dispatch_number`.
- `pdf_report.py`: Text aus der PDF holen (`extract_text`) und auswerten (`parse_report`). Getrennt, damit Tests ohne PDF auskommen.
- `report.py`: Ableitungsregeln (Einsatzbeginn = früheste Alarmierung der eigenen Fahrzeuge `02/..`, EHF, Gerätehaus, Wochenende/Feiertag), Prüfhinweise und Umwandlung Bericht → Einsatz.
- `metrics.py`: rechnet die Excel-Formeln nach. Kommentare nennen die Excel-Spalten (AO = Azeit, AP = Ezeit, AR–AU = Stärken, AM = Gesamtstärke). Kennzahlen werden **nie gespeichert**. `evaluate()` berechnet sie einmal je Einsatz für `statistics`, `response_plan` und `attendance_overview`. Minuten laufen wie in Excel per Modulo 24 h ab Einsatzbeginn.
- `store.py`: Datenbankzugriff. `FIELDS` ist die Liste der bearbeitbaren Einsatzfelder; INSERT/UPDATE, das Pydantic-Modell in `main.py` und der Abgleich bauen darauf auf. `MemberDirectory` gleicht Namen über `names.NameMatcher` ab.
- `db.py`: Verbindungen (`connection(path)`) und **Migrationen**, getrennt für die Zentrale (`CENTRAL_MIGRATIONS`, `DATA_DIR/app.db`) und je Wehr (`TENANT_MIGRATIONS`, `DATA_DIR/tenants/<slug>/einsaetze.db`), gezählt über `PRAGMA user_version`. Schemaänderungen nur als neuen Schritt hinten anfügen. Wehr-Schritt 1 ist das ursprüngliche deutsche Schema, 2 benennt es ins Englische um, 3 ergänzt Konfiguration, Logos, Fahrzeuge, Stichworte und `dispatch_number`. Eindeutigkeit gilt über `(year, number)` je Wehr.
- `excel_layout.py`: `Layout`, der Spaltenaufbau der Einsatzübersicht aus der Fahrzeugliste einer Wehr (bei fünf Fahrzeugen A:AV). `excel_export.py` schreibt damit den Export mit Formeln wie im Original. Einen Excel-Import gibt es nicht mehr.
- `names.py`, `timeutil.py`, `holidays.py`: Namensvergleich, Zeitumwandlungen, Feiertage RLP.
- `mail.py`: Versand per SMTP (`SMTP_*`) über das Postfach der eigenen Domain, Envelope-From = `MAIL_FROM` (SPF), eigene DKIM-Signatur (`DKIM_SELECTOR`, `DKIM_KEY_FILE`, d = Domain aus `MAIL_FROM`) für DMARC; `python -m app.mail dkim-key|check|test`. Kein Dritt-Dienst.
- `auth.py`: Anmeldung per Magic Link (aktiv, wenn `ADMIN_EMAILS` gesetzt ist; berechtigt ist, wer `tenancy.is_allowed`): Versand über `mail.py`, HMAC-signierte Links (15 Min., einmalig) und Sitzungs-Cookies (30 Tage), Anmeldeseiten als `APIRouter`. Schlüssel aus `SECRET_KEY` oder `session.key` im Datenordner.
- `theme.py`: Farben und Logos. `palette` leitet aus `colors` (`brand`, optional `brand_dark`) alle `--brand-*`-Tokens ab und dunkelt abgeleitete Töne selbst bis zum Mindestkontrast ab; `check` lehnt zu helle Farben ab; `image_type` erkennt PNG/JPEG/WebP am Inhalt (kein SVG). `NEUTRAL` gilt für Anmeldung und VG-Gesamtansicht.
- `admin.py`: Verwaltung als `APIRouter` (`/api/admin/...` mit Recht `admin` je Wehr, `/api/super/...` nur Superadmin): Einstellungen (`SettingsIn` → `_check_settings` → `TenantConfig`, Meldungen auf Deutsch als 422), Logos, Stichwortkatalog (eigener Katalog entsteht bei der ersten Änderung als Kopie der Vorlage, Import CSV/XLSX), Rollenvergabe nach `tenancy.GRANTABLE` im eigenen Bereich, VGs und Wehren. Nach dem Speichern immer `tenancy.forget_config(slug)`.
- `dpa.py`: AVV je VG (`APIRouter`). Status `pending`/`draft`/`revoked` sperrt die Wehren der VG für alle außer Superadmins (Prüfung in `tenancy.access_for`, Liste in `Access.blocked`). Vertragstext aus `templates/avv_v<TEMPLATE_VERSION>.html`; **Textänderungen nur als neue Datei mit erhöhter `TEMPLATE_VERSION`**, damit gespeicherte Prüfsummen nachvollziehbar bleiben. Uploads nach `DATA_DIR/avv/<vg>/`, nie überschreiben; `dpa_event` ist per Trigger nur anhängbar.
- `main.py`: nur HTTP: Endpunkte, Anmeldeprüfung als Middleware (`PUBLIC_PATHS` ohne Anmeldung), Zugriff (`access`), JSON-Aufbereitung (`incident_json`).

**Farben und Logos:** `app.css` definiert nur Tokens (`--brand`, `--brand-dark`, `--brand-mid` …, Standard = Rot der FF Rheinbrohl); keine Farbwerte direkt in Regeln. `/api/theme.css` überschreibt sie je Wehr, Logos kommen über `/api/branding/<slug>/<name>` aus der Wehr-DB (Tabelle `asset`), ohne Logo das neutrale Signet aus `static/img/`.

**Frontend** (`static/`): `app.js` erzeugt alle Ansichten als Template-Strings mit `esc()` für Nutzerdaten. Der Zustand liegt im globalen Objekt `state`, die Fachkonstanten in `config` (von `/api/config`). Ansichten sind in `VIEWS` registriert (Reiter, Laden, Zeichnen); `records.js`, `admin.js` und `dpa.js` tragen sich nach `app.js` selbst ein. `app.js` meldet `app:data` (Daten neu geladen) und `app:view` (Ansicht gezeichnet) als Ereignisse auf `document`. Routing über den URL-Hash (`#evaluation`, `#incidents`, `#members`). Tooltips kommen generisch über `data-tip`. `help.js` ist die **einzige Quelle für die Online-Hilfe**: `HELP_SECTIONS` liefert Tooltip-Kurztexte und das Hilfefenster, Schlüssel sind die Feld- bzw. Kennzahlnamen der API. `helpButton(key)` erzeugt das `?`-Symbol, statische Elemente bekommen es über `data-help-key`. Neue Felder oder Kennzahlen bekommen dort einen Eintrag. Texte mit Werten der Wehr (Fahrzeuge, Orte, Zeitgrenzen) sind Funktionen, die zur Laufzeit aus `config` lesen – keine festen Zahlen oder Namen. `help.js` wird vor `app.js` geladen und nutzt dessen `$` und `esc` erst zur Laufzeit. `admin.js` (Verwaltung) und `dpa.js` (Auftragsverarbeitung) werden nach `app.js` geladen und tragen sich in `VIEWS` ein (`visible()` statt `permission`); Eingaben binden über `data-bind="pfad"` an `admin.settings`.

**Neues Einsatzfeld:** Migration in `db.py` (`TENANT_MIGRATIONS`), Eintrag in `store.FIELDS` (ggf. `INT_FIELDS`), Ableitung in `report.derive`, ggf. `report.COMPARED_FIELDS`, `FORM_FIELDS` in `app.js`, Hilfetext in `help.js`.

## Daten und Datenschutz

`Einsatzberichte/` (PDFs, Excel) und `daten/` (SQLite) enthalten Namen und Anwesenheiten. Sie sind per `.gitignore` ausgeschlossen und dürfen nicht eingecheckt werden. Auch im Code und in Tests keine echten Namen verwenden (Beispiele: „M. Muster“, „Beispiel, Erika“). Konfiguration: `.env` (Vorlage `.env.example`: `APP_PORT`, `BASE_URL`, `ADMIN_EMAILS`, `SECRET_KEY`, `SMTP_*`, `MAIL_FROM`, `DKIM_*`, `DPA_*` für den AVV). Neue Variablen gehören immer mit Kommentar in `.env.example`. Tests prüfen die Rechte als Matrix (`tests/test_access.py`); neue Endpunkte mit Einsatzdaten gehören dort hinein.

Bewusste Abweichungen zur Excel-Datei sind im README dokumentiert. Einsätze ohne Eintreffzeit fließen zum Beispiel nicht in den Bedarfsplan ein.
