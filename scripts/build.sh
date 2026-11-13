#!/usr/bin/env bash
# Build ffplay-custom: download FFmpeg 6.1.1, apply our patch, compile.
# Usage: ./scripts/build.sh [work folder]     (the work folder defaults to ~/ffplay-custom-build)
# It never touches ~/build, where you may keep a working tree of your own.
set -e

VER=6.1.1
REPO=$(cd "$(dirname "$0")/.." && pwd)
WORK=${1:-$HOME/ffplay-custom-build}

mkdir -p "$WORK"
cd "$WORK"

# Download FFmpeg once
if [ ! -f "ffmpeg-$VER.tar.xz" ]; then
    curl -L -o "ffmpeg-$VER.tar.xz" "https://ffmpeg.org/releases/ffmpeg-$VER.tar.xz"
fi

# Start from a clean copy of the source
rm -rf "ffmpeg-$VER"
tar -xf "ffmpeg-$VER.tar.xz"
cd "ffmpeg-$VER"

# Apply our changes to fftools/ffplay.c
patch -p1 < "$REPO/patches/ffplay-custom.patch"

# Same configure line as always
./configure --disable-programs --enable-ffplay --disable-doc --enable-libdav1d

# ffplay.c draws its text with SDL2_ttf. FFmpeg's configure does not know about it, so add it to the link line
sed -i 's/^EXTRALIBS-ffplay=.*/& -lSDL2_ttf/' ffbuild/config.mak
if ! grep -q 'SDL2_ttf' ffbuild/config.mak; then
    echo "Could not add SDL2_ttf to the link line (ffbuild/config.mak)."
    exit 1
fi

make -j"$(nproc)"

echo "Built: $WORK/ffmpeg-$VER/ffplay"
