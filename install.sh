#!/usr/bin/env bash
set -euo pipefail

REPO="ryz3nplayz/dctl"
INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/dctl"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { printf "${GREEN}[dctl]${NC} %s\n" "$1"; }
warn()  { printf "${YELLOW}[dctl]${NC} %s\n" "$1"; }
error() { printf "${RED}[dctl]${NC} %s\n" "$1" >&2; exit 1; }

need() {
    if ! command -v "$1" &>/dev/null; then
        error "$1 is required but not found. Install it and re-run."
    fi
}

need python3
need git
need pip

python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" || {
    error "Python 3.11+ is required (found $(python3 --version))."
}

# Decide source: local repo or clone from GitHub
if [ -f "$(dirname "$0")/pyproject.toml" ] && grep -q 'name = "dctl"' "$(dirname "$0")/pyproject.toml" 2>/dev/null; then
    SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
    info "Installing from local source: $SOURCE_DIR"
else
    SOURCE_DIR="$INSTALL_DIR/src"
    if [ -d "$SOURCE_DIR/.git" ]; then
        info "Updating existing clone..."
        git -C "$SOURCE_DIR" pull --ff-only || warn "git pull failed, using existing source"
    else
        info "Cloning $REPO..."
        rm -rf "$SOURCE_DIR"
        git clone "https://github.com/${REPO}.git" "$SOURCE_DIR"
    fi
fi

# Create or reuse venv
if [ -d "$INSTALL_DIR/venv" ]; then
    info "Reusing existing virtual environment"
else
    info "Creating virtual environment..."
    python3 -m venv "$INSTALL_DIR/venv"
fi

VENV_PYTHON="$INSTALL_DIR/venv/bin/python"

# Install
info "Installing dctl..."
"$VENV_PYTHON" -m pip install -q --upgrade pip
"$VENV_PYTHON" -m pip install -q "$SOURCE_DIR"

# Symlink
mkdir -p "$BIN_DIR"
ln -sf "$INSTALL_DIR/venv/bin/dctl" "$BIN_DIR/dctl"

# Verify
if "$BIN_DIR/dctl" capabilities &>/dev/null; then
    VERSION=$("$BIN_DIR/dctl" --version 2>/dev/null || echo "installed")
    info "dctl $VERSION installed successfully"
    info "Binary: $BIN_DIR/dctl"
else
    warn "dctl installed but 'dctl capabilities' failed. Check dependencies with: dctl doctor"
fi

# PATH check
case ":${PATH}:" in
    *":$BIN_DIR:"*) ;;
    *) warn "$BIN_DIR is not in PATH. Add it with:
         echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.bashrc && source ~/.bashrc" ;;
esac
