#!/usr/bin/env python3
import argparse
import atexit
import os
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd, cwd=None):
    print("> " + " ".join(map(str, cmd)), flush=True)

    creationflags = 0
    startupinfo = None

    if sys.platform.startswith("win"):
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    p = subprocess.run(
        [str(x) for x in cmd],
        cwd=cwd,
        creationflags=creationflags,
        startupinfo=startupinfo,
    )

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


def inject_splash_assets(root, data_dir):
    splash_dir = root / "splash"
    if not splash_dir.is_dir():
        print(f"WARNING: splash asset folder missing: {splash_dir}")
        return

    files = [
        "warning.chr",
        "warning.pal",
        "warning_lo.scrn",
        "warning_up.scrn",
    ]

    print("Injecting custom splash graphics...")

    for name in files:
        src = splash_dir / name
        dst = Path(data_dir) / name

        if not src.is_file():
            raise SystemExit(f"Missing splash asset: {src}")

        shutil.copy2(src, dst)
        print(f"  {name} -> {dst}")


def find_ndstool(root, repo):
    if sys.platform.startswith("win"):
        bundled = root / "bundled" / "tools" / "windows" / "ndstool.exe"
    elif sys.platform == "darwin":
        bundled = root / "bundled" / "tools" / "macos" / "ndstool"
    else:
        bundled = root / "bundled" / "tools" / "linux" / "ndstool"

    if bundled.exists():
        return bundled

    if sys.platform.startswith("win"):
        db_tool = repo / "Database" / "ndstool.exe"
        if db_tool.exists():
            return db_tool

    found = shutil.which("ndstool")
    if found:
        return Path(found)

    raise SystemExit("ndstool not found.")

AP_PATCHES = [
    (0x00004500,
     "AB 6C 48 42 E2 00 9B 10 0E E3 62 A1 B4 96 67 FB",
     "00 00 9F E5 1E FF 2F E1 83 A8 00 00 07 40 2D E9"),
    (0x00004510,
     "F8 E8 C7 E2 A8 E1 87 76 96 9D F5 6C A0 3C F0 1A",
     "14 00 9F E5 14 10 9F E5 00 20 91 E5 02 00 50 E1"),
    (0x00004520,
     "FA B2 CF B2 13 94 FE 10 9C 6B 4A 11 C4 5A 4F F3",
     "0C 00 9F 05 00 00 81 05 07 80 BD E8 EC 90 1D 02"),
    (0x00004530,
     "C9 D3 5E 75 00 6E 0B C7",
     "C8 88 1D 02 00 15 00 02"),
    (0x000049F8,
     "1E FF 2F E1",
     "C3 FE FF EA"),
]


def _hexbytes(s):
    return bytes.fromhex(s.replace(" ", ""))


def apply_antipiracy_patch(input_rom, work_dir):
    src = Path(input_rom)
    dst = Path(work_dir) / "input_antipiracy.nds"
    shutil.copy2(src, dst)

    data = bytearray(dst.read_bytes())

    print("Applying anti-piracy patch for official hardware...")

    for off, old_hex, new_hex in AP_PATCHES:
        old = _hexbytes(old_hex)
        new = _hexbytes(new_hex)
        cur = bytes(data[off:off + len(old)])

        if cur == new:
            print(f"  0x{off:08X}: already patched")
            continue

        if cur != old:
            raise SystemExit(
                f"Anti-piracy patch mismatch at 0x{off:08X}. "
                "This ROM does not match the expected clean DQMJ2P ROM, "
                "or it was already modified differently."
            )

        data[off:off + len(old)] = new
        print(f"  0x{off:08X}: patched")

    dst.write_bytes(data)
    return dst



def apply_overlay4_antipiracy_patch(ov4_path, overlay_decompress, overlay_compress):
    ov4_path = Path(ov4_path)
    if not ov4_path.is_file():
        raise SystemExit(f"overlay_0004.bin not found: {ov4_path}")

    print("Applying anti-piracy patch to overlay_0004...")

    dec = overlay_decompress(ov4_path)

    if len(dec) < 0x1F8:
        raise SystemExit("overlay_0004.bin is smaller than expected after decompression")

    ptr_154 = dec[0x154:0x158]
    ptr_1f4 = dec[0x1F4:0x1F8]

    old_150 = dec[0x150:0x154]
    old_1f0 = dec[0x1F0:0x1F4]

    dec[0x150:0x154] = ptr_154
    dec[0x1F0:0x1F4] = ptr_1f4

    print(f"  overlay_0004 +0x150: {old_150.hex(' ')} -> {ptr_154.hex(' ')}")
    print(f"  overlay_0004 +0x1F0: {old_1f0.hex(' ')} -> {ptr_1f4.hex(' ')}")

    ov4_path.write_bytes(overlay_compress(bytes(dec)))


def _csv_set(value):
    return {x.strip() for x in str(value).split(",") if x.strip()}



def build_randomizer_settings_summary(args):
    lines = [
        "",
        "--- Patcher Settings ---",
        "Patch options:",
        "- Anti-piracy: on",
        f"- New synthesis recipes: {'on' if args.new_synths else 'off'}",
        f"- X/XY monster suffixes: {'on' if args.xvariant_suffix else 'off'}",
        f"- Gender icons: {'on' if args.gender_icons else 'off'}",
        f"- XP multiplier: {'on' if bool(args.xp_mult) else 'off'}",
        f"- Scout offense boost: {'on' if args.scout_offense else 'off'}",
        f"- Scout penalty changes: {'on' if args.scout_penalty else 'off'}",
        f"- Synthesis level changes: {'on' if args.synthesis_level else 'off'}",
        f"- Synthesis polarity changes: {'on' if args.synthesis_polarity else 'off'}",
        "",
        "Randomiser settings:",
        f"- Battle monsters: {'on' if args.randomizer_monsters else 'off'}",
        f"- Battle XP rewards: {'on' if args.randomizer_xp else 'off'}",
        f"- Spoiler log: {'on' if args.randomizer_spoiler else 'off'}",
        f"- Allow Flee/Scout: {'on' if args.randomizer_allow_flee else 'off'}",
        f"- Stronger monsters: {'on' if args.randomizer_stronger else 'off'}",
        f"- No flee: {'on' if args.randomizer_no_flee else 'off'}",
        f"- Level Up XP mode: {args.randomizer_level_up}",
        f"- Level Up XP variance: {args.randomizer_level_up_variance}",
        f"- Skill Points mode: {args.randomizer_skill_points}",
        f"- Excluded ranks: {args.randomizer_rank_excludes or 'none'}",
        f"- Excluded families: {args.randomizer_family_excludes or 'none'}",
        f"- Excluded sizes: {args.randomizer_size_excludes or 'none'}",
        "- 0-XP battle entries: always skipped",
        "",
    ]

    return "\n".join(lines)

def main(argv=None):
    ap = argparse.ArgumentParser(description="DQMJ2P GUI patch backend")
    ap.add_argument("--rom", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--work", default="GUI_WORK")
    ap.add_argument("--keep-work", action="store_true", help="Do not delete GUI_WORK after patching")
    ap.add_argument("--repo", default="AUTO")

    ap.add_argument("--new-synths", action="store_true")
    ap.add_argument("--anti-piracy", action="store_true")
    ap.add_argument("--xp-mult", type=float, default=None)
    ap.add_argument("--xvariant-suffix", action="store_true")
    ap.add_argument("--gender-icons", action="store_true")
    ap.add_argument("--scout-offense", action="store_true")
    ap.add_argument("--scout-penalty", action="store_true")
    ap.add_argument("--synthesis-level", type=int, default=None)
    ap.add_argument("--synthesis-polarity", action="store_true")

    ap.add_argument("--randomizer-monsters", action="store_true")
    ap.add_argument("--randomizer-seed", type=int, default=0)
    ap.add_argument("--randomizer-spoiler", action="store_true")
    ap.add_argument("--randomizer-allow-flee", action="store_true")
    ap.add_argument("--randomizer-remove-zero-xp", action="store_true")
    ap.add_argument("--randomizer-xp", action="store_true")
    ap.add_argument("--randomizer-stronger", action="store_true")
    ap.add_argument("--randomizer-no-flee", action="store_true")
    ap.add_argument("--randomizer-level-up", choices=["none", "swap", "random"], default="none")
    ap.add_argument("--randomizer-level-up-variance", type=int, default=110)
    ap.add_argument("--randomizer-skill-points", choices=["none", "swap", "random"], default="none")
    ap.add_argument("--randomizer-rank-excludes", default="")
    ap.add_argument("--randomizer-family-excludes", default="")
    ap.add_argument("--randomizer-size-excludes", default="")

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

    def _cleanup_work():
        if args.keep_work:
            print(f"Keeping work dir: {work}")
            return
        try:
            if work.exists():
                shutil.rmtree(work)
                print(f"Cleaned work dir: {work}")
        except Exception as e:
            print(f"WARNING: failed to clean work dir {work}: {e}")

    atexit.register(_cleanup_work)

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

    rom_for_extract = rom

    run([
        str(ndstool), "-x", str(rom_for_extract),
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

    inject_splash_assets(root, pro_rom / "data_dir")

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

    # TEMP crash workaround: disable actionhelp growth pending proper fix.
    # apply_grow_actionhelp(dec)
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

    if (
        args.randomizer_monsters
        or args.randomizer_xp
        or args.randomizer_level_up != "none"
        or args.randomizer_skill_points != "none"
    ):
        sys.path.insert(0, str(root))
        from randomizer.pro_randomizer import ProRandomizerConfig, run_pro_randomizer

        randomizer_config = ProRandomizerConfig(
            seed=args.randomizer_seed,
            generate_spoiler=args.randomizer_spoiler,
            randomize_monsters=args.randomizer_monsters,
            allow_flee_scout=args.randomizer_allow_flee,
            remove_zero_xp=True,
            randomize_xp=args.randomizer_xp,
            stronger_monsters=args.randomizer_stronger,
            no_flee=args.randomizer_no_flee,
            level_up_mode=args.randomizer_level_up,
            level_up_variance=args.randomizer_level_up_variance,
            skill_points_mode=args.randomizer_skill_points,
            rank_excludes=_csv_set(args.randomizer_rank_excludes),
            family_excludes=_csv_set(args.randomizer_family_excludes),
            size_excludes=_csv_set(args.randomizer_size_excludes),
            settings_summary=build_randomizer_settings_summary(args),
        )

        run_pro_randomizer(
            pro_rom,
            output.parent,
            repo,
            randomizer_config,
            log=print,
        )


    if args.anti_piracy:
        ov4 = pro_rom / "overlay_dir" / "overlay_0004.bin"
        y9 = pro_rom / "y9.bin"
        if not ov4.is_file() or not y9.is_file():
            raise SystemExit("overlay_0004.bin or y9.bin not found")
        orig = ov4.stat().st_size
        apply_overlay4_antipiracy_patch(ov4, overlay_decompress, overlay_compress)
        if ov4.stat().st_size != orig:
            update_y9(y9, 4, ov4.stat().st_size)

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
