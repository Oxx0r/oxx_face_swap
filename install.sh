#!/usr/bin/env bash
# =============================================================================
# Oxx' FaceSwap - einmalige Einrichtung (Shell-Skript / Linux, macOS, Git Bash)
#
#   chmod +x install.sh
#   ./install.sh           # CPU-Modus
#   ./install.sh --cuda    # NVIDIA-GPU (CUDA)
#   ./install.sh --force   # Modelle neu herunterladen, auch wenn vorhanden
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

CUDA=0
FORCE=0

for arg in "$@"; do
    case "$arg" in
        --cuda|-c) CUDA=1 ;;
        --force|-f) FORCE=1 ;;
        --help|-h)
            echo "Verwendung: $0 [--cuda] [--force] [--help]"
            echo "  --cuda   NVIDIA-GPU (onnxruntime-gpu) installieren"
            echo "  --force  Modelle auch dann neu laden, wenn sie schon vorhanden sind"
            echo "  --help   diese Hilfe anzeigen"
            exit 0
            ;;
        *)
            echo "Unbekannte Option: $arg" >&2
            exit 1
            ;;
    esac
done

# --------------------------------------------------------------------------- Python
echo "==> Prüfe Python"
if ! command -v python3 >/dev/null 2>&1; then
    echo "Fehler: Python 3.10+ wurde nicht gefunden. Bitte installieren und in PATH aufnehmen." >&2
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Gefunden: Python $PYTHON_VERSION"

VENV_PYTHON="$ROOT/.venv/bin/python"

# --------------------------------------------------------------- venv + pip
if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "==> Erstelle virtuelle Umgebung (.venv)"
    python3 -m venv .venv
else
    echo "==> Virtuelle Umgebung existiert bereits"
fi

echo "==> Installiere Abhängigkeiten"
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r "$ROOT/requirements.txt"

if [[ $CUDA -eq 1 ]]; then
    echo "==> Installiere onnxruntime-gpu (CUDA)"
    "$VENV_PYTHON" -m pip uninstall -y onnxruntime 2>/dev/null || true
    "$VENV_PYTHON" -m pip install onnxruntime-gpu
else
    echo "   CPU-Modus aktiv. Für NVIDIA-GPU: ./install.sh --cuda"
fi

# ----------------------------------------------------------------- Modelle
MODELS_DIR="$ROOT/models"
BUFFALO_ZIP="$MODELS_DIR/buffalo_l.zip"
BUFFALO_DIR="$MODELS_DIR/buffalo_l"
INSWAPPER="$MODELS_DIR/inswapper_128.onnx"

BUFFALO_URL="https://github.com/deepinsight/insightface/releases/download/model-zoo/buffalo_l.zip"
INSWAPPER_URL="https://github.com/deepinsight/insightface/releases/download/model-zoo/inswapper_128.onnx"

mkdir -p "$MODELS_DIR"

download_if_needed() {
    local target="$1"
    local url="$2"
    local marker="$3"
    if [[ $FORCE -eq 1 || ! -e "$marker" ]]; then
        echo "==> Lade $(basename "$target") herunter"
        if command -v curl >/dev/null 2>&1; then
            curl -L --retry 3 -o "$target" "$url"
        elif command -v wget >/dev/null 2>&1; then
            wget -O "$target" "$url"
        else
            echo "Fehler: weder curl noch wget verfügbar." >&2
            exit 1
        fi
    else
        echo "   $(basename "$target") vorhanden."
    fi
}

if [[ $FORCE -eq 1 || ! -f "$INSWAPPER" ]]; then
    download_if_needed "$INSWAPPER" "$INSWAPPER_URL" "$INSWAPPER"
else
    echo "   inswapper_128.onnx vorhanden."
fi

if [[ $FORCE -eq 1 || ! -d "$BUFFALO_DIR" ]]; then
    download_if_needed "$BUFFALO_ZIP" "$BUFFALO_URL" "$BUFFALO_DIR"
    if [[ -f "$BUFFALO_ZIP" ]]; then
        echo "==> Entpacke buffalo_l.zip"
        if command -v unzip >/dev/null 2>&1; then
            mkdir -p "$BUFFALO_DIR"
            unzip -o "$BUFFALO_ZIP" -d "$BUFFALO_DIR"
            rm -f "$BUFFALO_ZIP"
        else
            echo "Fehler: unzip nicht verfügbar." >&2
            exit 1
        fi
    fi
else
    echo "   buffalo_l vorhanden."
fi

# ------------------------------------------------------------------- Icon
ICON="$ROOT/assets/icon.ico"
if [[ ! -f "$ICON" ]]; then
    echo "==> Erzeuge App-Icon"
    "$VENV_PYTHON" "$ROOT/tools/make_icon.py"
fi

# ------------------------------------------------------------------ Selbsttest
echo "==> Selbsttest"
"$VENV_PYTHON" -c "from faceswap.engine import FaceSwapEngine; e=FaceSwapEngine(); e.load(); print('Modelle geladen. Gerät:', e.active_device)"

echo ""
echo "Fertig! Starte die App mit ./start_gui.sh oder:"
echo "  $VENV_PYTHON faceswap_gui.py"
echo "  $VENV_PYTHON faceswap_cli.py --help"
