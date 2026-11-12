#!/usr/bin/env python3
# Update 5 for ffplay-custom.
#   * Open File... / Open Folder... in the menu, like files opened from outside (the file manager, "Open with"),
#     now ADD to the queue while something is playing. When nothing is playing, they start right away.
#   * The menu boxes have no visible border: they float. A deeper soft shadow and a faint haze of light
#     around the edge lift them off the picture instead of a line.
#   * The glass is tinted very slightly with your bar color.
#   * The row under the mouse gets a small dot in the bar color (there are no boxes behind text).
#   * When the menu opens, its rows fade and slide in one after another.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v4b.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_menu_anim_t0" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_label_c(p.x + p.w / 2, fy + 100" not in src:
    print("Apply patch_queue_v4.py and patch_queue_v4b.py first. Nothing written.")
    sys.exit(1)


def fail(label, why):
    print("FAILED:", label, "-", why, "Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        fail(label, "matched %d times, expected 1." % n)
    src = src.replace(old, new)
    print("ok:", label)


def patch_between(start, end, new, label):
    global src
    if src.count(start) != 1:
        fail(label, "start matched %d times, expected 1." % src.count(start))
    a = src.index(start)
    b = src.find(end, a + len(start))
    if b < 0 or src.count(end) != 1:
        fail(label, "end matched %d times, expected 1." % src.count(end))
    src = src[:a] + new + src[b:]
    print("ok:", label)


# ---- opening while something plays adds to the queue

patch("""        if (line[0] == 'o' && !opened) {
            queue_clear();          /* open now: start a fresh queue */
            opened = 1;
        }
""", """        if (line[0] == 'o' && !opened && !is) {
            queue_clear();          /* nothing is playing: open now, with a fresh queue */
            opened = 1;
        }                           /* while something plays, an 'o' is added to the queue like an 'a' */
""", "opening while something plays adds to the queue")

# ---- borderless glass that floats

patch("        e.y = t->y - i * 3 + 6;\n", "        e.y = t->y - i * 3 + 10;\n", "deeper shadow")
patch("""        SDL_SetRenderDrawColor(renderer, 0, 0, 0, 7);
        ui_rr_fill(&e, r + i * 3);
    }
}
""", """        SDL_SetRenderDrawColor(renderer, 0, 0, 0, 7);
        ui_rr_fill(&e, r + i * 3);
    }
    for (i = 4; i >= 1; i--) {      /* a faint haze of light at the edge, in place of a line: the panel floats */
        e.x = t->x - i * 2;
        e.y = t->y - i * 2;
        e.w = t->w + i * 4;
        e.h = t->h + i * 4;
        SDL_SetRenderDrawColor(renderer, 255, 255, 255, 3);
        ui_rr_fill(&e, r + i * 2);
    }
}
""", "light haze")

patch("        SDL_SetRenderDrawColor(renderer, 12, 14, 20, 118);\n",
      "        SDL_SetRenderDrawColor(renderer, 10 + cfg_bar_r / 12, 12 + cfg_bar_g / 12, 18 + cfg_bar_b / 12, 118);\n",
      "glass tinted with the bar color")

patch_between("        if (row == 1 && t->h > 12) {                    /* a thin highlight just inside the top edge */",
              "    }\n}\n\n/* The idle background: a few soft glows",
              "", "no border lines")

patch("    int row, run = -1, inset, piece, top3;\n", "    int row, run = -1, inset, top3;\n", "unused variable")

# ---- the row under the mouse: a small dot

patch("    SDL_Rect r, card, row;\n    int ww, wh, i, pad, cy, lit;\n\n    if (ui_prefs_open || (!ui_idle && !ui_menu_open))\n        return;\n",
      """    SDL_Rect r, card, row, dot;
    static int was_shown = 0;
    int ww, wh, i, pad, cy, lit, shown = ui_menu_open && !ui_idle;
    double k;

    if (shown && !was_shown)
        ui_menu_anim_t0 = av_gettime_relative();     /* the rows fade in from this moment */
    was_shown = shown;
    if (ui_prefs_open || (!ui_idle && !ui_menu_open))
        return;
""", "menu: variables and the start of the fade-in")

patch("""        ui_label(row.x + 28, cy, ui_menu_label[i], 22, 240, 240, 240, lit ? 255 : 205);
        if (i == UI_ROW_OPEN || i == UI_ROW_QUEUE || i == UI_ROW_INFO)
            ui_chevron(row.x + r.w - 22, cy, lit ? 255 : 170);
""", """        k = ui_idle ? 1.0 : av_clipd((av_gettime_relative() - ui_menu_anim_t0 - i * 40000) / 180000.0, 0.0, 1.0);
        k = 1.0 - (1.0 - k) * (1.0 - k) * (1.0 - k);        /* ease out: quick, then settling */
        ui_label(row.x + 28 + (int)((1.0 - k) * 10), cy, ui_menu_label[i], 22, 240, 240, 240,
                 (int)((lit ? 255 : 205) * k));
        if (i == UI_ROW_OPEN || i == UI_ROW_QUEUE || i == UI_ROW_INFO)
            ui_chevron(row.x + r.w - 22, cy, (int)((lit ? 255 : 170) * k));
        if (lit) {                  /* a small dot marks the row under the mouse */
            dot.x = row.x + 11;
            dot.y = cy - 3;
            dot.w = 6;
            dot.h = 6;
            SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                                   av_clip(cfg_bar_b + 40, 0, 255), (int)(235 * k));
            ui_pill(&dot);
        }
""", "menu: rows fade in, dot on the hovered row")

patch("""        ui_label(p.x + 28, row_y + UI_MENU_ROW / 2, i ? "Folder..." : "File...", 22, 240, 240, 240,
                 i == ui_open_hover ? 255 : 205);
""", """        ui_label(p.x + 28, row_y + UI_MENU_ROW / 2, i ? "Folder..." : "File...", 22, 240, 240, 240,
                 i == ui_open_hover ? 255 : 205);
        if (i == ui_open_hover) {
            SDL_Rect dot = { p.x + 11, row_y + UI_MENU_ROW / 2 - 3, 6, 6 };

            SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                                   av_clip(cfg_bar_b + 40, 0, 255), 235);
            ui_pill(&dot);
        }
""", "Open choices: dot on the hovered row")

patch("""        ui_label(r.x + 28, row_y + UI_CTX_ROW / 2, ui_ctx_label(i), 20, 240, 240, 240,
                 i == ui_ctx_hover ? 255 : 205);
""", """        ui_label(r.x + 28, row_y + UI_CTX_ROW / 2, ui_ctx_label(i), 20, 240, 240, 240,
                 i == ui_ctx_hover ? 255 : 205);
        if (i == ui_ctx_hover) {
            SDL_Rect dot = { r.x + 11, row_y + UI_CTX_ROW / 2 - 3, 6, 6 };

            SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                                   av_clip(cfg_bar_b + 40, 0, 255), 235);
            ui_pill(&dot);
        }
""", "item menu: dot on the hovered row")

# ---- keep redrawing while the rows fade in

patch("static int ui_q_hover_idx = -1;     /* ... and which item or choice */\n",
      "static int ui_q_hover_idx = -1;     /* ... and which item or choice */\n"
      "static int64_t ui_menu_anim_t0 = 0; /* when the popup menu opened (its rows fade in from then) */\n",
      "fade-in start time")
patch("    if (ui_q_open && (ui_menu_open || ui_idle) && (second != last_second || seen_gen != q_dur_gen)) {\n",
      "    if (ui_menu_open && !ui_idle && av_gettime_relative() - ui_menu_anim_t0 < 600000)\n"
      "        is->force_refresh = 1;                  /* the rows are still fading in */\n"
      "    if (ui_q_open && (ui_menu_open || ui_idle) && (second != last_second || seen_gen != q_dur_gen)) {\n",
      "redraw while the rows fade in")

open(path, "w").write(src)
print("Patched", path)
