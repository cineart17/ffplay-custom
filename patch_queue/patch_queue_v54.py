#!/usr/bin/env python3
# patch_queue_v54.py (round 2): playlists with rename, "Add to playlist", the reworked Library sidebar, redrawn icons, solid drop down arrows.
# Run it from ~/build/ffmpeg-6.1.1 (it patches fftools/ffplay.c in place; make your own backup first, as usual). Applies on top of v53.
import sys, os

PATH = sys.argv[1] if len(sys.argv) > 1 else "fftools/ffplay.c"
src = open(PATH, encoding="utf-8").read()
if "v54: playlists" in src:
    sys.exit("Already applied: patch_queue_v54 (" + PATH + ")")


def R(old, new, what):
    global src
    n = src.count(old)
    if n != 1:
        sys.exit("FAILED: %s (anchor found %d times, expected 1). Nothing was written." % (what, n))
    src = src.replace(old, new)
    print("ok: " + what)


# ------------------------------------------------------------------ icons
R("""       UI_IC_ARW_L, UI_IC_ARW_R, UI_IC_ARW_U, UI_IC_ARW_D, UI_IC_PLAY,
       UI_IC_N };""",
  """       UI_IC_ARW_L, UI_IC_ARW_R, UI_IC_ARW_U, UI_IC_ARW_D, UI_IC_PLAY,
       UI_IC_TRI_R, UI_IC_TRI_D, UI_IC_VIDEO, UI_IC_MUSIC, UI_IC_USB, UI_IC_DISK, UI_IC_PLAYLIST, UI_IC_PLNEW,      /* v54 */
       UI_IC_N };""", "icon enum")

R("""    case UI_IC_SEARCH:
        ic_arc(10.5f, 10.5f, 6.5f, 0, 360);""",
  """    case UI_IC_TRI_R: {                         /* v54: a solid arrow head for the drop downs: no line, no outline */
        int k;

        for (k = 0; k < 10; k++) {
            float x = 8.4f + k * 0.85f, hh = 5.0f * (1.0f - k / 10.5f);

            ic_seg(x, 12.0f - hh, x, 12.0f + hh);
        }
        break;
    }
    case UI_IC_TRI_D: {
        int k;

        for (k = 0; k < 10; k++) {
            float y = 8.4f + k * 0.85f, hh = 5.0f * (1.0f - k / 10.5f);

            ic_seg(12.0f - hh, y, 12.0f + hh, y);
        }
        break;
    }
    case UI_IC_VIDEO:                           /* a screen with a solid play mark */
        ic_rrect(3, 5, 18, 14, 3.4f);
        ic_tri_fill(10.4f, 9.6f, 10.4f, 14.4f, 14.8f, 12.0f);
        break;
    case UI_IC_MUSIC: {                         /* one note: a solid head, a stem and a flag */
        static const float flag[] = { 10.9f, 4.6f, 13.6f, 5.6f, 15.8f, 7.6f, 16.6f, 10.4f };

        ic_arc(8.4f, 17.4f, 1.0f, 0, 360);
        ic_arc(8.4f, 17.4f, 2.1f, 0, 360);
        ic_seg(10.9f, 16.6f, 10.9f, 4.6f);
        ic_poly(flag, 4, 0);
        break;
    }
    case UI_IC_USB:                             /* an external drive: the box with its plug */
        ic_rrect(2.5f, 7.5f, 13.5f, 9, 2.8f);
        ic_seg(16, 10.2f, 21, 10.2f);
        ic_seg(16, 13.8f, 21, 13.8f);
        ic_seg(21, 10.2f, 21, 13.8f);
        ic_arc(6.3f, 12, 0.5f, 0, 360);
        break;
    case UI_IC_DISK:                            /* a drive inside the computer: a flat box with a light */
        ic_rrect(3, 7, 18, 10, 3.2f);
        ic_seg(6.5f, 12, 11, 12);
        ic_arc(17.2f, 12, 0.5f, 0, 360);
        break;
    case UI_IC_PLAYLIST:                        /* lines with a solid play mark */
        ic_seg(4, 6.5f, 20, 6.5f);
        ic_seg(4, 11.5f, 12.5f, 11.5f);
        ic_seg(4, 16.5f, 12.5f, 16.5f);
        ic_tri_fill(15.6f, 13.6f, 15.6f, 19.4f, 19.6f, 16.5f);
        break;
    case UI_IC_PLNEW:                           /* lines with a plus: a new playlist */
        ic_seg(4, 6.5f, 20, 6.5f);
        ic_seg(4, 11.5f, 12.5f, 11.5f);
        ic_seg(4, 16.5f, 10.5f, 16.5f);
        ic_seg(17, 13, 17, 20);
        ic_seg(13.5f, 16.5f, 20.5f, 16.5f);
        break;
    case UI_IC_SEARCH:
        ic_arc(10.5f, 10.5f, 6.5f, 0, 360);""", "icon shapes")

R("""static void ui_icon_build(int id)
{
    ui_is_n = 0;""",
  """/* v54: a solid triangle, made of thin lines one under the other (the drawing has no fill, only strokes) */
static void ic_tri_fill(float x0, float y0, float x1, float y1, float x2, float y2)
{
    float px[3] = { x0, x1, x2 }, py[3] = { y0, y1, y2 };
    float ymin = FFMIN3(y0, y1, y2), ymax = FFMAX3(y0, y1, y2), y;
    int i;

    for (y = ymin; y <= ymax + 0.0001f; y += 0.7f) {
        float lo = 1e9f, hi = -1e9f;

        for (i = 0; i < 3; i++) {
            float xa = px[i], ya = py[i], xb = px[(i + 1) % 3], yb = py[(i + 1) % 3], x;

            if (ya == yb || y < FFMIN(ya, yb) || y > FFMAX(ya, yb))
                continue;
            x = xa + (y - ya) * (xb - xa) / (yb - ya);
            lo = FFMIN(lo, x);
            hi = FFMAX(hi, x);
        }
        if (hi >= lo)
            ic_seg(lo, y, hi, y);
    }
}

static void ui_icon_build(int id)
{
    ui_is_n = 0;""", "icon fill helper")

# ------------------------------------------------------------------ forward declarations, draw, refresh and event hooks
R("""static int ui_pk_event(VideoState *is, SDL_Event *ev);
""",
  """static int ui_pk_event(VideoState *is, SDL_Event *ev);
/* v54: the "Add to playlist" chooser (see the playlists section before the file picker) */
static int ui_apl_open = 0;
static void ui_apl_draw(void);
static int ui_apl_event(VideoState *is, SDL_Event *ev);
static int ui_apl_busy(void);
static void ui_apl_for_path(const char *path, int x, int y);
""", "forward declarations")

R("""    ui_pk_draw();
    ui_ink_dark = 0;
    ui_present();""",
  """    ui_pk_draw();
    ui_ink_dark = 0;
    ui_apl_draw();                              /* v54: over everything, the picker included */
    ui_ink_dark = 0;
    ui_present();""", "draw hook")

R("""        if (ui_q_autoscroll() || ui_pk_busy())
            is->force_refresh = 1;""",
  """        if (ui_q_autoscroll() || ui_pk_busy() || ui_apl_busy())
            is->force_refresh = 1;""", "refresh hook")

R("""            if (ev.type != SDL_QUIT && ui_pk_event(NULL, &ev))      /* v44 */
                continue;""",
  """            if (ev.type != SDL_QUIT && ui_apl_event(NULL, &ev))     /* v54: the playlist chooser comes first */
                continue;
            if (ev.type != SDL_QUIT && ui_pk_event(NULL, &ev))      /* v44 */
                continue;""", "idle event hook")

R("""        if (ui_pk_event(cur_stream, &event))    /* v44: the picker uses the keys, the typing and the wheel while it is open */
            continue;""",
  """        if (ui_apl_event(cur_stream, &event))   /* v54: the playlist chooser comes first */
            continue;
        if (ui_pk_event(cur_stream, &event))    /* v44: the picker uses the keys, the typing and the wheel while it is open */
            continue;""", "event hook")

# ------------------------------------------------------------------ the queue item menu: Remove, Sleep, Add to playlist
R("""    if (i == 0)
        return "Remove from queue";
    return ui_ctx_name && ui_ctx_name == q_sleep_item ? "Cancel sleep after item" : "Sleep after this item";""",
  """    if (i == 0)
        return "Remove from queue";
    if (i == 2)
        return "Add to playlist";               /* v54 */
    return ui_ctx_name && ui_ctx_name == q_sleep_item ? "Cancel sleep after item" : "Sleep after this item";""", "queue menu label")
R("""    r.h = 2 * UI_CTX_ROW + 16;
    r.x = av_clip(ui_ctx_x, 8, FFMAX(ww - r.w - 8, 8));""",
  """    r.h = 3 * UI_CTX_ROW + 16;
    r.x = av_clip(ui_ctx_x, 8, FFMAX(ww - r.w - 8, 8));""", "queue menu height")
R("""y >= r->y + 8 + 2 * UI_CTX_ROW)
        return -1;""", """y >= r->y + 8 + 3 * UI_CTX_ROW)
        return -1;""", "queue menu hit")
R("""    for (i = 0; i < 2; i++) {
        row_y = r.y + 8 + i * UI_CTX_ROW;
        ui_icon(i ? UI_IC_MOON : UI_IC_TRASH, r.x + 28, row_y + UI_CTX_ROW / 2, 18, 240, 240, 240,""",
  """    for (i = 0; i < 3; i++) {
        row_y = r.y + 8 + i * UI_CTX_ROW;
        ui_icon(i == 2 ? UI_IC_PLAYLIST : i ? UI_IC_MOON : UI_IC_TRASH, r.x + 28, row_y + UI_CTX_ROW / 2, 18, 240, 240, 240,""", "queue menu draw")
R("""/* 0 = remove the item, 1 = sleep after it (or stop doing that) */""",
  """/* 0 = remove the item, 1 = sleep after it (or stop doing that), 2 = add it to a playlist (v54) */""", "queue action comment")
R("""        if (was_playing)
            ui_end_current(is);     /* the next item takes its place */
    } else {
        q_sleep_end = 0;""",
  """        if (was_playing)
            ui_end_current(is);     /* the next item takes its place */
    } else if (act == 2) {
        ui_apl_for_path(q_items[idx], ui_ctx_x, ui_ctx_y);
    } else {
        q_sleep_end = 0;""", "queue action")

# ------------------------------------------------------------------ the tile menu: Add to playlist
R("""static int ui_tvc_x = 0, ui_tvc_y = 0, ui_tvc_hover = -1, ui_tvc_n = 0, ui_tvc_act[4];""",
  """static int ui_tvc_x = 0, ui_tvc_y = 0, ui_tvc_hover = -1, ui_tvc_n = 0, ui_tvc_act[5];""", "tile menu acts")
R("""static const char * const ui_tvc_label[4] = { "Play", "Play next", "Add to queue", "Remove from queue" };""",
  """static const char * const ui_tvc_label[5] = { "Play", "Play next", "Add to queue", "Remove from queue", "Add to playlist" };""", "tile menu labels")
R("""    default:                                    /* Remove from queue */
        idx = ui_tv_qindex(path);""",
  """    case 4:                                     /* v54: Add to playlist */
        ui_apl_for_path(path, ui_tvc_x, ui_tvc_y);
        break;
    default:                                    /* Remove from queue */
        idx = ui_tv_qindex(path);""", "tile menu action")
R("""    else if (qi != q_pos)
        ui_tvc_act[n++] = 3;                    /* Remove from queue */
    ui_tvc_n = n;""",
  """    else if (qi != q_pos)
        ui_tvc_act[n++] = 3;                    /* Remove from queue */
    ui_tvc_act[n++] = 4;                        /* v54: Add to playlist */
    ui_tvc_n = n;""", "tile menu items")

# ------------------------------------------------------------------ playlists (storage) and the "Add to playlist" chooser
PL_BLOCK = r'''/* ================================================================================================================================
   v54: playlists. A playlist is a plain .m3u file in ~/.config/ffplay-custom/playlists/ (one path per line), so other players can read
   it and it can be edited by hand. "Add to playlist" (file picker, queue menu, tile menu) opens the small chooser below: the playlists
   that exist, and "New playlist..." which asks for a name. A folder that is added brings every song and video inside it (and inside
   its folders), in name order. A file that is already in a playlist is not added twice.
   ================================================================================================================================ */
#define PL_NAME  96
#define PL_MAX   64
#define PL_FILES 5000

/*PLSTART*/
static int pl_dir(char *out, size_t size)       /* the folder of the playlists; made if it is not there yet */
{
    const char *home = getenv("HOME");
    char p[PATH_MAX];

    if (!home || !home[0])
        return 0;
    snprintf(p, sizeof(p), "%.4000s/.config", home);
    mkdir(p, 0755);
    snprintf(p, sizeof(p), "%.4000s/.config/ffplay-custom", home);
    mkdir(p, 0755);
    snprintf(out, size, "%.4000s/.config/ffplay-custom/playlists", home);
    mkdir(out, 0755);
    return 1;
}

static int pl_file(const char *name, char *out, size_t size)
{
    char dir[PATH_MAX];

    if (!pl_dir(dir, sizeof(dir)))
        return 0;
    snprintf(out, size, "%.4000s/%.200s.m3u", dir, name);
    return 1;
}

static void pl_clean(char *name)                /* in place: something that is safe as a file name, at most 80 bytes */
{
    char *s, *d = name;
    size_t n;

    for (s = name; *s; s++) {
        unsigned char c = *s;

        *d++ = (c < 32 || c == 127 || c == '/' || c == '\\') ? '_' : (char)c;
    }
    *d = 0;
    s = name;
    while (*s == ' ' || *s == '.')
        s++;
    if (s != name)
        memmove(name, s, strlen(s) + 1);
    n = strlen(name);
    if (n > 80) {
        n = 80;
        while (n && ((unsigned char)name[n] & 0xC0) == 0x80)
            n--;
        name[n] = 0;
    }
    while (n && name[n - 1] == ' ')
        name[--n] = 0;
}

static char pl_names[PL_MAX][PL_NAME];          /* the playlists that exist, A to Z (made by pl_list) */
static int pl_n = 0;

static int pl_name_cmp(const void *a, const void *b)
{
    return av_strcasecmp((const char *)a, (const char *)b);
}

static void pl_list(void)
{
    char dir[PATH_MAX];
    DIR *d;
    struct dirent *de;

    pl_n = 0;
    if (!pl_dir(dir, sizeof(dir)) || !(d = opendir(dir)))
        return;
    while ((de = readdir(d)) && pl_n < PL_MAX) {
        size_t n = strlen(de->d_name);

        if (de->d_name[0] == '.' || n < 5 || n - 4 >= PL_NAME || av_strcasecmp(de->d_name + n - 4, ".m3u"))
            continue;
        snprintf(pl_names[pl_n], PL_NAME, "%.*s", (int)(n - 4), de->d_name);
        pl_n++;
    }
    closedir(d);
    if (pl_n > 1)
        qsort(pl_names, pl_n, PL_NAME, pl_name_cmp);
}

static void pl_free(char **v, int n)
{
    int i;

    for (i = 0; i < n; i++)
        free(v[i]);
    free(v);
}

static int pl_push(char ***v, int *n, int *cap, const char *path)
{
    if (*n >= *cap) {
        int nc = *cap ? *cap * 2 : 64;
        char **t = realloc(*v, nc * sizeof(**v));

        if (!t)
            return 0;
        *v = t;
        *cap = nc;
    }
    if (!((*v)[*n] = strdup(path)))
        return 0;
    (*n)++;
    return 1;
}

/* The paths of a playlist, in order (relative lines are taken from the playlists' own folder). Returns how many; free with pl_free. */
static int pl_load(const char *name, char ***out)
{
    char file[PATH_MAX + 128], dir[PATH_MAX], line[PATH_MAX + 8], full[PATH_MAX * 2 + 16];
    char **v = NULL;
    int n = 0, cap = 0;
    FILE *f;

    *out = NULL;
    if (!pl_file(name, file, sizeof(file)) || !pl_dir(dir, sizeof(dir)) || !(f = fopen(file, "r")))
        return 0;
    while (n < 20000 && fgets(line, sizeof(line), f)) {
        line[strcspn(line, "\r\n")] = 0;
        if (!line[0] || line[0] == '#')
            continue;
        if (line[0] == '/')
            snprintf(full, sizeof(full), "%s", line);
        else
            snprintf(full, sizeof(full), "%s/%s", dir, line);
        if (!pl_push(&v, &n, &cap, full))
            break;
    }
    fclose(f);
    *out = v;
    return n;
}

static int pl_create(const char *name)          /* 1 if the playlist is there afterwards */
{
    char file[PATH_MAX + 128];
    struct stat st;
    FILE *f;

    if (!name[0] || !pl_file(name, file, sizeof(file)))
        return 0;
    if (stat(file, &st) == 0)
        return 1;
    if (!(f = fopen(file, "w")))
        return 0;
    fputs("#EXTM3U\n", f);
    fclose(f);
    return 1;
}

static int pl_delete(const char *name)
{
    char file[PATH_MAX + 128];

    return pl_file(name, file, sizeof(file)) && unlink(file) == 0;
}

static int pl_exists(const char *name)
{
    char file[PATH_MAX + 128];
    struct stat st;

    return pl_file(name, file, sizeof(file)) && stat(file, &st) == 0;
}

static int pl_rename(const char *from, const char *to)
{
    char a[PATH_MAX + 128], b[PATH_MAX + 128];

    return pl_file(from, a, sizeof(a)) && pl_file(to, b, sizeof(b)) && rename(a, b) == 0;
}

/* A file, or every song and video inside a folder and the folders in it (name order), added to the list v */
static void pl_collect(const char *path, char ***v, int *n, int *cap, int depth)
{
    struct stat st;
    DIR *d;
    struct dirent *de;
    char **names = NULL, full[PATH_MAX + 300];
    int nn = 0, nc = 0, i;

    if (*n >= PL_FILES || stat(path, &st) != 0)
        return;
    if (!S_ISDIR(st.st_mode)) {
        if (S_ISREG(st.st_mode))
            pl_push(v, n, cap, path);
        return;
    }
    if (depth > 4 || !(d = opendir(path)))
        return;
    while ((de = readdir(d))) {
        if (de->d_name[0] == '.')
            continue;
        if (nn >= nc) {
            char **t = realloc(names, (nc ? nc * 2 : 64) * sizeof(*names));

            if (!t)
                break;
            names = t;
            nc = nc ? nc * 2 : 64;
        }
        if ((names[nn] = strdup(de->d_name)))
            nn++;
    }
    closedir(d);
    if (nn > 1)
        qsort(names, nn, sizeof(*names), name_cmp);
    for (i = 0; i < nn; i++) {
        struct stat s2;

        snprintf(full, sizeof(full), "%s%s%s", path, !strcmp(path, "/") ? "" : "/", names[i]);
        if (*n < PL_FILES && stat(full, &s2) == 0) {
            if (S_ISDIR(s2.st_mode))
                pl_collect(full, v, n, cap, depth + 1);
            else if (S_ISREG(s2.st_mode) && is_media_file(names[i]))
                pl_push(v, n, cap, full);
        }
        free(names[i]);
    }
    free(names);
}

/* Append what is not in the playlist yet. Returns how many were added. */
static int pl_add_files(const char *name, char **files, int nf)
{
    char file[PATH_MAX + 128], **have = NULL;
    int nh, i, j, added = 0;
    FILE *f;

    if (!pl_file(name, file, sizeof(file)))
        return 0;
    nh = pl_load(name, &have);
    if (!(f = fopen(file, "a"))) {
        pl_free(have, nh);
        return 0;
    }
    for (i = 0; i < nf; i++) {
        int dup = 0;

        for (j = 0; j < nh && !dup; j++)
            dup = !strcmp(have[j], files[i]);
        for (j = 0; j < i && !dup; j++)
            dup = !strcmp(files[j], files[i]);
        if (dup)
            continue;
        fprintf(f, "%s\n", files[i]);
        added++;
    }
    fclose(f);
    pl_free(have, nh);
    return added;
}

/* Take the first line that is this path out of the playlist */
static int pl_remove_path(const char *name, const char *path)
{
    char file[PATH_MAX + 128], **v = NULL;
    int n, i, done = 0;
    FILE *f;

    if (!pl_file(name, file, sizeof(file)))
        return 0;
    n = pl_load(name, &v);
    if (!(f = fopen(file, "w"))) {
        pl_free(v, n);
        return 0;
    }
    fputs("#EXTM3U\n", f);
    for (i = 0; i < n; i++) {
        if (!done && !strcmp(v[i], path)) {
            done = 1;
            continue;
        }
        fprintf(f, "%s\n", v[i]);
    }
    fclose(f);
    pl_free(v, n);
    return done;
}
/*PLEND*/

static void ui_pk_pl_changed(const char *name);         /* defined with the picker: its list and its tree follow what changed */
static void ui_pk_pl_renamed(const char *from, const char *to);

/* ----- the chooser ----- */
#define UI_APL_ROW 38
#define UI_APL_VIS 8
static int ui_apl_x = 0, ui_apl_y = 0, ui_apl_hot = -1, ui_apl_naming = 0, ui_apl_sc = 0, ui_apl_w = 260;
static char **ui_apl_paths = NULL;                      /* what is going to be added */
static int ui_apl_np = 0, ui_apl_cap = 0, ui_apl_nn = 0;
static char ui_apl_text[PL_NAME + 8];
static char ui_apl_ren[PL_NAME];                        /* not empty: the playlist with this name is being renamed */
static char ui_apl_names[PL_MAX][PL_NAME];
static char ui_apl_toast[260];
static int64_t ui_apl_toast_until = 0;

static void ui_apl_say(const char *fmt, ...)            /* a short message at the bottom of the window */
{
    va_list ap;

    va_start(ap, fmt);
    vsnprintf(ui_apl_toast, sizeof(ui_apl_toast), fmt, ap);
    va_end(ap);
    ui_apl_toast_until = av_gettime_relative() + 2600000;
}

static void ui_apl_clear(void)
{
    pl_free(ui_apl_paths, ui_apl_np);
    ui_apl_paths = NULL;
    ui_apl_np = ui_apl_cap = 0;
}

static void ui_apl_begin(void)                          /* then ui_apl_add_path for everything, then ui_apl_show */
{
    ui_apl_clear();
    ui_apl_ren[0] = 0;
}

static void ui_apl_add_path(const char *path)
{
    pl_push(&ui_apl_paths, &ui_apl_np, &ui_apl_cap, path);
}

static void ui_apl_show(int x, int y)                   /* with nothing to add it is "New playlist" straight away */
{
    int i;

    pl_list();
    memcpy(ui_apl_names, pl_names, sizeof(ui_apl_names));
    ui_apl_nn = pl_n;
    ui_apl_w = ui_text_width("New playlist...", 18);
    for (i = 0; i < ui_apl_nn; i++)
        ui_apl_w = FFMAX(ui_apl_w, ui_text_width(ui_apl_names[i], 18));
    ui_apl_w = av_clip(ui_apl_w + 92, 240, 440);
    ui_apl_x = x;
    ui_apl_y = y;
    ui_apl_hot = -1;
    ui_apl_sc = 0;
    ui_apl_naming = ui_apl_np == 0;
    ui_apl_text[0] = 0;
    ui_apl_open = 1;
    SDL_StartTextInput();
    ui_wake();
}

static void ui_apl_rename(const char *name, int x, int y)       /* the name box, with the old name in it */
{
    ui_apl_begin();
    ui_apl_show(x, y);
    snprintf(ui_apl_ren, sizeof(ui_apl_ren), "%.95s", name);
    snprintf(ui_apl_text, sizeof(ui_apl_text), "%.95s", name);
}

static void ui_apl_for_path(const char *path, int x, int y)
{
    ui_apl_begin();
    ui_apl_add_path(path);
    ui_apl_show(x, y);
}

static void ui_apl_close(void)
{
    ui_apl_open = 0;
    ui_apl_naming = 0;
    ui_apl_hot = -1;
    ui_apl_ren[0] = 0;
    ui_apl_clear();
}

static int ui_apl_busy(void)
{
    return ui_apl_open || av_gettime_relative() < ui_apl_toast_until;
}

static int ui_apl_rows(void)                            /* rows on show: "New playlist..." and the playlists, at most UI_APL_VIS */
{
    return FFMIN(ui_apl_nn + 1, UI_APL_VIS);
}

static SDL_Rect ui_apl_rect(void)
{
    SDL_Rect r;
    int ww, wh;

    SDL_GetWindowSize(window, &ww, &wh);
    r.w = ui_apl_naming ? 330 : ui_apl_w;
    r.h = ui_apl_naming ? 34 + UI_APL_ROW + 16 : 34 + ui_apl_rows() * UI_APL_ROW + 12;
    r.x = av_clip(ui_apl_x, 8, FFMAX(ww - r.w - 8, 8));
    r.y = av_clip(ui_apl_y, 8, FFMAX(wh - r.h - 8, 8));
    return r;
}

static int ui_apl_hit(const SDL_Rect *r, int x, int y)  /* the row under the mouse (0 = New playlist..., 1.. = playlists), or -1 */
{
    int row;

    if (ui_apl_naming || x < r->x || x >= r->x + r->w || y < r->y + 34 || y >= r->y + 34 + ui_apl_rows() * UI_APL_ROW)
        return -1;
    row = (y - r->y - 34) / UI_APL_ROW + ui_apl_sc;
    return row <= ui_apl_nn ? row : -1;
}

/* Add what was chosen to the playlist called raw (made if needed) */
static void ui_apl_commit(const char *raw)
{
    char name[PL_NAME + 8], **list = NULL;
    int n = 0, cap = 0, i, added = 0, np = ui_apl_np;

    snprintf(name, sizeof(name), "%.*s", PL_NAME - 1, raw);
    pl_clean(name);
    if (!name[0])
        return;                                         /* nothing typed: the box stays */
    if (ui_apl_ren[0]) {                                /* a rename */
        char old[PL_NAME];

        snprintf(old, sizeof(old), "%s", ui_apl_ren);
        if (!strcmp(old, name)) {
            ui_apl_close();                             /* the same name: nothing to do */
        } else if (av_strcasecmp(old, name) && pl_exists(name)) {
            ui_apl_say("There is already a playlist called \"%.60s\"", name);      /* the box stays, so another name can be typed */
        } else if (pl_rename(old, name)) {
            ui_apl_say("Renamed to \"%.60s\"", name);
            ui_apl_close();
            ui_pk_pl_renamed(old, name);
        } else {
            ui_apl_say("Could not rename \"%.60s\"", old);
            ui_apl_close();
        }
        return;
    }
    if (!pl_create(name)) {
        ui_apl_say("Could not make the playlist \"%.60s\"", name);
        ui_apl_close();
        return;
    }
    for (i = 0; i < ui_apl_np; i++)
        pl_collect(ui_apl_paths[i], &list, &n, &cap, 0);
    if (n)
        added = pl_add_files(name, list, n);
    pl_free(list, n);
    if (!np)
        ui_apl_say("Made the playlist \"%.60s\"", name);
    else if (added > 1)
        ui_apl_say("Added %d items to \"%.60s\"", added, name);
    else if (added == 1)
        ui_apl_say("Added to \"%.60s\"", name);
    else
        ui_apl_say(n ? "Already in \"%.60s\"" : "Nothing to add to \"%.60s\"", name);
    ui_apl_close();
    ui_pk_pl_changed(name);
}

static void ui_apl_pick(int row)
{
    if (row == 0) {
        ui_apl_naming = 1;                              /* "New playlist...": a name is typed */
        ui_apl_text[0] = 0;
    } else if (row >= 1 && row <= ui_apl_nn) {
        char name[PL_NAME];

        snprintf(name, sizeof(name), "%s", ui_apl_names[row - 1]);
        ui_apl_commit(name);
    }
}

static int ui_apl_event(VideoState *is, SDL_Event *ev)
{
    SDL_Rect r;
    int hit;

    if (!ui_apl_open)
        return 0;
    switch (ev->type) {
    case SDL_MOUSEMOTION:
        r = ui_apl_rect();
        ui_apl_hot = ui_apl_hit(&r, ev->motion.x, ev->motion.y);
        break;
    case SDL_MOUSEBUTTONDOWN:
        r = ui_apl_rect();
        hit = ui_apl_hit(&r, ev->button.x, ev->button.y);
        if (ev->button.button == SDL_BUTTON_LEFT && hit >= 0)
            ui_apl_pick(hit);
        else if (ev->button.x < r.x || ev->button.x >= r.x + r.w || ev->button.y < r.y || ev->button.y >= r.y + r.h ||
                 ev->button.button != SDL_BUTTON_LEFT)
            ui_apl_close();                             /* a click anywhere else (or a right click) closes it */
        break;
    case SDL_MOUSEWHEEL:
        if (!ui_apl_naming && ui_apl_nn + 1 > UI_APL_VIS) {
            float dy = ev->wheel.preciseY;

            if (ev->wheel.direction == SDL_MOUSEWHEEL_FLIPPED)
                dy = -dy;
            ui_apl_sc = av_clip(ui_apl_sc + (dy < 0 ? 1 : dy > 0 ? -1 : 0), 0, ui_apl_nn + 1 - UI_APL_VIS);
        }
        break;
    case SDL_MOUSEBUTTONUP:
    case SDL_KEYUP:
    case SDL_TEXTEDITING:
    case SDL_FINGERDOWN:
    case SDL_FINGERUP:
    case SDL_FINGERMOTION:
        break;
    case SDL_TEXTINPUT:
        if (ui_apl_naming && (unsigned char)ev->text.text[0] >= 32 && strlen(ui_apl_text) + strlen(ev->text.text) < PL_NAME - 4)
            strcat(ui_apl_text, ev->text.text);
        break;
    case SDL_KEYDOWN: {
        SDL_Keycode k = ev->key.keysym.sym;

        if (k == SDLK_ESCAPE) {
            if (ui_apl_naming && ui_apl_np > 0)
                ui_apl_naming = 0;                      /* back to the list */
            else
                ui_apl_close();
        } else if (ui_apl_naming) {
            if (k == SDLK_RETURN || k == SDLK_KP_ENTER) {
                ui_apl_commit(ui_apl_text);
            } else if (k == SDLK_BACKSPACE) {
                size_t n = strlen(ui_apl_text);

                while (n && ((unsigned char)ui_apl_text[n - 1] & 0xC0) == 0x80)
                    n--;
                if (n)
                    n--;
                ui_apl_text[n] = 0;
            }
        } else if (k == SDLK_DOWN || k == SDLK_UP) {
            int cur = ui_apl_hot < 0 ? (k == SDLK_DOWN ? -1 : ui_apl_nn + 1) : ui_apl_hot;

            ui_apl_hot = av_clip(cur + (k == SDLK_DOWN ? 1 : -1), 0, ui_apl_nn);
            if (ui_apl_hot < ui_apl_sc)
                ui_apl_sc = ui_apl_hot;
            else if (ui_apl_hot >= ui_apl_sc + UI_APL_VIS)
                ui_apl_sc = ui_apl_hot - UI_APL_VIS + 1;
        } else if ((k == SDLK_RETURN || k == SDLK_KP_ENTER) && ui_apl_hot >= 0) {
            ui_apl_pick(ui_apl_hot);
        }
        break;
    }
    default:
        return 0;                                       /* window events and the like carry on as usual */
    }
    ui_wake();
    if (is)
        is->force_refresh = 1;
    return 1;
}

static void ui_apl_draw(void)
{
    SDL_Rect r;
    int i, ww, wh, ar = av_clip(cfg_bar_r + 40, 0, 255), ag = av_clip(cfg_bar_g + 40, 0, 255), ab = av_clip(cfg_bar_b + 40, 0, 255);
    int64_t now = av_gettime_relative();

    if (ui_apl_open) {
        r = ui_apl_rect();
        ui_glass(&r, 18);
        SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
        ui_label(r.x + 24, r.y + 18, ui_apl_ren[0] ? "Rename playlist" : ui_apl_naming ? "New playlist" : "Add to playlist", 13, 150, 150, 150, 255);
        if (ui_apl_naming) {                            /* the name, with a line under it (no box) */
            int fx = r.x + 24, fy = r.y + 34 + UI_APL_ROW / 2, fw = r.w - 48, tw;
            char t[PL_NAME + 8];

            snprintf(t, sizeof(t), "%s", ui_apl_text);
            while (t[0] && ui_text_width(t, 18) > fw - 8)
                memmove(t, t + 1, strlen(t));
            tw = t[0] ? ui_text_width(t, 18) : 0;
            if (t[0])
                ui_label(fx, fy, t, 18, 245, 245, 245, 255);
            else
                ui_label(fx, fy, "Name", 18, 150, 150, 150, 255);
            SDL_SetRenderDrawColor(renderer, ar, ag, ab, 200);
            SDL_RenderDrawLine(renderer, fx - 2, fy + 15, fx + fw, fy + 15);
            if ((now / 500000) % 2 == 0) {
                SDL_SetRenderDrawColor(renderer, 245, 245, 245, 220);
                SDL_RenderDrawLine(renderer, fx + tw + 2, fy - 10, fx + tw + 2, fy + 10);
            }
        } else {
            for (i = 0; i < ui_apl_rows(); i++) {
                int row = i + ui_apl_sc, ry = r.y + 34 + i * UI_APL_ROW, hot = row == ui_apl_hot;
                char t[PL_NAME + 8];

                snprintf(t, sizeof(t), "%s", row == 0 ? "New playlist..." : ui_apl_names[row - 1]);
                ui_fit_text(t, 18, r.w - 92);
                ui_icon(row == 0 ? UI_IC_PLNEW : UI_IC_PLAYLIST, r.x + 30, ry + UI_APL_ROW / 2, 18, 240, 240, 240, hot ? 255 : 190);
                ui_label(r.x + 58, ry + UI_APL_ROW / 2, t, 18, 240, 240, 240, hot ? 255 : 210);
                if (hot) {
                    SDL_Rect dot = { r.x + 13, ry + UI_APL_ROW / 2 - 3, 6, 6 };

                    SDL_SetRenderDrawColor(renderer, ar, ag, ab, 235);
                    ui_pill(&dot);
                }
            }
            if (ui_apl_nn + 1 > UI_APL_VIS) {            /* more below or above */
                if (ui_apl_sc > 0)
                    ui_icon(UI_IC_TRI_D, r.x + r.w - 28, r.y + 18, 12, 150, 150, 150, 255);
                if (ui_apl_sc + UI_APL_VIS < ui_apl_nn + 1)
                    ui_icon(UI_IC_TRI_D, r.x + r.w - 28, r.y + r.h - 12, 12, 150, 150, 150, 255);
            }
        }
    }
    if (now < ui_apl_toast_until) {
        char t[sizeof(ui_apl_toast)];

        SDL_GetWindowSize(window, &ww, &wh);
        snprintf(t, sizeof(t), "%s", ui_apl_toast);
        ui_fit_text(t, 17, FFMAX(ww - 120, 80));
        r.w = ui_text_width(t, 17) + 56;
        r.h = 42;
        r.x = (ww - r.w) / 2;
        r.y = wh - r.h - 78;
        ui_glass(&r, 20);
        SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
        ui_label_c(ww / 2, r.y + r.h / 2, t, 17, 245, 245, 245, 255);
    }
}

'''
i = src.index("   v44: our own file picker.")
j = src.rfind("\n", 0, i - 1) + 1
src = src[:j] + PL_BLOCK + src[j:]
print("ok: playlists and Add to playlist chooser")

# ------------------------------------------------------------------ the picker: structures
R("""    int depth, open, kids, grp, kind;           /* kids: -1 = not looked at yet; grp: 0 places, 1 drives; kind: 0 folder, 1 drive not mounted, 2 heading */
} UiPkNode;""",
  """    int depth, open, kids, grp, kind;           /* kids: -1 = not looked at yet; grp: 0 library, 1 devices, 2 recent, 3 playlists; kind: 0 folder, 1 drive not mounted, 2 heading, 3 the "New playlist" row, 4 a playlist (v54) */
    int ic;                                     /* v54: its icon */
} UiPkNode;""", "node struct")
R("""    char dev[48], label[64], size[16], mnt[PATH_MAX];
} UiPkDev;""",
  """    char dev[48], label[64], size[16], mnt[PATH_MAX];
    int ext;                                    /* v54: 1 = a drive that is plugged in (removable), 0 = built in */
} UiPkDev;""", "dev struct")

R("""static char ui_pk_loc[PATH_MAX];
""",
  """static char ui_pk_loc[PATH_MAX];
static char ui_pk_pl[PL_NAME];                  /* v54: the playlist that is open instead of a folder ("" = a folder is open); ui_pk_dir stays the last folder */

static const char *ui_pk_loc_now(void)          /* where the picker is: a folder, or "playlist:Name" (history and reload use this) */
{
    static char b[PATH_MAX + PL_NAME + 16];

    if (ui_pk_pl[0]) {
        snprintf(b, sizeof(b), "playlist:%s", ui_pk_pl);
        return b;
    }
    return ui_pk_dir;
}
""", "pk playlist state")

# ------------------------------------------------------------------ history, load, reload, up
R("""    if (ui_pk_hi >= 0 && ui_pk_hi < ui_pk_hn && !strcmp(ui_pk_hist[ui_pk_hi], ui_pk_dir))
        return;""",
  """    if (ui_pk_hi >= 0 && ui_pk_hi < ui_pk_hn && !strcmp(ui_pk_hist[ui_pk_hi], ui_pk_loc_now()))
        return;""", "hist compare")
R("""    ui_pk_hist[ui_pk_hn++] = strdup(ui_pk_dir);""", """    ui_pk_hist[ui_pk_hn++] = strdup(ui_pk_loc_now());""", "hist push")

R("""/* Read a folder. Returns 0 if it cannot be read (nothing changes then). */
static int ui_pk_load(const char *dir)""",
  """/* v54: a playlist is listed like a folder (its files, in the order of the playlist: no sorting). Files that are gone are left out. */
static int ui_pk_load_playlist(const char *name)
{
    char **v = NULL, file[PATH_MAX + 128];
    struct stat st;
    int n, i;

    if (!pl_file(name, file, sizeof(file)) || stat(file, &st) != 0)
        return 0;
    n = pl_load(name, &v);
    ui_pk_nrw = 0;
    ui_pk_free_ents(ui_pk_e, ui_pk_n);
    ui_pk_n = 0;
    ui_pk_free_ents(ui_pk_x, ui_pk_nx);
    ui_pk_nx = 0;
    ui_pk_jq_clear();
    for (i = 0; i < n; i++) {
        char *slash = strrchr(v[i], '/');
        UiPkEnt *e;

        if (!slash || !slash[1] || stat(v[i], &st) != 0 || !S_ISREG(st.st_mode))
            continue;
        if (!(e = ui_pk_push(&ui_pk_e, &ui_pk_n, &ui_pk_cap)))
            break;
        e->name = strdup(slash + 1);
        if (slash == v[i]) {
            e->where = strdup("/");
        } else {
            size_t wl = slash - v[i];
            e->where = malloc(wl + 1);
            if (e->where) {
                memcpy(e->where, v[i], wl);
                e->where[wl] = 0;
            }
        }
        e->dir = 0;
        e->size = st.st_size;
        e->mtime = st.st_mtime;
        e->count = -1;
    }
    pl_free(v, n);
    ui_pk_nav_t = av_gettime_relative();
    snprintf(ui_pk_pl, sizeof(ui_pk_pl), "%s", name);
    ui_pk_filter[0] = 0;
    ui_pk_search_on = 0;
    ui_pk_touched = 0;
    ui_pk_sc = 0.0;
    ui_pk_goal = -1.0;
    ui_pk_rebuild();
    return 1;
}

/* Read a folder. Returns 0 if it cannot be read (nothing changes then). */
static int ui_pk_load(const char *dir)""", "load playlist")
R("""    if (!realpath(dir, real) || !(d = opendir(real)))
        return 0;
    ui_pk_nrw = 0;                              /* the rows point into what is freed now */""",
  """    if (!strncmp(dir, "playlist:", 9))
        return ui_pk_load_playlist(dir + 9);    /* v54 */
    if (!realpath(dir, real) || !(d = opendir(real)))
        return 0;
    ui_pk_nrw = 0;                              /* the rows point into what is freed now */""", "load dispatch")
R("""    snprintf(ui_pk_dir, sizeof(ui_pk_dir), "%s", real);
    snprintf(ui_pk_last, sizeof(ui_pk_last), "%s", real);""",
  """    snprintf(ui_pk_dir, sizeof(ui_pk_dir), "%s", real);
    snprintf(ui_pk_last, sizeof(ui_pk_last), "%s", real);
    ui_pk_pl[0] = 0;                            /* v54: a folder is open now, not a playlist */""", "load clears playlist")
R("""    snprintf(keep, sizeof(keep), "%s", ui_pk_dir);
    snprintf(q, sizeof(q), "%s", ui_pk_filter);""",
  """    snprintf(keep, sizeof(keep), "%.*s", PATH_MAX - 1, ui_pk_loc_now());
    snprintf(q, sizeof(q), "%s", ui_pk_filter);""", "reload")
R("""    int i;

    if (!strcmp(ui_pk_dir, "/"))
        return;
    snprintf(old, sizeof(old), "%s", ui_pk_dir);""",
  """    int i;

    if (ui_pk_pl[0]) {                          /* v54: out of a playlist: back to the last folder */
        snprintf(old, sizeof(old), "%s", ui_pk_dir);
        ui_pk_go(old);
        return;
    }
    if (!strcmp(ui_pk_dir, "/"))
        return;
    snprintf(old, sizeof(old), "%s", ui_pk_dir);""", "up")
R("""    if (ui_pk_filter[0]) {
        ui_pk_jq_push(0, ui_pk_dir, 0);""",
  """    if (ui_pk_filter[0] && !ui_pk_pl[0]) {      /* v54: in a playlist only its own files are matched */
        ui_pk_jq_push(0, ui_pk_dir, 0);""", "search start")
R("""static void ui_pk_resort(void)
{
    if (ui_pk_n > 1)
        qsort(ui_pk_e, ui_pk_n, sizeof(*ui_pk_e), ui_pk_cmp);
    if (ui_pk_nx > 1)""",
  """static void ui_pk_resort(void)
{
    if (ui_pk_n > 1 && !ui_pk_pl[0])            /* v54: a playlist keeps its own order */
        qsort(ui_pk_e, ui_pk_n, sizeof(*ui_pk_e), ui_pk_cmp);
    if (ui_pk_nx > 1)""", "resort")

# ------------------------------------------------------------------ the tree: Library, Devices, Playlists
R("""static int ui_pk_tn_insert(int at, const char *name, const char *path, const char *dev, int depth, int kind, int grp)
{
    UiPkNode *n;
""",
  """static int ui_pk_tn_ic = 0;                    /* v54: the icon for the next node (0 = the folder icon) */

static int ui_pk_tn_insert(int at, const char *name, const char *path, const char *dev, int depth, int kind, int grp)
{
    UiPkNode *n;
""", "tn insert head")
R("""    n->kind = kind;
    n->grp = grp;
    n->kids = kind == 0 ? -1 : 0;""",
  """    n->kind = kind;
    n->grp = grp;
    n->ic = ui_pk_tn_ic ? ui_pk_tn_ic : UI_IC_FOLDER;
    ui_pk_tn_ic = 0;
    n->kids = kind == 0 ? -1 : 0;""", "tn insert body")

i0 = src.index("/* The drives part of the tree, made again from ui_pk_dev")
i1 = src.index("static void ui_pk_rec_load(void);\nstatic void ui_pk_tree_recents(void);")
src = src[:i0] + r'''/* v54: the tree has groups: 0 Library (Videos, Music), 1 Devices (this computer's own home, then drives), 2 Recent (off), 3 Playlists.
   A group is made again by itself, so a new drive or a new playlist does not close the drop downs of the others. */
#define UI_PK_SHOW_RECENT 0                     /* 1 = the Recent places come back, between Devices and the drives of... (they are still kept) */
#define UI_PK_SYS_NAME "System"                 /* the entry for the computer's own disk (it opens your home folder) */

static void ui_pk_tree_drop(int grp)
{
    int i;

    for (i = ui_pk_ntn - 1; i >= 0; i--)
        if (ui_pk_tn[i].grp == grp) {
            ui_pk_tn_free(&ui_pk_tn[i]);
            memmove(&ui_pk_tn[i], &ui_pk_tn[i + 1], (ui_pk_ntn - i - 1) * sizeof(*ui_pk_tn));
            ui_pk_ntn--;
        }
}

/* The groups from the top: 0 Library, 5 the Devices heading, 4 System (and what is open under it), 1 the drives, 3 Playlists, 2 Recent.
   System is a group of its own so that a drive that comes or goes does not close its drop downs. */
static int ui_pk_rank(int grp)
{
    static const int rank[6] = { 0, 3, 5, 4, 2, 1 };

    return rank[av_clip(grp, 0, 5)];
}

static int ui_pk_tree_at(int grp)               /* where the nodes of a group go: before the first node of a later group */
{
    int i;

    for (i = 0; i < ui_pk_ntn; i++)
        if (ui_pk_rank(ui_pk_tn[i].grp) > ui_pk_rank(grp))
            return i;
    return ui_pk_ntn;
}

/* The Devices part: the heading, the computer's own disk (it starts in your home folder, with the usual folders under its drop down),
   then the drives that lsblk found */
static void ui_pk_tree_devs(void)
{
    const char *home = getenv("HOME");
    int i, at, have_sys = 0;

    ui_pk_tree_drop(5);
    ui_pk_tree_drop(1);
    for (i = 0; i < ui_pk_ntn; i++)
        have_sys |= ui_pk_tn[i].grp == 4;
    at = ui_pk_tree_at(5);
    ui_pk_tn_insert(at, "Devices", "", NULL, 0, 2, 5);
    if (!have_sys && home && home[0]) {
        char real[PATH_MAX];

        at = ui_pk_tree_at(4);
        ui_pk_tn_ic = UI_IC_DISK;
        ui_pk_tn_insert(at, UI_PK_SYS_NAME, realpath(home, real) ? real : home, NULL, 0, 0, 4);
    }
    at = ui_pk_tree_at(1);
    for (i = 0; i < ui_pk_ndev; i++) {
        char real[PATH_MAX];
        const char *m = ui_pk_dev[i].mnt;

        if (m[0] && realpath(m, real))
            m = real;
        ui_pk_tn_ic = ui_pk_dev[i].ext ? UI_IC_USB : UI_IC_DISK;
        if (ui_pk_tn_insert(at, ui_pk_dev[i].label, m, ui_pk_dev[i].dev[0] ? ui_pk_dev[i].dev : NULL, 0, ui_pk_dev[i].mnt[0] ? 0 : 1, 1))
            at++;
    }
}

/* The Playlists part: every playlist, then "New playlist" */
static void ui_pk_tree_pls(void)
{
    int i, at;

    ui_pk_tree_drop(3);
    pl_list();
    at = ui_pk_tree_at(3);
    if (!ui_pk_tn_insert(at, "Playlists", "", NULL, 0, 2, 3))
        return;
    at++;
    for (i = 0; i < pl_n; i++) {
        char loc[PL_NAME + 16];

        snprintf(loc, sizeof(loc), "playlist:%.*s", PL_NAME - 1, pl_names[i]);
        ui_pk_tn_ic = UI_IC_PLAYLIST;
        if (ui_pk_tn_insert(at, pl_names[i], loc, NULL, 0, 4, 3))
            at++;
    }
    ui_pk_tn_ic = UI_IC_PLNEW;
    ui_pk_tn_insert(at, "New playlist", "", NULL, 0, 3, 3);
}

''' + src[i1:]
print("ok: tree: Devices and Playlists parts")

i0 = src.index("static void ui_pk_tree_build(void)\n{")
i1 = src.index("\n\n/* ----- v51: recent places")
src = src[:i0] + r'''static void ui_pk_tree_build(void)
{
    static const char * const names[] = { "Videos", "Music" };
    static const int icons[] = { UI_IC_VIDEO, UI_IC_MUSIC };
    const char *home = getenv("HOME");
    char base[PATH_MAX], real[PATH_MAX];
    int i, any = 0;

    ui_pk_tree_clear();
    for (i = 0; home && home[0] && i < 2; i++) {        /* v54: Library: only the Videos and the Music folder */
        struct stat st;

        snprintf(base, sizeof(base), "%s/%s", home, names[i]);
        if (stat(base, &st) != 0 || !S_ISDIR(st.st_mode))
            continue;
        if (!any++)
            ui_pk_tn_insert(ui_pk_ntn, "Library", "", NULL, 0, 2, 0);
        ui_pk_tn_ic = icons[i];
        ui_pk_tn_insert(ui_pk_ntn, names[i], realpath(base, real) ? real : base, NULL, 0, 0, 0);
    }
    ui_pk_rec_load();
    ui_pk_tree_recents();
    ui_pk_tree_devs();
    ui_pk_tree_pls();
}''' + src[i1:]
print("ok: tree: Library")

R("""static void ui_pk_tree_recents(void)
{
    int i, at;
""",
  """static void ui_pk_tree_recents(void)
{
    int i, at;

    if (!UI_PK_SHOW_RECENT)
        return;                                 /* v54: the Library has only Videos and Music; the places are still kept in recent_places.txt */
""", "recents off")

# a playlist changed: its list and the tree follow
R("""/* Work that waits for the main loop: a new list of drives, a drive that has been mounted, and the search */""",
  """/* v54: a playlist was made, added to or changed: the tree shows it, and the list too if it is the one that is open */
static void ui_pk_pl_changed(const char *name)
{
    if (!ui_pk_open)
        return;
    ui_pk_tree_pls();
    if (ui_pk_pl[0] && !strcmp(ui_pk_pl, name))
        ui_pk_reload();
}

static void ui_pk_pl_renamed(const char *from, const char *to)   /* a playlist got a new name: the open one and the history follow */
{
    int i;

    if (!ui_pk_open)
        return;
    for (i = 0; i < ui_pk_hn; i++)
        if (!strncmp(ui_pk_hist[i], "playlist:", 9) && !strcmp(ui_pk_hist[i] + 9, from)) {
            char *n = malloc(strlen(to) + 10);

            if (n) {
                sprintf(n, "playlist:%s", to);
                free(ui_pk_hist[i]);
                ui_pk_hist[i] = n;
            }
        }
    if (ui_pk_pl[0] && !strcmp(ui_pk_pl, from))
        snprintf(ui_pk_pl, sizeof(ui_pk_pl), "%s", to);
    ui_pk_tree_pls();
}

static void ui_pk_pl_gone(const char *name)     /* a playlist was deleted: leave it if it was open */
{
    if (ui_pk_pl[0] && !strcmp(ui_pk_pl, name)) {
        char d[PATH_MAX];

        snprintf(d, sizeof(d), "%s", ui_pk_dir);
        ui_pk_go(d);
    }
    ui_pk_tree_pls();
}

/* Work that waits for the main loop: a new list of drives, a drive that has been mounted, and the search */""", "pl changed")

# ------------------------------------------------------------------ drives: external or built in, and no folders that only look like drives
R("""static int ui_pk_dev_thread(void *arg)
{""",
  """static int ui_pk_is_mount(const char *path)     /* v54: a real mount point: not a folder that was left behind in /media/USER */
{
    struct stat a, b;
    char up[PATH_MAX + 4], *slash;

    if (stat(path, &a) != 0 || !S_ISDIR(a.st_mode))
        return 0;
    snprintf(up, sizeof(up), "%.4090s", path);
    if (!(slash = strrchr(up, '/')))
        return 0;
    if (slash == up)
        slash[1] = 0;
    else
        *slash = 0;
    return stat(up, &b) == 0 && a.st_dev != b.st_dev;
}

static int ui_pk_dev_thread(void *arg)
{""", "is mount")
R("""FILE *f = popen("lsblk -P -b -o PATH,LABEL,SIZE,FSTYPE,MOUNTPOINT,TYPE,PARTTYPE 2>/dev/null", "r");""",
  """FILE *f = popen("lsblk -P -b -o PATH,LABEL,SIZE,FSTYPE,MOUNTPOINT,TYPE,PARTTYPE,RM,HOTPLUG 2>/dev/null", "r");""", "lsblk columns")
R("""char path[64] = "", label[64] = "", size[32] = "", fst[32] = "", mnt[PATH_MAX] = "", type[16] = "", pt[48] = "";""",
  """char path[64] = "", label[64] = "", size[32] = "", fst[32] = "", mnt[PATH_MAX] = "", type[16] = "", pt[48] = "", rm[8] = "", hp[8] = "";""", "lsblk vars")
R("""            ui_pk_lsblk_val(line, "PARTTYPE", pt, sizeof(pt));""",
  """            ui_pk_lsblk_val(line, "PARTTYPE", pt, sizeof(pt));
            ui_pk_lsblk_val(line, "RM", rm, sizeof(rm));
            ui_pk_lsblk_val(line, "HOTPLUG", hp, sizeof(hp));""", "lsblk parse")
R("""                snprintf(ui_pk_dev_tmp[n].label, sizeof(ui_pk_dev_tmp[0].label), "%s Volume", gb);
            n++;""",
  """                snprintf(ui_pk_dev_tmp[n].label, sizeof(ui_pk_dev_tmp[0].label), "%s Volume", gb);
            ui_pk_dev_tmp[n].ext = rm[0] == '1' || hp[0] == '1';
            n++;""", "lsblk ext")
R("""            if (have)
                continue;
            ui_pk_dev_tmp[n].dev[0] = 0;
            ui_pk_dev_tmp[n].size[0] = 0;""",
  """            if (have || !ui_pk_is_mount(full))
                continue;                       /* v54: a folder in /media/USER is only a drive if something is mounted on it */
            ui_pk_dev_tmp[n].dev[0] = 0;
            ui_pk_dev_tmp[n].size[0] = 0;
            ui_pk_dev_tmp[n].ext = 1;""", "stale mount folders")
R("""            ui_pk_ndev = ui_pk_dev_tmpn;
            ui_pk_tree_devs();""",
  """            ui_pk_ndev = ui_pk_dev_tmpn;
            for (st = 0; st < ui_pk_ndev; st++)         /* v54: what was found, for the log (~/.cache/ffplay-custom/log.txt) */
                av_log(NULL, AV_LOG_INFO, "ffplay-custom: drive: dev=%s label=\\"%s\\" mount=%s %s\\n", ui_pk_dev[st].dev[0] ? ui_pk_dev[st].dev : "-",
                       ui_pk_dev[st].label, ui_pk_dev[st].mnt[0] ? ui_pk_dev[st].mnt : "-", ui_pk_dev[st].ext ? "external" : "built in");
            ui_pk_tree_devs();""", "drive log")

# ------------------------------------------------------------------ the sidebar
R("""            int ry = L.side.y + 6 + i * UI_PK_TROW - (int)ui_pk_ssc, ix, on, mounted = nd->kind == 0;""",
  """            int ry = L.side.y + 6 + i * UI_PK_TROW - (int)ui_pk_ssc, ix, on, mounted = nd->kind == 0 || nd->kind == 3 || nd->kind == 4;""", "side mounted")
R("""            on = mounted && nd->path[0] && !strcmp(nd->path, ui_pk_dir);""",
  """            on = mounted && nd->path[0] && !strcmp(nd->path, ui_pk_loc_now());""", "side on")
R("""                ui_icon(nd->open ? UI_IC_ARW_D : UI_IC_ARW_R, ix, ry + UI_PK_TROW / 2, 14, 200, 200, 200, 255);
            ui_icon(UI_IC_FOLDER, ix + 18, ry + UI_PK_TROW / 2, 16, 245, 245, 245, mounted ? (on ? 255 : 210) : 120);""",
  """                ui_icon(nd->open ? UI_IC_TRI_D : UI_IC_TRI_R, ix, ry + UI_PK_TROW / 2, 14, 190, 190, 190, 255);      /* v54: a solid arrow head */
            ui_icon(nd->ic, ix + 17, ry + UI_PK_TROW / 2, 18, 245, 245, 245, mounted ? (on ? 255 : 210) : 120);""", "side icons")

# ------------------------------------------------------------------ the top bar and the list in a playlist
R("""ui_pk_ibtn(&L.upb, UI_IC_ARW_U, ui_pk_hbtn == 22, 0, strcmp(ui_pk_dir, "/") ? 255 : 90);""",
  """ui_pk_ibtn(&L.upb, UI_IC_ARW_U, ui_pk_hbtn == 22, 0, ui_pk_pl[0] || strcmp(ui_pk_dir, "/") ? 255 : 90);""", "up button")
R("""    } else {

        const char *home = getenv("HOME");
        int hl = home ? (int)strlen(home) : 0, starts_home""",
  """    } else if (ui_pk_pl[0]) {                   /* v54: a playlist is open */
        int cyp = L.crumbs.y + L.crumbs.h / 2;

        ui_icon(UI_IC_PLAYLIST, L.crumbs.x + 14, cyp, 18, 245, 245, 245, 230);
        snprintf(tmp, sizeof(tmp), "%s", ui_pk_pl);
        ui_fit_text(tmp, 16, FFMAX(L.crumbs.w - 60, 60));
        ui_label(L.crumbs.x + 40, cyp, tmp, 16, 245, 245, 245, 255);
    } else {

        const char *home = getenv("HOME");
        int hl = home ? (int)strlen(home) : 0, starts_home""", "crumbs")
R("""        ui_icon(ui_pk_desc ? UI_IC_ARW_D : UI_IC_ARW_U, L.sortb.x + L.sortb.w - 28, L.sortb.y + L.sortb.h / 2, 14, 190, 190, 190, 255);""",
  """        if (!ui_pk_pl[0])
            ui_icon(ui_pk_desc ? UI_IC_ARW_D : UI_IC_ARW_U, L.sortb.x + L.sortb.w - 28, L.sortb.y + L.sortb.h / 2, 14, 190, 190, 190, 255);""", "sort arrow")
R("""    return ui_pk_sortk == 1 ? "Modified" : ui_pk_sortk == 2 ? "Size" : "Name";""",
  """    if (ui_pk_pl[0])
        return "In order";                      /* v54: a playlist keeps its own order */
    return ui_pk_sortk == 1 ? "Modified" : ui_pk_sortk == 2 ? "Size" : "Name";""", "sort name")
R("""        const char *m = ui_pk_filter[0] ? (ui_pk_scan_on ? "Looking ..." : "Nothing matches") :
                        ui_pk_all ?""",
  """        const char *m = ui_pk_filter[0] ? (ui_pk_scan_on ? "Looking ..." : "Nothing matches") :
                        ui_pk_pl[0] ? "This playlist is empty: right-click a song and choose Add to playlist" :
                        ui_pk_all ?""", "empty message")
R("""snprintf(tmp, sizeof(tmp), "%s", ui_pk_sect_name[w->idx]);""",
  """snprintf(tmp, sizeof(tmp), "%s", ui_pk_pl[0] && !w->idx ? "In this playlist" : ui_pk_sect_name[w->idx]);""", "section name")
R("""            snprintf(tmp, sizeof(tmp), "%s", wide ? "Add this folder" : "Folder");""",
  """            snprintf(tmp, sizeof(tmp), "%s", ui_pk_pl[0] ? (wide ? "Add playlist" : "Playlist") : wide ? "Add this folder" : "Folder");""", "add folder label")
R("""            ui_pk_button(&L.ok, tmp, ui_pk_hbtn == 1, 1, nt > 0 || (ce && !ce->dir));
        }
    }
    ui_pk_cm_draw();""",
  """            ui_pk_button(&L.ok, tmp, ui_pk_hbtn == 1, 1, nt > 0 || (ce && !ce->dir));
            if (ui_pk_pl[0] && !nt)             /* v54: the whole playlist */
                ui_pk_button(&L.extra, wide ? "Play playlist" : "Play all", ui_pk_hbtn == 3, 0, ui_pk_nrw > 0);
        }
    }
    ui_pk_cm_draw();""", "play playlist button")

# ------------------------------------------------------------------ the buttons
R("""static void ui_pk_enter(const UiPkEnt *e)       /* go into a folder */""",
  """/* v54: every file of a playlist: 'o' plays it from the first one, 'a' adds them all to the queue */
static void ui_pk_send_playlist(VideoState *is, char what, const char *name)
{
    char **v = NULL;
    int n = pl_load(name, &v), i, sent = 0;

    for (i = 0; i < n; i++) {
        struct stat st;

        if (stat(v[i], &st) != 0 || !S_ISREG(st.st_mode))
            continue;
        ui_pk_send(is, !sent && what == 'o' ? 'o' : 'a', v[i]);
        sent++;
    }
    pl_free(v, n);
    snprintf(ui_pk_note, sizeof(ui_pk_note), sent ? (what == 'o' ? "Playing the playlist: %.100s" : "Added the playlist: %.100s") : "Nothing to play in: %.100s", name);
    ui_pk_note_until = av_gettime_relative() + 2500000;
}

static void ui_pk_enter(const UiPkEnt *e)       /* go into a folder */""", "send playlist")
R("""    if (ui_pk_mode == 2) {
        if (e && e->dir && ui_pk_touched)
            ui_pk_path_of(e, path, sizeof(path));
        else
            snprintf(path, sizeof(path), "%s", ui_pk_dir);
        ui_pk_send(is, 'a', path);
        ui_pk_close(is);
    } else if (e && e->dir) {
        ui_pk_enter(e);
    }""",
  """    if (ui_pk_pl[0] && !(e && e->dir)) {        /* v54: in a playlist this button is for the whole playlist */
        ui_pk_send_playlist(is, ui_pk_mode == 2 ? 'a' : 'o', ui_pk_pl);
        ui_pk_close(is);
    } else if (ui_pk_mode == 2) {
        if (e && e->dir && ui_pk_touched)
            ui_pk_path_of(e, path, sizeof(path));
        else
            snprintf(path, sizeof(path), "%s", ui_pk_dir);
        ui_pk_send(is, 'a', path);
        ui_pk_close(is);
    } else if (e && e->dir) {
        ui_pk_enter(e);
    }""", "do extra")

# ------------------------------------------------------------------ the right-click menus
R("""static int ui_pk_cm_act[4];
static char ui_pk_cm_lab[4][24], ui_pk_cm_path[PATH_MAX + 300], ui_pk_cm_nm[200];""",
  """static int ui_pk_cm_act[6];
static char ui_pk_cm_lab[6][32], ui_pk_cm_path[PATH_MAX + 300], ui_pk_cm_nm[200];
static int ui_pk_cm_multi = 0, ui_pk_cm_arm = 0;        /* v54: the menu is for all ticked files; a playlist waits for a second click to be deleted */""", "cm arrays")
R("""    snprintf(ui_pk_cm_lab[ui_pk_cm_n], 24, "%s", label);""", """    snprintf(ui_pk_cm_lab[ui_pk_cm_n], 32, "%s", label);""", "cm label size")
R("""enum { UI_PK_A_PLAY, UI_PK_A_ADD, UI_PK_A_ENTER, UI_PK_A_NEXT, UI_PK_A_SORT = 10 };""",
  """enum { UI_PK_A_PLAY, UI_PK_A_ADD, UI_PK_A_ENTER, UI_PK_A_NEXT, UI_PK_A_PL, UI_PK_A_RMPL, UI_PK_A_PLPLAY, UI_PK_A_PLADD, UI_PK_A_PLDEL,
       UI_PK_A_PLREN, UI_PK_A_SORT = 10 };""", "cm enum")
R("""static void ui_pk_cm_start(int row, int x, int y)
{""",
  """/* v54: the ticked files, in the order they were ticked, go to the playlist chooser */
static void ui_pk_ticked_to_apl(void)
{
    UiPkEnt **v;
    int n = 0, i, cap = ui_pk_n + ui_pk_nx;
    char path[PATH_MAX + 300];

    if (!cap || !(v = calloc(cap, sizeof(*v))))
        return;
    for (i = 0; i < ui_pk_n; i++)
        if (ui_pk_e[i].sel)
            v[n++] = &ui_pk_e[i];
    for (i = 0; i < ui_pk_nx; i++)
        if (ui_pk_x[i].sel)
            v[n++] = &ui_pk_x[i];
    if (n > 1)
        qsort(v, n, sizeof(*v), ui_pk_ord_cmp);
    for (i = 0; i < n; i++) {
        ui_pk_path_of(v[i], path, sizeof(path));
        ui_apl_add_path(path);
    }
    free(v);
}

static void ui_pk_cm_start_pl(const char *name, int x, int y)   /* v54: right click on a playlist in the tree */
{
    snprintf(ui_pk_cm_nm, sizeof(ui_pk_cm_nm), "%s", name);
    ui_pk_cm_path[0] = 0;
    ui_pk_cm_kind = 2;
    ui_pk_cm_w = 250;
    ui_pk_cm_x = x;
    ui_pk_cm_y = y;
    ui_pk_cm_n = 0;
    ui_pk_cm_hot = -1;
    ui_pk_cm_arm = 0;
    ui_pk_cm_item("Play playlist", UI_PK_A_PLPLAY);
    ui_pk_cm_item("Add playlist to queue", UI_PK_A_PLADD);
    ui_pk_cm_item("Rename playlist", UI_PK_A_PLREN);
    ui_pk_cm_item("Delete playlist", UI_PK_A_PLDEL);
    ui_pk_cm_open = 1;
}

static void ui_pk_cm_start(int row, int x, int y)
{""", "cm start pl")
R("""        ui_pk_cm_item("Add folder to queue", UI_PK_A_ADD);
    } else {""",
  """        ui_pk_cm_item("Add folder to queue", UI_PK_A_ADD);
        ui_pk_cm_item("Add folder to playlist", UI_PK_A_PL);
    } else {""", "cm dir items")
R("""        ui_pk_cm_item("Add to queue", UI_PK_A_ADD);
    }
    ui_pk_cur = row;""",
  """        ui_pk_cm_item("Add to queue", UI_PK_A_ADD);
        ui_pk_cm_item(ui_pk_cm_multi ? "Add selected to playlist" : "Add to playlist", UI_PK_A_PL);
        if (ui_pk_pl[0])
            ui_pk_cm_item("Remove from playlist", UI_PK_A_RMPL);
    }
    ui_pk_cur = row;""", "cm file items")
R("""    ui_pk_cm_kind = 0;
    ui_pk_cm_w = 230;
    ui_pk_cm_x = x;
    ui_pk_cm_y = y;
    ui_pk_cm_n = 0;
    ui_pk_cm_hot = -1;
    if (e->dir) {""",
  """    ui_pk_cm_kind = 0;
    ui_pk_cm_w = 250;
    ui_pk_cm_x = x;
    ui_pk_cm_y = y;
    ui_pk_cm_n = 0;
    ui_pk_cm_hot = -1;
    ui_pk_cm_arm = 0;
    ui_pk_cm_multi = e->sel && ui_pk_ticked(NULL) > 1;
    if (e->dir) {""", "cm start head")
R("""    } else {
        ui_pk_send(is, 'a', ui_pk_cm_path);     /* the picker stays open: more can be added */""",
  """    } else if (act == UI_PK_A_PL) {             /* v54: the chooser opens where the menu was */
        ui_apl_begin();
        if (ui_pk_cm_multi)
            ui_pk_ticked_to_apl();
        else
            ui_apl_add_path(ui_pk_cm_path);
        ui_apl_show(ui_pk_cm_x, ui_pk_cm_y);
    } else if (act == UI_PK_A_RMPL) {
        if (pl_remove_path(ui_pk_pl, ui_pk_cm_path))
            snprintf(ui_pk_note, sizeof(ui_pk_note), "Removed from the playlist: %.100s", name);
        ui_pk_note_until = av_gettime_relative() + 2500000;
        ui_pk_pl_changed(ui_pk_pl);
    } else if (act == UI_PK_A_PLPLAY || act == UI_PK_A_PLADD) {
        ui_pk_send_playlist(is, act == UI_PK_A_PLPLAY ? 'o' : 'a', name);
        if (act == UI_PK_A_PLPLAY)
            ui_pk_close(is);
    } else if (act == UI_PK_A_PLREN) {
        ui_apl_rename(name, ui_pk_cm_x, ui_pk_cm_y);
    } else if (act == UI_PK_A_PLDEL) {
        if (!ui_pk_cm_arm) {                    /* the first click asks again: nothing is deleted by accident */
            ui_pk_cm_arm = 1;
            snprintf(ui_pk_cm_lab[3], sizeof(ui_pk_cm_lab[3]), "Click again to delete");
            ui_pk_cm_open = 1;
        } else {
            if (pl_delete(name))
                snprintf(ui_pk_note, sizeof(ui_pk_note), "Deleted the playlist: %.100s", name);
            ui_pk_note_until = av_gettime_relative() + 2500000;
            ui_pk_pl_gone(name);
        }
    } else {
        ui_pk_send(is, 'a', ui_pk_cm_path);     /* the picker stays open: more can be added */""", "cm do")

# ------------------------------------------------------------------ the mouse
R("""            if (b == SDL_BUTTON_RIGHT && ui_pk_hrow >= 0)
                ui_pk_cm_start(ui_pk_hrow, x, y);       /* a right click on a row opens its menu */""",
  """            if (b == SDL_BUTTON_RIGHT && ui_pk_hrow >= 0)
                ui_pk_cm_start(ui_pk_hrow, x, y);       /* a right click on a row opens its menu */
            else if (b == SDL_BUTTON_RIGHT && ui_pk_hnode >= 0 && ui_pk_tn[ui_pk_hnode].kind == 4)
                ui_pk_cm_start_pl(ui_pk_tn[ui_pk_hnode].name, x, y);    /* v54: a playlist in the tree */""", "mouse right")
R("""        } else if (ui_pk_hbtn == 23) {
            ui_pk_sort_menu(&L);""",
  """        } else if (ui_pk_hbtn == 23) {
            if (!ui_pk_pl[0])                   /* v54: a playlist has no sort */
                ui_pk_sort_menu(&L);""", "mouse sort")
R("""            if (nd->kind == 1) {                /* a drive that is not mounted yet */""",
  """            if (nd->kind == 3) {                /* v54: "New playlist": the name is typed */
                ui_apl_begin();
                ui_apl_show(x, y);
            } else if (nd->kind == 1) {         /* a drive that is not mounted yet */""", "mouse new playlist")

# ------------------------------------------------------------------ start
R("""    ui_pk_hist_clear();
    ui_pk_tree_build();""",
  """    ui_pk_hist_clear();
    ui_pk_pl[0] = 0;
    ui_pk_tree_build();""", "start")

# ------------------------------------------------------------------ write it out
open(PATH, "w", encoding="utf-8").write(src)
print("\nDone: patch_queue_v54 applied.")
