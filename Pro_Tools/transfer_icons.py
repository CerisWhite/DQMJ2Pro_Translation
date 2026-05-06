#!/usr/bin/env python3
"""Replace Pro_ROM's ♂/♀/⚥ font glyphs with J2's +/−/± circle icons.

The Pro NFTR has three gender-symbol glyphs at indices 594, 595, 596;
J2 has plus/minus/neutral circles at 553, 554, 555. Each glyph is a
96-byte 12×16 4bpp tile in the CGLP block. We overwrite Pro's three
tiles in place — CGLP block size, CWDH, CMAP, and the in-text token
routing for {231}/{232} all stay untouched, so the dialogue tokens
still fire but render the new pixels.

Pre-extracted source tiles live in icon_tiles/{plus,minus,neutral}.bin
(one 96-byte cell each, dumped from J2 glyphs 553/554/555).

Usage:  transplant_gender_icons.py [pro_font_path]
        default = ../Pro_ROM/data_dir/font_16x16.NFTR
"""
import struct, sys
from pathlib import Path

CELL_SIZE = 96     # 12×16 × 4bpp / 8
TARGET_INDICES = {            # Pro glyph index -> source tile filename
    594: 'plus.bin',
    595: 'minus.bin',
    596: 'neutral.bin',
}


def cglp_glyph_offsets(font_bytes):
    """Return (glyph_data_start_offset, n_glyphs) for the PLGC block."""
    i = font_bytes.find(b'PLGC')
    if i < 0:
        raise RuntimeError('PLGC block not found')
    blk_size = struct.unpack('<I', font_bytes[i+4:i+8])[0]
    cw       = font_bytes[i+8]
    ch       = font_bytes[i+9]
    cell_sz  = struct.unpack('<H', font_bytes[i+0xa:i+0xc])[0]
    if (cw, ch, cell_sz) != (12, 16, CELL_SIZE):
        raise RuntimeError(f'unexpected CGLP geometry cw={cw} ch={ch} cell={cell_sz}')
    glyph_data_off = i + 0x10
    n_glyphs = (blk_size - 0x10) // cell_sz
    return glyph_data_off, n_glyphs


def main():
    here     = Path(__file__).resolve().parent
    pro_path = Path(sys.argv[1]) if len(sys.argv) > 1 \
               else here.parent / 'Pro_ROM' / 'data_dir' / 'font_16x16.NFTR'
    tiles_dir = here / 'icon_tiles'

    src_tiles = {}
    for gi, fname in TARGET_INDICES.items():
        data = (tiles_dir / fname).read_bytes()
        if len(data) != CELL_SIZE:
            raise RuntimeError(f'{fname} is {len(data)} bytes, expected {CELL_SIZE}')
        src_tiles[gi] = data

    font = bytearray(pro_path.read_bytes())
    glyph_off, n_glyphs = cglp_glyph_offsets(font)
    for gi in TARGET_INDICES:
        if gi >= n_glyphs:
            raise RuntimeError(f'target glyph {gi} out of range (font has {n_glyphs})')

    for gi, tile in src_tiles.items():
        off = glyph_off + gi * CELL_SIZE
        font[off : off + CELL_SIZE] = tile
        print(f'  patched glyph {gi} @ 0x{off:x} ({TARGET_INDICES[gi]})')

    pro_path.write_bytes(bytes(font))
    print(f'wrote {pro_path}')


if __name__ == '__main__':
    main()
