// Ladefehler dürfen die bestehende Ansicht nicht zerstören; Wiederholen bleibt bedienbar.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

test("Fehler erhält Seitenstruktur; Wiederholen lädt und zeichnet erneut", async () => {
  let attempts = 0, renders = 0, retry;
  const classes = new Set();
  const section = { hidden: false, children: ["Tabelle"],
    classList: { add: (v) => classes.add(v), remove: (v) => classes.delete(v) },
    prepend: (error) => section.children.unshift(error),
  };
  const elements = { "#view-incidents": section, "#page-title": {} };
  const context = vm.createContext({
    state: { year: 2025 }, location: { hash: "#incidents" },
    VIEWS: { incidents: { label: "Einsätze", load: async () => { if (++attempts === 1) throw Error("Ausfall"); }, render: () => renders++ } },
    allowedViews: () => ["incidents"], $$: () => [], navGroup: () => undefined, renderSubTabs: () => {},
    parseHash: () => ({ view: "incidents", params: new URLSearchParams() }), URLSearchParams,
    $: (key) => key === "button" ? { addEventListener: (_, fn) => { retry = fn; } }
      : key === ".view-load-error" ? section.children.find((v) => typeof v === "object") : elements[key],
    esc: (s) => String(s), noticeBox: (kind, title, text = "") => `${kind}|${title}|${text}`, Event: class {}, appTitle: "Einsatzstatistik",
    document: { dispatchEvent() {}, createElement: () => ({ remove() { section.children.shift(); } }) },
  });
  const source = fs.readFileSync("static/app.js", "utf8");
  vm.runInContext("let viewRun = 0; " + source.slice(source.indexOf("async function showView()"), source.indexOf("async function reloadData()")), context);
  await context.showView();
  assert.equal(section.children[1], "Tabelle");
  assert.equal(classes.has("loading"), false);
  assert.match(section.children[0].innerHTML, /Erneut versuchen/);
  assert.match(section.children[0].innerHTML, /konnte nicht geladen werden.*Ausfall/);      // Titel nennt, was nicht geschah; Ursache dahinter
  await retry();
  assert.equal(attempts, 2);
  assert.equal(renders, 1);
  assert.deepEqual(section.children, ["Tabelle"]);
});
