#!/usr/bin/env python3
# Update 4 for ffplay-custom.
#   * No highlight boxes behind menu rows, queue rows, sleep choices, the seek tooltip or the snap message:
#     text only (the tooltip and snap text get a soft shadow so they stay readable).
#   * Softer, smaller arrowheads in the menus and the preferences.
#   * Chapters: the seek bar is cut into sections, one per chapter, instead of dots or ticks.
#   * Cover art backdrop: audio files with embedded art get a slowly drifting glow of the cover's own colors
#     behind the picture, and it breathes with the music.
#   * Desktop media controls (MPRIS): the sound indicator in the top panel, media keys and playerctl can control
#     playback. This starts the small helper "ffplay-mpris" (see the instructions), so it needs that file.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v3b.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_mpris_tick" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "q_dur_gen" not in src:
    print("Apply patch_queue_v3.py and patch_queue_v3b.py first. Nothing written.")
    sys.exit(1)


def fail(label, why):
    print("FAILED:", label, "-", why, "Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    """Swap old for new, only if old is found exactly once."""
    global src
    n = src.count(old)
    if n != 1:
        fail(label, "matched %d times, expected 1." % n)
    src = src.replace(old, new)
    print("ok:", label)


def patch_between(start, end, new, label):
    """Replace everything from start (included) up to end (not included)."""
    global src
    if src.count(start) != 1:
        fail(label, "start matched %d times, expected 1." % src.count(start))
    a = src.index(start)
    b = src.find(end, a + len(start))
    if b < 0 or src.count(end) != 1:
        fail(label, "end matched %d times, expected 1." % src.count(end))
    src = src[:a] + new + src[b:]
    print("ok:", label)


# ============================================================ no boxes behind text

patch("""        if (lit) {                  /* a soft rounded highlight behind the row */
            hl.x = row.x + 6;
            hl.y = row.y + 3;
            hl.w = row.w - 12;
            hl.h = row.h - 6;
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 30);
            ui_rr_fill(&hl, 11);
        }
""", "", "menu rows: no highlight box")
patch("    SDL_Rect r, card, row, hl;\n    int ww, wh, i, pad, cy, lit;\n",
      "    SDL_Rect r, card, row;\n    int ww, wh, i, pad, cy, lit;\n", "menu rows: unused variable")

patch("""        if (lit) {                  /* a soft rounded highlight under the row the mouse is on */
            hl.x = p.x + 8;
            hl.y = cy - UI_Q_ROW / 2 + 2;
            hl.w = p.w - 16;
            hl.h = UI_Q_ROW - 4;
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 18);
            ui_rr_fill(&hl, 11);
        }
""", "", "queue rows: no highlight box")
patch("    SDL_Rect p = ui_q_rect(ww, wh), sep, dot, hl, chip[6];\n",
      "    SDL_Rect p = ui_q_rect(ww, wh), sep, dot, chip[6];\n", "queue rows: unused variable")

patch("""        if (i == ui_open_hover) {
            hl.x = p.x + 6;
            hl.y = row_y + 3;
            hl.w = p.w - 12;
            hl.h = UI_MENU_ROW - 6;
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 30);
            ui_rr_fill(&hl, 11);
        }
""", "", "Open choices: no highlight box")
patch("    SDL_Rect p = ui_open_rect(ww, wh), hl;\n", "    SDL_Rect p = ui_open_rect(ww, wh);\n", "Open choices: unused variable")

patch("""        if (i == ui_ctx_hover) {
            hl.x = r.x + 6;
            hl.y = row_y + 3;
            hl.w = r.w - 12;
            hl.h = UI_CTX_ROW - 6;
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 30);
            ui_rr_fill(&hl, 11);
        }
""", "", "item menu: no highlight box")
patch("    SDL_Rect r = ui_ctx_rect(ww, wh), hl;\n", "    SDL_Rect r = ui_ctx_rect(ww, wh);\n", "item menu: unused variable")

# the sleep choices: text only, the one that is on in the bar color
patch("""            if (i == sel) {
                SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 215);
                ui_pill(&chip[i]);
            } else if (hot) {
                SDL_SetRenderDrawColor(renderer, 255, 255, 255, 38);
                ui_pill(&chip[i]);
            }
            ui_label_c(chip[i].x + chip[i].w / 2, cy, names[i], 16, 245, 245, 245, (i == sel || hot) ? 255 : 200);
""", """            if (i == sel)               /* the choice that is on: in the bar color */
                ui_label_c(chip[i].x + chip[i].w / 2, cy, names[i], 16, av_clip(cfg_bar_r + 40, 0, 255),
                           av_clip(cfg_bar_g + 40, 0, 255), av_clip(cfg_bar_b + 40, 0, 255), 255);
            else
                ui_label_c(chip[i].x + chip[i].w / 2, cy, names[i], 16, 245, 245, 245, hot ? 255 : 160);
""", "sleep choices: text only")

# the seek tooltip and the snap message: no box, a soft shadow instead
patch("static void ui_label(int x, int cy, const char *s, int px, int r, int g, int b, int a);\n\n/* ---- chapters on the seek bar",
      """static void ui_label(int x, int cy, const char *s, int px, int r, int g, int b, int a);

/* Text with a soft shadow under it, for text that floats over the picture without a box */
static void ui_label_s(int x, int cy, const char *s, int px, int r, int g, int b, int a)
{
    ui_label(x + 1, cy + 2, s, px, 0, 0, 0, a * 150 / 255);
    ui_label(x, cy, s, px, r, g, b, a);
}

/* ---- chapters on the seek bar""", "text with a shadow")

patch("""    SDL_SetRenderDrawColor(renderer, 20, 22, 26, 205);
    ui_pill(&box);
    ui_label(box.x + 14, box.y + box.h / 2, text, 16, 240, 240, 240, 255);
""", """    ui_label_s(box.x + 14, box.y + box.h / 2, text, 16, 245, 245, 245, 255);
""", "seek tooltip: no box")
patch("""    SDL_SetRenderDrawColor(renderer, 20, 22, 26, 190);
    ui_pill(&box);
    ui_label(box.x + 22, box.y + box.h / 2, msg, 22, 245, 245, 245, 255);
""", """    ui_label_s(box.x + 22, box.y + box.h / 2, msg, 22, 245, 245, 245, 255);
""", "snap message: no box")

# ============================================================ softer arrows

patch("/* ----- rounded rectangles ----- */\n",
      r'''/* A soft arrowhead for the menus: a flat, fine chevron with a faint halo, pointing left (dir = -1) or
   right (dir = 1). cx, cy = its middle. a = how strong it is (0 to 255). */
static void ui_arrow(int cx, int cy, int dir, int a)
{
    int k, tail = cx - dir * 3, tip = cx + dir * 3, h = 5;

    for (k = -1; k <= 1; k++) {
        SDL_SetRenderDrawColor(renderer, 225, 225, 225, k ? a / 5 : a);
        SDL_RenderDrawLine(renderer, tail, cy - h + k, tip, cy + k);
        SDL_RenderDrawLine(renderer, tip, cy + k, tail, cy + h + k);
    }
}

/* ----- rounded rectangles ----- */
''', "soft arrowhead")

patch("""    SDL_SetRenderDrawColor(renderer, 230, 230, 230, a);
    ui_q_line(x, cy - 6, x + 6, cy);
    ui_q_line(x + 6, cy, x, cy + 6);
""", """    ui_arrow(x + 3, cy, 1, a - 60);
""", "menu chevrons")

patch("""            ui_label(x_right - 190, cy, "<", 22, 190, 190, 190, 255);
            ui_label(x_right - 12, cy, ">", 22, 190, 190, 190, 255);
""", """            ui_arrow(x_right - 184, cy, -1, 150);
            ui_arrow(x_right - 6, cy, 1, 150);
""", "preferences arrows")

patch("""    ui_label(right - 154, cy, "<", 22, 190, 190, 190, hk == UI_Q_XF_DEC ? 255 : 170);
    ui_label(right - 26, cy, ">", 22, 190, 190, 190, hk == UI_Q_XF_INC ? 255 : 170);
""", """    ui_arrow(right - 148, cy, -1, hk == UI_Q_XF_DEC ? 235 : 150);
    ui_arrow(right - 20, cy, 1, hk == UI_Q_XF_INC ? 235 : 150);
""", "crossfade arrows")

# ============================================================ chapters: a bar in sections

patch_between("/* Chapter marks: small glowing dots sitting in the seek bar where chapters start */",
              "/* A small label above the seek bar",
              r'''/* The seek bar. A file with chapters gets a bar in sections: a small gap where each chapter starts,
   and the section under the mouse is a little brighter. Without chapters it is the plain bar. */
static void ui_seek_bar(VideoState *is, SDL_Rect *sk, double frac)
{
    double dur = is->ic->duration / (double)AV_TIME_BASE, f;
    int xs[130], n = 1, i, gap = 4, fx, hx = -1, ax, bx, x;
    unsigned c;
    SDL_Rect seg, fill;

    if (dur <= 0 || is->ic->nb_chapters < 2) {
        ui_bar(sk, frac);
        return;
    }
    xs[0] = sk->x;
    for (c = 1; c < is->ic->nb_chapters && n < 126; c++) {      /* where each chapter after the first starts */
        f = ui_chapter_start(is, c) / dur;
        if (f <= 0.004 || f >= 0.996)
            continue;
        x = sk->x + (int)(f * sk->w);
        if (x - xs[n - 1] < 12 || sk->x + sk->w - x < 12)       /* too close to the last one or the end */
            continue;
        xs[n++] = x;
    }
    xs[n] = sk->x + sk->w;
    if (n < 2) {
        ui_bar(sk, frac);
        return;
    }
    fx = sk->x + (int)(av_clipd(frac, 0.0, 1.0) * sk->w);
    if (ui_drag == 1)
        hx = sk->x + (int)(ui_seek_frac * sk->w);
    else if (ui_hover && ui_hover_x >= sk->x - 6 && ui_hover_x <= sk->x + sk->w + 6)
        hx = ui_hover_x;

    for (i = 0; i < n; i++) {
        ax = xs[i] + (i ? gap / 2 : 0);
        bx = xs[i + 1] - (i < n - 1 ? gap - gap / 2 : 0);
        seg.x = ax;
        seg.y = sk->y;
        seg.w = bx - ax;
        seg.h = sk->h;
        SDL_SetRenderDrawColor(renderer, 255, 255, 255, (hx >= xs[i] && hx < xs[i + 1]) ? 80 : 45);
        ui_pill(&seg);
        if (fx > ax) {                          /* how far the playing has got inside this section */
            fill = seg;
            fill.w = FFMAX(FFMIN(fx, bx) - ax, FFMIN(seg.h, seg.w));
            SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 200);
            ui_pill(&fill);
        }
    }
}

''', "chapters: a bar in sections")

patch("    ui_bar(&sk, frac);\n    ui_chapter_ticks(is, &sk);\n", "    ui_seek_bar(is, &sk, frac);\n", "draw the sectioned bar")



# ============================================================ cover art backdrop

patch("    SDL_AudioDeviceID audio_dev_id;  /* this stream's own audio device (two streams play during a crossfade) */\n",
      "    SDL_AudioDeviceID audio_dev_id;  /* this stream's own audio device (two streams play during a crossfade) */\n"
      "    float level;                /* how loud the sound going out is (0 to 1), for the cover art backdrop */\n"
      "    unsigned stream_id;         /* a number that is different for every stream that is opened */\n",
      "stream loudness and id fields")

patch("static char   *xf_failed = NULL;            /* an item that would not open early: do not try again */\n",
      "static char   *xf_failed = NULL;            /* an item that would not open early: do not try again */\n"
      "static unsigned ui_stream_serial = 0;       /* counts the streams opened so far */\n",
      "stream counter")
patch("    is->xf_gain = xf_open_gain;\n", "    is->xf_gain = xf_open_gain;\n    is->stream_id = ++ui_stream_serial;\n",
      "number each stream")

patch("""        vol = (int)(is->audio_volume * is->xf_gain * ui_sleep_gain + 0.5f);
""", """        if (is->audio_buf && !is->paused) {         /* the loudness, for the cover art backdrop */
            const int16_t *sm = (const int16_t *)((uint8_t *)is->audio_buf + is->audio_buf_index);
            int cnt = len1 / 2, k, used = 0;
            double acc = 0;

            for (k = 0; k < cnt; k += 8, used++)
                acc += (double)sm[k] * sm[k];
            is->level = used ? (float)(sqrt(acc / used) / 32768.0) : 0.0f;
        } else {
            is->level = 0.0f;
        }
        vol = (int)(is->audio_volume * is->xf_gain * ui_sleep_gain + 0.5f);
""", "loudness in the audio callback")

patch("static void video_image_display(VideoState *is)\n{\n",
      "static void ui_cover_backdrop(VideoState *is, int flip);\n\nstatic void video_image_display(VideoState *is)\n{\n",
      "backdrop declaration")

patch("    SDL_RenderCopyEx(renderer, is->vid_texture, NULL, &rect, 0, NULL, vp->flip_v ? SDL_FLIP_VERTICAL : 0);\n    set_sdl_yuv_conversion_mode(NULL);\n",
      "    ui_cover_backdrop(is, vp->flip_v);      /* behind the cover art: its own colors, glowing */\n"
      "    SDL_RenderCopyEx(renderer, is->vid_texture, NULL, &rect, 0, NULL, vp->flip_v ? SDL_FLIP_VERTICAL : 0);\n    set_sdl_yuv_conversion_mode(NULL);\n",
      "draw the backdrop before the picture")

patch("/* ----- the big logo on the idle screen ---- */" if False else "static SDL_Texture *ui_make_target(int w, int h)\n{\n",
      r'''/* ----- the cover art backdrop -----
   While an audio file with embedded cover art plays, a field of the cover's own colors fills the window
   behind the picture. It is a soft mesh of 17 x 10 colored points: the colors come from the cover (averaged
   down to that size once per file), the points drift slowly, and the whole thing brightens and swells a
   little with the loudness of the music. */
#define UI_BD_W 17
#define UI_BD_H 10
static SDL_Texture *ui_bd_tex = NULL;           /* the cover, tiny, to read its colors from */
static SDL_Color ui_bd_col[UI_BD_H][UI_BD_W];
static char ui_bd_key[1024] = "";               /* the file the colors were taken from */
static float ui_bd_level = 0.0f;                /* the loudness, smoothed */

static SDL_Texture *ui_make_target(int w, int h);

/* Does this stream show cover art (a picture attached to an audio file)? */
static int ui_has_cover(VideoState *is)
{
    return is && is->video_st && (is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC) && is->vid_texture;
}

/* Average the cover down to one color per mesh point */
static void ui_cover_colors(VideoState *is, int flip)
{
    enum { TW = 192, TH = 108 };
    static uint32_t px[TW * TH];
    SDL_Texture *prev = SDL_GetRenderTarget(renderer);
    int i, j, x, y, ok = 0;

    memset(ui_bd_col, 0, sizeof(ui_bd_col));
    if (!ui_bd_tex)
        ui_bd_tex = ui_make_target(TW, TH);
    if (!ui_bd_tex)
        return;
    SDL_SetRenderTarget(renderer, ui_bd_tex);
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    SDL_RenderClear(renderer);
    SDL_RenderCopyEx(renderer, is->vid_texture, NULL, NULL, 0, NULL, flip ? SDL_FLIP_VERTICAL : 0);
    ok = SDL_RenderReadPixels(renderer, NULL, SDL_PIXELFORMAT_ARGB8888, px, TW * 4) == 0;
    SDL_SetRenderTarget(renderer, prev);
    if (!ok)
        return;
    for (j = 0; j < UI_BD_H; j++) {
        for (i = 0; i < UI_BD_W; i++) {
            int x0 = i * TW / UI_BD_W, x1 = FFMAX((i + 1) * TW / UI_BD_W, x0 + 1);
            int y0 = j * TH / UI_BD_H, y1 = FFMAX((j + 1) * TH / UI_BD_H, y0 + 1);
            double r = 0, g = 0, b = 0, n = 0, lum;

            for (y = y0; y < y1; y++)
                for (x = x0; x < x1; x++) {
                    uint32_t p = px[y * TW + x];

                    r += (p >> 16) & 255;
                    g += (p >> 8) & 255;
                    b += p & 255;
                    n++;
                }
            r /= n;
            g /= n;
            b /= n;
            lum = 0.30 * r + 0.59 * g + 0.11 * b;       /* a little more color than the cover has */
            ui_bd_col[j][i].r = (Uint8)av_clipd(lum + (r - lum) * 1.3, 0, 255);
            ui_bd_col[j][i].g = (Uint8)av_clipd(lum + (g - lum) * 1.3, 0, 255);
            ui_bd_col[j][i].b = (Uint8)av_clipd(lum + (b - lum) * 1.3, 0, 255);
            ui_bd_col[j][i].a = 255;
        }
    }
}

static void ui_cover_backdrop(VideoState *is, int flip)
{
    static int idx[(UI_BD_W - 1) * (UI_BD_H - 1) * 6];
    static int idx_ready = 0;
    SDL_Vertex v[UI_BD_H * UI_BD_W];
    SDL_Rect veil;
    double t = av_gettime_relative() / 1000000.0, u, w, shimmer, bright, swell;
    int i, j, k = 0, W = is->width, H = is->height;
    float target;

    if (!ui_has_cover(is) || W <= 0 || H <= 0)
        return;
    if (strncmp(ui_bd_key, is->filename, sizeof(ui_bd_key) - 1)) {     /* a new file: take its colors */
        snprintf(ui_bd_key, sizeof(ui_bd_key), "%s", is->filename);
        ui_cover_colors(is, flip);
    }
    if (!idx_ready) {
        for (j = 0; j < UI_BD_H - 1; j++)
            for (i = 0; i < UI_BD_W - 1; i++) {
                int a = j * UI_BD_W + i;

                idx[k++] = a;
                idx[k++] = a + 1;
                idx[k++] = a + UI_BD_W;
                idx[k++] = a + 1;
                idx[k++] = a + UI_BD_W + 1;
                idx[k++] = a + UI_BD_W;
            }
        idx_ready = 1;
    }

    target = is->paused ? 0.0f : av_clipf(is->level * 4.0f, 0.0f, 1.0f);
    ui_bd_level += (target - ui_bd_level) * 0.15f;
    bright = 0.62 + 0.38 * ui_bd_level;
    swell = 1.0 + 0.03 * ui_bd_level;
    for (j = 0; j < UI_BD_H; j++) {
        for (i = 0; i < UI_BD_W; i++) {
            SDL_Vertex *p = &v[j * UI_BD_W + i];

            u = i / (double)(UI_BD_W - 1);
            w = j / (double)(UI_BD_H - 1);
            /* the points reach past the window, so their drifting never shows an edge */
            p->position.x = (float)(((u - 0.5) * 1.18 * swell + 0.5 + 0.035 * sin(t * 0.31 + j * 0.9 + i * 0.45)) * W);
            p->position.y = (float)(((w - 0.5) * 1.18 * swell + 0.5 + 0.045 * cos(t * 0.27 + i * 0.7 + j * 0.55)) * H);
            shimmer = bright * (1.0 + 0.10 * sin(t * 0.8 + i * 1.3 + j * 1.7));
            p->color.r = (Uint8)av_clipd(ui_bd_col[j][i].r * shimmer, 0, 255);
            p->color.g = (Uint8)av_clipd(ui_bd_col[j][i].g * shimmer, 0, 255);
            p->color.b = (Uint8)av_clipd(ui_bd_col[j][i].b * shimmer, 0, 255);
            p->color.a = 255;
            p->tex_coord.x = 0;
            p->tex_coord.y = 0;
        }
    }
    SDL_RenderGeometry(renderer, NULL, v, UI_BD_H * UI_BD_W, idx, (UI_BD_W - 1) * (UI_BD_H - 1) * 6);

    /* a dark veil, so the controls on top stay readable */
    veil.x = 0;
    veil.y = 0;
    veil.w = W;
    veil.h = H;
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 45);
    SDL_RenderFillRect(renderer, &veil);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);
}

/* Keep the backdrop moving: the cover is a still picture, so nothing else would redraw the window */
static void ui_cover_tick(VideoState *is)
{
    static int64_t last = 0;
    int64_t now = av_gettime_relative();

    if (ui_has_cover(is) && !is->paused && now - last > 33000) {
        last = now;
        is->force_refresh = 1;
    }
}

static SDL_Texture *ui_make_target(int w, int h)
{
''', "cover backdrop")

patch("        ui_xfade_tick(is);\n", "        ui_xfade_tick(is);\n        ui_cover_tick(is);\n", "keep the backdrop moving")



# ============================================================ the desktop's media controls (MPRIS)

patch("static void refresh_loop_wait_event(VideoState *is, SDL_Event *event) {\n",
      r'''/* ----- the desktop's media controls (MPRIS) -----
   ffplay-custom starts a small helper, "ffplay-mpris", which shows up on the desktop as a media player: the sound
   indicator in the top panel, the media keys and playerctl then control playback. We tell the helper what is
   playing through its stdin; it hands commands back through a file, which is read a few times a second. */
#include <stdarg.h>

static FILE *mpris_out = NULL;              /* the helper's stdin */
static int mpris_started = 0;
static char mpris_cmd_path[PATH_MAX] = "";  /* the file the helper writes commands to */
static int64_t mpris_poll_at = 0;

static void ui_mpris_put(const char *fmt, ...)
{
    va_list ap;

    if (!mpris_out)
        return;
    va_start(ap, fmt);
    if (vfprintf(mpris_out, fmt, ap) < 0 || fflush(mpris_out) != 0) {
        fclose(mpris_out);                  /* the helper is gone */
        mpris_out = NULL;
    }
    va_end(ap);
}

static void ui_mpris_start(void)
{
    const char *home = getenv("HOME");
    char dir[PATH_MAX - 16];
    int fds[2], i;
    pid_t pid;

    if (!home)
        return;
    snprintf(dir, sizeof(dir), "%s/.cache", home);
    mkdir(dir, 0755);
    snprintf(dir, sizeof(dir), "%s/.cache/ffplay-custom", home);
    mkdir(dir, 0755);
    snprintf(mpris_cmd_path, sizeof(mpris_cmd_path), "%s/mpris.cmd", dir);
    unlink(mpris_cmd_path);
    if (pipe(fds) != 0)
        return;
    pid = fork();
    if (pid < 0) {
        close(fds[0]);
        close(fds[1]);
        return;
    }
    if (pid == 0) {                         /* the helper: stdin is our pipe, everything else is closed */
        dup2(fds[0], 0);
        for (i = 3; i < 256; i++)
            close(i);
        execlp("ffplay-mpris", "ffplay-mpris", mpris_cmd_path, (char *)NULL);
        _exit(127);
    }
    close(fds[0]);
    signal(SIGPIPE, SIG_IGN);
    mpris_out = fdopen(fds[1], "w");
}

static void ui_mpris_clean(char *s)
{
    for (; *s; s++)
        if (*s == '\t' || *s == '\n' || *s == '\r')
            *s = ' ';
}

/* Where the playing position is, in seconds from the start of the file */
static double ui_mpris_pos(VideoState *is)
{
    double c = get_master_clock(is);

    if (isnan(c))
        return 0;
    if (is->ic && is->ic->start_time != AV_NOPTS_VALUE)
        c -= is->ic->start_time / (double)AV_TIME_BASE;
    return FFMAX(c, 0.0);
}

static void ui_mpris_seek_to(VideoState *is, double secs)
{
    int64_t ts;

    if (!is || !is->ic || is->ic->duration <= 0 || is->seek_req)
        return;
    secs = av_clipd(secs, 0.0, FFMAX(is->ic->duration / (double)AV_TIME_BASE - 0.5, 0.0));
    ts = (int64_t)(secs * AV_TIME_BASE);
    if (is->ic->start_time != AV_NOPTS_VALUE)
        ts += is->ic->start_time;
    stream_seek(is, ts, 0, 0);
}

/* Tell the helper what is playing: title, artist, album, length and the cover art (saved as a file) */
static void ui_mpris_meta(VideoState *is, int track)
{
    static int art_n = 0;
    char title[300] = "", artist[200] = "", album[200] = "", art[PATH_MAX + 16] = "", file[PATH_MAX], *dot;
    const char *home = getenv("HOME"), *base;
    AVDictionaryEntry *e;
    unsigned i;
    int64_t dur_us = 0;

    if (is->ic) {
        if ((e = av_dict_get(is->ic->metadata, "title", NULL, 0)))
            snprintf(title, sizeof(title), "%s", e->value);
        if ((e = av_dict_get(is->ic->metadata, "artist", NULL, 0)))
            snprintf(artist, sizeof(artist), "%s", e->value);
        if ((e = av_dict_get(is->ic->metadata, "album", NULL, 0)))
            snprintf(album, sizeof(album), "%s", e->value);
        if (is->ic->duration > 0)
            dur_us = is->ic->duration;
    }
    if (!title[0]) {                        /* no title tag: the file name without its ending */
        base = strrchr(is->filename, '/');
        snprintf(title, sizeof(title), "%s", base ? base + 1 : is->filename);
        dot = strrchr(title, '.');
        if (dot && dot != title)
            *dot = 0;
    }
    if (home && is->ic) {
        for (i = 0; i < is->ic->nb_streams; i++) {
            AVStream *st = is->ic->streams[i];

            if ((st->disposition & AV_DISPOSITION_ATTACHED_PIC) && st->attached_pic.size > 0) {
                FILE *f;

                snprintf(file, sizeof(file), "%s/.cache/ffplay-custom/cover-%d.%s", home, art_n++ % 4,
                         st->codecpar->codec_id == AV_CODEC_ID_PNG ? "png" : "jpg");
                f = fopen(file, "wb");
                if (f) {
                    fwrite(st->attached_pic.data, 1, st->attached_pic.size, f);
                    fclose(f);
                    snprintf(art, sizeof(art), "file://%s", file);
                }
                break;
            }
        }
    }
    ui_mpris_clean(title);
    ui_mpris_clean(artist);
    ui_mpris_clean(album);
    ui_mpris_put("meta\t%s\t%s\t%s\t%lld\t%s\t%d\n", title, artist, album, (long long)dur_us, art, track);
}

/* Play from the idle screen: the queue from the top, or on after a sleep stop */
static void ui_idle_play(void)
{
    if (q_count > 0)
        q_forced = (q_hold && q_pos + 1 < q_count) ? q_pos + 1 : 0;
}

static void ui_mpris_command(VideoState *is, const char *line)
{
    long long n;
    double f;

    if (!strcmp(line, "playpause")) {
        if (is)
            toggle_pause(is);
        else
            ui_idle_play();
    } else if (!strcmp(line, "play")) {
        if (!is)
            ui_idle_play();
        else if (is->paused)
            toggle_pause(is);
    } else if (!strcmp(line, "pause")) {
        if (is && !is->paused)
            toggle_pause(is);
    } else if (!strcmp(line, "stop")) {
        if (is) {
            q_hold = 1;                     /* back to the idle screen; play carries on with the next item */
            ui_end_current(is);
        }
    } else if (!strcmp(line, "next")) {
        q_step = 1;
        if (is)
            ui_end_current(is);
        else if (q_count > 0)
            q_forced = av_clip(q_pos + 1, 0, q_count - 1);
    } else if (!strcmp(line, "prev")) {
        if (is && ui_mpris_pos(is) > 3.0) {
            ui_mpris_seek_to(is, 0.0);      /* a few seconds in: back to the start of this item first */
        } else {
            q_step = -1;
            if (is)
                ui_end_current(is);
            else if (q_count > 0)
                q_forced = av_clip(q_pos - 1, 0, q_count - 1);
        }
    } else if (sscanf(line, "seek %lld", &n) == 1) {
        if (is)
            ui_mpris_seek_to(is, ui_mpris_pos(is) + n / 1e6);
    } else if (sscanf(line, "setpos %lld", &n) == 1) {
        if (is)
            ui_mpris_seek_to(is, n / 1e6);
    } else if (sscanf(line, "vol %lf", &f) == 1) {
        if (is) {
            is->audio_volume = av_clip((int)(f * SDL_MIX_MAXVOLUME + 0.5), 0, SDL_MIX_MAXVOLUME);
            is->muted = 0;
        }
    } else if (sscanf(line, "shuffle %lld", &n) == 1) {
        queue_set_shuffle(n != 0);
    } else if (!strcmp(line, "raise")) {
        SDL_RaiseWindow(window);
    } else if (!strcmp(line, "quit")) {
        do_exit(is);
    }
}

/* Read what the helper has been asked to do since the last look */
static void ui_mpris_commands(VideoState *is)
{
    char work[PATH_MAX + 8], line[256];
    FILE *f;

    snprintf(work, sizeof(work), "%s.work", mpris_cmd_path);
    if (rename(mpris_cmd_path, work) != 0)
        return;                             /* nothing was asked */
    f = fopen(work, "r");
    if (!f)
        return;
    while (fgets(line, sizeof(line), f)) {
        line[strcspn(line, "\r\n")] = 0;
        if (line[0])
            ui_mpris_command(is, line);
    }
    fclose(f);
    unlink(work);
}

/* On every turn of the loop: start the helper once, pass on its commands, tell it what changed.
   is = the stream playing now, or NULL on the idle screen. */
static void ui_mpris_tick(VideoState *is)
{
    static unsigned last_id = 0;
    static char last_status[12] = "";
    static int last_shuffle = -1, last_vol = -1, last_can = -1, track = 0;
    static int64_t next_pos = 0;
    const char *status;
    int64_t now = av_gettime_relative();
    int vol, can;

    if (!mpris_started) {
        mpris_started = 1;
        ui_mpris_start();
    }
    if (!mpris_out)
        return;
    if (now >= mpris_poll_at) {
        mpris_poll_at = now + 150000;
        ui_mpris_commands(is);
        if (!mpris_out)
            return;
    }
    if (is && !is->audio_st && !is->video_st)
        return;                             /* still opening: keep saying what it said */
    if ((is ? is->stream_id : 0) != last_id) {         /* a different stream (not just the same address again) */
        last_id = is ? is->stream_id : 0;
        last_status[0] = 0;
        next_pos = 0;
        if (is)
            ui_mpris_meta(is, ++track);
    }
    if (is && now >= next_pos) {
        next_pos = now + 1000000;
        ui_mpris_put("pos\t%lld\n", (long long)(ui_mpris_pos(is) * 1e6));
    }
    status = !is ? "Stopped" : is->paused ? "Paused" : "Playing";
    if (strcmp(status, last_status)) {
        snprintf(last_status, sizeof(last_status), "%s", status);
        ui_mpris_put("status\t%s\n", status);
    }
    vol = is ? is->audio_volume : -1;
    if (vol != last_vol) {
        last_vol = vol;
        if (vol >= 0)
            ui_mpris_put("vol\t%.3f\n", vol / (double)SDL_MIX_MAXVOLUME);
    }
    if (q_shuffle != last_shuffle) {
        last_shuffle = q_shuffle;
        ui_mpris_put("shuffle\t%d\n", q_shuffle ? 1 : 0);
    }
    can = q_count > 0;
    if (can != last_can) {
        last_can = can;
        ui_mpris_put("can\t%d\t%d\n", can, can);
    }
}

static void refresh_loop_wait_event(VideoState *is, SDL_Event *event) {
''', "media controls (MPRIS)")

patch("        ui_cover_tick(is);\n", "        ui_cover_tick(is);\n        ui_mpris_tick(is);\n", "media controls tick")
patch("        ui_sleep_tick(NULL);\n", "        ui_sleep_tick(NULL);\n        ui_mpris_tick(NULL);\n", "media controls tick on the idle screen")

# Everything matched, so it is safe to write
open(path, "w").write(src)
print("Patched", path)
