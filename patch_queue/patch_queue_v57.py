#!/usr/bin/env python3
# patch_queue_v57.py - the Stripfilm view (video items) and spring loaded scrolling, on top of v56
# Run it from ~/build/ffmpeg-6.1.1 (it patches fftools/ffplay.c).
import sys

PATH = "fftools/ffplay.c"
src = open(PATH, encoding="utf-8").read()

if "v57: the Stripfilm view" in src:
    print("Already applied")
    sys.exit(0)

failed = 0


def patch(name, old, new):
    global src, failed
    n = src.count(old)
    if n != 1:
        print("FAILED: %s (found %d times)" % (name, n))
        failed += 1
        return
    src = src.replace(old, new, 1)
    print("ok: " + name)


# ---------------------------------------------------------------- globals, bar lift, hit tests
patch("globals", r'''static double ui_tile_lift[32];             /* 0 to 1: how far each tile has risen under the mouse (by queue number) */
''', r'''static double ui_tile_lift[32];             /* 0 to 1: how far each tile has risen under the mouse (by queue number) */

/* v57: the Stripfilm view and spring loaded scrolling. For a video, a two finger swipe up opens the Stripfilm view (the video plays
   on in a large tile, the queue is a strip of small tiles below it, the seek and volume bars sit between them). A swipe up once more,
   or a hard swipe from the start, opens the tiles of all. A swipe down goes back a step. Scrolling tiles squeeze together with the
   speed and slowly spring back. */
#define UI_SF_HARD 5.0                          /* a swipe up this long goes straight to the tiles of all (a normal one stops at the strip) */
#define UI_SF_SWIPE 1.5                         /* tiles of the strip for each notch of a sideways swipe */
#define UI_SQ_PITCH 0.40                        /* at full speed the tiles come this much closer together ... */
#define UI_SQ_SIZE 0.12                         /* ... and shrink this much */
static int ui_sf_lift_px = 0;                   /* how far the bars are lifted for the Stripfilm view (0 = at the bottom edge) */
static int ui_sf_mode = 0;                      /* 1 = the Stripfilm layout (video items), 0 = the tiles of all */
static double ui_sf_p = 0.0;                    /* 0 to 1: how far the view has moved into the Stripfilm layout */
static double ui_sf_pos = 0.0, ui_sf_target = 0.0;      /* the strip: the queue number in the middle (the video that plays does not change) */
static int64_t ui_sf_touch = 0;                 /* when the strip was last moved by hand */
static double ui_sq = 0.0;                      /* 0 to 1: how much the scrolling tiles are squeezed together right now */
''')

patch("bar hit test helper", r'''#define UI_ON(is) ((is)->width >= 260 && (is)->height >= UI_MIN_H)
''', r'''#define UI_ON(is) ((is)->width >= 260 && (is)->height >= UI_MIN_H)

/* v57: is y on the strip the mouse reacts to? In the Stripfilm view the bars are lifted and the strip of tiles is below them. */
static int ui_bar_y(VideoState *is, int y)
{
    int top = is->height - UI_BAR_H - ui_sf_lift_px;

    return y >= top && (!ui_sf_lift_px || y < top + UI_BAR_H);
}
''')

patch("layout lifts the bars", r'''    int ty = is->height - bottom_offset - bar_h;
''', r'''    int ty = is->height - bottom_offset - bar_h - ui_sf_lift_px;     /* v57 */
''')

patch("no glass strip when lifted", r'''        strip.y = is->height - UI_BAR_GLASS;
        ui_glass_bar(&strip);
''', r'''        strip.y = is->height - UI_BAR_GLASS;
        if (!ui_sf_lift_px)                     /* v57: lifted bars float over the Stripfilm view */
            ui_glass_bar(&strip);
''')

patch("mouse: snap back test", r'''ev->button.button == SDL_BUTTON_LEFT && ev->button.y < is->height - UI_BAR_H && ui_flow_snap_back(is))''',
      r'''ev->button.button == SDL_BUTTON_LEFT && !ui_bar_y(is, ev->button.y) && ui_flow_snap_back(is))''')

patch("mouse: bar click test", r'''        if (ev->button.button != SDL_BUTTON_LEFT || ev->button.y < is->height - UI_BAR_H)
            return 0;''', r'''        if (ev->button.button != SDL_BUTTON_LEFT || !ui_bar_y(is, ev->button.y))
            return 0;''')

patch("mouse: hover test", r'''        ui_hover = ev->motion.y >= is->height - UI_BAR_H;''',
      r'''        ui_hover = ui_bar_y(is, ev->motion.y);''')

patch("wheel zone", r'''    if (my < is->height - UI_BAR_H)
        return 0;
    ui_layout(is, &sk, &vo);''', r'''    if (!ui_bar_y(is, my))
        return 0;
    ui_layout(is, &sk, &vo);''')

patch("vflow_set clears the Stripfilm", r'''    ui_vflow = on;
    ui_vflow_t = 0;
    ui_bd_key[0] = 0;                   /* the backdrop takes its colors from the picture of this moment */''', r'''    ui_vflow = on;
    ui_sf_mode = 0;                     /* v57: a view opened another way is the tiles of all */
    ui_sf_lift_px = 0;
    ui_vflow_t = 0;
    ui_bd_key[0] = 0;                   /* the backdrop takes its colors from the picture of this moment */''')

patch("flow draw: bars back down", r'''        ui_flow_n = 0;
        ui_flow_moving = 0;
        ui_tp_stop();
        return;
    }
    if (ui_tv_on(is)) {                         /* v37: the tiled view draws instead */
        ui_tv_draw(is);
        return;
    }''', r'''        ui_flow_n = 0;
        ui_flow_moving = 0;
        ui_tp_stop();
        ui_sf_lift_px = 0;
        return;
    }
    if (ui_tv_on(is)) {                         /* v37: the tiled view draws instead */
        ui_tv_draw(is);
        return;
    }
    ui_sf_lift_px = 0;''')

# ---------------------------------------------------------------- helpers that need the tiled view's state
patch("helpers before the view-is-there block", r'''/* ---- when is the view there, and does it own the keys? ---- */
''', r'''/* ======================= v57: the Stripfilm view ======================= */
static int ui_sf_video(VideoState *is)         /* a video (not a cover) is what plays */
{
    return is && is->video_st && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC) && q_count > 0 && q_pos >= 0 && q_pos < q_count;
}

static int ui_sf_active(VideoState *is)        /* the Stripfilm layout is what the view shows now */
{
    return ui_sf_mode && ui_tv_on(is) && ui_flow_video(is) && !ui_tv_q[0];
}

/* The strip moves by hand (a swipe, the arrow keys): the video that plays stays where it is */
static void ui_sf_scroll(VideoState *is, double d)
{
    ui_sf_target = av_clipd(ui_sf_target + d, 0.0, FFMAX(q_count - 1, 0));
    ui_sf_touch = av_gettime_relative();
    ui_tv_moving = 1;
    is->force_refresh = 1;
}

/* ---- when is the view there, and does it own the keys? ---- */
''')

patch("reset starts the strip at the playing video", r'''    ui_tv_focus = av_clip(q_pos, 0, q_count - 1);
    ui_tv_dims(is, &R, &L);
    ui_tv_pos = ui_tv_focus % L;''', r'''    ui_tv_focus = av_clip(q_pos, 0, q_count - 1);
    ui_sf_pos = ui_sf_target = ui_tv_focus;     /* v57 */
    ui_sf_touch = 0;
    ui_sq = 0.0;
    ui_tv_dims(is, &R, &L);
    ui_tv_pos = ui_tv_focus % L;''')

patch("enter: the layout moves in from nothing", r'''        ui_vflow_auto = 0;
    } else if (is->audio_st) {
        ui_tv_audio = 1;''', r'''        ui_vflow_auto = 0;
        ui_sf_p = 0.0;                          /* v57: the layout moves in */
    } else if (is->audio_st) {
        ui_tv_audio = 1;''')

patch("exit, plus level and swipe functions", r'''    ui_tv_audio = 0;
    is->force_refresh = 1;
}

/* Play a file from the view''', r'''    ui_tv_audio = 0;
    ui_sf_mode = 0;                             /* v57 */
    is->force_refresh = 1;
}

/* v57: 0 = no view, 1 = the Stripfilm view, 2 = the tiles of all (over a video) */
static int ui_sf_cur(VideoState *is)
{
    return ui_tv_cap(is) ? (ui_sf_mode ? 1 : 2) : 0;
}

static void ui_sf_level(VideoState *is, int lvl)
{
    int cur = ui_sf_cur(is);

    if (lvl == cur)
        return;
    if (lvl <= 0) {
        ui_sf_mode = 0;
        ui_tv_exit(is);
    } else if (cur == 0) {                      /* opening: the Stripfilm view, or (a hard swipe) the tiles of all */
        ui_sf_mode = lvl == 1;
        ui_tv_enter(is);
        if (!ui_tv_cap(is))
            ui_sf_mode = 0;                     /* it did not open (a small window) */
    } else if (lvl == 1) {                      /* from the tiles of all back to the strip, centred on the tile that was in focus */
        ui_sf_target = av_clip(ui_tv_focus, 0, q_count - 1);
        ui_sf_touch = 0;
        ui_sf_mode = 1;
    } else {                                    /* from the strip to the tiles of all, from the tile that is in the middle of the strip */
        ui_tv_focus = av_clip((int)floor(ui_sf_target + 0.5), 0, q_count - 1);
        ui_sf_mode = 0;
    }
    ui_tv_moving = 1;
    is->force_refresh = 1;
}

/* A two finger swipe up or down over a video. One swipe moves one step (closed > strip > all tiles), a hard swipe up from the
   start goes straight to the tiles of all, a hard swipe down from the tiles closes the view. */
static void ui_sf_swipe(VideoState *is, double ay)
{
    static double acc = 0.0;
    static int64_t last = 0;
    static int base = 0;
    int64_t now = av_gettime_relative();
    int cur = ui_sf_cur(is), lvl;

    if (now - last > 250000) {
        acc = 0.0;
        base = cur;
    }
    last = now;
    acc += ay * UI_TV_UP_SIGN;                  /* up is positive */
    lvl = base;
    if (acc >= UI_SF_HARD)
        lvl = base + 2;
    else if (acc >= 1.0)
        lvl = base + 1;
    else if (acc <= -UI_SF_HARD)
        lvl = base - 2;
    else if (acc <= -1.0)
        lvl = base - 1;
    lvl = av_clip(lvl, 0, 2);
    if (lvl != cur)
        ui_sf_level(is, lvl);
}

/* Play a file from the view''')

# ---------------------------------------------------------------- keys, swipes, taps
patch("step: the strip moves", r'''static void ui_tv_step(VideoState *is, int dcol, int drow)
{
    ui_tv_moving = 1;
''', r'''static void ui_tv_step(VideoState *is, int dcol, int drow)
{
    ui_tv_moving = 1;
    if (ui_sf_active(is)) {                     /* v57: in the Stripfilm view the arrow keys move the strip */
        if (dcol)
            ui_sf_scroll(is, dcol);
        return;
    }
''')

patch("key: Enter in the strip", r'''        p = ui_tv_q[0] ? ui_tv_sel_path() : q_items[av_clip(ui_tv_focus, 0, q_count - 1)];''',
      r'''        p = ui_tv_q[0] ? ui_tv_sel_path() :
            ui_sf_active(is) ? q_items[av_clip((int)floor(ui_sf_target + 0.5), 0, q_count - 1)] :
            q_items[av_clip(ui_tv_focus, 0, q_count - 1)];''')

patch("key: Up in the strip", r'''    case SDLK_UP:
        ui_tv_step(is, 0, -1);
        return 1;''', r'''    case SDLK_UP:
        if (ui_sf_active(is)) {                 /* v57: up from the strip opens the tiles of all */
            ui_sf_level(is, 2);
            return 1;
        }
        ui_tv_step(is, 0, -1);
        return 1;''')

patch("text: typing leaves the strip", r'''    if (!ui_tv_cap(is) || ui_menu_open || ui_prefs_open || ui_q_open || ui_info_open || ui_ctx_open)
        return 0;
    if (!n && t[0] == ' ')''', r'''    if (!ui_tv_cap(is) || ui_menu_open || ui_prefs_open || ui_q_open || ui_info_open || ui_ctx_open)
        return 0;
    if (ui_sf_mode)
        ui_sf_level(is, 2);                     /* v57: the search lives in the tiles of all */
    if (!n && t[0] == ' ')''')

patch("swipe x: the strip", r'''    int steps;

    if (now - last > 300000 || ax * acc < 0.0)
        acc = 0.0;
    last = now;
    acc += ax;''', r'''    int steps;

    if (ui_sf_active(is)) {                     /* v57: the strip moves, the video that plays stays */
        ui_sf_scroll(is, ax * UI_SF_SWIPE);
        return;
    }
    if (now - last > 300000 || ax * acc < 0.0)
        acc = 0.0;
    last = now;
    acc += ax;''')

patch("release: a tap in the strip plays", r'''        if (item == ui_tv_focus)
            ui_tv_play(is, q_items[av_clip(item, 0, q_count - 1)]);     /* a tap on the tile in focus plays it */''',
      r'''        if (ui_sf_active(is) || item == ui_tv_focus)    /* v57: in the strip a tap plays the tile */
            ui_tv_play(is, q_items[av_clip(item, 0, q_count - 1)]);     /* a tap on the tile in focus plays it */''')

patch("wheel: two finger swipes over a video", r'''    if (act == 2 || (!zone && ui_tv_on(is))) {                  /* with the view open, a swipe down closes it */
        if (ui_tv_on(is))''', r'''    if (act == 2 || (!zone && ui_tv_on(is))) {                  /* with the view open, a swipe down closes it */
        if (ui_sf_video(is)) {                  /* v57: over a video the swipes go closed > Stripfilm > all tiles */
            ui_sf_swipe(is, ay);
            is->force_refresh = 1;
            return;
        }
        if (ui_tv_on(is))''')

# ---------------------------------------------------------------- spring loaded scrolling in the tiles of all
patch("tiles: closer with speed (pitch)", r'''    double pitch = R->sw * 1.08;
''', r'''    double pitch = R->sw * 1.08 * (1.0 - UI_SQ_PITCH * ui_sq);     /* v57: the tiles squeeze together while they scroll */
''')

patch("tiles: smaller with speed", r'''        bw = R->sw * sc;
        bh = R->sh * sc;''', r'''        bw = R->sw * sc * (1.0 - UI_SQ_SIZE * ui_sq);
        bh = R->sh * sc * (1.0 - UI_SQ_SIZE * ui_sq);''')

patch("tiles: fade out into the strip", r'''        al = (int)(al * en);
        ti = (int)(((R->sec + 1) * 1031 + item) % 4093);''', r'''        al = (int)(al * en);
        if (vm)
            al = (int)(al * (1.0 - ui_sf_p));   /* v57: the tiles fade while the Stripfilm layout comes in */
        ti = (int)(((R->sec + 1) * 1031 + item) % 4093);''')

# ---------------------------------------------------------------- the Stripfilm drawing
patch("the Stripfilm drawing", r'''static void ui_tv_draw(VideoState *is)
{
    int64_t now = av_gettime_relative();''', r'''/* v57: one tile of the Stripfilm view, in its own shape, fitted into the box bw x bh. side = -1 or 1: a tile that peeks out from
   behind the large one, its outer edge is "edge" pixels from the middle. live = the video that plays (its picture is the live one).
   Returns 1 if it is a preview that plays. */
static int ui_sf_put(const char *path, int live, double cx, double cy, double bw, double bh, int side, double edge,
                     int al, int md, int shadow, SDL_Rect *out)
{
    SDL_Texture *tex = NULL;
    int pw = 0, ph = 0, cw = 0, ch = 0, nw, nh, pv = 0;
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
        if (!tex)
            tex = ui_cov_get(path, &cw, &ch);
        if (!tex)
            tex = ui_flow_icon();
    }
    if (!tex)
        return pv;
    if (shadow)
        ui_tile_shadow(tex, out, al, 0.0, FFMIN(out->w, out->h) / 11);
    ui_flow_quad_round(tex, out, al, md, 0.0, FFMIN(out->w, out->h) / 11);
    return pv;
}

/* A rounded ring (thickness th) around a tile: the mark of the video that plays in the strip */
static void ui_sf_ring(const SDL_Rect *t, int rr, int th)
{
    int row;

    rr = (int)(av_clip(rr, 0, FFMIN(t->w, t->h) / 2) * ui_round_k() + 0.5);
    for (row = 0; row < t->h; row++) {
        double e = FFMIN(row + 0.5, t->h - row - 0.5);
        int io = e < rr ? (int)(rr - sqrt((double)rr * rr - (rr - e) * (rr - e)) + 0.5) : 0, ii = th;
        SDL_Rect a;

        if (row < th || row >= t->h - th) {
            a.x = t->x + io;
            a.y = t->y + row;
            a.w = t->w - 2 * io;
            a.h = 1;
            if (a.w > 0)
                SDL_RenderFillRect(renderer, &a);
            continue;
        }
        if (rr - th > 0 && e - th < rr - th)
            ii = th + (int)((rr - th) - sqrt((double)(rr - th) * (rr - th) - ((rr - th) - (e - th)) * ((rr - th) - (e - th))) + 0.5);
        if (ii <= io)
            ii = io + 1;
        a.y = t->y + row;
        a.h = 1;
        a.x = t->x + io;
        a.w = ii - io;
        if (a.w > 0)
            SDL_RenderFillRect(renderer, &a);
        a.x = t->x + t->w - ii;
        SDL_RenderFillRect(renderer, &a);
    }
}

/* v57: the Stripfilm view: the video that plays in a large tile (the previous and next tiles peek out behind it), the bars below it,
   and the whole queue as a strip of small tiles under the bars. The strip moves by itself: the video that plays does not change. */
static void ui_sf_draw(VideoState *is, double dt, int64_t now, double ep, int hs, int hi)
{
    int W = is->width, H = is->height, sh_s, tw_s, lift, y0, y1, c0, k0, k1, K, n, dn;
    double fa = ui_sf_p * ep, aw, ah, asp, bwid, bhgt, pitch, sc, sy, cy;
    SDL_Rect bt, r;

    sh_s = (int)av_clipd(H * 0.105, 34.0, 92.0);        /* the height of a tile of the strip */
    tw_s = (int)(sh_s * 1.6);
    lift = sh_s + 22;                                   /* the bars sit this much above the bottom edge */
    ui_sf_lift_px = (int)(lift * ui_sf_p * ep);
    y0 = H < 460 ? 40 : 56;
    y1 = (H - 18 - lift) - 28;                          /* the large tile ends above the bars */
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
        ui_tile_shadow(ui_live_tex, &lr, (int)(255 * ui_sf_p), 0.0, (int)(FFMIN(lr.w, lr.h) / 11.0 * ep));
        ui_flow_quad_round(ui_live_tex, &lr, (int)(255 * ui_sf_p), 255, 0.0, (int)(FFMIN(lr.w, lr.h) / 11.0 * ep));
        r = bt;
    } else {
        ui_sf_put(q_items[q_pos], 0, W / 2.0, cy, bt.w, bt.h, 0, 0.0, (int)(255 * ui_sf_p), 255, 1, &r);
    }
    if (ui_tvh_n < 128) {
        ui_tvh[ui_tvh_n].r = bt;
        ui_tvh[ui_tvh_n].sec = -1;
        ui_tvh[ui_tvh_n].item = q_pos;
        ui_tvh_n++;
    }

    /* the strip: no titles, the tiles come closer together and a little smaller the faster it moves */
    pitch = (tw_s + 12) * (1.0 - UI_SQ_PITCH * ui_sq);
    sc = 1.0 - UI_SQ_SIZE * ui_sq;
    sy = H - 16 - sh_s / 2.0 + (1.0 - ui_sf_p) * 56.0;
    K = FFMIN((int)(W / (2.0 * pitch)) + 3, 40);
    c0 = av_clip((int)floor(ui_sf_pos + 0.5), 0, q_count - 1);
    k0 = FFMAX(c0 - K, 0);
    k1 = FFMIN(c0 + K, q_count - 1);
    for (n = k0; n <= k1; n++) {                        /* the far ones first, the middle one on top */
        int i = n <= c0 ? n : k1 - (n - c0 - 1), play = i == q_pos, al, md, ti = i % 4093;
        double x = W / 2.0 + (i - ui_sf_pos) * pitch, goal, lf, g;

        if (x < -tw_s || x > W + tw_s)
            continue;
        goal = (hs == -1 && hi == i) ? 1.0 : 0.0;
        lf = ui_tv_lift[ti];
        lf += (goal - lf) * (1.0 - exp(-dt * 14.0));
        if (fabs(goal - lf) < 0.004)
            lf = goal;
        else
            ui_tv_moving = 1;
        ui_tv_lift[ti] = lf;
        g = sc * (play ? 1.1 : 1.0) * (1.0 + 0.05 * lf);
        al = (int)((play ? 255 : 225) * ui_sf_p);
        al += (int)((255 * ui_sf_p - al) * lf);
        md = play ? 255 : 200 + (int)(55 * lf);
        if (ui_tv_drag && ui_tv_press == i && ui_tv_pressec == -1)
            al = al / 3;                                /* the one that is being dragged leaves a faint place behind */
        if (ui_sf_put(q_items[i], play, x, sy - 6 * lf, tw_s * g, sh_s * g, 0, 0.0, al, md, 0, &r))
            ui_tv_moving = 1;
        if (play) {                                     /* the mark of the video that plays: a white ring */
            SDL_Rect rg = { r.x - 5, r.y - 5, r.w + 10, r.h + 10 };

            SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, (int)(235 * ui_sf_p));
            ui_sf_ring(&rg, FFMIN(r.w, r.h) / 11 + 5, 3);
        }
        if (ui_tvh_n < 128) {
            ui_tvh[ui_tvh_n].r = r;
            ui_tvh[ui_tvh_n].sec = -1;
            ui_tvh[ui_tvh_n].item = i;
            ui_tvh_n++;
        }
    }
}

static void ui_tv_draw(VideoState *is)
{
    int64_t now = av_gettime_relative();''')

# ---------------------------------------------------------------- ui_tv_draw: the move between layouts, the squeeze, the calls
patch("draw: layout move and squeeze", r'''    if (q_pos != last_q) {                      /* a new item started: the focus goes to it */
        last_q = q_pos;
        if (!ui_tv_q[0])
            ui_tv_focus = q_pos;
    }''', r'''    {                                           /* v57: the move between the Stripfilm layout and the tiles of all, and the squeeze of scrolling tiles */
        double want = (vm && ui_sf_mode) ? 1.0 : 0.0, cur, v = 0.0, tgt;
        static double prev = 0.0;
        static int prev_kind = -1;
        int kind = (vm && ui_sf_mode) ? 0 : ui_tv_q[0] ? 1 : 2;

        ui_sf_p += (want - ui_sf_p) * (1.0 - exp(-dt * 10.0));
        if (fabs(want - ui_sf_p) < 0.01)
            ui_sf_p = want;
        else
            ui_tv_moving = 1;
        if (!vm || ui_sf_p <= 0.004)
            ui_sf_lift_px = 0;
        cur = kind == 0 ? ui_sf_pos : kind == 1 ? ui_tv_sec[ui_tv_act].pos : ui_tv_pos;
        if (dt > 0.0 && kind == prev_kind && now - ui_tv_born > 150000)
            v = fabs(cur - prev) / dt;              /* tiles a second */
        prev = cur;
        prev_kind = kind;
        tgt = av_clipd((v - 2.0) / 16.0, 0.0, 1.0);
        ui_sq += (tgt - ui_sq) * (1.0 - exp(-dt * (tgt > ui_sq ? 18.0 : 2.4)));    /* quick to squeeze, slow to spring back */
        if (ui_sq < 0.004 && tgt <= 0.0)
            ui_sq = 0.0;
        else
            ui_tv_moving = 1;
    }
    if (q_pos != last_q) {                      /* a new item started: the focus goes to it */
        last_q = q_pos;
        if (!ui_tv_q[0])
            ui_tv_focus = q_pos;
        ui_sf_target = q_pos;                   /* v57: the strip follows */
        ui_sf_touch = 0;
    }''')

patch("draw: the search box fades", r'''        ui_glass(&box, box.h / 2);''', r'''        if (!vm || ui_sf_p < 0.5)               /* v57: no search box in the Stripfilm layout */
            ui_glass(&box, box.h / 2);''')

patch("draw: the box text fades", r'''tx = box.x + 18, cy = box.y + box.h / 2, al = (int)(255 * ep);''',
      r'''tx = box.x + 18, cy = box.y + box.h / 2, al = (int)(255 * ep * (vm ? 1.0 - ui_sf_p : 1.0));''')

patch("draw: the strip and the browsing rows", r'''    if (!ui_tv_q[0]) {                          /* browsing: the queue in rows, the lower row continues the upper one */''',
      r'''    if (!ui_tv_q[0] && vm && ui_sf_p > 0.004)
        ui_sf_draw(is, dt, now, ep, hs, hi);    /* v57 */
    if (!ui_tv_q[0] && !(vm && ui_sf_p > 0.996)) {      /* browsing: the queue in rows, the lower row continues the upper one */''')

patch("draw: hint fades", r'''"Type to search     Enter plays     Esc closes", 13, 255, 255, 255, (int)(95 * ep));''',
      r'''"Type to search     Enter plays     Esc closes", 13, 255, 255, 255, (int)(95 * ep * (vm ? 1.0 - ui_sf_p : 1.0)));''')

patch("draw: searching branch", r'''    } else {                                    /* searching: three sections, each its own row of matches, the best one in focus */''',
      r'''    } else if (ui_tv_q[0]) {                    /* searching: three sections, each its own row of matches, the best one in focus */''')

if failed:
    print("FAILED: %d edit(s) did not apply, nothing was written" % failed)
    sys.exit(1)

open(PATH, "w", encoding="utf-8").write(src)
print("Done: v57 (the Stripfilm view and spring loaded scrolling)")
