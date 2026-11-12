#!/usr/bin/env bash
# Copy the current state of your build into this repo and refresh the patch.
# Usage: ./scripts/sync.sh [build folder]     (the build folder defaults to ~/build)
set -e

REPO=$(cd "$(dirname "$0")/.." && pwd)
BUILD=${1:-$HOME/build}
SRC="$BUILD/ffmpeg-6.1.1/fftools/ffplay.c"
TAR="$BUILD/ffmpeg-6.1.1.tar.xz"

if [ ! -f "$SRC" ] || [ ! -f "$TAR" ]; then
    echo "Could not find $SRC or $TAR"
    exit 1
fi

mkdir -p "$REPO/src/fftools" "$REPO/patches" "$REPO/patch_queue" "$REPO/tools"

# 1. The modified source file
cp "$SRC" "$REPO/src/fftools/ffplay.c"

# 2. One patch with every change against the original FFmpeg file
tar -xOf "$TAR" ffmpeg-6.1.1/fftools/ffplay.c > /tmp/ffplay.c.orig
diff -u --label a/fftools/ffplay.c --label b/fftools/ffplay.c /tmp/ffplay.c.orig "$SRC" > "$REPO/patches/ffplay-custom.patch" || true

# 3. Check that the patch applies to a clean copy
rm -rf /tmp/ptest && mkdir -p /tmp/ptest
tar -xf "$TAR" -C /tmp/ptest ffmpeg-6.1.1/fftools/ffplay.c
(cd /tmp/ptest/ffmpeg-6.1.1 && patch -p1 --dry-run < "$REPO/patches/ffplay-custom.patch")

# 4. The update scripts and the media controls helper, if they are there
cp -u "$BUILD"/patch_queue_v*.py "$REPO/patch_queue/" 2>/dev/null || true
if [ -f "$BUILD/ffplay-mpris" ]; then
    cp "$BUILD/ffplay-mpris" "$REPO/tools/ffplay-mpris"
fi

echo "Synced. Now add a line to CHANGELOG.md, then: git add -A && git commit"
