from __future__ import annotations

import json
import math
import random
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from trackdna.ai import load_settings, polish_suno, save_settings
from trackdna.ingest import resolve_bundle
from trackdna.job import run_analysis
from trackdna.report import format_report
from trackdna.suno import format_suno

# Walnut chassis + cream liner notes
BG = "#16100c"
WOOD = "#241810"
PAPER = "#f3ead8"
SHEET = "#fff8ec"
INK = "#231610"
CREAM = "#f7f0e4"
TOMATO = "#e24b2a"
TOMATO_HOT = "#ff6a45"
BUTTER = "#f2c14e"
SAGE = "#5d8a62"
PEACH = "#e39a72"
RUST = "#b63d22"
MUTED = "#c4b09a"
RULE = "#d8c7ae"
FIELD = "#1c1410"

TAB_PROMPT = "Suno/MiniMax prompt"
_DECK_LINES = (
    "RECORDING  ·  listening for the groove",
    "RECORDING  ·  pressing the mix into tape",
    "RECORDING  ·  winding the DNA",
    "RECORDING  ·  no vocals, just feel",
)


class TrackDNAApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.title("Track DNA")
        self.geometry("1260x840")
        self.minsize(1040, 740)
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
        self._vinyl_angle = 0.0
        self._vinyl_job = None
        self._vu_job = None
        self._deck_job = None
        self._deck_angle = 0.0
        self._deck_tick = 0
        self._deck_phase = 0
        self._deck_vu_l = 0.4
        self._deck_vu_r = 0.35

        self._build()
        self._tick_vinyl()
        self._tick_vu()

    def _build(self) -> None:
        spine = ctk.CTkFrame(self, fg_color=TOMATO, width=8, corner_radius=0)
        spine.pack(side="left", fill="y")
        spine.pack_propagate(False)

        body = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        body.pack(side="left", fill="both", expand=True)
        self.body = body

        header = ctk.CTkFrame(body, fg_color=BG)
        header.pack(fill="x", padx=22, pady=(16, 8))

        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.pack(side="left")
        self.vinyl = tk.Canvas(brand, width=74, height=74, bg=BG, highlightthickness=0, bd=0)
        self.vinyl.pack(side="left", padx=(0, 14))
        titles = ctk.CTkFrame(brand, fg_color="transparent")
        titles.pack(side="left")
        ctk.CTkLabel(
            titles,
            text="Track DNA",
            font=ctk.CTkFont(family="Georgia", size=34, weight="bold"),
            text_color=CREAM,
        ).pack(anchor="w")
        ctk.CTkLabel(
            titles,
            text="A little desk for catching grooves. Instrumental prompts only.",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=MUTED,
        ).pack(anchor="w")

        stickers = ctk.CTkFrame(header, fg_color="transparent")
        stickers.pack(side="right")
        self._sticker(stickers, self.rank, TOMATO, CREAM).pack(side="left", padx=(0, 8))
        self._sticker(stickers, self.runs, SAGE, SHEET).pack(side="left")

        desk = ctk.CTkFrame(body, fg_color=PAPER, corner_radius=16)
        desk.pack(fill="x", padx=22, pady=(0, 10))
        desk_top = ctk.CTkFrame(desk, fg_color="transparent")
        desk_top.pack(fill="x", padx=18, pady=(14, 0))
        ctk.CTkLabel(
            desk_top,
            text="SIDE A",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=TOMATO,
        ).pack(side="left")
        ctk.CTkLabel(
            desk_top,
            text="put a song on the desk",
            font=ctk.CTkFont(family="Georgia", size=16, slant="italic"),
            text_color=INK,
        ).pack(side="left", padx=10)

        row1 = ctk.CTkFrame(desk, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=(10, 6))
        self._field(row1, self.file_path, "WAV, MP3, FLAC… the dusty one in your downloads").pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )
        self._ghost_btn(row1, "Browse", self._browse, 104).pack(side="left")

        row2 = ctk.CTkFrame(desk, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=6)
        self._field(row2, self.url_value, "or a YouTube link, if the internet is behaving").pack(
            side="left", fill="x", expand=True
        )

        row3 = ctk.CTkFrame(desk, fg_color="transparent")
        row3.pack(fill="x", padx=16, pady=(8, 16))
        ctk.CTkCheckBox(
            row3,
            text="All the juicy detail",
            variable=self.detailed,
            command=self._refresh_suno,
            fg_color=TOMATO,
            hover_color=RUST,
            checkmark_color=SHEET,
            text_color=INK,
            border_color="#b89d7c",
        ).pack(side="left")
        self._ghost_btn(row3, "Settings", self._settings, 104).pack(side="right", padx=(8, 0))
        self._ghost_btn(row3, "Polish", self._ai_polish, 104).pack(side="right", padx=(8, 0))
        self.analyze_btn = ctk.CTkButton(
            row3,
            text="Spin it  ●",
            width=148,
            height=40,
            corner_radius=12,
            fg_color=TOMATO,
            text_color=SHEET,
            hover_color=TOMATO_HOT,
            font=ctk.CTkFont(family="Georgia", size=16, weight="bold"),
            command=self._analyze,
        )
        self.analyze_btn.pack(side="right")

        needle = ctk.CTkFrame(body, fg_color="transparent")
        needle.pack(fill="x", padx=26, pady=(2, 0))
        ctk.CTkLabel(
            needle,
            textvariable=self.xp_label,
            text_color=PEACH,
            width=92,
            anchor="w",
            font=ctk.CTkFont(family="Georgia", size=13, slant="italic"),
        ).pack(side="left")
        self.vu = tk.Canvas(needle, height=22, bg=BG, highlightthickness=0, bd=0)
        self.vu.pack(side="left", fill="x", expand=True, padx=8)
        ctk.CTkLabel(body, textvariable=self.status, text_color=MUTED, anchor="w").pack(fill="x", padx=26, pady=(2, 8))

        meters = ctk.CTkFrame(body, fg_color="transparent")
        meters.pack(fill="x", padx=18, pady=(0, 10))
        self.stat_vars = {
            "bpm": tk.StringVar(value="—"),
            "key": tk.StringVar(value="—"),
            "bass": tk.StringVar(value="—"),
            "groove": tk.StringVar(value="—"),
            "form": tk.StringVar(value="—"),
        }
        accents = [
            ("bpm", TOMATO),
            ("key", BUTTER),
            ("bass", RUST),
            ("groove", SAGE),
            ("form", PEACH),
        ]
        for key, accent in accents:
            self._meter(meters, key, self.stat_vars[key], accent).pack(
                side="left", expand=True, fill="both", padx=4
            )

        notes = ctk.CTkFrame(body, fg_color=PAPER, corner_radius=16)
        notes.pack(fill="both", expand=True, padx=22, pady=(0, 18))
        self._build_deck(body)
        self.tabs = ctk.CTkTabview(
            notes,
            fg_color=PAPER,
            segmented_button_fg_color=WOOD,
            segmented_button_selected_color=TOMATO,
            segmented_button_selected_hover_color=RUST,
            segmented_button_unselected_color=FIELD,
            text_color=SHEET,
        )
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(8, 10))
        self.tabs.add(TAB_PROMPT)
        self.tabs.add("Full report")
        self.tabs.add("JSON")

        prompt_tab = self.tabs.tab(TAB_PROMPT)
        prompt_tab.configure(fg_color=PAPER)
        self.style_label = tk.StringVar(value="style prompt  →  paste in the left box")
        self.lyrics_label = tk.StringVar(value="structure  →  tags only, no words")
        self.map_open = False
        self.lyrics_box = self._structure_dropdown(prompt_tab)
        self.style_box = self._copy_panel(prompt_tab, self.style_label, "Copy style")
        self._set_placeholder(self.style_box, "Your track's vibe lands here after a spin.")

        report_tab = self.tabs.tab("Full report")
        report_tab.configure(fg_color=PAPER)
        self.report_box = self._sheet(report_tab)
        self.report_box.pack(fill="both", expand=True, padx=8, pady=8)
        report_btns = ctk.CTkFrame(report_tab, fg_color="transparent")
        report_btns.pack(fill="x", padx=8, pady=(0, 8))
        self._ghost_btn(report_btns, "Copy report", lambda: self._copy(self.report_box.get("1.0", "end")), 124).pack(
            side="left"
        )
        self._ghost_btn(report_btns, "Save…", self._save_report, 88).pack(side="left", padx=8)

        json_tab = self.tabs.tab("JSON")
        json_tab.configure(fg_color=PAPER)
        self.json_box = self._sheet(json_tab, size=12)
        self.json_box.pack(fill="both", expand=True, padx=8, pady=8)
        json_btns = ctk.CTkFrame(json_tab, fg_color="transparent")
        json_btns.pack(fill="x", padx=8, pady=(0, 8))
        self._ghost_btn(json_btns, "Copy JSON", lambda: self._copy(self.json_box.get("1.0", "end")), 114).pack(side="left")
        self._ghost_btn(json_btns, "Save…", self._save_json, 88).pack(side="left", padx=8)

    def _build_deck(self, parent) -> None:
        self.deck = ctk.CTkFrame(parent, fg_color=WOOD, corner_radius=20)
        top = ctk.CTkFrame(self.deck, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(14, 2))
        self.deck_caption = tk.StringVar(value="RECORDING  ·  listening for the groove")
        ctk.CTkLabel(
            top,
            textvariable=self.deck_caption,
            font=ctk.CTkFont(family="Georgia", size=17, slant="italic"),
            text_color=CREAM,
        ).pack(side="left")
        self.deck_counter = tk.StringVar(value="000")
        ctk.CTkLabel(
            top,
            textvariable=self.deck_counter,
            font=ctk.CTkFont(family="Consolas", size=18, weight="bold"),
            text_color=TOMATO,
        ).pack(side="right")
        self.deck_canvas = tk.Canvas(self.deck, width=640, height=248, bg=WOOD, highlightthickness=0, bd=0)
        self.deck_canvas.pack(padx=14, pady=(0, 14))

    def _show_deck(self, caption: str = "RECORDING  ·  listening for the groove") -> None:
        self.deck_caption.set(caption)
        self._deck_tick = 0
        self._deck_phase = 0
        self.deck.place(in_=self.body, relx=0.5, rely=0.62, anchor="center")
        self.deck.lift()
        if self._deck_job is None:
            self._tick_deck()

    def _hide_deck(self) -> None:
        self.deck.place_forget()
        if self._deck_job is not None:
            self.after_cancel(self._deck_job)
            self._deck_job = None

    def _tick_deck(self) -> None:
        if not self.busy or not self.deck_canvas.winfo_exists():
            self._deck_job = None
            return
        self._deck_angle = (self._deck_angle + 11) % 360
        self._deck_tick += 1
        self._deck_vu_l = self._deck_vu_l * 0.55 + (0.25 + random.random() * 0.75) * 0.45
        self._deck_vu_r = self._deck_vu_r * 0.55 + (0.2 + random.random() * 0.8) * 0.45
        if self._deck_tick % 18 == 0:
            self._deck_phase = (self._deck_phase + 1) % len(_DECK_LINES)
            self.deck_caption.set(_DECK_LINES[self._deck_phase])
        self.deck_counter.set(f"{self._deck_tick % 1000:03d}")
        self._draw_deck()
        self._deck_job = self.after(45, self._tick_deck)

    def _draw_deck(self) -> None:
        c = self.deck_canvas
        c.delete("all")
        w, h = 640, 248
        rec_on = (self._deck_tick // 5) % 2 == 0
        # chassis
        c.create_rectangle(10, 8, w - 6, h - 4, fill="#120c09", outline="")
        c.create_rectangle(8, 6, w - 10, h - 8, fill="#3b2a20", outline="#1a100c", width=2)
        c.create_rectangle(14, 12, w - 16, 40, fill="#2a1c16", outline="")
        c.create_oval(22, 16, 40, 34, fill=TOMATO if rec_on else "#4a2018", outline="#7a2a1c")
        if rec_on:
            c.create_oval(26, 20, 36, 30, fill="#ff8a6a", outline="")
        c.create_text(48, 25, text="REC", fill=SHEET, font=("Segoe UI", 10, "bold"), anchor="w")
        c.create_text(w // 2, 25, text="CASSETTE DECK", fill=MUTED, font=("Segoe UI", 9, "bold"))
        digits = f"{self._deck_tick % 1000:03d}"
        for i, ch in enumerate(digits):
            x = w - 92 + i * 22
            c.create_rectangle(x, 14, x + 20, 34, fill="#0e0a08", outline="#5a4030")
            c.create_text(x + 10, 24, text=ch, fill=TOMATO, font=("Consolas", 12, "bold"))
        # cassette well
        c.create_rectangle(48, 48, w - 48, 178, fill="#1a120e", outline="#5a4030")
        c.create_rectangle(56, 54, w - 56, 170, fill="#241810", outline="")
        self._draw_cassette(c, 88, 58, 464, 108)
        # VU meters
        c.create_text(70, 196, text="L", fill=MUTED, font=("Segoe UI", 8, "bold"))
        c.create_text(70, 218, text="R", fill=MUTED, font=("Segoe UI", 8, "bold"))
        self._draw_vu_row(c, 86, 188, self._deck_vu_l)
        self._draw_vu_row(c, 86, 210, self._deck_vu_r)
        # transport keys
        keys = (("●", TOMATO, SHEET), ("▶", "#2a1c16", CREAM), ("■", "#2a1c16", CREAM), ("◀◀", "#2a1c16", CREAM))
        for i, (mark, fill, ink) in enumerate(keys):
            x = 430 + i * 48
            c.create_oval(x, 186, x + 40, 226, fill=fill, outline="#120c09", width=2)
            c.create_text(x + 20, 206, text=mark, fill=ink, font=("Segoe UI", 11, "bold"))

    def _draw_cassette(self, c, x: int, y: int, w: int, h: int) -> None:
        c.create_rectangle(x + 4, y + 5, x + w + 4, y + h + 5, fill="#1a100c", outline="")
        c.create_rectangle(x, y, x + w, y + h, fill="#e4d4b4", outline="#6a5438", width=2)
        c.create_rectangle(x + 8, y + 8, x + w - 8, y + 36, fill="#f3ead8", outline="#c9b496")
        c.create_text(x + 22, y + 22, text="SIDE A", fill=TOMATO, font=("Segoe UI", 9, "bold"), anchor="w")
        c.create_text(x + w / 2, y + 22, text="TRACK DNA", fill=INK, font=("Georgia", 13, "italic"))
        c.create_text(x + w - 22, y + 22, text="TYPE I", fill="#8a7058", font=("Segoe UI", 8), anchor="e")
        well = (x + 18, y + 44, x + w - 18, y + h - 10)
        c.create_rectangle(*well, fill="#2a1c14", outline="#8a7058")
        left = (x + 78, y + 76)
        right = (x + w - 78, y + 76)
        take = 22 + min(12, self._deck_tick // 18)
        give = 34 - min(10, self._deck_tick // 22)
        self._draw_hub(c, left[0], left[1], give, self._deck_angle)
        self._draw_hub(c, right[0], right[1], take, -self._deck_angle)
        wx1, wy1, wx2, wy2 = x + 150, y + 56, x + w - 150, y + h - 18
        c.create_rectangle(wx1, wy1, wx2, wy2, fill="#1c1410", outline="#6a4e3a")
        c.create_rectangle(wx1 + 4, wy1 + 10, wx2 - 4, wy2 - 10, fill="#5a3a1c", outline="")
        shift = (self._deck_tick * 5) % 8
        for xx in range(wx1 + 8 + shift, wx2 - 6, 8):
            c.create_line(xx, wy1 + 12, xx + 3, wy2 - 12, fill="#c4a574")
        c.create_line(left[0] + 16, left[1], wx1, (wy1 + wy2) / 2, fill="#8a6030", width=3)
        c.create_line(wx2, (wy1 + wy2) / 2, right[0] - 16, right[1], fill="#8a6030", width=3)
        # capstan
        cap = x + w / 2
        c.create_oval(cap - 5, y + h - 8, cap + 5, y + h + 2, fill="#c4a574", outline="#3a2818")

    def _draw_hub(self, canvas, cx: int, cy: int, pack: int, angle: float) -> None:
        canvas.create_oval(cx - pack - 3, cy - pack - 3, cx + pack + 3, cy + pack + 3, fill="#4a3020", outline="#2a1c14")
        canvas.create_oval(cx - pack, cy - pack, cx + pack, cy + pack, fill="#6e4a28", outline="#3a2818")
        for i in range(6):
            a = math.radians(angle + i * 60)
            canvas.create_polygon(
                cx + 5 * math.cos(a - 0.35),
                cy + 5 * math.sin(a - 0.35),
                cx + (pack - 3) * math.cos(a),
                cy + (pack - 3) * math.sin(a),
                cx + 5 * math.cos(a + 0.35),
                cy + 5 * math.sin(a + 0.35),
                fill="#e8dcc4",
                outline="",
            )
        canvas.create_oval(cx - 6, cy - 6, cx + 6, cy + 6, fill=BUTTER, outline="#2a1c14")

    def _draw_vu_row(self, canvas, x: int, y: int, level: float) -> None:
        for i in range(16):
            on = (i / 16) < level
            if i > 13:
                color = TOMATO if on else "#4a2018"
            elif i > 9:
                color = BUTTER if on else "#4a3a18"
            else:
                color = SAGE if on else "#24301c"
            bx = x + i * 18
            canvas.create_rectangle(bx, y, bx + 14, y + 14, fill=color, outline="#120c09")

    def _field(self, parent, variable, placeholder) -> ctk.CTkEntry:
        entry = ctk.CTkEntry(
            parent,
            textvariable=variable,
            placeholder_text=placeholder,
            height=40,
            fg_color=SHEET,
            border_color="#c9b496",
            text_color=INK,
            placeholder_text_color="#8d7760",
            corner_radius=10,
        )
        self._bind_edit_menu(entry)
        return entry

    def _sheet(self, parent, size: int = 13) -> ctk.CTkTextbox:
        box = ctk.CTkTextbox(
            parent,
            font=ctk.CTkFont(family="Consolas", size=size),
            fg_color=SHEET,
            text_color=INK,
            border_color=RULE,
            border_width=1,
            corner_radius=10,
        )
        self._bind_edit_menu(box)
        return box

    def _bind_edit_menu(self, widget) -> None:
        menu = tk.Menu(
            widget,
            tearoff=0,
            bg=SHEET,
            fg=INK,
            activebackground=TOMATO,
            activeforeground=SHEET,
            relief="flat",
        )
        menu.add_command(label="Cut", command=lambda: self._edit_event(widget, "<<Cut>>"))
        menu.add_command(label="Copy", command=lambda: self._edit_event(widget, "<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: self._edit_paste(widget))
        menu.add_separator()
        menu.add_command(label="Select All", command=lambda: self._edit_select_all(widget))

        def popup(event):
            widget.focus_set()
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
            return "break"

        widget.bind("<Button-3>", popup)
        widget.bind("<App>", popup)
        widget.bind("<Shift-F10>", popup)
        widget.bind("<Control-a>", lambda _e: self._edit_select_all(widget) or "break")
        widget.bind("<Control-A>", lambda _e: self._edit_select_all(widget) or "break")

    def _edit_inner(self, widget):
        return getattr(widget, "_entry", None) or getattr(widget, "_textbox", None) or widget

    def _edit_event(self, widget, sequence: str) -> None:
        widget.focus_set()
        self._edit_inner(widget).event_generate(sequence)

    def _edit_paste(self, widget) -> None:
        try:
            clip = self.clipboard_get()
        except tk.TclError:
            return
        if not clip:
            return
        widget.focus_set()
        inner = self._edit_inner(widget)
        try:
            inner.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        if isinstance(widget, ctk.CTkEntry):
            widget.insert("insert", clip)
        else:
            inner.insert("insert", clip)

    def _edit_select_all(self, widget) -> None:
        widget.focus_set()
        if isinstance(widget, ctk.CTkEntry):
            widget.select_range(0, "end")
            widget.icursor("end")
            return
        widget.tag_add("sel", "1.0", "end")
        widget.mark_set("insert", "1.0")

    def _ghost_btn(self, parent, text, command, width) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            width=width,
            height=38,
            corner_radius=10,
            fg_color=WOOD,
            text_color=CREAM,
            hover_color="#3a281e",
            command=command,
        )

    def _sticker(self, parent, variable, fill, ink) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=fill, corner_radius=8)
        ctk.CTkLabel(
            frame,
            textvariable=variable,
            text_color=ink,
            font=ctk.CTkFont(family="Georgia", size=13, weight="bold"),
        ).pack(padx=12, pady=7)
        return frame

    def _meter(self, parent, title: str, variable, accent: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=PAPER, corner_radius=12)
        ctk.CTkFrame(card, fg_color=accent, height=6, corner_radius=4).pack(fill="x", padx=10, pady=(10, 6))
        ctk.CTkLabel(
            card,
            text=title,
            text_color="#8a7058",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        ).pack()
        ctk.CTkLabel(
            card,
            textvariable=variable,
            text_color=INK,
            font=ctk.CTkFont(family="Georgia", size=20, weight="bold"),
        ).pack(pady=(0, 12))
        return card

    def _copy_panel(self, parent, title, button_text: str) -> ctk.CTkTextbox:
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        top = ctk.CTkFrame(wrap, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(
            top,
            textvariable=title,
            text_color=INK,
            font=ctk.CTkFont(family="Georgia", size=14, slant="italic"),
        ).pack(side="left")
        box = self._sheet(wrap, size=14)
        box.pack(fill="both", expand=True, pady=(6, 4))
        ctk.CTkButton(
            top,
            text=button_text,
            width=118,
            height=34,
            corner_radius=10,
            fg_color=BUTTER,
            text_color=INK,
            hover_color="#ffd86a",
            command=lambda: self._copy(box.get("1.0", "end")),
        ).pack(side="right")
        return box

    def _structure_dropdown(self, parent) -> ctk.CTkTextbox:
        self.map_wrap = ctk.CTkFrame(parent, fg_color=SHEET, corner_radius=12, border_width=1, border_color=RULE)
        self.map_wrap.pack(side="bottom", fill="x", padx=8, pady=(0, 10))
        header = ctk.CTkFrame(self.map_wrap, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=8)
        self.map_toggle_btn = ctk.CTkButton(
            header,
            text="▸  Peek at the structure map",
            fg_color=WOOD,
            hover_color="#3a281e",
            text_color=CREAM,
            anchor="w",
            corner_radius=10,
            command=self._toggle_structure_map,
        )
        self.map_toggle_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))
        box = ctk.CTkTextbox(
            self.map_wrap,
            font=ctk.CTkFont(family="Consolas", size=14),
            wrap="word",
            fg_color=FIELD,
            text_color=CREAM,
            height=240,
            corner_radius=10,
        )
        self._bind_edit_menu(box)
        ctk.CTkButton(
            header,
            text="Copy map",
            width=110,
            height=34,
            corner_radius=10,
            fg_color=BUTTER,
            text_color=INK,
            hover_color="#ffd86a",
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

    def _tick_vinyl(self) -> None:
        if not self.vinyl.winfo_exists():
            return
        speed = 16 if self.busy else (4 if self.dna else 1.2)
        self._vinyl_angle = (self._vinyl_angle + speed) % 360
        self._draw_vinyl()
        self._vinyl_job = self.after(80 if self.busy else 50, self._tick_vinyl)

    def _draw_vinyl(self) -> None:
        c = self.vinyl
        c.delete("all")
        cx, cy, r = 37, 37, 33
        c.create_oval(cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1, fill="#3a281e", outline="")
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#0c0908", outline="#4a3428")
        for rad in range(14, 31, 3):
            c.create_oval(cx - rad, cy - rad, cx + rad, cy + rad, outline="#2a211c")
        ang = math.radians(self._vinyl_angle)
        hx = cx + 29 * math.cos(ang)
        hy = cy + 29 * math.sin(ang)
        c.create_line(cx, cy, hx, hy, fill="#3d332c", width=2)
        c.create_oval(cx - 12, cy - 12, cx + 12, cy + 12, fill=TOMATO, outline=BUTTER)
        lx = cx + 7 * math.cos(ang + 0.8)
        ly = cy + 7 * math.sin(ang + 0.8)
        c.create_line(cx, cy, lx, ly, fill=BUTTER, width=2)
        c.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill="#120c09", outline="")

    def _tick_vu(self) -> None:
        if not self.vu.winfo_exists():
            return
        self.vu.delete("all")
        w = max(self.vu.winfo_width(), 40)
        self.vu.create_rectangle(0, 7, w, 17, fill="#2a1c16", outline="")
        if self.busy:
            level = 0.35 + random.random() * 0.6
        elif self.dna:
            level = 1.0
        else:
            level = 0.05
        fill = max(10, int((w - 2) * level))
        self.vu.create_rectangle(1, 8, fill, 16, fill=TOMATO, outline="")
        for x in range(40, w, 40):
            self.vu.create_line(x, 7, x, 17, fill="#16100c")
        self._vu_job = self.after(90 if self.busy else 240, self._tick_vu)

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
        self.analyze_btn.configure(state="disabled", text="Recording…", fg_color=RUST)
        self.xp_label.set("recording")
        self.status.set("Listening… measuring the stuff you can actually hear.")
        self._show_deck()
        threading.Thread(target=self._analyze_worker, args=(source,), daemon=True).start()

    def _analyze_worker(self, source: str) -> None:
        try:
            path, meta = resolve_bundle(
                source,
                progress=lambda msg: self.after(0, lambda m=msg: self.status.set(m)),
            )
            dna, suno = run_analysis(
                path,
                meta,
                detailed=self.detailed.get(),
                progress=lambda msg: self.after(0, lambda m=msg: self.status.set(m)),
            )
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
        genres = ", ".join((dna.get("genres") or [])[:3])
        extra = f"  ·  {genres}" if genres else ""
        self._done(f"Got it.  {dna['source_name']}  ·  {dna['tempo_bpm']:.0f} BPM  ·  {sections} parts{extra}")

    def _update_hud(self, dna: dict) -> None:
        bass = _band(dna, "bass") + _band(dna, "sub")
        groove = dna.get("swing_class", "straight")
        sections = len(dna.get("sections") or [])
        self.stat_vars["bpm"].set(f"{dna['tempo_bpm']:.0f}")
        self.stat_vars["key"].set(str(dna.get("key") or "—"))
        self.stat_vars["bass"].set(f"{bass:.0f}%")
        self.stat_vars["groove"].set(str(groove))
        self.stat_vars["form"].set(f"{sections} parts")
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
        self._show_deck("RECORDING  ·  polishing the tape")

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
        win.geometry("520x430")
        win.configure(fg_color=BG)
        win.grab_set()
        card = ctk.CTkFrame(win, fg_color=PAPER, corner_radius=16)
        card.pack(fill="both", expand=True, padx=16, pady=16)
        key = tk.StringVar(value=cfg.get("api_key", ""))
        base = tk.StringVar(value=cfg.get("base_url", "https://api.openai.com/v1"))
        model = tk.StringVar(value=cfg.get("model", "gpt-4.1-mini"))
        cookies = tk.StringVar(value=cfg.get("cookies_txt", ""))
        ctk.CTkLabel(card, text="Optional API for prompt polish", text_color=INK).pack(anchor="w", padx=16, pady=(16, 8))
        for var, hint, show in (
            (key, "API key", "•"),
            (base, "Base URL", ""),
            (model, "Model", ""),
        ):
            entry = ctk.CTkEntry(
                card,
                textvariable=var,
                placeholder_text=hint,
                show=show,
                fg_color=SHEET,
                text_color=INK,
                border_color="#c9b496",
            )
            entry.pack(fill="x", padx=16, pady=4)
            self._bind_edit_menu(entry)
        ctk.CTkLabel(card, text="YouTube cookies.txt if a link gets blocked", text_color=INK).pack(
            anchor="w", padx=16, pady=(12, 4)
        )
        cookies_entry = ctk.CTkEntry(
            card,
            textvariable=cookies,
            placeholder_text="Path to cookies.txt",
            fg_color=SHEET,
            text_color=INK,
            border_color="#c9b496",
        )
        cookies_entry.pack(fill="x", padx=16, pady=4)
        self._bind_edit_menu(cookies_entry)
        ctk.CTkLabel(
            card,
            text="No key needed for analysis. Cookies are only for stubborn YouTube links.",
            text_color="#8a7058",
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

        ctk.CTkButton(card, text="Save", fg_color=TOMATO, text_color=SHEET, corner_radius=10, command=save).pack(
            pady=(4, 16)
        )

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
        self._hide_deck()
        self.analyze_btn.configure(state="normal", text="Spin it  ●", fg_color=TOMATO)
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
