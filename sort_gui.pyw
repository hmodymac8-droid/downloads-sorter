"""Downloads Sorter: control panel, report window and background entry point."""

import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import booster
import cleaner
import duplicates
import sort_downloads as core
import theme

AFTER_RUN_LABELS = {"window": "Show a report window", "notify": "Only a tray notification"}


def format_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def split_list(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,;\n]+", text) if part.strip()]


def parse_extensions(text: str) -> list[str]:
    parts = [p.lower() for p in re.split(r"[,\s;]+", text) if p.strip(".")]
    return sorted({p if p.startswith(".") else "." + p for p in parts})


def report_result(parent, message, errors):
    if errors:
        shown = "\n".join(errors[:10]) + ("\n…" if len(errors) > 10 else "")
        messagebox.showwarning("Done", f"{message}\n\n{len(errors)} failed:\n{shown}", parent=parent)
    else:
        messagebox.showinfo("Done", message, parent=parent)


def ask_delete_how(parent, message):
    """Ask whether to recycle or delete for good. Returns "recycle", "permanent" or None."""
    dialog = tk.Toplevel(parent)
    dialog.title("Delete")
    dialog.transient(parent)
    dialog.resizable(False, False)
    dialog.configure(background=theme.BACKGROUND)
    theme.dark_titlebar(dialog)
    answer = []
    frame = ttk.Frame(dialog, padding=theme.px(18))
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=message, justify="left", wraplength=theme.px(460)).pack(anchor="w")
    ttk.Label(frame, text="Files sent to the Recycle Bin can be brought back from History.",
              style="Muted.TLabel").pack(anchor="w", pady=(theme.px(10), 0))
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(theme.px(16), 0))

    def choose(value):
        answer.append(value)
        dialog.destroy()

    ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right")
    ttk.Button(buttons, text="Delete for good", command=lambda: choose("permanent")).pack(side="right", padx=6)
    recycle = ttk.Button(buttons, text="Move to Recycle Bin", style=theme.accent(), command=lambda: choose("recycle"))
    recycle.pack(side="right")
    dialog.bind("<Escape>", lambda _: dialog.destroy())
    dialog.bind("<Return>", lambda _: choose("recycle"))
    dialog.update_idletasks()
    dialog.geometry(f"+{parent.winfo_rootx() + (parent.winfo_width() - dialog.winfo_width()) // 2}"
                    f"+{parent.winfo_rooty() + (parent.winfo_height() - dialog.winfo_height()) // 3}")
    recycle.focus_set()
    dialog.grab_set()
    parent.wait_window(dialog)
    return answer[0] if answer else None


def attach_file_menu(tree, path_for_row, on_change, extra=()):
    """Give a file list a right-click menu (show in Explorer, open, delete) and
    make double-click show the file in Explorer.

    path_for_row(row id) returns where that row's file is now, or None.
    extra adds (label, function(path)) items above Delete.
    """

    def current():
        selection = tree.selection()
        path = path_for_row(selection[0]) if selection else None
        if path is None or not path.exists():
            messagebox.showinfo("File", "This file is not there any more.", parent=tree)
            return None
        return path

    def show():
        if path := current():
            subprocess.Popen(f'explorer /select,"{path}"')

    def run():
        if path := current():
            try:
                os.startfile(path)
            except OSError as error:
                messagebox.showwarning("Open", f"Could not open it:\n{error}", parent=tree)

    def delete():
        path = current()
        if not path or not messagebox.askyesno(
                "Delete", f"Move this file to the Recycle Bin?\n\n{path.name}\n\n"
                "You can bring it back from the History tab.", parent=tree):
            return
        _, errors = core.delete_files([path])
        if errors:
            messagebox.showwarning("Delete", f"Could not delete it:\n{errors[0]}", parent=tree)
            return
        on_change()

    def call(function):
        if path := current():
            function(path)

    menu = tk.Menu(tree, tearoff=0)
    theme.style_menu(menu)
    menu.add_command(label="Show in File Explorer", command=show)
    menu.add_command(label="Open / Run", command=run)
    menu.add_separator()
    for label, function in extra:
        menu.add_command(label=label, command=lambda function=function: call(function))
    menu.add_command(label="Delete (to Recycle Bin)", command=delete)

    def popup(event):
        row = tree.identify_row(event.y)
        if row:
            if row not in tree.selection():
                tree.selection_set(row)
            menu.tk_popup(event.x_root, event.y_root)

    tree.bind("<Button-3>", popup)
    # Double-clicking a file row (not a column heading) shows it in File Explorer.
    tree.bind("<Double-1>", lambda event: show() if tree.identify_row(event.y) else None)


def add_scrolled_tree(parent, columns, first=None, **options):
    """Treeview with a vertical scrollbar. columns: (id, title, width, anchor).

    first=(title, width) adds a leading column that shows each row's text with
    its colour tile.
    """
    tree = ttk.Treeview(parent, columns=[c[0] for c in columns], show="tree headings" if first else "headings", **options)
    if first:
        tree.heading("#0", text=first[0], anchor="w")
        tree.column("#0", width=theme.px(first[1]), anchor="w")
    for column, title, width, anchor in columns:
        tree.heading(column, text=title, anchor=anchor)
        tree.column(column, width=theme.px(width), anchor=anchor)
    scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    tree.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="left", fill="y")
    return tree


class CategoryDialog(tk.Toplevel):
    """Add or edit one category."""

    def __init__(self, parent, category=None):
        super().__init__(parent)
        self.title("Category")
        self.transient(parent)
        self.resizable(False, False)
        self.result = None
        theme.dark_titlebar(self)
        category = category or {"folder": "", "extensions": [], "min_age_days": None, "recycle_after_days": 0}
        self.folder = tk.StringVar(value=category["folder"])
        self.extensions = tk.StringVar(value=" ".join(category["extensions"]))
        self.age = tk.StringVar(value="" if category["min_age_days"] is None else str(category["min_age_days"]))
        self.recycle = tk.StringVar(value=str(category["recycle_after_days"]))

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Destination folder").grid(row=0, column=0, sticky="w")
        ttk.Entry(body, textvariable=self.folder, width=52).grid(row=1, column=0, pady=(2, 0))
        ttk.Button(body, text="Browse…", command=self.browse).grid(row=1, column=1, padx=(6, 0))
        ttk.Label(body, text="A plain name creates the folder inside the folder being sorted.",
                  foreground="gray").grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Label(body, text="File extensions (separated by spaces or commas)").grid(
            row=3, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(body, textvariable=self.extensions, width=52).grid(row=4, column=0, pady=(2, 0))

        ttk.Label(body, text="Move these files after (days)").grid(row=5, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(body, textvariable=self.age, width=8).grid(row=6, column=0, sticky="w", pady=(2, 0))
        ttk.Label(body, text="Leave blank to use the general setting.", foreground="gray").grid(
            row=7, column=0, columnspan=2, sticky="w")
        ttk.Label(body, text="Clean up: send to the Recycle Bin after (days in this folder)").grid(
            row=8, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(body, textvariable=self.recycle, width=8).grid(row=9, column=0, sticky="w", pady=(2, 0))
        ttk.Label(body, text="0 = never. Only files this program moved here are cleaned up,\n"
                  "and you can bring them back from the History tab.", foreground="gray", justify="left").grid(
            row=10, column=0, columnspan=2, sticky="w")

        buttons = ttk.Frame(body)
        buttons.grid(row=11, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="OK", style=theme.accent(), command=self.accept).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left")

        self.bind("<Return>", lambda _: self.accept())
        self.bind("<Escape>", lambda _: self.destroy())
        self.grab_set()
        self.wait_window()

    def browse(self):
        folder = filedialog.askdirectory(parent=self)
        if folder:
            self.folder.set(folder)

    def accept(self):
        folder, extensions = self.folder.get().strip(), parse_extensions(self.extensions.get())
        try:
            age = int(self.age.get()) if self.age.get().strip() else None
            recycle = int(self.recycle.get() or 0)
            if (age is not None and age < 0) or recycle < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Category", "Days must be whole numbers, 0 or more.", parent=self)
            return
        if not folder or not extensions:
            messagebox.showwarning("Category", "Enter a folder and at least one extension.", parent=self)
            return
        self.result = {"folder": folder, "extensions": extensions, "min_age_days": age, "recycle_after_days": recycle}
        self.destroy()


class App(tk.Tk):
    def __init__(self, splash=False):
        super().__init__()
        self.title(core.APP_NAME)
        if splash:
            self.withdraw()  # stay hidden behind the splash card until everything is built
        theme.apply(self)
        splash_card = theme.Splash(self, core.APP_NAME, f"Version {core.VERSION}") if splash else None
        theme.set_size(self, 1200, 760, 980, 640)
        self.update_info = None  # the newer release, once a check has found one
        self.config_data = core.load_config()
        if self.config_data["window_geometry"]:
            try:
                self.geometry(self.config_data["window_geometry"])
            except tk.TclError:
                pass
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.moves = {}  # preview row id -> planned move
        for category in self.config_data["categories"]:
            theme.tile(group=Path(category["folder"]).name)  # fixes each folder's tile colour, in settings order

        self.sidebar = theme.Sidebar(self, core.APP_NAME, self.show_page)
        self.sidebar.pack(side="left", fill="y")
        main = ttk.Frame(self)
        main.pack(side="left", fill="both", expand=True)
        self.build_status_bar(main)
        self.pages = ttk.Frame(main)
        self.pages.pack(fill="both", expand=True)
        self.pages.rowconfigure(0, weight=1)
        self.pages.columnconfigure(0, weight=1)
        self.page_frames = {}
        for key, glyph, title, build in (
            ("preview", "", "Preview", self.build_preview_tab),
            ("duplicates", "", "Duplicates", self.build_duplicates_tab),
            ("cleaner", "\uE74D", "Cleaner", self.build_cleaner_tab),
            ("booster", "\uE945", "Booster", self.build_booster_tab),
            ("history", "", "History", self.build_history_tab),
            ("settings", "", "Settings", self.build_settings_tab),
            ("about", "", "About", self.build_about_tab),
        ):
            page = ttk.Frame(self.pages, padding=(theme.px(22), theme.px(16), theme.px(22), 0))
            page.grid(row=0, column=0, sticky="nsew")
            ttk.Label(page, text=title, style="Title.TLabel").pack(anchor="w", pady=(0, theme.px(10)))
            build(page).pack(fill="both", expand=True)
            self.page_frames[key] = page
            self.sidebar.add(key, glyph, title)

        # Shown across the top only when a newer version exists.
        self.banner = ttk.Frame(main, padding=(theme.px(22), theme.px(10)))
        self.banner_label = ttk.Label(self.banner)
        self.banner_label.pack(side="left")
        ttk.Button(self.banner, text="Later", command=self.banner.pack_forget).pack(side="right")
        ttk.Button(self.banner, text="Update now", style=theme.accent(),
                   command=self.install_update).pack(side="right", padx=6)

        self.refresh_preview()
        self.refresh_background_status(repeat=True)
        self.show_page("preview")
        self.after(1500, self.check_updates)
        if splash_card:
            def reveal():
                splash_card.destroy()
                self.deiconify()
                theme.dark_titlebar(self)
            self.after(1300, reveal)

    # --- About page and updates ---

    def build_about_tab(self, parent):
        tab = ttk.Frame(parent)
        head = ttk.Frame(tab)
        head.pack(fill="x", pady=(theme.px(6), theme.px(14)))
        ttk.Label(head, image=theme.app_icon(72)).pack(side="left", padx=(0, theme.px(18)))
        text = ttk.Frame(head)
        text.pack(side="left")
        ttk.Label(text, text=core.APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(text, text=f"Version {core.VERSION}  ·  MIT License", foreground="gray").pack(anchor="w")
        ttk.Label(tab, wraplength=theme.px(620), justify="left", text=(
            "Keeps your Downloads folder tidy by moving old files into category folders, "
            "automatically or only when you say so. Every change is logged and can be undone."
        )).pack(anchor="w")
        links = ttk.Frame(tab)
        links.pack(anchor="w", pady=theme.px(14))
        ttk.Button(links, text="GitHub page", command=lambda: webbrowser.open(
            f"https://github.com/{core.GITHUB_REPO}")).pack(side="left")
        ttk.Button(links, text="Open settings and log folder", command=self.open_data_folder).pack(side="left", padx=6)

        ttk.Separator(tab).pack(fill="x", pady=theme.px(8))
        ttk.Label(tab, text="Updates", style="Title.TLabel").pack(anchor="w", pady=(theme.px(6), theme.px(6)))
        self.update_status = ttk.Label(tab, text="Not checked yet.")
        self.update_status.pack(anchor="w")
        buttons = ttk.Frame(tab)
        buttons.pack(anchor="w", pady=theme.px(10))
        self.check_button = ttk.Button(buttons, text="Check for updates", command=self.check_updates)
        self.check_button.pack(side="left")
        self.update_button = ttk.Button(buttons, text="Update now", style=theme.accent(),
                                        command=self.install_update, state="disabled")
        self.update_button.pack(side="left", padx=6)
        self.auto_update = tk.BooleanVar(value=self.config_data["auto_update"])
        ttk.Checkbutton(tab, text="Install new versions automatically", variable=self.auto_update,
                        style=theme.switch(),
                        command=lambda: self.update_config(auto_update=self.auto_update.get())).pack(anchor="w")
        ttk.Label(tab, foreground="gray", wraplength=theme.px(620), justify="left", text=(
            "Off: you get a notification and choose when to update. On: while automatic sorting is running, "
            "new versions install by themselves when no Downloads Sorter window is open."
        )).pack(anchor="w", pady=(theme.px(4), 0))
        return tab

    def open_data_folder(self):
        core.DATA_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(core.DATA_DIR)

    def check_updates(self):
        self.check_button.config(state="disabled")
        self.update_status.config(text="Checking for updates…")
        result = []
        # The network call runs off the window's thread so the window never freezes.
        thread = threading.Thread(target=lambda: result.append(core.check_for_update()), daemon=True)
        thread.start()

        def done():
            if thread.is_alive():
                self.after(200, done)
                return
            self.check_button.config(state="normal")
            self.update_info = result[0] if result else None
            if self.update_info:
                message = f"Version {self.update_info['version']} is available (you have {core.VERSION})."
                self.banner_label.config(text=message)
                self.banner.pack(side="top", fill="x", before=self.pages)
                self.update_button.config(state="normal")
            else:
                message = f"No newer version found. You have version {core.VERSION}."
            self.update_status.config(text=message)

        done()

    def install_update(self):
        update = self.update_info
        if not update:
            return
        if not core.is_installed():  # run from source: nothing to replace, so show the release page
            webbrowser.open(update["page"])
            return
        if not messagebox.askyesno("Update", f"Download and install version {update['version']} now?\n\n"
                                   f"{core.APP_NAME} will close and reopen by itself."):
            return
        self.update_button.config(state="disabled")
        self.banner.pack_forget()
        self.update_status.config(text=f"Downloading version {update['version']}…")
        result = []

        def download():
            try:
                result.append(core.download_update(update))
            except OSError as error:
                result.append(error)

        thread = threading.Thread(target=download, daemon=True)
        thread.start()

        def done():
            if thread.is_alive():
                self.after(300, done)
            elif isinstance(result[0], OSError):
                self.update_button.config(state="normal")
                self.update_status.config(text=f"The download failed: {result[0]}")
            else:
                core.apply_update(result[0], reopen=True)
                self.close()  # the installer needs every window closed

        done()

    def close(self):
        self.save_duplicates_settings()
        self.update_config(window_geometry=self.geometry())
        self.destroy()

    def show_page(self, key):
        self.page_frames[key].tkraise()
        self.sidebar.select(key)
        if key == "history":
            self.refresh_history()  # background runs change it while the window is open

    def update_config(self, **changes):
        """Change settings on top of what is on disk, since the tray menu writes there too."""
        config = core.load_config()
        config.update(changes)
        core.save_config(config)
        self.config_data = config

    # --- Preview tab ---

    def build_preview_tab(self, parent):
        tab = ttk.Frame(parent)
        top = ttk.Frame(tab)
        top.pack(fill="x")
        ttk.Button(top, text="Refresh", command=self.refresh_preview).pack(side="left")
        self.summary = ttk.Label(top)
        self.summary.pack(side="left", padx=10)
        # Off: only files old enough to move. On: every file that has a destination,
        # so the user can pick new ones to sort by hand.
        self.show_all = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Show all files (ignore age)", variable=self.show_all,
                        style=theme.switch(), command=self.refresh_preview).pack(side="right")

        table = ttk.Frame(tab)
        table.pack(fill="both", expand=True, pady=8)
        self.tree = add_scrolled_tree(table, (
            ("root", "In", 120, "w"), ("age", "Age (days)", 100, "center"),
            ("size", "Size", 100, "center"), ("destination", "Goes to", 220, "w"),
        ), first=("File", 380), selectmode="extended")
        self.tree.bind("<Delete>", lambda _: self.exclude_selected())
        attach_file_menu(self.tree, lambda row: self.moves[row]["source"], self.refresh_preview,
                         extra=[("Move only the selected file(s) now", lambda _: self.move_selected()),
                                ("Never move this file", self.never_move)])

        bottom = ttk.Frame(tab)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Exclude selected", command=self.exclude_selected).pack(side="left")
        ttk.Button(bottom, text="Undo last move", command=self.undo).pack(side="left", padx=6)
        self.move_button = ttk.Button(bottom, text="Move files", style=theme.accent(), command=self.move)
        self.move_button.pack(side="right")
        ttk.Button(bottom, text="Move selected", command=self.move_selected).pack(side="right", padx=(6, 6))
        ttk.Button(bottom, text="Sort ALL files now (ignore age)", command=self.sort_all_now).pack(side="right")
        return tab

    def refresh_preview(self):
        self.tree.delete(*self.tree.get_children())
        self.moves.clear()
        for move in core.plan_moves(self.config_data, everything=self.show_all.get()):
            try:
                destination = move["folder"].relative_to(move["root"])
            except ValueError:
                destination = move["folder"]
            row = self.tree.insert(
                "", "end", text=move["source"].name,
                image=theme.tile(move["source"].suffix.lstrip("."), move["folder"].name),
                values=(move["root"].name, f"{move['age']:.0f}", format_size(move["size"]), destination))
            self.moves[row] = move
        self.update_summary()
        self.refresh_history()

    def update_summary(self):
        count = len(self.moves)
        size = format_size(sum(move["size"] for move in self.moves.values()))
        if self.show_all.get():
            text = f"{count} file(s) of any age ({size}): select the ones to sort" if count else "No files to sort"
        else:
            text = f"{count} file(s) ready to move ({size})" if count else "Nothing to move: no files are old enough yet"
        self.summary.config(text=text)
        self.move_button.config(text=f"Move {count} file(s)", state="normal" if count else "disabled")

    def exclude_selected(self):
        for row in self.tree.selection():
            self.tree.delete(row)
            self.moves.pop(row, None)
        self.update_summary()

    def never_move(self, path):
        self.update_config(ignore=self.config_data["ignore"] + [path.name])
        self.ignore_var.set(", ".join(self.config_data["ignore"]))
        self.refresh_preview()

    def move(self):
        if not messagebox.askyesno("Move files", f"Move the {len(self.moves)} listed file(s)?"):
            return
        count, errors = core.move_files(list(self.moves.values()))
        self.refresh_preview()
        report_result(self, f"Moved {count} file(s).", errors)

    def move_selected(self):
        """Move just the highlighted preview rows and leave the rest for later."""
        moves = [self.moves[row] for row in self.tree.selection() if row in self.moves]
        if not moves:
            messagebox.showinfo("Move selected", "Select one or more files in the list first "
                                "(Ctrl or Shift for several).")
            return
        if not messagebox.askyesno("Move files", f"Move only the {len(moves)} selected file(s)?"):
            return
        count, errors = core.move_files(moves)
        self.refresh_preview()
        report_result(self, f"Moved {count} file(s).", errors)

    def sort_folder_now(self, index):
        """Sort one of the folders from Settings right away, by the usual rules."""
        folder = self.folder_values[index]
        name = folder or str(core.detect_downloads_folder())
        moves = core.plan_moves(dict(self.config_data, folders=[folder]))
        if not moves:
            messagebox.showinfo("Sort folder", f"Nothing to sort in\n{name}\n\nNo files there are old enough yet.")
            return
        if not messagebox.askyesno("Sort folder", f"Move {len(moves)} file(s) in\n{name}\ninto their category folders?"):
            return
        count, errors = core.move_files(moves)
        self.refresh_preview()
        report_result(self, f"Moved {count} file(s).", errors)

    def sort_all_now(self):
        """Move every file that has a destination, however new it is."""
        moves = core.plan_moves(self.config_data, everything=True)
        if not moves:
            messagebox.showinfo("Sort all", "There are no files to sort.")
            return
        if not messagebox.askyesno(
                "Sort all", f"Move all {len(moves)} file(s) now, including new ones and ones you put back "
                "with Undo?\n\nFiles on the never-move list stay. You can undo this from History."):
            return
        count, errors = core.move_files(moves)
        self.refresh_preview()
        report_result(self, f"Moved {count} file(s).", errors)

    def undo(self):
        run = core.last_active_run()
        if not run:
            messagebox.showinfo("Undo", "There is no move to undo.")
            return
        remaining = sum(map(core.is_active, run["moves"]))
        if not messagebox.askyesno("Undo", f"Put back the {remaining} file(s) moved on {run['time']}?"):
            return
        count, errors = core.undo_last(run["time"])
        self.refresh_preview()
        report_result(self, f"Restored {count} file(s).", errors)

    # --- Duplicates tab ---

    def build_duplicates_tab(self, parent):
        settings = self.config_data["duplicates"]
        tab = ttk.Frame(parent)
        top = ttk.Frame(tab)
        top.pack(fill="x")
        self.scan_button = ttk.Button(top, text="Scan", style=theme.accent(), command=self.scan_duplicates)
        self.scan_button.pack(side="left")
        self.stop_button = ttk.Button(top, text="Stop", command=self.stop_duplicates_scan, state="disabled")
        self.stop_button.pack(side="left", padx=6)
        self.duplicates_summary = ttk.Label(top, text="Choose where to look and how to compare, then click Scan.")
        self.duplicates_summary.pack(side="left", padx=10)
        self.duplicates_progress = ttk.Progressbar(top, mode="indeterminate", length=theme.px(160))

        options = ttk.Frame(tab)
        options.pack(fill="x", pady=(theme.px(10), 0))
        options.columnconfigure(2, weight=1)
        self.dup_source = tk.StringVar(value=settings["source"])
        self.dup_folder = tk.StringVar(value=settings["folder"])
        self.dup_recursive = tk.BooleanVar(value=settings["recursive"])
        self.dup_check_folder = tk.StringVar(value=settings["check_folder"])
        self.dup_check_subfolders = tk.BooleanVar(value=settings["check_subfolders"])
        ttk.Label(options, text="Look in").grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Radiobutton(options, text="The sorted folders", value="sorted", variable=self.dup_source).grid(
            row=0, column=1, sticky="w")
        ttk.Checkbutton(options, text="Include subfolders", variable=self.dup_recursive, style=theme.switch()).grid(
            row=0, column=3, sticky="e")
        ttk.Radiobutton(options, text="This folder:", value="folder", variable=self.dup_source).grid(
            row=1, column=1, sticky="w", pady=(4, 0))
        folder_row = ttk.Frame(options)
        folder_row.grid(row=1, column=2, columnspan=2, sticky="ew", pady=(4, 0))
        folder_entry = ttk.Entry(folder_row, textvariable=self.dup_folder)
        folder_entry.pack(side="left", fill="x", expand=True)
        folder_entry.bind("<FocusIn>", lambda _: self.dup_source.set("folder"))
        ttk.Button(folder_row, text="Browse…", command=self.browse_duplicates_folder).pack(side="left", padx=(6, 0))

        ttk.Label(options, text="Match by").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=(8, 0))
        self.dup_mode = ttk.Combobox(options, state="readonly", values=list(duplicates.MODES.values()), width=32)
        self.dup_mode.set(duplicates.MODES.get(settings["mode"], duplicates.MODES["content"]))
        self.dup_mode.grid(row=2, column=1, columnspan=2, sticky="w", pady=(8, 0))

        ttk.Label(options, text="Show only").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=(8, 0))
        filters = ttk.Frame(options)
        filters.grid(row=3, column=1, columnspan=3, sticky="w", pady=(8, 0))
        self.dup_extension = tk.StringVar(value=settings["extension"])
        self.dup_name = tk.StringVar(value=settings["name"])
        self.dup_min_mb = tk.StringVar(value=settings["min_mb"])
        for label, variable, width in (("Extension", self.dup_extension, 8), ("Name contains", self.dup_name, 22),
                                       ("At least (MB)", self.dup_min_mb, 7)):
            ttk.Label(filters, text=label).pack(side="left", padx=(0, 4))
            entry = ttk.Entry(filters, textvariable=variable, width=width)
            entry.pack(side="left", padx=(0, 12))
            entry.bind("<Return>", lambda _: self.apply_duplicates_filter())
        ttk.Button(filters, text="Apply", command=self.apply_duplicates_filter).pack(side="left")
        ttk.Button(filters, text="Clear", command=self.clear_duplicates_filter).pack(side="left", padx=6)

        ttk.Label(options, text="Check in").grid(row=4, column=0, sticky="w", padx=(0, 12), pady=(8, 0))
        check_row = ttk.Frame(options)
        check_row.grid(row=4, column=1, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Entry(check_row, textvariable=self.dup_check_folder).pack(side="left", fill="x", expand=True)
        ttk.Button(check_row, text="Browse…", command=self.browse_check_folder).pack(side="left", padx=6)
        ttk.Button(check_row, text="Use scan folder",
                   command=lambda: self.dup_check_folder.set(self.dup_folder.get())).pack(side="left")
        # On a row of their own so they stay visible when the window is narrow.
        check_actions = ttk.Frame(options)
        check_actions.grid(row=5, column=1, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Button(check_actions, text="Check copies in this folder", command=self.check_duplicates_in_folder).pack(
            side="left")
        ttk.Checkbutton(check_actions, text="Include subfolders", variable=self.dup_check_subfolders,
                        style=theme.switch()).pack(side="left", padx=12)

        # Packed before the table so the table, not these buttons, shrinks in a small window.
        bottom = ttk.Frame(tab)
        bottom.pack(side="bottom", fill="x")
        table = ttk.Frame(tab)
        table.pack(fill="both", expand=True, pady=8)
        self.duplicates_tree = add_scrolled_tree(table, (
            ("size", "Size", 90, "center"), ("modified", "Modified", 140, "center"), ("folder", "Folder", 160, "w"),
            ("path", "Full path", 420, "w"),
        ), first=("File", 380), selectmode="extended")
        self.duplicates_tree.tag_configure("group", foreground=theme.MUTED)
        self.duplicates_tree.bind("<Button-1>", self.on_duplicates_click)
        self.duplicates_tree.bind("<space>", lambda _: self.toggle_duplicates(self.duplicates_tree.selection()))
        self.duplicates_tree.bind("<Button-3>", self.duplicates_popup)
        self.duplicates_tree.bind("<Double-1>", self.on_duplicates_double_click)
        self.dup_groups = []  # every group the last scan found, minus files deleted or removed since
        self.dup_shown = []  # the groups that pass the filter, as listed
        self.dup_rows = {}  # file row id -> duplicates.Entry
        self.dup_group_rows = {}  # group row id -> duplicates.Group
        self.dup_checked = set()  # core.norm(path) of every checked file
        self.dup_thread = None
        self.dup_cancel = threading.Event()
        self.dup_save_job = None
        for variable in (self.dup_source, self.dup_folder, self.dup_recursive, self.dup_extension, self.dup_name,
                         self.dup_min_mb, self.dup_check_folder, self.dup_check_subfolders):
            variable.trace_add("write", lambda *_: self.save_duplicates_settings_soon())
        self.dup_mode.bind("<<ComboboxSelected>>", lambda _: self.save_duplicates_settings_soon())

        check = ttk.Menubutton(bottom, text="Check…")
        menu = tk.Menu(check, tearoff=0)
        theme.style_menu(menu)
        check["menu"] = menu
        for label, command in (
                ("Check all", lambda: self.check_duplicates_by(lambda files: files)),
                ("Uncheck all", lambda: self.check_duplicates_by(lambda files: [])),
                ("Invert", self.invert_duplicates),
                (None, None),
                ("All but the first in each group", lambda: self.check_duplicates_by(lambda files: files[1:])),
                ("All but the newest in each group", lambda: self.check_duplicates_by(
                    lambda files: sorted(files, key=lambda e: e.modified, reverse=True)[1:])),
                ("The biggest in each group", lambda: self.check_duplicates_by(
                    lambda files: [e for e in files if e.size == max(f.size for f in files)])),
                ("The smallest in each group", lambda: self.check_duplicates_by(
                    lambda files: [e for e in files if e.size == min(f.size for f in files)])),
                ("Extra copies in the same folder (keep 1 per folder)", self.check_same_folder_duplicates),
                ('Every copy inside the "Check in" folder', self.check_duplicates_in_folder),
                (None, None),
                ("Highlighted rows", lambda: self.set_duplicates_checked(self.duplicates_tree.selection(), True))):
            if label:
                menu.add_command(label=label, command=command)
            else:
                menu.add_separator()
        check.pack(side="left")
        self.delete_duplicates_button = ttk.Button(
            bottom, text="Delete checked", command=self.delete_checked_duplicates, state="disabled")
        self.delete_duplicates_button.pack(side="right")
        ttk.Button(bottom, text="Keep first, delete the rest", command=lambda: self.delete_duplicate_entries(
            [e for group in self.dup_shown for e in group.files[1:]])).pack(side="right", padx=6)
        ttk.Button(bottom, text="Keep newest, delete the rest", command=lambda: self.delete_duplicate_entries(
            [e for group in self.dup_shown
             for e in sorted(group.files, key=lambda e: e.modified, reverse=True)[1:]])).pack(side="right")
        return tab

    def browse_duplicates_folder(self):
        folder = filedialog.askdirectory(title="Folder to look for duplicates in",
                                         initialdir=self.dup_folder.get() or None)
        if folder:
            self.dup_folder.set(str(Path(folder)))
            self.dup_source.set("folder")

    def browse_check_folder(self):
        folder = filedialog.askdirectory(title="Folder whose copies to check",
                                         initialdir=self.dup_check_folder.get() or self.dup_folder.get() or None)
        if folder:
            self.dup_check_folder.set(str(Path(folder)))

    def duplicates_mode(self):
        return next(key for key, label in duplicates.MODES.items() if label == self.dup_mode.get())

    def save_duplicates_settings_soon(self):
        """Save shortly after the last change, not on every key press."""
        if self.dup_save_job:
            self.after_cancel(self.dup_save_job)
        self.dup_save_job = self.after(800, self.save_duplicates_settings)

    def save_duplicates_settings(self):
        if self.dup_save_job:
            self.after_cancel(self.dup_save_job)
            self.dup_save_job = None
        self.update_config(duplicates={
            "source": self.dup_source.get(), "folder": self.dup_folder.get().strip().strip('"'),
            "recursive": self.dup_recursive.get(), "mode": self.duplicates_mode(),
            "extension": self.dup_extension.get().strip(), "name": self.dup_name.get().strip(),
            "min_mb": self.dup_min_mb.get().strip(), "check_folder": self.dup_check_folder.get().strip().strip('"'),
            "check_subfolders": self.dup_check_subfolders.get()})

    def scan_duplicates(self):
        if self.dup_thread and self.dup_thread.is_alive():
            return
        if self.dup_source.get() == "folder":
            folder = Path(self.dup_folder.get().strip().strip('"'))
            if not self.dup_folder.get().strip() or not folder.is_dir():
                messagebox.showwarning("Duplicates", "Choose the folder to look in first.", parent=self)
                return
            folders = [folder]
        else:
            folders = duplicates.sorted_folders(self.config_data)
        self.save_duplicates_settings()
        mode, recursive = self.duplicates_mode(), self.dup_recursive.get()
        self.dup_groups = []
        self.render_duplicates()
        cancel = self.dup_cancel = threading.Event()
        state = {"status": "Looking for files…"}

        def work():
            try:
                files = duplicates.collect(folders, recursive, cancel)
                state["status"] = f"Comparing {len(files)} file(s)…"
                state["groups"] = duplicates.find(files, mode, cancel, lambda text: state.update(status=text))
            except duplicates.Cancelled:
                state["cancelled"] = True
            except Exception as error:  # shown to the user, not lost with the thread
                state["error"] = error

        # Hashing can take long, so it runs off the window's thread.
        self.dup_thread = threading.Thread(target=work, daemon=True)
        self.dup_thread.start()
        self.set_duplicates_scanning(True)

        def check():
            if self.dup_thread.is_alive():
                self.duplicates_summary.config(text=state["status"])
                self.after(150, check)
                return
            self.set_duplicates_scanning(False)
            if "error" in state:
                self.duplicates_summary.config(text="The scan failed.")
                messagebox.showerror("Duplicates", f"The scan failed:\n{state['error']}", parent=self)
            elif "cancelled" in state:
                self.duplicates_summary.config(text="Scan stopped.")
            else:
                self.dup_groups = state["groups"]
                # Identical content is safe to pre-check; files that only look alike are left to the user.
                self.dup_checked = {core.norm(e.path) for group in self.dup_groups for e in group.files[1:]} \
                    if mode == "content" else set()
                self.render_duplicates()

        check()

    def stop_duplicates_scan(self):
        self.dup_cancel.set()
        self.duplicates_summary.config(text="Stopping…")

    def set_duplicates_scanning(self, scanning):
        self.scan_button.config(state="disabled" if scanning else "normal")
        self.stop_button.config(state="normal" if scanning else "disabled")
        if scanning:
            self.duplicates_progress.pack(side="right")
            self.duplicates_progress.start(12)
        else:
            self.duplicates_progress.stop()
            self.duplicates_progress.pack_forget()

    def duplicates_filter(self):
        extension = duplicates.norm_text(self.dup_extension.get().strip().lstrip("."))
        needle = duplicates.norm_text(self.dup_name.get().strip())
        try:
            min_size = float(self.dup_min_mb.get().strip() or 0) * 1024 * 1024
        except ValueError:
            min_size = 0
        return lambda e: ((not extension or duplicates.norm_text(e.name).endswith("." + extension))
                          and needle in duplicates.norm_text(e.name) and e.size >= min_size)

    def apply_duplicates_filter(self):
        self.save_duplicates_settings()
        self.render_duplicates()

    def clear_duplicates_filter(self):
        for variable in (self.dup_extension, self.dup_name, self.dup_min_mb):
            variable.set("")
        self.apply_duplicates_filter()

    def render_duplicates(self):
        tree = self.duplicates_tree
        tree.delete(*tree.get_children())
        self.dup_rows.clear()
        self.dup_group_rows.clear()
        self.dup_shown = []
        passes = self.duplicates_filter()
        for group in self.dup_groups:
            files = [e for e in group.files if passes(e)]
            if len(files) < 2:
                continue  # a single file left after filtering is no longer a duplicate
            shown = duplicates.Group(group.number, files)
            self.dup_shown.append(shown)
            same_size = len({e.size for e in files}) == 1
            parent = tree.insert("", "end", open=True, tags=("group",), text=f"Group {group.number}:  {len(files)} files",
                                 values=(format_size(files[0].size) if same_size else "", "", "", ""))
            self.dup_group_rows[parent] = shown
            for entry in files:
                row = tree.insert(parent, "end", values=(
                    format_size(entry.size), time.strftime("%Y-%m-%d %H:%M", time.localtime(entry.modified)),
                    entry.path.parent.name or entry.path.parent, entry.path))
                self.dup_rows[row] = entry
                self.paint_duplicate(row)
        self.update_duplicates_summary()

    def paint_duplicate(self, row):
        entry = self.dup_rows[row]
        checked = core.norm(entry.path) in self.dup_checked
        image = theme.checkbox(checked)
        self.duplicates_tree.item(row, image=image,
                                  text=entry.name if image else f"{'☑' if checked else '☐'}  {entry.name}")

    def checked_duplicates(self):
        return [e for e in self.dup_rows.values() if core.norm(e.path) in self.dup_checked]

    def update_duplicates_summary(self):
        if not self.dup_groups:
            text = "No duplicates found." if self.dup_thread else "Choose where to look and how to compare, then click Scan."
        elif not self.dup_shown:
            text = f"{len(self.dup_groups)} group(s) found, but none match the filter."
        else:
            files = sum(len(group.files) for group in self.dup_shown)
            spare = sum(sum(e.size for e in group.files) - max(e.size for e in group.files) for group in self.dup_shown)
            text = f"{len(self.dup_shown)} group(s), {files} files, up to {format_size(spare)} to free"
        checked = self.checked_duplicates()
        if checked:
            text += f"   ·   {len(checked)} checked ({format_size(sum(e.size for e in checked))})"
        self.duplicates_summary.config(text=text)
        self.delete_duplicates_button.config(
            text=f"Delete {len(checked)} checked" if checked else "Delete checked",
            state="normal" if checked else "disabled")

    def duplicate_file_rows(self, rows):
        """File rows for a selection; a group row stands for all of its files."""
        found = []
        for row in rows:
            for file_row in self.duplicates_tree.get_children(row) if row in self.dup_group_rows else [row]:
                if file_row in self.dup_rows and file_row not in found:
                    found.append(file_row)
        return found

    def set_duplicates_checked(self, rows, checked):
        for row in self.duplicate_file_rows(rows):
            key = core.norm(self.dup_rows[row].path)
            if checked:
                self.dup_checked.add(key)
            else:
                self.dup_checked.discard(key)
            self.paint_duplicate(row)
        self.update_duplicates_summary()

    def toggle_duplicates(self, rows):
        """Check them all, or uncheck them all if they already are."""
        rows = self.duplicate_file_rows(rows)
        self.set_duplicates_checked(rows, not all(core.norm(self.dup_rows[r].path) in self.dup_checked for r in rows))

    def on_duplicates_click(self, event):
        tree = self.duplicates_tree
        row = tree.identify_row(event.y)
        if row in self.dup_rows and tree.identify_column(event.x) == "#0" and "image" in tree.identify_element(
                event.x, event.y):
            self.toggle_duplicates([row])
            return "break"  # a click on the box only ticks it, the highlight stays as it was

    def on_duplicates_double_click(self, event):
        """Like the other lists: double-clicking a file shows it in File Explorer.
        Group rows keep folding open and shut, and the tick box only ticks."""
        tree = self.duplicates_tree
        row = tree.identify_row(event.y)
        if row in self.dup_rows and "image" not in tree.identify_element(event.x, event.y):
            self.show_duplicate(self.dup_rows[row].path)
            return "break"

    def check_duplicates_by(self, pick):
        """Check the files pick(group files) returns in each listed group, and nothing else."""
        self.dup_checked = {core.norm(e.path) for group in self.dup_shown for e in pick(group.files)}
        for row in self.dup_rows:
            self.paint_duplicate(row)
        self.update_duplicates_summary()

    def invert_duplicates(self):
        self.check_duplicates_by(lambda files: [e for e in files if core.norm(e.path) not in self.dup_checked])

    def check_same_folder_duplicates(self):
        def pick(files):
            first_in_folder = {}
            for e in files:
                first_in_folder.setdefault(core.norm(e.path.parent), e)
            return [e for e in files if first_in_folder[core.norm(e.path.parent)] is not e]

        if not any(pick(group.files) for group in self.dup_shown):
            messagebox.showinfo("Duplicates", "No group has two copies in the same folder.", parent=self)
            return
        self.check_duplicates_by(pick)

    def check_duplicates_in_folder(self):
        folder = (self.dup_check_folder.get() or self.dup_folder.get()).strip().strip('"')
        if not folder:
            messagebox.showinfo("Duplicates", 'Enter a folder in "Check in", or click Use scan folder.', parent=self)
            return
        if not Path(folder).is_dir():
            messagebox.showwarning("Duplicates", f"Not a folder:\n{folder}", parent=self)
            return
        target, subfolders = core.norm(Path(folder)), self.dup_check_subfolders.get()

        def inside(e):
            parent = core.norm(e.path.parent)
            return parent == target or subfolders and parent.startswith(target.rstrip(os.sep) + os.sep)

        if not any(inside(e) for group in self.dup_shown for e in group.files):
            messagebox.showinfo("Duplicates", f"None of the listed files are in\n{Path(folder)}", parent=self)
            return
        self.check_duplicates_by(lambda files: [e for e in files if inside(e)])

    def duplicates_popup(self, event):
        tree = self.duplicates_tree
        row = tree.identify_row(event.y)
        if not row:
            return
        if row not in tree.selection():
            tree.selection_set(row)
        rows = self.duplicate_file_rows(tree.selection())
        entries = [self.dup_rows[r] for r in rows]
        if not entries:
            return
        checked = all(core.norm(e.path) in self.dup_checked for e in entries)
        menu = tk.Menu(tree, tearoff=0)
        theme.style_menu(menu)
        menu.add_command(label="Uncheck" if checked else "Check",
                         command=lambda: self.set_duplicates_checked(rows, not checked))
        menu.add_separator()
        menu.add_command(label="Show in File Explorer", command=lambda: self.show_duplicate(entries[0].path))
        menu.add_command(label="Open / Run", command=lambda: self.open_duplicates(entries))
        menu.add_separator()
        menu.add_command(label="Remove from this list (keeps the file)",
                         command=lambda: self.forget_duplicates({core.norm(e.path) for e in entries}))
        menu.add_command(label="Delete…", command=lambda: self.delete_duplicate_entries(entries))
        menu.tk_popup(event.x_root, event.y_root)

    def show_duplicate(self, path):
        if error := duplicates.reveal(path):
            messagebox.showwarning("File", error, parent=self)

    def open_duplicates(self, entries):
        errors = [error for entry in entries if (error := duplicates.open_file(entry.path))]
        if errors:
            messagebox.showwarning("Open", "Could not open:\n" + "\n".join(errors[:8]), parent=self)

    def forget_duplicates(self, keys):
        """Take files off the list (deleted, or the user removed them); groups left with one file go."""
        for group in self.dup_groups:
            group.files = [e for e in group.files if core.norm(e.path) not in keys]
        self.dup_groups = [group for group in self.dup_groups if len(group.files) > 1]
        self.dup_checked -= keys
        self.render_duplicates()

    def delete_checked_duplicates(self):
        self.delete_duplicate_entries(self.checked_duplicates())

    def delete_duplicate_entries(self, entries):
        if not entries:
            messagebox.showinfo("Duplicates", "There is nothing to delete. Check one or more files first "
                                "(click the box next to a file, or use Check…).", parent=self)
            return
        doomed = {core.norm(e.path) for e in entries}
        # Count against the whole group, filtered-out copies included: those would survive.
        emptied = sum(all(core.norm(e.path) in doomed for e in group.files) for group in self.dup_groups)
        listing = "\n".join(e.name for e in entries[:12]) + (f"\n… and {len(entries) - 12} more" if len(entries) > 12 else "")
        warning = (f"\n\nWARNING: in {emptied} group(s) every copy is selected, so no copy of those files "
                   "will be left." if emptied else "")
        how = ask_delete_how(self, f"Delete {len(entries)} file(s) ({format_size(sum(e.size for e in entries))})?"
                             f"\n\n{listing}{warning}")
        if how is None:
            return
        permanent = how == "permanent"
        if permanent and not messagebox.askyesno(
                "Delete for good", f"The {len(entries)} file(s) will be gone for good: they won't go to the "
                "Recycle Bin and History can't bring them back.\n\nDelete them?", icon="warning", parent=self):
            return
        count, errors = core.delete_files([e.path for e in entries], permanent=permanent)
        self.forget_duplicates({core.norm(e.path) for e in entries if not e.path.exists()})
        self.refresh_preview()
        report_result(self, f"Deleted {count} file(s) for good." if permanent else
                      f"Sent {count} file(s) to the Recycle Bin. You can bring them back from History.", errors)

    # --- Cleaner tab ---

    def build_cleaner_tab(self, parent):
        tab = ttk.Frame(parent)
        top = ttk.Frame(tab)
        top.pack(fill="x")
        self.clean_scan_button = ttk.Button(top, text="Scan", style=theme.accent(), command=self.scan_cleaner)
        self.clean_scan_button.pack(side="left")
        self.clean_stop_button = ttk.Button(top, text="Stop", command=lambda: self.clean_cancel.set(), state="disabled")
        self.clean_stop_button.pack(side="left", padx=6)
        self.clean_summary = ttk.Label(top, text="Tick what to look for, then click Scan. Nothing is deleted until "
                                       "you click Clean.")
        self.clean_summary.pack(side="left", padx=10)
        self.clean_progress = ttk.Progressbar(top, mode="indeterminate", length=theme.px(160))

        # Packed before the table so the table, not these buttons, shrinks in a small window.
        bottom = ttk.Frame(tab)
        bottom.pack(side="bottom", fill="x")
        self.clean_button = ttk.Button(bottom, text="Clean checked", style=theme.accent(),
                                       command=self.clean_checked, state="disabled")
        self.clean_button.pack(side="right")
        ttk.Label(bottom, text=f"Only files left untouched for {cleaner.MIN_AGE_HOURS} hours are included. "
                  "Everything cleaned is listed in History.", style="Muted.TLabel").pack(side="left")

        table = ttk.Frame(tab)
        table.pack(fill="both", expand=True, pady=8)
        self.cleaner_tree = add_scrolled_tree(table, (
            ("files", "Files", 70, "center"), ("size", "Size", 90, "center"), ("about", "About", 520, "w"),
        ), first=("What to clean", 230), selectmode="browse")
        self.cleaner_tree.bind("<Button-1>", self.on_cleaner_click)
        self.cleaner_tree.bind("<space>", lambda _: self.toggle_cleaner(self.cleaner_tree.selection()))
        self.cleaner_tree.bind("<Double-1>", self.open_cleaner_folder)
        saved = self.config_data["cleaner"]["categories"]
        self.clean_checked_keys = set(saved if saved is not None else
                                      [c.key for c in cleaner.CATEGORIES if c.checked])
        self.clean_found = {}  # category key -> cleaner.Found from the last scan
        self.clean_thread = None
        self.clean_cancel = threading.Event()
        for category in cleaner.CATEGORIES:
            self.cleaner_tree.insert("", "end", iid=category.key, text=category.label)
            self.paint_cleaner(category.key)
        return tab

    def paint_cleaner(self, key):
        found = self.clean_found.get(key)
        self.cleaner_tree.item(key, image=theme.checkbox(key in self.clean_checked_keys), values=(
            len(found.files) if found else "", format_size(found.size) if found else "",
            cleaner.BY_KEY[key].description))

    def on_cleaner_click(self, event):
        tree = self.cleaner_tree
        row = tree.identify_row(event.y)
        if row and tree.identify_column(event.x) == "#0" and "image" in tree.identify_element(event.x, event.y):
            self.toggle_cleaner([row])
            return "break"

    def toggle_cleaner(self, rows):
        for key in rows:
            self.clean_checked_keys ^= {key}
            self.paint_cleaner(key)
        self.update_config(cleaner={"categories": sorted(self.clean_checked_keys)})
        self.update_cleaner_summary()

    def open_cleaner_folder(self, event):
        found = self.clean_found.get(self.cleaner_tree.identify_row(event.y))
        if found and found.folders:
            os.startfile(found.folders[0])

    def chosen_cleaner_results(self):
        return [found for key, found in self.clean_found.items() if key in self.clean_checked_keys]

    def update_cleaner_summary(self):
        if not self.clean_found:
            return
        chosen = self.chosen_cleaner_results()
        count, size = sum(len(f.files) for f in chosen), sum(f.size for f in chosen)
        self.clean_summary.config(text=f"{count} file(s), {format_size(size)} can be cleaned." if count
                                  else "Nothing to clean in the ticked items.")
        self.clean_button.config(state="normal" if count else "disabled")

    def set_cleaner_busy(self, busy, mode="indeterminate"):
        self.clean_scan_button.config(state="disabled" if busy else "normal")
        self.clean_stop_button.config(state="normal" if busy else "disabled")
        if busy:
            self.clean_button.config(state="disabled")
            self.clean_progress.config(mode=mode, value=0)
            self.clean_progress.pack(side="right")
            if mode == "indeterminate":
                self.clean_progress.start(12)
        else:
            self.clean_progress.stop()
            self.clean_progress.pack_forget()

    def run_cleaner_job(self, work, finish, state):
        """Run work(state) off the window's thread, showing state["status"], then finish(state)."""
        self.clean_cancel = state["cancel"] = threading.Event()

        def guarded():
            try:
                work(state)
            except cleaner.Cancelled:
                state["cancelled"] = True
            except Exception as error:  # shown to the user, not lost with the thread
                state["error"] = error

        self.clean_thread = threading.Thread(target=guarded, daemon=True)
        self.clean_thread.start()

        def check():
            if self.clean_thread.is_alive():
                self.clean_summary.config(text=state.get("status", ""))
                if "fraction" in state:
                    self.clean_progress.config(value=state["fraction"] * 100)
                self.after(150, check)
                return
            self.set_cleaner_busy(False)
            if "error" in state:
                self.clean_summary.config(text="Something went wrong.")
                messagebox.showerror("Cleaner", str(state["error"]), parent=self)
            else:
                finish(state)

        check()

    def scan_cleaner(self):
        if self.clean_thread and self.clean_thread.is_alive():
            return
        keys = [c.key for c in cleaner.CATEGORIES if c.key in self.clean_checked_keys]
        if not keys:
            messagebox.showinfo("Cleaner", "Tick at least one item to look for.", parent=self)
            return
        self.clean_found = {}
        for category in cleaner.CATEGORIES:
            self.paint_cleaner(category.key)
        self.set_cleaner_busy(True)

        def work(state):
            state["found"] = cleaner.scan(keys, state["cancel"], lambda text: state.update(status=text))

        def finish(state):
            if state.get("cancelled"):
                self.clean_summary.config(text="Scan stopped.")
                return
            self.clean_found = {found.category.key: found for found in state["found"]}
            for key in self.clean_found:
                self.paint_cleaner(key)
            self.update_cleaner_summary()

        self.run_cleaner_job(work, finish, {"status": "Looking for junk files…"})

    def clean_checked(self):
        chosen = self.chosen_cleaner_results()
        paths = [path for found in chosen for path in found.files]
        if not paths:
            return
        how = ask_delete_how(self, f"Clean {len(paths)} file(s) ({format_size(sum(f.size for f in chosen))})?\n\n"
                             "Files a program is using are skipped. Deleting for good frees the space now; "
                             "the Recycle Bin holds on to it until it is emptied.")
        if how is None:
            return
        sizes = {}
        for path in paths:
            try:
                sizes[path] = path.stat().st_size
            except OSError:
                sizes[path] = 0
        roots = [folder for found in chosen for folder in found.folders]
        self.set_cleaner_busy(True, mode="determinate")

        def work(state):
            def progress(done, count):
                state.update(status=f"Cleaning {done} of {count}…", fraction=done / count)
            state["result"] = core.delete_files(paths, permanent=how == "permanent", progress=progress,
                                                cancel=state["cancel"])
            cleaner.remove_empty_folders(roots)

        def finish(state):
            count, errors = state["result"]
            gone = {path for path in paths if not path.exists()}
            for found in self.clean_found.values():
                found.files = [path for path in found.files if path not in gone]
                found.size = sum(sizes.get(path, 0) for path in found.files)
                self.paint_cleaner(found.category.key)
            self.update_cleaner_summary()
            self.refresh_preview()
            where = "deleted for good" if how == "permanent" else "sent to the Recycle Bin"
            message = f"Cleaned {count} file(s), {format_size(sum(sizes[p] for p in gone))} {where}. " \
                      "They are listed in History."
            if state["cancel"].is_set():
                message += " Stopped before the end."
            if errors:
                message += f"\n\n{len(errors)} file(s) were skipped because a program is using them " \
                           "or they need administrator rights."
            messagebox.showinfo("Cleaner", message, parent=self)

        self.run_cleaner_job(work, finish, {"status": "Cleaning…"})

    # --- Booster tab ---

    def build_booster_tab(self, parent):
        tab = ttk.Frame(parent)
        self.boost_memory = ttk.Label(tab)
        self.boost_memory.pack(anchor="w")
        notebook = ttk.Notebook(tab)
        notebook.pack(fill="both", expand=True, pady=(theme.px(8), 0))

        # Startup apps: fewer of them means a faster sign-in and less running in the background.
        startup = ttk.Frame(notebook, padding=theme.px(10))
        notebook.add(startup, text="Startup apps")
        bar = ttk.Frame(startup)
        bar.pack(side="bottom", fill="x")
        ttk.Button(bar, text="Refresh", command=self.refresh_startup).pack(side="left")
        ttk.Button(bar, text="Turn on", command=lambda: self.set_startup_selected(True)).pack(side="right")
        ttk.Button(bar, text="Turn off", style=theme.accent(),
                   command=lambda: self.set_startup_selected(False)).pack(side="right", padx=6)
        self.startup_summary = ttk.Label(bar, style="Muted.TLabel")
        self.startup_summary.pack(side="left", padx=10)
        table = ttk.Frame(startup)
        table.pack(fill="both", expand=True, pady=(0, 8))
        self.startup_tree = add_scrolled_tree(table, (
            ("status", "Status", 70, "w"), ("where", "Where", 190, "w"), ("command", "Command", 420, "w"),
        ), first=("App", 240), selectmode="extended")
        self.startup_tree.tag_configure("off", foreground=theme.MUTED)
        self.startup_tree.bind("<Double-1>", lambda _: self.set_startup_selected(None))
        self.startup_rows = {}

        # Programs: the biggest memory users, which can be ended to free memory.
        programs = ttk.Frame(notebook, padding=theme.px(10))
        notebook.add(programs, text="Running programs")
        bar = ttk.Frame(programs)
        bar.pack(side="bottom", fill="x")
        ttk.Button(bar, text="Refresh", command=self.refresh_programs).pack(side="left")
        ttk.Button(bar, text="End selected", style=theme.accent(), command=self.end_selected_programs).pack(side="right")
        ttk.Label(bar, text="Save your work first: ending a program closes it without asking.",
                  style="Muted.TLabel").pack(side="left", padx=10)
        table = ttk.Frame(programs)
        table.pack(fill="both", expand=True, pady=(0, 8))
        self.programs_tree = add_scrolled_tree(table, (
            ("copies", "Copies", 80, "e"), ("memory", "Memory", 110, "e"), ("note", "", 300, "w"),
        ), first=("Program", 280), selectmode="extended")
        self.programs_tree.tag_configure("protected", foreground=theme.MUTED)
        self.program_rows = {}

        # Power plan.
        power = ttk.Frame(notebook, padding=theme.px(14))
        notebook.add(power, text="Power plan")
        ttk.Label(power, text="High performance keeps the processor at full speed: faster, but it uses more "
                  "power. Balanced saves power while the PC is idle.", wraplength=theme.px(640),
                  justify="left").pack(anchor="w")
        self.power_choice = tk.StringVar()
        self.power_plans = {}
        self.power_list = ttk.Frame(power)
        self.power_list.pack(anchor="w", pady=theme.px(10))
        buttons = ttk.Frame(power)
        buttons.pack(anchor="w")
        ttk.Button(buttons, text="Use this plan", style=theme.accent(), command=self.apply_power_plan).pack(side="left")
        ttk.Button(buttons, text="Refresh", command=self.refresh_power).pack(side="left", padx=6)

        notebook.bind("<<NotebookTabChanged>>", lambda _: self.refresh_memory())
        self.after(200, self.refresh_booster)
        return tab

    def refresh_booster(self):
        self.refresh_startup()
        self.refresh_programs()
        self.refresh_power()

    def refresh_memory(self):
        total, available = booster.memory_status()
        used = total - available
        self.boost_memory.config(text=f"Memory in use: {format_size(used)} of {format_size(total)} "
                                 f"({used * 100 // max(total, 1)}%)")

    def refresh_startup(self):
        tree = self.startup_tree
        tree.delete(*tree.get_children())
        self.startup_rows.clear()
        items = booster.startup_items()
        for item in items:
            row = tree.insert("", "end", text=item.name, tags=() if item.enabled else ("off",),
                              values=("On" if item.enabled else "Off", item.where, item.command))
            self.startup_rows[row] = item
        on = sum(item.enabled for item in items)
        self.startup_summary.config(text=f"{on} of {len(items)} start with Windows. "
                                    "Turning one off keeps it installed.")

    def set_startup_selected(self, enabled):
        """enabled=None flips each selected app."""
        items = [self.startup_rows[row] for row in self.startup_tree.selection()]
        if not items:
            messagebox.showinfo("Startup apps", "Select one or more apps first.", parent=self)
            return
        errors = []
        for item in items:
            try:
                booster.set_startup_enabled(item, (not item.enabled) if enabled is None else enabled)
            except PermissionError:
                errors.append(f"{item.name}: it is set up for all users, so changing it needs administrator rights")
            except OSError as error:
                errors.append(f"{item.name}: {error}")
        self.refresh_startup()
        if errors:
            report_result(self, "Some apps could not be changed.", errors)

    def refresh_programs(self):
        tree = self.programs_tree
        tree.delete(*tree.get_children())
        self.program_rows.clear()
        for program in booster.running_programs()[:60]:
            row = tree.insert("", "end", text=program.name, tags=("protected",) if program.protected else (),
                              values=(len(program.pids), format_size(program.memory),
                                      "Part of Windows" if program.protected else ""))
            self.program_rows[row] = program
        self.refresh_memory()

    def end_selected_programs(self):
        programs = [p for p in (self.program_rows[row] for row in self.programs_tree.selection()) if not p.protected]
        if not programs:
            messagebox.showinfo("Running programs", "Select one or more programs that are not part of Windows.",
                                parent=self)
            return
        names = "\n".join(f"{p.name} ({format_size(p.memory)})" for p in programs)
        if not messagebox.askyesno("End programs", f"End these programs now? Unsaved work in them is lost.\n\n{names}",
                                   icon="warning", parent=self):
            return
        before = booster.memory_status()[1]
        errors = [f"{p.name}: {error}" for p in programs if (error := booster.end_program(p))]
        time.sleep(0.5)  # give Windows a moment to hand the memory back
        self.refresh_programs()
        freed = max(booster.memory_status()[1] - before, 0)
        report_result(self, f"Ended {len(programs) - len(errors)} program(s), about {format_size(freed)} freed.",
                      errors)

    def refresh_power(self):
        for child in self.power_list.winfo_children():
            child.destroy()
        plans = booster.power_plans()
        self.power_plans = {plan.guid: plan for plan in plans}
        for plan in plans:
            ttk.Radiobutton(self.power_list, text=plan.name + ("  (in use)" if plan.active else ""),
                            value=plan.guid, variable=self.power_choice).pack(anchor="w", pady=2)
            if plan.active:
                self.power_choice.set(plan.guid)

    def apply_power_plan(self):
        plan = self.power_plans.get(self.power_choice.get())
        if not plan or plan.active:
            return
        if error := booster.set_power_plan(plan):
            messagebox.showwarning("Power plan", error, parent=self)
        self.refresh_power()

    # --- History tab ---

    def build_history_tab(self, parent):
        tab = ttk.Frame(parent)
        top = ttk.Frame(tab)
        top.pack(fill="x")
        ttk.Button(top, text="Refresh", command=self.refresh_history).pack(side="left")
        ttk.Label(top, text="Search").pack(side="left", padx=(12, 4))
        self.history_filter = tk.StringVar()
        self.history_filter.trace_add("write", lambda *_: self.refresh_history())
        ttk.Entry(top, textvariable=self.history_filter, width=28).pack(side="left")
        self.history_summary = ttk.Label(top)
        self.history_summary.pack(side="left", padx=10)

        table = ttk.Frame(tab)
        table.pack(fill="both", expand=True, pady=8)
        self.history_tree = add_scrolled_tree(table, (
            ("time", "When", 170, "w"), ("origin", "From", 170, "w"),
            ("destination", "To", 190, "w"), ("status", "Status", 90, "w"),
        ), first=("File", 320), selectmode="extended")
        self.history_tree.tag_configure("inactive", foreground="gray")
        self.history_rows = {}  # row id -> (run time, index in run, move)
        self.history_tree.bind("<Control-a>", lambda _: self.history_tree.selection_set(self.history_tree.get_children()))
        attach_file_menu(self.history_tree, lambda row: core.current_path(self.history_rows[row][2]), self.refresh_preview)

        bottom = ttk.Frame(tab)
        bottom.pack(fill="x")
        ttk.Label(bottom, text="Select rows (Ctrl or Shift for several, Ctrl+A for all). Undo puts moved files "
                  "back and brings deleted files out of the Recycle Bin.", foreground="gray").pack(side="left")
        ttk.Button(bottom, text="Undo selected", command=self.undo_selected).pack(side="right")
        return tab

    def refresh_history(self):
        self.history_tree.delete(*self.history_tree.get_children())
        self.history_rows.clear()
        search = self.history_filter.get().lower().strip()
        total = undoable = 0
        for run in reversed(core.load_history()):
            for index, move in enumerate(run["moves"]):
                total += 1
                undoable += core.can_undo(move)
                source = Path(move[0])
                status = "Moved" if core.is_active(move) else move[2].capitalize()
                if not core.is_active(move) and move[2] == "deleted":
                    destination = "Recycle Bin"
                elif not core.is_active(move) and move[2] == "erased":
                    destination = "Deleted for good"
                else:
                    destination = Path(move[1]).parent if move[1] else source.parent
                values = (run["time"], source.parent, destination, status)
                if search and search not in f"{source.name} {' '.join(map(str, values))}".lower():
                    continue
                folder = Path(move[1]).parent.name if move[1] else source.parent.name
                row = self.history_tree.insert(
                    "", "end", text=source.name, values=values,
                    image=theme.tile(source.suffix.lstrip("."), folder, faded=not core.is_active(move)),
                    tags=() if core.is_active(move) else ("inactive",))
                self.history_rows[row] = (run["time"], index, move)
        shown = f"showing {len(self.history_rows)} of " if search else ""
        self.history_summary.config(text=f"{shown}{total} change(s) logged, {undoable} can be undone")

    def undo_selected(self):
        chosen = [self.history_rows[row] for row in self.history_tree.selection()]
        selection = [(run_time, index) for run_time, index, move in chosen if core.can_undo(move)]
        if not selection:
            messagebox.showinfo("Undo", "Select one or more rows with the status Moved or Deleted.")
            return
        if not messagebox.askyesno("Undo", f"Undo {len(selection)} change(s)?"):
            return
        count, errors = core.undo_moves(selection)
        self.refresh_preview()
        report_result(self, f"Restored {count} file(s).", errors)

    # --- Settings tab ---

    def build_settings_tab(self, parent):
        tab = ttk.Frame(parent)
        tab.columnconfigure(1, weight=1)
        config = self.config_data
        self.age_var = tk.StringVar(value=str(config["min_age_days"]))
        self.interval_var = tk.StringVar(value=str(config["scan_interval_minutes"]))
        self.other_var = tk.StringVar(value=config["other_folder"])
        self.ignore_var = tk.StringVar(value=", ".join(config["ignore"]))
        self.after_run_var = tk.StringVar(value=AFTER_RUN_LABELS.get(config["after_run"], AFTER_RUN_LABELS["window"]))

        ttk.Label(tab, text="Folders to sort").grid(row=0, column=0, sticky="nw")
        self.folders = tk.Listbox(tab, height=2, activestyle="none")
        theme.style_listbox(self.folders)
        self.folders.grid(row=0, column=1, sticky="ew", padx=6)
        self.folder_values = list(config["folders"])
        self.show_folders()
        folder_menu = tk.Menu(self.folders, tearoff=0)
        theme.style_menu(folder_menu)
        folder_menu.add_command(label="Sort only this folder now",
                                command=lambda: self.sort_folder_now(self.folders.curselection()[0]))

        def folder_popup(event):
            index = self.folders.nearest(event.y)
            if index >= 0:
                self.folders.selection_clear(0, "end")
                self.folders.selection_set(index)
                folder_menu.tk_popup(event.x_root, event.y_root)

        self.folders.bind("<Button-3>", folder_popup)
        folder_buttons = ttk.Frame(tab)
        folder_buttons.grid(row=0, column=2, sticky="n")
        ttk.Button(folder_buttons, text="Add…", command=self.add_folder).pack(fill="x")
        ttk.Button(folder_buttons, text="Remove", command=self.remove_folder).pack(fill="x", pady=(4, 0))

        def row(number, label, widget_builder, hint=""):
            ttk.Label(tab, text=label).grid(row=number, column=0, sticky="w", pady=(8, 0))
            frame = ttk.Frame(tab)
            frame.grid(row=number, column=1, columnspan=2, sticky="ew", padx=6, pady=(8, 0))
            widget_builder(frame).pack(side="left")
            ttk.Label(frame, text=hint, foreground="gray").pack(side="left", padx=8)

        row(1, "Move files older than (days)",
            lambda f: ttk.Spinbox(f, from_=0, to=3650, textvariable=self.age_var, width=8),
            "a category can have its own number")
        row(2, "Background check every (minutes)",
            lambda f: ttk.Spinbox(f, from_=0, to=10080, textvariable=self.interval_var, width=8),
            "0 turns automatic sorting off")
        row(3, "After an automatic run",
            lambda f: ttk.Combobox(f, textvariable=self.after_run_var, values=list(AFTER_RUN_LABELS.values()),
                                   state="readonly", width=26))
        row(4, "Folder for all other file types",
            lambda f: ttk.Entry(f, textvariable=self.other_var, width=28), "leave blank to leave those files alone")
        row(5, "Never move (names or patterns)",
            lambda f: ttk.Entry(f, textvariable=self.ignore_var, width=58), "e.g. *.torrent, taxes*")

        ttk.Label(tab, text="Categories").grid(row=6, column=0, sticky="w", pady=(12, 2))
        table = ttk.Frame(tab)
        table.grid(row=7, column=0, columnspan=3, sticky="nsew")
        tab.rowconfigure(7, weight=1)
        self.categories = add_scrolled_tree(table, (
            ("extensions", "Extensions", 430, "w"), ("age", "Move after", 110, "w"),
            ("recycle", "Clean up after", 130, "w"),
        ), first=("Destination folder", 220), height=4)
        self.categories.bind("<Double-1>", lambda _: self.edit_category())
        self.category_values = {}  # row id -> category dict
        for category in config["categories"]:
            self.insert_category(category)

        buttons = ttk.Frame(tab)
        buttons.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        ttk.Button(buttons, text="Add…", command=self.add_category).pack(side="left")
        ttk.Button(buttons, text="Edit…", command=self.edit_category).pack(side="left", padx=6)
        ttk.Button(buttons, text="Remove", command=self.remove_category).pack(side="left")
        ttk.Button(buttons, text="Save settings", style=theme.accent(), command=self.save_settings).pack(side="right")
        return tab

    def show_folders(self):
        self.folders.delete(0, "end")
        for folder in self.folder_values:
            self.folders.insert("end", folder or f"Downloads (automatic): {core.detect_downloads_folder()}")

    def add_folder(self):
        folder = filedialog.askdirectory(parent=self)
        if folder and os.path.normpath(folder) not in self.folder_values:
            self.folder_values.append(os.path.normpath(folder))
            self.show_folders()

    def remove_folder(self):
        for index in reversed(self.folders.curselection()):
            del self.folder_values[index]
        self.show_folders()

    def insert_category(self, category, row=None):
        values = (
            " ".join(category["extensions"]),
            "general" if category["min_age_days"] is None else f"{category['min_age_days']} days",
            f"{category['recycle_after_days']} days" if category["recycle_after_days"] else "never",
        )
        row = row or self.categories.insert("", "end")
        self.categories.item(row, text=category["folder"], image=theme.tile(group=Path(category["folder"]).name),
                             values=values)
        self.category_values[row] = category

    def add_category(self):
        dialog = CategoryDialog(self)
        if dialog.result:
            self.insert_category(dialog.result)

    def edit_category(self):
        selection = self.categories.selection()
        if not selection:
            return
        dialog = CategoryDialog(self, self.category_values[selection[0]])
        if dialog.result:
            self.insert_category(dialog.result, selection[0])

    def remove_category(self):
        for row in self.categories.selection():
            self.categories.delete(row)
            del self.category_values[row]

    def save_settings(self):
        try:
            age, interval = int(self.age_var.get()), int(self.interval_var.get())
            if age < 0 or interval < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Settings", "Days and minutes must be whole numbers, 0 or more.")
            return
        if not self.folder_values:
            self.folder_values = [""]
            self.show_folders()
        after_run = next(key for key, label in AFTER_RUN_LABELS.items() if label == self.after_run_var.get())
        self.update_config(
            folders=list(self.folder_values), min_age_days=age, scan_interval_minutes=interval,
            categories=[self.category_values[row] for row in self.categories.get_children()],
            other_folder=self.other_var.get().strip(), ignore=split_list(self.ignore_var.get()), after_run=after_run)
        message = "Settings saved. The Preview tab shows the result."
        if interval == 0:
            if core.background_pid() or core.autostart_enabled():
                message += "\n\nAutomatic sorting has been turned off because the interval is 0."
            core.set_autostart(False)
            core.stop_background()
        self.refresh_preview()
        self.after(800, self.refresh_background_status)
        messagebox.showinfo("Settings", message)

    # --- Background control ---

    def build_status_bar(self, parent):
        bar = ttk.Frame(parent, padding=(theme.px(22), theme.px(12)))
        bar.pack(side="bottom", fill="x")
        self.status_dot = ttk.Label(bar, text="●", font=("Segoe UI", 13))
        self.status_dot.pack(side="left", padx=(0, 6))
        # The buttons are packed before the label so a narrow window cuts the text, not the buttons.
        self.background_button = ttk.Button(bar, command=self.toggle_background)
        self.background_button.pack(side="right")
        self.pause_button = ttk.Button(bar, command=self.toggle_pause)
        self.pause_button.pack(side="right", padx=6)
        self.background_label = ttk.Label(bar)
        self.background_label.pack(side="left")

    def refresh_background_status(self, repeat=False):
        running = core.background_pid() is not None
        self.config_data["paused_until"] = core.load_config()["paused_until"]  # the tray menu can change it
        paused = core.is_paused(self.config_data)
        if running and paused:
            text = f"Automatic sorting is PAUSED until {self.config_data['paused_until']}"
        elif running:
            text = "Automatic sorting is ON (see the icon in the taskbar tray)"
        elif self.config_data["scan_interval_minutes"] == 0:
            text = "Automatic sorting is OFF: the check interval is set to 0"
        else:
            text = "Automatic sorting is OFF: nothing moves until you click Move"
        self.background_label.config(text=text)
        self.status_dot.config(foreground=theme.AMBER if running and paused else theme.GREEN if running else theme.GRAY)
        self.background_button.config(text="Turn off automatic sorting" if running else "Turn on automatic sorting")
        self.pause_button.config(text="Resume" if paused else "Pause for today", state="normal" if running else "disabled")
        if repeat:
            self.after(3000, self.refresh_background_status, True)

    def toggle_pause(self):
        self.update_config(paused_until="" if core.is_paused(self.config_data) else core.pause_until_tomorrow())
        self.refresh_background_status()

    def toggle_background(self):
        if core.background_pid():
            core.set_autostart(False)
            core.stop_background()
        elif self.config_data["scan_interval_minutes"] == 0:
            messagebox.showinfo(
                "Automatic sorting",
                "The check interval is 0, which keeps automatic sorting off.\n\n"
                "Set it to 1 or more in Settings, save, then turn it on.")
        elif messagebox.askyesno(
                "Automatic sorting",
                f"The {len(self.moves)} file(s) in the preview will be moved now, and from then on files "
                f"will be checked every {self.config_data['scan_interval_minutes']} minutes and moved without asking.\n\n"
                "After each run you can review, approve or undo what moved.\n\n"
                "It starts by itself every time you sign in to Windows.\n\nTurn it on?"):
            core.set_autostart(True)
            core.start_background()
            self.after(1500, self.refresh_preview)
        self.after(800, self.refresh_background_status)


class ReportWindow(tk.Tk):
    """What automatic runs moved since the user last approved, with Undo and Approve.

    Only one is open at a time; it picks up further runs by itself.
    """

    def __init__(self):
        super().__init__()
        self.title(f"{core.APP_NAME}: files were moved")
        theme.apply(self)
        theme.set_size(self, 900, 580, 660, 380)
        core.DATA_DIR.mkdir(parents=True, exist_ok=True)
        core.REPORT_PID_FILE.write_text(str(os.getpid()))
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.heading = ttk.Label(self, padding=(10, 14, 10, 4), style="Title.TLabel")
        self.heading.pack(anchor="w")
        ttk.Label(self, padding=(10, 0), text="Approve to keep them where they are now, or Undo to put them all back. "
                  "Right-click a file for more.").pack(anchor="w")
        table = ttk.Frame(self, padding=10)
        table.pack(fill="both", expand=True)
        self.tree = add_scrolled_tree(table, (
            ("destination", "Moved to", 300, "w"), ("time", "When", 170, "w")), first=("File", 360))
        self.paths = {}  # row id -> where the file is now
        attach_file_menu(self.tree, self.paths.get, self.refresh)

        buttons = ttk.Frame(self, padding=(10, 0, 10, 10))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Approve", style=theme.accent(), command=self.approve).pack(side="right")
        self.undo_button = ttk.Button(buttons, text="Undo all", command=self.undo)
        self.undo_button.pack(side="right", padx=6)

        self.pending = []
        self.refresh(repeat=True)
        # Come to the front once, without staying above other windows.
        self.attributes("-topmost", True)
        self.after(500, lambda: self.attributes("-topmost", False))

    def refresh(self, repeat=False):
        pending = core.pending_moves()
        if pending != self.pending or not self.tree.get_children():
            self.pending = pending
            self.tree.delete(*self.tree.get_children())
            self.paths.clear()
            for run_time, _, (source, destination) in pending:
                row = self.tree.insert(
                    "", "end", text=Path(source).name,
                    image=theme.tile(Path(source).suffix.lstrip("."), Path(destination).parent.name),
                    values=(Path(destination).parent, run_time))
                self.paths[row] = Path(destination)
            self.heading.config(text=f"{len(pending)} file(s) were moved automatically" if pending
                                else "Nothing is waiting for review")
            self.undo_button.config(state="normal" if pending else "disabled")
        if repeat:
            self.after(3000, self.refresh, True)

    def approve(self):
        core.approve_pending()
        self.close()

    def undo(self):
        count, errors = core.undo_moves([(run_time, index) for run_time, index, _ in self.pending])
        core.approve_pending()
        report_result(self, f"Restored {count} file(s). They will not be moved again automatically.", errors)
        self.close()

    def close(self):
        core.REPORT_PID_FILE.unlink(missing_ok=True)
        self.destroy()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "--background":
        core.run_background()
    elif mode == "--report":
        ReportWindow().mainloop()
    else:
        App(splash=True).mainloop()
