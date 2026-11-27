"use strict";

// Übungsdienste (ohne BKS-Bericht): Erfassen über den Knopf „Übung erfassen“ oben (Dialog), Liste der Übungen unter
// Einsätze → Übungen (aufklappen, bearbeiten), Teilnahme je Person unter Personal → Übungen. Wird nach app.js geladen und trägt sich in VIEWS ein.
// Übungen fließen in keine Auswertung ein (eigene Tabellen). Den Personenstamm pflegt Einstellungen → Personen.
const trainingState = {
  data: null, year: null,
  editing: null,             // null | "new" | Übungs-ID
  draft: null,               // Stand des Formulars: Felder, memberIds (Set), newMembers, revision
  search: "", pendingDelete: null,
  openPeople: new Set(), openTrainings: new Set(),     // aufgeklappte Zeilen
};

async function loadTrainings() {
  if (!trainingState.data || trainingState.year !== state.year || trainingState.stale) {
    const year = state.year, data = await api(`/api/trainings?year=${year}`);
    if (year === state.year) { trainingState.data = data; trainingState.year = year; trainingState.stale = false; }
  }
}
const reloadTrainings = () => { trainingState.data = null; return loadTrainings(); };

const splitIso = (iso) => iso ? { date: iso.slice(0, 10), time: iso.slice(11, 16) } : { date: "", time: "" };

function emptyTrainingDraft() {
  const today = new Date(), date = `${today.getFullYear()}-${pad2(today.getMonth() + 1)}-${pad2(today.getDate())}`;
  // Enddatum = Startdatum, solange es nicht von Hand geändert wird (endTouched)
  return { id: null, revision: null, topic: "", startDate: date, startTime: "19:00", endDate: date, endTime: "21:00",
    endTouched: false, csaLoad: false, category: "", place: "", trainer: "", notes: "", memberIds: new Set(), newMembers: [] };
}

function draftFromTraining(t) {
  const s = splitIso(t.started_at), e = splitIso(t.ended_at);
  return { id: t.id, revision: t.revision, topic: t.topic, startDate: s.date, startTime: s.time, endDate: e.date,
    endTime: e.time, endTouched: true, csaLoad: Boolean(t.csa_load), category: t.category || "", place: t.place || "", trainer: t.trainer || "",
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
    category: d.category, place: d.place, trainer: d.trainer, notes: d.notes, csa_load: d.csaLoad, member_ids: [...d.memberIds],
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
    aria-pressed="${d.memberIds.has(m.id)}">${esc(m.name)}${m.active ? "" : " (ausgetreten)"}</button>`;
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
  return `<div class="training-form" data-training-form>
    <div class="form-grid">
      ${trainingField("Thema", "topic", d.topic, { span: "span-2", attributes: 'maxlength="200" required' })}
      ${trainingField("Beginn (Datum)", "startDate", d.startDate, { type: "date" })}
      ${trainingField("Beginn (Uhrzeit)", "startTime", d.startTime, { type: "time" })}
      ${trainingField("Ende (Datum)", "endDate", d.endDate, { type: "date" })}
      ${trainingField("Ende (Uhrzeit)", "endTime", d.endTime, { type: "time" })}
      ${trainingField("Kategorie (optional)", "category", d.category, { attributes: 'maxlength="80"' })}
      ${trainingField("Ort (optional)", "place", d.place, { attributes: 'maxlength="120"' })}
      ${trainingField("Übungsleiter/in (optional)", "trainer", d.trainer, { attributes: 'maxlength="120" list="tr-trainer-list" autocomplete="off"' })}
      <datalist id="tr-trainer-list">${trainingState.data.members.filter((m) => m.active).map((m) => `<option value="${esc(m.name)}">`).join("")}</datalist>
      <label class="toggle span-2"><input type="checkbox" id="tr-csaLoad" data-tr-flag="csaLoad" ${d.csaLoad ? "checked" : ""}> CSA-Belastungsübung (jährlich für Träger/innen eines Chemikalienschutzanzugs)</label>
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
    <p class="small muted">Neue Personen werden beim Speichern in den Personenstamm übernommen; dort (Einstellungen → Personen) pflegst du ihn.</p>
    <div class="form-actions">
      <button type="button" class="btn btn-outline" data-tr-action="cancel">Abbrechen</button>
      <button type="button" class="btn btn-primary" data-tr-action="save">Speichern</button>
    </div></div>`;
}

// ------------------------------------------------------------ Übersicht (Reiter Personal → Übungen)
const TRAINING_COLUMNS = [["name", "Name", ""], ["trainings", "Übungen", ""], ["rate", "Beteiligung", "right hide-mobile"],
  ["hours", "Stunden", "right hide-mobile"], ["last", "Zuletzt", "right hide-mobile"]];

const trainingDays = (t) => t.started_at.slice(0, 10) === t.ended_at.slice(0, 10)
  ? `${formatDate(t.started_at)} ${formatTime(t.started_at)}–${formatTime(t.ended_at)}`
  : `${formatDateTime(t.started_at)} – ${formatDateTime(t.ended_at)}`;

const trainingBar = (value, max) => `<div class="inline-bar"><b>${value}</b><span class="track"><span style="width:${(value / Math.max(1, max)) * 100}%"></span></span></div>`;
const trainingChevron = (open) => `<td class="col-toggle">${ICON_CHEVRON}</td>`;

/** Übungen einer Person im Jahr (Detailzeile der Teilnahmetabelle). */
function personTrainingsHtml(person) {
  const rows = trainingState.data.trainings.filter((t) => t.participants.some((p) => p.id === person.id));
  return `<div class="member-incidents"><table class="mini-table"><thead><tr><th>Datum</th><th>Thema</th><th>Dauer</th><th>Übungsleiter/in</th></tr></thead>
    <tbody>${rows.map((t) => `<tr class="link-row" data-tr-open="${t.id}" tabindex="0"><td>${trainingDays(t)}</td><td>${esc(t.topic)}</td><td>${formatDuration(t.duration_min)}</td><td>${esc(t.trainer || "–")}</td></tr>`).join("")}</tbody></table></div>`;
}

/** PIN der QR-Anmeldung und wartende Anmeldungen (Quarantäne) einer Übung; nur mit Recht zum Ändern. */
function checkinAdminHtml(t) {
  const waiting = t.checkins || [];
  const line = (c) => `<li>${esc(c.name)}${c.match ? ` <span class="muted">(entspricht ${esc(c.match)})</span>` : ` <span class="muted">(neue Person)</span>`}
    <button type="button" class="btn btn-light btn-small" data-tr-action="accept-checkin" data-id="${t.id}" data-checkin-id="${c.id}">Übernehmen</button>
    <button type="button" class="btn btn-outline btn-small" data-tr-action="reject-checkin" data-id="${t.id}" data-checkin-id="${c.id}">Ablehnen</button></li>`;
  return `<div class="small"><p><b>Anmelde-PIN (QR-Code):</b> ${t.checkin_pin ? `<span class="pin">${esc(t.checkin_pin)}</span>` : "keine"}
      <button type="button" class="btn btn-outline btn-small" data-tr-action="new-pin" data-id="${t.id}">${t.checkin_pin ? "Neu erzeugen" : "Erzeugen"}</button>
     </p>
    ${waiting.length ? `<p><b>Wartende Anmeldungen (${waiting.length}):</b>
      <button type="button" class="btn btn-light btn-small" data-tr-action="accept-checkin" data-id="${t.id}">Alle übernehmen</button></p>
      <ul class="plain">${waiting.map(line).join("")}</ul>` : ""}</div>`;
}

/** Teilnehmer, Notizen und Aktionen einer Übung (Detailzeile der Übungsliste). */
function trainingDetailHtml(t) {
  const meta = [t.category, t.place, t.trainer && `Übungsleiter/in: ${t.trainer}`].filter(Boolean).map(esc).join(" · ");
  return `<div class="detail-grid training-detail">
    ${meta ? `<p class="small">${meta}</p>` : ""}${t.csa_load ? `<p class="small"><span class="tenant-badge">CSA-Belastungsübung</span></p>` : ""}
    ${t.notes ? `<p class="small">${esc(t.notes)}</p>` : ""}
    <p class="small"><b>Teilnehmer:</b> ${t.participants.map((p) => esc(p.name)).join("; ") || "–"}</p>
    ${can("trainings.edit") ? checkinAdminHtml(t) : ""}
    ${can("trainings.edit") ? `<div class="form-actions">
      <button type="button" class="btn btn-outline btn-small" data-tr-action="delete" data-id="${t.id}">Löschen</button>
      <button type="button" class="btn btn-light btn-small" data-tr-action="edit" data-id="${t.id}">Bearbeiten</button></div>` : ""}</div>`;
}

/** Liste der Übungen (Einsätze → Übungen): wichtigste Daten je Zeile, Aufklappen zeigt alles, Bearbeiten im Dialog. */
function renderTrainings() {
  if (!trainingState.data) { loadTrainings().then(() => state.view === "trainings" && renderTrainings()); return; }
  const data = trainingState.data, s = data.summary;
  const trainings = data.trainings.filter((t) => t.id !== trainingState.pendingDelete);
  const maxParticipants = Math.max(1, ...trainings.map((t) => t.participants.length));
  const open = (id) => trainingState.openTrainings.has(id);
  const canEdit = can("trainings.edit");
  const row = (t) => `<tr class="row ${open(t.id) ? "open" : ""}" data-tr-training="${t.id}" tabindex="0" aria-expanded="${open(t.id)}">
      <td>${formatDate(t.started_at)}<span class="member-sub">${formatTime(t.started_at)}–${formatTime(t.ended_at)}</span></td>
      <td class="hide-mobile">${formatTime(t.started_at)}–${formatTime(t.ended_at)}</td>
      <td><strong>${esc(t.topic)}</strong>${t.csa_load ? ` <span class="tenant-badge">CSA</span>` : ""}<span class="member-sub">${[t.category, t.place].filter(Boolean).map(esc).join(" · ")}</span></td>
      <td class="hide-mobile">${esc(t.category || "–")}</td><td class="hide-mobile">${esc(t.place || "–")}</td>
      <td class="right hide-mobile">${formatDuration(t.duration_min)}</td>
      ${canEdit ? `<td class="right">${t.checkin_pin ? `<span class="pin">${esc(t.checkin_pin)}</span>` : "–"}</td>` : ""}
      <td>${trainingBar(t.participants.length, maxParticipants)}${t.checkins?.length ? `<span class="member-sub">+ ${t.checkins.length} wartend</span>` : ""}</td>${trainingChevron()}</tr>
    ${open(t.id) ? `<tr class="detail"><td colspan="${canEdit ? 9 : 8}">${trainingDetailHtml(t)}</td></tr>` : ""}`;
  $("#view-trainings").innerHTML = `<div class="card list-card members-table">
    <div class="toolbar"><div><h3>Übungen ${state.year}</h3>
      <p class="muted small">${plural(s.count, "Übung", "Übungen")} · ${formatHours(s.minutes)} Übungszeit · Zeile aufklappen zeigt Teilnehmer und Notizen · Nicht Teil der Einsatzstatistik${can("trainings.edit") ? " · Neue Übung: „Übung erfassen“ oben" : ""}</p></div>
      ${can("trainings.edit") ? `<button type="button" class="btn btn-light btn-small" data-tr-action="qr">QR-Code zur Anmeldung</button>` : ""}</div>
    <div class="table-wrap"><table class="table"><thead><tr><th>Datum</th><th class="hide-mobile">Zeit</th><th>Thema</th>
      <th class="hide-mobile">Kategorie</th><th class="hide-mobile">Ort</th><th class="right hide-mobile">Dauer</th>${canEdit ? `<th class="right">Anmelde-PIN</th>` : ""}<th>Teilnehmer</th><th class="col-toggle"><span class="visually-hidden">Details anzeigen</span></th></tr></thead>
      <tbody>${trainings.map(row).join("")}</tbody></table></div>
    ${trainings.length ? "" : `<p class="empty-note">Für ${state.year} ist keine Übung erfasst.</p>`}</div>`;
}

/** Träger/innen eines Chemikalienschutzanzugs und die jährliche CSA-Belastungsübung des Jahres. */
function csaStatusHtml(csa) {
  if (!csa.length) return "";
  const open = csa.filter((p) => !p.done);
  const chip = (p) => `<li><span class="tenant-badge ${p.done ? "signed" : "stale"}">${esc(p.name)}${p.done ? ` · ${formatDate(p.last)}` : " · offen"}</span></li>`;
  return `<div class="card csa-status"><h3>CSA-Belastungsübung ${state.year}</h3>
    <p class="muted small">${open.length ? `${plural(open.length, "CSA-Träger/in", "CSA-Träger/innen")} von ${csa.length} ohne Belastungsübung in diesem Jahr.` : `Alle ${csa.length} CSA-Träger/innen haben die Belastungsübung absolviert.`}
      Eine Übung zählt, wenn „CSA-Belastungsübung“ angekreuzt ist; wer CSA-Träger/in ist, steht unter Einstellungen → Personen.</p>
    <ul>${csa.map(chip).join("")}</ul></div>`;
}

function renderTrainingMembers() {
  if (!trainingState.data) { loadTrainings().then(() => state.view === "training_members" && renderTrainingMembers()); return; }
  const data = trainingState.data, s = data.summary;
  const sort = trainingState.sort || (trainingState.sort = { field: "trainings", descending: true });
  const cmp = (x, y) => sort.field === "name" ? x.name.localeCompare(y.name, "de") : (x[sort.field] ?? "") > (y[sort.field] ?? "") ? 1 : (x[sort.field] ?? "") < (y[sort.field] ?? "") ? -1 : 0;
  const people = [...s.members].sort((x, y) => sort.descending ? cmp(y, x) : cmp(x, y));
  const trainings = data.trainings.filter((t) => t.id !== trainingState.pendingDelete);
  const maxCount = Math.max(1, ...people.map((m) => m.trainings));
  const open = (set, id) => set.has(id);
  const personRow = (m, i) => `<tr class="row ${open(trainingState.openPeople, m.id) ? "open" : ""}" data-tr-person="${m.id}" tabindex="0" aria-expanded="${open(trainingState.openPeople, m.id)}">
      <td class="muted">${i + 1}</td>
      <td><strong>${esc(m.name)}</strong><span class="member-sub">${percent(m.rate).replace(" ", "\u00a0")} · ${num(m.hours)}\u00a0h</span></td>
      <td>${trainingBar(m.trainings, maxCount)}</td>
      <td class="right hide-mobile">${percent(m.rate)}</td><td class="right hide-mobile">${num(m.hours)}</td>
      <td class="right hide-mobile">${formatDate(m.last)}</td>${trainingChevron()}</tr>
    ${open(trainingState.openPeople, m.id) ? `<tr class="detail"><td colspan="${TRAINING_COLUMNS.length + 2}">${personTrainingsHtml(m)}</td></tr>` : ""}`;
  $("#view-training_members").innerHTML = `${csaStatusHtml(data.csa || [])}
    <div class="card list-card members-table">
      <div class="toolbar"><div><h3>Übungsteilnahme ${state.year}</h3>
        <p class="muted small">${plural(people.length, "Person", "Personen")} · ${plural(s.count, "Übung", "Übungen")} · ${formatHours(s.minutes)} Übungszeit · Stunden = Dauer der Übung je Teilnahme · Nicht Teil der Einsatzstatistik</p></div></div>
      <div class="table-wrap"><table class="table"><thead><tr><th class="col-number">Nr.</th>${TRAINING_COLUMNS.map(([f, title, cls]) =>
        `<th class="sortable ${cls}" aria-sort="${sort.field === f ? (sort.descending ? "descending" : "ascending") : "none"}"><button type="button" class="sort-button" data-tr-sort="${f}">${title}${sort.field === f ? (sort.descending ? " ▾" : " ▴") : ""}</button></th>`).join("")}<th class="col-toggle"><span class="visually-hidden">Übungen anzeigen</span></th></tr></thead>
        <tbody>${people.map(personRow).join("")}</tbody></table></div>
      ${people.length ? "" : `<p class="empty-note">Für ${state.year} sind keine Übungsteilnahmen erfasst.</p>`}</div>`;
}

// ------------------------------------------------------------ Bedienung
const trainingDialog = () => $("#training-dialog");

function renderTrainingDialog() {
  $("#training-title").textContent = trainingState.draft.id ? "Übung bearbeiten" : "Übung erfassen";
  $("#training-form-body").innerHTML = trainingFormHtml();
}

/** Öffnet den Dialog (vom Knopf oben bzw. „Bearbeiten“ in der Liste); newDraft erst nach dem Laden der Personen. */
async function openTrainingForm(makeDraft, editing) {
  try { await loadTrainings(); } catch (e) { toast(e.message); return; }
  trainingState.draft = makeDraft();
  trainingState.editing = editing;
  trainingState.search = "";
  renderTrainingDialog();
  if (!trainingDialog().open) trainingDialog().showModal();
  $("#tr-topic")?.focus();
}

// ------------------------------------------------------------ QR-Code zur Anmeldung (ohne Benutzerkonto)
const checkinDialog = () => $("#checkin-dialog");

async function renderCheckin() {
  const { url } = await api("/api/trainings/checkin");
  $("#checkin-body").innerHTML = `<div class="checkin-print">
      <img src="/api/trainings/checkin.svg?v=${Date.now()}" alt="QR-Code zur Anmeldung zum Übungsdienst" width="280" height="280">
      <p class="small"><a href="${esc(url)}" target="_blank" rel="noopener">${esc(url)}</a></p></div>
    <div class="form-actions">
      <button type="button" class="btn btn-outline" data-checkin="rotate">Neuen Code erzeugen</button>
      <button type="button" class="btn btn-primary" data-checkin="print">Drucken</button></div>
    <p class="muted small">Anmelden kann sich nur, wer die PIN einer Übung kennt (Einsätze → Übungen, Übung aufklappen; wird beim Anlegen erzeugt). Anmeldungen warten dort auf deine Bestätigung. „Neuen Code erzeugen“ macht ausgehängte Codes ungültig.</p>`;
}

async function openCheckin() {
  try { await renderCheckin(); } catch (e) { toast(e.message); return; }
  if (!checkinDialog().open) checkinDialog().showModal();
}

async function checkinClick(e) {
  const button = e.target.closest("[data-checkin]");
  if (!button) return;
  if (button.dataset.checkin === "print") {
    document.body.classList.add("print-checkin"); window.print(); document.body.classList.remove("print-checkin"); return;
  }
  if (!confirm("Neuen Code erzeugen? Bereits ausgehängte QR-Codes funktionieren danach nicht mehr.")) return;
  try { await apiJson("/api/trainings/checkin/rotate", "POST", {}); await renderCheckin(); toast("Neuer Code erzeugt."); }
  catch (err) { toast(err.message); }
}

const closeTrainingForm = () => { if (trainingDialog().open) trainingDialog().close(); };

function showTrainings() {
  if (state.view === "trainings" || state.view === "training_members") VIEWS[state.view].render();
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
  let saved;
  try {
    saved = await apiJson(d.id ? `/api/trainings/${d.id}` : "/api/trainings", d.id ? "PUT" : "POST", trainingPayload(d));
  } catch (e) { toast(e.message); return; }
  const year = Number(d.startDate.slice(0, 4));
  closeTrainingForm();
  await reloadTrainings();
  showTrainings();
  const pin = !d.id && saved?.checkin_pin ? ` Anmelde-PIN für den QR-Code: ${saved.checkin_pin}` : "";
  toast((year === state.year ? "Übung gespeichert." : `Übung gespeichert (Jahr ${year}).`) + pin, pin ? { duration: 15000 } : undefined);
}

function deleteTraining(id) {
  const training = trainingState.data.trainings.find((t) => t.id === id);
  if (!training) return;
  // Wie bei Einsätzen: erst ausblenden, endgültig löschen erst nach Ablauf der Rückgängig-Zeit
  trainingState.pendingDelete = id;
  showTrainings();
  let undone = false;
  toast("Übung gelöscht.", { action: "Rückgängig", duration: 6000, onAction: () => {
    undone = true; trainingState.pendingDelete = null; showTrainings();
  } });
  setTimeout(async () => {
    if (undone) return;
    try { await api(`/api/trainings/${id}?revision=${training.revision}`, { method: "DELETE" }); }
    catch (e) { toast(e.message); }
    trainingState.pendingDelete = null;
    await reloadTrainings();
    showTrainings();
  }, 6200);
}

/** PIN erzeugen bzw. wartende Anmeldungen übernehmen/ablehnen; danach neu laden (Revision und Teilnehmer ändern sich). */
async function checkinAction(url, method, message) {
  try { await api(url, { method }); } catch (err) { toast(err.message); return; }
  await reloadTrainings();
  showTrainings();
  toast(message);
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
    $(`#view-training_members [data-tr-sort="${field}"]`)?.focus({ preventScroll: true });
    return;
  }
  const link = e.target.closest("[data-tr-open]");
  if (link) {
    if (can("trainings.edit")) openTrainingForm(() => draftFromTraining(trainingState.data.trainings.find((t) => t.id === Number(link.dataset.trOpen))), Number(link.dataset.trOpen));
    return;
  }
  const person = e.target.closest("tr[data-tr-person]"), training = e.target.closest("tr[data-tr-training]");
  if (person || training) {
    const [set, id] = person ? [trainingState.openPeople, Number(person.dataset.trPerson)] : [trainingState.openTrainings, Number(training.dataset.trTraining)];
    if (set.has(id)) set.delete(id); else set.add(id);
    VIEWS[state.view].render();
    $(`#${$("#view-trainings").hidden ? "view-training_members" : "view-trainings"} tr[${person ? "data-tr-person" : "data-tr-training"}="${id}"]`)?.focus({ preventScroll: true });
    return;
  }
  if (e.target.closest("tr.detail") && !e.target.closest("[data-tr-action]")) return;
  const button = e.target.closest("[data-tr-action]");
  if (!button) return;
  const d = trainingState.draft;
  switch (button.dataset.trAction) {
    case "edit": openTrainingForm(() => draftFromTraining(trainingState.data.trainings.find((t) => t.id === Number(button.dataset.id))), Number(button.dataset.id)); break;
    case "delete": deleteTraining(Number(button.dataset.id)); break;
    case "qr": await openCheckin(); break;
    case "new-pin": if (confirm("Neue PIN erzeugen? Die bisherige PIN gilt danach nicht mehr.")) await checkinAction(`/api/trainings/${button.dataset.id}/checkin-pin`, "POST", "Neue PIN erzeugt."); break;
    case "accept-checkin": await checkinAction(`/api/trainings/${button.dataset.id}/checkins/${button.dataset.checkinId ? `${button.dataset.checkinId}/` : ""}accept`, "POST", "Anmeldung übernommen."); break;
    case "reject-checkin": await checkinAction(`/api/trainings/${button.dataset.id}/checkins/${button.dataset.checkinId}`, "DELETE", "Anmeldung abgelehnt."); break;
    case "cancel": closeTrainingForm(); break;
    case "save": await saveTraining(); break;
    case "all": for (const m of trainingState.data.members) if (m.active) d.memberIds.add(m.id); refreshTrainingPeople(); break;
    case "none": d.memberIds.clear(); d.newMembers = []; refreshTrainingPeople(); break;
    case "add-new": addNewTrainingMember(); break;
  }
}

VIEWS.trainings = { label: "Übungen", sub: "Übungen", title: "Übungen", load: loadTrainings, render: renderTrainings,
  permission: "trainings.view", single: true, help: "sec_training" };
VIEWS.training_members = { label: "Übungen", sub: "Übungen", title: "Übungen", load: loadTrainings, render: renderTrainingMembers,
  permission: "trainings.view", single: true, help: "sec_training" };

$("#btn-training").addEventListener("click", () => openTrainingForm(emptyTrainingDraft, "new"));
for (const view of [$("#view-trainings"), $("#view-training_members")]) view.addEventListener("click", trainingClick);
for (const view of [$("#view-trainings"), $("#view-training_members")]) view.addEventListener("keydown", (e) => {
  const row = e.target.closest("tr[data-tr-person], tr[data-tr-training], tr[data-tr-open]");
  if (row && e.target === row && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); row.click(); }
});
trainingDialog().addEventListener("click", trainingClick);
checkinDialog().addEventListener("click", checkinClick);
trainingDialog().addEventListener("close", () => { trainingState.editing = trainingState.draft = null; });
trainingDialog().addEventListener("change", (e) => {
  if (e.target.dataset.trFlag) trainingState.draft[e.target.dataset.trFlag] = e.target.checked;
});
trainingDialog().addEventListener("input", (e) => {
  if (e.target.dataset.tr) updateDraftField(e.target);
  if (e.target.id === "tr-search") { trainingState.search = e.target.value; refreshTrainingPeople(); }
});
trainingDialog().addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.target.id === "tr-new-last" || e.target.id === "tr-new-first")) { e.preventDefault(); addNewTrainingMember(); }
});
// Daten wurden neu geladen: beim nächsten Laden frisch holen, die gezeichnete Ansicht behält ihre Daten
document.addEventListener("app:data", () => { trainingState.stale = true; });
