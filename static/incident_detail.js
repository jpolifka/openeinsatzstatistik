// Einsatz: Detailansicht, Bearbeiten, Ungespeicherte Änderungen, Löschen mit „Rückgängig“. Wird vor app.js geladen.

function vehicleTable(e) {
  const limit = config.default_limit;
  return `<div class="table-wrap"><table class="mini-table"><thead><tr>
    <th>Fzg.</th><th class="right">Stärke</th><th>Ausrücken</th><th class="right">Ausrückdauer</th><th>Eintreffen</th><th class="right">Zeit bis Eintreffen</th></tr></thead>
    <tbody>${e.vehicles.map((v) => isIdle(v)
      ? `<tr class="vehicle-idle"><td>${esc(v.call_sign)}</td><td colspan="5">nicht im Einsatz</td></tr>`
      : `<tr><td><strong>${esc(v.call_sign)}</strong>${v.substitute ? `<br><span class="small muted">${esc(v.substitute)}</span>` : ""}${v.deployed === 0 ? `<br><span class="small muted">nur bereitgestellt</span>` : ""}</td>
        <td class="right">${orDash(v.crew)}${v.respiratory ? `<br><span class="small muted">${v.respiratory} AGT</span>` : ""}</td><td>${formatTime(v.departed)}</td><td class="right minutes">${num(v.turnout_min)}</td>
        <td>${formatTime(v.arrived)}</td><td class="right minutes ${v.arrival_min != null && v.arrival_min > limit ? "late" : ""}">${num(v.arrival_min)}${v.arrival_min != null && v.arrival_min > limit ? lateMark(true, limit) : ""}</td></tr>`).join("")}
    </tbody></table></div>`;
}

// pickLeader: Namen sind Knöpfe, ein Klick trägt die Person als Einheitsführung ins Formular ein
function peopleChips(e, { markNew = false, pickLeader = false } = {}) {
  return e.people.map((p) => {
    const isLeader = e.unit_leader ? p.leader : /Einheitsführer/.test(p.role || "");
    const cls = [markNew && p.new && "new", isLeader && "leader"].filter(Boolean).join(" ");
    const tip = [p.role, p.vehicle, p.agt && `Atemschutz${p.agt_min ? ` ${p.agt_min} min` : ""}`, markNew && p.new && "wird als neue Person angelegt",
      pickLeader && `Klicken: als Einheitsführung eintragen (${p.leader_name})`].filter(Boolean).join(" · ");
    const content = `${esc(p.name)}${p.vehicle ? `<small>${esc(p.vehicle)}</small>` : ""}`;
    const attributes = `class="person ${cls}" ${tip ? `data-tip="${esc(tip)}"` : ""}`;
    return pickLeader
      ? `<button type="button" ${attributes} data-leader="${esc(p.leader_name)}">${content}</button>`
      : `<span ${attributes}>${content}</span>`;
  }).join("") || `<span class="muted">Keine Anwesenheit erfasst</span>`;
}

/** Einheitsführung aus einem angeklickten Namen übernehmen und die Hervorhebung nachziehen. */
function pickLeader(chip) {
  const form = chip.closest("[data-form], .preview-card");
  const input = $('input[name="unit_leader"]', form);
  input.value = chip.dataset.leader;
  input.classList.remove("missing");
  highlightLeader(form);
}

function highlightLeader(form) {
  const leader = $('input[name="unit_leader"]', form).value.trim();
  for (const chip of $$("[data-leader]", form)) chip.classList.toggle("leader", !!leader && chip.dataset.leader === leader);
}

function warningsList(warnings, emptyText = "") {
  if (!warnings.length && !emptyText) return "";
  const items = warnings.length ? warnings.map((w) => `<li>${esc(w)}</li>`).join("") : `<li class="ok">${emptyText}</li>`;
  return `<ul class="warnings">${items}</ul>`;
}

function attendancePanel(e, options = {}) {
  // Ohne Recht auf Anwesenheit (z. B. Wehrleiter) nur die Anzahl
  if (!e.people_visible) {
    return `<h4>Anwesenheit · ${e.people_count} Personen${helpButton("attendance")}</h4>
      <p class="small muted">Die Namen sehen nur Rollen der Wehr mit Recht auf die Anwesenheit (z. B. Wehrführer, Erfasser).</p>`;
  }
  const newCount = options.markNew ? e.people.filter((p) => p.new).length : 0;
  const hint = options.pickLeader && e.people.length ? `<p class="small muted">Einen Namen anklicken, um die Person als Einheitsführung einzutragen.</p>` : "";
  return `<h4>Anwesenheit · ${e.people.length} Personen${newCount ? ` · ${newCount} neu` : ""}${helpButton("attendance")}</h4>
    ${hint}<div class="people">${peopleChips(e, options)}</div>`;
}

// Weitere Angaben aus dem BKS-Bericht (Abbruch, Objekt, Brandverlauf, Rettung) – nur was angegeben ist
function reportDetailsPanel(e) {
  const stamp = (iso) => iso ? `${formatDate(iso)} ${formatTime(iso)}` : null;
  const count = (n) => n == null ? null : String(n);
  const rows = [
    ["Einsatzabbruch", "abort_reason", e.abort_reason], ["Objekt", "building", e.building], ["Brandmelde-Nr.", "alarm_system", e.alarm_system],
    ["Einsatztaktik", "tactic", e.tactic], ["Brand unter Kontrolle", "fire_controlled_at", stamp(e.fire_controlled_at)],
    ["Feuer aus", "fire_out_at", stamp(e.fire_out_at)], ["Brandwache bis", "fire_watch_until", stamp(e.fire_watch_until)],
    ["Menschen gerettet", "rescued", count(e.rescued)], ["Tiere gerettet", "rescued_animals", count(e.rescued_animals)],
    ["Verletzte", "injured", count(e.injured)], ["Verletzte Feuerwehrangehörige", "injured_firefighters", count(e.injured_firefighters)],
    ["Verstorbene", "deceased", count(e.deceased)],
  ].filter(([, , value]) => value != null && value !== "");
  if (!rows.length) return "";
  return `<div class="panel"><h4>Weitere Angaben</h4><dl class="facts">${rows.map(([label, key, value]) =>
    `<dt>${label}${helpButton(key)}</dt><dd>${esc(value)}</dd>`).join("")}</dl></div>`;
}

function incidentDetail(e) {
  const limit = config.default_limit;
  return `<div class="detail-grid">
    <div class="panel"><h4>Einsatz</h4><dl class="facts">
      <dt>Beginn</dt><dd>${formatDate(e.started_at)} ${formatTime(e.started_at)}</dd>
      <dt>Ende</dt><dd>${formatDate(e.ended_at)} ${formatTime(e.ended_at)}</dd>
      <dt>Dauer${helpButton("duration")}</dt><dd>${formatDuration(e.duration_min)}</dd>
      <dt>Zeitfenster${helpButton("time_window")}</dt><dd>${e.weekend_or_holiday ? "Sa/So/Feiertag" : "Werktag"}, ${e.daytime ? "Tag" : "Nacht"}</dd>
      <dt>Ort</dt><dd>${esc(e.place || "–")}</dd>
      ${e.people_visible !== false ? `<dt>Einheitsführung${helpButton("unit_leader")}</dt><dd>${esc(e.unit_leader || "–")}</dd>` : ""}
      <dt>Gerätehaus${helpButton("station_staff")}</dt><dd>${e.station_staff}</dd>
      <dt>Quelle</dt><dd class="small">${sourceLabel(e)}</dd>
      ${e.bks_url ? `<dt>BKS-Portal${helpButton("bks_url")}</dt><dd class="small">${bksLink(e)}</dd>` : ""}
    </dl></div>
    <div class="panel"><h4>Fahrzeuge${helpButton("vehicles")}</h4>${vehicleTable(e)}</div>
    ${reportDetailsPanel(e)}
    <div class="panel"><h4>Kennzahlen</h4><dl class="facts">
      <dt>Ausrückdauer${helpButton("turnout_min")}</dt><dd>${minutes(e.turnout_min)}</dd>
      <dt>Zeit bis Eintreffen${helpButton("arrival_min")}</dt><dd>${minutes(e.arrival_min)}</dd>
      <dt>${limit} Min. erreicht${helpButton("on_time")}</dt><dd>${e.on_time == null ? "–" : e.on_time ? "ja" : "nein"}</dd>
      <dt>Stärke Eintreffen${helpButton("crew_on_arrival")}</dt><dd>${orDash(e.crew_on_arrival)}</dd>
      <dt>zusätzlich bis ${limit} Min.${helpButton("crew_within_limit")}</dt><dd>${orDash(e.crew_within_limit)}</dd>
      <dt>zusätzlich ${limit}–${config.second_limit} Min.${helpButton("crew_within_second")}</dt><dd>${orDash(e.crew_within_second)}</dd>
      <dt>Gesamtstärke${helpButton("crew_total")}</dt><dd>${e.crew_total}</dd>
    </dl>
    <h4 class="section-gap">Aktueller Datenstand</h4>${warningsList(e.current_warnings || [], "Keine aktuellen Prüfhinweise")}
    ${e.warnings.length ? `<h4 class="section-gap">Hinweise beim Import${helpButton("warnings")}</h4><p class="small muted">Historische Hinweise aus dem Bericht; spätere Korrekturen sind hier nicht berücksichtigt.</p>${warningsList(e.warnings)}` : ""}
    </div>
    <div class="panel full">${attendancePanel(e)}</div>
    <div class="actions panel full bare">
      ${stepButtons(e)}
      ${e.can_delete ? `<button type="button" class="btn btn-outline btn-small" data-action="delete" data-id="${e.id}">Löschen</button>` : ""}
      ${e.can_edit ? `<button type="button" class="btn btn-light btn-small" data-action="edit" data-id="${e.id}" data-tip="Taste e">Bearbeiten</button>` : ""}
    </div>
  </div>`;
}


// Vorheriger / nächster Einsatz in der Reihenfolge der Liste (Tasten k / j)
function stepButtons(e) {
  const list = visibleIncidents(), i = list.findIndex((x) => x.id === e.id);
  const button = (delta, label, key) => `<button type="button" class="btn btn-light btn-small step" data-action="step" data-step="${delta}"
    data-id="${e.id}" data-tip="Taste ${key}" ${list[i + delta] ? "" : "disabled"}>${label}</button>`;
  return `<span class="step-buttons">${button(-1, "‹ Vorheriger", "k")}${button(1, "Nächster ›", "j")}</span>`;
}

let formSequence = 0;
function formFields(e) {
  const prefix = `incident-form-${++formSequence}`;
  // Einheitsführung ist ein Name: nur mit Recht auf die Anwesenheit (sonst bleibt der gespeicherte Wert)
  const fields = config.incident_fields.filter(([name]) => name !== "unit_leader" || e.people_visible !== false);
  return `<div class="form-grid">${fields.map(([name, title, type, span, attributes]) => {
    const value = type === "datetime-local" ? (e[name] || "").slice(0, 19) : e[name];
    const missing = name === "unit_leader" && !value;
    // Nummerierung nach Datum: die Nr. vergibt die App
    const extra = name === "number" && config.numbering === "by_date" ? ' readonly data-tip="Wird nach dem Einsatzbeginn vergeben"' : "";
    const id = `${prefix}-${name}`;
    return `<div class="field ${span}"><span><label for="${id}">${title}</label>${helpButton(name)}</span><input id="${id}" name="${name}" type="${type}" value="${esc(value ?? "")}" ${attributes}${extra}
      class="${missing ? "missing" : ""}"></div>`;
  }).join("")}</div>`;
}

function readForm(el) {
  const values = {};
  for (const input of $$("input[name]", el)) {
    values[input.name] = input.type === "number" ? (input.value === "" ? null : Number(input.value)) : input.value;
  }
  return values;
}

// Bearbeiten: Fahrzeuge direkt im Formular, Anwesenheit als Entwurf (state.editDraft) bis zum Speichern
function vehicleEditTable(e) {
  const time = (t) => t ? t.slice(0, 8) : "";   // mit Sekunden (step="1"), sonst ändern sich Ausrückdauer und Zeit bis Eintreffen
  return `<div class="table-wrap"><table class="mini-table vehicle-edit"><thead><tr>
    <th>Fzg.</th><th>dabei</th><th>Stärke</th><th>Ausrücken</th><th>Eintreffen</th></tr></thead>
    <tbody>${e.vehicles.map((v) => `<tr data-vehicle="${esc(v.call_sign)}">
      <td><strong>${esc(v.call_sign)}</strong></td>
      <td><input type="checkbox" data-v="present" ${isIdle(v) ? "" : "checked"} aria-label="${esc(v.call_sign)} im Einsatz"></td>
      <td><input type="number" min="0" max="99" data-v="crew" value="${v.crew ?? ""}" aria-label="Stärke ${esc(v.call_sign)}"></td>
      <td><input type="time" step="1" data-v="departed" value="${time(v.departed)}" aria-label="Ausrücken ${esc(v.call_sign)}"></td>
      <td><input type="time" step="1" data-v="arrived" value="${time(v.arrived)}" aria-label="Eintreffen ${esc(v.call_sign)}"></td>
    </tr>`).join("")}</tbody></table></div>`;
}

// "Nachname, Vorname" -> "V. Nachname" (Schreibweise für das Feld Einheitsführung)
function leaderSpelling(name) {
  const [last, first = ""] = name.split(",").map((part) => part.trim());
  return first ? `${first.charAt(0)}. ${last}` : last;
}

function peopleEditPanel() {
  const people = state.editDraft.people;
  const chips = people.map((p, i) => `<span class="person-edit">
      <button type="button" class="person" data-leader="${esc(p.leader_name)}" data-tip="${esc([p.role, p.vehicle, `Klicken: als Einheitsführung eintragen (${p.leader_name})`].filter(Boolean).join(" · "))}">${esc(p.name)}${p.vehicle ? `<small>${esc(p.vehicle)}</small>` : ""}</button>
      <button type="button" class="person-remove" data-action="remove-person" data-index="${i}" aria-label="${esc(p.name)} entfernen">×</button>
    </span>`).join("");
  return `<h4>Anwesenheit · ${people.length} Personen${helpButton("attendance")}</h4>
    <p class="small muted">Einen Namen anklicken, um die Person als Einheitsführung einzutragen; × entfernt sie aus dem Einsatz.</p>
    <div class="people">${chips || `<span class="muted">Keine Anwesenheit erfasst</span>`}</div>
    <div class="person-add">
      <input type="text" list="member-options" data-p="name" placeholder="Nachname, Vorname" aria-label="Person hinzufügen" autocomplete="off">
      <input type="text" data-p="role" placeholder="Funktion" aria-label="Funktion">
      <select data-p="vehicle" aria-label="Fahrzeug"><option value="">ohne Fahrzeug</option>
        ${config.vehicles.map((c) => `<option>${esc(c)}</option>`).join("")}</select>
      <button type="button" class="btn btn-light btn-small" data-action="add-person">Hinzufügen</button>
    </div>`;
}

function readIncidentForm(form) {
  const vehicles = [...$$("tr[data-vehicle]", form)].filter((row) => $('[data-v="present"]', row).checked).map((row) => {
    const value = (key) => $(`[data-v="${key}"]`, row).value;
    return { call_sign: row.dataset.vehicle, crew: value("crew") === "" ? null : Number(value("crew")),
             departed: value("departed") || null, arrived: value("arrived") || null };
  });
  if (!state.editDraft.visible) return { ...readForm(form), vehicles };      // Anwesenheit bleibt unverändert
  const people = state.editDraft.people.map((p) => ({ id: p.id, name: p.id == null ? p.name : null,
    role: p.role || null, vehicle: p.vehicle || null }));
  return { ...readForm(form), vehicles, people };
}

function addDraftPerson(form) {
  const field = (key) => $(`.person-add [data-p="${key}"]`, form);
  const name = field("name").value.trim().replace(/\s+/g, " ");
  if (!name) { field("name").focus(); return; }
  const member = state.memberOptions.find((m) => m.name.toLowerCase() === name.toLowerCase());
  const people = state.editDraft.people;
  if (people.some((p) => (member && p.id === member.id) || p.name.toLowerCase() === name.toLowerCase())) {
    toast(`${name} ist schon eingetragen`);
    return;
  }
  const display = member ? member.name : name;
  people.push({ id: member ? member.id : null, name: display, role: field("role").value.trim(),
                vehicle: field("vehicle").value, leader_name: leaderSpelling(display) });
  if (!member) toast(`${display} wird beim Speichern als neue Person angelegt`);
  redrawPeople(form);
}

function redrawPeople(form) {
  $("[data-people-edit]", form).innerHTML = peopleEditPanel();
  highlightLeader(form);
  $('.person-add [data-p="name"]', form).focus();
}

async function startEditing(id) {
  const incident = state.incidents.incidents.find((x) => x.id === id);
  state.editing = id;
  state.editNode = null;
  state.editDraft = { revision: incident.revision, visible: incident.people_editable, people: incident.people.map((p) => ({ id: p.id, name: p.name,
    role: p.role || "", vehicle: p.vehicle || "", leader_name: p.leader_name })) };
  updateDatalists();
  renderIncidents();
  state.current = id;
  state.editSnapshot = editSnapshot();
  $(`[data-form="${CSS.escape(id)}"] input:not([readonly])`)?.focus({ preventScroll: true });
  if (!incident.people_editable) { state.memberOptions = []; return; }
  try {
    state.memberOptions = (await api(`/api/members?tenant=${encodeURIComponent(incident.tenant)}`)).members;
  } catch (e) {
    state.memberOptions = [];
  }
  const options = state.memberOptions.map((m) => `<option value="${esc(m.name)}">`).join("");
  let list = $("#member-options");
  if (!list) { list = document.createElement("datalist"); list.id = "member-options"; $("#datalists").append(list); }
  list.innerHTML = options;
}

function editForm(e) {
  return `<div class="detail-grid" data-form="${e.id}">
    <div class="panel full"><h4>Einsatz ${e.number ?? ""} bearbeiten</h4>${formFields(e)}</div>
    <div class="panel full"><h4>Fahrzeuge${helpButton("vehicles")}</h4>
      <p class="small muted">Stärke und Zeiten korrigieren oder ein Fahrzeug ergänzen („dabei“). Manuell ergänzte Fahrzeuge und Personen bleiben erhalten, wenn der Bericht später erneut eingelesen wird.</p>
      ${vehicleEditTable(e)}</div>
    <div class="panel full" data-people-edit>${state.editDraft.visible ? peopleEditPanel() : attendancePanel(e)}</div>
    <div class="actions panel full bare">
      ${stepButtons(e)}
      <button type="button" class="btn btn-outline btn-small" data-action="cancel" data-tip="Esc">Abbrechen</button>
      <button type="button" class="btn btn-primary btn-small" data-action="save" data-id="${e.id}">Speichern</button>
    </div>
  </div>`;
}

function updateDatalists() {
  // Vorschläge für Ort und Einheitsführung aus den bekannten Orten und vorhandenen Einsätzen
  const incidents = state.incidents?.incidents || [];
  const places = [...new Set([...config.places, ...incidents.map((e) => e.place)])].filter(Boolean);
  const leaders = [...new Set(incidents.map((e) => e.unit_leader).filter(Boolean))].sort();
  let container = $("#datalists");
  if (!container) { container = document.createElement("div"); container.id = "datalists"; document.body.append(container); }
  const options = (values) => values.map((v) => `<option value="${esc(v)}">`).join("");
  container.innerHTML = `<datalist id="place-options">${options(places)}</datalist><datalist id="leader-options">${options(leaders)}</datalist>`;
}

// ------------------------------------------------------------ Ungespeicherte Bearbeitung
const openEditForm = () => state.editing == null ? null : $(`[data-form="${CSS.escape(state.editing)}"]`) || state.editNode;
const editSnapshot = () => { const form = openEditForm(); return form ? JSON.stringify(readIncidentForm(form)) : null; };
const incidentDirty = () => state.editing != null && state.editSnapshot != null && editSnapshot() !== state.editSnapshot;

/** Vor dem Verlassen eines geänderten Formulars nachfragen; true = weiter (Bearbeitung ist dann beendet). */
async function confirmLeaveEdit() {
  if (state.editing == null) return true;
  if (incidentDirty() && !await askConfirm({ title: "Änderungen am Einsatz verwerfen?", text: "Die Änderungen sind noch nicht gespeichert.",
    confirm: "Änderungen verwerfen", cancel: "Weiter bearbeiten", danger: true })) return false;
  state.editing = null;
  state.editSnapshot = null;
  return true;
}

/** Benachbarten Einsatz der Liste aufklappen (delta +1 nächster, -1 vorheriger); ohne geöffneten der erste. */
async function stepIncident(delta, from = state.current) {
  const list = visibleIncidents();
  if (!list.length) return;
  const index = list.findIndex((x) => x.id === from);
  const target = list[index < 0 ? (delta > 0 ? 0 : list.length - 1) : index + delta];
  if (!target || !await confirmLeaveEdit()) return;
  state.expanded.clear();
  state.expanded.add(target.id);
  state.current = target.id;
  renderIncidents();
  const row = $(`#incident-table tr.row[data-id="${CSS.escape(target.id)}"]`);
  row?.scrollIntoView({ block: "start", behavior: scrollBehavior() });
  $("button", row)?.focus({ preventScroll: true });
}

// ------------------------------------------------------------ Löschen mit „Rückgängig“
// Der Einsatz verschwindet sofort; gelöscht wird erst nach UNDO_MS (beim Schließen der Seite sofort).
const UNDO_MS = 15000;
const pendingDeletes = new Map();             // id -> { incident, timer }
const deleteUrl = (incident) => `/api/incidents/${encodeURIComponent(incident.id)}?revision=${incident.revision}`;

function deleteIncident(id) {
  const list = state.incidents.incidents, incident = list.find((x) => x.id === id);
  state.incidents.incidents = list.filter((x) => x.id !== id);
  state.expanded.delete(id);
  if (state.editing === id) { state.editing = null; state.editSnapshot = null; }
  pendingDeletes.set(id, { incident, timer: setTimeout(() => commitDelete(id), UNDO_MS) });
  renderIncidents();
  const open = pendingDeletes.size;
  toast(`Einsatz ${incident.number ?? ""} vom ${formatDate(incident.started_at)} gelöscht${open > 1 ? ` (${open} Löschungen rückgängig möglich)` : ""}`,
    { action: "Rückgängig", onAction: () => undoDelete(id), duration: UNDO_MS, onHold: holdDeletes, onRelease: releaseDeletes });
}

// Solange die Meldung mit „Rückgängig“ gelesen oder bedient wird, läuft die Frist bis zum endgültigen Löschen nicht ab
function holdDeletes() {
  for (const p of pendingDeletes.values()) clearTimeout(p.timer);
}
function releaseDeletes() {
  for (const [id, p] of pendingDeletes) p.timer = setTimeout(() => commitDelete(id), UNDO_MS);
}

function undoDelete(id) {
  const pending = pendingDeletes.get(id);
  if (!pending) return;
  clearTimeout(pending.timer);
  pendingDeletes.delete(id);
  if (state.incidents?.year === pending.incident.year) state.incidents.incidents.push(pending.incident);
  state.expanded.add(id);
  state.current = id;
  if (state.view === "incidents") renderIncidents();
  toast("Einsatz wiederhergestellt");
}

async function commitDelete(id) {
  const pending = pendingDeletes.get(id);
  if (!pending) return;
  pendingDeletes.delete(id);
  try {
    await api(deleteUrl(pending.incident), { method: "DELETE" });
    state.evaluation = null;                 // Kennzahlen und Jahre beim nächsten Zeichnen neu
    await loadYears();
    document.dispatchEvent(new Event("app:data"));
  } catch (err) {
    state.incidents = null;
    await showView();
    await reportError(`Einsatz ${pending.incident.number ?? ""} wurde nicht gelöscht.`, err, "Die Liste wurde neu geladen.");
  }
}
window.addEventListener("pagehide", () => {
  for (const { incident, timer } of pendingDeletes.values()) {
    clearTimeout(timer);
    fetch(deleteUrl(incident), { method: "DELETE", keepalive: true });
  }
  pendingDeletes.clear();
});

async function handleIncidentAction(action, id, el) {
  if (action === "step") { await stepIncident(Number(el.dataset.step), id); return; }
  if (action === "edit") {
    if (state.editing !== id && !await confirmLeaveEdit()) return;
    await startEditing(id);
    return;
  }
  if (action === "cancel") { if (await confirmLeaveEdit()) renderIncidents(); return; }
  if (action === "delete") { deleteIncident(id); return; }
  if (action === "add-person") { addDraftPerson(formOf(el)); return; }
  if (action === "remove-person") {
    state.editDraft.people.splice(Number(el.dataset.index), 1);
    redrawPeople(formOf(el));
    return;
  }
  try {
    if (action === "save") {
      await apiJson(`/api/incidents/${encodeURIComponent(id)}`, "PUT", {
        ...readIncidentForm($(`[data-form="${id}"]`)), revision: state.editDraft.revision,
      });
      state.editing = null;
      state.editSnapshot = null;
      toast("Gespeichert");
    }
    await reloadData();
  } catch (err) {
    await reportError("Der Einsatz wurde nicht gespeichert.", err, "Ihre Eingaben bleiben im Formular erhalten.");
  }
}


// Bericht im BKS-Portal (neues Fenster); Nummer des Berichts, dazu der Stammdatensatz des Einsatzes
function bksLink(e) {
  return `<a href="${esc(e.bks_url)}" target="_blank" rel="noopener">Bericht ${esc(e.bks_report_id)} öffnen</a>`
    + (e.bks_record_id && e.bks_record_id !== e.bks_report_id ? ` · Stammdatensatz ${esc(e.bks_record_id)}` : "");
}
