# DQMJ2-Randomizer-—-Project-Overview

# DQMJ2 Randomizer — Project Overview
Relevant source files
- [DQMJ2_Randomizer_Windows.bat](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/DQMJ2_Randomizer_Windows.bat)
- [README.md](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/README.md?plain=1)
- [screenshots/app.png](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/screenshots/app.png)

The **DQMJ2 Randomizer** is a Python-based tool designed to modify the European (EU) version of *Dragon Quest Monsters: Joker 2*[README.md7-8](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/README.md?plain=1#L7-L8) It allows players to shuffle monster encounters, customize experience curves, and apply various gameplay challenges to enhance replayability. The project features a web-based user interface powered by the `NiceGUI` framework, providing an accessible way to configure randomization settings without direct hex editing.

## Core Purpose and Audience

This tool is intended for players who wish to experience a "roguelike" or randomized version of DQMJ2. It targets a technical audience interested in how NDS ROM data is parsed and patched, as well as general users looking for a streamlined randomization experience [README.md5-7](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/README.md?plain=1#L5-L7)

### High-Level Workflow

The application follows a linear pipeline:

1. **Input:** The user uploads a clean DQMJ2 EU ROM via the Web UI [main.py236-240](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/main.py#L236-L240)
2. **Configuration:** The user selects desired filters (Rank, Family, Size) and mods (XP curves, Stat boosts) [README.md38-57](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/README.md?plain=1#L38-L57)
3. **Processing:** The engine parses binary tables, shuffles data based on a seed, and patches the ROM in-memory [shuffle.py27-50](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/shuffle.py#L27-L50)
4. **Output:** A randomized `.nds` file and an optional spoiler log are generated for the user [shuffle.py101-105](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/shuffle.py#L101-L105)

## System Architecture

The following diagram illustrates the relationship between the user-facing UI, the state management, and the underlying binary manipulation engine.

**System Component Map**

```
Code Entity Space

User Interface (Natural Language Space)

Interacts

Updates State

Triggers

Reads/Writes

Uses

Provides Config

Web Browser (127.0.0.1:8080)

Monsters/LevelUp/Items Tabs

main.py (NiceGUI Entry)

randomInfo.py (RandomizationInfo Class)

shuffle.py (randomize_and_patch)

utils.py (probability_stack)

Binary Data Tables (.bin)
```

**Sources:**[main.py1-20](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/main.py#L1-L20)[randomInfo.py1-5](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/randomInfo.py#L1-L5)[shuffle.py1-15](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/shuffle.py#L1-L15)[utils.py1-5](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/utils.py#L1-L5)

## Feature Overview

- **Monster Randomization:** Shuffles encounters in `BtlEnmyPrm2.bin` based on Rank (F to ???), Family, and Size (Small, Medium, Giant) [README.md40-47](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/README.md?plain=1#L40-L47)
- **XP & Leveling:** Offers two modes for level-up curves: "Swap" (shuffling existing curves) or "Random" (scaling XP requirements via variance factors) [shuffle.py175-200](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/shuffle.py#L175-L200)
- **Challenge Mods:** Includes "Stronger Monsters" (150% stat boost) and flee-behavior modifications [README.md52-57](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/README.md?plain=1#L52-L57)
- **Item & Skill Randomization:** Shuffles item data and skill point distribution per level [shuffle.py260-290](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/shuffle.py#L260-L290)

## Code-to-Data Mapping

The randomizer operates by locating specific patterns within the NDS ROM that correspond to internal game tables.

**Binary Table Mapping**

```
Randomizer Logic

ROM Filesystem

Pattern Match

Pattern Match

Pattern Match

Hardcoded Offset (0x41EBC00)

DQMJ2 ROM (.nds)

BtlEnmyPrm2.bin (Monster Data)

LevelUpTbl.bin (XP Curves)

SkillPointTbl.bin (SP per Level)

ItemTbl.bin (Item Data)
```

**Sources:**[shuffle.py59-62](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/shuffle.py#L59-L62)[shuffle.py178-180](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/shuffle.py#L178-L180)[shuffle.py262-264](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/shuffle.py#L262-L264)[shuffle.py291-293](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/shuffle.py#L291-L293)

## Navigation

To dive deeper into specific areas of the project, refer to the following child pages:

### [1.1 Getting Started](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/1.1 Getting Started)

Step-by-step guide for installation. Requires **Python 3.11.4** or higher [README.md13](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/README.md?plain=1#L13-L13) Covers the use of the `DQMJ2_Randomizer_Windows.bat` launcher which automates virtual environment setup and portability patching [DQMJ2_Randomizer_Windows.bat5-53](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/DQMJ2_Randomizer_Windows.bat#L5-L53)

### [1.2 Project Structure and File Layout](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/1.2 Project Structure and File Layout)

Detailed breakdown of the repository. Explains the role of the `venv/` directory, the `fonts/` assets used for the UI [main.py26-32](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/main.py#L26-L32) and the `valid_monsters.txt` reference file which serves as the primary database for monster metadata [shuffle.py12-15](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/shuffle.py#L12-L15)

---

**Sources:**

- [README.md1-81](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/README.md?plain=1#L1-L81)
- [DQMJ2_Randomizer_Windows.bat1-55](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/DQMJ2_Randomizer_Windows.bat#L1-L55)
- [main.py1-50](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/main.py#L1-L50)
- [shuffle.py1-300](https://github.com/Wire0n-misc/dqmj2-randomizer/blob/6f6224e2/shuffle.py#L1-L300)