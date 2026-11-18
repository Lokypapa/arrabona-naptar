# -*- coding: utf-8 -*-
"""Arrabona Naptár - indító.  Futtatás:  python arrabona_naptar.py"""
import sys
import threading
import tkinter as tk
from tkinter import messagebox

from anaptar import APP_NAME

MUTEX_NAME = "Local\\ArrabonaNaptar_SingleInstance"
SHOW_EVENT = "Local\\ArrabonaNaptar_Show"   # a masodik peldany ezzel hozza elo az elsot
_handles = []


def _k32():
    import ctypes
    from ctypes import c_bool, c_uint32, c_void_p, c_wchar_p
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.restype = c_void_p
    k.CreateMutexW.argtypes = [c_void_p, c_bool, c_wchar_p]
    k.CreateEventW.restype = c_void_p
    k.CreateEventW.argtypes = [c_void_p, c_bool, c_bool, c_wchar_p]
    k.OpenEventW.restype = c_void_p
    k.OpenEventW.argtypes = [c_uint32, c_bool, c_wchar_p]
    k.SetEvent.argtypes = [c_void_p]
    k.CloseHandle.argtypes = [c_void_p]
    k.WaitForSingleObject.restype = c_uint32
    k.WaitForSingleObject.argtypes = [c_void_p, c_uint32]
    return k, ctypes


def single_instance():
    """Egyszerre csak egy peldany fusson (ket peldany felulirhatna egymas menteset)."""
    if sys.platform != "win32":
        return True
    try:
        k, ctypes = _k32()
        h = k.CreateMutexW(None, False, MUTEX_NAME)
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            return False
        _handles.append(h)
        return True
    except Exception:
        return True


def wake_existing():
    """Mar fut egy peldany (pl. a talcan): szolunk neki, hogy jojjon elo."""
    try:
        k, _ = _k32()
        h = k.OpenEventW(0x0002, False, SHOW_EVENT)  # EVENT_MODIFY_STATE
        if not h:
            return False
        k.SetEvent(h)
        k.CloseHandle(h)
        return True
    except Exception:
        return False


def listen_for_wake(callback):
    if sys.platform != "win32":
        return
    try:
        k, _ = _k32()
        h = k.CreateEventW(None, False, False, SHOW_EVENT)  # automatikusan visszaallo
        if not h:
            return
        _handles.append(h)

        def loop():
            while True:
                if k.WaitForSingleObject(h, 0xFFFFFFFF) == 0:
                    callback()
        threading.Thread(target=loop, daemon=True).start()
    except Exception:
        pass


def dpi_aware():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def _info(text, error=False):
    r = tk.Tk()
    r.withdraw()
    (messagebox.showerror if error else messagebox.showinfo)(APP_NAME, text)
    r.destroy()


def main():
    dpi_aware()
    if not single_instance():
        if not wake_existing():
            _info("Az Arrabona Naptár már fut (a tálcán találod).")
        return
    try:
        from anaptar.ui import NaptarApp
    except ImportError as ex:
        _info(f"Hiányzó csomag: {ex}\n\nTelepítés:  pip install -r requirements.txt", error=True)
        return
    root = tk.Tk()
    app = NaptarApp(root, start_hidden="--tray" in sys.argv)
    listen_for_wake(lambda: app.call_ui(app.show_window))
    root.mainloop()


if __name__ == "__main__":
    main()
