"use strict";

// Darstellung der Verwaltungsbereiche; Zustand und Aktionen liegen in admin.js.

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
// Zuordnung eines erkannten Fahrzeugs: zuerst über den Funkrufnamen der Fahrzeugliste, sonst über die Präfixe
function fleetMatch(v) {
  const listed = admin.settings.fleet.find((x) => x.name && x.name === v.name);
  if (listed) return `<b>eigenes Fahrzeug</b> (Fahrzeugliste, Block ${esc(listed.call_sign || listed.name)})`;
  if (v.own) return `<b>eigenes Fahrzeug</b> (Block ${esc(v.call_sign)}, noch nicht in der Fahrzeugliste)`;
  if (v.call_sign) return "Fahrzeug einer anderen Wehr der VG";
  return "fremdes Fahrzeug";
}

// Präfixe wie admin.prefixes_of: „FW NR#.ABC 02“ -> „FL NR#.ABC “ und „02/“; ohne Einheit die gespeicherten
function bksPrefixes(s) {
  const m = /^FW (\S+) (\d\d)$/.exec((s.unit_marker || "").trim());
  return m ? { unit: `FL ${m[1]} `, own: `${m[2]}/`, valid: true }
    : { unit: s.unit_prefix, own: s.own_prefix, valid: !(s.unit_marker || "").trim() };
}

function bksDerived(s) {
  const p = bksPrefixes(s);
  if (!p.valid) return `<span class="message-error">Bitte wie in der Kopfzeile des Berichts angeben, z. B. FW NR#.ABC 02.</span>`;
  if (!p.unit) return "Ohne Einheit zählen nur die Fahrzeuge der Fahrzeugliste als eigene.";
  return `Eigene Fahrzeuge beginnen mit <b>${esc(p.unit + p.own)}</b>, Fahrzeuge der übrigen Wehren der VG mit <b>${esc(p.unit)}</b>. Fahrzeuge der Fahrzeugliste zählen immer als eigene.`;
}

function bksSection() {
  const s = admin.settings;
  const result = admin.parseResult;
  const items = result ? [
    ...result.units.map((u) => `<li><b>${esc(u.unit)}</b> → ${u.own ? "<b>Bericht dieser Wehr</b>" : "Bericht einer anderen Einheit"}</li>`),
    ...result.vehicles.map((v) => `<li><b>${esc(v.name)}</b> → ${fleetMatch(v)}${v.description ? `<br><span class="small muted">${esc(v.description)}</span>` : ""}</li>`),
  ] : [];
  const found = result ? (items.length ? `<ul class="plain-list">${items.join("")}</ul>`
    : `<p class="message message-error">Kein Funkrufname (z. B. FL NR#.ABC 02/45-01) und keine Einheit (z. B. FW NR#.ABC 02) gefunden.</p>`) : "";
  return `<p class="small muted">So erkennt die App im Einsatzbericht des BKS-Portals, von welcher Wehr ein Bericht stammt und welche Fahrzeuge dazugehören.${helpButton("admin_bks")}</p>
    <div class="form-grid">
      ${adminField("Einheit im Bericht", textInput("unit_marker", s.unit_marker, 'placeholder="FW NR#.ABC 02" spellcheck="false"'), "span-2")}
      ${adminField("FEZ-Kennung", textInput("control_center", s.control_center, 'spellcheck="false"'))}
    </div>
    <p class="small muted" id="bks-derived">${bksDerived(s)}</p>
    <h3 class="section-gap">Testen</h3>
    <label class="field"><span>Text aus einem Bericht</span>
      <textarea rows="4" id="parse-line" spellcheck="false" placeholder="Funkrufnamen, Zeilen der Fahrzeugtabelle oder den ganzen Berichtstext einfügen, z. B. FL NR#.ABC 02/45-01"></textarea></label>
    <button type="button" class="btn btn-light btn-small section-gap" data-admin-action="parse-test">Erkennung prüfen</button>
    ${found}
    <h3 class="section-gap">Einsatznummern</h3>
    <div class="form-grid">
      ${adminField("Nummerierung", `<select data-bind="numbering">
        <option value="bks" ${s.numbering === "bks" ? "selected" : ""}>aus dem Bericht (fehlt sie: nächste freie)</option>
        <option value="by_date" ${s.numbering === "by_date" ? "selected" : ""}>nach Datum durchnummerieren</option></select>`, "span-3")}
    </div>
    <p class="small muted">Nach Datum: Die App nummeriert alle Einsätze eines Jahres nach dem Beginn; ein später eingelesener Einsatz (z. B. eine selbst angelegte Brandsicherheitswache) rückt an seine Stelle, die folgenden Nummern verschieben sich. Beim Speichern werden alle Jahre neu nummeriert.</p>
    ${saveButton()}`;
}

// ------------------------------------------------------------ Orte und Bedarfsplan
function placesSection() {
  const s = admin.settings;
  const rows = s.places.map((p, i) => `<tr>
    <td>${textInput(`places.${i}.name`, p.name, 'placeholder="Musterstadt"')}</td>
    <td class="center"><input type="checkbox" data-plan-place="${i}" ${s.plan_places.includes(p.name) ? "checked" : ""} aria-label="Bedarfsplan"></td>
    <td><button type="button" class="icon-button" data-admin-action="remove-place" data-index="${i}" aria-label="entfernen">✕</button></td>
  </tr>`).join("");
  const options = (values, current) => values.map((v) => `<option ${v === current ? "selected" : ""}>${v}</option>`).join("");
  return `<p class="small muted">Das Einsatzgebiet ist der Ort, mit dessen Namen der Einsatzort beginnt (z. B. „Musterstadt-Nord“ → Musterstadt). Nur Orte mit Haken zählen zum Ausrückebereich des Feuerwehrbedarfsplans.${helpButton("admin_places")}</p>
    <div class="table-wrap"><table class="mini-table admin-table"><thead><tr><th>Ort</th><th>Bedarfsplan</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
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
  return `${admin.superOverview.pending_archives?.length ? `<div class="message message-info">Archivierung noch offen: ${admin.superOverview.pending_archives.map(esc).join(", ")}. Die Wehren sind gesperrt; automatische Wiederholung jede Minute. Daten und Zuordnungen bleiben bis zur erfolgreichen Sicherung erhalten.</div>` : ""}<h3>Verbandsgemeinden</h3>
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
        <td><select data-tenant-vg="${esc(t.slug)}">${vgOptions(t.vg)}</select></td><td class="right">${t.incidents ?? "–"}</td>
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
