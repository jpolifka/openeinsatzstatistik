// Stichwortsuche im Einsatzformular (Katalog der Wehr). Wird vor app.js geladen.

// ------------------------------------------------------------ Stichwortsuche
const fold = (s) => s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/ß/g, "ss");
const keywordName = (e) => config.keyword_catalog.find((k) => k.code === (e.subcode ? `${e.keyword}.${e.subcode}` : e.keyword))?.name;

/** Katalogeinträge, in denen alle eingegebenen Wörter vorkommen – in Stichwort (mit/ohne Punkt), Bezeichnung
 *  oder einem Meldebild. Treffer in Stichwort/Bezeichnung zuerst; bei Treffern im Meldebild steht es in hint. */
function searchKeywords(query) {
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const matches = (text) => words.every((w) => fold(text).includes(w));
  const direct = [], viaTerm = [];
  for (const k of config.keyword_catalog) {
    if (k.active === false) continue;          // deaktiviert: nur noch Bezeichnung für alte Einsätze
    if (matches(`${k.code} ${k.code.replace(".", "")} ${k.name}`)) { direct.push(k); continue; }
    const term = k.terms.split(", ").find(matches) || (matches(k.terms) && k.terms);
    if (term) viaTerm.push({ ...k, hint: term });
  }
  return [...direct, ...viaTerm].slice(0, 15);
}

let keywordList = null, keywordInput = null;
function showKeywordSuggestions(input) {
  const matches = searchKeywords(input.value);
  if (!matches.length) { closeKeywordSuggestions(); return; }
  if (!keywordList) {
    keywordList = document.createElement("ul");
    keywordList.id = "keyword-suggestions";
    keywordList.className = "suggestions";
    keywordList.setAttribute("role", "listbox");
    // mousedown statt click: das Eingabefeld behält den Fokus
    keywordList.addEventListener("mousedown", (e) => {
      const item = e.target.closest("[data-code]");
      e.preventDefault();
      if (item) chooseKeyword(item.dataset.code);
    });
    document.body.append(keywordList);
  }
  keywordInput = input;
  input.setAttribute("aria-controls", keywordList.id);
  input.setAttribute("aria-expanded", "true");
  keywordList.innerHTML = matches.map((k, i) => `<li role="option" data-code="${esc(k.code)}" class="${i ? "" : "active"}">
    <b>${esc(k.code)}</b><span>${esc(k.name)}${k.hint ? `<small>${esc(k.hint)}</small>` : ""}</span></li>`).join("");
  const r = input.getBoundingClientRect();
  Object.assign(keywordList.style, { left: `${Math.min(r.left, window.innerWidth - 340)}px`, top: `${r.bottom + 4}px` });
  keywordList.hidden = false;
}

function closeKeywordSuggestions() {
  if (keywordList) keywordList.hidden = true;
  keywordInput?.setAttribute("aria-expanded", "false");
  keywordInput = null;
}

function chooseKeyword(code) {
  const form = formOf(keywordInput), [keyword, subcode = ""] = code.split(".");
  keywordInput.value = keyword;
  keywordInput.classList.remove("missing");
  $('input[name="subcode"]', form).value = subcode;
  closeKeywordSuggestions();
}

function navigateKeywordSuggestions(e) {
  if (!keywordList || keywordList.hidden) return;
  const items = [...$$("li", keywordList)], current = items.findIndex((li) => li.classList.contains("active"));
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    const next = (current + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
    items.forEach((li, i) => li.classList.toggle("active", i === next));
    items[next].scrollIntoView({ block: "nearest" });
  } else if (e.key === "Enter") {
    e.preventDefault();
    chooseKeyword(items[Math.max(current, 0)].dataset.code);
  } else if (e.key === "Escape") {
    e.stopPropagation();   // Dialog nicht schließen
    e.preventDefault();
    closeKeywordSuggestions();
  }
}
// Fest positionierte Liste beim Scrollen schließen statt hinterherzuschieben
window.addEventListener("scroll", (e) => { if (e.target !== keywordList) closeKeywordSuggestions(); }, true);
window.addEventListener("resize", closeKeywordSuggestions);
