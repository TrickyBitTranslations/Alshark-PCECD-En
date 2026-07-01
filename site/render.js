/* render.js - browser port of the #-engine dialogue render model (tools/alshark/dialogcodec.py +
   render.py). Given a recommended English translation and the line's original raw bytes, it produces
   the exact display lines the game flows (same merge boundary-spacing + box-width word-wrap), so the
   preview of an *edited* line matches in-game. The Python side is the source of truth;
   tools/test_render_conformance.py runs this (via node) against it over every line and fails CI on
   drift. Widths / name maps / the non-ASCII byte tables all come from render.json `meta`.

   Works in the browser (window.Render) and under node (module.exports + a CLI: it reads a JSON array
   of {english, raw_hex} on argv[2] and prints the layout array). */
"use strict";
(function (root) {

  const TOKEN = /^<([0-9a-fA-F]{2})>$/;
  const WTOK = /<[0-9a-fA-F]{2}>|[#%$@<>]|\s+|[^\s#%$@<>]+/g;
  const NAME = /\$<([0-9a-fA-F]{2})>|<[0-9a-fA-F]{2}>|[\s\S]/g;
  const FULL_PX = 12;
  const RESET = new Set(["2304", "2305", "2306", "235f", "233e"]);
  const SPACE = new Set(["2321", "2300", "2303", "2301"]);

  const hex = b => b.toString(16).padStart(2, "0");
  const hexOf = arr => arr.map(hex).join("");
  const bytesFromHex = h => { const a = []; for (let i = 0; i < h.length; i += 2) a.push(parseInt(h.substr(i, 2), 16)); return a; };

  function cpx(ch, meta) {
    const o = ch.codePointAt(0);
    return (o >= 0x20 && o <= 0x7e) ? meta.widths[o - 0x20] : FULL_PX;
  }
  const wpx = (seg, meta) => { let s = 0; for (const c of seg) s += cpx(c, meta); return s; };
  const isVis = ch => !!ch && !/\s/.test(ch) && !"#%$<>@".includes(ch);

  /* bytes -> display string, using meta's byte tables so it matches the Python decode exactly. */
  function decode(b, meta) {
    const sb = (meta && meta.sb) || {}, dw = (meta && meta.dw) || {};
    let out = "", i = 0;
    while (i < b.length) {
      const c = b[i];
      if ((c >= 0x81 && c <= 0x9f) || (c >= 0xe0 && c <= 0xef)) { out += dw[hex(c) + hex(b[i + 1])] || "�"; i += 2; }
      else if (c >= 0xa1 && c <= 0xdf) { out += (c in sb ? sb[c] : "｡"); i += 1; }
      else if (c >= 0x20 && c <= 0x7e) { out += String.fromCharCode(c); i += 1; }
      else { out += "<" + hex(c) + ">"; i += 1; }
    }
    return out;
  }

  /* English markup string -> engine bytes. <xx> -> that byte; ASCII -> its code; other chars via the
     meta.enc table (Shift-JIS / single-byte hiragana), matching dialogcodec._enc_text. */
  function pushChar(out, ch, enc) {
    const code = ch.charCodeAt(0);
    if (code <= 0x7e) { out.push(code); return; }
    const h = enc[ch];
    if (h) { for (let k = 0; k < h.length; k += 2) out.push(parseInt(h.substr(k, 2), 16)); }
    else out.push(code & 0xff);                          // unknown non-ASCII (ASCII edits never hit this)
  }
  function encodeRaw(s, meta) {
    const enc = (meta && meta.enc) || {};
    const out = []; let last = 0, m;
    const re = /<([0-9a-fA-F]{2})>/g;
    while ((m = re.exec(s))) {
      for (let i = last; i < m.index; i++) pushChar(out, s[i], enc);
      out.push(parseInt(m[1], 16));
      last = re.lastIndex;
    }
    for (let i = last; i < s.length; i++) pushChar(out, s[i], enc);
    return out;
  }

  function pctLen(d, i) {
    const s = d[i + 1];
    if (s >= 0x80) return 2;
    if ([0x04, 0x05, 0x07, 0x08, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x19, 0x1a,
      0x1c, 0x1d, 0x21, 0x25, 0x26].includes(s)) return 3 + d[i + 2];
    const FIXED = { 0x00: 4, 0x01: 3, 0x02: 2, 0x06: 5, 0x09: 4, 0x0a: 4, 0x0b: 5, 0x0c: 5,
      0x0d: 6, 0x0e: 2, 0x0f: 3, 0x17: 4, 0x18: 5, 0x1b: 4, 0x1f: 4, 0x20: 6 };
    if (s in FIXED) return FIXED[s];
    if (s === 0x03) return d[i + 3] === 0 ? 3 : 5;
    if (s === 0x1e) { let j = i + 3 + d[i + 2] + 2; while (j < d.length && d[j] !== 0x00) j++; return j - i + 3; }
    throw new Error("render: unhandled %<" + hex(s) + "> at " + i);
  }

  function tokenize(b) {
    const segs = []; let i = 0, run = [];
    const flush = () => { if (run.length) { segs.push(["dlg", run]); run = []; } };
    while (i < b.length) {
      const c = b[i];
      if (c === 0x23) { flush(); const ln = (i + 1 < b.length && b[i + 1] === 0x3c) ? 5 : 2; segs.push(["op", b.slice(i, i + ln)]); i += ln; }
      else if (c === 0x25) { flush(); const ln = pctLen(b, i); segs.push(["op", b.slice(i, i + ln)]); i += ln; }
      else if (c === 0x24) { run.push(b[i], b[i + 1]); i += 2; }
      else if (c === 0x40) { run.push(b[i]); i += 1; }
      else if ((c >= 0x81 && c <= 0x9f) || (c >= 0xe0 && c <= 0xef)) { run.push(b[i], b[i + 1]); i += 2; }
      else if ((c >= 0xa1 && c <= 0xdf) || (c >= 0x20 && c <= 0x7e)) { run.push(b[i]); i += 1; }
      else { flush(); segs.push(["op", b.slice(i, i + 1)]); i += 1; }
    }
    flush();
    return segs;
  }

  const zeroW = t => t === "#" || t === "%" || t === "<" || t === ">" || TOKEN.test(t);

  /* faithful port of dialogcodec.wrap() - inserts @ line breaks so each rendered line fits `width`. */
  function wrap(s, meta, opts) {
    opts = opts || {};
    const width = opts.width || meta.boxPx;
    const nameW = opts.nameW || meta.nameWDefault;
    const startPx = opts.startPx || 0;
    const lines = [{ sep: "", toks: [], px: startPx, words: 0, auto: false }];
    let space = "";
    const cur = () => lines[lines.length - 1];
    const newline = (sep, auto) => lines.push({ sep, toks: [], px: 0, words: 0, auto });
    const toks = s.match(WTOK) || [];
    for (let ti = 0; ti < toks.length; ti++) {
      const a = toks[ti];
      if (a === "@") { newline("@", false); space = ""; }
      else if (a === "$") {
        const nx = ti + 1 < toks.length ? TOKEN.exec(toks[ti + 1]) : null;
        const nw = nx ? (meta.nameW[parseInt(nx[1], 16)] ?? nameW) : nameW;
        let c = cur();
        if (c.px && c.px + wpx(space, meta) + nw > width) { newline("@", true); space = ""; c = cur(); }
        else if (space && c.px) { c.toks.push(space); c.px += wpx(space, meta); }
        space = "";
        c.toks.push("$"); c.px += nw; c.words += 1;
      } else if (TOKEN.test(a)) {
        cur().toks.push(a);
        if (a === "<05>") { newline("", false); space = ""; }
      } else if (a === "#" || a === "%" || a === "<" || a === ">") {
        cur().toks.push(a);
      } else if (/^\s+$/.test(a)) {
        space = a;
      } else {
        const w = wpx(a, meta); let c = cur();
        if (c.px && c.px + wpx(space, meta) + w > width) {
          newline("@", true); space = ""; c = cur();
          c.toks.push(a); c.px += w; c.words += 1;
        } else {
          if (space) { c.toks.push(space); c.px += wpx(space, meta); }
          space = "";
          c.toks.push(a); c.px += w; c.words += 1;
        }
      }
    }
    for (let i = 1; i < lines.length; i++) {          // anti-widow
      const ln = lines[i], prev = lines[i - 1];
      if (!(ln.auto && ln.words === 1 && prev.words >= 2)) continue;
      let wi = -1; for (let j = 0; j < prev.toks.length; j++) if (!zeroW(prev.toks[j])) wi = j;
      if (wi < 0) continue;
      const si = (wi > 0 && /^\s+$/.test(prev.toks[wi - 1])) ? wi - 1 : null;
      const word = prev.toks[wi];
      if (word === "$") continue;
      const gap = si !== null ? prev.toks[si] : " ";
      if (wpx(word, meta) + wpx(gap, meta) + ln.px > width) continue;
      prev.toks.splice(wi, 1);
      if (si !== null) prev.toks.splice(si, 1);
      prev.px -= wpx(word, meta) + wpx(gap, meta); prev.words -= 1;
      ln.toks = [word, gap].concat(ln.toks);
      ln.px += wpx(word, meta) + wpx(gap, meta); ln.words += 1;
    }
    let out = "";
    for (const ln of lines) out += ln.sep + ln.toks.join("");
    return { out, endPx: lines[lines.length - 1].px };
  }

  function encodeRun(s, startPx, meta) {
    if (s && !s.trim()) return { bytes: encodeRaw(s, meta), endPx: startPx + wpx(s, meta) };
    const w = wrap(s, meta, { startPx });
    return { bytes: encodeRaw(w.out, meta), endPx: w.endPx };
  }

  /* faithful port of dialogcodec.merge() - keep raw's code bytes, swap in english glyph runs. */
  function merge(english, raw, meta) {
    const rawSegs = tokenize(raw);
    const enDlg = tokenize(encodeRaw(english, meta)).filter(s => s[0] === "dlg").map(s => s[1]);
    const nDlg = rawSegs.filter(s => s[0] === "dlg").length;
    if (enDlg.length !== nDlg) throw new Error("merge: " + nDlg + " raw runs vs " + enDlg.length + " english");
    const enDec = enDlg.map(d => decode(d, meta));
    const out = []; let di = 0, pen = 0, last = "", lead = false;
    for (let si = 0; si < rawSegs.length; si++) {
      const t = rawSegs[si][0], d = rawSegs[si][1];
      if (t === "op") {
        const joins = si + 1 < rawSegs.length && rawSegs[si + 1][0] === "dlg";
        if (last && joins) {
          const nxt = enDec[di];
          if (nxt.slice(0, 1) !== " " && nxt.trim()) {
            if (last === " " && !RESET.has(hexOf(d))) { out.push(0x20); pen += cpx(" ", meta); }
            else if (SPACE.has(hexOf(d)) && isVis(last) && isVis(nxt[0])) lead = true;
          }
        }
        last = "";
        for (const x of d) out.push(x);
        if (RESET.has(hexOf(d))) pen = 0;
      } else {
        let en = enDec[di]; di += 1;
        if (lead) { en = " " + en; lead = false; }
        const r = encodeRun(en, pen, meta); pen = r.endPx;
        for (const x of r.bytes) out.push(x);
        last = en ? en[en.length - 1] : "";
      }
    }
    return out;
  }

  /* the display-line model the preview renders: [{text, px, over}] */
  function layout(english, raw, meta, width) {
    width = width || meta.boxPx;
    const merged = (english && english.trim()) ? merge(english, raw, meta) : raw;
    const names = meta.nameText || {};
    const lines = [];
    let text = "", px = 0;
    const end = () => { lines.push({ text, px, over: px > width }); text = ""; px = 0; };
    for (const seg of tokenize(merged)) {
      if (seg[0] === "op") { if (RESET.has(hexOf(seg[1]))) end(); continue; }
      const s = decode(seg[1], meta); let m;
      NAME.lastIndex = 0;
      while ((m = NAME.exec(s))) {
        const tok = m[0];
        if (tok === "@") end();
        else if (m[1] !== undefined) { const nm = names[parseInt(m[1], 16)] ?? ("{" + m[1] + "}"); text += nm; px += wpx(nm, meta); }
        else if (tok[0] === "<" || "#%$>".includes(tok)) { /* zero width */ }
        else { text += tok; px += cpx(tok, meta); }
      }
    }
    end();
    while (lines.length && lines[lines.length - 1].text === "") lines.pop();
    return lines;
  }

  const API = { layout, merge, wrap, tokenize, decode, encodeRaw, bytesFromHex, cpx, wpx };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.Render = API;

  if (typeof require !== "undefined" && typeof module !== "undefined" && require.main === module) {
    const fs = require("fs");
    const input = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
    const meta = input.meta;
    const res = input.lines.map(l => {
      try { return layout(l.english, bytesFromHex(l.raw_hex), meta); }
      catch (e) { return null; }
    });
    process.stdout.write(JSON.stringify(res));
  }
})(typeof self !== "undefined" ? self : this);
