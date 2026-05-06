You will need the J2P ROM, ndstool (<https://github.com/devkitpro/ndstool>), and python. For BLZ, you'll need to replace it with the build in the .rar file or compile it yourself. The version in the Pro_Tools.zip is adjusted for linux since that's what I use.
To build ndstool, you'll probably have to use MSYS2 if you're on Windows. I don't know if it needs anything beyond the basics of GCC but I'm sure there are instructions for it somewhere. If not, ask me later. The BLZ binary will be `blz.out` in the Pro_Tools directory.
The ndstool command I usually use comes out to this (inside of a `Pro_ROM` folder):
`../ndstool -x ../DQMJ2P.nds -7 arm7.bin -9 arm9.bin -d data_dir -y overlay_dir -t banner.bin -h header.bin -y7 y7.bin -y9 y9.bin -t banner.bin -o logo.bin`
and to make the new ROM after changing things:
`../ndstool -c ../edited.nds -7 arm7.bin -9 arm9.bin -d data_dir -y overlay_dir -t banner.bin -h header.bin -y7 y7.bin -y9 y9.bin -t banner.bin -o logo.bin`

- arm9tool.py: Compresses and decompresses the arm9.bin file; You will need to put a copy of the decompressed arm9.bin in Pro_Tools as Pro_ARM9.bin for msgtool to work. `python Pro_Tools/arm9tool.py decompress Pro_ROM/arm9.bin Pro_Tools/Pro_ARM9.bin`
- find_untranslated.py: `python Pro_Tools/find_untranslated.py <directory>` will list every file with JP characters inside it. Use with `-v` to print the exact line numbers and strings themselves.
- grow_msg_pool.py: VITAL. This is what fixes the stat issue that comes from the text being too large compared to JP. `python Pro_Tools/grow_msg_pool.py --pool 0 --size 0x38000 --in Pro_ROM/arm9.bin --out patched.bin`  and then rename patched.bin to arm9.bin and replace the original one. This tool won't work on an already edited arm9.bin, so `ndstool -x <rom> -9 arm.bin` to extract a fresh one as needed. If you start seeing the stat issues again, make the size larger. AS FAR AS I KNOW, you can use a size up to `0x40000`. It must be a multiple of 1000 regardless.
- msgtool.py: extracts strings. `python Pro_Tools/msgtool.py extract Pro_ROM/data_dir STRINGS/` will extract the msg files to a new STRINGS directory. `python Pro_Tools/msgtool.py repack STRINGS/ OUTPUT/` will rebuild the files to OUTPUT
- storytool.py: extracts scripts. `python Pro_Tools/storytool.py disasm Pro_ROM/data_dir SCRIPTS/` will extract the script files to a new SCRIPTS directory. `python Pro_Tools/storytool.py asm SCRIPTS/ OUTPUT/` will rebuild the files to OUTPUT

Extract the strings and scripts, edit them, rebuild them to OUTPUT, copy the contents of OUTPUT to data_dir (`cp OUTPUT/* Pro_ROM/data_dir/`) and then rebuild with ndstool. Finally, test your changes by running edited.nds in your emulator of choice.
