#!/usr/bin/env bash
# ============================================================
#   Vedika Mascot — Linux Setup & Launcher
#   Run this script ONCE on each Linux machine.
#   Usage:  bash setup_linux.sh
# ============================================================
set -e

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   Vedika AI Mascot — Linux Setup     ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. System dependencies ──────────────────────────────────
echo "→ Installing system packages (requires sudo)..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-pip python3-venv \
    espeak espeak-data libespeak-dev \
    portaudio19-dev python3-pyaudio \
    libqt5webengine5 python3-pyqt5 python3-pyqt5.qtwebengine \
    libglib2.0-0 libxcb-xinerama0 libxcb-icccm4 libxcb-image0 \
    libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-xkb1 \
    libxkbcommon-x11-0 libegl1-mesa \
    2>/dev/null || echo "⚠ Some packages may not have installed (non-Ubuntu system?)"

echo "✓ System packages done."
echo ""

# ── 2. Python venv ───────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "→ Creating Python virtual environment at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
echo "✓ Virtual environment active."
echo ""

# ── 3. Python packages ──────────────────────────────────────
echo "→ Installing Python packages..."
pip install --quiet --upgrade pip
pip install --quiet \
    PyQt5 \
    PyQtWebEngine \
    pyttsx3 \
    SpeechRecognition \
    pyaudio \
    google-genai

echo "✓ Python packages installed."
echo ""

# ── 4. Launch Vedika ─────────────────────────────────────────
echo "→ Starting Vedika..."
echo ""
cd "$SCRIPT_DIR"

# Qt WebEngine needs these on Linux
export QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-dev-shm-usage"
export QT_XCB_GL_INTEGRATION=none

python3 main.py
