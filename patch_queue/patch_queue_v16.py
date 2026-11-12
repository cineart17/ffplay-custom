#!/usr/bin/env python3
# Update 16 for ffplay-custom (on top of patch_queue_v15.py).
#   * The black dot (the hole) in the middle of the disc is gone.
#   * No black shadows anywhere: under the menus and panels (the glass ones, the queue panel, the preferences),
#     under floating text (the seek tooltip, the toast messages), behind the volume number, and around the covers
#     in the on screen queue. The faint haze of light at the edge of a panel is not a black shadow and stays.
#   * All of it is one switch, ui_shadows_on, near the top of the file. Set it to 1 and rebuild to bring the shadows back.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v15.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_shadows_on" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "double tl[11]" not in src:
    print("Apply patch_queue_v15.py first. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


patch("    ui_fan(cx, cy, r * 0.035, 0, two_pi, 12, 14, 14, 18, a);                    /* the hole in the middle */\n", "",
      "no black dot on the disc")

patch("/* Text with a soft shadow under it, for text that floats over the picture without a box */\n",
      "static int ui_shadows_on = 0;       /* 1 = black shadows under panels, floating text, the volume number and the covers; 0 = none */\n\n"
      "/* Text with a soft shadow under it, for text that floats over the picture without a box */\n",
      "the shadow switch")

patch("    ui_label(x + 1, cy + 2, s, px, 0, 0, 0, a * 150 / 255);\n    ui_label(x, cy, s, px, r, g, b, a);\n",
      "    if (ui_shadows_on)\n        ui_label(x + 1, cy + 2, s, px, 0, 0, 0, a * 150 / 255);\n    ui_label(x, cy, s, px, r, g, b, a);\n",
      "no shadow under floating text")

patch("    ui_label(vo.x + vo.w + 11, vo.y + vo.h / 2 + 1, buf, 15, 0, 0, 0, 150);\n",
      "    if (ui_shadows_on)\n        ui_label(vo.x + vo.w + 11, vo.y + vo.h / 2 + 1, buf, 15, 0, 0, 0, 150);\n",
      "no shadow behind the volume number")

patch("    for (i = 6; i >= 1; i--) {\n        e.x = t->x - i * 3;\n",
      "    for (i = ui_shadows_on ? 6 : 0; i >= 1; i--) {         /* the black shadow (skipped when the switch is off) */\n        e.x = t->x - i * 3;\n",
      "no shadow under panels")

patch("        for (k = 3; k >= 1; k--) {\n            sh.x = tile->x - k * 4;\n",
      "        for (k = ui_shadows_on ? 3 : 0; k >= 1; k--) {\n            sh.x = tile->x - k * 4;\n",
      "no shadow around the covers")

open(path, "w").write(src)
print("Patched", path)
