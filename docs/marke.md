# Marke: openEinsatzstatistik

Dieses Dokument legt fest, wie das Projekt auftritt. Es folgt dem Erscheinungsbild von **Polifka IT Beratung**
(Stahlblau, Bernstein-Akzent, weich gerundete Formen), damit Projekt und Anbieter erkennbar zusammengehören. Alle Dateien liegen in [`brand/`](../brand/).

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
Das Gehäuse ist wie der Rechner im Polifka-Logo weich gerundet. Die Flamme ist das einzige Bernstein im Zeichen.

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

## Farben

Die Palette ist die von Polifka IT Beratung, bewusst schmal. Faustregel: **70 % Weiß/Neutral, 25 % Blau, höchstens 5 % Bernstein.**

| Name | Wert | Einsatz |
|---|---|---|
| Stahlblau | `#2F6D92` | Markenfarbe: Bildmarke, Wortmarke, Links, Buttons |
| Nachtblau | `#1B3F55` | dunkle Flächen: Social-Bild, Fußzeile, Titelfolie |
| Blau hell | `#E3EEF5` | getönte Hintergründe |
| Bernstein | `#E0A43A` | **nur** die Flamme und einzelne Markierungen, nie als Text auf Weiß |
| Tinte | `#14293A` | Text, nie reines Schwarz |
| Himmel | `#7AB3D6` | Blau auf dunklen Flächen |

Druck (Richtwerte, vor dem Auftrag Andruck prüfen): Stahlblau ca. CMYK 80/40/15/20, Pantone 7698 C; Bernstein ca. CMYK 10/38/90/0.

Weiße Schrift auf Stahlblau und Nachtblau erreicht mindestens 5,6:1 (WCAG AA); Bernstein dient nur als Zeichen, nicht als Textfarbe.

## Marke und Oberfläche der Wehr

Die Oberfläche gehört der Wehr: Wehr-Rot (oder eigene Farbe), eigenes Logo, auf Wunsch eigene Schrift (siehe `DESIGN.md`).
Die Marke erscheint dort nur zurückhaltend:

- **Footer:** „openEinsatzstatistik – freie Software“ als Link zum Quellcode (Pflicht aus der AGPL, nicht entfernen).
- **Ohne Wehr-Logo:** die Bildmarke als Ersatz in Kopfzeile, Footer und Browser-Tab.
- **Anmeldung und VG-Gesamtansicht:** neutrales Farbschema in Stahlblau (`theme.NEUTRAL`).

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
- Icons: Linien-Icons mit 2 px Strich und runden Enden, einfarbig in Stahlblau oder Tinte.
- Diagramme in der App sind grau, das Rot der Wehr hebt hervor. Auf Marken-Material gilt: Blau für Daten, Bernstein für die eine Hervorhebung.

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
