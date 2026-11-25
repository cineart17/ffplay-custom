#!/usr/bin/env python3
"""patch_queue_v49.py - file picker, round 1 (on top of v48).

  - one top row: Back, Forward, Up (arrows), title, path, Name/Modified/Size, close (x); no Cancel button
  - Back/Forward history (Alt+Left / Alt+Right, and the side buttons of a mouse)
  - the main button follows the row: Open on a folder, Play on a file; Open Folder shows Open + Play
  - "Date" is now "Modified" and reads like Files (3 minutes ago, Today at ..., Yesterday at ..., Monday at ..., 1 week ago, Nov 12, 2026)
  - the foot shows the item count of the folder, or the size of the selected file / the item count of the selected folder

Run it from ~/build/ffmpeg-6.1.1:   python3 ~/build/patch_queue_v49.py [path/to/ffplay.c]
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
if "ui_pk_hist_push" in src:
    print("Already applied: v49 is in " + path)
    sys.exit(0)


def fail(msg):
    print("FAILED: " + msg)
    sys.exit(1)


def replace(s, old, new, what):
    n = s.count(old)
    if n != 1:
        fail("%s: expected 1 match, found %d" % (what, n))
    return s.replace(old, new)


def insert_before(s, anchor, new, what):
    return replace(s, anchor, new + anchor, what)


def func_span(s, head, what):
    i = s.find("\n" + head)
    if i < 0 or s.count("\n" + head) != 1:
        fail("%s: function head not found exactly once" % what)
    i += 1
    j = s.find("\n}\n", i)
    if j < 0:
        fail("%s: end of function not found" % what)
    return i, j + 3


def replace_func(s, head, new, what):
    i, j = func_span(s, head, what)
    return s[:i] + new + s[j:]


def replace_span(s, start, end, new, what):
    i = s.find(start)
    if i < 0 or s.count(start) != 1:
        fail("%s: start marker not found exactly once" % what)
    j = s.find(end, i)
    if j < 0:
        fail("%s: end marker not found" % what)
    return s[:i] + new + s[j + len(end):]


def patch(what, fn):
    """Apply one edit to the text in memory and say so; the file is only written at the end."""
    global src
    src = fn(src)
    print("ok: " + what)


# ---------------------------------------------------------------------------------------------------------------- sizes
patch("UI_PK_BAR", lambda s: replace(s, "#define UI_PK_BAR  44", "#define UI_PK_BAR  52", "UI_PK_BAR"))

# ---------------------------------------------------------------------------------------------------------------- the Back icon
patch("icon enum", lambda s: replace(s, "UI_IC_CHEV_U, UI_IC_X,\n       UI_IC_N };", "UI_IC_CHEV_U, UI_IC_X,\n       UI_IC_CHEV_L,\n       UI_IC_N };", "icon enum"))
patch("icon build", lambda s: insert_before(s, "    case UI_IC_CHEV_D:\n        ic_arc(12, 7.5f, 7, 30, 150);\n", "    case UI_IC_CHEV_L:                          /* v49: the mirror of the right one (Back in the picker) */\n"
                    "        ic_arc(16.5f, 12, 7, 120, 240);\n"
                    "        break;\n", "icon build"))

# ---------------------------------------------------------------------------------------------------------------- comment
patch("comment", lambda s: replace(s, "hidden ones, Esc clears the filter, then closes.\n", "hidden ones, Esc clears the filter, then closes.\n"
              "     v49:   one top row (Back, Forward, Up, title, path, Name / Modified / Size, close); Alt+Left and Alt+Right (or the side\n"
              "            buttons of a mouse) are Back and Forward; the main button follows the row: Open for a folder, Play for a file;\n"
              "            the foot counts the items of the folder, or gives the size of the chosen file.\n", "comment"))

# ---------------------------------------------------------------------------------------------------------------- layout struct
patch("UiPkLay", lambda s: replace_span(s, "    SDL_Rect p, side, bar, list, up, cancel, ok, extra, all, hid, sort[3];", "} UiPkLay;", "    SDL_Rect p, side, bar, list, nav[3], path, xb, ok, extra, sort[3];     /* v49: nav = Back, Forward, Up; xb = close */\n"
                   "    int side_on, tog, sort_on, title_on, title_x;       /* tog: there is room in the foot for All files and Hidden */\n"
                   "} UiPkLay;", "UiPkLay"))

# ---------------------------------------------------------------------------------------------------------------- statics
NEW_STATICS = r'''/* v49: where the person has been (Back, Forward), what was last counted, where the toggles were drawn, a dimmed button */
#define UI_PK_HIST 48
#define UI_PK_CLOCK24 0                         /* 1 = clock times like 17:05, 0 = like 5:05 pm */
static char ui_pk_hist[UI_PK_HIST][PATH_MAX];
static int ui_pk_hn = 0, ui_pk_hi = -1;         /* how many folders are kept, and which of them is open */
static int ui_pk_gen = 0;                       /* counts the folder reads, so a count made for an older read is not trusted */
static char ui_pk_cnt_path[PATH_MAX + 300];
static int ui_pk_cnt_n = 0, ui_pk_cnt_gen = -1;
static SDL_Rect ui_pk_hit_all, ui_pk_hit_hid;   /* where All files and Hidden were drawn (empty when there is no room) */
static int ui_pk_btn_dim = 0;                   /* 1 while a button is drawn that cannot be used yet */

'''
patch("statics", lambda s: insert_before(s, "\nstatic int ui_pk_cm_open;", "\n" + NEW_STATICS.rstrip("\n") + "\n", "statics"))

# ---------------------------------------------------------------------------------------------------------------- load counts its reads
patch("load gen", lambda s: replace(s, "    ui_pk_nav_t = av_gettime_relative();\n    snprintf(ui_pk_dir, sizeof(ui_pk_dir), \"%s\", real);\n", "    ui_pk_gen++;\n    ui_pk_nav_t = av_gettime_relative();\n    snprintf(ui_pk_dir, sizeof(ui_pk_dir), \"%s\", real);\n", "load gen"))

# ---------------------------------------------------------------------------------------------------------------- helpers
HELPERS = r'''/* v49: Back and Forward remember the folders that were open, in the order they were visited */
static void ui_pk_hist_push(const char *dir)
{
    int at, i;

    if (ui_pk_hi >= 0 && !strcmp(ui_pk_hist[ui_pk_hi], dir))
        return;
    at = ui_pk_hi + 1;                          /* going somewhere new drops what was ahead */
    if (at >= UI_PK_HIST) {                     /* full: the oldest one goes */
        for (i = 1; i < UI_PK_HIST; i++)
            memcpy(ui_pk_hist[i - 1], ui_pk_hist[i], PATH_MAX);
        at = UI_PK_HIST - 1;
    }
    snprintf(ui_pk_hist[at], PATH_MAX, "%s", dir);
    ui_pk_hi = at;
    ui_pk_hn = at + 1;
}

/* d = -1: Back, d = 1: Forward. A folder that cannot be read any more is not entered. */
static void ui_pk_hist_step(int d)
{
    char to[PATH_MAX];
    int at = ui_pk_hi + d;

    if (at < 0 || at >= ui_pk_hn)
        return;
    snprintf(to, sizeof(to), "%s", ui_pk_hist[at]);
    if (ui_pk_load(to))
        ui_pk_hi = at;
}

/* How many rows the folder would show if it were opened (the same rules as the list: hidden ones, files that can be played).
   -1 if it cannot be read. */
static int ui_pk_count_in(const char *dir)
{
    char full[PATH_MAX + 300];
    struct dirent *de;
    DIR *d = opendir(dir);
    int n = 0;

    if (!d)
        return -1;
    while ((de = readdir(d))) {
        struct stat st;

        if (!strcmp(de->d_name, ".") || !strcmp(de->d_name, ".."))
            continue;
        if (de->d_name[0] == '.' && !ui_pk_hidden)
            continue;
        snprintf(full, sizeof(full), "%s/%s", dir, de->d_name);
        if (stat(full, &st) != 0)
            continue;
        if (S_ISDIR(st.st_mode))
            n++;
        else if (S_ISREG(st.st_mode) && ui_pk_mode != 1 && (ui_pk_all || ui_pk_has_ext(de->d_name)))
            n++;
    }
    closedir(d);
    return n;
}

/* The count is made once per folder and per read, not on every frame */
static int ui_pk_count_cached(const char *dir)
{
    if (ui_pk_cnt_gen != ui_pk_gen || strcmp(dir, ui_pk_cnt_path)) {
        ui_pk_cnt_n = ui_pk_count_in(dir);
        ui_pk_cnt_gen = ui_pk_gen;
        snprintf(ui_pk_cnt_path, sizeof(ui_pk_cnt_path), "%s", dir);
    }
    return ui_pk_cnt_n;
}

static void ui_pk_fmt_size(double sz, char *out, size_t n)
{
    if (sz < 1000.0)
        snprintf(out, n, "%d bytes", (int)sz);
    else if (sz < 1e6)
        snprintf(out, n, "%.1f kB", sz / 1e3);
    else if (sz < 1e9)
        snprintf(out, n, "%.1f MB", sz / 1e6);
    else
        snprintf(out, n, "%.1f GB", sz / 1e9);
}

static void ui_pk_clock(const struct tm *tm, char *out, size_t n)
{
#if UI_PK_CLOCK24
    snprintf(out, n, "%d:%02d", tm->tm_hour, tm->tm_min);
#else
    int h = tm->tm_hour % 12;

    snprintf(out, n, "%d:%02d %s", h ? h : 12, tm->tm_min, tm->tm_hour < 12 ? "am" : "pm");
#endif
}

/* The number of the calendar day (so two times can be compared by the day they fall on, not by 24 hour spans) */
static long ui_pk_days(const struct tm *tm)
{
    long y = tm->tm_year + 1900L, m = tm->tm_mon + 1, d = tm->tm_mday, era, yoe, doy, doe;

    y -= m <= 2;
    era = (y >= 0 ? y : y - 399) / 400;
    yoe = y - era * 400;
    doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
    doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return era * 146097 + doe;
}

/* "Modified", the way Files tells it: just now, 3 minutes ago, 2 hours ago, Today at 12:17 pm, Yesterday at 4:19 pm,
   Monday at 8:00 pm (2 to 6 days ago), 1 week ago (7 to 13 days), else Nov 12, 2026. A time in the future is shown as a date. */
static void ui_pk_when(time_t t, time_t now, char *out, size_t n)
{
    struct tm tm, tn;
    char clk[24];
    long age = (long)(now - t), dd;

    localtime_r(&t, &tm);
    localtime_r(&now, &tn);
    dd = ui_pk_days(&tn) - ui_pk_days(&tm);
    ui_pk_clock(&tm, clk, sizeof(clk));
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

static const char *ui_pk_title(void)
{
    return ui_pk_mode == 2 ? "Add to Queue" : "Open Media";
}

'''
patch("helpers", lambda s: insert_before(s, "static void ui_pk_path_of(int e, char *out, size_t size)", HELPERS, "helpers"))

# ---------------------------------------------------------------------------------------------------------------- up and go record the history
patch("up history", lambda s: replace(s, "    if (!ui_pk_load(parent))\n        return;\n", "    if (!ui_pk_load(parent))\n        return;\n    ui_pk_hist_push(ui_pk_dir);\n", "up history"))
patch("ui_pk_go", lambda s: replace_func(s, "static void ui_pk_go(const char *dir)\n{", r'''static void ui_pk_go(const char *dir)
{
    if (ui_pk_load(dir))
        ui_pk_hist_push(ui_pk_dir);
    else
        fprintf(stderr, "ffplay-custom: cannot read %s\n", dir);
}
''', "ui_pk_go"))

# ---------------------------------------------------------------------------------------------------------------- layout
patch("ui_pk_layout", lambda s: replace_func(s, "static void ui_pk_layout(int ww, int wh, UiPkLay *L)\n{", r'''static void ui_pk_layout(int ww, int wh, UiPkLay *L)
{
    static const char * const nm[3] = { "Name", "Modified", "Size" };
    int k, x, xr, right;

    L->p.w = FFMIN(av_clip(ww - 40, 360, 940), ww - 8);
    L->p.h = FFMIN(av_clip(wh - 40, 280, 640), wh - 8);
    L->p.x = (ww - L->p.w) / 2;
    L->p.y = FFMAX((wh - L->p.h) / 2, 4);
    L->side_on = L->p.w >= 640;
    L->bar.x = L->p.x;                          /* v49: one top row over the whole panel */
    L->bar.y = L->p.y;
    L->bar.w = L->p.w;
    L->bar.h = UI_PK_BAR;
    L->side.x = L->p.x;
    L->side.y = L->p.y + UI_PK_BAR;
    L->side.w = L->side_on ? UI_PK_SIDE : 0;
    L->side.h = L->p.h - UI_PK_BAR - UI_PK_FOOT;
    L->list.x = L->p.x + L->side.w;
    L->list.y = L->p.y + UI_PK_BAR;
    L->list.w = L->p.w - L->side.w;
    L->list.h = L->p.h - UI_PK_BAR - UI_PK_FOOT;

    /* the top row: Back, Forward, Up, the title, the path, Name / Modified / Size, close */
    x = L->p.x + 12;
    for (k = 0; k < 3; k++) {
        L->nav[k].x = x;
        L->nav[k].y = L->bar.y + 10;
        L->nav[k].w = 32;
        L->nav[k].h = 32;
        x += 34;
    }
    L->title_on = L->p.w >= 560;
    L->title_x = x + 12;
    x = L->title_on ? L->title_x + ui_text_width(ui_pk_title(), 20) + 18 : x + 8;
    L->xb.w = 32;
    L->xb.h = 32;
    L->xb.x = L->p.x + L->p.w - 12 - L->xb.w;
    L->xb.y = L->bar.y + 10;
    right = L->xb.x - 10;
    L->sort_on = L->p.w >= 780;
    if (L->sort_on) {
        xr = L->xb.x - 6;
        for (k = 2; k >= 0; k--) {
            L->sort[k].w = ui_text_width(nm[k], 15) + (k == ui_pk_sortk ? 40 : 24);
            L->sort[k].h = 30;
            L->sort[k].y = L->bar.y + 11;
            L->sort[k].x = xr - L->sort[k].w;
            xr -= L->sort[k].w + 2;
        }
        right = L->sort[0].x - 10;
    }
    L->path.x = x;
    L->path.y = L->bar.y + 9;
    L->path.h = 34;
    L->path.w = FFMAX(right - x, 60);

    /* the foot: the buttons at the right end (Cancel is gone: the x and Esc close the picker) */
    L->ok.h = 36;
    L->ok.y = L->p.y + L->p.h - UI_PK_FOOT + 13;
    L->ok.w = ui_pk_mode == 1 ? 110 : 132;
    L->ok.x = L->p.x + L->p.w - 20 - L->ok.w;
    L->extra = L->ok;
    L->extra.w = ui_pk_mode == 2 ? (L->p.w >= 740 ? 150 : 96) : 110;
    L->extra.x = L->ok.x - 10 - L->extra.w;
    L->tog = L->p.w >= (ui_pk_mode == 2 ? 860 : ui_pk_mode == 1 ? 720 : 680);
}
''', "ui_pk_layout"))

# ---------------------------------------------------------------------------------------------------------------- what the buttons do, and the foot text
ACTIONS = r'''/* v49: the row the person has chosen (-1 if none yet) */
static int ui_pk_chosen(void)
{
    return ui_pk_touched && ui_pk_nv > 0 ? ui_pk_vis[ui_pk_cur] : -1;
}

/* What the main button does in Open File: 0 nothing yet, 1 Open (go into the chosen folder), 2 Play (play the chosen file).
   In Open Folder and Add to Queue it always works (Play the chosen or open folder; Add). */
static int ui_pk_okmode(void)
{
    int e = ui_pk_chosen();

    if (ui_pk_mode != 0)
        return 2;
    if (e < 0)
        return 0;
    return ui_pk_e[e].dir ? 1 : 2;
}

/* Open: go into the chosen folder */
static void ui_pk_enter_sel(void)
{
    char path[PATH_MAX + 300];
    int e = ui_pk_chosen();

    if (e < 0 || !ui_pk_e[e].dir)
        return;
    ui_pk_path_of(e, path, sizeof(path));
    ui_pk_go(path);
}

/* The line in the foot, in two pieces: a name (may be empty) and what follows it. Returns 1 for a message (drawn in colour). */
static int ui_pk_status(char *lead, size_t ls, char *tail, size_t ts)
{
    int nt = ui_pk_mode == 2 ? ui_pk_ticked() : 0, e = ui_pk_chosen(), i;
    char path[PATH_MAX + 300], sz[32];

    lead[0] = tail[0] = 0;
    if (ui_pk_note[0] && av_gettime_relative() < ui_pk_note_until) {
        snprintf(tail, ts, "%s", ui_pk_note);
        return 1;
    }
    if (ui_pk_filter[0]) {
        snprintf(tail, ts, "Filter: %.100s  -  %d of %d items", ui_pk_filter, ui_pk_nv, ui_pk_n);
        return 1;
    }
    if (nt > 1) {
        snprintf(tail, ts, "%d files selected", nt);
        return 0;
    }
    if (nt == 1) {
        for (i = 0; i < ui_pk_n; i++)
            if (ui_pk_sel[i]) {
                e = i;
                break;
            }
    }
    if (e >= 0 && e < ui_pk_n) {
        snprintf(lead, ls, "%.255s", ui_pk_e[e].name);
        if (ui_pk_e[e].dir) {                   /* a folder: how many items are in it, not how big it is */
            int c;

            ui_pk_path_of(e, path, sizeof(path));
            c = ui_pk_count_cached(path);
            if (c < 0)
                snprintf(tail, ts, " selected");
            else
                snprintf(tail, ts, " selected (%d item%s)", c, c == 1 ? "" : "s");
        } else {
            ui_pk_fmt_size((double)ui_pk_e[e].size, sz, sizeof(sz));
            snprintf(tail, ts, " selected (%s)", sz);
        }
        return 0;
    }
    snprintf(tail, ts, "%d item%s", ui_pk_nv, ui_pk_nv == 1 ? "" : "s");
    return 0;
}

'''
patch("actions", lambda s: insert_before(s, "/* Enter or Enter-like: a folder is entered, a file is opened (or, with ticks, they are added) */", ACTIONS, "actions"))

# ---------------------------------------------------------------------------------------------------------------- start: the history begins at the folder that opens
patch("start history", lambda s: replace(s, "        ui_pick_start_zenity(item);             /* nothing can be read: the system dialog is the way out */\n        return;\n    }\n", "        ui_pick_start_zenity(item);             /* nothing can be read: the system dialog is the way out */\n        return;\n    }\n"
              "    ui_pk_hn = 0;                               /* v49: Back and Forward start from here */\n"
              "    ui_pk_hi = -1;\n"
              "    ui_pk_hist_push(ui_pk_dir);\n", "start history"))

# ---------------------------------------------------------------------------------------------------------------- button
patch("ui_pk_button", lambda s: replace_func(s, "static void ui_pk_button(const SDL_Rect *r, const char *label, int hot, int primary)\n{", r'''static void ui_pk_button(const SDL_Rect *r, const char *label, int hot, int primary)
{
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    if (primary)
        SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r, 0, 255), av_clip(cfg_bar_g, 0, 255), av_clip(cfg_bar_b, 0, 255),
                               ui_pk_btn_dim ? 70 : hot ? 255 : 215);
    else
        SDL_SetRenderDrawColor(renderer, 255, 255, 255, ui_pk_btn_dim ? 14 : hot ? 60 : 30);
    ui_pill(r);
    ui_label_c(r->x + r->w / 2, r->y + r->h / 2, label, 16, 245, 245, 245, ui_pk_btn_dim ? 120 : 255);
}
''', "ui_pk_button"))

# ---------------------------------------------------------------------------------------------------------------- draw
patch("ui_pk_draw", lambda s: replace_func(s, "static void ui_pk_draw(void)\n{", r'''static void ui_pk_draw(void)
{
    UiPkLay L;
    SDL_Rect r, clip;
    char tmp[PATH_MAX + 64], lead[320], tail[220];
    int ww, wh, i, first, last, mx = 0, my = 0, x, cy, cyf, cols_date, cols_size, om, msg, tw;
    time_t now = time(NULL);

    if (!ui_pk_open)
        return;
    SDL_GetWindowSize(window, &ww, &wh);
    ui_pk_layout(ww, wh, &L);
    ui_pk_clamp_scroll(&L);
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
    ui_glass(&L.p, 28);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    SDL_GetMouseState(&mx, &my);

    /* the top row: Back, Forward, Up, the title, the path, Name / Modified / Size, close */
    cy = L.bar.y + L.bar.h / 2;
    {
        static const int ic[3] = { UI_IC_CHEV_L, UI_IC_CHEV_R, UI_IC_CHEV_U };
        int can[3];

        can[0] = ui_pk_hi > 0;
        can[1] = ui_pk_hi + 1 < ui_pk_hn;
        can[2] = strcmp(ui_pk_dir, "/") != 0;
        for (i = 0; i < 3; i++) {
            if (can[i] && ui_pk_hbtn == 20 + i) {
                SDL_SetRenderDrawColor(renderer, 255, 255, 255, 34);
                ui_pill(&L.nav[i]);
            }
            ui_icon(ic[i], L.nav[i].x + L.nav[i].w / 2, cy, 18, 245, 245, 245, can[i] ? 235 : 70);
        }
    }
    if (L.title_on)
        ui_label(L.title_x, cy, ui_pk_title(), 20, 245, 245, 245, 255);

    /* the path, in a pill: the folders from the left, the last ones if they do not all fit */
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 22);
    ui_pill(&L.path);
    {
        const char *home = getenv("HOME");
        int hl = home ? (int)strlen(home) : 0, starts_home = hl > 1 && !strncmp(ui_pk_dir, home, hl) &&
                 (ui_pk_dir[hl] == '/' || !ui_pk_dir[hl]);
        struct { char label[PATH_MAX]; int upto; } seg[64];
        int ns = 0, pos, sw, total, from = 0, avail = L.path.w - 32, len = (int)strlen(ui_pk_dir);
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
        x = L.path.x + 16;
        ui_pk_ncrumb = 0;
        if (from > 0) {
            ui_label(x, cy, "...", 16, 170, 170, 170, 255);
            x += ui_text_width("...", 16) + gap;
        }
        for (i = from; i < ns; i++) {
            int last_seg = i == ns - 1;

            snprintf(tmp, sizeof(tmp), "%s", seg[i].label);
            ui_fit_text(tmp, 16, FFMAX(avail - (x - L.path.x - 16), 60));
            sw = ui_text_width(tmp, 16);
            if (ui_pk_ncrumb < 24) {
                ui_pk_crumb[ui_pk_ncrumb].r.x = x - 4;
                ui_pk_crumb[ui_pk_ncrumb].r.y = L.path.y + 2;
                ui_pk_crumb[ui_pk_ncrumb].r.w = sw + 8;
                ui_pk_crumb[ui_pk_ncrumb].r.h = L.path.h - 4;
                ui_pk_crumb[ui_pk_ncrumb].upto = seg[i].upto;
                ui_pk_ncrumb++;
            }
            ui_label(x, cy, tmp, 16, 245, 245, 245, last_seg ? 255 : 190);
            x += sw;
            if (!last_seg) {
                ui_icon(UI_IC_CHEV_R, x + 13, cy, 14, 150, 150, 150, 255);
                x += gap;
            }
        }
    }
    if (L.sort_on) {
        static const char * const nm[3] = { "Name", "Modified", "Size" };

        for (i = 0; i < 3; i++) {
            int on = i == ui_pk_sortk, hot = ui_pk_hbtn == 10 + i;

            if (hot) {
                SDL_SetRenderDrawColor(renderer, 255, 255, 255, 26);
                ui_pill(&L.sort[i]);
            }
            ui_label(L.sort[i].x + 12, L.sort[i].y + L.sort[i].h / 2, nm[i], 15, on ? av_clip(cfg_bar_r + 70, 0, 255) : 190,
                     on ? av_clip(cfg_bar_g + 70, 0, 255) : 190, on ? av_clip(cfg_bar_b + 70, 0, 255) : 190, 255);
            if (on)
                ui_icon(ui_pk_desc ? UI_IC_CHEV_D : UI_IC_CHEV_U, L.sort[i].x + L.sort[i].w - 15, L.sort[i].y + L.sort[i].h / 2, 14,
                        av_clip(cfg_bar_r + 70, 0, 255), av_clip(cfg_bar_g + 70, 0, 255), av_clip(cfg_bar_b + 70, 0, 255), 255);
        }
    }
    if (ui_pk_hbtn == 4) {
        SDL_SetRenderDrawColor(renderer, 255, 255, 255, 40);
        ui_pill(&L.xb);
    }
    ui_icon(UI_IC_X, L.xb.x + L.xb.w / 2, cy, 16, 245, 245, 245, ui_pk_hbtn == 4 ? 255 : 200);
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 26);
    SDL_RenderDrawLine(renderer, L.p.x + 12, L.list.y, L.p.x + L.p.w - 12, L.list.y);

    /* the places */
    if (L.side_on) {
        SDL_SetRenderDrawColor(renderer, 0, 0, 0, 55);
        SDL_RenderFillRect(renderer, &L.side);
        for (i = 0; i < ui_pk_npl; i++) {
            int on = !strcmp(ui_pk_pl[i].path, ui_pk_dir);

            r.x = L.side.x + 8;
            r.y = L.side.y + 8 + i * 36;
            r.w = L.side.w - 16;
            r.h = 34;
            if (r.y + r.h > L.side.y + L.side.h)
                break;
            if (on || i == ui_pk_hplace) {
                SDL_SetRenderDrawColor(renderer, on ? av_clip(cfg_bar_r, 0, 255) : 255, on ? av_clip(cfg_bar_g, 0, 255) : 255,
                                       on ? av_clip(cfg_bar_b, 0, 255) : 255, on ? 90 : 28);
                ui_pill(&r);
            }
            ui_icon(UI_IC_FOLDER, r.x + 20, r.y + r.h / 2, 18, 245, 245, 245, on ? 255 : 200);
            snprintf(tmp, sizeof(tmp), "%s", ui_pk_pl[i].name);
            ui_fit_text(tmp, 16, r.w - 52);
            ui_label(r.x + 38, r.y + r.h / 2, tmp, 16, 245, 245, 245, on ? 255 : 215);
        }
        SDL_SetRenderDrawColor(renderer, 255, 255, 255, 26);
        SDL_RenderDrawLine(renderer, L.side.x + L.side.w, L.side.y, L.side.x + L.side.w, L.side.y + L.side.h);
    }

    /* the list */
    clip = L.list;
    SDL_RenderSetClipRect(renderer, &clip);
    cols_date = L.list.w >= 640;
    cols_size = L.list.w >= 400;
    first = (int)(ui_pk_sc / UI_PK_ROW);
    last = FFMIN(ui_pk_nv - 1, (int)((ui_pk_sc + L.list.h) / UI_PK_ROW));
    for (i = first; i <= last; i++) {
        const UiPkEnt *e = &ui_pk_e[ui_pk_vis[i]];
        int ry = L.list.y + (int)(i * (double)UI_PK_ROW - ui_pk_sc), tx = L.list.x + 16, ticked = ui_pk_sel[ui_pk_vis[i]];
        int right = L.list.x + L.list.w - 22;

        r.x = L.list.x + 6;
        r.y = ry + 2;
        r.w = L.list.w - 12 - 8;
        r.h = UI_PK_ROW - 4;
        cy = ry + UI_PK_ROW / 2;
        if (i == ui_pk_cur && ui_pk_touched) {
            SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r, 0, 255), av_clip(cfg_bar_g, 0, 255), av_clip(cfg_bar_b, 0, 255), 85);
            ui_pill(&r);
        } else if (i == ui_pk_hrow || i == ui_pk_cur) {
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, i == ui_pk_hrow ? 30 : 16);
            ui_pill(&r);
        }
        if (ui_pk_mode == 2 && !e->dir) {       /* a box to tick */
            SDL_Rect b = { tx, cy - 9, 18, 18 };

            SDL_SetRenderDrawColor(renderer, 245, 245, 245, ticked ? 255 : 150);
            if (ticked) {
                SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                                       av_clip(cfg_bar_b + 40, 0, 255), 255);
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
        ui_icon(e->dir ? UI_IC_FOLDER : UI_IC_FILE, tx + 10, cy, 18, 245, 245, 245, e->dir ? 255 : 190);
        tx += 30;
        if (cols_date) {                        /* v49: Modified, told the way Files tells it */
            char ds[48];

            ui_pk_when(e->mtime, now, ds, sizeof(ds));
            ui_label(right - ui_text_width(ds, 14), cy, ds, 14, 170, 170, 170, 255);
            right -= 190;
        }
        if (cols_size && !e->dir) {
            char ss[32];

            ui_pk_fmt_size((double)e->size, ss, sizeof(ss));
            ui_label(right - ui_text_width(ss, 14), cy, ss, 14, 170, 170, 170, 255);
        }
        if (cols_size)
            right -= 100;
        snprintf(tmp, sizeof(tmp), "%s", e->name);
        ui_fit_text(tmp, 17, FFMAX(right - tx - 10, 40));
        ui_label(tx, cy, tmp, 17, 245, 245, 245, 255);
    }
    if (ui_pk_nv == 0) {
        const char *m = ui_pk_filter[0] ? "Nothing matches" : ui_pk_mode == 1 ? "No folders here" : ui_pk_all ? "This folder is empty" :
                        "No music or videos here";

        ui_label_c(L.list.x + L.list.w / 2, L.list.y + L.list.h / 2, m, 18, 170, 170, 170, 255);
    }
    if (ui_pk_nv * UI_PK_ROW > L.list.h) {      /* where in the list the view is */
        double fh = (double)L.list.h / (ui_pk_nv * UI_PK_ROW);

        r.w = 4;
        r.h = FFMAX((int)(L.list.h * fh), 24);
        r.x = L.list.x + L.list.w - 8;
        r.y = L.list.y + (int)((L.list.h - r.h) * (ui_pk_sc / (ui_pk_nv * (double)UI_PK_ROW - L.list.h)));
        SDL_SetRenderDrawColor(renderer, 255, 255, 255, 70);
        ui_pill(&r);
    }
    SDL_RenderSetClipRect(renderer, NULL);

    /* the foot: what is in the folder or chosen, then the toggles, then the buttons */
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 26);
    SDL_RenderDrawLine(renderer, L.p.x + 12, L.p.y + L.p.h - UI_PK_FOOT, L.p.x + L.p.w - 12, L.p.y + L.p.h - UI_PK_FOOT);
    cyf = L.ok.y + L.ok.h / 2;
    {
        int sx = L.p.x + 20, btn_left = ui_pk_mode == 0 ? L.ok.x : L.extra.x, sw = L.tog ? 250 : btn_left - sx - 16;

        msg = ui_pk_status(lead, sizeof(lead), tail, sizeof(tail));
        tw = ui_text_width(tail, 15);
        if (lead[0]) {                          /* the name gives way, so the size or the count at its end always shows */
            ui_fit_text(lead, 15, FFMAX(sw - tw - ui_text_width("\"\"", 15), 30));
            snprintf(tmp, sizeof(tmp), "\"%s\"%s", lead, tail);
        } else {
            snprintf(tmp, sizeof(tmp), "%s", tail);
            ui_fit_text(tmp, 15, FFMAX(sw, 40));
        }
        if (msg)
            ui_label(sx, cyf, tmp, 15, av_clip(cfg_bar_r + 60, 0, 255), av_clip(cfg_bar_g + 60, 0, 255),
                     av_clip(cfg_bar_b + 60, 0, 255), 255);
        else
            ui_label(sx, cyf, tmp, 15, 190, 190, 190, 255);
        memset(&ui_pk_hit_all, 0, sizeof(ui_pk_hit_all));
        memset(&ui_pk_hit_hid, 0, sizeof(ui_pk_hit_hid));
        if (L.tog) {
            int tx = sx + 270, w;

            if (ui_pk_mode != 1) {
                snprintf(tmp, sizeof(tmp), "All files: %s", ui_pk_all ? "On" : "Off");
                w = ui_text_width(tmp, 15);
                ui_label(tx, cyf, tmp, 15, ui_pk_hbtn == 5 ? 255 : 190, ui_pk_hbtn == 5 ? 255 : 190, ui_pk_hbtn == 5 ? 255 : 190, 255);
                ui_pk_hit_all.x = tx - 6;
                ui_pk_hit_all.y = L.ok.y;
                ui_pk_hit_all.w = w + 12;
                ui_pk_hit_all.h = L.ok.h;
                tx += w + 26;
            }
            snprintf(tmp, sizeof(tmp), "Hidden: %s", ui_pk_hidden ? "On" : "Off");
            w = ui_text_width(tmp, 15);
            ui_label(tx, cyf, tmp, 15, ui_pk_hbtn == 6 ? 255 : 190, ui_pk_hbtn == 6 ? 255 : 190, ui_pk_hbtn == 6 ? 255 : 190, 255);
            ui_pk_hit_hid.x = tx - 6;
            ui_pk_hit_hid.y = L.ok.y;
            ui_pk_hit_hid.w = w + 12;
            ui_pk_hit_hid.h = L.ok.h;
        }
    }
    if (ui_pk_mode == 0) {                      /* Open on a folder, Play on a file; nothing chosen yet: Open, dimmed */
        om = ui_pk_okmode();
        ui_pk_btn_dim = om == 0;
        ui_pk_button(&L.ok, om == 2 ? "Play" : "Open", ui_pk_hbtn == 1 && om != 0, 1);
        ui_pk_btn_dim = 0;
    } else if (ui_pk_mode == 1) {               /* Open (go into the chosen folder) and Play (play the chosen or open folder) */
        int can_open = ui_pk_chosen() >= 0 && ui_pk_e[ui_pk_chosen()].dir;

        ui_pk_btn_dim = !can_open;
        ui_pk_button(&L.extra, "Open", ui_pk_hbtn == 3 && can_open, 0);
        ui_pk_btn_dim = 0;
        ui_pk_button(&L.ok, "Play", ui_pk_hbtn == 1, 1);
    } else {
        int nt = ui_pk_ticked();

        snprintf(tmp, sizeof(tmp), "%s", L.p.w >= 740 ? "Add this folder" : "Folder");
        ui_pk_button(&L.extra, tmp, ui_pk_hbtn == 3, 0);
        if (nt > 0) {
            snprintf(tmp, sizeof(tmp), "Add %d", nt);
            ui_pk_button(&L.ok, tmp, ui_pk_hbtn == 1, 1);
        } else {
            ui_pk_button(&L.ok, "Add", ui_pk_hbtn == 1, 1);
        }
    }
    ui_pk_cm_draw();
}
''', "ui_pk_draw"))

# ---------------------------------------------------------------------------------------------------------------- mouse
patch("ui_pk_mouse", lambda s: replace_func(s, "static int ui_pk_mouse(VideoState *is, SDL_Event *ev)\n{", r'''static int ui_pk_mouse(VideoState *is, SDL_Event *ev)
{
    UiPkLay L;
    int ww, wh, x, y, i;

    SDL_GetWindowSize(window, &ww, &wh);
    ui_pk_layout(ww, wh, &L);
    x = ev->type == SDL_MOUSEMOTION ? ev->motion.x : ev->button.x;
    y = ev->type == SDL_MOUSEMOTION ? ev->motion.y : ev->button.y;
    ui_wake();
    if (ui_pk_cm_open) {                        /* v45: the menu of a row owns the mouse until it closes */
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
    ui_pk_hrow = ui_pk_hplace = ui_pk_hbtn = -1;
    if (ui_pk_in(&L.list, x, y))
        ui_pk_hrow = (int)((y - L.list.y + ui_pk_sc) / UI_PK_ROW);
    if (ui_pk_hrow >= ui_pk_nv)
        ui_pk_hrow = -1;
    if (L.side_on && ui_pk_in(&L.side, x, y) && y >= L.side.y + 8 && (y - L.side.y - 8) / 36 < ui_pk_npl)
        ui_pk_hplace = (y - L.side.y - 8) / 36;
    if (L.sort_on && y >= L.bar.y && y < L.bar.y + L.bar.h) {
        for (i = 0; i < 3; i++)
            if (ui_pk_in(&L.sort[i], x, y))
                ui_pk_hbtn = 10 + i;
    }
    if (ui_pk_hbtn >= 10)
        ;
    else if (ui_pk_in(&L.nav[0], x, y))
        ui_pk_hbtn = 20;                        /* Back */
    else if (ui_pk_in(&L.nav[1], x, y))
        ui_pk_hbtn = 21;                        /* Forward */
    else if (ui_pk_in(&L.nav[2], x, y))
        ui_pk_hbtn = 22;                        /* Up */
    else if (ui_pk_in(&L.xb, x, y))
        ui_pk_hbtn = 4;                         /* close */
    else if (ui_pk_in(&L.ok, x, y))
        ui_pk_hbtn = 1;
    else if (ui_pk_mode != 0 && ui_pk_in(&L.extra, x, y))
        ui_pk_hbtn = 3;
    else if (ui_pk_in(&ui_pk_hit_all, x, y))
        ui_pk_hbtn = 5;
    else if (ui_pk_in(&ui_pk_hit_hid, x, y))
        ui_pk_hbtn = 6;

    if (ev->type == SDL_MOUSEBUTTONDOWN) {
        if (ev->button.button != SDL_BUTTON_LEFT) {
            if (ev->button.button == SDL_BUTTON_RIGHT && ui_pk_hrow >= 0)
                ui_pk_cm_start(ui_pk_hrow, x, y);       /* v45: a right click on a row opens its menu (it used to go up a folder) */
            else if (ev->button.button == SDL_BUTTON_X1)
                ui_pk_hist_step(-1);            /* v49: the side buttons of a mouse: Back */
            else if (ev->button.button == SDL_BUTTON_X2)
                ui_pk_hist_step(1);             /* Forward */
        } else if (!ui_pk_in(&L.p, x, y)) {
            ui_pk_close(is);                    /* a click outside closes it */
        } else if (ui_pk_hbtn == 20) {
            ui_pk_hist_step(-1);
        } else if (ui_pk_hbtn == 21) {
            ui_pk_hist_step(1);
        } else if (ui_pk_hbtn == 22) {
            ui_pk_up();
        } else if (ui_pk_hbtn == 4) {
            ui_pk_close(is);
        } else if (ui_pk_hbtn == 1) {
            if (ui_pk_mode == 0) {
                int om = ui_pk_okmode();

                if (om == 1)
                    ui_pk_enter_sel();          /* a folder is chosen: Open goes into it */
                else if (om == 2)
                    ui_pk_confirm(is, 0);       /* a file is chosen: Play */
            } else {
                ui_pk_confirm(is, 0);
            }
        } else if (ui_pk_hbtn == 3) {
            if (ui_pk_mode == 1)
                ui_pk_enter_sel();              /* Open Folder: Open goes into the chosen folder, Play (the main button) plays it */
            else
                ui_pk_confirm(is, 1);
        } else if (ui_pk_hbtn == 5 || ui_pk_hbtn == 6) {
            char keep[PATH_MAX];

            if (ui_pk_hbtn == 5)
                ui_pk_all = !ui_pk_all;
            else
                ui_pk_hidden = !ui_pk_hidden;
            snprintf(keep, sizeof(keep), "%s", ui_pk_dir);
            ui_pk_load(keep);
        } else if (ui_pk_hbtn >= 10) {
            int k = ui_pk_hbtn - 10;

            if (k == ui_pk_sortk) {
                ui_pk_desc = !ui_pk_desc;       /* the one that is on: the other way round */
            } else {
                ui_pk_sortk = k;
                ui_pk_desc = k != 0;            /* the newest and the biggest first, names from A */
            }
            ui_pk_resort();
        } else if (ui_pk_hplace >= 0) {
            ui_pk_go(ui_pk_pl[ui_pk_hplace].path);
        } else if (y >= L.bar.y && y < L.bar.y + L.bar.h) {
            for (i = 0; i < ui_pk_ncrumb; i++)
                if (ui_pk_in(&ui_pk_crumb[i].r, x, y)) {
                    char to[PATH_MAX];

                    snprintf(to, sizeof(to), "%.*s", ui_pk_crumb[i].upto, ui_pk_dir);
                    ui_pk_go(to[0] ? to : "/");
                    break;
                }
        } else if (ui_pk_hrow >= 0 && av_gettime_relative() - ui_pk_nav_t > 350000) {
            int64_t now = av_gettime_relative();
            int dbl = ui_pk_click_row == ui_pk_hrow && now - ui_pk_click_t < 450000;

            ui_pk_click_row = ui_pk_hrow;
            ui_pk_click_t = now;
            ui_pk_cur = ui_pk_hrow;
            ui_pk_touched = 1;
            if (dbl) {
                ui_pk_click_row = -2;
                ui_pk_activate(is);
            } else if (ui_pk_mode == 2 && !ui_pk_e[ui_pk_vis[ui_pk_hrow]].dir) {
                ui_pk_tick_row(ui_pk_hrow);     /* a click ticks the file */
            } else if (ui_pk_mode == 2) {       /* a folder is entered with one click: there is nothing to tick on it */
                ui_pk_click_row = -2;
                ui_pk_activate(is);
            }
        }
    }
    if (is)
        is->force_refresh = 1;
    return 1;
}
''', "ui_pk_mouse"))

# ---------------------------------------------------------------------------------------------------------------- keys: Alt+Left / Alt+Right
patch("keys", lambda s: replace(s, "        if (k == SDLK_ESCAPE) {\n            if (ui_pk_filter[0]) {\n", "        if (alt && (k == SDLK_LEFT || k == SDLK_RIGHT)) {       /* v49: Back and Forward */\n"
              "            ui_pk_hist_step(k == SDLK_LEFT ? -1 : 1);\n"
              "            return 1;\n"
              "        }\n"
              "        if (k == SDLK_ESCAPE) {\n            if (ui_pk_filter[0]) {\n", "keys"))

open(path, "w", encoding="utf-8").write(src)
print("Done: patch_queue_v49 applied.")
