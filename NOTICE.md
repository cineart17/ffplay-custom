# Notices

## What this project is based on

ffplay-custom is a modified version of `fftools/ffplay.c` from **FFmpeg 6.1.1** (https://ffmpeg.org).

- Original file: Copyright (c) 2003 Fabrice Bellard and the FFmpeg developers.
- License of the original file: GNU Lesser General Public License, version 2.1 or later (see `LICENSE`).
- Modified file in this repository: `src/fftools/ffplay.c`. Every change from the original is in
  `patches/ffplay-custom.patch`, and the history of the changes is in git and in `CHANGELOG.md`.
- The modifications are made available under the same license (LGPL 2.1 or later).

The license header at the top of `ffplay.c` must stay in the file.

## Build configuration

```
./configure --disable-programs --enable-ffplay --disable-doc --enable-libdav1d
```

Neither `--enable-gpl` nor `--enable-nonfree` is used, so the resulting build stays under the LGPL. If you add those
options, or other external libraries, the license of the result can change. Check each library before you do.

## Libraries used (not included in this repository)

| Library | Used for | License |
| --- | --- | --- |
| FFmpeg libraries (libavcodec, libavformat, libavutil, libswscale, libswresample, libavfilter, libavdevice) | Decoding and playback | LGPL 2.1 or later |
| SDL2 | Window, drawing and audio output | zlib |
| libdav1d | AV1 decoding | BSD 2-Clause |
| PyGObject and GLib (optional) | `tools/ffplay-mpris`, desktop media controls | LGPL 2.1 or later |

This table is a summary. The license of each project is the one that applies, so check its own repository if you need
to be sure.

## If you share a build

If you publish a compiled ffplay-custom, FFmpeg's own checklist (https://ffmpeg.org/legal.html) suggests:

1. Compile without `--enable-gpl` and without `--enable-nonfree`.
2. Make sure the source you publish matches the binary you publish exactly (tag the commit you built from).
3. Include the changes against FFmpeg (`patches/ffplay-custom.patch`) and the configure line (above).
4. Publish the source as a tarball or zip next to the binary.
5. Say in the download page or README that the software uses code of FFmpeg licensed under the LGPL v2.1, with a link
   to the source.

This is general information, not legal advice.
