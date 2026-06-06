r"""FileMind Pipeline Monitor — Check KPIs every 30 seconds.

Usage: python C:\AI_STATION\filemind\_monitor.py
Press Ctrl+C to stop.
"""
import os
import sqlite3
import time
from typing import Any

try:
    from .config import config
except ImportError:
    from config import config

DB = str(config.sqlite_db)
LOG = str(config.log_file)
CHECK_INTERVAL = 30

def check_db() -> dict[str, Any]:
    if not os.path.exists(DB):
        return {"error": "DB not found"}

    conn = sqlite3.connect(DB)
    total = int(conn.execute("SELECT COUNT(*) FROM file_index").fetchone()[0])
    unknown = int(
        conn.execute(
            "SELECT COUNT(*) FROM file_index WHERE category = 'unknown'"
        ).fetchone()[0]
    )
    classified = total - unknown
    with_embed = int(
        conn.execute("SELECT COUNT(*) FROM file_index WHERE chunk_count > 0").fetchone()[
            0
        ]
    )

    categories: dict[str, int] = {}
    rows = conn.execute(
        "SELECT category, COUNT(*) FROM file_index WHERE category IS NOT NULL AND category != 'unknown' GROUP BY category"
    ).fetchall()
    for cat, cnt in rows:
        categories[cat] = cnt

    conn.close()
    return {
        "total": total,
        "unknown": unknown,
        "classified": classified,
        "pct": round(classified / total * 100, 1) if total > 0 else 0,
        "with_embed": with_embed,
        "categories": categories,
    }

def check_log() -> str | list[str]:
    if not os.path.exists(LOG):
        return "No classify log yet"
    
    try:
        with open(LOG, "r", encoding="utf-8") as f:
            content = f.read()
        lines = content.strip().split("\n")
        
        # Last few meaningful lines
        info_lines = [l for l in lines if "classifier" in l.lower() or "classified" in l.lower() or "error" in l.lower()]
        return info_lines[-5:] if info_lines else ["No classifier output yet"]
    except Exception as e:
        return f"Error reading log: {e}"

last_classified = 0

def main() -> None:
    global last_classified
    print("=" * 70)
    print("FileMind Pipeline Monitor")
    print("=" * 70)
    
    while True:
        try:
            stats = check_db()
            log_lines = check_log()
            
            if "error" in stats:
                print(f"\nERROR: {stats['error']}")
                time.sleep(CHECK_INTERVAL)
                continue
            
            # Calculate progress since last check
            delta = stats["classified"] - last_classified
            last_classified = stats["classified"]
            
            print(f"\n{'='*70}")
            print(f"time: {time.strftime('%H:%M:%S')}")
            print(f"  Total: {stats['total']}")
            print(f"  Classified: {stats['classified']} ({stats['pct']}%) | Delta: +{delta}")
            print(f"  Unknown: {stats['unknown']}")
            print(f"  With Embeddings: {stats['with_embed']}")
            print()
            for cat, cnt in sorted(stats["categories"].items(), key=lambda x: -x[1]):
                print(f"    {cat}: {cnt}")
            print()
            print(f"  Recent log:")
            for line in (log_lines if isinstance(log_lines, list) else [log_lines]):
                print(f"    {line}")
            
            # Status check
            if stats["unknown"] == 0:
                print("\nDONE: All files classified!")
                break
            
        except KeyboardInterrupt:
            print("\n\nMonitor stopped by user")
            break
        except Exception as e:
            print(f"\nError: {e}")
        
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
