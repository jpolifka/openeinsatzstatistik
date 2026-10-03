"use strict";

// Neuigkeiten für die Benutzer (Reiter „Neuigkeiten“ im Hilfefenster). Neueste Version oben.
// Texte für Anwender: was sich in der Bedienung ändert, keine Technik. HTML erlaubt.
// Ein neuer Eintrag mit neuem Datum markiert das ?-Symbol im Kopf, bis die Neuigkeiten gelesen sind.
const CHANGELOG = [
  {
    date: "2026-10-03",
    items: [
      "<b>BKS-Kennung vereinfacht:</b> Es genügt die Einheit aus der Kopfzeile des Berichts (z. B. „FW NR#.ABC 02“); die Funkrufnamen der eigenen Fahrzeuge leitet die App daraus ab. Das Testfeld nimmt jetzt beliebigen Text aus einem Bericht, auch einzelne Funkrufnamen.",
      "<b>Gebührenordnung leichter finden:</b> In der Verwaltung stehen „Fahrzeuge der VG“ und „Gebührenordnung“ jetzt auch bei ausgewählter Wehr; ein Klick wechselt zur Wehrleitung ihrer VG.",
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
