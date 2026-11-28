#!/usr/bin/env python3
# patch_queue_v68.py - on top of v67
#  In the Stripfilm view the typed letters no longer start a search: every key binding works as it does with the view closed.
#  Tab, Esc, Enter, Left, Right, Up and Home/End still belong to the view (Tab closes it). The search is in the tiles of all.
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "fftools/ffplay.c"
src = open(path, encoding="utf-8").read()
done = 0


def edit(old, new, what):
    global src, done
    if new in src:
        print("already: " + what)
        return
    n = src.count(old)
    if n != 1:
        print("FAILED: %s (found %d times)" % (what, n))
        sys.exit(1)
    src = src.replace(old, new)
    done += 1
    print("ok: " + what)


edit("    case SDLK_BACKSPACE: {\n        size_t n = strlen(ui_tv_q);\n\n        if (n > 0) {\n",
     "    case SDLK_BACKSPACE: {\n        size_t n = strlen(ui_tv_q);\n\n"
     "        if (ui_sf_active(is))                   /* v68: the Stripfilm view has no search: the key does what it does everywhere */\n"
     "            return 0;\n"
     "        if (n > 0) {\n",
     "Backspace is the player's in the Stripfilm view")

edit("    case SDLK_DOWN:\n        ui_tv_step(is, 0, 1);\n        return 1;\n",
     "    case SDLK_DOWN:\n"
     "        if (ui_sf_active(is))                   /* v68: down moves nothing in the strip: it is the player's key */\n"
     "            return 0;\n"
     "        ui_tv_step(is, 0, 1);\n        return 1;\n",
     "Down is the player's in the Stripfilm view")

edit("    case SDLK_SPACE:\n        if (!ui_tv_q[0])\n            toggle_pause(is);                   /* nothing typed: Space still pauses */\n        return 1;\n"
     "    default:\n        return 1;                               /* the letters belong to the search (they arrive as text) */\n",
     "    case SDLK_SPACE:\n"
     "        if (ui_sf_active(is))                   /* v68: in the Stripfilm view Space is the player's key, as chosen in settings.conf */\n"
     "            return 0;\n"
     "        if (!ui_tv_q[0])\n            toggle_pause(is);                   /* nothing typed: Space still pauses */\n        return 1;\n"
     "    default:\n"
     "        if (ui_sf_active(is))                   /* v68: every other key works as it does with the view closed (no search from here) */\n"
     "            return 0;\n"
     "        return 1;                               /* the letters belong to the search (they arrive as text) */\n",
     "other keys are the player's in the Stripfilm view")

edit("    if (!ui_tv_cap(is) || ui_menu_open || ui_prefs_open || ui_q_open || ui_info_open || ui_ctx_open)\n        return 0;\n    if (!n && t[0] == ' ')\n",
     "    if (!ui_tv_cap(is) || ui_menu_open || ui_prefs_open || ui_q_open || ui_info_open || ui_ctx_open)\n        return 0;\n"
     "    if (ui_sf_active(is))\n        return 0;                               /* v68: typing in the Stripfilm view is no search (the tiles of all have it) */\n"
     "    if (!n && t[0] == ' ')\n",
     "typed text is no search in the Stripfilm view")

open(path, "w", encoding="utf-8").write(src)
print("v68: %d edits applied to %s" % (done, path) if done else "v68 is already in %s, nothing changed" % path)
