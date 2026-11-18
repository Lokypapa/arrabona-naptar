# -*- coding: utf-8 -*-
"""[v1.3.0] iCalendar (.ics) olvasás és írás – külső naptárak (Google, iCloud, Outlook...) és közzététel.

Olvasás: VEVENT-ek (ismétlődés RRULE/EXDATE/RDATE, áthelyezett alkalom RECURRENCE-ID, időzónák).
A külső naptárak alkalmait egy időablakra (alapból −1 / +2 év) kibontjuk egyszerű, nem ismétlődő
eseményekké, így a nyári időszámítás és a bonyolult szabályok (pl. „minden hónap 2. keddje”) is pontosak.
Írás: a saját események (ismétlődéssel), születésnapok és kérésre a műszakok .ics fájlba.
"""
import calendar
import datetime as _dt
import hashlib
import re

try:
    from zoneinfo import ZoneInfo
except ImportError:                      # pragma: no cover
    ZoneInfo = None

from . import esemenyek as ev
from . import muszak

TZ_NAME = "Europe/Budapest"
UTC = _dt.timezone.utc

# Outlook / Exchange gyakran Windows-os időzóna-nevet ír
WIN_TZ = {
    "central europe standard time": "Europe/Budapest",
    "central european standard time": "Europe/Warsaw",
    "w. europe standard time": "Europe/Berlin",
    "romance standard time": "Europe/Paris",
    "gmt standard time": "Europe/London",
    "greenwich standard time": "Atlantic/Reykjavik",
    "e. europe standard time": "Europe/Bucharest",
    "fle standard time": "Europe/Kiev",
    "gtb standard time": "Europe/Athens",
    "russian standard time": "Europe/Moscow",
    "eastern standard time": "America/New_York",
    "central standard time": "America/Chicago",
    "mountain standard time": "America/Denver",
    "pacific standard time": "America/Los_Angeles",
    "utc": "UTC", "coordinated universal time": "UTC",
}

WD = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")


# ------------------------------------------------------------------ időzónák
def _zone(name):
    if not name:
        return None
    n = name.strip().strip('"')
    if n.upper() in ("UTC", "GMT", "Z"):
        return UTC
    n = WIN_TZ.get(n.casefold(), n)
    m = re.search(r"([A-Za-z]+/[A-Za-z_]+(?:/[A-Za-z_]+)?)", n)     # pl. "/mozilla.org/.../Europe/Budapest"
    if m and ZoneInfo is not None:
        try:
            return ZoneInfo(m.group(1))
        except Exception:
            pass
    if ZoneInfo is not None:
        try:
            return ZoneInfo(n)
        except Exception:
            pass
    return None                          # ismeretlen: helyi (lebegő) időként kezeljük


def _local_tz():
    if ZoneInfo is not None:
        try:
            return ZoneInfo(TZ_NAME)
        except Exception:
            pass
    return None


def to_local(dt):
    """Időzónás datetime → helyi (naiv) datetime. A naiv (lebegő) időt nem bántjuk."""
    if dt.tzinfo is None:
        return dt
    lt = _local_tz()
    return (dt.astimezone(lt) if lt else dt.astimezone()).replace(tzinfo=None)


# ------------------------------------------------------------------ alacsony szint
def unfold(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out = []
    for ln in text.split("\n"):
        if ln[:1] in (" ", "\t") and out:
            out[-1] += ln[1:]
        elif ln.strip():
            out.append(ln)
    return out


def parse_line(ln):
    """'DTSTART;TZID=Europe/Budapest:20261118T090000' → ('DTSTART', {'TZID': ...}, '2026...')"""
    i, q = 0, False
    while i < len(ln):
        c = ln[i]
        if c == '"':
            q = not q
        elif c == ":" and not q:
            break
        i += 1
    head, value = ln[:i], ln[i + 1:]
    parts, cur, q = [], "", False
    for c in head:
        if c == '"':
            q = not q
        if c == ";" and not q:
            parts.append(cur)
            cur = ""
        else:
            cur += c
    parts.append(cur)
    name = parts[0].upper()
    if "." in name:                      # csoport-előtag (item1.X)
        name = name.split(".", 1)[1]
    params = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.upper()] = v.strip('"')
    return name, params, value


def unescape(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            out.append("\n" if n in "nN" else n)
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def escape(s):
    return (str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def parse_dt(value, params):
    """→ (date) egész napos, vagy (datetime, időzónás vagy naiv)."""
    v = value.strip()
    if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", v):
        return _dt.date(int(v[:4]), int(v[4:6]), int(v[6:8]))
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})?(Z?)", v)
    if not m:
        raise ValueError(v)
    y, mo, d, h, mi, s, z = m.groups()
    dt = _dt.datetime(int(y), int(mo), int(d), int(h), int(mi), int(s or 0))
    if z:
        return dt.replace(tzinfo=UTC)
    tz = _zone(params.get("TZID"))
    return dt.replace(tzinfo=tz) if tz else dt


def parse_duration(v):
    m = re.fullmatch(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", v.strip())
    if not m:
        return None
    sg, w, d, h, mi, s = m.groups()
    td = _dt.timedelta(weeks=int(w or 0), days=int(d or 0), hours=int(h or 0), minutes=int(mi or 0),
                       seconds=int(s or 0))
    return -td if sg == "-" else td


# ------------------------------------------------------------------ elemzés
def parse(text):
    """→ {"name": naptár neve, "events": [vevent dict]} – a vevent kulcsai: a tulajdonságok listái."""
    lines = unfold(text)
    events, stack, cal_name = [], [], ""
    cur = None
    for ln in lines:
        name, params, value = parse_line(ln)
        if name == "BEGIN":
            stack.append(value.upper())
            if value.upper() == "VEVENT":
                cur = {}
            continue
        if name == "END":
            if stack:
                top = stack.pop()
                if top == "VEVENT" and cur is not None:
                    events.append(cur)
                    cur = None
            continue
        if not stack:
            continue
        if stack[-1] == "VALARM" and name == "TRIGGER" and cur is not None and \
                params.get("RELATED", "START").upper() == "START":
            du = parse_duration(value) if not params.get("VALUE") else None
            if du is not None and du <= _dt.timedelta(0):
                cur.setdefault("_ALARMS", []).append(int(-du.total_seconds() // 60))
            continue
        if stack[-1] == "VCALENDAR" and name == "X-WR-CALNAME":
            cal_name = unescape(value)
        elif stack[-1] == "VEVENT" and cur is not None:
            cur.setdefault(name, []).append((params, value))
    return {"name": cal_name, "events": events}


def _first(ve, key, default=""):
    v = ve.get(key)
    return v[0] if v else (None if default is None else ({}, default))


def _text(ve, key):
    p, v = _first(ve, key)
    return unescape(v).strip()


def parse_rrule(s):
    r = {}
    for part in s.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            r[k.upper()] = v
    return r


# ------------------------------------------------------------------ ismétlődés kibontása
def _month_days(y, m, byday, bymonthday, default_day):
    last = calendar.monthrange(y, m)[1]
    days = None
    if bymonthday:
        s = set()
        for x in bymonthday:
            n = int(x)
            n = last + 1 + n if n < 0 else n
            if 1 <= n <= last:
                s.add(n)
        days = s
    if byday:
        s = set()
        for tok in byday:
            mt = re.fullmatch(r"([+-]?\d+)?(MO|TU|WE|TH|FR|SA|SU)", tok.strip().upper())
            if not mt:
                continue
            wd = WD.index(mt.group(2))
            cand = [d for d in range(1, last + 1) if _dt.date(y, m, d).weekday() == wd]
            if mt.group(1):
                n = int(mt.group(1))
                if 1 <= abs(n) <= len(cand):
                    s.add(cand[n - 1] if n > 0 else cand[n])
            else:
                s.update(cand)
        days = s if days is None else days & s
    if days is None:
        days = {default_day} if default_day <= last else set()
    return sorted(days)


def _setpos(lst, bysetpos):
    if not bysetpos:
        return lst
    out = []
    for x in bysetpos:
        n = int(x)
        if 1 <= abs(n) <= len(lst):
            out.append(lst[n - 1] if n > 0 else lst[n])
    return sorted(set(out))


def expand_dates(start, rule, win_end, max_n=5000):
    """Az RRULE szerinti kezdőnapok (date, a start-tal együtt), növekvő sorrendben, win_end-ig."""
    freq = rule.get("FREQ", "").upper()
    iv = max(1, int(rule.get("INTERVAL", "1") or 1))
    count = int(rule.get("COUNT", "0") or 0)
    until = None
    if rule.get("UNTIL"):
        try:
            u = parse_dt(rule["UNTIL"], {})
            until = u if isinstance(u, _dt.date) and not isinstance(u, _dt.datetime) else to_local(u).date()
        except ValueError:
            until = None
    byday = [x for x in rule.get("BYDAY", "").split(",") if x]
    bymd = [x for x in rule.get("BYMONTHDAY", "").split(",") if x]
    bymonth = [int(x) for x in rule.get("BYMONTH", "").split(",") if x.strip().lstrip("-").isdigit()]
    bysetpos = [x for x in rule.get("BYSETPOS", "").split(",") if x]
    out, n, guard = [], 0, 0
    stop = min(win_end, until) if until else win_end

    def emit(d):
        nonlocal n
        if d < start:
            return True
        if until and d > until:
            return False
        if count and n >= count:
            return False
        n += 1
        if d <= win_end:
            out.append(d)
        return True

    if freq == "DAILY":
        d = start
        while d <= stop and (not count or n < count) and guard < 200000:
            guard += 1
            ok = ((not bymonth or d.month in bymonth) and
                  (not byday or WD[d.weekday()] in [b[-2:].upper() for b in byday]) and
                  (not bymd or d.day in _month_days(d.year, d.month, [], bymd, d.day)))
            if ok and not emit(d):
                break
            d += _dt.timedelta(days=iv)
        return out
    if freq == "WEEKLY":
        wds = sorted({WD.index(b[-2:].upper()) for b in byday if b[-2:].upper() in WD}) or [start.weekday()]
        wk = start - _dt.timedelta(days=start.weekday())
        while wk <= stop and (not count or n < count) and guard < 50000:
            guard += 1
            for wd in wds:
                d = wk + _dt.timedelta(days=wd)
                if bymonth and d.month not in bymonth:
                    continue
                if not emit(d):
                    return out
            wk += _dt.timedelta(weeks=iv)
        return out
    if freq in ("MONTHLY", "YEARLY"):
        y, m = start.year, start.month
        while _dt.date(y, m, 1) <= stop and (not count or n < count) and guard < 20000:
            guard += 1
            months = [m] if freq == "MONTHLY" else (bymonth or [start.month])
            for mm in months:
                if freq == "MONTHLY" and bymonth and mm not in bymonth:
                    continue
                days = _month_days(y, mm, byday, bymd, start.day)
                for dd in _setpos(days, bysetpos):
                    if not emit(_dt.date(y, mm, dd)):
                        return out
            if freq == "MONTHLY":
                m += iv
                y += (m - 1) // 12
                m = (m - 1) % 12 + 1
            else:
                y += iv
        return out
    return [start] if start <= win_end else []


def _key(v):
    """Alkalom-azonosító összehasonlításhoz: egész napos → date, időpontos → helyi naiv datetime."""
    if isinstance(v, _dt.datetime):
        return to_local(v)
    return v


def _dates_list(ve, key):
    out = []
    for params, value in ve.get(key, []):
        for part in value.split(","):
            try:
                out.append(parse_dt(part, params))
            except ValueError:
                pass
    return out


def expand(vevents, win_start, win_end, cal_id="", color="#2980b9", reminders=(), cal_name=""):
    """VEVENT-ek → saját eseményformátumú, nem ismétlődő alkalmak a [win_start, win_end] ablakban."""
    overrides = {}                               # uid → {alkalom-kulcs: vevent}
    masters = []
    for ve in vevents:
        uid = _text(ve, "UID") or hashlib.md5(repr(sorted(ve.items())).encode()).hexdigest()
        if ve.get("RECURRENCE-ID"):
            p, v = ve["RECURRENCE-ID"][0]
            try:
                overrides.setdefault(uid, {})[_key(parse_dt(v, p))] = ve
            except ValueError:
                pass
            masters.append((uid, ve, True))
        else:
            masters.append((uid, ve, False))
    out = []
    for uid, ve, is_override in masters:
        if _text(ve, "STATUS").upper() == "CANCELLED":
            continue
        try:
            p, v = ve["DTSTART"][0]
            start = parse_dt(v, p)
        except (KeyError, ValueError, IndexError):
            continue
        all_day = not isinstance(start, _dt.datetime)
        end = None
        if ve.get("DTEND"):
            try:
                end = parse_dt(ve["DTEND"][0][1], ve["DTEND"][0][0])
            except ValueError:
                end = None
        elif ve.get("DURATION"):
            du = parse_duration(ve["DURATION"][0][1])
            end = start + du if du is not None else None
        if all_day:
            if isinstance(end, _dt.datetime):
                end = end.date()
            length = (end - start) if end and end > start else _dt.timedelta(days=1)
        else:
            if end is not None and not isinstance(end, _dt.datetime):
                end = _dt.datetime.combine(end, _dt.time(0, 0), tzinfo=start.tzinfo)
            if end is not None and (end.tzinfo is None) != (start.tzinfo is None):
                end = end.replace(tzinfo=start.tzinfo)
            length = (end - start) if end and end >= start else _dt.timedelta(0)
        # alkalmak (az eredeti időzónában számolva, utána helyire alakítva)
        if is_override or not ve.get("RRULE"):
            starts = [start]
        else:
            rule = parse_rrule(ve["RRULE"][0][1])
            sd = start if all_day else start.date()
            span = max(0, length.days) + 1
            dates = expand_dates(sd, rule, win_end + _dt.timedelta(days=1))
            dates = [d for d in dates if d >= win_start - _dt.timedelta(days=span)]
            starts = [d if all_day else _dt.datetime.combine(d, start.timetz().replace(tzinfo=None),
                                                             tzinfo=start.tzinfo) for d in dates]
            for rd in _dates_list(ve, "RDATE"):
                if isinstance(rd, _dt.datetime) == (not all_day):
                    starts.append(rd)
            ex = {_key(x) for x in _dates_list(ve, "EXDATE")}
            if all_day:
                ex |= {x.date() if isinstance(x, _dt.datetime) else x for x in ex}
            ov = set(overrides.get(uid, {}))
            starts = [s for s in starts if _key(s) not in ex and _key(s) not in ov]
        title = _text(ve, "SUMMARY") or "(névtelen)"
        loc, notes = _text(ve, "LOCATION"), _text(ve, "DESCRIPTION")
        for s in starts:
            if all_day:
                ds, de = s, s + length - _dt.timedelta(days=1)
                if de < win_start or ds > win_end:
                    continue
                e = {"all_day": True, "date": ds.isoformat(), "time": "",
                     "end_date": de.isoformat() if de > ds else "", "end_time": ""}
            else:
                ls = to_local(s)
                le = to_local(s + length) if length else None
                if (le or ls).date() < win_start or ls.date() > win_end:
                    continue
                e = {"all_day": False, "date": ls.date().isoformat(), "time": ls.strftime("%H:%M"),
                     "end_date": le.date().isoformat() if le and le.date() > ls.date() else "",
                     "end_time": le.strftime("%H:%M") if le and le > ls else ""}
            e.update({"id": f"ext:{cal_id}:{uid}:{e['date']}T{e['time']}", "kind": "event", "title": title,
                      "location": loc, "notes": notes, "color": color, "reminders": list(reminders),
                      "repeat": {"freq": "none", "interval": 1, "weekdays": [], "until": "", "count": 0},
                      "skip": [], "birth_year": 0, "readonly": True, "cal": cal_id, "cal_name": cal_name,
                      "uid": uid})
            out.append(e)
    return out


# ------------------------------------------------------------------ importálás saját eseménnyé
_FREQ_IN = {"DAILY": "daily", "WEEKLY": "weekly", "MONTHLY": "monthly", "YEARLY": "yearly"}


def to_native(ve, win_start, win_end):
    """Egy VEVENT → saját esemény(ek). Egyszerű szabálynál egy ismétlődő esemény lesz belőle,
    bonyolultnál (pl. „hónap 2. keddje”) az ablakba eső alkalmak külön-külön."""
    uid = _text(ve, "UID")
    rr = parse_rrule(ve["RRULE"][0][1]) if ve.get("RRULE") else {}
    simple = (not rr or (rr.get("FREQ", "").upper() in _FREQ_IN and
                         not ({"BYMONTHDAY", "BYMONTH", "BYSETPOS", "BYHOUR", "BYMINUTE", "BYYEARDAY",
                               "BYWEEKNO"} & set(rr)) and
                         (not rr.get("BYDAY") or (rr["FREQ"].upper() == "WEEKLY" and
                                                  all(re.fullmatch(r"(MO|TU|WE|TH|FR|SA|SU)", b.strip().upper())
                                                      for b in rr["BYDAY"].split(","))))) and
              not ve.get("RDATE"))
    if not simple:
        insts = expand([ve], win_start, win_end, cal_id="imp")
        res = []
        for e in insts:
            n = ev.new_event(**{k: e[k] for k in ("title", "all_day", "date", "time", "end_date", "end_time",
                                                     "location", "notes")})
            n["ics_uid"] = f"{uid}|{e['date']}"
            res.append(n)
        return res
    one = expand([dict(ve, RRULE=[])] if ve.get("RRULE") else [ve], _dt.date(1900, 1, 1),
                 _dt.date(9999, 1, 1), cal_id="imp")
    if not one:
        return []
    e = one[0]
    n = ev.new_event(**{k: e[k] for k in ("title", "all_day", "date", "time", "end_date", "end_time",
                                             "location", "notes")})
    n["ics_uid"] = uid
    if rr:
        until = ""
        if rr.get("UNTIL"):
            try:
                u = parse_dt(rr["UNTIL"], {})
                until = (u if not isinstance(u, _dt.datetime) else to_local(u).date()).isoformat()
            except ValueError:
                pass
        n["repeat"] = {"freq": _FREQ_IN[rr["FREQ"].upper()], "interval": int(rr.get("INTERVAL", 1) or 1),
                       "weekdays": [WD.index(b.strip().upper()) for b in rr.get("BYDAY", "").split(",") if b.strip()],
                       "until": until, "count": int(rr.get("COUNT", 0) or 0)}
        n["skip"] = sorted({(to_local(x).date() if isinstance(x, _dt.datetime) else x).isoformat()
                            for x in _dates_list(ve, "EXDATE")})
    if _text(ve, "X-ARRABONA-KIND") == "birthday":
        n["kind"] = "birthday"
        try:
            n["birth_year"] = int(_text(ve, "X-ARRABONA-BIRTH-YEAR") or 0)
        except ValueError:
            pass
    n["reminders"] = list(ve.get("_ALARMS", []))
    return [ev.normalize(n)]


# ------------------------------------------------------------------ írás
VTIMEZONE = """BEGIN:VTIMEZONE
TZID:Europe/Budapest
BEGIN:DAYLIGHT
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
TZNAME:CEST
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
TZNAME:CET
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE"""


def fold(line):
    """75 bájtos sorhossz (UTF-8 karakter közepén nem vágunk)."""
    b = line.encode("utf-8")
    if len(b) <= 75:
        return line
    out, cur, lim = [], b"", 75
    for ch in line:
        cb = ch.encode("utf-8")
        if len(cur) + len(cb) > lim:
            out.append(cur.decode("utf-8"))
            cur, lim = b"", 74
        cur += cb
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def _ymd(s):
    return s.replace("-", "")


def _stamp(s):
    try:
        t = _dt.datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        t = _dt.datetime(2026, 1, 1)
    return t.strftime("%Y%m%dT%H%M%S")


def _vevent_lines(e):
    L = ["BEGIN:VEVENT", f"UID:{e.get('ics_uid') or e['id']}@arrabona-naptar",
         f"DTSTAMP:{_stamp(e.get('modified', ''))}Z", f"SUMMARY:{escape(e['title'])}"]
    d0 = ev._d(e["date"])
    if e.get("all_day"):
        ed = ev._d(e.get("end_date")) or d0
        L.append(f"DTSTART;VALUE=DATE:{d0.strftime('%Y%m%d')}")
        L.append(f"DTEND;VALUE=DATE:{(max(ed, d0) + _dt.timedelta(days=1)).strftime('%Y%m%d')}")
    else:
        t0 = ev._t(e["time"]) or _dt.time(9, 0)
        s = _dt.datetime.combine(d0, t0)
        ed = ev._d(e.get("end_date")) or d0
        te = ev._t(e.get("end_time"))
        en = _dt.datetime.combine(ed, te) if te else s + _dt.timedelta(hours=1)
        if en <= s:
            en += _dt.timedelta(days=1)
        L.append(f"DTSTART;TZID={TZ_NAME}:{s.strftime('%Y%m%dT%H%M%S')}")
        L.append(f"DTEND;TZID={TZ_NAME}:{en.strftime('%Y%m%dT%H%M%S')}")
    r = e["repeat"]
    if r["freq"] != "none":
        rule = f"FREQ={r['freq'].upper()}"
        if r["interval"] > 1:
            rule += f";INTERVAL={r['interval']}"
        if r["freq"] == "weekly" and r["weekdays"]:
            rule += ";BYDAY=" + ",".join(WD[i] for i in r["weekdays"])
        if r["count"]:
            rule += f";COUNT={r['count']}"
        elif r["until"]:
            rule += f";UNTIL={_ymd(r['until'])}" if e.get("all_day") else \
                f";UNTIL={_ymd(r['until'])}T225959Z"
        L.append("RRULE:" + rule)
        if e.get("skip"):
            if e.get("all_day"):
                L.append("EXDATE;VALUE=DATE:" + ",".join(_ymd(s) for s in e["skip"]))
            else:
                L.append(f"EXDATE;TZID={TZ_NAME}:" + ",".join(_ymd(s) + "T" + (e["time"] or "09:00").replace(":", "")
                                                               + "00" for s in e["skip"]))
    if e.get("location"):
        L.append(f"LOCATION:{escape(e['location'])}")
    if e.get("notes"):
        L.append(f"DESCRIPTION:{escape(e['notes'])}")
    if e.get("kind") == "birthday":
        L.append("X-ARRABONA-KIND:birthday")
        if e.get("birth_year"):
            L.append(f"X-ARRABONA-BIRTH-YEAR:{e['birth_year']}")
    for m in e.get("reminders") or []:
        L += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{escape(e['title'])}",
              f"TRIGGER:-PT{m}M" if m else "TRIGGER:PT0M", "END:VALARM"]
    L.append("END:VEVENT")
    return L


def _shift_lines(day, t):
    sp = muszak.span(t) if t.get("kind", "work") == "work" else None
    s = en = None
    if sp:
        s = _dt.datetime.combine(day, _dt.time(0, 0)) + _dt.timedelta(minutes=sp[0])
        en = s + _dt.timedelta(minutes=sp[1])
    L = ["BEGIN:VEVENT", f"UID:shift-{day.isoformat()}@arrabona-naptar", "DTSTAMP:20260101T000000Z",
         f"SUMMARY:{escape(t['code'] + ' – ' + t['name'])}", "CATEGORIES:Műszak", "TRANSP:TRANSPARENT"]
    if s and en and en > s:
        L.append(f"DTSTART;TZID={TZ_NAME}:{s.strftime('%Y%m%dT%H%M%S')}")
        L.append(f"DTEND;TZID={TZ_NAME}:{en.strftime('%Y%m%dT%H%M%S')}")
    else:
        L.append(f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}")
        L.append(f"DTEND;VALUE=DATE:{(day + _dt.timedelta(days=1)).strftime('%Y%m%d')}")
    L.append("END:VEVENT")
    return L


def export(events, name="Arrabona Naptár", shifts=None, shift_types=None, birthdays=True):
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Arrabona//Arrabona Naptar//HU", "CALSCALE:GREGORIAN",
         "METHOD:PUBLISH", f"X-WR-CALNAME:{escape(name)}", f"X-WR-TIMEZONE:{TZ_NAME}",
         "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H"]
    L += VTIMEZONE.split("\n")
    for e in events:
        if e.get("readonly") or (e.get("kind") == "birthday" and not birthdays):
            continue
        L += _vevent_lines(e)
    if shifts and shift_types:
        by = muszak.types_by_code(shift_types)
        for k in sorted(shifts):
            t = by.get(shifts[k])
            d = ev._d(k)
            if t and d and t.get("kind", "work") != "off":
                L += _shift_lines(d, t)
    L.append("END:VCALENDAR")
    return "\r\n".join(fold(x) for x in L) + "\r\n"


def import_text(text, win_start, win_end):
    """Egy .ics fájl tartalma → saját események listája (importáláshoz).
    A saját exportunkból visszaolvasott eseményeknél az eredeti azonosító megmarad (nincs duplikálás),
    a műszakokat kihagyjuk (azok a Műszak-táblában vannak)."""
    cal = parse(text)
    over = {}
    for ve in cal["events"]:
        if ve.get("RECURRENCE-ID"):
            p, v = ve["RECURRENCE-ID"][0]
            try:
                k = _key(parse_dt(v, p))
                over.setdefault(_text(ve, "UID"), set()).add(k if not isinstance(k, _dt.datetime) else k.date())
            except ValueError:
                pass
    out = []
    for ve in cal["events"]:
        uid = _text(ve, "UID")
        if uid.startswith("shift-") and uid.endswith("@arrabona-naptar"):
            continue
        if _text(ve, "STATUS").upper() == "CANCELLED":
            continue
        for n in to_native(ve, win_start, win_end):
            if n["repeat"]["freq"] != "none" and uid in over:
                n["skip"] = sorted(set(n["skip"]) | {d.isoformat() for d in over[uid]})
            if ve.get("RECURRENCE-ID"):
                n["ics_uid"] = f"{uid}|{n['date']}"
            if uid.endswith("@arrabona-naptar") and n.get("ics_uid") == uid:
                n["id"] = uid[:-len("@arrabona-naptar")]
                n.pop("ics_uid", None)
            out.append(n)
    return out
