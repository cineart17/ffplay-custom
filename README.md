# ffplay-custom

A customised build of **ffplay** (from FFmpeg 6.1.1) that works as a small music and video player with a
cover-flow queue, a spinning disc, frosted glass menus and desktop media controls.

It is not a new program. It is FFmpeg's own `fftools/ffplay.c` with a lot of changes on top, built with FFmpeg's normal
build system.

> ffplay-custom is an independent personal project. It is not affiliated with or endorsed by the FFmpeg project.
> "FFmpeg" is a trademark of Fabrice Bellard, originator of the FFmpeg project.

## Highlights

- **Cover-flow queue** for audio: the playing item is large in the middle with a spinning disc behind it, and the
  rest of the queue sits on both sides on tilted covers. Click, swipe or drag to move around, and drag a cover to a new
  place to reorder the queue.
- **Covers** come from the picture inside the file (or a frame from a video). Files without one get a frosted file icon.
- **Waveform bars** above the seek line, showing the shape of the whole track and bouncing with the music.
- **Frosted glass** menus: the queue panel (with smooth scrolling), Open, the item menu and preferences.
- **Backdrops**: a blurred, moving cover behind the player, and a bubble party for audio files without a cover.
- **Desktop media controls** (MPRIS) through the small `tools/ffplay-mpris` helper.
- Seek bar with chapter sections, a seek tooltip and a window snap preview.

The full list of changes is in [CHANGELOG.md](CHANGELOG.md).

## Layout of this repository

| Path | What it is |
| --- | --- |
| `src/fftools/ffplay.c` | The modified source file (the current state of the project). |
| `patches/ffplay-custom.patch` | Every change as one patch against the original FFmpeg 6.1.1 `ffplay.c`. |
| `patch_queue/` | The step-by-step update scripts (`patch_queue_vN.py`) the project was built with, kept as history. |
| `tools/ffplay-mpris` | Python helper that exposes the player to the desktop's media controls. |
| `scripts/build.sh` | Downloads FFmpeg 6.1.1, applies the patch and builds ffplay-custom. |
| `scripts/sync.sh` | Copies your working build into this repo and refreshes the patch. |
| `LICENSE`, `NOTICE.md` | License and third-party notices. Please read them if you share the code or a build. |

## Build

Tested on Ubuntu 24.04 (gcc 13).

1. Install what the build needs:
```
sudo apt install -y build-essential nasm pkg-config curl libsdl2-dev libdav1d-dev
```

2. Build (this downloads FFmpeg 6.1.1 into `~/build`, applies the patch and compiles):
```
./scripts/build.sh
```

3. Install the player:
```
cp --remove-destination ~/build/ffmpeg-6.1.1/ffplay ~/.local/bin/ffplay-custom
```

4. Optional: desktop media controls. This needs the Python GObject bindings:
```
sudo apt install -y python3-gi gir1.2-glib-2.0
install -m 755 tools/ffplay-mpris ~/.local/bin/ffplay-mpris
```

The build uses this configure line, and nothing else is enabled:
```
./configure --disable-programs --enable-ffplay --disable-doc --enable-libdav1d
```

## Use

```
ffplay-custom ~/Music/some-album/
```

Settings (bar color, hide delay and so on) are stored in `~/.config/ffplay-custom/settings.conf`.

## Working on the code

The project keeps one source of truth, `src/fftools/ffplay.c`, and git history for every change.

1. Make the change in your build tree (`~/build/ffmpeg-6.1.1`) and test it.
2. Copy the result into the repo and refresh the patch:
```
./scripts/sync.sh
```
3. Add a line to `CHANGELOG.md`, then commit:
```
git add -A
git commit -m "Short description of the change"
git push
```

## License

ffplay-custom is a modified version of FFmpeg's `ffplay.c`, so it is licensed under the
**GNU Lesser General Public License, version 2.1 or later**, like FFmpeg itself. The full text is in
[LICENSE](LICENSE). See [NOTICE.md](NOTICE.md) for what was modified, the build configuration and the licenses of
the libraries it uses.

If you share a compiled build of ffplay-custom (a GitHub release, for example), the LGPL asks you to also make the
matching source available. This repository does that, as long as the release is built from the same commit.
