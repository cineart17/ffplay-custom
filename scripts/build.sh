#!/usr/bin/env bash
# Build ffplay-custom: download FFmpeg 6.1.1, apply our patch, compile.
# Usage: ./scripts/build.sh [work folder]     (the work folder defaults to ~/build)
set -e

VER=6.1.1
REPO=$(cd "$(dirname "$0")/.." && pwd)
WORK=${1:-$HOME/build}

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

# Same configure line as always, then build
./configure --disable-programs --enable-ffplay --disable-doc --enable-libdav1d
make -j"$(nproc)"

echo "Built: $WORK/ffmpeg-$VER/ffplay"
