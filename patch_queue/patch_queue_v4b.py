#!/usr/bin/env python3
# Follow-up to patch_queue_v4.py:
#   * The queue counter ("1/179   [1:23:36 / 2:13:14]") is centred in the panel.
#   * The menu options are left-aligned again: the main menu, the Open choices and the item menu.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v4.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_mpris_tick" not in src:
    print("Apply patch_queue_v4.py first. Nothing written.")
    sys.exit(1)
if "ui_label_c(p.x + p.w / 2, fy + 100" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


patch("    ui_label(p.x + 20, fy + 100, text, 15, 170, 170, 170, 255);\n",
      "    ui_label_c(p.x + p.w / 2, fy + 100, text, 15, 170, 170, 170, 255);\n",
      "counter centred")

patch("""        if (i == UI_ROW_QUEUE || i == UI_ROW_INFO)
            ui_label(row.x + 28, cy, ui_menu_label[i], 22, 240, 240, 240, lit ? 255 : 205);
        else
            ui_label_c(row.x + row.w / 2, cy, ui_menu_label[i], 22, 240, 240, 240, lit ? 255 : 205);
""", """        ui_label(row.x + 28, cy, ui_menu_label[i], 22, 240, 240, 240, lit ? 255 : 205);
""", "menu rows left-aligned")

patch("""        ui_label_c(p.x + p.w / 2, row_y + UI_MENU_ROW / 2, i ? "Folder..." : "File...", 22, 240, 240, 240,
                   i == ui_open_hover ? 255 : 205);
""", """        ui_label(p.x + 28, row_y + UI_MENU_ROW / 2, i ? "Folder..." : "File...", 22, 240, 240, 240,
                 i == ui_open_hover ? 255 : 205);
""", "Open choices left-aligned")

patch("""        ui_label_c(r.x + r.w / 2, row_y + UI_CTX_ROW / 2, ui_ctx_label(i), 20, 240, 240, 240,
                   i == ui_ctx_hover ? 255 : 205);
""", """        ui_label(r.x + 28, row_y + UI_CTX_ROW / 2, ui_ctx_label(i), 20, 240, 240, 240,
                 i == ui_ctx_hover ? 255 : 205);
""", "item menu left-aligned")

open(path, "w").write(src)
print("Patched", path)
