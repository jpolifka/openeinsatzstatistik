# Nutzertest: Leitfaden

Ziel: herausfinden, ob Schriftführer, Wehrleiter und VG-Verwaltung die App **ohne Hilfe** für ihre echten Aufgaben
nutzen können, und wo sie stolpern. Getestet wird die App, nicht die Person.

## Vorbereitung

- **Demo starten:** `docker compose -f docker-compose.demo.yml up --build` → http://localhost:8113.
  Erfundene Daten (VG Musterland, Wehren Musterstadt und Nebenhausen, 2025–2026), Anmeldung aus.
  Neustart des Containers setzt alles zurück, also vor jeder Sitzung neu starten.
- **Importtests** brauchen echte BKS-Berichte. Die gehören nicht in die Demo und nicht in dieses Repository:
  Testperson bringt eigene (anonymisierte oder ihre eigenen) Berichte mit, auf ihrem eigenen Rechner,
  und es wird nichts aufgezeichnet, was Namen zeigt.
- Bildschirm und Ton aufzeichnen nur mit schriftlicher Einwilligung (Vorlage unten); bei Importaufgaben aus.
- Eine Person fragt, eine zweite schreibt mit. Dauer je Sitzung 45 Minuten.

## Ablauf einer Sitzung (45 Min.)

1. **Begrüßung (5 Min.):** „Wir testen die Software, nicht dich. Es gibt keine falschen Antworten. Bitte sprich laut aus,
   was du denkst und suchst. Ich helfe nicht, bis du ‚fertig‘ oder ‚ich komme nicht weiter‘ sagst.“
2. **Einstiegsfragen (5 Min.):** Rolle in der Wehr, wie wird heute ausgewertet (Excel? Papier?), wie lange dauert der
   Jahresbericht, was nervt am meisten.
3. **Aufgaben (25 Min.):** Szenarien der eigenen Rolle (unten). Aufgabe vorlesen, nicht erklären, wo es klickbar ist.
4. **Nachgespräch (10 Min.):** Fragen unten, plus SUS-Fragebogen.

## Aufgaben je Rolle

Erfolg = ohne Hilfe gelöst. Teilerfolg = mit einem Hinweis. Misserfolg = aufgegeben oder falsches Ergebnis.

### Schriftführer (Wehr)

| # | Aufgabe | Erfolgskriterium |
|---|---|---|
| S1 | Du hast heute drei neue Einsatzberichte (PDF). Übernimm sie in die Statistik. | alle drei gespeichert, Namen geprüft |
| S2 | In einem Bericht ist ein Name falsch zugeordnet. Korrigiere ihn vor dem Speichern. | richtiger Name im Einsatz |
| S3 | Ein Bericht wurde im Portal geändert. Lies ihn erneut ein und aktualisiere den Einsatz. | Einsatz aktualisiert, nicht doppelt |
| S4 | Finde den Einsatz „Wohnungsbrand“ vom Frühjahr und ergänze von Hand eine Person. | Person erscheint, Speichern erfolgreich |
| S5 | Exportiere alle Einsätze 2026 als Excel. | Datei heruntergeladen |

### Wehrleiter (Wehr)

| # | Aufgabe | Erfolgskriterium |
|---|---|---|
| W1 | Wie viele Einsätze hatten wir 2026, und wie viele davon waren Brände? | richtige Zahlen genannt |
| W2 | Wie oft haben wir die 10-Minuten-Grenze beim Eintreffen eingehalten? | Quote gefunden, Fallzahl verstanden |
| W3 | Welche Fahrzeuge werden am häufigsten alarmiert, welche kaum? | Ansicht „Fahrzeuge & Atemschutz“ gefunden |
| W4 | Welche Person hatte 2026 die meisten Einsatzteilnahmen? (Hinweis: darf der Wehrleiter das sehen?) | Reaktion auf Rechtegrenze notiert |
| W5 | Du brauchst für die Gemeinderatssitzung drei Kennzahlen. Wähle sie aus. | Auswahl begründet, keine Fehldeutung |

### VG-Verwaltung

| # | Aufgabe | Erfolgskriterium |
|---|---|---|
| V1 | Vergleiche die Wehren der VG: Welche hatte 2026 die meisten Einsätze? | Gesamtansicht gefunden |
| V2 | Ein Einsatz wurde von beiden Wehren erfasst. Prüfe, ob die Angaben übereinstimmen. | Abgleich gefunden, Abweichung benannt |
| V3 | Berechne den Kostenersatz für einen Stammdatensatz. | Ergebnis nachvollzogen |
| V4 | Lege eine neue Wehr an und gib einer Person Zugriff. | Wehr + Zuordnung vorhanden |

### Admin / Einrichtung

| # | Aufgabe | Erfolgskriterium |
|---|---|---|
| A1 | Trage die Fahrzeuge deiner Wehr ein und stelle die Zeitgrenze ein. | Fahrzeuge + Grenzen gespeichert |
| A2 | Wechsle die Farbe auf eure Wehrfarbe und lade ein Logo hoch. | Farbe/Logo sichtbar |

## Beobachtungsbogen (je Aufgabe)

| Feld | Eintrag |
|---|---|
| Aufgabe / Testperson (Kürzel) | |
| Ergebnis | Erfolg / Teilerfolg / Misserfolg |
| Zeit (mm:ss) | |
| Wo gezögert, falsch geklickt, gesucht? | |
| Zitate (wörtlich) | |
| Hilfe nötig? Welche? | |
| Schweregrad | 0 kein Problem, 1 kosmetisch, 2 behindert, 3 verhindert die Aufgabe |

## Nachgespräch

- Was war am leichtesten, was am schwersten?
- Hast du den Zahlen vertraut? Woran hättest du es gemerkt, wenn sie falsch wären?
- Würdest du die Excel-Übersicht dafür abschalten? Was fehlt dafür?
- Was würdest du nie hochladen, und warum? (Datenschutzgefühl)
- Wem würdest du das empfehlen, wem nicht?

### SUS (System Usability Scale), je 1 = stimme gar nicht zu … 5 = stimme voll zu

1. Ich würde das System gern häufig nutzen.
2. Ich fand das System unnötig komplex.
3. Ich fand das System einfach zu benutzen.
4. Ich würde technische Hilfe brauchen, um es zu nutzen.
5. Die Funktionen waren gut aufeinander abgestimmt.
6. Es gab zu viele Unstimmigkeiten.
7. Die meisten Leute würden es schnell lernen.
8. Ich fand es sehr umständlich zu benutzen.
9. Ich fühlte mich sicher bei der Benutzung.
10. Ich musste vieles lernen, bevor es losging.

Auswertung: ungerade Fragen = Wert − 1, gerade Fragen = 5 − Wert, Summe × 2,5. Ab etwa 68 gilt als durchschnittlich,
ab 80 als gut.

## Stichprobe und Zeitplan

| Phase | Wer | Wann |
|---|---|---|
| 1 Aufgabentests | 5–6 Personen der Heimatwehr (2 Schriftführer, 2 Führungskräfte, 1–2 VG) | Wochen 1–3 |
| 2 Pilot | 2–3 weitere Wehren mit eigenen Berichten, mindestens eine ohne persönlichen Draht | Wochen 4–9 |
| 3 Laufend | alle Nutzer: Feedback-Reiter, SUS nach 4 Wochen | ab Woche 10 |

Nach jeder Runde: Probleme nach Schweregrad sortieren, Schweregrad 3 und 2 zuerst beheben, mit neuen Personen
wiederholen. Fünf Personen je Rolle zeigen den Großteil der Bedienprobleme.

## Erfolgskennzahlen

| Kennzahl | Ziel |
|---|---|
| Aufgaben ohne Hilfe gelöst | ≥ 80 % |
| Zeit bis zum ersten Import | ≤ 15 Min. |
| Berichte ohne manuelle Korrektur importiert | ≥ 90 % |
| SUS | ≥ 75 |
| Pilotwehren, die nach 8 Wochen noch monatlich importieren | ≥ 2 von 3 |
| „Excel abschalten“ mit Ja beantwortet | ≥ 2 von 3 |

## Parser-Test mit fremden Wehren

Der größte technische Risikofaktor sind Berichte, die anders aussehen als die der Heimatwehr. Bitte Pilotwehren,
Fehlermeldungen zu notieren (Dateiname, Meldung, nicht den Inhalt). Zum Nachstellen genügt ein **anonymisierter**
Bericht (Namen ersetzt, Adressen geschwärzt), der als Testfall in `tests/` landet.

## Einwilligung (Vorlage)

> Ich nehme freiwillig an einem Test der Software „openEinsatzstatistik“ teil. Notizen und, falls vereinbart, Bildschirm- und
> Tonaufnahmen dienen nur der Verbesserung der Software, werden nicht weitergegeben und nach der Auswertung, spätestens
> nach drei Monaten, gelöscht. In Berichten vorkommende Namen werden nicht aufgezeichnet. Ich kann jederzeit abbrechen.
>
> Name / Kürzel: ____________  Datum: ____________  Aufnahme erlaubt: ☐ ja ☐ nein
