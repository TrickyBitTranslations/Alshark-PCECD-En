"""Shared TSV read/write for the translation surfaces.

Each script/*.tsv is a header row then tab-separated columns:
  block_off  str_off  speaker  text  raw_hex  english  status
Rows are kept in file order (== the block's entry order, which reinsert relies on).
"""
import pathlib

COLUMNS = ['block_off', 'str_off', 'speaker', 'text', 'raw_hex', 'english', 'status']


def read(path):
    """Yield dict rows (header skipped, blanks skipped) in file order."""
    lines = pathlib.Path(path).read_text(encoding='utf-8').splitlines()
    cols = lines[0].split('\t')
    for line in lines[1:]:
        if line:
            yield dict(zip(cols, line.split('\t')))


def write(path, rows, columns=COLUMNS):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\t'.join(columns) + '\n')
        for r in rows:
            f.write('\t'.join(str(r.get(c, '')) for c in columns) + '\n')
