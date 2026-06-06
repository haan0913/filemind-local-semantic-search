"""
Determine root cause of 4,692 file indexing gap.
Break down: (1) excluded by SKIP_DIRS, (2) scannable but not yet indexed, (3) other.
"""
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, 'C:/AI_STATION/filemind')
from config import SCAN_ROOTS, INDEX_EXTENSIONS, SKIP_DIRS, SKIP_SUBDIRS

# Re-scan disk and categorize each file
excluded_by_skip = 0
scannable_not_indexed = 0
total_on_disk = 0
excluded_by_ext = 0
by_skip_reason = Counter()
by_extension_gap = Counter()

from catalog import Catalog
c = Catalog()
c.init_db()

for root in SCAN_ROOTS:
    root_path = Path(root)
    if not root_path.exists():
        print(f"SKIP (not found): {root}")
        continue
    
    for ext in INDEX_EXTENSIONS:
        for filepath in root_path.rglob(f"*{ext}"):
            if not filepath.is_file():
                continue
            
            total_on_disk += 1
            path_str = str(filepath)
            
            # Check SKIP_DIRS
            skipped = False
            skip_reason = None
            for skip in SKIP_DIRS:
                if skip in filepath.parts:
                    skipped = True
                    skip_reason = f"SKIP_DIRS:{skip}"
                    break
            
            if not skipped:
                for skip in SKIP_SUBDIRS:
                    if skip in filepath.parts:
                        skipped = True
                        skip_reason = f"SKIP_SUBDIRS:{skip}"
                        break
            
            if skipped:
                excluded_by_skip += 1
                by_skip_reason[skip_reason] += 1
                continue
            
            # File is scannable - check if in index
            in_index = c.file_exists(path_str)
            if not in_index:
                scannable_not_indexed += 1
                by_extension_gap[ext] += 1
            # Check file size
            try:
                size = filepath.stat().st_size
                if size > 500_000:  # MAX_FILE_SIZE
                    by_skip_reason[f"TOO_LARGE:{size}"] += 1
            except:
                pass

c.close()

print(f"\n{'='*60}")
print(f"ROOT CAUSE ANALYSIS: 4,692 File Indexing Gap")
print(f"{'='*60}")
print(f"\nTotal files on disk (matching INDEX_EXTENSIONS): {total_on_disk}")
print(f"  Excluded by SKIP_DIRS/SKIP_SUBDIRS: {excluded_by_skip}")
print(f"  Scannable but NOT in index:         {scannable_not_indexed}")
print(f"  Already in index:                   {total_on_disk - excluded_by_skip - scannable_not_indexed}")

print(f"\n--- Excluded by SKIP_DIRS (top reasons) ---")
for reason, count in by_skip_reason.most_common(20):
    print(f"  {reason:>30}  {count:>6,}")

print(f"\n--- Scannable but not indexed (by extension) ---")
for ext, count in by_extension_gap.most_common(20):
    print(f"  {ext:>12}  {count:>6,}")

print(f"\n--- CONCLUSION ---")
if excluded_by_skip > scannable_not_indexed * 2:
    print("PRIMARY CAUSE: Most 'missing' files are EXCLUDED by SKIP_DIRS on purpose.")
    print("These are in .kimi (skipped entirely), vault (backups), node_modules, etc.")
    print("This is CORRECT behavior - we don't want to index those.")
    print(f"\nREAL gap (scannable files not indexed): {scannable_not_indexed}")
    print(f"These need: python run.py scan --full")
else:
    print("PRIMARY CAUSE: Files are scannable but haven't been indexed yet.")
    print(f"Need: python run.py scan --full to index {scannable_not_indexed} files")
