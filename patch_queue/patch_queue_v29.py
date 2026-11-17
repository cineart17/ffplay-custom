#!/usr/bin/env python3
# patch_queue_v29.py - run it inside ~/build/ffmpeg-6.1.1 (it edits fftools/ffplay.c)
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


if "ui_flow_snap_back" in src:
    print("Already applied")
    sys.exit(0)

patch("no automatic snap back", r'''    if (ui_flow_touch && now - ui_flow_touch > 5000000) {       /* 5 s after the last swipe: back to the playing item */
        ui_flow_target = q_pos;
        ui_flow_touch = 0;
    }
''', r'''                                                /* the row stays where it was swiped to until a tap outside the tiles */
''')

patch("snap back declaration", r'''static int ui_flow_motion(VideoState *is, int x, int y);
static int ui_flow_release(VideoState *is, int x, int y);''', r'''static int ui_flow_motion(VideoState *is, int x, int y);
static int ui_flow_release(VideoState *is, int x, int y);
static int ui_flow_snap_back(VideoState *is);''')

patch("tap outside the tiles", r'''            return 1;                       /* a click on a cover */
        if (ev->button.button != SDL_BUTTON_LEFT || ev->button.y < is->height - UI_BAR_H)
            return 0;''', r'''            return 1;                       /* a click on a cover */
        if (ev->button.button == SDL_BUTTON_LEFT && ev->button.y < is->height - UI_BAR_H && ui_flow_snap_back(is))
            return 1;                       /* a tap outside the tiles: the row glides back to the playing item */
        if (ev->button.button != SDL_BUTTON_LEFT || ev->button.y < is->height - UI_BAR_H)
            return 0;''')

patch("snap back function", r'''static int ui_flow_motion(VideoState *is, int x, int y)
{
    ui_hov_x = x;''', r'''/* A tap that is not on a tile: if the row was moved away from the playing item, it glides back to it (and the tap is used up) */
static int ui_flow_snap_back(VideoState *is)
{
    if (!ui_flow_on(is) || ui_flow_press >= 0 || ui_flow_dragging)
        return 0;
    if (ui_flow_target == q_pos && !ui_flow_moving)
        return 0;
    ui_flow_target = q_pos;
    ui_flow_touch = 0;
    is->force_refresh = 1;
    return 1;
}

static int ui_flow_motion(VideoState *is, int x, int y)
{
    ui_hov_x = x;''')

if fails:
    print("\n%d patches did not apply. Nothing was written." % len(fails))
    sys.exit(1)
open(PATH, "w").write(src)
print("Patched " + PATH)
