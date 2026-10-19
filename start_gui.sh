#!/usr/bin/env bash
# =============================================================================
# Oxx' FaceSwap - GUI starten (Shell-Skript / Linux, macOS, Git Bash)
#
#   ./start_gui.sh        # ohne Konsolenfenster (wenn möglich)
#   ./start_gui.sh debug  # mit Konsole (zeigt Fehlermeldungen)
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON="$ROOT/.venv/bin/python"
APP="faceswap_gui.py"

if [[ ! -x "$PYTHON" ]]; then
    echo "[Fehler] Keine virtuelle Umgebung gefunden."
    echo "         Bitte einmalig ./install.sh ausfuehren."
    exit 1
fi

if [[ ! -f "models/inswapper_128.onnx" ]]; then
    echo "[Warnung] Die Modelle fehlen."
    echo "          Bitte einmalig ./install.sh ausfuehren."
fi
if [[ ! -d "models/buffalo_l" ]]; then
    echo "[Warnung] Das Erkennungsmodell buffalo_l fehlt."
    echo "          Bitte einmalig ./install.sh ausfuehren."
fi

mkdir -p output

if [[ "${1:-}" == "debug" ]]; then
    exec "$PYTHON" "$APP"
fi

# pythonw gibt es unter Linux/macOS nicht; dort einfach python verwenden
exec "$PYTHON" "$APP"
