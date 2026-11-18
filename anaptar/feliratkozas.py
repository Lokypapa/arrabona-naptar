# -*- coding: utf-8 -*-
"""[v1.3.0] Külső naptárak (feliratkozás .ics címre vagy fájlra) és a saját naptár közzététele.

Naptár-bejegyzés (store.data["calendars"]):
    {"id", "name", "url", "color", "enabled": bool, "reminders": bool,
     "last_sync": "YYYY-MM-DDTHH:MM", "error": "", "count": 0}
A letöltött tartalom a %APPDATA%\\ArrabonaNaptar\\naptarak\\<id>.ics fájlba kerül, így internet nélkül
is látszik a legutóbbi állapot.
"""
import datetime as _dt
import os
import re
import urllib.error
import urllib.request
import uuid

from . import ical
from .common import data_dir

USER_AGENT = "ArrabonaNaptar/1.3 (+https://github.com/Lokypapa)"
PUBLISH_NAME = "ArrabonaNaptar.ics"


def cache_dir():
    p = os.path.join(data_dir(), "naptarak")
    os.makedirs(p, exist_ok=True)
    return p


def normalize_url(u):
    u = (u or "").strip().strip('"')
    if u.lower().startswith("webcal://"):
        u = "https://" + u[9:]
    elif u.lower().startswith("webcals://"):
        u = "https://" + u[10:]
    if "dropbox.com" in u.lower():                       # megosztott Dropbox-link: közvetlen letöltés
        u = re.sub(r"([?&])dl=0", r"\1dl=1", u)
        if "dl=1" not in u and "raw=1" not in u:
            u += ("&" if "?" in u else "?") + "dl=1"
    return u


def is_local(u):
    u = (u or "").strip().strip('"')
    return u.lower().startswith("file://") or bool(re.match(r"^[a-zA-Z]:[\\/]", u)) or u.startswith("\\\\") \
        or (u.startswith("/") and os.path.exists(u))


def kind_label(u):
    lu = (u or "").lower()
    if is_local(u):
        return "Fájl"
    for k, n in (("google.com", "Google"), ("icloud.com", "iCloud"), ("outlook.", "Outlook"),
                 ("office365", "Outlook"), ("live.com", "Outlook"), ("dropbox", "Dropbox")):
        if k in lu:
            return n
    return "Webcím"


def fetch(url, timeout=30):
    """A naptár szövege (str). Hibánál magyar üzenetű RuntimeError."""
    if is_local(url):
        p = url.strip().strip('"')
        if p.lower().startswith("file://"):
            p = urllib.request.url2pathname(p[7:])
        try:
            with open(p, "rb") as f:
                raw = f.read()
        except OSError as ex:
            raise RuntimeError(f"A fájl nem olvasható: {ex.strerror or ex}")
    else:
        u = normalize_url(url)
        if not u.lower().startswith(("http://", "https://")):
            raise RuntimeError("A cím https:// vagy webcal:// kezdetű legyen (vagy egy .ics fájl útvonala).")
        req = urllib.request.Request(u, headers={"User-Agent": USER_AGENT, "Accept": "text/calendar, */*"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read(20 * 1024 * 1024)
        except urllib.error.HTTPError as ex:
            if ex.code in (401, 403):
                raise RuntimeError(f"Nincs hozzáférés ({ex.code}) – a titkos / nyilvános .ics címet add meg.")
            if ex.code == 404:
                raise RuntimeError("A cím nem található (404) – lehet, hogy közben új címet kapott a naptár.")
            raise RuntimeError(f"A szerver hibát adott: {ex.code}")
        except urllib.error.URLError as ex:
            raise RuntimeError(f"Nem érhető el (nincs internet?): {getattr(ex, 'reason', ex)}")
        except OSError as ex:
            raise RuntimeError(f"Letöltési hiba: {ex}")
    for enc in ("utf-8-sig", "cp1250", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if "BEGIN:VCALENDAR" not in text[:2000].upper():
        raise RuntimeError("Ez nem naptár (.ics) tartalom. Google-nél a „Titkos cím iCal formátumban”, "
                           "iCloudnál a nyilvános naptár linkje kell.")
    return text


def window(today=None):
    t = today or _dt.date.today()
    return t - _dt.timedelta(days=365), t + _dt.timedelta(days=730)


class Subscriptions:
    def __init__(self, store, settings):
        self.store = store
        self.settings = settings
        self._events = {}                 # naptár id → kibontott események
        for c in self.calendars:
            self.load_cached(c)

    @property
    def calendars(self):
        return self.store.data.setdefault("calendars", [])

    def get(self, cid):
        return next((c for c in self.calendars if c["id"] == cid), None)

    def add(self, name, url, color, reminders=False):
        c = {"id": uuid.uuid4().hex[:10], "name": name.strip() or "Naptár", "url": url.strip(), "color": color,
             "enabled": True, "reminders": bool(reminders), "last_sync": "", "error": "", "count": 0}
        self.calendars.append(c)
        self.store.save()
        return c

    def remove(self, cid):
        self.store.data["calendars"] = [c for c in self.calendars if c["id"] != cid]
        self._events.pop(cid, None)
        try:
            os.remove(os.path.join(cache_dir(), cid + ".ics"))
        except OSError:
            pass
        self.store.save()

    def _path(self, c):
        return os.path.join(cache_dir(), c["id"] + ".ics")

    def load_cached(self, c, text=None):
        if text is None:
            try:
                with open(self._path(c), "r", encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                self._events[c["id"]] = []
                return
        self.rebuild(c, text)

    def rebuild(self, c, text):
        try:
            cal = ical.parse(text)
            ws, we = window()
            rem = list(self.settings.get("default_reminders") or [15]) if c.get("reminders") else []
            self._events[c["id"]] = ical.expand(cal["events"], ws, we, c["id"], c.get("color") or "#2980b9",
                                                rem, c.get("name", ""))
        except Exception as ex:                  # hibás fájl ne vigye el a programot
            self._events[c["id"]] = []
            c["error"] = f"Hibás naptárfájl: {ex}"
            return None
        return cal

    def apply_text(self, c, text):
        """Letöltés után (fő szálon): mentés a gyorsítótárba, kibontás, állapot."""
        tmp = self._path(c) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, self._path(c))
        c["error"] = ""
        cal = self.rebuild(c, text)
        if cal and not c.get("name_set") and cal.get("name") and c.get("name") in ("", "Naptár"):
            c["name"] = cal["name"]
            self.recolor(c)
        c["count"] = len(self._events.get(c["id"], []))
        c["last_sync"] = _dt.datetime.now().strftime("%Y-%m-%dT%H:%M")

    def apply_error(self, c, msg):
        c["error"] = msg
        c["last_try"] = _dt.datetime.now().strftime("%Y-%m-%dT%H:%M")

    def due(self, now=None):
        """A frissítésre váró naptárak (bekapcsolt, és lejárt az idő – hibánál 10 perc múlva újra)."""
        now = now or _dt.datetime.now()
        every = max(5, int(self.settings.get("calendar_refresh_min", 30) or 30))
        out = []
        for c in self.calendars:
            if not c.get("enabled", True):
                continue
            last = c.get("last_try") if c.get("error") else c.get("last_sync")
            try:
                t = _dt.datetime.fromisoformat(last) if last else None
            except ValueError:
                t = None
            wait = 10 if c.get("error") else every
            if t is None or now - t >= _dt.timedelta(minutes=wait):
                out.append(c)
        return out

    def events(self):
        out = []
        for c in self.calendars:
            if c.get("enabled", True):
                out.extend(self._events.get(c["id"], []))
        return out

    def find(self, eid):
        for lst in self._events.values():
            for e in lst:
                if e["id"] == eid:
                    return e
        return None

    def search(self, q):
        q = q.casefold().strip()
        if not q:
            return []
        seen, out = set(), []
        for e in self.events():
            if q in " ".join((e["title"], e["location"], e["notes"])).casefold():
                k = (e["cal"], e["uid"])
                if k not in seen:                # ismétlődőből csak az első alkalom
                    seen.add(k)
                    out.append(e)
        return out

    def recolor(self, c):
        for e in self._events.get(c["id"], []):
            e["color"] = c["color"]
            e["cal_name"] = c["name"]


# ------------------------------------------------------------------ közzététel
def publish(store, settings, last=None):
    """A saját naptár kiírása a beállított mappába (ArrabonaNaptar.ics). Csak akkor ír, ha változott.
    Visszaad: (útvonal vagy None, a kiírt tartalom)."""
    folder = (settings.get("publish_dir") or "").strip()
    if not folder:
        return None, last
    txt = ical.export(store.events, shifts=store.shifts if settings.get("publish_shifts", True) else None,
                      shift_types=store.shift_types, birthdays=settings.get("publish_birthdays", True))
    path = os.path.join(folder, PUBLISH_NAME)
    if txt == last and os.path.exists(path):
        return path, txt
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            if f.read() == txt:
                return path, txt
    except OSError:
        pass
    os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(txt)
    os.replace(tmp, path)
    return path, txt
