#!/usr/bin/env bash
# ffplay-custom-install
# Installs ffplay-custom for the current user: the player, the media-controls helper, the app-menu launcher and the logo.
# Run it after ./scripts/build.sh.
# Usage: ./scripts/install.sh [work folder]     (the work folder defaults to ~/ffplay-custom-build, where build.sh builds;
#                                                give ~/build if that is where you built)
set -e

VER=6.1.1
REPO=$(cd "$(dirname "$0")/.." && pwd)
WORK=${1:-$HOME/ffplay-custom-build}
BIN="$WORK/ffmpeg-$VER/ffplay"
CONF="$HOME/.config/ffplay-custom"
LOGO="$CONF/logo.png"

if [ ! -x "$BIN" ]; then
    echo "There is no built player at $BIN."
    echo "Run ./scripts/build.sh first, or give the folder you built in: ./scripts/install.sh ~/build"
    exit 1
fi
if [ ! -f "$REPO/assets/logo.png" ]; then
    echo "assets/logo.png is missing from the repository."
    exit 1
fi

mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications" "$CONF"

cp --remove-destination "$BIN" "$HOME/.local/bin/ffplay-custom"
install -m 755 "$REPO/tools/ffplay-mpris" "$HOME/.local/bin/ffplay-mpris"
echo "Installed the player and the media-controls helper in $HOME/.local/bin"

# The logo is copied only when there is none yet, so a logo you changed yourself is kept
if [ ! -f "$LOGO" ]; then
    cp "$REPO/assets/logo.png" "$LOGO"
    echo "Installed the logo: $LOGO"
else
    echo "Kept the logo that is already there: $LOGO"
fi

cat > "$HOME/.local/share/applications/ffplay-custom.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=ffplay-custom
Comment=Custom ffplay media player
Exec=$HOME/.local/bin/ffplay-custom %F
TryExec=$HOME/.local/bin/ffplay-custom
Icon=$LOGO
Terminal=false
Categories=AudioVideo;Audio;Video;Player;
MimeType=audio/mpeg;audio/flac;audio/mp4;audio/x-m4a;audio/ogg;audio/opus;audio/x-opus+ogg;video/mp4;video/x-matroska;video/webm;
EOF
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
echo "Added ffplay-custom to the app menu."

case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) echo "Note: $HOME/.local/bin is not on your PATH yet. Log out and back in once, or run: export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac
echo "Done."

# Create application launcher and Desktop shortcut on first install
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$DESKTOP_DIR"
cat << 'DESK' > "$DESKTOP_DIR/ffplay-custom.desktop"
[Desktop Entry]
Type=Application
Name=ffplay-custom
Comment=Custom media player based on FFmpeg and SDL2
Exec=ffplay-custom %U
Icon=$HOME/.config/ffplay-custom/logo.png
Terminal=false
Categories=AudioVideo;Player;
DESK
sed -i "s|\$HOME|$HOME|g" "$DESKTOP_DIR/ffplay-custom.desktop"
if [ -d "$HOME/Desktop" ] && [ ! -f "$HOME/Desktop/ffplay-custom.desktop" ]; then
    cp "$DESKTOP_DIR/ffplay-custom.desktop" "$HOME/Desktop/ffplay-custom.desktop"
    chmod +x "$HOME/Desktop/ffplay-custom.desktop"
fi
