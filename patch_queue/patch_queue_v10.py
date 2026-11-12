#!/usr/bin/env python3
# Update 10 for ffplay-custom (on top of patch_queue_v9.py).
#   * Covers have rounded corners. The file icon (no picture) is a frosted glass tile instead of a plain white one,
#     and the bars around a video thumbnail are frosted in your bar color (the color is picked up when the picture
#     loads, so a new bar color shows on covers loaded after you change it).
#   * The previous and next arrowheads get a small vertical bar at their end, like in your reference.
#   * The landing marker while dragging a cover is thinner and much fainter.
#   * Covers in the row no longer overlap each other.
#   * Dragging a cover to the window's edge speeds up the closer the mouse gets to the very edge.
#   * The queue menu's list now glides when it scrolls (wheel, or dragging an item to the top or bottom) instead of
#     jumping a whole row at a time.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v9.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_flow_off" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_flow_tile" not in src:
    print("Apply patch_queue_v9.py first. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


# ============================================================ rounded pictures, frosted bars

patch("                    sq[(y * 256 + x) * 4 + k] = (uint8_t)(k < 3 ? FFMIN(v * 0.8 + 40.0, 255.0) : 255.0);\n",
      "                    {\n"
      "                        double bc = k == 0 ? cfg_bar_r : k == 1 ? cfg_bar_g : cfg_bar_b;     /* frosted, in your bar color */\n\n"
      "                        sq[(y * 256 + x) * 4 + k] = (uint8_t)(k < 3 ? FFMIN((v * 0.8 + 40.0) * 0.6 + bc * 0.4, 255.0) : 255.0);\n"
      "                    }\n",
      "frosted bars in the bar color")

patch("        *ow = 256;\n        *oh = 256;\n    }\nend:\n",
      r'''        *ow = 256;
        *oh = 256;
    }
    if (*ow == *oh && *ow >= 64) {      /* round the corners: the transparent corners are baked into the picture */
        int sz = *ow, rr = *ow / 11, k;

        for (y = 0; y < rr; y++)
            for (x = 0; x < rr; x++) {
                double dxx = rr - x - 0.5, dyy = rr - y - 0.5;
                double cov = av_clipd(rr - sqrt(dxx * dxx + dyy * dyy) + 0.5, 0.0, 1.0);
                int at[4] = { y * sz + x, y * sz + sz - 1 - x, (sz - 1 - y) * sz + x, (sz - 1 - y) * sz + sz - 1 - x };

                for (k = 0; k < 4; k++)
                    out[at[k] * 4 + 3] = (uint8_t)(out[at[k] * 4 + 3] * cov);
            }
    }
end:
''', "rounded corners")

patch("    int cr = 233 * md / 255, cg = 104 * md / 255, cb = 36 * md / 255;\n",
      "    int cr = 233 * md / 255, cg = 104 * md / 255, cb = 36 * md / 255, rad = t->w / 11;\n",
      "icon variables")

patch("    SDL_SetRenderDrawColor(renderer, 238 * md / 255, 238 * md / 255, 240 * md / 255, al);\n    ui_rr_fill(t, 8);\n",
      "    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 44 * al / 255);                      /* frosted glass: a light haze, */\n"
      "    ui_rr_fill(t, rad);\n"
      "    SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 58 * al / 255);    /* tinted with your bar color, */\n"
      "    ui_rr_fill(t, rad);\n"
      "    r.x = t->x + t->w / 14;                                                              /* with a soft light along the top */\n"
      "    r.y = t->y + 2;\n    r.w = t->w - t->w / 7;\n    r.h = t->h / 3;\n"
      "    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 16 * al / 255);\n"
      "    ui_rr_fill(&r, rad);\n",
      "frosted file icon")

patch("""    tex = ui_cov_get(q_items[idx], &cw, &ch);
    if (!tex) {
        ui_flow_note(tile, al, md);
        return;
    }
    SDL_SetRenderDrawColor(renderer, 24, 24, 28, al * 220 / 255);
    ui_rr_fill(tile, 8);
    SDL_SetTextureAlphaMod(tex, (Uint8)al);
    SDL_SetTextureColorMod(tex, (Uint8)md, (Uint8)md, (Uint8)md);
    SDL_RenderCopy(renderer, tex, NULL, tile);
    if (cw > 0 && ch > 0 && cw != ch) {
        SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 80 * al / 255);
        hz = *tile;
        if (cw > ch) {
            bw = (tile->h - tile->h * ch / cw) / 2;
            hz.h = bw;
            SDL_RenderFillRect(renderer, &hz);
            hz.y = tile->y + tile->h - bw;
            SDL_RenderFillRect(renderer, &hz);
        } else {
            bw = (tile->w - tile->w * cw / ch) / 2;
            hz.w = bw;
            SDL_RenderFillRect(renderer, &hz);
            hz.x = tile->x + tile->w - bw;
            SDL_RenderFillRect(renderer, &hz);
        }
    }
}
""", """    tex = ui_cov_get(q_items[idx], &cw, &ch);
    if (!tex) {
        ui_flow_note(tile, al, md);
        return;
    }
    SDL_SetTextureAlphaMod(tex, (Uint8)al);
    SDL_SetTextureColorMod(tex, (Uint8)md, (Uint8)md, (Uint8)md);
    SDL_RenderCopy(renderer, tex, NULL, tile);      /* the corners of the picture are already rounded */
}
""", "tile without the old overlay")

patch("    SDL_Texture *tex;\n    SDL_Rect hz;\n    int cw = 0, ch = 0, bw;\n",
      "    SDL_Texture *tex;\n    int cw = 0, ch = 0;\n",
      "tile variables")

patch("                ui_shadow(&tile, 10);\n", "                ui_shadow(&tile, tile.w / 11);\n", "round shadows")
patch("        ui_shadow(&g, 10);\n", "        ui_shadow(&g, g.w / 11);\n", "round shadow of the dragged cover")

# ============================================================ no overlap

patch("/* The icon for a file with no picture, like the file manager's: a light page with an orange music note */\n",
      r'''/* How far from the middle (in widths of the middle cover) the cover at distance d sits. The covers shrink with
   distance, so each place is worked out from the one before it, with a small gap, and nothing overlaps. */
static double ui_flow_off(double B, double d)
{
    static const double pos[8] = { 0.0, 0.85, 1.47, 2.03, 2.56, 3.09, 3.62, 4.15 };
    double ad = fabs(d), o;
    int k = av_clip((int)ad, 0, 6);

    o = pos[k] + (pos[k + 1] - pos[k]) * FFMIN(ad - k, 1.0);
    return (d < 0 ? -o : o) * B + (d > 0 ? B * 0.30 * FFMIN(d, 1.0) : 0.0);     /* the right side leaves room for the disc */
}

/* The icon for a file with no picture, like the file manager's: a light page with an orange music note */
''', "cover places without overlap")

patch("            dc = av_clipd(d, -1.0, 1.0);\n", "", "drop the old spacing: dc")
patch("            off = B * (0.86 * dc + 0.42 * (d - dc)) + (d > 0 ? B * 0.30 * FFMIN(d, 1.0) : 0.0);\n",
      "            off = ui_flow_off(B, d);\n", "use the new spacing")
patch("    double dt, B, d, ad, dc, sc, off,", "    double dt, B, d, ad, sc, off,", "drop the old spacing: declaration")

# ============================================================ buttons, marker, edge speed

patch("    ui_tri(34 - 5, cy, 10, 12, -1);             /* one arrowhead each, not two */\n    ui_tri(ex + 16 - 5, cy, 10, 12, 1);\n",
      r'''    {                                           /* one arrowhead each, with a small bar at its end */
        SDL_Rect stop;

        stop.w = 2;
        stop.h = 12;
        stop.y = cy - 6;
        stop.x = 34 - 9;
        SDL_RenderFillRect(renderer, &stop);    /* previous: the bar, then the arrowhead */
        ui_tri(34 - 5, cy, 9, 12, -1);
        ui_tri(ex + 16 - 4, cy, 9, 12, 1);      /* next: the arrowhead, then the bar */
        stop.x = ex + 16 + 6;
        SDL_RenderFillRect(renderer, &stop);
    }
''', "bars on the arrowheads")

patch("            bar.x = (before ? r->x : r->x + r->w) - 3;\n            bar.y = r->y;\n            bar.w = 6;\n            bar.h = r->h;\n            SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 235);\n            ui_rr_fill(&bar, 3);\n",
      "            bar.x = (before ? r->x : r->x + r->w) - 2;\n            bar.y = r->y + r->h / 8;\n            bar.w = 4;\n            bar.h = r->h * 3 / 4;\n"
      "            SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 110);       /* a quiet marker */\n"
      "            ui_rr_fill(&bar, 2);\n",
      "a quieter landing marker")

patch("""        if (now - ui_flow_edge_at > 350000 && (ui_flow_mx < W / 12 || ui_flow_mx > W - W / 12)) {
            ui_flow_target = av_clip(ui_flow_target + (ui_flow_mx < W / 2 ? -1 : 1), 0, q_count - 1);
            ui_flow_edge_at = now;              /* at an edge: the row keeps moving that way */
        }
""", """        {
            int zone = W / 8, dist = FFMIN(ui_flow_mx, W - 1 - ui_flow_mx);    /* how far from the nearest edge */

            if (dist < zone) {                  /* in the edge zone: the closer to the very edge, the faster the row moves */
                double depth = av_clipd((zone - dist) / (double)zone, 0.0, 1.0);
                int64_t gap = 420000 - (int64_t)(360000 * depth * depth);     /* 0.42 s per step at first, 0.06 s at the edge */

                if (now - ui_flow_edge_at > gap) {
                    ui_flow_target = av_clip(ui_flow_target + (ui_flow_mx < W / 2 ? -1 : 1) * (depth > 0.9 ? 2 : 1),
                                             0, q_count - 1);
                    ui_flow_edge_at = now;
                }
            }
        }
""", "faster at the very edge")

# ============================================================ the queue menu glides

patch("static int ui_q_scroll = 0;     /* first queue item shown in the panel */\n",
      "static int ui_q_scroll = 0;     /* first queue item shown in the panel */\n"
      "static double ui_q_off = 0.0;   /* rows the list is still sliding after a scroll, so it glides instead of jumping */\n"
      "static int ui_q_last_scroll = -1;\n"
      "static int64_t ui_q_off_t = 0;\n",
      "glide state")

patch("    SDL_Rect p = ui_q_rect(ww, wh), sep, dot, chip[6];\n",
      "    SDL_Rect p = ui_q_rect(ww, wh), sep, dot, chip[6], clip;\n",
      "glide: clip rectangle")

patch("        ui_q_scroll = q_pos - 2;\n        ui_q_reveal = 0;\n    }\n    ui_q_scroll = av_clip(ui_q_scroll, 0, FFMAX(q_count - vis, 0));\n",
      r'''        ui_q_scroll = q_pos - 2;
        ui_q_reveal = 0;
        ui_q_last_scroll = -1;          /* just opened: no gliding, show it in place */
    }
    ui_q_scroll = av_clip(ui_q_scroll, 0, FFMAX(q_count - vis, 0));
    {                                   /* the rows scrolled since the last drawing slide into place */
        double ddt = ui_q_off_t ? av_clipd((now - ui_q_off_t) / 1000000.0, 0.0, 0.1) : 0.0;

        if (ui_q_last_scroll < 0)
            ui_q_off = 0.0;
        else
            ui_q_off += ui_q_scroll - ui_q_last_scroll;
        ui_q_last_scroll = ui_q_scroll;
        ui_q_off = av_clipd(ui_q_off, -3.0, 3.0) * exp(-ddt * 14.0);
        if (fabs(ui_q_off) < 0.01)
            ui_q_off = 0.0;
        ui_q_off_t = now;
    }
''', "glide: how far the rows still have to slide")

patch("    for (i = 0; i < vis && ui_q_scroll + i < q_count; i++) {\n        item = ui_q_slot_item(ui_q_scroll + i, drop);\n        cy = top + i * UI_Q_ROW + UI_Q_ROW / 2;\n        ui_fade = ui_cascade(i + 1);\n",
      r'''    clip.x = p.x;
    clip.y = top;
    clip.w = p.w;
    clip.h = vis * UI_Q_ROW;
    SDL_RenderSetClipRect(renderer, &clip);     /* rows slide in and out at the list's edges */
    for (i = -1; i <= vis && ui_q_scroll + i < q_count; i++) {
        if (ui_q_scroll + i < 0)
            continue;
        item = ui_q_slot_item(ui_q_scroll + i, drop);
        cy = top + (int)((i + ui_q_off) * UI_Q_ROW) + UI_Q_ROW / 2;
        ui_fade = ui_cascade(FFMAX(i, 0) + 1);
''', "glide: draw the rows where they are sliding")

patch("    /* under the list */\n    fy = top + vis * UI_Q_ROW;\n",
      "    SDL_RenderSetClipRect(renderer, NULL);\n\n    /* under the list */\n    fy = top + vis * UI_Q_ROW;\n",
      "glide: end the clip")

patch("    if (ui_flow_wants_redraw(is))\n        is->force_refresh = 1;                  /* the disc turns, the bars move, the covers glide */\n",
      "    if (ui_flow_wants_redraw(is))\n        is->force_refresh = 1;                  /* the disc turns, the bars move, the covers glide */\n"
      "    if (ui_q_open && ui_q_off != 0.0)\n        is->force_refresh = 1;                  /* the queue list is still gliding */\n",
      "keep redrawing while the list glides")

open(path, "w").write(src)
print("Patched", path)
