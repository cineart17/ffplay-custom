#!/usr/bin/env python3
# Update 43 for ffplay-custom (on top of patch_queue_v42.py).
#   * Rearranging in the tiled view: while a tile is held and dragged, the view scrolls when the mouse is near the left or right
#     edge (along the rows), or near the top or bottom (between the rows). The nearer the edge, the faster. Drop it where you want.
#   * The tiles that are not in focus are not as dark: they fade less with the distance from the focus and from the row in focus,
#     and are dimmed less, so the titles and pictures can be read.
#   * Leaving the tiled view over a video: the title (and its dot and glow) of the playing tile fades away with the video growing
#     back, instead of staying on the picture, and the growing back ends sooner.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v42.py. Writes the file only if every edit matches.
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


if "v43" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_pick_attach_thread" not in src:
    print("Apply patch_queue_v42.py first. Nothing written.")
    sys.exit(1)

patch("the view scrolls at the edge while a tile is dragged", r'''        g.h = (int)FFMIN(H * 0.2, 140);
        g.w = asp > 0.0 ? (int)(g.h * asp) : g.h;''', r'''        {                                       /* v43: near an edge the view scrolls, so the tile can be taken further than the ones in sight */
            static int64_t last_scroll = 0;
            double ex = FFMIN(W * 0.09, 170.0), ey = FFMIN(H * 0.13, 130.0), depth = 0.0;
            int dx = 0, dy = 0;

            if (ui_hov_x >= 0 && ui_hov_x < ex) {
                dx = -1;
                depth = 1.0 - ui_hov_x / ex;
            } else if (ui_hov_x > W - ex) {
                dx = 1;
                depth = 1.0 - (W - ui_hov_x) / ex;
            }
            if (ui_hov_y >= 0 && ui_hov_y < ey) {
                dy = -1;
                depth = FFMAX(depth, 1.0 - ui_hov_y / ey);
            } else if (ui_hov_y > H - ey) {
                dy = 1;
                depth = FFMAX(depth, 1.0 - (H - ui_hov_y) / ey);
            }
            if ((dx || dy) && !ui_tv_q[0]) {
                if (now - last_scroll > (int64_t)((400.0 - 280.0 * av_clipd(depth, 0.0, 1.0)) * 1000.0)) {
                    last_scroll = now;
                    ui_tv_step(is, dx, dy);     /* one tile (or row) at a time, quicker the nearer the edge */
                }
                ui_tv_moving = 1;
            }
        }
        g.h = (int)FFMIN(H * 0.2, 140);
        g.w = asp > 0.0 ? (int)(g.h * asp) : g.h;''')

patch("tiles not in focus are lighter", r'''        al = (int)(255 * av_clipd(1.05 - 0.26 * d, 0.18, 1.0) * av_clipd(1.0 - 0.5 * R->rowd, 0.55, 1.0));
        md = (int)(255 * av_clipd(1.0 - 0.22 * FFMIN(d, 2.2), 0.45, 1.0));''',
      r'''        al = (int)(255 * av_clipd(1.05 - 0.17 * d, 0.5, 1.0) * av_clipd(1.0 - 0.25 * R->rowd, 0.78, 1.0));     /* v43: lighter than before, so they can be read */
        md = (int)(255 * av_clipd(1.0 - 0.12 * FFMIN(d, 2.5), 0.72, 1.0));''')

patch("the glow of the playing tile fades with the video", r'''            ui_tv_glow(tile.x + tile.w / 2.0, tile.y + tile.h / 2.0, tile.w * 0.95, tile.h * 0.95, (int)(120 * (1.0 - d / 0.6) * (al / 255.0)));''',
      r'''            ui_tv_glow(tile.x + tile.w / 2.0, tile.y + tile.h / 2.0, tile.w * 0.95, tile.h * 0.95,
                       (int)(120 * (1.0 - d / 0.6) * (((vm && R->sec < 0 && play) ? al * ep * ep : al) / 255.0)));''')

patch("the title of the playing tile fades with the video", r'''        if (play) {                             /* the dot of the item that plays, before its title */
            SDL_Rect pdot;
            int tw = ui_text_width(name, px);
''', r'''        la = (vm && R->sec < 0 && play) ? (int)(al * ep * ep) : al;     /* v43: over a video the title goes with the video growing back */
        if (play) {                             /* the dot of the item that plays, before its title */
            SDL_Rect pdot;
            int tw = ui_text_width(name, px);
''')
patch("title alpha declared", r'''        int c = ord[o].c, item = R->sec < 0 ? R->first + c : c, play, nw, nh, al, md, tx, ty, ti;''',
      r'''        int c = ord[o].c, item = R->sec < 0 ? R->first + c : c, play, nw, nh, al, md, tx, ty, ti, la;''')
patch("dot alpha", r'''av_clip(cfg_bar_b + 40, 0, 255), (int)(235 * al / 255.0));
            ui_pill(&pdot);''', r'''av_clip(cfg_bar_b + 40, 0, 255), (int)(235 * la / 255.0));
            ui_pill(&pdot);''')
patch("title alpha", r'''(int)(al * (d < 0.6 ? 1.0 : 0.75 + 0.25 * lf)));
        if (ui_tvh_n < 128) {''', r'''(int)(la * (d < 0.6 ? 1.0 : 0.75 + 0.25 * lf)));
        if (ui_tvh_n < 128) {''')

patch("growing back ends sooner", r'''        ui_vflow_p += (want - ui_vflow_p) * (1.0 - exp(-dtv * (want > 0.5 ? 8.0 : 12.0)));      /* growing back is quicker */
        if (fabs(want - ui_vflow_p) < 0.004)
            ui_vflow_p = want;
        ui_vflow_ep = ui_vflow_p * ui_vflow_p * (3.0 - 2.0 * ui_vflow_p);
        ep = ui_vflow_ep;''', r'''        ui_vflow_p += (want - ui_vflow_p) * (1.0 - exp(-dtv * (want > 0.5 ? 8.0 : 14.0)));      /* growing back is quicker */
        if (fabs(want - ui_vflow_p) < (want > 0.5 ? 0.004 : 0.03))      /* v43: the last part of the way back is not seen: it ends there */
            ui_vflow_p = want;
        ui_vflow_ep = ui_vflow_p * ui_vflow_p * (3.0 - 2.0 * ui_vflow_p);
        ep = ui_vflow_ep;''')

if fails:
    print("\n%d edit(s) failed. Nothing written." % len(fails))
    sys.exit(1)
open(PATH, "w").write(src)
print("\nAll edits applied to " + PATH)
