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
    $: (key) => { if (!elements.has(key)) elements.set(key, { hidden: false, disabled: false }); return elements.get(key); },
    $$: () => [], window: { confirm: () => true },
    esc: (s) => String(s), alert: () => {}, toast: () => {},
    readForm: () => ({ description: "Korrektur" }),
    apiJson: async (...args) => { calls.push(args); return { number: 1, year: 2025 }; },
  });
  vm.runInContext(fs.readFileSync("static/imports.js", "utf8"), context);
  vm.runInContext("renderPreviews = () => {}; keepPreviewInput = () => {};", context);
  return { context, calls };
}

test("Abbruch eines laufenden Uploads verwirft verspätete Vorschau", async () => {
  const { context, calls } = setup();
  let finish;
  context.api = () => new Promise((resolve) => { finish = resolve; });
  const reading = context.readPdfs([{ name: "test.xlsx" }]);
  await context.discardUpload();
  finish({ token: "late", reports: [{ filename: "test.xlsx" }], errors: [] });
  await reading;
  assert.equal(context.state.upload.reports.length, 0);
  assert.equal(calls[0][0], "/api/reports/cancel");
  assert.equal(calls[0][2].token, "late");
});

test("Doppeltes Einlesen startet nur eine Anfrage", async () => {
  const { context } = setup();
  let finish, reads = 0;
  context.api = () => { reads++; return new Promise((resolve) => { finish = resolve; }); };
  const first = context.readPdfs([{ name: "test.xlsx" }]);
  await context.readPdfs([{ name: "other.xlsx" }]);
  assert.equal(reads, 1);
  finish({ token: "new", reports: [], errors: [] });
  await first;
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
  let finish;
  context.api = () => new Promise((resolve) => { finish = resolve; });
  const reading = context.readPdfs([{ name: "new.xlsx" }]);
  await context.acceptReport(0);
  assert.equal(calls.length, 0);
  finish({ token: "new", reports: [], errors: [] });
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
