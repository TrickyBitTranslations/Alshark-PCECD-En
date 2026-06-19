/* Alshark translation browser.
   Static data (built by CI): data/script.json, data/status.json,
   data/suggestions.json. Submissions go through prefilled GitHub issues. */

const REPO = "TrickyBitTranslations/Alshark-PCECD-En";
const FILE_LABELS = { "system1.tsv": "Map & Event", "cutscene.tsv": "Dialogue" };

function fileLabel(f) {
  return FILE_LABELS[f] || f.replace(/\.tsv$/, "");
}

let SCRIPT = {}, STATUS = {}, SUGG = {};
let curFile = null;

async function boot() {
  const [s1, s2, s3] = await Promise.all([
    fetch("data/script.json").then(r => r.json()),
    fetch("data/status.json").then(r => r.json()),
    fetch("data/suggestions.json").then(r => r.json()).catch(() => ({})),
  ]);
  SCRIPT = s1; STATUS = s2; SUGG = s3;
  renderHeader();
  renderTabs();
  window.addEventListener("hashchange", route);
  document.getElementById("search").addEventListener("input", route);
  document.getElementById("only-untranslated").addEventListener("change", route);
  route();
}

function renderHeader() {
  const pct = STATUS.total ? (100 * STATUS.done / STATUS.total) : 0;
  document.getElementById("overall-bar").style.width = pct.toFixed(1) + "%";
  document.getElementById("overall-text").textContent =
    `${STATUS.done} / ${STATUS.total} lines translated (${pct.toFixed(1)}%)`;
  // human-reviewed vs machine translation, among translated lines (excl. ignored)
  const hbase = (STATUS.done || 0) - (STATUS.ignore || 0);
  const hpct = hbase ? (100 * (STATUS.human || 0) / hbase) : 0;
  const hb = document.getElementById("human-bar");
  if (hb) {
    hb.style.width = hpct.toFixed(1) + "%";
    document.getElementById("human-text").textContent =
      `${STATUS.human || 0} / ${hbase} human-reviewed (${hpct.toFixed(1)}%)`;
  }
}

function renderTabs() {
  const nav = document.getElementById("tabs");
  nav.innerHTML = "";
  for (const f of Object.keys(SCRIPT)) {
    const t = STATUS.files[f] || { lines: 0, done: 0, human: 0, ignore: 0 };
    const a = document.createElement("a");
    a.href = "#/" + f;
    a.dataset.file = f;
    a.innerHTML = `${fileLabel(f)} <small>${t.done}/${t.lines}</small>`;
    a.title = `${t.human || 0} human-reviewed, ${t.ignore || 0} ignored, `
            + `${t.done} translated of ${t.lines}`;
    nav.appendChild(a);
  }
  const names = (STATUS.names || []);
  if (names.length) {
    const a = document.createElement("a");
    a.href = "#/names";
    a.dataset.file = "names";
    const decided = names.filter(n => n.en).length;
    a.innerHTML = `Names &amp; terms <small>${decided}/${names.length}</small>`;
    nav.appendChild(a);
  }
  if (Object.keys(STATUS.tokens || {}).length) {
    const a = document.createElement("a");
    a.href = "#/tokens";
    a.dataset.file = "tokens";
    a.innerHTML = `&#123;Tokens&#125;`;
    nav.appendChild(a);
  }
}

function route() {
  const m = location.hash.match(/^#\/([^/]+)(?:\/(.+))?/);
  curFile = m ? decodeURIComponent(m[1]) : Object.keys(SCRIPT)[0];
  const block = m && m[2] ? decodeURIComponent(m[2]) : null;
  for (const a of document.querySelectorAll("#tabs a"))
    a.classList.toggle("active", a.dataset.file === curFile);
  if (curFile === "names") { renderNames(); return; }
  if (curFile === "tokens") { renderTokens(); return; }
  const q = document.getElementById("search").value.trim().toLowerCase();
  const onlyUn = document.getElementById("only-untranslated").checked;
  if (q || onlyUn) renderSearch(q, onlyUn);
  else if (block) renderBlock(curFile, block);
  else renderBlocks(curFile);
}

function renderTokens() {
  const el = document.getElementById("content");
  el.innerHTML = "";
  const head = div("block-head");
  head.innerHTML =
    `<h2>Embeddable name tokens <small>type <code>{Name}</code> in a translation
     to insert that name in the in-game highlight color - click to copy</small></h2>`;
  el.appendChild(head);
  const q = document.getElementById("search").value.trim().toLowerCase();
  // dedupe by English name (the data has one entry per token id)
  const byEn = {};
  for (const [, en] of Object.entries(STATUS.tokens || {})) byEn[en] = en;
  const jpFor = {};
  for (const n of (STATUS.names || [])) if (n.en) jpFor[n.en] = n.jp;
  const grid = div("token-grid");
  for (const en of Object.values(byEn).sort((a, b) => a.localeCompare(b))) {
    if (q && !en.toLowerCase().includes(q)
          && !(jpFor[en] || "").toLowerCase().includes(q)) continue;
    const chip = div("token-chip");
    chip.innerHTML = `<code>{${esc(en)}}</code>`
      + (jpFor[en] ? `<span class="jp">${esc(jpFor[en])}</span>` : "");
    chip.title = "Click to copy {" + en + "}";
    chip.addEventListener("click", () => {
      navigator.clipboard?.writeText(`{${en}}`);
      chip.classList.add("copied");
      setTimeout(() => chip.classList.remove("copied"), 800);
    });
    grid.appendChild(chip);
  }
  el.appendChild(grid);
}

function renderNames() {
  const el = document.getElementById("content");
  el.innerHTML = "";
  const head = div("block-head");
  head.innerHTML =
    `<h2>Names &amp; terms <small>shared across the whole script via {NAME}
     tokens - propose readings or contest existing ones</small></h2>`;
  el.appendChild(head);
  const q = document.getElementById("search").value.trim().toLowerCase();
  const table = document.createElement("table");
  table.className = "lines";
  const thead = document.createElement("tr");
  thead.className = "head";
  for (const [cls, label] of [["sp", "Token"], ["jp", "Japanese"],
                              ["en", "English"], ["act", ""]]) {
    const th = document.createElement("th");
    th.className = cls;
    th.textContent = label;
    thead.appendChild(th);
  }
  table.appendChild(thead);
  for (const n of STATUS.names) {
    if (q && !(n.jp.toLowerCase().includes(q) || n.en.toLowerCase().includes(q)))
      continue;
    const tr = document.createElement("tr");
    tr.className = n.en ? "done" : "todo";
    tr.appendChild(td("sp", "0x" + n.tok.toString(16).padStart(2, "0")));
    tr.appendChild(td("jp", n.jp));
    tr.appendChild(td("en", n.en || "-"));
    const act = document.createElement("td");
    act.className = "act";
    const a = document.createElement("a");
    a.className = "suggest";
    const p = new URLSearchParams({
      template: "name-suggestion.yml",
      title: `[name] ${n.jp}`,
      term: `${n.jp} (token 0x${n.tok.toString(16).padStart(2, "0")})`,
      current: n.en || "none yet",
    });
    a.href = `https://github.com/${REPO}/issues/new?${p}`;
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = n.en ? "Contest" : "Propose";
    act.appendChild(a);
    tr.appendChild(act);
    table.appendChild(tr);
  }
  el.appendChild(table);
}

function blockMeta(file, block) {
  const lines = SCRIPT[file][block];
  const real = lines.filter(l => !isEngineData(l));
  const done = real.filter(l => l.en).length;
  const b = (STATUS.budgets || {})[file + ":" + block];
  return { lines, real, done, budget: b };
}

/* A scene's text decompresses into one shared 2048-byte buffer; this shows how
   much of that is left (the real size limit). null for non-dialogue blocks. */
function budgetBadge(budget) {
  if (!budget) return null;
  const { used, limit } = budget;
  const free = limit - used;
  const pct = Math.min(100, Math.max(0, 100 * used / limit));
  const cls = free <= 0 ? "full" : free < 128 ? "tight" : "ok";
  const el = div("budget " + cls);
  el.innerHTML =
    `<div class="bbar"><div style="width:${pct}%"></div></div>` +
    `<span class="btxt"><b>${free}</b> B free <small>${used}/${limit}</small></span>`;
  el.title = `Scene text uses ${used} of ${limit} decompressed bytes (the shared ` +
             `scene buffer); ${free} bytes left. Going over crashes the game, so the ` +
             `build rejects it.`;
  return el;
}

function renderBlocks(file) {
  const el = document.getElementById("content");
  el.innerHTML = "";
  const grid = div("block-grid");
  let shown = 0;
  for (const block of Object.keys(SCRIPT[file])) {
    const { real, done, budget } = blockMeta(file, block);
    if (real.length === 0) continue;          // all engine-data rows, nothing to translate
    shown++;
    const card = div("block-card");
    const pct = real.length ? (100 * done / real.length) : 0;
    card.innerHTML =
      `<h3>Scene ${esc(block)}</h3>
       <div class="progress sm"><div style="width:${pct}%"></div></div>
       <p>${done}/${real.length} lines` +
      `</p>`;
    const bb = budgetBadge(budget);
    if (bb) card.appendChild(bb);
    card.addEventListener("click", () => location.hash = `#/${file}/${block}`);
    grid.appendChild(card);
  }
  el.appendChild(grid);
  if (!shown) el.innerHTML = `<p class="dim">No translatable scenes in this file.</p>`;
}

function renderBlock(file, block) {
  const el = document.getElementById("content");
  el.innerHTML = "";
  const { lines, real, done, budget } = blockMeta(file, block);
  const head = div("block-head");
  head.innerHTML =
    `<a href="#/${file}">← scenes</a>
     <h2>Scene ${esc(block)} <small>${done}/${real.length} translated</small></h2>`;
  const bb = budgetBadge(budget);
  if (bb) head.appendChild(bb);
  el.appendChild(head);
  el.appendChild(linesTable(file, block, lines));
}

function renderSearch(q, onlyUn) {
  const el = document.getElementById("content");
  el.innerHTML = "";
  const rows = [];
  for (const [block, lines] of Object.entries(SCRIPT[curFile])) {
    for (const l of lines) {
      if (onlyUn && (l.en || isEngineData(l))) continue;
      if (q && !(l.jp.toLowerCase().includes(q)
                 || enPlain(l.en).toLowerCase().includes(q)
                 || speakerName(l.sp).toLowerCase().includes(q)
                 || l.sp.toLowerCase().includes(q))) continue;
      rows.push({ block, l });
    }
  }
  const head = div("block-head");
  head.innerHTML = `<h2>${rows.length} matching lines <small>in ${fileLabel(curFile)}</small></h2>`;
  el.appendChild(head);
  const byBlock = {};
  for (const r of rows) (byBlock[r.block] ??= []).push(r.l);
  for (const [block, ls] of Object.entries(byBlock).slice(0, 50)) {
    const h = document.createElement("h3");
    h.className = "scene-h";
    h.innerHTML = `<a href="#/${curFile}/${block}">Scene ${esc(block)}</a>`;
    el.appendChild(h);
    el.appendChild(linesTable(curFile, block, ls));
  }
}

/* Rows flagged by the data build as extraction noise that crossed into
   engine bytecode - shown dimmed, not translatable yet. */
function isEngineData(l) {
  return l.x === 1;
}

function linesTable(file, block, lines) {
  const table = document.createElement("table");
  table.className = "lines";
  const thead = document.createElement("tr");
  thead.className = "head";
  for (const [cls, label] of [["sp", "Speaker"], ["jp", "Japanese"],
                              ["en", "English"], ["act", ""]]) {
    const th = document.createElement("th");
    th.className = cls;
    th.textContent = label;
    thead.appendChild(th);
  }
  table.appendChild(thead);
  for (const l of lines) {
    const tr = document.createElement("tr");
    const sug = SUGG[file + ":" + block + " " + l.id] || [];
    const open = sug.filter(s => s.state === "open");
    const unsafe = isEngineData(l);
    tr.className = unsafe ? "unsafe" : (l.en ? "done" : "todo");
    if (l.st) tr.classList.add("st-" + l.st);   // human / ignore review marker
    tr.appendChild(td("sp", speakerName(l.sp)));
    tr.appendChild(td("jp", l.jp.replaceAll(/(\\n)+/g, "\n")));
    tr.appendChild(tdEnglish(l.en));
    const act = document.createElement("td");
    act.className = "act";
    if (unsafe) {
      const s = document.createElement("span");
      s.className = "engine";
      s.title = "This row overlaps engine data and can't be translated yet.";
      s.textContent = "engine data";
      act.appendChild(s);
      tr.appendChild(act);
      table.appendChild(tr);
      continue;
    }
    if (l.st) {
      const b = document.createElement("span");
      b.className = "review " + l.st;
      b.textContent = l.st;
      act.appendChild(b);
    }
    if (open.length) {
      const best = open.find(s => s.verdict === "valid") || open[0];
      const a = document.createElement("a");
      a.className = "sug " + best.verdict;
      a.href = `https://github.com/${REPO}/issues/${best.n}`;
      a.textContent = `${open.length} suggestion${open.length > 1 ? "s" : ""}`;
      a.title = "Open suggestion(s) for this line";
      act.appendChild(a);
    }
    const s = document.createElement("a");
    s.className = "suggest";
    s.href = suggestUrl(file, block, l);
    s.target = "_blank";
    s.rel = "noopener";
    s.textContent = l.en ? "Improve" : "Suggest";
    act.appendChild(s);
    tr.appendChild(act);
    table.appendChild(tr);
  }
  return table;
}

function suggestUrl(file, block, l) {
  const p = new URLSearchParams({
    template: "translation-suggestion.yml",
    title: `[tl] ${l.sp || "line"} ${block} ${l.id}`,
    file: file,
    line: `${block} ${l.id}`,
    original: l.jp,
  });
  return `https://github.com/${REPO}/issues/new?${p}`;
}

function speakerName(sp) {
  return (STATUS.speakers || {})[sp] || sp;
}

function enPlain(en) {
  return (en || "").replace(/\{([^}]+)\}/g,
    (_, k) => (STATUS.tokens || {})[k.toUpperCase()] || k);
}

/* English cell: \n -> line break, \p -> page divider, {NAME} -> highlighted
   name (the game renders tokens in a highlight color too). */
function tdEnglish(en) {
  const t = document.createElement("td");
  t.className = "en";
  if (!en) { t.textContent = "-"; return t; }
  let afterPage = false;                 // \p{NAME}\n = next box's title header
  for (const part of en.split(/(\{[^}]+\}|\\n|\\p)/)) {
    if (!part) continue;
    if (part === "\\n") {
      t.appendChild(document.createElement("br"));
    } else if (part === "\\p") {
      const d = document.createElement("span");
      d.className = "page-break";
      d.textContent = "- next box -";
      t.appendChild(d);
      afterPage = true;
      continue;
    } else if (part.startsWith("{")) {
      const key = part.slice(1, -1).toUpperCase();
      const s = document.createElement("span");
      s.className = afterPage ? "tok box-title" : "tok";
      if (afterPage) s.title = "Title of the next dialogue box";
      s.textContent = (STATUS.tokens || {})[key] || part;
      t.appendChild(s);
    } else {
      t.appendChild(document.createTextNode(part));
    }
    afterPage = false;
  }
  return t;
}

function div(cls) { const d = document.createElement("div"); d.className = cls; return d; }
function td(cls, text) { const t = document.createElement("td"); t.className = cls; t.textContent = text; return t; }
function esc(s) { return s.replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

boot();
