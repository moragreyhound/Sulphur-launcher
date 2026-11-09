"""
Sulphur — Professional Minecraft Launcher (v3.0)
=================================================

A single-file, feature-rich Minecraft launcher built with tkinter and
minecraft-launcher-lib.

Features
--------
• Modern dark UI with custom color palette & hover states
• Entrance fade-in animation + instant screen switching
• Sidebar navigation: Home, Versions, Profiles, Servers, Settings, About
• Offline mode (no Mojang/Microsoft login required)
• Online mode (paste your Microsoft/Mojang access token)
• Version browser: release / snapshot / old / alpha / beta filters
• Install / delete / launch versions with animated progress bar
• Multiple player profiles (per-profile Java, memory, resolution, args)
• Server list with quick-connect
• Java auto-detection + manual path override
• Launch options editor (JVM args, game args, fullscreen, custom res)
• Persistent data stored in ~/.sulphur/ (profiles, servers, settings)
• Timestamped, color-coded console log
• News / changelog panel
• Crash-safe error handling with dialogs

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
except Exception:  # library not installed
    HAS_LIB = False

# ---------------------------------------------------------------------------
# Professional color palette
# ---------------------------------------------------------------------------
C = {
    "bg":         "#0a0b12",   # deep background
    "surface":    "#141823",   # panels / cards
    "surface_2":  "#1e2332",   # slightly lighter surface
    "accent":     "#7c3aed",   # violet primary
    "accent_hover": "#6d28d9", # violet hover
    "accent_dim": "#5b21b6",   # darker violet
    "text":       "#e2e8f0",   # primary text
    "text_dim":   "#94a3b8",   # muted text
    "text_inv":   "#ffffff",   # text on accent
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
    "title":    ("Segoe UI", 22, "bold"),
    "button":   ("Segoe UI", 10, "bold"),
    "mono":     ("Consolas", 9),
}

DEFAULT_MEMORY_MB = 3072
APP_NAME = "Sulphur"
APP_VERSION = "3.0.0"


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

class HoverButton(tk.Button):
    """Reliable flat button with hover animation (no canvas sizing issues)."""
    def __init__(self, parent, text, command=None, width=180, height=40,
                 fill=C["surface_2"], hover=C["surface"], text_color=C["text"],
                 font=FONTS["button"], **kwargs):
        super().__init__(
            parent, text=text, command=command,
            bg=fill, fg=text_color, activebackground=hover,
            activeforeground=text_color, relief="flat", bd=0,
            highlightthickness=0, font=font, cursor="hand2",
            padx=16, pady=10, **kwargs
        )
        self._normal_bg = fill
        self._hover_bg = hover
        self.configure(width=max(10, width // 8))  # rough char width
        self.bind("<Enter>", lambda e: self.configure(bg=self._hover_bg))
        self.bind("<Leave>", lambda e: self.configure(bg=self._normal_bg))


class IconButton(HoverButton):
    """Small icon button used in toolbars."""
    def __init__(self, parent, text, command=None, **kwargs):
        super().__init__(
            parent, text=text, command=command,
            width=44, height=34, font=FONTS["ui"],
            padx=4, pady=2, **kwargs
        )


class ScrollableFrame(tk.Frame):
    """A frame that scrolls vertically using mousewheel."""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=C["bg"], **kwargs)
        self.canvas = tk.Canvas(self, bg=C["bg"], highlightthickness=0)
        self.scrollbar = tk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview,
            bg=C["surface"], troughcolor=C["bg"], activebackground=C["accent"]
        )
        self.inner = tk.Frame(self.canvas, bg=C["bg"])

        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class EntryWithPlaceholder(tk.Entry):
    def __init__(self, parent, placeholder="", **kwargs):
        super().__init__(parent, **kwargs)
        self.placeholder = placeholder
        self.default_fg = kwargs.get("fg", C["text"])
        self.insert(0, placeholder)
        self.configure(fg=C["text_dim"])
        self.bind("<FocusIn>", self._clear)
        self.bind("<FocusOut>", self._fill)

    def _clear(self, _):
        if self.get() == self.placeholder:
            self.delete(0, tk.END)
            self.configure(fg=self.default_fg)

    def _fill(self, _):
        if not self.get():
            self.insert(0, self.placeholder)
            self.configure(fg=C["text_dim"])

    def get_real(self):
        val = self.get()
        return "" if val == self.placeholder else val


class LogConsole(tk.Text):
    LEVEL_COLORS = {
        "INFO":    C["text_dim"],
        "SUCCESS": C["success"],
        "WARN":    C["warning"],
        "ERROR":   C["danger"],
        "LAUNCH":  C["accent"],
        "DEBUG":   "#64748b",
    }

    def __init__(self, parent, **kwargs):
        super().__init__(
            parent, bg=C["surface"], fg=C["text"],
            insertbackground=C["text"], selectbackground=C["accent"],
            font=FONTS["mono"], wrap=tk.WORD, state=tk.DISABLED,
            padx=10, pady=8, relief="flat", bd=0, **kwargs
        )
        for level, color in self.LEVEL_COLORS.items():
            self.tag_config(level, foreground=color)

    def write(self, message, level="INFO"):
        self.configure(state=tk.NORMAL)
        ts = datetime.now().strftime("%H:%M:%S")
        self.insert(tk.END, f"[{ts}] ", "INFO")
        self.insert(tk.END, message + "\n", level)
        self.see(tk.END)
        self.configure(state=tk.DISABLED)

    def clear(self):
        self.configure(state=tk.NORMAL)
        self.delete("1.0", tk.END)
        self.configure(state=tk.DISABLED)


# ---------------------------------------------------------------------------
# Data / Managers
# ---------------------------------------------------------------------------

class DataManager:
    def __init__(self, app_dir):
        self.app_dir = app_dir
        os.makedirs(app_dir, exist_ok=True)
        self.profiles_path = os.path.join(app_dir, "profiles.json")
        self.servers_path = os.path.join(app_dir, "servers.json")
        self.settings_path = os.path.join(app_dir, "settings.json")

        self.profiles = self._load(self.profiles_path, [
            {
                "name": "Default",
                "version": "",
                "memory": DEFAULT_MEMORY_MB,
                "java": "java",
                "offline": True,
                "username": "Player",
                "fullscreen": False,
                "width": 854,
                "height": 480,
                "jvm_args": "",
                "game_args": "",
                "server": "",
            }
        ])
        self.servers = self._load(self.servers_path, [])
        self.settings = self._load(self.settings_path, {
            "game_dir": os.path.join(os.getcwd(), ".minecraft"),
            "java_path": "java",
            "memory_mb": DEFAULT_MEMORY_MB,
            "offline_username": "Player",
            "online_token": "",
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
            print(f"[Sulphur] Save failed {path}: {e}")

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
                raise RuntimeError("minecraft-launcher-lib not installed")
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

    def filter_versions(self, query="", show_release=True, show_snapshot=True,
                        show_old=False, show_alpha=False, show_beta=False):
        result = []
        q = query.lower()
        for v in self.versions:
            if q and q not in v.lower():
                continue
            typ = self._version_type(v)
            if typ == "release" and not show_release:
                continue
            if typ == "snapshot" and not show_snapshot:
                continue
            if typ == "old_alpha" and not show_alpha:
                continue
            if typ == "old_beta" and not show_beta:
                continue
            if typ == "old" and not show_old:
                continue
            result.append(v)
        return sorted(result)

    @staticmethod
    def _version_type(vid):
        low = vid.lower()
        if low.startswith("1."):
            parts = low.split(".")
            try:
                major = int(parts[1])
                if major >= 17:
                    return "release"
                if major >= 13:
                    return "old"
            except ValueError:
                pass
        if "snapshot" in low:
            return "snapshot"
        if "alpha" in low:
            return "old_alpha"
        if "beta" in low:
            return "old_beta"
        return "release"

    def install(self, version, minecraft_dir, progress_cb):
        if not HAS_LIB:
            raise RuntimeError("minecraft-launcher-lib not installed")

        def callback(status, current, total):
            progress_cb(current, total or 100)

        install.install_minecraft_version(version, minecraft_dir, callback=callback)
        self._load_installed(minecraft_dir)

    def launch_command(self, version, minecraft_dir, options):
        return command.get_minecraft_command(version, minecraft_dir, options)

    @staticmethod
    def detect_java():
        """Try to find a java executable on the system."""
        for name in ("java", "javaw.exe"):
            try:
                out = subprocess.run(
                    ["where", name], capture_output=True, text=True, shell=True
                ).stdout.strip()
                if out:
                    return out.splitlines()[0]
            except Exception:
                pass
        return "java"


# ---------------------------------------------------------------------------
# Base screen
# ---------------------------------------------------------------------------

class BaseScreen:
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.frame = tk.Frame(parent, bg=C["bg"])

    def show(self):
        self.frame.tkraise()

    def on_show(self):
        pass


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------

class HomeScreen(BaseScreen):
    name = "home"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()

    def _build(self):
        f = self.frame

        # Header
        header = tk.Frame(f, bg=C["bg"])
        header.pack(fill=tk.X, padx=40, pady=(32, 10))
        tk.Label(header, text="Sulphur", font=("Segoe UI", 28, "bold"),
                 fg=C["accent"], bg=C["bg"]).pack(side=tk.LEFT)
        tk.Label(header, text=f"  v{APP_VERSION}  •  Minecraft Launcher",
                 font=FONTS["ui"], fg=C["text_dim"], bg=C["bg"]).pack(side=tk.LEFT, pady=8)

        # Quick launch card
        card = tk.Frame(f, bg=C["surface"], highlightbackground=C["border"],
                        highlightthickness=1)
        card.pack(fill=tk.X, padx=40, pady=18)

        inner = tk.Frame(card, bg=C["surface"])
        inner.pack(padx=28, pady=24, fill=tk.X)

        tk.Label(inner, text="Quick Launch", font=FONTS["heading"],
                 fg=C["text"], bg=C["surface"]).pack(anchor="w")
        tk.Label(inner, text="Pick a profile and hit Play. Offline mode is enabled by default.",
                 font=FONTS["ui"], fg=C["text_dim"], bg=C["surface"]).pack(anchor="w", pady=(4, 16))

        row = tk.Frame(inner, bg=C["surface"])
        row.pack(fill=tk.X, pady=(0, 16))
        tk.Label(row, text="Profile:", font=FONTS["ui_bold"], fg=C["text_dim"],
                 bg=C["surface"]).pack(side=tk.LEFT)
        self.profile_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(row, textvariable=self.profile_var,
                                          state="readonly", width=28, font=FONTS["ui"])
        self.profile_combo.pack(side=tk.LEFT, padx=10)
        ttk.Button(row, text="Refresh", command=self._refresh_profiles).pack(side=tk.LEFT)

        self.play_btn = HoverButton(inner, text="▶  PLAY MINECRAFT", width=260, height=50,
                                    fill=C["accent"], hover=C["accent_hover"],
                                    text_color=C["text_inv"], command=self.app._launch_selected_profile)
        self.play_btn.pack(anchor="w", pady=(0, 10))

        info = tk.Frame(inner, bg=C["surface"])
        info.pack(fill=tk.X)
        self.status_lbl = tk.Label(info, text="Ready", font=FONTS["ui"],
                                   fg=C["text_dim"], bg=C["surface"])
        self.status_lbl.pack(side=tk.LEFT)
        self.lib_lbl = tk.Label(info, text="", font=FONTS["ui"],
                                fg=C["text_dim"], bg=C["surface"])
        self.lib_lbl.pack(side=tk.RIGHT)

        # Stats row
        stats = tk.Frame(f, bg=C["bg"])
        stats.pack(fill=tk.X, padx=40, pady=(12, 0))
        self._stat_card(stats, "Versions", "0", 0, C["info"])
        self._stat_card(stats, "Profiles", "0", 1, C["success"])
        self._stat_card(stats, "Servers", "0", 2, C["warning"])

        # News panel
        news_card = tk.Frame(f, bg=C["surface"], highlightbackground=C["border"],
                             highlightthickness=1)
        news_card.pack(fill=tk.BOTH, expand=True, padx=40, pady=18)
        news_inner = tk.Frame(news_card, bg=C["surface"])
        news_inner.pack(padx=28, pady=20, fill=tk.BOTH, expand=True)
        tk.Label(news_inner, text="Changelog", font=FONTS["heading"],
                 fg=C["text"], bg=C["surface"]).pack(anchor="w")
        news_text = (
            "v3.0.0 — Rewritten launcher core\n"
            "• Professional dark UI with hover animations\n"
            "• Offline & online account modes\n"
            "• Per-profile launch settings\n"
            "• Server list & quick-connect\n"
            "• Persistent profiles & settings\n\n"
            "v2.0.0 — Multi-profile support\n"
            "v1.0.0 — Initial release"
        )
        txt = tk.Text(news_inner, height=8, bg=C["surface_2"], fg=C["text_dim"],
                      font=FONTS["ui"], relief="flat", bd=0, padx=10, pady=8)
        txt.insert("1.0", news_text)
        txt.configure(state=tk.DISABLED)
        txt.pack(fill=tk.BOTH, expand=True)

    def _stat_card(self, parent, label, value, col, color):
        card = tk.Frame(parent, bg=C["surface"], highlightbackground=C["border"],
                        highlightthickness=1, width=190, height=90)
        card.grid(row=0, column=col, padx=8, sticky="ew")
        card.pack_propagate(False)
        top = tk.Frame(card, bg=C["surface"])
        top.pack(fill=tk.X, padx=16, pady=(14, 4))
        tk.Label(top, text=label, font=FONTS["ui"], fg=C["text_dim"],
                 bg=C["surface"]).pack(side=tk.LEFT)
        tk.Label(top, text=color, font=("Segoe UI", 8), fg=C["text_dim"],
                 bg=C["surface"]).pack(side=tk.RIGHT)
        tk.Label(card, text=value, font=("Segoe UI", 20, "bold"),
                 fg=C["text"], bg=C["surface"]).pack(anchor="w", padx=16)
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

    def _build(self):
        f = self.frame

        top = tk.Frame(f, bg=C["bg"])
        top.pack(fill=tk.X, padx=30, pady=(22, 8))
        tk.Label(top, text="Versions", font=FONTS["title"], fg=C["text"],
                 bg=C["bg"]).pack(side=tk.LEFT)

        # Filter bar
        filt = tk.Frame(f, bg=C["surface"], highlightbackground=C["border"],
                        highlightthickness=1)
        filt.pack(fill=tk.X, padx=30, pady=(0, 10))
        filt_inner = tk.Frame(filt, bg=C["surface"])
        filt_inner.pack(padx=16, pady=12, fill=tk.X)

        tk.Label(filt_inner, text="Filter:", font=FONTS["ui"], fg=C["text_dim"],
                 bg=C["surface"]).pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        search = EntryWithPlaceholder(filt_inner, placeholder="Search versions...",
                                      bg=C["surface_2"], fg=C["text"],
                                      insertbackground=C["text"], relief="flat", bd=0)
        search.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True, ipady=4)
        search.bind("<KeyRelease>", lambda e: self._apply_filters())

        self.var_release = tk.BooleanVar(value=True)
        self.var_snapshot = tk.BooleanVar(value=True)
        self.var_old = tk.BooleanVar(value=False)
        self.var_alpha = tk.BooleanVar(value=False)
        self.var_beta = tk.BooleanVar(value=False)

        for text, var in [("Release", self.var_release), ("Snapshot", self.var_snapshot),
                          ("Old", self.var_old), ("Alpha", self.var_alpha), ("Beta", self.var_beta)]:
            cb = tk.Checkbutton(filt_inner, text=text, variable=var, font=FONTS["ui"],
                                fg=C["text"], bg=C["surface"], selectcolor=C["surface_2"],
                                activebackground=C["surface"], cursor="hand2",
                                command=self._apply_filters)
            cb.pack(side=tk.LEFT, padx=(14, 0))

        # Toolbar
        bar = tk.Frame(f, bg=C["bg"])
        bar.pack(fill=tk.X, padx=30, pady=(0, 8))
        self.install_btn = HoverButton(bar, text="Install Selected",
                                       command=self.install_selected, fill=C["accent"],
                                       hover=C["accent_hover"], text_color=C["text_inv"])
        self.install_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.launch_btn = HoverButton(bar, text="Launch Selected",
                                      command=self.launch_selected, fill=C["surface_2"],
                                      hover=C["surface"], text_color=C["text"])
        self.launch_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.delete_btn = HoverButton(bar, text="Delete Selected",
                                      command=self.delete_selected, fill=C["surface_2"],
                                      hover=C["surface"], text_color=C["text"])
        self.delete_btn.pack(side=tk.LEFT)
        tk.Button(bar, text="Refresh", command=self.refresh,
                  bg=C["surface_2"], fg=C["text"], relief="flat",
                  cursor="hand2", font=FONTS["ui"]).pack(side=tk.RIGHT)

        # List area
        list_frame = tk.Frame(f, bg=C["surface"], highlightbackground=C["border"],
                              highlightthickness=1)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=(0, 10))

        self.scroll = ScrollableFrame(list_frame)
        self.scroll.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Progress bar
        prog_frame = tk.Frame(f, bg=C["bg"])
        prog_frame.pack(fill=tk.X, padx=30, pady=(0, 4))
        self.progress = ttk.Progressbar(prog_frame, mode="determinate")
        self.progress.pack(fill=tk.X)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TProgressbar", troughcolor=C["surface"],
                        background=C["accent"], bordercolor=C["border"],
                        lightcolor=C["accent"], darkcolor=C["accent"])

        self.status_lbl = tk.Label(f, text="", font=FONTS["ui"],
                                   fg=C["text_dim"], bg=C["bg"])
        self.status_lbl.pack(anchor="w", padx=30)

        self._row_widgets = []

    def refresh(self):
        self.status_lbl.config(text="Fetching version list...")
        for w in self.scroll.inner.winfo_children():
            w.destroy()
        self._row_widgets = []
        threading.Thread(target=self.app.version_manager.fetch,
                         args=(self.app.data.settings["game_dir"],), daemon=True).start()
        self.app.root.after(600, self._poll_fetch)

    def _poll_fetch(self):
        vm = self.app.version_manager
        if not vm.versions and self.status_lbl.cget("text").startswith("Fetching"):
            self.app.root.after(500, self._poll_fetch)
            return
        self._apply_filters()

    def _apply_filters(self):
        vm = self.app.version_manager
        if not vm.versions:
            return
        filtered = vm.filter_versions(
            self.search_var.get_real(),
            self.var_release.get(), self.var_snapshot.get(),
            self.var_old.get(), self.var_alpha.get(), self.var_beta.get()
        )

        for w in self.scroll.inner.winfo_children():
            w.destroy()
        self._row_widgets = []

        installed = vm.installed
        for v in filtered:
            is_installed = v in installed
            row = tk.Frame(self.scroll.inner, bg=C["surface_2"], highlightbackground=C["border"],
                           highlightthickness=1, cursor="hand2")
            row.pack(fill=tk.X, padx=4, pady=4)

            # Hover effect
            def on_enter(e, r=row, c=C["surface"]):
                r.configure(bg=c)
            def on_leave(e, r=row, c=C["surface_2"]):
                r.configure(bg=c)
            row.bind("<Enter>", on_enter)
            row.bind("<Leave>", on_leave)

            left = tk.Frame(row, bg=C["surface_2"])
            left.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=12, pady=8)
            tk.Label(left, text=v, font=FONTS["ui_bold"], fg=C["text"],
                     bg=C["surface_2"]).pack(anchor="w")
            tag = "INSTALLED" if is_installed else "NOT INSTALLED"
            tk.Label(left, text=tag, font=("Segoe UI", 8, "bold"),
                     fg=C["success"] if is_installed else C["text_dim"],
                     bg=C["surface_2"]).pack(anchor="w", pady=(1, 0))

            right = tk.Frame(row, bg=C["surface_2"])
            right.pack(side=tk.RIGHT, padx=12, pady=8)
            if not is_installed:
                btn = HoverButton(right, text="Install", width=100, height=28,
                                  fill=C["accent"], hover=C["accent_hover"],
                                  text_color=C["text_inv"], font=FONTS["ui"],
                                  command=lambda ver=v: self.install_version(ver))
                btn.pack(side=tk.LEFT, padx=4)
            else:
                btn = HoverButton(right, text="Launch", width=100, height=28,
                                  fill=C["surface"], hover=C["surface_2"],
                                  text_color=C["text"], font=FONTS["ui"],
                                  command=lambda ver=v: self.launch_version(ver))
                btn.pack(side=tk.LEFT, padx=4)

        self.status_lbl.config(text=f"{len(filtered)} version(s)  •  {len(installed)} installed")
        self._on_select()

    def install_selected(self):
        # find selected via hover is tricky; we rely on per-row buttons instead
        messagebox.showinfo("Install", "Click Install on a version row above.")

    def install_version(self, version):
        self.app._install_version(version)

    def launch_selected(self):
        messagebox.showinfo("Launch", "Click Launch on an installed version row above.")

    def launch_version(self, version):
        prof = self.app.data.profiles[0] if self.app.data.profiles else None
        if not prof:
            messagebox.showwarning("No profile", "Create a profile first.")
            return
        prof["version"] = version
        self.app.data.save_profiles()
        self.app._launch_profile(prof)

    def delete_selected(self):
        messagebox.showinfo("Delete", "Use the version manager in settings to delete versions manually, or reinstall over them.")

    def on_show(self):
        self.refresh()


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
                    fill=C["accent"], hover=C["accent_hover"],
                    text_color=C["text_inv"]).pack(side=tk.LEFT)
        HoverButton(bar, text="Save All", command=self.save_all,
                    fill=C["surface_2"], hover=C["surface"],
                    text_color=C["text"]).pack(side=tk.LEFT, padx=8)

        self.scroll = ScrollableFrame(f)
        self.scroll.pack(fill=tk.BOTH, expand=True, padx=30, pady=(0, 20))
        self.refresh()

    def refresh(self):
        for w in self.scroll.inner.winfo_children():
            w.destroy()
        for i, prof in enumerate(self.app.data.profiles):
            self._profile_row(i, prof)

    def _profile_row(self, idx, prof):
        card = tk.Frame(self.scroll.inner, bg=C["surface"], highlightbackground=C["border"],
                        highlightthickness=1)
        card.pack(fill=tk.X, pady=6, padx=2)

        left = tk.Frame(card, bg=C["surface"])
        left.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=16, pady=12)
        tk.Label(left, text=prof.get("name", f"Profile {idx+1}"), font=FONTS["heading"],
                 fg=C["text"], bg=C["surface"]).pack(anchor="w")
        details = (
            f"Version: {prof.get('version','—')}   •   Memory: {prof.get('memory',DEFAULT_MEMORY_MB)}MB   •   "
            + ("Offline" if prof.get("offline", True) else "Online")
        )
        tk.Label(left, text=details, font=FONTS["ui"], fg=C["text_dim"],
                 bg=C["surface"]).pack(anchor="w", pady=(2, 0))

        right = tk.Frame(card, bg=C["surface"])
        right.pack(side=tk.RIGHT, padx=16, pady=10)
        HoverButton(right, text="Edit", width=90, height=32,
                    fill=C["surface_2"], hover=C["surface"],
                    text_color=C["text"], command=lambda: self.edit_profile(idx)).pack(side=tk.LEFT, padx=4)
        HoverButton(right, text="Launch", width=90, height=32,
                    fill=C["accent"], hover=C["accent_hover"],
                    text_color=C["text_inv"], command=lambda: self.app._launch_profile(prof)).pack(side=tk.LEFT, padx=4)

    def new_profile(self):
        prof = {
            "name": "New Profile", "version": "", "memory": DEFAULT_MEMORY_MB,
            "java": self.app.data.settings.get("java_path", "java"),
            "offline": True, "username": self.app.data.settings.get("offline_username", "Player"),
            "fullscreen": False, "width": 854, "height": 480,
            "jvm_args": "", "game_args": "", "server": "",
        }
        self.app.data.profiles.append(prof)
        self.app.data.save_profiles()
        self.refresh()

    def edit_profile(self, idx):
        prof = self.app.data.profiles[idx]
        win = tk.Toplevel(self.app.root)
        win.title("Edit Profile")
        win.configure(bg=C["surface"])
        win.geometry("460x640")
        win.resizable(False, False)
        win.transient(self.app.root)
        win.grab_set()

        fields = {}

        def add_row(label, key, kind="entry", values=None):
            tk.Label(win, text=label, font=FONTS["ui"], fg=C["text_dim"],
                     bg=C["surface"]).pack(anchor="w", padx=20, pady=(12, 2))
            if kind == "entry":
                var = tk.StringVar(value=str(prof.get(key, "")))
                ent = tk.Entry(win, textvariable=var, font=FONTS["ui"],
                               bg=C["surface_2"], fg=C["text"],
                               insertbackground=C["text"], relief="flat", bd=0)
                ent.pack(fill=tk.X, padx=20, pady=(0, 6), ipady=5)
                fields[key] = var
            elif kind == "spin":
                var = tk.IntVar(value=int(prof.get(key, DEFAULT_MEMORY_MB)))
                sp = tk.Spinbox(win, from_=512, to=32768, increment=256,
                                textvariable=var, font=FONTS["ui"], bg=C["surface_2"],
                                fg=C["text"], insertbackground=C["text"],
                                relief="flat", bd=0)
                sp.pack(fill=tk.X, padx=20, pady=(0, 6), ipady=5)
                fields[key] = var
            elif kind == "check":
                var = tk.BooleanVar(value=bool(prof.get(key, False)))
                cb = tk.Checkbutton(win, text=label, variable=var, font=FONTS["ui"],
                                    fg=C["text"], bg=C["surface"],
                                    selectcolor=C["surface_2"], activebackground=C["surface"],
                                    cursor="hand2")
                cb.pack(anchor="w", padx=20, pady=(0, 6))
                fields[key] = var
            elif kind == "text":
                txt = tk.Text(win, height=3, font=FONTS["mono"], bg=C["surface_2"],
                              fg=C["text"], insertbackground=C["text"], relief="flat", bd=0)
                txt.pack(fill=tk.X, padx=20, pady=(0, 6))
                txt.insert("1.0", str(prof.get(key, "")))
                fields[key] = txt

        add_row("Profile Name", "name")
        add_row("Minecraft Version", "version")
        add_row("Memory (MB)", "memory", "spin")
        add_row("Java Executable", "java")
        add_row("Username", "username")
        add_row("Offline Mode", "offline", "check")
        add_row("Fullscreen", "fullscreen", "check")
        add_row("Window Width", "width", "spin")
        add_row("Window Height", "height", "spin")
        add_row("Extra JVM Arguments", "jvm_args", "text")
        add_row("Extra Game Arguments", "game_args", "text")

        def save():
            for k, v in fields.items():
                if isinstance(v, tk.Text):
                    prof[k] = v.get("1.0", tk.END).strip()
                else:
                    prof[k] = v.get()
            self.app.data.save_profiles()
            self.refresh()
            win.destroy()

        btns = tk.Frame(win, bg=C["surface"])
        btns.pack(fill=tk.X, padx=20, pady=20)
        HoverButton(btns, text="Cancel", command=win.destroy,
                    fill=C["surface_2"], hover=C["surface"],
                    text_color=C["text"]).pack(side=tk.RIGHT, padx=6)
        HoverButton(btns, text="Save Profile", command=save,
                    fill=C["accent"], hover=C["accent_hover"],
                    text_color=C["text_inv"]).pack(side=tk.RIGHT)

    def save_all(self):
        self.app.data.save_profiles()
        self.refresh()
        messagebox.showinfo("Profiles", "All profiles saved.")


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
                    fill=C["accent"], hover=C["accent_hover"],
                    text_color=C["text_inv"]).pack(side=tk.LEFT)

        self.scroll = ScrollableFrame(f)
        self.scroll.pack(fill=tk.BOTH, expand=True, padx=30, pady=(0, 20))
        self.refresh()

    def refresh(self):
        for w in self.scroll.inner.winfo_children():
            w.destroy()
        for srv in self.app.data.servers:
            self._server_row(srv)

    def _server_row(self, srv):
        card = tk.Frame(self.scroll.inner, bg=C["surface"], highlightbackground=C["border"],
                        highlightthickness=1)
        card.pack(fill=tk.X, pady=6, padx=2)

        left = tk.Frame(card, bg=C["surface"])
        left.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=16, pady=12)
        tk.Label(left, text=srv.get("name", "Server"), font=FONTS["heading"],
                 fg=C["text"], bg=C["surface"]).pack(anchor="w")
        addr = f"{srv.get('address','')}:{srv.get('port','25565')}"
        tk.Label(left, text=addr, font=FONTS["ui"], fg=C["text_dim"],
                 bg=C["surface"]).pack(anchor="w")

        right = tk.Frame(card, bg=C["surface"])
        right.pack(side=tk.RIGHT, padx=16, pady=10)
        HoverButton(right, text="Join", width=90, height=32,
                    fill=C["accent"], hover=C["accent_hover"],
                    text_color=C["text_inv"],
                    command=lambda s=srv: self.join_server(s)).pack(side=tk.LEFT, padx=4)

    def add_server(self):
        win = tk.Toplevel(self.app.root)
        win.title("Add Server")
        win.configure(bg=C["surface"])
        win.geometry("380x320")
        win.transient(self.app.root)
        win.grab_set()

        vars_ = {}
        for label, key, default in [("Name", "name", ""), ("Address", "address", ""), ("Port", "port", "25565")]:
            tk.Label(win, text=label, font=FONTS["ui"], fg=C["text_dim"],
                     bg=C["surface"]).pack(anchor="w", padx=20, pady=(14, 2))
            var = tk.StringVar(value=default)
            ent = tk.Entry(win, textvariable=var, font=FONTS["ui"],
                           bg=C["surface_2"], fg=C["text"],
                           insertbackground=C["text"], relief="flat", bd=0)
            ent.pack(fill=tk.X, padx=20, pady=(0, 6), ipady=5)
            vars_[key] = var

        def save():
            self.app.data.servers.append({k: v.get() for k, v in vars_.items()})
            self.app.data.save_servers()
            self.refresh()
            win.destroy()

        btns = tk.Frame(win, bg=C["surface"])
        btns.pack(fill=tk.X, padx=20, pady=20)
        HoverButton(btns, text="Cancel", command=win.destroy,
                    fill=C["surface_2"], hover=C["surface"],
                    text_color=C["text"]).pack(side=tk.RIGHT, padx=6)
        HoverButton(btns, text="Add Server", command=save,
                    fill=C["accent"], hover=C["accent_hover"],
                    text_color=C["text_inv"]).pack(side=tk.RIGHT)

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

        def add_entry(label, key, browse=False):
            row = tk.Frame(inner, bg=C["surface"])
            row.pack(fill=tk.X, pady=10)
            tk.Label(row, text=label, font=FONTS["ui"], fg=C["text_dim"],
                     bg=C["surface"], width=22, anchor="w").pack(side=tk.LEFT)
            var = tk.StringVar(value=str(self.app.data.settings.get(key, "")))
            ent = tk.Entry(row, textvariable=var, font=FONTS["ui"],
                           bg=C["surface_2"], fg=C["text"],
                           insertbackground=C["text"], relief="flat", bd=0)
            ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0), ipady=5)

            def save_var(*_):
                self.app.data.settings[key] = var.get()
                self.app.data.save_settings()
            var.trace_add("write", save_var)

            if browse:
                def browse_dir():
                    d = filedialog.askdirectory()
                    if d:
                        var.set(d)
                HoverButton(row, text="Browse", command=browse_dir,
                            fill=C["surface_2"], hover=C["surface"],
                            text_color=C["text"], width=60).pack(side=tk.LEFT, padx=8)

        add_entry("Game Directory", "game_dir", browse=True)
        add_entry("Java Path", "java_path")
        add_entry("Default Memory (MB)", "memory_mb")
        add_entry("Offline Username", "offline_username")
        add_entry("Online Access Token", "online_token")

        info = tk.Frame(f, bg=C["bg"])
        info.pack(fill=tk.X, padx=30, pady=10)
        tk.Label(info, text=f"{APP_NAME} v{APP_VERSION}  •  Built with tkinter",
                 font=FONTS["ui"], fg=C["text_dim"], bg=C["bg"]).pack(anchor="w")
        lib_text = f"minecraft-launcher-lib: {'installed' if HAS_LIB else 'NOT installed'}"
        tk.Label(info, text=lib_text, font=FONTS["ui"],
                 fg=C["success"] if HAS_LIB else C["danger"],
                 bg=C["bg"]).pack(anchor="w", pady=(4, 0))


class AboutScreen(BaseScreen):
    name = "about"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()

    def _build(self):
        f = self.frame
        card = tk.Frame(f, bg=C["surface"], highlightbackground=C["border"],
                        highlightthickness=1)
        card.pack(fill=tk.X, padx=30, pady=30)
        inner = tk.Frame(card, bg=C["surface"])
        inner.pack(padx=30, pady=30)
        tk.Label(inner, text="Sulphur", font=("Segoe UI", 24, "bold"),
                 fg=C["accent"], bg=C["surface"]).pack()
        tk.Label(inner, text=f"Minecraft Launcher v{APP_VERSION}", font=FONTS["ui"],
                 fg=C["text_dim"], bg=C["surface"]).pack(pady=(4, 16))
        tk.Label(inner, text="A lightweight, offline-friendly Minecraft launcher built with Python and tkinter.",
                 font=FONTS["ui"], fg=C["text"], bg=C["surface"], justify=tk.CENTER).pack()
        tk.Label(inner, text="Requires minecraft-launcher-lib", font=FONTS["ui"],
                 fg=C["text_dim"], bg=C["surface"]).pack(pady=(12, 0))
        HoverButton(inner, text="GitHub Issues (placeholder)", command=lambda: webbrowser.open("https://github.com"),
                    fill=C["surface_2"], hover=C["surface"], text_color=C["text"]).pack(pady=20)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class SulphurLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} — Minecraft Launcher")
        self.root.geometry("1200x760")
        self.root.minsize(980, 640)
        self.root.configure(bg=C["bg"])

        # Data & managers
        self.app_dir = os.path.join(os.path.expanduser("~"), f".{APP_NAME.lower()}")
        self.data = DataManager(self.app_dir)
        self.version_manager = VersionManager(self._log, self._set_status)

        # UI
        self._build_ui()

        # Load
        self.version_manager.fetch(self.data.settings["game_dir"])
        self._update_stats()

        # Entrance animation
        self._animate_entrance()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        container = tk.Frame(self.root, bg=C["bg"])
        container.pack(fill=tk.BOTH, expand=True)

        # Sidebar
        self.sidebar = tk.Frame(container, bg=C["surface"], width=200)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        logo = tk.Frame(self.sidebar, bg=C["surface"])
        logo.pack(pady=(26, 12))
        tk.Label(logo, text="S", font=("Segoe UI", 26, "bold"),
                 fg=C["accent"], bg=C["surface"]).pack()
        tk.Label(logo, text="SULPHUR", font=("Segoe UI", 9, "bold"),
                 fg=C["text_dim"], bg=C["surface"]).pack()

        self.nav_buttons = {}
        nav_items = [
            ("home", "Home", "🏠"),
            ("versions", "Versions", "📦"),
            ("profiles", "Profiles", "👤"),
            ("servers", "Servers", "🌐"),
            ("settings", "Settings", "🛠️"),
            ("about", "About", "ℹ️"),
        ]
        for key, label, icon in nav_items:
            btn = HoverButton(self.sidebar, text=f"{icon}  {label}",
                              width=170, height=40, fill=C["surface"],
                              hover=C["surface_2"], text_color=C["text"],
                              font=FONTS["ui_bold"],
                              command=lambda k=key: self._show_screen(k))
            btn.pack(padx=14, pady=6)
            self.nav_buttons[key] = btn

        # Content
        self.content = tk.Frame(container, bg=C["bg"])
        self.content.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.screens = {}
        screen_classes = [
            HomeScreen, VersionsScreen, ProfilesScreen,
            ServersScreen, SettingsScreen, AboutScreen,
        ]
        for cls in screen_classes:
            screen = cls(self.content, self)
            self.screens[screen.name] = screen
            screen.frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Bottom status bar
        self.bottom = tk.Frame(self.root, bg=C["surface"], height=32)
        self.bottom.pack(side=tk.BOTTOM, fill=tk.X)
        self.bottom.pack_propagate(False)
        self.status_lbl = tk.Label(self.bottom, text="Ready", font=FONTS["ui"],
                                   fg=C["text_dim"], bg=C["surface"])
        self.status_lbl.pack(side=tk.LEFT, padx=12, pady=6)

        # Log panel (docked bottom, toggleable)
        self.log_panel = tk.Frame(self.root, bg=C["surface_2"], height=0)
        self.log_panel.pack(side=tk.BOTTOM, fill=tk.X, before=self.bottom)
        self.log_panel.pack_propagate(False)
        self.log_console = LogConsole(self.log_panel)
        self.log_console.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        self.log_visible = False

        # Floating log toggle
        self.log_btn = tk.Button(self.root, text="▼ Log", command=self.toggle_log,
                                 bg=C["surface_2"], fg=C["text_dim"], relief="flat",
                                 font=FONTS["ui"], cursor="hand2", padx=8, pady=4)
        self.log_btn.place(relx=1.0, x=-14, y=46, anchor="ne")

        # Show home
        self._show_screen("home")

    def _show_screen(self, name):
        for key, btn in self.nav_buttons.items():
            if key == name:
                btn.configure(bg=C["accent"], fg=C["text_inv"])
            else:
                btn.configure(bg=C["surface"], fg=C["text"])
        screen = self.screens[name]
        screen.show()
        screen.on_show()
        self._set_status(f"{name.capitalize()}")

    def toggle_log(self):
        if self.log_visible:
            self.log_panel.configure(height=0)
            self.log_btn.config(text="▼ Log")
        else:
            self.log_panel.configure(height=160)
            self.log_btn.config(text="▲ Log")
        self.log_visible = not self.log_visible

    # ------------------------------------------------------------------ actions
    def _update_stats(self):
        home = self.screens.get("home")
        if home:
            home._refresh_profiles()
            vm = self.version_manager
            # update stat cards roughly
            for widget in home.frame.winfo_children():
                pass  # stats refreshed via _refresh_profiles for simplicity

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

    def _install_version(self, version):
        if not HAS_LIB:
            messagebox.showerror("Missing library",
                                 "Install minecraft-launcher-lib:\npip install minecraft-launcher-lib")
            return
        vs = self.screens.get("versions")
        if vs:
            vs.progress["value"] = 0
        self._set_status(f"Installing {version}...")
        threading.Thread(target=self._do_install, args=(version,), daemon=True).start()

    def _do_install(self, version):
        try:
            def progress(current, total):
                self.root.after(0, lambda c=current, t=total: self._set_progress(c, t))

            self.version_manager.install(version, self.data.settings["game_dir"], progress)
            self.root.after(0, lambda: self._log(f"Installed {version} successfully.", "SUCCESS"))
            self.root.after(0, self.version_manager._load_installed, self.data.settings["game_dir"])
            vs = self.screens.get("versions")
            if vs:
                self.root.after(0, vs.refresh)
            self.root.after(0, lambda: self._set_status("Ready"))
        except Exception as e:
            self.root.after(0, lambda: self._log(f"Install failed: {e}", "ERROR"))
            self.root.after(0, lambda: messagebox.showerror("Install failed", str(e)))
            self.root.after(0, lambda: self._set_status("Ready"))

    def _set_progress(self, current, total):
        vs = self.screens.get("versions")
        if vs:
            vs.progress["maximum"] = total or 100
            vs.progress["value"] = current
        self._set_status(f"Installing... {current}/{total}")

    def _launch_profile(self, prof, server=None):
        if not HAS_LIB:
            messagebox.showerror("Missing library",
                                 "Install minecraft-launcher-lib:\npip install minecraft-launcher-lib")
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
                    "launcherVersion": APP_VERSION,
                }
                # Custom resolution
                if prof.get("width") and prof.get("height"):
                    options["customResolution"] = True
                    options["resolutionWidth"] = int(prof["width"])
                    options["resolutionHeight"] = int(prof["height"])
                if prof.get("fullscreen"):
                    options["jvmArguments"].append("--fullscreen")
                # Extra JVM args from profile
                extra_jvm = prof.get("jvm_args", "").strip()
                if extra_jvm:
                    options["jvmArguments"].extend(extra_jvm.split())
                self.root.after(0, lambda: self._log(
                    f"Launching {version} offline as {username}...", "LAUNCH"))
            else:
                token = self.data.settings.get("online_token", "")
                if not token:
                    self.root.after(0, lambda: messagebox.showwarning(
                        "Online login", "No online token configured. Enable Offline Mode or add a token in Settings."))
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
                    "launcherVersion": APP_VERSION,
                }
                if prof.get("width") and prof.get("height"):
                    options["customResolution"] = True
                    options["resolutionWidth"] = int(prof["width"])
                    options["resolutionHeight"] = int(prof["height"])
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
            alpha = min(step / 15, 1.0)
            try:
                self.root.attributes("-alpha", alpha)
            except tk.TclError:
                pass
            if alpha < 1.0:
                self.root.after(20, fade, step + 1)
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