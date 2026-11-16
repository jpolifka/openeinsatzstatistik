"use strict";

// Neuigkeiten für die Benutzer (Reiter „Neuigkeiten“ im Hilfefenster). Neueste Version oben.
// Texte für Anwender: was sich in der Bedienung ändert, keine Technik. HTML erlaubt.
// Ein neuer Eintrag mit neuem Datum markiert das ?-Symbol im Kopf, bis die Neuigkeiten gelesen sind. Kommt am selben Tag
// noch ein Eintrag hinzu, bekommt er `version` ("JJJJ-MM-TT.2", dann .3 …); ohne `version` gilt das Datum.
const CHANGELOG = [
  {
    date: "2026-11-16",
    version: "2026-11-16.9a",
    items: [
      "<b>Farben:</b> Schrift und Diagramme sind jetzt warmes Grau statt kaltem Anthrazit und passen besser zu Bordeaux und Sand.",
    ],
  },
  {
    date: "2026-11-16",
    version: "2026-11-16.8",
    items: [
      "<b>Auswahl:</b> Die Auswahl oben ist jetzt nach Verbandsgemeinde gruppiert; darunter stehen die Gesamtansicht und die Wehren.",
    ],
  },
  {
    date: "2026-11-16",
    version: "2026-11-16.7",
    items: [
      "<b>Import:</b> Berichte aus allen Landkreisen und kreisfreien Städten in Rheinland-Pfalz werden erkannt, nicht nur aus dem Kreis Neuwied. Die Kennung der VG beginnt mit dem Kreis, z. B. „MYK.ABC“.",
    ],
  },
  {
    date: "2026-11-16",
    version: "2026-11-16.6",
    items: [
      "<b>Verwaltung:</b> Die Auswahl oben ist nach Verbandsgemeinde gegliedert, die Benutzerliste lässt sich auf eine VG oder Wehr eingrenzen. Heißen Wehren in zwei VGs gleich, bildet die Verwaltung den Kurznamen selbst (mit VG-Zusatz).",
      "<b>Verwaltung (Superadmin):</b> „Wehren &amp; VGs“ zeigt links alle Verbandsgemeinden mit Suche, rechts Stammdaten, Wehren und Zugriffe der gewählten VG. Wehren verschieben und archivieren fragt jetzt nach; Änderungen stehen im Protokoll.",
    ],
  },
  {
    date: "2026-11-16",
    version: "2026-11-16.4",
    items: [
      "<b>Einsätze:</b> In der Gesamtansicht der Verbandsgemeinde lässt sich die Einsatzliste jetzt wie die Auswertungen auf einzelne Wehren eingrenzen.",
    ],
  },
  {
    date: "2026-11-16",
    version: "2026-11-16.3",
    items: [
      "<b>Aufgeräumter Kopf:</b> Der aktive Reiter ist jetzt deutlich hervorgehoben, Beschriftungen und Untertitel im Kopf entfallen, der Titel wird nicht mehr abgeschnitten.",
      "<b>Einfachere Einstellungen:</b> Die Wehr wählst du nur noch im Kopf und im Auswahlfeld der Einstellungen; die zusätzlichen Knöpfe zum Wechseln entfallen.",
    ],
  },
  {
    date: "2026-11-16",
    version: "2026-11-16.2",
    items: [
      "<b>Rollen wie im BKS-Portal:</b> Neue Funktionen als Rollen: Stellv. Wehrführer/in, Stellv. Wehrleiter/in, Brand- und Katastrophenschutzinspekteur/in (und Stellvertretung), Sachbearbeiter/in Brand- u. KatS bzw. Feuerwehr, FEZ der VG sowie Leitstellenleitung und -personal. „Erfasser“ heißt jetzt „Bearbeiter/in Einsatzberichte“. Die Rechte bestehender Zuordnungen ändern sich nicht. Die Funktionsrollen der VG gibt es in drei Stufen: Sachbearbeitung (Einsätze und Personen bearbeiten), Leitung (zusätzlich Freigabe, Einstellungen, Benutzer) und Wehrleiter/in (zusätzlich Gebühren, AVV, Rollenpflege).",
      "<b>Aufgabenträger:</b> Eine VG ist jetzt Verbandsgemeinde, kreisfreie Stadt, Landkreis oder Leitstelle (Einstellungen → Verbandsgemeinden). Die Art bestimmt, welche Rollen dort vergeben werden können.",
      "<b>Personen in Rollen der VG:</b> Anwesenheit und Personal lassen sich jetzt auch einer Rolle der VG geben. Die neuen Funktionsrollen und Wehrleiter/in (samt Stellvertretung) haben dieses Recht; „Statistik VG“ weiterhin nicht.",
    ],
  },
  {
    date: "2026-11-16",
    items: [
      "<b>openEinsatzstatistik:</b> Die Anwendung heißt jetzt so und ist freie Software (AGPL-Lizenz). Unten auf jeder Seite steht ein Link zum Quellcode.",
      "<b>Neue Standardfarben:</b> Ohne eigene Wehrfarbe erscheint die Oberfläche jetzt in Bordeaux mit Sand für Tabellen, wie in den Schulungsunterlagen des Landes. Hinweise und Fehler sind signalorange. Wehren mit eigener Farbe sehen nur die neuen Hinweisfarben.",
      "<b>Eigene Schrift:</b> Die Oberfläche nutzt jetzt die Systemschriften (wie das BKS-Portal). Unter Einstellungen → Farben und Logos kann jede Wehr eine eigene Schriftdatei hochladen.",
      "<b>Neues Zeichen:</b> Ohne eigenes Wehr-Logo zeigt die Anwendung jetzt das Zeichen von openEinsatzstatistik (drei Balken mit Flamme) in Kopfzeile, Fußzeile und Browser-Tab. Die Anmeldeseite und die Gesamtansicht der Verbandsgemeinde sind in Stahlblau gehalten.",
    ],
  },
  {
    date: "2026-11-14",
    version: "2026-11-14.6",
    items: [
      "<b>Einsatzliste:</b> Die Liste zeigt zuerst 25 Einsätze; „Weitere anzeigen“ lädt die nächsten. Beim Drucken erscheinen alle.",
      "<b>Auswertungen:</b> Wo Angaben ganz fehlen, steht ein Satz mit Weg zu den betroffenen Einsätzen statt leerer Kacheln. Die Diagramme sind jetzt grau; das Rot der Wehr bleibt für Erreichungsgrad und Hervorhebungen.",
      "<b>Kopf und Handy:</b> Der Seitentitel bleibt bis 1560 px Breite einzeilig. Auf Touchgeräten sind Auswahlfelder, Sortierknöpfe und Links 44 px hoch.",
      "<b>Fehler beim Laden:</b> Die Meldung nennt, was nicht geladen werden konnte, und wie es weitergeht. Eine fehlerhafte Fahrzeugzeit bringt nicht mehr die ganze Auswertung zum Absturz.",
    ],
  },
  {
    date: "2026-11-14",
    version: "2026-11-14.5",
    items: [
      "<b>Personal:</b> Die Tabelle lässt sich jetzt auch mit der Tastatur sortieren und aufklappen (Pfeil rechts zeigt, dass sich eine Zeile öffnet). Die Balken sind schlanker, die Zahl steht vor dem Balken. Auf dem Handy zeigt jede Zeile Beteiligung und Stunden unter dem Namen.",
      "<b>Auswertungen:</b> In „Wo entsteht die Zeit?“ sind Median und „90 % höchstens“ getrennte, farblich unterscheidbare Balken mit Legende. Sind alle Angaben vollständig, steht dort ein Satz statt sechs gleich langer Balken. Zahlen im Fließtext sind eindeutig lesbar (111 statt „III“).",
    ]
  },
  {
    date: "2026-11-14",
    version: "2026-11-14.4",
    items: [
      "<b>Einlesen: erst das Wichtige.</b> Die Vorschau zeigt Prüfhinweise, die Anwesenden mit neuen Personen und eine Zeile zum Einsatz (Stichwort, Ort, Zeit, Einheitsführung, Fahrzeuge, Eintreffen). Alle Felder, Zeiten und Fahrzeuge stehen dahinter unter „Alle Felder“ und lassen sich dort wie bisher ändern.",
      "<b>Fahrzeuge als Zeitstrahl:</b> Im Einsatzdetail zeigt ein Zeitstrahl je Fahrzeug Ausrücken und Anfahrt bis zum Eintreffen, mit der Zeitgrenze als gestrichelter Linie. Ein Umschalter „Zeitstrahl / Tabelle“ bringt die genaue Tabelle zurück; die Wahl bleibt erhalten.",
      "<b>Eine gesammelte Hilfe:</b> Die vielen ?-Symbole an Feldern und Kennzahlen entfallen. Das ? im Kopf öffnet die Hilfe passend zur gerade offenen Ansicht und enthält alle Erklärungen."
    ]
  },
  {
    date: "2026-11-14",
    version: "2026-11-14.3",
    items: [
      "<b>Mehrere Berichte einlesen:</b> Zuerst ist nur der erste Bericht aufgeklappt, die übrigen zeigen ihr Statusband und öffnen sich per Klick. Nach „In Statistik übernehmen“ springt die Ansicht zum nächsten offenen Bericht; „Nächster offener Bericht“ und „2 von 3 übernommen“ stehen in der Statuszeile.",
      "<b>Sammelübernahme mit neuen Personen:</b> Berichte ohne Prüfhinweise lassen sich auch dann gemeinsam übernehmen, wenn neue Personen darin vorkommen. Vorher nennt ein Dialog, wer angelegt wird.",
      "<b>Einsatz bearbeiten:</b> Das Formular ist wie die Vorschau gegliedert; seltene Angaben liegen unter „Weitere Angaben“. Eine fehlende Einheitsführung ist jetzt gelb markiert und mit „fehlt“ beschriftet.",
      "<b>Ruhigerer Kopf:</b> Der Seitentitel bricht nicht mehr um, die Kopfzeile bleibt in allen Ansichten gleich hoch.",
      "<b>Übersicht:</b> Fehlende Angaben stehen in einer Aufgabe gebündelt, leere Zeitfenster sind eine Zeile statt sechs Striche. Diagrammachsen für Zählwerte zeigen nur ganze Zahlen.",
      "<b>Kleinigkeiten:</b> Beginn und Ende im Detail zeigen bei fehlender Angabe nur einen Strich, „Quelle“ endet nicht mehr mit einem hängenden Punkt, die Überschriftenebenen stimmen auch nach dem Wechsel der Ansicht."
    ]
  },
  {
    date: "2026-11-14",
    version: "2026-11-14.2",
    items: [
      "<b>Zahlen besser lesbar:</b> Ziffern in Tabellen, Kennzahlen, Chips und Eingabefeldern verwechseln Eins und großes I sowie Null und O nicht mehr.",
      "<b>Einlesen übersichtlicher:</b> In der Vorschau stehen zuerst die Angaben, die jeder Bericht hat. Seltene Angaben (Abbruch, Brandverlauf, gerettete und verletzte Personen) sind unter „Weitere Angaben“ eingeklappt und öffnen sich, sobald der Bericht etwas enthält. „In Statistik übernehmen“ bleibt am unteren Rand sichtbar.",
      "<b>Leere Auswertungen:</b> Ohne Einsätze oder ohne Zeitangaben erklärt die Auswertung, was fehlt, statt leerer Diagramme.",
      "<b>Handy:</b> Der Kopf braucht weniger Platz, und die Reiterleiste zeigt am Rand, dass sie weiter läuft.",
      "<b>Screenreader:</b> Diagrammsäulen haben Namen, Tabellenköpfe im Einlesen-Fenster sind zugeordnet, Überschriften springen nicht mehr."
    ]
  },
  {
    date: "2026-11-14",
    items: [
      "<b>Bedienung per Tastatur besser sichtbar:</b> Der Fokusrahmen ist im roten Kopf weiß und in Eingabefeldern deutlich zu erkennen. Rahmen von Eingabefeldern sind kräftiger.",
      "<b>Handy und Tablet:</b> Knöpfe, Filter, Kontrollkästchen und das ?-Symbol lassen sich auf Touchgeräten leichter treffen."
    ]
  },
  {
    date: "2026-11-13",
    version: "2026-11-13.2",
    items: [
      "<b>Sammelübernahme sicherer:</b> Ein Doppelklick sendet keinen Bericht zweimal. Bei einem Fehler hält die Übernahme an, der Fehler steht am betroffenen Bericht, die Meldung nennt ihn, und der Knopf ist danach wieder bedienbar.",
      "<b>Verspätetes Eintreffen:</b> Zu späte Zeiten sind jetzt zusätzlich mit einem Symbol gekennzeichnet und in einem eigenen Ockerton gesetzt, nicht mehr im Rot der Wehr. Bildschirmleser lesen „nicht innerhalb von 10 Minuten“ mit.",
      "<b>Rückgängig beim Löschen:</b> Die Frist beträgt 15 Sekunden und steht still, solange der Mauszeiger oder die Tastatur auf der Meldung liegt. Mehrere Löschungen hintereinander bleiben einzeln rückgängig zu machen (Strg+Z).",
      "<b>Stichwortsuche:</b> Die Vorschlagsliste wird Bildschirmlesern als Auswahlfeld mit Trefferzahl und markiertem Eintrag angesagt.",
    ],
  },
  {
    date: "2026-11-13",
    items: [
      "<b>Berichte einlesen klarer:</b> Das Band über jedem Bericht sagt jetzt mit Wort und Symbol, ob der Bericht <i>bereit</i>, <i>zu prüfen</i> oder <i>übernommen</i> ist. Rot erscheint nur noch bei Fehlern. Was geprüft werden muss (Hinweise, Abweichungen, neue Personen), steht oben in der Karte; neue Personen sind mit „neu“ gekennzeichnet.",
      "<b>Sammelübernahme:</b> Berichte ohne Hinweise, neue Personen und Abweichungen lassen sich mit einem Klick gemeinsam übernehmen. Die übrigen bleiben zur Prüfung stehen.",
      "<b>Rückfragen und Fehlermeldungen:</b> Statt der Browser-Fenster erscheinen eigene Dialoge, deren Knöpfe sagen, was passiert („Vorschauen verwerfen“). Fehlermeldungen nennen den betroffenen Bericht, was nicht gespeichert wurde und wie es weitergeht; Ihre Eingaben bleiben stehen.",
      "<b>Bedienung mit Tastatur und Bildschirmleser:</b> Spaltenköpfe der Einsatzliste sind echte Knöpfe, der aktive Reiter wird angesagt, Meldungen unten werden vorgelesen, und jede Ansicht hat einen eigenen Titel im Browser-Tab.",
    ],
  },
  {
    date: "2026-10-16",
    items: [
      "<b>Kostenersatz:</b> Abgerechnet werden nur noch die ausgerückten und eingesetzten Fahrzeuge und die auf ihnen eingetragene Mannschaftsstärke. Anwesende im Feuerwehrhaus und Fahrzeuge, die nicht eingesetzt wurden („nur bereit“), kosten nichts; dazu erscheint ein Hinweis.",
    ],
  },
  {
    date: "2026-10-15",
    items: [
      "<b>Berichte einlesen:</b> Ein Upload darf höchstens 100 MB groß sein (Berichte und ZIP-Inhalt zusammen) – bei größeren Mengen bitte in Teilen hochladen. Liest gerade jemand anderes Berichte ein, erscheint ein Hinweis, kurz zu warten; danach einfach erneut einlesen.",
      "<b>Rollen:</b> Wer Rollen anlegt oder ändert, kann darin nicht mehr Rechte vergeben, als er selbst hat oder über seine Verteilung ohnehin erreichen kann.",
    ],
  },
  {
    date: "2026-10-14",
    version: "2026-10-14.3",
    items: [
      "<b>Berichte abgleichen übersichtlicher:</b> Jede Zeile zeigt die Befunde jetzt auf einen Blick (z. B. „Bericht fehlt: Wehr“), mit <i>Geprüft</i> direkt in der Zeile. <i>Alle bestätigen</i> vermerkt alle offenen Befunde auf einmal als geprüft. „Einsatz öffnen“ springt direkt zum Einsatz in der Einsatzliste.",
      "<b>Einsätze: „Zu erledigen“:</b> Neuer Filter für Einsätze mit Prüfhinweisen, fehlender Nummer oder einem offenen Hinweis an die Wehr. Betroffene Einsätze tragen in der Liste einen Punkt, der Grund steht im Tooltip.",
    ],
  },
  {
    date: "2026-10-14",
    version: "2026-10-14.2",
    items: [
      "<b>Handarbeit bleibt erhalten:</b> Wird ein Bericht erneut eingelesen und der Einsatz aktualisiert, überschreibt er keine Angaben mehr, die Sie von Hand geändert haben (Felder, Fahrzeugzeiten, Anwesenheit). Das gilt auch, wenn der Bericht einen Wert gar nicht enthält oder die Anwesenheitsliste leer ist. In der Vorschau steht dann „bleibt wie erfasst“. Möchten Sie den Berichtswert doch, tragen Sie ihn in der Vorschau ein.",
      "<b>Neue Auswertungen unter „Auswertungen“:</b> <i>Abbrüche &amp; Anlagen</i> (warum Einsätze abgebrochen wurden, Fehlalarme, Brandmeldeanlagen je Anlage bzw. Objekt), <i>Fahrzeuge &amp; Atemschutz</i> (Alarmierungen, Ausfahrten und tatsächliche Einsätze je Fahrzeug, Einsatzstunden, Geräteträger und Minuten unter Atemschutz) und <i>Brand &amp; Rettung</i> (Zeit bis „Brand unter Kontrolle“ und „Feuer aus“, Innen-/Außenangriff, Brandwachen, Menschenrettung und Verletzte).",
      "<b>Personal:</b> Neue Spalten für Einsätze unter Atemschutz und Atemschutzminuten sowie je Person die besetzten Funktionen (Einheitsführer, Maschinist, Angriffstrupp …) im aufgeklappten Eintrag.",
      "<b>Mehr aus dem BKS-Bericht:</b> Objekt, Nummer der Brandmeldeanlage, Einsatztaktik, Brandzeiten, Menschenrettung und Verletzte, ob ein Fahrzeug eingesetzt war, sowie Atemschutz je Person werden übernommen und stehen im Einsatz (auch bearbeitbar). <b>Bereits erfasste Einsätze:</b> den Bericht erneut einlesen und aktualisieren, damit die neuen Angaben übernommen werden – bis dahin zählen sie als „nicht angegeben“, nie als null.",
    ],
  },
  {
    date: "2026-10-14",
    items: [
      "<b>Abgebrochene Einsätze:</b> Der „Einsatzabbruch“ aus dem BKS-Bericht wird jetzt übernommen und steht im Einsatz (auch bearbeitbar). Fehlt die Eintreffzeit und ist ein Abbruch hinterlegt, gilt der Einsatz in „Eintreffen und verfügbare Kräfte“ als rechtzeitig eingetroffen. <b>Bereits erfasste Einsätze:</b> den Bericht erneut einlesen und aktualisieren, damit der Abbruch übernommen wird.",
      "<b>BKS-Portal:</b> Der Link zum Bericht öffnet jetzt direkt den richtigen Bereich im Portal.",
      "<b>Hilfetexte:</b> Orte werden in den Hilfetexten nicht mehr namentlich genannt. Welche Orte zum Ausrückebereich zählen, legt die Verwaltung unter <i>Einstellungen → Orte &amp; Zeitgrenzen</i> fest.",
    ],
  },
  {
    date: "2026-10-05",
    items: [
      "<b>Sicherer abmelden:</b> „Abmelden“ beendet die Sitzung jetzt auch auf dem Server – ein kopiertes Anmelde-Cookie ist danach wertlos. Superadmins sehen unter <i>Einstellungen → Sitzungen</i>, wer angemeldet ist, und können einzelne Sitzungen, alle einer Person oder alle anderen beenden. <b>Einmalig nach dem Update:</b> alle melden sich neu an.",
    ],
  },
  {
    date: "2026-10-04",
    items: [
      "<b>Kostenersatz leichter finden:</b> Unter „Einsätze“ gibt es jetzt den eigenen Unterreiter <i>Kostenersatz</i> (Verbandsgemeinde-Ansicht). Dort einen Einsatz wählen und die Kosten berechnen – nicht mehr nur versteckt im aufgeklappten Einsatz unter „Berichte abgleichen“.",
      "<b>Neu geordnet:</b> Die Reiter heißen jetzt <i>Übersicht</i>, <i>Einsätze</i>, <i>Auswertungen</i>, <i>Personal</i> und <i>Einstellungen</i>. „Berichte abgleichen“ (früher Prüfprotokoll) ist ein Unterreiter von „Einsätze“, „Datenschutz &amp; Vertrag“ (früher Auftragsverarbeitung) steht unter „Einstellungen“. Die Auswahl oben heißt „Feuerwehr / Verbandsgemeinde“ (früher „Ansicht“ bzw. „Wehrleitung“). Gespeicherte Links funktionieren weiter.",
      "<b>Verständlichere Begriffe:</b> Azeit heißt jetzt <i>Ausrückdauer</i>, Ezeit <i>Zeit bis zum Eintreffen</i>, EHF <i>Einheitsführung</i>, „Kameraden“ <i>Einsatzteilnahmen</i> (Reiter „Personal“). Das gilt auch im Excel-Export.",
      "<b>Ehrlicher benannt:</b> Der „Feuerwehrbedarfsplan Pos. 8.4“ heißt <i>Eintreffen und verfügbare Kräfte</i>. Die Karte zeigt, wie oft das erste eigene Fahrzeug rechtzeitig eintraf, und zählt die Personen – sie ersetzt keinen Bedarfsplan und prüft keine Funktionen oder Qualifikationen. Die Hilfe erklärt, was sie aussagt.",
      "<b>Übersicht:</b> Jahreskennzahlen, offene Aufgaben (Einsätze mit Prüfhinweisen oder fehlenden Angaben – ein Klick zeigt sie in der Liste) und die Datenvollständigkeit. Kennzahlen nennen jetzt, für wie viele Einsätze sie berechnet werden konnten („42 von 57 Einsätzen auswertbar“); Fehlendes zählt nie als null.",
      "<b>Zeiten &amp; Kräfte:</b> Ausrückdauer, Anfahrtdauer je Fahrzeug und Zeit bis zum Eintreffen mit Median und 90. Perzentil, Kräfteaufbau nach 5, 10 und 15 Minuten sowie die Zeiten nach Tageszeit und Ort. Zeilen mit weniger als 5 Einsätzen sind gekennzeichnet. Wie „Eintreffen und verfügbare Kräfte“ nur sichtbar, wenn freigegeben.",
      "<b>Belastung:</b> Lange, nächtliche und Wochenend-Einsätze mit Stunden, Verteilung der Einsatzdauer und zeitliche Überschneidung von Einsätzen.",
      "<b>Viele Berichte auf einmal:</b> Größere Mengen (z. B. ein ZIP mit allen Berichten des Jahres) brechen nicht mehr mit einem Zeitfehler ab. Die Berichte werden im Hintergrund und schneller gelesen; die Anzeige zeigt, wie viele schon gelesen sind.",
    ],
  },
  {
    date: "2026-10-03",
    items: [
      "<b>Aus der Auswertung in die Liste:</b> Ein Klick auf einen Balken oder eine Säule (Monat, Wochentag, Uhrzeit, Ort, Art, Alarmstufe, Wehr) oder auf die Zahlen im Bedarfsplan zeigt genau diese Einsätze.",
      "<b>Einsatzliste:</b> Spalten sortierbar, neuer Filter „Prüfhinweise“ für unvollständige Einsätze, Filter und Suche bleiben beim Neuladen erhalten und lassen sich als Link weitergeben. Im geöffneten Einsatz blättern „Vorheriger“ und „Nächster“.",
      "<b>Nichts mehr verlieren:</b> Bei ungespeicherten Änderungen an einem Einsatz fragt die App vor dem Wechsel von Reiter, Jahr oder Wehr. Ein gelöschter Einsatz lässt sich einige Sekunden lang mit „Rückgängig“ zurückholen.",
      "<b>Schneller:</b> Tastenkürzel (<kbd>/</kbd> Suche, <kbd>i</kbd> Einlesen, <kbd>j</kbd>/<kbd>k</kbd> blättern, <kbd>e</kbd> bearbeiten, <kbd>?</kbd> Übersicht). Berichte lassen sich auf das ganze Fenster ziehen.",
      "<b>Verwaltung:</b> Fahrzeugtabellen kompakt oder mit allen Spalten und mit Suche, Stichworte mit Filter „nur Abweichungen“, feste Tabellenköpfe beim Scrollen. Der zuletzt offene Bereich wird gemerkt.",
      "<b>Einstellungen für die ganze VG:</b> Bei gewählter Wehrleitung pflegen Sie Fahrzeuge, BKS-Kennung, Orte, Bedarfsplan, Farben und Stichworte einmal für alle Wehren der VG – Fahrzeuge aller Wehren in einer Tabelle, Standort und Ausrückebereich je Wehr in einer Übersicht. Eine Wehr übernimmt die Vorgaben und kann bei sich abweichen; die Verwaltung zeigt an jedem Wert „von der VG“ oder „abweichend“. Der Bereich „Fahrzeuge der VG“ ist in „Fahrzeuge“ aufgegangen.",
      "<b>Verwaltung:</b> Ein Klick auf einen Bereich wechselt nicht mehr zwischen Wehr und Wehrleitung; gewechselt wird nur über die Auswahl oben rechts.",
      "<b>Orte ohne Namensanfang:</b> Unter „Orte & Bedarfsplan“ genügt der Ortsname. Ein Einsatz gehört zu dem Ort, mit dessen Namen der Einsatzort beginnt (z. B. „Musterstadt-Nord“ → Musterstadt).",
      "<b>BKS-Kennung vereinfacht:</b> Es genügt die Einheit aus der Kopfzeile des Berichts (z. B. „FW NR#.ABC 02“); die Funkrufnamen der eigenen Fahrzeuge leitet die App daraus ab. Das Testfeld nimmt jetzt beliebigen Text aus einem Bericht, auch einzelne Funkrufnamen.",
      "<b>Berichte prüfen:</b> Auch Stammdatensätze und Weiterleitungen werden erst nach Ihrer ausdrücklichen Bestätigung gespeichert. Schließen verwirft offene Vorschauen, nicht bereits bestätigte Berichte.",
      "<b>Abgleich:</b> Änderungen an Beschreibung, Leitstellen-Nummer, Anwesenheit und Sekunden werden genauer erkannt.",
      "<b>Smartphone:</b> Die Aktionen im Kopfbereich können umbrechen und bleiben erreichbar.",
      "<b>Kostenersatz:</b> Ohne zum Einsatztag gültige Gebührenordnung erfolgt keine automatische Auswahl einer späteren Fassung.",
      "<b>Gemeinsames Bearbeiten:</b> Die Oberfläche erkennt inzwischen geänderte Einsätze und verhindert das Überschreiben eines neueren Standes.",
      "<b>Auswertung:</b> Fehlende Anwesenheit wird als unvollständige Datengrundlage kenntlich gemacht. Der Kennzahlen-Export berücksichtigt Auswahl und Frist.",
      "<b>Importhinweise:</b> Hinweise aus dem ursprünglichen Bericht sind als historische Hinweise gekennzeichnet.",
      "<b>Aktueller Datenstand:</b> Fehlende Einsatzzeiten und Anwesenheiten werden unabhängig von der Importhistorie erneut geprüft. Die Leitstellen-Nummer lässt sich im Formular korrigieren.",
      "<b>Nachverarbeitung:</b> Offene zentrale Importarbeiten werden automatisch wiederholt und angezeigt. Bereits gespeicherte Einsätze müssen nicht erneut importiert werden.",
      "<b>Ladefehler:</b> Mit „Erneut versuchen“ bleibt die Ansicht nutzbar.",
    ],
  },
  {
    date: "2026-10-02",
    items: [
      "<b>Einsatz bearbeiten:</b> Ausrücken und Eintreffen zeigen die Sekunden. Beim Speichern bleiben die Zeiten aus dem Bericht genau erhalten.",
      "<b>Kameraden mit gleichem Nachnamen</b> (z. B. Geschwister) werden beim Einlesen nicht mehr zusammengelegt.",
      "<b>Bericht übernehmen</b> geht je Bericht nur einmal – ein Doppelklick legt keinen zweiten Einsatz an. Einen erfassten Einsatz aktualisiert, wer Einsätze bearbeiten darf.",
      "<b>Einstellungen:</b> Ist inzwischen ein Fahrzeug dazugekommen (z. B. beim Einlesen), bittet die App, die Seite neu zu laden, statt es zu überschreiben. Der Tag darf bis 24 Uhr gehen.",
      "<b>Hochladen:</b> höchstens 200 MB auf einmal, größere Mengen bitte in Teilen.",
      "<b>Bearbeiten und Vorschau:</b> Eingaben bleiben erhalten, wenn man währenddessen sucht, filtert, eine andere Zeile aufklappt oder einen anderen Bericht übernimmt.",
      "<b>EHF und Einsatzleiter</b> sieht nur, wer auch die Anwesenheit sehen darf.",
      "<b>Kostenersatz:</b> Ersatzfahrzeuge werden nach ihrem eigenen Fahrzeugtyp berechnet, lange Einsätze mit den vollen Stunden. Ein Hinweis erscheint, wenn der Einsatz vor dem Gültigkeitsbeginn der Gebührenordnung liegt.",
      "<b>Nummerierung nach Datum:</b> Ein Einsatz lässt sich in ein anderes Jahr verschieben.",
      "<b>Rollen selbst gestalten:</b> Unter Verwaltung → <b>Rollen</b> steht, welche Rolle was darf. Der Wehrleiter kann eigene Rollen für seine VG anlegen – zum Beispiel einen „Gruppenführer“, der Einsätze einliest und bearbeitet, aber nicht löscht.",
      "<b>Feinere Rechte:</b> Ansehen, Exportieren, Einlesen, Bearbeiten und Löschen von Einsätzen sind getrennte Rechte. Schaltflächen, die man nicht nutzen darf, sind ausgeblendet.",
      "<b>Mehrere Rollen</b> je Person sind möglich. Unter Verwaltung → Benutzer zeigt <b>Rechte</b>, was jemand darf und woher; das <b>Protokoll</b> zeigt, wer wann Rollen vergeben oder geändert hat.",
      "<b>Hilfe passend zur Ansicht:</b> Das <b>?</b> im Kopf öffnet die Hilfe direkt beim Thema der aktuellen Seite – auch im Fenster „Bericht einlesen“ und in jedem Bereich der Verwaltung.",
      "<b>Neuigkeiten</b> und <b>Feedback</b> im Hilfefenster: Hier steht, was neu ist. Fragen, Fehler und Wünsche gehen direkt an den Betreiber.",
      "<b>Anwesenheit</b> sehen nur noch Wehrführer und Erfasser. Der Wehrleiter sieht die Zahl der Personen, aber keine Namen.",
      "<b>Wehrleitung:</b> Die Verwaltung zeigt alle Fahrzeuge der VG. Sie lassen sich einer Wehr zuordnen.",
      "<b>Fahrzeugliste:</b> Den Fahrzeugtyp liest die App aus dem Funkrufnamen. Doppelte Fahrzeuge entstehen nicht mehr.",
      "<b>Excel-Export</b> aus dem BKS-Portal lässt sich wie die PDF einlesen.",
      "Fahrzeuge erscheinen mit dem <b>vollen Funkrufnamen</b> aus dem Bericht.",
      "<b>Kostenersatz</b> nach der Gebührenordnung der VG, berechnet je Einsatz über alle beteiligten Wehren.",
      "<b>Einsatznummern</b> wie im BKS-Portal oder nach Datum durchnummeriert. Der <b>Bedarfsplan</b> lässt sich für alle Benutzer freigeben.",
      "<b>Einsatz bearbeiten:</b> Fahrzeuge, Stärke und Anwesenheit lassen sich ändern. Unter „Kameraden“ steht, bei welchen Einsätzen jemand dabei war.",
      "<b>Prüfprotokoll</b> für den Wehrleiter: gleicht Berichte mehrerer Wehren zu einem Einsatz ab. Berichte einer anderen Wehr werden an diese weitergegeben.",
      "Ein erneut eingelesener Bericht <b>aktualisiert</b> den erfassten Einsatz. Jeder Einsatz hat einen Link ins BKS-Portal.",
      "<b>Verwaltung</b> für Wehrführer: Fahrzeuge, Orte, Bedarfsplan, Stichworte, Farben, Logos und Benutzer.",
      "<b>Gesamtansicht</b> aller Wehren einer Verbandsgemeinde für Wehrleitung und Statistik VG.",
    ],
  },
  {
    date: "2026-10-01",
    items: [
      "<b>Stichwortsuche:</b> Das Stichwort findet sich auch über das Meldebild der AAO, z. B. „Ölspur“. „B207“ wird wie „B2.07“ erkannt.",
      "<b>EHF</b> per Klick aus der Anwesenheit wählen. Neues Diagramm <b>Verlauf</b> mit den Einsätzen je Monat über mehrere Jahre.",
      "Berichte ohne Prüfhinweise übernimmt die App direkt, angezeigt werden nur die zu prüfenden.",
      "Mehrere Berichte lassen sich als <b>ZIP-Datei</b> auf einmal einlesen.",
      "<b>Anmeldung per E-Mail-Link</b>, ohne Passwort.",
    ],
  },
  {
    date: "2026-09-30",
    items: [
      "Erste Version: Einsatzberichte einlesen, Auswertung mit Bedarfsplan, Einsatzliste mit Excel-Export, Kameraden und Online-Hilfe.",
    ],
  },
];
