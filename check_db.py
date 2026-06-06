import sqlite3
import sys

try:
    from .config import config
except ImportError:
    from config import config

stdout_reconfigure = getattr(sys.stdout, "reconfigure", None)
if callable(stdout_reconfigure):
    stdout_reconfigure(errors="replace")

conn = sqlite3.connect(str(config.sqlite_db))
conn.execute('PRAGMA read_uncommitted=1')
conn.row_factory = sqlite3.Row

total = conn.execute('SELECT COUNT(*) FROM file_index').fetchone()[0]
print(f'Total files in DB (including uncommitted): {total}')

cats = conn.execute('SELECT category, COUNT(*) as cnt FROM file_index GROUP BY category ORDER BY cnt DESC').fetchall()
print('\nCategory breakdown:')
for r in cats:
    print(f'  {r["category"]}: {r["cnt"]}')

rows = conn.execute('SELECT path, category, confidence, ext, chunk_count, content_summary FROM file_index ORDER BY RANDOM() LIMIT 15').fetchall()
print(f'\nRandom sample of {len(rows)} files:')
for i, r in enumerate(rows):
    summary = (r["content_summary"] or "")[:150].replace('\n', ' ')
    print(f'{i+1}. {r["path"][:75]}')
    print(f'   Cat: {r["category"]} | Conf: {r["confidence"]:.2f} | Type: {r["ext"]} | Chunks: {r["chunk_count"]}')
    print(f'   Summary: {summary}')
    print()

conn.close()
