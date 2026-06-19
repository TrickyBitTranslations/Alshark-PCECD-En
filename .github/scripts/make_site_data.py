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


def block_used(codec, entries):
    """Rebuilt block size in bytes: pointer table + entry bytes."""
    total = 2 * len(entries)
    for en, raw in entries:
        total += len(codec.encode(en)) if en else len(raw)
    return total


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = {}
    tally = defaultdict(lambda: {"lines": 0, "done": 0, "human": 0, "ignore": 0})
    budgets = {}

    for path in sorted((ROOT / "script").glob("*.tsv")):
        codec = CODECS.get(path.name, textcodec)
        blocks = defaultdict(list)
        block_entries = defaultdict(list)
        for r in tsv.read(path):
            bo, en, st = r["block_off"], r["english"].strip(), r["status"].strip()
            line = {"id": r["str_off"], "sp": r["speaker"], "jp": r["text"], "en": en}
            if st:
                line["st"] = st
            blocks[bo].append(line)
            block_entries[bo].append((en, bytes.fromhex(r["raw_hex"])))
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
            budgets[f"{path.name}:{bo}"] = {"used": block_used(codec, entries), "limit": PAGE}

    (OUT / "script.json").write_text(
        json.dumps(files, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

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
