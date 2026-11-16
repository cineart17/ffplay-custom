#!/usr/bin/env python3
# Update 27 for ffplay-custom (on top of patch_queue_v26.py).
#   * Playing again from the tiled view that a pause opened: the view waited 250 ms after play before it closed,
#     so the video seemed slow to grow back. It waits 60 ms now, and the video grows back a little quicker than it
#     shrinks.
#   * Screen sleep: the player re-checks every 2 s whether a video really plays (not paused, not held on its last
#     picture) and says on the terminal when it lets the screen sleep or keeps it awake.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v26.py. Writes the file only if every spot matches once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "screen kept awake" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_ks_tick(" not in src:
    print("Apply patch_queue_v25.py and patch_queue_v26.py first. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


patch("if (seen && now - unpaused_at > 250000) {", "if (seen && now - unpaused_at > 60000) {",
      "playing again closes the tiled view after 60 ms, not 250 ms")

patch("ui_vflow_p += (want - ui_vflow_p) * (1.0 - exp(-dtv * 8.0));",
      "ui_vflow_p += (want - ui_vflow_p) * (1.0 - exp(-dtv * (want > 0.5 ? 8.0 : 12.0)));      /* growing back is quicker */",
      "the video grows back a little quicker")

patch("""    static int inhibit = -1;
    int want = is && !is->paused && is->video_st &&
               !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC);

    if (want == inhibit)
        return;
    inhibit = want;
""", """    static int inhibit = -1;
    static int64_t asserted = 0;
    int64_t now = av_gettime_relative();
    int want = is && !is->paused && !is->ui_held && is->video_st &&
               !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC);

    if (want == inhibit && now - asserted < 2000000)    /* checked again every 2 s, not only when the state changes */
        return;
    if (want != inhibit)
        av_log(NULL, AV_LOG_INFO, want ? "screen kept awake (a video is playing)\\n"
                                       : "screen may sleep (the system's idle settings apply)\\n");
    inhibit = want;
    asserted = now;
""", "screen sleep is re-checked and reported")

open(path, "w").write(src)
print("Patched fftools/ffplay.c")
