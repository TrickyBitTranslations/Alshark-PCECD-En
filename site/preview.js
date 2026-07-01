/* Dialogue preview: render a cutscene line the way the #-engine flows it on screen.
   Params:
     ?id=<block>:<str_off>   line to preview (from data/render.json, precomputed by the Python
                             engine model so line breaks match the game exactly)
     ?file=cutscene.tsv      (default) for the "back to review" link
     ?en=<base64>            an edited/recommended translation (live, via render.js + the line's raw)
   Each utterance renders as its own blue box. Glyph shapes are a web font (approximate); the line
   BREAKS are exact, and a per-line gauge shows the real in-game px vs the 216px box so fit is true. */
"use strict";

const P = new URLSearchParams(location.search);

function renderLine(line, meta) {
  const el = document.createElement("div");
  el.className = "dlg-line" + (line.over ? " over" : "") + (line.name ? " name" : "");
  const txt = document.createElement("span");
  txt.className = "dlg-text";
  txt.textContent = line.text;
  el.appendChild(txt);
  const gauge = document.createElement("span");
  gauge.className = "dlg-gauge";
  gauge.title = line.px + " / " + meta.boxPx + " px";
  const fill = document.createElement("i");
  fill.style.width = Math.min(100, 100 * line.px / meta.boxPx) + "%";
  if (line.px > meta.boxPx) fill.classList.add("over");
  gauge.appendChild(fill);
  el.appendChild(gauge);
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

function decodeB64(s) {
  try { return decodeURIComponent(escape(atob(s.replace(/-/g, "+").replace(/_/g, "/")))); }
  catch { return null; }
}

async function boot() {
  const body = document.getElementById("pv-body");
  const id = P.get("id");
  const file = P.get("file") || "cutscene.tsv";
  document.getElementById("pv-id").textContent = id ? file + " · " + id : "";
  if (!id) { body.innerHTML = "<p class=\"dim\">No <code>?id=block:str_off</code> given.</p>"; return; }

  let data;
  try { data = await fetch("data/render.json").then(r => r.json()); }
  catch { body.innerHTML = "<p class=\"dim\">Couldn't load render data.</p>"; return; }

  const meta = data.meta;
  let lines = data.lines[id];
  body.innerHTML = "";

  // live preview of an edited/recommended translation
  const enB64 = P.get("en");
  if (enB64 && window.Render) {
    const en = decodeB64(enB64);
    const rawHex = (data.raws || {})[id];
    if (en != null && rawHex) {
      try {
        lines = window.Render.layout(en, window.Render.bytesFromHex(rawHex), meta);
        body.appendChild(note("<b>Live preview</b> of a recommended translation."));
      } catch (e) {
        body.appendChild(note("Couldn't render this edit: <code>" + String(e.message || e) +
          "</code>. The code sequence (<code>#</code>/<code>%</code>/<code>$</code>) must match the original line."));
      }
    } else if (en != null) {
      body.appendChild(note("No raw bytes for <code>" + id + "</code> to render an edit against; showing the committed line."));
    }
  }

  if (!lines) {
    body.appendChild(note("No rendered preview for <code>" + id + "</code> — it may be untranslated or " +
      "not a cutscene line. Only translated <code>cutscene.tsv</code> lines are previewable."));
    return;
  }
  body.appendChild(renderStage(lines, meta));

  const actions = document.createElement("div");
  actions.className = "pv-actions";
  const block = id.split(":")[0];
  actions.innerHTML =
    "<a href=\"index.html#/" + file + "/" + block + "\">← back to this scene</a>" +
    " <span class=\"muted\">box width " + meta.boxPx + "px · " +
    lines.filter(l => l.text).length + " text rows</span>";
  body.appendChild(actions);
}

boot();
