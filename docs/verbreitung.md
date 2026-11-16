# Verbreitung als Open-Source-Projekt

Das Projekt steht kostenlos unter der AGPL-3.0. Verbreitung heißt also nicht „verkaufen“, sondern
**Vertrauen aufbauen, Einstieg leicht machen und Nutzer zu Mitwirkenden machen**.

## Positionierung

> Aus dem BKS-Einsatzbericht wird die Einsatzstatistik, ohne Excel-Handarbeit. Frei, quelloffen, von Feuerwehrleuten
> für Feuerwehren. Personendaten bleiben bei der Wehr.

Was uns von allgemeiner Statistiksoftware unterscheidet: versteht das BKS-Format Rheinland-Pfalz, rechnet die bekannte
Excel-Einsatzübersicht nach, trennt Rechte nach Wehr und Verbandsgemeinde, jede Kennzahl nennt Fallzahl und Abdeckung.

## Zielgruppen (Reihenfolge)

1. **Verbandsgemeinden und Wehrleitungen in RLP:** ein Betreiber, mehrere Wehren; Kostenersatz, Abgleich, VG-Gesamtansicht.
2. **Einzelne Wehren mit Excel-Bastlern:** kennen das Problem, entscheiden schnell.
3. **Später:** Wehren in anderen Bundesländern (braucht jeweils einen eigenen Berichtsleser, nur auf Nachfrage und mit
   Beispielberichten aus der Region).

## Was „Betrieb“ für andere bedeutet

Frei heißt nicht, dass jede Wehr einen Server haben will. Es gibt drei Wege; kläre vorab, welche du anbietest:

| Weg | Wer betreibt | Aufwand für dich |
|---|---|---|
| Selbst betreiben (Docker) | Wehr/VG-IT | Dokumentation, Issues |
| Gemeinsamer Betrieb durch eine VG oder einen Kreis | VG-IT, Rechenzentrum | Beratung |
| Gehostet durch dich | du | Haftung, Support, AVV, Kosten → nur bewusst und ggf. gegen Aufwandsentschädigung |

Empfehlung: zuerst die ersten beiden anbieten und das Hosting nur für die Pilotwehren übernehmen. Eine Pauschale für
Betrieb und Support ist mit einer freien Lizenz vereinbar. Verkauft wird dann der Service, nicht die Software.

## Maßnahmen

### 1. Repository öffentlich machen (Vorbereitung)

Checkliste, bevor das Repository öffentlich wird:

- [ ] Git-Historie auf Personendaten prüfen (Namen, echte Mailadressen, Berichte). Die Dateimuster sind ausgeschlossen,
      aber die Commit-Autoren-Mails (privat, `@icloud.com`) sind dann öffentlich; ggf. mit `.mailmap` oder Umschreiben.
- [x] Logos und Fahrzeugdaten einer realen Wehr sind aus dem Code entfernt. **Auch aus der Git-Historie**: vor dem
      Öffentlichmachen die Historie bereinigen oder mit neuer Historie veröffentlichen (siehe unten).
- [ ] Impressum/Kontakt im README, `SECURITY.md` und Meldeweg testen (Private Vulnerability Reporting aktivieren).
- [ ] Beschreibung, Themen (`feuerwehr`, `einsatzstatistik`, `bks`, `fastapi`) und Social-Preview-Bild setzen.
- [ ] Release `v1.0.0` mit Changelog und Docker-Image (GitHub Container Registry), damit der Einstieg
      `docker compose up` genügt und niemand bauen muss.
- [ ] Demo-Zugang online (nur erfundene Daten, `docker-compose.demo.yml`), Adresse im README.

### 2. Erster Eindruck

- README oben: ein Satz, drei Screenshots (Übersicht, Zeiten & Kräfte, Import-Vorschau), Link zur Demo, **Schnellstart in
  fünf Zeilen**.
- Kurzes Video (2–3 Min.): „Vom PDF zur Auswertung“.
- Einseitige [Produktbeschreibung](produktbeschreibung.md) als PDF zum Weitergeben an Wehrleiter und Verwaltung.

### 3. Wege zu den Nutzern

| Kanal | Aktion |
|---|---|
| Wehrleiter-Dienstversammlungen, Kreisfeuerwehrverband, Verbandsversammlung | 15-Min.-Vortrag mit Live-Demo; Anfrage über den Kreisfeuerwehrverband |
| Landesfeuerwehrverband RLP, Kreisbrandinspektoren | als Multiplikator gewinnen, Pilotempfehlung erfragen |
| Fachpresse (z. B. „Brandschutz“, Feuerwehr-Magazine, Landesfeuerwehrzeitung) | Kurzmeldung „freie Software statt Excel“ |
| Feuerwehr-Foren und Gruppen (Facebook, Telegram, Feuerwehr-Forum) | Beitrag mit Demo-Link, kein Dauerwerben |
| BKS-Portal-Betreiber, Leitstelle, Landesamt | Gespräch: stabile Berichtsformate, Hinweise auf mögliche Schnittstelle |
| Bürgermeister/VG-Bürgermeister | Argument Haushalt: kostenlose Software, Kosten nur für eigenen Betrieb |
| IT-Dienstleister der Kommunen | Betriebsanleitung, AVV-Vorlage, Docker-Hinweise |

### 4. Gemeinschaft aufbauen

- GitHub Discussions (Fragen, Ideen), Issues-Vorlagen (Fehler, Berichtsformat, Wunsch).
- „Good first issue“ für Dinge, die auch Nicht-Programmierer können: Texte der Hilfe, Stichwortkataloge anderer Wehren,
  anonymisierte Beispielberichte, Übersetzung von Fachbegriffen.
- Halbjährlich Nutzertreffen (online, 1 Std.): Neuigkeiten, Wünsche, Erfahrungen.
- Beitragende nennen: Danksagungen im Changelog.

### 5. Nachhaltigkeit

- **Wartung:** Wer pflegt, wenn du keine Zeit hast? Zweiten Maintainer aus einer Pilotwehr gewinnen.
- **BKS-Format ändert sich:** Anonymisierte Testberichte sammeln, Parser-Tests laufen in CI.
- **Finanzierung ohne Verkauf:** Spenden/GitHub Sponsors, Förderung durch Feuerwehrverbände oder Land,
  bezahlte Einführung/Schulung/Betrieb für VGs. Open-Source-Förderprogramme (z. B. Prototype Fund, Sovereign Tech
  Fund) prüfen; kommunale Open-Source-Initiativen (z. B. openCode.de) als Plattform.
- **Haftung:** In der Lizenz steht „ohne Gewährleistung“. Wer hostet, braucht trotzdem eine Vereinbarung (AVV), die App
  bringt dafür die Vorlage mit (`templates/avv_v*.html`).


## Zeitplan

| Zeitraum | Ziel |
|---|---|
| Monate 1–2 | Nutzertests Phase 1, Fehler beheben, Repository vorbereiten (Checkliste) |
| Monate 3–4 | Pilotwehren, Fallstudie mit Zahlen („Auswertung in 10 statt 360 Minuten“) |
| Monat 5 | Repository öffentlich, Release 1.0, Demo online, erster Vortrag |
| Monate 6–9 | weitere VGs, Pressebeitrag, Nutzertreffen, zweiter Maintainer |
| danach | Wachstum über Empfehlungen; andere Bundesländer nur auf Nachfrage |

## Erfolgskennzahlen

- Anzahl Wehren mit monatlichem Import (Ziel 10 nach 12 Monaten)
- Anzahl VGs
- Externe Issues/Beiträge pro Quartal
- Empfehlungsquote (Frage im Nachgespräch)
- Zeit bis zur ersten Auswertung bei einer neuen Wehr
