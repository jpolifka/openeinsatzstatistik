// Atemschutz-Dokumentation (static/atemschutz.js): Ansichten, Nutzlast ohne Personen-ID, Darstellung ohne Einzelheiten Dritter.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function load(extra = {}) {
  const els = {};
  const el = (key) => (els[key] ||= { innerHTML: "", value: "", addEventListener() {}, focus() {}, hidden: false });
  const context = vm.createContext({
    VIEWS: {}, document: { addEventListener() {} }, state: { year: 2026, view: "atemschutz" }, config: { scope: "t:a", permissions: ["agt.own"] },
    $: el, $$: () => [], esc: (s) => String(s ?? ""), plural: (n, one, many) => `${n} ${n === 1 ? one : many}`,
    formatDuration: (m) => `${m} min`, formatDate: (i) => i, formatDateTime: (i) => i, formatTime: (i) => i.slice(11, 16), keyFigures: (e) => e.map(([v, l]) => `${v} ${l}`).join(","),
    noticeBox: (kind, title) => `[${kind}] ${title}`, toast() {}, api: async () => ({}), apiJson: async () => ({}), ...extra,
  });
  vm.runInContext(fs.readFileSync("static/atemschutz.js", "utf8"), context);
  return { context, els };
}

test("Zwei Ansichten mit eigenen Rechten, ein Reiter, Bereiche in der Seite", () => {
  const { context } = load();
  assert.equal(context.VIEWS.atemschutz.permission, "agt.own");
  assert.equal(context.VIEWS.agt_eval.permission, "agt.evaluate");
  assert.ok(context.VIEWS.atemschutz.single && context.VIEWS.agt_eval.single);
  const html = fs.readFileSync("static/index.html", "utf8");
  assert.match(html, /id="view-atemschutz"/);
  assert.match(html, /id="view-agt_eval"/);
  assert.match(html, /atemschutz\.js/);
  assert.match(fs.readFileSync("static/app.js", "utf8"), /views: \["atemschutz", "agt_eval", "agt_cosign"\]/);
});

test("Die Nutzlast enthält nie eine Personen-ID oder E-Mail", () => {
  const { context } = load();
  const payload = (code) => JSON.stringify(vm.runInContext(code, context));
  const manual = payload(`agtPayload({ id: null, revision: null, kind: "strecke", date: "2026-03-01", time: "19:00", duration: "20",
    place: "Strecke", keyword: "", startBar: "300", endBar: "120", external: false, organisation: "", notes: "", source: null })`);
  assert.doesNotMatch(manual, /member|email/);
  assert.match(manual, /"started_at":"2026-03-01T19:00"/);
  assert.match(manual, /"start_bar":300/);
  const taken = JSON.parse(payload(`agtPayload({ id: null, source: { kind: "incident", id: 7 }, kind: "einsatz", date: "2026-03-01",
    time: "10:00", duration: "45", place: "x", keyword: "y", startBar: "", endBar: "", notes: "n" })`));
  assert.deepEqual(Object.keys(taken).sort(), ["duration_min", "end_bar", "notes", "source", "start_bar"]);   // Stichwort, Beginn, Ort holt der Server
  const external = JSON.parse(payload(`agtPayload({ id: 3, revision: 1, kind: "einsatz", date: "2026-03-01", time: "10:00", duration: "45",
    place: "", keyword: "", startBar: "", endBar: "", external: true, organisation: "Werkfeuerwehr", notes: "", source: null })`));
  assert.equal(external.organisation, "Werkfeuerwehr");
  assert.equal(external.revision, 1);
});

test("Ohne E-Mail im Personalstamm: Hinweis statt Daten", () => {
  const { context, els } = load();
  vm.runInContext(`agt.data = { linked: false }; renderAgt();`, context);
  assert.match(els["#view-atemschutz"].innerHTML, /nicht hinterlegt/);
});

test("Auswertung zeigt nur Summen und den Ablauf der G26.3", () => {
  const { context, els } = load();
  vm.runInContext(`agt.summary = { year: 2026, years: [2026], kinds: { einsatz: "Einsatz", uebung: "Übung", strecke: "Streckendurchgang" },
    people: [{ id: 1, name: "Beispiel, Anna", linked: true, minutes: 80, valid_until: "2099-01-01",
      kinds: { einsatz: { count: 1, minutes: 60 }, uebung: { count: 0, minutes: 0 }, strecke: { count: 1, minutes: 20 } } },
      { id: 2, name: "Muster, Berta", linked: false, minutes: 0, valid_until: null,
      kinds: { einsatz: { count: 0, minutes: 0 }, uebung: { count: 0, minutes: 0 }, strecke: { count: 0, minutes: 0 } } }] };
    renderAgtEval();`, context);
  const html = els["#view-agt_eval"].innerHTML;
  assert.match(html, /Beispiel, Anna/);
  assert.match(html, /60 min/);
  assert.match(html, /ohne E-Mail/);
  assert.match(html, /nicht erfasst/);
  assert.doesNotMatch(html, /\d bar|<th[^>]*>Ort/);
});

test("Abzeichnen: offene Einträge mit Knopf, Namen der Abzeichnung, keine Notizen", () => {
  const { context, els } = load();
  vm.runInContext(`agt.cosign = { year: 2026, years: [2026], kinds: { strecke: "Streckendurchgang" }, entries: [
    { id: 1, person: "Beispiel, Anna", kind: "strecke", started_at: "2026-03-12T19:00:00", duration_min: 20, place: "Strecke",
      keyword: null, start_bar: 300, end_bar: 120, external: false, organisation: null, revision: 2, cosign: null },
    { id: 2, person: "Muster, Berta", kind: "strecke", started_at: "2026-03-13T19:00:00", duration_min: 25, place: null,
      keyword: null, start_bar: null, end_bar: null, external: false, organisation: null, revision: 1,
      cosign: { name: "Wehrführer, Willi", at: "2026-03-14 10:00:00", valid: true } }] };
    renderAgtCosign();`, context);
  const html = els["#view-agt_cosign"].innerHTML;
  assert.match(html, /Beispiel, Anna/);
  assert.match(html, /data-agt-cosign="sign" data-id="1" data-revision="2"/);
  assert.doesNotMatch(html, /Wehrführer, Willi/);                   // bereits abgezeichnete erst nach Umschalten
  vm.runInContext("agt.cosignOpen = true; renderAgtCosign();", context);
  assert.match(els["#view-agt_cosign"].innerHTML, /Wehrführer, Willi/);
  assert.match(els["#view-agt_cosign"].innerHTML, /data-agt-cosign="withdraw" data-id="2"/);
});
