import argparse
import base64
import json
import struct
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR   = Path(__file__).parent
STRINGS_DIR  = SCRIPT_DIR / 'Translation' / 'STRINGS'
MON_NAMES_F  = STRINGS_DIR / 'msg_monstername.txt'
SKILL_NAMES_F = STRINGS_DIR / 'msg_skillname.txt'
TOK_NAMES_F  = STRINGS_DIR / 'msg_tokusei.txt'

# ── Nickname codec (via Pro_RE/msgtool character table) ───────────────────────

def _build_nick_codec():
    try:
        sys.path.insert(0, str(SCRIPT_DIR / 'Pro_RE'))
        import msgtool
        table   = msgtool.load_table()
        _decode = msgtool.build_decoder(table)
        _encode = msgtool.build_encoder(table)
        def decode_nick(raw: bytes) -> str:
            return _decode(raw)
        def encode_nick(text: str) -> bytes:
            return _encode(text)
        return decode_nick, encode_nick
    except Exception as e:
        # Fall back to hex if msgtool/arm9 not available
        def decode_nick(raw: bytes) -> str:
            return raw.hex()
        def encode_nick(text: str) -> bytes:
            try:
                return bytes.fromhex(text)
            except ValueError:
                sys.exit(f'msgtool not available and "{text}" is not a hex string.')
        return decode_nick, encode_nick

_decode_nick, _encode_nick = _build_nick_codec()

# ── Save constants ─────────────────────────────────────────────────────────────

MAGIC            = b'SIZ\x00'
COPY2_OFFSET     = 0x7100    # byte offset where the second save copy starts
RECORD_START     = 0x01E8    # first monster record within each copy
RECORD_SIZE      = 0x84
MAX_RECORDS      = 100       # nursery pool: 100 slots total

# Compact party table: 3×u16 species + 3×u8 level for the active party
PARTY_TABLE      = 0x007C

# Pen display order: u8 slot indices, terminated by 0xFF, max 27 entries
ACTIVE_LIST      = 0x01CC

# Party (0..2) then standby (3..5) creation IDs — 6 × u32
TEAM_OFF         = 0x00B4

# Per-record staleness: record+0x14 is a u32 sequential creation ID.
# Non-zero = slot holds a live monster; zero = slot was consumed in synthesis.
RECORD_ID_OFF    = 0x14


# ── Loaders ───────────────────────────────────────────────────────────────────

def _load_lines(path: Path) -> list[str]:
    if path.exists():
        return path.read_text(encoding='utf-8').splitlines()
    return []

def load_string_tables():
    return (
        _load_lines(MON_NAMES_F),
        _load_lines(SKILL_NAMES_F),
        _load_lines(TOK_NAMES_F),
    )

# ── Record parsing ─────────────────────────────────────────────────────────────


def _read_u8(buf, off): return buf[off]
def _read_u16(buf, off): return struct.unpack_from('<H', buf, off)[0]
def _read_u32(buf, off): return struct.unpack_from('<I', buf, off)[0]

def _write_u8(buf, off, v): buf[off] = v & 0xFF
def _write_u16(buf, off, v): struct.pack_into('<H', buf, off, v & 0xFFFF)
def _write_u32(buf, off, v): struct.pack_into('<I', buf, off, v & 0xFFFFFFFF)


def read_record(copy: bytearray, slot: int, mon_names: list, skill_names: list) -> dict | None:
    base = RECORD_START + slot * RECORD_SIZE
    if base + RECORD_SIZE > len(copy):
        return None

    if _read_u32(copy, base + RECORD_ID_OFF) == 0:
        return None  # stale slot (consumed in synthesis)

    species  = _read_u16(copy, base + 0x18)
    if species == 0:
        return None  # truly empty slot

    mon_name = mon_names[species].strip() if 0 < species < len(mon_names) else f'unknown#{species}'

    variant       = _read_u8(copy, base + 0x1A)
    polarity      = _read_u8(copy, base + 0x1B)
    synthesis_plus      = _read_u8(copy, base + 0x1C)
    synthesis_plus_base = _read_u8(copy, base + 0x1E)

    cur_hp = _read_u16(copy, base + 0x20)
    cur_mp = _read_u16(copy, base + 0x22)
    max_hp = _read_u16(copy, base + 0x24)
    max_mp = _read_u16(copy, base + 0x26)

    atk = _read_u16(copy, base + 0x28)
    def_ = _read_u16(copy, base + 0x2A)
    agi = _read_u16(copy, base + 0x2C)
    wis = _read_u16(copy, base + 0x2E)

    level            = _read_u8(copy, base + 0x30)
    equipped_weapon  = _read_u8(copy, base + 0x31)
    tactics          = _read_u8(copy, base + 0x32)
    skill_points     = _read_u16(copy, base + 0x3C)
    exp          = _read_u32(copy, base + 0x34)
    exp_next     = _read_u32(copy, base + 0x38)

    # Lineage: 6 entries, interleaved grandparents
    #   +0x40  parent 1 species
    #   +0x42  parent 2 species
    #   +0x44  gp_p1a  (parent 1's first parent)
    #   +0x46  gp_p2a  (parent 2's first parent)
    #   +0x48  gp_p1b  (parent 1's second parent)
    #   +0x4A  gp_p2b  (parent 2's second parent)
    parent1  = _read_u16(copy, base + 0x40)
    parent2  = _read_u16(copy, base + 0x42)
    gp_p1a   = _read_u16(copy, base + 0x44)
    gp_p2a   = _read_u16(copy, base + 0x46)
    gp_p1b   = _read_u16(copy, base + 0x48)
    gp_p2b   = _read_u16(copy, base + 0x4A)
    # Variant (0=normal, 1=X, 2=XY) for each ancestor, same order as species above
    var_p1   = _read_u8(copy, base + 0x4C)
    var_p2   = _read_u8(copy, base + 0x4D)
    var_gp_p1a = _read_u8(copy, base + 0x4E)
    var_gp_p2a = _read_u8(copy, base + 0x4F)
    var_gp_p1b = _read_u8(copy, base + 0x50)
    var_gp_p2b = _read_u8(copy, base + 0x51)

    def gp_ref(mid, var=0):
        return {'id': mid, 'variant': var}

    # +0x00: 16-byte monster nickname
    # +0x52: 16-byte parent 1 nickname
    # +0x66: 16-byte parent 2 nickname
    nick_field_bytes   = bytearray(copy[base + 0x00: base + 0x00 + 16])
    parent1_nick_field = bytearray(copy[base + 0x52: base + 0x52 + 16])
    parent2_nick_field = bytearray(copy[base + 0x66: base + 0x66 + 16])

    def _decode_field(raw16):
        raw = bytearray()
        for b in raw16:
            if b == 0: break
            raw.append(b)
        try:
            return _decode_nick(bytes(raw))
        except Exception:
            return raw.hex()

    nickname = _decode_field(nick_field_bytes)

    # Skills: up to 5 × (id u8, sp u8) at +0x7A; unused slots are zeroed
    skills = []
    for j in range(5):
        sid = copy[base + 0x7A + j * 2]
        ssp = copy[base + 0x7A + j * 2 + 1]
        sname = skill_names[sid] if 0 < sid < len(skill_names) else ('(none)' if sid == 0 else f'?({sid})')
        skills.append({'id': sid, 'name': sname, 'sp': ssp})

    return {
        'slot': slot,
        'id':   species,
        'name':     mon_name,
        'nickname': nickname,
        'variant':        variant,
        'polarity':       polarity,
        'synthesis_plus': synthesis_plus,
        'synthesis_plus_base': synthesis_plus_base,
        'level':           level,
        'equipped_weapon': equipped_weapon,
        'tactics':         tactics,
        'skill_points':    skill_points,
        'exp':          exp,
        'exp_next': exp_next,
        'cur_hp':   cur_hp,
        'max_hp':   max_hp,
        'cur_mp':   cur_mp,
        'max_mp':   max_mp,
        'atk':      atk,
        'def':      def_,
        'agi':      agi,
        'wis':      wis,
        'lineage': {
            'parent_1': {'id': parent1, 'nickname': _decode_field(parent1_nick_field), 'variant': var_p1},
            'parent_2': {'id': parent2, 'nickname': _decode_field(parent2_nick_field), 'variant': var_p2},
            'gp_1a': gp_ref(gp_p1a, var_gp_p1a),
            'gp_1b': gp_ref(gp_p1b, var_gp_p1b),
            'gp_2a': gp_ref(gp_p2a, var_gp_p2a),
            'gp_2b': gp_ref(gp_p2b, var_gp_p2b),
        },
        'skills':   skills,
    }


def write_record(copy: bytearray, slot: int, rec: dict):
    base = RECORD_START + slot * RECORD_SIZE

    _write_u16(copy, base + 0x18, rec['id'])
    _write_u8(copy, base + 0x1A, rec.get('variant', 0))
    _write_u8(copy, base + 0x1B, rec.get('polarity', 0))
    _write_u8(copy, base + 0x1C, rec.get('synthesis_plus', 0))
    _write_u8(copy, base + 0x1E, rec.get('synthesis_plus_base', 0))

    _write_u16(copy, base + 0x20, rec['cur_hp'])
    _write_u16(copy, base + 0x22, rec['cur_mp'])
    _write_u16(copy, base + 0x24, rec['max_hp'])
    _write_u16(copy, base + 0x26, rec['max_mp'])

    _write_u16(copy, base + 0x28, rec['atk'])
    _write_u16(copy, base + 0x2A, rec['def'])
    _write_u16(copy, base + 0x2C, rec['agi'])
    _write_u16(copy, base + 0x2E, rec['wis'])

    _write_u8 (copy, base + 0x30, rec['level'] & 0xFF)
    _write_u8 (copy, base + 0x31, rec.get('equipped_weapon', 0))
    _write_u8 (copy, base + 0x32, rec.get('tactics', 0))
    _write_u16(copy, base + 0x3C, rec.get('skill_points', 0))
    _write_u32(copy, base + 0x34, rec['exp'])
    _write_u32(copy, base + 0x38, rec['exp_next'])

    lin = rec.get('lineage', {})

    def _lineage_id(key):
        v = lin.get(key, {})
        return v.get('id', 0) if isinstance(v, dict) else int(v)

    def _lineage_var(key):
        v = lin.get(key, {})
        return v.get('variant', 0) if isinstance(v, dict) else 0

    _write_u16(copy, base + 0x40, _lineage_id('parent_1'))
    _write_u16(copy, base + 0x42, _lineage_id('parent_2'))
    _write_u16(copy, base + 0x44, _lineage_id('gp_1a'))
    _write_u16(copy, base + 0x46, _lineage_id('gp_2a'))
    _write_u16(copy, base + 0x48, _lineage_id('gp_1b'))
    _write_u16(copy, base + 0x4A, _lineage_id('gp_2b'))
    _write_u8 (copy, base + 0x4C, _lineage_var('parent_1'))
    _write_u8 (copy, base + 0x4D, _lineage_var('parent_2'))
    _write_u8 (copy, base + 0x4E, _lineage_var('gp_1a'))
    _write_u8 (copy, base + 0x4F, _lineage_var('gp_2a'))
    _write_u8 (copy, base + 0x50, _lineage_var('gp_1b'))
    _write_u8 (copy, base + 0x51, _lineage_var('gp_2b'))

    def _encode_field(text):
        try:
            raw = _encode_nick(text)
        except Exception:
            raw = b''
        return (raw + b'\x00' * 16)[:16]

    copy[base + 0x00: base + 0x10] = _encode_field(rec.get('nickname', ''))
    copy[base + 0x52: base + 0x62] = _encode_field((lin.get('parent_1') or {}).get('nickname', ''))
    copy[base + 0x66: base + 0x76] = _encode_field((lin.get('parent_2') or {}).get('nickname', ''))

    # Skills — write all 5 slots; zero out any beyond what the record contains
    skill_list = rec.get('skills', [])[:5]
    for j in range(5):
        if j < len(skill_list):
            skill = skill_list[j]
            sid = skill.get('id', 0) if isinstance(skill, dict) else int(skill)
            ssp = skill.get('sp', 0) if isinstance(skill, dict) else 0
        else:
            sid, ssp = 0, 0
        copy[base + 0x7A + j * 2]     = sid & 0xFF
        copy[base + 0x7A + j * 2 + 1] = ssp & 0xFF


# ── Compact party table ────────────────────────────────────────────────────────

def read_party_table(copy: bytearray) -> list[tuple[int, int]]:
    """Return [(species, level), ...] for up to 3 party slots."""
    off = PARTY_TABLE
    party = []
    for i in range(3):
        sp = _read_u16(copy, off + i * 2)
        lv = copy[off + 6 + i]
        party.append((sp, lv))
    return party


def update_party_table(copy: bytearray, records: list[dict], party_slots: list[int]):
    """Rewrite the compact party table from the given slot indices (in order)."""
    off = PARTY_TABLE
    for i, slot in enumerate(party_slots[:3]):
        rec = next((r for r in records if r['slot'] == slot), None)
        if rec is None:
            _write_u16(copy, off + i * 2, 0)
            copy[off + 6 + i] = 0
        else:
            sp = rec['species']['id'] if isinstance(rec['species'], dict) else rec['species']
            _write_u16(copy, off + i * 2, sp)
            copy[off + 6 + i] = rec['level'] & 0xFF


# ── Save I/O ──────────────────────────────────────────────────────────────────

def load_save(path: Path) -> bytearray:
    data = bytearray(path.read_bytes())
    if data[:4] != MAGIC:
        sys.exit(f'ERROR: {path} does not start with SIZ\\x00 — not a DQMJ2P save.')
    return data


def extract_copy(data: bytearray, copy_index: int) -> bytearray:
    off = 0 if copy_index == 0 else COPY2_OFFSET
    return bytearray(data[off: off + COPY2_OFFSET])


def patch_copy_into(data: bytearray, copy: bytearray, copy_index: int):
    off = 0 if copy_index == 0 else COPY2_OFFSET
    data[off: off + len(copy)] = copy


# ── Convert save → JSON ────────────────────────────────────────────────────────

RECORD_END = RECORD_START + MAX_RECORDS * RECORD_SIZE


def _copy_to_doc(copy: bytearray) -> dict:
    """Extract header, trailer, and monster records from a save copy into a dict."""
    header  = base64.b64encode(copy[:RECORD_START]).decode()
    trailer = base64.b64encode(copy[RECORD_END:]).decode()
    return {'header': header, 'trailer': trailer}


def _doc_to_copy(doc: dict, records_blob: bytearray) -> bytearray:
    """Reconstruct a save copy from stored header/trailer and a pre-built records blob."""
    header  = base64.b64decode(doc['header'])
    trailer = base64.b64decode(doc['trailer'])
    copy = bytearray(header) + records_blob + bytearray(trailer)
    # Pad or trim to exactly COPY2_OFFSET bytes.
    if len(copy) < COPY2_OFFSET:
        copy += bytearray(COPY2_OFFSET - len(copy))
    return copy[:COPY2_OFFSET]


TEAM_ROLES = ['party_1', 'party_2', 'party_3', 'standby_1', 'standby_2', 'standby_3']


def save_to_json(save_path: Path, out_path: Path):
    mon_names, skill_names, _ = load_string_tables()
    data  = load_save(save_path)
    copy0 = extract_copy(data, 0)

    # Map creation IDs from the team table to roles.
    id_to_role = {}
    for i, role in enumerate(TEAM_ROLES):
        cid = _read_u32(copy0, TEAM_OFF + i * 4)
        if cid:
            id_to_role[cid] = role

    records = []
    for slot in range(MAX_RECORDS):
        rec = read_record(copy0, slot, mon_names, skill_names)
        if rec is None:
            continue
        cid = _read_u32(copy0, RECORD_START + slot * RECORD_SIZE + RECORD_ID_OFF)
        rec['role'] = id_to_role.get(cid, 'pen')
        records.append(rec)

    doc = _copy_to_doc(copy0)
    doc['monsters'] = records

    out_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Wrote {len(records)} monsters to {out_path}')


# ── Convert JSON → save ────────────────────────────────────────────────────────

def json_to_save(json_path: Path, save_path: Path):
    mon_names, skill_names, _ = load_string_tables()
    doc     = json.loads(json_path.read_text(encoding='utf-8'))
    records = doc['monsters']

    # Validate and index records by slot.
    by_slot: dict[int, dict] = {}
    for rec in records:
        slot = rec['slot']
        if not (0 <= slot < MAX_RECORDS):
            print(f'WARNING: slot {slot} out of range, skipping.', file=sys.stderr)
            continue
        by_slot[slot] = rec

    # Reconstruct the save copy, then write records into it.
    copy = _doc_to_copy(doc, bytearray(MAX_RECORDS * RECORD_SIZE))

    next_id = 1
    slot_to_id: dict[int, int] = {}
    for slot in range(MAX_RECORDS):
        base = RECORD_START + slot * RECORD_SIZE
        if slot in by_slot:
            write_record(copy, slot, by_slot[slot])
            _write_u32(copy, base + RECORD_ID_OFF, next_id)
            slot_to_id[slot] = next_id
            next_id += 1
        else:
            copy[base: base + RECORD_SIZE] = bytes(RECORD_SIZE)

    # Rewrite the team layout from role tags.
    role_to_slot = {rec['role']: rec['slot'] for rec in records if rec.get('role') in TEAM_ROLES}
    for i, role in enumerate(TEAM_ROLES):
        slot = role_to_slot.get(role)
        _write_u32(copy, TEAM_OFF + i * 4, slot_to_id.get(slot, 0) if slot is not None else 0)

    # Regenerate the pen slot list in the header.
    pen_slots = sorted(by_slot.keys())
    pen_capacity = RECORD_START - ACTIVE_LIST - 1  # reserve 1 byte for terminator
    pen_bytes = bytes(pen_slots[:pen_capacity]) + b'\xff'
    copy[ACTIVE_LIST: RECORD_START] = pen_bytes + bytes(RECORD_START - ACTIVE_LIST - len(pen_bytes))

    # Recompute checksums.
    # +0x88: additive sum of 0x1C10 u32 words starting at +0x90 (covers all game data)
    data_sum = sum(struct.unpack_from('<I', copy, 0x90 + i * 4)[0] for i in range(0x1C10)) & 0xFFFFFFFF
    struct.pack_into('<I', copy, 0x88, data_sum)
    # +0x8C: additive sum of 0x23 u32 words starting at +0x00 (covers header incl. +0x88)
    hdr_sum = sum(struct.unpack_from('<I', copy, i * 4)[0] for i in range(0x23)) & 0xFFFFFFFF
    struct.pack_into('<I', copy, 0x8C, hdr_sum)

    data = bytearray(b'\xff' * 0x10000)
    data[:COPY2_OFFSET] = copy
    data[COPY2_OFFSET: COPY2_OFFSET * 2] = copy
    save_path.write_bytes(data)
    print(f'Wrote {len(by_slot)} monster records to {save_path}.')


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description='DQMJ2P Save Converter — .sav ↔ .json')
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--to-json',   nargs=2, metavar=('SAV', 'OUTPUT'), help='Convert .sav → JSON')
    mode.add_argument('--from-json', nargs=2, metavar=('JSON', 'OUTPUT'), help='Convert JSON → .sav')

    args = ap.parse_args()

    if args.to_json:
        save_to_json(Path(args.to_json[0]), Path(args.to_json[1]))
    else:
        json_to_save(Path(args.from_json[0]), Path(args.from_json[1]))


if __name__ == '__main__':
    main()
