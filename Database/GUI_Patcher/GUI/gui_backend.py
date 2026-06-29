#!/usr/bin/env python3
import argparse
import os
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd, cwd=None):
    print("> " + " ".join(map(str, cmd)), flush=True)
    p = subprocess.run(cmd, cwd=cwd)
    if p.returncode != 0:
        raise SystemExit(p.returncode)


def app_root():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def run_py_script(script_path, argv):
    script_path = Path(script_path).resolve()
    old_argv = sys.argv[:]
    old_cwd = Path.cwd()
    try:
        sys.argv = [str(script_path)] + [str(a) for a in argv]
        os.chdir(script_path.parent)
        spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "main"):
            mod.main()
    finally:
        os.chdir(old_cwd)
        sys.argv = old_argv


def find_ndstool(root, repo):
    if sys.platform.startswith("win"):
        bundled = root / "bundled" / "tools" / "windows" / "ndstool.exe"
    else:
        bundled = root / "bundled" / "tools" / "linux" / "ndstool"

    if bundled.exists():
        return bundled

    db_tool = repo / "Database" / "ndstool.exe"
    if db_tool.exists():
        return db_tool

    found = shutil.which("ndstool")
    if found:
        return Path(found)

    raise SystemExit("ndstool not found.")

def main(argv=None):
    ap = argparse.ArgumentParser(description="DQMJ2P GUI patch backend")
    ap.add_argument("--rom", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--work", default="GUI_WORK")
    ap.add_argument("--repo", default="AUTO")

    ap.add_argument("--new-synths", action="store_true")
    ap.add_argument("--xp-mult", type=float, default=None)
    ap.add_argument("--xvariant-suffix", action="store_true")
    ap.add_argument("--gender-icons", action="store_true")
    ap.add_argument("--scout-offense", action="store_true")
    ap.add_argument("--scout-penalty", action="store_true")
    ap.add_argument("--synthesis-level", type=int, default=None)
    ap.add_argument("--synthesis-polarity", action="store_true")

    args = ap.parse_args(argv)

    root = app_root()
    if args.repo == "AUTO":
        bundled_repo = root / "bundled" / "repo"
        repo = bundled_repo if bundled_repo.exists() else Path(__file__).resolve().parents[3]
    else:
        repo = Path(args.repo).resolve()

    rom = Path(args.rom).resolve()
    output = Path(args.output).resolve()
    work = Path(args.work).resolve()
    pro_rom = work / "Pro_ROM"

    sys.path.insert(0, str(repo / "Pro_Tools"))

    import msgtool
    import storytool
    from apply_patches import (
        arm9_decompress, arm9_compress,
        overlay_decompress, overlay_compress,
        update_y9,
        apply_grow_msg_pool,
        apply_grow_actionhelp,
        apply_xp_mult,
        apply_xvariant_suffix,
        apply_gender_icons,
        apply_scout_offense,
        apply_scout_penalty,
        apply_synthesis_level,
        apply_synthesis_polarity,
        find_rom,
    )

    if not rom.is_file():
        raise SystemExit(f"ROM not found: {rom}")

    ndstool = find_ndstool(root, repo)

    if work.exists():
        shutil.rmtree(work)
    pro_rom.mkdir(parents=True)

    print(f"Input ROM: {rom}")
    print(f"Output ROM: {output}")
    print(f"Work dir: {work}")
    print()

    run([
        str(ndstool), "-x", str(rom),
        "-7", str(pro_rom / "arm7.bin"),
        "-9", str(pro_rom / "arm9.bin"),
        "-d", str(pro_rom / "data_dir"),
        "-y", str(pro_rom / "overlay_dir"),
        "-t", str(pro_rom / "banner.bin"),
        "-h", str(pro_rom / "header.bin"),
        "-y7", str(pro_rom / "y7.bin"),
        "-y9", str(pro_rom / "y9.bin"),
        "-o", str(pro_rom / "logo.bin"),
    ])

    print("Decompressing ARM9 for text tools...")
    run_py_script(repo / "Pro_Tools" / "arm9tool.py", [
        "decompress",
        pro_rom / "arm9.bin",
        repo / "Pro_Tools" / "Pro_ARM9.bin",
    ])

    print("Repacking strings...")
    msgtool.cmd_repack(str(repo / "Translation" / "STRINGS"), str(pro_rom / "data_dir"))

    print("Assembling scripts...")
    storytool.cmd_asm(str(repo / "Translation" / "SCRIPTS"), str(pro_rom / "data_dir"))

    files = find_rom(pro_rom)

    print("Applying ARM9 patches...")
    if "arm9" not in files:
        raise SystemExit("arm9.bin not found")
    arm9 = files["arm9"]
    dec = arm9_decompress(arm9)
    apply_grow_msg_pool(dec, 0x35000)
    if args.xvariant_suffix:
        apply_xvariant_suffix(dec)
    arm9.write_bytes(arm9_compress(dec))

    print("Applying overlay_0001 patches...")
    if "ov0001" not in files or "y9" not in files:
        raise SystemExit("overlay_0001.bin or y9.bin not found")
    ov1 = files["ov0001"]
    orig = ov1.stat().st_size
    dec = overlay_decompress(ov1)

    apply_grow_actionhelp(dec)
    if args.xp_mult is not None:
        apply_xp_mult(dec, args.xp_mult)

    if args.scout_offense:
        apply_scout_offense(dec)
    if args.scout_penalty:
        apply_scout_penalty(dec)

    comp = overlay_compress(bytes(dec))
    ov1.write_bytes(comp)
    if len(comp) != orig:
        update_y9(files["y9"], 1, len(comp))

    if args.synthesis_level is not None or args.synthesis_polarity:
        print("Applying overlay_0000 patches...")
        if "ov0000" not in files:
            raise SystemExit("overlay_0000.bin not found")
        ov0 = files["ov0000"]
        orig = ov0.stat().st_size
        dec = overlay_decompress(ov0)

        if args.synthesis_level is not None:
            apply_synthesis_level(dec, args.synthesis_level)
        if args.synthesis_polarity:
            apply_synthesis_polarity(dec)

        comp = overlay_compress(bytes(dec))
        ov0.write_bytes(comp)
        if len(comp) != orig:
            update_y9(files["y9"], 0, len(comp))

    if args.gender_icons:
        print("Applying gender icon replacement...")
        if "nftr" not in files:
            raise SystemExit("font_16x16.NFTR not found")
        apply_gender_icons(files["nftr"])

    if args.new_synths:
        print("Adding new synthesis recipes...")

        kind_csv = work / "Kind.csv"
        fourg_csv = work / "4g.csv"

        run_py_script(repo / "Pro_Tools" / "synthesis_parser.py", [
            "--in", pro_rom / "data_dir" / "CombinationKindTbl.bin",
            "--out", kind_csv,
        ])

        run_py_script(repo / "Pro_Tools" / "synthesis_parser.py", [
            "--in", pro_rom / "data_dir" / "Combination4GTbl.bin",
            "--out", fourg_csv,
            "--type", "4g",
        ])

        with open(kind_csv, "a", encoding="utf-8", newline="") as out:
            out.write((repo / "Database" / "new_synths_kind.csv").read_text(encoding="utf-8"))

        with open(fourg_csv, "a", encoding="utf-8", newline="") as out:
            out.write((repo / "Database" / "new_synths_4g.csv").read_text(encoding="utf-8"))

        run_py_script(repo / "Pro_Tools" / "synthesis_parser.py", [
            "--in", kind_csv,
            "--out", pro_rom / "data_dir" / "CombinationKindTbl.bin",
        ])

        run_py_script(repo / "Pro_Tools" / "synthesis_parser.py", [
            "--in", fourg_csv,
            "--out", pro_rom / "data_dir" / "Combination4GTbl.bin",
            "--type", "4g",
        ])

    print("Rebuilding ROM...")
    run([
        str(ndstool), "-c", str(output),
        "-7", str(pro_rom / "arm7.bin"),
        "-9", str(pro_rom / "arm9.bin"),
        "-d", str(pro_rom / "data_dir"),
        "-y", str(pro_rom / "overlay_dir"),
        "-t", str(pro_rom / "banner.bin"),
        "-h", str(pro_rom / "header.bin"),
        "-y7", str(pro_rom / "y7.bin"),
        "-y9", str(pro_rom / "y9.bin"),
        "-o", str(pro_rom / "logo.bin"),
    ])

    print()
    print(f"Done: {output}")


if __name__ == "__main__":
    main()
