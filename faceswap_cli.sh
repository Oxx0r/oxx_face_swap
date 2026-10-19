#!/usr/bin/env bash
# =============================================================================
# Oxx' FaceSwap - Kommandozeilen-Version (Shell-Skript / Linux, macOS, Git Bash)
#
#   ./faceswap_cli.sh                              # zeigt die Hilfe
#   ./faceswap_cli.sh --source spender.jpg --target ziel.jpg
#   ./faceswap_cli.sh -s spender.jpg -t gruppe.jpg --face 2,4 -o fertig.jpg
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON="$ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    echo "Bitte zuerst ./install.sh ausfuehren."
    exit 1
fi

exec "$PYTHON" faceswap_cli.py "$@"
