// Übersicht, Zeiten & Kräfte und Belastung (static/analysis.js) sowie Reiter-Aufbau (NAV in app.js).
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function load(extra = {}) {
  const els = {};
  const el = (key) => (els[key] ||= { innerHTML: "", hidden: false });
  const context = vm.createContext({
    VIEWS: {}, document: { addEventListener() {} }, window: { scrollTo() {} },
    state: { year: 2025, incidents: null, evaluation: null }, config: { vg: null, tenant: { slug: "a" }, permissions: ["stats.view"] },
    $: el, esc: (s) => String(s ?? ""), num: (n) => n == null ? "–" : String(n), percent: (q) => q == null ? "–" : `${Math.round(q * 100)} %`,
    minutes: (m) => m == null ? "–" : `${m} min`, plural: (n, one, many) => `${n} ${n === 1 ? one : many}`,
    formatDuration: (m) => m == null ? "–" : `${m} min`, formatHours: (m) => m == null ? "–" : `${Math.round(m / 60)} h`,
    helpButton: () => "", shareOf: (c, t) => `${c}/${t}`, can: (p) => context.config.permissions.includes(p),
    evaluationToolbar: () => "", listLink: (f) => `#incidents?${new URLSearchParams(f)}`, loadEvaluation: async () => {}, loadIncidents: async () => {},
    chartCard: ({ title, chart, table }) => `[${title}]${chart}${table}`, barChart: (items) => items.map((i) => `${i.label}=${i.text ?? i.value}`).join(";"),
    columnChart: (groups) => groups.map((g) => `${g.axis}=${g.values[0].text}`).join(";"), dataTable: (head, rows) => rows.map((r) => r.join("|")).join("\n"),
    keyFigures: (e) => e.map(([v, l]) => `${v} ${l}`).join(","), MISSING_LABELS: { arrival: "ohne Eintreffzeit", leader: "ohne Einheitsführung" },
    records: { notices: [] }, renderNotices() {}, ...extra,
  });
  vm.runInContext(fs.readFileSync("static/analysis.js", "utf8"), context);
  return { context, els };
}

const distribution = (valid, total, median) => ({ valid, total, average: median, median, p90: median + 2 });
const evaluation = (overrides = {}) => ({
  response_plan_hidden: [], response_plan: { limit: 10, total: { rate: 0.5, on_time: 1, count: 2 } },
  statistics: { count: 57, per_week: 1.1, duration_avg_min: 40, duration_total_min: 600, staff_recorded: 10, staff_total: 57 },
  tenants: null,
  coverage: { total: 57, rows: [{ key: "duration", valid: 57 }, { key: "arrival", valid: 42 }, { key: "leader", valid: 50 }] },
  timing: { total: 57, turnout: distribution(42, 57, 4), arrival: distribution(42, 57, 9), travel: distribution(60, 70, 5),
    build_up: [{ minutes: 5, crew: 0, valid: 42, total: 57 }, { minutes: 10, crew: 3.2, valid: 42, total: 57 }],
    by_window: [{ key: "weekday_day", day_type: "Werktag", hours: "06–18", count: 3, small: true, turnout: distribution(3, 3, 4), arrival: distribution(3, 3, 9) }],
    by_area: [{ name: "Ort", count: 9, small: false, turnout: distribution(9, 9, 4), arrival: distribution(9, 9, 9) }] },
  workload: { total: 57, duration: distribution(50, 57, 60), long: { count: 5, minutes: 120, hours: 12, staff_recorded: 3, staff_total: 5, staff_hours: 20 },
    night: { count: 4, hours: 3, staff_recorded: 4, staff_total: 4, staff_hours: 9 }, weekend: { count: 6, hours: 5, staff_recorded: 6, staff_total: 6, staff_hours: 12 },
    buckets: [{ label: "bis 30 min", count: 10 }], overlap: { valid: 57, total: 57, incidents_with_overlap: 2, max_concurrent: 2, overlap_minutes: 30 } },
  ...overrides,
});

test("Datenabdeckung nennt Fallzahl und Fehlendes", () => {
  const { context } = load();
  assert.equal(context.coverageText(42, 57), "42 von 57 Einsätzen auswertbar");
  assert.equal(context.coverageText(57, 57), "alle 57 Einsätze auswertbar");
  assert.equal(context.coverageText(0, 0), "keine Einsätze");
  assert.equal(context.coverageText(60, 70, vm.runInContext("VEHICLE_UNIT", context)), "60 von 70 Fahrzeugen auswertbar");
});

test("Zeiten & Kräfte zeigt Median, 90 %, Kräfteaufbau und kennzeichnet kleine Gruppen", () => {
  const { context, els } = load();
  context.state.evaluation = evaluation();
  context.renderTimes();
  const html = els["#view-times"].innerHTML;
  assert.match(html, /Median · 90 % ≤ 6 min · 42 von 57 Einsätzen auswertbar/);
  assert.match(html, /60 von 70 Fahrzeugen auswertbar/);
  assert.match(html, /10 min=3\.2/);
  assert.match(html, /wenige Fälle/);
});

test("Zeiten & Kräfte ohne Freigabe zeigt nur den Hinweis", () => {
  const { context, els } = load();
  context.state.evaluation = evaluation({ timing: null, response_plan_hidden: ["Wehr A"] });
  context.renderTimes();
  assert.match(els["#view-times"].innerHTML, /noch nicht freigegeben/);
  assert.doesNotMatch(els["#view-times"].innerHTML, /Median/);
});

test("Belastung zeigt lange, nächtliche Einsätze und die Überschneidung mit Vorbehalt", () => {
  const { context, els } = load();
  context.state.evaluation = evaluation();
  context.renderWorkload();
  const html = els["#view-load"].innerHTML;
  assert.match(html, /ab 120 min/);
  assert.match(html, /nicht, dass dieselben Kräfte gebunden waren/);
  assert.match(html, /3 von 5 Einsätzen erfasst/);
});

test("Übersicht verlinkt fehlende Angaben und blendet die Einheitsführung ohne Namensrecht aus", () => {
  const { context, els } = load();
  context.state.evaluation = evaluation();
  context.state.incidents = { incidents: [{ current_warnings: ["x"] }, { current_warnings: [] }] };
  context.renderOverview();
  const html = els["#view-overview"].innerHTML;
  assert.match(html, /1 Einsatz hat<\/a>|1 Einsatz hat Prüfhinweise/);
  assert.match(html, /15 Einsätze ohne Eintreffzeit/);
  assert.match(html, /missing=arrival/);
  assert.doesNotMatch(html, /ohne Einheitsführung/);
});

test("Reiter: Auswertungen bündelt drei Ansichten, Verwaltung zwei", () => {
  const source = fs.readFileSync("static/app.js", "utf8");
  const nav = source.slice(source.indexOf("const NAV = ["), source.indexOf("function renderTabs()"));
  const context = vm.createContext({ VIEWS: { overview: { permission: "p" }, evaluation: { permission: "p" }, times: { permission: "p" },
    load: { permission: "p" }, incidents: { permission: "p" }, members: { permission: "p", single: true }, admin: { visible: () => true } },
    can: () => true, config: { vg: null } });
  vm.runInContext(nav + "; this.NAV = NAV; this.allowedViews = allowedViews; this.navGroup = navGroup;", context);
  assert.deepEqual([...context.allowedViews()], ["overview", "incidents", "evaluation", "times", "load", "members", "admin"]);
  assert.equal(context.navGroup("times").key, "evaluation");
  assert.equal(context.navGroup("dpa").key, "admin");
  context.config.vg = {};
  assert.ok(!context.allowedViews().includes("members"));
});
