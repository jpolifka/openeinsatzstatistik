"use strict";

// Online-Hilfe: eine Quelle für die ?-Symbole an Feldern/Kennzahlen und das Hilfefenster.
// Schlüssel = Feld- bzw. Kennzahlname der API. short = Tooltip, text = Erklärung im Hilfefenster (HTML erlaubt).
// Texte mit Werten der Wehr (Fahrzeuge, Orte, Zeitgrenzen) sind Funktionen: config aus app.js gibt es erst zur Laufzeit.
const helpList = (values) => values.length ? values.map(esc).join(", ") : "–";
const helpLimit = () => config.default_limit;
const helpLimits = () => config.limits.join(" oder ");
const helpDay = () => config.day_hours.map((h) => `${String(h).padStart(2, "0")}:00`);
const helpValue = (v) => typeof v === "function" ? v() : v;

const HELP_SECTIONS = [
  {
    id: "sec_capture",
    title: "Einsatz erfassen",
    intro: "Diese Felder stehen in der Vorschau und unter „Einsätze → Bearbeiten“. Sie werden aus dem Einsatzbericht des BKS-Portals (PDF oder Excel-Export) vorbelegt und können vor dem Übernehmen korrigiert werden.",
    entries: {
      number: {
        title: "Nr.",
        short: "Laufende Einsatznummer im Jahr (z. B. 54 für 54-26).",
        text: "Laufende Einsatznummer innerhalb des Jahres, wie im Dateinamen des Berichts (<i>54-26_B2_…pdf</i> → 54). Ob ein Einsatz schon erfasst ist, erkennt die App an der Nummer des Berichts im BKS-Portal, bei älteren Einsätzen an Nr. und Jahr. Ein erneut eingelesener Bericht aktualisiert dann den erfassten Einsatz. Fehlt die Nr. im Bericht, vergibt die App die nächste freie. Ist in der Verwaltung „nach Datum durchnummerieren“ eingestellt, vergibt die App alle Nummern selbst nach dem Einsatzbeginn – ein später eingelesener Einsatz rückt an seine Stelle.",
      },
      started_at: {
        title: "Beginn",
        short: () => `Früheste Alarmierung eines eigenen Fahrzeugs (${esc(config.own_prefix)}..).`,
        text: () => `Einsatzbeginn = frühester Alarmierungszeitpunkt der eigenen Fahrzeuge (Funkrufname ${esc(config.own_prefix)}..). Gibt es keine, zählt die erste Alarmierung im Bericht. Alle Minutenwerte (Azeit, Ezeit) werden ab diesem Zeitpunkt gerechnet. Der Beginn bestimmt außerdem Jahr, Monat, Wochentag und das Zeitfenster Tag/Nacht.`,
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
        short: "Einsatzart + Alarmstufe, z. B. H2 – oder Suchbegriff wie „Verkehrsunfall“ eingeben.",
        text: "Einsatzstichwort aus Buchstabe und Ziffer. Der Buchstabe ist die Einsatzart: <b>H</b> Hilfeleistung, <b>B</b> Brand, <b>W</b> Wasser, <b>G</b> Gefahrstoff, <b>S</b> Sonderlage. Die Ziffer ist die Alarmstufe (1–4). Aus <i>H2.03</i> wird Stichwort H2, Stufe 03; eine Brandsicherheitswache wird als S1 / 00 geführt. Ins Feld kann auch ein Suchbegriff geschrieben werden (z. B. <i>Verkehrsunfall</i>): Die Liste zeigt passende Stichworte aus der Alarm- und Ausrückeordnung (H2.03, H3.01, H3.04, H3.05). Gesucht wird auch in den Meldebildern der AAO, z. B. findet <i>Türöffnung</i> H2.01 und <i>Wasserrohrbruch</i> H1.09, ein Klick oder Enter übernimmt Stichwort und Stufe. Wer das ganze Stichwort ins Feld schreibt – mit oder ohne Punkt, also <i>B2.07</i> oder <i>B207</i> –, bekommt es automatisch in Stichwort und Stufe aufgeteilt.",
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
        text: () => `Ortsteil oder Ort des Einsatzes. Bekannte Orte (${helpList(config.places)}) werden vorgeschlagen. Nur Einsätze in ${helpList(config.plan_places)} zählen für den Feuerwehrbedarfsplan – bitte den Ort daher genau so schreiben.`,
      },
      bks_url: {
        title: "BKS-Portal",
        short: "Bericht im BKS-Portal öffnen.",
        text: "Jeder Bericht im BKS-Portal hat eine eigene Nummer (Haupt- bzw. Nebenbericht einer Einheit). Alle Berichte eines Einsatzes verweisen auf denselben <i>Stammdatensatz</i>; darüber erkennt die App gemeinsame Einsätze mehrerer Wehren – auch selbst angelegte ohne Einsatznummer der Leitstelle, z. B. Brandsicherheitswachen. Der Link öffnet den Bericht im Portal (Anmeldung dort nötig).",
      },
      dispatch_number: {
        title: "Leitstellen-Nr.",
        short: "Gemeinsame Einsatznummer der Leitstelle für beteiligte Wehren.",
        text: "Die Einsatznummer der Leitstelle verbindet Berichte desselben Einsatzes über mehrere Wehren. Sie ist nicht die laufende Nummer der Wehr und nicht die BKS-Bericht-ID. Leer bedeutet unbekannt; bei Korrekturen den Originalbericht prüfen.",
      },
      unit_leader: {
        title: "EHF",
        short: "Einheitsführer, Schreibweise „V. Nachname“.",
        text: "Einheitsführer des Einsatzes in der Schreibweise <i>V. Nachname</i>. Übernommen wird die Person mit der Funktion „Einheitsführer“. Fehlt sie im Bericht, wird der Einsatzleiter eingetragen und ein Prüfhinweis erzeugt – ist auch der nicht in der Anwesenheit, bleibt das Feld leer und ist rot markiert. Ein Klick auf einen Namen in der Anwesenheit trägt diese Person als EHF ein.",
      },
    },
  },
  {
    id: "sec_metrics",
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
        text: () => `Minuten vom Einsatzbeginn bis zum Eintreffen (Status 4) des ersten eigenen Fahrzeugs an der Einsatzstelle. Rot markiert, wenn sie über ${helpLimit()} Minuten liegt. Ohne Eintreffzeit wird der Einsatz im Bedarfsplan nicht berücksichtigt.`,
      },
      on_time: {
        title: () => `${helpLimit()} Min. erreicht`,
        short: "Ja, wenn das erste Fahrzeug innerhalb der Zeitgrenze eingetroffen ist.",
        text: () => `„Ja“, wenn die Ezeit höchstens der Zeitgrenze entspricht (${helpLimit()} Minuten; in der Auswertung umschaltbar: ${helpLimits()}). Grundlage des Erreichungsgrads im Feuerwehrbedarfsplan.`,
      },
      crew_on_arrival: {
        title: "Stärke bei Eintreffen",
        short: "Besatzung der Fahrzeuge, die als erste eingetroffen sind.",
        text: "Summe der Besatzung aller Fahrzeuge, die zum Zeitpunkt der Ezeit eingetroffen sind.",
      },
      crew_within_limit: {
        title: () => `Zusätzliche Kräfte bis ${helpLimit()} Min.`,
        short: "Zusätzliche Kräfte, die bis zur Zeitgrenze nachgekommen sind.",
        text: () => `Summe der Besatzung der Fahrzeuge, die nach dem ersten Fahrzeug, aber noch innerhalb der Zeitgrenze (${helpLimits()} Minuten) eingetroffen sind.`,
      },
      crew_within_second: {
        title: () => `Zusätzliche Kräfte zwischen ${helpLimit()} und ${config.second_limit} Min.`,
        short: () => `Zusätzliche Kräfte zwischen Zeitgrenze und ${config.second_limit} Minuten.`,
        text: () => `Summe der Besatzung der Fahrzeuge, die nach der Zeitgrenze und bis ${config.second_limit} Minuten nach Einsatzbeginn eingetroffen sind.`,
      },
      crew_total: {
        title: "Gesamtstärke",
        short: "Besatzung aller Fahrzeuge plus Personen im Gerätehaus.",
        text: () => `Besatzung aller eigenen Fahrzeuge plus Personen im Gerätehaus.${config.plan_excluded_vehicles.length ? ` Im Bedarfsplan wird – wie in der Einsatzübersicht – ohne ${helpList(config.plan_excluded_vehicles)} gerechnet.` : ""}`,
      },
      duration: {
        title: "Dauer",
        short: "Zeit von Beginn bis Ende des Einsatzes.",
        text: "Zeit von Einsatzbeginn bis Einsatzende. Grundlage für Einsatzstunden, Personalstunden und die Stunden je Kamerad.",
      },
      time_window: {
        title: "Zeitfenster",
        short: "Werktag oder Sa/So/Feiertag, Tag (06–18 Uhr) oder Nacht.",
        text: () => `Einordnung nach Einsatzbeginn: <b>Tag</b> ${helpDay().join("–")} Uhr, sonst <b>Nacht</b>; <b>Sa/So/Feiertag</b> an Wochenenden und gesetzlichen Feiertagen in Rheinland-Pfalz, sonst <b>Werktag</b>. In der Liste als „WE/FT“ gekennzeichnet.`,
      },
      vehicles: {
        title: "Fahrzeuge",
        short: "Stärke sowie Ausrücke- und Eintreffzeit je Fahrzeug.",
        text: () => `Je Fahrzeug (${helpList(config.vehicles)} – in der Reihenfolge der Einsatzübersicht): Stärke, Uhrzeit Ausrücken und Eintreffen sowie die daraus berechneten Minuten.${Object.entries(config.substitutes).map(([sub, block]) => ` ${esc(sub)} wird bei eigener Besatzung als Ersatz im Block ${esc(block)} eingetragen.`).join("")} Grau = nicht im Einsatz.`,
      },
      warnings: {
        title: "Prüfhinweise",
        short: "Auffälligkeiten beim Einlesen – bitte kontrollieren.",
        text: "Beim Einlesen erzeugte Hinweise, z. B. fehlender Einheitsführer oder nicht ermittelbarer Beginn/Ende. Jeder neue oder geänderte Bericht muss ausdrücklich bestätigt werden, auch ohne Hinweise. Stammdatensätze und Weiterleitungen haben eigene Bestätigungsaktionen. Schließen verwirft offene Vorschauen, bereits bestätigte Berichte bleiben gespeichert. In den Einsatzdetails steht der aktuelle Datenstand getrennt von den historischen Importhinweisen; Korrekturen entfernen diese Historie nicht.",
      },
      attendance: {
        title: "Anwesenheit",
        short: "Alle Personen laut Anwesenheitsliste des Berichts.",
        text: "Personen aus der Anwesenheitsliste des Berichts, mit Fahrzeug und Funktion. Namen werden mit den bekannten Kameraden abgeglichen; unbekannte Namen sind markiert und werden beim Übernehmen als neue Kameraden angelegt. Beim Bearbeiten und in der Vorschau trägt ein Klick auf einen Namen die Person als EHF ein; der EHF ist dunkelrot hervorgehoben.",
      },
    },
  },
  {
    id: "sec_evaluation",
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
        text: () => `Berücksichtigt werden Einsätze ab Alarmstufe ${config.plan_min_level} (Stichwort x${config.plan_min_level}–x4) in ${helpList(config.plan_places)} mit Eintreffzeit. Erreichungsgrad = Anteil der Einsätze, bei denen das erste Fahrzeug innerhalb der Zeitgrenze (${helpLimits()} Minuten) eingetroffen ist – getrennt nach den vier Zeitfenstern Werktag/Wochenende × Tag/Nacht. Die Stärken sind Mittelwerte je Einsatz. Den Bedarfsplan sehen zunächst nur Wehrführer und Wehrleiter; mit „für alle freigegeben“ (oder in der Verwaltung unter „Orte & Bedarfsplan“) sehen ihn alle Rollen der Wehr.`,
      },
      alarm_level: {
        title: "Alarmstufen",
        short: "Ziffer im Stichwort, z. B. H2 → Stufe 2.",
        text: "Die Alarmstufe ist die Ziffer im Einsatzstichwort (H<b>2</b>, B<b>3</b> …). Sie ist unabhängig von der zweistelligen „Stufe“ nach dem Punkt.",
      },
      area: {
        title: "Einsatzgebiet",
        short: "Einsätze je Ort anhand des Anfangs des Ortsnamens.",
        text: () => `Zuordnung nach dem Ortsnamen, mit dem der Einsatzort beginnt${config.places.length ? ` (z. B. „${esc(config.places[0])}-…“ → ${esc(config.places[0])})` : ""}. Orte außerhalb der bekannten Liste erscheinen als „sonstige“.`,
      },
      participations: {
        title: "Einsätze und Beteiligungen (alle Wehren)",
        short: "Große Zahl: Einsätze ohne Doppelte. Beteiligungen: Summe der Einsätze aller Wehren.",
        text: "In der Gesamtansicht einer Verbandsgemeinde zählt ein Einsatz, an dem mehrere Wehren beteiligt waren, bei jeder Wehr (Beteiligungen). Die große Zahl zählt ihn nur einmal: Einsätze mit demselben Stammdatensatz im BKS-Portal oder derselben Einsatznummer der Leitstelle gelten als ein Einsatz. Einsätze ohne beides (z. B. aus der früheren Excel-Übersicht) zählen einzeln. Alle übrigen Kennzahlen und Diagramme summieren die Beteiligungen; der Bedarfsplan wertet jede Wehr mit ihren eigenen Orten aus. Über die Schaltflächen oben lässt sich die Auswertung auf einzelne Wehren einschränken.",
      },
    },
  },
  {
    id: "sec_vg",
    title: "Einsätze mehrerer Wehren",
    intro: "Im BKS-Portal hat ein Einsatz einen Stammdatensatz (alle Fahrzeuge mit den Zeiten der Leitstelle) und je beteiligter Einheit einen Haupt- oder Nebenbericht. Die Wehren korrigieren in ihren Berichten oft Stärke und Zeiten – daraus entstehen Abweichungen.",
    entries: {
      notices: {
        title: "Hinweise",
        short: "Was andere für eure Wehr eingelesen haben, Abweichungen und fehlende Berichte.",
        text: "Hinweise entstehen, wenn jemand ohne eigene Rolle in der Wehr (z. B. der Wehrleiter) einen Einsatz der Wehr einliest, wenn der Bericht einer anderen Wehr für eure Fahrzeuge andere Werte nennt, wenn laut Stammdatensatz oder fremdem Bericht eure Fahrzeuge ausgerückt sind, aber noch kein eigener Bericht erfasst ist, und wenn eine andere Wehr euren Bericht hochgeladen hat – er liegt dann zur Übernahme bereit („Übernehmen“). Erledigt markieren kann, wer Einsätze der Wehr bearbeiten darf.",
      },
      records: {
        title: "Prüfprotokoll",
        short: "Abgleich je Einsatz über alle Wehren der VG (Recht „Prüfprotokoll und Kostenersatz“, z. B. Wehrleiter).",
        text: "Für jeden Einsatz mit Stammdatensatz vergleicht das Protokoll die Zeiten der Leitstelle mit den Berichten der Wehren. „Als geprüft markieren“ gilt für den jetzigen Stand: Kommt ein neuer Befund hinzu (z. B. ein geänderter Bericht), ist der Einsatz wieder offen. „Drucken / PDF“ druckt die angezeigten Einsätze mit ihren Befunden.",
      },
      fees: {
        title: "Kostenersatz",
        short: "Kostenaufstellung nach der Gebührenordnung der VG (Recht „Prüfprotokoll und Kostenersatz“, z. B. Wehrleiter).",
        text: "Im Prüfprotokoll rechnet „Kostenersatz berechnen“ einen Einsatz über alle beteiligten Wehren nach der Gebührenordnung (Verwaltung → Gebührenordnung): Fahrzeuge je Stunde vom Ausrücken bis zum Einsatzende des Fahrzeugs, Einsatzkräfte je Person und Stunde von der Alarmierung bis zum Einsatzende (Brandsicherheitswache mit eigenem Satz). Angefangene Stunden werden bis 30 Minuten als halbe, darüber als volle Stunde abgerechnet. Bei einem Fehlalarm einer Brandmeldeanlage gilt höchstens die Pauschale. Auslagen bekommen den Verwaltungszuschlag, Umsatzsteuer nur, wenn sie anfällt. Den Fahrzeugtyp liefert die Bezeichnung in der Fahrzeugliste (z. B. „HLF 20“). Es wird nichts gespeichert.",
      },
      findings: {
        title: "Befunde",
        short: "Abweichungen, fehlende und unbearbeitete Berichte.",
        text: "<b>Abweichung</b>: Stärke, Alarmierung, Ausrücken, Eintreffen oder Ende eines Fahrzeugs weichen im Bericht der Wehr vom Stammdatensatz ab (minutengenau), oder ein ausgerücktes Fahrzeug fehlt im Bericht. <b>Stichwort</b>: anderes Stichwort als im Stammdatensatz. <b>Bericht fehlt</b>: Fahrzeuge der Wehr sind laut Stammdatensatz ausgerückt, die Wehr hat aber keinen Bericht erfasst. <b>unbearbeitet</b>: Bericht ohne Anwesenheit. <b>ohne Nr.</b>: Bericht ohne Einsatzbericht-Nr.",
      },
    },
  },
  {
    id: "sec_members",
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
        short: () => `Einsätze zwischen ${config.day_hours[1]} und ${config.day_hours[0]} Uhr bzw. an Wochenenden und Feiertagen.`,
        text: () => `Anzahl der Einsätze mit Beginn in der Nacht (${helpDay().reverse().join("–")} Uhr) bzw. an Samstagen, Sonntagen und Feiertagen.`,
      },
    },
  },
  {
    id: "sec_shortcuts",
    title: "Tastenkürzel und Bedienhilfen",
    intro: "Die Tasten wirken, solange kein Eingabefeld und kein Dialog aktiv ist.",
    entries: {
      shortcuts: {
        title: "Tastenkürzel",
        short: "/ Suche · i Bericht einlesen · j/k nächster/vorheriger Einsatz · e bearbeiten · Esc schließen · ? Hilfe",
        text: "<kbd>/</kbd> Suche in der Einsatzliste · <kbd>i</kbd> Bericht einlesen · <kbd>j</kbd> / <kbd>k</kbd> nächsten bzw. vorherigen Einsatz der Liste aufklappen · <kbd>e</kbd> geöffneten Einsatz bearbeiten · <kbd>Esc</kbd> Bearbeiten abbrechen bzw. Details zuklappen · <kbd>Strg</kbd>+<kbd>Z</kbd> (Mac: <kbd>⌘</kbd>+<kbd>Z</kbd>) gerade gelöschten Einsatz zurückholen · <kbd>?</kbd> diese Hilfe.",
      },
      list_filters: {
        title: "Filter und Links",
        short: "Filter, Suche und Sortierung stehen in der Adresse – Link kopieren und weitergeben.",
        text: "Kategorie, Suche, Sortierung und der Filter <b>Prüfhinweise</b> (nur Einsätze mit aktuellen Prüfhinweisen, z. B. ohne Eintreffzeit oder Anwesenheit) stehen in der Adresse der Seite: Sie bleiben beim Neuladen erhalten, und ein kopierter Link zeigt anderen dieselbe Liste. In der <b>Auswertung</b> öffnet ein Klick auf einen Balken, eine Säule oder die Zahlen im Bedarfsplan die passenden Einsätze; der Filter steht dann als Chip über der Liste und lässt sich mit × entfernen. Spaltenköpfe mit ▾/▴ sortieren die Liste. Kategorie, Sortierung und Tabellen-/Diagrammansicht merkt sich der Browser.",
      },
      undo_delete: {
        title: "Löschen rückgängig machen",
        short: "Nach dem Löschen bleibt ein Einsatz einige Sekunden wiederherstellbar.",
        text: "Ein gelöschter Einsatz verschwindet sofort aus der Liste; endgültig gelöscht wird er erst nach einigen Sekunden. Bis dahin holt <b>Rückgängig</b> in der Meldung unten (oder <kbd>Strg</kbd>+<kbd>Z</kbd>) ihn zurück. Wer die Seite vorher schließt, löscht sofort. Ungespeicherte Änderungen an einem Einsatz gehen nicht verloren: Beim Wechsel von Reiter, Jahr oder Wehr und beim Schließen fragt die App nach.",
      },
      drop_files: {
        title: "Berichte aufs Fenster ziehen",
        short: "PDF- oder Excel-Berichte einfach ins Browserfenster ziehen.",
        text: "Berichte (PDF, Excel-Export oder ZIP) lassen sich auf jede Stelle des Fensters ziehen; der Import öffnet sich und liest sie sofort ein.",
      },
    },
  },
  {
    id: "sec_admin",
    title: "Verwaltung",
    intro: "Je Bereich mit dem passenden Recht (siehe Rechte), im Startbestand für Wehrführer, Wehrleiter und Superadmins. Änderungen gelten sofort für alle Benutzer der Wehr.",
    entries: {
      admin_colors: {
        title: "Farben",
        short: "Hauptfarbe (und optional eine dunkle Variante) der Wehr.",
        text: "Farbe über den Farbwähler, als Hex-Wert (#RRGGBB) oder als Rot/Grün/Blau-Anteile (0–255) einstellen – die drei Eingaben bleiben gleich. Aus der Hauptfarbe leitet die App alle anderen Töne ab (Flächen, Tabellenköpfe, Diagramme Tag/Nacht) und dunkelt sie bei Bedarf so weit ab, dass Schrift und Diagramme lesbar bleiben. Ist die Hauptfarbe selbst zu hell für weiße Schrift (Kontrast unter 4,5:1), lässt sie sich nicht speichern. Ohne eigene Farbe gilt das Standardrot. Die Gesamtansicht einer VG und die Anmeldung sind immer neutral gestaltet.",
      },
      admin_logos: {
        title: "Logos",
        short: "Logo für Kopfzeile, Fußzeile und Browser-Tab.",
        text: "<b>Logo hell</b> steht auf der farbigen Kopfzeile (am besten weiß auf transparent), <b>Logo dunkel</b> in der Fußzeile, das <b>Symbol</b> im Browser-Tab. Erlaubt sind PNG, JPEG und WebP bis 512 KB; SVG geht aus Sicherheitsgründen nicht. Ohne eigenes Bild erscheint das neutrale Signet.",
      },
      admin_fleet: {
        title: "Fahrzeuge",
        short: "Fahrzeugblöcke der Einsatzübersicht mit Dienstzeitraum.",
        text: "Jedes Fahrzeug ist ein Block der Einsatzübersicht (Stärke, Ausrücken, Eintreffen). Der <b>Funkrufname</b> wird genau so eingetragen, wie er im BKS-Bericht steht, z. B. „FL NR#.ABC 02/45-01“ oder „RP WW 01/23-06“ für ein Fahrzeug des Landes am Standort. Darüber ordnet die App die Fahrzeuge eines Berichts zu; zur Auswahl stehen die Namen aus bisher eingelesenen Berichten der VG. Darunter steht die Auflösung nach dem Funkrufnamenverzeichnis RLP (Kennung, Standort, Kennzahl = Fahrzeugart, laufende Nummer) und der Block, unter dem das Fahrzeug in Einsätzen und im Excel-Export erscheint (z. B. 02/45). Der <b>Fahrzeugtyp</b> ist die Grundlage für den Kostenersatz und muss so heißen wie in der Gebührenordnung (z. B. HLF 20). Zur Auswahl stehen die Typen, die die Kennzahl laut Verzeichnis haben kann, und die Typen der Gebührenordnung. Vorbelegt wird er, wenn nur einer davon in Frage kommt; sonst steht der Hinweis „laut Kennzahl: …“ darunter. Jedes Fahrzeug kann nur einmal in der Liste stehen – für einen alten Eintrag wie 02/45 den Funkrufnamen dort eintragen statt ihn neu hinzuzufügen. <b>Im Dienst ab / außer Dienst ab</b> begrenzen, wann ein Fahrzeug beim Einlesen zugeordnet und als Spalte im Excel-Export des Jahres angezeigt wird – ein ausgemustertes Fahrzeug muss so nicht gelöscht werden, alte Einsätze bleiben vollständig. <b>Ersetzt durch</b> hält fest, welches Fahrzeug nachfolgt. Ohne Haken bei <b>Bedarfsplan</b> zählt die Besatzung nicht zur Gesamtstärke des Bedarfsplans. Eigene Fahrzeuge, die in einem Bericht vorkommen, aber noch fehlen, werden beim Übernehmen automatisch angefügt.",
      },
      admin_vg_vehicles: {
        title: "Fahrzeuge der VG",
        short: "Alle Fahrzeuge aller Wehren der VG in einer Tabelle.",
        text: "Bei gewählter Wehrleitung stehen hier die Fahrzeuglisten aller Wehren der VG untereinander, mit denselben Spalten wie bei einer Wehr (Funkrufname, Fahrzeugtyp, Dienstzeitraum, Nachfolger, Bedarfsplan, Reihenfolge, Ersatzfahrzeuge). Über die Spalte <b>Wehr</b> wechselt ein Fahrzeug die Wehr – nur deren Berichte ordnen es als eigenes Fahrzeug zu (Einsatzbeginn, Kostenersatz). Die bisherigen Einsätze mit seinen Daten bleiben bei der alten Wehr unverändert; dort erscheint es nur nicht mehr als Spalte. Darunter stehen die Funkrufnamen aus eingelesenen Berichten, die noch keiner Wehr gehören (weitere wie Rettungsdienst oder Fahrzeuge des Landes aufklappbar). Gespeichert wird alles mit einem Klick; hat sich eine Liste inzwischen geändert (z. B. durch einen Import), bitte neu laden.",
      },
      admin_vg_defaults: {
        title: "Vorgaben der VG",
        short: "Einstellungen, die für alle Wehren der VG gelten.",
        text: "Bei gewählter Wehrleitung legen <b>Allgemein</b>, <b>BKS-Kennung</b> und <b>Orte & Bedarfsplan</b> die Vorgaben für alle Wehren der VG fest: Farben, Kennung im BKS-Bericht, FEZ, Nummerierung, Orte, Alarmstufe, Zeitgrenzen und Tagesstunden. Je Wehr kommen ihr Standort und ihr Ausrückebereich dazu. Eine neue Wehr übernimmt alle Vorgaben. Eine Wehr kann bei sich abweichen – bei gewählter Wehr steht an jedem Wert „von der VG“ oder „abweichend von der VG“ mit „VG-Wert übernehmen“. Abweichungen sind in der Wehrleitung unter dem jeweiligen Wert aufgeführt; ändert die VG ihre Vorgabe auf denselben Wert, entfällt die Abweichung.",
      },
      admin_bks: {
        title: "BKS-Kennung",
        short: "Woran die App die eigenen Fahrzeuge und Berichte erkennt.",
        text: "<b>Kennung der VG</b> (gilt für alle Wehren der VG) und <b>Standort</b> der Wehr ergeben die Einheit aus der Kopfzeile des Berichts, z. B. „FW NR#.ABC 02“. Darüber werden Berichte der richtigen Wehr zugeordnet, und daraus ergeben sich die Funkrufnamen: „FL NR#.ABC 02/…“ sind eigene Fahrzeuge (deren früheste Alarmierung ist der Einsatzbeginn), „FL NR#.ABC …“ Fahrzeuge der übrigen Wehren der VG. Fahrzeuge der Fahrzeugliste zählen immer als eigene, auch mit anderem Funkrufnamen (z. B. „RP WW …“). <b>FEZ-Kennung</b>: die Feuerwehreinsatzzentrale, deren Einsatzende mitzählt. Ins <b>Testfeld</b> passt beliebiger Text aus einem Bericht – einzelne Funkrufnamen, Zeilen der Fahrzeugtabelle oder der ganze Bericht; die App zeigt, wie sie jedes gefundene Fahrzeug zuordnet.",
      },
      admin_places: {
        title: "Orte und Bedarfsplan",
        short: "Einsatzgebiete und Ausrückebereich des Feuerwehrbedarfsplans.",
        text: "Ein Einsatz gehört zu dem Ort, mit dessen <b>Namen</b> der Einsatzort beginnt (z. B. „Musterstadt-Nord“ → Musterstadt, Groß-/Kleinschreibung egal). Nur Orte mit Haken bei <b>Bedarfsplan</b> zählen für den Erreichungsgrad. Dazu kommen die Mindest-Alarmstufe, die Zeitgrenzen (mehrere möglich, z. B. 8 und 10 Minuten), die zweite Grenze für „Stärke nach … Min.“ und die Stunden, die als Tag gelten. Orte und Bedarfsplan gibt die Wehrleitung für alle Wehren der VG vor; dort setzt sie auch je Wehr die Haken des Ausrückebereichs.",
      },
      admin_keywords: {
        title: "Stichwortkatalog",
        short: "Stichworte der AAO für die Suche im Feld Stichwort.",
        text: "Den Katalog pflegt die Wehrleitung für alle Wehren der VG; Standard ist die Vorlage der AAO. Bei gewählter Wehr zeigt die Spalte <b>Herkunft</b>, was von der VG kommt. Eine Wehr kann abweichen: Haken <b>gilt hier</b> entfernen (Stichwort gilt in dieser Wehr nicht), Bezeichnung oder Suchbegriffe ändern oder eigene Stichworte ergänzen; ↺ hebt eine Abweichung wieder auf. In der Wehrleitung steht je Stichwort, welche Wehren abweichen. <b>Deaktivierte</b> Stichworte erscheinen nicht mehr in der Suche, alte Einsätze behalten aber ihre Bezeichnung. Ein ganzer Katalog lässt sich als CSV oder Excel (Stichwort, Bezeichnung, Suchbegriffe) einlesen – vorher zeigt die App, was neu ist oder sich ändert.",
      },
      dpa: {
        title: "Auftragsverarbeitung (AVV)",
        short: "Vertrag nach Art. 28 DSGVO zwischen VG und Betreiber.",
        text: "Die Verbandsgemeinde ist als Träger der Feuerwehr für die Daten verantwortlich, der Betreiber der App verarbeitet sie in ihrem Auftrag. Ablauf: Angaben des Auftraggebers ausfüllen → der Vertrag wird aus der Vorlage erzeugt (mit Prüfsumme des Textes) → drucken und unterschreiben lassen → unterschriebenes PDF hochladen und/oder einen Link zur Ablage der VG eintragen → der Betreiber bestätigt. Bis dahin sind die Einsatzdaten der Wehren dieser VG gesperrt. Ausfüllen darf, wer das Recht „Auftragsverarbeitung ausfüllen“ hat (im Startbestand Wehrleiter, Statistik VG und Wehrführer); hochgeladene Dateien werden nie überschrieben, alle Schritte werden protokolliert.",
      },
      admin_users: {
        title: "Benutzer",
        short: "Wer welche Rolle in welcher Wehr bzw. VG hat.",
        text: "Eine Zuordnung verbindet eine E-Mail-Adresse mit einer Rolle in einer Wehr oder in einer VG (dann gilt sie in allen Wehren der VG). Eine Person kann mehrere Rollen haben; ihre Rechte addieren sich. Vergeben und entziehen darf man nur die Rollen, die die eigene Rolle verteilen darf (siehe Rollen → Verteilung), nur im eigenen Bereich und nie bei sich selbst. <b>Rechte</b> zeigt, was eine Person darf und über welche Rolle. Wer keine Zuordnung mehr hat, ist beim nächsten Aufruf abgemeldet.",
      },
      admin_roles: {
        title: "Rollen",
        short: "Welche Rolle welche Rechte hat – als Übersicht.",
        text: "Startbestand: <b>Benutzer</b> (nur Auswertung, ohne Namen) → <b>Erfasser</b> (erbt Benutzer; Einsätze, Anwesenheit und Kameraden, Berichte einlesen, bearbeiten) → <b>Wehrführer</b> (erbt Erfasser; Verwaltung der Wehr, vergibt Erfasser und Benutzer). Für die VG: <b>Statistik VG</b> (z. B. Bürgermeister: Auswertung aller Wehren, ohne Namen) → <b>Wehrleiter</b> (erbt Statistik VG; Einsätze und Verwaltung aller Wehren, Prüfprotokoll, Gebührenordnung, vergibt alle Rollen, pflegt eigene Rollen der VG – sieht aber keine Anwesenheit). Der Wehrleiter kann eigene Rollen für seine VG anlegen, der Superadmin Rollen für alle VGs. Die Tabelle zeigt ● eigene und ○ geerbte Rechte.",
      },
      admin_role_editor: {
        title: "Rolle bearbeiten",
        short: "Bezeichnung, Bereich, Vererbung, Rechte und Verteilung einer Rolle.",
        text: "<b>Bereich</b>: Rolle einer Wehr oder der VG (gilt dann in allen Wehren der VG); er lässt sich nach dem Anlegen nicht ändern. <b>Gilt in</b>: eigene Rolle einer VG oder (nur Superadmin) in allen VGs. <b>Erbt von</b>: die Rolle bekommt alle Rechte und die Verteilung der gewählten Rolle dazu – Änderungen dort wirken mit. Geerbte Rechte lassen sich nicht abwählen; für weniger Rechte von einer kleineren Rolle erben (z. B. Benutzer statt Erfasser). Ein Recht, das ein anderes voraussetzt, setzt dieses mit. <b>Leitplanken</b>: Anwesenheit und Kameraden gibt es nur für Rollen einer Wehr; Gesamtansicht, Prüfprotokoll, Gebühren und Rollenpflege nur für Rollen der VG. Systemrollen ändert nur der Superadmin, Rollen, die man selbst hat (auch über Vererbung), ändert jemand anderes. Löschen lässt sich eine Rolle erst, wenn sie niemand mehr hat und keine Rolle von ihr erbt. Änderungen gelten sofort.",
      },
      admin_role_grants: {
        title: "Verteilung",
        short: "Wer diese Rolle vergeben darf – und was Inhaber dieser Rolle vergeben.",
        text: "Vergeben darf nur, wer das Recht „Rollen vergeben“ hat, und nur die Rollen, die hier freigegeben sind – in der Wehr seiner Rolle bzw. in der VG und ihren Wehren. Beispiel Startbestand: der Wehrführer vergibt Erfasser und Benutzer, der Wehrleiter alle Rollen. Neue Rollen darf zunächst vergeben, wer Rollen der VG pflegt.",
      },
      admin_role_events: {
        title: "Protokoll",
        short: "Wer wann welche Rolle vergeben, entzogen oder geändert hat.",
        text: "Jede Vergabe, jeder Entzug und jede Änderung an Rollen wird mit Zeit und Adresse protokolliert. Das Protokoll lässt sich nur ergänzen, nicht ändern. Sichtbar sind die Einträge der Bereiche, deren Zuordnungen man sehen darf.",
      },
    },
  },
  {
    id: "sec_permissions",
    title: "Rechte",
    intro: "Jede Rolle ist eine Sammlung dieser Rechte. Eine Rolle der VG gilt in allen Wehren der VG; mehrere Rollen addieren sich. Superadmins dürfen alles.",
    entries: {
      perm_stats_view: {
        title: "Auswertung ansehen",
        short: "Kennzahlen, Diagramme und Bedarfsplan (wenn freigegeben) – ohne Namen.",
        text: "Kennzahlen, Diagramme und Bedarfsplan (wenn freigegeben) – ohne Namen.",
      },
      perm_plan_view: {
        title: "Bedarfsplan ohne Freigabe sehen",
        short: "Der Bedarfsplan einer Wehr ist sichtbar, auch solange die Wehr ihn nicht für alle freigegeben hat.",
        text: "Der Bedarfsplan einer Wehr ist sichtbar, auch solange die Wehr ihn nicht für alle freigegeben hat.",
      },
      perm_plan_release: {
        title: "Bedarfsplan freigeben",
        short: "Schalter „Bedarfsplan für alle“ in der Auswertung bzw. unter Orte & Bedarfsplan.",
        text: "Schalter „Bedarfsplan für alle“ in der Auswertung bzw. unter Orte & Bedarfsplan.",
      },
      perm_incidents_view: {
        title: "Einsätze ansehen",
        short: "Einsatzliste, einzelne Einsätze und Hinweise – ohne Anwesenheit, wenn das Recht dafür fehlt.",
        text: "Einsatzliste, einzelne Einsätze und Hinweise – ohne Anwesenheit, wenn das Recht dafür fehlt.",
      },
      perm_incidents_export: {
        title: "Excel-Export",
        short: "Einsatzübersicht als Excel; die Anwesenheit nur mit dem Recht „Anwesenheit und Kameraden sehen“.",
        text: "Einsatzübersicht als Excel; die Anwesenheit nur mit dem Recht „Anwesenheit und Kameraden sehen“.",
      },
      perm_reports_import: {
        title: "Berichte einlesen",
        short: "Einsatzberichte (PDF, Excel) einlesen und übernehmen, auch Berichte, die eine andere Wehr weitergegeben hat.",
        text: "Einsatzberichte (PDF, Excel) einlesen und übernehmen, auch Berichte, die eine andere Wehr weitergegeben hat.",
      },
      perm_incidents_edit: {
        title: "Einsätze bearbeiten",
        short: "Felder und Fahrzeuge eines Einsatzes ändern, Hinweise erledigen.",
        text: "Felder und Fahrzeuge eines Einsatzes ändern, Hinweise erledigen.",
      },
      perm_incidents_delete: {
        title: "Einsätze löschen",
        short: "Einen Einsatz endgültig entfernen.",
        text: "Einen Einsatz endgültig entfernen.",
      },
      perm_people_view: {
        title: "Anwesenheit und Kameraden sehen",
        short: "Namen der Kameraden, Anwesenheit je Einsatz und Reiter Kameraden. Nur für Rollen einer Wehr.",
        text: "Namen der Kameraden, Anwesenheit je Einsatz und Reiter Kameraden. Nur für Rollen einer Wehr.",
      },
      perm_people_edit: {
        title: "Anwesenheit bearbeiten",
        short: "Anwesenheit eines Einsatzes ändern und Kameraden ergänzen. Nur für Rollen einer Wehr.",
        text: "Anwesenheit eines Einsatzes ändern und Kameraden ergänzen. Nur für Rollen einer Wehr.",
      },
      perm_tenant_settings: {
        title: "Einstellungen, Fahrzeuge, Farben und Logos",
        short: "Fahrzeuge, BKS-Kennung, Orte, Zeitgrenzen, Farben und Logos. In einer Rolle der VG: Vorgaben für alle Wehren der VG.",
        text: "Name, Farben, Logos, Fahrzeuge, BKS-Kennung, Orte und Zeitgrenzen. In einer Rolle der Wehr: Werte und Abweichungen dieser Wehr von den Vorgaben der VG. In einer Rolle der VG: die Vorgaben für alle Wehren der VG und die Fahrzeuge aller Wehren.",
      },
      perm_tenant_keywords: {
        title: "Stichwortkatalog",
        short: "Stichworte ergänzen, ändern, deaktivieren oder einlesen – in einer Rolle der VG für alle Wehren der VG.",
        text: "Stichworte ergänzen, ändern, deaktivieren oder einlesen. In einer Rolle der Wehr: Abweichungen vom Katalog der VG (Stichwort gilt hier nicht, eigene Bezeichnung, eigene Stichworte). In einer Rolle der VG: der Katalog für alle Wehren der VG.",
      },
      perm_vg_overview: {
        title: "Gesamtansicht der VG",
        short: "Auswahl „Wehrleitung“ oben: Auswertung aller Wehren der VG zusammen. Nur für Rollen der VG.",
        text: "Auswahl „Wehrleitung“ oben: Auswertung aller Wehren der VG zusammen. Nur für Rollen der VG.",
      },
      perm_vg_records: {
        title: "Prüfprotokoll und Kostenersatz",
        short: "Abgleich der Berichte aller Wehren je Einsatz und Kostenaufstellung. Nur für Rollen der VG.",
        text: "Abgleich der Berichte aller Wehren je Einsatz und Kostenaufstellung. Nur für Rollen der VG.",
      },
      perm_vg_fees: {
        title: "Gebührenordnung der VG",
        short: "Gebührenordnung (Kostenersatz) der VG pflegen. Nur für Rollen der VG.",
        text: "Gebührenordnung (Kostenersatz) der VG in Fassungen mit Gültigkeitsbeginn pflegen. Nur für Rollen der VG.",
      },
      perm_dpa_view: {
        title: "Auftragsverarbeitung ansehen",
        short: "Stand des AVV der VG ansehen.",
        text: "Stand des AVV der VG ansehen.",
      },
      perm_dpa_edit: {
        title: "Auftragsverarbeitung ausfüllen",
        short: "AVV ausfüllen, Vertrag erzeugen und das unterschriebene Dokument ablegen.",
        text: "AVV ausfüllen, Vertrag erzeugen und das unterschriebene Dokument ablegen.",
      },
      perm_users_view: {
        title: "Zuordnungen sehen",
        short: "Wer welche Rolle hat, Rechte einer Person und das Protokoll – im eigenen Bereich.",
        text: "Wer welche Rolle hat, Rechte einer Person und das Protokoll – im eigenen Bereich.",
      },
      perm_users_grant: {
        title: "Rollen vergeben",
        short: "Rollen vergeben und entziehen, soweit die Verteilung der eigenen Rolle es erlaubt.",
        text: "Rollen vergeben und entziehen, soweit die Verteilung der eigenen Rolle es erlaubt.",
      },
      perm_roles_manage: {
        title: "Rollen der VG anlegen und ändern",
        short: "Eigene Rollen der VG anlegen, ändern und löschen. Nur für Rollen der VG.",
        text: "Eigene Rollen der VG anlegen, ändern und löschen. Nur für Rollen der VG.",
      },
    },
  },
];

const HELP = Object.fromEntries(HELP_SECTIONS.flatMap((s) => Object.entries(s.entries)));

/** Kleines ?-Symbol: Tooltip mit Kurztext, Klick öffnet das Hilfefenster an der Stelle. */
function helpButton(key) {
  const h = HELP[key];
  if (!h) return "";
  return `<button type="button" class="help-btn" data-help="${key}" data-tip="${esc(helpValue(h.short))}" aria-label="Hilfe: ${esc(helpValue(h.title))}">?</button>`;
}

function helpContent() {
  return HELP_SECTIONS.map((s) => `<section class="help-section" id="help-${s.id}">
    <h3>${s.title}</h3>${s.intro ? `<p class="muted">${s.intro}</p>` : ""}
    <dl class="help-list">${Object.entries(s.entries).map(([k, e]) =>
      `<div id="help-${k}"><dt>${helpValue(e.title)}</dt><dd>${helpValue(e.text)}</dd></div>`).join("")}</dl>
  </section>`).join("");
}

/** Hilfe zur aktuellen Stelle: offener Dialog, sonst die Ansicht (VIEWS[…].help, Abschnitt- oder Feldschlüssel). */
function helpContext() {
  if ($("#pdf-dialog").open) return "sec_capture";
  if ($("#fees-dialog").open) return "fees";
  return helpValue(VIEWS[state.view]?.help) || null;
}

/** Hilfefenster öffnen: key = Feld (hervorgehoben) oder Abschnitt (sec_…); tab = help, news oder feedback. */
function openHelp(key, tab = "help") {
  const dialog = $("#help-dialog");
  const body = $("#help-body");
  if (!body.innerHTML) body.innerHTML = helpContent();
  for (const el of body.querySelectorAll(".highlight")) el.classList.remove("highlight");
  showHelpTab(tab);
  if (!dialog.open) dialog.showModal();
  const target = key && $(`#help-${key}`);
  if (target && tab === "help") {
    // Abschnitt an den Anfang, Feld hervorgehoben in die Mitte
    const section = key.startsWith("sec_");
    if (!section) target.classList.add("highlight");
    target.scrollIntoView({ block: section ? "start" : "center" });
  } else {
    $("#help-dialog .dialog-body:not([hidden])").scrollTop = 0;
  }
}

function showHelpTab(tab) {
  if (tab === "feedback" && !config?.feedback) tab = "help";
  for (const b of $$("#help-tabs button")) b.classList.toggle("active", b.dataset.helpTab === tab);
  $("#help-tabs [data-help-tab=feedback]").hidden = !config?.feedback;
  $("#help-body").hidden = tab !== "help";
  $("#help-news").hidden = tab !== "news";
  $("#help-feedback").hidden = tab !== "feedback";
  $("#help-intro").hidden = tab !== "help";
  if (tab === "news") {
    if (!$("#help-news").innerHTML) $("#help-news").innerHTML = changelogContent();
    remember("changelog_seen", CHANGELOG[0].date);
    markNews();
  }
  if (tab === "feedback") $("#feedback-form textarea").focus();
}

// ------------------------------------------------------------ Neuigkeiten
function changelogContent() {
  return CHANGELOG.map((v) => `<section class="help-section">
    <h3>${formatDate(v.date)}</h3>
    <ul class="changelog">${v.items.map((i) => `<li>${i}</li>`).join("")}</ul>
  </section>`).join("");
}

/** Punkt am ?-Symbol im Kopf, solange es ungelesene Neuigkeiten gibt. */
function markNews() {
  const unseen = CHANGELOG[0].date > (recall("changelog_seen") || "");
  const button = $("#btn-help");
  button.classList.toggle("has-news", unseen);
  button.title = unseen ? "Hilfe · Neuigkeiten" : "Hilfe";
  $("#help-tabs [data-help-tab=news]").classList.toggle("has-news", unseen);
}

// ------------------------------------------------------------ Feedback (per Mail an die Superadmins)
function feedbackView() {
  const view = VIEWS[state.view];
  const section = state.view === "admin" ? ADMIN_SECTIONS.find((x) => x.key === admin.section)?.label : "";
  return [view?.label, section, $("#pdf-dialog").open && "Bericht einlesen"].filter(Boolean).join(" · ");
}

async function sendFeedback(form) {
  const message = form.elements.message.value.trim();
  const status = $("#feedback-status");
  if (!message) return;
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    await apiJson("/api/feedback", "POST", { message, view: feedbackView() });
    form.reset();
    status.className = "message message-info";
    status.textContent = "Danke! Dein Feedback ist verschickt.";
  } catch (e) {
    status.className = "message message-error";
    status.textContent = e.message;
  } finally {
    status.hidden = false;
    button.disabled = false;
  }
}

document.addEventListener("click", (e) => {
  const button = e.target.closest("[data-help]");
  if (!button) return;
  e.preventDefault();          // ?-Symbol steht teils in <label>/<th> – dort nichts anderes auslösen
  e.stopPropagation();
  openHelp(button.dataset.help);
}, true);

/** Start (aus app.js, sobald $ und config da sind): ?-Symbole der festen Elemente, Kopf-Symbol, Reiter, Feedback. */
function setupHelp() {
  // Fest in index.html stehende Elemente mit data-help-key bekommen ihr ?-Symbol aus derselben Quelle
  for (const el of $$("[data-help-key]")) el.insertAdjacentHTML("beforeend", helpButton(el.dataset.helpKey));
  markNews();
  $("#btn-help").addEventListener("click", () => openHelp(helpContext()));
  $("#help-tabs").addEventListener("click", (e) => {
    const button = e.target.closest("[data-help-tab]");
    if (button) showHelpTab(button.dataset.helpTab);
  });
  $("#feedback-form").addEventListener("submit", (e) => { e.preventDefault(); sendFeedback(e.target); });
  $("#feedback-form").addEventListener("input", () => { $("#feedback-status").hidden = true; });
}
