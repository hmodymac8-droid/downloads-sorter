"""Build DownloadsSorterSetup.exe. Needs:  py -m pip install pyinstaller pystray pillow sv-ttk

Run make_icon.py first if icon.ico is missing.

    py build.py [work_folder]

Intermediate files go in work_folder (default: a temp folder), and the finished
installer is copied next to this script.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
work = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="downloads_sorter_build_"))


def pyinstaller(*args: str) -> None:
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--icon", str(HERE / "icon.ico"), "--add-data", f"{HERE / 'icon.ico'};.",
        "--collect-data", "sv_ttk",  # the theme's Tcl and image files
        "--hidden-import", "PIL.ImageTk", "--hidden-import", "PIL._tkinter_finder",  # for the colour tiles
        "--paths", str(HERE), "--distpath", str(work / "dist"),
        "--workpath", str(work / "work"), "--specpath", str(work), *args,
    ], check=True)


# 1. The program itself, as a folder (starts faster than a single-file exe).
#    pystray picks its Windows backend at run time, so PyInstaller must be told about it.
pyinstaller("--onedir", "--name", "DownloadsSorter", "--hidden-import", "pystray._win32", str(HERE / "sort_gui.pyw"))
# 2. The setup program, a single exe carrying that folder inside it.
pyinstaller("--onefile", "--name", "DownloadsSorterSetup",
            "--add-data", f"{work / 'dist' / 'DownloadsSorter'};app", str(HERE / "installer.py"))

shutil.copy2(work / "dist" / "DownloadsSorterSetup.exe", HERE / "DownloadsSorterSetup.exe")
print("Built", HERE / "DownloadsSorterSetup.exe")
