#!/usr/bin/env python3
# patch_queue_v63.py - applies on top of v62.
#
#   1. text is drawn in its natural state (slight hinting, no sharpening)
#   2. tiles-view search box: its own defined background, a search icon, text that stays inside the box
#   3. search sections: In this queue / In Videos / In Music / Elsewhere
#   4. exit at the end of the queue (on = the window closes, off = it pauses at the end, also for songs)
#   5. repeat works again (the end of a file was being counted as a failed file)
#   6. miniplayer: a swipe over the music tiles moves through the queue
#   7. on the seek / volume bars an up or down wheel or two finger swipe always adjusts
#   8. tiles of all -> strip -> full video (never straight from the tiles to the video); full video -> tiles by a hard swipe stays
#
# Usage:  python3 patch_queue_v63.py [path/to/ffplay.c]
# Default path: ~/build/ffmpeg-6.1.1/fftools/ffplay.c
# Every edit must match exactly once, otherwise nothing is written.

import os
import sys

path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/build/ffmpeg-6.1.1/fftools/ffplay.c")
src = open(path, encoding="utf-8").read()

edits = []   # (name, old, new)


def edit(name, old, new):
    edits.append((name, old, new))


# ---------------------------------------------------------------- 1. natural text
edit("text: slight hinting only", r'''#ifdef TTF_HINTING_LIGHT_SUBPIXEL
    TTF_SetFontHinting(ui_fonts[i].font, cfg_crisp ? TTF_HINTING_LIGHT_SUBPIXEL : TTF_HINTING_LIGHT);
#else
    TTF_SetFontHinting(ui_fonts[i].font, cfg_crisp ? TTF_HINTING_NORMAL : TTF_HINTING_LIGHT);
#endif
    TTF_SetFontKerning(ui_fonts[i].font, 1);
''', r'''    TTF_SetFontHinting(ui_fonts[i].font, TTF_HINTING_LIGHT);    /* v63: slight hinting, the way desktop apps draw text: no extra sharpening */
    TTF_SetFontKerning(ui_fonts[i].font, 1);
''')

edit("text: cfg_crisp comment", r'''static int     cfg_crisp = 1;               /* 1 = letters placed with sub-pixel accuracy (v45) */''',
     r'''static int     cfg_crisp = 1;               /* v63: not used any more (text is drawn naturally); still read so an old settings file loads */''')

edit("text: crisp_text no longer saved", r'''    fprintf(f, "# 1 = letters are placed with sub-pixel accuracy (tighter, crisper titles), 0 = the older rendering\ncrisp_text = %d\n\n", cfg_crisp);
''', "")

# ---------------------------------------------------------------- 4 + 5. end of a file, repeat, exit at the end
edit("end: flag for a file that reached its end", r'''static const void *volatile ui_failed_is = NULL;    /* v47: the stream whose file could not be opened */''',
     r'''static const void *volatile ui_failed_is = NULL;    /* v47: the stream whose file could not be opened */
static const void *volatile ui_ended_is = NULL;     /* v63: the stream that reached the end of its file (that is not a failure) */''')

edit("end: hold on the last item, songs too, never while repeating", r'''/* The end of the last video of the queue, when the player does not quit: it stays on its last picture instead */
static int ui_hold_last_wanted(VideoState *is)
{
    return !cfg_quit_when_done && is != xf_stream && is->video_st && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC) &&
           q_count > 0 && q_pos >= 0 && q_pos < q_count && q_forced < 0 && queue_next() >= q_count;
}''', r'''/* The end of the last item of the queue (a video or a song), when the player does not quit: it pauses there instead of going to
   the idle screen (v63). While repeating there is no last item. */
static int ui_hold_last_wanted(VideoState *is)
{
    return !cfg_quit_when_done && is != xf_stream && q_repeat == 0 &&
           q_count > 0 && q_pos >= 0 && q_pos < q_count && q_forced < 0 && queue_next() >= q_count;
}''')

edit("end: the reader marks a normal end", r'''                } else {
                    ret = AVERROR_EOF;
                    goto fail;
                }''', r'''                } else {
                    ui_ended_is = is;           /* v63: a normal end, not a failed file */
                    ret = AVERROR_EOF;
                    goto fail;
                }''')

edit("end: a normal end is not a failure", r'''        ui_failed_is = is;                      /* v47: the main loop skips this item instead of repeating or quitting */''',
     r'''        if (ui_ended_is == is)                  /* v63: it reached its end: not a failure, so repeat and quit-at-the-end see a played item */
            ui_ended_is = NULL;
        else
            ui_failed_is = is;                  /* v47: the main loop skips this item instead of repeating or quitting */''')

# ---------------------------------------------------------------- 3. search sections
edit("sections: state", r'''static UiTvSec ui_tv_sec[3];''', r'''static UiTvSec ui_tv_sec[4];''')
edit("sections: heights", r'''static int ui_tv_secy[3][2];''', r'''static int ui_tv_secy[4][2];''')
edit("sections: names", r'''static const char * const ui_tv_title[3] = { "In this queue", "In Music", "In Videos" };''',
     r'''static const char * const ui_tv_title[4] = { "In this queue", "In Videos", "In Music", "Elsewhere" };    /* v63 */''')
edit("sections: three folders", r'''static UiTvLib ui_tv_lib[2];''', r'''static UiTvLib ui_tv_lib[3];                    /* 0 = Music, 1 = Videos, 2 = elsewhere (v63) */
static char ui_tv_skip[2][1024];                /* the Music and Videos folders: "Elsewhere" does not look in them again */
static int ui_tv_visits = 0;                    /* how many directory entries the reading may still look at */''')

edit("sections: reading a folder", r'''    if (depth > 6 || *budget <= 0)
        return;
    d = opendir(dir);''', r'''    if (depth > 6 || *budget <= 0 || ui_tv_visits <= 0)
        return;
    d = opendir(dir);''')
edit("sections: reading a folder 2", r'''    while ((e = readdir(d)) && *budget > 0) {
        const char *dot;
        int k;
''', r'''    while (*budget > 0 && ui_tv_visits-- > 0 && (e = readdir(d))) {
        const char *dot;
        int k;
''')
edit("sections: reading a folder 3", r'''        if (S_ISDIR(st.st_mode)) {
            ui_tv_scan_dir(path, kind, depth + 1, budget);
        } else if (S_ISREG(st.st_mode) && (dot = strrchr(e->d_name, '.')) && dot[1]) {
            for (k = 0; ui_tv_ext[kind][k]; k++)
                if (!av_strcasecmp(dot + 1, ui_tv_ext[kind][k])) {
                    ui_tv_lib_add(kind, path);
                    (*budget)--;
                    break;
                }
        }''', r'''        if (S_ISDIR(st.st_mode)) {
            if (kind == 2 && (!strcmp(path, ui_tv_skip[0]) || !strcmp(path, ui_tv_skip[1])))
                continue;                       /* v63: Music and Videos have their own sections */
            ui_tv_scan_dir(path, kind, depth + 1, budget);
        } else if (S_ISREG(st.st_mode) && (dot = strrchr(e->d_name, '.')) && dot[1]) {
            int row;

            for (row = 0; row < 2; row++) {     /* kind 2 (elsewhere) takes songs and videos */
                if (kind != 2 && kind != row)
                    continue;
                for (k = 0; ui_tv_ext[row][k]; k++)
                    if (!av_strcasecmp(dot + 1, ui_tv_ext[row][k])) {
                        ui_tv_lib_add(kind, path);
                        (*budget)--;
                        row = 2;                /* found: leave both loops */
                        break;
                    }
            }
        }''')

edit("sections: reading thread", r'''        else
            ui_tv_userdir(k ? "XDG_VIDEOS_DIR" : "XDG_MUSIC_DIR", k ? "Videos" : "Music", dir, sizeof(dir));
        ui_tv_scan_dir(dir, k, 0, &budget);
    }
    ui_tv_scan_state = 2;''', r'''        else
            ui_tv_userdir(k ? "XDG_VIDEOS_DIR" : "XDG_MUSIC_DIR", k ? "Videos" : "Music", dir, sizeof(dir));
        snprintf(ui_tv_skip[k], sizeof(ui_tv_skip[k]), "%s", dir);
        while (strlen(ui_tv_skip[k]) > 1 && ui_tv_skip[k][strlen(ui_tv_skip[k]) - 1] == '/')
            ui_tv_skip[k][strlen(ui_tv_skip[k]) - 1] = 0;
        ui_tv_visits = 300000;
        ui_tv_scan_dir(dir, k, 0, &budget);
    }
    {                                           /* v63: elsewhere = the rest of the home folder (hidden folders are left out) */
        const char *home = getenv("HOME");
        int budget2 = 20000;

        if (home && home[0]) {
            ui_tv_visits = 300000;
            ui_tv_scan_dir(home, 2, 0, &budget2);
        }
    }
    ui_tv_scan_state = 2;''')

edit("sections: clearing the folders", r'''    for (k = 0; k < 2; k++) {
        for (i = 0; i < ui_tv_lib[k].n; i++)
            av_free(ui_tv_lib[k].p[i]);
        ui_tv_lib[k].n = 0;
    }''', r'''    for (k = 0; k < 3; k++) {
        for (i = 0; i < ui_tv_lib[k].n; i++)
            av_free(ui_tv_lib[k].p[i]);
        ui_tv_lib[k].n = 0;
    }''')

edit("sections: search 1", r'''    for (s = 0; s < 3; s++) {
        ui_tv_sec_free(&ui_tv_sec[s]);
        ui_tv_sec[s].pos = 0.0;''', r'''    for (s = 0; s < 4; s++) {
        ui_tv_sec_free(&ui_tv_sec[s]);
        ui_tv_sec[s].pos = 0.0;''')

edit("sections: search 2", r'''        for (k = 0; k < 2; k++)
            for (i = 0; i < ui_tv_lib[k].n; i++) {
                ui_tv_name(ui_tv_lib[k].p[i], nm, sizeof(nm));
                sc = ui_tv_match(nm, ui_tv_q, hl);
                if (sc > 0)
                    ui_tv_offer(&ui_tv_sec[1 + k], ui_tv_lib[k].p[i], sc, hl);
            }''', r'''        for (k = 0; k < 3; k++) {
            static const int sec_of[3] = { 2, 1, 3 };       /* Music is the third section, Videos the second, Elsewhere the fourth */

            for (i = 0; i < ui_tv_lib[k].n; i++) {
                ui_tv_name(ui_tv_lib[k].p[i], nm, sizeof(nm));
                sc = ui_tv_match(nm, ui_tv_q, hl);
                if (sc > 0)
                    ui_tv_offer(&ui_tv_sec[sec_of[k]], ui_tv_lib[k].p[i], sc, hl);
            }
        }''')

edit("sections: search 3", r'''    for (s = 0; s < 3; s++)
        if (ui_tv_sec[s].n > 1)
            qsort(ui_tv_sec[s].h, ui_tv_sec[s].n, sizeof(UiTvHit), ui_tv_cmp);
    for (s = 2; s >= 0; s--)''', r'''    for (s = 0; s < 4; s++)
        if (ui_tv_sec[s].n > 1)
            qsort(ui_tv_sec[s].h, ui_tv_sec[s].n, sizeof(UiTvHit), ui_tv_cmp);
    for (s = 3; s >= 0; s--)''')

edit("sections: reset", r'''    for (s = 0; s < 3; s++)
        ui_tv_sec_free(&ui_tv_sec[s]);
    ui_tv_focus = av_clip(q_pos, 0, q_count - 1);''', r'''    for (s = 0; s < 4; s++)
        ui_tv_sec_free(&ui_tv_sec[s]);
    ui_tv_focus = av_clip(q_pos, 0, q_count - 1);''')

edit("sections: exit", r'''    for (s = 0; s < 3; s++)
        ui_tv_sec_free(&ui_tv_sec[s]);
    ui_tvc_open = 0;
    ui_pv_request(NULL);
    if (ui_flow_video(is) && ui_vflow) {''', r'''    for (s = 0; s < 4; s++)
        ui_tv_sec_free(&ui_tv_sec[s]);
    ui_tvc_open = 0;
    ui_pv_request(NULL);
    if (ui_flow_video(is) && ui_vflow) {''')

edit("sections: keys", r'''        for (s = ui_tv_act + drow; drow && s >= 0 && s < 3; s += drow)''',
     r'''        for (s = ui_tv_act + drow; drow && s >= 0 && s < 4; s += drow)''')

edit("sections: mouse", r'''    for (s = 0; s < 3; s++)
        if (y >= ui_tv_secy[s][0] && y < ui_tv_secy[s][1])''', r'''    for (s = 0; s < 4; s++)
        if (y >= ui_tv_secy[s][0] && y < ui_tv_secy[s][1])''')

edit("sections: draw height", r'''        double secH = (cbot - ctop) / 3.0;''', r'''        double secH = (cbot - ctop) / 4.0;''')
edit("sections: draw loop", r'''        for (s = 0; s < 3; s++) {
            UiTvSec *sec = &ui_tv_sec[s];
            UiTvRow row;''', r'''        for (s = 0; s < 4; s++) {
            UiTvSec *sec = &ui_tv_sec[s];
            UiTvRow row;''')
edit("sections: music tiles sit closer", r'''            row.sw = (int)(sh * (s == 1 ? 1.22 : 1.75));            /* v39: music tiles sit closer */''',
     r'''            row.sw = (int)(sh * (s == 2 ? 1.22 : 1.75));            /* v39: music tiles sit closer (v63: Music is the third section) */''')
edit("sections: tap", r'''    } else if (sec >= 0 && sec < 3) {
        if (item == ui_tv_sec[sec].target && ui_tv_act == sec)''', r'''    } else if (sec >= 0 && sec < 4) {
        if (item == ui_tv_sec[sec].target && ui_tv_act == sec)''')
edit("sections: item path", r'''    if (sec >= 0 && sec < 3 && item < ui_tv_sec[sec].n)''', r'''    if (sec >= 0 && sec < 4 && item < ui_tv_sec[sec].n)''')

# ---------------------------------------------------------------- 2. the search box of the tiles view
edit("search box", r'''    {
        int r, g, b, tx = box.x + 18, cy = box.y + box.h / 2, al = (int)(255 * ep * (vm ? 1.0 - ui_sf_p : 1.0));
        SDL_Rect caret;

        if (!vm || ui_sf_p < 0.5)               /* v57: no search box in the Stripfilm layout */
            ui_glass(&box, box.h / 2);
        ui_tv_theme(&r, &g, &b);
        if (ui_tv_q[0]) {
            ui_label(tx, cy, ui_tv_q, sm ? 15 : 18, 255, 255, 255, al);
            caret.x = tx + ui_text_width(ui_tv_q, sm ? 15 : 18) + 2;
        } else {
            ui_label(tx, cy, "Search the queue, your music and your videos", sm ? 15 : 17, 255, 255, 255, al * 68 / 100);
            caret.x = tx - 2;
        }''', r'''    {
        int r, g, b, ipx = sm ? 16 : 18, tpx = sm ? 15 : 18, ix = box.x + (sm ? 12 : 16), tx = ix + ipx + 10, cy = box.y + box.h / 2;
        int al = (int)(255 * ep * (vm ? 1.0 - ui_sf_p : 1.0)), fw = box.x + box.w - 18 - tx;      /* fw: the room the text has */
        char vis[128];
        SDL_Rect caret;

        if (!vm || ui_sf_p < 0.5) {             /* v57: no search box in the Stripfilm layout */
            SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
            SDL_SetRenderDrawColor(renderer, 16, 18, 24, al * 215 / 255);       /* v63: its own dark background: the picture behind never shows through */
            ui_pill(&box);
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, al * 24 / 255);     /* and a light veil on it, so the box stays defined */
            ui_pill(&box);
        }
        ui_tv_theme(&r, &g, &b);
        ui_icon(UI_IC_SEARCH, ix, cy, ipx, 210, 210, 210, al);
        if (ui_tv_q[0]) {
            snprintf(vis, sizeof(vis), "%s", ui_tv_q);
            while (vis[0] && ui_text_width(vis, tpx) > fw) {    /* too long for the box: the end of it stays in sight, with the caret */
                int n = 1;

                while ((vis[n] & 0xC0) == 0x80)
                    n++;                        /* a whole character at a time */
                memmove(vis, vis + n, strlen(vis + n) + 1);
            }
            ui_label(tx, cy, vis, tpx, 255, 255, 255, al);
            caret.x = tx + ui_text_width(vis, tpx) + 2;
        } else {
            snprintf(vis, sizeof(vis), "%s", "Search the queue, your videos and your music");
            ui_fit_text(vis, tpx, fw);          /* cut with ... when the box is narrow */
            ui_label(tx, cy, vis, tpx, 255, 255, 255, al * 68 / 100);
            caret.x = tx - 2;
        }''')

# ---------------------------------------------------------------- 6. miniplayer: swipe over the music tiles
edit("swipe: declaration", r'''static void ui_flow_swipe(VideoState *is, SDL_Event *ev);''', r'''static void ui_flow_swipe(VideoState *is, SDL_Event *ev, int vertical);''')
edit("swipe: definition", r'''static void ui_flow_swipe(VideoState *is, SDL_Event *ev)
{''', r'''static void ui_flow_swipe(VideoState *is, SDL_Event *ev, int vertical)
{''')
edit("swipe: amount", r'''#if SDL_VERSION_ATLEAST(2, 0, 18)
    amount = ev->wheel.preciseX;
#else
    amount = ev->wheel.x;
#endif''', r'''#if SDL_VERSION_ATLEAST(2, 0, 18)
    amount = vertical ? -ev->wheel.preciseY : ev->wheel.preciseX;      /* v63: vertical = a wheel turned down goes on to the next item */
#else
    amount = vertical ? -ev->wheel.y : ev->wheel.x;
#endif''')
edit("swipe: sideways call", r'''            ui_flow_swipe(is, ev);
        is->force_refresh = 1;''', r'''            ui_flow_swipe(is, ev, 0);
        is->force_refresh = 1;''')
edit("swipe: miniplayer", r'''    zone = ui_wheel_zone(is);
    act = zone == 1 ? 0 : zone == 2 ? 1 : cfg_wheel;''', r'''    zone = ui_wheel_zone(is);
    if (ui_pip && !zone && !ui_tv_on(is) && ui_flow_on(is) && q_count > 1) {    /* v63: the miniplayer's music tiles: a swipe over them moves through the queue */
        ui_flow_swipe(is, ev, 1);
        is->force_refresh = 1;
        return;
    }
    act = zone == 1 ? 0 : zone == 2 ? 1 : cfg_wheel;''')

# ---------------------------------------------------------------- 7. wheel and two finger swipes on the seek / volume bar
edit("bars: vertical wheel wins on the bars", r"""    if (FFABS(ax) > FFABS(ay)) {                /* a sideways swipe: along the tiles of the view, or through the queue */""",
     r"""    if ((ay == 0.0 || !ui_wheel_zone(is)) && FFABS(ax) > FFABS(ay)) {   /* a sideways swipe: along the tiles of the view, or through the queue (v63: on the seek and volume bars an up or down swipe is never taken for a sideways one) */""")

# ---------------------------------------------------------------- 8. transitions: tiles of all -> strip -> video
edit("views: step back to the strip", r"""/* A two finger swipe up or down over a video. One swipe moves one step (closed > strip > all tiles), a hard swipe up from the""",
     r"""/* v63: out of the tiles of all over a video: the strip always comes first, never the full video window directly.
   Returns 1 if it went to the strip. (The other way round stays: a hard swipe up from the full video goes straight to the tiles.) */
static int ui_sf_step_back(VideoState *is)
{
    if (!ui_flow_video(is) || ui_sf_cur(is) != 2)
        return 0;
    if (ui_tv_q[0] || ui_tv_searching) {        /* the search ends first: the strip shows the queue */
        ui_tv_q[0] = 0;
        ui_tv_searching = 0;
        ui_tv_search();
    }
    ui_sf_level(is, 1);
    return 1;
}

/* A two finger swipe up or down over a video. One swipe moves one step (closed > strip > all tiles), a hard swipe up from the""")

edit("views: hard swipe down from the tiles stops at the strip", r"""    lvl = av_clip(lvl, 0, 2);
    if (lvl != cur)
        ui_sf_level(is, lvl);""", r"""    lvl = av_clip(lvl, 0, 2);
    if (base == 2 && lvl < 1)
        lvl = 1;                                /* v63: from the tiles of all down is the strip, even for a hard swipe */
    if (lvl != cur)
        ui_sf_level(is, lvl);""")

edit("views: tap on the playing tile", r"""    if (idx >= 0 && idx == q_pos) {             /* the one that plays: back to it */
        if (ui_flow_video(is))""", r"""    if (idx >= 0 && idx == q_pos && ui_sf_step_back(is)) {      /* v63: from the tiles of all it goes to the strip first */
        if (is->paused)
            toggle_pause(is);
        return;
    }
    if (idx >= 0 && idx == q_pos) {             /* the one that plays: back to it */
        if (ui_flow_video(is))""")

edit("views: tap on another tile", r"""    if (!ui_sf_active(is))                      /* v58: the Stripfilm view stays open while the next video starts */
        ui_tv_exit(is);""", r"""    if (!ui_sf_active(is) && !ui_sf_step_back(is))      /* v58: the Stripfilm view stays open while the next video starts (v63: also from the tiles of all) */
        ui_tv_exit(is);""")

edit("views: Esc", r"""        } else {
            ui_tv_exit(is);
        }
        return 1;
    case SDLK_TAB:
        ui_tv_exit(is);
        return 1;""", r"""        } else if (!ui_sf_step_back(is)) {      /* v63: from the tiles of all over a video Esc goes to the strip */
            ui_tv_exit(is);
        }
        return 1;
    case SDLK_TAB:
        if (!ui_sf_step_back(is))
            ui_tv_exit(is);
        return 1;""")

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
print("v63: %d edits applied to %s" % (len(edits), path))
