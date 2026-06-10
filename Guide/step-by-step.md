### Dragon Quest Monsters: Joker 2 Professional
#### Quick Translation Patching Guide:

This guide [originates from this google doc](https://docs.google.com/document/d/1hYcnyBTjx02n6xiYTC_GZ14FXWaOdcHdTvIsb3KCaw4/edit)

1. Install python. On windows, you’ll get it from here: https://www.python.org/ftp/python/3.14.5/python-3.14.5-amd64.exe

SELECT “Add python.exe to PATH”.

![Add python.exe to PATH](1.png)

2. Download the code from the [repository](https://github.com/CerisWhite/DQMJ2Pro_Translation) (edit: or [this fork](https://github.com/saneezore07/DQMJ2Pro_Translation/blob/master/Guide/step-by-step.md))

![Download the code from the repository](2.png)

3. Get a copy of `ndstool` or build it from source. (Note: I cannot verify the version from `dslazy` works properly, due to it being several years old)

![ndstool](3.png)

4. In `Pro_Tools`, rename `blz_win` to `blz`

![Rename blz_win to blz](4.png)

5. In the file bar, type `cmd` and then press enter to bring up a command prompt

![Open command prompt](5.png)

6. In the command prompt, type `python --version` and press enter, which should give you a version string like this. This verifies you have Python installed correctly.

![python --version](6.png)

7. Now you’ll do `mkdir Pro_ROM` and extract the data from your `.nds` file with this command:

```bat
ndstool -x DQMJ2P.nds -7 Pro_ROM\arm7.bin -9 Pro_ROM\arm9.bin -d Pro_ROM\data -y Pro_ROM\overlay -t Pro_ROM\banner.bin -h Pro_ROM\header.bin -y7 Pro_ROM\y7.bin -y9 Pro_ROM\y9.bin
```

![Extract ROM](7.png)

Normally, I would include `-o Pro_ROM\logo.bin` but the DSLazy version of `ndstool` does not properly support it.

8. Decompress the `arm9.bin` so the tools can use it:

```bat
python Pro_Tools\arm9tool.py decompress Pro_ROM\arm9.bin Pro_Tools\Pro_ARM9.bin
```

![Decompress arm9.bin](8.png)

9. Now you can run the automatic patcher

```bat
python Pro_Tools\performpatch.py
```

10. If you used a different directory name, enter it here. After pressing enter, the script will automatically build the data and apply the necessary patches.

![Run automatic patcher](9.png)

Rebuild with `ndstool`:

```bat
ndstool -c Patched.nds -7 Pro_ROM\arm7.bin -9 Pro_ROM\arm9.bin -d Pro_ROM\data -y Pro_ROM\overlay -t Pro_ROM\banner.bin -h Pro_ROM\header.bin -y7 Pro_ROM\y7.bin -y9 Pro_ROM\y9.bin
```

Again, I would include `-o` if this version of `ndstool` supported it.

![Rebuild](10.png)

And now you should have a finished “Patched.nds” file you can use in whatever emulator you prefer.
