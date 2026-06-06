import sys
sys.path.insert(0, 'C:/AI_STATION/filemind')
from catalog import Catalog
c = Catalog()
c.init_db()
total = c.count()
stats = c.get_stats()
print(f"Total indexed: {total}")
print(f"Categories: {stats['categories']}")

unknowns = c.conn.execute("SELECT path, ext FROM file_index WHERE category = 'unknown' LIMIT 10").fetchall()
print(f"\nUnknown files sample ({len(unknowns)} shown):")
for r in unknowns:
    print(f"  {r[1]:>8}  {r[0]}")

c.close()
