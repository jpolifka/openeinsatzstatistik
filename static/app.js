"use strict";

// Gemerkte Einstellungen nur im eigenen Browser (privat/gesperrt: ohne)
function remember(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* privat/gesperrt */ } }
function recall(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
function recallList(key) { try { return JSON.parse(recall(key)) || []; } catch (e) { return []; } }
// Sortierung der Einsatzliste: "feld-desc" bzw. "feld-asc"
const INCIDENT_SORTS = ["number", "started_at", "keyword", "arrival_min", "crew_total"];
function sortFrom(text) {
  const [field, direction] = (text || "").split("-");
  return INCIDENT_SORTS.includes(field) ? { field, descending: direction !== "asc" } : { field: "started_at", descending: true };
}

// Fachkonstanten (Fahrzeuge, Orte, Zeitgrenzen, …) kommen von /api/config – hier keine eigenen Kopien.
let config = null;

const state = {
  years: [], year: null, view: "evaluation", limit: null,
  evaluation: null, incidents: null,
  category: recall("incident-category") || "all", query: "", expanded: new Set(), editing: null,
  warnOnly: false,                            // nur Einsätze mit aktuellen Prüfhinweisen
  filters: {},                                // Filter aus der Auswertung (Monat, Ort, …), siehe LIST_FILTERS
  incidentSort: sortFrom(recall("incident-sort")),
  current: null,                              // zuletzt geöffneter Einsatz (Tasten j/k/e, Vor/Zurück)
  editSnapshot: null,                         // Stand des Formulars beim Öffnen – Vergleich für „ungespeichert“
  tableCards: new Set(recallList("table-cards")),   // Diagramme, die als Tabelle angezeigt werden (gemerkt)
  memberSort: { field: "incidents", descending: true }, openMembers: new Set(),
  editDraft: null, editNode: null, memberOptions: [], scrollTo: null,
  upload: { token: null, reports: [], errors: [], notes: [] }, dataChanged: false,
  tenantFilter: new Set(),                    // Gesamtansicht: ausgewählte Wehren (leer = alle)
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
// Rechte des Benutzers für die ausgewählte Wehr (stats, incidents, write, admin) – geprüft wird im Backend
const can = (permission) => Boolean(config?.permissions.includes(permission));

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
/** Kurze Meldung unten; mit action ein Knopf (z. B. „Rückgängig“), der onAction aufruft. */
function toast(text, { action = null, onAction = null, duration = 3500 } = {}) {
  const el = $("#toast");
  el.textContent = text;
  if (action) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "toast-action";
    button.textContent = action;
    button.addEventListener("click", () => { el.hidden = true; onAction(); });
    el.append(button);
  }
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, duration);
}

// ------------------------------------------------------------ Diagramm-Bausteine
function niceScale(max) {
  if (max <= 0) return { max: 1, step: 1 };
  const raw = max / 4, p = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((f) => f * p).find((s) => s >= raw);
  return { max: Math.ceil(max / step) * step, step };
}

// Ziel in der Einsatzliste (Filter als Adresse, siehe listLink) für anklickbare Balken und Säulen
const linkAttributes = (link) => link ? ` data-list-link="${esc(link)}" role="link"` : "";

/** Waagerechte Balken, eine Serie. items: [{label, hint, value, tip, link}] */
function barChart(items) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return `<div class="bar-list">${items.map((i) => `
    <div class="bar-row ${i.link && i.value ? "linked" : ""}" data-tip="${esc(i.tip || `${i.label}: ${i.value}`)}${i.link && i.value ? "\nKlicken: Einsätze anzeigen" : ""}" tabindex="0"${i.value ? linkAttributes(i.link) : ""}>
      <span class="bar-label">${esc(i.label)}${i.hint ? `<small>${esc(i.hint)}</small>` : ""}</span>
      <span class="bar-track">${i.value ? `<span class="bar" style="width:${(i.value / max) * 100}%"></span>` : ""}</span>
      <span class="bar-value">${i.text ?? i.value}</span>
    </div>`).join("")}</div>`;
}

/** Säulen. groups: [{axis, tip, link, values: [{value, tone, labelled}]}]; tone = series | previous | day | night */
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
        <div class="columns-group ${g.link ? "linked" : ""}" data-tip="${esc(g.tip)}${g.link ? "\nKlicken: Einsätze anzeigen" : ""}" tabindex="0"${linkAttributes(g.link)}>${g.values.map((v) => `
          <div class="column tone-${v.tone || "series"}" style="height:${((v.value || 0) / scale.max) * 100}%">
            ${v.labelled && v.value ? `<span class="column-value">${v.text ?? v.value}</span>` : ""}
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
// permission: nötiges Recht, sonst fehlt der Reiter; visible(): eigene Regel; noYear: Titel ohne Jahr;
// help: Abschnitt (sec_…) oder Feld der Hilfe, das das ?-Symbol im Kopf in dieser Ansicht öffnet.
// Weitere Ansichten tragen sich selbst ein (admin.js).
// sub: Beschriftung im Unterreiter, wenn ein Hauptreiter mehrere Ansichten bündelt (NAV); overview, times und load
// stehen in analysis.js.
const VIEWS = {
  evaluation: { label: "Einsatzgeschehen", sub: "Einsatzgeschehen", load: loadEvaluation, render: renderEvaluation, permission: "stats.view",
    help: () => config.vg ? "sec_vg" : "sec_evaluation" },
  incidents: { label: "Einsätze", sub: "Einsätze", load: loadIncidents, render: renderIncidents, permission: "incidents.view",
    help: () => state.editing != null ? "sec_capture" : "sec_metrics" },
  // Personal gehört zu einer Wehr – nicht in der Gesamtansicht einer VG
  members: { label: "Personal", title: "Einsatzteilnahmen", load: loadMembers, render: renderMembers, permission: "people.view", single: true,
    help: "sec_members" },
};
// Hauptreiter: Jeder bündelt Ansichten (Schlüssel in VIEWS); mehrere erscheinen als Unterreiter darunter.
const NAV = [
  { key: "overview", label: "Übersicht", views: ["overview"] },
  { key: "incidents", label: "Einsätze", views: ["incidents", "fees", "records"] },
  { key: "evaluation", label: "Auswertungen", views: ["evaluation", "times", "load"] },
  { key: "members", label: "Personal", views: ["members"] },
  { key: "admin", label: "Einstellungen", views: ["admin", "dpa"] },
];
const navGroup = (view) => NAV.find((g) => g.views.includes(view));
// In der Reihenfolge der Hauptreiter; die erste erlaubte Ansicht ist der Einstieg
const allowedViews = () => NAV.flatMap((g) => g.views).filter((key) => {
  const view = VIEWS[key];
  return view && (view.visible ? view.visible() : can(view.permission)) && !(view.single && config.vg);
});

function renderTabs() {
  const allowed = allowedViews();
  $("#tabs").innerHTML = NAV.map((g) => ({ g, first: g.views.find((k) => allowed.includes(k)) })).filter((x) => x.first)
    .map(({ g, first }) => `<a href="#${first}" data-nav="${g.key}">${g.label}</a>`).join("");
}

// Unterreiter des gewählten Hauptreiters (nur bei mehreren erlaubten Ansichten)
function renderSubTabs() {
  const allowed = allowedViews(), views = (navGroup(state.view)?.views || []).filter((k) => allowed.includes(k));
  $("#subtabs-nav").hidden = views.length < 2;
  $("#subtabs").innerHTML = views.length < 2 ? "" : views.map((k) =>
    `<a href="#${k}" data-view="${k}" class="${k === state.view ? "active" : ""}">${esc(VIEWS[k].sub || VIEWS[k].label)}</a>`).join("");
}

// Name und Logos der Wehr; ohne eigene Logos (und in der Gesamtansicht) das neutrale Signet
function applyBranding() {
  const b = config.branding;
  const named = config.name !== "Einsatzstatistik";       // ohne Wehr heißt die Auswahl selbst so
  document.title = named ? `Einsatzstatistik · ${config.name}` : "Einsatzstatistik";
  $(".topbar-kicker").textContent = document.title;
  $("#footer-name").textContent = named ? `${config.name} · Einsatzstatistik` : "Einsatzstatistik";
  $("#logo-light").src = b.logo_light || "/static/img/app-icon-light.svg";
  $("#logo-light").alt = b.logo_light ? config.name : "";
  $("#logo-dark").src = b.logo_dark || "/static/img/app-icon.svg";
  $("#favicon").href = b.icon || "/static/img/app-icon.svg";
}

// Auswahl der Wehr in der Kopfzeile, nur wenn mehrere sichtbar sind
function renderScopes() {
  $("#scope-select").hidden = config.scopes.length < 2;
  $("#scope").innerHTML = config.scopes.map((s) =>
    `<option value="${esc(s.key)}" ${s.key === config.scope ? "selected" : ""}>${esc(s.name)}</option>`).join("");
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

// Personal: Anwesenheit aus der Auswertung, Einsätze je Person aus der Einsatzliste
// Einsatz in der Einsatzliste aufklappen und hinscrollen (aus Hinweisen und der Personal-Ansicht)

let viewRun = 0;
async function showView() {
  const key = parseHash().view, allowed = allowedViews();
  state.view = allowed.includes(key) ? key : allowed[0];
  const view = VIEWS[state.view];
  for (const a of $$("#tabs a")) a.classList.toggle("active", a.dataset.nav === navGroup(state.view)?.key);
  renderSubTabs();
  for (const k of Object.keys(VIEWS)) $(`#view-${k}`).hidden = k !== state.view;
  $("#page-title").textContent = view.noYear ? (view.title || view.label) : `${view.title || view.label} ${state.year}`;
  const section = $(`#view-${state.view}`), run = ++viewRun;
  section.classList.add("loading");
  $(".view-load-error", section)?.remove();
  try {
    await view.load();
    if (run !== viewRun) return;                     // inzwischen neu angefordert: das spätere Laden zeichnet
    view.render();
    if (state.view !== "incidents" && parseHash().params.toString()) history.replaceState(null, "", `#${state.view}`);
    document.dispatchEvent(new Event("app:view"));    // Ansicht gezeichnet (z. B. Sprung zu einem Einsatz)
  } catch (e) {
    if (run === viewRun) {
      const error = document.createElement("div");
      error.className = "view-load-error";
      error.innerHTML = errorBox(e.message) + '<button type="button" class="btn btn-light">Erneut versuchen</button>';
      $("button", error).addEventListener("click", () => showView());
      section.prepend(error);
    }
  } finally {
    if (run === viewRun) section.classList.remove("loading");
  }
}

async function reloadData() {
  state.evaluation = null;
  state.incidents = null;
  await loadYears();
  await showView();
  document.dispatchEvent(new Event("app:data"));     // z. B. Hinweise neu laden (records.js)
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
window.addEventListener("hashchange", (e) => {
  // Offenes, geändertes Formular: erst fragen, sonst zurück zur bisherigen Adresse
  if (!confirmLeaveEdit()) { history.replaceState(null, "", new URL(e.oldURL).hash); return; }
  applyListParams(parseHash().params);
  state.expanded.clear();
  if (state.scrollTo) state.expanded.add(state.scrollTo);   // Sprung zu einem Einsatz (openIncident)
  showView();
});
window.addEventListener("beforeunload", (e) => {
  if (incidentDirty()) e.preventDefault();
});
$("#year").addEventListener("change", (e) => {
  if (!confirmLeaveEdit()) { e.target.value = String(state.year); return; }
  state.year = Number(e.target.value);
  remember("year", state.year);
  state.expanded.clear();
  state.editing = null;
  showView();
});

// Auswertungen (Einsatzgeschehen, Zeiten & Kräfte, Belastung) und Übersicht teilen sich die Bedienung
const evaluationViews = ["overview", "evaluation", "times", "load"];
function onEvaluationViews(type, handler) {
  for (const key of evaluationViews) $(`#view-${key}`).addEventListener(type, handler);
}

onEvaluationViews("change", async (e) => {
  if (!e.target.matches("[data-plan-release]")) return;
  try {
    await apiJson(`/api/admin/${encodeURIComponent(config.tenant.slug)}/response-plan`, "PUT", { public: e.target.checked });
    state.evaluation = null;
    toast(e.target.checked ? "Eintreffen und Kräfte für alle freigegeben" : "Eintreffen und Kräfte nur noch für die Verwaltung sichtbar");
    await showView();
  } catch (err) {
    e.target.checked = !e.target.checked;
    alert(err.message);
  }
});
onEvaluationViews("keydown", (e) => {
  const link = e.target.closest("[data-list-link]");
  if (link && e.key === "Enter") location.hash = link.dataset.listLink;
});
onEvaluationViews("click", (e) => {
  const toggle = e.target.closest("[data-toggle-table]");
  if (toggle) {
    const id = toggle.dataset.toggleTable;
    state.tableCards.has(id) ? state.tableCards.delete(id) : state.tableCards.add(id);
    remember("table-cards", JSON.stringify([...state.tableCards]));
    VIEWS[state.view].render();
    return;
  }
  const limitButton = e.target.closest("[data-limit]");
  if (limitButton && Number(limitButton.dataset.limit) !== state.limit) {
    state.limit = Number(limitButton.dataset.limit);
    showView();
    return;
  }
  const filterButton = e.target.closest("[data-tenant-filter]");
  if (filterButton) {
    const slug = filterButton.dataset.tenantFilter;
    if (!slug) state.tenantFilter.clear();
    else if (state.tenantFilter.has(slug)) state.tenantFilter.delete(slug);
    else state.tenantFilter.add(slug);
    if (state.tenantFilter.size === config.tenants.length) state.tenantFilter.clear();
    showView();
    return;
  }
  const link = e.target.closest("[data-list-link]");
  if (link) { location.hash = link.dataset.listLink; return; }
  const action = e.target.closest("[data-action]")?.dataset.action;
  if (action === "print") window.print();
  if (action === "summary-export") {
    const params = new URLSearchParams({ year: state.year, limit: state.limit });
    if (state.tenantFilter.size) params.set("tenants", [...state.tenantFilter].sort().join(","));
    location.href = `/api/export/summary?${params}`;
  }
});

$("#category-filter").addEventListener("click", (e) => {
  const button = e.target.closest("button");
  if (!button) return;
  state.category = button.dataset.category;
  remember("incident-category", state.category);
  renderIncidents();
});
$("#warn-filter").addEventListener("click", () => { state.warnOnly = !state.warnOnly; renderIncidents(); });
$("#view-incidents").addEventListener("click", (e) => {
  const remove = e.target.closest("[data-remove-filter]");
  if (remove) {
    if (remove.dataset.removeFilter) delete state.filters[remove.dataset.removeFilter];
    else state.filters = {};
    renderIncidents();
    return;
  }
  if (e.target.closest("[data-clear-filters]")) { clearListFilters(); renderIncidents(); return; }
  const th = e.target.closest("[data-sort-incidents]");
  if (th && !e.target.closest(".help-btn")) {
    const field = th.dataset.sortIncidents, { incidentSort: sort } = state;
    // Erster Klick: Zahlen und Datum absteigend, Stichwort aufsteigend; weiterer Klick dreht um
    state.incidentSort = { field, descending: sort.field === field ? !sort.descending : field !== "keyword" };
    remember("incident-sort", `${field}-${state.incidentSort.descending ? "desc" : "asc"}`);
    renderIncidents();
  }
});
$("#incident-table thead").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.target.matches("[data-sort-incidents]")) e.target.click();
});
$("#search").addEventListener("input", (e) => { state.query = e.target.value; renderIncidents(); });
$("#btn-export").addEventListener("click", () => { location.href = `/api/export?year=${state.year}`; });

$("#incident-table tbody").addEventListener("click", (e) => {
  const chip = e.target.closest("[data-leader]");
  if (chip) { pickLeader(chip); return; }
  const action = e.target.closest("[data-action]");
  if (action) { handleIncidentAction(action.dataset.action, action.dataset.id, action); return; }
  if (e.target.closest("tr.detail")) return;
  const row = e.target.closest("tr.row");
  if (!row) return;
  const id = row.dataset.id;
  if (state.expanded.has(id)) {
    if (state.editing === id && !confirmLeaveEdit()) return;
    state.expanded.delete(id);
  } else {
    state.expanded.add(id);
    state.current = id;
  }
  renderIncidents();
});

$("#view-members").addEventListener("keydown", (e) => {
  const incident = e.target.closest("[data-open-incident]");
  if (incident && e.key === "Enter") openIncident(incident.dataset.openIncident, state.year);
});
$("#view-members").addEventListener("click", (e) => {
  const incident = e.target.closest("[data-open-incident]");
  if (incident) { openIncident(incident.dataset.openIncident, state.year); return; }
  const row = e.target.closest("tr[data-member]");
  if (row) {
    const id = Number(row.dataset.member);
    if (state.openMembers.has(id)) state.openMembers.delete(id); else state.openMembers.add(id);
    renderMembers();
    return;
  }
  const th = e.target.closest("[data-sort]");
  if (!th) return;
  const field = th.dataset.sort;
  state.memberSort = { field, descending: state.memberSort.field === field ? !state.memberSort.descending : field !== "name" };
  renderMembers();
});

// Einheitsführung von Hand geändert → Hervorhebung der Namen anpassen.
// Stichwort: Suche im Katalog, ganzes Stichwort (B207, B2.07) gleich trennen – der Server trennt beim Speichern ebenso.
const formOf = (el) => el.closest("[data-form], .preview-card");
for (const container of [$("#incident-table tbody"), $("#previews")]) {
  container.addEventListener("input", (e) => {
    if (e.target.name === "unit_leader") highlightLeader(formOf(e.target));
    if (e.target.name === "keyword") showKeywordSuggestions(e.target);
  });
  container.addEventListener("change", (e) => {
    if (e.target.name === "keyword") splitKeyword(formOf(e.target));
  });
  container.addEventListener("keydown", (e) => {
    if (e.target.name === "keyword") navigateKeywordSuggestions(e);
  });
  container.addEventListener("focusout", (e) => {
    if (e.target.name === "keyword") closeKeywordSuggestions();
  });
}

function splitKeyword(form) {
  const keyword = $('input[name="keyword"]', form), subcode = $('input[name="subcode"]', form);
  const m = keyword.value.trim().match(/^([a-z]\d)\s*[.\s]?\s*(\d{0,2})$/i);
  // Freier Text ohne Auswahl aus der Liste ist kein Stichwort
  keyword.classList.toggle("missing", !m && !!keyword.value.trim());
  if (!m) return;
  keyword.value = m[1].toUpperCase();
  if (m[2]) subcode.value = m[2].padStart(2, "0");
}

// Dialoge
for (const button of $$("[data-close]")) {
  button.innerHTML = ICON_CLOSE;
  button.addEventListener("click", () => {
    if (button.dataset.close === "pdf-dialog" && acceptingReports) { toast("Bitte die laufende Übernahme abwarten."); return; }
    $(`#${button.dataset.close}`).close();
  });
}
const pdfDialog = $("#pdf-dialog");
pdfDialog.addEventListener("cancel", (event) => {
  if (acceptingReports) { event.preventDefault(); toast("Bitte die laufende Übernahme abwarten."); }
});
async function openImport() {
  if (!state.incidents) { try { await loadIncidents(); } catch (e) { /* nur für Vorschläge */ } }
  updateDatalists();
  if (state.upload.reports.every((r) => r.saved || isUnchanged(r))) {
    state.upload = { token: null, reports: [], errors: [], notes: [] };
    $("#pdf-error").hidden = true;
    renderPreviews();
  }
  if (!pdfDialog.open) pdfDialog.showModal();
}
$("#btn-pdf").addEventListener("click", openImport);
pdfDialog.addEventListener("close", async () => {
  if (!acceptingReports) {
    try { await discardUpload(); } catch (e) { toast(e.message); }
  }
  if (state.dataChanged) { state.dataChanged = false; await reloadData(); }
});
const dropzone = $("#dropzone");
["dragenter", "dragover"].forEach((t) => dropzone.addEventListener(t, (e) => { e.preventDefault(); dropzone.classList.add("dragging"); }));
["dragleave", "drop"].forEach((t) => dropzone.addEventListener(t, () => dropzone.classList.remove("dragging")));
dropzone.addEventListener("drop", (e) => { e.preventDefault(); readPdfs(e.dataTransfer.files); });
dropzone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#pdf-input").click(); } });
$("#pdf-input").addEventListener("change", (e) => { readPdfs(e.target.files); e.target.value = ""; });
// Berichte überall aufs Fenster ziehen: öffnet den Import und liest sie ein (nur mit Recht zum Einlesen)
const draggingFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files") && !$("#btn-pdf").hidden && !pdfDialog.open;
let dragDepth = 0;
window.addEventListener("dragenter", (e) => {
  if (!draggingFiles(e)) return;
  dragDepth++;
  document.body.classList.add("drop-target");
});
window.addEventListener("dragleave", (e) => {
  if (!draggingFiles(e)) return;
  dragDepth = Math.max(0, dragDepth - 1);
  if (!dragDepth) document.body.classList.remove("drop-target");
});
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", async (e) => {
  e.preventDefault();
  const files = draggingFiles(e) ? e.dataTransfer.files : null;
  dragDepth = 0;
  document.body.classList.remove("drop-target");
  if (!files?.length) return;
  await openImport();
  readPdfs(files);
});
$("#previews").addEventListener("change", (e) => {
  const i = e.target.dataset.replace;
  if (i === undefined) return;
  // Eingaben behalten: Formularwerte vor dem Neuzeichnen übernehmen
  keepPreviewInput();
  state.upload.reports[i].replace = e.target.checked;
  renderPreviews();
});
$("#previews").addEventListener("click", (e) => {
  const chip = e.target.closest("[data-leader]");
  if (chip) { pickLeader(chip); return; }
  const button = e.target.closest("[data-accept]");
  if (button) acceptReport(Number(button.dataset.accept));
});

$("#scope").addEventListener("change", async (e) => {
  if (uploadBusy || acceptingReports) { e.target.value = config.scope; toast("Bitte den laufenden Import abwarten."); return; }
  if (state.upload.reports.some((r) => !r.saved && !isUnchanged(r)) &&
      !window.confirm("Offene Importvorschauen verwerfen und Ansicht wechseln?")) { e.target.value = config.scope; return; }
  // Ungespeicherte Einstellungen (admin.js) bzw. Einsatz: erst fragen, sonst wechselte die Wehr auf dem Server trotzdem
  if (typeof confirmDiscard === "function" && !confirmDiscard()) { e.target.value = config.scope; return; }
  if (!confirmLeaveEdit()) { e.target.value = config.scope; return; }
  try {
    await discardUpload();
    await apiJson("/api/scope", "POST", { key: e.target.value });
    location.reload();
  } catch (err) {
    alert(err.message);
  }
});

// ------------------------------------------------------------ Tastenkürzel (Übersicht in der Hilfe: sec_shortcuts)
const typing = (el) => Boolean(el.closest?.("input, textarea, select, [contenteditable]"));

function focusSearch() {
  if (!allowedViews().includes("incidents")) return;
  if (state.view === "incidents") { $("#search").focus(); $("#search").select(); return; }
  document.addEventListener("app:view", () => $("#search").focus(), { once: true });
  location.hash = "#incidents";
}

document.addEventListener("keydown", (e) => {
  if (e.defaultPrevented || $("dialog[open]")) return;
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key === "z" && !typing(e.target) && pendingDeletes.size) {
    e.preventDefault();
    undoDelete([...pendingDeletes.keys()].at(-1));
    return;
  }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.key === "Escape") {
    if (e.target.id === "search") { e.target.blur(); return; }
    if (state.view !== "incidents") return;
    if (state.editing != null) { if (confirmLeaveEdit()) renderIncidents(); return; }
    if (state.expanded.size) { state.expanded.clear(); renderIncidents(); }
    return;
  }
  if (typing(e.target)) return;
  const incidents = state.view === "incidents" && state.incidents;
  if (e.key === "/") { e.preventDefault(); focusSearch(); }
  else if (e.key === "i" && !$("#btn-pdf").hidden) { e.preventDefault(); openImport(); }
  else if (e.key === "?") { e.preventDefault(); openHelp("sec_shortcuts"); }
  else if (incidents && (e.key === "j" || e.key === "k")) { e.preventDefault(); stepIncident(e.key === "j" ? 1 : -1); }
  else if (incidents && e.key === "e") {
    const incident = state.incidents.incidents.find((x) => x.id === state.current);
    if (!incident?.can_edit || state.editing === incident.id || !confirmLeaveEdit()) return;
    e.preventDefault();
    state.expanded.add(incident.id);
    startEditing(incident.id);
  }
});

// Start
(async () => {
  const fail = (message) => {
    $("#view-evaluation").hidden = false;
    $("#view-evaluation").innerHTML = errorBox(message);
  };
  try {
    config = await api("/api/config");
  } catch (e) {
    fail(e.message);
    return;
  }
  applyBranding();
  setupHelp();
  if (config.user) {
    $("#logout").hidden = false;
    $("#logout button").dataset.tip = `Abmelden (${config.user})`;
  }
  if (!config.tenants.length && !config.superadmin && !config.dpa_blocked.length) {
    fail("Dir ist keine Wehr zugeordnet.");
    return;
  }
  renderTabs();
  if (!config.tenants.length) {               // Superadmin ohne Wehr bzw. nur Wehren ohne AVV: Verwaltung, AVV
    $("#btn-pdf").hidden = true;
    $(".year-select:not(#scope-select)").hidden = true;
    await showView();
    return;
  }
  renderScopes();
  $("#btn-pdf").hidden = !can("reports.import");
  $("#btn-export").hidden = !can("incidents.export");
  try {
    await loadYears();
  } catch (e) {
    fail(e.message);
    return;
  }
  state.limit = config.default_limit;
  applyListParams(parseHash().params);       // Filter aus einem geteilten Link
  await showView();
  document.dispatchEvent(new Event("app:data"));
})();
