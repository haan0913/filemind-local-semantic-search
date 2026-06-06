import sqlite3

try:
    from .config import config
except ImportError:
    from config import config

conn = sqlite3.connect(str(config.sqlite_db))
total = conn.execute('SELECT COUNT(*) FROM file_index').fetchone()[0]
categorized = conn.execute("SELECT COUNT(*) FROM file_index WHERE category IS NOT NULL AND category != ''").fetchone()[0]
with_embeddings = conn.execute('SELECT COUNT(*) FROM file_index WHERE chunk_count > 0').fetchone()[0]
unknown = conn.execute("SELECT COUNT(*) FROM file_index WHERE category = 'unknown'").fetchone()[0]
print(f'Total: {total}')
print(f'Categorized: {categorized}')
print(f'With embeddings: {with_embeddings}')
print(f'Unknown: {unknown}')
print()
rows = conn.execute("SELECT category, COUNT(*) as cnt FROM file_index WHERE category IS NOT NULL AND category != '' GROUP BY category ORDER BY cnt DESC").fetchall()
for r in rows:
    print(f'  {r[0]}: {r[1]}')
conn.close()
