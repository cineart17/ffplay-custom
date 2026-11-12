#!/usr/bin/env python3
# Update 9 for ffplay-custom (on top of patch_queue_v8.py).
#   * A cover with no picture shows a file-manager style icon (a light page with an orange music note)
#     instead of the first letter of its name.
#   * Hold a cover and drag to rearrange the queue. A bar-colored marker shows where it will land, the dragged
#     cover follows the mouse, and holding it near the left or right edge keeps the row moving.
#     A plain click still plays the item (or pauses / resumes the playing one).
#   * Every cover except the middle one gets a small, faded title under it.
#   * Video thumbnails no longer have black bars: the bars are a frosted blur of the picture, tinted with your bar color.
#   * Fix: the big title in the cover-flow could turn into the blocky pixel font. The old letter tiles asked for a new
#     text size every frame as the covers glided, which used up the player's few font slots. Only fixed sizes are used now.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v8.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_flow_tile" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_flow_draw(VideoState *is)\n{" not in src:
    print("Apply patch_queue_v8.py first. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


# ============================================================ mouse hooks

patch("static int ui_flow_click(VideoState *is, int x, int y);\nstatic int ui_ctrl_click(VideoState *is, int x);\n",
      "static int ui_flow_click(VideoState *is, int x, int y);\n"
      "static int ui_flow_motion(VideoState *is, int x, int y);\n"
      "static int ui_flow_release(VideoState *is, int x, int y);\n"
      "static int ui_ctrl_click(VideoState *is, int x);\n",
      "mouse declarations")

patch("    if (ev->type == SDL_MOUSEMOTION) {\n        ui_hover = ev->motion.y >= is->height - UI_BAR_H;\n",
      "    if (ev->type == SDL_MOUSEMOTION) {\n"
      "        if (ui_flow_motion(is, ev->motion.x, ev->motion.y))\n            return 1;                       /* dragging a cover */\n"
      "        ui_hover = ev->motion.y >= is->height - UI_BAR_H;\n",
      "mouse moves while dragging a cover")

patch("    if (ev->type == SDL_MOUSEBUTTONUP && ev->button.button == SDL_BUTTON_LEFT && ui_drag) {\n",
      "    if (ev->type == SDL_MOUSEBUTTONUP && ev->button.button == SDL_BUTTON_LEFT &&\n"
      "        ui_flow_release(is, ev->button.x, ev->button.y))\n        return 1;                           /* a click on a cover ends, or a drag drops */\n"
      "    if (ev->type == SDL_MOUSEBUTTONUP && ev->button.button == SDL_BUTTON_LEFT && ui_drag) {\n",
      "mouse release on a cover")

patch("        if (!edges && is && ev->button.y >= is->height - UI_BAR_H)\n            return 0;\n        ui_win_mode = edges ? 2 : 1;\n",
      "        if (!edges && is && ev->button.y >= is->height - UI_BAR_H)\n            return 0;\n"
      "        if (!edges && is && ui_flow_cover_at(is, ev->button.x, ev->button.y) >= 0)\n"
      "            return 0;                   /* a press on a cover belongs to the queue view, not to moving the window */\n"
      "        ui_win_mode = edges ? 2 : 1;\n",
      "a press on a cover does not move the window")

# ============================================================ pictures: square, with frosted bars for video

patch("static uint8_t *ui_cov_decode(const char *path, int *ow, int *oh)\n",
      "static uint8_t *ui_cov_decode(const char *path, int *ow, int *oh, int *cw, int *ch)\n",
      "decoder signature")

patch("    int ls[4] = { 0 }, i, n, w, h, got = 0;\n",
      "    int ls[4] = { 0 }, i, n, w, h, got = 0;\n"
      "    uint8_t *sq = NULL, *tiny = NULL, *tdst[4] = { NULL };\n"
      "    struct SwsContext *sws2 = NULL;\n"
      "    int tls[4] = { 0 }, x, y, ox, oy;\n",
      "decoder variables")

patch("    sws_scale(sws, (const uint8_t *const *)fr->data, fr->linesize, 0, fr->height, dst, ls);\n    *ow = w;\n    *oh = h;\nend:\n    sws_freeContext(sws);\n",
      r'''    sws_scale(sws, (const uint8_t *const *)fr->data, fr->linesize, 0, fr->height, dst, ls);
    *ow = w;
    *oh = h;
    *cw = w;
    *ch = h;
    if (w != h) {       /* not square (a video frame): a square with the picture in the middle and a frosted blur around it */
        sq = av_malloc(256 * 256 * 4);
        tiny = av_malloc(16 * 16 * 4);
        sws2 = sws_getContext(fr->width, fr->height, fr->format, 16, 16, AV_PIX_FMT_RGBA, SWS_AREA, NULL, NULL, NULL);
        if (!sq || !tiny || !sws2) {
            av_freep(&out);
            goto end;
        }
        tdst[0] = tiny;
        tls[0] = 16 * 4;
        sws_scale(sws2, (const uint8_t *const *)fr->data, fr->linesize, 0, fr->height, tdst, tls);
        for (y = 0; y < 256; y++)
            for (x = 0; x < 256; x++) {
                double fx = x * 15.0 / 255.0, fy = y * 15.0 / 255.0, ax, ay;
                int x0 = (int)fx, y0 = (int)fy, x1 = FFMIN(x0 + 1, 15), y1 = FFMIN(y0 + 1, 15), k;

                ax = fx - x0;
                ay = fy - y0;
                for (k = 0; k < 4; k++) {
                    double v = (tiny[(y0 * 16 + x0) * 4 + k] * (1 - ax) + tiny[(y0 * 16 + x1) * 4 + k] * ax) * (1 - ay) +
                               (tiny[(y1 * 16 + x0) * 4 + k] * (1 - ax) + tiny[(y1 * 16 + x1) * 4 + k] * ax) * ay;

                    sq[(y * 256 + x) * 4 + k] = (uint8_t)(k < 3 ? FFMIN(v * 0.8 + 40.0, 255.0) : 255.0);
                }
            }
        ox = (256 - w) / 2;
        oy = (256 - h) / 2;
        for (y = 0; y < h; y++)
            memcpy(sq + ((oy + y) * 256 + ox) * 4, out + (size_t)y * w * 4, w * 4);
        av_freep(&out);
        out = sq;
        sq = NULL;
        *ow = 256;
        *oh = 256;
    }
end:
    sws_freeContext(sws);
    sws_freeContext(sws2);
    av_free(tiny);
    av_free(sq);
''', "square pictures with frosted bars")

patch("    uint8_t *px;\n    int w, h;\n    SDL_Texture *tex;\n} UiCov;",
      "    uint8_t *px;\n    int w, h;                   /* the size of the texture */\n    int cw, ch;                 /* the size of the picture inside it (smaller on one side if it was a video frame) */\n    SDL_Texture *tex;\n} UiCov;",
      "picture sizes")

patch("    uint8_t *px;\n    int k, w, h;\n",
      "    uint8_t *px;\n    int k, w, h, cw, ch;\n", "thread variables")

patch("        w = h = 0;\n        px = p ? ui_cov_decode(p, &w, &h) : NULL;\n",
      "        w = h = cw = ch = 0;\n        px = p ? ui_cov_decode(p, &w, &h, &cw, &ch) : NULL;\n", "thread decode call")

patch("        ui_cov[k].h = h;\n",
      "        ui_cov[k].h = h;\n        ui_cov[k].cw = cw;\n        ui_cov[k].ch = ch;\n", "thread stores picture size")

patch("            *w = c->w;\n            *h = c->h;\n",
      "            *w = c->cw;\n            *h = c->ch;\n", "ui_cov_get reports the picture size")

# ============================================================ drag state, tiles, file icon

patch("static int ui_flow_moving = 0;\nstatic int ui_flow_n = 0;\n",
      "static int ui_flow_moving = 0;\nstatic int ui_flow_n = 0;\n"
      "static int ui_flow_press = -1;          /* the cover the mouse went down on (-1 = none) */\n"
      "static int ui_flow_dragging = 0;        /* 1 once the mouse has moved far enough to drag it */\n"
      "static int ui_flow_px = 0, ui_flow_py = 0;      /* where the mouse went down */\n"
      "static int ui_flow_mx = 0, ui_flow_my = 0;      /* where the mouse is, while dragging */\n"
      "static int ui_flow_drop = -1;           /* where the dragged item lands in the queue if dropped now */\n"
      "static int64_t ui_flow_edge_at = 0;     /* when the row last stepped because the mouse was at an edge */\n",
      "drag state")

patch("    return ui_flow_on(is) && (!is->paused || ui_flow_moving);\n",
      "    return ui_flow_on(is) && (!is->paused || ui_flow_moving || ui_flow_dragging);\n",
      "redraw while dragging")

patch("static void ui_flow_draw(VideoState *is)\n{\n    enum { NEQ = 72 };\n",
      r'''/* The icon for a file with no picture, like the file manager's: a light page with an orange music note */
static void ui_flow_note(const SDL_Rect *t, int al, int md)
{
    const double two_pi = 6.28318531;
    double u = t->w / 100.0;
    SDL_Rect r;
    SDL_Vertex v[4];
    int idx[6] = { 0, 1, 2, 1, 3, 2 }, k;
    int cr = 233 * md / 255, cg = 104 * md / 255, cb = 36 * md / 255;
    static const double bx[4] = { 43, 77, 43, 77 }, by[4] = { 28, 20, 37, 29 };

    SDL_SetRenderDrawColor(renderer, 238 * md / 255, 238 * md / 255, 240 * md / 255, al);
    ui_rr_fill(t, 8);
    ui_fan(t->x + 36 * u, t->y + 70 * u, 9 * u, 0, two_pi, 24, cr, cg, cb, al);
    ui_fan(t->x + 66 * u, t->y + 64 * u, 9 * u, 0, two_pi, 24, cr, cg, cb, al);
    SDL_SetRenderDrawColor(renderer, cr, cg, cb, al);
    r.w = FFMAX((int)(3.6 * u), 2);
    r.x = t->x + (int)(43 * u);
    r.y = t->y + (int)(30 * u);
    r.h = (int)(40 * u);
    SDL_RenderFillRect(renderer, &r);
    r.x = t->x + (int)(73 * u);
    r.y = t->y + (int)(23 * u);
    r.h = (int)(41 * u);
    SDL_RenderFillRect(renderer, &r);
    for (k = 0; k < 4; k++) {                   /* the beam joining the two stems */
        v[k].position.x = (float)(t->x + bx[k] * u);
        v[k].position.y = (float)(t->y + by[k] * u);
        v[k].color.r = (Uint8)cr;
        v[k].color.g = (Uint8)cg;
        v[k].color.b = (Uint8)cb;
        v[k].color.a = (Uint8)al;
        v[k].tex_coord.x = 0;
        v[k].tex_coord.y = 0;
    }
    SDL_RenderGeometry(renderer, NULL, v, 4, idx, 6);
}

/* One cover in the row: its picture (the bars of a video thumbnail frosted in your bar color) or the file icon */
static void ui_flow_tile(int idx, const SDL_Rect *tile, int al, int md)
{
    SDL_Texture *tex;
    SDL_Rect hz;
    int cw = 0, ch = 0, bw;

    tex = ui_cov_get(q_items[idx], &cw, &ch);
    if (!tex) {
        ui_flow_note(tile, al, md);
        return;
    }
    SDL_SetRenderDrawColor(renderer, 24, 24, 28, al * 220 / 255);
    ui_rr_fill(tile, 8);
    SDL_SetTextureAlphaMod(tex, (Uint8)al);
    SDL_SetTextureColorMod(tex, (Uint8)md, (Uint8)md, (Uint8)md);
    SDL_RenderCopy(renderer, tex, NULL, tile);
    if (cw > 0 && ch > 0 && cw != ch) {
        SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 80 * al / 255);
        hz = *tile;
        if (cw > ch) {
            bw = (tile->h - tile->h * ch / cw) / 2;
            hz.h = bw;
            SDL_RenderFillRect(renderer, &hz);
            hz.y = tile->y + tile->h - bw;
            SDL_RenderFillRect(renderer, &hz);
        } else {
            bw = (tile->w - tile->w * cw / ch) / 2;
            hz.w = bw;
            SDL_RenderFillRect(renderer, &hz);
            hz.x = tile->x + tile->w - bw;
            SDL_RenderFillRect(renderer, &hz);
        }
    }
}

static void ui_flow_draw(VideoState *is)
{
    enum { NEQ = 72 };
''', "file icon and tile helpers")

patch("    SDL_Rect sk, vo, tile, dst, bar;\n    SDL_Texture *tex;\n    char name[320], num[48];\n    int tw, th, al, md;\n",
      "    SDL_Rect sk, vo, tile, bar;\n    char name[320], num[48];\n    int al, md;\n",
      "draw variables")

patch("""            SDL_SetRenderDrawColor(renderer, 24, 24, 28, al * 220 / 255);
            ui_rr_fill(&tile, 8);
            tex = ui_cov_get(q_items[i], &tw, &th);
            if (tex) {
                dst = tile;
                if (tw >= th)
                    dst.h = FFMAX(tile.w * th / tw, 1);
                else
                    dst.w = FFMAX(tile.h * tw / th, 1);
                dst.x = tile.x + (tile.w - dst.w) / 2;
                dst.y = tile.y + (tile.h - dst.h) / 2;
                SDL_SetTextureAlphaMod(tex, (Uint8)al);
                SDL_SetTextureColorMod(tex, (Uint8)md, (Uint8)md, (Uint8)md);
                SDL_RenderCopy(renderer, tex, NULL, &dst);
            } else {                            /* no picture (yet): a tile with the first letter */
                ui_q_name(i, name, 300);
                num[0] = name[0] && (unsigned char)name[0] < 0x80 ? name[0] : '#';
                num[1] = 0;
                SDL_SetRenderDrawColor(renderer, cfg_bar_r / 3 + 20, cfg_bar_g / 3 + 20, cfg_bar_b / 3 + 24, al);
                ui_rr_fill(&tile, 8);
                ui_label_c(tile.x + tile.w / 2, tile.y + tile.h / 2, num, FFMAX((int)(s * 0.4), 12), 240, 240, 240, al);
            }
""", """            ui_flow_tile(i, &tile, (ui_flow_dragging && i == ui_flow_press) ? al / 3 : al, md);
            if (i != ci) {                      /* a small, faded title under every cover but the middle one */
                ui_q_name(i, name, 300);
                ui_fit_text(name, 15, tile.w);
                ui_label_c(tile.x + tile.w / 2, tile.y + tile.h + 18, name, 15, 235, 235, 235, al * 55 / 100);
            }
""", "covers with small titles")

patch("    ui_fit_text(name, 24, (int)(W * 0.8));\n    ui_label_c(W / 2, cy + (int)(B / 2) + 40, name, 24, 255, 255, 255, 255);\n",
      "    ui_fit_text(name, 22, (int)(W * 0.8));\n    ui_label_c(W / 2, cy + (int)(B / 2) + 40, name, 22, 255, 255, 255, 255);\n",
      "title in a size the player keeps")

patch("        ui_label_c(ex + 72, cy, \"1\", 11, 245, 245, 245, 255);\n",
      "    {                                           /* a small 1 drawn with lines (no extra text size needed) */\n"
      "        ui_q_line(ex + 73, cy - 3, ex + 73, cy + 3);\n"
      "        ui_q_line(ex + 71, cy - 2, ex + 73, cy - 3);\n"
      "    }\n",
      "repeat one mark")

# ============================================================ dragging

patch("    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);\n}\n\n/* A click on a cover: play that item (or pause / resume if it is the one playing) */\n",
      r'''    if (ui_flow_dragging && ui_flow_press >= 0 && ui_flow_press < q_count) {
        int best = -1, bd = 1 << 30, k, mid, before, p;
        SDL_Rect g;

        for (k = 0; k < ui_flow_n; k++) {       /* the cover nearest the mouse (not the one in hand) */
            if (ui_flow_hit[k].idx == ui_flow_press)
                continue;
            mid = ui_flow_hit[k].r.x + ui_flow_hit[k].r.w / 2;
            if (FFABS(ui_flow_mx - mid) < bd) {
                bd = FFABS(ui_flow_mx - mid);
                best = k;
            }
        }
        ui_flow_drop = -1;
        if (best >= 0) {
            const SDL_Rect *r = &ui_flow_hit[best].r;

            before = ui_flow_mx < r->x + r->w / 2;
            p = ui_flow_hit[best].idx + (before ? 0 : 1);       /* the place between two covers */
            ui_flow_drop = ui_flow_press < p ? p - 1 : p;
            bar.x = (before ? r->x : r->x + r->w) - 3;
            bar.y = r->y;
            bar.w = 6;
            bar.h = r->h;
            SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 235);
            ui_rr_fill(&bar, 3);
        }
        g.w = (int)(B * 0.55);
        g.h = g.w;
        g.x = ui_flow_mx - g.w / 2;
        g.y = av_clip(ui_flow_my - g.h / 2, 0, FFMAX(H - g.h, 0));
        ui_shadow(&g, 10);
        ui_flow_tile(ui_flow_press, &g, 235, 255);              /* the cover in hand follows the mouse */
        if (now - ui_flow_edge_at > 350000 && (ui_flow_mx < W / 12 || ui_flow_mx > W - W / 12)) {
            ui_flow_target = av_clip(ui_flow_target + (ui_flow_mx < W / 2 ? -1 : 1), 0, q_count - 1);
            ui_flow_edge_at = now;              /* at an edge: the row keeps moving that way */
        }
        ui_flow_touch = now;
    }
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);
}

/* Which queue item is under the mouse (the nearest cover), or -1 */
static int ui_flow_cover_at(VideoState *is, int x, int y)
{
    int i;

    if (!ui_flow_on(is) || ui_menu_open || ui_prefs_open)
        return -1;
    for (i = ui_flow_n - 1; i >= 0; i--) {      /* the last one drawn is the nearest */
        const SDL_Rect *r = &ui_flow_hit[i].r;

        if (x >= r->x && x < r->x + r->w && y >= r->y && y < r->y + r->h)
            return ui_flow_hit[i].idx;
    }
    return -1;
}

/* A click on a cover: play that item (or pause / resume if it is the one playing) */
''', "drawing the drag")

patch("""/* A click on a cover: play that item (or pause / resume if it is the one playing) */
static int ui_flow_click(VideoState *is, int x, int y)
{
    int i;

    if (!ui_flow_on(is) || ui_menu_open || ui_prefs_open)
        return 0;
    for (i = ui_flow_n - 1; i >= 0; i--) {      /* the last one drawn is the nearest */
        const SDL_Rect *r = &ui_flow_hit[i].r;

        if (x >= r->x && x < r->x + r->w && y >= r->y && y < r->y + r->h) {
            if (ui_flow_hit[i].idx == q_pos) {
                toggle_pause(is);
            } else {
                q_forced = ui_flow_hit[i].idx;
                ui_end_current(is);
            }
            return 1;
        }
    }
    return 0;
}
""", """/* The mouse went down on a cover: it is a click if it comes up in the same place, a drag if it moves */
static int ui_flow_click(VideoState *is, int x, int y)
{
    int idx = ui_flow_cover_at(is, x, y);

    if (idx < 0)
        return 0;
    ui_flow_press = idx;
    ui_flow_dragging = 0;
    ui_flow_px = x;
    ui_flow_py = y;
    return 1;
}

/* The mouse moved with a cover held down. Returns 1 while a cover is held. */
static int ui_flow_motion(VideoState *is, int x, int y)
{
    if (ui_flow_press < 0)
        return 0;
    if (!ui_flow_dragging && (FFABS(x - ui_flow_px) >= 8 || FFABS(y - ui_flow_py) >= 8)) {
        ui_flow_dragging = 1;
        ui_flow_drop = -1;
        SDL_CaptureMouse(SDL_TRUE);
    }
    ui_flow_mx = x;
    ui_flow_my = y;
    is->force_refresh = 1;
    return 1;
}

/* The mouse came up: drop the cover where the marker is, or, if it never moved, play it (or pause / resume) */
static int ui_flow_release(VideoState *is, int x, int y)
{
    int idx = ui_flow_press;

    if (idx < 0)
        return 0;
    ui_flow_press = -1;
    if (ui_flow_dragging) {
        ui_flow_dragging = 0;
        SDL_CaptureMouse(SDL_FALSE);
        if (ui_flow_drop >= 0 && ui_flow_drop != idx && idx < q_count) {
            queue_move(idx, ui_flow_drop);
            ui_flow_last_q = q_pos;             /* the row stays on the moved item instead of jumping back */
            ui_flow_target = ui_flow_drop;
            ui_flow_touch = av_gettime_relative();
        }
        ui_flow_drop = -1;
    } else if (idx == q_pos) {
        toggle_pause(is);
    } else if (idx < q_count) {
        q_forced = idx;
        ui_end_current(is);
    }
    is->force_refresh = 1;
    return 1;
}
""", "click, drag and drop")

open(path, "w").write(src)
print("Patched", path)
