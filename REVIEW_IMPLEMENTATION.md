# Umsetzung des Reviews

Branch: `fix/comprehensive-review`, Ausgangspunkt: `de7b2cb`.
Die echte Instanz und echte Einsatzdaten werden bei der Umsetzung nicht verändert.

## Umgesetzt und geprüft

- Anmeldeprüfung verwendet den ASGI-Pfad statt der aus dem Host konstruierten URL; die Rechte-Dependency weist fehlende Sitzungen zusätzlich ab.
- FastAPI/Starlette, Multipart-, PDF- und Kryptografie-Abhängigkeiten aktualisiert. Der Audit der aktualisierten Anforderungen meldet keine bekannten Schwachstellen.
- Neue Einsatzberichte werden in der Oberfläche ausdrücklich übernommen. Direkte Speicherung von Stammdatensätzen und Weiterleitung anderer Wehren werden vor dem Upload erklärt; diese Importwege sind noch nicht vollständig gestuft.
- Importvergleich umfasst Beschreibung, Leitstellen-Nummer, Personen/Funktionen/Fahrzeugzuordnungen und Sekunden. Unbekannte Fahrzeugspalten fließen ebenfalls ein.
- Nutzereingaben in Excel-Zellen bleiben Text; beabsichtigte Formeln bleiben Formeln. Einsatzdauer über 24 Stunden erhält vollständige Datumswerte und ein Stundenformat ohne Tagesumbruch.
- Eine zukünftige Gebührenordnung wird nicht automatisch rückwirkend gewählt. Negative, nicht endliche und boolesche Gebührensätze sowie ungültige Kalenderdaten werden abgewiesen.
- Negative Stärken, gelöschter Einsatzbeginn und Ende vor Beginn werden abgefangen. Fahrzeugstärke hat eine serverseitige Untergrenze.
- Einsatzrevision schützt Speichervorgänge aus der Oberfläche. Alte API-Aufrufer ohne Revision bleiben kompatibel und müssen in einer weiteren API-Härtung auf eine verbindliche Vorbedingung umgestellt werden. Import-Aktualisierungen brauchen ebenfalls diesen Revisionsvertrag.
- Verbrauchte Magic Links werden atomar und dauerhaft in der Zentral-Datenbank markiert.
- Nacharbeit eines gespeicherten Imports wird in derselben Wehr-Transaktion dauerhaft eingereiht. Zentrale Änderungen haben eine idempotente Abschlussmarkierung. Fehlgeschlagene Aufträge bleiben für Wiederholung beim Neustart erhalten; ein Speichervorgang bleibt erfolgreich und meldet offene Nacharbeit.
- Zusätzliche Stärke statt vermeintlicher kumulativer Stärke wird in UI, Hilfe und Excel eindeutig beschriftet.
- Kennzahlen-Export berücksichtigt Wehr-Auswahl und Frist; fehlende Personalstunden erhalten Abdeckungshinweise.
- Formularlabels sind explizit zugeordnet; Einsatzdetails haben einen Tastatur-Button. Importdialog hat einen zugänglichen Titel.
- Historische Importhinweise werden als solche erklärt. Ladefehler erhalten die Seitenstruktur und eine Wiederholen-Aktion.
- Gleichzeitiges Einlesen ist gesperrt; das Ersetzen offener Vorschauen benötigt eine Rückfrage.
- Mobile Kopfzeile darf umbrechen. Die globale Auswahl heißt „Ansicht“ statt „Wehr“.
- Prüfprotokoll bündelt das Laden von Einsatz-/Pending-Daten pro Wehr; eine Lastmessung steht noch aus.
- Vorschauen haben Anzahl-, Benutzer- und Speicherbudgets; PDF-Seiten sowie Excel-Spalten/Blätter sind begrenzt.
- Neuere Datenbankschemata verhindern einen Downgrade. Migrationen aus jeder historischen Schema-Version sowie erneute Starts werden getestet.
- CI prüft Python 3.12/3.14, Abhängigkeiten und JavaScript-Syntax. Container verwendet einen unprivilegierten Benutzer, Healthcheck und Ressourcenlimits; Host-Port wird standardmäßig nur an Loopback gebunden.
- Gemeinsame Personalstunden-/Abdeckungslogik ist zentralisiert, Import-Nacharbeit in ein eigenes Modul getrennt.

## Noch offen – keine vollständige Freigabe

1. Alle Importtypen vollständig als Vorschau/Bestätigung gestalten, einschließlich Stammdatensätzen und Weiterleitungen; atomare Stapelentscheidung und serverseitiger Abbruchvertrag.
2. Revision für alle schreibenden API-Aufrufer verbindlich machen und Import-Aktualisierungen gegen inzwischen geänderte Einsätze absichern.
3. Zeitgesteuerte Wiederholung der Nacharbeit im laufenden Betrieb und Übersicht offener Aufträge; momentan Wiederholung beim Neustart. Hintergrundverarbeitung benötigt einen klaren Lebenszyklus.
4. Mandanten-Anlage/-Archivierung mit dauerhaften Lebenszykluszuständen und Wiederaufnahme nach Dateisystemfehlern absichern; reale Restore-Probe auf einer Kopie.
5. Vollständiger Dependency-Lock mit Hashes; Docker-Build unter Linux/Python 3.12 wirklich ausführen. Die CI wurde hinzugefügt, aber noch nicht auf GitHub ausgeführt.
6. Frontend in kleinere explizite Module schneiden; gemeinsames Feldschema und formatunabhängige BKS-Normalisierung. Kein unnötiger Framework-Wechsel.
7. Vollständige Browser-Regressionen für Upload/Abbruch, Fehler → Retry, Exportparität, alle Dialoge und Tastaturbedienung. Aktuelle Browserprüfung ist manuell mit synthetischen Daten.
8. Lastprofil des Prüfprotokolls; harte Request-/Parser-Laufzeitgrenzen und einheitliche Schutzregeln für administrative Excel-Importe. Die neuen Dateigrenzen ersetzen keine Prozess-Isolation.
9. Aktuelle Prüfhinweise dynamisch berechnen, zusätzlich zur bereits getrennten Importhistorie; leere Zustände und Verwaltungskontext weiter vereinheitlichen.

## Vor einem späteren Rollout

- Sicherung der Zentral-Datenbank und **aller** Wehr-Datenbanken sowie Assets/AVV-Dateien als konsistenten Bestand anlegen und Wiederherstellung prüfen. Bei aktiven Schreibern nicht lediglich einzelne SQLite-Dateien kopieren.
- Neue Migrationen erhöhen die Schema-Version. Ein Software-Downgrade ohne Rückspielen der passenden Sicherung wird absichtlich abgewiesen.
- `APP_UID`/`APP_GID` so setzen, dass der Container auf den bestehenden Datenordner schreiben darf. Keine automatische Änderung des Besitzers echter Daten durch diesen Branch.
- Standard-Portbindung ist jetzt `127.0.0.1`. Ein Proxy auf dem Host kann diese nutzen; Container-Proxys sollten das gemeinsame Docker-Netz nutzen. Eine absichtlich andere Bindung benötigt `APP_BIND`.
- Öffentlich konfigurierte `BASE_URL` erfordert `ADMIN_EMAILS`; fehlende Anmeldung lässt sich damit nicht unbemerkt für eine öffentliche Domain starten.
- Zuerst gegen eine Kopie testen, dann ausdrücklich freigegeben deployen. Es wurde weder ein Deployment noch ein Push ausgelöst.
