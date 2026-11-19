# -*- coding: utf-8 -*-
"""[v1.4.0] Időjárás az Open-Meteo ingyenes, kulcs nélküli szolgáltatásából (open-meteo.com).

- 16 napos napi előrejelzés (ikon, min/max, csapadék, szél, napkelte/napnyugta)
- aktuális állapot és a következő órák
- településkereső (Open-Meteo geocoding)
Az utolsó sikeres letöltés a %APPDATA%\\ArrabonaNaptar\\idojaras.json fájlba kerül, így internet
nélkül is látszik (a korát kiírjuk).
"""
import datetime as _dt
import json
import os
import urllib.parse
import urllib.request

from .common import data_dir

UA = "ArrabonaNaptar/1.4 (+https://github.com/Lokypapa/arrabona-naptar)"
REFRESH_MIN = 30
DEFAULT_PLACE = {"name": "Győr", "lat": 47.6875, "lon": 17.6504}

# WMO időjárás-kódok → (ikon, magyar leírás)
WMO = {
    0: ("☀", "Derült"), 1: ("🌤", "Többnyire derült"), 2: ("⛅", "Gyengén felhős"), 3: ("☁", "Borult"),
    45: ("🌫", "Köd"), 48: ("🌫", "Zúzmarás köd"),
    51: ("🌦", "Gyenge szitálás"), 53: ("🌦", "Szitálás"), 55: ("🌧", "Erős szitálás"),
    56: ("🌧", "Ónos szitálás"), 57: ("🌧", "Erős ónos szitálás"),
    61: ("🌦", "Gyenge eső"), 63: ("🌧", "Eső"), 65: ("🌧", "Erős eső"),
    66: ("🌧", "Ónos eső"), 67: ("🌧", "Erős ónos eső"),
    71: ("🌨", "Gyenge havazás"), 73: ("🌨", "Havazás"), 75: ("❄", "Erős havazás"), 77: ("🌨", "Hószemcse"),
    80: ("🌦", "Gyenge zápor"), 81: ("🌧", "Zápor"), 82: ("🌧", "Heves zápor"),
    85: ("🌨", "Hózápor"), 86: ("❄", "Erős hózápor"),
    95: ("⛈", "Zivatar"), 96: ("⛈", "Zivatar jégesővel"), 99: ("⛈", "Erős zivatar jégesővel"),
}


def describe(code):
    try:
        return WMO.get(int(code), ("·", "–"))
    except (TypeError, ValueError):
        return ("·", "–")


def cache_path():
    return os.path.join(data_dir(), "idojaras.json")


def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def forecast_url(lat, lon):
    q = {
        "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}",
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,is_day",
        "hourly": "temperature_2m,weather_code,precipitation_probability",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                 "precipitation_sum,wind_speed_10m_max,sunrise,sunset",
        "timezone": "Europe/Budapest", "forecast_days": "16", "wind_speed_unit": "kmh",
    }
    return "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q, safe=",")


def fetch(lat, lon):
    """Letöltés + átalakítás. Hibánál magyar üzenetű RuntimeError."""
    try:
        d = _get_json(forecast_url(lat, lon))
    except Exception as ex:
        raise RuntimeError(f"Az időjárás nem tölthető le (nincs internet?): {getattr(ex, 'reason', ex)}")
    if d.get("error"):
        raise RuntimeError(f"Időjárás-szolgáltatás hiba: {d.get('reason')}")
    return convert(d)


def convert(d):
    out = {"fetched": _dt.datetime.now().strftime("%Y-%m-%dT%H:%M"), "current": {}, "daily": {}, "hourly": []}
    c = d.get("current") or {}
    if c:
        out["current"] = {"time": c.get("time", ""), "temp": c.get("temperature_2m"),
                          "feels": c.get("apparent_temperature"), "hum": c.get("relative_humidity_2m"),
                          "code": c.get("weather_code"), "wind": c.get("wind_speed_10m"), "is_day": c.get("is_day", 1)}
    dl = d.get("daily") or {}
    for i, day in enumerate(dl.get("time") or []):
        def g(k):
            v = dl.get(k) or []
            return v[i] if i < len(v) else None
        out["daily"][day] = {"code": g("weather_code"), "tmax": g("temperature_2m_max"), "tmin": g("temperature_2m_min"),
                             "pp": g("precipitation_probability_max"), "psum": g("precipitation_sum"),
                             "wind": g("wind_speed_10m_max"), "sunrise": (g("sunrise") or "")[11:16],
                             "sunset": (g("sunset") or "")[11:16]}
    hl = d.get("hourly") or {}
    for i, t in enumerate(hl.get("time") or []):
        def h(k):
            v = hl.get(k) or []
            return v[i] if i < len(v) else None
        out["hourly"].append({"time": t, "temp": h("temperature_2m"), "code": h("weather_code"),
                              "pp": h("precipitation_probability")})
    return out


def geocode(name):
    """Településkereső → [{"name", "region", "country", "lat", "lon"}]."""
    q = urllib.parse.urlencode({"name": name.strip(), "count": "8", "language": "hu", "format": "json"})
    try:
        d = _get_json("https://geocoding-api.open-meteo.com/v1/search?" + q)
    except Exception as ex:
        raise RuntimeError(f"A keresés nem sikerült (nincs internet?): {getattr(ex, 'reason', ex)}")
    res = []
    for r in d.get("results") or []:
        res.append({"name": r.get("name", ""), "region": r.get("admin1", "") or "",
                    "country": r.get("country", "") or "", "lat": float(r["latitude"]), "lon": float(r["longitude"])})
    return res


def load_cache():
    try:
        with open(cache_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_cache(data):
    p = cache_path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, p)


def age_minutes(data, now=None):
    try:
        t = _dt.datetime.fromisoformat(data["fetched"])
    except (KeyError, TypeError, ValueError):
        return None
    return int(((now or _dt.datetime.now()) - t).total_seconds() // 60)


def fmt_t(v):
    if v is None:
        return "–"
    r = round(float(v))
    return f"{'−' if r < 0 else ''}{abs(r)}°"


def next_hours(data, now=None, n=6, step=3):
    """A következő órák (step óránként) a mostani óra után: [(óra "18", temp, code, pp)]."""
    now = now or _dt.datetime.now()
    key = now.strftime("%Y-%m-%dT%H:00")
    hs = data.get("hourly") or []
    idx = next((i for i, h in enumerate(hs) if h["time"] >= key), None)
    if idx is None:
        return []
    out = []
    for i in range(idx + step, len(hs), step):
        h = hs[i]
        out.append((h["time"][11:13], h["temp"], h["code"], h["pp"]))
        if len(out) >= n:
            break
    return out
