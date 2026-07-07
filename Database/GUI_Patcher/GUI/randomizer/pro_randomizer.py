from dataclasses import dataclass, field
from pathlib import Path
import random


@dataclass
class ProRandomizerConfig:
    seed: int = 0
    generate_spoiler: bool = True
    randomize_monsters: bool = False
    allow_flee_scout: bool = True
    remove_zero_xp: bool = True
    randomize_xp: bool = False
    stronger_monsters: bool = False
    no_flee: bool = False
    rank_excludes: set[str] = field(default_factory=set)
    family_excludes: set[str] = field(default_factory=set)
    size_excludes: set[str] = field(default_factory=set)


def run_pro_randomizer(extracted_rom_dir: Path, config: ProRandomizerConfig, log=print):
    """
    Prototype hook.

    Wire0n's EU DQMJ2 randomizer patches BtlEnmyPrm2.bin, LevelUpTbl.bin,
    SkillPointTbl.bin, and ItemTbl.bin by matching known EU table bytes inside
    the raw ROM. For DQMJ2P we should patch the extracted filesystem files
    directly after ndstool extraction and before rebuild.
    """
    extracted_rom_dir = Path(extracted_rom_dir)

    data_dir = extracted_rom_dir / "data_dir"
    if not data_dir.is_dir():
        raise FileNotFoundError(f"data_dir not found: {data_dir}")

    seed = config.seed or random.randint(1, 999999)
    random.seed(seed)

    log(f"Randomizer prototype enabled")
    log(f"Seed: {seed}")
    log("TODO: locate DQMJ2P table files and port randomization safely")

    return {
        "seed": seed,
        "spoiler_text": f"Randomization Seed: {seed}\n",
    }
