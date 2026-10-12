# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 hmodymac8-droid
"""Build DownloadsSorterSetup.exe, a standard Windows setup wizard.

Needs:  py -m pip install pyinstaller pystray pillow sv-ttk cryptography
        Inno Setup 6 (https://jrsoftware.org/isinfo.php, or: winget install JRSoftware.InnoSetup)
Run make_icon.py first if icon.ico is missing.

    py build.py [work_folder]

Intermediate files go in work_folder (default: a temp folder), and the finished
installer is written next to this script.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import sort_downloads as core

HERE = Path(__file__).resolve().parent
work = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="downloads_sorter_build_"))


def find_iscc() -> str:
    """Locate the Inno Setup command-line compiler."""
    candidates = [shutil.which("ISCC")] + [
        str(Path(os.environ.get(variable, "")) / folder / "Inno Setup 6" / "ISCC.exe")
        for variable, folder in (("LOCALAPPDATA", "Programs"), ("ProgramFiles(x86)", ""), ("ProgramFiles", ""))
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    sys.exit("Inno Setup 6 was not found. Install it with:  winget install JRSoftware.InnoSetup")


# 1. The program itself, packaged as a folder with PyInstaller.
subprocess.run([
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
    "--name", "DownloadsSorter",
    "--icon", str(HERE / "icon.ico"), "--add-data", f"{HERE / 'icon.ico'};.",
    "--add-data", f"{HERE / 'icon.png'};.",  # the icon artwork, for large copies inside windows
    "--add-data", f"{HERE / 'fonts'};fonts",  # DM Sans and Manrope, with their licences
    "--collect-data", "sv_ttk",  # the theme's Tcl and image files
    "--hidden-import", "PIL.ImageTk", "--hidden-import", "PIL._tkinter_finder",  # for the colour tiles
    # pystray picks its Windows backend at run time, so PyInstaller must be told about it.
    "--hidden-import", "pystray._win32",
    "--paths", str(HERE), "--distpath", str(work / "dist"),
    "--workpath", str(work / "work"), "--specpath", str(work),
    str(HERE / "sort_gui.pyw"),
], check=True)

# 2. The setup wizard, compiled from installer.iss with Inno Setup.
subprocess.run([
    find_iscc(), f"/DAppVersion={core.VERSION}", f"/DDistDir={work / 'dist' / 'DownloadsSorter'}",
    f"/O{HERE}", *sys.argv[2:], str(HERE / "installer.iss"),
], check=True)
print("Built", HERE / "DownloadsSorterSetup.exe", "version", core.VERSION)
