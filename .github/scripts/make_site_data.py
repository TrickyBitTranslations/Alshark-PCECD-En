"""Generate the static JSON the website reads (site/data/*.json).

  script.json       every line: ids, speaker, japanese, english
  status.json       progress totals + per-block byte budgets
  suggestions.json  open suggestion issues mapped to line ids (optional;
                    pass --issues <file> with the GitHub API JSON)

Computed from script/*.tsv + the codecs alone; no game dump needed.

Usage: python .github/scripts/make_site_data.py [--issues issues.json]
"""
import json
import pathlib
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent  # repo root (.github/scripts/..)
sys.path.insert(0, str(ROOT / "tools"))
import tsv
from alshark import textcodec, dialogcodec

OUT = ROOT / "site" / "data"
PAGE = 0x2000                         # a block loads into one 8KB logical page
CODECS = {"cutscene.tsv": dialogcodec}    # else tier-1 textcodec

# Files hidden from the site and dropped from all stats.
# system1.tsv (839 lines) is leftover MIGHT & MAGIC III: ISLES OF TERRA text, NOT Alshark.
# Right Stuff / Victor also did the M&M III PC Engine CD port, so its whole script sits dead on
# this disc. Proven by content: Sheltem x17, Terra x8, Fountainhead, Greywind, orcs, gargoyles,
# Gold currency, "exp" - and ZERO Alshark proper nouns (Sion / Zolias / meteor / Credits) across
# all 839 lines. These blocks are not loaded by Alshark. Do NOT translate it; keep it hidden.
#
# cutscene_subs.tsv is the anime-cutscene subtitle surface: a different schema entirely
# (recno_hex<TAB>English, comment-headed - no block_off/raw_hex), built straight into the
# subtitle blob by rebuild/build.py. It has no block/pointer layout for this script to size,
# so skip it here rather than parse it with the standard columns.
EXCLUDE = {"system1.tsv", "cutscene_subs.tsv"}


def block_used(codec, entries):
    """Rebuilt block size in bytes: pointer table + entry bytes."""
    total = 2 * len(entries)
    for en, raw in entries:
        total += len(codec.encode(en)) if en else len(raw)
    return total


def has_text(codec, raw):
    """True if the row holds displayable glyph text worth translating.

    Pure control-code / padding rows (no glyph runs) return False, so the site
    hides them and drops them from every count. A decode failure is treated as
    text present (a deferred/uncrackable line), so it stays counted."""
    try:
        if codec is dialogcodec:
            return any(t == "dlg" for t, _ in codec.tokenize(raw))
        s = codec.decode(raw)
        return bool(s and s.strip())
    except Exception:
        return True


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    budget_file = ROOT / "script" / "budgets.json"
    committed = json.loads(budget_file.read_text()) if budget_file.exists() else {}
    files = {}
    tally = defaultdict(lambda: {"lines": 0, "done": 0, "human": 0, "ignore": 0})
    budgets = {}

    for path in sorted((ROOT / "script").glob("*.tsv")):
        if path.name in EXCLUDE:
            continue
        codec = CODECS.get(path.name, textcodec)
        blocks = defaultdict(list)
        block_entries = defaultdict(list)
        for r in tsv.read(path):
            bo, en, st = r["block_off"], r["english"].strip(), r["status"].strip()
            raw = bytes.fromhex(r["raw_hex"])
            line = {"id": r["str_off"], "sp": r["speaker"], "jp": r["text"], "en": en}
            if st:
                line["st"] = st
            # Control-only rows (terminator/padding or no displayable glyphs)
            # have nothing to translate.
            structural = raw == b"\x00" or not has_text(codec, raw)
            if structural:
                line["x"] = 1                # dimmed on the site, excluded from all counts
            blocks[bo].append(line)
            block_entries[bo].append((en, raw))
            if not structural:
                t = tally[path.name]
                t["lines"] += 1
                if en:
                    t["done"] += 1
                if st == "human":
                    t["human"] += 1
                elif st == "ignore":
                    t["ignore"] += 1
        files[path.name] = dict(blocks)
        for bo, entries in block_entries.items():
            key = f"{path.name}:{bo}"
            budgets[key] = {"used": block_used(codec, entries),
                            "limit": committed.get(key, PAGE)}

    (OUT / "script.json").write_text(
        json.dumps(files, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # render.json: precomputed in-game line layout for the dialogue preview (cutscene lines only,
    # via the shared engine width model in alshark.render). The site preview fetches this.
    import export_render_model
    from alshark import render as _render
    rlines, _, _ = export_render_model.build(str(ROOT / "script" / "cutscene.tsv"))
    (OUT / "render.json").write_text(
        json.dumps({"meta": _render.model_meta(), "lines": rlines},
                   ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    total = sum(t["lines"] for t in tally.values())
    done = sum(t["done"] for t in tally.values())
    human = sum(t["human"] for t in tally.values())
    ignore = sum(t["ignore"] for t in tally.values())
    (OUT / "status.json").write_text(json.dumps({
        "total": total, "done": done, "human": human, "ignore": ignore,
        "files": dict(tally), "budgets": budgets,
        "speakers": {}, "tokens": {}, "names": [],
    }, ensure_ascii=False), encoding="utf-8")

    # suggestions.json (filled by the CI bot from open issues; empty otherwise)
    (OUT / "suggestions.json").write_text("{}", encoding="utf-8")

    print(f"site data: {total} lines ({done} translated), {len(budgets)} block budgets")


if __name__ == "__main__":
    main()
