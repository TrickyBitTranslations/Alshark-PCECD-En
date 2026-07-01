"""Validate a single translation suggestion (the issue-form bot).

Reads the issue body from $ISSUE_BODY (GitHub issue-form markdown), pulls out
file / line id / proposed translation, and checks: the codec can encode it, the
control codes from the original survive, and the block still fits its 8KB page
with the suggestion applied on top of the current TSV. Emits a markdown report to
stdout (posted as the issue comment); exits 0 (valid) / 1 (invalid).
"""
import os
import pathlib
import re
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent  # repo root (.github/scripts/..)
sys.path.insert(0, str(ROOT / "tools"))
import tsv
from alshark import textcodec, dialogcodec

PAGE = 0x2000
CODECS = {"cutscene.tsv": dialogcodec}


def parse_form(body):
    """{heading: value} from issue-form markdown (### Heading\\n\\nvalue)."""
    fields = {}
    for m in re.finditer(r"^### (.+?)\s*\n+(.*?)(?=\n### |\Z)", body, re.S | re.M):
        fields[m.group(1).strip().lower()] = m.group(2).strip()
    return fields


# <00> is the entry terminator, which reinsert adds automatically, so translators
# need not retype it. Every other <XX> carries game meaning and must be kept.
EXEMPT = {"<00>"}


def control_codes(s):
    """Multiset of the <XX> control codes in a line, minus the auto-added ones."""
    return Counter(t for t in re.findall(r"<[0-9a-fA-F]{2}>", s) if t not in EXEMPT)


def preview_link(tsv_name, block_s, str_s, text):
    """Link to the in-game dialogue preview of this exact suggestion (cutscene lines only). The
    site's render.js renders the proposed text (base64) against the line's raw bytes."""
    if tsv_name != "cutscene.tsv":
        return None
    import base64
    repo = os.environ.get("GITHUB_REPOSITORY", "TrickyBitTranslations/Alshark-PCECD-En")
    owner, name = repo.split("/", 1)
    en = base64.urlsafe_b64encode(text.encode("utf-8")).decode()
    return (f"https://{owner.lower()}.github.io/{name}/preview.html"
            f"?id={block_s}:{str_s}&en={en}")


def main():
    fields = parse_form(os.environ.get("ISSUE_BODY", ""))
    try:
        tsv_name = fields["script file"]
        block_s, str_s = fields["line id"].split()
        text = fields["proposed translation"].strip()
        assert text and text.lower() != "_no response_"
    except Exception:
        print("### :x: Could not parse the suggestion\n\nUse the form fields: "
              "script file, line id, and a non-empty proposed translation.")
        sys.exit(1)
    text = text.replace("\r", "")

    path = ROOT / "script" / tsv_name
    if not path.is_file():
        print(f"### :x: Unknown script file `{tsv_name}`\n\nPick the TSV the line "
              "lives in (the site fills this in for you).")
        sys.exit(1)

    codec = CODECS.get(tsv_name, textcodec)
    block_rows = [r for r in tsv.read(path) if r["block_off"] == block_s]
    target = next((r for r in block_rows if r["str_off"] == str_s), None)
    if target is None:
        print(f"### :x: line id `{block_s} {str_s}` not found in `{tsv_name}`")
        sys.exit(1)

    problems = []
    enc = b""
    try:
        enc = codec.encode(text)
    except Exception as e:
        problems.append(f"syntax: {e}")

    missing = control_codes(target["text"]) - control_codes(text)
    if missing:
        codes = ", ".join(f"`{c}`" + (f" x{n}" if n > 1 else "")
                          for c, n in sorted(missing.items()))
        problems.append(f"missing control codes from the original: {codes} "
                        "(copy them through unchanged)")

    used = 2 * len(block_rows)
    for r in block_rows:
        if r is target:
            used += len(enc)
        elif r["english"].strip():
            used += len(codec.encode(r["english"]))
        else:
            used += len(bytes.fromhex(r["raw_hex"]))
    if used > PAGE:
        problems.append(f"this scene would be {used} bytes, over the {PAGE} cap "
                        "(shorten this line or another in the scene)")

    if problems:
        print("### :x: Suggestion has problems\n")
        for p in problems:
            print(f"- {p}")
        print(f"\n**Original:** {target['text']}")
        link = preview_link(tsv_name, block_s, str_s, text)
        if link:
            print(f"\n[▶ Preview how it renders](%s) (a full line-gauge turns red)" % link)
        print("\nSee CONTRIBUTING.md for the markup and length rules. "
              "Edit the issue to re-run validation.")
        sys.exit(1)

    print("### :white_check_mark: Suggestion is valid\n")
    print(f"`{tsv_name}` block `{block_s}` line `{str_s}`:\n\n```\n{text}\n```")
    print(f"\n**Original:** {target['text']}")
    link = preview_link(tsv_name, block_s, str_s, text)
    if link:
        print(f"\n[▶ Preview how it renders in the game box]({link})")
    print("\nA maintainer can apply it with a `/apply` comment.")


if __name__ == "__main__":
    main()
