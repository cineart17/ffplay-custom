#!/usr/bin/env python3
# Queue and menu update 3 for ffplay-custom.
#   * The queue opens scrolled to the playing item, with two items above it when there are any.
#   * "Open File..." and "Open Folder..." are one "Open" row; hovering it shows the two choices.
#   * Queue panel: a bottom section with a crossfade setting (0 to 10 s), a sleep timer
#     (hover it for End of track, 5, 10, 30 min, 1 hr) and a quiet counter: 1/179  [1:23:36 / 2:13:14].
#   * Right-click a queue item: "Remove from queue" or "Sleep after this item".
#   * Menu boxes: softer corners, a shadow, a hairline edge and rounded hover highlights.
#     All menu rows are centred except Queue and Media Info.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v2.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_ctx_open" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_info_open" not in src or "queue_set_shuffle" not in src:
    print("Apply patch_queue_v2.py first. Nothing written.")
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


# ============================================================ settings, stream gain, text cache

patch("static int     cfg_wheel = 0;               /* mouse wheel: 0 = off, 1 = volume, 2 = seek */\n",
      "static int     cfg_wheel = 0;               /* mouse wheel: 0 = off, 1 = volume, 2 = seek */\n"
      "static int     cfg_crossfade = 0;           /* seconds the end of one item and the start of the next overlap (0 to 10) */\n"
      "static float   xf_open_gain = 1.0f;         /* loudness a stream starts with: 0 while it opens under the end of the last item */\n"
      "static float   ui_sleep_gain = 1.0f;        /* the sleep timer fades everything out with this */\n"
      "static VideoState *xf_stream = NULL; /* the next item, already playing under the end of this one */\n"
      "static char   *xf_name = NULL;              /* its name in the queue */\n"
      "static char   *xf_failed = NULL;            /* an item that would not open early: do not try again */\n",
      "settings: crossfade and gain variables")

patch("        else if (sscanf(line, \" font = %400[^\\n]\", cfg_font) == 1) {\n",
      "        else if (sscanf(line, \" crossfade = %d\", &n) == 1)\n"
      "            cfg_crossfade = av_clip(n, 0, 10);\n"
      "        else if (sscanf(line, \" font = %400[^\\n]\", cfg_font) == 1) {\n",
      "settings: read crossfade")

patch("    ui_key_save(f);\n    fprintf(f, \"# Font file for the text",
      "    fprintf(f, \"# Seconds the end of one item and the start of the next overlap (0 = off, 10 at most)\\ncrossfade = %d\\n\\n\",\n"
      "            cfg_crossfade);\n"
      "    ui_key_save(f);\n    fprintf(f, \"# Font file for the text",
      "settings: write crossfade")

patch("    int audio_volume;\n",
      "    int audio_volume;\n    float xf_gain;              /* 0 to 1: how loud this stream is during a crossfade */\n",
      "stream gain field")


patch("    float xf_gain;              /* 0 to 1: how loud this stream is during a crossfade */\n",
      "    float xf_gain;              /* 0 to 1: how loud this stream is during a crossfade */\n    SDL_AudioDeviceID audio_dev_id;  /* this stream's own audio device (two streams play during a crossfade) */\n",
      "stream audio device field")
patch("        decoder_abort(&is->auddec, &is->sampq);\n        SDL_CloseAudioDevice(audio_dev);\n",
      "        decoder_abort(&is->auddec, &is->sampq);\n        SDL_CloseAudioDevice(is->audio_dev_id);\n",
      "close the stream's own audio device")
patch("        SDL_PauseAudioDevice(audio_dev, 0);\n",
      "        is->audio_dev_id = audio_dev;\n        SDL_PauseAudioDevice(is->audio_dev_id, 0);\n",
      "remember the stream's audio device")

patch("    is->muted = 0;\n    is->av_sync_type = av_sync_type;\n",
      "    is->muted = 0;\n    is->xf_gain = xf_open_gain;\n    is->av_sync_type = av_sync_type;\n",
      "stream starts with its gain")

patch("    int audio_size, len1;\n\n    audio_callback_time = av_gettime_relative();\n",
      "    int audio_size, len1, vol;\n\n    audio_callback_time = av_gettime_relative();\n",
      "audio callback: volume variable")

patch("        if (!is->muted && is->audio_buf && is->audio_volume == SDL_MIX_MAXVOLUME)\n"
      "            memcpy(stream, (uint8_t *)is->audio_buf + is->audio_buf_index, len1);\n"
      "        else {\n"
      "            memset(stream, 0, len1);\n"
      "            if (!is->muted && is->audio_buf)\n"
      "                SDL_MixAudioFormat(stream, (uint8_t *)is->audio_buf + is->audio_buf_index, AUDIO_S16SYS, len1, is->audio_volume);\n"
      "        }\n",
      "        vol = (int)(is->audio_volume * is->xf_gain * ui_sleep_gain + 0.5f);\n"
      "        if (!is->muted && is->audio_buf && vol == SDL_MIX_MAXVOLUME)\n"
      "            memcpy(stream, (uint8_t *)is->audio_buf + is->audio_buf_index, len1);\n"
      "        else {\n"
      "            memset(stream, 0, len1);\n"
      "            if (!is->muted && is->audio_buf)\n"
      "                SDL_MixAudioFormat(stream, (uint8_t *)is->audio_buf + is->audio_buf_index, AUDIO_S16SYS, len1, vol);\n"
      "        }\n",
      "audio callback: crossfade and sleep gain")

patch("#define UI_TEXT_CACHE 64\n", "#define UI_TEXT_CACHE 128\n", "bigger text cache")

# ============================================================ queue state and durations

patch("static int q_cap = 0;                   /* room in all three queue arrays */\n",
      "static int q_cap = 0;                   /* room in all three queue arrays */\n"
      "static char *q_sleep_item = NULL;       /* stop after this item has played (a pointer into q_items) */\n"
      "static int q_hold = 0;                  /* 1 = playback stopped for the sleep timer: wait on the idle screen */\n"
      "static int64_t q_sleep_end = 0;         /* when the sleep timer runs out (0 = no timer) */\n"
      "static int ui_sleep_sel = 0;            /* the timer choice: 0 off, 1 end of track, 2 to 5 = 5, 10, 30, 60 minutes */\n"
      "static int ui_user_skip = 0;            /* 1 = the item was ended by the user (n, p, a click), not by reaching its end */\n",
      "queue state: sleep and crossfade")

DUR_BLOCK = r'''
/* ----- how long each item is: found in the background, for the counter in the queue panel ----- */
typedef struct QDur {
    char *path;
    double secs;
} QDur;
static QDur *q_dur = NULL;                  /* what is known so far */
static int q_dur_n = 0, q_dur_cap = 0;
static char **q_todo = NULL;                /* paths still to look at */
static int q_todo_n = 0, q_todo_head = 0, q_todo_cap = 0;
static SDL_mutex *q_dur_mu = NULL;
static SDL_cond *q_dur_cv = NULL;

static double queue_probe(const char *path)
{
    AVFormatContext *ic = NULL;
    AVDictionary *opts = NULL;
    double secs = 0;

    if (strstr(path, "://"))
        return 0;                           /* a stream: no length */
    av_dict_set(&opts, "probesize", "1000000", 0);
    av_dict_set(&opts, "analyzeduration", "1000000", 0);
    if (avformat_open_input(&ic, path, NULL, &opts) == 0) {
        avformat_find_stream_info(ic, NULL);
        if (ic->duration > 0)
            secs = ic->duration / (double)AV_TIME_BASE;
        avformat_close_input(&ic);
    }
    av_dict_free(&opts);
    return secs;
}

static int queue_probe_thread(void *arg)
{
    QDur *grown;
    char *path;
    double secs;

    for (;;) {
        SDL_LockMutex(q_dur_mu);
        while (q_todo_head >= q_todo_n)
            SDL_CondWait(q_dur_cv, q_dur_mu);
        path = q_todo[q_todo_head++];
        if (q_todo_head >= q_todo_n)
            q_todo_head = q_todo_n = 0;
        SDL_UnlockMutex(q_dur_mu);

        secs = queue_probe(path);

        SDL_LockMutex(q_dur_mu);
        if (q_dur_n + 1 > q_dur_cap) {
            grown = av_realloc_array(q_dur, FFMAX(q_dur_cap * 2, 64), sizeof(*q_dur));
            if (grown) {
                q_dur = grown;
                q_dur_cap = FFMAX(q_dur_cap * 2, 64);
            }
        }
        if (q_dur_n + 1 <= q_dur_cap) {
            q_dur[q_dur_n].path = path;
            q_dur[q_dur_n].secs = secs;
            q_dur_n++;
        } else {
            av_free(path);
        }
        SDL_UnlockMutex(q_dur_mu);
    }
    return 0;
}

/* The length of an item is wanted: look at the file in the background (once per file name) */
static void queue_probe_add(const char *path)
{
    SDL_Thread *t;
    char **grown;
    char *copy;
    int i;

    if (!q_dur_mu) {
        q_dur_mu = SDL_CreateMutex();
        q_dur_cv = SDL_CreateCond();
        if (!q_dur_mu || !q_dur_cv)
            return;
        t = SDL_CreateThread(queue_probe_thread, "item lengths", NULL);
        if (!t)
            return;
        SDL_DetachThread(t);
    }
    copy = av_strdup(path);
    if (!copy)
        return;
    SDL_LockMutex(q_dur_mu);
    for (i = 0; i < q_dur_n; i++)
        if (!strcmp(q_dur[i].path, path))
            goto skip;
    for (i = q_todo_head; i < q_todo_n; i++)
        if (!strcmp(q_todo[i], path))
            goto skip;
    if (q_todo_n + 1 > q_todo_cap) {
        grown = av_realloc_array(q_todo, FFMAX(q_todo_cap * 2, 64), sizeof(*q_todo));
        if (!grown)
            goto skip;
        q_todo = grown;
        q_todo_cap = FFMAX(q_todo_cap * 2, 64);
    }
    q_todo[q_todo_n++] = copy;
    SDL_CondSignal(q_dur_cv);
    SDL_UnlockMutex(q_dur_mu);
    return;
skip:
    SDL_UnlockMutex(q_dur_mu);
    av_free(copy);
}

/* Add up the queue. before = the items that played before the current one, total = all of them,
   unknown = items whose length has not been found yet. streaming = 0 on the idle screen: then
   the item that played last counts as played too. */
static void queue_stats(int streaming, double *before, double *total, int *unknown)
{
    double b = 0, t = 0, s;
    int i, j, miss = 0;

    if (q_dur_mu)
        SDL_LockMutex(q_dur_mu);
    for (i = 0; i < q_count; i++) {
        int found = 0;

        s = 0;
        for (j = 0; q_dur_mu && j < q_dur_n; j++)
            if (!strcmp(q_dur[j].path, q_items[i])) {
                s = q_dur[j].secs;
                found = 1;
                break;
            }
        if (!found)
            miss++;
        t += s;
        if (q_played[i] && (i != q_pos || !streaming))
            b += s;
    }
    if (q_dur_mu)
        SDL_UnlockMutex(q_dur_mu);
    *before = b;
    *total = t;
    *unknown = miss;
}
'''

patch("static void queue_add(const char *path)\n{\n", DUR_BLOCK + "\nstatic void queue_add(const char *path)\n{\n",
      "item lengths")

patch("    q_seq[q_count] = q_seq_next++;\n    q_count++;\n",
      "    q_seq[q_count] = q_seq_next++;\n    q_count++;\n    queue_probe_add(name);\n",
      "queue_add asks for the length")

patch("    q_count = 0;\n    q_pos = -1;\n    q_step = 1;\n    q_forced = -1;\n    q_seq_next = 0;\n",
      "    q_count = 0;\n    q_pos = -1;\n    q_step = 1;\n    q_forced = -1;\n    q_seq_next = 0;\n"
      "    q_sleep_item = NULL;\n    q_hold = 0;\n    xf_name = NULL;\n",
      "queue_clear forgets sleep and crossfade")

patch("    gone = q_items[idx];\n    for (i = idx; i < q_count - 1; i++) {\n",
      "    gone = q_items[idx];\n    if (gone == q_sleep_item)\n        q_sleep_item = NULL;\n    if (gone == xf_name)\n        xf_name = NULL;\n"
      "    for (i = idx; i < q_count - 1; i++) {\n",
      "queue_remove forgets sleep and crossfade")



# ============================================================ the look: corners, shadow, edge

patch("/* ----- rounded rectangles ----- */\n",
      r'''/* Draw text with its middle at cx */
static void ui_label_c(int cx, int cy, const char *s, int px, int r, int g, int b, int a)
{
    ui_label(cx - ui_text_width(s, px) / 2, cy, s, px, r, g, b, a);
}

/* ----- rounded rectangles ----- */
''', "centred text")

patch_between("/* How far in from the left and right edge a row of a rounded rectangle starts */",
              "/* ----- frosted glass ----- */",
              r'''/* How far in from the left and right edge a row of a rounded rectangle starts.
   The corner is a squircle, not a circle: it flows into the straight edge more gently. */
static int ui_rr_inset(int row, int h, int r)
{
    double dy;

    if (row < r)
        dy = r - row - 0.5;
    else if (row >= h - r)
        dy = row - (h - r) + 0.5;
    else
        return 0;
    return (int)(r - r * cbrt(1.0 - pow(dy / r, 3.0)) + 0.5);
}

/* Fill a rounded rectangle with the current draw color */
static void ui_rr_fill(const SDL_Rect *t, int r)
{
    SDL_Rect line;
    int row, inset;

    r = FFMIN(r, FFMIN(t->w, t->h) / 2);
    for (row = 0; row < t->h; row++) {
        inset = ui_rr_inset(row, t->h, r);
        line.x = t->x + inset;
        line.y = t->y + row;
        line.w = t->w - 2 * inset;
        line.h = 1;
        if (line.w > 0)
            SDL_RenderFillRect(renderer, &line);
    }
}

/* A soft shadow under a panel: a few rounded shapes, each a little bigger and fainter */
static void ui_shadow(const SDL_Rect *t, int r)
{
    SDL_Rect e;
    int i;

    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    for (i = 6; i >= 1; i--) {
        e.x = t->x - i * 3;
        e.y = t->y - i * 3 + 6;
        e.w = t->w + i * 6;
        e.h = t->h + i * 6;
        SDL_SetRenderDrawColor(renderer, 0, 0, 0, 7);
        ui_rr_fill(&e, r + i * 3);
    }
}

''', "squircle corners, fill and shadow")

patch_between("/* Frosted glass: the blurred picture behind a rounded rectangle",
              "/* The idle background: a few soft glows",
              r'''/* Frosted glass: a soft shadow, the blurred picture behind a rounded rectangle, a dark tint,
   a faint sheen at the top, a thin inner highlight and a hairline edge. */
static void ui_glass(const SDL_Rect *t, int r)
{
    int row, run = -1, inset, piece, top3;
    SDL_Rect line;

    r = FFMIN(r, FFMIN(t->w, t->h) / 2);
    ui_shadow(t, r);

    /* 1. The blurred picture, cut to the rounded shape. Full-width rows are
          copied together; the rows in the corners one by one. */
    for (row = 0; row <= t->h; row++) {
        inset = (row < t->h) ? ui_rr_inset(row, t->h, r) : -1;
        if (inset == 0) {
            if (run < 0)
                run = row;
            continue;
        }
        if (run >= 0) {
            ui_blur_strip(t->x, t->y + run, t->w, row - run);
            run = -1;
        }
        if (inset > 0)
            ui_blur_strip(t->x + inset, t->y + row, t->w - 2 * inset, 1);
    }

    /* 2. Tint, sheen, inner highlight and edge */
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    top3 = FFMAX(t->h / 3, 1);
    for (row = 0; row < t->h; row++) {
        inset = ui_rr_inset(row, t->h, r);
        line.x = t->x + inset;
        line.y = t->y + row;
        line.w = t->w - 2 * inset;
        line.h = 1;
        SDL_SetRenderDrawColor(renderer, 12, 14, 20, 118);
        SDL_RenderFillRect(renderer, &line);
        if (row < top3) {
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 14 - 14 * row / top3);
            SDL_RenderFillRect(renderer, &line);
        }

        if (row == 1 && t->h > 12) {                    /* a thin highlight just inside the top edge */
            SDL_Rect hi = { line.x + 2, line.y, line.w - 4, 1 };

            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 26);
            SDL_RenderFillRect(renderer, &hi);
        }

        SDL_SetRenderDrawColor(renderer, 255, 255, 255, 64 - 40 * row / t->h);
        if (row == 0 || row == t->h - 1) {
            SDL_RenderFillRect(renderer, &line);        /* top and bottom edge */
        } else {
            /* a short piece at each end that follows the curve */
            piece = 1 + FFABS(ui_rr_inset(row + 1, t->h, r) - inset);
            line.w = piece;
            SDL_RenderFillRect(renderer, &line);
            line.x = t->x + t->w - inset - piece;
            SDL_RenderFillRect(renderer, &line);
        }
    }
}

''', "glass: shadow, hairline edge")

patch("    ui_glass(&p, 24);\n    x_right = p.x + p.w - 32;\n",
      "    ui_glass(&p, 28);\n    x_right = p.x + p.w - 32;\n", "preferences corners")

# ============================================================ menu rows and state

patch("#define UI_MENU_ITEMS 6         /* rows in the menu */\n\n"
      "static const char *ui_menu_label[UI_MENU_ITEMS] = { \"Open File...\", \"Open Folder...\", \"Queue\",\n"
      "                                                    \"Media Info\", \"Preferences...\", \"Quit\" };\n",
      "#define UI_MENU_ITEMS 5         /* rows in the menu */\n"
      "#define UI_ROW_OPEN  0          /* Open: File... and Folder... appear beside it */\n"
      "#define UI_ROW_QUEUE 1\n"
      "#define UI_ROW_INFO  2\n"
      "#define UI_ROW_PREFS 3\n"
      "#define UI_ROW_QUIT  4\n\n"
      "static const char *ui_menu_label[UI_MENU_ITEMS] = { \"Open\", \"Queue\", \"Media Info\",\n"
      "                                                    \"Preferences...\", \"Quit\" };\n",
      "menu rows")

patch("static int ui_info_open = 0;    /* 1 while the Media Info panel is showing beside the menu */\n",
      "static int ui_info_open = 0;    /* 1 while the Media Info panel is showing beside the menu */\n"
      "static int ui_open_open = 0;    /* 1 while the File / Folder choices are showing beside \"Open\" */\n"
      "static int ui_open_hover = -1;  /* the choice under the mouse (0 = File, 1 = Folder) */\n"
      "static int ui_q_reveal = 0;     /* 1 = the queue panel was just opened: scroll to the playing item */\n"
      "static int ui_ctx_open = 0;     /* 1 while the right-click menu of a queue item is showing */\n"
      "static int ui_ctx_x, ui_ctx_y;  /* where it was opened */\n"
      "static int ui_ctx_hover = -1;   /* its row under the mouse */\n"
      "static char *ui_ctx_name = NULL;    /* the queue item it is for */\n"
      "static int ui_q_hover_kind = 0;     /* what the mouse is over in the queue panel (UI_Q_NONE ...) */\n"
      "static int ui_q_hover_idx = -1;     /* ... and which item or choice */\n",
      "menu state")

# ============================================================ the queue panel: geometry

patch_between("/* ----- the queue panel: opens beside the \"Queue\" row ----- */",
              "/* The list position where the dragged item would land */",
              r'''/* ----- the queue panel: opens beside the "Queue" row ----- */
#define UI_Q_W 420              /* panel width */
#define UI_Q_HEAD 52            /* the top row: add, previous, play/pause, next, shuffle */
#define UI_Q_ROW 40             /* one queue item */
#define UI_Q_PAD 10             /* space above and below the rows */
#define UI_Q_FOOT 116           /* under the list: crossfade, sleep timer and the counter */

/* What the mouse is over in the panel */
#define UI_Q_NONE 0
#define UI_Q_ADD  1             /* "Add to queue..." */
#define UI_Q_SHUF 2             /* the shuffle icon */
#define UI_Q_ITEM 3             /* a queue item */
#define UI_Q_DOT  4             /* the drag dot at the end of an item */
#define UI_Q_PREV 5             /* previous */
#define UI_Q_PLAY 6             /* play / pause */
#define UI_Q_NEXT 7             /* next */
#define UI_Q_DEL  8             /* the x that removes an item */
#define UI_Q_XF_DEC 9           /* crossfade: shorter */
#define UI_Q_XF_INC 10          /* crossfade: longer */
#define UI_Q_SLEEP  11          /* the sleep timer row */
#define UI_Q_CHIP   12          /* one of its choices (the number is in the item) */

/* How many items are shown at once (the panel scrolls beyond that) */
static int ui_q_visible(int wh)
{
    int room = (wh - 16 - 2 * UI_Q_PAD - UI_Q_HEAD - UI_Q_FOOT) / UI_Q_ROW;

    return av_clip(FFMAX(q_count, 1), 1, av_clip(room, 1, 14));
}

/* Where the panel is: beside the menu, level with the "Queue" row */
static SDL_Rect ui_q_rect(int ww, int wh)
{
    SDL_Rect m = ui_menu_rect(ww, wh), p;
    int gap = ui_idle ? 14 : 22;

    p.w = FFMIN(FFMIN(UI_Q_W, FFMAX(ww / 3, 360)), ww - 16);
    p.h = 2 * UI_Q_PAD + UI_Q_HEAD + ui_q_visible(wh) * UI_Q_ROW + UI_Q_FOOT;
    if (m.x + m.w + gap + p.w <= ww - 8)
        p.x = m.x + m.w + gap;                  /* to the right of the menu */
    else
        p.x = FFMAX(m.x - gap - p.w, 8);        /* no room there: to the left */
    p.y = av_clip(m.y + UI_ROW_QUEUE * UI_MENU_ROW - UI_Q_PAD, 8, FFMAX(wh - p.h - 8, 8));
    return p;
}

/* The choices of the sleep timer. Chosen with ui_sleep_choose(): 0 = off, 1 = end of track, 2 to 5 = minutes. */
static const char *const ui_chip_full[6] = { "Off", "End of track", "5 min", "10 min", "30 min", "1 hr" };
static const char *const ui_chip_short[6] = { "Off", "End", "5m", "10m", "30m", "1h" };

/* Where the six choices go when the sleep row is open (cy = the middle of the row). The long names are
   used when they fit, the short ones when the window is narrow. Returns the names to draw. */
static const char *const *ui_q_chips(const SDL_Rect *p, int cy, SDL_Rect out[6])
{
    const char *const *names = ui_chip_full;
    int pass, i, w[6], total = 0, x;

    for (pass = 0; pass < 2; pass++) {
        total = 0;
        for (i = 0; i < 6; i++) {
            w[i] = ui_text_width(names[i], 16) + 14;
            total += w[i] + (i ? 4 : 0);
        }
        if (total <= p->w - 32)
            break;
        names = ui_chip_short;
    }
    x = p->x + (p->w - total) / 2;
    for (i = 0; i < 6; i++) {
        out[i].x = x;
        out[i].y = cy - 13;
        out[i].w = w[i];
        out[i].h = 26;
        x += w[i] + 4;
    }
    return names;
}

''', "queue panel: geometry and footer zones")

patch_between("/* What is at (x, y) in the panel? item = the queue item for ITEM, DOT and DEL. */",
              "/* Is this text (the inside of a bracket) only download or codec information, like 1080p_25fps_H264? */",
              r'''/* What is at (x, y) in the panel? item = the queue item for ITEM, DOT and DEL, or the choice for CHIP. */
static int ui_q_hit(const SDL_Rect *p, int wh, int x, int y, int *item)
{
    int top = p->y + UI_Q_PAD + UI_Q_HEAD, slot, drop = 0, right = p->x + p->w;
    int fy = top + ui_q_visible(wh) * UI_Q_ROW, i;
    SDL_Rect chip[6];

    *item = -1;
    if (x < p->x || x >= right || y < p->y || y >= p->y + p->h)
        return UI_Q_NONE;
    if (y < top) {                              /* the top row */
        if (y < p->y + UI_Q_PAD)
            return UI_Q_NONE;
        if (x >= right - 56)
            return UI_Q_SHUF;
        if (x >= right - 96)
            return UI_Q_NEXT;
        if (x >= right - 136)
            return UI_Q_PLAY;
        if (x >= right - 176)
            return UI_Q_PREV;
        return UI_Q_ADD;
    }
    if (y >= fy) {                              /* under the list */
        if (y >= fy + 6 && y < fy + 46) {       /* crossfade: the left half of the value shortens it */
            if (x < right - 170)
                return UI_Q_NONE;
            return x < right - 84 ? UI_Q_XF_DEC : UI_Q_XF_INC;
        }
        if (y >= fy + 46 && y < fy + 86) {      /* sleep timer */
            if (ui_q_hover_kind == UI_Q_SLEEP || ui_q_hover_kind == UI_Q_CHIP) {    /* the choices are showing */
                ui_q_chips(p, fy + 66, chip);
                for (i = 0; i < 6; i++)
                    if (x >= chip[i].x && x < chip[i].x + chip[i].w) {
                        *item = i;
                        return UI_Q_CHIP;
                    }
            }
            return UI_Q_SLEEP;
        }
        return UI_Q_NONE;
    }
    slot = (y - top) / UI_Q_ROW;
    if (slot >= ui_q_visible(wh) || ui_q_scroll + slot >= q_count)
        return UI_Q_NONE;
    if (ui_q_drag >= 0)
        drop = ui_q_drop(wh, p);
    *item = ui_q_slot_item(ui_q_scroll + slot, drop);
    if (x >= right - 48)
        return UI_Q_DOT;
    if (x >= right - 86)
        return UI_Q_DEL;
    return UI_Q_ITEM;
}

/* Should a panel stay open with the mouse here? The panel, plus the gap to its menu row. */
static int ui_q_keep(const SDL_Rect *m, const SDL_Rect *p, int x, int y, int row)
{
    int row_top = m->y + row * UI_MENU_ROW;
    int x0 = p->x >= m->x ? m->x + m->w : p->x + p->w;
    int x1 = p->x >= m->x ? p->x : m->x;

    if (x >= p->x - 6 && x < p->x + p->w + 6 && y >= p->y - 6 && y < p->y + p->h + 6)
        return 1;
    return x >= x0 && x < x1 && y >= row_top - 6 && y < row_top + UI_MENU_ROW + 6;
}

''', "queue panel: hit testing")

# ============================================================ the queue panel: drawing

patch_between("static int ui_q_hover_kind = UI_Q_NONE;     /* what the mouse is over in the panel */",
              "/* ----- the Media Info panel: opens beside the \"Media Info\" row ----- */",
              r'''/* Choose what the sleep timer does: 0 = off, 1 = stop after the item that plays now, 2 to 5 = in 5, 10, 30
   or 60 minutes (the sound fades out over the last 20 seconds, then playback pauses) */
static void ui_sleep_choose(int sel)
{
    static const int minutes[6] = { 0, 0, 5, 10, 30, 60 };

    q_sleep_item = NULL;
    q_sleep_end = 0;
    ui_sleep_gain = 1.0f;
    ui_sleep_sel = 0;
    if (sel == 1 && q_pos >= 0 && q_pos < q_count) {
        q_sleep_item = q_items[q_pos];
        ui_sleep_sel = 1;
    } else if (sel >= 2 && sel <= 5) {
        q_sleep_end = av_gettime_relative() + (int64_t)minutes[sel] * 60 * 1000000;
        ui_sleep_sel = sel;
    }
}

/* The choice that is on now (0 to 5) */
static int ui_sleep_current(void)
{
    if (q_sleep_end)
        return av_clip(ui_sleep_sel, 2, 5);
    return q_sleep_item ? 1 : 0;
}

/* What the sleep row says while it is closed */
static void ui_sleep_text(char *out, size_t size)
{
    int i, left;

    if (q_sleep_end) {
        left = (int)((q_sleep_end - av_gettime_relative() + 999999) / 1000000);
        snprintf(out, size, "%d:%02d left", FFMAX(left, 0) / 60, FFMAX(left, 0) % 60);
    } else if (q_sleep_item) {
        for (i = 0; i < q_count; i++)
            if (q_items[i] == q_sleep_item)
                break;
        if (i == q_pos || i >= q_count)
            snprintf(out, size, "End of track");
        else
            snprintf(out, size, "After item %d", i + 1);
    } else {
        snprintf(out, size, "Off");
    }
}

/* h:mm:ss, or m:ss when the hours are not needed */
static void ui_fmt_clock(char *out, size_t size, double s, int hours)
{
    int t = (int)(s + 0.5);

    if (t < 0)
        t = 0;
    if (hours)
        snprintf(out, size, "%d:%02d:%02d", t / 3600, t / 60 % 60, t % 60);
    else
        snprintf(out, size, "%d:%02d", t / 60, t % 60);
}

static void ui_q_draw(int ww, int wh)
{
    static int64_t stats_at = 0;
    static double st_before = 0, st_total = 0;
    static int st_unknown = 0;
    SDL_Rect p = ui_q_rect(ww, wh), sep, dot, hl, chip[6];
    char name[300], text[96], a[24], b[24];
    const char *const *names;
    int vis = ui_q_visible(wh);
    int top = p.y + UI_Q_PAD + UI_Q_HEAD;
    int right = p.x + p.w;
    int max_w = p.w - 20 - 94;
    int drop = 0, i, item, cy, lit, hk = ui_q_hover_kind, fy, marker, sel, vx;
    int paused = ui_menu_stream && ui_menu_stream->paused;
    int64_t now = av_gettime_relative();
    double cur = 0, c;

    if (ui_q_reveal) {              /* just opened: show the playing item with two items above it */
        ui_q_scroll = q_pos - 2;
        ui_q_reveal = 0;
    }
    ui_q_scroll = av_clip(ui_q_scroll, 0, FFMAX(q_count - vis, 0));
    if (ui_q_drag >= 0)
        drop = ui_q_drop(wh, &p);
    ui_glass(&p, 22);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);

    /* top row: "Add to queue...", previous, play/pause, next and shuffle */
    cy = p.y + UI_Q_PAD + UI_Q_HEAD / 2;
    ui_label(p.x + 20, cy, "Add to queue...", 20, 240, 240, 240, hk == UI_Q_ADD ? 255 : 210);
    ui_transport_icon(0, right - 156, cy, hk == UI_Q_PREV ? 255 : 175);
    ui_transport_icon(paused ? 1 : 2, right - 116, cy, hk == UI_Q_PLAY ? 255 : 175);
    ui_transport_icon(3, right - 76, cy, hk == UI_Q_NEXT ? 255 : 175);
    if (q_shuffle)
        ui_shuffle_icon(right - 36, cy, cfg_bar_r, cfg_bar_g, cfg_bar_b, 255);     /* on: the bar color */
    else
        ui_shuffle_icon(right - 36, cy, 220, 220, 220, hk == UI_Q_SHUF ? 255 : 150);
    sep.x = p.x + 16;
    sep.y = top - 1;
    sep.w = p.w - 32;
    sep.h = 1;
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 40);
    SDL_RenderFillRect(renderer, &sep);

    if (q_count == 0)
        ui_label(p.x + 20, top + UI_Q_ROW / 2, "The queue is empty", 18, 220, 220, 220, 150);

    for (i = 0; i < vis && ui_q_scroll + i < q_count; i++) {
        item = ui_q_slot_item(ui_q_scroll + i, drop);
        cy = top + i * UI_Q_ROW + UI_Q_ROW / 2;
        lit = ui_q_drag < 0 && item == ui_q_hover_idx &&
              (hk == UI_Q_ITEM || hk == UI_Q_DOT || hk == UI_Q_DEL);
        marker = q_items[item] == q_sleep_item;
        if (lit) {                  /* a soft rounded highlight under the row the mouse is on */
            hl.x = p.x + 8;
            hl.y = cy - UI_Q_ROW / 2 + 2;
            hl.w = p.w - 16;
            hl.h = UI_Q_ROW - 4;
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 18);
            ui_rr_fill(&hl, 11);
        }
        ui_q_name(item, name, 290);
        ui_fit_text(name, 18, max_w - (marker ? 28 : 0));
        if (item == q_pos || item == ui_q_drag)
            ui_label(p.x + 20, cy, name, 18, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                     av_clip(cfg_bar_b + 40, 0, 255), 255);
        else
            ui_label(p.x + 20, cy, name, 18, 240, 240, 240, lit ? 255 : 205);
        if (marker)                 /* playback stops after this item */
            ui_label(right - 120, cy, "Zz", 15, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                     av_clip(cfg_bar_b + 40, 0, 255), 230);

        /* the x that removes the item */
        SDL_SetRenderDrawColor(renderer, 230, 230, 230, (lit && hk == UI_Q_DEL) ? 255 : 120);
        ui_q_line(right - 71, cy - 4, right - 63, cy + 4);
        ui_q_line(right - 71, cy + 4, right - 63, cy - 4);

        /* the dot to drag by: the bar color for the playing item and the one being dragged */
        dot.w = 10;
        dot.h = 10;
        dot.x = right - 30;
        dot.y = cy - 5;
        if (item == q_pos || item == ui_q_drag)
            SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 255);
        else
            SDL_SetRenderDrawColor(renderer, 200, 200, 200, lit ? 200 : 120);
        ui_pill(&dot);
    }

    /* under the list */
    fy = top + vis * UI_Q_ROW;
    sep.x = p.x + 16;
    sep.y = fy + 3;
    sep.w = p.w - 32;
    sep.h = 1;
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 40);
    SDL_RenderFillRect(renderer, &sep);

    /* crossfade: < 3 s > */
    cy = fy + 26;
    vx = right - 84;
    ui_label(p.x + 20, cy, "Crossfade", 18, 240, 240, 240, 210);
    ui_label(right - 154, cy, "<", 22, 190, 190, 190, hk == UI_Q_XF_DEC ? 255 : 170);
    ui_label(right - 26, cy, ">", 22, 190, 190, 190, hk == UI_Q_XF_INC ? 255 : 170);
    if (cfg_crossfade)
        snprintf(text, sizeof(text), "%d s", cfg_crossfade);
    else
        snprintf(text, sizeof(text), "Off");
    if (cfg_crossfade)
        ui_label_c(vx, cy, text, 18, 245, 245, 245, 255);
    else
        ui_label_c(vx, cy, text, 18, 150, 150, 150, 255);

    /* sleep timer: the value, or the choices while the mouse is on the row */
    cy = fy + 66;
    sel = ui_sleep_current();
    if (hk == UI_Q_SLEEP || hk == UI_Q_CHIP) {
        names = ui_q_chips(&p, cy, chip);
        for (i = 0; i < 6; i++) {
            int hot = hk == UI_Q_CHIP && ui_q_hover_idx == i;

            if (i == sel) {
                SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 215);
                ui_pill(&chip[i]);
            } else if (hot) {
                SDL_SetRenderDrawColor(renderer, 255, 255, 255, 38);
                ui_pill(&chip[i]);
            }
            ui_label_c(chip[i].x + chip[i].w / 2, cy, names[i], 16, 245, 245, 245, (i == sel || hot) ? 255 : 200);
        }
    } else {
        ui_label(p.x + 20, cy, "Sleep timer", 18, 240, 240, 240, 210);
        ui_sleep_text(text, sizeof(text));
        if (sel)
            ui_label(right - 20 - ui_text_width(text, 18), cy, text, 18, av_clip(cfg_bar_r + 40, 0, 255),
                     av_clip(cfg_bar_g + 40, 0, 255), av_clip(cfg_bar_b + 40, 0, 255), 255);
        else
            ui_label(right - 20 - ui_text_width(text, 18), cy, text, 18, 150, 150, 150, 255);
    }

    /* the counter: which item, and how far through the whole queue. Quiet on purpose. */
    if (now - stats_at > 400000 || now < stats_at) {
        queue_stats(ui_menu_stream != NULL, &st_before, &st_total, &st_unknown);
        stats_at = now;
    }
    if (ui_menu_stream) {
        c = get_master_clock(ui_menu_stream);
        if (!isnan(c)) {
            cur = c;
            if (ui_menu_stream->ic && ui_menu_stream->ic->start_time != AV_NOPTS_VALUE)
                cur -= ui_menu_stream->ic->start_time / (double)AV_TIME_BASE;
        }
    }
    ui_fmt_clock(a, sizeof(a), st_before + FFMAX(cur, 0), st_total >= 3600);
    ui_fmt_clock(b, sizeof(b), st_total, st_total >= 3600);
    snprintf(text, sizeof(text), "%d/%d   [%s / %s%s]", FFMAX(q_pos + 1, 0), q_count, a, b, st_unknown ? "+" : "");
    ui_label(p.x + 20, fy + 100, text, 15, 170, 170, 170, 255);
}

''', "queue panel: drawing")

# the info panel sits one row higher now
patch("    p.y = av_clip(m.y + 3 * UI_MENU_ROW - UI_I_PAD, 8, FFMAX(wh - p.h - 8, 8));\n",
      "    p.y = av_clip(m.y + UI_ROW_INFO * UI_MENU_ROW - UI_I_PAD, 8, FFMAX(wh - p.h - 8, 8));\n",
      "info panel position")
patch("    ui_glass(&p, 20);\n    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);\n    if (n == 0) {\n",
      "    ui_glass(&p, 22);\n    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);\n    if (n == 0) {\n",
      "info panel corners")

# ============================================================ the menu, the Open choices, the item menu

patch_between("static void ui_menu_draw(void)\n{",
              "/* The mouse button was released: drop the dragged queue item.",
              r'''/* End the file that is playing. The main loop then goes on with whatever queue_next() says. */
static void ui_end_current(VideoState *is)
{
    SDL_Event e;

    if (!is)
        return;
    ui_user_skip = 1;
    SDL_zero(e);
    e.type = FF_QUIT_EVENT;
    e.user.data1 = is;
    SDL_PushEvent(&e);
}

/* ----- "Open": the File and Folder choices ----- */
static SDL_Rect ui_open_rect(int ww, int wh)
{
    SDL_Rect m = ui_menu_rect(ww, wh), p;
    int gap = ui_idle ? 14 : 22;

    p.w = FFMAX(ui_text_width("Folder...", 22), ui_text_width("File...", 22)) + 64;
    p.h = 2 * UI_MENU_ROW + 16;
    if (m.x + m.w + gap + p.w <= ww - 8)
        p.x = m.x + m.w + gap;
    else
        p.x = FFMAX(m.x - gap - p.w, 8);
    p.y = av_clip(m.y + UI_ROW_OPEN * UI_MENU_ROW - 8, 8, FFMAX(wh - p.h - 8, 8));
    return p;
}

/* 0 = File, 1 = Folder, -1 = neither */
static int ui_open_hit(const SDL_Rect *p, int x, int y)
{
    if (x < p->x || x >= p->x + p->w || y < p->y + 8 || y >= p->y + 8 + 2 * UI_MENU_ROW)
        return -1;
    return (y - p->y - 8) / UI_MENU_ROW;
}

static void ui_open_draw(int ww, int wh)
{
    SDL_Rect p = ui_open_rect(ww, wh), hl;
    int i, row_y;

    ui_glass(&p, 20);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    for (i = 0; i < 2; i++) {
        row_y = p.y + 8 + i * UI_MENU_ROW;
        if (i == ui_open_hover) {
            hl.x = p.x + 6;
            hl.y = row_y + 3;
            hl.w = p.w - 12;
            hl.h = UI_MENU_ROW - 6;
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 30);
            ui_rr_fill(&hl, 11);
        }
        ui_label_c(p.x + p.w / 2, row_y + UI_MENU_ROW / 2, i ? "Folder..." : "File...", 22, 240, 240, 240,
                   i == ui_open_hover ? 255 : 205);
    }
}

/* ----- the menu of a queue item (right-click) ----- */
#define UI_CTX_ROW 40

static const char *ui_ctx_label(int i)
{
    if (i == 0)
        return "Remove from queue";
    return ui_ctx_name && ui_ctx_name == q_sleep_item ? "Cancel sleep after item" : "Sleep after this item";
}

static SDL_Rect ui_ctx_rect(int ww, int wh)
{
    SDL_Rect r;
    int w = FFMAX(ui_text_width("Remove from queue", 20), ui_text_width("Cancel sleep after item", 20));

    r.w = w + 56;
    r.h = 2 * UI_CTX_ROW + 16;
    r.x = av_clip(ui_ctx_x, 8, FFMAX(ww - r.w - 8, 8));
    r.y = av_clip(ui_ctx_y, 8, FFMAX(wh - r.h - 8, 8));
    return r;
}

static int ui_ctx_hit(const SDL_Rect *r, int x, int y)
{
    if (x < r->x || x >= r->x + r->w || y < r->y + 8 || y >= r->y + 8 + 2 * UI_CTX_ROW)
        return -1;
    return (y - r->y - 8) / UI_CTX_ROW;
}

static void ui_ctx_draw(int ww, int wh)
{
    SDL_Rect r = ui_ctx_rect(ww, wh), hl;
    int i, row_y;

    ui_glass(&r, 18);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    for (i = 0; i < 2; i++) {
        row_y = r.y + 8 + i * UI_CTX_ROW;
        if (i == ui_ctx_hover) {
            hl.x = r.x + 6;
            hl.y = row_y + 3;
            hl.w = r.w - 12;
            hl.h = UI_CTX_ROW - 6;
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 30);
            ui_rr_fill(&hl, 11);
        }
        ui_label_c(r.x + r.w / 2, row_y + UI_CTX_ROW / 2, ui_ctx_label(i), 20, 240, 240, 240,
                   i == ui_ctx_hover ? 255 : 205);
    }
}

/* 0 = remove the item, 1 = sleep after it (or stop doing that) */
static void ui_ctx_action(VideoState *is, int act)
{
    char *name = ui_ctx_name;
    int i, idx = -1, was_playing;

    ui_ctx_open = 0;
    ui_ctx_name = NULL;
    ui_ctx_hover = -1;
    for (i = 0; i < q_count; i++)
        if (q_items[i] == name)
            idx = i;
    if (idx < 0)
        return;
    if (act == 0) {
        was_playing = (idx == q_pos);
        queue_remove(idx);
        ui_q_hover_kind = UI_Q_NONE;
        ui_q_hover_idx = -1;
        if (was_playing)
            ui_end_current(is);     /* the next item takes its place */
    } else {
        q_sleep_end = 0;
        ui_sleep_gain = 1.0f;
        q_sleep_item = (q_sleep_item == q_items[idx]) ? NULL : q_items[idx];
        ui_sleep_sel = q_sleep_item ? 1 : 0;
    }
}

static void ui_q_show(void)
{
    if (!ui_q_open)
        ui_q_reveal = 1;            /* scroll to the playing item the first time it is drawn */
    ui_q_open = 1;
}

static void ui_menu_draw(void)
{
    SDL_Rect r, card, row, hl;
    int ww, wh, i, pad, cy, lit;

    if (ui_prefs_open || (!ui_idle && !ui_menu_open))
        return;
    if (ui_ctx_open && (!ui_q_open || (!ui_idle && !ui_menu_open)))
        ui_ctx_open = 0;
    SDL_GetWindowSize(window, &ww, &wh);
    r = ui_menu_rect(ww, wh);

    /* The popup gets a glass card around its rows. The idle screen has no card at all. */
    if (!ui_idle) {
        pad = 8;
        card.x = r.x - pad;
        card.y = r.y - pad;
        card.w = r.w + 2 * pad;
        card.h = r.h + 2 * pad;
        ui_glass(&card, 20);
    }

    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    for (i = 0; i < UI_MENU_ITEMS; i++) {
        row.x = r.x;
        row.y = r.y + i * UI_MENU_ROW;
        row.w = r.w;
        row.h = UI_MENU_ROW;
        cy = row.y + row.h / 2;
        lit = i == ui_menu_hover || (i == UI_ROW_OPEN && ui_open_open) ||
              (i == UI_ROW_QUEUE && ui_q_open) || (i == UI_ROW_INFO && ui_info_open);
        if (lit) {                  /* a soft rounded highlight behind the row */
            hl.x = row.x + 6;
            hl.y = row.y + 3;
            hl.w = row.w - 12;
            hl.h = row.h - 6;
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 30);
            ui_rr_fill(&hl, 11);
        }
        if (i == UI_ROW_QUEUE || i == UI_ROW_INFO)
            ui_label(row.x + 28, cy, ui_menu_label[i], 22, 240, 240, 240, lit ? 255 : 205);
        else
            ui_label_c(row.x + row.w / 2, cy, ui_menu_label[i], 22, 240, 240, 240, lit ? 255 : 205);
        if (i == UI_ROW_OPEN || i == UI_ROW_QUEUE || i == UI_ROW_INFO)
            ui_chevron(row.x + r.w - 22, cy, lit ? 255 : 170);
    }
    if (ui_idle) {
        int ls, gap;

        ui_logo_metrics(ww, wh, &ls, &gap);
        ui_logo_draw(r.x - gap - ls / 2, wh / 2, ls);
    }
    if (ui_open_open)
        ui_open_draw(ww, wh);
    else if (ui_q_open)
        ui_q_draw(ww, wh);
    else if (ui_info_open)
        ui_info_draw(ww, wh);
    if (ui_ctx_open)
        ui_ctx_draw(ww, wh);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);
}

/* Do what a menu row says */
static void ui_menu_action(VideoState *is, int item)
{
    if (item == UI_ROW_OPEN) {          /* Open: the choices appear beside it */
        ui_open_open = 1;
        ui_q_open = 0;
        ui_info_open = 0;
        return;
    }
    if (item == UI_ROW_QUEUE) {         /* Queue: show the queue panel */
        ui_q_show();
        ui_info_open = 0;
        ui_open_open = 0;
        return;
    }
    if (item == UI_ROW_INFO) {          /* Media Info: show the information panel */
        ui_info_open = 1;
        ui_q_open = 0;
        ui_open_open = 0;
        return;
    }
    ui_menu_open = 0;
    ui_menu_hover = -1;
    ui_q_open = 0;
    ui_info_open = 0;
    ui_open_open = 0;
    if (item == UI_ROW_PREFS) {
        ui_prefs_open = 1;
        ui_prefs_hover = -1;
    } else {
        do_exit(is);                /* Quit */
    }
}

/* Mouse events in the queue panel. Returns 1 if the panel used the event. */
static int ui_q_mouse(VideoState *is, SDL_Event *ev, int ww, int wh, int x, int y)
{
    SDL_Rect p = ui_q_rect(ww, wh);
    int item, kind = ui_q_hit(&p, wh, x, y, &item);
    int was_playing;

    if (ev->type == SDL_MOUSEMOTION) {
        ui_q_hover_kind = kind;
        ui_q_hover_idx = item;
        if (kind != UI_Q_NONE) {
            ui_menu_hover = UI_ROW_QUEUE;   /* the "Queue" row stays lit while the mouse is in the panel */
            return 1;
        }
        return 0;
    }
    if (ev->type != SDL_MOUSEBUTTONDOWN || ev->button.button != SDL_BUTTON_LEFT)
        return 0;
    if (kind == UI_Q_NONE)          /* a click on the panel's padding does nothing */
        return x >= p.x && x < p.x + p.w && y >= p.y && y < p.y + p.h;

    if (kind == UI_Q_ADD) {
        ui_menu_open = 0;
        ui_q_open = 0;
        ui_menu_hover = -1;
        ui_pick_start(2);           /* choose files to add to the queue */
    } else if (kind == UI_Q_SHUF) {
        queue_set_shuffle(!q_shuffle);
    } else if (kind == UI_Q_PREV) {
        q_step = -1;                /* the main loop plays the item before this one */
        ui_end_current(is);
    } else if (kind == UI_Q_NEXT) {
        q_step = 1;
        ui_end_current(is);
    } else if (kind == UI_Q_PLAY) {
        if (is)
            toggle_pause(is);
        else if (q_count > 0)       /* the idle screen: play the queue from the top, or go on after a sleep stop */
            q_forced = (q_hold && q_pos + 1 < q_count) ? q_pos + 1 : 0;
    } else if (kind == UI_Q_XF_DEC || kind == UI_Q_XF_INC) {
        cfg_crossfade = av_clip(cfg_crossfade + (kind == UI_Q_XF_INC ? 1 : -1), 0, 10);
        settings_save();
    } else if (kind == UI_Q_CHIP) {
        ui_sleep_choose(item);
    } else if (kind == UI_Q_SLEEP) {
        /* the row itself: the choices are showing, nothing to do */
    } else if (kind == UI_Q_DEL) {
        was_playing = (item == q_pos);
        queue_remove(item);
        ui_q_hover_kind = UI_Q_NONE;
        ui_q_hover_idx = -1;
        if (was_playing)
            ui_end_current(is);     /* the next item takes its place */
    } else if (kind == UI_Q_DOT) {
        ui_q_drag = item;           /* start dragging this item */
        ui_q_drag_y = y;
        SDL_CaptureMouse(SDL_TRUE); /* keep getting the mouse even outside the window */
    } else {                        /* an item: play it now */
        q_forced = item;
        ui_end_current(is);         /* the menu stays open, so you can keep browsing the queue */
    }
    return 1;
}

/* Mouse events for the menu. Returns 1 if the menu used the event.
   is = the stream playing now, or NULL on the idle screen. */
static int ui_menu_mouse(VideoState *is, SDL_Event *ev)
{
    SDL_Rect r, p, ip, op;
    int ww, wh, x, y, row, kind, item, hit;

    if (ui_prefs_open)
        return ui_prefs_mouse(is, ev);

    ui_menu_last_move = av_gettime_relative();     /* the popup closes when the mouse rests */

    if (ui_ctx_open && (!ui_q_open || (!ui_idle && !ui_menu_open)))
        ui_ctx_open = 0;
    if (ui_ctx_open) {              /* the item menu owns the mouse until it closes */
        SDL_GetWindowSize(window, &ww, &wh);
        op = ui_ctx_rect(ww, wh);
        x = (ev->type == SDL_MOUSEMOTION) ? ev->motion.x : ev->button.x;
        y = (ev->type == SDL_MOUSEMOTION) ? ev->motion.y : ev->button.y;
        hit = ui_ctx_hit(&op, x, y);
        if (ev->type == SDL_MOUSEMOTION) {
            ui_ctx_hover = hit;
        } else if (ev->type == SDL_MOUSEBUTTONDOWN) {
            if (ev->button.button == SDL_BUTTON_LEFT && hit >= 0)
                ui_ctx_action(is, hit);
            else
                ui_ctx_open = 0;    /* a click anywhere else (or a right-click) closes it */
        }
        ui_wake();
        if (is)
            is->force_refresh = 1;
        return 1;
    }

    if (ev->type == SDL_MOUSEBUTTONDOWN && ev->button.button == SDL_BUTTON_RIGHT && ui_q_open &&
        ui_q_drag < 0 && (ui_idle || ui_menu_open)) {
        /* right-click on a queue item: its own menu */
        SDL_GetWindowSize(window, &ww, &wh);
        p = ui_q_rect(ww, wh);
        kind = ui_q_hit(&p, wh, ev->button.x, ev->button.y, &item);
        if (item >= 0 && (kind == UI_Q_ITEM || kind == UI_Q_DOT || kind == UI_Q_DEL)) {
            ui_ctx_open = 1;
            ui_ctx_x = ev->button.x;
            ui_ctx_y = ev->button.y;
            ui_ctx_name = q_items[item];
            ui_ctx_hover = -1;
            ui_wake();
            if (is)
                is->force_refresh = 1;
            return 1;
        }
        if (ev->button.x >= p.x && ev->button.x < p.x + p.w && ev->button.y >= p.y && ev->button.y < p.y + p.h)
            return 1;               /* a right-click on the rest of the panel does nothing */
    }
    if (ev->type == SDL_MOUSEBUTTONDOWN && ev->button.button == SDL_BUTTON_RIGHT && !ui_idle) {
        /* right-click on the video: open the menu at the mouse */
        ui_menu_open = 1;
        ui_menu_x = ev->button.x;
        ui_menu_y = ev->button.y;
        ui_menu_hover = -1;
        ui_q_open = 0;
        ui_info_open = 0;
        ui_open_open = 0;
        ui_q_drag = -1;
        ui_wake();
        if (is)
            is->force_refresh = 1;
        return 1;
    }
    if (!ui_idle && !ui_menu_open)
        return 0;

    SDL_GetWindowSize(window, &ww, &wh);
    r = ui_menu_rect(ww, wh);
    x = (ev->type == SDL_MOUSEMOTION) ? ev->motion.x : ev->button.x;
    y = (ev->type == SDL_MOUSEMOTION) ? ev->motion.y : ev->button.y;
    row = (x >= r.x && x < r.x + r.w && y >= r.y && y < r.y + r.h) ? (y - r.y) / UI_MENU_ROW : -1;

    if (ui_q_drag >= 0) {           /* dragging a queue item: the panel owns the mouse */
        if (ev->type == SDL_MOUSEMOTION) {
            ui_q_drag_y = y;
            ui_wake();
            ui_q_autoscroll();
        }
        if (is)
            is->force_refresh = 1;
        return 1;
    }
    if (ui_open_open) {             /* the File / Folder choices */
        op = ui_open_rect(ww, wh);
        hit = ui_open_hit(&op, x, y);
        if (hit >= 0 || (x >= op.x && x < op.x + op.w && y >= op.y && y < op.y + op.h)) {
            if (ev->type == SDL_MOUSEMOTION) {
                ui_open_hover = hit;
                ui_menu_hover = UI_ROW_OPEN;    /* the "Open" row stays lit */
            } else if (ev->type == SDL_MOUSEBUTTONDOWN && ev->button.button == SDL_BUTTON_LEFT && hit >= 0) {
                ui_menu_open = 0;
                ui_menu_hover = -1;
                ui_open_open = 0;
                ui_open_hover = -1;
                ui_pick_start(hit);     /* 0 = Open File, 1 = Open Folder */
            }
            ui_wake();
            if (is)
                is->force_refresh = 1;
            return 1;
        }
        ui_open_hover = -1;
    }
    if (ui_q_open && ui_q_mouse(is, ev, ww, wh, x, y)) {
        if (is)
            is->force_refresh = 1;
        return 1;
    }
    if (ui_info_open) {             /* the information panel only shows things, but it keeps the mouse */
        ip = ui_info_rect(ww, wh, ui_info_collect(is));
        if (x >= ip.x && x < ip.x + ip.w && y >= ip.y && y < ip.y + ip.h) {
            if (ev->type == SDL_MOUSEMOTION)
                ui_menu_hover = UI_ROW_INFO;
            if (is)
                is->force_refresh = 1;
            return 1;
        }
    }

    if (ev->type == SDL_MOUSEMOTION) {
        ui_menu_hover = row;
        if (row == UI_ROW_OPEN) {
            ui_open_open = 1;       /* hovering "Open" shows File... and Folder... */
            ui_q_open = 0;
            ui_info_open = 0;
        } else if (row == UI_ROW_QUEUE) {
            ui_q_show();            /* hovering "Queue" opens the queue panel */
            ui_info_open = 0;
            ui_open_open = 0;
        } else if (row == UI_ROW_INFO) {
            ui_info_open = 1;       /* hovering "Media Info" opens the information panel */
            ui_q_open = 0;
            ui_open_open = 0;
        } else {
            if (ui_open_open) {
                op = ui_open_rect(ww, wh);
                if (!ui_q_keep(&r, &op, x, y, UI_ROW_OPEN))
                    ui_open_open = 0;
            }
            if (ui_q_open) {
                p = ui_q_rect(ww, wh);
                if (!ui_q_keep(&r, &p, x, y, UI_ROW_QUEUE))
                    ui_q_open = 0;
            }
            if (ui_info_open) {
                ip = ui_info_rect(ww, wh, ui_info_collect(is));
                if (!ui_q_keep(&r, &ip, x, y, UI_ROW_INFO))
                    ui_info_open = 0;
            }
        }
        ui_wake();
        if (is)
            is->force_refresh = 1;
        return ui_menu_open;        /* the popup swallows mouse movement; the idle screen doesn't */
    }
    if (ev->type == SDL_MOUSEBUTTONDOWN && ev->button.button == SDL_BUTTON_LEFT) {
        if (row >= 0) {
            ui_menu_action(is, row);
        } else if (ui_menu_open) {
            ui_menu_open = 0;       /* click outside closes the popup */
            ui_q_open = 0;
            ui_info_open = 0;
            ui_open_open = 0;
        } else {
            return 0;               /* idle screen: clicking elsewhere moves the window */
        }
        if (is)
            is->force_refresh = 1;
        return 1;
    }
    return 0;
}

''', "menu: rows, Open choices, item menu, mouse")

patch_between("/* The popup menu closes when the mouse has rested on it for 5 seconds",
              "/* While an item is dragged near the top or bottom of the queue list",
              r'''/* The popup menu closes when the mouse has rested on it for 5 seconds, unless the mouse is on the
   Open, Queue or Media Info panel (while a panel is open, it keeps the menu open). While the queue panel
   is showing, the picture is redrawn every second so the counter keeps up. */
static void ui_menu_tick(VideoState *is)
{
    static int64_t last_second = 0;
    int64_t second = av_gettime_relative() / 1000000;

    if (ui_q_open && (ui_menu_open || ui_idle) && second != last_second) {
        last_second = second;
        is->force_refresh = 1;
    }
    if (!ui_menu_open || ui_idle || ui_prefs_open || ui_q_drag >= 0 || ui_q_open || ui_info_open ||
        ui_open_open || ui_ctx_open)
        return;
    if (av_gettime_relative() - ui_menu_last_move > 5000000) {
        ui_menu_open = 0;
        ui_menu_hover = -1;
        is->force_refresh = 1;
    }
}

''', "menu tick")



# ============================================================ crossfade and sleep timer

patch("static void refresh_loop_wait_event(VideoState *is, SDL_Event *event) {\n",
      r'''/* ----- the sleep timer and the crossfade: both are checked on every turn of the event loop ----- */

/* Close the next item if it was started early */
static void ui_xf_abort(void)
{
    if (xf_stream) {
        stream_close(xf_stream);
        xf_stream = NULL;
    }
    xf_name = NULL;
}

/* A timed sleep: the sound fades out over the last 20 seconds, then playback pauses.
   is = the stream playing now, or NULL on the idle screen. */
static void ui_sleep_tick(VideoState *is)
{
    int64_t left;

    if (!q_sleep_end)
        return;
    left = q_sleep_end - av_gettime_relative();
    if (left <= 0) {
        q_sleep_end = 0;
        ui_sleep_sel = 0;
        ui_sleep_gain = 1.0f;
        ui_xf_abort();
        if (is) {
            is->xf_gain = 1.0f;
            if (!is->paused)
                toggle_pause(is);
            is->force_refresh = 1;
        }
        return;
    }
    ui_sleep_gain = left < 20000000 ? (float)(left / 20000000.0) : 1.0f;
}

/* The crossfade. Shortly before an item ends, the next one is opened as a second stream and starts
   playing quietly. The old one fades out while the new one fades in; when the old one ends, the new
   one simply becomes the stream that is playing (see the main loop). */
static void ui_xfade_tick(VideoState *is)
{
    VideoState *xf = xf_stream;
    double dur, pos, rem, t, c;
    int n = cfg_crossfade, next;

    if (!is || !is->ic || !is->audio_st || q_pos < 0 || q_pos >= q_count)
        return;
    pos = get_master_clock(is);
    if (isnan(pos))
        return;
    if (is->ic->start_time != AV_NOPTS_VALUE)
        pos -= is->ic->start_time / (double)AV_TIME_BASE;
    dur = is->ic->duration > 0 ? is->ic->duration / (double)AV_TIME_BASE : 0;
    rem = dur - pos;
    next = queue_next();

    if (xf) {
        if (n <= 0 || dur <= 0 || next >= q_count || xf_name != q_items[next] || rem > n + 1.0 ||
            (q_sleep_item && q_sleep_item == q_items[q_pos])) {
            is->xf_gain = 1.0f;         /* the plan changed (a seek, a click, the setting): back to normal */
            ui_xf_abort();
            return;
        }
        t = av_clipd(1.0 - rem / n, 0.0, 1.0);
        is->xf_gain = (float)cos(t * M_PI / 2);     /* equal power: the total loudness stays level */
        xf->xf_gain = (float)sin(t * M_PI / 2);
        xf->audio_volume = is->audio_volume;
        xf->muted = is->muted;
        if (xf->paused != is->paused)
            stream_toggle_pause(xf);
        c = get_master_clock(xf);               /* nothing shows its pictures yet: drop the old ones */
        if (!isnan(c))
            while (frame_queue_nb_remaining(&xf->pictq) > 1) {
                Frame *nx = frame_queue_peek_next(&xf->pictq);

                if (isnan(nx->pts) || nx->pts >= c)
                    break;
                frame_queue_next(&xf->pictq);
            }
        return;
    }

    if (n <= 0 || is->paused || dur < 2.0 * n + 2.0 || rem > n || rem < 0.3 || q_forced >= 0 || q_step != 1 ||
        next >= q_count || next == q_pos || q_hold || ui_seek_want || q_items[next] == xf_failed ||
        (q_sleep_item && q_sleep_item == q_items[q_pos]))
        return;
    if (!window_title)
        window_title = input_filename;          /* so opening the next item leaves the window title alone */
    startup_volume = 100;
    xf_open_gain = 0.0f;                        /* silent from the first moment */
    xf = stream_open(q_items[next], file_iformat);
    xf_open_gain = 1.0f;
    if (!xf) {
        xf_failed = q_items[next];
        return;
    }
    xf->audio_volume = is->audio_volume;
    xf->muted = is->muted;
    xf_stream = xf;
    xf_name = q_items[next];
}

static void refresh_loop_wait_event(VideoState *is, SDL_Event *event) {
''', "crossfade and sleep ticks")

patch("        ui_power_tick(is);\n        if (ui_q_autoscroll())\n",
      "        ui_power_tick(is);\n        ui_sleep_tick(is);\n        ui_xfade_tick(is);\n        if (ui_q_autoscroll())\n",
      "ticks in the event loop")

patch("        ui_inbox_tick(NULL);\n        ui_power_tick(NULL);\n",
      "        ui_inbox_tick(NULL);\n        ui_power_tick(NULL);\n        ui_sleep_tick(NULL);\n",
      "sleep tick on the idle screen")

# the next item may already be playing when the event loop hears about it
patch("        case FF_QUIT_EVENT:\n"
      "            /* The file ended, or n / p / Open was used: the main loop starts the next item */\n"
      "            if (event.user.data1 != cur_stream)\n",
      "        case FF_QUIT_EVENT:\n"
      "            /* The item that was started early ended or failed: forget it and carry on with this one */\n"
      "            if (xf_stream && event.user.data1 == xf_stream) {\n"
      "                cur_stream->xf_gain = 1.0f;\n"
      "                xf_failed = xf_name;\n"
      "                ui_xf_abort();\n"
      "                break;\n"
      "            }\n"
      "            /* The file ended, or n / p / Open was used: the main loop starts the next item */\n"
      "            if (event.user.data1 != cur_stream)\n",
      "an early item failed")

patch("            case SDLK_n:\n            case SDLK_PERIOD:\n                q_step = 1;\n",
      "            case SDLK_n:\n            case SDLK_PERIOD:\n                ui_user_skip = 1;\n                q_step = 1;\n",
      "next key counts as a skip")
patch("            case SDLK_p:\n            case SDLK_COMMA:\n                q_step = -1;\n",
      "            case SDLK_p:\n            case SDLK_COMMA:\n                ui_user_skip = 1;\n                q_step = -1;\n",
      "previous key counts as a skip")

# ============================================================ idle screen and main loop

patch("    ui_q_open = 0;\n    ui_info_open = 0;\n    ui_q_drag = -1;\n\n    while (queue_next() >= q_count) {\n",
      "    ui_q_open = 0;\n    ui_info_open = 0;\n    ui_open_open = 0;\n    ui_ctx_open = 0;\n    ui_q_drag = -1;\n\n"
      "    /* wait here until there is something to play (after a sleep stop: until the user picks something) */\n"
      "    while (queue_next() >= q_count || (q_hold && q_forced < 0)) {\n",
      "idle screen waits after a sleep stop")

patch("        ui_glass_frame(NULL);\n        SDL_Delay(16);\n    }\n    ui_idle = 0;\n}\n",
      "        ui_glass_frame(NULL);\n        SDL_Delay(16);\n    }\n    q_hold = 0;\n    ui_idle = 0;\n}\n",
      "idle screen ends the sleep stop")

patch_between("    /* Play the queue. The window stays open between files and when the queue is empty. */",
              "    /* never returns */",
              r'''    /* Play the queue. The window stays open between files and when the queue is empty. */
    for (;;) {
        int next;

        if (q_pos >= 0 && q_pos < q_count && q_sleep_item && q_sleep_item == q_items[q_pos]) {
            q_sleep_item = NULL;                /* the item the sleep timer waited for is over */
            ui_sleep_sel = 0;
            if (!ui_user_skip)
                q_hold = 1;                     /* it ended by itself: stop here */
        }
        ui_user_skip = 0;
        next = queue_next();                    /* the next item */

        if (q_hold && q_forced < 0) {           /* stopped by the sleep timer: wait for the user */
            ui_xf_abort();
            ui_idle_loop();
            continue;
        }
        if (next >= q_count) {
            ui_xf_abort();
            if (cfg_quit_when_done && q_count > 0)
                do_exit(NULL);                  /* something was played and the queue is done */
            ui_idle_loop();                     /* nothing to play: idle screen */
            continue;
        }
        q_pos = next;
        q_step = 1;
        q_played[q_pos] = 1;
        q_forced = -1;
        if (!is_full_screen)
            screen_width = screen_height = 0;   /* window follows the next video's size */
        startup_volume = 100;                   /* ffplay converts this each time; keep it fresh */
        input_filename = q_items[q_pos];        /* read_thread and the title use it */
        window_title = NULL;
        if (xf_stream && xf_name == q_items[q_pos]) {
            /* it has been playing quietly under the end of the last item: carry on with it */
            is = xf_stream;
            xf_stream = NULL;
            xf_name = NULL;
            is->xf_gain = 1.0f;
        } else {
            ui_xf_abort();
            is = stream_open(q_items[q_pos], file_iformat);
            if (!is) {
                av_log(NULL, AV_LOG_FATAL, "Failed to initialize VideoState!\n");
                continue;                       /* skip it, try the next item */
            }
            if (ui_session_volume >= 0)
                is->audio_volume = ui_session_volume;
        }
        event_loop(is);                         /* returns when this item is over */
    }

''', "main loop: sleep stop and crossfade handover")

# Everything matched, so it is safe to write
open(path, "w").write(src)
print("Patched", path)
