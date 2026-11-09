"""
Sulphur - A basic Minecraft launcher with offline support.

Requires:
    pip install minecraft-launcher-lib

Offline mode lets you play without logging into Mojang/Microsoft.
"""

import os
import sys
import json
import uuid
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ---------------------------------------------------------------------------
# Optional dependency: minecraft-launcher-lib
# ---------------------------------------------------------------------------
try:
    import minecraft_launcher_lib
    from minecraft_launcher_lib import utils, install, command
    HAS_LIB = True
except Exception:  # pragma: no cover - library not installed
    HAS_LIB = False

# Fallback versions shown when the manifest can't be fetched (offline).
OFFLINE_VERSIONS = [
    "1.20.1", "1.20", "1.19.4", "1.19.2", "1.18.2", "1.17.1",
    "1.16.5", "1.15.2", "1.14.4", "1.12.2",
]

DEFAULT_MEMORY_MB = 2048
APP_NAME = "Sulphur"


class SulphurLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} - Minecraft Launcher")
        self.root.geometry("700x520")
        self.root.minsize(600, 450)

        # State
        self.minecraft_dir = os.path.join(os.getcwd(), ".minecraft")
        self.java_path = self._detect_java()
        self.memory_mb = tk.IntVar(value=DEFAULT_MEMORY_MB)
        self.offline_mode = tk.BooleanVar(value=True)
        self.username_var = tk.StringVar(value="Player")
        self.version_var = tk.StringVar()
        self.versions = []          # list of version ids
        self.installed_versions = set()
        self.installing = False

        self._build_ui()
        self._load_installed_versions()
        self._refresh_version_list()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        # Top bar: directory + java
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Game folder:").pack(side=tk.LEFT)
        self.dir_entry = ttk.Entry(top, width=40)
        self.dir_entry.insert(0, self.minecraft_dir)
        self.dir_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(top, text="Browse", command=self._browse_dir).pack(side=tk.LEFT, padx=2)

        java_row = ttk.Frame(self.root, padding=(10, 0))
        java_row.pack(fill=tk.X)
        ttk.Label(java_row, text="Java path:").pack(side=tk.LEFT)
        self.java_entry = ttk.Entry(java_row, width=40)
        self.java_entry.insert(0, self.java_path or "")
        self.java_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(java_row, text="Browse", command=self._browse_java).pack(side=tk.LEFT, padx=2)

        # Login / offline section
        login = ttk.LabelFrame(self.root, text="Account", padding=10)
        login.pack(fill=tk.X, padx=10, pady=8)

        ttk.Checkbutton(
            login, text="Play offline (no login)",
            variable=self.offline_mode, command=self._toggle_offline
        ).pack(side=tk.LEFT)

        ttk.Label(login, text="Username:").pack(side=tk.LEFT, padx=(20, 5))
        self.user_entry = ttk.Entry(login, textvariable=self.username_var, width=20)
        self.user_entry.pack(side=tk.LEFT)

        # Version + memory
        mid = ttk.Frame(self.root, padding=10)
        mid.pack(fill=tk.X)

        ttk.Label(mid, text="Version:").pack(side=tk.LEFT)
        self.version_combo = ttk.Combobox(
            mid, textvariable=self.version_var, width=25, state="readonly"
        )
        self.version_combo.pack(side=tk.LEFT, padx=5)
        ttk.Button(mid, text="Refresh", command=self._refresh_version_list).pack(side=tk.LEFT, padx=2)

        ttk.Label(mid, text="Memory (MB):").pack(side=tk.LEFT, padx=(20, 5))
        ttk.Spinbox(mid, from_=512, to=16384, increment=256,
                    textvariable=self.memory_mb, width=8).pack(side=tk.LEFT)

        # Action buttons
        btns = ttk.Frame(self.root, padding=10)
        btns.pack(fill=tk.X)
        self.install_btn = ttk.Button(btns, text="Install Version", command=self._install_version)
        self.install_btn.pack(side=tk.LEFT, padx=4)
        self.launch_btn = ttk.Button(btns, text="Launch Minecraft", command=self._launch)
        self.launch_btn.pack(side=tk.LEFT, padx=4)

        # Progress bar
        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill=tk.X, padx=10, pady=(0, 5))

        # Log
        log_frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        log_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(log_frame, text="Log:").pack(anchor=tk.W)
        self.log = tk.Text(log_frame, height=10, wrap=tk.WORD, state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True)

        # Status bar
        self.status = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status, relief=tk.SUNKEN,
                  anchor=tk.W, padding=(10, 2)).pack(fill=tk.X, side=tk.BOTTOM)

        if not HAS_LIB:
            self._log("minecraft-launcher-lib is not installed.")
            self._log("Install it with:  pip install minecraft-launcher-lib")
            self.status.set("Library missing - install minecraft-launcher-lib")

    # ------------------------------------------------------------- helpers
    def _log(self, msg):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _set_status(self, msg):
        self.status.set(msg)
        self.root.after(0, lambda: None)

    def _detect_java(self):
        for name in ("java", "javaw.exe"):
            if subprocess.run(["where", name], capture_output=True,
                              text=True, shell=True).stdout.strip():
                return name
        return "java"

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.minecraft_dir)
        if d:
            self.minecraft_dir = d
            self.dir_entry.delete(0, tk.END)
            self.dir_entry.insert(0, d)
            self._load_installed_versions()
            self._refresh_version_list()

    def _browse_java(self):
        f = filedialog.askopenfilename(title="Select Java executable",
                                       filetypes=[("Java", "java*"), ("All", "*")])
        if f:
            self.java_path = f
            self.java_entry.delete(0, tk.END)
            self.java_entry.insert(0, f)

    def _toggle_offline(self):
        state = "disabled" if self.offline_mode.get() else "normal"
        self.user_entry.configure(state=state)
        self._log("Offline mode: " + ("ON" if self.offline_mode.get() else "OFF"))

    # ------------------------------------------------- versions
    def _load_installed_versions(self):
        self.installed_versions = set()
        versions_dir = os.path.join(self.minecraft_dir, "versions")
        if os.path.isdir(versions_dir):
            for name in os.listdir(versions_dir):
                if os.path.isdir(os.path.join(versions_dir, name)):
                    self.installed_versions.add(name)

    def _refresh_version_list(self):
        self._log("Fetching version list...")
        threading.Thread(target=self._fetch_versions, daemon=True).start()

    def _fetch_versions(self):
        try:
            if HAS_LIB:
                manifest = utils.get_version_manifest()
                self.versions = [v["id"] for v in manifest["versions"]]
            else:
                raise RuntimeError("library missing")
        except Exception as e:
            self._log(f"Could not fetch online versions ({e}). Using offline fallback.")
            self.versions = list(OFFLINE_VERSIONS)

        # Mark installed ones visually
        self.root.after(0, self._populate_version_combo)

    def _populate_version_combo(self):
        # Show installed versions first, then the rest
        installed = sorted(v for v in self.versions if v in self.installed_versions)
        not_installed = sorted(v for v in self.versions if v not in self.installed_versions)
        display = installed + ["---"] + not_installed
        self.version_combo["values"] = display
        if display:
            self.version_combo.current(0)
        self._set_status(f"{len(self.versions)} versions available")

    # ------------------------------------------------- install / launch
    def _install_version(self):
        if not HAS_LIB:
            messagebox.showerror("Missing library",
                                 "Install minecraft-launcher-lib: pip install minecraft-launcher-lib")
            return
        version = self.version_var.get()
        if not version or version == "---":
            messagebox.showwarning("No version", "Please select a version.")
            return
        if version in self.installed_versions:
            if not messagebox.askyesno("Already installed",
                                       f"{version} is already installed. Reinstall?"):
                return
        self.installing = True
        self.install_btn.configure(state=tk.DISABLED)
        self.launch_btn.configure(state=tk.DISABLED)
        self.progress["value"] = 0
        threading.Thread(target=self._do_install, args=(version,), daemon=True).start()

    def _do_install(self, version):
        try:
            def callback(status, current, total):
                self.root.after(0, lambda: self.progress.configure(
                    maximum=total or 100, value=current))
                self.root.after(0, lambda: self._set_status(f"{status} ({current}/{total})"))

            self.root.after(0, lambda: self._log(f"Installing {version}..."))
            install.install_minecraft_version(version, self.minecraft_dir, callback=callback)
            self.root.after(0, lambda: self._log(f"Installed {version} successfully."))
            self.root.after(0, self._load_installed_versions)
            self.root.after(0, self._refresh_version_list)
            self.root.after(0, lambda: self._set_status("Ready"))
        except Exception as e:
            self.root.after(0, lambda: self._log(f"Install failed: {e}"))
            self.root.after(0, lambda: messagebox.showerror("Install failed", str(e)))
        finally:
            self.root.after(0, lambda: self.install_btn.configure(state=tk.NORMAL))
            self.root.after(0, lambda: self.launch_btn.configure(state=tk.NORMAL))
            self.installing = False

    def _launch(self):
        if not HAS_LIB:
            messagebox.showerror("Missing library",
                                 "Install minecraft-launcher-lib: pip install minecraft-launcher-lib")
            return
        version = self.version_var.get()
        if not version or version == "---":
            messagebox.showwarning("No version", "Please select a version.")
            return
        if version not in self.installed_versions:
            if not messagebox.askyesno("Not installed",
                                       f"{version} is not installed. Install and launch?"):
                return
            self._install_version()
            return

        self.launch_btn.configure(state=tk.DISABLED)
        threading.Thread(target=self._do_launch, args=(version,), daemon=True).start()

    def _do_launch(self, version):
        try:
            username = self.username_var.get().strip() or "Player"
            if self.offline_mode.get():
                # Offline credentials: no Mojang/Microsoft login required.
                # Generate a deterministic offline UUID from the username.
                off_uuid = str(uuid.uuid3(uuid.NAMESPACE_URL, "Offline:" + username))
                options = {
                    "username": username,
                    "uuid": off_uuid,
                    "token": "",
                    "executablePath": self.java_entry.get().strip() or self.java_path or "java",
                    "jvmArguments": [
                        f"-Xmx{self.memory_mb.get()}M",
                        f"-Xms{max(self.memory_mb.get() // 2, 256)}M",
                    ],
                    "launcherName": APP_NAME,
                    "launcherVersion": "1.0",
                }
                self.root.after(0, lambda: self._log(f"Launching {version} offline as {username}..."))
            else:
                # Online mode requires valid auth (not implemented in this basic build).
                messagebox.showwarning(
                    "Online login not configured",
                    "Online authentication isn't wired up in this basic build. "
                    "Enable 'Play offline' to launch without logging in."
                )
                self.root.after(0, lambda: self.launch_btn.configure(state=tk.NORMAL))
                return

            mc_cmd = command.get_minecraft_command(version, self.minecraft_dir, options)
            self.root.after(0, lambda: self._log("Launch command built."))
            self.root.after(0, lambda: self._set_status("Launching..."))
            subprocess.Popen(mc_cmd, cwd=self.minecraft_dir)
            self.root.after(0, lambda: self._log("Minecraft launched."))
            self.root.after(0, lambda: self._set_status("Minecraft running"))
        except Exception as e:
            self.root.after(0, lambda: self._log(f"Launch failed: {e}"))
            self.root.after(0, lambda: messagebox.showerror("Launch failed", str(e)))
        finally:
            self.root.after(0, lambda: self.launch_btn.configure(state=tk.NORMAL))


def main():
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.2)  # slightly sharper on high-DPI
    except Exception:
        pass
    app = SulphurLauncher(root)
    root.mainloop()


if __name__ == "__main__":
    main()