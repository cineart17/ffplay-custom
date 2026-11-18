#!/usr/bin/env python3
# Update 35 for ffplay-custom (on top of patch_queue_v34.py).
# The three window states:
#   complete full screen (the whole display, no title bar, no resizing)
#   the conventional window (the window that fills the screen under the panel, or a window you sized, with the title bar,
#                            resizable at the corners)
#   the miniplayer (a small conventional window, on top, resizable at the corners)
#   * Leaving the miniplayer brings back exactly the state it was entered from. Before, a window that filled the screen came
#     back as a smaller window, because the miniplayer un-filled it and nothing filled it again. "On top" is put back
#     as it was, too.
#   * Esc in complete full screen does what a double tap does: it goes to the conventional window that fills the screen.
#     Esc in the miniplayer leaves the miniplayer.
#   * F or a double tap in the miniplayer leave it (back to where it was entered from) and go to complete full screen.
#   * The blur that melts away when the window comes back from out of sight has a switch: UI_WBLUR_RETURN (0 = no blur).
#   * Liquid glass: the smoked veil is a little stronger (80 to 130), so the white text can be read on a bright picture.
#   * The log file starts each run with the session type (x11 or wayland), the video driver, the renderer and the SDL version.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v34.py. Writes the file only if every edit matches.
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


if "ui_pip_was_top" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_pip_toggle" not in src:
    print("Apply patch_queue_v34.py first. Nothing written.")
    sys.exit(1)

patch("miniplayer state", r'''static int ui_pip = 0;''',
      r'''static int ui_pip = 0, ui_pip_was_top = 0, ui_pip_was_max = 0;     /* (was_top, was_max: how the window was before the miniplayer) */''')
patch("miniplayer end: the window is as it was", r'''    ui_pip = 0;
    ui_on_top = 0;
    SDL_SetWindowAlwaysOnTop(window, SDL_FALSE);''', r'''    ui_pip = 0;
    ui_on_top = ui_pip_was_top;                 /* on top again only if it was before */
    SDL_SetWindowAlwaysOnTop(window, ui_pip_was_top ? SDL_TRUE : SDL_FALSE);''')
patch("miniplayer end: the window that filled the screen fills it again", r'''    ui_keep_w = ui_pip_kw;
    ui_keep_h = ui_pip_kh;
}''', r'''    ui_keep_w = ui_pip_kw;
    ui_keep_h = ui_pip_kh;
    if (ui_pip_was_max)
        ui_max_set(1);                          /* it was the conventional window that fills the screen: it fills it again */
}''')
patch("miniplayer remembers the window that filled the screen", r'''    if (ui_maxed)
        ui_max_set(0);
    ui_fs_toggle_at = av_gettime_relative();
    ui_prog_until = ui_fs_toggle_at + 2000000;
    SDL_GetWindowPosition(window, &ui_pip_x, &ui_pip_y);''', r'''    ui_pip_was_max = ui_maxed;
    if (ui_maxed)
        ui_max_set(0);
    ui_fs_toggle_at = av_gettime_relative();
    ui_prog_until = ui_fs_toggle_at + 2000000;
    SDL_GetWindowPosition(window, &ui_pip_x, &ui_pip_y);''')
patch("miniplayer remembers on top", r'''    SDL_SetWindowAlwaysOnTop(window, SDL_TRUE);
    ui_on_top = 1;
    ui_pip = 1;''', r'''    ui_pip_was_top = ui_on_top;
    SDL_SetWindowAlwaysOnTop(window, SDL_TRUE);
    ui_on_top = 1;
    ui_pip = 1;''')
patch("Esc: complete full screen goes to the conventional window; the miniplayer ends", r'''                } else if (is_full_screen) {
                    toggle_full_screen(cur_stream);
                    cur_stream->force_refresh = 1;
                } else if (ui_maxed) {
                    ui_max_set(0);
                    cur_stream->force_refresh = 1;
                }
                break;
            }
            if (exit_on_keydown || event.key.keysym.sym == SDLK_q) {''', r'''                } else if (is_full_screen) {
                    ui_fs_cycle(cur_stream);            /* like a double tap: the conventional window that fills the screen */
                    cur_stream->force_refresh = 1;
                } else if (ui_pip) {
                    ui_pip_end();                       /* the miniplayer ends: back to where it was entered from */
                    cur_stream->force_refresh = 1;
                } else if (ui_maxed) {
                    ui_max_set(0);
                    cur_stream->force_refresh = 1;
                }
                break;
            }
            if (exit_on_keydown || event.key.keysym.sym == SDLK_q) {''')
patch("blur switch (declaration)", r'''#define UI_WBLUR_AWAY 0.0 ''', r'''#define UI_WBLUR_RETURN 0.85            /* how soft the picture is when the window comes back from out of sight, melting away (0 = no blur at all) */
#define UI_WBLUR_AWAY 0.0 ''')
patch("blur switch", r'''        ui_wblur = FFMAX(ui_wblur, 0.85);       /* the picture comes back soft and sharpens, it does not jump */''',
      r'''        ui_wblur = FFMAX(ui_wblur, UI_WBLUR_RETURN);    /* the picture comes back soft and sharpens, it does not jump */''')
patch("a stronger smoked veil", r'''28 + cfg_bar_b / 16, 80, 1);     /* the blurred picture, under a smoked veil */''',
      r'''28 + cfg_bar_b / 16, 130, 1);    /* the blurred picture, under a smoked veil (strong enough for white text on a bright picture) */''')
patch("the log says where it runs", r'''    fprintf(ui_logf, "---- started: video driver %s\n", drv ? drv : "?");''', r'''    {
        SDL_RendererInfo ri;
        SDL_version sv;
        const char *st = getenv("XDG_SESSION_TYPE");

        SDL_GetVersion(&sv);
        if (!renderer || SDL_GetRendererInfo(renderer, &ri) != 0)
            ri.name = "?";
        fprintf(ui_logf, "---- started: session %s, video driver %s, renderer %s, SDL %d.%d.%d\n", st ? st : "?",
                drv ? drv : "?", ri.name, sv.major, sv.minor, sv.patch);
    }''')

if fails:
    print("\n%d edits did not apply. Nothing was written." % len(fails))
    sys.exit(1)
open(PATH, "w").write(src)
print("Patched " + PATH)
