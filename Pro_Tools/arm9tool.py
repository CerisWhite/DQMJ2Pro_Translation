#!/usr/bin/env python3
"""DQMJ2P arm9.bin (de)compressor.

The cart's arm9.bin is Cue-style ARM9 BLZ (LZSS, decompressed backwards
from the end), with a 12-byte Nitro trailer appended after the BLZ
footer. Layout:

    [plaintext  0x000..0x4000]            uncompressed boot/decompressor
    [compressed 0x4000..0x964ac]          BLZ-compressed payload
    [BLZ footer 0x964ac..0x964b4]         8 bytes: enc_len_packed, dec_delta
    [Nitro trail 0x964b4..0x964c0]        12 bytes: nitrocode 0xDEC00621,
                                                    ptr-to-ModuleParams,
                                                    zero word

The runtime decompressor at 0x02000950 reads the 8-byte BLZ footer via
`ldmdb r0,{r1,r2}` where r0 = ModuleParams.compressed_static_end. It
preserves the plaintext prefix (compressed_start = compressed_end -
enc_len = 0x02004000 in stock).

Cue's stock `blz` would corrupt the plaintext prefix, so we drive the
compressor on the body alone and hand-stitch the file.

Usage:
    arm9tool.py decompress arm9.bin arm9_dec.bin
    arm9tool.py compress   arm9_dec.bin arm9.bin
"""
import os, struct, subprocess, sys, tempfile
from pathlib import Path

NITRO_TRAILER          = bytes.fromhex('2106c0de680b000000000000')
MODULE_PARAMS_FILE_OFF = 0xb68          # ModuleParams struct file offset
COMPRESSED_END_OFF     = 0x14           # field offset within ModuleParams
PLAINTEXT_PREFIX_LEN   = 0x4000         # boot stub + decompressor (uncompressed)
ARM9_LOAD_ADDR         = 0x02000000

BLZ = str(Path(__file__).parent / 'blz.exe')
if not os.path.isfile(BLZ):
    sys.exit(f'blz binary not found at {BLZ}')


def decompress(src_path, dst_path):
    data = Path(src_path).read_bytes()
    if not data.endswith(NITRO_TRAILER):
        sys.exit('error: input does not end with the expected Nitro trailer; '
                 'is this really arm9.bin?')
    stripped = data[:-len(NITRO_TRAILER)]
    enc_packed, dec_delta = struct.unpack('<II', stripped[-8:])
    print(f'BLZ footer: header={enc_packed>>24:#x}  enc_len={enc_packed&0xFFFFFF:#x}  dec_delta={dec_delta:#x}')
    if dec_delta == 0:
        sys.exit('dec_delta == 0; nothing to decompress')

    with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as tf:
        tf.write(stripped)
        tmp = tf.name
    try:
        subprocess.run([BLZ, '-d', tmp], check=True, capture_output=True)
        out = Path(tmp).read_bytes()
    finally:
        os.unlink(tmp)
    print(f'decompressed: {len(stripped):#x} -> {len(out):#x} bytes')
    Path(dst_path).write_bytes(out)


def compress(src_path, dst_path):
    """Compress arm9_decompressed.bin -> arm9.bin.

    Strategy:
      1. Split off the first 0x4000 bytes (plaintext prefix — preserved verbatim).
      2. Run Cue blz -en (or -eo) on the remainder to get compressed-body+footer.
      3. Concatenate: plaintext + compressed-body+footer.
      4. Patch ModuleParams.compressed_static_end to the new file end.
      5. Append the 12-byte Nitro trailer.
    """
    data = Path(src_path).read_bytes()
    if len(data) < PLAINTEXT_PREFIX_LEN:
        sys.exit(f'input too short ({len(data):#x} < plaintext prefix {PLAINTEXT_PREFIX_LEN:#x})')

    prefix = bytearray(data[:PLAINTEXT_PREFIX_LEN])
    body   = data[PLAINTEXT_PREFIX_LEN:]

    with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as tf:
        tf.write(body)
        tmp = tf.name
    try:
        # -eo (optimal) gives smaller output than -en; both produce identical
        # decompressed results.
        subprocess.run([BLZ, '-eo', tmp], check=True, capture_output=True)
        comp_body = Path(tmp).read_bytes()
    finally:
        os.unlink(tmp)

    # NOTE: Cue blz produces a self-consistent footer. Its enc_len is the size
    # of the compressed REGION (excluding any verbatim prefix it chose to leave
    # at the start of the output) — NOT the total file size. The runtime
    # decompressor computes compressed_start = compressed_end - enc_len, and any
    # bytes between compressed_end-file_size and compressed_start are left
    # untouched at runtime. blz's verbatim prefix sits exactly there, so the
    # body's first bytes round-trip correctly without any footer modification.
    # Do NOT rewrite the footer — doing so makes compressed_start point inside
    # the verbatim prefix and the decompressor mis-interprets those bytes as
    # compressed data.

    # Patch ModuleParams.compressed_static_end inside the plaintext prefix
    new_compressed_end = ARM9_LOAD_ADDR + PLAINTEXT_PREFIX_LEN + len(comp_body)
    mp_field = MODULE_PARAMS_FILE_OFF + COMPRESSED_END_OFF
    old = struct.unpack('<I', prefix[mp_field:mp_field+4])[0]
    struct.pack_into('<I', prefix, mp_field, new_compressed_end)
    print(f'ModuleParams.compressed_static_end: {old:#x} -> {new_compressed_end:#x}')

    out = bytes(prefix) + comp_body + NITRO_TRAILER
    Path(dst_path).write_bytes(out)
    print(f'wrote {dst_path}: {len(out):#x} bytes  ' \
          f'(plaintext {PLAINTEXT_PREFIX_LEN:#x} + compressed {len(comp_body):#x} + trailer 0xc)')


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in ('decompress','compress'):
        sys.exit(__doc__)
    {'decompress': decompress, 'compress': compress}[sys.argv[1]](sys.argv[2], sys.argv[3])

if __name__ == '__main__':
    main()
