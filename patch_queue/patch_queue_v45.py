#!/usr/bin/env python3
# Update 45 for ffplay-custom (on top of patch_queue_v44.py).
#   * The file picker sorts: Name, Date or Size, on the path bar; a click on the one that is on turns the order round (a small curve
#     shows which way). Folders stay first. Ticked files stay ticked when the order changes.
#   * Right click on a row of the picker no longer goes up one folder: it opens a small menu. A file: Play now, Add to queue. A folder:
#     Open folder, Play folder, Add folder to queue. "Add to queue" keeps the picker open and says what was added at the top.
#   * The x of a queue item shows only on the row the mouse is on, and it is a smooth one.
#   * The arrows at the end of the menu rows, and the separators of the picker's path, are soft curves (no corners) instead of ">".
#   * Crisper text: the letters are placed with sub-pixel accuracy, which tightens the loose spacing in titles.
#     crisp_text = 0 in ~/.config/ffplay-custom/settings.conf brings back the old rendering, to compare.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v44.py. Writes the file only if every edit matches.
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


if "ui_pk_cm_open" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_pk_draw" not in src:
    print("Apply patch_queue_v44.py first. Nothing written.")
    sys.exit(1)

# ---------------------------------------------------------------- soft shapes: curves and a smooth x
patch("icon ids", r'''UI_IC_EXPAND, UI_IC_DROP, UI_IC_BOOKMARK, UI_IC_EXIT, UI_IC_MOUSE,
       UI_IC_N };''', r'''UI_IC_EXPAND, UI_IC_DROP, UI_IC_BOOKMARK, UI_IC_EXIT, UI_IC_MOUSE,
       UI_IC_CHEV_R, UI_IC_CHEV_D, UI_IC_CHEV_U, UI_IC_X,
       UI_IC_N };''')
patch("icons: curves and x", r'''    case UI_IC_MOON:
        ic_arc(12, 12, 9, 5, 265);''', r'''    case UI_IC_CHEV_R:                          /* v45: a soft curve, no corner: an arc with round ends */
        ic_arc(7.5f, 12, 7, -60, 60);
        break;
    case UI_IC_CHEV_D:
        ic_arc(12, 7.5f, 7, 30, 150);
        break;
    case UI_IC_CHEV_U:
        ic_arc(12, 16.5f, 7, 210, 330);
        break;
    case UI_IC_X:
        ic_seg(7, 7, 17, 17);
        ic_seg(17, 7, 7, 17);
        break;
    case UI_IC_MOON:
        ic_arc(12, 12, 9, 5, 265);''')
patch("menu arrows are curves", r'''static void ui_chevron(int x, int cy, int a)
{
    ui_arrow(x + 3, cy, 1, a - 60);
}''', r'''static void ui_chevron(int x, int cy, int a)
{
    ui_icon(UI_IC_CHEV_R, x + 3, cy, 16, 225, 225, 225, av_clip((int)((a - 40) * ui_fade), 0, 255));
}''')
patch("the x shows on the row of the mouse", r'''        /* the x that removes the item */
        SDL_SetRenderDrawColor(renderer, 230, 230, 230, (int)(((lit && hk == UI_Q_DEL) ? 255 : 120) * ui_fade));
        ui_q_line(right - 71, cy - 4, right - 63, cy + 4);
        ui_q_line(right - 71, cy + 4, right - 63, cy - 4);''', r'''        /* the x that removes the item: only on the row the mouse is on (v45) */
        if (lit)
            ui_icon(UI_IC_X, right - 67, cy, 16, 230, 230, 230, (int)((hk == UI_Q_DEL ? 255 : 140) * ui_fade));''')

# ---------------------------------------------------------------- crisper text
patch("crisp text switch", r'''static int     cfg_picker = 1;''', r'''static int     cfg_crisp = 1;               /* 1 = letters placed with sub-pixel accuracy (v45) */
static int     cfg_picker = 1;''')
patch("crisp text switch read", r'''        else if (sscanf(line, " picker = %d", &n) == 1)
            cfg_picker = (n != 0);''', r'''        else if (sscanf(line, " picker = %d", &n) == 1)
            cfg_picker = (n != 0);
        else if (sscanf(line, " crisp_text = %d", &n) == 1)
            cfg_crisp = (n != 0);''')
patch("crisp text switch written", r'''picker = %d\n\n", cfg_picker);''', r'''picker = %d\n\n", cfg_picker);
    fprintf(f, "# 1 = letters are placed with sub-pixel accuracy (tighter, crisper titles), 0 = the older rendering\ncrisp_text = %d\n\n", cfg_crisp);''')
patch("crisp text", r'''    TTF_SetFontHinting(ui_fonts[i].font, TTF_HINTING_LIGHT);''', r'''#ifdef TTF_HINTING_LIGHT_SUBPIXEL
    TTF_SetFontHinting(ui_fonts[i].font, cfg_crisp ? TTF_HINTING_LIGHT_SUBPIXEL : TTF_HINTING_LIGHT);
#else
    TTF_SetFontHinting(ui_fonts[i].font, cfg_crisp ? TTF_HINTING_NORMAL : TTF_HINTING_LIGHT);
#endif
    TTF_SetFontKerning(ui_fonts[i].font, 1);''')

# ---------------------------------------------------------------- the picker: sorting
patch("sort state and order", r'''static int ui_pk_cmp(const void *a, const void *b)
{
    const UiPkEnt *x = a, *y = b;

    if (x->dir != y->dir)
        return y->dir - x->dir;                 /* the folders first */
    return av_strcasecmp(x->name, y->name);
}''', r'''static int ui_pk_sortk = 0, ui_pk_desc = 0;     /* v45: sorted by 0 name, 1 date, 2 size; desc = the other way round */
static char ui_pk_note[160];                    /* what was just added, shown at the top for a moment */
static int64_t ui_pk_note_until = 0;

static int ui_pk_cmp(const void *a, const void *b)
{
    const UiPkEnt *x = a, *y = b;
    int c = 0;

    if (x->dir != y->dir)
        return y->dir - x->dir;                 /* the folders first */
    if (ui_pk_sortk == 1 && x->mtime != y->mtime)
        c = x->mtime < y->mtime ? -1 : 1;
    else if (ui_pk_sortk == 2 && !x->dir && x->size != y->size)
        c = x->size < y->size ? -1 : 1;
    if (c)
        return ui_pk_desc ? -c : c;
    c = av_strcasecmp(x->name, y->name);
    return ui_pk_sortk == 0 && ui_pk_desc ? -c : c;
}''')
patch("resort", r'''/* Read a folder. Returns 0 if it cannot be read (nothing changes then). */''', r'''/* Sort the open folder again (the order was changed): what is ticked stays ticked, and the cursor stays on its row */
static void ui_pk_resort(void)
{
    char *keep = NULL, **names = NULL;
    int ns = 0, i, j;

    if (ui_pk_nv > 0)
        keep = strdup(ui_pk_e[ui_pk_vis[ui_pk_cur]].name);
    for (i = 0; i < ui_pk_n; i++)
        ns += ui_pk_sel[i] != 0;
    if (ns && (names = malloc(sizeof(char *) * ns))) {
        for (i = 0, j = 0; i < ui_pk_n; i++)
            if (ui_pk_sel[i])
                names[j++] = strdup(ui_pk_e[i].name);
    }
    qsort(ui_pk_e, ui_pk_n, sizeof(*ui_pk_e), ui_pk_cmp);
    memset(ui_pk_sel, 0, ui_pk_n + 1);
    for (j = 0; names && j < ns; j++) {
        for (i = 0; i < ui_pk_n; i++)
            if (names[j] && !strcmp(ui_pk_e[i].name, names[j])) {
                ui_pk_sel[i] = 1;
                break;
            }
        free(names[j]);
    }
    free(names);
    ui_pk_refilter();
    for (i = 0; keep && i < ui_pk_nv; i++)
        if (!strcmp(ui_pk_e[ui_pk_vis[i]].name, keep)) {
            ui_pk_cur = i;
            ui_pk_sc = FFMAX(0.0, (i - 3) * (double)UI_PK_ROW);
            break;
        }
    free(keep);
}

/* Read a folder. Returns 0 if it cannot be read (nothing changes then). */''')
patch("layout has the sort buttons", r'''    SDL_Rect p, side, bar, list, up, cancel, ok, extra, all, hid;
    int side_on, tog;''', r'''    SDL_Rect p, side, bar, list, up, cancel, ok, extra, all, hid, sort[3];
    int side_on, tog, sort_on;''')
patch("layout of the sort buttons", r'''    L->hid = L->all;
    L->hid.x = L->all.x + L->all.w + 8;
    L->hid.w = 100;
}''', r'''    L->hid = L->all;
    L->hid.x = L->all.x + L->all.w + 8;
    L->hid.w = 100;
    {                                           /* v45: Name, Date, Size at the right end of the path bar */
        static const char * const nm[3] = { "Name", "Date", "Size" };
        int k, xr = L->bar.x + L->bar.w - 14;

        L->sort_on = L->bar.w >= 500;
        for (k = 2; k >= 0; k--) {
            L->sort[k].w = ui_text_width(nm[k], 15) + (k == ui_pk_sortk ? 40 : 24);
            L->sort[k].h = 30;
            L->sort[k].y = L->bar.y + 7;
            L->sort[k].x = xr - L->sort[k].w;
            xr -= L->sort[k].w + 2;
        }
    }
}''')
patch("path leaves room for the sort buttons", r'''int ns = 0, pos, sw, total, from = 0, avail = L.bar.w - L.up.w - 12 - 32, len = (int)strlen(ui_pk_dir);''',
      r'''int ns = 0, pos, sw, total, from = 0, avail = L.bar.w - L.up.w - 12 - 32 - (L.sort_on ? L.bar.x + L.bar.w - L.sort[0].x : 0),
            len = (int)strlen(ui_pk_dir);''')
patch("sort buttons are drawn", r'''    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 26);
    SDL_RenderDrawLine(renderer, L.list.x, L.list.y, L.list.x + L.list.w, L.list.y);''', r'''    if (L.sort_on) {
        static const char * const nm[3] = { "Name", "Date", "Size" };

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
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 26);
    SDL_RenderDrawLine(renderer, L.list.x, L.list.y, L.list.x + L.list.w, L.list.y);''')
patch("path separators are curves", r'''                ui_label(x + 10, cy, ">", 14, 150, 150, 150, 255);''',
      r'''                ui_icon(UI_IC_CHEV_R, x + 13, cy, 14, 150, 150, 150, 255);''')
patch("sort buttons under the mouse", r'''    if (ui_pk_in(&L.up, x, y))
        ui_pk_hbtn = 0;''', r'''    if (L.sort_on && y >= L.bar.y && y < L.bar.y + L.bar.h) {
        for (i = 0; i < 3; i++)
            if (ui_pk_in(&L.sort[i], x, y))
                ui_pk_hbtn = 10 + i;
    }
    if (ui_pk_hbtn >= 10)
        ;
    else if (ui_pk_in(&L.up, x, y))
        ui_pk_hbtn = 0;''')
patch("a click on a sort button", r'''        } else if (ui_pk_hplace >= 0) {
            ui_pk_go(ui_pk_pl[ui_pk_hplace].path);''', r'''        } else if (ui_pk_hbtn >= 10) {
            int k = ui_pk_hbtn - 10;

            if (k == ui_pk_sortk) {
                ui_pk_desc = !ui_pk_desc;       /* the one that is on: the other way round */
            } else {
                ui_pk_sortk = k;
                ui_pk_desc = k != 0;            /* the newest and the biggest first, names from A */
            }
            ui_pk_resort();
        } else if (ui_pk_hplace >= 0) {
            ui_pk_go(ui_pk_pl[ui_pk_hplace].path);''')

# ---------------------------------------------------------------- the picker: right click on a row
patch("row menu", r'''static void ui_pk_draw(void)
{''', r'''/* v45: the menu of a row (right click). A file: Play now, Add to queue. A folder: Open folder, Play folder, Add folder to queue. */
enum { UI_PK_A_PLAY, UI_PK_A_ADD, UI_PK_A_ENTER };
static int ui_pk_cm_open = 0, ui_pk_cm_x = 0, ui_pk_cm_y = 0, ui_pk_cm_e = -1, ui_pk_cm_n = 0, ui_pk_cm_hot = -1;
static int ui_pk_cm_act[3];
static char ui_pk_cm_lab[3][24];

static SDL_Rect ui_pk_cm_rect(void)
{
    SDL_Rect r;
    int ww, wh;

    SDL_GetWindowSize(window, &ww, &wh);
    r.w = 230;
    r.h = ui_pk_cm_n * 36 + 12;
    r.x = av_clip(ui_pk_cm_x, 4, FFMAX(ww - r.w - 4, 4));
    r.y = av_clip(ui_pk_cm_y, 4, FFMAX(wh - r.h - 4, 4));
    return r;
}

static void ui_pk_cm_start(int row, int x, int y)
{
    int e = ui_pk_vis[row];

    ui_pk_cm_e = e;
    ui_pk_cm_x = x;
    ui_pk_cm_y = y;
    ui_pk_cm_n = 0;
    ui_pk_cm_hot = -1;
    if (ui_pk_e[e].dir) {
        snprintf(ui_pk_cm_lab[0], 24, "Open folder");
        ui_pk_cm_act[0] = UI_PK_A_ENTER;
        snprintf(ui_pk_cm_lab[1], 24, "Play folder");
        ui_pk_cm_act[1] = UI_PK_A_PLAY;
        snprintf(ui_pk_cm_lab[2], 24, "Add folder to queue");
        ui_pk_cm_act[2] = UI_PK_A_ADD;
        ui_pk_cm_n = 3;
    } else {
        snprintf(ui_pk_cm_lab[0], 24, "Play now");
        ui_pk_cm_act[0] = UI_PK_A_PLAY;
        snprintf(ui_pk_cm_lab[1], 24, "Add to queue");
        ui_pk_cm_act[1] = UI_PK_A_ADD;
        ui_pk_cm_n = 2;
    }
    ui_pk_cur = row;
    ui_pk_touched = 1;
    ui_pk_cm_open = 1;
}

static void ui_pk_cm_do(VideoState *is, int act)
{
    char path[PATH_MAX + 300];
    int e = ui_pk_cm_e;

    ui_pk_cm_open = 0;
    if (e < 0 || e >= ui_pk_n)
        return;
    ui_pk_path_of(e, path, sizeof(path));
    if (act == UI_PK_A_ENTER) {
        ui_pk_go(path);
    } else if (act == UI_PK_A_PLAY) {
        ui_pk_send(is, 'o', path);
        ui_pk_close(is);
    } else {
        ui_pk_send(is, 'a', path);              /* the picker stays open: more can be added */
        snprintf(ui_pk_note, sizeof(ui_pk_note), "Added: %.120s", ui_pk_e[e].name);
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
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 46);
    SDL_RenderDrawRect(renderer, &r);           /* a fine edge, so the menu stands out from the panel under it */
    for (i = 0; i < ui_pk_cm_n; i++) {
        SDL_Rect row = { r.x + 6, r.y + 6 + i * 36, r.w - 12, 34 };

        if (i == ui_pk_cm_hot) {
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 34);
            ui_pill(&row);
        }
        ui_label(row.x + 14, row.y + row.h / 2, ui_pk_cm_lab[i], 16, 245, 245, 245, i == ui_pk_cm_hot ? 255 : 215);
    }
}

static void ui_pk_draw(void)
{''')
patch("a note replaces the hint", r'''        const char *h = "Type to filter";''', r'''        const char *h = av_gettime_relative() < ui_pk_note_until ? ui_pk_note : "Type to filter";''')
patch("the row menu is drawn", r'''    } else {
        ui_pk_button(&L.ok, okname, ui_pk_hbtn == 1, 1);
    }
}''', r'''    } else {
        ui_pk_button(&L.ok, okname, ui_pk_hbtn == 1, 1);
    }
    ui_pk_cm_draw();
}''')
patch("the row menu owns the mouse", r'''    ui_wake();
    ui_pk_hrow = ui_pk_hplace = ui_pk_hbtn = -1;''', r'''    ui_wake();
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
    ui_pk_hrow = ui_pk_hplace = ui_pk_hbtn = -1;''')
patch("right click opens the row menu", r'''            if (ev->button.button == SDL_BUTTON_RIGHT && ui_pk_in(&L.p, x, y))
                ui_pk_up();                     /* a right click inside goes up one folder */''', r'''            if (ev->button.button == SDL_BUTTON_RIGHT && ui_pk_hrow >= 0)
                ui_pk_cm_start(ui_pk_hrow, x, y);       /* v45: a right click on a row opens its menu (it used to go up a folder) */''')
patch("Esc closes the row menu first", r'''        if (k == SDLK_ESCAPE) {
            if (ui_pk_filter[0]) {''', r'''        if (ui_pk_cm_open) {
            if (k == SDLK_ESCAPE)
                ui_pk_cm_open = 0;
            return 1;                           /* v45: the row menu uses the keys while it is open */
        }
        if (k == SDLK_ESCAPE) {
            if (ui_pk_filter[0]) {''')
patch("the row menu is closed with the picker", r'''static void ui_pk_close(VideoState *is)
{
    int i;

    ui_pk_open = 0;''', r'''static int ui_pk_cm_open;                        /* v45 (the row menu, below) */

static void ui_pk_close(VideoState *is)
{
    int i;

    ui_pk_open = 0;
    ui_pk_cm_open = 0;''')

if fails:
    print("\n%d edit(s) failed. Nothing written." % len(fails))
    sys.exit(1)
open(PATH, "w").write(src)
print("\nAll edits applied to " + PATH)
