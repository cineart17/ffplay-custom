#!/usr/bin/env python3
# patch_queue_v56.py: "Add to playlist" from the tiled view works. The chooser and its message were never drawn there: with no menu or panel open the
# player draws its frame without them, so the chooser was open (and took the clicks) but could not be seen.
# Run it from ~/build/ffmpeg-6.1.1 (it patches fftools/ffplay.c in place; make your own backup first, as usual). Applies on top of v55.
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "fftools/ffplay.c"
src = open(PATH, encoding="utf-8").read()
if "v56: the playlist chooser" in src:
    sys.exit("Already applied: patch_queue_v56 (" + PATH + ")")


def R(old, new, what):
    global src
    n = src.count(old)
    if n != 1:
        sys.exit("FAILED: %s (anchor found %d times, expected 1). Nothing was written." % (what, n))
    src = src.replace(old, new)
    print("ok: " + what)


R("""    if (ui_menu_open || ui_prefs_open || ui_pk_open) {
        ui_glass_frame(is);         /* frosted glass over the blurred picture */""",
  """    if (ui_menu_open || ui_prefs_open || ui_pk_open || ui_apl_busy()) {     /* v56: the playlist chooser (and its message) are drawn by the glass frame, and no menu is open in the tiled view */
        ui_glass_frame(is);         /* frosted glass over the blurred picture */""",
  "glass frame for the playlist chooser")

open(PATH, "w", encoding="utf-8").write(src)
print("\nDone: patch_queue_v56 applied.")
