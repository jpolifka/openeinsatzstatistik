"use strict";

// Einsätze über Wehren hinweg: Hinweise an die Wehr (Import durch andere, Abweichungen, weitergegebene
// Berichte) und das Prüfprotokoll des Wehrleiters je Stammdatensatz im BKS-Portal.
// Wird nach app.js geladen und trägt sich in VIEWS ein. Rechte prüft das Backend (app/main.py, app/records.py).

const records = { notices: [], showNotices: true, data: null, onlyOpen: true, expanded: new Set(), scrollTo: null };

VIEWS.records = { label: "Prüfprotokoll", load: loadRecords, render: renderRecords,
  visible: () => Boolean(config.vg && config.manages_vg) };

const NOTICE_KINDS = { import: "Eingelesen", deviation: "Abweichung", missing: "Bericht fehlt", pending: "Zur Übernahme" };
const FINDING_KINDS = { vehicle: "Abweichung", keyword: "Stichwort", missing: "Bericht fehlt", unedited: "unbearbeitet",
  no_number: "ohne Nr." };

// ------------------------------------------------------------ Hinweise
async function loadNotices() {
  if (!config.tenants.length || !can("incidents")) return;
  try {
    records.notices = (await api("/api/notices")).notices;
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
  el.hidden = !list.length;
  if (!list.length) { el.innerHTML = ""; return; }
  const several = new Set(list.map((n) => n.tenant)).size > 1 || config.vg;
  el.innerHTML = `<div class="card notices no-print">
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

async function openNoticeIncident(n) {
  if (n.year && n.year !== state.year && state.years.includes(n.year)) {
    state.year = n.year;
    $("#year").value = String(n.year);
  }
  records.scrollTo = n.incident_key;
  if (location.hash === "#incidents") {
    state.expanded.add(n.incident_key);
    await showView();
  } else {
    // Der Wechsel des Reiters leert state.expanded (Listener in app.js); danach aufklappen –
    // gezeichnet wird erst, wenn die Einsätze geladen sind
    window.addEventListener("hashchange", () => state.expanded.add(n.incident_key), { once: true });
    location.hash = "#incidents";
  }
}

// Weitergegebene Berichte einer Wehr lesen und wie hochgeladene PDFs zur Übernahme anzeigen
async function readPendingReports(slug) {
  const pending = (await api("/api/pending")).reports.filter((p) => p.tenant === slug);
  if (!pending.length) { toast("Es liegt kein Bericht mehr zur Übernahme bereit."); await loadNotices(); return; }
  if (!state.incidents) { try { await loadIncidents(); } catch (e) { /* nur für Vorschläge */ } }
  updateDatalists();
  $("#pdf-error").hidden = true;
  $("#pdf-dialog").showModal();
  $("#progress").hidden = false;
  try {
    await showUploadResult(await apiJson("/api/pending/read", "POST", { ids: pending.map((p) => p.id) }));
  } catch (e) {
    showUploadError(esc(e.message));
  } finally {
    $("#progress").hidden = true;
  }
}

$("#notices").addEventListener("click", async (e) => {
  const button = e.target.closest("button");
  if (!button) return;
  const find = (id) => records.notices.find((n) => n.id === Number(id));
  try {
    if (button.matches("[data-notices-toggle]")) { records.showNotices = !records.showNotices; renderNotices(); }
    if (button.dataset.noticeOpen) await openNoticeIncident(find(button.dataset.noticeOpen));
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
// Nach „Einsatz öffnen“: aufgeklappten Einsatz in den sichtbaren Bereich holen
document.addEventListener("app:view", () => {
  if (!records.scrollTo) return;
  $(`#incident-table tr.row[data-id="${CSS.escape(records.scrollTo)}"]`)?.scrollIntoView({ block: "start", behavior: "smooth" });
  records.scrollTo = null;
});

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
    ${entry.findings.length ? `<div class="actions panel full bare no-print">
      ${entry.reviewed ? `<button type="button" class="btn btn-outline btn-small" data-review="${id}" data-done="0">Prüfvermerk entfernen</button>`
        : `<button type="button" class="btn btn-primary btn-small" data-review="${id}" data-done="1">Als geprüft markieren</button>`}
    </div>` : ""}
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
