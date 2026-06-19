"""CD-ROM Mode 1 EDC/ECC (Neill Corlett's algorithm, public domain), Python port.

Recomputes the per-sector error-detection/correction bytes after the 2048-byte
user data is edited. Validated byte-exact against the original sectors.
"""

EDC_TABLE = []
for _i in range(256):
    _edc = _i
    for _ in range(8):
        _edc = (_edc >> 1) ^ (0xD8018001 if (_edc & 1) else 0)
    EDC_TABLE.append(_edc & 0xFFFFFFFF)

ECC_F = [0] * 256
ECC_B = [0] * 256
for _i in range(256):
    _j = ((_i << 1) ^ (0x11D if (_i & 0x80) else 0)) & 0xFF
    ECC_F[_i] = _j
    ECC_B[(_i ^ _j) & 0xFF] = _i


def edc_compute(data):
    edc = 0
    for b in data:
        edc = (edc >> 8) ^ EDC_TABLE[(edc ^ b) & 0xFF]
    return edc & 0xFFFFFFFF


def _ecc_block(sector, major_count, minor_count, major_mult, minor_inc, dest_off):
    # sector is a mutable bytearray (full 2352); ecc source base = offset 0x0C
    size = major_count * minor_count
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        a = 0
        b = 0
        for _ in range(minor_count):
            t = sector[0x0C + index]
            index += minor_inc
            if index >= size:
                index -= size
            a ^= t
            b ^= t
            a = ECC_F[a]
        a = ECC_B[(ECC_F[a] ^ b) & 0xFF]
        sector[dest_off + major] = a & 0xFF
        sector[dest_off + major + major_count] = (a ^ b) & 0xFF


def fix_mode1(sector):
    """sector: bytearray length 2352 with header (0x0C..0x0F) set and user data filled.
    Rewrites EDC (0x810), the 8 zero bytes (0x814), and P/Q ECC parity in place."""
    edc = edc_compute(sector[0:0x810])
    sector[0x810] = edc & 0xFF
    sector[0x811] = (edc >> 8) & 0xFF
    sector[0x812] = (edc >> 16) & 0xFF
    sector[0x813] = (edc >> 24) & 0xFF
    for k in range(0x814, 0x81C):
        sector[k] = 0
    # P parity -> 0x81C ; Q parity -> 0x8C8  (note Q major_mult is 86, not 88)
    _ecc_block(sector, 86, 24, 2, 86, 0x81C)
    _ecc_block(sector, 52, 43, 86, 88, 0x8C8)
    return sector
