#!/usr/bin/env python3
# Update 6 for ffplay-custom.
#   * Audio files without cover art get an aurora in your bar color behind the player: slow curtains of light that
#     drift, shift in hue, and carry the music along them (the loudness of the last moments travels across the
#     window as soft pulses). It replaces the plain spectrogram; the waves view (key w) still works, now over the aurora.
#   * The queue panel's rows fade and slide in one after another when it opens, like the menu.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v5.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_aurora_backdrop" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_menu_anim_t0" not in src:
    print("Apply patch_queue_v5.py first. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


# ============================================================ the aurora

patch("static void video_audio_display(VideoState *s)\n{\n",
      "static int ui_aurora_backdrop(VideoState *is);\n\nstatic void video_audio_display(VideoState *s)\n{\n",
      "aurora declaration")

patch("    int rdft_bits, nb_freq;\n\n    for (rdft_bits = 1; (1 << rdft_bits) < 2 * s->height; rdft_bits++)\n",
      "    int rdft_bits, nb_freq;\n\n"
      "    if (ui_aurora_backdrop(s) && s->show_mode == SHOW_MODE_RDFT)\n"
      "        return;                         /* the aurora is the picture; waves are drawn over it below */\n\n"
      "    for (rdft_bits = 1; (1 << rdft_bits) < 2 * s->height; rdft_bits++)\n",
      "the aurora replaces the spectrogram")

patch("static SDL_Texture *ui_make_target(int w, int h)\n{\n",
      r'''/* ----- the aurora: the backdrop for audio without cover art -----
   The same soft mesh as the cover art backdrop, but its colors are made up as it goes, from your bar color:
   slow curtains of light drift across it and shift in hue. The loudness of the last second or so is kept in
   a row of values, one per column, and it travels across the window, so the music seems to ripple through. */
static void ui_rgb2hsv(int r, int g, int b, double *h, double *s, double *v)
{
    double rf = r / 255.0, gf = g / 255.0, bf = b / 255.0;
    double mx = FFMAX3(rf, gf, bf), mn = FFMIN3(rf, gf, bf), d = mx - mn;

    *v = mx;
    *s = mx > 0 ? d / mx : 0;
    if (d <= 0)
        *h = 0;
    else if (mx == rf)
        *h = fmod((gf - bf) / d, 6.0) / 6.0;
    else if (mx == gf)
        *h = ((bf - rf) / d + 2.0) / 6.0;
    else
        *h = ((rf - gf) / d + 4.0) / 6.0;
    if (*h < 0)
        *h += 1.0;
}

static void ui_hsv2rgb(double h, double s, double v, SDL_Color *c)
{
    double r, g, b, f, p, q, t;
    int i;

    h = (h - floor(h)) * 6.0;
    i = (int)h;
    f = h - i;
    p = v * (1 - s);
    q = v * (1 - s * f);
    t = v * (1 - s * (1 - f));
    switch (i % 6) {
    case 0:  r = v; g = t; b = p; break;
    case 1:  r = q; g = v; b = p; break;
    case 2:  r = p; g = v; b = t; break;
    case 3:  r = p; g = q; b = v; break;
    case 4:  r = t; g = p; b = v; break;
    default: r = v; g = p; b = q; break;
    }
    c->r = (Uint8)av_clipd(r * 255, 0, 255);
    c->g = (Uint8)av_clipd(g * 255, 0, 255);
    c->b = (Uint8)av_clipd(b * 255, 0, 255);
    c->a = 255;
}

/* Draw the aurora behind an audio-only stream. Returns 1 if it was drawn. */
static int ui_aurora_backdrop(VideoState *is)
{
    static float hist[UI_BD_W];                 /* the loudness of the last moments, one value per column */
    static int64_t hist_at = 0;
    static float lvl = 0.0f;
    static int idx[(UI_BD_W - 1) * (UI_BD_H - 1) * 6];
    static int idx_ready = 0;
    SDL_Vertex v[UI_BD_H * UI_BD_W];
    double t = av_gettime_relative() / 1000000.0, h0, s0, v0, u, w, band, curtain, vw, val, dx, dy;
    int64_t now = av_gettime_relative();
    int i, j, k = 0, W = is->width, H = is->height;

    if (!is->audio_st || ui_has_cover(is) || W <= 0 || H <= 0)
        return 0;
    if (!idx_ready) {
        for (j = 0; j < UI_BD_H - 1; j++)
            for (i = 0; i < UI_BD_W - 1; i++) {
                int a = j * UI_BD_W + i;

                idx[k++] = a;
                idx[k++] = a + 1;
                idx[k++] = a + UI_BD_W;
                idx[k++] = a + 1;
                idx[k++] = a + UI_BD_W + 1;
                idx[k++] = a + UI_BD_W;
            }
        idx_ready = 1;
    }
    lvl += ((is->paused ? 0.0f : av_clipf(is->level * 4.0f, 0.0f, 1.0f)) - lvl) * 0.2f;
    if (now - hist_at > 60000 || now < hist_at) {       /* the ripple moves one column to the left */
        memmove(hist, hist + 1, sizeof(float) * (UI_BD_W - 1));
        hist[UI_BD_W - 1] = lvl;
        hist_at = now;
    }
    ui_rgb2hsv(cfg_bar_r, cfg_bar_g, cfg_bar_b, &h0, &s0, &v0);
    s0 = FFMAX(s0, 0.55);

    for (j = 0; j < UI_BD_H; j++) {
        for (i = 0; i < UI_BD_W; i++) {
            SDL_Vertex *p = &v[j * UI_BD_W + i];

            u = i / (double)(UI_BD_W - 1);
            w = j / (double)(UI_BD_H - 1);
            band = 0.5 + 0.5 * sin(i * 0.55 + t * 0.30 + 1.4 * sin(j * 0.6 + t * 0.20));
            curtain = pow(band, 2.2);                           /* the bright curtains */
            vw = 0.2 + 0.8 * pow(1.0 - w, 0.8);                 /* they hang from the top */
            val = 0.08 + 0.50 * curtain * vw + 0.50 * hist[i] * (0.4 + 0.6 * vw);
            val *= 0.75 + 0.50 * lvl;
            dx = u - 0.5;
            dy = w - 0.5;
            val *= 1.0 - 0.8 * (dx * dx + dy * dy);             /* darker toward the corners */
            ui_hsv2rgb(h0 + 0.06 * sin(t * 0.21 + i * 0.5 + j * 0.8) + 0.10 * curtain,
                       av_clipd(s0 * (1.05 - 0.30 * curtain), 0.0, 1.0), av_clipd(val, 0.0, 0.9), &p->color);
            p->position.x = (float)(((u - 0.5) * 1.12 + 0.5 + 0.02 * sin(t * 0.25 + j * 0.9 + i * 0.4)) * W);
            p->position.y = (float)(((w - 0.5) * 1.12 + 0.5 + 0.03 * cos(t * 0.22 + i * 0.6 + j * 0.5)) * H);
            p->tex_coord.x = 0;
            p->tex_coord.y = 0;
        }
    }
    SDL_RenderGeometry(renderer, NULL, v, UI_BD_H * UI_BD_W, idx, (UI_BD_W - 1) * (UI_BD_H - 1) * 6);
    return 1;
}

static SDL_Texture *ui_make_target(int w, int h)
{
''', "the aurora")

# ============================================================ the queue panel cascades in

patch("static void ui_label(int x, int cy, const char *s, int px, int r, int g, int b, int a);\n\n/* Text with a soft shadow",
      "static void ui_label(int x, int cy, const char *s, int px, int r, int g, int b, int a);\n"
      "static double ui_fade = 1.0;        /* 0 to 1: everything drawn through the helpers below is this strong */\n\n"
      "/* Text with a soft shadow", "fade variable")

patch("static void ui_label(int x, int cy, const char *s, int px, int r, int g, int b, int a)\n{\n    int w = 0, h = 0;\n    SDL_Texture *tex = ui_text_tex(s, px, &w, &h);\n    SDL_Rect dst;\n",
      "static void ui_label(int x, int cy, const char *s, int px, int r, int g, int b, int a)\n{\n    int w = 0, h = 0;\n    SDL_Texture *tex = ui_text_tex(s, px, &w, &h);\n    SDL_Rect dst;\n\n    a = (int)(a * ui_fade);\n",
      "text follows the fade")
patch("static void ui_shuffle_icon(int cx, int cy, int r, int g, int b, int a)\n{\n    SDL_SetRenderDrawColor(renderer, r, g, b, a);\n",
      "static void ui_shuffle_icon(int cx, int cy, int r, int g, int b, int a)\n{\n    SDL_SetRenderDrawColor(renderer, r, g, b, (int)(a * ui_fade));\n",
      "shuffle icon follows the fade")
patch("    SDL_Rect bar;\n\n    SDL_SetRenderDrawColor(renderer, 230, 230, 230, a);\n    if (which == 0) {",
      "    SDL_Rect bar;\n\n    SDL_SetRenderDrawColor(renderer, 230, 230, 230, (int)(a * ui_fade));\n    if (which == 0) {",
      "transport icons follow the fade")
patch("    int k, tail = cx - dir * 3, tip = cx + dir * 3, h = 5;\n\n    for (k = -1; k <= 1; k++) {\n",
      "    int k, tail = cx - dir * 3, tip = cx + dir * 3, h = 5;\n\n    a = av_clip((int)(a * ui_fade), 0, 255);       /* (a can arrive below 0 while the menu fades in) */\n    for (k = -1; k <= 1; k++) {\n",
      "arrows follow the fade (and never wrap around)")

patch("static int64_t ui_menu_anim_t0 = 0; /* when the popup menu opened (its rows fade in from then) */\n",
      "static int64_t ui_menu_anim_t0 = 0; /* when the popup menu opened (its rows fade in from then) */\n"
      "static int64_t ui_q_anim_t0 = 0;    /* when the queue panel opened (its rows fade in from then) */\n",
      "queue panel open time")

patch("    if (!ui_q_open)\n        ui_q_reveal = 1;            /* scroll to the playing item the first time it is drawn */\n",
      "    if (!ui_q_open) {\n        ui_q_reveal = 1;            /* scroll to the playing item the first time it is drawn */\n"
      "        ui_q_anim_t0 = av_gettime_relative();       /* and the rows fade in */\n    }\n",
      "note when the queue panel opens")

patch("static void ui_q_draw(int ww, int wh)\n{\n",
      r'''/* How far the fade-in of row number i of the queue panel has got (0 to 1, easing out). The rows start
   one after another; the last ones do not wait longer than a third of a second. */
static double ui_cascade(int i)
{
    double k;

    if (ui_q_drag >= 0)
        return 1.0;
    k = av_clipd((av_gettime_relative() - ui_q_anim_t0 - FFMIN(i * 24000, 300000)) / 170000.0, 0.0, 1.0);
    return 1.0 - (1.0 - k) * (1.0 - k) * (1.0 - k);
}

static void ui_q_draw(int ww, int wh)
{
''', "row cascade function")

patch("    /* top row: \"Add to queue...\", previous, play/pause, next and shuffle */\n",
      "    ui_fade = ui_cascade(0);\n    /* top row: \"Add to queue...\", previous, play/pause, next and shuffle */\n",
      "queue panel: fade the top row")

patch("        item = ui_q_slot_item(ui_q_scroll + i, drop);\n        cy = top + i * UI_Q_ROW + UI_Q_ROW / 2;\n",
      "        item = ui_q_slot_item(ui_q_scroll + i, drop);\n        cy = top + i * UI_Q_ROW + UI_Q_ROW / 2;\n"
      "        ui_fade = ui_cascade(i + 1);\n",
      "queue panel: fade each row")

patch("""        if (item == q_pos || item == ui_q_drag)
            ui_label(p.x + 20, cy, name, 18, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                     av_clip(cfg_bar_b + 40, 0, 255), 255);
        else
            ui_label(p.x + 20, cy, name, 18, 240, 240, 240, lit ? 255 : 205);
""", """        if (item == q_pos || item == ui_q_drag)
            ui_label(p.x + 20 + (int)((1.0 - ui_fade) * 12), cy, name, 18, av_clip(cfg_bar_r + 40, 0, 255),
                     av_clip(cfg_bar_g + 40, 0, 255), av_clip(cfg_bar_b + 40, 0, 255), 255);
        else
            ui_label(p.x + 20 + (int)((1.0 - ui_fade) * 12), cy, name, 18, 240, 240, 240, lit ? 255 : 205);
""", "queue panel: names slide in")

patch("        SDL_SetRenderDrawColor(renderer, 230, 230, 230, (lit && hk == UI_Q_DEL) ? 255 : 120);\n",
      "        SDL_SetRenderDrawColor(renderer, 230, 230, 230, (int)(((lit && hk == UI_Q_DEL) ? 255 : 120) * ui_fade));\n",
      "queue panel: the x fades in")

patch("""        if (item == q_pos || item == ui_q_drag)
            SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 255);
        else
            SDL_SetRenderDrawColor(renderer, 200, 200, 200, lit ? 200 : 120);
        ui_pill(&dot);
""", """        if (item == q_pos || item == ui_q_drag)
            SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, (int)(255 * ui_fade));
        else
            SDL_SetRenderDrawColor(renderer, 200, 200, 200, (int)((lit ? 200 : 120) * ui_fade));
        ui_pill(&dot);
""", "queue panel: the dot fades in")

patch("    /* crossfade: < 3 s > */\n", "    ui_fade = ui_cascade(vis + 1);\n    /* crossfade: < 3 s > */\n",
      "queue panel: fade the bottom section")

patch("    ui_label_c(p.x + p.w / 2, fy + 100, text, 15, 170, 170, 170, 255);\n}\n",
      "    ui_label_c(p.x + p.w / 2, fy + 100, text, 15, 170, 170, 170, 255);\n    ui_fade = 1.0;\n}\n",
      "queue panel: back to full strength")

patch("        is->force_refresh = 1;                  /* the rows are still fading in */\n",
      "        is->force_refresh = 1;                  /* the rows are still fading in */\n"
      "    if (ui_q_open && av_gettime_relative() - ui_q_anim_t0 < 700000)\n"
      "        is->force_refresh = 1;                  /* the queue rows are still fading in */\n",
      "redraw while the queue rows fade in")

open(path, "w").write(src)
print("Patched", path)
