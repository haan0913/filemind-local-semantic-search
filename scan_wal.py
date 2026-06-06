import sqlite3
import os

try:
    from .config import config
except ImportError:
    from config import config

DB_PATH = str(config.sqlite_db)

# Try to connect directly to the WAL file
if os.path.exists(DB_PATH):
    # Use read_uncommitted pragma
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA read_uncommitted=1')
    conn.execute('PRAGMA journal_mode=WAL')
    conn.row_factory = sqlite3.Row
    
    try:
        total = conn.execute('SELECT COUNT(*) FROM file_index').fetchone()[0]
        print(f'Files in DB (committed+uncommitted): {total}')
        
        if total > 0:
            rows = conn.execute('SELECT path, category, confidence, ext, chunk_count FROM file_index ORDER BY rowid LIMIT 10').fetchall()
            print(f'\n{"="*70}')
            print(f'SAMPLE OF 10 FILES IN PIPELINE')
            print(f'{"="*70}')
            for i, r in enumerate(rows):
                print(f'{i+1}. {r[0][:65]}')
                print(f'   Cat: {r[1]} | Conf: {r[2]:.2f} | Type: {r[3]} | Chunks: {r[4]}')
            
            cats = conn.execute('SELECT category, COUNT(*) as cnt FROM file_index GROUP BY category ORDER BY cnt DESC').fetchall()
            print(f'\nCategory breakdown:')
            for r in cats:
                print(f'  {r["category"]}: {r["cnt"]}')
        else:
            print('No files in database yet - pipeline still in pre-commit phase')
    except Exception as e:
        print(f'Error: {e}')
    
    conn.close()
else:
    print('Database not found')
