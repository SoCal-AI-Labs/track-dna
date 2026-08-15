from __future__ import annotations

import json
import random
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from trackdna.ai import load_settings, polish_suno, save_settings
from trackdna.analyze import analyze_track
from trackdna.ingest import resolve_source
from trackdna.report import format_report
from trackdna.suno import format_suno

# Warm studio desk — not cold neon SaaS
BG = "#241910"
PANEL = "#3a2a20"
CARD = "#4a3528"
INK = "#2a1c14"
CREAM = "#f6efe4"
BUTTER = "#f3d27a"
TOMATO = "#e85d3a"
SAGE = "#7fb069"
PEACH = "#f0a07a"
RUST = "#c44b2b"
MUTED = "#c9b8a4"

TAB_PROMPT = "Suno/MiniMax prompt"


class TrackDNAApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.title("Track DNA")
        self.geometry("1240x820")
        self.minsize(1020, 720)
        self.configure(fg_color=BG)

        self.file_path = tk.StringVar()
        self.url_value = tk.StringVar()
        self.status = tk.StringVar(value="Drop a song on the desk. We keep the feel. We leave the words.")
        self.rank = tk.StringVar(value="warming up")
        self.runs = tk.StringVar(value="0 spins")
        self.xp_label = tk.StringVar(value="needle up")
        self.detailed = tk.BooleanVar(value=True)
        self.busy = False
        self.dna: dict | None = None
        self.suno: dict | None = None
        self.run_count = 0
        self._eq_job = None
        self._eq_levels = [10, 16, 8, 20, 12, 14]

        self._build()
        self._tick_eq()

    def _build(self) -> None:
        header = ctk.CTkFrame(self, fg_color=BG)
        header.pack(fill="x", padx=22, pady=(16, 4))

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        title_row = ctk.CTkFrame(left, fg_color="transparent")
        title_row.pack(anchor="w")
        self.eq = tk.Canvas(title_row, width=86, height=34, bg=BG, highlightthickness=0, bd=0)
        self.eq.pack(side="left", padx=(0, 12), pady=(4, 0))
        ctk.CTkLabel(
            title_row,
            text="Track DNA",
            font=ctk.CTkFont(family="Georgia", size=34, weight="bold"),
            text_color=BUTTER,
        ).pack(side="left")
        ctk.CTkLabel(
            left,
            text="A little desk for catching grooves. Instrumental prompts only.",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=MUTED,
        ).pack(anchor="w", pady=(2, 0))

        stickers = ctk.CTkFrame(header, fg_color="transparent")
        stickers.pack(side="right")
        self._sticker(stickers, self.rank, TOMATO, CREAM).pack(side="left", padx=(0, 8))
        self._sticker(stickers, self.runs, SAGE, INK).pack(side="left")

        source = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=22, border_width=0)
        source.pack(fill="x", padx=22, pady=10)
        ctk.CTkLabel(
            source,
            text="put a song on the desk",
            font=ctk.CTkFont(family="Georgia", size=15, slant="italic"),
            text_color=PEACH,
        ).pack(anchor="w", padx=18, pady=(14, 0))

        row1 = ctk.CTkFrame(source, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=(10, 6))
        ctk.CTkEntry(
            row1,
            textvariable=self.file_path,
            placeholder_text="WAV, MP3, FLAC… the dusty one in your downloads",
            height=40,
            fg_color=CARD,
            border_color="#6a4e3a",
            text_color=CREAM,
            placeholder_text_color="#b89f86",
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._hw_button(row1, "Browse", self._browse, CARD, CREAM, 110).pack(side="left")

        row2 = ctk.CTkFrame(source, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=6)
        ctk.CTkEntry(
            row2,
            textvariable=self.url_value,
            placeholder_text="or a YouTube link, if the internet is behaving",
            height=40,
            fg_color=CARD,
            border_color="#6a4e3a",
            text_color=CREAM,
            placeholder_text_color="#b89f86",
        ).pack(side="left", fill="x", expand=True)

        row3 = ctk.CTkFrame(source, fg_color="transparent")
        row3.pack(fill="x", padx=16, pady=(6, 16))
        ctk.CTkCheckBox(
            row3,
            text="All the juicy detail",
            variable=self.detailed,
            command=self._refresh_suno,
            fg_color=TOMATO,
            hover_color=RUST,
            checkmark_color=CREAM,
            text_color=CREAM,
        ).pack(side="left")
        self._hw_button(row3, "Settings", self._settings, CARD, CREAM, 110).pack(side="right", padx=(8, 0))
        self._hw_button(row3, "Polish", self._ai_polish, CARD, CREAM, 110).pack(side="right", padx=(8, 0))
        self.analyze_btn = ctk.CTkButton(
            row3,
            text="Spin it  ●",
            width=150,
            height=40,
            corner_radius=20,
            fg_color=TOMATO,
            text_color=CREAM,
            hover_color="#ff734f",
            font=ctk.CTkFont(family="Georgia", size=16, weight="bold"),
            command=self._analyze,
        )
        self.analyze_btn.pack(side="right")

        needle = ctk.CTkFrame(self, fg_color="transparent")
        needle.pack(fill="x", padx=22, pady=(0, 2))
        ctk.CTkLabel(needle, textvariable=self.xp_label, text_color=PEACH, width=100, anchor="w").pack(side="left")
        self.progress = ctk.CTkProgressBar(
            needle, height=12, progress_color=TOMATO, fg_color="#4a3328", corner_radius=8
        )
        self.progress.pack(side="left", fill="x", expand=True, padx=8)
        self.progress.set(0)
        ctk.CTkLabel(self, textvariable=self.status, text_color=MUTED, anchor="w").pack(fill="x", padx=24)

        self.hud = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=22)
        self.hud.pack(fill="x", padx=22, pady=10)
        self.stat_vars = {
            "bpm": tk.StringVar(value="bpm\n—"),
            "key": tk.StringVar(value="key\n—"),
            "bass": tk.StringVar(value="bass\n—"),
            "groove": tk.StringVar(value="groove\n—"),
            "form": tk.StringVar(value="form\n—"),
        }
        chips = ctk.CTkFrame(self.hud, fg_color="transparent")
        chips.pack(fill="x", padx=10, pady=10)
        fills = [TOMATO, BUTTER, RUST, SAGE, PEACH]
        inks = [CREAM, INK, CREAM, INK, INK]
        for (key, var), fill, ink in zip(self.stat_vars.items(), fills, inks):
            self._stat_chip(chips, var, fill, ink).pack(side="left", expand=True, fill="both", padx=5)

        self.tabs = ctk.CTkTabview(
            self,
            fg_color=PANEL,
            segmented_button_fg_color=INK,
            segmented_button_selected_color=TOMATO,
            segmented_button_selected_hover_color=RUST,
            segmented_button_unselected_color=CARD,
            text_color=CREAM,
        )
        self.tabs.pack(fill="both", expand=True, padx=22, pady=(2, 16))
        self.tabs.add(TAB_PROMPT)
        self.tabs.add("Full report")
        self.tabs.add("JSON")

        prompt_tab = self.tabs.tab(TAB_PROMPT)
        self.style_label = tk.StringVar(value="style prompt  →  paste in the left box")
        self.lyrics_label = tk.StringVar(value="structure  →  tags only, no words")
        self.map_open = False
        self.lyrics_box = self._structure_dropdown(prompt_tab)
        self.style_box = self._copy_panel(prompt_tab, self.style_label, "Copy style")
        self._set_placeholder(self.style_box, "Your track's vibe lands here after a spin.")

        self.report_box = ctk.CTkTextbox(
            self.tabs.tab("Full report"),
            font=ctk.CTkFont(family="Consolas", size=13),
            fg_color=CARD,
            text_color=CREAM,
        )
        self.report_box.pack(fill="both", expand=True, padx=8, pady=8)
        report_btns = ctk.CTkFrame(self.tabs.tab("Full report"), fg_color="transparent")
        report_btns.pack(fill="x", padx=8, pady=(0, 8))
        self._hw_button(report_btns, "Copy report", lambda: self._copy(self.report_box.get("1.0", "end")), CARD, CREAM, 130).pack(
            side="left"
        )
        self._hw_button(report_btns, "Save…", self._save_report, CARD, CREAM, 90).pack(side="left", padx=8)

        self.json_box = ctk.CTkTextbox(
            self.tabs.tab("JSON"), font=ctk.CTkFont(family="Consolas", size=12), fg_color=CARD, text_color=CREAM
        )
        self.json_box.pack(fill="both", expand=True, padx=8, pady=8)
        json_btns = ctk.CTkFrame(self.tabs.tab("JSON"), fg_color="transparent")
        json_btns.pack(fill="x", padx=8, pady=(0, 8))
        self._hw_button(json_btns, "Copy JSON", lambda: self._copy(self.json_box.get("1.0", "end")), CARD, CREAM, 120).pack(
            side="left"
        )
        self._hw_button(json_btns, "Save…", self._save_json, CARD, CREAM, 90).pack(side="left", padx=8)

    def _hw_button(self, parent, text, command, fill, ink, width) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            width=width,
            height=38,
            corner_radius=18,
            fg_color=fill,
            text_color=ink,
            hover_color="#5c4030",
            command=command,
        )

    def _sticker(self, parent, variable, fill, ink) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=fill, corner_radius=16)
        ctk.CTkLabel(
            frame,
            textvariable=variable,
            text_color=ink,
            font=ctk.CTkFont(family="Georgia", size=13, weight="bold"),
        ).pack(padx=12, pady=7)
        return frame

    def _stat_chip(self, parent, variable, fill, ink) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=fill, corner_radius=18)
        ctk.CTkLabel(
            frame,
            textvariable=variable,
            text_color=ink,
            font=ctk.CTkFont(family="Georgia", size=15, weight="bold"),
            justify="center",
        ).pack(padx=8, pady=12)
        return frame

    def _copy_panel(self, parent, title, button_text: str) -> ctk.CTkTextbox:
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        top = ctk.CTkFrame(wrap, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, textvariable=title, text_color=PEACH, font=ctk.CTkFont(family="Georgia", size=14)).pack(
            side="left"
        )
        box = ctk.CTkTextbox(wrap, font=ctk.CTkFont(family="Consolas", size=14), wrap="word", fg_color=CARD, text_color=CREAM)
        box.pack(fill="both", expand=True, pady=(4, 6))
        ctk.CTkButton(
            top,
            text=button_text,
            width=120,
            height=34,
            corner_radius=16,
            fg_color=BUTTER,
            text_color=INK,
            hover_color="#ffe6a3",
            command=lambda: self._copy(box.get("1.0", "end")),
        ).pack(side="right")
        return box

    def _structure_dropdown(self, parent) -> ctk.CTkTextbox:
        self.map_wrap = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=18)
        self.map_wrap.pack(side="bottom", fill="x", padx=8, pady=(0, 10))
        header = ctk.CTkFrame(self.map_wrap, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=8)
        self.map_toggle_btn = ctk.CTkButton(
            header,
            text="▸  Peek at the structure map",
            fg_color=INK,
            hover_color="#3d2a20",
            text_color=CREAM,
            anchor="w",
            corner_radius=14,
            command=self._toggle_structure_map,
        )
        self.map_toggle_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))
        box = ctk.CTkTextbox(
            self.map_wrap,
            font=ctk.CTkFont(family="Consolas", size=14),
            wrap="word",
            fg_color=INK,
            text_color=CREAM,
            height=240,
        )
        ctk.CTkButton(
            header,
            text="Copy map",
            width=110,
            height=34,
            corner_radius=16,
            fg_color=BUTTER,
            text_color=INK,
            hover_color="#ffe6a3",
            command=lambda: self._copy(box.get("1.0", "end")),
        ).pack(side="right")
        self.map_body = box
        return box

    def _toggle_structure_map(self) -> None:
        self.map_open = not self.map_open
        if self.map_open:
            self.map_toggle_btn.configure(text="▾  Hide the structure map")
            self.map_body.pack(fill="x", padx=8, pady=(0, 10))
        else:
            self.map_toggle_btn.configure(text="▸  Peek at the structure map")
            self.map_body.pack_forget()

    def _tick_eq(self) -> None:
        if not self.eq.winfo_exists():
            return
        self.eq.delete("all")
        colors = [TOMATO, BUTTER, SAGE, PEACH, RUST, BUTTER]
        gap = 4
        bar_w = 10
        for i, color in enumerate(colors):
            if self.busy:
                h = random.randint(8, 30)
            elif self.dna:
                h = 8 + int((self._eq_levels[i] + random.randint(-3, 3)) * 0.7)
            else:
                h = 6 + (i * 2 + random.randint(0, 6)) % 16
            self._eq_levels[i] = h
            x = 4 + i * (bar_w + gap)
            self.eq.create_rectangle(x, 32 - h, x + bar_w, 32, fill=color, outline="")
        self._eq_job = self.after(140 if self.busy else 280, self._tick_eq)

    def _set_placeholder(self, box: ctk.CTkTextbox, text: str) -> None:
        box.delete("1.0", "end")
        box.insert("1.0", text)

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Pick a track",
            filetypes=[
                ("Audio", "*.wav *.mp3 *.flac *.ogg *.m4a *.aac *.aiff"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.file_path.set(path)
            self.url_value.set("")

    def _source(self) -> str:
        url = self.url_value.get().strip()
        if url:
            return url
        return self.file_path.get().strip()

    def _analyze(self) -> None:
        if self.busy:
            return
        source = self._source()
        if not source:
            messagebox.showinfo("Track DNA", "Drop a file or paste a URL first.")
            return
        self.busy = True
        self.analyze_btn.configure(state="disabled", text="Spinning…", fg_color=RUST)
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.xp_label.set("needle down")
        self.status.set("Listening… measuring the stuff you can actually hear.")
        threading.Thread(target=self._analyze_worker, args=(source,), daemon=True).start()

    def _analyze_worker(self, source: str) -> None:
        try:
            path = resolve_source(
                source,
                progress=lambda msg: self.after(0, lambda m=msg: self.status.set(m)),
            )
            dna = analyze_track(path, progress=lambda msg: self.after(0, lambda m=msg: self.status.set(m)))
            suno = format_suno(dna, detailed=self.detailed.get())
            self.after(0, lambda d=dna, s=suno: self._show_result(d, s))
        except Exception as exc:
            message = _format_error(exc)
            self.after(0, lambda m=message: self._fail(m))

    def _show_result(self, dna: dict, suno: dict) -> None:
        self.dna = dna
        self.suno = suno
        self.run_count += 1
        self._fill(self.style_box, suno["style"])
        self._fill(self.lyrics_box, suno["lyrics"])
        self._fill(self.report_box, format_report(dna))
        self._fill(self.json_box, json.dumps(dna, indent=2))
        self._update_counts()
        self._update_hud(dna)
        sections = len(dna.get("sections") or [])
        self._done(f"Got it.  {dna['source_name']}  ·  {dna['tempo_bpm']:.0f} BPM  ·  {sections} parts")

    def _update_hud(self, dna: dict) -> None:
        bass = _band(dna, "bass") + _band(dna, "sub")
        groove = dna.get("swing_class", "straight")
        sections = len(dna.get("sections") or [])
        self.stat_vars["bpm"].set(f"bpm\n{dna['tempo_bpm']:.0f}")
        self.stat_vars["key"].set(f"key\n{dna.get('key', '—')}")
        self.stat_vars["bass"].set(f"bass\n{bass:.0f}%")
        self.stat_vars["groove"].set(f"groove\n{groove}")
        self.stat_vars["form"].set(f"form\n{sections} parts")
        self.runs.set(f"{self.run_count} spin" + ("" if self.run_count == 1 else "s"))
        self.rank.set(_rank(dna))
        self.xp_label.set("locked in")

    def _refresh_suno(self) -> None:
        if not self.dna:
            return
        self.suno = format_suno(self.dna, detailed=self.detailed.get())
        self._fill(self.style_box, self.suno["style"])
        self._fill(self.lyrics_box, self.suno["lyrics"])
        self._update_counts()

    def _ai_polish(self) -> None:
        if not self.dna:
            messagebox.showinfo("Track DNA", "Spin a track first.")
            return
        if self.busy:
            return
        self.busy = True
        self.status.set("Polishing the prompt… still no lyrics.")
        self.progress.configure(mode="indeterminate")
        self.progress.start()

        def work():
            try:
                suno = polish_suno(self.dna)
                self.after(0, lambda s=suno: self._apply_suno(s, "Prompt got a little shinier."))
            except Exception as exc:
                message = _format_error(exc)
                self.after(0, lambda m=message: self._fail(m))

        threading.Thread(target=work, daemon=True).start()

    def _apply_suno(self, suno: dict, message: str) -> None:
        self.suno = suno
        self._fill(self.style_box, suno["style"])
        self._fill(self.lyrics_box, suno["lyrics"])
        self._update_counts()
        self._done(message)

    def _settings(self) -> None:
        cfg = load_settings()
        win = ctk.CTkToplevel(self)
        win.title("Settings")
        win.geometry("520x420")
        win.configure(fg_color=BG)
        win.grab_set()
        key = tk.StringVar(value=cfg.get("api_key", ""))
        base = tk.StringVar(value=cfg.get("base_url", "https://api.openai.com/v1"))
        model = tk.StringVar(value=cfg.get("model", "gpt-4.1-mini"))
        cookies = tk.StringVar(value=cfg.get("cookies_txt", ""))
        ctk.CTkLabel(win, text="Optional API for prompt polish", text_color=CREAM).pack(anchor="w", padx=16, pady=(16, 8))
        ctk.CTkEntry(win, textvariable=key, placeholder_text="API key", show="•", fg_color=CARD).pack(fill="x", padx=16, pady=4)
        ctk.CTkEntry(win, textvariable=base, placeholder_text="Base URL", fg_color=CARD).pack(fill="x", padx=16, pady=4)
        ctk.CTkEntry(win, textvariable=model, placeholder_text="Model", fg_color=CARD).pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(win, text="YouTube cookies.txt if a link gets blocked", text_color=CREAM).pack(
            anchor="w", padx=16, pady=(12, 4)
        )
        ctk.CTkEntry(win, textvariable=cookies, placeholder_text="Path to cookies.txt", fg_color=CARD).pack(
            fill="x", padx=16, pady=4
        )
        ctk.CTkLabel(
            win,
            text="No key needed for analysis. Cookies are only for stubborn YouTube links.",
            text_color=MUTED,
        ).pack(anchor="w", padx=16, pady=8)

        def save():
            save_settings(
                {
                    "api_key": key.get().strip(),
                    "base_url": base.get().strip(),
                    "model": model.get().strip(),
                    "cookies_txt": cookies.get().strip(),
                }
            )
            win.destroy()

        ctk.CTkButton(win, text="Save", fg_color=TOMATO, text_color=CREAM, corner_radius=16, command=save).pack(pady=12)

    def _save_report(self) -> None:
        if not self.dna:
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if path:
            Path(path).write_text(self.report_box.get("1.0", "end").strip() + "\n", encoding="utf-8")

    def _save_json(self) -> None:
        if not self.dna:
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            Path(path).write_text(json.dumps(self.dna, indent=2), encoding="utf-8")

    def _update_counts(self) -> None:
        style = self.style_box.get("1.0", "end").strip()
        lyrics = self.lyrics_box.get("1.0", "end").strip()
        self.style_label.set(f"style prompt  →  Suno / MiniMax  ({len(style)}/1000)")
        self.lyrics_label.set(f"structure  →  tags only, no words  ({len(lyrics)}/3000)")

    def _fill(self, box: ctk.CTkTextbox, text: str) -> None:
        box.delete("1.0", "end")
        box.insert("1.0", text)

    def _copy(self, text: str) -> None:
        body = text.strip()
        if not body:
            return
        self.clipboard_clear()
        self.clipboard_append(body)
        self.status.set("Copied. Go paste it into Suno or MiniMax.")

    def _fail(self, message: str) -> None:
        self._done("That one skipped.")
        self.xp_label.set("needle up")
        messagebox.showerror("Track DNA", message)

    def _done(self, message: str) -> None:
        self.busy = False
        self.analyze_btn.configure(state="normal", text="Spin it  ●", fg_color=TOMATO)
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(1 if self.dna else 0)
        self.status.set(message)


def _band(dna: dict, name: str) -> float:
    for row in dna.get("band_energy", []):
        if row["name"] == name:
            return float(row["energy_pct"])
    return 0.0


def _rank(dna: dict) -> str:
    sections = len(dna.get("sections") or [])
    duration = float(dna.get("duration_sec") or 0)
    if sections >= 10 and duration >= 180:
        return "liner notes"
    if sections >= 6:
        return "desk rat"
    if duration >= 60:
        return "crate digger"
    return "first spin"


def _format_error(exc: BaseException) -> str:
    text = str(exc).strip()
    if not text or text == "None":
        text = type(exc).__name__
    cause = exc.__cause__ or exc.__context__
    if cause and str(cause).strip() and str(cause) not in text:
        text = f"{text}\n\n{cause}"
    return text


def main() -> None:
    app = TrackDNAApp()
    app.mainloop()
