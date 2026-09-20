#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import sys
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from pvz_core import (
    ACHIEVEMENTS, BOOL_FIELDS, CHALLENGE_NAMES, MAX_I32, ProfileV8,
    SEED_NAMES, STORE_ITEMS,
)
from pvz_ig_core import InGameSave, MAX_RUN_STAGE, MAX_SUN

APP_TITLE = "Plants vs. Zombies: Replanted – PS4 Save Editor"
REGION = "CUSA55613"

BG = "#071923"
PANEL = "#0d2735"
PANEL_2 = "#103244"
PANEL_3 = "#153d50"
SIDEBAR = "#092331"
GREEN = "#47df65"
GREEN_DARK = "#1d8f3d"
TEXT = "#f4f7f8"
MUTED = "#a9c2cf"
BORDER = "#2b6076"
GOLD = "#ffd43b"


def asset_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "assets" / name


class ScrollPage(tk.Frame):
    def __init__(self, master, bg=BG):
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window_id, width=e.width))
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1460x900")
        self.minsize(1180, 760)
        self.configure(bg=BG)

        self.profile: ProfileV8 | None = None
        self.path: Path | None = None
        self.dirty = False
        self.images = {}
        self.pages = {}
        self.nav_buttons = {}
        self.current_page = "Overview"
        self.zen_selected_slot = None
        self.zen_form_dirty = False
        self._zen_refreshing = False
        self._zen_preview_ready = False

        # Separate in-progress-game (.ig.dat) state.  This is intentionally
        # independent from the 0.pb.dat profile editor.
        self.ig_save: InGameSave | None = None
        self.ig_path: Path | None = None
        self.ig_selected_record: int | None = None
        self.ig_dirty = False
        self.ig_form_dirty = False
        self._ig_refreshing = False

        self._setup_style()
        self._load_images()
        self._build_shell()
        self._build_pages()
        self.show_page("Overview")
        self._set_loaded_state(False)

        self.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.bind_all("<Control-o>", lambda _e: self.open_file())
        self.bind_all("<Control-s>", lambda _e: self.save_file())
        self.bind_all("<Control-b>", lambda _e: self.create_backup())
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                        rowheight=28, borderwidth=0)
        style.map("Treeview", background=[("selected", GREEN_DARK)])
        style.configure("Treeview.Heading", background=PANEL_3, foreground=TEXT, relief="flat")
        style.configure("Vertical.TScrollbar", background=PANEL_3, troughcolor=BG, bordercolor=BG)
        style.configure("PvZ.Horizontal.TProgressbar", troughcolor="#09202b", background=GREEN_DARK,
                        lightcolor=GREEN, darkcolor=GREEN_DARK, bordercolor="#09202b", thickness=12)

    def _load_images(self):
        # Assets are pre-sized in the package, so no third-party image library
        # (such as Pillow/PIL) is required at runtime. Tk 8.6+ loads PNG natively.
        for name in ("logo.png", "hero.png", "zen_preview.png", "sidebar_grave.png"):
            p = asset_path(name)
            try:
                self.images[name] = tk.PhotoImage(file=str(p))
            except tk.TclError as exc:
                raise RuntimeError(
                    f"Could not load UI image {p.name}. "
                    "Please use a standard Python 3 installation with Tkinter/Tk 8.6+."
                ) from exc

    def _build_shell(self):
        self.header = tk.Frame(self, bg="#06202c", height=104, highlightbackground=GREEN_DARK, highlightthickness=1)
        self.header.pack(fill="x")
        self.header.pack_propagate(False)

        tk.Label(self.header, image=self.images["logo.png"], bg="#06202c").pack(side="left", padx=(12, 8), pady=6)
        titlebox = tk.Frame(self.header, bg="#06202c")
        titlebox.pack(side="left", fill="y", padx=8)
        tk.Label(titlebox, text=APP_TITLE, bg="#06202c", fg=TEXT,
                 font=("Segoe UI Semibold", 20)).pack(anchor="w", pady=(15, 0))
        tk.Label(titlebox, text=f"Profile Editor  •  PS4 Save Data   |   Region: {REGION}",
                 bg="#06202c", fg="#c4dbe6", font=("Segoe UI", 10)).pack(anchor="w", pady=(3, 0))
        self.file_badge = tk.Label(titlebox, text="No save loaded", bg="#103244", fg="#cfe8d4",
                                   font=("Segoe UI Semibold", 8), padx=8, pady=3)
        self.file_badge.pack(anchor="w", pady=(7, 0))

        actions = tk.Frame(self.header, bg="#06202c")
        actions.pack(side="right", padx=14)
        self.open_btn = self._button(actions, "📂  Open Save", self.open_file, width=13)
        self.open_btn.pack(side="left", padx=4, pady=25)
        self.save_btn = self._button(actions, "💾  Save", self.save_file, width=10, accent=True)
        self.save_btn.pack(side="left", padx=4)
        self.backup_btn = self._button(actions, "⟳  Backup", self.create_backup, width=10)
        self.backup_btn.pack(side="left", padx=4)
        self.max_btn = self._button(actions, "♛  Safe Max", self.max_all, width=11)
        self.max_btn.pack(side="left", padx=4)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        self.sidebar = tk.Frame(body, bg=SIDEBAR, width=205, highlightbackground="#184759", highlightthickness=1)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        nav = [
            ("Overview", "⌂"), ("Progress", "▥"), ("In-Game", "☀"),
            ("Plants", "❧"), ("Zen Garden", "♨"),
            ("Shop", "▣"), ("Challenges", "♜"), ("Achievements", "★"),
            ("Trophy Prep", "PS"), ("Settings", "⚙"),
        ]
        for name, icon in nav:
            b = tk.Button(self.sidebar, text=f"{icon:>2}   {name}", command=lambda n=name: self.show_page(n),
                          anchor="w", bg=SIDEBAR, fg=TEXT, activebackground="#174b3c",
                          activeforeground=TEXT, bd=0, relief="flat", padx=18, pady=12,
                          font=("Segoe UI Semibold", 11), cursor="hand2")
            b.pack(fill="x", padx=8, pady=2)
            self.nav_buttons[name] = b

        tk.Label(self.sidebar, image=self.images["sidebar_grave.png"], bg=SIDEBAR).pack(side="bottom", pady=(0, 4))

        self.content = tk.Frame(body, bg=BG)
        self.content.pack(side="left", fill="both", expand=True)

        self.status = tk.StringVar(value="Open a decrypted CUSA55613 0.pb.dat profile.")
        statusbar = tk.Frame(self, bg="#061722", height=30, highlightbackground="#174458", highlightthickness=1)
        statusbar.pack(fill="x", side="bottom")
        tk.Label(statusbar, textvariable=self.status, bg="#061722", fg="#d4e8ef",
                 font=("Segoe UI", 9)).pack(side="left", padx=12)
        tk.Label(statusbar, text=f"🎮  {REGION}", bg="#061722", fg="#d4e8ef",
                 font=("Segoe UI", 9)).pack(side="right", padx=14)

    def _build_pages(self):
        for name in self.nav_buttons:
            page = ScrollPage(self.content, BG)
            page.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.pages[name] = page
        self._build_overview()
        self._build_progress()
        self._build_ingame()
        self._build_plants()
        self._build_zen()
        self._build_shop()
        self._build_challenges()
        self._build_achievements()
        self._build_trophy()
        self._build_settings()

    def show_page(self, name):
        self.current_page = name
        self.pages[name].tkraise()
        for n, b in self.nav_buttons.items():
            b.configure(bg="#1b7f3c" if n == name else SIDEBAR,
                        activebackground="#239949" if n == name else "#174b3c")

    def _on_mousewheel(self, event):
        page = self.pages.get(self.current_page)
        if not page:
            return
        try:
            delta = int(-event.delta / 120)
            if delta:
                page.canvas.yview_scroll(delta, "units")
        except tk.TclError:
            pass

    def _button(self, parent, text, cmd, width=None, accent=False):
        return tk.Button(parent, text=text, command=cmd, width=width, cursor="hand2",
                         bg=(GREEN_DARK if accent else PANEL_2), fg=TEXT,
                         activebackground=("#29aa50" if accent else PANEL_3), activeforeground=TEXT,
                         bd=0, relief="flat", padx=12, pady=9, font=("Segoe UI Semibold", 10))

    def _section(self, parent, title, subtitle=None):
        box = tk.Frame(parent, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        head = tk.Frame(box, bg=PANEL)
        head.pack(fill="x", padx=14, pady=(11, 8))
        tk.Label(head, text=title, bg=PANEL, fg=TEXT, font=("Segoe UI Semibold", 13)).pack(anchor="w")
        if subtitle:
            tk.Label(head, text=subtitle, bg=PANEL, fg=MUTED, font=("Segoe UI", 9), wraplength=850,
                     justify="left").pack(anchor="w", pady=(2, 0))
        return box

    def _card(self, parent, title, var, icon="●", width=18, on_change=None):
        box = tk.Frame(parent, bg=PANEL_2, highlightbackground=BORDER, highlightthickness=1)
        tk.Label(box, text=icon, bg=PANEL_2, fg=GOLD, font=("Segoe UI Symbol", 26)).pack(side="left", padx=(12, 8), pady=10)
        inner = tk.Frame(box, bg=PANEL_2)
        inner.pack(side="left", fill="both", expand=True, padx=(0, 12), pady=9)
        tk.Label(inner, text=title, bg=PANEL_2, fg="#d6e6ed", font=("Segoe UI Semibold", 9)).pack(anchor="w")
        e = tk.Entry(inner, textvariable=var, bg="#071e29", fg=TEXT, insertbackground=TEXT,
                     relief="flat", bd=0, font=("Segoe UI Semibold", 13), width=width)
        e.pack(fill="x", pady=(5, 0), ipady=4)
        e.bind("<KeyRelease>", lambda _e: on_change() if on_change else self._mark())
        return box

    def _page_title(self, parent, title, sub):
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill="x", padx=20, pady=(18, 12))
        tk.Label(wrap, text=title, bg=BG, fg=TEXT, font=("Segoe UI Semibold", 21)).pack(anchor="w")
        tk.Label(wrap, text=sub, bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 0))

    def _build_overview(self):
        page = self.pages["Overview"].inner
        self._page_title(page, "Overview", "Edit your profile, progression, garden and game settings.")

        area = tk.Frame(page, bg=BG)
        area.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        left = tk.Frame(area, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(area, bg=BG, width=470)
        right.pack(side="right", fill="y", padx=(16, 0))
        right.pack_propagate(False)

        self.ov = {k: tk.StringVar(value="—") for k in ["coins","level","finishedAdventure","ripLevel","tree","vase","izombie"]}
        top = tk.Frame(left, bg=BG)
        top.pack(fill="x")
        for i, spec in enumerate([
            ("Coins", "coins", "◉"), ("Adventure Level", "level", "☀"), ("Adventure Completions", "finishedAdventure", "▧")
        ]):
            c = self._card(top, spec[0], self.ov[spec[1]], spec[2], on_change=lambda k=spec[1]: self._overview_changed(k))
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i==0 else 6, 0))
            top.columnconfigure(i, weight=1)

        second = tk.Frame(left, bg=BG)
        second.pack(fill="x", pady=(10, 0))
        for i, spec in enumerate([
            ("R.I.P. Progress", "ripLevel", "RIP"), ("Tree of Wisdom", "tree", "♧"),
            ("Vasebreaker Endless", "vase", "◒"), ("I, Zombie Endless", "izombie", "☠")
        ]):
            c = self._card(second, spec[0], self.ov[spec[1]], spec[2], width=12, on_change=lambda k=spec[1]: self._overview_changed(k))
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i==0 else 6, 0))
            second.columnconfigure(i, weight=1)

        mid = tk.Frame(left, bg=BG)
        mid.pack(fill="x", pady=(10,0))
        modes = self._section(mid, "Game Modes & Settings")
        modes.pack(side="left", fill="both", expand=True, padx=(0,5))
        modesbody = tk.Frame(modes, bg=PANEL)
        modesbody.pack(fill="x", padx=14, pady=(0,12))
        self.quick_bool_vars = {}
        quick_keys = [
            ("mustacheModeActive","Mustache Mode"),("futureModeActive","Future Mode"),
            ("pinataModeActive","Pinata Mode"),("daisesModeActive","Daisies Mode"),
            ("harderEnabled","Harder Mode"),("hasUnlockedSurvivalMode","Unlock Survival"),
        ]
        for idx,(key,label) in enumerate(quick_keys):
            v=tk.BooleanVar(value=False); self.quick_bool_vars[key]=v
            cb=tk.Checkbutton(modesbody,text=label,variable=v,bg=PANEL,fg=TEXT,selectcolor="#0b5d2a",
                              activebackground=PANEL,activeforeground=TEXT,font=("Segoe UI",10),
                              command=lambda k=key:self._quick_bool_changed(k))
            cb.grid(row=idx//2,column=idx%2,sticky="w",padx=(0,24),pady=5)

        progress = self._section(mid, "Game Progress")
        progress.pack(side="left", fill="both", expand=True, padx=(5,0))
        self.progress_labels={}
        self.progress_bars={}
        progress_max={"Mini-Games":20,"Puzzle":18,"Survival":10,"Cloudy Day":13,"Co-op":15}
        for name in ["Mini-Games","Puzzle","Survival","Cloudy Day","Co-op"]:
            row=tk.Frame(progress,bg=PANEL); row.pack(fill="x",padx=14,pady=4)
            tk.Label(row,text=name,bg=PANEL,fg=TEXT,width=13,anchor="w",font=("Segoe UI",9)).pack(side="left")
            bar=ttk.Progressbar(row,maximum=progress_max[name],value=0,style="PvZ.Horizontal.TProgressbar")
            bar.pack(side="left",fill="x",expand=True,padx=8)
            lbl=tk.Label(row,text="—",bg=PANEL,fg=TEXT,width=8,font=("Segoe UI Semibold",9)); lbl.pack(side="right")
            self.progress_labels[name]=lbl
            self.progress_bars[name]=bar

        summary = self._section(left, "Shop & Unlock Summary")
        summary.pack(fill="x", pady=(10,0))
        self.summary_text = tk.Label(summary, text="Open a save to see unlock status.", bg=PANEL, fg=MUTED,
                                     justify="left", anchor="w", font=("Segoe UI",9))
        self.summary_text.pack(fill="x", padx=14, pady=(0,12))

        tk.Label(right, image=self.images["hero.png"], bg=BG).pack(fill="x")
        zbox=self._section(right,"Zen Garden Preview")
        zbox.pack(fill="x",pady=(12,0))
        tk.Label(zbox,image=self.images["zen_preview.png"],bg=PANEL).pack(fill="x",padx=8,pady=(0,8))
        self.zen_summary=tk.Label(zbox,text="—",bg=PANEL,fg="#d8ece0",font=("Segoe UI Semibold",10))
        self.zen_summary.pack(anchor="e",padx=12,pady=(0,10))

    def _build_progress(self):
        page=self.pages["Progress"].inner
        self._page_title(page,"Progress","Core story values, mode unlocks and special records.")
        core=self._section(page,"Core Values")
        core.pack(fill="x",padx=20,pady=(0,12))
        body=tk.Frame(core,bg=PANEL); body.pack(fill="x",padx=14,pady=(0,14))
        self.core_vars={}
        for r,(key,label,mn,mx) in enumerate([
            ("level","Adventure level",0,9999),("ripLevel","R.I.P. level",0,9999),("coins","Coins",0,MAX_I32),
            ("finishedAdventure","Adventure completions",0,9999),("finishedRipAdventure","R.I.P. completions",0,9999),
        ]):
            tk.Label(body,text=label,bg=PANEL,fg=TEXT,width=28,anchor="w").grid(row=r,column=0,sticky="w",pady=4)
            v=tk.StringVar(value="0"); self.core_vars[key]=(v,mn,mx)
            e=tk.Entry(body,textvariable=v,bg="#071e29",fg=TEXT,insertbackground=TEXT,relief="flat",width=22)
            e.grid(row=r,column=1,sticky="w",pady=4,ipady=5); e.bind("<KeyRelease>",lambda _e,k=key:self._core_changed(k))
        self._button(body,"Max Coins",lambda:self._set_core_value("coins","999999999"),width=12).grid(row=2,column=2,padx=10)

        unlock=self._section(page,"Unlock & Notification Flags")
        unlock.pack(fill="x",padx=20,pady=(0,12))
        ub=tk.Frame(unlock,bg=PANEL); ub.pack(fill="x",padx=14,pady=(0,14))
        self.unlock_vars={}
        for i,(key,label) in enumerate([
            ("hasUnlockedMinigames","Mini-Games unlocked"),("hasUnlockedPuzzleMode","Puzzle Mode unlocked"),
            ("hasUnlockedSurvivalMode","Survival Mode unlocked"),("hasNewMiniGame","New Mini-Game marker"),
            ("hasNewVasebreaker","New Vasebreaker marker"),("hasNewIZombie","New I, Zombie marker"),
            ("hasNewSurvival","New Survival marker"),("hasSeenStinky","Has seen Stinky"),
        ]):
            v=tk.BooleanVar(value=False); self.unlock_vars[key]=v
            tk.Checkbutton(ub,text=label,variable=v,bg=PANEL,fg=TEXT,selectcolor="#0b5d2a",
                           activebackground=PANEL,activeforeground=TEXT,command=lambda k=key:self._unlock_changed(k)).grid(row=i//2,column=i%2,sticky="w",padx=(0,35),pady=4)
        self._button(ub,"Unlock Main Modes",self.unlock_main_modes,width=18).grid(row=4,column=0,sticky="w",pady=(8,0))

        modes=self._section(page,"Mode / Cheat State Flags")
        modes.pack(fill="x",padx=20,pady=(0,20))
        mb=tk.Frame(modes,bg=PANEL); mb.pack(fill="x",padx=14,pady=(0,14))
        self.bool_vars={}
        for i,(key,label) in enumerate(BOOL_FIELDS):
            v=tk.BooleanVar(value=False); self.bool_vars[key]=v
            tk.Checkbutton(mb,text=label,variable=v,bg=PANEL,fg=TEXT,selectcolor="#0b5d2a",
                           activebackground=PANEL,activeforeground=TEXT,command=lambda k=key:self._bool_changed(k)).grid(row=i//2,column=i%2,sticky="w",padx=(0,32),pady=4)

    def _build_ingame(self):
        page = self.pages["In-Game"].inner
        self._page_title(
            page,
            "In-Game Save • Sun + Streak Editor",
            "Edit Sun and the live endless streak / Survival stage stored in raw-DEFLATE .ig.dat saves. This is separate from 0.pb.dat.",
        )

        file_sec = self._section(
            page,
            "In-Progress Save",
            "Open the .ig.dat that belongs to the current run. The editor scans populated AcQS/SaveHeader records and preserves every byte except the selected Sun and streak/stage values.",
        )
        file_sec.pack(fill="x", padx=20, pady=(0, 12))
        row = tk.Frame(file_sec, bg=PANEL)
        row.pack(fill="x", padx=14, pady=(0, 14))
        self.ig_open_btn = self._button(row, "📂  Open .ig.dat", self.open_ingame_file, width=15, accent=True)
        self.ig_open_btn.pack(side="left", padx=(0, 6))
        self.ig_save_btn = self._button(row, "💾  Save In-Game", self.save_ingame_file, width=16)
        self.ig_save_btn.pack(side="left", padx=6)
        self.ig_backup_btn = self._button(row, "⟳  Backup", self.create_ingame_backup, width=11)
        self.ig_backup_btn.pack(side="left", padx=6)
        self.ig_file_label = tk.Label(row, text="No .ig.dat loaded", bg=PANEL, fg=MUTED,
                                     font=("Segoe UI", 9), anchor="w")
        self.ig_file_label.pack(side="left", padx=(14, 0), fill="x", expand=True)

        list_sec = self._section(
            page,
            "Saved Run Slots",
            "P1/P2 Sun and the serialized Challenge.mSurvivalStage value are mapped. Level ID 115 is I, Zombie Endless; 105 is Vasebreaker Endless; 95 is Survival Day Endless.",
        )
        list_sec.pack(fill="x", padx=20, pady=(0, 12))
        table_wrap = tk.Frame(list_sec, bg=PANEL)
        table_wrap.pack(fill="x", padx=14, pady=(0, 14))
        cols = ("slot", "level", "version", "p1", "p2", "stage", "size")
        self.ig_tree = ttk.Treeview(table_wrap, columns=cols, show="headings", height=7, selectmode="browse")
        heads = {
            "slot": "Slot", "level": "Level / Mode", "version": "Save Ver.",
            "p1": "P1 Sun", "p2": "P2 Sun", "stage": "Streak / Stage", "size": "Payload",
        }
        widths = {"slot": 60, "level": 200, "version": 85, "p1": 95, "p2": 95, "stage": 120, "size": 115}
        for c in cols:
            self.ig_tree.heading(c, text=heads[c])
            self.ig_tree.column(c, width=widths[c], anchor="center", stretch=(c == "size"))
        self.ig_tree.pack(fill="x")
        self.ig_tree.bind("<<TreeviewSelect>>", self._on_ig_tree_select)

        edit_sec = self._section(
            page,
            "Selected Run",
            f"Replanted stores Sun per player and endless progress in Challenge.mSurvivalStage. Max Sun uses {MAX_SUN:,}.",
        )
        edit_sec.pack(fill="x", padx=20, pady=(0, 12))
        form = tk.Frame(edit_sec, bg=PANEL)
        form.pack(fill="x", padx=14, pady=(0, 14))

        self.ig_level_text = tk.StringVar(value="No slot selected")
        tk.Label(form, textvariable=self.ig_level_text, bg=PANEL, fg=GOLD,
                 font=("Segoe UI Semibold", 12)).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))

        self.ig_p1_var = tk.StringVar(value="0")
        self.ig_p2_var = tk.StringVar(value="0")
        self.ig_stage_var = tk.StringVar(value="0")
        for var in (self.ig_p1_var, self.ig_p2_var, self.ig_stage_var):
            var.trace_add("write", self._on_ig_form_changed)

        tk.Label(form, text="Player 1 Sun", bg=PANEL, fg=TEXT, font=("Segoe UI", 10)).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=5)
        self.ig_p1_entry = tk.Entry(form, textvariable=self.ig_p1_var, bg=PANEL_2, fg=TEXT,
                                    insertbackground=TEXT, relief="flat", width=14, font=("Segoe UI Semibold", 11))
        self.ig_p1_entry.grid(row=1, column=1, sticky="w", padx=(0, 24), pady=5, ipady=6)
        tk.Label(form, text="Player 2 Sun", bg=PANEL, fg=TEXT, font=("Segoe UI", 10)).grid(row=1, column=2, sticky="w", padx=(0, 8), pady=5)
        self.ig_p2_entry = tk.Entry(form, textvariable=self.ig_p2_var, bg=PANEL_2, fg=TEXT,
                                    insertbackground=TEXT, relief="flat", width=14, font=("Segoe UI Semibold", 11))
        self.ig_p2_entry.grid(row=1, column=3, sticky="w", pady=5, ipady=6)

        self.ig_stage_label = tk.Label(form, text="Current Streak / Stage", bg=PANEL, fg=TEXT, font=("Segoe UI", 10))
        self.ig_stage_label.grid(row=2, column=0, sticky="w", padx=(0, 8), pady=5)
        self.ig_stage_entry = tk.Entry(form, textvariable=self.ig_stage_var, bg=PANEL_2, fg=TEXT,
                                       insertbackground=TEXT, relief="flat", width=14, font=("Segoe UI Semibold", 11))
        self.ig_stage_entry.grid(row=2, column=1, sticky="w", padx=(0, 24), pady=5, ipady=6)
        self.ig_stage_hint = tk.Label(form, text="", bg=PANEL, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.ig_stage_hint.grid(row=2, column=2, columnspan=2, sticky="w", pady=5)

        buttons = tk.Frame(form, bg=PANEL)
        buttons.grid(row=3, column=0, columnspan=4, sticky="w", pady=(12, 0))
        self.ig_apply_btn = self._button(buttons, "Apply Values", self.apply_ingame_values, width=14)
        self.ig_apply_btn.pack(side="left", padx=(0, 6))
        self.ig_max_p1_btn = self._button(buttons, f"Max P1 → {MAX_SUN}", self.max_ingame_p1, width=15, accent=True)
        self.ig_max_p1_btn.pack(side="left", padx=6)
        self.ig_max_both_btn = self._button(buttons, f"Max P1 + P2 → {MAX_SUN}", self.max_ingame_both, width=21)
        self.ig_max_both_btn.pack(side="left", padx=6)

        presets = tk.Frame(form, bg=PANEL)
        presets.grid(row=4, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self.ig_izombie_btn = self._button(presets, "I, Zombie Streak → 10", self.preset_ingame_izombie, width=21, accent=True)
        self.ig_izombie_btn.pack(side="left", padx=(0, 6))
        self.ig_vase_btn = self._button(presets, "Vasebreaker Streak → 15", self.preset_ingame_vase, width=23)
        self.ig_vase_btn.pack(side="left", padx=6)
        self.ig_survival_btn = self._button(presets, "Survival → 40 Flags", self.preset_ingame_survival, width=20)
        self.ig_survival_btn.pack(side="left", padx=6)

        proof = self._section(
            page,
            "Verified Mapping",
            "The Sun pair is stable across all supplied CUSA55613 board payloads. The live Challenge streak/stage field is independently verified: Level ID 115 contains a saved 'Current Streak: 10' message and the mapped value is 10; Level ID 105 contains 'Current Streak: 15' and the mapped value is 15. The screenshot-matching new Level ID 115 run reads P1 = 100, P2 = 0 and current streak = 0.",
        )
        proof.pack(fill="x", padx=20, pady=(0, 20))

        self._set_ingame_state(False)

    def _set_ingame_state(self, loaded: bool):
        state = "normal" if loaded else "disabled"
        for name in ("ig_save_btn", "ig_backup_btn", "ig_apply_btn", "ig_max_p1_btn", "ig_max_both_btn",
                     "ig_izombie_btn", "ig_vase_btn", "ig_survival_btn", "ig_p1_entry", "ig_p2_entry", "ig_stage_entry"):
            w = getattr(self, name, None)
            if w is not None:
                w.configure(state=state)

    def _on_ig_form_changed(self, *_):
        if self._ig_refreshing or self.ig_selected_record is None:
            return
        self.ig_form_dirty = True

    def open_ingame_file(self):
        if self.ig_dirty or self.ig_form_dirty:
            answer = messagebox.askyesnocancel(
                "Unsaved in-game changes",
                "Save the current .ig.dat changes before opening another in-game save?",
            )
            if answer is None:
                return
            if answer and not self.save_ingame_file():
                return
        path = filedialog.askopenfilename(
            title="Open CUSA55613 in-progress save",
            filetypes=[("PvZ in-game save", "*.ig.dat"), ("DAT files", "*.dat"), ("All files", "*.*")],
        )
        if path:
            self.load_ingame_path(Path(path))

    def load_ingame_path(self, path: Path, select_level_id: int | None = None):
        try:
            save = InGameSave(path.read_bytes())
        except Exception as exc:
            messagebox.showerror("Cannot open in-game save", str(exc))
            return False
        self.ig_save = save
        self.ig_path = path
        self.ig_dirty = False
        self.ig_form_dirty = False
        self.ig_selected_record = None
        self._refresh_ingame_tree()
        self._set_ingame_state(True)
        self.ig_file_label.configure(text=f"Loaded: {path.name}  •  {len(save.records)} populated slot(s)")

        target = 0
        if select_level_id is not None:
            for i, r in enumerate(save.records):
                if r.level_id == select_level_id:
                    target = i
                    break
        else:
            # Prefer the screenshot-verified I, Zombie Endless slot when present.
            for i, r in enumerate(save.records):
                if r.level_id == 115:
                    target = i
                    break
        iid = f"ig{target}"
        if self.ig_tree.exists(iid):
            self.ig_tree.selection_set(iid)
            self.ig_tree.focus(iid)
            self.ig_tree.see(iid)
            self._load_ig_record_form(target)
        self.status.set(f"✓ In-game save parsed  •  {path.name}  •  {len(save.records)} populated slot(s)")
        return True

    def _refresh_ingame_tree(self, select_index: int | None = None):
        if not getattr(self, "ig_tree", None):
            return
        for item in self.ig_tree.get_children():
            self.ig_tree.delete(item)
        if not self.ig_save:
            return
        for i, rec in enumerate(self.ig_save.records):
            p1 = self.ig_save.get_sun(i, 1)
            p2 = self.ig_save.get_sun(i, 2)
            mode = self.ig_save.mode_name(i)
            level = f"{rec.level_id}" + (f"  • {mode}" if mode else "")
            stage = self.ig_save.get_run_stage(i) if self.ig_save.has_run_stage(i) else "—"
            if rec.level_id == 95 and stage != "—":
                stage = f"{stage}  (≥{int(stage) * 2} flags)"
            self.ig_tree.insert("", "end", iid=f"ig{i}", values=(i + 1, level, rec.version, p1, p2, stage, f"{rec.data_size:,} B"))
        if select_index is not None and 0 <= select_index < len(self.ig_save.records):
            iid = f"ig{select_index}"
            self.ig_tree.selection_set(iid)
            self.ig_tree.focus(iid)

    def _on_ig_tree_select(self, _event=None):
        if not self.ig_save:
            return
        selection = self.ig_tree.selection()
        if not selection:
            return
        try:
            new_index = int(selection[0][2:])
        except (ValueError, IndexError):
            return
        old_index = self.ig_selected_record
        if old_index is not None and old_index != new_index and self.ig_form_dirty:
            try:
                self._apply_ingame_form(silent=True)
            except Exception as exc:
                messagebox.showerror("Invalid in-game value", str(exc))
                self._ig_refreshing = True
                try:
                    self.ig_tree.selection_set(f"ig{old_index}")
                    self.ig_tree.focus(f"ig{old_index}")
                finally:
                    self._ig_refreshing = False
                return
        self._load_ig_record_form(new_index)

    def _load_ig_record_form(self, index: int):
        if not self.ig_save or not 0 <= index < len(self.ig_save.records):
            return
        rec = self.ig_save.records[index]
        self._ig_refreshing = True
        try:
            self.ig_selected_record = index
            self.ig_p1_var.set(str(self.ig_save.get_sun(index, 1)))
            self.ig_p2_var.set(str(self.ig_save.get_sun(index, 2)))

            mode = self.ig_save.mode_name(index)
            label = f"Slot {index + 1}  •  Level ID {rec.level_id}  •  Save version {rec.version}"
            if mode:
                label += f"  •  {mode}"
            self.ig_level_text.set(label)
            if self.ig_save.has_run_stage(index):
                stage = self.ig_save.get_run_stage(index)
                self.ig_stage_var.set(str(stage))
                self.ig_stage_label.configure(text=self.ig_save.run_stage_label(index))
                if rec.level_id == 95:
                    self.ig_stage_hint.configure(text=f"{stage} completed stages = at least {stage * 2} completed flags")
                elif rec.level_id == 115:
                    self.ig_stage_hint.configure(text="I, Zombie Endless trophy target: streak 10")
                elif rec.level_id == 105:
                    self.ig_stage_hint.configure(text="Vasebreaker Endless trophy target: streak 15")
                else:
                    self.ig_stage_hint.configure(text="Mapped Challenge.mSurvivalStage value")
                self.ig_stage_entry.configure(state="normal")
            else:
                self.ig_stage_var.set("N/A")
                self.ig_stage_label.configure(text="Current Streak / Stage")
                self.ig_stage_hint.configure(text="No verified Challenge block in this slot")
                self.ig_stage_entry.configure(state="disabled")
            self.ig_form_dirty = False
        finally:
            self._ig_refreshing = False

    def _apply_ingame_form(self, silent=False):
        if not self.ig_save or self.ig_selected_record is None:
            raise RuntimeError("No in-game slot is selected")
        p1 = self._parse_int(self.ig_p1_var.get(), "Player 1 Sun", 0, MAX_SUN)
        p2 = self._parse_int(self.ig_p2_var.get(), "Player 2 Sun", 0, MAX_SUN)
        idx = self.ig_selected_record
        stage = None
        if self.ig_save.has_run_stage(idx):
            stage = self._parse_int(self.ig_stage_var.get(), self.ig_save.run_stage_label(idx), 0, MAX_RUN_STAGE)
        self.ig_save.set_sun(idx, p1, 1)
        self.ig_save.set_sun(idx, p2, 2)
        if stage is not None:
            self.ig_save.set_run_stage(idx, stage)
        self.ig_dirty = True
        self.ig_form_dirty = False
        self._refresh_ingame_tree(select_index=idx)
        if not silent:
            extra = f" • {self.ig_save.run_stage_label(idx)} {stage:,}" if stage is not None else ""
            self.status.set(f"In-game values updated • P1 {p1:,} • P2 {p2:,}{extra} • Press Save In-Game")
        return p1, p2, stage

    def apply_ingame_values(self):
        try:
            self._apply_ingame_form(silent=False)
        except Exception as exc:
            messagebox.showerror("Invalid in-game value", str(exc))

    def max_ingame_p1(self):
        if self.ig_selected_record is None:
            return
        self._ig_refreshing = True
        try:
            self.ig_p1_var.set(str(MAX_SUN))
        finally:
            self._ig_refreshing = False
        self.ig_form_dirty = True
        self.apply_ingame_values()

    def max_ingame_both(self):
        if self.ig_selected_record is None:
            return
        self._ig_refreshing = True
        try:
            self.ig_p1_var.set(str(MAX_SUN))
            self.ig_p2_var.set(str(MAX_SUN))
        finally:
            self._ig_refreshing = False
        self.ig_form_dirty = True
        self.apply_ingame_values()

    def _preset_ingame_stage(self, expected_level: int, value: int, label: str):
        if not self.ig_save or self.ig_selected_record is None:
            return
        rec = self.ig_save.records[self.ig_selected_record]
        if rec.level_id != expected_level:
            messagebox.showerror("Wrong in-game slot", f"Select the {label} slot first.\n\nExpected Level ID {expected_level}, selected {rec.level_id}.")
            return
        if not self.ig_save.has_run_stage(self.ig_selected_record):
            messagebox.showerror("Streak unavailable", "No verified Challenge streak/stage block was found in this slot.")
            return
        self._ig_refreshing = True
        try:
            self.ig_stage_var.set(str(value))
        finally:
            self._ig_refreshing = False
        self.ig_form_dirty = True
        self.apply_ingame_values()

    def preset_ingame_izombie(self):
        self._preset_ingame_stage(115, 10, "I, Zombie Endless")

    def preset_ingame_vase(self):
        self._preset_ingame_stage(105, 15, "Vasebreaker Endless")

    def preset_ingame_survival(self):
        # Survival Endless uses 20 waves per stage and 10 waves per flag, so
        # 20 completed stages represents 40 completed flags before any
        # current-wave contribution. Level ID 95 is verified as Day Endless.
        self._preset_ingame_stage(95, 20, "Survival Day Endless")

    def save_ingame_file(self):
        if not self.ig_save or not self.ig_path:
            return False
        tmp = self.ig_path.with_suffix(self.ig_path.suffix + ".tmp")
        selected = self.ig_selected_record
        selected_level = None
        try:
            if self.ig_form_dirty:
                self._apply_ingame_form(silent=True)
            if selected is not None:
                selected_level = self.ig_save.records[selected].level_id
            out = self.ig_save.compressed_bytes()
            backup = self.ig_path.with_suffix(self.ig_path.suffix + ".bak")
            if not backup.exists():
                shutil.copy2(self.ig_path, backup)
            if tmp.exists():
                tmp.unlink()
            with tmp.open("wb") as fh:
                fh.write(out)
                fh.flush()
                os.fsync(fh.fileno())
            # Full decompression + SaveHeader + exact raw round-trip validation.
            InGameSave(tmp.read_bytes())
            try:
                shutil.copystat(self.ig_path, tmp)
            except OSError:
                pass
            os.replace(tmp, self.ig_path)
            self.load_ingame_path(self.ig_path, select_level_id=selected_level)
            self.status.set(f"✓ In-game save written and verified  •  Backup: {backup.name}")
            messagebox.showinfo("In-game save written", f"Sun / streak changes were saved and verified.\n\nBackup: {backup}")
            return True
        except Exception as exc:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            messagebox.showerror("In-game save failed", str(exc))
            return False

    def create_ingame_backup(self):
        if not self.ig_path:
            return False
        try:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            dest = self.ig_path.with_name(f"{self.ig_path.name}.manual.{stamp}.bak")
            shutil.copy2(self.ig_path, dest)
            self.status.set(f"In-game backup created • {dest.name}")
            messagebox.showinfo("In-game backup", f"Created:\n{dest}")
            return True
        except Exception as exc:
            messagebox.showerror("In-game backup failed", str(exc))
            return False

    def _build_plants(self):
        page=self.pages["Plants"].inner
        self._page_title(page,"Plants","Plant reference and purchasable upgrade ownership.")
        sec=self._section(page,"Upgrade Plants","These nine upgrade plants are represented by the first shop purchase slots.")
        sec.pack(fill="x",padx=20,pady=(0,12))
        b=tk.Frame(sec,bg=PANEL); b.pack(fill="x",padx=14,pady=(0,14))
        self.plant_purchase_vars=[]
        for i,name in enumerate(STORE_ITEMS[:9]):
            v=tk.BooleanVar(value=False); self.plant_purchase_vars.append(v)
            tk.Checkbutton(b,text=name,variable=v,bg=PANEL,fg=TEXT,selectcolor="#0b5d2a",
                           activebackground=PANEL,activeforeground=TEXT,command=lambda idx=i:self._plant_toggle(idx)).grid(row=i//3,column=i%3,sticky="w",padx=(0,35),pady=6)
        self._button(b,"Own All Upgrade Plants",self.own_upgrade_plants,width=22,accent=True).grid(row=4,column=0,columnspan=2,sticky="w",pady=(10,0))
        ref=self._section(page,"Seed Reference")
        ref.pack(fill="x",padx=20,pady=(0,20))
        txt="   •   ".join(SEED_NAMES)
        tk.Label(ref,text=txt,bg=PANEL,fg="#c9dce5",wraplength=1050,justify="left").pack(fill="x",padx=14,pady=(0,14))

    def _build_zen(self):
        page=self.pages["Zen Garden"].inner
        self._page_title(page,"Zen Garden","Edit every mapped field of your existing potted plants with a live visual preview. Changes are written in-place to the verified 80-byte plant records.")

        sec=self._section(page,"Garden Actions","Quick actions affect the existing active plants only. Unknown profile bytes stay untouched.")
        sec.pack(fill="x",padx=20,pady=(0,12))
        b=tk.Frame(sec,bg=PANEL); b.pack(fill="x",padx=14,pady=(0,14))
        self.zen_stats=tk.Label(b,text="No save loaded",bg=PANEL,fg=TEXT); self.zen_stats.pack(side="left")
        self._button(b,"Collect All 40",self.collect_all_zen,width=14).pack(side="right",padx=4)
        self._button(b,"Mature All",self.mature_plants,width=12).pack(side="right",padx=4)
        self._button(b,"Clear All Needs",self.clear_all_zen_needs,width=15).pack(side="right",padx=4)

        editor=self._section(page,"Plant Editor","Select a plant on the left, edit its values on the right, then press Apply Plant. Pressing the main Save button also applies the currently selected plant.")
        editor.pack(fill="both",expand=True,padx=20,pady=(0,12))
        body=tk.Frame(editor,bg=PANEL); body.pack(fill="both",expand=True,padx=12,pady=(0,14))

        left=tk.Frame(body,bg=PANEL)
        left.pack(side="left",fill="both",expand=True,padx=(0,12))
        self.zen_tree=ttk.Treeview(left,columns=("slot","plant","garden","age","need","x","y"),show="headings",height=21,selectmode="browse")
        widths=[("slot",52),("plant",170),("garden",125),("age",85),("need",70),("x",55),("y",55)]
        headings={"slot":"Slot","plant":"Plant","garden":"Garden","age":"Age","need":"Need","x":"X","y":"Y"}
        for col,w in widths:
            self.zen_tree.heading(col,text=headings[col]); self.zen_tree.column(col,width=w,anchor="center")
        ys=ttk.Scrollbar(left,orient="vertical",command=self.zen_tree.yview)
        self.zen_tree.configure(yscrollcommand=ys.set)
        self.zen_tree.pack(side="left",fill="both",expand=True)
        ys.pack(side="right",fill="y")
        self.zen_tree.bind("<<TreeviewSelect>>",self._zen_select)

        right=tk.Frame(body,bg=PANEL_2,width=470,highlightbackground=BORDER,highlightthickness=1)
        right.pack(side="right",fill="y")
        right.pack_propagate(False)
        tk.Label(right,text="Selected Plant",bg=PANEL_2,fg=TEXT,font=("Segoe UI Semibold",13)).pack(anchor="w",padx=14,pady=(12,3))
        self.zen_selected_label=tk.Label(right,text="Select a plant from the list",bg=PANEL_2,fg=MUTED,font=("Segoe UI",9))
        self.zen_selected_label.pack(anchor="w",padx=14,pady=(0,8))

        # Live plant preview. This is drawn with Tkinter primitives so the
        # standalone project still has no Pillow/PIL runtime dependency.
        preview=tk.Frame(right,bg="#081f2b",highlightbackground="#28627a",highlightthickness=1)
        preview.pack(fill="x",padx=14,pady=(0,10))
        top=tk.Frame(preview,bg="#081f2b")
        top.pack(fill="x",padx=10,pady=(8,2))
        tk.Label(top,text="Live Zen Garden Preview",bg="#081f2b",fg=TEXT,
                 font=("Segoe UI Semibold",10)).pack(side="left")
        self.zen_preview_badge=tk.Label(top,text="—",bg="#164257",fg="#d9f4df",
                                        font=("Segoe UI Semibold",8),padx=7,pady=2)
        self.zen_preview_badge.pack(side="right")
        self.zen_preview_canvas=tk.Canvas(preview,width=390,height=190,bg="#0b3340",
                                          highlightthickness=0,bd=0)
        self.zen_preview_canvas.pack(fill="x",padx=8,pady=(4,4))
        self.zen_preview_meta=tk.Label(preview,text="Select a plant to preview it",bg="#081f2b",
                                       fg="#a9c8d4",font=("Segoe UI",8),justify="left",anchor="w")
        self.zen_preview_meta.pack(fill="x",padx=10,pady=(0,8))
        self._zen_preview_ready = True
        self._draw_zen_preview(None)

        self.zen_vars={}
        form=tk.Frame(right,bg=PANEL_2); form.pack(fill="both",expand=True,padx=14)
        row=0
        def field(label,key,kind="entry",values=None):
            nonlocal row
            tk.Label(form,text=label,bg=PANEL_2,fg=MUTED,anchor="w").grid(row=row,column=0,sticky="w",pady=4,padx=(0,8))
            v=tk.StringVar(value=""); self.zen_vars[key]=v
            if kind=="combo":
                w=ttk.Combobox(form,textvariable=v,values=values or [],state="readonly",width=25)
                w.grid(row=row,column=1,sticky="ew",pady=4)
                w.bind("<<ComboboxSelected>>",lambda _e:self._zen_form_mark())
            else:
                w=tk.Entry(form,textvariable=v,bg="#071e29",fg=TEXT,insertbackground=TEXT,relief="flat",width=28)
                w.grid(row=row,column=1,sticky="ew",pady=4,ipady=4)
                w.bind("<KeyRelease>",lambda _e:self._zen_form_mark())
            row+=1
            return w
        form.columnconfigure(1,weight=1)

        self.zen_seed_values=[f"{i:02d}  {name}" for i,name in enumerate(SEED_NAMES[:40])]
        self.zen_garden_values=["0  Main Zen Garden","1  Mushroom Garden","2  Wheelbarrow","3  Aquarium Garden"]
        self.zen_age_values=["0  Sprout","1  Small","2  Medium","3  Mature"]
        self.zen_facing_values=["0  Left / default","1  Right / alternate"]

        field("Plant type","seedType","combo",self.zen_seed_values)
        field("Garden","whichZenGarden","combo",self.zen_garden_values)
        field("Growth stage","plantAge","combo",self.zen_age_values)
        field("Plant need","plantNeed")
        field("X position","x")
        field("Y position","y")
        field("Facing","facing","combo",self.zen_facing_values)
        field("Draw variation","drawVariation")
        field("Times fed","timesFed")
        field("Feedings per grow","feedingsPerGrow")
        field("Last watered (Unix)","lastWateredTime")
        field("Need fulfilled (Unix)","lastNeedFulfilledTime")
        field("Last fertilized (Unix)","lastFertilizedTime")
        field("Last chocolate (Unix)","lastChocolateTime")
        field("Future attribute","futureAttribute")

        self.zen_time_preview=tk.Label(right,text="Timestamps: —",bg=PANEL_2,fg="#84b7c8",font=("Segoe UI",8),
                                       justify="left",wraplength=390)
        self.zen_time_preview.pack(fill="x",padx=14,pady=(4,2))

        btns=tk.Frame(right,bg=PANEL_2); btns.pack(fill="x",padx=14,pady=(8,14))
        self._button(btns,"Apply Plant",self.apply_selected_zen,width=13,accent=True).pack(side="left",padx=(0,5))
        self._button(btns,"Mature",self.mature_selected_zen,width=10).pack(side="left",padx=5)
        self._button(btns,"Clear Need",self.clear_selected_zen_need,width=11).pack(side="left",padx=5)

        raw=self._section(page,"Field Notes")
        raw.pack(fill="x",padx=20,pady=(0,20))
        tk.Label(raw,text="Garden IDs observed in your save: 0 = Main, 1 = Mushroom, 3 = Aquarium; ID 2 is reserved for the Wheelbarrow slot. Growth stages use 0–3. Plant Need and variation remain numeric because their exact enum names have not been verified. Timestamp fields are Unix seconds; 0 means no recorded time.",bg=PANEL,fg=MUTED,wraplength=1080,justify="left").pack(fill="x",padx=14,pady=(0,14))

    def _draw_zen_preview(self, values):
        """Draw a lightweight live preview for the selected Zen Garden plant."""
        if not getattr(self, "_zen_preview_ready", False):
            return
        c=self.zen_preview_canvas
        c.delete("all")
        W=max(390, int(c.winfo_width() or 390)); H=190
        # Garden backdrop.
        c.create_rectangle(0,0,W,H,fill="#0f4552",outline="")
        c.create_oval(-60,-70,110,100,fill="#214f57",outline="")
        c.create_oval(W-90,-55,W+80,115,fill="#173d4c",outline="")
        c.create_rectangle(0,145,W,H,fill="#174d35",outline="")

        for x in range(12,W,26):
            c.create_line(x,148,x-4,138,fill="#4b8b4c",width=2)
            c.create_line(x,148,x+4,136,fill="#3f7b43",width=2)
        if not values:
            c.create_text(W//2,82,text="ZEN GARDEN",fill="#d6e9de",font=("Segoe UI Semibold",18))
            c.create_text(W//2,108,text="Select a plant from the list",fill="#8fb4c1",font=("Segoe UI",9))
            self.zen_preview_badge.configure(text="—")
            self.zen_preview_meta.configure(text="Select a plant to preview it")
            return

        st=values.get("seedType",0); age=max(0,min(int(values.get("plantAge",0)),3))
        garden=int(values.get("whichZenGarden",0)); facing=int(values.get("facing",0))
        name=SEED_NAMES[st] if 0 <= st < len(SEED_NAMES) else f"Seed {st}"
        scale=(0.50,0.67,0.84,1.0)[age]
        cx=W//2; base=145
        # Pot.
        pw=int(64*scale); ph=int(34*scale)
        c.create_polygon(cx-pw//2,base-ph,cx+pw//2,base-ph,cx+int(pw*.38),base,cx-int(pw*.38),base,
                         fill="#a86235",outline="#d79a61",width=2)
        c.create_rectangle(cx-pw//2-3,base-ph-8,cx+pw//2+3,base-ph+2,fill="#c77a42",outline="#e0a56e")
        y0=base-ph-8
        if age == 0:
            c.create_line(cx,y0,cx,y0-26,fill="#53b85c",width=5)
            c.create_oval(cx-20,y0-17,cx-2,y0-7,fill="#5bc768",outline="#2c7b3f")
            c.create_oval(cx+2,y0-22,cx+21,y0-10,fill="#5bc768",outline="#2c7b3f")
        else:
            self._draw_preview_species(c,name,cx,y0,scale,facing)

        age_name=self._age_label(age); garden_name=self._garden_label(garden)
        c.create_text(12,12,text=name,anchor="nw",fill="#f5fbf6",font=("Segoe UI Semibold",14))
        c.create_text(12,35,text=f"{age_name} • {garden_name}",anchor="nw",fill="#c4dce5",font=("Segoe UI",9))
        self.zen_preview_badge.configure(text=age_name.upper())
        slot=self.zen_selected_slot if self.zen_selected_slot is not None else "—"
        need=values.get("plantNeed","—"); x=values.get("x","—"); y=values.get("y","—")
        face="Right" if facing else "Left"
        self.zen_preview_meta.configure(text=f"Slot {slot}  •  {name}  •  {garden_name}  •  Need {need}\nPosition: X {x}, Y {y}  •  Facing: {face}")

    def _draw_preview_species(self,c,name,cx,y0,scale,facing):
        """Stylized, non-sprite plant renderer used by the live preview."""
        stem="#4fbf58"; leaf="#55ca61"; dark="#27813a"
        def stem_and_leaves(height=62):
            h=int(height*scale)
            c.create_line(cx,y0,cx,y0-h,fill=stem,width=max(4,int(7*scale)))
            ly=y0-int(h*.42)
            c.create_oval(cx-int(34*scale),ly-int(8*scale),cx-2,ly+int(10*scale),fill=leaf,outline=dark,width=2)
            c.create_oval(cx+2,ly-int(11*scale),cx+int(34*scale),ly+int(8*scale),fill=leaf,outline=dark,width=2)
            return y0-h
        low=name.lower()
        if "wall-nut" in low or "tall-nut" in low or "explode-o-nut" in low:
            hh=int((82 if "tall" in low or "giant" in low else 62)*scale); ww=int((66 if "giant" in low else 48)*scale)
            c.create_oval(cx-ww,y0-hh,cx+ww,y0+2,fill="#a87843",outline="#d0a36a",width=3)
            c.create_oval(cx-int(19*scale),y0-int(hh*.62),cx-int(9*scale),y0-int(hh*.48),fill="#102b35",outline="")
            c.create_oval(cx+int(9*scale),y0-int(hh*.62),cx+int(19*scale),y0-int(hh*.48),fill="#102b35",outline="")
            return
        if "shroom" in low:
            top=stem_and_leaves(38)
            ww=int(48*scale); hh=int(24*scale)
            color="#8b5dc7" if "sun-shroom" not in low else "#e5c95b"
            c.create_oval(cx-ww,top-hh,cx+ww,top+hh,fill=color,outline="#d4c0ec",width=2)
            c.create_rectangle(cx-int(10*scale),top+hh-2,cx+int(10*scale),y0,fill="#e4d8c5",outline="")
            return
        if "sunflower" in low or "marigold" in low:
            top=stem_and_leaves(70); r=int(18*scale); pr=int(13*scale)
            for dx,dy in ((0,-30),(21,-21),(30,0),(21,21),(0,30),(-21,21),(-30,0),(-21,-21)):
                c.create_oval(top*0+cx+int(dx*scale)-pr,top+int(dy*scale)-pr,cx+int(dx*scale)+pr,top+int(dy*scale)+pr,fill="#ffd34f",outline="#e0a821")
            c.create_oval(cx-r,top-r,cx+r,top+r,fill="#78472c",outline="#d29a51",width=2)
            return
        if "cactus" in low:
            h=int(86*scale); w=int(17*scale)
            c.create_rectangle(cx-w,y0-h,cx+w,y0,fill="#45a65a",outline="#7bd67c",width=2)
            c.create_oval(cx-w,y0-h-int(10*scale),cx+w,y0-h+int(10*scale),fill="#45a65a",outline="#7bd67c")
            c.create_line(cx-w,y0-int(h*.55),cx-int(37*scale),y0-int(h*.55),fill="#45a65a",width=max(5,int(10*scale)))
            c.create_line(cx+int(37*scale),y0-int(h*.35),cx+w,y0-int(h*.35),fill="#45a65a",width=max(5,int(10*scale)))
            return
        if any(k in low for k in ("cherry","jalapeno")):
            top=stem_and_leaves(45); r=int(19*scale)
            if "jalapeno" in low:
                c.create_oval(cx-int(16*scale),top-int(15*scale),cx+int(16*scale),top+int(45*scale),fill="#e34f3f",outline="#ff8b67",width=2)
            else:
                c.create_oval(cx-int(31*scale),top-r,cx-int(2*scale),top+r,fill="#e04b45",outline="#ff8b74",width=2)
                c.create_oval(cx+int(2*scale),top-r,cx+int(31*scale),top+r,fill="#e04b45",outline="#ff8b74",width=2)
            return
        if "chomper" in low:
            top=stem_and_leaves(65); ww=int(42*scale); hh=int(28*scale)
            c.create_oval(cx-ww,top-hh,cx+ww,top+hh,fill="#8857b5",outline="#c191e6",width=2)
            c.create_arc(cx-ww+4,top-hh+4,cx+ww-4,top+hh-4,start=200,extent=140,style="arc",outline="#f2d9ff",width=max(2,int(4*scale)))
            return
        if "pumpkin" in low:
            ww=int(50*scale); hh=int(38*scale)
            c.create_oval(cx-ww,y0-2*hh,cx+ww,y0,fill="#e88235",outline="#f3b45f",width=3)
            return
        if "garlic" in low:
            ww=int(38*scale); hh=int(55*scale)
            c.create_oval(cx-ww,y0-hh,cx+ww,y0,fill="#f0ead6",outline="#cfc7b1",width=2)
            return
        if "starfruit" in low:
            top=stem_and_leaves(56); r=int(38*scale); import math
            pts=[]
            for i in range(10):
                ang=-math.pi/2+i*math.pi/5; rr=r if i%2==0 else r*.45
                pts.extend([cx+rr*math.cos(ang), top+rr*math.sin(ang)])
            c.create_polygon(*pts,fill="#f2cf4c",outline="#fff09a",width=2)
            return
        if "lily" in low or "kelp" in low or "sea-shroom" in low or "cattail" in low:
            c.create_oval(cx-int(60*scale),y0-int(28*scale),cx+int(60*scale),y0+int(2*scale),fill="#4ca975",outline="#87d398",width=2)
            top=stem_and_leaves(52)
            c.create_oval(cx-int(22*scale),top-int(18*scale),cx+int(22*scale),top+int(18*scale),fill="#70c86e",outline="#a4ee9e",width=2)
            return
        if any(k in low for k in ("cabbage","kernel","melon","cob cannon")):
            top=stem_and_leaves(55); r=int(25*scale)
            color="#79b850" if "melon" not in low else "#5f9f58"
            c.create_oval(cx-r,top-r,cx+r,top+r,fill=color,outline="#a5db7e",width=2)
            return
        # Default pea/leafy plant renderer.
        top=stem_and_leaves(68); r=int(26*scale)
        head="#54b95c" if "snow" not in low and "winter" not in low else "#7ebed2"
        c.create_oval(cx-r,top-r,cx+r,top+r,fill=head,outline="#8fdd91",width=2)
        direction=1 if facing else -1
        sx=cx+direction*int(22*scale)
        c.create_oval(sx-direction*int(2*scale)-int(17*scale),top-int(12*scale),sx+direction*int(2*scale)+int(17*scale),top+int(12*scale),fill=head,outline="#8fdd91",width=2)
        c.create_oval(cx-direction*int(7*scale)-int(4*scale),top-int(9*scale),cx-direction*int(7*scale)+int(4*scale),top-int(1*scale),fill="#0a2c35",outline="")

    def _update_zen_preview_from_form(self):
        if not getattr(self,"_zen_preview_ready",False):
            return
        if not self.profile or self.zen_selected_slot is None:
            self._draw_zen_preview(None); return
        try:
            def combo(key, default=0):
                try: return int(str(self.zen_vars[key].get()).strip().split()[0])
                except Exception: return default
            def integer(key, default=0):
                try: return int(str(self.zen_vars[key].get()).strip(),0)
                except Exception: return default
            vals={
                "seedType":combo("seedType"),"whichZenGarden":combo("whichZenGarden"),
                "plantAge":combo("plantAge"),"facing":combo("facing"),
                "plantNeed":integer("plantNeed"),"x":integer("x"),"y":integer("y"),
            }
            self._draw_zen_preview(vals)
        except tk.TclError:
            pass

    @staticmethod
    def _zen_combo_number(text, label):
        try:
            return int(str(text).strip().split()[0])
        except Exception:
            raise ValueError(f"{label}: choose a valid value")

    @staticmethod
    def _format_timestamp(value):
        try:
            value = int(value)
            if value <= 0:
                return "Never"
            return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        except (ValueError, OSError, OverflowError):
            return "Out of range"

    def _zen_form_mark(self):
        if not self.profile or self.zen_selected_slot is None:
            return
        self.zen_form_dirty = True
        self._update_zen_preview_from_form()
        self._mark()

    def _load_zen_slot(self, slot):
        if not self.profile or not (0 <= slot < 200):
            return
        pp=self.profile.potted_plant(slot)
        st=pp["seedType"]
        self.zen_vars["seedType"].set(self.zen_seed_values[st] if 0 <= st < 40 else "")
        g=pp["whichZenGarden"]
        self.zen_vars["whichZenGarden"].set(self.zen_garden_values[g] if 0 <= g < len(self.zen_garden_values) else "")
        a=pp["plantAge"]
        self.zen_vars["plantAge"].set(self.zen_age_values[a] if 0 <= a < len(self.zen_age_values) else "")
        f=pp["facing"]
        self.zen_vars["facing"].set(self.zen_facing_values[f] if 0 <= f < len(self.zen_facing_values) else "")
        for key in ["plantNeed","x","y","drawVariation","timesFed","feedingsPerGrow","lastWateredTime","lastNeedFulfilledTime","lastFertilizedTime","lastChocolateTime","futureAttribute"]:
            self.zen_vars[key].set(str(pp[key]))
        name=SEED_NAMES[st] if 0 <= st < len(SEED_NAMES) else f"Seed {st}"
        self.zen_selected_label.configure(text=f"Slot {slot}  •  {name}  •  {self._garden_label(g)}")
        self.zen_time_preview.configure(
            text=(f"Watered: {self._format_timestamp(pp['lastWateredTime'])}\n"
                  f"Fertilized: {self._format_timestamp(pp['lastFertilizedTime'])}   •   "
                  f"Chocolate: {self._format_timestamp(pp['lastChocolateTime'])}")
        )
        self._update_zen_preview_from_form()
        self.zen_form_dirty = False

    def _select_zen_tree_slot(self, slot):
        for iid in self.zen_tree.get_children():
            vals=self.zen_tree.item(iid,"values")
            if vals and int(vals[0]) == slot:
                self._zen_refreshing = True
                try:
                    self.zen_tree.selection_set(iid)
                    self.zen_tree.focus(iid)
                    self.zen_tree.see(iid)
                finally:
                    self._zen_refreshing = False
                return True
        return False

    def _collect_zen_values(self):
        values={
            "seedType": self._zen_combo_number(self.zen_vars["seedType"].get(),"Plant type"),
            "whichZenGarden": self._zen_combo_number(self.zen_vars["whichZenGarden"].get(),"Garden"),
            "plantAge": self._zen_combo_number(self.zen_vars["plantAge"].get(),"Growth stage"),
            "facing": self._zen_combo_number(self.zen_vars["facing"].get(),"Facing"),
        }
        limits={
            "plantNeed":(0,MAX_I32),"x":(-2147483648,MAX_I32),"y":(-2147483648,MAX_I32),
            "drawVariation":(0,MAX_I32),"timesFed":(0,MAX_I32),"feedingsPerGrow":(0,MAX_I32),
            "lastWateredTime":(-9223372036854775808,9223372036854775807),
            "lastNeedFulfilledTime":(-9223372036854775808,9223372036854775807),
            "lastFertilizedTime":(-9223372036854775808,9223372036854775807),
            "lastChocolateTime":(-9223372036854775808,9223372036854775807),
            "futureAttribute":(-9223372036854775808,9223372036854775807),
        }
        for key,(mn,mx) in limits.items():
            values[key]=self._parse_int(self.zen_vars[key].get(),key,mn,mx)
        if not 0 <= values["seedType"] < 40:
            raise ValueError("Plant type must be one of the 40 verified Zen Garden seed types")
        if not 0 <= values["whichZenGarden"] <= 3:
            raise ValueError("Garden must be 0–3")
        if not 0 <= values["plantAge"] <= 3:
            raise ValueError("Growth stage must be 0–3")
        if values["facing"] not in (0,1):
            raise ValueError("Facing must be 0 or 1")
        return values

    def _write_zen_form(self, slot):
        values=self._collect_zen_values()
        for key,val in values.items():
            self.profile.set_potted_field(slot,key,val)
        self.zen_form_dirty = False
        return True

    def _commit_zen_form_if_needed(self):
        if not self.profile or self.zen_selected_slot is None or not self.zen_form_dirty:
            return True
        try:
            self._write_zen_form(self.zen_selected_slot)
            self._mark()
            return True
        except Exception as exc:
            messagebox.showerror("Zen Garden", f"Fix the selected plant before continuing:\n\n{exc}")
            return False

    def _zen_select(self, _event=None):
        if not self.profile or self._zen_refreshing:
            return
        sel=self.zen_tree.selection()
        if not sel:
            return
        vals=self.zen_tree.item(sel[0],"values")
        if not vals:
            return
        slot=int(vals[0])
        old_slot=self.zen_selected_slot
        if old_slot is not None and slot != old_slot and self.zen_form_dirty:
            try:
                self._write_zen_form(old_slot)
                self._mark()
            except Exception as exc:
                messagebox.showerror("Zen Garden", f"Could not apply changes to slot {old_slot}:\n\n{exc}")
                self._select_zen_tree_slot(old_slot)
                return
        self.zen_selected_slot=slot
        self._load_zen_slot(slot)

    def _apply_selected_zen(self, silent=False):
        if not self.profile or self.zen_selected_slot is None:
            return False
        slot=self.zen_selected_slot
        try:
            self._write_zen_form(slot)
            self._refresh_zen_tree(select_slot=slot)
            self._mark()
            if not silent:
                self.status.set(f"Zen Garden slot {slot} updated in memory • Press Save to write 0.pb.dat")
            return True
        except Exception as exc:
            if silent:
                raise
            messagebox.showerror("Zen Garden",str(exc))
            return False

    def apply_selected_zen(self):
        self._apply_selected_zen(silent=False)

    def mature_selected_zen(self):
        if not self.profile or getattr(self,"zen_selected_slot",None) is None: return
        self.zen_vars["plantAge"].set(self.zen_age_values[3])
        self.zen_vars["plantNeed"].set("0")
        self._apply_selected_zen(silent=False)

    def clear_selected_zen_need(self):

        if not self.profile or getattr(self,"zen_selected_slot",None) is None: return
        self.zen_vars["plantNeed"].set("0")
        self._apply_selected_zen(silent=False)

    def clear_all_zen_needs(self):
        if not self.profile or not self._commit_zen_form_if_needed(): return
        active=max(0,min(self.profile.get_scalar("numPottedPlants"),200))
        for i in range(active): self.profile.set_potted_field(i,"plantNeed",0)
        self._refresh_zen_tree(select_slot=getattr(self,"zen_selected_slot",None))
        self._mark()
        self.status.set(f"Cleared needs for {active} Zen Garden plants in memory • Press Save")

    def _garden_label(self, value):
        labels={0:"Main",1:"Mushroom",2:"Wheelbarrow",3:"Aquarium"}
        return labels.get(value,str(value))

    def _age_label(self, value):
        labels={0:"Sprout",1:"Small",2:"Medium",3:"Mature"}
        return labels.get(value,str(value))

    def _refresh_zen_tree(self, select_slot=None):
        if not self.profile:
            return
        p=self.profile
        self._zen_refreshing = True
        try:
            for item in self.zen_tree.get_children():
                self.zen_tree.delete(item)
            active=max(0,min(p.get_scalar("numPottedPlants"),200))
            row_for_slot={}
            for i in range(active):
                pp=p.potted_plant(i); st=pp["seedType"]
                name=SEED_NAMES[st] if 0<=st<len(SEED_NAMES) else f"Seed {st}"
                tag="odd" if i % 2 else "even"
                iid=self.zen_tree.insert("","end",values=(i,name,self._garden_label(pp["whichZenGarden"]),self._age_label(pp["plantAge"]),pp["plantNeed"],pp["x"],pp["y"]),tags=(tag,))
                row_for_slot[i]=iid
            self.zen_tree.tag_configure("even",background=PANEL)
            self.zen_tree.tag_configure("odd",background="#0b2d3b")
            target=select_slot if select_slot in row_for_slot else (0 if active else None)
            if target is not None:
                iid=row_for_slot[target]
                self.zen_tree.selection_set(iid); self.zen_tree.focus(iid); self.zen_tree.see(iid)
                self.zen_selected_slot=target
            else:
                self.zen_selected_slot=None
        finally:
            self._zen_refreshing = False
        if self.zen_selected_slot is not None:
            self._load_zen_slot(self.zen_selected_slot)
        else:
            self.zen_selected_label.configure(text="No active plants in this profile")
            self.zen_time_preview.configure(text="Timestamps: —")
            self._draw_zen_preview(None)

    def _build_shop(self):
        page=self.pages["Shop"].inner
        self._page_title(page,"Shop","Edit the game's 80 purchase slots. Named entries come from the mapped store enumeration.")
        sec=self._section(page,"Purchase Records","Consumables may use encoded quantities; unchanged slots are preserved exactly.")
        sec.pack(fill="x",padx=20,pady=(0,20))
        b=tk.Frame(sec,bg=PANEL); b.pack(fill="x",padx=14,pady=(0,14))
        self.purchase_vars=[]
        for i in range(80):
            name=STORE_ITEMS[i] if i<len(STORE_ITEMS) else f"Unknown purchase slot {i}"
            tk.Label(b,text=f"{i:02d}  {name}",bg=PANEL,fg=TEXT,width=34,anchor="w").grid(row=i,column=0,sticky="w",pady=2)
            v=tk.StringVar(value="0"); self.purchase_vars.append(v)
            e=tk.Entry(b,textvariable=v,bg="#071e29",fg=TEXT,insertbackground=TEXT,relief="flat",width=16)
            e.grid(row=i,column=1,sticky="w",pady=2,ipady=3); e.bind("<KeyRelease>",lambda _e,idx=i:self._challenge_changed(idx))
        self._button(b,"Own All 9 Upgrade Plants",self.own_upgrade_plants,width=22).grid(row=0,column=2,padx=14,sticky="w")

    def _build_challenges(self):
        page=self.pages["Challenges"].inner
        self._page_title(page,"Challenges","Raw mapped challenge records, including Survival, Mini-Games and Puzzle streaks.")
        quick=self._section(page,"Quick Actions")
        quick.pack(fill="x",padx=20,pady=(0,12))
        qb=tk.Frame(quick,bg=PANEL); qb.pack(fill="x",padx=14,pady=(0,14))
        for i,(text,cmd) in enumerate([
            ("Complete Adventure Twice",self.complete_adventure),("Complete 20 Mini-Games",self.complete_minigames),
            ("Complete Puzzle Levels",self.complete_puzzles),("Complete Survival Normal/Hard",self.complete_survival),
            ("Complete Cloudy Day",self.complete_cloudy),("Complete Co-op",self.complete_coop),
        ]):
            self._button(qb,text,cmd,width=24).grid(row=i//3,column=i%3,padx=4,pady=4,sticky="ew")
            qb.columnconfigure(i%3,weight=1)
        sec=self._section(page,"100 Challenge Records")
        sec.pack(fill="x",padx=20,pady=(0,20))
        b=tk.Frame(sec,bg=PANEL); b.pack(fill="x",padx=14,pady=(0,14))
        self.challenge_vars=[]
        for i in range(100):
            tk.Label(b,text=f"{i:02d}  {CHALLENGE_NAMES[i]}",bg=PANEL,fg=TEXT,width=38,anchor="w").grid(row=i,column=0,sticky="w",pady=2)
            v=tk.StringVar(value="0"); self.challenge_vars.append(v)
            e=tk.Entry(b,textvariable=v,bg="#071e29",fg=TEXT,insertbackground=TEXT,relief="flat",width=15)
            e.grid(row=i,column=1,sticky="w",pady=2,ipady=3); e.bind("<KeyRelease>",lambda _e,idx=i:self._challenge_changed(idx))

    def _build_achievements(self):
        page=self.pages["Achievements"].inner
        self._page_title(page,"Achievements","In-profile achievement flags. Platform trophy state remains separate.")
        sec=self._section(page,"Achievement Flags")
        sec.pack(fill="x",padx=20,pady=(0,20))
        b=tk.Frame(sec,bg=PANEL); b.pack(fill="x",padx=14,pady=(0,14))
        tk.Label(b,text="Achievement",bg=PANEL,fg=MUTED,width=42,anchor="w").grid(row=0,column=0)
        tk.Label(b,text="Earned",bg=PANEL,fg=MUTED,width=10).grid(row=0,column=1)
        tk.Label(b,text="Shown",bg=PANEL,fg=MUTED,width=10).grid(row=0,column=2)
        self.earned_vars=[]; self.shown_vars=[]
        for i,name in enumerate(ACHIEVEMENTS,1):
            tk.Label(b,text=f"{i-1:02d}  {name}",bg=PANEL,fg=TEXT,width=42,anchor="w").grid(row=i,column=0,sticky="w",pady=3)
            ev=tk.BooleanVar(value=False); sv=tk.BooleanVar(value=False)
            self.earned_vars.append(ev); self.shown_vars.append(sv)
            tk.Checkbutton(b,variable=ev,bg=PANEL,selectcolor="#0b5d2a",activebackground=PANEL,command=self._mark).grid(row=i,column=1)
            tk.Checkbutton(b,variable=sv,bg=PANEL,selectcolor="#0b5d2a",activebackground=PANEL,command=self._mark).grid(row=i,column=2)
        controls=tk.Frame(b,bg=PANEL)
        controls.grid(row=39,column=0,columnspan=3,sticky="w",pady=(10,0))
        self._button(controls,"Mark All Earned",lambda:self._set_all_achievements("earned",True),width=16).pack(side="left",padx=(0,6))
        self._button(controls,"Mark All Shown",lambda:self._set_all_achievements("shown",True),width=16).pack(side="left",padx=6)
        self._button(controls,"Clear All Flags",lambda:self._set_all_achievements("both",False),width=14).pack(side="left",padx=6)

    def _build_trophy(self):
        page=self.pages["Trophy Prep"].inner
        self._page_title(page,"Trophy Prep","Prepare in-game counters without pretending the PS4 trophy database is part of 0.pb.dat.")
        sec=self._section(page,"Threshold Presets","These values are stored in challenge records and are useful for normal in-game trophy conditions.")
        sec.pack(fill="x",padx=20,pady=(0,12))
        b=tk.Frame(sec,bg=PANEL); b.pack(fill="x",padx=14,pady=(0,14))
        self._button(b,"Tree of Wisdom → 100",lambda:self._set_challenge(49,100),width=22).grid(row=0,column=0,padx=4,pady=4)
        self._button(b,"Vasebreaker Endless → 15",lambda:self._set_challenge(59,15),width=24).grid(row=0,column=1,padx=4,pady=4)
        self._button(b,"I, Zombie Endless → 10",lambda:self._set_challenge(69,10),width=24).grid(row=0,column=2,padx=4,pady=4)
        self._button(b,"Survival Day Endless → 40",lambda:self._set_challenge(10,40),width=24).grid(row=1,column=0,padx=4,pady=(8,4))
        self._button(b,"Apply All Thresholds",self.trophy_thresholds,width=22,accent=True).grid(row=1,column=1,padx=4,pady=(8,4))
        note=self._section(page,"Important","profile_data.dat contains a separate PendingAchievements queue. This build intentionally edits only the verified 0.pb.dat profile until that queue is fully mapped and validated.")
        note.pack(fill="x",padx=20,pady=(0,20))

    def _build_settings(self):
        page=self.pages["Settings"].inner
        self._page_title(page,"Settings","Save safety, validation and file information.")
        sec=self._section(page,"Safety")
        sec.pack(fill="x",padx=20,pady=(0,12))
        b=tk.Frame(sec,bg=PANEL); b.pack(fill="x",padx=14,pady=(0,14))
        tk.Label(b,text="✓ Automatic .bak backup before replacing the original file",bg=PANEL,fg="#8cf29f").pack(anchor="w",pady=3)
        tk.Label(b,text="✓ Re-parse validation before final replacement",bg=PANEL,fg="#8cf29f").pack(anchor="w",pady=3)
        tk.Label(b,text="✓ Unknown / unmapped profile bytes are preserved",bg=PANEL,fg="#8cf29f").pack(anchor="w",pady=3)
        tk.Label(b,text="✓ Unsaved-change prompts protect edits when opening or closing",bg=PANEL,fg="#8cf29f").pack(anchor="w",pady=3)
        tk.Label(b,text="Shortcuts:  Ctrl+O Open   •   Ctrl+S Save   •   Ctrl+B Backup",bg=PANEL,fg=MUTED).pack(anchor="w",pady=(8,3))
        self.settings_info=tk.Label(b,text="No save loaded",bg=PANEL,fg=MUTED,justify="left")
        self.settings_info.pack(anchor="w",pady=(10,0))

    def _set_loaded_state(self, loaded):
        state="normal" if loaded else "disabled"
        for b in [self.save_btn,self.backup_btn,self.max_btn]: b.configure(state=state)

    def _mark(self, *_):
        if not self.profile: return
        self.dirty=True
        if self.path: self.status.set(f"Modified • {self.path.name} • Save to apply changes")

    def _quick_bool_changed(self,key):
        if key=="hasUnlockedSurvivalMode":
            if key in self.unlock_vars: self.unlock_vars[key].set(self.quick_bool_vars[key].get())
        elif key in self.bool_vars:
            self.bool_vars[key].set(self.quick_bool_vars[key].get())
        self._mark()

    def _overview_changed(self, key):
        if key in getattr(self,"core_vars",{}):
            self.core_vars[key][0].set(self.ov[key].get())
        challenge_map={"tree":49,"vase":59,"izombie":69}
        if key in challenge_map and len(getattr(self,"challenge_vars",[])) > challenge_map[key]:
            self.challenge_vars[challenge_map[key]].set(self.ov[key].get())
        self._mark()

    def _core_changed(self, key):
        if key in getattr(self,"ov",{}):
            self.ov[key].set(self.core_vars[key][0].get())
        self._mark()

    def _set_core_value(self, key, value):
        if key in self.core_vars:
            self.core_vars[key][0].set(str(value))
        if key in self.ov:
            self.ov[key].set(str(value))
        self._mark()

    def _unlock_changed(self, key):
        if key == "hasUnlockedSurvivalMode" and key in getattr(self,"quick_bool_vars",{}):
            self.quick_bool_vars[key].set(self.unlock_vars[key].get())
        self._mark()

    def _bool_changed(self, key):
        if key in getattr(self,"quick_bool_vars",{}):
            self.quick_bool_vars[key].set(self.bool_vars[key].get())
        self._mark()

    def _challenge_changed(self, idx):
        reverse={49:"tree",59:"vase",69:"izombie"}
        if idx in reverse and reverse[idx] in getattr(self,"ov",{}):
            self.ov[reverse[idx]].set(self.challenge_vars[idx].get())
        self._mark()

    def _set_all_achievements(self, which, value):
        if which in ("earned","both"):
            for v in self.earned_vars:
                v.set(bool(value))
        if which in ("shown","both"):
            for v in self.shown_vars:
                v.set(bool(value))
        self._mark()

    def _resolve_unsaved(self, action):
        profile_dirty = bool(self.dirty)
        ingame_dirty = bool(self.ig_dirty or self.ig_form_dirty)
        if not profile_dirty and not ingame_dirty:
            return True
        parts = []
        if profile_dirty:
            parts.append("profile (0.pb.dat)")
        if ingame_dirty:
            parts.append("in-game save (.ig.dat)")
        answer=messagebox.askyesnocancel(
            "Unsaved changes",
            f"Save your {' and '.join(parts)} changes before {action}?\n\nYes = Save   No = Discard   Cancel = Stay here"
        )
        if answer is None:
            return False
        if answer:
            if profile_dirty and not self.save_file():
                return False
            if ingame_dirty and not self.save_ingame_file():
                return False
        return True

    def on_close(self):
        if self._resolve_unsaved("closing the editor"):
            self.destroy()

    def _plant_toggle(self,idx):
        if idx < len(self.purchase_vars): self.purchase_vars[idx].set("1" if self.plant_purchase_vars[idx].get() else "0")
        self._mark()

    def open_file(self):
        if not self._resolve_unsaved("opening another save"):
            return
        path=filedialog.askopenfilename(title="Open CUSA55613 profile",filetypes=[("PvZ profile","*.pb.dat"),("DAT files","*.dat"),("All files","*.*")])
        if path: self.load_path(Path(path))

    def load_path(self,path:Path):
        try: p=ProfileV8(path.read_bytes())
        except Exception as exc:
            messagebox.showerror("Cannot open save",str(exc)); return
        self.profile=p; self.path=path; self.dirty=False
        self._pending_cloudy_all=False; self._pending_coop_all=False; self._pending_zen_all=False; self._pending_mature_plants=False
        self.zen_selected_slot=None; self.zen_form_dirty=False
        self._populate_from_profile()
        self._set_loaded_state(True)
        self.file_badge.configure(text=f"Loaded: {path.name}")
        self.status.set(f"✓ Profile parsed successfully  •  {path.name}  •  Format v{p.version}")

    def _populate_from_profile(self):
        p=self.profile
        if not p:return
        for key,(v,_,_) in self.core_vars.items(): v.set(str(p.get_scalar(key)))
        for key,v in self.unlock_vars.items(): v.set(bool(p.get_scalar(key)))
        for key,v in self.bool_vars.items(): v.set(p.get_bool(key))
        for i,v in enumerate(self.purchase_vars): v.set(str(p.get_array("purchases")[i]))
        for i,v in enumerate(self.challenge_vars): v.set(str(p.get_array("challengeRecords")[i]))
        earned=p.get_array("earnedAchievements"); shown=p.get_array("shownAchievements")
        for i,v in enumerate(self.earned_vars): v.set(bool(earned[i]))
        for i,v in enumerate(self.shown_vars): v.set(bool(shown[i]))
        for i,v in enumerate(self.plant_purchase_vars): v.set(p.get_array("purchases")[i] > 0)

        cr=p.get_array("challengeRecords")
        self.ov["coins"].set(str(p.get_scalar("coins"))); self.ov["level"].set(str(p.get_scalar("level")))
        self.ov["finishedAdventure"].set(str(p.get_scalar("finishedAdventure"))); self.ov["ripLevel"].set(str(p.get_scalar("ripLevel")))
        self.ov["tree"].set(str(cr[49])); self.ov["vase"].set(str(cr[59])); self.ov["izombie"].set(str(cr[69]))
        for key,v in self.quick_bool_vars.items():
            if key=="hasUnlockedSurvivalMode": v.set(bool(p.get_scalar(key)))
            else: v.set(p.get_bool(key))

        mg=sum(bool(x) for x in p.get_array("miniGamesCompleted")); cloudy=sum(bool(x) for x in p.get_array("cloudyDayLevelsCompleted")); coop=sum(bool(x) for x in p.get_array("coopLevelsCompleted"))
        puzzle=sum(1 for i in list(range(50,59))+list(range(60,69)) if cr[i]>0)
        survival=sum(1 for i in range(10) if cr[i]>0)
        progress_counts={"Mini-Games":(mg,20),"Puzzle":(puzzle,18),"Survival":(survival,10),"Cloudy Day":(cloudy,13),"Co-op":(coop,15)}
        for k,(value,total) in progress_counts.items():
            self.progress_labels[k].configure(text=f"{value}/{total}")
            self.progress_bars[k].configure(maximum=total,value=value)
        owned=sum(1 for x in p.get_array("purchases")[:30] if x>0)
        self.summary_text.configure(text=f"Known shop entries owned: {owned} / 30     •     Achievements earned: {sum(bool(x) for x in earned)} / 37     •     Adventure level: {p.get_scalar('level')}")
        active=max(0,min(p.get_scalar("numPottedPlants"),200)); collected=sum(bool(x) for x in p.get_array("collectedZenGardenPlants"))
        self.zen_summary.configure(text=f"{active} active plants  •  {collected}/40 collected")
        self.zen_stats.configure(text=f"Active potted plants: {active}/200     •     Collected plant types: {collected}/40")
        self._refresh_zen_tree()
        self.settings_info.configure(text=f"Player: {p.name}\nGUID: {p.guid}\nProfile version: {p.version}\nDecompressed size: {len(p.raw):,} bytes\nFile: {self.path}")
        self.dirty=False

    @staticmethod
    def _parse_int(text,label,mn=None,mx=None):
        try:v=int(text.strip(),0)
        except (TypeError, ValueError): raise ValueError(f"{label}: enter a whole number")
        if mn is not None and v<mn: raise ValueError(f"{label}: minimum is {mn}")
        if mx is not None and v>mx: raise ValueError(f"{label}: maximum is {mx}")
        return v

    def _sync_overview_to_core(self):
        # Kept for compatibility with older builds. v2.3 synchronizes both views live.
        return

    def _apply_ui(self):
        p=self.profile
        if not p: raise RuntimeError("No profile loaded")
        for key,(v,mn,mx) in self.core_vars.items(): p.set_scalar(key,self._parse_int(v.get(),key,mn,mx))
        for key,v in self.unlock_vars.items(): p.set_scalar(key,1 if v.get() else 0)
        for key,v in self.bool_vars.items(): p.set_bool(key,v.get())
        for i,v in enumerate(self.purchase_vars): p.set_array_item("purchases",i,self._parse_int(v.get(),f"Purchase slot {i}",-2147483648,MAX_I32))
        for i,v in enumerate(self.challenge_vars): p.set_array_item("challengeRecords",i,self._parse_int(v.get(),f"Challenge record {i}",-2147483648,MAX_I32))
        for i,v in enumerate(self.earned_vars): p.set_array_item("earnedAchievements",i,v.get())
        for i,v in enumerate(self.shown_vars): p.set_array_item("shownAchievements",i,v.get())
        if getattr(self,"zen_selected_slot",None) is not None and self.zen_form_dirty:
            self._apply_selected_zen(silent=True)
        if self._pending_cloudy_all: p.set_array_all("cloudyDayLevelsCompleted",1)
        if self._pending_coop_all: p.set_array_all("coopLevelsCompleted",1)
        if self._pending_zen_all: p.set_array_all("collectedZenGardenPlants",1)
        if self._pending_mature_plants:
            active=max(0,min(p.get_scalar("numPottedPlants"),200))
            for i in range(active): p.set_potted_field(i,"plantAge",3)
        if all(p.get_array("challengeRecords")[i]>0 for i in range(15,35)): p.set_array_all("miniGamesCompleted",1)

    def save_file(self):
        if not self.path or not self.profile:
            return False
        tmp=self.path.with_suffix(self.path.suffix+".tmp")
        try:
            self._apply_ui()
            out=self.profile.compressed_bytes()
            backup=self.path.with_suffix(self.path.suffix+".bak")
            if not backup.exists():
                shutil.copy2(self.path,backup)
            if tmp.exists():
                tmp.unlink()
            with tmp.open("wb") as fh:
                fh.write(out)
                fh.flush()
                os.fsync(fh.fileno())
            ProfileV8(tmp.read_bytes())
            try:
                shutil.copystat(self.path,tmp)
            except OSError:
                pass
            os.replace(tmp,self.path)
            self.load_path(self.path)
            self.status.set(f"✓ Saved and verified  •  Backup: {backup.name}  •  Format: 0.pb.dat")
            messagebox.showinfo("Saved",f"Save written and verified.\n\nBackup: {backup}")
            return True
        except Exception as exc:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            messagebox.showerror("Save failed",str(exc))
            return False

    def create_backup(self):
        if not self.path:
            return False
        try:
            stamp=datetime.now().strftime("%Y%m%d-%H%M%S")
            dest=self.path.with_name(f"{self.path.name}.manual.{stamp}.bak")
            shutil.copy2(self.path,dest)
            self.status.set(f"Backup created • {dest.name}")
            messagebox.showinfo("Backup",f"Created:\n{dest}")
            return True
        except Exception as exc:
            messagebox.showerror("Backup failed",str(exc))
            return False

    def unlock_main_modes(self):
        for k in ["hasUnlockedMinigames","hasUnlockedPuzzleMode","hasUnlockedSurvivalMode"]:
            if k in self.unlock_vars:self.unlock_vars[k].set(True)
        for k in ["hasSeenMultiplayerUnlocked","hasSeenLimboUnlocked","hasSeenRIPUnlocked","hasSeenCloudyDayUnlocked"]:
            if k in self.bool_vars:self.bool_vars[k].set(True)
        if "hasUnlockedSurvivalMode" in self.quick_bool_vars:
            self.quick_bool_vars["hasUnlockedSurvivalMode"].set(True)
        self._mark()

    def complete_adventure(self):
        self._set_core_value("level",50)
        self._set_core_value("finishedAdventure",2)
    def complete_minigames(self):
        for i in range(15,35): self.challenge_vars[i].set("1")
        self.progress_labels["Mini-Games"].configure(text="20/20")
        self.progress_bars["Mini-Games"].configure(value=20)
        self._mark()
    def complete_puzzles(self):
        for i in list(range(50,59))+list(range(60,69)): self.challenge_vars[i].set("1")
        self.progress_labels["Puzzle"].configure(text="18/18")
        self.progress_bars["Puzzle"].configure(value=18)
        self._mark()
    def complete_survival(self):
        for i in range(5): self.challenge_vars[i].set("5")
        for i in range(5,10): self.challenge_vars[i].set("10")
        self.progress_labels["Survival"].configure(text="10/10")
        self.progress_bars["Survival"].configure(value=10)
        self._mark()
    def complete_cloudy(self):
        self._pending_cloudy_all=True
        self.progress_labels["Cloudy Day"].configure(text="13/13")
        self.progress_bars["Cloudy Day"].configure(value=13)
        self._mark()
    def complete_coop(self):
        self._pending_coop_all=True
        self.progress_labels["Co-op"].configure(text="15/15")
        self.progress_bars["Co-op"].configure(value=15)
        self._mark()
    def collect_all_zen(self): self._pending_zen_all=True; self._mark()
    def mature_plants(self):
        if not self.profile or not self._commit_zen_form_if_needed(): return
        active=max(0,min(self.profile.get_scalar("numPottedPlants"),200))
        for i in range(active):
            self.profile.set_potted_field(i,"plantAge",3)
            self.profile.set_potted_field(i,"plantNeed",0)
        self._pending_mature_plants=False
        self._refresh_zen_tree(select_slot=getattr(self,"zen_selected_slot",None))
        self._mark()
        self.status.set(f"Matured {active} Zen Garden plants in memory • Press Save")
    def own_upgrade_plants(self):
        for i in range(9):
            if i<len(self.purchase_vars): self.purchase_vars[i].set("1")
            if i<len(self.plant_purchase_vars): self.plant_purchase_vars[i].set(True)
        self._mark()
    def _set_challenge(self,idx,val):
        self.challenge_vars[idx].set(str(val))
        self._challenge_changed(idx)
    def trophy_thresholds(self): self._set_challenge(49,100); self._set_challenge(59,15); self._set_challenge(69,10); self._set_challenge(10,40)

    def max_all(self):
        if not self.profile:return
        self._set_core_value("coins",999999999)
        self._set_core_value("level",50)
        self._set_core_value("finishedAdventure",2)
        self.unlock_main_modes(); self.own_upgrade_plants(); self.complete_minigames(); self.complete_puzzles(); self.complete_survival(); self.complete_cloudy(); self.complete_coop(); self.collect_all_zen(); self.mature_plants(); self.trophy_thresholds()
        for k in ["mustacheModeActive","futureModeActive","pinataModeActive","daisesModeActive","harderEnabled"]:
            if k in self.bool_vars:self.bool_vars[k].set(True)
        for k,v in self.quick_bool_vars.items():
            if k == "hasUnlockedSurvivalMode" and k in self.unlock_vars:
                v.set(self.unlock_vars[k].get())
            elif k in self.bool_vars:
                v.set(self.bool_vars[k].get())
        self.status.set("Safe Max preset applied in memory • Review changes, then press Save")


if __name__ == "__main__":
    App().mainloop()
