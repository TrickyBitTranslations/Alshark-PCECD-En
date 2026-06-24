#!/usr/bin/env python3
"""Build the Alshark English CD and publish an xdelta release patch.

The release ships an **xdelta patch** (only the changed bytes - NOT the game) plus our
.cue. Players bring their own JP Alshark CD (raw 2352-byte .bin matching the published
SHA-256), apply the patch, and play. No copyrighted data is distributed.

Usage:
  python rebuild/release.py --check                 # validate translations (no game data needed)
  python rebuild/release.py                          # build the EN CD (rebuild/build/Alshark.bin + .chd)
  python rebuild/release.py --release --tag v1.0     # build + make the xdelta + publish a GitHub release
  python rebuild/release.py --release --tag v1.0 --intro "First playable release!"
  python rebuild/release.py --release --tag v1.0 --intro-file notes/v1.0.md

Release notes are pulled from "Release-note:" trailers on commits since the previous tag,
so only commits that opt in show up - e.g. add to a commit message:
    Release-note: Battle menus and item names are now in English

Needs xdelta3 (sudo apt-get install -y xdelta3) and a logged-in gh for --release.
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))           # rebuild/
ROOT = os.path.dirname(HERE)                                # repo root
BUILD = os.path.join(HERE, 'build')
DIST = os.path.join(ROOT, 'dist')

JP_BIN = os.path.join(ROOT, 'extracted', 'Alshark.bin')     # JP source CD (raw 2352)
EN_BIN = os.path.join(BUILD, 'Alshark.bin')                 # built EN CD (raw 2352)
EN_CUE = os.path.join(BUILD, 'Alshark.cue')
PATCH = os.path.join(DIST, 'alshark-en.xdelta')
CUE_OUT = os.path.join(DIST, 'Alshark.cue')


def step(label):
    print('== %s' % label, flush=True)


def run(cmd, **kw):
    r = subprocess.run(cmd, **kw)
    if r.returncode != 0:
        print('FAILED: %s' % ' '.join(map(str, cmd)), file=sys.stderr)
        sys.exit(1)
    return r


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def release_notes(prev_range, intro_text):
    """Collect 'Release-note:' trailers in the commit range, dedup, prepend intro."""
    out = subprocess.run(['git', 'log', prev_range, '--format=%B'],
                         cwd=ROOT, capture_output=True, text=True).stdout
    seen, notes = set(), []
    for m in re.finditer(r'(?im)^\s*Release-note:\s*(.+?)\s*$', out):
        n = m.group(1).strip()
        if n and n not in seen:
            seen.add(n)
            notes.append('- ' + n)
    body = []
    if intro_text:
        body += [intro_text, '']
    if notes:
        body += ["## What's new", *notes, '']
    elif not intro_text:
        body += ["## What's new", '- (no Release-note: commits yet)', '']
    return body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='validate translations only')
    ap.add_argument('--release', action='store_true', help='make xdelta + publish a GitHub release')
    ap.add_argument('--tag', help='release tag, e.g. v1.0')
    ap.add_argument('--intro', help='text to put above the auto notes')
    ap.add_argument('--intro-file', help='file whose contents go above the auto notes')
    args = ap.parse_args()

    if args.check:
        step('check: validate translations (syntax, width, budgets)')
        env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, 'tools'))
        run([sys.executable, os.path.join(ROOT, 'tools', 'reinsert.py'), '--check'], cwd=ROOT, env=env)
        print('\nCHECK OK (nothing written).')
        return

    if not os.path.exists(JP_BIN) or os.path.getsize(JP_BIN) < (1 << 20):
        print('JP game data not found at %s' % JP_BIN, file=sys.stderr)
        print('Building needs the original disc in extracted/ (see README).', file=sys.stderr)
        print('Validation works without it:  python rebuild/release.py --check', file=sys.stderr)
        sys.exit(1)

    step('build EN CD (rebuild/build/Alshark.bin + .cue + .chd)')
    run([sys.executable, os.path.join(HERE, 'build.py'), '--chd'], cwd=ROOT)
    print('\nBUILD OK.')
    print('  CD:  %s (+ .cue)' % EN_BIN)
    print('  CHD: %s' % os.path.join(BUILD, 'Alshark (rebuild).chd'))

    if not args.release:
        return

    # --- release: xdelta patch + GitHub release ---
    if not args.tag:
        print('Release needs a tag:  python rebuild/release.py --release --tag v1.0', file=sys.stderr)
        sys.exit(1)
    for t in ('xdelta3', 'gh'):
        if not shutil.which(t):
            print('%s not found (xdelta3: sudo apt-get install -y xdelta3).' % t, file=sys.stderr)
            sys.exit(1)
    if subprocess.run(['gh', 'auth', 'status'], capture_output=True).returncode != 0:
        print("gh isn't logged in. Run: gh auth login   (or set GH_TOKEN)", file=sys.stderr)
        sys.exit(1)

    os.makedirs(DIST, exist_ok=True)
    # the patch carries only the changed bytes, not the game - safe to publish
    step('patch: xdelta3 JP -> EN delta')
    run(['xdelta3', '-e', '-f', '-s', JP_BIN, EN_BIN, PATCH])
    shutil.copyfile(EN_CUE, CUE_OUT)            # our cue (FILE "Alshark.bin"), not game data
    jp_hash = sha256(JP_BIN)
    print('  patch: %s (%d bytes)' % (PATCH, os.path.getsize(PATCH)))

    intro_text = args.intro or ''
    if args.intro_file:
        intro_text = ((intro_text + '\n\n') if intro_text else '') + \
            open(args.intro_file, encoding='utf-8').read().rstrip()

    subprocess.run(['git', 'fetch', '--tags', '--quiet'], cwd=ROOT)
    prev = subprocess.run(['git', 'describe', '--tags', '--abbrev=0'],
                          cwd=ROOT, capture_output=True, text=True).stdout.strip()
    rng = ('%s..HEAD' % prev) if prev else 'HEAD'
    body = release_notes(rng, intro_text)
    body += [
        '## Install',
        'Bring your own copy of the JP Alshark CD, then apply the patch with an xdelta tool '
        '(xdelta3, or a GUI like Delta Patcher):',
        '1. Apply `alshark-en.xdelta` to your JP CD track image (the raw 2352-byte .bin, SHA-256 below).',
        '2. Name the patched result `Alshark.bin` and put `Alshark.cue` (included) beside it.',
        '3. Load `Alshark.cue` in a PC Engine CD emulator, or convert to .chd with '
        '`chdman createcd -i Alshark.cue -o Alshark.chd`.',
        '',
        '## The patch applies to this JP file (SHA-256)',
        'Alshark.bin  -  %s' % jp_hash,
    ]
    notes_file = os.path.join(DIST, 'notes.md')
    open(notes_file, 'w', encoding='utf-8').write('\n'.join(body) + '\n')

    step('publish: gh release %s' % args.tag)
    run(['gh', 'release', 'create', args.tag, PATCH, CUE_OUT,
         '--title', args.tag, '--notes-file', notes_file], cwd=ROOT)
    print('\nRELEASED %s' % args.tag)
    print('  notes from Release-note: trailers (%s)' % rng)


if __name__ == '__main__':
    main()
