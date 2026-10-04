"use strict";

// Auftragsverarbeitung (AVV) je Verbandsgemeinde: ausfüllen, Vertrag drucken, unterschriebenes PDF
// hochladen oder Link hinterlegen; der Superadmin bestätigt. Solange kein AVV vorliegt, sind die
// Wehren der VG gesperrt (Backend: tenancy.access_for, app/dpa.py). Wird nach app.js geladen.

const dpaState = { data: null, error: "" };

VIEWS.dpa = { label: "Datenschutz & Vertrag", sub: "Datenschutz & Vertrag", load: loadDpa, render: renderDpa, noYear: true, help: "dpa",
  visible: () => config.superadmin || config.dpa_blocked.length > 0 || can("dpa.edit") };

async function loadDpa() {
  dpaState.data = await api("/api/dpa");
}

const dpaStep = (done, text) => `<li class="${done ? "done" : ""}">${done ? "✓" : "○"} ${text}</li>`;

function dpaCard(d) {
  const statuses = dpaState.data.statuses;
  const generated = Boolean(d.generated_hash);
  const stored = d.document_file || d.document_link;
  const form = d.can_edit ? `<div class="form-grid section-gap">${d.fields.map((f) =>
    `<label class="field ${f.key === "client_address" ? "span-6" : "span-3"}"><span>${esc(f.label)}</span>
      ${f.key === "client_address" ? `<textarea rows="2" data-dpa-field="${f.key}">${esc(f.value)}</textarea>`
        : `<input type="text" data-dpa-field="${f.key}" value="${esc(f.value)}">`}</label>`).join("")}</div>
    <div class="admin-actions left"><button type="button" class="btn btn-primary btn-small" data-dpa-action="save" data-slug="${esc(d.slug)}">Speichern und Vertrag erzeugen</button></div>` : "";
  const documentLinks = `<div class="admin-actions left">
      ${generated ? `<a class="btn btn-light btn-small" href="/api/dpa/${encodeURIComponent(d.slug)}/document" target="_blank" rel="noopener">Vertrag öffnen / drucken</a>` : ""}
      ${d.document_file && (d.can_edit || dpaState.data.superadmin) ? `<a class="btn btn-outline btn-small" href="/api/dpa/${encodeURIComponent(d.slug)}/file">Unterschriebenes PDF</a>` : ""}
      ${d.document_link ? `<a class="btn btn-outline btn-small" href="${esc(d.document_link)}" target="_blank" rel="noopener noreferrer">Ablage der VG</a>` : ""}
    </div>`;
  const upload = d.can_edit && generated ? `<h4 class="section-gap">Unterschriebenen Vertrag hinterlegen</h4>
    <div class="inline-row">
      <label class="btn btn-light btn-small file-button">PDF hochladen<input type="file" accept="application/pdf" data-dpa-upload="${esc(d.slug)}" hidden></label>
      <span class="small muted">und/oder Link zur Ablage der VG:</span>
      <input type="url" data-dpa-link="${esc(d.slug)}" value="${esc(d.document_link || "")}" placeholder="https://…" class="wide">
      <button type="button" class="btn btn-outline btn-small" data-dpa-action="link" data-slug="${esc(d.slug)}">Link speichern</button>
    </div>
    ${d.document_hash ? `<p class="small muted">Hochgeladen, Prüfsumme ${esc(d.document_hash.slice(0, 16))}…</p>` : ""}` : "";
  const admin = dpaState.data.superadmin ? `<h4 class="section-gap">Betreiber</h4>
    ${d.processor_missing.length ? `<div class="message message-error">Angaben zum Auftragnehmer fehlen in .env: ${d.processor_missing.map(esc).join(", ")}.</div>` : ""}
    <div class="form-grid">
      <label class="field span-2"><span>Status</span><select data-dpa-status="${esc(d.slug)}">${Object.entries(statuses).map(([k, label]) =>
        `<option value="${k}" ${k === d.status ? "selected" : ""}>${esc(label)}</option>`).join("")}</select></label>
      <label class="field"><span>unterschrieben am</span><input type="date" data-dpa-signed="${esc(d.slug)}" value="${esc(d.signed_on || "")}"></label>
      <label class="field span-2"><span>Notiz</span><input type="text" data-dpa-note="${esc(d.slug)}" placeholder="z. B. Original per Post erhalten"></label>
      <div class="field"><span>&nbsp;</span><button type="button" class="btn btn-primary btn-small" data-dpa-action="status" data-slug="${esc(d.slug)}">Status setzen</button></div>
    </div>
    <details class="section-gap"><summary class="small">Protokoll (${d.events.length})</summary>
      <table class="mini-table"><tbody>${d.events.map((e) => `<tr><td class="small">${esc(e.at)}</td><td class="small">${esc(e.email)}</td><td class="small">${esc(e.action)}</td><td class="small muted">${esc(e.detail || "")}</td></tr>`).join("")}</tbody></table>
    </details>` : "";
  return `<div class="card section-gap">
    <div class="card-header"><div><h2>${esc(d.name)}</h2><p class="muted">Wehren: ${esc(d.tenants.join(", ") || "–")}</p></div>
      <span class="tenant-badge dpa-${d.status}">${esc(d.status_label)}</span></div>
    ${d.status === "signed" ? `<p>Unterschrieben am ${formatDate(d.signed_on)}, bestätigt von ${esc(d.confirmed_by)} am ${formatDate(d.confirmed_at)} (Vorlage ${d.template_version}).</p>` : ""}
    ${d.open ? `<ol class="dpa-steps">
      ${dpaStep(generated, "Angaben des Auftraggebers ausfüllen und den Vertrag erzeugen")}
      ${dpaStep(Boolean(stored), "Vertrag drucken, vom Auftraggeber unterschreiben lassen und als PDF hochladen oder die Ablage verlinken")}
      ${dpaStep(false, "Bestätigung durch den Betreiber – danach sind die Wehren freigeschaltet")}
    </ol>` : ""}
    ${d.open && !d.can_edit ? `<p class="muted">Den Vertrag füllt die Verbandsgemeinde bzw. Wehrführung aus.</p>` : ""}
    ${form}${documentLinks}${upload}${admin}
  </div>`;
}

function renderDpa() {
  const items = dpaState.data.items;
  const blocked = config.dpa_blocked.length > 0;
  $("#view-dpa").innerHTML = `${dpaState.error ? errorBox(dpaState.error) : ""}
    <div class="card"><h2>Auftragsverarbeitung${helpButton("dpa")}</h2>
      <p>Die Einsatzstatistik verarbeitet Namen und Anwesenheiten im Auftrag der Verbandsgemeinde als Träger der Feuerwehr.
      Dafür braucht es einen Vertrag zur Auftragsverarbeitung (Art. 28 DSGVO).
      ${blocked ? "<b>Bis er vorliegt, sind die Einsatzdaten der betroffenen Wehren gesperrt.</b>" : ""}</p></div>
    ${items.map(dpaCard).join("") || `<div class="card section-gap muted">Keine Verbandsgemeinde zugeordnet.</div>`}`;
}

async function dpaRefresh(item, message) {
  const i = dpaState.data.items.findIndex((x) => x.slug === item.slug);
  dpaState.data.items[i] = item;
  dpaState.error = "";
  if (message) toast(message);
  renderDpa();
}

$("#view-dpa").addEventListener("click", async (e) => {
  const button = e.target.closest("[data-dpa-action]");
  if (!button) return;
  const slug = button.dataset.slug;
  try {
    if (button.dataset.dpaAction === "save") {
      const client_data = Object.fromEntries([...$$(`#view-dpa [data-dpa-field]`)].filter((el) =>
        el.closest(".card") === button.closest(".card")).map((el) => [el.dataset.dpaField, el.value]));
      await dpaRefresh(await apiJson(`/api/dpa/${encodeURIComponent(slug)}`, "PUT", { client_data }), "Vertrag erzeugt");
    }
    if (button.dataset.dpaAction === "link") {
      await dpaRefresh(await apiJson(`/api/dpa/${encodeURIComponent(slug)}/link`, "PUT",
        { link: $(`[data-dpa-link="${slug}"]`).value }), "Link gespeichert");
    }
    if (button.dataset.dpaAction === "status") {
      await dpaRefresh(await apiJson(`/api/dpa/${encodeURIComponent(slug)}/status`, "POST", {
        status: $(`[data-dpa-status="${slug}"]`).value, signed_on: $(`[data-dpa-signed="${slug}"]`).value,
        note: $(`[data-dpa-note="${slug}"]`).value }), "Status gesetzt");
    }
  } catch (err) {
    dpaState.error = err.message;
    renderDpa();
  }
});

$("#view-dpa").addEventListener("change", async (e) => {
  const slug = e.target.dataset.dpaUpload;
  if (!slug) return;
  try {
    const form = new FormData();
    form.append("file", e.target.files[0]);
    await dpaRefresh(await api(`/api/dpa/${encodeURIComponent(slug)}/upload`, { method: "POST", body: form }), "Vertrag hochgeladen");
  } catch (err) {
    dpaState.error = err.message;
    renderDpa();
  }
});
