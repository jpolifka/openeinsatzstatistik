# Umsetzung des Reviews

Branch: `fix/comprehensive-review`, Ausgangspunkt: `de7b2cb`.
Die echte Instanz und echte Einsatzdaten wurden nicht verändert. Kein Push und kein Deployment.

## Umgesetzt

- Anmeldung über den ASGI-Pfad; fehlende Sitzungen werden zusätzlich in der Rechteprüfung abgewiesen. Magic Links werden dauerhaft und atomar als verbraucht markiert.
- Aktualisierte direkte und transitive Laufzeit-Abhängigkeiten mit `requirements.lock` und SHA256-Prüfsummen. Das Containerimage installiert mit verpflichtender Hash-Prüfung.
- **Alle Importtypen werden zuerst nur gelesen.** Neue Einsätze, Stammdatensätze und Weiterleitungen haben eigene ausdrückliche Bestätigungsaktionen. Ein Stapel besteht aus unabhängigen Einzelentscheidungen; es wird keine gemeinsame Transaktion über mehrere Wehr-Datenbanken versprochen.
- Benutzergebundene Vorschauen mit Ablauf, Speicher-/Anzahlbudgets und explizitem serverseitigem Abbruch. Beim Schließen werden offene Vorschauen verworfen, bestätigte Berichte bleiben bestehen. Verspätete Upload-Ergebnisse werden nicht in eine inzwischen geschlossene/neue Vorschau übernommen.
- Aktualisieren und Löschen von Einsätzen benötigen eine Revision: fehlende Vorbedingung 428, zwischenzeitliche Änderung 409. Umnummerierung erhöht betroffene Revisionen. Import-Aktualisierung ist an die ursprünglich verglichene Einsatz-ID gebunden.
- Importvergleich umfasst Beschreibung, Leitstellen-Nummer, Personen/Funktionen/Fahrzeugzuordnungen, Sekunden und unbekannte Fahrzeugspalten.
- Dauerhafte Import-Nacharbeit in derselben Wehr-Transaktion, idempotente zentrale Abschlussmarkierung, Wiederholung jede Minute und beim Start. Offene Aufträge werden angezeigt; ein gespeicherter Einsatz muss bei einem zentralen Ausfall nicht erneut importiert werden.
- Wiederaufnehmbare Archivierung: Wehr zunächst sperren, Archivauftrag dauerhaft speichern, erst nach erfolgreichem Verschieben zentrale Zuordnungen entfernen. Dateisystemausfälle und Absturz nach Verschieben werden getestet. Abgebrochene Anlagen werden beim Start in `deleted/incomplete-…` gesichert, nicht gelöscht.
- Excel-Eingaben bleiben Text statt ungewollter Formeln. Lange Einsatz- und Anwesenheitsdauern erhalten Stundenformate ohne Tagesumbruch. Kennzahlen-Export berücksichtigt Auswahl und Frist.
- Gebührenordnungen gelten erst ab ihrem Gültigkeitsbeginn. Negative/nicht endliche/boolsche Gebühren, ungültige Kalenderdaten, negative/fractionale/boolsche Stärken und Ende vor Beginn werden abgefangen. Zeitangaben verwenden die örtliche Uhrzeit ohne Zeitzonen-Zusatz.
- Gemeinsame Personalstunden-/Abdeckungslogik; fehlende Anwesenheit wird nicht als belastbare Null dargestellt.
- Aktuelle Datenprüfungen werden von historischen Importhinweisen getrennt. Zusatzstärken sind in Oberfläche, Hilfe und Export eindeutig beschriftet.
- Explizite Formularlabels, Tastatur-Button für Einsatzdetails, zugänglicher Importtitel, korrekt als Auswahlgruppe ausgezeichnete Verwaltungsbereiche. Vorhandene Feld-IDs bleiben erhalten.
- Ladefehler erhalten die Seitenstruktur und eine Wiederholen-Aktion. Import, Abbruch, Fehlerrückkehr und Revisionen sind zusätzlich durch Frontend-Zustandstests abgesichert.
- Responsive Kopfzeile für Smartphone **und** Tablet; „Ansicht“ statt missverständlicher Wehr-Auswahl in der VG-Gesamtansicht.
- Modularität: `imports.js`, `admin_views.js`, `preview_sessions.py`, `import_queue.py`, `tenant_lifecycle.py`, `parser_worker.py`, `request_limits.py`, `incident_schema.py` und `bks_common.py`. Formular, API und Speicherung teilen einen Feldkatalog; PDF und Excel teilen formatunabhängige BKS-Regeln. Kein Framework-Wechsel.
- Prüfprotokoll lädt Einsatz-/Pending-Daten einmal je Wehr statt je Stammdatensatz. Synthetischer Test mit 500 Stammdatensätzen und 1.000 Beteiligungen: zwei Datenladungen, lokal ca. 0,02 Sekunden (keine Produktions-Leistungsgarantie).
- Request-Limit bereits vor/während Multipart-Verarbeitung, einschließlich Requests ohne Content-Length. PDF/XLSX-Auswertung in kurzlebigen Prozessen: höchstens zwei gleichzeitig, 45 Sekunden, begrenzte Rückgabemenge und unter Linux CPU-/Speicherlimits. Administrative Excel-Kataloge verwenden dieselben Schutzgrenzen und schließen Arbeitsmappen zuverlässig.
- Migrationen bleiben append-only; neuere Schemata verhindern Downgrades. Historische Schema-Versionen und Wiederholungsstarts werden getestet.
- Container mit unprivilegiertem Benutzer, Healthcheck, Ressourcenlimits und standardmäßiger Loopback-Portbindung. CI prüft Python 3.12/3.14, Hash-Lock, Sicherheitsaudit, JavaScript-Syntax und Frontend-Zustandstests.

## Prüfung

- Lokal Python 3.14: **309 Tests bestanden**; 7 zusätzliche JavaScript-Tests bestanden.
- Linux/Python 3.12 mit Hash-Lock: **309 Tests bestanden**.
- Dependency-Audit des Hash-Locks: keine bekannten Schwachstellen.
- Produktionsimage gebaut; Start, Migration und Healthcheck unter UID 10001 mit leerem, containerinternem Datenordner erfolgreich geprüft.
- Browserprüfung ausschließlich auf der lokalen synthetischen Instanz: Excel-Upload → Vorschau → ausdrückliche Übernahme, Einsatzdetails per Enter, Bearbeitungsformular, Verwaltungsbereiche und Feldzuordnungen. Kein Seitenüberlauf bei 390, 768 und 1440 Pixeln; keine Browserfehler in diesen Abläufen.
- Synthetische Archiv-/Restore-Probe mit Einsatzdaten und SQLite-Integritätsprüfung bestanden.
- Eine Deprecation-Warnung betrifft den TestClient mit httpx; sie verhindert keine Tests und ist kein bekannter Laufzeit-Sicherheitsbefund.

## Grenzen der Freigabe

- Die GitHub-CI wurde nicht ausgelöst, weil kein Push beauftragt wurde.
- Browser-Abläufe wurden manuell geprüft; die automatisierten Frontend-Tests sind Zustands-/Render-Regressionen, keine lückenlose Browser-Ende-zu-Ende- oder formale WCAG-Zertifizierung.
- Keine Restore-Probe mit einer echten Produktionskopie und kein Test des vorhandenen Reverse-Proxys/SMTP. Dafür sind eine ausdrücklich freigegebene Kopie und eine Rollout-Freigabe nötig.
- Vorschauen liegen weiterhin im Speicher eines einzelnen Web-Workers. Ein Neustart verwirft offene Vorschauen, nicht gespeicherte Einsätze oder Nacharbeitsaufträge. Horizontale Skalierung benötigt einen gemeinsamen Vorschau-Speicher.

## Vor einem späteren Rollout

- Sicherung der Zentral-Datenbank und **aller** Wehr-Datenbanken sowie Assets/AVV-Dateien als konsistenten Bestand anlegen und Wiederherstellung prüfen. Bei aktiven Schreibern nicht lediglich einzelne SQLite-Dateien kopieren.
- Neue Migrationen erhöhen die Schema-Version. Ein Software-Downgrade ohne Rückspielen der passenden Sicherung wird absichtlich abgewiesen.
- `APP_UID`/`APP_GID` so setzen, dass der Container auf den bestehenden Datenordner schreiben darf. Keine automatische Änderung des Besitzers echter Daten durch diesen Branch.
- Standard-Portbindung ist jetzt `127.0.0.1`. Ein Proxy auf dem Host kann diese nutzen; Container-Proxys sollten das gemeinsame Docker-Netz nutzen. Eine absichtlich andere Bindung benötigt `APP_BIND`.
- Öffentlich konfigurierte `BASE_URL` erfordert `ADMIN_EMAILS`; fehlende Anmeldung lässt sich damit nicht unbemerkt für eine öffentliche Domain starten.
- Zuerst gegen eine Kopie testen, dann ausdrücklich freigegeben deployen. Es wurde weder ein Deployment noch ein Push ausgelöst.
