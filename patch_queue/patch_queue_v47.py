#!/usr/bin/env python3
# Update 47 for ffplay-custom (on top of patch_queue_v46.py).
#   * The sliders in Preferences have no white knob any more: just the track and the fill, like the seek bar.
#   * Tiles follow the roundness setting all the way: their soft shadow is rounded too (it was a plain rectangle that showed past
#     the corners), and the file icon is drawn with the same corner radius (it had its corners baked in).
#   * Crossfade and Sleep timer are gone from Preferences: they stay in the queue menu (Off, End of track, then the minutes).
#   * Preferences has no cascade: every choice is showing all the time. Rest the mouse on a row and its title nudges a little
#     from the left margin, and the choice under the mouse grows from its own centre (a small zoom that settles).
#   * A queue file that is not there any more (deleted after it was queued) is skipped and the next item plays. The player
#     only quits at the end of the queue if something really played.
#   * Dragging a queue item to the top or bottom of the list scrolls it smoothly (by time, not one row every 90 ms).
#   * The placeholder in the tiled view's search box is brighter and a size larger, so it reads sharper.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v46.py. Writes the file only if every edit matches.
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


def region(name, start, end, new):
    """Replace everything from start up to (not including) end."""
    global src
    if src.count(start) != 1 or src.count(end) != 1:
        print("FAILED: %s (markers %d / %d)" % (name, src.count(start), src.count(end)))
        fails.append(name)
        return
    a = src.index(start)
    b = src.index(end)
    if b < a:
        print("FAILED: %s (markers in the wrong order)" % name)
        fails.append(name)
        return
    src = src[:a] + new + src[b:]
    print("ok: " + name)


if "ui_label_cs" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_sl_draw" not in src:
    print("Apply patch_queue_v46.py first. Nothing written.")
    sys.exit(1)

# ---------------------------------------------------------------- 1. sliders without the knob
patch("slider: no knob (declarations)", "    SDL_Rect tr, fill, knob;\n    char text[32];\n    int x0, x1, xr, d, hot = r == ui_prefs_hover || r == ui_pref_drag;",
      "    SDL_Rect tr, fill;\n    char text[32];\n    int x0, x1, xr, hot = r == ui_prefs_hover || r == ui_pref_drag;")
patch("slider: the track is a little thicker under the mouse", "    tr.y = cy - 3;\n    tr.w = x1 - x0;\n    tr.h = 6;\n",
      "    tr.h = hot ? 8 : 6;                         /* v47: no knob: the track thickens a little under the mouse */\n    tr.y = cy - tr.h / 2;\n    tr.w = x1 - x0;\n")
patch("slider: knob drawing removed", """    d = r == ui_pref_drag ? 20 : hot ? 17 : 14;
    knob.w = knob.h = d;
    knob.x = x0 + (int)((x1 - x0) * t) - d / 2;
    knob.y = cy - d / 2;
    SDL_SetRenderDrawColor(renderer, 245, 245, 245, 245);
    ui_pill(&knob);
""", "")

patch("slider: nothing is drawn for an empty slider", "    fill.w = FFMAX((int)(tr.w * t), tr.h);",
      "    fill.w = t > 0.0 ? FFMAX((int)(tr.w * t), tr.h) : 0;       /* v47: no stub at the start (the knob used to hide it) */")
patch("slider: fill only when there is some", "    ui_pill(&fill);                             /* the part before the knob: a lighter shade of the bar color */",
      "    if (fill.w > 0)\n        ui_pill(&fill);                         /* the part before the value: a lighter shade of the bar color */")

# ---------------------------------------------------------------- 2. text that grows from its centre
patch("ui_label_cs", """/* Draw text with its middle at cx */
static void ui_label_c(int cx, int cy, const char *s, int px, int r, int g, int b, int a)
{
    ui_label(cx - ui_text_width(s, px) / 2, cy, s, px, r, g, b, a);
}
""", """/* Draw text with its middle at cx */
static void ui_label_c(int cx, int cy, const char *s, int px, int r, int g, int b, int a)
{
    ui_label(cx - ui_text_width(s, px) / 2, cy, s, px, r, g, b, a);
}

/* v47: the same, grown by sc around its own centre (1.0 = as it is): the pop of a choice under the mouse */
static void ui_label_cs(int cx, int cy, const char *s, int px, int r, int g, int b, int a, double sc)
{
    int w = 0, h = 0;
    SDL_Texture *tex;
    SDL_Rect dst;

    tex = sc > 1.004 ? ui_text_tex(s, px, &w, &h) : NULL;
    if (!tex) {
        ui_label_c(cx, cy, s, px, r, g, b, a);
        return;
    }
    a = (int)(a * ui_fade);
    dst.w = (int)(w * sc + 0.5);
    dst.h = (int)(h * sc + 0.5);
    dst.x = cx - dst.w / 2;
    dst.y = cy - dst.h / 2;
    ui_ink(&r, &g, &b);                         /* dark text on the light glass */
    SDL_SetTextureColorMod(tex, r, g, b);
    SDL_SetTextureAlphaMod(tex, a);
    SDL_RenderCopy(renderer, tex, NULL, &dst);
}
""")

# ---------------------------------------------------------------- 3. tiles follow the roundness
patch("quad_round prototypes", "static void ui_flow_quad_round(SDL_Texture *tex, const SDL_Rect *t, int al, int md, double tilt, int rr);\n",
      "static void ui_flow_quad_round(SDL_Texture *tex, const SDL_Rect *t, int al, int md, double tilt, int rr);\n"
      "static void ui_flow_quad_rpx(SDL_Texture *tex, const SDL_Rect *t, int al, int md, double tilt, int rr);\n"
      "static void ui_tile_shadow(SDL_Texture *tex, const SDL_Rect *t, int al, double tilt, int rr);\n")

patch("quad_round becomes quad_rpx (radius in pixels)",
      "static void ui_flow_quad_round(SDL_Texture *tex, const SDL_Rect *t, int al, int md, double tilt, int rr)\n{\n    enum { NA = 14,",
      "static void ui_flow_quad_rpx(SDL_Texture *tex, const SDL_Rect *t, int al, int md, double tilt, int rr)\n{\n    enum { NA = 14,")
patch("quad_rpx: the radius is used as it is",
      "    rr = (int)(av_clip(rr, 0, FFMIN(t->w, t->h) / 2) * ui_round_k() + 0.5);     /* v46 */\n    c.r = (Uint8)md;",
      "    rr = av_clip(rr, 0, FFMIN(t->w, t->h) / 2);       /* v47: the radius is in pixels here; ui_flow_quad_round applies the roundness */\n    c.r = (Uint8)md;")
patch("quad_round wrapper and the rounded shadow",
      "    ui_quad_fringe(tex, v, NC);\n}\n\n/* While the queue view is over a video: remember where the video is drawn full screen",
      "    ui_quad_fringe(tex, v, NC);\n}\n\n"
      "/* Like ui_flow_quad_rpx, with the radius the tile would have at 100% roundness (the setting is applied here) */\n"
      "static void ui_flow_quad_round(SDL_Texture *tex, const SDL_Rect *t, int al, int md, double tilt, int rr)\n{\n"
      "    ui_flow_quad_rpx(tex, t, al, md, tilt, (int)(av_clip(rr, 0, FFMIN(t->w, t->h) / 2) * ui_round_k() + 0.5));      /* v46 */\n}\n\n"
      "/* v47: the soft shadow of a tile has the tile's rounded corners (it was a plain rectangle that showed past them) */\n"
      "static void ui_tile_shadow(SDL_Texture *tex, const SDL_Rect *t, int al, double tilt, int rr)\n{\n"
      "    SDL_Rect sh;\n    int k, base = (int)(av_clip(rr, 0, FFMIN(t->w, t->h) / 2) * ui_round_k() + 0.5);\n\n"
      "    for (k = ui_shadows_on ? 3 : 0; k >= 1; k--) {\n"
      "        sh.x = t->x - k * 4;\n        sh.y = t->y - k * 4 + 7;\n        sh.w = t->w + k * 8;\n        sh.h = t->h + k * 8;\n"
      "        ui_flow_quad_rpx(tex, &sh, al * 16 / 255, 0, tilt, base > 0 ? base + k * 4 : 0);   /* square stays square */\n"
      "    }\n}\n\n"
      "/* While the queue view is over a video: remember where the video is drawn full screen")

region("cover-flow tile: rounded shadow for the rounded tiles",
       "static void ui_flow_tile(int idx, const SDL_Rect *tile, int al, int md, double tilt)\n{",
       "/* The size of the picture of item i fitted into a sw x sh slot",
       """static void ui_flow_tile(int idx, const SDL_Rect *tile, int al, int md, double tilt)
{
    SDL_Texture *tex;
    SDL_Rect sh;
    int cw = 0, ch = 0, k, vid;

    tex = ui_cov_native(q_items[idx], &cw, &ch);        /* a video keeps its own shape, whatever is playing */
    vid = tex != NULL;
    if (!tex)
        tex = ui_cov_get(q_items[idx], &cw, &ch);
    if (tex && vid) {                           /* v47: the shadow of a rounded tile is rounded too */
        ui_tile_shadow(tex, tile, al, tilt, FFMIN(tile->w, tile->h) / 11);
    } else if (tex) {                           /* a soft shadow in the card's own shape: the picture again, black and bigger */
        for (k = ui_shadows_on ? 3 : 0; k >= 1; k--) {
            sh.x = tile->x - k * 4;
            sh.y = tile->y - k * 4 + 7;
            sh.w = tile->w + k * 8;
            sh.h = tile->h + k * 8;
            ui_flow_quad(tex, &sh, al * 16 / 255, 0, tilt);
        }
    } else {
        tex = ui_flow_icon();                   /* no picture (yet): the file icon */
    }
    if (tex && vid)                             /* the tiles of videos have the rounded corners of the playing one */
        ui_flow_quad_round(tex, tile, al, md, tilt, FFMIN(tile->w, tile->h) / 11);
    else if (tex)
        ui_flow_quad(tex, tile, al, md, tilt);
}

""")

region("tiled view tile: rounded shadow",
       "static void ui_tv_tile(const char *path, const SDL_Rect *t, int al, int md)\n{",
       "/* ---- v39: a video tile plays (picture only, at the video's own rate)",
       """static void ui_tv_tile(const char *path, const SDL_Rect *t, int al, int md)
{
    SDL_Texture *tex;
    int cw = 0, ch = 0;

    tex = ui_cov_native(path, &cw, &ch);
    if (!tex)
        tex = ui_cov_get(path, &cw, &ch);
    if (tex)                                    /* v47: the shadow has the same rounded corners as the tile */
        ui_tile_shadow(tex, t, al, 0.0, FFMIN(t->w, t->h) / 11);
    else
        tex = ui_flow_icon();
    if (tex)
        ui_flow_quad_round(tex, t, al, md, 0.0, FFMIN(t->w, t->h) / 11);
}

""")

patch("file icon: the baked corners follow the roundness",
      "    int k = (cfg_bar_r << 16) | (cfg_bar_g << 8) | cfg_bar_b, x, y, e;\n    double u = S / 100.0, rr = S / 11.0,",
      "    int k = ((cfg_bar_r << 16) | (cfg_bar_g << 8) | cfg_bar_b) | (av_clip(cfg_round, 0, 100) << 24), x, y, e;   /* v47: remade when the roundness changes */\n"
      "    double u = S / 100.0, rr = S / 11.0 * ui_round_k(),")

# ---------------------------------------------------------------- 4. the search box text
patch("search box placeholder: brighter and a size larger",
      'ui_label(tx, cy, "Search the queue, your music and your videos", sm ? 14 : 16, 255, 255, 255, al * 45 / 100);',
      'ui_label(tx, cy, "Search the queue, your music and your videos", sm ? 15 : 17, 255, 255, 255, al * 68 / 100);')

# ---------------------------------------------------------------- 5. Preferences: no Crossfade / Sleep timer rows, no cascade
patch("prefs: shown rows", "#define UI_PREF_ROWS 11\n",
      "#define UI_PREF_ROWS 11                 /* the row numbers the code knows (7 and 8, Crossfade and Sleep timer, live in the queue menu now) */\n"
      "#define UI_PREF_SHOWN 9                 /* v47: the rows that are shown */\n"
      "#define UI_PREF_NUDGE 6                 /* v47: how far the title of the row under the mouse moves from its margin */\n")
patch("prefs: hover amount", "static double ui_pref_pop[UI_PREF_ROWS][10];",
      "static double ui_pref_hv[UI_PREF_ROWS];     /* v47: 0 to 1: how far the title of each row has moved for the mouse on it */\n"
      "static double ui_pref_pop[UI_PREF_ROWS][10];")
patch("prefs: order of the rows", "static const int ui_pref_map[UI_PREF_ROWS] = { 0, 1, 7, 8, 2, 3, 4, 5, 6, 9, 10 };",
      "static const int ui_pref_map[UI_PREF_SHOWN] = { 0, 1, 2, 3, 4, 5, 6, 9, 10 };")
patch("prefs: row position", "    for (i = 0; i < UI_PREF_ROWS; i++)\n        if (ui_pref_map[i] == row)\n            return i;\n    return 0;\n",
      "    for (i = 0; i < UI_PREF_SHOWN; i++)\n        if (ui_pref_map[i] == row)\n            return i;\n    return -1;                                  /* not shown */\n")
patch("prefs: size 1", "if (avail >= 76 + UI_PREF_ROWS * 52 + 52) {", "if (avail >= 76 + UI_PREF_SHOWN * 52 + 52) {")
patch("prefs: size 2", "} else if (avail >= 40 + UI_PREF_ROWS * 34) {", "} else if (avail >= 40 + UI_PREF_SHOWN * 34) {")
patch("prefs: size 3", "ui_pr_row = av_clip((avail - 40) / UI_PREF_ROWS, 34, 52);", "ui_pr_row = av_clip((avail - 40) / UI_PREF_SHOWN, 34, 52);")
patch("prefs: size 4", "ui_pr_row = FFMAX((avail - 30) / UI_PREF_ROWS, 22);", "ui_pr_row = FFMAX((avail - 30) / UI_PREF_SHOWN, 22);")
patch("prefs: size 5", "p.h = UI_PREF_HEAD + UI_PREF_ROWS * UI_PREF_ROW + UI_PREF_FOOT;", "p.h = UI_PREF_HEAD + UI_PREF_SHOWN * UI_PREF_ROW + UI_PREF_FOOT;")
patch("prefs: mouse row", "    if (row >= UI_PREF_ROWS || x < p.x || x >= p.x + p.w)\n        row = -1;",
      "    if (row >= UI_PREF_SHOWN || x < p.x || x >= p.x + p.w)\n        row = -1;")

region("prefs: the drawing", "static void ui_prefs_draw(void)\n{",
       "/* Mouse events while the panel is open. It uses every mouse event. */",
       r'''static void ui_prefs_draw(void)
{
    SDL_Rect p;
    int ww, wh, i, cy;
    double dt, wt;
    static int64_t last = 0;
    int64_t now = av_gettime_relative();

    if (!ui_prefs_open) {
        for (i = 0; i < UI_PREF_ROWS; i++) {
            ui_pref_open[i] = 0.0;
            ui_pref_hv[i] = 0.0;
        }
        memset(ui_pref_pop, 0, sizeof(ui_pref_pop));
        ui_prefs_anim = 0;
        ui_prefs_w = 600.0;
        return;
    }
    dt = now - last > 100000 ? 0.016 : (now - last) / 1000000.0;
    last = now;
    ui_prefs_anim = 0;
    for (i = 0; i < UI_PREF_ROWS; i++) {
        double tgt = i == ui_prefs_hover ? 1.0 : 0.0;

        ui_pref_open[i] = ui_pref_slider(i) ? 0.0 : 1.0;        /* v47: no cascade: the choices of a row are always showing */
        ui_pref_hv[i] += (tgt - ui_pref_hv[i]) * (1.0 - exp(-dt / 0.07));     /* the title of the row under the mouse nudges */
        if (fabs(tgt - ui_pref_hv[i]) < 0.005)
            ui_pref_hv[i] = tgt;
        else
            ui_prefs_anim = 1;
    }
    SDL_GetWindowSize(window, &ww, &wh);
    wt = 600.0;                                 /* wide enough for the name and all the choices of the longest row */
    for (i = 0; i < UI_PREF_ROWS; i++)
        if (ui_pref_pos(i) >= 0 && !ui_pref_slider(i))
            wt = FFMAX(wt, ui_pref_need_w(i));
    ui_prefs_w = FFMIN(wt, ww - 16);
    p = ui_prefs_rect(ww, wh);
    ui_glass(&p, 28);

    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    ui_label(p.x + ui_pr_mg, p.y + UI_PREF_HEAD / 2 + 4, "Preferences", ui_pr_tpx, 245, 245, 245, 255);
    for (i = 0; i < UI_PREF_ROWS; i++) {
        static const int pic[UI_PREF_ROWS] = { UI_IC_VOLUME, UI_IC_EYE, UI_IC_EXPAND, UI_IC_DROP,
                                               UI_IC_BOOKMARK, UI_IC_EXIT, UI_IC_MOUSE, UI_IC_FADE, UI_IC_MOON,
                                               UI_IC_DROP, UI_IC_EXPAND };
        double hv = ui_pref_hv[i];
        int nudge;

        if (ui_pref_pos(i) < 0)
            continue;                           /* Crossfade and Sleep timer are in the queue menu */
        cy = p.y + UI_PREF_HEAD + ui_pref_pos(i) * UI_PREF_ROW + UI_PREF_ROW / 2;
        hv = hv * hv * (3.0 - 2.0 * hv);
        nudge = (int)(UI_PREF_NUDGE * hv + 0.5);        /* the icon and the name move a little from the left margin */
        ui_icon(pic[i], p.x + ui_pr_mg + nudge, cy, av_clip(ui_pr_px, 14, 22), 245, 245, 245, i == ui_prefs_hover ? 255 : 170);
        ui_label(p.x + ui_pr_mg + UI_PREF_ICW + nudge, cy, ui_pref_name[i], ui_pr_px, 245, 245, 245,
                 i == ui_prefs_hover ? 255 : 210);
        if (ui_pref_slider(i)) {                /* v46 */
            ui_sl_draw(&p, i, cy);
            continue;
        }
        {                                       /* the choices: all showing; the one under the mouse grows from its centre */
            SDL_Rect r[10];
            const char *names[10];
            char store[10][20];
            int n, c, sel, px, hot;

            n = ui_pref_layout(i, &p, cy, r, names, store, &sel, &px);
            for (c = 0; c < n; c++) {
                int mv = 0, cx = r[c].x + r[c].w / 2;
                double pe, sc;

                hot = i == ui_prefs_hover && ui_prefs_mx >= r[c].x && ui_prefs_mx < r[c].x + r[c].w &&
                      ui_prefs_my >= r[c].y && ui_prefs_my < r[c].y + r[c].h;
                pe = ui_pop_step(&ui_pref_pop[i][c], hot, dt, &mv);
                if (mv)
                    ui_prefs_anim = 1;
                sc = 1.0 + 0.15 * pe + 0.10 * sin(pe * 3.14159265);     /* a little too big on the way, then it settles */
                if (c == sel)                   /* the choice that is on: in the bar color */
                    ui_label_cs(cx, cy, names[c], px, av_clip(cfg_bar_r + 40 + (int)(30 * pe), 0, 255),
                                av_clip(cfg_bar_g + 40 + (int)(30 * pe), 0, 255), av_clip(cfg_bar_b + 40 + (int)(30 * pe), 0, 255),
                                255, sc);
                else
                    ui_label_cs(cx, cy, names[c], px, 215 + (int)(40 * pe), 215 + (int)(40 * pe), 215 + (int)(40 * pe),
                                (int)(165 + 90 * pe), sc);
            }
        }
    }
    if (UI_PREF_FOOT >= 30)
        ui_label(p.x + ui_pr_mg, p.y + p.h - UI_PREF_FOOT / 2, "Click a choice. Sliders: drag, scroll or arrows. Esc closes.",
             15, 170, 170, 170, 255);
}

''')

patch("prefs: choices can be hit as soon as the panel is up", "    if (row < 0 || row >= UI_PREF_ROWS || ui_pref_open[row] < 0.4)\n        return -1;",
      "    if (row < 0 || row >= UI_PREF_ROWS || ui_pref_slider(row) || ui_pref_pos(row) < 0)\n        return -1;")

# ---------------------------------------------------------------- 6. a missing file is skipped
patch("missing: state and test", "static int q_user_ended = 0;    /* 1 = the item that just ended was ended by the user, not by reaching its end */\n",
      "static int q_user_ended = 0;    /* 1 = the item that just ended was ended by the user, not by reaching its end */\n"
      "static int ui_played_any = 0;   /* v47: 1 once an item has really played (a queue of missing files does not quit the player) */\n"
      "static const void *volatile ui_failed_is = NULL;    /* v47: the stream whose file could not be opened */\n\n"
      "/* v47: a local file that is not there any more (deleted after it was queued) */\n"
      "static int ui_file_missing(const char *path)\n{\n"
      "    return path && path[0] && !strstr(path, \"://\") && strncmp(path, \"pipe:\", 5) && access(path, F_OK) != 0;\n}\n")
patch("missing: the reader says it failed", "    av_packet_free(&pkt);\n    if (ret != 0) {\n        SDL_Event event;\n\n        event.type = FF_QUIT_EVENT;\n        event.user.data1 = is;\n        SDL_PushEvent(&event);\n    }\n    SDL_DestroyMutex(wait_mutex);",
      "    av_packet_free(&pkt);\n    if (ret != 0) {\n        SDL_Event event;\n\n        ui_failed_is = is;                      /* v47: the main loop skips this item instead of repeating or quitting */\n        event.type = FF_QUIT_EVENT;\n        event.user.data1 = is;\n        SDL_PushEvent(&event);\n    }\n    SDL_DestroyMutex(wait_mutex);")
patch("missing: loop variables", "    /* Play the queue. The window stays open between files and when the queue is empty. */\n    for (;;) {\n        int next;\n",
      "    /* Play the queue. The window stays open between files and when the queue is empty. */\n    {\n    int missing_run = 0;                        /* v47: how many items in a row were skipped */\n\n    for (;;) {\n        int next, skip_dir;\n")
patch("missing: only quit when something played", "            if (cfg_quit_when_done && q_count > 0)\n                do_exit(NULL);                  /* something was played and the queue is done */",
      "            if (cfg_quit_when_done && q_count > 0 && ui_played_any)\n                do_exit(NULL);                  /* something was played and the queue is done */")
patch("missing: skip the item", "        q_pos = next;\n        q_step = 1;\n        q_played[q_pos] = 1;\n        q_forced = -1;\n",
      "        q_pos = next;\n        skip_dir = q_step < 0 ? -1 : 1;\n        q_step = 1;\n        q_played[q_pos] = 1;\n        q_forced = -1;\n"
      "        if (ui_file_missing(q_items[q_pos])) {  /* v47: deleted since it was queued: skip it, the next item plays */\n"
      "            av_log(NULL, AV_LOG_WARNING, \"Skipping '%s': the file is not there any more\\n\", q_items[q_pos]);\n"
      "            ui_user_skip = 1;                   /* so repeat-one does not try it again */\n"
      "            q_step = skip_dir;                  /* going back stays going back */\n"
      "            if (++missing_run >= FFMAX(q_count, 1)) {   /* every item is missing: wait on the idle screen */\n"
      "                missing_run = 0;\n"
      "                q_step = 1;\n"
      "                ui_xf_abort();\n"
      "                ui_idle_loop();\n"
      "            }\n"
      "            continue;\n"
      "        }\n"
      "        missing_run = 0;\n")
patch("missing: remember how the item ended", "        event_loop(is);                         /* returns when this item is over */\n    }\n\n    /* never returns */",
      "        {\n            const void *me = is;\n\n            event_loop(is);                     /* returns when this item is over */\n"
      "            if (ui_failed_is == me) {           /* v47: it could not be opened: it counts as skipped */\n"
      "                ui_failed_is = NULL;\n                ui_user_skip = 1;\n"
      "            } else {\n                ui_played_any = 1;\n            }\n        }\n    }\n    }\n\n    /* never returns */")

# ---------------------------------------------------------------- 7. smooth scrolling while dragging a queue item
region("queue drag: scroll by time", "static int ui_q_autoscroll(void)\n{",
       "/* The screen may go to sleep unless a video is actually playing",
       r'''static int ui_q_autoscroll(void)
{
    static int64_t last = 0;
    static double acc = 0.0;
    SDL_Rect p;
    int ww, wh, top, bottom, vis, dir = 0, before, step;
    double dt, dist = 0.0, rate;
    int64_t now = av_gettime_relative();

    if (ui_q_drag < 0) {
        last = 0;
        acc = 0.0;
        return 0;
    }
    dt = last ? av_clipd((now - last) / 1000000.0, 0.0, 0.05) : 0.0;
    last = now;
    SDL_GetWindowSize(window, &ww, &wh);
    p = ui_q_rect(ww, wh);
    vis = ui_q_visible(wh);
    top = p.y + UI_Q_PAD + UI_Q_HEAD + UI_Q_ROW / 2;
    bottom = p.y + UI_Q_PAD + UI_Q_HEAD + vis * UI_Q_ROW - UI_Q_ROW / 2;
    if (ui_q_drag_y < top) {
        dir = -1;
        dist = (double)(top - ui_q_drag_y) / UI_Q_ROW;
    } else if (ui_q_drag_y > bottom) {
        dir = 1;
        dist = (double)(ui_q_drag_y - bottom) / UI_Q_ROW;
    }
    if (!dir) {
        acc = 0.0;
        return 0;
    }
    rate = 5.0 + 6.0 * FFMIN(dist, 4.0);        /* v47: rows a second: faster the further out the mouse is; the list glides between rows */
    if (acc * dir < 0.0)
        acc = 0.0;
    acc += dir * rate * dt;
    step = (int)acc;
    if (!step)
        return 0;
    acc -= step;
    before = ui_q_scroll;
    ui_q_scroll = av_clip(ui_q_scroll + step, 0, FFMAX(q_count - vis, 0));
    return ui_q_scroll != before;
}

''')

if fails:
    print("\n%d edit(s) failed. Nothing written." % len(fails))
    sys.exit(1)
open(PATH, "w").write(src)
print("\nDone: patch_queue_v47 applied.")
