// Einsatzformular: In der Import-Vorschau sind seltene Angaben eingeklappt, im Bearbeiten-Formular nicht.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync("static/incident_detail.js", "utf8");
const code = source.slice(source.indexOf("let formSequence"), source.indexOf("function readForm"));
const FIELDS = [["number", "Nr.", "number", "", ""], ["place", "Ort", "text", "span-3", ""],
  ["abort_reason", "Einsatzabbruch", "text", "span-4", ""], ["rescued", "Menschen gerettet", "number", "", ""]];

function render(incident, options) {
  const context = vm.createContext({ config: { incident_fields: FIELDS }, esc: (s) => String(s), helpButton: () => "" });
  vm.runInContext(code + "\nthis.formFields = formFields;", context);
  return context.formFields(incident, options);
}

test("Vorschau: leere seltene Angaben stehen eingeklappt unter „Weitere Angaben“", () => {
  const html = render({ number: 3, place: "Beispielstadt" }, { fold: true });
  assert.match(html, /<details class="more-fields">/);
  assert.match(html, /keine im Bericht/);
  assert.ok(html.indexOf('name="place"') < html.indexOf("<details"));      // Kernfelder zuerst
  assert.ok(html.indexOf("<details") < html.indexOf('name="abort_reason"')); // seltene darin
});

test("Vorschau: ausgefüllte seltene Angaben öffnen die Gruppe und werden gezählt", () => {
  const html = render({ number: 3, abort_reason: "Fehlalarm", rescued: 0 }, { fold: true });
  assert.match(html, /<details class="more-fields" open>/);
  assert.match(html, /2 von 2 ausgefüllt/);
});

test("Bearbeiten: ohne fold bleibt ein einziges Formular ohne Einklappen", () => {
  const html = render({ number: 3 });
  assert.doesNotMatch(html, /<details/);
  assert.ok(html.includes('name="abort_reason"'));
});
