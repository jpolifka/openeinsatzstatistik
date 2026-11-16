---
name: openEinsatzstatistik
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
  field-line: "#858585"
  gridline: "#ECECEC"
  track: "#F3E4E5"
  series: "#4A4A4A"
  series-night: "#2E2E2E"
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
    fontFamily: "system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "3.1rem"
    fontWeight: 700
    lineHeight: 1.15
  headline:
    fontFamily: "system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1.7rem"
    fontWeight: 700
    lineHeight: 1.2
  title:
    fontFamily: "system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1.3rem"
    fontWeight: 700
    lineHeight: 1.2
  body:
    fontFamily: "system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.85rem"
    fontWeight: 700
    lineHeight: 1.35
  label-sm:
    fontFamily: "system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.78rem"
    fontWeight: 700
    lineHeight: 1.35
  body-sm:
    fontFamily: "system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.92rem"
    fontWeight: 400
    lineHeight: 1.5
  subtitle:
    fontFamily: "system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1rem"
    fontWeight: 700
    lineHeight: 1.3
  number:
    fontFamily: "system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.2
  prompt-title:
    fontFamily: "system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1.15rem"
    fontWeight: 700
    lineHeight: 1.2
  digits:
    fontFamily: "system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  kpi-value:
    fontFamily: "system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
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

# Design System: openEinsatzstatistik

## Overview

**Creative North Star: „Die Wachbuch-Auswertung“**

Die Oberfläche soll wirken wie ein sauber geführtes Einsatzbuch: sachlich, nachvollziehbar, ohne Effekte. Weiße Karten liegen auf einem blassen, rötlich getönten Grund; Zahlen stehen groß und ruhig, jede mit Fallzahl und Abdeckung daneben. Rot ist die Kennfarbe der Wehr und trägt Orientierung (Kopf, Hauptaktion, Überschriften, Erreichungsgrad), nicht Dekoration. Die Diagrammreihen sind neutral grau.

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
- **Signalrot der Wehr** (#D90000, `--brand`): Überschriften, Hauptaktion, aktive Reiter-Akzente, Erreichungsgrad.
- **Tiefes Wachrot** (#7A0000, `--brand-dark`): Anfang des Kopfverlaufs, Hero-Kennzahl, Summenfenster, Text auf hellen Rotflächen.
- **Verlaufsrot** (#A30000, `--brand-gradient`): Mitte des Kopfverlaufs.

### Secondary
- **Gedämpftes Rot** (#C9363F, `--brand-mid`): Tabellenköpfe, Panel-Überschriften, sekundäre Flächen.
- **Helles Akzentrot** (#E0525C, `--brand-accent`): Fokusring, Hover-Rahmen, gestrichelter Rahmen der Ablage. Weiß darauf hat nur 3,8:1; nicht als Textfarbe verwenden.

### Neutral
- **Rosa-Papier** (#FCEEEF, `--brand-pale`): Seitenhintergrund.
- **Rosenschimmer** (#F6DADC, `--brand-light`): Schlüsselwort-Chips, Hinweiszeilen, dezente Kacheln.
- **Kartenweiß** (#FFFFFF): Karten, Eingaben, Dialoge.
- **Tintengrau** (#333333, `--text`): Fließtext.
- **Beschriftungsgrau** (#6B6B6B, `--gray`): Sekundärtext; 4,8:1 auf hellem Grau.
- **Haarlinie** (#E4E4E4, `--line`): Trennlinien in Karten und Tabellen; Raster in #ECECEC. Nicht für Bedienelemente.
- **Feldlinie** (#858585, `--field-line`): Rahmen von Eingaben, Auswahlfeldern, Suchfeld, Farbwahl und Outline-Knöpfen; 3,7:1 auf Weiß, 3,3:1 auf Rosa-Papier.
- **Waldgrün** (#1E5A2C auf #E3F1E6): Status „erledigt“.
- **Bernstein** (#5E3A00 auf #FFF1CC, Linie #E2B24A): Status „zu prüfen“, neue Personen, Prüfhinweise.
- **Verspätet-Ocker** (#9A4A00, `--late-text`): zu spät eingetroffene Zeiten und Zu-erledigen-Marke; nicht vom Wehr-Rot abgeleitet, steht immer mit Symbol und verstecktem Text („nicht innerhalb von 10 Minuten“).
- **Fehlerrot** (#8C1111 auf #FDEBEA, Linie #D98A8A): Fehlermeldungen und „nicht gespeichert“; immer mit Symbol und Überschrift, auch in Wehren mit rotem Theme.

### Named Rules
**The Wehr-Token Rule.** Jede Farbe der Marke kommt aus einem `--brand-*`-Token. Feste Hex-Werte in Regeln sind nur für neutrale Grautöne zulässig und gehören auch dann auf Tokens.

**The One Voice Rule.** Eine Kennfarbe pro Wehr. Weitere Farben entstehen nur durch Abstufung (heller, dunkler), nie durch einen zweiten Farbton. Ausnahme sind die Statusfarben unten: Sie gehören keiner Wehr und bleiben in jedem Theme gleich.

**The Control-Edge Rule.** Alles, was man anklicken oder ausfüllen kann, hat einen Rand mit mindestens 3:1 (`--field-line`). `--line` trennt nur Inhalt.

**The Status Rule.** Rot der Wehr bedeutet Marke, nie Fehler. Zustände tragen eigene, von der Wehr unabhängige Töne: neutral = bereit, Bernstein (`--warn-*`) = zu prüfen, Grün (`--ok-*`) = erledigt, Fehlerrot (`--error-*`) = nicht gespeichert. Jeder Status nennt sich außerdem mit einem Wort (und meist einem Symbol); Farbe allein trägt nie die Bedeutung.

## Typography

**Schrift:** Systemschriften (`system-ui`, Segoe UI, Roboto, Helvetica, Arial), wie das BKS-Portal des Landes; es wird keine Schrift ausgeliefert. Jede Wehr kann in den Einstellungen eine eigene Schriftdatei (normal, optional fett) hinterlegen; `/api/theme.css` setzt dafür `--font`.

**Charakter:** Eine neutrale, vertraute Sans. Kraft kommt aus dem Gewicht 700 für Überschriften, Beschriftungen und Zahlen; der Fließtext bleibt ruhig.

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
- **Zustände:** Fokus zeigt einen 3-px-Ring in `--brand-accent` (auf dem farbigen Kopf in Weiß); deaktiviert mit 50 % Deckkraft; Druck verschiebt um 1 px.
- **Touch:** Auf Geräten mit grobem Zeiger (`pointer: coarse`) sind Knöpfe, Segmente, Schließen und Hilfe im Kopf mindestens 44 px hoch bzw. breit.

### Segmente
- Hellgraue Leiste mit 10 px Radius, aktiver Eintrag weiß mit roter Schrift und feinem Schatten.

### Kennzahlenkacheln
- Weiß, 14 px Radius, Titel in Grau (0,85 rem), Wert 1,9 rem in 700. Die Hero-Kachel ist tiefrot mit weißer Schrift und 3,1 rem.

### Schlüsselwort-Chips
- Rosenschimmer-Grund, tiefrote Schrift, 6 px Radius, Mindestbreite 58 px, zentriert.

### Eingaben
- Weiß, 1 px Rand in `--field-line`, 8 px Radius. Fokus: 2-px-Ring in `--brand` mit 1 px Abstand und Rand in `--brand`; kein heller Hof. Jedes Feld hat einen sichtbaren oder `aria-label`-Namen, ein Platzhalter ersetzt ihn nicht. Auf Touchgeräten mindestens 44 px hoch.

### Zahlen
- Ziffern in Daten (Tabellen, Kennzahlen, Chips, Eingaben) kommen aus `--font-num`, standardmäßig dieselbe Schrift wie der Text. Bei einer eigenen Wehrschrift mit verwechselbarer Eins und Null lässt sich `--font-num` getrennt setzen.

### Zeitstrahl
- Im Einsatzdetail zeigt ein Zeitstrahl je Fahrzeug Ausrücken (`--brand-accent`) und Anfahrt (`--brand`) auf einer Minutenachse ab Alarm; die Zeitgrenze ist eine gestrichelte Linie in `--late-text`. Verspätung steht zusätzlich als Wort und △. Ein Umschalter „Zeitstrahl / Tabelle“ hält die genauen Werte erreichbar; die Wahl bleibt erhalten.

### Hilfe
- Es gibt eine gesammelte Hilfe (das `?` im Kopf, passend zur Ansicht), keine `?`-Symbole an einzelnen Feldern oder Kennzahlen. Erklärungen stehen in `help.js`.

### Import-Vorschau
- Bei mehreren Berichten ist nur der erste aufgeklappt, die übrigen zeigen ihr Statusband mit „Öffnen“; nach der Übernahme öffnet sich der nächste. Fehlende Angaben im Formular sind Bernstein mit dem Wort „fehlt“ (nie Rosa: Rot der Wehr ist Marke).
- Sichtbar sind nur Prüfhinweise, die Anwesenden (neue Personen) und ein Einzeiler zum Einsatz; alle Felder, Zeiten und Fahrzeuge liegen hinter „Alle Felder“ (`<details>`, merkt sich je Bericht den Zustand). Die Übernahme ist eine feste Fußleiste am Dialogrand. Im Bearbeiten-Formular des Einsatzes liegen seltene Angaben in „Weitere Angaben“.

### Navigation
- Reiter im Kopf: weiße Schrift (`--on-brand-text`, 82 % → 100 % bei Hover/aktiv), 3-px-Unterstrich weiß für den aktiven Reiter, Streifen als dunkle Überlagerung (14 %); Unterreiter etwas kleiner und heller abgesetzt. Alles im Kopf nutzt die Tokens `--on-brand-text`, `--on-brand-fill`, `--on-brand-line`; der Fokusring ist dort weiß (8,2:1 auf dem Verlauf).

### Dialog
- 18 px Radius, Kopf weiß mit Linie darunter, Inhalt scrollt. Breiten 1080 / 920 / 760 px.
- **Rückfrage** (`askConfirm`): schmaler Dialog (460 px) statt `window.confirm`/`alert`. Die Knöpfe nennen die Folge („Vorschauen verwerfen“), bei zerstörerischen Aktionen ist der Fokus auf „Abbrechen“ und der Bestätigen-Knopf fehlerrot. Fehler nach einer Aktion nennen, was nicht geschehen ist, die Ursache und den nächsten Schritt (`reportError`).

### Diagramme (Signatur)
- Balkenlisten mit Beschriftung links, Wert rechts, dünner Bezugslinie; Säulen bis 24 px Breite. Reihen sind neutral und gehören nicht zum Wehr-Theme: `--series` (Graphit #4A4A4A), Tag `--day` (#8F8F8F), Nacht `--night` (#2E2E2E), Vorjahr `--previous` (#8F8F8F), alle mindestens 3:1 auf Weiß. Rot der Wehr gehört dem, worauf es ankommt (Erreichungsgrad, Fokus, Zeitstrahl). Beschriftungen immer in `--gray`.

## Do's and Don'ts

### Do:
- **Do** alle Markenfarben über `--brand-*`-Tokens ansprechen, damit Wehr-Themes greifen.
- **Do** Kennzahlen immer mit Fallzahl und Abdeckung („n von N“) zeigen und Fehlendes als „nicht angegeben“ darstellen.
- **Do** Texte in `--gray` nicht kleiner als 0,8 rem setzen und mindestens 4,5:1 Kontrast halten.
- **Do** Fokus sichtbar halten: 3-px-Ring in `--brand-accent`, Abstand 2 px; im farbigen Kopf weiß, in Eingabefeldern 2 px `--brand`.
- **Do** Rahmen von Bedienelementen in `--field-line` setzen und Datentabellenköpfe mit `scope` versehen (macht `markTableHeaders` in `app.js` automatisch).
- **Do** neue Felder und Kennzahlen in `help.js` erklären und Änderungen in `changelog.js` eintragen.

### Don't:
- **Don't** Schriften von fremden Servern laden: Eine Wehrschrift kommt nur als hochgeladene Datei über `/api/branding/…` (CSP `font-src 'self'`).
- **Don't** den Seitentitel umbrechen lassen: Der Kopf hat in jeder Ansicht dieselbe Höhe (Titel einzeilig, Beschriftungen von Wehr und Jahr entfallen bis 1560 px).
- **Don't** leere Diagramme mit Strichen zeigen; Leerzustände sagen, was fehlt und was zu tun ist.
- **Don't** `--brand-accent` auf dem Kopfverlauf als Fokusfarbe verwenden (unter 2:1).
- **Don't** `--brand-accent` oder `--day` als Textfarbe auf Weiß einsetzen (3,8:1).
- **Don't** Grautöne unter #6B6B6B für lesbaren Text verwenden; helle Grautöne (#B5B5B5, #BDBDBD) sind nur für Linien und Flächen.
- **Don't** Schatten in Schatten schachteln oder Karten in Karten ohne Linie darstellen.
- **Don't** echte Namen in Beispielen oder Screenshots zeigen.
- **Don't** `window.confirm`/`alert` verwenden; Rückfragen und Fehler laufen über `askConfirm`/`reportError`, Fehler am Ort des Geschehens über `noticeBox`.
- **Don't** Rot der Wehr für Fehler oder „neu“ einsetzen; dafür gibt es die Statusfarben.
- **Don't** Bedeutung allein über Farbe tragen; Status braucht Text oder Symbol.
