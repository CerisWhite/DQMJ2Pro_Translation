## Adding New Synthesis Recipes to Joker 2 Professional

These commands should be run between the steps of the [patching guide](https://github.com/saneezore07/DQMJ2Pro_Translation/blob/master/Guide/step-by-step.md), after step 9 `performpatch.py` and before step 10 `rebuild with ndstool`.

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
