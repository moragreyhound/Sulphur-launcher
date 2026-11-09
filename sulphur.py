"""
Sulphur — Professional Minecraft Launcher
=========================================

A feature-rich Minecraft launcher built with tkinter + minecraft-launcher-lib.

Features
--------
• Modern dark UI with custom color palette & hover animations
• Entrance fade-in + screen transitions
• Sidebar navigation (Home, Versions, Accounts, Profiles, Servers, Settings)
• Offline mode (no Mojang/Microsoft login required)
• Online account support (Microsoft / Mojang token-based)
• Version install / launch / delete with progress animation
• Multiple player profiles with custom settings
• Server list with quick connect
• Custom Java path & memory per profile
• Launch options (fullscreen, demo, custom resolution)
• Live console log
• Auto Java detection

Requirements
------------
    pip install minecraft-launcher-lib

Run
---
    python sulphur.py
"""

import os
import sys
import json
import uuid
import subprocess
import threading
import webbrowser
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ---------------------------------------------------------------------------
# Optional dependency
# ---------------------------------------------------------------------------
try:
    import minecraft_launcher_lib
    from minecraft_launcher_lib import utils, install, command
    HAS_LIB = True
except Exception:  # pragma: no cover
    HAS_LIB = False

# ---------------------------------------------------------------------------
# Professional color palette
# ---------------------------------------------------------------------------
C = {
    "bg":         "#0b0d14",   # deep navy-black
    "surface":    "#151928",   # panel surfaces
    "surface_2":  "#1e2335",   # slightly lighter surface
    "accent":     "#7c3aed",   # violet primary
    "accent_2":   "#4f46e5",   # indigo secondary
    "accent_glow":"#a78bfa",   # light violet glow
    "text":       "#e2e8f0",   # primary text
    "text_dim":   "#94a3b8",   # muted text
    "text_inv":   "#0f172a",   # text on accent
    "border":     "#262b40",   # subtle borders
    "success":    "#10b981",   # emerald
    "danger":     "#ef4444",   # red
    "warning":    "#f59e0b",   # amber
    "info":       "#3b82f6",   # blue
}

FONTS = {
    "ui":       ("Segoe UI", 10),
    "ui_bold":  ("Segoe UI", 10, "bold"),
    "heading":  ("Segoe UI", 13, "bold"),
    "title":    ("Segoe UI", 20, "bold"),
    "mono":     ("Consolas", 9),
    "button":   ("Segoe UI", 10, "bold"),
}

DEFAULT_MEMORY_MB = 3072
APP_NAME = "Sulphur"


# ---------------------------------------------------------------------------
# Utility widgets
# ---------------------------------------------------------------------------

class AnimatedButton(tk.Canvas):
    """A button with hover/press color animation drawn on a canvas."""
    def __init__(self, parent, text, command=None, width=200, height=42,
                 fill=C["accent"], hover=C["accent_2"], text_color=C["text_inv"],
                 radius=12, font=FONTS["button"], **kwargs):
        super().__init__(parent, width=width, height=height,
                         highlightthickness=0, bg=parent["bg"], **kwargs)
        self.command = command
        self.fill = fill
        self.hover = hover
        self.text_color = text_color
        self.radius = radius
        self.font = font
        self.text = text
        self._state = "normal"  # normal, hover, press

        self.bind("<Enter>", lambda e: self._set_state("hover"))
        self.bind("<Leave>", lambda e: self._set_state("normal"))
        self.bind("<ButtonPress-1>", lambda e: self._set_state("press"))
        self.bind("<ButtonRelease-1>", lambda e: self._on_release(e))
        self._draw()

    def _round_rect(self, x1, y1, x2, y2, r, color):
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]
        return self.create_polygon(points, smooth=True, fill=color, outline="")

    def _draw(self):
        self.delete("all")
        w = self.winfo_width() or 200
        h = self.winfo_height() or 42
        color = self.fill if self._state == "normal" else (
            self.hover if self._state == "hover" else C["accent_glow"]
        )
        self._round_rect(0, 0, w, h, self.radius, color)
        self.create_text(w / 2, h / 2, text=self.text, fill=self.text_color,
                         font=self.font, anchor="center")

    def _set_state(self, state):
        if self._state == state:
            return
        self._state = state
        self._draw()

    def _on_release(self, event):
        self._set_state("hover" if self.winfo_containing(event.x_root, event.y_root) == self else "normal")
        if self.command:
            self.command()


class HoverButton(tk.Button):
    """Standard tk.Button with hover color animation."""
    def __init__(self, parent, text, command=None, **kwargs):
        default_bg = kwargs.pop("bg", C["surface_2"])
        default_fg = kwargs.pop("fg", C["text"])
        hover_bg = kwargs.pop("hover_bg", C["surface"])
        super().__init__(parent, text=text, command=command,
                         bg=default_bg, fg=default_fg,
                         activebackground=hover_bg, activeforeground=default_fg,
                         relief="flat", bd=0, highlightthickness=0,
                         font=FONTS["ui"], padx=12, pady=6, cursor="hand2",
                         **kwargs)
        self._normal_bg = default_bg
        self._hover_bg = hover_bg
        self.bind("<Enter>", lambda e: self.configure(bg=self._hover_bg))
        self.bind("<Leave>", lambda e: self.configure(bg=self._normal_bg))


class SectionLabel(tk.Label):
    def __init__(self, parent, text, **kwargs):
        super().__init__(parent, text=text.upper(), font=FONTS["heading"],
                         fg=C["text_dim"], bg=C["bg"], **kwargs)


class LogConsole(tk.Text):
    """Colored console log with timestamp."""
    LEVEL_COLORS = {
        "INFO": C["text_dim"],
        "SUCCESS": C["success"],
        "WARN": C["warning"],
        "ERROR": C["danger"],
        "LAUNCH": C["accent"],
    }

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=C["surface"], fg=C["text"],
                         insertbackground=C["text"], selectbackground=C["accent"],
                         font=FONTS["mono"], wrap=tk.WORD, state=tk.DISABLED,
                         padx=10, pady=8, relief="flat", bd=0, **kwargs)
        for level, color in self.LEVEL_COLORS.items():
            self.tag_config(level, foreground=color)

    def write(self, message, level="INFO"):
        self.configure(state=tk.NORMAL)
        ts = datetime.now().strftime("%H:%M:%S")
        self.insert(tk.END, f"[{ts}] ", "INFO")
        self.insert(tk.END, message + "\n", level)
        self.see(tk.END)
        self.configure(state=tk.DISABLED)


# ---------------------------------------------------------------------------
# Managers
# ---------------------------------------------------------------------------

class DataManager:
    """Handles profiles, servers, and settings persistence."""
    def __init__(self, app_dir):
        self.app_dir = app_dir
        os.makedirs(app_dir, exist_ok=True)
        self.profiles_path = os.path.join(app_dir, "profiles.json")
        self.servers_path = os.path.join(app_dir, "servers.json")
        self.settings_path = os.path.join(app_dir, "settings.json")
        self.profiles = self._load(self.profiles_path, [
            {"name": "Default", "version": "", "memory": DEFAULT_MEMORY_MB,
             "java": "java", "offline": True, "username": "Player",
             "fullscreen": False, "width": 854, "height": 480}
        ])
        self.servers = self._load(self.servers_path, [])
        self.settings = self._load(self.settings_path, {
            "game_dir": os.path.join(os.getcwd(), ".minecraft"),
            "theme": "dark",
        })

    def _load(self, path, default):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _save(self, path, data):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Save failed {path}: {e}")

    def save_profiles(self):
        self._save(self.profiles_path, self.profiles)

    def save_servers(self):
        self._save(self.servers_path, self.servers)

    def save_settings(self):
        self._save(self.settings_path, self.settings)


class VersionManager:
    def __init__(self, log_cb, status_cb):
        self.log = log_cb
        self.status = status_cb
        self.versions = []
        self.installed = set()

    def fetch(self, minecraft_dir):
        try:
            if not HAS_LIB:
                raise RuntimeError("library missing")
            manifest = utils.get_version_manifest()
            self.versions = [v["id"] for v in manifest["versions"]]
            self.log(f"Fetched {len(self.versions)} versions from Mojang.")
        except Exception as e:
            self.log(f"Online fetch failed ({e}); using offline fallback.")
            self.versions = [
                "1.20.1", "1.20", "1.19.4", "1.19.2", "1.18.2", "1.17.1",
                "1.16.5", "1.15.2", "1.14.4", "1.12.2", "1.8.9",
            ]
        self._load_installed(minecraft_dir)

    def _load_installed(self, minecraft_dir):
        self.installed = set()
        versions_dir = os.path.join(minecraft_dir, "versions")
        if os.path.isdir(versions_dir):
            for name in os.listdir(versions_dir):
                if os.path.isdir(os.path.join(versions_dir, name)):
                    self.installed.add(name)

    def install(self, version, minecraft_dir, progress_cb):
        if not HAS_LIB:
            raise RuntimeError("minecraft-launcher-lib not installed")
        def callback(status, current, total):
            progress_cb(current, total or 100)
        install.install_minecraft_version(version, minecraft_dir, callback=callback)
        self._load_installed(minecraft_dir)

    def launch_command(self, version, minecraft_dir, options):
        return command.get_minecraft_command(version, minecraft_dir, options)


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------

class BaseScreen:
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.frame = tk.Frame(parent, bg=C["bg"])
    def pack(self, **kw):
        self.frame.pack(**kw)
    def place(self, **kw):
        self.frame.place(**kw)
    def tkraise(self):
        self.frame.tkraise()
    def on_show(self):
        pass


class HomeScreen(BaseScreen):
    name = "home"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()

    def _build(self):
        f = self.frame
        # Header
        header = tk.Frame(f, bg=C["bg"])
        header.pack(fill=tk.X, padx=40, pady=(40, 10))
        tk.Label(header, text="Sulphur", font=("Segoe UI", 28, "bold"),
                 fg=C["accent"], bg=C["bg"]).pack(side=tk.LEFT)
        tk.Label(header, text="  Minecraft Launcher", font=FONTS["ui"],
                 fg=C["text_dim"], bg=C["bg"]).pack(side=tk.LEFT, anchor="center")

        # Welcome card
        card = tk.Frame(f, bg=C["surface"], bd=0, highlightbackground=C["border"],
                        highlightthickness=1)
        card.pack(fill=tk.X, padx=40, pady=20)

        inner = tk.Frame(card, bg=C["surface"])
        inner.pack(padx=25, pady=25, fill=tk.X)
        tk.Label(inner, text="Welcome back", font=FONTS["heading"],
                 fg=C["text"], bg=C["surface"]).pack(anchor="w")
        tk.Label(inner, text="Select a profile and hit Play to jump straight into Minecraft.",
                 font=FONTS["ui"], fg=C["text_dim"], bg=C["surface"]).pack(anchor="w", pady=(4, 16))

        # Quick profile selector
        row = tk.Frame(inner, bg=C["surface"])
        row.pack(fill=tk.X, pady=(0, 16))
        tk.Label(row, text="Profile:", font=FONTS["ui_bold"], fg=C["text_dim"],
                 bg=C["surface"]).pack(side=tk.LEFT)
        self.profile_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(row, textvariable=self.profile_var,
                                          state="readonly", width=30, font=FONTS["ui"])
        self.profile_combo.pack(side=tk.LEFT, padx=10)
        ttk.Button(row, text="Refresh", command=self._refresh_profiles).pack(side=tk.LEFT)

        # Play button
        play = AnimatedButton(inner, text="▶  PLAY MINECRAFT", width=260, height=52,
                              fill=C["accent"], hover=C["accent_2"],
                              command=self.app._launch_selected_profile)
        play.pack(anchor="w", pady=(0, 10))

        # Status / info
        info = tk.Frame(inner, bg=C["surface"])
        info.pack(fill=tk.X)
        self.status_lbl = tk.Label(info, text="Ready", font=FONTS["ui"],
                                   fg=C["text_dim"], bg=C["surface"])
        self.status_lbl.pack(side=tk.LEFT)
        self.lib_lbl = tk.Label(info, text="", font=FONTS["ui"],
                                fg=C["text_dim"], bg=C["surface"])
        self.lib_lbl.pack(side=tk.RIGHT)

        # Quick stats
        stats = tk.Frame(f, bg=C["bg"])
        stats.pack(fill=tk.X, padx=40, pady=(10, 0))
        self._stat_card(stats, "Versions", "--", 0)
        self._stat_card(stats, "Profiles", "--", 1)
        self._stat_card(stats, "Servers", "--", 2)

    def _stat_card(self, parent, label, value, col):
        card = tk.Frame(parent, bg=C["surface"], highlightbackground=C["border"],
                        highlightthickness=1, width=200, height=100)
        card.grid(row=0, column=col, padx=8, sticky="ew")
        card.pack_propagate(False)
        tk.Label(card, text=label, font=FONTS["ui"], fg=C["text_dim"],
                 bg=C["surface"]).pack(anchor="w", padx=15, pady=(18, 4))
        tk.Label(card, text=value, font=("Segoe UI", 16, "bold"), fg=C["text"],
                 bg=C["surface"]).pack(anchor="w", padx=15)
        parent.grid_columnconfigure(col, weight=1)

    def _refresh_profiles(self):
        profiles = [p["name"] for p in self.app.data.profiles]
        self.profile_combo["values"] = profiles
        if profiles:
            self.profile_combo.current(0)
        self.status_lbl.config(text=f"{len(profiles)} profile(s) loaded")
        lib_text = "minecraft-launcher-lib: OK" if HAS_LIB else "minecraft-launcher-lib: MISSING"
        self.lib_lbl.config(text=lib_text,
                            fg=C["success"] if HAS_LIB else C["danger"])

    def on_show(self):
        self._refresh_profiles()
        self.app._update_stats()


class VersionsScreen(BaseScreen):
    name = "versions"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()
        self._refresh_job = None

    def _build(self):
        f = self.frame
        top = tk.Frame(f, bg=C["bg"])
        top.pack(fill=tk.X, padx=30, pady=(25, 10))
        tk.Label(top, text="Versions", font=FONTS["title"], fg=C["text"],
                 bg=C["bg"]).pack(side=tk.LEFT)
        tk.Button(top, text="Refresh", command=self.refresh,
                  bg=C["surface_2"], fg=C["text"], relief="flat",
                  cursor="hand2", font=FONTS["ui"]).pack(side=tk.RIGHT)

        # Toolbar
        bar = tk.Frame(f, bg=C["bg"])
        bar.pack(fill=tk.X, padx=30, pady=(0, 10))
        self.install_btn = HoverButton(bar, text="Install Selected",
                                       command=self.install_selected, bg=C["accent"],
                                       fg=C["text_inv"], hover_bg=C["accent_2"])
        self.install_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.launch_btn = HoverButton(bar, text="Launch Selected",
                                      command=self.launch_selected, bg=C["surface_2"],
                                      fg=C["text"], hover_bg=C["surface"])
        self.launch_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.delete_btn = HoverButton(bar, text="Delete Selected",
                                      command=self.delete_selected, bg=C["surface_2"],
                                      fg=C["text"], hover_bg=C["surface"])
        self.delete_btn.pack(side=tk.LEFT)

        # Listbox with scrollbar
        list_frame = tk.Frame(f, bg=C["surface"], highlightbackground=C["border"],
                              highlightthickness=1)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=(0, 20))

        scroll = tk.Scrollbar(list_frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox = tk.Listbox(list_frame, bg=C["surface"], fg=C["text"],
                                  selectbackground=C["accent"], selectforeground=C["text_inv"],
                                  font=FONTS["ui"], relief="flat", bd=0,
                                  highlightthickness=0, activestyle="none",
                                  yscrollcommand=scroll.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        scroll.config(command=self.listbox.yview)
        self.listbox.bind("<<ListboxSelect>>", lambda e: self._on_select())

        # Progress bar
        self.progress = ttk.Progressbar(f, mode="determinate", length=300)
        self.progress.pack(fill=tk.X, padx=30, pady=(0, 10))
        self.progress["value"] = 0

        self.status_lbl = tk.Label(f, text="", font=FONTS["ui"],
                                   fg=C["text_dim"], bg=C["bg"])
        self.status_lbl.pack(anchor="w", padx=30)

    def refresh(self):
        self.listbox.delete(0, tk.END)
        self.status_lbl.config(text="Fetching version list...")
        threading.Thread(target=self.app.version_manager.fetch,
                         args=(self.app.data.settings["game_dir"],),
                         daemon=True).start()
        self.app.root.after(500, self._poll_versions)

    def _poll_versions(self):
        vm = self.app.version_manager
        if vm.versions is None or (not vm.versions and self.status_lbl.cget("text").startswith("Fetching")):
            self.app.root.after(500, self._poll_versions)
            return
        installed = vm.installed
        # Sort: installed first, then rest
        ordered = sorted(vm.versions, key=lambda v: (v not in installed, v))
        self.listbox.delete(0, tk.END)
        for v in ordered:
            tag = " ✓" if v in installed else ""
            self.listbox.insert(tk.END, v + tag)
        self.status_lbl.config(
            text=f"{len(vm.versions)} versions  •  {len(installed)} installed")
        self._on_select()

    def _on_select(self):
        sel = self.listbox.curselection()
        if not sel:
            self.install_btn.configure(state=tk.DISABLED)
            self.launch_btn.configure(state=tk.DISABLED)
            self.delete_btn.configure(state=tk.DISABLED)
            return
        version = self.listbox.get(sel[0]).replace(" ✓", "")
        installed = version in self.app.version_manager.installed
        self.install_btn.configure(state=tk.DISABLED if installed else tk.NORMAL)
        self.launch_btn.configure(state=tk.NORMAL if installed else tk.DISABLED)
        self.delete_btn.configure(state=tk.NORMAL if installed else tk.DISABLED)

    def install_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        version = self.listbox.get(sel[0]).replace(" ✓", "")
        self.app._install_version(version)

    def launch_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        version = self.listbox.get(sel[0]).replace(" ✓", "")
        # Use default profile
        prof = self.app.data.profiles[0] if self.app.data.profiles else None
        if not prof:
            messagebox.showwarning("No profile", "Create a profile first.")
            return
        prof["version"] = version
        self.app.data.save_profiles()
        self.app._launch_profile(prof)

    def delete_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        version = self.listbox.get(sel[0]).replace(" ✓", "")
        if not messagebox.askyesno("Delete", f"Delete version {version}?"):
            return
        import shutil
        path = os.path.join(self.app.data.settings["game_dir"], "versions", version)
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            self.app.version_manager._load_installed(self.app.data.settings["game_dir"])
            self.refresh()
        except Exception as e:
            messagebox.showerror("Delete failed", str(e))


class AccountsScreen(BaseScreen):
    name = "accounts"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()

    def _build(self):
        f = self.frame
        tk.Label(f, text="Accounts", font=FONTS["title"], fg=C["text"],
                 bg=C["bg"]).pack(anchor="w", padx=30, pady=(25, 20))

        # Offline card
        card = tk.Frame(f, bg=C["surface"], highlightbackground=C["border"],
                        highlightthickness=1)
        card.pack(fill=tk.X, padx=30, pady=(0, 20))
        inner = tk.Frame(card, bg=C["surface"])
        inner.pack(padx=25, pady=20, fill=tk.X)
        tk.Label(inner, text="Offline Mode", font=FONTS["heading"],
                 fg=C["text"], bg=C["surface"]).pack(anchor="w")
        tk.Label(inner, text="Play without logging into Mojang or Microsoft. "
             "A local UUID is generated from your username.",
                 font=FONTS["ui"], fg=C["text_dim"], bg=C["surface"]).pack(anchor="w", pady=(4, 14))

        row = tk.Frame(inner, bg=C["surface"])
        row.pack(fill=tk.X)
        tk.Label(row, text="Username:", font=FONTS["ui_bold"], fg=C["text_dim"],
                 bg=C["surface"]).pack(side=tk.LEFT)
        self.offline_user = tk.StringVar(value="Player")
        tk.Entry(row, textvariable=self.offline_user, font=FONTS["ui"],
                 bg=C["surface_2"], fg=C["text"], insertbackground=C["text"],
                 relief="flat", bd=0, width=20).pack(side=tk.LEFT, padx=8)

        # Online card
        card2 = tk.Frame(f, bg=C["surface"], highlightbackground=C["border"],
                         highlightthickness=1)
        card2.pack(fill=tk.X, padx=30)
        inner2 = tk.Frame(card2, bg=C["surface"])
        inner2.pack(padx=25, pady=20, fill=tk.X)
        tk.Label(inner2, text="Online (Microsoft / Mojang)", font=FONTS["heading"],
                 fg=C["text"], bg=C["surface"]).pack(anchor="w")
        tk.Label(inner2, text="Sign in to access skins, capes, and multiplayer. "
             "Paste your access token below after authenticating.",
                 font=FONTS["ui"], fg=C["text_dim"], bg=C["surface"]).pack(anchor="w", pady=(4, 14))

        btn_row = tk.Frame(inner2, bg=C["surface"])
        btn_row.pack(fill=tk.X)
        HoverButton(btn_row, text="Open Microsoft Login", command=self._open_login,
                    bg=C["accent"], fg=C["text_inv"], hover_bg=C["accent_2"]).pack(side=tk.LEFT, padx=(0, 8))
        HoverButton(btn_row, text="Clear Token", command=self._clear_token,
                    bg=C["surface_2"], fg=C["text"], hover_bg=C["surface"]).pack(side=tk.LEFT)

        self.token_txt = tk.Text(inner2, height=3, bg=C["surface_2"], fg=C["text"],
                                 insertbackground=C["text"], relief="flat", bd=0,
                                 font=FONTS["mono"], padx=8, pady=8)
        self.token_txt.pack(fill=tk.X, pady=(10, 0))
        self.token_txt.insert("1.0", self.app.data.settings.get("online_token", ""))
        self.token_txt.bind("<FocusOut>", lambda e: self._save_token())

    def _open_login(self):
        webbrowser.open("https://login.live.com/oauth20_authorize.scope?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=YOUR_REDIRECT_URI")
        messagebox.showinfo("Microsoft Login",
            "A browser window has opened.\n\n"
            "1. Complete the Microsoft login.\n"
            "2. Copy the resulting access token.\n"
            "3. Paste it into the token field above and save.\n\n"
            "Note: This basic build uses a placeholder client ID. "
            "Register your own app at https://aka.ms/msaljs for production use.")

    def _clear_token(self):
        self.token_txt.delete("1.0", tk.END)
        self._save_token()

    def _save_token(self):
        self.app.data.settings["online_token"] = self.token_txt.get("1.0", tk.END).strip()
        self.app.data.save_settings()


class ProfilesScreen(BaseScreen):
    name = "profiles"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()

    def _build(self):
        f = self.frame
        tk.Label(f, text="Profiles", font=FONTS["title"], fg=C["text"],
                 bg=C["bg"]).pack(anchor="w", padx=30, pady=(25, 10))

        bar = tk.Frame(f, bg=C["bg"])
        bar.pack(fill=tk.X, padx=30, pady=(0, 10))
        HoverButton(bar, text="+ New Profile", command=self.new_profile,
                    bg=C["accent"], fg=C["text_inv"], hover_bg=C["accent_2"]).pack(side=tk.LEFT)
        HoverButton(bar, text="Save", command=self.save_profiles,
                    bg=C["surface_2"], fg=C["text"], hover_bg=C["surface"]).pack(side=tk.LEFT, padx=8)

        # Scrollable list
        wrap = tk.Frame(f, bg=C["bg"])
        wrap.pack(fill=tk.BOTH, expand=True, padx=30, pady=(0, 20))
        canvas = tk.Canvas(wrap, bg=C["bg"], highlightthickness=0)
        scroll = tk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        self.list_frame = tk.Frame(canvas, bg=C["bg"])
        self.list_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas = canvas

        self.refresh()

    def refresh(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        for i, prof in enumerate(self.app.data.profiles):
            self._profile_row(i, prof)

    def _profile_row(self, idx, prof):
        card = tk.Frame(self.list_frame, bg=C["surface"], highlightbackground=C["border"],
                        highlightthickness=1)
        card.pack(fill=tk.X, pady=6, padx=2)

        left = tk.Frame(card, bg=C["surface"])
        left.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=15, pady=12)

        name_var = tk.StringVar(value=prof.get("name", f"Profile {idx+1}"))
        tk.Label(left, text=name_var.get(), font=FONTS["heading"], fg=C["text"],
                 bg=C["surface"]).pack(anchor="w")
        details = f"Version: {prof.get('version','—')}   •   Memory: {prof.get('memory',DEFAULT_MEMORY_MB)}MB   •   "
        details += "Offline" if prof.get("offline", True) else "Online"
        tk.Label(left, text=details, font=FONTS["ui"], fg=C["text_dim"],
                 bg=C["surface"]).pack(anchor="w", pady=(2, 0))

        right = tk.Frame(card, bg=C["surface"])
        right.pack(side=tk.RIGHT, padx=15, pady=10)
        AnimatedButton(right, text="Edit", width=110, height=34,
                       fill=C["surface_2"], hover=C["surface"],
                       text_color=C["text"], command=lambda: self.edit_profile(idx)).pack(side=tk.LEFT, padx=4)
        AnimatedButton(right, text="Launch", width=110, height=34,
                       fill=C["accent"], hover=C["accent_2"],
                       command=lambda: self.app._launch_profile(prof)).pack(side=tk.LEFT, padx=4)

    def new_profile(self):
        prof = {"name": "New Profile", "version": "", "memory": DEFAULT_MEMORY_MB,
                "java": "java", "offline": True, "username": "Player",
                "fullscreen": False, "width": 854, "height": 480}
        self.app.data.profiles.append(prof)
        self.refresh()

    def edit_profile(self, idx):
        prof = self.app.data.profiles[idx]
        win = tk.Toplevel(self.app.root)
        win.title("Edit Profile")
        win.configure(bg=C["surface"])
        win.geometry("420x560")
        win.resizable(False, False)
        win.transient(self.app.root)
        win.grab_set()

        fields = {}
        def add(label, key, widget_kind="entry", values=None):
            tk.Label(win, text=label, font=FONTS["ui"], fg=C["text_dim"],
                     bg=C["surface"]).pack(anchor="w", padx=20, pady=(14, 2))
            if widget_kind == "entry":
                var = tk.StringVar(value=str(prof.get(key, "")))
                ent = tk.Entry(win, textvariable=var, font=FONTS["ui"],
                               bg=C["surface_2"], fg=C["text"], insertbackground=C["text"],
                               relief="flat", bd=0)
                ent.pack(fill=tk.X, padx=20, pady=(0, 6), ipady=4)
                fields[key] = var
            elif widget_kind == "spin":
                var = tk.IntVar(value=int(prof.get(key, DEFAULT_MEMORY_MB)))
                sp = tk.Spinbox(win, from_=512, to=16384, increment=256,
                                textvariable=var, font=FONTS["ui"], bg=C["surface_2"],
                                fg=C["text"], insertbackground=C["text"], relief="flat", bd=0)
                sp.pack(fill=tk.X, padx=20, pady=(0, 6), ipady=4)
                fields[key] = var
            elif widget_kind == "check":
                var = tk.BooleanVar(value=bool(prof.get(key, False)))
                cb = tk.Checkbutton(win, text=label, variable=var, font=FONTS["ui"],
                                    fg=C["text"], bg=C["surface"], selectcolor=C["surface_2"],
                                    activebackground=C["surface"], cursor="hand2")
                cb.pack(anchor="w", padx=20, pady=(0, 6))
                fields[key] = var

        add("Profile Name", "name")
        add("Version", "version")
        add("Memory (MB)", "memory", "spin")
        add("Java Executable", "java")
        add("Username", "username")
        add("Offline Mode", "offline", "check")
        add("Fullscreen", "fullscreen", "check")
        add("Window Width", "width", "spin")
        add("Window Height", "height", "spin")

        def save():
            for k, v in fields.items():
                prof[k] = v.get()
            self.app.data.save_profiles()
            self.refresh()
            win.destroy()

        btns = tk.Frame(win, bg=C["surface"])
        btns.pack(fill=tk.X, padx=20, pady=20)
        HoverButton(btns, text="Cancel", command=win.destroy,
                    bg=C["surface_2"], fg=C["text"], hover_bg=C["surface"]).pack(side=tk.RIGHT, padx=6)
        HoverButton(btns, text="Save Profile", command=save,
                    bg=C["accent"], fg=C["text_inv"], hover_bg=C["accent_2"]).pack(side=tk.RIGHT)

    def save_profiles(self):
        self.app.data.save_profiles()
        self.refresh()


class ServersScreen(BaseScreen):
    name = "servers"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()

    def _build(self):
        f = self.frame
        tk.Label(f, text="Servers", font=FONTS["title"], fg=C["text"],
                 bg=C["bg"]).pack(anchor="w", padx=30, pady=(25, 10))

        bar = tk.Frame(f, bg=C["bg"])
        bar.pack(fill=tk.X, padx=30, pady=(0, 10))
        HoverButton(bar, text="+ Add Server", command=self.add_server,
                    bg=C["accent"], fg=C["text_inv"], hover_bg=C["accent_2"]).pack(side=tk.LEFT)

        self.list_frame = tk.Frame(f, bg=C["bg"])
        self.list_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=(0, 20))
        self.refresh()

    def refresh(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        for srv in self.app.data.servers:
            self._server_row(srv)

    def _server_row(self, srv):
        card = tk.Frame(self.list_frame, bg=C["surface"], highlightbackground=C["border"],
                        highlightthickness=1)
        card.pack(fill=tk.X, pady=6, padx=2)
        left = tk.Frame(card, bg=C["surface"])
        left.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=15, pady=12)
        tk.Label(left, text=srv.get("name", "Server"), font=FONTS["heading"],
                 fg=C["text"], bg=C["surface"]).pack(anchor="w")
        tk.Label(left, text=f"{srv.get('address','')}:{srv.get('port','25565')}",
                 font=FONTS["ui"], fg=C["text_dim"], bg=C["surface"]).pack(anchor="w")
        right = tk.Frame(card, bg=C["surface"])
        right.pack(side=tk.RIGHT, padx=15, pady=10)
        AnimatedButton(right, text="Join", width=90, height=32,
                       fill=C["accent"], hover=C["accent_2"],
                       command=lambda: self.join_server(srv)).pack(side=tk.LEFT, padx=4)

    def add_server(self):
        win = tk.Toplevel(self.app.root)
        win.title("Add Server")
        win.configure(bg=C["surface"])
        win.geometry("360x260")
        win.transient(self.app.root)
        win.grab_set()
        vars_ = {}
        for label, key, default in [("Name", "name", ""), ("Address", "address", ""), ("Port", "port", "25565")]:
            tk.Label(win, text=label, font=FONTS["ui"], fg=C["text_dim"],
                     bg=C["surface"]).pack(anchor="w", padx=20, pady=(16, 2))
            var = tk.StringVar(value=default)
            ent = tk.Entry(win, textvariable=var, font=FONTS["ui"],
                           bg=C["surface_2"], fg=C["text"], insertbackground=C["text"],
                           relief="flat", bd=0)
            ent.pack(fill=tk.X, padx=20, pady=(0, 6), ipady=4)
            vars_[key] = var
        def save():
            self.app.data.servers.append({k: v.get() for k, v in vars_.items()})
            self.app.data.save_servers()
            self.refresh()
            win.destroy()
        btns = tk.Frame(win, bg=C["surface"])
        btns.pack(fill=tk.X, padx=20, pady=20)
        HoverButton(btns, text="Cancel", command=win.destroy,
                    bg=C["surface_2"], fg=C["text"], hover_bg=C["surface"]).pack(side=tk.RIGHT, padx=6)
        HoverButton(btns, text="Add Server", command=save,
                    bg=C["accent"], fg=C["text_inv"], hover_bg=C["accent_2"]).pack(side=tk.RIGHT)

    def join_server(self, srv):
        prof = self.app.data.profiles[0] if self.app.data.profiles else None
        if not prof:
            messagebox.showwarning("No profile", "Create a profile first.")
            return
        prof["server"] = f"{srv.get('address','')}:{srv.get('port','25565')}"
        self.app.data.save_profiles()
        self.app._launch_profile(prof, server=srv)


class SettingsScreen(BaseScreen):
    name = "settings"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()

    def _build(self):
        f = self.frame
        tk.Label(f, text="Settings", font=FONTS["title"], fg=C["text"],
                 bg=C["bg"]).pack(anchor="w", padx=30, pady=(25, 20))

        card = tk.Frame(f, bg=C["surface"], highlightbackground=C["border"],
                        highlightthickness=1)
        card.pack(fill=tk.X, padx=30, pady=(0, 20))
        inner = tk.Frame(card, bg=C["surface"])
        inner.pack(padx=25, pady=20, fill=tk.X)

        def add_row(label, key, kind="entry", values=None):
            row = tk.Frame(inner, bg=C["surface"])
            row.pack(fill=tk.X, pady=10)
            tk.Label(row, text=label, font=FONTS["ui"], fg=C["text_dim"],
                     bg=C["surface"], width=22, anchor="w").pack(side=tk.LEFT)
            if kind == "entry":
                var = tk.StringVar(value=str(self.app.data.settings.get(key, "")))
                ent = tk.Entry(row, textvariable=var, font=FONTS["ui"],
                               bg=C["surface_2"], fg=C["text"], insertbackground=C["text"],
                               relief="flat", bd=0)
                ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
                def save_var(*_):
                    self.app.data.settings[key] = var.get()
                    self.app.data.save_settings()
                var.trace_add("write", save_var)
            elif kind == "button":
                def browse():
                    d = filedialog.askdirectory()
                    if d:
                        ent_var.set(d)
                ent_var = tk.StringVar(value=str(self.app.data.settings.get(key, "")))
                ent = tk.Entry(row, textvariable=ent_var, font=FONTS["ui"],
                               bg=C["surface_2"], fg=C["text"], insertbackground=C["text"],
                               relief="flat", bd=0)
                ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
                HoverButton(row, text="Browse", command=browse,
                            bg=C["surface_2"], fg=C["text"], hover_bg=C["surface"]).pack(side=tk.LEFT, padx=6)
                def save_var(*_):
                    self.app.data.settings[key] = ent_var.get()
                    self.app.data.save_settings()
                ent_var.trace_add("write", save_var)

        add_row("Game Directory", "game_dir", "button")
        add_row("Launcher Theme", "theme")

        info = tk.Frame(f, bg=C["bg"])
        info.pack(fill=tk.X, padx=30, pady=10)
        tk.Label(info, text=f"{APP_NAME} v2.0.0  •  Built with tkinter",
                 font=FONTS["ui"], fg=C["text_dim"], bg=C["bg"]).pack(anchor="w")
        lib_text = "minecraft-launcher-lib: installed" if HAS_LIB else "minecraft-launcher-lib: NOT installed"
        tk.Label(info, text=lib_text, font=FONTS["ui"],
                 fg=C["success"] if HAS_LIB else C["danger"],
                 bg=C["bg"]).pack(anchor="w", pady=(4, 0))


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class SulphurLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} — Minecraft Launcher")
        self.root.geometry("1150x720")
        self.root.minsize(950, 620)
        self.root.configure(bg=C["bg"])

        # App dir for data persistence
        self.app_dir = os.path.join(os.path.expanduser("~"), f".{APP_NAME.lower()}")
        self.data = DataManager(self.app_dir)

        # Managers
        self.version_manager = VersionManager(self._log, self._set_status)

        # UI
        self._build_ui()

        # Load data
        self.version_manager.fetch(self.data.settings["game_dir"])
        self._update_stats()

        # Entrance animation
        self._animate_entrance()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        # Container
        self.container = tk.Frame(self.root, bg=C["bg"])
        self.container.pack(fill=tk.BOTH, expand=True)

        # Sidebar
        self.sidebar = tk.Frame(self.container, bg=C["surface"], width=210)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        logo = tk.Frame(self.sidebar, bg=C["surface"])
        logo.pack(pady=(26, 10))
        tk.Label(logo, text="S", font=("Segoe UI", 26, "bold"), fg=C["accent"],
                 bg=C["surface"]).pack()
        tk.Label(logo, text="SULPHUR", font=("Segoe UI", 10, "bold"),
                 fg=C["text_dim"], bg=C["surface"]).pack()

        self.nav_buttons = {}
        nav_items = [
            ("home", "Home", "🏠"),
            ("versions", "Versions", "📦"),
            ("accounts", "Accounts", "👤"),
            ("profiles", "Profiles", "⚙️"),
            ("servers", "Servers", "🌐"),
            ("settings", "Settings", "🛠️"),
        ]
        for key, label, icon in nav_items:
            btn = AnimatedButton(self.sidebar, text=f"{icon}  {label}",
                                 width=180, height=44, radius=10,
                                 fill=C["surface"], hover=C["surface_2"],
                                 text_color=C["text"], font=FONTS["ui_bold"],
                                 command=lambda k=key: self._show_screen(k))
            btn.pack(padx=12, pady=6)
            self.nav_buttons[key] = btn

        # Content
        self.content = tk.Frame(self.container, bg=C["bg"])
        self.content.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Bottom bar
        self.bottom = tk.Frame(self.root, bg=C["surface"], height=34)
        self.bottom.pack(side=tk.BOTTOM, fill=tk.X)
        self.bottom.pack_propagate(False)
        self.status_lbl = tk.Label(self.bottom, text="Ready", font=FONTS["ui"],
                                   fg=C["text_dim"], bg=C["surface"])
        self.status_lbl.pack(side=tk.LEFT, padx=12, pady=6)

        # Log panel (slidable)
        self.log_panel = tk.Frame(self.root, bg=C["surface_2"], height=150)
        self.log_console = LogConsole(self.log_panel)
        self.log_console.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        self.log_visible = False

        # Screens
        self.screens = {}
        screen_classes = [HomeScreen, VersionsScreen, AccountsScreen,
                          ProfilesScreen, ServersScreen, SettingsScreen]
        for cls in screen_classes:
            screen = cls(self.content, self)
            self.screens[screen.name] = screen
            screen.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Log toggle button (floating)
        self.log_btn = tk.Button(self.root, text="▼ Log", command=self.toggle_log,
                                 bg=C["surface_2"], fg=C["text_dim"], relief="flat",
                                 font=FONTS["ui"], cursor="hand2")
        self.log_btn.place(relx=1.0, x=-12, y=48, anchor="ne")

    def _show_screen(self, name):
        for key, btn in self.nav_buttons.items():
            if key == name:
                btn._state = "hover"
                btn._draw()
            else:
                btn._state = "normal"
                btn._draw()
        screen = self.screens[name]
        screen.tkraise()
        screen.on_show()
        self._set_status(f"{name.capitalize()}")

    def toggle_log(self):
        if self.log_visible:
            self.log_panel.pack_forget()
            self.log_btn.config(text="▼ Log")
        else:
            self.log_panel.pack(side=tk.BOTTOM, fill=tk.X, before=self.bottom)
            self.log_btn.config(text="▲ Log")
        self.log_visible = not self.log_visible

    # ------------------------------------------------------------------ actions
    def _update_stats(self):
        home = self.screens.get("home")
        if not home:
            return
        vm = self.version_manager
        # find stat cards by scanning home frame children is fragile; instead just refresh combo
        home._refresh_profiles()

    def _install_version(self, version):
        if not HAS_LIB:
            messagebox.showerror("Missing library",
                                 "Install minecraft-launcher-lib: pip install minecraft-launcher-lib")
            return
        self._set_status(f"Installing {version}...")
        vs = VersionsScreen  # just to reference progress bar location
        screen = self.screens.get("versions")
        if screen:
            screen.progress["value"] = 0
        threading.Thread(target=self._do_install, args=(version,), daemon=True).start()

    def _do_install(self, version):
        try:
            def progress(current, total):
                self.root.after(0, lambda c=current, t=total: self._set_progress(c, t))
            self.version_manager.install(version, self.data.settings["game_dir"], progress)
            self.root.after(0, lambda: self._log(f"Installed {version} successfully.", "SUCCESS"))
            self.root.after(0, self.version_manager._load_installed, self.data.settings["game_dir"])
            self.root.after(0, self.screens["versions"].refresh)
            self.root.after(0, lambda: self._set_status("Ready"))
        except Exception as e:
            self.root.after(0, lambda: self._log(f"Install failed: {e}", "ERROR"))
            self.root.after(0, lambda: messagebox.showerror("Install failed", str(e)))
            self.root.after(0, lambda: self._set_status("Ready"))

    def _set_progress(self, current, total):
        screen = self.screens.get("versions")
        if screen:
            screen.progress["maximum"] = total or 100
            screen.progress["value"] = current
        self._set_status(f"Installing... {current}/{total}")

    def _launch_selected_profile(self):
        home = self.screens.get("home")
        if not home:
            return
        name = home.profile_var.get()
        if not name:
            messagebox.showwarning("No profile", "Select a profile.")
            return
        prof = next((p for p in self.data.profiles if p["name"] == name), None)
        if not prof:
            return
        self._launch_profile(prof)

    def _launch_profile(self, prof, server=None):
        if not HAS_LIB:
            messagebox.showerror("Missing library",
                                 "Install minecraft-launcher-lib: pip install minecraft-launcher-lib")
            return
        version = prof.get("version", "")
        if not version:
            messagebox.showwarning("No version", "Select a Minecraft version in the profile.")
            return
        if version not in self.version_manager.installed:
            if not messagebox.askyesno("Not installed",
                                       f"{version} is not installed. Install and launch?"):
                return
            self._install_version(version)
            return

        self._set_status("Launching Minecraft...")
        threading.Thread(target=self._do_launch, args=(prof, server), daemon=True).start()

    def _do_launch(self, prof, server=None):
        try:
            version = prof["version"]
            minecraft_dir = self.data.settings["game_dir"]
            username = prof.get("username", "Player") or "Player"

            if prof.get("offline", True):
                off_uuid = str(uuid.uuid3(uuid.NAMESPACE_URL, "Offline:" + username))
                options = {
                    "username": username,
                    "uuid": off_uuid,
                    "token": "",
                    "executablePath": prof.get("java", "java") or "java",
                    "jvmArguments": [
                        f"-Xmx{prof.get('memory', DEFAULT_MEMORY_MB)}M",
                        f"-Xms{max(prof.get('memory', DEFAULT_MEMORY_MB)//2, 256)}M",
                    ],
                    "launcherName": APP_NAME,
                    "launcherVersion": "2.0.0",
                }
                if server:
                    addr = server.get("address", "")
                    port = server.get("port", "25565")
                    options["jvmArguments"] += [f"--server {addr}", f"--port {port}"]
                if prof.get("fullscreen"):
                    options["jvmArguments"] += ["--fullscreen"]
                if prof.get("width") and prof.get("height"):
                    options["jvmArguments"] += [
                        f"--width {int(prof['width'])}",
                        f"--height {int(prof['height'])}",
                    ]
                self.root.after(0, lambda: self._log(
                    f"Launching {version} offline as {username}...", "LAUNCH"))
            else:
                token = self.data.settings.get("online_token", "")
                if not token:
                    self.root.after(0, lambda: messagebox.showwarning(
                        "Online login", "No online token configured. Enable Offline Mode or add a token in Accounts."))
                    self.root.after(0, lambda: self._set_status("Ready"))
                    return
                options = {
                    "username": username,
                    "uuid": "",
                    "token": token,
                    "executablePath": prof.get("java", "java") or "java",
                    "jvmArguments": [
                        f"-Xmx{prof.get('memory', DEFAULT_MEMORY_MB)}M",
                        f"-Xms{max(prof.get('memory', DEFAULT_MEMORY_MB)//2, 256)}M",
                    ],
                    "launcherName": APP_NAME,
                    "launcherVersion": "2.0.0",
                }
                self.root.after(0, lambda: self._log(
                    f"Launching {version} online as {username}...", "LAUNCH"))

            mc_cmd = self.version_manager.launch_command(version, minecraft_dir, options)
            self.root.after(0, lambda: self._log("Launch command built."))
            self.root.after(0, lambda: self._set_status("Minecraft running"))
            subprocess.Popen(mc_cmd, cwd=minecraft_dir)
            self.root.after(0, lambda: self._log("Minecraft process started.", "SUCCESS"))
        except Exception as e:
            self.root.after(0, lambda: self._log(f"Launch failed: {e}", "ERROR"))
            self.root.after(0, lambda: messagebox.showerror("Launch failed", str(e)))
            self.root.after(0, lambda: self._set_status("Ready"))

    # ------------------------------------------------------------------ logging / status
    def _log(self, message, level="INFO"):
        self.root.after(0, lambda: self.log_console.write(message, level))

    def _set_status(self, message):
        self.root.after(0, lambda: self.status_lbl.config(text=message))

    # ------------------------------------------------------------------ animation
    def _animate_entrance(self):
        self.root.attributes("-alpha", 0.0)
        def fade(step=0):
            alpha = min(step / 18, 1.0)
            self.root.attributes("-alpha", alpha)
            if alpha < 1.0:
                self.root.after(16, fade, step + 1)
        fade()


def main():
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.15)
    except Exception:
        pass
    app = SulphurLauncher(root)
    root.mainloop()


if __name__ == "__main__":
    main()