"use strict";

// Fachkonstanten (Fahrzeuge, Orte, Zeitgrenzen, …) kommen von /api/config – hier keine eigenen Kopien.
let config = null;

const state = {
  years: [], year: null, view: "evaluation", limit: null,
  evaluation: null, incidents: null,
  category: "all", query: "", expanded: new Set(), editing: null,
  tableCards: new Set(),                      // Diagramme, die gerade als Tabelle angezeigt werden
  memberSort: { field: "incidents", descending: true },
  upload: { token: null, reports: [], errors: [] }, dataChanged: false,
};

// ------------------------------------------------------------ Hilfsfunktionen
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => el.querySelectorAll(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (n, digits = 1) => n == null ? "–" : Number(n).toLocaleString("de-DE", { maximumFractionDigits: digits });
const percent = (q) => q == null ? "–" : `${Math.round(q * 100)} %`;
const minutes = (m) => m == null ? "–" : `${num(m)} min`;
const orDash = (v) => v ?? "–";
const pad2 = (n) => String(n).padStart(2, "0");
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const formatDate = (iso) => iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}` : "–";
const formatTime = (iso) => !iso ? "–" : iso.length > 8 ? iso.slice(11, 16) : iso.slice(0, 5);
const weekdayShort = (iso) => iso ? new Date(iso).toLocaleDateString("de-DE", { weekday: "short" }) : "";
const MONTH_NAMES = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
const categoryOf = (keyword) => (keyword || "").charAt(0);
const errorBox = (message) => `<div class="message message-error">${esc(message)}</div>`;

function formatDuration(min) {
  if (min == null) return "–";
  const h = Math.floor(min / 60), m = Math.round(min % 60);
  return h ? `${h}:${pad2(m)} h` : `${m} min`;
}
const formatHours = (min) => min == null ? "–" : `${num(min / 60, 0)} h`;

const ICON_CHEVRON = `<svg class="chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const ICON_CLOSE = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>`;

async function api(url, options = {}) {
  const response = await fetch(url, options);
  // Sitzung abgelaufen → zur Anmeldung
  if (response.status === 401) { location.href = "/login"; throw new Error("Anmeldung erforderlich"); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Fehler ${response.status}`);
  return data;
}
const apiJson = (url, method, body) =>
  api(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

let toastTimer;
function toast(text) {
  const el = $("#toast");
  el.textContent = text;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3500);
}

function remember(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* privat/gesperrt */ } }
function recall(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }

// ------------------------------------------------------------ Diagramm-Bausteine
function niceScale(max) {
  if (max <= 0) return { max: 1, step: 1 };
  const raw = max / 4, p = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((f) => f * p).find((s) => s >= raw);
  return { max: Math.ceil(max / step) * step, step };
}

/** Waagerechte Balken, eine Serie. items: [{label, hint, value, tip}] */
function barChart(items) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return `<div class="bar-list">${items.map((i) => `
    <div class="bar-row" data-tip="${esc(i.tip || `${i.label}: ${i.value}`)}" tabindex="0">
      <span class="bar-label">${esc(i.label)}${i.hint ? `<small>${esc(i.hint)}</small>` : ""}</span>
      <span class="bar-track">${i.value ? `<span class="bar" style="width:${(i.value / max) * 100}%"></span>` : ""}</span>
      <span class="bar-value">${i.value}</span>
    </div>`).join("")}</div>`;
}

/** Säulen. groups: [{axis, tip, values: [{value, tone, labelled}]}]; tone = series | previous | day | night */
function columnChart(groups, { dense = false } = {}) {
  const max = Math.max(0, ...groups.flatMap((g) => g.values.map((v) => v.value || 0)));
  const scale = niceScale(max);
  const gridlines = [];
  for (let v = 0; v <= scale.max; v += scale.step) {
    gridlines.push(`<div class="columns-grid" style="bottom:${(v / scale.max) * 100}%"><span>${v}</span></div>`);
  }
  return `<div class="columns">
    <div class="columns-plot">${gridlines.join("")}
      <div class="columns-row">${groups.map((g) => `
        <div class="columns-group" data-tip="${esc(g.tip)}" tabindex="0">${g.values.map((v) => `
          <div class="column tone-${v.tone || "series"}" style="height:${((v.value || 0) / scale.max) * 100}%">
            ${v.labelled && v.value ? `<span class="column-value">${v.value}</span>` : ""}
          </div>`).join("")}
        </div>`).join("")}
      </div>
    </div>
    <div class="columns-axis ${dense ? "dense" : ""}">${groups.map((g) => `<span>${esc(g.axis)}</span>`).join("")}</div>
  </div>`;
}

function legend(entries) {
  return `<div class="legend">${entries.map(([tone, label]) => `<span><i class="tone-${tone}"></i>${esc(label)}</span>`).join("")}</div>`;
}

function keyFigures(entries) {
  return `<div class="key-figures">${entries.map(([value, label]) => `<span><b>${value}</b>${esc(label)}</span>`).join("")}</div>`;
}

function dataTable(head, rows, foot) {
  const cells = (row, tag) => row.map((c, i) => `<${tag} class="${i ? "right" : ""}">${c}</${tag}>`).join("");
  return `<div class="table-wrap"><table class="data-table">
    <thead><tr>${cells(head.map(esc), "th")}</tr></thead>
    <tbody>${rows.map((r) => `<tr>${cells(r, "td")}</tr>`).join("")}</tbody>
    ${foot ? `<tfoot><tr>${cells(foot, "td")}</tr></tfoot>` : ""}
  </table></div>`;
}

/** Karte mit Umschalter Diagramm / Tabelle (die Tabelle ist die barrierefreie Ansicht). */
function chartCard({ id, title, subtitle = "", chart, table, extra = "", heading = "h3", className = "", controls = "", chartLabel = "Diagramm" }) {
  const asTable = state.tableCards.has(id);
  return `<div class="card ${className}">
    <div class="card-header">
      <div><${heading}>${title}</${heading}>${subtitle ? `<p class="muted">${subtitle}</p>` : ""}</div>
      <div class="actions">${controls}<button type="button" class="btn btn-outline btn-small" data-toggle-table="${id}">${asTable ? chartLabel : "Tabelle"}</button></div>
    </div>
    ${asTable ? table : chart}
    ${extra}
  </div>`;
}

// ------------------------------------------------------------ Ansichten & Laden
const VIEWS = {
  evaluation: { label: "Auswertung", load: loadEvaluation, render: renderEvaluation },
  incidents: { label: "Einsätze", load: loadIncidents, render: renderIncidents },
  members: { label: "Kameraden", load: loadEvaluation, render: renderMembers },
};

function renderTabs() {
  $("#tabs").innerHTML = Object.entries(VIEWS).map(([key, v]) => `<a href="#${key}" data-view="${key}">${v.label}</a>`).join("");
}

async function loadYears() {
  const data = await api("/api/years");
  state.years = data.years.map((y) => y.year).sort((a, b) => b - a);
  const remembered = Number(recall("year"));
  if (!state.year || !state.years.includes(state.year)) {
    state.year = state.years.includes(remembered) ? remembered : state.years[0] ?? new Date().getFullYear();
  }
  $("#year").innerHTML = state.years.map((y) => `<option ${y === state.year ? "selected" : ""}>${y}</option>`).join("");
}

async function loadEvaluation() {
  const e = state.evaluation;
  if (!e || e.year !== state.year || e.response_plan.limit !== state.limit) {
    state.evaluation = await api(`/api/evaluation?year=${state.year}&limit=${state.limit}`);
  }
}

async function loadIncidents() {
  if (!state.incidents || state.incidents.year !== state.year) {
    state.incidents = await api(`/api/incidents?year=${state.year}`);
  }
}

async function showView() {
  const key = location.hash.slice(1);
  state.view = key in VIEWS ? key : "evaluation";
  const view = VIEWS[state.view];
  for (const a of $$("#tabs a")) a.classList.toggle("active", a.dataset.view === state.view);
  for (const k of Object.keys(VIEWS)) $(`#view-${k}`).hidden = k !== state.view;
  $("#page-title").textContent = `${view.label} ${state.year}`;
  const section = $(`#view-${state.view}`);
  section.classList.add("loading");
  try {
    await view.load();
    view.render();
  } catch (e) {
    section.innerHTML = errorBox(e.message);
  } finally {
    section.classList.remove("loading");
  }
}

async function reloadData() {
  state.evaluation = null;
  state.incidents = null;
  await loadYears();
  await showView();
}

// ------------------------------------------------------------ Auswertung
function renderEvaluation() {
  const { statistics: s, response_plan: plan, response_plan_previous: previousPlan } = state.evaluation;
  const currentYear = state.year === new Date().getFullYear();

  let comparison = "";
  if (currentYear && s.previous_to_date != null) {
    const d = s.count - s.previous_to_date;
    comparison = `${d > 0 ? "+" : ""}${d} gegenüber ${state.year - 1} zum selben Datum (${s.previous_to_date})`;
  } else if (s.previous_total != null) {
    comparison = `${state.year - 1}: ${s.previous_total} Einsätze`;
  }
  const kpi = (title, value, sub, hero = false) =>
    `<div class="kpi ${hero ? "hero" : ""}"><span class="kpi-title">${title}</span><span class="kpi-value">${value}</span><span class="kpi-sub">${sub}</span></div>`;
  const kpis = `<div class="kpis">
    ${kpi(`Einsätze ${state.year}`, s.count, esc(comparison), true)}
    ${kpi(`Einsätze / Woche${helpButton("per_week")}`, num(s.per_week, 2), currentYear ? "bis zur aktuellen KW" : "im ganzen Jahr")}
    ${kpi(`Ø Einsatzdauer${helpButton("duration")}`, formatDuration(s.duration_avg_min), "Alarm bis Einsatzende")}
    ${kpi(`Einsatzstunden${helpButton("operation_hours")}`, formatHours(s.duration_total_min), "Summe aller Einsätze")}
    ${kpi(`Personalstunden${helpButton("staff_hours")}`, `${num(s.staff_hours, 0)}<small>h</small>`, `Ø ${num(s.attendees_avg, 1)} Kameraden je Einsatz`)}
    ${kpi(`Eintreffen ≤ ${plan.limit} Min.${helpButton("on_time")}`, percent(plan.total.rate), `${plan.total.on_time} von ${plan.total.count} (Bedarfsplan)`)}
  </div>`;

  $("#view-evaluation").innerHTML = kpis + responsePlanCard(plan, previousPlan) + `
    <div class="grid grid-3">${categoriesCard(s)}${levelsCard(s)}${areasCard(s)}</div>
    <div class="grid">${monthsCard(s)}</div>
    <div class="grid">${historyCard(state.evaluation.history)}</div>
    <div class="grid grid-2">${hoursCard(s)}${weekdaysCard(s)}</div>`;
}

function responsePlanCard(plan, previousPlan) {
  const limit = plan.limit, second = config.second_limit;
  const windowTile = (w, isTotal) => `<div class="window ${isTotal ? "total" : ""} ${w.count ? "" : "empty"}">
      <div class="window-title">${isTotal ? "Gesamt" : esc(w.day_type)}<span>${isTotal ? "alle Zeitfenster" : esc(w.hours)}</span></div>
      <div class="rate">${percent(w.rate)}<small>${w.on_time} / ${w.count}</small></div>
      <div class="meter" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round((w.rate || 0) * 100)}"
           aria-label="Erreichungsgrad"><span style="width:${(w.rate || 0) * 100}%"></span></div>
      <dl class="window-values">
        <dt>Ø Ausrückezeit</dt><dd>${minutes(w.turnout_min)}</dd>
        <dt>Ø Eintreffzeit</dt><dd>${minutes(w.arrival_min)}</dd>
        <dt>Stärke bei Eintreffen</dt><dd>${num(w.crew_on_arrival)}</dd>
        <dt>Stärke nach ${limit} Min.</dt><dd>${num(w.crew_within_limit)}</dd>
        <dt>Stärke nach ${second} Min.</dt><dd>${num(w.crew_within_second)}</dd>
        <dt>Gesamtstärke</dt><dd>${num(w.crew_total)}</dd>
      </dl>
      ${isTotal && previousPlan?.total?.count ? `<div class="small faint">${state.year - 1}: ${percent(previousPlan.total.rate)} (${previousPlan.total.on_time} / ${previousPlan.total.count})</div>` : ""}
    </div>`;
  const rows = [...plan.windows, { ...plan.total, day_type: "Gesamt", hours: "" }].map((w) => [
    `${esc(w.day_type)} ${esc(w.hours)}`, w.count, num(w.turnout_min), num(w.arrival_min), w.on_time, w.late,
    percent(w.rate), num(w.crew_on_arrival), num(w.crew_within_limit), num(w.crew_within_second), num(w.crew_total)]);
  const table = dataTable(["Zeitfenster", "Einsätze", "Ø Azeit (min)", "Ø Ezeit (min)", `≤ ${limit} Min.`, `> ${limit} Min.`,
    "Erreichungsgrad", "Stärke Eintreffen", `Stärke nach ${limit} Min.`, `Stärke nach ${second} Min.`, "Gesamtstärke"], rows);
  const limitSwitch = `<div class="segments" role="group" aria-label="Zeitgrenze">
    ${config.limits.map((m) => `<button type="button" data-limit="${m}" class="${m === limit ? "active" : ""}">${m} Min.</button>`).join("")}
  </div>`;
  const footer = `<p class="plan-footer">Zeiten ab Einsatzbeginn (früheste Alarmierung). Gesamtstärke ohne ${config.plan_excluded_vehicles.join(", ")}, wie in der Einsatzübersicht.
    ${plan.without_times ? `${plural(plan.without_times, "Einsatz", "Einsätze")} ohne Eintreffzeit nicht berücksichtigt (Excel zählte sie mit 0 min als erreicht).` : ""}</p>`;
  return chartCard({
    id: "plan", heading: "h2", className: "plan grid", chartLabel: "Kacheln", controls: limitSwitch, extra: footer,
    title: `Feuerwehrbedarfsplan · Pos. 8.4${helpButton("response_plan")}`,
    subtitle: `Einsätze ab Alarmstufe ${config.plan_min_level} in ${plan.places.join(", ")} – Eintreffen des ersten Fahrzeugs innerhalb von ${limit} Minuten nach Alarmierung.`,
    chart: `<div class="plan-windows">${plan.windows.map((w) => windowTile(w, false)).join("")}${windowTile(plan.total, true)}</div>`,
    table,
  });
}

const shareOf = (count, total) => percent(total ? count / total : null);

function categoriesCard(s) {
  const items = s.categories.map((c) => ({
    label: c.name, hint: c.code, value: c.count,
    tip: `${c.name}: ${c.count}\n` + Object.entries(c.keywords).map(([k, n]) => `${k}: ${n}`).join(" · "),
  }));
  const table = dataTable(["Art", ...s.levels.map((l) => String(l.level)), "Summe"],
    s.categories.map((c) => [`${esc(c.name)} (${c.code})`, ...Object.values(c.keywords), `<b>${c.count}</b>`]),
    ["Gesamt", ...s.levels.map((l) => l.count), s.count]);
  const extra = `<div class="stat-mini">
    <div data-tip="Stichwort ${config.fire_alarm_system}"><b>${s.fire_alarm_systems}</b><span>Brandmeldeanlage</span></div>
    <div data-tip="Stichwort ${config.fire_watch}"><b>${s.fire_watches}</b><span>Brandsicherheitswache</span></div>
  </div>`;
  return chartCard({ id: "categories", title: "Einsatzarten", subtitle: "nach Einsatzstichwort", chart: barChart(items), table, extra });
}

function levelsCard(s) {
  const items = s.levels.map((l) => ({ label: `Stufe ${l.level}`, value: l.count, tip: `Alarmstufe ${l.level}: ${l.count} Einsätze` }));
  const table = dataTable(["Stufe", "Einsätze", "Anteil"], s.levels.map((l) => [`Stufe ${l.level}`, l.count, shareOf(l.count, s.count)]));
  return chartCard({ id: "levels", title: `Alarmstufen${helpButton("alarm_level")}`, subtitle: "zweite Ziffer des Stichworts (z. B. H<b>2</b>)", chart: barChart(items), table });
}

function areasCard(s) {
  const items = s.areas.map((a) => ({ label: a.name, value: a.count }));
  const own = s.areas.filter((a) => config.plan_places.includes(a.name)).reduce((sum, a) => sum + a.count, 0);
  const table = dataTable(["Ort", "Einsätze", "Anteil"], s.areas.map((a) => [esc(a.name), a.count, shareOf(a.count, s.count)]));
  const extra = keyFigures([[own, config.plan_places.join(", ")], [s.count - own, "außerhalb"]]);
  return chartCard({ id: "areas", title: `Einsatzgebiet${helpButton("area")}`, chart: barChart(items), table, extra });
}

function monthsCard(s) {
  const withPrevious = s.months.some((m) => m.previous != null);
  const previousYear = state.year - 1;
  const groups = s.months.map((m) => ({
    axis: m.name,
    tip: `${m.name} ${state.year}: ${m.count}` + (withPrevious ? `\n${m.name} ${previousYear}: ${m.previous}` : ""),
    values: [...(withPrevious ? [{ value: m.previous, tone: "previous" }] : []), { value: m.count, labelled: true }],
  }));
  const chartLegend = withPrevious ? legend([["series", String(state.year)], ["previous", String(previousYear)]]) : "";
  const table = dataTable(["Monat", String(state.year), ...(withPrevious ? [String(previousYear)] : [])],
    s.months.map((m) => [m.name, m.count, ...(withPrevious ? [m.previous] : [])]),
    ["Summe", s.count, ...(withPrevious ? [s.previous_total] : [])]);
  return chartCard({ id: "months", title: "Einsätze je Monat", subtitle: withPrevious ? `im Vergleich zu ${previousYear}` : "",
    chart: columnChart(groups) + chartLegend, table });
}

/** Verlauf über alle Jahre: Einsätze je Monat und gleitender 12-Monats-Durchschnitt, gewähltes Jahr hinterlegt. */
function historyCard(history) {
  const n = history.length;
  if (!n) return "";
  const scale = niceScale(Math.max(...history.map((h) => h.count)));
  const y = (v) => 100 - (v / scale.max) * 100;
  const path = (key) => history.map((h, i) => h[key] == null ? null : [i + 0.5, y(h[key])])
    .map((p, i, all) => p ? `${all[i - 1] ? "L" : "M"}${p[0]},${p[1].toFixed(2)}` : "").join("");
  const gridlines = [];
  for (let v = 0; v <= scale.max; v += scale.step) {
    gridlines.push(`<div class="columns-grid" style="bottom:${(v / scale.max) * 100}%"><span>${v}</span></div>`);
  }
  const first = history.findIndex((h) => h.year === state.year);
  const months = history.filter((h) => h.year === state.year).length;
  const band = first < 0 ? "" : `<div class="history-band" style="left:${(first / n) * 100}%;width:${(months / n) * 100}%"></div>`;
  const hits = history.map((h) => {
    const tip = `${h.name} ${h.year}${h.running ? " (laufend)" : ""}: ${plural(h.count, "Einsatz", "Einsätze")}` +
      (h.average == null ? "" : `\nØ letzte 12 Monate: ${num(h.average)}`);
    const dot = (v, cls) => v == null ? "" : `<i class="${cls}" style="bottom:${(v / scale.max) * 100}%"></i>`;
    return `<span class="history-hit" data-tip="${esc(tip)}">${dot(h.count, "dot-count")}${dot(h.average, "dot-average")}</span>`;
  }).join("");
  const years = [...new Set(history.map((h) => h.year))];
  const every = Math.ceil(years.length / 10);
  const axis = history.map((h, i) => h.month === 1 || i === 0 ? [h.year, i] : null).filter(Boolean)
    .filter(([year]) => (year - years[0]) % every === 0)
    .map(([year, i]) => `<span style="left:${(i / n) * 100}%">${year}</span>`).join("");
  const chart = `<div class="columns history">
      <div class="columns-plot">${gridlines.join("")}${band}
        <svg class="history-lines" viewBox="0 0 ${n} 100" preserveAspectRatio="none" aria-hidden="true">
          <path class="line-count" d="${path("count")}"/><path class="line-average" d="${path("average")}"/>
        </svg>
        <div class="history-hits">${hits}</div>
      </div>
      <div class="history-axis">${axis}</div>
    </div>` + legend([["series", "Einsätze im Monat"], ["average", "Ø letzte 12 Monate"], ["band", String(state.year)]]);
  const table = dataTable(["Jahr", ...MONTH_NAMES, "Summe"], years.map((year) => {
    const row = MONTH_NAMES.map((_, m) => history.find((h) => h.year === year && h.month === m + 1)?.count ?? "–");
    return [String(year), ...row, `<b>${row.reduce((sum, c) => sum + (Number(c) || 0), 0)}</b>`];
  }));
  return chartCard({ id: "history", title: `Verlauf${helpButton("history")}`, subtitle: `Einsätze je Monat seit ${years[0]}`, chart, table });
}

function hoursCard(s) {
  const [dayStart, dayEnd] = config.day_hours.map(pad2);
  const groups = s.hours.map((h) => ({
    axis: h.hour % 3 === 0 ? String(h.hour) : "",
    tip: `${pad2(h.hour)}:00 – ${pad2(h.hour)}:59 Uhr: ${h.count}`,
    values: [{ value: h.count, tone: h.daytime ? "day" : "night" }],
  }));
  const peak = s.hours.reduce((a, h) => (h.count > a.count ? h : a), s.hours[0]);
  const extra = legend([["day", `Tag ${dayStart}–${dayEnd} Uhr`], ["night", `Nacht ${dayEnd}–${dayStart} Uhr`]]) + keyFigures([
    [percent(s.daytime_share), "tagsüber"],
    [s.daytime_share == null ? "–" : `${100 - Math.round(s.daytime_share * 100)} %`, "nachts"],
    [`${peak.hour}–${peak.hour + 1} Uhr`, "häufigste Stunde"],
  ]);
  const table = dataTable(["Uhrzeit", "Einsätze"], s.hours.map((h) => [`${pad2(h.hour)}:00 Uhr`, h.count]));
  return chartCard({ id: "hours", title: "Alarmierungszeiten", subtitle: "Einsatzbeginn nach Uhrzeit", chart: columnChart(groups), table, extra });
}

function weekdaysCard(s) {
  const groups = s.weekdays.map((d) => ({ axis: d.name.slice(0, 2), tip: `${d.name}: ${d.count}`, values: [{ value: d.count, labelled: true }] }));
  const workdays = s.weekdays.slice(0, 5).reduce((sum, d) => sum + d.count, 0);
  const extra = keyFigures([[workdays, "Mo–Fr"], [s.count - workdays, "Sa/So"]]);
  const table = dataTable(["Wochentag", "Einsätze"], s.weekdays.map((d) => [d.name, d.count]));
  return chartCard({ id: "weekdays", title: "Wochentage", chart: columnChart(groups), table, extra });
}

// ------------------------------------------------------------ Einsätze
function matchesFilter(e) {
  if (state.category !== "all" && categoryOf(e.keyword) !== state.category) return false;
  const query = state.query.trim().toLowerCase();
  if (!query) return true;
  const text = [e.number, e.keyword, `${e.keyword}.${e.subcode}`, e.description, e.place, e.unit_leader,
    formatDate(e.started_at), e.filename, ...e.people.map((p) => p.name)].join(" ").toLowerCase();
  return query.split(/\s+/).every((t) => text.includes(t));
}

const isIdle = (v) => v.crew == null && !v.departed && !v.arrived;

function vehicleChips(e) {
  return `<div class="vehicle-chips">${e.vehicles.map((v) => {
    const short = v.call_sign.slice(3);
    if (isIdle(v)) return `<span data-tip="${v.call_sign}: nicht im Einsatz">${short}</span>`;
    const tip = `${esc(v.substitute || v.call_sign)} · Stärke ${orDash(v.crew)}\nEintreffen ${minutes(v.arrival_min)}`;
    return `<span class="on" data-tip="${tip}">${short}<b>${orDash(v.crew)}</b></span>`;
  }).join("")}</div>`;
}

function renderIncidents() {
  const list = state.incidents.incidents;
  const filters = [{ code: "all", name: "Alle" }, ...config.categories];
  const count = (code) => code === "all" ? list.length : list.filter((e) => categoryOf(e.keyword) === code).length;
  $("#category-filter").innerHTML = filters.map((c) =>
    `<button type="button" data-category="${c.code}" class="${state.category === c.code ? "active" : ""}" ${c.code !== "all" ? `data-tip="${c.name}"` : ""}>${c.code === "all" ? c.name : c.code}<span class="count">${count(c.code)}</span></button>`).join("");

  const visible = list.filter(matchesFilter).reverse();   // neueste zuerst
  const limit = config.default_limit;
  $("#incident-table tbody").innerHTML = visible.map((e) => {
    const open = state.expanded.has(e.id);
    const arrival = e.arrival_min == null ? `<span class="muted">–</span>`
      : `<span class="arrival ${e.on_time ? "" : "late"}" data-tip="${e.on_time ? "innerhalb" : "nicht innerhalb"} von ${limit} Minuten">${minutes(e.arrival_min)}</span>`;
    return `<tr class="row ${open ? "open" : ""}" data-id="${e.id}">
      <td><span class="number">${orDash(e.number)}</span></td>
      <td><div>${formatDate(e.started_at)}</div><div class="time">${weekdayShort(e.started_at)} ${formatTime(e.started_at)}${e.weekend_or_holiday ? " · WE/FT" : ""}</div></td>
      <td><span class="keyword ${categoryOf(e.keyword).toLowerCase()}">${esc(e.keyword)}${e.subcode ? "." + esc(e.subcode) : ""}</span></td>
      <td><div class="incident-title">${esc(e.description)}</div><div class="incident-place">${esc(e.place)}</div></td>
      <td>${e.unit_leader ? esc(e.unit_leader) : `<span class="muted">–</span>`}</td>
      <td>${vehicleChips(e)}</td>
      <td class="right">${arrival}</td>
      <td class="right">${e.crew_total}</td>
      <td>${ICON_CHEVRON}</td>
    </tr>${open ? `<tr class="detail"><td colspan="9">${state.editing === e.id ? editForm(e) : incidentDetail(e)}</td></tr>` : ""}`;
  }).join("");
  $("#incidents-empty").hidden = visible.length > 0;
}

function vehicleTable(e) {
  const limit = config.default_limit;
  return `<div class="table-wrap"><table class="mini-table"><thead><tr>
    <th>Fzg.</th><th class="right">Stärke</th><th>Ausr.</th><th class="right">Azeit</th><th>Eintr.</th><th class="right">Ezeit</th></tr></thead>
    <tbody>${e.vehicles.map((v) => isIdle(v)
      ? `<tr class="vehicle-idle"><td>${v.call_sign}</td><td colspan="5">nicht im Einsatz</td></tr>`
      : `<tr><td><strong>${v.call_sign}</strong>${v.substitute ? `<br><span class="small muted">${esc(v.substitute)}</span>` : ""}</td>
        <td class="right">${orDash(v.crew)}</td><td>${formatTime(v.departed)}</td><td class="right minutes">${num(v.turnout_min)}</td>
        <td>${formatTime(v.arrived)}</td><td class="right minutes ${v.arrival_min != null && v.arrival_min > limit ? "late" : ""}">${num(v.arrival_min)}</td></tr>`).join("")}
    </tbody></table></div>`;
}

// pickLeader: Namen sind Knöpfe, ein Klick trägt die Person als EHF ins Formular ein
function peopleChips(e, { markNew = false, pickLeader = false } = {}) {
  return e.people.map((p) => {
    const isLeader = e.unit_leader ? p.leader : /Einheitsführer/.test(p.role || "");
    const cls = [markNew && p.new && "new", isLeader && "leader"].filter(Boolean).join(" ");
    const tip = [p.role, p.vehicle, markNew && p.new && "wird als neuer Kamerad angelegt",
      pickLeader && `Klicken: als EHF eintragen (${p.leader_name})`].filter(Boolean).join(" · ");
    const content = `${esc(p.name)}${p.vehicle ? `<small>${esc(p.vehicle)}</small>` : ""}`;
    const attributes = `class="person ${cls}" ${tip ? `data-tip="${esc(tip)}"` : ""}`;
    return pickLeader
      ? `<button type="button" ${attributes} data-leader="${esc(p.leader_name)}">${content}</button>`
      : `<span ${attributes}>${content}</span>`;
  }).join("") || `<span class="muted">Keine Anwesenheit erfasst</span>`;
}

/** EHF aus einem angeklickten Namen übernehmen und die Hervorhebung nachziehen. */
function pickLeader(chip) {
  const form = chip.closest("[data-form], .preview-card");
  const input = $('input[name="unit_leader"]', form);
  input.value = chip.dataset.leader;
  input.classList.remove("missing");
  highlightLeader(form);
}

function highlightLeader(form) {
  const leader = $('input[name="unit_leader"]', form).value.trim();
  for (const chip of $$("[data-leader]", form)) chip.classList.toggle("leader", !!leader && chip.dataset.leader === leader);
}

function warningsList(warnings, emptyText = "") {
  if (!warnings.length && !emptyText) return "";
  const items = warnings.length ? warnings.map((w) => `<li>${esc(w)}</li>`).join("") : `<li class="ok">${emptyText}</li>`;
  return `<ul class="warnings">${items}</ul>`;
}

function attendancePanel(e, options = {}) {
  const newCount = options.markNew ? e.people.filter((p) => p.new).length : 0;
  const hint = options.pickLeader && e.people.length ? `<p class="small muted">Einen Namen anklicken, um die Person als EHF einzutragen.</p>` : "";
  return `<h4>Anwesenheit · ${e.people.length} Personen${newCount ? ` · ${newCount} neu` : ""}${helpButton("attendance")}</h4>
    ${hint}<div class="people">${peopleChips(e, options)}</div>`;
}

function incidentDetail(e) {
  const limit = config.default_limit;
  return `<div class="detail-grid">
    <div class="panel"><h4>Einsatz</h4><dl class="facts">
      <dt>Beginn</dt><dd>${formatDate(e.started_at)} ${formatTime(e.started_at)}</dd>
      <dt>Ende</dt><dd>${formatDate(e.ended_at)} ${formatTime(e.ended_at)}</dd>
      <dt>Dauer${helpButton("duration")}</dt><dd>${formatDuration(e.duration_min)}</dd>
      <dt>Zeitfenster${helpButton("time_window")}</dt><dd>${e.weekend_or_holiday ? "Sa/So/Feiertag" : "Werktag"}, ${e.daytime ? "Tag" : "Nacht"}</dd>
      <dt>Ort</dt><dd>${esc(e.place || "–")}</dd>
      <dt>EHF${helpButton("unit_leader")}</dt><dd>${esc(e.unit_leader || "–")}</dd>
      <dt>Gerätehaus${helpButton("station_staff")}</dt><dd>${e.station_staff}</dd>
      <dt>Quelle</dt><dd class="small">${e.source === "pdf" ? `PDF · ${esc(e.filename)}` : "Einsatzübersicht (Excel)"}</dd>
    </dl></div>
    <div class="panel"><h4>Fahrzeuge${helpButton("vehicles")}</h4>${vehicleTable(e)}</div>
    <div class="panel"><h4>Kennzahlen</h4><dl class="facts">
      <dt>Azeit${helpButton("turnout_min")}</dt><dd>${minutes(e.turnout_min)}</dd>
      <dt>Ezeit${helpButton("arrival_min")}</dt><dd>${minutes(e.arrival_min)}</dd>
      <dt>${limit} Min. erreicht${helpButton("on_time")}</dt><dd>${e.on_time == null ? "–" : e.on_time ? "ja" : "nein"}</dd>
      <dt>Stärke Eintreffen${helpButton("crew_on_arrival")}</dt><dd>${orDash(e.crew_on_arrival)}</dd>
      <dt>nach ${limit} Min.${helpButton("crew_within_limit")}</dt><dd>${orDash(e.crew_within_limit)}</dd>
      <dt>nach ${config.second_limit} Min.${helpButton("crew_within_second")}</dt><dd>${orDash(e.crew_within_second)}</dd>
      <dt>Gesamtstärke${helpButton("crew_total")}</dt><dd>${e.crew_total}</dd>
    </dl>
    ${e.warnings.length ? `<h4 class="section-gap">Prüfhinweise${helpButton("warnings")}</h4>${warningsList(e.warnings)}` : ""}
    </div>
    <div class="panel full">${attendancePanel(e)}</div>
    <div class="actions panel full bare">
      <button type="button" class="btn btn-outline btn-small" data-action="delete" data-id="${e.id}">Löschen</button>
      <button type="button" class="btn btn-light btn-small" data-action="edit" data-id="${e.id}">Bearbeiten</button>
    </div>
  </div>`;
}

// Formularfelder: [name, Titel, Eingabetyp, Breite, weitere Attribute]. Die Namen sind die Felder der API.
const FORM_FIELDS = [
  ["number", "Nr.", "number", "", 'min="1"'],
  ["started_at", "Beginn", "datetime-local", "span-2", 'step="1"'],
  ["ended_at", "Ende", "datetime-local", "span-2", 'step="1"'],
  ["station_staff", "Gerätehaus", "number", "", 'min="0"'],
  ["keyword", "Stichwort", "text", "", 'maxlength="6" placeholder="z. B. B2"'],
  ["subcode", "Stufe", "text", "", 'maxlength="2"'],
  ["description", "Einsatz", "text", "span-4", ""],
  ["place", "Ort", "text", "span-3", 'list="place-options"'],
  ["unit_leader", "EHF", "text", "span-3", 'list="leader-options" placeholder="z. B. M. Mustermann"'],
];

function formFields(e) {
  return `<div class="form-grid">${FORM_FIELDS.map(([name, title, type, span, attributes]) => {
    const value = type === "datetime-local" ? (e[name] || "").slice(0, 19) : e[name];
    const missing = name === "unit_leader" && !value;
    return `<label class="field ${span}"><span>${title}${helpButton(name)}</span><input name="${name}" type="${type}" value="${esc(value ?? "")}" ${attributes}
      class="${missing ? "missing" : ""}"></label>`;
  }).join("")}</div>`;
}

function readForm(el) {
  const values = {};
  for (const input of $$("input[name]", el)) {
    values[input.name] = input.type === "number" ? (input.value === "" ? null : Number(input.value)) : input.value;
  }
  return values;
}

function editForm(e) {
  return `<div class="detail-grid" data-form="${e.id}">
    <div class="panel full"><h4>Einsatz ${e.number ?? ""} bearbeiten</h4>${formFields(e)}</div>
    <div class="panel full">${attendancePanel(e, { pickLeader: true })}</div>
    <div class="actions panel full bare">
      <button type="button" class="btn btn-outline btn-small" data-action="cancel">Abbrechen</button>
      <button type="button" class="btn btn-primary btn-small" data-action="save" data-id="${e.id}">Speichern</button>
    </div>
  </div>`;
}

function updateDatalists() {
  // Vorschläge für Ort und EHF aus den bekannten Orten und vorhandenen Einsätzen
  const incidents = state.incidents?.incidents || [];
  const places = [...new Set([...config.places, ...incidents.map((e) => e.place)])].filter(Boolean);
  const leaders = [...new Set(incidents.map((e) => e.unit_leader).filter(Boolean))].sort();
  let container = $("#datalists");
  if (!container) { container = document.createElement("div"); container.id = "datalists"; document.body.append(container); }
  const options = (values) => values.map((v) => `<option value="${esc(v)}">`).join("");
  container.innerHTML = `<datalist id="place-options">${options(places)}</datalist><datalist id="leader-options">${options(leaders)}</datalist>`;
}

async function handleIncidentAction(action, id) {
  if (action === "edit") { state.editing = id; updateDatalists(); renderIncidents(); return; }
  if (action === "cancel") { state.editing = null; renderIncidents(); return; }
  try {
    if (action === "delete") {
      const incident = state.incidents.incidents.find((x) => x.id === id);
      if (!confirm(`Einsatz ${incident.number ?? ""} vom ${formatDate(incident.started_at)} wirklich löschen?`)) return;
      await api(`/api/incidents/${id}`, { method: "DELETE" });
      state.expanded.delete(id);
      toast("Einsatz gelöscht");
    }
    if (action === "save") {
      await apiJson(`/api/incidents/${id}`, "PUT", readForm($(`[data-form="${id}"]`)));
      state.editing = null;
      toast("Gespeichert");
    }
    await reloadData();
  } catch (err) {
    alert(err.message);
  }
}

// ------------------------------------------------------------ Kameraden
const MEMBER_COLUMNS = [      // [Feld, Titel, CSS-Klassen, Hilfe-Schlüssel]
  ["name", "Name", ""], ["incidents", "Einsätze", ""], ["rate", "Beteiligung", "right", "participation"],
  ["hours", "Stunden", "right", "hours"], ["nights", "nachts", "right hide-mobile", "nights_weekends"],
  ["weekends", "Sa/So/FT", "right hide-mobile", "nights_weekends"], ["last", "Zuletzt", "right hide-mobile"],
];

function renderMembers() {
  const a = state.evaluation.attendance;
  const { field, descending } = state.memberSort;
  const compare = (x, y) => field === "name" ? x.name.localeCompare(y.name, "de")
    : (x[field] ?? "") > (y[field] ?? "") ? 1 : (x[field] ?? "") < (y[field] ?? "") ? -1 : 0;
  const list = [...a.members].sort((x, y) => descending ? -compare(x, y) : compare(x, y));
  const max = Math.max(1, ...list.map((m) => m.incidents));
  $("#view-members").innerHTML = `<div class="card list-card members-table">
    <div class="toolbar"><div><h3>Anwesenheit ${state.year}</h3>
      <p class="muted small">${plural(list.length, "Kamerad", "Kameraden")} · ${plural(a.incident_count, "Einsatz", "Einsätze")} · Stunden = Einsatzdauer je Teilnahme</p></div></div>
    <div class="table-wrap"><table class="table">
      <thead><tr><th class="col-number">#</th>${MEMBER_COLUMNS.map(([f, title, cls, help]) =>
        `<th class="sortable ${cls}" data-sort="${f}">${title}${field === f ? (descending ? " ▾" : " ▴") : ""}${help ? helpButton(help) : ""}</th>`).join("")}</tr></thead>
      <tbody>${list.map((m, i) => `<tr>
        <td class="muted">${i + 1}</td>
        <td><strong>${esc(m.name)}</strong></td>
        <td><div class="inline-bar"><span class="track"><span style="width:${(m.incidents / max) * 100}%"></span></span><b>${m.incidents}</b></div></td>
        <td class="right">${percent(m.rate)}</td>
        <td class="right">${num(m.hours)}</td>
        <td class="right hide-mobile">${m.nights}</td>
        <td class="right hide-mobile">${m.weekends}</td>
        <td class="right hide-mobile">${formatDate(m.last)}</td>
      </tr>`).join("")}</tbody>
    </table></div>
    ${list.length ? "" : `<p class="empty-note">Für ${state.year} ist keine Anwesenheit erfasst.</p>`}
  </div>`;
}

// ------------------------------------------------------------ PDF einlesen
function showUploadError(html) {
  const el = $("#pdf-error");
  el.innerHTML = html;
  el.hidden = false;
}

async function readPdfs(files) {
  files = [...files].filter((f) => /\.(pdf|zip)$/i.test(f.name));
  $("#pdf-error").hidden = true;
  if (!files.length) { showUploadError("Bitte eine PDF- oder ZIP-Datei wählen."); return; }
  $("#progress").hidden = false;
  const form = new FormData();
  for (const f of files) form.append("pdfs", f, f.name.normalize("NFC"));
  try {
    const data = await api("/api/reports", { method: "POST", body: form });
    state.upload = { token: data.token, reports: data.reports.map((r) => ({ ...r, replace: false, saved: null })), errors: data.errors };
    if (data.errors.length) showUploadError(data.errors.map((e) => `${esc(e.file)}: ${esc(e.message)}`).join("<br>"));
    await acceptCleanReports();
    renderPreviews();
  } catch (e) {
    showUploadError(esc(e.message));
  } finally {
    $("#progress").hidden = true;
  }
}

// Zu prüfen sind Berichte mit Prüfhinweisen, neuen Personen oder Abweichungen zu einem erfassten Einsatz
function reviewReasons(r) {
  const reasons = [];
  if (r.warnings.length) reasons.push(plural(r.warnings.length, "Prüfhinweis", "Prüfhinweise"));
  const newPeople = r.people.filter((p) => p.new).length;
  if (newPeople) reasons.push(plural(newPeople, "neue Person", "neue Personen"));
  if (r.existing?.differences.length) reasons.push(plural(r.existing.differences.length, "Abweichung", "Abweichungen"));
  if (r.error) reasons.push(r.error);
  return reasons;
}

// Unveränderter, schon erfasster Einsatz: nichts zu tun
const isUnchanged = (r) => r.existing && !r.existing.differences.length && !reviewReasons(r).length;

async function acceptCleanReports() {
  // Nacheinander, damit doppelte Einsatznummern in einem Upload als Fehler beim zweiten Bericht auffallen
  for (const r of state.upload.reports) {
    if (r.existing || reviewReasons(r).length) continue;
    try {
      r.saved = await apiJson("/api/reports/accept", "POST", { token: state.upload.token, filename: r.filename, fields: {} });
      r.auto = true;
      state.dataChanged = true;
    } catch (err) {
      r.error = err.message;
    }
  }
}

function uploadSummary(reports) {
  const auto = reports.filter((r) => r.auto).length, unchanged = reports.filter(isUnchanged).length;
  const open = reports.filter((r) => !r.saved && !isUnchanged(r)).length;
  const parts = [];
  if (auto) parts.push(`${plural(auto, "Einsatz", "Einsätze")} ohne Anmerkungen übernommen`);
  if (unchanged) parts.push(`${plural(unchanged, "Einsatz", "Einsätze")} bereits unverändert erfasst`);
  if (open) parts.push(`${plural(open, "Bericht", "Berichte")} zu prüfen`);
  return parts.length ? `<div class="message message-info">${parts.join(" · ")}</div>` : "";
}

function previewStatus(r) {
  const existing = r.existing;
  const status = (cls, number, title, sub) =>
    `<div class="preview-status ${cls}"><span class="number">${number}</span><div><strong>${title}</strong><span>${sub}</span></div></div>`;
  if (r.saved) return status("done", "✓", `Einsatz ${r.saved.number ?? ""}/${r.saved.year} ist in der Statistik`, esc(r.filename));
  if (existing) {
    const origin = existing.source === "pdf" ? "aus einer PDF" : "aus der Einsatzübersicht (Excel)";
    const diffs = existing.differences.length ? plural(existing.differences.length, "Abweichung", "Abweichungen") : "keine Abweichungen";
    return status("existing", r.number ?? "?", `Einsatz ${r.number}/${r.year} ist bereits erfasst`, `${origin} · ${diffs}`);
  }
  return status("", r.number ?? "?", `Neuer Einsatz ${r.number ?? ""}${r.number ? "/" + r.year : ""}`,
    [esc(r.filename), ...reviewReasons(r).map(esc)].join(" · "));
}

function differencesTable(existing) {
  if (!existing?.differences.length) return "";
  return `<h4 class="section-gap">Abweichungen zur Statistik</h4>
    <table class="mini-table diff-table"><thead><tr><th>Feld</th><th>erfasst</th><th>PDF</th></tr></thead><tbody>
    ${existing.differences.map((d) => `<tr><td>${esc(d.field)}</td><td>${esc(d.stored)}</td><td>${esc(d.report)}</td></tr>`).join("")}</tbody></table>`;
}

function renderPreviews() {
  const reports = state.upload.reports;
  $("#dropzone").classList.toggle("compact", reports.length > 0);
  $("#previews").innerHTML = uploadSummary(reports) + reports.map((r, i) => {
    if (r.auto || isUnchanged(r)) return "";
    const existing = r.existing;
    return `<div class="preview-card" data-index="${i}">
      ${previewStatus(r)}
      ${r.saved ? "" : `<div class="preview-body">
        ${formFields(r)}
        <div class="preview-grid">
          <div class="panel outlined"><h4>Fahrzeuge${helpButton("vehicles")}</h4>${vehicleTable(r)}
            <p class="small muted section-gap">Ezeit erstes Fahrzeug: <b>${minutes(r.arrival_min)}</b> · Gesamtstärke ${r.crew_total}</p></div>
          <div class="panel outlined"><h4>Prüfhinweise${helpButton("warnings")}</h4>${warningsList(r.warnings, "Keine Prüfhinweise")}${differencesTable(existing)}</div>
        </div>
        <div class="panel outlined">${attendancePanel(r, { markNew: true, pickLeader: true })}</div>
        <div class="preview-footer">
          ${existing ? `<label class="toggle"><input type="checkbox" data-replace="${i}" ${r.replace ? "checked" : ""}> erfassten Einsatz durch diese PDF ersetzen</label>` : ""}
          <button type="button" class="btn btn-primary" data-accept="${i}" ${existing && !r.replace ? "disabled" : ""}>
            ${existing ? "Ersetzen" : "In Statistik übernehmen"}</button>
        </div>
      </div>`}
    </div>`;
  }).join("");
}

async function acceptReport(i) {
  const r = state.upload.reports[i];
  const card = $(`.preview-card[data-index="${i}"]`);
  const button = $("[data-accept]", card);
  button.disabled = true;
  try {
    const saved = await apiJson("/api/reports/accept", "POST",
      { token: state.upload.token, filename: r.filename, fields: readForm(card), replace: r.replace });
    r.saved = saved;
    state.dataChanged = true;
    toast(`Einsatz ${saved.number ?? ""}/${saved.year} übernommen`);
    renderPreviews();
  } catch (err) {
    button.disabled = false;
    alert(err.message);
  }
}

// ------------------------------------------------------------ Tooltip
const tooltip = $("#tooltip");
let tooltipTarget = null, tooltipFrame = 0;
function showTooltip(el, x, y) {
  // Text nur beim Wechsel des Elements setzen, Position höchstens einmal je Frame messen
  if (el !== tooltipTarget || tooltip.hidden) { tooltipTarget = el; tooltip.textContent = el.dataset.tip; tooltip.hidden = false; }
  cancelAnimationFrame(tooltipFrame);
  tooltipFrame = requestAnimationFrame(() => {
    const r = tooltip.getBoundingClientRect();
    tooltip.style.left = `${Math.min(window.innerWidth - r.width - 8, Math.max(8, x - r.width / 2))}px`;
    tooltip.style.top = `${Math.max(8, y - r.height - 12)}px`;
  });
}
function hideTooltip() {
  cancelAnimationFrame(tooltipFrame);
  tooltipTarget = null;
  tooltip.hidden = true;
}
document.addEventListener("mousemove", (e) => {
  const el = e.target.closest?.("[data-tip]");
  if (el) showTooltip(el, e.clientX, e.clientY); else if (tooltipTarget) hideTooltip();
});
document.addEventListener("focusin", (e) => {
  const el = e.target.closest?.("[data-tip]");
  if (el) { const r = el.getBoundingClientRect(); showTooltip(el, r.left + r.width / 2, r.top); }
});
document.addEventListener("focusout", hideTooltip);

// ------------------------------------------------------------ Ereignisse
window.addEventListener("hashchange", () => { state.expanded.clear(); showView(); });
$("#year").addEventListener("change", (e) => {
  state.year = Number(e.target.value);
  remember("year", state.year);
  state.expanded.clear();
  state.editing = null;
  showView();
});

$("#view-evaluation").addEventListener("click", (e) => {
  const toggle = e.target.closest("[data-toggle-table]");
  if (toggle) {
    const id = toggle.dataset.toggleTable;
    state.tableCards.has(id) ? state.tableCards.delete(id) : state.tableCards.add(id);
    renderEvaluation();
    return;
  }
  const limitButton = e.target.closest("[data-limit]");
  if (limitButton && Number(limitButton.dataset.limit) !== state.limit) {
    state.limit = Number(limitButton.dataset.limit);
    showView();
  }
});

$("#category-filter").addEventListener("click", (e) => {
  const button = e.target.closest("button");
  if (!button) return;
  state.category = button.dataset.category;
  renderIncidents();
});
$("#search").addEventListener("input", (e) => { state.query = e.target.value; renderIncidents(); });
$("#btn-export").addEventListener("click", () => { location.href = `/api/export?year=${state.year}`; });

$("#incident-table tbody").addEventListener("click", (e) => {
  const chip = e.target.closest("[data-leader]");
  if (chip) { pickLeader(chip); return; }
  const action = e.target.closest("[data-action]");
  if (action) { handleIncidentAction(action.dataset.action, Number(action.dataset.id)); return; }
  if (e.target.closest("tr.detail")) return;
  const row = e.target.closest("tr.row");
  if (!row) return;
  const id = Number(row.dataset.id);
  if (state.expanded.has(id)) {
    state.expanded.delete(id);
    if (state.editing === id) state.editing = null;
  } else {
    state.expanded.add(id);
  }
  renderIncidents();
});

$("#view-members").addEventListener("click", (e) => {
  const th = e.target.closest("[data-sort]");
  if (!th) return;
  const field = th.dataset.sort;
  state.memberSort = { field, descending: state.memberSort.field === field ? !state.memberSort.descending : field !== "name" };
  renderMembers();
});

// EHF von Hand geändert → Hervorhebung der Namen anpassen;
// ganzes Stichwort (B207, B2.07) gleich in Stichwort und Stufe trennen – der Server trennt beim Speichern ebenso
for (const container of [$("#incident-table tbody"), $("#previews")]) {
  container.addEventListener("input", (e) => {
    if (e.target.name === "unit_leader") highlightLeader(e.target.closest("[data-form], .preview-card"));
  });
  container.addEventListener("change", (e) => {
    if (e.target.name === "keyword") splitKeyword(e.target.closest("[data-form], .preview-card"));
  });
}

function splitKeyword(form) {
  const keyword = $('input[name="keyword"]', form), subcode = $('input[name="subcode"]', form);
  const m = keyword.value.trim().match(/^([a-z]\d)\s*[.\s]?\s*(\d{0,2})$/i);
  if (!m) return;
  keyword.value = m[1].toUpperCase();
  if (m[2]) subcode.value = m[2].padStart(2, "0");
}

// Dialoge
for (const button of $$("[data-close]")) {
  button.innerHTML = ICON_CLOSE;
  button.addEventListener("click", () => $(`#${button.dataset.close}`).close());
}
const pdfDialog = $("#pdf-dialog");
$("#btn-pdf").addEventListener("click", async () => {
  if (!state.incidents) { try { await loadIncidents(); } catch (e) { /* nur für Vorschläge */ } }
  updateDatalists();
  if (state.upload.reports.every((r) => r.saved || isUnchanged(r))) {
    state.upload = { token: null, reports: [], errors: [] };
    $("#pdf-error").hidden = true;
    renderPreviews();
  }
  pdfDialog.showModal();
});
pdfDialog.addEventListener("close", async () => {
  if (state.dataChanged) { state.dataChanged = false; await reloadData(); }
});
const dropzone = $("#dropzone");
["dragenter", "dragover"].forEach((t) => dropzone.addEventListener(t, (e) => { e.preventDefault(); dropzone.classList.add("dragging"); }));
["dragleave", "drop"].forEach((t) => dropzone.addEventListener(t, () => dropzone.classList.remove("dragging")));
dropzone.addEventListener("drop", (e) => { e.preventDefault(); readPdfs(e.dataTransfer.files); });
dropzone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#pdf-input").click(); } });
$("#pdf-input").addEventListener("change", (e) => { readPdfs(e.target.files); e.target.value = ""; });
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => e.preventDefault());
$("#previews").addEventListener("change", (e) => {
  const i = e.target.dataset.replace;
  if (i === undefined) return;
  // Eingaben behalten: Formularwerte vor dem Neuzeichnen übernehmen
  Object.assign(state.upload.reports[i], readForm(e.target.closest(".preview-card")), { replace: e.target.checked });
  renderPreviews();
});
$("#previews").addEventListener("click", (e) => {
  const chip = e.target.closest("[data-leader]");
  if (chip) { pickLeader(chip); return; }
  const button = e.target.closest("[data-accept]");
  if (button) acceptReport(Number(button.dataset.accept));
});

// Start
(async () => {
  renderTabs();
  addHelpButtons();
  try {
    [config] = await Promise.all([api("/api/config"), loadYears()]);
  } catch (e) {
    $("#view-evaluation").hidden = false;
    $("#view-evaluation").innerHTML = errorBox(e.message);
    return;
  }
  state.limit = config.default_limit;
  if (config.user) {
    $("#logout").hidden = false;
    $("#logout button").dataset.tip = `Abmelden (${config.user})`;
  }
  await showView();
})();
