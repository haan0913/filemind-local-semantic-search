import sys, sqlite3
sys.path.insert(0, 'C:/AI_STATION/filemind')
from config import config
from catalog import Catalog

print(f"DB path: {config.sqlite_db}")
conn = sqlite3.connect(str(config.sqlite_db))
cursor = conn.cursor()
total = cursor.execute('SELECT COUNT(*) FROM file_index').fetchone()[0]
print(f"Direct count: {total}")
if total > 0:
    sample = cursor.execute('SELECT path, category, chunk_count FROM file_index LIMIT 3').fetchall()
    for r in sample:
        print(f"  {r[0]} -> cat={r[1]} chunks={r[2]}")
conn.close()
print()

c = Catalog()
c.init_db()
total = c.count()
categorized = c.conn.execute('SELECT COUNT(*) FROM file_index WHERE category IS NOT NULL AND category != ""').fetchone()[0]
emb = c.conn.execute('SELECT COUNT(*) FROM file_index WHERE chunk_count > 0').fetchone()[0]
unknown = c.conn.execute('SELECT COUNT(*) FROM file_index WHERE category = "unknown"').fetchone()[0]

print(f'Total: {total}')
print(f'Categorized: {categorized}')
print(f'Unknown: {unknown}')
print(f'With embeddings: {emb}')

cats = c.conn.execute('SELECT category, COUNT(*) as cnt FROM file_index GROUP BY category ORDER BY cnt DESC').fetchall()
if cats:
    print('\nCategory breakdown:')
    for r in cats:
        print(f'  {r["category"]}: {r["cnt"]}')

c.close()