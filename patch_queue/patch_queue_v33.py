#!/usr/bin/env python3
# Update 33 for ffplay-custom (on top of patch_queue_v32.py). Merged from two versions: the stutter, preferences,
# waveform and tile parts come from the other account's v33, the rest is from this account.
#   * Background stutter: the player never waits for the screen any more (vsync is always off; the compositor of this
#     desktop shows no tearing), and it draws at most about 60 pictures a second. A window the window manager does not
#     show can no longer hold the player back, and background mode no longer makes a test picture that waits. The
#     screen-sleep switch (which asks the desktop each time) changes only after 1.5 s, not between every song and video.
#     The blur while another window has the focus is off (it ran the whole blur path on every frame). A log file,
#     ~/.cache/ffplay-custom/log.txt, gets every "ffplay-custom:" line with the time.
#   * Liquid glass without a lens: no bent edge, no highlight, no bright rim (no outline on the seek and volume bar),
#     an even haze, a lighter blur and a sharper edge.
#   * Preferences: the name nudges, and the choices slide in one after another from the right margin, with a soft pill
#     under the one the mouse is on.
#   * The queue view's waveform: one smooth shape, there at once. The track that plays is read before the view opens.
#   * Tiles that are alive: they glide in when the view opens, rise under the mouse, and the playing song breathes.
#   * Seeking: the nearest preview shows full size while a seek key is held or the bar is dragged, until the real picture
#     arrives. The previews start after 2 s and are made a little faster.
#   * The stock keys 0, 9, *, /, s, a, v, c, t, w, < and > are off.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v32.py. Writes the file only if every edit matches.
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
    """Replace from start (found once) up to, but not including, end."""
    global src
    a = src.find(start)
    b = src.find(end, a + 1) if a >= 0 else -1
    if a < 0 or b < 0 or src.count(start) != 1:
        print("FAILED: %s matched %d times" % (name, src.count(start)))
        fails.append(name)
        return
    src = src[:a] + new + src[b:]
    print("ok: " + name)


def between_incl(name, start, end, new):
    """Replace from start (found once) up to and including end (found once)."""
    global src
    if src.count(start) != 1 or src.count(end) != 1:
        print("FAILED: %s start matched %d times, end matched %d times" % (name, src.count(start), src.count(end)))
        fails.append(name)
        return
    a = src.index(start)
    b = src.index(end, a) + len(end)
    src = src[:a] + new + src[b:]
    print("ok: " + name)


if "ui_scrub_draw" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_wblur_tick" not in src:
    print("Apply patch_queue_v32.py first. Nothing written.")
    sys.exit(1)

# ============================================================ the stutter (the other account's version)
patch("vsync is never on", r'''static int ui_vsync_on = 1;''', r'''static int ui_vsync_on = 0;                 /* the player never waits for the screen (see ui_vsync_set) */''')
patch("vsync set does nothing", r'''static void ui_vsync_set(int on)
{
#if SDL_VERSION_ATLEAST(2, 0, 18)''', r'''static void ui_vsync_set(int on)
{
    /* With vsync on, a window the window manager does not show (another workspace, the Multitasking view) is not drawn to:
       the present then waits, and the whole player waits with it, the pictures pile up and are then skipped (the "fast
       forward"). The test picture of background mode did exactly that every 8 s on purpose. The compositor of this desktop
       shows no tearing, so the player simply never waits for the screen. */
    on = 0;
#if SDL_VERSION_ATLEAST(2, 0, 18)''')
patch("no vsync at the start", r'''renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);''',
      r'''renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED);''')
patch("probe without waiting", r'''        ui_bg_probe = now;
        ui_vsync_set(1);            /* with vsync a window in sight answers within a frame; a hidden one is held again */
    }''', r'''        ui_bg_probe = now;          /* one picture, drawn without waiting for the screen */
    }''')
patch("present: no wait, 60 a second at most", r'''    int64_t t0 = av_gettime_relative(), dt;

    SDL_RenderPresent(renderer);
    dt = av_gettime_relative() - t0;
    if (dt > 100000) {''', r'''    static int64_t last_present = 0;
    int64_t t0 = av_gettime_relative(), dt;

    if (last_present && t0 - last_present < 15000) {    /* not more than about 60 pictures a second, whatever draws */
        av_usleep((unsigned)(15000 - (t0 - last_present)));
        t0 = av_gettime_relative();
    }
    SDL_RenderPresent(renderer);
    dt = av_gettime_relative() - t0;
    last_present = av_gettime_relative();
    if (dt > 100000) {''')
patch("background mode ends when a present is quick", r'''    } else if (ui_bg && ui_vsync_on && dt < 40000) {''', r'''    } else if (ui_bg && dt < 40000) {''')

between("screen sleep does not flap", r'''static void ui_power_tick(VideoState *is)''', r'''/* ---- keyboard shortcuts that can be changed in settings.conf ---- */''', r'''static void ui_power_tick(VideoState *is)
{
    static int inhibit = -1, pending = -1;
    static int64_t asserted = 0, pending_since = 0;
    int64_t now = av_gettime_relative();
    int want = is && !is->paused && !is->ui_held && is->video_st &&
               !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC);

    if (ui_bg)
        return;                         /* out of sight: nothing that could make the player wait */
    if (inhibit != -1 && want != inhibit) {     /* a change has to last 1.5 s: no flapping between items (each change asks the desktop) */
        if (pending != want) {
            pending = want;
            pending_since = now;
        }
        if (now - pending_since < 1500000)
            return;
    } else {
        pending = -1;
    }
    if (want == inhibit && now - asserted < 5000000)
        return;
    if (want != inhibit)
        av_log(NULL, AV_LOG_INFO, want ? "screen kept awake (a video is playing)\n"
                                       : "screen may sleep (the system's idle settings apply)\n");
    inhibit = want;
    asserted = now;
    pending = -1;
    if (want)
        SDL_DisableScreenSaver();       /* playing a video: keep the screen on */
    else
        SDL_EnableScreenSaver();
}

''')


# ============================================================ blur, log file, glass, seeking, keys
patch('no blur while only unfocused',
      r'''#define UI_WBLUR_AWAY 0.40 ''',
      r'''#define UI_WBLUR_AWAY 0.0  ''')
patch('time.h for the log file',
      r'''#include <SDL_ttf.h>
''',
      r'''#include <SDL_ttf.h>
#include <time.h>
''')
patch('a sharper glass edge',
      r'''static const double depth[UI_LG_RINGS] = { -1.2, 0.4, 2.0, 5.0, 9.0, 15.0, 24.0 };''',
      r'''static const double depth[UI_LG_RINGS] = { -0.6, 0.2, 2.0, 5.0, 9.0, 15.0, 24.0 };    /* a sharp edge */''')
patch('no lens: declaration',
      r'''double lim = FFMIN(t->w, t->h) / 2.0 - 1.0, D, Rf;''',
      r'''double lim = FFMIN(t->w, t->h) / 2.0 - 1.0, D;''')
patch('no lens: radius',
      r'''    Rf = 0.5 * D;
''',
      r'''''')
patch('no lens: bend',
      r'''        double s = Rf * (1.0 - dn) * (1.0 - dn);        /* how far further in the picture is taken from */
''',
      r'''        double s = 0.0;                                 /* no lens: the picture behind is not bent at the edge */
''')
patch('an even haze',
      r'''vh[k * UI_LG_NP + j].color.a = k == 0 ? 0 : (Uint8)(ta * (0.62 + 0.38 * dn));      /* thinner at the rim: the bend shows */''',
      r'''vh[k * UI_LG_NP + j].color.a = k == 0 ? 0 : (Uint8)ta;      /* an even haze */''')
patch('no highlight, no bright rim',
      r'''    SDL_RenderGeometry(renderer, NULL, vs, nv + 1, idx, ni);   /* the highlight on the upper half */
    SDL_RenderGeometry(renderer, NULL, vr, nv + 1, idx, nrim); /* the rim of light */
''',
      r'''    (void)nrim;                                 /* no highlight and no bright rim: plain glass */
''')
patch('scrub forward declaration',
      r'''static void video_image_display(VideoState *is)
{''',
      r'''static int ui_scrub_draw(VideoState *is, const SDL_Rect *rect);

static void video_image_display(VideoState *is)
{''')
patch('the picture or the preview',
      r'''        SDL_RenderCopyEx(renderer, is->vid_texture, NULL, &rect, 0, NULL, vp->flip_v ? SDL_FLIP_VERTICAL : 0);
        ui_xf_video_draw(is, 0);''',
      r'''        if (!ui_scrub_draw(is, &rect))          /* while seeking: the nearest preview first, the real picture when it is there */
            SDL_RenderCopyEx(renderer, is->vid_texture, NULL, &rect, 0, NULL, vp->flip_v ? SDL_FLIP_VERTICAL : 0);
        ui_xf_video_draw(is, 0);''')
patch('the nearest preview while seeking',
      r'''static void ui_apply(VideoState *is, int x, int final)
{''',
      r'''/* While a seek key is held or the bar is dragged and the seek is still on its way, the picture of the nearest ready
   preview is drawn full size instead of the old frame (like the thumbnail strip of a video site: nothing waits).
   Returns 1 if it drew one. */
static int ui_scrub_draw(VideoState *is, const SDL_Rect *rect)
{
    int64_t now = av_gettime_relative();
    int n = ui_th.n, idx, d, found = -1;
    double f;
    UiThumb *t;

    if (!UI_THUMBS || ui_th.id <= 0 || ui_th.id != is->ui_thumb_id || n <= 0 || ui_th.dur <= 0.0)
        return 0;
    if (!(ui_drag == 1 || ui_ks_want || ((is->seek_req || is->prec_v) && (now - ui_ks_issued < 1500000 || now < ui_hold_until))))
        return 0;
    if (ui_drag == 1)
        f = ui_seek_frac;
    else if (ui_ks_want)
        f = (ui_ks_target - ui_th.start / (double)AV_TIME_BASE) / ui_th.dur;
    else
        f = (is->seek_pos - ui_th.start) / (double)AV_TIME_BASE / ui_th.dur;
    idx = av_clip((int)(av_clipd(f, 0.0, 1.0) * n), 0, n - 1);
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
    return 1;
}

static void ui_apply(VideoState *is, int x, int final)
{''')
patch('previews start after 2 s',
      r'''if (isnan(pos) || pos < 4.0)''',
      r'''if (isnan(pos) || pos < 2.0)''')
patch('previews are made a little faster',
      r'''av_usleep(6000);''',
      r'''av_usleep(2000);''')
patch('key . is off',
      r'''            case SDLK_n:
            case SDLK_PERIOD:
''',
      r'''            case SDLK_n:
''')
patch('key , is off',
      r'''            case SDLK_p:
            case SDLK_COMMA:
''',
      r'''            case SDLK_p:
''')
between_incl('keys 0 9 * / s a v c t are off',
        r'''            case SDLK_KP_MULTIPLY:
''',
        r'''            case SDLK_t:
                stream_cycle_channel(cur_stream, AVMEDIA_TYPE_SUBTITLE);
                break;
''',
        r'''''')
between_incl('key w is off',
        r'''            case SDLK_w:
''',
        r'''                    toggle_audio_display(cur_stream);
                }
                break;
''',
        r'''''')
patch('no lens: unused value',
      r'''        double dn = av_clipd(d / D, 0.0, 1.0);
''',
      r'''''')
patch('unused stock function 1',
      r'''static void toggle_audio_display(VideoState *is)''',
      r'''static av_unused void toggle_audio_display(VideoState *is)''')
patch('unused stock function 2',
      r'''static void stream_cycle_channel(VideoState *is, int codec_type)''',
      r'''static av_unused void stream_cycle_channel(VideoState *is, int codec_type)''')
patch('a log file',
      r'''static void ui_present(void)
{
''',
      r'''/* A log file for the lines that start with "ffplay-custom:" (held frames, background mode, slow steps), with the time,
   so they can be read without a terminal: ~/.cache/ffplay-custom/log.txt */
static FILE *ui_logf = NULL;

static void ui_log_cb(void *avcl, int level, const char *fmt, va_list vl)
{
    va_list vl2;
    char line[400];

    va_copy(vl2, vl);
    av_log_default_callback(avcl, level, fmt, vl);      /* the terminal gets it as before */
    if (ui_logf && level <= AV_LOG_WARNING) {
        vsnprintf(line, sizeof(line), fmt, vl2);
        if (!strncmp(line, "ffplay-custom:", 14)) {
            time_t tt = time(NULL);
            struct tm *tmv = localtime(&tt);
            char ts[16] = "";

            if (tmv)
                strftime(ts, sizeof(ts), "%H:%M:%S", tmv);
            fprintf(ui_logf, "%s %s", ts, line);
            fflush(ui_logf);
        }
    }
    va_end(vl2);
}

static void ui_log_open(void)
{
    const char *home = getenv("HOME"), *drv = SDL_GetCurrentVideoDriver();
    char dir[512], file[560];
    long size = 0;
    FILE *f;

    if (!home)
        return;
    snprintf(dir, sizeof(dir), "%s/.cache/ffplay-custom", home);
    mkdir(dir, 0755);
    snprintf(file, sizeof(file), "%s/log.txt", dir);
    f = fopen(file, "r");
    if (f) {
        fseek(f, 0, SEEK_END);
        size = ftell(f);
        fclose(f);
    }
    ui_logf = fopen(file, size > 200000 ? "w" : "a");       /* it never grows past a few hundred KB */
    if (!ui_logf)
        return;
    fprintf(ui_logf, "---- started: video driver %s\n", drv ? drv : "?");
    fflush(ui_logf);
    av_log_set_callback(ui_log_cb);
}

static void ui_log_once(void)
{
    static int logged = 0;

    if (!logged) {
        logged = 1;
        ui_log_open();
    }
}

static void ui_present(void)
{
''')
patch('a log file: opened at the first picture',
      r'''    if (last_present && t0 - last_present < 15000) {    /* not more than about 60 pictures a second, whatever draws */
''',
      r'''    ui_log_once();
    if (last_present && t0 - last_present < 15000) {    /* not more than about 60 pictures a second, whatever draws */
''')
patch('glass: a light blur, the glass stays sharp',
      r'''    SDL_Texture *bt = ui_blur_tex[2];
''',
      r'''    SDL_Texture *bt = ui_blur_tex[1];           /* a light blur: the glass stays sharp */
''')

# ============================================================ preferences, waveform, tiles (the other account's version)
between("row choices at the right margin", r'''static int ui_pref_layout(int row, const SDL_Rect *p, int cy, SDL_Rect out[10], const char *names[10], char store[10][20],''',
        r'''/* The width the panel needs so that the name and all choices''', r'''static int ui_pref_layout(int row, const SDL_Rect *p, int cy, SDL_Rect out[10], const char *names[10], char store[10][20],
                          int *sel, int *px)
{
    static const int px_try[4] = { 18, 16, 15, 14 }, pad_try[4] = { 18, 14, 10, 8 }, gap_try[4] = { 6, 5, 4, 3 };
    int n = ui_pref_choices(row, names, store, sel), i, total = 0, x, w[10], pass, room, gap = 3;

    room = p->w - 2 * ui_pr_mg - ui_text_width(ui_pref_name[row], ui_pr_px) - 26;      /* the name stays at its margin (nudged 10 px) */
    *px = 14;
    for (pass = 0; pass < 4; pass++) {
        gap = gap_try[pass];
        total = 0;
        for (i = 0; i < n; i++) {
            w[i] = ui_text_width(names[i], px_try[pass]) + pad_try[pass];
            total += w[i] + (i ? gap : 0);
        }
        *px = px_try[pass];
        if (total <= room)
            break;
    }
    x = p->x + p->w - ui_pr_mg - total;         /* against the right margin */
    ui_pl_title_x = p->x + ui_pr_mg + 10;
    for (i = 0; i < n; i++) {
        out[i].x = x;
        out[i].y = cy - FFMIN(32, ui_pr_row - 6) / 2;
        out[i].w = w[i];
        out[i].h = FFMIN(32, ui_pr_row - 6);
        x += w[i] + gap;
    }
    return n;
}

''')
patch("need width with the nudge", r'''ui_text_width(ui_pref_name[row], ui_pr_px) + 8 + total;''', r'''ui_text_width(ui_pref_name[row], ui_pr_px) + 26 + total;''')
between("the name only nudges", r'''        {                                       /* the name glides from the left margin into the row of the choices, and back */''',
        r'''        if (k > 0.01) {
            ui_pref_value(i, value, sizeof(value));''', r'''        ui_label(p.x + ui_pr_mg + (int)(10 * se), cy, ui_pref_name[i], ui_pr_px, 245, 245, 245,
                 i == ui_prefs_hover ? 255 : 210);      /* the name nudges a little to make room, like a volume bar coming in from the side */

''')
between("the choices slide in one after another", r'''            n = ui_pref_layout(i, &p, cy, r, names, store, &sel, &px);
            for (c = 0; c < n; c++) {
                double cxc = r[c].x + r[c].w / 2.0, cx = x_right + (cxc - x_right) * se;''', r'''            }
        }
    }
    if (UI_PREF_FOOT >= 30)''', r'''            n = ui_pref_layout(i, &p, cy, r, names, store, &sel, &px);
            for (c = 0; c < n; c++) {
                double cxc = r[c].x + r[c].w / 2.0, cx, sc;

                sc = av_clipd(se * 1.5 - 0.5 * (n - 1 - c) / FFMAX(n - 1, 1), 0.0, 1.0);   /* the choice at the margin first, then the next */
                sc = sc * sc * (3.0 - 2.0 * sc);
                cx = cxc + (1.0 - sc) * 34.0;           /* each one slides in from the side while it fades in */
                hot = i == ui_prefs_hover && ui_prefs_mx >= r[c].x && ui_prefs_mx < r[c].x + r[c].w &&
                      ui_prefs_my >= r[c].y && ui_prefs_my < r[c].y + r[c].h;
                if (hot) {                      /* a soft pill under the choice the mouse is on */
                    SDL_Rect pill = r[c];

                    pill.x = (int)(cx - r[c].w / 2.0);
                    SDL_SetRenderDrawColor(renderer, 255, 255, 255, (int)(34 * sc));
                    ui_pill(&pill);
                }
                if (c == sel)                   /* the choice that is on: in the bar color */
                    ui_label_c((int)cx, cy, names[c], px, av_clip(cfg_bar_r + 40, 0, 255),
                               av_clip(cfg_bar_g + 40, 0, 255), av_clip(cfg_bar_b + 40, 0, 255), (int)(255 * sc));
                else
                    ui_label_c((int)cx, cy, names[c], px, 245, 245, 245, (int)((hot ? 255 : 170) * sc));
''')

# ============================================================ the waveform: one smooth shape, there at once
patch("wave: the track is read before the view opens", r'''/* ---- previews on the tiles: the video under the mouse plays on its tile, without sound, at its own speed ---- */''',
r'''/* Read the shape of the track that plays (and the next one) before the queue view is opened, so it is ready when it shows */
static void ui_wave_tick(VideoState *is)
{
    static int last = -2;
    float tmp[UI_WAVE_N];

    if (!is || q_count <= 0 || q_pos < 0 || q_pos >= q_count || q_pos == last)
        return;
    if (is->video_st && !ui_vflow)              /* a video only needs it when the queue view is open */
        return;
    last = q_pos;
    ui_wave_get(q_items[q_pos], tmp);
    if (!is->video_st && q_pos + 1 < q_count)
        ui_wave_get(q_items[q_pos + 1], tmp);
}

/* ---- previews on the tiles: the video under the mouse plays on its tile, without sound, at its own speed ---- */''')
patch("wave: tick in the loop", r'''        UI_TIMED(ui_cover_tick(is));''', r'''        UI_TIMED(ui_wave_tick(is));
        UI_TIMED(ui_cover_tick(is));''')
between("wave: one smooth shape", r'''        for (j = 0; j < nb && bars_ok; j++) {
            if (have) {''', r'''    }
    if (ui_flow_dragging && ui_flow_press >= 0 && ui_flow_press < q_count) {''', r'''        (void)b0; (void)b1; (void)q; (void)amp; (void)j; (void)nb; (void)pitch; (void)bw; (void)bar;
        if (bars_ok) {                                  /* one smooth shape, mirrored around the middle line, drawn at once */
            enum { MAXC = 400 };
            static SDL_Vertex wf[MAXC * 4];
            static int wi[MAXC * 18];
            static double hs[MAXC], h2[MAXC], mixw = 0.0;
            static int64_t seen = 0, born = 0;
            int64_t tn = av_gettime_relative();
            int nc = av_clip(span / 4 + 1, 8, MAXC), c, ni = 0, ab = 90 * nal / 255;
            double grow, half = FFMAX(maxh / 2.0 - 1.5, 1.0);

            if (tn - seen > 400000)
                born = tn;                              /* the view has just opened: the shape rises from the line */
            seen = tn;
            grow = 1.0 - exp(-(tn - born) / 1000000.0 / 0.14);
            if (grow < 0.995)
                ui_flow_moving = 1;
            mixw += ((have ? 1.0 : 0.0) - mixw) * (1.0 - exp(-dt * 4.0));      /* the real shape fades in over the live one */
            if (fabs((have ? 1.0 : 0.0) - mixw) > 0.004)
                ui_flow_moving = 1;
            for (c = 0; c < nc; c++) {
                double u = c / (double)(nc - 1), fb = u * (UI_WAVE_N - 1), fe = u * (NEQ - 1);
                int b = (int)fb, e2 = (int)fe;
                double live, ph, whole;

                live = eq[e2] * (1.0 - (fe - e2)) + eq[FFMIN(e2 + 1, NEQ - 1)] * (fe - e2);
                ph = av_clipd(0.07 + 0.05 * sin(u * 16.0 + t * 2.1) + live * 0.9, 0.0, 1.0);   /* not read yet: the loudness of the last seconds */
                if (have) {
                    whole = wv[b] * (1.0 - (fb - b)) + wv[FFMIN(b + 1, UI_WAVE_N - 1)] * (fb - b);
                    whole *= is->paused ? 0.9 : (0.74 + 0.26 * live);       /* the whole track, moving with the music */
                } else {
                    whole = ph;
                }
                hs[c] = ph + (whole - ph) * mixw;
            }
            for (c = 0; c < nc; c++) {                  /* a little smoothing along the shape */
                double sum = 0.0;
                int k2, cnt = 0;

                for (k2 = -2; k2 <= 2; k2++)
                    if (c + k2 >= 0 && c + k2 < nc) {
                        sum += hs[c + k2];
                        cnt++;
                    }
                h2[c] = sum / cnt;
            }
            for (c = 0; c < nc; c++) {
                double x = x0 + span * c / (double)(nc - 1);
                double hh = 1.5 + av_clipd(h2[c], 0.0, 1.0) * half * grow;
                int k;

                for (k = 0; k < 4; k++) {
                    wf[c * 4 + k].position.x = (float)x;
                    wf[c * 4 + k].color.r = wf[c * 4 + k].color.g = wf[c * 4 + k].color.b = 255;
                    wf[c * 4 + k].color.a = (k == 0 || k == 3) ? 0 : (Uint8)ab;
                    wf[c * 4 + k].tex_coord.x = wf[c * 4 + k].tex_coord.y = 0.0f;
                }
                wf[c * 4 + 0].position.y = (float)(mid - hh - 1.2);      /* the soft edge, a pixel outside */
                wf[c * 4 + 1].position.y = (float)(mid - hh);
                wf[c * 4 + 2].position.y = (float)(mid + hh);
                wf[c * 4 + 3].position.y = (float)(mid + hh + 1.2);
            }
            for (c = 0; c < nc - 1; c++) {
                int a = c * 4, b2 = (c + 1) * 4;

                wi[ni++] = a + 1; wi[ni++] = a + 2; wi[ni++] = b2 + 1;      /* the body */
                wi[ni++] = a + 2; wi[ni++] = b2 + 2; wi[ni++] = b2 + 1;
                wi[ni++] = a;     wi[ni++] = a + 1; wi[ni++] = b2;          /* the soft edge above */
                wi[ni++] = a + 1; wi[ni++] = b2 + 1; wi[ni++] = b2;
                wi[ni++] = a + 2; wi[ni++] = a + 3; wi[ni++] = b2 + 2;      /* and below */
                wi[ni++] = a + 3; wi[ni++] = b2 + 3; wi[ni++] = b2 + 2;
            }
            SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
            SDL_RenderGeometry(renderer, NULL, wf, nc * 4, wi, ni);
        }
''')

# ============================================================ tiles that are alive
patch("tile state", r'''static int ui_tp_on = 0;''', r'''static double ui_tile_lift[32];             /* 0 to 1: how far each tile has risen under the mouse (by queue number) */
static int64_t ui_tile_born = 0, ui_tile_seen = 0;      /* when the queue view opened */
static int ui_tp_on = 0;''')
patch("tile locals", r'''    enum { NEQ = 72 };
    int sm, npx, gy;''', r'''    enum { NEQ = 72 };
    int sm, npx, gy, hov_i = -1;''')
patch("tile: view opened, tile under the mouse", r'''    ui_tp_tick(is);
    dt = ui_flow_t ?''', r'''    ui_tp_tick(is);
    if (now - ui_tile_seen > 350000)
        ui_tile_born = now;                     /* the view has just opened: the tiles glide in */
    ui_tile_seen = now;
    if (ui_hov_x >= 0 && !ui_flow_dragging && !ui_menu_open && !ui_prefs_open)
        hov_i = ui_flow_cover_at(is, ui_hov_x, ui_hov_y);
    dt = ui_flow_t ?''')
patch("tiles are alive", r'''                if (ui_flow_vmode && i != q_pos)
                    al = (int)(al * ui_vflow_ep);       /* the other tiles fade in while the video shrinks */
''', r'''                if (ui_flow_vmode && i != q_pos)
                    al = (int)(al * ui_vflow_ep);       /* the other tiles fade in while the video shrinks */
                {                               /* the tiles are alive: they glide in when the view opens, rise under the mouse,
                                                   and the one that plays breathes with the music */
                    double lf = ui_tile_lift[i & 31], goal = (i == hov_i) ? 1.0 : 0.0, en, ease, x1;
                    int dw, dh;

                    lf += (goal - lf) * (1.0 - exp(-dt * 14.0));
                    if (fabs(goal - lf) < 0.004)
                        lf = goal;
                    else
                        ui_flow_moving = 1;
                    ui_tile_lift[i & 31] = lf;
                    en = ui_flow_vmode ? 1.0 : av_clipd(((now - ui_tile_born) / 1000000.0 - ad * 0.05) / 0.45, 0.0, 1.0);
                    if (en < 1.0)
                        ui_flow_moving = 1;
                    x1 = en - 1.0;
                    ease = 1.0 + 2.70158 * x1 * x1 * x1 + 1.70158 * x1 * x1;     /* eases out and overshoots a little */
                    tile.x += (int)((1.0 - ease) * (d < 0 ? -1.0 : d > 0 ? 1.0 : 0.0) * W * 0.12);
                    tile.y += (int)((1.0 - ease) * 36.0);
                    al = (int)(al * en);
                    dw = dh = (i == q_pos && !ui_flow_vmode) ? (int)(tile.w * 0.018 * lvl) : 0;
                    dw += (int)(tile.w * 0.05 * lf);
                    dh += (int)(tile.h * 0.05 * lf);
                    if (dw || dh) {
                        tile.x -= dw / 2;
                        tile.y -= dh / 2 + (int)(6 * lf);
                        tile.w += dw;
                        tile.h += dh;
                    }
                    md = FFMIN(255, md + (int)(40 * lf));
                }
''')

if fails:
    print("\n%d edits did not apply. Nothing was written." % len(fails))
    sys.exit(1)
open(PATH, "w").write(src)
print("Patched " + PATH)
