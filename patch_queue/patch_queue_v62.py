#!/usr/bin/env python3
"""patch_queue_v62.py  --  clears the "may be truncated" compiler warnings. Nothing the player does changes.

Apply on top of v61:
    python3 patch_queue_v62.py                      # patches ~/build/ffmpeg-6.1.1/fftools/ffplay.c
    python3 patch_queue_v62.py path/to/ffplay.c     # or any other copy

All the warnings are about joining or copying paths in the file picker. av_strlcpy and av_strlcat cut an over-long text at
the same place snprintf did, and say so in their names. Every edit must match exactly once. If one does not, nothing is written.
"""
import os
import sys

path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/build/ffmpeg-6.1.1/fftools/ffplay.c")
src = open(path, encoding="utf-8").read()

if "static void ui_pk_join(" in src:
    sys.exit("already patched (v62 marker found): nothing to do")
if "v61: the strip scrolls like v59" not in src:
    sys.exit("v62: this is not v61: nothing written")

done = []


def patch(name, old, new):
    global src
    n = src.count(old)
    if n != 1:
        sys.exit("v62: '%s': found %d times (wanted 1): nothing written" % (name, n))
    src = src.replace(old, new)
    done.append(name)


patch("folder thumbnails: a helper that joins a folder and a name",
'''/* A picture for a folder: the first video in it,''',
'''/* v62: out = dir/name, cut to fit */
static void ui_pk_join(char *out, size_t size, const char *dir, const char *name)
{
    av_strlcpy(out, dir, size);
    av_strlcat(out, "/", size);
    av_strlcat(out, name, size);
}

/* A picture for a folder: the first video in it,''')

patch("folder thumbnails: reading the folder",
'''        snprintf(full, sizeof(full), "%s/%s", dir, de->d_name);
        if (stat(full, &st) != 0)
            continue;
        if (S_ISDIR(st.st_mode)) {
            if (ns < 400)''',
'''        ui_pk_join(full, sizeof(full), dir, de->d_name);
        if (stat(full, &st) != 0)
            continue;
        if (S_ISDIR(st.st_mode)) {
            if (ns < 400)''')

patch("folder thumbnails: videos",
'''        snprintf(full, sizeof(full), "%s/%s", dir, vid[i]);''',
'''        ui_pk_join(full, sizeof(full), dir, vid[i]);''')

patch("folder thumbnails: songs",
'''        snprintf(full, sizeof(full), "%s/%s", dir, aud[i]);''',
'''        ui_pk_join(full, sizeof(full), dir, aud[i]);''')

patch("folder thumbnails: folders inside",
'''        snprintf(full, sizeof(full), "%s/%s", dir, sub[i]);''',
'''        ui_pk_join(full, sizeof(full), dir, sub[i]);''')

patch("thumbnail requests",
'''            snprintf(ui_pk_want[ui_pk_nwant].path, sizeof(ui_pk_want[0].path), "%s", path);''',
'''            av_strlcpy(ui_pk_want[ui_pk_nwant].path, path, sizeof(ui_pk_want[0].path));''')

patch("typed path: ~ for the home folder",
'''    if (ui_pk_loc[0] == '~' && (ui_pk_loc[1] == '/' || !ui_pk_loc[1]) && home)
        snprintf(out, size, "%s%s", home, ui_pk_loc + 1);
    else if''',
'''    if (ui_pk_loc[0] == '~' && (ui_pk_loc[1] == '/' || !ui_pk_loc[1]) && home) {
        av_strlcpy(out, home, size);
        av_strlcat(out, ui_pk_loc + 1, size);
    } else if''')

patch("typed path: a path from the folder that is open",
'''    else
        snprintf(out, size, "%s/%s", ui_pk_dir, ui_pk_loc);
}''',
'''    else
        ui_pk_join(out, size, ui_pk_dir, ui_pk_loc);
}''')

patch("typed path: starting to type",
'''    snprintf(ui_pk_loc, sizeof(ui_pk_loc), "%s%s", ui_pk_dir, strcmp(ui_pk_dir, "/") ? "/" : "");''',
'''    av_strlcpy(ui_pk_loc, ui_pk_dir, sizeof(ui_pk_loc));
    if (strcmp(ui_pk_dir, "/"))
        av_strlcat(ui_pk_loc, "/", sizeof(ui_pk_loc));''')

patch("typed path: Tab completion",
'''    if (best[0])
        snprintf(ui_pk_loc, sizeof(ui_pk_loc), "%s%s%s/", dirpart, strcmp(dirpart, "/") ? "/" : "", best);''',
'''    if (best[0]) {
        av_strlcpy(ui_pk_loc, dirpart, sizeof(ui_pk_loc));
        if (strcmp(dirpart, "/"))
            av_strlcat(ui_pk_loc, "/", sizeof(ui_pk_loc));
        av_strlcat(ui_pk_loc, best, sizeof(ui_pk_loc));
        av_strlcat(ui_pk_loc, "/", sizeof(ui_pk_loc));
    }''')

open(path, "w", encoding="utf-8").write(src)
for d in done:
    print("ok: " + d)
print("Done: patch_queue_v62 applied (%d edits)." % len(done))
