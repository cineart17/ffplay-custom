#!/usr/bin/env python3
# patch_queue_v55.py: the bottom buttons of Open Media, simplified. Run it from ~/build/ffmpeg-6.1.1 (it patches fftools/ffplay.c in place;
# make your own backup first, as usual). Applies on top of the v54 redo.
#   a folder is chosen                  -> "Play folder" only (a double click or Enter opens it; there is no "Open folder" button)
#   inside a folder, nothing chosen     -> "Play folder" (plays the folder you are in)
#   one file chosen                     -> "Play"
#   two or more files ticked (Ctrl)     -> "Play selected"
#   inside a playlist, nothing chosen   -> "Play playlist";  a song chosen -> "Play" and "Play playlist"
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "fftools/ffplay.c"
src = open(PATH, encoding="utf-8").read()
if "v55: the main button" in src:
    sys.exit("Already applied: patch_queue_v55 (" + PATH + ")")


def R(old, new, what):
    global src
    n = src.count(old)
    if n != 1:
        sys.exit("FAILED: %s (anchor found %d times, expected 1). Nothing was written." % (what, n))
    src = src.replace(old, new)
    print("ok: " + what)


# ---- the main button: what it does when nothing is chosen (the first row is only highlighted until it is clicked)
R("""/* The main button (right end of the foot), v52:
   Open Media: "Play file" for a file, "Play folder" for a folder, "Play selected files" for a ticked set.
   Add to Queue: "Add", in the order the files were ticked. */""",
  """/* v55: the main button (right end of the foot).
   Open Media: "Play" for a chosen file, "Play folder" for a chosen folder or, with nothing chosen, the folder you are in,
   "Play selected" for a ticked set, "Play playlist" inside a playlist when no song is chosen.
   Add to Queue: "Add", in the order the files were ticked. */""", "main button comment")

R("""    if (!e)
        return;
    ui_pk_path_of(e, path, sizeof(path));
    ui_pk_send(is, 'o', path);                  /* a folder plays everything in it */
    ui_pk_close(is);
}""",
  """    if (!e || !ui_pk_touched) {                 /* v55: nothing chosen yet: the whole folder (or playlist) */
        if (ui_pk_pl[0]) {
            ui_pk_send_playlist(is, 'o', ui_pk_pl);
            ui_pk_close(is);
        } else if (ui_pk_nrw > 0) {
            ui_pk_send(is, 'o', ui_pk_dir);
            ui_pk_close(is);
        }
        return;
    }
    ui_pk_path_of(e, path, sizeof(path));
    ui_pk_send(is, 'o', path);                  /* a folder plays everything in it */
    ui_pk_close(is);
}""", "main button action")

# ---- the button before it: only the playlist button is left; "Open folder" is gone (double click or Enter opens a folder)
R("""/* The button before the play button: "Open folder" (go into it), or "Add this folder" in Add to Queue */""",
  """/* The button before the play button: "Add this folder" in Add to Queue, "Play playlist" in a playlist when a song is chosen (v55: no more "Open folder") */""",
  "extra comment")

R("""    UiPkEnt *e = ui_pk_cur_ent();

    if (ui_pk_pl[0] && !(e && e->dir)) {        /* v54: in a playlist this button is for the whole playlist */""",
  """    UiPkEnt *e = ui_pk_cur_ent();

    if (ui_pk_mode == 0 && !(ui_pk_pl[0] && ui_pk_touched && e && !ui_pk_ticked(NULL)))
        return;                                 /* v55: the empty space where the button is not drawn */
    if (ui_pk_pl[0] && !(e && e->dir)) {        /* v54: in a playlist this button is for the whole playlist */""",
  "extra guard")

R("""        ui_pk_send(is, 'a', path);
        ui_pk_close(is);
    } else if (e && e->dir) {
        ui_pk_enter(e);
    }
}

/* Enter, or a double click""",
  """        ui_pk_send(is, 'a', path);
        ui_pk_close(is);
    }
}

/* Enter, or a double click""", "extra: no Open folder")

# ---- Enter on a file plays that file, even if only the first row was highlighted
R("""    if (e->dir)
        ui_pk_enter(e);
    else
        ui_pk_do_ok(is);
}""",
  """    if (e->dir) {
        ui_pk_enter(e);
    } else {
        ui_pk_touched = 1;                      /* v55: Enter on the highlighted file plays that file, not the folder */
        ui_pk_do_ok(is);
    }
}""", "activate")

# ---- the buttons: sizes
R("""    L->ok.w = ui_pk_mode == 0 ? (L->p.w >= 740 ? 196 : 132) : 124;   /* v52: "Play selected files" fits */""",
  """    L->ok.w = ui_pk_mode == 0 ? (L->p.w >= 740 ? 150 : 132) : 124;   /* v55: "Play selected" fits */""", "ok width")

R("""        int sw = L.tog ? 316 : L.extra.x - (L.p.x + 20) - 16, fy = L.ok.y + L.ok.h / 2;""",
  """        int sw = L.tog ? 316 : (ui_pk_mode == 0 && !ui_pk_pl[0] ? L.ok.x : L.extra.x) - (L.p.x + 20) - 16, fy = L.ok.y + L.ok.h / 2;""",
  "status width")

# ---- the buttons: labels
R("""        UiPkEnt *ce = ui_pk_cur_ent();
        int nt = ui_pk_ticked(NULL);
        int wide = L.p.w >= 740;
""",
  """        UiPkEnt *ce = ui_pk_cur_ent();
        UiPkEnt *ch = ui_pk_touched ? ce : NULL;        /* v55: the row that was chosen (not just highlighted) */
        int nt = ui_pk_ticked(NULL);
        int wide = L.p.w >= 740;
""", "foot vars")

R("""        } else if (ce && ce->dir && !nt) {       /* v52: a folder has "Open folder" and "Play folder" */
            ui_pk_button(&L.extra, wide ? "Open folder" : "Open", ui_pk_hbtn == 3, 0, 1);
            ui_pk_button(&L.ok, wide ? "Play folder" : "Play", ui_pk_hbtn == 1, 1, 1);
        } else {
            if (nt > 1)
                snprintf(tmp, sizeof(tmp), "%s", wide ? "Play selected files" : "Play selected");
            else if (ce && !ce->dir)
                snprintf(tmp, sizeof(tmp), "%s", wide ? "Play file" : "Play");
            else
                snprintf(tmp, sizeof(tmp), "%s", wide ? "Play file" : "Play");
            ui_pk_button(&L.ok, tmp, ui_pk_hbtn == 1, 1, nt > 0 || (ce && !ce->dir));
            if (ui_pk_pl[0] && !nt)             /* v54: the whole playlist */
                ui_pk_button(&L.extra, wide ? "Play playlist" : "Play all", ui_pk_hbtn == 3, 0, ui_pk_nrw > 0);
        }""",
  """        } else {                                /* v55: one main button, and only a playlist has a second one */
            if (nt > 1)
                snprintf(tmp, sizeof(tmp), "%s", "Play selected");
            else if (nt == 1 || (ch && !ch->dir))
                snprintf(tmp, sizeof(tmp), "%s", "Play");
            else if (ui_pk_pl[0] && !ch)
                snprintf(tmp, sizeof(tmp), "%s", wide ? "Play playlist" : "Play all");
            else
                snprintf(tmp, sizeof(tmp), "%s", wide ? "Play folder" : "Play");
            ui_pk_button(&L.ok, tmp, ui_pk_hbtn == 1, 1, nt > 0 || ch || ui_pk_nrw > 0);
            if (ui_pk_pl[0] && !nt && ch)       /* v54: the whole playlist, when a song is chosen */
                ui_pk_button(&L.extra, wide ? "Play playlist" : "Play all", ui_pk_hbtn == 3, 0, ui_pk_nrw > 0);
        }""", "foot buttons")

open(PATH, "w", encoding="utf-8").write(src)
print("\nDone: patch_queue_v55 applied.")
