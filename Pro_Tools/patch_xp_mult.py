#!/usr/bin/env python3
"""Patch the battle XP multiplier in DQMJ2P overlay 1.

The inner XP accumulation loop in overlay 1 (RAM 0x021e3c4c) is:
    ADD r4, r4, r0          ; r4 (running total) += r0 (per-enemy XP)

Multiplier is encoded as a left/right shift on r0 before the add:
    ADD r4, r4, r0, LSL #n  ; 2^n × XP  (n > 0)
    ADD r4, r4, r0           ;  1 × XP   (n = 0, original)
    ADD r4, r4, r0, LSR #n  ; 0.5^n × XP (n < 0)

The --mult value is rounded to the nearest supported power of 2.
Supported range: 0.0625× (1/16) through 256× (LSR 4 … LSL 8).

The overlay table (y9.bin) encodes the compressed file size in its flags
field and must be updated whenever the compressed size changes, otherwise
the game reads the wrong number of bytes from the ROM and crashes.

Usage:
    patch_xp_mult.py                         # 2× XP (default)
    patch_xp_mult.py --mult 4.0              # 4× XP
    patch_xp_mult.py --mult 0.5             # half XP
    patch_xp_mult.py --in  Pro_ROM/overlay_dir/overlay_0001.bin
    patch_xp_mult.py --y9  Pro_ROM/y9.bin    # default: sibling of --in dir
"""
import argparse, math, os, struct, subprocess, sys, tempfile
from pathlib import Path

# ── constants ────────────────────────────────────────────────────────────────

OVERLAY_ID       = 1
OVERLAY_RAM_BASE = 0x021d7240
PATCH_RAM        = 0x021e3c4c          # ADD r4, r4, r0
PATCH_FILE_OFF   = PATCH_RAM - OVERLAY_RAM_BASE   # 0xca0c in decompressed overlay
ORIG_INSTR       = 0xE0844000          # ADD r4, r4, r0 (shift = 0)
UPPER_HALF       = 0xE084              # cond + opcode + Rn=r4 — never changes

# y9.bin overlay table: 8 × u32 per entry, flags field is last (offset 28)
Y9_ENTRY_SIZE    = 32
Y9_FLAGS_OFF     = 28   # within each entry
# flags encoding: bits[23:0] = compressed file size, bits[31:24] = compress flag
Y9_COMPRESS_FLAG = 0x01 << 24

MIN_SHIFT = -4   # 0.0625× (LSR #4)
MAX_SHIFT =  8   # 256×    (LSL #8)

BLZ = str(Path(__file__).parent / 'blz.out')


# ── helpers ──────────────────────────────────────────────────────────────────

def mult_to_shift(mult: float) -> int:
    """Round multiplier to nearest power-of-2, return shift exponent n."""
    if mult <= 0:
        sys.exit(f'multiplier must be positive, got {mult}')
    n = round(math.log2(mult))
    return max(MIN_SHIFT, min(MAX_SHIFT, n))


def encode_instr(n: int) -> int:
    """Return the full 32-bit ARM instruction for ADD r4, r4, r0 shifted by n."""
    shift_amt  = abs(n)
    shift_type = 0b00 if n >= 0 else 0b01   # 00=LSL, 01=LSR
    operand12  = (shift_amt << 7) | (shift_type << 5)  # Rm = r0 = 0
    return (UPPER_HALF << 16) | 0x4000 | operand12     # 0x4000 = Rd = r4


def blz_decompress(src: Path) -> bytearray:
    """Return decompressed contents of a BLZ-compressed overlay."""
    with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as tf:
        tf.write(src.read_bytes())
        tmp = tf.name
    try:
        r = subprocess.run([BLZ, '-d', tmp], capture_output=True)
        if r.returncode not in (0, 1):
            sys.exit(f'blz -d failed:\n{r.stderr.decode()}')
        return bytearray(Path(tmp).read_bytes())
    finally:
        os.unlink(tmp)


def blz_compress(data: bytes) -> bytes:
    """Compress bytes with BLZ optimal encoding."""
    with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as tf:
        tf.write(data)
        tmp = tf.name
    try:
        r = subprocess.run([BLZ, '-eo', tmp], capture_output=True)
        if r.returncode not in (0, 1):
            sys.exit(f'blz -eo failed:\n{r.stderr.decode()}')
        return Path(tmp).read_bytes()
    finally:
        os.unlink(tmp)


def update_y9(y9_path: Path, overlay_id: int, new_compressed_size: int):
    """Update the flags field for overlay_id in y9.bin with the new size."""
    y9 = bytearray(y9_path.read_bytes())
    off = overlay_id * Y9_ENTRY_SIZE + Y9_FLAGS_OFF
    old_flags = struct.unpack_from('<I', y9, off)[0]
    old_size  = old_flags & 0xFFFFFF
    new_flags = Y9_COMPRESS_FLAG | (new_compressed_size & 0xFFFFFF)
    struct.pack_into('<I', y9, off, new_flags)
    y9_path.write_bytes(y9)
    print(f'updated y9.bin overlay {overlay_id} flags: '
          f'0x{old_flags:08x} (size 0x{old_size:x}) → '
          f'0x{new_flags:08x} (size 0x{new_compressed_size:x})')


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--mult', type=float, default=2.0,
                    help='XP multiplier (rounded to nearest power of 2, default 2.0)')
    ap.add_argument('--in', dest='inp',
                    default='Pro_ROM/overlay_dir/overlay_0001.bin',
                    help='input overlay file')
    ap.add_argument('--out', default=None,
                    help='output overlay file (default: overwrite --in)')
    ap.add_argument('--y9', default=None,
                    help='y9.bin path (default: ../y9.bin relative to overlay dir)')
    args = ap.parse_args()

    in_path  = Path(args.inp)
    out_path = Path(args.out) if args.out else in_path
    y9_path  = Path(args.y9) if args.y9 else in_path.parent.parent / 'y9.bin'

    if not in_path.exists():
        sys.exit(f'input not found: {in_path}')
    if not os.path.isfile(BLZ):
        sys.exit(f'blz binary not found at {BLZ}')
    if not y9_path.exists():
        sys.exit(f'y9.bin not found at {y9_path}  (use --y9 to specify)')

    n        = mult_to_shift(args.mult)
    actual   = 2.0 ** n
    new_inst = encode_instr(n)

    print(f'requested {args.mult}×  →  nearest supported: {actual}×  '
          f'({"LSL" if n >= 0 else "LSR"} #{abs(n)})')

    # Decompress
    orig_compressed_size = in_path.stat().st_size
    dec = blz_decompress(in_path)

    # Verify expected instruction is present
    cur = struct.unpack_from('<I', dec, PATCH_FILE_OFF)[0]
    if (cur & 0xFFFF0000) != (ORIG_INSTR & 0xFFFF0000):
        sys.exit(f'unexpected instruction at 0x{PATCH_RAM:08x}: '
                 f'0x{cur:08x}  (upper half should be 0x{ORIG_INSTR >> 16:04x})\n'
                 f'Wrong overlay, or previously patched with incompatible tool.')

    struct.pack_into('<I', dec, PATCH_FILE_OFF, new_inst)
    print(f'patched 0x{PATCH_RAM:08x}: 0x{cur:08x} → 0x{new_inst:08x}')

    # Recompress
    compressed = blz_compress(bytes(dec))
    out_path.write_bytes(compressed)
    print(f'wrote {out_path}  ({len(compressed):#x} bytes, '
          f'was {orig_compressed_size:#x})')

    # Update y9.bin so the game loads the right number of bytes
    if len(compressed) != orig_compressed_size:
        update_y9(y9_path, OVERLAY_ID, len(compressed))
    else:
        print('compressed size unchanged — y9.bin not modified')


if __name__ == '__main__':
    main()
