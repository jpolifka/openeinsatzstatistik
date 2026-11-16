# openEinsatzstatistik – Einsatzstatistik für Feuerwehren

**Aus dem BKS-Einsatzbericht wird die Auswertung. Frei, quelloffen, ohne Excel-Handarbeit.**

## Das Problem

Nach jedem Einsatz liegt der Bericht im BKS-Portal. Für Jahresbericht, Gemeinderat und Bedarfsplan werden Zeiten,
Kräfte und Teilnahmen bisher von Hand in Excel übertragen. Das kostet Stunden und ist fehleranfällig.

## Die Lösung

Berichte (PDF oder Excel-Export aus dem BKS-Portal) hochladen, in der Vorschau prüfen, übernehmen. Die Auswertungen
entstehen daraus von selbst.

| Für | Nutzen |
|---|---|
| **Schriftführer** | Bericht einlesen, Namen und Felder prüfen, speichern. Minuten statt Abende. |
| **Wehrleiter** | Zeiten, Eintreffen und verfügbare Kräfte, Belastung, Fahrzeug- und Atemschutznutzung auf einen Blick |
| **Verbandsgemeinde** | Wehren im Vergleich, Abgleich gemeinsamer Einsätze, Kostenersatz nach Gebührensatzung |

## Was die App kann

- **Einlesen:** PDF und Excel-Export, einzeln oder als ZIP, mit Prüfhinweisen und Namensabgleich.
- **Auswerten:** Einsatzarten, Zeiten (Median, 90. Perzentil), Kräfteaufbau nach 5/10/15 Minuten, Eintreffen und verfügbare Kräfte,
  Belastung, Abbrüche und Brandmeldeanlagen, Fahrzeuge und Atemschutz, Brandverlauf.
- **Personal:** Einsatzteilnahmen, Stunden, Nacht- und Wochenendeinsätze je Person.
- **Nachvollziehbar:** Jede Kennzahl nennt Fallzahl und Abdeckung („42 von 57 Einsätzen auswertbar“). Fehlende Angaben zählen nie als null.
- **Excel-Export** im Format der bisherigen Einsatzübersicht.
- **Mehrere Wehren:** je Wehr eigene Daten, Farben, Logo und Fahrzeuge; die Verbandsgemeinde sieht nur personenfreie Daten.

## Datenschutz und Sicherheit

- Personendaten bleiben je Wehr in einer eigenen Datenbank; der Wehrleiter sieht auf Wunsch keine Namen.
- Rollen und Rechte feingranular und nachvollziehbar protokolliert.
- Anmeldung ohne Passwort per Einmal-Link, Sitzungen serverseitig und beendbar.
- Vertrag zur Auftragsverarbeitung (AVV) für jede Verbandsgemeinde eingebaut.
- Läuft auf eigenem Server in Deutschland, kein Dritt-Dienst.

## Kosten und Betrieb

Die Software ist kostenlos (Apache License 2.0). Betrieb mit Docker auf einem kleinen Server oder bei der VG-IT.
Auf Wunsch Unterstützung bei Einführung und Schulung.

## Jetzt ausprobieren

1. **Demo** mit erfundenen Daten: `docker compose -f docker-compose.demo.yml up --build` → http://localhost:8113
2. **Pilot:** Wir richten gemeinsam eure Wehr ein und lesen eure ersten Berichte ein.

Kontakt: Polifka IT-Beratung, In der Maar 31, 56598 Rheinbrohl · Quellcode: https://github.com/jpolifka/openeinsatzstatistik

*Hinweis: Ersetzt keinen Feuerwehrbedarfsplan.*
