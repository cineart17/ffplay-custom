#!/usr/bin/env python3
# Update 46 for ffplay-custom (on top of patch_queue_v45.py).
#   * Preferences has sliders, in the seek bar's style (a lighter shade of the bar color), with the value at the end:
#       Volume step (1 to 16), Hide bars after (0.5 to 30 s, finer at the short end), Crossfade (Off to 10 s),
#       Sleep timer (Off to 120 min; it follows the timer that is running), Glass tint (0 to 100%), Roundness (0 to 100%, 0 = square).
#     Drag a slider, or rest the mouse on its row and use the wheel, a two finger swipe up or down (the same direction as the volume
#     swipe), or the Up/Down/Left/Right keys. Crossfade moves in whole seconds (that is what the player keeps).
#   * Glass tint: how strong the smoked veil under the glass is (panels, menus, the bar). 50% is how it has been.
#   * Roundness: the corner radius of panels, menus, tiles, buttons and bars together. 100% is how it has been, 0 makes everything
#     square. Both are seen live in the Preferences panel while a slider moves, and are kept in settings.conf
#     (glass_tint = 50, roundness = 100).
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v45.py. Writes the file only if every edit matches.
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


if "ui_sl_draw" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_pk_cm_open" not in src:
    print("Apply patch_queue_v45.py first. Nothing written.")
    sys.exit(1)

# ---------------------------------------------------------------- the two new settings
patch("tint and roundness settings", r'''static int     cfg_crisp = 1;               /* 1 = letters placed with sub-pixel accuracy (v45) */''',
      r'''static int     cfg_crisp = 1;               /* 1 = letters placed with sub-pixel accuracy (v45) */
static int     cfg_tint = 50;               /* v46: how strong the smoked veil under the glass is, 0 to 100 (50 = as it was) */
static int     cfg_round = 100;             /* v46: how round the corners are, 0 to 100 (100 = as they were, 0 = square) */
static double  ui_round_k(void)
{
    return av_clipd(cfg_round, 0, 100) / 100.0;
}''')
patch("tint and roundness read", r'''        else if (sscanf(line, " crisp_text = %d", &n) == 1)
            cfg_crisp = (n != 0);''', r'''        else if (sscanf(line, " crisp_text = %d", &n) == 1)
            cfg_crisp = (n != 0);
        else if (sscanf(line, " glass_tint = %d", &n) == 1)
            cfg_tint = av_clip(n, 0, 100);
        else if (sscanf(line, " roundness = %d", &n) == 1)
            cfg_round = av_clip(n, 0, 100);''')
patch("tint and roundness written", r'''crisp_text = %d\n\n", cfg_crisp);''', r'''crisp_text = %d\n\n", cfg_crisp);
    fprintf(f, "# How strong the smoked veil under the glass is (0 to 100), and how round the corners are (0 = square, 100 = as before)\nglass_tint = %d\nroundness = %d\n\n", cfg_tint, cfg_round);''')

# ---------------------------------------------------------------- the glass tint and the corners
patch("tint of the panels", r'''22 + cfg_bar_r / 16, 24 + cfg_bar_g / 16, 28 + cfg_bar_b / 16, 130, 1);''',
      r'''22 + cfg_bar_r / 16, 24 + cfg_bar_g / 16, 28 + cfg_bar_b / 16, 30 + 2 * cfg_tint, 1);''')
patch("tint of the dark glass", r'''    ui_liquid(t, r, 10, 12, 16, 105, 0);''', r'''    ui_liquid(t, r, 10, 12, 16, 55 + cfg_tint, 0);''')
patch("tint of the bar", r'''    ui_liquid(t, 0, 8, 10, 14, 125, 0);''', r'''    ui_liquid(t, 0, 8, 10, 14, 75 + cfg_tint, 0);''')
patch("roundness of the pills", r'''static void ui_pill(const SDL_Rect *t)
{
    double rad = t->h / 2.0;
    int row;

    for (row = 0; row < t->h; row++) {
        double dy = row + 0.5 - rad;                      /* row center to bar center */
        int inset = (int)(rad - sqrt(rad * rad - dy * dy) + 0.5);
        SDL_Rect line = { t->x + inset, t->y + row, t->w - 2 * inset, 1 };

        if (line.w > 0)
            SDL_RenderFillRect(renderer, &line);
    }
}''', r'''static void ui_pill(const SDL_Rect *t)
{
    double rad = FFMIN(t->h, t->w) / 2.0 * ui_round_k();    /* v46: a full pill at 100%, a plain rectangle at 0 */
    int row;

    for (row = 0; row < t->h; row++) {
        double e = FFMIN(row + 0.5, t->h - row - 0.5);    /* row center to the nearest top or bottom edge */
        int inset = e < rad ? (int)(rad - sqrt(rad * rad - (rad - e) * (rad - e)) + 0.5) : 0;
        SDL_Rect line = { t->x + inset, t->y + row, t->w - 2 * inset, 1 };

        if (line.w > 0)
            SDL_RenderFillRect(renderer, &line);
    }
}''')
patch("roundness of the glass", r'''    r = FFMIN(r, FFMIN(t->w, t->h) / 2);
    if (shadow)''', r'''    r = (int)(FFMIN(r, FFMIN(t->w, t->h) / 2) * ui_round_k() + 0.5);       /* v46 */
    if (shadow)''')
patch("roundness of the tiles", r'''    rr = av_clip(rr, 0, FFMIN(t->w, t->h) / 2);
    c.r = (Uint8)md;''', r'''    rr = (int)(av_clip(rr, 0, FFMIN(t->w, t->h) / 2) * ui_round_k() + 0.5);     /* v46 */
    c.r = (Uint8)md;''')

# ---------------------------------------------------------------- the rows of Preferences
patch("more rows", r'''#define UI_PREF_ROWS 7''', r'''#define UI_PREF_ROWS 11''')
patch("names of the rows", r'''static const char *ui_pref_name[UI_PREF_ROWS] = {
    "Volume step", "Hide bars after", "Start fullscreen",
    "Bar color", "Remember volume", "Quit when the queue ends", "Scroll action"
};''', r'''static const char *ui_pref_name[UI_PREF_ROWS] = {
    "Volume step", "Hide bars after", "Start fullscreen",
    "Bar color", "Remember volume", "Quit when the queue ends", "Scroll action",
    "Crossfade", "Sleep timer", "Glass tint", "Roundness"
};''')
patch("order and kind of the rows", r'''static const int ui_hide_steps[] = { 1, 2, 3, 4, 5, 8, 10, 15, 30 };
''', r'''static const int ui_hide_steps[] = { 1, 2, 3, 4, 5, 8, 10, 15, 30 };

/* v46: the rows are numbered as they were (and the four new ones 7 to 10); this is the order they are shown in, top to bottom */
static const int ui_pref_map[UI_PREF_ROWS] = { 0, 1, 7, 8, 2, 3, 4, 5, 6, 9, 10 };

static int ui_pref_pos(int row)
{
    int i;

    for (i = 0; i < UI_PREF_ROWS; i++)
        if (ui_pref_map[i] == row)
            return i;
    return 0;
}

/* The rows that are a slider and not a list of choices */
static int ui_pref_slider(int row)
{
    return row == 0 || row == 1 || row == 7 || row == 8 || row == 9 || row == 10;
}
static void ui_sleep_set_minutes(int m);
''')
patch("sliders have no choices", r'''    int n = 0, i, b = 0;

    *sel = -1;
    row++;''', r'''    int n = 0, i, b = 0;

    *sel = -1;
    if (ui_pref_slider(row))
        return 0;                               /* v46: a slider has no list */
    row++;''')
patch("choices are where the row is shown", r'''int n, i, sel, px, cy = p->y + UI_PREF_HEAD + row * UI_PREF_ROW + UI_PREF_ROW / 2;''',
      r'''int n, i, sel, px, cy = p->y + UI_PREF_HEAD + ui_pref_pos(row) * UI_PREF_ROW + UI_PREF_ROW / 2;''')

patch("sliders do not open into choices", r'''        double tgt = i == ui_prefs_hover ? 1.0 : 0.0;''', r'''        double tgt = (i == ui_prefs_hover && !ui_pref_slider(i)) ? 1.0 : 0.0;''')
patch("the panel does not grow for a slider", r'''    if (ui_prefs_hover >= 0 && ui_prefs_hover < UI_PREF_ROWS)
        wt = FFMAX(wt, ui_pref_need_w(ui_prefs_hover));''', r'''    if (ui_prefs_hover >= 0 && ui_prefs_hover < UI_PREF_ROWS && !ui_pref_slider(ui_prefs_hover))
        wt = FFMAX(wt, ui_pref_need_w(ui_prefs_hover));''')
patch("rows are drawn in their order", r'''        cy = p.y + UI_PREF_HEAD + i * UI_PREF_ROW + UI_PREF_ROW / 2;
        e = ui_pref_open[i];''', r'''        cy = p.y + UI_PREF_HEAD + ui_pref_pos(i) * UI_PREF_ROW + UI_PREF_ROW / 2;
        e = ui_pref_open[i];''')
patch("icons of the rows", r'''            static const int pic[UI_PREF_ROWS] = { UI_IC_VOLUME, UI_IC_EYE, UI_IC_EXPAND, UI_IC_DROP,
                                                   UI_IC_BOOKMARK, UI_IC_EXIT, UI_IC_MOUSE };''', r'''            static const int pic[UI_PREF_ROWS] = { UI_IC_VOLUME, UI_IC_EYE, UI_IC_EXPAND, UI_IC_DROP,
                                                   UI_IC_BOOKMARK, UI_IC_EXIT, UI_IC_MOUSE, UI_IC_FADE, UI_IC_MOON,
                                                   UI_IC_DROP, UI_IC_EXPAND };''')
patch("a slider row is drawn", r'''                 i == ui_prefs_hover ? 255 : 210);      /* the name nudges a little to make room, like a volume bar coming in from the side */
''', r'''                 i == ui_prefs_hover ? 255 : 210);      /* the name nudges a little to make room, like a volume bar coming in from the side */
        if (ui_pref_slider(i)) {                /* v46 */
            ui_sl_draw(&p, i, cy);
            continue;
        }
''')
patch("hint", r'''"Move the mouse onto a setting to see its choices.  Esc closes."''', r'''"Hover for the choices. Sliders: drag, scroll or arrows. Esc closes."''')
patch("rows are found by where they are shown", r'''    if (row >= UI_PREF_ROWS || x < p.x || x >= p.x + p.w)
        row = -1;
    ui_wake();
    ui_prefs_mx = x;''', r'''    if (row >= UI_PREF_ROWS || x < p.x || x >= p.x + p.w)
        row = -1;
    if (row >= 0)
        row = ui_pref_map[row];                 /* v46: the row number as it is kept */
    ui_wake();
    ui_prefs_mx = x;''')
patch("a press on a slider", r'''        } else if (row >= 0) {
            int c = ui_pref_chip_at(row, &p, x, y);

            if (c >= 0)
                ui_pref_choose(row, c);         /* one of the choices of the row */
        }''', r'''        } else if (row >= 0 && ui_pref_slider(row)) {
            if (ui_sl_hit(&p, row, x)) {        /* v46: the slider takes the mouse until the button is let go */
                ui_pref_drag = row;
                SDL_CaptureMouse(SDL_TRUE);
                ui_sl_drag_to(&p, row, x);
            }
        } else if (row >= 0) {
            int c = ui_pref_chip_at(row, &p, x, y);

            if (c >= 0)
                ui_pref_choose(row, c);         /* one of the choices of the row */
        }''')

# ---------------------------------------------------------------- the sliders themselves
patch("the sliders", r'''static SDL_Rect ui_prefs_rect(int ww, int wh)
{''', r'''/* ----- v46: the sliders. Each has a range, what it shows, and how it is put into the setting ----- */
static int ui_pref_drag = -1;           /* the slider that is being dragged (-1 = none) */

static double ui_sl_lo(int r)
{
    return r == 1 ? 0.5 : r == 0 ? 1.0 : 0.0;
}

static double ui_sl_hi(int r)
{
    return r == 0 ? 16.0 : r == 1 ? 30.0 : r == 7 ? 10.0 : r == 8 ? 120.0 : 100.0;
}

static double ui_sl_get(int r)
{
    switch (r) {
    case 0: return cfg_vol_step;
    case 1: return cfg_hide_delay / 1000000.0;
    case 7: return cfg_crossfade;
    case 8: return q_sleep_end ? ceil((q_sleep_end - av_gettime_relative()) / 60000000.0) : 0.0;     /* the minutes left of the timer that runs */
    case 9: return cfg_tint;
    default: return cfg_round;
    }
}

static void ui_sl_put(int r, double v)
{
    v = av_clipd(v, ui_sl_lo(r), ui_sl_hi(r));
    switch (r) {
    case 0: cfg_vol_step = (int)(v + 0.5); break;
    case 1:
        v = v < 3.0 ? floor(v * 10.0 + 0.5) / 10.0 : v < 10.0 ? floor(v * 2.0 + 0.5) / 2.0 : floor(v + 0.5);
        cfg_hide_delay = (int64_t)(v * 1000000.0);
        break;
    case 7: cfg_crossfade = (int)(v + 0.5); break;
    case 8: ui_sleep_set_minutes((int)(v + 0.5)); break;
    case 9: cfg_tint = (int)(v + 0.5); break;
    default: cfg_round = (int)(v + 0.5); break;
    }
}

static double ui_sl_t(int r)
{
    double v = av_clipd(ui_sl_get(r), ui_sl_lo(r), ui_sl_hi(r)), lo = ui_sl_lo(r), hi = ui_sl_hi(r);

    return r == 1 ? log(v / lo) / log(hi / lo) : (v - lo) / (hi - lo);      /* the hiding time is finer at the short end */
}

static void ui_sl_text(int r, char *out, size_t size)
{
    switch (r) {
    case 0: snprintf(out, size, "%d", cfg_vol_step); break;
    case 1: snprintf(out, size, "%g s", cfg_hide_delay / 1000000.0); break;
    case 7:
        if (cfg_crossfade)
            snprintf(out, size, "%d s", cfg_crossfade);
        else
            snprintf(out, size, "Off");
        break;
    case 8:
        if (q_sleep_end)
            snprintf(out, size, "%d min", (int)ui_sl_get(8));
        else
            snprintf(out, size, q_sleep_item ? "Track end" : "Off");
        break;
    case 9: snprintf(out, size, "%d%%", cfg_tint); break;
    default:
        if (cfg_round)
            snprintf(out, size, "%d%%", cfg_round);
        else
            snprintf(out, size, "Square");
        break;
    }
}

/* One step of the arrow keys and of a notch of the wheel */
static void ui_sl_nudge(int r, int dir)
{
    double v = ui_sl_get(r), st;

    st = r == 1 ? (v < 3.0 - 0.01 || (dir < 0 && v <= 3.0 + 0.01) ? 0.1 : v < 10.0 - 0.01 || (dir < 0 && v <= 10.0 + 0.01) ? 0.5 : 1.0) :
         r == 8 ? 5.0 : r >= 9 ? 5.0 : 1.0;
    if (r == 8 && dir < 0 && v <= 5.0)
        v = 5.0;                                /* down from 5 minutes: off */
    ui_sl_put(r, v + dir * st);
    settings_save();
}

/* Where the slider of a row is: the track from x0 to x1, the value after it. The same column for every row. */
static void ui_sl_geom(const SDL_Rect *p, int *x0, int *x1, int *xr)
{
    int vw = ui_text_width("120 min", ui_pr_px) + 6;

    *xr = p->x + p->w - ui_pr_mg;
    *x0 = p->x + ui_pr_mg + UI_PREF_ICW + ui_text_width("Hide bars after", ui_pr_px) + 30;
    *x1 = *xr - vw - 18;
    if (*x1 - *x0 < 70)
        *x0 = *x1 - 70;
}

static int ui_sl_hit(const SDL_Rect *p, int r, int x)
{
    int x0, x1, xr;

    ui_sl_geom(p, &x0, &x1, &xr);
    return x >= x0 - 12 && x <= x1 + 12;
}

static void ui_sl_drag_to(const SDL_Rect *p, int r, int x)
{
    int x0, x1, xr;
    double t, lo = ui_sl_lo(r), hi = ui_sl_hi(r);

    ui_sl_geom(p, &x0, &x1, &xr);
    t = av_clipd((double)(x - x0) / FFMAX(x1 - x0, 1), 0.0, 1.0);
    ui_sl_put(r, r == 1 ? lo * pow(hi / lo, t) : lo + (hi - lo) * t);
}

static void ui_sl_draw(const SDL_Rect *p, int r, int cy)
{
    SDL_Rect tr, fill, knob;
    char text[32];
    int x0, x1, xr, d, hot = r == ui_prefs_hover || r == ui_pref_drag;
    double t = av_clipd(ui_sl_t(r), 0.0, 1.0);

    ui_sl_geom(p, &x0, &x1, &xr);
    tr.x = x0;
    tr.y = cy - 3;
    tr.w = x1 - x0;
    tr.h = 6;
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 45);
    ui_pill(&tr);                               /* the track, as on the seek bar */
    fill = tr;
    fill.w = FFMAX((int)(tr.w * t), tr.h);
    SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 60, 0, 255), av_clip(cfg_bar_g + 60, 0, 255), av_clip(cfg_bar_b + 60, 0, 255),
                           hot ? 235 : 200);
    ui_pill(&fill);                             /* the part before the knob: a lighter shade of the bar color */
    d = r == ui_pref_drag ? 20 : hot ? 17 : 14;
    knob.w = knob.h = d;
    knob.x = x0 + (int)((x1 - x0) * t) - d / 2;
    knob.y = cy - d / 2;
    SDL_SetRenderDrawColor(renderer, 245, 245, 245, 245);
    ui_pill(&knob);
    ui_sl_text(r, text, sizeof(text));
    ui_label(xr - ui_text_width(text, ui_pr_px), cy, text, ui_pr_px, hot ? 255 : 225, hot ? 255 : 225, hot ? 255 : 225, 255);
    if (r == 8 && q_sleep_end)
        ui_prefs_anim = 1;                      /* the timer runs: the knob follows it */
}

static SDL_Rect ui_prefs_rect(int ww, int wh)
{''')

patch("keys, the wheel and the end of a drag", r'''/* Draw one whole frame with frosted glass: used while a menu or the Preferences panel is up,''', r'''/* v46: while the panel is open, the wheel, a two finger swipe and the arrow keys move the slider the mouse is on, and a drag that
   goes outside the panel goes on. Returns 1 if the event was used. */
static int ui_prefs_event(VideoState *is, SDL_Event *ev)
{
    static double acc = 0.0;
    int r = ui_prefs_hover;
    SDL_Rect p;
    int ww, wh;

    if (!ui_prefs_open) {
        ui_pref_drag = -1;
        return 0;
    }
    SDL_GetWindowSize(window, &ww, &wh);
    p = ui_prefs_rect(ww, wh);
    if (ev->type == SDL_MOUSEMOTION && ui_pref_drag >= 0) {
        ui_sl_drag_to(&p, ui_pref_drag, ev->motion.x);
        ui_wake();
        if (is)
            is->force_refresh = 1;
        return 1;
    }
    if (ev->type == SDL_MOUSEBUTTONUP && ui_pref_drag >= 0) {
        ui_pref_drag = -1;
        SDL_CaptureMouse(SDL_FALSE);
        settings_save();
        if (is)
            is->force_refresh = 1;
        return 1;
    }
    if (ev->type == SDL_MOUSEWHEEL) {
        double ay = ev->wheel.preciseY;
        int steps;

        if (ev->wheel.direction == SDL_MOUSEWHEEL_FLIPPED)
            ay = -ay;
        if (r >= 0 && ui_pref_slider(r)) {
            if (ay * acc < 0.0)
                acc = 0.0;
            acc += ay;
            steps = (int)acc;
            if (steps) {
                acc -= steps;
                ui_sl_nudge(r, steps > 0 ? -1 : 1);     /* the same way round as the volume swipe: up = more */
            }
        }
        ui_wake();
        if (is)
            is->force_refresh = 1;
        return 1;                               /* the panel is up: nothing else uses the wheel */
    }
    if (ev->type == SDL_KEYDOWN && r >= 0 && ui_pref_slider(r)) {
        SDL_Keycode k = ev->key.keysym.sym;
        int dir = (k == SDLK_UP || k == SDLK_RIGHT || k == SDLK_PAGEUP) ? 1 : (k == SDLK_DOWN || k == SDLK_LEFT || k == SDLK_PAGEDOWN) ? -1 : 0;

        if (dir) {
            int n = (k == SDLK_PAGEUP || k == SDLK_PAGEDOWN) ? 4 : 1;

            while (n--)
                ui_sl_nudge(r, dir);
            ui_wake();
            if (is)
                is->force_refresh = 1;
            return 1;
        }
    }
    return 0;
}

/* Draw one whole frame with frosted glass: used while a menu or the Preferences panel is up,''')

patch("sleep timer from a slider", r'''/* What the sleep row says while it is closed */''', r'''/* v46: the sleep timer for any number of minutes (0 = off); the sound fades out over its last 20 seconds, as for the others */
static void ui_sleep_set_minutes(int m)
{
    static const int minutes[6] = { 0, 0, 5, 10, 30, 60 };
    int i, best = 2;

    if (m <= 0) {
        ui_sleep_choose(0);
        return;
    }
    q_sleep_item = NULL;
    q_sleep_end = av_gettime_relative() + (int64_t)m * 60 * 1000000;
    ui_sleep_gain = 1.0f;
    for (i = 3; i <= 5; i++)                    /* the queue panel marks the nearest of its own choices */
        if (abs(minutes[i] - m) < abs(minutes[best] - m))
            best = i;
    ui_sleep_sel = best;
}

/* What the sleep row says while it is closed */''')

patch("prefs events (playing)", r'''        if (ui_pk_event(cur_stream, &event))    /* v44: the picker uses the keys, the typing and the wheel while it is open */
            continue;''', r'''        if (ui_pk_event(cur_stream, &event))    /* v44: the picker uses the keys, the typing and the wheel while it is open */
            continue;
        if (ui_prefs_open && ui_prefs_event(cur_stream, &event))        /* v46: the sliders */
            continue;''')
patch("prefs events (idle)", r'''            if (ev.type != SDL_QUIT && ui_pk_event(NULL, &ev))      /* v44 */
                continue;''', r'''            if (ev.type != SDL_QUIT && ui_pk_event(NULL, &ev))      /* v44 */
                continue;
            if (ev.type != SDL_QUIT && ui_prefs_open && ui_prefs_event(NULL, &ev))      /* v46 */
                continue;''')

if fails:
    print("\n%d edit(s) failed. Nothing written." % len(fails))
    sys.exit(1)
open(PATH, "w").write(src)
print("\nAll edits applied to " + PATH)
