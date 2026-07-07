from dataclasses import dataclass, field
from pathlib import Path
import random
import struct


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
    level_up_mode: str = "none"  # none, swap, random
    level_up_variance: int = 110
    skill_points_mode: str = "none"  # none, swap, random


def _load_monster_names(repo: Path) -> dict[int, str]:
    names = {}
    path = repo / "Translation" / "STRINGS" / "msg_monstername.txt"

    if not path.is_file():
        return names

    # msg_monstername.txt line number matches monster ID.
    # Line 0 is blank/none, line 1 is Slime.
    for monster_id, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        name = line.strip()
        if name:
            names[monster_id] = name

    return names


def _monster_label(names: dict[int, str], monster_id: int) -> str:
    name = names.get(monster_id)
    if name:
        return f"{name} ({monster_id})"
    return f"monster {monster_id}"


def _write_spoiler(path: Path, text: str):
    with path.open("a", encoding="utf-8") as f:
        f.write(text)



def _norm_name(name: str) -> str:
    return (
        name.strip()
        .lower()
        .replace("’", "'")
        .replace(" ", "")
        .replace("-", "")
    )


def _load_monster_catalog(repo: Path) -> dict[int, dict[str, str]]:
    """Load J2P catalog metadata keyed by monster ID."""
    import csv

    db_path = Path(__file__).resolve().parent / "monster_database.csv"
    names_path = repo / "Translation" / "STRINGS" / "msg_monstername.txt"

    if not db_path.is_file() or not names_path.is_file():
        return {}

    name_to_id = {}
    for monster_id, line in enumerate(names_path.read_text(encoding="utf-8", errors="replace").splitlines()):
        name = line.strip()
        if name:
            name_to_id[_norm_name(name)] = monster_id

    catalog = {}
    with db_path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            name = (row.get("Monster (Eng)") or "").strip()
            monster_id = name_to_id.get(_norm_name(name))
            if not monster_id:
                continue

            family = (row.get("Family") or "").strip()
            if family in ("？？？系", "???系"):
                family = "???"

            catalog[monster_id] = {
                "rank": (row.get("Rank") or "").strip().upper(),
                "family": family.lower(),
                "size": (row.get("Sz.") or "").strip(),
            }

    return catalog


def _monster_allowed_by_filters(monster_id: int, catalog: dict[int, dict[str, str]], config: ProRandomizerConfig) -> bool:
    if not config.rank_excludes and not config.family_excludes and not config.size_excludes:
        return True

    info = catalog.get(monster_id)
    if not info:
        return False

    rank_excludes = {x.upper() for x in config.rank_excludes}
    family_excludes = {x.lower() for x in config.family_excludes}
    size_excludes = {str(x) for x in config.size_excludes}

    if info["rank"] in rank_excludes:
        return False
    if info["family"] in family_excludes:
        return False
    if info["size"] in size_excludes:
        return False

    return True

def randomize_battle_monsters(data_dir: Path, output_dir: Path, repo: Path, config: ProRandomizerConfig, log=print):
    path = data_dir / "BtlEnmyPrm2.bin"
    if not path.is_file():
        raise FileNotFoundError(path)

    data = path.read_bytes()
    header_size = 8
    entry_size = 100

    header = data[:header_size]
    body = data[header_size:]

    if len(body) % entry_size:
        raise ValueError(f"BtlEnmyPrm2.bin unexpected size: body remainder {len(body) % entry_size}")

    num_entries = len(body) // entry_size
    entries = [bytearray(body[i * entry_size:(i + 1) * entry_size]) for i in range(num_entries)]

    monster_names = _load_monster_names(repo)
    monster_catalog = _load_monster_catalog(repo)

    valid_indices = []
    for i, entry in enumerate(entries):
        monster_id = struct.unpack("<H", entry[0:2])[0]
        xp = int.from_bytes(entry[40:43], "little")
        if monster_id <= 0:
            continue
        if config.remove_zero_xp and xp <= 0:
            continue
        valid_indices.append(i)

    if not valid_indices:
        raise ValueError("No valid battle monster entries after filtering")

    candidate_indices = []
    for i, entry in enumerate(entries):
        monster_id = struct.unpack("<H", entry[0:2])[0]
        xp = int.from_bytes(entry[40:43], "little")

        if monster_id <= 0:
            continue
        if config.remove_zero_xp and xp <= 0:
            continue
        if _monster_allowed_by_filters(monster_id, monster_catalog, config):
            candidate_indices.append(i)

    if not candidate_indices:
        raise ValueError("No valid battle monster candidates after rank/family/size filtering")

    pool = [bytes(entries[i]) for i in candidate_indices]

    if config.stronger_monsters:
        boosted = []
        for e in pool:
            b = bytearray(e)
            stats = []
            for off in (48, 50, 52, 54, 56, 58):
                stats.append(min(int(struct.unpack("<H", b[off:off+2])[0] * 1.5), 9999))
            b[48:60] = struct.pack("<6H", *stats)
            boosted.append(bytes(b))
        pool = boosted

    if config.allow_flee_scout:
        pool = [e[:98] + bytes([0x00]) + e[99:] for e in pool]
    elif config.no_flee:
        pool = [e[:98] + bytes([0x02]) + e[99:] for e in pool]

    if config.randomize_xp:
        buckets = [
            (0, 100, 54),
            (100, 1000, 30),
            (1000, 10000, 10),
            (10000, 100000, 5),
            (100000, 333333, 1),
        ]
        weighted = []
        for lo, hi, weight in buckets:
            weighted.extend([(lo, hi)] * weight)

        new_pool = []
        for e in pool:
            b = bytearray(e)
            lo, hi = random.choice(weighted)
            xp = random.randint(lo, hi)
            b[40:43] = xp.to_bytes(3, "little")
            new_pool.append(bytes(b))
        pool = new_pool

    if len(pool) == len(valid_indices):
        shuffled = pool[:]
        random.shuffle(shuffled)
    else:
        shuffled = [random.choice(pool) for _ in valid_indices]

    spoiler_lines = []
    spoiler_by_old_name = []
    out_entries = [bytes(e) for e in entries]
    changed = 0

    for dst_i, old_entry, new_entry in zip(valid_indices, [bytes(entries[i]) for i in valid_indices], shuffled):
        old_id = struct.unpack("<H", old_entry[0:2])[0]
        new_id = struct.unpack("<H", new_entry[0:2])[0]
        old_xp = int.from_bytes(old_entry[40:43], "little")
        new_xp = int.from_bytes(new_entry[40:43], "little")

        if old_entry != new_entry:
            changed += 1

        line = f"Entry {dst_i:04d}: {_monster_label(monster_names, old_id)} -> {_monster_label(monster_names, new_id)}, XP {old_xp} -> {new_xp}\n"
        spoiler_lines.append(line)
        spoiler_by_old_name.append((_monster_label(monster_names, old_id).lower(), line))
        out_entries[dst_i] = new_entry

    path.write_bytes(header + b"".join(out_entries))

    log(f"Randomized battle monster table: {len(valid_indices)} entries from {num_entries} total")
    if len(candidate_indices) != len(valid_indices):
        log(f"Filtered replacement candidate pool: {len(candidate_indices)} entries")
    log(f"Changed battle monster entries: {changed}")

    if config.generate_spoiler:
        output_dir.mkdir(parents=True, exist_ok=True)
        spoiler = output_dir / f"randomizer_spoiler_{config.seed}.txt"
        spoiler.write_text(f"Randomization Seed: {config.seed}\n", encoding="utf-8")
        _write_spoiler(spoiler, f"BtlEnmyPrm2 entries randomized: {len(valid_indices)} / {num_entries}\n")
        _write_spoiler(spoiler, f"Replacement candidate pool: {len(candidate_indices)} entries\n")
        if config.rank_excludes:
            _write_spoiler(spoiler, f"Excluded ranks: {', '.join(sorted(config.rank_excludes))}\n")
        if config.family_excludes:
            _write_spoiler(spoiler, f"Excluded families: {', '.join(sorted(config.family_excludes))}\n")
        if config.size_excludes:
            _write_spoiler(spoiler, f"Excluded sizes: {', '.join(sorted(str(x) for x in config.size_excludes))}\n")
        _write_spoiler(spoiler, f"BtlEnmyPrm2 entries changed: {changed}\n\n")
        _write_spoiler(spoiler, "--- By battle entry order ---\n")
        _write_spoiler(spoiler, "".join(spoiler_lines))
        _write_spoiler(spoiler, "\n--- By original monster name ---\n")
        _write_spoiler(spoiler, "".join(line for _key, line in sorted(spoiler_by_old_name)))
        log(f"Spoiler file: {spoiler}")



def _weighted_choice(data):
    total = sum(weight for weight, _value in data)
    pick = random.uniform(0, total)
    cur = 0
    for weight, value in data:
        if cur <= pick < cur + weight:
            return value
        cur += weight
    return data[0][1]


def randomize_level_up(data_dir: Path, output_dir: Path, config: ProRandomizerConfig, log=print):
    if config.level_up_mode == "none":
        return

    path = data_dir / "LevelUpTbl.bin"
    if not path.is_file():
        raise FileNotFoundError(path)

    data = path.read_bytes()
    header = data[:400]
    body = data[400:]

    if len(body) % 400:
        raise ValueError(f"LevelUpTbl.bin unexpected size: body remainder {len(body) % 400}")

    curves = [bytearray(body[i * 400:(i + 1) * 400]) for i in range(len(body) // 400)]

    spoiler_lines = []
    if config.level_up_mode == "swap":
        before = list(range(len(curves)))
        shuffled = curves[:]
        random.shuffle(shuffled)
        curves = shuffled
        spoiler_lines.append("Level Up XP curve mode: swap\n")
        spoiler_lines.append(f"Curves shuffled: {before}\n")

    elif config.level_up_mode == "random":
        variance_factor = max(100, min(config.level_up_variance, 300)) / 100.0
        spoiler_lines.append(f"Level Up XP curve mode: random, variance {config.level_up_variance}%\n")

        for ci, curve in enumerate(curves):
            amounts = [int.from_bytes(curve[j * 4:(j + 1) * 4], "little") for j in range(100)]
            diffs = [0] + [amounts[j + 1] - amounts[j] for j in range(99)]

            new_amounts = []
            total = 0
            for level, diff in enumerate(diffs):
                if level == 0:
                    total = amounts[0]
                else:
                    factor = random.uniform(2 - variance_factor, variance_factor)
                    total = max(total, int(total + diff * factor))
                new_amounts.append(total)

            curves[ci] = bytearray().join(int(x).to_bytes(4, "little") for x in new_amounts)

    else:
        raise ValueError(f"Unknown level up randomiser mode: {config.level_up_mode}")

    path.write_bytes(header + b"".join(bytes(c) for c in curves))
    log(f"Randomized LevelUpTbl.bin: mode={config.level_up_mode}")

    if config.generate_spoiler:
        output_dir.mkdir(parents=True, exist_ok=True)
        spoiler = output_dir / f"randomizer_spoiler_{config.seed}.txt"
        _write_spoiler(spoiler, "\n--- Level Up XP Randomisation ---\n")
        _write_spoiler(spoiler, "".join(spoiler_lines))


def randomize_skill_points(data_dir: Path, output_dir: Path, config: ProRandomizerConfig, log=print):
    if config.skill_points_mode == "none":
        return

    path = data_dir / "SkillPointTbl.bin"
    if not path.is_file():
        raise FileNotFoundError(path)

    data = bytearray(path.read_bytes())
    if len(data) != 100:
        raise ValueError(f"SkillPointTbl.bin unexpected size: {len(data)}")

    values = [data[i] for i in range(100)]

    if config.skill_points_mode == "swap":
        random.shuffle(values)
    elif config.skill_points_mode == "random":
        weights = [
            (50.0, 1),
            (25.0, 5),
            (12.5, 8),
            (6.25, 11),
            (3.125, 15),
            (3.125, 20),
        ]
        values = [_weighted_choice(weights) for _ in range(100)]
    else:
        raise ValueError(f"Unknown skill point randomiser mode: {config.skill_points_mode}")

    path.write_bytes(bytes(values))
    log(f"Randomized SkillPointTbl.bin: mode={config.skill_points_mode}")

    if config.generate_spoiler:
        output_dir.mkdir(parents=True, exist_ok=True)
        spoiler = output_dir / f"randomizer_spoiler_{config.seed}.txt"
        _write_spoiler(spoiler, "\n--- Skill Point Randomisation ---\n")
        _write_spoiler(spoiler, f"Mode: {config.skill_points_mode}\n")
        for i, points in enumerate(values, start=1):
            _write_spoiler(spoiler, f"Level {i}: {points} skill points\n")


def run_pro_randomizer(pro_rom: Path, output_dir: Path, repo: Path, config: ProRandomizerConfig, log=print):
    pro_rom = Path(pro_rom)
    data_dir = pro_rom / "data_dir"

    seed = config.seed or random.randint(1, 999999)
    config.seed = seed
    random.seed(seed)

    log("Running DQMJ2P randomizer...")
    log(f"Seed: {seed}")

    if config.generate_spoiler:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        spoiler = Path(output_dir) / f"randomizer_spoiler_{seed}.txt"
        if not spoiler.exists():
            _write_spoiler(spoiler, f"Randomization Seed: {seed}\n")

    did_anything = False

    if config.randomize_monsters:
        randomize_battle_monsters(data_dir, Path(output_dir), Path(repo), config, log=log)
        did_anything = True

    if config.level_up_mode != "none":
        randomize_level_up(data_dir, Path(output_dir), config, log=log)
        did_anything = True

    if config.skill_points_mode != "none":
        randomize_skill_points(data_dir, Path(output_dir), config, log=log)
        did_anything = True

    if not did_anything:
        log("Randomiser enabled, but no randomiser modules selected")
