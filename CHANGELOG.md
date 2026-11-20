# Changelog

Every update to ffplay-custom, newest first. The numbers match the `patch_queue/patch_queue_vN.py` scripts.

## Repository (after v22)
- `assets/logo.png`: the ffplay-custom logo, so a fresh setup does not end up with the plain badge.
- `scripts/install.sh` installs the player, the media-controls helper, the app-menu launcher and the logo.

## v38
- New preference, Scroll action, with Seek, Volume and Navigation. It decides what the mouse wheel and a two finger swipe up or down do. Navigation: a swipe up opens the tiled queue view; inside it, up and down move between rows or sections and sideways moves along them. On the volume bar the scroll always changes the volume and on the seek bar it always seeks. Saved as scroll_action in settings.conf (the old mouse_wheel line is ignored).
- The swipe up now opens the tiled view: v37 guessed touchpad or wheel from fractional scroll values, which this session does not send.
- Searching: In this queue, In Music and In Videos each move on their own, the one the mouse is resting on.
- Bigger tiles in the rows and in the search sections.

## v37
- The miniplayer remembers where you left it (position and width), also between runs (~/.config/ffplay-custom/miniplayer.conf). A spot that is off every screen falls back to the bottom right corner.
- Full screen from the miniplayer: the window grows out of the miniplayer in one eased motion instead of jumping, and the miniplayer's always on top and show on all workspaces are switched off. Esc from that full screen still goes back to the window the miniplayer was entered from.
- Seeking: the blur came from small preview pictures stretched over the window. They are 320 x 180 now, they are only used when the jump is bigger than the gap between two previews, and the seek bar tooltip keeps its old size.
- New tiled queue view with flat tiles: two rows (three in a tall window), the lower row continues the upper one and swiping any row moves them all. Opened with a two finger swipe up, Tab or L. The entry animation is kept.
- Search in the tiled view: just type. The closest match springs into focus, the others follow to its right, and the letters that match are drawn in the seek bar color. Sections: In this queue, In Music, In Videos (set music_folder and video_folder in settings.conf, or the system folders are used). Letter shortcuts are off while the view is open. Esc clears the search, Esc again closes the view.
- Tiles can be held and dragged to a new place in the queue; in the queue panel a row can be dragged by its name, not only by the dots.
- Many tile titles no longer overflow the text cache.

## v36
- The seek and volume bar is the old flat strip again: a short dark frosted bar, edge to edge and flush with the bottom of the window.
- Preferences: the choice under the mouse rises a little and gets brighter (no pill any more).
- Queue panel: the Crossfade and Sleep timer rows nudge their names and their choices rise under the mouse, like the preference rows.
- Video queue tiles were convex like the outside of a cylinder (replaced in v37 by flat tiles).
- Line icons in the right-click menu, Open, the queue item menu, the Crossfade and Sleep timer rows and every preference row.

## v35
- The miniplayer returns to exactly the state it was entered from, including a window that filled the screen and the always-on-top setting.
- Esc in complete full screen goes to the conventional window that fills the screen; Esc in the miniplayer leaves it.
- F or a double tap in the miniplayer goes to complete full screen.
- The soft return from out of sight has a switch (UI_WBLUR_RETURN), the smoked glass veil is a little stronger, and the log file starts each run with the session type, video driver, renderer and SDL version.

## v34
- The picture follows the real window size: after a size change that the player missed, the picture no longer stays small in a corner.
- Picture in picture: a title bar button makes the window a small miniplayer on top, in the video's shape at the bottom right; it can be resized and moved, the queue keeps its size, and the button again gives the window back.
- The waveform shows the played part in the bar color, the rest dim, with the time played and the time left beside it.
- Generic liquid glass for the menus, preferences and panels: the blurred picture behind a smoked veil, no rim, white text.

## v33
- Background stutter: the player never waits for the screen (vsync is always off) and draws at most about 60 pictures a second, so a window the window manager does not show can no longer hold it back. The screen-sleep switch changes only after 1.5 s. The blur while another window has the focus is off. The lines that start with "ffplay-custom:" are also written to ~/.cache/ffplay-custom/log.txt.
- Liquid glass without a lens: no bent edge, no highlight, no bright rim, an even haze, a lighter blur and a sharper edge.
- Preferences: the name nudges and the choices slide in one after another, with a soft pill under the one the mouse is on.
- The queue view's waveform is one smooth shape, there at once; the track that plays is read before the view opens.
- Tiles that are alive: they glide in, rise under the mouse, and the playing song breathes.
- Seeking: the nearest preview is shown full size while a seek key is held or the bar is dragged, until the real picture arrives.
- The stock keys 0, 9, *, /, s, a, v, c, t, w, < and > are off.

## v32
- Key O (always on top) is gone.
- The picture softens a little while another window has the focus and sharpens when the mouse or focus comes back; after a window was out of sight it returns soft and clears, so the redraw is not seen.
- Liquid glass: lens-bent edges, highlight and bright rim on the bars pill, menus and panels.
- The seek and volume row sits in the middle of its dark glass pill.
- Smoother held-key and drag seeking.
- A double tap in the picture goes to complete full screen, then to the window filling the screen under the panel (corners can be dragged from there), then back.
- In Preferences the name and the choices of the hovered row form one centred row with equal gaps, and glide in and out.

## v31
- Background stutter: when the window manager holds a frame back (another workspace, the Multitasking view), the player stops drawing and tests once in 8 s whether the window is back; the pictures and sound go on in sync meanwhile.
- No seek previews are made while the window is out of sight.
- The slow-moment log only names steps over 150 ms.

## v30
- A "Back to playing" hint shows when the queue view is away from the playing item.
- Hover previews carry on from tile to tile without a wait.
- The Remember window setting is gone: the window position and size are no longer saved between runs (a resized window still keeps its size through the queue).
- The title bar buttons moved in, so the window corners are easy to grab.
- Smoother rounded corners on video tiles, and the neighbouring video tiles are rounded too.
- The Preferences panel, the menu and the queue view fit small windows.
- Slow moments in the player loop are named in the terminal (to track down stutter); the seek previews start later and take less CPU.

## v29
- The queue view no longer snaps back to the playing item after a few seconds; swipe and preview as many tiles as you like.
- A tap outside the tiles glides the row back to the playing item.

## v28
- The sound goes quiet while seeking, so there is no scratching.
- Page Up and Page Down are off; only the window corners resize.
- A tap on the playing tile fills the window instead of the screen; the size you gave the window is kept for every item, and full screen can no longer change it.
- Preferences, Crossfade and Sleep timer: the name stays and the choices squeeze in beside it.
- Previews: a video tile under the mouse plays at its own speed.
- Neighbour video tiles are nearly as big as the middle one and lean toward it.

## v27
- Playing again from the tiled view closes it sooner, and the video grows back a little quicker.
- The screen-sleep check repeats every 2 s and the terminal says when the screen may sleep.

## v26
- Previews on the seek bar: a picture of the video at the time under the mouse or the dragging, made in the background from key frames.
- Remember window: the window's size and place are saved when the player closes; once you resize or tile the window the next items keep its size (new Preferences row).
- Always on top with the O key (or a right click on the title bar when the window manager has no menu), with a dot in the title bar.
- Song tiles are smaller than video tiles in the queue view while a video plays.

## v25
- Preferences: the mouse on a setting shows all its choices in that row, click one to pick it; the rows glide between value and choices, and the sleep timer row glides too.
- Seeking in small steps: the bar follows every step at once and seeks are sent as fast as pictures arrive.
- The video crossfade shows in the queue view tiles too.
- Smooth slanted edges for the tiles; bigger video tiles; a tap on the playing tile grows the video first, then goes full screen.

## v24
- Background playback no longer stutters: a window the window manager holds back stops waiting for the screen, and the packet queue is bigger so audio keeps flowing.
- The window is shown once, so new items and the idle screen no longer raise it or re-center it; a tiled or maximized window keeps its size.
- Window title is `ffplay-custom - name`; right click on the title bar opens the window manager's menu (X11).
- Queue view: tapping the playing video's tile opens it full screen; pausing a queued video opens the view; the last picture stays when the queue ends and the player does not quit.
- Bigger video tiles, a dark glass strip behind the seek and volume bars, a shorter title bar.
- Video crossfade, no flash of the last picture on close, seek steps of 0.3 and 0.5 s with exact landing.

## v23
- Translucent top title bar in windowed mode (hides with the seek bar), with close on the left, fullscreen on the right, centered title, and native window-manager dragging/tiling via `SDL_SetWindowHitTest`.
- Reworked `Esc` key behaviour: closes open menus/panels or exits fullscreen instead of quitting the player.
- Moved the currently playing indicator dot to sit right before the track/video title in both card and large-title views.
- Installer creates an application entry and Desktop shortcut on first install.

## v22
- Key `l`: the playing video keeps playing live in its own tile, with an animated change from and to the full-screen video.
- Videos keep their own shape in the queue view for playlists with both audio and video, and the view stays when a video follows a song.
- A paused player keeps responding: the bar shows when the mouse moves and hides after the hide delay.
- The frosted glass (menus, queue panel, media info, Open, preferences) is light, with dark text.

## v21
- The sleep timer's "end of track" pauses just before the end of the item instead of going to the idle screen.
- Key `l` shows the videos of the queue as tiles in their own shape, with a dot on the video that plays and no disc.
- The waveform bars sit in the middle of the space between the queue view and the seek bar and grow up and down from the middle.

## Repository (after v20)
- `scripts/build.sh` links SDL2_ttf (it was missing from the link line) and builds in `~/ffplay-custom-build`, so it cannot overwrite a working tree in `~/build`.
- `REQUIREMENTS.md` and `scripts/install-deps.sh` list and install everything the player needs.
- README tidied: Requirements moved up, and the build steps no longer repeat the python3-gi install.

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
