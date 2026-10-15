// Einsatzliste und -detail: Adresse und Filter, Löschen mit „Rückgängig“, Schutz vor ungespeicherten Änderungen
// und Maskierung von Nutzerdaten. Geladen werden die echten Dateien; Browser und Server sind ersetzt.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const read = (file) => fs.readFileSync(`static/${file}`, "utf8");
const app = read("app.js");
// Reine Hilfsfunktionen aus app.js (Sortierung, esc, Formate), ohne den Seitenaufbau
const helpers = app.slice(app.indexOf("const INCIDENT_SORTS"), app.indexOf("// Fachkonstanten"))
  + app.slice(app.indexOf("const esc ="), app.indexOf("const ICON_CLOSE"));

function element() {
  return { innerHTML: "", textContent: "", value: "", hidden: false, dataset: {},
    classList: { add() {}, remove() {}, toggle() {} }, setAttribute() {}, replaceWith() {} };
}

function setup(overrides = {}) {
  const elements = new Map(), timers = new Map(), calls = [], toasts = [], listeners = {};
  let timerId = 0;
  const location = { hash: "" };
  const history = { replaced: [], replaceState(_, __, hash) { this.replaced.push(hash); location.hash = hash; } };
  const context = vm.createContext({
    console, URLSearchParams, Event: class {}, CSS: { escape: (s) => s },
    location, history,
    window: { addEventListener: (name, fn) => { listeners[name] = fn; }, confirm: () => true },
    document: { dispatchEvent() {}, addEventListener() {}, removeEventListener() {} },
    confirm: () => true, alert: () => {},
    state: { view: "incidents", query: "", category: "all", warnOnly: false, todoOnly: false, filters: {},
      incidentSort: { field: "started_at", descending: true }, tenantFilter: new Set(), expanded: new Set(),
      editing: null, editSnapshot: null, editNode: null, current: null,
      incidents: { year: 2025, incidents: [] } },
    config: { default_limit: 10, second_limit: 15, categories: [], tenants: [], vg: null, keyword_catalog: [] },
    $: (key) => { if (!elements.has(key)) elements.set(key, element()); return elements.get(key); },
    $$: () => [],
    helpButton: () => "", keywordName: () => undefined, toast: (text, options) => toasts.push({ text, ...options }),
    api: async (url, options) => { calls.push({ url, options }); return {}; },
    loadYears: async () => {}, showView: async () => {},
    fetch: (url, options) => calls.push({ url, options, keepalive: true }),
    setTimeout: (fn) => { timers.set(++timerId, fn); return timerId; },
    clearTimeout: (id) => timers.delete(id),
    ...overrides,
  });
  vm.runInContext(helpers, context);
  vm.runInContext(read("imports.js").slice(0, read("imports.js").indexOf("function showUploadError")), context);
  vm.runInContext(read("incident_list.js"), context);
  vm.runInContext(read("incident_detail.js"), context);
  vm.runInContext("renderIncidents = () => {};", context);          // Zeichnen prüft ein eigener Test
  return { context, elements, timers, calls, toasts, listeners, location, history };
}

const run = (ctx, code) => vm.runInContext(code, ctx.context);

// ------------------------------------------------------------ Adresse und Filter
test("Adresse mit Filtern wird übernommen und ergibt dieselbe Adresse zurück", () => {
  const ctx = setup();
  ctx.location.hash = "#incidents?cat=B&month=3&q=brand&sort=number-asc&warn=1&area=Rheinbrohl";
  run(ctx, "applyListParams(parseHash().params)");
  assert.equal(run(ctx, "state.category"), "B");
  assert.deepEqual(JSON.parse(run(ctx, "JSON.stringify(state.filters)")), { month: "3", area: "Rheinbrohl" });
  assert.equal(run(ctx, "state.warnOnly"), true);
  const entries = JSON.parse(run(ctx, "JSON.stringify([...listParams().entries()])")).sort();
  assert.deepEqual(entries, [["area", "Rheinbrohl"], ["cat", "B"], ["month", "3"], ["q", "brand"], ["sort", "number-asc"],
    ["warn", "1"]]);
});

test("Unbekannte Parameter und ungültige Sortierung werden verworfen", () => {
  const ctx = setup();
  ctx.location.hash = "#incidents?evil=1&sort=password-asc&month=5";
  run(ctx, "applyListParams(parseHash().params)");
  assert.deepEqual(JSON.parse(run(ctx, "JSON.stringify(state.filters)")), { month: "5" });
  assert.equal(run(ctx, "state.incidentSort.field"), "started_at");
  assert.equal(run(ctx, "listParams().toString()"), "month=5");        // Standardsortierung steht nicht in der Adresse
});

test("Ohne Parameter bleibt der aktuelle Filterstand", () => {
  const ctx = setup();
  run(ctx, 'state.query = "Wald"; state.filters = { month: "2" }; applyListParams(new URLSearchParams(""))');
  assert.equal(run(ctx, "state.query"), "Wald");
  assert.equal(run(ctx, "state.filters.month"), "2");
});

test("syncHash schreibt nur in der Einsatzliste und nur bei Änderung", () => {
  const ctx = setup();
  run(ctx, 'state.filters = { month: "3" }');
  run(ctx, "syncHash()");
  run(ctx, "syncHash()");
  assert.deepEqual(ctx.history.replaced, ["#incidents?month=3"]);
  run(ctx, 'state.view = "evaluation"; state.filters = { month: "4" }; syncHash()');
  assert.equal(ctx.history.replaced.length, 1);
});

test("listLink lässt leere Werte weg und übernimmt die Wehrauswahl der Gesamtansicht", () => {
  const ctx = setup();
  assert.equal(run(ctx, 'listLink({ month: 3, area: null, hour: "" })'), "#incidents?month=3");
  assert.equal(run(ctx, "listLink({})"), "#incidents");
  run(ctx, 'state.tenantFilter = new Set(["wehr-b", "wehr-a"])');
  assert.equal(run(ctx, "listLink({ month: 3 })"), "#incidents?tenants=wehr-a%2Cwehr-b&month=3");
});

// ------------------------------------------------------------ Löschen mit „Rückgängig“
const incident = (id = "wehr-a1:7", revision = 4) => ({ id, revision, number: 7, year: 2025, started_at: "2025-03-12T10:00:00" });

test("Rückgängig vor Ablauf sendet kein DELETE und stellt den Einsatz wieder her", () => {
  const ctx = setup();
  run(ctx, "state.incidents.incidents = [" + JSON.stringify(incident()) + "]; deleteIncident('wehr-a1:7')");
  assert.equal(run(ctx, "state.incidents.incidents.length"), 0);
  assert.equal(ctx.timers.size, 1);
  ctx.toasts[0].onAction();
  assert.equal(ctx.timers.size, 0);
  assert.equal(run(ctx, "state.incidents.incidents.length"), 1);
  assert.equal(run(ctx, "pendingDeletes.size"), 0);
  assert.deepEqual(ctx.calls, []);
});

test("Nach Ablauf geht genau ein DELETE mit der Revision hinaus", async () => {
  const ctx = setup();
  run(ctx, "state.incidents.incidents = [" + JSON.stringify(incident()) + "]; deleteIncident('wehr-a1:7')");
  const [fire] = [...ctx.timers.values()];
  await fire();
  await run(ctx, "commitDelete('wehr-a1:7')");                        // zweiter Auslöser darf nichts mehr senden
  assert.equal(ctx.calls.length, 1);
  assert.equal(ctx.calls[0].url, "/api/incidents/wehr-a1%3A7?revision=4");
  assert.equal(ctx.calls[0].options.method, "DELETE");
});

test("Rückgängig nach dem Löschen ist wirkungslos", async () => {
  const ctx = setup();
  run(ctx, "state.incidents.incidents = [" + JSON.stringify(incident()) + "]; deleteIncident('wehr-a1:7')");
  await [...ctx.timers.values()][0]();
  run(ctx, "undoDelete('wehr-a1:7')");
  assert.equal(run(ctx, "state.incidents.incidents.length"), 0);
});

test("Beim Schließen der Seite werden offene Löschungen sofort gesendet und nicht doppelt", () => {
  const ctx = setup();
  run(ctx, "state.incidents.incidents = [" + JSON.stringify(incident("a:1", 2)) + "," + JSON.stringify(incident("a:2", 5)) + "]");
  run(ctx, "deleteIncident('a:1'); deleteIncident('a:2')");
  ctx.listeners.pagehide();
  assert.deepEqual(ctx.calls.map((c) => c.url), ["/api/incidents/a%3A1?revision=2", "/api/incidents/a%3A2?revision=5"]);
  assert.ok(ctx.calls.every((c) => c.keepalive && c.options.method === "DELETE"));
  assert.equal(ctx.timers.size, 0);
  assert.equal(run(ctx, "pendingDeletes.size"), 0);
});

test("Fehlgeschlagenes Löschen meldet den Fehler und lädt die Liste neu", async () => {
  const alerts = [];
  let reloaded = 0;
  const ctx = setup({ api: async () => { throw new Error("Revision veraltet"); },
    alert: (text) => alerts.push(text), showView: async () => { reloaded++; } });
  run(ctx, "state.incidents.incidents = [" + JSON.stringify(incident()) + "]; deleteIncident('wehr-a1:7')");
  await [...ctx.timers.values()][0]();
  assert.match(alerts[0], /nicht gelöscht: Revision veraltet/);
  assert.equal(reloaded, 1);
  assert.equal(run(ctx, "state.incidents"), null);
});

// ------------------------------------------------------------ Ungespeicherte Änderungen
test("confirmLeaveEdit fragt nur bei geändertem Formular und bricht bei „Nein“ ab", () => {
  let asked = 0, answer = false;
  let current = "Rheinbrohl";
  const ctx = setup({ confirm: () => { asked++; return answer; } });
  ctx.context.formValue = () => ({ place: current });
  run(ctx, "readIncidentForm = () => formValue()");
  assert.equal(run(ctx, "confirmLeaveEdit()"), true);                 // nichts in Bearbeitung
  run(ctx, 'state.editing = "a:1"; state.editSnapshot = JSON.stringify({ place: "Rheinbrohl" })');
  assert.equal(run(ctx, "confirmLeaveEdit()"), true);                 // unverändert: keine Rückfrage
  assert.equal(asked, 0);
  current = "Neuwied";
  run(ctx, 'state.editing = "a:1"; state.editSnapshot = JSON.stringify({ place: "Rheinbrohl" })');
  assert.equal(run(ctx, "confirmLeaveEdit()"), false);
  assert.equal(run(ctx, "state.editing"), "a:1");                     // Bearbeitung bleibt offen
  answer = true;
  assert.equal(run(ctx, "confirmLeaveEdit()"), true);
  assert.equal(run(ctx, "state.editing"), null);
  assert.equal(asked, 2);
});

// ------------------------------------------------------------ Maskierung von Nutzerdaten
const PAYLOAD = `"><img src=x onerror=alert(1)>`;

function hostileIncident() {
  const p = PAYLOAD;
  return { id: "wehr-a1:1", number: 1, year: 2025, started_at: "2025-03-12T10:00:00", ended_at: "2025-03-12T11:00:00",
    keyword: "B", subcode: p, description: p, place: p, unit_leader: p, people_visible: true, people_count: 1,
    people: [{ id: 1, name: p, role: p, vehicle: p, leader: false, leader_name: p, agt: 1, agt_min: 3, new: true }],
    vehicles: [{ call_sign: "02/45", substitute: p, crew: 3, departed: "10:03:00", arrived: "10:08:00", turnout_min: 3,
      arrival_min: 8, deployed: 0, respiratory: 2 }, { call_sign: p, crew: null, departed: null, arrived: null }],
    warnings: [p], current_warnings: [p], crew_total: 3, arrival_min: 8, on_time: true, weekend_or_holiday: 0, daytime: true,
    station_staff: 0, tenant: p, source: "pdf", filename: p, bks_url: "https://example.org/b", bks_report_id: p,
    bks_record_id: p + "2", abort_reason: p, building: p, alarm_system: p, tactic: p, can_edit: true, can_delete: true };
}

function assertInert(html) {
  assert.ok(!html.includes("<img"), "ungeschütztes <img> in der Ausgabe");
  // Werte in Anführungszeichen entfernen: Text „onerror=“ in einem Attributwert ist harmlos, ein Attributname nicht
  const tag = html.replace(/"[^"]*"/g, '""').match(/<[^>]*\son\w+\s*=[^>]*>/);
  assert.equal(tag, null, `Ereignisattribut in einem Tag: ${tag && tag[0]}`);
}

test("Einsatzdetail maskiert alle Textfelder des Berichts", () => {
  const ctx = setup();
  const html = run(ctx, `incidentDetail(${JSON.stringify(hostileIncident())})`);
  assert.ok(html.includes("&lt;img src=x onerror=alert(1)&gt;"));    // der Text ist da, aber nur als Text
  assertInert(html);
});

test("Einsatzliste maskiert Beschreibung, Ort, Fahrzeuge, Hinweise und Wehr", () => {
  const ctx = setup({ weekdayShort: () => "", editForm: () => "" });
  const e = hostileIncident();
  run(ctx, `state.incidents.incidents = [${JSON.stringify(e)}]; state.expanded.add(${JSON.stringify(e.id)});
    config.vg = "vg"; config.tenants = [{ slug: ${JSON.stringify(PAYLOAD)}, name: ${JSON.stringify(PAYLOAD)} }];
    state.todoOnly = false;`);
  vm.runInContext(read("incident_list.js").slice(read("incident_list.js").indexOf("function renderIncidents")), ctx.context);
  run(ctx, "renderIncidents()");
  const html = ctx.elements.get("#incident-table tbody").innerHTML;
  assert.ok(html.includes("row"), "Zeile wurde gezeichnet");
  assertInert(html);
});
