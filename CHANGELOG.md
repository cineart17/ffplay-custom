# Changelog

Every update to ffplay-custom, newest first. The numbers match the `patch_queue/patch_queue_vN.py` scripts.

## Repository (after v20)
- `scripts/build.sh` links SDL2_ttf (it was missing from the link line) and builds in `~/ffplay-custom-build`, so it cannot overwrite a working tree in `~/build`.
- `REQUIREMENTS.md` and `scripts/install-deps.sh` list and install everything the player needs.

## v20
- A "modified by" notice under the license header of `ffplay.c`.

## v19
- The waveform bars are dimmer again (white, alpha 90) and stretch across the whole window, above the volume bar too.

## v18
- The waveform bars are one color, with no "played" part in the bar color.
- The disc label is a round, cropped piece of the cover again.

## v17
- The waveform bars are always shown, even when the seek bar hides.
- The waveform bars no longer get flat tops (soft loudness curve, more room to grow).

## v16
- No black dot in the middle of the disc.
- No black shadows under menus, panels, floating text, the volume number or the covers. One switch,
  `ui_shadows_on` in `ffplay.c`, brings them back.

## v15
- Each side cover turns by its own amount, and its width and title follow its angle.
- Shadows follow the cover's own shape. The waveform bars move with the music again.

## v14
- Titles under side covers tilt with their covers. Turned covers are slightly narrower.
- The disc turns slowly. The bars above the seek line show the shape of the whole track.

## v13
- The disc label is large and shows the cover. Side covers tilt. The file icon is a picture, so it tilts too.

## v12
- Rounded equaliser bars. The disc takes its color from the cover and has a solid look with a cover label.

## v11
- More solid frosted file icon. Covers overlap again but are cut where a nearer cover is in front.

## v10
- Rounded covers, frosted file icon, arrowhead bars on the buttons, quieter drag marker.
- Faster scrolling at the window edge while dragging. The queue menu list glides when it scrolls.

## v9
- Square pictures with frosted bars for video thumbnails. Covers with small titles.
- Click, drag and drop in the cover flow.

## v8
- The cover-flow queue. Buttons on the bar row, sideways swipes, repeat handling.

## v7
- A bubble party backdrop for audio without a cover.

## v6
- The queue panel rows fade in one after another.

## v5
- Opening a file while something plays adds it to the queue. Glass menus tinted with the bar color.

## v4
- Cleaner menus without highlight boxes, a sectioned chapter bar, a cover backdrop and desktop media controls (MPRIS).

## Earlier
- The first versions, before the patch queue numbering reached v4.
