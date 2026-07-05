#!/usr/bin/env python3
import contextlib
import os
import queue
import sys
import subprocess
import webbrowser
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    TKDND_AVAILABLE = True
except Exception:
    DND_FILES = None
    TkinterDnD = None
    TKDND_AVAILABLE = False

import gui_backend


def app_root():
    if getattr(sys, "frozen", False):
        return Path.cwd()
    return Path(__file__).resolve().parents[3]

ROOT = app_root()
PATCHER_VERSION = "0.5"

def open_url(url):
    if sys.platform.startswith("linux"):
        env = dict(os.environ)

        # AppImage/PyInstaller can poison launched desktop apps with bundled libs.
        for key in (
            "LD_LIBRARY_PATH",
            "PYTHONHOME",
            "PYTHONPATH",
            "APPDIR",
            "APPIMAGE",
            "ARGV0",
        ):
            env.pop(key, None)

        for cmd in (
            ["xdg-open", url],
            ["gio", "open", url],
        ):
            try:
                subprocess.Popen(
                    cmd,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return
            except Exception:
                pass

    try:
        webbrowser.open(url)
    except Exception:
        pass



class QueueWriter:
    def __init__(self, q):
        self.q = q

    def write(self, text):
        if text:
            self.q.put(text)

    def flush(self):
        pass


class App((TkinterDnD.Tk if TKDND_AVAILABLE else tk.Tk)):
    def __init__(self):
        super().__init__()
        try:
            # Prevent oversized fonts/widgets on some Linux AppImage setups only.
            if sys.platform.startswith("linux") and getattr(sys, "frozen", False):
                self.tk.call("tk", "scaling", 1.2)
        except Exception:
            pass
        self.title(f"DQMJ2P Translation Patcher v{PATCHER_VERSION}")
        self.geometry("760x620")
        self.minsize(720, 560)

        self.log_queue = queue.Queue()

        self.rom_var = tk.StringVar()
        self.out_var = tk.StringVar(value=str(Path.home() / f"DQMJ2P_Eng_Patched_v{PATCHER_VERSION}.nds"))

        self.new_synths_var = tk.BooleanVar(value=True)
        self.xp_mult_var = tk.BooleanVar(value=False)
        self.xp_mult_value = tk.StringVar(value="2.0")
        self.xvariant_var = tk.BooleanVar(value=False)
        self.gender_icons_var = tk.BooleanVar(value=False)
        self.scout_offense_var = tk.BooleanVar(value=False)
        self.scout_penalty_var = tk.BooleanVar(value=False)
        self.synth_level_var = tk.BooleanVar(value=False)
        self.synth_level_value = tk.StringVar(value="10")
        self.synth_polarity_var = tk.BooleanVar(value=False)

        self.show_log_var = tk.BooleanVar(value=False)

        self.build_ui()
        self.after(100, self.drain_log_queue)

    def build_ui(self):
        pad = {"padx": 10, "pady": 6}

        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True)

        self.drop_box = ttk.Label(
            frm,
            text="Drag and drop clean DQMJ2P ROM here",
            anchor="center",
            relief="ridge",
            padding=18,
        )
        self.drop_box.grid(row=0, column=0, columnspan=3, sticky="ew", padx=10, pady=10)

        ttk.Label(frm, text="Clean DQMJ2P ROM:").grid(row=1, column=0, sticky="w", **pad)
        self.rom_entry = ttk.Entry(frm, textvariable=self.rom_var)
        self.rom_entry.grid(row=1, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="Browse", command=self.browse_rom).grid(row=1, column=2, **pad)

        if TKDND_AVAILABLE:
            for widget in (self.drop_box, self.rom_entry):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self.handle_rom_drop)

        ttk.Label(frm, text="Output ROM:").grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.out_var).grid(row=2, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="Browse", command=self.browse_output).grid(row=2, column=2, **pad)

        opts = ttk.LabelFrame(frm, text="Patch options")
        opts.grid(row=3, column=0, columnspan=3, sticky="ew", **pad)

        ttk.Checkbutton(opts, text="Add new synthesis recipes", variable=self.new_synths_var).pack(anchor="w", padx=10, pady=3)

        xp_row = ttk.Frame(opts)
        xp_row.pack(anchor="w", padx=10, pady=3)
        ttk.Checkbutton(xp_row, text="Set XP Multiplier:", variable=self.xp_mult_var).pack(side="left")
        ttk.Entry(xp_row, textvariable=self.xp_mult_value, width=8).pack(side="left", padx=6)

        ttk.Checkbutton(opts, text="Apply X/XY Variant Suffix Fix", variable=self.xvariant_var).pack(anchor="w", padx=10, pady=3)
        ttk.Checkbutton(opts, text="Replace Gender Icons with Polarity", variable=self.gender_icons_var).pack(anchor="w", padx=10, pady=3)
        ttk.Checkbutton(opts, text='Make "Took offense" NOT Disable Scouting', variable=self.scout_offense_var).pack(anchor="w", padx=10, pady=3)
        ttk.Checkbutton(opts, text="Remove Multiple Species Owned Check From Scouting", variable=self.scout_penalty_var).pack(anchor="w", padx=10, pady=3)

        level_row = ttk.Frame(opts)
        level_row.pack(anchor="w", padx=10, pady=3)
        ttk.Checkbutton(level_row, text="Set Minimum Synthesis Level:", variable=self.synth_level_var).pack(side="left")
        ttk.Entry(level_row, textvariable=self.synth_level_value, width=5).pack(side="left", padx=6)

        ttk.Checkbutton(opts, text="Remove Synthesis Polarity Requirement", variable=self.synth_polarity_var).pack(anchor="w", padx=10, pady=3)

        self.run_btn = ttk.Button(frm, text="Patch ROM", command=self.start_patch)
        self.run_btn.grid(row=4, column=0, columnspan=3, pady=10)

        self.progress = ttk.Progressbar(frm, mode="indeterminate")
        self.progress.grid(row=5, column=0, columnspan=3, sticky="ew", padx=10)

        ttk.Checkbutton(
            frm,
            text="Show command log",
            variable=self.show_log_var,
            command=self.toggle_log,
        ).grid(row=6, column=0, sticky="w", padx=10, pady=6)

        release_link = ttk.Label(
            frm,
            text="Check for the Latest Release",
            cursor="hand2",
            foreground="blue",
            font=("", 9, "bold"),
        )
        release_link.grid(row=7, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 6))
        release_link.bind(
            "<Button-1>",
            lambda _e: open_url(
                "https://github.com/saneezore07/DQMJ2Pro_Translation/releases"
            ),
        )

        self.log_frame = ttk.Frame(frm)
        self.log_text = tk.Text(self.log_frame, height=14, wrap="word")
        self.log_text.pack(fill="both", expand=True)

        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(8, weight=1)

    def toggle_log(self):
        if self.show_log_var.get():
            self.log_frame.grid(row=8, column=0, columnspan=3, sticky="nsew", padx=10, pady=6)
        else:
            self.log_frame.grid_forget()

    def clean_dropped_path(self, raw):
        raw = raw.strip()

        # tkinterdnd2 may wrap paths with braces if they contain spaces.
        if raw.startswith("{") and raw.endswith("}"):
            raw = raw[1:-1]

        # If multiple files are dropped, take the first.
        if "} {" in raw:
            raw = raw.split("} {", 1)[0].lstrip("{").rstrip("}")

        return raw.strip().strip('"').strip("'")

    def handle_rom_drop(self, event):
        path = self.clean_dropped_path(event.data)
        if path:
            self.rom_var.set(path)
            self.out_var.set(str(Path(path).with_name(f"DQMJ2P_Eng_Patched_v{PATCHER_VERSION}.nds")))

    def browse_rom(self):
        path = filedialog.askopenfilename(
            title="Select clean DQMJ2P ROM",
            filetypes=[("Nintendo DS ROM", "*.nds"), ("All files", "*.*")]
        )
        if path:
            self.rom_var.set(path)
            self.out_var.set(str(Path(path).with_name(f"DQMJ2P_Eng_Patched_v{PATCHER_VERSION}.nds")))

    def browse_output(self):
        path = filedialog.asksaveasfilename(
            title="Save patched ROM as",
            defaultextension=".nds",
            filetypes=[("Nintendo DS ROM", "*.nds"), ("All files", "*.*")]
        )
        if path:
            self.out_var.set(path)

    def append_log(self, text):
        self.log_text.insert("end", text)
        self.log_text.see("end")

    def start_patch(self):
        rom = self.rom_var.get().strip()
        out = self.out_var.get().strip()

        if not rom:
            messagebox.showerror("Missing ROM", "Select a clean .nds ROM first.")
            return
        if not Path(rom).is_file():
            messagebox.showerror("ROM not found", rom)
            return
        if not out:
            messagebox.showerror("Missing output", "Choose an output .nds path.")
            return

        args = ["--rom", rom, "--output", out, "--anti-piracy"]
        if self.new_synths_var.get():
            args.append("--new-synths")
        if self.xp_mult_var.get():
            args.extend(["--xp-mult", self.xp_mult_value.get()])
        if self.xvariant_var.get():
            args.append("--xvariant-suffix")
        if self.gender_icons_var.get():
            args.append("--gender-icons")
        if self.scout_offense_var.get():
            args.append("--scout-offense")
        if self.scout_penalty_var.get():
            args.append("--scout-penalty")
        if self.synth_level_var.get():
            args.extend(["--synthesis-level", self.synth_level_value.get()])
        if self.synth_polarity_var.get():
            args.append("--synthesis-polarity")

        self.log_text.delete("1.0", "end")
        self.append_log("> gui_backend " + " ".join(args) + "\n\n")

        self.run_btn.config(state="disabled")
        self.progress.start(10)

        threading.Thread(target=self.run_backend, args=(args,), daemon=True).start()

    def run_backend(self, args):
        writer = QueueWriter(self.log_queue)
        code = 0

        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                gui_backend.main(args)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
            if e.code and not isinstance(e.code, int):
                self.log_queue.put(str(e.code) + "\n")
        except Exception as e:
            code = 1
            self.log_queue.put(f"ERROR: {e}\n")

        self.log_queue.put(("__DONE__", code))

    def drain_log_queue(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                if isinstance(item, tuple) and item[0] == "__DONE__":
                    code = item[1]
                    self.progress.stop()
                    self.run_btn.config(state="normal")
                    if code == 0:
                        messagebox.showinfo("Done", "Patched ROM created successfully.")
                    else:
                        messagebox.showerror("Failed", f"Patcher failed with exit code {code}.")
                else:
                    self.append_log(item)
        except queue.Empty:
            pass

        self.after(100, self.drain_log_queue)


if __name__ == "__main__":
    App().mainloop()
