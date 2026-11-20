# Arrabona Naptár Mobil

Az [Arrabona Naptár](../README.md) telefonos párja (PWA), GitHub Pages-ről:
https://lokypapa.github.io/arrabona-naptar/

- Adat: a gépi Naptár által a Dropbox mappába kiírt `ArrabonaNaptar_mobil.json` (ünnepek, névnapok,
  események, műszakok, teendők, szabadság – előre kiszámolva). Betöltés a Fájlok appból vagy Dropbox-linkről.
- Telefonos változások: `ArrabonaNaptar_telefon.json` („Küldés a gépre”), a gépen futó Naptár átveszi.
- Hálózat: csak az időjárás (open-meteo.com) és a megadott Dropbox-link; a Content-Security-Policy minden mást tilt.
- Fájlok: `index.html`, `app.js`, `app.css`, `sw.js` (offline), `manifest.webmanifest`, ikonok.
