#!/usr/bin/env python3
"""Patch overlay_0001 so translated msg_actionhelp loads without a size limit.

The original load path (fcn.0205da98) copies the decoded text into a fixed
0x3000-byte BSS buffer and refuses payloads larger than that cap.  Translated
English text (~14 KB) exceeds it, so the load silently fails and no help text
appears in battle.

overlay_0000 uses fcn.0205d9e8 for the same file — no BSS copy, no size cap,
identical pointer-table output.  This patch redirects overlay_0001's call site
to use fcn.0205d9e8 instead (nine instruction changes + one literal-pool fix).

The overlay table (y9.bin) encodes the compressed file size in its flags field
and must be updated whenever the compressed size changes, otherwise the game
reads the wrong number of bytes from the ROM and crashes.

Usage:
    patch_actionhelp_cap.py                        # default paths, in-place
    patch_actionhelp_cap.py --in  Pro_ROM/overlay_dir/overlay_0001.bin
    patch_actionhelp_cap.py --out /tmp/overlay_0001_patched.bin
    patch_actionhelp_cap.py --y9  Pro_ROM/y9.bin   # default: sibling of --in dir
"""
import argparse, os, struct, subprocess, sys, tempfile
from pathlib import Path

# ── constants ────────────────────────────────────────────────────────────────

OVERLAY_ID       = 1
OVERLAY_RAM_BASE = 0x021d7240

# Redirect msg_actionhelp load from fcn.0205da98 (BSS-copy + size cap)
# to fcn.0205d9e8 (pool-0 direct, no cap) — same target used by overlay_0000.
_FCN_D9E8 = 0x0205d9e8
_BL_SRC   = 0x02202b68    # RAM address of the BL instruction in the overlay

# Decompressed-file offsets and (expected_old, new) instruction words.
# The BL entry (index 8) has old=None because any BL is acceptable there.
OV_PATCHES = [
    (0x2B908, 0xE59F0028, 0xE59F202C),  # LDR r0,… → LDR r2,[PC,#0x2C]  (ptr-table)
    (0x2B90C, 0xE3A0C002, 0xE59F3024),  # MOV r12,#2 → LDR r3,[PC,#0x24] (count-table)
    (0x2B910, 0xE88D1001, 0xE28D100C),  # STMIA SP,… → ADD r1,SP,#0xC
    (0x2B914, 0xE59F0020, 0xE3A00001),  # LDR r0,… → MOV r0,#1
    (0x2B918, 0xE59F3020, 0xE3A0C002),  # LDR r3,… → MOV r12,#2
    (0x2B91C, 0xE28D200C, 0xE58DC000),  # ADD r2,SP,… → STR r12,[SP]
    (0x2B920, 0xE3A01A03, 0xE1A00000),  # MOV r1,#0x3000 → NOP
    (0x2B924, 0xE58DC008, 0xE1A00000),  # STR r12,[SP+8] → NOP
    (0x2B928, None,       None),         # BL: filled in dynamically
    (0x2B93C, 0x0223A8EC, 0x020DB220),  # pool: BSS dest → ptr-table address
]

# y9.bin overlay table
Y9_ENTRY_SIZE    = 32
Y9_FLAGS_OFF     = 28
Y9_COMPRESS_FLAG = 0x01 << 24

BLZ = str(Path(__file__).parent / 'blz.out')


# ── helpers ──────────────────────────────────────────────────────────────────

def _bl_encode(src_ram: int, tgt_ram: int) -> int:
    pc = src_ram + 8
    offset24 = ((tgt_ram - pc) // 4) & 0xFFFFFF
    return 0xEB000000 | offset24


def blz_decompress(data: bytes) -> bytearray:
    with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as tf:
        tf.write(data); tmp = tf.name
    try:
        r = subprocess.run([BLZ, '-d', tmp], capture_output=True)
        if r.returncode not in (0, 1):
            sys.exit(f'blz -d failed:\n{r.stderr.decode()}')
        return bytearray(Path(tmp).read_bytes())
    finally:
        os.unlink(tmp)


def blz_compress(data: bytes) -> bytes:
    with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as tf:
        tf.write(data); tmp = tf.name
    try:
        r = subprocess.run([BLZ, '-eo', tmp], capture_output=True)
        if r.returncode not in (0, 1):
            sys.exit(f'blz -eo failed:\n{r.stderr.decode()}')
        return Path(tmp).read_bytes()
    finally:
        os.unlink(tmp)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
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

    orig_size = in_path.stat().st_size
    dec = blz_decompress(in_path.read_bytes())

    bl_new = _bl_encode(_BL_SRC, _FCN_D9E8)
    patches = list(OV_PATCHES)
    patches[8] = (0x2B928, None, bl_new)

    changed = False
    for off, old, new in patches:
        cur = struct.unpack_from('<I', dec, off)[0]
        if cur == new:
            continue
        if old is not None and cur != old:
            sys.exit(f'unexpected value 0x{cur:08x} at dec+0x{off:x} '
                     f'(expected 0x{old:08x}) — wrong overlay or already patched '
                     f'with an incompatible tool')
        struct.pack_into('<I', dec, off, new)
        old_str = f'0x{old:08x}' if old is not None else '(any BL)'
        print(f'patched dec+0x{off:x}: {old_str} → 0x{new:08x}')
        changed = True

    if not changed:
        print('already patched — nothing to do')
        return

    compressed = blz_compress(bytes(dec))
    out_path.write_bytes(compressed)
    print(f'wrote {out_path}  ({len(compressed):#x} bytes, was {orig_size:#x})')

    if len(compressed) != orig_size:
        y9 = bytearray(y9_path.read_bytes())
        off = OVERLAY_ID * Y9_ENTRY_SIZE + Y9_FLAGS_OFF
        old_flags = struct.unpack_from('<I', y9, off)[0]
        new_flags = Y9_COMPRESS_FLAG | (len(compressed) & 0xFFFFFF)
        struct.pack_into('<I', y9, off, new_flags)
        y9_path.write_bytes(y9)
        print(f'updated y9.bin overlay {OVERLAY_ID} flags: '
              f'0x{old_flags:08x} → 0x{new_flags:08x}')
    else:
        print('compressed size unchanged — y9.bin not modified')


if __name__ == '__main__':
    main()
