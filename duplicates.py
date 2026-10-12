"""Find duplicate files: by content, by name, by name and size, by a similar
name (messy song/video titles), or by size.

This is the engine behind the Duplicates page in sort_gui.pyw. It never
touches the window, so a scan can run on a background thread.
"""

import hashlib
import os
import re
import shutil
import subprocess
import sys
import threading
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import sort_downloads as core

MODES = {
    "content": "Content (identical bytes)",
    "name": "Exact file name",
    "name_size": "Name + size",
    "name_similar": "Similar name (songs, videos)",
    "size": "Size only",
}
CHUNK_SIZE = 1024 * 1024
# In "similar name" mode a key that starts with another key at least this long
# joins that group, so "Title" and "Title Channel Handle" end up together.
MIN_PREFIX = 10


@dataclass
class Entry:
    path: Path
    size: int
    modified: float

    @property
    def name(self) -> str:
        return self.path.name


@dataclass
class Group:
    number: int
    files: list[Entry] = field(default_factory=list)


class Cancelled(Exception):
    pass


def norm_text(value: str) -> str:
    """Unicode-normalised, case-folded text for comparing Arabic and Latin names."""
    return unicodedata.normalize("NFKC", value).casefold()


# Resolution tags, even when glued to a word ("Video720p").
_RE_RESOLUTION = re.compile(r"\d{3,4}p", re.IGNORECASE)
_RE_QUALITY = re.compile(r"(?<![a-z0-9])(?:4k|8k|uhd|hd|h264|h265|x264|x265|hevc|av1|vp9)(?![a-z0-9])", re.IGNORECASE)
_RE_FEAT = re.compile(r"\b(?:feat\.?|ft\.?|featuring)\b", re.IGNORECASE)
_RE_PROD = re.compile(r"\b(?:prod\.?|produced\s+by)\b", re.IGNORECASE)
_RE_PROD_PAREN = re.compile(r"[\(\[]\s*(?:prod\.?|produced\s+by)\s*([^)\]]*)[\)\]]", re.IGNORECASE)
# Common video/music title clutter, longer phrases first.
_RE_JUNK_PHRASES = re.compile(
    r"\b(?:official\s+music\s+video|official\s+video|music\s+video|official\s+audio|lyric\s+video|"
    r"full\s+video|hd\s+video|official|lyrics?|audio|video|omv|mv|hd|uhd|youtube)\b", re.IGNORECASE)


def similar_name_key(name: str) -> str:
    """Canonical key for messy music/video file names.

    These all give the same key:
      MC TYSON Make It Rain feat eyden Watson Official Music Video720p.mp4
      MC TYSON " Make It Rain " feat. eyden & Watson (Official Music Video).mp4

    Spaces and punctuation don't count, so "Lil $o$o" matches "Lil oo" (a
    downloader that deletes symbols). Trailing words that repeat the leading
    words are dropped, so "Artist - Title - Artist" matches "Artist - Title".
    """
    s = norm_text(Path(name).stem)
    s = re.sub(r'["\'`´‘’“”«»]', " ", s)
    s = _RE_RESOLUTION.sub(" ", s)
    s = _RE_QUALITY.sub(" ", s)
    s = _RE_FEAT.sub(" feat ", s)
    s = _RE_PROD_PAREN.sub(r" prod \1 ", s)  # keep producer credits that only appear in (Prod. …)
    s = _RE_PROD.sub(" prod ", s)
    s = re.sub(r"\s*[&+]\s*|,\s*", " ", s)
    # Text in brackets stays: it is often the real title or a translation.
    # The rules above already removed metadata like (Official MV) or [1080p].
    s = _RE_JUNK_PHRASES.sub(" ", s)
    s = re.sub(r"[^\w\s]|_", " ", s)  # underscore is a separator in file names, not a letter
    tokens = re.sub(r"\s+", " ", s).strip().split(" ")
    for k in range(len(tokens) // 2, 0, -1):
        if tokens[:k] == tokens[-k:]:
            tokens = tokens[:-k]
            break
    return "".join(tokens)


def file_hash(path: Path, cancel: threading.Event) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        while chunk := file.read(CHUNK_SIZE):
            if cancel.is_set():
                raise Cancelled
            digest.update(chunk)
    return digest.hexdigest()


def sorted_folders(config: dict) -> list[Path]:
    """The folders this program sorts, and their category folders."""
    folders = []
    for root in core.watched_folders(config):
        folders.append(root)
        folders += [root / category["folder"] for category in config["categories"]]
        if config["other_folder"]:
            folders.append(root / config["other_folder"])
    return folders


def collect(folders: list[Path], recursive: bool, cancel: threading.Event) -> list[Entry]:
    """Every file in the folders, each once even when folders overlap."""
    found = {}
    for folder in folders:
        if recursive:
            walk = ((Path(top), names) for top, _, names in os.walk(folder))
        else:
            try:
                walk = [(folder, [item.name for item in os.scandir(folder) if item.is_file(follow_symlinks=False)])]
            except OSError:
                continue
        for top, names in walk:
            if cancel.is_set():
                raise Cancelled
            for name in names:
                path = top / name
                if core.is_skipped(path) or core.norm(path) in found:
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                found[core.norm(path)] = Entry(path, stat.st_size, stat.st_mtime)
    return list(found.values())


def find(files: list[Entry], mode: str, cancel: threading.Event, progress=lambda text: None) -> list[Group]:
    """Group the files by mode. Within each group the file to keep comes first:
    the shortest name, so "report.pdf" rather than "report (1).pdf"."""
    buckets = defaultdict(list)
    if mode in ("content", "size"):
        files = [entry for entry in files if entry.size]  # empty files all look alike
    if mode == "content":
        by_size = defaultdict(list)
        for entry in files:
            by_size[entry.size].append(entry)
        candidates = [entry for same in by_size.values() if len(same) > 1 for entry in same]
        # A unique size can't have a twin, so only same-size files are hashed.
        for done, entry in enumerate(candidates, 1):
            progress(f"Comparing contents… {done} of {len(candidates)} ({100 * done // len(candidates)}%)")
            try:
                buckets[(entry.size, file_hash(entry.path, cancel))].append(entry)
            except OSError:
                continue
    elif mode == "name":
        for entry in files:
            buckets[norm_text(entry.name)].append(entry)
    elif mode == "name_size":
        for entry in files:
            buckets[(norm_text(entry.name), entry.size)].append(entry)
    elif mode == "size":
        for entry in files:
            buckets[entry.size].append(entry)
    elif mode == "name_similar":
        for entry in files:
            if key := similar_name_key(entry.name):
                buckets[key].append(entry)
        # Cleaned-up copies often lose or gain a tail (channel names, translated
        # subtitles), so a key that extends a shorter one joins its group.
        root = None
        for key in sorted(buckets):
            if root and len(root) >= MIN_PREFIX and key.startswith(root):
                buckets[root] += buckets.pop(key)
            else:
                root = key
    else:
        raise ValueError(f"unknown mode {mode!r}")

    groups = [sorted(same, key=lambda e: (len(e.name), norm_text(str(e.path))))
              for same in buckets.values() if len(same) > 1]
    if mode == "size":
        groups.sort(key=lambda g: (-g[0].size, -len(g), norm_text(g[0].name)))
    else:
        groups.sort(key=lambda g: (-len(g), norm_text(g[0].name)))
    return [Group(number, files) for number, files in enumerate(groups, 1)]


def reveal(path: Path) -> str | None:
    """Show a file selected in the system file manager. None = done, else what went wrong."""
    if not path.is_file():
        return f"This file is not there any more:\n{path}"
    try:
        if sys.platform == "win32":
            subprocess.Popen(f'explorer /select,"{path}"')
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", str(path)], check=False)
        else:
            # The freedesktop call selects the file in most Linux file managers.
            if shutil.which("dbus-send") and subprocess.run(
                    ["dbus-send", "--session", "--print-reply", "--dest=org.freedesktop.FileManager1",
                     "/org/freedesktop/FileManager1", "org.freedesktop.FileManager1.ShowItems",
                     f"array:string:{path.resolve().as_uri()}", "string:"],
                    capture_output=True, timeout=10).returncode == 0:
                return None
            for manager in ("nautilus", "nemo", "dolphin"):
                if shutil.which(manager):
                    subprocess.Popen([manager, "--select", str(path)])
                    return None
            if not shutil.which("xdg-open"):
                return "No file manager was found (install xdg-utils)."
            subprocess.Popen(["xdg-open", str(path.parent)])  # last resort: just its folder
    except (OSError, subprocess.TimeoutExpired) as error:
        return str(error)
    return None


def open_file(path: Path) -> str | None:
    """Open a file with its default program. None = done, else what went wrong."""
    if not path.is_file():
        return f"This file is not there any more:\n{path}"
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", str(path)])
        else:
            return "xdg-open was not found (install xdg-utils)."
    except OSError as error:
        return str(error)
    return None
