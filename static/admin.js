"use strict";

// Verwaltung: Einstellungen (Name, Farben, Logos, Fahrzeuge, BKS-Kennung, Orte, Zeitgrenzen), Stichwortkatalog,
// Benutzer, Rollen und – für Superadmins – Verbandsgemeinden und Wehren. Ist oben in der Verwaltung die
// Verbandsgemeinde gewählt, zeigen dieselben Bereiche die Vorgaben der VG und alle ihre Wehren auf einmal;
// bei einer Wehr deren Werte und wo sie von der VG abweicht. Ein Bereich wechselt nie die Auswahl.
// Wird nach app.js geladen und trägt sich in VIEWS ein. Rechte prüft das Backend (app/admin.py).

// Bereiche mit dem nötigen Recht (rbac.py) bei gewählter Wehr (tenant) bzw. Verbandsgemeinde (vg);
// any: Benutzer und Rollen (entscheidet admin.overview.users), superOnly: nur Superadmin
const ADMIN_SECTIONS = [
  { key: "unit", label: "Allgemein", tenant: "tenant.settings", vg: "tenant.settings" },
  { key: "fleet", label: "Fahrzeuge", tenant: "tenant.settings", vg: "tenant.settings" },
  { key: "bks", label: "BKS-Kennung", tenant: "tenant.settings", vg: "tenant.settings" },
  { key: "places", label: "Orte & Zeitgrenzen", tenant: "tenant.settings", vg: "tenant.settings" },
  { key: "keywords", label: "Stichworte", tenant: "tenant.keywords", vg: "tenant.keywords" },
  { key: "people", label: "Personen", tenant: "tenant.settings" },
  { key: "fees", label: "Gebührenordnung", vg: "vg.fees" },
  { key: "users", label: "Benutzer", any: true }, { key: "roles", label: "Rollen", any: true },
  { key: "super", label: "Wehren & VGs", superOnly: true },
  { key: "sessions", label: "Sitzungen", superOnly: true },
];
// Bereiche, deren Eingaben über „Speichern“ gesichert werden (Einstellungen der Wehr bzw. Vorgaben der VG)
const SETTINGS_SECTIONS = ["unit", "fleet", "bks", "places"];

const admin = {
  overview: null, slug: null, section: null, settings: null, keywords: null, memberships: null, superOverview: null,
  check: null, importFile: null, importPreview: null, keywordQuery: "", keywordEdit: null, parseResult: null, error: "",
  fees: null, feeDraft: null,
  people: null,               // Personenstamm der gewählten Wehr (Einstellungen → Personen)
  personEdit: null,           // Person in Bearbeitung: { id, last_name, first_name }
  personQuery: "", personFlagged: false, personInactive: false,
  userScopes: null,           // Bereiche, in denen der Benutzer Rollen vergeben darf, mit den Rollen
  effective: null,            // Rechte einer Person mit Herkunft (Benutzer → „Rechte“)
  events: null,               // Protokoll der Vergaben und Rollenänderungen
  roles: null,                // Rechtekatalog und Rollen (/api/admin/roles)
  roleDraft: null,            // Rolle im Editor (neu: id null)
  vg: null,                   // ausgewählte Verbandsgemeinde (Slug der VG) statt einer Wehr
  vgSettings: null,           // Vorgaben der VG mit allen Wehren (Allgemein, BKS-Kennung, Orte & Zeitgrenzen)
  vgFleet: null,              // Fahrzeuglisten aller Wehren der VG
  saved: null,                // Stand des gerade bearbeiteten Datensatzes beim Laden/Speichern – Vergleich für „ungespeichert“
  fleetQuery: "",             // Suche in den Fahrzeugtabellen
  superVg: recall("super-vg"), superQuery: "",   // Superadmin: gewählte VG und Suche
  userFilter: "",             // Benutzer: nur eine VG ("vg:<slug>", mit ihren Wehren) bzw. Wehr ("tenant:<slug>")
  keywordDeviationsOnly: false,   // Stichworte: nur Abweichungen (Wehr) bzw. Stichworte mit Abweichungen (VG)
};
// Fahrzeugtabelle kompakt (ohne Dienstzeitraum, Nachfolger, Gesamtstärke); gemerkt je Ansicht, VG standardmäßig kompakt
const fleetCompactKey = () => admin.vg ? "fleet-compact-vg" : "fleet-compact";
const fleetCompact = () => (recall(fleetCompactKey()) ?? (admin.vg ? "1" : "0")) === "1";

// Hilfe zum gerade offenen Bereich der Verwaltung
const ADMIN_HELP = { unit: () => admin.vg ? "admin_vg_defaults" : "admin_colors", fleet: () => admin.vg ? "admin_vg_vehicles" : "admin_fleet",
  bks: "admin_bks", places: "admin_places", keywords: "admin_keywords", people: "admin_people", fees: "fees", users: "admin_users",
  roles: () => admin.roleDraft ? "admin_role_editor" : "admin_roles", sessions: "admin_sessions" };

VIEWS.admin = { label: "Einstellungen", sub: "Einstellungen", load: loadAdmin, render: renderAdmin, noYear: true,
  visible: () => config.admin, help: () => helpValue(ADMIN_HELP[admin.section]) || "sec_admin" };

// ------------------------------------------------------------ Laden
const vgUrl = (path = "") => `/api/admin/vgs/${encodeURIComponent(admin.vg)}${path}`;
const keywordsUrl = (path = "") => admin.vg ? vgUrl(`/keywords${path}`) : `/api/admin/${admin.slug}/keywords${path}`;
const keywordsScope = () => admin.vg ? `vg:${admin.vg}` : admin.slug;

// Was „Speichern“ im offenen Bereich sichert: Einstellungen der Wehr, Vorgaben der VG oder ihre Fahrzeuge
function adminData() {
  if (!SETTINGS_SECTIONS.includes(admin.section)) return null;
  if (!admin.vg) return admin.settings;
  return admin.section === "fleet" ? admin.vgFleet : admin.vgSettings;
}

async function loadAdmin() {
  if (!admin.overview) {
    admin.overview = await api("/api/admin");
    // Gewählte Wehr behalten (z. B. nach dem Speichern), sonst die oben ausgewählte, sonst die erste
    const pick = (slug) => admin.overview.tenants.find((t) => t.slug === slug);
    admin.slug = (pick(admin.slug) || pick(config.tenant?.slug) || admin.overview.tenants[0])?.slug || null;
    // Oben die Verbandsgemeinde gewählt (oder keine Wehr zu verwalten): in der Verwaltung ebenfalls
    const vgs = admin.overview.vgs;
    if (config.vg && vgs.some((v) => v.slug === config.vg.slug)) admin.vg = config.vg.slug;
    else if (!admin.slug && vgs.length) admin.vg = vgs[0].slug;
  }
  const sections = adminSections();
  if (!admin.section) admin.section = recall("admin-section");          // zuletzt offener Bereich
  if (!sections.some((x) => x.key === admin.section)) admin.section = sections[0]?.key || null;
  const s = admin.section;
  const snapshot = () => { admin.saved = JSON.stringify(settingsPayload()); admin.check = null; };
  if (SETTINGS_SECTIONS.includes(s)) {
    if (admin.vg && s === "fleet" && admin.vgFleet?.vg !== admin.vg) {
      admin.vgFleet = { vg: admin.vg, ...(await api(vgUrl("/fleet"))) };
      snapshot();
    } else if (admin.vg && s !== "fleet" && admin.vgSettings?.vg?.slug !== admin.vg) {
      admin.vgSettings = await api(vgUrl("/settings"));
      snapshot();
    } else if (!admin.vg && admin.settings?.slug !== admin.slug) {
      admin.settings = await api(`/api/admin/${admin.slug}/settings`);
      snapshot();
    } else if (adminData() && admin.saved === null) snapshot();
  }
  if (s === "keywords" && admin.keywords?.scope !== keywordsScope()) {
    admin.keywords = { ...(await api(keywordsUrl())), scope: keywordsScope() };
  }
  if (s === "people" && admin.people?.slug !== admin.slug) {
    admin.people = { slug: admin.slug, ...(await api(`/api/admin/${admin.slug}/members`)) };
    admin.personEdit = null;
  }
  if (s === "users" && !admin.memberships) setMemberships(await api("/api/admin/memberships"));
  if (s === "roles" && !admin.roles) admin.roles = await api("/api/admin/roles");
  if (s === "sessions") admin.sessions = await api("/api/super/sessions");     // immer frisch: ändert sich laufend
  if (s === "super" && !admin.superOverview) admin.superOverview = await api("/api/super/overview");
  if (s === "super" && !admin.memberships) setMemberships(await api("/api/admin/memberships"));
  if (s === "fees" && admin.fees?.vg !== admin.vg) {
    admin.fees = { vg: admin.vg, ...(await api(vgUrl("/fees"))) };
    admin.feeDraft = null;
  }
}

// Rechte in der ausgewählten Wehr bzw. VG der Verwaltung
function adminGranted() {
  const { overview } = admin;
  return (admin.vg ? overview.vgs.find((v) => v.slug === admin.vg)
    : overview.tenants.find((t) => t.slug === admin.slug))?.permissions || [];
}

// VG der gewählten Wehr, falls der Benutzer sie verwalten darf (Hinweis „zur Verbandsgemeinde wechseln“)
function adminTenantVg() {
  const { overview } = admin;
  const tenant = overview.tenants.find((t) => t.slug === admin.slug);
  return overview.vgs.find((v) => v.slug === tenant?.vg_slug) || null;
}

function adminSections() {
  const { overview } = admin;
  const granted = adminGranted();
  return ADMIN_SECTIONS.filter((x) => {
    if (x.superOnly) return overview.superadmin;
    if (x.any) return overview.users || overview.superadmin;
    const permission = admin.vg ? x.vg : x.tenant;
    return Boolean(permission) && granted.includes(permission);
  });
}

async function adminGo(changes) {
  Object.assign(admin, changes, { error: "" });
  await showView();
}

// ------------------------------------------------------------ Rahmen
// Auswahl nach Verbandsgemeinde gruppiert: je VG „Gesamte Verbandsgemeinde“ (falls berechtigt) und ihre Wehren
function adminChoiceGroups(vgs, tenants) {
  const groups = new Map();
  const group = (slug, name) => { if (!groups.has(slug)) groups.set(slug, { label: name, options: [] }); return groups.get(slug); };
  vgs.forEach((v) => group(v.slug, v.name).options.push({ key: `vg:${v.slug}`, label: "Gesamte Verbandsgemeinde" }));
  tenants.forEach((t) => group(t.vg_slug, t.vg).options.push({ key: t.slug, label: t.name }));
  return [...groups.values()].sort((a, b) => a.label.localeCompare(b.label, "de"));
}

function renderAdmin() {
  const { tenants, vgs } = admin.overview;
  // Auswahl: Verbandsgemeinde (Vorgaben und alle Wehren) oder eine Wehr – nur hier wechselt sie
  const current = admin.vg ? `vg:${admin.vg}` : admin.slug;
  const groups = adminChoiceGroups(vgs, tenants);
  const count = groups.reduce((n, g) => n + g.options.length, 0);
  const option = (c) => `<option value="${esc(c.key)}" ${c.key === current ? "selected" : ""}>${esc(c.label)}</option>`;
  const tenantSelect = count > 1 && !["users", "roles", "super", "sessions"].includes(admin.section)
    ? `<label class="field admin-tenant"><span>${admin.vg ? "Verbandsgemeinde" : "Feuerwehr"}</span><select data-admin-tenant>${groups.map((g) =>
      `<optgroup label="${esc(g.label)}">${g.options.map(option).join("")}</optgroup>`).join("")}</select></label>` : "";
  const sections = `<div class="segments" role="group" aria-label="Verwaltungsbereich">${adminSections().map(({ key, label }) =>
    `<button type="button" data-admin-section="${key}" aria-pressed="${key === admin.section}" class="${key === admin.section ? "active" : ""}">${label}</button>`).join("")}</div>`;
  const body = ({
    unit: () => admin.vg ? vgUnitSection() : unitSection(), fleet: () => admin.vg ? vgFleetSection() : fleetSection(),
    bks: () => admin.vg ? vgBksSection() : bksSection(), places: () => admin.vg ? vgPlacesSection() : placesSection(),
    keywords: keywordsSection, people: peopleSection, users: usersSection, roles: rolesSection, super: superSection, sessions: sessionsSection, fees: feesSection,
  }[admin.section] || (() => `<p class="muted">Hier gibt es für dich nichts zu verwalten.</p>`))();
  $("#view-admin").innerHTML = `<div class="card admin-card">
    <div class="admin-head">${sections}${tenantSelect}</div>
    ${admin.error ? errorBox(admin.error) : ""}
    <div class="admin-body">${body}</div>
  </div>`;
  if (admin.section === "unit") updateThemePreview();
  if (admin.section === "fleet") filterFleetRows();
  updateDirty();
}

let adminFieldSequence = 0;
const adminField = (label, input, span = "", help = "") => {
  const existing = input.match(/<(?:input|select|textarea)\b[^>]*\bid="([^"]+)"/);
  const id = existing?.[1] || `admin-field-${++adminFieldSequence}`;
  const control = existing ? input : input.replace(/<(input|select|textarea)\b/, `<$1 id="${id}"`);
  return `<div class="field ${span}"><span><label for="${id}">${label}</label></span>${control}</div>`;
};
const textInput = (path, value, attributes = "") =>
  `<input type="text" data-bind="${path}" value="${esc(value ?? "")}" ${attributes}>`;
// Speichern-Leiste der Einstellungen; bei ungespeicherten Änderungen klebt sie unten am Fenster
const saveButton = (label = "Speichern") =>
  `<div class="admin-actions" id="admin-savebar"><span class="unsaved-note">Ungespeicherte Änderungen</span>
    <button type="button" class="btn btn-primary" data-admin-action="save-settings">${label}</button></div>`;

// Ungespeicherte Änderungen an den Einstellungen der Wehr bzw. den Vorgaben oder Fahrzeugen der VG
const settingsDirty = () => Boolean(adminData() && admin.saved !== null && admin.saved !== JSON.stringify(settingsPayload()));

function updateDirty() {
  $("#admin-savebar")?.classList.toggle("dirty", settingsDirty());
}

// Vor dem Wechsel der Wehr: ungespeicherte Änderungen nur nach Rückfrage verwerfen
async function confirmDiscard() {
  if (!settingsDirty()) return true;
  if (!await askConfirm({ title: "Änderungen verwerfen?", text: "Die Änderungen an den Einstellungen sind noch nicht gespeichert.",
    confirm: "Änderungen verwerfen", cancel: "Weiter bearbeiten", danger: true })) return false;
  forgetAdminData();
  return true;
}

// Bearbeitete Daten verwerfen (werden beim nächsten Zeichnen neu geladen)
function forgetAdminData() {
  admin.settings = admin.vgSettings = admin.vgFleet = admin.saved = null;
}

// Wert im gerade bearbeiteten Datensatz (adminData) über einen Pfad wie "fleet.0.label" lesen bzw. setzen
function getPath(path) {
  return path.split(".").reduce((target, key) => target?.[key], adminData());
}

function setPath(path, value) {
  const keys = path.split(".");
  let target = adminData();
  for (const key of keys.slice(0, -1)) target = target[key];
  target[keys.at(-1)] = value;
}

function inputValue(input) {
  if (input.type === "checkbox") return input.checked;
  if (input.type === "number") return input.value === "" ? null : Number(input.value);
  return input.value;
}


// ------------------------------------------------------------ Aktionen
const VG_DEFAULT_KEYS = ["bks_code", "control_center", "places", "plan_min_level", "response_limits", "default_limit",
  "second_limit", "day_hours", "numbering"];

function settingsPayload() {
  const d = adminData();
  if (!d) return null;
  const vehicles = (fleet) => fleet.map((v) => ({ ...v, in_service_from: v.in_service_from || null,
    in_service_until: v.in_service_until || null, replaced_by: v.replaced_by || null }));
  if (d === admin.vgFleet) {
    return { tenants: d.tenants.map((t) => ({ slug: t.slug, fleet_version: t.fleet_version, substitutes: t.substitutes,
      fleet: vehicles(t.fleet) })) };
  }
  if (d === admin.vgSettings) {
    return { ...Object.fromEntries(VG_DEFAULT_KEYS.map((key) => [key, d[key] ?? ""])), colors: cleanColors(),
      tenants: d.tenants.map((t) => ({ slug: t.slug, station: t.station || "", plan_places: t.plan_places })) };
  }
  return { ...d, colors: cleanColors(), fleet: vehicles(d.fleet) };
}

// Betrifft die Änderung die oben ausgewählte Wehr bzw. Gesamtansicht? Dann deren Konfiguration neu holen
const affectsCurrent = () => admin.vg ? [config.tenant?.vg?.slug, config.vg?.slug].includes(admin.vg)
  : admin.slug === config.tenant?.slug;

// Nach Änderungen an der ausgewählten Wehr: Konfiguration, Farben und Logos neu holen
async function refreshCurrentTenant() {
  config = await api("/api/config");
  applyBranding();
  const link = $('link[href^="/api/theme.css"]');
  if (link) link.href = `/api/theme.css?t=${Date.now()}`;
  state.evaluation = null;
  state.incidents = null;
}

async function runAdminAction(button) {
  const { adminAction: action, index, step, key, name, code, mode, email, scope, slug } = button.dataset;
  const d = adminData();
  const list = button.dataset.list ? getPath(button.dataset.list) : null;     // Fahrzeugliste (Wehr oder eine Wehr der VG)
  const i = Number(index);
  const rerender = () => renderAdmin();
  if (action.startsWith("fee-")) { await runFeeAction(action, button.dataset); return; }
  switch (action) {
    case "save-settings": {
      const payload = settingsPayload();
      if (admin.vg && admin.section === "fleet") admin.vgFleet = { vg: admin.vg, ...(await apiJson(vgUrl("/fleet"), "PUT", payload)) };
      else if (admin.vg) admin.vgSettings = await apiJson(vgUrl("/settings"), "PUT", payload);
      else admin.settings = await apiJson(`/api/admin/${admin.slug}/settings`, "PUT", payload);
      admin.saved = JSON.stringify(settingsPayload());
      admin.check = null;
      // Die jeweils andere Sicht ist jetzt veraltet (Vorgaben vererben sich, Fahrzeuge stehen in beiden)
      if (admin.vg) admin.settings = null;
      else admin.vgSettings = admin.vgFleet = admin.overview = null;     // Name der Wehr kann sich geändert haben
      if (affectsCurrent()) await refreshCurrentTenant();
      toast("Gespeichert");
      await loadAdmin();
      return rerender();
    }
    case "clear-color":
      d.colors[key] = "";
      if (key === "brand") d.colors.brand_dark = "";
      admin.check = null;
      if (!d.colors.brand) d.palette = null;
      scheduleThemeCheck();
      return rerender();
    case "delete-asset":
      await api(`/api/admin/${admin.slug}/assets/${name}`, { method: "DELETE" });
      return afterAssetChange();
    case "assign-vehicle": {
      const input = $("#vg-vehicle-name");
      if (!input.value.trim()) return;
      assignVehicle(input.value.trim(), Number($("#vg-vehicle-tenant").value));
      return rerender();
    }
    case "add-vehicle":
      list.push(newVehicle());
      return rerender();
    case "move-vehicle": {
      const j = i + Number(step);
      [list[i], list[j]] = [list[j], list[i]];
      return rerender();
    }
    case "remove-vehicle": {
      const v = list[i];
      if (v.incidents && !await askConfirm({ title: `${v.name || v.call_sign} aus der Liste entfernen?`,
        text: `${plural(v.incidents, "Einsatz hat", "Einsätze haben")} Daten zu diesem Fahrzeug. Ohne Eintrag in der Liste erscheinen sie nicht mehr in Auswertung und Export. Die Daten bleiben erhalten.`,
        confirm: "Fahrzeug entfernen", danger: true })) return;
      list.splice(i, 1);
      return rerender();
    }
    case "add-substitute":
      getPath(button.dataset.subs)[""] = vehicleKey(list[0]);
      return rerender();
    case "remove-substitute":
      delete getPath(button.dataset.subs)[button.dataset.sub];
      return rerender();
    case "add-place":
      d.places.push({ name: "" });
      return rerender();
    case "remove-place": {
      const removed = d.places[i].name;
      for (const t of admin.vg ? d.tenants : [d]) t.plan_places = t.plan_places.filter((p) => p !== removed);
      d.places.splice(i, 1);
      return rerender();
    }
    case "fleet-compact":
      remember(fleetCompactKey(), fleetCompact() ? "0" : "1");
      return rerender();
    case "inherit":                          // Abweichung aufheben: Wert der VG übernehmen
      takeInherited(key);
      return rerender();
    case "parse-test":
      admin.parseResult = (await apiJson("/api/admin/parse-test", "POST", admin.vg
        ? { line: $("#parse-line").value, vg: admin.vg } : { line: $("#parse-line").value, unit_marker: d.unit_marker }));
      return rerender();
    case "person-add": {
      const last = $("#person-last").value.trim(), first = $("#person-first").value.trim();
      if (!last) { toast("Bitte einen Nachnamen eingeben."); $("#person-last").focus(); return; }
      return peopleChanged(await apiJson(peopleUrl(), "POST", { last_name: last, first_name: first }), "Person angelegt");
    }
    case "person-edit":
      admin.personEdit = { ...admin.people.members.find((m) => m.id === Number(button.dataset.id)) };
      return rerender();
    case "person-cancel":
      admin.personEdit = null;
      return rerender();
    case "person-save": {
      const e = admin.personEdit, to = $("#person-edit-tenant").value;
      let result = await apiJson(peopleUrl(`/${e.id}`), "PUT", { last_name: $("#person-edit-last").value,
        first_name: $("#person-edit-first").value, active: !$("#person-edit-left").checked });
      if (to) result = await apiJson(peopleUrl(`/${e.id}/transfer`), "POST", { to_slug: to });
      return peopleChanged(result, to ? "Person ist in die andere Wehr gewechselt" : "Person gespeichert");
    }
    case "person-merge": {
      const m = admin.people.members.find((x) => x.id === Number(button.dataset.id));
      const options = admin.people.members.filter((x) => x.id !== m.id).sort((x, y) => x.name.localeCompare(y.name, "de"))
        .map((x) => ({ value: x.id, label: x.name }));
      const into = await askAdminChoice({ title: `${m.name} zusammenführen`, label: "Gehört zu dieser Person",
        text: `Einsätze und Übungen von „${m.name}“ gehen auf die gewählte Person über, der Eintrag „${m.name}“ entfällt. Das lässt sich nicht rückgängig machen.`,
        options, confirm: "Zusammenführen", danger: true });
      if (!into) return;
      return peopleChanged(await apiJson(peopleUrl(`/${m.id}/merge`), "POST", { into: Number(into) }), "Personen zusammengeführt");
    }
    case "person-delete": {
      const m = admin.people.members.find((x) => x.id === Number(button.dataset.id));
      if (!await askConfirm({ title: `${m.name} löschen?`, text: "Die Person hat keine Einsätze und Übungen.", confirm: "Löschen", danger: true })) return;
      return peopleChanged(await api(peopleUrl(`/${m.id}`), { method: "DELETE" }), "Person gelöscht");
    }
    case "keyword-save": {
      const keywordCode = $("#keyword-code").value.trim().toUpperCase();
      const existing = admin.keywords.keywords.find((x) => x.code === keywordCode);
      admin.keywords = { ...(await apiJson(keywordsUrl(`/${encodeURIComponent(keywordCode)}`), "PUT",
        { name: $("#keyword-name").value, terms: $("#keyword-terms").value, active: existing ? existing.active : true })), scope: keywordsScope() };
      admin.keywordEdit = null;
      return keywordsChanged("Stichwort gespeichert");
    }
    case "keyword-edit":
      admin.keywordEdit = admin.keywords.keywords.find((x) => x.code === code);
      return rerender();
    case "keyword-cancel":
      admin.keywordEdit = null;
      return rerender();
    case "keyword-delete": {
      const k = admin.keywords.keywords.find((x) => x.code === code);
      const own = admin.vg || k?.source === "own";
      if (own && !await askConfirm({ title: `Stichwort ${code} löschen?`,
        text: "Alte Einsätze behalten das Stichwort, zeigen aber keine Bezeichnung mehr. Deaktivieren erhält die Bezeichnung.",
        confirm: "Stichwort löschen", danger: true })) return;
      admin.keywords = { ...(await api(keywordsUrl(`/${encodeURIComponent(code)}`), { method: "DELETE" })), scope: keywordsScope() };
      return keywordsChanged(own ? "Stichwort gelöscht" : "Wie bei der VG");
    }
    case "keywords-template":
      admin.keywords = { ...(await apiJson(keywordsUrl("/template"), "POST", {})), scope: keywordsScope() };
      return keywordsChanged("Stichworte ergänzt");
    case "keywords-reset":
      if (!await askConfirm({ title: admin.vg ? "Katalog der VG verwerfen?" : "Abweichungen der Wehr aufheben?",
        text: admin.vg ? "Die Vorlage wird wieder verwendet." : "Der Katalog der VG wird wieder verwendet.",
        confirm: admin.vg ? "Katalog verwerfen" : "Abweichungen aufheben", danger: true })) return;
      admin.keywords = { ...(await api(keywordsUrl(), { method: "DELETE" })), scope: keywordsScope() };
      return keywordsChanged(admin.vg ? "Vorlage wird verwendet" : "Katalog der VG wird verwendet");
    case "keywords-import": {
      if (mode === "replace" && !await askConfirm({ title: "Den ganzen Katalog ersetzen?", text: "Alle bisherigen Stichworte werden durch den Inhalt der Datei ersetzt.",
        confirm: "Katalog ersetzen", danger: true })) return;
      const form = new FormData();
      form.append("file", admin.importFile);
      admin.keywords = { ...(await api(keywordsUrl(`/import?mode=${mode}`), { method: "POST", body: form })), scope: keywordsScope() };
      admin.importFile = admin.importPreview = null;
      return keywordsChanged("Katalog importiert");
    }
    case "grant": {
      const [grantScope, grantSlug] = $("#grant-scope").value.split(":");
      const selected = $("#grant-scope").value;
      setMemberships(await apiJson("/api/admin/memberships", "POST",
        { email: $("#grant-email").value, scope: grantScope, slug: grantSlug, role: $("#grant-role").value }));
      admin.events = null;
      toast("Zugeordnet");
      rerender();
      if (admin.userScopes.some((x) => x.key === selected)) { $("#grant-scope").value = selected; filterRoleOptions(); }
      return;
    }
    case "revoke":
      if (!await askConfirm({ title: `Rolle von ${email} entfernen?`, text: "Die Rolle wird nur in diesem Bereich entzogen.", confirm: "Rolle entfernen", danger: true })) return;
      setMemberships(await api(`/api/admin/memberships?${new URLSearchParams({ email, scope, slug, role: key })}`, { method: "DELETE" }));
      admin.events = null;
      return rerender();
    case "effective":
      admin.effective = await api(`/api/admin/users/effective?${new URLSearchParams({ email })}`);
      rerender();
      $(".admin-body .message-info")?.scrollIntoView({ block: "nearest" });
      return;
    case "effective-close":
      admin.effective = null;
      return rerender();
    case "events":
      admin.events = (await api("/api/admin/role-events")).events;
      return rerender();
    case "role-open":
      admin.roleDraft = roleDraftFrom(roleById(Number(button.dataset.id)));
      rerender();
      $(".role-editor")?.scrollIntoView({ block: "start" });
      return;
    case "role-new":
      admin.roleDraft = newRoleDraft();
      return rerender();
    case "role-copy":
      admin.roleDraft = newRoleDraft(admin.roleDraft);
      return rerender();
    case "role-cancel":
      admin.roleDraft = null;
      return rerender();
    case "role-save": {
      const d = admin.roleDraft;
      admin.roles = d.id === null ? await apiJson("/api/admin/roles", "POST", rolePayload())
        : await apiJson(`/api/admin/roles/${d.id}`, "PUT", rolePayload());
      admin.roleDraft = null;
      admin.memberships = admin.events = null;          // Rollenauswahl und Protokoll neu laden
      toast("Rolle gespeichert");
      return rerender();
    }
    case "role-delete":
      if (!await askConfirm({ title: `Rolle „${admin.roleDraft.label}“ löschen?`, confirm: "Rolle löschen", danger: true })) return;
      admin.roles = await api(`/api/admin/roles/${admin.roleDraft.id}`, { method: "DELETE" });
      admin.roleDraft = null;
      admin.memberships = admin.events = null;
      toast("Rolle gelöscht");
      return rerender();
    case "session-end":
      if (!await askConfirm({ title: `Sitzung von ${email} beenden?`, text: "Die Person ist sofort abgemeldet.", confirm: "Sitzung beenden", danger: true })) return;
      admin.sessions = await api(`/api/super/sessions/${button.dataset.id}`, { method: "DELETE" });
      toast("Sitzung beendet");
      return rerender();
    case "sessions-user":
      if (!await askConfirm({ title: `Alle Sitzungen von ${email} beenden?`, text: "Die Person ist überall sofort abgemeldet.", confirm: "Alle Sitzungen beenden", danger: true })) return;
      admin.sessions = await api(`/api/super/sessions?email=${encodeURIComponent(email)}`, { method: "DELETE" });
      toast("Sitzungen beendet");
      return rerender();
    case "sessions-others":
      if (!await askConfirm({ title: "Alle anderen Benutzer abmelden?", text: "Sie müssen sich neu per Anmeldelink anmelden.", confirm: "Alle abmelden", danger: true })) return;
      admin.sessions = await api("/api/super/sessions?others=true", { method: "DELETE" });
      toast("Alle anderen abgemeldet");
      return rerender();
    case "create-vg":
      admin.superOverview = await apiJson("/api/super/vgs", "POST", { name: $("#vg-name").value, kind: $("#vg-kind").value });
      toast("VG angelegt");
      return rerender();
    case "rename-vg":
      admin.superOverview = await apiJson(`/api/super/vgs/${slug}`, "PUT", { slug, name: $(`[data-vg-name="${slug}"]`).value, kind: $(`[data-vg-kind="${slug}"]`).value });
      toast("Gespeichert");
      return rerender();
    case "move-tenant": {
      const others = admin.superOverview.vgs.filter((v) => v.slug !== admin.superVg);
      if (!others.length) { admin.error = "Es gibt keine andere Verbandsgemeinde, in die die Wehr verschoben werden könnte."; return renderAdmin(); }
      const name = admin.superOverview.tenants.find((t) => t.slug === slug)?.name || slug;
      const target = await askAdminChoice({ title: `„${name}“ verschieben`, confirm: "Verschieben",
        text: "Die Wehr wechselt mit allen Einsätzen in die andere Verbandsgemeinde. Zuordnungen auf VG-Ebene der bisherigen VG gelten dort nicht mehr; Vorgaben der neuen VG gelten ab sofort.",
        label: "Neue Verbandsgemeinde", options: others.map((v) => ({ value: v.slug, label: v.name })) });
      if (!target) return;
      admin.superOverview = await apiJson(`/api/super/tenants/${slug}?confirm=${encodeURIComponent(slug)}`, "PUT", { vg: target });
      admin.superVg = target; remember("super-vg", target);
      return superChanged("Wehr verschoben");
    }
    case "create-tenant":
      admin.superOverview = await apiJson("/api/super/tenants", "POST", {
        name: $("#tenant-name").value, vg: $("#tenant-vg").value, email: $("#tenant-email").value || null });
      return superChanged("Wehr angelegt");
    case "delete-tenant": {
      const name = admin.superOverview.tenants.find((t) => t.slug === slug)?.name || slug;
      if (!await askConfirm({ title: `Wehr „${name}“ archivieren?`, danger: true, confirm: "Archivieren",
        text: "Alle Zuordnungen werden entfernt, die Daten in deleted/ abgelegt (nichts wird gelöscht)." })) return;
      const typed = slug;
      admin.superOverview = await api(`/api/super/tenants/${slug}?confirm=${encodeURIComponent(typed)}`, { method: "DELETE" });
      return superChanged("Wehr archiviert");
    }
  }
}

/**
 * Dialog mit Auswahlliste (options) oder Texteingabe (input) -> gewählter Wert, bei Abbruch null.
 * Gegenstück zu askConfirm für Aktionen, die einen Wert brauchen.
 */
function askAdminChoice({ title, text = "", label, options = [], input = false, confirm = "OK", danger = false }) {
  return new Promise((resolve) => {
    const dialog = document.createElement("dialog");
    dialog.className = "dialog dialog-prompt";
    dialog.setAttribute("aria-labelledby", "choice-title");
    const control = input ? `<input type="text" id="choice-value" autocomplete="off">`
      : `<select id="choice-value">${options.map((o) => `<option value="${esc(o.value)}">${esc(o.label)}</option>`).join("")}</select>`;
    dialog.innerHTML = `<div class="dialog-body"><h3 id="choice-title">${esc(title)}</h3>
      <p class="prompt-text">${esc(text)}</p>
      <label class="field"><span>${esc(label)}</span>${control}</label>
      <div class="actions section-gap"><button type="button" class="btn btn-outline" data-answer="no">Abbrechen</button>
        <button type="button" class="btn ${danger ? "btn-danger" : "btn-primary"}" data-answer="yes">${esc(confirm)}</button></div></div>`;
    let answer = null;
    dialog.addEventListener("click", (e) => {
      const button = e.target.closest("[data-answer]");
      if (!button) return;
      if (button.dataset.answer === "yes") answer = dialog.querySelector("#choice-value").value.trim() || null;
      dialog.close();
    });
    dialog.addEventListener("close", () => { dialog.remove(); resolve(answer); });
    document.body.append(dialog);
    dialog.showModal();
    dialog.querySelector("#choice-value").focus();
  });
}

const peopleUrl = (path = "") => `/api/admin/${admin.slug}/members${path}`;

async function peopleChanged(result, message) {
  admin.people = { slug: admin.slug, ...result };
  admin.personEdit = null;
  trainingState.data = null;                       // Teilnehmerwahl der Übungen neu holen
  if (affectsCurrent()) await refreshCurrentTenant();
  toast(message);
  renderAdmin();
}

async function keywordsChanged(message) {
  if (affectsCurrent()) await refreshCurrentTenant();
  toast(message);
  renderAdmin();
}

async function superChanged(message) {
  if (!config.tenants.length) { location.reload(); return; }   // erste Wehr: Jahre, Reiter usw. neu aufbauen
  admin.overview = null;
  forgetAdminData();
  admin.keywords = admin.memberships = admin.roles = admin.roleDraft = null;
  await refreshCurrentTenant();
  renderScopes();
  renderTabs();
  toast(message);
  await showView();
}

// Logos sind sofort gespeichert; nur deren Adressen neu holen – ungespeicherte Eingaben (z. B. Farben) bleiben
async function afterAssetChange() {
  admin.settings.assets = (await api(`/api/admin/${admin.slug}/settings`)).assets;
  if (admin.slug === config.tenant?.slug) await refreshCurrentTenant();
  renderAdmin();
}

// ------------------------------------------------------------ Gebührenordnung der VG (Wehrleiter)
const FEE_RATES = [      // [Schlüssel, Bezeichnung, Einheit]
  ["personnel", "Je freiwilligem Feuerwehrangehörigen", "€/Std."], ["personnel_bma", "Je Angehörigem bei Brandmeldeanlagen", "€/Std."],
  ["fire_watch", "Brandsicherheitswache", "€/Std."], ["bma_flat_max", "Fehlalarm Brandmeldeanlage (höchstens)", "€"],
  ["admin_surcharge", "Verwaltungszuschlag auf Auslagen", "%"],
];
const emptyRates = () => ({ ...Object.fromEntries(FEE_RATES.map(([key]) => [key, 0])), vehicles: [] });

function feesSection() {
  const { schedules } = admin.fees, draft = admin.feeDraft;
  const rows = schedules.map((x) => `<tr>
    <td><strong>${esc(x.name)}</strong></td><td>${formatDate(x.valid_from)}</td><td class="right">${x.rates.vehicles.length}</td>
    <td class="right"><button type="button" class="btn btn-light btn-small" data-admin-action="fee-edit" data-id="${x.id}">Bearbeiten</button>
      <button type="button" class="btn btn-light btn-small" data-admin-action="fee-copy" data-id="${x.id}">Als neue Fassung</button>
      <button type="button" class="btn btn-outline btn-small" data-admin-action="fee-delete" data-id="${x.id}">Löschen</button></td></tr>`).join("");
  return `<p class="small muted">Kostensätze der Satzung über den Kostenersatz der Feuerwehr. Für einen Einsatz gilt die Fassung, die am Einsatztag gilt. Den Fahrzeugtyp eines Fahrzeugs bestimmt seine Bezeichnung in der Fahrzeugliste der Wehr (z. B. „HLF 20“).</p>
    <div class="table-wrap section-gap"><table class="mini-table admin-table"><thead><tr><th>Fassung</th><th>gültig ab</th><th class="right">Fahrzeugtypen</th><th></th></tr></thead>
      <tbody>${rows || `<tr><td colspan="4" class="muted">Noch keine Gebührenordnung hinterlegt.</td></tr>`}</tbody></table></div>
    ${draft ? "" : `<button type="button" class="btn btn-light btn-small section-gap" data-admin-action="fee-new">Neue Fassung</button>`}
    ${draft ? feeEditor(draft) : ""}`;
}

function feeEditor(d) {
  const vehicles = d.rates.vehicles.map((v, i) => `<tr>
    <td><input type="text" data-fee="rates.vehicles.${i}.code" value="${esc(v.code)}" placeholder="HLF 20" class="fee-code"></td>
    <td><input type="text" data-fee="rates.vehicles.${i}.name" value="${esc(v.name)}" placeholder="Hilfeleistungs-Löschgruppenfahrzeug 20"></td>
    <td><input type="number" step="0.01" min="0" data-fee="rates.vehicles.${i}.rate" value="${v.rate}" class="narrow"></td>
    <td><button type="button" class="icon-button" data-admin-action="fee-remove-vehicle" data-index="${i}" aria-label="entfernen">✕</button></td></tr>`).join("");
  return `<h3 class="section-gap">${d.id ? "Fassung bearbeiten" : "Neue Fassung"}</h3>
    <div class="form-grid">
      ${adminField("Bezeichnung", `<input type="text" data-fee="name" value="${esc(d.name)}" placeholder="Satzung vom …">`, "span-3")}
      ${adminField("gültig ab", `<input type="date" data-fee="valid_from" value="${esc(d.valid_from)}">`)}
      ${FEE_RATES.map(([key, label, unit]) => adminField(`${label} (${unit})`,
        `<input type="number" step="0.01" min="0" data-fee="rates.${key}" value="${d.rates[key]}">`, "span-2")).join("")}
    </div>
    <div class="table-wrap section-gap"><table class="mini-table admin-table"><thead><tr><th>Fahrzeugtyp</th><th>Beschreibung</th><th>€/Std.</th><th></th></tr></thead>
      <tbody>${vehicles}</tbody></table></div>
    <button type="button" class="btn btn-light btn-small section-gap" data-admin-action="fee-add-vehicle">Fahrzeugtyp hinzufügen</button>
    <div class="admin-actions"><button type="button" class="btn btn-outline" data-admin-action="fee-cancel">Abbrechen</button>
      <button type="button" class="btn btn-primary" data-admin-action="fee-save">Speichern</button></div>`;
}

async function runFeeAction(action, data) {
  const url = `/api/admin/vgs/${encodeURIComponent(admin.vg)}/fees`;
  const find = () => admin.fees.schedules.find((x) => x.id === Number(data.id));
  const copy = (x) => JSON.parse(JSON.stringify(x));
  switch (action) {
    case "fee-edit": admin.feeDraft = copy(find()); break;
    case "fee-copy": admin.feeDraft = { ...copy(find()), id: null, name: "", valid_from: "" }; break;
    case "fee-new": admin.feeDraft = { id: null, name: "", valid_from: "",
      rates: admin.fees.schedules[0] ? copy(admin.fees.schedules[0].rates) : emptyRates() }; break;
    case "fee-cancel": admin.feeDraft = null; break;
    case "fee-add-vehicle": admin.feeDraft.rates.vehicles.push({ code: "", name: "", rate: 0 }); break;
    case "fee-remove-vehicle": admin.feeDraft.rates.vehicles.splice(Number(data.index), 1); break;
    case "fee-delete":
      if (!await askConfirm({ title: `Fassung „${find().name}“ löschen?`, confirm: "Fassung löschen", danger: true })) return;
      admin.fees = { vg: admin.vg, ...(await api(`${url}/${data.id}`, { method: "DELETE" })) };
      toast("Fassung gelöscht");
      break;
    case "fee-save": {
      const d = admin.feeDraft;
      const body = { name: d.name, valid_from: d.valid_from, rates: d.rates };
      admin.fees = { vg: admin.vg, ...(await apiJson(d.id ? `${url}/${d.id}` : url, d.id ? "PUT" : "POST", body)) };
      admin.feeDraft = null;
      toast("Gebührenordnung gespeichert");
      break;
    }
  }
  renderAdmin();
}

function setFeePath(path, value) {
  const keys = path.split(".");
  let target = admin.feeDraft;
  for (const key of keys.slice(0, -1)) target = target[key];
  target[keys.at(-1)] = value;
}

// ------------------------------------------------------------ Ereignisse
$("#view-admin").addEventListener("click", async (e) => {
  const vgButton = e.target.closest("[data-super-vg]");
  if (vgButton) { admin.superVg = vgButton.dataset.superVg; remember("super-vg", admin.superVg); renderAdmin(); return; }
  const section = e.target.closest("[data-admin-section]");
  if (section) {
    // Ein Bereich wechselt nie die Auswahl (Wehr bzw. Verbandsgemeinde). Bearbeitet er andere Daten (VG: Fahrzeuge
    // statt Vorgaben), ungespeicherte Änderungen nur nach Rückfrage verwerfen.
    const before = adminData(), previous = admin.section;
    admin.section = section.dataset.adminSection;
    const after = adminData();
    admin.section = previous;
    if (before && before !== after) {
      if (!await confirmDiscard()) return;
      admin.saved = null;
    }
    remember("admin-section", section.dataset.adminSection);
    adminGo({ section: section.dataset.adminSection, parseResult: null });
    return;
  }
  const button = e.target.closest("[data-admin-action]");
  if (!button || button.disabled) return;
  try {
    admin.error = "";
    await runAdminAction(button);
  } catch (err) {
    admin.error = err.message;
    renderAdmin();
    $("#view-admin").scrollIntoView({ block: "start" });
  }
});

$("#view-admin").addEventListener("input", (e) => {
  handleAdminInput(e);
  updateDirty();
});
$("#view-admin").addEventListener("change", () => setTimeout(updateDirty));   // nach dem Handler unten

// Neuladen, Schließen oder Wechsel oben in der Kopfzeile (lädt neu): Rückfrage des Browsers
window.addEventListener("beforeunload", (e) => {
  if (settingsDirty()) e.preventDefault();
});

function handleAdminInput(e) {
  const t = e.target;
  if (t.dataset.role === "label" || t.dataset.role === "description") { admin.roleDraft[t.dataset.role] = t.value; return; }
  if (t.dataset.bind) {
    setPath(t.dataset.bind, t.dataset.number !== undefined ? Number(t.value) : inputValue(t));
    return;
  }
  if (t.dataset.bks) { setBks(t.dataset.bks, t.value.trim()); return; }
  if (t.dataset.fee) { setFeePath(t.dataset.fee, t.type === "number" ? Number(t.value || 0) : t.value); return; }
  if (t.dataset.colorPicker) { setColor(t.dataset.colorPicker, t.value.toUpperCase(), "picker"); return; }
  if (t.dataset.colorHex !== undefined && t.dataset.colorHex) { setColor(t.dataset.colorHex, t.value.trim().toUpperCase(), "hex"); return; }
  if (t.dataset.colorRgb) {
    const key = t.dataset.colorRgb;
    const rgb = [0, 1, 2].map((c) => Number($(`[data-color-rgb="${key}"][data-channel="${c}"]`).value || 0));
    setColor(key, rgbToHex(rgb), "rgb");
    return;
  }
  if (t.dataset.limits !== undefined) {
    adminData().response_limits = t.value.split(/[,;\s]+/).map(Number).filter((n) => n > 0);
    return;
  }
  if (t.dataset.personSearch !== undefined) {
    admin.personQuery = t.value;
    $("#person-list").innerHTML = personListHtml();
    return;
  }
  if (t.dataset.userFilter !== undefined) { admin.userFilter = t.value; renderAdmin(); return; }
  if (t.dataset.superSearch !== undefined) { admin.superQuery = t.value; $("#super-list").innerHTML = superListHtml(); return; }
  if (t.dataset.fleetSearch !== undefined) { admin.fleetQuery = t.value; filterFleetRows(); return; }
  if (t.dataset.keywordSearch !== undefined) {
    admin.keywordQuery = t.value;
    const position = t.selectionStart;
    renderAdmin();
    const search = $("[data-keyword-search]");
    search.focus();
    search.setSelectionRange(position, position);
  }
}

$("#view-admin").addEventListener("change", async (e) => {
  const t = e.target;
  if (t.dataset.personFlagged !== undefined || t.dataset.personInactive !== undefined) {
    if (t.dataset.personFlagged !== undefined) admin.personFlagged = t.checked; else admin.personInactive = t.checked;
    $("#person-list").innerHTML = personListHtml();
    return;
  }
  try {
    if (t.dataset.adminTenant !== undefined) {
      if (!await confirmDiscard()) { t.value = admin.vg ? `vg:${admin.vg}` : admin.slug; return; }
      const vg = t.value.startsWith("vg:") ? t.value.slice(3) : null;
      await adminGo({ vg, ...(vg ? {} : { slug: t.value }), saved: null, parseResult: null, keywordEdit: null });
      return;
    }
    if (t.dataset.fleetTenant !== undefined) {         // Fahrzeug wechselt die Wehr (Fahrzeuge der VG)
      const [from, i] = t.dataset.fleetTenant.split(":").map(Number);
      if (!await moveFleetVehicle(from, i, t.value === "" ? null : Number(t.value))) t.value = String(from);
      renderAdmin();
      return;
    }
    if (t.dataset.assignVehicle !== undefined) {
      if (t.value !== "") assignVehicle(t.dataset.assignVehicle, Number(t.value));
      renderAdmin();
      return;
    }
    if (t.dataset.bks || t.dataset.limits !== undefined) { renderAdmin(); return; }   // abgeleitete Werte, Standardgrenze
    if (/(^|\.)places\.\d+\.name$/.test(t.dataset.bind || "")) { renderAdmin(); return; }
    if (/^tenants\.\d+\.station$/.test(t.dataset.bind || "")) { renderAdmin(); return; }
    if (/(^|\.)fleet\.\d+\.label$/.test(t.dataset.bind || "")) { renderAdmin(); return; }   // Hinweis Gebührenordnung
    if (/(^|\.)fleet\.\d+\.name$/.test(t.dataset.bind || "")) {
      const v = getPath(t.dataset.bind.replace(/\.name$/, ""));
      v.name = v.name.trim();
      const known = knownVehicle(v.name);
      if (known) v.types = known.types;
      if (known?.label && !v.label) v.label = known.label;     // Fahrzeugtyp, wenn er eindeutig ist
      renderAdmin();
      return;
    }
    if (t.dataset.planPlace !== undefined) {            // Wehr: Ort zählt zum Ausrückebereich; VG: „Wehr:Ort“
      const d = adminData();
      const [tenant, place] = admin.vg ? t.dataset.planPlace.split(":").map(Number) : [null, Number(t.dataset.planPlace)];
      const target = admin.vg ? d.tenants[tenant] : d;
      const name = d.places[place].name;
      target.plan_places = t.checked ? [...new Set([...target.plan_places, name])] : target.plan_places.filter((p) => p !== name);
      return;
    }
    if (t.dataset.substitute !== undefined || t.dataset.substituteBlock !== undefined) {
      const path = t.dataset.subs;
      const entries = Object.entries(getPath(path));
      const i = Number(t.dataset.substitute ?? t.dataset.substituteBlock);
      if (t.dataset.substitute !== undefined) entries[i][0] = t.value.trim();
      else entries[i][1] = t.value;
      setPath(path, Object.fromEntries(entries));
      return;
    }
    if (t.dataset.asset) {
      const form = new FormData();
      form.append("file", t.files[0]);
      await api(`/api/admin/${admin.slug}/assets/${t.dataset.asset}`, { method: "PUT", body: form });
      toast(t.dataset.asset.startsWith("font") ? "Schrift gespeichert" : "Logo gespeichert");
      await afterAssetChange();
      return;
    }
    if (t.dataset.keywordActive) {
      const k = admin.keywords.keywords.find((x) => x.code === t.dataset.keywordActive);
      admin.keywords = { ...(await apiJson(keywordsUrl(`/${encodeURIComponent(k.code)}`), "PUT",
        { name: k.name, terms: k.terms, active: t.checked })), scope: keywordsScope() };
      await keywordsChanged(t.checked ? (admin.vg ? "Stichwort aktiviert" : "Stichwort gilt hier")
        : (admin.vg ? "Stichwort deaktiviert" : "Stichwort gilt hier nicht"));
      return;
    }
    if (t.dataset.keywordDeviations !== undefined) { admin.keywordDeviationsOnly = t.checked; renderAdmin(); return; }
    if (t.dataset.keywordFile !== undefined) {
      admin.importFile = t.files[0];
      const form = new FormData();
      form.append("file", admin.importFile);
      admin.importPreview = await api(keywordsUrl("/import?mode=preview"), { method: "POST", body: form });
      renderAdmin();
      return;
    }
    if (t.id === "grant-scope") { filterRoleOptions(); return; }
    if (admin.roleDraft && handleRoleChange(t)) { renderAdmin(); return; }
    if (t.dataset.tenantActive) {
      admin.superOverview = await apiJson(`/api/super/tenants/${t.dataset.tenantActive}`, "PUT", { active: t.checked });
      await superChanged(t.checked ? "Wehr aktiviert" : "Wehr deaktiviert");
      return;
    }
  } catch (err) {
    admin.error = err.message;
    if (t.type === "file") t.value = "";
    renderAdmin();
  }
});

// Auswahl im Rollen-Editor -> true, wenn neu gezeichnet werden soll
function handleRoleChange(t) {
  const d = admin.roleDraft;
  if (t.dataset.rolePermission) { toggleRolePermission(t.dataset.rolePermission, t.checked); return true; }
  for (const field of ["granted_by", "grants"]) {
    const id = t.dataset[field === "granted_by" ? "roleGranted_by" : "roleGrants"];
    if (id !== undefined) {
      d[field] = t.checked ? [...new Set([...d[field], Number(id)])] : d[field].filter((x) => x !== Number(id));
      return true;
    }
  }
  if (t.dataset.role === "parent") { d.parent = t.value ? Number(t.value) : null; return true; }
  if (t.dataset.role === "scope" || t.dataset.role === "vg") {
    d[t.dataset.role] = t.dataset.role === "vg" ? (t.value || null) : t.value;
    // Elternrolle, Verteilung und Rechte nur behalten, wenn sie zum neuen Bereich bzw. zur VG passen
    const ids = new Set(draftVisible(d).map((r) => r.id));
    if (d.parent && (!ids.has(d.parent) || roleById(d.parent).scope !== d.scope)) d.parent = null;
    d.granted_by = d.granted_by.filter((x) => ids.has(x));
    d.grants = d.grants.filter((x) => ids.has(x) && (d.vg !== null || roleById(x).vg === null));
    d.permissions = d.permissions.filter((k) => admin.roles.permissions.find((p) => p.key === k).scopes.includes(d.scope));
    return true;
  }
  return false;
}

// Rollenauswahl passend zum ersten Bereich, sobald der Benutzer-Bereich gezeichnet ist
new MutationObserver(() => { if (admin.section === "users") filterRoleOptions(); })
  .observe($("#view-admin"), { childList: true });
