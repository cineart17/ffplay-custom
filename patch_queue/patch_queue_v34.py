#!/usr/bin/env python3
# Update 34 for ffplay-custom (on top of patch_queue_v33.py).
#   * Window size bug (the picture and the bar stay small in a corner after the window got bigger): the player's idea
#     of the window size could go out of date and nothing put it right. Now, when it differs from the real window size
#     for more than 0.3 s, the picture follows the window (and a line in the log file says so).
#   * Picture in picture: a new button in the title bar, left of the full screen button. It makes the window a small
#     miniplayer (about a quarter of the screen width, in the video's shape, bottom right, on top of other windows). It can
#     be resized by its corners and moved by the title bar. The next items of the queue keep its size. The button again
#     (or F, or a double tap) gives the window its old size and place back.
#   * Waveform like the reference picture: the part that has played is in the bar color, the rest is dim, with the time
#     played on the left and the time left on the right. Finer detail (480 steps) and a milder height.
#   * Generic liquid glass for the menus, the preferences and the panels: the blurred picture behind, a smoked veil,
#     no rim, and white text.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v33.py. Writes the file only if every edit matches.
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
    """Replace from start (found once) up to, but not including, end."""
    global src
    a = src.find(start)
    b = src.find(end, a + 1) if a >= 0 else -1
    if a < 0 or b < 0 or src.count(start) != 1:
        print("FAILED: %s matched %d times" % (name, src.count(start)))
        fails.append(name)
        return
    src = src[:a] + new + src[b:]
    print("ok: " + name)


def between_incl(name, start, end, new):
    """Replace from start (found once) up to and including end (found once)."""
    global src
    if src.count(start) != 1 or src.count(end) != 1:
        print("FAILED: %s start matched %d times, end matched %d times" % (name, src.count(start), src.count(end)))
        fails.append(name)
        return
    a = src.index(start)
    b = src.index(end, a) + len(end)
    src = src[:a] + new + src[b:]
    print("ok: " + name)


if "ui_pip_toggle" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_scrub_draw" not in src:
    print("Apply patch_queue_v33.py first. Nothing written.")
    sys.exit(1)

patch('the picture follows the real window size',
      r'''    if (ui_win_unseen())
        return;                     /* minimized or hidden: nothing to draw */

    if (ui_bg) {''',
      r'''    if (ui_win_unseen())
        return;                     /* minimized or hidden: nothing to draw */

    {                                           /* the window's real size wins: a picture sized for an old window sits small in a corner */
        static int64_t since = 0;
        int cw, ch;

        SDL_GetWindowSize(window, &cw, &ch);
        if (cw > 0 && ch > 0 && (cw != is->width || ch != is->height)) {
            int64_t t_ = av_gettime_relative();

            if (!since) {
                since = t_;
            } else if (t_ - since > 300000) {   /* not a size change on its way: follow the window */
                av_log(NULL, AV_LOG_WARNING, "ffplay-custom: the picture was sized for %dx%d but the window is %dx%d: following the window\n",
                       is->width, is->height, cw, ch);
                screen_width = is->width = cw;
                screen_height = is->height = ch;
                if (is->vis_texture) {
                    SDL_DestroyTexture(is->vis_texture);
                    is->vis_texture = NULL;
                }
                since = 0;
            }
        } else {
            since = 0;
        }
    }

    if (ui_bg) {''')
patch('full screen ends the miniplayer',
      r'''static void toggle_full_screen(VideoState *is)
{
    is_full_screen = !is_full_screen;''',
      r'''static void ui_pip_end(void);

static void toggle_full_screen(VideoState *is)
{
    ui_pip_end();                               /* the miniplayer ends before full screen */
    is_full_screen = !is_full_screen;''')
patch('a double tap ends the miniplayer',
      r'''static void ui_fs_cycle(VideoState *is)
{
''',
      r'''static void ui_fs_cycle(VideoState *is)
{
    ui_pip_end();
''')
patch('picture in picture: state and toggle',
      r'''static void ui_titlebar_draw(VideoState *is)
{''',
      r'''/* ----- picture in picture: the window as a small miniplayer on top, in a corner ----- */
static int ui_pip = 0;
static int ui_pip_x, ui_pip_y, ui_pip_w, ui_pip_h, ui_pip_user, ui_pip_kw, ui_pip_kh;     /* the window as it was */

static void ui_pip_end(void)
{
    if (!ui_pip || !window)
        return;
    ui_pip = 0;
    ui_on_top = 0;
    SDL_SetWindowAlwaysOnTop(window, SDL_FALSE);
    ui_fs_toggle_at = av_gettime_relative();    /* the sizes that follow are ours, not the user's */
    ui_prog_until = ui_fs_toggle_at + 2000000;
    ui_prog_w = ui_pip_w;
    ui_prog_h = ui_pip_h;
    SDL_SetWindowSize(window, ui_pip_w, ui_pip_h);
    SDL_SetWindowPosition(window, ui_pip_x, ui_pip_y);
    ui_user_sized = ui_pip_user;
    ui_keep_w = ui_pip_kw;
    ui_keep_h = ui_pip_kh;
}

static void ui_pip_toggle(VideoState *is)
{
    SDL_Rect ub;
    int di, cw = 16, ch = 9, w, h;

    if (!window)
        return;
    if (ui_pip) {
        ui_pip_end();
        if (is)
            is->force_refresh = 1;
        return;
    }
    if (is_full_screen) {                       /* leave full screen first, and wait (at most 0.4 s) for the window manager */
        int64_t t0 = av_gettime_relative();

        is_full_screen = 0;
        SDL_SetWindowFullscreen(window, 0);
        SDL_PumpEvents();
        while (av_gettime_relative() - t0 < 400000 &&
               (SDL_GetWindowFlags(window) & (SDL_WINDOW_FULLSCREEN | SDL_WINDOW_FULLSCREEN_DESKTOP))) {
            SDL_Delay(10);
            SDL_PumpEvents();
        }
    }
    if (ui_maxed)
        ui_max_set(0);
    ui_fs_toggle_at = av_gettime_relative();
    ui_prog_until = ui_fs_toggle_at + 2000000;
    SDL_GetWindowPosition(window, &ui_pip_x, &ui_pip_y);
    SDL_GetWindowSize(window, &ui_pip_w, &ui_pip_h);
    ui_pip_user = ui_user_sized;
    ui_pip_kw = ui_keep_w;
    ui_pip_kh = ui_keep_h;
    if (is && is->video_st && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC) &&
        is->video_st->codecpar->width > 0 && is->video_st->codecpar->height > 0) {
        cw = is->video_st->codecpar->width;     /* the miniplayer has the video's shape */
        ch = is->video_st->codecpar->height;
    }
    di = SDL_GetWindowDisplayIndex(window);
    if (di < 0)
        di = 0;
    if (SDL_GetDisplayUsableBounds(di, &ub) != 0) {
        ub.x = 0;
        ub.y = 0;
        ub.w = 1280;
        ub.h = 720;
    }
    w = av_clip(ub.w / 4, 360, 640);
    h = av_clip(w * ch / cw, 160, FFMAX(ub.h / 2, 160));
    SDL_SetWindowSize(window, w, h);
    SDL_SetWindowPosition(window, ub.x + ub.w - w - 24, ub.y + ub.h - h - 24);
    ui_prog_w = w;
    ui_prog_h = h;
    SDL_SetWindowAlwaysOnTop(window, SDL_TRUE);
    ui_on_top = 1;
    ui_pip = 1;
    ui_user_sized = 1;                          /* the next items of the queue keep the miniplayer's size */
    ui_keep_w = w;
    ui_keep_h = h;
    if (is)
        is->force_refresh = 1;
}

static void ui_titlebar_draw(VideoState *is)
{''')
patch('title bar: hover on the new button',
      r'''            ui_tb_hover = (mx >= UI_TB_PAD && mx < UI_TB_PAD + UI_TB_BTN) ? 1 :
                          (mx >= w - UI_TB_PAD - UI_TB_BTN && mx < w - UI_TB_PAD) ? 2 : 0;''',
      r'''            ui_tb_hover = (mx >= UI_TB_PAD && mx < UI_TB_PAD + UI_TB_BTN) ? 1 :
                          (mx >= w - UI_TB_PAD - UI_TB_BTN && mx < w - UI_TB_PAD) ? 2 :
                          (mx >= w - UI_TB_PAD - 2 * UI_TB_BTN && mx < w - UI_TB_PAD - UI_TB_BTN) ? 3 : 0;''')
patch('title bar: highlight of the new button',
      r'''ui_fan(ui_tb_hover == 1 ? cx1 : cx2, cy, 12,''',
      r'''ui_fan(ui_tb_hover == 1 ? cx1 : ui_tb_hover == 3 ? cx2 - UI_TB_BTN : cx2, cy, 12,''')
patch('title bar: the picture in picture icon',
      r'''    if (ui_on_top)                              /* a small dot: the window stays on top */
''',
      r'''    {                                           /* picture in picture: a window with a small window in its corner */
        int px = cx2 - UI_TB_BTN;
        SDL_Rect corner;

        SDL_SetRenderDrawColor(renderer, 245, 245, 245, ui_tb_hover == 3 ? 255 : 200);
        ui_tb_line(px - 7, cy - 5, px + 7, cy - 5, 1.6);
        ui_tb_line(px - 7, cy + 5, px + 7, cy + 5, 1.6);
        ui_tb_line(px - 7, cy - 5, px - 7, cy + 5, 1.6);
        ui_tb_line(px + 7, cy - 5, px + 7, cy + 5, 1.6);
        corner.x = px + 1;
        corner.y = cy;
        corner.w = 6;
        corner.h = 5;
        SDL_RenderFillRect(renderer, &corner);
    }
    if (ui_on_top)                              /* a small dot: the window stays on top */
''')
patch('title bar: room for the title',
      r'''ui_fit_text(name, 14, w - 2 * (UI_TB_PAD + UI_TB_BTN + 16));''',
      r'''ui_fit_text(name, 14, w - 2 * (UI_TB_PAD + 2 * UI_TB_BTN + 16));''')
patch('title bar: the new button is not a place to drag',
      r'''area->x >= UI_TB_PAD + UI_TB_BTN && area->x < w - UI_TB_PAD - UI_TB_BTN)''',
      r'''area->x >= UI_TB_PAD + UI_TB_BTN && area->x < w - UI_TB_PAD - 2 * UI_TB_BTN)''')
patch('title bar: click on the new button',
      r'''        hover = (x >= UI_TB_PAD && x < UI_TB_PAD + UI_TB_BTN) ? 1 : (x >= w - UI_TB_PAD - UI_TB_BTN && x < w - UI_TB_PAD) ? 2 : 0;''',
      r'''        hover = (x >= UI_TB_PAD && x < UI_TB_PAD + UI_TB_BTN) ? 1 : (x >= w - UI_TB_PAD - UI_TB_BTN && x < w - UI_TB_PAD) ? 2 :
                (x >= w - UI_TB_PAD - 2 * UI_TB_BTN && x < w - UI_TB_PAD - UI_TB_BTN) ? 3 : 0;''')
patch('title bar: the new button toggles picture in picture',
      r'''    } else {
        toggle_full_screen(is);
        if (is)''',
      r'''    } else if (hover == 3) {
        ui_pip_toggle(is);
        if (is)
            is->force_refresh = 1;
    } else {
        toggle_full_screen(is);
        if (is)''')
patch('finer waveform steps',
      r'''#define UI_WAVE_N 200''',
      r'''#define UI_WAVE_N 480''')
patch('room for the times beside the wave',
      r'''int x0 = 24, span = W - 48, bars_ok = 1;''',
      r'''int lab_w = W >= 520 ? 56 : 0, x0 = 24 + lab_w, span = W - 48 - 2 * lab_w, bars_ok = 1;''')
patch('glass: a smoked veil',
      r'''ui_liquid(t, r, 225 + cfg_bar_r / 10, 228 + cfg_bar_g / 10, 232 + cfg_bar_b / 10, 165, 1);''',
      r'''ui_liquid(t, r, 22 + cfg_bar_r / 16, 24 + cfg_bar_g / 16, 28 + cfg_bar_b / 16, 80, 1);     /* the blurred picture, under a smoked veil */''')
patch('glass: white text in the preferences',
      r'''    ui_ink_dark = 1;                            /* the preferences are light glass: dark text on them */''',
      r'''    ui_ink_dark = 0;                            /* the glass is smoked: white text on it */''')
patch('glass: white text on the card',
      r'''    ui_ink_dark = !ui_idle;                     /* the card is light glass: dark text on it (the idle screen has no card) */''',
      r'''    ui_ink_dark = 0;                            /* white text on the card */''')
patch('glass: white text on the side panels',
      r'''    ui_ink_dark = 1;                            /* the side panels are light glass too */''',
      r'''    ui_ink_dark = 0;                            /* white text on the side panels */''')
patch('the played part and the times: the playhead',
      r'''            double grow, half = FFMAX(maxh / 2.0 - 1.5, 1.0);
''',
      r'''            double grow, half = FFMAX(FFMIN(maxh, 120) / 2.0 - 1.5, 1.0);      /* a milder height */
            static double wkeep = 0.0;                  /* the last good time, for the moments the clock has none */
            double wpos = get_master_clock(is), wdur = is->ic ? is->ic->duration / (double)AV_TIME_BASE : 0.0, wfrac = 0.0;
            int wpr = av_clip(cfg_bar_r + 40, 0, 255), wpg = av_clip(cfg_bar_g + 40, 0, 255), wpb = av_clip(cfg_bar_b + 40, 0, 255);

            if (isnan(wpos))
                wpos = wkeep;
            else
                wkeep = wpos;
            if (is->ic && is->ic->start_time != AV_NOPTS_VALUE)
                wpos -= is->ic->start_time / (double)AV_TIME_BASE;
            if (wdur > 0.0)
                wfrac = av_clipd(wpos / wdur, 0.0, 1.0);        /* how much of the track has played */
''')
patch('the played part: which columns',
      r'''                double hh = 1.5 + av_clipd(h2[c], 0.0, 1.0) * half * grow;
                int k;
''',
      r'''                double hh = 1.5 + av_clipd(h2[c], 0.0, 1.0) * half * grow;
                int k;
                int pl = c <= (int)(wfrac * (nc - 1));          /* the part that has played: the bar color */
''')
patch('the played part is in the bar color',
      r'''                    wf[c * 4 + k].color.r = wf[c * 4 + k].color.g = wf[c * 4 + k].color.b = 255;
                    wf[c * 4 + k].color.a = (k == 0 || k == 3) ? 0 : (Uint8)ab;
''',
      r'''                    wf[c * 4 + k].color.r = pl ? wpr : 255;
                    wf[c * 4 + k].color.g = pl ? wpg : 255;
                    wf[c * 4 + k].color.b = pl ? wpb : 255;
                    wf[c * 4 + k].color.a = (k == 0 || k == 3) ? 0 : (Uint8)(pl ? 235 * nal / 255 : ab);
''')
patch('the times beside the wave',
      r'''            SDL_RenderGeometry(renderer, NULL, wf, nc * 4, wi, ni);
''',
      r'''            SDL_RenderGeometry(renderer, NULL, wf, nc * 4, wi, ni);
            if (lab_w) {                                /* the time played on the left, the time left on the right */
                char t1[32], t2[32];
                int e1 = (int)FFMAX(wpos, 0.0), e2 = (int)FFMAX(wdur - wpos, 0.0);

                if (e1 >= 3600)
                    snprintf(t1, sizeof(t1), "%d:%02d:%02d", e1 / 3600, e1 / 60 % 60, e1 % 60);
                else
                    snprintf(t1, sizeof(t1), "%d:%02d", e1 / 60, e1 % 60);
                if (e2 >= 3600)
                    snprintf(t2, sizeof(t2), "%d:%02d:%02d", e2 / 3600, e2 / 60 % 60, e2 % 60);
                else
                    snprintf(t2, sizeof(t2), "%d:%02d", e2 / 60, e2 % 60);
                ui_label_c(24 + lab_w / 2, mid, t1, 15, 235, 235, 235, nal);
                ui_label_c(W - 24 - lab_w / 2, mid, t2, 15, 235, 235, 235, nal);
            }
''')

if fails:
    print("\n%d edits did not apply. Nothing was written." % len(fails))
    sys.exit(1)
open(PATH, "w").write(src)
print("Patched " + PATH)
