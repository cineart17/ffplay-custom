#!/usr/bin/env python3
"""patch_queue_v58.py: a tighter, flatter Stripfilm view (seek/volume bar inside the large tile, square tiles, fixed strip).

Applies on top of your current ffplay.c (the one with the Stripfilm view).  Usage:  python3 patch_queue_v58.py [path/to/ffplay.c]
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
# 1. less springing, no overlap: the squeeze is small and tiles shrink exactly as much as the gaps do
# ---------------------------------------------------------------------------------------------------------------------------
patch("constants and state",
'''#define UI_SQ_PITCH 0.40                        /* at full speed the tiles come this much closer together ... */
#define UI_SQ_SIZE 0.12                         /* ... and shrink this much */
static int ui_sf_lift_px = 0;                   /* how far the bars are lifted for the Stripfilm view (0 = at the bottom edge) */
''',
'''#define UI_SQ_PITCH 0.12                        /* v58: at full speed the tiles come this much closer together ... */
#define UI_SQ_SIZE 0.12                         /* ... and shrink as much, so they never touch (it was 0.40 and 0.12: they overlapped) */
static int ui_sf_lift_px = 0;                   /* v58: 1 = the Stripfilm view is up and the bars are drawn inside its large tile */
static SDL_Rect ui_sf_box;                      /* v58: the large tile of the Stripfilm view: the bars sit in its bottom */
static int ui_sf_tw = 100, ui_sf_th = 64;       /* v58: a tile of the strip (a tile that is dragged keeps this size) */
''')

patch("squeeze springs back quicker",
'''(tgt > ui_sq ? 18.0 : 2.4)''',
'''(tgt > ui_sq ? 18.0 : 6.0)''')

patch("small tiles sit closer",
'''double pitch = R->sw * 1.08 * (1.0 - UI_SQ_PITCH * ui_sq);''',
'''double pitch = R->sw * 0.95 * (1.0 - UI_SQ_PITCH * ui_sq);''')

patch("tighter scrolling: row of tiles",
'''ui_tv_pos += (col - ui_tv_pos) * (1.0 - exp(-dt * 9.0));''',
'''ui_tv_pos += (col - ui_tv_pos) * (1.0 - exp(-dt * 13.0));''')
patch("tighter scrolling: rows",
'''ui_tv_row += (rw - ui_tv_row) * (1.0 - exp(-dt * 9.0));''',
'''ui_tv_row += (rw - ui_tv_row) * (1.0 - exp(-dt * 13.0));''')
patch("tighter scrolling: search sections",
'''sec->pos += (sec->target - sec->pos) * (1.0 - exp(-dt * 9.0));''',
'''sec->pos += (sec->target - sec->pos) * (1.0 - exp(-dt * 13.0));''')

# ---------------------------------------------------------------------------------------------------------------------------
# 2. the bars live in the large tile
# ---------------------------------------------------------------------------------------------------------------------------
patch("bar zone",
'''static int ui_bar_y(VideoState *is, int y)
{
    int top = is->height - UI_BAR_H - ui_sf_lift_px;

    return y >= top && (!ui_sf_lift_px || y < top + UI_BAR_H);
}''',
'''static int ui_bar_y(VideoState *is, int y)
{
    int mx = 0, bottom = is->height;

    if (ui_sf_lift_px) {                        /* v58: in the Stripfilm view the bars are in the bottom of the large tile */
        SDL_GetMouseState(&mx, NULL);
        if (mx < ui_sf_box.x || mx >= ui_sf_box.x + ui_sf_box.w)
            return 0;
        bottom = ui_sf_box.y + ui_sf_box.h;
    }
    return y >= bottom - UI_BAR_H && (!ui_sf_lift_px || y < bottom);
}''')

patch("bar layout",
'''    int ty = is->height - bottom_offset - bar_h - ui_sf_lift_px;     /* v57 */

    vo->w = 90;
    vo->h = bar_h;
    vo->y = ty;
    vo->x = is->width - margin_x - 40 - vo->w;
    sk->x = margin_x + 28;                  /* room for the previous button on the left */''',
'''    int x0 = ui_sf_lift_px ? ui_sf_box.x : 0;                           /* v58: the bars sit in the large tile of the Stripfilm view */
    int x1 = ui_sf_lift_px ? ui_sf_box.x + ui_sf_box.w : is->width;
    int ty = (ui_sf_lift_px ? ui_sf_box.y + ui_sf_box.h : is->height) - bottom_offset - bar_h;

    vo->w = 90;
    vo->h = bar_h;
    vo->y = ty;
    vo->x = x1 - margin_x - 40 - vo->w;
    sk->x = x0 + margin_x + 28;             /* room for the previous button on the left */''')

patch("bar width never negative",
'''    sk->w = vo->x - 104 - sk->x;            /* room for next, shuffle and repeat on the right */''',
'''    sk->w = FFMAX(vo->x - 104 - sk->x, 20); /* room for next, shuffle and repeat on the right */''')

patch("bar glass",
'''        strip.x = 0;
        strip.w = is->width;
        strip.h = UI_BAR_GLASS;
        strip.y = is->height - UI_BAR_GLASS;
        if (!ui_sf_lift_px)                     /* v57: lifted bars float over the Stripfilm view */
            ui_glass_bar(&strip);''',
'''        strip.x = ui_sf_lift_px ? ui_sf_box.x : 0;              /* v58: in the Stripfilm view the glass is the bottom of the large tile */
        strip.w = ui_sf_lift_px ? ui_sf_box.w : is->width;
        strip.h = UI_BAR_GLASS;
        strip.y = (ui_sf_lift_px ? ui_sf_box.y + ui_sf_box.h : is->height) - UI_BAR_GLASS;
        ui_glass_bar(&strip);''')

patch("buttons follow the bars (draw)",
'''    int cy = sk->y + sk->h / 2, ex = sk->x + sk->w;

    (void)is;
    SDL_SetRenderDrawColor(renderer, 235, 235, 235, 215);
    {                                           /* one arrowhead each, with a small bar at its end */
        SDL_Rect stop;

        stop.w = 2;
        stop.h = 12;
        stop.y = cy - 6;
        stop.x = 34 - 9;
        SDL_RenderFillRect(renderer, &stop);    /* previous: the bar, then the arrowhead */
        ui_tri(34 - 5, cy, 9, 12, -1);''',
'''    int cy = sk->y + sk->h / 2, ex = sk->x + sk->w, px = (ui_sf_lift_px ? ui_sf_box.x : 0) + 34;     /* v58: px = the previous button */

    (void)is;
    SDL_SetRenderDrawColor(renderer, 235, 235, 235, 215);
    {                                           /* one arrowhead each, with a small bar at its end */
        SDL_Rect stop;

        stop.w = 2;
        stop.h = 12;
        stop.y = cy - 6;
        stop.x = px - 9;
        SDL_RenderFillRect(renderer, &stop);    /* previous: the bar, then the arrowhead */
        ui_tri(px - 5, cy, 9, 12, -1);''')

patch("buttons follow the bars (click)",
'''    ex = sk.x + sk.w;
    if (FFABS(x - 34) <= 12) {''',
'''    ex = sk.x + sk.w;
    if (FFABS(x - ((ui_sf_lift_px ? ui_sf_box.x : 0) + 34)) <= 12) {''')

patch("a tap on the bars is not a tap on the large tile",
'''    if (ui_tv_on(is))
        return ui_tv_click(is, x, y);
    idx = ui_flow_cover_at(is, x, y);''',
'''    if (ui_tv_on(is)) {
        if (ui_sf_lift_px && ui_bar_y(is, y))   /* v58: the bars are over the large tile: the tap is theirs */
            return 0;
        return ui_tv_click(is, x, y);
    }
    idx = ui_flow_cover_at(is, x, y);''')

# ---------------------------------------------------------------------------------------------------------------------------
# 3. square tiles in the Stripfilm view
# ---------------------------------------------------------------------------------------------------------------------------
patch("strip tiles are square",
'''    if (shadow)
        ui_tile_shadow(tex, out, al, 0.0, FFMIN(out->w, out->h) / 11);
    ui_flow_quad_round(tex, out, al, md, 0.0, FFMIN(out->w, out->h) / 11);
    return pv;''',
'''    if (shadow)
        ui_tile_shadow(tex, out, al, 0.0, 0);   /* v58: square corners, whatever the roundness setting is */
    ui_flow_quad_round(tex, out, al, md, 0.0, 0);
    return pv;''')

patch("ring is square",
'''    rr = (int)(av_clip(rr, 0, FFMIN(t->w, t->h) / 2) * ui_round_k() + 0.5);
    for (row = 0; row < t->h; row++) {
        double e = FFMIN(row + 0.5, t->h - row - 0.5);
        int io = e < rr''',
'''    rr = 0;                                     /* v58: square corners */
    for (row = 0; row < t->h; row++) {
        double e = FFMIN(row + 0.5, t->h - row - 0.5);
        int io = e < rr''')

# ---------------------------------------------------------------------------------------------------------------------------
# 4. the Stripfilm layout
# ---------------------------------------------------------------------------------------------------------------------------
region("the Stripfilm layout",
'''/* v57: the Stripfilm view: the video that plays in a large tile (the previous and next tiles peek out behind it), the bars below it,''',
'''static void ui_tv_draw(VideoState *is)
{''',
'''/* v58: the Stripfilm view: the video that plays in a large tile (the previous and next tiles peek out behind it) with the seek and
   volume bars in its bottom and its title under it, and the whole queue as a strip of small tiles on a flat dark frosted band at the
   bottom of the window. The strip has one fixed height, its tiles are square and never change size under the mouse. */
static void ui_sf_draw(VideoState *is, double dt, int64_t now, double ep, int hs, int hi)
{
    int W = is->width, H = is->height, band_h, y0, y1, c0, k0, k1, K, n, dn, tw, th;
    double fa = ui_sf_p * ep, aw, ah, asp, bwid, bhgt, pitch, sc, sy, cy;
    SDL_Rect bt, r, band;
    char name[320];

    th = H < 460 ? 52 : 64;                             /* the strip has one fixed height, whatever the window */
    tw = (int)(th * 1.6);
    ui_sf_tw = tw;
    ui_sf_th = th;
    band_h = th + 20;
    ui_sf_lift_px = fa > 0.02 ? 1 : 0;                  /* the bars are drawn inside the large tile (ui_sf_box) */
    y0 = H < 460 ? 40 : 56;
    y1 = H - band_h - 44;                               /* the large tile ends above its title, which is above the strip */
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

    ui_sf_target = av_clipd(ui_sf_target, 0.0, FFMAX(q_count - 1, 0));
    if (ui_sf_touch && now - ui_sf_touch > 180000) {    /* the hand has left: the strip settles on a whole tile */
        ui_sf_target = floor(ui_sf_target + 0.5);
        ui_sf_touch = 0;
    }
    ui_sf_pos += (ui_sf_target - ui_sf_pos) * (1.0 - exp(-dt * 13.0));       /* tighter than before */
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

    /* the video that plays, in the large tile (on its way from the full window while the view opens) */
    if (ui_live_ok && ui_live_tex) {
        SDL_Rect lr = bt;

        if (ep < 1.0) {
            lr.x = ui_live_rect.x + (int)((bt.x - ui_live_rect.x) * ep);
            lr.y = ui_live_rect.y + (int)((bt.y - ui_live_rect.y) * ep);
            lr.w = ui_live_rect.w + (int)((bt.w - ui_live_rect.w) * ep);
            lr.h = ui_live_rect.h + (int)((bt.h - ui_live_rect.h) * ep);
        }
        ui_tv_glow(bt.x + bt.w / 2.0, bt.y + bt.h / 2.0, bt.w * 0.62, bt.h * 0.75, (int)(110 * fa * ep));
        ui_tile_shadow(ui_live_tex, &lr, (int)(255 * ui_sf_p), 0.0, 0);
        ui_flow_quad_round(ui_live_tex, &lr, (int)(255 * ui_sf_p), 255, 0.0, 0);        /* square corners */
        r = bt;
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

    /* the title of the video that plays, under its large tile */
    ui_tv_name(q_items[q_pos], name, sizeof(name));
    ui_fit_text(name, 18, bt.w);
    ui_label_c(W / 2, bt.y + bt.h + 24, name, 18, 255, 255, 255, (int)(255 * fa));

    /* the band behind the strip: flat dark frosted glass, edge to edge, like the one behind the seek and volume bars */
    band.x = 0;
    band.w = W;
    band.h = band_h;
    band.y = H - band_h + (int)((1.0 - fa) * band_h);
    ui_glass_bar(&band);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);

    /* the strip: no titles; the tiles come a little closer together and shrink by the same amount the faster it moves */
    pitch = (tw + 12) * (1.0 - UI_SQ_PITCH * ui_sq);
    sc = 1.0 - UI_SQ_PITCH * ui_sq;
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
        if (ui_sf_put(q_items[i], play, x, sy, tw * sc, th * sc, 0, 0.0, al, md, 0, &r))
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

# ---------------------------------------------------------------------------------------------------------------------------
# 5. dragging a tile of the strip keeps its size
# ---------------------------------------------------------------------------------------------------------------------------
patch("dragged tile keeps its size",
'''        g.h = (int)FFMIN(H * 0.2, 140);
        g.w = asp > 0.0 ? (int)(g.h * asp) : g.h;
        g.x = ui_hov_x - g.w / 2;
        g.y = ui_hov_y - g.h / 2;
        ui_tv_tile(p, &g, 215, 255);''',
'''        if (vm && ui_sf_mode && ui_sf_p > 0.5) {  /* v58: in the Stripfilm view the dragged tile stays the size of a tile of the strip */
            ui_sf_put(p, 0, ui_hov_x, ui_hov_y, ui_sf_tw, ui_sf_th, 0, 0.0, 215, 255, 0, &g);
        } else {
            g.h = (int)FFMIN(H * 0.2, 140);
            g.w = asp > 0.0 ? (int)(g.h * asp) : g.h;
            g.x = ui_hov_x - g.w / 2;
            g.y = ui_hov_y - g.h / 2;
            ui_tv_tile(p, &g, 215, 255);
        }''')

# ---------------------------------------------------------------------------------------------------------------------------
# 6. tapping a tile of the strip plays it and the view stays
# ---------------------------------------------------------------------------------------------------------------------------
patch("tap on the playing tile in the strip",
'''    if (idx >= 0 && idx == q_pos) {             /* the one that plays: back to it */
        if (ui_flow_video(is))''',
'''    if (idx >= 0 && idx == q_pos && ui_sf_active(is)) {         /* v58: in the Stripfilm view the view stays; a paused video plays on */
        if (is->paused)
            toggle_pause(is);
        return;
    }
    if (idx >= 0 && idx == q_pos) {             /* the one that plays: back to it */
        if (ui_flow_video(is))''')

patch("tap on another tile in the strip",
'''        queue_add(path);
        idx = q_count - 1;
    }
    ui_tv_exit(is);
    q_forced = idx;''',
'''        queue_add(path);
        idx = q_count - 1;
    }
    if (!ui_sf_active(is))                      /* v58: the Stripfilm view stays open while the next video starts */
        ui_tv_exit(is);
    q_forced = idx;''')


def main():
    with open(PATH, "r", encoding="utf-8") as fh:
        text = fh.read()
    if "ui_sf_box" in text:
        print("Already applied: " + PATH)
        sys.exit(0)
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
    print("Done: patch_queue_v58 applied.")


main()
