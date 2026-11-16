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

test("Benutzerliste lässt sich nach VG (mit Wehren) und Wehr filtern", () => {
  const match = vm.runInContext("userFilterMatches", ctx);
  const rows = [{ scope: "vg", slug: "vg-a", vg: "vg-a" }, { scope: "tenant", slug: "a1", vg: "vg-a" }, { scope: "tenant", slug: "b1", vg: "vg-b" }];
  assert.deepEqual(rows.filter((m) => match(m, "vg:vg-a")).map((m) => m.slug), ["vg-a", "a1"]);
  assert.deepEqual(rows.filter((m) => match(m, "tenant:b1")).map((m) => m.slug), ["b1"]);
  assert.equal(rows.filter((m) => match(m, "")).length, 3);
});
