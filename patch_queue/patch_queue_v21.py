#!/usr/bin/env python3
# Update 21 for ffplay-custom.
#   * The sleep timer ("End of track" and "Sleep after this item") now PAUSES just before the end of the item,
#     so you stay in the playing view with the whole queue as it was. It no longer drops to the idle screen.
#   * Key L: the queue view for videos. Press L while a video plays to see the videos of the queue as tiles, each in
#     its own shape (not square, no letterboxing), with a small dot in your bar color on the one that is playing.
#     No spinning disc for videos. Press L again to go back to the full-screen video.
#   * The waveform bars sit in the middle of the space between the queue view and the progress bar, and have no
#     baseline: they grow up and down from a middle line, like a sound recorder.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v20.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_vflow" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_flow_on" not in src or "modified version of fftools/ffplay.c" not in src:
    print("Apply patch_queue_v20.py (and the ones before it) first. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


# ============================================================ sleep: pause just before the end

patch("""static void ui_sleep_tick(VideoState *is)
{
    int64_t left;

    if (!q_sleep_end)
        return;
""", """static void ui_sleep_tick(VideoState *is)
{
    int64_t left;
    double pos, dur;

    /* "End of track" / "Sleep after this item": pause a moment before the item ends, and stay where we are.
       The queue view and the queue stay as they are; play carries on into the last moments and then the next item. */
    if (is && q_sleep_item && q_pos >= 0 && q_pos < q_count && q_sleep_item == q_items[q_pos] && !is->paused &&
        is->ic && is->ic->duration > 0) {
        pos = get_master_clock(is);
        if (!isnan(pos)) {
            if (is->ic->start_time != AV_NOPTS_VALUE)
                pos -= is->ic->start_time / (double)AV_TIME_BASE;
            dur = is->ic->duration / (double)AV_TIME_BASE;
            if (dur - pos < 0.35 && dur - pos > -5.0) {
                q_sleep_item = NULL;
                ui_sleep_sel = 0;
                ui_xf_abort();
                is->xf_gain = 1.0f;
                toggle_pause(is);
                is->force_refresh = 1;
            }
        }
    }
    if (!q_sleep_end)
        return;
""", "sleep: pause before the end instead of going idle")

# ============================================================ the queue view over videos (key L)

patch("static int ui_flow_wants_redraw(VideoState *is);\n",
      "static int ui_flow_wants_redraw(VideoState *is);\nstatic int ui_flow_video(VideoState *is);\n",
      "forward declaration")

patch("    if (!ui_has_cover(is))                  /* a cover is drawn by the queue view instead (ui_flow_draw) */\n",
      "    if (!ui_has_cover(is) && !ui_flow_video(is))    /* a cover is drawn by the queue view instead (ui_flow_draw) */\n",
      "no full-screen video behind the tiles")

patch("    if (!ui_has_cover(is) || W <= 0 || H <= 0)\n        return;\n    if (strncmp(ui_bd_key",
      "    if (!(ui_has_cover(is) || ui_flow_video(is)) || W <= 0 || H <= 0)\n        return;\n    if (strncmp(ui_bd_key",
      "the cover backdrop also glows behind the video tiles")

# the pictures of videos in their own shape
patch("""    int tr, tg, tb;             /* the average color of the picture, for the disc */
    SDL_Texture *tex;
} UiCov;
""", """    int tr, tg, tb;             /* the average color of the picture, for the disc */
    SDL_Texture *tex;
    uint8_t *npx;               /* a video frame in its own shape (rounded corners), for the video tiles */
    int nw, nh;
    SDL_Texture *ntex;
} UiCov;
""", "pictures in their own shape: fields")

patch("static uint8_t *ui_cov_decode(const char *path, int *ow, int *oh, int *cw, int *ch)\n{\n",
      "static uint8_t *ui_cov_decode(const char *path, int *ow, int *oh, int *cw, int *ch, uint8_t **nat, int *nw, int *nh)\n{\n",
      "decoder: signature")

patch("    int tls[4] = { 0 }, x, y, ox, oy;\n\n    if (strstr(path, \"://\"))\n        return NULL;\n",
      "    int tls[4] = { 0 }, x, y, ox, oy;\n    uint8_t *nt = NULL;\n\n    *nat = NULL;\n    *nw = *nh = 0;\n    if (strstr(path, \"://\"))\n        return NULL;\n",
      "decoder: variables")

patch("""    *ow = w;
    *oh = h;
    *cw = w;
    *ch = h;
    if (w != h) {       /* not square""", """    *ow = w;
    *oh = h;
    *cw = w;
    *ch = h;
    if (w != h && w >= 32 && h >= 32 && !(st->disposition & AV_DISPOSITION_ATTACHED_PIC)) {
        /* a video frame: keep a copy in its own shape, with rounded corners, for the video tiles */
        int rr = FFMIN(w, h) / 11, k;

        nt = av_malloc((size_t)w * h * 4);
        if (nt) {
            memcpy(nt, out, (size_t)w * h * 4);
            for (y = 0; y < rr; y++)
                for (x = 0; x < rr; x++) {
                    double dxx = rr - x - 0.5, dyy = rr - y - 0.5;
                    double cov = av_clipd(rr - sqrt(dxx * dxx + dyy * dyy) + 0.5, 0.0, 1.0);
                    int at[4] = { y * w + x, y * w + w - 1 - x, (h - 1 - y) * w + x, (h - 1 - y) * w + w - 1 - x };

                    for (k = 0; k < 4; k++)
                        nt[at[k] * 4 + 3] = (uint8_t)(nt[at[k] * 4 + 3] * cov);
                }
        }
    }
    if (w != h) {       /* not square""", "decoder: keep the frame in its own shape")

patch("""end:
    sws_freeContext(sws);
    sws_freeContext(sws2);
    av_free(tiny);
""", """end:
    if (out && nt) {
        *nat = nt;
        *nw = w;
        *nh = h;
    } else {
        av_free(nt);
    }
    sws_freeContext(sws);
    sws_freeContext(sws2);
    av_free(tiny);
""", "decoder: hand the frame over")

patch("""    uint8_t *px;
    int k, w, h, cw, ch;

    for (;;) {
        SDL_LockMutex(ui_cov_mu);
        while (ui_cov_head >= ui_cov_tail)""", """    uint8_t *px, *npx = NULL;
    int k, w, h, cw, ch, nw = 0, nh = 0;

    for (;;) {
        SDL_LockMutex(ui_cov_mu);
        while (ui_cov_head >= ui_cov_tail)""", "cover thread: variables")

patch("        px = p ? ui_cov_decode(p, &w, &h, &cw, &ch) : NULL;\n",
      "        npx = NULL;\n        px = p ? ui_cov_decode(p, &w, &h, &cw, &ch, &npx, &nw, &nh) : NULL;\n", "cover thread: decode call")

patch("        ui_cov[k].ch = ch;\n        ui_cov[k].state = px ? 1 : 3;\n",
      "        ui_cov[k].ch = ch;\n        ui_cov[k].npx = npx;\n        ui_cov[k].nw = nw;\n        ui_cov[k].nh = nh;\n        ui_cov[k].state = px ? 1 : 3;\n",
      "cover thread: store the frame")

patch("""            av_freep(&c->px);
            c->state = c->tex ? 2 : 3;
""", """            av_freep(&c->px);
            if (c->npx) {                       /* the video frame in its own shape */
                c->ntex = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STATIC, c->nw, c->nh);
                if (c->ntex) {
                    SDL_UpdateTexture(c->ntex, NULL, c->npx, c->nw * 4);
                    SDL_SetTextureBlendMode(c->ntex, SDL_BLENDMODE_BLEND);
                }
                av_freep(&c->npx);
            }
            c->state = c->tex ? 2 : 3;
""", "cover texture in its own shape")

patch("static int ui_flow_on(VideoState *is)\n{\n    return is && is->audio_st && q_count > 0 && q_pos >= 0 && q_pos < q_count &&\n           (!is->video_st || (is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC));\n}\n",
      r'''static int ui_vflow = 0;                /* 1 = the queue view is shown over videos too (key L) */
static int ui_flow_vmode = 0;           /* 1 while the queue view is drawn over a video: own-shape tiles, no disc */

/* The picture of a video file in its own shape (rounded corners), or NULL if it is not a video or is still being read */
static SDL_Texture *ui_cov_native(const char *path, int *w, int *h)
{
    SDL_Texture *t = NULL;
    int i;

    if (!path || !ui_cov_mu)
        return NULL;
    SDL_LockMutex(ui_cov_mu);
    for (i = 0; i < ui_cov_n; i++)
        if (!strcmp(ui_cov[i].path, path)) {
            if (ui_cov[i].state == 2 && ui_cov[i].ntex) {
                t = ui_cov[i].ntex;
                *w = ui_cov[i].nw;
                *h = ui_cov[i].nh;
            }
            break;
        }
    SDL_UnlockMutex(ui_cov_mu);
    return t;
}

/* Width divided by height of a video's picture, or 0 if it is not known (yet) */
static double ui_cov_aspect(const char *path)
{
    int w = 0, h = 0;

    return ui_cov_native(path, &w, &h) && h > 0 ? (double)w / h : 0.0;
}

/* Is the queue view showing over a video (key L)? */
static int ui_flow_video(VideoState *is)
{
    return is && ui_vflow && is->video_st && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC) &&
           q_count > 0 && q_pos >= 0 && q_pos < q_count;
}

static int ui_flow_on(VideoState *is)
{
    return (is && is->audio_st && q_count > 0 && q_pos >= 0 && q_pos < q_count &&
            (!is->video_st || (is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC))) || ui_flow_video(is);
}
''', "the queue view over videos: switch and helpers")

patch("    return B * (0.86 * dc + 0.42 * (d - dc)) + (d > 0 ? B * 0.40 * FFMIN(d, 1.0) : 0.0);    /* the right side leaves room for the disc */\n",
      "    return B * (0.86 * dc + 0.42 * (d - dc)) + (d > 0 && !ui_flow_vmode ? B * 0.40 * FFMIN(d, 1.0) : 0.0);    /* the right side leaves room for the disc (not for videos) */\n",
      "no room for a disc beside videos")

patch("    tex = ui_cov_get(q_items[idx], &cw, &ch);\n    if (tex) {                                  /* a soft shadow",
      "    tex = ui_flow_vmode ? ui_cov_native(q_items[idx], &cw, &ch) : NULL;     /* a video keeps its own shape */\n"
      "    if (!tex)\n        tex = ui_cov_get(q_items[idx], &cw, &ch);\n"
      "    if (tex) {                                  /* a soft shadow",
      "tiles use the video's own shape")

# ---- drawing the view
patch("    int al, md, have, b0, b1, q;\n    float wv[UI_WAVE_N];\n",
      "    int al, md, have, b0, b1, q, mid, chh;\n    float wv[UI_WAVE_N];\n", "view: variables")

patch("    dt = ui_flow_t ? av_clipd((now - ui_flow_t) / 1000000.0, 0.0, 0.1) : 0.0;\n",
      "    ui_flow_vmode = ui_flow_video(is);          /* over a video: tiles in their own shape, no disc */\n"
      "    dt = ui_flow_t ? av_clipd((now - ui_flow_t) / 1000000.0, 0.0, 0.1) : 0.0;\n", "view: video mode")

patch("    B = FFMIN(W * 0.30, H * 0.44);\n    cx = W / 2 - (int)(B * 0.12);\n",
      "    B = ui_flow_vmode ? FFMIN(W * 0.36, H * 0.50) : FFMIN(W * 0.30, H * 0.44);     /* wide tiles need more room */\n"
      "    cx = W / 2 - (ui_flow_vmode ? 0 : (int)(B * 0.12));\n    chh = (int)B;                               /* the height of the middle tile */\n",
      "view: size and middle")

patch("            ui_flow_rects[e].y = cy - (int)(s / 2);\n        }\n",
      """            ui_flow_rects[e].y = cy - (int)(s / 2);
            if (ui_flow_vmode) {                /* a video keeps its own shape: fitted into the square slot, centred in it */
                double asp = ui_cov_aspect(q_items[i]);

                if (asp > 0.0) {
                    int sw = ui_flow_rects[e].w, sh = ui_flow_rects[e].h;
                    int nw = asp >= 1.0 ? sw : (int)(sh * asp), nh = asp >= 1.0 ? (int)(sw / asp) : sh;

                    ui_flow_rects[e].x += (sw - nw) / 2;
                    ui_flow_rects[e].y += (sh - nh) / 2;
                    ui_flow_rects[e].w = nw;
                    ui_flow_rects[e].h = nh;
                }
            }
            if (i == ci)
                chh = ui_flow_rects[e].h;       /* the labels go under the middle tile */
        }
""", "view: tiles in the shape of their video")

patch("                if (i == q_pos) {               /* the disc only shows where it sticks out to the right of the cover */\n",
      "                if (i == q_pos && !ui_flow_vmode) {     /* the disc only shows where it sticks out to the right of the cover */\n",
      "view: no disc for videos")

patch("                ui_flow_tile(i, &tile, (ui_flow_dragging && i == ui_flow_press) ? al / 3 : al, md, tl[e]);\n",
      """                ui_flow_tile(i, &tile, (ui_flow_dragging && i == ui_flow_press) ? al / 3 : al, md, tl[e]);
                if (ui_flow_vmode && i == q_pos) {      /* a small dot in the bar color marks the video that is playing */
                    int dd = FFMAX(tile.h / 34, 8);
                    SDL_Rect dot;

                    dot.w = dd;
                    dot.h = dd;
                    dot.x = tile.x + dd + 6;
                    dot.y = tile.y + tile.h - 2 * dd - 6;
                    SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 235 * al / 255);
                    ui_pill(&dot);
                }
""", "view: the dot on the playing video")

patch("    ui_label_c(W / 2, cy + (int)(B / 2) + 40, name, 22, 255, 255, 255, 255);\n",
      "    ui_label_c(W / 2, cy + chh / 2 + 40, name, 22, 255, 255, 255, 255);\n", "view: the name under the middle tile")
patch("    ui_label_c(W / 2, cy + (int)(B / 2) + 70, num, 15, 175, 175, 175, 255);\n",
      "    ui_label_c(W / 2, cy + chh / 2 + 70, num, 15, 175, 175, 175, 255);\n", "view: the counter under the middle tile")

# ---- the waveform: in the middle of the free space, with no baseline
patch("""        maxh = FFMIN(90, H / 6);                        /* the tallest a bar can be */
        base = sk.y - 12;
""", """        {                                               /* the free space: under the name and counter, over the seek bar */
            int top = cy + chh / 2 + 84, space = sk.y - 12 - top;

            mid = top + space / 2;                      /* the bars grow up and down from this line */
            maxh = av_clip(space - 12, 14, 220);        /* the tallest a bar can be */
        }
""", "bars: the middle of the free space")

patch("""            bar.x = x0 + (int)(j * pitch);
            bar.h = 3 + (int)(amp * maxh);
            bar.w = bw;
            bar.y = base - bar.h;
""", """            bar.x = x0 + (int)(j * pitch);
            bar.h = 3 + (int)(amp * (maxh - 3));
            bar.w = bw;
            bar.y = mid - bar.h / 2;                    /* no baseline: centred on the middle line, like a sound recorder */
""", "bars: no baseline")

patch("    int W = is->width, H = is->height, i, j, pass, cx, cy, ci, nb, bw, maxh, base;\n",
      "    int W = is->width, H = is->height, i, j, pass, cx, cy, ci, nb, bw, maxh;\n", "bars: unused variable")

# ---- the key
patch("            case SDLK_w:\n                if (cur_stream->show_mode == SHOW_MODE_VIDEO && cur_stream->vfilter_idx < nb_vfilters - 1) {\n",
      "            case SDLK_l:                /* the queue view over a video: the videos of the queue as tiles */\n"
      "                ui_vflow = !ui_vflow;\n                cur_stream->force_refresh = 1;\n                break;\n"
      "            case SDLK_w:\n                if (cur_stream->show_mode == SHOW_MODE_VIDEO && cur_stream->vfilter_idx < nb_vfilters - 1) {\n",
      "key L")

open(path, "w").write(src)
print("Patched", path)
