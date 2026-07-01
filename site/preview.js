/* Dialogue preview: render a cutscene line the way the #-engine flows it on screen.
   Params:
     ?id=<block>:<str_off>   line to preview (from data/render.json, precomputed by the Python
                             engine model so line breaks match the game exactly)
     ?file=cutscene.tsv      (default) for the "back to review" link
     ?en=<base64>            an edited/recommended translation (live). Phase 2 (needs render.js);
                             for now we show the committed line and a note.
   Each utterance renders as its own blue box; every glyph is an inline-block of its real VWF
   advance width, so the horizontal fit is accurate even though the glyph shapes are a web font. */
"use strict";

const REPO = "TrickyBitTranslations/Alshark-PCECD-En";
const P = new URLSearchParams(location.search);

function charPx(ch, meta) {
  const o = ch.codePointAt(0);
  return (o >= 0x20 && o <= 0x7e) ? meta.widths[o - 0x20] : meta.fullPx;
}

function renderLine(line, meta) {
  const el = document.createElement("div");
  el.className = "dlg-line" + (line.over ? " over" : "");
  for (const ch of line.text) {
    const g = document.createElement("span");
    g.className = "glyph";
    g.style.width = `calc(${charPx(ch, meta)}px * var(--sc))`;
    g.textContent = ch === " " ? " " : ch;
    el.appendChild(g);
  }
  const r = document.createElement("span");
  r.className = "pv-ruler";
  r.textContent = `${line.px}px`;
  el.appendChild(r);
  return el;
}

/* group lines into boxes: a blank line is a box/page break in the engine flow */
function toBoxes(lines) {
  const boxes = [];
  let cur = [];
  for (const l of lines) {
    if (l.text === "" && l.px === 0) { if (cur.length) { boxes.push(cur); cur = []; } }
    else cur.push(l);
  }
  if (cur.length) boxes.push(cur);
  return boxes;
}

function renderStage(lines, meta) {
  const stage = document.createElement("div");
  stage.className = "pv-stage";
  for (const box of toBoxes(lines)) {
    const b = document.createElement("div");
    b.className = "dlg-box";
    for (const l of box) b.appendChild(renderLine(l, meta));
    stage.appendChild(b);
  }
  return stage;
}

function note(msg) {
  const n = document.createElement("div");
  n.className = "pv-note";
  n.innerHTML = msg;
  return n;
}

async function boot() {
  const body = document.getElementById("pv-body");
  const id = P.get("id");
  const file = P.get("file") || "cutscene.tsv";
  document.getElementById("pv-id").textContent = id ? `${file} · ${id}` : "";
  if (!id) { body.innerHTML = `<p class="dim">No <code>?id=block:str_off</code> given.</p>`; return; }

  let render;
  try { render = await fetch("data/render.json").then(r => r.json()); }
  catch { body.innerHTML = `<p class="dim">Couldn't load render data.</p>`; return; }

  const lines = render.lines[id];
  body.innerHTML = "";
  if (P.get("en")) {
    body.appendChild(note(
      "<b>Live preview</b> of edited text is coming next (it needs the JS renderer, " +
      "<code>render.js</code>). Showing the <i>committed</i> line below for now."));
  }
  if (!lines) {
    body.appendChild(note(`No rendered preview for <code>${id}</code> — it may be untranslated or ` +
      `not a cutscene line. Only translated <code>cutscene.tsv</code> lines are previewable.`));
    return;
  }
  body.appendChild(renderStage(lines, render.meta));

  const actions = document.createElement("div");
  actions.className = "pv-actions";
  const [block] = id.split(":");
  actions.innerHTML =
    `<a href="index.html#/${file}/${block}">← back to this scene</a>` +
    ` <span class="muted">box width ${render.meta.boxPx}px · ${lines.filter(l=>l.text).length} text rows</span>`;
  body.appendChild(actions);
}

boot();
