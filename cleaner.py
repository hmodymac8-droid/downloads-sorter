"""Find junk files that are safe to remove: temporary files, browser caches,
crash reports, Windows Update downloads and the like.

This is the engine behind the Cleaner page in sort_gui.pyw. It never touches
the window, so a scan can run on a background thread. Deleting goes through
sort_downloads.delete_files, so every removed file is logged in History.
"""

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

# Files changed more recently than this are left alone: a program may still be using them.
MIN_AGE_HOURS = 24
# Never descend into these, wherever they turn up (this program's own data).
SKIP_DIRS = {"downloadssorter"}


def _env(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None


def _browser_caches() -> list[Path]:
    """Cache folders of Chromium browsers (every profile) and Firefox."""
    local = _env("LOCALAPPDATA")
    if not local:
        return []
    folders = []
    for user_data in ("Google/Chrome/User Data", "Microsoft/Edge/User Data", "BraveSoftware/Brave-Browser/User Data",
                      "Vivaldi/User Data", "Opera Software/Opera Stable"):
        root = local / user_data
        if not root.is_dir():
            continue
        profiles = [root] + [p for p in root.iterdir() if p.is_dir()]
        for profile in profiles:
            for cache in ("Cache", "Code Cache", "GPUCache", "Service Worker/CacheStorage"):
                if (profile / cache).is_dir():
                    folders.append(profile / cache)
    firefox = local / "Mozilla/Firefox/Profiles"
    if firefox.is_dir():
        folders += [p / "cache2" for p in firefox.iterdir() if (p / "cache2").is_dir()]
    return folders


@dataclass
class Category:
    key: str
    label: str
    description: str
    folders: callable  # () -> list[Path]
    checked: bool = True  # ticked the first time the page is shown


CATEGORIES = [
    Category("user_temp", "Your temporary files", "Left behind by installers and programs (%TEMP%)",
             lambda: [p for p in (_env("TEMP"),) if p]),
    Category("windows_temp", "Windows temporary files", r"C:\Windows\Temp (some files need administrator rights)",
             lambda: [p / "Temp" for p in (_env("SystemRoot"),) if p]),
    Category("browser_cache", "Browser caches", "Chrome, Edge, Brave, Vivaldi, Opera and Firefox. "
             "Close the browsers first; sign-ins and history are kept", _browser_caches),
    Category("crash_reports", "Crash reports and dumps", "Windows Error Reporting files and program crash dumps",
             lambda: [p for p in (
                 _env("LOCALAPPDATA") and _env("LOCALAPPDATA") / "CrashDumps",
                 _env("LOCALAPPDATA") and _env("LOCALAPPDATA") / "Microsoft/Windows/WER",
                 _env("ProgramData") and _env("ProgramData") / "Microsoft/Windows/WER") if p]),
    Category("thumbnails", "Thumbnail cache", "Explorer rebuilds it as needed (files in use are skipped)",
             lambda: [p for p in (_env("LOCALAPPDATA") and _env("LOCALAPPDATA") / "Microsoft/Windows/Explorer",)
                      if p]),
    Category("update_cache", "Windows Update downloads", "Already-installed update files (needs administrator rights)",
             lambda: [p / "SoftwareDistribution/Download" for p in (_env("SystemRoot"),) if p], checked=False),
]
BY_KEY = {category.key: category for category in CATEGORIES}


class Cancelled(Exception):
    pass


@dataclass
class Found:
    category: Category
    files: list[Path] = field(default_factory=list)
    size: int = 0
    folders: list[Path] = field(default_factory=list)


def _wanted(category: Category, path: Path) -> bool:
    if category.key == "thumbnails":
        return path.name.lower().startswith(("thumbcache_", "iconcache_"))
    return True


def scan(keys: list[str], cancel: threading.Event, progress=lambda text: None) -> list[Found]:
    """Collect the junk files of the chosen categories. Nothing is deleted here."""
    cutoff = time.time() - MIN_AGE_HOURS * 3600
    results, seen = [], set()
    for key in keys:
        category = BY_KEY[key]
        found = Found(category)
        for root in category.folders():
            if not root.is_dir():
                continue
            found.folders.append(root)
            progress(f"Scanning: {category.label}…")
            for folder, dirs, files in os.walk(root, onerror=lambda error: None):
                if cancel.is_set():
                    raise Cancelled
                dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS
                           and not os.path.islink(os.path.join(folder, d))]
                for name in files:
                    path = Path(folder, name)
                    key_path = str(path).lower()
                    if key_path in seen or not _wanted(category, path):
                        continue
                    try:
                        stat = path.stat()
                    except OSError:
                        continue
                    if stat.st_mtime > cutoff:
                        continue
                    seen.add(key_path)
                    found.files.append(path)
                    found.size += stat.st_size
        results.append(found)
    return results


def remove_empty_folders(roots: list[Path]) -> None:
    """Remove folders the clean-up emptied, below (never including) each root."""
    for root in roots:
        for folder, dirs, files in os.walk(root, topdown=False, onerror=lambda error: None):
            if Path(folder) != root and not os.path.islink(folder):
                try:
                    os.rmdir(folder)  # only succeeds when it is empty
                except OSError:
                    pass
