"""Quick embed: use content_summary as single-chunk for each file.

All files have content_summary (truncated to 500 chars). Instead of
chunking (which requires 512+ words), we embed each file's 
content_summary directly as a single vector.
"""
import sys, time, logging
sys.path.insert(0, "C:/AI_STATION")

from filemind.catalog import Catalog
from filemind.embedder import get_embedder
from filemind.vector_store import VectorStore

logging.basicConfig(level=logging.INFO, 
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("quick_embed")

def main():
    catalog = Catalog()
    catalog.init_db()
    vs = VectorStore()
    embedder = get_embedder()
    
    # Get all files with content_summary but no chunks
    files = catalog.conn.execute(
        "SELECT path, ext, content_summary, category, mtime "
        "FROM file_index WHERE chunk_count = 0 "
        "AND content_summary IS NOT NULL AND content_summary != ''"
    ).fetchall()
    
    logger.info(f"Found {len(files)} files to embed")
    
    total = 0
    errors = 0
    start = time.time()
    batch_texts = []
    batch_files = []
    
    for i, (path, ext, content, category, mtime) in enumerate(files):
        content = content.strip()
        if not content:
            continue
        
        batch_texts.append(content)
        batch_files.append((path, ext, category, mtime))
        
        # Embed in batches of 64
        if len(batch_texts) >= 64:
            total += _embed_batch(embedder, vs, batch_files, batch_texts)
            batch_texts = []
            batch_files = []
        
        if (i + 1) % 500 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            logger.info(f"Progress: {i+1}/{len(files)} ({(i+1)/len(files)*100:.1f}%) - {rate:.1f} files/sec")
    
    # Final batch
    if batch_texts:
        total += _embed_batch(embedder, vs, batch_files, batch_texts)
    
    catalog.conn.commit()
    elapsed = time.time() - start
    logger.info(f"DONE: {total} files embedded, {errors} errors in {elapsed:.0f}s")
    vs.close()
    catalog.close()

def _embed_batch(embedder, vs, file_infos, texts):
    """Embed a batch of texts and upsert to vector store."""
    try:
        encoded = embedder.encode(texts, return_dense=True, return_sparse=True)
        dense_vecs = encoded.get("dense_vecs", [])
        sparse_vecs = encoded.get("lexical_weights", [{}] * len(texts))
        
        records = []
        for i, (path, ext, category, mtime) in enumerate(file_infos):
            records.append({
                "id": f"{path}::chunk_0",
                "file_id": path,
                "chunk_index": 0,
                "content": texts[i][:500],
                "vector": dense_vecs[i] if i < len(dense_vecs) else [],
                "sparse_vector": sparse_vecs[i] if i < len(sparse_vecs) else {},
                "file_type": ext or "",
                "category": category or "unknown",
                "mtime": float(mtime or 0),
            })
        
        vs.upsert_chunks(records)
        
        # Update catalog chunk_count = 1
        from filemind.catalog import Catalog
        c = Catalog()
        c.init_db()
        for path, _, _, _ in file_infos:
            c.update_chunk_count(path, 1)
        c.conn.commit()
        c.close()
        
        return len(records)
    except Exception as e:
        logger.error(f"Batch embed failed: {e}")
        return 0

if __name__ == "__main__":
    main()