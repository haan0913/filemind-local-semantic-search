#!/usr/bin/env python
"""Live pipeline monitor - run in terminal to see real-time progress."""
import os
import sqlite3
import time

try:
    from .config import config
except ImportError:
    from config import config

DB = str(config.sqlite_db)

def get_status():
    if not os.path.exists(DB):
        return 0, 0

    c = sqlite3.connect(DB)
    total = c.execute("SELECT COUNT(*) FROM file_index").fetchone()[0]
    classified = c.execute("SELECT COUNT(*) FROM file_index WHERE category != 'unknown'").fetchone()[0]
    embedded = c.execute("SELECT COUNT(*) FROM file_index WHERE chunk_count > 0").fetchone()[0]
    top_cats = c.execute("SELECT category, COUNT(*) as cnt FROM file_index WHERE category != 'unknown' GROUP BY category ORDER BY cnt DESC").fetchall()
    c.close()
    return total, classified, embedded, top_cats

last_total = 0
last_classified = 0
start_time = time.time()

while True:
    try:
        result = get_status()
        if len(result) == 4:
            total, classified, embedded, top_cats = result
        else:
            total = 0
            classified = 0
            embedded = 0
            top_cats = []

        elapsed = time.time() - start_time
        speed = classified / max(elapsed, 1) if classified > 0 else 0.0

        # Clear screen and show progress
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=" * 60)
        print(f" FILEMIND PIPELINE LIVE MONITOR (elapsed: {elapsed:.0f}s)")
        print("=" * 60)
        print(f" Files in DB:     {total}")
        print(f" Classified:      {classified}/{total} ({classified*100//max(total,1)}%)")
        print(f" Embedded:        {embedded}/{total} ({embedded*100//max(total,1)}%)")

        if classified > 0 and embedded == 0:
            remaining = (total - classified) / max(speed, 0.001)
            print(f" Speed:           {speed:.1f} files/sec")
            print(f" Est. remaining:  {remaining/60:.0f} min ({remaining/3600:.1f} hr)")
        elif embedded > 0 and classified == total:
            print(f" Phase:            EMBEDDING (4/5)")

        if classified < total:
            print(f" Phase:            CLASSIFYING (3/5)")
        if embedded == total:
            print(f" Phase:            DONE (5/5)")

        # Category breakdown
        if top_cats:
            print(f"\n Categories:")
            for cat, cnt in top_cats:
                bar = '#' * min(cnt // 10, 40)
                print(f"   {cat:15s}: {cnt:4d} {bar}")

        # Speed change tracking
        if last_classified > 0 and classified > last_classified:
            delta = classified - last_classified
            delta_t = time.time() - (start_time + elapsed - delta / max(speed, 0.001))
            if delta_t > 0:
                print(f"\n Last batch speed: {delta/delta_t:.1f} files/sec")

        last_total = total
        last_classified = classified
        print(f"\n Refreshing every 10s... (Ctrl+C to exit)")
        time.sleep(10)

    except KeyboardInterrupt:
        print("\nMonitor stopped.")
        break
    except Exception as e:
        print(f"\n Error: {e} (retrying in 5s)")
        time.sleep(5)
