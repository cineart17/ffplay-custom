#!/usr/bin/env python3
# patch_queue_v32.py - run it inside ~/build/ffmpeg-6.1.1 (it edits fftools/ffplay.c)
import sys

PATH = "fftools/ffplay.c"
src = open(PATH).read()
fails = []


def patch(name, old, new):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED: %s matched %d times" % (name, n))
        fails.append(name)
        return
    src = src.replace(old, new)
    print("ok: " + name)


def between(name, start, end, new):
    global src
    a = src.find(start)
    b = src.find(end, a + 1) if a >= 0 else -1
    if a < 0 or b < 0 or src.count(start) != 1:
        print("FAILED: %s matched %d times" % (name, src.count(start)))
        fails.append(name)
        return
    src = src[:a] + new + src[b:]
    print("ok: " + name)


if "ui_fs_cycle" in src:
    print("Already applied")
    sys.exit(0)
if "ui_wblur" in src:
    print("The old v32 from the other account is applied here. This v32 contains all of it, so restore your backup first:")
    print("  cp ~/build/ffplay.c.before-queue-v32 fftools/ffplay.c")
    sys.exit(1)

# ============================================================ key O is gone
patch("no key O", r'''            case SDLK_o:                /* on top of the other windows, or not */
                ui_toggle_on_top();
                break;
''', "")

# ============================================================ a soft blur when the window is left, and back to sharp when it is back
patch("blur state", r'''static int ui_bg = 0;
static int64_t ui_bg_probe = 0;         /* when a picture was last drawn, or the mode last changed */
''', r'''static int ui_bg = 0;
static int64_t ui_bg_probe = 0;         /* when a picture was last drawn, or the mode last changed */
static double ui_wblur = 0.0;           /* 0 to 1: how much of the blurred picture is mixed in */
static double ui_wblur_t = 0.0;         /* where it is going */
static int64_t ui_wblur_last = 0;
#define UI_WBLUR_AWAY 0.40              /* how soft the picture is while another window has the focus (0 = never, 1 = fully) */
''')
patch("blur when background mode ends", r'''    ui_bg = on;
    ui_bg_probe = av_gettime_relative();
}''', r'''    if (!on && ui_bg)
        ui_wblur = FFMAX(ui_wblur, 0.85);       /* the picture comes back soft and sharpens, it does not jump */
    ui_bg = on;
    ui_bg_probe = av_gettime_relative();
}''')
patch("blur tick", r'''static void ui_present(void)
{
    int64_t t0 = av_gettime_relative(), dt;
''', r'''/* Window blur: while the window has neither the focus nor the mouse, the picture is a little soft. When the mouse comes
   in or the focus is back, the blur melts away over about half a second, so the moment the drawing starts again is not
   seen. */
static void ui_wblur_tick(VideoState *is)
{
    int64_t now = av_gettime_relative();
    double dt = (ui_wblur_last && now - ui_wblur_last < 200000) ? (now - ui_wblur_last) / 1000000.0 : 0.016;
    Uint32 fl = window ? SDL_GetWindowFlags(window) : 0;

    ui_wblur_last = now;
    ui_wblur_t = (ui_shown_once && !(fl & (SDL_WINDOW_INPUT_FOCUS | SDL_WINDOW_MOUSE_FOCUS))) ? UI_WBLUR_AWAY : 0.0;
    if (ui_wblur != ui_wblur_t) {
        double tau = ui_wblur_t > ui_wblur ? 0.15 : 0.28;

        ui_wblur += (ui_wblur_t - ui_wblur) * (1.0 - exp(-dt / tau));
        if (fabs(ui_wblur_t - ui_wblur) < 0.01)
            ui_wblur = ui_wblur_t;
        if (is)
            is->force_refresh = 1;
    }
}

static void ui_present(void)
{
    int64_t t0 = av_gettime_relative(), dt;
''')
patch("blur tick in the loop", r'''        UI_TIMED(ui_cover_tick(is));''', r'''        UI_TIMED(ui_wblur_tick(is));
        UI_TIMED(ui_cover_tick(is));''')

# ============================================================ the bars: centered in a pill of liquid glass
patch("bar height", r'''#define UI_BAR_H 28
#define UI_ON(is) ((is)->width >= 260 && (is)->height >= UI_BAR_H * 3)''', r'''#define UI_BAR_H 56                     /* the pill of the bars: 48 high, 4 from the bottom, and a little room around it */
#define UI_MIN_H 84                     /* below this height there are no bars */
#define UI_ON(is) ((is)->width >= 260 && (is)->height >= UI_MIN_H)''')
patch("min height (title bar)", r'''    if (w < 260 || h <= UI_BAR_H * 3)''', r'''    if (w < 260 || h <= UI_MIN_H)''')
patch("min height (buttons)", r'''    if (w < 260 || h < UI_BAR_H * 3)''', r'''    if (w < 260 || h < UI_MIN_H)''')
patch("bars centered in their pill", r'''    int bottom_offset = 6;''', r'''    int bottom_offset = 24;                 /* the middle of the bars is 28 px above the bottom: the middle of the glass pill */''')
patch("glass declarations", r'''static void ui_ctrl_draw(VideoState *is, const SDL_Rect *sk);
static void ui_titlebar_draw(VideoState *is);

static int ui_on_top = 0;''', r'''static void ui_ctrl_draw(VideoState *is, const SDL_Rect *sk);
static void ui_titlebar_draw(VideoState *is);
static void ui_glass_dark(const SDL_Rect *t, int r);

static int ui_on_top = 0;''')
between("pill of dark liquid glass", r'''    {                                           /* a dark glass strip as small as it can be: the bars stay visible on any picture */''',
        r'''    ui_seek_bar(is, &sk, frac);''', r'''    {                                           /* the bars sit in a pill of dark liquid glass, in its middle */
        SDL_Rect pill;

        pill.x = 10;
        pill.w = is->width - 20;
        pill.h = 48;
        pill.y = is->height - 52;
        ui_glass_dark(&pill, 24);
        SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    }
''')

patch("scene for the glass and the blur", r'''    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    SDL_RenderClear(renderer);
    {
        int full_h = is->height;

        /* The bars float over the video, so the video uses the whole window */
        if (is->audio_st && is->show_mode != SHOW_MODE_VIDEO)
            video_audio_display(is);
        else if (is->video_st)
            video_image_display(is);
        is->height = full_h;
    }
    ui_flow_draw(is);
    ui_draw(is);''', r'''    {                                           /* the glass of the bars and the soft blur need the picture as a texture */
        int ww, wh, scene = (UI_ON(is) && is->ic && !cursor_hidden) || ui_wblur > 0.01;

        SDL_GetWindowSize(window, &ww, &wh);
        if (scene) {
            ui_glass_resize(ww, wh);
            scene = ui_scene_tex != NULL;
        }
        if (scene)
            SDL_SetRenderTarget(renderer, ui_scene_tex);
        SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
        SDL_RenderClear(renderer);
        {
            int full_h = is->height;

            /* The bars float over the video, so the video uses the whole window */
            if (is->audio_st && is->show_mode != SHOW_MODE_VIDEO)
                video_audio_display(is);
            else if (is->video_st)
                video_image_display(is);
            is->height = full_h;
        }
        ui_flow_draw(is);
        if (scene) {
            SDL_SetRenderTarget(renderer, NULL);
            SDL_RenderCopy(renderer, ui_scene_tex, NULL, NULL);
            ui_glass_blur();
            if (ui_wblur > 0.01 && ui_blur_tex[1] && ui_blur_tex[2]) {  /* the blur of a window that was left */
                double wb = FFMIN(ui_wblur, 1.0);
                int k;

                for (k = 1; k <= 2; k++) {      /* the soft blur (1/4 size) comes in first, the strong one (1/8) follows it */
                    double a = k == 1 ? FFMIN(wb * 1.5, 1.0) : FFMAX((wb - 0.4) / 0.6, 0.0);

                    if (a <= 0.0)
                        continue;
                    SDL_SetTextureBlendMode(ui_blur_tex[k], SDL_BLENDMODE_BLEND);
                    SDL_SetTextureAlphaMod(ui_blur_tex[k], (int)(255 * a));
                    SDL_RenderCopy(renderer, ui_blur_tex[k], NULL, NULL);
                    SDL_SetTextureAlphaMod(ui_blur_tex[k], 255);
                    SDL_SetTextureBlendMode(ui_blur_tex[k], SDL_BLENDMODE_NONE);
                }
            }
        }
    }
    ui_draw(is);''')

# ============================================================ liquid glass
patch("light blur no longer needed as strips", r'''static void ui_blur_strip(int x, int y, int w, int h)''', r'''static av_unused void ui_blur_strip(int x, int y, int w, int h)''')

between("liquid glass", r'''/* Frosted glass: a soft shadow, the blurred picture behind a rounded rectangle, a dark tint,''',
        r'''/* The idle background: a few soft glows''', r'''/* ----- liquid glass -----
   A panel of real glass: the picture behind it, blurred a little; bent at the rim as by a thick lens (the rim shows the
   picture from further in, stretched); a light haze; a soft highlight on the upper half; and a bright rim that is
   strongest where the light falls (upper left) and where it comes out (lower right). It is built from a mesh of rings
   that follow the rounded shape, so the edge is smooth and the bend is smooth. */
#define UI_LG_ARC 10                    /* points along each corner */
#define UI_LG_NS 5                      /* points along each straight side (short triangles, even on a long edge) */
#define UI_LG_B (UI_LG_ARC + 1 + UI_LG_NS)
#define UI_LG_RINGS 7
#define UI_LG_NP (4 * UI_LG_B)          /* points on each ring */

static void ui_liquid(const SDL_Rect *t, int r, int tr, int tg, int tb, int ta, int shadow)
{
    static const double depth[UI_LG_RINGS] = { -1.2, 0.4, 2.0, 5.0, 9.0, 15.0, 24.0 };
    static SDL_Vertex vt[UI_LG_RINGS * UI_LG_NP + 1], vh[UI_LG_RINGS * UI_LG_NP + 1];
    static SDL_Vertex vs[UI_LG_RINGS * UI_LG_NP + 1], vr[UI_LG_RINGS * UI_LG_NP + 1];
    static int idx[(UI_LG_RINGS - 1) * UI_LG_NP * 6 + UI_LG_NP * 3];
    SDL_Texture *bt = ui_blur_tex[2];
    double lim = FFMIN(t->w, t->h) / 2.0 - 1.0, D, Rf;
    int k, j, c, i, ni = 0, nrim, nv = UI_LG_RINGS * UI_LG_NP;

    r = FFMIN(r, FFMIN(t->w, t->h) / 2);
    if (shadow)
        ui_shadow(t, r);
    if (!bt || ui_gw <= 0 || ui_gh <= 0 || t->w < 12 || t->h < 12) {   /* no blurred picture yet: a plain tinted shape */
        SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
        SDL_SetRenderDrawColor(renderer, tr, tg, tb, FFMIN(ta + 70, 235));
        ui_rr_fill(t, r);
        return;
    }
    D = FFMIN(24.0, lim);
    Rf = 0.5 * D;
    for (k = 0; k < UI_LG_RINGS; k++) {
        double d = depth[k] < 0 ? depth[k] : depth[k] * D / 24.0;
        double dn = av_clipd(d / D, 0.0, 1.0);
        double s = Rf * (1.0 - dn) * (1.0 - dn);        /* how far further in the picture is taken from */
        double x0 = t->x + d, y0 = t->y + d, x1 = t->x + t->w - d, y1 = t->y + t->h - d;
        double rk = FFMAX(r - d, 0.5);
        double P[UI_LG_NP][4];                          /* x, y, and where it points out */

        for (c = 0; c < 4; c++) {
            double cx = (c == 0 || c == 3) ? x0 + rk : x1 - rk;
            double cy = (c == 0 || c == 1) ? y0 + rk : y1 - rk;

            for (i = 0; i <= UI_LG_ARC; i++) {
                double a = (180.0 + 90.0 * c + 90.0 * i / UI_LG_ARC) * 3.14159265358979 / 180.0;
                double *q = P[c * UI_LG_B + i];

                q[2] = cos(a);
                q[3] = sin(a);
                q[0] = cx + rk * q[2];
                q[1] = cy + rk * q[3];
            }
        }
        for (c = 0; c < 4; c++)                         /* the straight sides: points between the end of one corner and the start of the next */
            for (i = 0; i < UI_LG_NS; i++) {
                double *e = P[c * UI_LG_B + UI_LG_ARC], *q = P[c * UI_LG_B + UI_LG_ARC + 1 + i], *st = P[((c + 1) % 4) * UI_LG_B];
                double f = (i + 1.0) / (UI_LG_NS + 1.0);

                q[0] = e[0] + (st[0] - e[0]) * f;
                q[1] = e[1] + (st[1] - e[1]) * f;
                q[2] = e[2];
                q[3] = e[3];
            }
        for (j = 0; j < UI_LG_NP; j++) {
            double px = P[j][0], py = P[j][1], ox = P[j][2], oy = P[j][3];
            double lit = FFMAX(ox * -0.62 + oy * -0.78, 0.0);       /* light from the upper left */
            double lit2 = FFMAX(ox * 0.62 + oy * 0.78, 0.0);        /* and out again at the lower right */
            double rim = av_clipd(60.0 + 170.0 * lit * lit + 85.0 * lit2 * lit2, 0.0, 255.0);
            double sheen = 70.0 * av_clipd(1.0 - (py - t->y) / (t->h * 0.5), 0.0, 1.0);
            SDL_Vertex *p = &vt[k * UI_LG_NP + j];

            p->position.x = (float)px;
            p->position.y = (float)py;
            p->color.r = p->color.g = p->color.b = 255;
            p->color.a = k == 0 ? 0 : 255;
            p->tex_coord.x = (float)av_clipd((px - ox * s) / ui_gw, 0.0, 1.0);      /* in = against the outward direction */
            p->tex_coord.y = (float)av_clipd((py - oy * s) / ui_gh, 0.0, 1.0);
            vh[k * UI_LG_NP + j] = *p;
            vh[k * UI_LG_NP + j].color.r = tr;
            vh[k * UI_LG_NP + j].color.g = tg;
            vh[k * UI_LG_NP + j].color.b = tb;
            vh[k * UI_LG_NP + j].color.a = k == 0 ? 0 : (Uint8)(ta * (0.62 + 0.38 * dn));      /* thinner at the rim: the bend shows */
            vs[k * UI_LG_NP + j] = *p;
            vs[k * UI_LG_NP + j].color.a = k == 0 ? 0 : (Uint8)sheen;
            vr[k * UI_LG_NP + j] = *p;
            vr[k * UI_LG_NP + j].color.a = k == 1 ? (Uint8)rim : k == 2 ? (Uint8)(rim * 0.4) : 0;
        }
    }
    vt[nv].position.x = vh[nv].position.x = vs[nv].position.x = vr[nv].position.x = (float)(t->x + t->w / 2.0);
    vt[nv].position.y = vh[nv].position.y = vs[nv].position.y = vr[nv].position.y = (float)(t->y + t->h / 2.0);
    vt[nv].tex_coord.x = (float)((t->x + t->w / 2.0) / ui_gw);
    vt[nv].tex_coord.y = (float)((t->y + t->h / 2.0) / ui_gh);
    vt[nv].color.r = vt[nv].color.g = vt[nv].color.b = 255;
    vt[nv].color.a = 255;
    vh[nv] = vt[nv];
    vh[nv].color.r = tr;
    vh[nv].color.g = tg;
    vh[nv].color.b = tb;
    vh[nv].color.a = (Uint8)ta;
    vs[nv] = vt[nv];
    vs[nv].color.a = 0;
    vr[nv] = vt[nv];
    vr[nv].color.a = 0;
    for (k = 0; k < UI_LG_RINGS - 1; k++)
        for (j = 0; j < UI_LG_NP; j++) {
            int a = k * UI_LG_NP + j, b = k * UI_LG_NP + (j + 1) % UI_LG_NP;
            int cc = (k + 1) * UI_LG_NP + j, dd = (k + 1) * UI_LG_NP + (j + 1) % UI_LG_NP;

            idx[ni++] = a;  idx[ni++] = b;  idx[ni++] = cc;
            idx[ni++] = b;  idx[ni++] = dd; idx[ni++] = cc;
        }
    nrim = 3 * UI_LG_NP * 6;                    /* the rim is the outer three rings */
    for (j = 0; j < UI_LG_NP; j++) {            /* the middle */
        idx[ni++] = (UI_LG_RINGS - 1) * UI_LG_NP + j;
        idx[ni++] = (UI_LG_RINGS - 1) * UI_LG_NP + (j + 1) % UI_LG_NP;
        idx[ni++] = nv;
    }
    SDL_SetTextureBlendMode(bt, SDL_BLENDMODE_BLEND);
    SDL_RenderGeometry(renderer, bt, vt, nv + 1, idx, ni);     /* the bent, blurred picture */
    SDL_SetTextureBlendMode(bt, SDL_BLENDMODE_NONE);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    SDL_RenderGeometry(renderer, NULL, vh, nv + 1, idx, ni);   /* the haze */
    SDL_RenderGeometry(renderer, NULL, vs, nv + 1, idx, ni);   /* the highlight on the upper half */
    SDL_RenderGeometry(renderer, NULL, vr, nv + 1, idx, nrim); /* the rim of light */
}

/* Light liquid glass: menus, panels and cards (dark text on them) */
static void ui_glass(const SDL_Rect *t, int r)
{
    int ink = ui_ink_dark;

    ui_ink_dark = 0;                            /* the glass itself is drawn as it is */
    ui_liquid(t, r, 225 + cfg_bar_r / 10, 228 + cfg_bar_g / 10, 232 + cfg_bar_b / 10, 165, 1);
    ui_ink_dark = ink;
}

/* Dark liquid glass: the pill of the seek and volume bars, over the video */
static void ui_glass_dark(const SDL_Rect *t, int r)
{
    int ink = ui_ink_dark;

    ui_ink_dark = 0;
    ui_liquid(t, r, 10, 12, 16, 105, 0);
    ui_ink_dark = ink;
}

''')

# ============================================================ smoother seeking with a held key
patch("held key seeks carry on", r'''    if ((is->seek_req || is->prec_v || is->prec_a) && now - ui_ks_issued < 1500000)
        return;                         /* still on its way: more steps add up meanwhile */''', r'''    if ((is->seek_req || is->prec_v || is->prec_a) && now - ui_ks_issued < 1500000) {
        if (!is->seek_req && (is->prec_v || is->prec_a) && ui_ks_target > is->prec_target &&
            ui_ks_target - is->prec_target < 20.0) {
            /* still skipping toward the last target: carry on to the new one, without a new start from a key frame
               (the pictures between are skipped as before, but the decoder never goes back) */
            is->prec_target = ui_ks_target;
            is->seek_pos = (int64_t)(ui_ks_target * AV_TIME_BASE);      /* the bar shows it */
            ui_ks_issued = now;
            ui_ks_want = 0;
        }
        return;                         /* still on its way: more steps add up meanwhile */
    }''')
patch("keys come faster", r'''    ui_ks_next = now + 30000;''', r'''    ui_ks_next = now + 10000;''')
patch("drag seeks come faster", r'''    ui_seek_next = now + 50000;         /* about 20 seeks a second while dragging */''', r'''    ui_seek_next = now + 33000;         /* about 30 seeks a second while dragging */''')

# ============================================================ full screen in three steps: double tap cycles them
patch("state of the filled window", r'''static int     ui_user_sized = 0; ''', r'''static int     ui_maxed = 0;                /* 1 = conventional full screen: the window fills the screen under the panel (maximized) */
static int     ui_user_sized = 0; ''')
patch("sizes of a filled window are not the user's", r'''    if (!cfg_keep_window || !window || is_full_screen || w < 260 || h < 160)
        return;
    if (SDL_GetWindowFlags(window) & (SDL_WINDOW_FULLSCREEN | SDL_WINDOW_FULLSCREEN_DESKTOP))
        return;''', r'''    if (window && !is_full_screen && now - ui_fs_toggle_at > 1500000)
        ui_maxed = (SDL_GetWindowFlags(window) & SDL_WINDOW_MAXIMIZED) != 0;      /* the window manager may have maximized or restored it */
    if (!cfg_keep_window || !window || is_full_screen || w < 260 || h < 160)
        return;
    if (SDL_GetWindowFlags(window) & (SDL_WINDOW_FULLSCREEN | SDL_WINDOW_FULLSCREEN_DESKTOP))
        return;
    if (ui_maxed)
        return;                                 /* a window that fills the screen is not a size the user chose */''')
patch("full screen steps", r'''static void toggle_full_screen(VideoState *is)
{
    is_full_screen = !is_full_screen;
    ui_fs_toggle_at = av_gettime_relative();
    ui_prog_until = av_gettime_relative() + 2000000;     /* the size changes of going in and out are ours */
    SDL_SetWindowFullscreen(window, is_full_screen ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0);
}''', r'''/* Fill the screen under the panel (on = 1) or give the window its own size back (on = 0) */
static void ui_max_set(int on)
{
    ui_maxed = on;
    ui_fs_toggle_at = av_gettime_relative();
    ui_prog_until = av_gettime_relative() + 2000000;
    {                                           /* wait (at most 0.4 s) until the window manager has left full screen */
        int64_t t0 = av_gettime_relative();

        SDL_PumpEvents();
        while (av_gettime_relative() - t0 < 400000 &&
               (SDL_GetWindowFlags(window) & (SDL_WINDOW_FULLSCREEN | SDL_WINDOW_FULLSCREEN_DESKTOP))) {
            SDL_Delay(10);
            SDL_PumpEvents();
        }
    }
    if (on) {
        SDL_MaximizeWindow(window);
    } else {
        int64_t t0 = av_gettime_relative();

        SDL_RestoreWindow(window);
        SDL_PumpEvents();
        while (av_gettime_relative() - t0 < 400000 && (SDL_GetWindowFlags(window) & SDL_WINDOW_MAXIMIZED)) {
            SDL_Delay(10);                      /* the corner that is grabbed next needs the new size */
            SDL_PumpEvents();
        }
    }
}

/* F, the title bar button and Esc: complete full screen on or off. Off goes back to where it came from (the window,
   or the window that fills the screen). */
static void toggle_full_screen(VideoState *is)
{
    is_full_screen = !is_full_screen;
    ui_fs_toggle_at = av_gettime_relative();
    ui_prog_until = av_gettime_relative() + 2000000;     /* the size changes of going in and out are ours */
    SDL_SetWindowFullscreen(window, is_full_screen ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0);
    if (!is_full_screen && ui_maxed)
        ui_max_set(1);
}

/* A double tap in the picture: window or filled window -> complete full screen (no bars at all) -> the filled window,
   with the title bar and the panel of the window manager, where the corners can be dragged -> complete full screen... */
static void ui_fs_cycle(VideoState *is)
{
    ui_fs_toggle_at = av_gettime_relative();
    ui_prog_until = av_gettime_relative() + 2000000;
    if (is_full_screen) {
        is_full_screen = 0;
        SDL_SetWindowFullscreen(window, 0);
        ui_max_set(1);
    } else {
        is_full_screen = 1;
        SDL_SetWindowFullscreen(window, SDL_WINDOW_FULLSCREEN_DESKTOP);
    }
}''')
patch("grab a corner of the filled window", r'''        edges = ui_edges_at(ev->button.x, ev->button.y);
        if (!edges)
            return 0;                   /* only the edges and corners are ours; a click on the picture goes on */
        ui_win_mode = 2;''', r'''        edges = ui_edges_at(ev->button.x, ev->button.y);
        if (!edges)
            return 0;                   /* only the edges and corners are ours; a click on the picture goes on */
        if (ui_maxed)
            ui_max_set(0);              /* the window gets its own size back, and the corner is dragged from there */
        ui_win_mode = 2;''')
patch("double tap cycles the full screen", r'''                if (av_gettime_relative() - last_mouse_left_click <= 500000) {
                    toggle_full_screen(cur_stream);''', r'''                if (av_gettime_relative() - last_mouse_left_click <= 500000) {
                    ui_fs_cycle(cur_stream);''')
patch("Esc leaves the filled window", r'''                } else if (is_full_screen) {
                    toggle_full_screen(cur_stream);
                    cur_stream->force_refresh = 1;
                }
                break;''', r'''                } else if (is_full_screen) {
                    toggle_full_screen(cur_stream);
                    cur_stream->force_refresh = 1;
                } else if (ui_maxed) {
                    ui_max_set(0);
                    cur_stream->force_refresh = 1;
                }
                break;''')

# ============================================================ preferences: the name and the choices in one centered row
patch("row layout: name and choices centered", r'''static int ui_pref_layout(int row, const SDL_Rect *p, int cy, SDL_Rect out[10], const char *names[10], char store[10][20],
                          int *sel, int *px)
{
    static const int px_try[4] = { 18, 16, 15, 14 }, pad_try[4] = { 18, 14, 10, 8 };
    int n = ui_pref_choices(row, names, store, sel), i, total = 0, x, w[10], pass, room;

    room = p->w - 2 * ui_pr_mg - ui_text_width(ui_pref_name[row], ui_pr_px) - 18;
    *px = 14;
    for (pass = 0; pass < 4; pass++) {
        total = 0;
        for (i = 0; i < n; i++) {
            w[i] = ui_text_width(names[i], px_try[pass]) + pad_try[pass];
            total += w[i] + (i ? 3 : 0);
        }
        *px = px_try[pass];
        if (total <= room)
            break;
    }
    x = p->x + p->w - ui_pr_mg - total;         /* against the right margin */
    for (i = 0; i < n; i++) {
        out[i].x = x;
        out[i].y = cy - FFMIN(32, ui_pr_row - 6) / 2;
        out[i].w = w[i];
        out[i].h = FFMIN(32, ui_pr_row - 6);
        x += w[i] + 3;
    }
    return n;
}''', r'''static int ui_pl_title_x = 0;           /* where the name starts when the choices are showing */

/* The name and the choices of a row are one row of items: the name first, then the choices, the same padding on each and
   the same gap between them, the whole row in the middle of the panel. */
static int ui_pref_layout(int row, const SDL_Rect *p, int cy, SDL_Rect out[10], const char *names[10], char store[10][20],
                          int *sel, int *px)
{
    static const int px_try[4] = { 18, 16, 15, 14 }, pad_try[4] = { 18, 14, 10, 8 }, gap_try[4] = { 6, 5, 4, 3 };
    int n = ui_pref_choices(row, names, store, sel), i, total = 0, x, w[10], pass, pp = 3, room, tw = 0, gap = 3;

    room = p->w - 2 * ui_pr_mg;
    *px = 14;
    for (pass = 0; pass < 4; pass++) {
        pp = pass;
        gap = gap_try[pass];
        tw = ui_text_width(ui_pref_name[row], ui_pr_px) + pad_try[pass];    /* the name is an item of the row too */
        total = tw;
        for (i = 0; i < n; i++) {
            w[i] = ui_text_width(names[i], px_try[pass]) + pad_try[pass];
            total += w[i] + gap;
        }
        *px = px_try[pass];
        if (total <= room)
            break;
    }
    x = p->x + (p->w - total) / 2;              /* the whole row in the middle */
    ui_pl_title_x = x + pad_try[pp] / 2;
    x += tw + gap;
    for (i = 0; i < n; i++) {
        out[i].x = x;
        out[i].y = cy - FFMIN(32, ui_pr_row - 6) / 2;
        out[i].w = w[i];
        out[i].h = FFMIN(32, ui_pr_row - 6);
        x += w[i] + gap;
    }
    return n;
}''')
patch("panel width for the centered row", r'''    for (i = 0; i < n; i++)
        total += ui_text_width(names[i], 14) + 8 + (i ? 3 : 0);
    return 2 * ui_pr_mg + ui_text_width(ui_pref_name[row], ui_pr_px) + 18 + total;''', r'''    for (i = 0; i < n; i++)
        total += ui_text_width(names[i], 14) + 8 + 3;
    return 2 * ui_pr_mg + ui_text_width(ui_pref_name[row], ui_pr_px) + 8 + total;''')
patch("the name glides into the row", r'''        ui_label(p.x + ui_pr_mg, cy, ui_pref_name[i], ui_pr_px, 245, 245, 245, i == ui_prefs_hover ? 255 : 210);     /* the name stays */
''', r'''        {                                       /* the name glides from the left margin into the row of the choices, and back */
            SDL_Rect r0[10];
            const char *n0[10];
            char s0[10][20];
            int sel0, px0, tx = p.x + ui_pr_mg;

            if (e > 0.01) {
                ui_pref_layout(i, &p, cy, r0, n0, s0, &sel0, &px0);
                tx += (int)((ui_pl_title_x - tx) * se);
            }
            ui_label(tx, cy, ui_pref_name[i], ui_pr_px, 245, 245, 245, i == ui_prefs_hover ? 255 : 210);
        }
''')

# ============================================================ the blur needs three steps, not four
patch("blur: three steps", r'''    for (i = 0; i < 4; i++) {
        if (!ui_blur_tex[i])
            break;
        SDL_SetRenderTarget(renderer, ui_blur_tex[i]);''', r'''    for (i = 0; i < 3; i++) {                   /* 1/2, 1/4 and 1/8 size are all that is used (the 1/16 step was a waste) */
        if (!ui_blur_tex[i])
            break;
        SDL_SetRenderTarget(renderer, ui_blur_tex[i]);''')


if fails:
    print("\n%d patches did not apply. Nothing was written." % len(fails))
    sys.exit(1)
open(PATH, "w").write(src)
print("Patched " + PATH)
