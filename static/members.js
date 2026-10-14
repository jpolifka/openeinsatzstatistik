// Personal (Einsatzteilnahmen). Wird vor app.js geladen.

async function loadMembers() {
  await loadEvaluation();
  await loadIncidents();
}


// ------------------------------------------------------------ Personal (Einsatzteilnahmen)
const MEMBER_COLUMNS = [      // [Feld, Titel, CSS-Klassen, Hilfe-Schlüssel]
  ["name", "Name", ""], ["incidents", "Einsätze", ""], ["rate", "Beteiligung", "right", "participation"],
  ["hours", "Stunden", "right", "hours"], ["nights", "nachts", "right hide-mobile", "nights_weekends"],
  ["weekends", "Sa/So/FT", "right hide-mobile", "nights_weekends"], ["agt_incidents", "Atemschutz", "right hide-mobile", "member_agt"],
  ["agt_minutes", "AGT-Min.", "right hide-mobile", "member_agt"], ["last", "Zuletzt", "right hide-mobile"],
];

// Funktionen einer Person im Jahr, z. B. „Maschinist 4× · Angriffstruppführer 2×“
function memberFunctions(member) {
  const entries = Object.entries(member.functions || {}).sort((x, y) => y[1] - x[1] || x[0].localeCompare(y[0], "de"));
  return entries.length ? `<p class="small muted">Funktionen: ${entries.map(([role, n]) => `${esc(role)} ${n}×`).join(" · ")}</p>` : "";
}

// Einsätze einer Person im gewählten Jahr (Klick öffnet den Einsatz)
function memberIncidents(member) {
  const rows = (state.incidents?.incidents || []).filter((e) => e.people.some((p) => p.id === member.id))
    .sort((a, b) => (b.started_at || "").localeCompare(a.started_at || ""));
  if (!rows.length) return `<p class="empty-note">Keine Einsätze gefunden.</p>`;
  return `<div class="member-incidents"><table class="mini-table"><thead><tr>
    <th>Nr.</th><th>Datum</th><th>Stichwort</th><th>Einsatz</th><th>Fahrzeug</th><th>Funktion</th></tr></thead>
    <tbody>${rows.map((e) => {
      const p = e.people.find((x) => x.id === member.id);
      return `<tr class="link-row" data-open-incident="${esc(e.id)}" tabindex="0">
        <td>${e.number ?? "–"}</td><td>${formatDate(e.started_at)} ${formatTime(e.started_at)}</td>
        <td>${esc(e.keyword)}${e.subcode ? "." + esc(e.subcode) : ""}</td><td>${esc(e.description || "–")}</td>
        <td>${esc(p.vehicle || "–")}</td><td>${esc(p.role || "–")}</td></tr>`;
    }).join("")}</tbody></table></div>`;
}

function renderMembers() {
  const a = state.evaluation.attendance;
  const { field, descending } = state.memberSort;
  const compare = (x, y) => field === "name" ? x.name.localeCompare(y.name, "de")
    : (x[field] ?? "") > (y[field] ?? "") ? 1 : (x[field] ?? "") < (y[field] ?? "") ? -1 : 0;
  const list = [...a.members].sort((x, y) => descending ? -compare(x, y) : compare(x, y));
  const max = Math.max(1, ...list.map((m) => m.incidents));
  $("#view-members").innerHTML = `<div class="card list-card members-table">
    <div class="toolbar"><div><h3>Anwesenheit ${state.year}</h3>
      <p class="muted small">${plural(list.length, "Person", "Personen")} · ${plural(a.incident_count, "Einsatz", "Einsätze")} · Stunden = Einsatzdauer je Teilnahme</p></div></div>
    <div class="table-wrap"><table class="table">
      <thead><tr><th class="col-number">#</th>${MEMBER_COLUMNS.map(([f, title, cls, help]) =>
        `<th class="sortable ${cls}" data-sort="${f}">${title}${field === f ? (descending ? " ▾" : " ▴") : ""}${help ? helpButton(help) : ""}</th>`).join("")}</tr></thead>
      <tbody>${list.map((m, i) => `<tr class="row ${state.openMembers.has(m.id) ? "open" : ""}" data-member="${m.id}">
        <td class="muted">${i + 1}</td>
        <td><strong>${esc(m.name)}</strong></td>
        <td><div class="inline-bar"><span class="track"><span style="width:${(m.incidents / max) * 100}%"></span></span><b>${m.incidents}</b></div></td>
        <td class="right">${percent(m.rate)}</td>
        <td class="right">${num(m.hours)}</td>
        <td class="right hide-mobile">${m.nights}</td>
        <td class="right hide-mobile">${m.weekends}</td>
        <td class="right hide-mobile">${m.agt_incidents || "–"}</td>
        <td class="right hide-mobile">${m.agt_minutes || "–"}</td>
        <td class="right hide-mobile">${formatDate(m.last)}</td>
      </tr>${state.openMembers.has(m.id) ? `<tr class="detail"><td colspan="${MEMBER_COLUMNS.length + 1}">${memberFunctions(m)}${memberIncidents(m)}</td></tr>` : ""}`).join("")}</tbody>
    </table></div>
    ${list.length ? "" : `<p class="empty-note">Für ${state.year} ist keine Anwesenheit erfasst.</p>`}
  </div>`;
}
