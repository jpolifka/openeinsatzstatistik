// Importzustand unabhängig vom Browser: Rennen, Abbruch und Revisionsvertrag.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function setup() {
  const elements = new Map();
  const calls = [], asked = [], errors = [], toasts = [], answers = { confirm: true };
  const context = vm.createContext({
    state: { upload: { token: null, reports: [] } },
    config: {}, console,
    FormData: class { append() {} },
    $: (key) => {
      if (!elements.has(key)) elements.set(key, { hidden: false, disabled: false, style: {}, classList: { add() {}, remove() {} } });
      return elements.get(key);
    },
    setTimeout: (fn) => setImmediate(fn),     // Abfrage des Lesevorgangs ohne Wartezeit
    $$: () => [], window: {},
    esc: (s) => String(s), toast: (text) => toasts.push(text),
    plural: (n, one, many) => `${n} ${n === 1 ? one : many}`,
    askConfirm: async (options) => { asked.push(options); return answers.confirm; },
    reportError: async (title, err) => { errors.push({ title, message: err.message }); },
    noticeBox: (kind, title, text = "") => `${kind}|${title}|${text}`,
    ICON_CHECK: "", ICON_ERROR: "",
    readForm: () => ({ description: "Korrektur" }),
    apiJson: async (...args) => { calls.push(args); return { number: 1, year: 2025 }; },
  });
  vm.runInContext(fs.readFileSync("static/imports.js", "utf8"), context);
  vm.runInContext("renderPreviews = () => {}; keepPreviewInput = () => {};", context);
  return { context, calls, asked, errors, toasts, answers };
}

// Lesen im Hintergrund: Upload antwortet mit einem Job, die Abfrage liefert das Ergebnis, sobald der Test
// finish(ergebnis) aufruft. uploads zählt die Upload-Anfragen.
function backgroundApi() {
  const api = { finish: null, uploads: 0 };
  let result = null;
  api.call = async (url) => {
    if (url.startsWith("/api/reports?")) { api.uploads++; return { job: "j", total: 1 }; }
    return result ? { done: true, read: 1, total: 1, ...result } : { done: false, read: 0, total: 1 };
  };
  api.finish = (data) => { result = data; };
  return api;
}
// Bis der Upload angenommen ist und der Lesevorgang abgefragt wird
const settle = () => new Promise((resolve) => setImmediate(resolve));

test("Abbruch eines laufenden Uploads verwirft verspätete Vorschau", async () => {
  const { context, calls } = setup();
  const api = backgroundApi();
  context.api = api.call;
  const reading = context.readPdfs([{ name: "test.xlsx" }]);
  await settle();
  await context.discardUpload();
  api.finish({ token: "late", reports: [{ filename: "test.xlsx" }], errors: [] });
  await reading;
  assert.equal(context.state.upload.reports.length, 0);
  assert.equal(calls[0][0], "/api/reports/cancel");
  assert.equal(calls[0][2].token, "late");
});

test("Doppeltes Einlesen startet nur eine Anfrage", async () => {
  const { context } = setup();
  const api = backgroundApi();
  context.api = api.call;
  const first = context.readPdfs([{ name: "test.xlsx" }]);
  await context.readPdfs([{ name: "other.xlsx" }]);
  api.finish({ token: "new", reports: [], errors: [] });
  await first;
  assert.equal(api.uploads, 1);
});

test("Aktualisierung sendet die Revision der Vorschau", async () => {
  const { context, calls } = setup();
  context.state.upload = { token: "original", reports: [{ filename: "test.xlsx", replace: true, existing: { revision: 7 } }] };
  await context.acceptReport(0);
  assert.equal(calls[0][2].revision, 7);
  assert.equal(calls[0][2].token, "original");
  assert.equal(context.state.upload.reports[0].saved.number, 1);
});

test("Eine alte Vorschau kann während eines neuen Uploads nicht übernommen werden", async () => {
  const { context, calls } = setup();
  context.state.upload = { token: "old", reports: [{ filename: "old.xlsx" }] };
  const api = backgroundApi();
  context.api = api.call;
  const reading = context.readPdfs([{ name: "new.xlsx" }]);
  await settle();
  await context.acceptReport(0);
  assert.equal(calls.length, 0);
  api.finish({ token: "new", reports: [], errors: [] });
  await reading;
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "/api/reports/cancel");
});

test("Stammdatensatz sendet keine Einsatzformularwerte", async () => {
  const { context, calls } = setup();
  context.state.upload = { token: "master", reports: [{ filename: "master.xlsx", action: "master" }] };
  await context.acceptReport(0);
  assert.equal(Object.keys(calls[0][2].fields).length, 0);
});

test("Verwaltungsfelder behalten bestehende IDs ohne doppelte Attribute", () => {
  const source = fs.readFileSync("static/admin.js", "utf8");
  const start = source.indexOf("const adminField =");
  const end = source.indexOf("const textInput", start);
  const context = vm.createContext({ helpButton: () => "" });
  vm.runInContext("let adminFieldSequence = 0; " + source.slice(start, end) + "; globalThis.field = adminField;", context);
  const html = context.field("Name", '<input id="vg-name" type="text">');
  assert.match(html, /for="vg-name"/);
  assert.equal((html.match(/ id=/g) || []).length, 1);
});

test("Offene Vorschauen werden vor dem Einlesen nur nach Bestätigung verworfen", async () => {
  const { context, asked, answers } = setup();
  context.state.upload = { token: "old", reports: [{ filename: "old.xlsx", warnings: [], people: [] }] };
  answers.confirm = false;
  await context.readPdfs([{ name: "new.xlsx" }]);
  assert.equal(asked.length, 1);
  assert.match(asked[0].title, /verwerfen/);
  assert.equal(asked[0].danger, true);
  assert.equal(context.state.upload.token, "old");           // nichts wurde verworfen
});

test("Fehler beim Übernehmen nennt den Bericht und lässt die Vorschau offen", async () => {
  const { context } = setup();
  context.state.upload = { token: "t", reports: [{ filename: "a.xlsx", number: 5, year: 2025 }] };
  context.apiJson = async () => { throw new Error("Revision veraltet"); };
  await context.acceptReport(0);
  const r = context.state.upload.reports[0];
  assert.ok(!r.saved);
  assert.match(r.failure.title, /5\/2025 \(a\.xlsx\) wurde nicht übernommen/);
  assert.match(r.failure.text, /Revision veraltet/);
});

test("Ein bereits gespeicherter Bericht wird nie ein zweites Mal gesendet", async () => {
  const { context, calls } = setup();
  context.state.upload = { token: "t", reports: [{ filename: "a.xlsx", saved: { number: 1, year: 2025 } }] };
  assert.equal(await context.acceptReport(0), false);
  assert.equal(calls.length, 0);
});

test("Sammelübernahme nimmt nur Berichte ohne Hinweise und hält beim ersten Fehler an", async () => {
  const { context, calls, toasts } = setup();
  const clean = (name) => ({ filename: name, number: 1, year: 2025, warnings: [], people: [] });
  context.state.upload = { token: "t", reports: [clean("a.xlsx"),
    { ...clean("b.xlsx"), warnings: ["Prüfen"] }, clean("c.xlsx"),
    { ...clean("d.xlsx"), existing: { differences: [{}], revision: 1 } }] };
  assert.deepEqual([0, 1, 2, 3].map((i) => vm.runInContext(`isClean(state.upload.reports[${i}])`, context)), [true, false, true, false]);
  await vm.runInContext("acceptCleanReports()", context);
  assert.deepEqual(calls.map((c) => c[2].filename), ["a.xlsx", "c.xlsx"]);
  assert.match(toasts.at(-1), /2 Berichte übernommen/);
});

test("Doppelter Aufruf der Sammelübernahme sendet jeden Bericht nur einmal", async () => {
  const { context, calls } = setup();
  const clean = (name) => ({ filename: name, number: 1, year: 2025, warnings: [], people: [] });
  context.state.upload = { token: "t", reports: [clean("a.xlsx"), clean("b.xlsx")] };
  await Promise.all([vm.runInContext("acceptCleanReports()", context), vm.runInContext("acceptCleanReports()", context)]);
  assert.deepEqual(calls.map((c) => c[2].filename), ["a.xlsx", "b.xlsx"]);
  assert.equal(vm.runInContext("bulkRunning", context), false);          // danach wieder bedienbar
});

test("Sammelübernahme hält beim Fehler an, nennt den Bericht und gibt den Knopf wieder frei", async () => {
  const { context, calls, toasts } = setup();
  const clean = (name) => ({ filename: name, number: 1, year: 2025, warnings: [], people: [] });
  context.state.upload = { token: "t", reports: [clean("a.xlsx"), clean("b.xlsx"), clean("c.xlsx")] };
  context.apiJson = async (...args) => { calls.push(args); if (args[2].filename === "b.xlsx") throw new Error("Revision veraltet"); return { number: 1, year: 2025 }; };
  await vm.runInContext("acceptCleanReports()", context);
  assert.deepEqual(calls.map((c) => c[2].filename), ["a.xlsx", "b.xlsx"]);   // c bleibt unberührt
  assert.match(toasts.at(-1), /1 Bericht übernommen\. Angehalten bei b\.xlsx; 2 Berichte offen/);
  assert.equal(vm.runInContext("bulkRunning", context), false);
  assert.ok(context.state.upload.reports[1].failure);
});

test("Die Dateiliste wird vor der Rückfrage kopiert (der Datei-Dialog leert sie sofort)", async () => {
  const { context } = setup();
  const api = backgroundApi();
  context.api = api.call;
  context.state.upload = { token: "old", reports: [{ filename: "old.xlsx", warnings: [], people: [] }] };
  const files = [{ name: "new.xlsx" }];
  const reading = context.readPdfs(files);
  files.length = 0;                                   // wie e.target.value = "" im Change-Handler
  await settle();
  api.finish({ token: "new", reports: [], errors: [] });
  await reading;
  assert.equal(api.uploads, 1);
});

const plain = (name, extra = {}) => ({ filename: name, number: 1, year: 2025, warnings: [], people: [], ...extra });

test("Neue Personen verhindern die Sammelübernahme nicht, der Dialog nennt sie vorher", async () => {
  const { context, calls, asked } = setup();
  context.state.upload = { token: "t", reports: [
    plain("a.xlsx", { people: [{ name: "M. Muster", new: true }, { name: "E. Beispiel", new: false }] }),
    plain("b.xlsx", { people: [{ name: "M. Muster", new: true }, { name: "K. Probe", new: true }] }),
    plain("c.xlsx", { warnings: ["Prüfen"] })] };
  await vm.runInContext("acceptCleanReports()", context);
  assert.equal(asked.length, 1);
  assert.match(asked[0].text, /werden 2 neue Personen angelegt: M\. Muster; K\. Probe/);   // einmal je Name, ohne Bekannte
  assert.deepEqual(calls.map((c) => c[2].filename), ["a.xlsx", "b.xlsx"]);                // Bericht mit Hinweis bleibt stehen
});

test("Wird der Dialog zur Sammelübernahme abgebrochen, wird nichts gesendet", async () => {
  const { context, calls, answers } = setup();
  answers.confirm = false;
  context.state.upload = { token: "t", reports: [plain("a.xlsx", { people: [{ name: "M. Muster", new: true }] }), plain("b.xlsx")] };
  await vm.runInContext("acceptCleanReports()", context);
  assert.equal(calls.length, 0);
  assert.equal(vm.runInContext("bulkRunning", context), false);
});

test("Nach dem Übernehmen öffnet sich der nächste offene Bericht, ein Fehler öffnet die eigene Karte", async () => {
  const { context } = setup();
  context.state.upload = { token: "t", reports: [plain("a.xlsx", { open: true }), plain("b.xlsx"), plain("c.xlsx")] };
  assert.equal(await context.acceptReport(0), true);
  const [a, b, c] = context.state.upload.reports;
  assert.equal(a.open, false);
  assert.equal(b.open, true);          // nächster offener
  assert.ok(!c.open);
  context.apiJson = async () => { throw new Error("Revision veraltet"); };
  b.open = false;
  assert.equal(await context.acceptReport(1), false);
  assert.equal(b.open, true);          // der Fehler steht in der Karte und muss sichtbar sein
});

test("Ein eingeklappter Bericht wird mit den gespeicherten Werten der Maske gesendet", async () => {
  const { context, calls } = setup();
  context.config = { incident_fields: [["number", "Nr.", "number"], ["place", "Ort", "text"], ["started_at", "Beginn", "datetime-local"], ["rescued", "Gerettet", "number"]] };
  context.state.upload = { token: "t", reports: [plain("a.xlsx", { place: "Beispielstadt", started_at: "2025-12-03T10:08:30.123", number: "7", rescued: null })] };
  await context.acceptReport(0);
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0][2].fields)), { number: 7, place: "Beispielstadt", started_at: "2025-12-03T10:08:30", rescued: null });
});

test("Zuerst ist nur der erste offene Bericht aufgeklappt", () => {
  const { context } = setup();
  context.showUploadResult({ token: "t", errors: [], reports: [plain("a.xlsx"), plain("b.xlsx")] });
  assert.deepEqual(context.state.upload.reports.map((r) => Boolean(r.open)), [true, false]);
});
