#!/usr/bin/env python3
"""
DQMJ2P Synthesis CSV Converter
Converts combination tables between binary and CSV formats with monster names.

Two table formats (all use 0xFFFF in first field as terminator):
  kind      (default) 6-byte records: result | p1 | p2
  4g                  10-byte records: result | gp1 | gp2 | gp3 | gp4  (--type 4g)

CSV Format (unified 5 columns):
    monster1|id, monster2|id, monster3|id, monster4|id, result|id

    - For kind/affection tables: columns 3-4 empty
    - For 4G tables: all 5 slots used
    - Monsters as "Name|ID" to handle duplicate names

Usage:
    python synth_csv.py --in <input> --out <output> [--type 4g|affection]

    Export examples:
        python synth_csv.py --in ./data/CombinationKindTbl.bin --out ./kind.csv
        python synth_csv.py --in ./data/CombinationAffectionTbl.bin --out ./affection.csv
        python synth_csv.py --in ./data/Combination4GTbl.bin --out ./4g.csv --type 4g

    Import examples:
        python synth_csv.py --in ./kind.csv --out ./CombinationKindTbl.bin
        python synth_csv.py --in ./affection.csv --out ./CombinationAffectionTbl.bin
        python synth_csv.py --in ./4g.csv --out ./Combination4GTbl.bin --type 4g
"""

import argparse
import csv
import struct
import sys
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
DATA_DIR   = SCRIPT_DIR.parent / 'Pro_ROM' / 'data_dir'


# ── data loaders ──────────────────────────────────────────────────────────────

def load_names() -> list[str]:
    for candidate in [
        SCRIPT_DIR / '_names_cache.txt',
        Path('/tmp/msg_out/msg_monstername.txt'),
    ]:
        if candidate.exists():
            return candidate.read_text(encoding='utf-8').splitlines()

    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        import msgtool  # type: ignore
        lines = msgtool.extract_lines((DATA_DIR / 'msg_monstername.binA').read_bytes())
        (SCRIPT_DIR / '_names_cache.txt').write_text('\n'.join(lines), encoding='utf-8')
        return lines
    except Exception as e:
        print(f"Warning: Could not load names: {e}", file=sys.stderr)
        return []


def read_binary_table(filepath: Path, table_type: str) -> list[tuple]:
    """Read binary table and return records in CSV order (m1, m2, m3, m4, result)."""
    data = filepath.read_bytes()
    records = []

    if table_type == '4g':
        # Binary: (result, gp1, gp2, gp3, gp4) × 10 bytes
        for offset in range(0, len(data) - 9, 10):
            vals = struct.unpack_from('<5H', data, offset)
            if vals[0] == 0xFFFF:
                break
            records.append((vals[1], vals[2], vals[3], vals[4], vals[0]))
    else:
        # kind (default): Binary: (result, p1, p2) × 6 bytes
        for offset in range(0, len(data) - 5, 6):
            vals = struct.unpack_from('<3H', data, offset)
            if vals[0] == 0xFFFF:
                break
            records.append((vals[1], vals[2], 0, 0, vals[0]))

    return records


def save_binary_table(filepath: Path, table_type: str, records: list[tuple]) -> None:
    """Save records to binary format with 0xFFFF terminator."""
    data = bytearray()

    if table_type == '4g':
        # CSV: (gp1, gp2, gp3, gp4, result) → Binary: (result, gp1, gp2, gp3, gp4)
        for gp1, gp2, gp3, gp4, result in records:
            data.extend(struct.pack('<5H', result, gp1, gp2, gp3, gp4))
        data.extend(struct.pack('<5H', 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF))
    else:
        # kind (default): CSV: (p1, p2, _, _, result) → Binary: (result, p1, p2)
        for p1, p2, _, _, result in records:
            data.extend(struct.pack('<3H', result, p1, p2))
        data.extend(struct.pack('<3H', 0xFFFF, 0xFFFF, 0xFFFF))

    filepath.write_bytes(data)


# ── CSV conversion ────────────────────────────────────────────────────────────

def export_to_csv(input_path: Path, output_path: Path, names: list[str],
                  table_type: str) -> None:
    records = read_binary_table(input_path, table_type)

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['monster1', 'monster2', 'monster3', 'monster4', 'result'])
        for record in records:
            writer.writerow([format_monster(names, record[i]) for i in range(5)])

    print(f"Exported {len(records)} records ({table_type}) → {output_path}")


def import_from_csv(input_path: Path, output_path: Path, names: list[str],
                    table_type: str) -> None:
    name_to_ids: dict[str, list[int]] = {}
    for idx, name in enumerate(names):
        if name:
            name_lower = name.lower()
            if name_lower not in name_to_ids:
                name_to_ids[name_lower] = []
            name_to_ids[name_lower].append(idx)

    records = []
    errors = []

    with open(input_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)  # skip header

        for row_num, row in enumerate(reader, start=2):
            while len(row) < 5:
                row.append('')

            if all(cell.strip() == '' for cell in row):
                continue

            try:
                monster_ids = []
                for i in range(5):
                    cell = row[i].strip()
                    if cell == '':
                        monster_ids.append(0)
                    else:
                        monster_ids.append(
                            parse_monster(names, name_to_ids, cell, f"Row {row_num}, Col {i+1}")
                        )
                records.append(tuple(monster_ids))
            except ValueError as e:
                errors.append(str(e))

    if errors:
        print("Import errors found:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        sys.exit(1)

    save_binary_table(output_path, table_type, records)
    print(f"Imported {len(records)} records ({table_type}) → {output_path}")


def format_monster(names: list[str], monster_id: int) -> str:
    if monster_id == 0:
        return ''
    if 0 < monster_id < len(names) and names[monster_id]:
        return f"{names[monster_id]}|{monster_id}"
    return str(monster_id)


def parse_monster(names: list[str], name_to_ids: dict[str, list[int]],
                  cell: str, context: str) -> int:
    cell = cell.strip()

    if '|' in cell:
        parts = cell.rsplit('|', 1)
        if len(parts) != 2:
            raise ValueError(f"{context}: Invalid format '{cell}' (expected 'name|id')")

        name_part, id_part = parts
        try:
            provided_id = int(id_part)
        except ValueError:
            raise ValueError(f"{context}: Invalid ID '{id_part}' in '{cell}'")

        if provided_id < 0 or provided_id >= len(names):
            raise ValueError(f"{context}: ID {provided_id} out of range (0-{len(names)-1})")

        if provided_id == 0:
            return 0

        actual_name = names[provided_id] if provided_id < len(names) else ''
        if not actual_name:
            raise ValueError(f"{context}: ID {provided_id} has no name in table")
        if actual_name.lower() != name_part.lower():
            raise ValueError(f"{context}: Name '{name_part}' doesn't match ID {provided_id} "
                             f"(actual: '{actual_name}')")
        return provided_id
    else:
        try:
            monster_id = int(cell)
        except ValueError:
            raise ValueError(f"{context}: Invalid ID '{cell}'")

        if monster_id < 0 or monster_id >= len(names):
            raise ValueError(f"{context}: ID {monster_id} out of range (0-{len(names)-1})")

        return monster_id


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description='DQMJ2P Synthesis CSV Converter',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    ap.add_argument('--in', dest='input', required=True, metavar='FILE',
                    help='Input file (binary .bin or CSV .csv)')
    ap.add_argument('--out', dest='output', required=True, metavar='FILE',
                    help='Output file (CSV .csv or binary .bin)')
    ap.add_argument('--type', choices=['kind', '4g'], default=None,
                    help='Table type: 4g for grandparent tables (default: kind — 6-byte result|p1|p2)')

    args = ap.parse_args()

    input_path  = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    names = load_names()
    if not names:
        print("Warning: No monster names loaded. Only numeric IDs will work.", file=sys.stderr)
        names = []

    table_type = args.type or 'kind'

    if input_path.suffix == '.bin' and output_path.suffix == '.csv':
        print(f"Exporting: {input_path} → {output_path}  (type={table_type})")
        export_to_csv(input_path, output_path, names, table_type)
    elif input_path.suffix == '.csv' and output_path.suffix == '.bin':
        print(f"Importing: {input_path} → {output_path}  (type={table_type})")
        if output_path.exists():
            print(f"Warning: Output file will be overwritten: {output_path}", file=sys.stderr)
        import_from_csv(input_path, output_path, names, table_type)
    else:
        print(f"Error: Need .bin ↔ .csv conversion. "
              f"Got: {input_path.suffix} → {output_path.suffix}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
