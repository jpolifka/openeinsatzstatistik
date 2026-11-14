"use strict";

// ------------------------------------------------------------ Bericht einlesen (PDF oder Excel-Export)
// Herkunft eines Einsatzes: Bericht als PDF bzw. Excel-Export des BKS-Portals oder frühere Einsatzübersicht
const SOURCES = { pdf: "PDF", bks_xlsx: "Excel-Export BKS" };

function sourceLabel(e) {
  return SOURCES[e.source] ? [SOURCES[e.source], e.filename && esc(e.filename)].filter(Boolean).join(" · ") : "Einsatzübersicht (Excel)";
}

/** Fehler im Einlese-Dialog: title nennt, was nicht geklappt hat; text (bereits maskiert) die Ursache und den nächsten Schritt. */
function showUploadError(title, text = "") {
  const el = $("#pdf-error");
  el.innerHTML = noticeBox("error", title, text);
  el.hidden = false;
}

let uploadBusy = false, bulkRunning = false;
let uploadGeneration = 0, acceptingReports = 0;
async function discardUpload() {
  uploadGeneration++;
  const token = state.upload.token;
  if (token) await apiJson("/api/reports/cancel", "POST", { token });
  state.upload = { token: null, reports: [], errors: [], notes: [] };
  renderPreviews();
}
async function readPdfs(files) {
  files = [...files];          // sofort kopieren: der Datei-Dialog leert seine Liste, noch bevor die Rückfrage beantwortet ist
  if (acceptingReports) { showUploadError("Eine Übernahme läuft.", "Bitte warten, bis sie fertig ist."); return; }
  if (uploadBusy) { showUploadError("Ein Import wird bereits gelesen.", "Bitte warten, bis er fertig ist."); return; }
  const open = state.upload.reports.filter((r) => !r.saved && !isUnchanged(r)).length;
  if (open && !await askConfirm({ title: "Offene Vorschauen verwerfen?",
    text: `${plural(open, "Bericht ist", "Berichte sind")} noch nicht übernommen. Korrekturen daran gehen verloren.`,
    confirm: "Vorschauen verwerfen und neu einlesen", danger: true })) return;
  files = [...files].filter((f) => /\.(pdf|xlsx|zip)$/i.test(f.name));
  $("#pdf-error").hidden = true;
  if (!files.length) { showUploadError("Keine passende Datei gewählt.", "Bitte eine PDF-, Excel- oder ZIP-Datei wählen."); return; }
  uploadBusy = true;
  const generation = ++uploadGeneration;
  $("#progress").hidden = false;
  const form = new FormData();
  for (const f of files) form.append("pdfs", f, f.name.normalize("NFC"));
  try {
    const data = await readInBackground(form);
    if (generation !== uploadGeneration) {
      await apiJson("/api/reports/cancel", "POST", { token: data.token });
      return;
    }
    if (state.upload.token) await apiJson("/api/reports/cancel", "POST", { token: state.upload.token });
    await showUploadResult(data);
  } catch (e) {
    showUploadError("Die Berichte konnten nicht gelesen werden.", `${esc(e.message)} Es wurde nichts gespeichert. Bitte die Dateien erneut einlesen.`);
  } finally {
    $("#progress").hidden = true;
    uploadBusy = false;
  }
}

// Hochladen, dann im Hintergrund lesen lassen und den Fortschritt abfragen: jede Anfrage bleibt kurz
// (Proxys wie Cloudflare brechen lange Anfragen nach etwa 100 s ab).
async function readInBackground(form) {
  const label = $("#progress-label"), track = $("#progress .progress-bar"), bar = $("span", track);
  label.textContent = "Berichte werden hochgeladen …";
  track.classList.remove("determinate");
  bar.style.width = "";
  const { job, total } = await api("/api/reports?background=true", { method: "POST", body: form });
  for (let wait = 400; ; wait = Math.min(wait * 1.5, 2000)) {
    await new Promise((resolve) => setTimeout(resolve, wait));
    const status = await api(`/api/reports/jobs/${encodeURIComponent(job)}`);
    if (status.done) return status;            // verworfen (generation): readPdfs gibt die Vorschau gleich frei
    label.textContent = `Berichte werden gelesen … ${status.read} von ${total}`;
    track.classList.add("determinate");
    bar.style.width = `${total ? (status.read / total) * 100 : 0}%`;
  }
}

// Gelesene Berichte zeigen; neue Einsätze werden erst ausdrücklich übernommen.
async function showUploadResult(data) {
  // Erfasster Einsatz: Aktualisieren ist vorausgewählt (manuell ergänzte Fahrzeuge und Personen bleiben)
  state.upload = { token: data.token, reports: data.reports.map((r) => ({ ...r, replace: Boolean(r.existing && r.can_edit), saved: null })),
                   errors: data.errors, notes: data.notes || [] };
  const first = state.upload.reports.findIndex((r) => isPending(r) && !r.action);
  if (first >= 0) state.upload.reports[first].open = true;     // offen ist zuerst nur ein Bericht, die übrigen zeigen ihr Statusband
  if (data.errors.length) {
    showUploadError(`${plural(data.errors.length, "Datei konnte", "Dateien konnten")} nicht gelesen werden.`,
      `${data.errors.map((e) => `${esc(e.file)}: ${esc(e.message)}`).join("<br>")}${data.reports.length ? "<br>Die übrigen Berichte stehen unten zur Prüfung bereit." : ""}`);
  } else {
    $("#pdf-error").hidden = true;
  }
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

// Ohne Prüfhinweise, noch nicht erfasst: kann in einem Schritt übernommen werden. Neue Personen sind kein Hindernis;
// die Sammelübernahme nennt sie vorher im Bestätigungsdialog.
const isClean = (r) => !r.action && !r.saved && !r.existing && !r.warnings.length && !r.error;
const isPending = (r) => !r.saved && !isUnchanged(r);
const newPeopleOf = (r) => r.people.filter((p) => p.new).map((p) => p.name);

function uploadSummary(reports) {
  const unchanged = reports.filter(isUnchanged).length;
  const open = reports.filter((r) => !r.saved && !isUnchanged(r)).length;
  const clean = reports.filter(isClean).length;
  const parts = [];
  if (unchanged) parts.push(`${plural(unchanged, "Einsatz", "Einsätze")} bereits unverändert erfasst`);
  const done = reports.filter((r) => r.saved).length;
  if (open) parts.push(`${plural(open, "Bericht", "Berichte")} offen`);
  if (done && open) parts.push(`${done} von ${done + open} übernommen`);
  if (!parts.length) return "";
  // Sammelübernahme nur ausdrücklich und nur für Berichte ohne Anmerkung; alles andere bleibt zur Prüfung
  const bulk = clean > 1 ? `<button type="button" class="btn btn-light" data-accept-clean ${acceptingReports || bulkRunning ? "disabled" : ""}>
      ${plural(clean, "Bericht ohne Hinweise", "Berichte ohne Hinweise")} übernehmen</button>` : "";
  const next = open > 1 ? `<button type="button" class="btn btn-outline" data-next-report>Nächster offener Bericht</button>` : "";
  return `<div class="message message-info preview-bulk"><span>${parts.join(" · ")}${clean > 1 ? ` · ${clean} davon ohne Hinweise` : ""}</span><span class="preview-bulk-actions">${next}${bulk}</span></div>`;
}

function previewStatus(r, i) {
  const existing = r.existing;
  // Neutral = bereit, Bernstein = zu prüfen, Grün = übernommen; das Wort steht immer dabei.
  // Offene Berichte lassen sich über das Band ein- und ausklappen (Knopf für die Tastatur, das ganze Band für die Maus).
  const toggle = r.saved || r.action ? "" : `<button type="button" class="status-toggle" aria-expanded="${r.open ? "true" : "false"}">${r.open ? "Einklappen" : "Öffnen"}</button>`;
  const status = (cls, tag, lead, title, sub) =>
    `<div class="preview-status ${cls}${toggle ? " toggles" : ""}"${toggle ? ` data-toggle-preview="${i}"` : ""}>${lead}<div><strong>${title}</strong><span class="status-sub">${sub}</span></div><span class="status-tag">${tag}</span>${toggle}</div>`;
  const number = (n) => `<span class="number">${n}</span>`;
  if (r.saved) return status("done", "Übernommen", ICON_CHECK.replace("<svg", '<svg class="status-icon"'),
    `Einsatz ${r.saved.number ?? ""}/${r.saved.year} ist in der Statistik`,
    esc(r.filename) + (r.saved.postprocessing_pending ? " · Gespeichert; zentrale Nachverarbeitung noch offen. Kein erneuter Import nötig." : ""));
  if (existing) {
    const origin = { pdf: "aus einer PDF", bks_xlsx: "aus einem Excel-Export" }[existing.source] || "aus der Einsatzübersicht (Excel)";
    const diffs = existing.differences.length ? plural(existing.differences.length, "Abweichung", "Abweichungen") : "keine Abweichungen";
    return status("existing review", "Zu prüfen", number(r.number ?? "?"), `Einsatz ${r.number}/${r.year} ist bereits erfasst`, `${origin} · ${diffs}`);
  }
  const reasons = reviewReasons(r);
  return status(reasons.length ? "review" : "", reasons.length ? "Zu prüfen" : "Bereit", number(r.number ?? "?"),
    `Neuer Einsatz ${r.number ?? ""}${r.number ? "/" + r.year : ""}${config.vg ? ` · ${esc(r.tenant_name)}` : ""}`,
    [esc(r.filename), ...reasons.map(esc)].join(" · "));
}

function differencesTable(existing) {
  if (!existing?.differences.length) return "";
  return `<h4 class="section-gap">Abweichungen zur Statistik</h4>
    <table class="mini-table diff-table"><thead><tr><th>Feld</th><th>erfasst</th><th>Bericht</th></tr></thead><tbody>
    ${existing.differences.map((d) => `<tr><td>${esc(d.field)}</td><td>${esc(d.stored)}</td><td>${esc(d.report)}${d.kept ? ' <span class="diff-kept">bleibt wie erfasst</span>' : ""}</td></tr>`).join("")}</tbody></table>`;
}

// Eingaben in den noch offenen Vorschauen vor dem Neuzeichnen übernehmen
function keepPreviewInput() {
  for (const card of $$(".preview-card[data-index]")) {
    const r = state.upload.reports[Number(card.dataset.index)];
    if (r && !r.saved && $("input[name]", card)) Object.assign(r, readForm(card));
  }
}

// Zuerst, was geprüft werden muss: Hinweise, Abweichungen zum erfassten Einsatz; ohne Anlass nur die ruhige Bestätigung
function reviewPanel(r) {
  const hasReview = r.warnings.length || r.existing?.differences.length;
  if (!hasReview) return `<div class="panel outlined"><h4>Prüfhinweise</h4>${warningsList([], "Keine Prüfhinweise")}</div>`;
  return `<div class="panel outlined preview-review"><h4>Zu prüfen</h4>${warningsList(r.warnings)}${differencesTable(r.existing)}</div>`;
}

function renderPreviews() {
  const reports = state.upload.reports;
  $("#dropzone").classList.toggle("compact", reports.length > 0);
  $("#previews").innerHTML = uploadNotes(state.upload.notes || []) + uploadSummary(reports) + reports.map((r, i) => {
    if (r.action) return `<div class="preview-card" data-index="${i}"><div class="preview-body">
      <h3>${esc(r.title)}</h3><p>${esc(r.filename)}</p><p>${esc(r.saved?.message || r.message)}</p>
      ${r.saved ? "" : `<button type="button" class="btn btn-primary" data-accept="${i}">${r.action === "master" ? "Stammdatensatz speichern" : "Bericht weitergeben"}</button>`}
      </div></div>`;
    if (isUnchanged(r)) return "";
    const existing = r.existing;
    return `<div class="preview-card" data-index="${i}">
      ${previewStatus(r, i)}
      ${r.saved || !r.open ? "" : `<div class="preview-body">
        ${reviewPanel(r)}
        ${reportSummary(r)}
        <div class="panel outlined">${attendancePanel(r, { markNew: true, pickLeader: true })}</div>
        <details class="all-fields" data-fields="${i}" ${r.allFields ? "open" : ""}>
          <summary>Alle Felder<span class="muted">Zeiten, Angaben und Fahrzeuge prüfen oder ändern</span></summary>
          <div class="all-fields-body">
            ${formFields(r)}
            <div class="panel outlined"><h4>Fahrzeuge</h4>${vehicleTable(r)}
              <p class="small muted section-gap">Zeit bis Eintreffen des ersten Fahrzeugs: <b>${minutes(r.arrival_min)}</b> · Gesamtstärke ${r.crew_total}</p>
              ${r.shared_with?.length ? `<p class="small muted section-gap">Gemeinsamer Einsatz mit ${esc(r.shared_with.join(", "))} (gleicher Einsatz im BKS-Portal bzw. gleiche Einsatznummer der Leitstelle).</p>` : ""}
              ${r.bks_url ? `<p class="small muted section-gap">BKS-Portal: ${bksLink(r)}</p>` : ""}</div>
          </div>
        </details>
        <div class="preview-failure">${r.failure ? noticeBox("error", r.failure.title, r.failure.text) : ""}</div>
        <div class="preview-footer">
          ${existing && r.can_edit ? `<label class="toggle"><input type="checkbox" data-replace="${i}" ${r.replace ? "checked" : ""}> erfassten Einsatz mit diesem Bericht aktualisieren
            <span class="muted">(manuell ergänzte Fahrzeuge und Personen bleiben)</span></label>` : ""}
          ${existing && !r.can_edit ? `<span class="muted">Einen erfassten Einsatz aktualisiert, wer Einsätze bearbeiten darf.</span>` : ""}
          ${existing && r.can_edit && !r.replace ? `<span class="small muted" id="replace-hint-${i}">Zum Aktualisieren erst das Feld links ankreuzen.</span>` : ""}
          <button type="button" class="btn btn-primary" data-accept="${i}" ${existing && !r.replace ? `disabled aria-describedby="replace-hint-${i}"` : ""}>
            ${existing ? "Aktualisieren" : "In Statistik übernehmen"}</button>
        </div>
      </div>`}
    </div>`;
  }).join("");
}

async function acceptReport(i) {
  if (uploadBusy) { toast("Bitte das laufende Einlesen abwarten."); return false; }
  const r = state.upload.reports[i];
  if (!r || r.saved) return false;                       // schon gespeichert: nie ein zweites Mal senden
  const card = $(`.preview-card[data-index="${i}"]`);
  const accept = $("[data-accept]", card);
  if (accept) accept.disabled = true;               // eingeklappte Berichte (Sammelübernahme) haben keinen Knopf
  acceptingReports++;
  let ok = false;
  try {
    const saved = await apiJson("/api/reports/accept", "POST",
      { token: state.upload.token, filename: r.filename, fields: r.action ? {} : r.open ? readForm(card) : storedFormValues(r),
        replace: r.replace, revision: r.existing?.revision });
    r.saved = saved;
    r.failure = null;
    r.open = false;
    state.dataChanged = true;
    toast(saved.message || `Einsatz ${saved.number ?? ""}/${saved.year} ${r.existing ? "aktualisiert" : "übernommen"}`);
    ok = true;
  } catch (err) {
    // Die Karte bleibt mit den Eingaben stehen; der Fehler erscheint an ihr und nennt den Bericht
    r.open = true;                                       // der Fehler steht in der geöffneten Karte
    r.failure = { title: `Einsatz ${r.number ?? ""}${r.number ? "/" + r.year : ""} (${r.filename}) wurde nicht übernommen.`,
      text: `${esc(err.message)} Ihre Eingaben bleiben erhalten. Bitte erneut „${r.existing ? "Aktualisieren" : "In Statistik übernehmen"}“ wählen.` };
  } finally {
    acceptingReports--;
  }
  keepPreviewInput();
  renderPreviews();                                      // erst nach dem Zählen: Sammelknopf und Karten stimmen wieder
  if (ok && !bulkRunning) openNextReport(i);             // nach dem Übernehmen weiter zum nächsten offenen Bericht
  return ok;
}

// Alle Berichte ohne Hinweise nacheinander übernehmen; Berichte mit Anmerkungen bleiben zur Prüfung stehen.
// Ein zweiter Aufruf (Doppelklick) tut nichts, solange der erste läuft.
async function acceptCleanReports() {
  if (bulkRunning || acceptingReports || uploadBusy) return;
  const planned = state.upload.reports.filter(isClean);
  const names = [...new Set(planned.flatMap(newPeopleOf))];
  if (names.length && !await askConfirm({ title: `${plural(planned.length, "Bericht", "Berichte")} übernehmen?`,
    text: `Dabei ${names.length === 1 ? "wird 1 neue Person" : `werden ${names.length} neue Personen`} angelegt: ${names.slice(0, 8).join("; ")}${names.length > 8 ? ` und ${names.length - 8} weitere` : ""}.`,
    confirm: "Übernehmen" })) return;
  bulkRunning = true;
  let saved = 0, failed = null;
  try {
    for (const r of planned) {
      if (r.saved || !isClean(r)) continue;              // inzwischen geändert oder gespeichert
      if (await acceptReport(state.upload.reports.indexOf(r))) saved++; else { failed = r; break; }   // beim ersten Fehler anhalten
    }
  } finally {
    bulkRunning = false;
    renderPreviews();
  }
  if (failed) failed.open = true; else openNextReport(-1);
  renderPreviews();
  const left = planned.length - saved;
  toast(failed ? `${plural(saved, "Bericht", "Berichte")} übernommen. Angehalten bei ${failed.filename}; ${plural(left, "Bericht", "Berichte")} offen.`
               : `${plural(saved, "Bericht", "Berichte")} übernommen`, { duration: failed ? 8000 : 3500 });
}

// Die Werte der Maske für einen eingeklappten Bericht (ohne Formular): so, wie readForm sie liefern würde
function storedFormValues(r) {
  return Object.fromEntries((config.incident_fields || []).filter(([name]) => name !== "unit_leader" || r.people_visible !== false)
    .map(([name, , type]) => [name, type === "number" ? (r[name] == null || r[name] === "" ? null : Number(r[name]))
      : type === "datetime-local" ? (r[name] || "").slice(0, 19) : (r[name] ?? "")]));
}

function focusReport(i) {
  const card = $(`.preview-card[data-index="${i}"]`);
  card?.scrollIntoView?.({ block: "nearest" });
  $(".status-toggle", card)?.focus?.();
}

// Band angeklickt: Bericht ein- oder ausklappen (Eingaben bleiben erhalten)
function toggleReport(i) {
  const r = state.upload.reports[i];
  if (!r || r.saved) return;
  keepPreviewInput();
  r.open = !r.open;
  renderPreviews();
  focusReport(i);
}

// Nächster Bericht, der noch offen ist (nach `after`, sonst von vorn); er wird geöffnet und bekommt den Fokus
function openNextReport(after = -1, closedOnly = false) {
  const reports = state.upload.reports;
  const candidate = (r) => isPending(r) && !r.action && !(closedOnly && r.open);
  const found = reports.findIndex((r, j) => j > after && candidate(r));
  const next = found >= 0 ? found : reports.findIndex(candidate);
  if (next < 0) return;
  keepPreviewInput();
  reports[next].open = true;
  renderPreviews();
  focusReport(next);
}

// Einzeiler der Vorschau: das Wichtigste eines Einsatzes, damit nicht jedes Feld gelesen werden muss
function reportSummary(r) {
  const when = r.started_at ? `${formatDate(r.started_at)} ${formatTime(r.started_at)}${r.ended_at ? `–${formatTime(r.ended_at)}` : ""}` : "";
  const code = r.keyword ? `<span class="keyword ${categoryOf(r.keyword).toLowerCase()}">${esc(r.keyword)}${r.subcode ? "." + esc(r.subcode) : ""}</span>` : "";
  const leader = r.people_visible === false ? ""
    : `<span data-oneline-leader>${r.unit_leader ? `Einheitsführung ${esc(r.unit_leader)}` : '<em class="field-missing">Einheitsführung fehlt</em>'}</span>`;
  const used = (r.vehicles || []).filter((v) => !isIdle(v)).length;
  const parts = [r.place && esc(r.place), when, leader, plural(used, "Fahrzeug", "Fahrzeuge"),
    r.arrival_min != null && `Eintreffen nach ${minutes(r.arrival_min)}`].filter(Boolean);
  return `<p class="preview-oneline">${code} <strong>${esc(r.description || "Einsatz ohne Beschreibung")}</strong><span class="oneline-rest">${parts.join(" · ")}</span></p>`;
}
