#!/usr/bin/env python3
# patch_queue_v66.py - applies on top of v65 (so v63, v64, v65, then this).
#
#   1. the small tile view (tiles of all) has two rows at most, not three
#   2. it does not open for a queue that has only songs (the Tab key and the swipe up do nothing there);
#      set UI_TV_NO_AUDIO_ONLY to 0 in the file to bring it back for songs
#   3. in a queue with both videos and songs, two songs take the room of one video tile (each half as wide), sit on the
#      same bottom line as the videos so the titles line up, and show only the title of the song
#      (the part after the last " - ", without a track number); the titles of the videos next to them are kept
#      a little shorter so they never run into the song titles
#
# Usage:  python3 patch_queue_v66.py [path/to/ffplay.c]
# Default path: ~/build/ffmpeg-6.1.1/fftools/ffplay.c
# Every edit must match exactly once, otherwise nothing is written.

import os
import sys

path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/build/ffmpeg-6.1.1/fftools/ffplay.c")
src = open(path, encoding="utf-8").read()

edits = []   # (name, old, new)


def edit(name, old, new):
    edits.append((name, old, new))


# ---------------------------------------------------------------- 1. two rows, and the helpers for songs
edit("rows: two at most, and the song helpers", r'''static void ui_tv_dims(VideoState *is, int *R, int *L)
{
    int n = q_count;

    *R = n <= 3 ? 1 : (is->height >= 720 ? 3 : 2);
    *L = FFMAX((n + *R - 1) / *R, 1);
}
''', r'''static void ui_tv_dims(VideoState *is, int *R, int *L)
{
    int n = q_count;

    *R = n <= 3 ? 1 : 2;                        /* v66: two rows at most */
    *L = FFMAX((n + *R - 1) / *R, 1);
}

/* v66: which items of the queue are songs (by the ending of the file), so the tiles view can leave itself out for a queue of songs
   only, and put two songs in the room of one video. Kept up to date whenever the queue changes (its size or the order of its items). */
#define UI_TV_NO_AUDIO_ONLY 1                   /* 1 = no tile view for a queue that has no video in it */
static unsigned char *ui_tv_isaud = NULL;
static int ui_tv_isaud_n = -1, ui_tv_isaud_cap = 0, ui_tv_nvid = 0, ui_tv_naud = 0;
static uintptr_t ui_tv_isaud_sig = 0;
static int64_t ui_tv_isaud_at = 0;

static int ui_tv_path_is_audio(const char *path)
{
    const char *dot = path ? strrchr(path, '.') : NULL, *slash = path ? strrchr(path, '/') : NULL;
    int i;

    if (!dot || (slash && dot < slash))
        return 0;
    for (i = 0; ui_tv_ext[0][i]; i++)
        if (!av_strcasecmp(dot + 1, ui_tv_ext[0][i]))
            return 1;
    return 0;
}

static void ui_tv_kinds(void)
{
    uintptr_t sig = 0;
    int64_t now = av_gettime_relative();
    int i;

    for (i = 0; i < q_count; i++)
        sig = sig * 1000003u + (uintptr_t)q_items[i];
    if (ui_tv_isaud && q_count == ui_tv_isaud_n && sig == ui_tv_isaud_sig && now - ui_tv_isaud_at < 2000000)
        return;
    if (q_count + 1 > ui_tv_isaud_cap) {
        unsigned char *g = av_realloc(ui_tv_isaud, q_count + 64);

        if (!g)
            return;
        ui_tv_isaud = g;
        ui_tv_isaud_cap = q_count + 64;
    }
    ui_tv_nvid = ui_tv_naud = 0;
    for (i = 0; i < q_count; i++) {
        ui_tv_isaud[i] = ui_tv_path_is_audio(q_items[i]) ? 1 : 0;
        if (ui_tv_isaud[i])
            ui_tv_naud++;
        else
            ui_tv_nvid++;
    }
    ui_tv_isaud_n = q_count;
    ui_tv_isaud_sig = sig;
    ui_tv_isaud_at = now;
}

static int ui_tv_has_video(void)
{
    ui_tv_kinds();
    return ui_tv_nvid > 0;
}

static int ui_tv_mixed(void)                    /* videos and songs in the same queue */
{
    ui_tv_kinds();
    return ui_tv_nvid > 0 && ui_tv_naud > 0;
}

static int ui_tv_aud(int item)
{
    return item >= 0 && item < ui_tv_isaud_n && ui_tv_isaud && ui_tv_isaud[item];
}

/* v66: only the title of a song: what is after the last " - " (an artist, an album, a track number go), and a track number in
   front ("01. ", "02) ", "03-") goes too. A name with nothing of that is left as it is. */
static void ui_tv_song(char *s)
{
    char *p, *best = NULL;
    int i, j;

    for (p = s; *p; p++) {
        if (!strncmp(p, " - ", 3))
            best = p + 3;
        else if (!strncmp(p, " \xE2\x80\x93 ", 5) || !strncmp(p, " \xE2\x80\x94 ", 5))
            best = p + 5;
    }
    if (best && strlen(best) >= 2)
        memmove(s, best, strlen(best) + 1);
    for (i = 0; i < 3 && s[i] >= '0' && s[i] <= '9'; i++)
        ;
    if (i > 0 && ((s[i] == '.' || s[i] == ')') ? s[i + 1] == ' ' : ((s[i] == '-' || s[i] == '_') && i >= 2))) {
        j = i;
        while (s[j] == '.' || s[j] == ')' || s[j] == '-' || s[j] == '_' || s[j] == ' ')
            j++;
        if (strlen(s + j) >= 2)
            memmove(s, s + j, strlen(s + j) + 1);
    }
}
''')

# ---------------------------------------------------------------- 2. no tile view for a queue of songs only
edit("audio only: no tile view", r'''    if (!is || q_count <= 0 || q_pos < 0 || ui_tv_cap(is) || ui_too_small())
        return;
    if (is->video_st && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC)) {
        if (!ui_vflow) {                        /* the same start as key L */''', r'''    if (!is || q_count <= 0 || q_pos < 0 || ui_tv_cap(is) || ui_too_small())
        return;
    if (UI_TV_NO_AUDIO_ONLY && !ui_tv_has_video())
        return;                                 /* v66: a queue of songs only has no tile view */
    if (is->video_st && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC)) {
        if (!ui_vflow) {                        /* the same start as key L */''')

# ---------------------------------------------------------------- 3. the row: two songs in the room of one video
edit("row: arrays and the room of the songs", r'''    UiTvOrd ord[48];
    int no = 0, k0, k1, c, o, W = is->width, vm = ui_flow_vmode, K;
    double pitch = R->sw * 1.08;

    K = (int)(W / (2.0 * pitch)) + 3;
    k0 = FFMAX((int)floor(R->pos) - K, 0);
    k1 = FFMIN((int)ceil(R->pos) + 2 * K, R->count - 1);     /* v39: a row that starts at the far left shows more tiles to the right */
    for (c = k0; c <= k1 && no < 48; c++) {
        double dc = c - R->pos, dce = dc, d;

        if (R->sec < 0 && R->rowd > 0.0) {      /* v39: the shift to the far left (see below) moves the tile, so its size and brightness follow */
            double pmax = W / 2.0 / pitch - 0.6;

            if (pmax > 0.0 && R->pos < pmax)
                dce -= (pmax - R->pos) * FFMIN(R->rowd, 1.0);
        }''', r'''    UiTvOrd ord[128];
    double ucen[130], upos = R->pos;            /* v66: where the tiles are, in the room of a video tile (a song is half of one) */
    int no = 0, k0, k1, c, o, W = is->width, vm = ui_flow_vmode, K, mix = R->sec < 0 && ui_tv_mixed();
    double pitch = R->sw * 1.08;

    K = (int)(W / (2.0 * pitch)) + 3;
    if (mix)
        K *= 2;                                 /* v66: songs are half as wide: twice as many tiles are in sight */
    k0 = FFMAX((int)floor(R->pos) - K, 0);
    k1 = FFMIN((int)ceil(R->pos) + 2 * K, R->count - 1);     /* v39: a row that starts at the far left shows more tiles to the right */
    if (k1 - k0 > 126)
        k1 = k0 + 126;
    if (mix) {                                  /* v66: the middle of every tile, counted in video tiles; the focus is placed the same way */
        double u = 0.0, ca = 0.0, cb = 0.0;
        int a = FFMAX((int)floor(R->pos), 0), b = FFMIN((int)ceil(R->pos), R->count - 1), j;

        for (j = 0; j <= k1; j++) {
            double w = ui_tv_aud(R->first + j) ? 0.5 : 1.0;

            if (j >= k0)
                ucen[j - k0] = u + w / 2.0;
            if (j == a)
                ca = u + w / 2.0;
            if (j == b)
                cb = u + w / 2.0;
            u += w;
        }
        upos = ca + (cb - ca) * (R->pos - a);
    }
    for (c = k0; c <= k1 && no < 128; c++) {
        double dc = mix ? ucen[c - k0] - upos : c - R->pos, dce = dc, d;

        if (R->sec < 0 && R->rowd > 0.0) {      /* v39: the shift to the far left (see below) moves the tile, so its size and brightness follow */
            double pmax = W / 2.0 / pitch - 0.6;

            if (pmax > 0.0 && upos < pmax)
                dce -= (pmax - upos) * FFMIN(R->rowd, 1.0);
        }''')

edit("row: the tile of a song", r'''        int c = ord[o].c, item = R->sec < 0 ? R->first + c : c, play, nw, nh, al, md, tx, ty, ti, la;
        double d = ord[o].d, dc = c - R->pos, sc, x, en, ease, x1, lf, goal, asp, bw, bh;''', r'''        int c = ord[o].c, item = R->sec < 0 ? R->first + c : c, play, nw, nh, al, md, tx, ty, ti, la, aud;
        double d = ord[o].d, dc = mix ? ucen[c - k0] - upos : c - R->pos, sc, x, en, ease, x1, lf, goal, asp, bw, bh, href;''')

edit("row: half the width", r'''        bw = R->sw * sc;
        bh = R->sh * sc;
        asp = (play && vm''', r'''        bw = R->sw * sc;
        bh = R->sh * sc;
        aud = mix && ui_tv_aud(item);
        href = FFMIN(bh, bw / (16.0 / 9.0));    /* v66: the height of a video tile (16:9) at this size */
        if (aud)
            bw *= 0.5;                          /* a song is half as wide as a video: two of them in the room of one */
        asp = (play && vm''')

edit("row: far left shift of the tile", r'''            if (pmax > 0.0 && R->pos < pmax)
                x -= (pmax - R->pos) * pitch * FFMIN(R->rowd, 1.0);''', r'''            if (pmax > 0.0 && upos < pmax)
                x -= (pmax - upos) * pitch * FFMIN(R->rowd, 1.0);''')

edit("row: songs sit on the bottom line of the videos", r'''        md = FFMIN(255, md + (int)(40 * lf));
        if (tile.x + tile.w < -20 || tile.x > W + 20)
            continue;
        if (R->sec < 0 && ui_tv_slot_n < 96) {''', r'''        if (aud && href > nh)
            tile.y += (int)((href - nh) / 2.0); /* v66: on the same bottom line as the videos, so the titles line up */
        md = FFMIN(255, md + (int)(40 * lf));
        if (tile.x + tile.w < -20 || tile.x > W + 20)
            continue;
        if (R->sec < 0 && ui_tv_slot_n < 96) {''')

edit("row: the title of a song", r'''        ui_tv_name(path, name, sizeof(name));
        px = d < 0.6 ? (R->sm ? 16 : 19) : (R->sm ? 12 : 14);''', r'''        ui_tv_name(path, name, sizeof(name));
        if (aud)
            ui_tv_song(name);                   /* v66: only the title of the song */
        px = aud ? (d < 0.6 ? (R->sm ? 13 : 16) : (R->sm ? 11 : 12)) : (d < 0.6 ? (R->sm ? 16 : 19) : (R->sm ? 12 : 14));''')

edit("row: the dot before the title", r'''            pdot.x = tx - FFMIN(tw, (int)(pitch * 1.4)) / 2 - 14;''',
     r'''            pdot.x = tx - FFMIN(tw, aud ? (int)(pitch * 0.45) : (int)(pitch * 1.4)) / 2 - 14;''')

edit("row: the width of the title", r'''        ui_tv_label(name, hl, px, tx, ty, (int)(pitch * (d < 0.6 ? 1.9 : 1.05)), (int)(la * (d < 0.6 ? 1.0 : 0.75 + 0.25 * lf)));''',
     r'''        ui_tv_label(name, hl, px, tx, ty, aud ? (int)(pitch * 0.47) : mix ? (int)(pitch * 0.98) : (int)(pitch * (d < 0.6 ? 1.9 : 1.05)),
                    (int)(la * (d < 0.6 ? 1.0 : 0.75 + 0.25 * lf)));''')

edit("rows: the box of a tile is the same for songs", r'''            row.sw = (int)(sh * (ui_tv_audio ? 1.22 : 1.75));        /* v39: music tiles sit closer */''',
     r'''            row.sw = (int)(sh * 1.75);                              /* v66: a song takes half of this width itself (two songs, one video's room) */''')

# ---------------------------------------------------------------- apply, all or nothing
out = src
for name, old, new in edits:
    n = out.count(old)
    if n != 1:
        print("FAILED: '%s' matched %d times (needs exactly 1). Nothing was written." % (name, n))
        sys.exit(1)
    out = out.replace(old, new, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(out)
print("v66: %d edits applied to %s" % (len(edits), path))
