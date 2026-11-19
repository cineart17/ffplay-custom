#!/usr/bin/env python3
# Update 36 for ffplay-custom (on top of patch_queue_v35.py).
#   * The seek and volume bar is the old flat strip again: a short dark frosted bar, edge to edge and flush with the bottom
#     of the window (no rounded ends, not floating). The controls and the seek tooltip move down with it.
#   * Preferences: the soft pill under the choice the mouse is on is gone. The choice under the mouse rises a little and gets
#     brighter instead.
#   * Queue panel: the Crossfade and Sleep timer rows now nudge their names from the left margin when the mouse is on them
#     (like the preference rows), and their choices rise and brighten under the mouse the same way.
#   * Video queue tiles (the queue view over a video) turn the other way: convex, like the outside of a cylinder. The edge
#     nearest the middle is the tall one now. Song queues keep their look.
#   * Line icons (thin, smooth, drawn once into small textures): right-click menu (Open, Queue, Media Info, Preferences, Quit),
#     Open > File / Folder, the queue item menu (Remove, Sleep after), the Crossfade and Sleep timer rows, and every
#     preference row.
#   * (added when merged: the old rounded bar glass function is marked unused, so the build prints no warning.)
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v35.py. Writes the file only if every edit matches.
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


if "ui_icon_tex" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_pip_was_top" not in src:
    print("Apply patch_queue_v35.py first. Nothing written.")
    sys.exit(1)

# ---------------------------------------------------------------- 1. the flat bar
patch("bar height", r'''#define UI_BAR_H 56                     /* the pill of the bars: 48 high, 4 from the bottom, and a little room around it */''',
      r'''#define UI_BAR_GLASS 30                 /* the flat bar of glass along the bottom edge */
#define UI_BAR_H 32                     /* the strip the mouse reacts to: the bar and a little room above it */''')

patch("bar layout", r'''    /* Floating rounded pill style with 16px bottom margin and side padding */
    int margin_x = 24;
    int bottom_offset = 24;                 /* the middle of the bars is 28 px above the bottom: the middle of the glass pill */
    int bar_h = 8;''', r'''    /* A flat strip along the bottom edge: the middle of the bars is 15 px above the bottom, the middle of the glass */
    int margin_x = 24;
    int bottom_offset = 12;
    int bar_h = 6;''')

patch("bar glass", r'''    {                                           /* the bars sit in a pill of dark liquid glass, in its middle */
        SDL_Rect pill;

        pill.x = 10;
        pill.w = is->width - 20;
        pill.h = 48;
        pill.y = is->height - 52;
        ui_glass_dark(&pill, 24);
        SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    }''', r'''    {                                           /* the bars sit on a flat strip of dark frosted glass: edge to edge, from the bottom */
        SDL_Rect strip;

        strip.x = 0;
        strip.w = is->width;
        strip.h = UI_BAR_GLASS;
        strip.y = is->height - UI_BAR_GLASS;
        ui_glass_bar(&strip);
        SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    }''')

patch("bar glass prototype", r'''static void ui_glass_dark(const SDL_Rect *t, int r);

static int ui_on_top = 0;''', r'''static void ui_glass_dark(const SDL_Rect *t, int r);
static void ui_glass_bar(const SDL_Rect *t);

static int ui_on_top = 0;''')

patch("bar glass function", r'''/* The idle background: a few soft glows in the bar color that drift slowly.''', r'''/* The flat bar along the bottom: the same dark frosted glass, with square corners (it runs off the window on three sides) */
static void ui_glass_bar(const SDL_Rect *t)
{
    int ink = ui_ink_dark;

    ui_ink_dark = 0;
    ui_liquid(t, 0, 8, 10, 14, 125, 0);
    ui_ink_dark = ink;
}

/* The idle background: a few soft glows in the bar color that drift slowly.''')

patch("tooltip a little higher", r'''    box.y = sk->y - 16 - box.h;''', r'''    box.y = sk->y - 22 - box.h;''')

# ---------------------------------------------------------------- 2. icons and the pop of a choice
ICONS = r'''/* ----- line icons -----
   Thin single-line icons for the menus. Each one is a few strokes (lines and arcs) on a 24 x 24 grid, drawn once for each size
   into a small texture with smooth edges, and tinted when it is drawn. */
enum { UI_IC_OPEN, UI_IC_FOLDER, UI_IC_FILE, UI_IC_QUEUE, UI_IC_INFO, UI_IC_GEAR, UI_IC_POWER, UI_IC_TRASH, UI_IC_MOON,
       UI_IC_FADE, UI_IC_SKIP, UI_IC_VOLUME, UI_IC_EYE, UI_IC_EXPAND, UI_IC_DROP, UI_IC_BOOKMARK, UI_IC_EXIT, UI_IC_MOUSE,
       UI_IC_N };
#define UI_IC_MAXS 80
typedef struct { float a, b, c, d, e, f; int arc; } UiStroke;       /* a line (a,b to c,d) or an arc (centre a,b, radius c, angles e to f) */
static UiStroke ui_is[UI_IC_MAXS];
static int ui_is_n;

static void ic_seg(float x0, float y0, float x1, float y1)
{
    UiStroke *s;

    if (ui_is_n >= UI_IC_MAXS)
        return;
    s = &ui_is[ui_is_n++];
    s->a = x0; s->b = y0; s->c = x1; s->d = y1; s->e = s->f = 0.0f; s->arc = 0;
}

static void ic_arc(float cx, float cy, float r, float a0, float a1)
{
    UiStroke *s;

    if (ui_is_n >= UI_IC_MAXS)
        return;
    s = &ui_is[ui_is_n++];
    s->a = cx; s->b = cy; s->c = r; s->d = 0.0f; s->e = a0; s->f = a1; s->arc = 1;
}

static void ic_poly(const float *p, int n, int closed)
{
    int i;

    for (i = 0; i + 1 < n; i++)
        ic_seg(p[i * 2], p[i * 2 + 1], p[i * 2 + 2], p[i * 2 + 3]);
    if (closed && n > 2)
        ic_seg(p[(n - 1) * 2], p[(n - 1) * 2 + 1], p[0], p[1]);
}

static void ic_rrect(float x, float y, float w, float h, float r)
{
    ic_seg(x + r, y, x + w - r, y);
    ic_seg(x + w, y + r, x + w, y + h - r);
    ic_seg(x + r, y + h, x + w - r, y + h);
    ic_seg(x, y + r, x, y + h - r);
    ic_arc(x + r, y + r, r, 180, 270);
    ic_arc(x + w - r, y + r, r, 270, 360);
    ic_arc(x + w - r, y + h - r, r, 0, 90);
    ic_arc(x + r, y + h - r, r, 90, 180);
}

static void ui_icon_build(int id)
{
    ui_is_n = 0;
    switch (id) {
    case UI_IC_OPEN: {                          /* an open folder */
        static const float back[] = { 19, 11.5f, 19, 9, 11.2f, 9, 9, 6.5f, 3, 6.5f, 3, 19 };
        static const float front[] = { 3, 19, 6.2f, 12, 22, 12, 18.8f, 19 };

        ic_poly(back, 6, 0);
        ic_poly(front, 4, 0);
        ic_seg(3, 19, 18.8f, 19);
        break;
    }
    case UI_IC_FOLDER: {
        static const float f[] = { 3, 6.5f, 9, 6.5f, 11.2f, 9, 21, 9, 21, 19, 3, 19 };

        ic_poly(f, 6, 1);
        break;
    }
    case UI_IC_FILE: {
        static const float f[] = { 6, 3, 14, 3, 19, 8, 19, 21, 6, 21 };
        static const float fold[] = { 14, 3, 14, 8, 19, 8 };

        ic_poly(f, 5, 1);
        ic_poly(fold, 3, 0);
        break;
    }
    case UI_IC_QUEUE:
        ic_seg(9, 7, 20, 7);
        ic_seg(9, 12, 20, 12);
        ic_seg(9, 17, 20, 17);
        ic_seg(4, 7, 4.3f, 7);
        ic_seg(4, 12, 4.3f, 12);
        ic_seg(4, 17, 4.3f, 17);
        break;
    case UI_IC_INFO:
        ic_arc(12, 12, 9, 0, 360);
        ic_seg(12, 11, 12, 17);
        ic_seg(12, 7.6f, 12, 7.7f);
        break;
    case UI_IC_GEAR: {
        static const float da[4] = { -15.0f, -9.0f, 9.0f, 15.0f }, dr[4] = { 7.3f, 9.6f, 9.6f, 7.3f };
        float pts[8 * 4 * 2];
        int k, j, n = 0;

        for (k = 0; k < 8; k++)
            for (j = 0; j < 4; j++) {
                float an = (k * 45.0f + da[j]) * 3.14159265f / 180.0f;

                pts[n++] = 12.0f + dr[j] * cosf(an);
                pts[n++] = 12.0f + dr[j] * sinf(an);
            }
        ic_poly(pts, 32, 1);
        ic_arc(12, 12, 3.2f, 0, 360);
        break;
    }
    case UI_IC_POWER:
        ic_arc(12, 13.2f, 7.6f, -50, 230);
        ic_seg(12, 3.5f, 12, 12);
        break;
    case UI_IC_TRASH: {
        static const float lid[] = { 9, 6.5f, 9, 4, 15, 4, 15, 6.5f };
        static const float body[] = { 6, 6.5f, 7, 20, 17, 20, 18, 6.5f };

        ic_seg(4, 6.5f, 20, 6.5f);
        ic_poly(lid, 4, 0);
        ic_poly(body, 4, 0);
        ic_seg(10, 10.5f, 10, 16);
        ic_seg(14, 10.5f, 14, 16);
        break;
    }
    case UI_IC_MOON:
        ic_arc(12, 12, 9, 5, 265);
        ic_arc(16.85f, 7.15f, 7, 53.7f, 216.3f);
        break;
    case UI_IC_FADE:                            /* two circles that overlap: one fades into the other */
        ic_arc(9, 12, 6.5f, 0, 360);
        ic_arc(15, 12, 6.5f, 0, 360);
        break;
    case UI_IC_SKIP: {
        static const float t[] = { 6, 5.5f, 16, 12, 6, 18.5f };

        ic_poly(t, 3, 1);
        ic_seg(19, 5.5f, 19, 18.5f);
        break;
    }
    case UI_IC_VOLUME: {
        static const float s[] = { 4, 9.5f, 8, 9.5f, 13, 5.5f, 13, 18.5f, 8, 14.5f, 4, 14.5f };

        ic_poly(s, 6, 1);
        ic_arc(13, 12, 5, -48, 48);
        ic_arc(13, 12, 8.5f, -48, 48);
        break;
    }
    case UI_IC_EYE:
        ic_arc(12, 17.45f, 10.95f, 209.8f, 330.2f);
        ic_arc(12, 6.55f, 10.95f, 29.8f, 150.2f);
        ic_arc(12, 12, 2.8f, 0, 360);
        break;
    case UI_IC_EXPAND: {
        static const float a[] = { 4, 9, 4, 4, 9, 4 }, b[] = { 15, 4, 20, 4, 20, 9 };
        static const float c[] = { 20, 15, 20, 20, 15, 20 }, d[] = { 9, 20, 4, 20, 4, 15 };

        ic_poly(a, 3, 0);
        ic_poly(b, 3, 0);
        ic_poly(c, 3, 0);
        ic_poly(d, 3, 0);
        break;
    }
    case UI_IC_DROP:
        ic_arc(12, 14.5f, 6.5f, -36.2f, 216.2f);
        ic_seg(12, 3.5f, 17.25f, 10.66f);
        ic_seg(12, 3.5f, 6.75f, 10.66f);
        break;
    case UI_IC_BOOKMARK: {
        static const float m[] = { 7, 3.5f, 17, 3.5f, 17, 20.5f, 12, 16.5f, 7, 20.5f };

        ic_poly(m, 5, 1);
        break;
    }
    case UI_IC_EXIT: {
        static const float br[] = { 10, 4, 4.5f, 4, 4.5f, 20, 10, 20 }, hd[] = { 16, 8, 20, 12, 16, 16 };

        ic_poly(br, 4, 0);
        ic_seg(9.5f, 12, 20, 12);
        ic_poly(hd, 3, 0);
        break;
    }
    case UI_IC_MOUSE:
        ic_rrect(6.5f, 3, 11, 18, 5.5f);
        ic_seg(12, 7, 12, 10.5f);
        break;
    }
}

static float ui_ic_dist(const UiStroke *s, float px, float py)
{
    if (!s->arc) {
        float vx = s->c - s->a, vy = s->d - s->b, wx = px - s->a, wy = py - s->b, l2 = vx * vx + vy * vy, t = 0.0f, dx, dy;

        if (l2 > 1e-6f)
            t = av_clipf((wx * vx + wy * vy) / l2, 0.0f, 1.0f);
        dx = wx - t * vx;
        dy = wy - t * vy;
        return sqrtf(dx * dx + dy * dy);
    } else {
        float dx = px - s->a, dy = py - s->b, rr = sqrtf(dx * dx + dy * dy), ang = atan2f(dy, dx) * 57.2957795f;
        float ex0, ey0, ex1, ey1, d0, d1;

        while (ang < s->e)
            ang += 360.0f;
        while (ang >= s->e + 360.0f)
            ang -= 360.0f;
        if (ang <= s->f)
            return fabsf(rr - s->c);
        ex0 = s->a + s->c * cosf(s->e * 0.0174532925f);
        ey0 = s->b + s->c * sinf(s->e * 0.0174532925f);
        ex1 = s->a + s->c * cosf(s->f * 0.0174532925f);
        ey1 = s->b + s->c * sinf(s->f * 0.0174532925f);
        d0 = sqrtf((px - ex0) * (px - ex0) + (py - ey0) * (py - ey0));
        d1 = sqrtf((px - ex1) * (px - ex1) + (py - ey1) * (py - ey1));
        return FFMIN(d0, d1);
    }
}

/* The icon id at a pixel size, drawn the first time it is asked for */
static SDL_Texture *ui_icon_tex(int id, int size)
{
    static SDL_Texture *tex[UI_IC_N][4];
    static int sz[UI_IC_N][4];
    SDL_Surface *surf;
    int slot, x, y, k, free_slot = -1;
    const float hw = 0.88f;                     /* half the stroke width, in grid units */

    if (id < 0 || id >= UI_IC_N || size < 8 || size > 64)
        return NULL;
    for (slot = 0; slot < 4; slot++) {
        if (tex[id][slot] && sz[id][slot] == size)
            return tex[id][slot];
        if (!tex[id][slot] && free_slot < 0)
            free_slot = slot;
    }
    if (free_slot < 0) {
        free_slot = 0;
        SDL_DestroyTexture(tex[id][0]);
        tex[id][0] = NULL;
    }
    ui_icon_build(id);
    surf = SDL_CreateRGBSurfaceWithFormat(0, size, size, 32, SDL_PIXELFORMAT_ARGB8888);
    if (!surf)
        return NULL;
    for (y = 0; y < size; y++) {
        Uint32 *row = (Uint32 *)((Uint8 *)surf->pixels + y * surf->pitch);

        for (x = 0; x < size; x++) {
            float gx = (x + 0.5f) * 24.0f / size, gy = (y + 0.5f) * 24.0f / size, dmin = 1e9f, cov;

            for (k = 0; k < ui_is_n; k++) {
                float d = ui_ic_dist(&ui_is[k], gx, gy);

                if (d < dmin)
                    dmin = d;
            }
            cov = av_clipf((hw - dmin) * size / 24.0f + 0.5f, 0.0f, 1.0f);
            row[x] = ((Uint32)(cov * 255.0f + 0.5f) << 24) | 0x00FFFFFFu;
        }
    }
    tex[id][free_slot] = SDL_CreateTextureFromSurface(renderer, surf);
    SDL_FreeSurface(surf);
    if (!tex[id][free_slot])
        return NULL;
    sz[id][free_slot] = size;
    SDL_SetTextureBlendMode(tex[id][free_slot], SDL_BLENDMODE_BLEND);
    return tex[id][free_slot];
}

/* An icon with its left edge at x and its middle at cy */
static void ui_icon(int id, int x, int cy, int size, int r, int g, int b, int a)
{
    SDL_Texture *tex = ui_icon_tex(id, size);
    SDL_Rect dst;

    if (!tex)
        return;
    dst.x = x;
    dst.y = cy - size / 2;
    dst.w = size;
    dst.h = size;
    a = av_clip((int)(a * ui_fade), 0, 255);
    ui_ink(&r, &g, &b);                         /* dark on the light glass */
    SDL_SetTextureColorMod(tex, r, g, b);
    SDL_SetTextureAlphaMod(tex, a);
    SDL_RenderCopy(renderer, tex, NULL, &dst);
}

#define UI_POP 3.0                      /* how far a choice rises under the mouse, in pixels */
/* One step of the rise of a choice: v goes toward 1 while the mouse is on it and back to 0 after. Returns the eased value. */
static double ui_pop_step(double *v, int hot, double dt, int *moving)
{
    double g = hot ? 1.0 : 0.0;

    *v += (g - *v) * (1.0 - exp(-dt / 0.06));
    if (fabs(g - *v) < 0.01)
        *v = g;
    else if (moving)
        *moving = 1;
    return *v * *v * (3.0 - 2.0 * *v);
}

/* ----- rounded rectangles ----- */
'''
patch("icons and pop", r'''/* ----- rounded rectangles ----- */
''', ICONS)

# ---------------------------------------------------------------- 3. the main menu
patch("menu icon width", r'''#define UI_MENU_ITEMS 5         /* rows in the menu */''',
      r'''#define UI_MENU_ITEMS 5         /* rows in the menu */
#define UI_MENU_ICW 32          /* room for the icon before the name of a row */''')
patch("menu width", r'''    r.w = longest + 56;
    r.h = UI_MENU_ITEMS * UI_MENU_ROW;''', r'''    r.w = longest + 56 + UI_MENU_ICW;
    r.h = UI_MENU_ITEMS * UI_MENU_ROW;''')
patch("menu rows", r'''        ui_label(row.x + 28 + (int)((1.0 - k) * 10), cy, ui_menu_label[i], 22, 240, 240, 240,
                 (int)((lit ? 255 : 205) * k));''', r'''        {
            static const int icons[UI_MENU_ITEMS] = { UI_IC_OPEN, UI_IC_QUEUE, UI_IC_INFO, UI_IC_GEAR, UI_IC_POWER };

            ui_icon(icons[i], row.x + 28 + (int)((1.0 - k) * 10), cy, 20, 240, 240, 240, (int)((lit ? 255 : 190) * k));
        }
        ui_label(row.x + 28 + UI_MENU_ICW + (int)((1.0 - k) * 10), cy, ui_menu_label[i], 22, 240, 240, 240,
                 (int)((lit ? 255 : 205) * k));''')

# the Open > File / Folder submenu
patch("open submenu width", r'''    p.w = FFMAX(ui_text_width("Folder...", 22), ui_text_width("File...", 22)) + 64;''',
      r'''    p.w = FFMAX(ui_text_width("Folder...", 22), ui_text_width("File...", 22)) + 64 + UI_MENU_ICW;''')
patch("open submenu rows", r'''        ui_label(p.x + 28, row_y + UI_MENU_ROW / 2, i ? "Folder..." : "File...", 22, 240, 240, 240,
                 i == ui_open_hover ? 255 : 205);''', r'''        ui_icon(i ? UI_IC_FOLDER : UI_IC_FILE, p.x + 28, row_y + UI_MENU_ROW / 2, 20, 240, 240, 240,
                i == ui_open_hover ? 255 : 190);
        ui_label(p.x + 28 + UI_MENU_ICW, row_y + UI_MENU_ROW / 2, i ? "Folder..." : "File...", 22, 240, 240, 240,
                 i == ui_open_hover ? 255 : 205);''')

# the queue item menu
patch("item menu width", r'''    r.w = w + 56;
    r.h = 2 * UI_CTX_ROW + 16;''', r'''    r.w = w + 56 + UI_MENU_ICW;
    r.h = 2 * UI_CTX_ROW + 16;''')
patch("item menu rows", r'''        ui_label(r.x + 28, row_y + UI_CTX_ROW / 2, ui_ctx_label(i), 20, 240, 240, 240,
                 i == ui_ctx_hover ? 255 : 205);''', r'''        ui_icon(i ? UI_IC_MOON : UI_IC_TRASH, r.x + 28, row_y + UI_CTX_ROW / 2, 18, 240, 240, 240,
                i == ui_ctx_hover ? 255 : 190);
        ui_label(r.x + 28 + UI_MENU_ICW, row_y + UI_CTX_ROW / 2, ui_ctx_label(i), 20, 240, 240, 240,
                 i == ui_ctx_hover ? 255 : 205);''')

# ---------------------------------------------------------------- 4. the queue panel rows
patch("queue panel a little wider", r'''#define UI_Q_W 420              /* panel width */''',
      r'''#define UI_Q_W 450              /* panel width */
#define UI_Q_ICW 28             /* room for the icon before the name of the Crossfade and Sleep timer rows */''')
patch("queue chips room", r'''room = p->w - 40 - labelw - 14;''', r'''room = p->w - 40 - labelw - 14 - UI_Q_ICW - 10;''')

patch("crossfade name nudges", r'''        ui_label(p.x + 20, cy, "Crossfade", 18, 240, 240, 240, 210);''',
      r'''        ui_icon(UI_IC_FADE, p.x + 20 + (int)(10 * se), cy, 18, 240, 240, 240, 190);
        ui_label(p.x + 20 + UI_Q_ICW + (int)(10 * se), cy, "Crossfade", 18, 240, 240, 240, 210);    /* the name nudges to usher the choices in */''')
patch("crossfade choices pop", r'''        if (ui_xf_e > 0.01) {
            for (k = 1; k < 7; k++)
                if (abs(ui_xf_vals[k] - cfg_crossfade) < abs(ui_xf_vals[cur] - cfg_crossfade))
                    cur = k;''', r'''        if (ui_xf_e <= 0.01)
            memset(ui_xf_pop, 0, sizeof(ui_xf_pop));
        if (ui_xf_e > 0.01) {
            for (k = 1; k < 7; k++)
                if (abs(ui_xf_vals[k] - cfg_crossfade) < abs(ui_xf_vals[cur] - cfg_crossfade))
                    cur = k;''')
patch("crossfade choices draw", r'''                int hot = hk == UI_Q_XFCHIP && ui_q_hover_idx == k;
                double cxc = xr[k].x + xr[k].w / 2.0, cx = hx + (cxc - hx) * se;

                if (k == cur)
                    ui_label_c((int)cx, cy, xn[k], xpx, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                               av_clip(cfg_bar_b + 40, 0, 255), (int)(255 * se));
                else
                    ui_label_c((int)cx, cy, xn[k], xpx, 245, 245, 245, (int)((hot ? 255 : 160) * se));''',
      r'''                int hot = hk == UI_Q_XFCHIP && ui_q_hover_idx == k, mv = 0, ly;
                double cxc = xr[k].x + xr[k].w / 2.0, cx = hx + (cxc - hx) * se, pe;

                pe = ui_pop_step(&ui_xf_pop[k], hot, dt, &mv);      /* the choice under the mouse rises and brightens */
                if (mv)
                    ui_xf_anim = 1;
                ly = cy - (int)(UI_POP * pe + 0.5);
                if (k == cur)
                    ui_label_c((int)cx, ly, xn[k], xpx, av_clip(cfg_bar_r + 40 + (int)(30 * pe), 0, 255),
                               av_clip(cfg_bar_g + 40 + (int)(30 * pe), 0, 255), av_clip(cfg_bar_b + 40 + (int)(30 * pe), 0, 255),
                               (int)(255 * se));
                else
                    ui_label_c((int)cx, ly, xn[k], xpx, 215 + (int)(40 * pe), 215 + (int)(40 * pe), 215 + (int)(40 * pe),
                               (int)((160 + 95 * pe) * se));''')
patch("crossfade pop state", r'''static double ui_xf_e = 0.0;            /* 0 to 1: how far the crossfade row has changed into its choices */''',
      r'''static double ui_xf_e = 0.0;            /* 0 to 1: how far the crossfade row has changed into its choices */
static double ui_xf_pop[7], ui_sl_pop[6];       /* 0 to 1: how far each choice has risen under the mouse */''')

patch("sleep name nudges", r'''        ui_label(p.x + 20, cy, "Sleep timer", 18, 240, 240, 240, 210);''',
      r'''        ui_icon(UI_IC_MOON, p.x + 20 + (int)(10 * se), cy, 18, 240, 240, 240, 190);
        ui_label(p.x + 20 + UI_Q_ICW + (int)(10 * se), cy, "Sleep timer", 18, 240, 240, 240, 210);    /* the name nudges to usher the choices in */''')
patch("sleep choices pop", r'''        if (ui_chip_e > 0.01) {
            sn = ui_q_chips_for(''', r'''        if (ui_chip_e <= 0.01)
            memset(ui_sl_pop, 0, sizeof(ui_sl_pop));
        if (ui_chip_e > 0.01) {
            sn = ui_q_chips_for(''')
patch("sleep choices draw", r'''                int hot = hk == UI_Q_CHIP && ui_q_hover_idx == i;
                double cxc = sr[i].x + sr[i].w / 2.0, cx = hx + (cxc - hx) * se;

                if (i == sel)               /* the choice that is on: in the bar color */
                    ui_label_c((int)cx, cy, sn[i], spx, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                               av_clip(cfg_bar_b + 40, 0, 255), (int)(255 * se));
                else
                    ui_label_c((int)cx, cy, sn[i], spx, 245, 245, 245, (int)((hot ? 255 : 160) * se));''',
      r'''                int hot = hk == UI_Q_CHIP && ui_q_hover_idx == i, mv = 0, ly;
                double cxc = sr[i].x + sr[i].w / 2.0, cx = hx + (cxc - hx) * se, pe;

                pe = ui_pop_step(&ui_sl_pop[i], hot, dt, &mv);      /* the choice under the mouse rises and brightens */
                if (mv)
                    ui_chip_anim = 1;
                ly = cy - (int)(UI_POP * pe + 0.5);
                if (i == sel)               /* the choice that is on: in the bar color */
                    ui_label_c((int)cx, ly, sn[i], spx, av_clip(cfg_bar_r + 40 + (int)(30 * pe), 0, 255),
                               av_clip(cfg_bar_g + 40 + (int)(30 * pe), 0, 255), av_clip(cfg_bar_b + 40 + (int)(30 * pe), 0, 255),
                               (int)(255 * se));
                else
                    ui_label_c((int)cx, ly, sn[i], spx, 215 + (int)(40 * pe), 215 + (int)(40 * pe), 215 + (int)(40 * pe),
                               (int)((160 + 95 * pe) * se));''')

# ---------------------------------------------------------------- 5. the preferences
patch("pref pop state", r'''static double ui_pref_open[UI_PREF_ROWS];   /* 0 to 1: how far each row has changed into its list of choices */''',
      r'''static double ui_pref_open[UI_PREF_ROWS];   /* 0 to 1: how far each row has changed into its list of choices */
static double ui_pref_pop[UI_PREF_ROWS][10];    /* 0 to 1: how far each choice has risen under the mouse */
#define UI_PREF_ICW 28                  /* room for the icon before the name of a row */''')
patch("pref layout room", r'''    room = p->w - 2 * ui_pr_mg - ui_text_width(ui_pref_name[row], ui_pr_px) - 26;      /* the name stays at its margin (nudged 10 px) */''',
      r'''    room = p->w - 2 * ui_pr_mg - ui_text_width(ui_pref_name[row], ui_pr_px) - 26 - UI_PREF_ICW;      /* the icon and the name stay at their margin (nudged 10 px) */''')
patch("pref need width", r'''    return 2 * ui_pr_mg + ui_text_width(ui_pref_name[row], ui_pr_px) + 26 + total;''',
      r'''    return 2 * ui_pr_mg + ui_text_width(ui_pref_name[row], ui_pr_px) + 26 + UI_PREF_ICW + total;''')
patch("pref reset", r'''        for (i = 0; i < UI_PREF_ROWS; i++)
            ui_pref_open[i] = 0.0;
        ui_prefs_anim = 0;
        ui_prefs_w = 600.0;
        return;''', r'''        for (i = 0; i < UI_PREF_ROWS; i++)
            ui_pref_open[i] = 0.0;
        memset(ui_pref_pop, 0, sizeof(ui_pref_pop));
        ui_prefs_anim = 0;
        ui_prefs_w = 600.0;
        return;''')
patch("pref names with icons", r'''        ui_label(p.x + ui_pr_mg + (int)(10 * se), cy, ui_pref_name[i], ui_pr_px, 245, 245, 245,
                 i == ui_prefs_hover ? 255 : 210);      /* the name nudges a little to make room, like a volume bar coming in from the side */''',
      r'''        {
            static const int pic[UI_PREF_ROWS] = { UI_IC_SKIP, UI_IC_VOLUME, UI_IC_EYE, UI_IC_EXPAND, UI_IC_DROP,
                                                   UI_IC_BOOKMARK, UI_IC_EXIT, UI_IC_MOUSE };

            ui_icon(pic[i], p.x + ui_pr_mg + (int)(10 * se), cy, av_clip(ui_pr_px, 14, 22), 245, 245, 245,
                    i == ui_prefs_hover ? 255 : 170);
        }
        ui_label(p.x + ui_pr_mg + UI_PREF_ICW + (int)(10 * se), cy, ui_pref_name[i], ui_pr_px, 245, 245, 245,
                 i == ui_prefs_hover ? 255 : 210);      /* the name nudges a little to make room, like a volume bar coming in from the side */''')
patch("pref choices: no pill, they rise", r'''                hot = i == ui_prefs_hover && ui_prefs_mx >= r[c].x && ui_prefs_mx < r[c].x + r[c].w &&
                      ui_prefs_my >= r[c].y && ui_prefs_my < r[c].y + r[c].h;
                if (hot) {                      /* a soft pill under the choice the mouse is on */
                    SDL_Rect pill = r[c];

                    pill.x = (int)(cx - r[c].w / 2.0);
                    SDL_SetRenderDrawColor(renderer, 255, 255, 255, (int)(34 * sc));
                    ui_pill(&pill);
                }
                if (c == sel)                   /* the choice that is on: in the bar color */
                    ui_label_c((int)cx, cy, names[c], px, av_clip(cfg_bar_r + 40, 0, 255),
                               av_clip(cfg_bar_g + 40, 0, 255), av_clip(cfg_bar_b + 40, 0, 255), (int)(255 * sc));
                else
                    ui_label_c((int)cx, cy, names[c], px, 245, 245, 245, (int)((hot ? 255 : 170) * sc));''',
      r'''                hot = i == ui_prefs_hover && ui_prefs_mx >= r[c].x && ui_prefs_mx < r[c].x + r[c].w &&
                      ui_prefs_my >= r[c].y && ui_prefs_my < r[c].y + r[c].h;
                {                               /* no box under it: the choice the mouse is on rises a little and gets brighter */
                    int mv = 0, ly;
                    double pe = ui_pop_step(&ui_pref_pop[i][c], hot, dt, &mv);

                    if (mv)
                        ui_prefs_anim = 1;
                    ly = cy - (int)(UI_POP * pe + 0.5);
                    if (c == sel)               /* the choice that is on: in the bar color */
                        ui_label_c((int)cx, ly, names[c], px, av_clip(cfg_bar_r + 40 + (int)(30 * pe), 0, 255),
                                   av_clip(cfg_bar_g + 40 + (int)(30 * pe), 0, 255), av_clip(cfg_bar_b + 40 + (int)(30 * pe), 0, 255),
                                   (int)(255 * sc));
                    else
                        ui_label_c((int)cx, ly, names[c], px, 215 + (int)(40 * pe), 215 + (int)(40 * pe), 215 + (int)(40 * pe),
                                   (int)((165 + 90 * pe) * sc));
                }''')

# ---------------------------------------------------------------- 6. convex tiles in the video queue
patch("convex video tiles", r'''            tl[e] = av_clipd(d, -1.0, 1.0) * (0.45 + 1.1 * fmod(i * 0.61803398875 + 0.3, 1.0));    /* each cover turns a little differently */''',
      r'''            tl[e] = av_clipd(d, -1.0, 1.0) * (0.45 + 1.1 * fmod(i * 0.61803398875 + 0.3, 1.0));    /* each cover turns a little differently */
            if (ui_flow_vmode)
                tl[e] = -tl[e];                 /* over a video the row is convex: the edge nearest the middle is the tall one, like the outside of a cylinder */''')

# ---------------------------------------------------------------- 7. the old rounded bar glass is not used any more
patch("old bar glass is unused", r'''static void ui_glass_dark(const SDL_Rect *t, int r)
''', r'''static av_unused void ui_glass_dark(const SDL_Rect *t, int r)
''')

if fails:
    print("\n%d edit(s) failed. Nothing written." % len(fails))
    sys.exit(1)
open(PATH, "w").write(src)
print("\nUpdate 36 written to " + PATH)
