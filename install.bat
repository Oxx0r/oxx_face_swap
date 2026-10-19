@echo off
rem Einmalige Einrichtung: virtuelle Umgebung, Abhaengigkeiten, Modelle.
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "install.ps1"
pause
endlocal
