// Einsatzliste: Laden, Filter und Sortierung (in der Adresse), Zeilen und Fahrzeugchips. Wird vor app.js geladen.

async function openIncident(key, year) {
  if (year && year !== state.year && state.years.includes(year)) {
    state.year = year;
    $("#year").value = String(year);
  }
  state.scrollTo = key;
  state.current = key;
  // Suche und Filter würden den Einsatz womöglich ausblenden
  clearListFilters();
  if (parseHash().view === "incidents") {
    state.expanded.add(key);
    await showView();
  } else {
    location.hash = "#incidents";            // der hashchange-Listener klappt state.scrollTo auf
  }
}
document.addEventListener("app:view", () => {
  if (!state.scrollTo || state.view !== "incidents") return;
  $(`#incident-table tr.row[data-id="${CSS.escape(state.scrollTo)}"]`)?.scrollIntoView({ block: "start", behavior: scrollBehavior() });
  state.scrollTo = null;
});

async function loadIncidents() {
  if (!state.incidents || state.incidents.year !== state.year) {
    const year = state.year, data = await api(`/api/incidents?year=${year}`);
    data.incidents = data.incidents.filter((i) => !pendingDeletes.has(i.id));   // gelöscht, Rückgängig noch möglich
    if (year === state.year) state.incidents = data;
  }
}

// ------------------------------------------------------------ Einsätze: Filter, Sortierung, Adresse
// Filter und Sortierung stehen in der Adresse (#incidents?cat=B&month=3 …): Sie überstehen das Neuladen,
// lassen sich als Link weitergeben, und die Auswertung springt damit in die Liste.
const WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"];
const WINDOW_LABELS = { weekday_day: "Werktag, Tag", weekday_night: "Werktag, Nacht", weekend_day: "Sa/So/Feiertag, Tag",
  weekend_night: "Sa/So/Feiertag, Nacht" };
// Einsätze, denen eine Angabe fehlt (Übersicht → Datenvollständigkeit): Beschriftung und Prüfung je Schlüssel
const MISSING_LABELS = { duration: "ohne Einsatzdauer", turnout: "ohne Ausrückdauer", arrival: "ohne Eintreffzeit",
  crew: "ohne Besatzung", attendance: "ohne Anwesenheit", leader: "ohne Einheitsführung" };
const lacks = {
  duration: (e) => e.duration_min == null, turnout: (e) => e.turnout_min == null, arrival: (e) => e.arrival_min == null,
  crew: (e) => !(e.crew_total > 0), attendance: (e) => !e.people_count, leader: (e) => !e.unit_leader,
};

// Filter aus der Auswertung: Schlüssel in der Adresse -> Beschriftung des Filter-Chips
const LIST_FILTERS = {
  tenants: (v) => v.split(",").map((slug) => config.tenants.find((t) => t.slug === slug)?.name || slug).join(", "),
  month: (v) => new Date(2000, Number(v) - 1).toLocaleString("de-DE", { month: "long" }), weekday: (v) => WEEKDAYS[Number(v)] || v,
  hour: (v) => `${pad2(v)}–${pad2((Number(v) + 1) % 24)} Uhr`, area: (v) => v, level: (v) => `Alarmstufe ${v}`,
  missing: (v) => MISSING_LABELS[v] || v,
  plan: () => "Eintreffen und Kräfte", window: (v) => WINDOW_LABELS[v] || v, late: (v) => `nicht innerhalb ${v} Min.`,
};

function parseHash() {
  const [view, query = ""] = location.hash.slice(1).split("?");
  return { view, params: new URLSearchParams(query) };
}

/** Adresse der Einsatzliste mit genau diesen Filtern (Werte undefined/null fallen weg). */
function listLink(filters) {
  // In der Gesamtansicht gilt die Auswahl der Wehren der Auswertung mit
  if (state.tenantFilter.size && !("tenants" in filters)) filters = { tenants: [...state.tenantFilter].sort().join(","), ...filters };
  const params = new URLSearchParams(Object.entries(filters).filter(([, v]) => v != null && v !== ""));
  return params.toString() ? `#incidents?${params}` : "#incidents";
}

/** Filter aus der Adresse übernehmen; ohne Parameter bleibt der aktuelle Stand (Klick auf den Reiter). */
function applyListParams(params) {
  if (!params.toString()) return;
  state.query = params.get("q") || "";
  state.category = params.get("cat") || "all";
  state.warnOnly = params.get("warn") === "1";
  state.todoOnly = params.get("todo") === "1";
  if (params.has("sort")) state.incidentSort = sortFrom(params.get("sort"));
  state.filters = Object.fromEntries(Object.keys(LIST_FILTERS).filter((k) => params.has(k)).map((k) => [k, params.get(k)]));
  $("#search").value = state.query;
}

function listParams() {
  const params = new URLSearchParams();
  if (state.query) params.set("q", state.query);
  if (state.category !== "all") params.set("cat", state.category);
  if (state.warnOnly) params.set("warn", "1");
  if (state.todoOnly) params.set("todo", "1");
  const { field, descending } = state.incidentSort;
  if (field !== "started_at" || !descending) params.set("sort", `${field}-${descending ? "desc" : "asc"}`);
  for (const [k, v] of Object.entries(state.filters)) params.set(k, v);
  return params;
}

// Adresse an die Filter anpassen, ohne Eintrag im Verlauf und ohne hashchange
function syncHash() {
  if (state.view !== "incidents") return;
  const query = listParams().toString(), hash = `#incidents${query ? `?${query}` : ""}`;
  if (location.hash !== hash) history.replaceState(null, "", hash);
}

function clearListFilters() {
  state.query = "";
  state.category = "all";
  state.warnOnly = false;
  state.todoOnly = false;
  state.filters = {};
  $("#search").value = "";
}

// Zu erledigen: Prüfhinweise, fehlende Nr. oder ein offener Hinweis (Abweichung, Bericht fehlt …) zu diesem Einsatz
function todoReasons(e) {
  const reasons = [...(e.current_warnings || [])];
  if (e.number == null) reasons.push("Einsatznummer fehlt");
  const notices = typeof records === "undefined" ? [] : records.notices;
  for (const n of notices) if (n.incident_key === e.id) reasons.push(n.text);
  return reasons;
}

const levelOf = (keyword) => (keyword || "").charAt(1);
const startOf = (e) => e.started_at ? new Date(e.started_at) : null;
// Nicht erreicht: bei der Standardgrenze wie die Auswertung (on_time), sonst über die Eintreffzeit
const isLate = (e, limit) => limit === config.default_limit ? e.on_time === false : e.arrival_min > limit;

function matchesFilter(e) {
  if (state.category !== "all" && categoryOf(e.keyword) !== state.category) return false;
  if (state.warnOnly && !e.current_warnings?.length) return false;
  if (state.todoOnly && !todoReasons(e).length) return false;
  const f = state.filters, start = startOf(e);
  if (f.tenants && !f.tenants.split(",").includes(e.tenant)) return false;
  if (f.month && start?.getMonth() + 1 !== Number(f.month)) return false;
  if (f.weekday && (start ? (start.getDay() + 6) % 7 : null) !== Number(f.weekday)) return false;
  if (f.hour && start?.getHours() !== Number(f.hour)) return false;
  if (f.area && e.area !== f.area) return false;
  if (f.level && levelOf(e.keyword) !== f.level) return false;
  if (f.missing && !lacks[f.missing]?.(e)) return false;
  // Eintreffen und Kräfte wie in der Auswertung: relevante Einsätze mit Eintreffzeit
  if ((f.plan || f.window || f.late) && !(e.plan_relevant && e.on_time != null)) return false;
  if (f.window && (e.weekend_or_holiday !== f.window.startsWith("weekend") || e.daytime !== f.window.endsWith("_day"))) return false;
  if (f.late && !isLate(e, Number(f.late))) return false;
  const query = state.query.trim().toLowerCase();
  if (!query) return true;
  const text = [e.number, e.keyword, `${e.keyword}.${e.subcode}`, keywordName(e), e.description, e.place, e.unit_leader,
    formatDate(e.started_at), e.filename, ...e.people.map((p) => p.name)].join(" ").toLowerCase();
  return query.split(/\s+/).every((t) => text.includes(t));
}

// Sortierwert einer Spalte; fehlende Werte stehen immer am Ende
function sortValue(e, field) {
  if (field === "keyword") return e.keyword ? `${e.keyword}.${e.subcode || ""}` : null;
  return e[field] ?? null;
}

/** Einsätze, wie die Liste sie zeigt: gefiltert und sortiert (auch für j/k und Vor/Zurück). */
function visibleIncidents() {
  const { field, descending } = state.incidentSort;
  return state.incidents.incidents.filter(matchesFilter).sort((a, b) => {
    const x = sortValue(a, field), y = sortValue(b, field);
    if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1;
    const order = typeof x === "number" ? x - y : String(x).localeCompare(String(y), "de", { numeric: true });
    return (descending ? -order : order) || (b.started_at || "").localeCompare(a.started_at || "");
  });
}

// Kopf der Liste: Sortierung, Filter aus der Auswertung, Prüfhinweise
function renderListControls(list) {
  const { field, descending } = state.incidentSort;
  for (const th of $$("#incident-table [data-sort-incidents]")) {
    const active = th.dataset.sortIncidents === field;
    th.setAttribute("aria-sort", active ? (descending ? "descending" : "ascending") : "none");
    $(".sort-mark", th).textContent = active ? (descending ? " ▾" : " ▴") : "";
  }
  const warned = list.filter((e) => e.current_warnings?.length).length;
  const warn = $("#warn-filter");
  warn.classList.toggle("active", state.warnOnly);
  warn.setAttribute("aria-pressed", String(state.warnOnly));
  $(".count", warn).textContent = warned;
  const todo = $("#todo-filter");
  todo.classList.toggle("active", state.todoOnly);
  todo.setAttribute("aria-pressed", String(state.todoOnly));
  $(".count", todo).textContent = list.filter((e) => todoReasons(e).length).length;
  const chips = Object.entries(state.filters).map(([k, v]) =>
    `<span class="filter-chip">${esc(LIST_FILTERS[k](v))}<button type="button" data-remove-filter="${k}" aria-label="Filter ${esc(LIST_FILTERS[k](v))} entfernen">×</button></span>`);
  $("#active-filters").innerHTML = chips.length ? `<span class="small muted">aus der Auswertung:</span>${chips.join("")}
    <button type="button" class="btn btn-link btn-small" data-remove-filter="">alle Filter aufheben</button>` : "";
  $("#active-filters").hidden = !chips.length;
}

const isIdle = (v) => v.crew == null && !v.departed && !v.arrived;

// „Zu spät“ trägt Symbol und Text, nicht nur die Farbe (für Bildschirmleser als Text vorhanden)
const LATE_ICON = `<svg class="late-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5 2.8 19.5h18.4L12 3.5Z" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linejoin="round"/></svg>`;
const lateMark = (late, limit) => `${late ? LATE_ICON : ""}<span class="visually-hidden"> (${late ? "nicht " : ""}innerhalb von ${limit} Minuten)</span>`;

function vehicleChips(e) {
  return `<div class="vehicle-chips">${e.vehicles.map((v) => {
    const short = esc(v.call_sign.slice(3));
    if (isIdle(v)) return `<span role="img" aria-label="${esc(v.call_sign)}: nicht im Einsatz" data-tip="${esc(v.call_sign)}: nicht im Einsatz">${short}</span>`;
    const tip = `${esc(v.substitute || v.call_sign)} · Stärke ${orDash(v.crew)}\nEintreffen ${minutes(v.arrival_min)}`;
    return `<span class="on" role="img" aria-label="${tip.replace("\n", ", ")}" data-tip="${tip}">${short}<b>${orDash(v.crew)}</b></span>`;
  }).join("")}</div>`;
}

function renderIncidents() {
  const list = state.incidents.incidents;
  const filters = [{ code: "all", name: "Alle" }, ...config.categories];
  const count = (code) => code === "all" ? list.length : list.filter((e) => categoryOf(e.keyword) === code).length;
  $("#category-filter").innerHTML = filters.map((c) =>
    `<button type="button" data-category="${c.code}" class="${state.category === c.code ? "active" : count(c.code) ? "" : "empty"}" aria-pressed="${state.category === c.code}" ${c.code !== "all" ? `data-tip="${c.name}"` : ""}>${c.code === "all" ? c.name : c.code}<span class="count">${count(c.code)}</span></button>`).join("");

  renderListControls(list);
  const visible = visibleIncidents();
  const limit = config.default_limit, withTenant = Boolean(config.vg);
  const tenantNames = Object.fromEntries(config.tenants.map((t) => [t.slug, t.name]));
  // Offenes Formular beim Neuzeichnen (Suche, Filter, andere Zeile) samt Eingaben behalten
  const formSelector = state.editing ? `[data-form="${CSS.escape(state.editing)}"]` : null;
  if (formSelector && $(formSelector)) state.editNode = $(formSelector);
  // Erste Seite plus alle aufgeklappten Einsätze (sonst verschwände die Zeile, die man gerade liest)
  const shown = visible.filter((e, i) => i < state.listLimit || state.expanded.has(e.id));
  $("#incident-table tbody").innerHTML = shown.map((e) => {
    const open = state.expanded.has(e.id);
    const arrival = e.arrival_min == null ? `<span class="muted">–</span>`
      : `<span class="arrival ${e.on_time ? "" : "late"}" data-tip="${e.on_time ? "innerhalb" : "nicht innerhalb"} von ${limit} Minuten">${minutes(e.arrival_min)}${lateMark(!e.on_time, limit)}</span>`;
    return `<tr class="row ${open ? "open" : ""}" data-id="${e.id}">
      <td><button type="button" class="btn btn-light btn-small" aria-expanded="${open}" aria-label="Details zu Einsatz ${esc(e.number ?? "ohne Nummer")}">${orDash(e.number)}</button></td>
      <td><div>${formatDate(e.started_at)}</div><div class="time">${weekdayShort(e.started_at)} ${formatTime(e.started_at)}${e.weekend_or_holiday ? " · WE/FT" : ""}</div></td>
      <td><span class="keyword ${categoryOf(e.keyword).toLowerCase()}" ${keywordName(e) ? `data-tip="${esc(keywordName(e))}"` : ""}>${esc(e.keyword)}${e.subcode ? "." + esc(e.subcode) : ""}</span></td>
      <td><div class="incident-title">${esc(e.description)}${todoReasons(e).length ? ` <span class="todo-mark" role="img" aria-label="Zu erledigen: ${esc(todoReasons(e).join(", "))}" data-tip="${esc(todoReasons(e).join("\n"))}">●</span>` : ""}</div><div class="incident-place">${withTenant ? `<span class="tenant-badge">${esc(tenantNames[e.tenant] || e.tenant)}</span>` : ""}${esc(e.place)}</div></td>
      <td>${e.unit_leader ? esc(e.unit_leader) : `<span class="muted">–</span>`}</td>
      <td>${vehicleChips(e)}</td>
      <td class="right">${arrival}</td>
      <td class="right">${e.crew_total}</td>
      <td>${ICON_CHEVRON}</td>
    </tr>${open ? `<tr class="detail"><td colspan="9">${state.editing === e.id ? editForm(e) : incidentDetail(e)}</td></tr>` : ""}`;
  }).join("");
  if (formSelector && state.editNode && $(formSelector)) $(formSelector).replaceWith(state.editNode);
  const more = $("#incidents-more");
  more.hidden = shown.length >= visible.length;
  more.innerHTML = more.hidden ? "" : `<span class="small muted">${shown.length} von ${visible.length} Einsätzen</span>
    <button type="button" class="btn btn-light" data-list-more>Weitere ${Math.min(LIST_PAGE, visible.length - shown.length)} anzeigen</button>`;
  $("#incidents-empty").hidden = visible.length > 0;
  $("#incidents-empty").innerHTML = list.length && (state.query || state.category !== "all" || state.warnOnly || state.todoOnly || Object.keys(state.filters).length)
    ? `Keine Einsätze zu diesen Filtern. <button type="button" class="btn btn-link btn-small" data-clear-filters>Alle Filter aufheben</button>`
    : "Keine Einsätze gefunden.";
  syncHash();
}
