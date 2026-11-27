"use strict";

// Auswertungen aus den Angaben des BKS-Berichts: „Abbrüche & Anlagen“, „Fahrzeuge & Atemschutz“, „Brand & Rettung“.
// Wird nach analysis.js geladen (nutzt dessen Bausteine) und trägt sich in VIEWS ein; Reiter stehen in NAV (app.js).
// Daten aus /api/evaluation: aborts, alarm_systems, vehicle_usage, respiratory, fire_course, casualties.
// Grundsatz wie dort: „nicht angegeben“ ist nie null – jede Kennzahl nennt, für wie viele Einsätze sie vorliegt.

VIEWS.aborts = { label: "Abbrüche & Anlagen", sub: "Abbrüche & Anlagen", load: loadEvaluation, render: renderAborts, permission: "stats.view",
  help: "sec_aborts" };
VIEWS.resources = { label: "Fahrzeuge & Atemschutz", sub: "Fahrzeuge & Atemschutz", load: loadEvaluation, render: renderResources, permission: "stats.view",
  help: "sec_resources" };
VIEWS.fire = { label: "Brand & Rettung", sub: "Brand & Rettung", load: loadEvaluation, render: renderFire, permission: "stats.view",
  help: "sec_fire" };

const ABORT_LONG = { false_alarm: "Täuschung, technischer oder böswilliger Alarm, kein Ereignis" };
const shareOfKnown = (part, total) => total ? percent(part / total) : "–";
const NOT_STATED = "ältere Berichte erneut einlesen, damit die Angabe übernommen wird";

// ------------------------------------------------------------ Abbrüche & Anlagen
function abortKindsCard(a) {
  const items = a.kinds.map((k) => ({ label: k.label, value: k.count, text: `${k.count} · ${percent(k.share)}`, link: k.count ? listLink({ abort: k.kind }) : null,
    tip: `${k.label}: ${k.count} von ${a.aborted} abgebrochenen Einsätzen` }));
  const table = dataTable(["Grund", "Einsätze", "Anteil der Abbrüche"], a.kinds.map((k) => [esc(k.label), countLink(k.count, { abort: k.kind }), percent(k.share)]));
  return chartCard({ id: "abort-kinds", title: `Warum wurden Einsätze abgebrochen?`,
    subtitle: "Gruppen nach dem Freitext „Einsatzabbruch“ des BKS-Berichts. Ein Abbruch heißt: Das Fahrzeug musste die Einsatzstelle nicht mehr erreichen.",
    chart: a.aborted ? barChart(items) : `<p class="empty-note">Im Jahr ${state.year} wurde kein Einsatz abgebrochen.</p>`, table });
}

function abortReasonsCard(a) {
  const label = Object.fromEntries(a.kinds.map((k) => [k.kind, k.label]));
  const rows = a.reasons.map((r) => [esc(r.reason), esc(label[r.kind] || ""), r.count]);
  return plainCard("Häufigste Gründe", "Wortlaut aus dem Bericht, gleiche Schreibweisen zusammengefasst",
    rows.length ? dataTable(["Grund laut Bericht", "Gruppe", "Einsätze"], rows) : `<p class="empty-note">Keine Abbrüche.</p>`);
}

function abortCategoriesCard(a) {
  const items = a.categories.map((c) => ({ label: c.name, value: c.aborted, text: `${c.aborted}/${c.count} · ${percent(c.share)}`,
    tip: `${c.name}: ${c.aborted} von ${c.count} Einsätzen abgebrochen` }));
  const table = dataTable(["Einsatzart", "Einsätze", "abgebrochen", "Anteil"], a.categories.map((c) => [esc(c.name), c.count, c.aborted, percent(c.share)]));
  return chartCard({ id: "abort-categories", title: "Abbrüche nach Einsatzart",
    subtitle: "Bei welchen Einsatzarten kommt es besonders oft vor, dass die Einheit nicht mehr gebraucht wird?",
    chart: items.length ? barChart(items) : "", table });
}

function alarmSystemsCard(s, a) {
  const f = a.fire_alarm_systems;
  const name = (r) => !r.known ? "ohne Angabe von Anlage oder Objekt" : [r.building, r.system && `Anlage ${r.system}`].filter(Boolean).join(" · ");
  const key = (r) => r.system || (r.building || "").trim() || "-";
  const rows = s.rows.map((r) => [esc(name(r)), countLink(r.count, { system: key(r) }), r.false_alarms, r.false_share == null ? "–" : percent(r.false_share), formatDate(r.last)]);
  const items = s.rows.filter((r) => r.known).slice(0, 12).map((r) => ({ label: name(r), value: r.count,
    text: r.false_alarms ? `${r.count} · ${r.false_alarms} Fehlalarm` : String(r.count), link: listLink({ system: key(r) }), tip: `${name(r)}: ${r.count} Einsätze, ${r.false_alarms} Fehlalarme` }));
  return chartCard({ id: "alarm-systems", title: `Brandmeldeanlagen`,
    subtitle: `Einsätze an Brandmeldeanlagen je Anlage bzw. Objekt – wenige Anlagen verursachen oft die meisten Alarme. ${esc(coverageText(s.identified, s.total))} mit Angabe von Anlage oder Objekt.`,
    chart: items.length ? barChart(items) : `<p class="empty-note">Keine Einsätze mit bekannter Anlage oder bekanntem Objekt${s.total ? ` – ${NOT_STATED}` : ""}.</p>`,
    table: dataTable(["Anlage / Objekt", "Einsätze", "Fehlalarme", "Anteil Fehlalarm", "zuletzt"], rows),
    extra: f.count ? `<p class="small muted section-gap">Alle Einsätze mit Stichwort B2.07: ${f.count}, davon ${f.aborted} abgebrochen (${f.false_alarms} als Fehlalarm).</p>` : "" });
}

function renderAborts() {
  const e = state.evaluation, a = e.aborts, s = e.alarm_systems, f = a.fire_alarm_systems;
  const kind = (key) => a.kinds.find((k) => k.kind === key)?.count ?? 0;
  $("#view-aborts").innerHTML = evaluationToolbar({ exports: false }) + `<div class="kpis kpis-4">
    ${analysisKpi(`Abgebrochene Einsätze`, a.aborted, esc(`${a.total ? percent(a.share) : "–"} von ${a.total} Einsätzen`), { abort: "any" })}
    ${analysisKpi("Fehlalarme", kind("false_alarm"), esc(ABORT_LONG.false_alarm), { abort: "false_alarm" })}
    ${analysisKpi(`An Brandmeldeanlagen`, f.count, esc(f.count ? `${shareOfKnown(f.aborted, f.count)} abgebrochen` : "keine Einsätze mit B2.07"), { system: "any" })}
    ${analysisKpi("In Bereitstellung / nicht erforderlich", kind("standby") + kind("not_needed"), esc(`${plural(kind("standby"), "Einsatz", "Einsätze")} in Bereitstellung`), { abort: "standby,not_needed" })}
  </div>
  <div class="grid grid-2">${abortKindsCard(a)}${abortCategoriesCard(a)}</div>
  <div class="grid">${alarmSystemsCard(s, a)}</div>
  <div class="grid">${abortReasonsCard(a)}</div>`;
}

// ------------------------------------------------------------ Fahrzeuge & Atemschutz
const vehicleName = (u) => u.label ? `${u.call_sign} · ${u.label}` : u.call_sign;

function vehicleUsageCard(v) {
  const unknown = v.rows.reduce((n, u) => n + u.unknown, 0), alerted = v.rows.reduce((n, u) => n + u.alerted, 0);
  const items = v.rows.map((u) => ({ label: vehicleName(u), value: u.drove, link: u.alerted ? listLink({ vehicle: u.call_sign }) : null,
    text: `${u.drove}${u.standby ? ` · ${u.standby}× bereit` : ""}`,
    tip: `${vehicleName(u)}: ${u.alerted} Alarmierungen, ${u.drove} Ausfahrten, ${u.deployed} eingesetzt, ${u.standby} nur bereitgestellt` }));
  const rows = v.rows.map((u) => [esc(vehicleName(u)), countLink(u.alerted, { vehicle: u.call_sign }), u.drove, u.deployed, u.standby, u.standby_share == null ? "–" : percent(u.standby_share),
    u.minutes_valid ? `${num(u.hours, 0)} h` : "–", u.crew_avg == null ? "–" : num(u.crew_avg)]);
  return chartCard({ id: "vehicle-usage", title: `Fahrzeugnutzung`,
    subtitle: "Wie oft wurde jedes Fahrzeug alarmiert, ist ausgerückt und tatsächlich eingesetzt worden? Grundlage für Alarm- und Ausrückeordnung und Beschaffung.",
    chart: items.length ? barChart(items) : `<p class="empty-note">Keine Fahrzeuge im Jahr ${state.year}.</p>`,
    table: dataTable(["Fahrzeug", "Alarmiert", "Ausgerückt", "Eingesetzt", "Nur bereit", "Anteil nur bereit", "Einsatzstunden", "Ø Besatzung"], rows),
    extra: `<p class="small muted section-gap">„Nur bereit“ = laut Bericht alarmiert, aber nicht eingesetzt (z. B. in Bereitstellung).${unknown
      ? ` Bei ${unknown} von ${alerted} Alarmierungen fehlt die Angabe – ${NOT_STATED}.` : ""} Einsatzstunden: Alarmierung bis Einsatzende des Fahrzeugs, nur ausgerückte Fahrzeuge.</p>` });
}

function respiratoryCard(r) {
  const body = r.known ? keyFigures([
    [r.with_agt ? `<a href="${esc(listLink({ agt: 1 }))}">${r.with_agt} von ${r.known}</a>` : `${r.with_agt} von ${r.known}`, "Einsätze mit Atemschutz"], [r.carriers, "Geräteträger (Stärke der Fahrzeuge)"],
    [r.persons, "Personen mit Atemschutzzeit"], [`${r.minutes} min`, "Minuten unter Atemschutz"],
    [r.average_minutes == null ? "–" : `${num(r.average_minutes)} min`, "je Person im Mittel"],
    [r.longest_minutes == null ? "–" : `${r.longest_minutes} min`, "längster Einsatz einer Person"]])
    : `<p class="empty-note">Keine Angaben zum Atemschutz – ${NOT_STATED}.</p>`;
  return `<div class="card"><div class="card-header"><div><h3>Atemschutz</h3>
    <p class="muted">Geräteträger je Fahrzeug und Minuten unter Atemschutz je Person laut Anwesenheitsliste. ${esc(coverageText(r.known, r.total))}.</p></div></div>
    ${body}</div>`;
}

function renderResources() {
  const e = state.evaluation, v = e.vehicle_usage, r = e.respiratory;
  const alerted = v.rows.reduce((n, u) => n + u.alerted, 0), standby = v.rows.reduce((n, u) => n + u.standby, 0);
  const known = v.rows.reduce((n, u) => n + u.known, 0);
  $("#view-resources").innerHTML = evaluationToolbar({ exports: false }) + `<div class="kpis kpis-4">
    ${analysisKpi(`Fahrzeug-Alarmierungen`, alerted, esc(`${plural(v.rows.length, "Fahrzeug", "Fahrzeuge")} in ${plural(v.total, "Einsatz", "Einsätzen")}`), ALL_INCIDENTS)}
    ${analysisKpi("Nur bereitgestellt", standby, esc(known ? `${percent(standby / known)} der Alarmierungen mit Angabe` : "keine Angabe vorhanden"), ALL_INCIDENTS)}
    ${analysisKpi(`Einsätze mit Atemschutz`, r.known ? r.with_agt : "–", esc(r.known ? `${shareOfKnown(r.with_agt, r.known)} von ${r.known} Einsätzen mit Angabe` : "keine Angabe vorhanden"), { agt: 1 })}
    ${analysisKpi("Minuten unter Atemschutz", r.known ? r.minutes : "–", esc(r.average_minutes == null ? "keine Zeiten erfasst" : `Ø ${num(r.average_minutes)} min je Person`), { agt: 1 })}
  </div>
  <div class="grid">${vehicleUsageCard(v)}</div><div class="grid">${respiratoryCard(r)}</div>`;
}

// ------------------------------------------------------------ Brand & Rettung
function fireTimesCard(f) {
  const rows = [distributionRow("Eintreffen bis „Brand unter Kontrolle“", f.to_control), distributionRow("Eintreffen bis „Feuer aus“", f.to_out)];
  const items = [["Unter Kontrolle", f.to_control], ["Feuer aus", f.to_out]].flatMap(([label, d]) => [
    { label: `${label} · Median`, value: d.median ?? 0, text: minutes(d.median), tip: `${label}: Median ${minutes(d.median)}, ${coverageText(d.valid, d.total)}` },
    { label: `${label} · 90 %`, value: d.p90 ?? 0, text: minutes(d.p90), tip: `${label}: 90 % höchstens ${minutes(d.p90)}` }]);
  return chartCard({ id: "fire-times", title: `Brandverlauf`,
    subtitle: `Zeit ab Eintreffen des ersten Fahrzeugs bei Brandeinsätzen (Einsatzart B, ohne Abbrüche, Brandmeldeanlagen und Brandsicherheitswachen). ${esc(coverageText(f.to_control.valid, f.total))} mit „Brand unter Kontrolle“.`,
    chart: f.total ? barChart(items) : `<p class="empty-note">Keine Brandeinsätze im Jahr ${state.year}.</p>`,
    table: dataTable(DISTRIBUTION_HEAD, rows) });
}

function fireTacticsCard(f) {
  const rows = f.tactics.map((t) => [esc(t.tactic), t.count, minutes(t.control.median), minutes(t.control.p90)]);
  const watch = f.fire_watches ? `${plural(f.fire_watches, "Brandwache", "Brandwachen")}${f.fire_watch_hours != null
    ? ` mit zusammen ${num(f.fire_watch_hours)} Stunden (Feuer aus bis Ende der Brandwache, ${f.fire_watch_valid} von ${f.fire_watches} mit Angabe)` : ""}` : "Keine Brandwachen";
  return plainCard(`Einsatztaktik und Brandwache`, "Außen- oder Innenangriff laut Bericht und Zeit bis „Brand unter Kontrolle“",
    `${rows.length ? dataTable(["Taktik", "Einsätze", "bis unter Kontrolle (Median)", "90 % höchstens"], rows) : `<p class="empty-note">Keine Angaben zur Einsatztaktik.</p>`}
     <p class="small muted section-gap">${esc(watch)}.</p>`);
}

const CASUALTY_LABELS = { rescued: "Menschen gerettet", rescued_animals: "Tiere gerettet", injured: "Verletzte (andere Personen)",
  injured_firefighters: "Verletzte Feuerwehrangehörige", deceased: "Verstorbene" };

function casualtiesCard(c) {
  const rows = Object.entries(CASUALTY_LABELS).map(([key, label]) => {
    const f = c.fields[key];
    return [esc(label), f.total, countLink(f.incidents, { casualty: key }), `${f.reported} von ${c.total}`];
  });
  const items = Object.entries(CASUALTY_LABELS).map(([key, label]) => ({ label, value: c.fields[key].total,
    tip: `${label}: ${c.fields[key].total} in ${plural(c.fields[key].incidents, "Einsatz", "Einsätzen")}` }));
  return chartCard({ id: "casualties", title: `Menschenrettung und Personenschäden`,
    subtitle: `Summe aus den Angaben der Berichte. ${c.incidents_with_persons} von ${c.total} Einsätzen mit mindestens einer Angabe größer null; „nicht angegeben“ zählt nicht als null.`,
    chart: barChart(items), table: dataTable(["Angabe", "Summe", "Einsätze (größer null)", "Berichte mit Angabe"], rows) });
}

function renderFire() {
  const e = state.evaluation, f = e.fire_course, c = e.casualties;
  $("#view-fire").innerHTML = evaluationToolbar({ exports: false }) + `<div class="kpis kpis-4">
    ${analysisKpi(`Brandeinsätze`, f.total, "ohne Abbrüche, Brandmeldeanlagen, Brandwachen", { fire: 1 })}
    ${analysisKpi("Bis „Brand unter Kontrolle“", minutes(f.to_control.median), esc(`Median ab Eintreffen · ${coverageText(f.to_control.valid, f.total)}`), { fire: 1 })}
    ${analysisKpi("Menschen gerettet", c.fields.rescued.total, esc(`in ${plural(c.fields.rescued.incidents, "Einsatz", "Einsätzen")}`), { casualty: "rescued" })}
    ${analysisKpi("Verletzte", c.fields.injured.total + c.fields.injured_firefighters.total, esc(`${c.fields.injured_firefighters.total} davon Feuerwehrangehörige`), { casualty: "injured,injured_firefighters" })}
  </div>
  <div class="grid grid-2">${fireTimesCard(f)}${fireTacticsCard(f)}</div><div class="grid">${casualtiesCard(c)}</div>`;
}
