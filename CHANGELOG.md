# Changelog

Every update to ffplay-custom, newest first. The numbers match the `patch_queue/patch_queue_vN.py` scripts.

## Repository (after v22)
- `assets/logo.png`: the ffplay-custom logo, so a fresh setup does not end up with the plain badge.
- `scripts/install.sh` installs the player, the media-controls helper, the app-menu launcher and the logo.

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
