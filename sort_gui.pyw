"""Downloads Sorter: control panel, report window and background entry point."""

import os
import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

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


def attach_file_menu(tree, path_for_row, on_change, extra=()):
    """Give a file list a right-click menu: show in Explorer, open, delete.

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
    def __init__(self):
        super().__init__()
        self.title(core.APP_NAME)
        theme.apply(self)
        theme.set_size(self, 1200, 760, 980, 640)
        self.config_data = core.load_config()
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
            ("history", "", "History", self.build_history_tab),
            ("settings", "", "Settings", self.build_settings_tab),
        ):
            page = ttk.Frame(self.pages, padding=(theme.px(22), theme.px(16), theme.px(22), 0))
            page.grid(row=0, column=0, sticky="nsew")
            ttk.Label(page, text=title, style="Title.TLabel").pack(anchor="w", pady=(0, theme.px(10)))
            build(page).pack(fill="both", expand=True)
            self.page_frames[key] = page
            self.sidebar.add(key, glyph, title)

        self.refresh_preview()
        self.refresh_background_status(repeat=True)
        self.show_page("preview")

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
        ttk.Button(bottom, text="Sort ALL files now (ignore age)", command=self.sort_all_now).pack(side="right", padx=6)
        return tab

    def refresh_preview(self):
        self.tree.delete(*self.tree.get_children())
        self.moves.clear()
        for move in core.plan_moves(self.config_data):
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
        self.summary.config(text=f"{count} file(s) ready to move ({size})" if count
                            else "Nothing to move: no files are old enough yet")
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
        if not moves or not messagebox.askyesno("Move files", f"Move only the {len(moves)} selected file(s)?"):
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
        tab = ttk.Frame(parent)
        top = ttk.Frame(tab)
        top.pack(fill="x")
        self.scan_button = ttk.Button(top, text="Scan for duplicates", command=self.scan_duplicates)
        self.scan_button.pack(side="left")
        self.duplicates_summary = ttk.Label(
            top, text="Finds files with identical content in the sorted folders and their category folders.")
        self.duplicates_summary.pack(side="left", padx=10)

        table = ttk.Frame(tab)
        table.pack(fill="both", expand=True, pady=8)
        self.duplicates_tree = add_scrolled_tree(table, (
            ("folder", "Folder", 340, "w"), ("size", "Size", 100, "center"), ("action", "Action", 100, "w"),
        ), first=("File", 380), selectmode="extended")
        self.duplicates_tree.tag_configure("keep", foreground="gray")
        self.duplicate_paths = {}  # row id -> path, for every row
        self.duplicate_extras = {}  # row id -> path, only rows that will be deleted
        attach_file_menu(self.duplicates_tree, self.duplicate_paths.get, self.scan_duplicates)

        bottom = ttk.Frame(tab)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Keep selected", command=self.keep_selected_duplicates).pack(side="left")
        ttk.Label(bottom, text="One copy of each file is always kept. Deleted copies go to the Recycle Bin "
                  "and can be brought back from History.", foreground="gray").pack(side="left", padx=8)
        self.delete_duplicates_button = ttk.Button(
            bottom, text="Delete duplicates", command=self.delete_duplicates, state="disabled")
        self.delete_duplicates_button.pack(side="right")
        return tab

    def scan_duplicates(self):
        self.scan_button.config(state="disabled")
        self.duplicates_summary.config(text="Scanning… large files take a while.")
        result = []
        # Hashing can take long, so it runs off the window's thread.
        thread = threading.Thread(target=lambda: result.append(core.find_duplicates(self.config_data)), daemon=True)
        thread.start()

        def check():
            if thread.is_alive():
                self.after(200, check)
            else:
                self.show_duplicates(result[0] if result else [])

        check()

    def show_duplicates(self, groups):
        self.scan_button.config(state="normal")
        self.duplicates_tree.delete(*self.duplicates_tree.get_children())
        self.duplicate_paths.clear()
        self.duplicate_extras.clear()
        for group in groups:
            size = format_size(group[0].stat().st_size) if group[0].exists() else ""
            for position, path in enumerate(group):
                row = self.duplicates_tree.insert(
                    "", "end", tags=() if position else ("keep",), text=path.name,
                    image=theme.tile(path.suffix.lstrip("."), path.parent.name),
                    values=(path.parent, size, "Delete" if position else "Keep"))
                self.duplicate_paths[row] = path
                if position:
                    self.duplicate_extras[row] = path
        self.update_duplicates_summary(len(groups))

    def update_duplicates_summary(self, groups=None):
        count = len(self.duplicate_extras)
        try:
            size = format_size(sum(path.stat().st_size for path in self.duplicate_extras.values()))
        except OSError:
            size = "?"
        if groups is not None and not count:
            text = "No duplicates found."
        else:
            text = f"{count} duplicate copy(ies) marked Delete ({size})"
        self.duplicates_summary.config(text=text)
        self.delete_duplicates_button.config(
            text=f"Delete {count} duplicate(s)", state="normal" if count else "disabled")

    def keep_selected_duplicates(self):
        for row in self.duplicates_tree.selection():
            if self.duplicate_extras.pop(row, None):
                self.duplicates_tree.set(row, "action", "Keep")
                self.duplicates_tree.item(row, tags=("keep",))
        self.update_duplicates_summary()

    def delete_duplicates(self):
        paths = list(self.duplicate_extras.values())
        if not messagebox.askyesno("Duplicates", f"Send {len(paths)} duplicate file(s) to the Recycle Bin?"):
            return
        count, errors = core.delete_files(paths)
        self.refresh_preview()
        report_result(self, f"Deleted {count} duplicate(s).", errors)
        self.scan_duplicates()

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
        self.background_label = ttk.Label(bar)
        self.background_label.pack(side="left")
        self.background_button = ttk.Button(bar, command=self.toggle_background)
        self.background_button.pack(side="right")
        self.pause_button = ttk.Button(bar, command=self.toggle_pause)
        self.pause_button.pack(side="right", padx=6)

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


def uninstall():
    """Remove the installed program. Settings and undo history are kept."""
    import tempfile
    import winreg

    root = tk.Tk()
    root.withdraw()
    if not core.FROZEN or core.APP_DIR != core.INSTALL_DIR.resolve():
        messagebox.showinfo("Uninstall", "This copy was not installed, so there is nothing to uninstall.")
        return
    if not messagebox.askyesno("Uninstall", f"Remove {core.APP_NAME} from this computer?\n\n"
                               "Files that were already sorted stay where they are."):
        return
    core.stop_background()
    core.set_autostart(False)
    for shortcut in (core.start_menu_shortcut(), core.desktop_shortcut()):
        shortcut.unlink(missing_ok=True)
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, core.UNINSTALL_KEY)
    except OSError:
        pass
    messagebox.showinfo("Uninstall", f"{core.APP_NAME} has been removed.")
    # A running exe can't delete its own folder, so a helper does it after we exit.
    subprocess.Popen(f'cmd /c ping -n 4 127.0.0.1 >nul & rmdir /s /q "{core.INSTALL_DIR}"',
                     cwd=tempfile.gettempdir(), stdin=subprocess.DEVNULL, creationflags=core.NO_WINDOW)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "--background":
        core.run_background()
    elif mode == "--report":
        ReportWindow().mainloop()
    elif mode == "--uninstall":
        uninstall()
    else:
        App().mainloop()
