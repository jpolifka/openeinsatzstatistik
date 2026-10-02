"use strict";

// Neuigkeiten für die Benutzer (Reiter „Neuigkeiten“ im Hilfefenster). Neueste Version oben.
// Texte für Anwender: was sich in der Bedienung ändert, keine Technik. HTML erlaubt.
// Ein neuer Eintrag mit neuem Datum markiert das ?-Symbol im Kopf, bis die Neuigkeiten gelesen sind.
const CHANGELOG = [
  {
    date: "2026-10-02",
    items: [
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
