from catalog import Catalog
c = Catalog()
c.init_db()
stats = c.get_stats()
print(f"Total files in catalog: {stats.get('total_files', 'N/A')}", flush=True)
print()
print("Categories:", flush=True)
for cat, count in sorted(stats.get('categories', {}).items(), key=lambda x: -x[1]):
    print(f"  {cat}: {count}", flush=True)
c.close()
