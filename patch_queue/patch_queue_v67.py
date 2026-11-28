#!/usr/bin/env python3
# patch_queue_v67.py - on top of v66
#  1. tiled view, two rows (and the search sections): tiles closer together and bigger
#  2. miniplayer: the music tiles scroll freely with the wheel / two-finger swipe and settle on the nearest item
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "fftools/ffplay.c"
src = open(path, encoding="utf-8").read()
done = 0
skipped = 0


def patch(old, new, what):
    global src, done, skipped
    if new in src:
        skipped += 1
        print("already: " + what)
        return
    n = src.count(old)
    if n != 1:
        print("FAILED: %s (found %d times)" % (what, n))
        sys.exit(1)
    src = src.replace(old, new)
    done += 1
    print("ok: " + what)


# ---- 1. spacing and size of the tiles ----------------------------------------------------------------------------------
patch("    int sm;                                     /* a small window: smaller titles */\n} UiTvRow;",
      "    int sm;                                     /* a small window: smaller titles */\n"
      "    double pitch;                               /* v67: pixels from one tile's middle to the next (0 = the old sw * 1.08) */\n} UiTvRow;",
      "row struct: pitch")

patch("    double pitch = R->sw * 1.08;\n",
      "    double pitch = R->pitch > 0.0 ? R->pitch : R->sw * 1.08;     /* v67: set by the caller, closer than before */\n",
      "row draw: pitch from the caller")

patch("        sc = 1.0 - 0.26 * (d < 1.0 ? d * d * (3.0 - 2.0 * d) : 1.0) - 0.035 * FFMIN(FFMAX(d - 1.0, 0.0), 4.0);",
      "        sc = 1.0 - 0.18 * (d < 1.0 ? d * d * (3.0 - 2.0 * d) : 1.0) - 0.03 * FFMIN(FFMAX(d - 1.0, 0.0), 4.0);     /* v67: the others shrink less */",
      "tiles shrink less with distance")

patch("(int)(pitch * (d < 0.6 ? 1.9 : 1.05)),",
      "(int)(pitch * (d < 0.6 ? 1.9 : 0.96)),",
      "titles of neighbours do not run into each other")

patch("        sh = av_clipd(FFMIN(FFMIN(rp * 0.74, rp - 46.0), W * 0.24), 40.0, 340.0);      /* v38: bigger */",
      "        sh = av_clipd(FFMIN(FFMIN(rp * 0.80, rp - 44.0), W * 0.27), 40.0, 400.0);      /* v67: bigger again */",
      "two rows: bigger tiles")

patch("            row.sh = (int)sh;\n            row.rowd = fabs(rr - ui_tv_row);\n",
      "            row.sh = (int)sh;\n            row.pitch = row.sw * 0.88;                              /* v67: was 1.08: the gap between tiles is about a twelfth of a tile */\n"
      "            row.rowd = fabs(rr - ui_tv_row);\n",
      "two rows: closer tiles")

patch("            row.sh = sh;\n            row.rowd = s == ui_tv_act ? 0.0 : 0.45;\n",
      "            row.sh = sh;\n"
      "            {                                                       /* v67: the spacing follows the shape of the tiles in the section (covers are square, videos are wide) */\n"
      "                double am = 1.0;\n"
      "                int ai;\n"
      "\n"
      "                for (ai = 0; ai < FFMIN(sec->n, 12); ai++) {\n"
      "                    double a = ui_cov_aspect(sec->h[ai].path);\n"
      "\n"
      "                    if (a > am)\n"
      "                        am = a;\n"
      "                }\n"
      "                row.pitch = sh * (0.8 * av_clipd(am, 1.0, 1.78) + 0.17);\n"
      "            }\n"
      "            row.rowd = s == ui_tv_act ? 0.0 : 0.45;\n",
      "search sections: spacing by tile shape")

# ---- 2. miniplayer: the music tiles scroll ---------------------------------------------------------------------------
patch("static int64_t ui_flow_touch = 0;       /* when the row was last swiped */\n",
      "static int64_t ui_flow_touch = 0;       /* when the row was last swiped */\n"
      "static double ui_flow_free = 0.0;       /* v67: miniplayer: where the fingers have taken the row (between two items) */\n"
      "static int ui_flow_free_on = 0, ui_flow_free_q = -1;\n"
      "static int64_t ui_flow_free_t = 0;\n",
      "free scroll state")

patch("    ui_flow_pos += (ui_flow_target - ui_flow_pos) * (1.0 - exp(-dt * 10.0));\n"
      "    ui_flow_moving = fabs(ui_flow_target - ui_flow_pos) > 0.003;\n"
      "    if (!ui_flow_moving)\n"
      "        ui_flow_pos = ui_flow_target;\n",
      "    if (ui_flow_free_on && q_pos != ui_flow_free_q)\n"
      "        ui_flow_free_on = 0;                    /* v67: a new item started: the row glides to it */\n"
      "    if (ui_flow_free_on && now - ui_flow_free_t > 160000) {     /* v67: the fingers are off: the row settles on the nearest item */\n"
      "        ui_flow_target = av_clip((int)floor(ui_flow_free + 0.5), 0, q_count - 1);\n"
      "        ui_flow_free_on = 0;\n"
      "    }\n"
      "    if (ui_flow_free_on) {                      /* v67: the row follows the fingers, item by item and in between */\n"
      "        double fg = av_clipd(ui_flow_free, 0.0, q_count - 1);\n"
      "\n"
      "        ui_flow_pos += (fg - ui_flow_pos) * (1.0 - exp(-dt * 18.0));\n"
      "        ui_flow_moving = 1;\n"
      "    } else {\n"
      "        ui_flow_pos += (ui_flow_target - ui_flow_pos) * (1.0 - exp(-dt * 10.0));\n"
      "        ui_flow_moving = fabs(ui_flow_target - ui_flow_pos) > 0.003;\n"
      "        if (!ui_flow_moving)\n"
      "            ui_flow_pos = ui_flow_target;\n"
      "    }\n",
      "draw: the row follows the fingers")

patch("    if (now - last > 300000 || amount * acc < 0.0)\n        acc = 0.0;\n    last = now;\n    acc += amount;\n    steps = (int)acc;\n    if (!steps)\n        return;\n    acc -= steps;\n    if (ui_flow_target < 0)\n",
      "    if (ui_pip) {                               /* v67: the miniplayer's music tiles scroll freely (wheel, two fingers, either way) and settle on an item */\n"
      "        if (!ui_flow_free_on) {\n"
      "            ui_flow_free = ui_flow_pos;\n"
      "            ui_flow_free_on = 1;\n"
      "        }\n"
      "        ui_flow_free = av_clipd(ui_flow_free + amount, 0.0, q_count - 1);\n"
      "        ui_flow_free_t = now;\n"
      "        ui_flow_free_q = q_pos;\n"
      "        ui_flow_target = av_clip((int)floor(ui_flow_free + 0.5), 0, q_count - 1);\n"
      "        ui_flow_touch = now;\n"
      "        is->force_refresh = 1;\n"
      "        return;\n"
      "    }\n"
      "    if (now - last > 300000 || amount * acc < 0.0)\n        acc = 0.0;\n    last = now;\n    acc += amount;\n    steps = (int)acc;\n    if (!steps)\n        return;\n    acc -= steps;\n    if (ui_flow_target < 0)\n",
      "swipe: free scrolling in the miniplayer")

open(path, "w", encoding="utf-8").write(src)
print("Done: %d changes" % done if done else "Already applied")
