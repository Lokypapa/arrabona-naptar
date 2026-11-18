# -*- coding: utf-8 -*-
"""Közös dolgok: útvonalak, beállítások, színek (az Arrabona Guard témáját követi)."""
import json
import os
import sys


def data_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, "ArrabonaNaptar")
    os.makedirs(d, exist_ok=True)
    return d


def store_path():
    return os.path.join(data_dir(), "naptar.json")


def res_path(*parts):
    """Beépített fájlok (logó). PyInstaller alatt a _internal mappában vannak."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


DEFAULT_SETTINGS = {
    "allday_reminder_time": "08:00",   # egész napos események / születésnapok emlékeztetője
    "nameday_reminder": True,          # figyelt nevek névnapján szól
    "nameday_reminder_time": "08:00",
    "show_namedays": True,             # névnap a havi nézet celláiban
    "show_jeles": True,                # jeles napok (anyák napja, advent...) a cellákban
    "tray_on_close": True,             # X-re a tálcára kerül (az emlékeztetők így is szólnak)
    "start_with_windows": False,
    "start_hidden": False,             # Windows-indításkor rögtön a tálcára
    "sound": True,
    "default_reminders": [15],         # új (időponthoz kötött) esemény alap-emlékeztetője, perc
    "birthday_reminders": [0, 1440],   # születésnap: aznap reggel + 1 nappal előtte
    "view": "month",
    "dark": None,                      # None = a Guard témáját követi
    "calendar_refresh_min": 30,        # [v1.3.0] külső naptárak frissítése (perc)
    "publish_dir": "",                 # [v1.3.0] ide írja ki az ArrabonaNaptar.ics-t (pl. Dropbox mappa)
    "publish_shifts": True,
    "publish_birthdays": True,
}


def _settings_file():
    return os.path.join(data_dir(), "beallitasok.json")


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(_settings_file(), "r", encoding="utf-8") as f:
            loaded = json.load(f)
        for k in s:
            if k in loaded and (s[k] is None or type(loaded[k]) is type(s[k])):
                s[k] = loaded[k]
    except Exception:
        pass
    return s


def save_settings(s):
    try:
        with open(_settings_file(), "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


COLORS = {
    'brand': '#27ae60', 'brand_dark': '#1e8a4c', 'white': '#ffffff',
    'bg': '#f0f0f4', 'panel': '#ffffff', 'panel_head': '#f5f5f7',
    'divider': '#e0e0e6', 'text': '#333333', 'text_soft': '#666666',
    'ok': '#27ae60', 'warn': '#e67e22', 'bad': '#c0392b', 'great': '#1e8a4c',
    'entry': '#ffffff', 'select': '#d5f0e0', 'other_month': '#f7f7fa', 'today': '#e8f7ee',
    'holiday': '#c0392b', 'workday': '#2980b9',
}
DARK_COLORS = {
    'brand': '#27ae60', 'brand_dark': '#1e8a4c', 'white': '#ffffff',
    'bg': '#16161c', 'panel': '#1e1e26', 'panel_head': '#26262f',
    'divider': '#3a3a44', 'text': '#e8e8ec', 'text_soft': '#9a9aa5',
    'ok': '#2ecc71', 'warn': '#e67e22', 'bad': '#e05548', 'great': '#27ae60',
    'entry': '#2a2a34', 'select': '#1e5a3a', 'other_month': '#191920', 'today': '#163a26',
    'holiday': '#ff6b5e', 'workday': '#5dade2',
}


def guard_is_dark():
    p = os.path.join(os.environ.get("APPDATA", ""), "ArrabonaGuard", "tema.txt")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return f.read().strip().lower() == "dark"
    except Exception:
        return False


_s = load_settings()
if (_s.get("dark") is None and guard_is_dark()) or _s.get("dark") is True:
    COLORS.update(DARK_COLORS)


def set_autostart(enabled, hidden=True):
    """Indítás a Windows-szal (HKCU\\...\\Run). Csak telepített (exe) változatnál értelmes."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        try:
            if enabled:
                if getattr(sys, "frozen", False):
                    cmd = f'"{sys.executable}"'
                else:
                    pyw = sys.executable.replace("python.exe", "pythonw.exe")
                    cmd = f'"{pyw}" "{os.path.abspath(sys.argv[0])}"'
                if hidden:
                    cmd += " --tray"
                winreg.SetValueEx(key, "ArrabonaNaptar", 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, "ArrabonaNaptar")
                except FileNotFoundError:
                    pass
        finally:
            winreg.CloseKey(key)
        return True
    except OSError:
        return False
