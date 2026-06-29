"""Shared helpers for the transplant / restore scripts."""
import re

# Match a SAY/SETNAME line, capturing the mnemonic and the quoted body.
TXT = re.compile(r'^(SAY|SETNAME)\s+"((?:[^"\\]|\\.)*)"\s*$')

# Hiragana, Katakana, half-width Katakana, CJK Unified Ideographs.
JP = re.compile(r'[぀-ゟ゠-ヿ一-鿿･-ﾟ]')


# 1F XX -> ASCII (J2 DTE digraph tiles, cracked from context).
DTE_TABLE = {
    '1F0B': 'S ', '1F0D': 'SA', '1F0F': 'SC', '1F11': 'SE',
    '1F14': 'SH', '1F15': 'SI', '1F1B': 'SO', '1F1D': 'SQ',
    '1F1F': 'SS', '1F20': 'ST',
    '1F27': 'Sa', '1F29': 'Sc', '1F2B': 'Se', '1F2E': 'Sh',
    '1F2F': 'Si', '1F32': 'Sl', '1F33': 'Sm', '1F35': 'So',
    '1F36': 'Sp', '1F37': 'Sq', '1F3A': 'St', '1F3B': 'Su',
    '1F3D': 'Sw', '1F3F': 'Sy',
    '1FE1': 'S',
}
DTE_RE        = re.compile(r'\{(1F[0-9A-Fa-f]{2})\}')
CHAR_FALLBACK = {'‘': "'"}

# Tag rename: J2 disasm was generated with the original storytool naming;
# Pro disasm uses the renamed tags.
TAG_RENAME = [
    (re.compile(r'\{SPEAKER=(\d+)\}'), r'{VOICE=\1}'),
    (re.compile(r'\{NEWLINE\}'),       '{BREAK}'),
    (re.compile(r'\{ENDLINE\}'),       '{END}'),
]


def translate_body(body: str) -> str:
    """Convert a J2-disasm SAY/SETNAME body to Pro-disasm format:
    drop the first {END} and everything after it (J2 padding artifacts plus
    the terminator the assembler restores), rename any lingering old tag
    names to the current Pro names (defensive — J2_SCRIPTS_EN has already
    been migrated), expand 1F XX DTE codes to plain ASCII, and apply the
    glyph fallback for codepoints Pro's font lacks."""
    for pat, repl in TAG_RENAME:
        body = pat.sub(repl, body)
    end = body.find('{END}')
    if end >= 0:
        body = body[:end]
    body = DTE_RE.sub(lambda m: DTE_TABLE.get(m.group(1).upper(), m.group(0)), body)
    for src, dst in CHAR_FALLBACK.items():
        body = body.replace(src, dst)
    return body


def parse(lines):
    """Return (blocks, isolated_idxs).
      blocks: list of {open, close, txts: [line_idx,...]}
      isolated: list of TXT line indices that fall outside any SYS_42..SYS_43
                block."""
    blocks = []; isolated = []; cur = None
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s == 'SYS_42 0x8':
            cur = {'open': i, 'txts': []}
        elif s == 'SYS_43 0x8' and cur is not None:
            cur['close'] = i
            blocks.append(cur); cur = None
        elif TXT.match(ln):
            (cur['txts'] if cur is not None else isolated).append(i)
    return blocks, isolated
