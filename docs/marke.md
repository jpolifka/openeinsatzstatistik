# Marke: openEinsatzstatistik

Dieses Dokument legt fest, wie das Projekt auftritt. Formen und Aufbau folgen dem Erscheinungsbild von **Polifka IT Beratung**, die Farben den Schulungsunterlagen des Landesamts (siehe unten)
(weich gerundete Formen, ruhiger Aufbau), damit Projekt und Anbieter erkennbar zusammengehören. Alle Dateien liegen in [`brand/`](../brand/).

![Logo](../brand/logo-horizontal.svg)

## Name und Ton

- **Schreibweise:** `openEinsatzstatistik` in einem Wort, „open“ klein, „E“ groß. Nicht „Open Einsatzstatistik“, nicht „OpenEinsatzstatistik“.
  Im Fließtext darf „die Einsatzstatistik“ stehen, wenn klar ist, welche gemeint ist. Eine Kurzform wird nicht eingeführt.
- **Kurzbeschreibung:** *Einsatzstatistik für Feuerwehren. Aus dem BKS-Einsatzbericht wird die Auswertung.*
- **Unterzeile im Logo:** FREIE EINSATZSTATISTIK FÜR FEUERWEHREN
- **Ton:** ruhig, präzise, nahbar. Kurze Sätze, aktiv, konkret („Bericht hochladen, Namen prüfen, übernehmen“), keine Superlative. Fachbegriffe der Feuerwehr so, wie die Wehr sie benutzt.
- **Absender:** „Ein Projekt von Polifka IT Beratung“, klein unter dem Logo oder im Impressum, nie als Teil des Logos.

## Logo

Die **Bildmarke** zeigt eine Auswertung als drei Balken, wobei der höchste Balken eine Flamme ist: Statistik über Einsätze.
Das Gehäuse ist wie der Rechner im Polifka-Logo weich gerundet. Die Flamme ist das einzige Signalorange im Zeichen.

| Datei | Einsatz |
|---|---|
| `logo-horizontal.svg` / `-white.svg` | Standard: README, Website-Kopf, Folien, Signaturen |
| `logo-stacked.svg` / `-white.svg` | Hochformat, Plakat, Titelfolie, Aufsteller |
| `wordmark.svg` / `-white.svg` | Nur Schrift, wo die Bildmarke schon daneben steht |
| `mark.svg` | Bildmarke allein: Profilbild, App-Icon, kleine Flächen |
| `mark-white.svg` | Bildmarke einfarbig weiß auf Blau, Rot und Fotos (Kopfzeile der App) |
| `mark-mono.svg` | einfarbig mit ausgestanzten Balken (`currentColor`): Stempel, Gravur, Schwarzweißdruck |
| `social-preview.png` (1280 × 640), `og-image.png` | GitHub „Social preview“, Link-Vorschauen |

Schriften sind in allen SVG-Dateien zu Pfaden umgewandelt, es braucht keine Installation.

**Schutzzone:** rundum mindestens die Höhe der Balkengruppe, also ein Viertel der Bildmarken-Höhe.
**Mindestgrößen:** Logo horizontal 120 px / 30 mm breit, gestapelt 100 px / 25 mm, Bildmarke 16 px (unter 48 px die vereinfachte Fassung ohne Flammen-Innenform, siehe `favicon.svg`), Druck 8 mm.

**Nicht erlaubt:** verzerren, drehen, Farben tauschen, Verläufe, Schatten, Konturen, Bildmarke ohne Gehäuse benutzen (außer in den App-Kacheln), Flamme einzeln verwenden, Wortmarke neu setzen.

## Farben und Farbkonzept

Die Farben folgen den Schulungsunterlagen des Landesamts für Brand- und Katastrophenschutz (Bordeaux als Standardfarbe, Sand für Tabellen, Signalorange für Hinweise und Fehler), damit sich Material von Wehren, Landesamt und diesem Projekt zusammen gut liest. Es werden nur Farben übernommen, **keine Logos, Wappen oder Wortmarken** des Landes oder des Landesamts; die Marke erweckt keinen amtlichen Eindruck.

| Rolle | Name | Wert | Einsatz |
|---|---|---|---|
| Hauptfarbe | Bordeaux | `#7C2734` | Zeichen, Wortmarke, Überschriften, Hauptaktionen, Tabellenköpfe (abgedunkelt) |
| Dunkel | Tiefes Bordeaux | `#44151D` | dunkle Flächen: Social-Bild, Kopf-Verlauf, Titelfolie |
| Fläche | Sand | `#E9D6CE` | Tabellenzeilen, Kacheln, Hinweisflächen, Hintergründe |
| Signal | Signalorange | `#D46E3B` | Hinweise und Fehler (Linie, Symbol, getönte Fläche), die Flamme im Zeichen |
| Text | Tinte | `#2B1A1D` | Text, nie reines Schwarz |
| Status | Waldgrün | `#1E5A2C` auf `#E3F1E6` | „erledigt“ |
| Daten | Warmgrau | gedämpfte Grautöne (#6E6460, #4A403C, #8A817C) | Diagramme, unabhängig von der Markenfarbe |

Abgeleitet (App und Material): Bordeaux gedämpft `#8C414C` (Tabellenköpfe, weiße Schrift 7,1:1), Bordeaux hell `#A36871` (Fokusring), Sandpapier `#F5ECE8` (Seitenhintergrund), Signalorange dunkel `#8F3E14` (Schrift auf hellem Grund, 7,3:1).

**Kontraste:** weiße Schrift auf Bordeaux 9,6:1, Bordeaux auf Sand 6,8:1, Tinte auf Sand 11,8:1. Signalorange `#D46E3B` ist **keine Schriftfarbe** (3,4:1 auf Weiß): Text in Hinweisen und Fehlern steht in der dunklen Fassung (`#8F3E14` bzw. `#6E2A0C`). Die Flamme im Zeichen ist Gestaltung, die Balken tragen die Aussage.

### Konzepte nach Einsatz

1. **Oberfläche (App):** weiße Karten, Sandpapier als Grund, Bordeaux für Kopf, Überschriften und Hauptaktion, Sand für Tabellenzeilen und Chips, Diagramme grau. Hinweis und Fehler teilen den Farbton Signalorange und unterscheiden sich durch Tönung (Fehler kräftiger und dunkler), Wort und Symbol: Farbe allein trägt nie die Bedeutung.
2. **Schulung und Dokumente:** wie in den Unterlagen des Landesamts: großflächige Bordeaux-Kapitelseiten mit weißer Schrift, Fließtext schwarz-warm auf Weiß, Tabellen mit Sand-Hintergrund und Bordeaux-Kopfzeile, Hinweise in Signalorange mit Wort („Hinweis“, „Achtung“).
3. **Digital und Social:** Tiefes Bordeaux als Grund, weißes Logo, Sand für Kleingedrucktes, Signalorange nur einmal (Flamme).
4. **Wehr-individuell:** Eine Wehr wählt ihre Hauptfarbe (und optional eine dunkle); die App leitet die Töne ab und prüft den Kontrast. Hinweise und Fehler bleiben signalorange, damit sie in jeder Wehr gleich erkennbar sind.

Faustregel für eine Fläche: **70 % Weiß/Sand, 25 % Bordeaux, höchstens 5 % Signalorange.**

Druck (Richtwerte, vor dem Auftrag Andruck prüfen): Bordeaux ca. CMYK 30/90/70/40; Sand ca. 8/18/20/0; Signalorange ca. 0/68/82/0. Das Bordeaux in den gedruckten Unterlagen des Landesamts wirkt heller und roter als `#7C2734`; für Material, das neben diesen Unterlagen liegt, den Ton per Andruck angleichen.

## Marke und Oberfläche der Wehr

Die Oberfläche gehört der Wehr: Bordeaux (oder eigene Farbe), eigenes Logo, auf Wunsch eigene Schrift (siehe `DESIGN.md`).
Die Marke erscheint dort nur zurückhaltend:

- **Footer:** „openEinsatzstatistik – freie Software“ als Link zum Quellcode (Pflicht aus der AGPL, nicht entfernen).
- **Ohne Wehr-Logo:** die Bildmarke als Ersatz in Kopfzeile, Footer und Browser-Tab.
- **Anmeldung und VG-Gesamtansicht:** die Standardfarben (Bordeaux mit Sand), unabhängig von der gewählten Wehr.

Für Website, Folien, Handzettel, GitHub und Mailings gilt das Erscheinungsbild dieses Dokuments mit der Schrift unten.

## Schrift

Eine normale, gut lesbare Groteskschrift, wie sie das BKS-Portal des Landes ausliefert: der Systemschriften-Stapel (Bootstrap 5).
Die Wortmarke ist in **Roboto** gesetzt, einer Schrift dieses Stapels (SIL Open Font License, als Pfade in den Logos).

- **Wortmarke:** „open“ in Roboto Regular, „Einsatzstatistik“ in Roboto Bold, Unterzeile in Roboto Medium, Versalien, weit gesperrt.
- **Websites, Folien, Dokumente:** `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`. Es muss nichts geladen werden, der DSGVO-Aufwand für Webfonts entfällt.
- **Schnitte:** Regular für Text, Bold für Überschriften und Hervorhebungen, Overlines in Versalien mit weiter Laufweite. Fließtext 16 px mit 1,6 Zeilenabstand.
- **In der App** gelten dieselben Systemschriften; eine Wehr kann eine eigene Schriftdatei hinterlegen (siehe `DESIGN.md`).

## Bildwelt und Icons

- Fotos: echte Wehren bei der Arbeit, Tageslicht, keine Stockbilder mit Blaulicht-Effekten. Nur mit Einwilligung der Abgebildeten, keine Einsatzkräfte erkennbar ohne Zustimmung, keine Unfallopfer.
- Icons: Linien-Icons mit 2 px Strich und runden Enden, einfarbig in Bordeaux oder Tinte.
- Diagramme in der App sind grau, die Farbe der Wehr hebt hervor. Auf Marken-Material gilt: Bordeaux für Daten, Signalorange für die eine Hervorhebung.

## Rechtliches

- Name und Logo gehören nicht zur AGPL-Lizenz (siehe `NOTICE`). Forks tragen einen anderen Namen und ein anderes Logo.
- Logos und Wappen von Feuerwehren gehören den jeweiligen Wehren.
- Empfohlen: Wortmarke beim DPMA anmelden (Klassen 9 und 42), bevor die Marke bekannt wird.

## Dateien neu erzeugen

Alle Logos, Icons und Social-Bilder entstehen aus einem Skript (Geometrie der Bildmarke, Text zu Pfaden). Änderungen an der Marke
immer dort vornehmen, nie an den Ausgaben. Aus der Projektwurzel:

```bash
docker build -q -t brand-tools -f tools/Dockerfile.brand tools
docker run --rm -v "$PWD/tools:/t:ro" -v "$PWD/tools/fonts:/fonts:ro" -v "$PWD:/out" brand-tools python /t/build_brand.py
```

Das Skript schreibt nach `brand/` und `static/` (Favicon, Apple-Touch-Icon, App-Kacheln, Kopfzeilen-Symbole). Die Schriften liegen mit ihren Lizenztexten in `tools/fonts/`.
