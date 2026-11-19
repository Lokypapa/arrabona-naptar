# -*- coding: utf-8 -*-
"""Események: tárolás, ismétlődés, születésnapok, emlékeztetők.

Esemény (dict):
    id, kind ("event" | "birthday"), title, all_day (bool),
    date "YYYY-MM-DD", time "HH:MM" (all_day esetén ""), end_date, end_time,
    repeat {"freq": "none|daily|weekly|monthly|yearly", "interval": 1,
            "weekdays": [0..6] (heti ismétlésnél), "until": "YYYY-MM-DD" vagy "",
            "count": 0 (0 = korlátlan)},
    skip ["YYYY-MM-DD", ...]  - kihagyott alkalmak ("csak ezt az egyet törlöm"),
    reminders [percek az esemény előtt; egész napos eseménynél a nap reggeli időpontjához képest],
    color, location, notes, birth_year (születésnapnál, 0 = ismeretlen), created, modified
"""
import calendar
import copy
import datetime as _dt
import json
import os
import shutil
import uuid

from . import muszak

FREQS = ("none", "daily", "weekly", "monthly", "yearly")
FREQ_NAMES = {"none": "Nem ismétlődik", "daily": "Naponta", "weekly": "Hetente",
              "monthly": "Havonta", "yearly": "Évente"}
COLORS = ("#27ae60", "#2980b9", "#8e44ad", "#e67e22", "#c0392b", "#16a085", "#d4a017", "#7f8c8d")


def _d(s):
    try:
        return _dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _t(s):
    try:
        h, m = str(s).split(":")[:2]
        return _dt.time(int(h), int(m))
    except (ValueError, TypeError):
        return None


def now_ts():
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def new_event(**kw):
    e = {"id": uuid.uuid4().hex, "kind": "event", "title": "", "all_day": True,
         "date": _dt.date.today().isoformat(), "time": "", "end_date": "", "end_time": "",
         "repeat": {"freq": "none", "interval": 1, "weekdays": [], "until": "", "count": 0},
         "skip": [], "reminders": [], "color": COLORS[0], "location": "", "notes": "",
         "birth_year": 0, "created": now_ts(), "modified": now_ts()}
    e.update(kw)
    return normalize(e)


def normalize(e):
    e.setdefault("id", uuid.uuid4().hex)
    e.setdefault("kind", "event")
    e.setdefault("all_day", not e.get("time"))
    for k in ("title", "time", "end_date", "end_time", "location", "notes"):
        e[k] = str(e.get(k) or "")
    e.setdefault("color", COLORS[0])
    r = e.get("repeat") or {}
    e["repeat"] = {"freq": r.get("freq") if r.get("freq") in FREQS else "none",
                   "interval": max(1, int(r.get("interval") or 1)),
                   "weekdays": sorted({int(x) for x in r.get("weekdays") or [] if 0 <= int(x) <= 6}),
                   "until": str(r.get("until") or ""), "count": max(0, int(r.get("count") or 0))}
    if e["kind"] == "birthday":
        e["all_day"] = True
        e["repeat"] = {"freq": "yearly", "interval": 1, "weekdays": [], "until": "", "count": 0}
    e["skip"] = sorted({s for s in e.get("skip") or [] if _d(s)})
    e["reminders"] = sorted({int(x) for x in e.get("reminders") or [] if int(x) >= 0})
    e["birth_year"] = int(e.get("birth_year") or 0)
    return e


# ---------------------------------------------------------------- ismétlődés
def _add_months(d, n, anchor_day):
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    return _dt.date(y, m, min(anchor_day, calendar.monthrange(y, m)[1]))


def occurrences(e, start, end):
    """Az esemény kezdőnapjai [start, end] között (date lista, növekvő)."""
    first = _d(e.get("date"))
    if first is None or end < start:
        return []
    r = e["repeat"]
    freq, iv = r["freq"], r["interval"]
    until = _d(r.get("until")) or _dt.date.max
    limit_count = r.get("count") or 0
    skip = set(e.get("skip") or [])
    span = 0
    if not e.get("all_day") or e.get("end_date"):
        ed = _d(e.get("end_date"))
        if ed and ed > first:
            span = (ed - first).days           # többnapos esemény: a korábban kezdődőt is mutatjuk
    lo = start - _dt.timedelta(days=span)
    out, n = [], 0

    def take(d):
        if lo <= d <= end and d.isoformat() not in skip:
            out.append(d)

    if freq == "none":
        if first <= end:
            take(first)
        return out
    if freq == "daily":
        if first < lo:
            k = (lo - first).days // iv
            n = k
            d = first + _dt.timedelta(days=k * iv)
        else:
            d = first
        while d <= end and d <= until and (not limit_count or n < limit_count):
            take(d)
            n += 1
            d += _dt.timedelta(days=iv)
        return out
    if freq == "weekly":
        wds = r["weekdays"] or [first.weekday()]
        week0 = first - _dt.timedelta(days=first.weekday())
        if limit_count:
            wk = week0                                # számlálás az elejétől
        else:
            k = max(0, ((lo - week0).days // 7) // iv)
            wk = week0 + _dt.timedelta(weeks=k * iv)
        while wk <= end and wk <= until:
            for wd in wds:
                d = wk + _dt.timedelta(days=wd)
                if d < first or d > until:
                    continue
                if limit_count and n >= limit_count:
                    return out
                n += 1
                if d <= end:
                    take(d)
            wk += _dt.timedelta(weeks=iv)
        return out
    if freq in ("monthly", "yearly"):
        step = iv if freq == "monthly" else 12 * iv
        k = 0
        if not limit_count and first < lo:
            months = (lo.year - first.year) * 12 + lo.month - first.month
            k = max(0, months // step - 1)
        while True:
            d = _add_months(first, k * step, first.day)
            if d > end or d > until or (limit_count and k >= limit_count):
                break
            take(d)
            k += 1
        return out
    return out


def age_on(e, day):
    """Születésnap: hány éves lesz az adott napon (None, ha nincs születési év)."""
    by = int(e.get("birth_year") or 0)
    if e.get("kind") != "birthday" or by <= 0 or day.year <= by:
        return None
    return day.year - by


def display_title(e, day):
    if e.get("kind") == "birthday":
        a = age_on(e, day)
        return f"🎂 {e['title']}" + (f" ({a} éves)" if a else "")
    return e["title"]


def instances(events, start, end):
    """[(nap, esemény), ...] időrendben (egész napos elöl)."""
    out = []
    for e in events:
        for d in occurrences(e, start, end):
            out.append((d, e))
    out.sort(key=lambda x: (x[0], not x[1].get("all_day"), x[1].get("time") or "", x[1]["title"].casefold()))
    return out


def covers(e, occ_day, day):
    """Az occ_day-en kezdődő alkalom érinti-e a 'day' napot (többnapos esemény)."""
    ed = _d(e.get("end_date"))
    first = _d(e.get("date"))
    if not ed or not first or ed <= first:
        return occ_day == day
    return occ_day <= day <= occ_day + (ed - first)


def events_on(events, day):
    res = []
    for d, e in instances(events, day - _dt.timedelta(days=0), day):
        if covers(e, d, day):
            res.append((d, e))
    return res


# ---------------------------------------------------------------- emlékeztetők
def reminder_triggers(e, occ_day, allday_time):
    """(időpont, perc) párok az adott alkalomhoz."""
    if e.get("all_day"):
        base = _dt.datetime.combine(occ_day, _t(allday_time) or _dt.time(8, 0))
    else:
        base = _dt.datetime.combine(occ_day, _t(e.get("time")) or _dt.time(9, 0))
    return [(base - _dt.timedelta(minutes=m), m) for m in e.get("reminders") or []]


def event_start_dt(e, occ_day):
    if e.get("all_day"):
        return _dt.datetime.combine(occ_day, _dt.time(0, 0))
    return _dt.datetime.combine(occ_day, _t(e.get("time")) or _dt.time(9, 0))


def due_reminders(events, since, now, allday_time):
    """Azok az emlékeztetők, amelyek (since, now] között jártak le.
    Visszaad: [(kulcs, esemény, alkalom napja, emlékeztető ideje, perc)]"""
    out = []
    start = (since - _dt.timedelta(days=1)).date()
    end = (now + _dt.timedelta(days=60)).date()      # 60 napos előre szólás is jó legyen
    for e in events:
        if not e.get("reminders"):
            continue
        for d in occurrences(e, start, end):
            for when, m in reminder_triggers(e, d, allday_time):
                if since < when <= now:
                    out.append((f"{e['id']}|{d.isoformat()}|{m}", e, d, when, m))
    out.sort(key=lambda x: x[3])
    return out


def reminder_label(m):
    if m == 0:
        return "az esemény idején"
    if m % 1440 == 0:
        n = m // 1440
        return "aznap" if n == 0 else ("1 nappal előtte" if n == 1 else f"{n} nappal előtte")
    if m % 60 == 0:
        return f"{m // 60} órával előtte"
    return f"{m} perccel előtte"


# ---------------------------------------------------------------- tárolás
class Store:
    """Atomi mentés (+ .bak) a %APPDATA%\\ArrabonaNaptar\\naptar.json fájlba."""

    def __init__(self, path):
        self.path = path
        self.data = {"version": 1, "events": [], "watched_names": [], "extra_swaps": [],
                     "reminder_state": {"last_check": "", "fired": {}},
                     "shift_types": copy.deepcopy(muszak.DEFAULT_TYPES), "shifts": {}}
        self.load()

    def load(self):
        for p in (self.path, self.path + ".bak"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict) and isinstance(d.get("events"), list):
                    self.data.update(d)
                    break
            except (OSError, ValueError):
                continue
        self.data["events"] = [normalize(e) for e in self.data.get("events", []) if isinstance(e, dict)]
        self.data.setdefault("watched_names", [])
        self.data.setdefault("extra_swaps", [])
        self.data["shift_types"] = [muszak.normalize_type(t) for t in
                                    (self.data.get("shift_types") or copy.deepcopy(muszak.DEFAULT_TYPES))]
        self.data["shifts"] = {k: v for k, v in (self.data.get("shifts") or {}).items()
                               if _d(k) and isinstance(v, str)}
        st = self.data.setdefault("reminder_state", {})
        st.setdefault("last_check", "")
        st.setdefault("fired", {})
        self.data.setdefault("calendars", [])       # [v1.3.0] feliratkozott külső naptárak
        self.data.setdefault("todos", [])           # [v1.4.0] teendők
        self.data.setdefault("leave", {"birth_year": 0, "years": {}})   # [v1.4.0] szabadságkeret

    on_save = None          # [v1.3.0] visszahívás mentés után (pl. .ics közzététel)

    def save(self):
        self._write()
        if self.on_save:
            try:
                self.on_save()
            except Exception:
                pass

    def _write(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(self.path):
            try:
                shutil.copy2(self.path, self.path + ".bak")
            except OSError:
                pass
        os.replace(tmp, self.path)

    # --- események
    @property
    def events(self):
        return self.data["events"]

    def get(self, eid):
        return next((e for e in self.events if e["id"] == eid), None)

    def upsert(self, e):
        e = normalize(copy.deepcopy(e))
        e["modified"] = now_ts()
        for i, x in enumerate(self.events):
            if x["id"] == e["id"]:
                self.events[i] = e
                break
        else:
            self.events.append(e)
        self.save()
        return e

    def delete(self, eid):
        self.data["events"] = [e for e in self.events if e["id"] != eid]
        self.save()

    def skip_occurrence(self, eid, day):
        e = self.get(eid)
        if e:
            e["skip"] = sorted(set(e.get("skip") or []) | {day.isoformat()})
            e["modified"] = now_ts()
            self.save()

    def end_series_before(self, eid, day):
        """Ettől az alkalomtól kezdve nincs több (a korábbiak maradnak)."""
        e = self.get(eid)
        if e:
            e["repeat"]["until"] = (day - _dt.timedelta(days=1)).isoformat()
            e["repeat"]["count"] = 0
            e["modified"] = now_ts()
            self.save()

    # --- figyelt névnapok: [{"name": "Katalin", "label": "Kati néni"}]
    @property
    def watched(self):
        return self.data["watched_names"]

    def swaps(self):
        out = []
        for s in self.data.get("extra_swaps") or []:
            a, b = _d(s.get("work")), _d(s.get("rest"))
            if a and b:
                out.append((a, b))
        return out

    # --- [v1.1.0] műszakok
    @property
    def shift_types(self):
        return self.data["shift_types"]

    @property
    def shifts(self):
        return self.data["shifts"]

    def shift_on(self, day):
        code = self.shifts.get(day.isoformat())
        return muszak.types_by_code(self.shift_types).get(code) if code else None

    def set_shift(self, day, code, save=True):
        if code:
            self.shifts[day.isoformat()] = code
        else:
            self.shifts.pop(day.isoformat(), None)
        if save:
            self.save()

    # ---------- [v1.4.0] teendők ----------
    @property
    def todos(self):
        return self.data["todos"]

    def todo(self, tid):
        return next((t for t in self.todos if t["id"] == tid), None)

    def upsert_todo(self, title, due="", notes="", tid=None):
        t = self.todo(tid) if tid else None
        if t is None:
            t = {"id": uuid.uuid4().hex[:12], "done": False, "done_at": "",
                 "created": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            self.todos.append(t)
        t.update(title=title.strip()[:200], due=due or "", notes=notes or "")
        self.save()
        return t

    def toggle_todo(self, tid):
        t = self.todo(tid)
        if t:
            t["done"] = not t["done"]
            t["done_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M") if t["done"] else ""
            self.save()
        return t

    def delete_todo(self, tid):
        self.data["todos"] = [t for t in self.todos if t["id"] != tid]
        self.save()

    def todos_on(self, d, include_overdue=False):
        k = d.isoformat()
        out = [t for t in self.todos if t.get("due") == k]
        if include_overdue:
            out = [t for t in self.todos if not t["done"] and t.get("due") and t["due"] < k] + out
        return sorted(out, key=lambda t: (t["done"], t.get("due") or "9999", t["title"].casefold()))

    def merge_import(self, events):
        """[v1.3.0] Importált események: ami már megvan (azonos azonosító vagy .ics UID), az frissül."""
        by_id = {e["id"]: i for i, e in enumerate(self.events)}
        by_uid = {e.get("ics_uid"): i for i, e in enumerate(self.events) if e.get("ics_uid")}
        added = updated = 0
        for n in events:
            n = normalize(n)
            i = by_id.get(n["id"])
            if i is None and n.get("ics_uid"):
                i = by_uid.get(n["ics_uid"])
            if i is not None:
                n["id"] = self.events[i]["id"]
                n["created"] = self.events[i].get("created", n.get("created"))
                self.events[i] = n
                updated += 1
            else:
                self.events.append(n)
                by_id[n["id"]] = len(self.events) - 1
                added += 1
        self.save()
        return added, updated

    def search(self, q):
        q = q.casefold().strip()
        if not q:
            return []
        return [e for e in self.events if q in " ".join((e["title"], e["location"], e["notes"])).casefold()]
