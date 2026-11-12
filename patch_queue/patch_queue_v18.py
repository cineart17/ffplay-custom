#!/usr/bin/env python3
# Update 18 for ffplay-custom (on top of patch_queue_v17.py).
#   * The bars above the seek line are all one color now: no part of them is drawn in your bar color to show how far
#     the song has played. They still bounce with the music and keep the shape of the track.
#   * The label on the disc is back to how it was in v13: a round, cropped piece of the cover that turns with the disc
#     (the squircle from v17 is gone).
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v17.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "NSQ" not in src:
    print("Already applied (or patch_queue_v17.py is missing). Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


def replace_between(start, end, new, label):
    """Replace everything from start (found once) up to and including end (found once, after start)."""
    global src
    if src.count(start) != 1 or src.count(end) != 1:
        print("FAILED:", label, "- start matched", src.count(start), "times, end matched", src.count(end),
              "times, expected 1 each. Nothing written.")
        sys.exit(1)
    a = src.index(start)
    b = src.index(end) + len(end)
    if b <= a:
        print("FAILED:", label, "- the end comes before the start. Nothing written.")
        sys.exit(1)
    src = src[:a] + new + src[b:]
    print("ok:", label)


# ============================================================ bars: one color, no progress

# the work out of how far the song has played is not needed any more
replace_between("        ui_layout(is, &sk, &vo);\n        if (is->ic && is->ic->duration > 0) {\n            double pos = get_master_clock(is);\n",
                "            frac = ui_seek_frac;\n        have = ui_wave_get(q_items[q_pos], wv);         /* the shape of the whole track, once it has been read */\n",
                "        ui_layout(is, &sk, &vo);\n"
                "        have = ui_wave_get(q_items[q_pos], wv);         /* the shape of the whole track, once it has been read */\n",
                "no progress calculation for the bars")

patch("        playx = sk.x + (int)(frac * sk.w);\n", "", "no playhead position")

patch("            if (bar.x < playx)\n"
      "                SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 235);\n"
      "            else\n"
      "                SDL_SetRenderDrawColor(renderer, 255, 255, 255, 90);\n",
      "            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 120);       /* every bar the same color */\n",
      "every bar one color")

# the two variables that are not used any more
patch("cx, cy, ci, nb, bw, maxh, base, playx;\n", "cx, cy, ci, nb, bw, maxh, base;\n", "drop the playhead variable")
patch("t = now / 1000000.0, frac = 0.0, pitch, amp;\n", "t = now / 1000000.0, pitch, amp;\n", "drop the progress variable")

# ============================================================ the disc label: back to the round, cropped piece

replace_between("    if (pic) {                                  /* the label: the whole cover squeezed into a squircle, turning with the disc */\n",
                "        SDL_RenderGeometry(renderer, pic, v, NSQ + 2, idx, NSQ * 3);\n    } else {\n",
                r'''    if (pic) {                                  /* the label: a piece of the cover, turning with the disc */
        SDL_Vertex v[34];
        int idx[32 * 3];
        SDL_Color w;

        w.r = 255;
        w.g = 255;
        w.b = 255;
        w.a = (Uint8)av_clip(a, 0, 255);
        SDL_SetTextureAlphaMod(pic, 255);
        SDL_SetTextureColorMod(pic, 255, 255, 255);
        v[0].position.x = (float)cx;
        v[0].position.y = (float)cy;
        v[0].color = w;
        v[0].tex_coord.x = 0.5f;
        v[0].tex_coord.y = 0.5f;
        for (i = 0; i <= 32; i++) {
            double an = i * two_pi / 32;

            v[i + 1].position.x = (float)(cx + r * lab * cos(an));
            v[i + 1].position.y = (float)(cy + r * lab * sin(an));
            v[i + 1].color = w;
            v[i + 1].tex_coord.x = (float)(0.5 + 0.34 * cos(an - ang));
            v[i + 1].tex_coord.y = (float)(0.5 + 0.34 * sin(an - ang));
        }
        for (i = 0; i < 32; i++) {
            idx[i * 3] = 0;
            idx[i * 3 + 1] = i + 1;
            idx[i * 3 + 2] = i + 2;
        }
        SDL_RenderGeometry(renderer, pic, v, 34, idx, 32 * 3);
    } else {
''', "the disc label is round and cropped again")

open(path, "w").write(src)
print("Patched", path)
