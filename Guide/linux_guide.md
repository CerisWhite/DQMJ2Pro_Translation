### Prerequisites
`python` `ndstool` `wine`

### Arch/Cachy/EndevourOS
```bat
sudo pacman -S python wine
```

```bat
yay -S ndstool
```

### Debian/Mint/Ubuntu
```bat
sudo apt install -y python3 wine build-essential
```

```bat
wget https://github.com/devkitPro/ndstool/releases/download/v2.1.2/ndstool-2.1.2.tar.bz2
```

```bat
tar -xjf ndstool-2.1.2.tar.bz2
```

```bat
cd ndstool-2.1.2
```

```bat
./configure && make && sudo make install
```

---

```bat
git clone https://github.com/saneezore07/DQMJ2Pro_Translation
```

```bat
cd DQMJ2Pro_Translation
```

```bat
mkdir -p Pro_ROM
```

```bat
cp Pro_Tools/blz_win.exe Pro_Tools/biz.exe
```

Put your rom in `DQMJ2Pro_Translation` as `DQMJ2P.nds`

```bat
ndstool -x DQMJ2P.nds -7 Pro_ROM\arm7.bin -9 Pro_ROM\arm9.bin -d Pro_ROM\data -y Pro_ROM\overlay -t Pro_ROM\banner.bin -h Pro_ROM\header.bin -y7 Pro_ROM\y7.bin -y9 Pro_ROM\y9.bin
```

```bat
python Pro_Tools/arm9tool.py decompress Pro_ROM/arm9.bin Pro_Tools/Pro_ARM9.bin
```

```bat
python Pro_Tools/performpatch.py --rom Pro_ROM
```

<details>
<summary>Adding new synthesis recipes</summary>

```bat
python Pro_Tools/synthesis_parser.py --in Pro_ROM/data/CombinationKindTbl.bin --out Kind.csv
```
```bat
python Pro_Tools/synthesis_parser.py --in Pro_ROM/data/Combination4GTbl.bin --out 4g.csv --type 4g
```
```bat
python -c "from pathlib import Path; open('Kind.csv','a',encoding='utf-8',newline='').write(''.join(Path('Database/new_synths_kind.csv').read_text(encoding='utf-8').splitlines(True)))"
```
```bat
python -c "from pathlib import Path; open('4g.csv','a',encoding='utf-8',newline='').write(''.join(Path('Database/new_synths_4g.csv').read_text(encoding='utf-8').splitlines(True)))"
```
```bat
python Pro_Tools/synthesis_parser.py --in Kind.csv --out Pro_ROM/data/CombinationKindTbl.bin
```
```bat
python Pro_Tools/synthesis_parser.py --in 4g.csv --out Pro_ROM/data/Combination4GTbl.bin --type 4g
```

</details>

```bat
ndstool -c Patched.nds -7 Pro_ROM\arm7.bin -9 Pro_ROM\arm9.bin -d Pro_ROM\data -y Pro_ROM\overlay -t Pro_ROM\banner.bin -h Pro_ROM\header.bin -y7 Pro_ROM\y7.bin -y9 Pro_ROM\y9.bin
```
