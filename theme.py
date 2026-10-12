"""Look and feel shared by every Downloads Sorter window.

A dark layout with a sidebar and coloured file tiles, built on the Sun Valley
theme (pip install sv-ttk). Without sv-ttk or Pillow the windows still work,
just plainer.
"""

import ctypes
import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk

try:
    import sv_ttk
except ImportError:
    sv_ttk = None
try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
except ImportError:
    Image = None

# Bundled files sit next to the scripts, or in PyInstaller's unpack folder.
ICON_FILE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "icon.ico"

BACKGROUND = "#1c1c1c"  # Sun Valley's dark window colour
SIDEBAR = "#141414"
SIDEBAR_HOVER = "#222222"
SIDEBAR_SELECTED = "#2a2a2a"
TEXT = "#f2f2f2"
MUTED = "#9a9a9a"
WARM = "#ff6b4a"  # accent used for the sidebar marker
GREEN, AMBER, GRAY = "#22a55b", "#e0a100", "#8a8a8a"  # status dot colours
# Tile colours, handed out to category folders in the order they are first seen.
# Muted, equally dark tones so the tiles sit quietly on the dark background.
PALETTE = ["#4f6485", "#6a5a8c", "#3f7273", "#7d6a48", "#7c5566", "#55744f", "#855f4c", "#48708f"]
NEUTRAL_TILE, FADED_TILE = "#5a5a5a", "#333333"
PAD = 14  # outer spacing used by all windows
BODY_POINTS = 11
ROW_HEIGHT, TILE_SIZE = 40, 28  # list rows, in 100%-display pixels

# Render at the screen's real resolution so text is sharp on scaled displays,
# not a blurry stretched bitmap. Must happen before the first window exists.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except (AttributeError, OSError):
    pass
scale = 1.0  # screen DPI / 96, set by apply()
_tile_cache = {}  # keeps PhotoImages alive; Tk drops images nobody references
_tile_colors = {}


def px(pixels: int) -> int:
    """Scale a size designed for a 100% display to this display."""
    return round(pixels * scale)


def set_size(window: tk.Misc, width: int, height: int, min_width: int, min_height: int) -> None:
    """Size a window in 100%-display units, kept within the screen."""
    max_width, max_height = window.winfo_screenwidth() - px(40), window.winfo_screenheight() - px(90)
    window.geometry(f"{min(px(width), max_width)}x{min(px(height), max_height)}")
    window.minsize(min(px(min_width), max_width), min(px(min_height), max_height))


def dark_titlebar(window: tk.Misc) -> None:
    """Match the title bar to the dark theme (Windows draws it, not Tk)."""
    if sv_ttk is None:
        return
    try:
        window.update_idletasks()
        handle = ctypes.windll.user32.GetParent(window.winfo_id())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            handle, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(ctypes.c_int(1)), 4)
    except (AttributeError, OSError):
        pass  # older Windows: the title bar just stays light


def apply(window: tk.Tk) -> None:
    """Call once on a new top-level window, before building its contents."""
    global scale
    scale = window.winfo_fpixels("1i") / 96
    _tile_cache.clear()  # images belong to the window they were made for
    if ICON_FILE.exists():
        try:
            window.iconbitmap(default=str(ICON_FILE))
        except tk.TclError:
            pass
    # Sizes in points follow the display scaling by themselves.
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        tkfont.nametofont(name).configure(family="Segoe UI", size=BODY_POINTS)
    if sv_ttk is None:
        return
    sv_ttk.set_theme("dark")
    # The theme sets its fonts in fixed pixels (14 for body text), which comes out
    # tiny on a scaled display. Convert each to points, a touch larger: 14px -> 11pt.
    for name in tkfont.names():
        if name.startswith("SunValley"):
            font = tkfont.nametofont(name)
            if font.cget("size") < 0:
                font.configure(size=round(-font.cget("size") * 0.75 + 0.6))
    style = ttk.Style()
    style.configure("Treeview", rowheight=px(ROW_HEIGHT))
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Title.TLabel", font=font_of("SunValleySubtitleFont", ("Segoe UI Semibold", 16)))
    window.configure(background=BACKGROUND)
    dark_titlebar(window)


def font_of(name: str, fallback):
    """A theme font by name, or a plain fallback when the theme is missing."""
    return name if name in tkfont.names() else fallback


def accent() -> str:
    """Style name for the one primary button of a view."""
    return "Accent.TButton" if sv_ttk is not None else "TButton"


def switch() -> str:
    """Style name for an on/off toggle."""
    return "Switch.TCheckbutton" if sv_ttk is not None else "TCheckbutton"


def style_listbox(listbox: tk.Listbox) -> None:
    """Plain Tk widgets don't follow the ttk theme, so colour them to match."""
    if sv_ttk is not None:
        listbox.configure(
            background="#2b2b2b", foreground=TEXT, selectbackground="#2f60d8", selectforeground="#ffffff",
            relief="flat", borderwidth=0, highlightthickness=1, highlightbackground="#454545",
            highlightcolor="#2f60d8")


def style_menu(menu: tk.Menu) -> None:
    if sv_ttk is not None:
        menu.configure(background="#2b2b2b", foreground=TEXT, activebackground="#2f60d8",
                       activeforeground="#ffffff", relief="flat", borderwidth=1)


def tile(label: str = "", group: str = "", faded: bool = False):
    """A small rounded colour square for a list row, like a file-type badge.

    group picks the colour (rows going to the same folder share one); label is
    a few letters drawn on it, normally the file extension.
    """
    if Image is None:
        return ""
    if faded:
        color = FADED_TILE
    elif group.lower() == "other" or not group:
        color = NEUTRAL_TILE
    else:
        color = _tile_colors.setdefault(group.lower(), PALETTE[len(_tile_colors) % len(PALETTE)])
    label = label.upper()[:4]
    key = (color, label, scale)
    if key not in _tile_cache:
        size, big = px(TILE_SIZE), px(TILE_SIZE) * 4  # draw 4x and shrink for smooth edges
        image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=big // 4, fill=color)
        if label:
            try:
                font = ImageFont.truetype("segoeuib.ttf", big * (38 if len(label) <= 3 else 30) // 100)
            except OSError:
                font = ImageFont.load_default()
            ink = "#8a8a8a" if faded else "#f2f2f2"
            draw.text((big / 2, big / 2), label, font=font, fill=ink, anchor="mm")
        # A transparent margin on the right separates the tile from the row's text.
        padded = Image.new("RGBA", (size + px(8), size), (0, 0, 0, 0))
        padded.paste(image.resize((size, size), Image.LANCZOS), (0, 0))
        _tile_cache[key] = ImageTk.PhotoImage(padded)
    return _tile_cache[key]


def checkbox(checked: bool):
    """A tick box for list rows. Being an image, a click on it can be told
    apart from a click on the row's text. Returns "" without Pillow."""
    if Image is None:
        return ""
    key = ("checkbox", checked, scale)
    if key not in _tile_cache:
        size, big = px(18), px(18) * 4  # draw 4x and shrink for smooth edges
        image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        if checked:
            draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=big // 5, fill=WARM)
            draw.line([(big * 0.24, big * 0.52), (big * 0.42, big * 0.70), (big * 0.76, big * 0.31)],
                      fill="#ffffff", width=max(1, big // 9), joint="curve")
        else:
            draw.rounded_rectangle((2, 2, big - 3, big - 3), radius=big // 5, outline=MUTED, width=max(1, big // 14))
        # Same height as the colour tiles, with a gap on the right before the text.
        padded = Image.new("RGBA", (size + px(10), px(TILE_SIZE)), (0, 0, 0, 0))
        padded.paste(image.resize((size, size), Image.LANCZOS), (0, (px(TILE_SIZE) - size) // 2))
        _tile_cache[key] = ImageTk.PhotoImage(padded)
    return _tile_cache[key]


def app_icon(size: int):
    """The app icon as an image for a label, `size` pixels at 100% scaling ("" without Pillow)."""
    if Image is None or not ICON_FILE.exists():
        return ""
    key = ("icon", size, scale)
    if key not in _tile_cache:
        icon = Image.open(ICON_FILE)
        icon.size = max(icon.info.get("sizes", [icon.size]))  # pick the largest picture in the .ico
        _tile_cache[key] = ImageTk.PhotoImage(icon.convert("RGBA").resize((px(size), px(size)), Image.LANCZOS))
    return _tile_cache[key]


class Splash(tk.Toplevel):
    """A small borderless card shown in the middle of the screen while the program starts."""

    def __init__(self, parent: tk.Tk, name: str, detail: str):
        super().__init__(parent)
        self.overrideredirect(True)  # no title bar or border
        self.configure(background=SIDEBAR, highlightthickness=1, highlightbackground="#333333")
        width, height = px(380), px(250)
        self.geometry(f"{width}x{height}+{(self.winfo_screenwidth() - width) // 2}"
                      f"+{(self.winfo_screenheight() - height) // 2}")
        tk.Label(self, image=app_icon(84), background=SIDEBAR).pack(pady=(px(34), px(14)))
        tk.Label(self, text=name, background=SIDEBAR, foreground=TEXT, font=("Segoe UI Semibold", 16)).pack()
        tk.Label(self, text=detail, background=SIDEBAR, foreground=MUTED, font=("Segoe UI", 10)).pack(pady=(px(4), 0))
        self.attributes("-topmost", True)
        self.update()  # paint now; the main window is still being built


class Sidebar(tk.Frame):
    """Vertical navigation: an icon and a name per page, with a marker on the current one."""

    def __init__(self, parent, title: str, on_select):
        super().__init__(parent, background=SIDEBAR, width=px(210))
        self.pack_propagate(False)
        self.on_select = on_select
        self.rows = {}  # page key -> (row frame, marker, icon label, text label)
        self.selected = None
        tk.Label(self, text=title, background=SIDEBAR, foreground=TEXT, anchor="w",
                 font=("Segoe UI Semibold", 14)).pack(fill="x", padx=px(18), pady=(px(20), px(18)))

    def add(self, key: str, glyph: str, text: str) -> None:
        row = tk.Frame(self, background=SIDEBAR, cursor="hand2")
        row.pack(fill="x", pady=px(1))
        marker = tk.Frame(row, background=SIDEBAR, width=px(4))
        marker.pack(side="left", fill="y")
        # Segoe MDL2 Assets is Windows' own icon font.
        icon = tk.Label(row, text=glyph, background=SIDEBAR, foreground=MUTED, font=("Segoe MDL2 Assets", 12))
        icon.pack(side="left", padx=(px(14), px(12)), pady=px(11))
        label = tk.Label(row, text=text, background=SIDEBAR, foreground=MUTED, anchor="w", font=("Segoe UI", 11))
        label.pack(side="left", fill="x", expand=True)
        self.rows[key] = (row, marker, icon, label)
        for widget in (row, icon, label):
            widget.bind("<Button-1>", lambda _, key=key: self.on_select(key))
            widget.bind("<Enter>", lambda _, key=key: self.paint(key, hover=True))
            widget.bind("<Leave>", lambda _, key=key: self.paint(key))

    def paint(self, key: str, hover: bool = False) -> None:
        row, marker, icon, label = self.rows[key]
        current = key == self.selected
        background = SIDEBAR_SELECTED if current else SIDEBAR_HOVER if hover else SIDEBAR
        marker.configure(background=WARM if current else background)
        for widget in (row, icon, label):
            widget.configure(background=background)
        for widget in (icon, label):
            widget.configure(foreground=TEXT if current or hover else MUTED)

    def select(self, key: str) -> None:
        previous, self.selected = self.selected, key
        if previous:
            self.paint(previous)
        self.paint(key)
