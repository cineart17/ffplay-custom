#!/usr/bin/env python3
# Update 14 for ffplay-custom (on top of patch_queue_v13.py).
#   * The small titles under the side covers now tilt with their covers: they follow the cover's lower edge, and
#     shrink toward the same edge, so a title and its cover look like one card.
#   * A turned cover is also a little narrower (14% at full turn), with the edge nearest the middle staying put,
#     so more of the cover behind it shows. It eases in and out as the row glides.
#   * The disc turns slowly now (about one turn every 7 seconds).
#   * The bars above the seek line show the whole track: the track is read in the background (low priority, a few
#     seconds for most songs) and every bar is how loud that stretch of the song is. The part already played is in your
#     bar color; a small pulse follows the playhead. Until the scan finishes (or if a file can't be read) the bars show
#     the loudness of the last few seconds, as before.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v13.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_wave_scan" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_flow_quad" not in src:
    print("Apply patch_queue_v13.py first. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


# ============================================================ a slower disc

patch("        ui_flow_ang = fmod(ui_flow_ang + dt * 2.2, 6.28318531);\n",
      "        ui_flow_ang = fmod(ui_flow_ang + dt * 0.9, 6.28318531);        /* about one turn every 7 seconds */\n",
      "a slower disc")

# ============================================================ turned covers are narrower

patch("""            ui_flow_rects[e].x = cx + (int)(off - s / 2);
            ui_flow_rects[e].y = cy - (int)(s / 2);
            ui_flow_rects[e].w = (int)s;
            ui_flow_rects[e].h = (int)s;
""", """            ui_flow_rects[e].w = (int)(s * (1.0 - 0.14 * FFMIN(ad, 1.0)));      /* a turned cover is narrower */
            ui_flow_rects[e].h = (int)s;
            ui_flow_rects[e].x = cx + (int)(off - s / 2);
            if (d < 0)
                ui_flow_rects[e].x += (int)s - ui_flow_rects[e].w;              /* the edge nearest the middle stays put */
            ui_flow_rects[e].y = cy - (int)(s / 2);
""", "narrower turned covers")

# ============================================================ titles that tilt, and the waveform

patch("""                if (i != ci && vw >= 48) {      /* a small, faded title under the part that shows */
                    ui_q_name(i, name, 300);
                    ui_fit_text(name, 15, vw);
                    ui_label_c(vx0 + vw / 2, tile.y + tile.h + 18, name, 15, 235, 235, 235, al * 55 / 100);
                }
""", """                if (i != ci && vw >= 48) {      /* a small, faded title under the part that shows, tilted with its cover */
                    ui_q_name(i, name, 300);
                    ui_fit_text(name, 15, vw);
                    ui_flow_title(name, 15, vx0 + vw / 2, &tile, av_clipd(d, -1.0, 1.0), al * 55 / 100);
                }
""", "titles tilt with their covers")

patch("static void ui_flow_draw(VideoState *is)\n{\n    enum { NEQ = 72 };\n",
      r'''/* A title drawn as part of a turned card: it hangs under the cover's lower edge and follows it (same tilt as the cover) */
static void ui_flow_title(const char *s, int px, int cx, const SDL_Rect *t, double tilt, int al)
{
    enum { NS = 12 };
    SDL_Vertex v[(NS + 1) * 2];
    int idx[NS * 6], k, w = 0, h = 0;
    SDL_Texture *tex = ui_text_tex(s, px, &w, &h);
    double cyt = t->y + t->h / 2.0, kin = 1.0 - 0.16 * fabs(tilt), left = cx - w / 2.0;
    SDL_Color c;

    if (!tex) {
        ui_label_c(cx, t->y + t->h + 18, s, px, 235, 235, 235, al);
        return;
    }
    c.r = 235;
    c.g = 235;
    c.b = 235;
    c.a = (Uint8)av_clip((int)(al * ui_fade), 0, 255);
    SDL_SetTextureColorMod(tex, 255, 255, 255);
    SDL_SetTextureAlphaMod(tex, 255);
    for (k = 0; k <= NS; k++) {
        double u = (double)k / NS, x = left + w * u;
        double uc = av_clipd((x - t->x) / (double)FFMAX(t->w, 1), 0.0, 1.0);
        double f = tilt < 0 ? 1.0 - (1.0 - kin) * uc : tilt > 0 ? kin + (1.0 - kin) * uc : 1.0;
        double mid = cyt + t->h * f / 2.0 + 18.0 * f;
        double hh = h * f / 2.0;

        v[k * 2].position.x = (float)x;
        v[k * 2].position.y = (float)(mid - hh);
        v[k * 2].color = c;
        v[k * 2].tex_coord.x = (float)u;
        v[k * 2].tex_coord.y = 0.0f;
        v[k * 2 + 1].position.x = (float)x;
        v[k * 2 + 1].position.y = (float)(mid + hh);
        v[k * 2 + 1].color = c;
        v[k * 2 + 1].tex_coord.x = (float)u;
        v[k * 2 + 1].tex_coord.y = 1.0f;
    }
    for (k = 0; k < NS; k++) {
        idx[k * 6] = k * 2;
        idx[k * 6 + 1] = k * 2 + 1;
        idx[k * 6 + 2] = k * 2 + 2;
        idx[k * 6 + 3] = k * 2 + 1;
        idx[k * 6 + 4] = k * 2 + 3;
        idx[k * 6 + 5] = k * 2 + 2;
    }
    SDL_RenderGeometry(renderer, tex, v, (NS + 1) * 2, idx, NS * 6);
}

/* ----- the shape of the whole track, read in the background -----
   Every file that plays is read once (at low priority) and measured: how loud each stretch of it is. */
#define UI_WAVE_N 200

typedef struct UiWave {
    char *path;
    int state;                  /* 0 = being read, 1 = ready, 2 = could not be read */
    float bin[UI_WAVE_N];
} UiWave;

static UiWave ui_wave[48];
static int ui_wave_n = 0, ui_wave_rr = 0;
static SDL_mutex *ui_wave_mu = NULL;
static SDL_cond *ui_wave_cv = NULL;
static int ui_wave_todo[48];
static unsigned ui_wave_head = 0, ui_wave_tail = 0;

static int ui_wave_cmp(const void *a, const void *b)
{
    float x = *(const float *)a, y = *(const float *)b;

    return x < y ? -1 : x > y;
}

/* Read all the audio of a file and measure it in UI_WAVE_N stretches. Returns 1 if bins are filled. */
static int ui_wave_scan(const char *path, float *bins)
{
    enum { RATE = 8000 };
    AVFormatContext *ic = NULL;
    AVCodecContext *cc = NULL;
    AVFrame *fr = NULL;
    AVPacket *pk = NULL;
    SwrContext *swr = NULL;
    const AVCodec *codec;
    AVStream *st;
    AVChannelLayout mono = AV_CHANNEL_LAYOUT_MONO, inl;
    double acc[UI_WAVE_N] = { 0 }, dur, mx;
    long cnt[UI_WAVE_N] = { 0 };
    float tmp[UI_WAVE_N], *buf = NULL, *nbuf;
    int64_t samples = 0;
    int si, i, n, b, cap = 0, want, ret = 0;

    if (strstr(path, "://") || avformat_open_input(&ic, path, NULL, NULL) < 0)
        return 0;
    avformat_find_stream_info(ic, NULL);
    si = av_find_best_stream(ic, AVMEDIA_TYPE_AUDIO, -1, -1, NULL, 0);
    dur = ic->duration > 0 ? ic->duration / (double)AV_TIME_BASE : 0.0;
    if (si < 0 || dur < 1.0 || dur > 7200.0)
        goto end;
    st = ic->streams[si];
    codec = avcodec_find_decoder(st->codecpar->codec_id);
    cc = codec ? avcodec_alloc_context3(codec) : NULL;
    if (!cc || avcodec_parameters_to_context(cc, st->codecpar) < 0 || avcodec_open2(cc, codec, NULL) < 0)
        goto end;
    fr = av_frame_alloc();
    pk = av_packet_alloc();
    if (!fr || !pk)
        goto end;
    while (av_read_frame(ic, pk) >= 0) {
        if (pk->stream_index == si && avcodec_send_packet(cc, pk) >= 0) {
            while (avcodec_receive_frame(cc, fr) >= 0) {
                if (!swr) {                     /* everything is turned into mono, 8000 samples a second */
                    int bad;

                    if (av_channel_layout_copy(&inl, &fr->ch_layout) < 0)
                        goto end;
                    if (inl.order == AV_CHANNEL_ORDER_UNSPEC)
                        av_channel_layout_default(&inl, inl.nb_channels > 0 ? inl.nb_channels : 2);
                    bad = swr_alloc_set_opts2(&swr, &mono, AV_SAMPLE_FMT_FLT, RATE, &inl, fr->format, fr->sample_rate, 0, NULL) < 0 ||
                          swr_init(swr) < 0;
                    av_channel_layout_uninit(&inl);
                    if (bad)
                        goto end;
                }
                want = (int)av_rescale_rnd(fr->nb_samples, RATE, FFMAX(fr->sample_rate, 1), AV_ROUND_UP) + 64;
                if (want > cap) {
                    nbuf = av_realloc_array(buf, want, sizeof(float));
                    if (!nbuf)
                        goto end;
                    buf = nbuf;
                    cap = want;
                }
                n = swr_convert(swr, (uint8_t **)&buf, cap, (const uint8_t **)fr->extended_data, fr->nb_samples);
                for (i = 0; i < n; i++) {
                    b = av_clip((int)(samples / (RATE * dur) * UI_WAVE_N), 0, UI_WAVE_N - 1);
                    acc[b] += (double)buf[i] * buf[i];
                    cnt[b]++;
                    samples++;
                }
                av_frame_unref(fr);
            }
        }
        av_packet_unref(pk);
    }
    for (i = 0; i < UI_WAVE_N; i++) {
        bins[i] = cnt[i] ? (float)sqrt(acc[i] / cnt[i]) : 0.0f;
        tmp[i] = bins[i];
    }
    qsort(tmp, UI_WAVE_N, sizeof(float), ui_wave_cmp);
    mx = tmp[(int)(UI_WAVE_N * 0.97)];          /* the loud parts reach the top; one odd peak doesn't flatten the rest */
    if (mx <= 0.0)
        goto end;
    for (i = 0; i < UI_WAVE_N; i++)
        bins[i] = (float)pow(av_clipd(bins[i] / mx, 0.0, 1.0), 0.8);
    ret = 1;
end:
    swr_free(&swr);
    av_freep(&buf);
    av_frame_free(&fr);
    av_packet_free(&pk);
    avcodec_free_context(&cc);
    avformat_close_input(&ic);
    return ret;
}

static int ui_wave_thread(void *arg)
{
    float bins[UI_WAVE_N];
    char *p;
    int k, ok;

    SDL_SetThreadPriority(SDL_THREAD_PRIORITY_LOW);
    for (;;) {
        SDL_LockMutex(ui_wave_mu);
        while (ui_wave_head >= ui_wave_tail)
            SDL_CondWait(ui_wave_cv, ui_wave_mu);
        k = ui_wave_todo[ui_wave_head++ % 48];
        p = av_strdup(ui_wave[k].path);
        SDL_UnlockMutex(ui_wave_mu);

        ok = p ? ui_wave_scan(p, bins) : 0;
        av_free(p);

        SDL_LockMutex(ui_wave_mu);
        if (ok)
            memcpy(ui_wave[k].bin, bins, sizeof(bins));
        ui_wave[k].state = ok ? 1 : 2;
        SDL_UnlockMutex(ui_wave_mu);
    }
    return 0;
}

/* The measured shape of a file: copies it into out and returns 1 if it is ready. Starts the scan the first time. */
static int ui_wave_get(const char *path, float *out)
{
    SDL_Thread *th;
    char *np;
    int i, k, slot, found = -1, ready = 0;

    if (!path)
        return 0;
    if (!ui_wave_mu) {
        ui_wave_mu = SDL_CreateMutex();
        ui_wave_cv = SDL_CreateCond();
        if (!ui_wave_mu || !ui_wave_cv)
            return 0;
        th = SDL_CreateThread(ui_wave_thread, "wave", NULL);
        if (th)
            SDL_DetachThread(th);
    }
    SDL_LockMutex(ui_wave_mu);
    for (i = 0; i < ui_wave_n; i++)
        if (ui_wave[i].path && !strcmp(ui_wave[i].path, path)) {
            found = i;
            break;
        }
    if (found < 0) {
        slot = -1;
        if (ui_wave_n < 48) {
            slot = ui_wave_n++;
        } else {
            for (i = 0; i < 48; i++) {          /* the table is full: reuse the next place that is not busy */
                k = (ui_wave_rr + i) % 48;
                if (ui_wave[k].state != 0) {
                    slot = k;
                    ui_wave_rr = (k + 1) % 48;
                    break;
                }
            }
        }
        np = slot >= 0 ? av_strdup(path) : NULL;
        if (np) {
            av_free(ui_wave[slot].path);
            ui_wave[slot].path = np;
            ui_wave[slot].state = 0;
            ui_wave_todo[ui_wave_tail++ % 48] = slot;
            SDL_CondSignal(ui_wave_cv);
            found = slot;
        } else if (slot >= 0 && slot == ui_wave_n - 1 && !ui_wave[slot].path) {
            ui_wave_n--;
        }
    }
    if (found >= 0 && ui_wave[found].state == 1) {
        memcpy(out, ui_wave[found].bin, sizeof(ui_wave[found].bin));
        ready = 1;
    }
    SDL_UnlockMutex(ui_wave_mu);
    return ready;
}

static void ui_flow_draw(VideoState *is)
{
    enum { NEQ = 72 };
''', "titles that tilt, and the track scan")

patch("""        nb = NEQ;
        pitch = (double)sk.w / nb;
        bw = FFMAX((int)(pitch * 0.55), 2);
        maxh = FFMIN(70, H / 8);
        base = sk.y - 12;
        playx = sk.x + (int)(frac * sk.w);
        for (j = 0; j < nb; j++) {
            amp = eq[j] * (0.55 + 0.45 * fabs(sin(j * 2.3 + t * 3.7)));
""", """        float wv[UI_WAVE_N];
        int have, b0, b1, q;

        have = ui_wave_get(q_items[q_pos], wv);         /* the shape of the whole track, once it has been read */
        nb = FFMAX(sk.w / 14, 24);
        pitch = (double)sk.w / nb;
        bw = FFMAX((int)(pitch * 0.55), 2);
        maxh = FFMIN(70, H / 8);
        base = sk.y - 12;
        playx = sk.x + (int)(frac * sk.w);
        for (j = 0; j < nb; j++) {
            if (have) {
                b0 = j * UI_WAVE_N / nb;
                b1 = FFMAX((j + 1) * UI_WAVE_N / nb, b0 + 1);
                amp = 0.0;
                for (q = b0; q < b1 && q < UI_WAVE_N; q++)
                    amp = FFMAX(amp, wv[q]);
                if (FFABS(sk.x + (int)(j * pitch) - playx) < 3 * pitch)       /* a little pulse at the playhead */
                    amp = FFMIN(1.0, amp * (1.0 + 0.35 * lvl));
            } else {                                    /* not read yet: the loudness of the last few seconds */
                amp = eq[j * NEQ / nb] * (0.55 + 0.45 * fabs(sin(j * 2.3 + t * 3.7)));
            }
""", "bars show the whole track")

open(path, "w").write(src)
print("Patched", path)
