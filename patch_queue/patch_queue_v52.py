#!/usr/bin/env python3
"""patch_queue_v52.py - file picker, round 4 (on top of v51).

  - Open Media is one choice in the menu: no separate File... / Folder... popup. The picker shows files and folders together.
  - A folder: "Open folder" (before the play button) goes into it, "Play folder" plays everything in it. A file: "Play file".
    Ctrl+click (or Space) ticks files, Ctrl+A ticks all, and the play button reads "Play selected files". What was ticked first plays
    first, even after sorting or searching. The play button has a play triangle in it.
  - Undo the v51 tree that opened itself down to the current folder.
  - Sort stays as you left it across restarts (written to settings.conf, with defaults there for a new settings file).
  - The picker uses sharp arrows instead of the soft chevrons; the rest of the player keeps its chevrons.

Run it from ~/build/ffmpeg-6.1.1:   python3 ~/build/patch_queue_v52.py [path/to/ffplay.c]
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
if "ui_pk_send_selected" in src:
    print("Already applied: v52 is in " + path)
    sys.exit(0)
if "ui_pk_thumb_flush" not in src:
    print("FAILED: apply patch_queue_v51.py first. Nothing written.")
    sys.exit(1)


def fail(msg):
    print("FAILED: " + msg)
    sys.exit(1)


def replace(s, old, new, what):
    n = s.count(old)
    if n != 1:
        fail("%s: expected 1 match, found %d" % (what, n))
    return s.replace(old, new)


def replace_n(s, old, new, nwant, what):
    n = s.count(old)
    if n != nwant:
        fail("%s: expected %d matches, found %d" % (what, nwant, n))
    return s.replace(old, new)


def patch(what, fn):
    """Apply one edit to the text in memory and say so; the file is only written at the end."""
    global src
    src = fn(src)
    print("ok: " + what)


# ----- the menu: Open Media opens the picker straight away -----

patch("Open menu row", lambda s: replace(s,
    r'''#define UI_ROW_OPEN  0          /* Open: File... and Folder... appear beside it */''',
    r'''#define UI_ROW_OPEN  0          /* v52: Open Media: files and folders are chosen in the picker */''', "Open menu row"))

patch("Open popup variables", lambda s: replace(s,
    r'''static int ui_open_open = 0;    /* 1 while the File / Folder choices are showing beside "Open" */
static int ui_open_hover = -1;  /* the choice under the mouse (0 = File, 1 = Folder) */
''', "", "Open popup variables"))

patch("Open popup functions", lambda s: replace(s,
    r'''/* ----- "Open": the File and Folder choices ----- */
static SDL_Rect ui_open_rect(int ww, int wh)
{
    SDL_Rect m = ui_menu_rect(ww, wh), p;
    int gap = ui_idle ? 14 : 22;

    p.w = FFMAX(ui_text_width("Folder...", 22), ui_text_width("File...", 22)) + 64 + UI_MENU_ICW;
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
    SDL_Rect p = ui_open_rect(ww, wh);
    int i, row_y;

    ui_glass(&p, 20);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    for (i = 0; i < 2; i++) {
        row_y = p.y + 8 + i * UI_MENU_ROW;
        ui_icon(i ? UI_IC_FOLDER : UI_IC_FILE, p.x + 28, row_y + UI_MENU_ROW / 2, 20, 240, 240, 240,
                i == ui_open_hover ? 255 : 190);
        ui_label(p.x + 28 + UI_MENU_ICW, row_y + UI_MENU_ROW / 2, i ? "Folder..." : "File...", 22, 240, 240, 240,
                 i == ui_open_hover ? 255 : 205);
        if (i == ui_open_hover) {
            SDL_Rect dot = { p.x + 11, row_y + UI_MENU_ROW / 2 - 3, 6, 6 };

            SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                                   av_clip(cfg_bar_b + 40, 0, 255), 235);
            ui_pill(&dot);
        }
    }
}

''', r'''/* v52: there is no File / Folder popup any more: "Open Media" goes straight to the picker. */

''', "Open popup functions"))

patch("menu label", lambda s: replace(s,
    r'''static const char *ui_menu_label[UI_MENU_ITEMS] = { "Open", "Queue", "Media Info",
                                                    "Preferences...", "Quit" };''',
    r'''static const char *ui_menu_label[UI_MENU_ITEMS] = { "Open Media", "Queue", "Media Info",
                                                    "Preferences...", "Quit" };''', "menu label"))

patch("menu lit row", lambda s: replace(s,
    r'''        lit = i == ui_menu_hover || (i == UI_ROW_OPEN && ui_open_open) ||''',
    r'''        lit = i == ui_menu_hover ||''', "menu lit row"))

patch("menu chevron", lambda s: replace(s,
    r'''        if (i == UI_ROW_OPEN || i == UI_ROW_QUEUE || i == UI_ROW_INFO)''',
    r'''        if (i == UI_ROW_QUEUE || i == UI_ROW_INFO)''', "menu chevron"))

patch("menu panel draw", lambda s: replace(s,
    r'''    if (ui_open_open)
        ui_open_draw(ww, wh);
    else if (ui_q_open)''',
    r'''    if (ui_q_open)''', "menu panel draw"))

patch("menu action", lambda s: replace(s,
    r'''    if (item == UI_ROW_OPEN) {          /* Open: the choices appear beside it */
        ui_open_open = 1;
        ui_q_open = 0;
        ui_info_open = 0;
        return;
    }''',
    r'''    if (item == UI_ROW_OPEN) {          /* v52: Open Media: one picker for files and folders */
        ui_menu_open = 0;
        ui_menu_hover = -1;
        ui_q_open = 0;
        ui_info_open = 0;
        ui_pick_start(0);
        return;
    }''', "menu action"))

patch("Open popup mouse", lambda s: replace(s,
    r'''    if (ui_open_open) {             /* the File / Folder choices */
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
''', "", "Open popup mouse"))

patch("Open popup hover", lambda s: replace(s,
    r'''        if (row == UI_ROW_OPEN) {
            ui_open_open = 1;       /* hovering "Open" shows File... and Folder... */
            ui_q_open = 0;
            ui_info_open = 0;
        } else if (row == UI_ROW_QUEUE) {''',
    r'''        if (row == UI_ROW_OPEN) {
            ui_q_open = 0;
            ui_info_open = 0;
        } else if (row == UI_ROW_QUEUE) {''', "Open popup hover"))

patch("Open popup keep", lambda s: replace(s,
    r'''            if (ui_open_open) {
                op = ui_open_rect(ww, wh);
                if (!ui_q_keep(&r, &op, x, y, UI_ROW_OPEN))
                    ui_open_open = 0;
            }
''', "", "Open popup keep"))

patch("Open popup right click", lambda s: replace(s,
    r'''        ui_menu_hover = -1;
        ui_q_open = 0;
        ui_info_open = 0;
        ui_open_open = 0;
        ui_q_drag = -1;''',
    r'''        ui_menu_hover = -1;
        ui_q_open = 0;
        ui_info_open = 0;
        ui_q_drag = -1;''', "Open popup right click"))

patch("Open popup click outside", lambda s: replace(s,
    r'''        } else if (ui_menu_open) {
            ui_menu_open = 0;       /* click outside closes the popup */
            ui_q_open = 0;
            ui_info_open = 0;
            ui_open_open = 0;
        } else {''',
    r'''        } else if (ui_menu_open) {
            ui_menu_open = 0;       /* click outside closes the popup */
            ui_q_open = 0;
            ui_info_open = 0;
        } else {''', "Open popup click outside"))

patch("Open popup reset 1", lambda s: replace(s,
    r'''    if (!ui_menu_open || ui_idle || ui_prefs_open || ui_q_drag >= 0 || ui_q_open || ui_info_open ||
        ui_open_open || ui_ctx_open)''',
    r'''    if (!ui_menu_open || ui_idle || ui_prefs_open || ui_q_drag >= 0 || ui_q_open || ui_info_open || ui_ctx_open)''',
    "Open popup reset 1"))
patch("Open popup small window", lambda s: replace(s,
    r'''    if (ui_too_small() && (ui_menu_open || ui_prefs_open || ui_q_open || ui_info_open || ui_open_open || ui_ctx_open || ui_tvc_open ||
                           ui_vflow || ui_tv_audio)) {
        ui_menu_open = ui_prefs_open = ui_q_open = ui_info_open = ui_open_open = ui_ctx_open = ui_tvc_open = 0;       /* v41 */''',
    r'''    if (ui_too_small() && (ui_menu_open || ui_prefs_open || ui_q_open || ui_info_open || ui_ctx_open || ui_tvc_open ||
                           ui_vflow || ui_tv_audio)) {
        ui_menu_open = ui_prefs_open = ui_q_open = ui_info_open = ui_ctx_open = ui_tvc_open = 0;       /* v41 */''',
    "Open popup small window"))
patch("Open popup escape 1", lambda s: replace(s,
    r'''                    if (ui_prefs_open || ui_q_open || ui_info_open || ui_open_open || ui_ctx_open) {
                        ui_prefs_open = 0;
                        ui_q_open = 0;
                        ui_info_open = 0;
                        ui_open_open = 0;
                        ui_ctx_open = 0;''',
    r'''                    if (ui_prefs_open || ui_q_open || ui_info_open || ui_ctx_open) {
                        ui_prefs_open = 0;
                        ui_q_open = 0;
                        ui_info_open = 0;
                        ui_ctx_open = 0;''', "Open popup escape 1"))
patch("Open popup escape 2", lambda s: replace(s,
    r'''                if (ui_menu_open || ui_prefs_open || ui_q_open || ui_info_open || ui_open_open || ui_ctx_open) {
                    ui_menu_open = 0;
                    ui_prefs_open = 0;
                    ui_q_open = 0;
                    ui_info_open = 0;
                    ui_open_open = 0;
                    ui_ctx_open = 0;''',
    r'''                if (ui_menu_open || ui_prefs_open || ui_q_open || ui_info_open || ui_ctx_open) {
                    ui_menu_open = 0;
                    ui_prefs_open = 0;
                    ui_q_open = 0;
                    ui_info_open = 0;
                    ui_ctx_open = 0;''', "Open popup escape 2"))
patch("Open popup guards", lambda s: replace_n(s, "ui_info_open || ui_open_open || ui_ctx_open)", "ui_info_open || ui_ctx_open)", 2, "Open popup guards"))
patch("Open popup idle reset", lambda s: replace(s,
    r'''    ui_info_open = 0;
    ui_open_open = 0;
    ui_ctx_open = 0;
    ui_q_drag = -1;''',
    r'''    ui_info_open = 0;
    ui_ctx_open = 0;
    ui_q_drag = -1;''', "Open popup idle reset"))

patch("zenity dialog title", lambda s: replace(s,
    r'''    if (item == 0) {            /* Open File... */
        cmd = "echo $$; exec zenity --file-selection --title='Open File' 2>/dev/null";
        what = 'o';
    } else if (item == 1) {     /* Open Folder... */
        cmd = "echo $$; exec zenity --file-selection --directory --title='Open Folder' 2>/dev/null";
        what = 'o';
    } else {                    /* Add to Queue... (one or more files) */
        cmd = "echo $$; exec zenity --file-selection --multiple --separator='\\n' --title='Add to Queue' 2>/dev/null";
        what = 'a';
    }''',
    r'''    if (item == 2) {            /* Add to Queue... (one or more files) */
        cmd = "echo $$; exec zenity --file-selection --multiple --separator='\\n' --title='Add to Queue' 2>/dev/null";
        what = 'a';
    } else {                    /* Open Media: one dialog for files and folders */
        cmd = "echo $$; exec zenity --file-selection --title='Open Media' 2>/dev/null";
        what = 'o';
    }''', "zenity dialog title"))

# ----- the icons: straight arrows in the picker, a play triangle on the button -----

patch("icon enum", lambda s: replace(s,
    r'''       UI_IC_GRID, UI_IC_LIST, UI_IC_SEARCH, UI_IC_ARR_L, UI_IC_ARR_R, UI_IC_ARR_U, UI_IC_EJECT,
       UI_IC_N };''',
    r'''       UI_IC_GRID, UI_IC_LIST, UI_IC_SEARCH, UI_IC_ARR_L, UI_IC_ARR_R, UI_IC_ARR_U, UI_IC_EJECT,
       UI_IC_ARW_L, UI_IC_ARW_R, UI_IC_ARW_U, UI_IC_ARW_D, UI_IC_PLAY,
       UI_IC_N };''', "icon enum"))

patch("icon shapes", lambda s: replace(s,
    r'''    case UI_IC_SEARCH:
        ic_arc(10.5f, 10.5f, 6.5f, 0, 360);''',
    r'''    case UI_IC_ARW_L:                           /* v52: sharp arrows, for the picker only */
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
    case UI_IC_PLAY: {                              /* a solid triangle for the play buttons */
        int k;

        for (k = 0; k < 12; k++) {
            float x = 8.0f + k, y0 = 5.0f + k * 7.0f / 11.0f, y1 = 19.0f - k * 7.0f / 11.0f;

            ic_seg(x, y0, x, y1);
        }
        break;
    }
    case UI_IC_SEARCH:
        ic_arc(10.5f, 10.5f, 6.5f, 0, 360);''', "icon shapes"))

# ----- settings: a new settings file starts with the picker choices, so sort has a place to live -----

patch("settings defaults", lambda s: replace(s,
    r'''    "# Font file for the text (leave empty to use the system font)\n"
    "font =\n";''',
    r'''    "# File picker: 0 = name, 1 = modified, 2 = size; picker_desc = 1 for the other way round\n"
    "picker_grid = 0\n"
    "picker_sort = 0\n"
    "picker_desc = 0\n"
    "\n"
    "# Font file for the text (leave empty to use the system font)\n"
    "font =\n";''', "settings defaults"))

patch("settings variables", lambda s: replace(s,
    r'''static int     cfg_pk_grid = 0, cfg_pk_sort = 0, cfg_pk_desc = 0, cfg_pk_thumbs = 1;      /* v50: the picker's view (list or grid) and its order */''',
    r'''static int     cfg_pk_grid = 0, cfg_pk_sort = 0, cfg_pk_desc = 0, cfg_pk_thumbs = 1;      /* picker view and order; all of them are saved between runs */''', "settings variables"))

# ----- the picker -----

patch("picker description", lambda s: replace(s,
    r'''   v44: our own file picker, for Open File, Open Folder and Add to Queue. It is drawn like the Preferences panel (frosted glass over
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
            Esc clears the search, then closes the search box, then closes the picker.''',
    r'''   v44: our own file picker. It is drawn like the Preferences panel (frosted glass over the blurred player) and sends what is chosen
   to the inbox, like the system dialog did. It needs no other program.
   v49: reworked. One top bar (back, forward, up, "Open Media", the path, Sort, list or grid, search, close), a folder tree on the left
   with drop downs, drives that are not mounted yet (click to mount), search just by typing (in this folder, below it, above it,
   elsewhere), a dynamic "Modified" column, item counts and sizes at the bottom, and buttons that follow what is selected.
   v52: Open Media is the one menu choice: files and folders are both shown. A folder has "Open folder" (go in) and "Play folder";
        a file has "Play file". Ctrl+click or Space ticks files, Ctrl+A ticks all, and "Play selected files" plays them in the order
        they were ticked. The tree no longer opens itself; the arrows in the picker are sharp. Sort stays across restarts.
     Mouse: a click selects a row, a double click opens it (a folder is entered, a file is played); Ctrl+click ticks a file; in Add
            to Queue a click on a file ticks it; the tree, the path and the arrows move around; the wheel scrolls; a click outside closes it.
            The back and forward buttons of a mouse go back and forward.
     Keys:  type to search, Up/Down/PageUp/PageDown/Home/End (and Left/Right in the grid), Enter (opens the row, or plays/adds what is ticked),
            Right enters a folder, Left or Backspace (with nothing typed) goes up, Alt+Left/Right back and forward, Alt+Up up, Space ticks,
            Ctrl+A ticks all (in the order chosen), Ctrl+1 list, Ctrl+2 grid, Ctrl+F search box, Ctrl+L type a path (Tab finishes a folder name), Ctrl+T thumbnails on or off, Tab shows all files, Ctrl+H shows hidden ones, F5 reads again,
            Esc clears the search, then closes the search box, then closes the picker.''', "picker description"))

patch("entry order field", lambda s: replace(s,
    r'''    int dir, sel, count, sect;                  /* count: items in a folder (-1 = not counted yet); sect: 0 here, 1 below, 2 above, 3 elsewhere */''',
    r'''    int dir, sel, ord, count, sect;             /* ord: order in which a file was ticked (v52); count: items in a folder (-1 = not counted yet); sect: 0 here, 1 below, 2 above, 3 elsewhere */''', "entry order field"))

patch("picker mode", lambda s: replace(s,
    r'''static int ui_pk_mode = 0;                      /* 0 = Open File, 1 = Open Folder, 2 = Add to Queue */''',
    r'''static int ui_pk_mode = 0;                      /* v52: 0 = Open Media (files and folders), 2 = Add to Queue */
static int ui_pk_sel_seq = 0;                   /* counts the ticks, so selected files play in the order they were ticked */''', "picker mode"))

patch("tree show state", lambda s: replace(s,
    r'''static int ui_pk_tree_show = -1;                /* v51: the tree node to scroll into view at the next drawing */                    /* 1 = scroll the cursor into view at the next drawing (the rows have no places yet) */
''', "", "tree show state"))

patch("tree reveal forward", lambda s: replace(s,
    r'''static void ui_pk_search_start(void);
static void ui_pk_tree_reveal(void);
''',
    r'''static void ui_pk_search_start(void);
''', "tree reveal forward"))

patch("tree reveal call", lambda s: replace(s,
    r'''    ui_pk_rebuild();
    ui_pk_tree_reveal();                        /* v51: the tree opens down to this folder */
    return 1;''',
    r'''    ui_pk_rebuild();
    return 1;''', "tree reveal call"))

patch("tree reveal function", lambda s: replace(s,
    r'''/* The tree opens down to the open folder and scrolls to it */
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

''', "", "tree reveal function"))

patch("tree scroll block", lambda s: replace(s,
    r'''        if (ui_pk_tree_show >= 0) {             /* v51: scroll to a node the tree opened down to */
            double ty = ui_pk_tree_show * (double)UI_PK_TROW;

            if (ty < ui_pk_ssc)
                ui_pk_ssc = ty;
            else if (ty + UI_PK_TROW + 12 > ui_pk_ssc + L.side.h)
                ui_pk_ssc = ty + UI_PK_TROW + 12 - L.side.h;
            ui_pk_tree_show = -1;
        }
''', "", "tree scroll block"))

patch("folder-only filters", lambda s: replace_n(s,
    "(ui_pk_mode == 1 || (!ui_pk_all && !ui_pk_has_ext(de->d_name)))",
    "!ui_pk_all && !ui_pk_has_ext(de->d_name)", 3, "folder-only filters"))

patch("picker layout", lambda s: replace(s,
    r'''    L->ok.w = 124;
    L->ok.h = 38;''',
    r'''    L->ok.w = ui_pk_mode == 0 ? (L->p.w >= 740 ? 196 : 132) : 124;   /* v52: "Play selected files" fits */
    L->ok.h = 38;''', "picker layout (play width)"))

patch("picker extra width", lambda s: replace(s,
    r'''    L->extra.w = ui_pk_mode == 2 ? (L->p.w >= 740 ? 150 : 96) : 104;''',
    r'''    L->extra.w = ui_pk_mode == 0 ? (L->p.w >= 740 ? 132 : 92) :
                 ui_pk_mode == 2 ? (L->p.w >= 740 ? 150 : 96) : 104;''', "picker extra width"))

patch("picker hidden switch", lambda s: replace(s,
    r'''    L->hid.x = ui_pk_mode != 1 ? L->all.x + L->all.w + 14 : L->all.x;''',
    r'''    L->hid.x = L->all.x + L->all.w + 14;''', "picker hidden switch"))

patch("selected files in order", lambda s: replace(s,
    r'''static void ui_pk_enter(const UiPkEnt *e)       /* go into a folder */''',
    r'''static int ui_pk_ord_cmp(const void *a, const void *b)
{
    const UiPkEnt *x = *(UiPkEnt * const *)a, *y = *(UiPkEnt * const *)b;

    return x->ord - y->ord;
}

/* Play or add all ticked files, in the order they were ticked (v52) */
static void ui_pk_send_selected(VideoState *is, char what)
{
    UiPkEnt **v = NULL;
    int n = 0, i, cap = ui_pk_n + ui_pk_nx;
    char path[PATH_MAX + 300];

    if (!cap)
        return;
    if (!(v = calloc(cap, sizeof(*v))))
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
        ui_pk_send(is, i ? 'a' : (what == 'o' ? 'o' : 'a'), path);
    }
    free(v);
    if (n)
        ui_pk_close(is);
}

static void ui_pk_enter(const UiPkEnt *e)       /* go into a folder */''', "selected files in order"))

patch("picker main button", lambda s: replace(s,
    r'''/* The main button (right end of the foot):
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
}''',
    r'''/* The main button (right end of the foot), v52:
   Open Media: "Play file" for a file, "Play folder" for a folder, "Play selected files" for a ticked set.
   Add to Queue: "Add", in the order the files were ticked. */
static void ui_pk_do_ok(VideoState *is)
{
    char path[PATH_MAX + 300];
    UiPkEnt *e = ui_pk_cur_ent();

    if (ui_pk_ticked(NULL) > 0) {
        ui_pk_send_selected(is, ui_pk_mode == 2 ? 'a' : 'o');
        return;
    }
    if (ui_pk_mode == 2) {
        if (e && !e->dir) {
            ui_pk_path_of(e, path, sizeof(path));
            ui_pk_send(is, 'a', path);
            ui_pk_close(is);
        }
        return;
    }
    if (!e)
        return;
    ui_pk_path_of(e, path, sizeof(path));
    ui_pk_send(is, 'o', path);                  /* a folder plays everything in it */
    ui_pk_close(is);
}

/* The button before the play button: "Open folder" (go into it), or "Add this folder" in Add to Queue */
static void ui_pk_do_extra(VideoState *is)
{
    char path[PATH_MAX + 300];
    UiPkEnt *e = ui_pk_cur_ent();

    if (ui_pk_mode == 2) {
        if (e && e->dir && ui_pk_touched)
            ui_pk_path_of(e, path, sizeof(path));
        else
            snprintf(path, sizeof(path), "%s", ui_pk_dir);
        ui_pk_send(is, 'a', path);
        ui_pk_close(is);
    } else if (e && e->dir) {
        ui_pk_enter(e);
    }
}''', "picker main button"))

patch("tick order", lambda s: replace(s,
    r'''static void ui_pk_tick_row(int row)
{
    UiPkEnt *e = ui_pk_ent(row);

    if (e && ui_pk_mode == 2 && !e->dir)
        e->sel ^= 1;
}''',
    r'''static void ui_pk_tick_row(int row)
{
    UiPkEnt *e = ui_pk_ent(row);

    if (!e || e->dir)
        return;
    e->sel = !e->sel;
    if (e->sel) {
        if (!e->ord)
            e->ord = ++ui_pk_sel_seq;           /* the order chosen, kept across sorts and searches */
    } else {
        e->ord = 0;
    }
}''', "tick order"))

patch("button play icon", lambda s: replace(s,
    r'''static void ui_pk_button(const SDL_Rect *r, const char *label, int hot, int primary, int enabled)
{
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    if (primary)
        SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r, 0, 255), av_clip(cfg_bar_g, 0, 255), av_clip(cfg_bar_b, 0, 255),
                               !enabled ? 110 : hot ? 255 : 215);
    else
        SDL_SetRenderDrawColor(renderer, 255, 255, 255, !enabled ? 14 : hot ? 60 : 30);
    ui_pill(r);
    ui_label_c(r->x + r->w / 2, r->y + r->h / 2, label, 16, 245, 245, 245, enabled ? 255 : 120);
}''',
    r'''static void ui_pk_button(const SDL_Rect *r, const char *label, int hot, int primary, int enabled)
{
    int play = primary && strstr(label, "Play") == label;   /* v52: a play triangle like the one on a video's button */

    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    if (primary)
        SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r, 0, 255), av_clip(cfg_bar_g, 0, 255), av_clip(cfg_bar_b, 0, 255),
                               !enabled ? 110 : hot ? 255 : 215);
    else
        SDL_SetRenderDrawColor(renderer, 255, 255, 255, !enabled ? 14 : hot ? 60 : 30);
    ui_pill(r);
    ui_label_c(r->x + r->w / 2 + (play && r->w >= 150 ? 11 : 0), r->y + r->h / 2, label, 16, 245, 245, 245, enabled ? 255 : 120);
    if (play && r->w >= 150)
        ui_icon(UI_IC_PLAY, r->x + 11, r->y + r->h / 2, 18, 245, 245, 245, enabled ? 255 : 120);
}''', "button play icon"))

patch("picker top arrows", lambda s: replace(s,
    r'''    ui_pk_ibtn(&L.back, UI_IC_ARR_L, ui_pk_hbtn == 20, 0, ui_pk_hi > 0 ? 255 : 90);
    ui_pk_ibtn(&L.fwd, UI_IC_ARR_R, ui_pk_hbtn == 21, 0, ui_pk_hi >= 0 && ui_pk_hi < ui_pk_hn - 1 ? 255 : 90);
    ui_pk_ibtn(&L.upb, UI_IC_ARR_U, ui_pk_hbtn == 22, 0, strcmp(ui_pk_dir, "/") ? 255 : 90);''',
    r'''    ui_pk_ibtn(&L.back, UI_IC_ARW_L, ui_pk_hbtn == 20, 0, ui_pk_hi > 0 ? 255 : 90);
    ui_pk_ibtn(&L.fwd, UI_IC_ARW_R, ui_pk_hbtn == 21, 0, ui_pk_hi >= 0 && ui_pk_hi < ui_pk_hn - 1 ? 255 : 90);
    ui_pk_ibtn(&L.upb, UI_IC_ARW_U, ui_pk_hbtn == 22, 0, strcmp(ui_pk_dir, "/") ? 255 : 90);''', "picker top arrows"))

patch("breadcrumb arrows", lambda s: replace(s,
    r'''                ui_icon(UI_IC_CHEV_R, x + 7, cy, 14, 150, 150, 150, 255);''',
    r'''                ui_icon(UI_IC_ARW_R, x + 7, cy, 14, 150, 150, 150, 255);''', "breadcrumb arrows"))

patch("sort arrows", lambda s: replace_n(s,
    "            ui_icon(ui_pk_desc ? UI_IC_CHEV_D : UI_IC_CHEV_U, row.x + row.w - 28, row.y + row.h / 2, 16, av_clip(cfg_bar_r + 70, 0, 255),\n",
    "            ui_icon(ui_pk_desc ? UI_IC_ARW_D : UI_IC_ARW_U, row.x + row.w - 28, row.y + row.h / 2, 16, av_clip(cfg_bar_r + 70, 0, 255),\n",
    1, "sort menu arrow"))

patch("sort button arrow", lambda s: replace(s,
    r'''        ui_icon(ui_pk_desc ? UI_IC_CHEV_D : UI_IC_CHEV_U, L.sortb.x + L.sortb.w - 28, L.sortb.y + L.sortb.h / 2, 14, 190, 190, 190, 255);''',
    r'''        ui_icon(ui_pk_desc ? UI_IC_ARW_D : UI_IC_ARW_U, L.sortb.x + L.sortb.w - 28, L.sortb.y + L.sortb.h / 2, 14, 190, 190, 190, 255);''', "sort button arrow"))

patch("tree arrows", lambda s: replace(s,
    r'''            if (mounted && nd->kids != 0)
                ui_icon(nd->open ? UI_IC_CHEV_D : UI_IC_CHEV_R, ix, ry + UI_PK_TROW / 2, 14, 200, 200, 200, 255);''',
    r'''            if (mounted && nd->kids != 0)
                ui_icon(nd->open ? UI_IC_ARW_D : UI_IC_ARW_R, ix, ry + UI_PK_TROW / 2, 14, 200, 200, 200, 255);''', "tree arrows"))

patch("selecting flag", lambda s: replace(s,
    r'''    cbud = av_gettime_relative() + 3000;
    ui_pk_thumb_begin();''',
    r'''    cbud = av_gettime_relative() + 3000;
    selecting = ui_pk_mode == 2 || ui_pk_ticked(NULL) > 0;    /* v52: a tick box appears once files are ticked */
    ui_pk_thumb_begin();''', "selecting flag"))

patch("selecting declaration", lambda s: replace(s,
    r'''    int ww, wh, i, mx = 0, my = 0, x, cy, cols_size, cols_mod, cols_loc, ar, ag, ab;''',
    r'''    int ww, wh, i, mx = 0, my = 0, x, cy, cols_size, cols_mod, cols_loc, ar, ag, ab, selecting;''', "selecting declaration"))

patch("grid tick box", lambda s: replace(s,
    r'''            if (ui_pk_mode == 2 && !e->dir) {
                SDL_Rect b = { t.x + 8, t.y + 8, 18, 18 };''',
    r'''            if (selecting && !e->dir) {
                SDL_Rect b = { t.x + 8, t.y + 8, 18, 18 };''', "grid tick box"))

patch("list tick box", lambda s: replace(s,
    r'''        if (ui_pk_mode == 2 && !e->dir) {       /* a box to tick */''',
    r'''        if (selecting && !e->dir) {             /* a box to tick */''', "list tick box"))

patch("list tick indent", lambda s: replace(s,
    r'''        if (ui_pk_mode == 2)
            tx += 30;''',
    r'''        if (selecting)
            tx += 30;''', "list tick indent"))

patch("empty folder message", lambda s: replace(s,
    r'''        const char *m = ui_pk_filter[0] ? (ui_pk_scan_on ? "Looking ..." : "Nothing matches") : ui_pk_mode == 1 ? "No folders here" :
                        ui_pk_all ? "This folder is empty" : "No music or videos here";''',
    r'''        const char *m = ui_pk_filter[0] ? (ui_pk_scan_on ? "Looking ..." : "Nothing matches") :
                        ui_pk_all ? "This folder is empty" : "No music or videos here";''', "empty folder message"))

patch("all files switch", lambda s: replace(s,
    r'''            if (ui_pk_mode != 1) {
                snprintf(tmp, sizeof(tmp), "All files: %s", ui_pk_all ? "On" : "Off");
                ui_label(L.all.x, fy, tmp, 15, ui_pk_hbtn == 5 ? 255 : 190, ui_pk_hbtn == 5 ? 255 : 190, ui_pk_hbtn == 5 ? 255 : 190, 255);
            }''',
    r'''            snprintf(tmp, sizeof(tmp), "All files: %s", ui_pk_all ? "On" : "Off");
            ui_label(L.all.x, fy, tmp, 15, ui_pk_hbtn == 5 ? 255 : 190, ui_pk_hbtn == 5 ? 255 : 190, ui_pk_hbtn == 5 ? 255 : 190, 255);''', "all files switch"))

patch("foot buttons", lambda s: replace(s,
    r'''        UiPkEnt *ce = ui_pk_cur_ent();
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
        }''',
    r'''        UiPkEnt *ce = ui_pk_cur_ent();
        int nt = ui_pk_ticked(NULL);
        int wide = L.p.w >= 740;

        if (ui_pk_mode == 2) {
            snprintf(tmp, sizeof(tmp), "%s", wide ? "Add this folder" : "Folder");
            ui_pk_button(&L.extra, tmp, ui_pk_hbtn == 3, 0, 1);
            if (nt > 0)
                snprintf(tmp, sizeof(tmp), "Add %d", nt);
            else
                snprintf(tmp, sizeof(tmp), "Add");
            ui_pk_button(&L.ok, tmp, ui_pk_hbtn == 1, 1, nt > 0 || (ce && !ce->dir));
        } else if (ce && ce->dir && !nt) {       /* v52: a folder has "Open folder" and "Play folder" */
            ui_pk_button(&L.extra, wide ? "Open folder" : "Open", ui_pk_hbtn == 3, 0, 1);
            ui_pk_button(&L.ok, wide ? "Play folder" : "Play", ui_pk_hbtn == 1, 1, 1);
        } else {
            if (nt > 1)
                snprintf(tmp, sizeof(tmp), "%s", wide ? "Play selected files" : "Play selected");
            else if (ce && !ce->dir)
                snprintf(tmp, sizeof(tmp), "%s", wide ? "Play file" : "Play");
            else
                snprintf(tmp, sizeof(tmp), "%s", wide ? "Play file" : "Play");
            ui_pk_button(&L.ok, tmp, ui_pk_hbtn == 1, 1, nt > 0 || (ce && !ce->dir));
        }''', "foot buttons"))

patch("extra button hover", lambda s: replace(s,
    r'''    else if (ui_pk_mode != 0 && ui_pk_in(&L.extra, x, y))''',
    r'''    else if (ui_pk_in(&L.extra, x, y))''', "extra button hover"))

patch("all files hover", lambda s: replace(s,
    r'''    else if (L.tog && ui_pk_mode != 1 && ui_pk_in(&L.all, x, y))''',
    r'''    else if (L.tog && ui_pk_in(&L.all, x, y))''', "all files hover"))

patch("mouse tick files", lambda s: replace(s,
    r'''            } else if (ui_pk_mode == 2 && e && !e->dir) {
                ui_pk_tick_row(ui_pk_hrow);     /* a click ticks the file */
            } else if (ui_pk_mode == 2 && e) {  /* a folder is entered with one click: there is nothing to tick on it */''',
    r'''            } else if ((ui_pk_mode == 2 || (ui_pk_mode == 0 && (SDL_GetModState() & KMOD_CTRL))) && e && !e->dir) {
                ui_pk_tick_row(ui_pk_hrow);     /* Ctrl+click ticks a file (a plain click in Add to Queue ticks it) */
            } else if (ui_pk_mode == 2 && e) {  /* a folder is entered with one click: there is nothing to tick on it */''', "mouse tick files"))

patch("enter plays selection", lambda s: replace(s,
    r'''        } else if (k == SDLK_RETURN || k == SDLK_KP_ENTER) {
            if ((ui_pk_mode == 2 && ui_pk_ticked(NULL) > 0) || (ui_pk_mode == 1 && ctrl))
                ui_pk_do_ok(is);
            else
                ui_pk_activate(is);''',
    r'''        } else if (k == SDLK_RETURN || k == SDLK_KP_ENTER) {
            if (ui_pk_ticked(NULL) > 0)
                ui_pk_do_ok(is);
            else
                ui_pk_activate(is);''', "enter plays selection"))

patch("space ticks", lambda s: replace(s,
    r'''        } else if (k == SDLK_SPACE && !ui_pk_filter[0]) {
            if (ui_pk_mode == 2) {''',
    r'''        } else if (k == SDLK_SPACE && !ui_pk_filter[0]) {
            {''', "space ticks"))

patch("ctrl a selects", lambda s: replace(s,
    r'''        } else if (ctrl && k == SDLK_a && ui_pk_mode == 2) {
            int i;

            for (i = 0; i < ui_pk_nrw; i++) {
                UiPkEnt *e = ui_pk_ent(i);

                if (e && !e->dir)
                    e->sel = 1;
            }''',
    r'''        } else if (ctrl && k == SDLK_a) {        /* v52: Ctrl+A ticks every file, in the order of the list */
            int i;

            for (i = 0; i < ui_pk_nrw; i++) {
                UiPkEnt *e = ui_pk_ent(i);

                if (e && !e->dir && !e->sel) {
                    e->sel = 1;
                    e->ord = ++ui_pk_sel_seq;
                }
            }''', "ctrl a selects"))

patch("all files key", lambda s: replace(s,
    r'''        } else if (k == SDLK_TAB && ui_pk_mode != 1) {''',
    r'''        } else if (k == SDLK_TAB) {''', "all files key"))

patch("picker start mode", lambda s: replace(s,
    r'''    ui_pk_mode = item == 1 ? 1 : item == 2 ? 2 : 0;
    ui_pk_all = 0;''',
    r'''    ui_pk_mode = item == 2 ? 2 : 0;              /* v52: Open Media handles files and folders */
    ui_pk_sel_seq = 0;
    ui_pk_all = 0;''', "picker start mode"))

patch("picker start popup", lambda s: replace(s,
    r'''    ui_info_open = 0;
    ui_open_open = 0;
    ui_ctx_open = 0;''',
    r'''    ui_info_open = 0;
    ui_ctx_open = 0;''', "picker start popup"))

patch("Open popup remaining resets", lambda s: replace_n(s, "ui_open_open = 0;\n", "", 5, "Open popup remaining resets"))

open(path, "w", encoding="utf-8").write(src)
print("Done: patch_queue_v52 applied.")
