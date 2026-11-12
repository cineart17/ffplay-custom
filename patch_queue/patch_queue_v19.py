#!/usr/bin/env python3
# Update 19 for ffplay-custom (on top of patch_queue_v18.py).
#   * The bars are dimmer again, the same as the old unplayed bars (white at alpha 90).
#   * The bars now stretch across the whole window, from the left side to the right side, so they also sit above the
#     volume bar. They keep a small gap (24 px, the same as the controls) at both ends of the window.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v18.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "int x0 = 24, span = W - 48;" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "every bar the same color" not in src:
    print("Apply patch_queue_v18.py first. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


# ============================================================ dimmer bars

patch("            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 120);       /* every bar the same color */\n",
      "            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 90);        /* every bar the same color, as dim as the old unplayed bars */\n",
      "dimmer bars")

# ============================================================ across the whole window

patch("    {                                           /* the bars above the seek bar are always shown, even when the seek bar hides */\n"
      "        ui_layout(is, &sk, &vo);\n",
      "    {                                           /* the bars are always shown, from the left of the window to the right */\n"
      "        int x0 = 24, span = W - 48;             /* where the bars start, and how wide they spread */\n\n"
      "        ui_layout(is, &sk, &vo);\n",
      "where the bars start and how wide they are")

patch("        nb = FFMAX(sk.w / 14, 24);\n        pitch = (double)sk.w / nb;\n",
      "        nb = FFMAX(span / 14, 24);\n        pitch = (double)span / nb;\n",
      "the number of bars follows the window")

patch("            bar.x = sk.x + (int)(j * pitch);\n            bar.h = 3 + (int)(amp * maxh);\n",
      "            bar.x = x0 + (int)(j * pitch);\n            bar.h = 3 + (int)(amp * maxh);\n",
      "bars start at the left of the window")

open(path, "w").write(src)
print("Patched", path)
