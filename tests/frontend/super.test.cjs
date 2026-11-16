// Gruppierung und Suche der Superadmin-Verwaltung (Wehren & VGs).
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const ctx = vm.createContext({ console, esc: String, admin: {} });
vm.runInContext(fs.readFileSync("static/admin_views.js", "utf8"), ctx);

const overview = {
  vgs: [{ slug: "vg-a", name: "VG Alpha" }, { slug: "vg-b", name: "VG Beta" }],
  tenants: [{ slug: "a1", name: "Altenau", vg: "vg-a" }, { slug: "b1", name: "Bergen", vg: "vg-b" }],
};

test("ohne Suche alle VGs mit ihren Wehren", () => {
  const g = vm.runInContext("superGroups", ctx)(overview);
  assert.deepEqual(g.map((x) => x.tenants.length), [1, 1]);
});

test("Suche trifft über Wehren die VG", () => {
  const g = vm.runInContext("superGroups", ctx)(overview, "berg");
  assert.equal(g.length, 1);
  assert.equal(g[0].vg.slug, "vg-b");
  assert.deepEqual(g[0].matches, ["b1"]);
});
