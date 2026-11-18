# A build.bat hivja: megkeresi az Inno Setup forditojat (ISCC.exe), es kiirja az utvonalat.
import glob
import os
import shutil

jeloltek = []
try:
    import winreg
    for gyoker, ut in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                       (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                       (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")):
        try:
            k = winreg.OpenKey(gyoker, ut)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(k)[0]):
            try:
                al = winreg.OpenKey(k, winreg.EnumKey(k, i))
                nev = str(winreg.QueryValueEx(al, "DisplayName")[0])
                if nev.lower().startswith("inno setup"):
                    hely = str(winreg.QueryValueEx(al, "InstallLocation")[0])
                    jeloltek.append(os.path.join(hely, "ISCC.exe"))
            except OSError:
                pass
except ImportError:
    pass
for alap in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", ""),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
    if alap:
        jeloltek += sorted(glob.glob(os.path.join(alap, "Inno Setup*", "ISCC.exe")), reverse=True)
w = shutil.which("ISCC")
if w:
    jeloltek.append(w)
for j in jeloltek:
    if os.path.isfile(j):
        print(j)
        break
