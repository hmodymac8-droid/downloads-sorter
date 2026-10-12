"""Setup program for Downloads Sorter. build.py packages this as DownloadsSorterSetup.exe.

Installs for the current user only (no administrator rights needed): copies the
program, adds shortcuts and an entry in Windows "Installed apps".
"""

import shutil
import subprocess
import sys
import time
import tkinter as tk
import winreg
from pathlib import Path
from tkinter import messagebox, ttk

import sort_downloads as core
import theme

# build.py bundles the packaged program folder under "app".
PAYLOAD = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "app"
VERSION = "1.0"


def create_shortcut(link: Path, target: Path) -> None:
    quote = lambda path: "'" + str(path).replace("'", "''") + "'"
    script = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut({quote(link)});"
              f"$s.TargetPath={quote(target)};$s.WorkingDirectory={quote(target.parent)};$s.Save()")
    core.run_quiet(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script])


def register_uninstaller(exe: Path) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, core.UNINSTALL_KEY) as key:
        for name, value in (
            ("DisplayName", core.APP_NAME), ("DisplayVersion", VERSION), ("DisplayIcon", str(exe)),
            ("InstallLocation", str(exe.parent)), ("UninstallString", f'"{exe}" --uninstall'),
        ):
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)


def install(target: Path, desktop: bool, automatic: bool, shortcuts: bool = True) -> Path:
    """Copy the program to target and hook it into Windows. Returns the installed exe."""
    # Stop a running background sorter (an older install or the script version)
    # so its files aren't locked and the new one takes over.
    core.stop_background()
    time.sleep(1)
    shutil.copytree(PAYLOAD, target, dirs_exist_ok=True)
    exe = target / core.EXE_NAME
    if shortcuts:
        create_shortcut(core.start_menu_shortcut(), exe)
        if desktop:
            create_shortcut(core.desktop_shortcut(), exe)
        register_uninstaller(exe)
        core.set_autostart(automatic, [str(exe), "--background"])
        if automatic:
            subprocess.Popen([str(exe), "--background"], cwd=target, stdin=subprocess.DEVNULL)
    return exe


class Setup(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{core.APP_NAME} Setup")
        self.resizable(False, False)
        theme.apply(self)
        # Keep automatic sorting however it is now; a fresh install starts with it off.
        self.automatic = tk.BooleanVar(value=core.autostart_enabled() or core.background_pid() is not None)
        self.desktop = tk.BooleanVar(value=True)
        self.open_after = tk.BooleanVar(value=True)

        body = ttk.Frame(self, padding=22)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=f"Install {core.APP_NAME}", font=("Segoe UI Semibold", 15)).pack(anchor="w")
        ttk.Label(body, wraplength=420, justify="left", text=(
            "Sorts old files in your Downloads folder into category folders. "
            "It installs for your user account only.")).pack(anchor="w", pady=(4, 10))
        ttk.Label(body, text=f"Location: {core.INSTALL_DIR}", foreground="gray", wraplength=420).pack(anchor="w")
        ttk.Checkbutton(body, text="Create a desktop shortcut", variable=self.desktop).pack(anchor="w", pady=(12, 0))
        ttk.Checkbutton(body, text="Sort automatically in the background (starts when you sign in)",
                        variable=self.automatic).pack(anchor="w")
        ttk.Checkbutton(body, text=f"Open {core.APP_NAME} when setup finishes", variable=self.open_after).pack(anchor="w")
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(16, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        self.install_button = ttk.Button(buttons, text="Install", style=theme.accent(), command=self.run)
        self.install_button.pack(side="right", padx=6)

    def run(self):
        self.install_button.config(state="disabled", text="Installing…")
        self.update()
        try:
            exe = install(core.INSTALL_DIR, self.desktop.get(), self.automatic.get())
        except OSError as error:
            self.install_button.config(state="normal", text="Install")
            messagebox.showerror("Setup", f"Could not install:\n{error}\n\n"
                                 f"If {core.APP_NAME} is open, close it and try again.", parent=self)
            return
        messagebox.showinfo("Setup", f"{core.APP_NAME} is installed.\n\nFind it in the Start menu.", parent=self)
        if self.open_after.get():
            subprocess.Popen([str(exe)], cwd=exe.parent, stdin=subprocess.DEVNULL)
        self.destroy()


if __name__ == "__main__":
    Setup().mainloop()
