#!/usr/bin/env python3
# Update 38 for ffplay-custom (on top of patch_queue_v37.py).
#   * Scroll action, a new preference with three choices: Seek, Volume, Navigation (it replaces "Mouse wheel: Off / Volume + queue /
#     Seek + queue"). It is what the mouse wheel and a two finger swipe up or down do:
#       - Seek: seeks by the seek step.  Volume: changes the volume.
#       - Navigation: a swipe (or wheel turn) up opens the tiled queue view. While the view is open, up and down move between its
#         rows (or sections while searching), sideways moves along them.
#     With the mouse on the volume bar the scroll always changes the volume, on the seek bar it always seeks, whatever is chosen.
#     The setting is saved as scroll_action in settings.conf (0 = seek, 1 = volume, 2 = navigation; the old mouse_wheel line is
#     ignored). The new default is Navigation.
#   * The reason the swipe up never opened the view: v37 guessed "touchpad or wheel" from fractional scroll values, and this
#     session sends whole steps, so every swipe was taken for a wheel. The choice above replaces the guess.
#   * Searching: the In this queue, In Music and In Videos rows each move on their own. A swipe sideways moves the row the mouse
#     is resting on (the arrow keys still move the row that is lit).
#   * The tiles are bigger (wider and taller, in the rows and in the search sections).
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v37.py. Writes the file only if every edit matches.
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
    """Replace everything from the line that starts with `start` up to (not including) `end`."""
    global src
    if src.count(start) != 1 or src.count(end) != 1:
        print("FAILED: %s markers matched %d and %d times" % (name, src.count(start), src.count(end)))
        fails.append(name)
        return
    i = src.index(start)
    j = src.index(end)
    if j < i:
        print("FAILED: %s markers are in the wrong order" % name)
        fails.append(name)
        return
    src = src[:i] + new + src[j:]
    print("ok: " + name)


if "ui_tv_swipe_open" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_tv_draw" not in src:
    print("Apply patch_queue_v37.py first. Nothing written.")
    sys.exit(1)

# ---------------------------------------------------------------- the preference
patch("wheel setting", r'''static int     cfg_wheel = 0;               /* mouse wheel: 0 = off, 1 = volume, 2 = seek */''',
      r'''static int     cfg_wheel = 2;               /* scroll action (wheel and two finger swipes): 0 = seek, 1 = volume, 2 = navigation */''')

patch("wheel setting in the template", r'''    "# Mouse wheel (and touchpad swipe): 0 = off, 1 = volume, 2 = seek by the seek step\n"
    "mouse_wheel = 0\n"''', r'''    "# Scroll action (mouse wheel and two finger swipes up and down): 0 = seek by the seek step, 1 = volume, 2 = navigation (a swipe up opens the tiled view)\n"
    "scroll_action = 2\n"''')

patch("wheel setting load", r'''        else if (sscanf(line, " mouse_wheel = %d", &n) == 1)
            cfg_wheel = av_clip(n, 0, 2);''', r'''        else if (sscanf(line, " scroll_action = %d", &n) == 1)
            cfg_wheel = av_clip(n, 0, 2);''')

patch("wheel setting save", r'''    fprintf(f, "# Mouse wheel (and touchpad swipe): 0 = off, 1 = volume, 2 = seek by the seek step\nmouse_wheel = %d\n\n", cfg_wheel);''',
      r'''    fprintf(f, "# Scroll action (mouse wheel and two finger swipes up and down): 0 = seek by the seek step, 1 = volume, 2 = navigation (a swipe up opens the tiled view)\nscroll_action = %d\n\n", cfg_wheel);''')

patch("preference name", r'''"Bar color", "Remember volume", "Quit when the queue ends", "Mouse wheel"''',
      r'''"Bar color", "Remember volume", "Quit when the queue ends", "Scroll action"''')

patch("preference value", r'''    default: snprintf(out, size, "%s", cfg_wheel == 1 ? "Volume + queue" : cfg_wheel == 2 ? "Seek + queue" : "Off"); break;''',
      r'''    default: snprintf(out, size, "%s", cfg_wheel == 1 ? "Volume" : cfg_wheel == 2 ? "Navigation" : "Seek"); break;''')

patch("preference choices", r'''        snprintf(store[0], 20, "Off");
        snprintf(store[1], 20, "Volume + queue");
        snprintf(store[2], 20, "Seek + queue");
        n = 3;
        *sel = av_clip(cfg_wheel, 0, 2);''', r'''        snprintf(store[0], 20, "Seek");
        snprintf(store[1], 20, "Volume");
        snprintf(store[2], 20, "Navigation");
        n = 3;
        *sel = av_clip(cfg_wheel, 0, 2);''')

# ---------------------------------------------------------------- the view's part of the swipes
patch("declarations", r'''static int ui_tv_wheel(VideoState *is, SDL_Event *ev);''',
      r'''static void ui_tv_swipe_x(VideoState *is, double ax);               /* v38: the parts of a swipe that belong to the tiled view */
static void ui_tv_swipe_y(VideoState *is, double ay);
static int ui_tv_swipe_open(VideoState *is, double ay);''')

between("swipes of the view", r'''/* Swipes: sideways moves through the rows, up and down (two fingers) between rows or sections.''',
        r'''/* ---- drawing ---- */''', r'''/* Swipes (v38). ui_wheel_action decides who gets a swipe (the Scroll action preference, and the bars); these are the parts that
   belong to the tiled view. ay is already turned the right way round: a negative ay is fingers moving up. */
static int64_t ui_tv_gest_until = 0;            /* the end of the swipe that opened the view keeps coming for a moment: it moves nothing */

static int ui_tv_sec_at(int y)                  /* the section (while searching) that has the height y, or -1 */
{
    int s;

    for (s = 0; s < 3; s++)
        if (y >= ui_tv_secy[s][0] && y < ui_tv_secy[s][1])
            return s;
    return -1;
}

/* Sideways: browsing, every row moves together. Searching, the section the mouse is resting on moves, on its own. */
static void ui_tv_swipe_x(VideoState *is, double ax)
{
    static double acc = 0.0;
    static int64_t last = 0;
    int64_t now = av_gettime_relative();
    int steps;

    if (now - last > 300000 || ax * acc < 0.0)
        acc = 0.0;
    last = now;
    acc += ax;
    steps = (int)acc;
    if (!steps)
        return;
    acc -= steps;
    if (ui_tv_q[0]) {
        int mx, my, s;

        SDL_GetMouseState(&mx, &my);
        s = ui_tv_sec_at(my);
        if (s >= 0 && ui_tv_sec[s].n > 0)
            ui_tv_act = s;
    }
    ui_tv_step(is, steps, 0);
}

/* Up and down: one row (or section) for each swipe */
static void ui_tv_swipe_y(VideoState *is, double ay)
{
    static double acc = 0.0;
    static int64_t last = 0;
    static int lock = 0;
    int64_t now = av_gettime_relative();

    if (now < ui_tv_gest_until)
        return;
    if (now - last > 250000) {
        acc = 0.0;
        lock = 0;
    }
    last = now;
    acc += ay;
    if (!lock && FFABS(acc) >= 2.0) {
        lock = 1;
        ui_tv_step(is, 0, acc * UI_TV_UP_SIGN > 0 ? 1 : -1);
    }
}

/* Fingers up (the Navigation choice) with the view closed: it opens. Returns 1 if the swipe was up. */
static int ui_tv_swipe_open(VideoState *is, double ay)
{
    static double acc = 0.0;
    static int64_t last = 0;
    int64_t now = av_gettime_relative();

    if (ay * UI_TV_UP_SIGN <= 0.0)
        return 0;                               /* down: nothing to do while the view is closed */
    if (now - last > 250000)
        acc = 0.0;
    last = now;
    acc += FFABS(ay);
    if (now >= ui_tv_gest_until && acc >= 1.0) {
        acc = 0.0;
        ui_tv_gest_until = now + 700000;
        ui_tv_enter(is);
    }
    return 1;
}

''')

# ---------------------------------------------------------------- what a wheel turn or a swipe does
between("scroll action", r'''/* The mouse wheel (or a touchpad swipe), as chosen in Preferences: volume, seek, or nothing */''',
        r'''static void event_loop(VideoState *cur_stream)''', r'''/* Where the mouse is on the bottom strip: 1 = on the seek bar, 2 = on the volume bar, 0 = elsewhere */
static int ui_wheel_zone(VideoState *is)
{
    SDL_Rect sk, vo;
    int mx, my;

    if (!is || !UI_ON(is))
        return 0;
    SDL_GetMouseState(&mx, &my);
    if (my < is->height - UI_BAR_H)
        return 0;
    ui_layout(is, &sk, &vo);
    if (mx >= vo.x - 10 && mx <= vo.x + vo.w + 10)
        return 2;
    if (mx >= sk.x - 10 && mx <= sk.x + sk.w + 10)
        return 1;
    return 0;
}

/* The mouse wheel and the two finger swipes, as chosen in Preferences (Scroll action): seek, volume or navigation.
   On the volume bar they change the volume and on the seek bar they seek, whatever is chosen. Sideways always navigates. */
static void ui_wheel_action(VideoState *is, SDL_Event *ev)
{
    static double acc = 0.0;
    static int64_t last = 0;
    int64_t now = av_gettime_relative();
    double ax, ay;
    int act, steps, i, zone;

    if (!is || ui_menu_open || ui_prefs_open)
        return;
#if SDL_VERSION_ATLEAST(2, 0, 18)
    ax = ev->wheel.preciseX;
    ay = ev->wheel.preciseY;
#else
    ax = ev->wheel.x;
    ay = ev->wheel.y;
#endif
    if (ev->wheel.direction == SDL_MOUSEWHEEL_FLIPPED) {
        ax = -ax;
        ay = -ay;
    }
    if (FFABS(ax) > FFABS(ay)) {                /* a sideways swipe: along the tiles of the view, or through the queue */
        if (ui_tv_cap(is))
            ui_tv_swipe_x(is, ax);
        else
            ui_flow_swipe(is, ev);
        is->force_refresh = 1;
        return;
    }
    if (ay == 0.0)
        return;
    zone = ui_wheel_zone(is);
    act = zone == 1 ? 0 : zone == 2 ? 1 : cfg_wheel;            /* 0 = seek, 1 = volume, 2 = navigation */
    if (act == 2 || (!zone && ui_tv_cap(is))) {                 /* with the view open, up and down belong to it */
        if (ui_tv_cap(is))
            ui_tv_swipe_y(is, ay);
        else
            ui_tv_swipe_open(is, ay);
        is->force_refresh = 1;
        return;
    }
    if (now - last > 300000 || ay * acc < 0.0)
        acc = 0.0;                              /* a new swipe, or the other direction: start from zero */
    last = now;
    acc += ay;
    steps = (int)acc;                           /* whole notches only: a touchpad adds up small moves */
    if (!steps)
        return;
    acc -= steps;
    if (act == 1) {
        for (i = 0; i < FFABS(steps); i++)
            update_volume(is, steps > 0 ? -1 : 1, SDL_VOLUME_STEP);        /* reversed */
    } else {
        ui_seek_relative(is, steps * cfg_seek);
    }
    ui_wake();                                  /* the bars show what happened */
    is->force_refresh = 1;
}

''')

# ---------------------------------------------------------------- bigger tiles
patch("browsing tiles", r'''        sh = av_clipd(FFMIN(rp * 0.62, W * 0.2), 40.0, 260.0);''',
      r'''        sh = av_clipd(FFMIN(FFMIN(rp * 0.74, rp - 46.0), W * 0.24), 40.0, 340.0);      /* v38: bigger */''')
patch("browsing tile width", r'''            row.sw = (int)(sh * 1.5);
            row.sh = (int)sh;''', r'''            row.sw = (int)(sh * 1.75);
            row.sh = (int)sh;''')
patch("search tiles", r'''        int sh = (int)av_clipd(secH - 24 - 34, 36.0, 190.0), tr, tg, tb;''',
      r'''        int sh = (int)av_clipd(FFMIN(secH - 24 - 30, W * 0.2), 36.0, 260.0), tr, tg, tb;     /* v38: bigger */''')
patch("search tile width", r'''            row.sw = (int)(sh * 1.5);
            row.sh = sh;''', r'''            row.sw = (int)(sh * 1.75);
            row.sh = sh;''')

if fails:
    print("\n%d edit(s) did not match. Nothing written." % len(fails))
    sys.exit(1)
open(PATH, "w").write(src)
print("\nAll edits applied. Rebuild: make -j$(nproc)")
