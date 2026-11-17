#!/usr/bin/env python3
# patch_queue_v30.py - run it inside ~/build/ffmpeg-6.1.1 (it edits fftools/ffplay.c)
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


def between(name, start, end, new):
    global src
    a = src.find(start)
    b = src.find(end, a + 1) if a >= 0 else -1
    if a < 0 or b < 0 or src.count(start) != 1:
        print("FAILED: %s matched %d times" % (name, src.count(start)))
        fails.append(name)
        return
    src = src[:a] + new + src[b:]
    print("ok: " + name)


if "ui_menu_rowh" in src:
    print("Already applied")
    sys.exit(0)

# ============================================================ Remember window: gone (the size of the window is still kept item to item)
patch("window settings", r'''static int     cfg_keep_window = 1;         /* 1 = remember the window's size and place, and keep its size between items */
static int     cfg_win_x = 0, cfg_win_y = 0, cfg_win_w = 0, cfg_win_h = 0;     /* where it was when the player closed */
''', r'''#define cfg_keep_window 1               /* the window keeps the size you gave it from one item to the next (nothing is kept between runs) */
''')
patch("read the window settings", r'''        else if (sscanf(line, " remember_window = %d", &n) == 1)
            cfg_keep_window = (n != 0);
        else if (sscanf(line, " window_rect = %d %d %d %d", &cfg_win_x, &cfg_win_y, &cfg_win_w, &cfg_win_h) == 4)
            ;
''', "")
patch("write the window settings", r'''    fprintf(f, "# 1 = remember the window's size and place between runs, and keep its size from one item to the next\nremember_window = %d\n\n",
            cfg_keep_window);
    if (cfg_win_w > 0)
        fprintf(f, "# Where the window was at the end of the last run: x y width height\nwindow_rect = %d %d %d %d\n\n",
                cfg_win_x, cfg_win_y, cfg_win_w, cfg_win_h);
''', "")
between("saving the window", r'''/* Save where the window is, for the next start */''', r'''static void do_exit(VideoState *is)''', "")
patch("no save on exit", r'''    ui_th_stop();
    ui_win_save();
''', r'''    ui_th_stop();
''')
between("no restore at start", r'''    static int restored = 0;
''', r'''    w = screen_width ? screen_width : default_width;''', "\n")
patch("preferences: eight rows", r'''#define UI_PREF_ROWS 9
#define UI_PREF_ROW 52          /* height of one row */
#define UI_PREF_HEAD 76         /* space for the title */
#define UI_PREF_FOOT 52         /* space for the hint at the bottom */''', r'''#define UI_PREF_ROWS 8
#define UI_PREF_ROW ui_pr_row   /* height of one row (smaller in a small window) */
#define UI_PREF_HEAD ui_pr_head /* space for the title */
#define UI_PREF_FOOT ui_pr_foot /* space for the hint at the bottom (none in a small window) */
static int ui_pr_row = 52, ui_pr_head = 76, ui_pr_foot = 52, ui_pr_px = 20, ui_pr_tpx = 28, ui_pr_mg = 32;''')
patch("row name gone", r'''"Mouse wheel", "Remember window"
};''', r'''"Mouse wheel"
};''')
patch("row value gone", r'''    case 8: snprintf(out, size, "%s", cfg_keep_window ? "On" : "Off"); break;
''', "")
patch("row choices gone", r'''row == 5 ? cfg_remember_volume : row == 8 ? cfg_keep_window : cfg_quit_when_done) ? 1 : 0;''',
      r'''row == 5 ? cfg_remember_volume : cfg_quit_when_done) ? 1 : 0;''')
patch("row choose gone", r'''    case 8: cfg_keep_window = idx != 0; break;
''', "")

# ============================================================ Preferences in a small window: smaller rows, nothing outside the window
between("panel size", r'''static SDL_Rect ui_prefs_rect(int ww, int wh)''', r'''static void ui_prefs_draw(void)''', r'''static SDL_Rect ui_prefs_rect(int ww, int wh)
{
    SDL_Rect p;
    int avail = wh - 16;

    if (avail >= 76 + UI_PREF_ROWS * 52 + 52) {         /* room enough: the full size */
        ui_pr_head = 76;
        ui_pr_row = 52;
        ui_pr_foot = 52;
        ui_pr_px = 20;
        ui_pr_tpx = 28;
    } else if (avail >= 40 + UI_PREF_ROWS * 34) {       /* a shorter window: smaller rows, no hint */
        ui_pr_head = 40;
        ui_pr_foot = 0;
        ui_pr_row = av_clip((avail - 40) / UI_PREF_ROWS, 34, 52);
        ui_pr_px = ui_pr_row >= 40 ? 20 : 17;
        ui_pr_tpx = 22;
    } else {                                            /* a very small window */
        ui_pr_head = 30;
        ui_pr_foot = 0;
        ui_pr_row = FFMAX((avail - 30) / UI_PREF_ROWS, 22);
        ui_pr_px = 14;
        ui_pr_tpx = 18;
    }
    ui_pr_mg = ww < 560 ? 14 : 32;
    p.w = FFMIN((int)(ui_prefs_w + 0.5), ww - 16);
    p.h = UI_PREF_HEAD + UI_PREF_ROWS * UI_PREF_ROW + UI_PREF_FOOT;
    p.x = (ww - p.w) / 2;
    p.y = FFMAX((wh - p.h) / 2, 4);
    return p;
}

''')
patch("grow limit", r'''    wt = FFMIN(wt, ww - 40);
    ui_prefs_w +=''', r'''    wt = FFMIN(wt, ww - 16);
    ui_prefs_w +=''')
patch("room beside the name", r'''    room = p->w - 64 - ui_text_width(ui_pref_name[row], 20) - 18;''',
      r'''    room = p->w - 2 * ui_pr_mg - ui_text_width(ui_pref_name[row], ui_pr_px) - 18;''')
patch("choices against the margin", r'''    x = p->x + p->w - 32 - total;               /* against the right margin */''',
      r'''    x = p->x + p->w - ui_pr_mg - total;         /* against the right margin */''')
patch("choice height", r'''        out[i].y = cy - 16;
        out[i].w = w[i];
        out[i].h = 32;''', r'''        out[i].y = cy - FFMIN(32, ui_pr_row - 6) / 2;
        out[i].w = w[i];
        out[i].h = FFMIN(32, ui_pr_row - 6);''')
patch("room needed", r'''    return 64 + ui_text_width(ui_pref_name[row], 20) + 18 + total;''',
      r'''    return 2 * ui_pr_mg + ui_text_width(ui_pref_name[row], ui_pr_px) + 18 + total;''')
patch("right margin", r'''    x_right = p.x + p.w - 32;''', r'''    x_right = p.x + p.w - ui_pr_mg;''')
patch("title", r'''    ui_label(p.x + 32, p.y + UI_PREF_HEAD / 2 + 4, "Preferences", 28, 245, 245, 245, 255);''',
      r'''    ui_label(p.x + ui_pr_mg, p.y + UI_PREF_HEAD / 2 + 4, "Preferences", ui_pr_tpx, 245, 245, 245, 255);''')
patch("row names", r'''        ui_label(p.x + 32, cy, ui_pref_name[i], 20, 245, 245, 245, i == ui_prefs_hover ? 255 : 210);     /* the name stays */''',
      r'''        ui_label(p.x + ui_pr_mg, cy, ui_pref_name[i], ui_pr_px, 245, 245, 245, i == ui_prefs_hover ? 255 : 210);     /* the name stays */''')
patch("value width", r'''            vw = ui_text_width(value, 20);''', r'''            vw = ui_text_width(value, ui_pr_px);''')
patch("value off", r'''                ui_label(vx, cy, value, 20, 150, 150, 150, (int)(255 * k));''', r'''                ui_label(vx, cy, value, ui_pr_px, 150, 150, 150, (int)(255 * k));''')
patch("value on", r'''                ui_label(vx, cy, value, 20, 245, 245, 245, (int)(255 * k));''', r'''                ui_label(vx, cy, value, ui_pr_px, 245, 245, 245, (int)(255 * k));''')
patch("hint only when there is room", r'''    ui_label(p.x + 32, p.y + p.h - UI_PREF_FOOT / 2, "Move the mouse onto a setting''',
      r'''    if (UI_PREF_FOOT >= 30)
        ui_label(p.x + ui_pr_mg, p.y + p.h - UI_PREF_FOOT / 2, "Move the mouse onto a setting''')

# ============================================================ the main menu in a short window
patch("menu row height", r'''#define UI_MENU_ROW 44          /* height of one menu row in pixels */''',
r'''static int ui_menu_rowh = 44;           /* height of one menu row: smaller when the window is short */
#define UI_MENU_ROW ui_menu_rowh''')
patch("menu fits the window", r'''    for (i = 0; i < UI_MENU_ITEMS; i++)
        longest = FFMAX(longest, ui_text_width(ui_menu_label[i], 22));
    r.w = longest + 56;''', r'''    ui_menu_rowh = av_clip((wh - 16) / UI_MENU_ITEMS, 30, 44);
    for (i = 0; i < UI_MENU_ITEMS; i++)
        longest = FFMAX(longest, ui_text_width(ui_menu_label[i], 22));
    r.w = longest + 56;''')

# ============================================================ corners: the buttons of the title bar are out of the way
patch("button margin", r'''#define UI_TB_BTN   40                  /* width of each button */''',
r'''#define UI_TB_BTN   40                  /* width of each button */
#define UI_TB_PAD   22                  /* the corners of the window (to resize it) are left of and right of the buttons */''')
patch("button places", r'''cx1 = UI_TB_BTN / 2, cx2;''', r'''cx1 = UI_TB_PAD + UI_TB_BTN / 2, cx2;''')
patch("right button place", r'''    cx2 = w - UI_TB_BTN / 2;''', r'''    cx2 = w - UI_TB_PAD - UI_TB_BTN / 2;''')
patch("which button (drawing)", r'''            ui_tb_hover = mx < UI_TB_BTN ? 1 : mx >= w - UI_TB_BTN ? 2 : 0;''',
      r'''            ui_tb_hover = (mx >= UI_TB_PAD && mx < UI_TB_PAD + UI_TB_BTN) ? 1 :
                          (mx >= w - UI_TB_PAD - UI_TB_BTN && mx < w - UI_TB_PAD) ? 2 : 0;''')
patch("which button (mouse)", r'''        hover = x < UI_TB_BTN ? 1 : x >= w - UI_TB_BTN ? 2 : 0;''',
      r'''        hover = (x >= UI_TB_PAD && x < UI_TB_PAD + UI_TB_BTN) ? 1 : (x >= w - UI_TB_PAD - UI_TB_BTN && x < w - UI_TB_PAD) ? 2 : 0;''')
patch("title room", r'''    ui_fit_text(name, 14, w - 2 * (UI_TB_BTN + 16));''', r'''    ui_fit_text(name, 14, w - 2 * (UI_TB_PAD + UI_TB_BTN + 16));''')
patch("drag area", r'''area->x >= UI_TB_BTN && area->x < w - UI_TB_BTN)
        return SDL_HITTEST_DRAGGABLE;''', r'''area->x >= UI_TB_PAD + UI_TB_BTN && area->x < w - UI_TB_PAD - UI_TB_BTN)
        return SDL_HITTEST_DRAGGABLE;''')

# ============================================================ crisp edges and round corners
patch("fringe state", r'''static int ui_tp_on = 0;''', r'''static double ui_flow_hint = 0.0;           /* 0 to 1: the "Back to playing" hint */
static int ui_tp_on = 0;''')

between("smooth edges", r'''static void ui_quad_fringe(SDL_Texture *tex, const SDL_Vertex *v, int n)''', r'''static void ui_flow_quad(SDL_Texture *tex, const SDL_Rect *t, int al, int md, double tilt)''', r'''static void ui_quad_fringe(SDL_Texture *tex, const SDL_Vertex *v, int n)
{
    enum { MAXN = 48 };
    SDL_Vertex f[(MAXN + 1) * 4 + 8];
    int idx[MAXN * 12 + 12], k, a, b, ni, side;

    if (n > MAXN || v[0].color.a <= 40)         /* the faint shadows do not need it */
        return;
    for (k = 0; k <= n; k++) {                  /* the outline, half a pixel inside, fading to nothing a pixel outside it (along its normal) */
        int k0 = k ? k - 1 : 0, k1 = k < n ? k + 1 : n;

        for (side = 0; side < 2; side++) {      /* 0 = the top chain, 1 = the bottom chain */
            const SDL_Vertex *p = &v[k * 2 + side], *p0 = &v[k0 * 2 + side], *p1 = &v[k1 * 2 + side];
            double tx = p1->position.x - p0->position.x, ty = p1->position.y - p0->position.y;
            double len = sqrt(tx * tx + ty * ty), nx, ny;

            if (len < 1e-6) {
                nx = 0.0;
                ny = side ? 1.0 : -1.0;
            } else {
                nx = side ? -ty / len : ty / len;
                ny = side ? tx / len : -tx / len;
            }
            f[k * 4 + side * 2] = *p;
            f[k * 4 + side * 2].position.x -= (float)(0.5 * nx);
            f[k * 4 + side * 2].position.y -= (float)(0.5 * ny);
            f[k * 4 + side * 2 + 1] = *p;
            f[k * 4 + side * 2 + 1].position.x += (float)(1.0 * nx);
            f[k * 4 + side * 2 + 1].position.y += (float)(1.0 * ny);
            f[k * 4 + side * 2 + 1].color.a = 0;
        }
    }
    ni = 0;
    for (k = 0; k < n; k++) {
        a = k * 4;
        b = (k + 1) * 4;
        idx[ni++] = a;      idx[ni++] = a + 1;  idx[ni++] = b;
        idx[ni++] = a + 1;  idx[ni++] = b + 1;  idx[ni++] = b;
        idx[ni++] = a + 2;  idx[ni++] = a + 3;  idx[ni++] = b + 2;
        idx[ni++] = a + 3;  idx[ni++] = b + 3;  idx[ni++] = b + 2;
    }
    for (side = 0; side < 2; side++) {          /* the left and the right side */
        int base = (n + 1) * 4 + side * 4, col = side ? n : 0;
        float dx = side ? 1.0f : -1.0f;

        f[base] = v[col * 2];                   /* the top corner, half a pixel inside */
        f[base].position.x -= 0.5f * dx;
        f[base + 1] = v[col * 2];               /* ...and a pixel outside */
        f[base + 1].position.x += 1.0f * dx;
        f[base + 1].color.a = 0;
        f[base + 2] = v[col * 2 + 1];
        f[base + 2].position.x -= 0.5f * dx;
        f[base + 3] = v[col * 2 + 1];
        f[base + 3].position.x += 1.0f * dx;
        f[base + 3].color.a = 0;
        idx[ni++] = base;      idx[ni++] = base + 1;  idx[ni++] = base + 2;
        idx[ni++] = base + 1;  idx[ni++] = base + 3;  idx[ni++] = base + 2;
    }
    SDL_RenderGeometry(renderer, tex, f, (n + 1) * 4 + 8, idx, ni);
}

''')

patch("round corners: more columns", r'''    enum { NC = 24 };
    SDL_Vertex v[(NC + 1) * 2];''', r'''    enum { NA = 14, NSTR = 4, NC = NA * 2 + NSTR };     /* columns: the left corner, the straight part, the right corner */
    SDL_Vertex v[(NC + 1) * 2];''')
patch("round corners: even arcs", r'''        if (k <= 8)                             /* the left corner */
            x = rr * k / 8.0;
        else if (k <= 16)                       /* the straight part */
            x = rr + (t->w - 2.0 * rr) * (k - 8) / 8.0;
        else                                    /* the right corner */
            x = t->w - rr + rr * (k - 16) / 8.0;
        dx = FFMIN(x, t->w - x);
        if (dx < rr)
            inset = rr - sqrt(FFMAX((double)rr * rr - (rr - dx) * (rr - dx), 0.0));''', r'''        if (k <= NA) {                          /* the left corner: even steps along the arc */
            double th = 1.57079632679 * k / NA;

            x = rr * (1.0 - cos(th));
            inset = rr * (1.0 - sin(th));
        } else if (k <= NA + NSTR) {            /* the straight part */
            x = rr + (t->w - 2.0 * rr) * (k - NA) / NSTR;
        } else {                                /* the right corner */
            double th = 1.57079632679 * (k - NA - NSTR) / NA;

            x = t->w - rr + rr * sin(th);
            inset = rr * (1.0 - cos(th));
        }
        dx = 0.0;
        (void)dx;''')

patch("video tiles are rounded", r'''    int cw = 0, ch = 0, k;

    tex = ui_cov_native(q_items[idx], &cw, &ch);        /* a video keeps its own shape, whatever is playing */
    if (!tex)''', r'''    int cw = 0, ch = 0, k, vid;

    tex = ui_cov_native(q_items[idx], &cw, &ch);        /* a video keeps its own shape, whatever is playing */
    vid = tex != NULL;
    if (!tex)''')
patch("video tiles are rounded (draw)", r'''    if (tex)
        ui_flow_quad(tex, tile, al, md, tilt);
}''', r'''    if (tex && vid)                             /* the tiles of videos have the rounded corners of the playing one */
        ui_flow_quad_round(tex, tile, al, md, tilt, FFMIN(tile->w, tile->h) / 11);
    else if (tex)
        ui_flow_quad(tex, tile, al, md, tilt);
}''')
patch("round quad before the tile", r'''static void ui_flow_tile(int idx, const SDL_Rect *tile, int al, int md, double tilt)
{''', r'''static void ui_flow_quad_round(SDL_Texture *tex, const SDL_Rect *t, int al, int md, double tilt, int rr);

static void ui_flow_tile(int idx, const SDL_Rect *tile, int al, int md, double tilt)
{''')

# ============================================================ the queue view: small windows, the hint, previews
patch("labels fit a small window", r'''    ui_q_name(ci, name, 300);                   /* the name under the middle cover */
    ui_fit_text(name, 22, (int)(W * 0.8));
    nal = ui_flow_vmode ? (int)(255 * ui_vflow_ep) : 255;       /* the labels fade in with the tiles */
    ui_label_c(W / 2, cy + chh / 2 + 40, name, 22, 255, 255, 255, nal);''', r'''    ui_q_name(ci, name, 300);                   /* the name under the middle cover */
    sm = H < 460;                               /* a small window: a smaller name, no counter, fewer bars */
    npx = sm ? 18 : 22;
    gy = cy + chh / 2 + (sm ? 26 : 40);
    ui_fit_text(name, npx, (int)(W * 0.8));
    nal = ui_flow_vmode ? (int)(255 * ui_vflow_ep) : 255;       /* the labels fade in with the tiles */
    ui_label_c(W / 2, gy, name, npx, 255, 255, 255, nal);''')
patch("small window locals", r'''static void ui_flow_draw(VideoState *is)
{
    enum { NEQ = 72 };''', r'''static void ui_flow_draw(VideoState *is)
{
    enum { NEQ = 72 };
    int sm, npx, gy;''')
patch("dot follows the name", r'''        pdot.x = W / 2 - ui_text_width(name, 22) / 2 - 20;
        pdot.y = cy + chh / 2 + 40 - 4;''', r'''        pdot.x = W / 2 - ui_text_width(name, npx) / 2 - 20;
        pdot.y = gy - 4;''')
patch("counter and hint", r'''    snprintf(num, sizeof(num), "%d / %d", ci + 1, q_count);
    ui_label_c(W / 2, cy + chh / 2 + 70, num, 15, 175, 175, 175, nal);
''', r'''    snprintf(num, sizeof(num), "%d / %d", ci + 1, q_count);
    if (!sm)
        ui_label_c(W / 2, cy + chh / 2 + 70, num, 15, 175, 175, 175, nal);
    {                                           /* a small hint while the row is away from the playing item (a tap outside the tiles also goes back) */
        double want = (ui_flow_target != q_pos && !ui_flow_dragging) ? 1.0 : 0.0;

        ui_flow_hint += (want - ui_flow_hint) * (1.0 - exp(-dt * 12.0));
        if (fabs(want - ui_flow_hint) < 0.01)
            ui_flow_hint = want;
        else
            ui_flow_moving = 1;                 /* keep drawing while it fades */
        if (ui_flow_hint > 0.02) {
            SDL_Rect hr;
            int hw = ui_text_width("Back to playing", 14) + 26, hy = sm ? gy + 24 : cy + chh / 2 + 70;

            hr.w = hw;
            hr.h = 24;
            hr.x = sm ? W / 2 - hw / 2 : W / 2 + ui_text_width(num, 15) / 2 + 18;
            hr.y = hy - 12;
            SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, (int)(95 * ui_flow_hint * nal / 255));
            ui_rr_fill(&hr, 12);
            ui_label_c(hr.x + hw / 2, hy, "Back to playing", 14, 255, 255, 255, (int)(255 * ui_flow_hint * nal / 255));
        }
    }
''')
patch("bars in a small window", r'''        int x0 = 24, span = W - 48;             /* where the bars start, and how wide they spread */''',
      r'''        int x0 = 24, span = W - 48, bars_ok = 1;        /* where the bars start, and how wide they spread */''')
patch("bars: room", r'''            int top = cy + chh / 2 + 84, space = sk.y - 12 - top;

            mid = top + space / 2;                      /* the bars grow up and down from this line */
            maxh = av_clip(space - 12, 14, 220);        /* the tallest a bar can be */''', r'''            int top = cy + chh / 2 + (sm ? 52 : 84), space = sk.y - 12 - top;

            bars_ok = space >= 18;                      /* no room (a small window): no bars, instead of bars over the name */
            mid = top + space / 2;                      /* the bars grow up and down from this line */
            maxh = av_clip(space - 12, 6, 220);         /* the tallest a bar can be */''')
patch("bars: only with room", r'''        for (j = 0; j < nb; j++) {
            if (have) {''', r'''        for (j = 0; j < nb && bars_ok; j++) {
            if (have) {''')

between("previews keep going between tiles", r'''/* Once per drawing of the queue view: a video tile that the mouse rests on for a moment starts to play */''',
        r'''/* The preview, if it is the one of tile i''', r'''/* Once per drawing of the queue view: a video tile that the mouse rests on for a moment starts to play. Moving on to the next
   tile right after (or over the gap between two tiles) keeps it going: the next one starts at once. */
static void ui_tp_tick(VideoState *is)
{
    static int cand = -1;
    static int64_t since = 0, gone = 0, active = 0;
    int64_t now = av_gettime_relative();
    int idx = -1;

    if (UI_TILE_PREVIEW && ui_hov_x >= 0 && ui_flow_press < 0 && !ui_flow_dragging && !ui_menu_open && !ui_prefs_open) {
        int i = ui_flow_cover_at(is, ui_hov_x, ui_hov_y);

        if (i >= 0 && i < q_count && i != q_pos && ui_cov_aspect(q_items[i]) > 0.0)
            idx = i;
    }
    if (idx < 0 && cand >= 0 && ui_hov_x >= 0) {        /* off the tile for a moment (a gap, the playing tile): carry on a little */
        if (!gone)
            gone = now;
        if (now - gone < 350000)
            idx = cand;
    } else {
        gone = 0;
    }
    if (ui_tp.file)
        active = now;
    if (idx != cand) {                          /* another tile, or none: the preview stops */
        cand = idx;
        since = now;
        ui_tp_stop();
    } else if (idx >= 0 && !ui_tp.file && now - since > (now - active < 1500000 ? 0 : 400000)) {
        ui_tp_start(idx);
    }
    ui_tp_on = cand >= 0;
}

''')

# ============================================================ stutter: what could take the time, and how to see it
patch("previews of the seek bar start later", r'''    if (isnan(pos) || pos < 1.5)
        return;
    dur = is->ic->duration / (double)AV_TIME_BASE;''', r'''    if (isnan(pos) || pos < 4.0)                /* not in the first seconds of an item */
        return;
    dur = is->ic->duration / (double)AV_TIME_BASE;''')
patch("previews of the seek bar breathe", r'''        av_frame_unref(fr);
    }
end:
    av_log(NULL, AV_LOG_VERBOSE, "ffplay-custom: seek previews''', r'''        av_frame_unref(fr);
        av_usleep(6000);                        /* a breath between pictures: never a whole core */
    }
end:
    av_log(NULL, AV_LOG_VERBOSE, "ffplay-custom: seek previews''')

patch("slow loop timer", r'''static void refresh_loop_wait_event(VideoState *is, SDL_Event *event) {''', r'''/* A tick or a refresh that takes long is named in the terminal, so a stutter can be traced to what caused it */
#define UI_TIMED(call) do { \
        int64_t t_ = av_gettime_relative(); \
        call; \
        t_ = av_gettime_relative() - t_; \
        if (t_ > 40000) \
            av_log(NULL, AV_LOG_WARNING, "ffplay-custom: slow: %s took %d ms\n", #call, (int)(t_ / 1000)); \
    } while (0)

static void refresh_loop_wait_event(VideoState *is, SDL_Event *event) {''')
patch("timed ticks", r'''        ui_aspect_tick(is);
        ui_inbox_tick(is);
        ui_menu_tick(is);
        ui_power_tick(is);
        ui_sleep_tick(is);
        ui_xfade_tick(is);
        ui_pause_tick(is);
        ui_ks_tick(is);
        ui_th_tick(is);
        ui_cover_tick(is);
        ui_mpris_tick(is);''', r'''        UI_TIMED(ui_aspect_tick(is));
        UI_TIMED(ui_inbox_tick(is));
        UI_TIMED(ui_menu_tick(is));
        UI_TIMED(ui_power_tick(is));
        UI_TIMED(ui_sleep_tick(is));
        UI_TIMED(ui_xfade_tick(is));
        UI_TIMED(ui_pause_tick(is));
        UI_TIMED(ui_ks_tick(is));
        UI_TIMED(ui_th_tick(is));
        UI_TIMED(ui_cover_tick(is));
        UI_TIMED(ui_mpris_tick(is));''')
patch("timed refresh", r'''            video_refresh(is, &remaining_time);
        SDL_PumpEvents();
    }
}''', r'''            UI_TIMED(video_refresh(is, &remaining_time));
        SDL_PumpEvents();
    }
}''')

if fails:
    print("\n%d patches did not apply. Nothing was written." % len(fails))
    sys.exit(1)
open(PATH, "w").write(src)
print("Patched " + PATH)
