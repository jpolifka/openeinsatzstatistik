# pdf2einsatz – Einsatzstatistik FF Rheinbrohl

Weboberfläche zur Einsatzstatistik der Freiwilligen Feuerwehr Rheinbrohl:
Einsatzbericht-PDFs aus dem BKS-Portal RLP einlesen, prüfen und in eine eigene Datenbank
übernehmen. Die Auswertungen der bisherigen Excel-„Einsatzübersicht“ (Statistik,
Feuerwehrbedarfsplan, Anwesenheit) rechnet die App direkt im Browser nach.

> [!IMPORTANT]
> Die Datenbanken enthalten Namen und Anwesenheiten der Einsatzkräfte. Vor dem Betrieb im
> Netzwerk die Anmeldung einschalten (`ADMIN_EMAILS`, siehe [Konfiguration](#konfiguration)).
> Einsatzdaten (`Einsatzberichte/`, `daten/`) werden nie eingecheckt.

## Inhalt

- [Funktionen](#funktionen)
- [Schnellstart](#schnellstart)
- [Konfiguration](#konfiguration)
- [Mandanten und Rollen](#mandanten-und-rollen)
- [Daten](#daten)
- [Datenschutz](#datenschutz)
- [Bedienung](#bedienung)
- [Entwicklung](#entwicklung)
- [Projektstruktur](#projektstruktur)
- [Abweichungen zur Excel-Einsatzübersicht](#abweichungen-zur-excel-einsatzübersicht)

## Funktionen

- **PDF einlesen** – Einsatzberichte per Drag & Drop (einzeln, mehrere oder als ZIP), Vorschau mit Prüfhinweisen,
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

Einstellungen stehen ausschließlich in `.env` (Vorlage: [`.env.example`](.env.example)).
Code und `docker-compose.yml` enthalten keine Standardwerte. Ohne `.env` startet der Container nicht.

| Variable       | Pflicht     | Bedeutung                                                    |
|----------------|-------------|--------------------------------------------------------------|
| `APP_PORT`     | ja          | Port auf dem Host, z. B. `8112`. Hinter einem Reverse Proxy auf demselben Host `127.0.0.1:8112`, damit die App nur über den Proxy erreichbar ist |
| `ADMIN_EMAILS` | nein        | Superadmins, durch Komma getrennt. Gesetzt = Anmeldung an; alle anderen Benutzer werden den Wehren zugeordnet (siehe [Mandanten und Rollen](#mandanten-und-rollen)). Leer = kein Schutz, jeder ist Superadmin. **Setzen, sobald die App im Netz läuft.** |
| `BASE_URL`     | mit `ADMIN_EMAILS` | Öffentliche Adresse der App, z. B. `https://einsatz.example.org`. Daraus entsteht der Link in der Mail. Mit `https://` wird das Sitzungs-Cookie nur über HTTPS gesendet |
| `SMTP_HOST`    | nein        | SMTP-Server des Postfachs der eigenen Domain, z. B. `smtp.strato.de`. Leer = kein Versand, Link steht nur im Log (`docker compose logs`) |
| `SMTP_PORT`, `SMTP_SECURITY` | mit `SMTP_HOST` | `465` + `ssl` oder `587` + `starttls` |
| `SMTP_USER`, `SMTP_PASSWORD` | mit `SMTP_HOST` | Zugangsdaten des Postfachs |
| `MAIL_FROM`    | mit `SMTP_HOST` | Absender, z. B. `Einsatzstatistik <statistik@example.org>` – Adresse des Postfachs oder ein Alias davon |
| `DKIM_SELECTOR`, `DKIM_KEY_FILE` | empfohlen | DKIM-Signatur durch die App, siehe [Mailversand](#mailversand) |
| `DPA_*`        | für den AVV | Angaben zum Auftragnehmer, Hosting, Datensicherung, Mail-Anbieter (siehe [Datenschutz](#datenschutz)) |
| `SECRET_KEY`   | nein        | Schlüssel für Links und Sitzungen. Leer = wird als `daten/session.key` erzeugt |

**Reverse Proxy:** Die App muss an der Wurzel der Domain laufen (nicht unter einem Unterpfad).
Weiterleitungen sind relative Pfade, `X-Forwarded-*`-Header werden nicht benötigt. Bei nginx
`client_max_body_size` so setzen, dass die PDFs bzw. ZIP-Dateien durchpassen (Standard 1 MB).

**Anmeldung:** Ist `ADMIN_EMAILS` gesetzt, fragt die App nach der E-Mail-Adresse und schickt
einen Anmeldelink (15 Minuten gültig, nur einmal benutzbar). Die Sitzung hält 30 Tage.
Wer keine Zuordnung zu einer aktiven Wehr mehr hat, ist beim nächsten Aufruf abgemeldet.
Wird `daten/session.key` gelöscht, sind alle abgemeldet. Die früheren Variablen `APP_PASSWORD`
und `AUTH_EMAILS` werden nicht mehr unterstützt; ist eine davon ohne `ADMIN_EMAILS` gesetzt,
startet die App nicht (sonst liefe sie still ohne Schutz).

### Mailversand

Die Anmeldelinks gehen per SMTP über das Postfach der eigenen Domain hinaus (kein Dritt-Dienst).
Damit sie bei Domains mit `DMARC p=reject` ankommen, muss SPF oder DKIM zur Absenderdomain passen:

- **SPF:** Der SPF-Eintrag der Domain muss den Ausgangsserver des Anbieters erlauben (bei Strato:
  `v=spf1 redirect=_spf.strato.com`). Die App setzt die Absenderadresse auch als Envelope-From.
- **DKIM:** Die App signiert jede Mail selbst (`d=` Domain aus `MAIL_FROM`). Einmalig:
  ```bash
  docker compose exec einsatzberichte python -m app.mail dkim-key   # legt DKIM_KEY_FILE an, gibt den TXT-Eintrag aus
  ```
  Den Eintrag als TXT unter `<DKIM_SELECTOR>._domainkey.<domain>` im DNS anlegen (Strato: Domainverwaltung
  → DNS → TXT- und CNAME-Records). Der Schlüssel wird nie überschrieben; für einen neuen Schlüssel einen
  neuen Selektor wählen.
- **Prüfen:** `docker compose exec einsatzberichte python -m app.mail check` zeigt SPF, DKIM und DMARC;
  `… python -m app.mail test <adresse>` schickt eine Test-Mail. Beim Start steht das Ergebnis im Log.

Die frühere Variable `RESEND_API_KEY` wird nicht mehr unterstützt; ist sie gesetzt, startet die App nicht.

Im Container fest eingestellt, weil er zum Volume gehört (siehe [`docker-compose.yml`](docker-compose.yml)):
`DATA_DIR=/daten` (Pflicht).

## Mandanten und Rollen

Eine Installation bedient mehrere Wehren, gruppiert nach Verbandsgemeinde (VG). Jede Wehr hat
eine eigene Datenbank und eine eigene Fachkonfiguration (Fahrzeuge, BKS-Kennung, Orte,
Bedarfsplan). Wer sich anmeldet, sieht nur die Wehren, denen er zugeordnet ist; bei mehreren
gibt es oben eine Auswahl.

| Rolle | Bereich | Statistik | Einsätze und Personal | PDF einlesen, bearbeiten | Verwaltung der Wehr |
|---|---|:-:|:-:|:-:|:-:|
| Superadmin (`ADMIN_EMAILS`) | alle | ✓ | ✓ | ✓ | ✓ |
| Wehrleiter | alle Wehren einer VG | ✓ | ✓ | ✓ | ✓ |
| Statistik VG (z. B. Bürgermeister) | alle Wehren einer VG | ✓ | – | – | – |
| Wehrführer | eine Wehr | ✓ | ✓ | ✓ | ✓ |
| Erfasser | eine Wehr | ✓ | ✓ | ✓ | – |
| Benutzer | eine Wehr | ✓ | – | – | – |

Rollen nur mit Statistik sehen keine Namen: Anwesenheit, Einsatzliste, Kameraden und der
Excel-Export sind für sie gesperrt. Geprüft wird im Backend, die Oberfläche blendet nur aus.

**Gesamtansicht einer VG** (Wehrleiter, Statistik VG, Superadmin; oben „Alle Wehren · …“):
- Auswertung über alle Wehren der VG, auf einzelne Wehren filterbar. Ein Einsatz mehrerer Wehren
  zählt bei jeder Wehr (Beteiligungen); die große Zahl zählt ihn über die Einsatznummer der
  Leitstelle nur einmal. Der Bedarfsplan wertet jede Wehr mit ihren eigenen Orten aus.
- Einsatzliste aller Wehren mit Markierung der Wehr; Kameraden gibt es nur je Wehr.
- Excel-Export als eine Mappe mit Übersicht und je Wehr Einsatzübersicht und Anwesenheit.
  „Kennzahlen (Excel)“ enthält nur die Zahlen je Wehr, ohne Namen.
- „Drucken / PDF“ öffnet die Druckansicht der Auswertung (im Druckdialog als PDF sichern).
- PDF einlesen verteilt die Berichte auf die passende Wehr (über die berichtende Einheit,
  ersatzweise die eigenen Fahrzeuge im Bericht). Haben andere Wehren denselben Einsatz schon
  erfasst, zeigt die Vorschau „gemeinsamer Einsatz mit …“.

**Verwaltung** (Reiter „Verwaltung“ für Wehrführer, Wehrleiter und Superadmin):
- *Wehr*: Name, Farben (Farbwähler, Hex oder RGB, mit Vorschau und Kontrastprüfung), Logos.
- *Fahrzeuge*: Reihenfolge, Bezeichnung, Dienstzeitraum („im Dienst ab“, „außer Dienst ab“), Nachfolger,
  Zählung im Bedarfsplan, Ersatzfahrzeuge. Neue eigene Fahrzeuge aus BKS-Berichten nimmt die App beim
  Übernehmen automatisch auf.
- *BKS-Kennung*: Präfixe und Einheit, an denen die App eigene Fahrzeuge und Berichte erkennt, mit Testfeld.
- *Orte & Bedarfsplan*: Orte mit Namensanfang, Ausrückebereich, Alarmstufe, Zeitgrenzen, Tagesstunden.
- *Stichworte*: Vorlage der AAO oder eigener Katalog – einzelne Stichworte anlegen, ändern, deaktivieren;
  Import aus CSV/Excel mit Vorschau.
- *Benutzer*: E-Mail-Adressen Rollen zuordnen (Wehrführer vergeben Erfasser und Benutzer, Wehrleiter alle
  Rollen ihrer VG). Den letzten Wehrleiter einer VG entfernt nur der Superadmin.
- *Wehren & VGs* (Superadmin): VGs und Wehren anlegen, umbenennen, einer VG zuordnen, deaktivieren und
  entfernen (die Daten wandern nach `daten/deleted/`, gelöscht wird nichts).

**Aussehen je Wehr:** Name, Logos (hell für die Kopfzeile, dunkel für die Fußzeile, Symbol für den
Browser-Tab; PNG, JPEG oder WebP bis 512 KB) und Farben. Aus der Hauptfarbe (und optional einer dunklen
Variante) leitet die App alle Farbtöne ab und hält die Kontraste lesbar; zu helle Farben für weiße
Schrift werden abgelehnt. Ohne eigene Farben gilt das bisherige Rot. Anmeldung und Gesamtansicht
einer VG sind neutral gestaltet.

**Umstellung einer bestehenden Installation:** Liegt beim Start noch `daten/einsaetze.db` (ohne
`daten/app.db`), übernimmt die App sie einmalig als Wehr „Rheinbrohl“ in der „VG Bad Hönningen“
(`daten/tenants/rheinbrohl/einsaetze.db`), samt den bisherigen Fahrzeugen, Orten und Logos. Die
Adressen aus `AUTH_EMAILS` werden dort Wehrführer. Die alte Datei bleibt als
`daten/einsaetze-vor-mandanten.db` liegen. Vorher `ADMIN_EMAILS` in `.env` setzen.

## Daten

| Pfad               | Inhalt                                               | Im Git |
|--------------------|------------------------------------------------------|:------:|
| `daten/`           | `app.db` (VGs, Wehren, Benutzer, Rollen, AVV), `tenants/<wehr>/einsaetze.db` je Wehr, `avv/` unterschriebene Verträge – der Datenbestand | nein |
| `Einsatzberichte/` | Berichts-PDFs und frühere `Einsatzübersicht_JJJJ.xlsx` (nur Ablage) | nein |

Die Datenbank ist maßgeblich. Einen Erstimport aus den Excel-Dateien gibt es nicht mehr: Eine neue
Datenbank startet leer, Einsätze kommen über die Berichts-PDFs hinein.

**Schema-Updates:** Beim Start bringt die App alle Datenbanken automatisch auf den
aktuellen Stand (Migrationen in `app/db.py`). Vor einem Update `daten/` sichern.

**Sicherung:** den ganzen Ordner `daten/` sichern, bei gestopptem Container oder je Datei mit
`sqlite3 <datei> ".backup <ziel>"` (die Datenbanken laufen im WAL-Modus, eine einfache Kopie im
laufenden Betrieb kann unvollständig sein). Zusätzlich gibt es „Einsätze → Excel-Export“.

## Datenschutz

Wer die App für andere Wehren betreibt, verarbeitet deren Daten im Auftrag (Art. 28 DSGVO).
Verantwortlich ist die Verbandsgemeinde als Träger der Feuerwehr, deshalb gilt ein
**Vertrag zur Auftragsverarbeitung (AVV) je VG**; er deckt alle ihre Wehren ab.

- **Sperre bis zum AVV:** Eine neue VG startet mit „AVV ausstehend“. Ihre Wehren sind für alle außer
  Superadmins gesperrt; Zugeordnete sehen nach der Anmeldung nur „Auftragsverarbeitung“.
- **Ablauf:** Wehrleitung, Statistik VG oder Wehrführer füllen die Angaben des Auftraggebers aus, die App
  erzeugt daraus den Vertrag (Vorlage `app/templates/avv_v2.html`, Prüfsumme des Textes wird gespeichert;
  ein mit einer älteren Vorlage erzeugter Vertrag wird weiter mit dieser angezeigt).
  Nach der Unterschrift wird das PDF hochgeladen (`daten/avv/<vg>/`, nie überschrieben, mit Prüfsumme)
  und/oder ein Link zur Ablage der VG hinterlegt. Der Superadmin bestätigt mit dem Datum der Unterschrift;
  erst dann sind die Wehren frei. Zurücknehmen (z. B. bei Kündigung) sperrt wieder. Jeder Schritt steht in
  einem Protokoll, an das nur angehängt werden kann.
- **Form:** Die DSGVO lässt ein elektronisches Format zu. Für Verpflichtungserklärungen einer Gemeinde kann
  die Gemeindeordnung aber eine handschriftliche Unterschrift (ggf. mit Dienstsiegel) verlangen – im
  Zweifel unterschriebenes Papier scannen oder eine qualifizierte elektronische Signatur nutzen und mit
  dem Datenschutzbeauftragten der VG abstimmen.
- **Eigenbetrieb:** Die bei der Umstellung übernommene VG Bad Hönningen steht auf „nicht erforderlich
  (Eigenbetrieb)“. Diesen Status setzt nur der Superadmin.
- **Angaben zum Auftragnehmer** (Anschrift, Vertretung, Hosting, Datensicherung) kommen aus `.env`
  (`DPA_*`, siehe [`.env.example`](.env.example)).
- **Löschung:** Entfernte Wehren liegen unter `daten/deleted/` und werden nach Vertragsende
  (spätestens drei Monate) von Hand gelöscht; unterschriebene Verträge unter `daten/avv/` bleiben für
  die Dauer der Aufbewahrungspflicht erhalten.

Die Vorlage ist ein Muster und keine Rechtsberatung.

## Bedienung

1. **PDF einlesen** (oben rechts): Bericht hineinziehen, mehrere PDFs auch als ZIP-Datei. Die Vorschau zeigt erkannte
   Felder, Fahrzeuge, Anwesenheit und Prüfhinweise. Berichte ohne Anmerkungen (keine
   Prüfhinweise, keine neuen Personen, keine Abweichungen) werden direkt übernommen, angezeigt
   werden nur die übrigen.
2. Felder wie EHF oder Zeiten bei Bedarf korrigieren, dann **In Statistik übernehmen**.
3. Ist die Einsatznummer schon erfasst, werden die Abweichungen angezeigt; mit
   „erfassten Einsatz durch diese PDF ersetzen“ lässt sich der Einsatz aktualisieren.

Was die einzelnen Felder und Kennzahlen bedeuten, erklärt die Online-Hilfe in der App.

## Entwicklung

Code ist englisch, Kommentare und Oberfläche sind deutsch.

Tests (pytest) laufen im Docker-Container:

```bash
docker build --target test -t pdf2einsatz-test . && docker run --rm pdf2einsatz-test
```

Lokal ohne Docker (Python 3.12):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
DATA_DIR=daten uvicorn app.main:app --reload --port 8112
```

## Projektstruktur

```text
app/
  main.py          FastAPI: Schnittstellen, Anmeldung, Zugriff je Wehr
  tenancy.py       VGs, Wehren, Rollen und Rechte; Fachkonfiguration laden und speichern
  auth.py          Anmeldung per Magic Link
  mail.py          Mailversand per SMTP mit DKIM, Prüfung von SPF/DKIM/DMARC
  domain.py        Fachkonstanten für alle Wehren (Stichworte, Einsatzarten, Standardwerte)
  tenant_config.py Fachkonfiguration einer Wehr (Fahrzeuge, Orte, Bedarfsplan) – auch für die Oberfläche
  legacy.py        Übernahme der bisherigen Einzel-Installation (FF Rheinbrohl)
  pdf_report.py    Einsatzbericht-PDF lesen
  report.py        Felder ableiten, Prüfhinweise, Bericht -> Einsatz
  metrics.py       Formeln der Einsatzübersicht (Kennzahlen, Statistik, Bedarfsplan, Anwesenheit)
  store.py         Datenbankzugriff, Namensabgleich Kameraden
  db.py            SQLite-Verbindungen und Migrationen (zentral und je Wehr)
  excel_layout.py  Spaltenaufbau der Einsatzübersicht, aus der Fahrzeugliste der Wehr
  excel_export.py  Excel-Export im Format der Einsatzübersicht, Gesamtmappe, Kennzahlen
  theme.py         Farben (abgeleitete Töne, Kontrastprüfung) und Logos einer Wehr
  admin.py         Verwaltung: Einstellungen, Logos, Stichworte, Rollen, VGs und Wehren
  dpa.py           Auftragsverarbeitungsvertrag je VG (Vorlage in templates/)
  names.py, timeutil.py, holidays.py   Namensvergleich, Zeiten, Feiertage RLP
static/
  index.html       Oberfläche
  app.js           Ansichten und Bedienung
  admin.js         Ansicht Verwaltung
  dpa.js           Ansicht Auftragsverarbeitung
  help.js          Texte und Logik der Online-Hilfe
  app.css          Gestaltung
  fonts/, img/     Schrift Sansation (SIL OFL), neutrales Signet
tests/             pytest (nur erfundene Daten)
Dockerfile, docker-compose.yml, requirements.txt, requirements-dev.txt
```

## Abweichungen zur Excel-Einsatzübersicht

Bewusste Unterschiede zu den Formeln der Excel-Datei:

- Das Blatt „Auswertung“ rechnet in Excel nicht (`#WERT!`, Formelbereiche `AO4:AO7`
  vs. `H4:H59`). Hier wird es korrekt gerechnet.
- Einsätze ohne Eintreffzeit zählt Excel mit 0 Minuten als „erreicht“ – hier werden sie
  im Bedarfsplan nicht berücksichtigt (die Anzahl wird angezeigt).
- Der Gesamtwert im Bedarfsplan ist über alle Einsätze gemittelt (Excel: Mittel der
  vier Zeitfenster).
- Tag/Nacht folgt überall der Excel-Regel (Spalte D): Ein Einsatzbeginn um genau 06:00:00
  oder 18:00:00 zählt zur Nacht, auch beim Anteil „tagsüber“.

## Lizenz

Internes Werkzeug der Freiwilligen Feuerwehr Rheinbrohl – keine Lizenz zur Weitergabe.
Die Schrift Sansation steht unter der SIL Open Font License; die Logos sind Eigentum der
FF Rheinbrohl.
