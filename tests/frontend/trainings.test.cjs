// Übungsdienste (static/trainings.js): Formular, Enddatum-Vorbelegung, Navigation.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function load() {
  const els = {};
  const el = (key) => (els[key] ||= { innerHTML: "", value: "", textContent: "", addEventListener() {}, focus() {} });
  const context = vm.createContext({
    VIEWS: {}, document: { addEventListener() {} }, state: { year: 2026 }, config: { permissions: ["trainings.view", "trainings.edit"] },
    $: el, esc: (s) => String(s ?? ""), pad2: (n) => String(n).padStart(2, "0"), plural: (n, one, many) => `${n} ${n === 1 ? one : many}`,
    formatDuration: (m) => `${m} min`, formatDate: (i) => i, formatTime: (i) => i, formatDateTime: (i) => i, formatHours: (m) => `${m / 60} h`,
    num: (n) => String(n), percent: (q) => `${Math.round(q * 100)} %`, can: () => true, toast() {}, api: async () => ({}), apiJson: async () => ({}),
  });
  vm.runInContext(fs.readFileSync("static/trainings.js", "utf8"), context);
  return { context, els };
}

test("Ansichten sind registriert, in der Navigation und im HTML", () => {
  const { context } = load();
  for (const key of ["trainings", "training_members"]) {
    assert.equal(typeof context.VIEWS[key].render, "function");
    assert.equal(context.VIEWS[key].permission, "trainings.view");
    assert.match(fs.readFileSync("static/index.html", "utf8"), new RegExp(`id="view-${key}"`));
  }
  const app = fs.readFileSync("static/app.js", "utf8");
  assert.match(app, /views: \["incidents", "trainings", "fees", "records"\]/);
  assert.match(app, /views: \["members", "training_members"\]/);
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
