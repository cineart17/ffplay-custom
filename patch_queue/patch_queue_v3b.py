#!/usr/bin/env python3
# Follow-up to patch_queue_v3.py:
#   * The queue counter updates the moment a file length is found (no more waiting for the next second tick).
#   * Chapter marks on the seek bar are small glowing dots sitting in the bar, not tall vertical ticks.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v3.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "q_dur_gen" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_ctx_open" not in src:
    print("Apply patch_queue_v3.py first. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


# ---- real-time counter
patch("static SDL_cond *q_dur_cv = NULL;\n",
      "static SDL_cond *q_dur_cv = NULL;\nstatic volatile int q_dur_gen = 0;          /* goes up every time a file length is found */\n",
      "length generation counter")
patch("            q_dur[q_dur_n].secs = secs;\n            q_dur_n++;\n",
      "            q_dur[q_dur_n].secs = secs;\n            q_dur_n++;\n            q_dur_gen++;\n",
      "count each new length")
patch("    static int st_unknown = 0;\n",
      "    static int st_unknown = 0, st_gen = -1;\n", "counter: remember which lengths it has seen")
patch("    if (now - stats_at > 400000 || now < stats_at) {\n",
      "    if (st_gen != q_dur_gen || now - stats_at > 400000 || now < stats_at) {\n        st_gen = q_dur_gen;\n",
      "counter: add up again as soon as a length arrives")
patch("    static int64_t last_second = 0;\n    int64_t second = av_gettime_relative() / 1000000;\n\n"
      "    if (ui_q_open && (ui_menu_open || ui_idle) && second != last_second) {\n        last_second = second;\n",
      "    static int64_t last_second = 0;\n    static int seen_gen = -1;\n    int64_t second = av_gettime_relative() / 1000000;\n\n"
      "    if (ui_q_open && (ui_menu_open || ui_idle) && (second != last_second || seen_gen != q_dur_gen)) {\n"
      "        last_second = second;\n        seen_gen = q_dur_gen;\n",
      "redraw as soon as a length arrives")

# ---- chapter dots
patch("""/* Little ticks on the seek bar where chapters start */
static void ui_chapter_ticks(VideoState *is, const SDL_Rect *sk)
{""", """/* Chapter marks: small glowing dots sitting in the seek bar where chapters start */
static void ui_chapter_ticks(VideoState *is, const SDL_Rect *sk)
{""", "chapter marks: name")
patch("""    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 150);
    for (i = 1; i < is->ic->nb_chapters; i++) {
        f = ui_chapter_start(is, i) / dur;
        if (f <= 0.005 || f >= 0.995)
            continue;
        t.w = 2;
        t.h = sk->h + 8;
        t.x = sk->x + (int)(f * sk->w) - 1;
        t.y = sk->y - 4;
        SDL_RenderFillRect(renderer, &t);
    }
""", """    for (i = 1; i < is->ic->nb_chapters; i++) {
        int d = FFMAX(sk->h - 2, 4), cx, cy, k;

        f = ui_chapter_start(is, i) / dur;
        if (f <= 0.005 || f >= 0.995)
            continue;
        cx = sk->x + (int)(f * sk->w);
        cy = sk->y + sk->h / 2;
        for (k = 2; k >= 0; k--) {          /* two faint halos, then the bright core */
            int size = d + k * 4;

            t.w = size;
            t.h = size;
            t.x = cx - size / 2;
            t.y = cy - size / 2;
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, k == 2 ? 28 : k == 1 ? 55 : 235);
            ui_pill(&t);
        }
    }
""", "chapter marks: glowing dots")

open(path, "w").write(src)
print("Patched", path)
