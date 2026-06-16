# Smart File Organizer & Deduplicator

A standard, robust, and feature-rich Python engine designed to declutter directories, deduplicate identical files using SHA-256 hashes, and safely categorize files into logical folder structures. Supports both a colorized interactive menu and a command-line interface (CLI) for automation, along with complete rollback (undo) capabilities.

---

## 🌟 Key Features

1. **SHA-256 Hashing & Deduplication**:
   - Computes unique SHA-256 hash signatures using streaming memory-safe chunks (8 MB).
   - Identifies identical files regardless of naming differences.
   - Moves duplicates safely to the Windows Recycle Bin (using `send2trash`) so they are easily restorable.
2. **True Relocation**:
   - Files are moved to destination directories rather than copied, ensuring zero storage overhead during organization.
   - Preserves timestamps and handles name conflicts gracefully (automatically renames conflicts sequentially).
3. **Smart MIME Fallback**:
   - Catches unknown file extensions and queries Python's built-in `mimetypes` library to route files to logical categories (e.g. `image/` -> `Images`, `text/` -> `Documents`).
4. **Complete Rollback (Undo) Engine**:
   - Every live run stores a structural rollback path inside a hidden `.organizer_history.json` log.
   - Running the rollback command restores all moved files and folders back to their original locations and cleans up empty category folders.
5. **Flexible Sorting Methods**:
   - **By Type**: Documents, Images, Videos, Audio, Archives, and Code Scripts.
   - **By Date**: Subfolders grouped by `Year-Month` (e.g. `2026-06`).
   - **By Size**: Subfolders grouped by size ranges (`Small (<1MB)`, `Medium`, `Large`, `Huge (>1GB)`).
6. **External Configuration (`organizer_config.json`)**:
   - Fully customize file extensions, excluded files/folders, prefix skips, and folder names.
7. **Double Execution Options**:
   - Interactive CLI with colored indicators (via `colorama`).
   - Windows launcher shell script (`organize.bat`) with drag-and-drop capability.

---

## 🚀 Quick Start

### 1. Drag & Drop Launcher (Windows)
Double-click `organize.bat` or drag a folder onto the `organize.bat` file to open the interactive prompt. Follow the on-screen steps:
1. Enter or confirm the folder path.
2. Choose organization method (Type, Date, Size, or Undo).
3. Choose whether to run a preview (Dry Run) first.

### 2. Command Line Interface (CLI)
For command line or scheduled automation, run the script directly:
```bash
# Preview organization by Type without making changes (Dry Run)
python organizer.py --target "C:\Users\Username\Downloads" --method type --dry-run

# Run live organization by Date skipping all interactive confirmation prompts
python organizer.py --target "C:\Users\Username\Downloads" --method date --yes

# Rollback (Undo) the last organization run in the target directory
python organizer.py --target "C:\Users\Username\Downloads" --undo --yes
```

---

## 🛠️ CLI Options Reference

| Argument | Short Flag | Description |
|---|---|---|
| `--help` | `-h` | Show the help message and exit. |
| `--target` | `-t` | Path to the directory to organize. Prompts if omitted. |
| `--method` | `-m` | Sorting method: `type`, `date`, or `size`. Defaults to `type` in automated mode. |
| `--dry-run` | `-d` | Preview files that will be moved or recycled without altering any files. |
| `--yes` | `-y` | Skip all confirmation prompts (ideal for batch scripts/automation). |
| `--undo` | *(none)* | Revert the last organization run on the target folder. |
| `--config` | `-c` | Path to a custom configuration JSON file. |

---

## ⚙️ Custom Configuration (`organizer_config.json`)

By default, the script looks for `organizer_config.json` next to `organizer.py`. You can adjust categories, extensions, and skips:

```json
{
  "categories": {
    "Documents": [".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".csv", ".rtf"],
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"],
    "Videos": [".mp4", ".mkv", ".avi", ".mov"],
    "Audio": [".mp3", ".wav", ".flac"],
    "Archives": [".zip", ".rar", ".7z", ".tar"],
    "Code_Scripts": [".py", ".js", ".html", ".css", ".json", ".ts"]
  },
  "skip_names": [
    "desktop.ini",
    "thumbs.db",
    "organization_log.txt",
    ".organizer_history.json"
  ],
  "skip_prefixes": ["~$"],
  "skip_fragments": [".git"]
}
```

---

## 🧪 Running Automated Tests

To verify file detection, hashing, category routing, duplicates removal, empty folder cleanup, and the undo mechanism, run the automated test suite:

```bash
python -m unittest test_organizer.py
```

The test suite automatically generates a local temporary workspace, populates it with dummy files (including duplicates, nested folders, empty files, and various extensions), runs the organizer CLI options, asserts correct results, tests the rollback logic, and cleans up after itself.
