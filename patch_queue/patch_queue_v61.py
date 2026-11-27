#!/usr/bin/env python3
"""patch_queue_v61.py  --  the Stripfilm strip scrolls like v59 again: no spring and no squeeze.

Apply on top of v60:
    python3 patch_queue_v61.py                      # patches ~/build/ffmpeg-6.1.1/fftools/ffplay.c
    python3 patch_queue_v61.py path/to/ffplay.c     # or any other copy

Everything else v60 added stays. Every edit must match exactly once. If one does not, nothing is written.
"""
import os
import sys

path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/build/ffmpeg-6.1.1/fftools/ffplay.c")
src = open(path, encoding="utf-8").read()

if "v61: the strip scrolls like v59" in src:
    sys.exit("already patched (v61 marker found): nothing to do")
if "v60: the Stripfilm view and its transitions" not in src:
    sys.exit("v61: this is not v60: nothing written")

done = []


def rep(old, new, name):
    global src
    n = src.count(old)
    if n != 1:
        sys.exit("v61: '%s': found %d times (wanted 1): nothing written" % (name, n))
    src = src.replace(old, new)
    done.append(name)


def region(start, end, new, name):
    """Replace from the start of `start` up to (not including) `end`."""
    global src
    a = src.find(start)
    b = src.find(end, a + len(start)) if a >= 0 else -1
    if a < 0 or b < 0 or src.count(start) != 1:
        sys.exit("v61: '%s': markers not found exactly once: nothing written" % name)
    src = src[:a] + new + src[b:]
    done.append(name)


rep("""static double ui_sf_v = 0.0;                    /* v60: how fast the strip moves (tiles a second); the strip is a spring */
static double ui_sf_sq = 0.0;                   /* v60: 0 to 0.3: how much the speed squeezes the tiles of the strip together */
""", "", "spring and squeeze state removed")

rep("""    ui_sf_v = 0.0;
    ui_sf_touch = 0;""", """    ui_sf_touch = 0;""", "speed reset removed")

# the comment above ui_sf_draw
region("""   The strip scrolls like the reference: a critically damped spring""", """static void ui_sf_draw(VideoState *is, double dt""",
       """   v61: the strip scrolls like v59: one plain glide, tiles of one size at one fixed spacing. No spring and no squeeze, so the
   tiles never overlap. */
""", "comment")

rep("""    double fa = ui_sf_p * ep, aw, ah, asp, bwid, bhgt, pitch0, pitch, sy, cy, half, cmin, cmax, bm = av_clipd(1.0 - ui_sf_p, 0.0, 1.0);""",
    """    double fa = ui_sf_p * ep, aw, ah, asp, bwid, bhgt, pitch, sy, cy, half, cmin, cmax, bm = av_clipd(1.0 - ui_sf_p, 0.0, 1.0);""",
    "variables")

rep("""    pitch0 = tw + 12;
    half = (W / 2.0 - margin - tw * 0.8 / 2.0 - pitch0 * 0.10) / pitch0;   /* tiles from the middle of the window to the first tile, when the strip starts at the left */""",
    """    pitch = tw + 12;                                    /* v61: the strip scrolls like v59 */
    half = (W / 2.0 - margin - tw / 2.0) / pitch;       /* tiles from the middle of the window to the first tile, when the strip starts at the left */""",
    "fixed spacing")

region("""    {                                                   /* the strip is a critically damped spring""", """    if (ui_sf_touch)
        ui_tv_moving = 1;
""", """    ui_sf_pos += (ui_sf_target - ui_sf_pos) * (1.0 - exp(-dt * 9.0));
    if (fabs(ui_sf_target - ui_sf_pos) < 0.003)
        ui_sf_pos = ui_sf_target;
    else
        ui_tv_moving = 1;
""", "v59 glide")

rep("""        ui_tv_moving = 1;
    pitch = pitch0 * (1.0 - ui_sf_sq);
""", """        ui_tv_moving = 1;
""", "squeeze removed")

rep("""    /* the strip: no titles. The tile in the middle (ui_sf_pos) is the largest, the others get smaller and dimmer, and the far ones
       first so the middle one is on top. When the view goes on to the tiles of all, each tile glides into its place there. */""",
    """    /* the strip: no titles, every tile the same size. When the view goes on to the tiles of all, each tile glides into its place there. */""",
    "strip comment")

rep("""    K = FFMIN((int)(W / (2.0 * pitch0)) + 4, 40);""", """    K = FFMIN((int)(W / (2.0 * pitch)) + 4, 40);""", "tiles in sight")

rep("""            double d, ad, sc, x, tcx, tcy, tbw, tbh, goal, lf, sl = 1.0;""",
    """            double x, tcx, tcy, tbw, tbh, goal, lf, sl = 1.0;""", "tile variables")

rep("""            d = i - ui_sf_pos;
            ad = fabs(d);
            sc = 1.0 - 0.17 * ui_sf_smooth(ad) - 0.02 * av_clipd(ad - 1.0, 0.0, 4.0);      /* the middle one is the largest */
            x = W / 2.0 + d * pitch + (d < 0 ? -1.0 : 1.0) * FFMIN(ad, 1.0) * pitch0 * 0.10;     /* room around the middle one */
""", """            x = W / 2.0 + (i - ui_sf_pos) * pitch;
""", "even positions")

rep("""            al = (int)((play ? 255.0 : 255.0 * av_clipd(1.0 - 0.07 * ad, 0.62, 1.0)) * ui_sf_p);""",
    """            al = (int)((play ? 255 : 225) * ui_sf_p);""", "even opacity")
rep("""            md = play ? 255 : FFMIN(255, 228 - (int)(10 * FFMIN(ad, 3.0)) + (int)(27 * lf));""",
    """            md = play ? 255 : 200 + (int)(55 * lf);""", "even brightness")
rep("""            tbw = tw * sc;
            tbh = th * sc;""", """            tbw = tw;
            tbh = th;""", "one tile size")
rep("""            if (ad < 0.6)                               /* a soft glow in the bar color behind the middle tile, like the reference */
                ui_tv_glow(tcx, tcy, tbw * 0.95, tbh * 0.95, (int)(110 * (1.0 - ad / 0.6) * (al / 255.0)));
""", "", "middle glow removed")

rep("""/* v60: the Stripfilm view and its transitions (see ui_sf_draw). """,
    """/* v61: the strip scrolls like v59. v60: the Stripfilm view and its transitions (see ui_sf_draw). """, "marker")

open(path, "w", encoding="utf-8").write(src)
for d in done:
    print("  ok:", d)
print("Done: patch_queue_v61 applied (%d edits)." % len(done))
