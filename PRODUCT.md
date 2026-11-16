# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
- Schriftführer bzw. wer Einsatzberichte erfasst: liest BKS-Berichte nach dem Einsatz ein, prüft die Vorschau, korrigiert Namen und Felder.
- Wehrleiter und Führung: lesen Auswertungen (Zeiten, Kräfte, Belastung, „Eintreffen und verfügbare Kräfte“) für Gremien und Berichte.
- VG-Verwaltung: wehrübergreifende Sicht, Prüfprotokoll, Kostenersatz, Verwaltung von Wehren, Rollen und AVV.
- Genutzt wird überwiegend am Desktop; Tablet und Handy kommen gelegentlich vor.

## Product Purpose
Einsatzstatistik für Feuerwehren, mandantenfähig (erste Wehr: FF Rheinbrohl). Einsatzberichte (PDF oder Excel-Export aus dem BKS-Portal RLP) werden eingelesen, in SQLite gespeichert und die Auswertungen der früheren Excel-„Einsatzübersicht“ nachgerechnet. Erfolg heißt: ein Bericht ist in wenigen Minuten geprüft und übernommen, Kennzahlen sind nachvollziehbar und stimmen mit der bisherigen Excel-Auswertung überein.

## Positioning
Rechnet die gewohnte Excel-Auswertung der Wehr nach, versteht das BKS-Format Rheinland-Pfalz und trennt Rechte nach Wehr und Verbandsgemeinde. Eine allgemeine Statistiksoftware kann das nicht ohne Anpassung.

## Operating Context
Berichte kommen aus dem BKS-Portal RLP. Personenbezogene Daten (Namen, Anwesenheiten) bleiben je Wehr; die Verbandsgemeinde sieht nur personenfreie Daten. Anmeldung per Magic Link, Betrieb per Docker.

## Capabilities and Constraints
- Vanilla JS und CSS ohne Build-Schritt (`static/`), FastAPI-Backend.
- Alle Texte der Oberfläche sind deutsch; Code ist englisch.
- Farben und Logos sind je Wehr einstellbar (Tokens in `app.css`, `/api/theme.css`). Standard ist ein neutrales Feuerwehrrot.
- Jede Kennzahl nennt Fallzahl und Abdeckung („n von N“); fehlende Werte erscheinen nie als null.
- Online-Hilfe in `help.js` ist die einzige Quelle; neue Felder und Kennzahlen bekommen dort einen Eintrag; sichtbare Änderungen kommen in `changelog.js`.

## Brand Commitments
Rot der Wehr als Standardfarbe; je Wehr abweichende Farben und Logos möglich.

## Evidence on Hand
Keine echten Berichte im Repository (Datenschutz). Beispiele nur mit erfundenen Namen („M. Muster“, „Beispiel, Erika“).

## Product Principles
1. Prüfen vor Übernehmen: Der Import zeigt Abweichungen und Hinweise, bevor etwas gespeichert wird.
2. Kennzahlen sind nachvollziehbar: Fallzahl, Abdeckung und Erklärung stehen dabei.
3. Personenbezug nur dort, wo das Recht besteht; die VG sieht keine Namen.
4. Ruhige, sachliche Oberfläche für Verwaltungsarbeit; Marke zeigt sich im Detail.

## Accessibility & Inclusion
WCAG 2.1 AA ist verbindlich. Keine echten Namen in Beispielen, Tests oder Dokumentation.
