"use strict";

// Online-Hilfe: eine Quelle für die ?-Symbole an Feldern/Kennzahlen und das Hilfefenster.
// Schlüssel = Feld- bzw. Kennzahlname der API. short = Tooltip, text = Erklärung im Hilfefenster (HTML erlaubt).
const HELP_SECTIONS = [
  {
    title: "Einsatz erfassen",
    intro: "Diese Felder stehen in der PDF-Vorschau und unter „Einsätze → Bearbeiten“. Sie werden aus dem Einsatzbericht des BKS-Portals vorbelegt und können vor dem Übernehmen korrigiert werden.",
    entries: {
      number: {
        title: "Nr.",
        short: "Laufende Einsatznummer im Jahr (z. B. 54 für 54-26).",
        text: "Laufende Einsatznummer innerhalb des Jahres, wie im Dateinamen des Berichts (<i>54-26_B2_…pdf</i> → 54). Zusammen mit dem Jahr aus dem Einsatzbeginn erkennt die App, ob ein Einsatz schon erfasst ist.",
      },
      started_at: {
        title: "Beginn",
        short: "Früheste Alarmierung eines Rheinbrohler Fahrzeugs (02/..).",
        text: "Einsatzbeginn = frühester Alarmierungszeitpunkt der eigenen Fahrzeuge (Funkrufname 02/..). Gibt es keine, zählt die erste Alarmierung im Bericht. Alle Minutenwerte (Azeit, Ezeit) werden ab diesem Zeitpunkt gerechnet. Der Beginn bestimmt außerdem Jahr, Monat, Wochentag und das Zeitfenster Tag/Nacht.",
      },
      ended_at: {
        title: "Ende",
        short: "Spätestes Einsatzende der eigenen Fahrzeuge bzw. der FEZ.",
        text: "Einsatzende = spätestes Einsatzende der eigenen Fahrzeuge bzw. der Feuerwehreinsatzzentrale (FL NR#.LIN). Aus Beginn und Ende ergeben sich Einsatzdauer, Einsatzstunden und die Stunden je Kamerad.",
      },
      station_staff: {
        title: "Gerätehaus",
        short: "Anwesende, die auf keinem Fahrzeug saßen (Bereitschaft im Gerätehaus).",
        text: "Personen im Gerätehaus = Anwesende laut Anwesenheitsliste minus Besatzung der erfassten Fahrzeuge. Der Wert fließt in die Gesamtstärke ein.",
      },
      keyword: {
        title: "Stichwort",
        short: "Einsatzart + Alarmstufe, z. B. H2 oder B3.",
        text: "Einsatzstichwort aus Buchstabe und Ziffer. Der Buchstabe ist die Einsatzart: <b>H</b> Hilfeleistung, <b>B</b> Brand, <b>W</b> Wasser, <b>G</b> Gefahrstoff, <b>S</b> Sonderlage. Die Ziffer ist die Alarmstufe (1–4). Aus <i>H2.03</i> wird Stichwort H2, Stufe 03; eine Brandsicherheitswache wird als S1 / 00 geführt. Wer das ganze Stichwort ins Feld schreibt – mit oder ohne Punkt, also <i>B2.07</i> oder <i>B207</i> –, bekommt es automatisch in Stichwort und Stufe aufgeteilt.",
      },
      subcode: {
        title: "Stufe",
        short: "Unterstichwort nach dem Punkt, z. B. 07 aus B2.07.",
        text: "Zweistellige Ergänzung nach dem Punkt des Einsatzstichworts (<i>B2.07</i> → 07). Sie unterscheidet Einsätze innerhalb eines Stichworts; B2.07 (Brandmeldeanlage) und S1.00 (Brandsicherheitswache) werden in der Auswertung gesondert gezählt. Nicht verwechseln mit der Alarmstufe – die steckt in der Ziffer des Stichworts.",
      },
      description: {
        title: "Einsatz",
        short: "Kurzbeschreibung: Meldebild / Objekt oder Straße.",
        text: "Kurzbeschreibung im Format <i>Meldebild / Objekt</i>, ersatzweise <i>Meldebild / Straße</i>. Wird in der Einsatzliste angezeigt und von der Suche durchsucht.",
      },
      place: {
        title: "Ort",
        short: "Einsatzort; bestimmt Einsatzgebiet und Bedarfsplan.",
        text: "Ortsteil oder Ort des Einsatzes. Bekannte Orte (Rheinbrohl, Arienheller, Hammerstein, Ariendorf, Bad Hönningen, Leutesdorf) werden vorgeschlagen. Nur Einsätze in Rheinbrohl, Hammerstein und Arienheller zählen für den Feuerwehrbedarfsplan – bitte den Ort daher genau so schreiben.",
      },
      unit_leader: {
        title: "EHF",
        short: "Einheitsführer, Schreibweise „V. Nachname“.",
        text: "Einheitsführer des Einsatzes in der Schreibweise <i>V. Nachname</i>. Übernommen wird die Person mit der Funktion „Einheitsführer“. Fehlt sie im Bericht, wird der Einsatzleiter eingetragen und ein Prüfhinweis erzeugt – ist auch der nicht in der Anwesenheit, bleibt das Feld leer und ist rot markiert. Ein Klick auf einen Namen in der Anwesenheit trägt diese Person als EHF ein.",
      },
    },
  },
  {
    title: "Kennzahlen je Einsatz",
    intro: "Werden aus den Fahrzeugzeiten berechnet und sind nicht direkt änderbar – korrigieren Sie bei Bedarf Beginn oder Ende.",
    entries: {
      turnout_min: {
        title: "Azeit (Ausrückezeit)",
        short: "Minuten von der Alarmierung bis zum Ausrücken des schnellsten Fahrzeugs.",
        text: "Minuten vom Einsatzbeginn bis zum Ausrücken (Status 3) des schnellsten eigenen Fahrzeugs. In der Fahrzeugtabelle steht die Azeit je Fahrzeug.",
      },
      arrival_min: {
        title: "Ezeit (Eintreffzeit)",
        short: "Minuten von der Alarmierung bis zum Eintreffen des ersten Fahrzeugs.",
        text: "Minuten vom Einsatzbeginn bis zum Eintreffen (Status 4) des ersten eigenen Fahrzeugs an der Einsatzstelle. Rot markiert, wenn sie über 8 Minuten liegt. Ohne Eintreffzeit wird der Einsatz im Bedarfsplan nicht berücksichtigt.",
      },
      on_time: {
        title: "8 Min. erreicht",
        short: "Ja, wenn das erste Fahrzeug innerhalb der Zeitgrenze eingetroffen ist.",
        text: "„Ja“, wenn die Ezeit höchstens der Zeitgrenze entspricht (8 Minuten; in der Auswertung auf 10 umschaltbar). Grundlage des Erreichungsgrads im Feuerwehrbedarfsplan.",
      },
      crew_on_arrival: {
        title: "Stärke bei Eintreffen",
        short: "Besatzung der Fahrzeuge, die als erste eingetroffen sind.",
        text: "Summe der Besatzung aller Fahrzeuge, die zum Zeitpunkt der Ezeit eingetroffen sind.",
      },
      crew_within_limit: {
        title: "Stärke nach 8 Min.",
        short: "Zusätzliche Kräfte, die bis zur Zeitgrenze nachgekommen sind.",
        text: "Summe der Besatzung der Fahrzeuge, die nach dem ersten Fahrzeug, aber noch innerhalb der Zeitgrenze (8 bzw. 10 Minuten) eingetroffen sind.",
      },
      crew_within_second: {
        title: "Stärke nach 15 Min.",
        short: "Zusätzliche Kräfte zwischen Zeitgrenze und 15 Minuten.",
        text: "Summe der Besatzung der Fahrzeuge, die nach der Zeitgrenze und bis 15 Minuten nach Einsatzbeginn eingetroffen sind.",
      },
      crew_total: {
        title: "Gesamtstärke",
        short: "Besatzung aller Fahrzeuge plus Personen im Gerätehaus.",
        text: "Besatzung aller eigenen Fahrzeuge plus Personen im Gerätehaus. Im Bedarfsplan wird – wie in der Einsatzübersicht – ohne 01/10 gerechnet.",
      },
      duration: {
        title: "Dauer",
        short: "Zeit von Beginn bis Ende des Einsatzes.",
        text: "Zeit von Einsatzbeginn bis Einsatzende. Grundlage für Einsatzstunden, Personalstunden und die Stunden je Kamerad.",
      },
      time_window: {
        title: "Zeitfenster",
        short: "Werktag oder Sa/So/Feiertag, Tag (06–18 Uhr) oder Nacht.",
        text: "Einordnung nach Einsatzbeginn: <b>Tag</b> 06:00–18:00 Uhr, sonst <b>Nacht</b>; <b>Sa/So/Feiertag</b> an Wochenenden und gesetzlichen Feiertagen in Rheinland-Pfalz, sonst <b>Werktag</b>. In der Liste als „WE/FT“ gekennzeichnet.",
      },
      vehicles: {
        title: "Fahrzeuge",
        short: "Stärke sowie Ausrücke- und Eintreffzeit je Fahrzeug.",
        text: "Je Fahrzeug (02/45, 02/24, 02/71, 02/19, 01/10 – in der Reihenfolge der Einsatzübersicht): Stärke, Uhrzeit Ausrücken und Eintreffen sowie die daraus berechneten Minuten. 01/23 wird bei Rheinbrohler Besatzung als Ersatz im Block 02/45 eingetragen. Grau = nicht im Einsatz.",
      },
      warnings: {
        title: "Prüfhinweise",
        short: "Auffälligkeiten beim Einlesen – bitte kontrollieren.",
        text: "Automatisch erzeugte Hinweise, z. B. fehlender Einheitsführer, nicht ermittelbarer Beginn/Ende oder Fahrzeuge, die keinem Block der Einsatzübersicht zugeordnet sind. Berichte ohne Prüfhinweise, ohne neue Personen und ohne Abweichungen werden beim Einlesen direkt übernommen; nur die übrigen erscheinen zur Kontrolle. Hinweise verhindern das Übernehmen nicht.",
      },
      attendance: {
        title: "Anwesenheit",
        short: "Alle Personen laut Anwesenheitsliste des Berichts.",
        text: "Personen aus der Anwesenheitsliste des Berichts, mit Fahrzeug und Funktion. Namen werden mit den bekannten Kameraden abgeglichen; unbekannte Namen sind markiert und werden beim Übernehmen als neue Kameraden angelegt. Beim Bearbeiten und in der PDF-Vorschau trägt ein Klick auf einen Namen die Person als EHF ein; der EHF ist dunkelrot hervorgehoben.",
      },
    },
  },
  {
    title: "Auswertung",
    intro: "Alle Werte beziehen sich auf das oben rechts gewählte Jahr. Jedes Diagramm lässt sich über „Tabelle“ als Zahlentabelle anzeigen.",
    entries: {
      history: {
        title: "Verlauf",
        short: "Einsätze je Monat über alle erfassten Jahre.",
        text: "Einsätze je Monat über alle erfassten Jahre, das gewählte Jahr ist hinterlegt. Die dunkle Linie ist der gleitende Durchschnitt der letzten 12 Monate (Einsätze je Monat) – sie glättet Ausreißer und zeigt, ob die Einsatzzahlen langfristig steigen oder fallen. Sie beginnt erst, wenn 12 Monate vorliegen.",
      },
      per_week: {
        title: "Einsätze / Woche",
        short: "Einsätze geteilt durch die Kalenderwochen des Jahres.",
        text: "Anzahl Einsätze geteilt durch die Kalenderwochen – im laufenden Jahr bis zur aktuellen KW, sonst über das ganze Jahr.",
      },
      operation_hours: {
        title: "Einsatzstunden",
        short: "Summe der Dauer aller Einsätze.",
        text: "Summe der Einsatzdauer aller Einsätze des Jahres (unabhängig von der Anzahl der Einsatzkräfte).",
      },
      staff_hours: {
        title: "Personalstunden",
        short: "Einsatzdauer × anwesende Kameraden, über alle Einsätze.",
        text: "Für jeden Einsatz Dauer × Anzahl der Anwesenden, aufsummiert über das Jahr. Darunter steht die durchschnittliche Zahl Anwesender je Einsatz.",
      },
      response_plan: {
        title: "Feuerwehrbedarfsplan Pos. 8.4",
        short: "Anteil der Einsätze, bei denen das erste Fahrzeug rechtzeitig eintraf.",
        text: "Berücksichtigt werden Einsätze ab Alarmstufe 2 (Stichwort x2–x4) in Rheinbrohl, Hammerstein und Arienheller mit Eintreffzeit. Erreichungsgrad = Anteil der Einsätze, bei denen das erste Fahrzeug innerhalb der Zeitgrenze (8 oder 10 Minuten, umschaltbar) eingetroffen ist – getrennt nach den vier Zeitfenstern Werktag/Wochenende × Tag/Nacht. Die Stärken sind Mittelwerte je Einsatz.",
      },
      alarm_level: {
        title: "Alarmstufen",
        short: "Ziffer im Stichwort, z. B. H2 → Stufe 2.",
        text: "Die Alarmstufe ist die Ziffer im Einsatzstichwort (H<b>2</b>, B<b>3</b> …). Sie ist unabhängig von der zweistelligen „Stufe“ nach dem Punkt.",
      },
      area: {
        title: "Einsatzgebiet",
        short: "Einsätze je Ort anhand des Anfangs des Ortsnamens.",
        text: "Zuordnung nach dem Anfang des Ortsnamens (z. B. „Rheinbrohl-…“ → Rheinbrohl). Orte außerhalb der bekannten Liste erscheinen als „sonstige“.",
      },
    },
  },
  {
    title: "Kameraden",
    intro: "Anwesenheit je Kamerad im gewählten Jahr. Spaltenköpfe anklicken zum Sortieren.",
    entries: {
      participation: {
        title: "Beteiligung",
        short: "Anteil der Einsätze des Jahres, bei denen der Kamerad anwesend war.",
        text: "Einsätze des Kameraden geteilt durch alle Einsätze des Jahres.",
      },
      hours: {
        title: "Stunden",
        short: "Summe der Einsatzdauer aller Einsätze mit Teilnahme.",
        text: "Summe der Einsatzdauer aller Einsätze, bei denen der Kamerad in der Anwesenheit steht.",
      },
      nights_weekends: {
        title: "nachts / Sa/So/FT",
        short: "Einsätze zwischen 18 und 6 Uhr bzw. an Wochenenden und Feiertagen.",
        text: "Anzahl der Einsätze mit Beginn in der Nacht (18:00–06:00 Uhr) bzw. an Samstagen, Sonntagen und Feiertagen.",
      },
    },
  },
];

const HELP = Object.fromEntries(HELP_SECTIONS.flatMap((s) => Object.entries(s.entries)));

/** Kleines ?-Symbol: Tooltip mit Kurztext, Klick öffnet das Hilfefenster an der Stelle. */
function helpButton(key) {
  const h = HELP[key];
  if (!h) return "";
  return `<button type="button" class="help-btn" data-help="${key}" data-tip="${esc(h.short)}" aria-label="Hilfe: ${esc(h.title)}">?</button>`;
}

function helpContent() {
  return HELP_SECTIONS.map((s) => `<section class="help-section">
    <h3>${s.title}</h3>${s.intro ? `<p class="muted">${s.intro}</p>` : ""}
    <dl class="help-list">${Object.entries(s.entries).map(([k, e]) =>
      `<div id="help-${k}"><dt>${e.title}</dt><dd>${e.text}</dd></div>`).join("")}</dl>
  </section>`).join("");
}

function openHelp(key) {
  const dialog = $("#help-dialog");
  const body = $("#help-body");
  if (!body.innerHTML) body.innerHTML = helpContent();
  for (const el of body.querySelectorAll(".highlight")) el.classList.remove("highlight");
  if (!dialog.open) dialog.showModal();
  const target = key && $(`#help-${key}`);
  if (target) {
    target.classList.add("highlight");
    target.scrollIntoView({ block: "center" });
  } else {
    body.scrollTop = 0;
  }
}

document.addEventListener("click", (e) => {
  const button = e.target.closest("[data-help]");
  if (!button) return;
  e.preventDefault();          // ?-Symbol steht teils in <label>/<th> – dort nichts anderes auslösen
  e.stopPropagation();
  openHelp(button.dataset.help);
}, true);

/** Fest in index.html stehende Elemente mit data-help-key bekommen ihr ?-Symbol aus derselben Quelle. */
function addHelpButtons() {
  for (const el of document.querySelectorAll("[data-help-key]")) el.insertAdjacentHTML("beforeend", helpButton(el.dataset.helpKey));
}
