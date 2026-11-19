# Arrabona Naptár v1.4.0

Saját Windows-os naptár magyar ünnepekkel, névnapokkal és emlékeztetőkkel. Az [Arrabona Guard](https://github.com/Lokypapa/arrabona-guard) és az [Arrabona Pass](https://github.com/Lokypapa/arrabona-pass) testvérprogramja: ugyanaz a stílus, és követi a Guard sötét vagy világos témáját.

## Mit tud?

- **Nézetek:** Hónap (a hetek számával a bal oszlopban), Hét és Lista (a következő 90 nap). A hétszámra kattintva megnyílik az adott hét.
- **Magyar ünnepek és munkarend:**
  - Az összes munkaszüneti nap: január 1., március 15., nagypéntek, húsvét, május 1., pünkösd, augusztus 20., október 23., november 1., és 2026-tól december 24. is, továbbá december 25–26.
  - Az áthelyezett munkanapok és pihenőnapok (2024–2026 beépítve, a 2026-os december 24-i változással együtt). A következő évekét a Beállítások → Munkarend fülön veheted fel.
  - Jeles napok: vízkereszt, a magyar kultúra napja, Valentin-nap, hamvazószerda, virágvasárnap, anyák napja, gyereknap, pedagógusnap, apák napja, az aradi vértanúk emléknapja, halottak napja, Mikulás, advent vasárnapjai, óraátállítás és mások.
- **Névnapok:** minden nap a cellában és a napi panelen. A Névnap-kereső becenévvel is működik (pl. Kati → Katalin: április 30., november 25.). A **figyelt nevek** (pl. családtagok) ★-gal jelennek meg a naptárban, és a névnapjukon emlékeztető jön.
  - **Bővített névnaptár (v1.2.0):** kb. 90 gyakori modern és külföldi eredetű név (Kiara, Kevin, Noel, Zoé, Hanna, Léna, Szofia, Maja, Leon, Dominik, Bendegúz, Zente…). A napi panelen „További névnapok” sorban látszanak, a kereső és a figyelt nevek is ismerik őket; a havi cellában csak akkor jelennek meg, ha figyelt név.
  - Ha egy névnek több névnapja is van (pl. Leon), a figyelt neveknél kiválaszthatod, melyik napon szóljon („Nap:” mező), vagy hagyhatod „mind”-en.
- **Események:**
  - egész napos vagy időponthoz kötött, többnapos is;
  - helyszín, megjegyzés, 8 szín;
  - ismétlődés: naponta, hetente (kiválasztott napokon, pl. H/Sze/P), havonta, évente, „minden 2. héten”, véggel vagy vég nélkül;
  - ismétlődőnél törölhető csak egy alkalom, egy adott alkalomtól az összes későbbi, vagy az egész sorozat.
- **Születésnapok:** évente ismétlődnek, és ha megadod a születési évet, kiírja, hányadik születésnap lesz („🎂 Anya (68 éves)”). A február 29-i születésnap nem szökőévben február 28-án jelenik meg.
- **Emlékeztetők:**
  - jobb alsó sarokban felugró ablak hangjelzéssel, „Szundi 10 perc” gombbal;
  - egész napos eseménynél és születésnapnál reggel szól (alapból 8:00-kor, beállítható);
  - ha a gép ki volt kapcsolva, induláskor az elmúlt 12 óra elmaradt emlékeztetőit is megmutatja.
- **Műszakbeosztás (v1.1.0):**
  - Műszaktípusok, amiket szabadon átírhatsz: Délelőtt 6–14 (DE), Délután 14–22 (DU), Éjszaka 22–6 (ÉJ), Nappal 12 óra 6–18 (N12), Éjszaka 12 óra 18–6 (É12), Szabadság (SZ), Betegszabadság (B), Pihenőnap (P). Mindegyiknek van kódja, ideje, színe, a fizetett órák száma, a fajtája (munka, fizetett távollét vagy pihenő), és kérhetsz hozzá emlékeztetőt a kezdés előtt.
  - Bejelölés: a **Műszak** gombbal megjelenik a színes gombsor. Válassz típust, és kattints a napokra; ugyanarra újra kattintva törlődik. Jobb gombbal egy napon rögtön is beállíthatod.
  - **Ismétlődő minta:** pl. `N12 É12 - -` (12 órás forgó), vagy hetente váltott 2 vagy 3 műszak. Egy kattintással kitölti akár az egész évet. Kérésre az ünnepnapokat üresen hagyja, és a már bejelölt szabadságot nem írja felül.
  - **Havi összesítés** a napi panelen: hány műszak és hány munkaóra, fizetett távollét, éjszakai órák (22–6), hétvégi és ünnepnapi órák, valamint a **havi munkaidőkeret** (munkanapok × 8 óra) és az eltérés (túlóra vagy hiány).
- **Pontos idő (v1.4.0)** másodpercre a fejlécben, alatta a dátum és a nap.
- **Időjárás (v1.4.0)** az open-meteo.com ingyenes, regisztráció nélküli szolgáltatásából, alapból Győrre (Beállítások vagy a ⚙ jel: bármelyik település):
  - 16 napra előre: a havi cellákban ikon és maximum, a hét nézetben max/min.
  - A napi panelen: mostani hőmérséklet és érzet, szél, páratartalom, csapadék esélye és mennyisége, napkelte és napnyugta, a következő órák.
  - Félóránként frissül, internet nélkül a legutóbbi állapot látszik.
- **Teendőlista (v1.4.0)** – **Teendők** nézet:
  - Gyors felvitel Enterrel, határidővel vagy anélkül; csoportok: Lejárt / Ma / Holnap / 7 napon belül / Később / Határidő nélkül / Kész.
  - A határidős teendők a naptárban és a napi panelen is ☐ jellel látszanak, és aznap reggel (az egész napos emlékeztető idején) szól a program.
- **Szabadság-nyilvántartás (v1.4.0)** – a napi panel Szabadság kártyája, vagy Műszak → Szabadság…:
  - A keretet az Mt. szerint számolja: 20 nap alap, életkor szerinti pótszabadság (25 éves kortól 1–10 nap), gyermekek után 2/4/7 nap (fogyatékos gyermekenként +2). Hozzáadható egyéb pótszabadság és az előző évről áthozott nap, vagy megadható kézi keret.
  - A kivett (mai napig) és tervezett napokat a műszakbeosztásból veszi: alapból az SZ napokat (a Műszaktípusoknál bármelyik típusra bekapcsolható a „Szabadságkeretből fogy”).
  - Októbertől figyelmeztet, ha még maradt beosztatlan szabadság, és akkor is, ha túllépted a keretet.
- **Önfrissítés (v1.4.0):** 6 óránként megnézi a GitHubon a legújabb kiadást, és ha van újabb, narancs sávban felajánlja. Ellenőrzött letöltés (SHA256), csendes telepítés, utána automatikus újraindulás. Kikapcsolható; kézi keresés: Beállítások → „Keresés most”.
- **Több naptár, szinkron (v1.3.0)** – fejléc → **Naptárak**:
  - **Feliratkozás** bármennyi külső naptárra a .ics címükkel: Google Naptár („Titkos cím iCal formátumban”), iCloud (nyilvános naptár linkje), Outlook.com (közzétett ICS-link), vagy egy .ics fájl a gépen. Mindegyik saját színnel jelenik meg, ki-be kapcsolható, 15/30/60/180 percenként frissül, és internet nélkül is látszik a legutóbbi állapota. Kérésre emlékeztetőt is ad az eseményeihez.
  - A külső események csak olvashatók (a módosításuk az eredeti helyükön történik). Egy kattintással **másolatot** kérhetsz belőlük a saját naptáradba, akár egyesével, akár az egész naptárat.
  - **Saját naptár kifelé:** megadhatsz egy mappát (pl. a Dropbox mappádat), ahová a program minden változáskor kiírja az `ArrabonaNaptar.ics` fájlt, kérésre a műszakokkal és a születésnapokkal együtt. Erre a fájlra a Dropbox-linkjével iPhone-on és Google Naptárban is fel lehet iratkozni.
  - **Export / import** .ics fájlba és fájlból (Google, Outlook, iPhone, más naptárprogramok). Az újraimportálás nem duplikál.
- **Napi panel jobb oldalt:** dátum, hét száma, az év hányadik napja, munkanap vagy pihenőnap, névnap, ünnep, jeles napok, a nap eseményei és a közelgő figyelt névnapok.
- **Keresés** az eseményekben és a nevekben (Ctrl+F).
- **Tálca:** az X-re a program a tálcára kerül, így az emlékeztetők akkor is szólnak. Indulhat a Windows-szal is, rögtön a tálcára.

## Billentyűk

| Billentyű | Mit csinál |
|---|---|
| `Ctrl+N` | új esemény |
| `PgUp` / `PgDn` | előző / következő hónap (hét) |
| `Home` | ugrás a mai napra |
| `Ctrl+F` | keresés |
| dupla kattintás egy napon | új esemény arra a napra |

## Adatok

`%APPDATA%\ArrabonaNaptar\naptar.json` (+ `.bak` az előző mentésről) és `beallitasok.json`. Ezek nem a program mappájában vannak, ezért frissítéskor és eltávolításkor is megmaradnak.

## Futtatás forrásból

```
pip install -r requirements.txt
python arrabona_naptar.py
```

## Kiadás készítése

`build\build.bat`: PyInstaller, Inno Setup 7 (vagy 6) és SHA256SUMS.txt → `release\ArrabonaNaptar_Setup_X.Y.Z.exe`.

## Licenc

Minden jog fenntartva, lásd: LICENSE.
