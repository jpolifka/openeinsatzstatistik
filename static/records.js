"use strict";

// Einsätze über Wehren hinweg: Hinweise an die Wehr (Import durch andere, Abweichungen, weitergegebene
// Berichte) und das Prüfprotokoll des Wehrleiters je Stammdatensatz im BKS-Portal.
// Wird nach app.js geladen und trägt sich in VIEWS ein. Rechte prüft das Backend (app/main.py, app/records.py).

const records = { notices: [], postprocessing: [], showNotices: true, data: null, onlyOpen: true, expanded: new Set() };
// Kostenersatz: Eingaben im Dialog und letztes Ergebnis (nur berechnet, nichts gespeichert)
const feeCalc = { record: null, request: null, result: null, error: "" };

VIEWS.records = { label: "Berichte abgleichen", sub: "Berichte abgleichen", load: loadRecords, render: renderRecords, help: "records",
  visible: () => Boolean(config.vg && config.vg_permissions.includes("vg.records")) };

const NOTICE_KINDS = { import: "Eingelesen", deviation: "Abweichung", missing: "Bericht fehlt", pending: "Zur Übernahme" };
const FINDING_KINDS = { vehicle: "Abweichung", keyword: "Stichwort", missing: "Bericht fehlt", unedited: "unbearbeitet",
  no_number: "ohne Nr." };

// ------------------------------------------------------------ Hinweise
async function loadNotices() {
  if (!config.tenants.length || !can("incidents.view")) return;
  try {
    records.notices = (await api("/api/notices")).notices;
    records.postprocessing = can("reports.import") ? (await api("/api/pending")).postprocessing || [] : [];
  } catch (e) {
    records.notices = [];
  }
  renderNotices();
}

// Einsatz zu einem Hinweis nur öffnen, wenn er in der jetzigen Auswahl liegt
const noticeInScope = (n) => Boolean(config.vg || config.tenant?.slug === n.tenant);

function noticeActions(n) {
  const open = n.incident_key && noticeInScope(n)
    ? `<button type="button" class="btn btn-light btn-small" data-notice-open="${n.id}">Einsatz öffnen</button>` : "";
  const take = n.kind === "pending" && n.can_close && noticeInScope(n)
    ? `<button type="button" class="btn btn-primary btn-small" data-notice-pending="${esc(n.tenant)}">Übernehmen</button>` : "";
  const done = n.can_close ? `<button type="button" class="btn btn-outline btn-small" data-notice-done="${n.id}">Erledigt</button>` : "";
  return open + take + done;
}

function renderNotices() {
  const el = $("#notices"), list = records.notices;
  const jobs = records.postprocessing;
  el.hidden = !list.length && !jobs.length;
  if (el.hidden) { el.innerHTML = ""; return; }
  const several = new Set(list.map((n) => n.tenant)).size > 1 || config.vg;
  el.innerHTML = `${jobs.length ? `<div class="message message-info">Gespeichert, zentrale Nachverarbeitung noch offen: ${jobs.map((j) => `${esc(j.tenant_name)} (${j.count})`).join(" · ")}. Automatische Wiederholung jede Minute; nicht erneut importieren.</div>` : ""}<div class="card notices no-print">
    <div class="notices-head">
      <strong>${plural(list.length, "Hinweis", "Hinweise")}${helpButton("notices")}</strong>
      <button type="button" class="btn btn-light btn-small" data-notices-toggle>${records.showNotices ? "Ausblenden" : "Anzeigen"}</button>
    </div>
    ${records.showNotices ? `<ul class="notice-list">${list.map((n) => `<li class="notice">
      <span class="notice-kind kind-${esc(n.kind)}">${esc(NOTICE_KINDS[n.kind] || n.kind)}</span>
      <div class="notice-body">
        <span class="notice-text">${esc(n.text)}</span>
        <span class="notice-meta">${several ? `${esc(n.tenant_name)} · ` : ""}${formatDate(n.created)} ${formatTime(n.created.replace(" ", "T"))}</span>
      </div>
      <div class="notice-actions">${noticeActions(n)}</div>
    </li>`).join("")}</ul>` : ""}
  </div>`;
}

// Weitergegebene Berichte einer Wehr lesen und wie hochgeladene PDFs zur Übernahme anzeigen
async function readPendingReports(slug) {
  if (uploadBusy || acceptingReports) { toast("Bitte den laufenden Import abwarten."); return; }
  if (state.upload.reports.some((r) => !r.saved && !isUnchanged(r)) &&
      !window.confirm("Offene Vorschauen verwerfen und bereitliegende Berichte prüfen?")) return;
  await discardUpload();
  uploadBusy = true;
  const generation = uploadGeneration;
  try {
  const pending = (await api("/api/pending")).reports.filter((p) => p.tenant === slug);
  if (!pending.length) { toast("Es liegt kein Bericht mehr zur Übernahme bereit."); await loadNotices(); return; }
  if (!state.incidents) { try { await loadIncidents(); } catch (e) { /* nur für Vorschläge */ } }
  updateDatalists();
  $("#pdf-error").hidden = true;
  $("#pdf-dialog").showModal();
  $("#progress").hidden = false;
  try {
    const data = await apiJson("/api/pending/read", "POST", { ids: pending.map((p) => p.id) });
    if (generation !== uploadGeneration) {
      await apiJson("/api/reports/cancel", "POST", { token: data.token });
      return;
    }
    await showUploadResult(data);
  } catch (e) {
    showUploadError(esc(e.message));
  } finally {
    $("#progress").hidden = true;
  }
  } finally {
    uploadBusy = false;
  }
}

$("#notices").addEventListener("click", async (e) => {
  const button = e.target.closest("button");
  if (!button) return;
  const find = (id) => records.notices.find((n) => n.id === Number(id));
  try {
    if (button.matches("[data-notices-toggle]")) { records.showNotices = !records.showNotices; renderNotices(); }
    if (button.dataset.noticeOpen) {
      const n = find(button.dataset.noticeOpen);
      await openIncident(n.incident_key, n.year);
    }
    if (button.dataset.noticePending) await readPendingReports(button.dataset.noticePending);
    if (button.dataset.noticeDone) {
      await api(`/api/notices/${button.dataset.noticeDone}/done`, { method: "POST" });
      await loadNotices();
    }
  } catch (err) {
    alert(err.message);
  }
});
document.addEventListener("app:data", loadNotices);

// ------------------------------------------------------------ Prüfprotokoll
// Bei jedem Anzeigen neu: Berichte und Hinweise ändern sich auch durch andere Wehren
async function loadRecords() {
  records.data = await api(`/api/records?year=${state.year}`);
}

function recordStatus(entry) {
  if (!entry.findings.length) return `<span class="record-status ok">ohne Befund</span>`;
  if (entry.reviewed) return `<span class="record-status ok" data-tip="${esc(`${entry.reviewed.by || "lokal"}, ${formatDate(entry.reviewed.at)}`)}">geprüft</span>`;
  return `<span class="record-status open">${plural(entry.findings.length, "Befund", "Befunde")}</span>`;
}

function recordTitle(entry) {
  const r = entry.record, first = entry.incidents[0] || {};
  const keyword = r.keyword ? `${r.keyword}${r.subcode ? "." + r.subcode : ""}` : first.keyword;
  const place = r.district || r.town || first.place;
  return [keyword, r.reported_as, place].filter(Boolean).map(esc).join(" · ") || "–";
}

const findingValue = (v) => v == null || v === "" ? "–" : esc(v);

function recordDetail(entry) {
  const reports = entry.incidents.map((i) => `<tr>
      <td>${esc(i.tenant_name)}</td><td>${i.number ?? "–"}</td><td>${esc(i.keyword || "–")}</td>
      <td class="right">${i.people}</td><td>${i.bks_report_id ? esc(i.bks_report_id) : "–"}</td></tr>`).join("");
  const findings = entry.findings.map((f) => `<tr>
      <td>${esc(f.tenant_name)}</td><td>${esc(FINDING_KINDS[f.kind] || f.kind)}</td><td>${findingValue(f.vehicle)}</td>
      <td>${findingValue(f.field)}</td><td>${findingValue(f.source)}</td><td>${findingValue(f.stored)}</td></tr>`).join("");
  const id = esc(entry.record.bks_record_id);
  return `<div class="detail-grid record-grid">
    <div class="panel"><h4>Berichte der Wehren</h4>
      ${reports ? `<table class="mini-table"><thead><tr><th>Wehr</th><th>Nr.</th><th>Stichwort</th><th class="right">Personen</th><th>BKS-Bericht</th></tr></thead><tbody>${reports}</tbody></table>`
        : `<p class="muted small">Noch kein Bericht einer Wehr erfasst.</p>`}
      <p class="small muted section-gap">Stammdatensatz ${id}${entry.record.dispatch_number ? ` · Einsatznummer Leitstelle ${esc(entry.record.dispatch_number)}` : ""}${entry.record.first_alarm ? "" : " · Stammdatensatz nicht eingelesen"}</p>
    </div>
    <div class="panel"><h4>Befunde${helpButton("findings")}</h4>
      ${findings ? `<table class="mini-table"><thead><tr><th>Wehr</th><th>Art</th><th>Fahrzeug</th><th>Wert</th><th>Stammdatensatz / Leitstelle</th><th>Bericht der Wehr</th></tr></thead><tbody>${findings}</tbody></table>`
        : `<p class="muted small">Keine Abweichungen.</p>`}
    </div>
    <div class="actions panel full bare no-print">
      ${entry.incidents.length ? `<button type="button" class="btn btn-light btn-small" data-fees="${id}">Kostenersatz berechnen</button>` : ""}
      ${!entry.findings.length ? "" : entry.reviewed ? `<button type="button" class="btn btn-outline btn-small" data-review="${id}" data-done="0">Prüfvermerk entfernen</button>`
        : `<button type="button" class="btn btn-primary btn-small" data-review="${id}" data-done="1">Als geprüft markieren</button>`}
    </div>
  </div>`;
}

function renderRecords() {
  const all = records.data.records;
  const open = all.filter((e) => e.findings.length && !e.reviewed);
  const shown = records.onlyOpen ? open : all;
  const rows = shown.map((entry) => {
    const id = entry.record.bks_record_id, expanded = records.expanded.has(id);
    const tenants = entry.incidents.map((i) => `${esc(i.tenant_name)}${i.number != null ? " " + i.number : ""}`).join(", ");
    return `<tr class="row ${expanded ? "open" : ""}" data-record="${esc(id)}">
        <td>${formatDate(entry.started_at)}</td><td>${recordTitle(entry)}</td><td>${tenants || "–"}</td>
        <td>${recordStatus(entry)}</td><td class="col-toggle">${ICON_CHEVRON}</td></tr>
      <tr class="detail record-detail" ${expanded ? "" : "hidden"}><td colspan="5">${recordDetail(entry)}</td></tr>`;
  }).join("");
  $("#view-records").innerHTML = `<div class="card list-card">
    <div class="toolbar no-print">
      <div class="segments" role="group" aria-label="Filter">
        <button type="button" data-records-filter="open" class="${records.onlyOpen ? "active" : ""}">Offen (${open.length})</button>
        <button type="button" data-records-filter="all" class="${records.onlyOpen ? "" : "active"}">Alle (${all.length})</button>
      </div>
      <div class="toolbar-right">${helpButton("records")}
        <button type="button" class="btn btn-light btn-small" data-records-print data-tip="Druckansicht, im Druckdialog „Als PDF sichern“">Drucken / PDF</button>
      </div>
    </div>
    <p class="print-only print-stamp">${esc(config.name)} · Prüfprotokoll ${state.year} · Stand ${formatDate(new Date().toISOString())}</p>
    <div class="table-wrap">
      <table class="table records-table">
        <thead><tr><th>Datum</th><th>Einsatz</th><th>Berichte</th><th>Status</th><th class="col-toggle"></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      ${shown.length ? "" : `<p class="empty-note">${records.onlyOpen ? "Keine offenen Befunde." : `Für ${state.year} sind keine Einsätze mit BKS-Stammdatensatz erfasst.`}</p>`}
    </div>
  </div>`;
}

$("#view-records").addEventListener("click", async (e) => {
  const filter = e.target.closest("[data-records-filter]");
  if (filter) { records.onlyOpen = filter.dataset.recordsFilter === "open"; renderRecords(); return; }
  if (e.target.closest("[data-records-print]")) { window.print(); return; }
  const fees = e.target.closest("[data-fees]");
  if (fees) { openFees(fees.dataset.fees); return; }
  const review = e.target.closest("[data-review]");
  if (review) {
    try {
      await apiJson(`/api/records/${encodeURIComponent(review.dataset.review)}/review`, "POST", { done: review.dataset.done === "1" });
      records.data = null;
      await loadRecords();
      renderRecords();
    } catch (err) {
      alert(err.message);
    }
    return;
  }
  if (e.target.closest("tr.detail")) return;
  const row = e.target.closest("tr[data-record]");
  if (!row) return;
  const id = row.dataset.record;
  if (records.expanded.has(id)) records.expanded.delete(id); else records.expanded.add(id);
  renderRecords();
});

// ------------------------------------------------------------ Kostenersatz nach der Gebührenordnung
const euro = (n) => n == null ? "–" : Number(n).toLocaleString("de-DE", { style: "currency", currency: "EUR" });
const hours = (h) => h == null ? "" : `${num(h, 1)} h`;

async function openFees(recordId) {
  feeCalc.record = recordId;
  feeCalc.request = { schedule_id: null, bma_cap: null, expenses: [], vat_percent: 0 };
  feeCalc.result = null;
  $("#fees-dialog").showModal();
  await calculateFees();
}

async function calculateFees() {
  try {
    feeCalc.result = await apiJson(`/api/records/${encodeURIComponent(feeCalc.record)}/fees`, "POST", feeCalc.request);
    feeCalc.error = "";
  } catch (e) {
    feeCalc.error = e.message;
  }
  renderFees();
}

function renderFees() {
  const r = feeCalc.result, q = feeCalc.request;
  if (!r) { $("#fees-body").innerHTML = feeCalc.error ? errorBox(feeCalc.error) : ""; return; }
  const first = r.incidents[0];
  $("#fees-subtitle").textContent = `${formatDate(first.started_at)} · ${r.keyword} · ${first.description || ""}`;
  const incidents = r.incidents.map((i) => `<tr><td>${esc(i.tenant)}</td><td>${i.number ?? "–"}</td>
    <td>${formatDate(i.started_at)} ${formatTime(i.started_at)} – ${formatTime(i.ended_at)}</td><td>${esc(i.place || "–")}</td></tr>`).join("");
  const positions = r.positions.map((p) => `<tr class="fee-${p.kind}">
    <td>${esc(p.tenant || "")}</td><td>${esc(p.label)}</td><td class="right">${p.count ?? ""}</td>
    <td class="right">${p.minutes == null ? "" : `${Math.round(p.minutes)} min`}</td><td class="right">${hours(p.hours)}</td>
    <td class="right">${p.rate == null ? "" : euro(p.rate)}</td><td class="right">${euro(p.amount)}</td></tr>`).join("");
  const expenses = q.expenses.map((x, i) => `<div class="inline-row">
    <input type="text" data-fee-expense="${i}" data-key="label" value="${esc(x.label)}" placeholder="z. B. Bindemittel" aria-label="Auslage">
    <input type="number" min="0" step="0.01" data-fee-expense="${i}" data-key="amount" value="${x.amount}" aria-label="Betrag in Euro" class="narrow">
    <button type="button" class="icon-button" data-fee-remove="${i}" aria-label="entfernen">✕</button></div>`).join("");
  $("#fees-body").innerHTML = `
    ${feeCalc.error ? errorBox(feeCalc.error) : ""}
    <div class="form-grid no-print">
      <label class="field span-3"><span>Gebührenordnung</span><select data-fee-option="schedule_id">
        ${r.schedules.map((x) => `<option value="${x.id}" ${x.id === r.schedule.id ? "selected" : ""}>${esc(x.name)} (ab ${formatDate(x.valid_from)})</option>`).join("")}</select></label>
      <label class="field"><span>Umsatzsteuer (%)</span><input type="number" min="0" max="100" step="1" data-fee-option="vat_percent" value="${q.vat_percent}"></label>
      ${r.alarm_system ? `<label class="toggle span-2"><input type="checkbox" data-fee-option="bma_cap" ${r.bma_cap ? "checked" : ""}> Fehlalarm Brandmeldeanlage (höchstens Pauschale)</label>` : ""}
    </div>
    <div class="no-print section-gap"><h4>Auslagen (mit Verwaltungszuschlag)</h4>${expenses}
      <button type="button" class="btn btn-light btn-small" data-fee-add>Auslage hinzufügen</button></div>
    <h4 class="section-gap">Einsatz</h4>
    <table class="mini-table"><thead><tr><th>Wehr</th><th>Nr.</th><th>Zeit</th><th>Ort</th></tr></thead><tbody>${incidents}</tbody></table>
    <h4 class="section-gap">Kostenaufstellung · ${esc(r.schedule.name)}</h4>
    <div class="table-wrap"><table class="mini-table fee-table"><thead><tr><th>Wehr</th><th>Position</th><th class="right">Anzahl</th>
      <th class="right">Dauer</th><th class="right">abgerechnet</th><th class="right">Satz</th><th class="right">Betrag</th></tr></thead>
      <tbody>${positions}</tbody>
      <tfoot>
        ${r.vat ? `<tr><td colspan="6">Summe netto</td><td class="right">${euro(r.net)}</td></tr>
          <tr><td colspan="6">Umsatzsteuer ${num(r.vat_percent, 1)} %</td><td class="right">${euro(r.vat)}</td></tr>` : ""}
        <tr class="fee-total"><td colspan="6">Gesamt</td><td class="right">${euro(r.total)}</td></tr>
      </tfoot></table></div>
    ${r.hints.length ? `<h4 class="section-gap">Hinweise</h4>${warningsList(r.hints)}` : ""}
    <p class="small muted section-gap">Fahrzeuge vom Ausrücken bis zum Einsatzende des Fahrzeugs, Einsatzkräfte von der Alarmierung bis zum Einsatzende; angefangene Stunden bis 30 Minuten als halbe, darüber als volle Stunde. Nur Berechnung – es wird nichts gespeichert. Stand ${formatDate(new Date().toISOString())}.</p>
    <div class="actions no-print"><button type="button" class="btn btn-primary btn-small" data-fee-print>Drucken / PDF</button></div>`;
}

$("#fees-body").addEventListener("change", async (e) => {
  const t = e.target, q = feeCalc.request;
  if (t.dataset.feeOption === "schedule_id") q.schedule_id = Number(t.value);
  else if (t.dataset.feeOption === "vat_percent") q.vat_percent = Number(t.value || 0);
  else if (t.dataset.feeOption === "bma_cap") q.bma_cap = t.checked;
  else if (t.dataset.feeExpense !== undefined) {
    const x = q.expenses[Number(t.dataset.feeExpense)];
    x[t.dataset.key] = t.dataset.key === "amount" ? Number(t.value || 0) : t.value;
  } else return;
  await calculateFees();
});
$("#fees-body").addEventListener("click", async (e) => {
  if (e.target.closest("[data-fee-add]")) { feeCalc.request.expenses.push({ label: "", amount: 0 }); renderFees(); return; }
  const remove = e.target.closest("[data-fee-remove]");
  if (remove) { feeCalc.request.expenses.splice(Number(remove.dataset.feeRemove), 1); await calculateFees(); return; }
  if (e.target.closest("[data-fee-print]")) {
    document.body.classList.add("print-fees");
    window.addEventListener("afterprint", () => document.body.classList.remove("print-fees"), { once: true });
    window.print();
  }
});
