#!/usr/bin/env python3
"""patch_queue_v51.py - file picker, round 3 (on top of v50).

  - Thumbnails in the grid view: a video shows a picture from about a tenth of the way in, a song shows its cover (if it has one), and a
    FOLDER shows a picture of something inside it (the first video, else the first song with a cover, one folder deeper if it has none).
    They are made by a thread, only for the tiles in view, and kept in memory. Ctrl+T turns them off and on (picker_thumbs in settings.conf).
  - The tree opens itself down to the open folder
  - Recent places: the folders something was played or added from, under Recent in the tree (recent_places.txt)
  - Ctrl+L, or a click on the empty part of the path: type a path (Tab finishes a folder name, Enter goes there)
  - Drives that are mounted get an eject mark in the tree: a click unmounts them

Run it from ~/build/ffmpeg-6.1.1:   python3 ~/build/patch_queue_v51.py [path/to/ffplay.c]
Nothing is written unless every edit matches.
"""
import os
import sys

if len(sys.argv) > 1:
    path = sys.argv[1]
elif os.path.isfile("fftools/ffplay.c"):
    path = "fftools/ffplay.c"
else:
    path = os.path.expanduser("~/build/ffmpeg-6.1.1/fftools/ffplay.c")
if not os.path.isfile(path):
    print("FAILED: cannot find " + path)
    sys.exit(1)
src = open(path, encoding="utf-8").read()
if "ui_pk_thumb_flush" in src:
    print("Already applied: v51 is in " + path)
    sys.exit(0)
if "ui_pk_search_start" not in src:
    print("FAILED: apply patch_queue_v50.py first. Nothing written.")
    sys.exit(1)


def fail(msg):
    print("FAILED: " + msg)
    sys.exit(1)


def replace(s, old, new, what):
    n = s.count(old)
    if n != 1:
        fail("%s: expected 1 match, found %d" % (what, n))
    return s.replace(old, new)


PICKER = r'''/* ================================================================================================================================
   v44: our own file picker, for Open File, Open Folder and Add to Queue. It is drawn like the Preferences panel (frosted glass over
   the blurred player) and sends what is chosen to the inbox, like the system dialog did. It needs no other program.
   v49: reworked. One top bar (back, forward, up, "Open Media", the path, Sort, list or grid, search, close), a folder tree on the left
   with drop downs, drives that are not mounted yet (click to mount), search just by typing (in this folder, below it, above it,
   elsewhere), a dynamic "Modified" column, item counts and sizes at the bottom, and buttons that follow what is selected.
     Mouse: a click selects a row, a double click opens it (a folder is entered, a file is played); in Add to Queue a click on a file
            ticks it; the tree, the path and the arrows move around; the wheel scrolls; a click outside closes it.
            The back and forward buttons of a mouse go back and forward.
     Keys:  type to search, Up/Down/PageUp/PageDown/Home/End (and Left/Right in the grid), Enter (opens the row, or adds what is ticked),
            Right enters a folder, Left or Backspace (with nothing typed) goes up, Alt+Left/Right back and forward, Alt+Up up, Space ticks,
            Ctrl+A ticks all, Ctrl+1 list, Ctrl+2 grid, Ctrl+F search box, Ctrl+L type a path (Tab finishes a folder name), Ctrl+T thumbnails on or off, Tab shows all files, Ctrl+H shows hidden ones, F5 reads again,
            Esc clears the search, then closes the search box, then closes the picker.
   ================================================================================================================================ */
#ifndef DT_DIR                                  /* d_type values (Linux), for a C mode that hides the names */
#define DT_UNKNOWN 0
#define DT_DIR 4
#define DT_REG 8
#define DT_LNK 10
#endif
#define UI_PK_CLOCK24 0                         /* 1 = clock times like 17:05, 0 = like 5:05 pm */
#define UI_PK_ROW   34
#define UI_PK_TOP   56
#define UI_PK_FOOT  60
#define UI_PK_SIDE  224
#define UI_PK_SBOX  50
#define UI_PK_HDR   34
#define UI_PK_TILE_W 136
#define UI_PK_TILE_H 128
#define UI_PK_TROW  30
#define UI_PK_MAXX  700

typedef struct {
    char *name;
    char *where;                                /* the folder it is in; NULL = the open folder */
    int dir, sel, count, sect;                  /* count: items in a folder (-1 = not counted yet); sect: 0 here, 1 below, 2 above, 3 elsewhere */
    int64_t size;
    time_t mtime;
} UiPkEnt;

typedef struct {
    int kind, idx;                              /* kind 0 = ui_pk_e[idx], 1 = ui_pk_x[idx], 2 = the header of section idx */
    SDL_Rect r;                                 /* where it is in the list (the list's own coordinates, before scrolling) */
} UiPkRow;

typedef struct {
    char *name, *path, *dev;                    /* dev: the block device of a drive (NULL for a folder) */
    int depth, open, kids, grp, kind;           /* kids: -1 = not looked at yet; grp: 0 places, 1 drives; kind: 0 folder, 1 drive not mounted, 2 heading */
} UiPkNode;

typedef struct {
    char dev[48], label[64], size[16], mnt[PATH_MAX];
} UiPkDev;

typedef struct {
    SDL_Rect p, top, side, list, sbox, crumbs, ok, extra, all, hid, back, fwd, upb, sortb, gridb, srchb, closeb;
    int side_on, tog, title_on, sbox_on, sort_on;
} UiPkLay;

static UiPkEnt *ui_pk_e = NULL;                 /* what is in the open folder */
static int ui_pk_n = 0, ui_pk_cap = 0;
static UiPkEnt *ui_pk_x = NULL;                 /* search results from other folders (below, above, elsewhere) */
static int ui_pk_nx = 0, ui_pk_xcap = 0;
static UiPkRow *ui_pk_rw = NULL;                /* the rows of the list: headers and the entries that pass the search */
static int ui_pk_nrw = 0, ui_pk_crw = 0, ui_pk_content_h = 0, ui_pk_lay_key = -1, ui_pk_rows_ver = 0, ui_pk_cols = 1;
static char ui_pk_dir[PATH_MAX], ui_pk_last[PATH_MAX], ui_pk_filter[128];
static int ui_pk_mode = 0;                      /* 0 = Open File, 1 = Open Folder, 2 = Add to Queue */
static int ui_pk_cur = 0, ui_pk_touched = 0;    /* the row with the cursor; touched = the person has chosen it (not just the first row) */
static int ui_pk_all = 0, ui_pk_hidden = 0;     /* show all files, show hidden ones */
static int ui_pk_grid = 0, ui_pk_search_on = 0; /* v49: the grid view; the search box is showing */
static int ui_pk_hrow = -1, ui_pk_hnode = -1, ui_pk_hbtn = -1;      /* under the mouse */
static double ui_pk_sc = 0.0;                   /* scrolled, in pixels */
static double ui_pk_goal = -1.0;                /* v48: where the wheel is taking the list (the list glides there); -1 = nowhere */
static double ui_pk_ssc = 0.0;                  /* the folder tree, scrolled */
static struct { SDL_Rect r; int upto; } ui_pk_crumb[24];
static int ui_pk_ncrumb = 0;
static int64_t ui_pk_click_t = 0, ui_pk_nav_t = 0;      /* nav_t: when a folder was last read (a click just after it is the second of a double click) */
static int ui_pk_click_row = -2;
static int ui_pk_sortk = 0, ui_pk_desc = 0;     /* sorted by 0 name, 1 modified, 2 size; desc = the other way round */
static char ui_pk_note[200];                    /* what was just done, shown in the foot for a moment */
static int64_t ui_pk_note_until = 0;
static int ui_pk_cm_open = 0;                   /* the menu of a row or of Sort (below) */
static int ui_pk_reveal = 0;
static int ui_pk_loc_on = 0, ui_pk_loc_fresh = 0;  /* fresh: the path shown has not been touched yet, so typing replaces it */                    /* v51: the path is being typed (Ctrl+L) */
static char ui_pk_loc[PATH_MAX];
static int ui_pk_tree_show = -1;                /* v51: the tree node to scroll into view at the next drawing */                    /* 1 = scroll the cursor into view at the next drawing (the rows have no places yet) */

static void ui_pk_close(VideoState *is);

static int ui_pk_has_ext(const char *name)
{
    const char *dot = strrchr(name, '.');
    int kind, k;

    if (!dot || !dot[1])
        return 0;
    for (kind = 0; kind < 2; kind++)
        for (k = 0; ui_tv_ext[kind][k]; k++)
            if (!av_strcasecmp(dot + 1, ui_tv_ext[kind][k]))
                return 1;
    return 0;
}

/* ----- the "Modified" column, told the way Files tells it (v49): Just now, 3 minutes ago, 2 hours ago, Today at 12:17 pm, Yesterday at
   4:19 pm, Monday at 8:00 pm (2 to 6 days ago), 1 week ago (7 to 13 days), else Nov 12, 2026. A time in the future is shown as a date.
   Days are calendar days, not blocks of 24 hours. ----- */
static void ui_pk_when(time_t t, time_t now, char *out, size_t n)
{
    struct tm tm, tn, a, b;
    char clk[24];
    long age = (long)(now - t), dd;
    int h;

    localtime_r(&t, &tm);
    localtime_r(&now, &tn);
    a = tm;
    b = tn;
    a.tm_hour = b.tm_hour = 12;
    a.tm_min = b.tm_min = a.tm_sec = b.tm_sec = 0;
    a.tm_isdst = b.tm_isdst = -1;
    dd = (long)lround(difftime(mktime(&b), mktime(&a)) / 86400.0);
    h = tm.tm_hour % 12;
#if UI_PK_CLOCK24
    snprintf(clk, sizeof(clk), "%d:%02d", tm.tm_hour, tm.tm_min);
#else
    snprintf(clk, sizeof(clk), "%d:%02d %s", h ? h : 12, tm.tm_min, tm.tm_hour < 12 ? "am" : "pm");
#endif
    if (age < -60 || dd < 0 || dd >= 14) {
        strftime(out, n, "%b %-d, %Y", &tm);
    } else if (age < 60) {
        snprintf(out, n, "Just now");
    } else if (age < 3600) {
        snprintf(out, n, "%ld minute%s ago", age / 60, age / 60 == 1 ? "" : "s");
    } else if (age < 6 * 3600) {
        snprintf(out, n, "%ld hour%s ago", age / 3600, age / 3600 == 1 ? "" : "s");
    } else if (dd == 0) {
        snprintf(out, n, "Today at %s", clk);
    } else if (dd == 1) {
        snprintf(out, n, "Yesterday at %s", clk);
    } else if (dd < 7) {
        char wd[32];

        strftime(wd, sizeof(wd), "%A", &tm);
        snprintf(out, n, "%s at %s", wd, clk);
    } else {
        snprintf(out, n, "1 week ago");
    }
}

static void ui_pk_size_str(int64_t n, char *out, size_t size)
{
    double sz = (double)n;

    if (sz < 1000.0)
        snprintf(out, size, "%d bytes", (int)sz);
    else if (sz < 1e6)
        snprintf(out, size, "%.1f kB", sz / 1e3);
    else if (sz < 1e9)
        snprintf(out, size, "%.1f MB", sz / 1e6);
    else
        snprintf(out, size, "%.1f GB", sz / 1e9);
}

/* How many items a folder holds, counted by the same rules as the list (hidden ones and, unless All files is on, files that are not
   music or videos are left out). Folders are items too. */
static int ui_pk_count_dir(const char *dir)
{
    DIR *d = opendir(dir);
    struct dirent *de;
    char full[PATH_MAX + 300];
    int n = 0;

    if (!d)
        return 0;
    while ((de = readdir(d))) {
        int isdir, isreg;

        if (de->d_name[0] == '.' && (!de->d_name[1] || (de->d_name[1] == '.' && !de->d_name[2])))
            continue;
        if (de->d_name[0] == '.' && !ui_pk_hidden)
            continue;
        if (de->d_type == DT_DIR) {
            isdir = 1;
            isreg = 0;
        } else if (de->d_type == DT_REG) {
            isdir = 0;
            isreg = 1;
        } else {
            struct stat st;

            snprintf(full, sizeof(full), "%s/%s", dir, de->d_name);
            if (stat(full, &st) != 0)
                continue;
            isdir = S_ISDIR(st.st_mode);
            isreg = S_ISREG(st.st_mode);
        }
        if (!isdir && !isreg)
            continue;
        if (!isdir && (ui_pk_mode == 1 || (!ui_pk_all && !ui_pk_has_ext(de->d_name))))
            continue;
        n++;
    }
    closedir(d);
    return n;
}

static void ui_pk_path_of(const UiPkEnt *e, char *out, size_t size)
{
    const char *d = e->where ? e->where : ui_pk_dir;

    snprintf(out, size, "%s%s%s", d, !strcmp(d, "/") ? "" : "/", e->name);
}

static void ui_pk_free_ents(UiPkEnt *a, int n)
{
    int i;

    for (i = 0; i < n; i++) {
        free(a[i].name);
        free(a[i].where);
    }
}

static UiPkEnt *ui_pk_push(UiPkEnt **arr, int *n, int *cap)
{
    if (*n >= *cap) {
        int nc = *cap ? *cap * 2 : 256;
        UiPkEnt *ne = realloc(*arr, nc * sizeof(**arr));

        if (!ne)
            return NULL;
        *arr = ne;
        *cap = nc;
    }
    memset(&(*arr)[*n], 0, sizeof(**arr));
    return &(*arr)[(*n)++];
}

static UiPkEnt *ui_pk_ent(int row)
{
    UiPkRow *w;

    if (row < 0 || row >= ui_pk_nrw)
        return NULL;
    w = &ui_pk_rw[row];
    if (w->kind == 0 && w->idx >= 0 && w->idx < ui_pk_n)
        return &ui_pk_e[w->idx];
    if (w->kind == 1 && w->idx >= 0 && w->idx < ui_pk_nx)
        return &ui_pk_x[w->idx];
    return NULL;
}

static UiPkEnt *ui_pk_cur_ent(void)
{
    return ui_pk_ent(ui_pk_cur);
}

static int ui_pk_cmp(const void *a, const void *b)
{
    const UiPkEnt *x = a, *y = b;
    int c = 0;

    if (x->sect != y->sect)
        return x->sect - y->sect;
    if (x->dir != y->dir)
        return y->dir - x->dir;                 /* the folders first */
    if (ui_pk_sortk == 1 && x->mtime != y->mtime)
        c = x->mtime < y->mtime ? -1 : 1;
    else if (ui_pk_sortk == 2 && !x->dir && x->size != y->size)
        c = x->size < y->size ? -1 : 1;
    if (c)
        return ui_pk_desc ? -c : c;
    c = av_strcasecmp(x->name, y->name);
    if (!c)
        c = strcmp(x->where ? x->where : "", y->where ? y->where : "");
    return ui_pk_sortk == 0 && ui_pk_desc ? -c : c;
}

static int ui_pk_first_entry(void)
{
    int i;

    for (i = 0; i < ui_pk_nrw; i++)
        if (ui_pk_rw[i].kind != 2)
            return i;
    return 0;
}

static void ui_pk_row_add(int kind, int idx)
{
    if (ui_pk_nrw >= ui_pk_crw) {
        int nc = ui_pk_crw ? ui_pk_crw * 2 : 512;
        UiPkRow *nr = realloc(ui_pk_rw, nc * sizeof(*nr));

        if (!nr)
            return;
        ui_pk_rw = nr;
        ui_pk_crw = nc;
    }
    ui_pk_rw[ui_pk_nrw].kind = kind;
    ui_pk_rw[ui_pk_nrw].idx = idx;
    memset(&ui_pk_rw[ui_pk_nrw].r, 0, sizeof(SDL_Rect));
    ui_pk_nrw++;
}

static const char * const ui_pk_sect_name[4] = { "In this folder", "Below this folder", "Above this folder", "Elsewhere" };

/* The rows: what is typed picks the entries (anywhere in the name); while something is typed they come in sections. The cursor stays on
   the entry it was on, if that is still there. */
static void ui_pk_rebuild(void)
{
    char keep[PATH_MAX + 300];
    UiPkEnt *ce = ui_pk_touched ? ui_pk_cur_ent() : NULL;
    int keep_sect = -1, i, s, c[4] = { 0, 0, 0, 0 }, searching = ui_pk_filter[0] != 0;

    keep[0] = 0;
    if (ce) {
        ui_pk_path_of(ce, keep, sizeof(keep));
        keep_sect = ce->sect;
    }
    ui_pk_nrw = 0;
    for (i = 0; i < ui_pk_n; i++)
        if (!searching || av_stristr(ui_pk_e[i].name, ui_pk_filter))
            c[0]++;
    for (i = 0; i < ui_pk_nx; i++)
        if (ui_pk_x[i].sect >= 1 && ui_pk_x[i].sect <= 3)
            c[ui_pk_x[i].sect]++;
    for (s = 0; s < 4; s++) {
        if (searching && !c[s])
            continue;
        if (searching)
            ui_pk_row_add(2, s);
        if (s == 0) {
            for (i = 0; i < ui_pk_n; i++)
                if (!searching || av_stristr(ui_pk_e[i].name, ui_pk_filter))
                    ui_pk_row_add(0, i);
        } else {
            for (i = 0; i < ui_pk_nx; i++)
                if (ui_pk_x[i].sect == s)
                    ui_pk_row_add(1, i);
        }
    }
    ui_pk_rows_ver++;
    ui_pk_cur = ui_pk_first_entry();
    if (keep[0]) {
        for (i = 0; i < ui_pk_nrw; i++) {
            UiPkEnt *e = ui_pk_ent(i);
            char p[PATH_MAX + 300];

            if (!e || e->sect != keep_sect)
                continue;
            ui_pk_path_of(e, p, sizeof(p));
            if (!strcmp(p, keep)) {
                ui_pk_cur = i;
                return;
            }
        }
        ui_pk_touched = 0;
    }
}

/* Where every row goes: one under the other in the list view, in lines of tiles in the grid view */
static void ui_pk_relayout(const UiPkLay *L)
{
    int key = L->list.w * 4 + ui_pk_grid * 2 + 1, i, y, c = 0, cw = L->list.w;

    key = key * 7919 + ui_pk_rows_ver;
    if (key == ui_pk_lay_key)
        return;
    ui_pk_lay_key = key;
    ui_pk_cols = 1;
    if (ui_pk_grid) {
        ui_pk_cols = FFMAX((L->list.w - 24) / UI_PK_TILE_W, 1);
        cw = (L->list.w - 24) / ui_pk_cols;
    }
    y = 6;
    for (i = 0; i < ui_pk_nrw; i++) {
        UiPkRow *w = &ui_pk_rw[i];

        if (w->kind == 2) {
            if (ui_pk_grid && c > 0) {
                y += UI_PK_TILE_H;
                c = 0;
            }
            w->r.x = 0;
            w->r.y = y;
            w->r.w = L->list.w;
            w->r.h = UI_PK_HDR;
            y += UI_PK_HDR;
        } else if (ui_pk_grid) {
            w->r.x = 12 + c * cw;
            w->r.y = y;
            w->r.w = cw;
            w->r.h = UI_PK_TILE_H;
            if (++c >= ui_pk_cols) {
                c = 0;
                y += UI_PK_TILE_H;
            }
        } else {
            w->r.x = 0;
            w->r.y = y;
            w->r.w = L->list.w;
            w->r.h = UI_PK_ROW;
            y += UI_PK_ROW;
        }
    }
    if (ui_pk_grid && c > 0)
        y += UI_PK_TILE_H;
    ui_pk_content_h = y + 6;
}

/* The row at a point of the window (an entry or a header), or -1 */
static int ui_pk_row_at(const UiPkLay *L, int mx, int my)
{
    int cx = mx - L->list.x, cy = my - L->list.y + (int)ui_pk_sc, lo = 0, hi = ui_pk_nrw, j;

    if (mx < L->list.x || mx >= L->list.x + L->list.w || my < L->list.y || my >= L->list.y + L->list.h)
        return -1;
    while (lo < hi) {                           /* the first row that ends below the point */
        int mid = (lo + hi) / 2;

        if (ui_pk_rw[mid].r.y + ui_pk_rw[mid].r.h > cy)
            hi = mid;
        else
            lo = mid + 1;
    }
    for (j = lo; j < ui_pk_nrw && ui_pk_rw[j].r.y <= cy; j++)
        if (cx >= ui_pk_rw[j].r.x && cx < ui_pk_rw[j].r.x + ui_pk_rw[j].r.w && cy < ui_pk_rw[j].r.y + ui_pk_rw[j].r.h)
            return j;
    return -1;
}

static double ui_pk_maxsc(const UiPkLay *L)
{
    return FFMAX(0.0, (double)ui_pk_content_h - L->list.h);
}

static void ui_pk_clamp_scroll(const UiPkLay *L)
{
    ui_pk_sc = av_clipd(ui_pk_sc, 0.0, ui_pk_maxsc(L));
}

static void ui_pk_show_cursor(const UiPkLay *L)
{
    int top, bot;

    if (ui_pk_cur < 0 || ui_pk_cur >= ui_pk_nrw)
        return;
    top = ui_pk_rw[ui_pk_cur].r.y - 4;
    bot = ui_pk_rw[ui_pk_cur].r.y + ui_pk_rw[ui_pk_cur].r.h + 4;
    if (top < ui_pk_sc)
        ui_pk_sc = top;
    else if (bot > ui_pk_sc + L->list.h)
        ui_pk_sc = bot - L->list.h;
    if (ui_pk_cur == ui_pk_first_entry())
        ui_pk_sc = 0.0;
}

/* The next entry up or down: in the grid the one in the line above or below that is nearest across. Headers are skipped. */
static int ui_pk_vstep(int from, int dir)
{
    int i = from + dir, best = -1, bestd = INT_MAX, liney = -1, cx;

    if (from < 0 || from >= ui_pk_nrw)
        return from;
    cx = ui_pk_rw[from].r.x + ui_pk_rw[from].r.w / 2;
    while (i >= 0 && i < ui_pk_nrw) {
        UiPkRow *w = &ui_pk_rw[i];

        if (w->r.y == ui_pk_rw[from].r.y && w->kind != 2) {
            i += dir;
            continue;
        }
        if (w->kind == 2) {
            if (best >= 0)
                break;
            i += dir;
            continue;
        }
        if (liney < 0)
            liney = w->r.y;
        if (w->r.y != liney)
            break;
        if (abs(w->r.x + w->r.w / 2 - cx) < bestd) {
            bestd = abs(w->r.x + w->r.w / 2 - cx);
            best = i;
        }
        i += dir;
    }
    return best >= 0 ? best : from;
}

static int ui_pk_hstep(int from, int dir)       /* the next entry along the line (grid view) */
{
    int i = from + dir;

    while (i >= 0 && i < ui_pk_nrw && ui_pk_rw[i].kind == 2)
        i += dir;
    return i >= 0 && i < ui_pk_nrw ? i : from;
}

/* Sort again (the order was changed): ticks travel with their entries, and the cursor stays on its entry */
static void ui_pk_resort(void)
{
    if (ui_pk_n > 1)
        qsort(ui_pk_e, ui_pk_n, sizeof(*ui_pk_e), ui_pk_cmp);
    if (ui_pk_nx > 1)
        qsort(ui_pk_x, ui_pk_nx, sizeof(*ui_pk_x), ui_pk_cmp);
    ui_pk_rebuild();
    ui_pk_goal = -1.0;
    if (ui_pk_touched)
        ui_pk_reveal = 1;
    else
        ui_pk_sc = 0.0;
}

/* ----- v51: thumbnails (grid view). A video shows a picture from about a tenth of the way in, a song shows its cover if it has one, and a
   folder shows a picture of something inside it (the first video, else the first song with a cover; one folder deeper if it has none).
   A thread does the decoding, one file at a time and only for the tiles that are in view, so scrolling never waits for it. What is made
   is kept in memory (a few hundred pictures) and is made again when the file or the folder changes. ----- */
#define UI_PK_TH_W   192
#define UI_PK_TH_H   108
#define UI_PK_TH_MAX 360
#define UI_PK_TQ     48

typedef struct { uint64_t key; int state, w, h; SDL_Texture *tex; int64_t born, used; } UiPkThumb;     /* state 1 asked, 2 ready, 3 nothing to show */
typedef struct { uint64_t key; int dir; char path[PATH_MAX]; } UiPkTReq;
typedef struct { uint64_t key; uint8_t *px; int w, h; } UiPkTRes;

static UiPkThumb ui_pk_th[UI_PK_TH_MAX];
static int ui_pk_nth = 0;
static UiPkTReq ui_pk_tq[UI_PK_TQ], ui_pk_want[UI_PK_TQ];
static int ui_pk_tqn = 0, ui_pk_nwant = 0;
static UiPkTRes ui_pk_tres[32];
static int ui_pk_tresn = 0, ui_pk_thread_on = 0, ui_pk_th_fading = 0;
static uint64_t ui_pk_tworking = 0;
static int64_t ui_pk_frame = 0;
static SDL_mutex *ui_pk_tmx = NULL;
static SDL_cond *ui_pk_tcv = NULL;

static uint64_t ui_pk_thumb_key(const UiPkEnt *e, const char *path)
{
    uint64_t h = 1469598103934665603ULL;
    const unsigned char *p = (const unsigned char *)path;
    char tail[64];
    int i;

    for (; *p; p++)
        h = (h ^ *p) * 1099511628211ULL;
    snprintf(tail, sizeof(tail), "|%ld|%ld|%d", (long)e->mtime, e->dir ? 0L : (long)e->size, e->dir);
    for (i = 0; tail[i]; i++)
        h = (h ^ (unsigned char)tail[i]) * 1099511628211ULL;
    return h ? h : 1;
}

static int ui_pk_intr_cb(void *p)
{
    return av_gettime_relative() > *(int64_t *)p;
}

/* A picture from a file: BGRA pixels in a box of at most UI_PK_TH_W x UI_PK_TH_H. Returns 1 if there is one. */
static int ui_pk_thumb_decode(const char *path, uint8_t **out, int *ow, int *oh)
{
    AVFormatContext *fc = avformat_alloc_context();
    AVCodecContext *cc = NULL;
    AVFrame *fr = NULL, *dst = NULL;
    AVPacket *pk = NULL;
    AVDictionary *opts = NULL;
    const AVCodec *dec = NULL;
    struct SwsContext *sws = NULL;
    int64_t deadline = av_gettime_relative() + 4000000;
    int vi, ok = 0, tw, th, i, got = 0;
    uint8_t *px = NULL;

    if (!fc)
        return 0;
    fc->interrupt_callback.callback = ui_pk_intr_cb;
    fc->interrupt_callback.opaque = &deadline;
    av_dict_set(&opts, "analyzeduration", "1500000", 0);
    av_dict_set(&opts, "probesize", "3000000", 0);
    if (avformat_open_input(&fc, path, NULL, &opts) < 0) {
        av_dict_free(&opts);
        return 0;                               /* avformat_open_input freed fc */
    }
    av_dict_free(&opts);
    if (avformat_find_stream_info(fc, NULL) < 0)
        goto end;
    vi = av_find_best_stream(fc, AVMEDIA_TYPE_VIDEO, -1, -1, &dec, 0);
    if (vi < 0 || !dec)
        goto end;
    if (!(cc = avcodec_alloc_context3(dec)) || avcodec_parameters_to_context(cc, fc->streams[vi]->codecpar) < 0)
        goto end;
    cc->thread_count = 1;
    cc->skip_loop_filter = AVDISCARD_NONREF;
    if (avcodec_open2(cc, dec, NULL) < 0)
        goto end;
    fr = av_frame_alloc();
    pk = av_packet_alloc();
    if (!fr || !pk)
        goto end;
    if (fc->streams[vi]->disposition & AV_DISPOSITION_ATTACHED_PIC) {       /* the cover of a song */
        if (avcodec_send_packet(cc, &fc->streams[vi]->attached_pic) >= 0) {
            avcodec_send_packet(cc, NULL);
            got = avcodec_receive_frame(cc, fr) >= 0;
        }
    } else {
        int64_t dur = fc->duration > 0 ? fc->duration : 0, target = 0;

        if (dur > 20 * AV_TIME_BASE)
            target = dur / 10;
        else if (dur > 4 * AV_TIME_BASE)
            target = dur / 3;
        if (target > 0) {
            if (fc->start_time != AV_NOPTS_VALUE)
                target += fc->start_time;
            if (av_seek_frame(fc, -1, target, AVSEEK_FLAG_BACKWARD) >= 0)
                avcodec_flush_buffers(cc);
        }
        for (i = 0; i < 400 && !got && av_gettime_relative() < deadline; i++) {
            int r = av_read_frame(fc, pk);

            if (r < 0)
                break;
            if (pk->stream_index == vi && avcodec_send_packet(cc, pk) >= 0)
                got = avcodec_receive_frame(cc, fr) >= 0;
            av_packet_unref(pk);
        }
    }
    if (!got || fr->width <= 0 || fr->height <= 0)
        goto end;
    tw = UI_PK_TH_W;
    th = (int)((int64_t)fr->height * tw / fr->width);
    if (th > UI_PK_TH_H) {
        th = UI_PK_TH_H;
        tw = (int)((int64_t)fr->width * th / fr->height);
    }
    tw = FFMAX(tw & ~1, 2);
    th = FFMAX(th & ~1, 2);
    {
        enum AVPixelFormat sf = fr->format;
        int full = 0;

        if (sf == AV_PIX_FMT_YUVJ420P) {                /* the "J" formats are the same pictures with full range */
            sf = AV_PIX_FMT_YUV420P;
            full = 1;
        } else if (sf == AV_PIX_FMT_YUVJ422P) {
            sf = AV_PIX_FMT_YUV422P;
            full = 1;
        } else if (sf == AV_PIX_FMT_YUVJ444P) {
            sf = AV_PIX_FMT_YUV444P;
            full = 1;
        } else if (sf == AV_PIX_FMT_YUVJ440P) {
            sf = AV_PIX_FMT_YUV440P;
            full = 1;
        }
        sws = sws_getContext(fr->width, fr->height, sf, tw, th, AV_PIX_FMT_BGRA, SWS_BILINEAR, NULL, NULL, NULL);
        if (!sws)
            goto end;
        sws_setColorspaceDetails(sws, sws_getCoefficients(SWS_CS_DEFAULT), full, sws_getCoefficients(SWS_CS_DEFAULT), 1, 0, 1 << 16, 1 << 16);
    }
    px = malloc((size_t)tw * th * 4);
    dst = av_frame_alloc();
    if (!px || !dst)
        goto end;
    {
        uint8_t *data[4] = { px, NULL, NULL, NULL };
        int ls[4] = { tw * 4, 0, 0, 0 };

        sws_scale(sws, (const uint8_t * const *)fr->data, fr->linesize, 0, fr->height, data, ls);
    }
    *out = px;
    px = NULL;
    *ow = tw;
    *oh = th;
    ok = 1;
end:
    free(px);
    av_frame_free(&dst);
    sws_freeContext(sws);
    av_packet_free(&pk);
    av_frame_free(&fr);
    avcodec_free_context(&cc);
    avformat_close_input(&fc);
    return ok;
}

static int ui_pk_thumb_namecmp(const void *a, const void *b)
{
    return av_strcasecmp(*(char * const *)a, *(char * const *)b);
}

/* A picture for a folder: the first video in it, else the first song that has a cover, else the same one folder down */
static int ui_pk_thumb_folder(const char *dir, int depth, int *tries, uint8_t **out, int *ow, int *oh)
{
    DIR *d = opendir(dir);
    struct dirent *de;
    char **vid = NULL, **aud = NULL, **sub = NULL, full[PATH_MAX + 300];
    int nv = 0, na = 0, ns = 0, i, ok = 0, seen = 0;

    if (!d)
        return 0;
    vid = calloc(400, sizeof(*vid));
    aud = calloc(400, sizeof(*aud));
    sub = calloc(400, sizeof(*sub));
    while (vid && aud && sub && (de = readdir(d)) && seen++ < 3000) {
        struct stat st;

        if (de->d_name[0] == '.')
            continue;
        snprintf(full, sizeof(full), "%s/%s", dir, de->d_name);
        if (stat(full, &st) != 0)
            continue;
        if (S_ISDIR(st.st_mode)) {
            if (ns < 400)
                sub[ns++] = strdup(de->d_name);
        } else if (S_ISREG(st.st_mode) && st.st_size > 0) {
            const char *dot = strrchr(de->d_name, '.');
            int k;

            if (!dot)
                continue;
            for (k = 0; ui_tv_ext[1][k]; k++)
                if (!av_strcasecmp(dot + 1, ui_tv_ext[1][k]) && nv < 400)
                    vid[nv++] = strdup(de->d_name);
            for (k = 0; ui_tv_ext[0][k]; k++)
                if (!av_strcasecmp(dot + 1, ui_tv_ext[0][k]) && na < 400)
                    aud[na++] = strdup(de->d_name);
        }
    }
    closedir(d);
    if (nv > 1)
        qsort(vid, nv, sizeof(*vid), ui_pk_thumb_namecmp);
    if (na > 1)
        qsort(aud, na, sizeof(*aud), ui_pk_thumb_namecmp);
    if (ns > 1)
        qsort(sub, ns, sizeof(*sub), ui_pk_thumb_namecmp);
    for (i = 0; i < nv && !ok && *tries < 6; i++, (*tries)++) {
        snprintf(full, sizeof(full), "%s/%s", dir, vid[i]);
        ok = ui_pk_thumb_decode(full, out, ow, oh);
    }
    for (i = 0; i < na && !ok && *tries < 6; i++, (*tries)++) {
        snprintf(full, sizeof(full), "%s/%s", dir, aud[i]);
        ok = ui_pk_thumb_decode(full, out, ow, oh);
    }
    for (i = 0; i < ns && !ok && depth < 2 && *tries < 6; i++) {
        snprintf(full, sizeof(full), "%s/%s", dir, sub[i]);
        ok = ui_pk_thumb_folder(full, depth + 1, tries, out, ow, oh);
    }
    for (i = 0; i < nv; i++)
        free(vid[i]);
    for (i = 0; i < na; i++)
        free(aud[i]);
    for (i = 0; i < ns; i++)
        free(sub[i]);
    free(vid);
    free(aud);
    free(sub);
    return ok;
}

static int ui_pk_thumb_thread(void *arg)
{
    (void)arg;
    for (;;) {
        UiPkTReq rq;
        uint8_t *px = NULL;
        int w = 0, h = 0, ok;

        SDL_LockMutex(ui_pk_tmx);
        while (ui_pk_tqn == 0)
            SDL_CondWait(ui_pk_tcv, ui_pk_tmx);
        rq = ui_pk_tq[0];
        memmove(&ui_pk_tq[0], &ui_pk_tq[1], (ui_pk_tqn - 1) * sizeof(ui_pk_tq[0]));
        ui_pk_tqn--;
        ui_pk_tworking = rq.key;
        SDL_UnlockMutex(ui_pk_tmx);
        if (rq.dir) {
            int tries = 0;

            ok = ui_pk_thumb_folder(rq.path, 0, &tries, &px, &w, &h);
        } else {
            ok = ui_pk_thumb_decode(rq.path, &px, &w, &h);
        }
        SDL_LockMutex(ui_pk_tmx);
        if (ui_pk_tresn < 32) {
            ui_pk_tres[ui_pk_tresn].key = rq.key;
            ui_pk_tres[ui_pk_tresn].px = ok ? px : NULL;
            ui_pk_tres[ui_pk_tresn].w = w;
            ui_pk_tres[ui_pk_tresn].h = h;
            ui_pk_tresn++;
        } else {
            free(px);                           /* the main loop is behind: this one is asked for again */
        }
        ui_pk_tworking = 0;
        SDL_UnlockMutex(ui_pk_tmx);
    }
    return 0;
}

static UiPkThumb *ui_pk_th_find(uint64_t key)
{
    int i;

    for (i = 0; i < ui_pk_nth; i++)
        if (ui_pk_th[i].key == key)
            return &ui_pk_th[i];
    return NULL;
}

static UiPkThumb *ui_pk_th_add(uint64_t key)
{
    UiPkThumb *t;
    int i, old = 0;

    if (ui_pk_nth < UI_PK_TH_MAX) {
        t = &ui_pk_th[ui_pk_nth++];
    } else {                                    /* full: the one that was shown longest ago goes */
        for (i = 1; i < ui_pk_nth; i++)
            if (ui_pk_th[i].used < ui_pk_th[old].used)
                old = i;
        t = &ui_pk_th[old];
        if (t->tex)
            SDL_DestroyTexture(t->tex);
    }
    memset(t, 0, sizeof(*t));
    t->key = key;
    t->state = 1;
    t->used = ui_pk_frame;
    return t;
}

static void ui_pk_thumb_begin(void)
{
    ui_pk_nwant = 0;
    ui_pk_th_fading = 0;
    ui_pk_frame++;
}

/* What the tiles in view are waiting for goes to the thread, in place of what it was told last time */
static void ui_pk_thumb_flush(void)
{
    int i, n = 0;

    if (!ui_pk_tmx) {
        if (!ui_pk_nwant)
            return;
        ui_pk_tmx = SDL_CreateMutex();
        ui_pk_tcv = SDL_CreateCond();
    }
    if (!ui_pk_thread_on && ui_pk_nwant) {
        SDL_Thread *t = SDL_CreateThread(ui_pk_thumb_thread, "pk-thumbs", NULL);

        if (t) {
            SDL_DetachThread(t);
            ui_pk_thread_on = 1;
        }
    }
    SDL_LockMutex(ui_pk_tmx);
    for (i = 0; i < ui_pk_nwant && n < UI_PK_TQ; i++)
        if (ui_pk_want[i].key != ui_pk_tworking)
            ui_pk_tq[n++] = ui_pk_want[i];
    ui_pk_tqn = n;
    if (n)
        SDL_CondSignal(ui_pk_tcv);
    SDL_UnlockMutex(ui_pk_tmx);
}

/* Finished pictures become textures (done here: only this thread may use the renderer) */
static int ui_pk_thumb_tick(void)
{
    UiPkTRes res[32];
    int n, i, got = 0;

    if (!ui_pk_tmx)
        return 0;
    SDL_LockMutex(ui_pk_tmx);
    n = ui_pk_tresn;
    memcpy(res, ui_pk_tres, n * sizeof(res[0]));
    ui_pk_tresn = 0;
    SDL_UnlockMutex(ui_pk_tmx);
    for (i = 0; i < n; i++) {
        UiPkThumb *t = ui_pk_th_find(res[i].key);

        if (!t) {
            free(res[i].px);
            continue;
        }
        got = 1;
        if (res[i].px) {
            t->tex = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STATIC, res[i].w, res[i].h);
            if (t->tex) {
                SDL_UpdateTexture(t->tex, NULL, res[i].px, res[i].w * 4);
                SDL_SetTextureBlendMode(t->tex, SDL_BLENDMODE_BLEND);
                t->w = res[i].w;
                t->h = res[i].h;
                t->state = 2;
                t->born = av_gettime_relative();
            } else {
                t->state = 3;
            }
        } else {
            t->state = 3;                       /* nothing to show: the icon stays */
        }
        free(res[i].px);
    }
    return got;
}

/* The picture of an entry inside a box, if there is one (the thread is asked for it if not). Returns 1 if it was drawn. */
static int ui_pk_thumb_draw(const UiPkEnt *e, const SDL_Rect *box)
{
    char path[PATH_MAX + 300];
    uint64_t key;
    UiPkThumb *t;
    SDL_Rect dst;
    int64_t age;

    if (!cfg_pk_thumbs || (!e->dir && e->size <= 0))
        return 0;                               /* an empty file has no picture */
    ui_pk_path_of(e, path, sizeof(path));
    key = ui_pk_thumb_key(e, path);
    t = ui_pk_th_find(key);
    if (!t)
        t = ui_pk_th_add(key);
    if (!t)
        return 0;
    t->used = ui_pk_frame;
    if (t->state == 1) {
        if (ui_pk_nwant < UI_PK_TQ) {
            ui_pk_want[ui_pk_nwant].key = key;
            ui_pk_want[ui_pk_nwant].dir = e->dir;
            snprintf(ui_pk_want[ui_pk_nwant].path, sizeof(ui_pk_want[0].path), "%s", path);
            ui_pk_nwant++;
        }
        return 0;
    }
    if (t->state != 2 || !t->tex)
        return 0;
    dst.h = box->h;
    dst.w = t->w * box->h / t->h;
    if (dst.w > box->w) {
        dst.w = box->w;
        dst.h = t->h * box->w / t->w;
    }
    dst.x = box->x + (box->w - dst.w) / 2;
    dst.y = box->y + (box->h - dst.h) / 2;
    age = av_gettime_relative() - t->born;
    SDL_SetTextureAlphaMod(t->tex, age < 220000 ? (Uint8)(255 * age / 220000) : 255);
    if (age < 220000)
        ui_pk_th_fading = 1;
    SDL_RenderCopy(renderer, t->tex, NULL, &dst);
    return 1;
}

static UiPkDev ui_pk_dev[24];                   /* v49: drives and partitions (see the drives section below) */
static int ui_pk_ndev = 0;

/* ----- v49: going back, forward and up ----- */
#define UI_PK_HIST 48
static char *ui_pk_hist[UI_PK_HIST];
static int ui_pk_hn = 0, ui_pk_hi = -1;

static void ui_pk_hist_clear(void)
{
    int i;

    for (i = 0; i < ui_pk_hn; i++)
        free(ui_pk_hist[i]);
    ui_pk_hn = 0;
    ui_pk_hi = -1;
}

static void ui_pk_hist_push(void)               /* the open folder becomes the newest one; what lay ahead of it is forgotten */
{
    int i;

    if (ui_pk_hi >= 0 && ui_pk_hi < ui_pk_hn && !strcmp(ui_pk_hist[ui_pk_hi], ui_pk_dir))
        return;
    for (i = ui_pk_hi + 1; i < ui_pk_hn; i++)
        free(ui_pk_hist[i]);
    ui_pk_hn = ui_pk_hi + 1;
    if (ui_pk_hn >= UI_PK_HIST) {
        free(ui_pk_hist[0]);
        memmove(ui_pk_hist, ui_pk_hist + 1, sizeof(char *) * (UI_PK_HIST - 1));
        ui_pk_hn--;
    }
    ui_pk_hist[ui_pk_hn++] = strdup(ui_pk_dir);
    ui_pk_hi = ui_pk_hn - 1;
}

static void ui_pk_jq_clear(void);
static void ui_pk_search_start(void);
static void ui_pk_tree_reveal(void);

/* Read a folder. Returns 0 if it cannot be read (nothing changes then). */
static int ui_pk_load(const char *dir)
{
    char real[PATH_MAX], full[PATH_MAX + 300];
    DIR *d;
    struct dirent *de;

    if (!realpath(dir, real) || !(d = opendir(real)))
        return 0;
    ui_pk_nrw = 0;                              /* the rows point into what is freed now */
    ui_pk_free_ents(ui_pk_e, ui_pk_n);
    ui_pk_n = 0;
    ui_pk_free_ents(ui_pk_x, ui_pk_nx);
    ui_pk_nx = 0;
    ui_pk_jq_clear();
    while ((de = readdir(d))) {
        struct stat st;
        int isdir;
        UiPkEnt *e;

        if (!strcmp(de->d_name, ".") || !strcmp(de->d_name, ".."))
            continue;
        if (de->d_name[0] == '.' && !ui_pk_hidden)
            continue;
        snprintf(full, sizeof(full), "%s/%s", real, de->d_name);
        if (stat(full, &st) != 0)
            continue;                           /* a broken link */
        isdir = S_ISDIR(st.st_mode);
        if (!isdir && !S_ISREG(st.st_mode))
            continue;
        if (!isdir && (ui_pk_mode == 1 || (!ui_pk_all && !ui_pk_has_ext(de->d_name))))
            continue;                           /* a folder is looked for: no files; else only what can be played, unless all are asked for */
        if (ui_pk_n >= 20000)
            break;
        if (!(e = ui_pk_push(&ui_pk_e, &ui_pk_n, &ui_pk_cap)))
            break;
        e->name = strdup(de->d_name);
        e->dir = isdir;
        e->size = st.st_size;
        e->mtime = st.st_mtime;
        e->count = -1;
    }
    closedir(d);
    if (ui_pk_n > 1)
        qsort(ui_pk_e, ui_pk_n, sizeof(*ui_pk_e), ui_pk_cmp);
    ui_pk_nav_t = av_gettime_relative();
    snprintf(ui_pk_dir, sizeof(ui_pk_dir), "%s", real);
    snprintf(ui_pk_last, sizeof(ui_pk_last), "%s", real);
    ui_pk_filter[0] = 0;
    ui_pk_search_on = 0;
    ui_pk_touched = 0;
    ui_pk_sc = 0.0;
    ui_pk_goal = -1.0;
    ui_pk_rebuild();
    ui_pk_tree_reveal();                        /* v51: the tree opens down to this folder */
    return 1;
}

/* The same folder again (a switch changed what is shown); what was typed stays */
static void ui_pk_reload(void)
{
    char keep[PATH_MAX], q[sizeof(ui_pk_filter)];
    int so = ui_pk_search_on;

    snprintf(keep, sizeof(keep), "%s", ui_pk_dir);
    snprintf(q, sizeof(q), "%s", ui_pk_filter);
    if (!ui_pk_load(keep))
        return;
    snprintf(ui_pk_filter, sizeof(ui_pk_filter), "%s", q);
    ui_pk_search_on = so;
    if (ui_pk_filter[0])
        ui_pk_search_start();
    else
        ui_pk_rebuild();
}

static void ui_pk_go(const char *dir)
{
    if (!ui_pk_load(dir)) {
        snprintf(ui_pk_note, sizeof(ui_pk_note), "Cannot open %.120s", dir);
        ui_pk_note_until = av_gettime_relative() + 2500000;
        return;
    }
    ui_pk_hist_push();
}

static void ui_pk_back(int step)
{
    int to = ui_pk_hi + step;

    if (to < 0 || to >= ui_pk_hn)
        return;
    if (ui_pk_load(ui_pk_hist[to])) {
        ui_pk_hi = to;
    } else {
        snprintf(ui_pk_note, sizeof(ui_pk_note), "That folder is gone");
        ui_pk_note_until = av_gettime_relative() + 2500000;
    }
}

static void ui_pk_up(void)
{
    char parent[PATH_MAX], base[PATH_MAX], old[PATH_MAX], *slash;
    int i;

    if (!strcmp(ui_pk_dir, "/"))
        return;
    snprintf(old, sizeof(old), "%s", ui_pk_dir);
    snprintf(parent, sizeof(parent), "%s", ui_pk_dir);
    slash = strrchr(parent, '/');
    snprintf(base, sizeof(base), "%s", slash ? slash + 1 : "");
    if (slash == parent)
        parent[1] = 0;                          /* the parent is the root */
    else if (slash)
        *slash = 0;
    ui_pk_go(parent);
    if (!strcmp(ui_pk_dir, old))
        return;
    for (i = 0; i < ui_pk_nrw; i++) {           /* the cursor goes to the folder that was left */
        UiPkEnt *e = ui_pk_ent(i);

        if (e && !strcmp(e->name, base)) {
            ui_pk_cur = i;
            ui_pk_touched = 1;
            ui_pk_reveal = 1;
            break;
        }
    }
}

/* ----- v49: search by typing: in this folder (instant), below it, above it, and elsewhere (found a little at a time, so the player
   never waits) ----- */
typedef struct { char *path; int depth; } UiPkJob;
typedef struct { UiPkJob *j; int n, head, cap; } UiPkJq;
static UiPkJq ui_pk_jq[3];                      /* 0 = below this folder, 1 = above it, 2 = elsewhere: they are searched in that order */
static int ui_pk_scan_on = 0, ui_pk_dirs_seen = 0, ui_pk_xc[4];
static const int ui_pk_xmax[4] = { 0, 250, 150, 250 };

static void ui_pk_jq_clear(void)
{
    int q, i;

    for (q = 0; q < 3; q++) {
        for (i = ui_pk_jq[q].head; i < ui_pk_jq[q].n; i++)
            free(ui_pk_jq[q].j[i].path);
        ui_pk_jq[q].n = ui_pk_jq[q].head = 0;
    }
    ui_pk_scan_on = 0;
    ui_pk_dirs_seen = 0;
    memset(ui_pk_xc, 0, sizeof(ui_pk_xc));
}

static void ui_pk_jq_push(int q, const char *path, int depth)
{
    UiPkJq *jq = &ui_pk_jq[q];

    if (jq->n >= jq->cap) {
        int nc = jq->cap ? jq->cap * 2 : 64;
        UiPkJob *nj = realloc(jq->j, nc * sizeof(*nj));

        if (!nj)
            return;
        jq->j = nj;
        jq->cap = nc;
    }
    jq->j[jq->n].path = strdup(path);
    jq->j[jq->n].depth = depth;
    jq->n++;
}

static int ui_pk_under(const char *path, const char *base)     /* path is base, or inside it */
{
    size_t n = strlen(base);

    if (!strcmp(base, "/"))
        return 1;
    return !strncmp(path, base, n) && (path[n] == '/' || !path[n]);
}

static void ui_pk_search_start(void)
{
    char p[PATH_MAX];
    const char *home = getenv("HOME");
    int i, n;

    ui_pk_nrw = 0;
    ui_pk_free_ents(ui_pk_x, ui_pk_nx);
    ui_pk_nx = 0;
    ui_pk_jq_clear();
    if (ui_pk_filter[0]) {
        ui_pk_jq_push(0, ui_pk_dir, 0);         /* the open folder itself is already listed: only its folders are entered */
        snprintf(p, sizeof(p), "%s", ui_pk_dir);
        for (i = 0; i < 14 && strcmp(p, "/"); i++) {
            char *slash = strrchr(p, '/');

            if (slash == p)
                p[1] = 0;
            else if (slash)
                *slash = 0;
            else
                break;
            ui_pk_jq_push(1, p, 0);
        }
        if (home && home[0])
            ui_pk_jq_push(2, home, 0);
        for (n = 0; n < ui_pk_ndev; n++)
            if (ui_pk_dev[n].mnt[0])
                ui_pk_jq_push(2, ui_pk_dev[n].mnt, 0);
        ui_pk_scan_on = 1;
    }
    ui_pk_rebuild();
    ui_pk_sc = 0.0;
    ui_pk_goal = -1.0;
}

static int ui_pk_dup(const char *where, const char *name)
{
    int i;

    for (i = 0; i < ui_pk_nx; i++)
        if (!strcmp(ui_pk_x[i].name, name) && !strcmp(ui_pk_x[i].where, where))
            return 1;
    return 0;
}

/* Look into one folder of the search. Returns 1 if a result was added. */
static int ui_pk_scan_dir(int q, const UiPkJob *job)
{
    static const int maxd[3] = { 6, 0, 4 };
    char full[PATH_MAX + 300];
    DIR *d;
    struct dirent *de;
    int added = 0, add = !(q == 0 && job->depth == 0), sect = q + 1;

    if (q == 2 && ui_pk_under(job->path, ui_pk_dir))
        return 0;                               /* that is "below this folder" */
    if (!(d = opendir(job->path)))
        return 0;
    ui_pk_dirs_seen++;
    while ((de = readdir(d))) {
        struct stat st;
        int isdir, isreg, islnk = de->d_type == DT_LNK;

        if (de->d_name[0] == '.' && (!de->d_name[1] || (de->d_name[1] == '.' && !de->d_name[2])))
            continue;
        if (de->d_name[0] == '.' && !ui_pk_hidden)
            continue;
        snprintf(full, sizeof(full), "%s/%s", job->path, de->d_name);
        if (de->d_type == DT_DIR) {
            isdir = 1;
            isreg = 0;
        } else if (de->d_type == DT_REG) {
            isdir = 0;
            isreg = 1;
        } else {
            if (stat(full, &st) != 0)
                continue;
            isdir = S_ISDIR(st.st_mode);
            isreg = S_ISREG(st.st_mode);
        }
        if (isdir && !islnk && job->depth < maxd[q])
            ui_pk_jq_push(q, full, job->depth + 1);
        if (!add || (!isdir && !isreg) || !av_stristr(de->d_name, ui_pk_filter))
            continue;
        if (!isdir && (ui_pk_mode == 1 || (!ui_pk_all && !ui_pk_has_ext(de->d_name))))
            continue;
        if (ui_pk_xc[sect] >= ui_pk_xmax[sect] || ui_pk_nx >= UI_PK_MAXX || ui_pk_dup(job->path, de->d_name))
            continue;
        if (stat(full, &st) == 0) {
            UiPkEnt *e = ui_pk_push(&ui_pk_x, &ui_pk_nx, &ui_pk_xcap);

            if (!e)
                continue;
            e->name = strdup(de->d_name);
            e->where = strdup(job->path);
            e->dir = isdir;
            e->size = st.st_size;
            e->mtime = st.st_mtime;
            e->count = -1;
            e->sect = sect;
            ui_pk_xc[sect]++;
            added = 1;
        }
    }
    closedir(d);
    return added;
}

/* A few milliseconds of searching for each turn of the main loop */
static void ui_pk_search_tick(void)
{
    int64_t until = av_gettime_relative() + 6000;
    int changed = 0, was_on = ui_pk_scan_on;

    while (ui_pk_scan_on && av_gettime_relative() < until) {
        UiPkJob job;
        int q;

        for (q = 0; q < 3 && ui_pk_jq[q].head >= ui_pk_jq[q].n; q++)
            ;
        if (q >= 3 || ui_pk_dirs_seen > 6000) {
            ui_pk_scan_on = 0;
            break;
        }
        job = ui_pk_jq[q].j[ui_pk_jq[q].head++];
        if (ui_pk_scan_dir(q, &job))
            changed = 1;
        free(job.path);
    }
    if (was_on && !ui_pk_scan_on) {
        int i;

        for (i = 0; i < 3; i++) {               /* done (or enough): nothing more to look into */
            int k;

            for (k = ui_pk_jq[i].head; k < ui_pk_jq[i].n; k++)
                free(ui_pk_jq[i].j[k].path);
            ui_pk_jq[i].n = ui_pk_jq[i].head = 0;
        }
        if (ui_pk_nx > 1)
            qsort(ui_pk_x, ui_pk_nx, sizeof(*ui_pk_x), ui_pk_cmp);
        changed = 1;
    }
    if (changed) {
        ui_pk_rebuild();
        if (ui_pk_touched)
            ui_pk_reveal = 1;
    }
}

/* ----- v49: drives. Partitions and external drives that are not mounted yet are listed under "Devices"; a click mounts them (through
   udisks, the same service the Files app uses) and goes in. Both the looking for drives and the mounting happen in a thread. ----- */
static SDL_atomic_t ui_pk_dev_state;            /* 0 = idle, 1 = looking, 2 = a new list is ready */
static SDL_atomic_t ui_pk_mnt_state;            /* 0 = idle, 1 = mounting, 2 = mounted (ui_pk_mnt_path), 3 = failed (ui_pk_mnt_msg) */
static UiPkDev ui_pk_dev_tmp[24];
static int ui_pk_dev_tmpn = 0;
static char ui_pk_mnt_path[PATH_MAX], ui_pk_mnt_msg[240], ui_pk_mnt_name[64];
static int64_t ui_pk_dev_next = 0;

static int ui_pk_devname_ok(const char *s)      /* only a plain device name goes near a shell */
{
    size_t i, n = strlen(s);

    if (n < 6 || n > 47 || strncmp(s, "/dev/", 5))
        return 0;
    for (i = 5; i < n; i++)
        if (!isalnum((unsigned char)s[i]) && s[i] != '_' && s[i] != '-' && s[i] != '.' && s[i] != '/')
            return 0;
    return !strstr(s, "..");
}

/* The value of KEY="..." in a line of `lsblk -P`, with \xNN escapes turned into characters */
static int ui_pk_lsblk_val(const char *line, const char *key, char *out, size_t size)
{
    char pat[32];
    const char *p = line, *q;
    size_t n = 0;

    snprintf(pat, sizeof(pat), "%s=\"", key);
    for (;;) {
        p = strstr(p, pat);
        if (!p)
            return 0;
        if (p == line || p[-1] == ' ')
            break;
        p++;
    }
    q = p + strlen(pat);
    while (*q && *q != '"' && n + 1 < size) {
        if (q[0] == '\\' && q[1] == 'x' && isxdigit((unsigned char)q[2]) && isxdigit((unsigned char)q[3])) {
            char hex[3] = { q[2], q[3], 0 };

            out[n++] = (char)strtol(hex, NULL, 16);
            q += 4;
        } else {
            out[n++] = *q++;
        }
    }
    out[n] = 0;
    return 1;
}

static int ui_pk_mnt_system(const char *m)      /* a mount point of the system itself, not of a drive of the person */
{
    static const char * const sys[] = { "/boot", "/var", "/usr", "/snap", "/etc", "/tmp", "/proc", "/sys", "/dev", "/opt", "[SWAP]", NULL };
    int i;

    if (!strcmp(m, "/") || !strcmp(m, "/home"))
        return 1;
    for (i = 0; sys[i]; i++)
        if (ui_pk_under(m, sys[i]))
            return 1;
    return !strncmp(m, "/run", 4) && strncmp(m, "/run/media", 10);
}

static int ui_pk_dev_thread(void *arg)
{
    FILE *f = popen("lsblk -P -b -o PATH,LABEL,SIZE,FSTYPE,MOUNTPOINT,TYPE,PARTTYPE 2>/dev/null", "r");
    char line[2048];
    const char *user = getenv("USER");
    int n = 0, k;

    if (f) {
        while (fgets(line, sizeof(line), f) && n < 22) {
            char path[64] = "", label[64] = "", size[32] = "", fst[32] = "", mnt[PATH_MAX] = "", type[16] = "", pt[48] = "";
            double bytes;
            char gb[16];

            ui_pk_lsblk_val(line, "PATH", path, sizeof(path));
            ui_pk_lsblk_val(line, "LABEL", label, sizeof(label));
            ui_pk_lsblk_val(line, "SIZE", size, sizeof(size));
            ui_pk_lsblk_val(line, "FSTYPE", fst, sizeof(fst));
            ui_pk_lsblk_val(line, "MOUNTPOINT", mnt, sizeof(mnt));
            ui_pk_lsblk_val(line, "TYPE", type, sizeof(type));
            ui_pk_lsblk_val(line, "PARTTYPE", pt, sizeof(pt));
            if (!fst[0] || !ui_pk_devname_ok(path) || (strcmp(type, "part") && strcmp(type, "disk") && strcmp(type, "crypt")))
                continue;                       /* no file system: nothing to open */
            if (!strcmp(fst, "swap") || !strcmp(fst, "crypto_LUKS") || !strcmp(fst, "LVM2_member") || !strcmp(fst, "linux_raid_member") ||
                !strcmp(fst, "squashfs") || !strcmp(fst, "iso9660"))
                continue;
            if (!av_strcasecmp(pt, "c12a7328-f81f-11d2-ba4b-00a0c93ec93b") || !av_strcasecmp(pt, "de94bba4-06d1-4d40-a16a-bfd50179d6ac"))
                continue;                       /* the EFI system partition and the Windows recovery partition */
            if (mnt[0] && ui_pk_mnt_system(mnt))
                continue;
            bytes = atof(size);
            snprintf(gb, sizeof(gb), "%.0f GB", bytes / 1e9);
            snprintf(ui_pk_dev_tmp[n].dev, sizeof(ui_pk_dev_tmp[0].dev), "%s", path);
            snprintf(ui_pk_dev_tmp[n].mnt, sizeof(ui_pk_dev_tmp[0].mnt), "%s", mnt);
            snprintf(ui_pk_dev_tmp[n].size, sizeof(ui_pk_dev_tmp[0].size), "%s", gb);
            if (label[0])
                snprintf(ui_pk_dev_tmp[n].label, sizeof(ui_pk_dev_tmp[0].label), "%s", label);
            else
                snprintf(ui_pk_dev_tmp[n].label, sizeof(ui_pk_dev_tmp[0].label), "%s Volume", gb);
            n++;
        }
        pclose(f);
    }
    for (k = 0; k < 2 && user && user[0]; k++) {    /* drives that are mounted under /media/USER or /run/media/USER, if lsblk did not name them */
        char base[PATH_MAX];
        DIR *d;
        struct dirent *de;

        snprintf(base, sizeof(base), "%s/%s", k ? "/run/media" : "/media", user);
        if (!(d = opendir(base)))
            continue;
        while ((de = readdir(d)) && n < 22) {
            char full[PATH_MAX + 300];
            int i, have = 0;

            if (de->d_name[0] == '.')
                continue;
            snprintf(full, sizeof(full), "%s/%s", base, de->d_name);
            for (i = 0; i < n; i++)
                if (!strcmp(ui_pk_dev_tmp[i].mnt, full))
                    have = 1;
            if (have)
                continue;
            ui_pk_dev_tmp[n].dev[0] = 0;
            ui_pk_dev_tmp[n].size[0] = 0;
            snprintf(ui_pk_dev_tmp[n].mnt, sizeof(ui_pk_dev_tmp[0].mnt), "%.4000s", full);
            snprintf(ui_pk_dev_tmp[n].label, sizeof(ui_pk_dev_tmp[0].label), "%.60s", de->d_name);
            n++;
        }
        closedir(d);
    }
    ui_pk_dev_tmpn = n;
    SDL_AtomicSet(&ui_pk_dev_state, 2);
    (void)arg;
    return 0;
}

static int ui_pk_mnt_op = 0;                    /* what the thread was asked to do: 0 mount, 1 unmount (for the message) */

/* arg: "m|/dev/sdb1" to mount, "u|/dev/sdb1|/media/me/DISK" to unmount */
static int ui_pk_mnt_thread(void *arg)
{
    char *spec = arg, *dev = spec + 2, *mnt, cmd[700], line[512], msg[240] = "", mp[PATH_MAX] = "";
    FILE *f;
    int ok = 0, tries, un = spec[0] == 'u';

    mnt = strchr(dev, '|');
    if (mnt)
        *mnt++ = 0;
    for (tries = 0; tries < 2 && !ok; tries++) {
        if (un && tries && (!mnt || !mnt[0] || strchr(mnt, '\'')))
            break;                              /* nothing else to try */
        if (un)
            snprintf(cmd, sizeof(cmd), tries ? "gio mount -u '%s' 2>&1" : "udisksctl unmount -b '%s' 2>&1", tries ? mnt : dev);
        else
            snprintf(cmd, sizeof(cmd), tries ? "gio mount -d '%s' 2>&1" : "udisksctl mount -b '%s' 2>&1", dev);
        if (!(f = popen(cmd, "r")))
            continue;
        while (fgets(line, sizeof(line), f)) {
            line[strcspn(line, "\n")] = 0;
            if (line[0])
                snprintf(msg, sizeof(msg), "%.230s", line);
        }
        pclose(f);
        mp[0] = 0;
        snprintf(cmd, sizeof(cmd), "lsblk -no MOUNTPOINT '%s' 2>/dev/null", dev);
        if ((f = popen(cmd, "r"))) {
            if (fgets(mp, sizeof(mp), f))
                mp[strcspn(mp, "\n")] = 0;
            pclose(f);
        }
        ok = un ? !mp[0] : mp[0] != 0;
    }
    if (ok) {
        snprintf(ui_pk_mnt_path, sizeof(ui_pk_mnt_path), "%s", un ? "" : mp);
    } else {
        const char *m = strstr(msg, "Error ");
        const char *c = m ? strchr(m, ':') : NULL;

        snprintf(ui_pk_mnt_msg, sizeof(ui_pk_mnt_msg), "%.230s", c && c[1] ? c + 2 : msg[0] ? msg : un ? "it is in use" : "it could not be mounted");
    }
    free(spec);
    SDL_AtomicSet(&ui_pk_mnt_state, ok ? 2 : 3);
    return 0;
}

static void ui_pk_dev_start(void)
{
    SDL_Thread *t;

    if (SDL_AtomicGet(&ui_pk_dev_state) != 0)
        return;
    SDL_AtomicSet(&ui_pk_dev_state, 1);
    ui_pk_dev_next = av_gettime_relative() + 5000000;
    if ((t = SDL_CreateThread(ui_pk_dev_thread, "pk-drives", NULL)))
        SDL_DetachThread(t);
    else
        SDL_AtomicSet(&ui_pk_dev_state, 0);
}

static void ui_pk_mnt_run(const UiPkDev *dv, int un)
{
    SDL_Thread *t;
    char *spec;

    if (SDL_AtomicGet(&ui_pk_mnt_state) == 1 || !dv->dev[0] || !ui_pk_devname_ok(dv->dev))
        return;
    if (un && ui_pk_under(ui_pk_dir, dv->mnt)) {        /* do not unmount the folder that is open: leave it first */
        const char *home = getenv("HOME");

        ui_pk_go(home && home[0] ? home : "/");
    }
    snprintf(ui_pk_mnt_name, sizeof(ui_pk_mnt_name), "%s", dv->label);
    snprintf(ui_pk_note, sizeof(ui_pk_note), "%s %.100s ...", un ? "Unmounting" : "Mounting", dv->label);
    ui_pk_note_until = av_gettime_relative() + 60000000;
    ui_pk_mnt_op = un;
    spec = malloc(strlen(dv->dev) + strlen(dv->mnt) + 8);
    if (!spec)
        return;
    sprintf(spec, "%c|%s|%s", un ? 'u' : 'm', dv->dev, dv->mnt);
    SDL_AtomicSet(&ui_pk_mnt_state, 1);
    if ((t = SDL_CreateThread(ui_pk_mnt_thread, "pk-mount", spec))) {
        SDL_DetachThread(t);
    } else {
        free(spec);
        SDL_AtomicSet(&ui_pk_mnt_state, 0);
    }
}

static void ui_pk_mount(const UiPkDev *dv)
{
    ui_pk_mnt_run(dv, 0);
}

/* ----- v49: the folder tree on the left. Every folder has a drop down; it is read when it is opened. ----- */
static UiPkNode *ui_pk_tn = NULL;
static int ui_pk_ntn = 0, ui_pk_ctn = 0;

static void ui_pk_tn_free(UiPkNode *n)
{
    free(n->name);
    free(n->path);
    free(n->dev);
}

static void ui_pk_tree_clear(void)
{
    int i;

    for (i = 0; i < ui_pk_ntn; i++)
        ui_pk_tn_free(&ui_pk_tn[i]);
    ui_pk_ntn = 0;
}

static int ui_pk_tn_insert(int at, const char *name, const char *path, const char *dev, int depth, int kind, int grp)
{
    UiPkNode *n;

    if (ui_pk_ntn >= ui_pk_ctn) {
        int nc = ui_pk_ctn ? ui_pk_ctn * 2 : 64;
        UiPkNode *nn = realloc(ui_pk_tn, nc * sizeof(*nn));

        if (!nn)
            return 0;
        ui_pk_tn = nn;
        ui_pk_ctn = nc;
    }
    at = av_clip(at, 0, ui_pk_ntn);
    memmove(&ui_pk_tn[at + 1], &ui_pk_tn[at], (ui_pk_ntn - at) * sizeof(*ui_pk_tn));
    n = &ui_pk_tn[at];
    memset(n, 0, sizeof(*n));
    n->name = strdup(name);
    n->path = strdup(path ? path : "");
    n->dev = dev ? strdup(dev) : NULL;
    n->depth = depth;
    n->kind = kind;
    n->grp = grp;
    n->kids = kind == 0 ? -1 : 0;
    ui_pk_ntn++;
    return 1;
}

static void ui_pk_tree_close(int i)
{
    int j = i + 1;

    if (i < 0 || i >= ui_pk_ntn)
        return;
    while (j < ui_pk_ntn && ui_pk_tn[j].kind != 2 && ui_pk_tn[j].depth > ui_pk_tn[i].depth)
        ui_pk_tn_free(&ui_pk_tn[j++]);
    memmove(&ui_pk_tn[i + 1], &ui_pk_tn[j], (ui_pk_ntn - j) * sizeof(*ui_pk_tn));
    ui_pk_ntn -= j - i - 1;
    ui_pk_tn[i].open = 0;
}

static int ui_pk_name_cmp(const void *a, const void *b)
{
    return av_strcasecmp(*(char * const *)a, *(char * const *)b);
}

static void ui_pk_tree_open(int i)
{
    DIR *d;
    struct dirent *de;
    char **names = NULL, full[PATH_MAX + 300];
    int n = 0, cap = 0, k;

    if (i < 0 || i >= ui_pk_ntn || ui_pk_tn[i].kind != 0 || !ui_pk_tn[i].path[0] || !(d = opendir(ui_pk_tn[i].path)))
        return;
    while ((de = readdir(d))) {
        int isdir = de->d_type == DT_DIR;

        if (de->d_name[0] == '.' && (!de->d_name[1] || (de->d_name[1] == '.' && !de->d_name[2])))
            continue;
        if (de->d_name[0] == '.' && !ui_pk_hidden)
            continue;
        if (!isdir && (de->d_type == DT_LNK || de->d_type == DT_UNKNOWN)) {
            struct stat st;

            snprintf(full, sizeof(full), "%s/%s", ui_pk_tn[i].path, de->d_name);
            isdir = stat(full, &st) == 0 && S_ISDIR(st.st_mode);
        }
        if (!isdir || n >= 400)
            continue;
        if (n >= cap) {
            char **nn = realloc(names, (cap ? cap * 2 : 32) * sizeof(*names));

            if (!nn)
                break;
            names = nn;
            cap = cap ? cap * 2 : 32;
        }
        names[n++] = strdup(de->d_name);
    }
    closedir(d);
    if (n > 1)
        qsort(names, n, sizeof(*names), ui_pk_name_cmp);
    ui_pk_tn[i].kids = n;
    ui_pk_tn[i].open = n > 0;
    for (k = 0; k < n; k++) {
        const char *base = ui_pk_tn[i].path;

        snprintf(full, sizeof(full), "%s%s%s", base, !strcmp(base, "/") ? "" : "/", names[k]);
        ui_pk_tn_insert(i + 1 + k, names[k], full, NULL, ui_pk_tn[i].depth + 1, 0, ui_pk_tn[i].grp);
        free(names[k]);
    }
    free(names);
}

/* The drives part of the tree, made again from ui_pk_dev (the places above it keep their drop downs) */
static void ui_pk_tree_devs(void)
{
    int i, f = -1;

    for (i = 0; i < ui_pk_ntn; i++)
        if (ui_pk_tn[i].grp == 1) {
            f = i;
            break;
        }
    if (f >= 0) {
        for (i = f; i < ui_pk_ntn; i++)
            ui_pk_tn_free(&ui_pk_tn[i]);
        ui_pk_ntn = f;
    }
    if (ui_pk_ndev <= 0)
        return;
    ui_pk_tn_insert(ui_pk_ntn, "Devices", "", NULL, 0, 2, 1);
    for (i = 0; i < ui_pk_ndev; i++) {
        char real[PATH_MAX];
        const char *m = ui_pk_dev[i].mnt;

        if (m[0] && realpath(m, real))
            m = real;
        ui_pk_tn_insert(ui_pk_ntn, ui_pk_dev[i].label, m, ui_pk_dev[i].dev[0] ? ui_pk_dev[i].dev : NULL, 0, ui_pk_dev[i].mnt[0] ? 0 : 1, 1);
    }
}

static void ui_pk_rec_load(void);
static void ui_pk_tree_recents(void);

static void ui_pk_tree_build(void)
{
    static const char * const names[] = { "Home", "Desktop", "Documents", "Downloads", "Music", "Videos", "Pictures" };
    const char *home = getenv("HOME");
    char base[PATH_MAX], real[PATH_MAX];
    int i;

    ui_pk_tree_clear();
    for (i = 0; home && home[0] && i < 7; i++) {
        struct stat st;

        if (i)
            snprintf(base, sizeof(base), "%s/%s", home, names[i]);
        else
            snprintf(base, sizeof(base), "%s", home);
        if (stat(base, &st) == 0 && S_ISDIR(st.st_mode))
            ui_pk_tn_insert(ui_pk_ntn, names[i], realpath(base, real) ? real : base, NULL, 0, 0, 0);
    }
    ui_pk_tn_insert(ui_pk_ntn, "Computer", "/", NULL, 0, 0, 0);
    ui_pk_rec_load();
    ui_pk_tree_recents();
    ui_pk_tree_devs();
}


/* ----- v51: recent places: the folders something was played or added from, newest first (kept in recent_places.txt) ----- */
#define UI_PK_NREC 6
static char *ui_pk_rec[UI_PK_NREC];
static int ui_pk_nrec = 0, ui_pk_rec_loaded = 0;

static int ui_pk_rec_file(char *out, size_t size)
{
    const char *home = getenv("HOME");

    if (!home || !home[0])
        return 0;
    snprintf(out, size, "%s/.config/ffplay-custom/recent_places.txt", home);
    return 1;
}

static void ui_pk_rec_load(void)
{
    char path[PATH_MAX + 64], line[PATH_MAX + 8];
    FILE *f;

    if (ui_pk_rec_loaded)
        return;
    ui_pk_rec_loaded = 1;
    if (!ui_pk_rec_file(path, sizeof(path)) || !(f = fopen(path, "r")))
        return;
    while (ui_pk_nrec < UI_PK_NREC && fgets(line, sizeof(line), f)) {
        line[strcspn(line, "\n")] = 0;
        if (line[0] == '/')
            ui_pk_rec[ui_pk_nrec++] = strdup(line);
    }
    fclose(f);
}

static void ui_pk_rec_save(void)
{
    char path[PATH_MAX + 64];
    FILE *f;
    int i;

    if (!ui_pk_rec_file(path, sizeof(path)) || !(f = fopen(path, "w")))
        return;
    for (i = 0; i < ui_pk_nrec; i++)
        fprintf(f, "%s\n", ui_pk_rec[i]);
    fclose(f);
}

static void ui_pk_rec_add(const char *dir)
{
    int i, at = ui_pk_nrec;

    ui_pk_rec_load();
    for (i = 0; i < ui_pk_nrec; i++)
        if (!strcmp(ui_pk_rec[i], dir)) {
            at = i;
            break;
        }
    if (at == ui_pk_nrec) {
        if (ui_pk_nrec < UI_PK_NREC)
            ui_pk_nrec++;
        else
            free(ui_pk_rec[UI_PK_NREC - 1]);
        at = ui_pk_nrec - 1;
        ui_pk_rec[at] = strdup(dir);
    }
    for (i = at; i > 0; i--) {                  /* to the front */
        char *t = ui_pk_rec[i];

        ui_pk_rec[i] = ui_pk_rec[i - 1];
        ui_pk_rec[i - 1] = t;
    }
    ui_pk_rec_save();
    ui_pk_tree_recents();
}

/* The Recent part of the tree, made again (between the places and the drives) */
static void ui_pk_tree_recents(void)
{
    int i, at;

    for (i = ui_pk_ntn - 1; i >= 0; i--)
        if (ui_pk_tn[i].grp == 2) {
            ui_pk_tn_free(&ui_pk_tn[i]);
            memmove(&ui_pk_tn[i], &ui_pk_tn[i + 1], (ui_pk_ntn - i - 1) * sizeof(*ui_pk_tn));
            ui_pk_ntn--;
        }
    for (at = 0; at < ui_pk_ntn && ui_pk_tn[at].grp != 1; at++)
        ;
    if (ui_pk_nrec > 0 && ui_pk_tn_insert(at, "Recent", "", NULL, 0, 2, 2))
        at++;
    for (i = 0; i < ui_pk_nrec; i++) {
        struct stat st;
        const char *base = strrchr(ui_pk_rec[i], '/');

        if (stat(ui_pk_rec[i], &st) != 0 || !S_ISDIR(st.st_mode))
            continue;                           /* gone */
        if (ui_pk_tn_insert(at, base && base[1] ? base + 1 : ui_pk_rec[i], ui_pk_rec[i], NULL, 0, 0, 2))
            at++;
    }
}

/* The tree opens down to the open folder and scrolls to it */
static void ui_pk_tree_reveal(void)
{
    int i, best = -1, cur, guard = 0;
    size_t bl = 0;

    for (i = 0; i < ui_pk_ntn; i++) {
        UiPkNode *n = &ui_pk_tn[i];

        if (n->depth == 0 && n->kind == 0 && n->grp != 2 && n->path[0] && ui_pk_under(ui_pk_dir, n->path) && strlen(n->path) >= bl) {
            best = i;
            bl = strlen(n->path);
        }
    }
    if (best < 0)
        return;
    cur = best;
    while (strcmp(ui_pk_tn[cur].path, ui_pk_dir) && guard++ < 40) {
        int j, found = -1;

        if (!ui_pk_tn[cur].open)
            ui_pk_tree_open(cur);
        if (!ui_pk_tn[cur].open)
            break;
        for (j = cur + 1; j < ui_pk_ntn && ui_pk_tn[j].depth > ui_pk_tn[cur].depth; j++)
            if (ui_pk_tn[j].depth == ui_pk_tn[cur].depth + 1 && ui_pk_under(ui_pk_dir, ui_pk_tn[j].path)) {
                found = j;
                break;
            }
        if (found < 0)
            break;
        cur = found;
    }
    ui_pk_tree_show = cur;
}

/* Work that waits for the main loop: a new list of drives, a drive that has been mounted, and the search */
static void ui_pk_scan_tick(VideoState *is)
{
    int st;

    if (!ui_pk_open)
        return;
    if (SDL_AtomicGet(&ui_pk_dev_state) == 2) {
        if (ui_pk_dev_tmpn != ui_pk_ndev || memcmp(ui_pk_dev_tmp, ui_pk_dev, sizeof(UiPkDev) * ui_pk_ndev)) {
            memcpy(ui_pk_dev, ui_pk_dev_tmp, sizeof(UiPkDev) * ui_pk_dev_tmpn);
            ui_pk_ndev = ui_pk_dev_tmpn;
            ui_pk_tree_devs();
            if (is)
                is->force_refresh = 1;
        }
        SDL_AtomicSet(&ui_pk_dev_state, 0);
    } else if (SDL_AtomicGet(&ui_pk_dev_state) == 0 && av_gettime_relative() > ui_pk_dev_next) {
        ui_pk_dev_start();
    }
    st = SDL_AtomicGet(&ui_pk_mnt_state);
    if (st >= 2) {
        SDL_AtomicSet(&ui_pk_mnt_state, 0);
        if (st == 2 && !ui_pk_mnt_op) {
            ui_pk_go(ui_pk_mnt_path);
            snprintf(ui_pk_note, sizeof(ui_pk_note), "%.80s is mounted", ui_pk_mnt_name);
        } else if (st == 2) {
            snprintf(ui_pk_note, sizeof(ui_pk_note), "%.80s can be unplugged now", ui_pk_mnt_name);
        } else {
            snprintf(ui_pk_note, sizeof(ui_pk_note), "Could not %s %.60s: %.100s", ui_pk_mnt_op ? "unmount" : "mount", ui_pk_mnt_name, ui_pk_mnt_msg);
        }
        if (st == 2)
            ui_pk_dev_next = 0;                 /* read the list of drives again now */
        ui_pk_note_until = av_gettime_relative() + 6000000;
        if (is)
            is->force_refresh = 1;
    }
    if (ui_pk_thumb_tick() && is)
        is->force_refresh = 1;
    if (ui_pk_scan_on) {
        ui_pk_search_tick();
        if (is)
            is->force_refresh = 1;
    }
}

/* 1 while something in the picker still moves or is being found, so the picture goes on being drawn */
static int ui_pk_busy(void)
{
    return ui_pk_open && (ui_pk_scan_on || ui_pk_goal >= 0.0 || SDL_AtomicGet(&ui_pk_mnt_state) == 1 || av_gettime_relative() < ui_pk_note_until ||
                          ui_pk_reveal || ui_pk_th_fading);
}

static const char *ui_pk_title(void)
{
    return ui_pk_mode == 2 ? "Add to Queue" : "Open Media";
}

static const char *ui_pk_sortname(void)
{
    return ui_pk_sortk == 1 ? "Modified" : ui_pk_sortk == 2 ? "Size" : "Name";
}

static void ui_pk_layout(int ww, int wh, UiPkLay *L)
{
    int bw = 32, bh = 32, by, tw;

    L->p.w = FFMIN(av_clip(ww - 40, 360, 1020), ww - 8);
    L->p.h = FFMIN(av_clip(wh - 40, 300, 680), wh - 8);
    L->p.x = (ww - L->p.w) / 2;
    L->p.y = FFMAX((wh - L->p.h) / 2, 4);
    L->side_on = L->p.w >= 660;
    L->sbox_on = ui_pk_filter[0] || ui_pk_search_on;
    L->top.x = L->p.x;
    L->top.y = L->p.y;
    L->top.w = L->p.w;
    L->top.h = UI_PK_TOP;
    L->side.x = L->p.x;
    L->side.y = L->p.y + UI_PK_TOP;
    L->side.w = L->side_on ? UI_PK_SIDE : 0;
    L->side.h = L->p.h - UI_PK_TOP - UI_PK_FOOT;
    L->list.x = L->p.x + L->side.w;
    L->list.y = L->p.y + UI_PK_TOP + (L->sbox_on ? UI_PK_SBOX : 0);
    L->list.w = L->p.w - L->side.w;
    L->list.h = L->p.h - UI_PK_TOP - UI_PK_FOOT - (L->sbox_on ? UI_PK_SBOX : 0);
    L->sbox.x = L->list.x + 14;
    L->sbox.y = L->p.y + UI_PK_TOP + 6;
    L->sbox.w = L->list.w - 28;
    L->sbox.h = UI_PK_SBOX - 12;

    by = L->p.y + (UI_PK_TOP - bh) / 2;
    L->back.x = L->p.x + 14;
    L->fwd.x = L->back.x + bw + 2;
    L->upb.x = L->fwd.x + bw + 2;
    L->back.y = L->fwd.y = L->upb.y = by;
    L->back.w = L->fwd.w = L->upb.w = bw;
    L->back.h = L->fwd.h = L->upb.h = bh;
    L->closeb.x = L->p.x + L->p.w - 14 - bw;
    L->srchb.x = L->closeb.x - bw - 2;
    L->gridb.x = L->srchb.x - bw - 2;
    L->closeb.y = L->srchb.y = L->gridb.y = by;
    L->closeb.w = L->srchb.w = L->gridb.w = bw;
    L->closeb.h = L->srchb.h = L->gridb.h = bh;
    L->sort_on = L->p.w >= 560;
    L->sortb.w = ui_text_width("Modified", 15) + 44;
    L->sortb.h = bh;
    L->sortb.y = by;
    L->sortb.x = L->gridb.x - 6 - L->sortb.w;
    L->title_on = L->p.w >= 780;
    tw = ui_text_width(ui_pk_title(), 20);
    L->crumbs.x = L->upb.x + bw + (L->title_on ? 18 + tw + 20 : 12);
    L->crumbs.y = by;
    L->crumbs.h = bh;
    L->crumbs.w = (L->sort_on ? L->sortb.x : L->gridb.x) - 10 - L->crumbs.x;

    L->ok.w = 124;
    L->ok.h = 38;
    L->ok.x = L->p.x + L->p.w - 20 - L->ok.w;
    L->ok.y = L->p.y + L->p.h - UI_PK_FOOT + (UI_PK_FOOT - 38) / 2;
    L->extra = L->ok;
    L->extra.w = ui_pk_mode == 2 ? (L->p.w >= 740 ? 150 : 96) : 104;
    L->extra.x = L->ok.x - 10 - L->extra.w;
    L->tog = L->p.w >= 900;
    L->all.x = L->p.x + 20 + 330;
    L->all.y = L->ok.y;
    L->all.w = ui_text_width("All files: Off", 15) + 10;
    L->all.h = 38;
    L->hid = L->all;
    L->hid.x = ui_pk_mode != 1 ? L->all.x + L->all.w + 14 : L->all.x;
    L->hid.w = ui_text_width("Hidden: Off", 15) + 10;
}

static int ui_pk_ticked(int64_t *bytes)
{
    int i, n = 0;

    if (bytes)
        *bytes = 0;
    for (i = 0; i < ui_pk_n; i++)
        if (ui_pk_e[i].sel) {
            n++;
            if (bytes)
                *bytes += ui_pk_e[i].size;
        }
    for (i = 0; i < ui_pk_nx; i++)
        if (ui_pk_x[i].sel) {
            n++;
            if (bytes)
                *bytes += ui_pk_x[i].size;
        }
    return n;
}

static void ui_pk_send(VideoState *is, char what, const char *path)
{
    struct stat st;

    (void)is;
    ui_inbox_send(what, path);
    if ((what == 'o' || what == 'a') && stat(path, &st) == 0) {         /* v51: the folder it came from is a recent place */
        char dir[PATH_MAX + 300], *slash;

        snprintf(dir, sizeof(dir), "%s", path);
        if (!S_ISDIR(st.st_mode) && (slash = strrchr(dir, '/')))
            slash[slash == dir ? 1 : 0] = 0;
        ui_pk_rec_add(dir);
    }
}

static void ui_pk_enter(const UiPkEnt *e)       /* go into a folder */
{
    char path[PATH_MAX + 300];

    ui_pk_path_of(e, path, sizeof(path));
    ui_pk_go(path);
}

/* The main button (right end of the foot):
   Open File: Open for a folder, Play for a file. Open Folder: Play (the selected folder, or the open one). Add to Queue: Add. */
static void ui_pk_do_ok(VideoState *is)
{
    char path[PATH_MAX + 300];
    UiPkEnt *e = ui_pk_cur_ent();
    int i, sent = 0;

    if (ui_pk_mode == 1) {
        if (e && e->dir && ui_pk_touched)
            ui_pk_path_of(e, path, sizeof(path));
        else
            snprintf(path, sizeof(path), "%s", ui_pk_dir);
        ui_pk_send(is, 'o', path);
        ui_pk_close(is);
    } else if (ui_pk_mode == 2) {
        for (i = 0; i < ui_pk_n; i++)
            if (ui_pk_e[i].sel) {
                ui_pk_path_of(&ui_pk_e[i], path, sizeof(path));
                ui_pk_send(is, 'a', path);
                sent++;
            }
        for (i = 0; i < ui_pk_nx; i++)
            if (ui_pk_x[i].sel) {
                ui_pk_path_of(&ui_pk_x[i], path, sizeof(path));
                ui_pk_send(is, 'a', path);
                sent++;
            }
        if (!sent && e && !e->dir) {
            ui_pk_path_of(e, path, sizeof(path));
            ui_pk_send(is, 'a', path);
            sent = 1;
        }
        if (sent)
            ui_pk_close(is);
    } else if (e) {
        if (e->dir) {
            ui_pk_enter(e);
        } else {
            ui_pk_path_of(e, path, sizeof(path));
            ui_pk_send(is, 'o', path);
            ui_pk_close(is);
        }
    }
}

/* The button next to it: Open (Open Folder: goes into the selected folder) or Add this folder (Add to Queue) */
static void ui_pk_do_extra(VideoState *is)
{
    char path[PATH_MAX + 300];
    UiPkEnt *e = ui_pk_cur_ent();

    if (ui_pk_mode == 1) {
        if (e && e->dir)
            ui_pk_enter(e);
    } else if (ui_pk_mode == 2) {
        if (e && e->dir && ui_pk_touched)
            ui_pk_path_of(e, path, sizeof(path));
        else
            snprintf(path, sizeof(path), "%s", ui_pk_dir);
        ui_pk_send(is, 'a', path);
        ui_pk_close(is);
    }
}

/* Enter, or a double click: a folder is entered, a file is played (or added) */
static void ui_pk_activate(VideoState *is)
{
    UiPkEnt *e = ui_pk_cur_ent();

    if (!e)
        return;
    if (e->dir)
        ui_pk_enter(e);
    else
        ui_pk_do_ok(is);
}

static void ui_pk_tick_row(int row)
{
    UiPkEnt *e = ui_pk_ent(row);

    if (e && ui_pk_mode == 2 && !e->dir)
        e->sel ^= 1;
}

/* ----- the menus: a row (right click: Play now, Play next, Add to queue; a folder: Open folder, Play folder, ...) and Sort ----- */
enum { UI_PK_A_PLAY, UI_PK_A_ADD, UI_PK_A_ENTER, UI_PK_A_NEXT, UI_PK_A_SORT = 10 };
static int ui_pk_cm_kind = 0, ui_pk_cm_x = 0, ui_pk_cm_y = 0, ui_pk_cm_n = 0, ui_pk_cm_hot = -1, ui_pk_cm_w = 230;
static int ui_pk_cm_act[4];
static char ui_pk_cm_lab[4][24], ui_pk_cm_path[PATH_MAX + 300], ui_pk_cm_nm[200];

static SDL_Rect ui_pk_cm_rect(void)
{
    SDL_Rect r;
    int ww, wh;

    SDL_GetWindowSize(window, &ww, &wh);
    r.w = ui_pk_cm_w;
    r.h = ui_pk_cm_n * 36 + 12;
    r.x = av_clip(ui_pk_cm_x, 4, FFMAX(ww - r.w - 4, 4));
    r.y = av_clip(ui_pk_cm_y, 4, FFMAX(wh - r.h - 4, 4));
    return r;
}

static void ui_pk_cm_item(const char *label, int act)
{
    snprintf(ui_pk_cm_lab[ui_pk_cm_n], 24, "%s", label);
    ui_pk_cm_act[ui_pk_cm_n++] = act;
}

static void ui_pk_cm_start(int row, int x, int y)
{
    UiPkEnt *e = ui_pk_ent(row);

    if (!e)
        return;
    ui_pk_path_of(e, ui_pk_cm_path, sizeof(ui_pk_cm_path));
    snprintf(ui_pk_cm_nm, sizeof(ui_pk_cm_nm), "%s", e->name);
    ui_pk_cm_kind = 0;
    ui_pk_cm_w = 230;
    ui_pk_cm_x = x;
    ui_pk_cm_y = y;
    ui_pk_cm_n = 0;
    ui_pk_cm_hot = -1;
    if (e->dir) {
        ui_pk_cm_item("Open folder", UI_PK_A_ENTER);
        ui_pk_cm_item("Play folder", UI_PK_A_PLAY);
        ui_pk_cm_item("Play folder next", UI_PK_A_NEXT);
        ui_pk_cm_item("Add folder to queue", UI_PK_A_ADD);
    } else {
        ui_pk_cm_item("Play now", UI_PK_A_PLAY);
        ui_pk_cm_item("Play next", UI_PK_A_NEXT);
        ui_pk_cm_item("Add to queue", UI_PK_A_ADD);
    }
    ui_pk_cur = row;
    ui_pk_touched = 1;
    ui_pk_cm_open = 1;
}

static void ui_pk_sort_menu(const UiPkLay *L)
{
    ui_pk_cm_kind = 1;
    ui_pk_cm_w = 180;
    ui_pk_cm_x = L->sortb.x + L->sortb.w - ui_pk_cm_w;
    ui_pk_cm_y = L->sortb.y + L->sortb.h + 4;
    ui_pk_cm_n = 0;
    ui_pk_cm_hot = -1;
    ui_pk_cm_item("Name", UI_PK_A_SORT);
    ui_pk_cm_item("Modified", UI_PK_A_SORT + 1);
    ui_pk_cm_item("Size", UI_PK_A_SORT + 2);
    ui_pk_cm_open = 1;
}

static void ui_pk_set_sort(int k)
{
    if (k == ui_pk_sortk) {
        ui_pk_desc = !ui_pk_desc;               /* the one that is on: the other way round */
    } else {
        ui_pk_sortk = k;
        ui_pk_desc = k != 0;                    /* the newest and the biggest first, names from A */
    }
    cfg_pk_sort = ui_pk_sortk;
    cfg_pk_desc = ui_pk_desc;
    settings_save();
    ui_pk_resort();
}

static void ui_pk_cm_do(VideoState *is, int act)
{
    char name[sizeof(ui_pk_cm_nm)];

    ui_pk_cm_open = 0;
    if (act >= UI_PK_A_SORT) {
        ui_pk_set_sort(act - UI_PK_A_SORT);
        return;
    }
    snprintf(name, sizeof(name), "%s", ui_pk_cm_nm);
    if (act == UI_PK_A_ENTER) {
        ui_pk_go(ui_pk_cm_path);
    } else if (act == UI_PK_A_PLAY) {
        ui_pk_send(is, 'o', ui_pk_cm_path);
        ui_pk_close(is);
    } else if (act == UI_PK_A_NEXT) {           /* v48: the picker stays open, like for Add */
        ui_pk_send(is, 'n', ui_pk_cm_path);
        snprintf(ui_pk_note, sizeof(ui_pk_note), "Plays next: %.120s", name);
        ui_pk_note_until = av_gettime_relative() + 2500000;
    } else {
        ui_pk_send(is, 'a', ui_pk_cm_path);     /* the picker stays open: more can be added */
        snprintf(ui_pk_note, sizeof(ui_pk_note), "Added: %.120s", name);
        ui_pk_note_until = av_gettime_relative() + 2500000;
    }
}

static void ui_pk_cm_draw(void)
{
    SDL_Rect r;
    int i;

    if (!ui_pk_cm_open)
        return;
    r = ui_pk_cm_rect();
    ui_glass(&r, 16);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    for (i = 0; i < ui_pk_cm_n; i++) {
        SDL_Rect row = { r.x + 6, r.y + 6 + i * 36, r.w - 12, 34 };
        int on = ui_pk_cm_kind == 1 && ui_pk_cm_act[i] - UI_PK_A_SORT == ui_pk_sortk;

        if (i == ui_pk_cm_hot) {
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 34);
            ui_pill(&row);
        }
        ui_label(row.x + 14, row.y + row.h / 2, ui_pk_cm_lab[i], 16, 245, 245, 245, i == ui_pk_cm_hot || on ? 255 : 215);
        if (on)
            ui_icon(ui_pk_desc ? UI_IC_CHEV_D : UI_IC_CHEV_U, row.x + row.w - 28, row.y + row.h / 2, 16, av_clip(cfg_bar_r + 70, 0, 255),
                    av_clip(cfg_bar_g + 70, 0, 255), av_clip(cfg_bar_b + 70, 0, 255), 255);
    }
}

static int ui_pk_in(const SDL_Rect *r, int x, int y)
{
    return x >= r->x && x < r->x + r->w && y >= r->y && y < r->y + r->h;
}

static void ui_pk_button(const SDL_Rect *r, const char *label, int hot, int primary, int enabled)
{
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    if (primary)
        SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r, 0, 255), av_clip(cfg_bar_g, 0, 255), av_clip(cfg_bar_b, 0, 255),
                               !enabled ? 110 : hot ? 255 : 215);
    else
        SDL_SetRenderDrawColor(renderer, 255, 255, 255, !enabled ? 14 : hot ? 60 : 30);
    ui_pill(r);
    ui_label_c(r->x + r->w / 2, r->y + r->h / 2, label, 16, 245, 245, 245, enabled ? 255 : 120);
}

/* A round button with an icon in the top bar */
static void ui_pk_ibtn(const SDL_Rect *r, int icon, int hot, int on, int alpha)
{
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    if (on) {
        SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r, 0, 255), av_clip(cfg_bar_g, 0, 255), av_clip(cfg_bar_b, 0, 255), 110);
        ui_pill(r);
    } else if (hot && alpha > 120) {
        SDL_SetRenderDrawColor(renderer, 255, 255, 255, 32);
        ui_pill(r);
    }
    ui_icon(icon, r->x + (r->w - 20) / 2, r->y + r->h / 2, 20, 245, 245, 245, alpha);
}

/* The text of the foot: how many items are here, or what is selected and how big it is */
static void ui_pk_status(char *out, size_t size, int maxw)
{
    int64_t bytes;
    int nt = ui_pk_ticked(&bytes), i, res = 0;
    UiPkEnt *e = ui_pk_touched ? ui_pk_cur_ent() : NULL;
    char sz[40], nm[PATH_MAX];

    if (ui_pk_filter[0]) {
        for (i = 0; i < ui_pk_nrw; i++)
            res += ui_pk_rw[i].kind != 2;
        snprintf(out, size, "%d result%s%s", res, res == 1 ? "" : "s", ui_pk_scan_on ? ", still looking ..." : "");
    } else if (nt > 0) {
        ui_pk_size_str(bytes, sz, sizeof(sz));
        snprintf(out, size, "%d selected (%s)", nt, sz);
    } else if (e) {
        if (e->dir) {
            if (e->count < 0) {
                char path[PATH_MAX + 300];

                ui_pk_path_of(e, path, sizeof(path));
                e->count = ui_pk_count_dir(path);
            }
            snprintf(sz, sizeof(sz), "%d item%s", e->count, e->count == 1 ? "" : "s");
        } else {
            ui_pk_size_str(e->size, sz, sizeof(sz));
        }
        snprintf(nm, sizeof(nm), "%s", e->name);
        ui_fit_text(nm, 15, FFMAX(maxw - ui_text_width(" selected (000.0 kB)", 15) - 10, 40));
        snprintf(out, size, "\"%s\" selected (%s)", nm, sz);
    } else {
        snprintf(out, size, "%d item%s", ui_pk_n, ui_pk_n == 1 ? "" : "s");
    }
    ui_fit_text(out, 15, maxw);
}

static void ui_pk_loc_str(const UiPkEnt *e, char *out, size_t size)   /* the folder of a search result, with ~ for the home folder */
{
    const char *home = getenv("HOME"), *w = e->where ? e->where : ui_pk_dir;
    size_t hl = home ? strlen(home) : 0;

    if (hl > 1 && !strncmp(w, home, hl) && (w[hl] == '/' || !w[hl]))
        snprintf(out, size, "~%s", w + hl);
    else
        snprintf(out, size, "%s", w);
}

static int ui_pk_first_vis(void)                /* the first row that is (partly) in view */
{
    int lo = 0, hi = ui_pk_nrw;

    while (lo < hi) {
        int mid = (lo + hi) / 2;

        if (ui_pk_rw[mid].r.y + ui_pk_rw[mid].r.h > (int)ui_pk_sc)
            hi = mid;
        else
            lo = mid + 1;
    }
    return lo;
}

static void ui_pk_draw(void)
{
    UiPkLay L;
    SDL_Rect r, clip;
    char buf[PATH_MAX + 96], tmp[PATH_MAX + 96];
    int ww, wh, i, mx = 0, my = 0, x, cy, cols_size, cols_mod, cols_loc, ar, ag, ab;
    int64_t cbud;
    time_t now = time(NULL);

    if (!ui_pk_open)
        return;
    SDL_GetWindowSize(window, &ww, &wh);
    ui_pk_layout(ww, wh, &L);
    ui_pk_relayout(&L);
    ui_pk_clamp_scroll(&L);
    if (ui_pk_reveal) {
        ui_pk_reveal = 0;
        ui_pk_show_cursor(&L);
        ui_pk_clamp_scroll(&L);
    }
    {                                           /* v48: smooth scrolling, like the list queue */
        static int64_t last = 0;
        static double prev = -1.0;
        int64_t tnow = av_gettime_relative();
        double dt = tnow - last > 100000 ? 0.016 : (tnow - last) / 1000000.0;

        last = tnow;
        if (ui_pk_goal >= 0.0 && ui_pk_sc != prev)
            ui_pk_goal = -1.0;                  /* a key, a click or a new folder moved the list: let it be */
        if (ui_pk_goal >= 0.0) {
            ui_pk_sc += (ui_pk_goal - ui_pk_sc) * (1.0 - exp(-dt / 0.08));
            if (fabs(ui_pk_goal - ui_pk_sc) < 0.5) {
                ui_pk_sc = ui_pk_goal;
                ui_pk_goal = -1.0;
            }
        }
        prev = ui_pk_sc;
    }
    ar = av_clip(cfg_bar_r, 0, 255);
    ag = av_clip(cfg_bar_g, 0, 255);
    ab = av_clip(cfg_bar_b, 0, 255);
    ui_glass(&L.p, 28);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    SDL_GetMouseState(&mx, &my);
    if (ui_pk_cm_open)
        mx = my = -1000;                        /* the menu has the mouse: nothing under it lights up */

    /* ---- the top bar: back, forward, up, the title, the path, Sort, list or grid, search, close ---- */
    ui_pk_ibtn(&L.back, UI_IC_ARR_L, ui_pk_hbtn == 20, 0, ui_pk_hi > 0 ? 255 : 90);
    ui_pk_ibtn(&L.fwd, UI_IC_ARR_R, ui_pk_hbtn == 21, 0, ui_pk_hi >= 0 && ui_pk_hi < ui_pk_hn - 1 ? 255 : 90);
    ui_pk_ibtn(&L.upb, UI_IC_ARR_U, ui_pk_hbtn == 22, 0, strcmp(ui_pk_dir, "/") ? 255 : 90);
    if (L.title_on)
        ui_label(L.upb.x + L.upb.w + 18, L.top.y + UI_PK_TOP / 2, ui_pk_title(), 20, 245, 245, 245, 255);
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, ui_pk_loc_on ? 34 : 16);                    /* the path sits in a soft pill, like the path bar of Files */
    ui_pill(&L.crumbs);
    ui_pk_ncrumb = 0;
    if (ui_pk_loc_on) {                         /* v51: Ctrl+L: the path is typed */
        const char *s = ui_pk_loc;
        int avail = L.crumbs.w - 40, tw;

        while (*s && ui_text_width(s, 16) > avail) {
            s++;
            while ((*s & 0xC0) == 0x80)
                s++;
        }
        tw = ui_text_width(s, 16);
        ui_label(L.crumbs.x + 18, L.crumbs.y + L.crumbs.h / 2, s, 16, 245, 245, 245, 255);
        if ((av_gettime_relative() / 500000) % 2 == 0) {
            SDL_SetRenderDrawColor(renderer, 245, 245, 245, 220);
            SDL_RenderDrawLine(renderer, L.crumbs.x + 20 + tw, L.crumbs.y + 7, L.crumbs.x + 20 + tw, L.crumbs.y + L.crumbs.h - 7);
        }
    } else {

        const char *home = getenv("HOME");
        int hl = home ? (int)strlen(home) : 0, starts_home = hl > 1 && !strncmp(ui_pk_dir, home, hl) &&
                 (ui_pk_dir[hl] == '/' || !ui_pk_dir[hl]);
        struct { char label[PATH_MAX]; int upto; } seg[64];
        int ns = 0, pos, sw, total, from = 0, avail = L.crumbs.w - 28, len = (int)strlen(ui_pk_dir);
        const int gap = 28;

        if (starts_home) {
            snprintf(seg[ns].label, sizeof(seg[0].label), "Home");
            seg[ns++].upto = hl;
            pos = hl;
        } else {
            snprintf(seg[ns].label, sizeof(seg[0].label), "Computer");
            seg[ns++].upto = 0;
            pos = 0;
        }
        while (pos < len && ns < 63) {
            int s0, s1;

            while (pos < len && ui_pk_dir[pos] == '/')
                pos++;
            s0 = pos;
            while (pos < len && ui_pk_dir[pos] != '/')
                pos++;
            s1 = pos;
            if (s1 > s0) {
                snprintf(seg[ns].label, sizeof(seg[0].label), "%.*s", FFMIN(s1 - s0, 300), ui_pk_dir + s0);
                seg[ns++].upto = s1;
            }
        }
        total = 0;
        for (i = 0; i < ns; i++)
            total += ui_text_width(seg[i].label, 16) + gap;
        for (from = 0; from < ns - 1 && total > avail; from++)
            total -= ui_text_width(seg[from].label, 16) + gap;
        x = L.crumbs.x + 16;
        cy = L.crumbs.y + L.crumbs.h / 2;
        if (from > 0) {
            ui_label(x, cy, "...", 16, 170, 170, 170, 255);
            x += ui_text_width("...", 16) + gap;
        }
        for (i = from; i < ns; i++) {
            int last_seg = i == ns - 1;

            snprintf(tmp, sizeof(tmp), "%s", seg[i].label);
            ui_fit_text(tmp, 16, FFMAX(avail - (x - L.crumbs.x - 16), 60));
            sw = ui_text_width(tmp, 16);
            if (ui_pk_ncrumb < 24) {
                ui_pk_crumb[ui_pk_ncrumb].r.x = x - 4;
                ui_pk_crumb[ui_pk_ncrumb].r.y = L.crumbs.y + 2;
                ui_pk_crumb[ui_pk_ncrumb].r.w = sw + 8;
                ui_pk_crumb[ui_pk_ncrumb].r.h = L.crumbs.h - 4;
                ui_pk_crumb[ui_pk_ncrumb].upto = seg[i].upto;
                ui_pk_ncrumb++;
            }
            ui_label(x, cy, tmp, 16, 245, 245, 245, last_seg ? 255 : 190);
            x += sw;
            if (!last_seg) {
                ui_icon(UI_IC_CHEV_R, x + 7, cy, 14, 150, 150, 150, 255);
                x += gap;
            }
        }
    }
    if (L.sort_on) {
        if (ui_pk_hbtn == 23 || (ui_pk_cm_open && ui_pk_cm_kind == 1)) {
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 28);
            ui_pill(&L.sortb);
        }
        ui_label(L.sortb.x + 16, L.sortb.y + L.sortb.h / 2, ui_pk_sortname(), 15, av_clip(ar + 70, 0, 255), av_clip(ag + 70, 0, 255),
                 av_clip(ab + 70, 0, 255), 255);
        ui_icon(ui_pk_desc ? UI_IC_CHEV_D : UI_IC_CHEV_U, L.sortb.x + L.sortb.w - 28, L.sortb.y + L.sortb.h / 2, 14, 190, 190, 190, 255);
    }
    ui_pk_ibtn(&L.gridb, ui_pk_grid ? UI_IC_LIST : UI_IC_GRID, ui_pk_hbtn == 24, 0, 255);
    ui_pk_ibtn(&L.srchb, UI_IC_SEARCH, ui_pk_hbtn == 25, L.sbox_on, 255);
    ui_pk_ibtn(&L.closeb, UI_IC_X, ui_pk_hbtn == 26, 0, 255);
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 26);
    SDL_RenderDrawLine(renderer, L.p.x + 12, L.p.y + UI_PK_TOP, L.p.x + L.p.w - 12, L.p.y + UI_PK_TOP);

    /* ---- the folder tree ---- */
    if (L.side_on) {
        double smax = FFMAX(0.0, ui_pk_ntn * (double)UI_PK_TROW + 12 - L.side.h);

        if (ui_pk_tree_show >= 0) {             /* v51: scroll to a node the tree opened down to */
            double ty = ui_pk_tree_show * (double)UI_PK_TROW;

            if (ty < ui_pk_ssc)
                ui_pk_ssc = ty;
            else if (ty + UI_PK_TROW + 12 > ui_pk_ssc + L.side.h)
                ui_pk_ssc = ty + UI_PK_TROW + 12 - L.side.h;
            ui_pk_tree_show = -1;
        }
        ui_pk_ssc = av_clipd(ui_pk_ssc, 0.0, smax);
        SDL_SetRenderDrawColor(renderer, 0, 0, 0, 55);
        SDL_RenderFillRect(renderer, &L.side);
        clip = L.side;
        SDL_RenderSetClipRect(renderer, &clip);
        for (i = 0; i < ui_pk_ntn; i++) {
            UiPkNode *nd = &ui_pk_tn[i];
            int ry = L.side.y + 6 + i * UI_PK_TROW - (int)ui_pk_ssc, ix, on, mounted = nd->kind == 0;

            if (ry + UI_PK_TROW < L.side.y || ry > L.side.y + L.side.h)
                continue;
            ix = L.side.x + 10 + nd->depth * 14;
            if (nd->kind == 2) {                /* the heading */
                ui_label(L.side.x + 18, ry + UI_PK_TROW / 2 + 4, nd->name, 13, 150, 150, 150, 255);
                continue;
            }
            on = mounted && nd->path[0] && !strcmp(nd->path, ui_pk_dir);
            r.x = L.side.x + 6;
            r.y = ry + 1;
            r.w = L.side.w - 12;
            r.h = UI_PK_TROW - 2;
            if (on || i == ui_pk_hnode) {
                SDL_SetRenderDrawColor(renderer, on ? ar : 255, on ? ag : 255, on ? ab : 255, on ? 90 : 28);
                ui_pill(&r);
            }
            if (mounted && nd->kids != 0)
                ui_icon(nd->open ? UI_IC_CHEV_D : UI_IC_CHEV_R, ix, ry + UI_PK_TROW / 2, 14, 200, 200, 200, 255);
            ui_icon(UI_IC_FOLDER, ix + 18, ry + UI_PK_TROW / 2, 16, 245, 245, 245, mounted ? (on ? 255 : 210) : 120);
            snprintf(tmp, sizeof(tmp), "%s", nd->name);
            ui_fit_text(tmp, 15, L.side.w - (ix - L.side.x) - 18 - 34 - (nd->kind == 1 ? 50 : 0) - (nd->grp == 1 && nd->dev && nd->kind == 0 && nd->depth == 0 ? 30 : 0));
            ui_label(ix + 40, ry + UI_PK_TROW / 2, tmp, 15, 245, 245, 245, mounted ? (on ? 255 : 220) : 150);
            if (nd->grp == 1 && nd->dev && nd->kind == 0 && nd->depth == 0)         /* v51: a mounted drive can be unmounted */
                ui_icon(UI_IC_EJECT, L.side.x + L.side.w - 32, ry + UI_PK_TROW / 2, 16, 245, 245, 245, i == ui_pk_hnode ? 255 : 110);
            if (nd->kind == 1)
                ui_label(L.side.x + L.side.w - 14 - ui_text_width("Mount", 12), ry + UI_PK_TROW / 2, "Mount", 12, 170, 170, 170,
                         i == ui_pk_hnode ? 255 : 150);
        }
        SDL_RenderSetClipRect(renderer, NULL);
        SDL_SetRenderDrawColor(renderer, 255, 255, 255, 26);
        SDL_RenderDrawLine(renderer, L.side.x + L.side.w, L.side.y, L.side.x + L.side.w, L.side.y + L.side.h);
    }

    /* ---- the search box ---- */
    if (L.sbox_on) {
        int tw;

        SDL_SetRenderDrawColor(renderer, 255, 255, 255, 22);
        ui_pill(&L.sbox);
        ui_icon(UI_IC_SEARCH, L.sbox.x + 12, L.sbox.y + L.sbox.h / 2, 18, 200, 200, 200, 255);
        if (ui_pk_filter[0]) {
            snprintf(tmp, sizeof(tmp), "%s", ui_pk_filter);
            ui_fit_text(tmp, 17, L.sbox.w - 70);
            tw = ui_text_width(tmp, 17);
            ui_label(L.sbox.x + 40, L.sbox.y + L.sbox.h / 2, tmp, 17, 245, 245, 245, 255);
            if ((av_gettime_relative() / 500000) % 2 == 0) {
                SDL_SetRenderDrawColor(renderer, 245, 245, 245, 220);
                SDL_RenderDrawLine(renderer, L.sbox.x + 42 + tw, L.sbox.y + 9, L.sbox.x + 42 + tw, L.sbox.y + L.sbox.h - 9);
            }
        } else {
            ui_label(L.sbox.x + 40, L.sbox.y + L.sbox.h / 2, "Type to search here, below and elsewhere", 16, 150, 150, 150, 255);
        }
    }

    /* ---- the list, or the grid ---- */
    clip = L.list;
    SDL_RenderSetClipRect(renderer, &clip);
    cols_size = L.list.w >= 420;
    cols_mod = L.list.w >= 640 && !ui_pk_filter[0];
    cols_loc = L.list.w >= 560 && ui_pk_filter[0];
    cbud = av_gettime_relative() + 3000;
    ui_pk_thumb_begin();
    for (i = ui_pk_first_vis(); i < ui_pk_nrw; i++) {
        UiPkRow *w = &ui_pk_rw[i];
        const UiPkEnt *e;
        int sx = L.list.x + w->r.x, sy = L.list.y + w->r.y - (int)ui_pk_sc, tx, right, shown;

        if (w->r.y > ui_pk_sc + L.list.h)
            break;
        if (w->kind == 2) {                     /* a section heading */
            int nn = 0, k;

            for (k = i + 1; k < ui_pk_nrw && ui_pk_rw[k].kind != 2; k++)
                nn++;
            snprintf(tmp, sizeof(tmp), "%s", ui_pk_sect_name[w->idx]);
            ui_label(sx + 18, sy + UI_PK_HDR / 2 + 3, tmp, 14, av_clip(ar + 70, 0, 255), av_clip(ag + 70, 0, 255), av_clip(ab + 70, 0, 255), 255);
            snprintf(tmp, sizeof(tmp), "%d", nn);
            ui_label(sx + 18 + ui_text_width(ui_pk_sect_name[w->idx], 14) + 10, sy + UI_PK_HDR / 2 + 3, tmp, 13, 150, 150, 150, 255);
            continue;
        }
        e = ui_pk_ent(i);
        if (!e)
            continue;
        if (e->dir && e->count < 0 && av_gettime_relative() < cbud) {
            char path[PATH_MAX + 300];

            ui_pk_path_of(e, path, sizeof(path));
            ((UiPkEnt *)e)->count = ui_pk_count_dir(path);
        }
        if (ui_pk_grid) {                       /* a tile: the icon, the name, and how many items or how big */
            SDL_Rect t = { sx + 4, sy + 4, w->r.w - 8, UI_PK_TILE_H - 8 };
            SDL_Rect box = { t.x + (t.w - 112) / 2, t.y + 8, 112, 63 };
            int rr = (int)(14 * ui_round_k()), has;

            if (i == ui_pk_cur && ui_pk_touched) {
                SDL_SetRenderDrawColor(renderer, ar, ag, ab, 85);
                ui_rr_fill(&t, rr);
            } else if (i == ui_pk_hrow || i == ui_pk_cur) {
                SDL_SetRenderDrawColor(renderer, 255, 255, 255, i == ui_pk_hrow ? 30 : 16);
                ui_rr_fill(&t, rr);
            }
            has = ui_pk_thumb_draw(e, &box);    /* v51: a picture from the file, or from inside the folder */
            if (!has) {
                ui_icon(e->dir ? UI_IC_FOLDER : UI_IC_FILE, box.x + box.w / 2 - 24, box.y + box.h / 2, 48, 245, 245, 245, e->dir ? 255 : 190);
            } else if (e->dir) {                /* a small folder on the picture says it is a folder */
                SDL_Rect bd = { box.x - 4, box.y + box.h - 22, 34, 26 };

                SDL_SetRenderDrawColor(renderer, 0, 0, 0, 170);
                ui_pill(&bd);
                ui_icon(UI_IC_FOLDER, bd.x + 8, bd.y + bd.h / 2, 18, 245, 245, 245, 255);
            }
            snprintf(tmp, sizeof(tmp), "%s", e->name);
            ui_fit_text(tmp, 15, t.w - 14);
            ui_label_c(t.x + t.w / 2, t.y + 88, tmp, 15, 245, 245, 245, 255);
            if (e->dir && e->count >= 0)
                snprintf(buf, sizeof(buf), "%d item%s", e->count, e->count == 1 ? "" : "s");
            else if (!e->dir)
                ui_pk_size_str(e->size, buf, sizeof(buf));
            else
                buf[0] = 0;
            if (buf[0])
                ui_label_c(t.x + t.w / 2, t.y + 106, buf, 12, 170, 170, 170, 255);
            if (ui_pk_mode == 2 && !e->dir) {
                SDL_Rect b = { t.x + 8, t.y + 8, 18, 18 };

                SDL_SetRenderDrawColor(renderer, 245, 245, 245, e->sel ? 255 : 150);
                if (e->sel) {
                    SDL_SetRenderDrawColor(renderer, av_clip(ar + 40, 0, 255), av_clip(ag + 40, 0, 255), av_clip(ab + 40, 0, 255), 255);
                    SDL_RenderFillRect(renderer, &b);
                    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 255);
                    SDL_RenderDrawLine(renderer, b.x + 4, b.y + 9, b.x + 7, b.y + 13);
                    SDL_RenderDrawLine(renderer, b.x + 7, b.y + 13, b.x + 14, b.y + 5);
                } else {
                    SDL_RenderDrawRect(renderer, &b);
                }
            }
            continue;
        }
        r.x = sx + 6;
        r.y = sy + 1;
        r.w = w->r.w - 12 - 8;
        r.h = UI_PK_ROW - 2;
        cy = sy + UI_PK_ROW / 2;
        tx = sx + 16;
        right = sx + w->r.w - 22;
        if (i == ui_pk_cur && ui_pk_touched) {
            SDL_SetRenderDrawColor(renderer, ar, ag, ab, 85);
            ui_pill(&r);
        } else if (i == ui_pk_hrow || i == ui_pk_cur) {
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, i == ui_pk_hrow ? 30 : 16);
            ui_pill(&r);
        }
        if (ui_pk_mode == 2 && !e->dir) {       /* a box to tick */
            SDL_Rect b = { tx, cy - 9, 18, 18 };

            SDL_SetRenderDrawColor(renderer, 245, 245, 245, e->sel ? 255 : 150);
            if (e->sel) {
                SDL_SetRenderDrawColor(renderer, av_clip(ar + 40, 0, 255), av_clip(ag + 40, 0, 255), av_clip(ab + 40, 0, 255), 255);
                SDL_RenderFillRect(renderer, &b);
                SDL_SetRenderDrawColor(renderer, 255, 255, 255, 255);
                SDL_RenderDrawLine(renderer, b.x + 4, b.y + 9, b.x + 7, b.y + 13);
                SDL_RenderDrawLine(renderer, b.x + 7, b.y + 13, b.x + 14, b.y + 5);
                SDL_RenderDrawLine(renderer, b.x + 4, b.y + 10, b.x + 7, b.y + 14);
                SDL_RenderDrawLine(renderer, b.x + 7, b.y + 14, b.x + 14, b.y + 6);
            } else {
                SDL_RenderDrawRect(renderer, &b);
            }
        }
        if (ui_pk_mode == 2)
            tx += 30;
        ui_icon(e->dir ? UI_IC_FOLDER : UI_IC_FILE, tx + 8, cy, 18, 245, 245, 245, e->dir ? 255 : 190);
        tx += 38;
        if (cols_size) {                        /* Size: a file's size, or how many items a folder holds */
            shown = 0;
            if (e->dir && e->count >= 0) {
                snprintf(buf, sizeof(buf), "%d item%s", e->count, e->count == 1 ? "" : "s");
                shown = 1;
            } else if (!e->dir) {
                ui_pk_size_str(e->size, buf, sizeof(buf));
                shown = 1;
            }
            if (shown)
                ui_label(right - ui_text_width(buf, 14), cy, buf, 14, 170, 170, 170, 255);
            right -= 100;
        }
        if (cols_mod) {                         /* Modified: today, yesterday, a weekday, weeks ago, a date when it is old */
            ui_pk_when(e->mtime, now, buf, sizeof(buf));
            ui_label(right - ui_text_width(buf, 14), cy, buf, 14, 170, 170, 170, 255);
            right -= 176;
        } else if (cols_loc && e->sect > 0) {   /* a search result from another folder: where it is */
            ui_pk_loc_str(e, buf, sizeof(buf));
            ui_fit_text(buf, 14, 230);
            ui_label(right - ui_text_width(buf, 14), cy, buf, 14, 150, 150, 150, 255);
            right -= 246;
        }
        snprintf(tmp, sizeof(tmp), "%s", e->name);
        ui_fit_text(tmp, 17, FFMAX(right - tx - 10, 40));
        ui_label(tx, cy, tmp, 17, 245, 245, 245, 255);
    }
    if (!ui_pk_grid)
        ui_pk_nwant = 0;                        /* the list view asks for no pictures */
    ui_pk_thumb_flush();
    if (ui_pk_nrw == 0) {
        const char *m = ui_pk_filter[0] ? (ui_pk_scan_on ? "Looking ..." : "Nothing matches") : ui_pk_mode == 1 ? "No folders here" :
                        ui_pk_all ? "This folder is empty" : "No music or videos here";

        ui_label_c(L.list.x + L.list.w / 2, L.list.y + L.list.h / 2, m, 18, 170, 170, 170, 255);
    }
    if (ui_pk_content_h > L.list.h) {           /* where in the list the view is */
        double fh = (double)L.list.h / ui_pk_content_h;

        r.w = 4;
        r.h = FFMAX((int)(L.list.h * fh), 24);
        r.x = L.list.x + L.list.w - 8;
        r.y = L.list.y + (int)((L.list.h - r.h) * (ui_pk_sc / (ui_pk_content_h - L.list.h)));
        SDL_SetRenderDrawColor(renderer, 255, 255, 255, 70);
        ui_pill(&r);
    }
    SDL_RenderSetClipRect(renderer, NULL);

    /* ---- the foot: how many items, or what is selected; the switches; the buttons ---- */
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 26);
    SDL_RenderDrawLine(renderer, L.p.x + 12, L.p.y + L.p.h - UI_PK_FOOT, L.p.x + L.p.w - 12, L.p.y + L.p.h - UI_PK_FOOT);
    {
        int sw = L.tog ? 316 : L.extra.x - (L.p.x + 20) - 16, fy = L.ok.y + L.ok.h / 2;

        if (av_gettime_relative() < ui_pk_note_until) {
            snprintf(tmp, sizeof(tmp), "%s", ui_pk_note);
            ui_fit_text(tmp, 15, sw);
            ui_label(L.p.x + 20, fy, tmp, 15, av_clip(ar + 70, 0, 255), av_clip(ag + 70, 0, 255), av_clip(ab + 70, 0, 255), 255);
        } else {
            ui_pk_status(tmp, sizeof(tmp), sw);
            ui_label(L.p.x + 20, fy, tmp, 15, 190, 190, 190, 255);
        }
        if (L.tog) {
            if (ui_pk_mode != 1) {
                snprintf(tmp, sizeof(tmp), "All files: %s", ui_pk_all ? "On" : "Off");
                ui_label(L.all.x, fy, tmp, 15, ui_pk_hbtn == 5 ? 255 : 190, ui_pk_hbtn == 5 ? 255 : 190, ui_pk_hbtn == 5 ? 255 : 190, 255);
            }
            snprintf(tmp, sizeof(tmp), "Hidden: %s", ui_pk_hidden ? "On" : "Off");
            ui_label(L.hid.x, fy, tmp, 15, ui_pk_hbtn == 6 ? 255 : 190, ui_pk_hbtn == 6 ? 255 : 190, ui_pk_hbtn == 6 ? 255 : 190, 255);
        }
    }
    {
        UiPkEnt *ce = ui_pk_cur_ent();
        int nt = ui_pk_mode == 2 ? ui_pk_ticked(NULL) : 0;

        if (ui_pk_mode == 1) {
            ui_pk_button(&L.extra, "Open", ui_pk_hbtn == 3, 0, ce && ce->dir);
            ui_pk_button(&L.ok, "Play", ui_pk_hbtn == 1, 1, 1);
        } else if (ui_pk_mode == 2) {
            snprintf(tmp, sizeof(tmp), "%s", L.p.w >= 740 ? "Add this folder" : "Folder");
            ui_pk_button(&L.extra, tmp, ui_pk_hbtn == 3, 0, 1);
            if (nt > 0)
                snprintf(tmp, sizeof(tmp), "Add %d", nt);
            else
                snprintf(tmp, sizeof(tmp), "Add");
            ui_pk_button(&L.ok, tmp, ui_pk_hbtn == 1, 1, nt > 0 || (ce && !ce->dir));
        } else {                                /* the button follows what is selected: a folder is opened, a file is played */
            ui_pk_button(&L.ok, ce && !ce->dir ? "Play" : "Open", ui_pk_hbtn == 1, 1, ce != NULL);
        }
    }
    ui_pk_cm_draw();
    (void)mx;
    (void)my;
}

static void ui_pk_toggle_grid(void)
{
    ui_pk_grid = !ui_pk_grid;
    cfg_pk_grid = ui_pk_grid;
    settings_save();
    ui_pk_lay_key = -1;
    ui_pk_goal = -1.0;
    if (ui_pk_touched)
        ui_pk_reveal = 1;
    else
        ui_pk_sc = 0.0;
}

static void ui_pk_toggle_search(void)
{
    if (ui_pk_filter[0] || ui_pk_search_on) {
        ui_pk_search_on = 0;
        if (ui_pk_filter[0]) {
            ui_pk_filter[0] = 0;
            ui_pk_search_start();
        }
    } else {
        ui_pk_search_on = 1;
    }
}


/* ----- v51: the path typed in the top row (Ctrl+L, or a click on the empty part of the path) ----- */
static void ui_pk_loc_full(char *out, size_t size)
{
    const char *home = getenv("HOME");

    if (ui_pk_loc[0] == '~' && (ui_pk_loc[1] == '/' || !ui_pk_loc[1]) && home)
        snprintf(out, size, "%s%s", home, ui_pk_loc + 1);
    else if (ui_pk_loc[0] == '/')
        snprintf(out, size, "%s", ui_pk_loc);
    else
        snprintf(out, size, "%s/%s", ui_pk_dir, ui_pk_loc);
}

static void ui_pk_loc_start(void)
{
    ui_pk_loc_on = 1;
    ui_pk_loc_fresh = 1;
    snprintf(ui_pk_loc, sizeof(ui_pk_loc), "%s%s", ui_pk_dir, strcmp(ui_pk_dir, "/") ? "/" : "");
}

static void ui_pk_loc_go(void)
{
    char p[PATH_MAX + 300], real[PATH_MAX];
    struct stat st;

    if (!ui_pk_loc[0])
        return;
    ui_pk_loc_full(p, sizeof(p));
    if (!realpath(p, real) || stat(real, &st) != 0) {
        snprintf(ui_pk_note, sizeof(ui_pk_note), "No such folder: %.140s", ui_pk_loc);
        ui_pk_note_until = av_gettime_relative() + 3000000;
        return;
    }
    ui_pk_loc_on = 0;
    if (S_ISDIR(st.st_mode)) {
        ui_pk_go(real);
    } else {                                    /* a file: its folder opens with the file chosen */
        char *slash = strrchr(real, '/'), name[PATH_MAX];
        int i;

        snprintf(name, sizeof(name), "%s", slash ? slash + 1 : real);
        if (slash)
            slash[slash == real ? 1 : 0] = 0;
        ui_pk_go(real);
        for (i = 0; i < ui_pk_nrw; i++) {
            UiPkEnt *e = ui_pk_ent(i);

            if (e && !strcmp(e->name, name)) {
                ui_pk_cur = i;
                ui_pk_touched = 1;
                ui_pk_reveal = 1;
                break;
            }
        }
    }
}

/* Tab: the folder name being typed is finished (the first folder, in name order, that starts with it) */
static void ui_pk_loc_complete(void)
{
    char full[PATH_MAX + 300], dirpart[PATH_MAX + 300], best[300] = "";
    char *slash;
    const char *prefix;
    DIR *d;
    struct dirent *de;
    size_t pl;

    ui_pk_loc_full(full, sizeof(full));
    if (!(slash = strrchr(full, '/')))
        return;
    prefix = slash + 1;
    pl = strlen(prefix);
    if (slash == full)
        snprintf(dirpart, sizeof(dirpart), "/");
    else
        snprintf(dirpart, sizeof(dirpart), "%.*s", (int)(slash - full), full);
    if (!(d = opendir(dirpart)))
        return;
    while ((de = readdir(d))) {
        char sub[PATH_MAX + 600];
        struct stat st;

        if (strcmp(de->d_name, ".") && strcmp(de->d_name, "..") && !strncmp(de->d_name, prefix, pl) && (de->d_name[0] != '.' || prefix[0] == '.')) {
            snprintf(sub, sizeof(sub), "%s/%s", dirpart, de->d_name);
            if (stat(sub, &st) == 0 && S_ISDIR(st.st_mode) && (!best[0] || av_strcasecmp(de->d_name, best) < 0))
                snprintf(best, sizeof(best), "%.299s", de->d_name);
        }
    }
    closedir(d);
    if (best[0])
        snprintf(ui_pk_loc, sizeof(ui_pk_loc), "%s%s%s/", dirpart, strcmp(dirpart, "/") ? "/" : "", best);
}

static void ui_pk_toggle_thumbs(void)
{
    cfg_pk_thumbs = !cfg_pk_thumbs;
    settings_save();
    snprintf(ui_pk_note, sizeof(ui_pk_note), "Thumbnails: %s", cfg_pk_thumbs ? "on" : "off");
    ui_pk_note_until = av_gettime_relative() + 2000000;
}

static int ui_pk_mouse(VideoState *is, SDL_Event *ev)
{
    UiPkLay L;
    int ww, wh, x, y, i;

    SDL_GetWindowSize(window, &ww, &wh);
    ui_pk_layout(ww, wh, &L);
    ui_pk_relayout(&L);
    ui_wake();
    if (ev->type != SDL_MOUSEMOTION && ev->type != SDL_MOUSEBUTTONDOWN) {
        if (is)
            is->force_refresh = 1;
        return 1;
    }
    x = ev->type == SDL_MOUSEMOTION ? ev->motion.x : ev->button.x;
    y = ev->type == SDL_MOUSEMOTION ? ev->motion.y : ev->button.y;
    if (ui_pk_cm_open) {                        /* the menu owns the mouse until it closes */
        SDL_Rect cr = ui_pk_cm_rect();

        ui_pk_cm_hot = ui_pk_in(&cr, x, y) ? (y - cr.y - 6) / 36 : -1;
        if (ui_pk_cm_hot >= ui_pk_cm_n || y < cr.y + 6)
            ui_pk_cm_hot = -1;
        if (ev->type == SDL_MOUSEBUTTONDOWN) {
            if (ev->button.button == SDL_BUTTON_LEFT && ui_pk_cm_hot >= 0)
                ui_pk_cm_do(is, ui_pk_cm_act[ui_pk_cm_hot]);
            else
                ui_pk_cm_open = 0;              /* a click anywhere else closes it */
        }
        if (is)
            is->force_refresh = 1;
        return 1;
    }
    ui_pk_hrow = ui_pk_row_at(&L, x, y);
    if (ui_pk_hrow >= 0 && ui_pk_rw[ui_pk_hrow].kind == 2)
        ui_pk_hrow = -1;
    ui_pk_hnode = -1;
    if (L.side_on && ui_pk_in(&L.side, x, y) && y >= L.side.y + 6) {
        int n = (y - L.side.y - 6 + (int)ui_pk_ssc) / UI_PK_TROW;

        if (n >= 0 && n < ui_pk_ntn && ui_pk_tn[n].kind != 2)
            ui_pk_hnode = n;
    }
    ui_pk_hbtn = -1;
    if (ui_pk_in(&L.back, x, y))
        ui_pk_hbtn = 20;
    else if (ui_pk_in(&L.fwd, x, y))
        ui_pk_hbtn = 21;
    else if (ui_pk_in(&L.upb, x, y))
        ui_pk_hbtn = 22;
    else if (L.sort_on && ui_pk_in(&L.sortb, x, y))
        ui_pk_hbtn = 23;
    else if (ui_pk_in(&L.gridb, x, y))
        ui_pk_hbtn = 24;
    else if (ui_pk_in(&L.srchb, x, y))
        ui_pk_hbtn = 25;
    else if (ui_pk_in(&L.closeb, x, y))
        ui_pk_hbtn = 26;
    else if (ui_pk_in(&L.ok, x, y))
        ui_pk_hbtn = 1;
    else if (ui_pk_mode != 0 && ui_pk_in(&L.extra, x, y))
        ui_pk_hbtn = 3;
    else if (L.tog && ui_pk_mode != 1 && ui_pk_in(&L.all, x, y))
        ui_pk_hbtn = 5;
    else if (L.tog && ui_pk_in(&L.hid, x, y))
        ui_pk_hbtn = 6;

    if (ev->type == SDL_MOUSEBUTTONDOWN) {
        int b = ev->button.button;

        if (ui_pk_loc_on && !ui_pk_in(&L.crumbs, x, y))
            ui_pk_loc_on = 0;
        if (b == SDL_BUTTON_X1) {
            ui_pk_back(-1);                     /* the back and forward buttons of a mouse */
        } else if (b == SDL_BUTTON_X2) {
            ui_pk_back(1);
        } else if (b != SDL_BUTTON_LEFT) {
            if (b == SDL_BUTTON_RIGHT && ui_pk_hrow >= 0)
                ui_pk_cm_start(ui_pk_hrow, x, y);       /* a right click on a row opens its menu */
        } else if (!ui_pk_in(&L.p, x, y)) {
            ui_pk_close(is);                    /* a click outside closes it */
        } else if (ui_pk_hbtn == 20) {
            ui_pk_back(-1);
        } else if (ui_pk_hbtn == 21) {
            ui_pk_back(1);
        } else if (ui_pk_hbtn == 22) {
            ui_pk_up();
        } else if (ui_pk_hbtn == 23) {
            ui_pk_sort_menu(&L);
        } else if (ui_pk_hbtn == 24) {
            ui_pk_toggle_grid();
        } else if (ui_pk_hbtn == 25) {
            ui_pk_toggle_search();
        } else if (ui_pk_hbtn == 26) {
            ui_pk_close(is);
        } else if (ui_pk_hbtn == 1) {
            ui_pk_do_ok(is);
        } else if (ui_pk_hbtn == 3) {
            ui_pk_do_extra(is);
        } else if (ui_pk_hbtn == 5 || ui_pk_hbtn == 6) {
            if (ui_pk_hbtn == 5)
                ui_pk_all = !ui_pk_all;
            else
                ui_pk_hidden = !ui_pk_hidden;
            ui_pk_reload();
        } else if (ui_pk_hnode >= 0) {
            UiPkNode *nd = &ui_pk_tn[ui_pk_hnode];
            int n = ui_pk_hnode;

            if (nd->kind == 1) {                /* a drive that is not mounted yet */
                for (i = 0; i < ui_pk_ndev; i++)
                    if (nd->dev && !strcmp(ui_pk_dev[i].dev, nd->dev)) {
                        ui_pk_mount(&ui_pk_dev[i]);
                        break;
                    }
            } else if (nd->grp == 1 && nd->dev && nd->depth == 0 && x >= L.side.x + L.side.w - 42) {      /* the eject mark: unmount */
                for (i = 0; i < ui_pk_ndev; i++)
                    if (!strcmp(ui_pk_dev[i].dev, nd->dev)) {
                        ui_pk_mnt_run(&ui_pk_dev[i], 1);
                        break;
                    }
            } else if (nd->kids != 0 && x < L.side.x + 10 + nd->depth * 14 + 18) {
                if (nd->open)
                    ui_pk_tree_close(n);
                else
                    ui_pk_tree_open(n);         /* the drop down */
            } else if (nd->path[0]) {
                char to[PATH_MAX];

                snprintf(to, sizeof(to), "%s", nd->path);
                ui_pk_go(to);
            }
        } else if (ui_pk_in(&L.crumbs, x, y)) {
            if (!ui_pk_loc_on) {
                for (i = 0; i < ui_pk_ncrumb; i++)
                    if (ui_pk_in(&ui_pk_crumb[i].r, x, y)) {
                        char to[PATH_MAX];

                        snprintf(to, sizeof(to), "%.*s", ui_pk_crumb[i].upto, ui_pk_dir);
                        ui_pk_go(to[0] ? to : "/");
                        break;
                    }
                if (i >= ui_pk_ncrumb)
                    ui_pk_loc_start();          /* the empty part of the path: type a path */
            }
        } else if (ui_pk_hrow >= 0 && av_gettime_relative() - ui_pk_nav_t > 350000) {
            int64_t now = av_gettime_relative();
            int dbl = ui_pk_click_row == ui_pk_hrow && now - ui_pk_click_t < 450000;
            UiPkEnt *e = ui_pk_ent(ui_pk_hrow);

            ui_pk_click_row = ui_pk_hrow;
            ui_pk_click_t = now;
            ui_pk_cur = ui_pk_hrow;
            ui_pk_touched = 1;
            if (dbl) {
                ui_pk_click_row = -2;
                ui_pk_activate(is);
            } else if (ui_pk_mode == 2 && e && !e->dir) {
                ui_pk_tick_row(ui_pk_hrow);     /* a click ticks the file */
            } else if (ui_pk_mode == 2 && e) {  /* a folder is entered with one click: there is nothing to tick on it */
                ui_pk_click_row = -2;
                ui_pk_activate(is);
            }
        }
    }
    if (is)
        is->force_refresh = 1;
    return 1;
}

/* Keys, typing and the wheel while the picker is open. Returns 1 if the event was used. */
static int ui_pk_event(VideoState *is, SDL_Event *ev)
{
    UiPkLay L;
    int ww, wh, rows;

    if (!ui_pk_open)
        return 0;
    SDL_GetWindowSize(window, &ww, &wh);
    ui_pk_layout(ww, wh, &L);
    ui_pk_relayout(&L);
    rows = FFMAX(L.list.h / (ui_pk_grid ? UI_PK_TILE_H : UI_PK_ROW) - 1, 1);
    if (is)
        is->force_refresh = 1;
    ui_wake();

    if (ev->type == SDL_TEXTINPUT) {
        const char *t = ev->text.text;
        size_t n = strlen(ui_pk_filter);

        if (ui_pk_cm_open)
            return 1;
        if (ui_pk_loc_on) {
            if (ui_pk_loc_fresh) {              /* the first letter replaces the path that was shown */
                ui_pk_loc[0] = 0;
                ui_pk_loc_fresh = 0;
            }
            if ((unsigned char)t[0] >= 32 && strlen(ui_pk_loc) + strlen(t) < sizeof(ui_pk_loc) - 1)
                strcat(ui_pk_loc, t);
            return 1;
        }
        if (!ui_pk_filter[0] && !strcmp(t, " "))
            return 1;                           /* the space bar ticks; a search does not start with a space */
        if ((unsigned char)t[0] >= 32 && n + strlen(t) < sizeof(ui_pk_filter) - 1) {
            strcat(ui_pk_filter, t);
            ui_pk_touched = 0;
            ui_pk_search_start();
        }
        return 1;
    }
    if (ev->type == SDL_MOUSEWHEEL) {
        float dy = ev->wheel.preciseY;
        int mx, my;

        if (ev->wheel.direction == SDL_MOUSEWHEEL_FLIPPED)
            dy = -dy;
        SDL_GetMouseState(&mx, &my);
        if (L.side_on && ui_pk_in(&L.side, mx, my))
            ui_pk_ssc -= dy * UI_PK_TROW * 2.0;         /* the tree (clamped when it is drawn) */
        else {
            double mxs = ui_pk_maxsc(&L);
            double base = ui_pk_goal >= 0.0 ? ui_pk_goal : ui_pk_sc;

            ui_pk_goal = av_clipd(base - dy * UI_PK_ROW * 2.5, 0.0, mxs);
        }
        return 1;
    }
    if (ev->type == SDL_KEYDOWN) {
        SDL_Keycode k = ev->key.keysym.sym;
        int ctrl = !!(ev->key.keysym.mod & KMOD_CTRL), alt = !!(ev->key.keysym.mod & KMOD_ALT);

        if (ui_pk_cm_open) {
            if (k == SDLK_ESCAPE)
                ui_pk_cm_open = 0;
            return 1;                           /* the menu uses the keys while it is open */
        }
        if (ui_pk_loc_on) {                     /* the path is being typed: it takes the keys */
            size_t n = strlen(ui_pk_loc);

            if (k == SDLK_BACKSPACE || k == SDLK_TAB)
                ui_pk_loc_fresh = 0;
            if (k == SDLK_ESCAPE) {
                ui_pk_loc_on = 0;
            } else if (k == SDLK_RETURN || k == SDLK_KP_ENTER) {
                ui_pk_loc_go();
            } else if (k == SDLK_TAB) {
                ui_pk_loc_complete();
            } else if (k == SDLK_BACKSPACE) {
                if (ctrl) {
                    ui_pk_loc[0] = 0;
                } else {
                    while (n > 0 && (ui_pk_loc[n - 1] & 0xC0) == 0x80)
                        n--;
                    if (n > 0)
                        ui_pk_loc[n - 1] = 0;
                }
            }
            return 1;
        }
        if (k == SDLK_ESCAPE) {
            if (ui_pk_filter[0]) {
                ui_pk_filter[0] = 0;
                ui_pk_search_start();
            } else if (ui_pk_search_on) {
                ui_pk_search_on = 0;
            } else {
                ui_pk_close(is);
            }
        } else if (alt && (k == SDLK_LEFT || k == SDLK_RIGHT)) {
            ui_pk_back(k == SDLK_LEFT ? -1 : 1);
        } else if (alt && k == SDLK_UP) {
            ui_pk_up();
        } else if (k == SDLK_DOWN || k == SDLK_UP || k == SDLK_PAGEDOWN || k == SDLK_PAGEUP || k == SDLK_HOME || k == SDLK_END ||
                   (ui_pk_grid && (k == SDLK_LEFT || k == SDLK_RIGHT))) {
            int c = ui_pk_cur, j;

            if (k == SDLK_HOME) {
                c = ui_pk_first_entry();
            } else if (k == SDLK_END) {
                for (c = ui_pk_nrw - 1; c > 0 && ui_pk_rw[c].kind == 2; c--)
                    ;
            } else if (k == SDLK_LEFT || k == SDLK_RIGHT) {
                c = ui_pk_hstep(c, k == SDLK_LEFT ? -1 : 1);
            } else if (k == SDLK_PAGEDOWN || k == SDLK_PAGEUP) {
                for (j = 0; j < rows; j++)
                    c = ui_pk_vstep(c, k == SDLK_PAGEDOWN ? 1 : -1);
            } else {
                c = ui_pk_vstep(c, k == SDLK_DOWN ? 1 : -1);
            }
            if (ui_pk_nrw > 0) {
                ui_pk_cur = av_clip(c, 0, ui_pk_nrw - 1);
                ui_pk_touched = 1;
                ui_pk_show_cursor(&L);
                ui_pk_clamp_scroll(&L);
            }
        } else if (k == SDLK_RETURN || k == SDLK_KP_ENTER) {
            if ((ui_pk_mode == 2 && ui_pk_ticked(NULL) > 0) || (ui_pk_mode == 1 && ctrl))
                ui_pk_do_ok(is);
            else
                ui_pk_activate(is);
        } else if (k == SDLK_RIGHT) {
            UiPkEnt *e = ui_pk_cur_ent();

            if (e && e->dir)
                ui_pk_activate(is);
        } else if (k == SDLK_LEFT || (k == SDLK_BACKSPACE && !ui_pk_filter[0])) {
            ui_pk_up();
        } else if (k == SDLK_BACKSPACE) {
            size_t n = strlen(ui_pk_filter);

            if (ctrl) {
                ui_pk_filter[0] = 0;
            } else {
                while (n > 0 && (ui_pk_filter[n - 1] & 0xC0) == 0x80)
                    n--;                        /* a whole character */
                if (n > 0)
                    ui_pk_filter[n - 1] = 0;
            }
            ui_pk_search_start();
        } else if (k == SDLK_SPACE && !ui_pk_filter[0]) {
            if (ui_pk_mode == 2) {
                ui_pk_tick_row(ui_pk_cur);
                ui_pk_cur = ui_pk_grid ? ui_pk_hstep(ui_pk_cur, 1) : ui_pk_vstep(ui_pk_cur, 1);
                ui_pk_touched = 1;
                ui_pk_show_cursor(&L);
                ui_pk_clamp_scroll(&L);
            }
        } else if (ctrl && k == SDLK_a && ui_pk_mode == 2) {
            int i;

            for (i = 0; i < ui_pk_nrw; i++) {
                UiPkEnt *e = ui_pk_ent(i);

                if (e && !e->dir)
                    e->sel = 1;
            }
        } else if (ctrl && k == SDLK_h) {
            ui_pk_hidden = !ui_pk_hidden;
            ui_pk_reload();
        } else if (ctrl && k == SDLK_f) {
            ui_pk_search_on = 1;
        } else if (ctrl && k == SDLK_l) {
            ui_pk_loc_start();
        } else if (ctrl && k == SDLK_t) {
            ui_pk_toggle_thumbs();
        } else if (ctrl && (k == SDLK_1 || k == SDLK_2)) {
            if (ui_pk_grid != (k == SDLK_2))
                ui_pk_toggle_grid();
        } else if (k == SDLK_F5) {
            ui_pk_dev_next = 0;
            ui_pk_reload();
        } else if (k == SDLK_TAB && ui_pk_mode != 1) {
            ui_pk_all = !ui_pk_all;
            ui_pk_reload();
        }
        return 1;                               /* a picker that is open uses every key */
    }
    return ev->type == SDL_KEYUP;
}

static void ui_pk_start(int item)
{
    const char *home = getenv("HOME");

    if (ui_pk_open || !window)
        return;
    ui_pk_mode = item == 1 ? 1 : item == 2 ? 2 : 0;
    ui_pk_all = 0;
    ui_pk_hidden = 0;
    ui_pk_hrow = ui_pk_hnode = ui_pk_hbtn = -1;
    ui_pk_click_row = -2;
    ui_pk_filter[0] = 0;
    ui_pk_search_on = 0;
    ui_pk_loc_on = 0;
    ui_pk_cm_open = 0;
    ui_pk_grid = cfg_pk_grid;
    ui_pk_sortk = av_clip(cfg_pk_sort, 0, 2);
    ui_pk_desc = cfg_pk_desc;
    ui_pk_ssc = 0.0;
    ui_pk_lay_key = -1;
    ui_pk_note_until = 0;
    ui_pk_reveal = 0;
    ui_pk_hist_clear();
    ui_pk_tree_build();
    if (!(ui_pk_last[0] && ui_pk_load(ui_pk_last)) && !(home && ui_pk_load(home)) && !ui_pk_load("/")) {
        ui_pk_tree_clear();
        ui_pick_start_zenity(item);             /* nothing can be read: the system dialog is the way out */
        return;
    }
    ui_pk_hist_push();
    ui_pk_dev_next = 0;                         /* look for drives right away */
    ui_menu_open = 0;
    ui_q_open = 0;
    ui_info_open = 0;
    ui_open_open = 0;
    ui_ctx_open = 0;
    ui_tvc_open = 0;
    ui_menu_hover = -1;
    ui_pk_open = 1;
    SDL_StartTextInput();
}

static void ui_pk_close(VideoState *is)
{
    int q;

    ui_pk_open = 0;
    ui_pk_cm_open = 0;
    ui_pk_loc_on = 0;
    ui_pk_nwant = 0;
    ui_pk_thumb_flush();                        /* the thread has nothing more to make */
    ui_pk_free_ents(ui_pk_e, ui_pk_n);
    free(ui_pk_e);
    ui_pk_e = NULL;
    ui_pk_n = ui_pk_cap = 0;
    ui_pk_free_ents(ui_pk_x, ui_pk_nx);
    free(ui_pk_x);
    ui_pk_x = NULL;
    ui_pk_nx = ui_pk_xcap = 0;
    free(ui_pk_rw);
    ui_pk_rw = NULL;
    ui_pk_nrw = ui_pk_crw = 0;
    ui_pk_jq_clear();
    for (q = 0; q < 3; q++) {
        free(ui_pk_jq[q].j);
        memset(&ui_pk_jq[q], 0, sizeof(ui_pk_jq[q]));
    }
    ui_pk_tree_clear();
    free(ui_pk_tn);
    ui_pk_tn = NULL;
    ui_pk_ctn = 0;
    ui_pk_hist_clear();
    ui_pk_filter[0] = 0;
    if (is)
        is->force_refresh = 1;
}

'''

START = "/* ================================================================================================================================\n   v44: our own file picker"
END = "static void refresh_loop_wait_event(VideoState *is, SDL_Event *event) {"


def rewrite_picker(s):
    a = s.find(START)
    b = s.find(END)
    if s.count(START) != 1 or s.count(END) != 1 or b < a:
        fail("the picker block was not found")
    return s[:a] + PICKER + s[b:]


def patch(what, fn):
    """Apply one edit to the text in memory and say so; the file is only written at the end."""
    global src
    src = fn(src)
    print("ok: " + what)


patch("the file picker, rewritten", rewrite_picker)
patch("settings var", lambda s: replace(s, "static int     cfg_pk_grid = 0, cfg_pk_sort = 0, cfg_pk_desc = 0;", "static int     cfg_pk_grid = 0, cfg_pk_sort = 0, cfg_pk_desc = 0, cfg_pk_thumbs = 1;", "settings var"))
patch("settings read", lambda s: replace(s, "        else if (sscanf(line, \" picker_desc = %d\", &n) == 1)\n            cfg_pk_desc = (n != 0);\n",
                                         "        else if (sscanf(line, \" picker_desc = %d\", &n) == 1)\n            cfg_pk_desc = (n != 0);\n        else if (sscanf(line, \" picker_thumbs = %d\", &n) == 1)\n            cfg_pk_thumbs = (n != 0);\n", "settings read"))
patch("settings write", lambda s: replace(s, "picker_desc = %d\\n\\n\", cfg_pk_grid, cfg_pk_sort, cfg_pk_desc);",
                                          "picker_desc = %d\\n# 1 = the grid view shows pictures from the videos, the covers of songs and a picture from inside each folder, 0 = icons only (Ctrl+T in the picker)\\npicker_thumbs = %d\\n\\n\", cfg_pk_grid, cfg_pk_sort, cfg_pk_desc, cfg_pk_thumbs);", "settings write"))
patch("icon enum", lambda s: replace(s, "UI_IC_ARR_U,\n       UI_IC_N };", "UI_IC_ARR_U, UI_IC_EJECT,\n       UI_IC_N };", "icon enum"))
patch("icon shape", lambda s: replace(s, "    case UI_IC_SEARCH:\n",
                                      "    case UI_IC_EJECT:                           /* v51: a triangle over a bar */\n        ic_seg(12, 5.5f, 19, 14.5f);\n        ic_seg(19, 14.5f, 5, 14.5f);\n        ic_seg(5, 14.5f, 12, 5.5f);\n        ic_seg(5.5f, 18.5f, 18.5f, 18.5f);\n        break;\n    case UI_IC_SEARCH:\n", "icon shape"))

open(path, "w", encoding="utf-8").write(src)
print("Done: patch_queue_v51 applied.")
