"use strict";

// Atemschutz-Dokumentation (Hauptreiter „Atemschutz“, nach app.js geladen, trägt sich in VIEWS ein):
// „Meine Einträge“ zeigt nur die eigenen Daten der angemeldeten Person (Einsatz, Übung, Streckendurchgang, G26.3),
// „Auswertung“ (nur Wehrführung) zeigt je Person ausschließlich Summen. Die Person bestimmt der Server aus der
// angemeldeten E-Mail – das Frontend nennt nie eine Personen-ID. Ungültige Eingaben meldet der Server auf Deutsch.
const agt = {
  data: null, year: null, scope: null,        // eigene Daten (GET /api/atemschutz/me)
  form: null,                    // null | Entwurf eines Eintrags (id null = neu)
  candidates: null,              // null | Einsätze/Übungen zum Übernehmen
  summary: null, summaryYear: null,
  cosign: null, cosignYear: null, cosignOpen: false,   // Abzeichnen (Wehrführung)
};

const agtThisYear = () => new Date().getFullYear();
const agtToday = () => new Date().toISOString().slice(0, 10);

async function loadAgt() {
  if (agt.scope !== config.scope) { agt.scope = config.scope; agt.form = agt.candidates = null; agt.year = null; agt.summaryYear = null; }
  agt.data = await api(`/api/atemschutz/me?year=${agt.year || agtThisYear()}`);
  agt.year = agt.data.year || agt.year || agtThisYear();
}

async function loadAgtSummary() {
  agt.summary = await api(`/api/atemschutz/summary?year=${agt.summaryYear || agtThisYear()}`);
  agt.summaryYear = agt.summary.year;
}

async function loadAgtCosign() {
  agt.cosign = await api(`/api/atemschutz/cosign?year=${agt.cosignYear || agtThisYear()}`);
  agt.cosignYear = agt.cosign.year;
}

function agtYearSelect(years, current, attribute) {
  return `<label class="year-select no-print"><span>Jahr</span><select ${attribute} aria-label="Jahr wählen">
    ${years.map((y) => `<option ${y === current ? "selected" : ""}>${y}</option>`).join("")}</select></label>`;
}

/** Tage bis zum Datum (negativ = abgelaufen). */
function agtDaysLeft(iso) {
  return Math.round((new Date(`${iso}T00:00:00`) - new Date(`${agtToday()}T00:00:00`)) / 86400000);
}

function agtValidity(iso) {
  if (!iso) return `<span class="muted">nicht erfasst</span>`;
  const days = agtDaysLeft(iso);
  if (days < 0) return `<span class="warn-text"><b>${formatDate(iso)}</b> – abgelaufen</span>`;
  if (days <= 60) return `<span class="warn-text"><b>${formatDate(iso)}</b> – noch ${plural(days, "Tag", "Tage")}</span>`;
  return `<b>${formatDate(iso)}</b> <span class="muted">(noch ${plural(days, "Tag", "Tage")})</span>`;
}

// ------------------------------------------------------------ Eigene Ansicht
function emptyAgtDraft(kind = "strecke") {
  return { id: null, revision: null, kind, date: agtToday(), time: "19:00", duration: "", place: "", keyword: "",
    startBar: "", endBar: "", external: false, organisation: "", notes: "", source: null, locked: false };
}

function agtDraftFrom(e) {
  return { id: e.id, revision: e.revision, kind: e.kind, date: e.started_at.slice(0, 10), time: e.started_at.slice(11, 16),
    duration: String(e.duration_min), place: e.place || "", keyword: e.keyword || "", startBar: e.start_bar ?? "",
    endBar: e.end_bar ?? "", external: e.external, organisation: e.organisation || "", notes: e.notes || "",
    source: e.source_kind ? { kind: e.source_kind, id: e.source_id } : null, locked: Boolean(e.source_kind) };
}

function agtPayload(d) {
  const number = (v) => v === "" || v == null ? null : Number(v);
  if (d.source && !d.id) {       // Übernahme: Stichwort, Beginn und Ort holt der Server aus der Statistik
    return { source: d.source, duration_min: number(d.duration), start_bar: number(d.startBar), end_bar: number(d.endBar),
      notes: d.notes };
  }
  return { kind: d.kind, started_at: `${d.date}T${d.time}`, duration_min: number(d.duration), place: d.place,
    keyword: d.keyword, start_bar: number(d.startBar), end_bar: number(d.endBar), external: d.external,
    organisation: d.external ? d.organisation : null, notes: d.notes, revision: d.revision };
}

function agtField(label, name, value, { type = "text", span = "", attributes = "" } = {}) {
  return `<div class="field ${span}"><span><label for="agt-${name}">${label}</label></span>
    <input id="agt-${name}" data-agt="${name}" type="${type}" value="${esc(value)}" ${attributes}></div>`;
}

function agtFormHtml() {
  const d = agt.form, kinds = agt.data.kinds, max = agt.data.bar_max, fixed = d.locked || (d.source && !d.id);
  const lock = fixed ? "readonly" : "";
  const title = d.id ? "Eintrag bearbeiten" : d.source ? "Aus der Statistik übernehmen" : "Neuer Eintrag";
  return `<form class="card agt-form" data-agt-form novalidate>
    <h3>${title}</h3>
    ${fixed ? `<p class="small muted">Stichwort, Beginn und Ort stammen aus der Einsatzstatistik. Hier trägst du Dauer und Drücke ein.</p>` : ""}
    <div class="form-grid">
      <div class="field"><span><label for="agt-kind">Art</label></span>
        <select id="agt-kind" data-agt="kind" ${fixed ? "disabled" : ""}>${Object.entries(kinds).map(([k, label]) =>
          `<option value="${k}" ${d.kind === k ? "selected" : ""}>${esc(label)}</option>`).join("")}</select></div>
      ${agtField("Datum", "date", d.date, { type: "date", attributes: `${lock} required` })}
      ${agtField("Uhrzeit", "time", d.time, { type: "time", attributes: `${lock} required` })}
      ${agtField("Dauer (Minuten)", "duration", d.duration, { type: "number", attributes: 'min="1" max="1440" step="1" required inputmode="numeric"' })}
      ${agtField(d.kind === "uebung" ? "Thema" : "Stichwort", "keyword", d.keyword, { attributes: `${lock} maxlength="120"` })}
      ${agtField("Ort", "place", d.place, { attributes: `${lock && d.id ? "" : lock} maxlength="120"` })}
      ${agtField("Startdruck (bar)", "startBar", d.startBar, { type: "number", attributes: `min="0" max="${max}" step="1" inputmode="numeric"` })}
      ${agtField("Enddruck (bar)", "endBar", d.endBar, { type: "number", attributes: `min="0" max="${max}" step="1" inputmode="numeric"` })}
      ${fixed ? "" : `<label class="toggle span-2"><input type="checkbox" data-agt="external" ${d.external ? "checked" : ""}>
        Fremdeintrag (z. B. Werk- oder Berufsfeuerwehr)</label>
        ${d.external ? agtField("Organisation", "organisation", d.organisation, { span: "span-2", attributes: 'maxlength="120" required' }) : ""}`}
      ${agtField("Notiz", "notes", d.notes, { span: "span-2", attributes: 'maxlength="1000"' })}
    </div>
    <div class="form-actions">
      <button type="button" class="btn btn-outline btn-small" data-agt-action="cancel">Abbrechen</button>
      <button type="submit" class="btn btn-primary btn-small">Speichern</button></div></form>`;
}

function agtCandidatesHtml() {
  const rows = agt.candidates.map((c, i) => `<tr><td>${formatDate(c.started_at)}<span class="member-sub">${formatTime(c.started_at)}</span></td>
    <td>${c.source === "incident" ? "Einsatz" : "Übung"}</td><td><b>${esc(c.keyword || "–")}</b></td><td>${esc(c.place || "–")}</td>
    <td class="right">${c.taken ? `<span class="muted">übernommen</span>`
      : `<button type="button" class="btn btn-light btn-small" data-agt-action="take" data-index="${i}">Übernehmen</button>`}</td></tr>`).join("");
  return `<div class="card"><div class="toolbar"><div><h3>Einsätze und Übungen ${agt.data.year}</h3>
      <p class="muted small">Nur Einsätze und Übungen, bei denen du laut Anwesenheit dabei warst.</p></div>
      <button type="button" class="btn btn-outline btn-small" data-agt-action="close-candidates">Schließen</button></div>
    <div class="table-wrap"><table class="mini-table"><thead><tr><th>Datum</th><th>Art</th><th>Stichwort / Thema</th><th>Ort</th><th></th></tr></thead>
    <tbody>${rows || `<tr><td colspan="5" class="muted">Keine Teilnahme in ${agt.data.year} gefunden.</td></tr>`}</tbody></table></div></div>`;
}

function agtMedicalHtml() {
  const d = agt.data, current = d.medical[0];
  const history = d.medical.map((m) => `<tr><td>${formatDate(m.examined_on)}</td><td>${formatDate(m.valid_until)}</td>
    <td class="right no-print"><button type="button" class="btn btn-outline btn-small" data-agt-action="delete-medical" data-id="${m.id}">Löschen</button></td></tr>`).join("");
  const reminders = d.mail ? `<fieldset class="agt-reminder no-print"><legend class="small"><b>Erinnerung per E-Mail</b> an deine hinterlegte Adresse</legend>
      ${d.reminder_days.map((days) => `<label class="toggle"><input type="checkbox" data-agt-reminder="${days}" ${d.reminder.includes(days) ? "checked" : ""}>
        ${days === 60 ? "2 Monate" : days === 30 ? "1 Monat" : "2 Wochen"} vor Ablauf</label>`).join(" ")}</fieldset>`
    : `<p class="small muted no-print">E-Mail-Erinnerungen sind auf diesem Server nicht eingerichtet.</p>`;
  return `<div class="card"><div class="toolbar"><div><h3>G26.3 (Atemschutz-Untersuchung)</h3>
      <p>Gültig bis: ${agtValidity(current?.valid_until)}</p></div></div>
    <form class="toolbar-inline no-print" data-agt-medical novalidate>
      <label class="field"><span>Untersuchung am</span><input type="date" id="agt-examined" required value="${agtToday()}"></label>
      <label class="field"><span>Nächste Prüfung</span><input type="date" id="agt-valid" required></label>
      <button type="submit" class="btn btn-light btn-small">Nachweis eintragen</button></form>
    ${reminders}
    ${d.medical.length ? `<div class="table-wrap"><table class="mini-table"><thead><tr><th>Untersuchung</th><th>Nächste Prüfung</th><th class="no-print"></th></tr></thead><tbody>${history}</tbody></table></div>` : ""}</div>`;
}

/** Stand der Abzeichnung durch die Wehrführung: mit Namen und Datum; nach einer Änderung „veraltet“. */
function agtCosignBadge(c) {
  if (!c) return `<span class="muted small">–</span>`;
  return c.valid ? `<span class="tenant-badge signed" data-tip="${esc(formatDateTime(c.at))}">${esc(c.name)}</span>`
    : `<span class="tenant-badge stale" data-tip="Abgezeichnet von ${esc(c.name)} am ${formatDate(c.at)}, danach wurde der Eintrag geändert.">veraltet</span>`;
}

function agtEntriesHtml() {
  const d = agt.data, kinds = d.kinds;
  const rows = d.entries.map((e) => `<tr>
    <td>${formatDate(e.started_at)}<span class="member-sub">${formatTime(e.started_at)}</span></td>
    <td>${esc(kinds[e.kind])}${e.external ? ` <span class="tenant-badge">${esc(e.organisation)}</span>` : ""}</td>
    <td><b>${esc(e.keyword || "–")}</b></td><td class="hide-mobile">${esc(e.place || "–")}</td>
    <td class="right">${formatDuration(e.duration_min)}</td>
    <td class="right hide-mobile">${e.start_bar == null ? "–" : `${e.start_bar} → ${e.end_bar} bar`}</td>
    <td>${agtCosignBadge(e.cosign)}</td>
    <td class="right no-print"><button type="button" class="btn btn-light btn-small" data-agt-action="edit" data-id="${e.id}">Bearbeiten</button>
      <button type="button" class="btn btn-outline btn-small" data-agt-action="delete" data-id="${e.id}">Löschen</button></td></tr>`).join("");
  return `<div class="card list-card"><div class="table-wrap"><table class="table"><thead><tr><th>Datum</th><th>Art</th><th>Stichwort / Thema</th>
    <th class="hide-mobile">Ort</th><th class="right">Dauer</th><th class="right hide-mobile">Druck</th><th>Abgezeichnet</th><th class="no-print"></th></tr></thead>
    <tbody>${rows}</tbody></table></div>
    ${d.entries.length ? "" : `<p class="empty-note">Für ${d.year} ist noch nichts eingetragen.</p>`}</div>`;
}

/** Einsichten durch Superadmins (Support, Prüfung) in die eigenen Daten – für die Person immer sichtbar. */
function agtAdminAccessHtml() {
  const access = agt.data.admin_access || [];
  return `<div class="card"><h3>Einsicht durch die Administration</h3>
    <p class="small muted">Superadmins der Anwendung können deine Einträge in Ausnahmefällen (Support, Prüfung) nur lesend einsehen. Jede Einsicht wird hier vermerkt. Die Wehrführung sieht Summen und zeichnet Einträge ab (ohne Notizen).</p>
    ${access.length ? `<ul class="plain small">${access.map((x) => `<li>${esc(x.at)} · ${esc(x.email)}</li>`).join("")}</ul>` : `<p class="small">Bisher keine Einsicht.</p>`}</div>`;
}

function renderAgt() {
  const section = $("#view-atemschutz"), d = agt.data;
  if (!d) { loadAgt().then(() => state.view === "atemschutz" && renderAgt()); return; }
  if (!d.linked) {
    section.innerHTML = `<div class="card">${noticeBox("info", "Deine E-Mail-Adresse ist im Personalstamm dieser Wehr nicht hinterlegt.",
      "Bitte die Wehrführung, sie unter Einstellungen → Personen bei dir einzutragen. Danach siehst du hier deine eigene Atemschutz-Dokumentation.")}</div>`;
    return;
  }
  const totals = d.totals;
  const figures = Object.entries(d.kinds).map(([k, label]) => [formatDuration(totals[k].minutes), `${label} (${totals[k].count}×)`]);
  section.innerHTML = `
    <p class="print-only print-stamp">${esc(config.name)} · Atemschutz-Nachweis ${d.year} · ${esc(d.name)} · Stand ${formatDate(new Date().toISOString())}</p>
    <div class="card"><div class="toolbar"><div><h3>${esc(d.name)}</h3>
      <p class="muted small no-print">Diese Einträge sieht nur du – die Wehrführung sieht Summen und kann einzelne Einträge (ohne Notizen) mit ihrem Namen abzeichnen; Superadmins können sie in Ausnahmefällen lesend einsehen (siehe unten, jede Einsicht wird vermerkt). Fremdeinträge (Werkfeuerwehr, Berufsfeuerwehr) sind möglich.</p></div>
      ${agtYearSelect(d.years, d.year, "data-agt-year")}</div>
      ${keyFigures(figures)}
      <div class="form-actions left no-print"><button type="button" class="btn btn-primary btn-small" data-agt-action="new">Neuer Eintrag</button>
        <button type="button" class="btn btn-light btn-small" data-agt-action="candidates">Aus Einsatzstatistik übernehmen</button>
        <button type="button" class="btn btn-light btn-small" data-agt-action="print">Als PDF drucken</button></div></div>
    ${agt.form ? agtFormHtml() : ""}${agt.candidates ? agtCandidatesHtml() : ""}
    ${agtEntriesHtml()}${agtMedicalHtml()}<div class="no-print">${agtAdminAccessHtml()}</div>`;
}

async function agtReload() { await loadAgt(); if (state.view === "atemschutz") renderAgt(); }

async function agtRun(action, message) {
  try {
    await action();
    if (message) toast(message);
  } catch (err) { toast(err.message); }
}

async function agtSave() {
  const d = agt.form;
  await agtRun(async () => {
    const url = "/api/atemschutz/me/entries" + (d.id ? `/${d.id}` : "");
    await apiJson(url, d.id ? "PUT" : "POST", agtPayload(d));
    agt.form = null; agt.candidates = null;
    await agtReload();
  }, "Gespeichert.");
}

async function agtClick(e) {
  const reminder = e.target.closest("[data-agt-reminder]");
  if (reminder) return;                                                   // wirkt über das change-Ereignis
  const button = e.target.closest("[data-agt-action]");
  if (!button) return;
  const id = Number(button.dataset.id);
  switch (button.dataset.agtAction) {
    case "new": agt.form = emptyAgtDraft(); renderAgt(); $("#agt-kind")?.focus(); break;
    case "print": window.print(); break;
    case "cancel": agt.form = null; renderAgt(); break;
    case "edit": agt.form = agtDraftFrom(agt.data.entries.find((x) => x.id === id)); renderAgt(); $("#agt-duration")?.focus(); break;
    case "candidates":
      await agtRun(async () => {
        agt.candidates = (await api(`/api/atemschutz/me/candidates?year=${agt.data.year}`)).candidates;
        renderAgt();
      });
      break;
    case "close-candidates": agt.candidates = null; renderAgt(); break;
    case "take": {
      const c = agt.candidates[Number(button.dataset.index)];
      const minutes = c.ended_at ? Math.round((new Date(c.ended_at) - new Date(c.started_at)) / 60000) : "";
      agt.form = { ...emptyAgtDraft(c.source === "incident" ? "einsatz" : "uebung"), source: { kind: c.source, id: c.id },
        date: c.started_at.slice(0, 10), time: formatTime(c.started_at), duration: minutes > 0 ? String(minutes) : "",
        keyword: c.keyword || "", place: c.place || "", locked: true };
      agt.candidates = null; renderAgt(); $("#agt-duration")?.focus();
      break;
    }
    case "delete": {
      const entry = agt.data.entries.find((x) => x.id === id);
      if (!confirm("Diesen Eintrag löschen?")) break;
      await agtRun(async () => { await api(`/api/atemschutz/me/entries/${id}?revision=${entry.revision}`, { method: "DELETE" }); await agtReload(); }, "Eintrag gelöscht.");
      break;
    }
    case "delete-medical":
      if (!confirm("Diesen Nachweis löschen?")) break;
      await agtRun(async () => { await api(`/api/atemschutz/me/medical/${id}`, { method: "DELETE" }); await agtReload(); }, "Nachweis gelöscht.");
      break;
  }
}

function agtInput(e) {
  const field = e.target.dataset?.agt;
  if (!field || !agt.form) return;
  const d = agt.form;
  const map = { startBar: "startBar", endBar: "endBar" };
  if (e.target.type === "checkbox") { d[field] = e.target.checked; renderAgt(); $(`#agt-${field}`)?.focus(); return; }
  d[map[field] || field] = e.target.value;
  if (field === "kind") renderAgt();
}

async function agtSubmit(e) {
  if (e.target.matches("[data-agt-form]")) { e.preventDefault(); await agtSave(); }
  if (e.target.matches("[data-agt-medical]")) {
    e.preventDefault();
    await agtRun(async () => {
      await apiJson("/api/atemschutz/me/medical", "POST", { examined_on: $("#agt-examined").value, valid_until: $("#agt-valid").value });
      await agtReload();
    }, "Nachweis eingetragen.");
  }
}

async function agtChange(e) {
  if (e.target.matches("[data-agt-year]")) {
    agt.year = Number(e.target.value); agt.form = agt.candidates = null;
    await agtRun(agtReload);
  }
  if (e.target.matches("[data-agt-reminder]")) {
    const offsets = [...$$("[data-agt-reminder]")].filter((x) => x.checked).map((x) => Number(x.dataset.agtReminder));
    await agtRun(async () => {
      agt.data.reminder = (await apiJson("/api/atemschutz/me/reminder", "PUT", { offsets })).reminder;
    }, "Erinnerung gespeichert.");
    renderAgt();
  }
}

// ------------------------------------------------------------ Abzeichnen durch die Wehrführung
function renderAgtCosign() {
  const section = $("#view-agt_cosign"), c = agt.cosign;
  if (!c) { loadAgtCosign().then(() => state.view === "agt_cosign" && renderAgtCosign()); return; }
  const shown = agt.cosignOpen ? c.entries : c.entries.filter((e) => !e.cosign?.valid);
  const rows = shown.map((e) => `<tr><td><b>${esc(e.person)}</b></td>
    <td>${formatDate(e.started_at)}<span class="member-sub">${formatTime(e.started_at)}</span></td>
    <td>${esc(c.kinds[e.kind])}${e.external ? ` <span class="tenant-badge">${esc(e.organisation)}</span>` : ""}</td>
    <td>${esc(e.keyword || "–")}<span class="member-sub">${esc(e.place || "")}</span></td>
    <td class="right">${formatDuration(e.duration_min)}</td>
    <td class="right hide-mobile">${e.start_bar == null ? "–" : `${e.start_bar} → ${e.end_bar} bar`}</td>
    <td>${agtCosignBadge(e.cosign)}</td>
    <td class="right">${e.cosign?.valid
      ? `<button type="button" class="btn btn-outline btn-small" data-agt-cosign="withdraw" data-id="${e.id}">Zurücknehmen</button>`
      : `<button type="button" class="btn btn-light btn-small" data-agt-cosign="sign" data-id="${e.id}" data-revision="${e.revision}">${e.cosign ? "Erneut abzeichnen" : "Abzeichnen"}</button>`}</td></tr>`).join("");
  section.innerHTML = `<div class="card list-card"><div class="toolbar"><div><h3>Einträge abzeichnen ${c.year}</h3>
      <p class="muted small">Du bestätigst einen Eintrag mit deinem Namen; die Person sieht, wer abgezeichnet hat. Ändert sie den Eintrag danach, gilt die Abzeichnung als veraltet. Notizen siehst du nicht, jeder Abruf und jede Abzeichnung wird protokolliert. Eigene Einträge zeichnest du nicht selbst ab.</p></div>
      ${agtYearSelect(c.years, c.year, "data-agt-cosign-year")}</div>
    <label class="toggle"><input type="checkbox" data-agt-cosign-all ${agt.cosignOpen ? "checked" : ""}> auch bereits abgezeichnete zeigen</label>
    <div class="table-wrap"><table class="table"><thead><tr><th>Person</th><th>Datum</th><th>Art</th><th>Stichwort / Ort</th><th class="right">Dauer</th>
      <th class="right hide-mobile">Druck</th><th>Abgezeichnet</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
    ${shown.length ? "" : `<p class="empty-note">Nichts zum Abzeichnen in ${c.year}.</p>`}</div>`;
}

async function agtCosignClick(e) {
  const button = e.target.closest("[data-agt-cosign]");
  if (!button) return;
  const id = Number(button.dataset.id), sign = button.dataset.agtCosign === "sign";
  await agtRun(async () => {
    if (sign) await apiJson(`/api/atemschutz/cosign/${id}`, "POST", { revision: Number(button.dataset.revision) });
    else await api(`/api/atemschutz/cosign/${id}`, { method: "DELETE" });
    await loadAgtCosign(); renderAgtCosign();
  }, sign ? "Abgezeichnet." : "Abzeichnung zurückgenommen.");
}

// ------------------------------------------------------------ Auswertung der Wehrführung (nur Summen)
function renderAgtEval() {
  const section = $("#view-agt_eval"), s = agt.summary;
  if (!s) { loadAgtSummary().then(() => state.view === "agt_eval" && renderAgtEval()); return; }
  const cell = (k) => `<td class="right">${k.count ? `${formatDuration(k.minutes)} <span class="member-sub">${k.count}×</span>` : "–"}</td>`;
  const rows = s.people.map((p) => `<tr><td><b>${esc(p.name)}</b>${p.linked ? "" : ` <span class="tenant-badge">ohne E-Mail</span>`}</td>
    ${Object.keys(s.kinds).map((k) => cell(p.kinds[k])).join("")}
    <td class="right"><b>${formatDuration(p.minutes)}</b></td><td class="right">${agtValidity(p.valid_until)}</td></tr>`).join("");
  section.innerHTML = `<div class="card list-card"><div class="toolbar"><div><h3>Atemschutz je Person ${s.year}</h3>
      <p class="muted small">Nur Summen und das Ablaufdatum der G26.3 – keine Einzeleinträge, Drücke oder Orte. Zeiten sind die von den Personen selbst eingetragenen Dauern.</p></div>
      ${agtYearSelect(s.years, s.year, "data-agt-summary-year")}</div>
    <div class="table-wrap"><table class="table"><thead><tr><th>Person</th>${Object.values(s.kinds).map((l) => `<th class="right">${esc(l)}</th>`).join("")}
      <th class="right">Gesamt</th><th class="right">G26.3 gültig bis</th></tr></thead><tbody>${rows}</tbody></table></div>
    ${s.people.length ? "" : `<p class="empty-note">Keine aktiven Personen im Personalstamm.</p>`}</div>`;
}

VIEWS.atemschutz = { label: "Atemschutz", sub: "Meine Einträge", title: "Atemschutz", noYear: true, load: loadAgt, render: renderAgt,
  permission: "agt.own", single: true, help: "sec_atemschutz" };
VIEWS.agt_eval = { label: "Atemschutz", sub: "Auswertung", title: "Atemschutz-Auswertung", noYear: true, load: loadAgtSummary,
  render: renderAgtEval, permission: "agt.evaluate", single: true, help: "sec_atemschutz" };

VIEWS.agt_cosign = { label: "Atemschutz", sub: "Abzeichnen", title: "Atemschutz-Einträge abzeichnen", noYear: true,
  load: loadAgtCosign, render: renderAgtCosign, permission: "agt.evaluate", single: true, help: "agt_cosign" };

const agtView = $("#view-atemschutz");
agtView.addEventListener("click", agtClick);
agtView.addEventListener("input", agtInput);
agtView.addEventListener("change", agtChange);
agtView.addEventListener("submit", agtSubmit);
$("#view-agt_eval").addEventListener("change", async (e) => {
  if (!e.target.matches("[data-agt-summary-year]")) return;
  agt.summaryYear = Number(e.target.value);
  await agtRun(async () => { await loadAgtSummary(); renderAgtEval(); });
});
$("#view-agt_cosign").addEventListener("click", agtCosignClick);
$("#view-agt_cosign").addEventListener("change", async (e) => {
  if (e.target.matches("[data-agt-cosign-all]")) { agt.cosignOpen = e.target.checked; renderAgtCosign(); return; }
  if (!e.target.matches("[data-agt-cosign-year]")) return;
  agt.cosignYear = Number(e.target.value);
  await agtRun(async () => { await loadAgtCosign(); renderAgtCosign(); });
});
