#!/usr/bin/env python3
"""
DQMJ2P msg_*.binA / message*.binA extract/repack tool.

Subcommands:
  extract  <data_dir> <out_dir>    extract every msg_*.binA / message*.binA in <data_dir>
                                   into UTF-8 .txt files in <out_dir>,
                                   plus MASTER.json mapping txt -> original path.
  repack   <txt_dir> <out_dir>     repack .txt files (using MASTER.json
                                   in <txt_dir>) back to .binA in <out_dir>.

Format
------
Each .txt has one entry per line, UTF-8 encoded.
The very first line is intentionally blank (the file's leading E3 1B sentinel).
Special escapes inside an entry:
    {XX}        single raw byte 0xXX that has no mapped codepoint
    {pNN}       DTE token: prefix p (one of 2,3) and sub-byte NN
                (used for tokens we have not yet reversed)
Newlines themselves are NOT allowed inside an entry.
"""

import json, os, re, struct, sys
from pathlib import Path

# Path to the decompressed arm9 binary. The codepoint table lives inside arm9
# itself, so a full RAM dump is no longer required.
ARM9_FILE = str(Path(__file__).resolve().parent / 'Pro_ARM9.bin')
TABLE_RAM_ADDR = 0x020dbc16
ARM9_BASE      = 0x02000000
PREFIX_BASE = {0xE0: 0xE6, 0xE1: 0x118, 0xE4: 0x2AF}
SEPARATOR = b'\xe3\x1b'
FPK_HEADER_LEN = 0x30


def load_table():
    """Return the 0x800-entry codepoint table (covers all known prefix ranges)."""
    data = open(ARM9_FILE, 'rb').read()
    base_off = TABLE_RAM_ADDR - ARM9_BASE
    n = 0x800
    return list(struct.unpack(f'<{n}H', data[base_off:base_off + n*2]))


def build_decoder(table):
    """Decode one entry's bytes into a UTF-8 string with {…} escapes."""
    def decode(entry: bytes) -> str:
        out = []
        i = 0
        while i < len(entry):
            b = entry[i]
            if b in PREFIX_BASE and i + 1 < len(entry):
                idx = PREFIX_BASE[b] + entry[i+1]
                cp = table[idx] if idx < len(table) else 0
                if cp == 0:
                    out.append(f'{{{b:01x}{entry[i+1]:02x}}}')  # opaque
                else:
                    out.append(chr(cp))
                i += 2
            elif b in (0xE2, 0xE3) and i + 1 < len(entry):
                # unknown DTE prefix — preserve opaque
                out.append(f'{{{b-0xE0}{entry[i+1]:02x}}}')
                i += 2
            else:
                cp = table[b]
                if cp == 0 or cp == 0x021C:  # 0 or junk placeholder
                    out.append(f'{{{b:02x}}}')
                else:
                    out.append(chr(cp))
                i += 1
        return ''.join(out)
    return decode


def build_encoder(table):
    """Build codepoint -> bytes map, then return encoder closure."""
    # 1) single-byte mappings (skip prefix bytes E0..E4 — decoder reads those as prefixes)
    single = {}
    for b in range(0x100):
        if 0xE0 <= b <= 0xE4:
            continue
        cp = table[b]
        if cp and cp != 0x021C and cp not in single:
            single[cp] = bytes([b])

    # 2) prefix-pair mappings (only fill if no single-byte form exists)
    for prefix, base in PREFIX_BASE.items():
        for sub in range(0x100):
            cp = table[base + sub]
            if cp and cp != 0x021C and cp not in single:
                # don't allow sub-byte == 0x1b under prefix E3 (would collide
                # with the entry separator) — we never use E3 anyway here.
                single[cp] = bytes([prefix, sub])

    escape_re = re.compile(r'\{([0-9a-fA-F]+)\}')

    def encode(text: str) -> bytes:
        out = bytearray()
        i = 0
        while i < len(text):
            # escape literal? {hh} or {pNN}
            m = escape_re.match(text, i)
            if m:
                tok = m.group(1)
                if len(tok) == 2:               # raw byte
                    out.append(int(tok, 16))
                elif len(tok) == 3:             # prefix sub-byte: pNN
                    p = int(tok[0], 16)         # 2 or 3
                    nn = int(tok[1:], 16)
                    out.extend([0xE0 + p, nn])
                else:
                    raise ValueError(f'bad escape {{{tok}}} at offset {i}')
                i = m.end()
                continue
            ch = text[i]; cp = ord(ch)
            if cp in single:
                out.extend(single[cp])
            else:
                raise ValueError(
                    f'no encoding for U+{cp:04X} ({ch!r}) in text {text!r}; '
                    f'use a {{XX}} or {{pNN}} escape if you really need this byte.'
                )
            i += 1
        return bytes(out)

    return encode


# ---------- FPK container ----------

def fpk_unwrap(data: bytes) -> tuple[bytes, bytes]:
    """Return (header30, payload). Asserts the standard 0x30-byte FPK layout."""
    assert data[:4] == b'FPK\x00', 'not an FPK file'
    payload_off = struct.unpack('<I', data[0x28:0x2c])[0]
    payload_size = struct.unpack('<I', data[0x2c:0x30])[0]
    assert payload_off == FPK_HEADER_LEN
    return data[:FPK_HEADER_LEN], data[payload_off:payload_off + payload_size]


def fpk_wrap(header30: bytes, payload: bytes) -> bytes:
    """Rebuild an FPK file with an updated payload-size field."""
    new = bytearray(header30)
    struct.pack_into('<I', new, 0x2c, len(payload))
    new.extend(payload)
    # Pad to 4-byte alignment to be safe (matches typical FPK layout)
    while len(new) % 4:
        new.append(0)
    return bytes(new)


# ---------- payload <-> entries ----------

def split_entries(payload: bytes) -> list[bytes]:
    """Split by E3 1B separator. The leading separator yields an empty entry
    we keep as the first list element so the round trip is exact."""
    out, buf, i = [], bytearray(), 0
    while i < len(payload):
        if payload[i:i+2] == SEPARATOR:
            out.append(bytes(buf)); buf = bytearray(); i += 2
        else:
            buf.append(payload[i]); i += 1
    if buf:                       # trailing data without final separator
        out.append(bytes(buf))
    return out


def join_entries(entries: list[bytes]) -> bytes:
    """Inverse of split_entries. With entries[0] always being the leading-empty
    artifact, SEP.join() naturally produces  SEP entry1 SEP entry2 ...  and we
    add a trailing SEP to match the original framing."""
    return SEPARATOR.join(entries) + SEPARATOR


# ---------- driver ----------

def cmd_extract(data_dir, out_dir):
    table = load_table()
    decode = build_decoder(table)
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    master = {}
    for path in sorted(Path(data_dir).iterdir()):
        if path.suffix != '.binA':
            continue
        if not (path.name.startswith('msg_') or path.name.startswith('message')):
            continue
        data = path.read_bytes()
        header, payload = fpk_unwrap(data)
        entries = split_entries(payload)
        txt_name = path.stem + '.txt'
        hdr_name = path.stem + '.fpkhdr'
        # write decoded text
        with open(out_dir / txt_name, 'w', encoding='utf-8') as f:
            for e in entries:
                f.write(decode(e))
                f.write('\n')
        # preserve original 48-byte FPK header verbatim
        (out_dir / hdr_name).write_bytes(header)
        master[txt_name] = {
            'source':     path.name,
            'fpk_header': hdr_name,
            'entry_count': len(entries),
        }
        print(f'  extracted {path.name}: {len(entries)} entries')
    with open(out_dir / 'MASTER.json', 'w', encoding='utf-8') as f:
        json.dump(master, f, indent=2, ensure_ascii=False)
    print(f'\nwrote MASTER.json with {len(master)} files in {out_dir}')


def cmd_repack(txt_dir, out_dir):
    table = load_table()
    encode = build_encoder(table)
    txt_dir = Path(txt_dir); out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    master = json.loads((txt_dir / 'MASTER.json').read_text(encoding='utf-8'))
    for txt_name, info in master.items():
        text  = (txt_dir / txt_name).read_text(encoding='utf-8')
        # strip ONE optional trailing newline (the file usually ends with \n)
        if text.endswith('\n'): text = text[:-1]
        lines = text.split('\n')
        entries = [encode(line) for line in lines]
        payload = join_entries(entries)
        header  = (txt_dir / info['fpk_header']).read_bytes()
        out_path = out_dir / info['source']
        out_path.write_bytes(fpk_wrap(header, payload))
        print(f'  repacked {info["source"]}: {len(entries)} entries, '
              f'{len(payload)} bytes payload')


def main():
    if len(sys.argv) < 4:
        print(__doc__); sys.exit(2)
    cmd, a, b = sys.argv[1], sys.argv[2], sys.argv[3]
    if cmd == 'extract':
        cmd_extract(a, b)
    elif cmd == 'repack':
        cmd_repack(a, b)
    else:
        print(__doc__); sys.exit(2)


if __name__ == '__main__':
    main()
