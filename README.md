# openEinsatzstatistik – Einsatzstatistik für Feuerwehren

Weboberfläche zur Einsatzstatistik für Freiwillige Feuerwehren, mandantenfähig und gruppiert nach
Verbandsgemeinde: Einsatzberichte (PDF oder Excel-Export) aus dem
BKS-Portal RLP einlesen, prüfen und in eine eigene Datenbank je Wehr übernehmen. Die Auswertungen
der bisherigen Excel-„Einsatzübersicht“ (Statistik, „Eintreffen und verfügbare Kräfte“, Anwesenheit)
rechnet die App aus den gespeicherten Einsätzen nach; Kennzahlen werden nie gespeichert.
Backend: FastAPI und SQLite, Oberfläche: Vanilla-JS ohne Build-Schritt.

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
- [Betrieb](#betrieb)
- [Entwicklung](#entwicklung)
- [Projektstruktur](#projektstruktur)
- [Abweichungen zur Excel-Einsatzübersicht](#abweichungen-zur-excel-einsatzübersicht)

## Funktionen

- **Bericht einlesen** – Einsatzberichte als PDF oder Excel-Export des BKS-Portals per Drag & Drop (einzeln,
  mehrere oder als ZIP), Vorschau mit Prüfhinweisen,
  Korrektur einzelner Felder vor dem Übernehmen, Abgleich mit bereits erfassten Einsätzen.
- **Navigation** – Hauptreiter *Übersicht*, *Einsätze*, *Auswertungen*, *Personal*, *Einstellungen*; mehrere
  Ansichten eines Reiters stehen als Unterreiter darunter (`NAV` in `app.js`). Alte Adressen
  (`#evaluation`, `#records`, `#admin`, `#dpa` …) funktionieren weiter. Die Auswahl oben heißt
  „Feuerwehr / Verbandsgemeinde“.
- **Übersicht** – Jahreskennzahlen, offene Aufgaben (Einsätze mit Prüfhinweisen oder fehlenden Angaben, Hinweise
  an die Wehr) und die Datenvollständigkeit je Angabe.
- **Auswertungen** – *Einsatzgeschehen*: Kennzahlen, „Eintreffen und verfügbare Kräfte“ (Eintreffquote des ersten
  eigenen Fahrzeugs; kein vollständiger Schutzzielnachweis, vgl. Abweichungen), Einsatzarten, Alarmstufen,
  Einsatzgebiet, Monate im Vorjahresvergleich, Uhrzeiten, Wochentage. *Zeiten & Kräfte*: Ausrückdauer, Anfahrtdauer
  je Fahrzeug und Zeit bis zum Eintreffen mit Median und 90. Perzentil, Kräfteaufbau nach 5/10/15 Minuten, Zeiten
  nach Tageszeit und Ort. *Belastung*: lange, nächtliche und Wochenend-Einsätze, Dauerverteilung, zeitliche
  Überschneidung. *Abbrüche & Anlagen*: Abbruchgründe und Brandmeldeanlagen (je Nummer bzw. Objekt).
  *Fahrzeuge & Atemschutz*: alarmiert, ausgerückt, eingesetzt oder nur bereit je Fahrzeug sowie Atemschutz-
  einsätze. *Brand & Rettung*: Zeit ab Eintreffen bis „Brand unter Kontrolle“ bzw. „Feuer aus“ und
  betroffene Personen. Jede Kennzahl nennt ihre Fallzahl („42 von 57 Einsätzen auswertbar“); Angaben, die
  im Bericht fehlen, zählen nie als 0 (Altdaten bekommen sie erst durch erneutes Einlesen). Jedes Diagramm
  ist auch als Tabelle abrufbar.
- **Einsätze** – Liste mit Suche und Filter, Details, Bearbeiten, Löschen sowie
  Excel-Export im Spaltenformat der Einsatzübersicht (A:AV + Anwesenheit). Für die VG als Unterreiter
  „Berichte abgleichen“ (früher Prüfprotokoll).
- **Personal** – Einsatzteilnahmen: Einsätze, Beteiligung, Stunden, Nacht- und Wochenendeinsätze je Person.
- **Online-Hilfe** – `?` im Kopf öffnet die gesammelte Hilfe beim Thema der aktuellen Ansicht bzw. des
  offenen Fensters (Felder und Kennzahlen haben kein eigenes Hilfesymbol). Im Hilfefenster stehen außerdem die **Neuigkeiten** (Änderungen für Anwender, ein Punkt am `?` zeigt
  ungelesene) und ein **Feedback**-Formular, das per Mail an die Superadmins (`ADMIN_EMAILS`) geht
  (nur mit Anmeldung und eingerichtetem Mailversand).

## Schnellstart

Voraussetzung: [Docker](https://docs.docker.com/get-docker/) mit Compose.

```bash
git clone https://github.com/jpolifka/openeinsatzstatistik.git
cd openeinsatzstatistik
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
| `ADMIN_EMAILS` | nein        | Superadmins, durch Komma getrennt. Gesetzt = Anmeldung an; alle anderen Benutzer werden den Wehren zugeordnet (siehe [Mandanten und Rollen](#mandanten-und-rollen)). Leer: die App startet nicht, außer mit `AUTH_DISABLED=1` (nur lokale Entwicklung, dann ist jeder Superadmin). |
| `BASE_URL`     | mit `ADMIN_EMAILS` | Öffentliche Adresse der App, z. B. `https://einsatz.example.org`. Daraus entsteht der Link in der Mail. Mit `https://` wird das Sitzungs-Cookie nur über HTTPS gesendet |
| `SMTP_HOST`    | nein        | SMTP-Server des Postfachs der eigenen Domain, z. B. `smtp.strato.de`. Leer = kein Versand, Link steht nur im Log (`docker compose logs`) |
| `SMTP_PORT`, `SMTP_SECURITY` | mit `SMTP_HOST` | `465` + `ssl` oder `587` + `starttls` |
| `SMTP_USER`, `SMTP_PASSWORD` | mit `SMTP_HOST` | Zugangsdaten des Postfachs |
| `MAIL_FROM`    | mit `SMTP_HOST` | Absender, z. B. `Einsatzstatistik <statistik@example.org>` – Adresse des Postfachs oder ein Alias davon |
| `DKIM_SELECTOR`, `DKIM_KEY_FILE` | empfohlen | DKIM-Signatur durch die App, siehe [Mailversand](#mailversand) |
| `DPA_*`        | für den AVV | Angaben zum Auftragnehmer, Hosting, Datensicherung, Mail-Anbieter (siehe [Datenschutz](#datenschutz)) |
| `SECRET_KEY`   | nein        | Schlüssel für die Anmeldelinks. Leer = wird als `daten/session.key` erzeugt |
| `APP_BIND`     | nein        | Host-Adresse der Portbindung, Standard `127.0.0.1`; `0.0.0.0` nur bei bewusst benötigtem direktem Netzwerkzugriff |
| `APP_UID`, `APP_GID` | nein  | Container-Benutzer übersteuern (Standard: Besitzer von `daten/`, root ist nicht erlaubt) |
| `KEEP_UPLOADS` | nein        | Fehlersuche: `1` legt jeden hochgeladenen Bericht zusätzlich in `daten/debug-reports` ab (enthält Namen, wird nach 3 Tagen gelöscht, Warnung im Log) |

**Reverse Proxy:** Die App muss an der Wurzel der Domain laufen (nicht unter einem Unterpfad).
Weiterleitungen sind relative Pfade, `X-Forwarded-*`-Header werden nicht benötigt. Bei nginx
`client_max_body_size` für den Upload-Weg `/api/reports` auf etwa 105 MB setzen (Berichte und ZIP-Dateien, höchstens 100 MB je Upload), sonst genügen 2 MB – die App lehnt größere Anfragen an allen anderen Wegen ab (`app/request_limits.py`). Die Beispielkonfiguration in `deploy/nginx/` macht das je `location`.

**Anmeldung:** Ist `ADMIN_EMAILS` gesetzt, fragt die App nach der E-Mail-Adresse und schickt
einen Anmeldelink (15 Minuten gültig, nur einmal benutzbar). Die Sitzung hält höchstens 30 Tage (nach 7 Tagen ohne Nutzung endet sie früher) und liegt serverseitig: „Abmelden“ beendet sie sofort, Superadmins können Sitzungen unter Einstellungen → Sitzungen beenden.
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
Zeitgrenzen). Wer sich anmeldet, sieht nur die Wehren, denen er zugeordnet ist; bei mehreren
gibt es oben eine Auswahl.

Rechte und Rollen (`app/rbac.py`): Die **Rechte** sind fest (Auswertung, Eintreffen und Kräfte, Einsätze ansehen,
exportieren, einlesen, bearbeiten, löschen, Anwesenheit sehen/bearbeiten, Einstellungen, Stichworte,
Gesamtansicht, Prüfprotokoll, Gebühren, AVV, Zuordnungen sehen, Rollen vergeben, Rollen pflegen). Eine
**Rolle** bündelt Rechte für einen Bereich – eine Wehr oder eine VG (gilt dann in allen Wehren der VG).
Rollen erben von einer anderen Rolle desselben Bereichs, eine Person kann mehrere Rollen haben. Startbestand
(entspricht dem früheren festen Modell):

| Rolle | Bereich | erbt von | Statistik | Einsätze | Anwesenheit und Personal | Berichte einlesen, bearbeiten | Verwaltung | vergibt |
|---|---|---|:-:|:-:|:-:|:-:|:-:|---|
| Superadmin (`ADMIN_EMAILS`) | alle | – | ✓ | ✓ | ✓ | ✓ | ✓ | alles |
| Wehrleiter | VG | Statistik VG | ✓ | ✓ | – | ✓ | ✓ (+ Rollen der VG) | alle Rollen |
| Statistik VG (z. B. Bürgermeister) | VG | – | ✓ | – | – | – | – | – |
| Wehrführer | Wehr | Erfasser | ✓ | ✓ | ✓ | ✓ | ✓ | Erfasser, Benutzer |
| Erfasser | Wehr | Benutzer | ✓ | ✓ | ✓ | ✓ | – | – |
| Benutzer | Wehr | – | ✓ | – | – | – | – | – |

**Eigene Rollen:** Der Wehrleiter legt unter Verwaltung → Rollen eigene Rollen für seine VG an (z. B.
„Gruppenführer“: erbt Benutzer, darf Einsätze einlesen und bearbeiten, aber nicht löschen), der Superadmin Rollen für alle VGs und ändert die
Systemrollen. Die **Verteilung** legt fest, welche Rolle welche Rollen vergeben darf. Änderungen gelten
sofort; Vergaben und Rollenänderungen stehen im Protokoll (nur anhängbar).

**Leitplanken** (fest im Code): Die Anwesenheit (Namen der Personen) gibt es nur für Rollen einer
Wehr – der Wehrleiter sieht bei einem Einsatz nur die Anzahl der Anwesenden; der Excel-Export enthält
für ihn kein Blatt Anwesenheit, Personal und die Anwesenheitsübersicht der Auswertung fehlen.
Auch Einheitsführung und Einsatzleiter (Namen) sieht nur, wer die Anwesenheit sehen darf.
Eigene Zuordnungen und Rollen, die man selbst hat (auch über Vererbung), ändert nur jemand anderes.
Rollen nur mit Statistik sehen keine Namen: Einsatzliste und Excel-Export sind für sie ebenfalls
gesperrt. Geprüft wird im Backend, die Oberfläche blendet nur aus.

**Gesamtansicht einer VG** (Recht „Gesamtansicht“: Wehrleiter, Statistik VG, Superadmin; oben „Verbandsgemeinde · …“):
- Auswertung über alle Wehren der VG, auf einzelne Wehren filterbar. Ein Einsatz mehrerer Wehren
  zählt bei jeder Wehr (Beteiligungen); die große Zahl zählt ihn über den Stammdatensatz im
  BKS-Portal bzw. die Einsatznummer der Leitstelle nur einmal. „Eintreffen und verfügbare Kräfte“ wertet jede Wehr
  mit ihren eigenen Orten aus.
- Einsatzliste aller Wehren mit Markierung der Wehr; Personal gibt es nur je Wehr.
- Excel-Export als eine Mappe mit Übersicht und je Wehr Einsatzübersicht (Anwesenheit nicht für
  den Wehrleiter).
  „Kennzahlen (Excel)“ enthält nur die Zahlen je Wehr, ohne Namen.
- „Drucken / PDF“ öffnet die Druckansicht der Auswertung (im Druckdialog als PDF sichern).
- Bericht einlesen verteilt die Berichte auf die passende Wehr (über die berichtende Einheit; die
  eigenen Fahrzeuge im Bericht nur bei Wehren ohne BKS-Kennung). Haben andere Wehren denselben
  Einsatz schon erfasst, zeigt die Vorschau „gemeinsamer Einsatz mit …“.

**Einstellungen** (Reiter „Einstellungen“ mit einem Verwaltungsrecht, im Startbestand Wehrführer, Wehrleiter und Superadmin).
Oben wählt man eine Feuerwehr oder die Verbandsgemeinde; die Bereiche wechseln diese Auswahl nie. Bei der
Verbandsgemeinde legen dieselben Bereiche die **Vorgaben der VG** für alle ihre Wehren fest (Recht
„Einstellungen“ bzw. „Stichwortkatalog“ in einer Rolle der VG) und zeigen alle Wehren auf einmal. Eine Wehr
übernimmt die Vorgaben und kann bei sich abweichen; an jedem Wert steht „von der VG“ oder „abweichend“.
- *Allgemein*: Name und Logos der Wehr, Farben (Vorgabe der VG; Farbwähler, Hex oder RGB, mit Vorschau und
  Kontrastprüfung).
- *Fahrzeuge*: Reihenfolge, Bezeichnung, Dienstzeitraum („im Dienst ab“, „außer Dienst ab“), Nachfolger,
  Zählung in der Gesamtstärke, Ersatzfahrzeuge. Bei der Verbandsgemeinde die Fahrzeuge aller Wehren in einer Tabelle,
  mit Wechsel der Wehr und den noch nicht zugeordneten Funkrufnamen aus Berichten. Neue eigene Fahrzeuge
  aus BKS-Berichten nimmt die App beim Übernehmen automatisch auf.
- *BKS-Kennung*: Kennung der VG (z. B. NR#.ABC) und Standort der Wehr ergeben die Einheit im Bericht
  („FW NR#.ABC 02“) und die eigenen Funkrufnamen; FEZ-Kennung, Nummerierung; Testfeld.
- *Orte & Zeitgrenzen*: Orte, Ausrückebereich je Wehr, Alarmstufe, Zeitgrenzen, Tagesstunden.
- *Stichworte*: Katalog der VG (Vorlage der AAO oder eigener) – Stichworte anlegen, ändern, deaktivieren,
  Import aus CSV/Excel mit Vorschau; je Wehr Abweichungen (gilt hier nicht, eigene Bezeichnung, eigene
  Stichworte).
- *Gebührenordnung* (nur Verbandsgemeinde): Fassungen der Satzung über den Kostenersatz.
- *Benutzer*: E-Mail-Adressen Rollen zuordnen – nach der Verteilung der eigenen Rolle, nie sich selbst.
  „Rechte“ zeigt, was eine Person darf und über welche Rolle; dazu das Protokoll der Vergaben.
- *Rollen*: Rechtematrix aller Rollen; eigene Rollen anlegen, ändern, kopieren und löschen (siehe oben).
- *Wehren & VGs* (Superadmin): VGs und Wehren anlegen, umbenennen, einer VG zuordnen, deaktivieren und
  entfernen (die Daten wandern nach `daten/deleted/`, gelöscht wird nichts).

**Aussehen je Wehr:** Name, Logos (hell für die Kopfzeile, dunkel für die Fußzeile, Symbol für den
Browser-Tab; PNG, JPEG oder WebP bis 512 KB) und Farben. Aus der Hauptfarbe (und optional einer dunklen
Variante) leitet die App alle Farbtöne ab und hält die Kontraste lesbar; zu helle Farben für weiße
Schrift werden abgelehnt. Ohne eigene Farben gilt das bisherige Rot. Anmeldung und Gesamtansicht
einer VG sind neutral gestaltet.

**Umstellung einer bestehenden Installation:** Liegt beim Start noch `daten/einsaetze.db` (ohne
`daten/app.db`), übernimmt die App sie einmalig als Wehr „Altenau“ in der „VG Nordkreis“
(`daten/tenants/altenau/einsaetze.db`). Fahrzeuge, Orte und Logos sind danach neu in den Einstellungen anzulegen. Die
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
- **Ablauf:** Verbandsgemeinde, Statistik VG oder Wehrführer füllen die Angaben des Auftraggebers aus, die App
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
- **Eigenbetrieb:** Die bei der Umstellung übernommene VG Nordkreis steht auf „nicht erforderlich
  (Eigenbetrieb)“. Diesen Status setzt nur der Superadmin.
- **Angaben zum Auftragnehmer** (Anschrift, Vertretung, Hosting, Datensicherung) kommen aus `.env`
  (`DPA_*`, siehe [`.env.example`](.env.example)).
- **Löschung:** Entfernte Wehren liegen unter `daten/deleted/` und werden nach Vertragsende
  (spätestens drei Monate) von Hand gelöscht; unterschriebene Verträge unter `daten/avv/` bleiben für
  die Dauer der Aufbewahrungspflicht erhalten.

Die Vorlage ist ein Muster und keine Rechtsberatung.

## Bedienung

1. **Bericht einlesen** (oben rechts): Bericht hineinziehen, mehrere auch als ZIP-Datei. Die Vorschau zeigt erkannte
   Felder, Fahrzeuge, Anwesenheit und Prüfhinweise; was zu prüfen ist, steht
   oben in der Karte. Berichte ohne Anmerkungen (keine Prüfhinweise, keine neuen Personen, keine
   Abweichungen) lassen sich mit **n Berichte ohne Hinweise übernehmen** in einem Schritt
   speichern; übernommen wird nie ohne ausdrücklichen Klick.
2. Felder wie Einheitsführung oder Zeiten bei Bedarf korrigieren, dann **In Statistik übernehmen**.
3. Ist der Bericht schon erfasst (gleiche Berichtsnummer im BKS-Portal, bei älteren Einsätzen
   gleiche Nr. und Jahr), werden die Abweichungen angezeigt; **Aktualisieren** übernimmt den
   neuen Stand. Der Einsatz behält seine ID, manuell ergänzte Fahrzeuge und Personen bleiben.

**Excel-Export statt PDF:** Das BKS-Portal exportiert einen Bericht auch als Excel-Datei (Blätter
„Einsatzbericht“, „Ausger. Fahrzeuge und Personen“, „Anwesenheitsliste“). Sie enthält dieselben Angaben
wie die PDF und wird genauso eingelesen. Weil die Unterblätter nicht auf den Bericht verweisen, wird nur
ein Bericht je Datei angenommen. In der Anwesenheitsliste stehen die Werte eine Spalte rechts von ihrer
Überschrift; die App richtet die Spalten am Inhalt aus.

**Mehrfachberichte:** Ein Einsatz hat im BKS-Portal einen *Stammdatensatz* (Verbandsgemeinde, alle
Fahrzeuge mit den Zeiten der Leitstelle, keine Personen) und je beteiligter Einheit einen Haupt-
bzw. Nebenbericht, der auf ihn verweist. Beim Einlesen wird der Stammdatensatz zentral bei der VG
gespeichert, jeder Bericht kommt zu seiner Wehr. Gehört ein Bericht zu einer anderen Wehr der VG,
für die der Hochladende keine Schreibrechte hat, wird er dort zur Übernahme abgelegt. Berichte von
Einheiten ohne Wehr (z. B. die FEZ) werden mit Hinweis übersprungen. Haupt- und Nebenberichte haben
einen Link ins BKS-Portal.

**Hinweise** (oben in jeder Ansicht) bekommt eine Wehr, wenn jemand ohne eigene Rolle dort einen
ihrer Einsätze einliest (z. B. der Wehrleiter), wenn ein Bericht einer anderen Wehr für ihre
Fahrzeuge andere Werte nennt, wenn ihre Fahrzeuge laut Stammdatensatz ausgerückt sind, sie aber
noch keinen Bericht hat, und wenn ein Bericht zur Übernahme bereitliegt. Die Texte enthalten keine
Namen; erledigt markiert, wer die Einsätze der Wehr bearbeiten darf.

**Berichte abgleichen** (früher Prüfprotokoll; Wehrleiter, Gesamtansicht der VG, Unterreiter von „Einsätze“): je Einsatz mit Stammdatensatz die Berichte
der Wehren und die Befunde – Stärke und Zeiten der Fahrzeuge im Vergleich zum Stammdatensatz,
anderes Stichwort, fehlende, unbearbeitete (ohne Anwesenheit) und Berichte ohne Nr. „Als geprüft
markieren“ gilt für den jetzigen Stand der Befunde; „Drucken / PDF“ für die Ablage.

**Einsatz bearbeiten** (Einsätze → aufklappen → Bearbeiten): Felder, Fahrzeuge (dabei, Stärke,
Ausrücken, Eintreffen) und Anwesenheit (Person entfernen, vorhandene Person oder neue Person
„Nachname, Vorname“ hinzufügen). Manuell ergänzte Fahrzeuge und Personen bleiben erhalten, wenn der
Bericht später erneut eingelesen wird; Werte von Fahrzeugen aus der PDF ersetzt der neue Bericht.

**Einsatznummern** (Verwaltung → BKS-Kennung): „aus dem Bericht“ übernimmt die Einsatzbericht-Nr.;
fehlt sie (z. B. bei selbst angelegten Brandsicherheitswachen), vergibt die App die nächste freie.
„nach Datum durchnummerieren“ vergibt alle Nummern nach dem Einsatzbeginn – ein später eingelesener
Einsatz rückt an seine Stelle, die folgenden Nummern verschieben sich.

**Eintreffen und verfügbare Kräfte:** Rollen mit „Eintreffen und Kräfte ohne Freigabe sehen“ (Wehrführer, Wehrleiter)
sehen die Auswertung immer; mit „Eintreffen und Kräfte freigeben“ geben sie sie über „für alle freigegeben“
(Karte im Einsatzgeschehen oder Einstellungen → Orte & Zeitgrenzen) für die übrigen Rollen frei. Ohne
Freigabe fehlt sie für diese auch in der Gesamtansicht, in *Zeiten & Kräfte* und im Kennzahlen-Export. (Die
Schlüssel der Rechte, z. B. `plan.release`, blieben unverändert.)

**Kostenersatz** (Recht „Prüfprotokoll und Kostenersatz“, Gebührenordnung mit „Gebührenordnung der VG“; im Startbestand der Wehrleiter): Verwaltung → Gebührenordnung pflegt die Satzung der VG in Fassungen
mit „gültig ab“ (für die VG Nordkreis vorbelegt mit der Satzung vom 16.05.2024 – Beginn der
Gültigkeit bitte prüfen). Im Prüfprotokoll rechnet „Kostenersatz berechnen“ einen Einsatz über alle
beteiligten Wehren: Fahrzeuge vom Ausrücken bis zum Einsatzende des Fahrzeugs, Einsatzkräfte von der
Alarmierung bis zum Einsatzende, halbstündlich aufgerundet; BSW mit eigenem Satz, Fehlalarm einer
BMA höchstens die Pauschale, Auslagen mit Verwaltungszuschlag, Umsatzsteuer wählbar. Den
Fahrzeugtyp liefert die Bezeichnung in der Fahrzeugliste der Wehr (z. B. „HLF 20“). Es wird nichts
gespeichert; „Drucken / PDF“ für die Ablage.

**Personal:** Ein Klick auf eine Person zeigt ihre Einsätze im Jahr, ein Klick auf einen Einsatz
öffnet ihn in der Einsatzliste.

Was die einzelnen Felder und Kennzahlen bedeuten, erklärt die Online-Hilfe in der App.

## Betrieb

- **Container:** läuft nie als root, sondern als Besitzer von `daten/` (`docker-entrypoint.sh`), mit
  Healthcheck (`/health`, ohne Anmeldung erreichbar) und Ressourcenlimits. Der Port ist standardmäßig an
  `127.0.0.1` gebunden (`APP_BIND`). Eine öffentliche `BASE_URL` verlangt `ADMIN_EMAILS`.
- **Ein Worker:** Vorschauen eingelesener Berichte liegen nur im Speicher eines Prozesses (1 Stunde gültig,
  an Benutzer und Wehr gebunden). Die App läuft deshalb mit genau einem uvicorn-Worker; horizontale
  Skalierung braucht erst einen gemeinsamen Speicher.
- **Einlesen:** Dateien werden in kurzlebigen Prozessen gelesen (höchstens zwei gleichzeitig, 45 Sekunden,
  CPU- und Speicherlimit); je Upload höchstens 100 MB, je Benutzer ein Upload gleichzeitig. Die
  Oberfläche liest im Hintergrund und fragt den Fortschritt ab, damit Proxys mit kurzem Zeitlimit
  (Cloudflare, ca. 100 s) nicht mit 524 abbrechen.
- **Updates:** Migrationen laufen beim Start und sind nur anhängbar; eine neuere Datenbank verhindert den
  Start einer älteren Version (kein Downgrade). Vor jedem Update `daten/` sichern.
- **Abhängigkeiten:** `requirements.txt` → `requirements.lock` mit SHA256-Prüfsummen (das Image installiert
  mit `--require-hashes`); beim Ändern das Lock neu erzeugen.
- **CI** (GitHub Actions): `checks.yml` prüft Python 3.14 (wie das Image), Lock, Sicherheitsaudit,
  JavaScript-Syntax und Frontend-Tests; `audit.yml` wiederholt das Sicherheitsaudit wöchentlich, damit neue
  Schwachstellen auch ohne Codeänderung auffallen.

Der Stand der Härtung steht in [REVIEW_IMPLEMENTATION.md](REVIEW_IMPLEMENTATION.md) (Rückblick auf den
Review, kein Betriebshandbuch).

## Entwicklung

Code ist englisch (Bezeichner, Datenbank, API, CSS), Kommentare und Oberfläche sind deutsch. Gearbeitet wird
mit Docker; `static/` ist nicht gemountet, sondern ins Image kopiert – nach Änderungen an Python- oder
Frontend-Dateien ist `docker compose up -d --build` nötig.

```bash
# Python-Tests (pytest), einzelner Test mit -k, Abdeckung mit --cov
docker build --target test -t openeinsatzstatistik-test . && docker run --rm openeinsatzstatistik-test
docker run --rm openeinsatzstatistik-test python -m pytest -q tests/test_rbac.py -k <name>
docker run --rm openeinsatzstatistik-test python -m pytest -q --cov=app --cov-branch --cov-report=term-missing:skip-covered

# JavaScript: Syntax und Frontend-Tests (wie in der CI)
docker run --rm -v "$PWD/static:/s:ro" node:22-alpine node --check /s/app.js
docker run --rm -v "$PWD:/w:ro" -w /w node:22-alpine node --test tests/frontend/*.test.cjs
```

Lokal ohne Docker (Python 3.14):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
DATA_DIR=daten uvicorn app.main:app --reload --port 8112
```

Konventionen: Neue Rechte stehen in `rbac.PERMISSIONS` (Zuordnung zu Systemrollen per Migration) mit
Hilfetext `perm_…` in `help.js`; neue Endpunkte mit Einsatzdaten gehören in die Rechtematrix
(`tests/test_access.py`). Sichtbare Änderungen bekommen einen Eintrag in `static/changelog.js`. Neue
Einsatzfelder laufen über Migration, `incident_schema.py`, beide Leser (PDF und Excel) und `report.derive`.
Tests und Beispiele enthalten nur erfundene Namen.

## Projektstruktur

```text
app/
  main.py          FastAPI: Schnittstellen, Anmeldung, Zugriff je Wehr
  tenancy.py       VGs, Wehren, Zuordnungen und Zugriff je Anfrage; Fachkonfiguration laden und speichern
  rbac.py          Rechtekatalog, Rollen mit Vererbung und Verteilung, Leitplanken, Protokoll
  auth.py          Anmeldung per Magic Link
  mail.py          Mailversand per SMTP mit DKIM, Prüfung von SPF/DKIM/DMARC
  domain.py        Fachkonstanten für alle Wehren (Stichworte, Einsatzarten, Standardwerte)
  tenant_config.py Fachkonfiguration einer Wehr (Fahrzeuge, Orte, Zeitgrenzen) – auch für die Oberfläche
  legacy.py        Übernahme der bisherigen Einzel-Installation (Wehr Altenau)
  pdf_report.py    Einsatzbericht-PDF lesen
  xlsx_report.py   Einsatzbericht als Excel-Export des BKS-Portals lesen
  report.py        Felder ableiten, Prüfhinweise, Bericht -> Einsatz
  records.py       Stammdatensätze, Verzeichnis der Berichte, Abgleich/Prüfprotokoll, Hinweise je VG
  fees.py          Gebührenordnungen der VG und Berechnung des Kostenersatzes
  metrics.py       Formeln der Einsatzübersicht (Kennzahlen, Statistik, Eintreffen/Kräfte, Anwesenheit) sowie
                   Zeiten, Kräfteaufbau, Belastung und Datenabdeckung (`timing`, `workload`, `coverage`)
  store.py         Datenbankzugriff, Namensabgleich Personen
  db.py            SQLite-Verbindungen und Migrationen (zentral und je Wehr)
  excel_layout.py  Spaltenaufbau der Einsatzübersicht, aus der Fahrzeugliste der Wehr
  excel_export.py  Excel-Export im Format der Einsatzübersicht, Gesamtmappe, Kennzahlen
  theme.py         Farben (abgeleitete Töne, Kontrastprüfung) und Logos einer Wehr
  admin/           Verwaltung (ein Modul je Thema): Einstellungen, Logos, Stichworte, Rollen, VGs und Wehren
  api/             Endpunkte mit Einsatzdaten: Auswertung, Einsätze, Berichte, Prüfprotokoll, Export
  importing.py     Berichte einlesen (PDF, Excel, ZIP), Zuordnung zur Wehr, Weitergabe, Nachbearbeitung
  preview_sessions.py  Vorschauen im Speicher, Lese-Aufträge, Upload-Plätze
  parser_worker.py Dateileser in kurzlebigen Prozessen mit Zeit- und Speicherlimit
  bks_common.py    formatunabhängige BKS-Regeln für PDF und Excel
  incident_schema.py gemeinsamer Feldkatalog (Formular, API, Speicherung)
  import_queue.py  Outbox für die Nacharbeit nach dem Speichern (idempotent, mit Wiederholung)
  tenant_lifecycle.py Wehren anlegen und archivieren (wiederaufnehmbar, nichts wird gelöscht)
  request_limits.py Größenlimit je Weg schon beim Lesen der Anfrage
  feedback.py      Feedback aus der Oberfläche per Mail an die Superadmins
  dpa.py           Auftragsverarbeitungsvertrag je VG (Vorlage in templates/)
  names.py, timeutil.py, holidays.py   Namensvergleich, Zeiten, Feiertage RLP
static/
  index.html       Oberfläche
  app.js           Kern: Zustand, Hilfsfunktionen, Diagramme, Reiter, Ereignisse, Tastenkürzel
  evaluation.js    Ansicht Einsatzgeschehen
  analysis.js      Übersicht, Zeiten & Kräfte, Belastung
  operations.js    Abbrüche & Anlagen, Fahrzeuge & Atemschutz, Brand & Rettung
  incident_list.js, incident_detail.js   Einsatzliste, Detail, Bearbeiten, Löschen
  members.js, keyword_search.js          Personal, Stichwortsuche im Formular
  imports.js       Berichte einlesen: Darstellung und Zustand
  records.js       Hinweise an die Wehr, Ansicht Prüfprotokoll
  admin.js, admin_views.js   Verwaltung: Aktionen und Zustand, Darstellung
  dpa.js           Ansicht Auftragsverarbeitung
  help.js          Texte und Logik der Online-Hilfe
  changelog.js     Neuigkeiten für Anwender
  app.css          Gestaltung
  fonts/, img/     Schrift Sansation (SIL OFL), neutrales Signet
tests/             pytest (nur erfundene Daten), tests/frontend/ Zustandstests der Oberfläche (node --test)
deploy/nginx/      Beispielkonfiguration für den Reverse Proxy
Dockerfile, docker-compose.yml, requirements.txt, requirements.lock, requirements-dev.txt
CLAUDE.md          Hinweise zur Architektur für die Arbeit mit Claude Code
```


## Lizenz

Der Quellcode steht unter der [GNU Affero General Public License 3.0](LICENSE) (Hinweise in [NOTICE](NOTICE)): Er darf
frei genutzt, verändert und weitergegeben werden, auch von Gemeinden und Verbänden im eigenen Betrieb. Wer eine
veränderte Fassung als Dienst anbietet (auch gehostet gegen Entgelt), muss den Quelltext dieser Fassung seinen Nutzern
unter derselben Lizenz zur Verfügung stellen. Der Link „openEinsatzstatistik – freie Software“ am Seitenende führt zum
Quellcode; wer die App verändert betreibt, muss ihn auf seine Fassung zeigen lassen.
Logos und Namen von Feuerwehren sind nicht Teil des Projekts (jede Wehr lädt ihr eigenes Logo in den Einstellungen hoch) und gehören den jeweiligen Wehren.
Die Schrift Sansation steht unter der SIL Open Font License.

Mitmachen und Sicherheitsmeldungen: [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md).
Demo mit erfundenen Daten: `docker compose -f docker-compose.demo.yml up --build` → http://localhost:8113.
Nutzertests und Verbreitung: [docs/](docs/).
