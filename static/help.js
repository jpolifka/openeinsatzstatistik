"use strict";

// Online-Hilfe: eine Quelle für das Hilfefenster (das ? im Kopf öffnet es passend zur Ansicht).
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
        text: () => `Einsatzbeginn = frühester Alarmierungszeitpunkt der eigenen Fahrzeuge (Funkrufname ${esc(config.own_prefix)}..). Gibt es keine, zählt die erste Alarmierung im Bericht. Alle Minutenwerte (Ausrückdauer, Zeit bis zum Eintreffen) werden ab diesem Zeitpunkt gerechnet. Der Beginn bestimmt außerdem Jahr, Monat, Wochentag und das Zeitfenster Tag/Nacht.`,
      },
      ended_at: {
        title: "Ende",
        short: "Spätestes Einsatzende der eigenen Fahrzeuge bzw. der FEZ.",
        text: "Einsatzende = spätestes Einsatzende der eigenen Fahrzeuge bzw. der Feuerwehreinsatzzentrale (FL NR#.LIN). Aus Beginn und Ende ergeben sich Einsatzdauer, Einsatzstunden und die Stunden je Person.",
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
        short: "Einsatzort; bestimmt Einsatzgebiet und Ausrückebereich.",
        text: () => `Ortsteil oder Ort des Einsatzes. Bekannte Orte der Wehr werden vorgeschlagen. Nur Einsätze in Orten, die in den Einstellungen unter „Orte & Zeitgrenzen“ zum Ausrückebereich zählen, gehen in „Eintreffen und verfügbare Kräfte“ ein – bitte den Ort daher genau so schreiben.`,
      },
      bks_url: {
        title: "BKS-Portal",
        short: "Bericht im BKS-Portal öffnen.",
        text: "Jeder Bericht im BKS-Portal hat eine eigene Nummer (Haupt- bzw. Nebenbericht einer Einheit). Alle Berichte eines Einsatzes verweisen auf denselben <i>Stammdatensatz</i>; darüber erkennt die App gemeinsame Einsätze mehrerer Wehren – auch selbst angelegte ohne Einsatznummer der Leitstelle, z. B. Brandsicherheitswachen. Der Link öffnet den Bericht im Portal (Anmeldung dort nötig).",
      },
      abort_reason: {
        title: "Einsatzabbruch",
        short: "Grund, warum der Einsatz abgebrochen wurde (aus dem BKS-Bericht).",
        text: () => `Wird aus dem Feld „Einsatzabbruch“ des BKS-Berichts übernommen (z. B. Täuschungsalarm, böswilliger Alarm, in Bereitstellung). Ist es gefüllt und fehlt die Eintreffzeit, gilt der Einsatz in „Eintreffen und verfügbare Kräfte“ als innerhalb der Zeitgrenze (${helpLimit()} Minuten) eingetroffen – die Einheit musste nicht mehr ankommen. Gibt es eine Eintreffzeit, zählt diese. Leer lassen, wenn der Einsatz nicht abgebrochen wurde.`,
      },
      building: {
        title: "Objekt",
        short: "Objekt der Einsatzstelle aus dem BKS-Bericht (z. B. Pflegeheim).",
        text: "Wird aus dem Feld „Einsatzstelle – Objekt“ übernommen. Es dient der Auswertung von Brandmeldeanlagen: Einsätze werden je Objekt gezählt, wenn keine Nummer der Anlage angegeben ist.",
      },
      alarm_system: {
        title: "Brandmelde-Nr.",
        short: "Nummer der Gefahrenmeldeanlage laut BKS-Bericht.",
        text: "Nummer der Gefahrenmeldeanlage (Brandmeldeanlage), die den Alarm ausgelöst hat. „0“ und „-“ gelten als nicht angegeben. Unter „Auswertungen → Abbrüche &amp; Anlagen“ werden Alarme und Fehlalarme je Anlage gezählt.",
      },
      tactic: {
        title: "Einsatztaktik",
        short: "Innen- oder Außenangriff laut BKS-Bericht.",
        text: "Taktik bei Brandeinsätzen laut Bericht (Innenangriff oder Außenangriff). Sie steht im Brandverlauf unter „Auswertungen → Brand &amp; Rettung“.",
      },
      fire_controlled_at: {
        title: "Brand unter Kontrolle",
        short: "Zeitpunkt „Brand unter Kontrolle“ laut Bericht.",
        text: "Die Auswertung rechnet die Zeit ab dem Eintreffen des ersten eigenen Fahrzeugs bis zu diesem Zeitpunkt. Ohne Eintreffzeit entfällt der Einsatz in dieser Kennzahl.",
      },
      fire_out_at: {
        title: "Feuer aus",
        short: "Zeitpunkt „Feuer aus“ laut Bericht.",
        text: "Zeitpunkt, an dem das Feuer aus war. Die Auswertung rechnet die Zeit ab dem Eintreffen des ersten eigenen Fahrzeugs.",
      },
      fire_watch_until: {
        title: "Brandwache bis",
        short: "Ende der Brandwache nach dem Einsatz laut Bericht.",
        text: "Bis wann eine Brandwache an der Einsatzstelle gestellt wurde (nicht die Brandsicherheitswache S1.00). Die Dauer wird ab „Feuer aus“, ersatzweise ab Einsatzende gerechnet.",
      },
      rescued: {
        title: "Menschen gerettet",
        short: "Summe der Menschenrettungen laut Bericht (alle Verfahren).",
        text: "Summe aller Angaben „Menschenrettung über/mit …“ des Berichts (baulicher Rettungsweg, Hubrettungsfahrzeug, Leiter, Boot, Schere/Spreizer, sonstiges). Leer heißt nicht angegeben, 0 heißt: ausdrücklich keine.",
      },
      rescued_animals: {
        title: "Tiere gerettet",
        short: "Gerettete Groß- und Kleintiere laut Bericht.",
        text: "Summe aus „Rettung von Großvieh“ und „Rettung von Kleinvieh“. Leer heißt nicht angegeben.",
      },
      injured: {
        title: "Verletzte",
        short: "Verletzte andere Personen (nicht Feuerwehr) laut Bericht.",
        text: "Verletzte Personen außer Feuerwehrangehörigen. Leer heißt nicht angegeben.",
      },
      injured_firefighters: {
        title: "Verletzte Feuerwehrangehörige",
        short: "Verletzte Feuerwehrangehörige laut Bericht.",
        text: "Verletzte Angehörige der Feuerwehr im Einsatz. Leer heißt nicht angegeben.",
      },
      deceased: {
        title: "Verstorbene",
        short: "Verstorbene Personen laut Bericht (Feuerwehr und andere).",
        text: "Summe aus „Verstorbene andere Personen“ und „Verstorbene Feuerwehrangehörige“. Leer heißt nicht angegeben.",
      },
      dispatch_number: {
        title: "Leitstellen-Nr.",
        short: "Gemeinsame Einsatznummer der Leitstelle für beteiligte Wehren.",
        text: "Die Einsatznummer der Leitstelle verbindet Berichte desselben Einsatzes über mehrere Wehren. Sie ist nicht die laufende Nummer der Wehr und nicht die BKS-Bericht-ID. Leer bedeutet unbekannt; bei Korrekturen den Originalbericht prüfen.",
      },
      unit_leader: {
        title: "Einheitsführung (EHF)",
        short: "Einheitsführer, Schreibweise „V. Nachname“.",
        text: "Einheitsführer des Einsatzes in der Schreibweise <i>V. Nachname</i>. Übernommen wird die Person mit der Funktion „Einheitsführer“. Fehlt sie im Bericht, wird der Einsatzleiter eingetragen und ein Prüfhinweis erzeugt – ist auch der nicht in der Anwesenheit, bleibt das Feld leer und ist rot markiert. Ein Klick auf einen Namen in der Anwesenheit trägt diese Person als Einheitsführung ein.",
      },
    },
  },
  {
    id: "sec_metrics",
    title: "Kennzahlen je Einsatz",
    intro: "Werden aus den Fahrzeugzeiten berechnet und sind nicht direkt änderbar – korrigieren Sie bei Bedarf Beginn oder Ende.",
    entries: {
      turnout_min: {
        title: "Ausrückdauer",
        short: "Minuten von der Alarmierung bis zum Ausrücken des schnellsten Fahrzeugs.",
        text: "Minuten vom Einsatzbeginn bis zum Ausrücken (Status 3) des schnellsten eigenen Fahrzeugs. In der Fahrzeugtabelle steht die Ausrückdauer je Fahrzeug.",
      },
      arrival_min: {
        title: "Zeit bis zum Eintreffen",
        short: "Minuten von der Alarmierung bis zum Eintreffen des ersten Fahrzeugs.",
        text: () => `Minuten vom Einsatzbeginn bis zum Eintreffen (Status 4) des ersten eigenen Fahrzeugs an der Einsatzstelle. Rot markiert, wenn sie über ${helpLimit()} Minuten liegt. Ohne Eintreffzeit wird der Einsatz in der Auswertung „Eintreffen und verfügbare Kräfte“ nicht berücksichtigt – außer es ist ein Einsatzabbruch hinterlegt: dann gilt er als rechtzeitig eingetroffen. Die Uhrzeit des Eintreffens selbst heißt „Eintreffen“.`,
      },
      on_time: {
        title: () => `${helpLimit()} Min. erreicht`,
        short: "Ja, wenn das erste Fahrzeug innerhalb der Zeitgrenze eingetroffen ist.",
        text: () => `„Ja“, wenn die Zeit bis zum Eintreffen höchstens der Zeitgrenze entspricht (${helpLimit()} Minuten; in der Auswertung umschaltbar: ${helpLimits()}). Grundlage der Eintreffquote in „Eintreffen und verfügbare Kräfte“.`,
      },
      crew_on_arrival: {
        title: "Stärke bei Eintreffen",
        short: "Besatzung der Fahrzeuge, die als erste eingetroffen sind.",
        text: "Summe der Besatzung aller Fahrzeuge, die zum Zeitpunkt des ersten Eintreffens eingetroffen sind.",
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
        text: () => `Besatzung aller eigenen Fahrzeuge plus Personen im Gerätehaus.${config.plan_excluded_vehicles.length ? ` In „Eintreffen und verfügbare Kräfte“ wird – wie in der Einsatzübersicht – ohne ${helpList(config.plan_excluded_vehicles)} gerechnet.` : ""}`,
      },
      duration: {
        title: "Dauer",
        short: "Zeit von Beginn bis Ende des Einsatzes.",
        text: "Zeit von Einsatzbeginn bis Einsatzende. Grundlage für Einsatzstunden, Personalstunden und die Stunden je Person.",
      },
      time_window: {
        title: "Zeitfenster",
        short: "Werktag oder Sa/So/Feiertag, Tag (06–18 Uhr) oder Nacht.",
        text: () => `Einordnung nach Einsatzbeginn: <b>Tag</b> ${helpDay().join("–")} Uhr, sonst <b>Nacht</b>; <b>Sa/So/Feiertag</b> an Wochenenden und gesetzlichen Feiertagen in Rheinland-Pfalz, sonst <b>Werktag</b>. In der Liste als „WE/FT“ gekennzeichnet.`,
      },
      vehicles: {
        title: "Fahrzeuge",
        short: "Stärke sowie Ausrücken und Eintreffen (Uhrzeit) je Fahrzeug.",
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
        text: "Personen aus der Anwesenheitsliste des Berichts, mit Fahrzeug und Funktion. Namen werden mit den bekannten Personen abgeglichen; unbekannte Namen sind markiert und werden beim Übernehmen als neue Personen angelegt. Beim Bearbeiten und in der Vorschau trägt ein Klick auf einen Namen die Person als Einheitsführung ein; die Einheitsführung ist dunkelrot hervorgehoben.",
      },
    },
  },
  {
    id: "sec_evaluation",
    title: "Einsatzgeschehen",
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
        short: "Einsatzdauer × anwesende Personen, über alle Einsätze.",
        text: "Für jeden Einsatz Dauer × Anzahl der Anwesenden, aufsummiert über das Jahr. Darunter steht die durchschnittliche Zahl Anwesender je Einsatz.",
      },
      response_plan: {
        title: "Eintreffen und verfügbare Kräfte",
        short: "Anteil der Einsätze, bei denen das erste eigene Fahrzeug rechtzeitig eintraf.",
        text: () => `Berücksichtigt werden Einsätze ab Alarmstufe ${config.plan_min_level} (Stichwort x${config.plan_min_level}–x4) im Ausrückebereich der Wehr mit Eintreffzeit. Welche Orte zum Ausrückebereich gehören, legt die Verwaltung unter „Einstellungen → Orte & Zeitgrenzen“ fest. Einsätze ohne Eintreffzeit, bei denen ein Einsatzabbruch hinterlegt ist, gelten als rechtzeitig eingetroffen. Eintreffquote = Anteil der Einsätze, bei denen das erste Fahrzeug innerhalb der Zeitgrenze (${helpLimits()} Minuten) eingetroffen ist – getrennt nach den vier Zeitfenstern Werktag/Wochenende × Tag/Nacht. Die Stärken sind Mittelwerte je Einsatz. <b>Was die Auswertung nicht aussagt:</b> Sie misst, ob das erste eigene Fahrzeug rechtzeitig eintraf, und zählt die Personen der Fahrzeuge. Funktionen, Ausrüstung und Qualifikation (z. B. Staffel 1/5/6, Gruppe 1/8/9 nach FwDV 3) prüft sie nicht; sie ist daher eine Eintreffquote, kein vollständiger Nachweis eines Schutzziels und kein Feuerwehrbedarfsplan. Die Zeitgrenze richtet sich nach den Einstellungen der Wehr (seit 26.09.2025 nennt die Feuerwehrverordnung RLP zehn statt acht Minuten Einsatzgrundzeit); wer Jahre vergleicht, sollte dieselbe Grenze wählen. Zunächst sehen die Auswertung nur Wehrführer und Wehrleiter; mit „für alle freigegeben“ (oder in den Einstellungen unter „Orte & Zeitgrenzen“) sehen sie alle Rollen der Wehr.`,
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
        text: "In der Gesamtansicht einer Verbandsgemeinde zählt ein Einsatz, an dem mehrere Wehren beteiligt waren, bei jeder Wehr (Beteiligungen). Die große Zahl zählt ihn nur einmal: Einsätze mit demselben Stammdatensatz im BKS-Portal oder derselben Einsatznummer der Leitstelle gelten als ein Einsatz. Einsätze ohne beides (z. B. aus der früheren Excel-Übersicht) zählen einzeln. Alle übrigen Kennzahlen und Diagramme summieren die Beteiligungen; die Auswertung „Eintreffen und verfügbare Kräfte“ wertet jede Wehr mit ihren eigenen Orten aus. Über die Schaltflächen oben lässt sich die Auswertung auf einzelne Wehren einschränken.",
      },
    },
  },
  {
    id: "sec_overview",
    title: "Übersicht",
    intro: "Der Einstieg: Jahreskennzahlen, was noch zu tun ist und wie vollständig die Daten sind.",
    entries: {
      overview_tasks: {
        title: "Offene Aufgaben",
        short: "Einsätze mit Prüfhinweisen oder fehlenden Angaben, dazu Hinweise an die Wehr.",
        text: "Hier stehen Einsätze des gewählten Jahres, die Aufmerksamkeit brauchen: Einsätze mit aktuellen Prüfhinweisen und Einsätze, denen eine Angabe fehlt (Einsatzdauer, Ausrücken, Eintreffen, Besatzung, Anwesenheit, Einheitsführung). Ein Klick öffnet die Einsatzliste mit genau diesem Filter. Hinweise an die Wehr (z. B. ein von anderen eingelesener Bericht) lassen sich hier einblenden.",
      },
      data_coverage: {
        title: "Datenvollständigkeit",
        short: "Für wie viele Einsätze liegt eine Angabe vor? Fehlendes ist nicht null.",
        text: "Zeigt je Angabe, für wie viele Einsätze des Jahres sie vorliegt. Einsätze ohne Angabe gehen nicht als Null in Durchschnitte ein, sondern fehlen in der jeweiligen Kennzahl – die Kennzahlen nennen deshalb ihre Fallzahl („42 von 57 Einsätzen auswertbar“). „Besatzung“ heißt: Mindestens ein eigenes Fahrzeug oder Personen im Gerätehaus sind mit Stärke erfasst.",
      },
    },
  },
  {
    id: "sec_times",
    title: "Zeiten & Kräfte",
    intro: "Wo entsteht die Zeit zwischen Alarmierung und Hilfe – und wie viele Kräfte sind wann vor Ort? Gerechnet wird aus allen Einsätzen des Jahres, nicht nur aus denen des Ausrückebereichs. Wie „Eintreffen und verfügbare Kräfte“ ist die Auswertung nur sichtbar, wenn sie freigegeben ist.",
    entries: {
      time_distribution: {
        title: "Median und 90. Perzentil",
        short: "Median: die Hälfte war schneller. 90 %: neun von zehn waren höchstens so langsam.",
        text: "Der <b>Median</b> ist der mittlere Wert – die Hälfte der Einsätze war schneller, die Hälfte langsamer. Das <b>90. Perzentil</b> sagt, wie lang es in neun von zehn Fällen höchstens dauerte; es zeigt die Verlässlichkeit besser als der Durchschnitt, den einzelne Ausreißer verzerren. Berechnet wird das Perzentil nach dem Rangverfahren (nächster Rang). <b>Fälle</b> nennt, für wie viele Einsätze bzw. Fahrzeuge der Wert vorliegt.",
      },
      travel_min: {
        title: "Anfahrtdauer je Fahrzeug",
        short: "Minuten vom Ausrücken bis zum Eintreffen desselben Fahrzeugs.",
        text: "Für jedes eigene Fahrzeug: Eintreffen minus Ausrücken <i>desselben</i> Fahrzeugs. Nicht gerechnet wird vom frühesten Ausrücken eines Fahrzeugs bis zur Ankunft eines anderen. Fahrzeuge ohne beide Zeiten oder mit unplausibler Reihenfolge (Eintreffen vor Ausrücken) fehlen und sind in „Fälle“ nicht enthalten. So lässt sich trennen: Personal sammeln (Ausrückdauer) oder Fahrt (Anfahrtdauer).",
      },
      build_up: {
        title: "Kräfteaufbau nach Alarmierung",
        short: "Ø Personen der bis dahin eingetroffenen eigenen Fahrzeuge nach 5, 10, 15 Minuten.",
        text: () => `Für jeden Einsatz mit Eintreffzeit die Besatzung aller eigenen Fahrzeuge, die nach 5, 10 und 15 Minuten (sowie ${helpLimits()} und ${config.second_limit} Minuten) nach Einsatzbeginn eingetroffen waren; angezeigt wird der Durchschnitt. Das sind Personen, keine taktischen Einheiten: Funktionen, Ausrüstung und Qualifikation (z. B. Staffel 1/5/6, Gruppe 1/8/9 nach FwDV 3) sind nicht erfasst.`,
      },
      time_groups: {
        title: "Zeiten nach Tageszeit und Ort",
        short: "Median und 90. Perzentil je Zeitfenster und Einsatzgebiet; kleine Fallzahlen sind gekennzeichnet.",
        text: "Dieselben Zeiten, gruppiert nach Werktag/Wochenende × Tag/Nacht und nach Einsatzgebiet. Gruppen mit weniger als 5 Einsätzen sind als „wenige Fälle“ gekennzeichnet; ihre Werte schwanken stark und sagen wenig über ein Muster aus.",
      },
    },
  },
  {
    id: "sec_load",
    title: "Belastung",
    intro: "Was hinter der reinen Zahl der Einsätze steckt: Dauer, Nachtstunden und gleichzeitige Einsätze.",
    entries: {
      workload: {
        title: "Lange und nächtliche Einsätze",
        short: "Einsätze ab zwei Stunden Dauer, in der Nacht und an Wochenenden/Feiertagen mit Stunden.",
        text: () => `<b>Lang</b> sind Einsätze ab zwei Stunden (Alarm bis Einsatzende). <b>Nachts</b> sind Einsätze mit Beginn außerhalb der Tagesstunden (${helpDay().join("–")} Uhr gilt als Tag). <b>Samstag, Sonntag, Feiertag</b> wie im Einsatzgeschehen. Ein Einsatz kann in mehreren Zeilen vorkommen. Die Personalstunden beruhen auf der erfassten Anwesenheit; fehlt sie, fehlen die Stunden (die Zeile nennt, für wie viele Einsätze sie vorliegen) – sie sind keine Stempelzeiten, sondern Einsatzdauer × Anwesende.`,
      },
      overlaps: {
        title: "Zeitliche Überschneidung",
        short: "Wann waren mehrere Einsätze gleichzeitig offen? Das belegt keine gebundenen Kräfte.",
        text: "Zählt Einsätze der Wehr, deren Zeitraum (Beginn bis Ende) sich mit einem anderen überschneidet, die höchste Zahl gleichzeitig offener Einsätze und die Zeit mit mindestens zwei offenen Einsätzen. Berührt das Ende eines Einsatzes genau den Beginn des nächsten, gilt das nicht als Überschneidung. Offen heißt nicht, dass dieselben Fahrzeuge oder Personen gebunden waren; die tatsächliche Bindung ist aus den Berichten nicht vollständig belegt. In der Gesamtansicht einer Verbandsgemeinde wird je Wehr gerechnet und addiert.",
      },
    },
  },
  {
    id: "sec_aborts",
    title: "Abbrüche und Brandmeldeanlagen",
    intro: "Wie viele Einsätze enden, bevor die Einheit gebraucht wird, und welche Anlagen die meisten Alarme auslösen. Grundlage ist das Feld „Einsatzabbruch“ des BKS-Berichts.",
    entries: {
      abort_kinds: {
        title: "Abbruchgründe",
        short: "Abgebrochene Einsätze nach Gruppen des Abbruchgrunds.",
        text: "Der Grund steht im Bericht als Freitext. Die App ordnet ihn vier Gruppen zu: <b>Fehlalarm / kein Ereignis</b> (Täuschungsalarm, technischer oder böswilliger Alarm, kein Schadenereignis festgestellt), <b>Nicht erforderlich</b>, <b>In Bereitstellung</b> und <b>Sonstiger Grund</b>. Die Zuordnung steht nicht im Bericht, sondern beruht auf dem Wortlaut; die Tabelle „Häufigste Gründe“ zeigt den Originaltext. Abgebrochene Einsätze ohne Eintreffzeit gelten in „Eintreffen und verfügbare Kräfte“ als rechtzeitig.",
      },
      alarm_systems: {
        title: "Brandmeldeanlagen",
        short: "Einsätze an Brandmeldeanlagen je Anlage bzw. Objekt, mit Anteil der Fehlalarme.",
        text: "Gezählt werden Einsätze mit Stichwort B2.07 und Einsätze mit angegebener Nummer der Gefahrenmeldeanlage. Gruppiert wird nach dieser Nummer, ersatzweise nach dem Objekt der Einsatzstelle. Einsätze ohne beides stehen gesammelt unter „ohne Angabe“. Als Fehlalarm zählen abgebrochene Einsätze mit Täuschungs-, technischem oder böswilligem Alarm bzw. ohne festgestelltes Ereignis. Hinweis: Die Zahlen können Argumente gegenüber Betreibern liefern – prüfen Sie vorher die Berichte der betroffenen Anlage.",
      },
    },
  },
  {
    id: "sec_resources",
    title: "Fahrzeuge und Atemschutz",
    intro: "Wie stark Fahrzeuge und Atemschutzgeräteträger gebraucht werden.",
    entries: {
      vehicle_usage: {
        title: "Fahrzeugnutzung",
        short: "Alarmierungen, Ausfahrten und tatsächliche Einsätze je Fahrzeug.",
        text: "<b>Alarmiert</b>: das Fahrzeug steht im Bericht. <b>Ausgerückt</b>: es hat eine Ausrückzeit. <b>Eingesetzt</b> bzw. <b>nur bereit</b>: Angabe „Eingesetzt“ der Fahrzeugtabelle (Ja/Nein) – ein Fahrzeug in Bereitstellung ist alarmiert, aber nicht eingesetzt. Ältere Einsätze haben die Angabe nicht; sie zählen nicht als „nur bereit“. <b>Einsatzstunden</b> = Alarmierung bis Einsatzende des Fahrzeugs, nur für ausgerückte Fahrzeuge. <b>Ø Besatzung</b> = mittlere Stärke bei Ausfahrten.",
      },
      respiratory: {
        title: "Atemschutz",
        short: "Einsätze mit Atemschutz, Geräteträger und Minuten unter Atemschutz.",
        text: "<b>Geräteträger</b> sind die AGT-Zahlen der Fahrzeuge im Bericht. Die <b>Minuten</b> stammen aus der Anwesenheitsliste („Min (AGT)“) je Person. Sie sind Angaben der Berichtenden, keine Messwerte der Atemschutzüberwachung. Einsätze ohne diese Angaben (ältere Berichte) fehlen in den Kennzahlen; die Karte nennt die Abdeckung. Namen und Zeiten je Person stehen unter „Personal“.",
      },
    },
  },
  {
    id: "sec_fire",
    title: "Brand und Rettung",
    intro: "Brandverlauf, Einsatztaktik, Menschenrettung und Personenschäden aus den Angaben des BKS-Berichts.",
    entries: {
      fire_course: {
        title: "Brandverlauf",
        short: "Zeit vom Eintreffen bis „Brand unter Kontrolle“ und „Feuer aus“.",
        text: "Berücksichtigt werden Brandeinsätze (Einsatzart B) ohne Abbruch, ohne Brandmeldeanlagen (B2.07) und ohne Brandsicherheitswachen. Die Zeit läuft ab dem Eintreffen des ersten eigenen Fahrzeugs; ohne Eintreffzeit oder bei Zeiten vor dem Eintreffen entfällt der Einsatz in der Kennzahl. Median und 90. Perzentil wie bei den Zeiten.",
      },
      fire_tactic: {
        title: "Einsatztaktik und Brandwache",
        short: "Innen- oder Außenangriff und Brandwachen nach dem Einsatz.",
        text: "Die Taktik wird nur angezeigt, wenn sie im Bericht angegeben ist. Brandwachen: Einsätze mit „Brandwache gestellt bis“; die Stunden laufen von „Feuer aus“ (ersatzweise Einsatzende) bis zum angegebenen Ende.",
      },
      casualties: {
        title: "Menschenrettung und Personenschäden",
        short: "Gerettete Menschen und Tiere, Verletzte und Verstorbene laut Bericht.",
        text: "Summen der Angaben im Bericht. „Menschen gerettet“ addiert alle Verfahren der Menschenrettung. Was nicht angegeben ist, zählt nicht als null: Die Spalte „Berichte mit Angabe“ nennt, in wie vielen Einsätzen die Zahl überhaupt vorliegt.",
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
        text: "Für jeden Einsatz mit Stammdatensatz vergleicht das Protokoll die Zeiten der Leitstelle mit den Berichten der Wehren. „Geprüft“ (in der Zeile) bzw. „Als geprüft markieren“ gilt für den jetzigen Stand: Kommt ein neuer Befund hinzu (z. B. ein geänderter Bericht), ist der Einsatz wieder offen. „Alle bestätigen“ vermerkt alle offenen Einsätze des Jahres auf einmal als geprüft – erst nach Durchsicht verwenden. „Einsatz öffnen“ springt zum erfassten Bericht der Wehr in der Einsatzliste. „Drucken / PDF“ druckt die angezeigten Einsätze mit ihren Befunden.",
      },
      fees: {
        title: "Kostenersatz",
        short: "Kostenaufstellung nach der Gebührenordnung der VG (Recht „Prüfprotokoll und Kostenersatz“, z. B. Wehrleiter).",
        text: "Im Reiter „Kostenersatz“ (unter „Einsätze“) rechnet „Kostenersatz berechnen“ einen Einsatz über alle beteiligten Wehren nach der Gebührenordnung (Verwaltung → Gebührenordnung): Fahrzeuge je Stunde vom Ausrücken bis zum Einsatzende des Fahrzeugs, Einsatzkräfte je Person und Stunde von der Alarmierung bis zum Einsatzende (Brandsicherheitswache mit eigenem Satz). Angefangene Stunden werden bis 30 Minuten als halbe, darüber als volle Stunde abgerechnet. Bei einem Fehlalarm einer Brandmeldeanlage gilt höchstens die Pauschale. Auslagen bekommen den Verwaltungszuschlag, Umsatzsteuer nur, wenn sie anfällt. Den Fahrzeugtyp liefert die Bezeichnung in der Fahrzeugliste (z. B. „HLF 20“). Es wird nichts gespeichert.",
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
    title: "Einsatzteilnahmen",
    intro: "Anwesenheit je Person im gewählten Jahr. Spaltenköpfe anklicken zum Sortieren.",
    entries: {
      participation: {
        title: "Beteiligung",
        short: "Anteil der Einsätze des Jahres, bei denen die Person anwesend war.",
        text: "Einsätze der Person geteilt durch alle Einsätze des Jahres.",
      },
      hours: {
        title: "Stunden",
        short: "Summe der Einsatzdauer aller Einsätze mit Teilnahme.",
        text: "Summe der Einsatzdauer aller Einsätze, bei denen die Person in der Anwesenheit steht.",
      },
      member_agt: {
        title: "Atemschutz",
        short: "Einsätze mit Atemschutz und Minuten unter Atemschutz laut Anwesenheitsliste.",
        text: "Einsätze, in denen die Person laut Anwesenheitsliste unter Atemschutz eingesetzt war, und die dort eingetragenen Minuten. Ältere Einsätze ohne diese Angabe sind nicht enthalten (Bericht erneut einlesen). Die Werte ersetzen keinen Atemschutznachweis.",
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
        text: "Kategorie, Suche, Sortierung und der Filter <b>Prüfhinweise</b> (nur Einsätze mit aktuellen Prüfhinweisen, z. B. ohne Eintreffzeit oder Anwesenheit) stehen in der Adresse der Seite: Sie bleiben beim Neuladen erhalten, und ein kopierter Link zeigt anderen dieselbe Liste. In der <b>Auswertung</b> öffnet ein Klick auf einen Balken, eine Säule oder die Zahlen in „Eintreffen und verfügbare Kräfte“ die passenden Einsätze; der Filter steht dann als Chip über der Liste und lässt sich mit × entfernen. Spaltenköpfe mit ▾/▴ sortieren die Liste. Kategorie, Sortierung und Tabellen-/Diagrammansicht merkt sich der Browser.",
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
        text: "Farbe über den Farbwähler, als Hex-Wert (#RRGGBB) oder als Rot/Grün/Blau-Anteile (0–255) einstellen – die drei Eingaben bleiben gleich. Aus der Hauptfarbe leitet die App alle anderen Töne ab (Flächen, Tabellenköpfe, Fokusrahmen); die Diagramme sind neutral grau und dunkelt sie bei Bedarf so weit ab, dass Schrift und Diagramme lesbar bleiben. Ist die Hauptfarbe selbst zu hell für weiße Schrift (Kontrast unter 4,5:1), lässt sie sich nicht speichern. Ohne eigene Farbe gilt das Standard-Bordeaux (#7C2734) mit Sand für Tabellen und Flächen; Hinweise und Fehler sind in jeder Wehr signalorange. Die Gesamtansicht einer VG und die Anmeldung sind immer neutral gestaltet.",
      },
      admin_logos: {
        title: "Logos",
        short: "Logo für Kopfzeile, Fußzeile und Browser-Tab.",
        text: "<b>Logo hell</b> steht auf der farbigen Kopfzeile (am besten weiß auf transparent), <b>Logo dunkel</b> in der Fußzeile, das <b>Symbol</b> im Browser-Tab. Erlaubt sind PNG, JPEG und WebP bis 512 KB; SVG geht aus Sicherheitsgründen nicht. Ohne eigenes Bild erscheint das neutrale Signet.",
      },
      admin_font: {
        title: "Schrift",
        short: "Eigene Schriftdatei für die Oberfläche der Wehr.",
        text: "Ohne eigene Datei zeigt die App Systemschriften (Segoe UI, Roboto, Helvetica, Arial), wie das BKS-Portal. Für ein eigenes Erscheinungsbild lässt sich eine <b>Schriftdatei</b> für normalen und optional für fetten Text hochladen: WOFF2, WOFF, TTF oder OTF bis 1 MB. WOFF2 ist am kleinsten und schnellsten. Die Lizenz der Schrift muss die Einbettung im Web erlauben; die Verantwortung dafür trägt die Wehr. Fehlt die fette Datei, berechnet der Browser fetten Text aus der normalen. Die Schrift gilt nur für diese Wehr, die Anmeldung und die Gesamtansicht der VG bleiben bei den Systemschriften.",
      },
      admin_fleet: {
        title: "Fahrzeuge",
        short: "Fahrzeugblöcke der Einsatzübersicht mit Dienstzeitraum.",
        text: "Jedes Fahrzeug ist ein Block der Einsatzübersicht (Stärke, Ausrücken, Eintreffen). Der <b>Funkrufname</b> wird genau so eingetragen, wie er im BKS-Bericht steht, z. B. „FL NR#.ABC 02/45-01“ oder „RP WW 01/23-06“ für ein Fahrzeug des Landes am Standort. Darüber ordnet die App die Fahrzeuge eines Berichts zu; zur Auswahl stehen die Namen aus bisher eingelesenen Berichten der VG. Darunter steht die Auflösung nach dem Funkrufnamenverzeichnis RLP (Kennung, Standort, Kennzahl = Fahrzeugart, laufende Nummer) und der Block, unter dem das Fahrzeug in Einsätzen und im Excel-Export erscheint (z. B. 02/45). Der <b>Fahrzeugtyp</b> ist die Grundlage für den Kostenersatz und muss so heißen wie in der Gebührenordnung (z. B. HLF 20). Zur Auswahl stehen die Typen, die die Kennzahl laut Verzeichnis haben kann, und die Typen der Gebührenordnung. Vorbelegt wird er, wenn nur einer davon in Frage kommt; sonst steht der Hinweis „laut Kennzahl: …“ darunter. Jedes Fahrzeug kann nur einmal in der Liste stehen – für einen alten Eintrag wie 02/45 den Funkrufnamen dort eintragen statt ihn neu hinzuzufügen. <b>Im Dienst ab / außer Dienst ab</b> begrenzen, wann ein Fahrzeug beim Einlesen zugeordnet und als Spalte im Excel-Export des Jahres angezeigt wird – ein ausgemustertes Fahrzeug muss so nicht gelöscht werden, alte Einsätze bleiben vollständig. <b>Ersetzt durch</b> hält fest, welches Fahrzeug nachfolgt. Ohne Haken bei <b>Gesamtstärke</b> zählt die Besatzung nicht zur Gesamtstärke in „Eintreffen und verfügbare Kräfte“. Eigene Fahrzeuge, die in einem Bericht vorkommen, aber noch fehlen, werden beim Übernehmen automatisch angefügt.",
      },
      admin_vg_vehicles: {
        title: "Fahrzeuge der VG",
        short: "Alle Fahrzeuge aller Wehren der VG in einer Tabelle.",
        text: "Bei gewählter Verbandsgemeinde stehen hier die Fahrzeuglisten aller Wehren der VG untereinander, mit denselben Spalten wie bei einer Wehr (Funkrufname, Fahrzeugtyp, Dienstzeitraum, Nachfolger, Gesamtstärke, Reihenfolge, Ersatzfahrzeuge). Über die Spalte <b>Wehr</b> wechselt ein Fahrzeug die Wehr – nur deren Berichte ordnen es als eigenes Fahrzeug zu (Einsatzbeginn, Kostenersatz). Die bisherigen Einsätze mit seinen Daten bleiben bei der alten Wehr unverändert; dort erscheint es nur nicht mehr als Spalte. Darunter stehen die Funkrufnamen aus eingelesenen Berichten, die noch keiner Wehr gehören (weitere wie Rettungsdienst oder Fahrzeuge des Landes aufklappbar). Gespeichert wird alles mit einem Klick; hat sich eine Liste inzwischen geändert (z. B. durch einen Import), bitte neu laden.",
      },
      admin_vg_defaults: {
        title: "Vorgaben der VG",
        short: "Einstellungen, die für alle Wehren der VG gelten.",
        text: "Bei gewählter Verbandsgemeinde legen <b>Allgemein</b>, <b>BKS-Kennung</b> und <b>Orte & Zeitgrenzen</b> die Vorgaben für alle Wehren der VG fest: Farben, Kennung im BKS-Bericht, FEZ, Nummerierung, Orte, Alarmstufe, Zeitgrenzen und Tagesstunden. Je Wehr kommen ihr Standort und ihr Ausrückebereich dazu. Eine neue Wehr übernimmt alle Vorgaben. Eine Wehr kann bei sich abweichen – bei gewählter Wehr steht an jedem Wert „von der VG“ oder „abweichend von der VG“ mit „VG-Wert übernehmen“. Abweichungen sind in der Verbandsgemeinde unter dem jeweiligen Wert aufgeführt; ändert die VG ihre Vorgabe auf denselben Wert, entfällt die Abweichung.",
      },
      admin_bks: {
        title: "BKS-Kennung",
        short: "Woran die App die eigenen Fahrzeuge und Berichte erkennt.",
        text: "<b>Kennung der VG</b> (gilt für alle Wehren der VG) und <b>Standort</b> der Wehr ergeben die Einheit aus der Kopfzeile des Berichts, z. B. „FW NR#.ABC 02“. Darüber werden Berichte der richtigen Wehr zugeordnet, und daraus ergeben sich die Funkrufnamen: „FL NR#.ABC 02/…“ sind eigene Fahrzeuge (deren früheste Alarmierung ist der Einsatzbeginn), „FL NR#.ABC …“ Fahrzeuge der übrigen Wehren der VG. Fahrzeuge der Fahrzeugliste zählen immer als eigene, auch mit anderem Funkrufnamen (z. B. „RP WW …“). <b>FEZ-Kennung</b>: die Feuerwehreinsatzzentrale, deren Einsatzende mitzählt. Ins <b>Testfeld</b> passt beliebiger Text aus einem Bericht – einzelne Funkrufnamen, Zeilen der Fahrzeugtabelle oder der ganze Bericht; die App zeigt, wie sie jedes gefundene Fahrzeug zuordnet.",
      },
      admin_places: {
        title: "Orte und Zeitgrenzen",
        short: "Einsatzgebiete und Ausrückebereich für „Eintreffen und verfügbare Kräfte“.",
        text: "Ein Einsatz gehört zu dem Ort, mit dessen <b>Namen</b> der Einsatzort beginnt (z. B. „Musterstadt-Nord“ → Musterstadt, Groß-/Kleinschreibung egal). Nur Orte mit Haken bei <b>Ausrückebereich</b> zählen für „Eintreffen und verfügbare Kräfte“. Dazu kommen die Mindest-Alarmstufe, die Zeitgrenzen (mehrere möglich, z. B. 8 und 10 Minuten), die zweite Grenze für „Stärke nach … Min.“ und die Stunden, die als Tag gelten. Orte und Zeitgrenzen gibt die Verbandsgemeinde für alle Wehren der VG vor; dort setzt sie auch je Wehr die Haken des Ausrückebereichs.",
      },
      admin_keywords: {
        title: "Stichwortkatalog",
        short: "Stichworte der AAO für die Suche im Feld Stichwort.",
        text: "Den Katalog pflegt die Verbandsgemeinde für alle Wehren der VG; Standard ist die Vorlage der AAO. Bei gewählter Wehr zeigt die Spalte <b>Herkunft</b>, was von der VG kommt. Eine Wehr kann abweichen: Haken <b>gilt hier</b> entfernen (Stichwort gilt in dieser Wehr nicht), Bezeichnung oder Suchbegriffe ändern oder eigene Stichworte ergänzen; ↺ hebt eine Abweichung wieder auf. In der Verbandsgemeinde steht je Stichwort, welche Wehren abweichen. <b>Deaktivierte</b> Stichworte erscheinen nicht mehr in der Suche, alte Einsätze behalten aber ihre Bezeichnung. Ein ganzer Katalog lässt sich als CSV oder Excel (Stichwort, Bezeichnung, Suchbegriffe) einlesen – vorher zeigt die App, was neu ist oder sich ändert.",
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
      admin_sessions: {
        title: "Sitzungen",
        short: "Wer angemeldet ist – Sitzungen einsehen und beenden (nur Superadmin).",
        text: "Zeigt alle gültigen Anmeldungen mit Browser, Anmeldezeit und letzter Aktivität. <b>Abmelden</b> beendet eine Sitzung sofort, auch wenn das Cookie kopiert wurde; <b>Alle dieser Person</b> beendet alle Geräte einer Adresse, <b>Alle anderen abmelden</b> alle außer deiner eigenen. Die Betroffenen können sich mit einem neuen Anmeldelink wieder anmelden. Wer den Zugang ganz verlieren soll, dem entziehst du die Zuordnung unter „Benutzer“. Sitzungen laufen nach 30 Tagen ab; Abmelden beendet die eigene Sitzung auch auf dem Server.",
      },
      admin_roles: {
        title: "Rollen",
        short: "Welche Rolle welche Rechte hat – als Übersicht.",
        text: "Startbestand: <b>Benutzer</b> (nur Auswertung, ohne Namen) → <b>Erfasser</b> (erbt Benutzer; Einsätze, Anwesenheit und Personal, Berichte einlesen, bearbeiten) → <b>Wehrführer</b> (erbt Erfasser; Verwaltung der Wehr, vergibt Erfasser und Benutzer). Für die VG: <b>Statistik VG</b> (z. B. Bürgermeister: Auswertung aller Wehren, ohne Namen) → <b>Wehrleiter</b> (erbt Statistik VG; Einsätze und Verwaltung aller Wehren, Prüfprotokoll, Gebührenordnung, vergibt alle Rollen, pflegt eigene Rollen der VG – sieht aber keine Anwesenheit). Der Wehrleiter kann eigene Rollen für seine VG anlegen, der Superadmin Rollen für alle VGs. Die Tabelle zeigt ● eigene und ○ geerbte Rechte.",
      },
      admin_role_editor: {
        title: "Rolle bearbeiten",
        short: "Bezeichnung, Bereich, Vererbung, Rechte und Verteilung einer Rolle.",
        text: "<b>Bereich</b>: Rolle einer Wehr oder der VG (gilt dann in allen Wehren der VG); er lässt sich nach dem Anlegen nicht ändern. <b>Gilt in</b>: eigene Rolle einer VG oder (nur Superadmin) in allen VGs. <b>Erbt von</b>: die Rolle bekommt alle Rechte und die Verteilung der gewählten Rolle dazu – Änderungen dort wirken mit. Geerbte Rechte lassen sich nicht abwählen; für weniger Rechte von einer kleineren Rolle erben (z. B. Benutzer statt Erfasser). Ein Recht, das ein anderes voraussetzt, setzt dieses mit. <b>Leitplanken</b>: Anwesenheit und Personal gibt es nur für Rollen einer Wehr; Gesamtansicht, Prüfprotokoll, Gebühren und Rollenpflege nur für Rollen der VG. Systemrollen ändert nur der Superadmin, Rollen, die man selbst hat (auch über Vererbung), ändert jemand anderes. Löschen lässt sich eine Rolle erst, wenn sie niemand mehr hat und keine Rolle von ihr erbt. Änderungen gelten sofort.",
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
        short: "Kennzahlen, Diagramme und „Eintreffen und verfügbare Kräfte“ (wenn freigegeben) – ohne Namen.",
        text: "Kennzahlen, Diagramme und „Eintreffen und verfügbare Kräfte“ (wenn freigegeben) – ohne Namen.",
      },
      perm_plan_view: {
        title: "Eintreffen und Kräfte ohne Freigabe sehen",
        short: "Die Auswertung „Eintreffen und verfügbare Kräfte“ einer Wehr ist sichtbar, auch solange die Wehr sie nicht für alle freigegeben hat.",
        text: "Die Auswertung „Eintreffen und verfügbare Kräfte“ einer Wehr ist sichtbar, auch solange die Wehr sie nicht für alle freigegeben hat.",
      },
      perm_plan_release: {
        title: "Eintreffen und Kräfte freigeben",
        short: "Schalter „für alle freigegeben“ in der Auswertung bzw. unter Orte & Zeitgrenzen.",
        text: "Schalter „für alle freigegeben“ in der Auswertung bzw. unter Orte & Zeitgrenzen.",
      },
      perm_incidents_view: {
        title: "Einsätze ansehen",
        short: "Einsatzliste, einzelne Einsätze und Hinweise – ohne Anwesenheit, wenn das Recht dafür fehlt.",
        text: "Einsatzliste, einzelne Einsätze und Hinweise – ohne Anwesenheit, wenn das Recht dafür fehlt.",
      },
      perm_incidents_export: {
        title: "Excel-Export",
        short: "Einsatzübersicht als Excel; die Anwesenheit nur mit dem Recht „Anwesenheit und Personal sehen“.",
        text: "Einsatzübersicht als Excel; die Anwesenheit nur mit dem Recht „Anwesenheit und Personal sehen“.",
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
        title: "Anwesenheit und Personal sehen",
        short: "Namen der Personen, Anwesenheit je Einsatz und Reiter Personal.",
        text: "Namen der Personen, Anwesenheit je Einsatz und Reiter Personal. In einer Rolle der VG gilt das für alle Wehren der VG – nur bei Funktionen vergeben, die diese Namen wirklich brauchen.",
      },
      perm_people_edit: {
        title: "Anwesenheit bearbeiten",
        short: "Anwesenheit eines Einsatzes ändern und Personen ergänzen.",
        text: "Anwesenheit eines Einsatzes ändern und Personen ergänzen. In einer Rolle der VG gilt das für alle Wehren der VG.",
      },
      perm_tenant_settings: {
        title: "Einstellungen, Fahrzeuge, Farben, Logos und Schrift",
        short: "Fahrzeuge, BKS-Kennung, Orte, Zeitgrenzen, Farben und Logos. In einer Rolle der VG: Vorgaben für alle Wehren der VG.",
        text: "Name, Farben, Logos, Schrift, Fahrzeuge, BKS-Kennung, Orte und Zeitgrenzen. In einer Rolle der Wehr: Werte und Abweichungen dieser Wehr von den Vorgaben der VG. In einer Rolle der VG: die Vorgaben für alle Wehren der VG und die Fahrzeuge aller Wehren.",
      },
      perm_tenant_keywords: {
        title: "Stichwortkatalog",
        short: "Stichworte ergänzen, ändern, deaktivieren oder einlesen – in einer Rolle der VG für alle Wehren der VG.",
        text: "Stichworte ergänzen, ändern, deaktivieren oder einlesen. In einer Rolle der Wehr: Abweichungen vom Katalog der VG (Stichwort gilt hier nicht, eigene Bezeichnung, eigene Stichworte). In einer Rolle der VG: der Katalog für alle Wehren der VG.",
      },
      perm_vg_overview: {
        title: "Gesamtansicht der VG",
        short: "Auswahl „Verbandsgemeinde · …“ oben: Auswertung aller Wehren der VG zusammen. Nur für Rollen der VG.",
        text: "Auswahl „Verbandsgemeinde · …“ oben: Auswertung aller Wehren der VG zusammen. Nur für Rollen der VG.",
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
    remember("changelog_seen", changelogVersion(CHANGELOG[0]));
    markNews();
  }
  if (tab === "feedback") $("#feedback-form textarea").focus();
}

// ------------------------------------------------------------ Neuigkeiten
/** Stand eines Eintrags für „ungelesen“: `version` (mehrere Einträge am selben Tag), sonst das Datum. */
const changelogVersion = (entry) => entry.version || entry.date;

function changelogContent() {
  return CHANGELOG.map((v) => `<section class="help-section">
    <h3>${formatDate(v.date)}</h3>
    <ul class="changelog">${v.items.map((i) => `<li>${i}</li>`).join("")}</ul>
  </section>`).join("");
}

/** Punkt am ?-Symbol im Kopf, solange es ungelesene Neuigkeiten gibt. */
function markNews() {
  const unseen = changelogVersion(CHANGELOG[0]) > (recall("changelog_seen") || "");
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

/** Start (aus app.js, sobald $ und config da sind): Kopf-Symbol, Reiter, Feedback. Die Hilfe ist eine gesammelte: das ? im Kopf. */
function setupHelp() {
  markNews();
  $("#btn-help").addEventListener("click", () => openHelp(helpContext()));
  $("#help-tabs").addEventListener("click", (e) => {
    const button = e.target.closest("[data-help-tab]");
    if (button) showHelpTab(button.dataset.helpTab);
  });
  $("#feedback-form").addEventListener("submit", (e) => { e.preventDefault(); sendFeedback(e.target); });
  $("#feedback-form").addEventListener("input", () => { $("#feedback-status").hidden = true; });
}
