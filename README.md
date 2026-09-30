# pdf2einsatz – Einsatzstatistik FF Rheinbrohl

Weboberfläche zur Einsatzstatistik der Freiwilligen Feuerwehr Rheinbrohl:
Einsatzbericht-PDFs aus dem BKS-Portal RLP einlesen, prüfen und in eine eigene Datenbank
übernehmen. Die Auswertungen der bisherigen Excel-„Einsatzübersicht“ (Statistik,
Feuerwehrbedarfsplan, Anwesenheit) rechnet die App direkt im Browser nach.

> [!IMPORTANT]
> Die Datenbank enthält Namen und Anwesenheiten der Einsatzkräfte. Vor dem Betrieb im
> Netzwerk ein Passwort setzen (siehe [Konfiguration](#konfiguration)). Einsatzdaten
> (`Einsatzberichte/`, `daten/`) werden nie eingecheckt.

## Inhalt

- [Funktionen](#funktionen)
- [Schnellstart](#schnellstart)
- [Konfiguration](#konfiguration)
- [Daten](#daten)
- [Bedienung](#bedienung)
- [Entwicklung](#entwicklung)
- [Projektstruktur](#projektstruktur)
- [Abweichungen zur Excel-Einsatzübersicht](#abweichungen-zur-excel-einsatzübersicht)

## Funktionen

- **PDF einlesen** – Einsatzbericht per Drag & Drop, Vorschau mit Prüfhinweisen,
  Korrektur einzelner Felder vor dem Übernehmen, Abgleich mit bereits erfassten Einsätzen.
- **Auswertung** – Kennzahlen, Feuerwehrbedarfsplan Pos. 8.4 (8 oder 10 Minuten),
  Einsatzarten, Alarmstufen, Einsatzgebiet, Monate im Vorjahresvergleich, Uhrzeiten,
  Wochentage. Jedes Diagramm ist auch als Tabelle abrufbar.
- **Einsätze** – Liste mit Suche und Filter, Details, Bearbeiten, Löschen sowie
  Excel-Export im Spaltenformat der Einsatzübersicht (A:AV + Anwesenheit).
- **Kameraden** – Einsätze, Beteiligung, Stunden, Nacht- und Wochenendeinsätze je Kamerad.
- **Online-Hilfe** – `?` im Kopf öffnet die Hilfe; das `?` neben Feldern und Kennzahlen
  erklärt den jeweiligen Wert und springt zur passenden Stelle.

## Schnellstart

Voraussetzung: [Docker](https://docs.docker.com/get-docker/) mit Compose.

```bash
git clone https://github.com/jpolifka/pdf2einsatz.git
cd pdf2einsatz
cp .env.example .env          # Passwort usw. anpassen
docker compose up -d --build
```

Danach <http://localhost:8112> öffnen. Zustand prüfen: <http://localhost:8112/health>.

## Konfiguration

Einstellungen stehen in `.env` (Vorlage: [`.env.example`](.env.example)).

| Variable       | Standard    | Bedeutung                                                    |
|----------------|-------------|--------------------------------------------------------------|
| `APP_PORT`     | `8112`      | Port auf dem Host                                            |
| `APP_BENUTZER` | `feuerwehr` | Benutzername für den Passwortschutz                          |
| `APP_PASSWORT` | *(leer)*    | Leer = kein Schutz. **Setzen, sobald die App im Netz läuft.** |

Im Container fest eingestellt (siehe [`docker-compose.yml`](docker-compose.yml)):
`DB_PFAD=/daten/einsaetze.db`, `IMPORT_ORDNER=/import`.

## Daten

| Pfad               | Inhalt                                               | Im Git |
|--------------------|------------------------------------------------------|:------:|
| `daten/`           | SQLite-Datenbank `einsaetze.db` – der Datenbestand   | nein   |
| `Einsatzberichte/` | Berichts-PDFs und `Einsatzübersicht_JJJJ.xlsx` je Jahr | nein |

**Erstimport:** Ist die Datenbank beim Start leer, übernimmt die App alle
`Einsatzübersicht_JJJJ.xlsx` aus `Einsatzberichte/` (Einsätze, Fahrzeuge, Anwesenheit).
Danach ist die Datenbank maßgeblich; die Excel-Dateien werden nicht mehr gebraucht.

**Neu importieren:**

```bash
docker compose down
rm daten/einsaetze.db*
docker compose up -d
```

**Sicherung:** `daten/einsaetze.db` sichern (bei gestopptem Container) oder in der App
„Einsätze → Excel-Export“ nutzen.

## Bedienung

1. **PDF einlesen** (oben rechts): Bericht hineinziehen. Die Vorschau zeigt erkannte
   Felder, Fahrzeuge, Anwesenheit und Prüfhinweise.
2. Felder wie EHF oder Zeiten bei Bedarf korrigieren, dann **In Statistik übernehmen**.
3. Ist die Einsatznummer schon erfasst, werden die Abweichungen angezeigt; mit
   „erfassten Einsatz durch diese PDF ersetzen“ lässt sich der Einsatz aktualisieren.

Was die einzelnen Felder und Kennzahlen bedeuten, erklärt die Online-Hilfe in der App.

## Entwicklung

Lokal ohne Docker (Python 3.12):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DB_PFAD=daten/einsaetze.db IMPORT_ORDNER=Einsatzberichte uvicorn app.main:app --reload --port 8112
```

Die PDF-Auswertung in `app/core.py` ist zugleich das eigenständige Kommandozeilen-Script
(früher `einsatzberichte_import.py`), das eine Import-Datei für die Excel-Einsatzübersicht
erzeugt:

```bash
python app/core.py --pdf-ordner Einsatzberichte/2026
```

## Projektstruktur

```text
app/
  main.py         FastAPI: Schnittstellen, Passwortschutz, Erstimport beim Start
  core.py         PDF lesen, Felder ableiten, Excel schreiben (auch als CLI nutzbar)
  bestand.py      Datenbankzugriff, Namensabgleich Kameraden, Erstimport aus Excel
  berechnung.py   Formeln der Einsatzübersicht (Kennzahlen, Statistik, Bedarfsplan, Anwesenheit)
  db.py           SQLite-Schema und Verbindung
  feiertage.py    Feiertage RLP (berechnet, ohne Internet)
static/
  index.html      Oberfläche
  app.js          Ansichten und Bedienung
  hilfe.js        Texte und Logik der Online-Hilfe
  app.css         Gestaltung
  fonts/, img/    Schrift Sansation (SIL OFL), Logos
Dockerfile, docker-compose.yml, requirements.txt
```

## Abweichungen zur Excel-Einsatzübersicht

Bewusste Unterschiede zu den Formeln der Excel-Datei:

- Das Blatt „Auswertung“ rechnet in Excel nicht (`#WERT!`, Formelbereiche `AO4:AO7`
  vs. `H4:H59`). Hier wird es korrekt gerechnet.
- Einsätze ohne Eintreffzeit zählt Excel mit 0 Minuten als „erreicht“ – hier werden sie
  im Bedarfsplan nicht berücksichtigt (die Anzahl wird angezeigt).
- Der Gesamtwert im Bedarfsplan ist über alle Einsätze gemittelt (Excel: Mittel der
  vier Zeitfenster).

## Lizenz

Internes Werkzeug der Freiwilligen Feuerwehr Rheinbrohl – keine Lizenz zur Weitergabe.
Die Schrift Sansation steht unter der SIL Open Font License; die Logos sind Eigentum der
FF Rheinbrohl.
