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
        title: () => `Stärke nach ${helpLimit()} Min.`,
        short: "Zusätzliche Kräfte, die bis zur Zeitgrenze nachgekommen sind.",
        text: () => `Summe der Besatzung der Fahrzeuge, die nach dem ersten Fahrzeug, aber noch innerhalb der Zeitgrenze (${helpLimits()} Minuten) eingetroffen sind.`,
      },
      crew_within_second: {
        title: () => `Stärke nach ${config.second_limit} Min.`,
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
        text: "Automatisch erzeugte Hinweise, z. B. fehlender Einheitsführer, nicht ermittelbarer Beginn/Ende oder Fahrzeuge, die keinem Block der Einsatzübersicht zugeordnet sind. Berichte ohne Prüfhinweise, ohne neue Personen und ohne Abweichungen werden beim Einlesen direkt übernommen; nur die übrigen erscheinen zur Kontrolle. Hinweise verhindern das Übernehmen nicht.",
      },
      attendance: {
        title: "Anwesenheit",
        short: "Alle Personen laut Anwesenheitsliste des Berichts.",
        text: "Personen aus der Anwesenheitsliste des Berichts, mit Fahrzeug und Funktion. Namen werden mit den bekannten Kameraden abgeglichen; unbekannte Namen sind markiert und werden beim Übernehmen als neue Kameraden angelegt. Beim Bearbeiten und in der Vorschau trägt ein Klick auf einen Namen die Person als EHF ein; der EHF ist dunkelrot hervorgehoben.",
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
        text: () => `Zuordnung nach dem Anfang des Ortsnamens${config.places.length ? ` (z. B. „${esc(config.places[0])}-…“ → ${esc(config.places[0])})` : ""}. Orte außerhalb der bekannten Liste erscheinen als „sonstige“.`,
      },
      participations: {
        title: "Einsätze und Beteiligungen (alle Wehren)",
        short: "Große Zahl: Einsätze ohne Doppelte. Beteiligungen: Summe der Einsätze aller Wehren.",
        text: "In der Gesamtansicht einer Verbandsgemeinde zählt ein Einsatz, an dem mehrere Wehren beteiligt waren, bei jeder Wehr (Beteiligungen). Die große Zahl zählt ihn nur einmal: Einsätze mit demselben Stammdatensatz im BKS-Portal oder derselben Einsatznummer der Leitstelle gelten als ein Einsatz. Einsätze ohne beides (z. B. aus der früheren Excel-Übersicht) zählen einzeln. Alle übrigen Kennzahlen und Diagramme summieren die Beteiligungen; der Bedarfsplan wertet jede Wehr mit ihren eigenen Orten aus. Über die Schaltflächen oben lässt sich die Auswertung auf einzelne Wehren einschränken.",
      },
    },
  },
  {
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
        short: "Abgleich je Einsatz über alle Wehren der VG (nur Wehrleiter).",
        text: "Für jeden Einsatz mit Stammdatensatz vergleicht das Protokoll die Zeiten der Leitstelle mit den Berichten der Wehren. „Als geprüft markieren“ gilt für den jetzigen Stand: Kommt ein neuer Befund hinzu (z. B. ein geänderter Bericht), ist der Einsatz wieder offen. „Drucken / PDF“ druckt die angezeigten Einsätze mit ihren Befunden.",
      },
      fees: {
        title: "Kostenersatz",
        short: "Kostenaufstellung nach der Gebührenordnung der VG (nur Wehrleiter).",
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
    title: "Verwaltung",
    intro: "Nur für Wehrführer, Wehrleiter und Superadmins. Änderungen gelten sofort für alle Benutzer der Wehr.",
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
        text: "Jedes Fahrzeug ist ein Block der Einsatzübersicht (Stärke, Ausrücken, Eintreffen). Der <b>Funkrufname</b> wird genau so eingetragen, wie er im BKS-Bericht steht, z. B. „FL NR#.ABC 02/45-01“ oder „RP WW 01/23-06“ für ein Fahrzeug des Landes am Standort. Darüber ordnet die App die Fahrzeuge eines Berichts zu; zur Auswahl stehen die Namen aus bisher eingelesenen Berichten der VG. Darunter steht die Auflösung nach dem Funkrufnamenverzeichnis RLP (Kennung, Standort, Kennzahl = Fahrzeugart, laufende Nummer) und der Block, unter dem das Fahrzeug in Einsätzen und im Excel-Export erscheint (z. B. 02/45). Der <b>Fahrzeugtyp</b> wird vorbelegt, wenn die Kennzahl eindeutig ist; er muss zur Gebührenordnung passen (z. B. HLF 20). <b>Im Dienst ab / außer Dienst ab</b> begrenzen, wann ein Fahrzeug beim Einlesen zugeordnet und als Spalte im Excel-Export des Jahres angezeigt wird – ein ausgemustertes Fahrzeug muss so nicht gelöscht werden, alte Einsätze bleiben vollständig. <b>Ersetzt durch</b> hält fest, welches Fahrzeug nachfolgt. Ohne Haken bei <b>Bedarfsplan</b> zählt die Besatzung nicht zur Gesamtstärke des Bedarfsplans. Eigene Fahrzeuge, die in einem Bericht vorkommen, aber noch fehlen, werden beim Übernehmen automatisch angefügt.",
      },
      admin_bks: {
        title: "BKS-Kennung",
        short: "Woran die App die eigenen Fahrzeuge und Berichte erkennt.",
        text: "<b>Einheiten-Präfix</b>: Anfang der Fahrzeugnamen der Einheit im Bericht, z. B. „FL NR#.ABC “ (mit Leerzeichen). <b>Eigener Präfix</b>: Funkrufnamen der eigenen Wehr, z. B. „02/“ – deren früheste Alarmierung ist der Einsatzbeginn. Fahrzeuge der Fahrzeugliste zählen immer als eigene, auch mit anderem Präfix (z. B. „RP WW …“). <b>Einheit im Bericht</b>: Kopfzeile des Berichts, z. B. „FW NR#.ABC 02“ – darüber werden Berichte in der Gesamtansicht der richtigen Wehr zugeordnet. <b>FEZ-Kennung</b>: die Feuerwehreinsatzzentrale, deren Einsatzende mitzählt. Mit dem Testfeld lässt sich eine Zeile aus einem Bericht prüfen.",
      },
      admin_places: {
        title: "Orte und Bedarfsplan",
        short: "Einsatzgebiete und Ausrückebereich des Feuerwehrbedarfsplans.",
        text: "Ein Einsatz gehört zu dem Ort, dessen <b>Namensanfang</b> zum Ortsnamen im Bericht passt (Groß-/Kleinschreibung egal). Nur Orte mit Haken bei <b>Bedarfsplan</b> zählen für den Erreichungsgrad. Dazu kommen die Mindest-Alarmstufe, die Zeitgrenzen (mehrere möglich, z. B. 8 und 10 Minuten), die zweite Grenze für „Stärke nach … Min.“ und die Stunden, die als Tag gelten.",
      },
      admin_keywords: {
        title: "Stichwortkatalog",
        short: "Stichworte der AAO für die Suche im Feld Stichwort.",
        text: "Standard ist die Vorlage der AAO. Sobald ein Stichwort ergänzt, geändert oder gelöscht wird, hat die Wehr ihren eigenen Katalog. <b>Deaktivierte</b> Stichworte erscheinen nicht mehr in der Suche, alte Einsätze behalten aber ihre Bezeichnung. Ein ganzer Katalog lässt sich als CSV oder Excel (Stichwort, Bezeichnung, Suchbegriffe) einlesen – vorher zeigt die App, was neu ist oder sich ändert.",
      },
      dpa: {
        title: "Auftragsverarbeitung (AVV)",
        short: "Vertrag nach Art. 28 DSGVO zwischen VG und Betreiber.",
        text: "Die Verbandsgemeinde ist als Träger der Feuerwehr für die Daten verantwortlich, der Betreiber der App verarbeitet sie in ihrem Auftrag. Ablauf: Angaben des Auftraggebers ausfüllen → der Vertrag wird aus der Vorlage erzeugt (mit Prüfsumme des Textes) → drucken und unterschreiben lassen → unterschriebenes PDF hochladen und/oder einen Link zur Ablage der VG eintragen → der Betreiber bestätigt. Bis dahin sind die Einsatzdaten der Wehren dieser VG gesperrt. Ausfüllen dürfen Wehrleitung, Statistik VG und Wehrführer; hochgeladene Dateien werden nie überschrieben, alle Schritte werden protokolliert.",
      },
      admin_roles: {
        title: "Rollen",
        short: "Wer was sehen und ändern darf.",
        text: "<b>Wehrführer</b>: Einsätze und Personal der Wehr, Berichte einlesen, Verwaltung der Wehr, vergibt Erfasser und Benutzer. <b>Erfasser</b>: Einsätze und Personal, Berichte einlesen und bearbeiten. <b>Benutzer</b>: nur die Auswertung, ohne Namen. <b>Wehrleiter</b> (VG): wie Wehrführer für alle Wehren der VG, mit Gesamtansicht, vergibt alle Rollen der VG. <b>Statistik VG</b> (z. B. Bürgermeister): nur die Auswertung aller Wehren der VG, ohne Namen. Wer keine Zuordnung mehr hat, ist beim nächsten Aufruf abgemeldet.",
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
  return HELP_SECTIONS.map((s) => `<section class="help-section">
    <h3>${s.title}</h3>${s.intro ? `<p class="muted">${s.intro}</p>` : ""}
    <dl class="help-list">${Object.entries(s.entries).map(([k, e]) =>
      `<div id="help-${k}"><dt>${helpValue(e.title)}</dt><dd>${helpValue(e.text)}</dd></div>`).join("")}</dl>
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
