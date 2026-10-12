"""Sort old files in the Downloads folder into category folders.

This is the engine; sort_gui.pyw is the program people run. It works both as
plain scripts and as the packaged DownloadsSorter.exe (see build.py).
"""

import fnmatch
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

APP_NAME = "Downloads Sorter"
FROZEN = getattr(sys, "frozen", False)  # True inside the packaged .exe
APP_DIR = Path(sys.executable if FROZEN else __file__).resolve().parent
# Settings live outside the program folder so reinstalling keeps them.
DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "DownloadsSorter"
CONFIG_FILE = DATA_DIR / "config.json"
HISTORY_FILE = DATA_DIR / "history.json"
LOG_FILE = DATA_DIR / "sort_downloads.log"
PID_FILE = DATA_DIR / "background.pid"
REPORT_PID_FILE = DATA_DIR / "report.pid"

DEFAULT_CONFIG = {
    "folders": [""],  # folders to sort; "" = the Downloads folder, detected automatically
    "min_age_days": 7,
    "scan_interval_minutes": 60,  # 0 = automatic sorting disabled
    # "folder" is relative to the sorted folder unless it is an absolute path.
    # "min_age_days": None uses the general setting above.
    # "recycle_after_days": files this program put there go to the Recycle Bin that
    # many days after it moved them; 0 = never.
    "categories": [
        {"folder": "Documents", "extensions": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv"]},
        {"folder": "Pictures", "extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".heic", ".tif", ".tiff", ".ico"]},
        {"folder": "Installers Archive", "extensions": [".exe", ".msi", ".msix", ".appx"], "recycle_after_days": 90},
        {"folder": "Archives", "extensions": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"]},
        {"folder": "Videos", "extensions": [".mp4", ".mkv", ".mov", ".avi", ".wmv", ".webm", ".m4v", ".flv"]},
        {"folder": "Audio", "extensions": [".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma", ".opus"]},
    ],
    "other_folder": "Other",  # where every other file type goes; "" = leave them
    "ignore": [],  # file names or patterns (*.torrent) that are never moved
    "paused_until": "",  # "YYYY-MM-DD HH:MM"; automatic runs wait until then
    "after_run": "window",  # "window" = report window, "notify" = tray notification only
}
# Partial downloads, shortcuts and system files that must never be moved.
SKIP_EXTENSIONS = {".crdownload", ".part", ".partial", ".download", ".opdownload", ".tmp", ".lnk", ".url"}
SKIP_NAMES = {"desktop.ini", "thumbs.db"}
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

log = logging.getLogger("sort_downloads")


def norm(path) -> str:
    return os.path.normcase(str(path))


# --- settings ---

def load_config() -> dict:
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    if "downloads_folder" in saved:  # setting from before several folders were supported
        saved.setdefault("folders", [saved.pop("downloads_folder")])
    config.update(saved)
    config["folders"] = config["folders"] or [""]
    for category in config["categories"]:
        category.setdefault("min_age_days", None)
        category.setdefault("recycle_after_days", 0)
    return config


def save_config(config: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def shell_folder(value_name: str, fallback: Path) -> Path:
    """Look up a per-user Windows folder, honouring a relocated one."""
    if sys.platform == "win32":
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
                return Path(winreg.ExpandEnvironmentStrings(value))
        except OSError:
            pass
    return fallback


def detect_downloads_folder() -> Path:
    return shell_folder("{374DE290-123F-4565-9164-39C4925E467B}", Path.home() / "Downloads")


def watched_folders(config: dict) -> list[Path]:
    return [Path(folder) if folder else detect_downloads_folder() for folder in config["folders"]]


def is_paused(config: dict) -> bool:
    return config["paused_until"] > time.strftime("%Y-%m-%d %H:%M")


def pause_until_tomorrow() -> str:
    """Timestamp for the coming midnight, for the "pause for today" setting."""
    tomorrow = time.localtime(time.time() + 86400)
    return time.strftime("%Y-%m-%d 00:00", tomorrow)


# --- planning and moving ---

def age_in_days(stat: os.stat_result) -> float:
    """Days since the file arrived in the folder.

    The newer of created/modified is used: files extracted from archives keep
    an old modified time, and copied files keep one too, so modified time alone
    would make brand-new files look ancient.
    """
    return (time.time() - max(stat.st_mtime, stat.st_ctime)) / 86400


def unique_destination(folder: Path, name: str) -> Path:
    """Return a path in folder that doesn't exist yet: name.ext, name (1).ext, ..."""
    candidate = folder / name
    stem, suffix = Path(name).stem, Path(name).suffix
    counter = 1
    while candidate.exists():
        candidate = folder / f"{stem} ({counter}){suffix}"
        counter += 1
    return candidate


def is_skipped(item: Path) -> bool:
    return item.name.startswith(".") or item.suffix.lower() in SKIP_EXTENSIONS or item.name.lower() in SKIP_NAMES


def is_ignored(name: str, config: dict) -> bool:
    return any(fnmatch.fnmatch(name.lower(), pattern.lower()) for pattern in config["ignore"])


def plan_moves(config: dict, everything: bool = False) -> list[dict]:
    """List the files that are due to move, without touching anything.

    everything=True is the manual "sort all now": it ignores file age and also
    takes files the user had put back with Undo.
    """
    # A file the user put back with Undo stays put, or the next run would just move it again.
    undone = set() if everything else {
        norm(move[0]) for run in load_history() for move in run["moves"] if move[2:] == ["undone"]}
    moves = []
    for root in watched_folders(config):
        rules = {
            ext.lower(): (root / category["folder"], category["min_age_days"])
            for category in config["categories"] for ext in category["extensions"]
        }
        other = (root / config["other_folder"], None) if config["other_folder"] else None
        try:
            items = sorted(root.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            continue  # folder missing or unreadable
        for item in items:
            try:
                if not item.is_file() or is_skipped(item) or is_ignored(item.name, config) or norm(item) in undone:
                    continue
                rule = rules.get(item.suffix.lower(), other)
                if not rule:
                    continue
                folder, category_age = rule
                stat = item.stat()
                age = age_in_days(stat)
                min_age = 0 if everything else config["min_age_days"] if category_age is None else category_age
                if age < min_age:
                    continue
                moves.append({"source": item, "folder": folder, "age": age, "size": stat.st_size, "root": root})
            except OSError:
                continue  # vanished or unreadable mid-scan
    return moves


def move_files(moves: list[dict], review: bool = False) -> tuple[int, list[str]]:
    """Carry out planned moves and log them. review=True marks the run as
    waiting for the user's Approve/Undo in the report window."""
    done, errors = [], []
    for move in moves:
        try:
            move["folder"].mkdir(parents=True, exist_ok=True)
            destination = unique_destination(move["folder"], move["source"].name)
            shutil.move(str(move["source"]), str(destination))
            done.append([str(move["source"]), str(destination)])
            log.info("Moved %s -> %s", move["source"].name, destination)
        except OSError as error:
            # File in use, permission denied, vanished: it stays for the next pass.
            errors.append(f"{move['source'].name}: {error}")
            log.warning("Skipped %s: %s", move["source"].name, error)
    if done:
        add_run(done, review=review)
    return len(done), errors


# --- history ---
# A run is {"time", "moves", "review"}. A move is [source, destination], plus a
# third item once it changes state:
#   "undone"   - moved back to source
#   "deleted"  - the file (at destination, or at source if destination is "")
#                was sent to the Recycle Bin
#   "restored" - a deleted file that was never moved was brought back to source
# Nothing is ever removed from the log.

def load_history() -> list[dict]:
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save_history(history: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, indent=1, ensure_ascii=False), encoding="utf-8")


def add_run(moves: list[list], review: bool = False) -> None:
    history = load_history()
    history.append({"time": time.strftime(TIME_FORMAT), "moves": moves, "review": review})
    save_history(history)


def is_active(move: list) -> bool:
    """True while the file is still where the program moved it."""
    return len(move) == 2


def can_undo(move: list) -> bool:
    return is_active(move) or move[2] == "deleted"


def current_path(move: list) -> Path | None:
    """Where the move's file is now, or None if it is in the Recycle Bin."""
    if is_active(move):
        return Path(move[1])
    return None if move[2] == "deleted" else Path(move[0])


def last_active_run() -> dict | None:
    """The most recent run that still has moves which can be undone."""
    return next((run for run in reversed(load_history()) if any(map(is_active, run["moves"]))), None)


def undo_moves(selection: list[tuple[str, int]]) -> tuple[int, list[str]]:
    """Reverse chosen changes. Each selection item is (run time, index in that run).

    A moved file goes back where it came from; a deleted file comes back out of
    the Recycle Bin to where it was when it was deleted.
    """
    history = load_history()
    runs = {run["time"]: run for run in history}
    restored, errors, folders = 0, [], set()
    for run_time, index in selection:
        move = runs[run_time]["moves"][index] if run_time in runs else None
        if not move or not can_undo(move):
            continue
        source, destination = Path(move[0]), Path(move[1])
        try:
            if is_active(move):
                source.parent.mkdir(parents=True, exist_ok=True)
                # Record where it actually landed in case the old name was taken.
                move[0] = str(unique_destination(source.parent, source.name))
                shutil.move(str(destination), move[0])
                move.append("undone")
                folders.add(destination.parent)
            elif move[1]:  # deleted after being moved: back to where it was moved to
                restore_from_recycle_bin(destination)
                del move[2]
            else:  # deleted where it lay
                restore_from_recycle_bin(source)
                move[2] = "restored"
            restored += 1
            log.info("Restored %s", source.name)
        except OSError as error:
            errors.append(f"{source.name}: {error}")
    for folder in folders:
        try:
            folder.rmdir()  # only succeeds if undoing left it empty
        except OSError:
            pass
    save_history(history)
    return restored, errors


def undo_last(run_time: str | None = None) -> tuple[int, list[str]]:
    """Undo every remaining move of one run: the given one, or the latest."""
    run = next((r for r in load_history() if r["time"] == run_time), None) if run_time else last_active_run()
    if not run:
        return 0, []
    return undo_moves([(run["time"], i) for i, move in enumerate(run["moves"]) if is_active(move)])


def pending_moves() -> list[tuple[str, int, list]]:
    """Moves from automatic runs the user has not approved yet: (run time, index, move)."""
    return [(run["time"], index, move) for run in load_history() if run.get("review")
            for index, move in enumerate(run["moves"]) if is_active(move)]


def approve_pending() -> None:
    history = load_history()
    for run in history:
        run["review"] = False
    save_history(history)


# --- deleting (always via the Recycle Bin, so it can be brought back) ---

def recycle(path: Path) -> None:
    """Send a file to the Recycle Bin (recoverable), not a permanent delete."""
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", ctypes.c_void_p),
            ("pTo", ctypes.c_void_p), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_void_p),
        ]

    source = ctypes.create_unicode_buffer(str(path) + "\0")  # list must end with two nulls
    FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 3, 0x4, 0x10, 0x40, 0x400
    operation = SHFILEOPSTRUCTW(
        None, FO_DELETE, ctypes.addressof(source), None,
        FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI, False, None, None)
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result or path.exists():
        raise OSError(f"Windows could not move it to the Recycle Bin (code {result})")


def restore_from_recycle_bin(original: Path) -> None:
    """Bring back the most recently recycled file that used to be at `original`.

    The bin keeps each file as a pair: $R<id> holds the content and $I<id>
    records the original path and deletion time.
    """
    if original.exists():
        raise OSError("a file with that name is already there")
    newest = None
    try:
        user_bins = list((Path(original.anchor) / "$Recycle.Bin").iterdir())
    except OSError:
        user_bins = []
    for user_bin in user_bins:
        try:
            records = list(user_bin.glob("$I*"))
        except OSError:
            continue  # another user's bin
        for record in records:
            try:
                data = record.read_bytes()
            except OSError:
                continue
            if len(data) < 28:
                continue
            deleted_at = int.from_bytes(data[16:24], "little")
            if int.from_bytes(data[:8], "little") == 2:  # Windows 10+: length-prefixed path
                name = data[28:28 + int.from_bytes(data[24:28], "little") * 2]
            else:
                name = data[24:]
            name = name.decode("utf-16-le", "replace").split("\0")[0]
            if norm(name) == norm(original) and (newest is None or deleted_at > newest[0]):
                newest = (deleted_at, record)
    if not newest:
        raise OSError("it is no longer in the Recycle Bin")
    record = newest[1]
    original.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(record.with_name("$R" + record.name[2:])), str(original))
    record.unlink(missing_ok=True)


def delete_files(paths: list[Path]) -> tuple[int, list[str]]:
    """Recycle files and log each one so it can be brought back from History."""
    history = load_history()
    active = {norm(move[1]): move for run in history for move in run["moves"] if is_active(move)}
    unlogged, errors, count = [], [], 0
    for path in paths:
        try:
            recycle(path)
        except OSError as error:
            errors.append(f"{path.name}: {error}")
            continue
        count += 1
        log.info("Deleted (Recycle Bin) %s", path)
        if norm(path) in active:
            active[norm(path)].append("deleted")
        else:
            unlogged.append([str(path), "", "deleted"])
    if unlogged:
        history.append({"time": time.strftime(TIME_FORMAT), "moves": unlogged, "review": False})
    save_history(history)
    return count, errors


def cleanup_expired(config: dict) -> int:
    """Recycle files this program sorted into a category with "recycle_after_days",
    once that many days have passed since it moved them. Files the program did
    not put there are never touched."""
    limits = {
        norm(root / category["folder"]): category["recycle_after_days"]
        for root in watched_folders(config) for category in config["categories"]
        if category["recycle_after_days"]
    }
    if not limits:
        return 0
    history, count, now = load_history(), 0, time.time()
    for run in history:
        try:
            moved_at = time.mktime(time.strptime(run["time"], TIME_FORMAT))
        except ValueError:
            continue
        for move in run["moves"]:
            destination = Path(move[1])
            days = limits.get(norm(destination.parent)) if is_active(move) else None
            if not days or now - moved_at < days * 86400 or not destination.exists():
                continue
            try:
                recycle(destination)
            except OSError as error:
                log.warning("Could not clean up %s: %s", destination.name, error)
                continue
            move.append("deleted")
            count += 1
            log.info("Cleaned up (Recycle Bin) %s after %d days", destination, days)
    if count:
        save_history(history)
    return count


# --- duplicates ---

def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def find_duplicates(config: dict) -> list[list[Path]]:
    """Groups of byte-identical files in the sorted folders and their category
    folders. The first file of each group is the one to keep."""
    by_size, seen = defaultdict(list), set()
    for root in watched_folders(config):
        folders = [root] + [root / category["folder"] for category in config["categories"]]
        if config["other_folder"]:
            folders.append(root / config["other_folder"])
        for folder in folders:
            if norm(folder) in seen:
                continue
            seen.add(norm(folder))
            try:
                for item in folder.iterdir():
                    if item.is_file() and not is_skipped(item) and (size := item.stat().st_size):
                        by_size[size].append(item)
            except OSError:
                continue
    groups = []
    for paths in by_size.values():
        if len(paths) < 2:
            continue  # a unique size can't have a twin, so it never needs hashing
        by_hash = defaultdict(list)
        for path in paths:
            try:
                by_hash[file_hash(path)].append(path)
            except OSError:
                continue
        # Keep the shortest name: "report.pdf" rather than "report (1).pdf".
        groups += [sorted(group, key=lambda p: (len(p.name), norm(p))) for group in by_hash.values() if len(group) > 1]
    return sorted(groups, key=lambda group: group[0].name.lower())


def setup_logging() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handlers = [logging.FileHandler(LOG_FILE, encoding="utf-8")]
    if sys.stdout is not None:  # no console under pythonw or the packaged exe
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", handlers=handlers)


# --- process control ---

AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "DownloadsSorter"


def run_quiet(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)


def self_command(*args: str) -> list[str]:
    """Command line that launches this program again with the given arguments."""
    if FROZEN:
        return [sys.executable, *args]
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return [str(pythonw if pythonw.exists() else sys.executable), str(APP_DIR / "sort_gui.pyw"), *args]


def launch(*args: str) -> None:
    # Detach all three streams so the child never holds the launcher's console or pipes open.
    subprocess.Popen(self_command(*args), cwd=APP_DIR, creationflags=NO_WINDOW,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def running_pid(pid_file: Path) -> int | None:
    """The PID in pid_file if that process is still one of ours, else None."""
    try:
        pid = int(pid_file.read_text())
    except (OSError, ValueError):
        return None
    output = run_quiet(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"]).stdout.lower()
    return pid if "python" in output or "downloadssorter" in output else None


def background_pid() -> int | None:
    return running_pid(PID_FILE)


def autostart_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as key:
            winreg.QueryValueEx(key, AUTOSTART_NAME)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool, command: list[str] | None = None) -> None:
    """Add or remove the per-user entry that starts background sorting at sign-in."""
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            value = subprocess.list2cmdline(command or self_command("--background"))
            winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, value)
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_NAME)
            except FileNotFoundError:
                pass


def start_background() -> None:
    launch("--background")


def stop_background() -> None:
    pid = background_pid()
    if pid:
        run_quiet(["taskkill", "/PID", str(pid), "/F"])
    PID_FILE.unlink(missing_ok=True)


def open_report() -> None:
    """Show the report window, unless one is already open (it refreshes itself)."""
    if not running_pid(REPORT_PID_FILE):
        launch("--report")


# --- background sorter with its tray icon ---

class Background:
    def __init__(self):
        self.wake = threading.Event()  # set to interrupt the wait between checks
        self.sort_now = False
        self.stopping = False
        self.icon = None  # the tray icon, when pystray is available
        self.shown_state = None

    def loop(self) -> None:
        last_run = 0.0
        while not self.stopping:
            config = load_config()  # reread every tick so GUI changes apply at once
            interval = config["scan_interval_minutes"]
            if interval <= 0:
                log.info("Interval is 0: automatic sorting is disabled; exiting")
                break
            due = time.time() - last_run >= interval * 60 and not is_paused(config)
            if self.sort_now or due:
                self.sort_now = False
                last_run = time.time()
                try:
                    self.sort_pass(config)
                except OSError as error:
                    log.error("Scan failed: %s", error)
            self.show_state(config)
            self.wake.wait(5)
            self.wake.clear()
        if self.icon:
            self.icon.stop()

    def sort_pass(self, config: dict) -> None:
        count, _ = move_files(plan_moves(config), review=True)
        cleaned = cleanup_expired(config)
        if count:
            log.info("Moved %d file(s)", count)
            if config["after_run"] == "window":
                open_report()
            else:
                self.notify(f"Moved {count} file(s). Open History to review or undo.")
        if cleaned:
            self.notify(f"Sent {cleaned} old file(s) to the Recycle Bin. You can bring them back from History.")

    def notify(self, message: str) -> None:
        if self.icon:
            try:
                self.icon.notify(message, APP_NAME)
            except Exception as error:  # a failed toast must not stop the sorter
                log.warning("Notification failed: %s", error)

    def show_state(self, config: dict) -> None:
        paused = is_paused(config)
        if self.icon and paused != self.shown_state:
            self.shown_state = paused
            self.icon.title = f"{APP_NAME}: paused until {config['paused_until']}" if paused else f"{APP_NAME}: on"
            self.icon.update_menu()

    # tray menu actions
    def request_sort(self, *_) -> None:
        self.sort_now = True
        self.wake.set()

    def toggle_pause(self, *_) -> None:
        config = load_config()
        config["paused_until"] = "" if is_paused(config) else pause_until_tomorrow()
        save_config(config)
        self.wake.set()

    def quit(self, *_) -> None:
        self.stopping = True
        self.wake.set()


def tray_image():
    """The tray icon: the app icon, or a simple drawn stand-in if the file is missing."""
    from PIL import Image, ImageDraw

    icon_file = Path(getattr(sys, "_MEIPASS", APP_DIR)) / "icon.ico"
    if icon_file.exists():
        return Image.open(icon_file)
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, 62, 62), radius=12, fill=(37, 99, 235))
    draw.rectangle((28, 12, 36, 32), fill="white")
    draw.polygon([(18, 30), (46, 30), (32, 44)], fill="white")
    draw.rectangle((14, 48, 50, 53), fill="white")
    return image


def run_background() -> None:
    setup_logging()
    if background_pid():
        log.info("Already running; exiting")
        return
    if load_config()["scan_interval_minutes"] <= 0:
        log.info("Interval is 0: automatic sorting is disabled; not starting")
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    log.info("Background sorting started")
    background = Background()
    try:
        try:
            import pystray
        except ImportError:
            log.info("pystray is not installed: running without a tray icon")
            background.loop()
            return
        item = pystray.MenuItem
        background.icon = pystray.Icon("DownloadsSorter", tray_image(), APP_NAME, pystray.Menu(
            item(f"Open {APP_NAME}", lambda *_: launch(), default=True),
            item("Sort now", background.request_sort),
            item(lambda _: "Resume sorting" if is_paused(load_config()) else "Pause for today", background.toggle_pause),
            item("Show report", lambda *_: open_report()),
            pystray.Menu.SEPARATOR,
            item("Exit (starts again at next sign-in)", background.quit),
        ))
        threading.Thread(target=background.loop, daemon=True).start()
        background.icon.run()
    finally:
        PID_FILE.unlink(missing_ok=True)


# --- install locations (used by installer.py and by --uninstall) ---

INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Programs" / APP_NAME
EXE_NAME = "DownloadsSorter.exe"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\DownloadsSorter"


def start_menu_shortcut() -> Path:
    return shell_folder("Programs", Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs") / f"{APP_NAME}.lnk"


def desktop_shortcut() -> Path:
    return shell_folder("Desktop", Path.home() / "Desktop") / f"{APP_NAME}.lnk"
