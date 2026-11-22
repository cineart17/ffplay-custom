#!/usr/bin/env python3
# Update 40 for ffplay-custom (on top of patch_queue_v39.py).
#   * The player now always starts in the conventional full screen: the window that fills the screen under the panel (maximized,
#     with our title bar, corners can be dragged), not the borderless full screen. A double tap in the picture goes to complete
#     full screen (no bars), and a double tap again comes back, as before. The idle screen starts the same way.
#   * Preferences, "Start fullscreen": On (the default) = that conventional full screen. Off = a normal window that is clearly
#     smaller than the screen (at most 70% of it), instead of the video's own size, which on a 1080p video looked like full screen.
#     That size is also the one the window goes back to when it is taken out of the conventional full screen.
#   * Seek step: the smallest one that moves smoothly, worked out for each file. ffplay seeks to key frames, so a step shorter
#     than the gap between two key frames can leave the picture where it was (going back it finds the same key frame again). The
#     Left/Right keys (and the wheel on the seek bar) now step about one key frame gap: the typical (9 out of 10) distance between key
#     frames, between 2 and 10 seconds. Sound-only files step 2 seconds. A file whose key frames are not known keeps ffplay's 10 seconds,
#     and -seek_interval still overrides all of this. There is no setting for it.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v39.py. Writes the file only if every edit matches.
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


if "ui_start_max" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_seek_relative" not in src or "ui_pip_grow" not in src:
    print("Apply patch_queue_v39.py first. Nothing written.")
    sys.exit(1)

STEP_FN = r'''/* The step of the Left and Right keys for a file (v40). ffplay seeks to key frames, so a step that is shorter than the gap between
   two key frames can leave the picture where it was: going back, it finds the same key frame again. The smallest step that always
   moves is about one gap: the typical distance between key frames, and at least half of the longest one. It is kept between 2 and
   10 seconds. Sound only: 2 seconds. A file whose key frames are not known (no index): ffplay's 10 seconds.
   Called once, from the thread that opens the file, before it starts to read (the index does not change under it). */
static int ui_step_cmp(const void *a, const void *b)
{
    double x = *(const double *)a, y = *(const double *)b;

    return x < y ? -1 : x > y ? 1 : 0;
}

static double ui_seek_step_for(AVFormatContext *ic)
{
    AVStream *st;
    int vi = av_find_best_stream(ic, AVMEDIA_TYPE_VIDEO, -1, -1, NULL, 0), i, n, ng = 0;
    double *gap, last = NAN, tb, step = 10.0, med, longest = 0.0;

    if (vi < 0 || (ic->streams[vi]->disposition & AV_DISPOSITION_ATTACHED_PIC))
        return 2.0;                             /* sound only: every frame is a place to land */
    st = ic->streams[vi];
    n = avformat_index_get_entries_count(st);
    if (n < 4)
        return 10.0;                            /* no index: the key frames are not known */
    gap = av_malloc_array(FFMIN(n, 20000), sizeof(*gap));
    if (!gap)
        return 10.0;
    tb = av_q2d(st->time_base);
    for (i = 0; i < n && ng < 20000; i++) {
        const AVIndexEntry *e = avformat_index_get_entry(st, i);
        double t;

        if (!e || !(e->flags & AVINDEX_KEYFRAME))
            continue;
        t = e->timestamp * tb;
        if (!isnan(last) && t > last + 0.05) {
            gap[ng++] = t - last;
            longest = FFMAX(longest, t - last);
        }
        last = t;
    }
    if (ng >= 3) {
        qsort(gap, ng, sizeof(*gap), ui_step_cmp);
        med = gap[(ng * 9) / 10];               /* the 9th tenth, not the middle: in a file with some long gaps the middle step would leave the picture in place there */
        step = ceil(FFMAX(med, 0.55 * longest));
    }
    av_free(gap);
    return av_clipd(step, 2.0, 10.0);
}

'''

# ---------------------------------------------------------------- 1. the player starts in the conventional full screen
patch("start flag", r'''static int     ui_maxed = 0;                /* 1 = conventional full screen: the window fills the screen under the panel (maximized) */''',
      r'''static int     ui_maxed = 0;                /* 1 = conventional full screen: the window fills the screen under the panel (maximized) */
static int     ui_start_max = 1;            /* 1 = the window opens as the conventional full screen (never as the borderless one) */''')

patch("no settings file: not borderless either", r'''static int is_full_screen = 1;''', r'''static int is_full_screen = 0;''')

patch("setting meaning", r'''    is_full_screen = cfg_fullscreen;
}''', r'''    is_full_screen = 0;                         /* v40: never the borderless full screen at the start: it is one double tap away */
    ui_start_max = cfg_fullscreen;              /* On = the conventional full screen, Off = a normal window */
}''')

patch("setting text", r'''    fprintf(f, "# 1 = always open fullscreen, 0 = open in a window\nfullscreen = %d\n\n", cfg_fullscreen);''',
      r'''    fprintf(f, "# 1 = open in the conventional full screen (the window that fills the screen under the panel; a double tap goes to complete full screen), 0 = open in a normal window\nfullscreen = %d\n\n", cfg_fullscreen);''')

patch("setting variable text", r'''static int     cfg_fullscreen = 1;          /* 1 = open fullscreen */''',
      r'''static int     cfg_fullscreen = 1;          /* 1 = open in the conventional full screen, 0 = in a normal window */''')

patch("max_set and the seek step are needed early", r'''static int ui_shown_once = 0;   /* the window is shown once; later items leave its place and workspace alone */''',
      r'''static int ui_shown_once = 0;   /* the window is shown once; later items leave its place and workspace alone */
static void ui_max_set(int on);

''' + STEP_FN + r'''/* How far the Left and Right keys (and the wheel on the seek bar) jump: the step of this file, or -seek_interval if it was given */
static double ui_seek_len(VideoState *is)
{
    if (seek_interval != 10.0f)
        return seek_interval > 0.0f ? seek_interval : 10.0;
    return is && is->ui_seek_step > 0.0 ? is->ui_seek_step : 10.0;
}''')

patch("first show of a video", r'''        if (!ui_shown_once)
            SDL_SetWindowPosition(window, screen_left, screen_top);
        if (is_full_screen)
            SDL_SetWindowFullscreen(window, SDL_WINDOW_FULLSCREEN_DESKTOP);''',
      r'''        if (!ui_shown_once)
            SDL_SetWindowPosition(window, screen_left, screen_top);
        if (!ui_shown_once && ui_start_max)
            ui_max_set(1);                      /* v40: it opens as the window that fills the screen */
        if (is_full_screen)
            SDL_SetWindowFullscreen(window, SDL_WINDOW_FULLSCREEN_DESKTOP);''')

patch("a normal window is smaller than the screen", r'''        if (tiled) {
            w = cw;
            h = ch;
        } else {''', r'''        if (!ui_shown_once && !screen_width && SDL_GetDisplayUsableBounds(0, &ub) == 0) {
            double k = FFMIN((ub.w * 0.7) / FFMAX(w, 1), (ub.h * 0.7) / FFMAX(h, 1));      /* v40: not almost the whole screen */

            if (k < 1.0) {
                w = (int)(w * k) & ~1;
                h = (int)(h * k) & ~1;
            }
        }
        if (tiled) {
            w = cw;
            h = ch;
        } else {''')

patch("first show of the idle screen", r'''        if (!is_full_screen)
            SDL_SetWindowSize(window, 960, 540);
        SDL_ShowWindow(window);
        ui_shown_once = 1;''', r'''        if (!is_full_screen)
            SDL_SetWindowSize(window, 960, 540);
        if (ui_start_max)
            ui_max_set(1);                      /* v40: the idle screen opens as the window that fills the screen too */
        SDL_ShowWindow(window);
        ui_shown_once = 1;''')

# ---------------------------------------------------------------- 2. the smallest smooth seek step, for each file
patch("seek step field", r'''    int ui_thumb_id;            /* the seek previews of this stream: 0 = not started, -1 = none, else their number */''',
      r'''    int ui_thumb_id;            /* the seek previews of this stream: 0 = not started, -1 = none, else their number */
    double ui_seek_step;        /* v40: the step of the Left/Right keys for this file, in seconds (0 = not known: ffplay's 10) */''')


patch("seek step is worked out when the file opens", r'''    is->realtime = is_realtime(ic);''',
      r'''    is->realtime = is_realtime(ic);
    is->ui_seek_step = ui_seek_step_for(ic);    /* v40: the smallest step that moves smoothly for this file */''')

patch("left key", r'''                incr = seek_interval ? -seek_interval : -10.0;''', r'''                incr = -ui_seek_len(cur_stream);''')
patch("right key", r'''                incr = seek_interval ? seek_interval : 10.0;''', r'''                incr = ui_seek_len(cur_stream);''')
patch("the wheel on the seek bar", r'''        ui_seek_relative(is, steps * (seek_interval ? seek_interval : 10.0));        /* v39: the same step as the arrow keys */''',
      r'''        ui_seek_relative(is, steps * ui_seek_len(is));        /* the same step as the arrow keys */''')

if fails:
    print("\n%d edit(s) failed. Nothing written." % len(fails))
    sys.exit(1)
open(PATH, "w").write(src)
print("\nAll edits applied to " + PATH)
