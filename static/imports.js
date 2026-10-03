"use strict";

// ------------------------------------------------------------ Bericht einlesen (PDF oder Excel-Export)
// Herkunft eines Einsatzes: Bericht als PDF bzw. Excel-Export des BKS-Portals oder frühere Einsatzübersicht
const SOURCES = { pdf: "PDF", bks_xlsx: "Excel-Export BKS" };

function sourceLabel(e) {
  return SOURCES[e.source] ? `${SOURCES[e.source]} · ${esc(e.filename)}` : "Einsatzübersicht (Excel)";
}

function showUploadError(html) {
  const el = $("#pdf-error");
  el.innerHTML = html;
  el.hidden = false;
}

let uploadBusy = false;
let uploadGeneration = 0, acceptingReports = 0;
async function discardUpload() {
  uploadGeneration++;
  const token = state.upload.token;
  if (token) await apiJson("/api/reports/cancel", "POST", { token });
  state.upload = { token: null, reports: [], errors: [], notes: [] };
  renderPreviews();
}
async function readPdfs(files) {
  if (acceptingReports) { showUploadError("Eine Übernahme läuft. Bitte warten."); return; }
  if (uploadBusy) { showUploadError("Ein Import wird bereits gelesen. Bitte warten."); return; }
  if (state.upload.reports.some((r) => !r.saved && !isUnchanged(r)) &&
      !window.confirm("Offene Vorschauen verwerfen und neue Berichte einlesen?")) return;
  files = [...files].filter((f) => /\.(pdf|xlsx|zip)$/i.test(f.name));
  $("#pdf-error").hidden = true;
  if (!files.length) { showUploadError("Bitte eine PDF-, Excel- oder ZIP-Datei wählen."); return; }
  uploadBusy = true;
  const generation = ++uploadGeneration;
  $("#progress").hidden = false;
  const form = new FormData();
  for (const f of files) form.append("pdfs", f, f.name.normalize("NFC"));
  try {
    const data = await api("/api/reports", { method: "POST", body: form });
    if (generation !== uploadGeneration) {
      await apiJson("/api/reports/cancel", "POST", { token: data.token });
      return;
    }
    if (state.upload.token) await apiJson("/api/reports/cancel", "POST", { token: state.upload.token });
    await showUploadResult(data);
  } catch (e) {
    showUploadError(esc(e.message));
  } finally {
    $("#progress").hidden = true;
    uploadBusy = false;
  }
}

// Gelesene Berichte zeigen; neue Einsätze werden erst ausdrücklich übernommen.
async function showUploadResult(data) {
  // Erfasster Einsatz: Aktualisieren ist vorausgewählt (manuell ergänzte Fahrzeuge und Personen bleiben)
  state.upload = { token: data.token, reports: data.reports.map((r) => ({ ...r, replace: Boolean(r.existing && r.can_edit), saved: null })),
                   errors: data.errors, notes: data.notes || [] };
  if (data.errors.length) showUploadError(data.errors.map((e) => `${esc(e.file)}: ${esc(e.message)}`).join("<br>"));
  renderPreviews();
}

// Zu prüfen sind Berichte mit Prüfhinweisen, neuen Personen oder Abweichungen zu einem erfassten Einsatz
function reviewReasons(r) {
  const reasons = [];
  if (r.action) return reasons;
  if (r.warnings.length) reasons.push(plural(r.warnings.length, "Prüfhinweis", "Prüfhinweise"));
  const newPeople = r.people.filter((p) => p.new).length;
  if (newPeople) reasons.push(plural(newPeople, "neue Person", "neue Personen"));
  if (r.existing?.differences.length) reasons.push(plural(r.existing.differences.length, "Abweichung", "Abweichungen"));
  if (r.error) reasons.push(r.error);
  return reasons;
}

// Unveränderter, schon erfasster Einsatz: nichts zu tun
const isUnchanged = (r) => !r.action && r.existing && !r.existing.differences.length && !reviewReasons(r).length;

// Übersprungene Berichte (z. B. FEZ) und gespeicherte Stammdatensätze
function uploadNotes(notes) {
  return notes.length ? `<div class="message message-info">${notes.map((n) => `${esc(n.file)}: ${esc(n.message)}`).join("<br>")}</div>` : "";
}

function uploadSummary(reports) {
  const auto = reports.filter((r) => r.auto).length, unchanged = reports.filter(isUnchanged).length;
  const open = reports.filter((r) => !r.saved && !isUnchanged(r)).length;
  const parts = [];
  if (auto) parts.push(`${plural(auto, "Einsatz", "Einsätze")} ohne Anmerkungen übernommen`);
  if (unchanged) parts.push(`${plural(unchanged, "Einsatz", "Einsätze")} bereits unverändert erfasst`);
  if (open) parts.push(`${plural(open, "Bericht", "Berichte")} zu prüfen`);
  return parts.length ? `<div class="message message-info">${parts.join(" · ")}</div>` : "";
}

function previewStatus(r) {
  const existing = r.existing;
  const status = (cls, number, title, sub) =>
    `<div class="preview-status ${cls}"><span class="number">${number}</span><div><strong>${title}</strong><span>${sub}</span></div></div>`;
  if (r.saved) return status("done", "✓", `Einsatz ${r.saved.number ?? ""}/${r.saved.year} ist in der Statistik`,
    esc(r.filename) + (r.saved.postprocessing_pending ? " · Gespeichert; zentrale Nachverarbeitung noch offen. Kein erneuter Import nötig." : ""));
  if (existing) {
    const origin = { pdf: "aus einer PDF", bks_xlsx: "aus einem Excel-Export" }[existing.source] || "aus der Einsatzübersicht (Excel)";
    const diffs = existing.differences.length ? plural(existing.differences.length, "Abweichung", "Abweichungen") : "keine Abweichungen";
    return status("existing", r.number ?? "?", `Einsatz ${r.number}/${r.year} ist bereits erfasst`, `${origin} · ${diffs}`);
  }
  return status("", r.number ?? "?", `Neuer Einsatz ${r.number ?? ""}${r.number ? "/" + r.year : ""}${config.vg ? ` · ${esc(r.tenant_name)}` : ""}`,
    [esc(r.filename), ...reviewReasons(r).map(esc)].join(" · "));
}

function differencesTable(existing) {
  if (!existing?.differences.length) return "";
  return `<h4 class="section-gap">Abweichungen zur Statistik</h4>
    <table class="mini-table diff-table"><thead><tr><th>Feld</th><th>erfasst</th><th>Bericht</th></tr></thead><tbody>
    ${existing.differences.map((d) => `<tr><td>${esc(d.field)}</td><td>${esc(d.stored)}</td><td>${esc(d.report)}</td></tr>`).join("")}</tbody></table>`;
}

// Eingaben in den noch offenen Vorschauen vor dem Neuzeichnen übernehmen
function keepPreviewInput() {
  for (const card of $$(".preview-card[data-index]")) {
    const r = state.upload.reports[Number(card.dataset.index)];
    if (r && !r.saved && $("input[name]", card)) Object.assign(r, readForm(card));
  }
}

function renderPreviews() {
  const reports = state.upload.reports;
  $("#dropzone").classList.toggle("compact", reports.length > 0);
  $("#previews").innerHTML = uploadNotes(state.upload.notes || []) + uploadSummary(reports) + reports.map((r, i) => {
    if (r.action) return `<div class="preview-card" data-index="${i}"><div class="preview-body">
      <h3>${esc(r.title)}</h3><p>${esc(r.filename)}</p><p>${esc(r.saved?.message || r.message)}</p>
      ${r.saved ? "" : `<button type="button" class="btn btn-primary" data-accept="${i}">${r.action === "master" ? "Stammdatensatz speichern" : "Bericht weitergeben"}</button>`}
      </div></div>`;
    if (r.auto || isUnchanged(r)) return "";
    const existing = r.existing;
    return `<div class="preview-card" data-index="${i}">
      ${previewStatus(r)}
      ${r.saved ? "" : `<div class="preview-body">
        ${formFields(r)}
        <div class="preview-grid">
          <div class="panel outlined"><h4>Fahrzeuge${helpButton("vehicles")}</h4>${vehicleTable(r)}
            <p class="small muted section-gap">Ezeit erstes Fahrzeug: <b>${minutes(r.arrival_min)}</b> · Gesamtstärke ${r.crew_total}</p></div>
          <div class="panel outlined"><h4>Prüfhinweise${helpButton("warnings")}</h4>${warningsList(r.warnings, "Keine Prüfhinweise")}${differencesTable(existing)}
            ${r.shared_with?.length ? `<p class="small muted section-gap">Gemeinsamer Einsatz mit ${esc(r.shared_with.join(", "))} (gleicher Einsatz im BKS-Portal bzw. gleiche Einsatznummer der Leitstelle).</p>` : ""}
            ${r.bks_url ? `<p class="small muted section-gap">BKS-Portal: ${bksLink(r)}</p>` : ""}</div>
        </div>
        <div class="panel outlined">${attendancePanel(r, { markNew: true, pickLeader: true })}</div>
        <div class="preview-footer">
          ${existing && r.can_edit ? `<label class="toggle"><input type="checkbox" data-replace="${i}" ${r.replace ? "checked" : ""}> erfassten Einsatz mit diesem Bericht aktualisieren
            <span class="muted">(manuell ergänzte Fahrzeuge und Personen bleiben)</span></label>` : ""}
          ${existing && !r.can_edit ? `<span class="muted">Einen erfassten Einsatz aktualisiert, wer Einsätze bearbeiten darf.</span>` : ""}
          <button type="button" class="btn btn-primary" data-accept="${i}" ${existing && !r.replace ? "disabled" : ""}>
            ${existing ? "Aktualisieren" : "In Statistik übernehmen"}</button>
        </div>
      </div>`}
    </div>`;
  }).join("");
}

async function acceptReport(i) {
  if (uploadBusy) { toast("Bitte das laufende Einlesen abwarten."); return; }
  const r = state.upload.reports[i];
  const card = $(`.preview-card[data-index="${i}"]`);
  const button = $("[data-accept]", card);
  button.disabled = true;
  acceptingReports++;
  try {
    const saved = await apiJson("/api/reports/accept", "POST",
      { token: state.upload.token, filename: r.filename, fields: r.action ? {} : readForm(card),
        replace: r.replace, revision: r.existing?.revision });
    r.saved = saved;
    state.dataChanged = true;
    toast(saved.message || `Einsatz ${saved.number ?? ""}/${saved.year} ${r.existing ? "aktualisiert" : "übernommen"}`);
    keepPreviewInput();
    renderPreviews();
  } catch (err) {
    button.disabled = false;
    alert(err.message);
  } finally {
    acceptingReports--;
  }
}
