#!/usr/bin/env python3
# Queue panel upgrade:
#   - the traditional shuffle icon (two crossing curves with arrow heads)
#   - shuffle is an on/off switch again: turning it ON shuffles the queue (a new order every time),
#     turning it OFF brings the original order back. Items that already played stay above the
#     playing item and are not shuffled back in. Items added while shuffle is on are mixed in.
#   - previous, play/pause and next buttons in the top row of the panel
#   - a small x before the dot of each item removes it from the queue
#   - item names no longer show download or codec info like (1080p_25fps_H264-128kbit_AAC)
#   - a new "Media Info" row under "Queue": hover it to see the title, artist, codecs, resolution...
# Run from inside ~/build/ffmpeg-6.1.1, after patch_shuffle.py.
# Writes the file only if every spot matches exactly once.

import re
import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "queue_reorder" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "queue_shuffle" not in src or "ui_q_open" not in src:
    print("Apply patch_queue_panel.py and patch_shuffle.py first. Nothing written.")
    sys.exit(1)

def patch(pattern, replacement, label, flags=0):
    """Swap pattern (a regex) for replacement, only if it matches exactly once.
    replacement can be a string or a function that takes the match."""
    global src
    repl = replacement if callable(replacement) else (lambda m: replacement)
    new_src, count = re.subn(pattern, repl, src, flags=flags)
    if count != 1:
        print("FAILED:", label, "- matched", count, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = new_src
    print("ok:", label)

# ============================================================ the menu has a sixth row

patch(r"static const char \*ui_menu_label\[5\] = \{[^}]*\};",
      '#define UI_MENU_ITEMS 6         /* rows in the menu */\n\n'
      'static const char *ui_menu_label[UI_MENU_ITEMS] = { "Open File...", "Open Folder...", "Queue",\n'
      '                                                    "Media Info", "Preferences...", "Quit" };',
      "menu rows")

patch(r"for \(i = 0; i < 5; i\+\+\)\s*longest = FFMAX\(longest, ui_text_width\(ui_menu_label\[i\], 22\)\);",
      "for (i = 0; i < UI_MENU_ITEMS; i++)\n        longest = FFMAX(longest, ui_text_width(ui_menu_label[i], 22));",
      "menu width")

patch(r"r\.h = 5 \* UI_MENU_ROW;",
      "r.h = UI_MENU_ITEMS * UI_MENU_ROW;",
      "menu height")

# ============================================================ state

patch(r"static int ui_q_drag_y = 0;[^\n]*\n",
      "static int ui_q_drag_y = 0;     /* mouse height while dragging */\n"
      "static int ui_info_open = 0;    /* 1 while the Media Info panel is showing beside the menu */\n"
      "static VideoState *ui_menu_stream = NULL;   /* the stream the menu is drawn over (NULL = idle screen) */\n",
      "panel state")

patch(r"ui_menu_draw\(\);\s*ui_prefs_draw\(\);",
      "ui_menu_stream = is;\n    ui_menu_draw();\n    ui_prefs_draw();",
      "the menu knows the stream (glass frame)")

patch(r"ui_draw\(is\);\s*ui_menu_draw\(\);",
      "ui_draw(is);\n    ui_menu_stream = is;\n    ui_menu_draw();",
      "the menu knows the stream (plain frame)")

patch(r"if \(is \|\| ui_prefs_open \|\| ui_q_open\)",
      "if (is || ui_prefs_open || ui_q_open || ui_info_open)",
      "blur for the information panel")

patch(r"(ui_idle = 1;\s*ui_menu_open = 0;\s*ui_menu_hover = -1;\s*ui_q_open = 0;)(\s*ui_q_drag = -1;)",
      lambda m: m.group(1) + "\n    ui_info_open = 0;" + m.group(2),
      "the idle screen starts with the panels closed")

# ============================================================ the queue

QUEUE_BLOCK = r'''static unsigned char *q_played = NULL;  /* 1 = this item has played */
static int *q_seq = NULL;               /* number of the item in the order it was added (the original order) */
static int q_seq_next = 0;
static int q_shuffle = 0;               /* 1 = shuffle is on */
static int q_forced = -1;               /* an item the user clicked: it plays next */
static char *q_buried[8];               /* names of removed items that were playing: a stream may still read them */
static int q_buried_next = 0;

static void queue_seed(void)
{
    static int seeded = 0;

    if (!seeded) {
        srand((unsigned)av_gettime());
        seeded = 1;
    }
}

/* Keep the name of an item that was playing alive for a while (the ending stream may still use it) */
static void queue_bury(char *name)
{
    av_free(q_buried[q_buried_next]);
    q_buried[q_buried_next] = name;
    q_buried_next = (q_buried_next + 1) % 8;
}

static void queue_add(const char *path)
{
    char **items = av_realloc_array(q_items, q_count + 1, sizeof(*q_items));
    unsigned char *played, tmp_played;
    int *seq, tmp_seq, lo, j;
    char *name, *tmp_item;

    if (!items)
        return;
    q_items = items;
    played = av_realloc(q_played, q_count + 1);
    if (!played)
        return;
    q_played = played;
    seq = av_realloc_array(q_seq, q_count + 1, sizeof(*q_seq));
    if (!seq)
        return;
    q_seq = seq;
    name = av_strdup(path);
    if (!name)
        return;
    q_items[q_count] = name;
    q_played[q_count] = 0;
    q_seq[q_count] = q_seq_next++;
    q_count++;

    if (q_shuffle && q_count > 1) {     /* shuffle is on: the new item lands among the ones still to play */
        queue_seed();
        lo = FFMAX(q_pos + 1, 0);
        j = lo + rand() % (q_count - lo);
        tmp_item = q_items[j];
        tmp_played = q_played[j];
        tmp_seq = q_seq[j];
        q_items[j] = q_items[q_count - 1];
        q_played[j] = q_played[q_count - 1];
        q_seq[j] = q_seq[q_count - 1];
        q_items[q_count - 1] = tmp_item;
        q_played[q_count - 1] = tmp_played;
        q_seq[q_count - 1] = tmp_seq;
    }
}

/* Empty the queue. The next item played will be the first one added after this. */
static void queue_clear(void)
{
    int i;

    for (i = 0; i < q_count; i++) {
        if (i == q_pos)
            queue_bury(q_items[i]);     /* the stream that is ending may still read its name */
        else
            av_free(q_items[i]);
    }
    q_count = 0;
    q_pos = -1;
    q_step = 1;
    q_forced = -1;
    q_seq_next = 0;
}

/* Which item plays next? q_count means there is none. */
static int queue_next(void)
{
    if (q_forced >= 0 && q_forced < q_count)
        return q_forced;                        /* the user clicked an item */
    return FFMAX(q_pos + q_step, 0);            /* previous on the first item replays it */
}

struct QPair {
    char *item;
    int seq;
};

static int queue_pair_cmp(const void *a, const void *b)
{
    return ((const struct QPair *)a)->seq - ((const struct QPair *)b)->seq;
}

/* Put the items that have not played yet in a new order: shuffle = at random (always different
   from the order before), otherwise the order they were added in (the original order).
   Items before the playing one stay where they are. Items that already played are kept out of the
   reordered part: they sit just above the playing item, so they do not come back. */
static void queue_reorder(int shuffle)
{
    char **items = NULL;
    unsigned char *flags = NULL;
    int *seqs = NULL;
    struct QPair *pairs = NULL, *orig = NULL, t;
    int pos = (q_pos >= 0 && q_pos < q_count) ? q_pos : -1;
    int i, j, n = 0, m = 0, new_pos = -1, tries;

    if (q_count < 2)
        return;
    items = av_malloc_array(q_count, sizeof(*items));
    flags = av_malloc(q_count);
    seqs = av_malloc_array(q_count, sizeof(*seqs));
    pairs = av_malloc_array(q_count, sizeof(*pairs));
    if (!items || !flags || !seqs || !pairs)
        goto end;

    for (i = 0; i < pos; i++) {                 /* before the playing item: unchanged */
        items[n] = q_items[i];
        flags[n] = q_played[i];
        seqs[n++] = q_seq[i];
    }
    for (i = pos + 1; i < q_count; i++) {       /* after it, but already played */
        if (!q_played[i])
            continue;
        items[n] = q_items[i];
        flags[n] = 1;
        seqs[n++] = q_seq[i];
    }
    if (pos >= 0) {                             /* the playing item */
        new_pos = n;
        items[n] = q_items[pos];
        flags[n] = q_played[pos];
        seqs[n++] = q_seq[pos];
    }
    for (i = pos + 1; i < q_count; i++) {       /* the rest: still to play */
        if (q_played[i])
            continue;
        pairs[m].item = q_items[i];
        pairs[m].seq = q_seq[i];
        m++;
    }

    if (shuffle && m >= 3) {
        queue_seed();
        orig = av_malloc_array(m, sizeof(*orig));
        if (orig)
            memcpy(orig, pairs, m * sizeof(*pairs));
        for (tries = 0; tries < 8; tries++) {   /* shuffle until the order really is different */
            for (i = m - 1; i > 0; i--) {
                j = rand() % (i + 1);
                t = pairs[i];
                pairs[i] = pairs[j];
                pairs[j] = t;
            }
            if (!orig || memcmp(orig, pairs, m * sizeof(*pairs)))
                break;
        }
    } else if (shuffle && m == 2) {
        t = pairs[0];                           /* two items: swap them */
        pairs[0] = pairs[1];
        pairs[1] = t;
    } else if (!shuffle && m > 1) {
        qsort(pairs, m, sizeof(*pairs), queue_pair_cmp);
    }
    for (i = 0; i < m; i++) {
        items[n] = pairs[i].item;
        flags[n] = 0;
        seqs[n++] = pairs[i].seq;
    }

    memcpy(q_items, items, n * sizeof(*items));
    memcpy(q_played, flags, n);
    memcpy(q_seq, seqs, n * sizeof(*seqs));
    if (new_pos >= 0)
        q_pos = new_pos;
    q_forced = -1;
end:
    av_free(items);
    av_free(flags);
    av_free(seqs);
    av_free(pairs);
    av_free(orig);
}

/* Turn shuffle on (the queue is shuffled) or off (the original order comes back) */
static void queue_set_shuffle(int on)
{
    q_shuffle = on;
    queue_reorder(on);
}

/* Take an item out of the queue. If it was playing, the next one takes its place. */
static void queue_remove(int idx)
{
    char *gone;
    int i;

    if (idx < 0 || idx >= q_count)
        return;
    gone = q_items[idx];
    for (i = idx; i < q_count - 1; i++) {
        q_items[i] = q_items[i + 1];
        q_played[i] = q_played[i + 1];
        q_seq[i] = q_seq[i + 1];
    }
    q_count--;
    if (idx == q_pos) {
        q_pos--;                                /* the item that followed it is now at idx */
        q_step = 1;
        queue_bury(gone);                       /* the stream that is playing it may still read the name */
    } else {
        if (idx < q_pos)
            q_pos--;
        av_free(gone);
    }
    if (q_forced == idx)
        q_forced = -1;
    else if (q_forced > idx)
        q_forced--;
}

/* Move an item to a new place in the queue. The item that is playing keeps playing. */
static void queue_move(int from, int to)
{
    char *item;
    unsigned char played;
    int seq, i;

    if (from == to || from < 0 || to < 0 || from >= q_count || to >= q_count)
        return;
    item = q_items[from];
    played = q_played[from];
    seq = q_seq[from];
    if (from < to) {
        for (i = from; i < to; i++) {
            q_items[i] = q_items[i + 1];
            q_played[i] = q_played[i + 1];
            q_seq[i] = q_seq[i + 1];
        }
    } else {
        for (i = from; i > to; i--) {
            q_items[i] = q_items[i - 1];
            q_played[i] = q_played[i - 1];
            q_seq[i] = q_seq[i - 1];
        }
    }
    q_items[to] = item;
    q_played[to] = played;
    q_seq[to] = seq;
    if (q_pos == from)
        q_pos = to;
    else if (from < q_pos && q_pos <= to)
        q_pos--;
    else if (to <= q_pos && q_pos < from)
        q_pos++;
    if (!q_shuffle) {                           /* with shuffle off, a hand-made order becomes the original order */
        for (i = 0; i < q_count; i++)
            q_seq[i] = i;
        q_seq_next = q_count;
    }
}
'''

patch(r"static unsigned char \*q_played = NULL;.*?static void queue_move\(int from, int to\)\s*\{.*?\n\}\n",
      QUEUE_BLOCK, "queue: shuffle on/off, remove, original order", re.DOTALL)

# ============================================================ the panels and the menu

PANEL_BLOCK = r'''static void toggle_pause(VideoState *is);

/* ----- the queue panel: opens beside the "Queue" row ----- */
#define UI_Q_W 380              /* panel width */
#define UI_Q_HEAD 52            /* the top row: add, previous, play/pause, next, shuffle */
#define UI_Q_ROW 40             /* one queue item */
#define UI_Q_PAD 10             /* space above and below the rows */

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

/* How many items are shown at once (the panel scrolls beyond that) */
static int ui_q_visible(int wh)
{
    int room = (wh - 16 - 2 * UI_Q_PAD - UI_Q_HEAD) / UI_Q_ROW;

    return av_clip(FFMAX(q_count, 1), 1, av_clip(room, 1, 14));
}

/* Where the panel is: beside the menu, level with the "Queue" row */
static SDL_Rect ui_q_rect(int ww, int wh)
{
    SDL_Rect m = ui_menu_rect(ww, wh), p;
    int gap = ui_idle ? 14 : 22;

    p.w = FFMIN(FFMIN(UI_Q_W, FFMAX(ww / 3, 360)), ww - 16);
    p.h = 2 * UI_Q_PAD + UI_Q_HEAD + ui_q_visible(wh) * UI_Q_ROW;
    if (m.x + m.w + gap + p.w <= ww - 8)
        p.x = m.x + m.w + gap;                  /* to the right of the menu */
    else
        p.x = FFMAX(m.x - gap - p.w, 8);        /* no room there: to the left */
    p.y = av_clip(m.y + 2 * UI_MENU_ROW - UI_Q_PAD, 8, FFMAX(wh - p.h - 8, 8));
    return p;
}

/* The list position where the dragged item would land */
static int ui_q_drop(int wh, const SDL_Rect *p)
{
    int top = p->y + UI_Q_PAD + UI_Q_HEAD;
    int slot = av_clip((ui_q_drag_y - top) / UI_Q_ROW, 0, ui_q_visible(wh) - 1);

    return av_clip(ui_q_scroll + slot, 0, FFMAX(q_count - 1, 0));
}

/* Which item is shown at a list position. While one is dragged, the others make room for it. */
static int ui_q_slot_item(int slot, int drop)
{
    int k;

    if (ui_q_drag < 0)
        return slot;
    if (slot == drop)
        return ui_q_drag;
    k = slot < drop ? slot : slot - 1;          /* position without the dragged item */
    return k < ui_q_drag ? k : k + 1;
}

/* What is at (x, y) in the panel? item = the queue item for ITEM, DOT and DEL. */
static int ui_q_hit(const SDL_Rect *p, int wh, int x, int y, int *item)
{
    int top = p->y + UI_Q_PAD + UI_Q_HEAD, slot, drop = 0, right = p->x + p->w;

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

/* Is this text (the inside of a bracket) only download or codec information, like 1080p_25fps_H264? */
static int ui_q_is_codec_info(const char *s)
{
    int n = 0;

    while (av_isdigit(s[n]))
        n++;
    if (n >= 3 && s[n] == 'p')                  /* 720p, 1080p, 1440p, 2160p ... */
        return 1;
    return n >= 2 && !strncmp(s + n, "kbit", 4);        /* 128kbit ... */
}

/* The name shown for a queue item: the file name without its folder, its extension
   and any trailing "(1080p_25fps_H264-128kbit_AAC)" */
static void ui_q_name(int idx, char *out, size_t size)
{
    const char *s = q_items[idx];
    const char *slash = strrchr(s, '/');
    char *dot, *open;
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
}

/* Cut a text so it fits in max_w pixels, ending with "...". s needs room for 4 more bytes. */
static void ui_fit_text(char *s, int px, int max_w)
{
    char tmp[320];
    int len = (int)strlen(s);
    int w = ui_text_width(s, px);
    int keep;

    if (w <= max_w || len < 2)
        return;
    keep = FFMIN((int)((int64_t)len * max_w / w), len - 1);
    for (; keep > 0; keep--) {
        if ((s[keep] & 0xC0) == 0x80)
            continue;                           /* inside a multi-byte character */
        memcpy(tmp, s, keep);
        memcpy(tmp + keep, "...", 4);
        if (ui_text_width(tmp, px) <= max_w)
            break;
    }
    if (keep > 0)
        memcpy(s, tmp, keep + 4);
    else
        memcpy(s, "...", 4);
}

/* A line about 2 pixels thick */
static void ui_q_line(int x0, int y0, int x1, int y1)
{
    SDL_RenderDrawLine(renderer, x0, y0, x1, y1);
    SDL_RenderDrawLine(renderer, x0 + 1, y0, x1 + 1, y1);
    SDL_RenderDrawLine(renderer, x0, y0 + 1, x1, y1 + 1);
}

/* A smooth curve, drawn as 16 short lines */
static void ui_bezier(double x0, double y0, double x1, double y1, double x2, double y2, double x3, double y3)
{
    double px = x0, py = y0;
    int i;

    for (i = 1; i <= 16; i++) {
        double t = i / 16.0, u = 1.0 - t;
        double x = u * u * u * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t * t * t * x3;
        double y = u * u * u * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t * t * t * y3;

        ui_q_line((int)(px + 0.5), (int)(py + 0.5), (int)(x + 0.5), (int)(y + 0.5));
        px = x;
        py = y;
    }
}

/* A filled triangle with its flat side at x (pointing right, dir = 1) or at x + w (pointing left) */
static void ui_tri(int x, int cy, int w, int h, int dir)
{
    int row;

    for (row = 0; row < h; row++) {
        double d = (row < h / 2.0 ? row + 0.5 : h - row - 0.5) / (h / 2.0);
        int len = (int)(w * d + 0.5);
        SDL_Rect line;

        line.y = cy - h / 2 + row;
        line.h = 1;
        line.w = len;
        line.x = dir > 0 ? x : x + w - len;
        SDL_RenderFillRect(renderer, &line);
    }
}

/* The traditional shuffle icon: two curves that cross, with arrow heads on the right */
static void ui_shuffle_icon(int cx, int cy, int r, int g, int b, int a)
{
    SDL_SetRenderDrawColor(renderer, r, g, b, a);
    ui_bezier(cx - 11, cy - 5, cx + 1, cy - 5, cx - 1, cy + 5, cx + 8, cy + 5);
    ui_bezier(cx - 11, cy + 5, cx + 1, cy + 5, cx - 1, cy - 5, cx + 8, cy - 5);
    ui_tri(cx + 6, cy + 5, 8, 9, 1);
    ui_tri(cx + 6, cy - 5, 8, 9, 1);
}

/* Previous (0), play (1), pause (2) and next (3) */
static void ui_transport_icon(int which, int cx, int cy, int a)
{
    SDL_Rect bar;

    SDL_SetRenderDrawColor(renderer, 230, 230, 230, a);
    if (which == 0) {
        ui_tri(cx - 11, cy, 10, 14, -1);
        ui_tri(cx - 1, cy, 10, 14, -1);
    } else if (which == 3) {
        ui_tri(cx - 9, cy, 10, 14, 1);
        ui_tri(cx + 1, cy, 10, 14, 1);
    } else if (which == 1) {
        ui_tri(cx - 5, cy, 12, 14, 1);
    } else {
        bar.y = cy - 7;
        bar.w = 4;
        bar.h = 14;
        bar.x = cx - 6;
        SDL_RenderFillRect(renderer, &bar);
        bar.x = cx + 2;
        SDL_RenderFillRect(renderer, &bar);
    }
}

/* The arrow at the end of a menu row that opens a panel */
static void ui_chevron(int x, int cy, int a)
{
    SDL_SetRenderDrawColor(renderer, 230, 230, 230, a);
    ui_q_line(x, cy - 6, x + 6, cy);
    ui_q_line(x + 6, cy, x, cy + 6);
}

static int ui_q_hover_kind = UI_Q_NONE;     /* what the mouse is over in the panel */
static int ui_q_hover_idx = -1;             /* ... and which item */

static void ui_q_draw(int ww, int wh)
{
    SDL_Rect p = ui_q_rect(ww, wh), sep, dot;
    char name[300];
    int vis = ui_q_visible(wh);
    int top = p.y + UI_Q_PAD + UI_Q_HEAD;
    int right = p.x + p.w;
    int max_w = p.w - 20 - 94;
    int drop = 0, i, item, cy, lit, hk = ui_q_hover_kind;
    int paused = ui_menu_stream && ui_menu_stream->paused;

    ui_q_scroll = av_clip(ui_q_scroll, 0, FFMAX(q_count - vis, 0));
    if (ui_q_drag >= 0)
        drop = ui_q_drop(wh, &p);
    ui_glass(&p, 20);
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
        ui_q_name(item, name, 290);
        ui_fit_text(name, 18, max_w);
        lit = ui_q_drag < 0 && item == ui_q_hover_idx &&
              (hk == UI_Q_ITEM || hk == UI_Q_DOT || hk == UI_Q_DEL);
        if (item == q_pos || item == ui_q_drag)
            ui_label(p.x + 20, cy, name, 18, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                     av_clip(cfg_bar_b + 40, 0, 255), 255);
        else
            ui_label(p.x + 20, cy, name, 18, 240, 240, 240, lit ? 255 : 205);

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
}

/* ----- the Media Info panel: opens beside the "Media Info" row ----- */
#define UI_I_ROW 30             /* height of one line */
#define UI_I_PAD 14             /* space above and below the lines */
#define UI_INFO_MAX 24
static char ui_il_label[UI_INFO_MAX][16];
static char ui_il_value[UI_INFO_MAX][200];

static void ui_info_put(int *n, const char *label, const char *value)
{
    if (*n >= UI_INFO_MAX || !value || !*value)
        return;
    snprintf(ui_il_label[*n], sizeof(ui_il_label[0]), "%s", label);
    snprintf(ui_il_value[*n], sizeof(ui_il_value[0]), "%s", value);
    (*n)++;
}

/* A codec name with its profile, like "aac (LC)" */
static void ui_info_codec(char *out, size_t size, enum AVCodecID id, int profile)
{
    const char *prof = avcodec_profile_name(id, profile);

    if (prof)
        snprintf(out, size, "%s (%s)", avcodec_get_name(id), prof);
    else
        snprintf(out, size, "%s", avcodec_get_name(id));
}

/* Collect what is known about the file that is playing. Returns the number of lines. */
static int ui_info_collect(VideoState *is)
{
    static const char *const tags[5][2] = {
        { "title", "Title" }, { "artist", "Artist" }, { "album", "Album" },
        { "date", "Date" }, { "genre", "Genre" }
    };
    AVFormatContext *ic;
    AVDictionaryEntry *e;
    AVCodecParameters *par;
    AVRational fr;
    const char *pf;
    char v[200];
    int n = 0, i;
    int64_t s;

    if (!is || !(ic = is->ic))
        return 0;
    for (i = 0; i < 5; i++) {
        e = av_dict_get(ic->metadata, tags[i][0], NULL, 0);
        if (e)
            ui_info_put(&n, tags[i][1], e->value);
    }
    if (ic->iformat && ic->iformat->long_name)
        ui_info_put(&n, "Format", ic->iformat->long_name);
    if (ic->duration > 0) {
        s = ic->duration / AV_TIME_BASE;
        if (s >= 3600)
            snprintf(v, sizeof(v), "%d:%02d:%02d", (int)(s / 3600), (int)(s / 60 % 60), (int)(s % 60));
        else
            snprintf(v, sizeof(v), "%d:%02d", (int)(s / 60), (int)(s % 60));
        ui_info_put(&n, "Duration", v);
    }
    if (ic->bit_rate > 0) {
        snprintf(v, sizeof(v), "%d kb/s", (int)(ic->bit_rate / 1000));
        ui_info_put(&n, "Bit rate", v);
    }
    if (is->video_st && is->video_st->codecpar) {
        par = is->video_st->codecpar;
        ui_info_codec(v, sizeof(v), par->codec_id, par->profile);
        ui_info_put(&n, "Video", v);
        if (par->width > 0 && par->height > 0) {
            snprintf(v, sizeof(v), "%dx%d", par->width, par->height);
            ui_info_put(&n, "Resolution", v);
        }
        fr = av_guess_frame_rate(ic, is->video_st, NULL);
        if (fr.num > 0 && fr.den > 0) {
            snprintf(v, sizeof(v), "%.3g fps", av_q2d(fr));
            ui_info_put(&n, "Frame rate", v);
        }
        pf = par->format >= 0 ? av_get_pix_fmt_name((enum AVPixelFormat)par->format) : NULL;
        if (pf)
            ui_info_put(&n, "Pixel format", pf);
        if (par->bit_rate > 0) {
            snprintf(v, sizeof(v), "%d kb/s", (int)(par->bit_rate / 1000));
            ui_info_put(&n, "Video rate", v);
        }
    }
    if (is->audio_st && is->audio_st->codecpar) {
        par = is->audio_st->codecpar;
        ui_info_codec(v, sizeof(v), par->codec_id, par->profile);
        ui_info_put(&n, "Audio", v);
        if (par->sample_rate > 0) {
            snprintf(v, sizeof(v), "%d Hz", par->sample_rate);
            ui_info_put(&n, "Sample rate", v);
        }
        if (par->ch_layout.nb_channels > 0) {
            if (av_channel_layout_describe(&par->ch_layout, v, sizeof(v)) < 0)
                snprintf(v, sizeof(v), "%d", par->ch_layout.nb_channels);
            ui_info_put(&n, "Channels", v);
        }
        if (par->bit_rate > 0) {
            snprintf(v, sizeof(v), "%d kb/s", (int)(par->bit_rate / 1000));
            ui_info_put(&n, "Audio rate", v);
        }
    }
    return n;
}

static SDL_Rect ui_info_rect(int ww, int wh, int lines)
{
    SDL_Rect m = ui_menu_rect(ww, wh), p;
    int gap = ui_idle ? 14 : 22;
    int rows = av_clip(lines, 1, FFMAX((wh - 16 - 2 * UI_I_PAD) / UI_I_ROW, 1));

    p.w = FFMIN(FFMIN(480, FFMAX(ww / 3, 380)), ww - 16);
    p.h = 2 * UI_I_PAD + rows * UI_I_ROW;
    if (m.x + m.w + gap + p.w <= ww - 8)
        p.x = m.x + m.w + gap;
    else
        p.x = FFMAX(m.x - gap - p.w, 8);
    p.y = av_clip(m.y + 3 * UI_MENU_ROW - UI_I_PAD, 8, FFMAX(wh - p.h - 8, 8));
    return p;
}

static void ui_info_draw(int ww, int wh)
{
    int n = ui_info_collect(ui_menu_stream);
    SDL_Rect p = ui_info_rect(ww, wh, n);
    char val[220];
    int rows = (p.h - 2 * UI_I_PAD) / UI_I_ROW, i, cy;

    ui_glass(&p, 20);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    if (n == 0) {
        ui_label(p.x + 20, p.y + UI_I_PAD + UI_I_ROW / 2,
                 ui_menu_stream ? "No information in this file" : "Nothing is playing",
                 18, 220, 220, 220, 160);
        return;
    }
    for (i = 0; i < n && i < rows; i++) {
        cy = p.y + UI_I_PAD + i * UI_I_ROW + UI_I_ROW / 2;
        ui_label(p.x + 20, cy, ui_il_label[i], 16, 190, 190, 190, 200);
        snprintf(val, sizeof(val), "%s", ui_il_value[i]);
        ui_fit_text(val, 18, p.w - 20 - 112 - 20);
        ui_label(p.x + 20 + 112, cy, val, 18, 240, 240, 240, 255);
    }
}

static void ui_menu_draw(void)
{
    SDL_Rect r, card, row;
    int ww, wh, i, pad, cy, lit;

    if (ui_prefs_open || (!ui_idle && !ui_menu_open))
        return;
    SDL_GetWindowSize(window, &ww, &wh);
    r = ui_menu_rect(ww, wh);

    /* The popup gets a glass card around its rows. The idle screen has no card at all. */
    if (!ui_idle) {
        pad = 8;
        card.x = r.x - pad;
        card.y = r.y - pad;
        card.w = r.w + 2 * pad;
        card.h = r.h + 2 * pad;
        ui_glass(&card, 16);
    }

    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    for (i = 0; i < UI_MENU_ITEMS; i++) {
        row.x = r.x;
        row.y = r.y + i * UI_MENU_ROW;
        row.w = r.w;
        row.h = UI_MENU_ROW;
        cy = row.y + row.h / 2;
        lit = i == ui_menu_hover || (i == 2 && ui_q_open) || (i == 3 && ui_info_open);
        ui_label(row.x + 28, cy, ui_menu_label[i], 22, 240, 240, 240, lit ? 255 : 205);
        if (i == 2 || i == 3)
            ui_chevron(row.x + r.w - 22, cy, lit ? 255 : 170);
    }
    if (ui_idle) {
        int ls, gap;

        ui_logo_metrics(ww, wh, &ls, &gap);
        ui_logo_draw(r.x - gap - ls / 2, wh / 2, ls);
    }
    if (ui_q_open)
        ui_q_draw(ww, wh);
    else if (ui_info_open)
        ui_info_draw(ww, wh);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);
}
'''

patch(r"/\* ----- the queue panel: opens beside the \"Queue\" row ----- \*/.*?"
      r"static void ui_menu_draw\(void\)\s*\{.*?\n\}\n",
      PANEL_BLOCK, "queue panel, Media Info panel and menu drawing", re.DOTALL)

MOUSE_BLOCK = r'''/* End the file that is playing. The main loop then goes on with whatever queue_next() says. */
static void ui_end_current(VideoState *is)
{
    SDL_Event e;

    if (!is)
        return;
    SDL_zero(e);
    e.type = FF_QUIT_EVENT;
    e.user.data1 = is;
    SDL_PushEvent(&e);
}

/* Do what a menu row says */
static void ui_menu_action(VideoState *is, int item)
{
    if (item == 2) {                /* Queue: show the queue panel */
        ui_q_open = 1;
        ui_info_open = 0;
        return;
    }
    if (item == 3) {                /* Media Info: show the information panel */
        ui_info_open = 1;
        ui_q_open = 0;
        return;
    }
    ui_menu_open = 0;
    ui_menu_hover = -1;
    ui_q_open = 0;
    ui_info_open = 0;
    if (item <= 1) {
        ui_pick_start(item);        /* Open File, Open Folder */
    } else if (item == 4) {
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
            ui_menu_hover = 2;      /* the "Queue" row stays lit while the mouse is in the panel */
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
        else if (q_count > 0)
            q_forced = 0;           /* the idle screen: play the queue from the top */
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
    } else {                        /* an item: play it now */
        q_forced = item;
        ui_menu_open = 0;
        ui_q_open = 0;
        ui_menu_hover = -1;
        ui_end_current(is);
    }
    return 1;
}

/* Mouse events for the menu. Returns 1 if the menu used the event.
   is = the stream playing now, or NULL on the idle screen. */
static int ui_menu_mouse(VideoState *is, SDL_Event *ev)
{
    SDL_Rect r, p, ip;
    int ww, wh, x, y, row;

    if (ui_prefs_open)
        return ui_prefs_mouse(is, ev);

    if (ev->type == SDL_MOUSEBUTTONDOWN && ev->button.button == SDL_BUTTON_RIGHT && !ui_idle) {
        /* right-click on the video: open the menu at the mouse */
        ui_menu_open = 1;
        ui_menu_x = ev->button.x;
        ui_menu_y = ev->button.y;
        ui_menu_hover = -1;
        ui_q_open = 0;
        ui_info_open = 0;
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
        }
        if (is)
            is->force_refresh = 1;
        return 1;
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
                ui_menu_hover = 3;
            if (is)
                is->force_refresh = 1;
            return 1;
        }
    }

    if (ev->type == SDL_MOUSEMOTION) {
        ui_menu_hover = row;
        if (row == 2) {
            ui_q_open = 1;          /* hovering "Queue" opens the queue panel */
            ui_info_open = 0;
        } else if (row == 3) {
            ui_info_open = 1;       /* hovering "Media Info" opens the information panel */
            ui_q_open = 0;
        } else {
            if (ui_q_open) {
                p = ui_q_rect(ww, wh);
                if (!ui_q_keep(&r, &p, x, y, 2))
                    ui_q_open = 0;
            }
            if (ui_info_open) {
                ip = ui_info_rect(ww, wh, ui_info_collect(is));
                if (!ui_q_keep(&r, &ip, x, y, 3))
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
        } else {
            return 0;               /* idle screen: clicking elsewhere moves the window */
        }
        if (is)
            is->force_refresh = 1;
        return 1;
    }
    return 0;
}

/* The mouse button was released: drop the dragged queue item. Returns 1 if there was a drag. */
static int ui_queue_release(SDL_Event *ev)
{
    SDL_Rect p;
    int ww, wh;

    if (ui_q_drag < 0 || ev->button.button != SDL_BUTTON_LEFT)
        return 0;
    SDL_GetWindowSize(window, &ww, &wh);
    p = ui_q_rect(ww, wh);
    ui_q_drag_y = ev->button.y;
    queue_move(ui_q_drag, ui_q_drop(wh, &p));
    ui_q_drag = -1;
    return 1;
}

/* Mouse wheel: scroll the queue panel. Returns 1 if the panel used it. */
static int ui_queue_wheel(SDL_Event *ev)
{
    int ww, wh;

    if (!ui_q_open || (!ui_idle && !ui_menu_open) || ui_prefs_open || !ev->wheel.y)
        return 0;
    SDL_GetWindowSize(window, &ww, &wh);
    ui_q_scroll = av_clip(ui_q_scroll - ev->wheel.y, 0, FFMAX(q_count - ui_q_visible(wh), 0));
    return 1;
}
'''

patch(r"/\* Do what a menu row says \*/.*?static int ui_queue_wheel\(SDL_Event \*ev\)\s*\{.*?\n\}\n",
      MOUSE_BLOCK, "menu clicks and panel mouse", re.DOTALL)

# Everything matched, so it's safe to write
open(path, "w").write(src)
print("Patched", path)
