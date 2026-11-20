# -*- coding: utf-8 -*-
"""[v1.5.0] Arrabona Naptár Mobil – adatcsere a telefonos alkalmazással (docs/ mappa, GitHub Pages).

PC → telefon:  ArrabonaNaptar_mobil.json   (a közzétételi mappába, pl. Dropbox\\Naptár)
    Minden, ami a telefonos nézethez kell, előre kiszámolva (−1 / +1 év):
    napok (ünnep, áthelyezés, jeles nap, névnapok), események alkalmai (ismétlődés kibontva,
    külső naptárak is), műszakok és típusaik, teendők, szabadságkeret, figyelt nevek, település.
    Így a telefonnak nem kell ünnepet, névnapot vagy ismétlődést számolnia – pontosan ugyanaz látszik.

Telefon → PC:  ArrabonaNaptar_telefon.json
    A telefonon végzett változások műveletlistája. Minden művelet ismételhető (idempotens), így ha
    ugyanaz a fájl kétszer érkezik, nem lesz duplikáció. A feldolgozott műveletek azonosítóit a
    következő mobil fájl „applied” listája visszaküldi; a telefon ezeket törli a saját listájából.

Műveletek:
    event_put   {"event": {...}}         új vagy módosított, NEM ismétlődő saját esemény
    event_del   {"event_id"}             nem ismétlődő saját esemény törlése
    event_skip  {"event_id", "day"}      ismétlődő esemény egy alkalmának törlése
    todo_put    {"todo": {...}}          teendő felvétele / módosítása (kész állapottal együtt)
    todo_del    {"todo_id"}
    shift       {"day", "code"}          műszak beírása ("" = törlés)
Ütközés: ha a gépen az elem a telefonos módosítás UTÁN változott, a gépi változat marad.
"""
import datetime as _dt
import json
import os

from . import VERSION
from . import esemenyek as ev
from . import muszak, nevnapok, szabadsag, unnepek

MOBILE_NAME = "ArrabonaNaptar_mobil.json"
PHONE_NAME = "ArrabonaNaptar_telefon.json"
FORMAT = "arrabona-naptar-mobil"
PHONE_FORMAT = "arrabona-naptar-telefon"
KEEP_APPLIED = 1000
MAX_INSTANCES = 20000


def _range(today):
    return _dt.date(today.year - 1, 1, 1), _dt.date(today.year + 1, 12, 31)


def build(store, ext_events, settings, today=None):
    """A telefonnak szóló adat (dict) – a 'generated' mező nélkül (azt íráskor tesszük bele)."""
    today = today or _dt.date.today()
    start, end = _range(today)
    swaps = store.swaps()
    days = {}
    d = start
    while d <= end:
        i = unnepek.day_info(d, swaps)
        x = {"n": nevnapok.names_for(d)}
        ex = nevnapok.extra_names_for(d)
        if ex:
            x["x"] = ex
        if i["holiday"]:
            x["h"] = i["holiday"]
        if i["red"]:
            x["r"] = 1
        if i["off"]:
            x["o"] = 1
        if i["workday_sat"]:
            x["w"] = 1
        if i["swap_note"]:
            x["s"] = i["swap_note"]
        if i["jeles"]:
            x["j"] = list(i["jeles"])
        days[d.isoformat()] = x
        d += _dt.timedelta(days=1)

    inst = []
    for occ, e in ev.instances(store.events + list(ext_events), start, end):
        first, last = ev._d(e.get("date")), ev._d(e.get("end_date"))
        span = (last - first).days if first and last and last > first else 0
        rec = e["repeat"]["freq"] != "none"
        o = {"id": e["id"], "occ": occ.isoformat(), "title": ev.display_title(e, occ),
             "all_day": bool(e.get("all_day")), "time": e.get("time") or "", "end_time": e.get("end_time") or "",
             "span": span, "color": e.get("color") or "", "location": e.get("location") or "",
             "notes": (e.get("notes") or "")[:2000], "kind": e.get("kind", "event")}
        if rec:
            o["rec"] = 1
        if e.get("readonly"):
            o["ro"] = 1
            o["cal"] = e.get("cal_name") or "külső naptár"
        if e.get("kind") == "birthday":
            o["ro"] = 1
            o["cal"] = "születésnap (a gépen szerkeszthető)"
        if not rec and not e.get("readonly") and e.get("kind") != "birthday":
            o["date"] = e["date"]
            o["end_date"] = e.get("end_date") or ""
            o["modified"] = e.get("modified", "")
        inst.append(o)
        if len(inst) >= MAX_INSTANCES:
            break

    types = []
    for t in store.shift_types:
        types.append({"code": t["code"], "name": t["name"], "start": t.get("start", ""), "end": t.get("end", ""),
                      "hours": muszak.hours_of(t), "kind": t["kind"], "color": t["color"],
                      "counts_leave": bool(t.get("counts_leave"))})
    lo, hi = start.isoformat(), end.isoformat()
    shifts = {k: v for k, v in store.shifts.items() if lo <= k <= hi}

    leave = {}
    for y in range(start.year, end.year + 1):
        total, parts = szabadsag.entitlement(store.data.get("leave"), y)
        leave[str(y)] = {"total": total, "configured": bool((store.data.get("leave") or {}).get("birth_year")
                                                            or ((store.data.get("leave") or {}).get("years") or {}))}
    place = settings.get("weather_place") or {}
    return {
        "format": FORMAT, "version": 1, "app_version": VERSION,
        "range": [lo, hi], "days": days, "instances": inst,
        "shift_types": types, "shifts": shifts,
        "todos": [{k: t.get(k, "") for k in ("id", "title", "due", "notes", "done", "done_at", "modified")}
                  for t in store.todos],
        "leave": leave,
        "watched": sorted({w["name"] for w in store.watched}),
        "weather": {"enabled": bool(settings.get("weather_enabled", True)), "name": place.get("name", "Győr"),
                    "lat": place.get("lat", 47.6875), "lon": place.get("lon", 17.6504)},
        "palette": list(ev.COLORS),
        "applied": list(store.data.get("mobile_applied") or [])[-KEEP_APPLIED:],
    }


def write(folder, data, last_body=None):
    """Kiírás, ha a tartalom változott. Visszaad: (útvonal, a tartalom 'generated' nélkül)."""
    body = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    path = os.path.join(folder, MOBILE_NAME)
    if body == last_body and os.path.exists(path):
        return path, body
    full = dict(data)
    full["generated"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(full, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
    return path, body


# ---------------------------------------------------------------- telefonos változások
class PhoneError(Exception):
    pass


def read_phone(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            d = json.load(f)
    except (OSError, ValueError) as ex:
        raise PhoneError(f"A telefonos fájl nem olvasható: {ex}")
    if not isinstance(d, dict) or d.get("format") != PHONE_FORMAT or not isinstance(d.get("ops"), list):
        raise PhoneError("Ez nem az Arrabona Naptár Mobil változásfájlja.")
    return d


def _clean_event(src, base=None):
    e = dict(base) if base else ev.new_event()
    for k in ("title", "date", "time", "end_date", "end_time", "location", "notes", "color"):
        if k in src:
            e[k] = str(src.get(k) or "")[:2000 if k == "notes" else 300]
    e["all_day"] = bool(src.get("all_day"))
    if e["all_day"]:
        e["time"] = e["end_time"] = ""
    if not ev._d(e["date"]):
        raise ValueError("dátum")
    if e.get("end_date") and (not ev._d(e["end_date"]) or e["end_date"] < e["date"]):
        e["end_date"] = ""
    for k in ("time", "end_time"):
        if e.get(k) and not ev._t(e[k]):
            e[k] = ""
    e["title"] = (e.get("title") or "").strip() or "(névtelen)"
    return e


def apply_ops(store, ops, settings=None):
    """A telefonos műveletek alkalmazása. Visszaad: statisztika dict. A store-t a végén menti."""
    settings = settings or {}
    applied = store.data.setdefault("mobile_applied", [])
    done = set(applied)
    st = {"events": 0, "todos": 0, "shifts": 0, "skipped": 0, "conflicts": 0}
    for op in ops:
        if not isinstance(op, dict) or not op.get("id"):
            continue
        oid = str(op["id"])[:64]
        if oid in done:
            continue
        ts = str(op.get("ts") or "")
        kind = op.get("op")
        try:
            if kind == "event_put":
                src = op.get("event") or {}
                cur = store.get(src.get("id")) if src.get("id") else None
                if cur is not None and (cur["repeat"]["freq"] != "none" or cur.get("kind") == "birthday"):
                    st["skipped"] += 1
                elif cur is not None and str(cur.get("modified", "")) > ts:
                    st["conflicts"] += 1
                else:
                    e = _clean_event(src, cur)
                    if cur is None:
                        if src.get("id"):
                            e["id"] = str(src["id"])[:40]
                        e["reminders"] = list(settings.get("default_reminders") or [15]) if not e["all_day"] else [0]
                    store.upsert(e)
                    st["events"] += 1
            elif kind == "event_del":
                cur = store.get(op.get("event_id"))
                if cur is None:
                    pass
                elif cur["repeat"]["freq"] != "none" or str(cur.get("modified", "")) > ts:
                    st["conflicts"] += 1
                else:
                    store.delete(cur["id"])
                    st["events"] += 1
            elif kind == "event_skip":
                cur, day = store.get(op.get("event_id")), ev._d(op.get("day"))
                if cur is not None and day:
                    store.skip_occurrence(cur["id"], day)
                    st["events"] += 1
            elif kind == "todo_put":
                src = op.get("todo") or {}
                cur = store.todo(src.get("id")) if src.get("id") else None
                if cur is not None and str(cur.get("modified", "")) > ts:
                    st["conflicts"] += 1
                else:
                    due = src.get("due") or ""
                    if due and not ev._d(due):
                        due = ""
                    t = store.upsert_todo(str(src.get("title") or "(névtelen)"), due, str(src.get("notes") or ""),
                                          tid=cur["id"] if cur else None)
                    if cur is None and src.get("id"):
                        t["id"] = str(src["id"])[:40]
                    want = bool(src.get("done"))
                    if t["done"] != want:
                        store.toggle_todo(t["id"])
                    st["todos"] += 1
            elif kind == "todo_del":
                cur = store.todo(op.get("todo_id"))
                if cur is not None:
                    if str(cur.get("modified", "")) > ts:
                        st["conflicts"] += 1
                    else:
                        store.delete_todo(cur["id"])
                        st["todos"] += 1
            elif kind == "shift":
                day = ev._d(op.get("day"))
                code = str(op.get("code") or "")
                if day and (not code or code in muszak.types_by_code(store.shift_types)):
                    store.set_shift(day, code, save=False)
                    st["shifts"] += 1
                else:
                    st["skipped"] += 1
            else:
                st["skipped"] += 1
        except (ValueError, KeyError, TypeError):
            st["skipped"] += 1
        applied.append(oid)
        done.add(oid)
    del applied[:-KEEP_APPLIED]
    store.save()
    return st
