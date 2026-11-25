#!/usr/bin/env python3
"""patch_queue_v53.py - small fixes on top of v52.

  - Ctrl+click in the file picker keeps the file you had clicked before: click one file, then Ctrl+click two more, and all three are
    selected (and play in that order). Before, the first click was left out.
  - The 11 "defined but not used" compiler warnings are gone (5 old functions and 7 old variables; one function only they used).

Run it from ~/build/ffmpeg-6.1.1:   python3 ~/build/patch_queue_v53.py [path/to/ffplay.c]
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
if "ui_pk_old_cur" in src:
    print("Already applied: v53 is in " + path)
    sys.exit(0)
if "ui_pk_send_selected" not in src:
    print("FAILED: apply patch_queue_v52.py first. Nothing written.")
    sys.exit(1)

failed = []


def edit(old, new, what):
    """Replace old with new, which must match exactly once."""
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED: %s (matched %d times)" % (what, n))
        failed.append(what)
        return
    src = src.replace(old, new)
    print("ok: " + what)


def between(start, end, new, what):
    """Put new in place of everything from start (kept) up to end (kept)."""
    global src
    if src.count(start) != 1 or src.count(end) != 1:
        print("FAILED: %s (markers matched %d and %d times)" % (what, src.count(start), src.count(end)))
        failed.append(what)
        return
    a = src.index(start) + len(start)
    b = src.index(end)
    if b < a:
        print("FAILED: %s (markers in the wrong order)" % what)
        failed.append(what)
        return
    src = src[:a] + new + src[b:]
    print("ok: " + what)


# ====================================================================================================== the 11 warnings
edit("""static double ui_chip_e = 0.0;          /* 0 to 1: how far the sleep timer row has changed into its choices */
static int64_t ui_chip_last = 0;
static double ui_xf_e = 0.0;            /* 0 to 1: how far the crossfade row has changed into its choices */
static double ui_xf_pop[7], ui_sl_pop[6];       /* 0 to 1: how far each choice has risen under the mouse */
static int64_t ui_xf_last = 0;
static int ui_xf_anim = 0;""", """static int ui_xf_anim = 0;""", "warnings: 6 old variables")
edit("""static int64_t ui_q_scroll_next = 0;       /* earliest time for the next scroll step while dragging */
""", "", "warnings: ui_q_scroll_next")
edit("""/* A soft arrowhead for the menus: a flat, fine chevron with a faint halo, pointing left (dir = -1) or
   right (dir = 1). cx, cy = its middle. a = how strong it is (0 to 255). */
static void ui_arrow(int cx, int cy, int dir, int a)
{
    int k, tail = cx - dir * 3, tip = cx + dir * 3, h = 5;

    a = av_clip((int)(a * ui_fade), 0, 255);       /* (a can arrive below 0 while the menu fades in) */
    for (k = -1; k <= 1; k++) {
        SDL_SetRenderDrawColor(renderer, 225, 225, 225, k ? a / 5 : a);
        SDL_RenderDrawLine(renderer, tail, cy - h + k, tip, cy + k);
        SDL_RenderDrawLine(renderer, tip, cy + k, tail, cy + h + k);
    }
}

""", "", "warnings: ui_arrow")
edit("""/* The text shown on the right of a row */
static void ui_pref_value(int row, char *out, size_t size)
{
    int i;

    row++;                                      /* v39: the Seek step row is gone, the numbers below keep their old meaning */
    switch (row) {
    case 0: snprintf(out, size, "%g s", cfg_seek); break;
    case 1: snprintf(out, size, "%d", cfg_vol_step); break;
    case 2: snprintf(out, size, "%g s", cfg_hide_delay / 1000000.0); break;
    case 3: snprintf(out, size, "%s", cfg_fullscreen ? "On" : "Off"); break;
    case 4:
        i = ui_color_index();
        snprintf(out, size, "%s", i >= 0 ? ui_colors[i].name : "Custom");
        break;
    case 5: snprintf(out, size, "%s", cfg_remember_volume ? "On" : "Off"); break;
    case 6: snprintf(out, size, "%s", cfg_quit_when_done ? "On" : "Off"); break;
    default: snprintf(out, size, "%s", cfg_wheel == 1 ? "Volume" : cfg_wheel == 2 ? "Navigation" : "Seek"); break;
    }
}
""", "", "warnings: ui_pref_value")
edit("""/* The six choices of the sleep timer (cy = the middle of the row) */
static const char *const *ui_q_chips(const SDL_Rect *p, int cy, SDL_Rect out[6])
{
    int px;

    return ui_q_chips_for(p, cy, ui_text_width("Sleep timer", 18), 6, ui_chip_full, ui_chip_short, out, &px);
}

""", "", "warnings: ui_q_chips")
edit("""/* The choice that is on now (0 to 5) */
static int ui_sleep_current(void)
{
    if (q_sleep_end)
        return av_clip(ui_sleep_sel, 2, 5);
    return q_sleep_item ? 1 : 0;
}

""", "", "warnings: ui_sleep_current")


edit(r"""/* Where the choices of a row under the list go: on the right of its name (labelw wide), which stays. The long names are used
   when they fit, then the short ones, then smaller text. Returns the names to draw; *px is their text size. */
static const char *const *ui_q_chips_for(const SDL_Rect *p, int cy, int labelw, int n, const char *const *full,
                                         const char *const *shrt, SDL_Rect *out, int *px)
{
    static const int pxs[3] = { 14, 15, 13 }, pads[3] = { 10, 8, 6 };
    const char *const *names = full;
    int pass, i, w[8], total = 0, x, room = p->w - 40 - labelw - 14 - UI_Q_ICW - 10;

    for (pass = 0; pass < 3; pass++) {
        names = pass == 0 ? full : shrt;
        total = 0;
        for (i = 0; i < n; i++) {
            w[i] = ui_text_width(names[i], pxs[pass]) + pads[pass];
            total += w[i] + (i ? 3 : 0);
        }
        *px = pxs[pass];
        if (total <= room)
            break;
    }
    x = p->x + p->w - 20 - total;
    for (i = 0; i < n; i++) {
        out[i].x = x;
        out[i].y = cy - 13;
        out[i].w = w[i];
        out[i].h = 26;
        x += w[i] + 3;
    }
    return names;
}

""", "", "warnings: ui_q_chips_for")

# ====================================================================================================== Ctrl+click keeps the first file
edit("""            ui_pk_click_row = ui_pk_hrow;
            ui_pk_click_t = now;
            ui_pk_cur = ui_pk_hrow;
            ui_pk_touched = 1;
            if (dbl) {""", """            int ui_pk_old_cur = ui_pk_cur, old_touched = ui_pk_touched;    /* v53: the row that was chosen before this click */

            ui_pk_click_row = ui_pk_hrow;
            ui_pk_click_t = now;
            ui_pk_cur = ui_pk_hrow;
            ui_pk_touched = 1;
            if (dbl) {""", "ctrl+click: remember the old row")
edit("""                ui_pk_tick_row(ui_pk_hrow);     /* Ctrl+click ticks a file (a plain click in Add to Queue ticks it) */""",
     """                if (ui_pk_mode == 0 && old_touched && ui_pk_old_cur != ui_pk_hrow && ui_pk_old_cur >= 0 && ui_pk_old_cur < ui_pk_nrw &&
                    ui_pk_ticked(NULL) == 0 && ui_pk_ent(ui_pk_old_cur) && !ui_pk_ent(ui_pk_old_cur)->dir)
                    ui_pk_tick_row(ui_pk_old_cur);      /* the file clicked first counts as selected, like in Files */
                ui_pk_tick_row(ui_pk_hrow);     /* Ctrl+click ticks a file (a plain click in Add to Queue ticks it) */""", "ctrl+click: tick the old row first")

if failed:
    print("\n%d edit(s) failed. Nothing written." % len(failed))
    sys.exit(1)
open(path, "w", encoding="utf-8").write(src)
print("\nDone: patch_queue_v53 applied.")
