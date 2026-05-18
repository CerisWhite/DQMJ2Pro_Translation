#!/usr/bin/env python3
"""Interactive patcher for DQMJ2P Pro ROM.

Applies mandatory translation-required patches (grow_*) and any optional
gameplay patches you select from a menu.

Usage:
    apply_patches.py
    apply_patches.py --rom Pro_ROM
"""
import argparse, curses, math, os, struct, subprocess, sys, tempfile
from pathlib import Path

BLZ = str(Path(__file__).parent / 'blz.out')

ARM9_BASE        = 0x02000000
ARM9_PLAINTEXT   = 0x4000
ARM9_MODPARAMS   = 0xb68
ARM9_COMPEND_OFF = 0x14
NITRO_TRAILER    = bytes.fromhex('2106c0de680b000000000000')

Y9_ENTRY_SIZE    = 32
Y9_FLAGS_OFF     = 28
Y9_COMPRESS_FLAG = 0x01 << 24

OV_RAM_BASE = 0x021d7240


# ── BLZ helpers ───────────────────────────────────────────────────────────────

def _blz_run(args_extra: list, data: bytes) -> bytes:
    with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as tf:
        tf.write(data); tmp = tf.name
    try:
        r = subprocess.run([BLZ] + args_extra + [tmp], capture_output=True)
        if r.returncode not in (0, 1):
            sys.exit(f'blz {args_extra} failed:\n{r.stderr.decode()}')
        return Path(tmp).read_bytes()
    finally:
        os.unlink(tmp)


def overlay_decompress(path: Path) -> bytearray:
    return bytearray(_blz_run(['-d'], path.read_bytes()))


def overlay_compress(dec: bytes) -> bytes:
    return _blz_run(['-eo'], dec)


def arm9_decompress(path: Path) -> bytearray:
    raw = path.read_bytes()
    if not raw.endswith(NITRO_TRAILER):
        sys.exit(f'{path}: missing Nitro trailer — not a compressed arm9.bin')
    return bytearray(_blz_run(['-d'], raw[:-len(NITRO_TRAILER)]))


def arm9_compress(dec: bytearray) -> bytes:
    prefix    = bytearray(dec[:ARM9_PLAINTEXT])
    comp_body = _blz_run(['-eo'], bytes(dec[ARM9_PLAINTEXT:]))
    new_end   = ARM9_BASE + ARM9_PLAINTEXT + len(comp_body)
    struct.pack_into('<I', prefix, ARM9_MODPARAMS + ARM9_COMPEND_OFF, new_end)
    return bytes(prefix) + comp_body + NITRO_TRAILER


def update_y9(y9_path: Path, overlay_id: int, new_size: int):
    y9 = bytearray(y9_path.read_bytes())
    off = overlay_id * Y9_ENTRY_SIZE + Y9_FLAGS_OFF
    old_flags = struct.unpack_from('<I', y9, off)[0]
    new_flags = Y9_COMPRESS_FLAG | (new_size & 0xFFFFFF)
    struct.pack_into('<I', y9, off, new_flags)
    y9_path.write_bytes(y9)
    print(f'  y9.bin overlay {overlay_id}: flags 0x{old_flags:08x} → 0x{new_flags:08x} '
          f'(size 0x{new_size:x})')


# ── patch logic (each mutates dec in-place, no mismatch exits) ────────────────

def _encode_mov_imm(rd, value):
    for rot in range(16):
        v = ((value << (2*rot)) | (value >> (32 - 2*rot))) & 0xFFFFFFFF if rot else value
        if v <= 0xFF:
            return 0xE3A00000 | (rd << 12) | (rot << 8) | v
    raise ValueError(f'0x{value:x} not encodable as ARM rotated imm8')


def _bl_encode(src_ram: int, tgt_ram: int) -> int:
    return 0xEB000000 | (((tgt_ram - src_ram - 8) // 4) & 0xFFFFFF)


def apply_grow_msg_pool(dec: bytearray, pool_size: int):
    off = 0x02026EC8 - ARM9_BASE
    new_inst = _encode_mov_imm(1, pool_size)
    cur = struct.unpack_from('<I', dec, off)[0]
    struct.pack_into('<I', dec, off, new_inst)
    print(f'  grow_msg_pool: 0x02026EC8: 0x{cur:08x} → 0x{new_inst:08x}  '
          f'(pool 0 size → 0x{pool_size:x})')


def apply_grow_actionhelp(dec: bytearray):
    bl_new = _bl_encode(0x02202b68, 0x0205d9e8)
    for off, new in [
        (0x2B908, 0xE59F202C), (0x2B90C, 0xE59F3024),
        (0x2B910, 0xE28D100C), (0x2B914, 0xE3A00001),
        (0x2B918, 0xE3A0C002), (0x2B91C, 0xE58DC000),
        (0x2B920, 0xE1A00000), (0x2B924, 0xE1A00000),
        (0x2B928, bl_new),     (0x2B93C, 0x020DB220),
    ]:
        cur = struct.unpack_from('<I', dec, off)[0]
        struct.pack_into('<I', dec, off, new)
        print(f'  grow_actionhelp: dec+0x{off:x}: 0x{cur:08x} → 0x{new:08x}')


def apply_xp_mult(dec: bytearray, mult: float):
    off = 0x021e3c4c - OV_RAM_BASE
    n = max(-4, min(8, round(math.log2(max(mult, 1e-9)))))
    operand12 = (abs(n) << 7) | ((0 if n >= 0 else 1) << 5)
    new_inst  = (0xE084 << 16) | 0x4000 | operand12
    cur = struct.unpack_from('<I', dec, off)[0]
    struct.pack_into('<I', dec, off, new_inst)
    print(f'  xp_mult: {mult}× → nearest {2.0**n}× '
          f'({"LSL" if n >= 0 else "LSR"} #{abs(n)}): '
          f'0x{cur:08x} → 0x{new_inst:08x}')


def apply_xvariant_suffix(dec: bytearray):
    off = 0x02045028 - ARM9_BASE
    cur = struct.unpack_from('<I', dec, off)[0]
    struct.pack_into('<I', dec, off, 0xEAFFFFFF)
    print(f'  xvariant branch: 0x{cur:08x} → 0xEAFFFFFF')
    off = 0x0204502c - ARM9_BASE
    for i, w in enumerate([
        0xE1A02006, 0xE3A00002, 0xE3A01000, 0xEB00630C,
        0xE1A01000, 0xE1A00004, 0xEB00631C,
        0xE3550000, 0x0A000009,
        0xE1A00006, 0xEBFFFF4A, 0xE0850000, 0xE1A02000,
        0xE3A00002, 0xE3A01001, 0xEB006300,
        0xE1A01000, 0xE1A00004, 0xEB006320,
    ]):
        struct.pack_into('<I', dec, off + i*4, w)
    print(f'  xvariant block: 19 instructions rewritten at 0x0204502c')
    for off, new in [
        (0x0203507C - ARM9_BASE, 0xE1D510F6),
        (0x02035080 - ARM9_BASE, 0xE1D520F4),
        (0x020350A8 - ARM9_BASE, 0xE1D510FE),
        (0x020350AC - ARM9_BASE, 0xE1D520FC),
    ]:
        cur = struct.unpack_from('<I', dec, off)[0]
        struct.pack_into('<I', dec, off, new)
        print(f'  xvariant synth: 0x{ARM9_BASE+off:08x}: 0x{cur:08x} → 0x{new:08x}')


def apply_gender_icons(nftr_path: Path):
    CELL = 96
    tiles_dir = Path(__file__).resolve().parent / 'icon_tiles'
    targets = {594: 'plus.bin', 595: 'minus.bin', 596: 'neutral.bin'}
    tiles = {}
    for gi, fname in targets.items():
        p = tiles_dir / fname
        if not p.exists():
            print(f'  WARNING: {p} not found — skipping gender icons'); return
        d = p.read_bytes()
        if len(d) != CELL:
            print(f'  WARNING: {fname} wrong size — skipping gender icons'); return
        tiles[gi] = d
    font = bytearray(nftr_path.read_bytes())
    i = font.find(b'PLGC')
    if i < 0:
        print('  WARNING: PLGC block not found — skipping gender icons'); return
    base = i + 0x10
    for gi, tile in tiles.items():
        off = base + gi * CELL
        font[off:off + CELL] = tile
        print(f'  gender_icons: glyph {gi} @ 0x{off:x} ← {targets[gi]}')
    nftr_path.write_bytes(bytes(font))
    print(f'  gender_icons: wrote {nftr_path}')


def apply_scout_offense(dec: bytearray):
    off = 0x021fbae8 - OV_RAM_BASE
    cur = struct.unpack_from('<I', dec, off)[0]
    struct.pack_into('<I', dec, off, 0xE1A00000)
    print(f'  scout_offense: 0x021fbae8: 0x{cur:08x} → 0xE1A00000 (NOP)')


def apply_scout_penalty(dec: bytearray):
    off = 0x021fa3f8 - OV_RAM_BASE   # ADD r1,r1,#1 → MOV r1,#1 (divisor always 1)
    cur = struct.unpack_from('<I', dec, off)[0]
    struct.pack_into('<I', dec, off, 0xE3A01001)
    print(f'  scout_penalty: 0x021fa3f8: 0x{cur:08x} → 0xE3A01001 (MOV r1,#1)')


def apply_synthesis_level(dec: bytearray, level: int):
    for off in (0x048B4C, 0x0494E4, 0x0494EC, 0x049A18):
        cur = struct.unpack_from('<I', dec, off)[0]
        new = (cur & 0xFFFFFF00) | (level & 0xFF)
        struct.pack_into('<I', dec, off, new)
        print(f'  synthesis_level: file+0x{off:x}: 0x{cur:08x} → 0x{new:08x}')


def apply_synthesis_polarity(dec: bytearray):
    for off, new in [
        (0x0484DC, 0xE3A00002), (0x0484F0, 0xE3A00002),
        (0x0485C4, 0xE3A00002), (0x0485D8, 0xE3A00002),
        (0x048B54, 0xE3A00002), (0x049484, 0xE3A00002),
        (0x049498, 0xE3A00000), (0x048530, 0xE3A00000),
        (0x048B74, 0xE3A00000), (0x04860C, 0xE3A00000),
        (0x049A2C, 0xE3A01001), (0x0494F4, 0xE3A01001),
    ]:
        cur = struct.unpack_from('<I', dec, off)[0]
        struct.pack_into('<I', dec, off, new)
        print(f'  synthesis_polarity: file+0x{off:x}: 0x{cur:08x} → 0x{new:08x}')


# ── patch definitions ─────────────────────────────────────────────────────────

def _parse_hex_int(s): return int(s, 0)

PATCHES = [
    dict(key='grow_msg_pool',      label='msg Pool Size Fix',
         required=True,  target='arm9',
         param=dict(default=0x35000, fmt=hex, parse=_parse_hex_int,
                    validate=lambda v: v > 0 and v % 0x1000 == 0,
                    validate_msg='must be a positive multiple of 0x1000')),

    dict(key='grow_actionhelp',    label='actionhelp Message Fix',
         required=True,  target='ov0001', param=None),

    dict(key='xp_mult',            label='Set XP Multiplier',
         required=False, target='ov0001',
         param=dict(default=2.0, fmt=str, parse=float,
                    validate=lambda v: 0.0625 <= v <= 256.0,
                    validate_msg='must be between 0.0625 and 256.0')),

    dict(key='xvariant_suffix',    label='Apply X/XY Variant Suffix Fix',
         required=False, target='arm9',   param=None),

    dict(key='gender_icons',       label='Replace Gender Icons with Polarity',
         required=False, target='nftr',   param=None),

    dict(key='scout_offense',      label='Make "Took offense" NOT Disable Scouting',
         required=False, target='ov0001', param=None),

    dict(key='scout_penalty',      label='Remove Multiple Species Owned Check From Scouting',
         required=False, target='ov0001', param=None),

    dict(key='synthesis_level',    label='Set Minimum Synthesis Level',
         required=False, target='ov0000',
         param=dict(default=10, fmt=str, parse=int,
                    validate=lambda v: 1 <= v <= 99,
                    validate_msg='must be between 1 and 99')),

    dict(key='synthesis_polarity', label='Remove Synthesis Polarity Requirement',
         required=False, target='ov0000', param=None),
]


# ── curses menu ───────────────────────────────────────────────────────────────

def _readline(stdscr, y, x, width, initial='') -> str | None:
    """Minimal line editor inside a curses window. ESC cancels (returns None)."""
    buf = list(initial)
    pos = len(buf)
    curses.curs_set(1)
    while True:
        visible = ''.join(buf)
        stdscr.addstr(y, x, visible[:width].ljust(width))
        stdscr.move(y, x + min(pos, width - 1))
        stdscr.refresh()
        ch = stdscr.getch()
        if ch in (curses.KEY_ENTER, 10, 13):
            curses.curs_set(0)
            return ''.join(buf)
        if ch == 27:                          # ESC — cancel
            curses.curs_set(0)
            return None
        if ch in (curses.KEY_BACKSPACE, 127, 8):
            if pos > 0:
                buf.pop(pos - 1); pos -= 1
        elif ch == curses.KEY_DC:
            if pos < len(buf): buf.pop(pos)
        elif ch == curses.KEY_LEFT:
            pos = max(0, pos - 1)
        elif ch == curses.KEY_RIGHT:
            pos = min(len(buf), pos + 1)
        elif ch == curses.KEY_HOME:
            pos = 0
        elif ch == curses.KEY_END:
            pos = len(buf)
        elif 32 <= ch <= 126:
            buf.insert(pos, chr(ch)); pos += 1


def _edit_value(stdscr, h, p, current):
    """Prompt for a new param value at the bottom of the screen.
    Returns new value, or current if cancelled/blank."""
    pd = p['param']
    prompt = f' {p["label"]}: '
    stdscr.addstr(h - 2, 0, prompt, curses.A_BOLD)
    stdscr.clrtoeol()
    stdscr.addstr(h - 1, 0, ' Enter confirm  Esc cancel', curses.A_DIM)
    stdscr.clrtoeol()

    raw = _readline(stdscr, h - 2, len(prompt), stdscr.getmaxyx()[1] - len(prompt) - 1,
                    initial=pd['fmt'](current))
    if raw is None or raw.strip() == '':
        return current
    try:
        v = pd['parse'](raw.strip())
    except (ValueError, OverflowError):
        stdscr.addstr(h - 2, 0, ' Invalid value — press any key', curses.A_BOLD)
        stdscr.clrtoeol(); stdscr.getch()
        return current
    if not pd['validate'](v):
        stdscr.addstr(h - 2, 0, f' {pd["validate_msg"]} — press any key', curses.A_BOLD)
        stdscr.clrtoeol(); stdscr.getch()
        return current
    return v


def _run_curses_menu(stdscr, state: dict) -> dict:
    curses.curs_set(0)
    curses.use_default_colors()
    curses.init_pair(1, -1, -1)                           # normal
    curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE)  # highlight

    cursor = 0
    status = ''

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()

        stdscr.addstr(0, 0, 'DQMJ2P Pro ROM Patcher — patch selection', curses.A_BOLD)
        stdscr.addstr(1, 0, '─' * min(w - 1, 50))

        for i, p in enumerate(PATCHES):
            s = state[p['key']]
            y = i + 3
            if y >= h - 3:
                break

            mark  = '*' if s['selected'] else ' '
            vstr  = (': ' + p['param']['fmt'](s['value'])) if p['param'] else ''
            line  = f'  [{mark}] {p["label"]}{vstr}'
            line  = line[:w - 1]

            attr = curses.color_pair(2) if i == cursor else curses.color_pair(1)
            if p['required'] and i != cursor:
                attr |= curses.A_DIM
            stdscr.addstr(y, 0, line.ljust(w - 1) if i == cursor else line, attr)

        if status:
            stdscr.addstr(h - 2, 0, f' {status}', curses.A_BOLD)
        stdscr.addstr(h - 1, 0,
                      ' ↑↓ move   Space toggle   Enter edit value   A apply   Q quit',
                      curses.A_DIM)
        stdscr.refresh()
        status = ''

        key = stdscr.getch()

        if key in (curses.KEY_UP, ord('k')):
            cursor = (cursor - 1) % len(PATCHES)

        elif key in (curses.KEY_DOWN, ord('j')):
            cursor = (cursor + 1) % len(PATCHES)

        elif key == ord(' '):
            p = PATCHES[cursor]
            s = state[p['key']]
            if p['required']:
                status = f'{p["label"]} is required and cannot be disabled.'
            else:
                s['selected'] = not s['selected']

        elif key in (curses.KEY_ENTER, 10, 13):
            p = PATCHES[cursor]
            s = state[p['key']]
            if p['param']:
                s['value'] = _edit_value(stdscr, h, p, s['value'])
                if not p['required']:
                    s['selected'] = True
            elif not p['required']:
                s['selected'] = not s['selected']
            else:
                status = f'{p["label"]} is required and cannot be disabled.'

        elif key in (ord('a'), ord('A')):
            break

        elif key in (ord('q'), ord('Q'), 27):
            curses.endwin()
            sys.exit('Aborted.')

    return state


def run_menu() -> dict:
    state = {p['key']: {'selected': p['required'],
                         'value':    p['param']['default'] if p['param'] else None}
             for p in PATCHES}
    curses.wrapper(_run_curses_menu, state)
    return state


# ── file discovery ────────────────────────────────────────────────────────────

def find_rom(rom_dir: Path) -> dict:
    candidates = {
        'arm9':   rom_dir / 'arm9.bin',
        'ov0000': rom_dir / 'overlay_dir' / 'overlay_0000.bin',
        'ov0001': rom_dir / 'overlay_dir' / 'overlay_0001.bin',
        'y9':     rom_dir / 'y9.bin',
        'nftr':   rom_dir / 'data_dir' / 'font_16x16.NFTR',
    }
    found, missing = {}, []
    for key, path in candidates.items():
        if path.exists():
            found[key] = path
        else:
            missing.append(str(path))
    if missing:
        print('Warning: files not found:')
        for m in missing: print(f'  {m}')
    return found


def _input_path(prompt: str, default: str = '') -> Path:
    raw = input(prompt).strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
        raw = raw[1:-1]
    return Path(raw if raw else default)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', default=None,
                    help='ROM directory (default: prompted interactively)')
    args = ap.parse_args()

    if not os.path.isfile(BLZ):
        sys.exit(f'blz binary not found at {BLZ}')

    if args.rom:
        rom_dir = Path(args.rom)
    else:
        rom_dir = _input_path('Enter ROM directory [default: Pro_ROM]: ', default='Pro_ROM')
    if not rom_dir.is_dir():
        sys.exit(f'directory not found: {rom_dir}')
    files = find_rom(rom_dir)

    state = run_menu()

    def sel(key): return state[key]['selected']
    def val(key): return state[key]['value']

    print()
    print('Applying patches...')
    print()

    # ── arm9 ──────────────────────────────────────────────────────────────────
    if 'arm9' in files:
        print('arm9.bin:')
        arm9_path = files['arm9']
        dec = arm9_decompress(arm9_path)
        apply_grow_msg_pool(dec, val('grow_msg_pool'))
        if sel('xvariant_suffix'):
            apply_xvariant_suffix(dec)
        final = arm9_compress(dec)
        arm9_path.write_bytes(final)
        print(f'  wrote {arm9_path} ({len(final):#x} bytes)')
        print()
    else:
        print('WARNING: arm9.bin not found — skipping arm9 patches')

    # ── overlay_0001 ──────────────────────────────────────────────────────────
    if 'ov0001' in files and 'y9' in files:
        print('overlay_0001.bin:')
        ov1      = files['ov0001']
        orig     = ov1.stat().st_size
        dec      = overlay_decompress(ov1)
        apply_grow_actionhelp(dec)
        if sel('xp_mult'):      apply_xp_mult(dec, val('xp_mult'))
        if sel('scout_offense'): apply_scout_offense(dec)
        if sel('scout_penalty'): apply_scout_penalty(dec)
        comp = overlay_compress(bytes(dec))
        ov1.write_bytes(comp)
        print(f'  wrote {ov1} ({len(comp):#x} bytes, was {orig:#x})')
        if len(comp) != orig:
            update_y9(files['y9'], 1, len(comp))
        else:
            print('  compressed size unchanged — y9.bin overlay 1 not modified')
        print()
    else:
        miss = [n for n, k in [('overlay_0001.bin', 'ov0001'), ('y9.bin', 'y9')]
                if k not in files]
        print(f'WARNING: {", ".join(miss)} not found — skipping overlay_0001 patches')

    # ── overlay_0000 ──────────────────────────────────────────────────────────
    if sel('synthesis_level') or sel('synthesis_polarity'):
        if 'ov0000' in files and 'y9' in files:
            print('overlay_0000.bin:')
            ov0  = files['ov0000']
            orig = ov0.stat().st_size
            dec  = overlay_decompress(ov0)
            if sel('synthesis_level'):    apply_synthesis_level(dec, val('synthesis_level'))
            if sel('synthesis_polarity'): apply_synthesis_polarity(dec)
            comp = overlay_compress(bytes(dec))
            ov0.write_bytes(comp)
            print(f'  wrote {ov0} ({len(comp):#x} bytes, was {orig:#x})')
            if len(comp) != orig:
                update_y9(files['y9'], 0, len(comp))
            else:
                print('  compressed size unchanged — y9.bin overlay 0 not modified')
            print()
        else:
            miss = [n for n, k in [('overlay_0000.bin', 'ov0000'), ('y9.bin', 'y9')]
                    if k not in files]
            print(f'WARNING: {", ".join(miss)} not found — skipping overlay_0000 patches')

    # ── NFTR ──────────────────────────────────────────────────────────────────
    if sel('gender_icons'):
        if 'nftr' in files:
            print('font_16x16.NFTR:')
            apply_gender_icons(files['nftr'])
            print()
        else:
            print('WARNING: font_16x16.NFTR not found — skipping gender icons')

    print('Done.')


if __name__ == '__main__':
    main()
