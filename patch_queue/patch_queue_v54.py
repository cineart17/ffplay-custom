#!/usr/bin/env python3
"""patch_queue_v54.py - playlists, reworked library tree, solid arrowheads, on top of v52 and v53.

  - Playlists: Add to playlist in the picker, queue and tile menus; playlists appear in the picker tree and can be played from there.
  - Library tree: Videos and Music at the top, Devices with System, then Playlists. Icons for video, music, system, external drives and playlists.
  - Drop-down arrows are solid triangles, with no arrow lines.
  - ExtDrive, Music, Movies, Videos and Pictures are no longer listed as devices.

Run it from ~/build/ffmpeg-6.1.1:   python3 ~/build/patch_queue_v54.py [path/to/ffplay.c]
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
if "ui_pk_pl_add_new" in src:
    print("Already applied: v54 is in " + path)
    sys.exit(0)
if "ui_pk_send_selected" not in src:
    print("FAILED: apply patch_queue_v52.py first. Nothing written.")
    sys.exit(1)


def fail(msg):
    print("FAILED: " + msg)
    sys.exit(1)


def replace(old, new, what):
    global src
    n = src.count(old)
    if n != 1:
        fail("%s: expected 1 match, found %d" % (what, n))
    src = src.replace(old, new)
    print("ok: " + what)


replace(r'''       UI_IC_ARW_L, UI_IC_ARW_R, UI_IC_ARW_U, UI_IC_ARW_D, UI_IC_PLAY,
       UI_IC_N };''', r'''       UI_IC_ARW_L, UI_IC_ARW_R, UI_IC_ARW_U, UI_IC_ARW_D, UI_IC_PLAY,
       UI_IC_VIDEO, UI_IC_MUSIC, UI_IC_DRIVE_SYSTEM, UI_IC_DRIVE_EXTERNAL, UI_IC_PLAYLIST,
       UI_IC_N };''', "icon enum")

replace(r'''typedef struct { float a, b, c, d, e, f; int arc; } UiStroke;''',
        r'''typedef struct { float a, b, c, d, e, f, g, h, i, j, k, l; int arc, fill; } UiStroke;''', "stroke struct")

replace(r'''    s->a = x0; s->b = y0; s->c = x1; s->d = y1; s->e = s->f = 0.0f; s->arc = 0;''',
        r'''    s->a = x0; s->b = y0; s->c = x1; s->d = y1; s->e = s->f = 0.0f;
    s->g = s->h = s->i = s->j = s->k = s->l = 0.0f; s->arc = 0; s->fill = 0;''', "line stroke")

replace(r'''    s->a = cx; s->b = cy; s->c = r; s->d = 0.0f; s->e = a0; s->f = a1; s->arc = 1;''',
        r'''    s->a = cx; s->b = cy; s->c = r; s->d = 0.0f; s->e = a0; s->f = a1;
    s->g = s->h = s->i = s->j = s->k = s->l = 0.0f; s->arc = 1; s->fill = 0;''', "arc stroke")

replace(r'''static void ic_rrect(float x, float y, float w, float h, float r)
{''', r'''static void ic_tri(float x0, float y0, float x1, float y1, float x2, float y2)
{
    UiStroke *s;

    if (ui_is_n >= UI_IC_MAXS)
        return;
    s = &ui_is[ui_is_n++];
    s->a = x0; s->b = y0; s->g = x1; s->h = y1; s->i = x2; s->j = y2;
    s->c = s->d = s->e = s->f = s->k = s->l = 0.0f; s->arc = 0; s->fill = 1;
}

static void ic_rrect(float x, float y, float w, float h, float r)
{''', "solid triangle helper")

replace(r'''    case UI_IC_ARW_L:                           /* v52: sharp arrows, for the picker only */
        ic_seg(20, 12, 5, 12);
        ic_seg(11, 6, 5, 12);
        ic_seg(5, 12, 11, 18);
        break;
    case UI_IC_ARW_R:
        ic_seg(4, 12, 19, 12);
        ic_seg(13, 6, 19, 12);
        ic_seg(19, 12, 13, 18);
        break;
    case UI_IC_ARW_U:
        ic_seg(12, 20, 12, 5);
        ic_seg(6, 11, 12, 5);
        ic_seg(12, 5, 18, 11);
        break;
    case UI_IC_ARW_D:
        ic_seg(12, 4, 12, 19);
        ic_seg(6, 13, 12, 19);
        ic_seg(12, 19, 18, 13);
        break;
''', r'''    case UI_IC_ARW_L:                           /* v54: solid arrowheads, no lines */
        ic_tri(4, 12, 18, 6, 18, 18);
        break;
    case UI_IC_ARW_R:
        ic_tri(20, 12, 6, 6, 6, 18);
        break;
    case UI_IC_ARW_U:
        ic_tri(12, 4, 6, 18, 18, 18);
        break;
    case UI_IC_ARW_D:
        ic_tri(12, 20, 6, 6, 18, 6);
        break;
''', "solid arrowheads")

replace(r'''    case UI_IC_SEARCH:
        ic_arc(10.5f, 10.5f, 6.5f, 0, 360);''', r'''    case UI_IC_VIDEO: {
        static const float p[] = { 10, 15, 10, 6, 18, 10.5f };

        ic_rrect(3, 5, 18, 14, 2);
        ic_tri(p[0], p[1], p[2], p[3], p[4], p[5]);
        break;
    }
    case UI_IC_MUSIC:
        ic_arc(8, 17, 2.6f, 0, 360);
        ic_arc(17, 15.5f, 2.6f, 0, 360);
        ic_seg(10.5f, 17, 10.5f, 7);
        ic_seg(19.5f, 15.5f, 19.5f, 5.5f);
        ic_seg(10.5f, 7, 19.5f, 5.5f);
        break;
    case UI_IC_DRIVE_SYSTEM:
        ic_rrect(3, 8, 18, 9, 2);
        ic_arc(8, 12.5f, 1.6f, 0, 360);
        ic_seg(14, 12.5f, 18, 12.5f);
        ic_seg(12, 5.5f, 12, 8);
        break;
    case UI_IC_DRIVE_EXTERNAL: {
        static const float h[] = { 14, 10, 17, 12.5f, 14, 15 };

        ic_rrect(5, 7, 13, 11, 2);
        ic_seg(18, 10, 21, 10);
        ic_seg(18, 15, 21, 15);
        ic_tri(h[0], h[1], h[2], h[3], h[4], h[5]);
        break;
    }
    case UI_IC_PLAYLIST:
        ic_seg(3, 7, 13, 7);
        ic_seg(3, 12, 13, 12);
        ic_seg(3, 17, 13, 17);
        ic_tri(15, 8, 15, 16, 21, 12);
        break;
    case UI_IC_SEARCH:
        ic_arc(10.5f, 10.5f, 6.5f, 0, 360);''', "library icons")

replace(r'''static float ui_ic_dist(const UiStroke *s, float px, float py)
{
    if (!s->arc) {''', r'''static float ui_ic_dist(const UiStroke *s, float px, float py)
{
    if (s->fill) {
        float x1 = s->a, y1 = s->b, x2 = s->g, y2 = s->h, x3 = s->i, y3 = s->j;
        float a = (px - x3) * (y1 - y3) - (x1 - x3) * (py - y3);
        float b = (px - x1) * (y2 - y1) - (x2 - x1) * (py - y1);
        float c = (px - x2) * (y3 - y2) - (x3 - x2) * (py - y2), d;
        int neg = a < 0 || b < 0 || c < 0, pos = a > 0 || b > 0 || c > 0;

        if (!neg || !pos)
            return 0.0f;
        d = FFMIN(ui_seg_dist(x1, y1, x2, y2, px, py), ui_seg_dist(x2, y2, x3, y3, px, py));
        return FFMIN(d, ui_seg_dist(x3, y3, x1, y1, px, py));
    }
    if (!s->arc) {''', "filled stroke distance")

replace(r'''/* v52: there is no File / Folder popup any more: "Open Media" goes straight to the picker. */

/* ----- the menu of a queue item (right-click) ----- */''', r'''/* v52: there is no File / Folder popup any more: "Open Media" goes straight to the picker. */

#define UI_PK_PL_MAX 512
#define UI_PK_NPL 16
static char ui_pk_pl_name[UI_PK_NPL][64], ui_pk_pl_last[64];
static int ui_pk_npl = 0;
static char ui_pk_pl_items[UI_PK_PL_MAX][PATH_MAX + 300];

static void ui_pk_pl_dir(char *out, size_t size)
{
    const char *home = getenv("HOME");
    char parent[PATH_MAX + 64];

    if (!home || !home[0]) {
        out[0] = 0;
        return;
    }
    snprintf(parent, sizeof(parent), "%s/.config/ffplay-custom", home);
    mkdir(parent, 0755);
    snprintf(out, size, "%s/playlists", parent);
    mkdir(out, 0755);
}

static void ui_pk_pl_file(const char *name, char *out, size_t size)
{
    char dir[PATH_MAX + 64], safe[64];
    size_t i, j = 0;

    ui_pk_pl_dir(dir, sizeof(dir));
    if (!dir[0]) {
        out[0] = 0;
        return;
    }
    for (i = 0; name && name[i] && j + 1 < sizeof(safe); i++) {
        unsigned char c = (unsigned char)name[i];

        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') ||
            c == ' ' || c == '_' || c == '-' || c == '.')
            safe[j++] = (char)c;
    }
    while (j > 0 && (safe[j - 1] == ' ' || safe[j - 1] == '.'))
        j--;
    if (!j)
        safe[j++] = 'P';
    safe[j] = 0;
    snprintf(out, size, "%s/%s.m3u8", dir, safe);
}

static void ui_pk_pl_load_names(void)
{
    char dir[PATH_MAX + 64];
    DIR *d;
    struct dirent *de;
    int i, j;

    ui_pk_npl = 0;
    ui_pk_pl_dir(dir, sizeof(dir));
    if (!dir[0] || !(d = opendir(dir)))
        return;
    while ((de = readdir(d)) && ui_pk_npl < UI_PK_NPL) {
        char *dot = strrchr(de->d_name, '.');

        if (!dot || dot == de->d_name || strcmp(dot, ".m3u8"))
            continue;
        snprintf(ui_pk_pl_name[ui_pk_npl], sizeof(ui_pk_pl_name[0]), "%.*s", (int)(dot - de->d_name), de->d_name);
        if (ui_pk_pl_name[ui_pk_npl][0])
            ui_pk_npl++;
    }
    closedir(d);
    for (i = 1; i < ui_pk_npl; i++) {
        char tmp[64];

        snprintf(tmp, sizeof(tmp), "%s", ui_pk_pl_name[i]);
        for (j = i; j > 0 && av_strcasecmp(ui_pk_pl_name[j - 1], tmp) > 0; j--)
            snprintf(ui_pk_pl_name[j], sizeof(ui_pk_pl_name[0]), "%s", ui_pk_pl_name[j - 1]);
        snprintf(ui_pk_pl_name[j], sizeof(ui_pk_pl_name[0]), "%s", tmp);
    }
}

static int ui_pk_pl_read(const char *name)
{
    char file[PATH_MAX + 64], line[PATH_MAX + 320];
    FILE *f;
    int n = 0;

    ui_pk_pl_file(name, file, sizeof(file));
    if (!file[0] || !(f = fopen(file, "r")))
        return 0;
    while (n < UI_PK_PL_MAX && fgets(line, sizeof(line), f)) {
        size_t l = strlen(line);

        while (l > 0 && (line[l - 1] == '\n' || line[l - 1] == '\r'))
            line[--l] = 0;
        if (!l || line[0] == '#')
            continue;
        snprintf(ui_pk_pl_items[n], sizeof(ui_pk_pl_items[0]), "%s", line);
        n++;
    }
    fclose(f);
    return n;
}

static void ui_pk_pl_write(const char *name, int n)
{
    char file[PATH_MAX + 64];
    FILE *f;
    int i;

    ui_pk_pl_file(name, file, sizeof(file));
    if (!file[0] || !(f = fopen(file, "w")))
        return;
    for (i = 0; i < n; i++)
        fprintf(f, "%s\n", ui_pk_pl_items[i]);
    fclose(f);
}

static void ui_pk_pl_add(const char *name, const char *path)
{
    int n, i;

    if (!name || !name[0] || !path || !path[0])
        return;
    n = ui_pk_pl_read(name);
    for (i = 0; i < n; i++)
        if (!strcmp(ui_pk_pl_items[i], path))
            return;
    if (n < UI_PK_PL_MAX) {
        snprintf(ui_pk_pl_items[n], sizeof(ui_pk_pl_items[0]), "%s", path);
        n++;
    }
    ui_pk_pl_write(name, n);
}

static void ui_pk_pl_add_new(const char *path)
{
    char name[64], file[PATH_MAX + 64];
    struct stat st;
    int i, n;

    for (i = 1; i < 1000; i++) {
        snprintf(name, sizeof(name), "Playlist %d", i);
        ui_pk_pl_file(name, file, sizeof(file));
        if (stat(file, &st) != 0)
            break;
    }
    snprintf(ui_pk_pl_last, sizeof(ui_pk_pl_last), "%s", name);
    n = ui_pk_pl_read(name);
    if (path && path[0]) {
        for (i = 0; i < n; i++)
            if (!strcmp(ui_pk_pl_items[i], path))
                break;
        if (i == n && n < UI_PK_PL_MAX) {
            snprintf(ui_pk_pl_items[n], sizeof(ui_pk_pl_items[0]), "%s", path);
            n++;
        }
    }
    ui_pk_pl_write(name, n);
}

/* ----- the menu of a queue item (right-click) ----- */''', "playlist storage")

replace(r'''#define UI_CTX_ROW 40

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

    r.w = w + 56 + UI_MENU_ICW;
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
    SDL_Rect r = ui_ctx_rect(ww, wh);
    int i, row_y;

    ui_glass(&r, 18);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    for (i = 0; i < 2; i++) {
        row_y = r.y + 8 + i * UI_CTX_ROW;
        ui_icon(i ? UI_IC_MOON : UI_IC_TRASH, r.x + 28, row_y + UI_CTX_ROW / 2, 18, 240, 240, 240,
                i == ui_ctx_hover ? 255 : 190);
        ui_label(r.x + 28 + UI_MENU_ICW, row_y + UI_CTX_ROW / 2, ui_ctx_label(i), 20, 240, 240, 240,
                 i == ui_ctx_hover ? 255 : 205);
        if (i == ui_ctx_hover) {
            SDL_Rect dot = { r.x + 11, row_y + UI_CTX_ROW / 2 - 3, 6, 6 };

            SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                                   av_clip(cfg_bar_b + 40, 0, 255), 235);
            ui_pill(&dot);
        }
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
''', r'''#define UI_CTX_ROW 40

static int ui_ctx_n = 3, ui_ctx_act[UI_PK_NPL + 2];
static char ui_ctx_lab[UI_PK_NPL + 2][64];

static void ui_ctx_pl_menu(const char *path)
{
    int i;

    ui_pk_pl_load_names();
    ui_ctx_n = 0;
    for (i = 0; i < ui_pk_npl; i++) {
        snprintf(ui_ctx_lab[ui_ctx_n], sizeof(ui_ctx_lab[0]), "%s", ui_pk_pl_name[i]);
        ui_ctx_act[ui_ctx_n++] = 100 + i;
    }
    snprintf(ui_ctx_lab[ui_ctx_n], sizeof(ui_ctx_lab[0]), "New playlist");
    ui_ctx_act[ui_ctx_n++] = 200;
    snprintf(ui_ctx_lab[ui_ctx_n], sizeof(ui_ctx_lab[0]), "Queue item: %.40s", path ? path : "");
    ui_ctx_act[ui_ctx_n++] = -1;
    ui_ctx_hover = -1;
    ui_ctx_open = 1;
}

static SDL_Rect ui_ctx_rect(int ww, int wh)
{
    SDL_Rect r;
    int i, w = 0;

    for (i = 0; i < ui_ctx_n; i++)
        w = FFMAX(w, ui_text_width(ui_ctx_lab[i], 20));
    r.w = w + 56 + UI_MENU_ICW;
    r.h = ui_ctx_n * UI_CTX_ROW + 16;
    r.x = av_clip(ui_ctx_x, 8, FFMAX(ww - r.w - 8, 8));
    r.y = av_clip(ui_ctx_y, 8, FFMAX(wh - r.h - 8, 8));
    return r;
}

static int ui_ctx_hit(const SDL_Rect *r, int x, int y)
{
    if (x < r->x || x >= r->x + r->w || y < r->y + 8 || y >= r->y + 8 + ui_ctx_n * UI_CTX_ROW)
        return -1;
    return (y - r->y - 8) / UI_CTX_ROW;
}

static void ui_ctx_draw(int ww, int wh)
{
    SDL_Rect r = ui_ctx_rect(ww, wh);
    int i, row_y, ico;

    ui_glass(&r, 18);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    for (i = 0; i < ui_ctx_n; i++) {
        row_y = r.y + 8 + i * UI_CTX_ROW;
        ico = ui_ctx_act[i] == 0 ? UI_IC_TRASH : ui_ctx_act[i] == 1 ? UI_IC_MOON : UI_IC_PLAYLIST;
        ui_icon(ico, r.x + 28, row_y + UI_CTX_ROW / 2, 18, 240, 240, 240,
                i == ui_ctx_hover ? 255 : 190);
        ui_label(r.x + 28 + UI_MENU_ICW, row_y + UI_CTX_ROW / 2, ui_ctx_lab[i], 20, 240, 240, 240,
                 i == ui_ctx_hover ? 255 : 205);
        if (i == ui_ctx_hover && ui_ctx_act[i] >= 0) {
            SDL_Rect dot = { r.x + 11, row_y + UI_CTX_ROW / 2 - 3, 6, 6 };

            SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                                   av_clip(cfg_bar_b + 40, 0, 255), 235);
            ui_pill(&dot);
        }
    }
}

/* 0 = remove, 1 = sleep after it, 2 = the playlist menu, 100+ a playlist, 200 = a new playlist */
static void ui_ctx_action(VideoState *is, int act)
{
    char *name = ui_ctx_name;
    char path[4096];
    int i, idx = -1, was_playing;

    snprintf(path, sizeof(path), "%s", name ? name : "");
    ui_ctx_open = 0;
    ui_ctx_hover = -1;
    if (act < 0) {
        ui_ctx_name = NULL;
        return;
    }
    if (act == 2) {
        ui_ctx_pl_menu(path);
        return;
    }
    if (act >= 100 && act < 100 + UI_PK_NPL) {
        ui_pk_pl_add(ui_pk_pl_name[act - 100], path);
        ui_ctx_name = NULL;
        return;
    }
    if (act == 200) {
        ui_pk_pl_add_new(path);
        ui_ctx_name = NULL;
        return;
    }
    ui_ctx_name = NULL;
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
            ui_end_current(is);
    } else {
        q_sleep_end = 0;
        ui_sleep_gain = 1.0f;
        q_sleep_item = (q_sleep_item == q_items[idx]) ? NULL : q_items[idx];
        ui_sleep_sel = q_sleep_item ? 1 : 0;
    }
}
''', "queue playlist menu")

replace(r'''            ui_ctx_open = 1;
            ui_ctx_x = ev->button.x;
            ui_ctx_y = ev->button.y;
            ui_ctx_name = q_items[item];
            ui_ctx_hover = -1;''', r'''            ui_ctx_open = 1;
            ui_ctx_x = ev->button.x;
            ui_ctx_y = ev->button.y;
            ui_ctx_name = q_items[item];
            ui_ctx_n = 3;
            ui_ctx_act[0] = 0;
            ui_ctx_act[1] = 1;
            ui_ctx_act[2] = 2;
            snprintf(ui_ctx_lab[0], sizeof(ui_ctx_lab[0]), "Remove from queue");
            snprintf(ui_ctx_lab[1], sizeof(ui_ctx_lab[0]), "%s",
                     ui_ctx_name && ui_ctx_name == q_sleep_item ? "Cancel sleep after item" : "Sleep after this item");
            snprintf(ui_ctx_lab[2], sizeof(ui_ctx_lab[0]), "Add to playlist");
            ui_ctx_hover = -1;''', "queue menu open")

replace(r'''#define UI_TVC_ROW 38
static int ui_tvc_x = 0, ui_tvc_y = 0, ui_tvc_hover = -1, ui_tvc_n = 0, ui_tvc_act[4];
static char ui_tvc_path[4096];
static const char * const ui_tvc_label[4] = { "Play", "Play next", "Add to queue", "Remove from queue" };''',
        r'''#define UI_TVC_ROW 38
static int ui_tvc_x = 0, ui_tvc_y = 0, ui_tvc_hover = -1, ui_tvc_n = 0, ui_tvc_act[UI_PK_NPL + 2];
static char ui_tvc_path[4096], ui_tvc_lab[UI_PK_NPL + 2][64];''', "tile menu state")

replace(r'''        w = FFMAX(w, ui_text_width(ui_tvc_label[ui_tvc_act[i]], 18));''',
        r'''        w = FFMAX(w, ui_text_width(ui_tvc_lab[i], 18));''', "tile menu width")

replace(r'''        ui_label(r.x + 30, ry + UI_TVC_ROW / 2, ui_tvc_label[ui_tvc_act[i]], 18, 240, 240, 240, i == ui_tvc_hover ? 255 : 205);''',
        r'''        ui_label(r.x + 30, ry + UI_TVC_ROW / 2, ui_tvc_lab[i], 18, 240, 240, 240, i == ui_tvc_hover ? 255 : 205);''', "tile menu draw")

replace(r'''static void ui_tvc_do(VideoState *is, int act)
{
    char path[4096];
    int idx;

    snprintf(path, sizeof(path), "%s", ui_tvc_path);
    ui_tvc_open = 0;
    ui_tvc_hover = -1;
    switch (act) {
    case 0:                                     /* Play */
        ui_tv_play(is, path);
        break;
    case 1:                                     /* Play next: right after the item that plays */
        idx = ui_tv_qindex(path);
        if (idx < 0) {
            queue_add(path);
            idx = ui_tv_qindex(path);
        }
        if (idx >= 0 && idx != q_pos && idx != q_pos + 1)
            queue_move(idx, idx > q_pos ? q_pos + 1 : q_pos);
        break;
    case 2:                                     /* Add to queue */
        if (ui_tv_qindex(path) < 0)
            queue_add(path);
        break;
    default:                                    /* Remove from queue */
        idx = ui_tv_qindex(path);
        if (idx >= 0 && idx != q_pos)
            queue_remove(idx);
        break;
    }
    if (ui_tv_q[0] && act != 0)
        ui_tv_search();                         /* "In this queue" follows what changed */
    ui_tv_moving = 1;
    is->force_refresh = 1;
}
''', r'''static void ui_tvc_pl_menu(const char *path)
{
    int i;

    ui_pk_pl_load_names();
    ui_tvc_n = 0;
    for (i = 0; i < ui_pk_npl; i++) {
        snprintf(ui_tvc_lab[ui_tvc_n], sizeof(ui_tvc_lab[0]), "%s", ui_pk_pl_name[i]);
        ui_tvc_act[ui_tvc_n++] = 100 + i;
    }
    snprintf(ui_tvc_lab[ui_tvc_n], sizeof(ui_tvc_lab[0]), "New playlist");
    ui_tvc_act[ui_tvc_n++] = 200;
    ui_tvc_hover = -1;
    ui_tvc_open = 1;
    ui_tv_moving = 1;
}

static void ui_tvc_do(VideoState *is, int act)
{
    char path[4096];
    int idx;

    snprintf(path, sizeof(path), "%s", ui_tvc_path);
    ui_tvc_open = 0;
    ui_tvc_hover = -1;
    if (act == 4) {
        ui_tvc_pl_menu(path);
        return;
    }
    if (act >= 100 && act < 100 + UI_PK_NPL) {
        ui_pk_pl_add(ui_pk_pl_name[act - 100], path);
        ui_tv_moving = 1;
        is->force_refresh = 1;
        return;
    }
    if (act == 200) {
        ui_pk_pl_add_new(path);
        ui_tv_moving = 1;
        is->force_refresh = 1;
        return;
    }
    switch (act) {
    case 0:
        ui_tv_play(is, path);
        break;
    case 1:
        idx = ui_tv_qindex(path);
        if (idx < 0) {
            queue_add(path);
            idx = ui_tv_qindex(path);
        }
        if (idx >= 0 && idx != q_pos && idx != q_pos + 1)
            queue_move(idx, idx > q_pos ? q_pos + 1 : q_pos);
        break;
    case 2:
        if (ui_tv_qindex(path) < 0)
            queue_add(path);
        break;
    case 3:
        idx = ui_tv_qindex(path);
        if (idx >= 0 && idx != q_pos)
            queue_remove(idx);
        break;
    }
    if (ui_tv_q[0] && act != 0)
        ui_tv_search();
    ui_tv_moving = 1;
    is->force_refresh = 1;
}
''', "tile playlist menu")

replace(r'''    ui_tvc_act[n++] = 0;                        /* Play */
    if (qi < 0 || (qi != q_pos && qi != q_pos + 1))
        ui_tvc_act[n++] = 1;                    /* Play next */
    if (qi < 0)
        ui_tvc_act[n++] = 2;                    /* Add to queue */
    else if (qi != q_pos)
        ui_tvc_act[n++] = 3;                    /* Remove from queue */
    ui_tvc_n = n;''', r'''    ui_tvc_act[n] = 0;
    snprintf(ui_tvc_lab[n++], sizeof(ui_tvc_lab[0]), "Play");
    if (qi < 0 || (qi != q_pos && qi != q_pos + 1)) {
        ui_tvc_act[n] = 1;
        snprintf(ui_tvc_lab[n++], sizeof(ui_tvc_lab[0]), "Play next");
    }
    if (qi < 0) {
        ui_tvc_act[n] = 2;
        snprintf(ui_tvc_lab[n++], sizeof(ui_tvc_lab[0]), "Add to queue");
    } else if (qi != q_pos) {
        ui_tvc_act[n] = 3;
        snprintf(ui_tvc_lab[n++], sizeof(ui_tvc_lab[0]), "Remove from queue");
    }
    ui_tvc_act[n] = 4;
    snprintf(ui_tvc_lab[n++], sizeof(ui_tvc_lab[0]), "Add to playlist");
    ui_tvc_n = n;''', "tile menu labels")

replace(r'''/* ----- the menus: a row (right click: Play now, Play next, Add to queue; a folder: Open folder, Play folder, ...) and Sort ----- */
enum { UI_PK_A_PLAY, UI_PK_A_ADD, UI_PK_A_ENTER, UI_PK_A_NEXT, UI_PK_A_SORT = 10 };
static int ui_pk_cm_kind = 0, ui_pk_cm_x = 0, ui_pk_cm_y = 0, ui_pk_cm_n = 0, ui_pk_cm_hot = -1, ui_pk_cm_w = 230;
static int ui_pk_cm_act[4];
static char ui_pk_cm_lab[4][24], ui_pk_cm_path[PATH_MAX + 300], ui_pk_cm_nm[200];''',
        r'''/* ----- the menus: a row (right click: Play now, Play next, Add to queue, Add to playlist; a folder: Open folder, Play folder, ...) and Sort ----- */
enum { UI_PK_A_PLAY, UI_PK_A_ADD, UI_PK_A_ENTER, UI_PK_A_NEXT, UI_PK_A_PL,
       UI_PK_A_SORT = 10, UI_PK_A_PLSEL = 20, UI_PK_A_PLNEW = 40 };
static int ui_pk_cm_kind = 0, ui_pk_cm_x = 0, ui_pk_cm_y = 0, ui_pk_cm_n = 0, ui_pk_cm_hot = -1, ui_pk_cm_w = 230;
static int ui_pk_cm_act[UI_PK_NPL + 2];
static char ui_pk_cm_lab[UI_PK_NPL + 2][64], ui_pk_cm_path[PATH_MAX + 300], ui_pk_cm_nm[200];
static char ui_pk_pl_target[PATH_MAX + 300];''', "picker menu state")

replace(r'''    snprintf(ui_pk_cm_lab[ui_pk_cm_n], 24, "%s", label);''',
        r'''    snprintf(ui_pk_cm_lab[ui_pk_cm_n], sizeof(ui_pk_cm_lab[0]), "%s", label);''', "picker menu item label")

replace(r'''    if (e->dir) {
        ui_pk_cm_item("Open folder", UI_PK_A_ENTER);
        ui_pk_cm_item("Play folder", UI_PK_A_PLAY);
        ui_pk_cm_item("Play folder next", UI_PK_A_NEXT);
        ui_pk_cm_item("Add folder to queue", UI_PK_A_ADD);
    } else {
        ui_pk_cm_item("Play now", UI_PK_A_PLAY);
        ui_pk_cm_item("Play next", UI_PK_A_NEXT);
        ui_pk_cm_item("Add to queue", UI_PK_A_ADD);
    }''', r'''    if (e->dir) {
        ui_pk_cm_item("Open folder", UI_PK_A_ENTER);
        ui_pk_cm_item("Play folder", UI_PK_A_PLAY);
        ui_pk_cm_item("Play folder next", UI_PK_A_NEXT);
        ui_pk_cm_item("Add folder to queue", UI_PK_A_ADD);
        ui_pk_cm_item("Add folder to playlist", UI_PK_A_PL);
    } else {
        ui_pk_cm_item("Play now", UI_PK_A_PLAY);
        ui_pk_cm_item("Play next", UI_PK_A_NEXT);
        ui_pk_cm_item("Add to queue", UI_PK_A_ADD);
        ui_pk_cm_item("Add to playlist", UI_PK_A_PL);
    }''', "picker menu item")

replace(r'''static void ui_pk_sort_menu(const UiPkLay *L)
{''', r'''static void ui_pk_pl_menu(const char *path)
{
    int i;

    snprintf(ui_pk_pl_target, sizeof(ui_pk_pl_target), "%s", path);
    ui_pk_pl_load_names();
    ui_pk_cm_kind = 2;
    ui_pk_cm_w = 300;
    ui_pk_cm_n = 0;
    ui_pk_cm_hot = -1;
    for (i = 0; i < ui_pk_npl; i++)
        ui_pk_cm_item(ui_pk_pl_name[i], UI_PK_A_PLSEL + i);
    ui_pk_cm_item("New playlist", UI_PK_A_PLNEW);
    ui_pk_cm_open = 1;
}

static void ui_pk_sort_menu(const UiPkLay *L)
{''', "picker playlist menu")

replace(r'''static void ui_pk_cm_do(VideoState *is, int act)
{
    char name[sizeof(ui_pk_cm_nm)];

    ui_pk_cm_open = 0;
    if (act >= UI_PK_A_SORT) {
        ui_pk_set_sort(act - UI_PK_A_SORT);
        return;
    }
    snprintf(name, sizeof(name), "%s", ui_pk_cm_nm);
''', r'''static void ui_pk_cm_do(VideoState *is, int act)
{
    char name[sizeof(ui_pk_cm_nm)];

    ui_pk_cm_open = 0;
    if (act == UI_PK_A_PL) {
        ui_pk_pl_menu(ui_pk_cm_path);
        return;
    }
    if (act >= UI_PK_A_PLSEL && act < UI_PK_A_PLSEL + UI_PK_NPL) {
        snprintf(name, sizeof(name), "%s", ui_pk_pl_name[act - UI_PK_A_PLSEL]);
        ui_pk_pl_add(name, ui_pk_pl_target);
        snprintf(ui_pk_note, sizeof(ui_pk_note), "Added to playlist: %.120s", name);
        ui_pk_note_until = av_gettime_relative() + 2500000;
        ui_pk_tree_playlists();
        return;
    }
    if (act == UI_PK_A_PLNEW) {
        ui_pk_pl_add_new(ui_pk_pl_target);
        snprintf(ui_pk_note, sizeof(ui_pk_note), "Added to new playlist: %.120s", ui_pk_pl_last);
        ui_pk_note_until = av_gettime_relative() + 2500000;
        ui_pk_tree_playlists();
        return;
    }
    if (act >= UI_PK_A_SORT && act < UI_PK_A_SORT + 3) {
        ui_pk_set_sort(act - UI_PK_A_SORT);
        return;
    }
    snprintf(name, sizeof(name), "%s", ui_pk_cm_nm);
''', "picker menu action")

replace(r'''static void ui_pk_cm_draw(void)
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
            ui_icon(ui_pk_desc ? UI_IC_ARW_D : UI_IC_ARW_U, row.x + row.w - 28, row.y + row.h / 2, 16, av_clip(cfg_bar_r + 70, 0, 255),
                    av_clip(cfg_bar_g + 70, 0, 255), av_clip(cfg_bar_b + 70, 0, 255), 255);
    }
}
''', r'''static void ui_pk_cm_draw(void)
{
    SDL_Rect r;
    int i;
    char tmp[64];

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
        snprintf(tmp, sizeof(tmp), "%s", ui_pk_cm_lab[i]);
        ui_fit_text(tmp, 16, row.w - 44);
        ui_label(row.x + 14, row.y + row.h / 2, tmp, 16, 245, 245, 245, i == ui_pk_cm_hot || on ? 255 : 215);
        if (on)
            ui_icon(ui_pk_desc ? UI_IC_ARW_D : UI_IC_ARW_U, row.x + row.w - 28, row.y + row.h / 2, 16, av_clip(cfg_bar_r + 70, 0, 255),
                    av_clip(cfg_bar_g + 70, 0, 255), av_clip(cfg_bar_b + 70, 0, 255), 255);
    }
}
''', "picker menu draw")

replace(r'''static void ui_pk_enter(const UiPkEnt *e)       /* go into a folder */
{''', r'''static void ui_pk_pl_play(VideoState *is, const char *name)
{
    int n, i;

    n = ui_pk_pl_read(name);
    if (!n) {
        snprintf(ui_pk_note, sizeof(ui_pk_note), "Playlist is empty: %.120s", name);
        ui_pk_note_until = av_gettime_relative() + 2500000;
        return;
    }
    for (i = 0; i < n; i++)
        ui_pk_send(is, i ? 'a' : 'o', ui_pk_pl_items[i]);
    snprintf(ui_pk_note, sizeof(ui_pk_note), "Playing playlist: %.120s", name);
    ui_pk_note_until = av_gettime_relative() + 2500000;
    ui_pk_close(is);
}

static void ui_pk_enter(const UiPkEnt *e)       /* go into a folder */
{''', "playlist playback")

replace(r'''/* The drives part of the tree, made again from ui_pk_dev (the places above it keep their drop downs) */
static void ui_pk_tree_devs(void)
{''', r'''static int ui_pk_dev_is_folder(const UiPkDev *dv)
{
    static const char *const skip[] = { "ExtDrive", "Music", "Movies", "Videos", "Pictures" };
    const char *base = strrchr(dv->label, '/');
    int i;

    base = base ? base + 1 : dv->label;
    for (i = 0; i < 5; i++)
        if (!av_strcasecmp(base, skip[i]) || !av_strcasecmp(dv->label, skip[i]))
            return 1;
    return 0;
}

static void ui_pk_tree_playlists(void)
{
    int i, f = -1;

    for (i = 0; i < ui_pk_ntn; i++)
        if (ui_pk_tn[i].grp == 3) {
            f = i;
            break;
        }
    if (f >= 0) {
        for (i = f; i < ui_pk_ntn; i++)
            ui_pk_tn_free(&ui_pk_tn[i]);
        ui_pk_ntn = f;
    }
    ui_pk_tn_insert(ui_pk_ntn, "Playlists", "", NULL, 0, 2, 3);
    ui_pk_pl_load_names();
    for (i = 0; i < ui_pk_npl; i++)
        ui_pk_tn_insert(ui_pk_ntn, ui_pk_pl_name[i], ui_pk_pl_name[i], NULL, 0, 3, 3);
    ui_pk_tn_insert(ui_pk_ntn, "New playlist", "", NULL, 0, 4, 3);
}

/* The drives part of the tree, made again from ui_pk_dev (the places above it keep their drop downs) */
static void ui_pk_tree_devs(void)
{''', "device filter and playlists")

replace(r'''static void ui_pk_tree_devs(void)
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
''', r'''static void ui_pk_tree_devs(void)
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
    ui_pk_tn_insert(ui_pk_ntn, "Devices", "", NULL, 0, 2, 1);
    ui_pk_tn_insert(ui_pk_ntn, "System", "/", NULL, 0, 0, 1);
    ui_pk_tn[ui_pk_ntn - 1].kids = 0;
    for (i = 0; i < ui_pk_ndev; i++) {
        char real[PATH_MAX];
        const char *m = ui_pk_dev[i].mnt;

        if (ui_pk_dev_is_folder(&ui_pk_dev[i]))
            continue;
        if (m[0] && realpath(m, real))
            m = real;
        ui_pk_tn_insert(ui_pk_ntn, ui_pk_dev[i].label, m, ui_pk_dev[i].dev[0] ? ui_pk_dev[i].dev : NULL, 0, ui_pk_dev[i].mnt[0] ? 0 : 1, 1);
    }
}
''', "device tree")

replace(r'''static void ui_pk_tree_build(void)
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
''', r'''static void ui_pk_tree_build(void)
{
    static const char * const names[] = { "Videos", "Music" };
    const char *home = getenv("HOME");
    char base[PATH_MAX], real[PATH_MAX];
    int i;

    ui_pk_tree_clear();
    ui_pk_tn_insert(ui_pk_ntn, "Folders", "", NULL, 0, 2, 0);
    for (i = 0; home && home[0] && i < 2; i++) {
        struct stat st;

        snprintf(base, sizeof(base), "%s/%s", home, names[i]);
        if (stat(base, &st) == 0 && S_ISDIR(st.st_mode))
            ui_pk_tn_insert(ui_pk_ntn, names[i], realpath(base, real) ? real : base, NULL, 0, 0, 0);
    }
    ui_pk_tree_devs();
    ui_pk_tree_playlists();
}
''', "library tree")

replace(r'''    ui_pk_rec_save();
    ui_pk_tree_recents();
}''', r'''    ui_pk_rec_save();
}''', "hide recent places")

replace(r'''            memcpy(ui_pk_dev, ui_pk_dev_tmp, sizeof(UiPkDev) * ui_pk_dev_tmpn);
            ui_pk_ndev = ui_pk_dev_tmpn;
            ui_pk_tree_devs();
            if (is)''', r'''            memcpy(ui_pk_dev, ui_pk_dev_tmp, sizeof(UiPkDev) * ui_pk_dev_tmpn);
            ui_pk_ndev = ui_pk_dev_tmpn;
            ui_pk_tree_devs();
            ui_pk_tree_playlists();
            if (is)''', "keep playlists after device scan")

replace(r'''            int ry = L.side.y + 6 + i * UI_PK_TROW - (int)ui_pk_ssc, ix, on, mounted = nd->kind == 0;''',
        r'''            int ry = L.side.y + 6 + i * UI_PK_TROW - (int)ui_pk_ssc, ix, on, mounted = nd->kind == 0 || nd->kind == 3 || nd->kind == 4, ico;''', "tree row variables")

replace(r'''            ui_icon(UI_IC_FOLDER, ix + 18, ry + UI_PK_TROW / 2, 16, 245, 245, 245, mounted ? (on ? 255 : 210) : 120);''',
        r'''            ico = UI_IC_FOLDER;
            if (nd->grp == 0 && nd->depth == 0)
                ico = !av_strcasecmp(nd->name, "Videos") ? UI_IC_VIDEO : UI_IC_MUSIC;
            else if (nd->kind == 3 || nd->kind == 4)
                ico = UI_IC_PLAYLIST;
            else if (nd->grp == 1)
                ico = nd->path[0] && !strcmp(nd->path, "/") ? UI_IC_DRIVE_SYSTEM : UI_IC_DRIVE_EXTERNAL;
            ui_icon(ico, ix + 18, ry + UI_PK_TROW / 2, 16, 245, 245, 245, mounted ? (on ? 255 : 210) : 120);''', "tree row icons")

replace(r'''            if (nd->kind == 1) {                /* a drive that is not mounted yet */
                for (i = 0; i < ui_pk_ndev; i++)
                    if (nd->dev && !strcmp(ui_pk_dev[i].dev, nd->dev)) {
                        ui_pk_mount(&ui_pk_dev[i]);
                        break;
                    }
            } else if (nd->grp == 1 && nd->dev && nd->depth == 0 && x >= L.side.x + L.side.w - 42) {''',
        r'''            if (nd->kind == 1) {                /* a drive that is not mounted yet */
                for (i = 0; i < ui_pk_ndev; i++)
                    if (nd->dev && !strcmp(ui_pk_dev[i].dev, nd->dev)) {
                        ui_pk_mount(&ui_pk_dev[i]);
                        break;
                    }
            } else if (nd->kind == 3) {
                ui_pk_pl_play(is, nd->name);
                return 1;
            } else if (nd->kind == 4) {
                ui_pk_pl_add_new(NULL);
                snprintf(ui_pk_note, sizeof(ui_pk_note), "New playlist: %.120s", ui_pk_pl_last);
                ui_pk_note_until = av_gettime_relative() + 2500000;
                ui_pk_tree_playlists();
                return 1;
            } else if (nd->grp == 1 && nd->dev && nd->depth == 0 && x >= L.side.x + L.side.w - 42) {''', "tree mouse playlists")

open(path, "w", encoding="utf-8").write(src)
print("\nDone: patch_queue_v54 applied.")
