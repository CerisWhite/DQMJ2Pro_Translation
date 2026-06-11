### Prerequisites
`python` `ndstool` `wine`

### Arch/Cachy/EndevourOS
`sudo pacman -S python wine`

`yay -S ndstool`

### Debian/Mint/Ubuntu
`sudo apt install -y python3 wine build-essential`

`wget https://github.com/devkitPro/ndstool/releases/download/v2.1.2/ndstool-2.1.2.tar.bz2`

`tar -xjf ndstool-2.1.2.tar.bz2`

`cd ndstool-2.1.2`

`./configure && make && sudo make install`

---

`git clone https://github.com/saneezore07/DQMJ2Pro_Translation`

`cd DQMJ2Pro_Translation`

`mkdir -p Pro_ROM`

`cp Pro_Tools/blz_win.exe Pro_Tools/biz.exe`

Put your rom in `DQMJ2Pro_Translation` as `DQMJ2P.nds`

`ndstool -x DQMJ2P.nds -7 Pro_ROM\arm7.bin -9 Pro_ROM\arm9.bin -d Pro_ROM\data -y Pro_ROM\overlay -t Pro_ROM\banner.bin -h Pro_ROM\header.bin -y7 Pro_ROM\y7.bin -y9 Pro_ROM\y9.bin`

`python Pro_Tools/arm9tool.py decompress Pro_ROM/arm9.bin Pro_Tools/Pro_ARM9.bin`

`python Pro_Tools/performpatch.py --rom Pro_ROM`

`ndstool -c Patched.nds -7 Pro_ROM\arm7.bin -9 Pro_ROM\arm9.bin -d Pro_ROM\data -y Pro_ROM\overlay -t Pro_ROM\banner.bin -h Pro_ROM\header.bin -y7 Pro_ROM\y7.bin -y9 Pro_ROM\y9.bin`
