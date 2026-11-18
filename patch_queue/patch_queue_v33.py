#!/usr/bin/env python3
# Update 33 for ffplay-custom (on top of patch_queue_v32.py).
#   * Background stutter, second round:
#       - The mouse ENTER event no longer ends background mode. A window that is out of sight can still get an enter
#         event (the Multitasking view shows it under the mouse), and the vsync that came with it made the next frame
#         wait for the window manager again: one more stall. Real mouse movement, focus and "shown" still end it.
#       - The blur while another window has the focus is off (UI_WBLUR_AWAY = 0). It ran the whole blur drawing path
#         on every frame for as long as the window was visible but not focused. The soft return from out of sight stays.
#       - A log file, ~/.cache/ffplay-custom/log.txt, gets every "ffplay-custom:" line (held frames, background mode on
#         and off, slow steps) with the time, so no terminal is needed to see what happened.
#   * Liquid glass without a lens: no bent edge, no highlight, no bright rim (so no outline on the seek and volume
#     bar), an even haze, and a sharper edge.
#   * Preferences: the name only nudges 12 px from its margin when the choices come; they glide in from the right
#     margin with a small overshoot, like the iPhone's volume bar.
#   * The queue view's waveform is one smooth wave instead of bars. It is drawn at full strength on the first frame
#     and morphs to the shape of the whole track when that has been read.
#   * Seeking: while a seek key is held or the bar is dragged, the picture of the nearest preview is shown full size at
#     once, instead of the old frame, until the real frame arrives. The previews start after 2 s (was 4 s) and are made
#     a little faster.
#   * Keys: the stock ffplay keys 0, 9, *, /, s, a, v, c, t, w, < and > are off.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v32.py. Writes the file only if every spot matches once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_scrub_draw" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_wblur_tick" not in src:
    print("Apply patch_queue_v32.py first. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


def between(start, end, new, label):
    """Replace everything from start (found once) up to and including end (found once, after start)."""
    global src
    if src.count(start) != 1 or src.count(end) != 1:
        print("FAILED:", label, "- start matched", src.count(start), "times, end matched", src.count(end),
              "times, expected 1 each. Nothing written.")
        sys.exit(1)
    a = src.index(start)
    b = src.index(end, a) + len(end)
    src = src[:a] + new + src[b:]
    print("ok:", label)


# ============================================================ stutter

patch("""                case SDL_WINDOWEVENT_SHOWN:
                case SDL_WINDOWEVENT_RESTORED:
                case SDL_WINDOWEVENT_FOCUS_GAINED:
                case SDL_WINDOWEVENT_ENTER:
                    ui_vsync_set(1);        /* the window is in sight again */
                    ui_bg_set(0);
                    cur_stream->force_refresh = 1;
                    break;
""", """                case SDL_WINDOWEVENT_SHOWN:
                case SDL_WINDOWEVENT_RESTORED:
                case SDL_WINDOWEVENT_FOCUS_GAINED:
                    ui_vsync_set(1);        /* the window is in sight again */
                    ui_bg_set(0);
                    cur_stream->force_refresh = 1;
                    break;
                case SDL_WINDOWEVENT_ENTER:     /* a window out of sight can get this too: it does not end background mode */
                    if (!ui_bg)
                        ui_vsync_set(1);
                    cur_stream->force_refresh = 1;
                    break;
""", "mouse enter no longer ends background mode")

patch("#define UI_WBLUR_AWAY 0.40 ", "#define UI_WBLUR_AWAY 0.0  ", "no blur while only unfocused")

patch("#include <SDL_ttf.h>\n", "#include <SDL_ttf.h>\n#include <time.h>\n", "time.h for the log file")

patch("static void ui_present(void)\n{\n    int64_t t0 = av_gettime_relative(), dt;\n",
"""/* A log file for the lines that start with "ffplay-custom:" (held frames, background mode, slow steps), with the time,
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
    fprintf(ui_logf, "---- started: video driver %s\\n", drv ? drv : "?");
    fflush(ui_logf);
    av_log_set_callback(ui_log_cb);
}

static void ui_present(void)
{
    static int logged = 0;
    int64_t t0 = av_gettime_relative(), dt;

    if (!logged) {
        logged = 1;
        ui_log_open();
    }
""", "a log file")

# ============================================================ liquid glass without a lens

patch("static const double depth[UI_LG_RINGS] = { -1.2, 0.4, 2.0, 5.0, 9.0, 15.0, 24.0 };",
      "static const double depth[UI_LG_RINGS] = { -0.6, 0.2, 2.0, 5.0, 9.0, 15.0, 24.0 };    /* a sharp edge */",
      "a sharper glass edge")
patch("double lim = FFMIN(t->w, t->h) / 2.0 - 1.0, D, Rf;", "double lim = FFMIN(t->w, t->h) / 2.0 - 1.0, D;", "no lens: declaration")
patch("    Rf = 0.5 * D;\n", "", "no lens: radius")
patch("        double s = Rf * (1.0 - dn) * (1.0 - dn);        /* how far further in the picture is taken from */\n",
      "        double s = 0.0;                                 /* no lens: the picture behind is not bent at the edge */\n",
      "no lens: bend")
patch("vh[k * UI_LG_NP + j].color.a = k == 0 ? 0 : (Uint8)(ta * (0.62 + 0.38 * dn));      /* thinner at the rim: the bend shows */",
      "vh[k * UI_LG_NP + j].color.a = k == 0 ? 0 : (Uint8)ta;      /* an even haze */",
      "an even haze")
patch("    SDL_RenderGeometry(renderer, NULL, vs, nv + 1, idx, ni);   /* the highlight on the upper half */\n"
      "    SDL_RenderGeometry(renderer, NULL, vr, nv + 1, idx, nrim); /* the rim of light */\n",
      "    (void)nrim;                                 /* no highlight and no bright rim: plain glass */\n",
      "no highlight, no bright rim")

# ============================================================ preferences: the name nudges, the choices glide in

patch("    room = p->w - 2 * ui_pr_mg;\n",
      "    room = p->w - 2 * ui_pr_mg - 12;            /* the name nudges 12 px when the choices come */\n",
      "preferences: room for the nudge")
patch("""    x = p->x + (p->w - total) / 2;              /* the whole row in the middle */
    ui_pl_title_x = x + pad_try[pp] / 2;
    x += tw + gap;
""", """    (void)pp;
    x = p->x + p->w - ui_pr_mg - (total - tw - gap);   /* the choices end at the right margin, where the value was */
    ui_pl_title_x = p->x + ui_pr_mg + 12;       /* the name only nudges a little from its margin */
""", "preferences: choices at the right margin, name nudges")
patch("double cxc = r[c].x + r[c].w / 2.0, cx = x_right + (cxc - x_right) * se;",
      "double cxc = r[c].x + r[c].w / 2.0, cx = x_right + (cxc - x_right) * (se + 0.06 * sin(3.14159265 * se));   /* a small overshoot */",
      "preferences: the choices pop in")

# ============================================================ a smooth wave in the queue view

between("        for (j = 0; j < nb && bars_ok; j++) {\n            if (have) {",
        "            ui_rr_fill(&bar, bw / 2);           /* rounded top and bottom, like the seek bar */\n        }\n",
"""        if (bars_ok) {                                  /* one smooth wave: drawn at full strength at once, morphing when the track has been read */
            enum { MAXW = 480 };
            static float cur[MAXW + 1];
            static SDL_Vertex wvx[(MAXW + 1) * 4];
            static int wix[MAXW * 18];
            static int64_t wlast = 0;
            int n = av_clip(span / 3, 24, MAXW), c, m = 0, wsnap = now - wlast > 200000;
            double wdt = wsnap ? 10.0 : av_clipd((now - wlast) / 1000000.0, 0.0, 0.05), wk = 1.0 - exp(-wdt / 0.12);
            const double fw = 1.0;                      /* half the width of the soft edge */
            SDL_Color wc, wz;

            wc.r = wc.g = wc.b = 255;
            wc.a = (Uint8)(90 * nal / 255);
            wz = wc;
            wz.a = 0;
            for (c = 0; c <= n; c++) {
                double u = (double)c / n, fp, am, hh;
                int i0, i1;
                SDL_Vertex *v = &wvx[c * 4];

                if (have) {                             /* the shape of the whole track, a little alive with the music */
                    fp = u * (UI_WAVE_N - 1);
                    i0 = (int)fp;
                    i1 = FFMIN(i0 + 1, UI_WAVE_N - 1);
                    am = wv[i0] + (wv[i1] - wv[i0]) * (fp - i0);
                    am *= is->paused ? 0.9 : 0.78 + 0.22 * av_clipd(lvl, 0.0, 1.0);
                } else {                                /* not read yet: the loudness of the last few seconds */
                    fp = u * (NEQ - 1);
                    i0 = (int)fp;
                    i1 = FFMIN(i0 + 1, NEQ - 1);
                    am = eq[i0] + (eq[i1] - eq[i0]) * (fp - i0);
                }
                cur[c] += (float)((am - cur[c]) * wk);
                hh = 1.5 + av_clipd(cur[c], 0.0, 1.0) * (maxh - 3) / 2.0;
                v[0].position.x = v[1].position.x = v[2].position.x = v[3].position.x = (float)(x0 + u * span);
                v[0].position.y = (float)(mid - hh - fw);
                v[1].position.y = (float)(mid - hh + fw);
                v[2].position.y = (float)(mid + hh - fw);
                v[3].position.y = (float)(mid + hh + fw);
                v[0].color = wz;
                v[1].color = wc;
                v[2].color = wc;
                v[3].color = wz;
                v[0].tex_coord.x = v[1].tex_coord.x = v[2].tex_coord.x = v[3].tex_coord.x = 0.0f;
                v[0].tex_coord.y = v[1].tex_coord.y = v[2].tex_coord.y = v[3].tex_coord.y = 0.0f;
            }
            for (c = 0; c < n; c++) {
                int b;

                for (b = 0; b < 3; b++) {
                    int a0 = c * 4 + b, a1 = a0 + 1, c0 = a0 + 4, c1 = a1 + 4;

                    wix[m++] = a0;
                    wix[m++] = a1;
                    wix[m++] = c0;
                    wix[m++] = a1;
                    wix[m++] = c1;
                    wix[m++] = c0;
                }
            }
            SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
            SDL_RenderGeometry(renderer, NULL, wvx, (n + 1) * 4, wix, m);
            wlast = now;
        }
        (void)nb;
        (void)pitch;
        (void)bw;
        (void)b0;
        (void)b1;
        (void)q;
        (void)amp;
        (void)bar;
        (void)j;
        (void)t;
""", "the waveform is one smooth wave")

# ============================================================ seeking: the nearest preview at once

patch("static void video_image_display(VideoState *is)\n{",
      "static int ui_scrub_draw(VideoState *is, const SDL_Rect *rect);\n\nstatic void video_image_display(VideoState *is)\n{",
      "scrub forward declaration")

patch("        SDL_RenderCopyEx(renderer, is->vid_texture, NULL, &rect, 0, NULL, vp->flip_v ? SDL_FLIP_VERTICAL : 0);\n        ui_xf_video_draw(is, 0);",
      "        if (!ui_scrub_draw(is, &rect))          /* while seeking: the nearest preview first, the real picture when it is there */\n            SDL_RenderCopyEx(renderer, is->vid_texture, NULL, &rect, 0, NULL, vp->flip_v ? SDL_FLIP_VERTICAL : 0);\n        ui_xf_video_draw(is, 0);",
      "the picture or the preview")

patch("static void ui_apply(VideoState *is, int x, int final)\n{",
"""/* While a seek key is held or the bar is dragged and the seek is still on its way, the picture of the nearest ready
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
{""", "the nearest preview while seeking")

patch("if (isnan(pos) || pos < 4.0)", "if (isnan(pos) || pos < 2.0)", "previews start after 2 s")
patch("av_usleep(6000);", "av_usleep(2000);", "previews are made a little faster")

# ============================================================ the stock keys

patch("            case SDLK_n:\n            case SDLK_PERIOD:\n", "            case SDLK_n:\n", "key . is off")
patch("            case SDLK_p:\n            case SDLK_COMMA:\n", "            case SDLK_p:\n", "key , is off")
between("            case SDLK_KP_MULTIPLY:\n",
        "            case SDLK_t:\n                stream_cycle_channel(cur_stream, AVMEDIA_TYPE_SUBTITLE);\n                break;\n",
        "", "keys 0 9 * / s a v c t are off")
between("            case SDLK_w:\n",
        "                    toggle_audio_display(cur_stream);\n                }\n                break;\n",
        "", "key w is off")

patch("        double dn = av_clipd(d / D, 0.0, 1.0);\n", "", "no lens: unused value")
patch("static void toggle_audio_display(VideoState *is)", "static av_unused void toggle_audio_display(VideoState *is)", "unused stock function 1")
patch("static void stream_cycle_channel(VideoState *is, int codec_type)", "static av_unused void stream_cycle_channel(VideoState *is, int codec_type)", "unused stock function 2")

open(path, "w").write(src)
print("Patched fftools/ffplay.c")
