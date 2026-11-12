#!/usr/bin/env python3
# Update 15 for ffplay-custom (on top of patch_queue_v14.py).
#   * Each side cover turns by its own amount (about half to one and a half times the usual tilt, fixed per place in the
#     queue so a cover keeps its angle as the row glides), and its width and title follow its angle.
#   * The faint vertical frame around the covers is gone. It was the old rectangular shadow, which no longer matched
#     a tilted cover. The shadow is now the cover's own shape, soft, black and a little bigger, so it follows the tilt.
#   * The waveform bars move with the music again: they keep the shape of the whole track, and each bar bounces with
#     the loudness ripple that travels across them like before. Paused, they hold still in the track's shape.
#   * Fixes the compiler warning from v14 (a declaration in the middle of the code).
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v14.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "double tl[11]" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_wave_scan" not in src:
    print("Apply patch_queue_v14.py first. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


def replace_function(start_marker, new_text, label):
    global src
    if src.count(start_marker) != 1:
        print("FAILED:", label, "- start matched", src.count(start_marker), "times, expected 1. Nothing written.")
        sys.exit(1)
    a = src.index(start_marker)
    b = src.index("\n}\n", a) + 3
    src = src[:a] + new_text + src[b:]
    print("ok:", label)


# ============================================================ declarations at the top (fixes the warning)

patch("    SDL_Rect sk, vo, tile, bar;\n    char name[320], num[48];\n    int al, md;\n",
      "    SDL_Rect sk, vo, tile, bar;\n    char name[320], num[48];\n    int al, md, have, b0, b1, q;\n    float wv[UI_WAVE_N];\n",
      "declarations at the top")

patch("        float wv[UI_WAVE_N];\n        int have, b0, b1, q;\n\n        have = ui_wave_get(q_items[q_pos], wv);",
      "        have = ui_wave_get(q_items[q_pos], wv);",
      "no declarations in the middle")

# ============================================================ each cover turns by its own amount

patch("        SDL_Rect ui_flow_rects[11], cut, dcl;\n        int ok[11];\n",
      "        SDL_Rect ui_flow_rects[11], cut, dcl;\n        double tl[11];\n        int ok[11];\n",
      "tilt table")

patch("            ui_flow_rects[e].w = (int)(s * (1.0 - 0.14 * FFMIN(ad, 1.0)));      /* a turned cover is narrower */\n",
      "            tl[e] = av_clipd(d, -1.0, 1.0) * (0.45 + 1.1 * fmod(i * 0.61803398875 + 0.3, 1.0));    /* each cover turns a little differently */\n"
      "            ui_flow_rects[e].w = (int)(s * (1.0 - 0.14 * fabs(tl[e])));         /* a turned cover is narrower */\n",
      "an angle for each cover")

patch("ui_flow_tile(i, &tile, (ui_flow_dragging && i == ui_flow_press) ? al / 3 : al, md, av_clipd(d, -1.0, 1.0));",
      "ui_flow_tile(i, &tile, (ui_flow_dragging && i == ui_flow_press) ? al / 3 : al, md, tl[e]);",
      "covers use their own angle")

patch("ui_flow_title(name, 15, vx0 + vw / 2, &tile, av_clipd(d, -1.0, 1.0), al * 55 / 100);",
      "ui_flow_title(name, 15, vx0 + vw / 2, &tile, tl[e], al * 55 / 100);",
      "titles use their cover's angle")

# ============================================================ shadows that follow the card

patch("                if (ad < 1.5)\n                    ui_shadow(&tile, tile.w / 11);\n", "", "no rectangular shadow behind covers")
patch("        ui_shadow(&g, g.w / 11);\n", "", "no rectangular shadow behind the cover in hand")

replace_function("static void ui_flow_tile(int idx, const SDL_Rect *tile, int al, int md, double tilt)", r'''static void ui_flow_tile(int idx, const SDL_Rect *tile, int al, int md, double tilt)
{
    SDL_Texture *tex;
    SDL_Rect sh;
    int cw = 0, ch = 0, k;

    tex = ui_cov_get(q_items[idx], &cw, &ch);
    if (tex) {                                  /* a soft shadow in the card's own shape: the picture again, black and bigger */
        for (k = 3; k >= 1; k--) {
            sh.x = tile->x - k * 4;
            sh.y = tile->y - k * 4 + 7;
            sh.w = tile->w + k * 8;
            sh.h = tile->h + k * 8;
            ui_flow_quad(tex, &sh, al * 16 / 255, 0, tilt);
        }
    } else {
        tex = ui_flow_icon();                   /* no picture (yet): the file icon */
    }
    if (tex)
        ui_flow_quad(tex, tile, al, md, tilt);
}
''', "a shadow that follows the card")

# ============================================================ the waveform moves again

patch("""            if (have) {
                b0 = j * UI_WAVE_N / nb;
                b1 = FFMAX((j + 1) * UI_WAVE_N / nb, b0 + 1);
                amp = 0.0;
                for (q = b0; q < b1 && q < UI_WAVE_N; q++)
                    amp = FFMAX(amp, wv[q]);
                if (FFABS(sk.x + (int)(j * pitch) - playx) < 3 * pitch)       /* a little pulse at the playhead */
                    amp = FFMIN(1.0, amp * (1.0 + 0.35 * lvl));
            } else {""", """            if (have) {                                 /* the shape of the whole track, bouncing with the music */
                b0 = j * UI_WAVE_N / nb;
                b1 = FFMAX((j + 1) * UI_WAVE_N / nb, b0 + 1);
                amp = 0.0;
                for (q = b0; q < b1 && q < UI_WAVE_N; q++)
                    amp = FFMAX(amp, wv[q]);
                if (is->paused)
                    amp *= 0.9;                         /* paused: it holds still */
                else                                    /* the loudness ripple travels across the bars, as before */
                    amp = FFMIN(1.0, amp * 1.2 * (0.55 + 0.45 * fabs(sin(j * 2.3 + t * 3.7))) * (0.40 + 0.90 * eq[j * NEQ / nb]));
            } else {""", "bars bounce with the music")

open(path, "w").write(src)
print("Patched", path)
