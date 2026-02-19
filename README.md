# Photo Manager

A cross-platform photo organizer and lightweight viewer built with Python, PyQt6, and SQLite. Designed for local-first photo management with perceptual duplicate detection, flexible tagging, and a Raspberry Pi-compatible viewer.

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Usage](#usage)
  - [Viewer](#viewer)
  - [Organizer](#organizer)
- [Keyboard Controls](#keyboard-controls)
  - [Viewer Controls](#viewer-controls)
  - [Organizer Controls](#organizer-controls)
  - [Custom Keybindings](#custom-keybindings)
  - [Bindable Actions](#bindable-actions)
- [Import Templates](#import-templates)
- [Raspberry Pi Integration](#raspberry-pi-integration)

---

## Overview

```
src/photo_manager/
├── config/              # Configuration management
│   └── config.py
├── db/                  # SQLite database layer
│   ├── manager.py       # CRUD operations
│   ├── models.py        # ImageRecord, TagDefinition, etc.
│   └── schema.py        # Schema + migrations
├── scanner/             # File scanning & metadata extraction
│   ├── exif.py          # EXIF orientation correction
│   ├── datetime_parser.py
│   ├── tag_template.py  # YAML import templates
│   └── scanner.py       # Directory scanning & import
├── hashing/             # Perceptual hashing & duplicate detection
│   ├── hasher.py        # pHash/dHash at 4 rotations + mirror
│   └── duplicates.py    # Rotation/mirror-aware comparison
├── query/               # Query language
│   ├── parser.py        # Expression parser
│   └── engine.py        # Query-to-SQL conversion
├── export/              # Data export
│   └── exporter.py
├── viewer/              # Lightweight image viewer (Pi-compatible)
│   ├── main_window.py   # Viewer window
│   ├── image_canvas.py  # Zoom, pan, rotation
│   ├── image_loader.py  # Threaded loading + caching
│   ├── slideshow.py     # Timed slideshow
│   └── ...
└── organizer/           # Full desktop organizer
    ├── organizer_window.py  # Main organizer window
    ├── grid_view.py         # Thumbnail grid
    ├── single_image_view.py # Full-size viewer
    ├── image_source.py      # Filtering (delete, duplicates)
    ├── tag_dialog.py        # Tag editing UI
    ├── duplicate_dialog.py  # Duplicate detection UI
    └── ...
```

---

## Installation

**Requirements:** Python 3.10+

```bash
# Clone the repository
git clone <repo-url>
cd photo_manager

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate
# Activate (Linux/macOS)
source .venv/bin/activate

# Install in editable mode
pip install -e .

# Install with dev dependencies (pytest)
pip install -e ".[dev]"

# Add src to pythonpath
$env:PYTHONPATH = "src"
```

**Dependencies:**
- `Pillow >= 10.0` -- Image processing
- `imagehash >= 4.3` -- Perceptual hashing
- `PyYAML >= 6.0` -- Configuration files
- `PyQt6 >= 6.5` -- GUI framework

### Quick Install (p_man launcher)

These scripts create a repo-local `.venv`, install the package in editable mode, and add the venv `Scripts`/`bin` directory to your **user PATH** so you can run `p_man` from anywhere. Restart your shell after running.

**Windows (PowerShell):**
```powershell
.\install_windows.ps1
```

**Linux (bash):**
```bash
./install_linux.sh
```

**WSL (bash):**
```bash
./install_wsl.sh
```

WSL uses the Windows `p_man` command and expects **Windows-style paths** (e.g., `D:\Photos`).

---

## Usage

### Unified Launcher (p_man)

`p_man [path]` defaults to the **current directory** if no path is provided.

Behavior:
- If the directory contains a database file (`.db`, `.sqlite`, `.sqlite3`), it opens the **organizer** with that DB.
- If no DB is found, it opens the **viewer** and scans recursively (no import).
- `--import` imports the target directory; with `--db` it uses that DB, otherwise the organizer will prompt for a DB.
- If multiple DB files are found, you will be prompted to select one.
- All viewer/organizer flags are passed through (e.g., `--view`, `--fullscreen`, `--slideshow`, `--query`, `--config`).

Examples:
```bash
p_man
p_man D:\Photos
p_man --import D:\Photos
p_man --import --db D:\Photos\my.db
p_man D:\Photos --view single --fullscreen
```

### Viewer

The lightweight viewer works directly on a directory of images or a database file. It supports slideshow mode, zoom/pan, rotation, brightness/contrast adjustment, and GIF animation.

```bash
# View images in a directory
python -m photo_manager.viewer /path/to/photos

# View from a database file
python -m photo_manager.viewer /path/to/photos.db

# Start in slideshow mode
python -m photo_manager.viewer /path/to/photos --slideshow

# Start fullscreen
python -m photo_manager.viewer /path/to/photos --fullscreen

# Use a custom config file
python -m photo_manager.viewer /path/to/photos --config viewer_config.yaml

# Filter by query (database mode only)
python -m photo_manager.viewer /path/to/photos.db --query "tag.person.alice"

# Open query dialog interactively
python -m photo_manager.viewer /path/to/photos.db --query
```

**Options:**

| Flag | Description |
|------|-------------|
| `<path>` | Directory to scan or `.db` file to open |
| `--config`, `-c` | Path to config YAML file |
| `--slideshow`, `-s` | Start in slideshow mode |
| `--fullscreen` | Start fullscreen |
| `--windowed` | Start windowed (overrides config) |
| `--query`, `-q` | Filter query expression; no value opens dialog |

The viewer auto-loads `viewer_config.yml` from the target directory if present.

### Organizer

The organizer provides a full database-backed photo management workflow: import, tag, review duplicates, and delete.

```bash
# Launch organizer (opens last-used database or prompts)
python -m photo_manager.organizer

# Open or create a specific database
python -m photo_manager.organizer /path/to/photos.db

# Open database and import a directory on startup
python -m photo_manager.organizer --db photos.db --import /path/to/new_photos

# Start in single-image view
python -m photo_manager.organizer photos.db --view single

# Start fullscreen
python -m photo_manager.organizer photos.db --fullscreen

# Use a custom config file
python -m photo_manager.organizer --config my_config.yaml
```

**Options:**

| Flag | Description |
|------|-------------|
| `<db_path>` | Database file path (positional or via `--db`) |
| `--db` | Path to database file |
| `--import` | Directory to import on startup |
| `--view` | Starting view: `grid` (default) or `single` |
| `--fullscreen` | Start fullscreen |
| `--windowed` | Start windowed |
| `--config` | Path to config YAML file |

**Per-database config** is stored at `<db_dir>/<db_name>.config.yaml` and is created automatically. Keybindings and session state are saved there.

---

## Keyboard Controls

Press **Alt+M** in either the viewer or organizer to toggle the help overlay, which shows all active keybindings.

### Viewer Controls

| Key | Action |
|-----|--------|
| **Right / Left** | Next / previous image |
| **Shift+Right / Left** | Next / previous folder |
| **F10** | Go to image number |
| **F12** | Toggle sequential / random order |
| **Up / Down** | Rotate CCW / CW |
| **Ctrl+Up / Down** | Brightness up / down |
| **Alt+Up / Down** | Contrast up / down |
| **Tab** | Cycle zoom mode |
| **Mouse Wheel** | Zoom in / out |
| **Click + Drag** | Pan image |
| **Ctrl+R** | Reset image adjustments |
| **Ctrl+I** | Toggle info display |
| **F9** | Cycle info detail level |
| **F11** | Toggle fullscreen |
| **Space** | Toggle slideshow pause |
| **+ / =** | Increase GIF speed |
| **- / _** | Decrease GIF speed |
| **Alt+M** | Show / hide help |
| **Esc** | Quit |

### Organizer Controls

**Views & Navigation:**

| Key | Action |
|-----|--------|
| **Tab** | Toggle grid / single-image view |
| **F11** | Toggle fullscreen |
| **Right / Left** | Next / previous image (single view) |
| **Alt+Right / Left** | Next / previous folder |
| **F10** | Go to image number |

**Image Adjustments (Single View):**

| Key | Action |
|-----|--------|
| **Up / Down** | Rotate CCW / CW |
| **Ctrl+Up / Down** | Brightness up / down |
| **Alt+Up / Down** | Contrast up / down |
| **Mouse Wheel** | Zoom in / out |
| **Click + Drag** | Pan image |
| **Ctrl+R** | Reset image adjustments |
| **Ctrl+Shift+S** | Save image with rotation baked in |
| **Ctrl+I** | Toggle info display |
| **F9** | Cycle info detail level |

**Tags:**

| Key | Action |
|-----|--------|
| **F2** | Edit tags dialog |
| **Ctrl+T** | Edit keybindings dialog |
| **Alt+Shift+T** | Show tag hotkeys overlay |
| **Ctrl+C** | Copy scene/event/person tags from current image |
| **Ctrl+V** | Paste copied tags onto current image |
| **Ctrl+Shift+V** | Apply copied tags to all images in folder (or dup group) |

**Delete Workflow:**

| Key | Action |
|-----|--------|
| **.** | Mark for deletion and advance |
| **Alt+.** | Unmark deletion and advance |
| **Ctrl+Alt+D** | Mark entire folder for deletion |
| **Alt+D** | Review images marked for deletion |
| **Ctrl+D** | Execute deletions (permanently delete marked files) |

**Duplicate Management:**

| Key | Action |
|-----|--------|
| **Ctrl+Shift+D** | Detect duplicates (hashing + comparison) |
| **F3** | Enter / exit duplicate review mode |
| **Alt+Right / Left** | Next / previous duplicate group (in review) |
| **Ctrl+K** | Mark image as kept |
| **Ctrl+N** | Toggle not-a-duplicate flag |
| **Ctrl+D** | Delete unmarked duplicates (in review) |

**Database:**

| Key | Action |
|-----|--------|
| **F4** | Import directory |
| **F5** | Query / filter images |
| **F1** | Check / add directory |

**Default tag hotkeys** (customizable via Ctrl+T):

| Key | Action |
|-----|--------|
| **F** | Set favorite |
| **D** | Set to-delete |
| **R** | Set reviewed |
| **Ctrl+.** | Clear to-delete and advance to next |

### Custom Keybindings

There are two ways to customize keybindings in the organizer:

#### Via the UI (Ctrl+T)

1. Press **Ctrl+T** to open the keybinding editor
2. Click the key capture field and press your desired key combination
3. Enter one or more comma-separated actions (e.g., `tag:person.alice` or `set_favorite, next_image`)
4. Click **Add Binding**
5. Click **OK** to save

Bindings are saved to the per-database config file and persist across sessions.

#### Via Config YAML

Edit the per-database config file (`<db_name>.config.yaml`) or pass a config file with `--config`. Keybindings live under `organizer.quick_toggle_bindings`:

```yaml
organizer:
  quick_toggle_bindings:
    # Single action
    "F": ["set_favorite"]
    "R": ["set_reviewed"]

    # Multiple actions executed in order
    "Ctrl+.": ["clear_to_delete", "next_image"]

    # Tag actions
    "1": ["tag:person.alice"]
    "2": ["tag:person.bob"]
    "3": ["tag:scene.outdoor.lake"]

    # Untag actions
    "Shift+1": ["untag:person.alice"]

    # Complex workflows
    "Ctrl+1": ["tag:event.vacation", "tag:scene.outdoor", "set_reviewed", "next_image"]
```

Legacy format (also supported):

```yaml
organizer:
  tag_keybindings:
    "1": "person.alice"
    "2": "event.birthday"
```

### Bindable Actions

These action strings can be used in `quick_toggle_bindings`:

| Action | Description |
|--------|-------------|
| `set_favorite` | Set the favorite flag |
| `clear_favorite` | Clear the favorite flag |
| `set_to_delete` | Set the to-delete flag |
| `clear_to_delete` | Clear the to-delete flag |
| `set_reviewed` | Set the reviewed flag |
| `clear_reviewed` | Clear the reviewed flag |
| `tag:<path>` | Add a tag (e.g., `tag:person.alice`, `tag:scene.outdoor.lake`) |
| `untag:<path>` | Remove a tag (e.g., `untag:person.alice`) |
| `next_image` | Navigate to next image |
| `prev_image` | Navigate to previous image |
| `edit_tags` | Open the tag editor dialog |

Tag paths use dot notation matching the tag tree hierarchy. Missing intermediate nodes are created automatically (e.g., `tag:event.wedding.2024` creates `event` > `wedding` > `2024`).

**Note:** All tag names are case-insensitive and stored as lowercase. `tag:Person.Alice` and `tag:person.alice` are equivalent.

---

## Query Syntax

The query language filters images by tags and fixed fields. Press **F5** in the organizer or use `--query` in the viewer. The filter dialog includes a **tag picker tree** — double-click any tag to insert it at the cursor position in the query input.

### Tag Presence (Dynamic Tags)

Dynamic tags are **presence-based** — the tag tree hierarchy encodes the full path, and you query by checking if a tag exists on an image.

```
tag.person.alice                 # Images tagged with person.alice
tag.scene.outdoor.lake           # Images tagged with scene.outdoor.lake
tag.event.birthday               # Images tagged with event.birthday
```

### Fixed Field Comparisons

Fixed fields (stored as columns on the images table) support comparison operators:

```
tag.datetime.year>=2020          # Year 2020 or later
tag.datetime.year==2019          # Exactly 2019
tag.favorite==true               # Favorited images
tag.image_size.width>1920        # Wide images
tag.location.city=="Portland"    # Specific city
```

### Boolean Shorthand

Boolean fields support a shorthand without `==true`:

```
tag.favorite                     # Same as tag.favorite==true
tag.reviewed                     # Same as tag.reviewed==true
```

### Negation

Prefix `!` negates any expression:

```
!tag.person.alice                # Images NOT tagged with person.alice
!tag.favorite                    # Images that are NOT favorited
!(tag.person.alice && tag.scene.outdoor)  # Negate a group
```

### Wildcards (Descendant Tags)

Query a tag and all its descendants:

```
tag.scene.outdoor*               # outdoor + all children (lake, hike, ...)
tag.scene.outdoor.*              # Children only (lake, hike), NOT outdoor itself
```

### None / Missing Values

Search for images with missing fixed fields:

```
tag.datetime.year==None          # Images with no year set
tag.datetime.year!=None          # Images that have a year
```

### Logical Operators

Combine expressions with `&&` (AND) and `||` (OR), using parentheses for grouping:

```
tag.person.alice && tag.datetime.year>=2020
tag.scene.indoor || tag.scene.outdoor
(tag.person.alice || tag.person.bob) && tag.event.birthday
tag.person.alice && tag.datetime.year>=2020 && !tag.scene.indoor
```

### Backward Compatibility

The old value-based syntax still works — it's treated as a presence check:

```
tag.person=="alice"              # Equivalent to tag.person.alice
tag.person!="alice"              # Equivalent to !tag.person.alice
```

---

## Import Templates

When importing a directory, you can place a `load_template.yaml` file in the import directory to automatically extract tags from the folder structure.

### Template Format

```yaml
version: 1
pattern: "{scene}/{filename}.{ext}"
options:
  case_insensitive: true
  require_full_match: true
  on_mismatch: tag_auto_tag_errors
tags:
  scene: "{scene}"
```

### Fields

| Field | Description |
|-------|-------------|
| `version` | Template version (currently `1`) |
| `pattern` | Path pattern with `{named}` capture groups |
| `options.case_insensitive` | Ignore case when matching (default: `false`) |
| `options.require_full_match` | All segments must match (default: `true`) |
| `options.on_mismatch` | What to do when a file doesn't match the pattern |
| `tags` | Maps tag paths to captured values via `{back_references}` |

### Pattern Syntax

Patterns describe the expected directory structure relative to the import root. Named groups in `{braces}` capture path segments and can be referenced in the `tags` section.

- `{name}` -- Capture a directory or file name segment
- `*` -- Match any directory or filename (no capture)
- `{filename}.{ext}` -- Special: matches the file's name and extension (must be the last segment)

### on_mismatch Options

| Value | Behavior |
|-------|----------|
| `skip_file` | Silently skip files that don't match the pattern |
| `tag_auto_tag_errors` | Import the file but flag it with `auto_tag_errors = true` |
| `fail_import` | Stop the entire import on first mismatch |

### Examples

**Tag by scene folder:**
```yaml
version: 1
pattern: "{scene}/*.*"
tags:
  scene: "{scene}"
```

Directory `Vacation/IMG_001.jpg` creates tag `scene.vacation` (presence-based).

**Tag by event and person:**
```yaml
version: 1
pattern: "{event}/{person}/{filename}.{ext}"
options:
  on_mismatch: skip_file
tags:
  event: "{event}"
  person: "{person}"
```

Directory `Birthday/Alice/photo.jpg` creates tags `event.birthday` and `person.alice`.

**Multi-level with year extraction:**
```yaml
version: 1
pattern: "{year}/{scene}/{filename}.{ext}"
options:
  case_insensitive: true
tags:
  datetime.year: "{year}"
  scene: "{scene}"
```

---

## Raspberry Pi Integration

*Running the lightweight viewer on a Raspberry Pi as a digital photo frame.*

### Setup Instructions

<!-- TODO -->

### Systemd Controls

<!-- TODO -->

### Add/Remove Files via USB

<!-- TODO -->
