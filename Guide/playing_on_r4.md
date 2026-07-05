### Too Long; Didn't Read:
You need to flash your old R4 with [pico_launcher](https://github.com/LNH-team/pico-launcher) and **disable** the `Anti-Piracy patch` tickbox in the Patcher.

### How to play on an R4
1. Patch your game **without** the `Anti-Piracy patch` in the Patcher program. <br>
Note: Your particular R4 may have in-built anti-piracy circumvension in the R4's cheat menu. Try to load the non-AP patched translation patched ROM on your stock R4 first before proceeding.
2. Go to [this setup](https://sanrax.github.io/flashcart-guides/cart-guides/dspico/) and find your specific R4 card. ![img](b.png)
3. [Format](https://sanrax.github.io/flashcart-guides/tutorials/formatting/) your R4 SD card (after you back up your files) and follow the installation guide under the **pico_loader** tab *specifically*.
4. Patch your game **without** the `Anti-Piracy patch` in the Patcher program.
5. Load your patched ROM onto your SD card.
6. Play.

### My R4 card isn't listed on the guide website!
R4 has a long history of clones/imitations/copycats, resulting in slightly or very different hardware across many, many different variations, resulting in spotty support. Consider [purchasing](https://www.aliexpress.com/item/1005011543735291.html) a [DSpico](https://www.lnh-team.org/) for ~11 USD (usually cheaper for first-time buyers, one player purchased for ~4 USD). It is a modern cutting-edge 'R4' flashcart with developer-friendly openness and consistent support.

### Why is this necessary?
It seems that applying the `Anti-Piracy patch`, a hexadecimal edit to the ROM file, does not play nice with the R4 kernel's method of ROM booting, causing a white-screen freeze at game boot. But unfortunately this game's anti-piracy basically makes playing the game impossible. Pico_launcher was built-in anti-piracy circumvention, without requiring ROMs to be directly patched.
