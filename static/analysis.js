"use strict";

// Übersicht und die Auswertungen „Zeiten & Kräfte“ und „Belastung“. Wird nach app.js geladen und trägt sich in VIEWS ein
// (Reiter und Unterreiter stehen in NAV, app.js). Die Daten kommen aus /api/evaluation (timing, workload, coverage).
// Grundsatz: Fehlende Angaben sind nicht null – jede Kennzahl nennt, für wie viele Einsätze sie berechnet wurde.

const INCIDENT_UNIT = ["Einsätze", "Einsätzen"], VEHICLE_UNIT = ["Fahrzeuge", "Fahrzeugen"];
const SMALL_SAMPLE_NOTE = "Weniger als 5 Einsätze – wenig belastbar";

VIEWS.overview = { label: "Übersicht", load: loadOverview, render: renderOverview, permission: "stats.view", help: "sec_overview" };
VIEWS.times = { label: "Zeiten & Kräfte", sub: "Zeiten & Kräfte", load: loadEvaluation, render: renderTimes, permission: "stats.view",
  help: "sec_times" };
VIEWS.load = { label: "Belastung", sub: "Belastung", load: loadEvaluation, render: renderWorkload, permission: "stats.view",
  help: "sec_load" };

// ------------------------------------------------------------ Bausteine
const analysisKpi = (title, value, sub) =>
  `<div class="kpi"><span class="kpi-title">${title}</span><span class="kpi-value">${value}</span><span class="kpi-sub">${sub}</span></div>`;

/** „42 von 57 Einsätzen auswertbar“ – mit Hinweis, wenn Angaben fehlen. */
function coverageText(valid, total, unit = INCIDENT_UNIT) {
  if (!total) return `keine ${unit[0]}`;
  return valid === total ? `alle ${total} ${unit[0]} auswertbar` : `${valid} von ${total} ${unit[1]} auswertbar`;
}

const round1 = (v) => v == null ? null : Math.round(v * 10) / 10;
const shareText = (count, total) => total ? `${percent(count / total)} der Einsätze` : "–";

// Leerzustand statt Gerüst aus Strichen und leeren Achsen: sagt, was fehlt und was zu tun ist
const noIncidentsCard = () => `<div class="card"><p class="empty-note">Im Jahr ${state.year} sind noch keine Einsätze erfasst. Mit „Bericht einlesen“ oben lassen sich Einsatzberichte aus dem BKS-Portal übernehmen; danach erscheint diese Auswertung.</p></div>`;

function notReleased() {
  const hidden = state.evaluation.response_plan_hidden;
  return `<div class="card"><p class="muted">Diese Auswertung ist${hidden.length ? ` für ${esc(hidden.join(", "))}` : ""} noch nicht freigegeben.
    ${config.tenant && can("plan.release") ? "Die Freigabe steht unter Einsatzgeschehen → Eintreffen und verfügbare Kräfte." : "Sie wird von der Wehrführung freigegeben."}</p></div>`;
}

// ------------------------------------------------------------ Übersicht
async function loadOverview() {
  await loadEvaluation();
  if (can("incidents.view")) await loadIncidents();
}

function openTasks(e) {
  const tasks = [];
  const incidents = state.incidents?.incidents;
  if (incidents) {
    const warned = incidents.filter((i) => i.current_warnings?.length).length;
    if (warned) tasks.push({ text: plural(warned, "Einsatz hat", "Einsätze haben") + " Prüfhinweise", link: listLink({ warn: 1 }) });
  }
  const gaps = [];
  for (const row of e.coverage.rows) {
    const missing = e.coverage.total - row.valid;
    if (!missing || (row.key === "leader" && !can("people.view"))) continue;
    gaps.push({ key: row.key, missing, text: `${plural(missing, "Einsatz", "Einsätze")} ${MISSING_LABELS[row.key]}`, link: incidents ? listLink({ missing: row.key }) : null });
  }
  // Viele fehlende Angaben zu einer Aufgabe bündeln statt sechs Zeilen mit fast derselben Zahl
  if (gaps.length > 2) {
    const same = gaps.every((g) => g.missing === gaps[0].missing);     // gleiche Zahl: einmal vorn nennen, sonst je Angabe
    tasks.push({ text: same ? `Angaben fehlen bei ${plural(gaps[0].missing, "Einsatz", "Einsätzen")}:` : `Fehlende Angaben bei bis zu ${plural(Math.max(...gaps.map((g) => g.missing)), "Einsatz", "Einsätzen")}:`,
      parts: gaps.map((g) => ({ text: same ? COVERAGE_SHORT[g.key] : `${COVERAGE_SHORT[g.key]} (${g.missing})`, link: g.link })) });
  } else {
    tasks.push(...gaps);
  }
  const notices = typeof records === "undefined" ? [] : records.notices;
  if (notices.length) tasks.push({ text: plural(notices.length, "Hinweis", "Hinweise") + " an die Wehr", notices: true });
  return tasks;
}

function openTasksCard(e) {
  const tasks = openTasks(e);
  const link = (t) => t.link ? `<a href="${esc(t.link)}">${esc(t.text)}</a>` : esc(t.text);
  const items = tasks.map((t) => `<li>${t.parts ? `${esc(t.text)} ${t.parts.map(link).join(", ")}` : link(t)}${t.notices
    ? ` <button type="button" class="btn btn-light btn-small" data-overview-notices>Anzeigen</button>` : ""}</li>`).join("");
  return `<div class="card"><div class="card-header"><div><h2>Offene Aufgaben</h2>
    <p class="muted">Was im Jahr ${state.year} noch Aufmerksamkeit braucht – ein Klick zeigt die betroffenen Einsätze.</p></div></div>
    ${tasks.length ? `<ul class="task-list">${items}</ul>` : `<p class="all-clear"><span class="record-status ok">Nichts offen</span> Alle Einsätze des Jahres sind vollständig erfasst.</p>`}</div>`;
}

const COVERAGE_LABELS = {
  duration: "Einsatzdauer (Beginn und Ende)", turnout: "Ausrücken eines eigenen Fahrzeugs", arrival: "Eintreffen eines eigenen Fahrzeugs",
  crew: "Besatzung der Fahrzeuge", attendance: "Anwesenheit", leader: "Einheitsführung",
};
const COVERAGE_SHORT = { duration: "Einsatzdauer", turnout: "Ausrücken", arrival: "Eintreffen", crew: "Besatzung",
  attendance: "Anwesenheit", leader: "Einheitsführung" };

function coverageCard(e) {
  const c = e.coverage;
  const rows = c.rows.filter((r) => r.key !== "leader" || can("people.view")).map((r) => {
    const share = c.total ? r.valid / c.total : null, missing = c.total - r.valid;
    return [esc(COVERAGE_LABELS[r.key]), `${r.valid} von ${c.total}`, percent(share),
      missing && state.incidents ? `<a href="${esc(listLink({ missing: r.key }))}">${missing} anzeigen</a>` : missing ? String(missing) : "–"];
  });
  const items = c.rows.filter((r) => r.key !== "leader" || can("people.view")).map((r) => ({
    label: COVERAGE_SHORT[r.key], value: r.valid, text: percent(c.total ? r.valid / c.total : null), tip: `${COVERAGE_LABELS[r.key]}: ${coverageText(r.valid, c.total)}` }));
  const table = dataTable(["Angabe", "Einsätze mit Angabe", "Anteil", "Fehlend"], rows);
  return chartCard({ id: "coverage", heading: "h2", title: `Datenvollständigkeit`,
    subtitle: "Wie belastbar sind die Kennzahlen? Einsätze ohne Angabe fließen nicht als Null ein, sondern fehlen in der jeweiligen Kennzahl.",
    chart: !c.total ? `<p class="empty-note">Keine Einsätze im Jahr ${state.year}.</p>`
      // Sechs gleich lange Balken sagen nichts: bei voller Abdeckung genügt ein Satz, die Tabelle bleibt erreichbar
      : c.rows.every((r) => r.valid === c.total) ? `<p class="all-clear"><span class="record-status ok">Vollständig</span> ${items.length === 1 ? "Die Angabe liegt" : `Alle ${items.length} Angaben liegen`} für ${c.total === 1 ? "den Einsatz" : `alle ${c.total} Einsätze`} vor.</p>` : barChart(items), table });
}

function renderOverview() {
  const e = state.evaluation, s = e.statistics, plan = e.response_plan;
  const quote = plan?.total.count ? analysisKpi(`Eintreffen ≤ ${plan.limit} Min.`, percent(plan.total.rate),
    `${plan.total.on_time} von ${plan.total.count} Einsätzen mit Eintreffzeit oder Abbruch`) : "";
  const vg = e.tenants;
  $("#view-overview").innerHTML = evaluationToolbar({ exports: false }) + `<div class="kpis kpis-4">
    ${analysisKpi(`Einsätze ${state.year}`, vg ? vg.unique : s.count, vg ? esc(`${vg.participations} Beteiligungen der Wehren`) : `${num(s.per_week, 2)} je Woche`)}
    ${analysisKpi(`Ø Einsatzdauer`, formatDuration(s.duration_avg_min), esc(coverageText(e.workload.duration.valid, e.workload.duration.total)))}
    ${analysisKpi(`Einsatzstunden`, formatHours(s.duration_total_min), "Summe aller Einsätze")}
    ${quote || analysisKpi("Eintreffen", "–", plan ? "noch keine Einsätze mit Eintreffzeit" : "für Sie noch nicht freigegeben")}
  </div><div class="grid grid-2">${openTasksCard(e)}${coverageCard(e)}</div>`;
}

document.addEventListener("click", (event) => {
  if (!event.target.closest("[data-overview-notices]")) return;
  records.showNotices = true;
  renderNotices();
  window.scrollTo({ top: 0, behavior: scrollBehavior() });
});

// ------------------------------------------------------------ Zeiten & Kräfte
const distributionRow = (label, d) => [label, `${d.valid} / ${d.total}`, minutes(d.average), minutes(d.median), minutes(d.p90)];
const DISTRIBUTION_HEAD = ["", "Fälle", "Ø", "Median", "90 % höchstens"];

function timeSummaryCard(t) {
  const rows = [distributionRow("Ausrückdauer", t.turnout), distributionRow("Anfahrtdauer je Fahrzeug", t.travel),
    distributionRow("Zeit bis zum Eintreffen", t.arrival)];
  // Je Größe zwei Balken: Median in der Reihenfarbe, 90 % heller; die Gruppe steht unter einer Überschrift
  const items = [["Ausrückdauer", "Ausrücken", t.turnout], ["Anfahrtdauer je Fahrzeug", "Anfahrt", t.travel], ["Zeit bis zum Eintreffen", "Eintreffen", t.arrival]].flatMap(([label, short, d], n) => [
    { label: short, gap: n > 0, value: d.median ?? 0, text: minutes(d.median), tip: `${label}: Median ${minutes(d.median)}, ${coverageText(d.valid, d.total, short === "Anfahrt" ? VEHICLE_UNIT : INCIDENT_UNIT)}` },
    { label: "", hint: "90 % höchstens", tone: "accent", value: d.p90 ?? 0, text: minutes(d.p90), tip: `${label}: 90 % höchstens ${minutes(d.p90)}` }]);
  return chartCard({ id: "time-summary", title: `Wo entsteht die Zeit?`,
    subtitle: "Median und 90. Perzentil statt nur Durchschnitt: 9 von 10 Einsätzen (bzw. Fahrzeugen) waren höchstens so langsam.",
    chart: barChart(items) + legend([["series", "Median"], ["accent", "90 % höchstens"]]), table: dataTable(DISTRIBUTION_HEAD, rows),
    extra: `<p class="small muted section-gap">Die Anfahrtdauer wird je Fahrzeug aus dessen eigenem Ausrücken und Eintreffen berechnet (${esc(coverageText(t.travel.valid, t.travel.total, VEHICLE_UNIT))}).</p>` });
}

function buildUpCard(t) {
  const groups = t.build_up.map((b) => ({ axis: `${b.minutes} min`, tip: `${b.minutes} Minuten nach Alarmierung: Ø ${num(b.crew)} Personen vor Ort (${coverageText(b.valid, b.total)})`,
    values: [{ value: round1(b.crew) ?? 0, text: num(b.crew), labelled: true }] }));
  const table = dataTable(["Minuten nach Alarmierung", "Ø Personen vor Ort", "Einsätze mit Eintreffzeit"],
    t.build_up.map((b) => [`${b.minutes} min`, num(b.crew), `${b.valid} / ${b.total}`]));
  return chartCard({ id: "build-up", title: `Kräfteaufbau nach Alarmierung`,
    subtitle: "Ø Besatzung der eigenen Fahrzeuge, die nach n Minuten eingetroffen waren. Funktionen und Qualifikationen sind nicht erfasst.",
    chart: columnChart(groups), table, extra: `<p class="small muted section-gap">${esc(coverageText(t.build_up[0]?.valid ?? 0, t.total))} (Einsätze mit Eintreffzeit).</p>` });
}

function groupTable(head, rows) {
  const body = rows.map((g) => [`${esc(g.label)}${g.small ? ` <span class="small muted" data-tip="${SMALL_SAMPLE_NOTE}">(wenige Fälle)</span>` : ""}`,
    g.count, minutes(g.turnout.median), minutes(g.arrival.median), minutes(g.arrival.p90)]);
  return dataTable([head, "Einsätze", "Ausrückdauer (Median)", "Zeit bis Eintreffen (Median)", "Zeit bis Eintreffen (90 %)"], body);
}

const plainCard = (title, subtitle, body) => `<div class="card"><div class="card-header"><div><h3>${title}</h3>
  <p class="muted">${subtitle}</p></div></div>${body}</div>`;

function groupsCard(t) {
  const windows = t.by_window.map((w) => ({ ...w, label: `${w.day_type} ${w.hours}` }));
  const areas = t.by_area.map((a) => ({ ...a, label: a.name }));
  const small = [...windows, ...areas].some((g) => g.small && g.count);
  return `<div class="grid">${plainCard(`Zeiten nach Tageszeit`, "Wann treten Verzögerungen wiederholt auf?", groupTable("Zeitfenster", windows))}</div>
    <div class="grid">${plainCard("Zeiten nach Ort", "Einsatzgebiet wie im Einsatzgeschehen", groupTable("Ort", areas))}</div>
    ${small ? `<p class="small muted">Zeilen mit weniger als 5 Einsätzen sind als „wenige Fälle“ gekennzeichnet und kaum aussagekräftig.</p>` : ""}`;
}

function renderTimes() {
  const e = state.evaluation, t = e.timing;
  if (!t) { $("#view-times").innerHTML = evaluationToolbar({ exports: false }) + notReleased(); return; }
  if (!t.total) { $("#view-times").innerHTML = evaluationToolbar({ exports: false }) + noIncidentsCard(); return; }
  if (!t.turnout.valid && !t.travel.valid && !t.arrival.valid) {   // Einsätze da, aber keine Zeiten: kein Gerüst aus Strichen
    $("#view-times").innerHTML = evaluationToolbar({ exports: false }) + `<div class="card"><p class="empty-note">Für ${plural(t.total, "Einsatz", "Einsätze")} im Jahr ${state.year} liegen keine Ausrück- und Eintreffzeiten vor. Sie stammen aus den Einsatzberichten; Einsätze ohne Fahrzeugzeiten zeigt die Einsatzliste mit dem Filter „Prüfhinweise“. Bereits erfasste Einsätze erhalten die Zeiten durch erneutes Einlesen des Berichts.</p></div>`;
    return;
  }
  $("#view-times").innerHTML = evaluationToolbar({ exports: false }) + `<div class="kpis kpis-4">
    ${analysisKpi(`Ausrückdauer`, minutes(t.turnout.median), esc(`Median · 90 % ≤ ${minutes(t.turnout.p90)} · ${coverageText(t.turnout.valid, t.turnout.total)}`))}
    ${analysisKpi(`Anfahrtdauer je Fahrzeug`, minutes(t.travel.median), esc(`Median · 90 % ≤ ${minutes(t.travel.p90)} · ${coverageText(t.travel.valid, t.travel.total, VEHICLE_UNIT)}`))}
    ${analysisKpi(`Zeit bis Eintreffen`, minutes(t.arrival.median), esc(`Median · 90 % ≤ ${minutes(t.arrival.p90)} · ${coverageText(t.arrival.valid, t.arrival.total)}`))}
    ${analysisKpi("Einsätze im Jahr", t.total, e.response_plan_hidden.length ? esc(`ohne ${e.response_plan_hidden.join(", ")} (nicht freigegeben)`) : `Jahr ${state.year}`)}
  </div>
  <div class="grid grid-2">${timeSummaryCard(t)}${buildUpCard(t)}</div>${groupsCard(t)}`;
}

// ------------------------------------------------------------ Belastung
function workloadCard(w, s) {
  const part = (label, p) => [label, p.count, shareText(p.count, w.total), formatHours(p.hours * 60),
    p.staff_hours == null ? "–" : `${num(p.staff_hours, 0)} h${p.staff_recorded < p.staff_total ? ` (${p.staff_recorded} von ${p.staff_total} Einsätzen erfasst)` : ""}`];
  const rows = [part(`Lang (ab ${formatDuration(w.long.minutes)})`, w.long), part("Nachts", w.night), part("Samstag, Sonntag, Feiertag", w.weekend)];
  const items = rows.map(([label, count]) => ({ label, value: count, tip: `${label}: ${count} von ${w.total} Einsätzen` }));
  return chartCard({ id: "workload", title: `Belastung durch lange und nächtliche Einsätze`,
    subtitle: "Welche Belastung steckt hinter der reinen Einsatzanzahl? Ein Einsatz kann in mehreren Zeilen vorkommen.",
    chart: barChart(items), table: dataTable(["Art", "Einsätze", "Anteil", "Einsatzstunden", "Personalstunden"], rows),
    extra: `<p class="small muted section-gap">Personalstunden = Einsatzdauer × erfasste Anwesende; ohne Anwesenheit fehlen sie (${esc(coverageText(s.staff_recorded, s.staff_total))}).</p>` });
}

function durationCard(w) {
  const d = w.duration;
  const items = w.buckets.map((b) => ({ label: b.label, value: b.count }));
  const table = dataTable(["Dauer", "Einsätze", "Anteil"], w.buckets.map((b) => [b.label, b.count, shareOf(b.count, d.valid)]));
  const extra = keyFigures([[formatDuration(d.median), "Median"], [formatDuration(d.p90), "90 % höchstens"], [formatDuration(d.average), "Durchschnitt"]]);
  return chartCard({ id: "durations", title: "Dauer der Einsätze",
    subtitle: `Alarm bis Einsatzende, ${coverageText(d.valid, d.total)}`, chart: barChart(items), table, extra });
}

function overlapCard(o) {
  const hours = o.overlap_minutes ? formatDuration(o.overlap_minutes) : "0 min";
  return `<div class="card"><div class="card-header"><div><h3>Zeitliche Überschneidung</h3>
    <p class="muted">Wann waren mehrere Einsätze gleichzeitig offen? Das heißt nicht, dass dieselben Kräfte gebunden waren.</p></div></div>
    <div class="stat-mini">
      <div><b>${o.incidents_with_overlap}</b><span>Einsätze mit Überschneidung</span></div>
      <div><b>${o.max_concurrent}</b><span>höchstens gleichzeitig</span></div>
      <div><b>${hours}</b><span>mit mehreren offenen Einsätzen</span></div>
    </div>
    <p class="small muted section-gap">${esc(coverageText(o.valid, o.total))} (Beginn und Ende bekannt).${config.vg ? " In der Gesamtansicht je Wehr gerechnet und addiert." : ""}</p></div>`;
}

function renderWorkload() {
  const e = state.evaluation, w = e.workload, s = e.statistics;
  if (!w.total) { $("#view-load").innerHTML = evaluationToolbar({ exports: false }) + noIncidentsCard(); return; }
  $("#view-load").innerHTML = evaluationToolbar({ exports: false }) + `<div class="kpis kpis-4">
    ${analysisKpi(`Lange Einsätze`, w.long.count, esc(`ab ${formatDuration(w.long.minutes)} · ${shareText(w.long.count, w.total)}`))}
    ${analysisKpi("Nächtliche Einsätze", w.night.count, esc(shareText(w.night.count, w.total)))}
    ${analysisKpi("Samstag, Sonntag, Feiertag", w.weekend.count, esc(shareText(w.weekend.count, w.total)))}
    ${analysisKpi(`Gleichzeitig offen`, w.overlap.incidents_with_overlap, esc(`höchstens ${w.overlap.max_concurrent} zugleich`))}
  </div>
  <div class="grid grid-2">${workloadCard(w, s)}${durationCard(w)}</div><div class="grid">${overlapCard(w.overlap)}</div>`;
}
