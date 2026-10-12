# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 hmodymac8-droid
"""Look and feel shared by every Downloads Sorter window.

A dark workspace with a sidebar, a top bar, page headers and bordered panels,
built on the Sun Valley theme (pip install sv-ttk) recoloured to this
program's palette. Without sv-ttk or Pillow the windows still work, just
plainer.
"""

import colorsys
import ctypes
import shutil
import sys
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
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

# The palette: near-black blue-greys with a mint accent.
BACKGROUND = "#0d0e11"  # the page
CARD = "#141517"  # panels, lists and summary cards
SIDEBAR = "#090a0c"
SECONDARY = "#1c1e21"  # hover, badges, quiet fills
RAISED = "#24272a"  # selected list rows
BORDER = "#2a2b2e"
CONTROL_BORDER = "#7a7d82"
TEXT = "#e9ebee"
MUTED = "#a7abb1"
PRIMARY = "#48d7a1"  # the accent: buttons, ticks, the current page
PRIMARY_TEXT = "#041b12"  # text drawn on the accent
BLUE, AMBER, ROSE, RED = "#69acf3", "#e6b55d", "#e581bc", "#f45a56"
GREEN, GRAY = PRIMARY, "#7a7d82"  # status dot colours
WARM = PRIMARY  # older name for the accent, kept for callers
# Tile tones, handed out to category folders in the order they are first seen.
TONES = [PRIMARY, BLUE, AMBER, ROSE, "#a993f0", "#5cc6d6", "#d99a6c", "#9ccf6a"]
PAD = 14  # outer spacing used by all windows
BODY_POINTS = 10
ROW_HEIGHT, TILE_SIZE = 44, 30  # list rows, in 100%-display pixels
EYEBROW = "YOUR DIGITAL SPACE, SORTED"

# Render at the screen's real resolution so text is sharp on scaled displays,
# not a blurry stretched bitmap. Must happen before the first window exists.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except (AttributeError, OSError):
    pass
scale = 1.0  # screen DPI / 96, set by apply()
_tile_cache = {}  # keeps PhotoImages alive; Tk drops images nobody references
_tile_colors = {}
FONT_TEXT, FONT_DISPLAY, FONT_ICONS = "Segoe UI", "Segoe UI Semibold", "Segoe MDL2 Assets"  # set by apply()
TTK_TEXT, TTK_DISPLAY = "Segoe UI", "Segoe UI Semibold"  # fonts of themed (ttk) widgets, set by apply()


def px(pixels: int) -> int:
    """Scale a size designed for a 100% display to this display."""
    return round(pixels * scale)


def mix(color: str, base: str, amount: float) -> str:
    """`amount` of `color` laid over `base`, like CSS color-mix."""
    a, b = (tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (color, base))
    return "#%02x%02x%02x" % tuple(round(x * amount + y * (1 - amount)) for x, y in zip(a, b))


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
        DWMWA_CAPTION_COLOR = 35  # Windows 11: paint the title bar in the sidebar colour
        color = int(SIDEBAR[5:7] + SIDEBAR[3:5] + SIDEBAR[1:3], 16)  # COLORREF is 0x00BBGGRR
        ctypes.windll.dwmapi.DwmSetWindowAttribute(handle, DWMWA_CAPTION_COLOR, ctypes.byref(ctypes.c_int(color)), 4)
    except (AttributeError, OSError):
        pass  # older Windows: the title bar just stays as it is


def _first_font(*families: str) -> str:
    available = set(tkfont.families())
    return next((family for family in families if family in available), families[-1])


def _recolor(sheet):
    """Sun Valley's sprites, moved to this palette: blue accents become mint and
    the neutral greys become the cooler, darker greys of the background."""
    # Grey level in the sprites -> grey level here (piecewise linear).
    points = [(0, 0), (25, 11), (28, 13), (42, 29), (47, 36), (60, 46), (100, 70), (158, 92), (200, 170), (255, 255)]

    def grey(value):
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            if value <= x1:
                return y0 + (y1 - y0) * (value - x0) / max(x1 - x0, 1)
        return value

    primary_hue = colorsys.rgb_to_hsv(*(int(PRIMARY[i:i + 2], 16) / 255 for i in (1, 3, 5)))[0]
    pixels = sheet.load()
    for y in range(sheet.height):
        for x in range(sheet.width):
            r, g, b, a = pixels[x, y]
            if not a:
                continue
            hue, saturation, value = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if saturation > 0.25 and 0.45 < hue < 0.72:  # Sun Valley's blues
                r, g, b = (round(c * 255) for c in colorsys.hsv_to_rgb(primary_hue, saturation, value * 0.84))
            elif saturation < 0.12:
                level = grey(round((r + g + b) / 3))
                r, g, b = (max(0, min(255, round(level + tint))) for tint in (-1, 0, 3))
            pixels[x, y] = (r, g, b, a)
    return sheet


def _restyle_sprites(window: tk.Tk) -> None:
    """Swap Sun Valley's images for recoloured ones, in place, so every style using them follows."""
    folder = Path(sv_ttk.__file__).parent / "theme"
    photo = ImageTk.PhotoImage(_recolor(Image.open(folder / "spritesheet_dark.png").convert("RGBA")), master=window)
    _tile_cache["spritesheet"] = photo
    entries = window.tk.splitlist(window.tk.eval("set ::spriteinfo"))
    for index in range(0, len(entries), 5):
        name, x, y, width, height = entries[index], *map(int, entries[index + 1:index + 5])
        image = window.tk.eval(f"set ::ttk::theme::sv_dark::I({name})")
        window.tk.call(image, "blank")
        window.tk.call(image, "copy", str(photo), "-from", x, y, x + width, y + height)


def apply(window: tk.Tk) -> None:
    """Call once on a new top-level window, before building its contents."""
    global scale, FONT_TEXT, FONT_DISPLAY, FONT_ICONS, TTK_TEXT, TTK_DISPLAY
    scale = window.winfo_fpixels("1i") / 96
    _tile_cache.clear()  # images belong to the window they were made for
    if ICON_FILE.exists():
        try:
            window.iconbitmap(default=str(ICON_FILE))
        except tk.TclError:
            pass
    TTK_TEXT = _first_font("Segoe UI Variable Text", "Segoe UI")
    TTK_DISPLAY = _first_font("Segoe UI Variable Display", "Segoe UI Semibold")
    # Arabic needs care. Themed widgets get their words pre-ordered by i18n.visual(), which
    # assumes the font above (it has no Arabic, so Windows doesn't reorder it again). Plain Tk
    # widgets get Arabic as is and need a font with Arabic letters to show it right to left.
    arabic = getattr(sys.modules.get("i18n"), "LANG", "en") == "ar"
    FONT_TEXT = "Segoe UI" if arabic else TTK_TEXT
    FONT_DISPLAY = "Segoe UI Semibold" if arabic else TTK_DISPLAY
    FONT_ICONS = _first_font("Segoe Fluent Icons", "Segoe MDL2 Assets")
    # Sizes in points follow the display scaling by themselves.
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        tkfont.nametofont(name).configure(family=FONT_TEXT, size=BODY_POINTS)
    window.configure(background=BACKGROUND)
    if sv_ttk is None:
        return
    sv_ttk.set_theme("dark")
    # The theme sets its fonts in fixed pixels (14 for body text), which comes out
    # tiny on a scaled display. Convert each to points: 14px -> 10pt.
    for name in tkfont.names():
        if name.startswith("SunValley"):
            font = tkfont.nametofont(name)
            if font.cget("size") < 0:
                font.configure(size=round(-font.cget("size") * 0.72 + 0.4), family=TTK_TEXT)
    if Image is not None:
        _restyle_sprites(window)
    style = ttk.Style()
    style.configure(".", background=BACKGROUND, foreground=TEXT, troughcolor=SECONDARY,
                    selectbackground=mix(PRIMARY, BACKGROUND, 0.3), selectforeground=TEXT)
    for name in ("TFrame", "TLabel", "TCheckbutton", "Switch.TCheckbutton", "TRadiobutton", "TNotebook"):
        style.configure(name, background=BACKGROUND)
    style.configure("AccentButton.TButton", foreground=PRIMARY_TEXT)
    style.configure("Accent.TButton", foreground=PRIMARY_TEXT)
    style.map("Accent.TButton", foreground=[("disabled", MUTED), ("pressed", PRIMARY_TEXT)])
    style.configure("TCombobox", foreground=TEXT)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Small.TLabel", foreground=MUTED, font=(TTK_TEXT, 8))
    style.configure("Title.TLabel", font=(TTK_DISPLAY, 20, "bold"))
    style.configure("Section.TLabel", font=(TTK_DISPLAY, 12, "bold"))
    style.configure("Eyebrow.TLabel", foreground=PRIMARY, font=(TTK_TEXT, 7, "bold"))
    # Lists: rows on the card colour, headings on the page colour, no outer frame (panels draw that).
    style.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, rowheight=px(ROW_HEIGHT),
                    borderwidth=0, font=(TTK_TEXT, 9))
    style.map("Treeview", background=[("selected", RAISED)], foreground=[("selected", TEXT)])
    style.layout("Treeview", [("Treeview.padding", {"sticky": "nswe", "children": [
        ("Treeview.treearea", {"sticky": "nswe"})]})])
    style.element_create("Flat.Treeheading.cell", "from", "default")
    style.layout("Heading", [("Flat.Treeheading.cell", {"sticky": "nswe"}), ("Treeheading.border", {
        "sticky": "nswe", "children": [("Treeheading.padding", {"sticky": "nswe", "children": [
            ("Treeheading.image", {"side": "right", "sticky": ""}),
            ("Treeheading.text", {"sticky": "we"})]})]})])
    style.configure("Heading", foreground=MUTED, background=BACKGROUND, font=(TTK_TEXT, 8), relief="flat",
                    borderwidth=0, padding=(px(8), px(8)))
    style.map("Heading", background=[("active", SECONDARY)], foreground=[("active", TEXT)])
    style.configure("TNotebook.Tab", padding=(px(12), px(4)))
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
            background=CARD, foreground=TEXT, selectbackground=mix(PRIMARY, CARD, 0.25), selectforeground=TEXT,
            relief="flat", borderwidth=0, highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=PRIMARY)


def style_menu(menu: tk.Menu) -> None:
    if sv_ttk is not None:
        menu.configure(background=CARD, foreground=TEXT, activebackground=mix(PRIMARY, CARD, 0.18),
                       activeforeground=TEXT, relief="flat", borderwidth=1)


# --- images for list rows ---

def _font(name: str, size: int):
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


def tile(label: str = "", group: str = "", faded: bool = False):
    """A small rounded badge for a list row, tinted with the row's folder colour.

    group picks the tone (rows going to the same folder share one); label is
    a few letters drawn on it, normally the file extension.
    """
    if Image is None:
        return ""
    if faded:
        fill, ink = SECONDARY, "#5c5f64"
    elif group.lower() == "other" or not group:
        fill, ink = SECONDARY, MUTED
    else:
        tone = _tile_colors.setdefault(group.lower(), TONES[len(_tile_colors) % len(TONES)])
        fill, ink = mix(tone, CARD, 0.14), tone
    label = label.upper()[:4]
    key = (fill, ink, label, scale)
    if key not in _tile_cache:
        size, big = px(TILE_SIZE), px(TILE_SIZE) * 4  # draw 4x and shrink for smooth edges
        image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=big // 5, fill=fill)
        if label:
            font = _font("segoeuib.ttf", big * (34 if len(label) <= 3 else 27) // 100)
            draw.text((big / 2, big / 2), label, font=font, fill=ink, anchor="mm")
        # A transparent margin on the right separates the tile from the row's text.
        padded = Image.new("RGBA", (size + px(10), size), (0, 0, 0, 0))
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
            draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=big // 5, fill=PRIMARY)
            draw.line([(big * 0.24, big * 0.52), (big * 0.42, big * 0.70), (big * 0.76, big * 0.31)],
                      fill=PRIMARY_TEXT, width=max(1, big // 9), joint="curve")
        else:
            draw.rounded_rectangle((2, 2, big - 3, big - 3), radius=big // 5, outline=CONTROL_BORDER,
                                   width=max(1, big // 14))
        # Same height as the colour tiles, with a gap on the right before the text.
        padded = Image.new("RGBA", (size + px(12), px(TILE_SIZE)), (0, 0, 0, 0))
        padded.paste(image.resize((size, size), Image.LANCZOS), (0, (px(TILE_SIZE) - size) // 2))
        _tile_cache[key] = ImageTk.PhotoImage(padded)
    return _tile_cache[key]


def brand_mark(size: int):
    """The program's mark: a mint rounded square with an arrow down onto a line."""
    if Image is None:
        return ""
    key = ("brand", size, scale)
    if key not in _tile_cache:
        big = px(size) * 4
        image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=big * 26 // 100, fill=PRIMARY)
        width, middle = max(2, big // 15), big / 2
        draw.line([(middle, big * 0.24), (middle, big * 0.62)], fill=PRIMARY_TEXT, width=width)
        draw.line([(big * 0.33, big * 0.46), (middle, big * 0.63), (big * 0.67, big * 0.46)],
                  fill=PRIMARY_TEXT, width=width, joint="curve")
        draw.line([(big * 0.3, big * 0.76), (big * 0.7, big * 0.76)], fill=PRIMARY_TEXT, width=width)
        _tile_cache[key] = ImageTk.PhotoImage(image.resize((px(size), px(size)), Image.LANCZOS))
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


# --- building blocks for pages ---

def label(parent, text="", color=TEXT, size=BODY_POINTS, weight="normal", background=None, display=False,
          font=None, **options):
    """A plain Tk label in this palette (plain Tk, so it can sit on any background colour)."""
    options = {"borderwidth": 0, "padx": 0, "pady": 0, **options}
    return tk.Label(parent, text=text, foreground=color, background=background or parent.cget("background"),
                    font=font or (FONT_DISPLAY if display else FONT_TEXT, size, weight), **options)


_header_extras = []  # (header, eyebrow, description) of every page, hidden when the window is short


def page_header(parent, title: str, description: str, eyebrow: str = EYEBROW) -> ttk.Frame:
    """The top of a page: a small coloured line, a big title and a short description,
    with room on the right for the page's main buttons, which is returned."""
    header = ttk.Frame(parent)
    header.pack(fill="x", pady=(0, px(20)))
    actions = ttk.Frame(header)
    actions.pack(side="right", anchor="s")
    text = ttk.Frame(header)
    text.pack(side="left", fill="x", expand=True)
    eyebrow_label = ttk.Label(text, text=eyebrow, style="Eyebrow.TLabel")
    eyebrow_label.pack(anchor="w", pady=(0, px(4)))
    header.title = ttk.Label(text, text=title, style="Title.TLabel")
    header.title.pack(anchor="w")
    description_label = ttk.Label(text, text=description, style="Muted.TLabel")
    description_label.pack(anchor="w", pady=(px(4), 0))
    _header_extras.append((header, eyebrow_label, description_label))
    actions.header = header
    return actions


class Panel(tk.Frame):
    """A bordered box for a list: a toolbar on top, the list, and an optional footer."""

    def __init__(self, parent, title: str = "", glyph: str = ""):
        super().__init__(parent, background=BACKGROUND, highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=BORDER)
        self.toolbar = ttk.Frame(self, padding=(px(16), px(12)))
        self.toolbar.pack(fill="x")
        self.title = ttk.Frame(self.toolbar)
        self.title.pack(side="left")
        if glyph:
            label(self.title, glyph, PRIMARY, 11, background=BACKGROUND,
                  font=(FONT_ICONS, 11)).pack(side="left", padx=(0, px(8)))
        if title:
            label(self.title, title, TEXT, 10, "bold", background=BACKGROUND).pack(side="left")
        self.count = tk.Label(self.title, background=SECONDARY, foreground=MUTED, font=(FONT_TEXT, 8),
                              padx=px(7), pady=px(1), highlightthickness=1, highlightbackground=BORDER)
        self.controls = ttk.Frame(self.toolbar)
        self.controls.pack(side="right")
        tk.Frame(self, background=BORDER, height=1).pack(fill="x")
        self.footer = None
        self.body = tk.Frame(self, background=CARD)
        self.body.pack(fill="both", expand=True)

    def set_count(self, text: str) -> None:
        if text:
            self.count.config(text=text)
            self.count.pack(side="left", padx=(px(10), 0))
        else:
            self.count.pack_forget()

    def add_footer(self) -> ttk.Frame:
        """A strip under the list for totals and buttons. Packed before the list grows,
        so the list (not the buttons) shrinks in a small window."""
        self.body.pack_forget()
        self.footer = ttk.Frame(self, padding=(px(16), px(10)))
        self.footer.pack(side="bottom", fill="x")
        tk.Frame(self, background=BORDER, height=1).pack(side="bottom", fill="x")
        self.body.pack(fill="both", expand=True)
        return self.footer


class StatCard(tk.Frame):
    """A summary card: a caption with an icon, a big value with a unit, and a note."""

    def __init__(self, parent, caption: str, glyph: str):
        super().__init__(parent, background=CARD, highlightthickness=1, highlightbackground=BORDER,
                         padx=px(18), pady=px(14))
        top = tk.Frame(self, background=CARD)
        top.pack(fill="x")
        label(top, caption, MUTED, 9).pack(side="left")
        label(top, glyph, MUTED, background=CARD, font=(FONT_ICONS, 11)).pack(side="right")
        line = tk.Frame(self, background=CARD)
        line.pack(fill="x", pady=(px(8), px(2)))
        self.value = label(line, "—", TEXT, 20, "bold", display=True)
        self.value.pack(side="left")
        self.unit = label(line, "", MUTED, 10)
        self.unit.pack(side="left", anchor="s", padx=(px(6), 0), pady=(0, px(5)))
        self.note = label(self, "", MUTED, 8, anchor="w")
        self.note.pack(fill="x")

    def set(self, value: str, unit: str = "", note: str | None = None) -> None:
        self.value.config(text=value)
        self.unit.config(text=unit)
        if note is not None:
            self.note.config(text=note)


_stat_rows = []  # every row of summary cards, hidden together when the window is short


def stat_row(parent, cards: list[tuple[str, str]]) -> list[StatCard]:
    """A row of summary cards sharing the width equally. cards: (caption, glyph).
    Make it the first thing packed on its page, so it can be put back in place."""
    row = ttk.Frame(parent)
    row.pack(fill="x", pady=(0, px(18)))
    _stat_rows.append(row)
    made = []
    for column, (caption, glyph) in enumerate(cards):
        row.columnconfigure(column, weight=1, uniform="stat")
        card = StatCard(row, caption, glyph)
        card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else px(6), 0 if
                                                             column == len(cards) - 1 else px(6)))
        made.append(card)
    return made


def fit_height(window: tk.Misc, minimum: int = 760) -> None:
    """Hide the summary cards and the header's small print while the window is too short for them
    and the lists below."""
    show = window.winfo_height() >= px(minimum)
    for header, eyebrow, description in _header_extras:
        if show and not eyebrow.winfo_manager():
            eyebrow.pack(anchor="w", pady=(0, px(4)), before=header.title)
            description.pack(anchor="w", pady=(px(4), 0), after=header.title)
            header.pack_configure(pady=(0, px(20)))
        elif not show and eyebrow.winfo_manager():
            eyebrow.pack_forget()
            description.pack_forget()
            header.pack_configure(pady=(0, px(12)))
    for row in _stat_rows:
        if show and not row.winfo_manager():
            siblings = row.master.pack_slaves()
            row.pack(fill="x", pady=(0, px(18)), **({"before": siblings[0]} if siblings else {}))
        elif not show and row.winfo_manager():
            row.pack_forget()


class Splash(tk.Toplevel):
    """A small borderless card shown in the middle of the screen while the program starts."""

    def __init__(self, parent: tk.Tk, name: str, detail: str):
        super().__init__(parent)
        self.overrideredirect(True)  # no title bar or border
        self.configure(background=SIDEBAR, highlightthickness=1, highlightbackground=BORDER)
        width, height = px(380), px(250)
        self.geometry(f"{width}x{height}+{(self.winfo_screenwidth() - width) // 2}"
                      f"+{(self.winfo_screenheight() - height) // 2}")
        tk.Label(self, image=brand_mark(72) or app_icon(84), background=SIDEBAR).pack(pady=(px(40), px(16)))
        tk.Label(self, text=name, background=SIDEBAR, foreground=TEXT, font=(FONT_DISPLAY, 16)).pack()
        tk.Label(self, text=detail, background=SIDEBAR, foreground=MUTED, font=(FONT_TEXT, 9)).pack(pady=(px(4), 0))
        self.attributes("-topmost", True)
        self.update()  # paint now; the main window is still being built


class NavItem(tk.Canvas):
    """One sidebar entry, drawn on a canvas so it can have rounded corners and a count badge."""

    def __init__(self, parent, glyph: str, text: str, command):
        super().__init__(parent, background=SIDEBAR, height=px(42), highlightthickness=0, cursor="hand2")
        self.glyph, self.text, self.badge = glyph, text, ""
        self.state = "normal"  # "normal", "hover" or "current"
        self.bind("<Configure>", lambda _: self.draw())
        self.bind("<Enter>", lambda _: self.set_state("hover", only_from="normal"))
        self.bind("<Leave>", lambda _: self.set_state("normal", only_from="hover"))
        self.bind("<Button-1>", lambda _: command())

    def set_state(self, state: str, only_from: str | None = None) -> None:
        if only_from is None or self.state == only_from:
            self.state = state
            self.draw()

    def set_badge(self, text: str) -> None:
        self.badge = text
        self.draw()

    def draw(self) -> None:
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        fill = {"current": mix(PRIMARY, SIDEBAR, 0.10), "hover": SECONDARY}.get(self.state)
        ink = {"current": PRIMARY, "hover": TEXT}.get(self.state, MUTED)
        if fill:
            r, x0, y0, x1, y1 = px(6), 1, 1, width - 2, height - 2
            self.create_polygon(
                x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1, x0, y1,
                x0, y1 - r, x0, y0 + r, x0, y0, smooth=True, fill=fill, outline=fill)
        self.create_text(px(16), height // 2, text=self.glyph, fill=ink, anchor="w", font=(FONT_ICONS, 12))
        self.create_text(px(46), height // 2, text=self.text, fill=ink, anchor="w", font=(FONT_TEXT, 10))
        if self.badge:
            font = (FONT_TEXT, 8)
            text = self.create_text(width - px(14), height // 2, text=self.badge, fill=ink, anchor="e", font=font)
            x0, y0, x1, y1 = self.bbox(text)
            box = self.create_rectangle(x0 - px(6), y0 - px(1), x1 + px(6), y1 + px(1),
                                        fill=mix(PRIMARY, SIDEBAR, 0.12), outline="")
            self.tag_lower(box, text)


class Sidebar(tk.Frame):
    """Navigation down the left: the brand, the main pages, and at the bottom the
    disk space, Settings, Help & about, the version and a Donate link."""

    def __init__(self, parent, title: str, on_select):
        super().__init__(parent, background=SIDEBAR, width=px(228))
        self.pack_propagate(False)
        self.on_select = on_select
        self.items = {}  # page key -> NavItem
        self.selected = None
        tk.Frame(self, background=BORDER, width=1).pack(side="right", fill="y")
        brand = tk.Frame(self, background=SIDEBAR)
        brand.pack(fill="x", padx=px(22), pady=(px(26), 0))
        tk.Label(brand, image=brand_mark(38), background=SIDEBAR).pack(side="left")
        # The name is drawn on a canvas: it stays as it is in every language.
        first, _, rest = title.partition(" ")
        font = tkfont.Font(family=FONT_DISPLAY, size=11, weight="bold")
        line = font.metrics("linespace")
        name = tk.Canvas(brand, background=SIDEBAR, highlightthickness=0, height=line * 2,
                         width=max(font.measure(first), font.measure(rest + ".")) + 2)
        name.pack(side="left", padx=(px(12), 0))
        name.create_text(0, 0, text=first, fill=TEXT, font=font, anchor="nw")
        name.create_text(0, line, text=rest, fill=TEXT, font=font, anchor="nw")
        name.create_text(font.measure(rest), line, text=".", fill=PRIMARY, font=font, anchor="nw")
        label(self, "WORKSPACE", MUTED, 7, "bold", anchor="w").pack(fill="x", padx=px(28), pady=(px(30), px(8)))
        self.main = tk.Frame(self, background=SIDEBAR)
        self.main.pack(fill="x", padx=px(14))
        self.bottom = tk.Frame(self, background=SIDEBAR)
        self.bottom.pack(side="bottom", fill="x", padx=px(14), pady=(0, px(16)))
        # Disk space where the downloads live, like the design's "Local storage" bar.
        self.storage = tk.Frame(self.bottom, background=SIDEBAR)
        self.storage.pack(fill="x", padx=px(10), pady=(0, px(12)))
        tk.Frame(self.storage, background=BORDER, height=1).pack(fill="x", pady=(0, px(16)))
        head = tk.Frame(self.storage, background=SIDEBAR)
        head.pack(fill="x")
        label(head, "", MUTED, background=SIDEBAR, font=(FONT_ICONS, 10)).pack(side="left")
        label(head, "Local storage", TEXT, 9).pack(side="left", padx=(px(8), 0))
        self.bar = tk.Canvas(self.storage, height=px(5), background=SECONDARY, highlightthickness=0)
        self.bar.pack(fill="x", pady=px(10))
        numbers = tk.Frame(self.storage, background=SIDEBAR)
        numbers.pack(fill="x")
        self.used = label(numbers, "", MUTED, 8)
        self.used.pack(side="left")
        self.total = label(numbers, "", MUTED, 8)
        self.total.pack(side="right")
        self.bar.bind("<Configure>", lambda _: self._draw_bar())
        self.share = 0.0
        self.bottom_items = tk.Frame(self.bottom, background=SIDEBAR)
        self.bottom_items.pack(fill="x")
        self.version_row = tk.Frame(self.bottom, background=SIDEBAR)
        self.version_row.pack(fill="x", padx=px(14), pady=(px(10), 0))

    def add(self, key: str, glyph: str, text: str, bottom: bool = False) -> None:
        item = NavItem(self.bottom_items if bottom else self.main, glyph, text, lambda: self.on_select(key))
        item.pack(fill="x", pady=px(2))
        self.items[key] = item

    def set_badge(self, key: str, text: str) -> None:
        self.items[key].set_badge(text)

    def select(self, key: str) -> None:
        previous, self.selected = self.selected, key
        if previous:
            self.items[previous].set_state("normal")
        self.items[key].set_state("current")

    def show_storage(self, folder: Path) -> None:
        """Fill the storage bar from the drive the folder is on."""
        try:
            usage = shutil.disk_usage(folder)
        except OSError:
            self.storage.pack_forget()
            return
        gb = 1024 ** 3
        self.share = usage.used / usage.total if usage.total else 0
        self.used.config(text=f"{usage.used / gb:.0f} GB used")
        self.total.config(text=f"{usage.total / gb:.0f} GB")
        self._draw_bar()

    def _draw_bar(self) -> None:
        self.bar.delete("all")
        width = self.bar.winfo_width()
        color = RED if self.share > 0.9 else AMBER if self.share > 0.75 else PRIMARY
        self.bar.create_rectangle(0, 0, round(width * self.share), px(5), fill=color, outline="")

    def show_version(self, text: str, link_text: str, url: str) -> None:
        label(self.version_row, text, MUTED, 8).pack(side="left")
        link = label(self.version_row, link_text + " ↗", PRIMARY, 8, cursor="hand2")
        link.pack(side="right")
        link.bind("<Button-1>", lambda _: webbrowser.open(url))


class TopBar(tk.Frame):
    """A strip across the top of the page area: where you are, and how things stand."""

    def __init__(self, parent):
        super().__init__(parent, background=BACKGROUND)
        row = tk.Frame(self, background=BACKGROUND, height=px(60))
        row.pack(fill="x")
        row.pack_propagate(False)
        crumbs = tk.Frame(row, background=BACKGROUND)
        crumbs.pack(side="left", padx=px(30))
        label(crumbs, "", MUTED, background=BACKGROUND, font=(FONT_ICONS, 11)).pack(side="left")
        label(crumbs, "Workspace", MUTED, 9).pack(side="left", padx=(px(10), px(8)))
        label(crumbs, "", MUTED, background=BACKGROUND, font=(FONT_ICONS, 8)).pack(side="left")
        self.page = label(crumbs, "", TEXT, 9)
        self.page.pack(side="left", padx=(px(8), 0))
        status = tk.Frame(row, background=BACKGROUND)
        status.pack(side="right", padx=px(30))
        self.dot = label(status, "●", PRIMARY, 8)
        self.dot.pack(side="left")
        self.status = label(status, "", MUTED, 8)
        self.status.pack(side="left", padx=(px(6), 0))
        tk.Frame(self, background=BORDER, height=1).pack(fill="x")

    def set_page(self, title: str) -> None:
        self.page.config(text=title)

    def set_status(self, text: str, color: str) -> None:
        self.status.config(text=text)
        self.dot.config(foreground=color)
