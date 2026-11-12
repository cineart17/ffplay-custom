#!/usr/bin/env python3
# Update 17 for ffplay-custom (on top of patch_queue_v15.py; it works with or without patch_queue_v16.py).
#   * The bars above the seek line are always shown now, even when the seek bar and cursor hide.
#   * The bars no longer get flat tops. They used to be pushed past their top limit in loud parts, so every loud bar
#     was cut off at the same height and a row of them looked like a rectangle. Now the loudness is shaped by a soft
#     curve (nothing is cut off), the bounce never makes a bar taller than the song's own shape, and the bars have
#     more height to use (up to 90 px, was 70).
#   * The label on the disc shows the whole cover, squeezed into a squircle that fits inside the disc, instead of a
#     cropped piece. It still turns with the disc.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v15.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "NSQ" in src:
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


# ============================================================ the bars are always shown

patch("    if (!(cursor_hidden && !is->paused)) {      /* the bars above the seek bar come and go with it */\n",
      "    {                                           /* the bars above the seek bar are always shown, even when the seek bar hides */\n",
      "bars always visible")

# ============================================================ no flat tops

# a soft curve instead of cutting the loud stretches off at the top
patch("        bins[i] = (float)pow(av_clipd(bins[i] / mx, 0.0, 1.0), 0.8);\n",
      "        bins[i] = (float)(1.0 - exp(-1.5 * bins[i] / mx));      /* a soft curve: louder is always a little taller, nothing is cut off */\n",
      "a soft curve for the loudness")

# more room to grow
patch("        maxh = FFMIN(70, H / 8);\n",
      "        maxh = FFMIN(90, H / 6);                        /* the tallest a bar can be */\n",
      "taller bars allowed")

# the bounce only makes a bar a little shorter than the song's own shape, never taller, so no bar hits the ceiling
patch("                    amp = FFMIN(1.0, amp * 1.2 * (0.55 + 0.45 * fabs(sin(j * 2.3 + t * 3.7))) * (0.40 + 0.90 * eq[j * NEQ / nb]));\n",
      "                    amp = amp * (0.70 + 0.30 * fabs(sin(j * 2.3 + t * 3.7))) * (0.60 + 0.40 * eq[j * NEQ / nb]);\n",
      "the bounce never pushes a bar past its shape")

# ============================================================ the whole cover on the disc label, in a squircle

replace_between("    if (pic) {                                  /* the label: a piece of the cover, turning with the disc */\n",
                "        SDL_RenderGeometry(renderer, pic, v, 34, idx, 32 * 3);\n    } else {\n",
                r'''    if (pic) {                                  /* the label: the whole cover squeezed into a squircle, turning with the disc */
        enum { NSQ = 64 };
        SDL_Vertex v[NSQ + 2];
        int idx[NSQ * 3];
        SDL_Color w;
        double half = r * lab * 0.86, ca = cos(ang), sa = sin(ang);     /* half the squircle's width: it fits inside the label */

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
        for (i = 0; i <= NSQ; i++) {
            double an = i * two_pi / NSQ, c = cos(an), s = sin(an);
            double sx = c < 0 ? -sqrt(fabs(c)) : sqrt(fabs(c));         /* a point on the squircle: x^4 + y^4 = 1 */
            double sy = s < 0 ? -sqrt(fabs(s)) : sqrt(fabs(s));

            v[i + 1].position.x = (float)(cx + half * (sx * ca - sy * sa));     /* turned by the disc's angle */
            v[i + 1].position.y = (float)(cy + half * (sx * sa + sy * ca));
            v[i + 1].color = w;
            v[i + 1].tex_coord.x = (float)(0.5 + 0.5 * sx);                     /* the whole picture, edge to edge */
            v[i + 1].tex_coord.y = (float)(0.5 + 0.5 * sy);
        }
        for (i = 0; i < NSQ; i++) {
            idx[i * 3] = 0;
            idx[i * 3 + 1] = i + 1;
            idx[i * 3 + 2] = i + 2;
        }
        SDL_RenderGeometry(renderer, pic, v, NSQ + 2, idx, NSQ * 3);
    } else {
''', "the whole cover in a squircle on the disc")

open(path, "w").write(src)
print("Patched", path)
