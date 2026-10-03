"use strict";

// Neuigkeiten für die Benutzer (Reiter „Neuigkeiten“ im Hilfefenster). Neueste Version oben.
// Texte für Anwender: was sich in der Bedienung ändert, keine Technik. HTML erlaubt.
// Ein neuer Eintrag mit neuem Datum markiert das ?-Symbol im Kopf, bis die Neuigkeiten gelesen sind.
const CHANGELOG = [
  {
    date: "2026-10-02",
    items: [
      "<b>Einsatz bearbeiten:</b> Ausrücken und Eintreffen zeigen die Sekunden. Beim Speichern bleiben die Zeiten aus dem Bericht genau erhalten.",
      "<b>Kameraden mit gleichem Nachnamen</b> (z. B. Geschwister) werden beim Einlesen nicht mehr zusammengelegt.",
      "<b>Bericht übernehmen</b> geht je Bericht nur einmal – ein Doppelklick legt keinen zweiten Einsatz an. Einen erfassten Einsatz aktualisiert, wer Einsätze bearbeiten darf.",
      "<b>Einstellungen:</b> Ist inzwischen ein Fahrzeug dazugekommen (z. B. beim Einlesen), bittet die App, die Seite neu zu laden, statt es zu überschreiben. Der Tag darf bis 24 Uhr gehen.",
      "<b>Hochladen:</b> höchstens 200 MB auf einmal, größere Mengen bitte in Teilen.",
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
