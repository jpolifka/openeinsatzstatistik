"use strict";

// Online-Hilfe: eine Quelle für die ?-Symbole an Feldern/Kennzahlen und das Hilfefenster.
// kurz = Tooltip, text = ausführliche Erklärung im Hilfefenster (HTML erlaubt).
const HILFE_ABSCHNITTE = [
  {
    titel: "Einsatz erfassen",
    einleitung: "Diese Felder stehen in der PDF-Vorschau und unter „Einsätze → Bearbeiten“. Sie werden aus dem Einsatzbericht des BKS-Portals vorbelegt und können vor dem Übernehmen korrigiert werden.",
    eintraege: {
      nr: {
        titel: "Nr.",
        kurz: "Laufende Einsatznummer im Jahr (z. B. 54 für 54-26).",
        text: "Laufende Einsatznummer innerhalb des Jahres, wie im Dateinamen des Berichts (<i>54-26_B2_…pdf</i> → 54). Zusammen mit dem Jahr aus dem Einsatzbeginn erkennt die App, ob ein Einsatz schon erfasst ist.",
      },
      beginn: {
        titel: "Beginn",
        kurz: "Früheste Alarmierung eines Rheinbrohler Fahrzeugs (02/..).",
        text: "Einsatzbeginn = frühester Alarmierungszeitpunkt der eigenen Fahrzeuge (Funkrufname 02/..). Gibt es keine, zählt die erste Alarmierung im Bericht. Alle Minutenwerte (Azeit, Ezeit) werden ab diesem Zeitpunkt gerechnet. Der Beginn bestimmt außerdem Jahr, Monat, Wochentag und das Zeitfenster Tag/Nacht.",
      },
      ende: {
        titel: "Ende",
        kurz: "Spätestes Einsatzende der eigenen Fahrzeuge bzw. der FEZ.",
        text: "Einsatzende = spätestes Einsatzende der eigenen Fahrzeuge bzw. der Feuerwehreinsatzzentrale (FL NR#.LIN). Aus Beginn und Ende ergeben sich Einsatzdauer, Einsatzstunden und die Stunden je Kamerad.",
      },
      personen_gh: {
        titel: "Gerätehaus",
        kurz: "Anwesende, die auf keinem Fahrzeug saßen (Bereitschaft im Gerätehaus).",
        text: "Personen im Gerätehaus = Anwesende laut Anwesenheitsliste minus Besatzung der erfassten Fahrzeuge. Der Wert fließt in die Gesamtstärke ein.",
      },
      stichwort: {
        titel: "Stichwort",
        kurz: "Einsatzart + Alarmstufe, z. B. H2 oder B3.",
        text: "Einsatzstichwort aus Buchstabe und Ziffer. Der Buchstabe ist die Einsatzart: <b>H</b> Hilfeleistung, <b>B</b> Brand, <b>W</b> Wasser, <b>G</b> Gefahrstoff, <b>S</b> Sonderlage. Die Ziffer ist die Alarmstufe (1–4). Aus <i>H2.03</i> wird Stichwort H2, Stufe 03; eine Brandsicherheitswache wird als S1 / 00 geführt.",
      },
      stufe: {
        titel: "Stufe",
        kurz: "Unterstichwort nach dem Punkt, z. B. 07 aus B2.07.",
        text: "Zweistellige Ergänzung nach dem Punkt des Einsatzstichworts (<i>B2.07</i> → 07). Sie unterscheidet Einsätze innerhalb eines Stichworts; B2.07 (Brandmeldeanlage) und S1.00 (Brandsicherheitswache) werden in der Auswertung gesondert gezählt. Nicht verwechseln mit der Alarmstufe – die steckt in der Ziffer des Stichworts.",
      },
      einsatz: {
        titel: "Einsatz",
        kurz: "Kurzbeschreibung: Meldebild / Objekt oder Straße.",
        text: "Kurzbeschreibung im Format <i>Meldebild / Objekt</i>, ersatzweise <i>Meldebild / Straße</i>. Wird in der Einsatzliste angezeigt und von der Suche durchsucht.",
      },
      ort: {
        titel: "Ort",
        kurz: "Einsatzort; bestimmt Einsatzgebiet und Bedarfsplan.",
        text: "Ortsteil oder Ort des Einsatzes. Bekannte Orte (Rheinbrohl, Arienheller, Hammerstein, Ariendorf, Bad Hönningen, Leutesdorf) werden vorgeschlagen. Nur Einsätze in Rheinbrohl, Hammerstein und Arienheller zählen für den Feuerwehrbedarfsplan – bitte den Ort daher genau so schreiben.",
      },
      ehf: {
        titel: "EHF",
        kurz: "Einheitsführer, Schreibweise „V. Nachname“.",
        text: "Einheitsführer des Einsatzes in der Schreibweise <i>V. Nachname</i>. Übernommen wird die Person mit der Funktion „Einheitsführer“. Fehlt sie im Bericht, wird der Einsatzleiter eingetragen und ein Prüfhinweis erzeugt – ist auch der nicht in der Anwesenheit, bleibt das Feld leer und ist rot markiert.",
      },
    },
  },
  {
    titel: "Kennzahlen je Einsatz",
    einleitung: "Werden aus den Fahrzeugzeiten berechnet und sind nicht direkt änderbar – korrigieren Sie bei Bedarf Beginn oder Ende.",
    eintraege: {
      azeit: {
        titel: "Azeit (Ausrückezeit)",
        kurz: "Minuten von der Alarmierung bis zum Ausrücken des schnellsten Fahrzeugs.",
        text: "Minuten vom Einsatzbeginn bis zum Ausrücken (Status 3) des schnellsten eigenen Fahrzeugs. In der Fahrzeugtabelle steht die Azeit je Fahrzeug.",
      },
      ezeit: {
        titel: "Ezeit (Eintreffzeit)",
        kurz: "Minuten von der Alarmierung bis zum Eintreffen des ersten Fahrzeugs.",
        text: "Minuten vom Einsatzbeginn bis zum Eintreffen (Status 4) des ersten eigenen Fahrzeugs an der Einsatzstelle. Rot markiert, wenn sie über 8 Minuten liegt. Ohne Eintreffzeit wird der Einsatz im Bedarfsplan nicht berücksichtigt.",
      },
      erreicht: {
        titel: "8 Min. erreicht",
        kurz: "Ja, wenn das erste Fahrzeug innerhalb der Zeitgrenze eingetroffen ist.",
        text: "„Ja“, wenn die Ezeit höchstens der Zeitgrenze entspricht (8 Minuten; in der Auswertung auf 10 umschaltbar). Grundlage des Erreichungsgrads im Feuerwehrbedarfsplan.",
      },
      staerke_eintreffen: {
        titel: "Stärke bei Eintreffen",
        kurz: "Besatzung der Fahrzeuge, die als erste eingetroffen sind.",
        text: "Summe der Besatzung aller Fahrzeuge, die zum Zeitpunkt der Ezeit eingetroffen sind.",
      },
      staerke_grenze: {
        titel: "Stärke nach 8 Min.",
        kurz: "Zusätzliche Kräfte, die bis zur Zeitgrenze nachgekommen sind.",
        text: "Summe der Besatzung der Fahrzeuge, die nach dem ersten Fahrzeug, aber noch innerhalb der Zeitgrenze (8 bzw. 10 Minuten) eingetroffen sind.",
      },
      staerke_15: {
        titel: "Stärke nach 15 Min.",
        kurz: "Zusätzliche Kräfte zwischen Zeitgrenze und 15 Minuten.",
        text: "Summe der Besatzung der Fahrzeuge, die nach der Zeitgrenze und bis 15 Minuten nach Einsatzbeginn eingetroffen sind.",
      },
      staerke_gesamt: {
        titel: "Gesamtstärke",
        kurz: "Besatzung aller Fahrzeuge plus Personen im Gerätehaus.",
        text: "Besatzung aller eigenen Fahrzeuge plus Personen im Gerätehaus. Im Bedarfsplan wird – wie in der Einsatzübersicht – ohne 01/10 gerechnet.",
      },
      dauer: {
        titel: "Dauer",
        kurz: "Zeit von Beginn bis Ende des Einsatzes.",
        text: "Zeit von Einsatzbeginn bis Einsatzende. Grundlage für Einsatzstunden, Personalstunden und die Stunden je Kamerad.",
      },
      zeitfenster: {
        titel: "Zeitfenster",
        kurz: "Werktag oder Sa/So/Feiertag, Tag (06–18 Uhr) oder Nacht.",
        text: "Einordnung nach Einsatzbeginn: <b>Tag</b> 06:00–18:00 Uhr, sonst <b>Nacht</b>; <b>Sa/So/Feiertag</b> an Wochenenden und gesetzlichen Feiertagen in Rheinland-Pfalz, sonst <b>Werktag</b>. In der Liste als „WE/FT“ gekennzeichnet.",
      },
      fahrzeuge: {
        titel: "Fahrzeuge",
        kurz: "Stärke sowie Ausrücke- und Eintreffzeit je Fahrzeug.",
        text: "Je Fahrzeug (02/45, 02/24, 02/71, 02/19, 01/10 – in der Reihenfolge der Einsatzübersicht): Stärke, Uhrzeit Ausrücken und Eintreffen sowie die daraus berechneten Minuten. 01/23 wird bei Rheinbrohler Besatzung als Ersatz im Block 02/45 eingetragen. Grau = nicht im Einsatz.",
      },
      hinweise: {
        titel: "Prüfhinweise",
        kurz: "Auffälligkeiten beim Einlesen – bitte kontrollieren.",
        text: "Automatisch erzeugte Hinweise, z. B. fehlender Einheitsführer, nicht ermittelbarer Beginn/Ende oder Fahrzeuge, die keinem Block der Einsatzübersicht zugeordnet sind. Hinweise verhindern das Übernehmen nicht.",
      },
      anwesenheit: {
        titel: "Anwesenheit",
        kurz: "Alle Personen laut Anwesenheitsliste des Berichts.",
        text: "Personen aus der Anwesenheitsliste des Berichts, mit Fahrzeug und Funktion. Namen werden mit den bekannten Kameraden abgeglichen; unbekannte Namen sind markiert und werden beim Übernehmen als neue Kameraden angelegt.",
      },
    },
  },
  {
    titel: "Auswertung",
    einleitung: "Alle Werte beziehen sich auf das oben rechts gewählte Jahr. Jedes Diagramm lässt sich über „Tabelle“ als Zahlentabelle anzeigen.",
    eintraege: {
      pro_woche: {
        titel: "Einsätze / Woche",
        kurz: "Einsätze geteilt durch die Kalenderwochen des Jahres.",
        text: "Anzahl Einsätze geteilt durch die Kalenderwochen – im laufenden Jahr bis zur aktuellen KW, sonst über das ganze Jahr.",
      },
      einsatzstunden: {
        titel: "Einsatzstunden",
        kurz: "Summe der Dauer aller Einsätze.",
        text: "Summe der Einsatzdauer aller Einsätze des Jahres (unabhängig von der Anzahl der Einsatzkräfte).",
      },
      personalstunden: {
        titel: "Personalstunden",
        kurz: "Einsatzdauer × anwesende Kameraden, über alle Einsätze.",
        text: "Für jeden Einsatz Dauer × Anzahl der Anwesenden, aufsummiert über das Jahr. Darunter steht die durchschnittliche Zahl Anwesender je Einsatz.",
      },
      bedarfsplan: {
        titel: "Feuerwehrbedarfsplan Pos. 8.4",
        kurz: "Anteil der Einsätze, bei denen das erste Fahrzeug rechtzeitig eintraf.",
        text: "Berücksichtigt werden Einsätze ab Alarmstufe 2 (Stichwort x2–x4) in Rheinbrohl, Hammerstein und Arienheller mit Eintreffzeit. Erreichungsgrad = Anteil der Einsätze, bei denen das erste Fahrzeug innerhalb der Zeitgrenze (8 oder 10 Minuten, umschaltbar) eingetroffen ist – getrennt nach den vier Zeitfenstern Werktag/Wochenende × Tag/Nacht. Die Stärken sind Mittelwerte je Einsatz.",
      },
      alarmstufe: {
        titel: "Alarmstufen",
        kurz: "Ziffer im Stichwort, z. B. H2 → Stufe 2.",
        text: "Die Alarmstufe ist die Ziffer im Einsatzstichwort (H<b>2</b>, B<b>3</b> …). Sie ist unabhängig von der zweistelligen „Stufe“ nach dem Punkt.",
      },
      gebiet: {
        titel: "Einsatzgebiet",
        kurz: "Einsätze je Ort anhand des Anfangs des Ortsnamens.",
        text: "Zuordnung nach dem Anfang des Ortsnamens (z. B. „Rheinbrohl-…“ → Rheinbrohl). Orte außerhalb der bekannten Liste erscheinen als „sonstige“.",
      },
    },
  },
  {
    titel: "Kameraden",
    einleitung: "Anwesenheit je Kamerad im gewählten Jahr. Spaltenköpfe anklicken zum Sortieren.",
    eintraege: {
      beteiligung: {
        titel: "Beteiligung",
        kurz: "Anteil der Einsätze des Jahres, bei denen der Kamerad anwesend war.",
        text: "Einsätze des Kameraden geteilt durch alle Einsätze des Jahres.",
      },
      stunden: {
        titel: "Stunden",
        kurz: "Summe der Einsatzdauer aller Einsätze mit Teilnahme.",
        text: "Summe der Einsatzdauer aller Einsätze, bei denen der Kamerad in der Anwesenheit steht.",
      },
      nachts_we: {
        titel: "nachts / Sa/So/FT",
        kurz: "Einsätze zwischen 18 und 6 Uhr bzw. an Wochenenden und Feiertagen.",
        text: "Anzahl der Einsätze mit Beginn in der Nacht (18:00–06:00 Uhr) bzw. an Samstagen, Sonntagen und Feiertagen.",
      },
    },
  },
];

const HILFE = Object.fromEntries(HILFE_ABSCHNITTE.flatMap((a) => Object.entries(a.eintraege)));

/** Kleines ?-Symbol: Tooltip mit Kurztext, Klick öffnet das Hilfefenster an der Stelle. */
function hilfe(schluessel) {
  const h = HILFE[schluessel];
  if (!h) return "";
  return `<button type="button" class="hilfe-knopf" data-hilfe="${schluessel}" data-tip="${esc(h.kurz)}" aria-label="Hilfe: ${esc(h.titel)}">?</button>`;
}

function hilfeInhalt() {
  return HILFE_ABSCHNITTE.map((a) => `<section class="hilfe-abschnitt">
    <h3>${a.titel}</h3>${a.einleitung ? `<p class="gedaempft">${a.einleitung}</p>` : ""}
    <dl class="hilfe-liste">${Object.entries(a.eintraege).map(([k, e]) =>
      `<div id="hilfe-${k}"><dt>${e.titel}</dt><dd>${e.text}</dd></div>`).join("")}</dl>
  </section>`).join("");
}

function hilfeOeffnen(schluessel) {
  const d = $("#hilfe-dialog");
  const inhalt = $("#hilfe-inhalt");
  if (!inhalt.innerHTML) inhalt.innerHTML = hilfeInhalt();
  for (const el of inhalt.querySelectorAll(".markiert")) el.classList.remove("markiert");
  if (!d.open) d.showModal();
  const ziel = schluessel && $(`#hilfe-${schluessel}`);
  if (ziel) {
    ziel.classList.add("markiert");
    ziel.scrollIntoView({ block: "center" });
  } else {
    inhalt.scrollTop = 0;
  }
}

document.addEventListener("click", (e) => {
  const k = e.target.closest("[data-hilfe]");
  if (!k) return;
  e.preventDefault();          // ?-Symbol steht teils in <label>/<th> – dort nichts anderes auslösen
  e.stopPropagation();
  hilfeOeffnen(k.dataset.hilfe);
}, true);

// Tooltips der fest in index.html stehenden ?-Symbole aus derselben Quelle
for (const k of document.querySelectorAll("[data-hilfe]")) {
  if (HILFE[k.dataset.hilfe]) k.dataset.tip = HILFE[k.dataset.hilfe].kurz;
}
