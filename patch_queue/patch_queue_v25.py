#!/usr/bin/env python3
# Update 25 for ffplay-custom (on top of patch_queue_v24.py).
#   * Preferences: the mouse on a setting shows all its choices in that row (like the sleep timer row); click one to pick it.
#     The row changes to the choices with a smooth glide, and back again when the mouse leaves.
#   * The sleep timer row glides between its value and its choices too (it was an instant swap).
#   * Seeking in small steps (Left/Right, the wheel): the bar and the time follow every key press at once, and the player
#     seeks as soon as the last seek has shown its picture, so pictures keep coming while the key is held.
#   * The crossfade is visible in the queue view too: the next video fades in inside the playing video's tile.
#   * The slanted top and bottom edges of the tiles are smooth (a one pixel fringe), not stepped.
#   * Bigger video tiles in the queue view (the neighbours are partly out of the window, which is fine).
#   * A tap on the playing video's tile: the video grows back at once, and the window goes full screen after that
#     (the two together made it stutter).
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v24.py. Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_ks_tick(" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_present(" not in src or "ui_xf_video_draw" not in src:
    print("Apply patch_queue_v24.py first. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


# ============================================================ the crossfade is also drawn in the tile of the queue view
patch(r'''static void ui_xf_video_draw(VideoState *is);''',
      r'''static void ui_xf_video_draw(VideoState *is, int to_tile);''',
      "crossfade declaration")

patch(r'''ui_xf_video_draw(is);                   /* the next video fades in over the end of this one */''',
      r'''ui_xf_video_draw(is, 0);                /* the next video fades in over the end of this one */''',
      "crossfade call")

patch(r'''static void ui_xf_video_draw(VideoState *is)
{''', r'''static void ui_xf_video_draw(VideoState *is, int to_tile)
{''', "crossfade definition")

patch(r'''        xf->pictq.size <= 0 || ui_flow_video(is) || ui_has_cover(is))
        return;''', r'''        xf->pictq.size <= 0 || (!to_tile && (ui_flow_video(is) || ui_has_cover(is))))
        return;''', "crossfade also in the tile")

patch(r'''    calculate_display_rect(&r, is->xleft, is->ytop, is->width, is->height, np->width, np->height, np->sar);
    set_sdl_yuv_conversion_mode(np->frame);
    if (!np->uploaded) {
        if (upload_texture(&xf->vid_texture, np->frame) < 0) {''',
      r'''    if (to_tile)                                /* drawn into the picture of the tile: its whole area */
        calculate_display_rect(&r, 0, 0, ui_live_w, ui_live_h, np->width, np->height, np->sar);
    else
        calculate_display_rect(&r, is->xleft, is->ytop, is->width, is->height, np->width, np->height, np->sar);
    set_sdl_yuv_conversion_mode(np->frame);
    if (!np->uploaded) {
        if (upload_texture(&xf->vid_texture, np->frame) < 0) {''', "crossfade rectangle")

patch(r'''    SDL_RenderCopyEx(renderer, is->vid_texture, NULL, NULL, 0, NULL, flip ? SDL_FLIP_VERTICAL : 0);
    SDL_SetRenderTarget(renderer, prev);
    ui_live_ok = 1;''', r'''    SDL_RenderCopyEx(renderer, is->vid_texture, NULL, NULL, 0, NULL, flip ? SDL_FLIP_VERTICAL : 0);
    ui_xf_video_draw(is, 1);                    /* the next video fading in, inside the tile */
    SDL_SetRenderTarget(renderer, prev);
    ui_live_ok = 1;''', "crossfade in the live tile")

# ============================================================ bigger video tiles
patch(r'''B = ui_flow_vmode ? FFMIN(W * 0.42, H * 0.50 * ar) : FFMIN(W * 0.30, H * 0.44);''',
      r'''B = ui_flow_vmode ? FFMIN(W * 0.52, H * 0.58 * ar) : FFMIN(W * 0.30, H * 0.44);''',
      "bigger video tiles")

# ============================================================ smooth edges for the slanted tiles
patch(r'''static void ui_flow_quad(SDL_Texture *tex, const SDL_Rect *t, int al, int md, double tilt)
{''', r'''/* SDL draws a slanted edge with no smoothing, so it shows steps. A thin fringe along the top and the bottom edge fades out
   over about a pixel and smooths them. v = the vertices of the tile: n + 1 columns, the top one at 2k, the bottom one at 2k + 1. */
static void ui_quad_fringe(SDL_Texture *tex, const SDL_Vertex *v, int n)
{
    enum { MAXN = 32 };
    SDL_Vertex f[(MAXN + 1) * 4];
    int idx[MAXN * 12], k, a, b;

    if (n > MAXN || v[0].color.a <= 40)         /* the faint shadows do not need it */
        return;
    for (k = 0; k <= n; k++) {
        f[k * 4] = v[k * 2];                    /* the top edge, half a pixel inside... */
        f[k * 4].position.y += 0.5f;
        f[k * 4 + 1] = v[k * 2];                /* ...fading to nothing a pixel outside */
        f[k * 4 + 1].position.y -= 1.0f;
        f[k * 4 + 1].color.a = 0;
        f[k * 4 + 2] = v[k * 2 + 1];
        f[k * 4 + 2].position.y -= 0.5f;
        f[k * 4 + 3] = v[k * 2 + 1];
        f[k * 4 + 3].position.y += 1.0f;
        f[k * 4 + 3].color.a = 0;
    }
    for (k = 0; k < n; k++) {
        a = k * 4;
        b = (k + 1) * 4;
        idx[k * 12] = a;          idx[k * 12 + 1] = a + 1;  idx[k * 12 + 2] = b;
        idx[k * 12 + 3] = a + 1;  idx[k * 12 + 4] = b + 1;  idx[k * 12 + 5] = b;
        idx[k * 12 + 6] = a + 2;  idx[k * 12 + 7] = a + 3;  idx[k * 12 + 8] = b + 2;
        idx[k * 12 + 9] = a + 3;  idx[k * 12 + 10] = b + 3; idx[k * 12 + 11] = b + 2;
    }
    SDL_RenderGeometry(renderer, tex, f, (n + 1) * 4, idx, n * 12);
}

static void ui_flow_quad(SDL_Texture *tex, const SDL_Rect *t, int al, int md, double tilt)
{''', "edge smoothing helper")

patch(r'''    SDL_RenderGeometry(renderer, tex, v, (NS + 1) * 2, idx, NS * 6);
}

static void ui_flow_tile(''', r'''    SDL_RenderGeometry(renderer, tex, v, (NS + 1) * 2, idx, NS * 6);
    ui_quad_fringe(tex, v, NS);
}

static void ui_flow_tile(''', "smooth edges (covers)")

patch(r'''    SDL_RenderGeometry(renderer, tex, v, (NC + 1) * 2, idx, NC * 6);
}''', r'''    SDL_RenderGeometry(renderer, tex, v, (NC + 1) * 2, idx, NC * 6);
    ui_quad_fringe(tex, v, NC);
}''', "smooth edges (rounded tiles)")

# ============================================================ a tap on the playing tile: grow first, full screen after
patch(r'''#define UI_TILE_TAP_FULLSCREEN 1''',
      r'''static int ui_tile_fs_pending = 0;      /* the window goes full screen once the video has grown back */
#define UI_TILE_TAP_FULLSCREEN 1''', "pending full screen flag")

patch(r'''#if UI_TILE_TAP_FULLSCREEN
    if (!is_full_screen)
        toggle_full_screen(is);
#endif''', r'''#if UI_TILE_TAP_FULLSCREEN
    if (!is_full_screen)
        ui_tile_fs_pending = 1;         /* not at the same time as the video grows: that made it stutter */
#endif''', "full screen after the growing")

patch(r'''    int64_t now = av_gettime_relative();

    if (is->ui_hold) {''', r'''    int64_t now = av_gettime_relative();

    if (ui_tile_fs_pending) {
        if (ui_vflow)
            ui_tile_fs_pending = 0;                         /* L was pressed again: no full screen */
        else if (ui_vflow_p < 0.02) {
            ui_tile_fs_pending = 0;
            if (!is_full_screen)
                toggle_full_screen(is);
        }
    }
    if (is->ui_hold) {''', "full screen when grown")

# ============================================================ seeking in small steps
patch(r'''static void ui_ctrl_draw(VideoState *is, const SDL_Rect *sk);
static void ui_titlebar_draw(VideoState *is);

static void ui_draw(VideoState *is)''', r'''static void ui_ctrl_draw(VideoState *is, const SDL_Rect *sk);
static void ui_titlebar_draw(VideoState *is);

/* Seeking with the keys or the wheel: the bar follows every step at once, and a seek is sent as soon as the one before it has
   shown its picture, so pictures keep coming while a key is held */
static int ui_ks_want = 0;              /* 1 = a seek to ui_ks_target is waiting to be sent */
static double ui_ks_target = 0.0;       /* seconds: where the steps have taken it (the last one sent, when none waits) */
static int64_t ui_ks_next = 0, ui_ks_issued = 0;
static VideoState *ui_ks_is = NULL;     /* the stream the waiting seek is for (a new item cancels it) */

static void ui_draw(VideoState *is)''', "key seek state")

patch(r'''        if (!seek_by_bytes && is->seek_req)
            pos = is->seek_pos / (double)AV_TIME_BASE;
        else if (isnan(pos))''', r'''        if (!seek_by_bytes && ui_ks_want)
            pos = ui_ks_target;                 /* the steps of the keys, before they are sent */
        else if (!seek_by_bytes && is->seek_req)
            pos = is->seek_pos / (double)AV_TIME_BASE;
        else if (isnan(pos))''', "the bar follows the steps")

patch(r'''static void ui_apply(VideoState *is, int x, int final)
{''', r'''/* Send the waiting key seek when the one before it has landed (its picture and its sound are there) */
static void ui_ks_tick(VideoState *is)
{
    int64_t now;

    if (!ui_ks_want)
        return;
    if (!is || !is->ic || is != ui_ks_is) {
        ui_ks_want = 0;
        return;
    }
    now = av_gettime_relative();
    if (now < ui_ks_next)
        return;
    if ((is->seek_req || is->prec_v || is->prec_a) && now - ui_ks_issued < 1500000)
        return;                         /* still on its way: more steps add up meanwhile */
    ui_precise_next = 1;
    stream_seek(is, (int64_t)(ui_ks_target * AV_TIME_BASE), 0, 0);
    ui_ks_issued = now;
    ui_ks_next = now + 30000;
    ui_ks_want = 0;
}

static void ui_apply(VideoState *is, int x, int final)
{''', "key seek tick")

patch(r'''        pos = get_master_clock(is);
        if (isnan(pos))
            pos = (double)is->seek_pos / AV_TIME_BASE;
        pos += incr;
        if (is->ic->start_time != AV_NOPTS_VALUE && pos < is->ic->start_time / (double)AV_TIME_BASE)
            pos = is->ic->start_time / (double)AV_TIME_BASE;
        ui_precise_next = 1;
        stream_seek(is, (int64_t)(pos * AV_TIME_BASE), (int64_t)(incr * AV_TIME_BASE), 0);
    }
}''', r'''        if (ui_ks_want || is->seek_req || is->prec_v || is->prec_a || av_gettime_relative() - ui_ks_issued < 200000) {
            pos = ui_ks_target;         /* going on from the last step: the clock is not valid while a seek is on its way */
        } else {
            pos = get_master_clock(is);
            if (isnan(pos))
                pos = (double)is->seek_pos / AV_TIME_BASE;
        }
        pos += incr;
        if (is->ic->start_time != AV_NOPTS_VALUE && pos < is->ic->start_time / (double)AV_TIME_BASE)
            pos = is->ic->start_time / (double)AV_TIME_BASE;
        ui_ks_target = pos;
        ui_ks_is = is;
        ui_ks_want = 1;
        is->force_refresh = 1;
    }
}''', "steps add up")

patch(r'''                        pos = get_master_clock(cur_stream);
                        if (isnan(pos))
                            pos = (double)cur_stream->seek_pos / AV_TIME_BASE;
                        pos += incr;
                        if (cur_stream->ic->start_time != AV_NOPTS_VALUE && pos < cur_stream->ic->start_time / (double)AV_TIME_BASE)
                            pos = cur_stream->ic->start_time / (double)AV_TIME_BASE;
                        ui_precise_next = 1;
                        stream_seek(cur_stream, (int64_t)(pos * AV_TIME_BASE), (int64_t)(incr * AV_TIME_BASE), 0);''',
      r'''                        ui_seek_relative(cur_stream, incr);''', "keys use the same steps")

patch(r'''        ui_pause_tick(is);
''', r'''        ui_pause_tick(is);
        ui_ks_tick(is);
''', "key seeks in the loop")

# ============================================================ Preferences: the choices show when the mouse is on a row
patch(r'''static int ui_prefs_hover = -1;     /* row under the mouse */''',
      r'''static int ui_prefs_hover = -1;     /* row under the mouse */
static double ui_pref_open[UI_PREF_ROWS];   /* 0 to 1: how far each row has changed into its list of choices */
static int ui_prefs_anim = 0;       /* 1 = a row is still gliding */''', "choices state")

patch(r'''/* Change a setting (dir = -1 or 1 for the arrows) and save the file */
static void ui_pref_change(int row, int dir)''', r'''/* The choices of a row, for the list that shows when the mouse is on it. Returns how many; sel = the one that is on (or -1) */
static const double ui_seek_choices[] = { 0.3, 0.5, 1, 2, 3, 5, 10, 15, 30 };

static int ui_pref_choices(int row, const char *names[10], char store[10][20], int *sel)
{
    int n = 0, i, b = 0;

    *sel = -1;
    switch (row) {
    case 0:
        for (i = 0; i < 9; i++) {
            snprintf(store[i], 20, "%gs", ui_seek_choices[i]);
            if (fabs(ui_seek_choices[i] - cfg_seek) < fabs(ui_seek_choices[b] - cfg_seek))
                b = i;
        }
        n = 9;
        *sel = b;
        break;
    case 1:
        for (i = 0; i < 5; i++) {
            snprintf(store[i], 20, "%d", ui_vol_steps[i]);
            if (FFABS(ui_vol_steps[i] - cfg_vol_step) < FFABS(ui_vol_steps[b] - cfg_vol_step))
                b = i;
        }
        n = 5;
        *sel = b;
        break;
    case 2:
        for (i = 0; i < 9; i++) {
            snprintf(store[i], 20, "%ds", ui_hide_steps[i]);
            if (fabs(ui_hide_steps[i] - cfg_hide_delay / 1000000.0) < fabs(ui_hide_steps[b] - cfg_hide_delay / 1000000.0))
                b = i;
        }
        n = 9;
        *sel = b;
        break;
    case 4:
        for (i = 0; i < UI_NCOLORS; i++)
            snprintf(store[i], 20, "%s", ui_colors[i].name);
        n = UI_NCOLORS;
        *sel = ui_color_index();
        break;
    case 7:
        snprintf(store[0], 20, "Off");
        snprintf(store[1], 20, "Volume + queue");
        snprintf(store[2], 20, "Seek + queue");
        n = 3;
        *sel = av_clip(cfg_wheel, 0, 2);
        break;
    default:                                    /* the switches: Off and On */
        snprintf(store[0], 20, "Off");
        snprintf(store[1], 20, "On");
        n = 2;
        *sel = (row == 3 ? cfg_fullscreen : row == 5 ? cfg_remember_volume : cfg_quit_when_done) ? 1 : 0;
        break;
    }
    for (i = 0; i < n; i++)
        names[i] = store[i];
    return n;
}

/* Where the choices of a row go (centered in the row; the text gets smaller if they would not fit). Returns how many. */
static int ui_pref_layout(int row, const SDL_Rect *p, int cy, SDL_Rect out[10], const char *names[10], char store[10][20],
                          int *sel, int *px)
{
    int n = ui_pref_choices(row, names, store, sel), i, total, x, w[10], pass;

    *px = 18;
    for (pass = 0; pass < 2; pass++) {
        total = 0;
        for (i = 0; i < n; i++) {
            w[i] = ui_text_width(names[i], *px) + (pass ? 12 : 18);
            total += w[i] + (i ? 4 : 0);
        }
        if (total <= p->w - 32)
            break;
        *px = 15;
    }
    x = p->x + (p->w - total) / 2;
    for (i = 0; i < n; i++) {
        out[i].x = x;
        out[i].y = cy - 16;
        out[i].w = w[i];
        out[i].h = 32;
        x += w[i] + 4;
    }
    return n;
}

/* Which choice of the row is at x, y? -1 if none (or if the choices are not showing yet) */
static int ui_pref_chip_at(int row, const SDL_Rect *p, int x, int y)
{
    SDL_Rect r[10];
    const char *names[10];
    char store[10][20];
    int n, i, sel, px, cy = p->y + UI_PREF_HEAD + row * UI_PREF_ROW + UI_PREF_ROW / 2;

    if (row < 0 || row >= UI_PREF_ROWS || ui_pref_open[row] < 0.4)
        return -1;
    n = ui_pref_layout(row, p, cy, r, names, store, &sel, &px);
    for (i = 0; i < n; i++)
        if (x >= r[i].x && x < r[i].x + r[i].w && y >= r[i].y && y < r[i].y + r[i].h)
            return i;
    return -1;
}

/* Pick choice number idx of a row and save the file */
static void ui_pref_choose(int row, int idx)
{
    switch (row) {
    case 0: cfg_seek = ui_seek_choices[av_clip(idx, 0, 8)]; break;
    case 1: cfg_vol_step = ui_vol_steps[av_clip(idx, 0, 4)]; break;
    case 2: cfg_hide_delay = (int64_t)ui_hide_steps[av_clip(idx, 0, 8)] * 1000000; break;
    case 3: cfg_fullscreen = idx != 0; break;
    case 4:
        idx = av_clip(idx, 0, UI_NCOLORS - 1);
        cfg_bar_r = ui_colors[idx].r;
        cfg_bar_g = ui_colors[idx].g;
        cfg_bar_b = ui_colors[idx].b;
        break;
    case 5: cfg_remember_volume = idx != 0; break;
    case 6: cfg_quit_when_done = idx != 0; break;
    default: cfg_wheel = av_clip(idx, 0, 2); break;
    }
    settings_save();
}

/* Change a setting (dir = -1 or 1 for the arrows) and save the file */
static av_unused void ui_pref_change(int row, int dir)''', "choices of a row")

patch(r'''static int ui_pref_arrows(int row)''', r'''static av_unused int ui_pref_arrows(int row)''', "arrows helper is unused now")

patch(r'''    int ww, wh, i, cy, x_right, vw, vx;

    if (!ui_prefs_open)
        return;
    SDL_GetWindowSize(window, &ww, &wh);
    p = ui_prefs_rect(ww, wh);''', r'''    int ww, wh, i, cy, x_right, vw, vx;
    double e, k, dt;
    static int64_t last = 0;
    int64_t now = av_gettime_relative();

    if (!ui_prefs_open) {
        for (i = 0; i < UI_PREF_ROWS; i++)
            ui_pref_open[i] = 0.0;
        ui_prefs_anim = 0;
        return;
    }
    dt = now - last > 100000 ? 0.016 : (now - last) / 1000000.0;
    last = now;
    ui_prefs_anim = 0;
    for (i = 0; i < UI_PREF_ROWS; i++) {        /* the rows glide toward their list of choices, or back */
        double tgt = i == ui_prefs_hover ? 1.0 : 0.0;

        ui_pref_open[i] += (tgt - ui_pref_open[i]) * (1.0 - exp(-dt / 0.045));
        if (fabs(tgt - ui_pref_open[i]) < 0.01)
            ui_pref_open[i] = tgt;
        else
            ui_prefs_anim = 1;
    }
    SDL_GetWindowSize(window, &ww, &wh);
    p = ui_prefs_rect(ww, wh);''', "rows glide")

patch(r'''        ui_label(p.x + 32, cy, ui_pref_name[i], 20, 245, 245, 245, i == ui_prefs_hover ? 255 : 210);
''', r'''        e = ui_pref_open[i];
        k = 1.0 - e;                            /* how much of the name and the value is still showing */
        ui_label(p.x + 32, cy, ui_pref_name[i], 20, 245, 245, 245, (int)((i == ui_prefs_hover ? 255 : 210) * k));
''', "row name fades")

patch(r'''            ui_arrow(x_right - 184, cy, -1, 150);
            ui_arrow(x_right - 6, cy, 1, 150);''', r'''            ui_arrow(x_right - 184, cy, -1, (int)(150 * k));
            ui_arrow(x_right - 6, cy, 1, (int)(150 * k));''', "arrows fade")

patch(r'''            SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 255);
            ui_pill(&sw);
        }
        if (!ui_pref_arrows(i) && !strcmp(value, "Off"))
            ui_label(vx, cy, value, 20, 150, 150, 150, 255);
        else
            ui_label(vx, cy, value, 20, 245, 245, 245, 255);
    }
    ui_label(p.x + 32, p.y + p.h - UI_PREF_FOOT / 2, "Click the arrows or switches.  Esc closes.",''',
      r'''            SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, (int)(255 * k));
            ui_pill(&sw);
        }
        if (!ui_pref_arrows(i) && !strcmp(value, "Off"))
            ui_label(vx, cy, value, 20, 150, 150, 150, (int)(255 * k));
        else
            ui_label(vx, cy, value, 20, 245, 245, 245, (int)(255 * k));

        if (e > 0.01) {                         /* the choices, gliding in */
            SDL_Rect r[10];
            const char *names[10];
            char store[10][20];
            int n, c, sel, px, yo = (int)((1.0 - e) * 8), hot;

            n = ui_pref_layout(i, &p, cy, r, names, store, &sel, &px);
            for (c = 0; c < n; c++) {
                hot = i == ui_prefs_hover && ui_prefs_mx >= r[c].x && ui_prefs_mx < r[c].x + r[c].w &&
                      ui_prefs_my >= r[c].y && ui_prefs_my < r[c].y + r[c].h;
                if (hot) {                      /* a soft pill under the choice the mouse is on */
                    SDL_Rect pill = r[c];

                    pill.y += yo;
                    SDL_SetRenderDrawColor(renderer, 255, 255, 255, (int)(34 * e));
                    ui_pill(&pill);
                }
                if (c == sel)                   /* the choice that is on: in the bar color */
                    ui_label_c(r[c].x + r[c].w / 2, cy + yo, names[c], px, av_clip(cfg_bar_r + 40, 0, 255),
                               av_clip(cfg_bar_g + 40, 0, 255), av_clip(cfg_bar_b + 40, 0, 255), (int)(255 * e));
                else
                    ui_label_c(r[c].x + r[c].w / 2, cy + yo, names[c], px, 245, 245, 245, (int)((hot ? 255 : 170) * e));
            }
        }
    }
    ui_label(p.x + 32, p.y + p.h - UI_PREF_FOOT / 2, "Move the mouse onto a setting to see its choices.  Esc closes.",''', "choices drawn")

patch(r'''static double ui_pref_open[UI_PREF_ROWS];   /* 0 to 1: how far each row has changed into its list of choices */''',
      r'''static double ui_pref_open[UI_PREF_ROWS];   /* 0 to 1: how far each row has changed into its list of choices */
static int ui_prefs_mx = -1, ui_prefs_my = -1;      /* the mouse in the panel (for the choice under it) */''', "mouse position")

patch(r'''    int ww, wh, x, y, row, x_right;
''', r'''    int ww, wh, x, y, row;
''', "mouse handler variables")

patch(r'''    x_right = p.x + p.w - 32;
    ui_wake();

    if (ev->type == SDL_MOUSEMOTION) {
        ui_prefs_hover = row;
    } else if (ev->type == SDL_MOUSEBUTTONDOWN) {
        if (ev->button.button != SDL_BUTTON_LEFT || x < p.x || x >= p.x + p.w ||
            y < p.y || y >= p.y + p.h)
            ui_prefs_open = 0;                  /* right-click or a click outside closes it */
        else if (row >= 0)
            ui_pref_change(row, x < x_right - 100 ? -1 : 1);
    }''', r'''    ui_wake();
    ui_prefs_mx = x;
    ui_prefs_my = y;

    if (ev->type == SDL_MOUSEMOTION) {
        ui_prefs_hover = row;
    } else if (ev->type == SDL_MOUSEBUTTONDOWN) {
        if (ev->button.button != SDL_BUTTON_LEFT || x < p.x || x >= p.x + p.w ||
            y < p.y || y >= p.y + p.h) {
            ui_prefs_open = 0;                  /* right-click or a click outside closes it */
        } else if (row >= 0) {
            int c = ui_pref_chip_at(row, &p, x, y);

            if (c >= 0)
                ui_pref_choose(row, c);         /* one of the choices of the row */
        }
    }''', "clicks pick a choice")

# ============================================================ the sleep timer row glides too
patch(r'''static int ui_q_hover_kind = 0;''', r'''static double ui_chip_e = 0.0;          /* 0 to 1: how far the sleep timer row has changed into its choices */
static int64_t ui_chip_last = 0;
static int ui_chip_anim = 0;            /* 1 = it is still gliding */
static int ui_q_hover_kind = 0;''', "sleep row state")

patch(r'''    if (hk == UI_Q_SLEEP || hk == UI_Q_CHIP) {
        names = ui_q_chips(&p, cy, chip);
        for (i = 0; i < 6; i++) {
            int hot = hk == UI_Q_CHIP && ui_q_hover_idx == i;

            if (i == sel)               /* the choice that is on: in the bar color */
                ui_label_c(chip[i].x + chip[i].w / 2, cy, names[i], 16, av_clip(cfg_bar_r + 40, 0, 255),
                           av_clip(cfg_bar_g + 40, 0, 255), av_clip(cfg_bar_b + 40, 0, 255), 255);
            else
                ui_label_c(chip[i].x + chip[i].w / 2, cy, names[i], 16, 245, 245, 245, hot ? 255 : 160);
        }
    } else {
        ui_label(p.x + 20, cy, "Sleep timer", 18, 240, 240, 240, 210);
        ui_sleep_text(text, sizeof(text));
        if (sel)
            ui_label(right - 20 - ui_text_width(text, 18), cy, text, 18, av_clip(cfg_bar_r + 40, 0, 255),
                     av_clip(cfg_bar_g + 40, 0, 255), av_clip(cfg_bar_b + 40, 0, 255), 255);
        else
            ui_label(right - 20 - ui_text_width(text, 18), cy, text, 18, 150, 150, 150, 255);
    }''', r'''    {
        double tgt = (hk == UI_Q_SLEEP || hk == UI_Q_CHIP) ? 1.0 : 0.0, ek, dt;
        int64_t t2 = av_gettime_relative();
        int yo;

        dt = t2 - ui_chip_last > 100000 ? 0.016 : (t2 - ui_chip_last) / 1000000.0;
        ui_chip_last = t2;
        ui_chip_e += (tgt - ui_chip_e) * (1.0 - exp(-dt / 0.045));      /* the row glides, it does not jump */
        if (fabs(tgt - ui_chip_e) < 0.01)
            ui_chip_e = tgt;
        ui_chip_anim = ui_chip_e != tgt;
        ek = 1.0 - ui_chip_e;
        yo = (int)(ek * 7);
        if (ui_chip_e > 0.01) {
            names = ui_q_chips(&p, cy, chip);
            for (i = 0; i < 6; i++) {
                int hot = hk == UI_Q_CHIP && ui_q_hover_idx == i;

                if (i == sel)           /* the choice that is on: in the bar color */
                    ui_label_c(chip[i].x + chip[i].w / 2, cy + yo, names[i], 16, av_clip(cfg_bar_r + 40, 0, 255),
                               av_clip(cfg_bar_g + 40, 0, 255), av_clip(cfg_bar_b + 40, 0, 255), (int)(255 * ui_chip_e));
                else
                    ui_label_c(chip[i].x + chip[i].w / 2, cy + yo, names[i], 16, 245, 245, 245,
                               (int)((hot ? 255 : 160) * ui_chip_e));
            }
        }
        if (ek > 0.01) {
            ui_label(p.x + 20, cy - yo, "Sleep timer", 18, 240, 240, 240, (int)(210 * ek));
            ui_sleep_text(text, sizeof(text));
            if (sel)
                ui_label(right - 20 - ui_text_width(text, 18), cy - yo, text, 18, av_clip(cfg_bar_r + 40, 0, 255),
                         av_clip(cfg_bar_g + 40, 0, 255), av_clip(cfg_bar_b + 40, 0, 255), (int)(255 * ek));
            else
                ui_label(right - 20 - ui_text_width(text, 18), cy - yo, text, 18, 150, 150, 150, (int)(255 * ek));
        }
    }''', "the sleep row glides")

patch(r'''    if (ui_q_open && ui_q_off != 0.0)
        is->force_refresh = 1;                  /* the queue list is still gliding */''',
      r'''    if (ui_q_open && ui_q_off != 0.0)
        is->force_refresh = 1;                  /* the queue list is still gliding */
    if ((ui_q_open && ui_chip_anim) || (ui_prefs_open && ui_prefs_anim))
        is->force_refresh = 1;                  /* a row is changing into its choices, or back */''', "redraw while a row glides")

open(path, "w").write(src)
print("Patched fftools/ffplay.c")
