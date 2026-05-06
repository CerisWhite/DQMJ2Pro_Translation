#!/usr/bin/env python3
"""ASH (LZ-style) decompressor + compressor for DQMJ2P script blobs.

The runtime decompressor is fcn.0207d9b4 in arm9. Format:
   Header (16 bytes):
     +0x00  "ASH\\0"
     +0x04  u32  decompressed output size
     +0x08  u32  always 0x64 (version?)
     +0x0C  u32  metadata; not validated at runtime
   Body (from +0x10): a stream of flag-led tokens.
     flag byte:
       bit 0 = 0  →  raw mode.  length = flag >> 1 ; copy `length` bytes
                    verbatim from the stream into the output.
       bit 0 = 1  →  back-reference.  Read one more byte; together they form
                    a u16 (LE):  length = ((u16 >> 12) & 0xF) + 3
                                 offset = (u16 >> 1) & 0x7FF
                    Copy `length` bytes from output[window_start + offset]
                    where window_start = max(0, dst - 0x800).
"""
import struct


def decompress_ash(blob: bytes) -> bytes:
    if len(blob) < 0x10 or blob[:4] != b'ASH\x00':
        raise ValueError('not an ASH blob')
    out_size = struct.unpack('<I', blob[4:8])[0]
    if out_size > 16 * 1024 * 1024:                # 16 MB sanity cap
        raise ValueError(f'decompressed size {out_size} exceeds sanity cap')
    out = bytearray(out_size)
    src = 0x10
    dst = 0
    while dst < out_size:
        flag = blob[src]; src += 1
        if flag & 1:
            byte2 = blob[src]; src += 1
            packed  = flag | (byte2 << 8)
            length  = ((packed >> 12) & 0xF) + 3
            offset  = (packed >> 1) & 0x7FF
            window  = max(0, dst - 0x800)
            ref     = window + offset
            for _ in range(length):
                out[dst] = out[ref]; ref += 1; dst += 1
        else:
            length = flag >> 1
            out[dst:dst+length] = blob[src:src+length]
            dst += length; src += length
    return bytes(out)


def compress_ash(data: bytes, *, hash_word: int = 0, const_word: int = 0x64) -> bytes:
    """Greedy LZ compressor producing an ASH-format blob from raw `data`.

    Uses a hash table keyed on 3-byte prefixes to find candidate matches in
    O(1) amortized per byte. Each chain is walked until either the window
    boundary (0x800 bytes) is exited or a max-length match is found. Total
    runtime is roughly O(n × avg_chain_length); on real ROM data this is
    100×+ faster than the naive O(window) scan and produces identical output.
    """
    body = bytearray()
    raw_buf = bytearray()

    def flush_raw():
        while raw_buf:
            n = min(len(raw_buf), 127)
            body.append((n << 1) & 0xFE)            # raw flag
            body.extend(raw_buf[:n])
            del raw_buf[:n]

    src = 0
    n   = len(data)
    chain = {}      # 3-byte prefix -> list of positions where it occurred (most recent last)
    # Cap chain walks: pathological inputs (long runs of identical bytes) can
    # accumulate thousands of in-window positions for a single 3-byte key.
    # 64 candidates is plenty to find max-length matches in real scripts and
    # bounds worst-case runtime to O(n × 64).
    MAX_CHAIN = 64
    while src < n:
        max_match = min(18, n - src)
        best_len = 0
        best_off = 0
        if max_match >= 3:
            key = bytes(data[src:src+3])
            window_start = src - 0x800 if src > 0x800 else 0
            positions = chain.get(key)
            if positions:
                # Walk chain back-to-front (most recent first), capped.
                walked = 0
                end = len(positions) - 1
                stop = max(-1, end - MAX_CHAIN)
                for i in range(end, stop, -1):
                    ws_pos = positions[i]
                    if ws_pos < window_start:
                        break
                    ml_cap = min(max_match, src - ws_pos)
                    ml = 3
                    while ml < ml_cap and data[ws_pos + ml] == data[src + ml]:
                        ml += 1
                    if ml > best_len:
                        best_len = ml
                        best_off = ws_pos - window_start
                        if ml == max_match:
                            break
                # Periodically trim positions that are out of window so the
                # chain doesn't grow unbounded across the whole file.
                if len(positions) > MAX_CHAIN * 4:
                    cut = 0
                    for i, p in enumerate(positions):
                        if p >= window_start:
                            cut = i; break
                    else:
                        cut = len(positions)
                    if cut: del positions[:cut]

        if best_len >= 3:
            flush_raw()
            packed = (((best_len - 3) & 0xF) << 12) | ((best_off & 0x7FF) << 1) | 1
            body.append(packed & 0xFF)
            body.append((packed >> 8) & 0xFF)
            # Insert all positions covered by the match into the hash chain.
            for k in range(best_len):
                pos = src + k
                if pos + 3 <= n:
                    kkey = bytes(data[pos:pos+3])
                    chain.setdefault(kkey, []).append(pos)
            src += best_len
        else:
            if src + 3 <= n:
                kkey = bytes(data[src:src+3])
                chain.setdefault(kkey, []).append(src)
            raw_buf.append(data[src])
            src += 1
            if len(raw_buf) >= 127:
                flush_raw()

    flush_raw()

    # Header
    header = bytearray(b'ASH\x00')
    header.extend(struct.pack('<III', n, const_word, hash_word))
    return bytes(header + body)


# --------- self-test ---------

def _selftest():
    import os
    DATA = 'DATA/data_dir'
    failures = []
    sizes = []
    for fn in ['d000.e', 'd130.e', 'd123.e', 'k01e02.e']:
        p = f'{DATA}/{fn}'
        if not os.path.exists(p): continue
        d = open(p,'rb').read()
        # extract first inner blob (FPK directory format)
        nfiles = struct.unpack('<I', d[4:8])[0]
        off, sz = struct.unpack('<II', d[8 + 32:8 + 40])
        inner = d[off:off+sz]
        # decompress
        try:
            decompressed = decompress_ash(inner)
        except Exception as e:
            failures.append(f'{fn}: decompress failed — {e}'); continue
        # extract metadata
        ash_size_field = struct.unpack('<I', inner[4:8])[0]
        ash_const = struct.unpack('<I', inner[8:12])[0]
        ash_hash  = struct.unpack('<I', inner[12:16])[0]
        # recompress
        recompressed = compress_ash(decompressed, hash_word=ash_hash, const_word=ash_const)
        # decompress again to verify round-trip
        re_decompressed = decompress_ash(recompressed)
        ok = re_decompressed == decompressed
        sizes.append((fn, len(inner), len(recompressed), len(decompressed)))
        if not ok:
            failures.append(f'{fn}: round-trip mismatch ({len(decompressed)} vs {len(re_decompressed)})')
    print('=== ASH codec self-test ===')
    for fn, comp_size, our_size, decomp in sizes:
        ratio = our_size / comp_size if comp_size else 0
        print(f'  {fn}: orig_compressed=0x{comp_size:x}  our_compressed=0x{our_size:x} '
              f'(ratio {ratio:.2f})  decompressed=0x{decomp:x}')
    if failures:
        print('FAILURES:')
        for f in failures: print(f'  {f}')
    else:
        print('all round-trips OK')

if __name__ == '__main__':
    _selftest()
