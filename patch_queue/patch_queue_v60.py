#!/usr/bin/env python3
"""patch_queue_v60.py  --  Stripfilm transitions, square tiles, sorted folder play, thumbnails ahead of time.

Apply on top of the ffplay.c that is in ~/build/ffmpeg-6.1.1/fftools (the one you uploaded as ffplay-current.c).

    cd ~/build
    cp ffmpeg-6.1.1/fftools/ffplay.c ffplay.c.before-queue-v60
    python3 patch_queue_v60.py                      # patches ffmpeg-6.1.1/fftools/ffplay.c
    python3 patch_queue_v60.py path/to/ffplay.c     # or any other copy

Every edit is an exact match that must be found exactly once. If one is not found nothing is written.
"""
import os
import sys

path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/build/ffmpeg-6.1.1/fftools/ffplay.c")
src = open(path, encoding="utf-8").read()

if "v60: the Stripfilm view and its transitions" in src:
    sys.exit("already patched (v60 marker found): nothing to do")

orig = src
done = []


def rep(old, new, name):
    """Replace one exact piece of text, which must be there exactly once."""
    global src
    n = src.count(old)
    if n != 1:
        sys.exit("v60: '%s': found %d times (wanted 1): nothing written" % (name, n))
    src = src.replace(old, new)
    done.append(name)


def between(start, end, new, name, keep_end=True):
    """Replace everything from the first character of `start` up to (not including) `end`."""
    global src
    a = src.find(start)
    if a < 0 or src.count(start) != 1:
        sys.exit("v60: '%s': start marker found %d times (wanted 1): nothing written" % (name, src.count(start)))
    b = src.find(end, a)
    if b < 0:
        sys.exit("v60: '%s': end marker not found: nothing written" % name)
    src = src[:a] + new + (src[b:] if keep_end else src[b + len(end):])
    done.append(name)


# ---------------------------------------------------------------------------------------------------------------------
# 1. statics: the view is now two springs (how open, which layout), the strip has a speed, the rows tell the strip where their tiles are
rep("""static double ui_lv = 0.0, ui_lv_v = 0.0;       /* v59: the level of the view, smoothly: 0 = the full video, 1 = the Stripfilm view, 2 = the tiles of all (and its speed) */
static int64_t ui_lv_t = 0;                     /* when it was last moved */
static double ui_tile_p = 1.0;                  /* 0 to 1: how far the tiles of all have come in (over a video) */
""", """/* v60: the Stripfilm view and its transitions. Two springs instead of one level that has to pass through the middle: how far the view
   is open (0 = the full video, 1 = open) and which layout the open view has (0 = the tiles of all, 1 = the Stripfilm layout). A
   video that opens straight into the tiles shrinks into its small tile, without a flash of the strip; a layout change is the
   large tile and the tiles of the strip gliding into the places of the small tiles (and back). */
static double ui_lv = 0.0, ui_lv_v = 0.0;       /* v60: how far the view is open, and its speed */
static double ui_lay = 0.0, ui_lay_v = 0.0;     /* v60: the layout (0 = the tiles of all, 1 = Stripfilm), and its speed */
static int64_t ui_lv_t = 0;                     /* when they were last moved */
static double ui_tile_p = 1.0;                  /* 0 to 1: how much of the tiles of all shows (over a video) */
static SDL_Rect ui_sf_bt;                       /* v60: where the large tile of the Stripfilm view rests */
static double ui_sf_v = 0.0;                    /* v60: how fast the strip moves (tiles a second); the strip is a spring */
static double ui_sf_sq = 0.0;                   /* v60: 0 to 0.3: how much the speed squeezes the tiles of the strip together */
static SDL_Rect ui_tv_slot_r[96];               /* v60: where the rows put the tiles of the queue (the strip glides into these) */
static int ui_tv_slot_i[96], ui_tv_slot_n = 0;
static int64_t ui_tv_slot_at = 0, ui_tv_play_at = 0;
""", "statics")

# ---------------------------------------------------------------------------------------------------------------------
# 2. the copy of a video frame for the tiles is square cornered now (every tile rounds it itself when it is drawn)
rep("""        /* a video frame: keep a copy in its own shape, with rounded corners, for the video tiles */
        int rr = FFMIN(w, h) / 11, k;

        nt = av_malloc((size_t)w * h * 4);
        if (nt) {
            memcpy(nt, out, (size_t)w * h * 4);
            for (y = 0; y < rr; y++)
                for (x = 0; x < rr; x++) {
                    double dxx = rr - x - 0.5, dyy = rr - y - 0.5;
                    double cov = av_clipd(rr - sqrt(dxx * dxx + dyy * dyy) + 0.5, 0.0, 1.0);
                    int at[4] = { y * w + x, y * w + w - 1 - x, (h - 1 - y) * w + x, (h - 1 - y) * w + w - 1 - x };

                    for (k = 0; k < 4; k++)
                        nt[at[k] * 4 + 3] = (uint8_t)(nt[at[k] * 4 + 3] * cov);
                }
        }
""", """        /* a video frame: keep a copy in its own shape for the video tiles. v60: with square corners. Every tile rounds it when it is
           drawn (ui_flow_quad_round, by the Roundness setting); the corners that were baked in showed in the Stripfilm view */
        nt = av_malloc((size_t)w * h * 4);
        if (nt)
            memcpy(nt, out, (size_t)w * h * 4);
""", "native copy: square corners")

# a little pause after each picture, so reading a whole queue ahead of time never holds the video up
rep("""        ui_cov[k].state = px ? 1 : 3;
        SDL_UnlockMutex(ui_cov_mu);
    }
    return 0;
}
""", """        ui_cov[k].state = px ? 1 : 3;
        SDL_UnlockMutex(ui_cov_mu);
        SDL_Delay(6);                           /* v60: the queue is read ahead of time: leave the processor to the video */
    }
    return 0;
}
""", "cover thread pause")

# ---------------------------------------------------------------------------------------------------------------------
# 3. read the pictures of the queue as soon as it is filled
rep("""/* Is the queue view showing over a video (key L)? It also shows while the video shrinks into its tile or grows back. */
static int ui_flow_video(VideoState *is)
""", """/* v60: the pictures of the queue are read as soon as the queue is filled (the ones nearest to the playing item first), so the tiles
   of the Stripfilm view already have their thumbnails when it opens, and are not first asked for then. A few at a time. */
static void ui_cov_warm(void)
{
    static int last_n = -1, last_pos = -2, cursor = 0;
    int done = 0, lim;

    if (q_count <= 0 || q_pos < 0 || q_pos >= q_count)
        return;
    if (q_count != last_n || q_pos != last_pos) {       /* the queue or the playing item changed: a new round, from the playing item outwards */
        last_n = q_count;
        last_pos = q_pos;
        cursor = 0;
    }
    lim = 2 * FFMIN(q_count, 300) + 2;                  /* a long queue: the 300 nearest ones, the rest are read when they are shown */
    while (cursor < lim && done < 6) {
        int k = cursor++, off = (k + 1) / 2, i = (k & 1) ? q_pos + off : q_pos - off, w = 0, h = 0;

        if (i < 0 || i >= q_count || !q_items[i])
            continue;
        ui_cov_get(q_items[i], &w, &h);
        done++;
    }
}

/* Is the queue view showing over a video (key L)? It also shows while the video shrinks into its tile or grows back. */
static int ui_flow_video(VideoState *is)
""", "cover warm-up")

rep("""    int vid = is->video_st && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC);
    int64_t now = av_gettime_relative();

    if (ui_tile_fs_pending) {""", """    int vid = is->video_st && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC);
    int64_t now = av_gettime_relative();

    ui_cov_warm();                              /* v60 */
    if (ui_tile_fs_pending) {""", "warm-up call")

# ---------------------------------------------------------------------------------------------------------------------
# 4. a pause opens the Stripfilm view (only with a queue), not the tiles of all
rep("""        if (vid && q_count >= 2 && q_pos >= 0 && !ui_vflow) {
            ui_vflow_set(is, 1);
            ui_vflow_auto = 1;
        }""", """        if (vid && q_count >= 2 && q_pos >= 0 && !ui_vflow) {   /* v60: only when there is a queue: one item that is paused stays as it is */
            ui_vflow_set(is, 1);
            ui_sf_mode = 1;                     /* v60: the Stripfilm view, not the tiles of all */
            ui_vflow_auto = 1;
        }""", "pause opens Stripfilm")

# a view that opens from nothing starts straight in its layout (no gliding in from where it was left)
rep("""    ui_vflow = on;
    ui_sf_mode = 0;                     /* v57: a view opened another way is the tiles of all */
    ui_sf_lift_px = 0;""", """    ui_vflow = on;
    ui_sf_mode = 0;                     /* v57: a view opened another way is the tiles of all */
    ui_sf_lift_px = 0;
    if (on && ui_vflow_p < 0.02)
        ui_lv_t = 0;                    /* v60: it opens straight into its layout */""", "vflow_set restarts springs")

rep("""    ui_sf_pos = ui_sf_target = ui_tv_focus;     /* v57 */
    ui_sf_touch = 0;""", """    ui_sf_pos = ui_sf_target = ui_tv_focus;     /* v57 */
    ui_sf_v = 0.0;
    ui_sf_touch = 0;""", "reset strip speed")

rep("""        ui_vflow_auto = 0;
        ui_sf_p = 0.0;                          /* v57: the layout moves in */""", """        ui_vflow_auto = 0;
        if (ui_vflow_p < 0.02)
            ui_lv_t = 0;                        /* v60: it opens straight into its layout */""", "tv_enter restarts springs")

# strip -> tiles of all: the playing video is in focus and the rows are already there, so the large tile moves into its exact small tile
rep("""    } else {                                    /* from the strip to the tiles of all, from the tile that is in the middle of the strip */
        ui_tv_focus = av_clip((int)floor(ui_sf_target + 0.5), 0, q_count - 1);
        ui_sf_mode = 0;
    }""", """    } else {                                    /* v60: from the strip to the tiles of all, with the playing video in focus: the large tile moves into its small tile */
        int R, L;

        ui_tv_focus = av_clip(q_pos, 0, q_count - 1);
        ui_tv_dims(is, &R, &L);
        ui_tv_pos = ui_tv_focus % L;            /* the rows are already in place, so the tile it moves into does not move */
        ui_tv_row = ui_tv_focus / L;
        ui_sf_mode = 0;
    }""", "strip to tiles: exact tile")

# ---------------------------------------------------------------------------------------------------------------------
# 5. the rows: tell the strip where the tiles are, and leave the playing video to the large tile while the Stripfilm layout is still up
rep("""        if (tile.x + tile.w < -20 || tile.x > W + 20)
            continue;
        if (ui_tv_drag && ui_tv_press == item && ui_tv_pressec == R->sec)
            al = al / 3;                        /* the one that is being dragged leaves a faint place behind */""", """        if (tile.x + tile.w < -20 || tile.x > W + 20)
            continue;
        if (R->sec < 0 && ui_tv_slot_n < 96) {  /* v60: where this tile is: the tiles of the strip glide into these places */
            ui_tv_slot_i[ui_tv_slot_n] = item;
            ui_tv_slot_r[ui_tv_slot_n] = tile;
            ui_tv_slot_n++;
        }
        if (ui_tv_drag && ui_tv_press == item && ui_tv_pressec == R->sec)
            al = al / 3;                        /* the one that is being dragged leaves a faint place behind */""", "rows: slots")

rep("""            ui_tv_play_rect = tile;             /* v59: the large tile of the Stripfilm view moves into this one */
            ui_tv_play_w = W;
            ui_tv_play_h = is->height;
            ui_flow_quad_round(ui_live_tex, &lr, al, md, 0.0, (int)(FFMIN(lr.w, lr.h) / 11.0 * ep));""", """            ui_tv_play_rect = tile;             /* v59: the large tile of the Stripfilm view moves into this one */
            ui_tv_play_w = W;
            ui_tv_play_h = is->height;
            ui_tv_play_at = now;
            if (ui_sf_p <= 0.004)               /* v60: while the Stripfilm layout is up its large tile is the one that moves here: never two of them */
                ui_flow_quad_round(ui_live_tex, &lr, al, md, 0.0, (int)(FFMIN(lr.w, lr.h) / 11.0 * ep));""", "rows: playing tile")

# ---------------------------------------------------------------------------------------------------------------------
# 6. strip tiles: square corners for covers and the file icon (their corners are baked in, so the picture is cropped a little)
between("/* v57: one tile of the Stripfilm view, in its own shape, fitted into the box bw x bh.", "/* A rounded ring (thickness th) around a tile",
r'''/* v60: a tile with square corners from a texture that has see-through corners baked in (a cover, the file icon): the picture is
   cropped by a little more than those corners are deep, so no round corner shows in the Stripfilm view */
static void ui_sf_quad_sq(SDL_Texture *tex, const SDL_Rect *t, int al, int md)
{
    SDL_Vertex v[4];
    static const int idx[6] = { 0, 1, 2, 1, 3, 2 };
    const float in = 0.034f;
    int k;

    for (k = 0; k < 4; k++) {
        v[k].position.x = (float)(t->x + ((k & 1) ? t->w : 0));
        v[k].position.y = (float)(t->y + ((k & 2) ? t->h : 0));
        v[k].tex_coord.x = (k & 1) ? 1.0f - in : in;
        v[k].tex_coord.y = (k & 2) ? 1.0f - in : in;
        v[k].color.r = (Uint8)md;
        v[k].color.g = (Uint8)md;
        v[k].color.b = (Uint8)md;
        v[k].color.a = (Uint8)av_clip(al, 0, 255);
    }
    SDL_RenderGeometry(renderer, tex, v, 4, idx, 6);
}

/* v57: one tile of the Stripfilm view, in its own shape, fitted into the box bw x bh. side = -1 or 1: a tile that peeks out from
   behind the large one, its outer edge is "edge" pixels from the middle. live = the video that plays (its picture is the live one).
   Returns 1 if it is a preview that plays. */
static int ui_sf_put(const char *path, int live, double cx, double cy, double bw, double bh, int side, double edge,
                     int al, int md, int shadow, SDL_Rect *out)
{
    SDL_Texture *tex = NULL;
    int pw = 0, ph = 0, cw = 0, ch = 0, nw, nh, pv = 0, baked = 0;
    double asp = (live && ui_live_ok && ui_live_rect.h > 0) ? (double)ui_live_rect.w / ui_live_rect.h : ui_cov_aspect(path);

    if (!live)
        tex = ui_pv_get(path, &pw, &ph);        /* the picture that plays under the mouse */
    if (tex) {
        pv = 1;
        if (asp <= 0.0)
            asp = (double)pw / ph;
    }
    if (asp <= 0.0)
        nw = nh = (int)FFMIN(bw, bh);
    else if (bw / bh > asp) {
        nh = (int)bh;
        nw = (int)(bh * asp);
    } else {
        nw = (int)bw;
        nh = (int)(bw / asp);
    }
    out->w = FFMAX(nw, 2);
    out->h = FFMAX(nh, 2);
    if (side)
        cx += side * (edge - out->w / 2.0);
    out->x = (int)(cx - out->w / 2.0);
    out->y = (int)(cy - out->h / 2.0);
    if (live && ui_live_ok && ui_live_tex)
        tex = ui_live_tex;
    if (!tex) {
        tex = ui_cov_native(path, &cw, &ch);
        if (!tex) {
            baked = 1;                          /* a cover or the icon: its corners are in the picture */
            tex = ui_cov_get(path, &cw, &ch);
            if (!tex)
                tex = ui_flow_icon();
        }
    }
    if (!tex)
        return pv;
    if (shadow)
        ui_tile_shadow(tex, out, al, 0.0, 0);   /* v58: square corners, whatever the roundness setting is */
    if (baked)
        ui_sf_quad_sq(tex, out, al, md);        /* v60 */
    else
        ui_flow_quad_round(tex, out, al, md, 0.0, 0);
    return pv;
}

''', "ui_sf_put square")

# ---------------------------------------------------------------------------------------------------------------------
# 7. the Stripfilm view itself: strip scrolling like the reference, the large tile as a separate step drawn after the rows
new_sf = r'''/* v60: where the rows put the tile of this queue number (this frame or the last), if it is in sight */
static int ui_tv_slot_get(int item, SDL_Rect *r, int64_t now)
{
    int k;

    if (now - ui_tv_slot_at > 250000)
        return 0;
    for (k = 0; k < ui_tv_slot_n; k++)
        if (ui_tv_slot_i[k] == item) {
            *r = ui_tv_slot_r[k];
            return 1;
        }
    return 0;
}

static double ui_sf_smooth(double x)
{
    x = av_clipd(x, 0.0, 1.0);
    return x * x * (3.0 - 2.0 * x);
}

/* v60: the Stripfilm view and its transitions. The view has two springs (see ui_lv, ui_lay): how far it is open, and its layout.
   ui_sf_p = the layout (1 = Stripfilm), so (1 - ui_sf_p) is how far everything has glided towards the tiles of all.
   Drawn in two parts: this one is everything but the large tile (the title, the glass band, the strip, the tiles behind the large
   one). The large tile is drawn after the rows (ui_sf_draw_big), so it can move into the exact place of the small tile of the video.
   The strip scrolls like the reference: a critically damped spring (it starts gently and never overshoots), the tile in the middle is
   the largest and the others get smaller and dimmer the farther they are, a glow behind the middle one, and the tiles are squeezed
   together by the speed and slowly spring back. */
static void ui_sf_draw(VideoState *is, double dt, int64_t now, double ep, int hs, int hi)
{
    int W = is->width, H = is->height, band_h, y0, y1, c0, k0, k1, K, dd, dn, tw, th, margin = 14;
    double fa = ui_sf_p * ep, aw, ah, asp, bwid, bhgt, pitch0, pitch, sy, cy, half, cmin, cmax, bm = av_clipd(1.0 - ui_sf_p, 0.0, 1.0);
    SDL_Rect bt, r, band;
    char name[320];

    th = H < 460 ? 60 : 92;                             /* the strip has one fixed height, whatever the window */
    tw = (int)(th * 1.6);
    ui_sf_tw = tw;
    ui_sf_th = th;
    band_h = th + 24;
    ui_sf_lift_px = fa > 0.02 ? 1 : 0;                  /* the bars are drawn inside the large tile (ui_sf_box) */
    y0 = H < 460 ? 46 : 52;                             /* the title is above the large tile, so the tile is as high as it can be */
    y1 = H - band_h - 18;
    ah = FFMAX(y1 - y0, 40);
    aw = W * 0.76;
    asp = (ui_live_ok && ui_live_rect.h > 0) ? (double)ui_live_rect.w / ui_live_rect.h : 16.0 / 9.0;
    bwid = aw;
    bhgt = bwid / asp;
    if (bhgt > ah) {
        bhgt = ah;
        bwid = bhgt * asp;
    }
    bt.w = FFMAX((int)bwid, 8);
    bt.h = FFMAX((int)bhgt, 8);
    bt.x = W / 2 - bt.w / 2;
    bt.y = y0 + (int)((ah - bhgt) / 2.0);
    ui_sf_bt = bt;
    cy = bt.y + bt.h / 2.0;

    pitch0 = tw + 12;
    half = (W / 2.0 - margin - tw * 0.8 / 2.0 - pitch0 * 0.10) / pitch0;   /* tiles from the middle of the window to the first tile, when the strip starts at the left */
    if (q_count - 1 <= 2.0 * half)
        cmin = cmax = (q_count - 1) / 2.0;              /* a short strip is centred */
    else {
        cmin = half;                                    /* a long one starts at the far left, even at its first item ... */
        cmax = q_count - 1 - half;                      /* ... and ends at the far right */
    }
    ui_sf_target = av_clipd(ui_sf_target, cmin, cmax);
    if (ui_sf_touch && now - ui_sf_touch > 180000) {    /* the hand has left: the strip settles on a whole tile */
        ui_sf_target = av_clipd(floor(ui_sf_target + 0.5), cmin, cmax);
        ui_sf_touch = 0;
    }
    {                                                   /* the strip is a critically damped spring: no sudden start, no overshoot */
        double w = 11.0, sub = dt / 4.0, p0 = ui_sf_pos, vel, want;
        int k;

        for (k = 0; k < 4; k++) {
            ui_sf_v += (w * w * (ui_sf_target - ui_sf_pos) - 2.0 * w * ui_sf_v) * sub;
            ui_sf_pos += ui_sf_v * sub;
        }
        if (fabs(ui_sf_target - ui_sf_pos) < 0.003 && fabs(ui_sf_v) < 0.02) {
            ui_sf_pos = ui_sf_target;
            ui_sf_v = 0.0;
        } else {
            ui_tv_moving = 1;
        }
        vel = dt > 0.0 ? fabs(ui_sf_pos - p0) / dt : 0.0;
        want = av_clipd(vel * 0.045, 0.0, 0.30);        /* the faster it moves the closer the tiles come ... */
        ui_sf_sq += (want - ui_sf_sq) * (1.0 - exp(-dt * (want > ui_sf_sq ? 14.0 : 3.5)));    /* ... and they spring back slowly */
        if (ui_sf_sq < 0.003 && want < 0.003)
            ui_sf_sq = 0.0;
        else
            ui_tv_moving = 1;
    }
    if (ui_sf_touch)
        ui_tv_moving = 1;
    pitch = pitch0 * (1.0 - ui_sf_sq);

    /* the tiles of the queue that are before and after the video that plays, behind the large tile */
    for (dn = -1; dn <= 1; dn += 2) {
        int ni = q_pos + dn;

        if (ni < 0 || ni >= q_count)
            continue;
        if (ui_sf_put(q_items[ni], 0, W / 2.0, cy, bt.w * 0.84, bt.h * 0.84, dn, 0.59 * bt.w, (int)(190 * fa), 165, 1, &r))
            ui_tv_moving = 1;
        if (ui_tvh_n < 128) {
            ui_tvh[ui_tvh_n].r = r;
            ui_tvh[ui_tvh_n].sec = -1;
            ui_tvh[ui_tvh_n].item = ni;
            ui_tvh_n++;
        }
    }
    if (ui_tvh_n < 128) {                               /* a tap on the large tile */
        ui_tvh[ui_tvh_n].r = bt;
        ui_tvh[ui_tvh_n].sec = -1;
        ui_tvh[ui_tvh_n].item = q_pos;
        ui_tvh_n++;
    }

    /* the title of the video that plays, above its large tile */
    ui_tv_name(q_items[q_pos], name, sizeof(name));
    ui_fit_text(name, 18, bt.w);
    ui_label_c(W / 2, bt.y - 20, name, 18, 255, 255, 255, (int)(255 * fa));

    /* the band behind the strip: flat dark frosted glass, edge to edge, like the one behind the seek and volume bars */
    band.x = 0;
    band.w = W;
    band.h = band_h;
    band.y = H - band_h + (int)((1.0 - fa) * band_h);
    ui_glass_bar(&band);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);

    /* the strip: no titles. The tile in the middle (ui_sf_pos) is the largest, the others get smaller and dimmer, and the far ones
       first so the middle one is on top. When the view goes on to the tiles of all, each tile glides into its place there. */
    sy = H - band_h / 2.0 + (1.0 - fa) * band_h;
    K = FFMIN((int)(W / (2.0 * pitch0)) + 4, 40);
    c0 = av_clip((int)floor(ui_sf_pos + 0.5), 0, q_count - 1);
    k0 = FFMAX(c0 - K, 0);
    k1 = FFMIN(c0 + K, q_count - 1);
    for (dd = K; dd >= 0; dd--) {
        int sd;

        for (sd = -1; sd <= 1; sd += 2) {
            int i = c0 + sd * dd, play, al, md, ti;
            double d, ad, sc, x, tcx, tcy, tbw, tbh, goal, lf, sl = 1.0;
            SDL_Rect slot;

            if ((dd == 0 && sd > 0) || i < k0 || i > k1)
                continue;
            play = i == q_pos;
            ti = i % 4093;
            d = i - ui_sf_pos;
            ad = fabs(d);
            sc = 1.0 - 0.17 * ui_sf_smooth(ad) - 0.02 * av_clipd(ad - 1.0, 0.0, 4.0);      /* the middle one is the largest */
            x = W / 2.0 + d * pitch + (d < 0 ? -1.0 : 1.0) * FFMIN(ad, 1.0) * pitch0 * 0.10;     /* room around the middle one */
            if (x < -tw || x > W + tw)
                continue;
            goal = (hs == -1 && hi == i) ? 1.0 : 0.0;   /* the tile under the mouse only brightens (and plays its preview): no pop */
            lf = ui_tv_lift[ti];
            lf += (goal - lf) * (1.0 - exp(-dt * 14.0));
            if (fabs(goal - lf) < 0.004)
                lf = goal;
            else
                ui_tv_moving = 1;
            ui_tv_lift[ti] = lf;
            al = (int)((play ? 255.0 : 255.0 * av_clipd(1.0 - 0.07 * ad, 0.62, 1.0)) * ui_sf_p);
            al += (int)((255 * ui_sf_p - al) * lf);
            md = play ? 255 : FFMIN(255, 228 - (int)(10 * FFMIN(ad, 3.0)) + (int)(27 * lf));
            if (ui_tv_drag && ui_tv_press == i && ui_tv_pressec == -1)
                al = al / 3;                            /* the one that is being dragged leaves a faint place behind */
            tcx = x;
            tcy = sy;
            tbw = tw * sc;
            tbh = th * sc;
            if (play) {
                sl = 1.0 - av_clipd(bm * 3.0, 0.0, 1.0);       /* its place in the tiles of all is taken by the large tile */
            } else if (bm > 0.0) {
                if (ui_tv_slot_get(i, &slot, now)) {            /* glide into the place of this tile in the tiles of all, and hand over to it */
                    tcx += (slot.x + slot.w / 2.0 - tcx) * bm;
                    tcy += (slot.y + slot.h / 2.0 - tcy) * bm;
                    tbw += (slot.w - tbw) * bm;
                    tbh += (slot.h - tbh) * bm;
                    sl = 1.0 - ui_sf_smooth((bm - 0.35) / 0.65);
                } else {
                    sl = 1.0 - bm;
                }
                ui_tv_moving = 1;
            }
            al = (int)(al * sl);
            if (al <= 0)
                continue;
            if (ad < 0.6)                               /* a soft glow in the bar color behind the middle tile, like the reference */
                ui_tv_glow(tcx, tcy, tbw * 0.95, tbh * 0.95, (int)(110 * (1.0 - ad / 0.6) * (al / 255.0)));
            if (ui_sf_put(q_items[i], play, tcx, tcy, tbw, tbh, 0, 0.0, al, md, 0, &r))
                ui_tv_moving = 1;
            if (play) {                                 /* the mark of the video that plays: a white ring */
                SDL_Rect rg = { r.x - 4, r.y - 4, r.w + 8, r.h + 8 };

                SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
                SDL_SetRenderDrawColor(renderer, 255, 255, 255, (int)(235 * ui_sf_p * sl));
                ui_sf_ring(&rg, 0, 3);
            }
            if (ui_tvh_n < 128) {
                ui_tvh[ui_tvh_n].r = r;
                ui_tvh[ui_tvh_n].sec = -1;
                ui_tvh[ui_tvh_n].item = i;
                ui_tvh_n++;
            }
        }
    }
}

/* v60: the large tile of the Stripfilm view: the video that plays. It is drawn after the rows, so the place of its small tile in the
   tiles of all (this frame's, ui_tv_play_rect) is known exactly: it glides into that very tile and keeps square corners until it
   is there, where the rows take over (they leave the playing video to this tile until then). It also moves the seek and volume bars:
   they sit in the bottom of this tile, and glide to the bottom of the window with it (ui_sf_box). */
static void ui_sf_draw_big(VideoState *is, double ep, int64_t now)
{
    int W = is->width, H = is->height, la = 255, rr, found = 0;
    double fa = ui_sf_p * ep, bm = av_clipd(1.0 - ui_sf_p, 0.0, 1.0);
    SDL_Rect bt = ui_sf_bt, lr = bt, to = bt, r;

    if (fa <= 0.004)
        return;
    if (ui_live_ok && ui_live_tex) {
        if (ep < 1.0) {                                 /* on its way from the full window */
            lr.x = ui_live_rect.x + (int)((bt.x - ui_live_rect.x) * ep);
            lr.y = ui_live_rect.y + (int)((bt.y - ui_live_rect.y) * ep);
            lr.w = ui_live_rect.w + (int)((bt.w - ui_live_rect.w) * ep);
            lr.h = ui_live_rect.h + (int)((bt.h - ui_live_rect.h) * ep);
        }
        la = (int)(255 * av_clipd(ui_sf_p * 4.0, 0.0, 1.0));
        if (bm > 0.0) {                                 /* on its way into its small tile */
            if (now - ui_tv_play_at < 250000 && ui_tv_play_w == W && ui_tv_play_h == H) {
                to = ui_tv_play_rect;
                found = to.x + to.w > 0 && to.x < W && to.y + to.h > 0 && to.y < H;
            }
            if (!found) {                               /* its small tile is not in sight: it shrinks towards the middle and fades */
                to.w = (int)(bt.w * 0.6);
                to.h = (int)(bt.h * 0.6);
                to.x = W / 2 - to.w / 2;
                to.y = bt.y + (bt.h - to.h) / 2;
                la = (int)(la * (1.0 - bm));
            }
            lr.x += (int)((to.x - lr.x) * bm);
            lr.y += (int)((to.y - lr.y) * bm);
            lr.w += (int)((to.w - lr.w) * bm);
            lr.h += (int)((to.h - lr.h) * bm);
        }
        rr = (int)(FFMIN(lr.w, lr.h) / 11.0 * bm * ep);                   /* square in the Stripfilm layout, the roundness of the tiles in the other */
        ui_tv_glow(bt.x + bt.w / 2.0, bt.y + bt.h / 2.0, bt.w * 0.62, bt.h * 0.75, (int)(110 * fa * (1.0 - bm)));
        ui_tile_shadow(ui_live_tex, &lr, la, 0.0, rr);
        ui_flow_quad_round(ui_live_tex, &lr, la, 255, 0.0, rr);
    } else {
        ui_sf_put(q_items[q_pos], 0, W / 2.0, bt.y + bt.h / 2.0, bt.w, bt.h, 0, 0.0, (int)(255 * ui_sf_p), 255, 1, &r);
        lr = r;
    }
    ui_sf_box.x = (int)(lr.x * (1.0 - bm));             /* the bars: the bottom of the large tile, gliding to the bottom of the window */
    ui_sf_box.w = (int)(lr.w + (W - lr.w) * bm);
    ui_sf_box.y = (int)(lr.y * (1.0 - bm));
    ui_sf_box.h = (int)(lr.h + (H - lr.h) * bm);
}

'''
between("/* v59: the Stripfilm view: the video that plays in a large tile with its title above it", "static void ui_tv_draw(VideoState *is)", new_sf, "ui_sf_draw / ui_sf_draw_big")

# ---------------------------------------------------------------------------------------------------------------------
# 8. ui_tv_draw: two springs instead of one level; the large tile after the rows
new_springs = r'''    if (vm) {                                   /* v60: two smooth moves: how far the view is open, and its layout (0 = tiles of all, 1 = Stripfilm) */
        double want = ui_vflow ? 1.0 : 0.0, lt = ui_vflow ? ((ui_sf_mode && !ui_tv_q[0]) ? 1.0 : 0.0) : ui_lay;   /* a view that closes keeps its layout */
        double dtv, wa = want > 0.5 ? 11.0 : 13.0, wl = 11.0, sub;
        int k;

        if (now - ui_lv_t > 350000) {           /* the view has just opened: it starts in its own layout, from where the video is */
            ui_lv = ui_vflow_p > 0.999 ? 1.0 : ui_vflow_p;
            ui_lv_v = 0.0;
            ui_lay = lt;
            ui_lay_v = 0.0;
        }
        dtv = ui_lv_t ? av_clipd((now - ui_lv_t) / 1000000.0, 0.0, 0.1) : 0.0;
        ui_lv_t = now;
        sub = dtv / 4.0;
        for (k = 0; k < 4; k++) {               /* critically damped springs: they start gently, never overshoot, and a change of mind stays smooth */
            ui_lv_v += (wa * wa * (want - ui_lv) - 2.0 * wa * ui_lv_v) * sub;
            ui_lv += ui_lv_v * sub;
            ui_lay_v += (wl * wl * (lt - ui_lay) - 2.0 * wl * ui_lay_v) * sub;
            ui_lay += ui_lay_v * sub;
        }
        ui_lv = av_clipd(ui_lv, 0.0, 1.0);
        ui_lay = av_clipd(ui_lay, 0.0, 1.0);
        if (fabs(want - ui_lv) < (want > 0.5 ? 0.003 : 0.012) && fabs(ui_lv_v) < 0.05) {    /* the last bit of the way back is not seen */
            ui_lv = want;
            ui_lv_v = 0.0;
        } else {
            ui_tv_moving = 1;
        }
        if (fabs(lt - ui_lay) < 0.003 && fabs(ui_lay_v) < 0.05) {
            ui_lay = lt;
            ui_lay_v = 0.0;
        } else {
            ui_tv_moving = 1;
        }
        ui_vflow_p = ui_lv;
        ui_vflow_ep = ui_lv;
        ep = ui_lv;
        ui_sf_p = ui_lay;                       /* the Stripfilm layout */
        ui_tile_p = 1.0 - ui_lay;               /* the tiles of all */
        ui_vflow_t = now;
    } else {
        ui_sf_p = 0.0;
        ui_tile_p = 1.0;
        ui_lv_t = 0;
    }
'''
between("    if (vm) {                                   /* v59: one smooth move through the levels", "    if (!vm || ui_sf_p <= 0.004)\n        ui_sf_lift_px = 0;", new_springs, "ui_tv_draw springs")

rep("""        sh = av_clipd(FFMIN(FFMIN(rp * 0.74, rp - 46.0), W * 0.24), 40.0, 340.0);      /* v38: bigger */
        ui_tv_pos += (col - ui_tv_pos) * (1.0 - exp(-dt * 9.0));""", """        sh = av_clipd(FFMIN(FFMIN(rp * 0.74, rp - 46.0), W * 0.24), 40.0, 340.0);      /* v38: bigger */
        ui_tv_slot_n = 0;                       /* v60: this frame's places of the tiles (the strip reads them in the next frame, the large tile below in this one) */
        ui_tv_slot_at = now;
        ui_tv_pos += (col - ui_tv_pos) * (1.0 - exp(-dt * 9.0));""", "ui_tv_draw: slots reset")

rep("""    if (ui_tvc_open)
        ui_tvc_draw(is);
    SDL_RenderSetClipRect(renderer, NULL);
}

/* ---- the mouse ---- */""", """    if (!ui_tv_q[0] && vm && ui_sf_p > 0.004)
        ui_sf_draw_big(is, ep, now);            /* v60: the large tile, after the rows */
    if (ui_tvc_open)
        ui_tvc_draw(is);
    SDL_RenderSetClipRect(renderer, NULL);
}

/* ---- the mouse ---- */""", "ui_tv_draw: large tile after the rows")

# the header comment of the section says what v60 is, so a second run is refused
rep("""/* v57: the Stripfilm view and spring loaded scrolling. For a video, a two finger swipe up opens""", """/* v60: the Stripfilm view and its transitions (see ui_sf_draw). v57: the Stripfilm view and spring loaded scrolling. For a video, a two finger swipe up opens""", "marker")

# ---------------------------------------------------------------------------------------------------------------------
# 9. folders play in the order the picker shows them (Modified, Size, or Name backwards), not always A to Z
rep("""static int ui_pk_ord_cmp(const void *a, const void *b)
{
    const UiPkEnt *x = *(UiPkEnt * const *)a, *y = *(UiPkEnt * const *)b;
""", r'''static int ui_pk_ds_cmp(const void *a, const void *b)
{
    const UiPkEnt *x = a, *y = b;
    int c = 0;

    if (ui_pk_sortk == 1 && x->mtime != y->mtime)
        c = x->mtime < y->mtime ? -1 : 1;
    else if (ui_pk_sortk == 2 && x->size != y->size)
        c = x->size < y->size ? -1 : 1;
    if (c)
        return ui_pk_desc ? -c : c;
    c = natural_cmp(x->name, y->name);
    return ui_pk_sortk == 0 && ui_pk_desc ? -c : c;
}

/* v60: a folder plays (or is added) in the order the picker shows it: by Name, Modified or Size, up or down. By Name from A to Z the
   player already adds a folder in that order, so that is left to it. */
static void ui_pk_send_dir(VideoState *is, char what, const char *dir)
{
    struct stat st;
    DIR *d;
    struct dirent *e;
    UiPkEnt *v = NULL, *bigger;
    int n = 0, cap = 0, i;
    char full[PATH_MAX + 300];

    if ((ui_pk_sortk == 0 && !ui_pk_desc) || stat(dir, &st) != 0 || !S_ISDIR(st.st_mode) || !(d = opendir(dir))) {
        ui_pk_send(is, what, dir);
        return;
    }
    while ((e = readdir(d))) {
        if (e->d_name[0] == '.' || !is_media_file(e->d_name))
            continue;
        snprintf(full, sizeof(full), "%s/%s", dir, e->d_name);
        if (stat(full, &st) != 0 || !S_ISREG(st.st_mode))
            continue;
        if (n >= cap) {
            bigger = realloc(v, (size_t)(cap ? cap * 2 : 64) * sizeof(*v));
            if (!bigger)
                break;
            v = bigger;
            cap = cap ? cap * 2 : 64;
        }
        memset(&v[n], 0, sizeof(v[n]));
        v[n].name = av_strdup(e->d_name);
        if (!v[n].name)
            break;
        v[n].size = st.st_size;
        v[n].mtime = st.st_mtime;
        n++;
    }
    closedir(d);
    if (n <= 0) {
        free(v);
        ui_pk_send(is, what, dir);
        return;
    }
    qsort(v, n, sizeof(*v), ui_pk_ds_cmp);
    for (i = 0; i < n; i++) {
        snprintf(full, sizeof(full), "%s/%s", dir, v[i].name);
        if (!i)
            ui_pk_send(is, what, full);         /* the first one starts it (and is remembered as a recent place) */
        else
            ui_inbox_send('a', full);           /* the rest follow in the order they were sorted in */
        av_free(v[i].name);
    }
    free(v);
}

/* A file is sent as it is, a folder in the order the picker shows */
static void ui_pk_send_path(VideoState *is, char what, const char *path)
{
    struct stat st;

    if (stat(path, &st) == 0 && S_ISDIR(st.st_mode))
        ui_pk_send_dir(is, what, path);
    else
        ui_pk_send(is, what, path);
}

static int ui_pk_ord_cmp(const void *a, const void *b)
{
    const UiPkEnt *x = *(UiPkEnt * const *)a, *y = *(UiPkEnt * const *)b;
''', "picker: sorted folder send helpers")

rep("""        } else if (ui_pk_nrw > 0) {
            ui_pk_send(is, 'o', ui_pk_dir);
            ui_pk_close(is);
        }""", """        } else if (ui_pk_nrw > 0) {
            ui_pk_send_dir(is, 'o', ui_pk_dir);     /* v60: in the order the folder is sorted in here */
            ui_pk_close(is);
        }""", "picker: play the open folder")

rep("""    ui_pk_path_of(e, path, sizeof(path));
    ui_pk_send(is, 'o', path);                  /* a folder plays everything in it */
    ui_pk_close(is);""", """    ui_pk_path_of(e, path, sizeof(path));
    ui_pk_send_path(is, 'o', path);             /* a folder plays everything in it (v60: in the order it is sorted in) */
    ui_pk_close(is);""", "picker: play a chosen folder")

rep("""        else
            snprintf(path, sizeof(path), "%s", ui_pk_dir);
        ui_pk_send(is, 'a', path);
        ui_pk_close(is);""", """        else
            snprintf(path, sizeof(path), "%s", ui_pk_dir);
        ui_pk_send_path(is, 'a', path);         /* v60 */
        ui_pk_close(is);""", "picker: add a folder")

rep("""    } else if (act == UI_PK_A_PLAY) {
        ui_pk_send(is, 'o', ui_pk_cm_path);
        ui_pk_close(is);""", """    } else if (act == UI_PK_A_PLAY) {
        ui_pk_send_path(is, 'o', ui_pk_cm_path);    /* v60 */
        ui_pk_close(is);""", "picker menu: play")

rep("""        ui_pk_send(is, 'a', ui_pk_cm_path);     /* the picker stays open: more can be added */""",
    """        ui_pk_send_path(is, 'a', ui_pk_cm_path);    /* the picker stays open: more can be added (v60: a folder in its sorted order) */""",
    "picker menu: add")

# ---------------------------------------------------------------------------------------------------------------------
open(path, "w", encoding="utf-8").write(src)
print("v60 applied to %s (%d edits):" % (path, len(done)))
for d in done:
    print("  ok:", d)
print("%+d bytes" % (len(src) - len(orig)))
