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
  ["vehicles", "Fahrzeuge", false, false, "vg", "vg.fees"], ["fees", "Gebührenordnung", false, false, "vg", "vg.fees"],
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

function adminSections() {
  const { overview } = admin;
  const mode = admin.vg ? "vg" : "tenant";
  const granted = adminGranted();
  return ADMIN_SECTIONS.filter(([, , , superOnly, scope, permission]) => {
    if (superOnly) return overview.superadmin;
    if (scope === "any") return overview.users || overview.superadmin;
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
  const sections = `<div class="segments" role="tablist">${adminSections().map(([key, label]) =>
    `<button type="button" data-admin-section="${key}" class="${key === admin.section ? "active" : ""}">${label}</button>`).join("")}</div>`;
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

const adminField = (label, input, span = "", help = "") =>
  `<label class="field ${span}"><span>${label}${help ? helpButton(help) : ""}</span>${input}</label>`;
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

// ------------------------------------------------------------ Wehr: Name, Farben, Logos
const hexToRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const rgbToHex = (rgb) => "#" + rgb.map((c) => Math.max(0, Math.min(255, Math.round(c || 0))).toString(16).padStart(2, "0")).join("").toUpperCase();
const isHex = (value) => /^#[0-9A-Fa-f]{6}$/.test(value);

function colorField(key, label, hint) {
  const value = admin.settings.colors[key] || "";
  const rgb = value ? hexToRgb(value) : ["", "", ""];
  return `<div class="color-field">
    <span class="field-label">${label}</span>
    <div class="color-inputs">
      <input type="color" class="color-picker" data-color-picker="${key}" value="${value || "#808080"}" aria-label="${label} wählen">
      ${adminField("Hex", `<input type="text" data-color-hex="${key}" value="${esc(value)}" placeholder="#RRGGBB" maxlength="7" spellcheck="false">`, "color-hex")}
      ${["Rot", "Grün", "Blau"].map((name, i) =>
        adminField(name, `<input type="number" min="0" max="255" data-color-rgb="${key}" data-channel="${i}" value="${rgb[i]}">`, "color-channel")).join("")}
      <button type="button" class="btn btn-outline btn-small" data-admin-action="clear-color" data-key="${key}">${value ? "Zurücksetzen" : "Automatisch"}</button>
    </div>
    <p class="small muted">${hint}</p>
  </div>`;
}

function unitSection() {
  const s = admin.settings, assets = admin.overview.assets;
  const logos = Object.entries(assets).map(([name, label]) => {
    const url = s.assets[name];
    const fallback = name === "logo-light" ? "/static/img/app-icon-light.svg" : "/static/img/app-icon.svg";
    return `<div class="logo-slot ${name === "logo-light" ? "on-brand" : ""}">
      <div class="logo-preview"><img src="${esc(url || fallback)}" alt=""></div>
      <div><strong>${esc(label)}</strong><p class="small muted">${url ? "eigenes Bild" : "neutrales Signet"}</p>
        <label class="btn btn-light btn-small file-button">Bild wählen<input type="file" accept="image/png,image/jpeg,image/webp" data-asset="${name}" hidden></label>
        ${url ? `<button type="button" class="btn btn-outline btn-small" data-admin-action="delete-asset" data-name="${name}">Entfernen</button>` : ""}</div>
    </div>`;
  }).join("");
  // Farben und Logos zeigt die Seite nur, wenn oben genau diese Wehr gewählt ist (Gesamtansicht: neutral)
  const elsewhere = config.tenant?.slug !== admin.slug ? `<div class="message message-info">
      Oben ist ${config.vg ? "die Gesamtansicht der VG gewählt – sie ist immer neutral gestaltet" : "eine andere Wehr gewählt"}.
      Farben und Logos von ${esc(s.name)} erscheinen, wenn diese Wehr ausgewählt ist.
      <button type="button" class="btn btn-light btn-small" data-admin-action="select-tenant">${esc(s.name)} auswählen</button></div>` : "";
  return `${elsewhere}<div class="form-grid">${adminField("Name der Wehr", textInput("name", s.name, 'maxlength="80"'), "span-4")}</div>
    <h3 class="section-gap">Farben${helpButton("admin_colors")}</h3>
    <div class="admin-colors">
      <div>${colorField("brand", "Hauptfarbe", "Kopfzeile, Knöpfe, Überschriften und Diagramme. Weiße Schrift muss darauf lesbar sein.")}
        ${colorField("brand_dark", "Dunkle Farbe (optional)", "Hervorgehobene Kacheln und Verlauf der Kopfzeile. Leer = aus der Hauptfarbe abgeleitet.")}
        <div id="theme-problems"></div></div>
      ${themePreview()}
    </div>
    <h3 class="section-gap">Logos${helpButton("admin_logos")}</h3>
    <p class="small muted">PNG, JPEG oder WebP, höchstens 512 KB. Wird sofort gespeichert.</p>
    <div class="logo-slots">${logos}</div>
    ${saveButton()}`;
}

function themePreview() {
  return `<div class="theme-preview" id="theme-preview" aria-label="Vorschau der Farben">
    <div class="preview-bar"><span>${esc(admin.settings.name)}</span><b>Auswertung</b></div>
    <div class="preview-content">
      <div class="preview-kpi"><small>Einsätze</small><b>55</b></div>
      <div class="preview-chart"><span class="day" style="height:70%"></span><span class="night" style="height:45%"></span>
        <span class="day" style="height:90%"></span><span class="night" style="height:30%"></span><span class="day" style="height:55%"></span></div>
      <div class="preview-buttons"><span class="btn btn-primary btn-small">Bericht einlesen</span><span class="btn btn-light btn-small">Tabelle</span></div>
      <div class="preview-head">Tabellenkopf</div>
    </div>
  </div>`;
}

let themeTimer;
function scheduleThemeCheck() {
  clearTimeout(themeTimer);
  themeTimer = setTimeout(async () => {
    try {
      admin.check = await apiJson("/api/admin/theme-check", "POST", { colors: cleanColors() });
    } catch (e) {
      admin.check = { problems: [e.message], palette: null };
    }
    updateThemePreview();
  }, 250);
}

const cleanColors = () => Object.fromEntries(Object.entries(admin.settings.colors).filter(([, v]) => v));

function updateThemePreview() {
  const preview = $("#theme-preview");
  if (!preview) return;
  const palette = admin.check ? admin.check.palette : admin.settings.palette;
  for (const name of [...preview.style]) if (name.startsWith("--")) preview.style.removeProperty(name);
  for (const [name, value] of Object.entries(palette || {})) preview.style.setProperty(name, value);
  const problems = admin.check?.problems || [];
  $("#theme-problems").innerHTML = problems.length ? `<div class="message message-error">${problems.map(esc).join("<br>")}</div>` : "";
}

function setColor(key, hex, source) {
  admin.settings.colors[key] = hex;
  const valid = isHex(hex);
  if (source !== "picker" && valid) $(`[data-color-picker="${key}"]`).value = hex;
  if (source !== "hex") $(`[data-color-hex="${key}"]`).value = hex;
  if (source !== "rgb" && valid) {
    hexToRgb(hex).forEach((c, i) => { $(`[data-color-rgb="${key}"][data-channel="${i}"]`).value = c; });
  }
  if (valid || !hex) scheduleThemeCheck();
}

// ------------------------------------------------------------ Fahrzeuge
// Fahrzeug in Auswahllisten: Kurzname (Block), bei neuen Fahrzeugen bis zum Speichern der Funkrufname
const vehicleKey = (v) => v.call_sign || v.name;
const knownVehicle = (name) => admin.settings.known_vehicles.find((k) => k.name === name);

// Fahrzeugtyp vergleichen wie fees._type_key (ohne Leerzeichen und Satzzeichen)
const typeKey = (text) => (text || "").replace(/[\s\-./]/g, "").toLowerCase();

// Funkrufname, den ein anderer Eintrag schon hat (oder als Vorschlag für seinen alten Kurznamen)
function takenBy(v) {
  if (!v.name) return null;
  return admin.settings.fleet.find((x) => x !== v && (x.name === v.name || (!x.name && x.suggested_name === v.name)));
}

// Funkrufname mit Auflösung (Kennung, Standort, Fahrzeugart) und Block der Einsatzübersicht
function callSignCell(v, i) {
  const s = admin.settings;
  const known = knownVehicle(v.name);
  const other = takenBy(v);
  const block = v.call_sign ? `Block ${esc(v.call_sign)}` : "Block wird beim Speichern vergeben";
  const hint = other ? `<span class="missing-name">Steht schon in der Liste (${esc(other.call_sign || other.name)})${other.name ? "" : " – bitte dort eintragen"}</span>`
    : v.name ? [block, known && esc(known.description)].filter(Boolean).join(" · ")
    : v.call_sign ? `<span class="missing-name">Funkrufnamen wie im BKS-Bericht eintragen (bisher nur ${esc(v.call_sign)})</span>`
    : "Funkrufnamen auswählen oder eintragen";
  // Zur Auswahl nur Fahrzeuge, die noch nicht in der Liste stehen; der Vorschlag für diesen Eintrag zuerst
  const used = new Set(s.fleet.filter((x) => x !== v).flatMap((x) => [x.name, x.name ? "" : x.suggested_name]).filter(Boolean));
  const options = [...new Set([v.suggested_name, ...s.known_vehicles.map((k) => k.name)].filter((n) => n && !used.has(n)))];
  const placeholder = esc(v.suggested_name || "z. B. FL NR#.ABC 02/45-01");
  return `${textInput(`fleet.${i}.name`, v.name, `list="vehicles-${i}" placeholder="${placeholder}" spellcheck="false" class="wide"`)}
    <datalist id="vehicles-${i}">${options.map((n) => `<option value="${esc(n)}">${esc(knownVehicle(n)?.description || "")}</option>`).join("")}</datalist>
    <div class="small muted">${hint}</div>`;
}

// Fahrzeugtyp: Auswahl aus den Typen der Kennzahl (Funkrufnamenverzeichnis) und der Gebührenordnung
function vehicleTypeCell(v, i) {
  const s = admin.settings;
  const types = knownVehicle(v.name)?.types || v.types || [];
  const fee = new Set(s.fee_types.map(typeKey));
  const options = [...new Set([...types, ...s.fee_types])];
  let hint = "";
  if (!v.label && types.length > 1) hint = `laut Kennzahl: ${types.map(esc).join(" / ")}`;
  else if (v.label && s.fee_types.length && !fee.has(typeKey(v.label))) hint = '<span class="missing-name">nicht in der Gebührenordnung</span>';
  return `${textInput(`fleet.${i}.label`, v.label, `list="types-${i}" placeholder="${esc(types[0] || "z. B. HLF 20")}"`)}
    <datalist id="types-${i}">${options.map((t) => `<option value="${esc(t)}">${types.includes(t) ? "laut Funkrufname" : "Gebührenordnung"}</option>`).join("")}</datalist>
    ${hint ? `<div class="small muted">${hint}</div>` : ""}`;
}

function fleetSection() {
  const s = admin.settings;
  const others = (v) => s.fleet.filter((x) => vehicleKey(x) && x !== v);
  const rows = s.fleet.map((v, i) => `<tr>
    <td class="order"><button type="button" class="icon-button" data-admin-action="move-vehicle" data-index="${i}" data-step="-1" ${i ? "" : "disabled"} aria-label="nach oben">↑</button><button type="button" class="icon-button" data-admin-action="move-vehicle" data-index="${i}" data-step="1" ${i < s.fleet.length - 1 ? "" : "disabled"} aria-label="nach unten">↓</button></td>
    <td>${callSignCell(v, i)}</td>
    <td>${vehicleTypeCell(v, i)}</td>
    <td><input type="date" data-bind="fleet.${i}.in_service_from" value="${esc(v.in_service_from || "")}"></td>
    <td><input type="date" data-bind="fleet.${i}.in_service_until" value="${esc(v.in_service_until || "")}"></td>
    <td><select data-bind="fleet.${i}.replaced_by"><option value="">–</option>${others(v).map((x) =>
      `<option value="${esc(vehicleKey(x))}" ${vehicleKey(x) === v.replaced_by ? "selected" : ""}>${esc(x.call_sign || x.name)}</option>`).join("")}</select></td>
    <td class="center"><input type="checkbox" data-bind="fleet.${i}.in_plan_crew" ${v.in_plan_crew ? "checked" : ""} aria-label="zählt zur Gesamtstärke"></td>
    <td class="right">${v.incidents || ""}</td>
    <td><button type="button" class="icon-button" data-admin-action="remove-vehicle" data-index="${i}" aria-label="entfernen">✕</button></td>
  </tr>`).join("");
  const unused = Object.entries(s.unused_data);
  const substitutes = Object.entries(s.substitutes).map(([sub, block], i) => `<div class="inline-row">
    <input type="text" data-substitute="${i}" value="${esc(sub)}" list="known-vehicles" placeholder="z. B. FL NR#.ABC 01/23-01" spellcheck="false" class="wide" aria-label="Ersatzfahrzeug (Funkrufname)">
    <span>wird geführt im Block</span>
    <select data-substitute-block="${i}">${s.fleet.map((v) => `<option value="${esc(vehicleKey(v))}" ${vehicleKey(v) === block ? "selected" : ""}>${esc(v.call_sign || v.name)}</option>`).join("")}</select>
    <button type="button" class="icon-button" data-admin-action="remove-substitute" data-sub="${esc(sub)}" aria-label="entfernen">✕</button></div>`).join("");
  const datalist = `<datalist id="known-vehicles">${s.known_vehicles.map((k) =>
    `<option value="${esc(k.name)}">${esc(k.description)}</option>`).join("")}</datalist>`;
  const emptyRow = s.fleet.some((v) => !v.name && !v.call_sign);
  return `<p class="small muted">Reihenfolge wie in der Einsatzübersicht. Funkrufname genau wie im BKS-Bericht – zur Auswahl stehen die Fahrzeuge aus den bisher eingelesenen Berichten (<a href="${esc(s.call_sign_directory)}" target="_blank" rel="noopener">Funkrufnamenverzeichnis RLP</a>). Neue eigene Fahrzeuge aus BKS-Berichten werden beim Übernehmen automatisch hinten angefügt (im Dienst ab Einsatztag).${helpButton("admin_fleet")}</p>
    ${datalist}
    <div class="table-wrap"><table class="mini-table admin-table"><thead><tr><th></th><th>Funkrufname</th><th>Fahrzeugtyp</th><th>im Dienst ab</th><th>außer Dienst ab</th><th>ersetzt durch</th><th>Bedarfsplan</th><th class="right">Einsätze</th><th></th></tr></thead>
    <tbody>${rows}</tbody></table></div>
    <button type="button" class="btn btn-light btn-small section-gap" data-admin-action="add-vehicle" ${emptyRow ? 'disabled title="Erst den Funkrufnamen des neuen Fahrzeugs eintragen"' : ""}>Fahrzeug hinzufügen</button>
    ${unused.length ? `<div class="message message-info section-gap">Daten zu Fahrzeugen, die nicht (mehr) in der Liste stehen und daher nicht ausgewertet werden: ${unused.map(([cs, n]) => `${esc(cs)} (${n} Einsätze)`).join(", ")}.</div>` : ""}
    <h3 class="section-gap">Ersatzfahrzeuge</h3>
    <p class="small muted">Fährt ein Ersatzfahrzeug mit eigener Besatzung (Werkstatt), wird es im Block eines Stammfahrzeugs geführt.</p>
    ${substitutes}
    <button type="button" class="btn btn-light btn-small" data-admin-action="add-substitute" ${s.fleet.length ? "" : "disabled"}>Ersatzfahrzeug hinzufügen</button>
    ${saveButton()}`;
}

// ------------------------------------------------------------ Wehrleitung: Fahrzeuge der VG
// Auswahl der Wehr für ein Fahrzeug; data-* trägt, was das Backend zum Verschieben braucht
function vehicleTenantSelect(name, source = "", callSign = "") {
  const { tenants } = admin.vgVehicles;
  return `<select data-move-vehicle data-name="${esc(name)}" data-source="${esc(source)}" data-call-sign="${esc(callSign)}" aria-label="Wehr von ${esc(name)}">
    <option value="">${source ? "keiner Wehr (aus der Liste nehmen)" : "– keiner Wehr –"}</option>
    ${tenants.map((t) => `<option value="${esc(t.slug)}" ${t.slug === source ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select>`;
}

function vgVehiclesSection() {
  const { tenants, vehicles, unassigned, fee_types } = admin.vgVehicles;
  const fee = new Set(fee_types.map(typeKey));
  const typeCell = (label) => label ? `${esc(label)}${fee_types.length && !fee.has(typeKey(label)) ? ' <span class="missing-name">nicht in der Gebührenordnung</span>' : ""}`
    : '<span class="muted">–</span>';
  const assigned = tenants.map((t) => {
    const rows = vehicles.filter((v) => v.tenant === t.slug).map((v) => `<tr>
      <td><b>${esc(v.name || v.suggested_name || v.call_sign)}</b>${v.name ? "" : ' <span class="missing-name">Funkrufname noch nicht bestätigt</span>'}
        <div class="small muted">Block ${esc(v.call_sign)}${v.description ? ` · ${esc(v.description)}` : ""}</div></td>
      <td>${typeCell(v.label)}</td>
      <td class="right">${v.incidents || ""}</td>
      <td>${v.name || v.suggested_name ? vehicleTenantSelect(v.name || v.suggested_name, t.slug, v.call_sign)
        : '<span class="small muted">erst den Funkrufnamen bei der Wehr eintragen</span>'}</td>
      <td><button type="button" class="btn btn-light btn-small" data-admin-action="edit-fleet" data-tenant="${esc(t.slug)}">Bearbeiten</button></td>
    </tr>`).join("");
    return `<tr class="group-row"><th colspan="5">${esc(t.name)}</th></tr>${rows || '<tr><td colspan="5" class="muted">Noch keine Fahrzeuge.</td></tr>'}`;
  }).join("");
  const openRow = (v) => `<tr><td><b>${esc(v.name)}</b><div class="small muted">${esc(v.description)}</div></td>
    <td>${typeCell(v.label)}</td><td></td><td>${vehicleTenantSelect(v.name)}</td><td></td></tr>`;
  const own = unassigned.filter((v) => v.vg), others = unassigned.filter((v) => !v.vg);
  return `<p class="small muted">Alle Fahrzeuge der VG auf einen Blick. Über „Wehr“ gehört ein Fahrzeug zu einer Wehr und wird in deren Berichten zugeordnet. Wechselt es die Wehr, bleiben Einsätze mit seinen Daten bei der bisherigen Wehr; dort wird es ab dann nicht mehr zugeordnet. Fahrzeugtyp und Dienstzeitraum pflegt die Wehr unter „Fahrzeuge“.${helpButton("admin_vg_vehicles")}</p>
    <div class="table-wrap"><table class="mini-table admin-table"><thead><tr><th>Funkrufname</th><th>Fahrzeugtyp</th><th class="right">Einsätze</th><th>Wehr</th><th></th></tr></thead>
    <tbody>${assigned}
      <tr class="group-row"><th colspan="5">Noch keiner Wehr zugeordnet</th></tr>
      ${own.map(openRow).join("") || '<tr><td colspan="5" class="muted">Alle Fahrzeuge der VG aus den Berichten sind zugeordnet.</td></tr>'}
    </tbody></table></div>
    ${others.length ? `<details class="section-gap"><summary>Weitere Fahrzeuge aus Berichten (${others.length}, z. B. Rettungsdienst, Fahrzeuge des Landes, Nachbarwehren)</summary>
      <div class="table-wrap"><table class="mini-table admin-table"><tbody>${others.map(openRow).join("")}</tbody></table></div></details>` : ""}
    <div class="inline-row section-gap">
      <input type="text" id="vg-vehicle-name" list="vg-vehicle-names" placeholder="Funkrufname, z. B. FL NR#.ABC 01/10-01" spellcheck="false" class="wide" aria-label="Funkrufname">
      <datalist id="vg-vehicle-names">${unassigned.map((v) => `<option value="${esc(v.name)}">${esc(v.description)}</option>`).join("")}</datalist>
      <select id="vg-vehicle-tenant" aria-label="Wehr">${tenants.map((t) => `<option value="${esc(t.slug)}">${esc(t.name)}</option>`).join("")}</select>
      <button type="button" class="btn btn-light btn-small" data-admin-action="assign-vehicle">Fahrzeug zuordnen</button>
    </div>`;
}

// Fahrzeug einer Wehr zuordnen bzw. verschieben (Auswahl in der Übersicht der Wehrleitung)
async function moveVehicle(select) {
  const { name, source, callSign } = select.dataset;
  const tenants = admin.vgVehicles.tenants, target = select.value;
  const vehicle = admin.vgVehicles.vehicles.find((v) => v.tenant === source && v.call_sign === callSign);
  const from = tenants.find((t) => t.slug === source)?.name, to = tenants.find((t) => t.slug === target)?.name;
  if (vehicle?.incidents && !confirm(`${name} hat Daten in ${vehicle.incidents} Einsätzen von ${from}. Sie bleiben dort, ab jetzt wird ${name} aber ${to ? `${to} zugeordnet` : "keiner Wehr zugeordnet"}. Fortfahren?`)) {
    select.value = source;
    return;
  }
  if (admin.settings && [source, target].includes(admin.settings.slug) && !confirmDiscard()) { select.value = source; return; }
  admin.vgVehicles = { vg: admin.vg, ...(await apiJson(`/api/admin/vgs/${encodeURIComponent(admin.vg)}/vehicles/move`, "POST",
    { name, source: source || null, call_sign: callSign || null, target: target || null })) };
  admin.settings = admin.savedSettings = null;            // Fahrzeuglisten der Wehren neu laden
  if ([source, target].includes(config.tenant?.slug)) await refreshCurrentTenant();
  toast(to ? `${name} gehört jetzt zu ${to}` : `${name} ist keiner Wehr mehr zugeordnet`);
  renderAdmin();
}

// ------------------------------------------------------------ BKS-Kennung
// Zuordnung einer Testzeile: zuerst über den Funkrufnamen der Fahrzeugliste, sonst über die Präfixe
function fleetMatch(v) {
  const listed = admin.settings.fleet.find((x) => x.name && x.name === v.name);
  if (listed) return `Block ${esc(listed.call_sign || listed.name)} · <b>Fahrzeug der Liste</b>`;
  if (!v.call_sign) return "nicht der Einheit zugeordnet";
  return `Funkruf ${esc(v.call_sign)}${v.own ? " · <b>eigenes Fahrzeug</b>" : " · Fahrzeug der Einheit"}`;
}

function bksSection() {
  const s = admin.settings;
  const result = admin.parseResult;
  const found = result ? (result.length ? `<ul class="plain-list">${result.map((v) =>
    `<li><b>${esc(v.name)}</b> → ${fleetMatch(v)}</li>`).join("")}</ul>`
    : `<p class="message message-error">Keine Fahrzeugzeile erkannt.</p>`) : "";
  return `<p class="small muted">So erkennt die App im Einsatzbericht des BKS-Portals, welche Fahrzeuge zur Wehr gehören und von welcher Einheit ein Bericht stammt.${helpButton("admin_bks")}</p>
    <div class="form-grid">
      ${adminField("Einheiten-Präfix", textInput("unit_prefix", s.unit_prefix, 'placeholder="FL NR#.ABC " spellcheck="false"'), "span-2")}
      ${adminField("Eigener Präfix", textInput("own_prefix", s.own_prefix, 'placeholder="02/" maxlength="3"'))}
      ${adminField("Einheit im Bericht", textInput("unit_marker", s.unit_marker, 'placeholder="FW NR#.ABC 02" spellcheck="false"'), "span-2")}
      ${adminField("FEZ-Kennung", textInput("control_center", s.control_center, 'spellcheck="false"'))}
      ${adminField("Einsatznummern", `<select data-bind="numbering">
        <option value="bks" ${s.numbering === "bks" ? "selected" : ""}>aus dem Bericht (fehlt sie: nächste freie)</option>
        <option value="by_date" ${s.numbering === "by_date" ? "selected" : ""}>nach Datum durchnummerieren</option></select>`, "span-3")}
    </div>
    <p class="small muted">Nach Datum: Die App nummeriert alle Einsätze eines Jahres nach dem Beginn; ein später eingelesener Einsatz (z. B. eine selbst angelegte Brandsicherheitswache) rückt an seine Stelle, die folgenden Nummern verschieben sich. Beim Speichern werden alle Jahre neu nummeriert.</p>
    <p class="small muted">Leerzeichen am Ende des Einheiten-Präfixes gehören dazu.</p>
    <h3 class="section-gap">Testen</h3>
    <label class="field"><span>Fahrzeugzeile aus einem Bericht</span>
      <textarea rows="3" id="parse-line" spellcheck="false" placeholder="FL NR#.ABC 02/45-01 0 / 1 / 5 / 6 / 2 12.03.25 10:09:41 …"></textarea></label>
    <button type="button" class="btn btn-light btn-small section-gap" data-admin-action="parse-test">Erkennung prüfen</button>
    ${found}
    ${saveButton()}`;
}

// ------------------------------------------------------------ Orte und Bedarfsplan
function placesSection() {
  const s = admin.settings;
  const rows = s.places.map((p, i) => `<tr>
    <td>${textInput(`places.${i}.name`, p.name, 'placeholder="Musterstadt"')}</td>
    <td>${textInput(`places.${i}.prefix`, p.prefix, 'placeholder="muster" class="narrow"')}</td>
    <td class="center"><input type="checkbox" data-plan-place="${i}" ${s.plan_places.includes(p.name) ? "checked" : ""} aria-label="Bedarfsplan"></td>
    <td><button type="button" class="icon-button" data-admin-action="remove-place" data-index="${i}" aria-label="entfernen">✕</button></td>
  </tr>`).join("");
  const options = (values, current) => values.map((v) => `<option ${v === current ? "selected" : ""}>${v}</option>`).join("");
  return `<p class="small muted">Das Einsatzgebiet wird über den Anfang des Ortsnamens zugeordnet. Nur Orte mit Haken zählen zum Ausrückebereich des Feuerwehrbedarfsplans.${helpButton("admin_places")}</p>
    <div class="table-wrap"><table class="mini-table admin-table"><thead><tr><th>Ort</th><th>Namensanfang</th><th>Bedarfsplan</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
    <button type="button" class="btn btn-light btn-small section-gap" data-admin-action="add-place">Ort hinzufügen</button>
    <h3 class="section-gap">Feuerwehrbedarfsplan</h3>
    <div class="form-grid">
      ${adminField("ab Alarmstufe", `<select data-bind="plan_min_level" data-number>${options([1, 2, 3, 4], s.plan_min_level)}</select>`)}
      ${adminField("Zeitgrenzen (Min.)", `<input type="text" data-limits value="${esc(s.response_limits.join(", "))}" placeholder="8, 10">`)}
      ${adminField("Standard", `<select data-bind="default_limit" data-number>${options(s.response_limits, s.default_limit)}</select>`)}
      ${adminField("Zweite Grenze (Min.)", `<input type="number" min="1" max="120" data-bind="second_limit" value="${s.second_limit}">`)}
      ${adminField("Tag ab (Uhr)", `<input type="number" min="0" max="23" data-bind="day_hours.0" value="${s.day_hours[0]}">`)}
      ${adminField("Tag bis (Uhr)", `<input type="number" min="1" max="24" data-bind="day_hours.1" value="${s.day_hours[1]}">`)}
    </div>
    ${adminGranted().includes("plan.release") ? `<label class="toggle section-gap"><input type="checkbox" data-bind="response_plan_public" ${s.response_plan_public ? "checked" : ""}>
      Bedarfsplan für alle Rollen freigeben <span class="muted">(sonst nur mit dem Recht „Bedarfsplan ohne Freigabe sehen“)</span></label>`
      : `<p class="small muted section-gap">Bedarfsplan ${s.response_plan_public ? "ist für alle Rollen freigegeben" : "ist nicht freigegeben"} – freigeben darf, wer das Recht „Bedarfsplan freigeben“ hat.</p>`}
    ${saveButton()}`;
}

// ------------------------------------------------------------ Stichworte
function keywordsSection() {
  const k = admin.keywords;
  const query = fold(admin.keywordQuery);
  const list = k.keywords.filter((x) => !query || fold(`${x.code} ${x.name} ${x.terms}`).includes(query));
  const edit = admin.keywordEdit || { code: "", name: "", terms: "" };
  const preview = admin.importPreview;
  return `<div class="admin-status">
      <span class="tenant-badge">${k.custom ? "eigener Katalog" : "Vorlage (AAO)"}</span>
      <span class="small muted">${k.keywords.length} Stichworte${k.custom && k.template_missing ? ` · ${k.template_missing} der Vorlage fehlen` : ""}</span>
      <span class="toolbar-right">
        ${k.custom && k.template_missing ? `<button type="button" class="btn btn-light btn-small" data-admin-action="keywords-template">Fehlende aus der Vorlage ergänzen</button>` : ""}
        ${k.custom ? `<button type="button" class="btn btn-outline btn-small" data-admin-action="keywords-reset">Zurück zur Vorlage</button>` : ""}
      </span>
    </div>
    <h3 class="section-gap">${edit.code && k.keywords.some((x) => x.code === edit.code) ? "Stichwort ändern" : "Stichwort hinzufügen"}${helpButton("admin_keywords")}</h3>
    <div class="form-grid">
      ${adminField("Stichwort", `<input type="text" id="keyword-code" value="${esc(edit.code)}" placeholder="B2.07" maxlength="5">`)}
      ${adminField("Bezeichnung", `<input type="text" id="keyword-name" value="${esc(edit.name)}" maxlength="120">`, "span-2")}
      ${adminField("Suchbegriffe (Meldebilder)", `<input type="text" id="keyword-terms" value="${esc(edit.terms)}" placeholder="durch Komma getrennt">`, "span-3")}
    </div>
    <div class="admin-actions left"><button type="button" class="btn btn-primary btn-small" data-admin-action="keyword-save">Stichwort speichern</button>
      ${admin.keywordEdit ? `<button type="button" class="btn btn-outline btn-small" data-admin-action="keyword-cancel">Abbrechen</button>` : ""}</div>
    <h3 class="section-gap">Katalog</h3>
    <input type="search" class="search" data-keyword-search value="${esc(admin.keywordQuery)}" placeholder="Suchen: Stichwort, Bezeichnung, Meldebild …">
    <div class="table-wrap keyword-table"><table class="mini-table admin-table"><thead><tr><th>Stichwort</th><th>Bezeichnung</th><th>Suchbegriffe</th><th>aktiv</th><th></th></tr></thead><tbody>
      ${list.map((x) => `<tr class="${x.active ? "" : "inactive"}"><td><b>${esc(x.code)}</b></td><td>${esc(x.name)}</td><td class="terms" title="${esc(x.terms)}">${esc(x.terms)}</td>
        <td class="center"><input type="checkbox" data-keyword-active="${esc(x.code)}" ${x.active ? "checked" : ""} aria-label="aktiv"></td>
        <td class="nowrap"><button type="button" class="icon-button" data-admin-action="keyword-edit" data-code="${esc(x.code)}" aria-label="bearbeiten">✎</button><button type="button" class="icon-button" data-admin-action="keyword-delete" data-code="${esc(x.code)}" aria-label="löschen">✕</button></td></tr>`).join("")}
    </tbody></table></div>
    <h3 class="section-gap">Import aus Datei</h3>
    <p class="small muted">CSV (Semikolon oder Komma) oder Excel mit den Spalten Stichwort, Bezeichnung, Suchbegriffe; eine Kopfzeile ist erlaubt.</p>
    <label class="btn btn-light btn-small file-button">Datei wählen<input type="file" accept=".csv,.xlsx,text/csv" data-keyword-file hidden></label>
    ${preview ? `<div class="message message-info section-gap">${esc(admin.importFile.name)}: ${preview.new.length} neu, ${preview.changed.length} geändert, ${preview.unchanged} unverändert, ${preview.missing.length} nicht in der Datei
      <div class="admin-actions left"><button type="button" class="btn btn-primary btn-small" data-admin-action="keywords-import" data-mode="merge">Ergänzen und ändern</button>
      <button type="button" class="btn btn-outline btn-small" data-admin-action="keywords-import" data-mode="replace">Katalog ersetzen</button></div></div>` : ""}`;
}

// ------------------------------------------------------------ Benutzer
function setMemberships(data) {
  admin.memberships = data.memberships;
  admin.userScopes = data.scopes;
}

function usersSection() {
  const scopes = admin.userScopes;
  const rows = admin.memberships.map((m) => `<tr>
    <td>${esc(m.email)}</td><td>${esc(m.name)}${m.scope === "vg" ? " <span class='small muted'>(VG)</span>" : ""}</td><td>${esc(m.label)}</td>
    <td class="small muted">${m.last_login ? formatDate(m.last_login) : "noch nie"}</td>
    <td class="nowrap"><button type="button" class="btn btn-light btn-small" data-admin-action="effective" data-email="${esc(m.email)}">Rechte</button>
      ${m.editable ? `<button type="button" class="icon-button" data-admin-action="revoke" data-email="${esc(m.email)}" data-scope="${m.scope}" data-slug="${esc(m.slug)}" data-key="${esc(m.role)}" aria-label="Rolle entziehen" data-tip="Rolle entziehen">✕</button>` : ""}</td></tr>`).join("");
  const form = scopes.length ? `<div class="form-grid">
      ${adminField("E-Mail-Adresse", `<input type="email" id="grant-email" autocomplete="off">`, "span-2")}
      ${adminField("Bereich", `<select id="grant-scope">${scopes.map((x) => `<option value="${esc(x.key)}">${esc(x.label)}</option>`).join("")}</select>`, "span-2")}
      ${adminField("Rolle", `<select id="grant-role"></select>`)}
      <div class="field"><span>&nbsp;</span><button type="button" class="btn btn-primary" data-admin-action="grant">Zuordnen</button></div>
    </div>` : `<p class="small muted">Rollen vergeben darfst du nicht – hier stehen nur die Zuordnungen.</p>`;
  return `<p class="small muted">Wer eine Zuordnung hat, kann sich mit seiner E-Mail-Adresse anmelden. Eine Person kann mehrere Rollen haben;
    ihre Rechte addieren sich. Eigene Zuordnungen ändert jemand anderes.${helpButton("admin_users")}</p>
    <div class="section-gap">${form}</div>
    <div class="table-wrap section-gap"><table class="mini-table admin-table"><thead><tr><th>E-Mail</th><th>Bereich</th><th>Rolle</th><th>zuletzt angemeldet</th><th></th></tr></thead>
    <tbody>${rows || `<tr><td colspan="5" class="muted">Noch keine Zuordnungen.</td></tr>`}</tbody></table></div>
    ${admin.effective ? effectivePanel() : ""}
    <h3 class="section-gap">Protokoll${helpButton("admin_role_events")}</h3>
    ${admin.events ? eventsTable() : `<button type="button" class="btn btn-light btn-small" data-admin-action="events">Protokoll anzeigen</button>`}`;
}

function effectivePanel() {
  const e = admin.effective;
  const areas = e.areas.map((a) => `<h4 class="section-gap">${esc(a.name)}</h4>
    <div class="table-wrap"><table class="mini-table admin-table"><thead><tr><th>Recht</th><th>über</th></tr></thead><tbody>
    ${a.permissions.map((p) => `<tr><td>${esc(p.label)}${helpButton(permissionHelpKey(p.key))}</td><td class="small muted">${p.from.map(esc).join(", ")}</td></tr>`).join("")}
    </tbody></table></div>`).join("");
  return `<div class="message message-info section-gap"><b>Rechte von ${esc(e.email)}</b>${e.superadmin ? " – Superadmin: darf alles" : ""}
    <button type="button" class="icon-button" data-admin-action="effective-close" aria-label="schließen">✕</button>
    ${areas || `<p class="small muted">In deinen Bereichen keine Rechte.</p>`}</div>`;
}

function eventsTable() {
  return `<div class="table-wrap keyword-table"><table class="mini-table admin-table"><thead><tr><th>Zeit</th><th>Wer</th><th>Was</th><th></th></tr></thead><tbody>
    ${admin.events.map((x) => `<tr><td class="small nowrap">${formatDate(x.at)} ${esc(x.at.slice(11, 16))}</td><td class="small">${esc(x.email || "")}</td><td>${esc(x.action)}</td><td class="small muted">${esc(x.detail)}</td></tr>`).join("")
      || `<tr><td colspan="4" class="muted">Noch keine Einträge.</td></tr>`}</tbody></table></div>`;
}

// Rollen passend zum gewählten Bereich (aus /api/admin/memberships: nur, was der Benutzer dort vergeben darf)
function filterRoleOptions() {
  const select = $("#grant-role");
  const scope = admin.userScopes?.find((x) => x.key === $("#grant-scope")?.value);
  if (!select || !scope) return;
  select.innerHTML = scope.roles.map((r) => `<option value="${esc(r.key)}">${esc(r.label)}</option>`).join("");
}

// ------------------------------------------------------------ Rollen
const permissionHelpKey = (key) => `perm_${key.replace(".", "_")}`;
const roleById = (id) => admin.roles.roles.find((r) => r.id === id);

function roleOrigin(r) {
  if (r.system) return "System";
  if (!r.vg) return "alle VGs";
  return admin.roles.vgs.find((v) => v.slug === r.vg)?.name || r.vg;
}

function rolesSection() {
  const { roles, permissions, vgs, superadmin } = admin.roles;
  const canCreate = superadmin || vgs.some((v) => v.manage);
  const head = roles.map((r) => `<th class="center role-head">
    <button type="button" class="link-button" data-admin-action="role-open" data-id="${r.id}">${esc(r.label)}</button>
    <span class="small muted">${admin.roles.scopes[r.scope]} · ${esc(roleOrigin(r))}</span></th>`).join("");
  let group = "";
  const body = permissions.map((p) => {
    const groupRow = p.group !== group ? `<tr class="group-row"><th colspan="${roles.length + 1}">${esc(group = p.group)}</th></tr>` : "";
    const cells = roles.map((r) => {
      if (!p.scopes.includes(r.scope)) return `<td class="center muted" data-tip="Für Rollen dieses Bereichs nicht vorgesehen">·</td>`;
      if (r.permissions.includes(p.key)) return `<td class="center" data-tip="eigenes Recht">●</td>`;
      if (r.effective.includes(p.key)) return `<td class="center muted" data-tip="geerbt von ${esc(roleById(r.parent)?.label || "")}">○</td>`;
      return "<td></td>";
    }).join("");
    return `${groupRow}<tr><td>${esc(p.label)}${helpButton(permissionHelpKey(p.key))}</td>${cells}</tr>`;
  }).join("");
  const users = `<tr class="group-row"><th colspan="${roles.length + 1}">Zuordnungen</th></tr>
    <tr><td>Personen mit dieser Rolle</td>${roles.map((r) => `<td class="center">${r.members}</td>`).join("")}</tr>`;
  return `<p class="small muted">● eigenes Recht, ○ geerbt. Rollen eines Bereichs „VG“ gelten in allen Wehren der VG.
    Rechte, Vererbung und wer eine Rolle vergeben darf, stehen im Editor (Klick auf den Namen).${helpButton("admin_roles")}</p>
    ${admin.roleDraft ? roleEditor() : ""}
    ${canCreate && !admin.roleDraft ? `<div class="admin-actions left"><button type="button" class="btn btn-primary btn-small" data-admin-action="role-new">Neue Rolle</button></div>` : ""}
    <div class="table-wrap section-gap"><table class="mini-table admin-table role-matrix"><thead><tr><th>Recht</th>${head}</tr></thead>
    <tbody>${body}${users}</tbody></table></div>`;
}

// Rollen, die für den Entwurf in Frage kommen (gelten in seiner VG)
const draftVisible = (d) => admin.roles.roles.filter((r) => r.id !== d.id && (r.vg === null || r.vg === d.vg));

function draftInherited(d) {
  const parent = d.parent ? roleById(d.parent) : null;
  return parent ? parent.effective : [];
}

function roleEditor() {
  const d = admin.roleDraft;
  const { permissions, vgs, superadmin } = admin.roles;
  const readOnly = d.id !== null && !d.editable;
  const disabled = readOnly ? "disabled" : "";
  const inherited = draftInherited(d);
  const effective = new Set([...inherited, ...d.permissions]);
  const others = draftVisible(d);
  const vgOptions = [...(superadmin ? [{ slug: "", name: "alle VGs" }] : []), ...vgs.filter((v) => superadmin || v.manage)];
  const scopeField = d.id === null
    ? adminField("Bereich", `<select data-role="scope">${Object.entries(admin.roles.scopes).map(([k, l]) => `<option value="${k}" ${k === d.scope ? "selected" : ""}>${l}</option>`).join("")}</select>`)
    : adminField("Bereich", `<input type="text" value="${esc(admin.roles.scopes[d.scope])}" disabled>`);
  const vgField = d.id === null
    ? adminField("Gilt in", `<select data-role="vg">${vgOptions.map((v) => `<option value="${esc(v.slug)}" ${v.slug === (d.vg || "") ? "selected" : ""}>${esc(v.name)}</option>`).join("")}</select>`)
    : adminField("Gilt in", `<input type="text" value="${esc(roleOrigin(d))}" disabled>`);
  const parents = others.filter((r) => r.scope === d.scope);
  let group = "";
  const checks = permissions.map((p) => {
    const heading = p.group !== group ? `<div class="check-group">${esc(group = p.group)}</div>` : "";
    const wrongScope = !p.scopes.includes(d.scope);
    const fromParent = inherited.includes(p.key);
    const checked = fromParent || d.permissions.includes(p.key);
    const note = wrongScope ? `nur für Rollen ${p.scopes.map((x) => admin.roles.scopes[x] === "VG" ? "der VG" : "einer Wehr").join(" oder ")}`
      : fromParent ? "geerbt" : p.requires.length ? `setzt voraus: ${p.requires.map((k) => permissions.find((x) => x.key === k).label).join(", ")}` : "";
    return `${heading}<label class="check ${wrongScope ? "muted" : ""}"><input type="checkbox" data-role-permission="${p.key}"
      ${checked ? "checked" : ""} ${wrongScope || fromParent || readOnly ? "disabled" : ""}> ${esc(p.label)}${helpButton(permissionHelpKey(p.key))}
      ${note ? `<span class="small muted">${esc(note)}</span>` : ""}</label>`;
  }).join("");
  const granters = others.filter((r) => r.effective.includes("users.grant"));
  const grantable = others.filter((r) => d.vg !== null || r.vg === null);
  const roleChecks = (list, field) => list.map((r) => `<label class="check"><input type="checkbox" data-role-${field}="${r.id}"
    ${d[field].includes(r.id) ? "checked" : ""} ${disabled}> ${esc(r.label)} <span class="small muted">${admin.roles.scopes[r.scope]}</span></label>`).join("")
    || `<span class="small muted">keine</span>`;
  return `<div class="role-editor section-gap">
    <h3>${d.id === null ? "Neue Rolle" : esc(d.label)}${helpButton("admin_role_editor")}
      ${readOnly ? `<span class="tenant-badge">nur ansehen</span>` : ""}</h3>
    <div class="form-grid">
      ${adminField("Bezeichnung", `<input type="text" data-role="label" value="${esc(d.label)}" maxlength="60" ${disabled}>`, "span-2")}
      ${scopeField}${vgField}
      ${adminField("Erbt von", `<select data-role="parent" ${disabled}><option value="">–</option>${parents.map((r) =>
        `<option value="${r.id}" ${r.id === d.parent ? "selected" : ""}>${esc(r.label)} (${esc(roleOrigin(r))})</option>`).join("")}</select>`, "span-2")}
      ${adminField("Beschreibung", `<input type="text" data-role="description" value="${esc(d.description)}" maxlength="300" ${disabled}>`, "span-4")}
    </div>
    <h4 class="section-gap">Rechte</h4>
    <div class="check-grid">${checks}</div>
    <h4 class="section-gap">Verteilung${helpButton("admin_role_grants")}</h4>
    <div class="check-columns">
      <div><div class="check-group">Diese Rolle dürfen vergeben</div>${roleChecks(granters, "granted_by")}</div>
      ${effective.has("users.grant") ? `<div><div class="check-group">Inhaber dieser Rolle vergeben</div>${roleChecks(grantable, "grants")}</div>` : ""}
    </div>
    <div class="admin-actions">
      ${d.id !== null && d.deletable ? `<button type="button" class="btn btn-outline" data-admin-action="role-delete">Löschen</button>` : ""}
      ${d.id !== null && (superadmin || vgs.some((v) => v.manage)) ? `<button type="button" class="btn btn-light" data-admin-action="role-copy">Als Kopie anlegen</button>` : ""}
      <button type="button" class="btn btn-outline" data-admin-action="role-cancel">${readOnly ? "Schließen" : "Abbrechen"}</button>
      ${readOnly ? "" : `<button type="button" class="btn btn-primary" data-admin-action="role-save">Speichern</button>`}
    </div></div>`;
}

function roleDraftFrom(r) {
  return { id: r.id, label: r.label, description: r.description, scope: r.scope, vg: r.vg, parent: r.parent,
    permissions: [...r.permissions], granted_by: [...r.granted_by], grants: [...r.grants],
    editable: r.editable, deletable: r.deletable, system: r.system };
}

function newRoleDraft(base = null) {
  const { vgs, superadmin } = admin.roles;
  const vg = base ? (base.vg ?? (superadmin ? null : vgs.find((v) => v.manage)?.slug))
    : (admin.vg && vgs.some((v) => v.slug === admin.vg && v.manage) ? admin.vg : vgs.find((v) => v.manage)?.slug ?? null);
  const draft = { id: null, label: base ? `${base.label} (Kopie)` : "", description: base?.description || "",
    scope: base?.scope || "tenant", vg, parent: base?.parent ?? null, permissions: [...(base?.permissions || [])],
    granted_by: [], grants: [], editable: true, deletable: false, system: false };
  // Standard der Verteilung: wer Rollen der VG pflegt, darf die neue Rolle auch vergeben
  draft.granted_by = draftVisible(draft).filter((r) => r.effective.includes("roles.manage")).map((r) => r.id);
  return draft;
}

// Recht an- oder abwählen: mit allen Voraussetzungen bzw. allem, was darauf aufbaut
function toggleRolePermission(key, on) {
  const d = admin.roleDraft;
  const { permissions } = admin.roles;
  const set = new Set(d.permissions);
  if (on) {
    const todo = [key];
    while (todo.length) {
      const k = todo.pop();
      if (set.has(k)) continue;
      set.add(k);
      todo.push(...permissions.find((p) => p.key === k).requires);
    }
  } else {
    const todo = [key];
    while (todo.length) {
      const k = todo.pop();
      set.delete(k);
      todo.push(...permissions.filter((p) => p.requires.includes(k) && set.has(p.key)).map((p) => p.key));
    }
  }
  d.permissions = permissions.filter((p) => set.has(p.key) && p.scopes.includes(d.scope)).map((p) => p.key);
}

function rolePayload() {
  const d = admin.roleDraft;
  return { label: d.label, description: d.description, scope: d.scope, vg: d.vg || null, parent: d.parent,
    permissions: d.permissions, granted_by: d.granted_by, grants: d.grants };
}

// ------------------------------------------------------------ Superadmin: Wehren und VGs
function superSection() {
  const { vgs, tenants } = admin.superOverview;
  const vgOptions = (current) => vgs.map((v) => `<option value="${esc(v.slug)}" ${v.slug === current ? "selected" : ""}>${esc(v.name)}</option>`).join("");
  return `<h3>Verbandsgemeinden</h3>
    <div class="table-wrap"><table class="mini-table admin-table"><thead><tr><th>Kurzname</th><th>Name</th><th>AVV</th><th></th></tr></thead><tbody>
      ${vgs.map((v) => `<tr><td>${esc(v.slug)}</td><td><input type="text" data-vg-name="${esc(v.slug)}" value="${esc(v.name)}"></td>
        <td><a href="#dpa" class="tenant-badge dpa-${v.dpa}">${{ pending: "ausstehend", draft: "ausgefüllt", signed: "liegt vor", revoked: "zurückgenommen", not_required: "nicht erforderlich" }[v.dpa]}</a></td>
        <td><button type="button" class="btn btn-outline btn-small" data-admin-action="rename-vg" data-slug="${esc(v.slug)}">Umbenennen</button></td></tr>`).join("")}
    </tbody></table></div>
    <div class="form-grid section-gap">
      ${adminField("Kurzname", `<input type="text" id="vg-slug" placeholder="vg-musterstadt" maxlength="40">`)}
      ${adminField("Name", `<input type="text" id="vg-name" placeholder="VG Musterstadt">`, "span-3")}
      <div class="field"><span>&nbsp;</span><button type="button" class="btn btn-light" data-admin-action="create-vg">VG anlegen</button></div>
    </div>
    <h3 class="section-gap">Wehren</h3>
    <div class="table-wrap"><table class="mini-table admin-table"><thead><tr><th>Kurzname</th><th>Name</th><th>VG</th><th class="right">Einsätze</th><th>aktiv</th><th></th></tr></thead><tbody>
      ${tenants.map((t) => `<tr class="${t.active ? "" : "inactive"}"><td>${esc(t.slug)}</td><td>${esc(t.name)}</td>
        <td><select data-tenant-vg="${esc(t.slug)}">${vgOptions(t.vg)}</select></td><td class="right">${t.incidents}</td>
        <td class="center"><input type="checkbox" data-tenant-active="${esc(t.slug)}" ${t.active ? "checked" : ""} aria-label="aktiv"></td>
        <td><button type="button" class="btn btn-outline btn-small" data-admin-action="delete-tenant" data-slug="${esc(t.slug)}">Entfernen</button></td></tr>`).join("")}
    </tbody></table></div>
    <div class="form-grid section-gap">
      ${adminField("Kurzname", `<input type="text" id="tenant-slug" placeholder="musterstadt" maxlength="40">`)}
      ${adminField("Name", `<input type="text" id="tenant-name" placeholder="Feuerwehr Musterstadt">`, "span-2")}
      ${adminField("VG", `<select id="tenant-vg">${vgOptions()}</select>`)}
      ${adminField("Erster Wehrführer (E-Mail, optional)", `<input type="email" id="tenant-email">`, "span-2")}
    </div>
    <div class="admin-actions left"><button type="button" class="btn btn-primary" data-admin-action="create-tenant" ${vgs.length ? "" : "disabled"}>Wehr anlegen</button></div>
    <p class="small muted">Neue VGs starten mit „AVV ausstehend“: Ihre Wehren sind gesperrt, bis der Vertrag unter „Auftragsverarbeitung“ bestätigt ist.
    Kurznamen: Kleinbuchstaben, Ziffern und Bindestrich; sie lassen sich später nicht ändern. Entfernte Wehren werden nicht gelöscht, sondern im Datenordner unter <code>deleted/</code> abgelegt.</p>`;
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
      s.places.push({ name: "", prefix: "" });
      return rerender();
    case "remove-place":
      s.plan_places = s.plan_places.filter((p) => p !== s.places[i].name);
      s.places.splice(i, 1);
      return rerender();
    case "parse-test":
      admin.parseResult = (await apiJson("/api/admin/parse-test", "POST",
        { line: $("#parse-line").value, unit_prefix: s.unit_prefix, own_prefix: s.own_prefix })).vehicles;
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
  if (section) { adminGo({ section: section.dataset.adminSection, parseResult: null }); return; }
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
  if (t.dataset.bind) { setPath(t.dataset.bind, t.dataset.number !== undefined ? Number(t.value) : inputValue(t)); return; }
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
