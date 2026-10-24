# Houdini Cache Tool

A small pipeline tool for SideFX Houdini that exports SOP geometry caches into a clean, versioned folder structure — and never overwrites an existing version.

## Why

Without a convention, caches end up as `output.abc` or `smoke_v2_final_OK.bgeo.sc` scattered around a project. This tool enforces one predictable layout so anyone (or any script) can find the right cache.

## Features

- Exports the selected SOP node to `$HIP/cache/<element>/vXXX/`
- Automatic version increment (`v001`, `v002`, ...) — existing versions are never touched
- Element names are sanitized (`Fumée Rouge` → `fumee_rouge`)
- Animated caches (timeline frame range) or static caches (current frame)
- Writes an `info.json` next to each version (user, date, source scene, node, frame range, Houdini version)
- Progress bar with cancel, and the timeline is restored to the artist's frame afterwards
- Clear error messages for common mistakes (unsaved scene, nothing selected, non-SOP node)

## Output layout

```
<hip folder>/
└── cache/
    └── fumee/
        ├── v001/
        │   ├── fumee_v001.0001.bgeo.sc
        │   ├── fumee_v001.0002.bgeo.sc
        │   └── info.json
        └── v002/
```

Example `info.json`:

```json
{
    "element": "fumee",
    "version": 1,
    "user": "hugo",
    "date": "2026-10-23T22:58:12",
    "hip_file": "/home/hugo/Documents/Pipeline_Tool_I/Hip/Cache_Demo.hipnc",
    "node": "/obj/geo1/mountain1",
    "frame_range": [1, 48],
    "houdini_version": "22.0.466"
}
```

## Requirements

- Houdini 22.0 (Python 3)
- Tested on Linux (Pop!_OS)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Kaiser-Hugo/houdini-cache-tool.git
   ```
2. In Houdini, right-click a shelf → **New Tool…**, and paste this in the **Script** tab (adjust the path):
   ```python
   import sys
   import importlib

   TOOL_PATH = "/path/to/houdini-cache-tool"
   if TOOL_PATH not in sys.path:
       sys.path.append(TOOL_PATH)

   import cache_tool
   importlib.reload(cache_tool)
   cache_tool.run()
   ```

## Usage

1. Save your scene.
2. Select the SOP node you want to cache.
3. Click the shelf button, enter an element name, choose **Animated** or **Static**.
4. The cache is written to the next free version folder.

## Roadmap

- [ ] Package the tool as an HDA with parameters and an Export button
- [ ] Version browser: list existing versions and load one with a File SOP
- [ ] Optional shot level (`cache/<shot>/<element>/vXXX`)

## Author

Hugo Kaiser — 3D / FX artist moving towards pipeline TD work.

## Development notes

This tool was built with the help of Claude (Anthropic) as a coding assistant.
I defined the specification and folder conventions, tested every feature in
Houdini, and reviewed and understood all of the code. Using AI this way —
directing it, verifying its output and catching issues such as deprecated
API calls — is part of what I wanted to practise with this project.