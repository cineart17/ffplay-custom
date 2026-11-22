#!/usr/bin/env python3
# Update 42 for ffplay-custom (on top of patch_queue_v41.py).
#   * The file and folder dialogs (Open File, Open Folder, Add to Queue) stay above the player. They are the system's zenity
#     dialogs, not ours, and zenity 4 ignores its own --attach option, so a dialog could open behind a window that is on top
#     (the miniplayer, "always on top") or that fills the screen. On X11 the player now finds the dialog's window (by its process),
#     makes it a child of the player window (WM_TRANSIENT_FOR) and asks the window manager to bring it to the front, which is what
#     a dialog belonging to a window gets everywhere else. On Wayland there is no way to ask for this, so nothing changes there.
#     If the dialog's window is not found within 6 seconds, the dialog is left alone, exactly as before.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v41.py. Writes the file only if every edit matches.
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


if "ui_pick_attach_thread" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_too_small" not in src:
    print("Apply patch_queue_v41.py first. Nothing written.")
    sys.exit(1)

patch("file dialogs stay above the player", r'''/* ----- file dialogs (zenity), run in a thread so the player keeps working ----- */
static SDL_atomic_t ui_pick_busy;       /* 1 while a file dialog is open */

static int ui_pick_thread(void *arg)
{
    int item = (int)(intptr_t)arg;
    const char *cmd;
    char what;
    char line[PATH_MAX + 2];
    FILE *p;
    int status;

    if (item == 0) {            /* Open File... */
        cmd = "zenity --file-selection --title='Open File' 2>/dev/null";
        what = 'o';
    } else if (item == 1) {     /* Open Folder... */
        cmd = "zenity --file-selection --directory --title='Open Folder' 2>/dev/null";
        what = 'o';
    } else {                    /* Add to Queue... (one or more files) */
        cmd = "zenity --file-selection --multiple --separator='\n' --title='Add to Queue' 2>/dev/null";
        what = 'a';
    }

    p = popen(cmd, "r");
    if (p) {
        while (fgets(line, sizeof(line), p)) {
            line[strcspn(line, "\n")] = 0;
            if (line[0])
                ui_inbox_send(what, line);
        }
        status = pclose(p);
        if (status != -1 && ((status >> 8) & 0xff) == 127)
            fprintf(stderr, "ffplay-custom: zenity is needed for the file dialogs (sudo apt install zenity)\n");
    }
    SDL_AtomicSet(&ui_pick_busy, 0);
    return 0;
}

static void ui_pick_start(int item)
{
    SDL_Thread *t;

    if (!SDL_AtomicCAS(&ui_pick_busy, 0, 1))
        return;                 /* a dialog is already open */
    t = SDL_CreateThread(ui_pick_thread, "file dialog", (void *)(intptr_t)item);
    if (t)
        SDL_DetachThread(t);
    else
        SDL_AtomicSet(&ui_pick_busy, 0);
}''', r'''#include <SDL_syswm.h>
#include <dlfcn.h>

/* ----- file dialogs (zenity), run in a thread so the player keeps working ----- */
typedef struct {
    int type;
    unsigned long serial;
    int send_event;
    void *display;
    unsigned long window;
    unsigned long message_type;
    int format;
    long l[5];
} UiXCM3;

static SDL_atomic_t ui_pick_busy;       /* 1 while a file dialog is open */
static unsigned long ui_pick_xid = 0;   /* v42: our window (X11), the one the dialog belongs to */
static long ui_pick_pid = 0;            /* v42: the process of the dialog */

/* v42: zenity 4 ignores --attach, so on X11 the dialog's window is found by its process, made a child of ours (WM_TRANSIENT_FOR),
   and asked to come to the front: the window manager keeps a dialog above the window it belongs to, even when that window is on
   top or fills the screen. Nothing here can fail loudly: if the window is not found within 6 seconds, the dialog is left alone. */
static int ui_pick_attach_thread(void *arg)
{
    void *xl = dlopen("libX11.so.6", RTLD_LAZY);
    void *(*x_open)(const char *);
    int (*x_close)(void *);
    unsigned long (*x_atom)(void *, const char *, int);
    unsigned long (*x_root)(void *);
    int (*x_get)(void *, unsigned long, unsigned long, long, long, int, unsigned long, unsigned long *, int *, unsigned long *,
                 unsigned long *, unsigned char **);
    int (*x_free)(void *);
    int (*x_trans)(void *, unsigned long, unsigned long);
    int (*x_send)(void *, unsigned long, int, long, void *);
    int (*x_flush)(void *);
    void *dpy;
    unsigned long root, a_list, a_pid, a_act;
    int t;

    (void)arg;
    if (!xl || !ui_pick_xid || ui_pick_pid <= 0)
        return 0;
    *(void **)&x_open = dlsym(xl, "XOpenDisplay");
    *(void **)&x_close = dlsym(xl, "XCloseDisplay");
    *(void **)&x_atom = dlsym(xl, "XInternAtom");
    *(void **)&x_root = dlsym(xl, "XDefaultRootWindow");
    *(void **)&x_get = dlsym(xl, "XGetWindowProperty");
    *(void **)&x_free = dlsym(xl, "XFree");
    *(void **)&x_trans = dlsym(xl, "XSetTransientForHint");
    *(void **)&x_send = dlsym(xl, "XSendEvent");
    *(void **)&x_flush = dlsym(xl, "XFlush");
    if (!x_open || !x_close || !x_atom || !x_root || !x_get || !x_free || !x_trans || !x_send || !x_flush)
        return 0;
    dpy = x_open(NULL);                         /* a connection of its own: nothing is shared with SDL's */
    if (!dpy)
        return 0;
    root = x_root(dpy);
    a_list = x_atom(dpy, "_NET_CLIENT_LIST", 0);
    a_pid = x_atom(dpy, "_NET_WM_PID", 0);
    a_act = x_atom(dpy, "_NET_ACTIVE_WINDOW", 0);
    for (t = 0; t < 60; t++) {
        unsigned long type, n = 0, after, i;
        int fmt;
        unsigned char *data = NULL;
        int done = 0;

        SDL_Delay(100);
        if (x_get(dpy, root, a_list, 0, 4096, 0, 33 /* XA_WINDOW */, &type, &fmt, &n, &after, &data) != 0 || !data)
            continue;
        for (i = 0; i < n && !done; i++) {
            unsigned long w = ((unsigned long *)data)[i], tn = 0, ta, tb;
            int tf;
            unsigned char *pd = NULL;

            if (x_get(dpy, w, a_pid, 0, 1, 0, 6 /* XA_CARDINAL */, &ta, &tf, &tn, &tb, &pd) == 0 && pd) {
                if (tn == 1 && *(unsigned long *)pd == (unsigned long)ui_pick_pid) {
                    UiXCM3 ev;

                    x_trans(dpy, w, ui_pick_xid);       /* the dialog belongs to our window */
                    memset(&ev, 0, sizeof(ev));
                    ev.type = 33;                       /* ClientMessage: _NET_ACTIVE_WINDOW */
                    ev.display = dpy;
                    ev.window = w;
                    ev.message_type = a_act;
                    ev.format = 32;
                    ev.l[0] = 2;                        /* from a pager: the window manager brings it to the front */
                    x_send(dpy, root, 0, (1L << 20) | (1L << 19), &ev);
                    x_flush(dpy);
                    done = 1;
                }
                x_free(pd);
            }
        }
        x_free(data);
        if (done)
            break;
    }
    x_close(dpy);
    return 0;
}

static int ui_pick_thread(void *arg)
{
    int item = (int)(intptr_t)arg, first = 1;
    const char *cmd;
    char what;
    char line[PATH_MAX + 2];
    FILE *p;
    int status;

    if (item == 0) {            /* Open File... */
        cmd = "echo $$; exec zenity --file-selection --title='Open File' 2>/dev/null";
        what = 'o';
    } else if (item == 1) {     /* Open Folder... */
        cmd = "echo $$; exec zenity --file-selection --directory --title='Open Folder' 2>/dev/null";
        what = 'o';
    } else {                    /* Add to Queue... (one or more files) */
        cmd = "echo $$; exec zenity --file-selection --multiple --separator='\\n' --title='Add to Queue' 2>/dev/null";
        what = 'a';
    }

    p = popen(cmd, "r");
    if (p) {
        while (fgets(line, sizeof(line), p)) {
            line[strcspn(line, "\n")] = 0;
            if (first) {                        /* the first line is the process number of the dialog (v42) */
                SDL_Thread *at;

                first = 0;
                ui_pick_pid = atol(line);
                at = SDL_CreateThread(ui_pick_attach_thread, "dialog on top", NULL);
                if (at)
                    SDL_DetachThread(at);
                continue;
            }
            if (line[0])
                ui_inbox_send(what, line);
        }
        status = pclose(p);
        if (status != -1 && ((status >> 8) & 0xff) == 127)
            fprintf(stderr, "ffplay-custom: zenity is needed for the file dialogs (sudo apt install zenity)\n");
    }
    SDL_AtomicSet(&ui_pick_busy, 0);
    return 0;
}

static void ui_pick_start(int item)
{
    SDL_Thread *t;
    SDL_SysWMinfo info;

    if (!SDL_AtomicCAS(&ui_pick_busy, 0, 1))
        return;                 /* a dialog is already open */
    ui_pick_xid = 0;
    SDL_VERSION(&info.version);
    if (window && SDL_GetWindowWMInfo(window, &info) && info.subsystem == SDL_SYSWM_X11)
        ui_pick_xid = (unsigned long)info.info.x11.window;      /* X11 only: Wayland has no way to ask for this */
    t = SDL_CreateThread(ui_pick_thread, "file dialog", (void *)(intptr_t)item);
    if (t)
        SDL_DetachThread(t);
    else
        SDL_AtomicSet(&ui_pick_busy, 0);
}''')

if fails:
    print("\n%d edit(s) failed. Nothing written." % len(fails))
    sys.exit(1)
open(PATH, "w").write(src)
print("\nAll edits applied to " + PATH)
