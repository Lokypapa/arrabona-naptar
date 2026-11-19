# -*- coding: utf-8 -*-
"""[v1.4.0] Arrabona Naptár - ONFRISSITES (a Pass-ból átvéve) GitHub Release-bol (ugyanugy, mint a Guardnal).

  1. Indulas utan 1 perccel, majd 6 orankent lekerdezi a legujabb kiadast:
       https://api.github.com/repos/<GITHUB_REPO>/releases/latest
  2. Ha ujabb a futonal: savot mutat az ablakban (soha nem telepit magatol).
  3. Telepiteskor letolti az ArrabonaNaptar_Setup_<ver>.exe-t es a SHA256SUMS.txt-t,
     ELLENORZI az ellenorzoosszeget (ha nem egyezik: NEM telepit), elinditja a
     telepitot csendes modban, es kilep. A telepito a vegen ujrainditja a Naptart.

Az adatokat (%APPDATA%\\ArrabonaNaptar) a frissites nem erinti.
"""
import hashlib
import json
import os
import re
import sys
import urllib.request

from . import APP_NAME, VERSION
from .common import data_dir

GITHUB_REPO = "Lokypapa/arrabona-naptar"
FIRST_CHECK_MS = 60 * 1000
CHECK_MS = 6 * 3600 * 1000
MAX_SETUP_MB = 200
_UA = f"ArrabonaNaptar-Updater/{VERSION}"
_SETUP_RE = re.compile(r"setup.*\.exe$", re.I)
_SUMS_RE = re.compile(r"^sha256sums(\.txt)?$", re.I)


def upd_dir():
    d = os.path.join(os.environ.get("TEMP") or data_dir(), "ArrabonaNaptar_frissites")
    os.makedirs(d, exist_ok=True)
    return d


def ver_tuple(v):
    m = re.match(r"^\s*v?(\d+(?:\.\d+){0,3})", str(v or ""))
    if not m:
        return ()
    t = [int(x) for x in m.group(1).split(".")]
    while len(t) < 3:
        t.append(0)
    return tuple(t)


def newer(other, mine=VERSION):
    a, b = ver_tuple(other), ver_tuple(mine)
    return bool(a) and bool(b) and a > b


def _get(url, timeout=20, accept="application/vnd.github+json"):
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": accept})
    return urllib.request.urlopen(req, timeout=timeout)


def check():
    """Visszaad: (info_vagy_None, szoveg). info: dict(ver, tag, url, setup=(nev,url,meret), sums, notes)"""
    try:
        with _get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest") as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        msg = str(e)
        if "404" in msg:
            msg = "még nincs kiadott verzió a GitHubon"
        return None, f"Nem sikerült lekérdezni: {msg}"
    if d.get("draft") or d.get("prerelease"):
        return None, "A legújabb kiadás még teszt (pre-release)."
    tag = str(d.get("tag_name") or "")
    setup = sums = None
    for a in d.get("assets") or []:
        name = str(a.get("name") or "")
        dl = a.get("browser_download_url") or ""
        if not dl.startswith("https://"):
            continue
        if _SETUP_RE.search(name) and "naptar" in name.lower():
            setup = (name, dl, int(a.get("size") or 0))
        elif _SUMS_RE.match(name):
            sums = dl
    if not newer(tag):
        return None, f"A legfrissebb verzió fut: v{VERSION}"
    if not (setup and sums):
        return None, f"A {tag} kiadásból hiányzik a telepítő vagy a SHA256SUMS.txt."
    info = {"ver": ".".join(str(x) for x in ver_tuple(tag)), "tag": tag,
            "url": d.get("html_url") or "", "setup": setup, "sums": sums,
            "notes": str(d.get("body") or "")[:1500]}
    return info, f"Új verzió érhető el: v{info['ver']} (most: v{VERSION})"


def download_and_verify(info, progress=None):
    """Visszaad: a letoltott, ELLENORZOTT telepito utvonala. Hiba: RuntimeError."""
    name, url, size = info["setup"]
    name = os.path.basename(name)
    d = upd_dir()
    for old in os.listdir(d):
        try:
            os.remove(os.path.join(d, old))
        except OSError:
            pass
    with _get(info["sums"], accept="application/octet-stream") as r:
        sums = r.read(64 * 1024).decode("utf-8", "replace")
    expected = None
    for ln in sums.splitlines():
        m = re.match(r"^\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*$", ln)
        if m and os.path.basename(m.group(2)).lower() == name.lower():
            expected = m.group(1).lower()
            break
    if not expected:
        raise RuntimeError(f"A SHA256SUMS.txt-ben nincs bejegyzés ehhez: {name}")
    target = os.path.join(d, name)
    h = hashlib.sha256()
    n = 0
    with _get(url, timeout=120, accept="application/octet-stream") as r, open(target, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            n += len(chunk)
            if n > MAX_SETUP_MB * 1024 * 1024:
                raise RuntimeError("Túl nagy fájl – nem telepítem.")
            f.write(chunk)
            h.update(chunk)
            if progress and total:
                progress(n * 100 // total)
    if size and n != size:
        os.remove(target)
        raise RuntimeError(f"Hiányos letöltés ({n} / {size} bájt).")
    if h.hexdigest().lower() != expected:
        os.remove(target)
        raise RuntimeError("Az ellenőrzőösszeg NEM egyezik – a fájl sérült vagy módosított, "
                           "nem telepítem.")
    return target


def launch_installer(path):
    """Csendes telepites. A telepito maga ker UAC-engedelyt, es igy a vegen a Naptart
    a sajat (nem rendszergazdai) jogoddal inditja ujra. Utana a hivo azonnal lepjen ki."""
    import ctypes
    for k in list(os.environ):   # PyInstaller-kornyezet ne oroklodjon
        if k.upper().startswith(("_MEI", "_PYI")):
            os.environ.pop(k, None)
    os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    params = '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG="%s"' % os.path.join(
        os.path.dirname(path), "telepites_naplo.txt")
    se = ctypes.windll.shell32.ShellExecuteW
    se.restype = ctypes.c_void_p
    r = se(None, "open", path, params, os.path.dirname(path), 0) or 0
    if r <= 32:
        raise RuntimeError("A telepítő nem indult el (a UAC-kérdést elutasítottad?).")


def can_self_update():
    """Csak a telepitett exe tud frissulni (forrasbol futtatva nem)."""
    return sys.platform == "win32" and getattr(sys, "frozen", False)
