#!/usr/bin/env python3
"""
DQMJ2P script flat-text disassembler / assembler.

One instruction per line. Jump targets and ENTRY-table values are emitted as
symbolic labels (`L_<hex>`); the assembler resolves each label to its current
PC at compile time, so SAY/SETNAME body edits don't break jumps. Strings are
decoded inline; non-text bytes appear as `{HHH}` (3 hex = E-prefix DTE) or
`{HH}` (2 hex = single byte).

Usage:
    storytool.py disasm <file_or_dir> <out_dir>
    storytool.py asm    <txt_dir>     <out_dir> [fpk_name]

Output (one .txt per inner ASH blob):

    ASH const=0x64 hash=0x00109e5b
    ENTRY 250 L_0
    ENTRY 1 L_50

    L_0:
    JMP_ABS 0xc L_c
    L_c:
    SYS_11 0x14 64656d6f3133302e706f7300
    STORE 0x18 0x1 0x0 0x2 0x435e0000
    SAY "{308}「なんで…{315} バトル…{31B}"
    RET
"""

import base64, json, re, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from msgtool import load_table
from ash_codec import decompress_ash, compress_ash


# ---- DTE prefix table & script encoder (inlined from old scripttool.py) ---
# In script bytecode, bytes 0xE0..0xFF are reserved for opcodes / control.
# Voiced kana that have a single-byte slot in 0xE7..0xFF MUST be emitted via
# the E0/E1/E4 prefix tables instead, or the interpreter dispatches them as
# opcodes and crashes.
PREFIX_BASE = {0xE0: 0xE6, 0xE1: 0x118, 0xE4: 0x2AF}

def build_script_encoder(table):
    single = {}
    for b in range(0xE0):
        cp = table[b]
        if cp and cp != 0x021C and cp not in single:
            single[cp] = bytes([b])
    # Build prefix forms. When a codepoint is reachable from multiple prefixes,
    # prefer the one with the largest base (E4 > E1 > E0).
    for prefix, base in sorted(PREFIX_BASE.items(), key=lambda kv: kv[1]):
        for sub in range(0x100):
            cp = table[base + sub]
            if cp and cp != 0x021C and cp not in single:
                single[cp] = bytes([prefix, sub])
    for prefix, base in sorted(PREFIX_BASE.items(), key=lambda kv: -kv[1]):
        for sub in range(0x100):
            cp = table[base + sub]
            if cp and cp != 0x021C:
                cur = single.get(cp)
                if cur is None or (len(cur) == 2 and cur[0] < prefix):
                    single[cp] = bytes([prefix, sub])
    # Single-byte (0x00..0xDF) forms are always cheapest — never overwrite them.
    for b in range(0xE0):
        cp = table[b]
        if cp and cp != 0x021C:
            single[cp] = bytes([b])

    escape_re = re.compile(r'\{([0-9a-fA-F]+)\}')
    def encode(text: str) -> bytes:
        out = bytearray(); i = 0
        while i < len(text):
            m = escape_re.match(text, i)
            if m:
                tok = m.group(1)
                if len(tok) == 2:
                    out.append(int(tok, 16))
                elif len(tok) == 3:
                    p = int(tok[0], 16); nn = int(tok[1:], 16)
                    out.extend([0xE0 + p, nn])
                else:
                    raise ValueError(f'bad escape {{{tok}}} at offset {i}')
                i = m.end(); continue
            cp = ord(text[i])
            if cp not in single:
                raise ValueError(f'no encoding for U+{cp:04X} ({text[i]!r}) in {text!r}')
            out.extend(single[cp]); i += 1
        return bytes(out)
    return encode


# ---- FPK archive (multi-file, 40-byte directory entries) -----------------
FPK_ENTRY = 40

def fpk_parse(data: bytes):
    assert data[:4] == b'FPK\x00'
    n = struct.unpack('<I', data[4:8])[0]
    entries = []
    for i in range(n):
        base = 8 + i * FPK_ENTRY
        name = data[base:base+32].split(b'\x00', 1)[0].decode('latin1', 'replace')
        off, size = struct.unpack('<II', data[base+32:base+40])
        entries.append((name, off, size))
    return entries

def fpk_build(entries):
    """Build a multi-file FPK from (name, blob) pairs."""
    n = len(entries)
    header_size = 8 + n * FPK_ENTRY
    data_off = (header_size + 3) & ~3                  # 4-byte align data start
    out = bytearray()
    out.extend(b'FPK\x00')
    out.extend(struct.pack('<I', n))
    payload = bytearray()
    cur = data_off
    for name, blob in entries:
        nm = name.encode('ascii', 'replace')[:32].ljust(32, b'\x00')
        out.extend(nm)
        out.extend(struct.pack('<II', cur, len(blob)))
        payload.extend(blob)
        cur += len(blob)
        while cur & 3:                                 # 4-byte align between entries
            payload.append(0); cur += 1
    while len(out) < data_off: out.append(0)           # pad header to data_off
    out.extend(payload)
    return bytes(out)


# ---- opcode catalogue (see OPCODES.md) -----------------------------------
# (mnemonic, total_size_bytes, n_args)
OPCODES = {
    0x400: ('JMP_REL',    8, 1),
    0x401: ('NOP_01',     4, 0),
    0x402: ('RET',        4, 0),
    0x403: ('NOP_03',     4, 0),
    0x404: ('NOP_04',     4, 0),
    0x405: ('NOP_05',     4, 0),
    0x406: ('NOP_06',     4, 0),
    0x407: ('NOP_07',     4, 0),
    0x408: ('NOP_08',     4, 0),
    0x409: ('CALL_REL',  12, 2),
    0x40A: ('SPAWN',     12, 2),
    0x40B: ('WAIT',      16, 3),
    0x40C: ('JMP_ABS',   12, 2),
    0x40D: ('JMP_IF',    12, 2),
    0x40E: ('JMP_IFNOT', 12, 2),
    0x40F: ('CMP_EQ',    24, 5),
    0x410: ('CMP_NE',    24, 5),
    0x411: ('CMP_GT',    24, 5),
    0x412: ('CMP_LT',    24, 5),
    0x413: ('CMP_GE',    24, 5),
    0x414: ('CMP_LE',    24, 5),
    0x415: ('STORE',     24, 5),
    0x416: ('MATH_ADD',  32, 7),
    0x417: ('MATH_SUB',  32, 7),
    0x418: ('MATH_MUL',  32, 7),
    0x419: ('MATH_DIV',  32, 7),
    0x41A: ('MATH_MOD',  32, 7),
    0x41B: ('BIT_AND',   32, 7),
    0x41C: ('BIT_OR',    32, 7),
    0x41D: ('BIT_XOR',   32, 7),
}
OPCODE_BY_MNEM = {v[0]: (k, v[1], v[2]) for k, v in OPCODES.items()}

SYSCALL_HI         = 0x3FF        # anything below the main opcode range (0x400+)
SAY_OPCODE         = 0x47
SETNAME_OPCODE     = 0x87
TEXT_SYSCALLS = {SAY_OPCODE: 'SAY', SETNAME_OPCODE: 'SETNAME'}
EMPTY_CELL         = 0xFFFFFFFF
ENTRY_TABLE_OFFSET = 4
ENTRY_TABLE_LEN    = 0x1000              # 1024 cells × 4 bytes
BYTECODE_OFFSET    = ENTRY_TABLE_OFFSET + ENTRY_TABLE_LEN

def _u32(buf, off): return struct.unpack('<I', buf[off:off+4])[0]


# ---- text decoder / encoder ---------------------------------------------
# A SAY body is a stream of:
#   - DTE-encoded text (single byte 0x00..0xDF that maps to a codepoint, or
#     two-byte E0/E1/E4 + sub forms)
#   - control pairs E3 XX or 1F XX
#   - trailing zero pad to 4-byte alignment
# We inline everything into one string with {HHH} or {HH} escapes.

# Named tokens for common control sequences. Encoder/decoder check these
# before falling back to opaque {HHH}/{HH} hex escapes.
#   - parameterless: 2-byte sequence -> single named token
#   - parameterized: name + value -> 2 byte prefix + 1 byte param
NAMED_CTRL = {
    b'\xE3\x03': '{VOICE=03}',
    b'\xE3\x07': '{VOICE=07}',
    b'\xE3\x08': '{VOICE=08}',
    b'\xE3\x09': '{VOICE=09}',
    b'\xE3\x0C': '{PAGE}',
    b'\xE3\x0F': '{NAME}',
    b'\xE3\x12': '{WAIT}',     # mid-SAY wait-for-input (paired with {CLEAR})
    b'\xE3\x14': '{CLEAR}',    # clear visible text + continue same SAY
    b'\xE3\x15': '{BREAK}',
    b'\xE3\x1B': '{END}',
}
NAMED_CTRL_R = {v: k for k, v in NAMED_CTRL.items()}
COLOR_PREFIX = b'\xE3\x1C'        # 3-byte total: E3 1C XX  ->  {COLOR=N}


def _decode_say_body(body: bytes, table) -> str:
    """Decode a SAY/SETNAME body. Trailing zero bytes (the engine's required
    4-byte alignment padding) are stripped silently — the assembler restores
    them automatically. A trailing {ENDLINE} (E3 1B) is also stripped for
    readability — the assembler unconditionally appends it."""
    end = len(body)
    while end > 0 and body[end-1] == 0:
        end -= 1
    if end >= 2 and body[end-2:end] == b'\xE3\x1B':
        end -= 2
    out = []
    i = 0
    while i < end:
        b = body[i]
        # COLOR takes a parameter byte
        if body[i:i+2] == COLOR_PREFIX and i+2 < end:
            out.append(f'{{COLOR={body[i+2]}}}'); i += 3; continue
        # named parameterless 2-byte controls
        if body[i:i+2] in NAMED_CTRL:
            out.append(NAMED_CTRL[body[i:i+2]]); i += 2; continue
        if b in (0xE3, 0x1F) and i+1 < end:
            out.append(f'{{{b:02X}{body[i+1]:02X}}}'); i += 2; continue
        if b in PREFIX_BASE and i+1 < end:
            cp = table[PREFIX_BASE[b] + body[i+1]]
            if cp not in (0, 0x021C):
                out.append(chr(cp)); i += 2; continue
            out.append(f'{{{b-0xE0:01X}{body[i+1]:02X}}}'); i += 2; continue
        if b == 0xE2 and i+1 < end:
            out.append(f'{{{b-0xE0:01X}{body[i+1]:02X}}}'); i += 2; continue
        cp = table[b]
        if cp not in (0, 0x021C):
            out.append(chr(cp)); i += 1; continue
        out.append(f'{{{b:02X}}}'); i += 1
    return ''.join(out)


_ESCAPE_RE = re.compile(r'\{([0-9a-fA-F]+)\}')
_NAMED_RE  = re.compile(r'\{([A-Z]+)(?:=(\d+))?\}')

def _encode_say_text(text: str, encode) -> bytes:
    """Inverse of _decode_say_body for the body bytes only (no pad).
    {HH}  -> single byte
    {HHH} -> DTE: byte (0xE0 | hi-nibble), low byte
    """
    out = bytearray(); i = 0
    while i < len(text):
        # named tokens first ({NEWLINE}, {COLOR=1}, ...) — they share { with hex
        m_n = _NAMED_RE.match(text, i)
        if m_n:
            name, val = m_n.group(1), m_n.group(2)
            tok = f'{{{name}}}' if val is None else f'{{{name}={val}}}'
            if name == 'COLOR':
                if val is None:
                    raise ValueError('{COLOR=N} requires a value')
                out.extend(COLOR_PREFIX); out.append(int(val) & 0xFF)
                i = m_n.end(); continue
            if tok in NAMED_CTRL_R:
                out.extend(NAMED_CTRL_R[tok]); i = m_n.end(); continue
            raise ValueError(f'unknown named token: {tok}')
        m = _ESCAPE_RE.match(text, i)
        if m:
            tok = m.group(1)
            if len(tok) == 2:
                out.append(int(tok, 16))
            elif len(tok) == 3:
                p = int(tok[0], 16); nn = int(tok[1:], 16)
                out.extend([0xE0 + p, nn])
            elif len(tok) == 4:
                # full 2-byte literal pair, useful for E3XX / 1FXX terminators
                out.append(int(tok[0:2], 16)); out.append(int(tok[2:4], 16))
            else:
                raise ValueError(f'bad escape {{{tok}}}')
            i = m.end(); continue
        # plain character — encode via DTE encoder. If the next char is '{'
        # but neither escape regex matched, the brace is malformed (typo —
        # missing '}', wrong tag name, etc.). Raise loudly with context so the
        # user can fix it instead of looping forever.
        if text[i] == '{':
            ctx = text[max(0,i-15):i+30]
            raise ValueError(
                f'unparseable escape at offset {i} in SAY/SETNAME body: '
                f'context …{ctx!r}… (likely a missing "}}" or unknown token)')
        run = []
        while i < len(text) and text[i] != '{':
            run.append(text[i]); i += 1
        if run:
            out.extend(encode(''.join(run)))
    return bytes(out)


# ---- linear disassembler ------------------------------------------------

# Mnemonic -> arg index whose value is an absolute PC. These get rewritten as
# labels at disasm time and resolved by the assembler.
ABS_PC_ARG = {'JMP_ABS': 1, 'JMP_IF': 1, 'JMP_IFNOT': 1, 'SPAWN': 1,
              'CALL_REL': 1}      # name is misleading — arg-1 is absolute, per
                                  # the descriptor table at 0x020d96b4 and the
                                  # arm9 dispatcher.
# Mnemonic -> arg index whose value is a signed offset relative to the
# instruction's own PC (target = pc + offset).
REL_PC_ARG = {'JMP_REL': 0}


def _label(pc: int) -> str:
    return f'L_{pc & 0xFFFFFFFF:x}'


def disasm_blob(decompressed: bytes, table) -> tuple[list, dict]:
    if decompressed[:4] != b'SCR\x00':
        raise ValueError('missing SCR magic in decompressed blob')

    entries_raw = {}
    for idx in range(1024):
        v = _u32(decompressed, ENTRY_TABLE_OFFSET + idx*4)
        if v != EMPTY_CELL and not (v & 0x80000000):
            entries_raw[idx] = v

    bc = decompressed[BYTECODE_OFFSET:]
    n = len(bc)
    raw = []                                               # (mnem, pc, args)
    pc = 0
    while pc + 4 <= n:
        op = struct.unpack('<I', bc[pc:pc+4])[0]
        if op in OPCODES:
            mnem, size, nargs = OPCODES[op]
            if pc + size > n:
                raw.append(('DATA', pc, [op])); pc += 4; continue
            args = [struct.unpack('<I', bc[pc+4+i*4:pc+8+i*4])[0]
                    for i in range(nargs)]
            raw.append((mnem, pc, args))
            pc += size
            continue
        # syscall? op=0 isn't a real syscall; non-text syscalls have small
        # advance (every one observed in the wild is 0x8 or 0x14). Text
        # syscalls (SAY/SETNAME) are the only ones with variable-length bodies,
        # so allow them a higher cap.
        if 1 <= op <= SYSCALL_HI and pc + 8 <= n:
            advance = struct.unpack('<I', bc[pc+4:pc+8])[0]
            adv_cap = 0x400 if op in TEXT_SYSCALLS else 0x100
            if 8 <= advance <= adv_cap and advance % 4 == 0 and pc + advance <= n:
                body = bc[pc+8:pc+advance]
                if op in TEXT_SYSCALLS:
                    text = _decode_say_body(body, table)
                    raw.append((TEXT_SYSCALLS[op], pc, [text]))
                else:
                    raw.append((f'SYS_{op:02X}', pc, [advance, body.hex()]))
                pc += advance
                continue
        raw.append(('DATA', pc, [op]))
        pc += 4

    # Collect label sites: every PC referenced by an absolute or relative jump
    # arg, plus every non-empty ENTRY value.
    label_sites = set(entries_raw.values())
    for mnem, ipc, args in raw:
        if mnem in ABS_PC_ARG:
            label_sites.add(args[ABS_PC_ARG[mnem]] & 0xFFFFFFFF)
        elif mnem in REL_PC_ARG:
            off = args[REL_PC_ARG[mnem]]
            if off & 0x80000000: off -= 0x100000000
            label_sites.add((ipc + off) & 0xFFFFFFFF)

    # Every label site must be an instruction boundary — otherwise the script
    # has been misdecoded. With the tightened syscall heuristic this should
    # always hold; if it ever fails we want a hard error, not silent breakage.
    # One legitimate exception: a jump target equal to len(bc) (one past the
    # last instruction) is a "halt" convention seen in the wild (e.g. d145).
    # We register a sentinel index len(raw) so those labels can ride along
    # as trailing labels emitted after the last instruction.
    pc_to_idx = {ipc: i for i, (_, ipc, _) in enumerate(raw)}
    end_pc = n
    pc_to_idx[end_pc] = len(raw)
    for site in label_sites:
        if site not in pc_to_idx:
            raise ValueError(f'label site 0x{site:x} not on an instruction '
                             f'boundary — disasm misdecoded the bytecode')

    # Build symbolic instrs: rewrite jump args as label strings. Each instr is
    # (mnem, args, declared_labels) where declared_labels is the list of label
    # names whose target is this instruction.
    declared_at = {i: [] for i in range(len(raw) + 1)}
    for site in sorted(label_sites):
        declared_at[pc_to_idx[site]].append(_label(site))

    instrs = []
    for i, (mnem, ipc, args) in enumerate(raw):
        sym_args = list(args)
        if mnem in ABS_PC_ARG:
            ai = ABS_PC_ARG[mnem]
            sym_args[ai] = _label(args[ai] & 0xFFFFFFFF)
        elif mnem in REL_PC_ARG:
            ai = REL_PC_ARG[mnem]
            off = args[ai]
            if off & 0x80000000: off -= 0x100000000
            sym_args[ai] = _label((ipc + off) & 0xFFFFFFFF)
        instrs.append((mnem, sym_args, declared_at[i]))

    entries = {idx: _label(v) for idx, v in entries_raw.items()}
    trailing_labels = declared_at[len(raw)]
    return instrs, entries, trailing_labels


# ---- text emitter -------------------------------------------------------

def _quote(s: str) -> str:
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

def _unquote(s: str) -> str:
    if not (s.startswith('"') and s.endswith('"')):
        raise ValueError(f'unquoted: {s!r}')
    inner = s[1:-1]
    out = []; i = 0
    while i < len(inner):
        if inner[i] == '\\' and i+1 < len(inner):
            c = inner[i+1]
            out.append({'n':'\n','t':'\t','"':'"','\\':'\\'}.get(c, c))
            i += 2
        else:
            out.append(inner[i]); i += 1
    return ''.join(out)


def _arg_str(a) -> str:
    return a if isinstance(a, str) else f'0x{a:x}'


def _emit_instr(mnem, args) -> str:
    if mnem in ('SAY', 'SETNAME'):
        text, = args
        return f'{mnem} {_quote(text)}'
    if mnem.startswith('SYS_'):
        advance, hex_body = args
        return f'{mnem} 0x{advance:x} {hex_body}'
    if mnem == 'DATA':
        return f'DATA 0x{args[0]:08x}'
    return ' '.join([mnem] + [_arg_str(a) for a in args])


def emit_text(instrs, entries, ash_const, ash_hash, trailing_labels=()) -> str:
    lines = [f'ASH const=0x{ash_const:x} hash=0x{ash_hash:x}']
    for idx in sorted(entries):
        lines.append(f'ENTRY {idx} {entries[idx]}')
    lines.append('')
    for mnem, args, declared in instrs:
        for lbl in declared:
            lines.append(f'{lbl}:')
        lines.append(_emit_instr(mnem, args))
    for lbl in trailing_labels:
        lines.append(f'{lbl}:')
    return '\n'.join(lines) + '\n'


# ---- text parser + assembler --------------------------------------------

_SAY_RE = re.compile(r'^(SAY|SETNAME)\s+(".*?")(?:\s+pad=\d+)?\s*$')
_TEXT_OPCODE_BY_MNEM = {'SAY': SAY_OPCODE, 'SETNAME': SETNAME_OPCODE}
_LABEL_DECL_RE = re.compile(r'^(L_[0-9a-fA-F]+):$')
_LABEL_REF_RE  = re.compile(r'^L_[0-9a-fA-F]+$')


def _parse_arg(tok: str):
    return tok if _LABEL_REF_RE.match(tok) else int(tok, 0)


def parse_text(text: str):
    ash_const, ash_hash = 0x64, 0
    entries = {}
    instrs = []
    pending = []                                           # label decls awaiting next instr
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(';') or line.startswith('#'): continue
        if line.startswith('ASH'):
            for kv in line.split()[1:]:
                k,_,v = kv.partition('=')
                if k == 'const': ash_const = int(v, 0)
                elif k == 'hash': ash_hash = int(v, 0)
            continue
        if line.startswith('ENTRY'):
            _, idx, lbl = line.split()
            if not _LABEL_REF_RE.match(lbl):
                raise ValueError(f'ENTRY value must be a label: {line!r}')
            entries[int(idx, 0)] = lbl
            continue
        m = _LABEL_DECL_RE.match(line)
        if m:
            pending.append(m.group(1)); continue
        if line.startswith('SAY') or line.startswith('SETNAME'):
            m = _SAY_RE.match(line)
            if not m: raise ValueError(f'bad text-syscall line: {line!r}')
            mnem = m.group(1); text_lit = _unquote(m.group(2))
            instrs.append((mnem, [text_lit], pending)); pending = []; continue
        if line.startswith('DATA'):
            _, v = line.split(maxsplit=1)
            instrs.append(('DATA', [int(v, 0)], pending)); pending = []; continue
        if line.startswith('SYS_'):
            parts = line.split(maxsplit=2)
            mnem = parts[0]; advance = int(parts[1], 0)
            hex_body = parts[2] if len(parts) > 2 else ''
            instrs.append((mnem, [advance, hex_body], pending)); pending = []; continue
        parts = line.split()
        mnem = parts[0]
        if mnem not in OPCODE_BY_MNEM:
            raise ValueError(f'unknown opcode: {line!r}')
        args = [_parse_arg(p) for p in parts[1:]]
        instrs.append((mnem, args, pending)); pending = []
    # Labels left over after the last instruction are trailing labels that
    # mark one-past-end (the "halt" convention). The assembler resolves them
    # to the final bytecode length.
    trailing_labels = pending
    return ash_const, ash_hash, entries, instrs, trailing_labels


def _instr_size(mnem, args, encode):
    """Bytes the instruction will occupy. For SAY/SETNAME, also returns the
    encoded body so we don't encode it twice."""
    if mnem in ('SAY', 'SETNAME'):
        body = _encode_say_text(args[0], encode)
        # Implicit {ENDLINE} terminator: disasm strips it, asm restores it.
        if not body.endswith(b'\xE3\x1B'):
            body += b'\xE3\x1B'
        adv = 8 + len(body)
        if adv % 4: adv = (adv + 3) & ~3
        return adv, body
    if mnem.startswith('SYS_'):
        return args[0], None
    if mnem == 'DATA':
        return 4, None
    return OPCODE_BY_MNEM[mnem][1], None


def assemble(ash_const, ash_hash, entries, instrs, table, trailing_labels=()) -> bytes:
    encode = build_script_encoder(table)

    # Pass 1: lay out, assigning each declared label its current PC.
    label_pc = {}
    new_pcs = []
    body_cache = {}
    cur = 0
    for i, (mnem, args, declared) in enumerate(instrs):
        for lbl in declared:
            if lbl in label_pc:
                raise ValueError(f'duplicate label {lbl!r}')
            label_pc[lbl] = cur
        new_pcs.append(cur)
        sz, body = _instr_size(mnem, args, encode)
        if body is not None:
            body_cache[i] = body
        cur += sz
    for lbl in trailing_labels:
        if lbl in label_pc:
            raise ValueError(f'duplicate label {lbl!r}')
        label_pc[lbl] = cur

    def resolve(a, this_pc=None, relative=False):
        if isinstance(a, str):
            target = label_pc.get(a)
            if target is None:
                raise ValueError(f'undefined label {a!r}')
            return ((target - this_pc) if relative else target) & 0xFFFFFFFF
        return a & 0xFFFFFFFF

    # Pass 2: emit bytecode, resolving label references.
    bc = bytearray()
    for i, (mnem, args, _) in enumerate(instrs):
        new_pc = new_pcs[i]
        if mnem in ('SAY', 'SETNAME'):
            body = body_cache[i]
            advance = 8 + len(body)
            if advance % 4: advance = (advance + 3) & ~3
            bc.extend(struct.pack('<I', _TEXT_OPCODE_BY_MNEM[mnem]))
            bc.extend(struct.pack('<I', advance))
            bc.extend(body)
            bc.extend(b'\x00' * (advance - 8 - len(body)))
            continue
        if mnem.startswith('SYS_'):
            opcode = int(mnem[4:], 16)
            advance, hex_body = args
            raw = bytes.fromhex(hex_body) if hex_body else b''
            bc.extend(struct.pack('<I', opcode))
            bc.extend(struct.pack('<I', advance))
            bc.extend(raw)
            short = advance - 8 - len(raw)
            if short > 0: bc.extend(b'\x00' * short)
            continue
        if mnem == 'DATA':
            bc.extend(struct.pack('<I', args[0] & 0xFFFFFFFF))
            continue
        opcode, size, nargs = OPCODE_BY_MNEM[mnem]
        if len(args) != nargs:
            raise ValueError(f'{mnem}: expected {nargs} args, got {len(args)}')
        rel_idx = REL_PC_ARG.get(mnem)
        bc.extend(struct.pack('<I', opcode))
        for ai, a in enumerate(args):
            bc.extend(struct.pack('<I', resolve(a, new_pc, relative=(ai == rel_idx))))
        emitted = 4 + nargs*4
        if emitted < size: bc.extend(b'\x00' * (size - emitted))

    out = bytearray(b'SCR\x00')
    tbl = bytearray(b'\xFF' * ENTRY_TABLE_LEN)
    for idx, lbl in entries.items():
        target = label_pc.get(lbl)
        if target is None:
            raise ValueError(f'ENTRY {idx} references undefined label {lbl!r}')
        struct.pack_into('<I', tbl, idx*4, target & 0xFFFFFFFF)
    out.extend(tbl)
    out.extend(bc)
    return bytes(out)


# ---- driver --------------------------------------------------------------

def cmd_disasm(src, out_dir):
    import gc, hashlib
    table = load_table()
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    src = Path(src)
    paths = [src] if src.is_file() else sorted(src.iterdir())
    master_path = out_dir / 'MASTER.json'
    master = json.loads(master_path.read_text(encoding='utf-8')) if master_path.exists() else {}
    for p in paths:
        if p.suffix.lower() not in ('.e', '.m'): continue
        # resume support: skip files already in MASTER.json
        if p.name in master and not any(e.get('scr') and not (out_dir / e['scr']).exists()
                                        for e in master[p.name]['entries']):
            continue                                       # silently skip already-done
        d = p.read_bytes()
        if d[:4] != b'FPK\x00': continue
        fpk_entries = fpk_parse(d)
        per_inner = []; seen = {}                          # hash -> (scr or bin name)
        bin_dir = out_dir / '_blobs'
        for idx, (name, off, size) in enumerate(fpk_entries):
            if size == 0:
                per_inner.append({'name':name,'size':0,'scr':None,'bin':None}); continue
            blob = d[off:off+size]
            h = hashlib.sha1(blob).digest()
            if h in seen:
                per_inner.append({'name':name,'size':size,
                                  **seen[h],'dup':True})
                continue

            # Helper for non-script blobs: stash raw bytes verbatim so asm can
            # round-trip them. Stored uncompressed in _blobs/ next to the .txt.
            def _stash_blob(reason):
                bin_dir.mkdir(parents=True, exist_ok=True)
                bin_name = f'{p.stem}__{idx}.bin'
                (bin_dir / bin_name).write_bytes(blob)
                rec = {'scr':None,'bin':bin_name}
                seen[h] = rec
                per_inner.append({'name':name,'size':size, **rec})
                if reason: print(f'  stash: {p.name}/{name}: {reason}')

            try:
                decompressed = decompress_ash(blob)
            except Exception as e:
                _stash_blob(f'not script (decompress: {e})'); continue
            if decompressed[:4] != b'SCR\x00':
                del decompressed; _stash_blob('not script (no SCR magic)'); continue
            ash_const = struct.unpack('<I', blob[8:12])[0]
            ash_hash  = struct.unpack('<I', blob[12:16])[0]
            try:
                instrs, entries, trailing_labels = disasm_blob(decompressed, table)
            except Exception as e:
                del decompressed; _stash_blob(f'disasm failed: {e}'); continue
            text = emit_text(instrs, entries, ash_const, ash_hash, trailing_labels)
            scr_name = f'{p.stem}__{idx}.txt'
            (out_dir / scr_name).write_text(text, encoding='utf-8')
            rec = {'scr':scr_name,'bin':None}
            seen[h] = rec
            per_inner.append({'name':name,'size':size, **rec})
            del decompressed, instrs, entries, text
        master[p.name] = {'entries': per_inner}
        print(f'  disasm {p.name}: {len(fpk_entries)} inner(s)')
        # incremental save so a kill doesn't wipe progress
        master_path.write_text(json.dumps(master, indent=2, ensure_ascii=False), encoding='utf-8')
        del d, fpk_entries, per_inner, seen
        gc.collect()


def cmd_asm(txt_dir, out_dir, only=None):
    table = load_table()
    txt_dir = Path(txt_dir); out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    master = json.loads((txt_dir / 'MASTER.json').read_text(encoding='utf-8'))
    if only:
        if only not in master:
            print(f'error: {only!r} not in MASTER.json'); sys.exit(1)
        master = {only: master[only]}
    bin_dir = txt_dir / '_blobs'
    for fpk_name, info in master.items():
        blobs = {}                                    # cache: key -> bytes
        for ent in info['entries']:
            if ent.get('size',0) == 0: continue
            scr = ent.get('scr'); binf = ent.get('bin')
            if scr:
                if scr in blobs: continue
                text = (txt_dir / scr).read_text(encoding='utf-8')
                ac, ah, entries, instrs, trailing = parse_text(text)
                decompressed = assemble(ac, ah, entries, instrs, table, trailing)
                blobs[scr] = compress_ash(decompressed, hash_word=ah, const_word=ac)
            elif binf:
                if binf in blobs: continue
                blobs[binf] = (bin_dir / binf).read_bytes()
        fpk_entries = []
        for ent in info['entries']:
            if ent.get('size',0) == 0:
                fpk_entries.append((ent['name'], b''))
            elif ent.get('scr'):
                fpk_entries.append((ent['name'], blobs[ent['scr']]))
            elif ent.get('bin'):
                fpk_entries.append((ent['name'], blobs[ent['bin']]))
            else:
                # legacy entry from an older MASTER.json — we don't have the bytes
                raise RuntimeError(f'{fpk_name}/{ent["name"]}: no scr or bin '
                                   f'recorded — re-run disasm to capture it')
        (out_dir / fpk_name).write_bytes(fpk_build(fpk_entries))
        print(f'  asm {fpk_name}')


def main():
    if len(sys.argv) < 4: print(__doc__); sys.exit(2)
    cmd, a, b = sys.argv[1], sys.argv[2], sys.argv[3]
    if cmd == 'disasm': cmd_disasm(a, b)
    elif cmd == 'asm':
        only = sys.argv[4] if len(sys.argv) >= 5 else None
        cmd_asm(a, b, only)
    else: print(__doc__); sys.exit(2)

if __name__ == '__main__':
    main()
