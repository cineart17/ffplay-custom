#!/usr/bin/env python3
# Update 7 for ffplay-custom.
#   * Audio files without cover art get a bubble party instead of the aurora: soft glowing bubbles in your bar
#     color float up the window, wobbling as they go. The louder the music, the faster they rise and the bigger
#     and brighter they glow; a sudden loud hit makes every bubble pop out a little (a beat pulse).
#     The waves view (key w) still works over it. The aurora code stays in the file, unused, so it is easy to bring back.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v6.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_bubble_backdrop" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_aurora_backdrop" not in src or "ui_q_anim_t0" not in src:
    print("Apply patch_queue_v6.py first. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


patch("static int ui_aurora_backdrop(VideoState *is);\n",
      "static int ui_aurora_backdrop(VideoState *is) av_unused;\nstatic int ui_bubble_backdrop(VideoState *is);\n",
      "bubble declaration")

patch("    if (ui_aurora_backdrop(s) && s->show_mode == SHOW_MODE_RDFT)\n",
      "    if (ui_bubble_backdrop(s) && s->show_mode == SHOW_MODE_RDFT)\n",
      "bubbles replace the aurora")

patch("static SDL_Texture *ui_make_target(int w, int h)\n{\n",
      r'''/* ----- the bubble party: the backdrop for audio without cover art -----
   Soft glowing bubbles in your bar color float up the window. The loudness of the music makes them rise faster and
   glow bigger; a sudden loud hit (a beat) makes them all pop out for a moment. */
static int ui_bubble_backdrop(VideoState *is)
{
    enum { NB = 26, NSEG = 20 };
    static SDL_Vertex v[NB * (NSEG + 1)];
    static int idx[NB * NSEG * 3];
    static int idx_ready = 0;
    static double drift = 0.0, last_t = 0.0;
    static float lvl = 0.0f, slow = 0.0f, pulse = 0.0f;
    double t = av_gettime_relative() / 1000000.0, dt, h0, s0, v0;
    int W = is->width, H = is->height, i, k, j;
    double m;
    SDL_Color c;
    SDL_Rect bg;

    if (!is->audio_st || ui_has_cover(is) || W <= 0 || H <= 0)
        return 0;
    if (!idx_ready) {
        for (i = 0, k = 0; i < NB; i++)
            for (j = 0; j < NSEG; j++) {
                idx[k++] = i * (NSEG + 1);
                idx[k++] = i * (NSEG + 1) + 1 + j;
                idx[k++] = i * (NSEG + 1) + 1 + (j + 1) % NSEG;
            }
        idx_ready = 1;
    }
    dt = last_t > 0.0 ? av_clipd(t - last_t, 0.0, 0.1) : 0.0;
    last_t = t;
    if (is->paused)
        dt = 0.0;
    lvl += ((is->paused ? 0.0f : av_clipf(is->level * 4.0f, 0.0f, 1.0f)) - lvl) * 0.2f;
    slow += (lvl - slow) * 0.04f;
    pulse = FFMAX(0.0f, pulse - (float)dt * 2.2f);
    if (lvl - slow > 0.10f && pulse < 0.4f)
        pulse = 1.0f;                                   /* a sudden loud hit: the bubbles pop out */
    drift += dt * (0.04 + 0.20 * lvl);

    ui_rgb2hsv(cfg_bar_r, cfg_bar_g, cfg_bar_b, &h0, &s0, &v0);
    s0 = av_clipd(FFMAX(s0, 0.55), 0.0, 1.0);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    ui_hsv2rgb(h0, s0 * 0.8, 0.05 + 0.08 * lvl + 0.10 * pulse, &c);
    SDL_SetRenderDrawColor(renderer, c.r, c.g, c.b, 255);
    bg.x = 0;
    bg.y = 0;
    bg.w = W;
    bg.h = H;
    SDL_RenderFillRect(renderer, &bg);

    m = FFMIN(W, H);
    for (i = 0; i < NB; i++) {
        double r1 = fmod(i * 0.61803398875, 1.0);
        double r2 = fmod(i * 0.38196601125 + 0.17, 1.0);
        double r3 = fmod(i * 0.7548776662, 1.0);
        double life = fmod(drift * (0.6 + 0.8 * r1) + r2, 1.0);
        double x = W * (0.05 + 0.90 * r3 + 0.04 * sin(t * (0.5 + r1) + i * 1.7));
        double y = H * (1.1 - 1.2 * life);
        double rad = m * (0.05 + 0.09 * r2) * (0.8 + 0.5 * lvl + 0.6 * pulse);
        double alpha = av_clipd(sin(3.14159265 * life) * (0.35 + 0.45 * lvl + 0.30 * pulse), 0.0, 0.85);
        SDL_Vertex *p = &v[i * (NSEG + 1)];

        ui_hsv2rgb(h0 + 0.14 * sin(i * 0.9) + 0.06 * r1 + 0.03 * sin(t * 0.2), s0, 0.95, &c);
        p->position.x = (float)x;
        p->position.y = (float)y;
        p->color = c;
        p->color.a = (Uint8)(alpha * 255);              /* strong in the middle... */
        p->tex_coord.x = 0;
        p->tex_coord.y = 0;
        for (j = 0; j < NSEG; j++) {
            double a = j * 2.0 * 3.14159265 / NSEG;

            p = &v[i * (NSEG + 1) + 1 + j];
            p->position.x = (float)(x + rad * cos(a));
            p->position.y = (float)(y + rad * sin(a));
            p->color = c;
            p->color.a = 0;                             /* ...and gone at the edge: a soft glow */
            p->tex_coord.x = 0;
            p->tex_coord.y = 0;
        }
    }
    SDL_RenderGeometry(renderer, NULL, v, NB * (NSEG + 1), idx, NB * NSEG * 3);
    return 1;
}

static SDL_Texture *ui_make_target(int w, int h)
{
''', "the bubbles")

open(path, "w").write(src)
print("Patched", path)
