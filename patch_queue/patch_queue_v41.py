#!/usr/bin/env python3
# Update 41 for ffplay-custom (on top of patch_queue_v40.py).
#   * Fine seek steps where they are cheap. ffplay seeks to key frames, so a step shorter than the gap between two key frames
#     leaves the picture where it was. In a file whose key frames are close together (a gap of 3 seconds or less, and not too
#     heavy to decode: the work from the key frame up to the wanted time is counted in 1080p frames, at most 150) the Left/Right
#     keys now land exactly on their time and step 1 second. Every other file keeps v40's behaviour (ffplay's own seek, the step
#     worked out from its key frames). Sound-only files step 1 second. No quiet gap, no preview picture, nothing held back:
#     only the pictures and sound between the key frame and the wanted time are skipped.
#     Switch: exact_seek = 0 in ~/.config/ffplay-custom/settings.conf turns the exact landing off (the steps stay as in v40).
#   * Menus on a small miniplayer. The right-click menu, the queue, the Preferences, Media Info, the tiled view and the menus
#     of tiles and queue items need room. While the miniplayer is smaller than 700 x 420 they do not open (right click, the
#     L key, a swipe up, a pause) and the ones that are open when it is made smaller close. Make the miniplayer larger and
#     they work as before. The size is UI_FIT_W / UI_FIT_H.
#   * Drag the miniplayer by pressing on the picture and moving: the window follows the mouse and keeps its new place. A
#     press without moving still counts as a tap (a double tap still goes to full screen).
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v40.py. Writes the file only if every edit matches.
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


if "ui_too_small" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_seek_step_for" not in src:
    print("Apply patch_queue_v40.py first. Nothing written.")
    sys.exit(1)

# ---------------------------------------------------------------- 1. exact landing for short steps, where it is cheap
patch("exact seek switch", r'''static int     cfg_fullscreen = 1;          /* 1 = open in the conventional full screen, 0 = in a normal window */''',
      r'''static int     cfg_fullscreen = 1;          /* 1 = open in the conventional full screen, 0 = in a normal window */
static int     cfg_exact_seek = 1;          /* 1 = in a file with close key frames the Left/Right steps land exactly on their time (v41) */''')

patch("exact seek read", r'''        else if (sscanf(line, " fullscreen = %d", &n) == 1)
            cfg_fullscreen = (n != 0);''', r'''        else if (sscanf(line, " fullscreen = %d", &n) == 1)
            cfg_fullscreen = (n != 0);
        else if (sscanf(line, " exact_seek = %d", &n) == 1)
            cfg_exact_seek = (n != 0);''')

patch("exact seek written", r'''\nfullscreen = %d\n\n", cfg_fullscreen);''',
      r'''\nfullscreen = %d\n\n", cfg_fullscreen);
    fprintf(f, "# 1 = in a file with close key frames the Left/Right keys step 1 second and land exactly on their time, 0 = ffplay's own seek (to a key frame) always\nexact_seek = %d\n\n", cfg_exact_seek);''')

patch("exact seek field", r'''    double ui_seek_step;        /* v40: the step of the Left/Right keys for this file, in seconds (0 = not known: ffplay's 10) */''',
      r'''    double ui_seek_step;        /* v40: the step of the Left/Right keys for this file, in seconds (0 = not known: ffplay's 10) */
    int ui_seek_exact;          /* v41: 1 = the key frames of this file are so close that a step can land exactly on its time */''')

patch("step function: the exact decision", r'''static double ui_seek_step_for(AVFormatContext *ic)
{
    AVStream *st;
    int vi = av_find_best_stream(ic, AVMEDIA_TYPE_VIDEO, -1, -1, NULL, 0), i, n, ng = 0;
    double *gap, last = NAN, tb, step = 10.0, med, longest = 0.0;

    if (vi < 0 || (ic->streams[vi]->disposition & AV_DISPOSITION_ATTACHED_PIC))
        return 2.0;                             /* sound only: every frame is a place to land */''',
      r'''#define UI_EXACT_GAP  3.0               /* exact landing only when 9 key frame gaps in 10 are this short (seconds) ...  */
#define UI_EXACT_COST 150.0             /* ... and the longest gap, in 1080p frames to decode, is at most this much work */
#define UI_EXACT_STEP 1.0               /* the step of a file that lands exactly (seconds) */

static double ui_seek_step_for(AVFormatContext *ic, int *exact)
{
    AVStream *st;
    int vi = av_find_best_stream(ic, AVMEDIA_TYPE_VIDEO, -1, -1, NULL, 0), i, n, ng = 0;
    double *gap, last = NAN, tb, step = 10.0, med, longest = 0.0;

    *exact = 0;
    if (vi < 0 || (ic->streams[vi]->disposition & AV_DISPOSITION_ATTACHED_PIC))
        return 1.0;                             /* sound only: every frame is a place to land */''')

patch("step function: the exact decision 2", r'''        step = ceil(FFMAX(med, 0.55 * longest));
    }
    av_free(gap);
    return av_clipd(step, 2.0, 10.0);''', r'''        step = ceil(FFMAX(med, 0.55 * longest));
        if (cfg_exact_seek && med <= UI_EXACT_GAP) {
            double fps = av_q2d(st->avg_frame_rate), px = (double)st->codecpar->width * st->codecpar->height;

            if (!(fps > 1.0 && fps < 240.0))
                fps = 30.0;
            if (px < 1.0)
                px = 1920.0 * 1080.0;
            if (longest * fps * px / (1920.0 * 1080.0) <= UI_EXACT_COST) {
                *exact = 1;                     /* close key frames: the step can be small, and it lands where it says */
                av_free(gap);
                return UI_EXACT_STEP;
            }
        }
    }
    av_free(gap);
    return av_clipd(step, 2.0, 10.0);''')

patch("step is worked out when the file opens", r'''    is->ui_seek_step = ui_seek_step_for(ic);    /* v40: the smallest step that moves smoothly for this file */''',
      r'''    is->ui_seek_step = ui_seek_step_for(ic, &is->ui_seek_exact);    /* the smallest step that moves smoothly for this file (v40), and whether it lands exactly (v41) */''')

patch("exact landing is possible", r'''#define UI_PRECISE_SEEK 0                /* 0 = seek to the nearest key frame, as ffplay does (v39) */''',
      r'''#define UI_PRECISE_SEEK 1                /* the seeks that ask for it (a file with close key frames, v41) land exactly; the others go to the nearest key frame, as ffplay does */''')

patch("keys ask for exact landing", r'''        pos += incr;
        if (is->ic->start_time != AV_NOPTS_VALUE && pos < is->ic->start_time / (double)AV_TIME_BASE)
            pos = is->ic->start_time / (double)AV_TIME_BASE;
        stream_seek(is, (int64_t)(pos * AV_TIME_BASE), (int64_t)(incr * AV_TIME_BASE), 0);''',
      r'''        pos += incr;
        if (is->ic->start_time != AV_NOPTS_VALUE && pos < is->ic->start_time / (double)AV_TIME_BASE)
            pos = is->ic->start_time / (double)AV_TIME_BASE;
        ui_precise_next = is->ui_seek_exact &&  /* v41: close key frames: land exactly (not in the last second: nothing there would reach the time) */
                          (is->ic->duration <= 0 || pos < ((is->ic->start_time != AV_NOPTS_VALUE ? is->ic->start_time : 0) + is->ic->duration) / (double)AV_TIME_BASE - 1.0);
        stream_seek(is, (int64_t)(pos * AV_TIME_BASE), (int64_t)(incr * AV_TIME_BASE), 0);''')

patch("a drag lands exactly only in such a file", r'''        ui_precise_next = force;        /* the last seek of a drag lands exactly */''',
      r'''        ui_precise_next = force && is->ui_seek_exact;   /* the last seek of a drag lands exactly, in a file where that is cheap */''')

# ---------------------------------------------------------------- 2. a small miniplayer has no room for the menus
patch("too small: the test", r'''static void ui_max_set(int on);
''', r'''static void ui_max_set(int on);

/* v41: the menus, the queue, the preferences, Media Info and the tiled view are made for a window of a usable size. The miniplayer
   (small, but it can be dragged larger) opens none of them while it is smaller than this. */
#define UI_FIT_W 700
#define UI_FIT_H 420
static int ui_pip;                              /* 1 = the miniplayer (set below) */
static int ui_too_small(void)
{
    int w, h;

    if (!ui_pip || !window)
        return 0;
    SDL_GetWindowSize(window, &w, &h);
    return w < UI_FIT_W || h < UI_FIT_H;
}
''')

patch("no right-click menu when too small", r'''    if (ev->type == SDL_MOUSEBUTTONDOWN && ev->button.button == SDL_BUTTON_RIGHT && !ui_idle) {
        /* right-click on the video: open the menu at the mouse */''',
      r'''    if (ev->type == SDL_MOUSEBUTTONDOWN && ev->button.button == SDL_BUTTON_RIGHT && !ui_idle && !ui_too_small()) {
        /* right-click on the video: open the menu at the mouse */''')

patch("no queue view when too small", r'''static void ui_vflow_set(VideoState *is, int on)
{
    if (!!ui_vflow == !!on)
        return;''', r'''static void ui_vflow_set(VideoState *is, int on)
{
    if (!!ui_vflow == !!on)
        return;
    if (on && ui_too_small())
        return;                                 /* v41: no room in a small miniplayer */''')

patch("no tiled view over a song when too small", r'''    if (!is || q_count <= 0 || q_pos < 0 || ui_tv_cap(is))
        return;
    if (is->video_st && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC)) {
        if (!ui_vflow) {                        /* the same start as key L */''',
      r'''    if (!is || q_count <= 0 || q_pos < 0 || ui_tv_cap(is) || ui_too_small())
        return;
    if (is->video_st && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC)) {
        if (!ui_vflow) {                        /* the same start as key L */''')

patch("what is open closes when the window gets small", r'''    if (ui_menu_open || ui_prefs_open) {
        ui_glass_frame(is);         /* frosted glass over the blurred picture */
        return;
    }''', r'''    if (ui_too_small() && (ui_menu_open || ui_prefs_open || ui_q_open || ui_info_open || ui_open_open || ui_ctx_open || ui_tvc_open ||
                           ui_vflow || ui_tv_audio)) {
        ui_menu_open = ui_prefs_open = ui_q_open = ui_info_open = ui_open_open = ui_ctx_open = ui_tvc_open = 0;       /* v41 */
        ui_tv_audio = 0;
        ui_vflow_auto = 0;
        ui_vflow_set(is, 0);
        ui_menu_hover = -1;
        is->force_refresh = 1;
    }

    if (ui_menu_open || ui_prefs_open) {
        ui_glass_frame(is);         /* frosted glass over the blurred picture */
        return;
    }''')

# ---------------------------------------------------------------- 3. drag the miniplayer by the picture
patch("drag state", r'''/* ----- picture in picture: the window as a small miniplayer on top, in a corner ----- */''',
      r'''/* v41: the miniplayer follows the mouse while the picture is pressed and moved (the window manager's own move is only for the
   title bar). pd_on: a press is waiting; pd_moved: it has become a drag. */
static int ui_pd_on = 0, ui_pd_moved = 0, ui_pd_gx, ui_pd_gy, ui_pd_wx, ui_pd_wy;
static int64_t ui_last_lclick = 0;              /* time of the last left click in the picture (a second one within half a second = double tap) */

/* ----- picture in picture: the window as a small miniplayer on top, in a corner ----- */''')

patch("tap time is kept for the drag", r'''            if (event.button.button == SDL_BUTTON_LEFT) {
                static int64_t last_mouse_left_click = 0;
                if (av_gettime_relative() - last_mouse_left_click <= 500000) {
                    ui_fs_cycle(cur_stream);
                    cur_stream->force_refresh = 1;
                    last_mouse_left_click = 0;
                } else {
                    last_mouse_left_click = av_gettime_relative();
                }
            }''', r'''            if (event.button.button == SDL_BUTTON_LEFT) {
                if (av_gettime_relative() - ui_last_lclick <= 500000) {
                    ui_fs_cycle(cur_stream);
                    cur_stream->force_refresh = 1;
                    ui_last_lclick = 0;
                } else {
                    ui_last_lclick = av_gettime_relative();
                }
                if (ui_pip && !ui_grow_on && !is_full_screen && window) {       /* v41: a press on the picture may become a drag */
                    ui_pd_on = 1;
                    ui_pd_moved = 0;
                    SDL_GetGlobalMouseState(&ui_pd_gx, &ui_pd_gy);
                    SDL_GetWindowPosition(window, &ui_pd_wx, &ui_pd_wy);
                }
            }''')

patch("drag moves the window", r'''        case SDL_MOUSEMOTION:
            if (event.type == SDL_MOUSEMOTION &&
                (ui_titlebar_mouse(cur_stream, &event) || ui_menu_mouse(cur_stream, &event) ||''',
      r'''        case SDL_MOUSEMOTION:
            if (event.type == SDL_MOUSEMOTION && ui_pd_on) {
                int gx, gy;

                if (!(event.motion.state & SDL_BUTTON_LMASK) || !ui_pip || is_full_screen || ui_grow_on) {
                    ui_pd_on = 0;
                } else {
                    SDL_GetGlobalMouseState(&gx, &gy);
                    if (ui_pd_moved || abs(gx - ui_pd_gx) + abs(gy - ui_pd_gy) > 6) {
                        ui_pd_moved = 1;
                        ui_last_lclick = 0;             /* it was a drag, not the first tap of a double tap */
                        SDL_SetWindowPosition(window, ui_pd_wx + gx - ui_pd_gx, ui_pd_wy + gy - ui_pd_gy);
                        break;
                    }
                }
            }
            if (event.type == SDL_MOUSEMOTION &&
                (ui_titlebar_mouse(cur_stream, &event) || ui_menu_mouse(cur_stream, &event) ||''')

patch("drag ends", r'''        case SDL_MOUSEBUTTONUP:
            if (ui_queue_release(&event)) {
                cur_stream->force_refresh = 1;
                break;
            }
            if (ui_window_mouse(cur_stream, &event))
                break;''', r'''        case SDL_MOUSEBUTTONUP:
            if (ui_pd_on && event.button.button == SDL_BUTTON_LEFT) {
                ui_pd_on = 0;
                if (ui_pd_moved) {
                    ui_pd_moved = 0;
                    ui_pip_save();                      /* the new place is kept for the next time */
                    break;
                }
            }
            if (ui_queue_release(&event)) {
                cur_stream->force_refresh = 1;
                break;
            }
            if (ui_window_mouse(cur_stream, &event))
                break;''')

if fails:
    print("\n%d edit(s) failed. Nothing written." % len(fails))
    sys.exit(1)
open(PATH, "w").write(src)
print("\nAll edits applied to " + PATH)
