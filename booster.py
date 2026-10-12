# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 hmodymac8-droid
"""Make the PC start and run lighter: startup apps, memory-hungry programs and
the power plan.

This is the engine behind the Booster page in sort_gui.pyw. Every change it
makes can be reversed from the same page: startup apps are switched off the
way Task Manager does it (the entry itself is kept), and the power plan can be
switched back.
"""

import csv
import io
import os
import re
import struct
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"
# Ending these would crash or lock Windows, so they are never offered.
PROTECTED = {
    "system", "system idle process", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "lsaiso.exe", "svchost.exe", "dwm.exe", "explorer.exe", "fontdrvhost.exe",
    "memory compression", "secure system", "sihost.exe", "ctfmon.exe", "audiodg.exe", "conhost.exe",
    "msmpeng.exe", "searchindexer.exe", "spoolsv.exe", "taskhostw.exe", "runtimebroker.exe",
    "startmenuexperiencehost.exe", "shellexperiencehost.exe", "textinputhost.exe", "securityhealthservice.exe",
}


@dataclass
class StartupItem:
    name: str
    command: str
    where: str  # shown to the user
    hive: str  # "HKCU" or "HKLM", where its on/off switch lives
    approved_key: str  # subkey of APPROVED holding the switch
    enabled: bool
    value_name: str = ""  # the switch's value name, when it differs from name (startup-folder files)

    @property
    def needs_admin(self) -> bool:
        return self.hive == "HKLM"


def _hive(name):
    import winreg
    return winreg.HKEY_CURRENT_USER if name == "HKCU" else winreg.HKEY_LOCAL_MACHINE


def _approved_state(hive: str, subkey: str, name: str) -> bool:
    """Task Manager's switch: an even first byte (or no value) means on."""
    import winreg
    try:
        with winreg.OpenKey(_hive(hive), f"{APPROVED}\\{subkey}") as key:
            data, _ = winreg.QueryValueEx(key, name)
        return not (data and data[0] & 1)
    except OSError:
        return True


def startup_items() -> list[StartupItem]:
    import winreg
    items = []
    for hive, path, view, approved, where in (
            ("HKCU", RUN, 0, "Run", "Registry (you)"),
            ("HKLM", RUN, winreg.KEY_WOW64_64KEY, "Run", "Registry (all users)"),
            ("HKLM", RUN, winreg.KEY_WOW64_32KEY, "Run32", "Registry (all users, 32-bit)")):
        try:
            key = winreg.OpenKey(_hive(hive), path, 0, winreg.KEY_READ | view)
        except OSError:
            continue
        with key:
            index = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, index)
                except OSError:
                    break
                index += 1
                if any(item.name == name and item.hive == hive for item in items):
                    continue  # 64- and 32-bit views can show the same key
                items.append(StartupItem(name, str(value), where, hive, approved,
                                         _approved_state(hive, approved, name)))
    for hive, variable, where in (("HKCU", "APPDATA", "Startup folder (you)"),
                                  ("HKLM", "ProgramData", "Startup folder (all users)")):
        base = os.environ.get(variable)
        folder = Path(base, r"Microsoft\Windows\Start Menu\Programs\Startup") if base else None
        if not folder or not folder.is_dir():
            continue
        for path in folder.iterdir():
            if path.is_file() and path.name.lower() != "desktop.ini":
                items.append(StartupItem(path.stem, str(path), where, hive, "StartupFolder",
                                         _approved_state(hive, "StartupFolder", path.name), path.name))
    return sorted(items, key=lambda item: item.name.lower())


def set_startup_enabled(item: StartupItem, enabled: bool) -> None:
    """Switch a startup app on or off, exactly like Task Manager. Raises OSError
    (PermissionError for all-users items without administrator rights)."""
    import winreg
    name = item.value_name or item.name
    if enabled:
        data = bytes([2]) + bytes(11)
    else:
        filetime = int((time.time() + 11644473600) * 10_000_000)  # Windows time of switching off
        data = bytes([3, 0, 0, 0]) + struct.pack("<Q", filetime)
    with winreg.CreateKeyEx(_hive(item.hive), f"{APPROVED}\\{item.approved_key}", 0,
                            winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_BINARY, data)
    item.enabled = enabled


@dataclass
class Program:
    name: str
    pids: list[int]
    memory: int  # bytes, all copies together

    @property
    def protected(self) -> bool:
        return self.name.lower() in PROTECTED or os.getpid() in self.pids


def running_programs() -> list[Program]:
    """Programs running now, biggest memory users first, copies of one program combined."""
    output = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True,
                            creationflags=NO_WINDOW, errors="replace").stdout
    programs = {}
    for row in csv.reader(io.StringIO(output)):
        if len(row) < 5:
            continue
        name, pid, memory = row[0], row[1], re.sub(r"\D", "", row[4])
        program = programs.setdefault(name.lower(), Program(name, [], 0))
        program.pids.append(int(pid))
        program.memory += int(memory or 0) * 1024
    return sorted(programs.values(), key=lambda p: p.memory, reverse=True)


def end_program(program: Program) -> str | None:
    """End every copy of a program. Returns an error message, or None."""
    if program.protected:
        return f"{program.name} is part of Windows and can't be ended here."
    args = ["taskkill", "/f"] + [part for pid in program.pids for part in ("/pid", str(pid))]
    result = subprocess.run(args, capture_output=True, text=True, creationflags=NO_WINDOW, errors="replace")
    return None if result.returncode == 0 else (result.stderr or result.stdout).strip() or "taskkill failed"


@dataclass
class PowerPlan:
    guid: str
    name: str
    active: bool


def power_plans() -> list[PowerPlan]:
    output = subprocess.run(["powercfg", "/list"], capture_output=True, text=True,
                            creationflags=NO_WINDOW, errors="replace").stdout
    return [PowerPlan(guid, name, star == "*") for guid, name, star in
            re.findall(r"([0-9a-fA-F-]{36})\s+\((.+?)\)\s*(\*?)", output)]


def set_power_plan(plan: PowerPlan) -> str | None:
    result = subprocess.run(["powercfg", "/setactive", plan.guid], capture_output=True, text=True,
                            creationflags=NO_WINDOW, errors="replace")
    return None if result.returncode == 0 else (result.stderr or result.stdout).strip() or "powercfg failed"


def memory_status() -> tuple[int, int]:
    """(total, available) physical memory in bytes."""
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    status = MEMORYSTATUSEX(dwLength=ctypes.sizeof(MEMORYSTATUSEX))
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return status.ullTotalPhys, status.ullAvailPhys
