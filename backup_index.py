"""
FileMind Pre-Scan Backup

Creates a timestamped backup of the index (SQLite + Qdrant) before any
major scan operation. Restores can be done from this snapshot.

Usage:
    python backup_index.py            # Create backup
    python backup_index.py --list     # List existing backups
    python backup_index.py --restore <timestamp>  # Restore a backup
"""

import sys
import json
import shutil
from pathlib import Path
from datetime import datetime

try:
    from .config import config
except ImportError:
    from config import config

FILEMIND_DIR = Path(__file__).parent
INDEX_DIR = config.index_dir
VAULT_DIR = FILEMIND_DIR / "vault"
BACKUP_PREFIX = datetime.now().strftime("%Y%m%d_%H%M%S")


def create_backup():
    """Create a full backup of the index before scanning."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = VAULT_DIR / f"index_backup_{timestamp}"

    print(f"\n{'='*60}")
    print(f"  FileMind Pre-Scan Backup")
    print(f"  Timestamp: {timestamp}")
    print(f"{'='*60}\n")

    # Create backup directory
    backup_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Backup location: {backup_dir}")

    # Backup SQLite catalog
    sqlite_db = INDEX_DIR / "filemind.db"
    if sqlite_db.exists():
        dest = backup_dir / "filemind.db"
        shutil.copy2(sqlite_db, dest)
        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"  [OK] SQLite catalog: {size_mb:.2f} MB")
    else:
        print(f"  [SKIP] SQLite catalog not found at {sqlite_db}")

    # Backup Qdrant vector store
    qdrant_dir = config.qdrant_path
    if qdrant_dir.exists():
        dest = backup_dir / "qdrant"
        shutil.copytree(qdrant_dir, dest)
        # Calculate size
        total_size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
        size_mb = total_size / (1024 * 1024)
        print(f"  [OK] Qdrant vectors: {size_mb:.2f} MB")
    else:
        print(f"  [SKIP] Qdrant store not found at {qdrant_dir}")

    # Write backup manifest
    manifest = {
        "timestamp": timestamp,
        "created_at": datetime.now().isoformat(),
        "sqlite_db": str(sqlite_db),
        "qdrant_dir": str(qdrant_dir),
        "backup_path": str(backup_dir),
        "type": "pre_scan_backup",
    }
    manifest_path = backup_dir / "MANIFEST.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"  [OK] Manifest written: MANIFEST.json")

    # Cleanup old backups (keep last 5)
    cleanup_old_backups()

    print(f"\n  Backup complete: {backup_dir}")
    print(f"{'='*60}\n")
    return backup_dir


def list_backups():
    """List existing index backups."""
    if not VAULT_DIR.exists():
        print("No vault directory found.")
        return

    backups = sorted(VAULT_DIR.glob("index_backup_*"))
    if not backups:
        print("No index backups found.")
        return

    print(f"\n{'='*60}")
    print(f"  FileMind Index Backups")
    print(f"{'='*60}\n")

    for backup_dir in backups:
        manifest = backup_dir / "MANIFEST.json"
        if manifest.exists():
            with open(manifest, "r") as f:
                m = json.load(f)
            print(f"  {m['timestamp']}  ({m['type']})")
            print(f"    Path: {m['backup_path']}")
        else:
            print(f"  {backup_dir.name}  (no manifest)")
    print()


def restore_backup(timestamp: str):
    """Restore an index backup."""
    backup_dir = VAULT_DIR / f"index_backup_{timestamp}"
    if not backup_dir.exists():
        print(f"Backup not found: {backup_dir}")
        print("Run: python backup_index.py --list")
        return

    print(f"\n{'='*60}")
    print(f"  FileMind Index Restore")
    print(f"  Restoring: {timestamp}")
    print(f"{'='*60}\n")

    # Confirm
    print(f"  This will OVERWRITE the current index at {INDEX_DIR}")
    print(f"  Confirming restore from: {backup_dir}\n")

    # Restore SQLite
    src_db = backup_dir / "filemind.db"
    dest_db = INDEX_DIR / "filemind.db"
    if src_db.exists():
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_db, dest_db)
        print(f"  [OK] Restored SQLite catalog")
    else:
        print(f"  [SKIP] No SQLite backup found")

    # Restore Qdrant
    src_qdrant = backup_dir / "qdrant"
    dest_qdrant = INDEX_DIR / "qdrant"
    if src_qdrant.exists():
        if dest_qdrant.exists():
            shutil.rmtree(dest_qdrant)
        shutil.copytree(src_qdrant, dest_qdrant)
        print(f"  [OK] Restored Qdrant vectors")
    else:
        print(f"  [SKIP] No Qdrant backup found")

    print(f"\n  Restore complete. Verify with: python run.py stats")
    print(f"{'='*60}\n")


def cleanup_old_backups(keep=5):
    """Remove old backups, keeping the most recent N."""
    backups = sorted(VAULT_DIR.glob("index_backup_*"), reverse=True)
    if len(backups) <= keep:
        return

    for old_backup in backups[keep:]:
        print(f"  [CLEANUP] Removing old backup: {old_backup.name}")
        shutil.rmtree(old_backup)


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--list" in args:
        list_backups()
    elif "--restore" in args:
        idx = args.index("--restore")
        timestamp = args[idx + 1] if idx + 1 < len(args) else None
        if not timestamp:
            print("Usage: python backup_index.py --restore <timestamp>")
            sys.exit(1)
        restore_backup(timestamp)
    else:
        create_backup()
