"use strict";

// Übungsdienste (ohne BKS-Bericht): Erfassung im Hauptreiter Einsätze, Teilnahmen im Hauptreiter Personal.
// Wird nach app.js geladen und trägt sich in VIEWS ein. Übungen fließen in keine Auswertung ein (eigene Tabellen).
const trainingState = {
  data: null, year: null,
  editing: null,             // null | "new" | Übungs-ID
  draft: null,               // Stand des Formulars: Felder, memberIds (Set), newMembers, revision
  search: "", pendingDelete: null,
};

async function loadTrainings() {
  if (!trainingState.data || trainingState.year !== state.year) {
    const year = state.year, data = await api(`/api/trainings?year=${year}`);
    if (year === state.year) { trainingState.data = data; trainingState.year = year; }
  }
}
const reloadTrainings = () => { trainingState.data = null; return loadTrainings(); };

const splitIso = (iso) => iso ? { date: iso.slice(0, 10), time: iso.slice(11, 16) } : { date: "", time: "" };

function emptyTrainingDraft() {
  const today = new Date(), date = `${today.getFullYear()}-${pad2(today.getMonth() + 1)}-${pad2(today.getDate())}`;
  // Enddatum = Startdatum, solange es nicht von Hand geändert wird (endTouched)
  return { id: null, revision: null, topic: "", startDate: date, startTime: "19:00", endDate: date, endTime: "21:00",
    endTouched: false, category: "", place: "", trainer: "", notes: "", memberIds: new Set(), newMembers: [] };
}

function draftFromTraining(t) {
  const s = splitIso(t.started_at), e = splitIso(t.ended_at);
  return { id: t.id, revision: t.revision, topic: t.topic, startDate: s.date, startTime: s.time, endDate: e.date,
    endTime: e.time, endTouched: true, category: t.category || "", place: t.place || "", trainer: t.trainer || "",
    notes: t.notes || "", memberIds: new Set(t.participants.map((p) => p.id)), newMembers: [] };
}

/** Dauer in Minuten aus dem Formular (null bei unvollständigen oder unstimmigen Angaben). */
function draftMinutes(d) {
  if (!d.startDate || !d.startTime || !d.endDate || !d.endTime) return null;
  const diff = (new Date(`${d.endDate}T${d.endTime}`) - new Date(`${d.startDate}T${d.startTime}`)) / 60000;
  return diff > 0 ? diff : null;
}

function trainingPayload(d) {
  return { topic: d.topic, started_at: `${d.startDate}T${d.startTime}`, ended_at: `${d.endDate}T${d.endTime}`,
    category: d.category, place: d.place, trainer: d.trainer, notes: d.notes, member_ids: [...d.memberIds],
    new_members: d.newMembers, revision: d.revision };
}

// ------------------------------------------------------------ Erfassen
function trainingField(label, name, value, { type = "text", span = "", attributes = "" } = {}) {
  return `<div class="field ${span}"><span><label for="tr-${name}">${label}</label></span>
    <input id="tr-${name}" data-tr="${name}" type="${type}" value="${esc(value)}" ${attributes}></div>`;
}

/** Teilnehmerwahl: Klick auf eine Person schaltet die Teilnahme um; „Neue Person“ legt sie im Personenstamm an. */
function trainingPeopleHtml() {
  const d = trainingState.draft, q = trainingState.search.trim().toLowerCase();
  const members = trainingState.data.members.filter((m) => (m.active || d.memberIds.has(m.id))
    && (!q || m.name.toLowerCase().includes(q)));
  const chip = (m) => `<button type="button" class="chip-toggle ${d.memberIds.has(m.id) ? "on" : ""}" data-tr-member="${m.id}"
    aria-pressed="${d.memberIds.has(m.id)}">${esc(m.name)}${m.active ? "" : " (ausgeschieden)"}</button>`;
  const fresh = d.newMembers.map((m, i) => `<span class="chip-toggle on new">${esc([m.last_name, m.first_name].filter(Boolean).join(", "))}
    <button type="button" class="chip-remove" data-tr-remove-new="${i}" aria-label="Neue Person entfernen">×</button></span>`);
  return `<div class="people">${members.map(chip).join("") || `<span class="muted">Keine Person gefunden.</span>`}${fresh.join("")}</div>`;
}

function trainingPeopleCount() {
  const d = trainingState.draft;
  return plural(d.memberIds.size + d.newMembers.length, "Teilnehmer", "Teilnehmer");
}

function trainingFormHtml() {
  const d = trainingState.draft, minutes = draftMinutes(d);
  return `<div class="card training-form" data-training-form>
    <h3>${d.id ? "Übung bearbeiten" : "Neue Übung"}</h3>
    <div class="form-grid">
      ${trainingField("Thema", "topic", d.topic, { span: "span-2", attributes: 'maxlength="200" required' })}
      ${trainingField("Beginn (Datum)", "startDate", d.startDate, { type: "date" })}
      ${trainingField("Beginn (Uhrzeit)", "startTime", d.startTime, { type: "time" })}
      ${trainingField("Ende (Datum)", "endDate", d.endDate, { type: "date" })}
      ${trainingField("Ende (Uhrzeit)", "endTime", d.endTime, { type: "time" })}
      ${trainingField("Kategorie (optional)", "category", d.category, { attributes: 'maxlength="80"' })}
      ${trainingField("Ort (optional)", "place", d.place, { attributes: 'maxlength="120"' })}
      ${trainingField("Ausbilder/in (optional)", "trainer", d.trainer, { attributes: 'maxlength="120"' })}
      <div class="field span-2"><span><label for="tr-notes">Notizen (optional)</label></span>
        <textarea id="tr-notes" data-tr="notes" rows="2" maxlength="2000">${esc(d.notes)}</textarea></div>
    </div>
    <p class="small muted" id="tr-duration">${minutes ? `Dauer ${formatDuration(minutes)}` : "Das Ende muss nach dem Beginn liegen."}</p>
    <h4>Teilnehmer <span class="muted small" id="tr-count">(${trainingPeopleCount()})</span></h4>
    <div class="toolbar-inline">
      <input type="search" id="tr-search" placeholder="Person suchen" value="${esc(trainingState.search)}" aria-label="Person suchen">
      <button type="button" class="btn btn-light btn-small" data-tr-action="all">Alle übernehmen</button>
      <button type="button" class="btn btn-outline btn-small" data-tr-action="none">Auswahl leeren</button>
    </div>
    <div id="tr-people">${trainingPeopleHtml()}</div>
    <div class="toolbar-inline new-person">
      <input type="text" id="tr-new-last" placeholder="Nachname" maxlength="60" aria-label="Nachname der neuen Person">
      <input type="text" id="tr-new-first" placeholder="Vorname" maxlength="60" aria-label="Vorname der neuen Person">
      <button type="button" class="btn btn-light btn-small" data-tr-action="add-new">Neue Person hinzufügen</button>
    </div>
    <p class="small muted">Neue Personen werden beim Speichern in den Personenstamm übernommen.</p>
    <div class="form-actions">
      <button type="button" class="btn btn-outline btn-small" data-tr-action="cancel">Abbrechen</button>
      <button type="button" class="btn btn-primary btn-small" data-tr-action="save">Speichern</button>
    </div></div>`;
}

// ------------------------------------------------------------ Liste
function trainingRowHtml(t) {
  const names = t.participants.map((p) => esc(p.name)).join("; ") || "–";
  const days = t.started_at.slice(0, 10) === t.ended_at.slice(0, 10)
    ? `${formatDate(t.started_at)} ${formatTime(t.started_at)}–${formatTime(t.ended_at)}`
    : `${formatDateTime(t.started_at)} – ${formatDateTime(t.ended_at)}`;
  const meta = [t.category, t.place, t.trainer && `Ausbilder/in: ${t.trainer}`].filter(Boolean).map(esc).join(" · ");
  return `<div class="card training-row" data-training="${t.id}">
    <div class="toolbar"><div><h3>${esc(t.topic)}</h3>
      <p class="muted small">${days} · ${formatDuration(t.duration_min)} · ${plural(t.participants.length, "Teilnehmer", "Teilnehmer")}${meta ? ` · ${meta}` : ""}</p></div>
      ${can("trainings.edit") ? `<div class="form-actions">
        <button type="button" class="btn btn-outline btn-small" data-tr-action="delete" data-id="${t.id}">Löschen</button>
        <button type="button" class="btn btn-light btn-small" data-tr-action="edit" data-id="${t.id}">Bearbeiten</button></div>` : ""}</div>
    ${t.notes ? `<p class="small">${esc(t.notes)}</p>` : ""}
    <details><summary class="small">Teilnehmer anzeigen</summary><p class="small">${names}</p></details></div>`;
}

function renderTrainings() {
  const data = trainingState.data;
  const list = data.trainings.filter((t) => t.id !== trainingState.pendingDelete);
  $("#view-trainings").innerHTML = `
    <div class="card notice-card"><p class="small muted">Übungsdienste ohne BKS-Bericht. Sie erscheinen in keiner Auswertung und
      nicht in der Einsatzliste – nur hier und im Reiter Personal → Übungen.</p></div>
    ${trainingState.editing ? trainingFormHtml() : (can("trainings.edit")
      ? `<p><button type="button" class="btn btn-primary" data-tr-action="new">Neue Übung erfassen</button></p>` : "")}
    ${list.map(trainingRowHtml).join("") || `<p class="empty-note">Für ${state.year} ist keine Übung erfasst.</p>`}`;
}

// ------------------------------------------------------------ Teilnahmen (Reiter Personal)
const TRAINING_COLUMNS = [["name", "Name"], ["trainings", "Übungen"], ["rate", "Beteiligung"], ["hours", "Stunden"], ["last", "Zuletzt"]];

function renderTrainingMembers() {
  const data = trainingState.data, s = data.summary;
  const sort = trainingState.sort || (trainingState.sort = { field: "trainings", descending: true });
  const cmp = (x, y) => sort.field === "name" ? x.name.localeCompare(y.name, "de") : (x[sort.field] ?? "") > (y[sort.field] ?? "") ? 1 : -1;
  const list = [...s.members].sort((x, y) => sort.descending ? cmp(y, x) : cmp(x, y));
  const edit = can("trainings.edit");
  $("#view-training_members").innerHTML = `<div class="card list-card members-table">
    <div class="toolbar"><div><h3>Übungsteilnahme ${state.year}</h3>
      <p class="muted small">${plural(list.length, "Person", "Personen")} · ${plural(s.count, "Übung", "Übungen")} · ${formatHours(s.minutes)} Übungszeit
      · Diese Zahlen gehören nicht zur Einsatzstatistik.</p></div></div>
    <div class="table-wrap"><table class="table"><thead><tr>${TRAINING_COLUMNS.map(([f, title]) =>
      `<th class="sortable ${f === "name" ? "" : "right"}" aria-sort="${sort.field === f ? (sort.descending ? "descending" : "ascending") : "none"}"><button type="button" class="sort-button" data-tr-sort="${f}">${title}${sort.field === f ? (sort.descending ? " ▾" : " ▴") : ""}</button></th>`).join("")}</tr></thead>
      <tbody>${list.map((m) => `<tr><td><strong>${esc(m.name)}</strong></td><td class="right">${m.trainings}</td>
        <td class="right">${percent(m.rate)}</td><td class="right">${num(m.hours)}</td><td class="right">${formatDate(m.last)}</td></tr>`).join("")}</tbody></table></div>
    ${list.length ? "" : `<p class="empty-note">Für ${state.year} sind keine Übungsteilnahmen erfasst.</p>`}</div>
    ${edit ? `<div class="card"><h3>Personenstamm</h3>
      <p class="muted small">Ausgeschiedene Personen erscheinen nicht mehr in der Auswahl bei neuen Übungen; ihre Einsätze und Teilnahmen bleiben erhalten.</p>
      <ul class="member-admin">${data.members.map((m) => `<li><span ${m.active ? "" : 'class="muted"'}>${esc(m.name)}${m.active ? "" : " (ausgeschieden)"}</span>
        <button type="button" class="btn btn-light btn-small" data-tr-active="${m.id}" data-active="${m.active ? "0" : "1"}">${m.active ? "Ausgeschieden" : "Wieder aktiv"}</button></li>`).join("")}</ul></div>` : ""}`;
}

// ------------------------------------------------------------ Bedienung
function openTrainingForm(draft, editing) {
  trainingState.draft = draft;
  trainingState.editing = editing;
  trainingState.search = "";
  renderTrainings();
  $("#tr-topic")?.focus();
}

function updateDraftField(el) {
  const d = trainingState.draft, name = el.dataset.tr;
  d[name] = el.value;
  if (name === "endDate") d.endTouched = true;
  if (name === "startDate" && !d.endTouched) { d.endDate = el.value; $("#tr-endDate").value = el.value; }
  const minutes = draftMinutes(d);
  $("#tr-duration").textContent = minutes ? `Dauer ${formatDuration(minutes)}` : "Das Ende muss nach dem Beginn liegen.";
}

function refreshTrainingPeople() {
  $("#tr-people").innerHTML = trainingPeopleHtml();
  $("#tr-count").textContent = `(${trainingPeopleCount()})`;
}

function addNewTrainingMember() {
  const last = $("#tr-new-last"), first = $("#tr-new-first");
  if (!last.value.trim()) { toast("Bitte einen Nachnamen eingeben."); last.focus(); return; }
  const d = trainingState.draft, person = { last_name: last.value.trim(), first_name: first.value.trim() };
  const existing = trainingState.data.members.find((m) =>
    m.name.toLowerCase() === [person.last_name, person.first_name].filter(Boolean).join(", ").toLowerCase());
  if (existing) { d.memberIds.add(existing.id); toast(`${existing.name} ist schon im Personenstamm und wurde übernommen.`); }
  else d.newMembers.push(person);
  last.value = first.value = "";
  refreshTrainingPeople();
  last.focus();
}

async function saveTraining() {
  const d = trainingState.draft;
  if (!d.topic.trim()) { toast("Bitte ein Thema angeben."); $("#tr-topic").focus(); return; }
  if (!draftMinutes(d)) { toast("Das Ende muss nach dem Beginn liegen."); return; }
  try {
    await apiJson(d.id ? `/api/trainings/${d.id}` : "/api/trainings", d.id ? "PUT" : "POST", trainingPayload(d));
  } catch (e) { toast(e.message); return; }
  trainingState.editing = trainingState.draft = null;
  await reloadTrainings();
  VIEWS[state.view].render();
  toast("Übung gespeichert.");
}

function deleteTraining(id) {
  const training = trainingState.data.trainings.find((t) => t.id === id);
  if (!training) return;
  // Wie bei Einsätzen: erst ausblenden, endgültig löschen erst nach Ablauf der Rückgängig-Zeit
  trainingState.pendingDelete = id;
  renderTrainings();
  let undone = false;
  toast("Übung gelöscht.", { action: "Rückgängig", duration: 6000, onAction: () => {
    undone = true; trainingState.pendingDelete = null; renderTrainings();
  } });
  setTimeout(async () => {
    if (undone) return;
    try { await api(`/api/trainings/${id}?revision=${training.revision}`, { method: "DELETE" }); }
    catch (e) { toast(e.message); }
    trainingState.pendingDelete = null;
    await reloadTrainings();
    VIEWS[state.view].render();
  }, 6200);
}

async function trainingClick(e) {
  const member = e.target.closest("[data-tr-member]");
  if (member) {
    const id = Number(member.dataset.trMember), ids = trainingState.draft.memberIds;
    if (ids.has(id)) ids.delete(id); else ids.add(id);
    refreshTrainingPeople();
    $(`[data-tr-member="${id}"]`)?.focus();
    return;
  }
  const removeNew = e.target.closest("[data-tr-remove-new]");
  if (removeNew) { trainingState.draft.newMembers.splice(Number(removeNew.dataset.trRemoveNew), 1); refreshTrainingPeople(); return; }
  const sort = e.target.closest("[data-tr-sort]");
  if (sort) {
    const field = sort.dataset.trSort, s = trainingState.sort;
    trainingState.sort = { field, descending: s.field === field ? !s.descending : field !== "name" };
    renderTrainingMembers();
    return;
  }
  const active = e.target.closest("[data-tr-active]");
  if (active) {
    try { await apiJson(`/api/trainings/members/${active.dataset.trActive}`, "PUT", { active: active.dataset.active === "1" }); }
    catch (error) { toast(error.message); return; }
    await reloadTrainings();
    renderTrainingMembers();
    return;
  }
  const button = e.target.closest("[data-tr-action]");
  if (!button) return;
  const d = trainingState.draft;
  switch (button.dataset.trAction) {
    case "new": openTrainingForm(emptyTrainingDraft(), "new"); break;
    case "edit": openTrainingForm(draftFromTraining(trainingState.data.trainings.find((t) => t.id === Number(button.dataset.id))), Number(button.dataset.id)); break;
    case "delete": deleteTraining(Number(button.dataset.id)); break;
    case "cancel": trainingState.editing = trainingState.draft = null; renderTrainings(); break;
    case "save": await saveTraining(); break;
    case "all": for (const m of trainingState.data.members) if (m.active) d.memberIds.add(m.id); refreshTrainingPeople(); break;
    case "none": d.memberIds.clear(); d.newMembers = []; refreshTrainingPeople(); break;
    case "add-new": addNewTrainingMember(); break;
  }
}

VIEWS.trainings = { label: "Übungen", sub: "Übungen", title: "Übungsdienste", load: loadTrainings, render: renderTrainings,
  permission: "trainings.view", single: true, help: "sec_training" };
VIEWS.training_members = { label: "Übungen", sub: "Übungen", title: "Übungsteilnahme", load: loadTrainings, render: renderTrainingMembers,
  permission: "trainings.view", single: true, help: "sec_training" };

$("#view-trainings").addEventListener("click", trainingClick);
$("#view-training_members").addEventListener("click", trainingClick);
$("#view-trainings").addEventListener("input", (e) => {
  if (e.target.dataset.tr) updateDraftField(e.target);
  if (e.target.id === "tr-search") { trainingState.search = e.target.value; refreshTrainingPeople(); }
});
$("#view-trainings").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.target.id === "tr-new-last" || e.target.id === "tr-new-first")) { e.preventDefault(); addNewTrainingMember(); }
});
document.addEventListener("app:data", () => { trainingState.data = null; });
