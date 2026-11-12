#!/usr/bin/env python3
# Update 20 for ffplay-custom (on top of patch_queue_v19.py; it works on any earlier state too).
#   * Adds a short notice under the license header of ffplay.c saying that this is a modified version of FFmpeg's
#     ffplay.c, who modified it and when. The LGPL asks for this in modified files. The original license header
#     stays exactly as it is.
#   * Nothing in how the player looks or works changes.
# Run from inside ~/build/ffmpeg-6.1.1.
# Writes the file only if the spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ffplay-custom: this is a modified version" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)

old = """ * Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
 */

/**
 * @file
 * simple media player based on the FFmpeg libraries
 */
"""

new = """ * Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
 */

/*
 * ffplay-custom: this is a modified version of fftools/ffplay.c from FFmpeg 6.1.1.
 * Modified by Cine, first changed in 2026 (the dates of later changes are in the git history of the
 * ffplay-custom repository, and the list of changes is in its CHANGELOG.md).
 * It is still licensed under the GNU Lesser General Public License, version 2.1 or later, like the original.
 */

/**
 * @file
 * simple media player based on the FFmpeg libraries
 */
"""

n = src.count(old)
if n != 1:
    print("FAILED: the license header - matched", n, "times, expected 1. Nothing written.")
    sys.exit(1)
src = src.replace(old, new)
print("ok: modification notice under the license header")

open(path, "w").write(src)
print("Patched", path)
