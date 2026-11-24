#!/usr/bin/env python3
# Update 48 for ffplay-custom (on top of patch_queue_v47.py).
#   * Crossfade and Sleep timer in the queue menu follow the Preferences design: a slider each (the track and its fill in a lighter
#     shade of the bar color, no knob), the value at the end, no cascade. The name nudges in from the left margin while the mouse
#     is on the row. Drag the slider, or use the wheel while the mouse is on its row (the same way round as in Preferences).
#     Crossfade: Off to 10 s. Sleep timer: Off, End of track, 5, 10, 15, 30, 45, 60, 90, 120 min. The timer that runs moves the fill.
#   * File picker, right click: "Play next" (for a folder, "Play folder next"). The item goes right after the one that plays now,
#     and several in a row play in the order you chose them. The picker stays open, like for "Add to queue".
#   * File picker: the wheel and the touchpad scroll glide, like the list queue.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v47.py. Writes the file only if every edit matches.
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


def patch_between(name, start, end, new):
    """Replace everything from start (included) up to end (kept) with new. Both markers must be there exactly once."""
    global src
    if src.count(start) != 1 or src.count(end) != 1:
        print("FAILED: %s (markers matched %d and %d times)" % (name, src.count(start), src.count(end)))
        fails.append(name)
        return
    a = src.index(start)
    b = src.index(end)
    if b <= a:
        print("FAILED: %s (markers in the wrong order)" % name)
        fails.append(name)
        return
    src = src[:a] + new + src[b:]
    print("ok: " + name)


if "ui_qs_stop_cur" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "UI_PREF_NUDGE" not in src:
    print("Apply patch_queue_v47.py first. Nothing written.")
    sys.exit(1)

# ================================================================ Queue menu: Crossfade and Sleep timer as sliders
patch("queue sliders: the helpers", r'''/* h:mm:ss, or m:ss when the hours are not needed */''', r'''/* ----- v48: Crossfade and Sleep timer in the queue panel are sliders, like the ones in Preferences -----
   No cascade any more: the track and its fill (a lighter shade of the bar color), the value at the end, and the name nudges in
   from the left margin while the mouse is on the row. The sleep timer slider has its own stops: Off, End of track, then minutes. */
#define UI_QS_N 10
static const int ui_qs_min[UI_QS_N] = { 0, 0, 5, 10, 15, 30, 45, 60, 90, 120 };
static int ui_qs_drag = -1;             /* the slider being dragged: 0 = crossfade, 1 = sleep timer, -1 = none */
static double ui_qs_nud[2];             /* 0 to 1: how far the name of each row has moved for the mouse on it */

/* The stop the sleep timer is at: it follows the timer that runs (the nearest stop to the minutes left) */
static int ui_qs_stop_cur(void)
{
    int i, best = 2, left;

    if (q_sleep_end) {
        left = (int)((q_sleep_end - av_gettime_relative() + 59999999) / 60000000);
        for (i = 3; i < UI_QS_N; i++)
            if (abs(ui_qs_min[i] - left) < abs(ui_qs_min[best] - left))
                best = i;
        return best;
    }
    return q_sleep_item ? 1 : 0;
}

static void ui_qs_set_stop(int s)
{
    s = av_clip(s, 0, UI_QS_N - 1);
    if (s == ui_qs_stop_cur())
        return;
    if (s < 2)
        ui_sleep_choose(s);
    else
        ui_sleep_set_minutes(ui_qs_min[s]);
}

/* Where the sliders are: the track from x0 to x1, the value after it. The same column for both rows. */
static void ui_qs_geom(const SDL_Rect *p, int *x0, int *x1, int *xr)
{
    *xr = p->x + p->w - 20;
    *x1 = *xr - ui_text_width("119:59 left", 18) - 18;
    *x0 = p->x + 20 + UI_Q_ICW + ui_text_width("Sleep timer", 18) + 22;
    if (*x1 - *x0 < 60)
        *x0 = *x1 - 60;
}

static int ui_qs_hit(const SDL_Rect *p, int x)
{
    int x0, x1, xr;

    ui_qs_geom(p, &x0, &x1, &xr);
    return x >= x0 - 12 && x <= x1 + 12;
}

static void ui_qs_drag_to(const SDL_Rect *p, int row, int x)
{
    int x0, x1, xr;
    double t;

    ui_qs_geom(p, &x0, &x1, &xr);
    t = av_clipd((double)(x - x0) / FFMAX(x1 - x0, 1), 0.0, 1.0);
    if (row == 0)
        cfg_crossfade = av_clip((int)(t * 10.0 + 0.5), 0, 10);
    else
        ui_qs_set_stop((int)(t * (UI_QS_N - 1) + 0.5));
}

static void ui_qs_nudge(int row, int dir)
{
    if (row == 0)
        cfg_crossfade = av_clip(cfg_crossfade + dir, 0, 10);
    else
        ui_qs_set_stop(ui_qs_stop_cur() + dir);
    settings_save();
}

/* h:mm:ss, or m:ss when the hours are not needed */''')

patch_between("queue sliders: drawn", r'''    /* crossfade: its name stays; the choices squeeze in on the right of it while the mouse is on the row */''',
              r'''    /* the counter: which item, and how far through the whole queue. Quiet on purpose. */''', r'''    /* v48: crossfade and sleep timer: a slider each, with the name nudging in from the left margin while the mouse is on the row */
    {
        static int64_t qs_last = 0;
        int64_t tq = av_gettime_relative();
        double dtq = tq - qs_last > 100000 ? 0.016 : (tq - qs_last) / 1000000.0;
        int row;

        qs_last = tq;
        ui_xf_anim = 0;
        ui_chip_anim = 0;
        for (row = 0; row < 2; row++) {
            SDL_Rect tr, fill;
            int rcy = fy + (row ? 66 : 26), x0, x1, xr, mv = 0, nudge;
            int hot = row == ui_qs_drag || (row ? hk == UI_Q_SLEEP : hk == UI_Q_XFROW);
            double ne = ui_pop_step(&ui_qs_nud[row], hot, dtq, &mv), t;

            if (mv)
                ui_xf_anim = 1;
            nudge = (int)(UI_PREF_NUDGE * ne + 0.5);
            ui_icon(row ? UI_IC_MOON : UI_IC_FADE, p.x + 20 + nudge, rcy, 18, 240, 240, 240, hot ? 255 : 190);
            ui_label(p.x + 20 + UI_Q_ICW + nudge, rcy, row ? "Sleep timer" : "Crossfade", 18, 240, 240, 240, hot ? 255 : 210);
            ui_qs_geom(&p, &x0, &x1, &xr);
            t = row ? ui_qs_stop_cur() / (double)(UI_QS_N - 1) : cfg_crossfade / 10.0;
            tr.x = x0;
            tr.h = hot ? 8 : 6;
            tr.y = rcy - tr.h / 2;
            tr.w = x1 - x0;
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, (int)(45 * ui_fade));
            ui_pill(&tr);
            fill = tr;
            fill.w = t > 0.0 ? FFMAX((int)(tr.w * t), tr.h) : 0;
            SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 60, 0, 255), av_clip(cfg_bar_g + 60, 0, 255),
                                   av_clip(cfg_bar_b + 60, 0, 255), (int)((hot ? 235 : 200) * ui_fade));
            if (fill.w > 0)
                ui_pill(&fill);
            if (row == 0) {
                if (cfg_crossfade)
                    snprintf(text, sizeof(text), "%d s", cfg_crossfade);
                else
                    snprintf(text, sizeof(text), "Off");
            } else {
                ui_sleep_text(text, sizeof(text));
                if (q_sleep_end)
                    ui_chip_anim = 1;           /* the timer runs: the fill follows it */
            }
            ui_label(xr - ui_text_width(text, 18), rcy, text, 18, hot ? 255 : 225, hot ? 255 : 225, hot ? 255 : 225, 255);
        }
    }

''')
patch("queue sliders: sel", r'''    int drop = 0, i, item, cy, lit, hk = ui_q_hover_kind, fy, marker, sel;''',
      r'''    int drop = 0, i, item, cy, lit, hk = ui_q_hover_kind, fy, marker;''')

patch("queue sliders: hit test variables", r'''    int fy = top + ui_q_visible(wh) * UI_Q_ROW, i;
    SDL_Rect chip[8];
''', r'''    int fy = top + ui_q_visible(wh) * UI_Q_ROW;
''')
patch_between("queue sliders: hit test", r'''        if (y >= fy + 6 && y < fy + 46) {       /* crossfade: the choices are there while the mouse is on the row */''',
              r'''    slot = (y - top) / UI_Q_ROW;''', r'''        if (y >= fy + 6 && y < fy + 46)         /* crossfade */
            return UI_Q_XFROW;
        if (y >= fy + 46 && y < fy + 86)        /* sleep timer */
            return UI_Q_SLEEP;
        return UI_Q_NONE;
    }
''')
patch_between("queue sliders: clicks", r'''    } else if (kind == UI_Q_XF_DEC || kind == UI_Q_XF_INC) {''', r'''    } else if (kind == UI_Q_DEL) {''', r'''    } else if (kind == UI_Q_XFROW || kind == UI_Q_SLEEP) {
        if (ui_qs_hit(&p, x)) {     /* v48: the slider takes the mouse until the button is let go */
            ui_qs_drag = kind == UI_Q_SLEEP;
            SDL_CaptureMouse(SDL_TRUE);
            ui_qs_drag_to(&p, ui_qs_drag, x);
        }
''')
patch("queue sliders: drag follows the mouse", r'''    if (ui_prefs_open)
        return ui_prefs_mouse(is, ev);
''', r'''    if (ui_prefs_open)
        return ui_prefs_mouse(is, ev);
    if (ui_qs_drag >= 0 && ev->type == SDL_MOUSEMOTION) {       /* v48: a slider of the queue panel is being dragged */
        SDL_GetWindowSize(window, &ww, &wh);
        p = ui_q_rect(ww, wh);
        ui_qs_drag_to(&p, ui_qs_drag, ev->motion.x);
        ui_wake();
        if (is)
            is->force_refresh = 1;
        return 1;
    }
''')
patch("queue sliders: let go", r'''static int ui_queue_release(SDL_Event *ev)
{
    SDL_Rect p;
    int ww, wh;
''', r'''static int ui_queue_release(SDL_Event *ev)
{
    SDL_Rect p;
    int ww, wh;

    if (ui_qs_drag >= 0 && ev->button.button == SDL_BUTTON_LEFT) {      /* v48: a slider was let go */
        ui_qs_drag = -1;
        SDL_CaptureMouse(SDL_FALSE);
        settings_save();
        return 1;
    }
''')
patch("queue sliders: wheel", r'''    SDL_GetWindowSize(window, &ww, &wh);
    ui_q_scroll = av_clip(ui_q_scroll - ev->wheel.y, 0, FFMAX(q_count - ui_q_visible(wh), 0));
    return 1;''', r'''    SDL_GetWindowSize(window, &ww, &wh);
    {                                           /* v48: on a slider row the wheel moves the slider, as in Preferences */
        SDL_Rect p = ui_q_rect(ww, wh);
        int mx, my, item, kind;

        SDL_GetMouseState(&mx, &my);
        kind = ui_q_hit(&p, wh, mx, my, &item);
        if (kind == UI_Q_XFROW || kind == UI_Q_SLEEP) {
            int y = ev->wheel.direction == SDL_MOUSEWHEEL_FLIPPED ? -ev->wheel.y : ev->wheel.y;

            ui_qs_nudge(kind == UI_Q_SLEEP, y > 0 ? -1 : 1);       /* the same way round as in Preferences */
            return 1;
        }
    }
    ui_q_scroll = av_clip(ui_q_scroll - ev->wheel.y, 0, FFMAX(q_count - ui_q_visible(wh), 0));
    return 1;''')

# ================================================================ File picker: Play next, and a wheel that glides
patch("picker: play next, in the inbox", r'''        if (line[0] == 'o' || line[0] == 'a')
            queue_add_path(line + 1);
    }
    fclose(f);
    unlink(work);''', r'''        if (line[0] == 'o' || line[0] == 'a') {
            queue_add_path(line + 1);
        } else if (line[0] == 'n') {            /* v48: play next: it goes right after the item that plays now */
            static int pn_pos = -2, pn_cnt = 0;
            int before = q_count, k, base;

            queue_add_path(line + 1);
            if (q_pos != pn_pos) {              /* the item changed: a new run of "next" items starts */
                pn_pos = q_pos;
                pn_cnt = 0;
            }
            base = FFMAX(q_pos, -1) + 1 + pn_cnt;   /* after the ones already put there, so they play in the order chosen */
            for (k = 0; k < q_count - before; k++)
                queue_move(before + k, FFMIN(base + k, before + k));
            pn_cnt += q_count - before;
        }
    }
    fclose(f);
    unlink(work);''')
patch("picker: the actions", r'''enum { UI_PK_A_PLAY, UI_PK_A_ADD, UI_PK_A_ENTER };''', r'''enum { UI_PK_A_PLAY, UI_PK_A_ADD, UI_PK_A_ENTER, UI_PK_A_NEXT };''')
patch("picker: menu arrays", r'''static int ui_pk_cm_act[3];
static char ui_pk_cm_lab[3][24];''', r'''static int ui_pk_cm_act[4];
static char ui_pk_cm_lab[4][24];''')
patch("picker: menu rows", r'''        snprintf(ui_pk_cm_lab[1], 24, "Play folder");
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
    }''', r'''        snprintf(ui_pk_cm_lab[1], 24, "Play folder");
        ui_pk_cm_act[1] = UI_PK_A_PLAY;
        snprintf(ui_pk_cm_lab[2], 24, "Play folder next");
        ui_pk_cm_act[2] = UI_PK_A_NEXT;
        snprintf(ui_pk_cm_lab[3], 24, "Add folder to queue");
        ui_pk_cm_act[3] = UI_PK_A_ADD;
        ui_pk_cm_n = 4;
    } else {
        snprintf(ui_pk_cm_lab[0], 24, "Play now");
        ui_pk_cm_act[0] = UI_PK_A_PLAY;
        snprintf(ui_pk_cm_lab[1], 24, "Play next");
        ui_pk_cm_act[1] = UI_PK_A_NEXT;
        snprintf(ui_pk_cm_lab[2], 24, "Add to queue");
        ui_pk_cm_act[2] = UI_PK_A_ADD;
        ui_pk_cm_n = 3;
    }''')
patch("picker: play next does it", r'''    } else if (act == UI_PK_A_PLAY) {
        ui_pk_send(is, 'o', path);
        ui_pk_close(is);
    } else {''', r'''    } else if (act == UI_PK_A_PLAY) {
        ui_pk_send(is, 'o', path);
        ui_pk_close(is);
    } else if (act == UI_PK_A_NEXT) {           /* v48: the picker stays open, like for Add */
        ui_pk_send(is, 'n', path);
        snprintf(ui_pk_note, sizeof(ui_pk_note), "Plays next: %.120s", ui_pk_e[e].name);
        ui_pk_note_until = av_gettime_relative() + 2500000;
    } else {''')
patch("picker: scroll goal", r'''static double ui_pk_sc = 0.0;                   /* scrolled, in pixels */''',
      r'''static double ui_pk_sc = 0.0;                   /* scrolled, in pixels */
static double ui_pk_goal = -1.0;                /* v48: where the wheel is taking the list (the list glides there); -1 = nowhere */''')
patch("picker: the list glides", r'''    ui_pk_layout(ww, wh, &L);
    ui_pk_clamp_scroll(&L);
    ui_glass(&L.p, 28);''', r'''    ui_pk_layout(ww, wh, &L);
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
    ui_glass(&L.p, 28);''')
patch("picker: the wheel sets the goal", r'''        ui_pk_sc -= dy * UI_PK_ROW * 2.5;
        ui_pk_clamp_scroll(&L);
        return 1;''', r'''        {
            double mx = FFMAX(0.0, ui_pk_nv * (double)UI_PK_ROW - L.list.h);
            double base = ui_pk_goal >= 0.0 ? ui_pk_goal : ui_pk_sc;

            ui_pk_goal = av_clipd(base - dy * UI_PK_ROW * 2.5, 0.0, mx);
        }
        return 1;''')

if fails:
    print("\n%d edit(s) FAILED. Nothing written." % len(fails))
    sys.exit(1)
open(PATH, "w").write(src)
print("\nDone: patch_queue_v48 applied.")
