#!/usr/bin/env python3
# Update 48b for ffplay-custom (on top of patch_queue_v48.py).
#   * A launcher that passes URIs (a desktop entry with Exec=... %U, as a file manager, xdg-open or Settings -> Default Apps use)
#     handed us "file:///home/me/Music/%2813%29%20Song.mp3". The player took that text as the file name: the queue showed the
#     %XX escapes and nothing played. Now a file: URI is turned into the plain path ("/home/me/Music/(13) Song.mp3") before it
#     reaches the queue: "file:///path", "file://localhost/path" and "file:/path", with the %XX escapes decoded.
#     Other things are left exactly as they were (plain paths, "-", http: and the like, and file: names of another host).
#     Folders given as URIs are now opened as folders too, since the path is a real one by then.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v48.py. Writes the file only if the edit matches.
import sys

PATH = "fftools/ffplay.c"
src = open(PATH).read()

if "ui_uri_to_path" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_qs_stop_cur" not in src:
    print("Apply patch_queue_v48.py first. Nothing written.")
    sys.exit(1)

old = r'''static int opt_input_file(void *optctx, const char *filename)
{
    if (!strcmp(filename, "-"))
        filename = "fd:";
    queue_add_path(filename);
    if (!input_filename)
        input_filename = filename;      /* used for the window title */

    return 0;
}
'''
new = r'''/* v48b: "file:///home/me/My%20Song.mp3" (what a file manager passes for %U) -> "/home/me/My Song.mp3".
   Returns a new string (av_free it), or NULL when filename is not a file: URI for this computer (it is then used as it is). */
static int ui_hexval(int c)
{
    if (c >= '0' && c <= '9')
        return c - '0';
    if (c >= 'a' && c <= 'f')
        return c - 'a' + 10;
    if (c >= 'A' && c <= 'F')
        return c - 'A' + 10;
    return -1;
}

static char *ui_uri_to_path(const char *filename)
{
    const char *p = filename;
    char *out, *o;

    if (av_strncasecmp(p, "file:/", 6))
        return NULL;                    /* not a file: URI ("file:name" is left to FFmpeg, as before) */
    p += 5;
    if (p[0] == '/' && p[1] == '/') {   /* file://host/path: only an empty host or localhost is this computer */
        p += 2;
        if (*p != '/') {
            if (av_strncasecmp(p, "localhost/", 10))
                return NULL;
            p += 9;                     /* on the "/" after localhost */
        }
    }
    out = av_malloc(strlen(p) + 1);
    if (!out)
        return NULL;
    for (o = out; *p; p++) {
        int h, l;

        if (*p == '%' && (h = ui_hexval((unsigned char)p[1])) >= 0 && (l = ui_hexval((unsigned char)p[2])) >= 0) {
            if (!(h * 16 + l)) {        /* %00 cannot be in a name: leave the whole thing alone */
                av_free(out);
                return NULL;
            }
            *o++ = (char)(h * 16 + l);
            p += 2;
        } else {
            *o++ = *p;
        }
    }
    *o = 0;
    return out;
}

static int opt_input_file(void *optctx, const char *filename)
{
    char *path;

    if (!strcmp(filename, "-"))
        filename = "fd:";
    path = ui_uri_to_path(filename);    /* v48b: a file: URI becomes a plain path */
    if (path)
        filename = path;
    queue_add_path(filename);           /* the queue keeps its own copy */
    if (!input_filename)
        input_filename = filename;      /* used for the window title (a decoded path stays allocated for that) */
    else
        av_free(path);

    return 0;
}
'''
if src.count(old) != 1:
    print("FAILED: opt_input_file matched %d times. Nothing written." % src.count(old))
    sys.exit(1)
open(PATH, "w").write(src.replace(old, new))
print("ok: file: URIs become plain paths")
print("\nDone: patch_queue_v48b applied.")
