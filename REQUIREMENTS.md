# Requirements

ffplay-custom is a patched FFmpeg `ffplay`, so it needs what FFmpeg's `ffplay` needs, plus a few extras for the
features we added. On Ubuntu or elementary OS, one command installs everything:

```
./scripts/install-deps.sh          # to build and run
./scripts/install-deps.sh --run    # only to run a finished build
```

## To run the player

| Tool | Package (apt) | What it is for |
|---|---|---|
| zenity | `zenity` | The file and folder dialogs (Open, Add to queue). Without it those buttons do nothing. |
| python3 and python3-gi | `python3 python3-gi gir1.2-glib-2.0` | The `ffplay-mpris` helper, which shows the player in the desktop's sound menu and answers media keys. Without it everything else still works. |
| SDL2 and SDL2_ttf | `libsdl2-2.0-0 libsdl2-ttf-2.0-0` | The window, the drawing and the text. |
| fontconfig and a font | `fontconfig fonts-dejavu-core` | The text font. The player asks fontconfig for your system's sans-serif font and falls back to DejaVu Sans. You can set your own in `~/.config/ffplay-custom/settings.conf`. |
| dav1d | `libdav1d7` | AV1 video, because the build is configured with `--enable-libdav1d`. |
| A sound server | PipeWire or PulseAudio (already on a desktop install) | Sound. The crossfade plays two streams at once, which these allow. |
| A D-Bus session | already on a desktop install | Only for the media controls. |

Put `ffplay-mpris` somewhere on your `PATH`, for example `~/.local/bin`, and make it executable:

```
install -m 755 tools/ffplay-mpris ~/.local/bin/ffplay-mpris
```

The optional logo for the idle screen goes in `~/.config/ffplay-custom/logo.png`.

## To build the player

| Tool | Package (apt) | What it is for |
|---|---|---|
| Compiler and make | `build-essential` | Building FFmpeg. |
| pkg-config | `pkg-config` | Finding the libraries below. |
| nasm | `nasm` | FFmpeg's assembly code. Without it, configure stops (or builds a slower FFmpeg if you disable it). |
| SDL2 development files | `libsdl2-dev` | Needed by ffplay. |
| SDL2_ttf development files | `libsdl2-ttf-dev` | The patched `ffplay.c` includes `SDL_ttf.h` and links against it. |
| dav1d development files | `libdav1d-dev` | For `--enable-libdav1d`. |
| python3 | `python3` | The patch scripts in `patch_queue/` are Python. |
| xz, curl, patch, diff | `xz-utils curl patch diffutils` | Downloading and unpacking the FFmpeg source, applying and generating patches. |
| git, unzip | `git unzip` | Working with this repository. |

The player is built from the **FFmpeg 6.1.1** source. See `scripts/build.sh` for the exact configure line.

## Handy for testing (not needed)

| Tool | Package (apt) | What it is for |
|---|---|---|
| playerctl | `playerctl` | Try the media controls from a terminal: `playerctl -p ffplay-custom status`. |
| gdbus | `libglib2.0-bin` | Talk to the player over D-Bus by hand. |
