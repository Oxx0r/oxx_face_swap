# Oxx' FaceSwap – einmalige Einrichtung
#
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
#
# Das Skript legt eine virtuelle Umgebung an, installiert die Abhängigkeiten
# und lädt die ONNX-Modelle (buffalo_l + inswapper_128, ca. 840 MB) herunter.

[CmdletBinding()]
param(
    [switch]$Cuda,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$modelsDir = Join-Path $root "models"
$buffaloZip = Join-Path $modelsDir "buffalo_l.zip"
$buffaloDir = Join-Path $modelsDir "buffalo_l"
$inswapper = Join-Path $modelsDir "inswapper_128.onnx"

$buffaloUrl = "https://github.com/deepinsight/insightface/releases/download/model-zoo/buffalo_l.zip"
$inswapperUrl = "https://github.com/deepinsight/insightface/releases/download/model-zoo/inswapper_128.onnx"

function Write-Step($text) {
    Write-Host ""
    Write-Host "==> $text" -ForegroundColor Green
}

Write-Host "Oxx' FaceSwap Setup" -ForegroundColor Cyan
Write-Host "Projektordner: $root"

# ------------------------------------------------------------------ Python
Write-Step "Prüfe Python"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python wurde nicht gefunden. Bitte Python 3.10+ installieren und 'Add to PATH' aktivieren."
}
$version = (& python --version) -replace "Python ", ""
Write-Host "Gefunden: Python $version"

# --------------------------------------------------------------- venv + pip
if (-not (Test-Path $venvPython)) {
    Write-Step "Erstelle virtuelle Umgebung (.venv)"
    & python -m venv .venv
} else {
    Write-Step "Virtuelle Umgebung existiert bereits"
}

Write-Step "Installiere Abhängigkeiten"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $root "requirements.txt")

if ($Cuda) {
    Write-Step "Installiere onnxruntime-gpu (CUDA)"
    & $venvPython -m pip uninstall -y onnxruntime
    & $venvPython -m pip install onnxruntime-gpu
} else {
    Write-Host "CPU-Modus aktiv. Für NVIDIA-GPU: .\install.ps1 -Cuda" -ForegroundColor DarkGray
}

# ----------------------------------------------------------------- Modelle
New-Item -ItemType Directory -Force $modelsDir | Out-Null

if ($Force -or -not (Test-Path $inswapper)) {
    Write-Step "Lade inswapper_128.onnx (~528 MB)"
    & curl.exe -L --retry 3 -o $inswapper $inswapperUrl
} else {
    Write-Host "inswapper_128.onnx vorhanden." -ForegroundColor DarkGray
}

if ($Force -or -not (Test-Path $buffaloDir)) {
    Write-Step "Lade buffalo_l.zip (~275 MB) und entpacke es"
    & curl.exe -L --retry 3 -o $buffaloZip $buffaloUrl
    New-Item -ItemType Directory -Force $buffaloDir | Out-Null
    Expand-Archive -Path $buffaloZip -DestinationPath $buffaloDir -Force
    Remove-Item $buffaloZip -Force
} else {
    Write-Host "buffalo_l vorhanden." -ForegroundColor DarkGray
}

# ------------------------------------------------------------------- Icon
if (-not (Test-Path (Join-Path $root "assets\icon.ico"))) {
    Write-Step "Erzeuge App-Icon"
    & $venvPython (Join-Path $root "tools\make_icon.py")
}

# ------------------------------------------------------------------ Check
Write-Step "Selbsttest"
& $venvPython -c "from faceswap.engine import FaceSwapEngine; e=FaceSwapEngine(); e.load(); print('Modelle geladen. Gerät:', e.active_device)"

Write-Host ""
Write-Host "Fertig! Starte die App mit start_gui.bat oder:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\python.exe faceswap_gui.py"
Write-Host "  .\.venv\Scripts\python.exe faceswap_cli.py --help"
