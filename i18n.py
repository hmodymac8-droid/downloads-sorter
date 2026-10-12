# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 hmodymac8-droid
"""Arabic interface for Downloads Sorter.

The program's source is written in English. Rather than wrap every string by
hand, install() hooks the few Tk entry points through which text reaches the
screen (widget creation, configure, tree headings and cells, menus, message
boxes, window titles) and passes it through tr(). Text with no translation is
shown in English, so a missing entry is never an error.

To translate a new string, add it to translations_ar.py:
  EXACT      for fixed text
  TEMPLATES  for text with inserted values, written with {0}, {1}, ...
"""

import re

LANG = "en"
MISSES = set()  # English text seen with no Arabic translation (useful when adding strings)
_patterns = None


def _compile():
    from translations_ar import TEMPLATES

    compiled = []
    # Longest first, so a specific sentence wins over a shorter one that also fits.
    for english, arabic in sorted(TEMPLATES.items(), key=lambda pair: -len(pair[0])):
        pattern = re.escape(english)
        pattern = re.sub(r"\\\{(\d+)\\\}", "(.+?)", pattern)
        compiled.append((re.compile(pattern, re.DOTALL), arabic))
    return compiled


def tr(text):
    """Return the Arabic for an English interface string, or the text unchanged."""
    global _patterns
    if LANG != "ar" or not isinstance(text, str) or not text.strip():
        return text
    from translations_ar import EXACT

    if text in EXACT:
        return EXACT[text]
    if _patterns is None:
        _patterns = _compile()
    for pattern, arabic in _patterns:
        match = pattern.fullmatch(text)
        if match:
            # Inserted values are usually names and numbers; a few are words (a status) that have a translation.
            return arabic.format(*[EXACT.get(group, group) for group in match.groups()])
    if any(character.isascii() and character.isalpha() for character in text):
        MISSES.add(text)
    return text


_ARABIC = re.compile(r"[؀-ۿ]")
WRAP_PIXELS_PER_CHARACTER = 8.5  # rough width of body text at 100% scaling, for pre-wrapping


def visual(text: str, wrap_pixels: float = 0) -> str:
    """Put the words of Arabic text in the order themed (ttk) widgets need.

    Those widgets join Arabic letters correctly but lay the words of a line out
    left to right, so a sentence comes out backwards. Windows' own controls
    (menus, message boxes, plain Tk labels) do it properly and must not get this.
    The fix reverses the word order of each line, keeping stretches of Latin
    text and numbers in their own left-to-right order. Wrapped text is split
    into lines here first, because wrapping after reordering would put the end
    of the sentence on the first line.
    """
    if not isinstance(text, str) or not _ARABIC.search(text):
        return text
    lines = []
    for line in text.split("\n"):
        if wrap_pixels:
            limit, current = max(20, int(wrap_pixels / WRAP_PIXELS_PER_CHARACTER)), ""
            for word in line.split(" "):
                if current and len(current) + 1 + len(word) > limit:
                    lines.append(current)
                    current = word
                else:
                    current = f"{current} {word}" if current else word
            lines.append(current)
        else:
            lines.append(line)
    shaped = []
    for line in lines:
        tokens = re.split(r"(\s+)", line)[::-1]
        # Runs of non-Arabic words were reversed along with everything else; turn them back.
        start = None
        for index in range(len(tokens) + 1):
            latin = index < len(tokens) and not _ARABIC.search(tokens[index])
            if latin and start is None:
                start = index
            elif not latin and start is not None:
                run = tokens[start:index]
                # Leading/trailing spaces of the run belong to the Arabic words around it.
                while run and not run[0].strip():
                    start += 1
                    run = run[1:]
                end = start + len(run)
                while run and not run[-1].strip():
                    end -= 1
                    run = run[:-1]
                tokens[start:end] = run[::-1]
                start = None
        for index, token in enumerate(tokens):
            if _ARABIC.search(token):
                # Right-to-left marks make punctuation and brackets in the word sit on the correct side.
                tokens[index] = f"‏{token}‏"
            elif token.strip():
                # A Latin word or number ending the clause: its full stop or comma belongs on the left.
                body = token.rstrip(".,:;!?…")
                tokens[index] = token[len(body):] + body
        shaped.append("".join(tokens))
    return "\n".join(shaped)


def _translate_options(options, shape=False):
    """Translate the text options in a dict; shape=True also reorders it for a themed widget."""
    if not isinstance(options, dict):
        return
    for key in ("text", "label", "title", "message"):
        if isinstance(options.get(key), str):
            options[key] = tr(options[key])
            if shape:
                wrap = options.get("wraplength") or 0
                options[key] = visual(options[key], wrap if isinstance(wrap, (int, float)) else 0)


def install(language: str) -> None:
    """Choose the language and, for Arabic, hook Tk so interface text is translated."""
    global LANG
    LANG = language
    if language != "ar" or getattr(install, "done", False):
        return
    install.done = True
    import tkinter
    from tkinter import messagebox, ttk

    def wrap(owner, name, adjust):
        original = getattr(owner, name)

        def wrapper(*args, **kwargs):
            args, kwargs = adjust(list(args), kwargs)
            return original(*args, **kwargs)

        wrapper.__name__ = name
        setattr(owner, name, wrapper)

    def themed(widget):
        """True for ttk widgets that draw their own text (see visual()); entry fields are fine as they are."""
        return isinstance(widget, ttk.Widget) and not isinstance(widget, ttk.Entry)

    def options_in_kwargs(args, kwargs):
        shape = bool(args) and themed(args[0])
        _translate_options(kwargs, shape)
        for argument in args:
            _translate_options(argument, shape)  # Tk also accepts options as a dict
        return args, kwargs

    def widget_init(args, kwargs):
        # BaseWidget.__init__(self, master, widgetName, cnf={}, kw={}, extra=())
        shape = themed(args[0])
        _translate_options(kwargs.get("cnf"), shape)
        _translate_options(kwargs.get("kw"), shape)
        for argument in args[3:5]:
            _translate_options(argument, shape)
        return args, kwargs

    def cells(args, kwargs):
        # Tree rows: translate known words (a status, "never") but leave file names alone,
        # which exact-match lookup does by itself.
        # The row's own text is always data (a file or folder name), so it is not touched.
        if isinstance(kwargs.get("values"), (list, tuple)):
            kwargs["values"] = [visual(tr(value)) if isinstance(value, str) else value for value in kwargs["values"]]
        return args, kwargs

    def tree_set(args, kwargs):
        if len(args) == 4 and isinstance(args[3], str):  # tree.set(item, column, value)
            args[3] = visual(tr(args[3]))
        return args, kwargs

    def first_argument(args, kwargs):
        if len(args) > 1 and isinstance(args[1], str):  # window.title("...")
            args[1] = tr(args[1])
        return args, kwargs

    def dialog(args, kwargs):
        return [tr(argument) if isinstance(argument, str) else argument for argument in args], \
            {key: tr(value) if key in ("title", "message", "detail") else value for key, value in kwargs.items()}

    wrap(tkinter.BaseWidget, "__init__", widget_init)
    for name in ("configure", "config"):  # two names for one method; both are used
        wrap(tkinter.Misc, name, options_in_kwargs)
    wrap(tkinter.Menu, "add", options_in_kwargs)
    for name in ("wm_title", "title"):
        wrap(tkinter.Wm, name, first_argument)
    wrap(ttk.Treeview, "heading", options_in_kwargs)
    wrap(ttk.Treeview, "insert", cells)
    wrap(ttk.Treeview, "item", cells)
    wrap(ttk.Treeview, "set", tree_set)
    for name in ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel", "askquestion", "askyesnocancel"):
        wrap(messagebox, name, dialog)
