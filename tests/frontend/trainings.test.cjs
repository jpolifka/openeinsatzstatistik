// Übungsdienste (static/trainings.js): Formular, Enddatum-Vorbelegung, Navigation.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function load() {
  const els = {};
  const el = (key) => (els[key] ||= { innerHTML: "", value: "", textContent: "", addEventListener() {}, focus() {}, open: false });
  const context = vm.createContext({
    VIEWS: {}, document: { addEventListener() {} }, state: { year: 2026 }, config: { permissions: ["trainings.view", "trainings.edit"] },
    $: el, esc: (s) => String(s ?? ""), pad2: (n) => String(n).padStart(2, "0"), plural: (n, one, many) => `${n} ${n === 1 ? one : many}`,
    formatDuration: (m) => `${m} min`, formatDate: (i) => i, formatTime: (i) => i, formatDateTime: (i) => i, formatHours: (m) => `${m / 60} h`,
    num: (n) => String(n), ICON_CHEVRON: "<svg></svg>", analysisKpi: (t, v) => `${t}:${v}`, percent: (q) => `${Math.round(q * 100)} %`, can: () => true, signatureHtml: (t) => `<span class="sig">${t.signature ? "sig" : "keine"}${t.can_sign ? "+knopf" : ""}</span>`, toast() {}, api: async () => ({}), apiJson: async () => ({}),
  });
  vm.runInContext(fs.readFileSync("static/trainings.js", "utf8"), context);
  return { context, els };
}

test("Eine Ansicht unter Personal, ein einziger Knopf oben, kein zweiter Reiter bei Einsätzen", () => {
  const { context } = load();
  assert.equal(typeof context.VIEWS.training_members.render, "function");
  assert.equal(context.VIEWS.training_members.permission, "trainings.view");
  assert.equal(typeof context.VIEWS.trainings.render, "function");
  const html = fs.readFileSync("static/index.html", "utf8");
  assert.match(html, /id="view-training_members"/);
  assert.match(html, /id="view-trainings"/);
  assert.match(html, /id="btn-training"/);
  assert.match(html, /id="training-dialog"/);
  const app = fs.readFileSync("static/app.js", "utf8");
  assert.match(app, /views: \["incidents", "trainings", "fees", "records"\]/);
  assert.match(app, /views: \["members", "training_members"\]/);
});

test("Übersicht: Balken für die Häufigkeit, Zeilen klappen auf", () => {
  const { context, els } = load();
  vm.runInContext(`trainingState.data = { members: [], trainings: [{ id: 5, topic: "Knoten", started_at: "2026-03-01T19:00", ended_at: "2026-03-01T21:00",
      duration_min: 120, trainer: "Muster, Max", notes: "", participants: [{ id: 1, name: "Muster, Max" }] }],
    summary: { count: 1, minutes: 120, members: [{ id: 1, name: "Muster, Max", trainings: 1, minutes: 120, hours: 2, rate: 1, last: "2026-03-01T19:00" }] } };
    trainingState.openPeople.add(1);`, context);
  vm.runInContext("renderTrainingMembers()", context);
  const html = els["#view-training_members"].innerHTML;
  assert.match(html, /class="track"/);                                   // Balken
  assert.match(html, /data-tr-person="1"[^>]*aria-expanded="true"/);     // aufgeklappt
  assert.match(html, /Knoten/);                                           // Detailzeile der Person
  assert.match(html, /data-tr-open="5"/);                                 // Übung in der Detailzeile ist ein Link
});

test("Liste der Übungen: wichtigste Daten, aufklappbar, Bearbeiten in der Detailzeile", () => {
  const { context, els } = load();
  vm.runInContext(`state.view = "trainings"; trainingState.data = { members: [], trainings: [{ id: 5, topic: "Knoten", category: "Technik", place: "Gerätehaus",
      started_at: "2026-03-01T19:00", ended_at: "2026-03-01T21:00", duration_min: 120, trainer: "Muster, Max", notes: "Notiz", participants: [{ id: 1, name: "Muster, Max" }] }],
    summary: { count: 1, minutes: 120, members: [] } }; trainingState.openTrainings.add(5);`, context);
  vm.runInContext("renderTrainings()", context);
  const html = els["#view-trainings"].innerHTML;
  assert.match(html, /data-tr-training="5"[^>]*aria-expanded="true"/);
  assert.match(html, /Gerätehaus/);
  assert.match(html, /class="track"/);
  assert.match(html, /data-tr-action="edit"/);
  assert.match(html, /Notiz/);
});

test("Enddatum ist mit dem Startdatum vorbelegt; Dauer nur bei Ende nach Beginn", () => {
  const { context } = load();
  const d = vm.runInContext("emptyTrainingDraft()", context);
  assert.equal(d.endDate, d.startDate);
  assert.equal(vm.runInContext("draftMinutes(emptyTrainingDraft())", context), 120);
  context.d = { startDate: "2026-03-01", startTime: "20:00", endDate: "2026-03-01", endTime: "19:00" };
  assert.equal(vm.runInContext("draftMinutes(d)", context), null);
  context.d = { startDate: "2026-03-01", startTime: "20:00", endDate: "2026-03-02", endTime: "09:00" };
  assert.equal(vm.runInContext("draftMinutes(d)", context), 780);
});

test("Teilnehmerwahl: ausgeschiedene Personen fehlen, neue Personen werden gesendet", () => {
  const { context } = load();
  vm.runInContext(`trainingState.data = { members: [{ id: 1, name: "Muster, Max", active: true }, { id: 2, name: "Alt, Anna", active: false }] };
    trainingState.draft = emptyTrainingDraft(); trainingState.draft.memberIds.add(1);
    trainingState.draft.newMembers.push({ last_name: "Beispiel", first_name: "Erika" });`, context);
  const html = vm.runInContext("trainingPeopleHtml()", context);
  assert.match(html, /Muster, Max/);
  assert.doesNotMatch(html, /Alt, Anna/);
  assert.match(html, /Beispiel, Erika/);
  const payload = vm.runInContext("trainingPayload(trainingState.draft)", context);
  assert.deepEqual(Array.from(payload.member_ids), [1]);
  assert.equal(payload.new_members[0].last_name, "Beispiel");
});

test("Übungsleiter wird aus dem Personenstamm vorgeschlagen", () => {
  const { context } = load();
  vm.runInContext(`trainingState.data = { members: [{ id: 1, name: "Muster, Max", active: true }, { id: 2, name: "Alt, Anna", active: false }] };
    trainingState.draft = emptyTrainingDraft();`, context);
  const html = vm.runInContext("trainingFormHtml()", context);
  assert.match(html, /list="tr-trainer-list"/);
  assert.match(html, /<option value="Muster, Max">/);
  assert.doesNotMatch(html, /<option value="Alt, Anna">/);
});

test("CSA: Übersicht der Belastungsübung und Signatur in der Übungsliste", () => {
  const { context, els } = load();
  vm.runInContext(`trainingState.data = { members: [], can_sign: true, csa: [{ id: 1, name: "Muster, Max", done: false, last: null },
      { id: 2, name: "Beispiel, Erika", done: true, last: "2026-05-01T09:00" }],
    trainings: [{ id: 5, topic: "Belastung", csa_load: true, signature: { at: "2026-05-02 10:00:00", valid: true }, started_at: "2026-05-01T09:00",
      ended_at: "2026-05-01T11:00", duration_min: 120, participants: [] }],
    summary: { count: 1, minutes: 120, members: [] } };
    trainingState.openTrainings.add(5);`, context);
  vm.runInContext("renderTrainingMembers()", context);
  const members = els["#view-training_members"].innerHTML;
  assert.match(members, /1 CSA-Träger\/in von 2 ohne Belastungsübung/);
  assert.match(members, /Muster, Max · offen/);
  vm.runInContext("renderTrainings()", context);
  const list = els["#view-trainings"].innerHTML;
  assert.match(list, /CSA-Belastungsübung/);
  assert.match(list, /sig\+knopf/);                                      // Stand der Signatur und Knopf kommen aus signatureHtml
});

test("Formular: CSA-Belastungsübung wird mitgesendet", () => {
  const { context } = load();
  const payload = JSON.parse(vm.runInContext(`trainingState.data = { members: [] }; const d = emptyTrainingDraft(); d.csaLoad = true; d.topic = "x"; JSON.stringify(trainingPayload(d))`, context));
  assert.equal(payload.csa_load, true);
});
