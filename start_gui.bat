@echo off
rem ============================================================
rem  Oxx' FaceSwap - GUI starten
rem
rem    Doppelklick          -> Oberflaeche ohne Konsolenfenster
rem    start_gui.bat debug  -> mit Konsole (zeigt Fehlermeldungen)
rem
rem  Fehlt die Einrichtung, weist das Skript auf install.bat hin.
rem ============================================================
setlocal
cd /d "%~dp0"

set "PYW=.venv\Scripts\pythonw.exe"
set "PY=.venv\Scripts\python.exe"
set "APP=faceswap_gui.py"

if not exist "%PY%" (
    echo [Fehler] Keine virtuelle Umgebung gefunden.
    echo          Bitte einmalig install.bat ausfuehren.
    echo.
    pause
    exit /b 1
)

if not exist "models\inswapper_128.onnx" (
    echo [Warnung] Die Modelle fehlen.
    echo           Bitte einmalig install.bat ausfuehren.
    echo.
    pause
)
if not exist "models\buffalo_l\det_10g.onnx" (
    echo [Warnung] Das Erkennungsmodell buffalo_l fehlt.
    echo           Bitte einmalig install.bat ausfuehren.
    echo.
    pause
)

if not exist "output" mkdir "output"

if /i "%~1"=="debug" (
    "%PY%" "%APP%"
    exit /b %ERRORLEVEL%
)

if exist "%PYW%" (
    start "" "%PYW%" "%APP%"
) else (
    start "" "%PY%" "%APP%"
)

endlocal
exit /b 0
