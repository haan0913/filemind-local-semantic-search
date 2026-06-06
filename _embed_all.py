r"""Embed all files with content_summary but no embeddings.

Usage: python C:\AI_STATION\filemind\_embed_all.py
"""
import sys, time, logging
sys.path.insert(0, "C:/AI_STATION")

from filemind.catalog import Catalog
from filemind.chunker import TextChunker
from filemind.embedder import get_embedder
from filemind.vector_store import VectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("embed_all")

def main():
    catalog = Catalog()
    catalog.init_db()
    chunker = TextChunker()
    embedder = get_embedder()
    vs = VectorStore()
    
    # Get all files with content_summary but chunk_count=0
    all_files = catalog.conn.execute(
        "SELECT path, ext, content_summary, category, confidence FROM file_index WHERE chunk_count = 0 AND content_summary IS NOT NULL AND content_summary != ''"
    ).fetchall()

    logger.info(f"Found {len(all_files)} files to embed")

    total_chunks = 0
    total_indexed = 0
    total_errors = 0
    start = time.time()

    for i, (path, ext, content, category, conf) in enumerate(all_files):
        if i % 50 == 0:
            elapsed = time.time() - start
            rate = i / elapsed if elapsed > 0 else 0
            logger.info(f"Progress: {i}/{len(all_files)} ({i/len(all_files)*100:.1f}%) - {rate:.1f} files/sec")

        content = content.strip()
        if not content:
            continue

        try:
            vs.delete_by_file(path)
            chunks = chunker.chunk(content, path)
            if not chunks:
                continue

            texts = [c.content for c in chunks]
            encoded = embedder.encode(texts, return_dense=True, return_sparse=True)
            dense_vecs = encoded.get("dense_vecs", [])
            sparse_vecs = encoded.get("lexical_weights", [{}] * len(chunks))

            records = []
            for j, chunk in enumerate(chunks):
                records.append({
                    "id": f"{path}::chunk_{j}",
                    "file_id": path,
                    "chunk_index": j,
                    "content": chunk.content,
                    "vector": dense_vecs[j] if j < len(dense_vecs) else [],
                    "sparse_vector": sparse_vecs[j] if j < len(sparse_vecs) else {},
                    "file_type": ext or "",
                    "category": category or "unknown",
                    "mtime": 0,
                })

            vs.upsert_chunks(records)
            catalog.update_chunk_count(path, len(chunks))
            total_chunks += len(chunks)
            total_indexed += 1

        except Exception as e:
            total_errors += 1
            if total_errors <= 5:
                logger.error(f"Embed error: {path} - {e}")

    catalog.conn.commit()
    elapsed = time.time() - start
    logger.info(f"DONE: Indexed {total_indexed} files, {total_chunks} chunks, {total_errors} errors in {elapsed:.0f}s")
    catalog.close()

if __name__ == "__main__":
    main()
