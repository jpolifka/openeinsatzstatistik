// Importzustand unabhängig vom Browser: Rennen, Abbruch und Revisionsvertrag.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function setup() {
  const elements = new Map();
  const calls = [];
  const context = vm.createContext({
    state: { upload: { token: null, reports: [] } },
    config: {}, console,
    FormData: class { append() {} },
    $: (key) => {
      if (!elements.has(key)) elements.set(key, { hidden: false, disabled: false, style: {}, classList: { add() {}, remove() {} } });
      return elements.get(key);
    },
    setTimeout: (fn) => setImmediate(fn),     // Abfrage des Lesevorgangs ohne Wartezeit
    $$: () => [], window: { confirm: () => true },
    esc: (s) => String(s), alert: () => {}, toast: () => {},
    readForm: () => ({ description: "Korrektur" }),
    apiJson: async (...args) => { calls.push(args); return { number: 1, year: 2025 }; },
  });
  vm.runInContext(fs.readFileSync("static/imports.js", "utf8"), context);
  vm.runInContext("renderPreviews = () => {}; keepPreviewInput = () => {};", context);
  return { context, calls };
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
