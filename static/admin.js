"use strict";

// Verwaltung: Einstellungen der Wehr (Name, Farben, Logos, Fahrzeuge, BKS-Kennung, Orte, Bedarfsplan),
// Stichwortkatalog, Benutzer und – für Superadmins – Verbandsgemeinden und Wehren.
// Wird nach app.js geladen und trägt sich in VIEWS ein. Rechte prüft das Backend (app/admin.py).

const ADMIN_SECTIONS = [      // [Schlüssel, Bezeichnung, braucht die Einstellungen der Wehr, nur Superadmin, nur Wehrleiter]
  ["unit", "Wehr", true], ["fleet", "Fahrzeuge", true], ["bks", "BKS-Kennung", true],
  ["places", "Orte & Bedarfsplan", true], ["keywords", "Stichworte"], ["users", "Benutzer"],
  ["fees", "Gebührenordnung", false, false, true], ["super", "Wehren & VGs", false, true],
];
const SETTINGS_SECTIONS = ADMIN_SECTIONS.filter((s) => s[2]).map((s) => s[0]);

const admin = {
  overview: null, slug: null, section: null, settings: null, keywords: null, memberships: null, superOverview: null,
  check: null, importFile: null, importPreview: null, keywordQuery: "", keywordEdit: null, parseResult: null, error: "",
  fees: null, feeVg: null, feeDraft: null,
  savedSettings: null,        // Stand der Einstellungen beim Laden/Speichern – Vergleich für „ungespeichert“
};

VIEWS.admin = { label: "Verwaltung", load: loadAdmin, render: renderAdmin, noYear: true,
  visible: () => can("admin") || config.superadmin };

// ------------------------------------------------------------ Laden
async function loadAdmin() {
  if (!admin.overview) {
    admin.overview = await api("/api/admin");
    // Gewählte Wehr behalten (z. B. nach dem Speichern), sonst die oben ausgewählte, sonst die erste
    const pick = (slug) => admin.overview.tenants.find((t) => t.slug === slug);
    admin.slug = (pick(admin.slug) || pick(config.tenant?.slug) || admin.overview.tenants[0])?.slug || null;
  }
  const sections = adminSections();
  if (!sections.some(([key]) => key === admin.section)) admin.section = sections[0][0];
  const s = admin.section;
  if (SETTINGS_SECTIONS.includes(s) && admin.settings?.slug !== admin.slug) {
    admin.settings = await api(`/api/admin/${admin.slug}/settings`);
    admin.savedSettings = JSON.stringify(settingsPayload());
    admin.check = null;
  }
  if (s === "keywords" && admin.keywords?.slug !== admin.slug) {
    admin.keywords = { ...(await api(`/api/admin/${admin.slug}/keywords`)), slug: admin.slug };
  }
  if (s === "users" && !admin.memberships) admin.memberships = (await api("/api/admin/memberships")).memberships;
  if (s === "super" && !admin.superOverview) admin.superOverview = await api("/api/super/overview");
  if (s === "fees") {
    admin.feeVg = admin.feeVg || admin.overview.vgs[0].slug;
    if (admin.fees?.vg !== admin.feeVg) {
      admin.fees = { vg: admin.feeVg, ...(await api(`/api/admin/vgs/${encodeURIComponent(admin.feeVg)}/fees`)) };
      admin.feeDraft = null;
    }
  }
}

function adminSections() {
  const hasTenant = Boolean(admin.overview.tenants.length);
  return ADMIN_SECTIONS.filter(([, , needsTenant, superOnly, vgOnly]) =>
    (!superOnly || admin.overview.superadmin) && (!needsTenant || hasTenant) && (hasTenant || superOnly)
    && (!vgOnly || admin.overview.vgs.length > 0));
}

async function adminGo(changes) {
  Object.assign(admin, changes, { error: "" });
  await showView();
}

// ------------------------------------------------------------ Rahmen
function renderAdmin() {
  const { tenants } = admin.overview;
  const tenantSelect = tenants.length > 1 && !["users", "super", "fees"].includes(admin.section)
    ? `<label class="field admin-tenant"><span>Wehr</span><select data-admin-tenant>${tenants.map((t) =>
      `<option value="${esc(t.slug)}" ${t.slug === admin.slug ? "selected" : ""}>${esc(t.name)} · ${esc(t.vg)}</option>`).join("")}</select></label>` : "";
  const sections = `<div class="segments" role="tablist">${adminSections().map(([key, label]) =>
    `<button type="button" data-admin-section="${key}" class="${key === admin.section ? "active" : ""}">${label}</button>`).join("")}</div>`;
  const body = {
    unit: unitSection, fleet: fleetSection, bks: bksSection, places: placesSection,
    keywords: keywordsSection, users: usersSection, super: superSection, fees: feesSection,
  }[admin.section]();
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
      <div class="preview-buttons"><span class="btn btn-primary btn-small">PDF einlesen</span><span class="btn btn-light btn-small">Tabelle</span></div>
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
function fleetSection() {
  const s = admin.settings;
  const others = (v) => s.fleet.filter((x) => x.call_sign && x !== v);
  const rows = s.fleet.map((v, i) => `<tr>
    <td class="order"><button type="button" class="icon-button" data-admin-action="move-vehicle" data-index="${i}" data-step="-1" ${i ? "" : "disabled"} aria-label="nach oben">↑</button><button type="button" class="icon-button" data-admin-action="move-vehicle" data-index="${i}" data-step="1" ${i < s.fleet.length - 1 ? "" : "disabled"} aria-label="nach unten">↓</button></td>
    <td>${textInput(`fleet.${i}.call_sign`, v.call_sign, 'placeholder="02/45" maxlength="5" class="narrow"')}</td>
    <td>${textInput(`fleet.${i}.label`, v.label, 'placeholder="z. B. HLF 20"')}</td>
    <td><input type="date" data-bind="fleet.${i}.in_service_from" value="${esc(v.in_service_from || "")}"></td>
    <td><input type="date" data-bind="fleet.${i}.in_service_until" value="${esc(v.in_service_until || "")}"></td>
    <td><select data-bind="fleet.${i}.replaced_by"><option value="">–</option>${others(v).map((x) =>
      `<option ${x.call_sign === v.replaced_by ? "selected" : ""}>${esc(x.call_sign)}</option>`).join("")}</select></td>
    <td class="center"><input type="checkbox" data-bind="fleet.${i}.in_plan_crew" ${v.in_plan_crew ? "checked" : ""} aria-label="zählt zur Gesamtstärke"></td>
    <td class="right">${v.incidents || ""}</td>
    <td><button type="button" class="icon-button" data-admin-action="remove-vehicle" data-index="${i}" aria-label="entfernen">✕</button></td>
  </tr>`).join("");
  const unused = Object.entries(s.unused_data);
  const substitutes = Object.entries(s.substitutes).map(([sub, block], i) => `<div class="inline-row">
    <input type="text" data-substitute="${i}" value="${esc(sub)}" placeholder="01/23" maxlength="5" class="narrow" aria-label="Ersatzfahrzeug">
    <span>wird geführt im Block</span>
    <select data-substitute-block="${i}">${s.fleet.map((v) => `<option ${v.call_sign === block ? "selected" : ""}>${esc(v.call_sign)}</option>`).join("")}</select>
    <button type="button" class="icon-button" data-admin-action="remove-substitute" data-sub="${esc(sub)}" aria-label="entfernen">✕</button></div>`).join("");
  return `<p class="small muted">Reihenfolge wie in der Einsatzübersicht. Neue eigene Fahrzeuge aus BKS-Berichten werden beim Übernehmen automatisch hinten angefügt (im Dienst ab Einsatztag).${helpButton("admin_fleet")}</p>
    <div class="table-wrap"><table class="mini-table admin-table"><thead><tr><th></th><th>Funkruf</th><th>Bezeichnung</th><th>im Dienst ab</th><th>außer Dienst ab</th><th>ersetzt durch</th><th>Bedarfsplan</th><th class="right">Einsätze</th><th></th></tr></thead>
    <tbody>${rows}</tbody></table></div>
    <button type="button" class="btn btn-light btn-small section-gap" data-admin-action="add-vehicle">Fahrzeug hinzufügen</button>
    ${unused.length ? `<div class="message message-info section-gap">Daten zu Fahrzeugen, die nicht (mehr) in der Liste stehen und daher nicht ausgewertet werden: ${unused.map(([cs, n]) => `${esc(cs)} (${n} Einsätze)`).join(", ")}.</div>` : ""}
    <h3 class="section-gap">Ersatzfahrzeuge</h3>
    <p class="small muted">Fährt ein Ersatzfahrzeug mit eigener Besatzung (Werkstatt), wird es im Block eines Stammfahrzeugs geführt.</p>
    ${substitutes}
    <button type="button" class="btn btn-light btn-small" data-admin-action="add-substitute" ${s.fleet.length ? "" : "disabled"}>Ersatzfahrzeug hinzufügen</button>
    ${saveButton()}`;
}

// ------------------------------------------------------------ BKS-Kennung
function bksSection() {
  const s = admin.settings;
  const result = admin.parseResult;
  const found = result ? (result.length ? `<ul class="plain-list">${result.map((v) =>
    `<li><b>${esc(v.name)}</b> → ${v.call_sign ? `Funkruf ${esc(v.call_sign)}${v.own ? " · <b>eigenes Fahrzeug</b>" : " · Fahrzeug der Einheit"}` : "nicht der Einheit zugeordnet"}</li>`).join("")}</ul>`
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
    <label class="toggle section-gap"><input type="checkbox" data-bind="response_plan_public" ${s.response_plan_public ? "checked" : ""}>
      Bedarfsplan für alle Rollen freigeben <span class="muted">(sonst nur Wehrführer, Wehrleiter)</span></label>
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
function usersSection() {
  const { tenants, vgs, roles } = admin.overview;
  const scopes = [...vgs.map((v) => ({ key: `vg:${v.slug}`, label: `${v.name} (alle Wehren)` })),
    ...tenants.map((t) => ({ key: `tenant:${t.slug}`, label: t.name }))];
  const rows = admin.memberships.map((m) => `<tr>
    <td>${esc(m.email)}</td><td>${esc(m.name)}${m.scope === "vg" ? " <span class='small muted'>(VG)</span>" : ""}</td><td>${esc(m.label)}</td>
    <td class="small muted">${m.last_login ? formatDate(m.last_login) : "noch nie"}</td>
    <td>${m.editable ? `<button type="button" class="icon-button" data-admin-action="revoke" data-email="${esc(m.email)}" data-scope="${m.scope}" data-slug="${esc(m.slug)}" aria-label="entfernen">✕</button>` : ""}</td></tr>`).join("");
  const roleOptions = Object.entries(roles).map(([key, r]) => `<option value="${key}" data-scope="${r.scope}">${esc(r.label)}</option>`).join("");
  return `<p class="small muted">Wer eine Zuordnung hat, kann sich mit seiner E-Mail-Adresse anmelden. Was eine Rolle darf, steht in der Hilfe.${helpButton("admin_roles")}</p>
    <div class="form-grid">
      ${adminField("E-Mail-Adresse", `<input type="email" id="grant-email" autocomplete="off">`, "span-2")}
      ${adminField("Bereich", `<select id="grant-scope">${scopes.map((s) => `<option value="${esc(s.key)}">${esc(s.label)}</option>`).join("")}</select>`, "span-2")}
      ${adminField("Rolle", `<select id="grant-role">${roleOptions}</select>`)}
      <div class="field"><span>&nbsp;</span><button type="button" class="btn btn-primary" data-admin-action="grant">Zuordnen</button></div>
    </div>
    <div class="table-wrap section-gap"><table class="mini-table admin-table"><thead><tr><th>E-Mail</th><th>Bereich</th><th>Rolle</th><th>zuletzt angemeldet</th><th></th></tr></thead>
    <tbody>${rows || `<tr><td colspan="5" class="muted">Noch keine Zuordnungen.</td></tr>`}</tbody></table></div>`;
}

function filterRoleOptions() {
  const scope = ($("#grant-scope")?.value || "").split(":")[0];
  const select = $("#grant-role");
  if (!select) return;
  for (const option of select.options) option.hidden = option.dataset.scope !== scope;
  if (select.selectedOptions[0]?.hidden) select.value = [...select.options].find((o) => !o.hidden)?.value || "";
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
    case "add-vehicle":
      s.fleet.push({ call_sign: "", label: "", in_service_from: "", in_service_until: "", replaced_by: "", in_plan_crew: true, incidents: 0 });
      return rerender();
    case "move-vehicle": {
      const j = i + Number(step);
      [s.fleet[i], s.fleet[j]] = [s.fleet[j], s.fleet[i]];
      return rerender();
    }
    case "remove-vehicle": {
      const v = s.fleet[i];
      if (v.incidents && !confirm(`${v.call_sign} hat Daten in ${v.incidents} Einsätzen. Ohne Eintrag in der Liste erscheinen sie nicht mehr in Auswertung und Export (die Daten bleiben erhalten). Entfernen?`)) return;
      s.fleet.splice(i, 1);
      return rerender();
    }
    case "add-substitute":
      s.substitutes[""] = s.fleet[0].call_sign;
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
      admin.memberships = (await apiJson("/api/admin/memberships", "POST",
        { email: $("#grant-email").value, scope: grantScope, slug: grantSlug, role: $("#grant-role").value })).memberships;
      toast("Zugeordnet");
      return rerender();
    }
    case "revoke":
      if (!confirm(`Zuordnung von ${email} entfernen?`)) return;
      admin.memberships = (await api(`/api/admin/memberships?${new URLSearchParams({ email, scope, slug })}`, { method: "DELETE" })).memberships;
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
  admin.settings = admin.keywords = admin.memberships = null;
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
  const vgSelect = admin.overview.vgs.length > 1 ? adminField("Verbandsgemeinde", `<select data-fee-vg>${admin.overview.vgs.map((v) =>
    `<option value="${esc(v.slug)}" ${v.slug === admin.feeVg ? "selected" : ""}>${esc(v.name)}</option>`).join("")}</select>`) : "";
  const rows = schedules.map((x) => `<tr>
    <td><strong>${esc(x.name)}</strong></td><td>${formatDate(x.valid_from)}</td><td class="right">${x.rates.vehicles.length}</td>
    <td class="right"><button type="button" class="btn btn-light btn-small" data-admin-action="fee-edit" data-id="${x.id}">Bearbeiten</button>
      <button type="button" class="btn btn-light btn-small" data-admin-action="fee-copy" data-id="${x.id}">Als neue Fassung</button>
      <button type="button" class="btn btn-outline btn-small" data-admin-action="fee-delete" data-id="${x.id}">Löschen</button></td></tr>`).join("");
  return `<p class="small muted">Kostensätze der Satzung über den Kostenersatz der Feuerwehr. Für einen Einsatz gilt die Fassung, die am Einsatztag gilt. Den Fahrzeugtyp eines Fahrzeugs bestimmt seine Bezeichnung in der Fahrzeugliste der Wehr (z. B. „HLF 20“).${helpButton("fees")}</p>
    ${vgSelect ? `<div class="form-grid">${vgSelect}</div>` : ""}
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
  const url = `/api/admin/vgs/${encodeURIComponent(admin.feeVg)}/fees`;
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
      admin.fees = { vg: admin.feeVg, ...(await api(`${url}/${data.id}`, { method: "DELETE" })) };
      toast("Fassung gelöscht");
      break;
    case "fee-save": {
      const d = admin.feeDraft;
      const body = { name: d.name, valid_from: d.valid_from, rates: d.rates };
      admin.fees = { vg: admin.feeVg, ...(await apiJson(d.id ? `${url}/${d.id}` : url, d.id ? "PUT" : "POST", body)) };
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
      if (!confirmDiscard()) { t.value = admin.slug; return; }
      await adminGo({ slug: t.value, parseResult: null, keywordEdit: null });
      return;
    }
    if (t.dataset.feeVg !== undefined) { await adminGo({ feeVg: t.value }); return; }
    if (t.dataset.limits !== undefined) { renderAdmin(); return; }     // Auswahl der Standardgrenze aktualisieren
    if (t.dataset.bind?.startsWith("places.") && t.dataset.bind.endsWith(".name")) { renderAdmin(); return; }
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

// Rollenauswahl passend zum ersten Bereich, sobald der Benutzer-Bereich gezeichnet ist
new MutationObserver(() => { if (admin.section === "users") filterRoleOptions(); })
  .observe($("#view-admin"), { childList: true });
