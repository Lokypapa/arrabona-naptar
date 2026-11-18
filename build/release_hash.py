# -*- coding: utf-8 -*-
"""SHA256SUMS.txt keszitese a release mappa telepitoihez (a build.bat hivja).
Kesobb az onfrissito ez alapjan ellenorzi a letoltott telepitot."""
import hashlib
import os
import sys

mappa = sys.argv[1] if len(sys.argv) > 1 else "release"
sorok = []
for nev in sorted(os.listdir(mappa)):
    if nev.lower().endswith(".exe"):
        h = hashlib.sha256()
        with open(os.path.join(mappa, nev), "rb") as f:
            for darab in iter(lambda: f.read(1024 * 1024), b""):
                h.update(darab)
        sorok.append("%s  %s" % (h.hexdigest(), nev))
with open(os.path.join(mappa, "SHA256SUMS.txt"), "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(sorok) + "\n")
print("\n".join(sorok))
