#!/usr/bin/env python3
# Update 24 for ffplay-custom (on top of patch_queue_v23.py).
#   * Background stutter: when the window is not on screen (another workspace, Multitasking view), the window manager
#     can hold back every frame we present. The main loop then stalls, the video queue fills up, the reader stops
#     reading audio too, and the sound stutters. Now the time every present takes is measured; when one is held for
#     more than 150 ms the player stops waiting for the screen (vsync off) until the window is seen again (shown,
#     restored, focused, mouse over it). A minimized or hidden window is not drawn at all. The packet queue is also
#     bigger (64 MB), so audio keeps flowing while the picture is late. A line is printed on the terminal when it
#     happens.
#   * Window title: "ffplay-custom - <name>", the same name as the title bar (no folder path any more).
#   * Right click on the title bar: the window manager's own menu (Always on top, Show on all workspaces, move to
#     workspace, Move, Resize, Maximize, Minimize, Close). X11 sessions only (the _GTK_SHOW_WINDOW_MENU request).
#   * A tap on the playing video's tile in the queue view opens the video full screen (and plays) instead of pausing.
#     Pausing a video that is part of a queue opens the queue view; playing again closes it (if L opened it, it stays).
#     When the last item of the queue ends and "quit when the queue ends" is off, a video stays paused on its last
#     picture (play restarts it) instead of going to the idle screen.
#   * Bigger video tiles in the queue view.
#   * A dark glass strip behind the seek and volume bars (as small as it can be), a shorter title bar.
#   * Video crossfade: the next video fades in over the end of the one that plays, as the sound does.
#   * Smooth seeking: the Left/Right step can be 0.3 or 0.5 s (Preferences); key, wheel and bar-release seeks land
#     exactly on the wanted time (the pictures and sound before it are decoded and skipped); dragging the bar sends 20
#     seeks a second instead of 10.
#   * No flash of the last picture when the player closes: the window turns fully transparent before it goes.
#   * The window is shown once. A new item no longer re-raises or re-centers it, and the idle screen no longer pulls it
#     back to the front (found in the other v24; the likely real cause of the window popping up at the end of the queue).
#     A window tiled or maximized by the window manager keeps its size. The terminal says when the window goes out of
#     sight and comes back. Exact seeking can be switched off with UI_PRECISE_SEEK 0.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v23.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_present(" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_titlebar_draw" not in src:
    print("Apply patch_queue_v23.py first. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


# ============================================================ includes, bigger packet queue, stream fields
patch("#include <dirent.h>\n",
      "#include <dirent.h>\n#include <SDL_syswm.h>\n#include <dlfcn.h>\n",
      "includes for the window menu")

patch("#define MAX_QUEUE_SIZE (15 * 1024 * 1024)",
      "#define MAX_QUEUE_SIZE (64 * 1024 * 1024)       /* big: audio keeps flowing while the picture is late */",
      "bigger packet queue")

patch("    struct SwsContext *sub_convert_ctx;\n    int eof;\n",
      "    struct SwsContext *sub_convert_ctx;\n    int eof;\n"
      "    int seek_precise;           /* the seek in progress must land exactly on its time */\n"
      "    int prec_v, prec_a;         /* 1 = pictures / sound before prec_target are still being skipped */\n"
      "    int prec_ser_v, prec_ser_a; /* the queue serial those frames belong to */\n"
      "    double prec_target;         /* seconds */\n"
      "    volatile int ui_hold;       /* the reader saw the end of the last video: pause on its last picture */\n"
      "    int ui_held;                /* 0 = not held, 1 = paused on the last picture, 2 = restarting */\n",
      "stream fields")

# ============================================================ present without ever waiting for the window manager
patch("/* Show the cursor and bar again and restart the hide timer */\n",
      """/* ---- showing the picture without waiting for the window manager ----
   A window that is not on screen (another workspace, the Multitasking view) can have its frames held back for a long
   time. Waiting for them stops the main loop, so pictures pile up, the reader stops reading sound too, and playback
   stutters until the window is seen again. So a present that takes long switches vsync off; it comes back as soon as
   the window is seen again. */
static int ui_vsync_on = 1;
static int ui_present_slow = 0;

static void ui_vsync_set(int on)
{
#if SDL_VERSION_ATLEAST(2, 0, 18)
    if (renderer && on != ui_vsync_on) {
        SDL_RenderSetVSync(renderer, on);
        ui_vsync_on = on;
    }
#endif
    ui_present_slow = 0;
}

static void ui_present(void)
{
    int64_t t0 = av_gettime_relative(), dt;

    SDL_RenderPresent(renderer);
    dt = av_gettime_relative() - t0;
    if (dt > 100000) {
        if (ui_vsync_on)
            av_log(NULL, AV_LOG_WARNING, "ffplay-custom: the window manager held a frame for %d ms (window in the background?): not waiting for the screen until the window is seen again\\n", (int)(dt / 1000));
        ui_vsync_set(0);
    }
}

/* Is the window out of sight for sure (minimized or hidden)? Then nothing is drawn. */
static int ui_win_unseen(void)
{
    static int was = 0;
    int now = window && (SDL_GetWindowFlags(window) & (SDL_WINDOW_MINIMIZED | SDL_WINDOW_HIDDEN));

    if (now != was) {
        was = now;
        av_log(NULL, AV_LOG_WARNING, "ffplay-custom: window %s\\n", now ? "hidden or minimized: not drawing, the pictures still go by" : "on screen again");
    }
    return now;
}

/* Show the cursor and bar again and restart the hide timer */
""", "present helpers")

patch("static void ui_wake(void)\n{\n",
      "static void ui_wake(void)\n{\n    if (!ui_vsync_on)\n        ui_vsync_set(1);                /* the mouse moved: the window is in sight again */\n",
      "vsync back on mouse movement")

patch("    ui_prefs_draw();\n    ui_ink_dark = 0;\n    SDL_RenderPresent(renderer);\n}",
      "    ui_prefs_draw();\n    ui_ink_dark = 0;\n    ui_present();\n}",
      "present (glass frame)")

patch("    ui_menu_draw();\n    SDL_RenderPresent(renderer);\n}",
      "    ui_menu_draw();\n    ui_present();\n}",
      "present (video)")

patch("static void video_display(VideoState *is)\n{\n    if (!is->width)\n        video_open(is);\n\n",
      "static void video_display(VideoState *is)\n{\n    if (!is->width)\n        video_open(is);\n\n    if (ui_win_unseen())\n        return;                     /* minimized or hidden: nothing to draw */\n\n",
      "no drawing when out of sight")

patch("                case SDL_WINDOWEVENT_LEAVE:\n                    ui_hover = 0;\n                    break;\n",
      "                case SDL_WINDOWEVENT_SHOWN:\n                case SDL_WINDOWEVENT_RESTORED:\n                case SDL_WINDOWEVENT_FOCUS_GAINED:\n                case SDL_WINDOWEVENT_ENTER:\n"
      "                    ui_vsync_set(1);        /* the window is in sight again */\n                    cur_stream->force_refresh = 1;\n                    break;\n"
      "                case SDL_WINDOWEVENT_LEAVE:\n                    ui_hover = 0;\n                    break;\n",
      "window events bring vsync back")

# ============================================================ no flash of the last picture when closing
patch("    if (is)\n        volume_save(is->audio_volume);\n    if (is) {\n        stream_close(is);\n    }\n    if (renderer)\n        SDL_DestroyRenderer(renderer);",
      "    if (is)\n        volume_save(is->audio_volume);\n    if (is) {\n        stream_close(is);\n    }\n"
      "#if SDL_VERSION_ATLEAST(2, 0, 5)\n    if (window && (SDL_GetWindowFlags(window) & SDL_WINDOW_SHOWN)) {\n"
      "        SDL_SetWindowOpacity(window, 0.0f);     /* the window manager's closing effect then has nothing to show */\n"
      "        SDL_PumpEvents();\n        SDL_Delay(70);\n        SDL_HideWindow(window);\n    }\n#endif\n"
      "    if (renderer)\n        SDL_DestroyRenderer(renderer);",
      "transparent before closing")

# ============================================================ window title: ffplay-custom - name
patch("        input_filename = q_items[q_pos];        /* read_thread and the title use it */\n        window_title = NULL;\n",
      "        input_filename = q_items[q_pos];        /* read_thread and the title use it */\n"
      "        {                                       /* the window title: ffplay-custom - name, the name the title bar shows */\n"
      "            static char ui_title[400];\n            char nm[320];\n\n"
      "            ui_q_name(q_pos, nm, sizeof(nm));\n"
      "            snprintf(ui_title, sizeof(ui_title), \"ffplay-custom - %s\", nm);\n"
      "            window_title = ui_title;\n"
      "            if (window)\n                SDL_SetWindowTitle(window, window_title);\n        }\n",
      "window title")

# ============================================================ title bar: shorter, and the window manager's menu on right click
patch("#define UI_TB_H     40                  /* height of the strip */\n#define UI_TB_BTN   48                  /* width of each button */\n#define UI_TB_EDGE  6                   /* the top rows stay the window's resize edge */",
      "#define UI_TB_H     30                  /* height of the strip */\n#define UI_TB_BTN   40                  /* width of each button */\n#define UI_TB_EDGE  5                   /* the top rows stay the window's resize edge */",
      "shorter title bar")

patch("    for (y = 0; y < UI_TB_H + 14; y++) {        /* a dark glass strip that fades out along its lower edge */\n        a = y < UI_TB_H ? 125 : 125 * (UI_TB_H + 14 - y) / 14;",
      "    for (y = 0; y < UI_TB_H + 10; y++) {        /* a dark glass strip that fades out along its lower edge */\n        a = y < UI_TB_H ? 125 : 125 * (UI_TB_H + 10 - y) / 10;",
      "title bar glass")

patch("ui_fan(ui_tb_hover == 1 ? cx1 : cx2, cy, 16, 0, 6.28318531, 28, 255, 255, 255, 40);",
      "ui_fan(ui_tb_hover == 1 ? cx1 : cx2, cy, 12, 0, 6.28318531, 28, 255, 255, 255, 40);",
      "title bar highlight")

patch("    ui_tb_line(cx1 - 6, cy - 6, cx1 + 6, cy + 6, 2.0);\n    ui_tb_line(cx1 - 6, cy + 6, cx1 + 6, cy - 6, 2.0);",
      "    ui_tb_line(cx1 - 5, cy - 5, cx1 + 5, cy + 5, 1.8);\n    ui_tb_line(cx1 - 5, cy + 5, cx1 + 5, cy - 5, 1.8);",
      "title bar cross")

patch("                ui_tb_line(cx2 + sx * 7, cy + sy * 7, cx2 + sx * 2, cy + sy * 7, 2.0);\n                ui_tb_line(cx2 + sx * 7, cy + sy * 7, cx2 + sx * 7, cy + sy * 2, 2.0);",
      "                ui_tb_line(cx2 + sx * 6, cy + sy * 6, cx2 + sx * 2, cy + sy * 6, 1.8);\n                ui_tb_line(cx2 + sx * 6, cy + sy * 6, cx2 + sx * 6, cy + sy * 2, 1.8);",
      "title bar fullscreen corners")

patch("    ui_fit_text(name, 15, w - 2 * (UI_TB_BTN + 16));\n    ui_label_c(w / 2, cy, name, 15, 235, 235, 235, 210);",
      "    ui_fit_text(name, 14, w - 2 * (UI_TB_BTN + 16));\n    ui_label_c(w / 2, cy, name, 14, 235, 235, 235, 210);",
      "title bar text")

patch("/* Clicks on the two buttons. Returns 1 if the click was used. */\nstatic int ui_titlebar_mouse(",
      """/* The window manager's own window menu (always on top, show on all workspaces, move to workspace, move, resize,
   maximize, minimize, close) at the mouse. X11 sessions: the window manager is asked with _GTK_SHOW_WINDOW_MENU. */
typedef struct {
    int type;
    unsigned long serial;
    int send_event;
    void *display;
    unsigned long window;
    unsigned long message_type;
    int format;
    long l[5];
} UiXClientMsg;

static void ui_wm_menu(void)
{
    SDL_SysWMinfo info;
    static void *xlib = NULL;
    static unsigned long (*x_atom)(void *, const char *, int);
    static unsigned long (*x_root)(void *);
    static int (*x_send)(void *, unsigned long, int, long, void *);
    static int (*x_flush)(void *);
    union { UiXClientMsg m; long pad[24]; } ev;
    int gx, gy;

    SDL_VERSION(&info.version);
    if (!window || !SDL_GetWindowWMInfo(window, &info))
        return;
    if (info.subsystem != SDL_SYSWM_X11) {
        av_log(NULL, AV_LOG_WARNING, "ffplay-custom: the window menu is only available on X11 sessions\\n");
        return;
    }
    if (!xlib) {
        xlib = dlopen("libX11.so.6", RTLD_LAZY);
        if (xlib) {
            *(void **)&x_atom = dlsym(xlib, "XInternAtom");
            *(void **)&x_root = dlsym(xlib, "XDefaultRootWindow");
            *(void **)&x_send = dlsym(xlib, "XSendEvent");
            *(void **)&x_flush = dlsym(xlib, "XFlush");
        }
    }
    if (!x_atom || !x_root || !x_send || !x_flush)
        return;
    SDL_GetGlobalMouseState(&gx, &gy);
    memset(&ev, 0, sizeof(ev));
    ev.m.type = 33;                             /* ClientMessage */
    ev.m.display = info.info.x11.display;
    ev.m.window = info.info.x11.window;
    ev.m.message_type = x_atom(info.info.x11.display, "_GTK_SHOW_WINDOW_MENU", 0);
    ev.m.format = 32;
    ev.m.l[0] = 0;                              /* the pointer device */
    ev.m.l[1] = gx;
    ev.m.l[2] = gy;
    x_send(info.info.x11.display, x_root(info.info.x11.display), 0, (1L << 20) | (1L << 19), &ev);   /* SubstructureRedirect | SubstructureNotify */
    x_flush(info.info.x11.display);
}

/* Clicks on the two buttons. Returns 1 if the click was used. */
static int ui_titlebar_mouse(""", "window manager menu")

patch("    if (ev->button.button != SDL_BUTTON_LEFT || !hover)\n        return 0;\n    if (hover == 1) {",
      "    if (ev->button.button == SDL_BUTTON_RIGHT && y < UI_TB_H) {\n        ui_wm_menu();                           /* right click on the title bar: the window manager's menu */\n        return 1;\n    }\n"
      "    if (ev->button.button != SDL_BUTTON_LEFT || !hover)\n        return 0;\n    if (hover == 1) {",
      "right click on the title bar")

# ============================================================ dark glass strip behind the seek and volume bars
patch("    ui_seek_bar(is, &sk, frac);\n    ui_ctrl_draw(is, &sk);\n    ui_bar(&vo, vfrac);\n",
      """    {                                           /* a dark glass strip as small as it can be: the bars stay visible on any picture */
        SDL_Rect row;
        int y, top = sk.y - 12, a;

        row.x = 0;
        row.w = is->width;
        row.h = 1;
        for (y = top - 10; y < is->height; y++) {
            a = y < top ? 125 * (y - (top - 10)) / 10 : 125;
            row.y = y;
            SDL_SetRenderDrawColor(renderer, 0, 0, 0, a);
            SDL_RenderFillRect(renderer, &row);
        }
    }
    ui_seek_bar(is, &sk, frac);
    ui_ctrl_draw(is, &sk);
    ui_bar(&vo, vfrac);
""", "bottom glass strip")

# ============================================================ queue view: bigger video tiles, tap = full screen, pause = queue view
patch("    B = ui_flow_vmode ? FFMIN(W * 0.36, H * 0.50) : FFMIN(W * 0.30, H * 0.44);     /* wide tiles need more room */\n    cx = W / 2 - (ui_flow_vmode ? 0 : (int)(B * 0.12));\n    chh = (int)B;                               /* the height of the middle tile */\n    cy = (int)(H * 0.40);",
      """    {                                           /* video tiles: as big as the window allows (a wide picture fills the width, a tall one the height) */
        double ar = 1.0;

        if (ui_flow_vmode && is->video_st && is->video_st->codecpar->height > 0)
            ar = av_clipd((double)is->video_st->codecpar->width / is->video_st->codecpar->height, 1.0, 1.8);
        B = ui_flow_vmode ? FFMIN(W * 0.42, H * 0.50 * ar) : FFMIN(W * 0.30, H * 0.44);
    }
    cx = W / 2 - (ui_flow_vmode ? 0 : (int)(B * 0.12));
    chh = (int)B;                               /* the height of the middle tile */
    cy = (int)(H * (ui_flow_vmode ? 0.38 : 0.40));""", "bigger video tiles")

patch("static int ui_flow_on(VideoState *is)\n{",
      """static void toggle_full_screen(VideoState *is);

/* The queue view over a video: on or off, with the same start every time */
static int ui_vflow_auto = 0;           /* 1 = a pause opened the queue view, so playing again closes it */

static void ui_vflow_set(VideoState *is, int on)
{
    if (!!ui_vflow == !!on)
        return;
    ui_vflow = on;
    ui_vflow_t = 0;
    ui_bd_key[0] = 0;                   /* the backdrop takes its colors from the picture of this moment */
    ui_flow_pos = ui_flow_target = q_pos;       /* the row starts at the playing video, no gliding in */
    ui_flow_last_q = q_pos;
    ui_flow_touch = 0;
    is->force_refresh = 1;
}

/* A tap on the tile of the video that plays: it opens full screen and plays (1 = the window goes full screen, 0 = it only fills the window) */
#define UI_TILE_TAP_FULLSCREEN 1

static void ui_tile_open(VideoState *is)
{
    if (is->paused)
        toggle_pause(is);
    ui_vflow_auto = 0;
    ui_vflow_set(is, 0);
#if UI_TILE_TAP_FULLSCREEN
    if (!is_full_screen)
        toggle_full_screen(is);
#endif
}

static int ui_flow_on(VideoState *is)
{""", "tile helpers")

patch("    } else if (idx == q_pos) {\n        toggle_pause(is);\n    } else if (idx < q_count) {",
      "    } else if (idx == q_pos) {\n        if (ui_flow_video(is))\n            ui_tile_open(is);                   /* a video: its tile opens it full screen */\n        else\n            toggle_pause(is);\n    } else if (idx < q_count) {",
      "tap on the playing tile")

patch("                    ui_vflow = !ui_vflow;\n                    ui_vflow_t = 0;",
      "                    ui_vflow = !ui_vflow;\n                    ui_vflow_auto = 0;          /* L was pressed: it stays until L is pressed again */\n                    ui_vflow_t = 0;",
      "L key owns the queue view")

patch("static void refresh_loop_wait_event(VideoState *is, SDL_Event *event) {",
      """/* A pause opens the queue view over a video that is part of a queue; playing again closes it. The last picture of the
   last video stays on screen, paused, when the queue ends and the player does not quit. */
static void ui_pause_tick(VideoState *is)
{
    static int seen = 0;
    static int64_t unpaused_at = 0;
    int vid = is->video_st && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC);
    int64_t now = av_gettime_relative();

    if (is->ui_hold) {
        if (!is->ui_held) {
            if (!is->paused)
                toggle_pause(is);
            is->ui_held = 1;
            is->force_refresh = 1;
        } else if (is->ui_held == 1 && !is->paused) {      /* play was pressed on the last picture: from the start */
            is->ui_held = 2;
            is->ui_hold = 0;
            stream_seek(is, is->ic->start_time != AV_NOPTS_VALUE ? is->ic->start_time : 0, 0, 0);
        }
    } else if (is->ui_held == 2 && !is->seek_req && !is->eof) {
        is->ui_held = 0;
    }
    if (is->paused && !seen) {
        seen = 1;
        if (vid && q_count >= 2 && q_pos >= 0 && !ui_vflow) {
            ui_vflow_set(is, 1);
            ui_vflow_auto = 1;
        }
    } else if (!is->paused && !is->step) {
        if (seen && !unpaused_at)
            unpaused_at = now;
        if (seen && now - unpaused_at > 250000) {          /* playing for a moment (a seek while paused flickers) */
            seen = 0;
            unpaused_at = 0;
            if (ui_vflow_auto) {
                ui_vflow_auto = 0;
                ui_vflow_set(is, 0);
            }
        }
    } else {
        unpaused_at = 0;
    }
}

static void refresh_loop_wait_event(VideoState *is, SDL_Event *event) {""", "pause opens the queue view")

patch("        ui_xfade_tick(is);\n        ui_cover_tick(is);",
      "        ui_xfade_tick(is);\n        ui_pause_tick(is);\n        ui_cover_tick(is);",
      "pause tick in the loop")

# the reader: the end of the last video
patch("static int read_thread(void *arg)\n{",
      """/* The end of the last video of the queue, when the player does not quit: it stays on its last picture instead */
static int ui_hold_last_wanted(VideoState *is)
{
    return !cfg_quit_when_done && is != xf_stream && is->video_st && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC) &&
           q_count > 0 && q_pos >= 0 && q_pos < q_count && q_forced < 0 && queue_next() >= q_count;
}

static int read_thread(void *arg)
{""", "last video helper")

patch("            } else if (autoexit) {\n                ret = AVERROR_EOF;\n                goto fail;\n            }\n        }\n        ret = av_read_frame(ic, pkt);",
      "            } else if (autoexit) {\n                if (ui_hold_last_wanted(is)) {\n                    if (!is->ui_held)\n                        is->ui_hold = 1;        /* the main loop pauses on the last picture */\n                } else {\n                    ret = AVERROR_EOF;\n                    goto fail;\n                }\n            }\n        }\n        ret = av_read_frame(ic, pkt);",
      "hold on the last picture")

# ============================================================ video crossfade
patch("static void ui_live_grab(VideoState *is, const SDL_Rect *rect, int flip);",
      "static void ui_live_grab(VideoState *is, const SDL_Rect *rect, int flip);\nstatic void ui_xf_video_draw(VideoState *is);",
      "crossfade declaration")

patch("        SDL_RenderCopyEx(renderer, is->vid_texture, NULL, &rect, 0, NULL, vp->flip_v ? SDL_FLIP_VERTICAL : 0);\n    set_sdl_yuv_conversion_mode(NULL);\n    if (sp) {",
      "    {\n        SDL_RenderCopyEx(renderer, is->vid_texture, NULL, &rect, 0, NULL, vp->flip_v ? SDL_FLIP_VERTICAL : 0);\n        ui_xf_video_draw(is);                   /* the next video fades in over the end of this one */\n    }\n    set_sdl_yuv_conversion_mode(NULL);\n    if (sp) {",
      "crossfade drawing call")

patch("static void ui_xf_abort(void)\n{",
      """static double ui_xf_t = 0.0;            /* 0 to 1: how far the crossfade has gone */

/* The picture of the next video, drawn over the end of this one, a little stronger each moment */
static void ui_xf_video_draw(VideoState *is)
{
    VideoState *xf = xf_stream;
    Frame *np;
    SDL_Rect r;

    if (!xf || ui_xf_t <= 0.0 || !xf->video_st || (xf->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC) ||
        xf->pictq.size <= 0 || ui_flow_video(is) || ui_has_cover(is))
        return;
    np = frame_queue_peek_last(&xf->pictq);
    if (!np->frame || !np->frame->width || !np->width || !np->height)
        return;
    calculate_display_rect(&r, is->xleft, is->ytop, is->width, is->height, np->width, np->height, np->sar);
    set_sdl_yuv_conversion_mode(np->frame);
    if (!np->uploaded) {
        if (upload_texture(&xf->vid_texture, np->frame) < 0) {
            set_sdl_yuv_conversion_mode(NULL);
            return;
        }
        np->uploaded = 1;
        np->flip_v = np->frame->linesize[0] < 0;
    }
    SDL_SetTextureBlendMode(xf->vid_texture, SDL_BLENDMODE_BLEND);
    SDL_SetTextureAlphaMod(xf->vid_texture, (Uint8)(255.0 * av_clipd(ui_xf_t, 0.0, 1.0)));
    SDL_RenderCopyEx(renderer, xf->vid_texture, NULL, &r, 0, NULL, np->flip_v ? SDL_FLIP_VERTICAL : 0);
    SDL_SetTextureAlphaMod(xf->vid_texture, 255);
    set_sdl_yuv_conversion_mode(NULL);
}

static void ui_xf_abort(void)
{
    ui_xf_t = 0.0;""", "crossfade drawing")

patch("        xf->xf_gain = (float)sin(t * M_PI / 2);\n",
      "        xf->xf_gain = (float)sin(t * M_PI / 2);\n        ui_xf_t = t;                            /* the picture fades in the same way */\n",
      "crossfade progress")

# ============================================================ smooth seeking: steps of 0.3 and 0.5 s, exact landing, 20 seeks a second
patch("static const int ui_seek_steps[] = { 1, 2, 3, 5, 10, 15, 30 };",
      "static const av_unused int ui_seek_steps[] = { 1, 2, 3, 5, 10, 15, 30 };",
      "old seek steps")

patch("    case 0: cfg_seek = ui_step_list(ui_seek_steps, 7, cfg_seek, dir); break;",
      """    case 0: {
        static const double st[] = { 0.3, 0.5, 1, 2, 3, 5, 10, 15, 30 };
        int b = 0, k;

        for (k = 1; k < 9; k++)
            if (fabs(st[k] - cfg_seek) < fabs(st[b] - cfg_seek))
                b = k;
        cfg_seek = st[av_clip(b + dir, 0, 8)];
        break;
    }""", "seek steps with 0.3 and 0.5 s")

patch("static void stream_seek(VideoState *is, int64_t pos, int64_t rel, int by_bytes);\n\nstatic int ui_hover = 0;",
      "static void stream_seek(VideoState *is, int64_t pos, int64_t rel, int by_bytes);\n#define UI_PRECISE_SEEK 1                /* 0 = seek to the nearest key frame, as before */\nstatic int ui_precise_next = 0;         /* 1 = the next seek must land exactly on its time */\n\nstatic int ui_hover = 0;",
      "precise seek flag")

patch("static void stream_seek(VideoState *is, int64_t pos, int64_t rel, int by_bytes)\n{\n    if (!is->seek_req) {\n        is->seek_pos = pos;\n        is->seek_rel = rel;",
      "static void stream_seek(VideoState *is, int64_t pos, int64_t rel, int by_bytes)\n{\n    int prec = UI_PRECISE_SEEK ? ui_precise_next : 0;\n\n    ui_precise_next = 0;\n    if (!is->seek_req) {\n        is->seek_pos = pos;\n        is->seek_rel = rel;\n        is->seek_precise = prec && !by_bytes;",
      "stream_seek keeps the flag")

patch("    ui_seek_next = now + 100000;        /* about 10 seeks a second while dragging */",
      "    ui_seek_next = now + 50000;         /* about 20 seeks a second while dragging */",
      "20 seeks a second")

patch("        if (is->ic->start_time != AV_NOPTS_VALUE)\n            ts += is->ic->start_time;\n        stream_seek(is, ts, 0, 0);",
      "        if (is->ic->start_time != AV_NOPTS_VALUE)\n            ts += is->ic->start_time;\n        ui_precise_next = force;        /* the last seek of a drag lands exactly */\n        stream_seek(is, ts, 0, 0);",
      "exact landing after a drag")

patch("        stream_seek(is, (int64_t)(pos * AV_TIME_BASE), (int64_t)(incr * AV_TIME_BASE), 0);\n    }\n}\n\n/* The mouse wheel",
      "        ui_precise_next = 1;\n        stream_seek(is, (int64_t)(pos * AV_TIME_BASE), (int64_t)(incr * AV_TIME_BASE), 0);\n    }\n}\n\n/* The mouse wheel",
      "exact landing for wheel seeks")

patch("                        stream_seek(cur_stream, (int64_t)(pos * AV_TIME_BASE), (int64_t)(incr * AV_TIME_BASE), 0);",
      "                        ui_precise_next = 1;\n                        stream_seek(cur_stream, (int64_t)(pos * AV_TIME_BASE), (int64_t)(incr * AV_TIME_BASE), 0);",
      "exact landing for key seeks")

patch("            int64_t seek_max    = is->seek_rel < 0 ? seek_target - is->seek_rel - 2: INT64_MAX;\n",
      "            int64_t seek_max    = is->seek_rel < 0 ? seek_target - is->seek_rel - 2: INT64_MAX;\n"
      "            if (is->seek_precise && !(is->seek_flags & AVSEEK_FLAG_BYTE)) {\n"
      "                seek_min = INT64_MIN;           /* exact landing: start at the key frame before the time, */\n"
      "                seek_max = seek_target;         /* the pictures and sound before it are skipped */\n"
      "            }\n",
      "seek window for exact landing")

patch("                if (is->seek_flags & AVSEEK_FLAG_BYTE) {\n                   set_clock(&is->extclk, NAN, 0);\n                } else {\n                   set_clock(&is->extclk, seek_target / (double)AV_TIME_BASE, 0);\n                }",
      "                if (is->seek_flags & AVSEEK_FLAG_BYTE) {\n                   set_clock(&is->extclk, NAN, 0);\n                } else {\n                   set_clock(&is->extclk, seek_target / (double)AV_TIME_BASE, 0);\n                }\n"
      "                is->prec_v = is->prec_a = 0;\n"
      "                if (is->seek_precise && !(is->seek_flags & AVSEEK_FLAG_BYTE)) {\n"
      "                    is->prec_target = seek_target / (double)AV_TIME_BASE;\n"
      "                    if (is->video_stream >= 0 && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC)) {\n"
      "                        is->prec_ser_v = is->videoq.serial;\n                        is->prec_v = 1;\n                    }\n"
      "                    if (is->audio_stream >= 0) {\n"
      "                        is->prec_ser_a = is->audioq.serial;\n                        is->prec_a = 1;\n                    }\n"
      "                }\n",
      "skipping starts after the seek")

patch("static int get_video_frame(VideoState *is, AVFrame *frame)\n{",
      """/* After an exact seek: pictures and sound before the wanted time are thrown away */
static int ui_prec_skip_v(VideoState *is, double pts)
{
    if (!is->prec_v || is->viddec.pkt_serial != is->prec_ser_v || isnan(pts))
        return 0;
    if (pts + 0.001 < is->prec_target)
        return 1;
    is->prec_v = 0;
    return 0;
}

static int ui_prec_skip_a(VideoState *is, AVFrame *frame)
{
    double end;

    if (!is->prec_a || is->auddec.pkt_serial != is->prec_ser_a || frame->pts == AV_NOPTS_VALUE || frame->sample_rate <= 0)
        return 0;
    end = (frame->pts + frame->nb_samples) / (double)frame->sample_rate;
    if (end <= is->prec_target)
        return 1;
    is->prec_a = 0;
    return 0;
}

static int get_video_frame(VideoState *is, AVFrame *frame)
{""", "skip helpers")

patch("        frame->sample_aspect_ratio = av_guess_sample_aspect_ratio(is->ic, is->video_st, frame);\n\n        if (framedrop>0",
      "        frame->sample_aspect_ratio = av_guess_sample_aspect_ratio(is->ic, is->video_st, frame);\n\n"
      "        if (ui_prec_skip_v(is, dpts)) {\n            av_frame_unref(frame);\n            return 0;\n        }\n\n        if (framedrop>0",
      "skip pictures before the time")

patch("        if ((got_frame = decoder_decode_frame(&is->auddec, frame, NULL)) < 0)\n            goto the_end;\n\n        if (got_frame) {\n                tb = (AVRational){1, frame->sample_rate};",
      "        if ((got_frame = decoder_decode_frame(&is->auddec, frame, NULL)) < 0)\n            goto the_end;\n\n"
      "        if (got_frame && ui_prec_skip_a(is, frame)) {\n            av_frame_unref(frame);\n            got_frame = 0;\n        }\n\n"
      "        if (got_frame) {\n                tb = (AVRational){1, frame->sample_rate};",
      "skip sound before the time")

patch("    ui_idle = 1;\n    ui_menu_open = 0;\n    ui_menu_hover = -1;",
      "    SDL_SetWindowTitle(window, \"ffplay-custom\");      /* the idle screen has no item name */\n    ui_idle = 1;\n    ui_menu_open = 0;\n    ui_menu_hover = -1;",
      "idle screen title")

patch("    xf_stream = xf;\n    xf_name = q_items[next];",
      "    ui_xf_t = 0.0;\n    xf_stream = xf;\n    xf_name = q_items[next];",
      "crossfade starts from nothing")

# ============================================================ the window is shown once (from the other account's v24)
patch("static int video_open(VideoState *is)\n{\n    int w,h;\n",
      "static int ui_shown_once = 0;   /* the window is shown once; later items leave its place and workspace alone */\n\nstatic int video_open(VideoState *is)\n{\n    int w,h;\n",
      "video_open declaration")

patch("""    SDL_SetWindowSize(window, w, h);
    SDL_SetWindowPosition(window, screen_left, screen_top);
    if (is_full_screen)
        SDL_SetWindowFullscreen(window, SDL_WINDOW_FULLSCREEN_DESKTOP);
    SDL_ShowWindow(window);
""", """    {
        int tiled = 0, cw = 0, ch = 0;
        SDL_Rect ub;

        if (ui_shown_once && !is_full_screen && SDL_GetDisplayUsableBounds(SDL_GetWindowDisplayIndex(window), &ub) == 0) {
            SDL_GetWindowSize(window, &cw, &ch);
            tiled = ch >= ub.h - 8 || cw >= ub.w - 8;       /* maximized or tiled by the window manager: its size stays */
        }
        if (tiled) {
            w = cw;
            h = ch;
        } else {
            SDL_SetWindowSize(window, w, h);
        }
        if (!ui_shown_once)
            SDL_SetWindowPosition(window, screen_left, screen_top);
        if (is_full_screen)
            SDL_SetWindowFullscreen(window, SDL_WINDOW_FULLSCREEN_DESKTOP);
        if (!ui_shown_once) {
            SDL_ShowWindow(window);         /* only the first time: showing it again would raise it, even from another workspace */
            ui_shown_once = 1;
        }
    }
""", "no re-raising and no re-centering for every item")

patch("    if (!SDL_GetWindowFlags(window) || !(SDL_GetWindowFlags(window) & SDL_WINDOW_SHOWN)) {\n        SDL_SetWindowTitle(window, \"ffplay-custom\");",
      "    if (!ui_shown_once && (!SDL_GetWindowFlags(window) || !(SDL_GetWindowFlags(window) & SDL_WINDOW_SHOWN))) {\n        SDL_SetWindowTitle(window, \"ffplay-custom\");",
      "the idle screen shows the window only once")

patch("        SDL_ShowWindow(window);\n        if (is_full_screen)\n            SDL_SetWindowFullscreen(window, SDL_WINDOW_FULLSCREEN_DESKTOP);\n    }\n    if (cursor_hidden) {",
      "        SDL_ShowWindow(window);\n        ui_shown_once = 1;\n        if (is_full_screen)\n            SDL_SetWindowFullscreen(window, SDL_WINDOW_FULLSCREEN_DESKTOP);\n    }\n    if (cursor_hidden) {",
      "the idle screen remembers it showed the window")

open(path, "w").write(src)
print("Patched fftools/ffplay.c")
