#!/usr/bin/env python3
# patch_queue_v28.py - run it inside ~/build/ffmpeg-6.1.1 (it edits fftools/ffplay.c)
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


if "ui_note_size" in src:
    print("Already applied")
    sys.exit(0)

# ---------------------------------------------------------------- globals
patch("window and seek state", r'''static int64_t ui_prog_until = 0;''',
r'''static int ui_keep_w = 0, ui_keep_h = 0;    /* the size the user gave the window: the next items open at it (full screen never changes it) */
static int ui_prog_w = 0, ui_prog_h = 0;    /* the size we asked for ourselves: an event with this size is ours, not the user's */
static int64_t ui_fs_toggle_at = 0;         /* when the window last went into or out of full screen */
static volatile int64_t ui_seek_last = 0;   /* when a seek was last asked for: the sound is quiet around it */
static int ui_hov_x = -1, ui_hov_y = -1;    /* where the mouse is (for the previews on the tiles) */
static int ui_tp_on = 0;                    /* 1 = a tile preview is waiting to start or is playing: keep drawing */
static int64_t ui_prog_until = 0;''')

patch("crossfade row state", r'''static int ui_chip_anim = 0;''',
r'''static double ui_xf_e = 0.0;            /* 0 to 1: how far the crossfade row has changed into its choices */
static int64_t ui_xf_last = 0;
static int ui_xf_anim = 0;
static int ui_chip_anim = 0;''')

# ---------------------------------------------------------------- window size that sticks
patch("size note helper", r'''/* Save where the window is, for the next start */
static void ui_win_save(void)''',
r'''/* A change of the window size has arrived. If it is the user's (not ours, and not full screen going in or out), the next
   items open at this size. Full screen never changes it, so a video can not come back at the size of the whole screen. */
static void ui_note_size(int w, int h)
{
    int64_t now = av_gettime_relative();

    if (!cfg_keep_window || !window || is_full_screen || w < 260 || h < 160)
        return;
    if (SDL_GetWindowFlags(window) & (SDL_WINDOW_FULLSCREEN | SDL_WINDOW_FULLSCREEN_DESKTOP))
        return;
    if (now - ui_fs_toggle_at < 1500000)        /* the sizes that go with full screen are the screen's, or the window coming back */
        return;
    if (now < ui_prog_until && FFABS(w - ui_prog_w) <= 2 && FFABS(h - ui_prog_h) <= 2)
        return;                                 /* our own change */
    ui_user_sized = 1;
    ui_keep_w = w;
    ui_keep_h = h;
}

/* Save where the window is, for the next start */
static void ui_win_save(void)''')

patch("our own size in video_open", r'''            ui_prog_until = av_gettime_relative() + 1500000;     /* the size change that follows is ours */
            SDL_SetWindowSize(window, w, h);''',
r'''            ui_prog_until = av_gettime_relative() + 1500000;     /* the size change that follows is ours */
            ui_prog_w = w;
            ui_prog_h = h;
            SDL_SetWindowSize(window, w, h);''')

patch("restored window is the kept size", r'''        screen_width = cfg_win_w;
        screen_height = cfg_win_h;
        ui_user_sized = 1;
''', r'''        screen_width = cfg_win_w;
        screen_height = cfg_win_h;
        ui_user_sized = 1;
        ui_keep_w = cfg_win_w;
        ui_keep_h = cfg_win_h;
''')

patch("no snapping right after full screen", r'''    ui_aspect_due = 0;
    if (cfg_keep_window && ui_user_sized && av_gettime_relative() < ui_prog_until)''',
r'''    ui_aspect_due = 0;
    if (av_gettime_relative() - ui_fs_toggle_at < 1500000)
        return;                                 /* the window is coming back from full screen: it already has its size */
    if (cfg_keep_window && ui_user_sized && av_gettime_relative() < ui_prog_until)''')

patch("our own size in the aspect tick", r'''    ui_prog_until = av_gettime_relative() + 1500000;
    SDL_SetWindowSize(window, nw, nh);
}''', r'''    ui_prog_until = av_gettime_relative() + 1500000;
    ui_prog_w = nw;
    ui_prog_h = nh;
    if (cfg_keep_window && ui_user_sized) {     /* the snapped size is the size the user chose */
        ui_keep_w = nw;
        ui_keep_h = nh;
    }
    SDL_SetWindowSize(window, nw, nh);
}''')

patch("full screen toggle time", r'''    is_full_screen = !is_full_screen;
    ui_prog_until = av_gettime_relative() + 2000000;''',
r'''    is_full_screen = !is_full_screen;
    ui_fs_toggle_at = av_gettime_relative();
    ui_prog_until = av_gettime_relative() + 2000000;''')

patch("size events (idle screen)", r'''                    screen_height = ev.window.data2;
                    if (cfg_keep_window && !is_full_screen && av_gettime_relative() > ui_prog_until)
                        ui_user_sized = 1;''',
r'''                    screen_height = ev.window.data2;
                    ui_note_size(ev.window.data1, ev.window.data2);''')

patch("size events (playing)", r'''                    if (cfg_keep_window && !is_full_screen && av_gettime_relative() > ui_prog_until)
                        ui_user_sized = 1;      /* not our own change: the user sized or tiled the window */''',
r'''                    ui_note_size(event.window.data1, event.window.data2);      /* the user sized or tiled the window? */''')

patch("next item keeps the user's size", r'''        if (!is_full_screen && !(cfg_keep_window && ui_user_sized))
            screen_width = screen_height = 0;   /* window follows the next video's size (unless the user sized it) */''',
r'''        if (cfg_keep_window && ui_user_sized && ui_keep_w >= 260 && ui_keep_h >= 160) {
            screen_width = ui_keep_w;           /* the size the user gave the window, whatever full screen did to screen_width since */
            screen_height = ui_keep_h;
        } else {
            screen_width = screen_height = 0;   /* window follows the next video's size */
        }''')

# ---------------------------------------------------------------- keys, tile tap, edges
patch("no Page Up / Page Down", r'''            case SDLK_PAGEUP:
                if (cur_stream->ic->nb_chapters <= 1) {
                    incr = 600.0;
                    goto do_seek;
                }
                seek_chapter(cur_stream, 1);
                break;
            case SDLK_PAGEDOWN:
                if (cur_stream->ic->nb_chapters <= 1) {
                    incr = -600.0;
                    goto do_seek;
                }
                seek_chapter(cur_stream, -1);
                break;''',
r'''            case SDLK_PAGEUP:
            case SDLK_PAGEDOWN:
                break;                  /* Page Up and Page Down do nothing */''')
patch("chapter seek is unused", r'''static void seek_chapter(VideoState *is, int incr)''', r'''static av_unused void seek_chapter(VideoState *is, int incr)''')

patch("a tap on the tile fills the window", r'''#define UI_TILE_TAP_FULLSCREEN 1''', r'''#define UI_TILE_TAP_FULLSCREEN 0''')

patch("corners only", r'''    int m = 5;      /* thickness of the edge zones */
    int c = 16;     /* size of the corner zones */

    SDL_GetWindowSize(window, &w, &h);
    if (x < m)      e |= UI_EDGE_L;
    if (x >= w - m) e |= UI_EDGE_R;
    if (y < m)      e |= UI_EDGE_T;
    if (y >= h - m) e |= UI_EDGE_B;
    /* corners are bigger, so they are easy to grab */''',
r'''    int c = 20;     /* size of the corner zones: only the corners resize the window */

    SDL_GetWindowSize(window, &w, &h);''')

# ---------------------------------------------------------------- quiet sound while seeking
patch("seek time", r'''    int prec = UI_PRECISE_SEEK ? ui_precise_next : 0;

    ui_precise_next = 0;''', r'''    int prec = UI_PRECISE_SEEK ? ui_precise_next : 0;

    ui_seek_last = av_gettime_relative();
    ui_precise_next = 0;''')

patch("quiet sound while seeking", r'''        vol = (int)(is->audio_volume * is->xf_gain * ui_sleep_gain + 0.5f);''',
r'''        {                                       /* quiet while seeking: the cut and restarted sound would scratch */
            static float duck = 1.0f;
            int64_t tnow = av_gettime_relative();
            float want = (is->seek_req || (is->prec_a && tnow - ui_seek_last < 1500000) || tnow - ui_seek_last < 260000) ? 0.0f : 1.0f;

            if (want < duck)
                duck = FFMAX(want, duck * 0.3f);        /* down within a few milliseconds */
            else
                duck = FFMIN(want, duck + 0.10f);       /* back up over about a third of a second */
            if (duck < 0.01f)
                duck = 0.0f;
            vol = (int)(is->audio_volume * is->xf_gain * ui_sleep_gain * duck + 0.5f);
        }''')

# ---------------------------------------------------------------- the queue view: tiles
patch("neighbours tuck behind the middle tile", r'''    return B * (0.86 * dc + 0.42 * (d - dc))''',
r'''    return B * ((ui_flow_vmode ? 0.74 : 0.86) * dc + 0.42 * (d - dc))''')

patch("video neighbours are nearly as big as the middle one", r'''            sc = 1.0 - 0.40 * FFMIN(ad, 1.0) - 0.06 * FFMAX(FFMIN(ad, 3.0) - 1.0, 0.0);''',
r'''            sc = 1.0 - ((ui_flow_vmode && i != q_pos && ui_cov_aspect(q_items[i]) > 0.0) ? 0.16 : 0.40) * FFMIN(ad, 1.0) -
                 0.06 * FFMAX(FFMIN(ad, 3.0) - 1.0, 0.0);''')

patch("tile previews keep the view drawing", r'''    return ui_flow_on(is) && (!is->paused || ui_flow_moving || ui_flow_dragging);''',
r'''    return ui_flow_on(is) && (!is->paused || ui_flow_moving || ui_flow_dragging || ui_tp_on);''')

patch("mouse leaves the window", r'''                case SDL_WINDOWEVENT_LEAVE:
                    ui_hover = 0;
                    break;''', r'''                case SDL_WINDOWEVENT_LEAVE:
                    ui_hover = 0;
                    ui_hov_x = -1;
                    break;''')

patch("remember where the mouse is", r'''static int ui_flow_motion(VideoState *is, int x, int y)
{
    if (ui_flow_press < 0)
        return 0;''', r'''static int ui_flow_motion(VideoState *is, int x, int y)
{
    ui_hov_x = x;
    ui_hov_y = y;
    if (ui_flow_press < 0)
        return 0;''')

patch("flow off: stop the preview", r'''        ui_flow_n = 0;
        ui_flow_moving = 0;
        return;
    }
    ui_flow_vmode = ui_flow_video(is);''', r'''        ui_flow_n = 0;
        ui_flow_moving = 0;
        ui_tp_stop();
        return;
    }
    ui_flow_vmode = ui_flow_video(is);''')

patch("preview tick", r'''    dt = ui_flow_t ? av_clipd((now - ui_flow_t) / 1000000.0, 0.0, 0.1) : 0.0;
    ui_flow_t = now;
    {                                           /* the video shrinks''', r'''    ui_tp_tick(is);
    dt = ui_flow_t ? av_clipd((now - ui_flow_t) / 1000000.0, 0.0, 0.1) : 0.0;
    ui_flow_t = now;
    {                                           /* the video shrinks''')

patch("preview drawn on its tile", r'''                    ui_flow_tile(i, &tile, (ui_flow_dragging && i == ui_flow_press) ? al / 3 : al, md, tl[e]);''',
r'''                    ui_flow_tile(i, &tile, (ui_flow_dragging && i == ui_flow_press) ? al / 3 : al, md, tl[e]);
                    ui_tp_draw(i, &tile, al, md, tl[e]);        /* the video under the mouse plays on its tile */''')

patch("preview engine", r'''static void ui_flow_draw(VideoState *is)
{
    enum { NEQ = 72 };''', r'''/* ---- previews on the tiles: the video under the mouse plays on its tile, without sound, at its own speed ---- */
#define UI_TILE_PREVIEW 1               /* 0 = no previews on the tiles */
#define UI_TP_W 480                     /* the width of the pictures */

static struct {
    SDL_Thread *thread;
    volatile int abort;
    SDL_mutex *mutex;
    char *file;                         /* the item that is previewed */
    int w, h;                           /* the size of the pictures (set by the thread before the first one) */
    uint8_t *rgba;                      /* the newest picture (the thread writes, the main thread reads, both under the mutex) */
    int serial, shown;                  /* counts up with each picture / the picture the texture has */
    int64_t born;                       /* when the first picture was drawn (for the fade in) */
    SDL_Texture *tex;
    int tex_w, tex_h;
} ui_tp;

static int ui_flow_cover_at(VideoState *is, int x, int y);

static int ui_tp_intr(void *p)
{
    return *(volatile int *)p;
}

/* The player of the preview: its own copy of the file, decoded on a thread, one picture at a time on the clock of the file */
static int ui_tp_run(void *arg)
{
    AVFormatContext *ic = NULL;
    AVCodecContext *cc = NULL;
    const AVCodec *dec = NULL;
    AVPacket *pk = av_packet_alloc();
    AVFrame *fr = av_frame_alloc();
    struct SwsContext *sws = NULL;
    uint8_t *buf = NULL;
    int vs, tw, th, bad = 0;
    int64_t begin = 0, wall0 = 0;
    double pts0 = NAN, last = NAN, tb;

    SDL_SetThreadPriority(SDL_THREAD_PRIORITY_LOW);
    if (!pk || !fr)
        goto end;
    ic = avformat_alloc_context();
    if (!ic)
        goto end;
    ic->interrupt_callback.callback = ui_tp_intr;
    ic->interrupt_callback.opaque = (void *)&ui_tp.abort;
    if (avformat_open_input(&ic, ui_tp.file, NULL, NULL) < 0) {
        ic = NULL;
        goto end;
    }
    if (avformat_find_stream_info(ic, NULL) < 0)
        goto end;
    vs = av_find_best_stream(ic, AVMEDIA_TYPE_VIDEO, -1, -1, &dec, 0);
    if (vs < 0 || !dec || (ic->streams[vs]->disposition & AV_DISPOSITION_ATTACHED_PIC))
        goto end;
    cc = avcodec_alloc_context3(dec);
    if (!cc || avcodec_parameters_to_context(cc, ic->streams[vs]->codecpar) < 0)
        goto end;
    cc->thread_count = 2;
    if (avcodec_open2(cc, dec, NULL) < 0 || cc->width <= 0 || cc->height <= 0)
        goto end;
    tw = FFMIN(UI_TP_W, cc->width) & ~1;
    th = ((int)((int64_t)tw * cc->height / cc->width)) & ~1;
    if (tw < 16 || th < 16)
        goto end;
    buf = av_malloc((size_t)tw * th * 4);
    if (!buf)
        goto end;
    tb = av_q2d(ic->streams[vs]->time_base);
    if (ic->duration > 20 * (int64_t)AV_TIME_BASE)      /* a little into the video, past the first seconds */
        begin = (ic->start_time != AV_NOPTS_VALUE ? ic->start_time : 0) + ic->duration / 6;
    else
        begin = ic->start_time != AV_NOPTS_VALUE ? ic->start_time : 0;
    if (begin > 0 && av_seek_frame(ic, -1, begin, AVSEEK_FLAG_BACKWARD) >= 0)
        avcodec_flush_buffers(cc);

    while (!ui_tp.abort) {
        int ret = av_read_frame(ic, pk);

        if (ret < 0) {                          /* the end: from the start again */
            if (++bad > 3)
                break;
            if (av_seek_frame(ic, -1, begin, AVSEEK_FLAG_BACKWARD) < 0)
                break;
            avcodec_flush_buffers(cc);
            pts0 = NAN;
            continue;
        }
        if (pk->stream_index != vs || avcodec_send_packet(cc, pk) < 0) {
            av_packet_unref(pk);
            continue;
        }
        av_packet_unref(pk);
        while (!ui_tp.abort && avcodec_receive_frame(cc, fr) == 0) {
            double pts = fr->best_effort_timestamp == AV_NOPTS_VALUE ? NAN : fr->best_effort_timestamp * tb;
            int64_t due, tnow;
            uint8_t *dp[4] = { buf, NULL, NULL, NULL };
            int dl[4] = { tw * 4, 0, 0, 0 };

            if (isnan(pts))
                pts = isnan(last) ? 0.0 : last + 0.04;
            last = pts;
            bad = 0;
            if (isnan(pts0)) {
                pts0 = pts;
                wall0 = av_gettime_relative();
            }
            due = wall0 + (int64_t)((pts - pts0) * 1000000.0);
            while (!ui_tp.abort && (tnow = av_gettime_relative()) < due)
                av_usleep(FFMIN(due - tnow, 4000));
            if (ui_tp.abort)
                break;
            tnow = av_gettime_relative();
            if (tnow - due > 250000)            /* far behind: carry on from here instead of racing to catch up */
                wall0 += tnow - due;
            sws = sws_getCachedContext(sws, fr->width, fr->height, fr->format, tw, th, AV_PIX_FMT_RGBA, SWS_BILINEAR, NULL, NULL, NULL);
            if (!sws) {
                av_frame_unref(fr);
                goto end;
            }
            sws_scale(sws, (const uint8_t * const *)fr->data, fr->linesize, 0, fr->height, dp, dl);
            SDL_LockMutex(ui_tp.mutex);
            if (!ui_tp.rgba || ui_tp.w != tw || ui_tp.h != th) {
                av_freep(&ui_tp.rgba);
                ui_tp.rgba = av_malloc((size_t)tw * th * 4);
                ui_tp.w = tw;
                ui_tp.h = th;
            }
            if (ui_tp.rgba) {
                memcpy(ui_tp.rgba, buf, (size_t)tw * th * 4);
                ui_tp.serial++;
            }
            SDL_UnlockMutex(ui_tp.mutex);
            av_frame_unref(fr);
        }
    }
end:
    sws_freeContext(sws);
    av_freep(&buf);
    avcodec_free_context(&cc);
    avformat_close_input(&ic);
    av_packet_free(&pk);
    av_frame_free(&fr);
    return 0;
}

static void ui_tp_stop(void)
{
    if (ui_tp.thread) {
        ui_tp.abort = 1;
        SDL_WaitThread(ui_tp.thread, NULL);
        ui_tp.thread = NULL;
    }
    ui_tp.abort = 0;
    if (ui_tp.tex) {
        SDL_DestroyTexture(ui_tp.tex);
        ui_tp.tex = NULL;
    }
    av_freep(&ui_tp.rgba);
    av_freep(&ui_tp.file);
    ui_tp.w = ui_tp.h = ui_tp.serial = ui_tp.shown = 0;
    ui_tp.born = 0;
    ui_tp_on = 0;
}

static void ui_tp_start(int idx)
{
    ui_tp_stop();
    if (idx < 0 || idx >= q_count)
        return;
    if (!ui_tp.mutex)
        ui_tp.mutex = SDL_CreateMutex();
    ui_tp.file = av_strdup(q_items[idx]);
    if (!ui_tp.file || !ui_tp.mutex || !(ui_tp.thread = SDL_CreateThread(ui_tp_run, "tile preview", NULL)))
        av_freep(&ui_tp.file);
}

/* Once per drawing of the queue view: a video tile that the mouse rests on for a moment starts to play */
static void ui_tp_tick(VideoState *is)
{
    static int cand = -1;
    static int64_t since = 0;
    int64_t now = av_gettime_relative();
    int idx = -1;

    if (UI_TILE_PREVIEW && ui_hov_x >= 0 && ui_flow_press < 0 && !ui_flow_dragging && !ui_menu_open && !ui_prefs_open) {
        int i = ui_flow_cover_at(is, ui_hov_x, ui_hov_y);

        if (i >= 0 && i < q_count && i != q_pos && ui_cov_aspect(q_items[i]) > 0.0)
            idx = i;
    }
    if (idx != cand) {                          /* another tile, or none: the preview stops */
        cand = idx;
        since = now;
        ui_tp_stop();
    } else if (idx >= 0 && !ui_tp.file && now - since > 400000) {
        ui_tp_start(idx);
    }
    ui_tp_on = cand >= 0;
}

/* The preview, if it is the one of tile i: drawn over the cover, with the same turn and rounded corners */
static void ui_tp_draw(int i, const SDL_Rect *tile, int al, int md, double tilt)
{
    int64_t now = av_gettime_relative();
    double fade;

    if (!ui_tp.file || !ui_tp.mutex || strcmp(q_items[i], ui_tp.file))
        return;
    SDL_LockMutex(ui_tp.mutex);
    if (ui_tp.rgba && ui_tp.w > 0 && ui_tp.serial != ui_tp.shown) {
        if (ui_tp.tex && (ui_tp.tex_w != ui_tp.w || ui_tp.tex_h != ui_tp.h)) {
            SDL_DestroyTexture(ui_tp.tex);
            ui_tp.tex = NULL;
        }
        if (!ui_tp.tex) {
            ui_tp.tex = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STATIC, ui_tp.w, ui_tp.h);
            ui_tp.tex_w = ui_tp.w;
            ui_tp.tex_h = ui_tp.h;
            if (ui_tp.tex)
                SDL_SetTextureBlendMode(ui_tp.tex, SDL_BLENDMODE_BLEND);
        }
        if (ui_tp.tex)
            SDL_UpdateTexture(ui_tp.tex, NULL, ui_tp.rgba, ui_tp.w * 4);
        ui_tp.shown = ui_tp.serial;
    }
    SDL_UnlockMutex(ui_tp.mutex);
    if (!ui_tp.tex)
        return;
    if (!ui_tp.born)
        ui_tp.born = now;
    fade = av_clipd((now - ui_tp.born) / 250000.0, 0.0, 1.0);
    ui_flow_quad_round(ui_tp.tex, tile, (int)(al * fade), md, tilt, FFMIN(tile->w, tile->h) / 11);
}

static void ui_flow_draw(VideoState *is)
{
    enum { NEQ = 72 };''')

# ---------------------------------------------------------------- Preferences: the name stays, the choices squeeze in beside it
patch("panel width state", r'''static int ui_prefs_anim = 0;       /* 1 = a row is still gliding */''',
r'''static int ui_prefs_anim = 0;       /* 1 = a row is still gliding */
static double ui_prefs_w = 600.0;   /* the width of the panel: it grows when a row needs more room, and goes back */''')

between("row choices beside the name", r'''/* Where the choices of a row go (centered in the row;''', r'''/* Which choice of the row is at x, y?''', r'''/* Where the choices of a row go: on the right of the name, which stays. The text and the gaps get smaller if they would not
   fit in the room that is left. Returns how many. */
static int ui_pref_layout(int row, const SDL_Rect *p, int cy, SDL_Rect out[10], const char *names[10], char store[10][20],
                          int *sel, int *px)
{
    static const int px_try[4] = { 18, 16, 15, 14 }, pad_try[4] = { 18, 14, 10, 8 };
    int n = ui_pref_choices(row, names, store, sel), i, total = 0, x, w[10], pass, room;

    room = p->w - 64 - ui_text_width(ui_pref_name[row], 20) - 18;
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
    x = p->x + p->w - 32 - total;               /* against the right margin */
    for (i = 0; i < n; i++) {
        out[i].x = x;
        out[i].y = cy - 16;
        out[i].w = w[i];
        out[i].h = 32;
        x += w[i] + 3;
    }
    return n;
}

/* The width the panel needs so that the name and all choices of a row fit, at the smallest text */
static int ui_pref_need_w(int row)
{
    const char *names[10];
    char store[10][20];
    int sel, n = ui_pref_choices(row, names, store, &sel), i, total = 0;

    for (i = 0; i < n; i++)
        total += ui_text_width(names[i], 14) + 8 + (i ? 3 : 0);
    return 64 + ui_text_width(ui_pref_name[row], 20) + 18 + total;
}

''')

between("panel width", r'''static SDL_Rect ui_prefs_rect(int ww, int wh)''', r'''static void ui_prefs_draw(void)''', r'''static SDL_Rect ui_prefs_rect(int ww, int wh)
{
    SDL_Rect p;

    p.w = FFMIN((int)(ui_prefs_w + 0.5), ww - 40);
    p.h = UI_PREF_HEAD + UI_PREF_ROWS * UI_PREF_ROW + UI_PREF_FOOT;
    p.x = (ww - p.w) / 2;
    p.y = (wh - p.h) / 2;
    return p;
}

''')

between("rows draw", r'''static void ui_prefs_draw(void)''', r'''/* Mouse events while the panel is open.''', r'''static void ui_prefs_draw(void)
{
    SDL_Rect p, sw;
    char value[48];
    int ww, wh, i, cy, x_right, vw, vx;
    double e, se, k, dt, wt;
    static int64_t last = 0;
    int64_t now = av_gettime_relative();

    if (!ui_prefs_open) {
        for (i = 0; i < UI_PREF_ROWS; i++)
            ui_pref_open[i] = 0.0;
        ui_prefs_anim = 0;
        ui_prefs_w = 600.0;
        return;
    }
    dt = now - last > 100000 ? 0.016 : (now - last) / 1000000.0;
    last = now;
    ui_prefs_anim = 0;
    for (i = 0; i < UI_PREF_ROWS; i++) {        /* the rows glide toward their choices, or back */
        double tgt = i == ui_prefs_hover ? 1.0 : 0.0;

        ui_pref_open[i] += (tgt - ui_pref_open[i]) * (1.0 - exp(-dt / 0.07));
        if (fabs(tgt - ui_pref_open[i]) < 0.005)
            ui_pref_open[i] = tgt;
        else
            ui_prefs_anim = 1;
    }
    SDL_GetWindowSize(window, &ww, &wh);
    wt = 600.0;                                 /* the panel grows if the name and the choices of the row under the mouse need more */
    if (ui_prefs_hover >= 0 && ui_prefs_hover < UI_PREF_ROWS)
        wt = FFMAX(wt, ui_pref_need_w(ui_prefs_hover));
    wt = FFMIN(wt, ww - 40);
    ui_prefs_w += (wt - ui_prefs_w) * (1.0 - exp(-dt / 0.09));
    if (fabs(wt - ui_prefs_w) < 0.6)
        ui_prefs_w = wt;
    else
        ui_prefs_anim = 1;
    p = ui_prefs_rect(ww, wh);
    ui_glass(&p, 28);
    x_right = p.x + p.w - 32;

    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    ui_label(p.x + 32, p.y + UI_PREF_HEAD / 2 + 4, "Preferences", 28, 245, 245, 245, 255);
    for (i = 0; i < UI_PREF_ROWS; i++) {
        cy = p.y + UI_PREF_HEAD + i * UI_PREF_ROW + UI_PREF_ROW / 2;
        e = ui_pref_open[i];
        se = e * e * (3.0 - 2.0 * e);
        k = 1.0 - se;                           /* how much of the value is still showing */
        ui_label(p.x + 32, cy, ui_pref_name[i], 20, 245, 245, 245, i == ui_prefs_hover ? 255 : 210);     /* the name stays */

        if (k > 0.01) {
            ui_pref_value(i, value, sizeof(value));
            vw = ui_text_width(value, 20);
            vx = x_right - vw;
            if (i == 4) {
                sw.x = vx - 26;                 /* a dot in the chosen color */
                sw.y = cy - 8;
                sw.w = 16;
                sw.h = 16;
                SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, (int)(255 * k));
                ui_pill(&sw);
            }
            if (!ui_pref_arrows(i) && !strcmp(value, "Off"))
                ui_label(vx, cy, value, 20, 150, 150, 150, (int)(255 * k));
            else
                ui_label(vx, cy, value, 20, 245, 245, 245, (int)(255 * k));
        }

        if (e > 0.01) {                         /* the choices squeeze in from the right margin, beside the name */
            SDL_Rect r[10];
            const char *names[10];
            char store[10][20];
            int n, c, sel, px, hot;

            n = ui_pref_layout(i, &p, cy, r, names, store, &sel, &px);
            for (c = 0; c < n; c++) {
                double cxc = r[c].x + r[c].w / 2.0, cx = x_right + (cxc - x_right) * se;

                hot = i == ui_prefs_hover && ui_prefs_mx >= r[c].x && ui_prefs_mx < r[c].x + r[c].w &&
                      ui_prefs_my >= r[c].y && ui_prefs_my < r[c].y + r[c].h;
                if (hot) {                      /* a soft pill under the choice the mouse is on */
                    SDL_Rect pill = r[c];

                    pill.x = (int)(cx - r[c].w / 2.0);
                    SDL_SetRenderDrawColor(renderer, 255, 255, 255, (int)(34 * se));
                    ui_pill(&pill);
                }
                if (c == sel)                   /* the choice that is on: in the bar color */
                    ui_label_c((int)cx, cy, names[c], px, av_clip(cfg_bar_r + 40, 0, 255),
                               av_clip(cfg_bar_g + 40, 0, 255), av_clip(cfg_bar_b + 40, 0, 255), (int)(255 * se));
                else
                    ui_label_c((int)cx, cy, names[c], px, 245, 245, 245, (int)((hot ? 255 : 170) * se));
            }
        }
    }
    ui_label(p.x + 32, p.y + p.h - UI_PREF_FOOT / 2, "Move the mouse onto a setting to see its choices.  Esc closes.",
             15, 170, 170, 170, 255);
}

''')

# ---------------------------------------------------------------- the queue panel: crossfade and sleep timer rows
patch("queue chip kinds", r'''#define UI_Q_CHIP   12          /* one of its choices (the number is in the item) */''',
r'''#define UI_Q_CHIP   12          /* one of its choices (the number is in the item) */
#define UI_Q_XFCHIP 13          /* one of the choices of the crossfade (the number is in the item) */
#define UI_Q_XFROW  14          /* the crossfade row: its choices show while the mouse is on it */''')

between("row choices under the list", r'''/* Where the six choices go when the sleep row is open''', r'''/* The list position where the dragged item would land */''', r'''/* The choices of the crossfade, in seconds */
static const char *const ui_xf_names[7] = { "Off", "1s", "2s", "3s", "5s", "8s", "10s" };
static const int ui_xf_vals[7] = { 0, 1, 2, 3, 5, 8, 10 };

/* Where the choices of a row under the list go: on the right of its name (labelw wide), which stays. The long names are used
   when they fit, then the short ones, then smaller text. Returns the names to draw; *px is their text size. */
static const char *const *ui_q_chips_for(const SDL_Rect *p, int cy, int labelw, int n, const char *const *full,
                                         const char *const *shrt, SDL_Rect *out, int *px)
{
    static const int pxs[3] = { 14, 15, 13 }, pads[3] = { 10, 8, 6 };
    const char *const *names = full;
    int pass, i, w[8], total = 0, x, room = p->w - 40 - labelw - 14;

    for (pass = 0; pass < 3; pass++) {
        names = pass == 0 ? full : shrt;
        total = 0;
        for (i = 0; i < n; i++) {
            w[i] = ui_text_width(names[i], pxs[pass]) + pads[pass];
            total += w[i] + (i ? 3 : 0);
        }
        *px = pxs[pass];
        if (total <= room)
            break;
    }
    x = p->x + p->w - 20 - total;
    for (i = 0; i < n; i++) {
        out[i].x = x;
        out[i].y = cy - 13;
        out[i].w = w[i];
        out[i].h = 26;
        x += w[i] + 3;
    }
    return names;
}

/* The six choices of the sleep timer (cy = the middle of the row) */
static const char *const *ui_q_chips(const SDL_Rect *p, int cy, SDL_Rect out[6])
{
    int px;

    return ui_q_chips_for(p, cy, ui_text_width("Sleep timer", 18), 6, ui_chip_full, ui_chip_short, out, &px);
}

''')

patch("hit test: chip list is bigger", r'''    int fy = top + ui_q_visible(wh) * UI_Q_ROW, i;
    SDL_Rect chip[6];''', r'''    int fy = top + ui_q_visible(wh) * UI_Q_ROW, i;
    SDL_Rect chip[8];''')

patch("hit test: crossfade choices", r'''        if (y >= fy + 6 && y < fy + 46) {       /* crossfade: the left half of the value shortens it */
            if (x < right - 170)
                return UI_Q_NONE;
            return x < right - 84 ? UI_Q_XF_DEC : UI_Q_XF_INC;
        }''', r'''        if (y >= fy + 6 && y < fy + 46) {       /* crossfade: the choices are there while the mouse is on the row */
            if (ui_q_hover_kind == UI_Q_XFROW || ui_q_hover_kind == UI_Q_XFCHIP) {
                int xpx;

                ui_q_chips_for(p, fy + 26, ui_text_width("Crossfade", 18), 7, ui_xf_names, ui_xf_names, chip, &xpx);
                for (i = 0; i < 7; i++)
                    if (x >= chip[i].x && x < chip[i].x + chip[i].w) {
                        *item = i;
                        return UI_Q_XFCHIP;
                    }
            }
            return UI_Q_XFROW;
        }''')

patch("click on a crossfade choice", r'''    } else if (kind == UI_Q_CHIP) {
        ui_sleep_choose(item);''', r'''    } else if (kind == UI_Q_XFCHIP) {
        cfg_crossfade = ui_xf_vals[av_clip(item, 0, 6)];
        settings_save();
    } else if (kind == UI_Q_XFROW) {
        /* the row itself: the choices are showing, nothing to do */
    } else if (kind == UI_Q_CHIP) {
        ui_sleep_choose(item);''')

patch("rows redraw while they glide", r'''    if ((ui_q_open && ui_chip_anim) || (ui_prefs_open && ui_prefs_anim))''',
r'''    if ((ui_q_open && (ui_chip_anim || ui_xf_anim)) || (ui_prefs_open && ui_prefs_anim))''')

between("crossfade and sleep rows", r'''    /* crossfade: < 3 s > */''', r'''    /* the counter: which item, and how far through the whole queue.''', r'''    /* crossfade: its name stays; the choices squeeze in on the right of it while the mouse is on the row */
    cy = fy + 26;
    {
        double tgt = (hk == UI_Q_XFROW || hk == UI_Q_XFCHIP) ? 1.0 : 0.0, se, ek, dt, hx = right - 20;
        int64_t t2 = av_gettime_relative();
        SDL_Rect xr[8];
        const char *const *xn;
        int xpx, cur = 0, k;

        dt = t2 - ui_xf_last > 100000 ? 0.016 : (t2 - ui_xf_last) / 1000000.0;
        ui_xf_last = t2;
        ui_xf_e += (tgt - ui_xf_e) * (1.0 - exp(-dt / 0.07));
        if (fabs(tgt - ui_xf_e) < 0.005)
            ui_xf_e = tgt;
        ui_xf_anim = ui_xf_e != tgt;
        se = ui_xf_e * ui_xf_e * (3.0 - 2.0 * ui_xf_e);
        ek = 1.0 - se;
        ui_label(p.x + 20, cy, "Crossfade", 18, 240, 240, 240, 210);
        if (ek > 0.01) {
            if (cfg_crossfade)
                snprintf(text, sizeof(text), "%d s", cfg_crossfade);
            else
                snprintf(text, sizeof(text), "Off");
            if (cfg_crossfade)
                ui_label(right - 20 - ui_text_width(text, 18), cy, text, 18, 245, 245, 245, (int)(255 * ek));
            else
                ui_label(right - 20 - ui_text_width(text, 18), cy, text, 18, 150, 150, 150, (int)(255 * ek));
        }
        if (ui_xf_e > 0.01) {
            for (k = 1; k < 7; k++)
                if (abs(ui_xf_vals[k] - cfg_crossfade) < abs(ui_xf_vals[cur] - cfg_crossfade))
                    cur = k;
            xn = ui_q_chips_for(&p, cy, ui_text_width("Crossfade", 18), 7, ui_xf_names, ui_xf_names, xr, &xpx);
            for (k = 0; k < 7; k++) {
                int hot = hk == UI_Q_XFCHIP && ui_q_hover_idx == k;
                double cxc = xr[k].x + xr[k].w / 2.0, cx = hx + (cxc - hx) * se;

                if (k == cur)
                    ui_label_c((int)cx, cy, xn[k], xpx, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                               av_clip(cfg_bar_b + 40, 0, 255), (int)(255 * se));
                else
                    ui_label_c((int)cx, cy, xn[k], xpx, 245, 245, 245, (int)((hot ? 255 : 160) * se));
            }
        }
    }

    /* sleep timer: its name stays; the choices squeeze in on the right of it while the mouse is on the row */
    cy = fy + 66;
    sel = ui_sleep_current();
    {
        double tgt = (hk == UI_Q_SLEEP || hk == UI_Q_CHIP) ? 1.0 : 0.0, ek, se, dt, hx = right - 20;
        int64_t t2 = av_gettime_relative();
        SDL_Rect sr[8];
        const char *const *sn;
        int spx;

        dt = t2 - ui_chip_last > 100000 ? 0.016 : (t2 - ui_chip_last) / 1000000.0;
        ui_chip_last = t2;
        ui_chip_e += (tgt - ui_chip_e) * (1.0 - exp(-dt / 0.07));      /* the row glides, it does not jump */
        if (fabs(tgt - ui_chip_e) < 0.005)
            ui_chip_e = tgt;
        ui_chip_anim = ui_chip_e != tgt;
        se = ui_chip_e * ui_chip_e * (3.0 - 2.0 * ui_chip_e);
        ek = 1.0 - se;
        ui_label(p.x + 20, cy, "Sleep timer", 18, 240, 240, 240, 210);
        if (ek > 0.01) {
            ui_sleep_text(text, sizeof(text));
            if (sel)
                ui_label(right - 20 - ui_text_width(text, 18), cy, text, 18, av_clip(cfg_bar_r + 40, 0, 255),
                         av_clip(cfg_bar_g + 40, 0, 255), av_clip(cfg_bar_b + 40, 0, 255), (int)(255 * ek));
            else
                ui_label(right - 20 - ui_text_width(text, 18), cy, text, 18, 150, 150, 150, (int)(255 * ek));
        }
        if (ui_chip_e > 0.01) {
            sn = ui_q_chips_for(&p, cy, ui_text_width("Sleep timer", 18), 6, ui_chip_full, ui_chip_short, sr, &spx);
            for (i = 0; i < 6; i++) {
                int hot = hk == UI_Q_CHIP && ui_q_hover_idx == i;
                double cxc = sr[i].x + sr[i].w / 2.0, cx = hx + (cxc - hx) * se;

                if (i == sel)               /* the choice that is on: in the bar color */
                    ui_label_c((int)cx, cy, sn[i], spx, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                               av_clip(cfg_bar_b + 40, 0, 255), (int)(255 * se));
                else
                    ui_label_c((int)cx, cy, sn[i], spx, 245, 245, 245, (int)((hot ? 255 : 160) * se));
            }
        }
    }

''')

patch("unused names in the queue panel", r"""    SDL_Rect p = ui_q_rect(ww, wh), sep, dot, chip[6], clip;
    char name[300], text[96], a[24], b[24];
    const char *const *names;
    int vis = ui_q_visible(wh);""", r"""    SDL_Rect p = ui_q_rect(ww, wh), sep, dot, clip;
    char name[300], text[96], a[24], b[24];
    int vis = ui_q_visible(wh);""")
patch("unused vx in the queue panel", r"""hk = ui_q_hover_kind, fy, marker, sel, vx;""", r"""hk = ui_q_hover_kind, fy, marker, sel;""")

if fails:
    print("\n%d patches did not apply. Nothing was written." % len(fails))
    sys.exit(1)
open(PATH, "w").write(src)
print("Patched " + PATH)
