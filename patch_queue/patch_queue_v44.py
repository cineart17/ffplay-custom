#!/usr/bin/env python3
# Update 44 for ffplay-custom (on top of patch_queue_v43.py).
#   * Our own file picker. Open File, Open Folder and Add to Queue now open a picker in the player's own glass style, drawn over the
#     blurred player like Preferences, so it can never open behind the player and needs no other program:
#       - places on the left (Home, Documents, Downloads, Music, Videos, Pictures, drives, Computer), a path on top that can be clicked,
#         an Up button, and the folders and the music and videos in them with their size and date;
#       - type to filter the list; Up/Down/PageUp/PageDown/Home/End; Enter opens a folder or plays a file; Left or Backspace goes up;
#         Esc clears the filter, then closes; Tab shows all files; Ctrl+H shows hidden ones; the wheel scrolls;
#       - Add to Queue: Space or a click ticks a file, Ctrl+A ticks all, Enter adds what is ticked, "Add this folder" adds the open one;
#       - Open Folder: a click chooses a folder, Enter goes into it, "Open folder" opens the chosen one (or the one that is open).
#     It starts in the folder it was in last. The system dialog (zenity) is still there: picker = 0 in
#     ~/.config/ffplay-custom/settings.conf brings it back, and it is also the way out if no folder can be read.
#   * The seek code that nothing used any more is gone: the held-key steps (ui_ks_*) and the preview picture drawn while seeking
#     (ui_scrub_draw, the one warning of the build).
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v43.py. Writes the file only if every edit matches.
import sys

PATH = "fftools/ffplay.c"
src = open(PATH).read()
fails = []


def patch(name, old, new):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED: %s matched %d times" % (name, n))
        fails.append(name)
        return
    src = src.replace(old, new)
    print("ok: " + name)


if "ui_pk_draw" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "v43" not in src:
    print("Apply patch_queue_v43.py first. Nothing written.")
    sys.exit(1)

# ---------------------------------------------------------------- the settings: picker = 1 (ours), 0 (the system's)
patch("picker switch", r'''static int     cfg_exact_seek = 1;''', r'''static int     cfg_picker = 1;              /* 1 = our own file picker, 0 = the system's dialog (zenity) (v44) */
static int     cfg_exact_seek = 1;''')
patch("picker switch read", r'''        else if (sscanf(line, " exact_seek = %d", &n) == 1)
            cfg_exact_seek = (n != 0);''', r'''        else if (sscanf(line, " exact_seek = %d", &n) == 1)
            cfg_exact_seek = (n != 0);
        else if (sscanf(line, " picker = %d", &n) == 1)
            cfg_picker = (n != 0);''')
patch("picker switch written", r'''exact_seek = %d\n\n", cfg_exact_seek);''', r'''exact_seek = %d\n\n", cfg_exact_seek);
    fprintf(f, "# 1 = Open File, Open Folder and Add to Queue use the player's own picker, 0 = the system's dialog (needs zenity)\npicker = %d\n\n", cfg_picker);''')

# ---------------------------------------------------------------- the picker: where it is open, and how it is reached
patch("picker state", r'''static int ui_prefs_open = 0;       /* 1 while the Preferences panel is showing */''', r'''static int ui_prefs_open = 0;       /* 1 while the Preferences panel is showing */
static int ui_pk_open = 0;          /* v44: 1 while our file picker is showing */
static void ui_pk_draw(void);
static int ui_pk_mouse(VideoState *is, SDL_Event *ev);
static int ui_pk_event(VideoState *is, SDL_Event *ev);''')
patch("the menu asks for the picker", r'''static void ui_pick_start(int item)
{
    SDL_Thread *t;
    SDL_SysWMinfo info;''', r'''static void ui_pk_start(int item);
static void ui_pick_start_zenity(int item);

static void ui_pick_start(int item)
{
    if (cfg_picker)
        ui_pk_start(item);                      /* v44: our own picker */
    else
        ui_pick_start_zenity(item);
}

static void ui_pick_start_zenity(int item)
{
    SDL_Thread *t;
    SDL_SysWMinfo info;''')
patch("picker is drawn with the glass", r'''    ui_prefs_draw();
    ui_ink_dark = 0;
    ui_present();''', r'''    ui_prefs_draw();
    ui_ink_dark = 0;
    ui_pk_draw();
    ui_ink_dark = 0;
    ui_present();''')
patch("picker blurs the player", r'''        if (is || ui_prefs_open || ui_q_open || ui_info_open)
            ui_glass_blur();''', r'''        if (is || ui_prefs_open || ui_q_open || ui_info_open || ui_pk_open)
            ui_glass_blur();''')
patch("no idle menu under the picker", r'''    if (ui_prefs_open || (!ui_idle && !ui_menu_open))
        return;
    if (ui_ctx_open && (!ui_q_open''', r'''    if (ui_prefs_open || ui_pk_open || (!ui_idle && !ui_menu_open))
        return;
    if (ui_ctx_open && (!ui_q_open''')
patch("picker owns the mouse", r'''    if (ui_prefs_open)
        return ui_prefs_mouse(is, ev);
    if (ui_tv_ctx_mouse(is, ev))''', r'''    if (ui_prefs_open)
        return ui_prefs_mouse(is, ev);
    if (ui_pk_open)
        return ui_pk_mouse(is, ev);             /* v44 */
    if (ui_tv_ctx_mouse(is, ev))''')
patch("glass frame while the picker is open", r'''    if (ui_menu_open || ui_prefs_open) {
        ui_glass_frame(is);         /* frosted glass over the blurred picture */''', r'''    if (ui_menu_open || ui_prefs_open || ui_pk_open) {
        ui_glass_frame(is);         /* frosted glass over the blurred picture */''')
patch("the cursor stays", r'''if (!cursor_hidden && !ui_hover && !ui_drag && !ui_menu_open && !ui_prefs_open && av_gettime_relative()''',
      r'''if (!cursor_hidden && !ui_hover && !ui_drag && !ui_menu_open && !ui_prefs_open && !ui_pk_open && av_gettime_relative()''')
patch("picker takes keys, typing and the wheel (playing)", r'''        double x;
        refresh_loop_wait_event(cur_stream, &event);
        switch (event.type) {''', r'''        double x;
        refresh_loop_wait_event(cur_stream, &event);
        if (ui_pk_event(cur_stream, &event))    /* v44: the picker uses the keys, the typing and the wheel while it is open */
            continue;
        switch (event.type) {''')
patch("picker takes keys, typing and the wheel (idle)", r'''        while (SDL_PollEvent(&ev)) {
            switch (ev.type) {
            case SDL_QUIT:
                do_exit(NULL);
                break;
            case SDL_KEYDOWN:
                ev.key.keysym.sym = ui_key_translate(ev.key.keysym.sym);   /* the keys chosen in settings.conf */''', r'''        while (SDL_PollEvent(&ev)) {
            if (ev.type != SDL_QUIT && ui_pk_event(NULL, &ev))      /* v44 */
                continue;
            switch (ev.type) {
            case SDL_QUIT:
                do_exit(NULL);
                break;
            case SDL_KEYDOWN:
                ev.key.keysym.sym = ui_key_translate(ev.key.keysym.sym);   /* the keys chosen in settings.conf */''')

patch("the picker", r'''static void refresh_loop_wait_event(VideoState *is, SDL_Event *event) {''', r'''/* ================================================================================================================================
   v44: our own file picker, for Open File, Open Folder and Add to Queue. It is drawn like the Preferences panel (frosted glass over
   the blurred player) and sends what is chosen to the inbox, like the system dialog did. It needs no other program.
     Mouse: a click on a row selects it, a double click opens it (a folder is entered, a file is played); in Add to Queue a click on
            a file ticks it; the places on the left and the path on top move around; the wheel scrolls; a click outside closes it.
     Keys:  type to filter the list, Up/Down/PageUp/PageDown/Home/End, Enter (opens the row, or adds what is ticked), Right enters
            a folder, Left or Backspace (with nothing typed) goes up, Space ticks, Ctrl+A ticks all, Tab shows all files, Ctrl+H shows
            hidden ones, Esc clears the filter, then closes.
   ================================================================================================================================ */
#define UI_PK_ROW  34
#define UI_PK_HEAD 54
#define UI_PK_BAR  44
#define UI_PK_FOOT 62
#define UI_PK_SIDE 190

typedef struct {
    char *name;
    int dir;
    int64_t size;
    time_t mtime;
} UiPkEnt;

typedef struct {
    char name[48];
    char path[PATH_MAX];
} UiPkPlace;

typedef struct {
    SDL_Rect p, side, bar, list, up, cancel, ok, extra, all, hid;
    int side_on, tog;                           /* tog: there is room in the foot for All files and Hidden */
} UiPkLay;

static UiPkEnt *ui_pk_e = NULL;
static int ui_pk_n = 0, ui_pk_cap = 0;
static int *ui_pk_vis = NULL, ui_pk_nv = 0;     /* the entries that pass the filter */
static unsigned char *ui_pk_sel = NULL;         /* ticked (Add to Queue), by entry number */
static char ui_pk_dir[PATH_MAX], ui_pk_last[PATH_MAX], ui_pk_filter[128];
static int ui_pk_mode = 0;                      /* 0 = Open File, 1 = Open Folder, 2 = Add to Queue */
static int ui_pk_cur = 0, ui_pk_touched = 0;    /* the row with the cursor; touched = the person has chosen it (not just the first row) */
static int ui_pk_all = 0, ui_pk_hidden = 0;     /* show all files, show hidden ones */
static int ui_pk_hrow = -1, ui_pk_hplace = -1, ui_pk_hbtn = -1;      /* under the mouse */
static double ui_pk_sc = 0.0;                   /* scrolled, in pixels */
static UiPkPlace ui_pk_pl[24];
static int ui_pk_npl = 0;
static struct { SDL_Rect r; int upto; } ui_pk_crumb[24];
static int ui_pk_ncrumb = 0;
static int64_t ui_pk_click_t = 0, ui_pk_nav_t = 0;      /* nav_t: when a folder was last read (a click just after it is the second of a double click) */
static int ui_pk_click_row = -2;

static void ui_pk_close(VideoState *is)
{
    int i;

    ui_pk_open = 0;
    for (i = 0; i < ui_pk_n; i++)
        free(ui_pk_e[i].name);
    free(ui_pk_e);
    free(ui_pk_vis);
    free(ui_pk_sel);
    ui_pk_e = NULL;
    ui_pk_vis = NULL;
    ui_pk_sel = NULL;
    ui_pk_n = ui_pk_cap = ui_pk_nv = 0;
    if (is)
        is->force_refresh = 1;
}

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

static int ui_pk_cmp(const void *a, const void *b)
{
    const UiPkEnt *x = a, *y = b;

    if (x->dir != y->dir)
        return y->dir - x->dir;                 /* the folders first */
    return av_strcasecmp(x->name, y->name);
}

/* The rows that pass the filter (what was typed, anywhere in the name) */
static void ui_pk_refilter(void)
{
    int i;

    ui_pk_nv = 0;
    for (i = 0; i < ui_pk_n; i++)
        if (!ui_pk_filter[0] || av_stristr(ui_pk_e[i].name, ui_pk_filter))
            ui_pk_vis[ui_pk_nv++] = i;
    ui_pk_cur = av_clip(ui_pk_cur, 0, FFMAX(ui_pk_nv - 1, 0));
    ui_pk_sc = 0.0;
}

/* Read a folder. Returns 0 if it cannot be read (nothing changes then). */
static int ui_pk_load(const char *dir)
{
    char real[PATH_MAX], full[PATH_MAX + 300];
    DIR *d;
    struct dirent *de;
    int i;

    if (!realpath(dir, real) || !(d = opendir(real)))
        return 0;
    for (i = 0; i < ui_pk_n; i++)
        free(ui_pk_e[i].name);
    ui_pk_n = 0;
    while ((de = readdir(d))) {
        struct stat st;
        int isdir;

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
        if (ui_pk_n >= ui_pk_cap) {
            int nc = ui_pk_cap ? ui_pk_cap * 2 : 256;
            UiPkEnt *ne = realloc(ui_pk_e, nc * sizeof(*ne));

            if (!ne)
                break;
            ui_pk_e = ne;
            ui_pk_cap = nc;
        }
        ui_pk_e[ui_pk_n].name = strdup(de->d_name);
        ui_pk_e[ui_pk_n].dir = isdir;
        ui_pk_e[ui_pk_n].size = st.st_size;
        ui_pk_e[ui_pk_n].mtime = st.st_mtime;
        ui_pk_n++;
    }
    closedir(d);
    if (ui_pk_n > 1)
        qsort(ui_pk_e, ui_pk_n, sizeof(*ui_pk_e), ui_pk_cmp);
    free(ui_pk_vis);
    free(ui_pk_sel);
    ui_pk_vis = malloc(sizeof(int) * (ui_pk_n + 1));
    ui_pk_sel = calloc(ui_pk_n + 1, 1);
    ui_pk_nav_t = av_gettime_relative();
    snprintf(ui_pk_dir, sizeof(ui_pk_dir), "%s", real);
    snprintf(ui_pk_last, sizeof(ui_pk_last), "%s", real);
    ui_pk_filter[0] = 0;
    ui_pk_cur = 0;
    ui_pk_touched = 0;
    ui_pk_refilter();
    return 1;
}

static void ui_pk_path_of(int e, char *out, size_t size)
{
    snprintf(out, size, "%s%s%s", ui_pk_dir, !strcmp(ui_pk_dir, "/") ? "" : "/", ui_pk_e[e].name);
}

static void ui_pk_up(void)
{
    char parent[PATH_MAX], base[PATH_MAX], *slash;
    int i;

    if (!strcmp(ui_pk_dir, "/"))
        return;
    snprintf(parent, sizeof(parent), "%s", ui_pk_dir);
    slash = strrchr(parent, '/');
    snprintf(base, sizeof(base), "%s", slash ? slash + 1 : "");
    if (slash == parent)
        parent[1] = 0;                          /* the parent is the root */
    else if (slash)
        *slash = 0;
    if (!ui_pk_load(parent))
        return;
    for (i = 0; i < ui_pk_nv; i++)              /* the cursor goes to the folder that was left */
        if (!strcmp(ui_pk_e[ui_pk_vis[i]].name, base)) {
            ui_pk_cur = i;
            ui_pk_touched = 1;
            ui_pk_sc = FFMAX(0.0, (i - 3) * (double)UI_PK_ROW);
            break;
        }
}

static void ui_pk_go(const char *dir)
{
    if (!ui_pk_load(dir))
        fprintf(stderr, "ffplay-custom: cannot read %s\n", dir);
}

static void ui_pk_places(void)
{
    static const char * const names[] = { "Home", "Desktop", "Documents", "Downloads", "Music", "Videos", "Pictures" };
    const char *home = getenv("HOME"), *user = getenv("USER");
    char base[PATH_MAX];
    int i, k;

    ui_pk_npl = 0;
    if (home && home[0]) {
        for (i = 0; i < 7; i++) {
            struct stat st;

            if (i)
                snprintf(base, sizeof(base), "%s/%s", home, names[i]);
            else
                snprintf(base, sizeof(base), "%s", home);
            if (stat(base, &st) == 0 && S_ISDIR(st.st_mode)) {
                snprintf(ui_pk_pl[ui_pk_npl].name, sizeof(ui_pk_pl[0].name), "%s", names[i]);
                snprintf(ui_pk_pl[ui_pk_npl].path, sizeof(ui_pk_pl[0].path), "%s", base);
                ui_pk_npl++;
            }
        }
    }
    for (k = 0; k < 2 && user && user[0]; k++) {       /* the drives that are mounted */
        DIR *d;
        struct dirent *de;

        snprintf(base, sizeof(base), "%s/%s", k ? "/run/media" : "/media", user);
        if (!(d = opendir(base)))
            continue;
        while ((de = readdir(d)) && ui_pk_npl < 22) {
            if (de->d_name[0] == '.')
                continue;
            snprintf(ui_pk_pl[ui_pk_npl].name, sizeof(ui_pk_pl[0].name), "%s", de->d_name);
            snprintf(ui_pk_pl[ui_pk_npl].path, sizeof(ui_pk_pl[0].path), "%s/%s", base, de->d_name);
            ui_pk_npl++;
        }
        closedir(d);
    }
    snprintf(ui_pk_pl[ui_pk_npl].name, sizeof(ui_pk_pl[0].name), "Computer");
    snprintf(ui_pk_pl[ui_pk_npl].path, sizeof(ui_pk_pl[0].path), "/");
    ui_pk_npl++;
}

static void ui_pk_layout(int ww, int wh, UiPkLay *L)
{
    L->p.w = FFMIN(av_clip(ww - 40, 360, 940), ww - 8);
    L->p.h = FFMIN(av_clip(wh - 40, 280, 640), wh - 8);
    L->p.x = (ww - L->p.w) / 2;
    L->p.y = FFMAX((wh - L->p.h) / 2, 4);
    L->side_on = L->p.w >= 640;
    L->side.x = L->p.x;
    L->side.y = L->p.y + UI_PK_HEAD;
    L->side.w = L->side_on ? UI_PK_SIDE : 0;
    L->side.h = L->p.h - UI_PK_HEAD - UI_PK_FOOT;
    L->bar.x = L->p.x + L->side.w;
    L->bar.y = L->p.y + UI_PK_HEAD;
    L->bar.w = L->p.w - L->side.w;
    L->bar.h = UI_PK_BAR;
    L->list.x = L->bar.x;
    L->list.y = L->bar.y + UI_PK_BAR;
    L->list.w = L->bar.w;
    L->list.h = L->p.h - UI_PK_HEAD - UI_PK_BAR - UI_PK_FOOT;
    L->up.x = L->bar.x + 12;
    L->up.y = L->bar.y + 6;
    L->up.w = 56;
    L->up.h = 32;
    L->ok.w = 132;
    L->ok.h = 36;
    L->ok.x = L->p.x + L->p.w - 20 - L->ok.w;
    L->ok.y = L->p.y + L->p.h - UI_PK_FOOT + 13;
    L->cancel = L->ok;
    L->cancel.w = 96;
    L->cancel.x = L->ok.x - 10 - L->cancel.w;
    L->extra = L->ok;
    L->extra.w = L->p.w >= 740 ? 150 : 96;
    L->tog = L->p.w >= (ui_pk_mode == 2 ? 740 : 560);
    L->extra.x = L->cancel.x - 10 - L->extra.w;
    L->all.x = L->p.x + 20;
    L->all.y = L->ok.y;
    L->all.w = 120;
    L->all.h = 36;
    L->hid = L->all;
    L->hid.x = L->all.x + L->all.w + 8;
    L->hid.w = 100;
}

static int ui_pk_ticked(void)
{
    int i, n = 0;

    for (i = 0; i < ui_pk_n; i++)
        n += ui_pk_sel && ui_pk_sel[i];
    return n;
}

/* Send what was chosen and close. what: 'o' opens it now, 'a' adds it to the queue */
static void ui_pk_send(VideoState *is, char what, const char *path)
{
    ui_inbox_send(what, path);
}

static void ui_pk_confirm(VideoState *is, int folder_button)
{
    char path[PATH_MAX + 300];
    int i, sent = 0, e = ui_pk_nv > 0 ? ui_pk_vis[ui_pk_cur] : -1;

    if (ui_pk_mode == 1 || folder_button) {     /* a folder: the one with the cursor if the person chose it, else the one that is open */
        if (e >= 0 && ui_pk_e[e].dir && ui_pk_touched)
            ui_pk_path_of(e, path, sizeof(path));
        else
            snprintf(path, sizeof(path), "%s", ui_pk_dir);
        ui_pk_send(is, ui_pk_mode == 2 ? 'a' : 'o', path);
        sent = 1;
    } else if (ui_pk_mode == 2) {
        for (i = 0; i < ui_pk_n; i++)
            if (ui_pk_sel[i]) {
                ui_pk_path_of(i, path, sizeof(path));
                ui_pk_send(is, 'a', path);
                sent++;
            }
        if (!sent && e >= 0 && !ui_pk_e[e].dir) {
            ui_pk_path_of(e, path, sizeof(path));
            ui_pk_send(is, 'a', path);
            sent = 1;
        }
    } else if (e >= 0 && !ui_pk_e[e].dir) {
        ui_pk_path_of(e, path, sizeof(path));
        ui_pk_send(is, 'o', path);
        sent = 1;
    }
    if (sent)
        ui_pk_close(is);
}

/* Enter or Enter-like: a folder is entered, a file is opened (or, with ticks, they are added) */
static void ui_pk_activate(VideoState *is)
{
    char path[PATH_MAX + 300];
    int e;

    if (ui_pk_nv <= 0) {
        if (ui_pk_mode == 1)
            ui_pk_confirm(is, 0);
        return;
    }
    e = ui_pk_vis[ui_pk_cur];
    if (ui_pk_e[e].dir) {
        ui_pk_path_of(e, path, sizeof(path));
        ui_pk_go(path);
    } else {
        ui_pk_confirm(is, 0);
    }
}

static void ui_pk_show_cursor(const UiPkLay *L)
{
    double top = ui_pk_cur * (double)UI_PK_ROW, bot = top + UI_PK_ROW;

    if (top < ui_pk_sc)
        ui_pk_sc = top;
    else if (bot > ui_pk_sc + L->list.h)
        ui_pk_sc = bot - L->list.h;
}

static void ui_pk_clamp_scroll(const UiPkLay *L)
{
    double mx = FFMAX(0.0, ui_pk_nv * (double)UI_PK_ROW - L->list.h);

    ui_pk_sc = av_clipd(ui_pk_sc, 0.0, mx);
}

static void ui_pk_tick_row(int row)
{
    int e;

    if (row < 0 || row >= ui_pk_nv || ui_pk_mode != 2)
        return;
    e = ui_pk_vis[row];
    if (!ui_pk_e[e].dir)
        ui_pk_sel[e] ^= 1;
}

static void ui_pk_start(int item)
{
    const char *home = getenv("HOME");

    if (ui_pk_open || !window)
        return;
    ui_pk_mode = item == 1 ? 1 : item == 2 ? 2 : 0;
    ui_pk_all = 0;
    ui_pk_hidden = 0;
    ui_pk_hrow = ui_pk_hplace = ui_pk_hbtn = -1;
    ui_pk_click_row = -2;
    ui_pk_places();
    if (!(ui_pk_last[0] && ui_pk_load(ui_pk_last)) && !(home && ui_pk_load(home)) && !ui_pk_load("/")) {
        ui_pick_start_zenity(item);             /* nothing can be read: the system dialog is the way out */
        return;
    }
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

static int ui_pk_in(const SDL_Rect *r, int x, int y)
{
    return x >= r->x && x < r->x + r->w && y >= r->y && y < r->y + r->h;
}

static void ui_pk_button(const SDL_Rect *r, const char *label, int hot, int primary)
{
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    if (primary)
        SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r, 0, 255), av_clip(cfg_bar_g, 0, 255), av_clip(cfg_bar_b, 0, 255), hot ? 255 : 215);
    else
        SDL_SetRenderDrawColor(renderer, 255, 255, 255, hot ? 60 : 30);
    ui_pill(r);
    ui_label_c(r->x + r->w / 2, r->y + r->h / 2, label, 16, 245, 245, 245, 255);
}

static void ui_pk_draw(void)
{
    UiPkLay L;
    SDL_Rect r, clip;
    char buf[PATH_MAX + 64], tmp[PATH_MAX + 64];
    const char *title = ui_pk_mode == 1 ? "Open Folder" : ui_pk_mode == 2 ? "Add to Queue" : "Open File";
    const char *okname = ui_pk_mode == 1 ? "Open folder" : ui_pk_mode == 2 ? "Add" : "Open";
    int ww, wh, i, first, last, mx = 0, my = 0, nt, x, cy, cols_date, cols_size;

    if (!ui_pk_open)
        return;
    SDL_GetWindowSize(window, &ww, &wh);
    ui_pk_layout(ww, wh, &L);
    ui_pk_clamp_scroll(&L);
    ui_glass(&L.p, 28);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    SDL_GetMouseState(&mx, &my);

    /* header */
    ui_label(L.p.x + 26, L.p.y + UI_PK_HEAD / 2 + 2, title, 24, 245, 245, 245, 255);
    snprintf(buf, sizeof(buf), "%s", ui_pk_filter[0] ? ui_pk_filter : "");
    if (ui_pk_filter[0]) {
        int fw;

        snprintf(tmp, sizeof(tmp), "Filter: %s", buf);
        ui_fit_text(tmp, 16, L.p.w / 2 - 40);
        fw = ui_text_width(tmp, 16);
        ui_label(L.p.x + L.p.w - 26 - fw, L.p.y + UI_PK_HEAD / 2 + 2, tmp, 16, av_clip(cfg_bar_r + 60, 0, 255),
                 av_clip(cfg_bar_g + 60, 0, 255), av_clip(cfg_bar_b + 60, 0, 255), 255);
    } else {
        const char *h = "Type to filter";
        int fw = ui_text_width(h, 15);

        ui_label(L.p.x + L.p.w - 26 - fw, L.p.y + UI_PK_HEAD / 2 + 2, h, 15, 170, 170, 170, 255);
    }

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

    /* the path: Up, then the folders from the left, the last ones if they do not all fit */
    ui_pk_button(&L.up, "Up", ui_pk_hbtn == 0 && strcmp(ui_pk_dir, "/") != 0, 0);
    {
        const char *home = getenv("HOME");
        int hl = home ? (int)strlen(home) : 0, starts_home = hl > 1 && !strncmp(ui_pk_dir, home, hl) &&
                 (ui_pk_dir[hl] == '/' || !ui_pk_dir[hl]);
        struct { char label[PATH_MAX]; int upto; } seg[64];
        int ns = 0, pos, sw, total, from = 0, avail = L.bar.w - L.up.w - 12 - 32, len = (int)strlen(ui_pk_dir);
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
        x = L.up.x + L.up.w + 18;
        cy = L.bar.y + L.bar.h / 2;
        ui_pk_ncrumb = 0;
        if (from > 0) {
            ui_label(x, cy, "...", 16, 170, 170, 170, 255);
            x += ui_text_width("...", 16) + gap;
        }
        for (i = from; i < ns; i++) {
            int last_seg = i == ns - 1;

            snprintf(tmp, sizeof(tmp), "%s", seg[i].label);
            ui_fit_text(tmp, 16, FFMAX(avail - (x - L.up.x - L.up.w - 18), 60));
            sw = ui_text_width(tmp, 16);
            if (ui_pk_ncrumb < 24) {
                ui_pk_crumb[ui_pk_ncrumb].r.x = x - 4;
                ui_pk_crumb[ui_pk_ncrumb].r.y = L.bar.y + 4;
                ui_pk_crumb[ui_pk_ncrumb].r.w = sw + 8;
                ui_pk_crumb[ui_pk_ncrumb].r.h = L.bar.h - 8;
                ui_pk_crumb[ui_pk_ncrumb].upto = seg[i].upto;
                ui_pk_ncrumb++;
            }
            ui_label(x, cy, tmp, 16, 245, 245, 245, last_seg ? 255 : 190);
            x += sw;
            if (!last_seg) {
                ui_label(x + 10, cy, ">", 14, 150, 150, 150, 255);
                x += gap;
            }
        }
    }
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 26);
    SDL_RenderDrawLine(renderer, L.list.x, L.list.y, L.list.x + L.list.w, L.list.y);

    /* the list */
    clip = L.list;
    SDL_RenderSetClipRect(renderer, &clip);
    cols_date = L.list.w >= 560;
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
        if (cols_date) {
            char ds[40];
            struct tm tm;
            time_t t = e->mtime;

            localtime_r(&t, &tm);
            strftime(ds, sizeof(ds), "%b %d, %Y", &tm);
            ui_label(right - ui_text_width(ds, 14), cy, ds, 14, 170, 170, 170, 255);
            right -= 130;
        }
        if (cols_size && !e->dir) {
            char ss[32];
            double sz = (double)e->size;

            if (sz < 1000.0)
                snprintf(ss, sizeof(ss), "%d B", (int)sz);
            else if (sz < 1e6)
                snprintf(ss, sizeof(ss), "%.0f kB", sz / 1e3);
            else if (sz < 1e9)
                snprintf(ss, sizeof(ss), "%.1f MB", sz / 1e6);
            else
                snprintf(ss, sizeof(ss), "%.2f GB", sz / 1e9);
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

    /* the foot */
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 26);
    SDL_RenderDrawLine(renderer, L.p.x + 12, L.p.y + L.p.h - UI_PK_FOOT, L.p.x + L.p.w - 12, L.p.y + L.p.h - UI_PK_FOOT);
    if (L.tog && ui_pk_mode != 1) {
        snprintf(tmp, sizeof(tmp), "All files: %s", ui_pk_all ? "On" : "Off");
        ui_label(L.all.x, L.all.y + L.all.h / 2, tmp, 15, ui_pk_hbtn == 5 ? 255 : 190, ui_pk_hbtn == 5 ? 255 : 190,
                 ui_pk_hbtn == 5 ? 255 : 190, 255);
        L.hid.x = L.all.x + ui_text_width(tmp, 15) + 26;
    } else {
        L.hid.x = L.all.x;
    }
    snprintf(tmp, sizeof(tmp), "Hidden: %s", ui_pk_hidden ? "On" : "Off");
    if (L.tog)
        ui_label(L.hid.x, L.hid.y + L.hid.h / 2, tmp, 15, ui_pk_hbtn == 6 ? 255 : 190, ui_pk_hbtn == 6 ? 255 : 190,
             ui_pk_hbtn == 6 ? 255 : 190, 255);
    nt = ui_pk_mode == 2 ? ui_pk_ticked() : 0;
    if (L.tog && ui_pk_mode == 2 && nt > 0 && L.p.w >= 760) {
        snprintf(tmp, sizeof(tmp), "%d ticked", nt);
        ui_label(L.hid.x + ui_text_width("Hidden: Off", 15) + 30, L.hid.y + L.hid.h / 2, tmp, 15,
                 av_clip(cfg_bar_r + 60, 0, 255), av_clip(cfg_bar_g + 60, 0, 255), av_clip(cfg_bar_b + 60, 0, 255), 255);
    }
    if (ui_pk_mode == 2) {
        snprintf(tmp, sizeof(tmp), "%s", L.p.w >= 740 ? "Add this folder" : "Folder");
        ui_pk_button(&L.extra, tmp, ui_pk_hbtn == 3, 0);
    }
    ui_pk_button(&L.cancel, "Cancel", ui_pk_hbtn == 2, 0);
    if (ui_pk_mode == 2 && nt > 0) {
        snprintf(tmp, sizeof(tmp), "Add %d", nt);
        ui_pk_button(&L.ok, tmp, ui_pk_hbtn == 1, 1);
    } else {
        ui_pk_button(&L.ok, okname, ui_pk_hbtn == 1, 1);
    }
}

static int ui_pk_mouse(VideoState *is, SDL_Event *ev)
{
    UiPkLay L;
    int ww, wh, x, y, i;

    SDL_GetWindowSize(window, &ww, &wh);
    ui_pk_layout(ww, wh, &L);
    x = ev->type == SDL_MOUSEMOTION ? ev->motion.x : ev->button.x;
    y = ev->type == SDL_MOUSEMOTION ? ev->motion.y : ev->button.y;
    ui_wake();
    ui_pk_hrow = ui_pk_hplace = ui_pk_hbtn = -1;
    if (ui_pk_in(&L.list, x, y))
        ui_pk_hrow = (int)((y - L.list.y + ui_pk_sc) / UI_PK_ROW);
    if (ui_pk_hrow >= ui_pk_nv)
        ui_pk_hrow = -1;
    if (L.side_on && ui_pk_in(&L.side, x, y) && y >= L.side.y + 8 && (y - L.side.y - 8) / 36 < ui_pk_npl)
        ui_pk_hplace = (y - L.side.y - 8) / 36;
    if (ui_pk_in(&L.up, x, y))
        ui_pk_hbtn = 0;
    else if (ui_pk_in(&L.ok, x, y))
        ui_pk_hbtn = 1;
    else if (ui_pk_in(&L.cancel, x, y))
        ui_pk_hbtn = 2;
    else if (ui_pk_mode == 2 && ui_pk_in(&L.extra, x, y))
        ui_pk_hbtn = 3;
    else if (L.tog && ui_pk_mode != 1 && x >= L.all.x && x < L.all.x + 110 && y >= L.all.y && y < L.all.y + L.all.h)
        ui_pk_hbtn = 5;
    else if (L.tog && y >= L.hid.y && y < L.hid.y + L.hid.h && x >= (ui_pk_mode != 1 ? L.all.x + 130 : L.all.x) &&
             x < (ui_pk_mode != 1 ? L.all.x + 130 : L.all.x) + 110)
        ui_pk_hbtn = 6;

    if (ev->type == SDL_MOUSEBUTTONDOWN) {
        if (ev->button.button != SDL_BUTTON_LEFT) {
            if (ev->button.button == SDL_BUTTON_RIGHT && ui_pk_in(&L.p, x, y))
                ui_pk_up();                     /* a right click inside goes up one folder */
        } else if (!ui_pk_in(&L.p, x, y)) {
            ui_pk_close(is);                    /* a click outside closes it */
        } else if (ui_pk_hbtn == 0) {
            ui_pk_up();
        } else if (ui_pk_hbtn == 1) {
            ui_pk_confirm(is, 0);
        } else if (ui_pk_hbtn == 2) {
            ui_pk_close(is);
        } else if (ui_pk_hbtn == 3) {
            ui_pk_confirm(is, 1);
        } else if (ui_pk_hbtn == 5 || ui_pk_hbtn == 6) {
            char keep[PATH_MAX];

            if (ui_pk_hbtn == 5)
                ui_pk_all = !ui_pk_all;
            else
                ui_pk_hidden = !ui_pk_hidden;
            snprintf(keep, sizeof(keep), "%s", ui_pk_dir);
            ui_pk_load(keep);
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

/* Keys, typing and the wheel while the picker is open. Returns 1 if the event was used. */
static int ui_pk_event(VideoState *is, SDL_Event *ev)
{
    UiPkLay L;
    int ww, wh, rows;

    if (!ui_pk_open)
        return 0;
    SDL_GetWindowSize(window, &ww, &wh);
    ui_pk_layout(ww, wh, &L);
    rows = FFMAX(L.list.h / UI_PK_ROW - 1, 1);
    if (is)
        is->force_refresh = 1;
    ui_wake();

    if (ev->type == SDL_TEXTINPUT) {
        const char *t = ev->text.text;
        size_t n = strlen(ui_pk_filter);

        if (!ui_pk_filter[0] && !strcmp(t, " "))
            return 1;                           /* the space bar ticks; a filter does not start with a space */
        if ((unsigned char)t[0] >= 32 && n + strlen(t) < sizeof(ui_pk_filter) - 1) {
            strcat(ui_pk_filter, t);
            ui_pk_cur = 0;
            ui_pk_touched = 0;
            ui_pk_refilter();
        }
        return 1;
    }
    if (ev->type == SDL_MOUSEWHEEL) {
        float dy = ev->wheel.preciseY;

        if (ev->wheel.direction == SDL_MOUSEWHEEL_FLIPPED)
            dy = -dy;
        ui_pk_sc -= dy * UI_PK_ROW * 2.5;
        ui_pk_clamp_scroll(&L);
        return 1;
    }
    if (ev->type == SDL_KEYDOWN) {
        SDL_Keycode k = ev->key.keysym.sym;
        int ctrl = !!(ev->key.keysym.mod & KMOD_CTRL), alt = !!(ev->key.keysym.mod & KMOD_ALT);

        if (k == SDLK_ESCAPE) {
            if (ui_pk_filter[0]) {
                ui_pk_filter[0] = 0;
                ui_pk_refilter();
            } else {
                ui_pk_close(is);
            }
        } else if (k == SDLK_DOWN || k == SDLK_UP || k == SDLK_PAGEDOWN || k == SDLK_PAGEUP || k == SDLK_HOME || k == SDLK_END) {
            int d = k == SDLK_DOWN ? 1 : k == SDLK_UP ? -1 : k == SDLK_PAGEDOWN ? rows : k == SDLK_PAGEUP ? -rows : 0;

            if (alt && k == SDLK_UP) {
                ui_pk_up();
                return 1;
            }
            ui_pk_cur = k == SDLK_HOME ? 0 : k == SDLK_END ? ui_pk_nv - 1 : ui_pk_cur + d;
            ui_pk_cur = av_clip(ui_pk_cur, 0, FFMAX(ui_pk_nv - 1, 0));
            ui_pk_touched = 1;
            ui_pk_show_cursor(&L);
            ui_pk_clamp_scroll(&L);
        } else if (k == SDLK_RETURN || k == SDLK_KP_ENTER) {
            if (ui_pk_mode == 2 && ui_pk_ticked() > 0)
                ui_pk_confirm(is, 0);
            else
                ui_pk_activate(is);
        } else if (k == SDLK_RIGHT) {
            if (ui_pk_nv > 0 && ui_pk_e[ui_pk_vis[ui_pk_cur]].dir)
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
            ui_pk_refilter();
        } else if (k == SDLK_SPACE && !ui_pk_filter[0]) {
            if (ui_pk_mode == 2) {
                ui_pk_tick_row(ui_pk_cur);
                ui_pk_cur = FFMIN(ui_pk_cur + 1, FFMAX(ui_pk_nv - 1, 0));
                ui_pk_touched = 1;
                ui_pk_show_cursor(&L);
                ui_pk_clamp_scroll(&L);
            }
        } else if (ctrl && k == SDLK_a && ui_pk_mode == 2) {
            int i;

            for (i = 0; i < ui_pk_nv; i++)
                if (!ui_pk_e[ui_pk_vis[i]].dir)
                    ui_pk_sel[ui_pk_vis[i]] = 1;
        } else if (ctrl && k == SDLK_h) {
            char keep[PATH_MAX];

            ui_pk_hidden = !ui_pk_hidden;
            snprintf(keep, sizeof(keep), "%s", ui_pk_dir);
            ui_pk_load(keep);
        } else if (k == SDLK_TAB && ui_pk_mode != 1) {
            char keep[PATH_MAX];

            ui_pk_all = !ui_pk_all;
            snprintf(keep, sizeof(keep), "%s", ui_pk_dir);
            ui_pk_load(keep);
        }
        return 1;                               /* a picker that is open uses every key */
    }
    return ev->type == SDL_KEYUP;
}

static void refresh_loop_wait_event(VideoState *is, SDL_Event *event) {''')

# ---------------------------------------------------------------- the seek code nothing uses
patch("dead seek code: the held keys and the preview picture", r'''/* Send the waiting key seek when the one before it has landed (its picture and its sound are there) */
static void ui_ks_tick(VideoState *is)
{
    int64_t now;

    if (!ui_ks_want)
        return;
    if (!is || !is->ic || is != ui_ks_is) {
        ui_ks_want = 0;
        return;
    }
    now = av_gettime_relative();
    if (now < ui_ks_next)
        return;
    if ((is->seek_req || is->prec_v || is->prec_a) && now - ui_ks_issued < 1500000) {
        if (!is->seek_req && (is->prec_v || is->prec_a) && ui_ks_target > is->prec_target &&
            ui_ks_target - is->prec_target < 20.0) {
            /* still skipping toward the last target: carry on to the new one, without a new start from a key frame
               (the pictures between are skipped as before, but the decoder never goes back) */
            is->prec_target = ui_ks_target;
            is->seek_pos = (int64_t)(ui_ks_target * AV_TIME_BASE);      /* the bar shows it */
            ui_ks_issued = now;
            ui_ks_want = 0;
        }
        return;                         /* still on its way: more steps add up meanwhile */
    }
    ui_precise_next = 1;
    stream_seek(is, (int64_t)(ui_ks_target * AV_TIME_BASE), 0, 0);
    ui_ks_issued = now;
    ui_ks_next = now + 10000;
    ui_ks_want = 0;
}

/* While a seek key is held or the bar is dragged and the seek is still on its way, the picture of the nearest ready
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
    {                                           /* v37: a preview is a small picture stretched over the window, so it is only worth it when the jump is
                                                   bigger than the gap between two previews; a small step shows the real, sharp frames */
        double cur = get_master_clock(is), gap = FFMAX(2.0, 1.5 * ui_th.dur / n);

        if (!isnan(cur) && fabs(av_clipd(f, 0.0, 1.0) * ui_th.dur - (cur - ui_th.start / (double)AV_TIME_BASE)) < gap)
            return 0;
    }
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
''', "")
patch("dead seek code: declaration", r'''static int ui_scrub_draw(VideoState *is, const SDL_Rect *rect);

''', "")
patch("dead seek code: variables", r'''/* Seeking with the keys or the wheel: the bar follows every step at once, and a seek is sent as soon as the one before it has
   shown its picture, so pictures keep coming while a key is held */
static int ui_ks_want = 0;              /* 1 = a seek to ui_ks_target is waiting to be sent */
static double ui_ks_target = 0.0;       /* seconds: where the steps have taken it (the last one sent, when none waits) */
static int64_t ui_ks_next = 0, ui_ks_issued = 0;
static VideoState *ui_ks_is = NULL;     /* the stream the waiting seek is for (a new item cancels it) */

''', "")
patch("dead seek code: the bar", r'''        if (!seek_by_bytes && ui_ks_want)
            pos = ui_ks_target;                 /* the steps of the keys, before they are sent */
        else if (!seek_by_bytes && is->seek_req)''', r'''        if (!seek_by_bytes && is->seek_req)''')
patch("dead seek code: the tick", r'''        UI_TIMED(ui_ks_tick(is));
''', "")

if fails:
    print("\n%d edit(s) failed. Nothing written." % len(fails))
    sys.exit(1)
open(PATH, "w").write(src)
print("\nAll edits applied to " + PATH)
