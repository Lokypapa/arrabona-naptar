// Arrabona Naptár Mobil – a PC-s Arrabona Naptár telefonos párja (PWA, GitHub Pages).
// Adat: a gép által kiírt ArrabonaNaptar_mobil.json (Dropbox). A telefonos változások egy
// műveletlistába kerülnek, amit a „Küldés a gépre” ArrabonaNaptar_telefon.json néven ment a
// Dropboxba; a gépen futó Naptár átveszi. Az app az időjárás (open-meteo.com) és a megadott
// Dropbox-link letöltésén kívül semmilyen hálózati kapcsolatot nem használ.
"use strict";

const APP_VERSION = "1.0.1";
const FORMAT = "arrabona-naptar-mobil";
const PHONE_FORMAT = "arrabona-naptar-telefon";
const HONAP = ["január", "február", "március", "április", "május", "június", "július", "augusztus",
               "szeptember", "október", "november", "december"];
const NAP = ["hétfő", "kedd", "szerda", "csütörtök", "péntek", "szombat", "vasárnap"];
const NAP_R = ["H", "K", "Sze", "Cs", "P", "Szo", "V"];
const WMO = {
  0: ["☀", "Derült"], 1: ["🌤", "Többnyire derült"], 2: ["⛅", "Gyengén felhős"], 3: ["☁", "Borult"],
  45: ["🌫", "Köd"], 48: ["🌫", "Zúzmarás köd"], 51: ["🌦", "Gyenge szitálás"], 53: ["🌦", "Szitálás"],
  55: ["🌧", "Erős szitálás"], 56: ["🌧", "Ónos szitálás"], 57: ["🌧", "Erős ónos szitálás"],
  61: ["🌦", "Gyenge eső"], 63: ["🌧", "Eső"], 65: ["🌧", "Erős eső"], 66: ["🌧", "Ónos eső"], 67: ["🌧", "Erős ónos eső"],
  71: ["🌨", "Gyenge havazás"], 73: ["🌨", "Havazás"], 75: ["❄", "Erős havazás"], 77: ["🌨", "Hószemcse"],
  80: ["🌦", "Gyenge zápor"], 81: ["🌧", "Zápor"], 82: ["🌧", "Heves zápor"], 85: ["🌨", "Hózápor"],
  86: ["❄", "Erős hózápor"], 95: ["⛈", "Zivatar"], 96: ["⛈", "Zivatar jégesővel"], 99: ["⛈", "Erős zivatar jégesővel"],
};
const DEFAULT_PALETTE = ["#27ae60", "#2980b9", "#8e44ad", "#e67e22", "#c0392b", "#16a085", "#d4a017", "#7f8c8d"];

// ======================================================================
//  Dátum-segédek (helyi idő, "ÉÉÉÉ-HH-NN")
// ======================================================================
const z2 = n => String(n).padStart(2, "0");
function iso(d) { return `${d.getFullYear()}-${z2(d.getMonth() + 1)}-${z2(d.getDate())}`; }
function parseISO(s) { const m = /^(\d{4})-(\d\d)-(\d\d)$/.exec(s || ""); return m ? new Date(+m[1], m[2] - 1, +m[3]) : null; }
function addDays(s, n) { const d = parseISO(s); d.setDate(d.getDate() + n); return iso(d); }
function todayISO() { return iso(new Date()); }
function wd(s) { return (parseISO(s).getDay() + 6) % 7; }          // 0 = hétfő
function isoWeek(s) {
  const d = parseISO(s); const t = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 3 - (d.getDay() + 6) % 7);
  const w1 = new Date(t.getFullYear(), 0, 4);
  return 1 + Math.round(((t - w1) / 864e5 - 3 + (w1.getDay() + 6) % 7) / 7);
}
function huDate(s, opts = {}) {
  const d = parseISO(s); if (!d) return "";
  let t = (opts.year === false ? "" : d.getFullYear() + ". ") + HONAP[d.getMonth()] + " " + d.getDate() + ".";
  if (opts.weekday) t += ", " + NAP[wd(s)];
  return t;
}
function daysBetween(a, b) { return Math.round((parseISO(b) - parseISO(a)) / 864e5); }
function nowTs() {
  const d = new Date();
  return `${iso(d)} ${z2(d.getHours())}:${z2(d.getMinutes())}:${z2(d.getSeconds())}`;
}
function newId(n = 12) { return [...crypto.getRandomValues(new Uint8Array(n))].map(b => b.toString(16).padStart(2, "0")).join("").slice(0, n * 2); }
function fmtT(v) { if (v == null) return "–"; const r = Math.round(v); return (r < 0 ? "−" : "") + Math.abs(r) + "°"; }
function fmtH(h) { return (Math.round(h * 10) / 10).toString().replace(".", ",") + " óra"; }

// ======================================================================
//  Tárolás (localStorage) + állapot
// ======================================================================
const Store = {
  get(k, def) { try { const v = localStorage.getItem("anm." + k); return v == null ? def : JSON.parse(v); } catch (_) { return def; } },
  set(k, v) { try { localStorage.setItem("anm." + k, JSON.stringify(v)); return true; } catch (_) { return false; } },
  del(k) { try { localStorage.removeItem("anm." + k); } catch (_) {} },
};

const S = {
  snap: null, ops: [], cfg: { link: "", lastFetch: 0, wx: true }, wx: null,
  sel: todayISO(), ym: null, view: "cal", idx: null,
};

// ----------------------------------------------------------------------
//  Az adatok a telefonos változásokkal együtt (effektív nézet)
// ----------------------------------------------------------------------
function rebuild() {
  const snap = S.snap; if (!snap) { S.idx = null; return; }
  const del = new Set(), skip = new Set(), puts = new Map();
  const shifts = Object.assign({}, snap.shifts || {});
  const todos = new Map((snap.todos || []).map(t => [t.id, Object.assign({}, t)]));
  for (const o of S.ops) {
    if (o.op === "event_put") { puts.set(o.event.id, o.event); del.delete(o.event.id); }
    else if (o.op === "event_del") { del.add(o.event_id); puts.delete(o.event_id); }
    else if (o.op === "event_skip") skip.add(o.event_id + "|" + o.day);
    else if (o.op === "shift") { if (o.code) shifts[o.day] = o.code; else delete shifts[o.day]; }
    else if (o.op === "todo_put") todos.set(o.todo.id, Object.assign({}, todos.get(o.todo.id) || {}, o.todo, { _local: 1 }));
    else if (o.op === "todo_del") todos.delete(o.todo_id);
  }
  const byDay = new Map();
  const push = (i) => {
    for (let k = 0; k <= (i.span || 0); k++) {
      const d = k ? addDays(i.occ, k) : i.occ;
      if (!byDay.has(d)) byDay.set(d, []);
      byDay.get(d).push(i);
    }
  };
  for (const i of snap.instances || []) {
    if (puts.has(i.id) || del.has(i.id) || skip.has(i.id + "|" + i.occ)) continue;
    push(i);
  }
  for (const e of puts.values()) {
    const span = e.end_date && e.end_date > e.date ? daysBetween(e.date, e.end_date) : 0;
    push(Object.assign({}, e, { occ: e.date, span, kind: "event", _local: 1 }));
  }
  for (const l of byDay.values())
    l.sort((a, b) => (a.all_day === b.all_day ? 0 : a.all_day ? -1 : 1) || (a.time || "").localeCompare(b.time || "")
      || a.title.localeCompare(b.title, "hu"));
  const types = new Map((snap.shift_types || []).map(t => [t.code, t]));
  S.idx = { byDay, shifts, todos: [...todos.values()], types };
}

function dayInfo(s) { return (S.snap && S.snap.days && S.snap.days[s]) || null; }
function itemsOn(s) { return (S.idx && S.idx.byDay.get(s)) || []; }
function shiftOn(s) { const c = S.idx && S.idx.shifts[s]; return c ? S.idx.types.get(c) || null : null; }
function todosOn(s) { return S.idx ? S.idx.todos.filter(t => t.due === s) : []; }

// ======================================================================
//  Műveletek (telefonos változások)
// ======================================================================
function addOp(kind, payload, msg) {
  S.ops.push(Object.assign({ id: newId(8), ts: nowTs(), op: kind }, payload));
  Store.set("ops", S.ops);
  rebuild(); render();
  if (msg) toast(msg);
}

function importSnapshot(data, how) {
  if (!data || data.format !== FORMAT || !data.days || !Array.isArray(data.instances))
    throw new Error("Ez nem az Arrabona Naptár telefonos adatfájlja (ArrabonaNaptar_mobil.json).");
  const applied = new Set(data.applied || []);
  const before = S.ops.length;
  S.ops = S.ops.filter(o => !applied.has(o.id));
  S.snap = data;
  if (!Store.set("snap", data)) throw new Error("A telefon tárhelye megtelt.");
  Store.set("ops", S.ops);
  rebuild();
  const taken = before - S.ops.length;
  return `Frissítve (${how}) – gép: ${data.generated || "?"}` +
    (taken ? ` · ${taken} változásodat a gép átvette` : "") +
    (unsent() ? ` · ${unsent()} még nincs elküldve` : "");
}

function directLink(u) {
  u = (u || "").trim();
  if (!u) return "";
  try {
    const url = new URL(u);
    if (/(^|\.)dropbox\.com$/i.test(url.hostname)) {
      url.hostname = "dl.dropboxusercontent.com";
      url.searchParams.delete("dl"); url.searchParams.set("dl", "1");
    }
    return url.toString();
  } catch (_) { return ""; }
}

async function fetchLink(quiet) {
  const u = directLink(S.cfg.link);
  if (!u) { if (!quiet) toast("Nincs megadva Dropbox-link."); return false; }
  try {
    const r = await fetch(u, { cache: "no-store", redirect: "follow", credentials: "omit" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const data = await r.json();
    const msg = importSnapshot(data, "Dropbox-link");
    S.cfg.lastFetch = Date.now(); Store.set("cfg", S.cfg);
    render();
    if (!quiet) toast(msg, 4000);
    return true;
  } catch (e) {
    if (!quiet) toast("A link nem tölthető le: " + e.message + ". Használd az „Adatfájl kiválasztása” gombot.", 5500);
    return false;
  }
}

async function exportToPc() {
  if (!S.ops.length) { toast("Nincs új változás a telefonon."); return; }
  const body = JSON.stringify({ format: PHONE_FORMAT, created: nowTs(), app: APP_VERSION, ops: S.ops });
  const file = new File([body], "ArrabonaNaptar_telefon.json", { type: "application/json" });
  try {
    if (navigator.canShare && navigator.canShare({ files: [file] })) {
      await navigator.share({ files: [file], title: "ArrabonaNaptar_telefon.json" });
    } else {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(file); a.download = file.name;
      document.body.append(a); a.click(); a.remove();
    }
  } catch (e) {
    if (e.name === "AbortError") { toast("Megszakítva – a változások a telefonon maradtak."); return; }
    toast("Nem sikerült: " + e.message, 4000); return;
  }
  S.ops.forEach(o => { o.sent = 1; });
  Store.set("ops", S.ops);
  S.cfg.exportedAt = Date.now(); Store.set("cfg", S.cfg);
  renderSyncbars();
  if (S.view === "settings") renderSettings();
  toast("Elküldve – a gépen futó Naptár pár másodpercen belül átveszi.", 4000);
  if (S.cfg.link) setTimeout(() => fetchLink(true), 30e3);   // fél perc múlva megnézzük a visszaigazolást
}

// ======================================================================
//  Időjárás (open-meteo.com, ugyanaz, mint a gépen)
// ======================================================================
function wxUrl(lat, lon) {
  const q = new URLSearchParams({
    latitude: (+lat).toFixed(4), longitude: (+lon).toFixed(4),
    current: "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,is_day",
    hourly: "temperature_2m,weather_code,precipitation_probability",
    daily: "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_speed_10m_max,sunrise,sunset",
    timezone: "Europe/Budapest", forecast_days: "16", wind_speed_unit: "kmh",
  });
  return "https://api.open-meteo.com/v1/forecast?" + q.toString().replace(/%2C/g, ",");
}
async function loadWeather(force) {
  const w = S.snap && S.snap.weather;
  if (!w || !w.enabled || !S.cfg.wx) return;
  const c = S.wx;
  if (!force && c && c.name === w.name && Date.now() - c.at < 30 * 60e3) return;
  try {
    const r = await fetch(wxUrl(w.lat, w.lon), { cache: "no-store", credentials: "omit" });
    if (!r.ok) throw new Error(r.status);
    const d = await r.json();
    const out = { at: Date.now(), name: w.name, current: d.current || {}, daily: {}, hourly: [] };
    const dl = d.daily || {};
    (dl.time || []).forEach((t, i) => {
      out.daily[t] = { code: dl.weather_code[i], tmax: dl.temperature_2m_max[i], tmin: dl.temperature_2m_min[i],
        pp: (dl.precipitation_probability_max || [])[i], psum: (dl.precipitation_sum || [])[i],
        wind: (dl.wind_speed_10m_max || [])[i], sunrise: ((dl.sunrise || [])[i] || "").slice(11, 16),
        sunset: ((dl.sunset || [])[i] || "").slice(11, 16) };
    });
    const hl = d.hourly || {};
    (hl.time || []).forEach((t, i) => out.hourly.push({ t, temp: hl.temperature_2m[i], code: hl.weather_code[i] }));
    S.wx = out; Store.set("wx", out);
    render();
  } catch (_) { /* internet nélkül a tárolt marad */ }
}
function wxDay(s) { return S.cfg.wx && S.wx && S.wx.daily ? S.wx.daily[s] || null : null; }
function wxIcon(code) { return (WMO[code] || ["·", "–"]); }

// ======================================================================
//  Felület
// ======================================================================
const $ = id => document.getElementById(id);
function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") e.className = v;
    else if (k === "style") e.style.cssText = v;          // CSSOM: a szigorú CSP mellett is működik
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) e.append(k.nodeType ? k : String(k));
  return e;
}
let toastT = null;
function toast(msg, ms = 2600) {
  const t = $("toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, ms);
}
function safeColor(c) { return /^#[0-9a-f]{3,8}$/i.test(c || "") ? c : "#27ae60"; }

function show(view) {
  S.view = view;
  const has = !!S.snap;
  $("v-start").hidden = !(view === "start" || (!has && view !== "settings"));
  $("v-cal").hidden = !(has && view === "cal");
  $("v-todo").hidden = !(has && view === "todo");
  $("v-settings").hidden = view !== "settings";
  $("tabs").hidden = !has && view !== "settings";
  for (const [id, v] of [["t-cal", "cal"], ["t-todo", "todo"], ["t-settings", "settings"]]) $(id).classList.toggle("on", v === view);
  render();
}

function render() {
  renderSyncbars();
  if (!S.snap) { if (S.view === "settings") renderSettings(); return; }
  if (S.view === "cal") { renderGrid(); renderDay(); }
  else if (S.view === "todo") renderTodos();
  else if (S.view === "settings") renderSettings();
}

// [1.0.1] a sáv csak a még el NEM küldött változásokat számolja; az elküldöttek a gép
// visszaigazolásáig (a következő adatfrissítésig) csendben megmaradnak, és újraküldéskor újra mennek
function unsent() { return S.ops.filter(o => !o.sent).length; }
function renderSyncbars() {
  const n = unsent();
  for (const [b, t] of [["syncbar", "syncbar-t"], ["syncbar2", "syncbar2-t"]]) {
    $(b).hidden = !n; $(t).textContent = `${n} változás még nincs a gépen`;
  }
}

// ---------- havi rács ----------
function renderGrid() {
  if (!S.ym) { const d = parseISO(S.sel); S.ym = [d.getFullYear(), d.getMonth()]; }
  const [y, m] = S.ym;
  $("m-title").textContent = `${y}. ${HONAP[m]}`;
  const g = $("grid"); g.replaceChildren();
  g.append(el("div", { class: "gh" }, "hét"));
  NAP_R.forEach((n, i) => g.append(el("div", { class: "gh" + (i === 6 ? " we" : "") }, n)));
  const first = new Date(y, m, 1);
  let cur = iso(new Date(y, m, 1 - (first.getDay() + 6) % 7));
  const t0 = todayISO();
  for (let r = 0; r < 6; r++) {
    g.append(el("div", { class: "wk" }, String(isoWeek(cur))));
    for (let c = 0; c < 7; c++) {
      const s = cur, d = parseISO(s), info = dayInfo(s) || {};
      const cls = ["c"];
      if (d.getMonth() !== m) cls.push("out");
      if (s === t0) cls.push("today");
      if (s === S.sel) cls.push("sel");
      const cell = el("div", { class: cls.join(" "), "data-day": s });
      cell.append(el("div", { class: "n" + (info.r ? " red" : "") }, String(d.getDate())));
      const w = wxDay(s);
      if (w) cell.append(el("div", { class: "wx" }, wxIcon(w.code)[0] + fmtT(w.tmax)));
      const sh = shiftOn(s);
      if (sh) cell.append(el("div", { class: "sh", style: `background:${safeColor(sh.color)}` }, sh.code));
      else if (info.h) cell.append(el("div", { class: "hd" }, info.h));
      const dots = el("div", { class: "dots" });
      const its = itemsOn(s);
      its.slice(0, 4).forEach(i => dots.append(el("i", { class: "dot", style: `background:${safeColor(i.color)}` })));
      if (todosOn(s).some(t => !t.done)) dots.append(el("i", { class: "dot todo" }));
      cell.append(dots);
      g.append(cell);
      cur = addDays(cur, 1);
    }
  }
}

// ---------- napi panel ----------
function renderDay() {
  const s = S.sel, info = dayInfo(s), box = $("day"), t0 = todayISO();
  box.replaceChildren();
  const head = el("div", { class: "card" });
  head.append(el("p", { class: "dh" + (info && info.r ? " red" : "") }, huDate(s, { year: false, weekday: true })),
    el("div", { class: "sub" }, `${parseISO(s).getFullYear()} · ${isoWeek(s)}. hét` +
      (s === t0 ? " · ma" : ` · ${Math.abs(daysBetween(t0, s))} nap${daysBetween(t0, s) < 0 ? "ja" : " múlva"}`)));
  if (!info) head.append(el("p", { class: "soft small" }, "Erre a napra nincs adat (a gép csak a tavalyi, idei és jövő évi napokat küldi)."));
  else {
    const watched = new Set((S.snap.watched || []).map(n => n.toLowerCase()));
    const nm = el("div", { class: "names" }, "Névnap: ");
    (info.n || []).forEach((n, i) => { if (i) nm.append(", "); nm.append(watched.has(n.toLowerCase()) ? el("b", {}, "★ " + n) : n); });
    if (!(info.n || []).length) nm.append("– (szökőnap)");
    head.append(nm);
    if (info.x) head.append(el("div", { class: "jel" }, "További névnapok: " + info.x.join(", ")));
    if (info.h) head.append(el("div", { class: "hol" }, info.h));
    if (info.s) head.append(el("div", { class: "swap" }, info.s));
    (info.j || []).forEach(j => head.append(el("div", { class: "jel" }, "• " + j)));
  }
  box.append(head);

  // időjárás
  const w = wxDay(s);
  if (w) {
    const c = el("div", { class: "card" });
    const [ic, tx] = wxIcon(w.code);
    const cur = S.wx.current || {};
    if (s === t0 && cur.temperature_2m != null) {
      const [ci, ct] = wxIcon(cur.weather_code);
      c.append(el("div", { class: "wxbig" }, `${ci} ${fmtT(cur.temperature_2m)} `, el("span", { class: "sub" }, ct)),
        el("div", { class: "sub" }, `érzésre ${fmtT(cur.apparent_temperature)} · szél ${Math.round(cur.wind_speed_10m || 0)} km/h · pára ${Math.round(cur.relative_humidity_2m || 0)}%`),
        el("div", {}, `Napközben: ${ic} ${tx}, ${fmtT(w.tmax)} / ${fmtT(w.tmin)}`));
      const now = new Date(), key = `${todayISO()}T${z2(now.getHours())}:00`;
      const hs = S.wx.hourly.filter(h => h.t > key).filter((_, i) => i % 3 === 2).slice(0, 6);
      if (hs.length) c.append(el("div", { class: "hours" }, hs.map(h => el("span", {}, h.t.slice(11, 13) + "h", el("br"), wxIcon(h.code)[0] + fmtT(h.temp)))));
    } else {
      c.append(el("div", { class: "wxbig" }, `${ic} ${fmtT(w.tmax)} / ${fmtT(w.tmin)} `, el("span", { class: "sub" }, tx)));
    }
    const extra = [];
    if (w.pp != null) extra.push(`csapadék esélye ${Math.round(w.pp)}%`);
    if (w.psum) extra.push(`${String(Math.round(w.psum * 10) / 10).replace(".", ",")} mm`);
    if (w.wind != null) extra.push(`szél max. ${Math.round(w.wind)} km/h`);
    if (extra.length) c.append(el("div", { class: "sub" }, extra.join(" · ")));
    if (w.sunrise) c.append(el("div", { class: "sub" }, `Napkelte ${w.sunrise} · napnyugta ${w.sunset} · ${S.wx.name}`));
    box.append(c);
  }

  // műszak
  const sh = shiftOn(s);
  const shc = el("div", { class: "card" });
  const row = el("div", { class: "row" });
  if (sh) row.append(el("span", { class: "badge", style: `background:${safeColor(sh.color)}` }, sh.code),
    el("div", { class: "grow" }, sh.name + (sh.start && sh.end ? `  ${sh.start}–${sh.end}` : "")));
  else row.append(el("div", { class: "grow soft" }, "Nincs műszak beírva"));
  row.append(el("button", { class: "mini", "data-act": "shift-pick" }, sh ? "Módosítás" : "Műszak…"));
  shc.append(row);
  const ms = monthSummary(s);
  if (ms.days) {
    const diff = ms.total - ms.keret;
    shc.append(el("div", { class: "stat", style: "margin-top:8px" },
      `${HONAP[parseISO(s).getMonth()]}: ${fmtH(ms.work)} munka` + (ms.leave ? ` + ${fmtH(ms.leave)} távollét` : "") +
      ` · keret ${fmtH(ms.keret)} · `, el("span", { class: diff > 0 ? "warn" : diff < 0 ? "soft" : "ok" },
        (diff > 0 ? "+" : "") + fmtH(diff))));
  }
  const lv = leaveSummary(parseISO(s).getFullYear());
  if (lv) shc.append(el("div", { class: "stat", style: "margin-top:4px" },
    `Szabadság ${lv.year}: ${lv.total} nap · kivett ${lv.taken} · tervezett ${lv.planned} · `,
    el("span", { class: lv.remaining < 0 ? "bad" : "ok" }, `marad ${lv.remaining}`)));
  box.append(shc);

  // események
  const sec = el("div", { class: "sec" }, el("h3", {}, "Események"), el("button", { class: "mini on", "data-act": "new-event" }, "+ Esemény"));
  box.append(sec);
  const its = itemsOn(s);
  const ul = el("ul", { class: "list" });
  if (!its.length) ul.append(el("li", { class: "empty" }, "Nincs esemény."));
  its.forEach(i => {
    const tm = i.all_day ? "Egész nap" : (i.time + (i.end_time ? "–" + i.end_time : ""));
    const sub = [tm]; if (i.location) sub.push(i.location); if (i.cal) sub.push(i.cal); if (i.rec) sub.push("ismétlődő");
    const li = el("li", { "data-act": "event", "data-id": i.id, "data-occ": i.occ },
      el("span", { class: "bar", style: `background:${safeColor(i.color)}` }),
      el("div", { class: "li-main" }, el("div", { class: "li-t" }, i.title), el("div", { class: "li-s" }, sub.join(" · "))));
    ul.append(li);
  });
  box.append(ul);

  // teendők
  box.append(el("div", { class: "sec" }, el("h3", {}, "Teendők"), el("button", { class: "mini", "data-act": "new-todo-day" }, "+ Teendő")));
  let tds = todosOn(s);
  if (s === t0) tds = S.idx.todos.filter(t => !t.done && t.due && t.due < s).concat(tds);
  const tl = el("ul", { class: "list" });
  if (!tds.length) tl.append(el("li", { class: "empty" }, "Nincs teendő erre a napra."));
  tds.forEach(t => tl.append(todoLi(t, t.due !== s)));
  box.append(tl);

  // figyelt névnapok a következő 30 napban
  const up = upcomingWatched(s, 30);
  if (up.length) {
    const c = el("div", { class: "card" }, el("p", {}, el("b", {}, "Közelgő figyelt névnapok")));
    up.forEach(([d, n]) => c.append(el("div", { class: "sub" }, `${huDate(d, { year: false })} – ${n}`)));
    box.append(c);
  }
}

function todoLi(t, showDue) {
  const t0 = todayISO();
  const late = t.due && t.due < t0 && !t.done;
  const sub = [];
  if (showDue && t.due) sub.push(t.due === t0 ? "ma" : t.due === addDays(t0, 1) ? "holnap" : huDate(t.due, { year: t.due.slice(0, 4) !== t0.slice(0, 4) }));
  if (t.notes) sub.push(t.notes.split("\n")[0].slice(0, 60));
  return el("li", { class: t.done ? "done" : "" },
    el("span", { class: "chk" + (t.done ? " on" : ""), "data-act": "todo-toggle", "data-id": t.id }, t.done ? "✓" : ""),
    el("div", { class: "li-main", "data-act": "todo-edit", "data-id": t.id }, el("div", { class: "li-t" }, t.title),
      sub.length ? el("div", { class: "li-s" + (late ? " late" : "") }, sub.join(" · ")) : null));
}

function upcomingWatched(from, n) {
  const w = new Set((S.snap.watched || []).map(x => x.toLowerCase()));
  if (!w.size) return [];
  const out = [];
  for (let k = 0; k < n; k++) {
    const d = addDays(from, k), i = dayInfo(d);
    if (!i) break;
    for (const nm of (i.n || []).concat(i.x || [])) if (w.has(nm.toLowerCase())) out.push([d, nm]);
  }
  return out.slice(0, 6);
}

function monthSummary(s) {
  const d = parseISO(s), y = d.getFullYear(), m = d.getMonth();
  let work = 0, leave = 0, days = 0, keret = 0;
  for (let k = 1; k <= new Date(y, m + 1, 0).getDate(); k++) {
    const ds = iso(new Date(y, m, k)), info = dayInfo(ds);
    if (info && !info.o) keret += 8;
    const t = shiftOn(ds);
    if (t) { days++; if (t.kind === "work") work += +t.hours || 0; else if (t.kind === "leave") leave += +t.hours || 0; }
  }
  return { work, leave, days, keret, total: work + leave };
}

function leaveSummary(y) {
  const l = S.snap.leave && S.snap.leave[String(y)];
  if (!l) return null;
  const codes = new Set((S.snap.shift_types || []).filter(t => t.counts_leave).map(t => t.code));
  let taken = 0, planned = 0;
  const t0 = todayISO();
  for (const [d, c] of Object.entries(S.idx.shifts))
    if (d.startsWith(y + "-") && codes.has(c)) { if (d <= t0) taken++; else planned++; }
  if (!l.configured && !taken && !planned) return null;
  return { year: y, total: l.total, taken, planned, remaining: l.total - taken - planned };
}

// ---------- teendők nézet ----------
function renderTodos() {
  const box = $("todos"); box.replaceChildren();
  const t0 = todayISO(), groups = [["Lejárt", []], ["Ma", []], ["Holnap", []], ["A következő 7 napban", []],
    ["Később", []], ["Határidő nélkül", []], ["Kész", []]];
  const G = Object.fromEntries(groups);
  const all = S.idx.todos.slice().sort((a, b) => (a.due || "9999").localeCompare(b.due || "9999") || a.title.localeCompare(b.title, "hu"));
  for (const t of all) {
    if (t.done) G["Kész"].push(t);
    else if (!t.due) G["Határidő nélkül"].push(t);
    else if (t.due < t0) G["Lejárt"].push(t);
    else if (t.due === t0) G["Ma"].push(t);
    else if (t.due === addDays(t0, 1)) G["Holnap"].push(t);
    else if (t.due <= addDays(t0, 7)) G["A következő 7 napban"].push(t);
    else G["Később"].push(t);
  }
  G["Kész"].sort((a, b) => (b.done_at || "").localeCompare(a.done_at || ""));
  if (!all.length) box.append(el("p", { class: "empty" }, "Még nincs teendő. Írd be fent, és nyomd meg az Entert."));
  for (const [name, lst] of groups) {
    if (!lst.length) continue;
    box.append(el("div", { class: "grp" + (name === "Lejárt" ? " bad" : "") }, `${name} (${lst.length})`));
    const ul = el("ul", { class: "list" });
    (name === "Kész" ? lst.slice(0, 30) : lst).forEach(t => ul.append(todoLi(t, true)));
    box.append(ul);
  }
}

// ---------- beállítások ----------
function renderSettings() {
  const sn = S.snap;
  $("s-data").textContent = sn
    ? `A gép adatai: ${sn.generated || "?"} (Naptár v${sn.app_version || "?"}), ${sn.range[0].slice(0, 4)}–${sn.range[1].slice(0, 4)}.` +
      (S.cfg.lastFetch ? ` Utolsó letöltés a linkről: ${new Date(S.cfg.lastFetch).toLocaleString("hu-HU")}.` : "")
    : "Még nincs adat.";
  $("s-link").value = S.cfg.link || "";
  const un = unsent(), wait = S.ops.length - un;
  $("s-pending").textContent = !S.ops.length ? "Minden változás a gépen van."
    : (un ? `${un} változás még nincs elküldve. ` : "") +
      (wait ? `${wait} elküldve, a gép visszaigazolására vár (a következő adatfrissítéskor eltűnik).` : "");
  $("s-wx").checked = !!S.cfg.wx;
  $("s-wx-info").textContent = sn && sn.weather ? `Település: ${sn.weather.name} (a gépen állítható) · open-meteo.com` : "";
  $("s-ver").textContent = `Arrabona Naptár Mobil v${APP_VERSION}`;
}

// ======================================================================
//  Lapok (sheet): esemény, szerkesztés, műszak, teendő
// ======================================================================
function sheet(...kids) {
  const b = $("sheet-box"); b.replaceChildren(...kids.flat());
  $("sheet").hidden = false;
}
function closeSheet() { $("sheet").hidden = true; $("sheet-box").replaceChildren(); }

function findItem(id, occ) { return itemsOn(occ).find(i => i.id === id) || null; }

function openEvent(id, occ) {
  const i = findItem(id, occ); if (!i) return;
  const tm = i.all_day ? "Egész nap" : (i.time + (i.end_time ? "–" + i.end_time : ""));
  const kids = [el("h3", {}, i.title),
    el("div", { class: "card" },
      el("div", {}, huDate(i.occ, { weekday: true }) + (i.span ? " – " + huDate(addDays(i.occ, i.span), { weekday: true }) : "")),
      el("div", { class: "sub" }, tm),
      i.location ? el("div", {}, "📍 " + i.location) : null,
      i.notes ? el("div", { class: "sub", style: "white-space:pre-wrap;margin-top:6px" }, i.notes) : null,
      i.cal ? el("div", { class: "sub", style: "margin-top:6px" }, "Naptár: " + i.cal + " (csak olvasható)") : null)];
  if (!i.ro && !i.rec) {
    kids.push(el("button", { class: "btn primary", "data-act": "edit-event", "data-id": i.id, "data-occ": i.occ }, "Szerkesztés"));
    kids.push(el("button", { class: "btn danger", "data-act": "del-event", "data-id": i.id, "data-occ": i.occ }, "Törlés"));
  } else if (i.rec && !i.ro) {
    kids.push(el("p", { class: "soft small" }, "Ismétlődő esemény: a sorozatot a gépen tudod szerkeszteni. Innen ezt az egy alkalmat törölheted."));
    kids.push(el("button", { class: "btn danger", "data-act": "skip-event", "data-id": i.id, "data-occ": i.occ }, "Csak ez az alkalom törlése"));
  }
  kids.push(el("button", { class: "btn link", "data-act": "close" }, "Bezár"));
  sheet(kids);
}

let EDIT = null;
function openEditor(item) {
  const palette = (S.snap.palette && S.snap.palette.length ? S.snap.palette : DEFAULT_PALETTE);
  const e = item ? { id: item.id, title: item.title, all_day: item.all_day, date: item.date || item.occ,
    end_date: item.end_date || "", time: item.time || "", end_time: item.end_time || "", location: item.location || "",
    notes: item.notes || "", color: item.color || palette[0] }
    : { id: newId(16), title: "", all_day: false, date: S.sel, end_date: "", time: "09:00", end_time: "10:00",
        location: "", notes: "", color: palette[0], _new: 1 };
  EDIT = e;
  const sw = el("div", { class: "sw" });
  palette.forEach(c => sw.append(el("i", { class: c === e.color ? "on" : "", style: `background:${safeColor(c)}`, "data-act": "color", "data-c": c })));
  const f = (lab, input) => el("div", { class: "ef" }, el("label", {}, lab), input);
  sheet(el("h3", {}, item ? "Esemény szerkesztése" : "Új esemény"),
    f("Megnevezés", el("input", { type: "text", id: "e-title", value: e.title, placeholder: "pl. Fogorvos", enterkeyhint: "done" })),
    el("div", { class: "ef tgl" }, el("span", {}, "Egész napos"), el("input", { type: "checkbox", id: "e-all", checked: e.all_day ? "" : null })),
    el("div", { class: "two" }, f("Kezdés napja", el("input", { type: "date", id: "e-date", value: e.date })),
      f("Kezdés", el("input", { type: "time", id: "e-time", value: e.time }))),
    el("div", { class: "two" }, f("Vége napja (nem kötelező)", el("input", { type: "date", id: "e-edate", value: e.end_date })),
      f("Vége", el("input", { type: "time", id: "e-etime", value: e.end_time }))),
    f("Helyszín", el("input", { type: "text", id: "e-loc", value: e.location })),
    f("Megjegyzés", el("textarea", { id: "e-notes" }, e.notes)),
    f("Szín", sw),
    el("button", { class: "btn primary big", "data-act": "save-event" }, "Mentés"),
    el("button", { class: "btn link", "data-act": "close" }, "Mégse"));
  const upd = () => { const a = $("e-all").checked; $("e-time").disabled = a; $("e-etime").disabled = a; };
  $("e-all").addEventListener("change", upd); upd();
  if (!item) setTimeout(() => $("e-title").focus(), 50);
}
function saveEditor() {
  const e = EDIT; if (!e) return;
  const title = $("e-title").value.trim();
  const date = $("e-date").value, edate = $("e-edate").value;
  if (!title) { toast("Adj meg egy megnevezést."); return; }
  if (!parseISO(date)) { toast("Add meg a napot."); return; }
  const all = $("e-all").checked;
  const ev = { id: e.id, title, all_day: all, date, end_date: edate && edate > date ? edate : "",
    time: all ? "" : $("e-time").value, end_time: all ? "" : $("e-etime").value,
    location: $("e-loc").value.trim(), notes: $("e-notes").value.trim(), color: e.color };
  EDIT = null; closeSheet();
  S.sel = date; const d = parseISO(date); S.ym = [d.getFullYear(), d.getMonth()];
  addOp("event_put", { event: ev }, "Mentve a telefonon – küldd el a gépre.");
}

function openShiftPicker() {
  const types = S.snap.shift_types || [];
  const g = el("div", { class: "shgrid" });
  types.forEach(t => g.append(el("button", { style: `background:${safeColor(t.color)}`, "data-act": "set-shift", "data-code": t.code },
    `${t.code} – ${t.name}`, el("small", {}, t.start && t.end ? `${t.start}–${t.end}` : fmtH(t.hours)))));
  g.append(el("button", { class: "none", "data-act": "set-shift", "data-code": "" }, "Nincs", el("small", {}, "műszak törlése")));
  sheet(el("h3", {}, "Műszak – " + huDate(S.sel, { year: false, weekday: true })), g,
    el("p", { class: "soft small" }, "Tipp: a következő napra lépéshez használd a „Következő nap” gombot."),
    el("div", { class: "two" }, el("button", { class: "btn", "data-act": "shift-prev" }, "‹ Előző nap"),
      el("button", { class: "btn", "data-act": "shift-next" }, "Következő nap ›")),
    el("button", { class: "btn link", "data-act": "close" }, "Kész"));
}

let TEDIT = null;
function openTodo(t, due) {
  TEDIT = t ? Object.assign({}, t) : { id: newId(6), title: "", due: due || "", notes: "", done: false, _new: 1 };
  const f = (lab, input) => el("div", { class: "ef" }, el("label", {}, lab), input);
  const kids = [el("h3", {}, t ? "Teendő" : "Új teendő"),
    f("Teendő", el("input", { type: "text", id: "td-title", value: TEDIT.title, enterkeyhint: "done" })),
    f("Határidő (nem kötelező)", el("input", { type: "date", id: "td-due", value: TEDIT.due || "" })),
    f("Megjegyzés", el("textarea", { id: "td-notes" }, TEDIT.notes || "")),
    el("button", { class: "btn primary big", "data-act": "save-todo" }, "Mentés")];
  if (t) {
    kids.push(el("button", { class: "btn", "data-act": "todo-toggle", "data-id": t.id, "data-close": "1" }, t.done ? "Újranyitás" : "Kész ✓"));
    kids.push(el("button", { class: "btn danger", "data-act": "del-todo" }, "Törlés"));
  }
  kids.push(el("button", { class: "btn link", "data-act": "close" }, "Mégse"));
  sheet(kids);
  if (!t) setTimeout(() => $("td-title").focus(), 50);
}
function saveTodo() {
  const title = $("td-title").value.trim();
  if (!title) { toast("Írd be, mi a teendő."); return; }
  const t = { id: TEDIT.id, title, due: $("td-due").value || "", notes: $("td-notes").value.trim(), done: !!TEDIT.done };
  TEDIT = null; closeSheet();
  addOp("todo_put", { todo: t }, "Mentve a telefonon.");
}
function toggleTodo(id) {
  const t = S.idx.todos.find(x => x.id === id); if (!t) return;
  addOp("todo_put", { todo: { id: t.id, title: t.title, due: t.due || "", notes: t.notes || "", done: !t.done,
    done_at: !t.done ? nowTs().slice(0, 16) : "" } });
}

// ======================================================================
//  Események kezelése
// ======================================================================
function selectDay(s) {
  S.sel = s; const d = parseISO(s);
  if (!S.ym || S.ym[0] !== d.getFullYear() || S.ym[1] !== d.getMonth()) S.ym = [d.getFullYear(), d.getMonth()];
  render();
}
function moveMonth(k) {
  let [y, m] = S.ym; m += k; if (m < 0) { m = 11; y--; } if (m > 11) { m = 0; y++; }
  S.ym = [y, m];
  const sd = parseISO(S.sel);
  const day = Math.min(sd.getDate(), new Date(y, m + 1, 0).getDate());
  S.sel = iso(new Date(y, m, day));
  render();
}

function onClick(ev) {
  const cell = ev.target.closest(".c[data-day]");
  if (cell) { selectDay(cell.dataset.day); return; }
  if (ev.target.id === "sheet") { closeSheet(); return; }
  const b = ev.target.closest("[data-act]"); if (!b) return;
  const a = b.dataset.act, id = b.dataset.id, occ = b.dataset.occ;
  switch (a) {
    case "pick": $("file").click(); break;
    case "prev": moveMonth(-1); break;
    case "next": moveMonth(1); break;
    case "today": selectDay(todayISO()); break;
    case "tab-cal": show("cal"); break;
    case "tab-todo": show("todo"); break;
    case "tab-settings": case "settings": show("settings"); break;
    case "export": exportToPc(); break;
    case "refresh":
      if (S.cfg.link) fetchLink(false).then(ok => { if (ok) loadWeather(true); });
      else $("file").click();
      break;
    case "save-link": {
      const v = $("s-link").value.trim();
      if (v && !directLink(v)) { toast("Ez nem érvényes link."); break; }
      S.cfg.link = v; Store.set("cfg", S.cfg);
      if (v) fetchLink(false).then(ok => { if (ok) { show(S.snap ? "settings" : "start"); loadWeather(true); } });
      else toast("Link törölve.");
      break;
    }
    case "clear-link": S.cfg.link = ""; Store.set("cfg", S.cfg); renderSettings(); toast("Link törölve."); break;
    case "forget":
      if (confirm("Törlöd az adatokat erről a telefonról?" + (S.ops.length ? `\n\nFIGYELEM: ${S.ops.length} változás még nincs a gépen, ezek elvesznek!` : ""))) {
        ["snap", "ops", "wx"].forEach(k => Store.del(k)); S.snap = null; S.ops = []; S.wx = null; rebuild(); show("start");
      }
      break;
    case "event": openEvent(id, occ); break;
    case "new-event": openEditor(null); break;
    case "edit-event": { const i = findItem(id, occ); if (i) openEditor(i); break; }
    case "save-event": saveEditor(); break;
    case "color":
      if (EDIT) { EDIT.color = b.dataset.c; b.parentNode.querySelectorAll("i").forEach(x => x.classList.toggle("on", x === b)); }
      break;
    case "del-event":
      if (confirm("Törlöd ezt az eseményt?")) { closeSheet(); addOp("event_del", { event_id: id }, "Törölve a telefonon."); }
      break;
    case "skip-event":
      if (confirm("Törlöd ezt az egy alkalmat?")) { closeSheet(); addOp("event_skip", { event_id: id, day: occ }, "Az alkalom törölve."); }
      break;
    case "shift-pick": openShiftPicker(); break;
    case "set-shift": {
      const cur = S.idx.shifts[S.sel] || "", code = b.dataset.code;
      if (cur !== code) addOp("shift", { day: S.sel, code });
      toast(code ? `${huDate(S.sel, { year: false })}: ${code}` : "Műszak törölve", 1400);
      openShiftPicker();
      break;
    }
    case "shift-prev": selectDay(addDays(S.sel, -1)); openShiftPicker(); break;
    case "shift-next": selectDay(addDays(S.sel, 1)); openShiftPicker(); break;
    case "new-todo": openTodo(null, ""); break;
    case "new-todo-day": openTodo(null, S.sel); break;
    case "todo-edit": { const t = S.idx.todos.find(x => x.id === id); if (t) openTodo(t); break; }
    case "todo-toggle": toggleTodo(id); if (b.dataset.close) closeSheet(); break;
    case "save-todo": saveTodo(); break;
    case "del-todo":
      if (TEDIT && confirm("Törlöd ezt a teendőt?")) { const tid = TEDIT.id; TEDIT = null; closeSheet(); addOp("todo_del", { todo_id: tid }, "Törölve."); }
      break;
    case "close": EDIT = TEDIT = null; closeSheet(); break;
  }
}

function setupSwipe() {
  let x0 = null, y0 = null;
  const g = $("grid");
  g.addEventListener("touchstart", e => { const t = e.touches[0]; x0 = t.clientX; y0 = t.clientY; }, { passive: true });
  g.addEventListener("touchend", e => {
    if (x0 == null) return;
    const t = e.changedTouches[0], dx = t.clientX - x0, dy = t.clientY - y0;
    x0 = null;
    if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) moveMonth(dx < 0 ? 1 : -1);
  }, { passive: true });
}

// ======================================================================
//  Indítás
// ======================================================================
function init() {
  S.snap = Store.get("snap", null);
  S.ops = Store.get("ops", []);
  S.cfg = Object.assign({ link: "", lastFetch: 0, wx: true }, Store.get("cfg", {}));
  S.wx = Store.get("wx", null);
  rebuild();
  document.addEventListener("click", onClick);
  $("file").addEventListener("change", async ev => {
    const f = ev.target.files && ev.target.files[0]; ev.target.value = "";
    if (!f) return;
    try {
      const data = JSON.parse(await f.text());
      const msg = importSnapshot(data, "fájlból");
      show(S.view === "settings" ? "settings" : "cal");
      toast(msg, 4500);
      loadWeather(true);
    } catch (e) { toast(e.message.startsWith("Ez nem") ? e.message : "A fájl nem olvasható: " + e.message, 5000); }
  });
  $("todo-quick").addEventListener("submit", ev => {
    ev.preventDefault();
    const t = $("tq").value.trim(); if (!t) return;
    addOp("todo_put", { todo: { id: newId(6), title: t, due: $("tq-due").value || "", notes: "", done: false } }, "Teendő felvéve.");
    $("tq").value = "";
  });
  $("s-wx").addEventListener("change", e => { S.cfg.wx = e.target.checked; Store.set("cfg", S.cfg); if (S.cfg.wx) loadWeather(true); render(); });
  setupSwipe();
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    if (S.sel < todayISO() && S.view === "cal") { /* nap váltás után a kijelölés marad */ }
    if (S.cfg.link && Date.now() - (S.cfg.lastFetch || 0) > 60e3) fetchLink(true);
    loadWeather(false);
  });
  show(S.snap ? "cal" : "start");
  if (S.cfg.link) fetchLink(true);
  loadWeather(false);
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
  if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(() => {});
}
if (typeof document !== "undefined") init();
