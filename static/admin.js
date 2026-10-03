"use strict";

// Verwaltung: Einstellungen der Wehr (Name, Farben, Logos, Fahrzeuge, BKS-Kennung, Orte, Bedarfsplan),
// Stichwortkatalog, Benutzer, Rollen und – für Superadmins – Verbandsgemeinden und Wehren.
// Wird nach app.js geladen und trägt sich in VIEWS ein. Rechte prüft das Backend (app/admin.py).

// [Schlüssel, Bezeichnung, braucht die Einstellungen der Wehr, nur Superadmin, Auswahl oben: Wehr, Wehrleitung, beide,
//  nötiges Recht in der gewählten Wehr bzw. VG (rbac.py); bei „beide“ entscheidet admin.overview.users]
const ADMIN_SECTIONS = [
  ["unit", "Wehr", true, false, "tenant", "tenant.settings"], ["fleet", "Fahrzeuge", true, false, "tenant", "tenant.settings"],
  ["bks", "BKS-Kennung", true, false, "tenant", "tenant.settings"],
  ["places", "Orte & Bedarfsplan", true, false, "tenant", "tenant.settings"],
  ["keywords", "Stichworte", false, false, "tenant", "tenant.keywords"],
  ["vehicles", "Fahrzeuge der VG", false, false, "vg", "vg.fees"], ["fees", "Gebührenordnung", false, false, "vg", "vg.fees"],
  ["users", "Benutzer", false, false, "any"], ["roles", "Rollen", false, false, "any"],
  ["super", "Wehren & VGs", false, true, "any"],
];
const SETTINGS_SECTIONS = ADMIN_SECTIONS.filter((s) => s[2]).map((s) => s[0]);

const admin = {
  overview: null, slug: null, section: null, settings: null, keywords: null, memberships: null, superOverview: null,
  check: null, importFile: null, importPreview: null, keywordQuery: "", keywordEdit: null, parseResult: null, error: "",
  fees: null, feeDraft: null,
  userScopes: null,           // Bereiche, in denen der Benutzer Rollen vergeben darf, mit den Rollen
  effective: null,            // Rechte einer Person mit Herkunft (Benutzer → „Rechte“)
  events: null,               // Protokoll der Vergaben und Rollenänderungen
  roles: null,                // Rechtekatalog und Rollen (/api/admin/roles)
  roleDraft: null,            // Rolle im Editor (neu: id null)
  vg: null,                   // ausgewählte Wehrleitung (Slug der VG) statt einer Wehr
  vgVehicles: null,           // Fahrzeuge der VG (Wehrleitung)
  savedSettings: null,        // Stand der Einstellungen beim Laden/Speichern – Vergleich für „ungespeichert“
};

// Hilfe zum gerade offenen Bereich der Verwaltung
const ADMIN_HELP = { unit: "admin_colors", fleet: "admin_fleet", bks: "admin_bks", places: "admin_places",
  keywords: "admin_keywords", vehicles: "admin_vg_vehicles", fees: "fees", users: "admin_users",
  roles: () => admin.roleDraft ? "admin_role_editor" : "admin_roles" };

VIEWS.admin = { label: "Verwaltung", load: loadAdmin, render: renderAdmin, noYear: true,
  visible: () => config.admin, help: () => helpValue(ADMIN_HELP[admin.section]) || "sec_admin" };

// ------------------------------------------------------------ Laden
async function loadAdmin() {
  if (!admin.overview) {
    admin.overview = await api("/api/admin");
    // Gewählte Wehr behalten (z. B. nach dem Speichern), sonst die oben ausgewählte, sonst die erste
    const pick = (slug) => admin.overview.tenants.find((t) => t.slug === slug);
    admin.slug = (pick(admin.slug) || pick(config.tenant?.slug) || admin.overview.tenants[0])?.slug || null;
    // Oben die Wehrleitung gewählt: in der Verwaltung ebenfalls (falls sie die VG verwalten darf)
    if (config.vg && admin.overview.vgs.some((v) => v.slug === config.vg.slug)) admin.vg = config.vg.slug;
  }
  const sections = adminSections();
  if (!sections.some(([key]) => key === admin.section)) admin.section = sections[0]?.[0] || null;
  const s = admin.section;
  if (SETTINGS_SECTIONS.includes(s) && admin.settings?.slug !== admin.slug) {
    admin.settings = await api(`/api/admin/${admin.slug}/settings`);
    admin.savedSettings = JSON.stringify(settingsPayload());
    admin.check = null;
  }
  if (s === "keywords" && admin.keywords?.slug !== admin.slug) {
    admin.keywords = { ...(await api(`/api/admin/${admin.slug}/keywords`)), slug: admin.slug };
  }
  if (s === "users" && !admin.memberships) setMemberships(await api("/api/admin/memberships"));
  if (s === "roles" && !admin.roles) admin.roles = await api("/api/admin/roles");
  if (s === "super" && !admin.superOverview) admin.superOverview = await api("/api/super/overview");
  if (s === "fees" && admin.fees?.vg !== admin.vg) {
    admin.fees = { vg: admin.vg, ...(await api(`/api/admin/vgs/${encodeURIComponent(admin.vg)}/fees`)) };
    admin.feeDraft = null;
  }
  if (s === "vehicles" && admin.vgVehicles?.vg !== admin.vg) await loadVgVehicles();
}

async function loadVgVehicles() {
  admin.vgVehicles = { vg: admin.vg, ...(await api(`/api/admin/vgs/${encodeURIComponent(admin.vg)}/vehicles`)) };
}

// Rechte in der ausgewählten Wehr bzw. VG der Verwaltung
function adminGranted() {
  const { overview } = admin;
  return (admin.vg ? overview.vgs.find((v) => v.slug === admin.vg)
    : overview.tenants.find((t) => t.slug === admin.slug))?.permissions || [];
}

// VG der oben gewählten Wehr, falls der Benutzer sie verwalten darf (Bereiche der Wehrleitung auch bei gewählter Wehr)
function adminTenantVg() {
  const { overview } = admin;
  const tenant = overview.tenants.find((t) => t.slug === admin.slug);
  return overview.vgs.find((v) => v.slug === tenant?.vg_slug) || null;
}

function adminSections() {
  const { overview } = admin;
  const mode = admin.vg ? "vg" : "tenant";
  const granted = adminGranted();
  const tenantVg = admin.vg ? null : adminTenantVg();
  return ADMIN_SECTIONS.filter(([, , , superOnly, scope, permission]) => {
    if (superOnly) return overview.superadmin;
    if (scope === "any") return overview.users || overview.superadmin;
    // Bei gewählter Wehr führen die Bereiche der VG direkt zur Wehrleitung ihrer VG
    if (scope === "vg" && tenantVg) return tenantVg.permissions.includes(permission);
    return scope === mode && granted.includes(permission);
  });
}

async function adminGo(changes) {
  Object.assign(admin, changes, { error: "" });
  await showView();
}

// ------------------------------------------------------------ Rahmen
function renderAdmin() {
  const { tenants, vgs } = admin.overview;
  // Auswahl: Wehrleitung einer VG (Fahrzeuge der VG, Gebührenordnung) oder eine Wehr
  const choices = [...vgs.map((v) => ({ key: `vg:${v.slug}`, label: `Wehrleitung · ${v.name}` })),
    ...tenants.map((t) => ({ key: t.slug, label: `${t.name} · ${t.vg}` }))];
  const current = admin.vg ? `vg:${admin.vg}` : admin.slug;
  const tenantSelect = choices.length > 1 && !["users", "roles", "super"].includes(admin.section)
    ? `<label class="field admin-tenant"><span>${admin.vg ? "Wehrleitung" : "Wehr"}</span><select data-admin-tenant>${choices.map((c) =>
      `<option value="${esc(c.key)}" ${c.key === current ? "selected" : ""}>${esc(c.label)}</option>`).join("")}</select></label>` : "";
  const sections = `<div class="segments" role="group" aria-label="Verwaltungsbereich">${adminSections().map(([key, label]) =>
    `<button type="button" data-admin-section="${key}" aria-pressed="${key === admin.section}" class="${key === admin.section ? "active" : ""}">${label}</button>`).join("")}</div>`;
  const body = ({
    unit: unitSection, fleet: fleetSection, bks: bksSection, places: placesSection, vehicles: vgVehiclesSection,
    keywords: keywordsSection, users: usersSection, roles: rolesSection, super: superSection, fees: feesSection,
  }[admin.section] || (() => `<p class="muted">Hier gibt es für dich nichts zu verwalten.</p>`))();
  $("#view-admin").innerHTML = `<div class="card admin-card">
    <div class="admin-head">${sections}${tenantSelect}</div>
    ${admin.error ? errorBox(admin.error) : ""}
    <div class="admin-body">${body}</div>
  </div>`;
  if (admin.section === "unit") updateThemePreview();
  updateDirty();
}

let adminFieldSequence = 0;
const adminField = (label, input, span = "", help = "") => {
  const existing = input.match(/<(?:input|select|textarea)\b[^>]*\bid="([^"]+)"/);
  const id = existing?.[1] || `admin-field-${++adminFieldSequence}`;
  const control = existing ? input : input.replace(/<(input|select|textarea)\b/, `<$1 id="${id}"`);
  return `<div class="field ${span}"><span><label for="${id}">${label}</label>${help ? helpButton(help) : ""}</span>${control}</div>`;
};
const textInput = (path, value, attributes = "") =>
  `<input type="text" data-bind="${path}" value="${esc(value ?? "")}" ${attributes}>`;
// Speichern-Leiste der Einstellungen; bei ungespeicherten Änderungen klebt sie unten am Fenster
const saveButton = (label = "Speichern") =>
  `<div class="admin-actions" id="admin-savebar"><span class="unsaved-note">Ungespeicherte Änderungen</span>
    <button type="button" class="btn btn-primary" data-admin-action="save-settings">${label}</button></div>`;

// Ungespeicherte Änderungen an den Einstellungen der Wehr (Name, Farben, Fahrzeuge, Orte …)
const settingsDirty = () => Boolean(admin.settings && admin.savedSettings !== JSON.stringify(settingsPayload()));

function updateDirty() {
  $("#admin-savebar")?.classList.toggle("dirty", settingsDirty());
}

// Vor dem Wechsel der Wehr: ungespeicherte Änderungen nur nach Rückfrage verwerfen
function confirmDiscard() {
  if (!settingsDirty()) return true;
  if (!confirm("Die Änderungen an den Einstellungen sind noch nicht gespeichert. Verwerfen?")) return false;
  admin.settings = admin.savedSettings = null;
  return true;
}

// Wert in admin.settings über einen Pfad wie "fleet.0.label" setzen
function setPath(path, value) {
  const keys = path.split(".");
  let target = admin.settings;
  for (const key of keys.slice(0, -1)) target = target[key];
  target[keys.at(-1)] = value;
}

function inputValue(input) {
  if (input.type === "checkbox") return input.checked;
  if (input.type === "number") return input.value === "" ? null : Number(input.value);
  return input.value;
}


// ------------------------------------------------------------ Aktionen
function settingsPayload() {
  const s = admin.settings;
  return {
    ...s, colors: cleanColors(),
    fleet: s.fleet.map((v) => ({ ...v, in_service_from: v.in_service_from || null, in_service_until: v.in_service_until || null,
      replaced_by: v.replaced_by || null })),
  };
}

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
  const s = admin.settings;
  const i = Number(index);
  const rerender = () => renderAdmin();
  if (action.startsWith("fee-")) { await runFeeAction(action, button.dataset); return; }
  switch (action) {
    case "save-settings": {
      admin.settings = await apiJson(`/api/admin/${admin.slug}/settings`, "PUT", settingsPayload());
      admin.savedSettings = JSON.stringify(settingsPayload());
      admin.check = null;
      admin.overview = null;                 // Name der Wehr kann sich geändert haben
      if (admin.slug === config.tenant?.slug) await refreshCurrentTenant();
      toast("Gespeichert");
      await loadAdmin();
      return rerender();
    }
    case "select-tenant":
      if (settingsDirty() && !confirm("Die Änderungen sind noch nicht gespeichert. Trotzdem wechseln?")) return;
      await apiJson("/api/scope", "POST", { key: `t:${admin.slug}` });
      admin.settings = admin.savedSettings = null;    // kein Rückfrage-Dialog beim Neuladen
      location.reload();
      return;
    case "clear-color":
      s.colors[key] = "";
      if (key === "brand") s.colors.brand_dark = "";
      admin.check = null;
      if (!s.colors.brand) admin.settings.palette = null;
      scheduleThemeCheck();
      return rerender();
    case "delete-asset":
      await api(`/api/admin/${admin.slug}/assets/${name}`, { method: "DELETE" });
      return afterAssetChange();
    case "assign-vehicle": {
      const input = $("#vg-vehicle-name"), select = $("#vg-vehicle-tenant");
      if (!input.value.trim()) return;
      const fake = { dataset: { name: input.value.trim(), source: "", callSign: "" }, value: select.value };
      return moveVehicle(fake);
    }
    case "edit-fleet":
      if (!confirmDiscard()) return;
      return adminGo({ vg: null, slug: button.dataset.tenant, section: "fleet" });
    case "add-vehicle":
      s.fleet.push({ call_sign: "", name: "", suggested_name: "", types: [], label: "", in_service_from: "", in_service_until: "", replaced_by: "", in_plan_crew: true, incidents: 0 });
      return rerender();
    case "move-vehicle": {
      const j = i + Number(step);
      [s.fleet[i], s.fleet[j]] = [s.fleet[j], s.fleet[i]];
      return rerender();
    }
    case "remove-vehicle": {
      const v = s.fleet[i];
      if (v.incidents && !confirm(`${v.name || v.call_sign} hat Daten in ${v.incidents} Einsätzen. Ohne Eintrag in der Liste erscheinen sie nicht mehr in Auswertung und Export (die Daten bleiben erhalten). Entfernen?`)) return;
      s.fleet.splice(i, 1);
      return rerender();
    }
    case "add-substitute":
      s.substitutes[""] = vehicleKey(s.fleet[0]);
      return rerender();
    case "remove-substitute":
      delete s.substitutes[button.dataset.sub];
      return rerender();
    case "add-place":
      s.places.push({ name: "" });
      return rerender();
    case "remove-place":
      s.plan_places = s.plan_places.filter((p) => p !== s.places[i].name);
      s.places.splice(i, 1);
      return rerender();
    case "parse-test":
      admin.parseResult = (await apiJson("/api/admin/parse-test", "POST",
        { line: $("#parse-line").value, unit_marker: s.unit_marker }));
      return rerender();
    case "keyword-save": {
      const keywordCode = $("#keyword-code").value.trim().toUpperCase();
      const existing = admin.keywords.keywords.find((x) => x.code === keywordCode);
      admin.keywords = { ...(await apiJson(`/api/admin/${admin.slug}/keywords/${encodeURIComponent(keywordCode)}`, "PUT",
        { name: $("#keyword-name").value, terms: $("#keyword-terms").value, active: existing ? existing.active : true })), slug: admin.slug };
      admin.keywordEdit = null;
      return keywordsChanged("Stichwort gespeichert");
    }
    case "keyword-edit":
      admin.keywordEdit = admin.keywords.keywords.find((x) => x.code === code);
      return rerender();
    case "keyword-cancel":
      admin.keywordEdit = null;
      return rerender();
    case "keyword-delete":
      if (!confirm(`${code} löschen? Alte Einsätze behalten das Stichwort, zeigen aber keine Bezeichnung mehr. Deaktivieren erhält sie.`)) return;
      admin.keywords = { ...(await api(`/api/admin/${admin.slug}/keywords/${encodeURIComponent(code)}`, { method: "DELETE" })), slug: admin.slug };
      return keywordsChanged("Stichwort gelöscht");
    case "keywords-template":
      admin.keywords = { ...(await apiJson(`/api/admin/${admin.slug}/keywords/template`, "POST", {})), slug: admin.slug };
      return keywordsChanged("Stichworte ergänzt");
    case "keywords-reset":
      if (!confirm("Eigenen Katalog verwerfen und wieder die Vorlage verwenden?")) return;
      admin.keywords = { ...(await api(`/api/admin/${admin.slug}/keywords`, { method: "DELETE" })), slug: admin.slug };
      return keywordsChanged("Vorlage wird verwendet");
    case "keywords-import": {
      if (mode === "replace" && !confirm("Den ganzen Katalog durch die Datei ersetzen?")) return;
      const form = new FormData();
      form.append("file", admin.importFile);
      admin.keywords = { ...(await api(`/api/admin/${admin.slug}/keywords/import?mode=${mode}`, { method: "POST", body: form })), slug: admin.slug };
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
      if (!confirm(`Rolle von ${email} in diesem Bereich entfernen?`)) return;
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
      if (!confirm(`Rolle „${admin.roleDraft.label}“ löschen?`)) return;
      admin.roles = await api(`/api/admin/roles/${admin.roleDraft.id}`, { method: "DELETE" });
      admin.roleDraft = null;
      admin.memberships = admin.events = null;
      toast("Rolle gelöscht");
      return rerender();
    case "create-vg":
      admin.superOverview = await apiJson("/api/super/vgs", "POST", { slug: $("#vg-slug").value.trim(), name: $("#vg-name").value });
      toast("VG angelegt");
      return rerender();
    case "rename-vg":
      admin.superOverview = await apiJson(`/api/super/vgs/${slug}`, "PUT", { slug, name: $(`[data-vg-name="${slug}"]`).value });
      toast("Gespeichert");
      return rerender();
    case "create-tenant":
      admin.superOverview = await apiJson("/api/super/tenants", "POST", { slug: $("#tenant-slug").value.trim(),
        name: $("#tenant-name").value, vg: $("#tenant-vg").value, email: $("#tenant-email").value || null });
      return superChanged("Wehr angelegt");
    case "delete-tenant": {
      const typed = prompt(`Wehr „${slug}“ entfernen? Alle Zuordnungen werden gelöscht, die Daten in deleted/ abgelegt.\nZum Bestätigen den Kurznamen eintippen:`);
      if (typed !== slug) return;
      admin.superOverview = await api(`/api/super/tenants/${slug}?confirm=${encodeURIComponent(typed)}`, { method: "DELETE" });
      return superChanged("Wehr entfernt");
    }
  }
}

async function keywordsChanged(message) {
  if (admin.slug === config.tenant?.slug) await refreshCurrentTenant();
  toast(message);
  renderAdmin();
}

async function superChanged(message) {
  if (!config.tenants.length) { location.reload(); return; }   // erste Wehr: Jahre, Reiter usw. neu aufbauen
  admin.overview = null;
  admin.settings = admin.keywords = admin.memberships = admin.roles = admin.roleDraft = null;
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
  return `<p class="small muted">Kostensätze der Satzung über den Kostenersatz der Feuerwehr. Für einen Einsatz gilt die Fassung, die am Einsatztag gilt. Den Fahrzeugtyp eines Fahrzeugs bestimmt seine Bezeichnung in der Fahrzeugliste der Wehr (z. B. „HLF 20“).${helpButton("fees")}</p>
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
      if (!confirm(`Fassung „${find().name}“ löschen?`)) return;
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
  const section = e.target.closest("[data-admin-section]");
  if (section) {
    const key = section.dataset.adminSection;
    const toVg = !admin.vg && ADMIN_SECTIONS.find((x) => x[0] === key)?.[4] === "vg";
    if (toVg && !confirmDiscard()) return;
    adminGo({ section: key, parseResult: null, ...(toVg ? { vg: adminTenantVg().slug, keywordEdit: null } : {}) });
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
    if (t.dataset.bind === "unit_marker") $("#bks-derived").innerHTML = bksDerived(admin.settings);
    return;
  }
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
    admin.settings.response_limits = t.value.split(/[,;\s]+/).map(Number).filter((n) => n > 0);
    return;
  }
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
  try {
    if (t.dataset.adminTenant !== undefined) {
      if (!confirmDiscard()) { t.value = admin.vg ? `vg:${admin.vg}` : admin.slug; return; }
      const vg = t.value.startsWith("vg:") ? t.value.slice(3) : null;
      await adminGo({ vg, ...(vg ? {} : { slug: t.value }), parseResult: null, keywordEdit: null });
      return;
    }
    if (t.dataset.moveVehicle !== undefined) { await moveVehicle(t); return; }
    if (t.dataset.limits !== undefined) { renderAdmin(); return; }     // Auswahl der Standardgrenze aktualisieren
    if (t.dataset.bind?.startsWith("places.") && t.dataset.bind.endsWith(".name")) { renderAdmin(); return; }
    if (/^fleet\.\d+\.label$/.test(t.dataset.bind || "")) { renderAdmin(); return; }   // Hinweis Gebührenordnung
    if (/^fleet\.\d+\.name$/.test(t.dataset.bind || "")) {
      const v = admin.settings.fleet[Number(t.dataset.bind.split(".")[1])];
      v.name = v.name.trim();
      const known = knownVehicle(v.name);
      if (known) v.types = known.types;
      if (known?.label && !v.label) v.label = known.label;     // Fahrzeugtyp, wenn er eindeutig ist
      renderAdmin();
      return;
    }
    if (t.dataset.planPlace !== undefined) {
      const place = admin.settings.places[Number(t.dataset.planPlace)].name;
      admin.settings.plan_places = t.checked ? [...new Set([...admin.settings.plan_places, place])]
        : admin.settings.plan_places.filter((p) => p !== place);
      return;
    }
    if (t.dataset.substitute !== undefined || t.dataset.substituteBlock !== undefined) {
      const entries = Object.entries(admin.settings.substitutes);
      const i = Number(t.dataset.substitute ?? t.dataset.substituteBlock);
      if (t.dataset.substitute !== undefined) entries[i][0] = t.value.trim();
      else entries[i][1] = t.value;
      admin.settings.substitutes = Object.fromEntries(entries);
      return;
    }
    if (t.dataset.asset) {
      const form = new FormData();
      form.append("file", t.files[0]);
      await api(`/api/admin/${admin.slug}/assets/${t.dataset.asset}`, { method: "PUT", body: form });
      toast("Logo gespeichert");
      await afterAssetChange();
      return;
    }
    if (t.dataset.keywordActive) {
      const k = admin.keywords.keywords.find((x) => x.code === t.dataset.keywordActive);
      admin.keywords = { ...(await apiJson(`/api/admin/${admin.slug}/keywords/${encodeURIComponent(k.code)}`, "PUT",
        { name: k.name, terms: k.terms, active: t.checked })), slug: admin.slug };
      await keywordsChanged(t.checked ? "Stichwort aktiviert" : "Stichwort deaktiviert");
      return;
    }
    if (t.dataset.keywordFile !== undefined) {
      admin.importFile = t.files[0];
      const form = new FormData();
      form.append("file", admin.importFile);
      admin.importPreview = await api(`/api/admin/${admin.slug}/keywords/import?mode=preview`, { method: "POST", body: form });
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
    if (t.dataset.tenantVg) {
      admin.superOverview = await apiJson(`/api/super/tenants/${t.dataset.tenantVg}`, "PUT", { vg: t.value });
      await superChanged("VG geändert");
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
