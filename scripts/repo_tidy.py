#!/usr/bin/env python3
# Repo tidy-up for ffplay-custom.
#   * README.md: the Requirements section moves from the very end to just before "Working on the code".
#   * README.md: step 4 of the build no longer repeats the python3-gi install (install-deps.sh already does it).
#   * CHANGELOG.md: one line about it.
# Run from inside ~/projects/ffplay-custom.
# Writes a file only if every spot matches exactly once.

import sys

readme = open("README.md").read()
changelog = open("CHANGELOG.md").read()


def patch(text, old, new, label):
    n = text.count(old)
    if n != 1:
        print("FAILED:", label, "- matched", n, "times, expected 1. Nothing written.")
        sys.exit(1)
    print("ok:", label)
    return text.replace(old, new)


# The Requirements section, exactly as it is at the end of the README now
req = """
## Requirements

A few tools are needed for ffplay-custom to build and work, such as `zenity` for the file dialogs and `python3-gi` for the desktop media controls. See [REQUIREMENTS.md](REQUIREMENTS.md), or install everything with `./scripts/install-deps.sh`.
"""

if "## Requirements" in readme and readme.index("## Requirements") < readme.index("## Working on the code"):
    print("Already applied. Nothing written.")
    sys.exit(1)

# 1. take it out of the end...
readme = patch(readme, req, "", "remove Requirements from the end")
readme = readme.rstrip("\n") + "\n"

# 2. ...and put it before "Working on the code"
readme = patch(readme, "## Working on the code\n",
               req.lstrip("\n") + "\n## Working on the code\n",
               "Requirements before Working on the code")

# 3. step 4 of the build
readme = patch(readme,
               "4. Optional: desktop media controls. This needs the Python GObject bindings:\n"
               "```\n"
               "sudo apt install -y python3-gi gir1.2-glib-2.0\n"
               "install -m 755 tools/ffplay-mpris ~/.local/bin/ffplay-mpris\n"
               "```\n",
               "4. Optional: desktop media controls (the Python GObject bindings came with step 1):\n"
               "```\n"
               "install -m 755 tools/ffplay-mpris ~/.local/bin/ffplay-mpris\n"
               "```\n",
               "step 4 without the repeated install")

# 4. the changelog
changelog = patch(changelog,
                  "- `REQUIREMENTS.md` and `scripts/install-deps.sh` list and install everything the player needs.\n",
                  "- `REQUIREMENTS.md` and `scripts/install-deps.sh` list and install everything the player needs.\n"
                  "- README tidied: Requirements moved up, and the build steps no longer repeat the python3-gi install.\n",
                  "changelog line")

open("README.md", "w").write(readme)
open("CHANGELOG.md", "w").write(changelog)
print("Done. Check with: git diff")
