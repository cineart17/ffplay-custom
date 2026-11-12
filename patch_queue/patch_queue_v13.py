#!/usr/bin/env python3
# Update 13 for ffplay-custom (on top of patch_queue_v12.py).
#   * The spinning disc: its center now sits on the cover's right edge, so only a semicircle sticks out. The label,
#     the part with the album art, is much bigger (nearly all of the disc, with a thin band of grooves around it)
#     and shows a larger piece of the cover.
#   * The covers on both sides tilt like in your reference: the edge nearest the middle is shorter, as if it turns
#     away. The tilt is worked out from each cover's place in the row, so it eases in and out as the row glides
#     and as you swipe or drag.
#   * To make the tilt possible the file icon is now a picture too (made once, remade if the bar color changes),
#     so every cover is drawn the same way.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v12.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_flow_quad" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_cov_tone" not in src:
    print("Apply patch_queue_v12.py first. Nothing written.")
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
    """Replace from start_marker (found once) to the end of that function (the first line that is just a closing brace)."""
    global src
    if src.count(start_marker) != 1:
        print("FAILED:", label, "- start matched", src.count(start_marker), "times, expected 1. Nothing written.")
        sys.exit(1)
    a = src.index(start_marker)
    b = src.index("\n}\n", a) + 3
    src = src[:a] + new_text + src[b:]
    print("ok:", label)


# ============================================================ the disc

replace_function("/* The spinning disc:", r'''/* The spinning disc: solid, in a color from the cover, with a few grooves, light turning across it, and a big label that
   is a round piece of the cover turning with the disc (pic is NULL while the cover is not ready) */
static void ui_flow_disc(double cx, double cy, double r, double ang, int a, SDL_Texture *pic, SDL_Color base)
{
    const double two_pi = 6.28318531, pi = 3.14159265, lab = 0.74;      /* the label is nearly all of the disc */
    double k, f;
    int i;

    ui_fan(cx, cy, r, 0, two_pi, 48, base.r, base.g, base.b, a);                /* the solid disc */
    for (k = 0.95, i = 0; k > lab + 0.03; k -= 0.05, i++) {                     /* grooves in the band around the label */
        f = i % 2 ? 0.84 : 1.08;
        ui_fan(cx, cy, r * k, 0, two_pi, 48, FFMIN((int)(base.r * f), 255), FFMIN((int)(base.g * f), 255),
               FFMIN((int)(base.b * f), 255), a);
    }
    ui_fan(cx, cy, r * 0.97, ang, ang + 0.55, 8, 255, 255, 255, a * 40 / 255);  /* light turning across the grooves */
    ui_fan(cx, cy, r * 0.97, ang + pi, ang + pi + 0.55, 8, 255, 255, 255, a * 40 / 255);
    ui_fan(cx, cy, r * (lab + 0.025), 0, two_pi, 40, base.r * 6 / 10, base.g * 6 / 10, base.b * 6 / 10, a);   /* rim of the label */
    if (pic) {                                  /* the label: a piece of the cover, turning with the disc */
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
        ui_fan(cx, cy, r * lab, 0, two_pi, 40, cfg_bar_r, cfg_bar_g, cfg_bar_b, a);
    }
    ui_fan(cx, cy, r * 0.035, 0, two_pi, 12, 14, 14, 18, a);                    /* the hole in the middle */
}
''', "a big label on the disc")

patch("                        ui_flow_disc(tile.x + s * 1.08, cy, s * 0.35, ui_flow_ang, al, dpic, dcol);\n",
      "                        ui_flow_disc(tile.x + s, cy, s * 0.42, ui_flow_ang, al, dpic, dcol);     /* centered on the cover's edge: a semicircle shows */\n",
      "the disc's place: a semicircle")

# ============================================================ the file icon becomes a picture; covers are drawn tilted

patch("static void ui_flow_note(const SDL_Rect *t, int al, int md)\n{",
      "static void av_unused ui_flow_note(const SDL_Rect *t, int al, int md)\n{",
      "the old icon drawing is kept, unused")

replace_function("static void ui_flow_tile(int idx, const SDL_Rect *tile, int al, int md)", r'''/* The file icon as a picture, made once: a frosted tile in your bar color with an orange music note, rounded corners.
   Remade if the bar color changes. */
static SDL_Texture *ui_flow_icon(void)
{
    enum { S = 256 };
    static SDL_Texture *tex = NULL;
    static int key = -1;
    static const double qx[4] = { 43, 77, 77, 43 }, qy[4] = { 28, 20, 29, 37 };     /* the beam, clockwise */
    int k = (cfg_bar_r << 16) | (cfg_bar_g << 8) | cfg_bar_b, x, y, e;
    double u = S / 100.0, rr = S / 11.0, a1 = 0.43, a2 = 0.43, A, C[3], tint[3];
    uint8_t *px;

    if (tex && key == k)
        return tex;
    px = av_malloc((size_t)S * S * 4);
    if (!px)
        return tex;
    tint[0] = cfg_bar_r;
    tint[1] = cfg_bar_g;
    tint[2] = cfg_bar_b;
    A = a2 + a1 * (1.0 - a2);                   /* a haze of white, then your bar color, over nothing */
    for (e = 0; e < 3; e++)
        C[e] = (tint[e] * a2 + 255.0 * a1 * (1.0 - a2)) / A;
    for (y = 0; y < S; y++)
        for (x = 0; x < S; x++) {
            double fx = x + 0.5, fy = y + 0.5, nc, c, af, corner = 1.0, mn, d;
            double ox = 233, og = 104, ob = 36;
            uint8_t *p = px + ((size_t)y * S + x) * 4;

            nc = av_clipd(9 * u - hypot(fx - 36 * u, fy - 70 * u) + 0.5, 0.0, 1.0);          /* the two note heads */
            c = av_clipd(9 * u - hypot(fx - 66 * u, fy - 64 * u) + 0.5, 0.0, 1.0);
            nc = FFMAX(nc, c);
            mn = FFMIN(FFMIN(fx - 43 * u, 46.6 * u - fx), FFMIN(fy - 30 * u, 70 * u - fy));  /* the two stems */
            nc = FFMAX(nc, av_clipd(mn + 0.5, 0.0, 1.0));
            mn = FFMIN(FFMIN(fx - 73 * u, 76.6 * u - fx), FFMIN(fy - 23 * u, 64 * u - fy));
            nc = FFMAX(nc, av_clipd(mn + 0.5, 0.0, 1.0));
            mn = 1e9;                                   /* the beam joining the stems */
            for (e = 0; e < 4; e++) {
                double px0 = qx[e] * u, py0 = qy[e] * u, px1 = qx[(e + 1) % 4] * u, py1 = qy[(e + 1) % 4] * u;

                d = -((fx - px0) * (py1 - py0) - (fy - py0) * (px1 - px0)) / hypot(px1 - px0, py1 - py0);
                mn = FFMIN(mn, d);
            }
            nc = FFMAX(nc, av_clipd(mn + 0.5, 0.0, 1.0));
            af = nc + A * (1.0 - nc);
            p[0] = (uint8_t)((ox * nc + C[0] * A * (1.0 - nc)) / af);
            p[1] = (uint8_t)((og * nc + C[1] * A * (1.0 - nc)) / af);
            p[2] = (uint8_t)((ob * nc + C[2] * A * (1.0 - nc)) / af);
            if ((x < rr || x >= S - rr) && (y < rr || y >= S - rr)) {                   /* the rounded corners */
                double kx = x < rr ? rr : S - rr, ky = y < rr ? rr : S - rr;

                corner = av_clipd(rr - hypot(fx - kx, fy - ky) + 0.5, 0.0, 1.0);
            }
            p[3] = (uint8_t)(255.0 * af * corner);
        }
    if (tex)
        SDL_DestroyTexture(tex);
    tex = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STATIC, S, S);
    if (tex) {
        SDL_UpdateTexture(tex, NULL, px, S * 4);
        SDL_SetTextureBlendMode(tex, SDL_BLENDMODE_BLEND);
        key = k;
    }
    av_free(px);
    return tex;
}

/* A picture drawn as a slightly turned card: the edge nearest the middle of the row is shorter (tilt is -1 for the covers
   on the left, +1 on the right, 0 in the middle, and every value between while the row glides) */
static void ui_flow_quad(SDL_Texture *tex, const SDL_Rect *t, int al, int md, double tilt)
{
    enum { NS = 16 };
    SDL_Vertex v[(NS + 1) * 2];
    int idx[NS * 6], k;
    double cyt = t->y + t->h / 2.0, kin = 1.0 - 0.16 * fabs(tilt);
    SDL_Color c;

    c.r = (Uint8)md;
    c.g = (Uint8)md;
    c.b = (Uint8)md;
    c.a = (Uint8)av_clip(al, 0, 255);
    for (k = 0; k <= NS; k++) {
        double u = (double)k / NS;              /* 0 at the left edge, 1 at the right */
        double f = tilt < 0 ? 1.0 - (1.0 - kin) * u : tilt > 0 ? kin + (1.0 - kin) * u : 1.0;
        double hh = t->h * f / 2.0;

        v[k * 2].position.x = (float)(t->x + t->w * u);
        v[k * 2].position.y = (float)(cyt - hh);
        v[k * 2].color = c;
        v[k * 2].tex_coord.x = (float)u;
        v[k * 2].tex_coord.y = 0.0f;
        v[k * 2 + 1].position.x = (float)(t->x + t->w * u);
        v[k * 2 + 1].position.y = (float)(cyt + hh);
        v[k * 2 + 1].color = c;
        v[k * 2 + 1].tex_coord.x = (float)u;
        v[k * 2 + 1].tex_coord.y = 1.0f;
    }
    for (k = 0; k < NS; k++) {
        idx[k * 6] = k * 2;
        idx[k * 6 + 1] = k * 2 + 1;
        idx[k * 6 + 2] = k * 2 + 2;
        idx[k * 6 + 3] = k * 2 + 1;
        idx[k * 6 + 4] = k * 2 + 3;
        idx[k * 6 + 5] = k * 2 + 2;
    }
    SDL_RenderGeometry(renderer, tex, v, (NS + 1) * 2, idx, NS * 6);
}

static void ui_flow_tile(int idx, const SDL_Rect *tile, int al, int md, double tilt)
{
    SDL_Texture *tex;
    int cw = 0, ch = 0;

    tex = ui_cov_get(q_items[idx], &cw, &ch);
    if (!tex)
        tex = ui_flow_icon();                   /* no picture (yet): the file icon */
    if (tex)
        ui_flow_quad(tex, tile, al, md, tilt);
}
''', "covers drawn tilted, the file icon as a picture")

patch("                ui_flow_tile(i, &tile, (ui_flow_dragging && i == ui_flow_press) ? al / 3 : al, md);\n",
      "                ui_flow_tile(i, &tile, (ui_flow_dragging && i == ui_flow_press) ? al / 3 : al, md, av_clipd(d, -1.0, 1.0));\n",
      "tilt follows each cover's place")

patch("        ui_flow_tile(ui_flow_press, &g, 235, 255);",
      "        ui_flow_tile(ui_flow_press, &g, 235, 255, 0.0);",
      "the cover in hand is flat")

open(path, "w").write(src)
print("Patched", path)
