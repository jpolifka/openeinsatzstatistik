// Abbrüche & Anlagen, Fahrzeuge & Atemschutz, Brand & Rettung (static/operations.js, nutzt Bausteine aus analysis.js).
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function load() {
  const els = {};
  const el = (key) => (els[key] ||= { innerHTML: "", hidden: false });
  const context = vm.createContext({
    VIEWS: {}, document: { addEventListener() {} }, window: { scrollTo() {} },
    state: { year: 2026, incidents: null, evaluation: null }, config: { vg: null, tenant: { slug: "a" }, permissions: ["stats.view"] },
    $: el, esc: (s) => String(s ?? ""), num: (n) => n == null ? "–" : String(n), percent: (q) => q == null ? "–" : `${Math.round(q * 100)} %`,
    minutes: (m) => m == null ? "–" : `${m} min`, plural: (n, one, many) => `${n} ${n === 1 ? one : many}`,
    formatDuration: (m) => m == null ? "–" : `${m} min`, formatHours: (m) => m == null ? "–" : `${Math.round(m / 60)} h`,
    formatDate: (iso) => iso ? iso.slice(0, 10) : "–",
    shareOf: (c, t) => `${c}/${t}`, can: () => true,
    evaluationToolbar: () => "", listLink: () => "#incidents", loadEvaluation: async () => {}, loadIncidents: async () => {},
    chartCard: ({ title, subtitle = "", chart, table, extra = "" }) => `[${title}]${subtitle}${chart}${table}${extra}`, barChart: (items) => items.map((i) => `${i.label}=${i.text ?? i.value}`).join(";"),
    columnChart: () => "", dataTable: (head, rows) => rows.map((r) => r.join("|")).join("\n"),
    keyFigures: (e) => e.map(([v, l]) => `${v} ${l}`).join(","), MISSING_LABELS: {}, records: { notices: [] }, renderNotices() {},
  });
  for (const file of ["analysis.js", "operations.js"]) vm.runInContext(fs.readFileSync(`static/${file}`, "utf8"), context);
  return { context, els };
}

const dist = (valid, total, median) => ({ valid, total, average: median, median, p90: median && median + 5 });

test("Ansichten sind registriert und im Unterreiter benannt", () => {
  const { context } = load();
  for (const key of ["aborts", "resources", "fire"]) {
    assert.equal(typeof context.VIEWS[key].render, "function");
    assert.equal(context.VIEWS[key].permission, "stats.view");
  }
  const nav = fs.readFileSync("static/app.js", "utf8");
  assert.match(nav, /views: \["evaluation", "times", "load", "aborts", "resources", "fire"\]/);
  const html = fs.readFileSync("static/index.html", "utf8");
  for (const key of ["aborts", "resources", "fire"]) assert.match(html, new RegExp(`id="view-${key}"`));
  assert.match(html, /operations\.js/);
});

test("Abbrüche: Gruppen, Anlagen mit Fehlalarmquote und Abdeckung", () => {
  const { context, els } = load();
  context.state.evaluation = {
    aborts: { total: 20, aborted: 8, share: 0.4,
      kinds: [{ kind: "false_alarm", label: "Fehlalarm / kein Ereignis", count: 5, share: 0.625 },
        { kind: "not_needed", label: "Nicht erforderlich", count: 2, share: 0.25 }, { kind: "standby", label: "In Bereitstellung", count: 1, share: 0.125 },
        { kind: "other", label: "Sonstiger Grund", count: 0, share: 0 }],
      reasons: [{ reason: "Täuschungsalarm", count: 5, kind: "false_alarm" }],
      categories: [{ code: "B", name: "Brand", count: 10, aborted: 6, share: 0.6 }],
      fire_alarm_systems: { count: 9, aborted: 6, false_alarms: 5, share: 0.667 } },
    alarm_systems: { total: 9, identified: 7, rows: [
      { system: "301986", building: "WH Musterhaus", count: 5, aborted: 4, false_alarms: 3, false_share: 0.6, last: "2026-05-01T10:00:00", known: true },
      { system: null, building: null, count: 2, aborted: 0, false_alarms: 0, false_share: 0, last: null, known: false }] },
  };
  context.renderAborts();
  const html = els["#view-aborts"].innerHTML;
  assert.match(html, /Abgebrochene Einsätze/);
  assert.match(html, /Fehlalarm \/ kein Ereignis=5 · 63 %/);
  assert.match(html, /WH Musterhaus · Anlage 301986=5 · 3 Fehlalarm/);
  assert.match(html, /7 von 9 Einsätzen auswertbar/);
  assert.match(html, /ohne Angabe von Anlage oder Objekt/);
});

test("Fahrzeuge: nur bereitgestellt und fehlende Angaben werden benannt, Atemschutz ohne Daten ist keine Null", () => {
  const { context, els } = load();
  context.state.evaluation = {
    vehicle_usage: { total: 10, rows: [
      { call_sign: "02/45", label: "HLF 20", alerted: 8, drove: 8, deployed: 6, standby: 1, unknown: 1, hours: 12, minutes_valid: 8, crew_avg: 4.5, standby_share: 0.143, known: 7 },
      { call_sign: "02/24", label: "", alerted: 3, drove: 1, deployed: 0, standby: 0, unknown: 3, hours: 0, minutes_valid: 0, crew_avg: null, standby_share: null, known: 0 }] },
    respiratory: { total: 10, known: 0, with_agt: 0, share: null, carriers: 0, persons: 0, minutes: 0, average_minutes: null, longest_minutes: null },
  };
  context.renderResources();
  const html = els["#view-resources"].innerHTML;
  assert.match(html, /02\/45 · HLF 20=8 · 1× bereit/);
  assert.match(html, /Bei 4 von 11 Alarmierungen fehlt die Angabe/);
  assert.match(html, /Keine Angaben zum Atemschutz/);
  assert.doesNotMatch(html, /0 von 0/);
});

test("Brand & Rettung: Zeiten, Taktik, Brandwache und Zahl der Berichte mit Angabe", () => {
  const { context, els } = load();
  const field = (total, incidents, reported) => ({ total, incidents, reported });
  context.state.evaluation = {
    fire_course: { total: 12, to_control: dist(8, 12, 21), to_out: dist(7, 12, 48),
      tactics: [{ tactic: "Innenangriff", count: 4, control: dist(4, 4, 18) }], fire_watches: 2, fire_watch_hours: 5.5, fire_watch_valid: 2 },
    casualties: { total: 40, incidents_with_persons: 6, fields: { rescued: field(7, 4, 10), rescued_animals: field(0, 0, 2),
      injured: field(3, 3, 8), injured_firefighters: field(1, 1, 2), deceased: field(2, 2, 4) } },
  };
  context.renderFire();
  const html = els["#view-fire"].innerHTML;
  assert.match(html, /Median ab Eintreffen · 8 von 12 Einsätzen auswertbar/);
  assert.match(html, /Innenangriff\|4\|18 min/);
  assert.match(html, /2 Brandwachen mit zusammen 5\.5 Stunden/);
  assert.match(html, /Menschen gerettet\|7\|<a href="#incidents">4<\/a>\|10 von 40/);
});
