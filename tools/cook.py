"""Stage the cooked data track: CHD -> chdman extractcd -> CUE/BIN -> work/track02.iso.

Carves track 2's 2048-byte user data out of each 2352-byte Mode-1 sector. Bring your
own dump; override the default path with --chd.
"""
import argparse
import os
import subprocess
import struct

SEC = 2352
USER = 2048
DATA_OFF = 16

DEFAULT_CHD = "noredist/image/Alshark (Japan).chd"


def _msf_to_frames(msf):
    m, s, f = (int(x) for x in msf.split(':'))
    return (m * 60 + s) * 75 + f


def _track_indexes(cue_path):
    """Return {track_no: {index_no: start_frame}} from a cue sheet."""
    tracks = {}
    cur = None
    for line in open(cue_path):
        line = line.strip()
        if line.startswith('TRACK'):
            cur = int(line.split()[1])
            tracks[cur] = {}
        elif line.startswith('INDEX') and cur is not None:
            _, idx, msf = line.split()
            tracks[cur][int(idx)] = _msf_to_frames(msf)
    return tracks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--chd', default=DEFAULT_CHD)
    ap.add_argument('--extracted', default='extracted')
    ap.add_argument('--work', default='work')
    args = ap.parse_args()

    os.makedirs(args.extracted, exist_ok=True)
    os.makedirs(args.work, exist_ok=True)
    cue = os.path.join(args.extracted, 'Alshark.cue')
    binf = os.path.join(args.extracted, 'Alshark.bin')

    if not (os.path.exists(cue) and os.path.exists(binf)):
        print("extractcd:", args.chd)
        subprocess.run(['chdman', 'extractcd', '-i', args.chd,
                        '-o', cue, '-ob', binf, '-f'], check=True)

    tracks = _track_indexes(cue)
    start = tracks[2][1]                          # track 2 data starts at its INDEX 01
    end = tracks[3].get(0, tracks[3][1])          # ...and runs up to track 3's pregap (INDEX 00)
    nsec = end - start
    print(f"track2 start={start} end={end} ({nsec} sectors)")

    raw = open(binf, 'rb').read()
    out = bytearray()
    for s in range(start, start + nsec):
        b = s * SEC
        out += raw[b + DATA_OFF:b + DATA_OFF + USER]
    iso = os.path.join(args.work, 'track02.iso')
    open(iso, 'wb').write(out)
    print(f"wrote {iso}: {len(out)} bytes / {len(out) // USER} sectors")
    # cheap sanity: the opening greeting bytes should be where the notes say
    marker = bytes.fromhex('240081 41 b5cad6b3 8142'.replace(' ', ''))
    assert out[0x78508b:0x78508b + len(marker)] == marker, "cooked marker mismatch"
    print("marker check OK (@0x78508b = $<00>,ohayou.)")


if __name__ == '__main__':
    main()
