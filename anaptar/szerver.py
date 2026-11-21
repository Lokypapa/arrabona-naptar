# -*- coding: utf-8 -*-
"""[v1.6.0] Szerveres szinkron (saját tárhely, pl. https://arrabonagaming.hu/naptar/).

A szerver (api.php) ugyanazt az adatcsomagot tárolja, amit a gép a Dropboxba is kiír
(mobil.build), és a telefonról érkező változásokat (műveleteket). A gép:
  1. letölti a még át nem vett műveleteket  (GET  api.php?a=ops)
  2. alkalmazza őket                        (mobil.apply_ops – idempotens)
  3. feltölti a friss adatcsomagot          (PUT  api.php?a=snapshot) – benne az „applied”
     lista, amiből a szerver tudja, mit vett át a gép.
A jelszót a program nem tárolja: bejelentkezéskor egy eszköz-tokent kap, csak azt menti.
"""
import json
import re
import urllib.error
import urllib.request

from . import VERSION

UA = f"ArrabonaNaptar/{VERSION} (Windows)"
TIMEOUT = 20


class ServerError(Exception):
    def __init__(self, msg, status=0):
        super().__init__(msg)
        self.status = status


def normalize_url(u):
    """'arrabonagaming.hu/naptar' → 'https://arrabonagaming.hu/naptar/'"""
    u = (u or "").strip()
    if not u:
        return ""
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    u = re.sub(r"(api|setup)\.php.*$", "", u)
    u = re.sub(r"index\.html?$", "", u)
    if not u.endswith("/"):
        u += "/"
    return u


def is_secure(u):
    return u.lower().startswith("https://") or bool(re.match(r"^http://(127\.0\.0\.1|localhost)[:/]", u, re.I))


def _call(base, action, method="GET", body=None, token=None, raw=None, timeout=TIMEOUT):
    if not is_secure(base):
        raise ServerError("Csak https:// címmel működik (titkosított kapcsolat).")
    url = base + "api.php?a=" + action
    headers = {"User-Agent": UA, "Accept": "application/json"}
    data = None
    if raw is not None:
        data = raw
        headers["Content-Type"] = "application/json"
    elif body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-Auth-Token"] = token
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as ex:
        txt = ex.read().decode("utf-8", "replace")
        status = ex.code
    except urllib.error.URLError as ex:
        raise ServerError(f"A szerver nem érhető el (nincs internet?): {getattr(ex, 'reason', ex)}")
    except OSError as ex:
        raise ServerError(f"Kapcsolódási hiba: {ex}")
    try:
        d = json.loads(txt) if txt else {}
    except ValueError:
        raise ServerError(f"A szerver nem az Arrabona Naptár API-t adta vissza (HTTP {status}). Jó a cím?", status)
    if status >= 400 or d.get("ok") is False:
        raise ServerError(d.get("error") or f"HTTP {status}", status)
    return d


def ping(base):
    d = _call(base, "ping")
    if d.get("app") != "arrabona-naptar-server":
        raise ServerError("Ezen a címen nem az Arrabona Naptár szervere fut.")
    return d


def login(base, username, password, device="PC – Arrabona Naptár"):
    ping(base)
    d = _call(base, "login", "POST", {"username": username, "password": password, "device": device})
    return d["token"], d.get("username", username)


def logout(base, token):
    try:
        _call(base, "logout", "POST", {}, token=token)
    except ServerError:
        pass


def get_ops(base, token):
    return _call(base, "ops", token=token).get("ops") or []


def put_snapshot(base, token, raw_bytes):
    return _call(base, "snapshot", "PUT", raw=raw_bytes, token=token, timeout=60)


def status(base, token):
    return _call(base, "status", token=token)
