#!/usr/bin/env python3
# Update 8 for ffplay-custom: the cover-flow queue.
#   * While audio plays, the window shows the queue as a row of album covers. The playing item is big in the
#     middle with a spinning disc sliding out from behind it; the others are smaller covers on both sides, with no
#     disc. Video items show a thumbnail. Click a cover to play it (click the playing one to pause / resume).
#   * Swipe sideways (two fingers) to cascade through the queue; after 5 s it glides back to the playing item.
#   * Swipe up / down changes the volume, and the direction is reversed from before.
#     The "Mouse wheel" preference now reads Volume + queue / Seek + queue / Off.
#   * Above the seek bar, a row of moving bars (the loudness of the last seconds). The seek bar's row gets
#     a single-arrowhead previous button at its left end and next, shuffle and repeat at its right end.
#     Repeat goes off, queue, one item.
#   * Video files still play full screen; the cover-flow comes back when an audio item plays.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v6.py (v7 is optional).
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_flow_draw(VideoState *is)\n{" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_aurora_backdrop" not in src or "ui_q_anim_t0" not in src:
    print("Apply patch_queue_v6.py first. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


# ============================================================ hooks in the drawing code

patch("static void ui_cover_backdrop(VideoState *is, int flip);\n\nstatic void video_image_display(VideoState *is)\n",
      "static void ui_cover_backdrop(VideoState *is, int flip);\n"
      "static int ui_has_cover(VideoState *is);\n"
      "static void ui_flow_draw(VideoState *is);\n"
      "static int ui_flow_wants_redraw(VideoState *is);\n"
      "static void ui_flow_swipe(VideoState *is, SDL_Event *ev);\n\n"
      "static void video_image_display(VideoState *is)\n",
      "forward declarations")

patch("    SDL_RenderCopyEx(renderer, is->vid_texture, NULL, &rect, 0, NULL, vp->flip_v ? SDL_FLIP_VERTICAL : 0);\n",
      "    if (!ui_has_cover(is))                  /* a cover is drawn by the queue view instead (ui_flow_draw) */\n"
      "        SDL_RenderCopyEx(renderer, is->vid_texture, NULL, &rect, 0, NULL, vp->flip_v ? SDL_FLIP_VERTICAL : 0);\n",
      "the cover picture moves into the queue view")

patch("        video_image_display(is);\n    if (is)\n        ui_draw(is);\n",
      "        video_image_display(is);\n    if (is)\n        ui_flow_draw(is);\n    if (is)\n        ui_draw(is);\n",
      "queue view behind the menu glass")

patch("        else if (is->video_st)\n            video_image_display(is);\n        is->height = full_h;\n    }\n    ui_draw(is);\n",
      "        else if (is->video_st)\n            video_image_display(is);\n        is->height = full_h;\n    }\n    ui_flow_draw(is);\n    ui_draw(is);\n",
      "queue view in the main picture")

# ============================================================ the bar row: previous, next, shuffle, repeat

patch("static void ui_draw(VideoState *is)\n{\n    SDL_Rect sk, vo;\n",
      "static void ui_ctrl_draw(VideoState *is, const SDL_Rect *sk);\n\nstatic void ui_draw(VideoState *is)\n{\n    SDL_Rect sk, vo;\n",
      "bar buttons declaration")

patch("    ui_seek_bar(is, &sk, frac);\n    ui_bar(&vo, vfrac);\n",
      "    ui_seek_bar(is, &sk, frac);\n    ui_ctrl_draw(is, &sk);\n    ui_bar(&vo, vfrac);\n",
      "draw the bar buttons")

patch("    sk->x = margin_x;\n    sk->y = ty;\n    sk->h = bar_h;\n    sk->w = vo->x - 16 - sk->x;\n",
      "    sk->x = margin_x + 28;                  /* room for the previous button on the left */\n"
      "    sk->y = ty;\n    sk->h = bar_h;\n"
      "    sk->w = vo->x - 104 - sk->x;            /* room for next, shuffle and repeat on the right */\n",
      "make room on the bar row")

patch("static int ui_mouse(VideoState *is, SDL_Event *ev)\n{\n    SDL_Rect sk, vo;\n    int x;\n",
      "static int ui_flow_click(VideoState *is, int x, int y);\nstatic int ui_ctrl_click(VideoState *is, int x);\n\n"
      "static int ui_mouse(VideoState *is, SDL_Event *ev)\n{\n    SDL_Rect sk, vo;\n    int x;\n",
      "mouse declarations")

patch("        if (ev->button.button != SDL_BUTTON_LEFT || ev->button.y < is->height - UI_BAR_H)\n            return 0;\n        x = ev->button.x;\n",
      "        if (ev->button.button == SDL_BUTTON_LEFT && ui_flow_click(is, ev->button.x, ev->button.y))\n"
      "            return 1;                       /* a click on a cover */\n"
      "        if (ev->button.button != SDL_BUTTON_LEFT || ev->button.y < is->height - UI_BAR_H)\n            return 0;\n"
      "        x = ev->button.x;\n"
      "        if (ui_ctrl_click(is, x))\n            return 1;                       /* previous, next, shuffle or repeat */\n",
      "clicks on covers and bar buttons")

# ============================================================ repeat

patch("static int queue_next(void)\n{\n    if (q_forced >= 0 && q_forced < q_count)\n        return q_forced;                        /* the user clicked an item */\n    return FFMAX(q_pos + q_step, 0);            /* previous on the first item replays it */\n}\n",
      "static int q_repeat = 0;        /* 0 = off, 1 = repeat the queue, 2 = repeat the item playing */\n"
      "static int q_user_ended = 0;    /* 1 = the item that just ended was ended by the user, not by reaching its end */\n\n"
      "static int queue_next(void)\n{\n    int n;\n\n"
      "    if (q_forced >= 0 && q_forced < q_count)\n        return q_forced;                        /* the user clicked an item */\n"
      "    if (q_repeat == 2 && !q_user_ended && q_pos >= 0 && q_pos < q_count)\n        return q_pos;                           /* repeat one: play it again */\n"
      "    n = FFMAX(q_pos + q_step, 0);               /* previous on the first item replays it */\n"
      "    if (q_repeat == 1 && q_step > 0 && n >= q_count && q_count > 0)\n        n = 0;                                  /* repeat all: back to the top */\n"
      "    return n;\n}\n",
      "repeat in queue_next")

patch("        ui_user_skip = 0;\n        next = queue_next();                    /* the next item */\n",
      "        q_user_ended = ui_user_skip;\n        ui_user_skip = 0;\n        next = queue_next();                    /* the next item */\n",
      "remember how the item ended")

patch("q_forced >= 0 || q_step != 1 ||\n        next >= q_count",
      "q_forced >= 0 || q_step != 1 || q_repeat == 2 ||\n        next >= q_count",
      "no crossfade when repeating one item")

# ============================================================ swipes

patch("    default: snprintf(out, size, \"%s\", cfg_wheel == 1 ? \"Volume\" : cfg_wheel == 2 ? \"Seek\" : \"Off\"); break;\n",
      "    default: snprintf(out, size, \"%s\", cfg_wheel == 1 ? \"Volume + queue\" : cfg_wheel == 2 ? \"Seek + queue\" : \"Off\"); break;\n",
      "mouse wheel preference text")

patch("    if (!cfg_wheel || ui_menu_open || ui_prefs_open)\n        return;\n#if SDL_VERSION_ATLEAST(2, 0, 18)\n    amount = ev->wheel.preciseY;\n",
      "    if (!cfg_wheel || ui_menu_open || ui_prefs_open)\n        return;\n"
      "    {\n        double ax, ay;\n#if SDL_VERSION_ATLEAST(2, 0, 18)\n        ax = ev->wheel.preciseX;\n        ay = ev->wheel.preciseY;\n"
      "#else\n        ax = ev->wheel.x;\n        ay = ev->wheel.y;\n#endif\n"
      "        if (FFABS(ax) > FFABS(ay)) {            /* a sideways swipe moves through the queue */\n"
      "            ui_flow_swipe(is, ev);\n            return;\n        }\n    }\n"
      "#if SDL_VERSION_ATLEAST(2, 0, 18)\n    amount = ev->wheel.preciseY;\n",
      "sideways swipes")

patch("            update_volume(is, steps > 0 ? 1 : -1, SDL_VOLUME_STEP);\n",
      "            update_volume(is, steps > 0 ? -1 : 1, SDL_VOLUME_STEP);        /* reversed */\n",
      "volume swipe direction reversed")

patch("    if (ui_q_open && av_gettime_relative() - ui_q_anim_t0 < 700000)\n        is->force_refresh = 1;                  /* the queue rows are still fading in */\n",
      "    if (ui_flow_wants_redraw(is))\n        is->force_refresh = 1;                  /* the disc turns, the bars move, the covers glide */\n"
      "    if (ui_q_open && av_gettime_relative() - ui_q_anim_t0 < 700000)\n        is->force_refresh = 1;                  /* the queue rows are still fading in */\n",
      "keep redrawing")

# ============================================================ the queue view

patch("static void video_display(VideoState *is)\n{\n    if (!is->width)\n        video_open(is);\n",
      r'''/* ----- the cover-flow queue: shown while audio plays -----
   Every item in the queue is a cover. The one playing is large in the middle with a spinning disc behind it; the
   others sit on both sides, smaller. Pictures are read in the background: the picture attached to an audio file,
   or a frame from near the start of a video. */
typedef struct UiCov {
    char *path;
    int state;                  /* 0 = being read, 1 = pixels ready, 2 = texture ready, 3 = no picture */
    uint8_t *px;
    int w, h;
    SDL_Texture *tex;
} UiCov;

static UiCov *ui_cov = NULL;
static int ui_cov_n = 0, ui_cov_cap = 0;
static SDL_mutex *ui_cov_mu = NULL;
static SDL_cond *ui_cov_cv = NULL;
static int ui_cov_todo[1024];
static unsigned ui_cov_head = 0, ui_cov_tail = 0;

/* Read a picture for a file: RGBA pixels, at most 256 on the long side. NULL if there is none. */
static uint8_t *ui_cov_decode(const char *path, int *ow, int *oh)
{
    AVFormatContext *ic = NULL;
    AVCodecContext *cc = NULL;
    AVFrame *fr = NULL;
    AVPacket *pk = NULL;
    struct SwsContext *sws = NULL;
    const AVCodec *codec;
    AVStream *st = NULL;
    uint8_t *out = NULL, *dst[4] = { NULL };
    int ls[4] = { 0 }, i, n, w, h, got = 0;

    if (strstr(path, "://"))
        return NULL;
    if (avformat_open_input(&ic, path, NULL, NULL) < 0)
        return NULL;
    avformat_find_stream_info(ic, NULL);
    for (i = 0; i < (int)ic->nb_streams; i++)
        if (ic->streams[i]->disposition & AV_DISPOSITION_ATTACHED_PIC) {
            st = ic->streams[i];
            break;
        }
    for (i = 0; !st && i < (int)ic->nb_streams; i++)
        if (ic->streams[i]->codecpar->codec_type == AVMEDIA_TYPE_VIDEO)
            st = ic->streams[i];
    if (!st)
        goto end;
    codec = avcodec_find_decoder(st->codecpar->codec_id);
    cc = codec ? avcodec_alloc_context3(codec) : NULL;
    if (!cc || avcodec_parameters_to_context(cc, st->codecpar) < 0 || avcodec_open2(cc, codec, NULL) < 0)
        goto end;
    fr = av_frame_alloc();
    pk = av_packet_alloc();
    if (!fr || !pk)
        goto end;
    if (st->disposition & AV_DISPOSITION_ATTACHED_PIC) {
        if (avcodec_send_packet(cc, &st->attached_pic) >= 0) {
            avcodec_send_packet(cc, NULL);
            got = avcodec_receive_frame(cc, fr) >= 0;
        }
    } else {
        if (ic->duration > 0)
            av_seek_frame(ic, -1, ic->duration / 10, AVSEEK_FLAG_BACKWARD);     /* a frame a tenth of the way in */
        for (n = 0; !got && n < 400 && av_read_frame(ic, pk) >= 0; n++) {
            if (pk->stream_index == st->index && avcodec_send_packet(cc, pk) >= 0)
                got = avcodec_receive_frame(cc, fr) >= 0;
            av_packet_unref(pk);
        }
    }
    if (!got || fr->width <= 0 || fr->height <= 0)
        goto end;
    if (fr->width >= fr->height) {
        w = 256;
        h = FFMAX(fr->height * 256 / fr->width, 1);
    } else {
        h = 256;
        w = FFMAX(fr->width * 256 / fr->height, 1);
    }
    sws = sws_getContext(fr->width, fr->height, fr->format, w, h, AV_PIX_FMT_RGBA, SWS_BILINEAR, NULL, NULL, NULL);
    out = av_malloc((size_t)w * h * 4);
    if (!sws || !out) {
        av_freep(&out);
        goto end;
    }
    dst[0] = out;
    ls[0] = w * 4;
    sws_scale(sws, (const uint8_t *const *)fr->data, fr->linesize, 0, fr->height, dst, ls);
    *ow = w;
    *oh = h;
end:
    sws_freeContext(sws);
    av_frame_free(&fr);
    av_packet_free(&pk);
    avcodec_free_context(&cc);
    avformat_close_input(&ic);
    return out;
}

static int ui_cov_thread(void *arg)
{
    char *p;
    uint8_t *px;
    int k, w, h;

    for (;;) {
        SDL_LockMutex(ui_cov_mu);
        while (ui_cov_head >= ui_cov_tail)
            SDL_CondWait(ui_cov_cv, ui_cov_mu);
        k = ui_cov_todo[ui_cov_head++ % 1024];
        p = av_strdup(ui_cov[k].path);
        SDL_UnlockMutex(ui_cov_mu);

        w = h = 0;
        px = p ? ui_cov_decode(p, &w, &h) : NULL;
        av_free(p);

        SDL_LockMutex(ui_cov_mu);
        ui_cov[k].px = px;
        ui_cov[k].w = w;
        ui_cov[k].h = h;
        ui_cov[k].state = px ? 1 : 3;
        SDL_UnlockMutex(ui_cov_mu);
    }
    return 0;
}

/* The picture of a file as a texture, or NULL while it is still being read (or if there is none) */
static SDL_Texture *ui_cov_get(const char *path, int *w, int *h)
{
    SDL_Texture *t = NULL;
    UiCov *grown, *c;
    SDL_Thread *th;
    int i, found = -1;

    if (!path)
        return NULL;
    if (!ui_cov_mu) {
        ui_cov_mu = SDL_CreateMutex();
        ui_cov_cv = SDL_CreateCond();
        if (!ui_cov_mu || !ui_cov_cv)
            return NULL;
        th = SDL_CreateThread(ui_cov_thread, "cover", NULL);
        if (th)
            SDL_DetachThread(th);
    }
    SDL_LockMutex(ui_cov_mu);
    for (i = 0; i < ui_cov_n; i++)
        if (!strcmp(ui_cov[i].path, path)) {
            found = i;
            break;
        }
    if (found < 0 && ui_cov_n < 1000) {
        if (ui_cov_n >= ui_cov_cap) {
            grown = av_realloc_array(ui_cov, FFMAX(ui_cov_cap * 2, 64), sizeof(*ui_cov));
            if (grown) {
                ui_cov = grown;
                ui_cov_cap = FFMAX(ui_cov_cap * 2, 64);
            }
        }
        if (ui_cov_n < ui_cov_cap) {
            c = &ui_cov[ui_cov_n];
            memset(c, 0, sizeof(*c));
            c->path = av_strdup(path);
            if (c->path) {
                found = ui_cov_n++;
                ui_cov_todo[ui_cov_tail++ % 1024] = found;
                SDL_CondSignal(ui_cov_cv);
            }
        }
    }
    if (found >= 0) {
        c = &ui_cov[found];
        if (c->state == 1) {                    /* the pixels are ready: make the texture here, in the drawing thread */
            c->tex = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STATIC, c->w, c->h);
            if (c->tex) {
                SDL_UpdateTexture(c->tex, NULL, c->px, c->w * 4);
                SDL_SetTextureBlendMode(c->tex, SDL_BLENDMODE_BLEND);
            }
            av_freep(&c->px);
            c->state = c->tex ? 2 : 3;
        }
        if (c->state == 2) {
            t = c->tex;
            *w = c->w;
            *h = c->h;
        }
    }
    SDL_UnlockMutex(ui_cov_mu);
    return t;
}

/* A filled slice of a circle (a pie) in one color */
static void ui_fan(double cx, double cy, double r, double a0, double a1, int seg, int cr, int cg, int cb, int ca)
{
    SDL_Vertex v[50];
    int idx[48 * 3], k;
    SDL_Color c;

    seg = av_clip(seg, 1, 48);
    c.r = (Uint8)cr;
    c.g = (Uint8)cg;
    c.b = (Uint8)cb;
    c.a = (Uint8)av_clip(ca, 0, 255);
    v[0].position.x = (float)cx;
    v[0].position.y = (float)cy;
    v[0].color = c;
    v[0].tex_coord.x = 0;
    v[0].tex_coord.y = 0;
    for (k = 0; k <= seg; k++) {
        double a = a0 + (a1 - a0) * k / seg;

        v[k + 1].position.x = (float)(cx + r * cos(a));
        v[k + 1].position.y = (float)(cy + r * sin(a));
        v[k + 1].color = c;
        v[k + 1].tex_coord.x = 0;
        v[k + 1].tex_coord.y = 0;
    }
    for (k = 0; k < seg; k++) {
        idx[k * 3] = 0;
        idx[k * 3 + 1] = k + 1;
        idx[k * 3 + 2] = k + 2;
    }
    SDL_RenderGeometry(renderer, NULL, v, seg + 2, idx, seg * 3);
}

/* The spinning disc: dark grooves, light turning across them, and a label in your bar color */
static void ui_flow_disc(double cx, double cy, double r, double ang, int a)
{
    const double two_pi = 6.28318531, pi = 3.14159265;
    double k;
    int i;

    ui_fan(cx, cy, r, 0, two_pi, 48, 16, 16, 20, a);
    for (k = 0.94, i = 0; k > 0.45; k -= 0.08, i++)
        ui_fan(cx, cy, r * k, 0, two_pi, 48, i % 2 ? 30 : 12, i % 2 ? 30 : 12, i % 2 ? 36 : 15, a);
    ui_fan(cx, cy, r * 0.97, ang, ang + 0.55, 8, 255, 255, 255, a * 26 / 255);
    ui_fan(cx, cy, r * 0.97, ang + pi, ang + pi + 0.55, 8, 255, 255, 255, a * 26 / 255);
    ui_fan(cx, cy, r * 0.34, 0, two_pi, 32, cfg_bar_r, cfg_bar_g, cfg_bar_b, a);
    ui_fan(cx + cos(ang) * r * 0.2, cy + sin(ang) * r * 0.2, r * 0.05, 0, two_pi, 12, 245, 245, 245, a);
    ui_fan(cx, cy, r * 0.05, 0, two_pi, 12, 14, 14, 18, a);
}

static int ui_flow_target = -1;         /* the item the row is gliding to (the playing one, or one swiped to) */
static int ui_flow_last_q = -2;
static double ui_flow_pos = 0.0;        /* the item in the middle of the row, between two items while it glides */
static int64_t ui_flow_touch = 0;       /* when the row was last swiped */
static int64_t ui_flow_t = 0;
static double ui_flow_ang = 0.0;        /* how far the disc has turned */
static int ui_flow_moving = 0;
static int ui_flow_n = 0;
static struct {
    SDL_Rect r;
    int idx;
} ui_flow_hit[16];                      /* the covers drawn last time, far to near, for clicks */

/* Is the queue view showing? Audio, or audio with a cover; a video file plays full screen instead. */
static int ui_flow_on(VideoState *is)
{
    return is && is->audio_st && q_count > 0 && q_pos >= 0 && q_pos < q_count &&
           (!is->video_st || (is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC));
}

static int ui_flow_wants_redraw(VideoState *is)
{
    return ui_flow_on(is) && (!is->paused || ui_flow_moving);
}

static void ui_flow_draw(VideoState *is)
{
    enum { NEQ = 72 };
    static float eq[NEQ], lvl = 0.0f;
    static int64_t eq_at = 0;
    int64_t now = av_gettime_relative();
    int W = is->width, H = is->height, i, j, pass, cx, cy, ci, nb, bw, maxh, base, playx;
    double dt, B, d, ad, dc, sc, off, s, t = now / 1000000.0, frac = 0.0, pitch, amp;
    SDL_Rect sk, vo, tile, dst, bar;
    SDL_Texture *tex;
    char name[320], num[48];
    int tw, th, al, md;

    if (!ui_flow_on(is) || W < 260 || H < 200) {
        ui_flow_n = 0;
        ui_flow_moving = 0;
        return;
    }
    dt = ui_flow_t ? av_clipd((now - ui_flow_t) / 1000000.0, 0.0, 0.1) : 0.0;
    ui_flow_t = now;
    if (q_pos != ui_flow_last_q) {              /* a new item started: the row glides to it */
        ui_flow_last_q = q_pos;
        ui_flow_target = q_pos;
        ui_flow_touch = 0;
    }
    if (ui_flow_touch && now - ui_flow_touch > 5000000) {       /* 5 s after the last swipe: back to the playing item */
        ui_flow_target = q_pos;
        ui_flow_touch = 0;
    }
    ui_flow_target = av_clip(ui_flow_target, 0, q_count - 1);
    ui_flow_pos += (ui_flow_target - ui_flow_pos) * (1.0 - exp(-dt * 10.0));
    ui_flow_moving = fabs(ui_flow_target - ui_flow_pos) > 0.003;
    if (!ui_flow_moving)
        ui_flow_pos = ui_flow_target;
    if (!is->paused)
        ui_flow_ang = fmod(ui_flow_ang + dt * 2.2, 6.28318531);
    lvl += ((is->paused ? 0.0f : av_clipf(is->level * 4.0f, 0.0f, 1.0f)) - lvl) * 0.25f;
    if (now - eq_at > 45000 || now < eq_at) {
        memmove(eq, eq + 1, sizeof(float) * (NEQ - 1));
        eq[NEQ - 1] = lvl;
        eq_at = now;
    }

    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    B = FFMIN(W * 0.30, H * 0.44);
    cx = W / 2 - (int)(B * 0.12);
    cy = (int)(H * 0.40);
    ui_flow_n = 0;
    ci = av_clip((int)(ui_flow_pos + 0.5), 0, q_count - 1);

    for (pass = 4; pass >= 0; pass--) {
        for (i = ci - 5; i <= ci + 5; i++) {
            if (i < 0 || i >= q_count || (int)(fabs(i - ui_flow_pos) + 0.5) != pass)
                continue;
            d = i - ui_flow_pos;
            ad = fabs(d);
            dc = av_clipd(d, -1.0, 1.0);
            sc = 1.0 - 0.40 * FFMIN(ad, 1.0) - 0.06 * FFMAX(FFMIN(ad, 3.0) - 1.0, 0.0);
            off = B * (0.86 * dc + 0.42 * (d - dc)) + (d > 0 ? B * 0.30 * FFMIN(d, 1.0) : 0.0);
            s = B * sc;
            tile.x = cx + (int)(off - s / 2);
            tile.y = cy - (int)(s / 2);
            tile.w = (int)s;
            tile.h = (int)s;
            al = (int)(255 * av_clipd(1.15 - 0.30 * ad, 0.15, 1.0));
            md = (int)(255 * av_clipd(1.0 - 0.20 * FFMIN(ad, 2.0), 0.4, 1.0));

            if (ad < 1.5)
                ui_shadow(&tile, 10);
            if (i == q_pos)                     /* the disc sits behind the cover of the item playing */
                ui_flow_disc(tile.x + s * 0.78, cy, s * 0.47, ui_flow_ang, al);
            SDL_SetRenderDrawColor(renderer, 24, 24, 28, al * 220 / 255);
            ui_rr_fill(&tile, 8);
            tex = ui_cov_get(q_items[i], &tw, &th);
            if (tex) {
                dst = tile;
                if (tw >= th)
                    dst.h = FFMAX(tile.w * th / tw, 1);
                else
                    dst.w = FFMAX(tile.h * tw / th, 1);
                dst.x = tile.x + (tile.w - dst.w) / 2;
                dst.y = tile.y + (tile.h - dst.h) / 2;
                SDL_SetTextureAlphaMod(tex, (Uint8)al);
                SDL_SetTextureColorMod(tex, (Uint8)md, (Uint8)md, (Uint8)md);
                SDL_RenderCopy(renderer, tex, NULL, &dst);
            } else {                            /* no picture (yet): a tile with the first letter */
                ui_q_name(i, name, 300);
                num[0] = name[0] && (unsigned char)name[0] < 0x80 ? name[0] : '#';
                num[1] = 0;
                SDL_SetRenderDrawColor(renderer, cfg_bar_r / 3 + 20, cfg_bar_g / 3 + 20, cfg_bar_b / 3 + 24, al);
                ui_rr_fill(&tile, 8);
                ui_label_c(tile.x + tile.w / 2, tile.y + tile.h / 2, num, FFMAX((int)(s * 0.4), 12), 240, 240, 240, al);
            }
            if (ui_flow_n < 16) {
                ui_flow_hit[ui_flow_n].r = tile;
                ui_flow_hit[ui_flow_n].idx = i;
                ui_flow_n++;
            }
        }
    }

    ui_q_name(ci, name, 300);                   /* the name under the middle cover */
    ui_fit_text(name, 24, (int)(W * 0.8));
    ui_label_c(W / 2, cy + (int)(B / 2) + 40, name, 24, 255, 255, 255, 255);
    snprintf(num, sizeof(num), "%d / %d", ci + 1, q_count);
    ui_label_c(W / 2, cy + (int)(B / 2) + 70, num, 15, 175, 175, 175, 255);

    if (!(cursor_hidden && !is->paused)) {      /* the bars above the seek bar come and go with it */
        ui_layout(is, &sk, &vo);
        if (is->ic && is->ic->duration > 0) {
            double pos = get_master_clock(is);

            if (!isnan(pos)) {
                if (is->ic->start_time != AV_NOPTS_VALUE)
                    pos -= is->ic->start_time / (double)AV_TIME_BASE;
                frac = av_clipd(pos / (is->ic->duration / (double)AV_TIME_BASE), 0.0, 1.0);
            }
        }
        if (ui_drag == 1 || av_gettime_relative() < ui_hold_until)
            frac = ui_seek_frac;
        nb = NEQ;
        pitch = (double)sk.w / nb;
        bw = FFMAX((int)(pitch * 0.55), 2);
        maxh = FFMIN(70, H / 8);
        base = sk.y - 12;
        playx = sk.x + (int)(frac * sk.w);
        for (j = 0; j < nb; j++) {
            amp = eq[j] * (0.55 + 0.45 * fabs(sin(j * 2.3 + t * 3.7)));
            bar.x = sk.x + (int)(j * pitch);
            bar.h = 3 + (int)(amp * maxh);
            bar.w = bw;
            bar.y = base - bar.h;
            if (bar.x < playx)
                SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 235);
            else
                SDL_SetRenderDrawColor(renderer, 255, 255, 255, 90);
            SDL_RenderFillRect(renderer, &bar);
        }
    }
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);
}

/* A click on a cover: play that item (or pause / resume if it is the one playing) */
static int ui_flow_click(VideoState *is, int x, int y)
{
    int i;

    if (!ui_flow_on(is) || ui_menu_open || ui_prefs_open)
        return 0;
    for (i = ui_flow_n - 1; i >= 0; i--) {      /* the last one drawn is the nearest */
        const SDL_Rect *r = &ui_flow_hit[i].r;

        if (x >= r->x && x < r->x + r->w && y >= r->y && y < r->y + r->h) {
            if (ui_flow_hit[i].idx == q_pos) {
                toggle_pause(is);
            } else {
                q_forced = ui_flow_hit[i].idx;
                ui_end_current(is);
            }
            return 1;
        }
    }
    return 0;
}

/* A sideways swipe (two fingers on the touchpad): step through the queue */
static void ui_flow_swipe(VideoState *is, SDL_Event *ev)
{
    static double acc = 0.0;
    static int64_t last = 0;
    int64_t now = av_gettime_relative();
    double amount;
    int steps;

    if (!ui_flow_on(is) || q_count < 2)
        return;
#if SDL_VERSION_ATLEAST(2, 0, 18)
    amount = ev->wheel.preciseX;
#else
    amount = ev->wheel.x;
#endif
    if (ev->wheel.direction == SDL_MOUSEWHEEL_FLIPPED)
        amount = -amount;
    if (now - last > 300000 || amount * acc < 0.0)
        acc = 0.0;
    last = now;
    acc += amount;
    steps = (int)acc;
    if (!steps)
        return;
    acc -= steps;
    if (ui_flow_target < 0)
        ui_flow_target = q_pos;
    ui_flow_target = av_clip(ui_flow_target + steps, 0, q_count - 1);
    ui_flow_touch = now;
    is->force_refresh = 1;
}

/* The buttons on the seek bar's row: previous at the left end; next, shuffle and repeat at the right end */
static void ui_ctrl_draw(VideoState *is, const SDL_Rect *sk)
{
    int cy = sk->y + sk->h / 2, ex = sk->x + sk->w;

    (void)is;
    SDL_SetRenderDrawColor(renderer, 235, 235, 235, 215);
    ui_tri(34 - 5, cy, 10, 12, -1);             /* one arrowhead each, not two */
    ui_tri(ex + 16 - 5, cy, 10, 12, 1);
    if (q_shuffle)
        ui_shuffle_icon(ex + 44, cy, av_clip(cfg_bar_r + 60, 0, 255), av_clip(cfg_bar_g + 60, 0, 255),
                        av_clip(cfg_bar_b + 60, 0, 255), 255);
    else
        ui_shuffle_icon(ex + 44, cy, 235, 235, 235, 150);
    if (q_repeat)
        SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 60, 0, 255), av_clip(cfg_bar_g + 60, 0, 255),
                               av_clip(cfg_bar_b + 60, 0, 255), 255);
    else
        SDL_SetRenderDrawColor(renderer, 235, 235, 235, 150);
    ui_q_line(ex + 65, cy - 5, ex + 79, cy - 5);        /* the repeat loop */
    ui_q_line(ex + 65, cy + 5, ex + 79, cy + 5);
    ui_q_line(ex + 64, cy - 4, ex + 64, cy + 4);
    ui_q_line(ex + 80, cy - 4, ex + 80, cy + 4);
    ui_tri(ex + 74, cy - 5, 7, 8, 1);
    ui_tri(ex + 63, cy + 5, 7, 8, -1);
    if (q_repeat == 2)
        ui_label_c(ex + 72, cy, "1", 11, 245, 245, 245, 255);
}

/* A click on one of those buttons. Returns 1 if it was one. */
static int ui_ctrl_click(VideoState *is, int x)
{
    SDL_Rect sk, vo;
    int ex;

    ui_layout(is, &sk, &vo);
    ex = sk.x + sk.w;
    if (FFABS(x - 34) <= 12) {
        q_step = -1;                            /* the main loop plays the item before this one */
        ui_end_current(is);
    } else if (FFABS(x - (ex + 16)) <= 12) {
        q_step = 1;
        ui_end_current(is);
    } else if (FFABS(x - (ex + 44)) <= 13) {
        queue_set_shuffle(!q_shuffle);
    } else if (FFABS(x - (ex + 72)) <= 13) {
        q_repeat = (q_repeat + 1) % 3;
    } else {
        return 0;
    }
    is->force_refresh = 1;
    return 1;
}

static void video_display(VideoState *is)
{
    if (!is->width)
        video_open(is);
''', "the cover-flow queue")

open(path, "w").write(src)
print("Patched", path)
