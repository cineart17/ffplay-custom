#!/usr/bin/env python3
# Update 23 for ffplay-custom (on top of patch_queue_v22.py).
#   * A translucent title bar across the top of the window in windowed mode only, drawn over the picture like the seek
#     bar (it shows when the mouse moves and hides after the hide delay): close at the left, fullscreen at the right,
#     the name of what plays in the middle. It is on the idle screen too.
#   * The strip between the two buttons moves the window. SDL is told that it is a drag area (SDL_SetWindowHitTest), so
#     the window manager does the move itself. That is what makes dragging it to the top of the screen maximize the
#     window, and dragging it to the left or right side tile it, like the windows of other apps.
#   * The old way of moving the window (hold the picture and drag, with our own snapping and the "Release for ..."
#     message) is gone: it moved the window by hand, which fought the window manager. Dragging an edge or corner still
#     resizes the window, keeping the video's shape. A window the system tiled or maximized is no longer pulled back
#     to the video's shape.
#   * The small dot that marks the item that plays now sits before its title (like the dot that marks the menu row under
#     the mouse), not on the lower left corner of its picture. It shows in both views.
#   * Reworked Esc key behaviour: Esc closes open menus/panels or exits fullscreen, rather than quitting the app.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v22.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_titlebar_draw" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_live_grab" not in src:
    print("Apply patch_queue_v22.py first. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


def replace_between(start, end, new, label):
    """Replace everything from start (found once) up to and including end (found once, after start)."""
    global src
    if src.count(start) != 1 or src.count(end) != 1:
        print("FAILED:", label, "- start matched", src.count(start), "times, end matched", src.count(end),
              "times, expected 1 each. Nothing written.")
        sys.exit(1)
    a = src.index(start)
    b = src.index(end) + len(end)
    if b <= a:
        print("FAILED:", label, "- the end comes before the start. Nothing written.")
        sys.exit(1)
    src = src[:a] + new + src[b:]
    print("ok:", label)


# ============================================================ the old snapping goes

patch("/* ---- chapters on the seek bar, the seek bar tooltip, and the window snap preview ---- */\n",
      "/* ---- chapters on the seek bar and the seek bar tooltip ---- */\n",
      "comment")

patch("#define UI_SNAP_FULL  1\n#define UI_SNAP_LEFT  2\n#define UI_SNAP_RIGHT 3\n"
      "static int ui_snap_zone = 0;        /* where the window would snap if the mouse button were released now */\n"
      "static int ui_snapped = 0;          /* 1 while the window sits in a half-screen snap */\n"
      "static int ui_prev_w = 0, ui_prev_h = 0;    /* the size to give back when a snapped window is dragged away */\n",
      "", "no snap state")

replace_between("/* While the window is dragged to a screen edge: tint it and say what will happen */\nstatic void ui_snap_draw(void)\n{\n",
                "    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);\n}\n\nstatic void ui_ctrl_draw(VideoState *is, const SDL_Rect *sk);\n",
                "static void ui_ctrl_draw(VideoState *is, const SDL_Rect *sk);\nstatic void ui_titlebar_draw(VideoState *is);\n",
                "no snap preview")

patch("    ui_ink_dark = 0;\n    ui_snap_draw();\n    SDL_RenderPresent(renderer);\n}",
      "    ui_ink_dark = 0;\n    SDL_RenderPresent(renderer);\n}",
      "no snap preview in the glass frame")

patch("    if (is)\n        ui_draw(is);\n    if (ui_scene_tex) {\n",
      "    if (is)\n        ui_draw(is);\n    ui_titlebar_draw(is);                       /* on the idle screen too */\n    if (ui_scene_tex) {\n",
      "the title bar in the glass frame")

patch("    ui_flow_draw(is);\n    ui_draw(is);\n    ui_snap_draw();\n    ui_menu_stream = is;\n",
      "    ui_flow_draw(is);\n    ui_draw(is);\n    ui_titlebar_draw(is);\n    ui_menu_stream = is;\n",
      "the title bar in the normal frame")

patch("    if (is_full_screen || ui_snapped || !is->video_st || !is->ic)\n        return;\n",
      "    if (is_full_screen || !is->video_st || !is->ic)\n        return;\n",
      "no snapped state in the aspect tick")

patch("    SDL_GetWindowSize(window, &w, &h);\n    if (w < 260 || h <= UI_BAR_H * 3)\n        return;\n",
      "    SDL_GetWindowSize(window, &w, &h);\n    if (w < 260 || h <= UI_BAR_H * 3)\n        return;\n"
      "    {                                           /* a window the system tiled or maximized keeps the size it was given */\n"
      "        SDL_Rect area;\n\n"
      "        if (SDL_GetDisplayUsableBounds(SDL_GetWindowDisplayIndex(window), &area) == 0 && h >= area.h - 40)\n"
      "            return;\n"
      "    }\n",
      "a tiled or maximized window keeps its size")

# ============================================================ moving the window: the title bar

patch("   Drag the picture to move the window. Drag an edge or corner to resize it.\n",
      "   The title bar moves the window (the window manager does the move, see ui_hit_test). Drag an edge or corner to resize it.\n",
      "comment")

patch("static int ui_win_moved = 0;    /* 1 once the mouse has moved enough to start a move */\n", "", "no move state")

replace_between("/* Mouse events for moving and resizing the window.\n",
                "        return was_resize;\n    }\n    return 0;\n}\n",
                r'''/* ---- the title bar: a translucent strip across the top of the window (windowed mode only), drawn over the picture like the seek bar ----
   Close at the left, fullscreen at the right, the name of what plays in the middle.
   The strip between the buttons moves the window: ui_hit_test tells SDL that it is a drag area, so the window manager
   does the move itself. That is why dragging it to the top of the screen maximizes the window, and to the left or right
   side tiles it, like any other window of the desktop. */
#define UI_TB_H     40                  /* height of the strip */
#define UI_TB_BTN   48                  /* width of each button */
#define UI_TB_EDGE  6                   /* the top rows stay the window's resize edge */

static int ui_tb_on = 0;                /* 1 while the strip is drawn */
static int ui_tb_hover = 0;             /* 0 = nothing, 1 = close, 2 = fullscreen */

/* One line, w pixels thick, from (x0, y0) to (x1, y1), in the current draw color */
static void ui_tb_line(double x0, double y0, double x1, double y1, double w)
{
    SDL_Vertex v[4];
    int idx[6] = { 0, 1, 2, 1, 3, 2 }, k;
    Uint8 cr, cg, cb, ca;
    double dx = x1 - x0, dy = y1 - y0, len = sqrt(dx * dx + dy * dy), nx, ny;

    if (len < 0.01)
        return;
    nx = -dy / len * w / 2.0;
    ny = dx / len * w / 2.0;
    SDL_GetRenderDrawColor(renderer, &cr, &cg, &cb, &ca);
    v[0].position.x = (float)(x0 + nx);
    v[0].position.y = (float)(y0 + ny);
    v[1].position.x = (float)(x0 - nx);
    v[1].position.y = (float)(y0 - ny);
    v[2].position.x = (float)(x1 + nx);
    v[2].position.y = (float)(y1 + ny);
    v[3].position.x = (float)(x1 - nx);
    v[3].position.y = (float)(y1 - ny);
    for (k = 0; k < 4; k++) {
        v[k].color.r = cr;
        v[k].color.g = cg;
        v[k].color.b = cb;
        v[k].color.a = ca;
        v[k].tex_coord.x = 0;
        v[k].tex_coord.y = 0;
    }
    SDL_RenderGeometry(renderer, NULL, v, 4, idx, 6);
}

static void ui_titlebar_draw(VideoState *is)
{
    SDL_Rect row;
    char name[300];
    int w, h, y, a, sx, sy, cy = UI_TB_H / 2, cx1 = UI_TB_BTN / 2, cx2;

    ui_tb_on = 0;
    ui_tb_hover = 0;
    if (!window || cursor_hidden || is_full_screen)     /* windowed mode only; hides with the cursor like the seek bar */
        return;
    SDL_GetWindowSize(window, &w, &h);
    if (w < 260 || h < UI_BAR_H * 3)
        return;
    ui_tb_on = 1;
    cx2 = w - UI_TB_BTN / 2;
    {                                           /* which button is the mouse over? */
        int mx, my;

        SDL_GetMouseState(&mx, &my);
        if (my >= UI_TB_EDGE && my < UI_TB_H)
            ui_tb_hover = mx < UI_TB_BTN ? 1 : mx >= w - UI_TB_BTN ? 2 : 0;
    }
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    row.x = 0;
    row.w = w;
    row.h = 1;
    for (y = 0; y < UI_TB_H + 14; y++) {        /* a dark glass strip that fades out along its lower edge */
        a = y < UI_TB_H ? 125 : 125 * (UI_TB_H + 14 - y) / 14;
        row.y = y;
        SDL_SetRenderDrawColor(renderer, 0, 0, 0, a);
        SDL_RenderFillRect(renderer, &row);
    }

    if (ui_tb_hover)                            /* a soft round highlight under the button the mouse is over */
        ui_fan(ui_tb_hover == 1 ? cx1 : cx2, cy, 16, 0, 6.28318531, 28, 255, 255, 255, 40);

    SDL_SetRenderDrawColor(renderer, 245, 245, 245, ui_tb_hover == 1 ? 255 : 200);      /* close: a cross */
    ui_tb_line(cx1 - 6, cy - 6, cx1 + 6, cy + 6, 2.0);
    ui_tb_line(cx1 - 6, cy + 6, cx1 + 6, cy - 6, 2.0);

    SDL_SetRenderDrawColor(renderer, 245, 245, 245, ui_tb_hover == 2 ? 255 : 200);
    for (sx = -1; sx <= 1; sx += 2)
        for (sy = -1; sy <= 1; sy += 2) {
            if (!is_full_screen) {              /* four corners pointing out: go fullscreen */
                ui_tb_line(cx2 + sx * 7, cy + sy * 7, cx2 + sx * 2, cy + sy * 7, 2.0);
                ui_tb_line(cx2 + sx * 7, cy + sy * 7, cx2 + sx * 7, cy + sy * 2, 2.0);
            } else {                            /* four corners pointing in: leave fullscreen */
                ui_tb_line(cx2 + sx * 2, cy + sy * 2, cx2 + sx * 7, cy + sy * 2, 2.0);
                ui_tb_line(cx2 + sx * 2, cy + sy * 2, cx2 + sx * 2, cy + sy * 7, 2.0);
            }
        }

    if (is && q_pos >= 0 && q_pos < q_count)    /* the name of what plays, in the middle */
        ui_q_name(q_pos, name, sizeof(name));
    else
        snprintf(name, sizeof(name), "ffplay-custom");
    ui_fit_text(name, 15, w - 2 * (UI_TB_BTN + 16));
    ui_label_c(w / 2, cy, name, 15, 235, 235, 235, 210);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);
}

/* Tells SDL which part of the window moves it: the strip between the two buttons. The window manager then does the move. */
static SDL_HitTestResult SDLCALL ui_hit_test(SDL_Window *win, const SDL_Point *area, void *data)
{
    int w, h;

    if (!ui_tb_on || is_full_screen)
        return SDL_HITTEST_NORMAL;
    SDL_GetWindowSize(win, &w, &h);
    if (area->y >= UI_TB_EDGE && area->y < UI_TB_H && area->x >= UI_TB_BTN && area->x < w - UI_TB_BTN)
        return SDL_HITTEST_DRAGGABLE;
    return SDL_HITTEST_NORMAL;
}

/* Clicks on the two buttons. Returns 1 if the click was used. */
static int ui_titlebar_mouse(VideoState *is, SDL_Event *ev)
{
    int w, h, x, y, hover = 0;

    if (!ui_tb_on || !window || (ev->type != SDL_MOUSEBUTTONDOWN && ev->type != SDL_MOUSEMOTION))
        return 0;
    SDL_GetWindowSize(window, &w, &h);
    x = ev->type == SDL_MOUSEMOTION ? ev->motion.x : ev->button.x;
    y = ev->type == SDL_MOUSEMOTION ? ev->motion.y : ev->button.y;
    if (y >= UI_TB_EDGE && y < UI_TB_H)
        hover = x < UI_TB_BTN ? 1 : x >= w - UI_TB_BTN ? 2 : 0;
    if (ev->type == SDL_MOUSEMOTION) {
        if (hover != ui_tb_hover && is)
            is->force_refresh = 1;
        ui_tb_hover = hover;
        return 0;                               /* the others still see the movement */
    }
    if (ev->button.button != SDL_BUTTON_LEFT || !hover)
        return 0;
    if (hover == 1) {
        SDL_Event quit;

        memset(&quit, 0, sizeof(quit));
        quit.type = SDL_QUIT;
        SDL_PushEvent(&quit);                   /* the same as closing the window any other way */
    } else {
        toggle_full_screen(is);
        if (is)
            is->force_refresh = 1;
    }
    return 1;
}

/* Mouse events for resizing the window by its edges and corners (moving it is the title bar's job).
   Returns 1 if the event was used here, 0 if normal handling should go on. */
static int ui_window_mouse(VideoState *is, SDL_Event *ev)
{
    int gx, gy;
    int edges;

    if (is_full_screen) {
        if (ui_win_mode) {
            ui_win_mode = 0;
            SDL_CaptureMouse(SDL_FALSE);
        }
        ui_set_cursor(0);
        return 0;
    }

    SDL_GetGlobalMouseState(&gx, &gy);

    if (ev->type == SDL_MOUSEBUTTONDOWN) {
        if (ev->button.button != SDL_BUTTON_LEFT)
            return 0;
        edges = ui_edges_at(ev->button.x, ev->button.y);
        if (!edges)
            return 0;                   /* only the edges and corners are ours; a click on the picture goes on */
        ui_win_mode = 2;
        ui_win_edges = edges;
        ui_gx0 = gx;
        ui_gy0 = gy;
        SDL_GetWindowPosition(window, &ui_wx0, &ui_wy0);
        SDL_GetWindowSize(window, &ui_ww0, &ui_wh0);
        SDL_CaptureMouse(SDL_TRUE);
        return 1;
    }
    if (ev->type == SDL_MOUSEMOTION) {
        if (ui_win_mode == 2) {
            ui_resize_to(is, gx, gy);
            ui_wake();
            return 1;
        }
        /* Not resizing: show a resize cursor over the edges */
        ui_set_cursor(ui_edges_at(ev->motion.x, ev->motion.y));
        return 0;
    }
    if (ev->type == SDL_MOUSEBUTTONUP && ev->button.button == SDL_BUTTON_LEFT && ui_win_mode) {
        ui_win_mode = 0;
        SDL_CaptureMouse(SDL_FALSE);
        return 1;
    }
    return 0;
}
''', "the title bar, the window manager drag, and edges-only resizing")

patch("        if (!window || !renderer || !renderer_info.num_texture_formats) {\n"
      "            av_log(NULL, AV_LOG_FATAL, \"Failed to create window or renderer: %s\", SDL_GetError());\n"
      "            do_exit(NULL);\n        }\n",
      "        if (!window || !renderer || !renderer_info.num_texture_formats) {\n"
      "            av_log(NULL, AV_LOG_FATAL, \"Failed to create window or renderer: %s\", SDL_GetError());\n"
      "            do_exit(NULL);\n        }\n"
      "        SDL_SetWindowHitTest(window, ui_hit_test, NULL);        /* the title bar moves the window: the window manager does it */\n",
      "tell SDL about the drag area")

patch("                if (ev.type != SDL_MOUSEBUTTONUP && ui_menu_mouse(NULL, &ev))\n                    break;\n"
      "                ui_window_mouse(NULL, &ev);     /* drag to move, edges to resize */\n",
      "                if (ev.type != SDL_MOUSEBUTTONUP && ui_titlebar_mouse(NULL, &ev))\n                    break;\n"
      "                if (ev.type != SDL_MOUSEBUTTONUP && ui_menu_mouse(NULL, &ev))\n                    break;\n"
      "                ui_window_mouse(NULL, &ev);     /* edges to resize */\n",
      "the title bar buttons on the idle screen")

patch("            if (ui_menu_mouse(cur_stream, &event) || ui_window_mouse(cur_stream, &event) ||\n"
      "                ui_mouse(cur_stream, &event))\n                break;\n            if (exit_on_mousedown) {",
      "            if (ui_titlebar_mouse(cur_stream, &event) || ui_menu_mouse(cur_stream, &event) ||\n"
      "                ui_window_mouse(cur_stream, &event) || ui_mouse(cur_stream, &event))\n                break;\n            if (exit_on_mousedown) {",
      "the title bar buttons: clicks")

patch("                (ui_menu_mouse(cur_stream, &event) || ui_window_mouse(cur_stream, &event) ||\n"
      "                 ui_mouse(cur_stream, &event)))\n                break;\n            if (cursor_hidden) {",
      "                (ui_titlebar_mouse(cur_stream, &event) || ui_menu_mouse(cur_stream, &event) ||\n"
      "                 ui_window_mouse(cur_stream, &event) || ui_mouse(cur_stream, &event)))\n                break;\n            if (cursor_hidden) {",
      "the title bar buttons: movement")

# ============================================================ Reworked Esc key behaviour

patch("                ev.key.keysym.sym = ui_key_translate(ev.key.keysym.sym);   /* the keys chosen in settings.conf */\n"
      "                if (ui_prefs_open && ev.key.keysym.sym == SDLK_ESCAPE)\n"
      "                    ui_prefs_open = 0;\n"
      "                else if (ev.key.keysym.sym == SDLK_q || ev.key.keysym.sym == SDLK_ESCAPE)\n"
      "                    do_exit(NULL);\n",
      "                ev.key.keysym.sym = ui_key_translate(ev.key.keysym.sym);   /* the keys chosen in settings.conf */\n"
      "                if (ev.key.keysym.sym == SDLK_ESCAPE) {\n"
      "                    if (ui_prefs_open || ui_q_open || ui_info_open || ui_open_open || ui_ctx_open) {\n"
      "                        ui_prefs_open = 0;\n"
      "                        ui_q_open = 0;\n"
      "                        ui_info_open = 0;\n"
      "                        ui_open_open = 0;\n"
      "                        ui_ctx_open = 0;\n"
      "                    } else if (is_full_screen) {\n"
      "                        toggle_full_screen(NULL);\n"
      "                    }\n"
      "                } else if (ev.key.keysym.sym == SDLK_q)\n"
      "                    do_exit(NULL);\n",
      "Reworked Esc key on the idle screen")

patch("            event.key.keysym.sym = ui_key_translate(event.key.keysym.sym);   /* the keys chosen in settings.conf */\n"
      "            if ((ui_menu_open || ui_prefs_open) && event.key.keysym.sym == SDLK_ESCAPE) {\n"
      "                ui_menu_open = 0;\n"
      "                ui_prefs_open = 0;\n"
      "                cur_stream->force_refresh = 1;\n"
      "                break;\n"
      "            }\n"
      "            if (exit_on_keydown || event.key.keysym.sym == SDLK_ESCAPE || event.key.keysym.sym == SDLK_q) {\n"
      "                do_exit(cur_stream);\n"
      "                break;\n"
      "            }\n",
      "            event.key.keysym.sym = ui_key_translate(event.key.keysym.sym);   /* the keys chosen in settings.conf */\n"
      "            if (event.key.keysym.sym == SDLK_ESCAPE) {\n"
      "                if (ui_menu_open || ui_prefs_open || ui_q_open || ui_info_open || ui_open_open || ui_ctx_open) {\n"
      "                    ui_menu_open = 0;\n"
      "                    ui_prefs_open = 0;\n"
      "                    ui_q_open = 0;\n"
      "                    ui_info_open = 0;\n"
      "                    ui_open_open = 0;\n"
      "                    ui_ctx_open = 0;\n"
      "                    cur_stream->force_refresh = 1;\n"
      "                } else if (is_full_screen) {\n"
      "                    toggle_full_screen(cur_stream);\n"
      "                    cur_stream->force_refresh = 1;\n"
      "                }\n"
      "                break;\n"
      "            }\n"
      "            if (exit_on_keydown || event.key.keysym.sym == SDLK_q) {\n"
      "                do_exit(cur_stream);\n"
      "                break;\n"
      "            }\n",
      "Reworked Esc key during playback")

# ============================================================ the dot before the title of the item that plays

replace_between("                if (ui_flow_vmode && i == q_pos) {      /* a small dot in the bar color marks the video that is playing */\n",
                "                    ui_pill(&dot);\n                }\n",
                "", "no dot on the corner of the picture")

patch("                    ui_flow_title(name, 15, vx0 + vw / 2, &tile, tl[e], al * 55 / 100);\n                }\n",
      "                    ui_flow_title(name, 15, vx0 + vw / 2, &tile, tl[e], al * 55 / 100);\n"
      "                    if (i == q_pos)             /* the dot of the item that plays, before its title */\n"
      "                        ui_flow_title_dot(name, 15, vx0 + vw / 2, &tile, tl[e], al, 6);\n"
      "                }\n",
      "the dot before a small title")

patch("    ui_label_c(W / 2, cy + chh / 2 + 40, name, 22, 255, 255, 255, nal);\n",
      "    ui_label_c(W / 2, cy + chh / 2 + 40, name, 22, 255, 255, 255, nal);\n"
      "    if (ci == q_pos) {                          /* the dot of the item that plays, before its title */\n"
      "        SDL_Rect pdot;\n\n"
      "        pdot.w = 8;\n"
      "        pdot.h = 8;\n"
      "        pdot.x = W / 2 - ui_text_width(name, 22) / 2 - 20;\n"
      "        pdot.y = cy + chh / 2 + 40 - 4;\n"
      "        SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),\n"
      "                               av_clip(cfg_bar_b + 40, 0, 255), (int)(235 * nal / 255));\n"
      "        ui_pill(&pdot);\n"
      "    }\n",
      "the dot before the big title")

patch("/* ----- the shape of the whole track, read in the background -----\n",
      r'''/* The dot before the title of the item that plays: the same small bar-color dot that marks the menu row under the mouse.
   It sits just before the text that ui_flow_title draws, on the same line, tilted with the card. */
static void ui_flow_title_dot(const char *s, int px, int cx, const SDL_Rect *t, double tilt, int al, int size)
{
    double kin = 1.0 - 0.16 * fabs(tilt), x = cx - ui_text_width(s, px) / 2.0 - size - 6;
    double uc = av_clipd((x - t->x) / (double)FFMAX(t->w, 1), 0.0, 1.0);
    double f = tilt < 0 ? 1.0 - (1.0 - kin) * uc : tilt > 0 ? kin + (1.0 - kin) * uc : 1.0;
    SDL_Rect dot;

    dot.w = FFMAX((int)(size * f), 3);
    dot.h = dot.w;
    dot.x = (int)x;
    dot.y = (int)(t->y + t->h / 2.0 + t->h * f / 2.0 + 18.0 * f) - dot.h / 2;
    SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                           av_clip(cfg_bar_b + 40, 0, 255), al * 235 / 255);
    ui_pill(&dot);
}

/* ----- the shape of the whole track, read in the background -----
''', "the dot helper for small titles")

open(path, "w").write(src)
print("Patched", path)
