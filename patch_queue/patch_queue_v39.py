#!/usr/bin/env python3
# Update 39 for ffplay-custom (on top of patch_queue_v38.py).
#   * Seeking is ffplay's own again: the Left/Right keys jump 10 s (or -seek_interval), the seek is sent at once from the clock with
#     the direction that stock ffplay gives it, and it lands on the key frame (no exact landing, no held-key stepping). The bar
#     follows the clock. The "Seek step" preference and seek_seconds in settings.conf are gone. The live frames when the mouse
#     is on the seek bar (the tooltip) and while the bar is dragged stay.
#   * Tiled view:
#       - a video tile plays (at the video's own frame rate, picture only) while the mouse rests on it, after a short pause. The
#         tile that plays in the player keeps playing as before. Only the tile under the mouse is decoded, so it stays light.
#       - the tile under the mouse brightens, like the one that plays.
#       - music tiles sit closer together.
#       - rows that are not in focus start at the far left (the first video in the middle no longer pulls the lower rows with it).
#       - titles are trimmed: (Official Music Video), [1080P HD], (Audio), (Lyrics) and the like are left out, also in the search.
#       - right-click on a tile: Play, Play next, Add to queue, Remove from queue.
#       - a two finger swipe down closes the view (animated, like Esc); up and down in the view no longer move tiles (the arrow keys do).
#   * Round two: no quiet gap or preview picture while seeking, the wheel seeks like the keys; the view a pause opens scrolls, swipes
#     and has the tile menu; each tile has its own brightness slot; rows at the far left dim by where they really are; the SMS promo
#     tails and the noise words are also left out of the queue panel and title bar.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v38.py. Writes the file only if every edit matches.
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
    """Replace everything from `start` up to (not including) `end`."""
    global src
    if src.count(start) != 1 or src.count(end) != 1:
        print("FAILED: %s markers matched %d and %d times" % (name, src.count(start), src.count(end)))
        fails.append(name)
        return
    i = src.index(start)
    j = src.index(end)
    if j < i:
        print("FAILED: %s markers are in the wrong order" % name)
        fails.append(name)
        return
    src = src[:i] + new + src[j:]
    print("ok: " + name)


if "ui_pv_request" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_tv_swipe_open" not in src:
    print("Apply patch_queue_v38.py first. Nothing written.")
    sys.exit(1)

# ================================================================ seeking: ffplay's own
patch("exact landing off", r'''#define UI_PRECISE_SEEK 1                /* 0 = seek to the nearest key frame, as before */''',
      r'''#define UI_PRECISE_SEEK 0                /* 0 = seek to the nearest key frame, as ffplay does (v39) */''')

patch("seek like ffplay", r'''        if (ui_ks_want || is->seek_req || is->prec_v || is->prec_a || av_gettime_relative() - ui_ks_issued < 200000) {
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
        is->force_refresh = 1;''', r'''        pos = get_master_clock(is);             /* v39: exactly what ffplay does */
        if (isnan(pos))
            pos = (double)is->seek_pos / AV_TIME_BASE;
        pos += incr;
        if (is->ic->start_time != AV_NOPTS_VALUE && pos < is->ic->start_time / (double)AV_TIME_BASE)
            pos = is->ic->start_time / (double)AV_TIME_BASE;
        stream_seek(is, (int64_t)(pos * AV_TIME_BASE), (int64_t)(incr * AV_TIME_BASE), 0);
        is->force_refresh = 1;''')

patch("left key", r'''            case SDLK_LEFT:
                incr = -cfg_seek;
                goto do_seek;''', r'''            case SDLK_LEFT:
                incr = seek_interval ? -seek_interval : -10.0;
                goto do_seek;''')
patch("right key", r'''            case SDLK_RIGHT:
                incr = cfg_seek;
                goto do_seek;''', r'''            case SDLK_RIGHT:
                incr = seek_interval ? seek_interval : 10.0;
                goto do_seek;''')

patch("seek step out of the template", r'''    "# Seconds the Left/Right arrow keys jump\n"
    "seek_seconds = 2\n"
    "\n"
''', "")
patch("seek step out of the file", r'''    fprintf(f, "# Seconds the Left/Right arrow keys jump\nseek_seconds = %g\n\n", cfg_seek);
''', "")

# the Seek step row leaves Preferences: the rows below it move up by one (the functions that use the row numbers skip the old row 0)
patch("preference rows", r'''#define UI_PREF_ROWS 8''', r'''#define UI_PREF_ROWS 7''')
patch("preference names", r'''    "Seek step", "Volume step", "Hide bars after", "Start fullscreen",''', r'''    "Volume step", "Hide bars after", "Start fullscreen",''')
patch("preference icons", r'''{ UI_IC_SKIP, UI_IC_VOLUME, UI_IC_EYE, UI_IC_EXPAND, UI_IC_DROP,''', r'''{ UI_IC_VOLUME, UI_IC_EYE, UI_IC_EXPAND, UI_IC_DROP,''')
patch("preference arrows", r'''    return row == 0 || row == 1 || row == 2 || row == 4 || row == 7;''', r'''    return row == 0 || row == 1 || row == 3 || row == 6;''')
patch("preference color row", r'''            if (i == 4) {''', r'''            if (i == 3) {''')
patch("preference value row", r'''    int i;

    switch (row) {
    case 0: snprintf(out, size, "%g s", cfg_seek); break;''', r'''    int i;

    row++;                                      /* v39: the Seek step row is gone, the numbers below keep their old meaning */
    switch (row) {
    case 0: snprintf(out, size, "%g s", cfg_seek); break;''')
patch("preference choices row", r'''    *sel = -1;
    switch (row) {
    case 0:
        for (i = 0; i < 9; i++) {
            snprintf(store[i], 20, "%gs", ui_seek_choices[i]);''', r'''    *sel = -1;
    row++;
    switch (row) {
    case 0:
        for (i = 0; i < 9; i++) {
            snprintf(store[i], 20, "%gs", ui_seek_choices[i]);''')
patch("preference choose row", r'''static void ui_pref_choose(int row, int idx)
{
    switch (row) {''', r'''static void ui_pref_choose(int row, int idx)
{
    row++;
    switch (row) {''')
patch("preference change row", r'''    int i;

    switch (row) {
    case 0: {
        static const double st[] = { 0.3, 0.5, 1, 2, 3, 5, 10, 15, 30 };''', r'''    int i;

    row++;
    switch (row) {
    case 0: {
        static const double st[] = { 0.3, 0.5, 1, 2, 3, 5, 10, 15, 30 };''')

# ================================================================ the tiled view: declarations
patch("declarations", r'''static int ui_tv_release(VideoState *is, int x, int y);''', r'''static int ui_tv_release(VideoState *is, int x, int y);
static int ui_tvc_open = 0;                             /* v39: the right-click menu of a tile is showing */
static void ui_pv_request(const char *path);            /* the tile that plays while the mouse rests on it */
static void ui_tv_hover_preview(int hs, int hi, int64_t now);
static void ui_tvc_draw(VideoState *is);
static int ui_tv_ctx_mouse(VideoState *is, SDL_Event *ev);''')

# ================================================================ titles without the noise
between("trimmed titles", r'''static void ui_tv_name(const char *s, char *out, size_t size)''', r'''static int ui_tv_lc(int c)''',
        r'''static int ui_tv_lc(int c);

/* v39: words that say nothing about the song, when they are all there is inside brackets: (Official Music Video), [1080P HD] ... */
static int ui_tv_noise_tok(const char *t)
{
    static const char * const w[] = { "official", "music", "video", "videos", "audio", "lyric", "lyrics", "lyrical", "visualizer",
                                      "visualiser", "hd", "hq", "uhd", "fhd", "mv", "explicit", "full", "hdr", "remastered",
                                      "remaster", "h264", "h265", "hevc", "x264", "x265", "av1", "vp9", "aac", "mp3", "opus", NULL };
    int i, n = 0;

    for (i = 0; w[i]; i++)
        if (!strcmp(t, w[i]))
            return 1;
    while (t[n] >= '0' && t[n] <= '9')
        n++;
    if (n > 0 && t[n]) {                        /* 1080p, 60fps, 4k, 128kbit, 44khz */
        const char *u = t + n;

        return !strcmp(u, "p") || !strcmp(u, "fps") || !strcmp(u, "k") || !strcmp(u, "kbit") || !strcmp(u, "kbps") ||
               !strcmp(u, "hz") || !strcmp(u, "khz") || !strcmp(u, "bit");
    }
    return 0;
}

static int ui_tv_word_c(int c)
{
    return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c >= 0x80;
}

static int ui_tv_noise_group(const char *s, int n)
{
    char tok[32];
    int i = 0, k, words = 0;

    while (i < n) {
        while (i < n && !ui_tv_word_c((unsigned char)s[i]))
            i++;
        if (i >= n)
            break;
        k = 0;
        while (i < n && ui_tv_word_c((unsigned char)s[i])) {
            if (k < 30)
                tok[k++] = (char)ui_tv_lc((unsigned char)s[i]);
            i++;
        }
        tok[k] = 0;
        if (!ui_tv_noise_tok(tok))
            return 0;
        words++;
    }
    return words > 0;
}

static void ui_tv_clean(char *s)
{
    static const char * const tail[] = { "official music video", "official lyric video", "official video", "official audio",
                                         "official visualizer", "music video", "lyric video", "lyrics video", NULL };
    char o[512];
    int n = (int)strlen(s), i = 0, k = 0, j, again;

    if (n <= 0 || n >= (int)sizeof(o) - 2)
        return;
    while (i < n) {
        char c = s[i];

        if (c == '(' || c == '[' || c == '{') {
            char close = c == '(' ? ')' : c == '[' ? ']' : '}';

            j = i + 1;
            while (j < n && s[j] != close)
                j++;
            if (j < n && ui_tv_noise_group(s + i + 1, j - i - 1)) {         /* the group goes, with the space before it */
                while (k > 0 && o[k - 1] == ' ')
                    k--;
                i = j + 1;
                while (i < n && s[i] == ' ')
                    i++;
                if (k > 0 && i < n)
                    o[k++] = ' ';
                continue;
            }
        }
        o[k++] = s[i++];
    }
    o[k] = 0;
    do {                                        /* the same words without brackets, at the end of the title */
        again = 0;
        while (k > 0 && (o[k - 1] == ' ' || o[k - 1] == '-' || o[k - 1] == '|' || o[k - 1] == '~' || o[k - 1] == ':' || o[k - 1] == '_'))
            o[--k] = 0;
        for (i = 0; tail[i]; i++) {
            int tl = (int)strlen(tail[i]), p = k - tl, q;

            if (p < 1 || (o[p - 1] != ' ' && o[p - 1] != '-'))
                continue;
            for (q = 0; q < tl && ui_tv_lc((unsigned char)o[p + q]) == tail[i][q]; q++)
                ;
            if (q == tl) {
                k = p;
                o[k] = 0;
                again = 1;
                break;
            }
        }
    } while (again);
    while (k > 0 && (o[k - 1] == ' ' || o[k - 1] == '-' || o[k - 1] == '|' || o[k - 1] == '~' || o[k - 1] == ':' || o[k - 1] == '_'))
        o[--k] = 0;
    if (k > 0)
        memcpy(s, o, k + 1);
}

static void ui_tv_name(const char *s, char *out, size_t size)
{
    const char *slash = strrchr(s, '/');
    char *dot, *open, keep[320];
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
    snprintf(keep, sizeof(keep), "%s", out);
    ui_tv_clean(out);
    if (!out[0])
        snprintf(out, size, "%s", keep);
}

''')

# ================================================================ the tile that plays under the mouse
patch("preview player", r'''static int ui_tv_is_playing(const char *path)
{''', r'''/* ---- v39: a video tile plays (picture only, at the video's own rate) while the mouse rests on it ----
   One thread decodes the one file that is wanted, scales it to at most 512 px and hands the newest picture over. Nothing else is
   decoded, so it stays light. It stops by itself when the view has not asked for a picture for 2 seconds. */
#define UI_PV_SIDE 512

typedef struct {
    SDL_Thread *th;
    SDL_mutex *mu;
    SDL_cond *cv;
    volatile int quit;
    volatile int gen;                           /* changes with every new request */
    char want[4096];                            /* the file that is wanted ("" = none) */
    char dead[4096];                            /* a file that could not be played: it is not tried again at once */
    uint8_t *pix;                               /* the newest picture (RGBA) */
    int w, h, fresh, cgen;                      /* its size; 1 = not yet in the texture; the request it belongs to */
    int64_t last_get;                           /* when the view last asked for it */
    SDL_Texture *tex;
    int tex_w, tex_h;
} UiPv;

static UiPv ui_pv;

static int ui_pv_gone(int gen)
{
    return ui_pv.quit || ui_pv.gen != gen;
}

/* Plays the file until it is not wanted any more. Returns 1 if the file could not be played. */
static int ui_pv_run(const char *path, int gen)
{
    AVFormatContext *ic = NULL;
    AVCodecContext *cc = NULL;
    const AVCodec *codec = NULL;
    AVFrame *fr = NULL;
    AVPacket *pkt = NULL;
    struct SwsContext *sws = NULL;
    AVDictionary *opts = NULL;
    uint8_t *buf = NULL;
    double tb, dar, last_pts = 0.0, pts0;
    int64_t wall0 = 0;
    int vs, tw, th, i, failed = 1, shown = 0, restarts = 0;

    av_dict_set(&opts, "probesize", "2000000", 0);
    av_dict_set(&opts, "analyzeduration", "1000000", 0);
    if (avformat_open_input(&ic, path, NULL, &opts) < 0) {
        av_dict_free(&opts);
        return 1;
    }
    av_dict_free(&opts);
    if (avformat_find_stream_info(ic, NULL) < 0)
        goto end;
    vs = av_find_best_stream(ic, AVMEDIA_TYPE_VIDEO, -1, -1, &codec, 0);
    if (vs < 0 || !codec || (ic->streams[vs]->disposition & AV_DISPOSITION_ATTACHED_PIC))
        goto end;
    cc = avcodec_alloc_context3(codec);
    if (!cc || avcodec_parameters_to_context(cc, ic->streams[vs]->codecpar) < 0)
        goto end;
    cc->thread_count = 2;
    cc->skip_loop_filter = AVDISCARD_ALL;       /* a small picture: the loop filter is not worth the time */
    cc->flags2 |= AV_CODEC_FLAG2_FAST;
    if (avcodec_open2(cc, codec, NULL) < 0)
        goto end;
    for (i = 0; i < (int)ic->nb_streams; i++)
        if (i != vs)
            ic->streams[i]->discard = AVDISCARD_ALL;
    if (cc->width <= 0 || cc->height <= 0)
        goto end;
    {
        AVRational sar = av_guess_sample_aspect_ratio(ic, ic->streams[vs], NULL);

        dar = (double)cc->width / cc->height * (sar.num > 0 && sar.den > 0 ? av_q2d(sar) : 1.0);
    }
    if (dar >= 1.0) {
        tw = UI_PV_SIDE;
        th = (int)(UI_PV_SIDE / dar);
    } else {
        th = UI_PV_SIDE;
        tw = (int)(UI_PV_SIDE * dar);
    }
    tw = FFMAX(tw & ~1, 2);
    th = FFMAX(th & ~1, 2);
    fr = av_frame_alloc();
    pkt = av_packet_alloc();
    buf = av_malloc((size_t)tw * th * 4);
    if (!fr || !pkt || !buf)
        goto end;
    tb = av_q2d(ic->streams[vs]->time_base);
    failed = 0;

    while (!ui_pv_gone(gen) && restarts < 4) {
        int ret;
        double dur = ic->duration > 0 ? ic->duration / (double)AV_TIME_BASE : 0.0;
        int64_t from = (dur > 12.0 ? (int64_t)(dur * 0.25 * AV_TIME_BASE) : 0) + (ic->start_time != AV_NOPTS_VALUE ? ic->start_time : 0);

        if (av_seek_frame(ic, -1, from, AVSEEK_FLAG_BACKWARD) < 0)
            av_seek_frame(ic, -1, 0, AVSEEK_FLAG_BACKWARD);
        avcodec_flush_buffers(cc);
        pts0 = -1.0;
        restarts++;
        for (;;) {
            if (ui_pv_gone(gen))
                break;
            if (av_gettime_relative() - ui_pv.last_get > 2000000)
                goto end;                       /* nobody is looking */
            ret = av_read_frame(ic, pkt);
            if (ret < 0)
                break;                          /* the end: from the start again */
            if (pkt->stream_index != vs) {
                av_packet_unref(pkt);
                continue;
            }
            ret = avcodec_send_packet(cc, pkt);
            av_packet_unref(pkt);
            if (ret < 0 && ret != AVERROR(EAGAIN))
                continue;
            while (!ui_pv_gone(gen) && avcodec_receive_frame(cc, fr) >= 0) {
                int64_t now = av_gettime_relative(), target;
                double pts = fr->best_effort_timestamp == AV_NOPTS_VALUE ? last_pts + 0.04 : fr->best_effort_timestamp * tb;
                uint8_t *dst[4] = { buf, NULL, NULL, NULL };
                int ls[4] = { tw * 4, 0, 0, 0 };

                last_pts = pts;
                if (pts0 < 0.0 || pts < pts0 - 0.5) {
                    pts0 = pts;
                    wall0 = now;
                }
                target = wall0 + (int64_t)((pts - pts0) * 1000000.0);
                if (now > target + 250000) {    /* behind: this picture is skipped, and the clock starts again if it is far behind */
                    if (now > target + 1000000) {
                        pts0 = pts;
                        wall0 = now;
                    }
                    av_frame_unref(fr);
                    continue;
                }
                while (!ui_pv_gone(gen) && (now = av_gettime_relative()) < target)
                    av_usleep((unsigned)FFMIN(target - now, 4000));
                if (ui_pv_gone(gen)) {
                    av_frame_unref(fr);
                    break;
                }
                sws = sws_getCachedContext(sws, fr->width, fr->height, (enum AVPixelFormat)fr->format, tw, th, AV_PIX_FMT_RGBA,
                                           SWS_FAST_BILINEAR, NULL, NULL, NULL);
                if (!sws) {
                    av_frame_unref(fr);
                    failed = 1;
                    goto end;
                }
                sws_scale(sws, (const uint8_t * const *)fr->data, fr->linesize, 0, fr->height, dst, ls);
                av_frame_unref(fr);
                SDL_LockMutex(ui_pv.mu);
                if (ui_pv.gen == gen) {
                    memcpy(ui_pv.pix, buf, (size_t)tw * th * 4);
                    ui_pv.w = tw;
                    ui_pv.h = th;
                    ui_pv.fresh = 1;
                    ui_pv.cgen = gen;
                }
                SDL_UnlockMutex(ui_pv.mu);
                shown = 1;
                restarts = 0;
            }
        }
    }
    if (!shown)
        failed = 1;
end:
    sws_freeContext(sws);
    av_free(buf);
    av_packet_free(&pkt);
    av_frame_free(&fr);
    avcodec_free_context(&cc);
    avformat_close_input(&ic);
    return failed;
}

static int ui_pv_thread(void *arg)
{
    char path[4096];
    int gen, failed;

    (void)arg;
    for (;;) {
        SDL_LockMutex(ui_pv.mu);
        while (!ui_pv.quit && !ui_pv.want[0])
            SDL_CondWait(ui_pv.cv, ui_pv.mu);
        if (ui_pv.quit) {
            SDL_UnlockMutex(ui_pv.mu);
            return 0;
        }
        snprintf(path, sizeof(path), "%s", ui_pv.want);
        gen = ui_pv.gen;
        SDL_UnlockMutex(ui_pv.mu);
        failed = ui_pv_run(path, gen);
        SDL_LockMutex(ui_pv.mu);
        if (ui_pv.gen == gen) {                 /* it ended by itself: wait for the next request */
            ui_pv.want[0] = 0;
            if (failed)
                snprintf(ui_pv.dead, sizeof(ui_pv.dead), "%s", path);
        }
        SDL_UnlockMutex(ui_pv.mu);
    }
}

/* path = the file to play, NULL = stop */
static void ui_pv_request(const char *path)
{
    if (!ui_pv.mu) {
        if (!path)
            return;
        ui_pv.mu = SDL_CreateMutex();
        ui_pv.cv = SDL_CreateCond();
        ui_pv.pix = av_malloc((size_t)UI_PV_SIDE * UI_PV_SIDE * 4);
        if (!ui_pv.mu || !ui_pv.cv || !ui_pv.pix)
            return;
        ui_pv.th = SDL_CreateThread(ui_pv_thread, "ffplay-custom preview", NULL);
        if (!ui_pv.th) {
            ui_pv.mu = NULL;                    /* no thread: no previews (a later try starts again) */
            return;
        }
        SDL_DetachThread(ui_pv.th);
    }
    SDL_LockMutex(ui_pv.mu);
    if (!path) {
        if (ui_pv.want[0]) {
            ui_pv.want[0] = 0;
            ui_pv.gen++;
        }
    } else if (strcmp(path, ui_pv.want) && strcmp(path, ui_pv.dead)) {
        snprintf(ui_pv.want, sizeof(ui_pv.want), "%s", path);
        ui_pv.dead[0] = 0;
        ui_pv.gen++;
        ui_pv.fresh = 0;
        ui_pv.last_get = av_gettime_relative();
        SDL_CondSignal(ui_pv.cv);
    }
    SDL_UnlockMutex(ui_pv.mu);
}

/* The texture of the picture that plays for this file, or NULL if it is not the one that is wanted (or has no picture yet) */
static SDL_Texture *ui_pv_get(const char *path, int *w, int *h)
{
    SDL_Texture *t = NULL;

    if (!ui_pv.mu || !path)
        return NULL;
    SDL_LockMutex(ui_pv.mu);
    if (ui_pv.want[0] && !strcmp(path, ui_pv.want)) {
        ui_pv.last_get = av_gettime_relative();
        if (ui_pv.cgen == ui_pv.gen && ui_pv.w > 0 && ui_pv.h > 0) {
            if (!ui_pv.tex || ui_pv.tex_w != ui_pv.w || ui_pv.tex_h != ui_pv.h) {
                if (ui_pv.tex)
                    SDL_DestroyTexture(ui_pv.tex);
                ui_pv.tex = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STREAMING, ui_pv.w, ui_pv.h);
                ui_pv.tex_w = ui_pv.w;
                ui_pv.tex_h = ui_pv.h;
                ui_pv.fresh = 1;
                if (ui_pv.tex)
                    SDL_SetTextureBlendMode(ui_pv.tex, SDL_BLENDMODE_BLEND);
            }
            if (ui_pv.tex && ui_pv.fresh) {
                SDL_UpdateTexture(ui_pv.tex, NULL, ui_pv.pix, ui_pv.w * 4);
                ui_pv.fresh = 0;
            }
            if (ui_pv.tex) {
                t = ui_pv.tex;
                *w = ui_pv.w;
                *h = ui_pv.h;
            }
        }
    }
    SDL_UnlockMutex(ui_pv.mu);
    return t;
}

static int ui_tv_is_playing(const char *path)
{''')

# ---------------------------------------------------------------- the rows: far left start, preview, brighter under the mouse
patch("picture of a tile that plays", r'''        asp = (play && vm && ui_live_ok && ui_live_rect.h > 0) ? (double)ui_live_rect.w / ui_live_rect.h : ui_cov_aspect(path);''',
      r'''        asp = (play && vm && ui_live_ok && ui_live_rect.h > 0) ? (double)ui_live_rect.w / ui_live_rect.h : ui_cov_aspect(path);
        ptex = play ? NULL : ui_pv_get(path, &pw, &ph);         /* v39: the picture that plays under the mouse */
        if (ptex && asp <= 0.0)
            asp = (double)pw / ph;''')

patch("preview variables", r'''        const char *path = ui_tv_row_path(R, c);
''', r'''        const char *path = ui_tv_row_path(R, c);
        SDL_Texture *ptex;
        int pw = 0, ph = 0;
''')

patch("rows start at the far left", r'''        x = R->cx + dc * pitch + (dc < 0 ? -1.0 : 1.0) * FFMIN(fabs(dc), 1.0) * pitch * 0.12;''',
      r'''        x = R->cx + dc * pitch + (dc < 0 ? -1.0 : 1.0) * FFMIN(fabs(dc), 1.0) * pitch * 0.12;
        if (R->sec < 0 && R->rowd > 0.0) {      /* v39: the rows that are not in focus start at the far left, until the focus has gone far enough */
            double pmax = W / 2.0 / pitch - 0.6;

            if (pmax > 0.0 && R->pos < pmax)
                x -= (pmax - R->pos) * pitch * FFMIN(R->rowd, 1.0);
        }''')

patch("brighter under the mouse", r'''        ui_tv_lift[ti] = lf;
        nw += (int)(nw * 0.05 * lf);''', r'''        ui_tv_lift[ti] = lf;
        al += (int)((255 - al) * lf);           /* v39: the tile under the mouse brightens like the one that plays */
        md += (int)((255 - md) * lf);
        nw += (int)(nw * 0.05 * lf);''')

patch("draw the preview", r'''        } else {
            ui_tv_tile(path, &tile, al, md);
        }
        ui_tv_name(path, name, sizeof(name));''', r'''        } else if (ptex) {                      /* it plays under the mouse */
            ui_flow_quad_round(ptex, &tile, al, md, 0.0, FFMIN(tile.w, tile.h) / 11);
            ui_tv_moving = 1;
        } else {
            ui_tv_tile(path, &tile, al, md);
        }
        ui_tv_name(path, name, sizeof(name));''')

patch("title brightness", r'''(int)(al * (d < 0.6 ? 1.0 : 0.75)));''', r'''(int)(al * (d < 0.6 ? 1.0 : 0.75 + 0.25 * lf)));''')

patch("packed rows", r'''            row.sw = (int)(sh * 1.75);
            row.sh = (int)sh;''', r'''            row.sw = (int)(sh * (ui_tv_audio ? 1.22 : 1.75));        /* v39: music tiles sit closer */
            row.sh = (int)sh;''')
patch("packed music section", r'''            row.sw = (int)(sh * 1.75);
            row.sh = sh;''', r'''            row.sw = (int)(sh * (s == 1 ? 1.22 : 1.75));            /* v39: music tiles sit closer */
            row.sh = sh;''')

patch("hover and preview in the draw", r'''        if (!ui_tv_hit_at(ui_hov_x, ui_hov_y, &hs, &hi))
            hs = -2;
    ui_tvh_n = 0;''', r'''        if (!ui_tv_hit_at(ui_hov_x, ui_hov_y, &hs, &hi))
            hs = -2;
    if (ui_tvc_open)
        hs = -2;                                /* v39: no tile is under the mouse while its menu is open */
    ui_tv_hover_preview(hs, hi, now);
    ui_tvh_n = 0;''')

patch("menu in the draw", r'''    SDL_RenderSetClipRect(renderer, NULL);
}

/* ---- the mouse ---- */''', r'''    if (ui_tvc_open)
        ui_tvc_draw(is);
    SDL_RenderSetClipRect(renderer, NULL);
}

/* ---- the mouse ---- */''')

patch("preview stops when the view opens", r'''    ui_tv_born = now;
    ui_tv_press = -1;
    ui_tv_drag = 0;
}''', r'''    ui_tv_born = now;
    ui_tv_press = -1;
    ui_tv_drag = 0;
    ui_tvc_open = 0;
    ui_pv_request(NULL);
}''')

patch("preview stops when the view closes", r'''    if (ui_flow_video(is) && ui_vflow) {
        ui_vflow_auto = 0;
        ui_vflow_set(is, 0);                    /* the video grows back */''', r'''    ui_tvc_open = 0;
    ui_pv_request(NULL);
    if (ui_flow_video(is) && ui_vflow) {
        ui_vflow_auto = 0;
        ui_vflow_set(is, 0);                    /* the video grows back */''')

patch("a key closes the menu", r'''        return 0;
    ui_wake();
    switch (k) {
    case SDLK_ESCAPE:                           /* Esc closes the search, Esc again closes the view */''', r'''        return 0;
    ui_wake();
    if (ui_tvc_open) {                          /* v39: the menu of a tile: any key closes it, Esc is used up by that */
        ui_tvc_open = 0;
        if (k == SDLK_ESCAPE)
            return 1;
    }
    switch (k) {
    case SDLK_ESCAPE:                           /* Esc closes the search, Esc again closes the view */''')

# ---------------------------------------------------------------- a swipe down closes the view
between("swipe down closes", r'''/* Up and down: one row (or section) for each swipe */''', r'''/* Fingers up (the Navigation choice) with the view closed''', r'''/* Fingers down: the view closes (animated, like Esc). Up and down no longer move tiles: the arrow keys do. */
static void ui_tv_swipe_y(VideoState *is, double ay)
{
    static double acc = 0.0;
    static int64_t last = 0;
    static int lock = 0;
    int64_t now = av_gettime_relative();

    if (now < ui_tv_gest_until)
        return;
    if (now - last > 250000) {
        acc = 0.0;
        lock = 0;
    }
    last = now;
    acc += ay;
    if (!lock && acc * UI_TV_UP_SIGN <= -1.2) {
        lock = 1;
        ui_tv_gest_until = now + 700000;
        ui_tv_exit(is);
        is->force_refresh = 1;
    }
}

''')

# ---------------------------------------------------------------- the right-click menu of a tile, and the preview that follows the mouse
patch("tile menu", r'''static void ui_flow_draw(VideoState *is)
{
    enum { NEQ = 72 };''', r'''/* ---- v39: what is under the mouse in the view: the tile that plays, and the right-click menu ---- */
static const char *ui_tv_item_path(int sec, int item)
{
    if (item < 0)
        return NULL;
    if (sec == -1)
        return item < q_count ? q_items[item] : NULL;
    if (sec >= 0 && sec < 3 && item < ui_tv_sec[sec].n)
        return ui_tv_sec[sec].h[item].path;
    return NULL;
}

static int ui_tv_ext_is(const char *path, int kind)
{
    const char *dot = strrchr(path, '.'), *slash = strrchr(path, '/');
    int i;

    if (!dot || (slash && dot < slash))
        return 0;
    for (i = 0; ui_tv_ext[kind][i]; i++)
        if (!av_strcasecmp(dot + 1, ui_tv_ext[kind][i]))
            return 1;
    return 0;
}

/* The video under the mouse starts to play in its tile after a short rest, and stops a moment after the mouse has left it */
static void ui_tv_hover_preview(int hs, int hi, int64_t now)
{
    static char dw[4096];
    static int64_t since = 0, lost = 0;
    const char *p = hs >= -1 ? ui_tv_item_path(hs, hi) : NULL;

    if (p && ui_tv_ext_is(p, 1) && !ui_tv_is_playing(p)) {
        lost = 0;
        if (strcmp(p, dw)) {
            snprintf(dw, sizeof(dw), "%s", p);
            since = now;
        }
        if (now - since >= 300000)
            ui_pv_request(p);
        else
            ui_tv_moving = 1;
    } else {
        dw[0] = 0;
        if (!lost)
            lost = now;
        if (now - lost > 400000)
            ui_pv_request(NULL);
    }
}

#define UI_TVC_ROW 38
static int ui_tvc_x = 0, ui_tvc_y = 0, ui_tvc_hover = -1, ui_tvc_n = 0, ui_tvc_act[4];
static char ui_tvc_path[4096];
static const char * const ui_tvc_label[4] = { "Play", "Play next", "Add to queue", "Remove from queue" };

static int ui_tv_qindex(const char *path)       /* the place of a file in the queue (the same file under another name counts), or -1 */
{
    int i, idx = -1;
    char *rp;

    for (i = 0; i < q_count && idx < 0; i++)
        if (!strcmp(q_items[i], path))
            idx = i;
    if (idx >= 0)
        return idx;
    rp = realpath(path, NULL);
    for (i = 0; rp && i < q_count && idx < 0; i++) {
        char *rq = realpath(q_items[i], NULL);

        if (rq && !strcmp(rq, rp))
            idx = i;
        free(rq);
    }
    free(rp);
    return idx;
}

static SDL_Rect ui_tvc_rect(int ww, int wh)
{
    SDL_Rect r;
    int i, w = 0;

    for (i = 0; i < ui_tvc_n; i++)
        w = FFMAX(w, ui_text_width(ui_tvc_label[ui_tvc_act[i]], 18));
    r.w = w + 56;
    r.h = ui_tvc_n * UI_TVC_ROW + 16;
    r.x = av_clip(ui_tvc_x, 8, FFMAX(ww - r.w - 8, 8));
    r.y = av_clip(ui_tvc_y, 8, FFMAX(wh - r.h - 8, 8));
    return r;
}

static int ui_tvc_hit(const SDL_Rect *r, int x, int y)
{
    if (x < r->x || x >= r->x + r->w || y < r->y + 8 || y >= r->y + 8 + ui_tvc_n * UI_TVC_ROW)
        return -1;
    return (y - r->y - 8) / UI_TVC_ROW;
}

static void ui_tvc_draw(VideoState *is)
{
    SDL_Rect r = ui_tvc_rect(is->width, is->height);
    int i, ry;

    ui_glass(&r, 16);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    for (i = 0; i < ui_tvc_n; i++) {
        ry = r.y + 8 + i * UI_TVC_ROW;
        ui_label(r.x + 30, ry + UI_TVC_ROW / 2, ui_tvc_label[ui_tvc_act[i]], 18, 240, 240, 240, i == ui_tvc_hover ? 255 : 205);
        if (i == ui_tvc_hover) {
            SDL_Rect dot = { r.x + 13, ry + UI_TVC_ROW / 2 - 3, 6, 6 };

            SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                                   av_clip(cfg_bar_b + 40, 0, 255), 235);
            ui_pill(&dot);
        }
    }
    ui_tv_moving = 1;
}

static void ui_tvc_do(VideoState *is, int act)
{
    char path[4096];
    int idx;

    snprintf(path, sizeof(path), "%s", ui_tvc_path);
    ui_tvc_open = 0;
    ui_tvc_hover = -1;
    switch (act) {
    case 0:                                     /* Play */
        ui_tv_play(is, path);
        break;
    case 1:                                     /* Play next: right after the item that plays */
        idx = ui_tv_qindex(path);
        if (idx < 0) {
            queue_add(path);
            idx = ui_tv_qindex(path);
        }
        if (idx >= 0 && idx != q_pos && idx != q_pos + 1)
            queue_move(idx, idx > q_pos ? q_pos + 1 : q_pos);
        break;
    case 2:                                     /* Add to queue */
        if (ui_tv_qindex(path) < 0)
            queue_add(path);
        break;
    default:                                    /* Remove from queue */
        idx = ui_tv_qindex(path);
        if (idx >= 0 && idx != q_pos)
            queue_remove(idx);
        break;
    }
    if (ui_tv_q[0] && act != 0)
        ui_tv_search();                         /* "In this queue" follows what changed */
    ui_tv_moving = 1;
    is->force_refresh = 1;
}

/* The mouse, while the view is open: right-click on a tile opens its menu, and the menu owns the mouse until it closes */
static int ui_tv_ctx_mouse(VideoState *is, SDL_Event *ev)
{
    SDL_Rect r;
    int x, y, hit, sec, item, qi, n = 0;
    const char *p;

    if (ev->type != SDL_MOUSEBUTTONDOWN && ev->type != SDL_MOUSEMOTION)
        return 0;
    if (!ui_tv_cap(is)) {
        ui_tvc_open = 0;
        return 0;
    }
    x = ev->type == SDL_MOUSEMOTION ? ev->motion.x : ev->button.x;
    y = ev->type == SDL_MOUSEMOTION ? ev->motion.y : ev->button.y;
    if (ui_tvc_open) {
        r = ui_tvc_rect(is->width, is->height);
        hit = ui_tvc_hit(&r, x, y);
        if (ev->type == SDL_MOUSEMOTION)
            ui_tvc_hover = hit;
        else if (ev->button.button == SDL_BUTTON_LEFT && hit >= 0)
            ui_tvc_do(is, ui_tvc_act[hit]);
        else
            ui_tvc_open = 0;                    /* a click anywhere else closes it */
        ui_wake();
        is->force_refresh = 1;
        return 1;
    }
    if (ev->type != SDL_MOUSEBUTTONDOWN || ev->button.button != SDL_BUTTON_RIGHT || ui_tv_drag)
        return 0;
    if (!ui_tv_hit_at(x, y, &sec, &item) || !(p = ui_tv_item_path(sec, item)))
        return 0;
    snprintf(ui_tvc_path, sizeof(ui_tvc_path), "%s", p);
    qi = ui_tv_qindex(p);
    ui_tvc_act[n++] = 0;                        /* Play */
    if (qi < 0 || (qi != q_pos && qi != q_pos + 1))
        ui_tvc_act[n++] = 1;                    /* Play next */
    if (qi < 0)
        ui_tvc_act[n++] = 2;                    /* Add to queue */
    else if (qi != q_pos)
        ui_tvc_act[n++] = 3;                    /* Remove from queue */
    ui_tvc_n = n;
    ui_tvc_x = x;
    ui_tvc_y = y;
    ui_tvc_hover = -1;
    ui_tvc_open = 1;
    ui_pv_request(NULL);
    ui_wake();
    is->force_refresh = 1;
    return 1;
}

static void ui_flow_draw(VideoState *is)
{
    enum { NEQ = 72 };''')

patch("menu gets the mouse", r'''    if (ui_prefs_open)
        return ui_prefs_mouse(is, ev);

    ui_menu_last_move''', r'''    if (ui_prefs_open)
        return ui_prefs_mouse(is, ev);
    if (ui_tv_ctx_mouse(is, ev))                /* v39: right-click on a tile of the tiled view */
        return 1;

    ui_menu_last_move''')

# ================================================================ round two (this chat): what the first pass left out
# ---- seeking: nothing of ours left between the key and ffplay
patch("no ducking while seeking", r'''        {                                       /* quiet while seeking: the cut and restarted sound would scratch */
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
        }''', r'''        vol = (int)(is->audio_volume * is->xf_gain * ui_sleep_gain + 0.5f);        /* v39: no quiet gap around a seek, as in ffplay */''')

patch("no preview picture while seeking", r'''        if (!ui_scrub_draw(is, &rect))          /* while seeking: the nearest preview first, the real picture when it is there */
            SDL_RenderCopyEx(renderer, is->vid_texture, NULL, &rect, 0, NULL, vp->flip_v ? SDL_FLIP_VERTICAL : 0);''',
      r'''        SDL_RenderCopyEx(renderer, is->vid_texture, NULL, &rect, 0, NULL, vp->flip_v ? SDL_FLIP_VERTICAL : 0);''')

patch("wheel seeks like the keys", r'''        ui_seek_relative(is, steps * cfg_seek);''',
      r'''        ui_seek_relative(is, steps * (seek_interval ? seek_interval : 10.0));        /* v39: the same step as the arrow keys */''')

patch("old seek_seconds line is ignored", r'''            cfg_seek = av_clipd(d, 0.1, 600.0);''', r'''            (void)d;                    /* v39: the seek step is ffplay's own now; an old line is ignored */''')

patch("bar follows the seek target", r'''            pos = (!seek_by_bytes && is->seek_pos) ? is->seek_pos / (double)AV_TIME_BASE : ui_last_pos;''',
      r'''            pos = !seek_by_bytes ? is->seek_pos / (double)AV_TIME_BASE : ui_last_pos;      /* v39: also a seek to the very start */''')

# ---- the tile under the mouse: its own lift slot (two tiles used to share one slot, so the brightness fought itself)
patch("lift slots", r'''static double ui_tv_lift[64];''', r'''static double ui_tv_lift[4096];''')
patch("lift slot of a tile", r'''        ti = (R->sec < 0 ? item : c + 20 * (R->sec + 1)) & 63;''',
      r'''        ti = (int)(((R->sec + 1) * 1031 + item) % 4093);        /* v39: one slot for each tile */''')

# ---- the rows that are not in focus: dim and small by where they really are, and drawn far enough along the row
patch("far left: distance from where the tile really is", r'''        double dc = c - R->pos, d = sqrt(dc * dc + (1.15 * R->rowd) * (1.15 * R->rowd));
''', r'''        double dc = c - R->pos, dce = dc, d;

        if (R->sec < 0 && R->rowd > 0.0) {      /* v39: the shift to the far left (see below) moves the tile, so its size and brightness follow */
            double pmax = W / 2.0 / pitch - 0.6;

            if (pmax > 0.0 && R->pos < pmax)
                dce -= (pmax - R->pos) * FFMIN(R->rowd, 1.0);
        }
        d = sqrt(dce * dce + (1.15 * R->rowd) * (1.15 * R->rowd));
''')
patch("far left: tiles to draw", r'''    k1 = FFMIN((int)ceil(R->pos) + K, R->count - 1);''', r'''    k1 = FFMIN((int)ceil(R->pos) + 2 * K, R->count - 1);     /* v39: a row that starts at the far left shows more tiles to the right */''')

# ---- a view opened by a pause: scrolling, swiping and the tile menu work there too
patch("sideways swipe with the view open", r'''        if (ui_tv_cap(is))
            ui_tv_swipe_x(is, ax);''', r'''        if (ui_tv_on(is))                       /* v39: also the view a pause opened */
            ui_tv_swipe_x(is, ax);''')
patch("up and down with the view open", r'''    zone = ui_wheel_zone(is);
    act = zone == 1 ? 0 : zone == 2 ? 1 : cfg_wheel;            /* 0 = seek, 1 = volume, 2 = navigation */
    if (act == 2 || (!zone && ui_tv_cap(is))) {                 /* with the view open, up and down belong to it */
        if (ui_tv_cap(is))
            ui_tv_swipe_y(is, ay);''', r'''    if (av_gettime_relative() < ui_tv_gest_until)
        return;                                 /* v39: the end of the swipe that opened or closed the view moves nothing */
    zone = ui_wheel_zone(is);
    act = zone == 1 ? 0 : zone == 2 ? 1 : cfg_wheel;            /* 0 = seek, 1 = volume, 2 = navigation */
    if (act == 2 || (!zone && ui_tv_on(is))) {                  /* with the view open, a swipe down closes it */
        if (ui_tv_on(is))
            ui_tv_swipe_y(is, ay);''')
patch("tile menu in a paused view", r'''    if (!ui_tv_cap(is)) {
        ui_tvc_open = 0;
        return 0;
    }''', r'''    if (!ui_tv_on(is)) {
        ui_tvc_open = 0;
        return 0;
    }''')

# ---- titles: the queue panel, the title bar and the tiles all use the same trimmed name; the "SMS ..." promos go too
patch("queue names are trimmed too", r'''        *open = 0;
    }
}

/* Cut a text so it fits in max_w pixels, ending with "...". s needs room for 4 more bytes. */''', r'''        *open = 0;
    }
    {                                           /* v39: (Official Music Video), [1080P HD] and the like are left out, as in the tiled view */
        char keep[320];

        snprintf(keep, sizeof(keep), "%s", out);
        ui_tv_clean(out);
        if (!out[0])
            snprintf(out, size, "%s", keep);
    }
}

/* Cut a text so it fits in max_w pixels, ending with "...". s needs room for 4 more bytes. */''')
patch("clean declared early", r'''/* Is this text (the inside of a bracket) only download or codec information, like 1080p_25fps_H264? */''',
      r'''static void ui_tv_clean(char *s);

/* Is this text (the inside of a bracket) only download or codec information, like 1080p_25fps_H264? */''')
patch("promo tails", r'''    if (n <= 0 || n >= (int)sizeof(o) - 2)
        return;
    while (i < n) {''', r'''    if (n <= 0 || n >= (int)sizeof(o) - 2)
        return;
    for (j = 3; j + 3 <= n; j++) {              /* a telephone company's promo at the end: "SMS 'SKIZA 123' to 811", "To subscribe to skiza..." */
        if (s[j - 1] != ' ')
            continue;
        if ((!av_strncasecmp(s + j, "sms", 3) && (j + 3 == n || s[j + 3] == ' ' || s[j + 3] == '\'' || s[j + 3] == '[')) ||
            !av_strncasecmp(s + j, "to subcribe", 11) || !av_strncasecmp(s + j, "to subscribe", 12)) {
            n = j;
            s[n] = 0;
            break;
        }
    }
    while (i < n) {''')

if fails:
    print("\n%d edit(s) did not match. Nothing written." % len(fails))
    sys.exit(1)
open(PATH, "w").write(src)
print("\nAll edits applied. Rebuild: make -j$(nproc)")
