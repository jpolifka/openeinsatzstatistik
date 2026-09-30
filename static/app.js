"use strict";

// Fahrzeug-Blöcke in derselben Reihenfolge wie in der Einsatzübersicht
const BLOECKE = ["02/45", "02/24", "02/71", "02/19", "01/10"];
const ARTEN = [["H", "Hilfeleistung"], ["B", "Brand"], ["W", "Wasser"], ["G", "Gefahrstoff"], ["S", "Sonderlage"]];
const ANSICHTEN = ["auswertung", "einsaetze", "kameraden"];

const z = {
  jahre: [], jahr: null, ansicht: "auswertung", grenze: 8,
  auswertung: null, einsaetze: null,
  filterArt: "alle", suche: "", offen: new Set(), bearbeiten: null,
  tabellen: new Set(),                       // Diagramme, die gerade als Tabelle angezeigt werden
  kamSort: { feld: "einsaetze", ab: true },
  pdf: { token: null, berichte: [], fehler: [] }, geaendert: false,
};

// ------------------------------------------------------------ Hilfsfunktionen
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const zahl = (n, stellen = 1) => n == null ? "–" : Number(n).toLocaleString("de-DE", { maximumFractionDigits: stellen });
const prozent = (q) => q == null ? "–" : `${Math.round(q * 100)} %`;
const mehrzahl = (n, eins, viele) => `${n} ${n === 1 ? eins : viele}`;
const datum = (iso) => iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}` : "–";
const uhr = (iso) => !iso ? "–" : iso.length > 8 ? iso.slice(11, 16) : iso.slice(0, 5);
const wochentag = (iso) => iso ? new Date(iso).toLocaleDateString("de-DE", { weekday: "short" }) : "";
function dauer(min) {
  if (min == null) return "–";
  const h = Math.floor(min / 60), m = Math.round(min % 60);
  return h ? `${h}:${String(m).padStart(2, "0")} h` : `${m} min`;
}
function stunden(min) { return min == null ? "–" : `${zahl(min / 60, 0)} h`; }

const SVG_AUF = `<svg class="aufklapp" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

async function api(url, optionen = {}) {
  const antwort = await fetch(url, optionen);
  const daten = await antwort.json().catch(() => ({}));
  if (!antwort.ok) throw new Error(daten.detail || `Fehler ${antwort.status}`);
  return daten;
}

let toastTimer;
function toast(text) {
  const t = $("#toast");
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 3500);
}

function merken(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* privat/gesperrt */ } }
function erinnern(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }

// ------------------------------------------------------------ Diagramm-Bausteine
function schoeneSkala(max) {
  if (max <= 0) return { max: 1, schritt: 1 };
  const roh = max / 4, p = 10 ** Math.floor(Math.log10(roh));
  const schritt = [1, 2, 5, 10].map((f) => f * p).find((s) => s >= roh);
  return { max: Math.ceil(max / schritt) * schritt, schritt };
}

/** Waagerechte Balken, eine Serie. items: [{name, klein, wert, tip}] */
function balken(items) {
  const max = Math.max(1, ...items.map((i) => i.wert));
  return `<div class="balken-liste">${items.map((i) => `
    <div class="balken-zeile" data-tip="${esc(i.tip || `${i.name}: ${i.wert}`)}" tabindex="0">
      <span class="balken-name">${esc(i.name)}${i.klein ? `<small>${esc(i.klein)}</small>` : ""}</span>
      <span class="balken-spur">${i.wert ? `<span class="balken" style="width:${(i.wert / max) * 100}%;display:block"></span>` : ""}</span>
      <span class="balken-wert">${i.wert}</span>
    </div>`).join("")}</div>`;
}

/** Säulen. gruppen: [{achse, tip, werte: [{wert, farbe, beschriften}]}] */
function saeulen(gruppen, { dicht = false } = {}) {
  const max = Math.max(0, ...gruppen.flatMap((g) => g.werte.map((w) => w.wert || 0)));
  const s = schoeneSkala(max);
  const gitter = [];
  for (let v = 0; v <= s.max; v += s.schritt) {
    gitter.push(`<div class="saeulen-gitter" style="bottom:${(v / s.max) * 100}%"><span>${v}</span></div>`);
  }
  return `<div class="saeulen">
    <div class="saeulen-flaeche">${gitter.join("")}
      <div class="saeulen-reihe">${gruppen.map((g) => `
        <div class="saeulen-gruppe" data-tip="${esc(g.tip)}" tabindex="0">${g.werte.map((w) => `
          <div class="saeule" style="height:${((w.wert || 0) / s.max) * 100}%;background:${w.farbe || "var(--serie)"}">
            ${w.beschriften && w.wert ? `<span class="saeule-wert">${w.wert}</span>` : ""}
          </div>`).join("")}
        </div>`).join("")}
      </div>
    </div>
    <div class="saeulen-achse ${dicht ? "dicht" : ""}">${gruppen.map((g) => `<span>${esc(g.achse)}</span>`).join("")}</div>
  </div>`;
}

function datenTabelle(kopf, zeilen, fuss) {
  return `<div class="tabelle-rahmen"><table class="daten-tabelle">
    <thead><tr>${kopf.map((k, i) => `<th class="${i ? "rechts" : ""}">${esc(k)}</th>`).join("")}</tr></thead>
    <tbody>${zeilen.map((r) => `<tr>${r.map((c, i) => `<td class="${i ? "rechts" : ""}">${c}</td>`).join("")}</tr>`).join("")}</tbody>
    ${fuss ? `<tfoot><tr>${fuss.map((c, i) => `<td class="${i ? "rechts" : ""}">${c}</td>`).join("")}</tr></tfoot>` : ""}
  </table></div>`;
}

/** Karte mit Umschalter Diagramm / Tabelle (die Tabelle ist die barrierefreie Ansicht). */
function karte(id, titel, unter, diagramm, tabelle, zusatz = "") {
  const alsTabelle = z.tabellen.has(id);
  return `<div class="karte">
    <div class="karte-kopf">
      <div><h3>${titel}</h3>${unter ? `<p class="gedaempft">${unter}</p>` : ""}</div>
      <button type="button" class="knopf knopf-rand knopf-klein" data-wechsel="${id}">${alsTabelle ? "Diagramm" : "Tabelle"}</button>
    </div>
    ${alsTabelle ? tabelle : diagramm}
    ${zusatz}
  </div>`;
}

// ------------------------------------------------------------ Laden & Navigation
async function jahreLaden() {
  const d = await api("/api/jahre");
  z.jahre = d.jahre.map((j) => j.jahr).sort((a, b) => b - a);
  const gemerkt = Number(erinnern("jahr"));
  if (!z.jahr || !z.jahre.includes(z.jahr)) z.jahr = z.jahre.includes(gemerkt) ? gemerkt : z.jahre[0] ?? new Date().getFullYear();
  $("#jahr").innerHTML = z.jahre.map((j) => `<option ${j === z.jahr ? "selected" : ""}>${j}</option>`).join("");
}

async function ansichtZeigen() {
  const h = location.hash.slice(1);
  z.ansicht = ANSICHTEN.includes(h) ? h : "auswertung";
  for (const a of document.querySelectorAll("#reiter a")) a.classList.toggle("aktiv", a.dataset.ansicht === z.ansicht);
  for (const a of ANSICHTEN) $(`#ansicht-${a}`).hidden = a !== z.ansicht;
  $("#kopf-jahr").textContent = { auswertung: `Auswertung ${z.jahr}`, einsaetze: `Einsätze ${z.jahr}`, kameraden: `Kameraden ${z.jahr}` }[z.ansicht];
  const bereich = $(`#ansicht-${z.ansicht}`);
  bereich.classList.add("laedt");
  try {
    if (z.ansicht === "einsaetze") {
      if (!z.einsaetze || z.einsaetze.jahr !== z.jahr) z.einsaetze = await api(`/api/einsaetze?jahr=${z.jahr}`);
      einsaetzeZeigen();
    } else {
      if (!z.auswertung || z.auswertung.jahr !== z.jahr || z.auswertung.grenze !== z.grenze) {
        z.auswertung = await api(`/api/auswertung?jahr=${z.jahr}&grenze=${z.grenze}`);
        z.auswertung.grenze = z.grenze;
      }
      z.ansicht === "auswertung" ? auswertungZeigen() : kameradenZeigen();
    }
  } catch (e) {
    bereich.innerHTML = `<div class="meldung meldung-fehler">${esc(e.message)}</div>`;
  } finally {
    bereich.classList.remove("laedt");
  }
}

// ------------------------------------------------------------ Auswertung
function auswertungZeigen() {
  const { statistik: s, bedarfsplan: bp, bedarfsplan_vorjahr: bpv } = z.auswertung;
  const laufend = z.jahr === new Date().getFullYear();

  let vergleich = "";
  if (laufend && s.vorjahr_bis_heute != null) {
    const d = s.anzahl - s.vorjahr_bis_heute;
    vergleich = `${d > 0 ? "+" : ""}${d} gegenüber ${z.jahr - 1} zum selben Datum (${s.vorjahr_bis_heute})`;
  } else if (s.vorjahr_gesamt != null) {
    vergleich = `${z.jahr - 1}: ${s.vorjahr_gesamt} Einsätze`;
  }
  const kpis = `<div class="kpis">
    <div class="kpi held"><span class="kpi-titel">Einsätze ${z.jahr}</span><span class="kpi-wert">${s.anzahl}</span><span class="kpi-unter">${esc(vergleich)}</span></div>
    <div class="kpi"><span class="kpi-titel">Einsätze / Woche${hilfe("pro_woche")}</span><span class="kpi-wert">${zahl(s.pro_woche, 2)}</span><span class="kpi-unter">${laufend ? "bis zur aktuellen KW" : "im ganzen Jahr"}</span></div>
    <div class="kpi"><span class="kpi-titel">Ø Einsatzdauer${hilfe("dauer")}</span><span class="kpi-wert">${dauer(s.dauer_mittel_min)}</span><span class="kpi-unter">Alarm bis Einsatzende</span></div>
    <div class="kpi"><span class="kpi-titel">Einsatzstunden${hilfe("einsatzstunden")}</span><span class="kpi-wert">${stunden(s.dauer_gesamt_min)}</span><span class="kpi-unter">Summe aller Einsätze</span></div>
    <div class="kpi"><span class="kpi-titel">Personalstunden${hilfe("personalstunden")}</span><span class="kpi-wert">${zahl(s.personal_std, 0)}<small>h</small></span><span class="kpi-unter">Ø ${zahl(s.anwesend_mittel, 1)} Kameraden je Einsatz</span></div>
    <div class="kpi"><span class="kpi-titel">Eintreffen ≤ ${bp.grenze} Min.${hilfe("erreicht")}</span><span class="kpi-wert">${prozent(bp.gesamt.quote)}</span><span class="kpi-unter">${bp.gesamt.erreicht} von ${bp.gesamt.anzahl} (Bedarfsplan)</span></div>
  </div>`;

  $("#ansicht-auswertung").innerHTML = kpis + bedarfsplanKarte(bp, bpv) + `
    <div class="raster raster-3">${artenKarte(s)}${stufenKarte(s)}${gebietKarte(s)}</div>
    <div class="raster">${monatKarte(s)}</div>
    <div class="raster raster-2">${stundenKarte(s)}${wochentagKarte(s)}</div>`;
}

function bedarfsplanKarte(bp, bpv) {
  const g = bp.grenze;
  const fensterHtml = (f, gesamt) => {
    const leer = !f.anzahl;
    return `<div class="fenster ${gesamt ? "gesamt" : ""} ${leer ? "ohne" : ""}">
      <div class="fenster-titel">${gesamt ? "Gesamt" : esc(f.tagart)}<span>${gesamt ? "alle Zeitfenster" : esc(f.zeit)}</span></div>
      <div class="quote">${prozent(f.quote)}<small>${f.erreicht} / ${f.anzahl}</small></div>
      <div class="meter" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round((f.quote || 0) * 100)}"
           aria-label="Erreichungsgrad"><span style="width:${(f.quote || 0) * 100}%"></span></div>
      <dl class="fenster-werte">
        <dt>Ø Ausrückezeit</dt><dd>${f.azeit == null ? "–" : zahl(f.azeit) + " min"}</dd>
        <dt>Ø Eintreffzeit</dt><dd>${f.ezeit == null ? "–" : zahl(f.ezeit) + " min"}</dd>
        <dt>Stärke bei Eintreffen</dt><dd>${zahl(f.staerke_eintreffen)}</dd>
        <dt>Stärke nach ${g} Min.</dt><dd>${zahl(f.staerke_grenze)}</dd>
        <dt>Stärke nach 15 Min.</dt><dd>${zahl(f.staerke_15)}</dd>
        <dt>Gesamtstärke</dt><dd>${zahl(f.staerke_gesamt)}</dd>
      </dl>
      ${gesamt && bpv?.gesamt?.anzahl ? `<div class="klein" style="opacity:.8">${z.jahr - 1}: ${prozent(bpv.gesamt.quote)} (${bpv.gesamt.erreicht} / ${bpv.gesamt.anzahl})</div>` : ""}
    </div>`;
  };
  const alsTabelle = z.tabellen.has("bedarf");
  const zeilen = [...bp.fenster, { ...bp.gesamt, tagart: "Gesamt", zeit: "" }].map((f) => [
    `${esc(f.tagart)} ${esc(f.zeit)}`, f.anzahl, zahl(f.azeit), zahl(f.ezeit), f.erreicht, f.nicht_erreicht,
    prozent(f.quote), zahl(f.staerke_eintreffen), zahl(f.staerke_grenze), zahl(f.staerke_15), zahl(f.staerke_gesamt)]);
  const tabelle = datenTabelle(["Zeitfenster", "Einsätze", "Ø Azeit (min)", "Ø Ezeit (min)", `≤ ${g} Min.`, `> ${g} Min.`,
    "Erreichungsgrad", "Stärke Eintreffen", `Stärke nach ${g} Min.`, "Stärke nach 15 Min.", "Gesamtstärke"], zeilen);
  return `<div class="karte bedarf raster">
    <div class="karte-kopf">
      <div>
        <h2>Feuerwehrbedarfsplan · Pos. 8.4${hilfe("bedarfsplan")}</h2>
        <p class="gedaempft">Einsätze ab Alarmstufe 2 in ${bp.orte.join(", ")} – Eintreffen des ersten Fahrzeugs innerhalb von ${g} Minuten nach Alarmierung.</p>
      </div>
      <div class="aktionen">
        <div class="segmente" id="grenze" role="group" aria-label="Zeitgrenze">
          ${[8, 10].map((m) => `<button type="button" data-grenze="${m}" class="${m === g ? "aktiv" : ""}">${m} Min.</button>`).join("")}
        </div>
        <button type="button" class="knopf knopf-rand knopf-klein" data-wechsel="bedarf">${alsTabelle ? "Kacheln" : "Tabelle"}</button>
      </div>
    </div>
    ${alsTabelle ? tabelle : `<div class="bedarf-fenster">${bp.fenster.map((f) => fensterHtml(f, false)).join("")}${fensterHtml(bp.gesamt, true)}</div>`}
    <p class="bedarf-fuss">Zeiten ab Einsatzbeginn (früheste Alarmierung). Gesamtstärke ohne 01/10, wie in der Einsatzübersicht.
      ${bp.ohne_zeiten ? `${mehrzahl(bp.ohne_zeiten, "Einsatz", "Einsätze")} ohne Eintreffzeit nicht berücksichtigt (Excel zählte sie mit 0 min als erreicht).` : ""}</p>
  </div>`;
}

function artenKarte(s) {
  const items = s.kategorien.map((k) => ({
    name: k.name, klein: k.kuerzel, wert: k.anzahl,
    tip: `${k.name}: ${k.anzahl}\n` + Object.entries(k.stichworte).map(([sw, n]) => `${sw}: ${n}`).join(" · "),
  }));
  const tabelle = datenTabelle(["Art", "1", "2", "3", "4", "Summe"],
    s.kategorien.map((k) => [`${esc(k.name)} (${k.kuerzel})`, ...Object.values(k.stichworte), `<b>${k.anzahl}</b>`]),
    ["Gesamt", ...[1, 2, 3, 4].map((i) => s.stufen[i - 1].anzahl), s.anzahl]);
  const mini = `<div class="stat-mini">
    <div data-tip="Stichwort B2.07"><b>${s.bma}</b><span>Brandmeldeanlage</span></div>
    <div data-tip="Stichwort S1.00"><b>${s.bsw}</b><span>Brandsicherheitswache</span></div>
  </div>`;
  return karte("arten", "Einsatzarten", "nach Einsatzstichwort", balken(items), tabelle, mini);
}

function stufenKarte(s) {
  const items = s.stufen.map((x) => ({ name: `Stufe ${x.stufe}`, wert: x.anzahl, tip: `Alarmstufe ${x.stufe}: ${x.anzahl} Einsätze` }));
  const tabelle = datenTabelle(["Stufe", "Einsätze", "Anteil"],
    s.stufen.map((x) => [`Stufe ${x.stufe}`, x.anzahl, prozent(s.anzahl ? x.anzahl / s.anzahl : null)]));
  return karte("stufen", `Alarmstufen${hilfe("alarmstufe")}`, "zweite Ziffer des Stichworts (z. B. H<b>2</b>)", balken(items), tabelle);
}

function gebietKarte(s) {
  const items = s.gebiete.map((x) => ({ name: x.name, wert: x.anzahl }));
  const eigen = s.gebiete.filter((x) => ["Rheinbrohl", "Arienheller", "Hammerstein"].includes(x.name)).reduce((a, x) => a + x.anzahl, 0);
  const tabelle = datenTabelle(["Ort", "Einsätze", "Anteil"],
    s.gebiete.map((x) => [esc(x.name), x.anzahl, prozent(s.anzahl ? x.anzahl / s.anzahl : null)]));
  const zusatz = `<div class="kennzeile"><span><b>${eigen}</b>Rheinbrohl, Arienheller, Hammerstein</span><span><b>${s.anzahl - eigen}</b>außerhalb</span></div>`;
  return karte("gebiet", `Einsatzgebiet${hilfe("gebiet")}`, "", balken(items), tabelle, zusatz);
}

function monatKarte(s) {
  const mitVj = s.monate.some((m) => m.vorjahr != null);
  const gruppen = s.monate.map((m) => ({
    achse: m.name,
    tip: `${m.name} ${z.jahr}: ${m.anzahl}` + (mitVj ? `\n${m.name} ${z.jahr - 1}: ${m.vorjahr}` : ""),
    werte: mitVj ? [{ wert: m.vorjahr, farbe: "var(--vorjahr)" }, { wert: m.anzahl, beschriften: true }] : [{ wert: m.anzahl, beschriften: true }],
  }));
  const legende = mitVj ? `<div class="legende"><span><i style="background:var(--serie)"></i>${z.jahr}</span><span><i style="background:var(--vorjahr)"></i>${z.jahr - 1}</span></div>` : "";
  const tabelle = datenTabelle(["Monat", String(z.jahr), ...(mitVj ? [String(z.jahr - 1)] : [])],
    s.monate.map((m) => [m.name, m.anzahl, ...(mitVj ? [m.vorjahr] : [])]),
    ["Summe", s.anzahl, ...(mitVj ? [s.vorjahr_gesamt] : [])]);
  return karte("monate", "Einsätze je Monat", mitVj ? `im Vergleich zu ${z.jahr - 1}` : "", saeulen(gruppen) + legende, tabelle);
}

function stundenKarte(s) {
  const gruppen = s.stunden.map((x) => ({
    achse: x.stunde % 3 === 0 ? String(x.stunde) : "",
    tip: `${String(x.stunde).padStart(2, "0")}:00 – ${String(x.stunde).padStart(2, "0")}:59 Uhr: ${x.anzahl}`,
    werte: [{ wert: x.anzahl, farbe: x.tag ? "var(--tag)" : "var(--nacht)" }],
  }));
  const spitze = s.stunden.reduce((a, x) => (x.anzahl > a.anzahl ? x : a), s.stunden[0]);
  const zusatz = `<div class="legende"><span><i style="background:var(--tag)"></i>Tag 06–18 Uhr</span><span><i style="background:var(--nacht)"></i>Nacht 18–06 Uhr</span></div>
    <div class="kennzeile"><span><b>${prozent(s.anteil_tag)}</b>tagsüber</span><span><b>${s.anteil_tag == null ? "–" : `${100 - Math.round(s.anteil_tag * 100)} %`}</b>nachts</span>
    <span><b>${spitze.stunde}–${spitze.stunde + 1} Uhr</b>häufigste Stunde</span></div>`;
  const tabelle = datenTabelle(["Uhrzeit", "Einsätze"], s.stunden.map((x) => [`${String(x.stunde).padStart(2, "0")}:00 Uhr`, x.anzahl]));
  return karte("stunden", "Alarmierungszeiten", "Einsatzbeginn nach Uhrzeit", saeulen(gruppen), tabelle, zusatz);
}

function wochentagKarte(s) {
  const gruppen = s.wochentage.map((x) => ({ achse: x.name.slice(0, 2), tip: `${x.name}: ${x.anzahl}`, werte: [{ wert: x.anzahl, beschriften: true }] }));
  const werktage = s.wochentage.slice(0, 5).reduce((a, x) => a + x.anzahl, 0);
  const zusatz = `<div class="kennzeile"><span><b>${werktage}</b>Mo–Fr</span><span><b>${s.anzahl - werktage}</b>Sa/So</span></div>`;
  const tabelle = datenTabelle(["Wochentag", "Einsätze"], s.wochentage.map((x) => [x.name, x.anzahl]));
  return karte("wochentage", "Wochentage", "", saeulen(gruppen), tabelle, zusatz);
}

// ------------------------------------------------------------ Einsätze
function passt(e) {
  if (z.filterArt !== "alle" && !(e.stichwort || "").startsWith(z.filterArt)) return false;
  const q = z.suche.trim().toLowerCase();
  if (!q) return true;
  const text = [e.nr, e.stichwort, `${e.stichwort}.${e.stufe}`, e.einsatz, e.ort, e.ehf, datum(e.beginn), e.datei,
    ...e.personen.map((p) => p.name)].join(" ").toLowerCase();
  return q.split(/\s+/).every((t) => text.includes(t));
}

function fahrzeugChips(e) {
  return `<div class="fzg">${e.fahrzeuge.map((f) => {
    const kurz = f.block.slice(3);
    if (f.staerke == null && !f.aus && !f.ein) return `<span data-tip="${f.block}: nicht im Einsatz">${kurz}</span>`;
    return `<span class="an" data-tip="${esc(f.name || f.block)} · Stärke ${f.staerke ?? "–"}\nEintreffen ${f.ezeit == null ? "–" : zahl(f.ezeit) + " min"}">${kurz}<b>${f.staerke ?? "–"}</b></span>`;
  }).join("")}</div>`;
}

function einsaetzeZeigen() {
  const liste = z.einsaetze.einsaetze;
  const anzahl = { alle: liste.length };
  for (const [k] of ARTEN) anzahl[k] = liste.filter((e) => (e.stichwort || "").startsWith(k)).length;
  $("#filter-art").innerHTML = [["alle", "Alle"], ...ARTEN].map(([k, n]) =>
    `<button type="button" data-art="${k}" class="${z.filterArt === k ? "aktiv" : ""}" ${k !== "alle" ? `data-tip="${n}"` : ""}>${k === "alle" ? n : k}<span class="anzahl">${anzahl[k]}</span></button>`).join("");

  const sichtbar = liste.filter(passt).reverse();   // neueste zuerst
  $("#tabelle-einsaetze tbody").innerHTML = sichtbar.map((e) => {
    const offen = z.offen.has(e.id);
    const sw = (e.stichwort || "").charAt(0).toLowerCase();
    const ez = e.ezeit == null ? `<span class="gedaempft">–</span>`
      : `<span class="ezeit ${e.erreicht ? "" : "spaet"}" data-tip="${e.erreicht ? "innerhalb" : "nicht innerhalb"} von 8 Minuten">${zahl(e.ezeit)} min</span>`;
    return `<tr class="zeile ${offen ? "offen" : ""}" data-id="${e.id}">
      <td><span class="nr">${e.nr ?? "–"}</span></td>
      <td><div>${datum(e.beginn)}</div><div class="zeit">${wochentag(e.beginn)} ${uhr(e.beginn)}${e.wochenende ? " · WE/FT" : ""}</div></td>
      <td><span class="stichwort ${sw}">${esc(e.stichwort)}${e.stufe ? "." + esc(e.stufe) : ""}</span></td>
      <td><div class="einsatz-titel">${esc(e.einsatz)}</div><div class="einsatz-ort">${esc(e.ort)}</div></td>
      <td>${e.ehf ? esc(e.ehf) : `<span class="gedaempft">–</span>`}</td>
      <td>${fahrzeugChips(e)}</td>
      <td class="rechts">${ez}</td>
      <td class="rechts">${e.staerke_gesamt}</td>
      <td>${SVG_AUF}</td>
    </tr>${offen ? `<tr class="detail"><td colspan="9">${z.bearbeiten === e.id ? formularDetail(e) : einsatzDetail(e)}</td></tr>` : ""}`;
  }).join("");
  $("#leer-einsaetze").hidden = sichtbar.length > 0;
}

function fahrzeugTabelle(e) {
  return `<div class="tabelle-rahmen"><table class="mini"><thead><tr>
    <th>Fzg.</th><th class="rechts">Stärke</th><th>Ausr.</th><th class="rechts">Azeit</th><th>Eintr.</th><th class="rechts">Ezeit</th></tr></thead>
    <tbody>${e.fahrzeuge.map((f) => f.staerke == null && !f.aus && !f.ein
      ? `<tr class="leer-fzg"><td>${f.block}</td><td colspan="5">nicht im Einsatz</td></tr>`
      : `<tr><td><strong>${f.block}</strong>${f.name && !f.name.includes(f.block) ? `<br><span class="klein gedaempft">${esc(f.name.replace("FL NR#.BHÖ ", ""))}</span>` : ""}</td>
        <td class="rechts">${f.staerke ?? "–"}</td><td>${uhr(f.aus)}</td><td class="rechts minuten">${zahl(f.azeit)}</td>
        <td>${uhr(f.ein)}</td><td class="rechts minuten ${f.ezeit != null && f.ezeit > 8 ? "spaet" : ""}">${zahl(f.ezeit)}</td></tr>`).join("")}
    </tbody></table></div>`;
}

function personenChips(e, markiereNeu) {
  const ehfName = (e.ehf || "").split(". ").pop();
  return e.personen.map((p) => {
    const istEhf = /Einheitsführer/.test(p.funktion || "") || (!!ehfName && p.name.startsWith(ehfName));
    const klasse = markiereNeu && p.neu ? "neu" : istEhf ? "ehf" : "";
    const tip = [p.funktion, p.fahrzeug, markiereNeu && p.neu && "wird als neuer Kamerad angelegt"].filter(Boolean).join(" · ");
    return `<span class="person ${klasse}" ${tip ? `data-tip="${esc(tip)}"` : ""}>${esc(p.name)}${p.fahrzeug ? `<small>${esc(p.fahrzeug)}</small>` : ""}</span>`;
  }).join("") || `<span class="gedaempft">Keine Anwesenheit erfasst</span>`;
}

function einsatzDetail(e) {
  return `<div class="detail-innen">
    <div class="block"><h4>Einsatz</h4><dl class="daten">
      <dt>Beginn</dt><dd>${datum(e.beginn)} ${uhr(e.beginn)}</dd>
      <dt>Ende</dt><dd>${datum(e.ende)} ${uhr(e.ende)}</dd>
      <dt>Dauer${hilfe("dauer")}</dt><dd>${dauer(e.dauer_min)}</dd>
      <dt>Zeitfenster${hilfe("zeitfenster")}</dt><dd>${e.wochenende ? "Sa/So/Feiertag" : "Werktag"}, ${e.tag ? "Tag" : "Nacht"}</dd>
      <dt>Ort</dt><dd>${esc(e.ort || "–")}</dd>
      <dt>EHF${hilfe("ehf")}</dt><dd>${esc(e.ehf || "–")}</dd>
      <dt>Gerätehaus${hilfe("personen_gh")}</dt><dd>${e.personen_gh}</dd>
      <dt>Quelle</dt><dd class="klein">${e.quelle === "pdf" ? `PDF · ${esc(e.datei)}` : "Einsatzübersicht (Excel)"}</dd>
    </dl></div>
    <div class="block"><h4>Fahrzeuge${hilfe("fahrzeuge")}</h4>${fahrzeugTabelle(e)}</div>
    <div class="block"><h4>Kennzahlen</h4><dl class="daten">
      <dt>Azeit${hilfe("azeit")}</dt><dd>${e.azeit == null ? "–" : zahl(e.azeit) + " min"}</dd>
      <dt>Ezeit${hilfe("ezeit")}</dt><dd>${e.ezeit == null ? "–" : zahl(e.ezeit) + " min"}</dd>
      <dt>8 Min. erreicht${hilfe("erreicht")}</dt><dd>${e.erreicht == null ? "–" : e.erreicht ? "ja" : "nein"}</dd>
      <dt>Stärke Eintreffen${hilfe("staerke_eintreffen")}</dt><dd>${e.staerke_eintreffen ?? "–"}</dd>
      <dt>nach 8 Min.${hilfe("staerke_grenze")}</dt><dd>${e.staerke_grenze ?? "–"}</dd>
      <dt>nach 15 Min.${hilfe("staerke_15")}</dt><dd>${e.staerke_15 ?? "–"}</dd>
      <dt>Gesamtstärke${hilfe("staerke_gesamt")}</dt><dd>${e.staerke_gesamt}</dd>
    </dl>
    ${e.hinweise.length ? `<h4 style="margin-top:14px">Prüfhinweise${hilfe("hinweise")}</h4><ul class="hinweise">${e.hinweise.map((h) => `<li>${esc(h)}</li>`).join("")}</ul>` : ""}
    </div>
    <div class="block voll"><h4>Anwesenheit · ${e.personen.length} Personen${hilfe("anwesenheit")}</h4><div class="personen">${personenChips(e, false)}</div></div>
    <div class="aktionen block voll" style="background:none;box-shadow:none;padding:0">
      <button type="button" class="knopf knopf-rand knopf-klein" data-aktion="loeschen" data-id="${e.id}">Löschen</button>
      <button type="button" class="knopf knopf-hell knopf-klein" data-aktion="bearbeiten" data-id="${e.id}">Bearbeiten</button>
    </div>
  </div>`;
}

function formFelder(e) {
  const f = (name, titel, wert, typ = "text", breite = "", extra = "") =>
    `<label class="feld ${breite}"><span>${titel}${hilfe(name)}</span><input name="${name}" type="${typ}" value="${esc(wert ?? "")}" ${extra}
      class="${name === "ehf" && !wert ? "fehlt" : ""}"></label>`;
  return `<div class="formular">
    ${f("nr", "Nr.", e.nr, "number", "", 'min="1"')}
    ${f("beginn", "Beginn", (e.beginn || "").slice(0, 19), "datetime-local", "b2", 'step="1"')}
    ${f("ende", "Ende", (e.ende || "").slice(0, 19), "datetime-local", "b2", 'step="1"')}
    ${f("personen_gh", "Gerätehaus", e.personen_gh, "number", "", 'min="0"')}
    ${f("stichwort", "Stichwort", e.stichwort, "text", "", 'maxlength="4"')}
    ${f("stufe", "Stufe", e.stufe, "text", "", 'maxlength="2"')}
    ${f("einsatz", "Einsatz", e.einsatz, "text", "b4")}
    ${f("ort", "Ort", e.ort, "text", "b3", 'list="orte"')}
    ${f("ehf", "EHF", e.ehf, "text", "b3", 'list="ehf-liste" placeholder="z. B. M. Mustermann"')}
  </div>`;
}

function formWerte(el) {
  const w = {};
  for (const i of el.querySelectorAll("input[name]")) {
    if (i.name === "nr" || i.name === "personen_gh") w[i.name] = i.value === "" ? null : Number(i.value);
    else w[i.name] = i.value;
  }
  return w;
}

function formularDetail(e) {
  return `<div class="detail-innen" data-form="${e.id}">
    <div class="block voll"><h4>Einsatz ${e.nr ?? ""} bearbeiten</h4>${formFelder(e)}</div>
    <div class="aktionen block voll" style="background:none;box-shadow:none;padding:0">
      <button type="button" class="knopf knopf-rand knopf-klein" data-aktion="abbrechen">Abbrechen</button>
      <button type="button" class="knopf knopf-haupt knopf-klein" data-aktion="speichern" data-id="${e.id}">Speichern</button>
    </div>
  </div>`;
}

function auswahllisten() {
  // Vorschläge für Ort und EHF aus den vorhandenen Einsätzen
  const alle = z.einsaetze?.einsaetze || [];
  const orte = [...new Set(["Rheinbrohl", "Arienheller", "Hammerstein", "Ariendorf", "Bad Hönningen", "Leutesdorf", ...alle.map((e) => e.ort)])].filter(Boolean);
  const ehf = [...new Set(alle.map((e) => e.ehf).filter(Boolean))].sort();
  let dl = $("#datalisten");
  if (!dl) { dl = document.createElement("div"); dl.id = "datalisten"; document.body.append(dl); }
  dl.innerHTML = `<datalist id="orte">${orte.map((o) => `<option value="${esc(o)}">`).join("")}</datalist>
    <datalist id="ehf-liste">${ehf.map((o) => `<option value="${esc(o)}">`).join("")}</datalist>`;
}

async function datenNeu() {
  z.auswertung = null;
  z.einsaetze = null;
  await jahreLaden();
  await ansichtZeigen();
}

// ------------------------------------------------------------ Kameraden
function kameradenZeigen() {
  const a = z.auswertung.anwesenheit;
  const { feld, ab } = z.kamSort;
  const liste = [...a.kameraden].sort((x, y) => {
    const v = feld === "name" ? x.name.localeCompare(y.name, "de") : (x[feld] ?? "") > (y[feld] ?? "") ? 1 : (x[feld] ?? "") < (y[feld] ?? "") ? -1 : 0;
    return ab ? -v : v;
  });
  const max = Math.max(1, ...liste.map((k) => k.einsaetze));
  const kopf = [["name", "Name", ""], ["einsaetze", "Einsätze", ""], ["quote", "Beteiligung", "rechts", "beteiligung"], ["stunden", "Stunden", "rechts", "stunden"],
    ["nacht", "nachts", "rechts sp-mobil-aus", "nachts_we"], ["wochenende", "Sa/So/FT", "rechts sp-mobil-aus", "nachts_we"], ["zuletzt", "Zuletzt", "rechts sp-mobil-aus"]];
  $("#ansicht-kameraden").innerHTML = `<div class="karte liste-karte kameraden-tabelle">
    <div class="werkzeuge"><div><h3>Anwesenheit ${z.jahr}</h3>
      <p class="gedaempft klein">${mehrzahl(liste.length, "Kamerad", "Kameraden")} · ${mehrzahl(a.anzahl_einsaetze, "Einsatz", "Einsätze")} · Stunden = Einsatzdauer je Teilnahme</p></div></div>
    <div class="tabelle-rahmen"><table class="tabelle">
      <thead><tr><th class="sp-nr">#</th>${kopf.map(([f, t, k, h]) => `<th class="sortierbar ${k}" data-sort="${f}">${t}${feld === f ? (ab ? " ▾" : " ▴") : ""}${h ? hilfe(h) : ""}</th>`).join("")}</tr></thead>
      <tbody>${liste.map((k, i) => `<tr>
        <td class="gedaempft">${i + 1}</td>
        <td><strong>${esc(k.name)}</strong></td>
        <td><div class="inline-balken"><span class="spur"><span style="width:${(k.einsaetze / max) * 100}%"></span></span><b>${k.einsaetze}</b></div></td>
        <td class="rechts">${prozent(k.quote)}</td>
        <td class="rechts">${zahl(k.stunden)}</td>
        <td class="rechts sp-mobil-aus">${k.nacht}</td>
        <td class="rechts sp-mobil-aus">${k.wochenende}</td>
        <td class="rechts sp-mobil-aus">${datum(k.zuletzt)}</td>
      </tr>`).join("")}</tbody>
    </table></div>
    ${liste.length ? "" : `<p class="leer">Für ${z.jahr} ist keine Anwesenheit erfasst.</p>`}
  </div>`;
}

// ------------------------------------------------------------ PDF einlesen
async function pdfEinlesen(dateien) {
  dateien = [...dateien].filter((f) => f.name.toLowerCase().endsWith(".pdf"));
  const fehler = $("#pdf-fehler");
  fehler.hidden = true;
  if (!dateien.length) { fehler.textContent = "Bitte eine PDF-Datei wählen."; fehler.hidden = false; return; }
  $("#fortschritt").hidden = false;
  const fd = new FormData();
  for (const f of dateien) fd.append("pdfs", f, f.name.normalize("NFC"));
  try {
    const d = await api("/api/pdf", { method: "POST", body: fd });
    z.pdf = { token: d.token, berichte: d.berichte.map((b) => ({ ...b, ersetzen: false, gespeichert: null })), fehler: d.fehler };
    if (d.fehler.length) {
      fehler.innerHTML = d.fehler.map((f) => `${esc(f.datei)}: ${esc(f.meldung)}`).join("<br>");
      fehler.hidden = false;
    }
    vorschauZeigen();
  } catch (e) {
    fehler.textContent = e.message;
    fehler.hidden = false;
  } finally {
    $("#fortschritt").hidden = true;
  }
}

function vorschauZeigen() {
  const berichte = z.pdf.berichte;
  $("#ablage").classList.toggle("kompakt", berichte.length > 0);
  $("#vorschau").innerHTML = berichte.map((b, i) => {
    const v = b.vorhanden;
    let status;
    if (b.gespeichert) {
      status = `<div class="vorschau-status fertig"><span class="nr">✓</span><div><strong>Einsatz ${b.gespeichert.nr ?? ""}/${b.gespeichert.jahr} ist in der Statistik</strong><span>${esc(b.datei)}</span></div></div>`;
    } else if (v) {
      status = `<div class="vorschau-status vorhanden"><span class="nr">${b.nr ?? "?"}</span><div><strong>Einsatz ${b.nr}/${b.jahr} ist bereits erfasst</strong>
        <span>${v.quelle === "pdf" ? "aus einer PDF" : "aus der Einsatzübersicht (Excel)"} · ${v.abweichungen.length ? mehrzahl(v.abweichungen.length, "Abweichung", "Abweichungen") : "keine Abweichungen"}</span></div></div>`;
    } else {
      status = `<div class="vorschau-status"><span class="nr">${b.nr ?? "?"}</span><div><strong>Neuer Einsatz ${b.nr ?? ""}${b.nr ? "/" + b.jahr : ""}</strong><span>${esc(b.datei)}</span></div></div>`;
    }
    const hinweise = b.hinweise.length ? b.hinweise.map((h) => `<li>${esc(h)}</li>`).join("") : `<li class="ok">Keine Prüfhinweise</li>`;
    const abw = v && v.abweichungen.length ? `<h4 style="margin-top:14px">Abweichungen zur Statistik</h4>
      <table class="mini abw-tab"><thead><tr><th>Feld</th><th>erfasst</th><th>PDF</th></tr></thead><tbody>
      ${v.abweichungen.map((a) => `<tr><td>${esc(a.feld)}</td><td>${esc(a.liste)}</td><td>${esc(a.pdf)}</td></tr>`).join("")}</tbody></table>` : "";
    const neuePersonen = b.personen.filter((p) => p.neu).length;
    return `<div class="vorschau-karte" data-index="${i}">
      ${status}
      ${b.gespeichert ? "" : `<div class="vorschau-inhalt">
        ${formFelder(b)}
        <div class="vorschau-raster">
          <div class="block" style="box-shadow:none;border:1px solid var(--linie)"><h4>Fahrzeuge${hilfe("fahrzeuge")}</h4>${fahrzeugTabelle(b)}
            <p class="klein gedaempft" style="margin-top:8px">Ezeit erstes Fahrzeug: <b>${b.ezeit == null ? "–" : zahl(b.ezeit) + " min"}</b> · Gesamtstärke ${b.staerke_gesamt}</p></div>
          <div class="block" style="box-shadow:none;border:1px solid var(--linie)"><h4>Prüfhinweise${hilfe("hinweise")}</h4><ul class="hinweise">${hinweise}</ul>${abw}</div>
        </div>
        <div class="block" style="box-shadow:none;border:1px solid var(--linie)"><h4>Anwesenheit · ${b.personen.length} Personen${neuePersonen ? ` · ${neuePersonen} neu` : ""}${hilfe("anwesenheit")}</h4>
          <div class="personen">${personenChips(b, true)}</div></div>
        <div class="vorschau-fuss">
          ${v ? `<label class="schalter"><input type="checkbox" data-ersetzen="${i}" ${b.ersetzen ? "checked" : ""}> erfassten Einsatz durch diese PDF ersetzen</label>` : ""}
          <button type="button" class="knopf knopf-haupt" data-uebernehmen="${i}" ${v && !b.ersetzen ? "disabled" : ""}>
            ${v ? "Ersetzen" : "In Statistik übernehmen"}</button>
        </div>
      </div>`}
    </div>`;
  }).join("");
}

async function uebernehmen(i) {
  const b = z.pdf.berichte[i];
  const karteEl = document.querySelector(`.vorschau-karte[data-index="${i}"]`);
  const knopf = karteEl.querySelector("[data-uebernehmen]");
  knopf.disabled = true;
  try {
    const e = await api("/api/pdf/uebernehmen", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: z.pdf.token, datei: b.datei, felder: formWerte(karteEl), ersetzen: b.ersetzen }),
    });
    b.gespeichert = e;
    z.geaendert = true;
    toast(`Einsatz ${e.nr ?? ""}/${e.jahr} übernommen`);
    vorschauZeigen();
  } catch (err) {
    knopf.disabled = false;
    alert(err.message);
  }
}

// ------------------------------------------------------------ Tooltip
const tip = $("#tooltip");
let tipEl = null, tipBild = 0;
function tipZeigen(el, x, y) {
  // Text nur beim Wechsel des Elements setzen, Position höchstens einmal je Frame messen
  if (el !== tipEl || tip.hidden) { tipEl = el; tip.textContent = el.dataset.tip; tip.hidden = false; }
  cancelAnimationFrame(tipBild);
  tipBild = requestAnimationFrame(() => {
    const r = tip.getBoundingClientRect();
    tip.style.left = `${Math.min(window.innerWidth - r.width - 8, Math.max(8, x - r.width / 2))}px`;
    tip.style.top = `${Math.max(8, y - r.height - 12)}px`;
  });
}
function tipVerbergen() {
  cancelAnimationFrame(tipBild);
  tipEl = null;
  tip.hidden = true;
}
document.addEventListener("mousemove", (e) => {
  const el = e.target.closest?.("[data-tip]");
  if (el) tipZeigen(el, e.clientX, e.clientY); else if (tipEl) tipVerbergen();
});
document.addEventListener("focusin", (e) => {
  const el = e.target.closest?.("[data-tip]");
  if (el) { const r = el.getBoundingClientRect(); tipZeigen(el, r.left + r.width / 2, r.top); }
});
document.addEventListener("focusout", tipVerbergen);

// ------------------------------------------------------------ Ereignisse
window.addEventListener("hashchange", () => { z.offen.clear(); ansichtZeigen(); });
$("#jahr").addEventListener("change", (e) => {
  z.jahr = Number(e.target.value);
  merken("jahr", z.jahr);
  z.offen.clear();
  z.bearbeiten = null;
  ansichtZeigen();
});

$("#ansicht-auswertung").addEventListener("click", (e) => {
  const w = e.target.closest("[data-wechsel]");
  if (w) {
    const id = w.dataset.wechsel;
    z.tabellen.has(id) ? z.tabellen.delete(id) : z.tabellen.add(id);
    auswertungZeigen();
    return;
  }
  const g = e.target.closest("[data-grenze]");
  if (g && Number(g.dataset.grenze) !== z.grenze) {
    z.grenze = Number(g.dataset.grenze);
    ansichtZeigen();
  }
});

$("#filter-art").addEventListener("click", (e) => {
  const k = e.target.closest("button");
  if (!k) return;
  z.filterArt = k.dataset.art;
  einsaetzeZeigen();
});
$("#suche").addEventListener("input", (e) => { z.suche = e.target.value; einsaetzeZeigen(); });
$("#knopf-export").addEventListener("click", () => { location.href = `/api/export?jahr=${z.jahr}`; });

$("#tabelle-einsaetze tbody").addEventListener("click", async (e) => {
  const aktion = e.target.closest("[data-aktion]");
  if (aktion) {
    const id = Number(aktion.dataset.id);
    if (aktion.dataset.aktion === "bearbeiten") { z.bearbeiten = id; auswahllisten(); einsaetzeZeigen(); }
    if (aktion.dataset.aktion === "abbrechen") { z.bearbeiten = null; einsaetzeZeigen(); }
    if (aktion.dataset.aktion === "loeschen") {
      const ein = z.einsaetze.einsaetze.find((x) => x.id === id);
      if (!confirm(`Einsatz ${ein.nr ?? ""} vom ${datum(ein.beginn)} wirklich löschen?`)) return;
      await api(`/api/einsatz/${id}`, { method: "DELETE" });
      toast("Einsatz gelöscht");
      z.offen.delete(id);
      await datenNeu();
    }
    if (aktion.dataset.aktion === "speichern") {
      try {
        await api(`/api/einsatz/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formWerte(document.querySelector(`[data-form="${id}"]`))) });
        z.bearbeiten = null;
        toast("Gespeichert");
        await datenNeu();
      } catch (err) { alert(err.message); }
    }
    return;
  }
  if (e.target.closest("tr.detail")) return;
  const zeile = e.target.closest("tr.zeile");
  if (!zeile) return;
  const id = Number(zeile.dataset.id);
  if (z.offen.has(id)) { z.offen.delete(id); if (z.bearbeiten === id) z.bearbeiten = null; } else z.offen.add(id);
  einsaetzeZeigen();
});

$("#ansicht-kameraden").addEventListener("click", (e) => {
  const th = e.target.closest("[data-sort]");
  if (!th) return;
  const f = th.dataset.sort;
  z.kamSort = { feld: f, ab: z.kamSort.feld === f ? !z.kamSort.ab : f !== "name" };
  kameradenZeigen();
});

// PDF-Dialog
const dialog = $("#pdf-dialog");
$("#knopf-pdf").addEventListener("click", async () => {
  if (!z.einsaetze) { try { z.einsaetze = await api(`/api/einsaetze?jahr=${z.jahr}`); } catch (e) { /* nur für Vorschläge */ } }
  auswahllisten();
  if (z.pdf.berichte.every((b) => b.gespeichert)) {
    z.pdf = { token: null, berichte: [], fehler: [] };
    $("#pdf-fehler").hidden = true;
    vorschauZeigen();
  }
  dialog.showModal();
});
$("#dialog-zu").addEventListener("click", () => dialog.close());
$("#hilfe-zu").addEventListener("click", () => $("#hilfe-dialog").close());
dialog.addEventListener("close", async () => {
  if (z.geaendert) { z.geaendert = false; await datenNeu(); }
});
const ablage = $("#ablage");
["dragenter", "dragover"].forEach((t) => ablage.addEventListener(t, (e) => { e.preventDefault(); ablage.classList.add("ziehen"); }));
["dragleave", "drop"].forEach((t) => ablage.addEventListener(t, () => ablage.classList.remove("ziehen")));
ablage.addEventListener("drop", (e) => { e.preventDefault(); pdfEinlesen(e.dataTransfer.files); });
ablage.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#eingabe-pdf").click(); } });
$("#eingabe-pdf").addEventListener("change", (e) => { pdfEinlesen(e.target.files); e.target.value = ""; });
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => e.preventDefault());
$("#vorschau").addEventListener("change", (e) => {
  const i = e.target.dataset.ersetzen;
  if (i === undefined) return;
  // Eingaben behalten: Formularwerte vor dem Neuzeichnen übernehmen
  const karteEl = e.target.closest(".vorschau-karte");
  Object.assign(z.pdf.berichte[i], formWerte(karteEl), { ersetzen: e.target.checked });
  vorschauZeigen();
});
$("#vorschau").addEventListener("click", (e) => {
  const k = e.target.closest("[data-uebernehmen]");
  if (k) uebernehmen(Number(k.dataset.uebernehmen));
});

// Start
(async () => {
  try {
    await jahreLaden();
  } catch (e) {
    $("#ansicht-auswertung").innerHTML = `<div class="meldung meldung-fehler">${esc(e.message)}</div>`;
  }
  await ansichtZeigen();
})();
