@echo off
rem Kommandozeilen-Version: zeigt unter anderem die Hilfe.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Bitte zuerst install.bat ausfuehren.
    pause
    exit /b 1
)
echo Beispiel:
echo   .venv\Scripts\python.exe faceswap_cli.py --source spender.jpg --target ziel.jpg
echo.
".venv\Scripts\python.exe" faceswap_cli.py --help
cmd /k
endlocal
