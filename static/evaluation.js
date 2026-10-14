// Auswertung (Einsatzgeschehen): Laden und Karten der Ansicht „Einsatzgeschehen“. Wird vor app.js geladen; 
// nutzt dessen Hilfsfunktionen ($, esc, chartCard …) erst zur Laufzeit.

async function loadEvaluation() {
  const e = state.evaluation, filter = [...state.tenantFilter].sort().join(",");
  // Zeitgrenze der Anfrage merken: ohne Freigabe fehlt die Auswertung des Eintreffens (response_plan = null)
  if (!e || e.year !== state.year || e.limit !== state.limit || e.filter !== filter) {
    const { year, limit } = state;
    const data = await api(`/api/evaluation?year=${year}&limit=${limit}${filter ? `&tenants=${encodeURIComponent(filter)}` : ""}`);
    // Inzwischen anderes Jahr bzw. andere Auswahl: die ältere Antwort verwerfen
    if (year === state.year && limit === state.limit && filter === [...state.tenantFilter].sort().join(",")) {
      state.evaluation = Object.assign(data, { filter, limit });
    }
  }
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
  const vg = state.evaluation.tenants;
  const kpis = `<div class="kpis">
    ${vg ? kpi(`Einsätze ${state.year}${helpButton("participations")}`, vg.unique,
      esc(`${vg.participations} Beteiligungen der Wehren${vg.without_dispatch_number ? ` · ${vg.without_dispatch_number} ohne BKS-Stammdatensatz und Leitstellen-Nr.` : ""}`), true)
      : kpi(`Einsätze ${state.year}`, s.count, esc(comparison), true)}
    ${kpi(`Einsätze / Woche${helpButton("per_week")}`, num(s.per_week, 2), currentYear ? "bis zur aktuellen KW" : "im ganzen Jahr")}
    ${kpi(`Ø Einsatzdauer${helpButton("duration")}`, formatDuration(s.duration_avg_min),
      state.evaluation.workload.duration.valid < state.evaluation.workload.duration.total
        ? `Alarm bis Einsatzende · ${state.evaluation.workload.duration.valid} von ${state.evaluation.workload.duration.total} Einsätzen` : "Alarm bis Einsatzende")}
    ${kpi(`Einsatzstunden${helpButton("operation_hours")}`, formatHours(s.duration_total_min), "Summe aller Einsätze")}
    ${kpi(`Personalstunden${helpButton("staff_hours")}`, s.staff_hours == null ? "–" : `${num(s.staff_hours, 0)}<small>h</small>`,
      s.staff_recorded < s.staff_total ? `Unvollständig: Anwesenheit und Dauer für ${s.staff_recorded} von ${s.staff_total} Einsätzen` : `Ø ${num(s.attendees_avg, 1)} Personen je Einsatz`)}
    ${plan ? kpi(`Eintreffen ≤ ${plan.limit} Min.${helpButton("on_time")}`, percent(plan.total.rate), `${plan.total.on_time} von ${plan.total.count} Einsätzen mit Eintreffzeit oder Abbruch`) : ""}
  </div>`;

  $("#view-evaluation").innerHTML = evaluationToolbar() + kpis + (plan ? responsePlanCard(plan, previousPlan) : "") + (vg ? tenantsCard(vg) : "") + `
    <div class="grid grid-3">${categoriesCard(s)}${levelsCard(s)}${areasCard(s)}</div>
    <div class="grid">${monthsCard(s)}</div>
    <div class="grid">${historyCard(state.evaluation.history)}</div>
    <div class="grid grid-2">${hoursCard(s)}${weekdaysCard(s)}</div>`;
}

// Kopf der Auswertung: Wehr-Filter (Gesamtansicht), Drucken und Kennzahlen-Export
function evaluationToolbar({ exports = true } = {}) {
  const tenants = config.vg ? config.tenants : [];
  const chips = tenants.length > 1 ? `<div class="segments tenant-filter" role="group" aria-label="Wehren">
    <button type="button" data-tenant-filter="" class="${state.tenantFilter.size ? "" : "active"}">Alle Wehren</button>
    ${tenants.map((t) => `<button type="button" data-tenant-filter="${esc(t.slug)}" class="${state.tenantFilter.has(t.slug) ? "active" : ""}">${esc(t.name)}</button>`).join("")}
  </div>` : "<div></div>";
  const chosen = state.tenantFilter.size ? tenants.filter((t) => state.tenantFilter.has(t.slug)).map((t) => t.name).join(", ") : "";
  return `<div class="evaluation-toolbar no-print">${chips}<div class="toolbar-right">
      ${exports ? `<button type="button" class="btn btn-light btn-small" data-action="summary-export" data-tip="Kennzahlen je Wehr, ohne Namen">Kennzahlen (Excel)</button>` : ""}
      <button type="button" class="btn btn-light btn-small" data-action="print" data-tip="Druckansicht, im Druckdialog „Als PDF sichern“">Drucken / PDF</button>
    </div></div>
    <p class="print-only print-stamp">${esc(config.name)} · Einsatzstatistik ${state.year}${chosen ? ` · ${esc(chosen)}` : ""} · Stand ${formatDate(new Date().toISOString())}</p>`;
}

function tenantsCard(vg) {
  const rows = vg.rows.map((r) => [esc(r.name), r.count, r.plan_count, percent(r.rate), minutes(r.arrival_min),
    num(r.duration_hours, 0), num(r.staff_hours, 0)]);
  const sum = (key) => vg.rows.reduce((total, r) => total + (r[key] || 0), 0);
  const table = dataTable(["Wehr", "Einsätze", "Eintreffen: Einsätze", "In der Zeitgrenze", "Ø Zeit bis Eintreffen", "Einsatzstunden", "Personalstunden"],
    rows, ["Summe (Beteiligungen)", vg.participations, sum("plan_count"), "", "", num(sum("duration_hours"), 0), num(sum("staff_hours"), 0)]);
  const items = vg.rows.map((r) => ({ label: r.name, value: r.count, tip: `${r.name}: ${r.count} Einsätze`,
    link: listLink({ tenants: config.tenants.find((t) => t.name === r.name)?.slug }) }));
  const extra = keyFigures([[vg.unique, "Einsätze ohne Doppelte"], [vg.participations - vg.unique, "gemeinsame Beteiligungen"]]);
  return `<div class="grid">${chartCard({ id: "tenants", title: `Wehren${helpButton("participations")}`,
    subtitle: "Einsätze je Wehr; ein gemeinsamer Einsatz zählt bei jeder beteiligten Wehr", chart: barChart(items), table, extra })}</div>`;
}

function responsePlanCard(plan, previousPlan) {
  const limit = plan.limit, second = config.second_limit;
  // Einsätze des Zeitfensters bzw. die verspäteten in der Einsatzliste
  const windowLinks = (w, isTotal) => {
    const window = isTotal ? undefined : w.key;
    return w.count ? `<div class="window-links no-print"><a href="${esc(listLink({ plan: 1, window }))}">${plural(w.count, "Einsatz", "Einsätze")}</a>
      ${w.late ? ` · <a href="${esc(listLink({ plan: 1, window, late: limit }))}">${w.late} nicht erreicht</a>` : ""}</div>` : "";
  };
  const windowTile = (w, isTotal) => `<div class="window ${isTotal ? "total" : ""} ${w.count ? "" : "empty"}">
      <div class="window-title">${isTotal ? "Gesamt" : esc(w.day_type)}<span>${isTotal ? "alle Zeitfenster" : esc(w.hours)}</span></div>
      <div class="rate">${percent(w.rate)}<small>${w.on_time} / ${w.count}</small></div>
      ${windowLinks(w, isTotal)}
      <div class="meter" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round((w.rate || 0) * 100)}"
           aria-label="Erreichungsgrad"><span style="width:${(w.rate || 0) * 100}%"></span></div>
      <dl class="window-values">
        <dt>Ø Ausrückdauer</dt><dd>${minutes(w.turnout_min)}</dd>
        <dt>Ø Zeit bis Eintreffen</dt><dd>${minutes(w.arrival_min)}</dd>
        <dt>Stärke bei Eintreffen</dt><dd>${num(w.crew_on_arrival)}</dd>
        <dt>Zusätzlich bis ${limit} Min.</dt><dd>${num(w.crew_within_limit)}</dd>
        <dt>Zusätzlich ${limit}–${second} Min.</dt><dd>${num(w.crew_within_second)}</dd>
        <dt>Gesamtstärke</dt><dd>${num(w.crew_total)}</dd>
      </dl>
      ${isTotal && previousPlan?.total?.count ? `<div class="small faint">${state.year - 1}: ${percent(previousPlan.total.rate)} (${previousPlan.total.on_time} / ${previousPlan.total.count})</div>` : ""}
    </div>`;
  const rows = [...plan.windows, { ...plan.total, day_type: "Gesamt", hours: "" }].map((w) => [
    `${esc(w.day_type)} ${esc(w.hours)}`, w.count, num(w.turnout_min), num(w.arrival_min), w.on_time, w.late,
    percent(w.rate), num(w.crew_on_arrival), num(w.crew_within_limit), num(w.crew_within_second), num(w.crew_total)]);
  const table = dataTable(["Zeitfenster", "Einsätze", "Ø Ausrückdauer (min)", "Ø Zeit bis Eintreffen (min)", `≤ ${limit} Min.`, `> ${limit} Min.`,
    "Erreichungsgrad", "Stärke Eintreffen", `Zusätzlich bis ${limit} Min.`, `Zusätzlich ${limit}–${second} Min.`, "Gesamtstärke"], rows);
  // Umschalter nur, wenn die Wehr mehrere Zeitgrenzen eingestellt hat
  const limitSwitch = config.limits.length > 1 ? `<div class="segments" role="group" aria-label="Zeitgrenze">
    ${config.limits.map((m) => `<button type="button" data-limit="${m}" class="${m === limit ? "active" : ""}">${m} Min.</button>`).join("")}
  </div>` : "";
  const e = state.evaluation;
  // Freigabe: Verwaltungsrollen sehen den Plan immer und geben ihn für die übrigen Rollen frei
  const release = config.tenant && can("plan.release") ? `<label class="toggle no-print" data-tip="Ohne Freigabe sehen diese Auswertung nur Rollen mit dem Recht „Eintreffen und Kräfte ohne Freigabe sehen“ (z. B. Wehrführer, Wehrleiter)">
      <input type="checkbox" data-plan-release ${e.response_plan_public ? "checked" : ""}> für alle freigegeben</label>` : "";
  const hidden = e.response_plan_hidden.length ? ` Ohne ${esc(e.response_plan_hidden.join(", "))} (nicht freigegeben).` : "";
  const exclusions = config.plan_excluded_vehicles.length ? `Gesamtstärke ohne ${esc(config.plan_excluded_vehicles.join(", "))}.` : "Keine Fahrzeuge ausgeschlossen.";
  const footer = `<p class="plan-footer">${!e.response_plan_public && !hidden ? "<b>Nur für die Verwaltung sichtbar.</b> " : ""}Zeiten ab Einsatzbeginn (früheste Alarmierung). ${exclusions}
    ${plan.without_times ? `${plural(plan.without_times, "Einsatz", "Einsätze")} ohne Eintreffzeit nicht berücksichtigt (Excel zählte sie mit 0 min als erreicht).` : ""}${hidden}</p>`;
  return chartCard({
    id: "plan", heading: "h2", className: "plan grid", chartLabel: "Kacheln", controls: release + limitSwitch, extra: footer,
    title: `Eintreffen und verfügbare Kräfte${helpButton("response_plan")}`,
    subtitle: plan.places.length ? `Einsätze ab Alarmstufe ${config.plan_min_level} im Ausrückebereich der Wehr (festgelegt unter Einstellungen → Orte & Zeitgrenzen) – Eintreffen des ersten Fahrzeugs innerhalb von ${limit} Minuten nach Alarmierung; abgebrochene Einsätze ohne Eintreffzeit gelten als rechtzeitig. Das ist eine Eintreffquote – kein vollständiger Nachweis eines Schutzziels und kein Feuerwehrbedarfsplan.` : "Noch kein Ausrückebereich konfiguriert. Bitte unter Einstellungen → Orte & Zeitgrenzen einrichten.",
    chart: `<div class="plan-windows">${plan.windows.map((w) => windowTile(w, false)).join("")}${windowTile(plan.total, true)}</div>`,
    table,
  });
}

const shareOf = (count, total) => percent(total ? count / total : null);

function categoriesCard(s) {
  const items = s.categories.map((c) => ({
    label: c.name, hint: c.code, value: c.count, link: listLink({ cat: c.code }),
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
  const items = s.levels.map((l) => ({ label: `Stufe ${l.level}`, value: l.count, tip: `Alarmstufe ${l.level}: ${l.count} Einsätze`,
    link: listLink({ level: l.level }) }));
  const table = dataTable(["Stufe", "Einsätze", "Anteil"], s.levels.map((l) => [`Stufe ${l.level}`, l.count, shareOf(l.count, s.count)]));
  return chartCard({ id: "levels", title: `Alarmstufen${helpButton("alarm_level")}`, subtitle: "zweite Ziffer des Stichworts (z. B. H<b>2</b>)", chart: barChart(items), table });
}

function areasCard(s) {
  const items = s.areas.map((a) => ({ label: a.name, value: a.count, link: listLink({ area: a.name }) }));
  const own = s.areas.filter((a) => config.plan_places.includes(a.name)).reduce((sum, a) => sum + a.count, 0);
  const table = dataTable(["Ort", "Einsätze", "Anteil"], s.areas.map((a) => [esc(a.name), a.count, shareOf(a.count, s.count)]));
  const extra = keyFigures([[own, config.plan_places.join(", ")], [s.count - own, "außerhalb"]]);
  return chartCard({ id: "areas", title: `Einsatzgebiet${helpButton("area")}`, chart: barChart(items), table, extra });
}

function monthsCard(s) {
  const withPrevious = s.months.some((m) => m.previous != null);
  const previousYear = state.year - 1;
  const groups = s.months.map((m, i) => ({
    axis: m.name, link: m.count ? listLink({ month: i + 1 }) : null,
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
    axis: h.hour % 3 === 0 ? String(h.hour) : "", link: h.count ? listLink({ hour: h.hour }) : null,
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
  const groups = s.weekdays.map((d, i) => ({ axis: d.name.slice(0, 2), tip: `${d.name}: ${d.count}`,
    link: d.count ? listLink({ weekday: i }) : null, values: [{ value: d.count, labelled: true }] }));
  const workdays = s.weekdays.slice(0, 5).reduce((sum, d) => sum + d.count, 0);
  const extra = keyFigures([[workdays, "Mo–Fr"], [s.count - workdays, "Sa/So"]]);
  const table = dataTable(["Wochentag", "Einsätze"], s.weekdays.map((d) => [d.name, d.count]));
  return chartCard({ id: "weekdays", title: "Wochentage", chart: columnChart(groups), table, extra });
}
