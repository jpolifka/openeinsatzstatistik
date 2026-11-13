---
name: pdf2einsatz
description: Einsatzstatistik für Feuerwehren – sachliche Auswertung in Wehr-Rot auf weißen Karten
colors:
  brand: "#D90000"
  brand-dark: "#7A0000"
  brand-gradient: "#A30000"
  brand-mid: "#C9363F"
  brand-accent: "#E0525C"
  brand-hover: "#B80000"
  brand-light: "#F6DADC"
  brand-pale: "#FCEEEF"
  text: "#333333"
  gray: "#6B6B6B"
  light-gray: "#F2F2F2"
  white: "#FFFFFF"
  line: "#E4E4E4"
  gridline: "#ECECEC"
  track: "#F3E4E5"
  series-night: "#A80000"
  series-previous: "#8F8F8F"
  ok-bg: "#E3F1E6"
  ok-text: "#1E5A2C"
  warn-bg: "#FFF1CC"
  warn-text: "#5E3A00"
  warn-line: "#E2B24A"
  error-bg: "#FDEBEA"
  error-text: "#8C1111"
  error-line: "#D98A8A"
  late-text: "#9A4A00"
typography:
  display:
    fontFamily: "Sansation, Segoe UI, system-ui, sans-serif"
    fontSize: "3.1rem"
    fontWeight: 700
    lineHeight: 1.15
  headline:
    fontFamily: "Sansation, Segoe UI, system-ui, sans-serif"
    fontSize: "1.7rem"
    fontWeight: 700
    lineHeight: 1.2
  title:
    fontFamily: "Sansation, Segoe UI, system-ui, sans-serif"
    fontSize: "1.3rem"
    fontWeight: 700
    lineHeight: 1.2
  body:
    fontFamily: "Sansation, Segoe UI, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Sansation, Segoe UI, system-ui, sans-serif"
    fontSize: "0.85rem"
    fontWeight: 700
    lineHeight: 1.35
  label-sm:
    fontFamily: "Sansation, Segoe UI, system-ui, sans-serif"
    fontSize: "0.78rem"
    fontWeight: 700
    lineHeight: 1.35
  body-sm:
    fontFamily: "Sansation, Segoe UI, system-ui, sans-serif"
    fontSize: "0.92rem"
    fontWeight: 400
    lineHeight: 1.5
  subtitle:
    fontFamily: "Sansation, Segoe UI, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 700
    lineHeight: 1.3
  number:
    fontFamily: "Sansation, Segoe UI, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.2
  prompt-title:
    fontFamily: "Sansation, Segoe UI, system-ui, sans-serif"
    fontSize: "1.15rem"
    fontWeight: 700
    lineHeight: 1.2
  kpi-value:
    fontFamily: "Sansation, Segoe UI, system-ui, sans-serif"
    fontSize: "1.9rem"
    fontWeight: 700
    lineHeight: 1.1
rounded:
  xs: "4px"
  chip: "6px"
  sm: "8px"
  md: "10px"
  lg: "14px"
  xl: "18px"
  pill: "999px"
spacing:
  sm: "8px"
  md: "14px"
  lg: "18px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.brand}"
    textColor: "{colors.white}"
    rounded: "{rounded.md}"
    padding: "10px 18px"
  button-primary-hover:
    backgroundColor: "{colors.brand-hover}"
  button-light:
    backgroundColor: "{colors.brand-light}"
    textColor: "{colors.brand-dark}"
    rounded: "{rounded.md}"
    padding: "10px 18px"
  button-outline:
    backgroundColor: "{colors.white}"
    textColor: "{colors.gray}"
    rounded: "{rounded.md}"
    padding: "10px 18px"
  card:
    backgroundColor: "{colors.white}"
    textColor: "{colors.text}"
    rounded: "{rounded.lg}"
    padding: "22px"
  kpi:
    backgroundColor: "{colors.white}"
    textColor: "{colors.text}"
    rounded: "{rounded.lg}"
    padding: "16px 18px"
  kpi-hero:
    backgroundColor: "{colors.brand-dark}"
    textColor: "{colors.white}"
    rounded: "{rounded.lg}"
    padding: "16px 18px"
  input:
    backgroundColor: "{colors.white}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "8px 10px"
  keyword-chip:
    backgroundColor: "{colors.brand-light}"
    textColor: "{colors.brand-dark}"
    rounded: "6px"
    padding: "3px 9px"
---

# Design System: pdf2einsatz

## Overview

**Creative North Star: „Die Wachbuch-Auswertung“**

Die Oberfläche soll wirken wie ein sauber geführtes Einsatzbuch: sachlich, nachvollziehbar, ohne Effekte. Weiße Karten liegen auf einem blassen, rötlich getönten Grund; Zahlen stehen groß und ruhig, jede mit Fallzahl und Abdeckung daneben. Rot ist die Kennfarbe der Wehr und trägt Orientierung (Kopf, Hauptaktion, Überschriften, Diagrammreihen), nicht Dekoration.

Gearbeitet wird überwiegend am Desktop, in Maske und Tabelle: Berichte prüfen, Listen filtern, Kennzahlen lesen. Die Dichte ist mittel. Karten haben reichlich Innenabstand, Tabellen sind kompakt und mit tabellarischen Ziffern gesetzt.

Die Farben gehören der jeweiligen Wehr: Alle Rottöne sind Tokens, die `/api/theme.css` je Wehr überschreibt. Nichts in den Regeln darf einen festen Rotton enthalten.

**Key Characteristics:**
- Weiße Karten auf blassem Markengrund, weich angehoben
- Eine Kennfarbe, abgeleitet in zehn Tönen; keine zweite Akzentfarbe
- Kräftige, kurze Beschriftungen (Gewicht 700), ruhiger Fließtext
- Jede Kennzahl nennt Fallzahl und Abdeckung; Fehlendes ist nie „0“
- Sachlicher Ton, deutsche Fachbegriffe der Feuerwehr

## Colors

Eine Kennfarbe in Abstufungen, dazu neutrale Grautöne und ein Statusgrün, das unabhängig von der Wehr bleibt.

### Primary
- **Signalrot der Wehr** (#D90000, `--brand`): Überschriften, Hauptaktion, aktive Reiter-Akzente, Diagrammreihe.
- **Tiefes Wachrot** (#7A0000, `--brand-dark`): Anfang des Kopfverlaufs, Hero-Kennzahl, Summenfenster, Text auf hellen Rotflächen.
- **Verlaufsrot** (#A30000, `--brand-gradient`): Mitte des Kopfverlaufs.

### Secondary
- **Gedämpftes Rot** (#C9363F, `--brand-mid`): Tabellenköpfe, Panel-Überschriften, sekundäre Flächen.
- **Helles Akzentrot** (#E0525C, `--brand-accent`): Fokusring, Hover-Rahmen, gestrichelter Rahmen der Ablage, Tagesreihe. Weiß darauf hat nur 3,8:1; nicht als Textfarbe verwenden.

### Neutral
- **Rosa-Papier** (#FCEEEF, `--brand-pale`): Seitenhintergrund.
- **Rosenschimmer** (#F6DADC, `--brand-light`): Schlüsselwort-Chips, Hinweiszeilen, dezente Kacheln.
- **Kartenweiß** (#FFFFFF): Karten, Eingaben, Dialoge.
- **Tintengrau** (#333333, `--text`): Fließtext.
- **Beschriftungsgrau** (#6B6B6B, `--gray`): Sekundärtext; 4,8:1 auf hellem Grau.
- **Haarlinie** (#E4E4E4, `--line`): Rahmen und Trennlinien; Raster in #ECECEC.
- **Waldgrün** (#1E5A2C auf #E3F1E6): Status „erledigt“.
- **Bernstein** (#5E3A00 auf #FFF1CC, Linie #E2B24A): Status „zu prüfen“, neue Personen, Prüfhinweise.
- **Verspätet-Ocker** (#9A4A00, `--late-text`): zu spät eingetroffene Zeiten und Zu-erledigen-Marke; nicht vom Wehr-Rot abgeleitet, steht immer mit Symbol und verstecktem Text („nicht innerhalb von 10 Minuten“).
- **Fehlerrot** (#8C1111 auf #FDEBEA, Linie #D98A8A): Fehlermeldungen und „nicht gespeichert“; immer mit Symbol und Überschrift, auch in Wehren mit rotem Theme.

### Named Rules
**The Wehr-Token Rule.** Jede Farbe der Marke kommt aus einem `--brand-*`-Token. Feste Hex-Werte in Regeln sind nur für neutrale Grautöne zulässig und gehören auch dann auf Tokens.

**The One Voice Rule.** Eine Kennfarbe pro Wehr. Weitere Farben entstehen nur durch Abstufung (heller, dunkler), nie durch einen zweiten Farbton. Ausnahme sind die Statusfarben unten: Sie gehören keiner Wehr und bleiben in jedem Theme gleich.

**The Status Rule.** Rot der Wehr bedeutet Marke, nie Fehler. Zustände tragen eigene, von der Wehr unabhängige Töne: neutral = bereit, Bernstein (`--warn-*`) = zu prüfen, Grün (`--ok-*`) = erledigt, Fehlerrot (`--error-*`) = nicht gespeichert. Jeder Status nennt sich außerdem mit einem Wort (und meist einem Symbol); Farbe allein trägt nie die Bedeutung.

## Typography

**Schrift:** Sansation (Gewichte 300, 400, 700; lokal ausgeliefert, mit Segoe UI und System-Sans als Rückfall)

**Charakter:** Eine freundliche, leicht geometrische Sans mit kantigem Ton. Kraft kommt aus dem Gewicht 700 für Überschriften, Beschriftungen und Zahlen; der Fließtext bleibt ruhig.

### Hierarchy
- **Display** (700, 3,1 rem, 1,15): Hero-Kennzahl.
- **Headline** (700, 1,7 rem, 1,2): Seitentitel im Kopf.
- **Title** (700, 1,3 rem / 1,05 rem, 1,2): Karten- und Abschnittsüberschriften, in Markenrot.
- **Body** (400, 15 px, 1,5): Fließtext, Tabellen.
- **Label** (700, 0,85 rem) und **Label klein** (700, 0,78 rem): Kennzahlentitel, Feldnamen, Spaltenköpfe, Panel-Überschriften (Versalien, Sperrung 0,08 em). Nichts ist kleiner als 0,78 rem.
- **Body klein** (400, 0,92 rem) und **Untertitel** (700, 1 rem): Tabellen, Kartenuntertitel. Weitere Stufen: 1,3 / 1,5 / 1,7 / 1,9 / 3,1 rem für Überschriften und Kennzahlen.

### Named Rules
**The Fall-Zahl Rule.** Jede Kennzahl bekommt Fallzahl und Abdeckung („n von N“) in derselben Karte, in `--gray` und mindestens 0,8 rem.

**The Tabellenziffer Rule.** Tabellen setzen Zahlen mit `font-variant-numeric: tabular-nums`.

## Layout

Eine Spalte bis maximal 1280 px, zentriert, mit 24 px Seitenrand. Kopf mit Verlauf, darunter ein Reiter-Streifen und optional Unterreiter; darunter Karten in einem Raster mit 18 px Abstand (`.grid-2`, `.grid-3`) und Kennzahlenzeilen mit 14 px Abstand (`.kpis`: 1,35fr + fünf Spalten oder vier gleiche).

Breakpoints bei 1150, 1000, 900 und 760 px lösen Spalten auf. Breite Tabellen scrollen in einem eigenen Container (`.table-wrap`), nie die Seite. Druckansichten blenden Kopf und Bedienelemente aus.

Rhythmus: 8 / 14 / 18 / 24 px. Karten haben 22 px Innenabstand, Kennzahlenkacheln 16–18 px.

## Elevation & Depth

Hybrid aus Tönung und Schatten. Der Seitengrund ist ein blasses Rosa, Karten sind weiß und liegen mit einem weichen, rötlich getönten Schatten darauf. Dialoge setzen sich mit einem deutlich größeren Schatten und einer dunkel-roten Abdunklung des Hintergrunds ab.

### Shadow Vocabulary
- **Karte** (`0 1px 2px rgba(51,0,0,.06), 0 6px 20px rgba(122,0,0,.06)`): Karten und Kennzahlenkacheln.
- **Primärbutton** (`0 4px 14px var(--brand-shadow)`): Hauptaktion, Markenfarbe mit 25 % Deckkraft.
- **Dialog** (`0 30px 80px rgba(60,0,0,.35)`) mit Abdunklung `rgba(40,0,0,.45)`.
- **Hinweis** (`0 6px 18px rgba(0,0,0,.2)`): Tooltip und Toast.

### Named Rules
**The Quiet Shadow Rule.** Schatten tragen Ebene, nie Schmuck. Innerhalb einer Karte gibt es keine weiteren Schatten, nur Linien (`--line`).

## Shapes

Abgerundete, freundliche Formen mit gestaffelten Radien: 6 px (Chips), 8 px (Eingaben), 10 px (Buttons, Auswahlfelder), 14 px (Karten), 18 px (Dialoge), voller Kreis für Hilfe- und Schließen-Knöpfe, Pille für Personenmarken. Diagrammbalken haben nur rechts oben und unten einen Radius von 4 px. Hervorhebungen sind Flächen, keine Rahmen.

## Components

### Buttons
- **Form:** 10 px Radius, 10×18 px Innenabstand, Gewicht 700, Icon 20 px davor.
- **Primär:** Marken-Rot mit weißer Schrift und farbigem Schatten; Hover dunkler (`--brand-hover`).
- **Hell:** Rosenschimmer mit dunkelrotem Text, für Zweitaktionen.
- **Weiß / Outline:** weißer Grund, graue Schrift, Linie; Hover färbt den Rahmen.
- **Zustände:** Fokus zeigt einen 3-px-Ring in `--brand-accent`; deaktiviert mit 50 % Deckkraft; Druck verschiebt um 1 px.

### Segmente
- Hellgraue Leiste mit 10 px Radius, aktiver Eintrag weiß mit roter Schrift und feinem Schatten.

### Kennzahlenkacheln
- Weiß, 14 px Radius, Titel in Grau (0,85 rem), Wert 1,9 rem in 700. Die Hero-Kachel ist tiefrot mit weißer Schrift und 3,1 rem.

### Schlüsselwort-Chips
- Rosenschimmer-Grund, tiefrote Schrift, 6 px Radius, Mindestbreite 58 px, zentriert.

### Eingaben
- Weiß, 1 px Linie, 8 px Radius. Fokus: Rahmen in `--brand-accent` und 3-px-Hof in `--brand-light` (statt Systemring).

### Navigation
- Reiter im Kopf: weiße Schrift (82 % → 100 % bei Hover/aktiv), 3-px-Unterstrich weiß für den aktiven Reiter, Streifen als dunkle Überlagerung (14 %); Unterreiter etwas kleiner und heller abgesetzt.

### Dialog
- 18 px Radius, Kopf weiß mit Linie darunter, Inhalt scrollt. Breiten 1080 / 920 / 760 px.
- **Rückfrage** (`askConfirm`): schmaler Dialog (460 px) statt `window.confirm`/`alert`. Die Knöpfe nennen die Folge („Vorschauen verwerfen“), bei zerstörerischen Aktionen ist der Fokus auf „Abbrechen“ und der Bestätigen-Knopf fehlerrot. Fehler nach einer Aktion nennen, was nicht geschehen ist, die Ursache und den nächsten Schritt (`reportError`).

### Diagramme (Signatur)
- Balkenlisten mit Beschriftung links, Wert rechts, dünner Bezugslinie; Säulen bis 24 px Breite. Reihen: `--series` (#D90000), Tag `--day`, Nacht `--night`, Vorjahr `--previous` (grau). Beschriftungen immer in `--gray`.

## Do's and Don'ts

### Do:
- **Do** alle Markenfarben über `--brand-*`-Tokens ansprechen, damit Wehr-Themes greifen.
- **Do** Kennzahlen immer mit Fallzahl und Abdeckung („n von N“) zeigen und Fehlendes als „nicht angegeben“ darstellen.
- **Do** Texte in `--gray` nicht kleiner als 0,8 rem setzen und mindestens 4,5:1 Kontrast halten.
- **Do** Fokus sichtbar halten: 3-px-Ring in `--brand-accent`, Abstand 2 px.
- **Do** neue Felder und Kennzahlen in `help.js` erklären und Änderungen in `changelog.js` eintragen.

### Don't:
- **Don't** `--brand-accent` oder `--day` als Textfarbe auf Weiß einsetzen (3,8:1).
- **Don't** Grautöne unter #6B6B6B für lesbaren Text verwenden; helle Grautöne (#B5B5B5, #BDBDBD) sind nur für Linien und Flächen.
- **Don't** Schatten in Schatten schachteln oder Karten in Karten ohne Linie darstellen.
- **Don't** echte Namen in Beispielen oder Screenshots zeigen.
- **Don't** `window.confirm`/`alert` verwenden; Rückfragen und Fehler laufen über `askConfirm`/`reportError`, Fehler am Ort des Geschehens über `noticeBox`.
- **Don't** Rot der Wehr für Fehler oder „neu“ einsetzen; dafür gibt es die Statusfarben.
- **Don't** Bedeutung allein über Farbe tragen; Status braucht Text oder Symbol.
