"use strict";

// Darstellung der Verwaltungsbereiche; Zustand und Aktionen liegen in admin.js. Die Einstellungsbereiche gibt es
// zweimal: für eine Wehr (mit Kennzeichen, wo sie von der VG abweicht) und für die Verbandsgemeinde (vg…Section:
// Vorgaben der VG und alle Wehren auf einmal).

// ------------------------------------------------------------ Vererbung: von der VG / abweichend
const INHERITED_LABELS = { bks_code: "Kennung der VG", control_center: "FEZ-Kennung", places: "Orte",
  plan_min_level: "Alarmstufe", response_limits: "Zeitgrenzen", default_limit: "Standardgrenze",
  second_limit: "zweite Grenze", day_hours: "Tag", numbering: "Nummerierung", colors: "Farben" };

const sameValue = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

// Wert einer Vorgabe in den Einstellungen der Wehr, vergleichbar mit inherited
function ownValue(key) {
  const s = admin.settings;
  if (key === "places") return s.places.map((p) => p.name);
  if (key === "colors") return cleanColors();
  return s[key] ?? null;
}

function inheritedValueText(key, value) {
  if (value === null || value === undefined || (Array.isArray(value) && !value.length)) return "–";
  if (key === "day_hours") return `${value[0]}–${value[1]} Uhr`;
  if (key === "numbering") return value === "by_date" ? "nach Datum" : "aus dem Bericht";
  if (key === "colors") return value.brand || "Standard";
  if (key === "response_limits") return `${value.join(", ")} Min.`;
  if (["default_limit", "second_limit"].includes(key)) return `${value} Min.`;
  return Array.isArray(value) ? value.join(", ") : String(value);
}

// Kennzeichen hinter einem Feld der Wehr: „von der VG“ oder „abweichend“ mit „VG-Wert übernehmen“
function inheritNote(...keys) {
  const s = admin.settings;
  const own = keys.filter((key) => !sameValue(ownValue(key), s.inherited[key]));
  if (!own.length) return `<span class="inherit-badge" title="Vorgabe der ${esc(s.vg.name)}">von der VG</span>`;
  return `<span class="inherit-badge own" title="VG: ${esc(own.map((k) => `${INHERITED_LABELS[k]} ${inheritedValueText(k, s.inherited[k])}`).join(" · "))}">abweichend von der VG</span>
    ${own.map((key) => `<button type="button" class="btn btn-light btn-small" data-admin-action="inherit" data-key="${key}">${own.length > 1 ? `${INHERITED_LABELS[key]}: ` : ""}VG-Wert übernehmen</button>`).join("")}`;
}

// Abweichung aufheben: Wert der VG eintragen (gespeichert wird beim Speichern; gleich der VG = keine Abweichung)
function takeInherited(key) {
  const s = admin.settings, value = structuredClone(s.inherited[key]);
  if (key === "places") {
    s.places = value.map((name) => ({ name }));
    s.plan_places = s.plan_places.filter((p) => value.includes(p));
  } else if (key === "bks_code") {
    setBks("code", value || "");
  } else if (key === "colors") {
    s.colors = { brand: "", brand_dark: "", ...value };
    admin.check = null;
    scheduleThemeCheck();
  } else {
    s[key] = value;
  }
}

// Abweichungen der Wehren von den Vorgaben (VG-Ansicht), z. B. „Wehr A: Tag 8–20 Uhr“
function overridesNote(...keys) {
  const rows = admin.vgSettings.tenants.flatMap((t) => keys.filter((k) => k in t.overrides)
    .map((k) => `<li><b>${esc(t.name)}</b>: ${INHERITED_LABELS[k]} ${esc(inheritedValueText(k, t.overrides[k]))}</li>`));
  return rows.length ? `<div class="message message-info section-gap">Abweichend von der Vorgabe (ändert die Wehr selbst):<ul class="plain-list">${rows.join("")}</ul></div>` : "";
}

// ------------------------------------------------------------ Allgemein: Name, Farben, Logos
const hexToRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const rgbToHex = (rgb) => "#" + rgb.map((c) => Math.max(0, Math.min(255, Math.round(c || 0))).toString(16).padStart(2, "0")).join("").toUpperCase();
const isHex = (value) => /^#[0-9A-Fa-f]{6}$/.test(value);

function colorField(key, label, hint) {
  const value = adminData().colors[key] || "";
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

const colorFields = () => `<div class="admin-colors">
      <div>${colorField("brand", "Hauptfarbe", "Kopfzeile, Knöpfe, Überschriften und Diagramme. Weiße Schrift muss darauf lesbar sein.")}
        ${colorField("brand_dark", "Dunkle Farbe (optional)", "Hervorgehobene Kacheln und Verlauf der Kopfzeile. Leer = aus der Hauptfarbe abgeleitet.")}
        <div id="theme-problems"></div></div>
      ${themePreview()}
    </div>`;

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
  const fonts = Object.entries(admin.overview.fonts || {}).map(([name, label]) => {
    const url = s.assets[name];
    return `<div class="logo-slot">
      <div><strong>${esc(label)}</strong><p class="small muted">${url ? "eigene Schriftdatei" : "Systemschrift"}</p>
        <label class="btn btn-light btn-small file-button">Datei wählen<input type="file" accept=".woff2,.woff,.ttf,.otf,font/woff2,font/woff,font/ttf,font/otf" data-asset="${name}" hidden></label>
        ${url ? `<button type="button" class="btn btn-outline btn-small" data-admin-action="delete-asset" data-name="${name}">Entfernen</button>` : ""}</div>
    </div>`;
  }).join("");
  // Farben, Logos und Schrift sieht man erst, wenn oben genau diese Wehr gewählt ist (die Gesamtansicht ist neutral)
  const elsewhere = config.tenant?.slug !== admin.slug
    ? `<p class="small muted">Farben, Logos und Schrift erscheinen in der Oberfläche, sobald oben ${esc(s.name)} gewählt ist.</p>` : "";
  return `<div class="form-grid">${adminField("Name der Wehr", textInput("name", s.name, 'maxlength="80"'), "span-4")}</div>
    <h3 class="section-gap">Farben ${inheritNote("colors")}</h3>
    ${elsewhere}
    ${colorFields()}
    <h3 class="section-gap">Logos</h3>
    <p class="small muted">PNG, JPEG oder WebP, höchstens 512 KB. Wird sofort gespeichert.</p>
    <div class="logo-slots">${logos}</div>
    <h3 class="section-gap">Schrift</h3>
    <p class="small muted">Ohne eigene Datei gelten die Systemschriften (Segoe UI, Roboto, Helvetica, Arial). WOFF2, WOFF, TTF oder OTF, höchstens 1 MB; die Lizenz der Schrift muss die Nutzung im Web erlauben. Ist keine fette Schrift hinterlegt, berechnet der Browser sie aus der normalen. Wird sofort gespeichert.</p>
    <div class="logo-slots">${fonts}</div>
    ${saveButton()}`;
}

function vgUnitSection() {
  const d = admin.vgSettings;
  return `<p class="small muted">Vorgaben der ${esc(d.vg.name)} für alle ihre Wehren. Eine Wehr kann bei sich abweichen; ihren Namen und ihre Logos pflegt jede Wehr selbst (oben die Wehr auswählen).</p>
    <h3 class="section-gap">Farben</h3>
    ${colorFields()}
    ${overridesNote("colors")}
    ${saveButton()}`;
}

function themePreview() {
  const d = adminData();
  return `<div class="theme-preview" id="theme-preview" aria-label="Vorschau der Farben">
    <div class="preview-bar"><span>${esc(d.name || d.vg?.name || "")}</span><b>Auswertung</b></div>
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

const cleanColors = () => Object.fromEntries(Object.entries(adminData()?.colors || {}).filter(([, v]) => v));

function updateThemePreview() {
  const preview = $("#theme-preview");
  if (!preview) return;
  const palette = admin.check ? admin.check.palette : adminData().palette;
  for (const name of [...preview.style]) if (name.startsWith("--")) preview.style.removeProperty(name);
  for (const [name, value] of Object.entries(palette || {})) preview.style.setProperty(name, value);
  const problems = admin.check?.problems || [];
  $("#theme-problems").innerHTML = problems.length ? `<div class="message message-error">${problems.map(esc).join("<br>")}</div>` : "";
}

function setColor(key, hex, source) {
  adminData().colors[key] = hex;
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
const newVehicle = (fields = {}) => ({ call_sign: "", name: "", suggested_name: "", types: [], label: "", in_service_from: "",
  in_service_until: "", replaced_by: "", in_plan_crew: true, incidents: 0, ...fields });

// Funkrufnamen zur Auswahl: Wehr aus ihren Berichten; VG alle Fahrzeuge der Wehren und die noch nicht zugeordneten
function knownVehicles() {
  if (!admin.vg) return admin.settings.known_vehicles;
  const f = admin.vgFleet;
  const listed = f.tenants.flatMap((t) => t.fleet).map((v) => ({ name: v.name || v.suggested_name, description: v.description,
    types: v.types, label: v.label }));
  return [...listed, ...f.unassigned].filter((k) => k.name);
}
const knownVehicle = (name) => knownVehicles().find((k) => k.name === name);

// Fahrzeugtyp vergleichen wie fees._type_key (ohne Leerzeichen und Satzzeichen)
const typeKey = (text) => (text || "").replace(/[\s\-./]/g, "").toLowerCase();

// Alle Fahrzeuglisten der Ansicht: die der Wehr bzw. die aller Wehren der VG
const allFleets = () => admin.vg ? admin.vgFleet.tenants.map((t) => t.fleet) : [admin.settings.fleet];

// Funkrufname, den ein anderer Eintrag schon hat (oder als Vorschlag für seinen alten Kurznamen)
function takenBy(v) {
  if (!v.name) return null;
  return allFleets().flat().find((x) => x !== v && (x.name === v.name || (!x.name && x.suggested_name === v.name)));
}

// Funkrufname mit Auflösung (Kennung, Standort, Fahrzeugart) und Block der Einsatzübersicht
function callSignCell(v, i, path, id) {
  const known = knownVehicle(v.name);
  const other = takenBy(v);
  const block = v.call_sign ? `Block ${esc(v.call_sign)}` : "Block wird beim Speichern vergeben";
  const hint = other ? `<span class="missing-name">Steht schon in einer Liste (${esc(other.call_sign || other.name)})${other.name ? "" : " – bitte dort eintragen"}</span>`
    : v.name ? [block, known && esc(known.description)].filter(Boolean).join(" · ")
    : v.call_sign ? `<span class="missing-name">Funkrufnamen wie im BKS-Bericht eintragen (bisher nur ${esc(v.call_sign)})</span>`
    : "Funkrufnamen auswählen oder eintragen";
  // Zur Auswahl nur Fahrzeuge, die noch nicht in einer Liste stehen; der Vorschlag für diesen Eintrag zuerst
  const used = new Set(allFleets().flat().filter((x) => x !== v).flatMap((x) => [x.name, x.name ? "" : x.suggested_name]).filter(Boolean));
  const options = [...new Set([v.suggested_name, ...knownVehicles().map((k) => k.name)].filter((n) => n && !used.has(n)))];
  const placeholder = esc(v.suggested_name || "z. B. FL NR#.ABC 02/45-01");
  return `${textInput(`${path}.${i}.name`, v.name, `list="vehicles-${id}${i}" placeholder="${placeholder}" spellcheck="false" class="wide"`)}
    <datalist id="vehicles-${id}${i}">${options.map((n) => `<option value="${esc(n)}">${esc(knownVehicle(n)?.description || "")}</option>`).join("")}</datalist>
    <div class="small muted">${hint}</div>`;
}

// Fahrzeugtyp: Auswahl aus den Typen der Kennzahl (Funkrufnamenverzeichnis) und der Gebührenordnung
function vehicleTypeCell(v, i, path, id) {
  const feeTypes = adminData().fee_types;
  const types = knownVehicle(v.name)?.types || v.types || [];
  const fee = new Set(feeTypes.map(typeKey));
  const options = [...new Set([...types, ...feeTypes])];
  let hint = "";
  if (!v.label && types.length > 1) hint = `laut Kennzahl: ${types.map(esc).join(" / ")}`;
  else if (v.label && feeTypes.length && !fee.has(typeKey(v.label))) hint = '<span class="missing-name">nicht in der Gebührenordnung</span>';
  return `${textInput(`${path}.${i}.label`, v.label, `list="types-${id}${i}" placeholder="${esc(types[0] || "z. B. HLF 20")}"`)}
    <datalist id="types-${id}${i}">${options.map((t) => `<option value="${esc(t)}">${types.includes(t) ? "laut Funkrufname" : "Gebührenordnung"}</option>`).join("")}</datalist>
    ${hint ? `<div class="small muted">${hint}</div>` : ""}`;
}

// Zeilen einer Fahrzeugliste; path ist ihr Pfad im Datensatz (fleet bzw. tenants.<n>.fleet), tenant die Wehr in der VG
function fleetRows(fleet, path, id, tenant = null) {
  const others = (v) => fleet.filter((x) => vehicleKey(x) && x !== v);
  const tenants = admin.vg ? admin.vgFleet.tenants : [];
  const search = (v) => esc([v.name, v.suggested_name, v.call_sign, v.label].filter(Boolean).join(" ").toLowerCase());
  return fleet.map((v, i) => `<tr data-fleet-row="${search(v)}">
    <td class="order sticky-col"><button type="button" class="icon-button" data-admin-action="move-vehicle" data-list="${path}" data-index="${i}" data-step="-1" ${i ? "" : "disabled"} aria-label="nach oben">↑</button><button type="button" class="icon-button" data-admin-action="move-vehicle" data-list="${path}" data-index="${i}" data-step="1" ${i < fleet.length - 1 ? "" : "disabled"} aria-label="nach unten">↓</button></td>
    <td class="sticky-col name-col">${callSignCell(v, i, path, id)}</td>
    ${tenant === null ? "" : `<td><select class="fleet-tenant" data-fleet-tenant="${tenant}:${i}" aria-label="Wehr">${tenants.map((t, j) =>
      `<option value="${j}" ${j === tenant ? "selected" : ""}>${esc(t.name)}</option>`).join("")}<option value="">keiner Wehr</option></select></td>`}
    <td>${vehicleTypeCell(v, i, path, id)}</td>
    <td class="detail-col"><input type="date" data-bind="${path}.${i}.in_service_from" value="${esc(v.in_service_from || "")}" aria-label="im Dienst ab"></td>
    <td class="detail-col"><input type="date" data-bind="${path}.${i}.in_service_until" value="${esc(v.in_service_until || "")}" aria-label="außer Dienst ab"></td>
    <td class="detail-col"><select data-bind="${path}.${i}.replaced_by" aria-label="ersetzt durch"><option value="">–</option>${others(v).map((x) =>
      `<option value="${esc(vehicleKey(x))}" ${vehicleKey(x) === v.replaced_by ? "selected" : ""}>${esc(x.call_sign || x.name)}</option>`).join("")}</select></td>
    <td class="center detail-col"><input type="checkbox" data-bind="${path}.${i}.in_plan_crew" ${v.in_plan_crew ? "checked" : ""} aria-label="zählt zur Gesamtstärke"></td>
    <td class="right">${v.incidents || ""}</td>
    <td><button type="button" class="icon-button" data-admin-action="remove-vehicle" data-list="${path}" data-index="${i}" aria-label="entfernen">✕</button></td>
  </tr>`).join("");
}

const fleetHead = (withTenant) => `<thead><tr><th class="sticky-col"></th><th class="sticky-col name-col">Funkrufname</th>${withTenant ? "<th>Wehr</th>" : ""}<th>Fahrzeugtyp</th><th class="detail-col">im Dienst ab</th><th class="detail-col">außer Dienst ab</th><th class="detail-col">ersetzt durch</th><th class="detail-col">Gesamtstärke</th><th class="right">Einsätze</th><th></th></tr></thead>`;

// Suche und Umschalter kompakt / alle Spalten über einer Fahrzeugtabelle
const fleetTools = () => `<div class="admin-status fleet-tools">
    <input type="search" class="search" data-fleet-search value="${esc(admin.fleetQuery)}" placeholder="Fahrzeug suchen: Funkrufname, Block, Typ …" aria-label="Fahrzeug suchen">
    <span class="toolbar-right"><button type="button" class="btn btn-light btn-small" data-admin-action="fleet-compact"
      data-tip="Dienstzeitraum, Nachfolger und Gesamtstärke ${fleetCompact() ? "einblenden" : "ausblenden"}">${fleetCompact() ? "Alle Spalten" : "Kompakt"}</button></span>
  </div>`;
const fleetTableClass = () => `mini-table admin-table fleet-table ${fleetCompact() ? "compact" : ""}`;

// Suche: Zeilen nur ein- und ausblenden (Eingaben bleiben stehen)
function filterFleetRows() {
  const words = admin.fleetQuery.toLowerCase().split(/\s+/).filter(Boolean);
  for (const row of $$("#view-admin [data-fleet-row]")) row.hidden = !words.every((w) => row.dataset.fleetRow.includes(w));
}

// Ersatzfahrzeuge einer Fahrzeugliste: werden im Block eines Stammfahrzeugs geführt
function substituteRows(substitutes, fleet, subsPath, listPath) {
  return Object.entries(substitutes).map(([sub, block], i) => `<div class="inline-row">
    <input type="text" data-substitute="${i}" data-subs="${subsPath}" value="${esc(sub)}" list="known-vehicles" placeholder="z. B. FL NR#.ABC 01/23-01" spellcheck="false" class="wide" aria-label="Ersatzfahrzeug (Funkrufname)">
    <span>wird geführt im Block</span>
    <select data-substitute-block="${i}" data-subs="${subsPath}">${fleet.map((v) => `<option value="${esc(vehicleKey(v))}" ${vehicleKey(v) === block ? "selected" : ""}>${esc(v.call_sign || v.name)}</option>`).join("")}</select>
    <button type="button" class="icon-button" data-admin-action="remove-substitute" data-subs="${subsPath}" data-sub="${esc(sub)}" aria-label="entfernen">✕</button></div>`).join("")
    + `<button type="button" class="btn btn-light btn-small" data-admin-action="add-substitute" data-subs="${subsPath}" data-list="${listPath}" ${fleet.length ? "" : "disabled"}>Ersatzfahrzeug hinzufügen</button>`;
}

const unusedNote = (unused) => {
  const entries = Object.entries(unused || {});
  return entries.length ? `<div class="message message-info section-gap">Daten zu Fahrzeugen, die nicht (mehr) in der Liste stehen und daher nicht ausgewertet werden: ${entries.map(([cs, n]) => `${esc(cs)} (${n} Einsätze)`).join(", ")}.</div>` : "";
};

const knownDatalist = () => `<datalist id="known-vehicles">${knownVehicles().map((k) =>
  `<option value="${esc(k.name)}">${esc(k.description || "")}</option>`).join("")}</datalist>`;

function fleetSection() {
  const s = admin.settings;
  const emptyRow = s.fleet.some((v) => !v.name && !v.call_sign);
  const vg = adminTenantVg();
  return `<p class="small muted">Reihenfolge wie in der Einsatzübersicht. Funkrufname genau wie im BKS-Bericht – zur Auswahl stehen die Fahrzeuge aus den bisher eingelesenen Berichten (<a href="${esc(s.call_sign_directory)}" target="_blank" rel="noopener">Funkrufnamenverzeichnis RLP</a>). Neue eigene Fahrzeuge aus BKS-Berichten werden beim Übernehmen automatisch hinten angefügt (im Dienst ab Einsatztag).${vg ? ` Alle Fahrzeuge der VG auf einmal: oben „Wehrleitung · ${esc(vg.name)}“ wählen.` : ""}</p>
    ${knownDatalist()}
    ${fleetTools()}
    <div class="table-wrap table-scroll"><table class="${fleetTableClass()}">${fleetHead(false)}
    <tbody>${fleetRows(s.fleet, "fleet", "")}</tbody></table></div>
    <button type="button" class="btn btn-light btn-small section-gap" data-admin-action="add-vehicle" data-list="fleet" ${emptyRow ? 'disabled title="Erst den Funkrufnamen des neuen Fahrzeugs eintragen"' : ""}>Fahrzeug hinzufügen</button>
    ${unusedNote(s.unused_data)}
    <h3 class="section-gap">Ersatzfahrzeuge</h3>
    <p class="small muted">Fährt ein Ersatzfahrzeug mit eigener Besatzung (Werkstatt), wird es im Block eines Stammfahrzeugs geführt.</p>
    ${substituteRows(s.substitutes, s.fleet, "substitutes", "fleet")}
    ${saveButton()}`;
}

// ------------------------------------------------------------ Verbandsgemeinde: Fahrzeuge aller Wehren der VG
function vgFleetSection() {
  const f = admin.vgFleet;
  const typeCell = (label) => label ? esc(label) : '<span class="muted">–</span>';
  const groups = f.tenants.map((t, j) => {
    const path = `tenants.${j}.fleet`;
    const emptyRow = t.fleet.some((v) => !v.name && !v.call_sign);
    return `<tr class="group-row"><th colspan="10">${esc(t.name)}</th></tr>
      ${fleetRows(t.fleet, path, `${j}-`, j) || '<tr><td colspan="10" class="muted">Noch keine Fahrzeuge.</td></tr>'}
      <tr><td></td><td colspan="9"><button type="button" class="btn btn-light btn-small" data-admin-action="add-vehicle" data-list="${path}" ${emptyRow ? "disabled" : ""}>Fahrzeug für ${esc(t.name)} hinzufügen</button>
        ${unusedNote(t.unused_data)}
        <details class="section-gap"><summary>Ersatzfahrzeuge von ${esc(t.name)} (${Object.keys(t.substitutes).length})</summary>
          ${substituteRows(t.substitutes, t.fleet, `tenants.${j}.substitutes`, path)}</details></td></tr>`;
  }).join("");
  const assign = (v) => `<select data-assign-vehicle="${esc(v.name)}" aria-label="Wehr von ${esc(v.name)}"><option value="">– keiner Wehr –</option>${f.tenants.map((t, j) =>
    `<option value="${j}">${esc(t.name)}</option>`).join("")}</select>`;
  const openRow = (v) => `<tr><td><b>${esc(v.name)}</b><div class="small muted">${esc(v.description)}</div></td><td>${typeCell(v.label)}</td><td>${assign(v)}</td></tr>`;
  const own = f.unassigned.filter((v) => v.vg), others = f.unassigned.filter((v) => !v.vg);
  return `<p class="small muted">Alle Fahrzeuge der VG in einer Tabelle, gruppiert nach Wehr. Über „Wehr“ wechselt ein Fahrzeug die Wehr; Einsätze mit seinen Daten bleiben bei der bisherigen Wehr, dort wird es ab dann nicht mehr zugeordnet. Gespeichert wird alles zusammen. (<a href="${esc(f.call_sign_directory)}" target="_blank" rel="noopener">Funkrufnamenverzeichnis RLP</a>)</p>
    ${knownDatalist()}
    ${fleetTools()}
    <div class="table-wrap table-scroll"><table class="${fleetTableClass()}">${fleetHead(true)}<tbody>${groups}</tbody></table></div>
    <h3 class="section-gap">Noch keiner Wehr zugeordnet</h3>
    <div class="table-wrap"><table class="mini-table admin-table"><thead><tr><th>Funkrufname</th><th>Fahrzeugtyp</th><th>Wehr</th></tr></thead>
      <tbody>${own.map(openRow).join("") || '<tr><td colspan="3" class="muted">Alle Fahrzeuge der VG aus den Berichten sind zugeordnet.</td></tr>'}</tbody></table></div>
    ${others.length ? `<details class="section-gap"><summary>Weitere Fahrzeuge aus Berichten (${others.length}, z. B. Rettungsdienst, Fahrzeuge des Landes, Nachbarwehren)</summary>
      <div class="table-wrap"><table class="mini-table admin-table"><tbody>${others.map(openRow).join("")}</tbody></table></div></details>` : ""}
    <div class="inline-row section-gap">
      <input type="text" id="vg-vehicle-name" list="known-vehicles" placeholder="Funkrufname, z. B. FL NR#.ABC 01/10-01" spellcheck="false" class="wide" aria-label="Funkrufname">
      <select id="vg-vehicle-tenant" aria-label="Wehr">${f.tenants.map((t, j) => `<option value="${j}">${esc(t.name)}</option>`).join("")}</select>
      <button type="button" class="btn btn-light btn-small" data-admin-action="assign-vehicle">Fahrzeug zuordnen</button>
    </div>
    ${saveButton()}`;
}

// Funkrufname (aus „noch keiner Wehr“ oder eingetippt) einer Wehr der VG zuordnen
function assignVehicle(name, tenant) {
  const f = admin.vgFleet;
  const known = f.unassigned.find((v) => v.name === name);
  f.tenants[tenant].fleet.push(newVehicle({ name, label: known?.label || "", types: known?.types || [], description: known?.description || "" }));
  f.unassigned = f.unassigned.filter((v) => v.name !== name);
}

// Fahrzeug einer Wehr zu einer anderen (target: Index) bzw. aus den Listen nehmen (null); false = abgebrochen
async function moveFleetVehicle(from, i, target) {
  const f = admin.vgFleet, source = f.tenants[from], v = source.fleet[i];
  const name = v.name || v.suggested_name;
  if (target !== null && !name) {
    await askConfirm({ title: "Funkrufname fehlt.", text: "Bitte zuerst den Funkrufnamen des Fahrzeugs eintragen, dann die Wehr wechseln.", confirm: "Verstanden", cancel: null });
    return false;
  }
  const to = target === null ? "keiner Wehr" : f.tenants[target].name;
  if (v.incidents && !await askConfirm({ title: `${name || v.call_sign} ${target === null ? "aus allen Listen nehmen" : `${to} zuordnen`}?`,
    text: `${plural(v.incidents, "Einsatz von", "Einsätze von")} ${source.name} haben Daten dazu. Sie bleiben dort, ab dem Speichern wird das Fahrzeug aber ${to} zugeordnet.`,
    confirm: "Zuordnung ändern", danger: true })) return false;
  source.fleet.splice(i, 1);
  const keys = [v.call_sign, v.name].filter(Boolean);
  for (const x of source.fleet) if (keys.includes(x.replaced_by)) x.replaced_by = "";
  source.substitutes = Object.fromEntries(Object.entries(source.substitutes).filter(([, block]) => !keys.includes(block)));
  if (target !== null) {
    f.tenants[target].fleet.push(newVehicle({ name, label: v.label, types: v.types, description: v.description,
      in_service_from: v.in_service_from, in_service_until: v.in_service_until, in_plan_crew: v.in_plan_crew }));
  } else if (name) {
    f.unassigned.unshift({ name, description: v.description, types: v.types, label: v.label, vg: true });
  }
  return true;
}

// ------------------------------------------------------------ BKS-Kennung
// Zuordnung eines erkannten Fahrzeugs: zuerst über den Funkrufnamen der Fahrzeugliste, sonst über die Präfixe
function fleetMatch(v) {
  const listed = admin.settings.fleet.find((x) => x.name && x.name === v.name);
  if (listed) return `<b>eigenes Fahrzeug</b> (Fahrzeugliste, Block ${esc(listed.call_sign || listed.name)})`;
  if (v.own) return `<b>eigenes Fahrzeug</b> (Block ${esc(v.call_sign)}, noch nicht in der Fahrzeugliste)`;
  if (v.call_sign) return "Fahrzeug einer anderen Wehr der VG";
  return "fremdes Fahrzeug";
}

// Kennung der VG und Standort ergeben die Einheit im Bericht: „NR#.ABC“ + „02“ -> „FW NR#.ABC 02“
function setBks(part, value) {
  const s = admin.settings;
  if (part === "code") s.bks_code = value || null;
  else s.station = value || null;
  s.unit_marker = s.bks_code && s.station ? `FW ${s.bks_code} ${s.station}` : "";
  if (!s.unit_marker) {                     // ohne Standort: nur die Fahrzeuge der VG erkennbar
    s.unit_prefix = s.bks_code ? `FL ${s.bks_code} ` : "";
    s.own_prefix = "";
  }
  const derived = $("#bks-derived");
  if (derived) derived.innerHTML = bksDerived(s);
}

// Präfixe wie admin.prefixes_of: „FW NR#.ABC 02“ -> „FL NR#.ABC “ und „02/“; ohne Einheit die gespeicherten
function bksPrefixes(s) {
  const m = /^FW (\S+) (\d\d)$/.exec((s.unit_marker || "").trim());
  return m ? { unit: `FL ${m[1]} `, own: `${m[2]}/`, valid: true }
    : { unit: s.unit_prefix, own: s.own_prefix, valid: !(s.bks_code && s.station) };
}

function bksDerived(s) {
  const p = bksPrefixes(s);
  if (s.station && !/^\d\d$/.test(s.station)) return `<span class="message-error">Standort zweistellig, z. B. 02.</span>`;
  if (!p.valid) return `<span class="message-error">Kennung wie in der Kopfzeile des Berichts, z. B. NR#.ABC aus „FW NR#.ABC 02“.</span>`;
  if (!p.unit) return "Ohne Kennung und Standort zählen nur die Fahrzeuge der Fahrzeugliste als eigene.";
  return `Einheit im Bericht <b>${esc(s.unit_marker || "–")}</b>. Eigene Fahrzeuge beginnen mit <b>${esc(p.unit + p.own)}</b>, Fahrzeuge der übrigen Wehren der VG mit <b>${esc(p.unit)}</b>. Fahrzeuge der Fahrzeugliste zählen immer als eigene.`;
}

const parseTestField = () => `<h3 class="section-gap">Testen</h3>
    <label class="field"><span>Text aus einem Bericht</span>
      <textarea rows="4" id="parse-line" spellcheck="false" placeholder="Funkrufnamen, Zeilen der Fahrzeugtabelle oder den ganzen Berichtstext einfügen, z. B. FL NR#.ABC 02/45-01"></textarea></label>
    <button type="button" class="btn btn-light btn-small section-gap" data-admin-action="parse-test">Erkennung prüfen</button>`;

function parseResultList(items) {
  if (!admin.parseResult) return "";
  return items.length ? `<ul class="plain-list">${items.join("")}</ul>`
    : `<p class="message message-error">Kein Funkrufname (z. B. FL NR#.ABC 02/45-01) und keine Einheit (z. B. FW NR#.ABC 02) gefunden.</p>`;
}

const numberingOptions = (value, bind) => `<select data-bind="${bind}">
        <option value="bks" ${value === "bks" ? "selected" : ""}>aus dem Bericht (fehlt sie: nächste freie)</option>
        <option value="by_date" ${value === "by_date" ? "selected" : ""}>nach Datum durchnummerieren</option></select>`;
const NUMBERING_HINT = "Nach Datum: Die App nummeriert alle Einsätze eines Jahres nach dem Beginn; ein später eingelesener Einsatz (z. B. eine selbst angelegte Brandsicherheitswache) rückt an seine Stelle, die folgenden Nummern verschieben sich. Beim Speichern werden alle Jahre neu nummeriert.";

function bksSection() {
  const s = admin.settings;
  const result = admin.parseResult;
  const items = result ? [
    ...result.units.map((u) => `<li><b>${esc(u.unit)}</b> → ${u.own ? "<b>Bericht dieser Wehr</b>" : "Bericht einer anderen Einheit"}</li>`),
    ...result.vehicles.map((v) => `<li><b>${esc(v.name)}</b> → ${fleetMatch(v)}${v.description ? `<br><span class="small muted">${esc(v.description)}</span>` : ""}</li>`),
  ] : [];
  return `<p class="small muted">So erkennt die App im Einsatzbericht des BKS-Portals, von welcher Wehr ein Bericht stammt und welche Fahrzeuge dazugehören.</p>
    <div class="form-grid">
      ${adminField(`Kennung der VG ${inheritNote("bks_code")}`, `<input type="text" data-bks="code" value="${esc(s.bks_code || "")}" placeholder="NR#.ABC" spellcheck="false">`, "span-2")}
      ${adminField("Standort", `<input type="text" data-bks="station" value="${esc(s.station || "")}" placeholder="02" maxlength="2" class="narrow">`)}
      ${adminField(`FEZ-Kennung ${inheritNote("control_center")}`, textInput("control_center", s.control_center, 'spellcheck="false"'), "span-2")}
    </div>
    <p class="small muted" id="bks-derived">${bksDerived(s)}</p>
    ${parseTestField()}
    ${parseResultList(items)}
    <h3 class="section-gap">Einsatznummern ${inheritNote("numbering")}</h3>
    <div class="form-grid">${adminField("Nummerierung", numberingOptions(s.numbering, "numbering"), "span-3")}</div>
    <p class="small muted">${NUMBERING_HINT}</p>
    ${saveButton()}`;
}

function vgBksSection() {
  const d = admin.vgSettings;
  const result = admin.parseResult;
  const unit = (t) => "bks_code" in t.overrides ? t.unit_marker || "–" : d.bks_code && t.station ? `FW ${d.bks_code} ${t.station}` : "–";
  const rows = d.tenants.map((t, j) => `<tr><td><b>${esc(t.name)}</b></td>
    <td>${textInput(`tenants.${j}.station`, t.station || "", 'placeholder="02" maxlength="2" class="narrow" aria-label="Standort"')}</td>
    <td>${esc(unit(t))}${"bks_code" in t.overrides ? ` <span class="inherit-badge own">eigene Kennung ${esc(t.overrides.bks_code || "–")}</span>` : ""}</td></tr>`).join("");
  const owner = (tenant) => tenant ? `<b>${esc(tenant)}</b>` : "keiner Wehr der VG";
  const items = result ? [
    ...result.units.map((u) => `<li><b>${esc(u.unit)}</b> → Bericht von ${owner(u.tenant)}</li>`),
    ...result.vehicles.map((v) => `<li><b>${esc(v.name)}</b> → ${v.tenant ? `Fahrzeug von ${owner(v.tenant)}`
      : v.block ? `geführt bei <b>${esc(v.block.tenant)}</b> im Block ${esc(v.block.call_sign)}` : `Fahrzeug von ${owner(null)}`}${v.description ? `<br><span class="small muted">${esc(v.description)}</span>` : ""}</li>`),
  ] : [];
  return `<p class="small muted">Kennung der VG und Standort jeder Wehr ergeben die Einheit in der Kopfzeile des Berichts (z. B. „FW NR#.ABC 02“) und die Funkrufnamen ihrer Fahrzeuge. Das Testfeld zeigt, welcher Wehr die App einen Bericht bzw. ein Fahrzeug zuordnet (gespeicherter Stand).</p>
    <div class="form-grid">
      ${adminField("Kennung der VG", textInput("bks_code", d.bks_code || "", 'placeholder="NR#.ABC" spellcheck="false"'), "span-2")}
      ${adminField("FEZ-Kennung", textInput("control_center", d.control_center, 'spellcheck="false"'), "span-2")}
    </div>
    <div class="table-wrap section-gap"><table class="mini-table admin-table"><thead><tr><th>Wehr</th><th>Standort</th><th>Einheit im Bericht</th></tr></thead><tbody>${rows}</tbody></table></div>
    ${overridesNote("bks_code", "control_center")}
    ${parseTestField()}
    ${parseResultList(items)}
    <h3 class="section-gap">Einsatznummern</h3>
    <div class="form-grid">${adminField("Nummerierung", numberingOptions(d.numbering, "numbering"), "span-3")}</div>
    <p class="small muted">${NUMBERING_HINT}</p>
    ${overridesNote("numbering")}
    ${saveButton()}`;
}

// ------------------------------------------------------------ Orte und Zeitgrenzen
const levelOptions = (current) => [1, 2, 3, 4].map((v) => `<option ${v === current ? "selected" : ""}>${v}</option>`).join("");

function planFields(d) {
  return `<div class="form-grid">
      ${adminField("ab Alarmstufe", `<select data-bind="plan_min_level" data-number>${levelOptions(d.plan_min_level)}</select>`)}
      ${adminField("Zeitgrenzen (Min.)", `<input type="text" data-limits value="${esc(d.response_limits.join(", "))}" placeholder="8, 10">`)}
      ${adminField("Standard", `<select data-bind="default_limit" data-number>${d.response_limits.map((v) => `<option ${v === d.default_limit ? "selected" : ""}>${v}</option>`).join("")}</select>`)}
      ${adminField("Zweite Grenze (Min.)", `<input type="number" min="1" max="120" data-bind="second_limit" value="${d.second_limit}">`)}
      ${adminField("Tag ab (Uhr)", `<input type="number" min="0" max="23" data-bind="day_hours.0" value="${d.day_hours[0]}">`)}
      ${adminField("Tag bis (Uhr)", `<input type="number" min="1" max="24" data-bind="day_hours.1" value="${d.day_hours[1]}">`)}
    </div>`;
}

const PLAN_KEYS = ["plan_min_level", "response_limits", "default_limit", "second_limit", "day_hours"];

function placesSection() {
  const s = admin.settings;
  const rows = s.places.map((p, i) => `<tr>
    <td>${textInput(`places.${i}.name`, p.name, 'placeholder="Musterstadt"')}</td>
    <td class="center"><input type="checkbox" data-plan-place="${i}" ${s.plan_places.includes(p.name) ? "checked" : ""} aria-label="Zählt zum Ausrückebereich"></td>
    <td><button type="button" class="icon-button" data-admin-action="remove-place" data-index="${i}" aria-label="entfernen">✕</button></td>
  </tr>`).join("");
  return `<p class="small muted">Das Einsatzgebiet ist der Ort, mit dessen Namen der Einsatzort beginnt (z. B. „Musterstadt-Nord“ → Musterstadt). Nur Orte mit Haken zählen zum Ausrückebereich der Auswertung „Eintreffen und verfügbare Kräfte“.</p>
    <h3 class="section-gap">Orte ${inheritNote("places")}</h3>
    <div class="table-wrap"><table class="mini-table admin-table"><thead><tr><th>Ort</th><th>Ausrückebereich</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
    <button type="button" class="btn btn-light btn-small section-gap" data-admin-action="add-place">Ort hinzufügen</button>
    <h3 class="section-gap">Zeitgrenzen und Tageszeit ${inheritNote(...PLAN_KEYS)}</h3>
    ${planFields(s)}
    ${adminGranted().includes("plan.release") ? `<label class="toggle section-gap"><input type="checkbox" data-bind="response_plan_public" ${s.response_plan_public ? "checked" : ""}>
      Eintreffen und Kräfte für alle Rollen freigeben <span class="muted">(sonst nur mit dem Recht „Eintreffen und Kräfte ohne Freigabe sehen“)</span></label>`
      : `<p class="small muted section-gap">Die Auswertung des Eintreffens ${s.response_plan_public ? "ist für alle Rollen freigegeben" : "ist nicht freigegeben"} – freigeben darf, wer das Recht „Eintreffen und Kräfte freigeben“ hat.</p>`}
    ${saveButton()}`;
}

function vgPlacesSection() {
  const d = admin.vgSettings;
  const ownPlaces = (t) => "places" in t.overrides;
  const head = d.tenants.map((t) => `<th class="center">${esc(t.name)}</th>`).join("");
  const rows = d.places.map((p, i) => `<tr>
    <td>${textInput(`places.${i}.name`, p.name, 'placeholder="Musterstadt"')}</td>
    ${d.tenants.map((t, j) => `<td class="center">${ownPlaces(t) ? '<span class="small muted">eigene Orte</span>'
      : `<input type="checkbox" data-plan-place="${j}:${i}" ${t.plan_places.includes(p.name) ? "checked" : ""} aria-label="${esc(p.name)} im Ausrückebereich von ${esc(t.name)}">`}</td>`).join("")}
    <td><button type="button" class="icon-button" data-admin-action="remove-place" data-index="${i}" aria-label="entfernen">✕</button></td>
  </tr>`).join("");
  return `<p class="small muted">Orte der VG für die Zuordnung des Einsatzgebiets (ein Einsatz gehört zu dem Ort, mit dessen Namen der Einsatzort beginnt). Die Haken je Wehr bilden ihren Ausrückebereich für die Auswertung „Eintreffen und verfügbare Kräfte“.</p>
    <div class="table-wrap"><table class="mini-table admin-table"><thead><tr><th>Ort</th>${head}<th></th></tr></thead><tbody>${rows}</tbody></table></div>
    <button type="button" class="btn btn-light btn-small section-gap" data-admin-action="add-place">Ort hinzufügen</button>
    ${overridesNote("places")}
    <h3 class="section-gap">Zeitgrenzen und Tageszeit</h3>
    ${planFields(d)}
    ${overridesNote(...PLAN_KEYS)}
    ${saveButton()}`;
}

// ------------------------------------------------------------ Stichworte
// Herkunft eines Stichworts in einer Wehr: aus dem Katalog der VG, dort geändert bzw. „gilt hier nicht“, eigenes
function keywordSource(x) {
  if (x.source === "own") return '<span class="inherit-badge own">eigenes</span>';
  if (x.source === "changed") return `<span class="inherit-badge own">${x.active ? "geändert" : "gilt hier nicht"}</span>`;
  return '<span class="inherit-badge">von der VG</span>';
}

// Abweichungen der Wehren je Stichwort (Katalog der VG)
function keywordDeviations(code) {
  const kinds = { off: "gilt nicht", changed: "geändert", own: "eigenes" };
  return (admin.keywords.deviations?.[code] || []).map((d) => `${esc(d.tenant)}: ${kinds[d.kind]}`).join("<br>");
}

function keywordsSection() {
  const k = admin.keywords;
  const query = fold(admin.keywordQuery);
  const deviates = (x) => admin.vg ? Boolean(k.deviations?.[x.code]) : x.source !== "vg";
  const list = k.keywords.filter((x) => (!query || fold(`${x.code} ${x.name} ${x.terms}`).includes(query))
    && (!admin.keywordDeviationsOnly || deviates(x)));
  const edit = admin.keywordEdit || { code: "", name: "", terms: "" };
  const preview = admin.importPreview;
  const deviating = k.keywords.filter((x) => x.source !== "vg").length;
  const status = admin.vg
    ? `<span class="tenant-badge">${k.custom ? "Katalog der VG" : "Vorlage (AAO)"}</span>
      <span class="small muted">${k.keywords.length} Stichworte für alle Wehren${k.custom && k.template_missing ? ` · ${k.template_missing} der Vorlage fehlen` : ""}${k.tenant_only?.length ? ` · eigene Stichworte einzelner Wehren: ${k.tenant_only.map(esc).join(", ")}` : ""}</span>`
    : `<span class="tenant-badge">${deviating ? `${deviating} Abweichungen von der VG` : "wie die VG"}</span>
      <span class="small muted">${k.keywords.filter((x) => x.active).length} Stichworte gelten hier</span>`;
  const reset = admin.vg ? (k.custom ? "Zurück zur Vorlage" : "") : (deviating ? "Alle Abweichungen aufheben" : "");
  // Löschen: in der VG und bei eigenen Stichworten; eine Abweichung aufheben; ein Stichwort der VG nur abschalten
  const removeButton = (x) => admin.vg || x.source === "own"
    ? `<button type="button" class="icon-button" data-admin-action="keyword-delete" data-code="${esc(x.code)}" aria-label="löschen">✕</button>`
    : x.source === "changed" ? `<button type="button" class="icon-button" data-admin-action="keyword-delete" data-code="${esc(x.code)}" aria-label="wie bei der VG" title="Wie bei der VG">↺</button>` : "";
  return `<div class="admin-status">
      ${status}
      <span class="toolbar-right">
        ${k.custom && k.template_missing ? `<button type="button" class="btn btn-light btn-small" data-admin-action="keywords-template">Fehlende aus der Vorlage ergänzen</button>` : ""}
        ${reset ? `<button type="button" class="btn btn-outline btn-small" data-admin-action="keywords-reset">${reset}</button>` : ""}
      </span>
    </div>
    <h3 class="section-gap">${edit.code && k.keywords.some((x) => x.code === edit.code) ? "Stichwort ändern" : "Stichwort hinzufügen"}</h3>
    <div class="form-grid">
      ${adminField("Stichwort", `<input type="text" id="keyword-code" value="${esc(edit.code)}" placeholder="B2.07" maxlength="5">`)}
      ${adminField("Bezeichnung", `<input type="text" id="keyword-name" value="${esc(edit.name)}" maxlength="120">`, "span-2")}
      ${adminField("Suchbegriffe (Meldebilder)", `<input type="text" id="keyword-terms" value="${esc(edit.terms)}" placeholder="durch Komma getrennt">`, "span-3")}
    </div>
    <div class="admin-actions left"><button type="button" class="btn btn-primary btn-small" data-admin-action="keyword-save">Stichwort speichern</button>
      ${admin.keywordEdit ? `<button type="button" class="btn btn-outline btn-small" data-admin-action="keyword-cancel">Abbrechen</button>` : ""}</div>
    <h3 class="section-gap">Katalog</h3>
    <div class="admin-status"><input type="search" class="search" data-keyword-search value="${esc(admin.keywordQuery)}" placeholder="Suchen: Stichwort, Bezeichnung, Meldebild …">
      <label class="toggle"><input type="checkbox" data-keyword-deviations ${admin.keywordDeviationsOnly ? "checked" : ""}>
        ${admin.vg ? "nur Stichworte, bei denen Wehren abweichen" : "nur Abweichungen von der VG"} (${k.keywords.filter(deviates).length})</label></div>
    <div class="table-wrap keyword-table"><table class="mini-table admin-table"><thead><tr><th>Stichwort</th><th>Bezeichnung</th><th>Suchbegriffe</th><th>${admin.vg ? "aktiv" : "gilt hier"}</th><th>${admin.vg ? "Wehren" : "Herkunft"}</th><th></th></tr></thead><tbody>
      ${list.map((x) => `<tr class="${x.active ? "" : "inactive"}"><td><b>${esc(x.code)}</b></td><td>${esc(x.name)}</td><td class="terms" title="${esc(x.terms)}">${esc(x.terms)}</td>
        <td class="center"><input type="checkbox" data-keyword-active="${esc(x.code)}" ${x.active ? "checked" : ""} aria-label="${admin.vg ? "aktiv" : "gilt hier"}"></td>
        <td class="small">${admin.vg ? keywordDeviations(x.code) : keywordSource(x)}</td>
        <td class="nowrap"><button type="button" class="icon-button" data-admin-action="keyword-edit" data-code="${esc(x.code)}" aria-label="bearbeiten">✎</button>${removeButton(x)}</td></tr>`).join("")}
    </tbody></table></div>
    <h3 class="section-gap">Import aus Datei</h3>
    <p class="small muted">CSV (Semikolon oder Komma) oder Excel mit den Spalten Stichwort, Bezeichnung, Suchbegriffe; eine Kopfzeile ist erlaubt.${admin.vg ? "" : " Stichworte der VG, die in der Datei fehlen, gelten nach „Katalog ersetzen“ in dieser Wehr nicht."}</p>
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

// Filter der Benutzerliste: alle, eine VG (mit ihren Wehren) oder eine Wehr
function userFilterMatches(m, filter) {
  if (!filter) return true;
  const [scope, slug] = filter.split(":");
  return scope === "vg" ? m.vg === slug : m.scope === "tenant" && m.slug === slug;
}

function userFilterOptions(memberships) {
  const vgs = new Map(), tenants = new Map();
  memberships.forEach((m) => {
    if (m.scope === "vg") vgs.set(m.slug, m.name); else tenants.set(m.slug, { name: m.name, vg: m.vg });
    if (m.vg && !vgs.has(m.vg)) vgs.set(m.vg, m.vg);
  });
  const known = Object.fromEntries((admin.overview?.vgs || []).map((v) => [v.slug, v.name]));
  return [...vgs.entries()].map(([slug, name]) => ({ slug, name: known[slug] || name, tenants: [...tenants.entries()].filter(([, t]) => t.vg === slug) }))
    .sort((a, b) => a.name.localeCompare(b.name, "de"));
}

function usersSection() {
  const scopes = admin.userScopes;
  const filterOptions = userFilterOptions(admin.memberships);
  const filter = filterOptions.length > 1 ? `<label class="field admin-tenant"><span>Anzeigen</span><select data-user-filter>
      <option value="">Alle Bereiche</option>${filterOptions.map((g) => `<optgroup label="${esc(g.name)}">
        <option value="vg:${esc(g.slug)}" ${admin.userFilter === `vg:${g.slug}` ? "selected" : ""}>Gesamte VG mit allen Wehren</option>
        ${g.tenants.map(([slug, t]) => `<option value="tenant:${esc(slug)}" ${admin.userFilter === `tenant:${slug}` ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</optgroup>`).join("")}</select></label>` : "";
  const rows = admin.memberships.filter((m) => userFilterMatches(m, admin.userFilter)).map((m) => `<tr>
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
    ihre Rechte addieren sich. Eigene Zuordnungen ändert jemand anderes.</p>
    <div class="section-gap">${form}</div>
    ${filter ? `<div class="section-gap">${filter}</div>` : ""}
    <div class="table-wrap section-gap"><table class="mini-table admin-table"><thead><tr><th>E-Mail</th><th>Bereich</th><th>Rolle</th><th>zuletzt angemeldet</th><th></th></tr></thead>
    <tbody>${rows || `<tr><td colspan="5" class="muted">Noch keine Zuordnungen.</td></tr>`}</tbody></table></div>
    ${admin.effective ? effectivePanel() : ""}
    <h3 class="section-gap">Protokoll</h3>
    ${admin.events ? eventsTable() : `<button type="button" class="btn btn-light btn-small" data-admin-action="events">Protokoll anzeigen</button>`}`;
}

function effectivePanel() {
  const e = admin.effective;
  const areas = e.areas.map((a) => `<h4 class="section-gap">${esc(a.name)}</h4>
    <div class="table-wrap"><table class="mini-table admin-table"><thead><tr><th>Recht</th><th>über</th></tr></thead><tbody>
    ${a.permissions.map((p) => `<tr><td>${esc(p.label)}</td><td class="small muted">${p.from.map(esc).join(", ")}</td></tr>`).join("")}
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
    return `${groupRow}<tr><td>${esc(p.label)}</td>${cells}</tr>`;
  }).join("");
  const users = `<tr class="group-row"><th colspan="${roles.length + 1}">Zuordnungen</th></tr>
    <tr><td>Personen mit dieser Rolle</td>${roles.map((r) => `<td class="center">${r.members}</td>`).join("")}</tr>`;
  return `<p class="small muted">● eigenes Recht, ○ geerbt. Rollen eines Bereichs „VG“ gelten in allen Wehren der VG.
    Rechte, Vererbung und wer eine Rolle vergeben darf, stehen im Editor (Klick auf den Namen).</p>
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
      ${checked ? "checked" : ""} ${wrongScope || fromParent || readOnly ? "disabled" : ""}> ${esc(p.label)}
      ${note ? `<span class="small muted">${esc(note)}</span>` : ""}</label>`;
  }).join("");
  const granters = others.filter((r) => r.effective.includes("users.grant"));
  const grantable = others.filter((r) => d.vg !== null || r.vg === null);
  const roleChecks = (list, field) => list.map((r) => `<label class="check"><input type="checkbox" data-role-${field}="${r.id}"
    ${d[field].includes(r.id) ? "checked" : ""} ${disabled}> ${esc(r.label)} <span class="small muted">${admin.roles.scopes[r.scope]}</span></label>`).join("")
    || `<span class="small muted">keine</span>`;
  return `<div class="role-editor section-gap">
    <h3>${d.id === null ? "Neue Rolle" : esc(d.label)}
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
    <h4 class="section-gap">Verteilung</h4>
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
const VG_KINDS = { vg: "Verbandsgemeinde / verbandsfrei", city: "Kreisfreie Stadt", district: "Landkreis", dispatch: "Leitstelle" };
const kindOptions = (current) => Object.entries(VG_KINDS).map(([k, label]) => `<option value="${k}" ${k === current ? "selected" : ""}>${label}</option>`).join("");

const DPA_LABELS = { pending: "ausstehend", draft: "ausgefüllt", signed: "liegt vor", revoked: "zurückgenommen", not_required: "nicht erforderlich" };

// VGs mit ihren Wehren; die Suche trifft Name oder Kurzname von VG und Wehr (eine VG bleibt, wenn eine ihrer Wehren trifft)
function superGroups(overview, query = "") {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const hit = (...texts) => words.every((w) => texts.some((t) => String(t).toLowerCase().includes(w)));
  return overview.vgs.map((v) => {
    const all = overview.tenants.filter((t) => t.vg === v.slug);
    const vgHit = hit(v.name, v.slug);
    return { vg: v, tenants: all, shown: !words.length || vgHit || all.some((t) => hit(t.name, t.slug)),
      matches: words.length && !vgHit ? all.filter((t) => hit(t.name, t.slug)).map((t) => t.slug) : [] };
  }).filter((g) => g.shown);
}

function superSelected(overview) {
  return overview.vgs.find((v) => v.slug === admin.superVg) || overview.vgs[0] || null;
}

function superListHtml() {
  const groups = superGroups(admin.superOverview, admin.superQuery);
  const current = superSelected(admin.superOverview)?.slug;
  return groups.map(({ vg, tenants, matches }) => `<button type="button" class="super-vg ${vg.slug === current ? "active" : ""}" data-super-vg="${esc(vg.slug)}">
      <strong>${esc(vg.name)}</strong>
      <span class="small muted">${esc(VG_KINDS[vg.kind] || "")} · ${plural(tenants.length, "Wehr", "Wehren")}${tenants.some((t) => !t.active) ? ` · ${tenants.filter((t) => !t.active).length} inaktiv` : ""}</span>
      ${vg.blocked ? `<span class="tenant-badge dpa-${vg.dpa}">AVV ${DPA_LABELS[vg.dpa]}: gesperrt</span>` : ""}
      ${matches.length ? `<span class="small">Treffer: ${matches.map(esc).join(", ")}</span>` : ""}</button>`).join("")
    || `<p class="muted small">Nichts gefunden.</p>`;
}

function superDetail(vg) {
  const { tenants, pending_archives: pending } = admin.superOverview;
  const mine = tenants.filter((t) => t.vg === vg.slug);
  const vgOptions = (current) => admin.superOverview.vgs.map((v) => `<option value="${esc(v.slug)}" ${v.slug === current ? "selected" : ""}>${esc(v.name)}</option>`).join("");
  const scopes = new Set([`vg:${vg.slug}`, ...mine.map((t) => `tenant:${t.slug}`)]);
  const access = (admin.memberships || []).filter((m) => scopes.has(`${m.scope}:${m.slug}`));
  const open = (pending || []).filter((slug) => mine.some((t) => t.slug === slug));
  return `${open.length ? `<div class="message message-info">Archivierung noch offen: ${open.map(esc).join(", ")}. Die Wehren sind gesperrt; automatische Wiederholung jede Minute.</div>` : ""}
    <h3>${esc(vg.name)}</h3>
    ${vg.blocked ? `<div class="message message-info">Auftragsverarbeitung (AVV) ${DPA_LABELS[vg.dpa]}: Die Wehren dieser VG sind für alle außer Superadmins gesperrt. <a href="#dpa">Zum Vertrag</a></div>` : ""}
    <div class="form-grid">
      ${adminField("Name", `<input type="text" data-vg-name="${esc(vg.slug)}" value="${esc(vg.name)}">`, "span-2")}
      ${adminField("Art", `<select data-vg-kind="${esc(vg.slug)}">${kindOptions(vg.kind)}</select>`)}
      <div class="field"><span>AVV</span><a href="#dpa" class="tenant-badge dpa-${vg.dpa}">${DPA_LABELS[vg.dpa]}</a></div>
      <div class="field"><span>&nbsp;</span><button type="button" class="btn btn-outline" data-admin-action="rename-vg" data-slug="${esc(vg.slug)}">Speichern</button></div>
    </div>
    <h3 class="section-gap">Wehren (${mine.length})</h3>
    <div class="table-wrap"><table class="mini-table admin-table"><thead><tr><th>Name</th><th class="right">Einsätze</th><th>aktiv</th><th></th></tr></thead><tbody>
      ${mine.map((t) => `<tr class="${t.active ? "" : "inactive"}"><td>${esc(t.name)}</td><td class="right">${t.incidents ?? "–"}</td>
        <td class="center"><input type="checkbox" data-tenant-active="${esc(t.slug)}" ${t.active ? "checked" : ""} aria-label="aktiv"></td>
        <td class="admin-actions"><button type="button" class="btn btn-outline btn-small" data-admin-action="move-tenant" data-slug="${esc(t.slug)}">Verschieben …</button>
          <button type="button" class="btn btn-outline btn-small" data-admin-action="delete-tenant" data-slug="${esc(t.slug)}">Archivieren</button></td></tr>`).join("")
        || `<tr><td colspan="4" class="muted">Noch keine Wehr in dieser VG.</td></tr>`}
    </tbody></table></div>
    <div class="form-grid section-gap">
      ${adminField("Name", `<input type="text" id="tenant-name" placeholder="Feuerwehr Musterstadt">`, "span-2")}
      ${adminField("Erster Wehrführer (E-Mail, optional)", `<input type="email" id="tenant-email">`, "span-2")}
      <input type="hidden" id="tenant-vg" value="${esc(vg.slug)}">
    </div>
    <div class="admin-actions left"><button type="button" class="btn btn-primary" data-admin-action="create-tenant">Wehr in dieser VG anlegen</button></div>
    <h3 class="section-gap">Zugriff</h3>
    <div class="table-wrap"><table class="mini-table admin-table"><thead><tr><th>Person</th><th>Bereich</th><th>Rolle</th></tr></thead><tbody>
      ${access.map((m) => `<tr><td>${esc(m.email)}</td><td>${esc(m.name)}</td><td>${esc(m.label)}</td></tr>`).join("")
        || `<tr><td colspan="3" class="muted">Keine Zuordnungen.</td></tr>`}
    </tbody></table></div>
    <p class="small muted">Rollen vergeben und entziehen unter <button type="button" class="btn-link" data-admin-section="users">Benutzer</button>.
    Archivierte Wehren werden nicht gelöscht, sondern im Datenordner unter <code>deleted/</code> abgelegt.</p>`;
}

function superSection() {
  const vg = superSelected(admin.superOverview);
  return `<div class="super-layout">
    <aside class="super-side">
      <input type="search" class="search" data-super-search value="${esc(admin.superQuery)}" placeholder="VG oder Wehr suchen …" aria-label="VG oder Wehr suchen">
      <div id="super-list" class="super-list">${superListHtml()}</div>
      <details class="section-gap" ${admin.superOverview.vgs.length ? "" : "open"}><summary class="btn btn-light btn-small">+ VG anlegen</summary>
        <div class="form-grid">
          ${adminField("Name", `<input type="text" id="vg-name" placeholder="VG Musterstadt">`)}
          ${adminField("Art", `<select id="vg-kind">${kindOptions("vg")}</select>`)}
          <div class="field"><button type="button" class="btn btn-light" data-admin-action="create-vg">VG anlegen</button></div>
        </div>
        <p class="small muted">Neue VGs starten mit „AVV ausstehend“: Ihre Wehren sind gesperrt, bis der Vertrag unter „Auftragsverarbeitung“ bestätigt ist.</p></details>
    </aside>
    <section class="super-detail">${vg ? superDetail(vg) : `<p class="muted">Lege links die erste Verbandsgemeinde an.</p>`}</section>
  </div>`;
}

// ------------------------------------------------------------ Superadmin: Sitzungen
const sessionTime = (seconds) => {
  const d = new Date(seconds * 1000);
  return `${formatDate(d.toISOString().slice(0, 10))} ${d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}`;
};

// Browser und System grob aus dem User-Agent, sonst der gekürzte Text
function browserLabel(agent) {
  if (!agent) return "–";
  const browser = /Edg\//.test(agent) ? "Edge" : /OPR\//.test(agent) ? "Opera" : /Firefox\//.test(agent) ? "Firefox"
    : /Chrome\//.test(agent) ? "Chrome" : /Safari\//.test(agent) ? "Safari" : null;
  const system = /Windows/.test(agent) ? "Windows" : /Android/.test(agent) ? "Android" : /iPhone|iPad/.test(agent) ? "iOS"
    : /Mac OS X/.test(agent) ? "macOS" : /Linux/.test(agent) ? "Linux" : null;
  return browser ? [browser, system].filter(Boolean).join(" · ") : agent.slice(0, 40);
}

function sessionsSection() {
  const { enabled, sessions } = admin.sessions;
  if (!enabled) return `<p class="muted">Die Anmeldung ist nicht eingeschaltet (ADMIN_EMAILS), daher gibt es keine Sitzungen.</p>`;
  const perEmail = {};
  sessions.forEach((x) => { perEmail[x.email] = (perEmail[x.email] || 0) + 1; });
  const rows = sessions.map((x) => `<tr class="${x.current ? "current" : ""}"><td>${esc(x.email)}${x.current ? ` <span class="tenant-badge">diese Sitzung</span>` : ""}</td>
    <td>${esc(browserLabel(x.user_agent))}</td><td>${sessionTime(x.created)}</td><td>${sessionTime(x.last_seen)}</td><td>${sessionTime(x.expires)}</td>
    <td class="right">${x.current ? "" : `<button type="button" class="btn btn-outline btn-small" data-admin-action="session-end" data-id="${x.id}" data-email="${esc(x.email)}">Abmelden</button>`}
      ${perEmail[x.email] > 1 && !x.current ? `<button type="button" class="btn btn-light btn-small" data-admin-action="sessions-user" data-email="${esc(x.email)}">Alle dieser Person</button>` : ""}</td></tr>`).join("");
  return `<h3>Angemeldete Sitzungen</h3>
    <div class="table-wrap"><table class="mini-table admin-table"><thead><tr><th>Benutzer</th><th>Browser</th><th>Angemeldet</th><th>Zuletzt aktiv</th><th>Läuft ab</th><th></th></tr></thead>
      <tbody>${rows || `<tr><td colspan="6" class="muted">Keine Sitzungen.</td></tr>`}</tbody></table></div>
    <div class="admin-actions left"><button type="button" class="btn btn-outline" data-admin-action="sessions-others" ${sessions.some((x) => !x.current) ? "" : "disabled"}>Alle anderen abmelden</button></div>
    <p class="small muted">Eine beendete Sitzung ist sofort ungültig, auch ein kopiertes Cookie. Die Person kann sich mit einem neuen Anmeldelink wieder anmelden.
    Wer den Zugang ganz verlieren soll, dem entziehst du die Zuordnung unter „Benutzer“. „Zuletzt aktiv“ wird auf etwa 5 Minuten genau geführt.</p>`;
}
