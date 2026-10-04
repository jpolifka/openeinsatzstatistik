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
  Überschneidung. Jede Kennzahl nennt ihre Fallzahl („42 von 57 Einsätzen auswertbar“). Jedes Diagramm ist auch
  als Tabelle abrufbar.
- **Einsätze** – Liste mit Suche und Filter, Details, Bearbeiten, Löschen sowie
  Excel-Export im Spaltenformat der Einsatzübersicht (A:AV + Anwesenheit). Für die VG als Unterreiter
  „Berichte abgleichen“ (früher Prüfprotokoll).
- **Personal** – Einsatzteilnahmen: Einsätze, Beteiligung, Stunden, Nacht- und Wochenendeinsätze je Person.
- **Online-Hilfe** – `?` im Kopf öffnet die Hilfe beim Thema der aktuellen Ansicht bzw. des offenen
  Fensters; das `?` neben Feldern und Kennzahlen erklärt den jeweiligen Wert und springt zur passenden Stelle.
  Im Hilfefenster stehen außerdem die **Neuigkeiten** (Änderungen für Anwender, ein Punkt am `?` zeigt
  ungelesene) und ein **Feedback**-Formular, das per Mail an die Superadmins (`ADMIN_EMAILS`) geht
  (nur mit Anmeldung und eingerichtetem Mailversand).

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
- **Eigenbetrieb:** Die bei der Umstellung übernommene VG Bad Hönningen steht auf „nicht erforderlich
  (Eigenbetrieb)“. Diesen Status setzt nur der Superadmin.
- **Angaben zum Auftragnehmer** (Anschrift, Vertretung, Hosting, Datensicherung) kommen aus `.env`
  (`DPA_*`, siehe [`.env.example`](.env.example)).
- **Löschung:** Entfernte Wehren liegen unter `daten/deleted/` und werden nach Vertragsende
  (spätestens drei Monate) von Hand gelöscht; unterschriebene Verträge unter `daten/avv/` bleiben für
  die Dauer der Aufbewahrungspflicht erhalten.

Die Vorlage ist ein Muster und keine Rechtsberatung.

## Bedienung

1. **Bericht einlesen** (oben rechts): Bericht hineinziehen, mehrere auch als ZIP-Datei. Die Vorschau zeigt erkannte
   Felder, Fahrzeuge, Anwesenheit und Prüfhinweise. Berichte ohne Anmerkungen (keine
   Prüfhinweise, keine neuen Personen, keine Abweichungen) werden direkt übernommen, angezeigt
   werden nur die übrigen.
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
mit „gültig ab“ (für die VG Bad Hönningen vorbelegt mit der Satzung vom 16.05.2024 – Beginn der
Gültigkeit bitte prüfen). Im Prüfprotokoll rechnet „Kostenersatz berechnen“ einen Einsatz über alle
beteiligten Wehren: Fahrzeuge vom Ausrücken bis zum Einsatzende des Fahrzeugs, Einsatzkräfte von der
Alarmierung bis zum Einsatzende, halbstündlich aufgerundet; BSW mit eigenem Satz, Fehlalarm einer
BMA höchstens die Pauschale, Auslagen mit Verwaltungszuschlag, Umsatzsteuer wählbar. Den
Fahrzeugtyp liefert die Bezeichnung in der Fahrzeugliste der Wehr (z. B. „HLF 20“). Es wird nichts
gespeichert; „Drucken / PDF“ für die Ablage.

**Personal:** Ein Klick auf eine Person zeigt ihre Einsätze im Jahr, ein Klick auf einen Einsatz
öffnet ihn in der Einsatzliste.

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
  tenancy.py       VGs, Wehren, Zuordnungen und Zugriff je Anfrage; Fachkonfiguration laden und speichern
  rbac.py          Rechtekatalog, Rollen mit Vererbung und Verteilung, Leitplanken, Protokoll
  auth.py          Anmeldung per Magic Link
  mail.py          Mailversand per SMTP mit DKIM, Prüfung von SPF/DKIM/DMARC
  domain.py        Fachkonstanten für alle Wehren (Stichworte, Einsatzarten, Standardwerte)
  tenant_config.py Fachkonfiguration einer Wehr (Fahrzeuge, Orte, Zeitgrenzen) – auch für die Oberfläche
  legacy.py        Übernahme der bisherigen Einzel-Installation (FF Rheinbrohl)
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
  dpa.py           Auftragsverarbeitungsvertrag je VG (Vorlage in templates/)
  names.py, timeutil.py, holidays.py   Namensvergleich, Zeiten, Feiertage RLP
static/
  index.html       Oberfläche
  app.js           Kern: Zustand, Hilfsfunktionen, Diagramme, Reiter, Ereignisse, Tastenkürzel
  evaluation.js    Ansicht Einsatzgeschehen
  incident_list.js, incident_detail.js   Einsatzliste, Detail, Bearbeiten, Löschen
  members.js, keyword_search.js          Personal, Stichwortsuche im Formular
  records.js       Hinweise an die Wehr, Ansicht Prüfprotokoll
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
  in „Eintreffen und verfügbare Kräfte“ nicht berücksichtigt (die Anzahl wird angezeigt).
- Der Gesamtwert dort ist über alle Einsätze gemittelt (Excel: Mittel der
  vier Zeitfenster).
- Tag/Nacht folgt überall der Excel-Regel (Spalte D): Ein Einsatzbeginn um genau 06:00:00
  oder 18:00:00 zählt zur Nacht, auch beim Anteil „tagsüber“.
- „Eintreffen und verfügbare Kräfte“ (früher „Feuerwehrbedarfsplan Pos. 8.4“) ist eine Eintreffquote des ersten
  eigenen Fahrzeugs mit Personenzahlen; Funktionen, Ausrüstung und Qualifikation (FwDV 3) sind nicht erfasst. Sie
  ersetzt keinen Feuerwehrbedarfsplan. Spalten- und Kartenbezeichnungen: Azeit → Ausrückdauer, Ezeit → Zeit bis
  Eintreffen, EHF → Einheitsführung (auch im Excel-Export).
- Die Zeitgrenze ist 10 Minuten (Einsatzgrundzeit nach der Feuerwehrverordnung RLP seit 26.09.2025); die frühere Auswahl 8 Minuten entfällt
  (Spalten „10 Min. erreicht“ und „Stärke nach 10 Min.“ im Export).

## Lizenz

Internes Werkzeug der Freiwilligen Feuerwehr Rheinbrohl – keine Lizenz zur Weitergabe.
Die Schrift Sansation steht unter der SIL Open Font License; die Logos sind Eigentum der
FF Rheinbrohl.
# Review-Härtung und Rollout

Der Branch `fix/comprehensive-review` enthält Sicherheits-, Daten- und UI-Korrekturen.
Umsetzungsstand, verbleibende Arbeiten und wichtige Hinweise zu Datenbanksicherung,
Schema-Versionen, Container-Benutzer und Portbindung stehen in
[REVIEW_IMPLEMENTATION.md](REVIEW_IMPLEMENTATION.md).
