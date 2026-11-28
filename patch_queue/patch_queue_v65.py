#!/usr/bin/env python3
# patch_queue_v65.py - applies on top of v64 (so v63, then v64, then this).
#
#   1. a tap on the search box of the tiles view starts the search: the caret blinks and the keys type into it
#      (typing a letter still starts it too)
#   2. while a search is on (typed, or started by the tap) two finger swipes and the wheel only scroll the sections:
#      they never step back to the Stripfilm or close the tiles. Esc ends the search and the usual swipe steps
#      (tiles > Stripfilm > full video window) work again
#   3. pausing in a Stripfilm view that you opened yourself no longer jumps to the tiles: the Space key also arrives as a
#      typed space, and that was sent to the search. A pause that opens the Stripfilm by itself works as before
#
# Usage:  python3 patch_queue_v65.py [path/to/ffplay.c]
# Default path: ~/build/ffmpeg-6.1.1/fftools/ffplay.c
# Every edit must match exactly once, otherwise nothing is written.

import os
import sys

path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/build/ffmpeg-6.1.1/fftools/ffplay.c")
src = open(path, encoding="utf-8").read()

edits = []   # (name, old, new)


def edit(name, old, new):
    edits.append((name, old, new))


# ---------------------------------------------------------------- 1. a tap on the search box
edit("box: where it is", r'''static int ui_tv_searching = 0;                 /* the search box has been used (it shows a caret) */''',
     r'''static int ui_tv_searching = 0;                 /* the search box has been used (it shows a caret) */
static SDL_Rect ui_tv_sbox;                     /* v65: where the search box was drawn last, for a tap on it */
static int ui_tv_sbox_ok = 0;                   /* v65: 1 = the box is on screen (not in the Stripfilm layout) */''')

edit("box: remember it when it is drawn", r'''    box.y = sm ? 34 : 44;
    {''', r'''    box.y = sm ? 34 : 44;
    ui_tv_sbox = box;                           /* v65 */
    ui_tv_sbox_ok = !vm || ui_sf_p < 0.5;
    {''')

edit("box: a tap starts the search", r'''static int ui_tv_click(VideoState *is, int x, int y)
{
    int sec, item;

    if (!ui_tv_hit_at(x, y, &sec, &item))
        return 0;''', r'''static int ui_tv_click(VideoState *is, int x, int y)
{
    int sec, item;

    if (ui_tv_on(is) && ui_tv_cap(is) && !ui_sf_mode && ui_tv_sbox_ok && !ui_tvc_open &&
        x >= ui_tv_sbox.x && x < ui_tv_sbox.x + ui_tv_sbox.w && y >= ui_tv_sbox.y && y < ui_tv_sbox.y + ui_tv_sbox.h) {
        ui_tv_searching = 1;                    /* v65: a tap on the box: the caret blinks and the keys type into it */
        SDL_StartTextInput();
        ui_tv_moving = 1;
        is->force_refresh = 1;
        return 1;
    }
    if (!ui_tv_hit_at(x, y, &sec, &item))
        return 0;''')

# ---------------------------------------------------------------- 2. swipes only scroll while a search is on
edit("search: swipes only scroll the sections", r'''    if (ui_tv_q[0] && ui_tv_on(is) && !zone) {  /* v64: while searching, up and down scroll the page of sections */
        ui_tv_vt -= ay * 60.0;                  /* a wheel up (or fingers down) goes up the page; fingers up goes down it */
        ui_tv_moving = 1;
        is->force_refresh = 1;
        return;
    }''', r'''    if ((ui_tv_q[0] || ui_tv_searching) && ui_tv_on(is) && !zone) {     /* v64: while searching, up and down scroll the page of sections (v65: also when the search was started by a tap) */
        if (ui_tv_q[0])
            ui_tv_vt -= ay * 60.0;              /* a wheel up (or fingers down) goes up the page; fingers up goes down it */
        ui_tv_moving = 1;                       /* v65: with nothing typed yet there are no sections, and the swipe still never closes the view */
        is->force_refresh = 1;
        return;
    }''')

# ---------------------------------------------------------------- 3. Space in the Stripfilm view
edit("space: a typed space does not leave the strip", r'''    if (ui_sf_mode)
        ui_sf_level(is, 2);                     /* v57: the search lives in the tiles of all */
    if (!n && t[0] == ' ')
        return 1;''', r'''    if (!n && t[0] == ' ')
        return 1;                               /* v65: the Space key pauses (that is done by the key); its typed space is not a search, so the view stays */
    if (ui_sf_mode)
        ui_sf_level(is, 2);                     /* v57: the search lives in the tiles of all */''')

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
print("v65: %d edits applied to %s" % (len(edits), path))
