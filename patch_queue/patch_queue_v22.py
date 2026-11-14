#!/usr/bin/env python3
# Update 22 for ffplay-custom (on top of patch_queue_v21.py, the one that is on GitHub).
#   * Key L: the video that plays now keeps playing in its own tile (rounded, with the same tilt as the other tiles),
#     and the change is animated: the video shrinks from the full screen into its tile while the other tiles and the
#     backdrop fade in, and it grows back when you press L again.
#   * Playlists with both audio and video: videos show in their own shape in the queue view whichever kind of item is
#     playing. If the queue view is showing (an audio item is playing) and a video follows, the queue view stays; L
#     goes to the full screen video. The picture in hand while dragging keeps its shape, and the title under the middle
#     tile no longer jumps when the row passes between a wide and a square picture.
#   * A paused player keeps responding: the bars show up when the mouse moves, and hide again after the hide delay.
#   * The frosted glass (menus, queue panel, media info, Open, preferences) is light now, with dark text on it.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v21.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_live_grab" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_cov_native" not in src or "ui_flow_vmode" not in src:
    print("Apply patch_queue_v21.py (the one on GitHub) first. Nothing written.")
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


# ============================================================ a paused player keeps responding

patch("    if (cursor_hidden && !is->paused) return;\n",
      "    if (cursor_hidden) return;                  /* the bar hides after the hide delay, paused or not */\n",
      "the bar hides when paused too")

patch("        ui_cover_tick(is);\n        ui_mpris_tick(is);\n        if (ui_q_autoscroll())\n            is->force_refresh = 1;\n",
      r'''        ui_cover_tick(is);
        ui_mpris_tick(is);
        if (ui_q_autoscroll())
            is->force_refresh = 1;
        if (is->paused && !is->force_refresh) {     /* paused: the picture is still, but the bars show, move and hide, so keep drawing while they are active */
            static int64_t forced_at = 0;
            int64_t tnow = av_gettime_relative();

            if ((ui_hover || ui_drag || tnow - cursor_last_shown < CURSOR_HIDE_DELAY + 800000) && tnow - forced_at > 30000) {
                forced_at = tnow;
                is->force_refresh = 1;
            }
        }
''', "keep drawing while the bars are active and the player is paused")

# ============================================================ light frosted glass

patch("/* Show the cursor and bar again and restart the hide timer */\nstatic void ui_wake(void)\n",
      r'''/* ----- light glass: on the frosted glass, text and lines that were light are drawn dark instead -----
   ui_ink_dark is 1 while a panel on glass is drawn. Light grays and white then turn dark (the lighter they were, the
   darker they become); colors, such as your bar color, stay as they are. */
static int ui_ink_dark = 0;

static void ui_ink(int *r, int *g, int *b)
{
    if (ui_ink_dark && FFMIN3(*r, *g, *b) >= 100 && FFMAX3(*r, *g, *b) - FFMIN3(*r, *g, *b) <= 40) {
        *r = (255 - *r) * 8 / 10;
        *g = (255 - *g) * 8 / 10;
        *b = (255 - *b) * 8 / 10;
    }
}

static int ui_set_color(SDL_Renderer *rd, int r, int g, int b, int a)
{
    ui_ink(&r, &g, &b);
    return (SDL_SetRenderDrawColor)(rd, r, g, b, a);
}
#define SDL_SetRenderDrawColor(rd, r, g, b, a) ui_set_color(rd, r, g, b, a)

/* Show the cursor and bar again and restart the hide timer */
static void ui_wake(void)
''', "light glass: dark ink helpers")

patch("    SDL_SetTextureColorMod(tex, r, g, b);\n    SDL_SetTextureAlphaMod(tex, a);\n    SDL_RenderCopy(renderer, tex, NULL, &dst);\n}\n\n/* Draw text with its middle at cx */",
      "    ui_ink(&r, &g, &b);                         /* dark text on the light glass */\n"
      "    SDL_SetTextureColorMod(tex, r, g, b);\n    SDL_SetTextureAlphaMod(tex, a);\n    SDL_RenderCopy(renderer, tex, NULL, &dst);\n}\n\n/* Draw text with its middle at cx */",
      "dark text on the light glass")

patch("    int row, run = -1, inset, top3;\n    SDL_Rect line;\n\n    r = FFMIN(r, FFMIN(t->w, t->h) / 2);\n    ui_shadow(t, r);\n",
      "    int row, run = -1, inset, top3, ink = ui_ink_dark;\n    SDL_Rect line;\n\n    ui_ink_dark = 0;                            /* the glass itself is drawn as it is */\n"
      "    r = FFMIN(r, FFMIN(t->w, t->h) / 2);\n    ui_shadow(t, r);\n",
      "the glass is drawn without the ink change")

patch("        SDL_SetRenderDrawColor(renderer, 10 + cfg_bar_r / 12, 12 + cfg_bar_g / 12, 18 + cfg_bar_b / 12, 118);\n",
      "        SDL_SetRenderDrawColor(renderer, 225 + cfg_bar_r / 10, 228 + cfg_bar_g / 10, 232 + cfg_bar_b / 10, 168);     /* a light haze */\n",
      "a light tint")

patch("            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 14 - 14 * row / top3);\n",
      "            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 70 - 70 * row / top3);\n",
      "a brighter sheen")

patch("            SDL_RenderFillRect(renderer, &line);\n        }\n\n    }\n}\n\n/* The idle background",
      "            SDL_RenderFillRect(renderer, &line);\n        }\n\n    }\n    ui_ink_dark = ink;\n}\n\n/* The idle background",
      "give the ink setting back")

patch("    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);\n    for (i = 0; i < UI_MENU_ITEMS; i++) {\n        row.x = r.x;",
      "    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);\n"
      "    ui_ink_dark = !ui_idle;                     /* the card is light glass: dark text on it (the idle screen has no card) */\n"
      "    for (i = 0; i < UI_MENU_ITEMS; i++) {\n        row.x = r.x;",
      "dark text on the menu card")

patch("    if (ui_open_open)\n        ui_open_draw(ww, wh);\n    else if (ui_q_open)",
      "    ui_ink_dark = 1;                            /* the side panels are light glass too */\n"
      "    if (ui_open_open)\n        ui_open_draw(ww, wh);\n    else if (ui_q_open)",
      "dark text on the side panels")

patch("    if (ui_ctx_open)\n        ui_ctx_draw(ww, wh);\n    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);\n}",
      "    if (ui_ctx_open)\n        ui_ctx_draw(ww, wh);\n    ui_ink_dark = 0;\n    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);\n}",
      "the menu gives the ink setting back")

patch("    ui_menu_draw();\n    ui_prefs_draw();\n    ui_snap_draw();\n",
      "    ui_menu_draw();\n    ui_ink_dark = 1;                            /* the preferences are light glass: dark text on them */\n"
      "    ui_prefs_draw();\n    ui_ink_dark = 0;\n    ui_snap_draw();\n",
      "dark text in the preferences")

# ============================================================ globals for the live tile and its animation

patch("static int ui_flow_wants_redraw(VideoState *is);\nstatic int ui_flow_video(VideoState *is);\n",
      r'''static int ui_flow_wants_redraw(VideoState *is);
static int ui_flow_video(VideoState *is);
static void ui_live_grab(VideoState *is, const SDL_Rect *rect, int flip);
static double ui_vflow_p = 0.0;         /* 0 to 1: how far the playing video has shrunk into its tile (it animates when L is pressed) */
static double ui_vflow_ep = 0.0;        /* the same, eased: slow, quick, slow */
static int64_t ui_vflow_t = 0;          /* when the animation was last stepped */
static SDL_Rect ui_live_rect;           /* where the video is drawn full screen (set in video_image_display) */
static int ui_live_ok = 0;              /* 1 = the frame on screen was copied into ui_live_tex in this drawing */
static SDL_Texture *ui_live_tex = NULL; /* the frame on screen, as a picture of its own for the tile */
static int ui_live_w = 0, ui_live_h = 0;
''', "globals for the live tile")

patch("    ui_cover_backdrop(is, vp->flip_v);      /* behind the cover art: its own colors, glowing */\n",
      "    ui_cover_backdrop(is, vp->flip_v);      /* behind the cover art: its own colors, glowing */\n"
      "    ui_live_grab(is, &rect, vp->flip_v);    /* over a video: copy the frame, the tile shows it */\n",
      "copy the frame for the tile")

patch("    int i, j, k = 0, W = is->width, H = is->height;\n    float target;\n",
      "    int i, j, k = 0, W = is->width, H = is->height;\n    float target;\n    double bdk = ui_flow_video(is) ? ui_vflow_ep : 1.0;     /* the backdrop fades in while the video shrinks into its tile */\n",
      "backdrop fade: variable")

patch("            p->color.a = 255;\n            p->tex_coord.x = 0;\n            p->tex_coord.y = 0;\n        }\n    }\n    SDL_RenderGeometry(renderer, NULL, v, UI_BD_H * UI_BD_W, idx, (UI_BD_W - 1) * (UI_BD_H - 1) * 6);\n",
      "            p->color.a = (Uint8)(255 * bdk);\n            p->tex_coord.x = 0;\n            p->tex_coord.y = 0;\n        }\n    }\n"
      "    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);\n"
      "    SDL_RenderGeometry(renderer, NULL, v, UI_BD_H * UI_BD_W, idx, (UI_BD_W - 1) * (UI_BD_H - 1) * 6);\n",
      "backdrop fade: the colors")

patch("    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 45);\n    SDL_RenderFillRect(renderer, &veil);\n    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);\n}\n\n/* Keep the backdrop moving",
      "    SDL_SetRenderDrawColor(renderer, 0, 0, 0, (int)(45 * bdk));\n    SDL_RenderFillRect(renderer, &veil);\n    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);\n}\n\n/* Keep the backdrop moving",
      "backdrop fade: the veil")

patch("    if (ui_has_cover(is) && !is->paused && now - last > 33000) {",
      "    if ((ui_has_cover(is) || ui_flow_video(is)) && !is->paused && now - last > 33000) {",
      "keep the backdrop moving over a video")

patch("    SDL_RenderClear(renderer);\n    if (!is)\n        ui_blobs();\n",
      "    SDL_RenderClear(renderer);\n    ui_live_ok = 0;                             /* set again if a video frame is copied for its tile in this drawing */\n    if (!is)\n        ui_blobs();\n",
      "no old frame is used")

# ============================================================ the video playing in its tile

patch("/* Is the queue view showing over a video (key L)? */\nstatic int ui_flow_video(VideoState *is)\n{\n"
      "    return is && ui_vflow && is->video_st && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC) &&\n"
      "           q_count > 0 && q_pos >= 0 && q_pos < q_count;\n}\n",
      "/* Is the queue view showing over a video (key L)? It also shows while the video shrinks into its tile or grows back. */\n"
      "static int ui_flow_video(VideoState *is)\n{\n"
      "    return is && (ui_vflow || ui_vflow_p > 0.002) && is->video_st && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC) &&\n"
      "           q_count > 0 && q_pos >= 0 && q_pos < q_count;\n}\n",
      "the view also shows while the animation runs")

patch("    if (!path || !ui_cov_mu)\n        return NULL;\n    SDL_LockMutex(ui_cov_mu);\n    for (i = 0; i < ui_cov_n; i++)\n        if (!strcmp(ui_cov[i].path, path)) {\n            if (ui_cov[i].state == 2 && ui_cov[i].ntex) {",
      "    if (!path || !ui_cov_mu)\n        return NULL;\n    {\n        int cw, ch;\n\n        ui_cov_get(path, &cw, &ch);             /* also starts the reading and makes the textures, so there is no square flash first */\n    }\n"
      "    SDL_LockMutex(ui_cov_mu);\n    for (i = 0; i < ui_cov_n; i++)\n        if (!strcmp(ui_cov[i].path, path)) {\n            if (ui_cov[i].state == 2 && ui_cov[i].ntex) {",
      "make the textures before asking for the video's own shape")

patch("    tex = ui_flow_vmode ? ui_cov_native(q_items[idx], &cw, &ch) : NULL;     /* a video keeps its own shape */\n",
      "    tex = ui_cov_native(q_items[idx], &cw, &ch);        /* a video keeps its own shape, whatever is playing */\n",
      "videos keep their shape in every queue view")

patch("/* A title drawn as part of a turned card: it hangs under the cover's lower edge and follows it (same tilt as the cover) */\n",
      r'''/* The size of the picture of item i fitted into a sw x sh slot: a video keeps its own shape (the playing one: the shape of the
   screen it is on), covers and files with no picture fill the slot */
static void ui_flow_fit(int i, int sw, int sh, int *nw, int *nh)
{
    double asp = (i == q_pos && ui_flow_vmode && ui_live_ok && ui_live_rect.h > 0)
                 ? (double)ui_live_rect.w / ui_live_rect.h : ui_cov_aspect(q_items[i]);

    *nw = sw;
    *nh = sh;
    if (asp > 0.0) {
        *nw = asp >= 1.0 ? sw : (int)(sh * asp);
        *nh = asp >= 1.0 ? (int)(sw / asp) : sh;
    }
}

/* Like ui_flow_quad, but with rounded corners (radius rr): the columns are crowded near the left and right edges, where the
   corners are, and each column's top and bottom are moved in by how far the corner cuts in there */
static void ui_flow_quad_round(SDL_Texture *tex, const SDL_Rect *t, int al, int md, double tilt, int rr)
{
    enum { NC = 24 };
    SDL_Vertex v[(NC + 1) * 2];
    int idx[NC * 6], k;
    double cyt = t->y + t->h / 2.0, kin = 1.0 - 0.16 * fabs(tilt);
    SDL_Color c;

    rr = av_clip(rr, 0, FFMIN(t->w, t->h) / 2);
    c.r = (Uint8)md;
    c.g = (Uint8)md;
    c.b = (Uint8)md;
    c.a = (Uint8)av_clip(al, 0, 255);
    for (k = 0; k <= NC; k++) {
        double x, dx, inset = 0.0, u, f, hh;

        if (k <= 8)                             /* the left corner */
            x = rr * k / 8.0;
        else if (k <= 16)                       /* the straight part */
            x = rr + (t->w - 2.0 * rr) * (k - 8) / 8.0;
        else                                    /* the right corner */
            x = t->w - rr + rr * (k - 16) / 8.0;
        dx = FFMIN(x, t->w - x);
        if (dx < rr)
            inset = rr - sqrt(FFMAX((double)rr * rr - (rr - dx) * (rr - dx), 0.0));
        u = x / FFMAX(t->w, 1);
        f = tilt < 0 ? 1.0 - (1.0 - kin) * u : tilt > 0 ? kin + (1.0 - kin) * u : 1.0;      /* the same tilt as the covers */
        hh = (t->h / 2.0 - inset) * f;
        v[k * 2].position.x = (float)(t->x + x);
        v[k * 2].position.y = (float)(cyt - hh);
        v[k * 2].color = c;
        v[k * 2].tex_coord.x = (float)u;
        v[k * 2].tex_coord.y = (float)(inset / FFMAX(t->h, 1));
        v[k * 2 + 1].position.x = (float)(t->x + x);
        v[k * 2 + 1].position.y = (float)(cyt + hh);
        v[k * 2 + 1].color = c;
        v[k * 2 + 1].tex_coord.x = (float)u;
        v[k * 2 + 1].tex_coord.y = (float)(1.0 - inset / FFMAX(t->h, 1));
    }
    for (k = 0; k < NC; k++) {
        idx[k * 6] = k * 2;
        idx[k * 6 + 1] = k * 2 + 1;
        idx[k * 6 + 2] = k * 2 + 2;
        idx[k * 6 + 3] = k * 2 + 1;
        idx[k * 6 + 4] = k * 2 + 3;
        idx[k * 6 + 5] = k * 2 + 2;
    }
    SDL_RenderGeometry(renderer, tex, v, (NC + 1) * 2, idx, NC * 6);
}

/* While the queue view is over a video: remember where the video is drawn full screen, and copy the frame that is on screen
   into a picture of its own (ui_live_tex), so its tile can show it, rounded, while it plays. Called from video_image_display,
   where the colors of the frame are already set up. */
static void ui_live_grab(VideoState *is, const SDL_Rect *rect, int flip)
{
    SDL_Texture *prev;
    int w, h;

    ui_live_ok = 0;
    if (!ui_flow_video(is) || !is->vid_texture || rect->w < 16 || rect->h < 16)
        return;
    ui_live_rect = *rect;
    w = FFMIN(rect->w, 1920);
    h = (int)((double)w * rect->h / rect->w);
    if (!ui_live_tex || ui_live_w != w || ui_live_h != h) {
        if (ui_live_tex)
            SDL_DestroyTexture(ui_live_tex);
        ui_live_tex = ui_make_target(w, h);
        ui_live_w = w;
        ui_live_h = h;
        if (ui_live_tex)
            SDL_SetTextureBlendMode(ui_live_tex, SDL_BLENDMODE_BLEND);
    }
    if (!ui_live_tex)
        return;
    prev = SDL_GetRenderTarget(renderer);
    SDL_SetRenderTarget(renderer, ui_live_tex);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);
    SDL_RenderCopyEx(renderer, is->vid_texture, NULL, NULL, 0, NULL, flip ? SDL_FLIP_VERTICAL : 0);
    SDL_SetRenderTarget(renderer, prev);
    ui_live_ok = 1;
}

/* A title drawn as part of a turned card: it hangs under the cover's lower edge and follows it (same tilt as the cover) */
''', "the live tile helpers")

# ---- drawing the view: the animation, the mixed playlist, the live tile

patch("    int al, md, have, b0, b1, q, mid, chh;\n",
      "    int al, md, have, b0, b1, q, mid, chh, nal;\n",
      "variable for the labels' strength")

patch("    dt = ui_flow_t ? av_clipd((now - ui_flow_t) / 1000000.0, 0.0, 0.1) : 0.0;\n    ui_flow_t = now;\n",
      r'''    if (!ui_flow_vmode) {                       /* an audio item shows the queue view: a video that follows keeps it (L goes to the full screen video) */
        ui_vflow = 1;
        ui_vflow_p = 1.0;
        ui_vflow_ep = 1.0;
    }
    dt = ui_flow_t ? av_clipd((now - ui_flow_t) / 1000000.0, 0.0, 0.1) : 0.0;
    ui_flow_t = now;
    {                                           /* the video shrinks into its tile (or grows back) smoothly when L is pressed */
        double want = ui_vflow ? 1.0 : 0.0, dtv = ui_vflow_t ? av_clipd((now - ui_vflow_t) / 1000000.0, 0.0, 0.1) : 0.0;

        ui_vflow_t = now;
        ui_vflow_p += (want - ui_vflow_p) * (1.0 - exp(-dtv * 8.0));
        if (fabs(want - ui_vflow_p) < 0.004)
            ui_vflow_p = want;
        ui_vflow_ep = ui_vflow_p * ui_vflow_p * (3.0 - 2.0 * ui_vflow_p);
    }
''', "the shrinking animation")

patch("    if (!ui_flow_moving)\n        ui_flow_pos = ui_flow_target;\n",
      "    if (!ui_flow_moving)\n        ui_flow_pos = ui_flow_target;\n"
      "    if (ui_vflow_p != (ui_vflow ? 1.0 : 0.0))\n"
      "        ui_flow_moving = 1;                     /* the video is still shrinking into its tile, or growing back: keep drawing */\n",
      "keep drawing while the animation runs")

patch("            off = ui_flow_off(B, d);\n            s = B * sc;\n",
      "            off = ui_flow_off(B, d);\n"
      "            if (ui_flow_vmode && i != q_pos) {  /* the other tiles slide out from behind the video and grow a little */\n"
      "                off *= 0.55 + 0.45 * ui_vflow_ep;\n"
      "                sc *= 0.8 + 0.2 * ui_vflow_ep;\n"
      "            }\n"
      "            s = B * sc;\n",
      "the other tiles slide out while the video shrinks")

replace_between("            if (ui_flow_vmode) {                /* a video keeps its own shape: fitted into the square slot, centred in it */\n",
                "                chh = ui_flow_rects[e].h;       /* the labels go under the middle tile */\n",
                r'''            {                                   /* a video keeps its own shape (whatever is playing): fitted into the square slot, centred in it */
                int sw = ui_flow_rects[e].w, sh = ui_flow_rects[e].h, nw, nh;

                ui_flow_fit(i, sw, sh, &nw, &nh);
                ui_flow_rects[e].x += (sw - nw) / 2;
                ui_flow_rects[e].y += (sh - nh) / 2;
                ui_flow_rects[e].w = nw;
                ui_flow_rects[e].h = nh;
            }
''', "videos keep their shape in every view")

patch("        }\n        for (pass = 4; pass >= 0; pass--) {     /* then draw them, the far ones first */\n",
      r'''        }
        {                                       /* the labels and bars go under the middle picture: its height is eased between the two nearest items, so they do not jump */
            int i0 = av_clip((int)floor(ui_flow_pos), 0, q_count - 1), i1 = FFMIN(i0 + 1, q_count - 1), pw, h0, h1;
            double f = av_clipd(ui_flow_pos - i0, 0.0, 1.0);

            ui_flow_fit(i0, (int)B, (int)B, &pw, &h0);
            ui_flow_fit(i1, (int)B, (int)B, &pw, &h1);
            chh = (int)(h0 * (1.0 - f) + h1 * f);
        }
        for (pass = 4; pass >= 0; pass--) {     /* then draw them, the far ones first */
''', "the labels' height does not jump")

patch("                md = (int)(255 * av_clipd(1.0 - 0.20 * FFMIN(ad, 2.0), 0.4, 1.0));\n\n                vx0 = tile.x;",
      "                md = (int)(255 * av_clipd(1.0 - 0.20 * FFMIN(ad, 2.0), 0.4, 1.0));\n"
      "                if (ui_flow_vmode && i != q_pos)\n"
      "                    al = (int)(al * ui_vflow_ep);       /* the other tiles fade in while the video shrinks */\n\n"
      "                vx0 = tile.x;",
      "the other tiles fade in")

replace_between("                ui_flow_tile(i, &tile, (ui_flow_dragging && i == ui_flow_press) ? al / 3 : al, md, tl[e]);\n"
                "                if (ui_flow_vmode && i == q_pos) {      /* a small dot in the bar color marks the video that is playing */\n",
                "                    ui_pill(&dot);\n                }\n",
                r'''                if (ui_flow_vmode && i == q_pos && ui_live_ok) {        /* the video that plays now keeps playing in its tile */
                    SDL_Rect lr = tile;
                    double ep = ui_vflow_ep;

                    if (ep < 1.0) {             /* on its way between the full screen and its tile */
                        lr.x = ui_live_rect.x + (int)((tile.x - ui_live_rect.x) * ep);
                        lr.y = ui_live_rect.y + (int)((tile.y - ui_live_rect.y) * ep);
                        lr.w = ui_live_rect.w + (int)((tile.w - ui_live_rect.w) * ep);
                        lr.h = ui_live_rect.h + (int)((tile.h - ui_live_rect.h) * ep);
                    }
                    ui_flow_quad_round(ui_live_tex, &lr, al, md, tl[e] * ep, (int)(FFMIN(lr.w, lr.h) / 11.0 * ep));
                } else {
                    ui_flow_tile(i, &tile, (ui_flow_dragging && i == ui_flow_press) ? al / 3 : al, md, tl[e]);
                }
                if (ui_flow_vmode && i == q_pos) {      /* a small dot in the bar color marks the video that is playing */
                    int dd = FFMAX(tile.h / 34, 8);
                    SDL_Rect dot;

                    dot.w = dd;
                    dot.h = dd;
                    dot.x = tile.x + dd + 6;
                    dot.y = tile.y + tile.h - 2 * dd - 6;
                    SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, (int)(235 * al / 255 * ui_vflow_ep));
                    ui_pill(&dot);
                }
''', "the video plays in its tile")

patch("    ui_label_c(W / 2, cy + chh / 2 + 40, name, 22, 255, 255, 255, 255);\n",
      "    nal = ui_flow_vmode ? (int)(255 * ui_vflow_ep) : 255;       /* the labels fade in with the tiles */\n"
      "    ui_label_c(W / 2, cy + chh / 2 + 40, name, 22, 255, 255, 255, nal);\n",
      "the title fades in")
patch("    ui_label_c(W / 2, cy + chh / 2 + 70, num, 15, 175, 175, 175, 255);\n",
      "    ui_label_c(W / 2, cy + chh / 2 + 70, num, 15, 175, 175, 175, nal);\n",
      "the counter fades in")

patch("            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 90);        /* every bar the same color, as dim as the old unplayed bars */\n",
      "            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 90 * nal / 255);   /* every bar the same color, as dim as the old unplayed bars */\n",
      "the bars fade in")

patch("        g.w = (int)(B * 0.55);\n        g.h = g.w;\n",
      "        ui_flow_fit(ui_flow_press, (int)(B * 0.55), (int)(B * 0.55), &g.w, &g.h);     /* the picture in hand keeps its shape */\n",
      "the picture in hand keeps its shape")

# ---- the key

replace_between("            case SDLK_l:                /* the queue view over a video: the videos of the queue as tiles */\n",
                "                ui_vflow = !ui_vflow;\n                cur_stream->force_refresh = 1;\n                break;\n",
                r'''            case SDLK_l:                /* the queue view over a video (with audio it is always there): the video keeps playing in its tile */
                if (cur_stream->video_st && !(cur_stream->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC)) {
                    ui_vflow = !ui_vflow;
                    ui_vflow_t = 0;
                    ui_bd_key[0] = 0;           /* the backdrop takes its colors from the picture of this moment */
                    ui_flow_pos = ui_flow_target = q_pos;       /* the row starts at the playing video, no gliding in */
                    ui_flow_last_q = q_pos;
                    ui_flow_touch = 0;
                    cur_stream->force_refresh = 1;
                }
                break;
''', "key L: animated, only over a video")

open(path, "w").write(src)
print("Patched", path)
