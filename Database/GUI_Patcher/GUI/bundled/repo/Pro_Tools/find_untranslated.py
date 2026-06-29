#!/usr/bin/env python3
"""List script files that still contain Japanese text inside SAY/SETNAME bodies.

Usage:
    python3 find_untranslated.py [DIR] [-v|--verbose]

Without flags: prints one filename per line, sorted alphabetically.
With -v/--verbose: also prints each offending line and the running totals.
"""
import re, sys
from pathlib import Path

JP_RANGES = (
    (0x3040, 0x309F),   # Hiragana
    (0x30A0, 0x30FF),   # Katakana
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0xFF65, 0xFF9F),   # Half-width Katakana
)
JP_RE = re.compile('[' + ''.join(f'\\u{lo:04x}-\\u{hi:04x}' for lo, hi in JP_RANGES) + ']')
TXT   = re.compile(r'^(SAY|SETNAME)\s+"((?:[^"\\]|\\.)*)"\s*$')


def scan(path: Path):
    """Return list of (line_no, body) for every JP-bearing TXT in the file."""
    hits = []
    for n, ln in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        m = TXT.match(ln)
        if m and JP_RE.search(m.group(2)):
            hits.append((n, m.group(2)))
    return hits


def main():
    args = sys.argv[1:]
    verbose = False
    if '-v' in args: args.remove('-v'); verbose = True
    if '--verbose' in args: args.remove('--verbose'); verbose = True
    root = Path(args[0]) if args else Path('Translation/SCRIPTS')
    if not root.exists():
        print(f'no such directory: {root}', file=sys.stderr); sys.exit(1)
    files = []
    for p in sorted(root.glob('*.txt')):
        hits = scan(p)
        if hits: files.append((p.name, hits))
    for name, hits in files:
        if verbose:
            print(f'{name}  ({len(hits)} JP lines)')
            for n, body in hits:
                print(f'  line {n}: {body}')
        else:
            print(name)
    if verbose:
        print(f'\n{len(files)} files, {sum(len(h) for _, h in files)} JP lines total.')


if __name__ == '__main__':
    main()
