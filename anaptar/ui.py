# -*- coding: utf-8 -*-
"""Arrabona Naptár - felület (tkinter). Havi nézet hétszámokkal, heti nézet, lista,
napi panel (névnap, ünnep, jeles napok, események), emlékeztetők, tálca."""
import datetime as _dt
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME, VERSION
from . import esemenyek as ev
import webbrowser

from . import feliratkozas, ical, idojaras, mobil, muszak, nevnapok, szabadsag, szerver, unnepek, updater
from .common import (COLORS, load_settings, res_path, save_settings, set_autostart, store_path)

try:
    from PIL import Image, ImageFilter, ImageTk
except Exception:
    Image = ImageFilter = ImageTk = None
try:
    import pystray
except Exception:
    pystray = None

FONT = "Segoe UI"
H = unnepek.HONAPOK
HR = ("jan.", "febr.", "márc.", "ápr.", "máj.", "jún.", "júl.", "aug.", "szept.", "okt.", "nov.", "dec.")
NAP = unnepek.NAPOK
NAPR = unnepek.NAPOK_ROVID
REMINDER_CHOICES = [(0, "Az esemény idején"), (10, "10 perccel előtte"), (15, "15 perccel előtte"),
                    (30, "30 perccel előtte"), (60, "1 órával előtte"), (120, "2 órával előtte"),
                    (1440, "1 nappal előtte"), (2880, "2 nappal előtte"), (10080, "1 héttel előtte")]
ALLDAY_REMINDER_CHOICES = [(0, "Aznap reggel"), (1440, "1 nappal előtte"), (2880, "2 nappal előtte"),
                           (4320, "3 nappal előtte"), (10080, "1 héttel előtte"), (20160, "2 héttel előtte")]


def hu_date(d, year=True, weekday=False):
    s = (f"{d.year}. " if year else "") + f"{H[d.month - 1]} {d.day}."
    return s + (f", {NAP[d.weekday()]}" if weekday else "")


def watched_on(store, d):
    """[v1.2.0] A nap figyelt névnapjai: [(név, figyelt-bejegyzés)]. A bővített névnaptár is számít;
    ha egy figyelt névhez konkrét nap van megadva ("day": "MM-DD"), csak azon a napon jelez."""
    if not store.watched:
        return []
    key = nevnapok._key(d)                                      # szökőév-független kulcs
    out = []
    names = {n.casefold(): n for n in nevnapok.all_names_for(d)}
    for w in store.watched:
        n = names.get(w["name"].casefold())
        if n and (not w.get("day") or w["day"] == key):
            out.append((n, w))
    return out


def parse_date(s, default_year=None):
    """'2026.11.18', '2026-11-18', '2026. november 18.', '11.18', '11/18', '18' -> date vagy None."""
    s = (s or "").strip().lower().rstrip(".").replace(" ", "")
    if not s:
        return None
    for i, name in enumerate(H):
        s = s.replace(name, f"{i + 1}.")
    import re
    parts = [p for p in re.split(r"[.\-/]+", s) if p]
    today = _dt.date.today()
    y = default_year or today.year
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    try:
        if len(nums) == 3:
            return _dt.date(nums[0], nums[1], nums[2])
        if len(nums) == 2:
            return _dt.date(y, nums[0], nums[1])
        if len(nums) == 1:
            return _dt.date(today.year, today.month, nums[0])
    except ValueError:
        return None
    return None


def parse_time(s):
    s = (s or "").strip().replace(".", ":")
    if not s:
        return ""
    if s.isdigit() and len(s) <= 2:
        s += ":00"
    elif s.isdigit() and len(s) in (3, 4):
        s = s[:-2] + ":" + s[-2:]
    try:
        h, m = [int(x) for x in s.split(":")[:2]]
        if 0 <= h <= 23 and 0 <= m <= 59:
            return f"{h:02d}:{m:02d}"
    except ValueError:
        pass
    return None


def load_logo(size):
    if Image is None:
        return None
    try:
        img = Image.open(res_path("assets", "logo_naptar.png")).convert("RGBA")
        return ImageTk.PhotoImage(img.resize((size, size), Image.LANCZOS))
    except Exception:
        return None


def btn(parent, text, cmd, primary=False, danger=False, small=False, **kw):
    if primary:
        bg, fg, abg = COLORS['brand'], COLORS['white'], COLORS['brand_dark']
    elif danger:
        bg, fg, abg = COLORS['bad'], COLORS['white'], COLORS['bad']
    else:
        bg, fg, abg = COLORS['panel_head'], COLORS['text'], COLORS['divider']
    return tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, activebackground=abg,
                     activeforeground=fg, relief=tk.FLAT, bd=0, padx=8 if small else 12,
                     pady=3 if small else 6, font=(FONT, 9 if small else 10, "bold" if primary else "normal"),
                     cursor="hand2", **kw)


def entry(parent, var, width=30):
    return tk.Entry(parent, textvariable=var, width=width, font=(FONT, 11), bg=COLORS['entry'],
                    fg=COLORS['text'], insertbackground=COLORS['text'], relief=tk.FLAT,
                    highlightthickness=1, highlightbackground=COLORS['divider'],
                    highlightcolor=COLORS['brand'])


def label(parent, text="", soft=False, size=10, bold=False, bg=None, fg=None, **kw):
    return tk.Label(parent, text=text, bg=bg or COLORS['panel'],
                    fg=fg or (COLORS['text_soft'] if soft else COLORS['text']),
                    font=(FONT, size, "bold" if bold else "normal"), **kw)


def check(parent, text, var, bg=None, **kw):
    bg = bg or COLORS['panel']
    return tk.Checkbutton(parent, text=text, variable=var, bg=bg, fg=COLORS['text'],
                          selectcolor=COLORS['entry'], activebackground=bg,
                          activeforeground=COLORS['text'], font=(FONT, 10), **kw)


def _blend(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{int(x + (y - x) * t):02x}" for x, y in zip(a, b))


# ======================================================================
#  Főablak
# ======================================================================

class NaptarApp:
    def __init__(self, root, start_hidden=False):
        self.root = root
        self.settings = load_settings()
        self.store = ev.Store(store_path())
        self.subs = feliratkozas.Subscriptions(self.store, self.settings)   # [v1.3.0] külső naptárak
        self._syncing = set()
        self._pub_last = None
        self._pub_pending = False
        self._mob_last = None           # [v1.5.0] telefonos adatfájl utolsó tartalma
        self._srv_last = None           # [v1.6.0] a szerverre utoljára feltöltött tartalom
        self._srv_busy = False
        self._srv_force = False
        self.srv_state = ""
        self.store.on_save = self._schedule_publish
        self.today = _dt.date.today()
        self.sel = self.today
        self.view = self.settings.get("view", "month") if self.settings.get("view") in ("month", "week", "list", "todo") \
            else "month"
        self.icon = None
        self._q = queue.Queue()
        self._popups = []
        self._tray_hint_shown = False
        self._icon_img = None
        self.paint_code = None          # [v1.1.0] műszak-"festés": None = ki, "" = törlés, kód
        self.weather = idojaras.load_cache()      # [v1.4.0]
        self._weather_busy = False
        self.update_info = None
        self._upd_shown = False

        root.title(f"{APP_NAME} v{VERSION}")
        root.geometry("1180x760")
        root.minsize(980, 640)
        root.configure(bg=COLORS['bg'])
        self._set_icon()
        self._style()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._build()
        self.render()
        self.build_tray()
        root.after(100, self._poll_q)
        root.after(2000, self._reminder_tick)
        root.after(60000, self._midnight_check)
        root.after(3000, self._sync_tick)
        root.after(4000, self._publish_now)
        root.after(8000, self._phone_poll)
        root.after(6000, self._server_tick)
        root.after(1500, self._weather_tick)
        root.after(updater.FIRST_CHECK_MS, self._update_cycle)
        self._tick_clock()
        if start_hidden and self.icon is not None:
            root.withdraw()

    # ---------- alap ----------
    def call_ui(self, fn):
        self._q.put(fn)

    def _poll_q(self):
        try:
            while True:
                fn = self._q.get_nowait()
                try:
                    fn()
                except tk.TclError:
                    pass
        except queue.Empty:
            pass
        self.root.after(100, self._poll_q)

    def _set_icon(self):
        ico = res_path("assets", "logo_naptar.ico")
        if sys.platform == "win32" and os.path.exists(ico):
            try:
                self.root.iconbitmap(default=ico)
            except Exception:
                pass
        self._icon_img = load_logo(64)
        if self._icon_img is not None:
            try:
                self.root.iconphoto(True, self._icon_img)
            except Exception:
                pass

    def _style(self):
        st = ttk.Style(self.root)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("Treeview", background=COLORS['panel'], fieldbackground=COLORS['panel'],
                     foreground=COLORS['text'], rowheight=26, borderwidth=0, font=(FONT, 10))
        st.map("Treeview", background=[("selected", COLORS['select'])],
               foreground=[("selected", COLORS['text'])])
        st.configure("Treeview.Heading", background=COLORS['panel_head'], foreground=COLORS['text'],
                     relief="flat", font=(FONT, 10, "bold"))
        st.configure("TCombobox", fieldbackground=COLORS['entry'], background=COLORS['panel_head'],
                     foreground=COLORS['text'], arrowcolor=COLORS['text_soft'])
        st.map("TCombobox", fieldbackground=[("readonly", COLORS['entry'])],
               foreground=[("readonly", COLORS['text'])])
        st.configure("Vertical.TScrollbar", background=COLORS['panel_head'], troughcolor=COLORS['panel'],
                     bordercolor=COLORS['panel'], arrowcolor=COLORS['text_soft'])
        self.root.option_add("*TCombobox*Listbox.background", COLORS['entry'])
        self.root.option_add("*TCombobox*Listbox.foreground", COLORS['text'])

    # ---------- váz ----------
    def _build(self):
        r = self.root
        head = tk.Frame(r, bg=COLORS['brand'], height=64)
        head.pack(fill=tk.X)
        head.pack_propagate(False)
        self._logo = load_logo(40)
        if self._logo is not None:
            tk.Label(head, image=self._logo, bg=COLORS['brand']).pack(side=tk.LEFT, padx=(16, 8))
        tk.Label(head, text=APP_NAME, bg=COLORS['brand'], fg=COLORS['white'],
                 font=(FONT, 18, "bold")).pack(side=tk.LEFT, padx=(4 if self._logo else 16, 6))
        tk.Label(head, text=f"v{VERSION}", bg=COLORS['brand'], fg="#d5f5e3",
                 font=(FONT, 9)).pack(side=tk.LEFT, pady=(10, 0))
        hb = dict(bg=COLORS['brand_dark'], fg=COLORS['white'], activebackground="#176b3b",
                  activeforeground=COLORS['white'], relief=tk.FLAT, bd=0, padx=12, pady=6,
                  font=(FONT, 10), cursor="hand2")
        tk.Button(head, text="Beállítások", command=self.open_settings, **hb).pack(side=tk.RIGHT, padx=(6, 16))
        tk.Button(head, text="Névnap-kereső", command=self.open_name_search, **hb).pack(side=tk.RIGHT, padx=6)
        tk.Button(head, text="Naptárak", command=self.open_calendars, **hb).pack(side=tk.RIGHT, padx=6)
        # [v1.4.0] pontos idő másodperccel
        ck = tk.Frame(head, bg=COLORS['brand'])
        ck.pack(side=tk.RIGHT, padx=(0, 22))
        self.clock_lbl = tk.Label(ck, text="", bg=COLORS['brand'], fg=COLORS['white'], font=("Consolas", 20, "bold"))
        self.clock_lbl.pack(anchor="e")
        self.clock_sub = tk.Label(ck, text="", bg=COLORS['brand'], fg="#d5f5e3", font=(FONT, 9))
        self.clock_sub.pack(anchor="e")

        # [v1.4.0] frissítés-sáv (rejtve)
        self.upd_banner = tk.Frame(r, bg="#e67e22")
        self.upd_lbl = tk.Label(self.upd_banner, text="", bg="#e67e22", fg="white", font=(FONT, 10, "bold"))
        self.upd_lbl.pack(side=tk.LEFT, padx=(14, 8), pady=7)
        self.upd_btn = tk.Button(self.upd_banner, text="Telepítés és újraindítás", command=self.install_update,
                                 font=(FONT, 9, "bold"), fg="white", bg="#b5561a", activebackground="#9a4a16",
                                 activeforeground="white", relief=tk.FLAT, bd=0, cursor="hand2", padx=10, pady=3)
        self.upd_btn.pack(side=tk.LEFT, pady=7)
        tk.Button(self.upd_banner, text="Mi változott?", command=lambda: self.update_info and webbrowser.open(
            self.update_info["url"]), font=(FONT, 9), fg="white", bg="#e67e22", activebackground="#d35400",
                  activeforeground="white", relief=tk.FLAT, bd=0, cursor="hand2").pack(side=tk.LEFT, padx=10)

        tb = tk.Frame(r, bg=COLORS['bg'])
        tb.pack(fill=tk.X, padx=16, pady=(12, 8))
        self._tb = tb
        btn(tb, "+ Új esemény", lambda: self.new_event(), primary=True).pack(side=tk.LEFT)
        btn(tb, "+ Születésnap", lambda: self.new_event(kind="birthday")).pack(side=tk.LEFT, padx=6)
        self.shift_btn = btn(tb, "Műszak", self.toggle_paint)
        self.shift_btn.pack(side=tk.LEFT)
        tk.Frame(tb, bg=COLORS['bg'], width=16).pack(side=tk.LEFT)
        btn(tb, "Ma", self.go_today).pack(side=tk.LEFT)
        btn(tb, "◀", lambda: self.move(-1)).pack(side=tk.LEFT, padx=(6, 0))
        btn(tb, "▶", lambda: self.move(1)).pack(side=tk.LEFT, padx=(2, 0))

        self.search_var = tk.StringVar()
        se = entry(tb, self.search_var, width=20)
        se.pack(side=tk.RIGHT, ipady=4)
        se.bind("<Return>", lambda e: self.do_search())
        tk.Label(tb, text="Keresés:", bg=COLORS['bg'], fg=COLORS['text_soft'], font=(FONT, 10)).pack(side=tk.RIGHT, padx=(16, 6))
        self.view_btns = {}
        for key, txt in (("todo", "Teendők"), ("list", "Lista"), ("week", "Hét"), ("month", "Hónap")):
            b = btn(tb, txt, lambda k=key: self.set_view(k))
            b.pack(side=tk.RIGHT, padx=1)
            self.view_btns[key] = b
        # [v1.2.1] a cím a jobb oldali gombok UTÁN kerül fel, így szűk ablakban a cím vége rövidül,
        # nem a gombok vagy a cím eleje tűnik el
        self.title_lbl = tk.Label(tb, text="", bg=COLORS['bg'], fg=COLORS['text'], font=(FONT, 15, "bold"),
                                  anchor="w")
        self.title_lbl.pack(side=tk.LEFT, padx=14, fill=tk.X, expand=True)

        self.paint_bar = tk.Frame(r, bg=COLORS['bg'])     # [v1.1.0] műszak-gombsor (rejtve)
        self._body_anchor = tk.Frame(r, bg=COLORS['bg'], height=0)
        self._body_anchor.pack(fill=tk.X)
        body = tk.Frame(r, bg=COLORS['bg'])
        body.pack(fill=tk.BOTH, expand=True, padx=16)
        self.side_outer = tk.Frame(body, bg=COLORS['panel'], width=340, highlightthickness=1,
                                   highlightbackground=COLORS['divider'])
        self.side_outer.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        self.side_outer.pack_propagate(False)
        self.side = ScrollFrame(self.side_outer)                 # [v1.4.0] görgethető oldalpanel
        self.side.pack(fill=tk.BOTH, expand=True)
        self.main = tk.Frame(body, bg=COLORS['panel'], highlightthickness=1,
                             highlightbackground=COLORS['divider'])
        self.main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.status = tk.Label(r, text="", bg=COLORS['bg'], fg=COLORS['text_soft'], font=(FONT, 9), anchor="w")
        self.status.pack(fill=tk.X, padx=18, pady=(6, 8))

        r.bind("<Control-n>", lambda e: self.new_event())
        r.bind("<Prior>", lambda e: self.move(-1))
        r.bind("<Next>", lambda e: self.move(1))
        r.bind("<Home>", lambda e: self.go_today())
        r.bind("<Control-f>", lambda e: (se.focus_set(), "break")[1])

    # ---------- navigáció ----------
    def set_view(self, v):
        self.view = v
        self.settings["view"] = v
        save_settings(self.settings)
        self.render()

    def go_today(self):
        self.today = _dt.date.today()
        self.sel = self.today
        self.render()

    def move(self, step):
        d = self.sel
        if self.view == "month":
            y, m = divmod(d.month - 1 + step, 12)
            y += d.year
            import calendar
            self.sel = _dt.date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))
        elif self.view == "week":
            self.sel = d + _dt.timedelta(weeks=step)
        else:
            self.sel = d + _dt.timedelta(days=30 * step)
        self.render()

    def select(self, d, rerender=True):
        month_changed = (d.year, d.month) != (self.sel.year, self.sel.month)
        self.sel = d
        if rerender and (month_changed or self.view != "month"):
            self.render()
        else:
            self._paint_selection()
            self.render_side()

    # ---------- rajzolás ----------
    def swaps(self):
        return self.store.swaps()

    def render(self):
        for k, b in self.view_btns.items():
            on = k == self.view
            b.config(bg=COLORS['brand'] if on else COLORS['panel_head'],
                     fg=COLORS['white'] if on else COLORS['text'])
        for w in self.main.winfo_children():
            w.destroy()
        if self.view == "month":
            self.title_lbl.config(text=f"{self.sel.year}. {H[self.sel.month - 1]}")
            self.render_month()
        elif self.view == "week":
            mon = self.sel - _dt.timedelta(days=self.sel.weekday())
            sun = mon + _dt.timedelta(days=6)
            if mon.month == sun.month:
                rng = f"{H[mon.month - 1]} {mon.day}–{sun.day}."
            else:
                rng = f"{HR[mon.month - 1]} {mon.day}. – {HR[sun.month - 1]} {sun.day}."
            self.title_lbl.config(text=f"{mon.year}. {unnepek.iso_week(mon)}. hét · {rng}")
            self.render_week()
        elif self.view == "todo":
            n = sum(1 for t in self.store.todos if not t["done"])
            self.title_lbl.config(text=f"Teendők – {n} nyitott")
            self.render_todo()
        else:
            self.title_lbl.config(text=f"Lista – {hu_date(self.sel)[:-1]}-tól, 90 nap")
            self.render_list()
        self.render_side()
        self.update_status()

    def update_status(self):
        t = self.today
        names = ", ".join(nevnapok.names_for(t)) or "–"
        doy = t.timetuple().tm_yday
        left = (_dt.date(t.year, 12, 31) - t).days
        self.status.config(text=f"Ma: {hu_date(t, weekday=True)}  ·  {unnepek.iso_week(t)}. hét  ·  "
                                f"Névnap: {names}  ·  Az év {doy}. napja, még {left} nap van hátra")

    # --- havi nézet
    def render_month(self):
        y, m = self.sel.year, self.sel.month
        first = _dt.date(y, m, 1)
        start = first - _dt.timedelta(days=first.weekday())
        days = [start + _dt.timedelta(days=i) for i in range(42)]
        inst = ev.instances(self.all_events(), days[0], days[-1])
        by_day = {}
        for occ, e in inst:
            for i in range((max(0, ((ev._d(e.get("end_date")) or occ) - (ev._d(e["date"]) or occ)).days)) + 1):
                dd = occ + _dt.timedelta(days=i)
                by_day.setdefault(dd, []).append((occ, e))
        watched = {w["name"].casefold(): w for w in self.store.watched}
        g = tk.Frame(self.main, bg=COLORS['divider'])
        g.pack(fill=tk.BOTH, expand=True)
        g.columnconfigure(0, weight=0, minsize=34)
        for c in range(1, 8):
            g.columnconfigure(c, weight=1, uniform="day")
        hdr_bg = COLORS['panel_head']
        tk.Label(g, text="hét", bg=hdr_bg, fg=COLORS['text_soft'], font=(FONT, 8)).grid(
            row=0, column=0, sticky="nsew", padx=(0, 1), pady=(0, 1))
        for c, n in enumerate(NAP):
            tk.Label(g, text=n, bg=hdr_bg, fg=COLORS['holiday'] if c == 6 else COLORS['text'],
                     font=(FONT, 10, "bold")).grid(row=0, column=c + 1, sticky="nsew", padx=(0, 1), pady=(0, 1))
        self.cells = {}
        swaps = self.swaps()
        for row in range(6):
            g.rowconfigure(row + 1, weight=1, uniform="wk")
            wk_day = days[row * 7]
            wl = tk.Label(g, text=str(unnepek.iso_week(wk_day)), bg=hdr_bg, fg=COLORS['brand'],
                          font=(FONT, 10, "bold"), cursor="hand2")
            wl.grid(row=row + 1, column=0, sticky="nsew", padx=(0, 1), pady=(0, 1))
            wl.bind("<Button-1>", lambda e, d=wk_day: (setattr(self, "sel", d), self.set_view("week")))
            for col in range(7):
                d = days[row * 7 + col]
                self._month_cell(g, row + 1, col + 1, d, d.month == m, by_day.get(d, []), watched, swaps)

    def _month_cell(self, g, r, c, d, in_month, items, watched, swaps):
        info = unnepek.day_info(d, swaps)
        bg = COLORS['panel'] if in_month else COLORS['other_month']
        if d == self.today:
            bg = COLORS['today']
        cell = tk.Frame(g, bg=bg, highlightthickness=2, highlightbackground=bg, cursor="hand2")
        cell.grid(row=r, column=c, sticky="nsew", padx=(0, 1), pady=(0, 1))
        cell.grid_propagate(False)
        cell.pack_propagate(False)
        self.cells[d] = (cell, bg)
        top = tk.Frame(cell, bg=bg)
        top.pack(fill=tk.X, padx=4, pady=(2, 0))
        num_fg = COLORS['holiday'] if info["red"] else COLORS['text']
        if not in_month:
            num_fg = _blend(num_fg, bg, 0.55)
        tk.Label(top, text=str(d.day), bg=bg, fg=num_fg,
                 font=(FONT, 12, "bold" if d == self.today else "normal")).pack(side=tk.LEFT)
        sh = self.store.shift_on(d)
        if sh:                                                   # [v1.1.0] műszak-jelvény
            tk.Label(top, text=sh["code"], bg=sh["color"] if in_month else _blend(sh["color"], bg, 0.5),
                     fg="#ffffff", font=(FONT, 8, "bold"), padx=3).pack(side=tk.LEFT, padx=(4, 0))
        wd = self.weather_for(d)                                  # [v1.4.0] időjárás-ikon
        if wd:
            tk.Label(top, text=f"{idojaras.describe(wd['code'])[0]}{idojaras.fmt_t(wd['tmax'])}", bg=bg,
                     fg=_blend(COLORS['text'], bg, 0.15 if in_month else 0.55), font=(FONT, 8)).pack(side=tk.RIGHT)
        if self.settings.get("show_namedays", True):
            names = nevnapok.names_for(d)
            hit = [n for n, _w in watched_on(self.store, d)]
            names += [n for n in hit if n not in names]          # figyelt bővített név is látszik
            txt = ", ".join(names)
            tk.Label(top, text=("★ " if hit else "") + txt, bg=bg,
                     fg=COLORS['warn'] if hit else _blend(COLORS['text_soft'], bg, 0.25 if in_month else 0.6),
                     font=(FONT, 8, "bold" if hit else "normal"), anchor="e").pack(side=tk.RIGHT, fill=tk.X)
        lines = []
        if info["holiday"]:
            lines.append((info["holiday"], COLORS['holiday'], None, True))
        if info["swap_note"]:
            lines.append(("Munkanap (szombat)" if info["workday_sat"] else "Pihenőnap (áthelyezett)",
                          COLORS['workday'] if info["workday_sat"] else COLORS['holiday'], None, False))
        if self.settings.get("show_jeles", True):
            for j in info["jeles"][:1]:
                lines.append((j, COLORS['text_soft'], None, False))
        for occ, e in items:
            t = (e["time"] + " " if not e.get("all_day") and e.get("time") and occ == d else "")
            lines.append((t + ev.display_title(e, d), COLORS['white'], e.get("color") or COLORS['brand'], False))
        for td in self.store.todos_on(d):                         # [v1.4.0] teendők
            if not td["done"]:
                lines.append(("☐ " + td["title"], COLORS['warn'] if d < self.today else COLORS['text'], None, False))
        maxl = 4
        for i, (txt, fg, ebg, bold) in enumerate(lines[:maxl]):
            lb = tk.Label(cell, text=txt, bg=ebg or bg, fg=fg if in_month or ebg else _blend(fg, bg, 0.5),
                          font=(FONT, 8, "bold" if bold else "normal"), anchor="w", padx=3)
            lb.pack(fill=tk.X, padx=3, pady=(1, 0))
        if len(lines) > maxl:
            tk.Label(cell, text=f"+{len(lines) - maxl} további", bg=bg, fg=COLORS['text_soft'],
                     font=(FONT, 8), anchor="w").pack(fill=tk.X, padx=6)
        for w in [cell] + list(cell.winfo_children()) + list(top.winfo_children()):
            w.bind("<Button-1>", lambda e, dd=d: self._cell_click(dd))
            w.bind("<Double-1>", lambda e, dd=d: None if self.paint_code is not None else self.new_event(day=dd))
            w.bind("<Button-3>", lambda e, dd=d: self._shift_menu(e, dd))
        if d == self.sel:
            cell.config(highlightbackground=COLORS['brand'])

    def _paint_selection(self):
        for d, (cell, bg) in getattr(self, "cells", {}).items():
            try:
                cell.config(highlightbackground=COLORS['brand'] if d == self.sel else bg)
            except tk.TclError:
                pass

    # --- heti nézet
    def render_week(self):
        mon = self.sel - _dt.timedelta(days=self.sel.weekday())
        days = [mon + _dt.timedelta(days=i) for i in range(7)]
        inst = ev.instances(self.all_events(), days[0], days[-1])
        g = tk.Frame(self.main, bg=COLORS['divider'])
        g.pack(fill=tk.BOTH, expand=True)
        swaps = self.swaps()
        self.cells = {}
        for c, d in enumerate(days):
            g.columnconfigure(c, weight=1, uniform="d")
            info = unnepek.day_info(d, swaps)
            bg = COLORS['today'] if d == self.today else COLORS['panel']
            col = tk.Frame(g, bg=bg, highlightthickness=2,
                           highlightbackground=COLORS['brand'] if d == self.sel else bg)
            col.grid(row=0, column=c, sticky="nsew", padx=(0, 1))
            self.cells[d] = (col, bg)
            g.rowconfigure(0, weight=1)
            hd = tk.Frame(col, bg=COLORS['panel_head'])
            hd.pack(fill=tk.X)
            tk.Label(hd, text=f"{NAP[d.weekday()]}", bg=COLORS['panel_head'],
                     fg=COLORS['holiday'] if info["red"] else COLORS['text'], font=(FONT, 10, "bold")).pack(pady=(6, 0))
            tk.Label(hd, text=f"{HR[d.month - 1]} {d.day}.", bg=COLORS['panel_head'],
                     fg=COLORS['holiday'] if info["red"] else COLORS['text'], font=(FONT, 15, "bold")).pack()
            tk.Label(hd, text=", ".join(nevnapok.names_for(d)), bg=COLORS['panel_head'], fg=COLORS['text_soft'],
                     font=(FONT, 8), wraplength=130).pack(pady=(0, 2))
            wd = self.weather_for(d)
            tk.Label(hd, text=(f"{idojaras.describe(wd['code'])[0]} {idojaras.fmt_t(wd['tmax'])} / "
                               f"{idojaras.fmt_t(wd['tmin'])}") if wd else "", bg=COLORS['panel_head'],
                     fg=COLORS['text'], font=(FONT, 9)).pack(pady=(0, 6))
            sh = self.store.shift_on(d)
            if sh:
                tk.Label(hd, text=f"{sh['name']} {muszak.label_time(sh)}", bg=sh["color"], fg="#ffffff",
                         font=(FONT, 8, "bold")).pack(fill=tk.X)
            if info["holiday"]:
                label(col, info["holiday"], bg=bg, fg=COLORS['holiday'], size=9, bold=True, wraplength=140).pack(fill=tk.X, padx=4, pady=(4, 0))
            if info["swap_note"]:
                label(col, info["swap_note"], bg=bg, fg=COLORS['workday'] if info["workday_sat"] else COLORS['holiday'],
                      size=8, wraplength=140).pack(fill=tk.X, padx=4, pady=(2, 0))
            for j in info["jeles"]:
                label(col, j, bg=bg, soft=True, size=8, wraplength=140).pack(fill=tk.X, padx=4, pady=(2, 0))
            for td in self.store.todos_on(d):
                tl = label(col, ("☑ " if td["done"] else "☐ ") + td["title"], bg=bg, size=9, wraplength=140,
                           fg=COLORS['text_soft'] if td["done"] else COLORS['text'], justify=tk.LEFT, cursor="hand2")
                tl.pack(fill=tk.X, padx=4, pady=(4, 0))
                tl.bind("<Double-1>", lambda e_, tid=td["id"]: (self.store.toggle_todo(tid), self.render()))
            for occ, e in inst:
                if not ev.covers(e, occ, d):
                    continue
                t = "Egész nap" if e.get("all_day") else (e["time"] + (f"–{e['end_time']}" if e.get("end_time") else ""))
                box = tk.Frame(col, bg=e.get("color") or COLORS['brand'], cursor="hand2")
                box.pack(fill=tk.X, padx=4, pady=(6, 0))
                l1 = tk.Label(box, text=t, bg=box["bg"], fg="#ffffff", font=(FONT, 8), anchor="w")
                l1.pack(fill=tk.X, padx=4, pady=(2, 0))
                l2 = tk.Label(box, text=ev.display_title(e, d), bg=box["bg"], fg="#ffffff",
                              font=(FONT, 9, "bold"), anchor="w", wraplength=140, justify=tk.LEFT)
                l2.pack(fill=tk.X, padx=4, pady=(0, 3))
                for w in (box, l1, l2):
                    w.bind("<Double-1>", lambda ev_, ee=e, oc=occ: self.edit_event(ee, oc))
            for w in [col] + list(col.winfo_children()) + list(hd.winfo_children()):
                w.bind("<Button-1>", lambda e, dd=d: self.select(dd, rerender=False), add="+")

    # --- lista nézet
    def render_list(self):
        top = tk.Frame(self.main, bg=COLORS['panel'])
        top.pack(fill=tk.X, padx=10, pady=(8, 4))
        self.list_jeles = getattr(self, "list_jeles", tk.BooleanVar(value=False))
        check(top, "Jeles napok is", self.list_jeles, command=self.render).pack(side=tk.LEFT)
        self.list_shifts = getattr(self, "list_shifts", tk.BooleanVar(value=False))
        check(top, "Műszakok is", self.list_shifts, command=self.render).pack(side=tk.LEFT, padx=(8, 0))
        label(top, "  (a következő 90 nap; dupla kattintás: szerkesztés)", soft=True, size=9).pack(side=tk.LEFT)
        tf = tk.Frame(self.main, bg=COLORS['panel'])
        tf.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        tr = ttk.Treeview(tf, columns=("date", "time", "what", "kind"), show="headings")
        for c, t, w in (("date", "Dátum", 190), ("time", "Idő", 90), ("what", "Mi", 420), ("kind", "Típus", 120)):
            tr.heading(c, text=t, anchor="w")
            tr.column(c, width=w, anchor="w", stretch=c == "what")
        sb = ttk.Scrollbar(tf, orient=tk.VERTICAL, command=tr.yview)
        tr.configure(yscrollcommand=sb.set)
        tr.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        tr.tag_configure("holiday", foreground=COLORS['holiday'])
        tr.tag_configure("soft", foreground=COLORS['text_soft'])
        tr.tag_configure("watch", foreground=COLORS['warn'])
        start, end = self.sel, self.sel + _dt.timedelta(days=90)
        rows = []
        swaps = self.swaps()
        for occ, e in ev.instances(self.all_events(), start, end):
            t = "egész nap" if e.get("all_day") else e["time"] + (f"–{e['end_time']}" if e.get("end_time") else "")
            rows.append((occ, 1, t, ev.display_title(e, occ), "Születésnap" if e["kind"] == "birthday" else "Esemény",
                         "", ("ev", e["id"], occ.isoformat())))
        watched = {w["name"].casefold(): w for w in self.store.watched}
        d = start
        while d <= end:
            info = unnepek.day_info(d, swaps)
            if info["holiday"]:
                rows.append((d, 0, "", info["holiday"], "Ünnep", "holiday", None))
            if info["swap_note"]:
                rows.append((d, 0, "", info["swap_note"], "Munkarend", "holiday", None))
            for n, w in watched_on(self.store, d):
                rows.append((d, 0, "", f"Névnap: {n}" + (f" ({w['label']})" if w.get("label") else ""),
                             "Figyelt névnap", "watch", None))
            if self.list_shifts.get():
                sh = self.store.shift_on(d)
                if sh:
                    rows.append((d, 1, sh.get("start", ""), f"{sh['name']} {muszak.label_time(sh)}".strip(),
                                 "Műszak", "", None))
            if self.list_jeles.get():
                for j in info["jeles"]:
                    rows.append((d, 2, "", j, "Jeles nap", "soft", None))
            d += _dt.timedelta(days=1)
        rows.sort(key=lambda x: (x[0], x[1], x[2]))
        self._list_keys = {}
        for i, (dd, _, t, what, kind, tag, key) in enumerate(rows):
            iid = f"r{i}"
            tr.insert("", tk.END, iid=iid, values=(hu_date(dd, weekday=True), t, what, kind),
                      tags=(tag,) if tag else ())
            self._list_keys[iid] = (dd, key)
        tr.bind("<<TreeviewSelect>>", lambda e: self._list_pick(tr, False))
        tr.bind("<Double-1>", lambda e: self._list_pick(tr, True))
        if not rows:
            label(self.main, "Nincs semmi a következő 90 napban.", soft=True).pack(pady=20)

    def _list_pick(self, tr, edit):
        sel = tr.selection()
        if not sel:
            return
        dd, key = self._list_keys.get(sel[0], (None, None))
        if dd is None:
            return
        self.sel = dd
        self.render_side()
        if edit and key and key[0] == "ev":
            e = self.get_event(key[1])
            if e:
                self.edit_event(e, _dt.date.fromisoformat(key[2]))

    # --- napi panel
    def render_side(self):
        s = self.side.inner
        for w in s.winfo_children():
            w.destroy()
        self.side.to_top()
        d = self.sel
        info = unnepek.day_info(d, self.swaps())
        pad = dict(padx=16)
        label(s, f"{d.year}. {H[d.month - 1]}", soft=True, size=10).pack(anchor="w", pady=(14, 0), **pad)
        label(s, f"{d.day}.", size=30, bold=True,
              fg=COLORS['holiday'] if info["red"] else COLORS['text']).pack(anchor="w", **pad)
        doy = d.timetuple().tm_yday
        rel = (d - self.today).days
        when = "ma" if rel == 0 else ("holnap" if rel == 1 else "tegnap" if rel == -1 else
                                       (f"{rel} nap múlva" if rel > 0 else f"{-rel} napja"))
        label(s, f"{NAP[d.weekday()]}  ·  {unnepek.iso_week(d)}. hét  ·  {when}", size=10).pack(anchor="w", **pad)
        label(s, f"Az év {doy}. napja · {'munkanap' if not info['off'] else 'pihenőnap'}",
              soft=True, size=9).pack(anchor="w", pady=(0, 8), **pad)
        names = nevnapok.names_for(d)
        nf = tk.Frame(s, bg=COLORS['panel'])
        nf.pack(fill=tk.X, **pad)
        label(nf, "Névnap:", soft=True, size=9).pack(side=tk.LEFT)
        label(nf, ", ".join(names) if names else "– (szökőnap)", bold=True, size=11,
              wraplength=230, justify=tk.LEFT).pack(side=tk.LEFT, padx=(6, 0))
        extra = nevnapok.extra_names_for(d)                       # [v1.2.0] bővített névnaptár
        if extra:
            label(s, "További névnapok: " + ", ".join(extra), soft=True, size=9,
                  wraplength=290, justify=tk.LEFT).pack(anchor="w", pady=(2, 0), **pad)
        if info["holiday"]:
            label(s, info["holiday"], fg=COLORS['holiday'], bold=True, size=11,
                  wraplength=290, justify=tk.LEFT).pack(anchor="w", pady=(8, 0), **pad)
            if info["rest"] and not info["workday_sat"]:
                label(s, "Munkaszüneti nap", soft=True, size=9).pack(anchor="w", **pad)
        if info["swap_note"]:
            label(s, info["swap_note"], bold=True, size=10,
                  fg=COLORS['workday'] if info["workday_sat"] else COLORS['holiday'],
                  wraplength=290, justify=tk.LEFT).pack(anchor="w", pady=(6, 0), **pad)
        for j in info["jeles"]:
            label(s, "• " + j, size=9, wraplength=290, justify=tk.LEFT).pack(anchor="w", pady=(2, 0), **pad)
        self._side_weather(s, d, pad)
        self._side_shift(s, d, pad)
        self._side_leave(s, d, pad)
        tk.Frame(s, bg=COLORS['divider'], height=1).pack(fill=tk.X, pady=10, **pad)
        hf = tk.Frame(s, bg=COLORS['panel'])
        hf.pack(fill=tk.X, **pad)
        label(hf, "Események", bold=True, size=11).pack(side=tk.LEFT)
        btn(hf, "+ Új", lambda: self.new_event(day=self.sel), primary=True, small=True).pack(side=tk.RIGHT)
        items = ev.events_on(self.all_events(), d)
        lst = tk.Frame(s, bg=COLORS['panel'])
        lst.pack(fill=tk.BOTH, expand=True, pady=(6, 0), **pad)
        if not items:
            label(lst, "Erre a napra nincs esemény.\n(Dupla kattintás egy napon: új esemény)",
                  soft=True, size=9, justify=tk.LEFT).pack(anchor="w")
        for occ, e in items:
            row = tk.Frame(lst, bg=COLORS['panel_head'], cursor="hand2")
            row.pack(fill=tk.X, pady=3)
            tk.Frame(row, bg=e.get("color") or COLORS['brand'], width=5).pack(side=tk.LEFT, fill=tk.Y)
            inner = tk.Frame(row, bg=COLORS['panel_head'])
            inner.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8, pady=4)
            t = "Egész nap" if e.get("all_day") else e["time"] + (f"–{e['end_time']}" if e.get("end_time") else "")
            if e["repeat"]["freq"] != "none" and e["kind"] != "birthday":
                t += "  ·  " + ev.FREQ_NAMES[e["repeat"]["freq"]].lower()
            if e.get("reminders"):
                t += "  ·  🔔"
            if e.get("readonly"):
                t += "  ·  " + (e.get("cal_name") or "külső naptár")
            l1 = label(inner, t, soft=True, size=8, bg=COLORS['panel_head'])
            l1.pack(anchor="w")
            l2 = label(inner, ev.display_title(e, d), bold=True, size=10, bg=COLORS['panel_head'],
                       wraplength=230, justify=tk.LEFT)
            l2.pack(anchor="w")
            ws = [row, inner, l1, l2]
            if e.get("location"):
                l3 = label(inner, "📍 " + e["location"], size=9, bg=COLORS['panel_head'], wraplength=230, justify=tk.LEFT)
                l3.pack(anchor="w")
                ws.append(l3)
            if not e.get("readonly"):
                bx = btn(row, "✕", lambda ee=e, oc=occ: self.delete_event(ee, oc), small=True)
                bx.pack(side=tk.RIGHT, padx=4)
            for w in ws:
                w.bind("<Button-1>", lambda ev_, ee=e, oc=occ: self.edit_event(ee, oc))
        self._side_todos(s, d, pad)
        up = self._upcoming_watched(d)
        if up:
            tk.Frame(s, bg=COLORS['divider'], height=1).pack(fill=tk.X, pady=8, **pad)
            label(s, "Közelgő figyelt névnapok", bold=True, size=10).pack(anchor="w", **pad)
            for dd, n, lab in up[:5]:
                label(s, f"{hu_date(dd, year=False)}  {n}" + (f" ({lab})" if lab else ""),
                      size=9, fg=COLORS['warn']).pack(anchor="w", **pad)
        tk.Frame(s, bg=COLORS['panel'], height=10).pack()

    # ---------- [v1.1.0] műszakok ----------
    def _side_shift(self, s, d, pad):
        sh = self.store.shift_on(d)
        sf = tk.Frame(s, bg=COLORS['panel'])
        sf.pack(fill=tk.X, pady=(8, 0), **pad)
        label(sf, "Műszak:", soft=True, size=9).pack(side=tk.LEFT)
        if sh:
            tk.Label(sf, text=f" {sh['code']} ", bg=sh["color"], fg="#ffffff", font=(FONT, 9, "bold")).pack(side=tk.LEFT, padx=(6, 4))
            label(sf, f"{sh['name']} {muszak.label_time(sh)} · {muszak.fmt_h(muszak.hours_of(sh))}",
                  size=9, wraplength=200, justify=tk.LEFT).pack(side=tk.LEFT)
        else:
            label(sf, "–", size=9).pack(side=tk.LEFT, padx=6)
        mb = btn(sf, "▾", lambda: None, small=True)
        mb.pack(side=tk.RIGHT)
        mb.config(command=lambda: self._shift_menu(None, d, widget=mb))
        if any(k.startswith(f"{d.year}-{d.month:02d}-") for k in self.store.shifts):
            sm = muszak.month_summary(self.store.shifts, self.store.shift_types, d.year, d.month, self.swaps())
            card = tk.Frame(s, bg=COLORS['panel_head'])
            card.pack(fill=tk.X, pady=(6, 0), **pad)
            label(card, f"{H[d.month - 1].capitalize()}: {sm['shifts']} műszak, {muszak.fmt_h(sm['work_hours'])}",
                  bold=True, size=9, bg=COLORS['panel_head']).pack(anchor="w", padx=8, pady=(6, 0))
            parts = []
            if sm["leave_hours"]:
                parts.append(f"távollét {muszak.fmt_h(sm['leave_hours'])}")
            if sm["night_hours"]:
                parts.append(f"éjszakai {muszak.fmt_h(sm['night_hours'])}")
            if sm["weekend_hours"]:
                parts.append(f"hétvégi {muszak.fmt_h(sm['weekend_hours'])}")
            if sm["holiday_hours"]:
                parts.append(f"ünnepnapi {muszak.fmt_h(sm['holiday_hours'])}")
            if parts:
                label(card, ", ".join(parts), size=8, bg=COLORS['panel_head'], wraplength=280,
                      justify=tk.LEFT).pack(anchor="w", padx=8)
            diff = sm["diff"]
            col = COLORS['ok'] if abs(diff) < 0.01 else (COLORS['warn'] if diff > 0 else COLORS['text_soft'])
            txt = f"Keret: {muszak.fmt_h(sm['keret'])} · összesen {muszak.fmt_h(sm['total'])}"
            txt += "" if abs(diff) < 0.01 else (f" (+{muszak.fmt_h(diff)} túlóra)" if diff > 0 else
                                                f" ({muszak.fmt_h(-diff)} hiányzik)")
            label(card, txt, size=8, fg=col, bg=COLORS['panel_head'], wraplength=280,
                  justify=tk.LEFT).pack(anchor="w", padx=8, pady=(0, 6))

    def toggle_paint(self):
        if self.paint_code is None:
            self.paint_code = self.store.shift_types[0]["code"] if self.store.shift_types else ""
            if self.view != "month":
                self.view = "month"
        else:
            self.paint_code = None
        self._build_paint_bar()
        self.render()

    def _build_paint_bar(self):
        pb = self.paint_bar
        for w in pb.winfo_children():
            w.destroy()
        if self.paint_code is None:
            pb.pack_forget()
            self.shift_btn.config(bg=COLORS['panel_head'], fg=COLORS['text'])
            return
        self.shift_btn.config(bg=COLORS['brand'], fg=COLORS['white'])
        pb.pack(fill=tk.X, padx=16, pady=(0, 8), before=self._body_anchor)
        label(pb, "Műszak bejelölése: válassz, majd kattints a napokra →", bg=COLORS['bg'], size=9).pack(side=tk.LEFT, padx=(0, 8))
        for t in self.store.shift_types:
            on = self.paint_code == t["code"]
            b = tk.Button(pb, text=t["code"], command=lambda c=t["code"]: self._set_paint(c),
                          bg=t["color"], fg="#ffffff", activebackground=t["color"], relief=tk.SUNKEN if on else tk.FLAT,
                          bd=3 if on else 0, padx=8, pady=3, font=(FONT, 9, "bold"), cursor="hand2")
            b.pack(side=tk.LEFT, padx=2)
        btn(pb, "Törlés", lambda: self._set_paint(""), small=True).pack(side=tk.LEFT, padx=(6, 2))
        btn(pb, "Kész", self.toggle_paint, primary=True, small=True).pack(side=tk.RIGHT)
        btn(pb, "Műszaktípusok…", lambda: ShiftTypesDialog(self), small=True).pack(side=tk.RIGHT, padx=4)
        btn(pb, "Ismétlődő minta…", lambda: PatternDialog(self), small=True).pack(side=tk.RIGHT)
        btn(pb, "Szabadság…", lambda: LeaveDialog(self), small=True).pack(side=tk.RIGHT, padx=4)
        cur = next((t for t in self.store.shift_types if t["code"] == self.paint_code), None)
        label(pb, f"  {cur['name']} {muszak.label_time(cur)}" if cur else "  (törlés)", bg=COLORS['bg'],
              soft=True, size=9).pack(side=tk.LEFT, padx=6)

    def _set_paint(self, code):
        self.paint_code = code
        self._build_paint_bar()

    def _cell_click(self, d):
        if self.paint_code is None:
            self.select(d)
            return
        cur = self.store.shifts.get(d.isoformat())
        self.store.set_shift(d, "" if cur == self.paint_code else self.paint_code)
        self.sel = d
        self.render()

    def _shift_menu(self, event, d, widget=None):
        m = tk.Menu(self.root, tearoff=0)
        for t in self.store.shift_types:
            m.add_command(label=f"{t['code']}  –  {t['name']} {muszak.label_time(t)}",
                          command=lambda c=t["code"]: (self.store.set_shift(d, c), setattr(self, "sel", d), self.render()))
        m.add_separator()
        m.add_command(label="Műszak törlése", command=lambda: (self.store.set_shift(d, ""), self.render()))
        m.add_command(label="Ismétlődő minta…", command=lambda: PatternDialog(self, start=d))
        m.add_command(label="Műszaktípusok…", command=lambda: ShiftTypesDialog(self))
        m.add_command(label="Szabadság…", command=lambda: LeaveDialog(self, d.year))
        try:
            if event is not None:
                m.tk_popup(event.x_root, event.y_root)
            elif widget is not None:
                m.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height())
        finally:
            m.grab_release()

    def _upcoming_watched(self, frm, days=45):
        if not self.store.watched:
            return []
        out, d = [], frm
        for _ in range(days):
            for n, w in watched_on(self.store, d):
                out.append((d, n, w.get("label", "")))
            d += _dt.timedelta(days=1)
        return out

    # ---------- események ----------
    def new_event(self, day=None, kind="event"):
        EventDialog(self, None, day or self.sel, kind=kind)

    def edit_event(self, e, occ=None):
        if e.get("readonly"):
            ExtEventDialog(self, e)
            return
        EventDialog(self, e, occ or ev._d(e["date"]))

    def delete_event(self, e, occ):
        if e.get("readonly"):
            messagebox.showinfo(APP_NAME, f"Ez az esemény a(z) „{e.get('cal_name') or 'külső'}” naptárból jön.\n"
                                "Ott tudod módosítani vagy törölni; a következő frissítéskor itt is eltűnik.",
                                parent=self.root)
            return
        if e["repeat"]["freq"] == "none":
            if messagebox.askyesno(APP_NAME, f"Törlöd ezt az eseményt?\n\n{e['title']}", parent=self.root):
                self.store.delete(e["id"])
                self.render()
            return
        if e["kind"] == "birthday":
            if messagebox.askyesno(APP_NAME, f"Törlöd a születésnapot?\n\n{e['title']}", parent=self.root):
                self.store.delete(e["id"])
                self.render()
            return
        RecurringDeleteDialog(self, e, occ)

    def do_search(self):
        q = self.search_var.get().strip()
        if not q:
            return
        hits = self.store.search(q) + self.subs.search(q)
        names = nevnapok.find_name(q, self.sel.year)
        SearchResultDialog(self, q, hits, names)

    # ---------- emlékeztetők ----------
    def _reminder_tick(self):
        try:
            self.check_reminders()
        except Exception as ex:  # az ütemező soha ne álljon le
            self.status.config(text=f"Emlékeztető hiba: {ex}")
        self.root.after(20000, self._reminder_tick)

    def check_reminders(self, now=None):
        now = now or _dt.datetime.now()
        st = self.store.data["reminder_state"]
        try:
            since = _dt.datetime.fromisoformat(st.get("last_check") or "")
        except ValueError:
            since = now - _dt.timedelta(hours=1)
        since = max(since, now - _dt.timedelta(hours=12))   # gép kikapcsolva volt: max 12 órát pótol
        fired = st.setdefault("fired", {})
        due = []
        for key, e, d, when, m in ev.due_reminders(self.all_events(), since, now,
                                                   self.settings.get("allday_reminder_time", "08:00")):
            if key not in fired:
                fired[key] = now.isoformat(timespec="minutes")
                due.append(("event", e, d, when, m))
        # szundi
        for sn in list(st.setdefault("snooze", [])):
            try:
                t = _dt.datetime.fromisoformat(sn["until"])
            except (ValueError, KeyError):
                st["snooze"].remove(sn)
                continue
            if t <= now:
                st["snooze"].remove(sn)
                e = self.get_event(sn.get("id"))
                if e:
                    due.append(("event", e, ev._d(sn.get("day")) or now.date(), t, -1))
        # [v1.1.0] műszak előtti emlékeztető
        for key, t, d, when in muszak.due_shift_reminders(self.store.shifts, self.store.shift_types, since, now):
            if key not in fired:
                fired[key] = now.isoformat(timespec="minutes")
                due.append(("shift", t, d, when, None))
        # figyelt névnapok
        if self.settings.get("nameday_reminder", True) and self.store.watched:
            tt = ev._t(self.settings.get("nameday_reminder_time", "08:00")) or _dt.time(8, 0)
            for back in (1, 0):
                d = now.date() - _dt.timedelta(days=back)
                when = _dt.datetime.combine(d, tt)
                if not (since < when <= now):
                    continue
                for n, w in watched_on(self.store, d):
                    key = f"nevnap|{d.isoformat()}|{n}"
                    if key not in fired:
                        fired[key] = now.isoformat(timespec="minutes")
                        due.append(("nameday", w, d, when, n))
        # [v1.4.0] teendők: a határidő napján (az egész napos emlékeztető idején)
        tt = ev._t(self.settings.get("allday_reminder_time", "08:00")) or _dt.time(8, 0)
        for back in (1, 0):
            d = now.date() - _dt.timedelta(days=back)
            when = _dt.datetime.combine(d, tt)
            if not (since < when <= now):
                continue
            for td in self.store.todos_on(d):
                key = f"todo|{td['id']}|{d.isoformat()}"
                if not td["done"] and key not in fired:
                    fired[key] = now.isoformat(timespec="minutes")
                    due.append(("todo", td, d, when, None))
        limit = (now - _dt.timedelta(days=90)).isoformat()
        for k in [k for k, v in fired.items() if v < limit]:
            del fired[k]
        st["last_check"] = now.isoformat(timespec="seconds")
        self.store.save()
        if len(due) > 4:
            lines = []
            for kind, obj, d, when, extra in due:
                lines.append(f"• {hu_date(d, year=False)}: " +
                             (ev.display_title(obj, d) if kind == "event" else
                              f"Műszak: {obj['name']} {muszak.label_time(obj)}" if kind == "shift" else
                              f"Teendő: {obj['title']}" if kind == "todo" else f"Névnap: {extra}"))
            ReminderPopup(self, "Emlékeztetők", "\n".join(lines[:12]) + ("\n…" if len(lines) > 12 else ""), None)
        else:
            for kind, obj, d, when, extra in due:
                if kind == "event":
                    self._popup_event(obj, d, extra)
                elif kind == "todo":
                    ReminderPopup(self, "Teendő mára", f"☐ {obj['title']}\n{hu_date(d, weekday=True)}"
                                  + (f"\n{obj['notes'][:200]}" if obj.get("notes") else ""), None)
                elif kind == "shift":
                    ReminderPopup(self, "Műszak", f"{obj['name']}  {muszak.label_time(obj)}\n{hu_date(d, weekday=True)}"
                                  f"\n({obj['reminder']} perc múlva kezdődik)", None)
                else:
                    lab = obj.get("label")
                    ReminderPopup(self, "Ma névnap van" if d == now.date() else "Névnap volt",
                                  f"{extra}" + (f"  ({lab})" if lab else "") + f"\n{hu_date(d, weekday=True)}", None)
        return due

    def _popup_event(self, e, d, m):
        when = hu_date(d, weekday=True)
        if not e.get("all_day"):
            when += f"  {e['time']}" + (f"–{e['end_time']}" if e.get("end_time") else "")
        txt = ev.display_title(e, d) + "\n" + when
        if e.get("location"):
            txt += "\n📍 " + e["location"]
        if m is not None and m > 0:
            txt += f"\n({ev.reminder_label(m)})"
        ReminderPopup(self, "Emlékeztető", txt, (e, d))
        if self.icon is not None and self.root.state() == "withdrawn":
            try:
                self.icon.notify(txt[:200], APP_NAME)
            except Exception:
                pass

    def snooze(self, e, d, minutes=10):
        st = self.store.data["reminder_state"]
        st.setdefault("snooze", []).append({"id": e["id"], "day": d.isoformat(),
                                            "until": (_dt.datetime.now() + _dt.timedelta(minutes=minutes)).isoformat(timespec="seconds")})
        self.store.save()

    def _midnight_check(self):
        if _dt.date.today() != self.today:
            old = self.today
            self.today = _dt.date.today()
            if self.sel == old:
                self.sel = self.today
            self.render()
        self.root.after(60000, self._midnight_check)

    # ---------- [v1.4.0] óra ----------
    def _tick_clock(self):
        now = _dt.datetime.now()
        try:
            self.clock_lbl.config(text=now.strftime("%H:%M:%S"))
            self.clock_sub.config(text=f"{hu_date(now.date())} {NAP[now.weekday()].lower()}")
        except tk.TclError:
            return
        self.root.after(max(50, 1000 - now.microsecond // 1000 + 5), self._tick_clock)

    # ---------- [v1.4.0] időjárás ----------
    def place(self):
        p = self.settings.get("weather_place") or {}
        if not p.get("lat") and p.get("lat") != 0:
            p = dict(idojaras.DEFAULT_PLACE)
        return p

    def weather_for(self, d):
        if not self.settings.get("weather_enabled", True) or not self.weather:
            return None
        return (self.weather.get("daily") or {}).get(d.isoformat())

    def _weather_tick(self):
        try:
            if self.settings.get("weather_enabled", True):
                p = self.place()
                w = self.weather
                stale = (not w or (idojaras.age_minutes(w) or 9999) >= idojaras.REFRESH_MIN
                         or w.get("place", {}).get("name") != p.get("name"))
                if stale and not self._weather_busy:
                    self.refresh_weather()
        finally:
            self.root.after(5 * 60 * 1000, self._weather_tick)

    def refresh_weather(self, done=None):
        if self._weather_busy:
            return
        self._weather_busy = True
        p = self.place()

        def finish(ok, res):
            self._weather_busy = False
            if ok:
                res["place"] = p
                self.weather = res
                try:
                    idojaras.save_cache(res)
                except OSError:
                    pass
                self.render()
            else:
                self.status.config(text=str(res))
            if done:
                done(ok, res)
        self.run_bg(lambda: idojaras.fetch(p["lat"], p["lon"]), finish)

    def run_bg(self, func, done):
        def work():
            try:
                res, ok = func(), True
            except Exception as ex:
                res, ok = ex, False
            self.call_ui(lambda: done(ok, res))
        threading.Thread(target=work, daemon=True).start()

    def _side_weather(self, s, d, pad):
        wd = self.weather_for(d)
        if not wd:
            if self.settings.get("weather_enabled", True) and d == self.today and not self.weather:
                label(s, "Időjárás betöltése…", soft=True, size=9).pack(anchor="w", pady=(8, 0), **pad)
            return
        w = self.weather
        card = tk.Frame(s, bg=COLORS['panel_head'])
        card.pack(fill=tk.X, pady=(10, 0), **pad)
        hf = tk.Frame(card, bg=COLORS['panel_head'])
        hf.pack(fill=tk.X, padx=8, pady=(6, 0))
        label(hf, f"Időjárás · {w.get('place', {}).get('name', '')}", bold=True, size=9,
              bg=COLORS['panel_head']).pack(side=tk.LEFT)
        lk = label(hf, "⚙", soft=True, size=9, bg=COLORS['panel_head'], cursor="hand2")
        lk.pack(side=tk.RIGHT)
        lk.bind("<Button-1>", lambda e: PlaceDialog(self))
        icon, txt = idojaras.describe(wd["code"])
        cur = w.get("current") or {}
        if d == self.today and cur.get("temp") is not None:
            ci, ct = idojaras.describe(cur.get("code"))
            label(card, f"{ci} {idojaras.fmt_t(cur['temp'])}  {ct}", bold=True, size=14,
                  bg=COLORS['panel_head']).pack(anchor="w", padx=8)
            extra = [f"érzésre {idojaras.fmt_t(cur.get('feels'))}"]
            if cur.get("wind") is not None:
                extra.append(f"szél {round(cur['wind'])} km/h")
            if cur.get("hum") is not None:
                extra.append(f"pára {round(cur['hum'])}%")
            label(card, " · ".join(extra), size=8, bg=COLORS['panel_head']).pack(anchor="w", padx=8)
            label(card, f"Napközben: {icon} {txt}, {idojaras.fmt_t(wd['tmax'])} / {idojaras.fmt_t(wd['tmin'])}",
                  size=9, bg=COLORS['panel_head'], wraplength=290, justify=tk.LEFT).pack(anchor="w", padx=8, pady=(2, 0))
        else:
            label(card, f"{icon} {idojaras.fmt_t(wd['tmax'])} / {idojaras.fmt_t(wd['tmin'])}  {txt}", bold=True,
                  size=12, bg=COLORS['panel_head'], wraplength=290, justify=tk.LEFT).pack(anchor="w", padx=8)
        rain = []
        if wd.get("pp") is not None:
            rain.append(f"csapadék esélye {round(wd['pp'])}%")
        if wd.get("psum"):
            rain.append(f"{wd['psum']:.1f} mm".replace(".", ","))
        if wd.get("wind") is not None:
            rain.append(f"szél max. {round(wd['wind'])} km/h")
        if rain:
            label(card, " · ".join(rain), size=8, bg=COLORS['panel_head'], wraplength=290,
                  justify=tk.LEFT).pack(anchor="w", padx=8)
        if wd.get("sunrise"):
            label(card, f"Napkelte {wd['sunrise']} · napnyugta {wd['sunset']}", soft=True, size=8,
                  bg=COLORS['panel_head']).pack(anchor="w", padx=8)
        if d == self.today:
            hs = idojaras.next_hours(w)
            if hs:
                label(card, "   ".join(f"{h}h {idojaras.describe(c)[0]}{idojaras.fmt_t(t)}" for h, t, c, pp in hs[:5]),
                      size=8, bg=COLORS['panel_head'], wraplength=300, justify=tk.LEFT).pack(anchor="w", padx=8, pady=(2, 0))
        age = idojaras.age_minutes(w)
        if age is not None:
            when = "most" if age < 2 else (f"{age} perce" if age < 90 else f"{age // 60} órája")
            label(card, f"frissítve {when} · open-meteo.com", soft=True, size=7,
                  bg=COLORS['panel_head']).pack(anchor="w", padx=8, pady=(2, 6))

    # ---------- [v1.4.0] szabadság ----------
    def leave_summary(self, year):
        return szabadsag.summary(self.store.data.get("leave"), self.store.shifts, self.store.shift_types, year,
                                 self.today)

    def _side_leave(self, s, d, pad):
        sm = self.leave_summary(d.year)
        if not sm["configured"] and not sm["taken"] and not sm["planned"]:
            return
        card = tk.Frame(s, bg=COLORS['panel_head'], cursor="hand2")
        card.pack(fill=tk.X, pady=(6, 0), **pad)
        l1 = label(card, f"Szabadság {d.year}: {sm['total']} nap", bold=True, size=9, bg=COLORS['panel_head'])
        l1.pack(anchor="w", padx=8, pady=(6, 0))
        col = COLORS['bad'] if sm["remaining"] < 0 else COLORS['ok']
        l2 = label(card, f"kivett {len(sm['taken'])} · tervezett {len(sm['planned'])} · marad {sm['remaining']}",
                   size=9, fg=col, bg=COLORS['panel_head'])
        l2.pack(anchor="w", padx=8, pady=(0, 2 if sm["warn"] else 6))
        ws = [card, l1, l2]
        if sm["warn"]:
            l3 = label(card, sm["warn"], size=8, fg=COLORS['warn'], bg=COLORS['panel_head'], wraplength=290,
                       justify=tk.LEFT)
            l3.pack(anchor="w", padx=8, pady=(0, 6))
            ws.append(l3)
        for w in ws:
            w.bind("<Button-1>", lambda e: LeaveDialog(self, d.year))

    # ---------- [v1.4.0] teendők ----------
    def _todo_row(self, parent, td, bg, show_due=True, wrap=230):
        row = tk.Frame(parent, bg=bg)
        row.pack(fill=tk.X, pady=2)
        cb = tk.Label(row, text="☑" if td["done"] else "☐", bg=bg, fg=COLORS['brand'] if td["done"] else COLORS['text'],
                      font=(FONT, 13), cursor="hand2")
        cb.pack(side=tk.LEFT, padx=(4, 4))
        cb.bind("<Button-1>", lambda e: (self.store.toggle_todo(td["id"]), self.render()))
        f = (FONT, 10, "overstrike") if td["done"] else (FONT, 10)
        txt = tk.Label(row, text=td["title"], bg=bg, fg=COLORS['text_soft'] if td["done"] else COLORS['text'],
                       font=f, anchor="w", justify=tk.LEFT, wraplength=wrap, cursor="hand2")
        txt.pack(side=tk.LEFT, fill=tk.X, expand=True)
        txt.bind("<Button-1>", lambda e: TodoDialog(self, td))
        if show_due and td.get("due"):
            dd = ev._d(td["due"])
            late = dd < self.today and not td["done"]
            rel = (dd - self.today).days
            dtxt = "ma" if rel == 0 else "holnap" if rel == 1 else hu_date(dd, year=dd.year != self.today.year)
            tk.Label(row, text=dtxt, bg=bg, fg=COLORS['bad'] if late else COLORS['text_soft'],
                     font=(FONT, 8, "bold" if late else "normal")).pack(side=tk.RIGHT, padx=4)
        return row

    def _side_todos(self, s, d, pad):
        items = self.store.todos_on(d, include_overdue=(d == self.today))
        tk.Frame(s, bg=COLORS['divider'], height=1).pack(fill=tk.X, pady=8, **pad)
        hf = tk.Frame(s, bg=COLORS['panel'])
        hf.pack(fill=tk.X, **pad)
        label(hf, "Teendők", bold=True, size=11).pack(side=tk.LEFT)
        btn(hf, "+ Teendő", lambda: TodoDialog(self, None, due=d), small=True).pack(side=tk.RIGHT)
        lf = tk.Frame(s, bg=COLORS['panel'])
        lf.pack(fill=tk.X, pady=(4, 0), **pad)
        if not items:
            label(lf, "Nincs teendő erre a napra.", soft=True, size=9).pack(anchor="w")
        for td in items:
            self._todo_row(lf, td, COLORS['panel'], show_due=td.get("due") != d.isoformat())

    def render_todo(self):
        m = self.main
        top = tk.Frame(m, bg=COLORS['panel'])
        top.pack(fill=tk.X, padx=14, pady=(12, 6))
        self.todo_title = tk.StringVar()
        self.todo_due = tk.StringVar()
        label(top, "Új teendő:", size=10).pack(side=tk.LEFT)
        te = entry(top, self.todo_title, width=36)
        te.pack(side=tk.LEFT, padx=6, ipady=3)
        label(top, "Határidő:", size=9, soft=True).pack(side=tk.LEFT, padx=(6, 0))
        entry(top, self.todo_due, width=11).pack(side=tk.LEFT, padx=4, ipady=3)
        btn(top, "Ma", lambda: self.todo_due.set(self.today.strftime("%Y.%m.%d.")), small=True).pack(side=tk.LEFT)
        btn(top, "Holnap", lambda: self.todo_due.set((self.today + _dt.timedelta(days=1)).strftime("%Y.%m.%d.")),
            small=True).pack(side=tk.LEFT, padx=2)
        btn(top, "+ Hozzáad", self._quick_todo, primary=True, small=True).pack(side=tk.LEFT, padx=(8, 0))
        te.bind("<Return>", lambda e: self._quick_todo())
        self.todo_err = label(m, "", size=9, fg=COLORS['bad'])
        self.todo_err.pack(anchor="w", padx=14)
        sf = ScrollFrame(m)
        sf.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        inner = sf.inner
        t0 = self.today
        groups = [("Lejárt", []), ("Ma", []), ("Holnap", []), ("A következő 7 napban", []), ("Később", []),
                  ("Határidő nélkül", []), ("Kész", [])]
        g = dict(groups)
        for td in sorted(self.store.todos, key=lambda t: (t.get("due") or "9999", t["title"].casefold())):
            if td["done"]:
                g["Kész"].append(td)
                continue
            dd = ev._d(td.get("due"))
            if not dd:
                g["Határidő nélkül"].append(td)
            elif dd < t0:
                g["Lejárt"].append(td)
            elif dd == t0:
                g["Ma"].append(td)
            elif dd == t0 + _dt.timedelta(days=1):
                g["Holnap"].append(td)
            elif dd <= t0 + _dt.timedelta(days=7):
                g["A következő 7 napban"].append(td)
            else:
                g["Később"].append(td)
        g["Kész"].sort(key=lambda t: t.get("done_at") or "", reverse=True)
        if not self.store.todos:
            label(inner, "Még nincs teendő. Írd be fent, és nyomj Entert.\n"
                         "Határidővel a naptárban is megjelenik, és aznap reggel szól.",
                  soft=True, size=10, justify=tk.LEFT).pack(anchor="w", padx=10, pady=16)
        for name, lst in groups:
            if not lst:
                continue
            hf = tk.Frame(inner, bg=COLORS['panel'])
            hf.pack(fill=tk.X, padx=6, pady=(12, 2))
            label(hf, f"{name}  ({len(lst)})", bold=True, size=11,
                  fg=COLORS['bad'] if name == "Lejárt" else COLORS['text']).pack(side=tk.LEFT)
            if name == "Kész":
                btn(hf, "Kész teendők törlése", self._purge_done, small=True).pack(side=tk.RIGHT)
            for td in lst[:30] if name == "Kész" else lst:
                r = self._todo_row(inner, td, COLORS['panel_head'], wrap=560)
                bx = btn(r, "✕", lambda tid=td["id"]: (self.store.delete_todo(tid), self.render()), small=True)
                bx.pack(side=tk.RIGHT, padx=4)
        te.focus_set()

    def _quick_todo(self):
        t = self.todo_title.get().strip()
        if not t:
            return
        due = ""
        if self.todo_due.get().strip():
            d = parse_date(self.todo_due.get())
            if not d:
                self.todo_err.config(text="A határidőt így add meg: 2026.11.25. (vagy hagyd üresen)")
                return
            due = d.isoformat()
        self.store.upsert_todo(t, due)
        self.render()

    def _purge_done(self):
        n = sum(1 for t in self.store.todos if t["done"])
        if n and messagebox.askyesno(APP_NAME, f"Törlöd a {n} kész teendőt?", parent=self.root):
            self.store.data["todos"] = [t for t in self.store.todos if not t["done"]]
            self.store.save()
            self.render()

    # ---------- [v1.4.0] önfrissítés ----------
    def _update_cycle(self):
        try:
            if self.settings.get("update_check", True):
                self.check_update()
        finally:
            self.root.after(updater.CHECK_MS, self._update_cycle)

    def check_update(self, manual=False, parent=None):
        def done(ok, res):
            info, text = res if ok else (None, f"Hiba: {res}")
            if info:
                self.update_info = info
                self.upd_lbl.config(text=f"Új verzió érhető el: v{info['ver']} (most: v{VERSION})")
                if not self._upd_shown:
                    self.upd_banner.pack(fill=tk.X, before=self._tb)
                    self._upd_shown = True
                if self.icon is not None and self.root.state() == "withdrawn":
                    try:
                        self.icon.notify(text, APP_NAME)
                    except Exception:
                        pass
            if manual:
                messagebox.showinfo(APP_NAME, text, parent=parent or self.root)
        self.run_bg(updater.check, done)

    def install_update(self):
        info = self.update_info
        if not info:
            return
        if not updater.can_self_update():
            if messagebox.askyesno(APP_NAME, "Forrásból futtatva nem tudok frissülni.\n"
                                   "Megnyissam a letöltési oldalt?", parent=self.root):
                webbrowser.open(info["url"])
            return
        if not messagebox.askyesno(APP_NAME, f"Letöltöm és telepítem a v{info['ver']} verziót.\n\n"
                                   "Az eseményeid, műszakjaid és beállításaid megmaradnak.\n"
                                   "A Naptár bezárul, és a telepítés után újraindul. Mehet?", parent=self.root):
            return
        self.upd_btn.config(state=tk.DISABLED)

        def prog(p):
            self.call_ui(lambda: self.upd_lbl.config(text=f"Letöltés… {p}%"))

        def done(ok, res):
            if not ok:
                self.upd_btn.config(state=tk.NORMAL)
                self.upd_lbl.config(text=f"Új verzió érhető el: v{info['ver']}")
                messagebox.showerror(APP_NAME, str(res), parent=self.root)
                return
            try:
                updater.launch_installer(res)
            except Exception as ex:
                self.upd_btn.config(state=tk.NORMAL)
                messagebox.showerror(APP_NAME, str(ex), parent=self.root)
                return
            self.quit_app()
        self.upd_lbl.config(text="Letöltés…")
        self.run_bg(lambda: updater.download_and_verify(info, prog), done)

    # ---------- [v1.3.0] külső naptárak, közzététel ----------
    def all_events(self):
        return self.store.events + self.subs.events()

    def get_event(self, eid):
        return self.store.get(eid) or self.subs.find(eid)

    def _sync_tick(self):
        try:
            for c in self.subs.due():
                self.sync_calendar(c)
        except Exception as ex:
            self.status.config(text=f"Naptár-frissítési hiba: {ex}")
        self.root.after(60000, self._sync_tick)

    def sync_calendar(self, c, done=None):
        """Letöltés háttérszálon; az eredményt a fő szál dolgozza fel."""
        if c["id"] in self._syncing:
            return
        self._syncing.add(c["id"])
        url = c["url"]

        def work():
            try:
                text, err = feliratkozas.fetch(url), None
            except Exception as ex:
                text, err = None, str(ex)

            def finish():
                self._syncing.discard(c["id"])
                if self.subs.get(c["id"]) is None:      # közben törölték
                    return
                if err:
                    self.subs.apply_error(c, err)
                    self.status.config(text=f"„{c['name']}” naptár: {err}")
                else:
                    self.subs.apply_text(c, text)
                    self.status.config(text=f"„{c['name']}” frissítve {_dt.datetime.now():%H:%M} · "
                                            f"{c['count']} alkalom")
                self.store.save()
                self.render()
                if done:
                    done()
            self.call_ui(finish)
        threading.Thread(target=work, daemon=True).start()

    def _schedule_publish(self):
        if self.settings.get("publish_dir") and not self._pub_pending:
            self._pub_pending = True
            try:
                self.root.after(1500, self._publish_now)
            except Exception:
                self._pub_pending = False

    def _publish_now(self):
        self._pub_pending = False
        if not self.settings.get("publish_dir"):
            return None
        try:
            path, self._pub_last = feliratkozas.publish(self.store, self.settings, self._pub_last)
        except OSError as ex:
            self.status.config(text=f"A naptár közzététele nem sikerült: {ex}")
            return None
        self._publish_mobile()
        return path

    # ---------- [v1.5.0] Arrabona Naptár Mobil ----------
    def _publish_mobile(self, force=False):
        folder = self.settings.get("publish_dir")
        if not folder or not self.settings.get("publish_mobile", True):
            return None
        try:
            data = mobil.build(self.store, self.subs.events(), self.settings, self.today)
            path, self._mob_last = mobil.write(folder, data, None if force else self._mob_last)
            return path
        except OSError as ex:
            self.status.config(text=f"A telefonos adatfájl kiírása nem sikerült: {ex}")
            return None

    # ---------- [v1.6.0] szerveres szinkron ----------
    def _server_tick(self):
        try:
            self.server_sync()
        except Exception as ex:
            self.srv_state = f"Hiba: {ex}"
        self.root.after(15000, self._server_tick)

    def server_sync(self, force=False, done=None):
        s = self.settings
        base, token = s.get("sync_url", ""), s.get("sync_token", "")
        if not base or not token or self._srv_busy:
            return False
        data = mobil.build(self.store, self.subs.events(), s, self.today)
        body = mobil.dumps_body(data)
        upload = force or self._srv_force or body != self._srv_last
        raw = mobil.full_bytes(data) if upload else None
        self._srv_busy = True
        self._srv_force = False

        def work():
            ops = szerver.get_ops(base, token)
            if raw is not None:
                szerver.put_snapshot(base, token, raw)
            return ops

        def finish(ok, res):
            self._srv_busy = False
            now = _dt.datetime.now().strftime("%H:%M:%S")
            if not ok:
                if isinstance(res, szerver.ServerError) and res.status == 401:
                    s["sync_token"] = ""
                    save_settings(s)
                    self.srv_state = "A bejelentkezés lejárt – jelentkezz be újra (Naptárak → Szerver-szinkron)."
                    self.status.config(text="Szerver: " + self.srv_state)
                else:
                    self.srv_state = f"{now} – {res}"
                if done:
                    done(False, res)
                return
            if raw is not None:
                self._srv_last = body
            ops = res
            msg = f"{now} – rendben" + (" (adatok feltöltve)" if raw is not None else "")
            if ops:
                st = mobil.apply_ops(self.store, ops, s)
                self._srv_force = True               # a visszaigazolás ("applied") menjen fel rögtön
                self.root.after(500, self.server_sync)
                self.render()
                parts = [f"{st[k]} {n}" for k, n in (("events", "esemény"), ("todos", "teendő"),
                                                     ("shifts", "műszak")) if st[k]]
                msg = f"{now} – telefonról átvéve: " + (", ".join(parts) or "nem volt új változás")
                if st["conflicts"]:
                    msg += f" ({st['conflicts']} kimaradt, mert a gépen frissebb volt)"
                self.status.config(text="Szerver: " + msg)
            self.srv_state = msg
            if done:
                done(True, ops)
        self.run_bg(work, finish)
        return True

    def _phone_poll(self):
        try:
            self.phone_merge()
        except Exception as ex:                  # a figyelő soha ne álljon le
            self.status.config(text=f"Telefonos változások: {ex}")
        self.root.after(10000, self._phone_poll)

    def phone_merge(self):
        s = self.settings
        folder = s.get("publish_dir")
        if not folder or not s.get("publish_mobile", True):
            return None
        path = os.path.join(folder, mobil.PHONE_NAME)
        try:
            stt = os.stat(path)
        except OSError:
            return None
        if time.time() - stt.st_mtime < 3:
            return None                          # a Dropbox még írhatja
        try:
            data = mobil.read_phone(path)
        except mobil.PhoneError as ex:
            sig = f"{stt.st_size}:{int(stt.st_mtime)}"
            if s.get("phone_bad_sig") != sig:
                s["phone_bad_sig"] = sig
                save_settings(s)
                self.status.config(text=str(ex))
            return None
        stats = mobil.apply_ops(self.store, data["ops"], s)
        try:
            os.remove(path)                      # átvéve
        except OSError:
            pass
        self._pub_last = None
        self._publish_now()
        self._publish_mobile(force=True)         # a telefon visszakapja az „átvettem” listát
        self.render()
        parts = []
        if stats["events"]:
            parts.append(f"{stats['events']} esemény")
        if stats["todos"]:
            parts.append(f"{stats['todos']} teendő")
        if stats["shifts"]:
            parts.append(f"{stats['shifts']} műszak")
        msg = "Telefonról átvéve: " + (", ".join(parts) if parts else "nem volt új változás")
        if stats["conflicts"]:
            msg += f" · {stats['conflicts']} változás kimaradt, mert közben a gépen módosult"
        self.status.config(text=msg)
        return stats

    def open_calendars(self):
        CalendarsDialog(self)

    # ---------- beállítások, névnapok ----------
    def open_settings(self):
        SettingsDialog(self)

    def open_name_search(self):
        NameDialog(self)

    # ---------- tálca, ablak ----------
    def build_tray(self):
        if pystray is None or Image is None:
            return
        try:
            src = Image.open(res_path("assets", "logo_naptar.png")).convert("RGBA")
            src = src.crop(src.getbbox())
            size = 16
            if sys.platform == "win32":
                import ctypes
                size = ctypes.windll.user32.GetSystemMetrics(49) or 16
            img = src
            while img.width > size * 2:
                img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
            img = img.resize((size, size), Image.LANCZOS).filter(
                ImageFilter.UnsharpMask(radius=0.8, percent=180, threshold=3))
            menu = pystray.Menu(
                pystray.MenuItem("Megnyitás", lambda i, it: self.call_ui(self.show_window), default=True),
                pystray.MenuItem("Új esemény", lambda i, it: self.call_ui(lambda: (self.show_window(), self.new_event()))),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Kilépés", lambda i, it: self.call_ui(self.quit_app)))
            self.icon = pystray.Icon("ArrabonaNaptar", img, f"{APP_NAME} v{VERSION}", menu)
            self.icon.run_detached()
        except Exception:
            self.icon = None

    def on_close(self):
        if self.settings.get("tray_on_close", True) and self.icon is not None:
            self.root.withdraw()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                try:
                    self.icon.notify("Az Arrabona Naptár a tálcán fut tovább, így az emlékeztetők is "
                                     "szólnak. Kilépés: jobb klikk az ikonra → Kilépés.", APP_NAME)
                except Exception:
                    pass
        else:
            self.quit_app()

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        try:
            self.root.attributes("-topmost", True)
            self.root.after(300, lambda: self.root.attributes("-topmost", False))
        except tk.TclError:
            pass
        self.root.focus_force()

    def quit_app(self):
        try:
            self.store.save()
        except OSError:
            pass
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
        self.root.destroy()


# ======================================================================
#  Párbeszédablakok
# ======================================================================

class Dialog(tk.Toplevel):
    def __init__(self, app, title):
        super().__init__(app.root)
        self.app = app
        self.title(title)
        self.configure(bg=COLORS['panel'])
        self.transient(app.root)
        self.resizable(False, False)
        self.body = tk.Frame(self, bg=COLORS['panel'], padx=22, pady=18)
        self.body.pack(fill=tk.BOTH, expand=True)
        self.bind("<Escape>", lambda e: self.destroy())
        if app._icon_img is not None:
            try:
                self.iconphoto(False, app._icon_img)
            except tk.TclError:
                pass

    def finish(self):
        self.update_idletasks()
        try:
            x = self.app.root.winfo_rootx() + (self.app.root.winfo_width() - self.winfo_width()) // 2
            y = self.app.root.winfo_rooty() + (self.app.root.winfo_height() - self.winfo_height()) // 3
            self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except (tk.TclError, TypeError):
            pass
        try:
            self.grab_set()
        except tk.TclError:
            pass


class EventDialog(Dialog):
    def __init__(self, app, e, day, kind="event"):
        self.orig = e
        self.occ = day
        kind = e["kind"] if e else kind
        self.kind = kind
        super().__init__(app, ("Születésnap" if kind == "birthday" else "Esemény") +
                         (" szerkesztése" if e else " – új"))
        e = e or ev.new_event(kind=kind, date=day.isoformat(), all_day=True,
                              reminders=list(app.settings.get("birthday_reminders" if kind == "birthday"
                                                              else "default_reminders", [])))
        self.e = e
        b = self.body
        row = 0

        def lab(t, r, c=0, **kw):
            label(b, t, soft=True, size=9).grid(row=r, column=c, sticky="w", pady=(8, 2), **kw)

        lab("Név" if kind == "birthday" else "Megnevezés *", row)
        self.title_var = tk.StringVar(value=e["title"])
        te = entry(b, self.title_var, width=44)
        te.grid(row=row + 1, column=0, columnspan=4, sticky="we", ipady=4)
        row += 2

        if kind == "birthday":
            first = ev._d(e["date"]) or day
            lab("Születésnap (hónap.nap)", row)
            self.bday_var = tk.StringVar(value=f"{first.month:02d}.{first.day:02d}.")
            entry(b, self.bday_var, width=12).grid(row=row + 1, column=0, sticky="w", ipady=3)
            lab("Születési év (nem kötelező)", row, 1, padx=(12, 0))
            self.byear_var = tk.StringVar(value=str(e["birth_year"]) if e["birth_year"] else "")
            entry(b, self.byear_var, width=8).grid(row=row + 1, column=1, sticky="w", ipady=3, padx=(12, 0))
            row += 2
            self.allday_var = tk.BooleanVar(value=True)
        else:
            self.allday_var = tk.BooleanVar(value=bool(e.get("all_day")))
            check(b, "Egész napos", self.allday_var, command=self._toggle_allday).grid(
                row=row, column=0, sticky="w", pady=(10, 0))
            row += 1
            lab("Kezdés napja", row)
            lab("Időpont", row, 1, padx=(12, 0))
            self.date_var = tk.StringVar(value=(ev._d(e["date"]) or day).strftime("%Y.%m.%d."))
            entry(b, self.date_var, width=14).grid(row=row + 1, column=0, sticky="w", ipady=3)
            self.time_var = tk.StringVar(value=e.get("time", ""))
            self.time_e = entry(b, self.time_var, width=7)
            self.time_e.grid(row=row + 1, column=1, sticky="w", ipady=3, padx=(12, 0))
            row += 2
            lab("Vége napja (többnapos eseménynél)", row)
            lab("Befejezés", row, 1, padx=(12, 0))
            ed = ev._d(e.get("end_date"))
            self.end_date_var = tk.StringVar(value=ed.strftime("%Y.%m.%d.") if ed else "")
            entry(b, self.end_date_var, width=14).grid(row=row + 1, column=0, sticky="w", ipady=3)
            self.end_time_var = tk.StringVar(value=e.get("end_time", ""))
            self.end_time_e = entry(b, self.end_time_var, width=7)
            self.end_time_e.grid(row=row + 1, column=1, sticky="w", ipady=3, padx=(12, 0))
            row += 2

            # ismétlődés
            lab("Ismétlődés", row)
            rf = tk.Frame(b, bg=COLORS['panel'])
            rf.grid(row=row + 1, column=0, columnspan=4, sticky="w")
            self.freq_var = tk.StringVar(value=ev.FREQ_NAMES[e["repeat"]["freq"]])
            cb = ttk.Combobox(rf, textvariable=self.freq_var, values=list(ev.FREQ_NAMES.values()),
                              state="readonly", width=16, font=(FONT, 10))
            cb.pack(side=tk.LEFT)
            cb.bind("<<ComboboxSelected>>", lambda ev_: self._toggle_repeat())
            label(rf, "  minden", size=9).pack(side=tk.LEFT)
            self.iv_var = tk.StringVar(value=str(e["repeat"]["interval"]))
            tk.Spinbox(rf, from_=1, to=99, textvariable=self.iv_var, width=3, font=(FONT, 10)).pack(side=tk.LEFT, padx=4)
            self.iv_lbl = label(rf, ".", size=9)
            self.iv_lbl.pack(side=tk.LEFT)
            label(rf, "   vége:", size=9).pack(side=tk.LEFT)
            until = ev._d(e["repeat"]["until"])
            self.until_var = tk.StringVar(value=until.strftime("%Y.%m.%d.") if until else "")
            entry(rf, self.until_var, width=12).pack(side=tk.LEFT, padx=4, ipady=2)
            label(rf, "(üres = soha)", soft=True, size=8).pack(side=tk.LEFT)
            self.wd_frame = tk.Frame(b, bg=COLORS['panel'])
            self.wd_frame.grid(row=row + 2, column=0, columnspan=4, sticky="w", pady=(4, 0))
            self.wd_vars = []
            first = ev._d(e["date"]) or day
            for i, n in enumerate(NAPR):
                v = tk.BooleanVar(value=i in (e["repeat"]["weekdays"] or [first.weekday()]))
                check(self.wd_frame, n, v).pack(side=tk.LEFT)
                self.wd_vars.append(v)
            row += 3

            lab("Helyszín", row)
            self.loc_var = tk.StringVar(value=e.get("location", ""))
            entry(b, self.loc_var, width=44).grid(row=row + 1, column=0, columnspan=4, sticky="we", ipady=3)
            row += 2

        # emlékeztetők
        lab("Emlékeztető", row)
        rem = tk.Frame(b, bg=COLORS['panel'])
        rem.grid(row=row + 1, column=0, columnspan=4, sticky="w")
        self.rem_frame = rem
        self.rem_vars = {}
        self._build_reminders()
        row += 2

        # szín
        lab("Szín", row)
        cf = tk.Frame(b, bg=COLORS['panel'])
        cf.grid(row=row + 1, column=0, columnspan=4, sticky="w")
        self.color = e.get("color") or ev.COLORS[0]
        self.swatches = []
        for c in ev.COLORS:
            sw = tk.Label(cf, text="  ", bg=c, width=3, cursor="hand2", relief=tk.FLAT,
                          highlightthickness=2, highlightbackground=COLORS['panel'])
            sw.pack(side=tk.LEFT, padx=2)
            sw.bind("<Button-1>", lambda ev_, cc=c: self._pick_color(cc))
            self.swatches.append((c, sw))
        self._pick_color(self.color)
        row += 2

        lab("Megjegyzés", row)
        self.notes = tk.Text(b, width=44, height=3, font=(FONT, 10), bg=COLORS['entry'], fg=COLORS['text'],
                             insertbackground=COLORS['text'], relief=tk.FLAT, highlightthickness=1,
                             highlightbackground=COLORS['divider'], wrap=tk.WORD)
        self.notes.grid(row=row + 1, column=0, columnspan=4, sticky="we")
        self.notes.insert("1.0", e.get("notes", ""))
        row += 2

        self.err = label(b, "", size=9, fg=COLORS['bad'])
        self.err.grid(row=row, column=0, columnspan=4, sticky="w", pady=(6, 0))
        bf = tk.Frame(b, bg=COLORS['panel'])
        bf.grid(row=row + 1, column=0, columnspan=4, sticky="we", pady=(8, 0))
        btn(bf, "Mégse", self.destroy).pack(side=tk.RIGHT)
        btn(bf, "Mentés", self.save, primary=True).pack(side=tk.RIGHT, padx=6)
        if self.orig:
            btn(bf, "Törlés", self._delete, danger=True).pack(side=tk.LEFT)
        self.bind("<Return>", lambda ev_: self.save() if self.focus_get() is not self.notes else None)
        if kind != "birthday":
            self._toggle_allday()
            self._toggle_repeat()
        self.finish()
        te.focus_set()

    def _build_reminders(self):
        for w in self.rem_frame.winfo_children():
            w.destroy()
        allday = self.allday_var.get()
        choices = ALLDAY_REMINDER_CHOICES if allday else REMINDER_CHOICES
        cur = set(self.e.get("reminders") or []) if not self.rem_vars else \
            {m for m, v in self.rem_vars.items() if v.get()}
        self.rem_vars = {}
        for i, (m, t) in enumerate(choices):
            v = tk.BooleanVar(value=m in cur)
            check(self.rem_frame, t, v).grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 10))
            self.rem_vars[m] = v
        if allday:
            label(self.rem_frame, f"(reggel {self.app.settings.get('allday_reminder_time', '08:00')}-kor szól)",
                  soft=True, size=8).grid(row=2, column=0, columnspan=3, sticky="w")

    def _toggle_allday(self):
        st = tk.DISABLED if self.allday_var.get() else tk.NORMAL
        for w in (self.time_e, self.end_time_e):
            w.config(state=st)
        self._build_reminders()

    def _toggle_repeat(self):
        f = self._freq()
        names = {"daily": "naponta", "weekly": "hetente", "monthly": "havonta", "yearly": "évente", "none": ""}
        self.iv_lbl.config(text=f" {names[f]}" if f != "none" else "")
        if f == "weekly":
            self.wd_frame.grid()
        else:
            self.wd_frame.grid_remove()

    def _freq(self):
        inv = {v: k for k, v in ev.FREQ_NAMES.items()}
        return inv.get(self.freq_var.get(), "none")

    def _pick_color(self, c):
        self.color = c
        for cc, sw in self.swatches:
            sw.config(highlightbackground=COLORS['text'] if cc == c else COLORS['panel'])

    def save(self):
        title = self.title_var.get().strip()
        if not title:
            self.err.config(text="Adj nevet az eseménynek.")
            return
        e = dict(self.e)
        e["title"] = title
        e["color"] = self.color
        e["notes"] = self.notes.get("1.0", tk.END).rstrip()
        e["reminders"] = [m for m, v in self.rem_vars.items() if v.get()]
        if self.kind == "birthday":
            by = self.byear_var.get().strip()
            if by and (not by.isdigit() or not 1900 <= int(by) <= _dt.date.today().year):
                self.err.config(text="A születési év 1900 és idén közötti szám legyen (vagy üres).")
                return
            year = int(by) if by else 2000          # szökőnap miatt szökőév az alap
            d = parse_date(self.bday_var.get(), default_year=year)
            if d is None:
                self.err.config(text="A dátumot hónap.nap alakban add meg (pl. 03.15.).")
                return
            e["date"] = d.isoformat()
            e["birth_year"] = int(by) if by else 0
            e["all_day"] = True
        else:
            d = parse_date(self.date_var.get())
            if d is None:
                self.err.config(text="Hibás kezdőnap (pl. 2026.11.18.).")
                return
            e["date"] = d.isoformat()
            e["all_day"] = self.allday_var.get()
            if e["all_day"]:
                e["time"] = e["end_time"] = ""
            else:
                t = parse_time(self.time_var.get())
                if not t:
                    self.err.config(text="Add meg az időpontot (pl. 14:30), vagy jelöld egész naposnak.")
                    return
                et = parse_time(self.end_time_var.get())
                if et is None:
                    self.err.config(text="Hibás befejezési idő (pl. 15:30).")
                    return
                e["time"], e["end_time"] = t, et
            ed_txt = self.end_date_var.get().strip()
            if ed_txt:
                ed = parse_date(ed_txt, default_year=d.year)
                if ed is None or ed < d:
                    self.err.config(text="A vége napja nem lehet a kezdés előtt.")
                    return
                e["end_date"] = ed.isoformat() if ed > d else ""
            else:
                e["end_date"] = ""
            f = self._freq()
            try:
                iv = max(1, int(self.iv_var.get()))
            except ValueError:
                iv = 1
            u_txt = self.until_var.get().strip()
            until = ""
            if u_txt and f != "none":
                u = parse_date(u_txt, default_year=d.year)
                if u is None or u < d:
                    self.err.config(text="Az ismétlődés vége nem lehet a kezdés előtt.")
                    return
                until = u.isoformat()
            wds = [i for i, v in enumerate(self.wd_vars) if v.get()] if f == "weekly" else []
            e["repeat"] = {"freq": f, "interval": iv, "weekdays": wds, "until": until, "count": 0}
            e["location"] = self.loc_var.get().strip()
        self.app.store.upsert(e)
        self.destroy()
        if self.kind != "birthday" and not self.orig:
            self.app.sel = ev._d(e["date"])
        self.app.render()
        self.app.status.config(text=f"Mentve: {title}")

    def _delete(self):
        e = self.orig
        self.destroy()
        self.app.delete_event(e, self.occ or ev._d(e["date"]))


class RecurringDeleteDialog(Dialog):
    def __init__(self, app, e, occ):
        super().__init__(app, "Ismétlődő esemény törlése")
        b = self.body
        label(b, e["title"], bold=True, size=12).pack(anchor="w")
        label(b, f"Ez egy ismétlődő esemény. Mit törölsz?\n(kiválasztott alkalom: {hu_date(occ, weekday=True)})",
              soft=True, justify=tk.LEFT).pack(anchor="w", pady=(4, 12))

        def do(kind):
            if kind == "one":
                app.store.skip_occurrence(e["id"], occ)
            elif kind == "after":
                if occ <= (ev._d(e["date"]) or occ):
                    app.store.delete(e["id"])
                else:
                    app.store.end_series_before(e["id"], occ)
            else:
                app.store.delete(e["id"])
            self.destroy()
            app.render()
        btn(b, "Csak ezt az alkalmat", lambda: do("one")).pack(fill=tk.X, pady=2)
        btn(b, "Ezt és az összes későbbit", lambda: do("after")).pack(fill=tk.X, pady=2)
        btn(b, "Az egész sorozatot", lambda: do("all"), danger=True).pack(fill=tk.X, pady=2)
        btn(b, "Mégse", self.destroy).pack(fill=tk.X, pady=(10, 0))
        self.finish()


class SearchResultDialog(Dialog):
    def __init__(self, app, q, hits, name_days):
        super().__init__(app, f"Keresés: {q}")
        b = self.body
        if name_days:
            label(b, f"„{q}” névnapja: " + ", ".join(hu_date(d, year=False) for d in name_days),
                  bold=True, fg=COLORS['warn']).pack(anchor="w", pady=(0, 8))
        label(b, f"{len(hits)} esemény", soft=True).pack(anchor="w")
        tr = ttk.Treeview(b, columns=("date", "title"), show="headings", height=min(12, max(3, len(hits))))
        tr.heading("date", text="Első alkalom / ismétlődés", anchor="w")
        tr.heading("title", text="Esemény", anchor="w")
        tr.column("date", width=220)
        tr.column("title", width=320)
        tr.pack(fill=tk.BOTH, expand=True, pady=6)
        for e in hits:
            d = ev._d(e["date"])
            rep = "" if e["repeat"]["freq"] == "none" else " · " + ev.FREQ_NAMES[e["repeat"]["freq"]].lower()
            tr.insert("", tk.END, iid=e["id"], values=(hu_date(d) + rep, e["title"]))

        def open_(ev_=None):
            s = tr.selection()
            if s:
                e = app.get_event(s[0])
                self.destroy()
                app.sel = ev._d(e["date"])
                app.render()
                app.edit_event(e)
        tr.bind("<Double-1>", open_)
        btn(b, "Bezár", self.destroy).pack(anchor="e")
        self.finish()


class NameDialog(Dialog):
    """Névnap-kereső + figyelt nevek (pl. családtagok) kezelése."""

    def __init__(self, app):
        super().__init__(app, "Névnapok")
        b = self.body
        label(b, "Kinek mikor van névnapja?", bold=True, size=11).grid(row=0, column=0, columnspan=3, sticky="w")
        self.q = tk.StringVar()
        qe = entry(b, self.q, width=24)
        qe.grid(row=1, column=0, sticky="w", ipady=4, pady=(6, 0))
        btn(b, "Keresés", self.find).grid(row=1, column=1, padx=6, pady=(6, 0))
        self.res = label(b, "", size=10, wraplength=420, justify=tk.LEFT)
        self.res.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        qe.bind("<Return>", lambda e: self.find())
        qe.bind("<KeyRelease>", lambda e: self.find(live=True))

        tk.Frame(b, bg=COLORS['divider'], height=1).grid(row=3, column=0, columnspan=3, sticky="we", pady=12)
        label(b, "Figyelt névnapok (szól, és ★-gal jelöli a naptárban)", bold=True, size=11).grid(
            row=4, column=0, columnspan=3, sticky="w")
        self.tr = ttk.Treeview(b, columns=("name", "label", "when"), show="headings", height=8)
        for c, t, w in (("name", "Név", 120), ("label", "Kinek (megjegyzés)", 170), ("when", "Névnap", 150)):
            self.tr.heading(c, text=t, anchor="w")
            self.tr.column(c, width=w)
        self.tr.grid(row=5, column=0, columnspan=3, sticky="we", pady=(6, 0))
        af = tk.Frame(b, bg=COLORS['panel'])
        af.grid(row=6, column=0, columnspan=3, sticky="we", pady=(8, 0))
        label(af, "Név:", size=9).pack(side=tk.LEFT)
        self.nn = tk.StringVar()
        cb = ttk.Combobox(af, textvariable=self.nn, values=nevnapok.all_names(), width=14, font=(FONT, 10))
        cb.pack(side=tk.LEFT, padx=4)
        label(af, "Nap:", size=9).pack(side=tk.LEFT, padx=(8, 0))
        self._nd_map = {}
        self.nd = tk.StringVar(value="mind")                     # [v1.2.0] több névnap közül egy
        self.nd_cb = ttk.Combobox(af, textvariable=self.nd, values=["mind"], width=9, state="readonly",
                                  font=(FONT, 10))
        self.nd_cb.pack(side=tk.LEFT, padx=4)
        self.nn.trace_add("write", lambda *a: self._days_for_name())
        label(af, "Kinek:", size=9).pack(side=tk.LEFT, padx=(8, 0))
        self.nl = tk.StringVar()
        entry(af, self.nl, width=14).pack(side=tk.LEFT, padx=4, ipady=2)
        btn(af, "Hozzáadás", self.add, primary=True, small=True).pack(side=tk.LEFT, padx=4)
        btn(af, "Törlés", self.remove, small=True).pack(side=tk.LEFT)
        self.err = label(b, "", size=9, fg=COLORS['bad'])
        self.err.grid(row=7, column=0, columnspan=3, sticky="w")
        btn(b, "Bezár", self.destroy).grid(row=8, column=2, sticky="e", pady=(8, 0))
        self.fill()
        self.finish()
        qe.focus_set()

    def find(self, live=False):
        q = self.q.get().strip()
        if not q:
            self.res.config(text="")
            return
        days = nevnapok.find_name(q, self.app.sel.year)
        if days:
            full = nevnapok.resolve(q)
            who = full if nevnapok._fold(full) == nevnapok._fold(q) else f"{q} ({full})"
            self.res.config(text=f"{who}: " + ", ".join(hu_date(d, year=False) for d in days), fg=COLORS['text'])
            self.nn.set(full)
        elif not live:
            sim = [n for n in nevnapok.all_names() if nevnapok._fold(n).startswith(nevnapok._fold(q))][:8]
            self.res.config(text="Nincs ilyen név a naptárban." + (f" Hasonló: {', '.join(sim)}" if sim else ""),
                            fg=COLORS['text_soft'])

    def _days_for_name(self):
        n = nevnapok.resolve(self.nn.get().strip()) if self.nn.get().strip() else ""
        days = nevnapok.find_name(n, self.app.sel.year) if n else []
        self._nd_map = {hu_date(d, year=False): nevnapok._key(d) for d in days}
        self.nd_cb.config(values=["mind"] + list(self._nd_map))
        self.nd.set("mind")

    def fill(self):
        self.tr.delete(*self.tr.get_children())
        for i, w in enumerate(self.app.store.watched):
            days = nevnapok.find_name(w["name"], self.app.sel.year)
            if w.get("day"):
                days = [d for d in days if nevnapok._key(d) == w["day"]]
            self.tr.insert("", tk.END, iid=str(i), values=(w["name"], w.get("label", ""),
                                                          ", ".join(hu_date(d, year=False) for d in days) or "nincs a naptárban"))

    def add(self):
        n = nevnapok.resolve(self.nn.get().strip()) if self.nn.get().strip() else ""
        if not n:
            return
        if not nevnapok.find_name(n):
            self.err.config(text=f"„{n}” nincs a névnaptárban (pontos név kell, pl. Katalin).")
            return
        if any(w["name"].casefold() == n.casefold() and w.get("label", "") == self.nl.get().strip()
               for w in self.app.store.watched):
            return
        self.err.config(text="")
        ent = {"name": n, "label": self.nl.get().strip()}
        day = self._nd_map.get(self.nd.get())
        if day:
            ent["day"] = day
        self.app.store.watched.append(ent)
        self.app.store.save()
        self.nn.set("")
        self.nl.set("")
        self.fill()
        self.app.render()

    def remove(self):
        s = self.tr.selection()
        if not s:
            return
        del self.app.store.watched[int(s[0])]
        self.app.store.save()
        self.fill()
        self.app.render()


class SettingsDialog(Dialog):
    def __init__(self, app):
        super().__init__(app, "Beállítások")
        s = app.settings
        b = self.body
        nb = ttk.Notebook(b)
        nb.pack(fill=tk.BOTH, expand=True)

        def tab(t):
            f = tk.Frame(nb, bg=COLORS['panel'], padx=14, pady=12)
            nb.add(f, text=t)
            return f
        t1, t2, t3 = tab("Általános"), tab("Emlékeztetők"), tab("Munkarend")

        self.v = {k: tk.BooleanVar(value=bool(s.get(k))) for k in
                  ("show_namedays", "show_jeles", "tray_on_close", "start_with_windows", "start_hidden",
                   "sound", "nameday_reminder", "weather_enabled", "update_check")}
        for i, (k, t) in enumerate((("show_namedays", "Névnapok a havi nézetben"),
                                    ("show_jeles", "Jeles napok (anyák napja, advent, óraátállítás…) a havi nézetben"),
                                    ("tray_on_close", "Bezáráskor (X) a tálcára kerül – így az emlékeztetők is szólnak"),
                                    ("start_with_windows", "Indítás a Windows-szal"),
                                    ("start_hidden", "    …rögtön a tálcára (ablak nélkül)"))):
            check(t1, t, self.v[k]).grid(row=i, column=0, sticky="w", pady=1)
        self.dark = tk.StringVar(value={None: "A Guard témáját követi", True: "Sötét", False: "Világos"}[s.get("dark")])
        df = tk.Frame(t1, bg=COLORS['panel'])
        df.grid(row=6, column=0, sticky="w", pady=(10, 0))
        label(df, "Téma:").pack(side=tk.LEFT)
        ttk.Combobox(df, textvariable=self.dark, state="readonly", width=24,
                     values=["A Guard témáját követi", "Sötét", "Világos"]).pack(side=tk.LEFT, padx=6)
        label(df, "(újraindítás után)", soft=True, size=9).pack(side=tk.LEFT)
        # [v1.4.0] időjárás, frissítés
        wf = tk.Frame(t1, bg=COLORS['panel'])
        wf.grid(row=7, column=0, sticky="w", pady=(10, 0))
        check(wf, "Időjárás megjelenítése (open-meteo.com) – település:", self.v["weather_enabled"]).pack(side=tk.LEFT)
        self.place_lbl = label(wf, app.place().get("name", ""), bold=True)
        self.place_lbl.pack(side=tk.LEFT, padx=4)
        btn(wf, "Módosítás…", lambda: PlaceDialog(app), small=True).pack(side=tk.LEFT, padx=4)
        uf = tk.Frame(t1, bg=COLORS['panel'])
        uf.grid(row=8, column=0, sticky="w", pady=(4, 0))
        check(uf, "Frissítések keresése a GitHubon (6 óránként)", self.v["update_check"]).pack(side=tk.LEFT)
        btn(uf, "Keresés most", lambda: app.check_update(manual=True, parent=self), small=True).pack(side=tk.LEFT, padx=8)
        label(t1, f"Adatok: {app.store.path}", soft=True, size=8).grid(row=9, column=0, sticky="w", pady=(12, 0))

        label(t2, "Egész napos események és születésnapok emlékeztetője:").grid(row=0, column=0, sticky="w")
        self.allday_t = tk.StringVar(value=s.get("allday_reminder_time", "08:00"))
        entry(t2, self.allday_t, width=6).grid(row=0, column=1, sticky="w", padx=6, ipady=2)
        check(t2, "Figyelt névnapokon szóljon, ekkor:", self.v["nameday_reminder"]).grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.nd_t = tk.StringVar(value=s.get("nameday_reminder_time", "08:00"))
        entry(t2, self.nd_t, width=6).grid(row=1, column=1, sticky="w", padx=6, ipady=2, pady=(6, 0))
        check(t2, "Hangjelzés az emlékeztetőnél", self.v["sound"]).grid(row=2, column=0, sticky="w", pady=(6, 0))
        label(t2, "Ha a gép ki volt kapcsolva, indításkor az elmúlt 12 óra elmaradt emlékeztetőit is megmutatja.",
              soft=True, size=9, wraplength=460, justify=tk.LEFT).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))

        label(t3, "Áthelyezett munkanapok: 2024–2026 beépítve (a 2026-os december 24-i változással együtt).\n"
                  "Ha megjelenik a következő évi rendelet, itt felveheted (szombati munkanap → helyette pihenőnap).",
              soft=True, size=9, wraplength=480, justify=tk.LEFT).grid(row=0, column=0, columnspan=4, sticky="w")
        self.sw = ttk.Treeview(t3, columns=("work", "rest"), show="headings", height=6)
        self.sw.heading("work", text="Szombati munkanap", anchor="w")
        self.sw.heading("rest", text="Helyette pihenőnap", anchor="w")
        self.sw.grid(row=1, column=0, columnspan=4, sticky="we", pady=8)
        self.w_var, self.r_var = tk.StringVar(), tk.StringVar()
        label(t3, "Munkanap:", size=9).grid(row=2, column=0, sticky="w")
        entry(t3, self.w_var, width=12).grid(row=2, column=1, sticky="w", ipady=2)
        label(t3, "Pihenőnap:", size=9).grid(row=2, column=2, sticky="w", padx=(10, 0))
        entry(t3, self.r_var, width=12).grid(row=2, column=3, sticky="w", ipady=2)
        sf = tk.Frame(t3, bg=COLORS['panel'])
        sf.grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 0))
        btn(sf, "Hozzáadás", self.add_swap, small=True, primary=True).pack(side=tk.LEFT)
        btn(sf, "Törlés", self.del_swap, small=True).pack(side=tk.LEFT, padx=6)
        self.sw_err = label(t3, "", size=9, fg=COLORS['bad'])
        self.sw_err.grid(row=4, column=0, columnspan=4, sticky="w")
        self.fill_swaps()

        bf = tk.Frame(b, bg=COLORS['panel'])
        bf.pack(fill=tk.X, pady=(12, 0))
        btn(bf, "Mégse", self.destroy).pack(side=tk.RIGHT)
        btn(bf, "Mentés", self.save, primary=True).pack(side=tk.RIGHT, padx=6)
        self.finish()

    def fill_swaps(self):
        self.sw.delete(*self.sw.get_children())
        for i, x in enumerate(self.app.store.data.get("extra_swaps", [])):
            self.sw.insert("", tk.END, iid=str(i), values=(x.get("work"), x.get("rest")))

    def add_swap(self):
        w, r = parse_date(self.w_var.get()), parse_date(self.r_var.get())
        if not w or not r:
            self.sw_err.config(text="Mindkét dátumot add meg (pl. 2027.01.09.).")
            return
        if w.weekday() != 5:
            self.sw_err.config(text="Az áthelyezett munkanap általában szombat – ellenőrizd a dátumot.")
        else:
            self.sw_err.config(text="")
        self.app.store.data.setdefault("extra_swaps", []).append({"work": w.isoformat(), "rest": r.isoformat()})
        self.app.store.save()
        unnepek._cache.clear()
        self.w_var.set("")
        self.r_var.set("")
        self.fill_swaps()
        self.app.render()

    def del_swap(self):
        s = self.sw.selection()
        if s:
            del self.app.store.data["extra_swaps"][int(s[0])]
            self.app.store.save()
            unnepek._cache.clear()
            self.fill_swaps()
            self.app.render()

    def save(self):
        s = self.app.settings
        for var, key in ((self.allday_t, "allday_reminder_time"), (self.nd_t, "nameday_reminder_time")):
            t = parse_time(var.get())
            if not t:
                messagebox.showerror(APP_NAME, "Az időpontot ÓÓ:PP alakban add meg (pl. 08:00).", parent=self)
                return
            s[key] = t
        for k, v in self.v.items():
            s[k] = bool(v.get())
        s["dark"] = {"A Guard témáját követi": None, "Sötét": True, "Világos": False}[self.dark.get()]
        save_settings(s)
        set_autostart(s["start_with_windows"], hidden=s["start_hidden"])
        self.destroy()
        if s.get("weather_enabled") and not self.app.weather:
            self.app.refresh_weather()
        self.app.render()


class ReminderPopup(tk.Toplevel):
    """Jobb alsó sarokban felugró, mindig felül lévő emlékeztető."""

    def __init__(self, app, head, text, target):
        super().__init__(app.root)
        self.app = app
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.configure(bg=COLORS['brand'])
        f = tk.Frame(self, bg=COLORS['panel'], padx=16, pady=12)
        f.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        hf = tk.Frame(f, bg=COLORS['panel'])
        hf.pack(fill=tk.X)
        label(hf, "🔔 " + head, bold=True, size=11, fg=COLORS['brand']).pack(side=tk.LEFT)
        label(hf, APP_NAME, soft=True, size=8).pack(side=tk.RIGHT)
        label(f, text, size=11, wraplength=330, justify=tk.LEFT).pack(anchor="w", pady=(6, 10))
        bf = tk.Frame(f, bg=COLORS['panel'])
        bf.pack(fill=tk.X)
        btn(bf, "Rendben", self.close, primary=True, small=True).pack(side=tk.RIGHT)
        if target is not None:
            e, d = target
            btn(bf, "Szundi 10 perc", lambda: (app.snooze(e, d, 10), self.close()), small=True).pack(side=tk.RIGHT, padx=6)
            btn(bf, "Megnyitás", lambda: (self.close(), app.show_window(), app.select(d), app.edit_event(e, d)),
                small=True).pack(side=tk.LEFT)
        self.update_idletasks()
        app._popups = [p for p in app._popups if p.winfo_exists()]
        off = sum(p.winfo_height() + 10 for p in app._popups)
        w, h = max(self.winfo_reqwidth(), 360), self.winfo_reqheight()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{sw - w - 20}+{max(0, sh - h - 70 - off)}")
        app._popups.append(self)
        if app.settings.get("sound", True):
            try:
                if sys.platform == "win32":
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                else:
                    self.bell()
            except Exception:
                pass

    def close(self):
        try:
            self.destroy()
        except tk.TclError:
            pass


# ======================================================================
#  [v1.1.0] Műszakok
# ======================================================================

class ShiftTypesDialog(Dialog):
    """Műszaktípusok: kód, név, kezdés-befejezés, fizetett órák, fajta, szín, emlékeztető."""

    def __init__(self, app):
        super().__init__(app, "Műszaktípusok")
        b = self.body
        self.types = [dict(t) for t in app.store.shift_types]
        self.tr = ttk.Treeview(b, columns=("code", "name", "time", "hours", "kind", "rem"), show="headings", height=9)
        for c, t, w in (("code", "Kód", 50), ("name", "Megnevezés", 150), ("time", "Idő", 100),
                        ("hours", "Óra", 50), ("kind", "Fajta", 120), ("rem", "Emlékeztető", 90)):
            self.tr.heading(c, text=t, anchor="w")
            self.tr.column(c, width=w)
        self.tr.grid(row=0, column=0, columnspan=8, sticky="we")
        self.tr.bind("<<TreeviewSelect>>", lambda e: self._load())
        f = tk.Frame(b, bg=COLORS['panel'])
        f.grid(row=1, column=0, columnspan=8, sticky="we", pady=(10, 0))
        self.v = {k: tk.StringVar() for k in ("code", "name", "start", "end", "hours", "reminder")}
        for i, (k, t, w) in enumerate((("code", "Kód", 5), ("name", "Megnevezés", 16), ("start", "Kezdés", 6),
                                       ("end", "Vége", 6), ("hours", "Óra (0=auto)", 5), ("reminder", "Emlékeztető (perc)", 5))):
            label(f, t, soft=True, size=8).grid(row=0, column=i, sticky="w", padx=(0, 6))
            entry(f, self.v[k], width=w).grid(row=1, column=i, sticky="w", padx=(0, 6), ipady=2)
        self.kind = tk.StringVar(value=muszak.KINDS["work"])
        self.cl = tk.BooleanVar(value=False)                       # [v1.4.0]
        check(f, "Szabadságkeretből fogy", self.cl).grid(row=3, column=6, columnspan=2, sticky="w", padx=(8, 0))
        label(f, "Fajta", soft=True, size=8).grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Combobox(f, textvariable=self.kind, values=list(muszak.KINDS.values()), state="readonly",
                     width=18).grid(row=3, column=0, columnspan=2, sticky="w")
        label(f, "Szín", soft=True, size=8).grid(row=2, column=2, sticky="w", pady=(6, 0))
        cf = tk.Frame(f, bg=COLORS['panel'])
        cf.grid(row=3, column=2, columnspan=4, sticky="w")
        self.color = ev.COLORS[0]
        self.sw = []
        for c in list(ev.COLORS) + ["#2c3e50", "#d35400"]:
            s = tk.Label(cf, text="  ", bg=c, width=2, cursor="hand2", highlightthickness=2,
                         highlightbackground=COLORS['panel'])
            s.pack(side=tk.LEFT, padx=1)
            s.bind("<Button-1>", lambda e, cc=c: self._color(cc))
            self.sw.append((c, s))
        bf = tk.Frame(b, bg=COLORS['panel'])
        bf.grid(row=2, column=0, columnspan=8, sticky="we", pady=(10, 0))
        btn(bf, "Új / mentés a kód alapján", self._save_row, primary=True, small=True).pack(side=tk.LEFT)
        btn(bf, "Törlés", self._del_row, small=True).pack(side=tk.LEFT, padx=6)
        btn(bf, "Alapértékek", self._defaults, small=True).pack(side=tk.LEFT)
        self.err = label(b, "", size=9, fg=COLORS['bad'])
        self.err.grid(row=3, column=0, columnspan=8, sticky="w", pady=(4, 0))
        label(b, "A „Fizetett távollét” (szabadság, betegszabadság) órái a havi keretbe beleszámítanak, de nem munkaórák.\n"
                 "Ha a vége korábbi, mint a kezdés (pl. 22:00–06:00), a műszak másnap ér véget.",
              soft=True, size=8, justify=tk.LEFT).grid(row=4, column=0, columnspan=8, sticky="w")
        ef = tk.Frame(b, bg=COLORS['panel'])
        ef.grid(row=5, column=0, columnspan=8, sticky="e", pady=(10, 0))
        btn(ef, "Mégse", self.destroy).pack(side=tk.RIGHT)
        btn(ef, "Mentés", self.save, primary=True).pack(side=tk.RIGHT, padx=6)
        self._fill()
        self.finish()

    def _color(self, c):
        self.color = c
        for cc, s in self.sw:
            s.config(highlightbackground=COLORS['text'] if cc == c else COLORS['panel'])

    def _fill(self):
        self.tr.delete(*self.tr.get_children())
        for i, t in enumerate(self.types):
            self.tr.insert("", tk.END, iid=str(i), values=(
                t["code"], t["name"], muszak.label_time(t) or "–", muszak.fmt_h(muszak.hours_of(t)).replace(" óra", ""),
                muszak.KINDS[t["kind"]], f"{t['reminder']} perc" if t.get("reminder") else "–"))

    def _load(self):
        s = self.tr.selection()
        if not s:
            return
        t = self.types[int(s[0])]
        for k in self.v:
            val = t.get(k, "")
            self.v[k].set("" if val in (0, 0.0) and k in ("hours", "reminder") else str(val))
        self.kind.set(muszak.KINDS[t["kind"]])
        self.cl.set(bool(t.get("counts_leave")))
        self._color(t["color"])

    def _save_row(self):
        code = self.v["code"].get().strip()
        if not code:
            self.err.config(text="Adj meg egy rövid kódot (pl. DE, N12).")
            return
        for k in ("start", "end"):
            if self.v[k].get().strip() and parse_time(self.v[k].get()) is None:
                self.err.config(text="Az időt ÓÓ:PP alakban add meg (pl. 06:00).")
                return
        inv = {v: k for k, v in muszak.KINDS.items()}
        t = muszak.normalize_type({"code": code, "name": self.v["name"].get() or code,
                                   "start": parse_time(self.v["start"].get()) or "", "end": parse_time(self.v["end"].get()) or "",
                                   "hours": self.v["hours"].get().replace(",", ".") or 0, "kind": inv[self.kind.get()],
                                   "color": self.color, "reminder": self.v["reminder"].get() or 0,
                                   "counts_leave": bool(self.cl.get())})
        if t["kind"] == "work" and not muszak.span(t) and not t["hours"]:
            self.err.config(text="Munkaműszaknál add meg a kezdést és a véget (vagy az órák számát).")
            return
        self.err.config(text="")
        for i, x in enumerate(self.types):
            if x["code"] == t["code"]:
                self.types[i] = t
                break
        else:
            self.types.append(t)
        self._fill()
        for v in self.v.values():          # a következő új típus üres űrlappal induljon
            v.set("")

    def _del_row(self):
        s = self.tr.selection()
        if not s:
            return
        code = self.types[int(s[0])]["code"]
        used = sum(1 for v in self.app.store.shifts.values() if v == code)
        if used and not messagebox.askyesno(APP_NAME, f"A(z) {code} műszak {used} napon be van jelölve.\n"
                                            "Törlöd a típust? (A bejelölések is törlődnek.)", parent=self):
            return
        del self.types[int(s[0])]
        self._fill()

    def _defaults(self):
        import copy
        have = {t["code"] for t in self.types}
        for t in copy.deepcopy(muszak.DEFAULT_TYPES):
            if t["code"] not in have:
                self.types.append(muszak.normalize_type(t))
        self._fill()

    def save(self):
        codes = {t["code"] for t in self.types}
        st = self.app.store
        st.data["shift_types"] = self.types
        st.data["shifts"] = {k: v for k, v in st.shifts.items() if v in codes}
        st.save()
        self.destroy()
        if self.app.paint_code not in codes and self.app.paint_code is not None:
            self.app.paint_code = self.types[0]["code"] if self.types else ""
        self.app._build_paint_bar()
        self.app.render()


class PatternDialog(Dialog):
    """Ismétlődő műszakminta (pl. 12 órás forgó: N12 É12 P P) kitöltése egy időszakra."""

    PRESETS = [("12 órás forgó (nappal, éjszaka, 2 szabad)", "N12 É12 - -"),
               ("12 órás: 2 nappal, 2 éjszaka, 4 szabad", "N12 N12 É12 É12 - - - -"),
               ("3 műszak hetente váltva (H–P)", "DE DE DE DE DE - - DU DU DU DU DU - - ÉJ ÉJ ÉJ ÉJ ÉJ - -"),
               ("2 műszak hetente váltva (H–P)", "DE DE DE DE DE - - DU DU DU DU DU - -"),
               ("Hétköznap délelőtt", "DE DE DE DE DE - -")]

    def __init__(self, app, start=None):
        super().__init__(app, "Ismétlődő műszakminta")
        b = self.body
        start = start or app.sel
        label(b, "Minta: a kódok szóközzel elválasztva, a „-” üres (szabad) nap.", size=9).grid(row=0, column=0, columnspan=4, sticky="w")
        self.pat = tk.StringVar(value="N12 É12 - -")
        pe = entry(b, self.pat, width=52)
        pe.grid(row=1, column=0, columnspan=4, sticky="we", ipady=4, pady=(4, 0))
        codes = " ".join(t["code"] for t in app.store.shift_types)
        label(b, f"Kódok: {codes}", soft=True, size=8).grid(row=2, column=0, columnspan=4, sticky="w")
        self.preset = tk.StringVar(value="Kész minták…")
        cb = ttk.Combobox(b, textvariable=self.preset, values=[p[0] for p in self.PRESETS], state="readonly", width=48)
        cb.grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: self.pat.set(dict(self.PRESETS)[self.preset.get()]))
        label(b, "Kezdőnap (a minta első napja)", soft=True, size=9).grid(row=4, column=0, sticky="w", pady=(10, 2))
        label(b, "Utolsó nap", soft=True, size=9).grid(row=4, column=1, sticky="w", pady=(10, 2), padx=(12, 0))
        self.start = tk.StringVar(value=start.strftime("%Y.%m.%d."))
        self.end = tk.StringVar(value=_dt.date(start.year, 12, 31).strftime("%Y.%m.%d."))
        entry(b, self.start, width=14).grid(row=5, column=0, sticky="w", ipady=3)
        entry(b, self.end, width=14).grid(row=5, column=1, sticky="w", ipady=3, padx=(12, 0))
        self.skip_hol = tk.BooleanVar(value=False)
        check(b, "Munkaszüneti napokat (ünnepeket) hagyja üresen", self.skip_hol).grid(row=6, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self.keep = tk.BooleanVar(value=True)
        check(b, "A már bejelölt szabadságot / betegszabadságot ne írja felül", self.keep).grid(row=7, column=0, columnspan=4, sticky="w")
        self.err = label(b, "", size=9, fg=COLORS['bad'], wraplength=440, justify=tk.LEFT)
        self.err.grid(row=8, column=0, columnspan=4, sticky="w", pady=(6, 0))
        bf = tk.Frame(b, bg=COLORS['panel'])
        bf.grid(row=9, column=0, columnspan=4, sticky="e", pady=(8, 0))
        btn(bf, "Mégse", self.destroy).pack(side=tk.RIGHT)
        btn(bf, "Kitöltés", self.apply, primary=True).pack(side=tk.RIGHT, padx=6)
        self.finish()
        pe.focus_set()

    def apply(self):
        codes = {t["code"].casefold(): t["code"] for t in self.app.store.shift_types}
        pat = []
        for p in self.pat.get().split():
            if p in ("-", "_", "x", "X"):
                pat.append("")
            elif p.casefold() in codes:
                pat.append(codes[p.casefold()])
            else:
                self.err.config(text=f"Ismeretlen kód: „{p}”. Elérhető: {' '.join(codes.values())} (és „-” a szabad nap).")
                return
        if not pat:
            self.err.config(text="Adj meg egy mintát.")
            return
        s, e = parse_date(self.start.get()), parse_date(self.end.get())
        if not s or not e or e < s:
            self.err.config(text="Hibás dátum (az utolsó nap nem lehet a kezdőnap előtt).")
            return
        if (e - s).days > 3 * 366:
            self.err.config(text="Legfeljebb 3 évet tölthetsz ki egyszerre.")
            return
        sh = self.app.store.shifts
        tb = muszak.types_by_code(self.app.store.shift_types)
        kept = {k: v for k, v in sh.items() if self.keep.get() and tb.get(v, {}).get("kind") == "leave"
                and s.isoformat() <= k <= e.isoformat()}
        n = muszak.apply_pattern(sh, s, e, pat, skip_holidays=self.skip_hol.get(), swaps=self.app.swaps())
        sh.update(kept)
        self.app.store.save()
        self.destroy()
        self.app.render()
        self.app.status.config(text=f"Műszakminta kitöltve: {n} nap ({hu_date(s)} – {hu_date(e)})")


# ======================================================================
#  [v1.3.0] Külső naptárak és közzététel
# ======================================================================
CAL_HELP = (
    "Hol találod a naptár .ics címét?\n"
    "• Google Naptár (gépen, böngészőben): Beállítások → a naptár neve → „Titkos cím iCal formátumban”.\n"
    "• iCloud (iPhone): Naptár app → Naptárak → ⓘ a naptár mellett → „Nyilvános naptár” be → Link megosztása.\n"
    "• Outlook.com: Beállítások → Naptár → Megosztott naptárak → Naptár közzététele → ICS-link.\n"
    "• Vagy egy .ics fájl a gépeden (Tallózás…), pl. egy Dropbox mappában.\n"
    "A külső naptárak csak olvashatók: itt látod őket, de a módosítás a saját helyükön történik.")

PUB_HELP = (
    "A program ebbe a mappába folyamatosan kiírja az ArrabonaNaptar.ics fájlt (minden változáskor).\n"
    "Telefonra: tedd a Dropbox mappádba, a Dropboxban kérj rá megosztási linket, és iPhone-on:\n"
    "Beállítások → Naptár → Fiókok → Fiók hozzáadása → Egyéb → Előfizetett naptár hozzáadása → link.\n"
    "Google Naptárban: Egyéb naptárak + → „URL-alapú” → ugyanez a link.\n"
    "Telefonos app: https://lokypapa.github.io/arrabona-naptar/ – ugyanebből a mappából olvassa az "
    "ArrabonaNaptar_mobil.json-t, és ide küldi vissza a változásokat.")


class CalendarsDialog(Dialog):
    def __init__(self, app):
        super().__init__(app, "Naptárak")
        b = self.body
        subs = app.subs
        self.subs = subs
        label(b, "Feliratkozott naptárak", bold=True, size=12).grid(row=0, column=0, columnspan=4, sticky="w")
        self.tr = ttk.Treeview(b, columns=("on", "name", "kind", "state"), show="headings", height=6)
        for c, t, w in (("on", "Be", 40), ("name", "Név", 170), ("kind", "Forrás", 80), ("state", "Állapot", 300)):
            self.tr.heading(c, text=t, anchor="w")
            self.tr.column(c, width=w)
        self.tr.grid(row=1, column=0, columnspan=4, sticky="we", pady=(6, 0))
        self.tr.bind("<<TreeviewSelect>>", lambda e: self._load())
        self.tr.bind("<Double-1>", lambda e: self.toggle())

        bf = tk.Frame(b, bg=COLORS['panel'])
        bf.grid(row=2, column=0, columnspan=4, sticky="we", pady=(6, 0))
        btn(bf, "Be / Ki", self.toggle, small=True).pack(side=tk.LEFT)
        btn(bf, "Frissítés most", self.refresh, small=True).pack(side=tk.LEFT, padx=6)
        btn(bf, "Másolás a saját naptárba", self.copy_own, small=True).pack(side=tk.LEFT)
        btn(bf, "Törlés", self.remove, danger=True, small=True).pack(side=tk.RIGHT)

        ff = tk.Frame(b, bg=COLORS['panel'])
        ff.grid(row=3, column=0, columnspan=4, sticky="we", pady=(12, 0))
        label(ff, "Név:", size=9).grid(row=0, column=0, sticky="w")
        self.name = tk.StringVar()
        entry(ff, self.name, width=22).grid(row=0, column=1, sticky="w", padx=4, ipady=2)
        label(ff, "Szín:", size=9).grid(row=0, column=2, sticky="e", padx=(10, 0))
        cf = tk.Frame(ff, bg=COLORS['panel'])
        cf.grid(row=0, column=3, sticky="w", padx=4)
        self.color = ev.COLORS[1]
        self.swatches = []
        for c in ev.COLORS:
            sw = tk.Label(cf, text=" ", bg=c, width=2, cursor="hand2", highlightthickness=2,
                          highlightbackground=COLORS['panel'])
            sw.pack(side=tk.LEFT, padx=1)
            sw.bind("<Button-1>", lambda ev_, cc=c: self._pick(cc))
            self.swatches.append((c, sw))
        self._pick(self.color)
        label(ff, "Cím vagy fájl:", size=9).grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.url = tk.StringVar()
        entry(ff, self.url, width=58).grid(row=1, column=1, columnspan=3, sticky="we", padx=4, pady=(6, 0), ipady=2)
        btn(ff, "Tallózás…", self.browse, small=True).grid(row=1, column=4, padx=4, pady=(6, 0))
        self.rem = tk.BooleanVar(value=False)
        check(ff, "Emlékeztető az eseményeihez (az alapbeállítás szerint)", self.rem).grid(
            row=2, column=1, columnspan=3, sticky="w", pady=(4, 0))
        af = tk.Frame(ff, bg=COLORS['panel'])
        af.grid(row=3, column=1, columnspan=4, sticky="w", pady=(6, 0))
        btn(af, "Új naptár hozzáadása", self.add, primary=True, small=True).pack(side=tk.LEFT)
        btn(af, "Módosítás mentése", self.save_sel, small=True).pack(side=tk.LEFT, padx=6)
        self.err = label(b, "", size=9, fg=COLORS['bad'], wraplength=640, justify=tk.LEFT)
        self.err.grid(row=4, column=0, columnspan=4, sticky="w")
        label(b, CAL_HELP, soft=True, size=9, justify=tk.LEFT, wraplength=640).grid(
            row=5, column=0, columnspan=4, sticky="w", pady=(6, 0))
        rf = tk.Frame(b, bg=COLORS['panel'])
        rf.grid(row=6, column=0, columnspan=4, sticky="w", pady=(6, 0))
        label(rf, "Frissítés:", size=9).pack(side=tk.LEFT)
        self.every = tk.StringVar(value=str(app.settings.get("calendar_refresh_min", 30)))
        ttk.Combobox(rf, textvariable=self.every, values=["15", "30", "60", "180"], width=5,
                     state="readonly").pack(side=tk.LEFT, padx=4)
        label(rf, "percenként", size=9).pack(side=tk.LEFT)

        tk.Frame(b, bg=COLORS['divider'], height=1).grid(row=7, column=0, columnspan=4, sticky="we", pady=12)
        label(b, "Saját naptár kifelé (.ics)", bold=True, size=12).grid(row=8, column=0, columnspan=4, sticky="w")
        pf = tk.Frame(b, bg=COLORS['panel'])
        pf.grid(row=9, column=0, columnspan=4, sticky="we", pady=(6, 0))
        label(pf, "Közzététel mappába:", size=9).pack(side=tk.LEFT)
        self.pub = tk.StringVar(value=app.settings.get("publish_dir", ""))
        entry(pf, self.pub, width=44).pack(side=tk.LEFT, padx=4, ipady=2)
        btn(pf, "Tallózás…", self.browse_dir, small=True).pack(side=tk.LEFT)
        btn(pf, "Ki", lambda: self.pub.set(""), small=True).pack(side=tk.LEFT, padx=4)
        of = tk.Frame(b, bg=COLORS['panel'])
        of.grid(row=10, column=0, columnspan=4, sticky="w", pady=(4, 0))
        self.p_sh = tk.BooleanVar(value=app.settings.get("publish_shifts", True))
        self.p_bd = tk.BooleanVar(value=app.settings.get("publish_birthdays", True))
        self.p_mob = tk.BooleanVar(value=app.settings.get("publish_mobile", True))
        check(of, "Műszakok is", self.p_sh).pack(side=tk.LEFT)
        check(of, "Születésnapok is", self.p_bd).pack(side=tk.LEFT, padx=10)
        check(of, "Telefonos app (Arrabona Naptár Mobil) adatai is", self.p_mob).pack(side=tk.LEFT)
        label(b, PUB_HELP, soft=True, size=9, justify=tk.LEFT, wraplength=640).grid(
            row=11, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self.pub_state = label(b, "", size=9, fg=COLORS['brand'], wraplength=640, justify=tk.LEFT)
        self.pub_state.grid(row=12, column=0, columnspan=4, sticky="w")
        xf = tk.Frame(b, bg=COLORS['panel'])
        xf.grid(row=13, column=0, columnspan=4, sticky="we", pady=(10, 0))
        btn(xf, "Exportálás fájlba…", self.export_file, small=True).pack(side=tk.LEFT)
        btn(xf, "Szerver-szinkron…", lambda: ServerDialog(app), small=True).pack(side=tk.LEFT, padx=(0, 6))
        btn(xf, "Importálás .ics-ből…", self.import_file, small=True).pack(side=tk.LEFT, padx=6)
        btn(xf, "Mentés és bezárás", self.save_close, primary=True).pack(side=tk.RIGHT)
        self.fill()
        self.finish()

    # --- lista
    def _pick(self, c):
        self.color = c
        for cc, sw in self.swatches:
            sw.config(highlightbackground=COLORS['text'] if cc == c else COLORS['panel'])

    def _state(self, c):
        if self.app._syncing and c["id"] in self.app._syncing:
            return "frissítés folyamatban…"
        if c.get("error"):
            return "⚠ " + c["error"]
        if not c.get("last_sync"):
            return "még nem frissült"
        t = c["last_sync"].replace("T", " ")
        return f"{t} · {c.get('count', 0)} alkalom" + (" · 🔔" if c.get("reminders") else "")

    def fill(self):
        self.tr.delete(*self.tr.get_children())
        for c in self.subs.calendars:
            self.tr.insert("", tk.END, iid=c["id"], values=("✓" if c.get("enabled", True) else "–", c["name"],
                                                           feliratkozas.kind_label(c["url"]), self._state(c)))

    def _sel(self):
        s = self.tr.selection()
        return self.subs.get(s[0]) if s else None

    def _load(self):
        c = self._sel()
        if c:
            self.name.set(c["name"])
            self.url.set(c["url"])
            self.rem.set(bool(c.get("reminders")))
            self._pick(c.get("color") or ev.COLORS[1])

    def _after_change(self):
        self.app.store.save()
        self.fill()
        self.app.render()

    def browse(self):
        p = filedialog.askopenfilename(parent=self, title="Naptárfájl kiválasztása",
                                       filetypes=[("iCalendar", "*.ics"), ("Minden fájl", "*.*")])
        if p:
            self.url.set(p)
            if not self.name.get().strip():
                self.name.set(os.path.splitext(os.path.basename(p))[0])

    def _check_url(self):
        u = self.url.get().strip()
        if not u:
            self.err.config(text="Add meg a naptár címét (https:// vagy webcal://) vagy egy .ics fájlt.")
            return None
        if not (feliratkozas.is_local(u) or u.lower().startswith(("http://", "https://", "webcal://", "webcals://"))):
            self.err.config(text="A cím https:// vagy webcal:// kezdetű legyen, vagy egy .ics fájl útvonala.")
            return None
        self.err.config(text="")
        return u

    def add(self):
        u = self._check_url()
        if not u:
            return
        if any(feliratkozas.normalize_url(c["url"]) == feliratkozas.normalize_url(u) for c in self.subs.calendars):
            self.err.config(text="Erre a naptárra már fel vagy iratkozva.")
            return
        c = self.subs.add(self.name.get(), u, self.color, self.rem.get())
        if self.name.get().strip():
            c["name_set"] = True
        self.fill()
        self.tr.selection_set(c["id"])
        self.refresh()

    def save_sel(self):
        c = self._sel()
        if not c:
            self.err.config(text="Előbb jelölj ki egy naptárat a listában.")
            return
        u = self._check_url()
        if not u:
            return
        changed_url = feliratkozas.normalize_url(u) != feliratkozas.normalize_url(c["url"])
        c.update(name=self.name.get().strip() or c["name"], url=u, color=self.color, reminders=self.rem.get(),
                 name_set=True)
        self.subs.load_cached(c)                 # szín / név / emlékeztető az új beállítással
        self._after_change()
        if changed_url:
            self.refresh()

    def toggle(self):
        c = self._sel()
        if c:
            c["enabled"] = not c.get("enabled", True)
            self._after_change()
            self.tr.selection_set(c["id"])
            if c["enabled"]:
                self.refresh()

    def refresh(self):
        cs = [self._sel()] if self._sel() else [c for c in self.subs.calendars if c.get("enabled", True)]
        for c in cs:
            if c:
                self.app.sync_calendar(c, done=self._refreshed)
        self.fill()

    def _refreshed(self):
        try:
            if self.winfo_exists():
                sel = self.tr.selection()
                self.fill()
                if sel and self.subs.get(sel[0]):
                    self.tr.selection_set(sel[0])
        except tk.TclError:
            pass

    def remove(self):
        c = self._sel()
        if c and messagebox.askyesno(APP_NAME, f"Leiratkozol erről a naptárról?\n\n{c['name']}\n\n"
                                     "(Az eredeti naptárban nem töröl semmit.)", parent=self):
            self.subs.remove(c["id"])
            self.fill()
            self.app.render()

    def copy_own(self):
        """A kijelölt külső naptár eseményeinek átmásolása saját (szerkeszthető) eseménnyé."""
        c = self._sel()
        if not c:
            self.err.config(text="Előbb jelölj ki egy naptárat a listában.")
            return
        try:
            with open(os.path.join(feliratkozas.cache_dir(), c["id"] + ".ics"), "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            self.err.config(text="Ez a naptár még nem frissült, előbb nyomd meg a „Frissítés most” gombot.")
            return
        if not messagebox.askyesno(APP_NAME, f"Átmásolod a(z) „{c['name']}” eseményeit a saját naptáradba?\n\n"
                                   "Utána szerkesztheted őket, de a külső naptárral már nem frissülnek. "
                                   "Érdemes utána kikapcsolni a feliratkozást, különben duplán látszanak.",
                                   parent=self):
            return
        self._import_text(text)

    # --- közzététel / export / import
    def browse_dir(self):
        p = filedialog.askdirectory(parent=self, title="Közzétételi mappa (pl. a Dropbox mappád)")
        if p:
            self.pub.set(os.path.normpath(p))

    def _apply_settings(self):
        s = self.app.settings
        try:
            s["calendar_refresh_min"] = int(self.every.get())
        except ValueError:
            pass
        s["publish_dir"] = self.pub.get().strip()
        s["publish_shifts"] = bool(self.p_sh.get())
        s["publish_birthdays"] = bool(self.p_bd.get())
        s["publish_mobile"] = bool(self.p_mob.get())
        save_settings(s)

    def save_close(self):
        self._apply_settings()
        if self.app.settings.get("publish_dir"):
            self.app._pub_last = None
            self.app._mob_last = None
            path = self.app._publish_now()
            if path:
                self.app.status.config(text=f"Saját naptár kiírva: {path}")
        self.app.store.save()
        self.destroy()

    def export_file(self):
        self._apply_settings()
        p = filedialog.asksaveasfilename(parent=self, title="Exportálás", defaultextension=".ics",
                                         initialfile="ArrabonaNaptar.ics",
                                         filetypes=[("iCalendar", "*.ics")])
        if not p:
            return
        s = self.app.settings
        txt = ical.export(self.app.store.events, shifts=self.app.store.shifts if s.get("publish_shifts", True) else None,
                          shift_types=self.app.store.shift_types, birthdays=s.get("publish_birthdays", True))
        try:
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(txt)
        except OSError as ex:
            self.err.config(text=f"Nem sikerült menteni: {ex}")
            return
        self.pub_state.config(text=f"Kész: {p}\nEzt Google Naptárba (Beállítások → Importálás) vagy iPhone-ra "
                                   "(megnyitás a Fájlok appból) is beolvashatod.")

    def import_file(self):
        p = filedialog.askopenfilename(parent=self, title="Importálás .ics-ből",
                                       filetypes=[("iCalendar", "*.ics"), ("Minden fájl", "*.*")])
        if not p:
            return
        try:
            text = feliratkozas.fetch(p)
        except RuntimeError as ex:
            self.err.config(text=str(ex))
            return
        self._import_text(text)

    def _import_text(self, text):
        ws, we = feliratkozas.window()
        try:
            evs = ical.import_text(text, ws, we)
        except Exception as ex:
            self.err.config(text=f"A fájl nem olvasható: {ex}")
            return
        if not evs:
            self.err.config(text="Nem találtam benne eseményt.")
            return
        add, upd = self.app.store.merge_import(evs)
        self.err.config(text="")
        self.pub_state.config(text=f"Importálva: {add} új esemény" + (f", {upd} frissítve" if upd else "") + ".")
        self.app.render()


class ExtEventDialog(Dialog):
    """Külső naptárból jött (csak olvasható) esemény részletei."""

    def __init__(self, app, e):
        super().__init__(app, "Esemény")
        b = self.body
        self.e = e
        tk.Frame(b, bg=e.get("color") or COLORS['brand'], height=4).pack(fill=tk.X, pady=(0, 8))
        label(b, e["title"], bold=True, size=13, wraplength=420, justify=tk.LEFT).pack(anchor="w")
        d = ev._d(e["date"])
        when = hu_date(d, weekday=True)
        if e.get("end_date"):
            when += " – " + hu_date(ev._d(e["end_date"]), weekday=True)
        if not e.get("all_day"):
            when += f"  {e['time']}" + (f"–{e['end_time']}" if e.get("end_time") else "")
        label(b, when, size=10).pack(anchor="w", pady=(4, 0))
        if e.get("location"):
            label(b, "📍 " + e["location"], size=10, wraplength=420, justify=tk.LEFT).pack(anchor="w", pady=(4, 0))
        if e.get("notes"):
            label(b, e["notes"][:1500], soft=True, size=9, wraplength=420, justify=tk.LEFT).pack(anchor="w", pady=(6, 0))
        label(b, f"Naptár: {e.get('cal_name') or 'külső'} (csak olvasható – a módosítás az eredeti helyén)",
              soft=True, size=9, wraplength=420, justify=tk.LEFT).pack(anchor="w", pady=(10, 0))
        bf = tk.Frame(b, bg=COLORS['panel'])
        bf.pack(fill=tk.X, pady=(12, 0))
        btn(bf, "Másolat a saját naptárba", self.copy, small=True).pack(side=tk.LEFT)
        btn(bf, "Bezár", self.destroy, primary=True).pack(side=tk.RIGHT)
        self.finish()

    def copy(self):
        e = self.e
        n = ev.new_event(**{k: e[k] for k in ("title", "all_day", "date", "time", "end_date", "end_time",
                                                 "location", "notes")})
        n["color"] = e.get("color") or ev.COLORS[0]
        self.app.store.upsert(n)
        self.destroy()
        self.app.render()
        EventDialog(self.app, self.app.store.get(n["id"]), ev._d(n["date"]))


# ======================================================================
#  [v1.4.0] Görgethető keret, teendők, szabadság, időjárás-település
# ======================================================================
class ScrollFrame(tk.Frame):
    """Függőlegesen görgethető keret (egérgörgővel is). A tartalom a .inner-be kerül."""

    def __init__(self, parent, bg=None):
        bg = bg or COLORS['panel']
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.sb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.sb.set)
        self.sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _wheel(self, e):
        try:
            if self.inner.winfo_height() > self.canvas.winfo_height():
                self.canvas.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")
        except (tk.TclError, TypeError):
            pass

    def to_top(self):
        try:
            self.canvas.yview_moveto(0)
        except tk.TclError:
            pass


class TodoDialog(Dialog):
    def __init__(self, app, td, due=None):
        super().__init__(app, "Teendő szerkesztése" if td else "Új teendő")
        b = self.body
        self.td = td
        label(b, "Teendő *").grid(row=0, column=0, sticky="w")
        self.title_v = tk.StringVar(value=td["title"] if td else "")
        te = entry(b, self.title_v, width=44)
        te.grid(row=1, column=0, columnspan=4, sticky="we", ipady=4, pady=(2, 10))
        label(b, "Határidő (üresen is hagyhatod)").grid(row=2, column=0, sticky="w")
        d0 = ev._d(td.get("due")) if td else due
        self.due_v = tk.StringVar(value=d0.strftime("%Y.%m.%d.") if d0 else "")
        entry(b, self.due_v, width=12).grid(row=3, column=0, sticky="w", ipady=3, pady=(2, 10))
        qf = tk.Frame(b, bg=COLORS['panel'])
        qf.grid(row=3, column=1, columnspan=3, sticky="w", padx=6)
        t = app.today
        for txt, dd in (("Ma", t), ("Holnap", t + _dt.timedelta(days=1)),
                        ("Jövő hét", t + _dt.timedelta(days=7 - t.weekday())), ("Nincs", None)):
            btn(qf, txt, lambda x=dd: self.due_v.set(x.strftime("%Y.%m.%d.") if x else ""), small=True).pack(
                side=tk.LEFT, padx=1)
        label(b, "Megjegyzés").grid(row=4, column=0, sticky="w")
        self.notes = tk.Text(b, width=44, height=4, font=(FONT, 10), bg=COLORS['entry'], fg=COLORS['text'],
                             insertbackground=COLORS['text'], relief=tk.FLAT, highlightthickness=1,
                             highlightbackground=COLORS['divider'], wrap=tk.WORD)
        self.notes.grid(row=5, column=0, columnspan=4, sticky="we", pady=(2, 0))
        if td:
            self.notes.insert("1.0", td.get("notes", ""))
        self.err = label(b, "", size=9, fg=COLORS['bad'])
        self.err.grid(row=6, column=0, columnspan=4, sticky="w")
        bf = tk.Frame(b, bg=COLORS['panel'])
        bf.grid(row=7, column=0, columnspan=4, sticky="we", pady=(10, 0))
        if td:
            btn(bf, "Törlés", self.delete, danger=True).pack(side=tk.LEFT)
            btn(bf, "Kész ✓" if not td["done"] else "Újranyitás", self.toggle).pack(side=tk.LEFT, padx=6)
        btn(bf, "Mégse", self.destroy).pack(side=tk.RIGHT)
        btn(bf, "Mentés", self.save, primary=True).pack(side=tk.RIGHT, padx=6)
        te.bind("<Return>", lambda e: self.save())
        te.focus_set()
        self.finish()

    def save(self):
        t = self.title_v.get().strip()
        if not t:
            self.err.config(text="Írd be, mi a teendő.")
            return
        due = ""
        if self.due_v.get().strip():
            d = parse_date(self.due_v.get())
            if not d:
                self.err.config(text="A határidőt így add meg: 2026.11.25.")
                return
            due = d.isoformat()
        self.app.store.upsert_todo(t, due, self.notes.get("1.0", "end").strip(), tid=self.td["id"] if self.td else None)
        self.destroy()
        self.app.render()

    def toggle(self):
        self.app.store.toggle_todo(self.td["id"])
        self.destroy()
        self.app.render()

    def delete(self):
        if messagebox.askyesno(APP_NAME, f"Törlöd ezt a teendőt?\n\n{self.td['title']}", parent=self):
            self.app.store.delete_todo(self.td["id"])
            self.destroy()
            self.app.render()


class LeaveDialog(Dialog):
    """Szabadságkeret beállítása és a kivett / tervezett napok."""

    def __init__(self, app, year=None):
        super().__init__(app, "Szabadság")
        self.year = year or app.sel.year
        self.leave = app.store.data.setdefault("leave", {"birth_year": 0, "years": {}})
        b = self.body
        yf = tk.Frame(b, bg=COLORS['panel'])
        yf.grid(row=0, column=0, columnspan=4, sticky="w")
        btn(yf, "◀", lambda: self._go(-1), small=True).pack(side=tk.LEFT)
        self.y_lbl = label(yf, "", bold=True, size=14)
        self.y_lbl.pack(side=tk.LEFT, padx=10)
        btn(yf, "▶", lambda: self._go(1), small=True).pack(side=tk.LEFT)

        f = tk.Frame(b, bg=COLORS['panel'])
        f.grid(row=1, column=0, columnspan=4, sticky="w", pady=(12, 0))
        self.v = {k: tk.StringVar() for k in ("birth_year", "children", "disabled", "extra", "carried", "manual")}
        rows = (("birth_year", "Születési éved (az életkor szerinti pótszabadsághoz):"),
                ("children", "16 évesnél fiatalabb gyermekek száma ebben az évben:"),
                ("disabled", "…ebből fogyatékos gyermek (+2 nap / gyermek):"),
                ("extra", "Egyéb pótszabadság (nap):"),
                ("carried", "Előző évről áthozott napok:"),
                ("manual", "Kézi keret (ha a munkáltatód mást ad, pl. időarányosan – üresen: számolt):"))
        for i, (k, t) in enumerate(rows):
            label(f, t, size=9).grid(row=i, column=0, sticky="w", pady=2)
            e = entry(f, self.v[k], width=7)
            e.grid(row=i, column=1, sticky="w", padx=8, ipady=2)
            self.v[k].trace_add("write", lambda *a: self._preview())
        self.calc = label(b, "", size=10, bold=True, wraplength=520, justify=tk.LEFT)
        self.calc.grid(row=2, column=0, columnspan=4, sticky="w", pady=(10, 0))
        self.parts = label(b, "", soft=True, size=9, wraplength=520, justify=tk.LEFT)
        self.parts.grid(row=3, column=0, columnspan=4, sticky="w")
        self.days = label(b, "", size=9, wraplength=520, justify=tk.LEFT)
        self.days.grid(row=4, column=0, columnspan=4, sticky="w", pady=(10, 0))
        codes = ", ".join(sorted(szabadsag.leave_codes(app.store.shift_types))) or "nincs ilyen"
        label(b, f"Szabadságnak a(z) {codes} műszaktípusú napok számítanak (Műszaktípusok → „Szabadságkeretből "
                 "fogy”). A mai napig kivettnek, utána tervezettnek számítanak.\n"
                 "Alap: 20 nap + életkor szerint 1–10 nap (25 éves kortól) + gyermekek után 2 / 4 / 7 nap (Mt. 116–118. §).",
              soft=True, size=8, wraplength=520, justify=tk.LEFT).grid(row=5, column=0, columnspan=4, sticky="w", pady=(10, 0))
        self.err = label(b, "", size=9, fg=COLORS['bad'])
        self.err.grid(row=6, column=0, columnspan=4, sticky="w")
        bf = tk.Frame(b, bg=COLORS['panel'])
        bf.grid(row=7, column=0, columnspan=4, sticky="we", pady=(10, 0))
        btn(bf, "Szabadság bejelölése a naptárban", self.paint, small=True).pack(side=tk.LEFT)
        btn(bf, "Bezár", self.destroy).pack(side=tk.RIGHT)
        btn(bf, "Mentés", self.save, primary=True).pack(side=tk.RIGHT, padx=6)
        self._load()
        self.finish()

    def _load(self):
        self.y_lbl.config(text=f"{self.year}. év")
        cfg = szabadsag.year_cfg(self.leave, self.year)
        self._loading = True
        self.v["birth_year"].set(str(self.leave.get("birth_year") or ""))
        for k in ("children", "disabled", "extra", "carried"):
            self.v[k].set(str(cfg.get(k) or 0))
        self.v["manual"].set("" if cfg.get("manual") in (None, "", 0) else str(cfg["manual"]))
        self._loading = False
        self._preview()

    def _read(self):
        def num(k, lo=0, hi=400, empty=0):
            t = self.v[k].get().strip()
            if not t:
                return empty
            try:
                n = int(t)
            except ValueError:
                raise ValueError(k)
            if not lo <= n <= hi:
                raise ValueError(k)
            return n
        by = num("birth_year", 0, 2100)
        if by and not 1930 <= by <= self.year:
            raise ValueError("birth_year")
        return by, {"children": num("children", 0, 20), "disabled": num("disabled", 0, 20),
                    "extra": num("extra", 0, 100), "carried": num("carried", 0, 100),
                    "manual": num("manual", 0, 200, None)}

    def _preview(self):
        if getattr(self, "_loading", False) or not hasattr(self, "calc"):
            return
        try:
            by, cfg = self._read()
            self.err.config(text="")
        except ValueError:
            self.err.config(text="Csak számokat írj be (a születési év pl. 1985).")
            return
        tmp = {"birth_year": by, "years": dict(self.leave.get("years") or {})}
        tmp["years"][str(self.year)] = cfg
        sm = szabadsag.summary(tmp, self.app.store.shifts, self.app.store.shift_types, self.year, self.app.today)
        p = sm["parts"]
        self.calc.config(text=f"Keret: {sm['total']} nap  ·  kivett: {len(sm['taken'])}  ·  tervezett: "
                              f"{len(sm['planned'])}  ·  marad: {sm['remaining']}",
                         fg=COLORS['bad'] if sm["remaining"] < 0 else COLORS['text'])
        if "manual" in p:
            pt = f"Kézi keret {p['manual']} nap" + (f" + áthozott {p['carried']}" if p["carried"] else "")
        else:
            pt = (f"Alap 20 + életkor {p['age']} + gyermek {p['children']}"
                  + (f" + egyéb {p['extra']}" if p["extra"] else "") + (f" + áthozott {p['carried']}" if p["carried"] else ""))
        self.parts.config(text=pt + (f"\n{sm['warn']}" if sm["warn"] else ""))

        def fmt(lst):
            if not lst:
                return "–"
            by_m = {}
            for d in lst:
                by_m.setdefault(d.month, []).append(str(d.day))
            return "; ".join(f"{HR[m - 1]} {', '.join(v)}" for m, v in sorted(by_m.items()))
        self.days.config(text=f"Kivett: {fmt(sm['taken'])}\nTervezett: {fmt(sm['planned'])}")

    def save(self):
        try:
            by, cfg = self._read()
        except ValueError:
            self.err.config(text="Csak számokat írj be (a születési év pl. 1985).")
            return False
        self.leave["birth_year"] = by
        self.leave.setdefault("years", {})[str(self.year)] = cfg
        self.app.store.save()
        self.app.render_side()
        self.err.config(text="Elmentve.", fg=COLORS['ok'])
        return True

    def _go(self, step):
        if self.save():
            self.year += step
            self._load()

    def paint(self):
        if not self.save():
            return
        code = next(iter(sorted(szabadsag.leave_codes(self.app.store.shift_types))), None)
        self.destroy()
        if code:
            if self.app.paint_code is None:
                self.app.toggle_paint()
            self.app._set_paint(code)
            self.app.render()


class PlaceDialog(Dialog):
    """Település választása az időjáráshoz."""

    def __init__(self, app):
        super().__init__(app, "Időjárás – település")
        b = self.body
        cur = app.place()
        label(b, f"Most: {cur.get('name')}", bold=True, size=11).grid(row=0, column=0, columnspan=3, sticky="w")
        self.q = tk.StringVar()
        e = entry(b, self.q, width=28)
        e.grid(row=1, column=0, sticky="w", ipady=3, pady=(8, 0))
        e.bind("<Return>", lambda ev_: self.search())
        btn(b, "Keresés", self.search, primary=True, small=True).grid(row=1, column=1, padx=6, pady=(8, 0))
        self.lb = tk.Listbox(b, width=52, height=8, bg=COLORS['entry'], fg=COLORS['text'], font=(FONT, 10),
                             relief=tk.FLAT, highlightthickness=1, highlightbackground=COLORS['divider'])
        self.lb.grid(row=2, column=0, columnspan=3, sticky="we", pady=(8, 0))
        self.lb.bind("<Double-1>", lambda ev_: self.choose())
        self.msg = label(b, "Írd be a település nevét (pl. Győr, Mosonmagyaróvár), majd Keresés.", soft=True, size=9,
                         wraplength=420, justify=tk.LEFT)
        self.msg.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.res = []
        bf = tk.Frame(b, bg=COLORS['panel'])
        bf.grid(row=4, column=0, columnspan=3, sticky="we", pady=(10, 0))
        btn(bf, "Mégse", self.destroy).pack(side=tk.RIGHT)
        btn(bf, "Kiválaszt", self.choose, primary=True).pack(side=tk.RIGHT, padx=6)
        e.focus_set()
        self.finish()

    def search(self):
        q = self.q.get().strip()
        if len(q) < 2:
            return
        self.msg.config(text="Keresés…")

        def done(ok, res):
            try:
                if not self.winfo_exists():
                    return
            except tk.TclError:
                return
            self.lb.delete(0, tk.END)
            if not ok:
                self.msg.config(text=str(res))
                return
            self.res = res
            for r in res:
                self.lb.insert(tk.END, f"{r['name']}  –  {r['region']}, {r['country']}".replace(" – , ", " – "))
            self.msg.config(text="Nincs találat." if not res else "Válaszd ki, majd Kiválaszt (vagy dupla kattintás).")
            if res:
                self.lb.selection_set(0)
        self.app.run_bg(lambda: idojaras.geocode(q), done)

    def choose(self):
        s = self.lb.curselection()
        if not s or not self.res:
            return
        r = self.res[s[0]]
        self.app.settings["weather_place"] = {"name": r["name"], "lat": r["lat"], "lon": r["lon"]}
        self.app.settings["weather_enabled"] = True
        save_settings(self.app.settings)
        self.destroy()
        self.app.weather = None
        self.app.render()
        self.app.refresh_weather()


# ======================================================================
#  [v1.6.0] Szerveres szinkron beállítása
# ======================================================================
class ServerDialog(Dialog):
    def __init__(self, app):
        super().__init__(app, "Szerver-szinkron")
        b = self.body
        s = app.settings
        label(b, "Saját szerver (pl. arrabonagaming.hu)", bold=True, size=12).grid(row=0, column=0, columnspan=3, sticky="w")
        label(b, "A gép és a telefon a saját tárhelyeden keresztül szinkronizál – automatikusan, Dropbox és "
                 "„Küldés a gépre” nélkül. A jelszót a program nem tárolja, csak egy eszköz-azonosítót.",
              soft=True, size=9, wraplength=460, justify=tk.LEFT).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 10))
        self.url = tk.StringVar(value=s.get("sync_url") or "https://arrabonagaming.hu/naptar/")
        self.user = tk.StringVar(value=s.get("sync_user", ""))
        self.pw = tk.StringVar()
        for i, (t, v, sh) in enumerate((("Cím:", self.url, ""), ("Felhasználónév:", self.user, ""),
                                        ("Jelszó:", self.pw, "•"))):
            label(b, t, size=10).grid(row=2 + i, column=0, sticky="w", pady=3)
            e = entry(b, v, width=40)
            if sh:
                e.config(show=sh)
            e.grid(row=2 + i, column=1, columnspan=2, sticky="we", padx=6, ipady=2)
        self.st_lbl = label(b, "", size=9, wraplength=460, justify=tk.LEFT)
        self.st_lbl.grid(row=5, column=0, columnspan=3, sticky="w", pady=(10, 0))
        bf = tk.Frame(b, bg=COLORS['panel'])
        bf.grid(row=6, column=0, columnspan=3, sticky="we", pady=(12, 0))
        self.login_btn = btn(bf, "Bejelentkezés", self.do_login, primary=True, small=True)
        self.login_btn.pack(side=tk.LEFT)
        btn(bf, "Szinkron most", self.sync_now, small=True).pack(side=tk.LEFT, padx=6)
        btn(bf, "Kijelentkezés", self.do_logout, small=True).pack(side=tk.LEFT)
        btn(bf, "Bezár", self.destroy).pack(side=tk.RIGHT)
        label(b, "Telefonon: nyisd meg a fenti címet Safariban → Megosztás → Főképernyőhöz adás, és jelentkezz be "
                 "ugyanezzel a felhasználóval.", soft=True, size=8, wraplength=460,
              justify=tk.LEFT).grid(row=7, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self._show()
        self.finish()

    def _show(self, extra=""):
        s = self.app.settings
        if s.get("sync_token"):
            t = f"✓ Bejelentkezve: {s.get('sync_user', '')} @ {s.get('sync_url', '')}"
            if self.app.srv_state:
                t += f"\nUtolsó szinkron: {self.app.srv_state}"
            col = COLORS['ok']
        else:
            t, col = "Nincs bejelentkezve.", COLORS['text_soft']
        self.st_lbl.config(text=t + (f"\n{extra}" if extra else ""), fg=col if not extra.startswith("⚠") else COLORS['bad'])

    def do_login(self):
        base = szerver.normalize_url(self.url.get())
        user, pw = self.user.get().strip(), self.pw.get()
        if not base or not user or not pw:
            self._show("⚠ Add meg a címet, a felhasználónevet és a jelszót.")
            return
        if not szerver.is_secure(base):
            self._show("⚠ Csak https:// címmel működik.")
            return
        self.login_btn.config(state=tk.DISABLED)
        self._show("Bejelentkezés…")

        def done(ok, res):
            try:
                self.login_btn.config(state=tk.NORMAL)
            except tk.TclError:
                return
            if not ok:
                self._show(f"⚠ {res}")
                return
            token, uname = res
            s = self.app.settings
            s.update(sync_url=base, sync_user=uname, sync_token=token)
            save_settings(s)
            self.pw.set("")
            self.url.set(base)
            self.app._srv_last = None
            self._show("Bejelentkezve – első feltöltés…")
            self.app.server_sync(force=True, done=lambda o, r: self._after_sync(o, r))
        self.app.run_bg(lambda: szerver.login(base, user, pw), done)

    def _after_sync(self, ok, res):
        try:
            self._show("" if ok else f"⚠ {res}")
        except tk.TclError:
            pass

    def sync_now(self):
        if not self.app.settings.get("sync_token"):
            self._show("⚠ Előbb jelentkezz be.")
            return
        self._show("Szinkron…")
        if not self.app.server_sync(force=True, done=lambda o, r: self._after_sync(o, r)):
            self._show("Már folyamatban van egy szinkron, pár másodperc.")

    def do_logout(self):
        s = self.app.settings
        base, token = s.get("sync_url", ""), s.get("sync_token", "")
        if not token:
            return
        if not messagebox.askyesno(APP_NAME, "Kijelentkezel a szerverről ezen a gépen?\n"
                                   "(A szerveren lévő adatok megmaradnak.)", parent=self):
            return
        s["sync_token"] = ""
        save_settings(s)
        self.app.srv_state = ""
        self.app.run_bg(lambda: szerver.logout(base, token), lambda ok, r: None)
        self._show()
