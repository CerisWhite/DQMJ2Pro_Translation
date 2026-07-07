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

    pool = [bytes(entries[i]) for i in valid_indices]

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

    shuffled = pool[:]
    random.shuffle(shuffled)

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
    log(f"Changed battle monster entries: {changed}")

    if config.generate_spoiler:
        output_dir.mkdir(parents=True, exist_ok=True)
        spoiler = output_dir / f"randomizer_spoiler_{config.seed}.txt"
        spoiler.write_text(f"Randomization Seed: {config.seed}\n", encoding="utf-8")
        _write_spoiler(spoiler, f"BtlEnmyPrm2 entries randomized: {len(valid_indices)} / {num_entries}\n")
        _write_spoiler(spoiler, f"BtlEnmyPrm2 entries changed: {changed}\n\n")
        _write_spoiler(spoiler, "--- By battle entry order ---\n")
        _write_spoiler(spoiler, "".join(spoiler_lines))
        _write_spoiler(spoiler, "\n--- By original monster name ---\n")
        _write_spoiler(spoiler, "".join(line for _key, line in sorted(spoiler_by_old_name)))
        log(f"Spoiler file: {spoiler}")


def run_pro_randomizer(pro_rom: Path, output_dir: Path, repo: Path, config: ProRandomizerConfig, log=print):
    pro_rom = Path(pro_rom)
    data_dir = pro_rom / "data_dir"

    seed = config.seed or random.randint(1, 999999)
    config.seed = seed
    random.seed(seed)

    log("Running DQMJ2P randomizer...")
    log(f"Seed: {seed}")

    if config.randomize_monsters:
        randomize_battle_monsters(data_dir, Path(output_dir), Path(repo), config, log=log)
    else:
        log("Randomizer enabled, but no randomizer modules selected")
