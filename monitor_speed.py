#!/usr/bin/env python3
"""Monitor pipeline speed and forecast completion."""
import sys, sqlite3, time
sys.path.insert(0, 'C:/AI_STATION/filemind')
from config import config

DB_PATH = str(config.sqlite_db)
START_TIME = 1743926528  # 05:42:08 epoch (approx)
TOTAL_FILES = 3227

print("=== FileMind Pipeline Speed Monitor ===")

# First check
conn = sqlite3.connect(DB_PATH)
c1 = conn.execute('SELECT COUNT(*) FROM file_index').fetchone()[0]
conn.close()
now1 = time.time()
print(f"[00:00] Files in DB: {c1}")

time.sleep(30)

# Second check
conn = sqlite3.connect(DB_PATH)
c2 = conn.execute('SELECT COUNT(*) FROM file_index').fetchone()[0]
conn.close()
now2 = time.time()

elapsed = now2 - now1
diff = c2 - c1

print(f"[00:30] Files in DB: {c2} (+{diff} in 30s)")
print()

if diff > 0:
    rate = diff / elapsed  # files per second
    remaining = TOTAL_FILES - c2
    eta_seconds = remaining / rate
    eta_minutes = eta_seconds / 60
    eta_hours = eta_minutes / 60

    print(f"Classification rate: {rate:.3f} files/sec ({rate*60:.1f} files/min)")
    print(f"Files remaining: {remaining}")
    print(f"Estimated time to completion: {eta_minutes:.1f} minutes ({eta_hours:.1f} hours)")
    print(f"Batch size: 5 files per API call")
    print(f"Approx time per batch: {5/rate:.1f} seconds")
else:
    print("WARNING: No progress in 30 seconds. Pipeline may be stuck on first batch.")
    print("gemma4-e4b-json in thinking mode can take 30-90 seconds per batch.")
    print("Estimated: 3227/5 batches = 645 batches")
    print(f"At 30s/batch: {645*30/60:.0f} minutes = {645*30/3600:.1f} hours")
    print(f"At 45s/batch: {645*45/60:.0f} minutes = {645*45/3600:.1f} hours")
    print(f"At 60s/batch: {645*60/60:.0f} minutes = {645*60/3600:.1f} hours")
    print(f"At 90s/batch: {645*90/60:.0f} minutes = {645*90/3600:.1f} hours")