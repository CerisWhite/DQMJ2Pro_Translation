#!/usr/bin/env python3
"""One-shot build + patch for DQMJ2P Pro ROM.

1. Reads the ROM directory (same as apply_patches.py).
2. Locates data_dir inside the ROM by finding the subdirectory that contains .e files.
3. Builds Translation/STRINGS → data_dir  via msgtool.repack.
4. Builds Translation/SCRIPTS → data_dir  via storytool.asm.
5. Applies the mandatory patches + gender icon replacement with default values:
     - grow_msg_pool    (pool size 0x35000)
     - grow_actionhelp
     - gender_icons

Usage:
    performpatch.py
    performpatch.py --rom Pro_ROM
"""
import argparse, shutil, sys, tempfile
from pathlib import Path

# Make Pro_RE importable regardless of cwd.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import msgtool
import storytool
from apply_patches import (
    arm9_decompress, arm9_compress,
    overlay_decompress, overlay_compress,
    update_y9,
    apply_grow_msg_pool,
    apply_grow_actionhelp,
    apply_gender_icons,
    find_rom,
    _input_path,
)

# Root of the translation workspace (one level above Pro_RE).
_TRANS_ROOT  = _HERE.parent / 'Translation'
STRINGS_DIR  = _TRANS_ROOT / 'STRINGS'
SCRIPTS_DIR  = _TRANS_ROOT / 'SCRIPTS'

GROW_MSG_POOL_SIZE = 0x35000


# ── data_dir discovery ────────────────────────────────────────────────────────

def find_data_dir(rom_dir: Path) -> Path | None:
    """Return the immediate subdirectory of rom_dir that contains .e files, or None."""
    for sub in sorted(p for p in rom_dir.iterdir() if p.is_dir()):
        if any(sub.glob('*.e')):
            return sub
    return None


def _copy_by_name(src_dir: Path, rom_dir: Path):
    """For each file in src_dir, find a same-named file anywhere under rom_dir and overwrite it."""
    index: dict[str, Path] = {}
    for p in rom_dir.rglob('*'):
        if p.is_file():
            index.setdefault(p.name, p)   # first match wins

    for src in src_dir.iterdir():
        if not src.is_file():
            continue
        dest = index.get(src.name)
        if dest:
            shutil.copy2(src, dest)
            print(f'  copied {src.name} → {dest}')
        else:
            print(f'  WARNING: no match for {src.name} in ROM — skipped')


# ── build steps ───────────────────────────────────────────────────────────────

def _build(label: str, src_dir: Path, data_dir: Path | None, rom_dir: Path, fn):
    """Run fn(src_dir, out_dir), writing directly to data_dir if known, otherwise
    to a temp directory and then copying files into the ROM by name."""
    if not src_dir.is_dir():
        print(f'WARNING: {src_dir} not found — skipping {label}')
        return
    if not (src_dir / 'MASTER.json').exists():
        print(f'WARNING: {src_dir}/MASTER.json not found — skipping {label}')
        return

    if data_dir is not None:
        print(f'{label}: {src_dir} → {data_dir}')
        fn(str(src_dir), str(data_dir))
    else:
        print(f'{label}: data_dir unknown — building to temp dir then matching by filename')
        with tempfile.TemporaryDirectory() as tmp:
            fn(str(src_dir), tmp)
            _copy_by_name(Path(tmp), rom_dir)
    print()


def build_strings(data_dir: Path | None, rom_dir: Path):
    _build('repack strings', STRINGS_DIR, data_dir, rom_dir, msgtool.cmd_repack)


def build_scripts(data_dir: Path | None, rom_dir: Path):
    _build('asm scripts', SCRIPTS_DIR, data_dir, rom_dir, storytool.cmd_asm)


# ── patch steps ───────────────────────────────────────────────────────────────

def patch_arm9(files: dict):
    if 'arm9' not in files:
        print('WARNING: arm9.bin not found — skipping arm9 patches')
        return
    print('arm9.bin:')
    path = files['arm9']
    dec  = arm9_decompress(path)
    apply_grow_msg_pool(dec, GROW_MSG_POOL_SIZE)
    final = arm9_compress(dec)
    path.write_bytes(final)
    print(f'  wrote {path} ({len(final):#x} bytes)')
    print()


def patch_overlay1(files: dict):
    if 'ov0001' not in files or 'y9' not in files:
        miss = [n for n, k in [('overlay_0001.bin', 'ov0001'), ('y9.bin', 'y9')]
                if k not in files]
        print(f'WARNING: {", ".join(miss)} not found — skipping overlay_0001 patches')
        return
    print('overlay_0001.bin:')
    ov1  = files['ov0001']
    orig = ov1.stat().st_size
    dec  = overlay_decompress(ov1)
    apply_grow_actionhelp(dec)
    comp = overlay_compress(bytes(dec))
    ov1.write_bytes(comp)
    print(f'  wrote {ov1} ({len(comp):#x} bytes, was {orig:#x})')
    if len(comp) != orig:
        update_y9(files['y9'], 1, len(comp))
    else:
        print('  compressed size unchanged — y9.bin overlay 1 not modified')
    print()


def patch_nftr(files: dict):
    if 'nftr' not in files:
        print('WARNING: font_16x16.NFTR not found — skipping gender icons')
        return
    print('font_16x16.NFTR:')
    apply_gender_icons(files['nftr'])
    print()


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', default=None,
                    help='ROM directory (default: prompted interactively)')
    args = ap.parse_args()

    if args.rom:
        rom_dir = Path(args.rom)
    else:
        rom_dir = _input_path('Enter ROM directory [default: Pro_ROM]: ', default='Pro_ROM')
    if not rom_dir.is_dir():
        sys.exit(f'directory not found: {rom_dir}')

    data_dir = find_data_dir(rom_dir)
    if data_dir:
        print(f'data_dir: {data_dir}')
    else:
        print('data_dir not found — will match output files by name')
    print()

    build_strings(data_dir, rom_dir)
    build_scripts(data_dir, rom_dir)

    files = find_rom(rom_dir)
    print('Applying patches...')
    print()
    patch_arm9(files)
    patch_overlay1(files)
    patch_nftr(files)

    print('Done.')


if __name__ == '__main__':
    main()
