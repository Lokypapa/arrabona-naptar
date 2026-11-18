# -*- coding: utf-8 -*-
"""Magyar ünnepek, munkaszüneti napok, áthelyezett munkanapok és jeles napok.

Munkaszüneti napok (Mt. 102. §): január 1., március 15., nagypéntek (2017-től), húsvéthétfő,
május 1., pünkösdhétfő, augusztus 20., október 23., november 1., december 25-26., és
2026-tól december 24. is (az Országgyűlés 2026. november 3-i döntése; a 2026. december 12-i
szombati munkanap ezzel elmaradt).

Áthelyezett munkanapok: minden évre külön miniszteri rendelet szól. A beépített lista:
2024 (15/2023. GFM), 2025 (11/2024. NGM), 2026 (10/2025. NGM, a december 24-i módosítással).
Későbbi évekre a felhasználó a Beállításokban veheti fel (vagy a program frissítése hozza).
"""
import datetime as _dt

D = _dt.date

# ---------------------------------------------------------------- beépített munkarend
# év -> [(szombati munkanap, a helyette kapott pihenőnap), ...]
ATHELYEZESEK = {
    2024: [(D(2024, 8, 3), D(2024, 8, 19)), (D(2024, 12, 7), D(2024, 12, 24)),
           (D(2024, 12, 14), D(2024, 12, 27))],
    2025: [(D(2025, 5, 17), D(2025, 5, 2)), (D(2025, 10, 18), D(2025, 10, 24)),
           (D(2025, 12, 13), D(2025, 12, 24))],
    2026: [(D(2026, 1, 10), D(2026, 1, 2)), (D(2026, 8, 8), D(2026, 8, 21))],
}

HONAPOK = ["január", "február", "március", "április", "május", "június", "július",
           "augusztus", "szeptember", "október", "november", "december"]
NAPOK = ["hétfő", "kedd", "szerda", "csütörtök", "péntek", "szombat", "vasárnap"]
NAPOK_ROVID = ["H", "K", "Sze", "Cs", "P", "Szo", "V"]


def easter(y):
    """Húsvétvasárnap (Gergely-naptár, anonim/Meeus-algoritmus)."""
    a = y % 19
    b, c = divmod(y, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return D(y, month, day)


def _nth_weekday(y, m, weekday, n):
    """n. (1-től) adott napja a hónapnak; n=-1: az utolsó. weekday: 0=hétfő."""
    if n > 0:
        d = D(y, m, 1)
        d += _dt.timedelta(days=(weekday - d.weekday()) % 7)
        return d + _dt.timedelta(weeks=n - 1)
    nxt = D(y + (m == 12), m % 12 + 1, 1)
    d = nxt - _dt.timedelta(days=1)
    return d - _dt.timedelta(days=(d.weekday() - weekday) % 7)


# ---------------------------------------------------------------- évenkénti tábla
_cache = {}


def year_table(y, extra_swaps=None):
    """dátum -> {"holiday": név vagy None, "rest": bool (munkaszüneti/pihenőnap hétköznap is),
                "workday_sat": bool, "swap_note": str, "jeles": [nevek]}"""
    key = (y, tuple(sorted((a.isoformat(), b.isoformat()) for a, b in (extra_swaps or []))))
    if key in _cache:
        return _cache[key]
    t = {}

    def info(d):
        return t.setdefault(d, {"holiday": None, "rest": False, "workday_sat": False,
                                "swap_note": "", "jeles": []})

    def holiday(d, name, rest=True):
        i = info(d)
        i["holiday"] = name if not i["holiday"] else i["holiday"] + " · " + name
        i["rest"] = i["rest"] or rest

    def jeles(d, name):
        info(d)["jeles"].append(name)

    E = easter(y)
    td = _dt.timedelta
    # --- munkaszüneti napok
    holiday(D(y, 1, 1), "Újév")
    holiday(D(y, 3, 15), "Nemzeti ünnep (1848)")
    if y >= 2017:
        holiday(E - td(2), "Nagypéntek")
    holiday(E, "Húsvétvasárnap")
    holiday(E + td(1), "Húsvéthétfő")
    holiday(D(y, 5, 1), "A munka ünnepe")
    holiday(E + td(49), "Pünkösdvasárnap")
    holiday(E + td(50), "Pünkösdhétfő")
    holiday(D(y, 8, 20), "Államalapítás ünnepe (Szent István)")
    holiday(D(y, 10, 23), "Nemzeti ünnep (1956)")
    holiday(D(y, 11, 1), "Mindenszentek")
    if y >= 2026:
        holiday(D(y, 12, 24), "Szenteste")
    else:
        jeles(D(y, 12, 24), "Szenteste")
    holiday(D(y, 12, 25), "Karácsony")
    holiday(D(y, 12, 26), "Karácsony másnapja")

    # --- áthelyezett munkanapok
    for work, rest in list(ATHELYEZESEK.get(y, [])) + [s for s in (extra_swaps or []) if s[0].year == y]:
        w = info(work)
        w["workday_sat"] = True
        w["swap_note"] = f"Áthelyezett munkanap ({rest.month:02d}.{rest.day:02d}. helyett)"
        r = info(rest)
        r["rest"] = True
        r["swap_note"] = f"Áthelyezett pihenőnap (ledolgozás: {work.month:02d}.{work.day:02d}.)"

    # --- jeles napok, emléknapok (nem munkaszüneti)
    for (m, d_), name in (
            ((1, 6), "Vízkereszt"), ((1, 22), "A magyar kultúra napja"),
            ((2, 2), "Gyertyaszentelő Boldogasszony"), ((2, 14), "Valentin-nap"),
            ((2, 25), "A kommunista diktatúrák áldozatainak emléknapja"),
            ((3, 8), "Nemzetközi nőnap"), ((4, 11), "A költészet napja"),
            ((4, 16), "A holokauszt áldozatainak emléknapja"), ((4, 22), "A Föld napja"),
            ((5, 10), "Madarak és fák napja"), ((6, 4), "A nemzeti összetartozás napja"),
            ((10, 6), "Az aradi vértanúk emléknapja (nemzeti gyásznap)"),
            ((10, 31), "A reformáció emléknapja"), ((11, 2), "Halottak napja"),
            ((12, 6), "Mikulás"), ((12, 31), "Szilveszter")):
        jeles(D(y, m, d_), name)
    jeles(E - td(47), "Farsang farka (húshagyó kedd)")
    jeles(E - td(46), "Hamvazószerda")
    jeles(E - td(7), "Virágvasárnap")
    jeles(E - td(3), "Nagycsütörtök")
    jeles(E - td(1), "Nagyszombat")
    jeles(E + td(39), "Áldozócsütörtök (Mennybemenetel)")
    jeles(E + td(60), "Úrnapja")
    jeles(_nth_weekday(y, 5, 6, 1), "Anyák napja")
    jeles(_nth_weekday(y, 5, 6, -1), "Gyereknap")
    jeles(_nth_weekday(y, 6, 6, 1), "Pedagógusnap")
    jeles(_nth_weekday(y, 6, 6, 3), "Apák napja")
    d24 = D(y, 12, 24)
    adv1 = d24 - td(days=(d24.weekday() + 1) % 7) - td(weeks=3)   # advent 4. = utolsó vasárnap dec. 25. előtt
    for i in range(4):
        jeles(adv1 + td(weeks=i), f"Advent {i + 1}. vasárnapja")
    jeles(_nth_weekday(y, 3, 6, -1), "Óraátállítás: nyári időszámítás (2:00 → 3:00)")
    jeles(_nth_weekday(y, 10, 6, -1), "Óraátállítás: téli időszámítás (3:00 → 2:00)")
    _cache[key] = t
    return t


def day_info(day, extra_swaps=None):
    t = year_table(day.year, extra_swaps)
    i = t.get(day) or {"holiday": None, "rest": False, "workday_sat": False, "swap_note": "", "jeles": []}
    out = dict(i)
    out["jeles"] = list(i["jeles"])
    wd = day.weekday()
    # pihenőnap-e (munkarend szerint)
    if i["workday_sat"]:
        out["off"] = False
    else:
        out["off"] = bool(i["rest"]) or wd >= 5
    out["red"] = (bool(i["rest"]) and not i["workday_sat"]) or wd == 6
    return out


def iso_week(day):
    return day.isocalendar()[1]


def has_swaps(y, extra_swaps=None):
    return bool(ATHELYEZESEK.get(y)) or any(s[0].year == y for s in (extra_swaps or []))


def long_weekends(y, extra_swaps=None):
    """Legalább 3 napos pihenő-tömbök az évben: [(első nap, utolsó nap), ...]"""
    out, start, d = [], None, D(y, 1, 1)
    end = D(y, 12, 31)
    while d <= end + _dt.timedelta(days=1):
        off = d <= end and day_info(d, extra_swaps)["off"]
        if off and start is None:
            start = d
        elif not off and start is not None:
            if (d - start).days >= 3:
                last = d - _dt.timedelta(days=1)
                if any(day_info(x, extra_swaps)["holiday"] or day_info(x, extra_swaps)["swap_note"]
                       for x in (start + _dt.timedelta(days=k) for k in range((last - start).days + 1))):
                    out.append((start, last))
            start = None
        d += _dt.timedelta(days=1)
    return out


def workdays_in_month(y, m, extra_swaps=None):
    d, n = D(y, m, 1), 0
    while d.month == m:
        n += not day_info(d, extra_swaps)["off"]
        d += _dt.timedelta(days=1)
    return n
