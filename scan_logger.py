"""
FileMind Scan Logger

Structured logging for full system scans. Records every file found,
its classification, safety status, and migration candidate status.
Outputs: 
  - Console summary during scan
  - JSON report at end (docs/scan_report_YYYYMMDD_HHMMSS.json)
  - Append to SYSTEM_NOTES.md with key findings

Usage:
    python scan_logger.py start                          # Begin logging session
    python scan_logger.py log <path> <category> <safety>  # Log individual file
    python scan_logger.py report                          # Generate summary report
    python run.py scan --full && python scan_logger.py --scan-log
"""

import json
import time
import sys
from pathlib import Path
from datetime import datetime
from collections import Counter
from dataclasses import dataclass, field, asdict

FILEMIND_DIR = Path(__file__).parent
DOCS_DIR = FILEMIND_DIR / "docs"
SYSTEM_NOTES = FILEMIND_DIR / "SYSTEM_NOTES.md"
SAFETY_CONFIG = FILEMIND_DIR / "safety_config.py"


@dataclass
class FileRecord:
    path: str
    extension: str
    size_bytes: int
    category: str = "unknown"
    safety: str = "UNCLASSIFIED"  # IMMUTABLE, PROTECTED, MOVABLE, UNCLASSIFIED
    in_index: bool = False
    is_duplicate: bool = False
    migration_note: str = ""


@dataclass 
class ScanSession:
    session_id: str
    started_at: str
    ended_at: str = ""
    total_files: int = 0
    total_size_bytes: int = 0
    by_category: dict = field(default_factory=dict)
    by_safety: dict = field(default_factory=dict)
    by_extension: dict = field(default_factory=dict)
    movable_candidates: list = field(default_factory=list)
    protected_review: list = field(default_factory=list)
    immutables_found: int = 0
    duplicates_found: int = 0
    unknown_files: int = 0
    errors: list = field(default_factory=list)
    notes: list = field(default_factory=list)


class ScanLogger:
    """Structured logger for system scans."""

    def __init__(self):
        self.session = ScanSession(
            session_id=datetime.now().strftime("%Y%m%d_%H%M%S"),
            started_at=datetime.now().isoformat(),
        )
        self.records: list[FileRecord] = []
        DOCS_DIR.mkdir(parents=True, exist_ok=True)

    def log_file(self, record: FileRecord):
        """Log a single file record."""
        self.records.append(record)
        self.session.total_files += 1
        self.session.total_size_bytes += record.size_bytes

        # Tally categories
        cat = record.category
        self.session.by_category[cat] = self.session.by_category.get(cat, 0) + 1

        # Tally safety
        safety = record.safety
        self.session.by_safety[safety] = self.session.by_safety.get(safety, 0) + 1

        # Tally extensions
        ext = record.extension or "(no ext)"
        self.session.by_extension[ext] = self.session.by_extension.get(ext, 0) + 1

        # Track special cases
        if safety == "IMMUTABLE":
            self.session.immutables_found += 1
        if safety == "MOVABLE":
            self.session.movable_candidates.append(record.path)
        if safety == "PROTECTED":
            self.session.protected_review.append(record.path)
        if cat == "unknown":
            self.session.unknown_files += 1
        if record.is_duplicate:
            self.session.duplicates_found += 1

    def add_note(self, note: str):
        self.session.notes.append(note)

    def add_error(self, error: str):
        self.session.errors.append(error)

    def generate_report(self) -> dict:
        """Generate summary report as dict."""
        self.session.ended_at = datetime.now().isoformat()

        # Top extensions
        top_exts = dict(
            sorted(self.session.by_extension.items(), key=lambda x: x[1], reverse=True)[:15]
        )

        # Movable file breakdown
        movable_by_ext = Counter()
        for rec in self.records:
            if rec.safety == "MOVABLE":
                movable_by_ext[rec.extension or "(no ext)"] += 1

        return {
            "session_id": self.session.session_id,
            "started_at": self.session.started_at,
            "ended_at": self.session.ended_at,
            "duration_seconds": (
                datetime.fromisoformat(self.session.ended_at) 
                - datetime.fromisoformat(self.session.started_at)
            ).total_seconds(),
            "summary": {
                "total_files": self.session.total_files,
                "total_size_mb": round(self.session.total_size_bytes / (1024 * 1024), 2),
                "immutables_found": self.session.immutables_found,
                "protected_files": len(self.session.protected_review),
                "movable_candidates": len(self.session.movable_candidates),
                "unclassified": self.session.total_files 
                    - self.session.immutables_found 
                    - len(self.session.protected_review) 
                    - len(self.session.movable_candidates),
                "duplicates_found": self.session.duplicates_found,
                "unknown_category": self.session.unknown_files,
            },
            "by_category": dict(sorted(self.session.by_category.items(), key=lambda x: x[1], reverse=True)),
            "by_safety": dict(sorted(self.session.by_safety.items(), key=lambda x: x[1], reverse=True)),
            "top_15_extensions": top_exts,
            "movable_by_extension": dict(movable_by_ext.most_common(15)),
            "notes": self.session.notes,
            "errors": self.session.errors,
            "movable_sample": self.session.movable_candidates[:20],
            "protected_sample": self.session.protected_review[:20],
        }

    def save_report(self) -> Path:
        """Save report to JSON file."""
        report = self.generate_report()
        filepath = DOCS_DIR / f"scan_report_{self.session.session_id}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        return filepath

    def print_summary(self):
        """Print human-readable summary to console."""
        report = self.generate_report()
        s = report["summary"]

        print("\n" + "=" * 60)
        print(f"  FileMind Full System Scan Report")
        print(f"  Session: {self.session.session_id}")
        print(f"  Duration: {report['duration_seconds']:.1f}s")
        print("=" * 60)
        print(f"\n  Total files:  {s['total_files']:,}")
        print(f"  Total size:   {s['total_size_mb']:.1f} MB")
        print(f"  Duplicates:   {s['duplicates_found']:,}")
        print(f"  Unknowns:     {s['unknown_category']:,}")
        print(f"\n  ── Safety Classification ──")
        print(f"  IMMUTABLE (never touch):    {s['immutables_found']:>6,}")
        print(f"  PROTECTED (needs approval):  {s['protected_files']:>6,}")
        print(f"  MOVABLE (safe to move):      {s['movable_candidates']:>6,}")
        unclass = s['unclassified']
        print(f"  UNCLASSIFIED (needs review): {unclass:>6,}")
        print(f"\n  ── Categories ──")
        for cat, count in report["by_category"].items():
            bar = "#" * min(count // 10, 50)
            print(f"  {cat:<20} {count:>6,} {bar}")
        print(f"\n  ── Top Extensions ──")
        for ext, count in list(report["top_15_extensions"].items())[:10]:
            bar = "#" * min(count // 5, 50)
            print(f"  {ext:<10} {count:>6,} {bar}")
        print(f"\n  ── Movable Breakdown ──")
        for ext, count in list(report.get("movable_by_extension", {}).items())[:10]:
            print(f"  {ext:<10} {count:>6,}")
        print(f"\n  Report saved to: docs/scan_report_{self.session.session_id}.json")
        print("=" * 60 + "\n")


def run_full_scan_with_logging():
    """Run a full system scan with structured logging."""
    import sys
    sys.path.insert(0, str(FILEMIND_DIR))
    
    from catalog import Catalog
    from config import SCAN_ROOTS, INDEX_EXTENSIONS, SKIP_DIRS, SKIP_SUBDIRS
    from safety_config import classify_safety, is_immutable, is_protected, is_movable

    logger = ScanLogger()
    catalog = Catalog()

    logger.add_note(f"Scan roots: {SCAN_ROOTS}")
    logger.add_note(f"Index extensions: {len(INDEX_EXTENSIONS)} types")
    print(f"\nStarting full system scan with safety logging...")
    print(f"Scan roots: {SCAN_ROOTS}")

    for root in SCAN_ROOTS:
        root_path = Path(root)
        if not root_path.exists():
            logger.add_error(f"Scan root not found: {root}")
            continue

        print(f"\n  Scanning: {root}")
        for ext in sorted(INDEX_EXTENSIONS):
            for filepath in root_path.rglob(f"*{ext}"):
                if not filepath.is_file():
                    continue

                path_str = str(filepath)

                # Check skip dirs
                if any(skip in filepath.parts for skip in SKIP_DIRS | SKIP_SUBDIRS):
                    continue

                # Get file info
                try:
                    size = filepath.stat().st_size
                except (OSError, PermissionError):
                    logger.add_error(f"Cannot read: {path_str}")
                    continue

                # Safety classification
                safety = classify_safety(path_str)

                # Check if already in index
                in_index = catalog.file_exists(str(filepath))

                record = FileRecord(
                    path=path_str,
                    extension=filepath.suffix.lower(),
                    size_bytes=size,
                    category="unknown",  # Will be populated from catalog
                    safety=safety,
                    in_index=in_index,
                )

                # Try to get existing category from catalog
                if in_index:
                    entry = catalog.get_file(str(filepath))
                    if entry and entry.get('category'):
                        record.category = entry['category']

                logger.log_file(record)

    # Save report
    report_path = logger.save_report()
    logger.print_summary()

    return logger


if __name__ == "__main__":
    if "--scan" in sys.argv or "scan" in sys.argv:
        run_full_scan_with_logging()
    elif "--report" in sys.argv or "report" in sys.argv:
        # Load latest report
        import glob
        reports = sorted(DOCS_DIR.glob("scan_report_*.json"))
        if reports:
            with open(reports[-1], "r") as f:
                report = json.load(f)
            print(json.dumps(report, indent=2))
        else:
            print("No scan reports found. Run: python scan_logger.py --scan")
    else:
        print("FileMind Scan Logger")
        print("\nUsage:")
        print("  python scan_logger.py --scan        # Run full scan with logging")
        print("  python scan_logger.py --report      # Show latest report")
        print("\nOr from FileMind:")
        print("  python run.py scan --full           # Normal scan (also logs)")
