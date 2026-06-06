import sys
sys.path.insert(0, 'C:/AI_STATION/filemind')
from catalog import Catalog

c = Catalog()
c.init_db()

print('=== Indexed file extensions ===')
rows = c.conn.execute('SELECT ext, COUNT(*) as cnt FROM file_index GROUP BY ext ORDER BY cnt DESC').fetchall()
for r in rows:
    print(f'  {r["ext"]:>12}  {r["cnt"]:>6,}')

total = c.count()
print(f'\nTotal indexed: {total}')

print('\n=== Last scan log ===')
history = c.get_scan_history(5)
for h in history:
    print(f'  ID {h["id"]}: scanned={h["files_scanned"]} new={h["files_new"]} changed={h["files_changed"]} deleted={h["files_deleted"]} errors={h["errors"]} status={h["status"]}')

# Compare with what scan_logger found on disk
import json
with open('docs/scan_report_20260408_144212.json') as f:
    scan = json.load(f)

print(f'\n=== Disk vs Index Gap ===')
print(f'Files on disk (scan): {scan["summary"]["total_files"]}')
print(f'Files in index:       {total}')
print(f'Gap:                  {scan["summary"]["total_files"] - total}')

# Breakdown by extension
print(f'\n=== Extension breakdown (disk) ===')
for ext, count in sorted(scan["top_15_extensions"].items(), key=lambda x: x[1], reverse=True):
    print(f'  {ext:>12}  {count:>6,}')

print(f'\n=== What scan_logger indexes vs what filemind run.py indexes ===')
print(f'scan_logger.py scans: all files matching INDEX_EXTENSIONS in config.py')
print(f'run.py scan indexes:  files that pass SKIP_DIRS check + content extraction + embedding')
print(f'The gap could be: (1) files skipped by SKIP_DIRS, (2) files too large, (3) files from scan roots not in catalog')

# Check SKIP_DIRS coverage
from config import SKIP_DIRS, SKIP_SUBDIRS, SCAN_ROOTS, INDEX_EXTENSIONS
print(f'\n=== Config ===')
print(f'SCAN_ROOTS: {len(SCAN_ROOTS)} roots')
print(f'SKIP_DIRS: {SKIP_DIRS}')
print(f'SKIP_SUBDIRS: {SKIP_SUBDIRS}')
print(f'INDEX_EXTENSIONS: {len(INDEX_EXTENSIONS)} types')

c.close()
