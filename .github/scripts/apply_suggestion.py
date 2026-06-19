"""Apply a validated translation suggestion to its TSV row (the /apply bot).

Reads the issue body from $ISSUE_BODY (same form as validate_suggestion.py) and
writes the proposed translation into the english column of the matching row,
marking it human-reviewed. Run validate_suggestion.py first; this only edits the
spreadsheet. Exits 1 if the row can't be found.
"""
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent  # repo root (.github/scripts/..)
sys.path.insert(0, str(ROOT / "tools"))
import tsv
from validate_suggestion import parse_form


def main():
    fields = parse_form(os.environ.get("ISSUE_BODY", ""))
    tsv_name = fields["script file"]
    block_s, str_s = fields["line id"].split()
    text = fields["proposed translation"].strip().replace("\r", "")

    path = ROOT / "script" / tsv_name
    rows = list(tsv.read(path))
    hit = False
    for r in rows:
        if r["block_off"] == block_s and r["str_off"] == str_s:
            r["english"] = text
            r["status"] = "human"      # an applied contributor suggestion is human-reviewed
            hit = True
    if not hit:
        print(f"row {block_s} {str_s} not found in {tsv_name}")
        sys.exit(1)
    tsv.write(path, rows)
    print(f"applied to {tsv_name} row {block_s} {str_s}")


if __name__ == "__main__":
    main()
