#!/usr/bin/env python3
# Update 37 for ffplay-custom (on top of patch_queue_v36.py).
#   * Miniplayer: remembers where you left it (position and width, also between runs, in ~/.config/ffplay-custom/miniplayer.conf).
#     A remembered spot that is off every screen falls back to the bottom right corner.
#   * Miniplayer -> full screen: the window now GROWS out of the miniplayer (eased, about 0.28 s) instead of jumping back to its old
#     size first, and the miniplayer's always on top and show on all workspaces are switched off on the way (X11 sessions for
#     the workspace part, the window manager menu does the same elsewhere). Esc from that full screen still goes back to the
#     window the miniplayer was entered from (v35 behaviour).
#   * Seeking: the blur came from the preview pictures (192 x 108, one every few seconds) being stretched over the whole window
#     while a seek is on its way. Previews are now 320 x 180, and they are only used when the jump is bigger than the gap between
#     two previews; small steps show the real, sharp frames. The seek bar tooltip keeps its old size.
#   * New tiled queue view (flat tiles, no tilt), replaces the convex video queue view: two rows (three in a tall window) where the
#     lower row continues the upper one; swiping any row moves all of them. Entered with L, Tab, or a two finger swipe up on a
#     touchpad. The entry animation is kept (the video shrinks into its tile, the others slide out from behind it).
#       - Type at once to search: the closest match springs to the tile in focus, the others follow to its right, the letters of the
#         title that match what you typed are drawn in the seek bar color. Sections: In this queue, In Music, In Videos (your
#         Music and Videos folders, or music_folder / video_folder in settings.conf). Left/Right, swipes and the wheel move through a section, Up/Down switch sections or rows.
#       - Letter shortcuts are off while the view is open (a paused video that opened it by itself keeps them).
#       - Esc closes the search, Esc again closes the view. Enter plays the tile in focus (a file from a folder is added to the queue).
#       - Tiles can be dragged to a new place in the queue (hold and drag).
#   * Many tile titles no longer thrash the text cache (128 -> 320 entries).
#   * Queue panel: a row can now be held and dragged by its name, not only by the dots (a plain click still plays it).
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v36.py. Writes the file only if every edit matches.
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


if "ui_tv_draw" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_icon_tex" not in src:
    print("Apply patch_queue_v36.py first. Nothing written.")
    sys.exit(1)

# ---------------------------------------------------------------- globals and forward declarations
patch("globals", r'''static void ui_flow_swipe(VideoState *is, SDL_Event *ev);

static int ui_scrub_draw(VideoState *is, const SDL_Rect *rect);''', r'''static void ui_flow_swipe(VideoState *is, SDL_Event *ev);
static int ui_tv_on(VideoState *is);                    /* v37: the tiled queue view */
static int ui_tv_cap(VideoState *is);
static int ui_tv_wheel(VideoState *is, SDL_Event *ev);
static int ui_tv_key(VideoState *is, SDL_Event *ev);
static int ui_tv_text(VideoState *is, const char *t);
static void ui_tv_enter(VideoState *is);
static void ui_tv_draw(VideoState *is);
static int ui_tv_click(VideoState *is, int x, int y);
static int ui_tv_motion(VideoState *is, int x, int y);
static int ui_tv_release(VideoState *is, int x, int y);
static int ui_tv_moving = 0;                            /* 1 = the tiled view is animating: keep drawing */
static int ui_grow_on = 0;                              /* 1 = the miniplayer is growing into full screen */
static void ui_pip_save(void);
static void ui_grow_tick(VideoState *is);

static int ui_scrub_draw(VideoState *is, const SDL_Rect *rect);''')

patch("do_exit saves the miniplayer", r'''static void do_exit(VideoState *is)
{
    ui_th_stop();''', r'''static void do_exit(VideoState *is)
{
    ui_th_stop();
    ui_pip_save();                              /* a miniplayer that is still open is remembered where it is */''')

patch("note_size ignores the grow", r'''    int64_t now = av_gettime_relative();

    if (window && !is_full_screen && now - ui_fs_toggle_at > 1500000)
        ui_maxed''', r'''    int64_t now = av_gettime_relative();

    if (ui_grow_on)
        return;                                 /* the steps of the miniplayer growing are ours */
    if (window && !is_full_screen && now - ui_fs_toggle_at > 1500000)
        ui_maxed''')

patch("titlebar hidden while growing", r'''    if (!window || cursor_hidden || is_full_screen)     /* windowed mode only; hides with the cursor like the seek bar */''',
      r'''    if (!window || cursor_hidden || is_full_screen || ui_grow_on)     /* windowed mode only; hides with the cursor like the seek bar */''')

# ---------------------------------------------------------------- seek blur
patch("preview size", r'''    tw = 192;
    th = (int)((double)ch * tw / cw);
    if (th > 108) {
        th = 108;''', r'''    tw = 320;                                   /* v37: bigger previews, they are drawn large while seeking */
    th = (int)((double)ch * tw / cw);
    if (th > 180) {
        th = 180;''')

patch("scrub only for big jumps", r'''    idx = av_clip((int)(av_clipd(f, 0.0, 1.0) * n), 0, n - 1);
    for (d = 0; d < n && found < 0; d++) {
        if (idx - d >= 0 && __atomic_load_n(&ui_th.t[idx - d].ready, __ATOMIC_ACQUIRE))
            found = idx - d;
        else if (idx + d < n && __atomic_load_n(&ui_th.t[idx + d].ready, __ATOMIC_ACQUIRE))
            found = idx + d;
    }
    if (found < 0)
        return 0;
    t = &ui_th.t[found];
    if (!t->tex) {
        t->tex = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STATIC, ui_th.w, ui_th.h);
        if (!t->tex)
            return 0;
        SDL_UpdateTexture(t->tex, NULL, t->rgba, ui_th.w * 4);
        SDL_SetTextureBlendMode(t->tex, SDL_BLENDMODE_NONE);
    }
    SDL_RenderCopy(renderer, t->tex, NULL, rect);
    return 1;''', r'''    idx = av_clip((int)(av_clipd(f, 0.0, 1.0) * n), 0, n - 1);
    {                                           /* v37: a preview is a small picture stretched over the window, so it is only worth it when the jump is
                                                   bigger than the gap between two previews; a small step shows the real, sharp frames */
        double cur = get_master_clock(is), gap = FFMAX(2.0, 1.5 * ui_th.dur / n);

        if (!isnan(cur) && fabs(av_clipd(f, 0.0, 1.0) * ui_th.dur - (cur - ui_th.start / (double)AV_TIME_BASE)) < gap)
            return 0;
    }
    for (d = 0; d < n && found < 0; d++) {
        if (idx - d >= 0 && __atomic_load_n(&ui_th.t[idx - d].ready, __ATOMIC_ACQUIRE))
            found = idx - d;
        else if (idx + d < n && __atomic_load_n(&ui_th.t[idx + d].ready, __ATOMIC_ACQUIRE))
            found = idx + d;
    }
    if (found < 0)
        return 0;
    t = &ui_th.t[found];
    if (!t->tex) {
        t->tex = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STATIC, ui_th.w, ui_th.h);
        if (!t->tex)
            return 0;
        SDL_UpdateTexture(t->tex, NULL, t->rgba, ui_th.w * 4);
        SDL_SetTextureBlendMode(t->tex, SDL_BLENDMODE_NONE);
    }
    SDL_RenderCopy(renderer, t->tex, NULL, rect);
    return 1;''')

# ---------------------------------------------------------------- queue panel: drag by the name
patch("press state", r'''static int ui_q_drag = -1;      /* queue item being dragged (-1 = none) */''',
      r'''static int ui_q_drag = -1;      /* queue item being dragged (-1 = none) */
static int ui_q_press = -1;     /* v37: a row the mouse went down on: a click plays it, a drag moves it */
static int ui_q_press_x = 0, ui_q_press_y = 0;
static VideoState *ui_q_press_is = NULL;''')

patch("press on a name", r'''    } else {                        /* an item: play it now */
        q_forced = item;
        ui_end_current(is);         /* the menu stays open, so you can keep browsing the queue */
    }
    return 1;''', r'''    } else {                        /* an item: a click plays it (when the mouse comes up), held and moved it is dragged */
        ui_q_press = item;
        ui_q_press_x = x;
        ui_q_press_y = y;
        ui_q_press_is = is;
        SDL_CaptureMouse(SDL_TRUE);
    }
    return 1;''')

patch("press turns into a drag", r'''    if (ui_q_drag >= 0) {           /* dragging a queue item: the panel owns the mouse */
        if (ev->type == SDL_MOUSEMOTION) {''', r'''    if (ui_q_press >= 0) {          /* the mouse is down on a name: it becomes a drag once it has moved a little */
        if (ev->type == SDL_MOUSEMOTION && (FFABS(x - ui_q_press_x) >= 5 || FFABS(y - ui_q_press_y) >= 5)) {
            ui_q_drag = ui_q_press;
            ui_q_drag_y = y;
            ui_q_press = -1;
        } else {
            if (is)
                is->force_refresh = 1;
            return 1;
        }
    }
    if (ui_q_drag >= 0) {           /* dragging a queue item: the panel owns the mouse */
        if (ev->type == SDL_MOUSEMOTION) {''')

patch("press released", r'''    SDL_Rect p;
    int ww, wh;

    if (ui_q_drag < 0 || ev->button.button != SDL_BUTTON_LEFT)
        return 0;''', r'''    SDL_Rect p;
    int ww, wh;

    if (ui_q_press >= 0 && ev->button.button == SDL_BUTTON_LEFT) {      /* no drag happened: it was a click, play the item */
        int it = ui_q_press;

        ui_q_press = -1;
        SDL_CaptureMouse(SDL_FALSE);
        if (it < q_count) {
            q_forced = it;
            ui_end_current(ui_q_press_is);  /* the menu stays open, so you can keep browsing the queue */
        }
        return 1;
    }
    if (ui_q_drag < 0 || ev->button.button != SDL_BUTTON_LEFT)
        return 0;''')

# ---------------------------------------------------------------- hooks of the tiled view
patch("flow redraw", r'''    return ui_flow_on(is) && (!is->paused || ui_flow_moving || ui_flow_dragging || ui_tp_on);''',
      r'''    return ui_flow_on(is) && (!is->paused || ui_flow_moving || ui_flow_dragging || ui_tp_on || (ui_tv_moving && ui_tv_on(is)));''')

patch("flow draw hook", r'''    ui_flow_vmode = ui_flow_video(is);          /* over a video: tiles in their own shape, no disc */
    if (!ui_flow_vmode) {                       /* an audio item shows the queue view''', r'''    if (ui_tv_on(is)) {                         /* v37: the tiled view draws instead */
        ui_tv_draw(is);
        return;
    }
    ui_flow_vmode = ui_flow_video(is);          /* over a video: tiles in their own shape, no disc */
    if (!ui_flow_vmode) {                       /* an audio item shows the queue view''')

patch("click hook", r'''static int ui_flow_click(VideoState *is, int x, int y)
{
    int idx = ui_flow_cover_at(is, x, y);
''', r'''static int ui_flow_click(VideoState *is, int x, int y)
{
    int idx;

    if (ui_tv_on(is))
        return ui_tv_click(is, x, y);
    idx = ui_flow_cover_at(is, x, y);
''')

patch("snap back hook", r'''static int ui_flow_snap_back(VideoState *is)
{
    if (!ui_flow_on(is) || ui_flow_press >= 0 || ui_flow_dragging)
        return 0;''', r'''static int ui_flow_snap_back(VideoState *is)
{
    if (!ui_flow_on(is) || ui_flow_press >= 0 || ui_flow_dragging || ui_tv_on(is))
        return 0;''')

patch("motion hook", r'''static int ui_flow_motion(VideoState *is, int x, int y)
{
    ui_hov_x = x;
    ui_hov_y = y;
    if (ui_flow_press < 0)''', r'''static int ui_flow_motion(VideoState *is, int x, int y)
{
    ui_hov_x = x;
    ui_hov_y = y;
    if (ui_tv_on(is))
        return ui_tv_motion(is, x, y);
    if (ui_flow_press < 0)''')

patch("release hook", r'''static int ui_flow_release(VideoState *is, int x, int y)
{
    int idx = ui_flow_press;
''', r'''static int ui_flow_release(VideoState *is, int x, int y)
{
    int idx = ui_flow_press;

    if (ui_tv_on(is))
        return ui_tv_release(is, x, y);
''')

patch("wheel hook", r'''    int steps, i;

    if (!cfg_wheel || ui_menu_open || ui_prefs_open)
        return;
    {
        double ax, ay;''', r'''    int steps, i;

    if (ui_tv_wheel(is, ev))                    /* v37: swipes in the tiled view, and the two finger swipe up that opens it */
        return;
    if (!cfg_wheel || ui_menu_open || ui_prefs_open)
        return;
    {
        double ax, ay;''')

patch("key hook", r'''        refresh_loop_wait_event(cur_stream, &event);
        switch (event.type) {
        case SDL_KEYDOWN:
            event.key.keysym.sym = ui_key_translate(event.key.keysym.sym);   /* the keys chosen in settings.conf */''', r'''        refresh_loop_wait_event(cur_stream, &event);
        switch (event.type) {
        case SDL_TEXTINPUT:                     /* v37: typing in the tiled view searches */
            if (ui_tv_text(cur_stream, event.text.text))
                cur_stream->force_refresh = 1;
            break;
        case SDL_KEYDOWN:
            if (ui_tv_key(cur_stream, &event)) {    /* v37: the tiled view uses the keys (the letters are the search) */
                cur_stream->force_refresh = 1;
                break;
            }
            event.key.keysym.sym = ui_key_translate(event.key.keysym.sym);   /* the keys chosen in settings.conf */''')

patch("tab opens the view", r'''            switch (event.key.keysym.sym) {
            case SDLK_f:
                toggle_full_screen(cur_stream);
                cur_stream->force_refresh = 1;
                break;
            case SDLK_n:
                ui_user_skip = 1;
                q_step = 1;
                ui_end_stream(cur_stream);
                return;''', r'''            switch (event.key.keysym.sym) {
            case SDLK_TAB:                      /* v37: the tiled queue view (or the two finger swipe up) */
                ui_tv_enter(cur_stream);
                cur_stream->force_refresh = 1;
                break;
            case SDLK_f:
                toggle_full_screen(cur_stream);
                cur_stream->force_refresh = 1;
                break;
            case SDLK_n:
                ui_user_skip = 1;
                q_step = 1;
                ui_end_stream(cur_stream);
                return;''')

patch("L enters the view", r'''                if (cur_stream->video_st && !(cur_stream->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC)) {
                    ui_vflow = !ui_vflow;
                    ui_vflow_auto = 0;          /* L was pressed: it stays until L is pressed again */''', r'''                if (cur_stream->video_st && !(cur_stream->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC)) {
                    ui_vflow = !ui_vflow;
                    ui_vflow_auto = 0;          /* L was pressed: it stays until L is pressed again (Esc also closes it) */
                    ui_tv_seen = 0;             /* v37: the tiled view starts from the playing video */''')

# ---------------------------------------------------------------- miniplayer: memory, smooth growth
patch("full screen from the miniplayer", r'''static void toggle_full_screen(VideoState *is)
{
    ui_pip_end();                               /* the miniplayer ends before full screen */
    is_full_screen = !is_full_screen;''', r'''static int ui_pip_grow(VideoState *is);
static void ui_pip_left_fs(void);

static void toggle_full_screen(VideoState *is)
{
    if (ui_grow_on)
        return;                                 /* the miniplayer is already growing */
    if (ui_pip_grow(is))                        /* v37: the miniplayer grows into full screen, smoothly */
        return;
    ui_pip_end();                               /* the miniplayer ends before full screen */
    is_full_screen = !is_full_screen;''')

patch("double tap from the miniplayer", r'''static void ui_fs_cycle(VideoState *is)
{
    ui_pip_end();
    ui_fs_toggle_at = av_gettime_relative();''', r'''static void ui_fs_cycle(VideoState *is)
{
    if (ui_grow_on)
        return;
    if (ui_pip_grow(is))                        /* v37: the miniplayer grows into full screen, smoothly */
        return;
    ui_pip_end();
    ui_fs_toggle_at = av_gettime_relative();''')

patch("pip end saves", r'''    ui_pip = 0;
    ui_on_top = ui_pip_was_top;                 /* on top again only if it was before */
    SDL_SetWindowAlwaysOnTop(window, ui_pip_was_top ? SDL_TRUE : SDL_FALSE);''', r'''    ui_pip_save();                              /* v37: where it was left is where it opens next time */
    ui_pip = 0;
    ui_on_top = ui_pip_was_top;                 /* on top again only if it was before */
    SDL_SetWindowAlwaysOnTop(window, ui_pip_was_top ? SDL_TRUE : SDL_FALSE);
    ui_wm_state("_NET_WM_STATE_STICKY", 0);     /* and on this workspace only again */''')

patch("pip helpers", r'''/* ----- picture in picture: the window as a small miniplayer on top, in a corner ----- */
static int ui_pip = 0, ui_pip_was_top = 0, ui_pip_was_max = 0;     /* (was_top, was_max: how the window was before the miniplayer) */
static int ui_pip_x, ui_pip_y, ui_pip_w, ui_pip_h, ui_pip_user, ui_pip_kw, ui_pip_kh;     /* the window as it was */
''', r'''/* A _NET_WM_STATE change for the window (X11 sessions): add = 1 sets it, 0 clears it. Used to clear "show on all workspaces". */
typedef struct {
    int type;
    unsigned long serial;
    int send_event;
    void *display;
    unsigned long window;
    unsigned long message_type;
    int format;
    long l[5];
} UiXCM2;

static void ui_wm_state(const char *name, int add)
{
    SDL_SysWMinfo info;
    static void *xlib = NULL;
    static unsigned long (*x_atom)(void *, const char *, int);
    static unsigned long (*x_root)(void *);
    static int (*x_send)(void *, unsigned long, int, long, void *);
    static int (*x_flush)(void *);
    union { UiXCM2 m; long pad[24]; } ev;

    SDL_VERSION(&info.version);
    if (!window || !SDL_GetWindowWMInfo(window, &info) || info.subsystem != SDL_SYSWM_X11)
        return;
    if (!xlib) {
        xlib = dlopen("libX11.so.6", RTLD_LAZY);
        if (xlib) {
            *(void **)&x_atom = dlsym(xlib, "XInternAtom");
            *(void **)&x_root = dlsym(xlib, "XDefaultRootWindow");
            *(void **)&x_send = dlsym(xlib, "XSendEvent");
            *(void **)&x_flush = dlsym(xlib, "XFlush");
        }
    }
    if (!x_atom || !x_root || !x_send || !x_flush)
        return;
    memset(&ev, 0, sizeof(ev));
    ev.m.type = 33;                             /* ClientMessage */
    ev.m.display = info.info.x11.display;
    ev.m.window = info.info.x11.window;
    ev.m.message_type = x_atom(info.info.x11.display, "_NET_WM_STATE", 0);
    ev.m.format = 32;
    ev.m.l[0] = add ? 1 : 0;                    /* _NET_WM_STATE_ADD / _NET_WM_STATE_REMOVE */
    ev.m.l[1] = (long)x_atom(info.info.x11.display, name, 0);
    ev.m.l[3] = 1;                              /* the source: a normal application */
    x_send(info.info.x11.display, x_root(info.info.x11.display), 0, (1L << 20) | (1L << 19), &ev);
    x_flush(info.info.x11.display);
}

/* ----- picture in picture: the window as a small miniplayer on top, in a corner ----- */
static int ui_pip = 0, ui_pip_was_top = 0, ui_pip_was_max = 0;     /* (was_top, was_max: how the window was before the miniplayer) */
static int ui_pip_x, ui_pip_y, ui_pip_w, ui_pip_h, ui_pip_user, ui_pip_kw, ui_pip_kh;     /* the window as it was */

/* Where the miniplayer was left (x, y and width) is kept in ~/.config/ffplay-custom/miniplayer.conf */
static void ui_pip_conf(char *out, size_t size)
{
    const char *home = getenv("HOME");

    snprintf(out, size, "%s/.config/ffplay-custom/miniplayer.conf", home ? home : "");
}

static void ui_pip_save(void)
{
    char path[1024];
    int x, y, w, h;
    FILE *f;

    if (!ui_pip || !window || ui_grow_on)
        return;
    SDL_GetWindowPosition(window, &x, &y);
    SDL_GetWindowSize(window, &w, &h);
    if (w < 200 || h < 100)
        return;
    ui_pip_conf(path, sizeof(path));
    f = fopen(path, "w");
    if (!f)
        return;
    fprintf(f, "%d %d %d\n", x, y, w);
    fclose(f);
}

static int ui_pip_load(int *x, int *y, int *w)
{
    char path[1024];
    FILE *f;
    int n;

    ui_pip_conf(path, sizeof(path));
    f = fopen(path, "r");
    if (!f)
        return 0;
    n = fscanf(f, "%d %d %d", x, y, w);
    fclose(f);
    return n == 3;
}

/* The miniplayer grows out of its place into the screen (eased, a few tens of steps), then the window goes full screen, which at
   that size changes nothing you can see. Its always on top and show on all workspaces are switched off. 1 = handled. */
#define UI_GROW_US 280000
static int ui_grow_x0, ui_grow_y0, ui_grow_w0, ui_grow_h0, ui_grow_x1, ui_grow_y1, ui_grow_w1, ui_grow_h1;
static int64_t ui_grow_t0 = 0, ui_grow_last = 0;
static int ui_pg_return = 0;                    /* 1 = full screen came from the miniplayer: leaving it goes back to the window before it */
static int64_t ui_pg_restore_at = 0;

static void ui_pip_left_fs(void)
{
    if (ui_pg_return) {
        ui_pg_return = 0;
        ui_pg_restore_at = av_gettime_relative() + 150000;      /* after the window manager has put its own size back */
    }
}

static int ui_pip_grow(VideoState *is)
{
    SDL_Rect db;
    int di;

    if (!ui_pip || !window || is_full_screen || ui_grow_on)
        return 0;
    di = SDL_GetWindowDisplayIndex(window);
    if (di < 0)
        di = 0;
    if (SDL_GetDisplayBounds(di, &db) != 0)
        return 0;                               /* no screen size: the plain way (the caller does it) */
    ui_pip_save();
    SDL_GetWindowPosition(window, &ui_grow_x0, &ui_grow_y0);
    SDL_GetWindowSize(window, &ui_grow_w0, &ui_grow_h0);
    ui_grow_x1 = db.x;
    ui_grow_y1 = db.y;
    ui_grow_w1 = db.w;
    ui_grow_h1 = db.h;
    ui_pip = 0;                                 /* it is no miniplayer any more: what the miniplayer switched on goes off */
    ui_on_top = ui_pip_was_top;
    SDL_SetWindowAlwaysOnTop(window, ui_pip_was_top ? SDL_TRUE : SDL_FALSE);
    ui_wm_state("_NET_WM_STATE_STICKY", 0);
    ui_user_sized = ui_pip_user;
    ui_keep_w = ui_pip_kw;
    ui_keep_h = ui_pip_kh;
    ui_grow_on = 1;
    ui_grow_t0 = av_gettime_relative();
    ui_grow_last = 0;
    ui_fs_toggle_at = ui_grow_t0;
    ui_prog_until = ui_grow_t0 + 2000000;
    if (is)
        is->force_refresh = 1;
    return 1;
}

static void ui_grow_tick(VideoState *is)
{
    int64_t now;
    double f, e;
    int x, y, w, h;

    now = av_gettime_relative();
    if (ui_pg_restore_at && now >= ui_pg_restore_at && window) {    /* out of full screen: the window as it was before the miniplayer */
        ui_pg_restore_at = 0;
        if (!is_full_screen && !ui_maxed) {
            SDL_SetWindowSize(window, ui_pip_w, ui_pip_h);
            SDL_SetWindowPosition(window, ui_pip_x, ui_pip_y);
            ui_prog_w = ui_pip_w;
            ui_prog_h = ui_pip_h;
            ui_fs_toggle_at = now;
            ui_prog_until = now + 2000000;
            if (is)
                is->force_refresh = 1;
        }
    }
    if (!ui_grow_on || !window)
        return;
    if (now - ui_grow_last < 7000)
        return;                                 /* about 140 steps a second at most */
    ui_grow_last = now;
    f = (now - ui_grow_t0) / (double)UI_GROW_US;
    if (f >= 1.0) {
        SDL_SetWindowPosition(window, ui_grow_x1, ui_grow_y1);
        SDL_SetWindowSize(window, ui_grow_w1, ui_grow_h1);
        ui_grow_on = 0;
        is_full_screen = 1;
        ui_fs_toggle_at = now;
        ui_prog_until = now + 2000000;
        SDL_SetWindowFullscreen(window, SDL_WINDOW_FULLSCREEN_DESKTOP);
        SDL_SetWindowSize(window, ui_pip_w, ui_pip_h);      /* where leaving full screen goes: the window as it was before the miniplayer */
        SDL_SetWindowPosition(window, ui_pip_x, ui_pip_y);
        ui_maxed = ui_pip_was_max;              /* a window that filled the screen fills it again */
        ui_pg_return = 1;
        if (is)
            is->force_refresh = 1;
        return;
    }
    e = f < 0.5 ? 4.0 * f * f * f : 1.0 - pow(-2.0 * f + 2.0, 3.0) / 2.0;      /* ease in and out */
    x = ui_grow_x0 + (int)((ui_grow_x1 - ui_grow_x0) * e);
    y = ui_grow_y0 + (int)((ui_grow_y1 - ui_grow_y0) * e);
    w = ui_grow_w0 + (int)((ui_grow_w1 - ui_grow_w0) * e);
    h = ui_grow_h0 + (int)((ui_grow_h1 - ui_grow_h0) * e);
    ui_prog_w = w;
    ui_prog_h = h;
    ui_prog_until = now + 1500000;
    SDL_SetWindowSize(window, w, h);
    SDL_SetWindowPosition(window, x, y);
    if (is)
        is->force_refresh = 1;
}
''')

patch("pip opens where it was left", r'''    w = av_clip(ub.w / 4, 360, 640);
    h = av_clip(w * ch / cw, 160, FFMAX(ub.h / 2, 160));
    SDL_SetWindowSize(window, w, h);
    SDL_SetWindowPosition(window, ub.x + ub.w - w - 24, ub.y + ub.h - h - 24);''', r'''    w = av_clip(ub.w / 4, 360, 640);
    h = av_clip(w * ch / cw, 160, FFMAX(ub.h / 2, 160));
    {                                           /* v37: the place and width it was left at, if that is still on a screen */
        int lx, ly, lw, k, nd = SDL_GetNumVideoDisplays(), ok = 0;
        SDL_Rect lb;

        px = ub.x + ub.w - w - 24;
        py = ub.y + ub.h - h - 24;
        if (ui_pip_load(&lx, &ly, &lw)) {
            for (k = 0; k < nd && !ok; k++) {
                if (SDL_GetDisplayUsableBounds(k, &lb) != 0)
                    continue;
                if (lx + lw / 2 >= lb.x && lx + lw / 2 < lb.x + lb.w && ly + 40 >= lb.y && ly + 40 < lb.y + lb.h) {
                    lw = av_clip(lw, 240, lb.w);
                    w = lw;
                    h = av_clip(w * ch / cw, 120, lb.h);
                    px = av_clip(lx, lb.x, lb.x + lb.w - w);
                    py = av_clip(ly, lb.y, lb.y + lb.h - h);
                    ok = 1;
                }
            }
        }
    }
    SDL_SetWindowSize(window, w, h);
    SDL_SetWindowPosition(window, px, py);''')

patch("pip locals", r'''static void ui_pip_toggle(VideoState *is)
{
    SDL_Rect ub;
    int di, cw = 16, ch = 9, w, h;''', r'''static void ui_pip_toggle(VideoState *is)
{
    SDL_Rect ub;
    int di, cw = 16, ch = 9, w, h, px, py;''')

patch("grow tick in the loop", r'''        UI_TIMED(ui_aspect_tick(is));
        UI_TIMED(ui_inbox_tick(is));''', r'''        UI_TIMED(ui_grow_tick(is));
        UI_TIMED(ui_aspect_tick(is));
        UI_TIMED(ui_inbox_tick(is));''')

# ---------------------------------------------------------------- the tiled queue view
TV = r'''/* ======================= v37: the tiled queue view =======================
   Flat tiles (no tilt), two rows (three in a tall window) where the lower row continues the upper one, and every row moves
   together. Type to search: sections In this queue / In Music / In Videos, the matching letters of the titles in the bar color. */
#define UI_TV_KEEP 60                           /* matches kept for each section */
#define UI_TV_HL 120                            /* bytes of a title that are matched */
#define UI_TV_SWIPE_MIN 1.2                     /* how far a two finger swipe up has to go to open the view */
#define UI_TV_UP_SIGN (-1.0)                    /* the sign of the wheel's y for a swipe up (turn it to 1.0 if it is the other way) */

typedef struct {
    char *path;
    int score;
    unsigned char hl[UI_TV_HL];
} UiTvHit;

typedef struct {
    UiTvHit *h;
    int n;
    double pos;                                 /* the column in the focus place, between two while it glides */
    int target;
    int64_t born;                               /* when its tiles last sprang in */
} UiTvSec;

typedef struct {
    SDL_Rect r;
    int sec, item;                              /* sec -1 = the queue itself (item = queue number), 0 to 2 = a section (item = match number) */
} UiTvHitRect;

static int ui_tv_audio = 0;                     /* 1 = the tiled view over a song (a video uses the queue view's own switch) */
static char ui_tv_q[96];                        /* what was typed */
static int ui_tv_searching = 0;                 /* the search box has been used (it shows a caret) */
static int ui_tv_focus = 0;                     /* browsing: the queue number in focus */
static double ui_tv_pos = 0.0, ui_tv_row = 0.0; /* browsing: the column and the row that glide to the focus */
static UiTvSec ui_tv_sec[3];
static int ui_tv_act = 0;                       /* searching: the section the keys move */
static int64_t ui_tv_t = 0, ui_tv_born = 0, ui_tv_seen = 0;
static UiTvHitRect ui_tvh[128];
static int ui_tvh_n = 0;
static double ui_tv_lift[64];
static int ui_tv_press = -1, ui_tv_pressec = -2, ui_tv_drag = 0, ui_tv_px = 0, ui_tv_py = 0;   /* the tile the mouse went down on */
static int ui_tv_secy[3][2];                    /* the top and bottom of each section (for the wheel) */
static const char * const ui_tv_title[3] = { "In this queue", "In Music", "In Videos" };

/* ---- the folders: Music and Videos are read once in a thread, the search goes over what it has found ---- */
typedef struct {
    char **p;
    int n, cap;
} UiTvLib;

static UiTvLib ui_tv_lib[2];
static SDL_mutex *ui_tv_mu = NULL;
static volatile int ui_tv_scan_state = 0;       /* 0 = not yet, 1 = reading, 2 = read */
static int64_t ui_tv_scan_at = 0;
static const char * const ui_tv_ext[2][16] = {
    { "mp3", "flac", "ogg", "oga", "opus", "m4a", "aac", "wav", "wma", "aiff", "aif", "ape", "mka", NULL },
    { "mp4", "mkv", "webm", "avi", "mov", "m4v", "wmv", "flv", "mpg", "mpeg", "ts", "m2ts", "3gp", "ogv", NULL }
};

static void ui_tv_lib_add(int kind, const char *path)
{
    UiTvLib *l = &ui_tv_lib[kind];
    char *c;

    SDL_LockMutex(ui_tv_mu);
    if (l->n >= l->cap) {
        int nc = l->cap ? l->cap * 2 : 1024;
        char **g = av_realloc_array(l->p, nc, sizeof(*g));

        if (!g) {
            SDL_UnlockMutex(ui_tv_mu);
            return;
        }
        l->p = g;
        l->cap = nc;
    }
    c = av_strdup(path);
    if (c)
        l->p[l->n++] = c;
    SDL_UnlockMutex(ui_tv_mu);
}

static void ui_tv_scan_dir(const char *dir, int kind, int depth, int *budget)
{
    DIR *d;
    struct dirent *e;
    char path[1024];
    struct stat st;

    if (depth > 6 || *budget <= 0)
        return;
    d = opendir(dir);
    if (!d)
        return;
    while ((e = readdir(d)) && *budget > 0) {
        const char *dot;
        int k;

        if (e->d_name[0] == '.')
            continue;
        snprintf(path, sizeof(path), "%s/%s", dir, e->d_name);
        if (stat(path, &st) != 0)
            continue;
        if (S_ISDIR(st.st_mode)) {
            ui_tv_scan_dir(path, kind, depth + 1, budget);
        } else if (S_ISREG(st.st_mode) && (dot = strrchr(e->d_name, '.')) && dot[1]) {
            for (k = 0; ui_tv_ext[kind][k]; k++)
                if (!av_strcasecmp(dot + 1, ui_tv_ext[kind][k])) {
                    ui_tv_lib_add(kind, path);
                    (*budget)--;
                    break;
                }
        }
    }
    closedir(d);
}

/* The Music or Videos folder: the one in ~/.config/user-dirs.dirs, or ~/Music and ~/Videos */
static void ui_tv_userdir(const char *key, const char *def, char *out, size_t size)
{
    const char *home = getenv("HOME");
    char path[1024], line[1024];
    FILE *f;
    size_t kl = strlen(key);

    snprintf(out, size, "%s/%s", home ? home : "", def);
    if (!home)
        return;
    snprintf(path, sizeof(path), "%s/.config/user-dirs.dirs", home);
    f = fopen(path, "r");
    if (!f)
        return;
    while (fgets(line, sizeof(line), f)) {
        char *p = line, *q;

        if (strncmp(p, key, kl) || p[kl] != '=')
            continue;
        p += kl + 1;
        if (*p == '"')
            p++;
        q = strchr(p, '"');
        if (!q)
            q = strchr(p, '\n');
        if (q)
            *q = 0;
        if (!strncmp(p, "$HOME", 5))
            snprintf(out, size, "%s%s", home, p + 5);
        else if (*p == '/')
            snprintf(out, size, "%s", p);
        break;
    }
    fclose(f);
}

static int ui_tv_scan_thread(void *arg)
{
    char dir[1024];
    int budget = 40000, k;

    for (k = 0; k < 2; k++) {
        const char *own = k ? cfg_video_dir : cfg_music_dir;        /* music_folder / video_folder in settings.conf, if set */

        if (own[0])
            snprintf(dir, sizeof(dir), "%s", own);
        else
            ui_tv_userdir(k ? "XDG_VIDEOS_DIR" : "XDG_MUSIC_DIR", k ? "Videos" : "Music", dir, sizeof(dir));
        ui_tv_scan_dir(dir, k, 0, &budget);
    }
    ui_tv_scan_state = 2;
    return 0;
}

static void ui_tv_scan_start(void)
{
    int64_t now = av_gettime_relative();
    SDL_Thread *th;
    int k, i;

    if (!ui_tv_mu)
        ui_tv_mu = SDL_CreateMutex();
    if (!ui_tv_mu || ui_tv_scan_state == 1 || (ui_tv_scan_state == 2 && now - ui_tv_scan_at < 60000000))
        return;                                 /* it is being read, or it was read less than a minute ago */
    SDL_LockMutex(ui_tv_mu);
    for (k = 0; k < 2; k++) {
        for (i = 0; i < ui_tv_lib[k].n; i++)
            av_free(ui_tv_lib[k].p[i]);
        ui_tv_lib[k].n = 0;
    }
    SDL_UnlockMutex(ui_tv_mu);
    ui_tv_scan_state = 1;
    ui_tv_scan_at = now;
    th = SDL_CreateThread(ui_tv_scan_thread, "library", NULL);
    if (th)
        SDL_DetachThread(th);
    else
        ui_tv_scan_state = 0;
}

/* ---- names and matching ---- */
static void ui_tv_name(const char *s, char *out, size_t size)
{
    const char *slash = strrchr(s, '/');
    char *dot, *open;
    size_t len;

    snprintf(out, size, "%s", slash ? slash + 1 : s);
    dot = strrchr(out, '.');
    if (dot && dot != out && strlen(dot) <= 5)
        *dot = 0;
    for (;;) {
        len = strlen(out);
        while (len > 0 && out[len - 1] == ' ')
            out[--len] = 0;
        open = strrchr(out, '(');
        if (!open || open == out || len == 0 || out[len - 1] != ')' || !ui_q_is_codec_info(open + 1))
            break;
        *open = 0;
    }
}

static int ui_tv_lc(int c)
{
    return (c >= 'A' && c <= 'Z') ? c + 32 : c;
}

/* How well a title fits what was typed. 0 = it does not. hl[] gets 1 for every byte of the title that matches (whole UTF-8
   letters). Every word typed is looked for as it is (best where a word starts), else its letters in order. */
static int ui_tv_match(const char *name, const char *query, unsigned char *hl)
{
    char ln[UI_TV_HL];
    int n = (int)strlen(name), score = 0, matched = 0, total = 0, words = 0, i;
    const char *q = query;

    if (n > UI_TV_HL - 1)
        n = UI_TV_HL - 1;
    for (i = 0; i < n; i++)
        ln[i] = (char)ui_tv_lc((unsigned char)name[i]);
    memset(hl, 0, UI_TV_HL);
    while (*q) {
        char w[96];
        int m = 0, best = -1, bests = -1, p, k, cur;

        while (*q == ' ')
            q++;
        while (*q && *q != ' ' && m < (int)sizeof(w) - 1)
            w[m++] = (char)ui_tv_lc((unsigned char)*q++);
        w[m] = 0;
        if (!m)
            break;
        words++;
        total += m;
        for (p = 0; p + m <= n; p++) {          /* the word as it is: the best place for it */
            int s;

            if (memcmp(ln + p, w, m))
                continue;
            s = 10 + (p == 0 ? 6 : 0) + ((p > 0 && (ln[p - 1] == ' ' || ln[p - 1] == '-' || ln[p - 1] == '_' || ln[p - 1] == '.')) ? 5 : 0);
            if (s > bests) {
                bests = s;
                best = p;
            }
        }
        if (best >= 0) {
            for (k = 0; k < m; k++)
                hl[best + k] = 1;
            matched += m;
            score += m * 12 + bests * 3;
            continue;
        }
        cur = 0;                                /* else its letters in order */
        for (k = 0; k < m; k++) {
            for (p = cur; p < n; p++) {
                if (((unsigned char)ln[p] & 0xC0) == 0x80 || ln[p] != w[k])
                    continue;
                break;
            }
            if (p >= n)
                continue;                       /* this letter is not there: the word only matches in part */
            score += 4 - FFMIN(p - cur, 3);
            matched++;
            hl[p] = 1;
            p++;
            while (p < n && ((unsigned char)ln[p] & 0xC0) == 0x80)
                hl[p++] = 1;
            cur = p;
        }
    }
    if (!words || matched == 0)
        return 0;
    if (total <= 2 ? matched < total : matched * 100 < 70 * total)
        return 0;
    score -= (total - matched) * 6;
    score -= n / 10;
    return score > 0 ? score : 1;
}

static void ui_tv_sec_free(UiTvSec *sec)
{
    int i;

    for (i = 0; i < sec->n; i++)
        av_freep(&sec->h[i].path);
    sec->n = 0;
}

static void ui_tv_offer(UiTvSec *sec, const char *path, int score, const unsigned char *hl)
{
    UiTvHit *h;
    int i, mi = 0;

    if (!sec->h)
        sec->h = av_calloc(UI_TV_KEEP, sizeof(UiTvHit));
    if (!sec->h)
        return;
    if (sec->n < UI_TV_KEEP) {
        h = &sec->h[sec->n];
    } else {
        for (i = 1; i < sec->n; i++)
            if (sec->h[i].score < sec->h[mi].score)
                mi = i;
        if (sec->h[mi].score >= score)
            return;
        h = &sec->h[mi];
        av_freep(&h->path);
    }
    h->path = av_strdup(path);
    if (!h->path)
        return;
    h->score = score;
    memcpy(h->hl, hl, UI_TV_HL);
    if (h == &sec->h[sec->n])
        sec->n++;
    else if (!h->path)
        h->score = 0;
}

static int ui_tv_cmp(const void *a, const void *b)
{
    const UiTvHit *x = a, *y = b;

    return y->score - x->score;
}

static void ui_tv_search(void)
{
    int64_t now = av_gettime_relative();
    char nm[300];
    unsigned char hl[UI_TV_HL];
    int s, i, k, sc;

    for (s = 0; s < 3; s++) {
        ui_tv_sec_free(&ui_tv_sec[s]);
        ui_tv_sec[s].pos = 0.0;                 /* the best match is the one in focus, the others come after it */
        ui_tv_sec[s].target = 0;
        ui_tv_sec[s].born = now;                /* and the tiles spring in */
    }
    ui_tv_act = 0;
    if (!ui_tv_q[0])
        return;
    ui_tv_scan_start();
    for (i = 0; i < q_count; i++) {
        ui_tv_name(q_items[i], nm, sizeof(nm));
        sc = ui_tv_match(nm, ui_tv_q, hl);
        if (sc > 0)
            ui_tv_offer(&ui_tv_sec[0], q_items[i], sc, hl);
    }
    if (ui_tv_mu) {
        SDL_LockMutex(ui_tv_mu);
        for (k = 0; k < 2; k++)
            for (i = 0; i < ui_tv_lib[k].n; i++) {
                ui_tv_name(ui_tv_lib[k].p[i], nm, sizeof(nm));
                sc = ui_tv_match(nm, ui_tv_q, hl);
                if (sc > 0)
                    ui_tv_offer(&ui_tv_sec[1 + k], ui_tv_lib[k].p[i], sc, hl);
            }
        SDL_UnlockMutex(ui_tv_mu);
    }
    for (s = 0; s < 3; s++)
        if (ui_tv_sec[s].n > 1)
            qsort(ui_tv_sec[s].h, ui_tv_sec[s].n, sizeof(UiTvHit), ui_tv_cmp);
    for (s = 2; s >= 0; s--)
        if (ui_tv_sec[s].n > 0)
            ui_tv_act = s;                      /* the keys start in the first section that has something */
}

/* ---- when is the view there, and does it own the keys? ---- */
static int ui_tv_on(VideoState *is)
{
    if (!is || q_count <= 0 || q_pos < 0 || q_pos >= q_count)
        return 0;
    if (ui_tv_audio && (!ui_flow_on(is) || ui_flow_video(is)))
        ui_tv_audio = 0;
    return ui_flow_video(is) || ui_tv_audio;
}

static int ui_tv_cap(VideoState *is)
{
    if (!ui_tv_on(is))
        return 0;
    if (ui_flow_video(is))
        return ui_vflow && !ui_vflow_auto;      /* a pause that opened the view by itself leaves the keys alone */
    return 1;
}

static void ui_tv_dims(VideoState *is, int *R, int *L)
{
    int n = q_count;

    *R = n <= 3 ? 1 : (is->height >= 720 ? 3 : 2);
    *L = FFMAX((n + *R - 1) / *R, 1);
}

static void ui_tv_reset(VideoState *is, int64_t now)
{
    int R, L, s;

    ui_tv_q[0] = 0;
    ui_tv_searching = 0;
    for (s = 0; s < 3; s++)
        ui_tv_sec_free(&ui_tv_sec[s]);
    ui_tv_focus = av_clip(q_pos, 0, q_count - 1);
    ui_tv_dims(is, &R, &L);
    ui_tv_pos = ui_tv_focus % L;
    ui_tv_row = ui_tv_focus / L;
    ui_tv_born = now;
    ui_tv_press = -1;
    ui_tv_drag = 0;
}

static void ui_tv_enter(VideoState *is)
{
    if (!is || q_count <= 0 || q_pos < 0 || ui_tv_cap(is))
        return;
    if (is->video_st && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC)) {
        if (!ui_vflow) {                        /* the same start as key L */
            ui_vflow = 1;
            ui_vflow_t = 0;
            ui_bd_key[0] = 0;
            ui_flow_pos = ui_flow_target = q_pos;
            ui_flow_last_q = q_pos;
            ui_flow_touch = 0;
        }
        ui_vflow_auto = 0;
    } else if (is->audio_st) {
        ui_tv_audio = 1;
    }
    ui_tv_seen = 0;                             /* the view starts from the playing item */
    SDL_StartTextInput();
    is->force_refresh = 1;
}

static void ui_tv_exit(VideoState *is)
{
    int s;

    ui_tv_q[0] = 0;
    ui_tv_searching = 0;
    for (s = 0; s < 3; s++)
        ui_tv_sec_free(&ui_tv_sec[s]);
    if (ui_flow_video(is) && ui_vflow) {
        ui_vflow_auto = 0;
        ui_vflow_set(is, 0);                    /* the video grows back */
    }
    ui_tv_audio = 0;
    is->force_refresh = 1;
}

/* Play a file from the view: one that is in the queue is played from there, one from a folder is added first */
static void ui_tv_play(VideoState *is, const char *path)
{
    int i, idx = -1;

    if (!path)
        return;
    for (i = 0; i < q_count && idx < 0; i++)
        if (!strcmp(q_items[i], path))
            idx = i;
    if (idx < 0) {                              /* the same file under another name (a relative path in the queue, a full one here) */
        char *rp = realpath(path, NULL);

        for (i = 0; rp && i < q_count && idx < 0; i++) {
            char *rq = realpath(q_items[i], NULL);

            if (rq && !strcmp(rq, rp))
                idx = i;
            free(rq);
        }
        free(rp);
    }
    if (idx >= 0 && idx == q_pos) {             /* the one that plays: back to it */
        if (ui_flow_video(is))
            ui_tile_open(is);
        else if (is->paused)
            toggle_pause(is);
        ui_tv_exit(is);
        return;
    }
    if (idx < 0) {
        queue_add(path);
        idx = q_count - 1;
    }
    ui_tv_exit(is);
    q_forced = idx;
    ui_end_current(is);
}

static const char *ui_tv_sel_path(void)
{
    UiTvSec *sec = &ui_tv_sec[ui_tv_act];

    return (sec->n > 0 && sec->target >= 0 && sec->target < sec->n) ? sec->h[sec->target].path : NULL;
}

static void ui_tv_step(VideoState *is, int dcol, int drow)
{
    ui_tv_moving = 1;
    if (ui_tv_q[0]) {                           /* searching: along a section, or to the next section that has something */
        UiTvSec *sec = &ui_tv_sec[ui_tv_act];
        int s;

        if (dcol && sec->n > 0)
            sec->target = av_clip(sec->target + dcol, 0, sec->n - 1);
        for (s = ui_tv_act + drow; drow && s >= 0 && s < 3; s += drow)
            if (ui_tv_sec[s].n > 0) {
                ui_tv_act = s;
                break;
            }
    } else {                                    /* browsing: the row ends where it ends, up and down keep the column */
        int R, L, row, col;

        ui_tv_dims(is, &R, &L);
        row = ui_tv_focus / L;
        col = ui_tv_focus % L;
        if (dcol)
            col = av_clip(col + dcol, 0, L - 1);
        if (drow)
            row = av_clip(row + drow, 0, R - 1);
        ui_tv_focus = av_clip(row * L + col, 0, q_count - 1);
    }
    is->force_refresh = 1;
}

static int ui_tv_key(VideoState *is, SDL_Event *ev)
{
    SDL_Keycode k = ev->key.keysym.sym;
    const char *p;

    if (!ui_tv_cap(is) || ui_menu_open || ui_prefs_open || ui_q_open || ui_info_open || ui_open_open || ui_ctx_open)
        return 0;
    if ((ev->key.keysym.mod & (KMOD_CTRL | KMOD_ALT | KMOD_GUI)) || (k >= SDLK_F1 && k <= SDLK_F12))
        return 0;
    ui_wake();
    switch (k) {
    case SDLK_ESCAPE:                           /* Esc closes the search, Esc again closes the view */
        if (ui_tv_q[0] || ui_tv_searching) {
            ui_tv_q[0] = 0;
            ui_tv_searching = 0;
            ui_tv_search();
            ui_tv_moving = 1;
        } else {
            ui_tv_exit(is);
        }
        return 1;
    case SDLK_TAB:
        ui_tv_exit(is);
        return 1;
    case SDLK_RETURN:
    case SDLK_KP_ENTER:
        p = ui_tv_q[0] ? ui_tv_sel_path() : q_items[av_clip(ui_tv_focus, 0, q_count - 1)];
        ui_tv_play(is, p);
        return 1;
    case SDLK_BACKSPACE: {
        size_t n = strlen(ui_tv_q);

        if (n > 0) {
            do
                n--;
            while (n > 0 && ((unsigned char)ui_tv_q[n] & 0xC0) == 0x80);
            ui_tv_q[n] = 0;
            ui_tv_search();
            ui_tv_moving = 1;
        }
        return 1;
    }
    case SDLK_LEFT:
        ui_tv_step(is, -1, 0);
        return 1;
    case SDLK_RIGHT:
        ui_tv_step(is, 1, 0);
        return 1;
    case SDLK_UP:
        ui_tv_step(is, 0, -1);
        return 1;
    case SDLK_DOWN:
        ui_tv_step(is, 0, 1);
        return 1;
    case SDLK_HOME:
        ui_tv_step(is, -100000, 0);
        return 1;
    case SDLK_END:
        ui_tv_step(is, 100000, 0);
        return 1;
    case SDLK_SPACE:
        if (!ui_tv_q[0])
            toggle_pause(is);                   /* nothing typed: Space still pauses */
        return 1;
    default:
        return 1;                               /* the letters belong to the search (they arrive as text) */
    }
}

static int ui_tv_text(VideoState *is, const char *t)
{
    size_t n = strlen(ui_tv_q), m = strlen(t);

    if (!ui_tv_cap(is) || ui_menu_open || ui_prefs_open || ui_q_open || ui_info_open || ui_open_open || ui_ctx_open)
        return 0;
    if (!n && t[0] == ' ')
        return 1;
    if (n + m >= sizeof(ui_tv_q) - 1)
        return 1;
    memcpy(ui_tv_q + n, t, m + 1);
    ui_tv_searching = 1;
    ui_tv_search();
    ui_tv_moving = 1;
    return 1;
}

/* Swipes: sideways moves through the rows, up and down (two fingers) between rows or sections. A two finger swipe up on a touchpad
   opens the view; a mouse wheel (whole notches) keeps its job, the volume. */
static int ui_tv_wheel(VideoState *is, SDL_Event *ev)
{
    static double accx = 0.0, accy = 0.0, accs = 0.0;
    static int64_t last = 0, lasty = 0, block = 0;
    static int lock = 0, frac = 0;
    int64_t now = av_gettime_relative();
    double ax, ay;

    if (!is || ui_menu_open || ui_prefs_open || !is->width)
        return 0;
#if SDL_VERSION_ATLEAST(2, 0, 18)
    ax = ev->wheel.preciseX;
    ay = ev->wheel.preciseY;
#else
    ax = ev->wheel.x;
    ay = ev->wheel.y;
#endif
    if (ev->wheel.direction == SDL_MOUSEWHEEL_FLIPPED) {
        ax = -ax;
        ay = -ay;
    }
    if (ui_tv_cap(is)) {
        if (FFABS(ax) > FFABS(ay)) {            /* sideways: the rows move */
            int steps;

            if (now - last > 300000 || ax * accx < 0.0)
                accx = 0.0;
            last = now;
            accx += ax;
            steps = (int)accx;
            if (steps) {
                accx -= steps;
                ui_tv_step(is, steps, 0);
            }
        } else {                                /* up or down: one row, or section, for each swipe */
            if (now - lasty > 250000) {
                accy = 0.0;
                lock = 0;
            }
            lasty = now;
            accy += ay;
            if (!lock && FFABS(accy) >= 2.0) {
                lock = 1;
                ui_tv_step(is, 0, accy * UI_TV_UP_SIGN > 0 ? 1 : -1);
            }
        }
        return 1;
    }
    if (FFABS(ay) <= FFABS(ax) || ay == 0.0)
        return 0;
    if (now - lasty > 250000) {
        accs = 0.0;
        frac = 0;
    }
    lasty = now;
    if (FFABS(ay - floor(ay + 0.5)) > 0.01)
        frac = 1;                               /* fractions: a touchpad, not a wheel */
    if (!frac || ay * UI_TV_UP_SIGN <= 0.0)
        return 0;
    accs += FFABS(ay);
    if (now >= block && accs >= UI_TV_SWIPE_MIN && !ui_tv_on(is)) {
        ui_tv_enter(is);
        block = now + 700000;                   /* the end of the swipe keeps coming for a moment */
        accs = 0.0;
    }
    return 1;                                   /* a swipe up does not change the volume */
}

/* ---- drawing ---- */
static void ui_tv_theme(int *r, int *g, int *b)
{
    *r = FFMIN(255, cfg_bar_r + 55);
    *g = FFMIN(255, cfg_bar_g + 55);
    *b = FFMIN(255, cfg_bar_b + 55);
}

/* A soft glow in the bar color behind a tile: a fan that is strongest in the middle and nothing at the rim */
static void ui_tv_glow(double cx, double cy, double rx, double ry, int a)
{
    enum { N = 36 };
    SDL_Vertex v[N + 2];
    int idx[N * 3], k, r, g, b;

    if (a <= 2)
        return;
    r = cfg_bar_r;
    g = cfg_bar_g;
    b = cfg_bar_b;
    v[0].position.x = (float)cx;
    v[0].position.y = (float)cy;
    v[0].color.r = (Uint8)r;
    v[0].color.g = (Uint8)g;
    v[0].color.b = (Uint8)b;
    v[0].color.a = (Uint8)av_clip(a, 0, 255);
    v[0].tex_coord.x = v[0].tex_coord.y = 0.0f;
    for (k = 0; k <= N; k++) {
        double an = k * 6.28318530718 / N;

        v[k + 1].position.x = (float)(cx + cos(an) * rx);
        v[k + 1].position.y = (float)(cy + sin(an) * ry);
        v[k + 1].color = v[0].color;
        v[k + 1].color.a = 0;
        v[k + 1].tex_coord.x = v[k + 1].tex_coord.y = 0.0f;
    }
    for (k = 0; k < N; k++) {
        idx[k * 3] = 0;
        idx[k * 3 + 1] = k + 1;
        idx[k * 3 + 2] = k + 2;
    }
    SDL_RenderGeometry(renderer, NULL, v, N + 2, idx, N * 3);
}

/* A title with the matched letters in the bar color. It is cut with "..." to fit max_w (the letters that are kept keep their color). */
static void ui_tv_label(const char *name, const unsigned char *hl, int px, int cx, int cy, int max_w, int a)
{
    char s[320], pre[320];
    unsigned char h[320];
    int n = (int)strlen(name), lo, hi, i, j, x0, tr, tg, tb;

    if (n > 300)
        n = 300;
    memcpy(s, name, n);
    s[n] = 0;
    memset(h, 0, sizeof(h));
    if (hl)
        memcpy(h, hl, FFMIN(n, UI_TV_HL));
    if (ui_text_width(s, px) > max_w) {         /* binary search for how much fits with the dots */
        lo = 0;
        hi = n;
        while (lo < hi) {
            int mid = (lo + hi + 1) / 2, keep = mid;

            while (keep > 0 && ((unsigned char)s[keep] & 0xC0) == 0x80)
                keep--;
            memcpy(pre, s, keep);
            memcpy(pre + keep, "...", 4);
            if (ui_text_width(pre, px) <= max_w)
                lo = mid;
            else
                hi = mid - 1;
        }
        while (lo > 0 && ((unsigned char)s[lo] & 0xC0) == 0x80)
            lo--;
        memcpy(s + lo, "...", 4);
        for (i = lo; i < lo + 3; i++)
            h[i] = 0;
        n = lo + 3;
    }
    ui_tv_theme(&tr, &tg, &tb);
    x0 = cx - ui_text_width(s, px) / 2;
    for (i = 0; i < n; i = j) {
        char seg[320];
        int xo = 0;

        for (j = i; j < n && h[j] == h[i]; j++)
            ;
        memcpy(seg, s + i, j - i);
        seg[j - i] = 0;
        if (i > 0) {
            memcpy(pre, s, i);
            pre[i] = 0;
            xo = ui_text_width(pre, px);
        }
        if (h[i])
            ui_label(x0 + xo, cy, seg, px, tr, tg, tb, a);
        else
            ui_label(x0 + xo, cy, seg, px, 255, 255, 255, a * 70 / 100);
    }
}

/* The tile of a file (a picture of its own shape, or the file icon), flat with rounded corners and a soft shadow */
static void ui_tv_tile(const char *path, const SDL_Rect *t, int al, int md)
{
    SDL_Texture *tex;
    SDL_Rect sh;
    int cw = 0, ch = 0, k;

    tex = ui_cov_native(path, &cw, &ch);
    if (!tex)
        tex = ui_cov_get(path, &cw, &ch);
    if (tex) {
        for (k = ui_shadows_on ? 3 : 0; k >= 1; k--) {
            sh.x = t->x - k * 4;
            sh.y = t->y - k * 4 + 7;
            sh.w = t->w + k * 8;
            sh.h = t->h + k * 8;
            ui_flow_quad(tex, &sh, al * 16 / 255, 0, 0.0);
        }
    } else {
        tex = ui_flow_icon();
    }
    if (tex)
        ui_flow_quad_round(tex, t, al, md, 0.0, FFMIN(t->w, t->h) / 11);
}

static int ui_tv_is_playing(const char *path)
{
    return path && q_pos >= 0 && q_pos < q_count && !strcmp(path, q_items[q_pos]);
}

typedef struct {
    int sec;                                    /* -1 = the queue itself, 0 to 2 = the matches of a section */
    int first, count;                           /* the queue numbers of the row (sec -1), or 0 and the number of matches */
    double pos;                                 /* the column in the focus place */
    int cx, cy, sw, sh;                         /* where the focus tile sits, and the size of the box a tile is fitted into */
    double rowd;                                /* how far this row is from the row in focus (0 = in focus) */
    int64_t born;
    int sm;                                     /* a small window: smaller titles */
} UiTvRow;

typedef struct {
    double d;
    int c;
} UiTvOrd;

static int ui_tv_ord_cmp(const void *a, const void *b)
{
    double x = ((const UiTvOrd *)a)->d, y = ((const UiTvOrd *)b)->d;

    return x < y ? 1 : x > y ? -1 : 0;
}

static const char *ui_tv_row_path(const UiTvRow *R, int c)
{
    if (R->sec < 0)
        return q_items[R->first + c];
    return ui_tv_sec[R->sec].h[c].path;
}

static void ui_tv_row_draw(VideoState *is, const UiTvRow *R, int hov_sec, int hov_item, double dt, int64_t now, double ep)
{
    UiTvOrd ord[48];
    int no = 0, k0, k1, c, o, W = is->width, vm = ui_flow_vmode, K;
    double pitch = R->sw * 1.08;

    K = (int)(W / (2.0 * pitch)) + 3;
    k0 = FFMAX((int)floor(R->pos) - K, 0);
    k1 = FFMIN((int)ceil(R->pos) + K, R->count - 1);
    for (c = k0; c <= k1 && no < 48; c++) {
        double dc = c - R->pos, d = sqrt(dc * dc + (1.15 * R->rowd) * (1.15 * R->rowd));

        ord[no].d = d;
        ord[no].c = c;
        no++;
    }
    qsort(ord, no, sizeof(ord[0]), ui_tv_ord_cmp);              /* the far ones first, the one in focus on top */
    for (o = 0; o < no; o++) {
        int c = ord[o].c, item = R->sec < 0 ? R->first + c : c, play, nw, nh, al, md, tx, ty, ti;
        double d = ord[o].d, dc = c - R->pos, sc, x, en, ease, x1, lf, goal, asp, bw, bh;
        const char *path = ui_tv_row_path(R, c);
        const unsigned char *hl = R->sec >= 0 ? ui_tv_sec[R->sec].h[c].hl : NULL;
        SDL_Rect tile;
        char name[320];
        int px;

        if (!path)
            continue;
        play = ui_tv_is_playing(path);
        sc = 1.0 - 0.26 * (d < 1.0 ? d * d * (3.0 - 2.0 * d) : 1.0) - 0.035 * FFMIN(FFMAX(d - 1.0, 0.0), 4.0);
        bw = R->sw * sc;
        bh = R->sh * sc;
        asp = (play && vm && ui_live_ok && ui_live_rect.h > 0) ? (double)ui_live_rect.w / ui_live_rect.h : ui_cov_aspect(path);
        if (asp <= 0.0) {
            nw = nh = (int)FFMIN(bw, bh);       /* a cover or a file icon is square */
        } else if (bw / bh > asp) {
            nh = (int)bh;
            nw = (int)(bh * asp);
        } else {
            nw = (int)bw;
            nh = (int)(bw / asp);
        }
        x = R->cx + dc * pitch + (dc < 0 ? -1.0 : 1.0) * FFMIN(fabs(dc), 1.0) * pitch * 0.12;
        if (vm && R->sec < 0 && !play)          /* over a video: the other tiles slide out from behind the one that plays */
            x = R->cx + (x - R->cx) * (0.55 + 0.45 * ep);
        en = (R->sec < 0 && vm) ? 1.0 : av_clipd(((now - R->born) / 1000000.0 - fabs(dc) * 0.05) / 0.45, 0.0, 1.0);
        if (en < 1.0)
            ui_tv_moving = 1;
        x1 = en - 1.0;
        ease = 1.0 + 2.70158 * x1 * x1 * x1 + 1.70158 * x1 * x1;                 /* eases out and overshoots a little */
        x += (1.0 - ease) * (dc < 0 ? -1.0 : 1.0) * W * 0.12;
        al = (int)(255 * av_clipd(1.05 - 0.26 * d, 0.18, 1.0) * av_clipd(1.0 - 0.5 * R->rowd, 0.55, 1.0));
        md = (int)(255 * av_clipd(1.0 - 0.22 * FFMIN(d, 2.2), 0.45, 1.0));
        if (vm && R->sec < 0 && !play)
            al = (int)(al * ep);                /* the other tiles fade in while the video shrinks */
        al = (int)(al * en);
        ti = (R->sec < 0 ? item : c + 20 * (R->sec + 1)) & 63;
        goal = (hov_sec == R->sec && hov_item == item) ? 1.0 : 0.0;
        lf = ui_tv_lift[ti];
        lf += (goal - lf) * (1.0 - exp(-dt * 14.0));
        if (fabs(goal - lf) < 0.004)
            lf = goal;
        else
            ui_tv_moving = 1;
        ui_tv_lift[ti] = lf;
        nw += (int)(nw * 0.05 * lf);
        nh += (int)(nh * 0.05 * lf);
        tile.w = nw;
        tile.h = nh;
        tile.x = (int)x - nw / 2;
        tile.y = R->cy + (int)((1.0 - ease) * 36.0) - nh / 2 - (int)(6 * lf);
        md = FFMIN(255, md + (int)(40 * lf));
        if (tile.x + tile.w < -20 || tile.x > W + 20)
            continue;
        if (ui_tv_drag && ui_tv_press == item && ui_tv_pressec == R->sec)
            al = al / 3;                        /* the one that is being dragged leaves a faint place behind */
        if (d < 0.6)                            /* a soft glow in the bar color behind the tile in focus, like the reference */
            ui_tv_glow(tile.x + tile.w / 2.0, tile.y + tile.h / 2.0, tile.w * 0.95, tile.h * 0.95, (int)(120 * (1.0 - d / 0.6) * (al / 255.0)));
        if (play && vm && ui_live_ok) {         /* the video that plays now keeps playing in its tile */
            SDL_Rect lr = tile;

            if (ep < 1.0) {                     /* on its way between the full screen and its tile */
                lr.x = ui_live_rect.x + (int)((tile.x - ui_live_rect.x) * ep);
                lr.y = ui_live_rect.y + (int)((tile.y - ui_live_rect.y) * ep);
                lr.w = ui_live_rect.w + (int)((tile.w - ui_live_rect.w) * ep);
                lr.h = ui_live_rect.h + (int)((tile.h - ui_live_rect.h) * ep);
            }
            ui_flow_quad_round(ui_live_tex, &lr, al, md, 0.0, (int)(FFMIN(lr.w, lr.h) / 11.0 * ep));
        } else {
            ui_tv_tile(path, &tile, al, md);
        }
        ui_tv_name(path, name, sizeof(name));
        px = d < 0.6 ? (R->sm ? 16 : 19) : (R->sm ? 12 : 14);
        tx = tile.x + tile.w / 2;
        ty = tile.y + tile.h + (d < 0.6 ? 20 : 16);
        if (play) {                             /* the dot of the item that plays, before its title */
            SDL_Rect pdot;
            int tw = ui_text_width(name, px);

            pdot.w = 7;
            pdot.h = 7;
            pdot.x = tx - FFMIN(tw, (int)(pitch * 1.4)) / 2 - 14;
            pdot.y = ty - 3;
            SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                                   av_clip(cfg_bar_b + 40, 0, 255), (int)(235 * al / 255.0));
            ui_pill(&pdot);
        }
        ui_tv_label(name, hl, px, tx, ty, (int)(pitch * (d < 0.6 ? 1.9 : 1.05)), (int)(al * (d < 0.6 ? 1.0 : 0.75)));
        if (ui_tvh_n < 128) {
            ui_tvh[ui_tvh_n].r.x = tile.x;
            ui_tvh[ui_tvh_n].r.y = tile.y;
            ui_tvh[ui_tvh_n].r.w = tile.w;
            ui_tvh[ui_tvh_n].r.h = tile.h + 30;
            ui_tvh[ui_tvh_n].sec = R->sec;
            ui_tvh[ui_tvh_n].item = item;
            ui_tvh_n++;
        }
    }
}

static int ui_tv_hit_at(int x, int y, int *sec, int *item)
{
    int i;

    for (i = ui_tvh_n - 1; i >= 0; i--) {       /* the last one drawn is the nearest */
        const SDL_Rect *r = &ui_tvh[i].r;

        if (x >= r->x && x < r->x + r->w && y >= r->y && y < r->y + r->h) {
            *sec = ui_tvh[i].sec;
            *item = ui_tvh[i].item;
            return 1;
        }
    }
    return 0;
}

static void ui_tv_draw(VideoState *is)
{
    int64_t now = av_gettime_relative();
    int W = is->width, H = is->height, vm, R, L, s, ctop, cbot, hs = -2, hi = -1, sm = H < 460;
    double dt, ep = 1.0, t = now / 1000000.0;
    SDL_Rect box;
    static int last_q = -2;

    ui_flow_vmode = vm = ui_flow_video(is);
    ui_flow_n = 0;
    ui_flow_moving = 0;
    ui_tp_stop();
    if (W < 260 || H < 200)
        return;
    if (now - ui_tv_seen > 350000)
        ui_tv_reset(is, now);                   /* the view has just opened */
    ui_tv_seen = now;
    ui_tv_moving = 0;
    dt = ui_tv_t ? av_clipd((now - ui_tv_t) / 1000000.0, 0.0, 0.1) : 0.0;
    ui_tv_t = now;
    if (vm) {                                   /* the video shrinks into its tile (or grows back): the same animation as before */
        double want = ui_vflow ? 1.0 : 0.0, dtv = ui_vflow_t ? av_clipd((now - ui_vflow_t) / 1000000.0, 0.0, 0.1) : 0.0;

        ui_vflow_t = now;
        ui_vflow_p += (want - ui_vflow_p) * (1.0 - exp(-dtv * (want > 0.5 ? 8.0 : 12.0)));      /* growing back is quicker */
        if (fabs(want - ui_vflow_p) < 0.004)
            ui_vflow_p = want;
        ui_vflow_ep = ui_vflow_p * ui_vflow_p * (3.0 - 2.0 * ui_vflow_p);
        ep = ui_vflow_ep;
        if (ui_vflow_p != want)
            ui_tv_moving = 1;
    }
    if (q_pos != last_q) {                      /* a new item started: the focus goes to it */
        last_q = q_pos;
        if (!ui_tv_q[0])
            ui_tv_focus = q_pos;
    }
    ui_tv_focus = av_clip(ui_tv_focus, 0, q_count - 1);
    ui_tv_dims(is, &R, &L);
    if (ui_hov_x >= 0 && !ui_menu_open && !ui_prefs_open && !ui_tv_drag)
        if (!ui_tv_hit_at(ui_hov_x, ui_hov_y, &hs, &hi))
            hs = -2;
    ui_tvh_n = 0;

    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, (int)(110 * ep));         /* the tiles read better on a calmer picture */
    SDL_RenderFillRect(renderer, NULL);

    box.w = av_clip((int)(W * 0.6), 180, 560);          /* the search box */
    box.h = sm ? 30 : 38;
    box.x = (W - box.w) / 2;
    box.y = sm ? 34 : 44;
    {
        int r, g, b, tx = box.x + 18, cy = box.y + box.h / 2, al = (int)(255 * ep);
        SDL_Rect caret;

        ui_glass(&box, box.h / 2);
        ui_tv_theme(&r, &g, &b);
        if (ui_tv_q[0]) {
            ui_label(tx, cy, ui_tv_q, sm ? 15 : 18, 255, 255, 255, al);
            caret.x = tx + ui_text_width(ui_tv_q, sm ? 15 : 18) + 2;
        } else {
            ui_label(tx, cy, "Search the queue, your music and your videos", sm ? 14 : 16, 255, 255, 255, al * 45 / 100);
            caret.x = tx - 2;
        }
        if (ui_tv_searching || ui_tv_q[0]) {    /* a caret in the bar color that blinks */
            if (fmod(t, 1.0) < 0.6) {
                caret.y = cy - (sm ? 9 : 11);
                caret.w = 2;
                caret.h = sm ? 18 : 22;
                SDL_SetRenderDrawColor(renderer, r, g, b, al);
                SDL_RenderFillRect(renderer, &caret);
            }
            ui_tv_moving = 1;
        }
    }
    ctop = box.y + box.h + (sm ? 10 : 18);
    cbot = H - (sm ? 40 : 58);

    if (!ui_tv_q[0]) {                          /* browsing: the queue in rows, the lower row continues the upper one */
        UiTvRow row;
        double avail = cbot - ctop, rp = avail / R, sh, col = ui_tv_focus % L, rw = ui_tv_focus / L;
        int r;

        sh = av_clipd(FFMIN(rp * 0.62, W * 0.2), 40.0, 260.0);
        ui_tv_pos += (col - ui_tv_pos) * (1.0 - exp(-dt * 9.0));
        ui_tv_row += (rw - ui_tv_row) * (1.0 - exp(-dt * 9.0));
        if (fabs(col - ui_tv_pos) < 0.003)
            ui_tv_pos = col;
        else
            ui_tv_moving = 1;
        if (fabs(rw - ui_tv_row) < 0.003)
            ui_tv_row = rw;
        else
            ui_tv_moving = 1;
        for (r = 0; r < R; r++) {               /* the row in focus is drawn last, so it is on top */
            int rr = (r + (int)floor(ui_tv_row + 0.5) + 1) % R;

            row.sec = -1;
            row.first = rr * L;
            row.count = FFMIN(L, q_count - rr * L);
            if (row.count <= 0)
                continue;
            row.pos = FFMIN(ui_tv_pos, row.count - 1);
            row.cx = W / 2;
            row.cy = ctop + (int)(rp * (rr + 0.5)) - 8;
            row.sw = (int)(sh * 1.5);
            row.sh = (int)sh;
            row.rowd = fabs(rr - ui_tv_row);
            row.born = ui_tv_born;
            row.sm = sm;
            ui_tv_row_draw(is, &row, hs, hi, dt, now, ep);
        }
        if (!sm && ep > 0.9 && W > 480)         /* a quiet hint under the rows */
            ui_label_c(W / 2, H - 46, "Type to search     Enter plays     Esc closes", 13, 255, 255, 255, (int)(95 * ep));
    } else {                                    /* searching: three sections, each its own row of matches, the best one in focus */
        double secH = (cbot - ctop) / 3.0;
        int sh = (int)av_clipd(secH - 24 - 34, 36.0, 190.0), tr, tg, tb;

        ui_tv_theme(&tr, &tg, &tb);
        for (s = 0; s < 3; s++) {
            UiTvSec *sec = &ui_tv_sec[s];
            UiTvRow row;
            int top = ctop + (int)(secH * s), hy = top + 12, a = s == ui_tv_act ? 235 : 150;
            char head[96];
            SDL_Rect mark;

            ui_tv_secy[s][0] = top;
            ui_tv_secy[s][1] = top + (int)secH;
            snprintf(head, sizeof(head), "%s", ui_tv_title[s]);
            mark.x = 24;
            mark.y = hy - 7;
            mark.w = 3;
            mark.h = 14;
            SDL_SetRenderDrawColor(renderer, tr, tg, tb, a);
            ui_pill(&mark);
            ui_label(34, hy, head, sm ? 14 : 16, 255, 255, 255, a);
            if (sec->n > 0) {
                char cnt[24];

                snprintf(cnt, sizeof(cnt), "%d", sec->n);
                ui_label(34 + ui_text_width(head, sm ? 14 : 16) + 10, hy, cnt, sm ? 12 : 13, 255, 255, 255, 110);
            }
            sec->target = av_clip(sec->target, 0, FFMAX(sec->n - 1, 0));
            sec->pos += (sec->target - sec->pos) * (1.0 - exp(-dt * 9.0));
            if (fabs(sec->target - sec->pos) < 0.003)
                sec->pos = sec->target;
            else
                ui_tv_moving = 1;
            if (sec->n == 0) {
                const char *msg = (s > 0 && ui_tv_scan_state == 1) ? "Looking through your folders..." : "Nothing matches";

                ui_label(34, top + 12 + 28, msg, 14, 255, 255, 255, 95);
                continue;
            }
            row.sec = s;
            row.first = 0;
            row.count = sec->n;
            row.pos = sec->pos;
            row.cx = (int)(W * 0.30);
            row.cy = top + 24 + sh / 2 + 6;
            row.sw = (int)(sh * 1.5);
            row.sh = sh;
            row.rowd = s == ui_tv_act ? 0.0 : 0.45;
            row.born = sec->born;
            row.sm = sm;
            ui_tv_row_draw(is, &row, hs, hi, dt, now, ep);
        }
        if (ui_tv_scan_state == 1)
            ui_tv_moving = 1;                   /* the folders are still being read: the lists grow */
    }
    if (ui_tv_drag && ui_tv_press >= 0 && ui_tv_pressec == -1 && ui_tv_press < q_count) {       /* the tile that is being dragged, under the mouse */
        SDL_Rect g;
        int hs2, hi2;
        const char *p = q_items[ui_tv_press];
        double asp = ui_cov_aspect(p);

        g.h = (int)FFMIN(H * 0.2, 140);
        g.w = asp > 0.0 ? (int)(g.h * asp) : g.h;
        g.x = ui_hov_x - g.w / 2;
        g.y = ui_hov_y - g.h / 2;
        ui_tv_tile(p, &g, 215, 255);
        if (ui_tv_hit_at(ui_hov_x, ui_hov_y, &hs2, &hi2) && hs2 == -1 && hi2 != ui_tv_press) {      /* the place it would take */
            SDL_Rect m = { 0, 0, 0, 0 };
            int k;

            for (k = ui_tvh_n - 1; k >= 0; k--)
                if (ui_tvh[k].sec == -1 && ui_tvh[k].item == hi2) {
                    m = ui_tvh[k].r;
                    break;
                }
            SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                                   av_clip(cfg_bar_b + 40, 0, 255), 220);
            SDL_RenderDrawRect(renderer, &m);
        }
        ui_tv_moving = 1;
    }
    SDL_RenderSetClipRect(renderer, NULL);
}

/* ---- the mouse ---- */
static int ui_tv_click(VideoState *is, int x, int y)
{
    int sec, item;

    if (!ui_tv_hit_at(x, y, &sec, &item))
        return 0;
    ui_tv_press = item;
    ui_tv_pressec = sec;
    ui_tv_drag = 0;
    ui_tv_px = x;
    ui_tv_py = y;
    return 1;
}

static int ui_tv_motion(VideoState *is, int x, int y)
{
    ui_hov_x = x;
    ui_hov_y = y;
    if (ui_tv_press < 0)
        return 0;
    if (!ui_tv_drag && ui_tv_pressec == -1 && (FFABS(x - ui_tv_px) >= 8 || FFABS(y - ui_tv_py) >= 8)) {
        ui_tv_drag = 1;                         /* held and moved: the tile is dragged to a new place in the queue */
        SDL_CaptureMouse(SDL_TRUE);
    }
    is->force_refresh = 1;
    return 1;
}

static int ui_tv_release(VideoState *is, int x, int y)
{
    int item = ui_tv_press, sec = ui_tv_pressec, s2, i2;

    if (item < 0)
        return 0;
    ui_tv_press = -1;
    if (ui_tv_drag) {
        ui_tv_drag = 0;
        SDL_CaptureMouse(SDL_FALSE);
        if (ui_tv_hit_at(x, y, &s2, &i2) && s2 == -1 && i2 != item && item < q_count) {
            queue_move(item, i2);               /* dropped on another tile: it takes that place */
            ui_tv_focus = i2;
        }
    } else if (sec == -1) {
        if (item == ui_tv_focus)
            ui_tv_play(is, q_items[av_clip(item, 0, q_count - 1)]);     /* a tap on the tile in focus plays it */
        else
            ui_tv_focus = item;                 /* a tap on another tile brings it into focus */
    } else if (sec >= 0 && sec < 3) {
        if (item == ui_tv_sec[sec].target && ui_tv_act == sec)
            ui_tv_play(is, ui_tv_sec[sec].h[av_clip(item, 0, FFMAX(ui_tv_sec[sec].n - 1, 0))].path);
        else {
            ui_tv_act = sec;
            ui_tv_sec[sec].target = item;
        }
    }
    ui_tv_moving = 1;
    is->force_refresh = 1;
    return 1;
}

'''

patch("the tiled view", r'''static void ui_flow_draw(VideoState *is)
{
    enum { NEQ = 72 };''', TV + r'''static void ui_flow_draw(VideoState *is)
{
    enum { NEQ = 72 };''')

# ---------------------------------------------------------------- folders for the search (settings.conf)
patch("folder settings", r'''#define cfg_keep_window 1               /* the window keeps the size you gave it from one item to the next (nothing is kept between runs) */''',
      r'''static char    cfg_music_dir[400] = "";     /* v37: where the tiled view searches for music (empty = the system's Music folder) */
static char    cfg_video_dir[400] = "";     /* and for videos (empty = the system's Videos folder) */
#define cfg_keep_window 1               /* the window keeps the size you gave it from one item to the next (nothing is kept between runs) */''')

patch("folder settings load", r'''        else if (sscanf(line, " font = %400[^\n]", cfg_font) == 1) {''',
      r'''        else if (sscanf(line, " music_folder = %399[^\n]", cfg_music_dir) == 1) {
            n = (int)strlen(cfg_music_dir);
            while (n > 0 && cfg_music_dir[n - 1] == ' ')
                cfg_music_dir[--n] = 0;
        } else if (sscanf(line, " video_folder = %399[^\n]", cfg_video_dir) == 1) {
            n = (int)strlen(cfg_video_dir);
            while (n > 0 && cfg_video_dir[n - 1] == ' ')
                cfg_video_dir[--n] = 0;
        } else if (sscanf(line, " font = %400[^\n]", cfg_font) == 1) {''')

patch("folder settings save", r'''    ui_key_save(f);
''', r'''    fprintf(f, "# Folders the search of the tiled queue view looks in (empty = the system's Music and Videos folders)\nmusic_folder = %s\nvideo_folder = %s\n\n",
            cfg_music_dir, cfg_video_dir);
    ui_key_save(f);
''')

# ---------------------------------------------------------------- seeking: the tooltip keeps its size, many titles keep their text
patch("tooltip keeps its size", r'''    r.w = (int)(ui_th.w * sc);
    r.h = (int)(ui_th.h * sc);''', r'''    r.w = (int)(ui_th.w * sc * 0.6);            /* v37: the pictures are bigger now, the tooltip stays as it was */
    r.h = (int)(ui_th.h * sc * 0.6);''')

patch("text cache", "#define UI_TEXT_CACHE 128", "#define UI_TEXT_CACHE 320")

# ---------------------------------------------------------------- leaving full screen after the miniplayer: back to the window before it
patch("leaving full screen (F)", r"""    SDL_SetWindowFullscreen(window, is_full_screen ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0);
    if (!is_full_screen && ui_maxed)
        ui_max_set(1);
}""", r"""    SDL_SetWindowFullscreen(window, is_full_screen ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0);
    if (!is_full_screen)
        ui_pip_left_fs();
    if (!is_full_screen && ui_maxed)
        ui_max_set(1);
}""")

patch("leaving full screen (Esc)", r"""        is_full_screen = 0;
        SDL_SetWindowFullscreen(window, 0);
        ui_max_set(1);""", r"""        is_full_screen = 0;
        SDL_SetWindowFullscreen(window, 0);
        ui_max_set(1);
        ui_pip_left_fs();""")

if fails:
    print("%d edit(s) failed. Nothing written." % len(fails))
    sys.exit(1)
open(PATH, "w").write(src)
print("All edits applied. Rebuild: make -j$(nproc)")
