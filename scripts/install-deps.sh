#!/usr/bin/env bash
# Installs what ffplay-custom needs on Ubuntu or elementary OS (apt).
#
#   ./scripts/install-deps.sh          everything: to build the player and to run it
#   ./scripts/install-deps.sh --run    only what is needed to run a finished build
#
# It asks for your password once (sudo). See REQUIREMENTS.md for what each package is for.

set -e

RUN_PKGS="zenity fontconfig fonts-dejavu-core libsdl2-2.0-0 libsdl2-ttf-2.0-0 libdav1d7 python3 python3-gi gir1.2-glib-2.0"
BUILD_PKGS="build-essential pkg-config nasm libsdl2-dev libsdl2-ttf-dev libdav1d-dev xz-utils curl patch diffutils git unzip"

if ! command -v apt-get >/dev/null 2>&1; then
    echo "This script is for apt-based systems (Ubuntu, elementary OS, Debian)."
    echo "On another system, install the equivalents of: $RUN_PKGS $BUILD_PKGS"
    exit 1
fi

if [ "$1" = "--run" ]; then
    PKGS="$RUN_PKGS"
else
    PKGS="$RUN_PKGS $BUILD_PKGS"
fi

echo "Installing: $PKGS"
sudo apt-get update
sudo apt-get install -y $PKGS

echo
echo "Checking the tools the player calls while it runs:"
for tool in zenity fc-match python3; do
    if command -v "$tool" >/dev/null 2>&1; then
        echo "  ok       $tool"
    else
        echo "  MISSING  $tool"
    fi
done
if python3 -c "import gi" >/dev/null 2>&1; then
    echo "  ok       python3-gi"
else
    echo "  MISSING  python3-gi (the desktop media controls need it)"
fi
echo "Done."
