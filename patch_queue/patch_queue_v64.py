#!/usr/bin/env python3
# patch_queue_v64.py - applies on top of v63.
#
#   1. search view: each section has its title above its row, the items start at the far left under the title,
#      and the sections sit one under the other on a page that scrolls (wheel or two finger swipe up/down,
#      the arrow keys bring the section they move to into sight)
#   2. a right-click menu action while a search is on (Play next, Add to queue, Remove...) no longer refreshes the view:
#      the sections keep their place, their scroll and their animation, and the folders are not read again
#
# Usage:  python3 patch_queue_v64.py [path/to/ffplay.c]
# Default path: ~/build/ffmpeg-6.1.1/fftools/ffplay.c
# Every edit must match exactly once, otherwise nothing is written.

import os
import sys

path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/build/ffmpeg-6.1.1/fftools/ffplay.c")
src = open(path, encoding="utf-8").read()

edits = []   # (name, old, new)


def edit(name, old, new):
    edits.append((name, old, new))


# ---------------------------------------------------------------- state of the scrolling page
edit("page: state", r'''static int ui_tv_secy[4][2];''', r'''static int ui_tv_secy[4][2];
static double ui_tv_vs = 0.0, ui_tv_vt = 0.0;   /* v64: how far the page of sections is scrolled (px): now, and where it is going */
static int ui_tv_last_act = -1;                 /* v64: the section that was last brought into sight */''')

edit("page: a new search starts at the top", r'''    ui_tv_act = 0;
    if (!ui_tv_q[0])
        return;''', r'''    ui_tv_act = 0;
    ui_tv_vs = ui_tv_vt = 0.0;                  /* v64: the page starts at the top */
    ui_tv_last_act = -1;
    if (!ui_tv_q[0])
        return;''')

edit("page: the layout", r'''    } else if (ui_tv_q[0]) {                    /* searching: three sections, each its own row of matches, the best one in focus */
        double secH = (cbot - ctop) / 4.0;
        int sh = (int)av_clipd(FFMIN(secH - 24 - 30, W * 0.2), 36.0, 260.0), tr, tg, tb;     /* v38: bigger */

        ui_tv_theme(&tr, &tg, &tb);
        for (s = 0; s < 4; s++) {
            UiTvSec *sec = &ui_tv_sec[s];
            UiTvRow row;
            int top = ctop + (int)(secH * s), hy = top + 12, a = s == ui_tv_act ? 235 : 150;
            char head[96];
            SDL_Rect mark;

            ui_tv_secy[s][0] = top;
            ui_tv_secy[s][1] = top + (int)secH;''', r'''    } else if (ui_tv_q[0]) {                    /* searching: the sections one under the other on a page that scrolls (v64) */
        double avail = cbot - ctop, total = 0.0, maxs, topv[4], hv[4];
        int sh = (int)av_clipd(FFMIN(avail / 2.0 - 60.0, W * 0.2), 36.0, 260.0), tr, tg, tb, hk, hn = 0;      /* two sections fit a page */
        SDL_Rect pclip;

        ui_tv_theme(&tr, &tg, &tb);
        for (s = 0; s < 4; s++) {               /* where each section starts on the page */
            topv[s] = total;
            hv[s] = ui_tv_sec[s].n > 0 ? sh + 60.0 : 56.0;      /* a section with nothing in it is only its title and a line */
            total += hv[s];
        }
        maxs = FFMAX(total - avail, 0.0);
        if (ui_tv_act != ui_tv_last_act) {      /* the section the keys moved to comes into sight */
            ui_tv_last_act = ui_tv_act;
            if (topv[ui_tv_act] < ui_tv_vt)
                ui_tv_vt = topv[ui_tv_act];
            else if (topv[ui_tv_act] + hv[ui_tv_act] > ui_tv_vt + avail)
                ui_tv_vt = topv[ui_tv_act] + hv[ui_tv_act] - avail;
        }
        ui_tv_vt = av_clipd(ui_tv_vt, 0.0, maxs);
        ui_tv_vs += (ui_tv_vt - ui_tv_vs) * (1.0 - exp(-dt * 12.0));
        if (fabs(ui_tv_vt - ui_tv_vs) < 0.5)
            ui_tv_vs = ui_tv_vt;
        else
            ui_tv_moving = 1;
        ui_tv_vs = av_clipd(ui_tv_vs, 0.0, maxs);
        pclip.x = 0;                            /* nothing of the page is drawn over the search box */
        pclip.y = ctop;
        pclip.w = W;
        pclip.h = (int)avail;
        SDL_RenderSetClipRect(renderer, &pclip);
        for (s = 0; s < 4; s++) {
            UiTvSec *sec = &ui_tv_sec[s];
            UiTvRow row;
            int top = ctop + (int)(topv[s] - ui_tv_vs), hy = top + 12, a = s == ui_tv_act ? 235 : 150;
            char head[96];
            SDL_Rect mark;

            ui_tv_secy[s][0] = FFMAX(top, ctop);
            ui_tv_secy[s][1] = FFMIN(top + (int)hv[s], ctop + (int)avail);''')

edit("page: items start at the far left", r'''            row.cx = (int)(W * 0.30);
            row.cy = top + 24 + sh / 2 + 6;
            row.sw = (int)(sh * (s == 2 ? 1.22 : 1.75));            /* v39: music tiles sit closer (v63: Music is the third section) */''',
     r'''            row.sw = (int)(sh * (s == 2 ? 1.22 : 1.75));            /* v39: music tiles sit closer (v63: Music is the third section) */
            row.cx = 28 + row.sw / 2;                               /* v64: the first item starts at the far left, under its title */
            row.cy = top + 24 + sh / 2 + 6;''')

edit("page: end of the sections", r'''            ui_tv_row_draw(is, &row, hs, hi, dt, now, ep);
        }
        if (ui_tv_scan_state == 1)
            ui_tv_moving = 1;                   /* the folders are still being read: the lists grow */''', r'''            ui_tv_row_draw(is, &row, hs, hi, dt, now, ep);
        }
        SDL_RenderSetClipRect(renderer, NULL);
        for (hk = 0; hk < ui_tvh_n; hk++)       /* a tile that is scrolled out of sight cannot be hit */
            if (ui_tvh[hk].r.y + ui_tvh[hk].r.h / 2 >= ctop && ui_tvh[hk].r.y + ui_tvh[hk].r.h / 2 < cbot)
                ui_tvh[hn++] = ui_tvh[hk];
        ui_tvh_n = hn;
        if (ui_tv_scan_state == 1)
            ui_tv_moving = 1;                   /* the folders are still being read: the lists grow */''')

edit("page: wheel and swipes scroll it", r'''    act = zone == 1 ? 0 : zone == 2 ? 1 : cfg_wheel;''', r'''    if (ui_tv_q[0] && ui_tv_on(is) && !zone) {  /* v64: while searching, up and down scroll the page of sections */
        ui_tv_vt -= ay * 60.0;                  /* a wheel up (or fingers down) goes up the page; fingers up goes down it */
        ui_tv_moving = 1;
        is->force_refresh = 1;
        return;
    }
    act = zone == 1 ? 0 : zone == 2 ? 1 : cfg_wheel;''')

# ---------------------------------------------------------------- the menu of a tile does not refresh the view
edit("menu: no rescan flag", r'''static int ui_tv_visits = 0;                    /* how many directory entries the reading may still look at */''',
     r'''static int ui_tv_visits = 0;                    /* how many directory entries the reading may still look at */
static int ui_tv_keep_scan = 0;                 /* v64: 1 = do not read the folders again now (a menu action rebuilds the lists) */''')

edit("menu: scan start respects it", r'''    if (!ui_tv_mu || ui_tv_scan_state == 1 || (ui_tv_scan_state == 2 && now - ui_tv_scan_at < 60000000))''',
     r'''    if (!ui_tv_mu || ui_tv_scan_state == 1 || (ui_tv_scan_state == 2 && (ui_tv_keep_scan || now - ui_tv_scan_at < 60000000)))''')

edit("menu: the view stays as it is", r'''    if (ui_tv_q[0] && act != 0)
        ui_tv_search();                         /* "In this queue" follows what changed */''', r'''    if (ui_tv_q[0] && act != 0) {               /* "In this queue" follows what changed; the rest of the view stays as it is (v64) */
        UiTvSec keep[4];
        double vs = ui_tv_vs, vt = ui_tv_vt;
        int ka = ui_tv_act, s;

        for (s = 0; s < 4; s++)
            keep[s] = ui_tv_sec[s];             /* only pos, target and born are used again (the lists are rebuilt) */
        ui_tv_keep_scan = 1;                    /* the folders are not read again */
        ui_tv_search();
        ui_tv_keep_scan = 0;
        for (s = 0; s < 4; s++) {               /* every section keeps its place and its animation: no new spring-in */
            ui_tv_sec[s].target = av_clip(keep[s].target, 0, FFMAX(ui_tv_sec[s].n - 1, 0));
            ui_tv_sec[s].pos = av_clipd(keep[s].pos, 0.0, FFMAX(ui_tv_sec[s].n - 1, 0));
            ui_tv_sec[s].born = keep[s].born;
        }
        if (ui_tv_sec[ka].n > 0)
            ui_tv_act = ka;
        ui_tv_vs = vs;                          /* and the page stays scrolled where it was */
        ui_tv_vt = vt;
        ui_tv_last_act = ui_tv_act;
    }''')

# ---------------------------------------------------------------- apply, all or nothing
out = src
for name, old, new in edits:
    n = out.count(old)
    if n != 1:
        print("FAILED: '%s' matched %d times (needs exactly 1). Nothing was written." % (name, n))
        sys.exit(1)
    out = out.replace(old, new, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(out)
print("v64: %d edits applied to %s" % (len(edits), path))
