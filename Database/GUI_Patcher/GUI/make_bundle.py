#!/usr/bin/env python3
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = ROOT / "GUI" / "bundled" / "repo"

REMOVE_DIRS = [
    ".git",
    "GUI/bundled",
    "GUI_WORK",
    "Pro_ROM",
    "Pro_ROM_YT",
    "_roms",
    "_graphics",
    "build",
    "dist",
    "__pycache__",
]

REMOVE_GLOBS = [
    "*.nds",
    "*.sav",
    "*.dsv",
    "*.ml1",
    "*.bak",
    "*.bak_*",
    "*.zip",
    "*.7z",
    "*.tar",
    "*.tar.zst",
    "*.pyc",
    "patched_*",
    "Patched*",
]

def remove_path(p: Path):
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=True)
    elif p.exists():
        p.unlink()

with tempfile.TemporaryDirectory(prefix="dqmj2p_bundle_") as tmp:
    stage = Path(tmp) / "repo_stage"

    print(f"Creating clean stage: {stage}")
    shutil.copytree(ROOT, stage, symlinks=False)

    for rel in REMOVE_DIRS:
        remove_path(stage / rel)

    for pat in REMOVE_GLOBS:
        for p in stage.rglob(pat):
            remove_path(p)

    if BUNDLE.exists():
        shutil.rmtree(BUNDLE)

    BUNDLE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(stage, BUNDLE)

print(f"Bundled repo written to: {BUNDLE}")
