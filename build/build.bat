@echo off
rem ============================================================
rem  Arrabona Naptar - kiadas keszitese
rem    1) PyInstaller: dist\Arrabona Naptar\  (mappa: exe + _internal)
rem    2) Inno Setup:  release\ArrabonaNaptar_Setup_VERZIO.exe
rem  Futtatas: dupla kattintas, vagy a projekt mappajabol:  build\build.bat
rem  Kell hozza: Python 3.11+  es  Inno Setup 7 (vagy 6)
rem ============================================================
setlocal
cd /d "%~dp0.."

set VER=
for /f "delims=" %%v in ('python build\verzio.py') do set VER=%%v
if "%VER%"=="" (
    echo [HIBA] Nem talalom a Pythont vagy a verziot az anaptar\__init__.py-ban.
    goto :hiba
)
echo.
echo === Arrabona Naptar v%VER% kiadas keszitese ===
echo.

echo [1/4] Python-csomagok...
python -m pip install --upgrade --quiet -r requirements.txt pyinstaller || goto :hiba

echo [2/4] PyInstaller...
python -m PyInstaller --noconfirm --clean --onedir --windowed ^
    --name "Arrabona Naptar" --icon "assets\logo_naptar.ico" ^
    --add-data "assets;assets" ^
    --hidden-import pystray._win32 ^
    --hidden-import tzdata --collect-data tzdata ^
    arrabona_naptar.py || goto :hiba

echo [3/4] Inno Setup...
set ISCC=
for /f "delims=" %%i in ('python build\iscc_keres.py') do set "ISCC=%%i"
if not exist "%ISCC%" (
    echo [HIBA] Nincs telepitve az Inno Setup 7 vagy 6: https://jrsoftware.org/isdl.php
    goto :hiba
)
if exist release rmdir /s /q release
"%ISCC%" /Q /DAppVersion=%VER% build\installer.iss || goto :hiba

echo [4/4] SHA256SUMS.txt...
python build\release_hash.py release || goto :hiba

echo.
echo ============================================================
echo  KESZ: release\ArrabonaNaptar_Setup_%VER%.exe + SHA256SUMS.txt
echo  GitHub (kesobb): Releases - Draft a new release - tag: v%VER%
echo  Mindket fajlt huzd be az "Attach binaries" mezobe!
echo ============================================================
explorer release
pause
exit /b 0

:hiba
echo.
echo *** A build megszakadt (lasd a hibat fent). ***
pause
exit /b 1
