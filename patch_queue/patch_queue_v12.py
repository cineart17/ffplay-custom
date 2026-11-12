#!/usr/bin/env python3
# Update 12 for ffplay-custom (on top of patch_queue_v11.py).
#   * The equaliser bars above the seek bar have rounded tops and bottoms, like the seek bar.
#   * The spinning disc takes its color from the cover (the cover's average color, made a bit richer and kept
#     away from pure black and white). It is a solid disc now, with grooves a little darker and lighter than it,
#     and its label is a round piece of the cover that turns with the disc.
#   * The disc is a little smaller and sits further out, so its label shows. The covers to the right of the middle
#     one move out a bit to make room for it.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v11.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_cov_tone" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_flow_rects" not in src:
    print("Apply patch_queue_v11.py first. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


# ============================================================ rounded equaliser bars

patch("""                SDL_SetRenderDrawColor(renderer, 255, 255, 255, 90);
            SDL_RenderFillRect(renderer, &bar);
""", """                SDL_SetRenderDrawColor(renderer, 255, 255, 255, 90);
            ui_rr_fill(&bar, bw / 2);           /* rounded top and bottom, like the seek bar */
""", "rounded equaliser bars")

# ============================================================ the average color of every cover

patch("""    int cw, ch;                 /* the size of the picture inside it (smaller on one side if it was a video frame) */
    SDL_Texture *tex;
} UiCov;
""", """    int cw, ch;                 /* the size of the picture inside it (smaller on one side if it was a video frame) */
    int tr, tg, tb;             /* the average color of the picture, for the disc */
    SDL_Texture *tex;
} UiCov;
""", "average color field")

patch("""            av_freep(&c->px);
            c->state = c->tex ? 2 : 3;
""", """            {                                   /* the average color (the see-through corners are skipped) */
                long sr = 0, sg = 0, sb = 0, cnt = 0;
                int q;

                for (q = 0; q < c->w * c->h; q += 3) {
                    const uint8_t *p = c->px + q * 4;

                    if (p[3] > 200) {
                        sr += p[0];
                        sg += p[1];
                        sb += p[2];
                        cnt++;
                    }
                }
                c->tr = cnt ? (int)(sr / cnt) : 40;
                c->tg = cnt ? (int)(sg / cnt) : 40;
                c->tb = cnt ? (int)(sb / cnt) : 40;
            }
            av_freep(&c->px);
            c->state = c->tex ? 2 : 3;
""", "work out the average color")

# ============================================================ ask for the disc color and the picture

patch("""/* A filled slice of a circle (a pie) in one color */
""", """/* The picture of a file, if it is ready, and the color for its disc: its average color, a bit richer, and not too dark
   or too light. Without a picture the color comes from your bar color. */
static SDL_Texture *ui_cov_tone(const char *path, SDL_Color *dc)
{
    SDL_Texture *t = NULL;
    double h, s, v;
    int i, r = cfg_bar_r / 2, g = cfg_bar_g / 2, b = cfg_bar_b / 2;

    dc->a = 255;
    if (path && ui_cov_mu) {
        SDL_LockMutex(ui_cov_mu);
        for (i = 0; i < ui_cov_n; i++)
            if (!strcmp(ui_cov[i].path, path)) {
                if (ui_cov[i].state == 2) {
                    t = ui_cov[i].tex;
                    r = ui_cov[i].tr;
                    g = ui_cov[i].tg;
                    b = ui_cov[i].tb;
                }
                break;
            }
        SDL_UnlockMutex(ui_cov_mu);
        if (t) {
            ui_rgb2hsv(r, g, b, &h, &s, &v);
            ui_hsv2rgb(h, FFMIN(s * 1.3, 0.85), av_clipd(v * 1.1, 0.40, 0.78), dc);
            return t;
        }
    }
    dc->r = (Uint8)r;
    dc->g = (Uint8)g;
    dc->b = (Uint8)b;
    return NULL;
}

/* A filled slice of a circle (a pie) in one color */
""", "ask for the disc color")

# ============================================================ the disc

patch("""/* The spinning disc: dark grooves, light turning across them, and a label in your bar color */
static void ui_flow_disc(double cx, double cy, double r, double ang, int a)
{
    const double two_pi = 6.28318531, pi = 3.14159265;
    double k;
    int i;

    ui_fan(cx, cy, r, 0, two_pi, 48, 16, 16, 20, a);
    for (k = 0.94, i = 0; k > 0.45; k -= 0.08, i++)
        ui_fan(cx, cy, r * k, 0, two_pi, 48, i % 2 ? 30 : 12, i % 2 ? 30 : 12, i % 2 ? 36 : 15, a);
    ui_fan(cx, cy, r * 0.97, ang, ang + 0.55, 8, 255, 255, 255, a * 26 / 255);
    ui_fan(cx, cy, r * 0.97, ang + pi, ang + pi + 0.55, 8, 255, 255, 255, a * 26 / 255);
    ui_fan(cx, cy, r * 0.34, 0, two_pi, 32, cfg_bar_r, cfg_bar_g, cfg_bar_b, a);
    ui_fan(cx + cos(ang) * r * 0.2, cy + sin(ang) * r * 0.2, r * 0.05, 0, two_pi, 12, 245, 245, 245, a);
    ui_fan(cx, cy, r * 0.05, 0, two_pi, 12, 14, 14, 18, a);
}
""", """/* The spinning disc: solid, in a color from the cover, with grooves, light turning across it, and a label that is a
   round piece of the cover turning with the disc (pic is NULL while the cover is not ready) */
static void ui_flow_disc(double cx, double cy, double r, double ang, int a, SDL_Texture *pic, SDL_Color base)
{
    const double two_pi = 6.28318531, pi = 3.14159265;
    double k, f;
    int i;

    ui_fan(cx, cy, r, 0, two_pi, 48, base.r, base.g, base.b, a);                /* the solid disc */
    for (k = 0.94, i = 0; k > 0.45; k -= 0.08, i++) {                           /* grooves: rings a little lighter and darker */
        f = i % 2 ? 0.84 : 1.08;
        ui_fan(cx, cy, r * k, 0, two_pi, 48, FFMIN((int)(base.r * f), 255), FFMIN((int)(base.g * f), 255),
               FFMIN((int)(base.b * f), 255), a);
    }
    ui_fan(cx, cy, r * 0.97, ang, ang + 0.55, 8, 255, 255, 255, a * 40 / 255);  /* light turning across the grooves */
    ui_fan(cx, cy, r * 0.97, ang + pi, ang + pi + 0.55, 8, 255, 255, 255, a * 40 / 255);
    ui_fan(cx, cy, r * 0.37, 0, two_pi, 32, base.r * 6 / 10, base.g * 6 / 10, base.b * 6 / 10, a);    /* rim of the label */
    if (pic) {                                  /* the label: the middle of the cover, turning with the disc */
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

            v[i + 1].position.x = (float)(cx + r * 0.34 * cos(an));
            v[i + 1].position.y = (float)(cy + r * 0.34 * sin(an));
            v[i + 1].color = w;
            v[i + 1].tex_coord.x = (float)(0.5 + 0.2 * cos(an - ang));
            v[i + 1].tex_coord.y = (float)(0.5 + 0.2 * sin(an - ang));
        }
        for (i = 0; i < 32; i++) {
            idx[i * 3] = 0;
            idx[i * 3 + 1] = i + 1;
            idx[i * 3 + 2] = i + 2;
        }
        SDL_RenderGeometry(renderer, pic, v, 34, idx, 32 * 3);
    } else {
        ui_fan(cx, cy, r * 0.34, 0, two_pi, 32, cfg_bar_r, cfg_bar_g, cfg_bar_b, a);
    }
    ui_fan(cx, cy, r * 0.05, 0, two_pi, 12, 14, 14, 18, a);                     /* the hole in the middle */
}
""", "solid disc with a cover label")

patch("""                    if (dcl.w > 0) {
                        SDL_RenderSetClipRect(renderer, &dcl);
                        ui_flow_disc(tile.x + s * 0.78, cy, s * 0.47, ui_flow_ang, al);
                        SDL_RenderSetClipRect(renderer, &cut);
""", """                    if (dcl.w > 0) {
                        SDL_Color dcol;
                        SDL_Texture *dpic = ui_cov_tone(q_items[i], &dcol);

                        SDL_RenderSetClipRect(renderer, &dcl);
                        ui_flow_disc(tile.x + s * 1.08, cy, s * 0.35, ui_flow_ang, al, dpic, dcol);
                        SDL_RenderSetClipRect(renderer, &cut);
""", "draw the disc with its color and label")

# ============================================================ more room on the right for the disc

patch("(d > 0 ? B * 0.30 * FFMIN(d, 1.0) : 0.0);    /* the right side leaves room for the disc */",
      "(d > 0 ? B * 0.40 * FFMIN(d, 1.0) : 0.0);    /* the right side leaves room for the disc */",
      "more room for the disc")

open(path, "w").write(src)
print("Patched", path)
