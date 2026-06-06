import sys
sys.path.insert(0, 'C:/AI_STATION/filemind')
from catalog import Catalog

c = Catalog()
c.init_db()
total = c.count()
print(f'Total files in DB: {total}')

if total > 0:
    rows = c.conn.execute('SELECT path, category, confidence, ext, chunk_count FROM file_index ORDER BY rowid LIMIT 5').fetchall()
    print(f'\n{"="*70}')
    print(f'FIRST 5 FILES FULLY PROCESSED THROUGH PIPELINE')
    print(f'{"="*70}')
    for i, r in enumerate(rows):
        print(f'\n{i+1}. {r[0]}')
        print(f'   Category: {r[1]} | Confidence: {r[2]:.2f} | Type: {r[3]} | Chunks: {r[4]}')
    
    categories = c.conn.execute('SELECT category, COUNT(*) as cnt FROM file_index GROUP BY category ORDER BY cnt DESC').fetchall()
    print(f'\n\n{"="*70}')
    print(f'CATEGORY BREAKDOWN ({total} files)')
    print(f'{"="*70}')
    for r in categories:
        print(f'  {r["category"]}: {r["cnt"]}')

c.close()

# Check if background process still running
import subprocess
try:
    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq python.exe'], capture_output=True, text=True)
    count = result.stdout.count('python.exe')
    print(f'\n\nPython processes running: {count}')
except:
    pass