#!/usr/bin/env bash
# =============================================================================
# Oxx' FaceSwap - Kurzname fuer den GUI-Start (leitet an start_gui.sh weiter)
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

exec bash "$ROOT/start_gui.sh" "$@"
