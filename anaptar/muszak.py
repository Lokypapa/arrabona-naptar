# -*- coding: utf-8 -*-
"""[v1.1.0] Munkarend / műszakbeosztás.

Műszaktípus (dict): code ("DE"), name ("Délelőtt"), start "06:00", end "14:00" (ha end <= start,
másnap ér véget), hours (fizetett órák; 0 = az időkből számolva), color, kind:
    "work"  - munkában töltött műszak
    "leave" - fizetett távollét (szabadság, betegszabadság): beleszámít a keretbe
    "off"   - pihenőnap (0 óra)
reminder (perc a kezdés előtt, 0 = nincs)

Beosztás: data["shifts"] = {"YYYY-MM-DD": "DE", ...}
"""
import datetime as _dt

from . import unnepek

DEFAULT_TYPES = [
    {"code": "DE", "name": "Délelőtt", "start": "06:00", "end": "14:00", "hours": 0, "color": "#2980b9", "kind": "work", "reminder": 0},
    {"code": "DU", "name": "Délután", "start": "14:00", "end": "22:00", "hours": 0, "color": "#e67e22", "kind": "work", "reminder": 0},
    {"code": "ÉJ", "name": "Éjszaka", "start": "22:00", "end": "06:00", "hours": 0, "color": "#2c3e50", "kind": "work", "reminder": 0},
    {"code": "N12", "name": "Nappal (12 óra)", "start": "06:00", "end": "18:00", "hours": 0, "color": "#16a085", "kind": "work", "reminder": 0},
    {"code": "É12", "name": "Éjszaka (12 óra)", "start": "18:00", "end": "06:00", "hours": 0, "color": "#8e44ad", "kind": "work", "reminder": 0},
    {"code": "SZ", "name": "Szabadság", "start": "", "end": "", "hours": 8, "color": "#27ae60", "kind": "leave", "reminder": 0, "counts_leave": True},
    {"code": "B", "name": "Betegszabadság", "start": "", "end": "", "hours": 8, "color": "#c0392b", "kind": "leave", "reminder": 0},
    {"code": "P", "name": "Pihenőnap", "start": "", "end": "", "hours": 0, "color": "#7f8c8d", "kind": "off", "reminder": 0},
]
KINDS = {"work": "Munka", "leave": "Fizetett távollét", "off": "Pihenőnap"}
NIGHT_START, NIGHT_END = 22, 6          # éjszakai munka: 22:00-06:00 (Mt. 89. §)


def _mins(t):
    try:
        h, m = [int(x) for x in str(t).split(":")[:2]]
        return h * 60 + m
    except (ValueError, TypeError):
        return None


def span(t):
    """(kezdés, vége) datetime-hoz kellő percek: (start_min, dur_min) vagy None."""
    a, b = _mins(t.get("start")), _mins(t.get("end"))
    if a is None or b is None:
        return None
    dur = (b - a) % 1440 or 1440
    return a, dur


def hours_of(t):
    if float(t.get("hours") or 0) > 0:
        return float(t["hours"])
    sp = span(t)
    return round(sp[1] / 60, 2) if sp else 0.0


def night_hours(t):
    sp = span(t)
    if not sp or t.get("kind") != "work":
        return 0.0
    a, dur = sp
    n = 0
    for m in range(a, a + dur):
        h = (m // 60) % 24
        if h >= NIGHT_START or h < NIGHT_END:
            n += 1
    return round(n / 60, 2)


def label_time(t):
    if t.get("start") and t.get("end"):
        return f"{t['start']}–{t['end']}"
    return ""


def types_by_code(types):
    return {t["code"]: t for t in types}


def normalize_type(t):
    t = dict(t)
    t["code"] = str(t.get("code") or "").strip()[:4]
    t["name"] = str(t.get("name") or t["code"]).strip()[:30]
    for k in ("start", "end"):
        m = _mins(t.get(k))
        t[k] = f"{m // 60:02d}:{m % 60:02d}" if m is not None and str(t.get(k)).strip() else ""
    try:
        t["hours"] = max(0.0, min(24.0, float(t.get("hours") or 0)))
    except ValueError:
        t["hours"] = 0.0
    t["kind"] = t.get("kind") if t.get("kind") in KINDS else "work"
    t["color"] = t.get("color") or "#7f8c8d"
    # [v1.4.0] a szabadságkeretből fogy-e (régi adatoknál: az SZ kód igen)
    t["counts_leave"] = bool(t["counts_leave"]) if "counts_leave" in t else (t["code"].upper() == "SZ")
    try:
        t["reminder"] = max(0, int(t.get("reminder") or 0))
    except ValueError:
        t["reminder"] = 0
    return t


def apply_pattern(shifts, start, end, pattern, skip_holidays=False, swaps=None):
    """Minta (kódlista, '' = üres nap) ismétlése start..end között. Visszaad: hány nap lett beírva."""
    pattern = [p for p in pattern]
    if not pattern or end < start:
        return 0
    n, i, d = 0, 0, start
    while d <= end:
        code = pattern[i % len(pattern)]
        info = unnepek.day_info(d, swaps) if skip_holidays else None
        if skip_holidays and info["holiday"] and info["rest"]:
            pass                                   # ünnepnap: kimarad (de a minta lép tovább)
        elif code:
            shifts[d.isoformat()] = code
            n += 1
        else:
            shifts.pop(d.isoformat(), None)
        i += 1
        d += _dt.timedelta(days=1)
    return n


def month_summary(shifts, types, y, m, swaps=None):
    tb = types_by_code(types)
    d = _dt.date(y, m, 1)
    s = {"count": {}, "work_hours": 0.0, "leave_hours": 0.0, "night_hours": 0.0,
         "weekend_hours": 0.0, "holiday_hours": 0.0, "shifts": 0, "days_set": 0}
    while d.month == m:
        code = shifts.get(d.isoformat())
        t = tb.get(code)
        if t:
            s["days_set"] += 1
            s["count"][code] = s["count"].get(code, 0) + 1
            h = hours_of(t)
            if t["kind"] == "work":
                s["shifts"] += 1
                s["work_hours"] += h
                s["night_hours"] += night_hours(t)
                info = unnepek.day_info(d, swaps)
                if info["holiday"] and info["rest"]:
                    s["holiday_hours"] += h
                elif d.weekday() >= 5:
                    s["weekend_hours"] += h
            elif t["kind"] == "leave":
                s["leave_hours"] += h
        d += _dt.timedelta(days=1)
    s["keret"] = unnepek.workdays_in_month(y, m, swaps) * 8
    s["total"] = s["work_hours"] + s["leave_hours"]
    s["diff"] = s["total"] - s["keret"]
    for k in ("work_hours", "leave_hours", "night_hours", "weekend_hours", "holiday_hours", "total", "diff"):
        s[k] = round(s[k], 2)
    return s


def shift_start_dt(day, t):
    sp = span(t)
    if not sp:
        return None
    return _dt.datetime.combine(day, _dt.time(0, 0)) + _dt.timedelta(minutes=sp[0])


def due_shift_reminders(shifts, types, since, now):
    tb = types_by_code(types)
    out = []
    d = (since - _dt.timedelta(days=1)).date()
    while d <= (now + _dt.timedelta(days=2)).date():
        t = tb.get(shifts.get(d.isoformat()))
        if t and t.get("reminder") and t["kind"] == "work":
            st = shift_start_dt(d, t)
            if st:
                when = st - _dt.timedelta(minutes=t["reminder"])
                if since < when <= now:
                    out.append((f"muszak|{d.isoformat()}|{t['code']}", t, d, when))
        d += _dt.timedelta(days=1)
    return out


def fmt_h(h):
    return (f"{h:.0f}" if abs(h - round(h)) < 0.01 else f"{h:.1f}".replace(".", ",")) + " óra"
