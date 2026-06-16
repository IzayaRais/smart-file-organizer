"""
organizer.py v4.0 — SHA-256 Deduplicator, Smart File Organizer & Rollback Engine
- TRUE MOVE: files are relocated and originals are gone
- DUPLICATES → Windows Recycle Bin (restorable)
- CLI & Interactive Modes: supports automation and batch processing
- Undo/Rollback Function: reverses previous organizations safely
- Smart Fallback: uses MIME-type detection for unknown extensions
- Configuration support: custom categories and skip rules via organizer_config.json
- Full audit report & JSON history log
"""

import os
import sys
import shutil
import hashlib
import datetime
import json
import argparse
import mimetypes
from pathlib import Path
from collections import defaultdict

# Force sys.stdout and sys.stderr to UTF-8 to prevent UnicodeEncodeError on Windows console
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ──────────────────────────────────────────────────────────────
# SECTION 0 ▸ DEFAULT CONFIGURATION & GLOBAL STATE
# ──────────────────────────────────────────────────────────────

VERSION = "4.0"

# Default categories (can be overridden by organizer_config.json)
CATEGORIES = {
    "Documents":    {".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".csv", ".rtf", ".odt", ".pages"},
    "Images":       {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".bmp", ".tiff", ".ico"},
    "Videos":       {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm"},
    "Audio":        {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma"},
    "Archives":     {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
    "Code_Scripts": {".py", ".js", ".html", ".css", ".json", ".xml", ".sh", ".bat", ".cmd", ".ts", ".tsx", ".jsx"},
}

EXT_TO_CAT: dict = {}
for _cat, _exts in CATEGORIES.items():
    for _e in _exts:
        EXT_TO_CAT[_e] = _cat

MANAGED_FOLDERS = {
    "Documents", "Images", "Videos", "Audio", "Archives",
    "Code_Scripts", "Others", "Duplicates_Trash", "Empty_Files",
    "Previous_Folders",
}

SKIP_NAMES    = {"desktop.ini", "thumbs.db", "thumbs.db:encryptable", "organization_log.txt", ".organizer_history.json"}
SKIP_PREFIXES = ("~$",)
SKIP_FRAGS    = (".git",)
HASH_CHUNK    = 8 * 1024 * 1024   # 8 MB streaming chunks


# ──────────────────────────────────────────────────────────────
# SECTION 1 ▸ CONFIGURATION LOADING
# ──────────────────────────────────────────────────────────────

def load_config(config_path=None):
    """Load configuration from JSON, overriding defaults if present."""
    global CATEGORIES, EXT_TO_CAT, MANAGED_FOLDERS, SKIP_NAMES, SKIP_PREFIXES, SKIP_FRAGS
    
    if not config_path:
        # Check default config next to the script
        script_dir = Path(__file__).resolve().parent
        config_path = script_dir / "organizer_config.json"
    else:
        config_path = Path(config_path)
        
    if config_path.exists() and config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            loaded = []
            if "categories" in data:
                CATEGORIES = {k: set(v) for k, v in data["categories"].items()}
                EXT_TO_CAT = {}
                for _cat, _exts in CATEGORIES.items():
                    for _e in _exts:
                        EXT_TO_CAT[_e.lower()] = _cat
                # Recompute MANAGED_FOLDERS based on new categories
                MANAGED_FOLDERS = set(CATEGORIES.keys()) | {
                    "Others", "Duplicates_Trash", "Empty_Files", "Previous_Folders"
                }
                loaded.append("categories")
                
            if "skip_names" in data:
                SKIP_NAMES = set(data["skip_names"])
                loaded.append("skip_names")
            if "skip_prefixes" in data:
                SKIP_PREFIXES = tuple(data["skip_prefixes"])
                loaded.append("skip_prefixes")
            if "skip_fragments" in data:
                SKIP_FRAGS = tuple(data["skip_fragments"])
                loaded.append("skip_fragments")
                
            info(f"Loaded config from {config_path.name} (fields: {', '.join(loaded)})")
            return True
        except Exception as exc:
            warn(f"Could not parse config file {config_path}: {exc}. Using defaults.")
    return False


# ──────────────────────────────────────────────────────────────
# SECTION 2 ▸ RECYCLE BIN SUPPORT
# ──────────────────────────────────────────────────────────────

def _ensure_send2trash():
    """Install send2trash if not present — called once at startup."""
    try:
        import send2trash  # noqa
        return True
    except ImportError:
        print("  Installing send2trash for Recycle Bin support...")
        import subprocess
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "send2trash", "--quiet"],
            capture_output=True
        )
        if r.returncode == 0:
            print("  send2trash installed OK.")
            return True
        else:
            print("  WARNING: Could not install send2trash.")
            print("  Duplicates will be PERMANENTLY deleted instead of sent to Recycle Bin.")
            return False

_HAS_SEND2TRASH = _ensure_send2trash()

def recycle(path: Path) -> bool:
    """Send a file to the Recycle Bin. Returns True on success."""
    if _HAS_SEND2TRASH:
        try:
            import send2trash
            send2trash.send2trash(str(path))
            return True
        except Exception as exc:
            warn(f"Recycle Bin failed for {path.name}: {exc} — permanent delete used.")
    # Fallback: permanent delete
    try:
        path.unlink()
        return True
    except Exception as exc:
        warn(f"Could not delete {path.name}: {exc}")
        return False


# ──────────────────────────────────────────────────────────────
# SECTION 3 ▸ CONSOLE HELPERS
# ──────────────────────────────────────────────────────────────

try:
    import colorama
    colorama.init()
    C = {"cyan":"\033[96m","green":"\033[92m","yellow":"\033[93m",
         "magenta":"\033[95m","red":"\033[91m","gray":"\033[90m",
         "white":"\033[97m","reset":"\033[0m","bold":"\033[1m"}
except ImportError:
    C = defaultdict(str)

_original_print = print
def print(*args, **kwargs):
    if 'file' in kwargs and kwargs['file'] is not None:
        _original_print(*args, **kwargs)
        return
    sep = kwargs.get('sep', ' ')
    end = kwargs.get('end', '\n')
    text = sep.join(str(arg) for arg in args)
    try:
        _original_print(text, end=end, flush=kwargs.get('flush', False))
    except UnicodeEncodeError:
        text_ascii = text.replace("╔", "+").replace("═", "-").replace("╗", "+") \
                         .replace("║", "|").replace("╚", "+").replace("╝", "+") \
                         .replace("►", ">").replace("✔", "OK").replace("⚠", "/!\\") \
                         .replace("✘", "[X]").replace("─", "-").replace("█", "#") \
                         .replace("░", ".").replace("╠", "+").replace("╣", "+") \
                         .replace("♻", "Recycled") \
                         .replace("┌", "+").replace("┐", "+").replace("└", "+") \
                         .replace("┘", "+").replace("├", "+").replace("┤", "+") \
                         .replace("▪", "*")
        try:
            safe_text = text_ascii.encode('ascii', errors='replace').decode('ascii')
            _original_print(safe_text, end=end, flush=kwargs.get('flush', False))
        except Exception:
            try:
                _original_print(text.encode('ascii', errors='replace').decode('ascii'), end=end, flush=kwargs.get('flush', False))
            except Exception:
                pass

def col(text, color): return f"{C[color]}{text}{C['reset']}"
def banner():
    os.system("cls" if os.name == "nt" else "clear")
    w = 56
    print()
    print(col(f"  ╔{'═'*w}╗", "cyan"))
    print(col(f"  ║{'FOLDER ORGANIZER  v'+VERSION+'  —  Python SHA-256':^{w}}║", "cyan"))
    print(col(f"  ║{'True Move  ·  Recycle Bin Safe  ·  Full Report':^{w}}║", "cyan"))
    print(col(f"  ╚{'═'*w}╝", "cyan"))
    print()

def step(m):  print(col(f"  ► {m}", "yellow"))
def ok(m):    print(col(f"  ✔ {m}", "green"))
def warn(m):  print(col(f"  ⚠ {m}", "magenta"))
def info(m):  print(col(f"    {m}", "gray"))
def err(m):   print(col(f"  ✘ {m}", "red"))
def ruler():  print(col(f"  {'─'*56}", "gray"))


# ──────────────────────────────────────────────────────────────
# SECTION 4 ▸ PATH & WRITE VALIDATION
# ──────────────────────────────────────────────────────────────

def get_target_folder() -> Path:
    while True:
        print(col("  Enter the FULL PATH of the folder to organize:", "white"))
        raw = input(col("  Path: ", "white")).strip().strip('"')
        if not raw:
            err("Path cannot be empty.")
            continue
        p = Path(raw).expanduser()
        if p.is_dir():
            ok(f"Folder confirmed: {p}")
            print()
            return p
        err(f"Not found: {raw}")
        print(col("  [R] Retry   [Q] Quit", "gray"))
        if input(col("  Choice: ", "white")).strip().upper() == "Q":
            sys.exit(0)

def verify_write_permission(path: Path) -> bool:
    """Test if we can write to the target directory by creating a temp file."""
    try:
        temp_file = path / f".write_test_{int(datetime.datetime.now().timestamp())}"
        temp_file.touch()
        temp_file.unlink()
        return True
    except (PermissionError, OSError) as exc:
        err(f"No write permission in target directory: {path}. Details: {exc}")
        return False


# ──────────────────────────────────────────────────────────────
# SECTION 5 ▸ FILE COLLECTION
# ──────────────────────────────────────────────────────────────

def _is_managed(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
        return rel.parts[0] in MANAGED_FOLDERS if rel.parts else False
    except ValueError:
        return False

def _is_protected(path: Path) -> bool:
    n = path.name.lower()
    if n in SKIP_NAMES: return True
    if any(n.startswith(p) for p in SKIP_PREFIXES): return True
    if path.name.startswith("."): return True
    if any(f in path.parts for f in SKIP_FRAGS): return True
    if os.name == "nt":
        try:
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            if attrs != -1 and (attrs & 0x2 or attrs & 0x4):  # HIDDEN | SYSTEM
                return True
        except Exception:
            pass
    return False

def collect_files(root: Path) -> list:
    step("Scanning folder recursively...")
    files = [
        p for p in root.rglob("*")
        if p.is_file() and not _is_managed(p, root) and not _is_protected(p)
    ]
    ok(f"Found {len(files)} candidate files.")
    print()
    return files


# ──────────────────────────────────────────────────────────────
# SECTION 6 ▸ SHA-256 HASHING
# ──────────────────────────────────────────────────────────────

def sha256(path: Path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(HASH_CHUNK):
                h.update(chunk)
        return h.hexdigest()
    except (PermissionError, OSError) as exc:
        warn(f"Cannot hash {path.name}: {exc}")
        return None

def detect_duplicates(files: list):
    step("Computing SHA-256 hashes (streaming, memory-safe)...")
    zero_byte = [f for f in files if f.stat().st_size == 0]
    hashable  = [f for f in files if f.stat().st_size  > 0]

    hash_to_keeper: dict = {}
    duplicates: list = []
    total = len(hashable)

    for i, path in enumerate(hashable, 1):
        pct = int(i / max(1, total) * 44)
        bar = f"[{'█'*pct}{'░'*(44-pct)}] {i}/{total}"
        print(f"\r  {col(bar, 'cyan')}  ", end="", flush=True)

        digest = sha256(path)
        if digest is None:
            continue

        if digest in hash_to_keeper:
            existing = hash_to_keeper[digest]
            if path.stat().st_ctime < existing.stat().st_ctime:
                duplicates.append(existing)
                hash_to_keeper[digest] = path
            else:
                duplicates.append(path)
        else:
            hash_to_keeper[digest] = path

    print()
    keepers = list(hash_to_keeper.values())
    ok(f"Keepers: {len(keepers)}  |  Duplicates: {len(duplicates)}  |  Zero-byte: {len(zero_byte)}")
    print()
    return keepers, duplicates, zero_byte


# ──────────────────────────────────────────────────────────────
# SECTION 7 ▸ SMART SORTING & MOVE PLAN
# ──────────────────────────────────────────────────────────────

def get_category_date(path: Path) -> str:
    mtime = path.stat().st_mtime
    dt = datetime.datetime.fromtimestamp(mtime)
    return dt.strftime("%Y-%m")

def get_category_size(path: Path) -> str:
    size_bytes = path.stat().st_size
    if size_bytes < 1024 * 1024:
        return "Small (<1MB)"
    elif size_bytes < 100 * 1024 * 1024:
        return "Medium (1MB-100MB)"
    elif size_bytes < 1024 * 1024 * 1024:
        return "Large (100MB-1GB)"
    else:
        return "Huge (>1GB)"

def get_category_by_mime(path: Path) -> str:
    """Determine category based on file MIME type if extension not matched."""
    mime, _ = mimetypes.guess_type(path)
    if mime:
        main_type = mime.split('/')[0]
        if main_type == "text":
            return "Documents"
        elif main_type == "image":
            return "Images"
        elif main_type == "video":
            return "Videos"
        elif main_type == "audio":
            return "Audio"
        elif main_type == "application":
            sub_type = mime.split('/')[1]
            if sub_type in ("zip", "x-tar", "x-rar-compressed", "x-7z-compressed", "gzip"):
                return "Archives"
            elif sub_type in ("pdf", "msword", "vnd.openxmlformats-officedocument.wordprocessingml.document", "rtf"):
                return "Documents"
    return "Others"

def safe_dest(dest_dir: Path, filename: str, used: dict) -> Path:
    key  = (str(dest_dir).lower(), filename.lower())
    stem = Path(filename).stem
    sfx  = Path(filename).suffix
    if key not in used:
        used[key] = 0
        candidate = dest_dir / filename
    else:
        used[key] += 1
        candidate = dest_dir / f"{stem}_{used[key]}{sfx}"
    return candidate

def build_move_plan(keepers: list, zero_byte: list, root: Path, org_method: str = "type") -> list:
    used: dict = {}
    plan = []
    for f in keepers:
        if org_method == "date":
            cat = get_category_date(f)
        elif org_method == "size":
            cat = get_category_size(f)
        else:
            ext = f.suffix.lower()
            if ext in EXT_TO_CAT:
                cat = EXT_TO_CAT[ext]
            else:
                cat = get_category_by_mime(f)
            
        dst = safe_dest(root / cat, f.name, used)
        if f.resolve() != dst.resolve():
            plan.append({"src": f, "dst": dst, "cat": cat})
    for f in zero_byte:
        dst = safe_dest(root / "Empty_Files", f.name, used)
        if f.resolve() != dst.resolve():
            plan.append({"src": f, "dst": dst, "cat": "Empty_Files"})
    return plan


# ──────────────────────────────────────────────────────────────
# SECTION 8 ▸ DRY RUN PREVIEW
# ──────────────────────────────────────────────────────────────

def show_dry_run(duplicates, move_plan, total, n_keepers, n_zero):
    if duplicates:
        step("Duplicates that WOULD be sent to Recycle Bin:")
        for d in duplicates:
            info(f"  ♻  {d}")
        print()

    step(f"Files that WOULD be moved ({len(move_plan)}):")
    for p in move_plan:
        note = f"  →  renamed: {p['dst'].name}" if p['dst'].name != p['src'].name else ""
        info(f"  [{p['cat']}]  {p['src'].name}{note}")
    print()

    w = 52
    rows = [
        ("Files scanned",           total),
        ("Unique keepers",          n_keepers),
        ("Duplicates → Recycle Bin",len(duplicates)),
        ("Files to move",           len(move_plan)),
        ("Zero-byte files",         n_zero),
    ]
    print(col(f"  ┌{'─'*w}┐", "cyan"))
    print(col(f"  │{'  DRY RUN SUMMARY — NO CHANGES MADE  ':^{w}}│", "cyan"))
    print(col(f"  ├{'─'*w}┤", "cyan"))
    for label, val in rows:
        line = f"  {label:<30}: {val}"
        print(col(f"  │{line:<{w}}│", "cyan"))
    print(col(f"  └{'─'*w}┘", "cyan"))
    print()


# ──────────────────────────────────────────────────────────────
# SECTION 9 ▸ LIVE EXECUTION
# ──────────────────────────────────────────────────────────────

def execute(root: Path, duplicates: list, move_plan: list, log: list):
    trashed_ok = trash_err = moved_ok = move_err = 0

    # ── 9a: Send duplicates to Recycle Bin ───────────────────
    if duplicates:
        step(f"Sending {len(duplicates)} duplicate(s) to Recycle Bin...")
        log.append("=== DUPLICATES SENT TO RECYCLE BIN ===")
        for d in duplicates:
            if recycle(d):
                info(f"  ♻  Recycled: {d.name}")
                log += [f"  FILE : {d}", f"  ACTION: Sent to Recycle Bin", "  ---"]
                trashed_ok += 1
            else:
                log.append(f"  FAILED TO RECYCLE: {d}")
                trash_err += 1
        ok(f"Recycled {trashed_ok}  |  Errors: {trash_err}")
        print()

    # ── 9b: TRUE MOVE unique files into category folders ─────
    step(f"Moving {len(move_plan)} file(s) to category folders...")
    log.append("")
    log.append("=== FILES MOVED ===")

    for p in move_plan:
        p["dst"].parent.mkdir(parents=True, exist_ok=True)
        src: Path = p["src"]
        dst: Path = p["dst"]
        try:
            shutil.move(str(src), str(dst))
            renamed = dst.name != src.name
            note = f"  (renamed → {dst.name})" if renamed else ""
            info(f"  [{p['cat']}]  {src.name}{note}")
            log += [f"  FROM: {src}", f"  TO  : {dst}", "  ---"]
            moved_ok += 1
        except Exception as exc:
            warn(f"  Failed: {src.name}: {exc}")
            log.append(f"  FAILED: {src}  ({exc})")
            move_err += 1

    ok(f"Moved {moved_ok}  |  Errors: {move_err}")
    print()
    return trashed_ok, moved_ok, move_err, trash_err


# ──────────────────────────────────────────────────────────────
# SECTION 10 ▸ CLEANUP EMPTY FOLDERS
# ──────────────────────────────────────────────────────────────

def cleanup_empty_folders_list(root: Path, log: list, empty_folders_list: list) -> int:
    prev_dir = root / "Previous_Folders"
    used = {}
    moved_count = 0

    step("Cleaning up empty folders...")
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        d = Path(dirpath)
        if d == root:
            continue
        if _is_managed(d, root) or d == prev_dir:
            continue
        
        try:
            if not any(d.iterdir()):
                prev_dir.mkdir(parents=True, exist_ok=True)
                dst = safe_dest(prev_dir, d.name, used)
                shutil.move(str(d), str(dst))
                moved_count += 1
                empty_folders_list.append({"src": d, "dst": dst})
                info(f"  [Empty_Folder]  {d.name} → {dst.name}")
                log += [f"  EMPTY FOLDER: {d}", f"  MOVED TO : {dst}", "  ---"]
        except Exception as exc:
            warn(f"  Failed to move empty folder {d.name}: {exc}")
            
    if moved_count > 0:
        ok(f"Moved {moved_count} empty folder(s) to {prev_dir.name}")
    else:
        info("  No empty folders found.")
    print()
    return moved_count


# ──────────────────────────────────────────────────────────────
# SECTION 11 ▸ UNDO & HISTORY SYSTEM
# ──────────────────────────────────────────────────────────────

def save_history(root: Path, method: str, moves: list, empty_folders: list, recycled: list):
    """Save history of the run to a hidden JSON file inside the target folder."""
    history_path = root / ".organizer_history.json"
    new_entry = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "method": method,
        "moves": [{"src": str(m["src"]), "dst": str(m["dst"])} for m in moves],
        "empty_folders": [{"src": str(ef["src"]), "dst": str(ef["dst"])} for ef in empty_folders],
        "recycled": [str(r) for r in recycled]
    }
    
    history_data = []
    if history_path.exists():
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                history_data = json.load(f)
                if not isinstance(history_data, list):
                    history_data = []
        except Exception:
            pass
            
    history_data.append(new_entry)
    
    try:
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(history_data, f, indent=2)
    except Exception as exc:
        warn(f"Could not save history for undo: {exc}")

def execute_undo(root: Path) -> bool:
    """Roll back the most recent organization operation."""
    history_path = root / ".organizer_history.json"
    if not history_path.exists():
        err(f"No history file found at {history_path}. Cannot undo.")
        return False
        
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            history_data = json.load(f)
    except Exception as exc:
        err(f"Failed to read history file: {exc}")
        return False
        
    if not history_data or not isinstance(history_data, list):
        err("History is empty or invalid.")
        return False
        
    # Get the last run
    last_run = history_data.pop()
    
    step(f"Reversing run from {last_run.get('timestamp', 'unknown time')}...")
    
    # Reversing moves (dst -> src)
    moves = last_run.get("moves", [])
    success_moves = 0
    fail_moves = 0
    
    # Restoring files
    for move in reversed(moves):
        src = Path(move["src"])
        dst = Path(move["dst"])
        
        if not dst.exists():
            warn(f"File to restore does not exist at destination: {dst}")
            fail_moves += 1
            continue
            
        try:
            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(src))
            info(f"  Restored: {dst.name} → {src}")
            success_moves += 1
        except Exception as exc:
            warn(f"Failed to restore {dst.name} to {src}: {exc}")
            fail_moves += 1
            
    # Reversing empty folders (dst -> src)
    empty_folders = last_run.get("empty_folders", [])
    success_folders = 0
    for ef in reversed(empty_folders):
        src = Path(ef["src"])
        dst = Path(ef["dst"])
        if dst.exists():
            try:
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(src))
                info(f"  Restored folder: {dst.name} → {src}")
                success_folders += 1
            except Exception as exc:
                warn(f"Failed to restore folder {dst.name}: {exc}")
                
    # Duplicates warning
    recycled = last_run.get("recycled", [])
    if recycled:
        warn(f"{len(recycled)} duplicate file(s) were sent to the Recycle Bin/deleted.")
        warn("  These cannot be automatically restored by this script.")
        warn("  Please restore them manually from the Windows Recycle Bin if needed.")
        for r in recycled:
            info(f"    - {Path(r).name}")
            
    # Clean up empty managed folders left behind
    cleanup_empty_folders_after_undo(root)
    
    # Save the updated history list
    try:
        if history_data:
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(history_data, f, indent=2)
        else:
            history_path.unlink(missing_ok=True)
    except Exception as exc:
        warn(f"Failed to update history file: {exc}")
        
    ok(f"Undo completed: {success_moves} file(s) and {success_folders} folder(s) restored.")
    if fail_moves > 0:
        warn(f"Failed to restore {fail_moves} file(s).")
    return True

def cleanup_empty_folders_after_undo(root: Path):
    """Deletes empty directories in the root that are part of MANAGED_FOLDERS."""
    for folder in MANAGED_FOLDERS:
        d = root / folder
        if d.is_dir():
            try:
                if not any(d.iterdir()):
                    d.rmdir()
                    info(f"  Cleaned up empty folder: {folder}")
            except Exception:
                pass


# ──────────────────────────────────────────────────────────────
# SECTION 12 ▸ FINAL CONSOLE REPORT
# ──────────────────────────────────────────────────────────────

def print_report(stats: dict, move_plan: list, duplicates: list, root: Path):
    """Beautiful, detailed final report printed to console."""
    w = 58
    ruler()
    print()
    print(col(f"  ╔{'═'*w}╗", "green"))
    print(col(f"  ║{'  ORGANIZATION COMPLETE — FULL REPORT  ':^{w}}║", "green"))
    print(col(f"  ╠{'═'*w}╣", "green"))

    summary_rows = [
        ("Files scanned",                stats["scanned"]),
        ("Unique files kept",             stats["unique"]),
        ("Duplicates → Recycle Bin ♻",   stats["dupes"]),
        ("Files moved to folders",        stats["moved"]),
        ("Zero-byte files handled",       stats["zero"]),
        ("Empty folders moved",           stats.get("empty_folders", 0)),
        ("Errors",                        stats["errors"]),
    ]
    for label, val in summary_rows:
        line = f"  {label:<32}: {val}"
        color = "red" if label == "Errors" and val > 0 else "green"
        print(col(f"  ║{line:<{w}}║", color))

    print(col(f"  ╠{'═'*w}╣", "green"))

    # Category breakdown
    cat_counts: dict = defaultdict(int)
    for p in move_plan:
        cat_counts[p["cat"]] += 1
    if cat_counts:
        print(col(f"  ║{'  FOLDER BREAKDOWN':^{w}}║", "green"))
        print(col(f"  ╠{'═'*w}╣", "green"))
        for cat in sorted(cat_counts):
            n    = cat_counts[cat]
            bar  = "▪" * min(n, 30)
            line = f"  {cat:<16} {bar}  {n} file(s)"
            print(col(f"  ║{line:<{w}}║", "green"))
        print(col(f"  ╠{'═'*w}╣", "green"))

    # Duplicates list
    if duplicates:
        print(col(f"  ║{'  DUPLICATES RECYCLED (restorable)':^{w}}║", "green"))
        print(col(f"  ╠{'═'*w}╣", "green"))
        for d in duplicates:
            line = f"  ♻  {d.name}"
            print(col(f"  ║{line:<{w}}║", "magenta"))
        print(col(f"  ╠{'═'*w}╣", "green"))

    print(col(f"  ║{'  Audit log → organization_log.txt':^{w}}║", "green"))
    print(col(f"  ╚{'═'*w}╝", "green"))
    print()
    print(col("  TIP: Open Recycle Bin to restore any duplicate you want back.", "yellow"))
    print()


# ──────────────────────────────────────────────────────────────
# SECTION 13 ▸ AUDIT LOG
# ──────────────────────────────────────────────────────────────

def write_log(root: Path, log_lines: list, stats: dict):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = (
        f"FOLDER ORGANIZER v{VERSION} — AUDIT LOG\n"
        f"Date    : {ts}\n"
        f"Target  : {root}\n"
        f"Scanned : {stats['scanned']}\n"
        f"Unique  : {stats['unique']}\n"
        f"Dupes   : {stats['dupes']}\n"
        f"Moved   : {stats['moved']}\n"
        f"EmptyDirs: {stats.get('empty_folders', 0)}\n"
        f"Errors  : {stats['errors']}\n"
        f"{'='*44}\n\n"
    )
    log_path = root / "organization_log.txt"
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(header + "\n".join(log_lines))
        ok(f"Log saved: {log_path}")
    except Exception as exc:
        warn(f"Could not write log: {exc}")


# ──────────────────────────────────────────────────────────────
# SECTION 14 ▸ CLI ARGUMENT PARSING
# ──────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="organizer.py — SHA-256 Deduplicator, Smart File Organizer & Rollback Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python organizer.py -t "C:\\MyFolder" -m type --dry-run
  python organizer.py -t "C:\\MyFolder" -m date --yes
  python organizer.py -t "C:\\MyFolder" --undo
        """
    )
    parser.add_argument(
        "-t", "--target",
        help="Path to the folder to organize. If not provided, the script will prompt for it."
    )
    parser.add_argument(
        "-m", "--method",
        choices=["type", "date", "size"],
        help="Organization method: 'type' (by file type), 'date' (by year-month), or 'size' (by size range)."
    )
    parser.add_argument(
        "-d", "--dry-run",
        action="store_true",
        help="Preview the changes without actually moving or deleting any files."
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip all interactive confirmation prompts (Live Mode, confirmation)."
    )
    parser.add_argument(
        "--undo",
        action="store_true",
        help="Undo the last organization run in the target folder."
    )
    parser.add_argument(
        "-c", "--config",
        help="Path to a custom JSON configuration file."
    )
    return parser.parse_args()


# ──────────────────────────────────────────────────────────────
# MAIN ENTRYPOINT
# ──────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    
    # Load config (defaults to organizer_config.json in script folder if exists)
    load_config(args.config)
    
    # ── Resolve target folder ────────────────────────────────────────
    root = None
    if args.target:
        candidate = Path(args.target).expanduser().resolve()
        if candidate.is_dir():
            root = candidate
            ok(f"Target directory: {root}")
        else:
            err(f"Provided target path is not a directory: {args.target}")
            sys.exit(1)
    else:
        # Fall back to interactive target prompt
        banner()
        root = get_target_folder()
        
    # Verify write access
    if not verify_write_permission(root):
        sys.exit(1)
        
    # ── Check if undo is requested ───────────────────────────────────
    if args.undo:
        if args.yes:
            execute_undo(root)
        else:
            warn(f"About to UNDO the last organization in: {root}")
            print(col("  This will move organized files and folders back to their original paths.", "yellow"))
            print(col("  Proceed?", "white"))
            print(col("  1. Yes", "cyan"))
            print(col("  2. No (Cancel)", "cyan"))
            while True:
                choice = input(col("  Choice [1/2]: ", "white")).strip()
                if choice == "1":
                    execute_undo(root)
                    break
                elif choice == "2":
                    print("  Cancelled.")
                    break
                else:
                    err("Invalid choice. Please enter 1 or 2.")
        return

    org_method = args.method
    if not org_method:
        if args.yes:
            # Non-interactive default to 'type'
            org_method = "type"
        else:
            print(col("  Choose an organization method:", "white"))
            print(col("  1. By Type (Documents, Images, etc.)", "cyan"))
            print(col("  2. By Date (Year-Month)", "cyan"))
            print(col("  3. By Size (Small, Medium, Large, Huge)", "cyan"))
            print(col("  4. Undo Last Organization (Rollback)", "magenta"))
            while True:
                choice = input(col("  Choice [1/2/3/4]: ", "white")).strip()
                if choice == "1":
                    org_method = "type"
                    break
                elif choice == "2":
                    org_method = "date"
                    break
                elif choice == "3":
                    org_method = "size"
                    break
                elif choice == "4":
                    execute_undo(root)
                    if not args.target:
                        input(col("  Press ENTER to close...", "white"))
                    return
                else:
                    err("Invalid choice. Please enter 1, 2, 3, or 4.")
            print()
            print()

    # ── Resolve dry-run vs live ─────────────────────────────────────
    is_dry = args.dry_run
    if not args.dry_run and not args.yes and not args.target:
        # Prompt only if it's completely interactive
        print(col("  Run a DRY RUN first? (see the plan before any changes)", "white"))
        print(col("  1. Yes (Dry Run)", "cyan"))
        print(col("  2. No (Live Mode)", "cyan"))
        while True:
            choice = input(col("  Choice [1/2]: ", "white")).strip()
            if choice == "1":
                is_dry = True
                break
            elif choice == "2":
                is_dry = False
                break
            else:
                err("Invalid choice. Please enter 1 or 2.")
        print()

    if is_dry:
        warn("DRY RUN — previewing changes only.")
    else:
        ok(f"LIVE MODE — files will be moved using method '{org_method}'.")
    print()

    # ── Collect files ────────────────────────────────────────────────
    all_files = collect_files(root)
    total = len(all_files)
    if total == 0:
        ok("No files to organize.")
        if not args.yes and not args.target:
            input(col("  Press ENTER to exit...", "white"))
        return

    # ── Duplicate detection ──────────────────────────────────────────
    keepers, duplicates, zero_byte = detect_duplicates(all_files)
    move_plan = build_move_plan(keepers, zero_byte, root, org_method)

    if is_dry:
        show_dry_run(duplicates, move_plan, total, len(keepers), len(zero_byte))
        if not args.yes and not args.target:
            input(col("  Press ENTER to exit...", "white"))
        return

    # ── Confirmation (unless --yes or automatic run in background) ──
    if not args.yes and not args.target:
        warn(f"About to MOVE {len(move_plan)} file(s) and send {len(duplicates)} duplicate(s) to Recycle Bin.")
        print(col("  Duplicates go to Recycle Bin — you can restore them anytime.", "yellow"))
        print(col("  Proceed?", "white"))
        print(col("  1. Yes", "cyan"))
        print(col("  2. No (Cancel)", "cyan"))
        
        proceed = False
        while True:
            choice = input(col("  Choice [1/2]: ", "white")).strip()
            if choice == "1":
                proceed = True
                break
            elif choice == "2":
                print("  Cancelled.")
                input(col("  Press ENTER...", "white"))
                return
            else:
                err("Invalid choice. Please enter 1 or 2.")
        print()
    else:
        proceed = True

    if proceed:
        log_lines: list = []
        # Execute
        trashed, moved, move_err, trash_err = execute(root, duplicates, move_plan, log_lines)

        # Track actual empty folders moved to save in history for rollback
        empty_folders_moved_list = []
        empty_folders_moved_count = cleanup_empty_folders_list(root, log_lines, empty_folders_moved_list)

        # Stats
        stats = {
            "scanned": total,
            "unique":  len(keepers),
            "dupes":   len(duplicates),
            "moved":   moved,
            "zero":    len(zero_byte),
            "empty_folders": empty_folders_moved_count,
            "errors":  move_err + trash_err,
        }

        # Save History for undo
        save_history(root, org_method, move_plan, empty_folders_moved_list, duplicates)

        # Write text log
        write_log(root, log_lines, stats)

        # Print final console report
        print_report(stats, move_plan, duplicates, root)

        if not args.yes and not args.target:
            input(col("  Press ENTER to close...", "white"))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(col("\n\n  Interrupted. Exiting cleanly.", "magenta"))
        sys.exit(0)
