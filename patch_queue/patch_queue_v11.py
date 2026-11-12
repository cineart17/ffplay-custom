#!/usr/bin/env python3
# Update 11 for ffplay-custom (on top of patch_queue_v10.py).
#   * The frosted file icon is more solid (still translucent), and the odd rectangle along its top is gone.
#   * The spinning disc is only seen where it sticks out to the right of the cover, never through the cover.
#   * The covers overlap again, like in v8, because you liked that. But a cover is now cut off where a nearer
#     one is in front of it, so you never see an album picture through another one. Titles are centered on the part
#     of each cover that shows, and a click on a hidden part goes to the cover in front.
# Run from inside ~/build/ffmpeg-6.1.1, after patch_queue_v10.py.
# Writes the file only if every spot matches exactly once.

import sys

path = "fftools/ffplay.c"
src = open(path).read()

if "ui_flow_rects" in src:
    print("Already applied. Nothing written.")
    sys.exit(1)
if "ui_flow_off" not in src:
    print("Apply patch_queue_v10.py first. Nothing written.")
    sys.exit(1)


def patch(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    src = src.replace(old, new)
    print("ok:", label)


# ============================================================ the file icon

patch("""    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 44 * al / 255);                      /* frosted glass: a light haze, */
    ui_rr_fill(t, rad);
    SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 58 * al / 255);    /* tinted with your bar color, */
    ui_rr_fill(t, rad);
    r.x = t->x + t->w / 14;                                                              /* with a soft light along the top */
    r.y = t->y + 2;
    r.w = t->w - t->w / 7;
    r.h = t->h / 3;
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 16 * al / 255);
    ui_rr_fill(&r, rad);
""", """    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 110 * al / 255);                     /* frosted glass: a light haze, */
    ui_rr_fill(t, rad);
    SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 110 * al / 255);   /* tinted with your bar color */
    ui_rr_fill(t, rad);
""", "a more solid icon, no rectangle")

# ============================================================ the places of the covers: overlapping again

patch("""static double ui_flow_off(double B, double d)
{
    static const double pos[8] = { 0.0, 0.85, 1.47, 2.03, 2.56, 3.09, 3.62, 4.15 };
    double ad = fabs(d), o;
    int k = av_clip((int)ad, 0, 6);

    o = pos[k] + (pos[k + 1] - pos[k]) * FFMIN(ad - k, 1.0);
    return (d < 0 ? -o : o) * B + (d > 0 ? B * 0.30 * FFMIN(d, 1.0) : 0.0);     /* the right side leaves room for the disc */
}
""", """static double ui_flow_off(double B, double d)
{
    double dc = av_clipd(d, -1.0, 1.0);

    return B * (0.86 * dc + 0.42 * (d - dc)) + (d > 0 ? B * 0.30 * FFMIN(d, 1.0) : 0.0);    /* the right side leaves room for the disc */
}
""", "the places of the covers, overlapping again")

patch("""/* How far from the middle (in widths of the middle cover) the cover at distance d sits. The covers shrink with
   distance, so each place is worked out from the one before it, with a small gap, and nothing overlaps. */
""", """/* How far from the middle the cover at distance d sits (in widths of the middle cover). Far covers overlap a little. */
""", "comment")

# ============================================================ drawing: each cover is cut where a nearer one is in front

patch("""    for (pass = 4; pass >= 0; pass--) {
        for (i = ci - 5; i <= ci + 5; i++) {
            if (i < 0 || i >= q_count || (int)(fabs(i - ui_flow_pos) + 0.5) != pass)
                continue;
            d = i - ui_flow_pos;
            ad = fabs(d);
            sc = 1.0 - 0.40 * FFMIN(ad, 1.0) - 0.06 * FFMAX(FFMIN(ad, 3.0) - 1.0, 0.0);
            off = ui_flow_off(B, d);
            s = B * sc;
            tile.x = cx + (int)(off - s / 2);
            tile.y = cy - (int)(s / 2);
            tile.w = (int)s;
            tile.h = (int)s;
            al = (int)(255 * av_clipd(1.15 - 0.30 * ad, 0.15, 1.0));
            md = (int)(255 * av_clipd(1.0 - 0.20 * FFMIN(ad, 2.0), 0.4, 1.0));

            if (ad < 1.5)
                ui_shadow(&tile, tile.w / 11);
            if (i == q_pos)                     /* the disc sits behind the cover of the item playing */
                ui_flow_disc(tile.x + s * 0.78, cy, s * 0.47, ui_flow_ang, al);
            ui_flow_tile(i, &tile, (ui_flow_dragging && i == ui_flow_press) ? al / 3 : al, md);
            if (i != ci) {                      /* a small, faded title under every cover but the middle one */
                ui_q_name(i, name, 300);
                ui_fit_text(name, 15, tile.w);
                ui_label_c(tile.x + tile.w / 2, tile.y + tile.h + 18, name, 15, 235, 235, 235, al * 55 / 100);
            }
            if (ui_flow_n < 16) {
                ui_flow_hit[ui_flow_n].r = tile;
                ui_flow_hit[ui_flow_n].idx = i;
                ui_flow_n++;
            }
        }
    }
""", """    {
        SDL_Rect ui_flow_rects[11], cut, dcl;
        int ok[11];

        for (i = ci - 5; i <= ci + 5; i++) {    /* first, where every cover sits */
            int e = i - (ci - 5);

            ok[e] = i >= 0 && i < q_count;
            if (!ok[e])
                continue;
            d = i - ui_flow_pos;
            ad = fabs(d);
            sc = 1.0 - 0.40 * FFMIN(ad, 1.0) - 0.06 * FFMAX(FFMIN(ad, 3.0) - 1.0, 0.0);
            off = ui_flow_off(B, d);
            s = B * sc;
            ui_flow_rects[e].x = cx + (int)(off - s / 2);
            ui_flow_rects[e].y = cy - (int)(s / 2);
            ui_flow_rects[e].w = (int)s;
            ui_flow_rects[e].h = (int)s;
        }
        for (pass = 4; pass >= 0; pass--) {     /* then draw them, the far ones first */
            for (i = ci - 5; i <= ci + 5; i++) {
                int e = i - (ci - 5), vx0, vx1, vw;

                if (!ok[e] || (int)(fabs(i - ui_flow_pos) + 0.5) != pass)
                    continue;
                d = i - ui_flow_pos;
                ad = fabs(d);
                tile = ui_flow_rects[e];
                s = tile.w;
                al = (int)(255 * av_clipd(1.6 - 0.35 * ad, 0.12, 1.0));
                md = (int)(255 * av_clipd(1.0 - 0.20 * FFMIN(ad, 2.0), 0.4, 1.0));

                vx0 = tile.x;                   /* the part of this cover that is not covered by a nearer one */
                vx1 = tile.x + tile.w;
                cut.x = 0;
                cut.y = 0;
                cut.w = W;
                cut.h = H;
                if (d < -0.5 && e + 1 < 11 && ok[e + 1]) {
                    vx1 = FFMIN(vx1, ui_flow_rects[e + 1].x);
                    cut.w = FFMAX(vx1, 0);
                } else if (d > 0.5 && e > 0 && ok[e - 1]) {
                    vx0 = FFMAX(vx0, ui_flow_rects[e - 1].x + ui_flow_rects[e - 1].w);
                    cut.x = av_clip(vx0, 0, W);
                    cut.w = W - cut.x;
                }
                vw = vx1 - vx0;
                if (vw <= 0 || cut.w <= 0)
                    continue;                   /* hidden completely */
                SDL_RenderSetClipRect(renderer, &cut);
                if (ad < 1.5)
                    ui_shadow(&tile, tile.w / 11);
                if (i == q_pos) {               /* the disc only shows where it sticks out to the right of the cover */
                    dcl.x = FFMAX(tile.x + tile.w, cut.x);
                    dcl.y = 0;
                    dcl.w = FFMAX(cut.x + cut.w - dcl.x, 0);
                    dcl.h = H;
                    if (dcl.w > 0) {
                        SDL_RenderSetClipRect(renderer, &dcl);
                        ui_flow_disc(tile.x + s * 0.78, cy, s * 0.47, ui_flow_ang, al);
                        SDL_RenderSetClipRect(renderer, &cut);
                    }
                }
                ui_flow_tile(i, &tile, (ui_flow_dragging && i == ui_flow_press) ? al / 3 : al, md);
                if (i != ci && vw >= 48) {      /* a small, faded title under the part that shows */
                    ui_q_name(i, name, 300);
                    ui_fit_text(name, 15, vw);
                    ui_label_c(vx0 + vw / 2, tile.y + tile.h + 18, name, 15, 235, 235, 235, al * 55 / 100);
                }
                SDL_RenderSetClipRect(renderer, NULL);
                if (ui_flow_n < 16) {           /* a click on a hidden part goes to the cover in front */
                    ui_flow_hit[ui_flow_n].r.x = vx0;
                    ui_flow_hit[ui_flow_n].r.y = tile.y;
                    ui_flow_hit[ui_flow_n].r.w = vw;
                    ui_flow_hit[ui_flow_n].r.h = tile.h;
                    ui_flow_hit[ui_flow_n].idx = i;
                    ui_flow_n++;
                }
            }
        }
    }
""", "covers cut where a nearer one is in front")

open(path, "w").write(src)
print("Patched", path)
