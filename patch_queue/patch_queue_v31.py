#!/usr/bin/env python3
# Update 31 for ffplay-custom (on top of patch_queue_v30.py): background stutter.
#
# The stutter: a video playing in a window that is out of sight (another workspace, the Multitasking view) falls
# behind, the sound stutters with it, and everything is fine again when the workspace is shown. v24 fixed this by
# switching vsync off when the window manager holds a frame back. This update adds a "background mode" on top:
#   * The first held frame (over 100 ms) puts the player in background mode. In it the player does not draw at all:
#     the pictures still go by in time, so picture and sound stay in sync, and the window manager gets no frames it
#     will never show (a window that keeps sending frames nobody shows can fill the buffers of the compositor, and
#     then even a present without vsync waits).
#   * Once in 8 s one picture is drawn with vsync on, as a test. If it comes back within a frame the window is seen
#     again; if it is held, the player stays in background mode. Moving the mouse over the window, focusing it, or
#     showing it ends background mode at once, as before.
#   * The seek previews are not started while in background mode (no disk and CPU work for nobody).
#   * The slow-moment log (v30) names only steps that took over 150 ms, so it no longer fills the terminal.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v30.py. Writes the file only if every spot matches once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_bg_set" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "UI_TIMED" not in src or "ui_present_slow" not in src:
    print("Apply patch_queue_v30.py first. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


patch("static void ui_present(void)\n{\n    int64_t t0 = av_gettime_relative(), dt;\n",
"""/* Background mode: the window is out of sight (a frame was held for long). Nothing is drawn, except one picture in
   a while to find out whether the window is back. */
static int ui_bg = 0;
static int64_t ui_bg_probe = 0;         /* when a picture was last drawn, or the mode last changed */

static void ui_bg_set(int on)
{
    if (on != ui_bg)
        av_log(NULL, AV_LOG_WARNING, on ? "ffplay-custom: window out of sight: not drawing, the pictures and sound go on\\n"
                                        : "ffplay-custom: window in sight again\\n");
    ui_bg = on;
    ui_bg_probe = av_gettime_relative();
}

static void ui_present(void)
{
    int64_t t0 = av_gettime_relative(), dt;
""", "background mode state")

patch("        ui_vsync_set(0);\n    }\n}\n\n/* Is the window out of sight for sure",
"""        ui_vsync_set(0);
        ui_bg_set(1);                   /* out of sight: video_display draws only once in a while */
    } else if (ui_bg && ui_vsync_on && dt < 40000) {
        ui_bg_set(0);                   /* a present with vsync on came back in time: the window is seen again */
    }
}

/* Is the window out of sight for sure""", "a held frame starts background mode, a quick one ends it")

patch("    if (!ui_vsync_on)\n        ui_vsync_set(1);                /* the mouse moved: the window is in sight again */\n",
"""    if (!ui_vsync_on)
        ui_vsync_set(1);                /* the mouse moved: the window is in sight again */
    if (ui_bg)
        ui_bg_set(0);
""", "the mouse ends background mode")

patch("                    ui_vsync_set(1);        /* the window is in sight again */\n",
"""                    ui_vsync_set(1);        /* the window is in sight again */
                    ui_bg_set(0);
""", "showing or focusing the window ends background mode")

patch("""    if (ui_win_unseen())
        return;                     /* minimized or hidden: nothing to draw */

    if (ui_menu_open || ui_prefs_open) {""",
"""    if (ui_win_unseen())
        return;                     /* minimized or hidden: nothing to draw */

    if (ui_bg) {                    /* out of sight: one picture in a while shows whether the window is back */
        int64_t now = av_gettime_relative();

        if (now - ui_bg_probe < 8000000)
            return;
        ui_bg_probe = now;
        ui_vsync_set(1);            /* with vsync a window in sight answers within a frame; a hidden one is held again */
    }

    if (ui_menu_open || ui_prefs_open) {""", "no drawing in background mode")

patch("    if (!UI_THUMBS || is->ui_thumb_id || !is->ic)\n        return;\n    pos = get_master_clock(is);",
      "    if (!UI_THUMBS || is->ui_thumb_id || !is->ic || ui_bg)     /* no previews for a window nobody sees */\n        return;\n    pos = get_master_clock(is);",
      "no seek previews in background mode")

patch("if (t_ > 40000)", "if (t_ > 150000)", "the slow-moment log names only steps over 150 ms")

open(path, "w").write(src)
print("Patched fftools/ffplay.c")
