#!/usr/bin/env python3
"""patch_queue_v59.py: no spring-loaded scrolling, a strip that starts at the left, a taller strip, smooth chained transitions.

Applies on top of v58 (fftools/ffplay.c).  Usage:  python3 patch_queue_v59.py [path/to/ffplay.c]
Every edit must match exactly once; if any edit does not, nothing is written.
"""
import os
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/build/ffmpeg-6.1.1/fftools/ffplay.c")
EDITS = []


def patch(name, old, new):
    EDITS.append((name, None, old, new))


def region(name, start, end, new):
    """Replace everything from start up to (not including) end."""
    EDITS.append((name, end, start, new))


# ---------------------------------------------------------------------------------------------------------------------------
# 1. no more spring-loaded scrolling: back to the scrolling from before the Stripfilm view
# ---------------------------------------------------------------------------------------------------------------------------
patch("squeeze constants removed",
'''#define UI_SQ_PITCH 0.12                        /* v58: at full speed the tiles come this much closer together ... */
#define UI_SQ_SIZE 0.12                         /* ... and shrink as much, so they never touch (it was 0.40 and 0.12: they overlapped) */
''',
'')

patch("squeeze state replaced by the level of the view",
'''static double ui_sq = 0.0;                      /* 0 to 1: how much the scrolling tiles are squeezed together right now */
''',
'''static double ui_lv = 0.0, ui_lv_v = 0.0;       /* v59: the level of the view, smoothly: 0 = the full video, 1 = the Stripfilm view, 2 = the tiles of all (and its speed) */
static int64_t ui_lv_t = 0;                     /* when it was last moved */
static double ui_tile_p = 1.0;                  /* 0 to 1: how far the tiles of all have come in (over a video) */
static SDL_Rect ui_tv_play_rect;                /* where the small tile of the playing video was drawn last: the large tile moves into it */
static int ui_tv_play_w = 0, ui_tv_play_h = 0;  /* the window size that was for */
''')

patch("squeeze reset removed",
'''    ui_sq = 0.0;
    ui_tv_dims(is, &R, &L);''',
'''    ui_tv_dims(is, &R, &L);''')

patch("tile spacing as before",
'''    double pitch = R->sw * 0.95 * (1.0 - UI_SQ_PITCH * ui_sq);     /* v57: the tiles squeeze together while they scroll */''',
'''    double pitch = R->sw * 1.08;''')

patch("tile size as before",
'''        bw = R->sw * sc * (1.0 - UI_SQ_SIZE * ui_sq);
        bh = R->sh * sc * (1.0 - UI_SQ_SIZE * ui_sq);''',
'''        bw = R->sw * sc;
        bh = R->sh * sc;''')

patch("scroll speed as before: row of tiles",
'''ui_tv_pos += (col - ui_tv_pos) * (1.0 - exp(-dt * 13.0));''',
'''ui_tv_pos += (col - ui_tv_pos) * (1.0 - exp(-dt * 9.0));''')
patch("scroll speed as before: rows",
'''ui_tv_row += (rw - ui_tv_row) * (1.0 - exp(-dt * 13.0));''',
'''ui_tv_row += (rw - ui_tv_row) * (1.0 - exp(-dt * 9.0));''')
patch("scroll speed as before: search sections",
'''sec->pos += (sec->target - sec->pos) * (1.0 - exp(-dt * 13.0));''',
'''sec->pos += (sec->target - sec->pos) * (1.0 - exp(-dt * 9.0));''')

# ---------------------------------------------------------------------------------------------------------------------------
# 2. smooth, chained transitions: full video -> Stripfilm -> tiles of all (and back), one continuous motion
# ---------------------------------------------------------------------------------------------------------------------------
region("one level that moves smoothly",
'''    if (vm) {                                   /* the video shrinks into its tile (or grows back): the same animation as before */''',
'''    if (q_pos != last_q) {                      /* a new item started: the focus goes to it */''',
'''    if (vm) {                                   /* v59: one smooth move through the levels: 0 = the full video, 1 = Stripfilm, 2 = the tiles of all */
        double lt = !ui_vflow ? 0.0 : (ui_sf_mode && !ui_tv_q[0]) ? 1.0 : 2.0, dtv, a, b, w = 12.0, sub;
        int k;

        if (now - ui_lv_t > 350000) {           /* the view has just opened: start from where the video flow is */
            ui_lv = ui_vflow_p > 0.999 ? ((ui_sf_mode && !ui_tv_q[0]) ? 1.0 : 2.0) : ui_vflow_p;
            ui_lv_v = 0.0;
        }
        dtv = ui_lv_t ? av_clipd((now - ui_lv_t) / 1000000.0, 0.0, 0.1) : 0.0;
        ui_lv_t = now;
        sub = dtv / 4.0;
        for (k = 0; k < 4; k++) {               /* a critically damped spring: it starts gently, never overshoots, and the middle level is passed
                                                   without stopping, so each step builds on the one before (a change of mind stays smooth too) */
            ui_lv_v += (w * w * (lt - ui_lv) - 2.0 * w * ui_lv_v) * sub;
            ui_lv += ui_lv_v * sub;
        }
        ui_lv = av_clipd(ui_lv, 0.0, 2.0);
        if (fabs(lt - ui_lv) < 0.003 && fabs(ui_lv_v) < 0.05) {
            ui_lv = lt;
            ui_lv_v = 0.0;
        } else {
            ui_tv_moving = 1;
        }
        a = av_clipd(ui_lv, 0.0, 1.0);          /* 0 to 1: full video -> Stripfilm */
        b = av_clipd(ui_lv - 1.0, 0.0, 1.0);    /* 0 to 1: Stripfilm -> tiles of all */
        b = b * b * (3.0 - 2.0 * b);
        ui_vflow_p = a;
        ui_vflow_ep = a * a * (3.0 - 2.0 * a);
        ep = ui_vflow_ep;
        ui_sf_p = ui_lv <= 1.0 ? ep : 1.0 - b;
        ui_tile_p = b;
        ui_vflow_t = now;
    } else {
        ui_sf_p = 0.0;
        ui_tile_p = 1.0;
        ui_lv_t = 0;
    }
    if (!vm || ui_sf_p <= 0.004)
        ui_sf_lift_px = 0;
''')

patch("tiles come in with the second step",
'''            al = (int)(al * (1.0 - ui_sf_p));   /* v57: the tiles fade while the Stripfilm layout comes in */''',
'''            al = (int)(al * ui_tile_p);         /* v59: the tiles come in with the second step (Stripfilm -> tiles of all) */''')

patch("tiles rise into place",
'''        tile.y = R->cy + (int)((1.0 - ease) * 36.0) - nh / 2 - (int)(6 * lf);''',
'''        tile.y = R->cy + (int)((1.0 - ease) * 36.0) + (vm ? (int)((1.0 - ui_tile_p) * 36.0) : 0) - nh / 2 - (int)(6 * lf);''')

patch("remember where the playing small tile is",
'''            ui_flow_quad_round(ui_live_tex, &lr, al, md, 0.0, (int)(FFMIN(lr.w, lr.h) / 11.0 * ep));''',
'''            ui_tv_play_rect = tile;             /* v59: the large tile of the Stripfilm view moves into this one */
            ui_tv_play_w = W;
            ui_tv_play_h = is->height;
            ui_flow_quad_round(ui_live_tex, &lr, al, md, 0.0, (int)(FFMIN(lr.w, lr.h) / 11.0 * ep));''')

# ---------------------------------------------------------------------------------------------------------------------------
# 3. the Stripfilm layout: starts at the left, taller strip, title above the large tile, the large tile moves into the small one
# ---------------------------------------------------------------------------------------------------------------------------
region("the Stripfilm layout",
'''/* v58: the Stripfilm view: the video that plays in a large tile''',
'''static void ui_tv_draw(VideoState *is)
{''',
'''/* v59: the Stripfilm view: the video that plays in a large tile with its title above it and the seek and volume bars in its bottom, and
   the whole queue as a strip of small tiles on a flat dark frosted band at the bottom of the window. The strip has one fixed height, its
   tiles are square and never change size under the mouse. It starts at the far left when it is longer than the window, and is centred
   when it is short. The large tile moves into the small tile of the video when the view goes on to the tiles of all. */
static void ui_sf_draw(VideoState *is, double dt, int64_t now, double ep, int hs, int hi)
{
    int W = is->width, H = is->height, band_h, y0, y1, c0, k0, k1, K, n, dn, tw, th, margin = 14;
    double fa = ui_sf_p * ep, aw, ah, asp, bwid, bhgt, pitch, sy, cy, half, cmin, cmax, m;
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
    cy = bt.y + bt.h / 2.0;
    m = av_clipd(ui_lv - 1.0, 0.0, 1.0);                /* how far the large tile has gone on into the tiles of all */
    m = m * m * (3.0 - 2.0 * m);

    pitch = tw + 12;
    half = (W / 2.0 - margin - tw / 2.0) / pitch;       /* tiles from the middle of the window to the first tile, when the strip starts at the left */
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
    ui_sf_pos += (ui_sf_target - ui_sf_pos) * (1.0 - exp(-dt * 9.0));
    if (fabs(ui_sf_target - ui_sf_pos) < 0.003)
        ui_sf_pos = ui_sf_target;
    else
        ui_tv_moving = 1;
    if (ui_sf_touch)
        ui_tv_moving = 1;

    /* the tiles of the queue that are before and after the video that plays, behind it */
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

    /* the video that plays, in the large tile (on its way from the full window while the view opens, and into its small tile when it goes on) */
    if (ui_live_ok && ui_live_tex) {
        SDL_Rect lr = bt, to;
        int la = (int)(255 * (ui_lv <= 1.0 ? ui_sf_p : 1.0 - m));

        if (ep < 1.0) {
            lr.x = ui_live_rect.x + (int)((bt.x - ui_live_rect.x) * ep);
            lr.y = ui_live_rect.y + (int)((bt.y - ui_live_rect.y) * ep);
            lr.w = ui_live_rect.w + (int)((bt.w - ui_live_rect.w) * ep);
            lr.h = ui_live_rect.h + (int)((bt.h - ui_live_rect.h) * ep);
        }
        if (m > 0.0) {
            if (ui_tv_play_w == W && ui_tv_play_h == H) {
                to = ui_tv_play_rect;
            } else {                                    /* no small tile is known yet: shrink towards the middle */
                to.w = (int)(bt.w * 0.6);
                to.h = (int)(bt.h * 0.6);
                to.x = W / 2 - to.w / 2;
                to.y = bt.y + (bt.h - to.h) / 2;
            }
            lr.x += (int)((to.x - lr.x) * m);
            lr.y += (int)((to.y - lr.y) * m);
            lr.w += (int)((to.w - lr.w) * m);
            lr.h += (int)((to.h - lr.h) * m);
        }
        ui_tv_glow(bt.x + bt.w / 2.0, bt.y + bt.h / 2.0, bt.w * 0.62, bt.h * 0.75, (int)(110 * fa * ep));
        ui_tile_shadow(ui_live_tex, &lr, la, 0.0, 0);
        ui_flow_quad_round(ui_live_tex, &lr, la, 255, 0.0, 0);          /* square corners */
        ui_sf_box = lr;                                 /* the bars sit in the bottom of this */
    } else {
        ui_sf_put(q_items[q_pos], 0, W / 2.0, cy, bt.w, bt.h, 0, 0.0, (int)(255 * ui_sf_p), 255, 1, &r);
        ui_sf_box = r;
    }
    if (ui_tvh_n < 128) {
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

    /* the strip: no titles; the tile in the middle of it (ui_sf_pos) is where the strip has been moved to */
    sy = H - band_h / 2.0 + (1.0 - fa) * band_h;
    K = FFMIN((int)(W / (2.0 * pitch)) + 3, 40);
    c0 = av_clip((int)floor(ui_sf_pos + 0.5), 0, q_count - 1);
    k0 = FFMAX(c0 - K, 0);
    k1 = FFMIN(c0 + K, q_count - 1);
    for (n = k0; n <= k1; n++) {                        /* the far ones first, the middle one on top */
        int i = n <= c0 ? n : k1 - (n - c0 - 1), play = i == q_pos, al, md, ti = i % 4093;
        double x = W / 2.0 + (i - ui_sf_pos) * pitch, goal, lf;

        if (x < -tw || x > W + tw)
            continue;
        goal = (hs == -1 && hi == i) ? 1.0 : 0.0;       /* the tile under the mouse only brightens (and plays its preview): no pop */
        lf = ui_tv_lift[ti];
        lf += (goal - lf) * (1.0 - exp(-dt * 14.0));
        if (fabs(goal - lf) < 0.004)
            lf = goal;
        else
            ui_tv_moving = 1;
        ui_tv_lift[ti] = lf;
        al = (int)((play ? 255 : 225) * ui_sf_p);
        al += (int)((255 * ui_sf_p - al) * lf);
        md = play ? 255 : 200 + (int)(55 * lf);
        if (ui_tv_drag && ui_tv_press == i && ui_tv_pressec == -1)
            al = al / 3;                                /* the one that is being dragged leaves a faint place behind */
        if (ui_sf_put(q_items[i], play, x, sy, tw, th, 0, 0.0, al, md, 0, &r))
            ui_tv_moving = 1;
        if (play) {                                     /* the mark of the video that plays: a white ring */
            SDL_Rect rg = { r.x - 4, r.y - 4, r.w + 8, r.h + 8 };

            SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, (int)(235 * ui_sf_p));
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

''')


def main():
    with open(PATH, "r", encoding="utf-8") as fh:
        text = fh.read()
    if "ui_tile_p" in text:
        print("Already applied: " + PATH)
        sys.exit(0)
    if "ui_sf_box" not in text:
        print("FAILED: this is not v58 yet (apply patch_queue_v58.py first). Nothing was written.")
        sys.exit(1)
    for i, (name, end, old, new) in enumerate(EDITS, 1):
        if end is None:
            if text.count(old) != 1:
                print("FAILED: edit %d (%s) matched %d times, expected once. Nothing was written." % (i, name, text.count(old)))
                sys.exit(1)
            text = text.replace(old, new)
        else:
            a = text.find(old)
            b = text.find(end, a + 1) if a >= 0 else -1
            if a < 0 or text.count(old) != 1 or b < 0:
                print("FAILED: edit %d (%s) start or end marker not found once. Nothing was written." % (i, name))
                sys.exit(1)
            text = text[:a] + new + text[b:]
        print("ok: " + name)
    with open(PATH, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("Done: patch_queue_v59 applied.")


main()
