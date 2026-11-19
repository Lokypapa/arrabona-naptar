# -*- coding: utf-8 -*-
"""[v1.4.0] Szabadság-nyilvántartás (Mt. 116–118. §).

Évi keret = 20 nap alapszabadság
          + életkor szerinti pótszabadság (attól az évtől, amelyben az életkort eléri):
              25: 1, 28: 2, 31: 3, 33: 4, 35: 5, 37: 6, 39: 7, 41: 8, 43: 9, 45: 10
          + 16 évesnél fiatalabb gyermek után: 1 → 2, 2 → 4, 2-nél több → összesen 7 nap,
            fogyatékos gyermekenként +2 nap
          + egyéb pótszabadság (kézzel) + előző évről áthozott napok
A „kézi keret” megadásával a számítás felülírható (pl. munkáltató szerinti, időarányos keret).

Kivett / tervezett napok: a műszakbeosztásban azok a napok, amelyek műszaktípusa „szabadságnak
számít” (alapból az SZ – Szabadság). A mai napig kivettnek, utána tervezettnek számít.
Beállítások: store.data["leave"] = {"birth_year": 1985, "years": {"2026": {...}}}
"""
import datetime as _dt

AGE_STEPS = ((45, 10), (43, 9), (41, 8), (39, 7), (37, 6), (35, 5), (33, 4), (31, 3), (28, 2), (25, 1))
YEAR_KEYS = ("children", "disabled", "extra", "carried", "manual")


def age_extra(year, birth_year):
    if not birth_year:
        return 0
    age = year - int(birth_year)
    return next((n for a, n in AGE_STEPS if age >= a), 0)


def child_extra(children, disabled=0):
    c = max(0, int(children or 0))
    base = 0 if c == 0 else (2 if c == 1 else 4 if c == 2 else 7)
    return base + 2 * max(0, min(int(disabled or 0), c))


def year_cfg(leave, year):
    """Az év beállításai; ha az évhez még nincs, az utolsó korábbi év gyerekszáma öröklődik."""
    years = (leave or {}).get("years") or {}
    cfg = dict(years.get(str(year)) or {})
    if not cfg:
        prev = sorted((int(k) for k in years if k.isdigit() and int(k) < year), reverse=True)
        if prev:
            p = years[str(prev[0])]
            cfg = {"children": p.get("children", 0), "disabled": p.get("disabled", 0), "extra": p.get("extra", 0)}
    for k in YEAR_KEYS:
        cfg.setdefault(k, 0 if k != "manual" else None)
    return cfg


def entitlement(leave, year):
    cfg = year_cfg(leave, year)
    by = (leave or {}).get("birth_year") or 0
    parts = {"base": 20, "age": age_extra(year, by), "children": child_extra(cfg["children"], cfg["disabled"]),
             "extra": int(cfg.get("extra") or 0), "carried": int(cfg.get("carried") or 0)}
    total = sum(parts.values())
    if cfg.get("manual") not in (None, "", 0):
        total = int(cfg["manual"]) + parts["carried"]
        parts["manual"] = int(cfg["manual"])
    return total, parts


def leave_codes(types):
    return {t["code"] for t in types if t.get("counts_leave")}


def usage(shifts, types, year, today=None):
    today = today or _dt.date.today()
    codes = leave_codes(types)
    taken, planned = [], []
    pre = f"{year}-"
    for k, c in shifts.items():
        if k.startswith(pre) and c in codes:
            try:
                d = _dt.date.fromisoformat(k)
            except ValueError:
                continue
            (taken if d <= today else planned).append(d)
    return sorted(taken), sorted(planned)


def summary(leave, shifts, types, year, today=None):
    today = today or _dt.date.today()
    total, parts = entitlement(leave, year)
    taken, planned = usage(shifts, types, year, today)
    remaining = total - len(taken) - len(planned)
    warn = ""
    if remaining < 0:
        warn = f"Túllépted a keretet {-remaining} nappal."
    elif today.year == year and today.month >= 10 and remaining > 0:
        warn = f"Év végéig még {remaining} nap szabadság beosztatlan."
    return {"year": year, "total": total, "parts": parts, "taken": taken, "planned": planned,
            "remaining": remaining, "warn": warn, "configured": bool((leave or {}).get("birth_year")
                                                                     or ((leave or {}).get("years") or {}))}
