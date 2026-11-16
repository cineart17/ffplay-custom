#!/usr/bin/env python3
# Update 26 for ffplay-custom (on top of patch_queue_v25.py).
#   * Previews on the seek bar: a picture of the video at the time under the mouse (or where you drag to), above the time.
#     A second reader makes them in the background, at low priority, from the file that plays: first a coarse set across the whole
#     video, then finer ones, a key frame each (about one for every 3 seconds, 240 at most). The mouse only looks them up,
#     so the preview follows it with no waiting, however fast it moves. Videos shorter than 8 s, songs and streams get none.
#   * Remember window (a new row in Preferences, on by default): the size and place of the window are saved when the player
#     closes and restored at the next start. Once the window has been resized or tiled by you, the next items of the queue
#     keep that size (letterboxed if their shape is different) instead of resizing the window to their own shape.
#   * Always on top: key O, or a right click on the title bar where the window manager's menu is not available (not X11).
#     A small dot in the title bar shows when it is on.
#   * Song tiles have their own, smaller size next to the video tiles in the queue view while a video plays.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v25.py. Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_th_tick(" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_ks_tick(" not in src:
    print("Apply patch_queue_v25.py first. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


# ============================================================ fields
patch(r'''    int ui_held;                /* 0 = not held, 1 = paused on the last picture, 2 = restarting */
''', r'''    int ui_held;                /* 0 = not held, 1 = paused on the last picture, 2 = restarting */
    int ui_thumb_id;            /* the seek previews of this stream: 0 = not started, -1 = none, else their number */
''', "stream field for previews")

# ============================================================ remember the window
patch(r'''static int     cfg_crossfade = 0;           /* seconds the end of one item and the start of the next overlap (0 to 10) */''',
      r'''static int     cfg_crossfade = 0;           /* seconds the end of one item and the start of the next overlap (0 to 10) */
static int     cfg_keep_window = 1;         /* 1 = remember the window's size and place, and keep its size between items */
static int     cfg_win_x = 0, cfg_win_y = 0, cfg_win_w = 0, cfg_win_h = 0;     /* where it was when the player closed */
static int     ui_user_sized = 0;           /* 1 = the window was resized or tiled by the user: the next items keep its size */
static int64_t ui_prog_until = 0;           /* until then a change of the window size is our own, not the user's */''', "window settings")

patch(r'''        else if (sscanf(line, " crossfade = %d", &n) == 1)
            cfg_crossfade = av_clip(n, 0, 10);''', r'''        else if (sscanf(line, " crossfade = %d", &n) == 1)
            cfg_crossfade = av_clip(n, 0, 10);
        else if (sscanf(line, " remember_window = %d", &n) == 1)
            cfg_keep_window = (n != 0);
        else if (sscanf(line, " window_rect = %d %d %d %d", &cfg_win_x, &cfg_win_y, &cfg_win_w, &cfg_win_h) == 4)
            ;''', "read the window settings")

patch(r'''            cfg_crossfade);
    ui_key_save(f);''', r'''            cfg_crossfade);
    fprintf(f, "# 1 = remember the window's size and place between runs, and keep its size from one item to the next\nremember_window = %d\n\n",
            cfg_keep_window);
    if (cfg_win_w > 0)
        fprintf(f, "# Where the window was at the end of the last run: x y width height\nwindow_rect = %d %d %d %d\n\n",
                cfg_win_x, cfg_win_y, cfg_win_w, cfg_win_h);
    ui_key_save(f);''', "write the window settings")

# ============================================================ the previews engine, and saving the window, before do_exit
patch(r'''static void do_exit(VideoState *is)
{
    if (is)
        volume_save(is->audio_volume);''', r'''/* ---- the previews on the seek bar ---- */
#define UI_THUMBS 1                     /* 0 = no previews */
#define UI_TH_MAX 240

typedef struct {
    uint8_t *rgba;                      /* the picture, made by the reader */
    int ready;                          /* 1 = rgba is complete */
    SDL_Texture *tex;                   /* made on first use, by the main thread */
} UiThumb;

static struct {
    SDL_Thread *thread;
    volatile int abort;
    int id, n, w, h;                    /* the stream they belong to, how many, the size of each */
    double dur;                         /* seconds */
    int64_t start;                      /* the file's start time, in AV_TIME_BASE units */
    char *file;
    UiThumb t[UI_TH_MAX];
} ui_th;

static int ui_th_intr(void *p)
{
    return *(volatile int *)p;
}

/* The reader: its own copy of the file and a decoder that only decodes key frames */
static int ui_th_run(void *arg)
{
    AVFormatContext *ic = NULL;
    AVCodecContext *cc = NULL;
    const AVCodec *dec = NULL;
    AVPacket *pk = av_packet_alloc();
    AVFrame *fr = av_frame_alloc();
    struct SwsContext *sws = NULL;
    int vs, n = ui_th.n, i, m = 0, stride, order[UI_TH_MAX], tw = ui_th.w, th = ui_th.h, made = 0;
    int64_t t0 = av_gettime_relative();

    SDL_SetThreadPriority(SDL_THREAD_PRIORITY_LOW);      /* in the background: the playing comes first */
    if (!pk || !fr)
        goto end;
    ic = avformat_alloc_context();
    if (!ic)
        goto end;
    ic->interrupt_callback.callback = ui_th_intr;
    ic->interrupt_callback.opaque = (void *)&ui_th.abort;
    if (avformat_open_input(&ic, ui_th.file, NULL, NULL) < 0) {
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
    cc->skip_frame = AVDISCARD_NONKEY;
    cc->thread_count = 1;
    if (avcodec_open2(cc, dec, NULL) < 0)
        goto end;

    for (stride = 32; stride >= 1; stride >>= 1)        /* coarse first, then finer: every time some are ready everywhere */
        for (i = 0; i < n; i += stride)
            if (stride == 32 || (i % (stride << 1)))
                order[m++] = i;

    for (i = 0; i < m && !ui_th.abort; i++) {
        int idx = order[i], got = 0, tries;
        int64_t ts = ui_th.start + (int64_t)((idx + 0.5) * ui_th.dur / n * AV_TIME_BASE);
        uint8_t *dst, *dp[4] = { NULL };
        int dl[4] = { 0 };

        if (av_seek_frame(ic, -1, ts, AVSEEK_FLAG_BACKWARD) < 0)
            continue;
        avcodec_flush_buffers(cc);
        for (tries = 0; tries < 400 && !got && !ui_th.abort; tries++) {
            if (av_read_frame(ic, pk) < 0)
                break;
            if (pk->stream_index == vs && avcodec_send_packet(cc, pk) == 0) {
                if (avcodec_receive_frame(cc, fr) == 0) {
                    got = 1;
                } else {                        /* the decoder keeps the picture back: ask for it */
                    avcodec_send_packet(cc, NULL);
                    if (avcodec_receive_frame(cc, fr) == 0)
                        got = 1;
                    else
                        avcodec_flush_buffers(cc);
                }
            }
            av_packet_unref(pk);
        }
        if (!got)
            continue;
        sws = sws_getCachedContext(sws, fr->width, fr->height, fr->format, tw, th, AV_PIX_FMT_RGBA, SWS_BILINEAR, NULL, NULL, NULL);
        dst = av_malloc((size_t)tw * th * 4);
        if (sws && dst) {
            dp[0] = dst;
            dl[0] = tw * 4;
            sws_scale(sws, (const uint8_t * const *)fr->data, fr->linesize, 0, fr->height, dp, dl);
            ui_th.t[idx].rgba = dst;
            __atomic_store_n(&ui_th.t[idx].ready, 1, __ATOMIC_RELEASE);
            made++;
        } else {
            av_free(dst);
        }
        av_frame_unref(fr);
    }
end:
    av_log(NULL, AV_LOG_VERBOSE, "ffplay-custom: seek previews: %d of %d made in %d ms\n", made, n, (int)((av_gettime_relative() - t0) / 1000));
    sws_freeContext(sws);
    avcodec_free_context(&cc);
    avformat_close_input(&ic);
    av_packet_free(&pk);
    av_frame_free(&fr);
    return 0;
}

static void ui_th_stop(void)
{
    int i;

    if (ui_th.thread) {
        ui_th.abort = 1;
        SDL_WaitThread(ui_th.thread, NULL);
        ui_th.thread = NULL;
    }
    for (i = 0; i < UI_TH_MAX; i++) {
        if (ui_th.t[i].tex)
            SDL_DestroyTexture(ui_th.t[i].tex);
        ui_th.t[i].tex = NULL;
        av_freep(&ui_th.t[i].rgba);
        ui_th.t[i].ready = 0;
    }
    av_freep(&ui_th.file);
    ui_th.n = 0;
    ui_th.id = 0;
    ui_th.abort = 0;
}

/* Save where the window is, for the next start */
static void ui_win_save(void)
{
    int x, y, w, h;
    Uint32 fl;

    if (!cfg_keep_window || !window || is_full_screen)
        return;
    fl = SDL_GetWindowFlags(window);
    if (!(fl & SDL_WINDOW_SHOWN) || (fl & (SDL_WINDOW_MAXIMIZED | SDL_WINDOW_MINIMIZED)))
        return;
    SDL_GetWindowPosition(window, &x, &y);
    SDL_GetWindowSize(window, &w, &h);
    if (w < 260 || h < 160 || (x == cfg_win_x && y == cfg_win_y && w == cfg_win_w && h == cfg_win_h))
        return;
    cfg_win_x = x;
    cfg_win_y = y;
    cfg_win_w = w;
    cfg_win_h = h;
    settings_save();
}

static void do_exit(VideoState *is)
{
    ui_th_stop();
    ui_win_save();
    if (is)
        volume_save(is->audio_volume);''', "previews engine and saving the window")

# ============================================================ the window keeps its size
patch(r'''static int video_open(VideoState *is)
{
    int w,h;

    w = screen_width ? screen_width : default_width;''', r'''static int video_open(VideoState *is)
{
    int w,h;
    static int restored = 0;

    if (!ui_shown_once && !restored && cfg_keep_window && !screen_width && cfg_win_w >= 260 && cfg_win_h >= 160) {
        int nd = SDL_GetNumVideoDisplays(), k, ok = 0;
        SDL_Rect b;

        restored = 1;                           /* the window as it was when the player closed last time */
        for (k = 0; k < nd; k++)
            if (SDL_GetDisplayBounds(k, &b) == 0 && cfg_win_x + 60 >= b.x && cfg_win_x + 60 < b.x + b.w &&
                cfg_win_y + 20 >= b.y && cfg_win_y + 20 < b.y + b.h)
                ok = 1;                         /* only if that place is still on a screen */
        if (ok) {
            screen_left = cfg_win_x;
            screen_top = cfg_win_y;
        }
        screen_width = cfg_win_w;
        screen_height = cfg_win_h;
        ui_user_sized = 1;
    }
    w = screen_width ? screen_width : default_width;''', "restore the window")

patch(r'''        } else {
            SDL_SetWindowSize(window, w, h);
        }
        if (!ui_shown_once)
            SDL_SetWindowPosition(window, screen_left, screen_top);''', r'''        } else {
            ui_prog_until = av_gettime_relative() + 1500000;     /* the size change that follows is ours */
            SDL_SetWindowSize(window, w, h);
        }
        if (!ui_shown_once)
            SDL_SetWindowPosition(window, screen_left, screen_top);''', "our own resize in video_open")

patch(r'''        if (!is_full_screen)
            screen_width = screen_height = 0;   /* window follows the next video's size */''',
      r'''        if (!is_full_screen && !(cfg_keep_window && ui_user_sized))
            screen_width = screen_height = 0;   /* window follows the next video's size (unless the user sized it) */''',
      "the next item keeps the size")

patch(r'''                    ui_aspect_due = av_gettime_relative() + 250000;
''', r'''                    ui_aspect_due = av_gettime_relative() + 250000;
                    if (cfg_keep_window && !is_full_screen && av_gettime_relative() > ui_prog_until)
                        ui_user_sized = 1;      /* not our own change: the user sized or tiled the window */
''', "the user's resize (playing)")

patch(r'''                    screen_width  = ev.window.data1;    /* the next video opens at this size */
                    screen_height = ev.window.data2;
''', r'''                    screen_width  = ev.window.data1;    /* the next video opens at this size */
                    screen_height = ev.window.data2;
                    if (cfg_keep_window && !is_full_screen && av_gettime_relative() > ui_prog_until)
                        ui_user_sized = 1;
''', "the user's resize (idle screen)")

patch(r'''    SDL_SetWindowSize(window, nw, nh);
}''', r'''    ui_prog_until = av_gettime_relative() + 1500000;
    SDL_SetWindowSize(window, nw, nh);
}''', "our own resize in the aspect tick")

patch(r'''    is_full_screen = !is_full_screen;
    SDL_SetWindowFullscreen(window, is_full_screen ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0);''',
      r'''    is_full_screen = !is_full_screen;
    ui_prog_until = av_gettime_relative() + 2000000;     /* the size changes of going in and out are ours */
    SDL_SetWindowFullscreen(window, is_full_screen ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0);''', "full screen changes are ours")

# ============================================================ the Preferences row
patch(r'''#define UI_PREF_ROWS 8''', r'''#define UI_PREF_ROWS 9''', "a ninth row")

patch(r'''    "Bar color", "Remember volume", "Quit when the queue ends", "Mouse wheel"
};''', r'''    "Bar color", "Remember volume", "Quit when the queue ends", "Mouse wheel", "Remember window"
};''', "row name")

patch(r'''    case 6: snprintf(out, size, "%s", cfg_quit_when_done ? "On" : "Off"); break;
    default: snprintf(out, size, "%s", cfg_wheel''', r'''    case 6: snprintf(out, size, "%s", cfg_quit_when_done ? "On" : "Off"); break;
    case 8: snprintf(out, size, "%s", cfg_keep_window ? "On" : "Off"); break;
    default: snprintf(out, size, "%s", cfg_wheel''', "row value")

patch(r'''        *sel = (row == 3 ? cfg_fullscreen : row == 5 ? cfg_remember_volume : cfg_quit_when_done) ? 1 : 0;''',
      r'''        *sel = (row == 3 ? cfg_fullscreen : row == 5 ? cfg_remember_volume : row == 8 ? cfg_keep_window : cfg_quit_when_done) ? 1 : 0;''',
      "row choices")

patch(r'''    case 6: cfg_quit_when_done = idx != 0; break;
    default: cfg_wheel = av_clip(idx, 0, 2); break;''', r'''    case 6: cfg_quit_when_done = idx != 0; break;
    case 8: cfg_keep_window = idx != 0; break;
    default: cfg_wheel = av_clip(idx, 0, 2); break;''', "row choose")

# ============================================================ separate sizes for song tiles and video tiles
patch(r'''/* Like ui_flow_quad, but with rounded corners (radius rr): the columns are crowded near the left and right edges, where the''',
      r'''/* The slot a tile sits in. While a video plays the slots are big; a song tile keeps the smaller size it has in a row of songs */
static double ui_flow_slot(int i, double B, double W, double H)
{
    double small = FFMIN(W * 0.30, H * 0.44);

    if (ui_flow_vmode && i != q_pos && ui_cov_aspect(q_items[i]) <= 0.0 && small < B)
        return small;
    return B;
}

/* Like ui_flow_quad, but with rounded corners (radius rr): the columns are crowded near the left and right edges, where the''',
      "slot size helper")

patch(r'''            s = B * sc;
            tl[e] =''', r'''            s = ui_flow_slot(i, B, W, H) * sc;
            tl[e] =''', "song tiles are smaller")

patch(r'''            ui_flow_fit(i0, (int)B, (int)B, &pw, &h0);
            ui_flow_fit(i1, (int)B, (int)B, &pw, &h1);''', r'''            ui_flow_fit(i0, (int)ui_flow_slot(i0, B, W, H), (int)ui_flow_slot(i0, B, W, H), &pw, &h0);
            ui_flow_fit(i1, (int)ui_flow_slot(i1, B, W, H), (int)ui_flow_slot(i1, B, W, H), &pw, &h1);''', "label height follows the slot")

# ============================================================ always on top
patch(r'''static void ui_titlebar_draw(VideoState *is);

/* Seeking with the keys or the wheel:''', r'''static void ui_titlebar_draw(VideoState *is);

static int ui_on_top = 0;               /* 1 = the window stays above the others */

static void ui_toggle_on_top(void)
{
#if SDL_VERSION_ATLEAST(2, 0, 16)
    if (!window)
        return;
    ui_on_top = !ui_on_top;
    SDL_SetWindowAlwaysOnTop(window, ui_on_top ? SDL_TRUE : SDL_FALSE);
    ui_wake();                          /* the title bar shows, with its dot */
#endif
}

/* Seeking with the keys or the wheel:''', "always on top")

patch(r'''            case SDLK_t:
                stream_cycle_channel(cur_stream, AVMEDIA_TYPE_SUBTITLE);
                break;''', r'''            case SDLK_o:                /* on top of the other windows, or not */
                ui_toggle_on_top();
                break;
            case SDLK_t:
                stream_cycle_channel(cur_stream, AVMEDIA_TYPE_SUBTITLE);
                break;''', "key O")

patch(r'''    if (info.subsystem != SDL_SYSWM_X11) {
        av_log(NULL, AV_LOG_WARNING, "ffplay-custom: the window menu is only available on X11 sessions\n");
        return;
    }''', r'''    if (info.subsystem != SDL_SYSWM_X11) {      /* no window manager menu to ask for: the one thing it would give us here */
        ui_toggle_on_top();
        return;
    }''', "right click without the window menu")

patch(r'''    if (is && q_pos >= 0 && q_pos < q_count)    /* the name of what plays, in the middle */''',
      r'''    if (ui_on_top)                              /* a small dot: the window stays on top */
        ui_fan(cx2 - UI_TB_BTN / 2 - 6, cy, 3, 0, 6.28318531, 16, av_clip(cfg_bar_r + 60, 0, 255),
               av_clip(cfg_bar_g + 60, 0, 255), av_clip(cfg_bar_b + 60, 0, 255), 230);
    if (is && q_pos >= 0 && q_pos < q_count)    /* the name of what plays, in the middle */''', "dot in the title bar")

# ============================================================ the previews on the bar
patch(r'''/* A small label above the seek bar: the time under the mouse (or where you are dragging to),''',
      r'''/* Start the previews of the stream that plays, once it has played for a moment (a second reader should not compete with the opening) */
static void ui_th_tick(VideoState *is)
{
    static int next_id = 0;
    double pos, dur;
    int cw, ch, tw, th;

    if (!UI_THUMBS || is->ui_thumb_id || !is->ic)
        return;
    pos = get_master_clock(is);
    if (isnan(pos) || pos < 1.5)
        return;
    dur = is->ic->duration / (double)AV_TIME_BASE;
    if (!is->video_st || (is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC) || dur < 8.0 || !is->filename ||
        strstr(is->filename, "://") || !is->video_st->codecpar->width || !is->video_st->codecpar->height) {
        is->ui_thumb_id = -1;                   /* songs, short clips and streams get none */
        ui_th_stop();
        return;
    }
    cw = is->video_st->codecpar->width;
    ch = is->video_st->codecpar->height;
    tw = 192;
    th = (int)((double)ch * tw / cw);
    if (th > 108) {
        th = 108;
        tw = (int)((double)cw * th / ch);
    }
    tw = FFMAX(tw & ~1, 16);
    th = FFMAX(th & ~1, 16);
    ui_th_stop();                               /* the ones of the item before */
    is->ui_thumb_id = ++next_id;
    ui_th.id = is->ui_thumb_id;
    ui_th.n = av_clip((int)(dur / 3.0), 40, UI_TH_MAX);
    ui_th.w = tw;
    ui_th.h = th;
    ui_th.dur = dur;
    ui_th.start = is->ic->start_time != AV_NOPTS_VALUE ? is->ic->start_time : 0;
    ui_th.file = av_strdup(is->filename);
    if (!ui_th.file || !(ui_th.thread = SDL_CreateThread(ui_th_run, "seek previews", NULL))) {
        ui_th_stop();
        is->ui_thumb_id = -1;
    }
}

/* The preview for the fraction f of the video, above the time label (its top is at ybox), centered on cx. It takes the nearest
   one that is ready, so it never waits; a few more are ready every moment */
static void ui_th_draw(VideoState *is, double f, int cx, int ybox)
{
    int n = ui_th.n, idx, d, found = -1;
    SDL_Rect r, sh;
    UiThumb *t;
    double sc;

    if (!UI_THUMBS || ui_th.id <= 0 || ui_th.id != is->ui_thumb_id || n <= 0 || is->width < 380)
        return;
    idx = av_clip((int)(f * n), 0, n - 1);
    for (d = 0; d < n && found < 0; d++) {
        if (idx - d >= 0 && __atomic_load_n(&ui_th.t[idx - d].ready, __ATOMIC_ACQUIRE))
            found = idx - d;
        else if (idx + d < n && __atomic_load_n(&ui_th.t[idx + d].ready, __ATOMIC_ACQUIRE))
            found = idx + d;
    }
    if (found < 0)
        return;
    t = &ui_th.t[found];
    if (!t->tex) {
        t->tex = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STATIC, ui_th.w, ui_th.h);
        if (!t->tex)
            return;
        SDL_UpdateTexture(t->tex, NULL, t->rgba, ui_th.w * 4);
        SDL_SetTextureBlendMode(t->tex, SDL_BLENDMODE_NONE);
    }
    sc = is->width >= 1400 ? 1.5 : is->width >= 900 ? 1.25 : 1.0;
    r.w = (int)(ui_th.w * sc);
    r.h = (int)(ui_th.h * sc);
    r.x = av_clip(cx - r.w / 2, 8, FFMAX(is->width - r.w - 8, 8));
    r.y = ybox - 6 - r.h;
    if (r.y < 34)
        return;                                 /* no room above the bar in a small window */
    sh.x = r.x - 3;
    sh.y = r.y - 3;
    sh.w = r.w + 6;
    sh.h = r.h + 6;
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 90);
    SDL_RenderFillRect(renderer, &sh);
    SDL_RenderCopy(renderer, t->tex, NULL, &r);
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 60);
    SDL_RenderDrawRect(renderer, &r);
}

/* A small label above the seek bar: the time under the mouse (or where you are dragging to),''', "preview functions")

patch(r'''    box.y = sk->y - 16 - box.h;
    ui_label_s(box.x + 14, box.y + box.h / 2, text, 16, 245, 245, 245, 255);
}''', r'''    box.y = sk->y - 16 - box.h;
    ui_th_draw(is, f, cx, box.y);
    ui_label_s(box.x + 14, box.y + box.h / 2, text, 16, 245, 245, 245, 255);
}''', "preview above the time")

patch(r'''        ui_ks_tick(is);
''', r'''        ui_ks_tick(is);
        ui_th_tick(is);
''', "previews start in the loop")

patch(r'''    ui_aspect_due = 0;
''', r'''    ui_aspect_due = 0;
    if (cfg_keep_window && ui_user_sized && av_gettime_relative() < ui_prog_until)
        return;                                 /* our own size change (the saved window, a new item): the size stays as it is */
''', "no snapping of our own sizes")

open(path, "w").write(src)
print("Patched fftools/ffplay.c")
