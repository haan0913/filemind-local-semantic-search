"""
FileMind REST API
Exposes the FileMind search engine and catalog to the web frontend.
"""

import logging
import os
from typing import Optional, List
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

try:
    from .search import SearchEngine
    from .catalog import Catalog
    from .config import config
    from .vector_store import VectorStore
except ImportError:
    from search import SearchEngine
    from catalog import Catalog
    from config import config
    from vector_store import VectorStore

logger = logging.getLogger(__name__)
DEFAULT_API_PORT = int(os.getenv("FILEMIND_API_PORT", "8072"))

app = FastAPI(title="FileMind Core API")

# Allow Web UI CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FILEMIND_RECOVERY_COMMAND = r"C:\AI_STATION\scripts\start_ai_station_session.ps1"


def _runtime_metadata() -> dict:
    """Return non-secret runtime paths useful for desktop sidecar acceptance."""
    return {
        "ai_station_root": str(getattr(config, "ai_station_root", "")),
        "filemind_dir": str(getattr(config, "filemind_dir", "")),
        "index_dir": str(getattr(config, "index_dir", "")),
        "sqlite_db": str(getattr(config, "sqlite_db", "")),
        "bm25_index_path": str(getattr(config, "bm25_index_path", "")),
        "progress_file": str(getattr(config, "progress_file", "")),
        "log_file": str(getattr(config, "log_file", "")),
        "huggingface_cache_dir": str(getattr(config, "huggingface_cache_dir", "")),
        "model_cache_dir": os.getenv("FILEMIND_MODEL_CACHE_DIR", ""),
        "qdrant_mode": getattr(config, "qdrant_mode", ""),
        "qdrant_url": getattr(config, "qdrant_url", ""),
        "qdrant_collection": getattr(config, "qdrant_collection", ""),
        "api_port": DEFAULT_API_PORT,
    }


def _probe_qdrant_dependency() -> dict:
    """Return a cheap, explicit upstream dependency probe for shared Qdrant."""
    mode = getattr(config, "qdrant_mode", "local").lower()
    if mode != "http":
        return {"status": "not-applicable", "mode": mode}

    qdrant_url = (getattr(config, "qdrant_url", "") or "http://127.0.0.1:6333").rstrip(
        "/"
    )
    ready_url = f"{qdrant_url}/readyz"
    try:
        response = requests.get(ready_url, timeout=2)
    except requests.RequestException as exc:
        return {
            "status": "unavailable",
            "mode": mode,
            "url": ready_url,
            "message": str(exc),
        }
    return {
        "status": "ok" if 200 <= response.status_code < 300 else "unavailable",
        "mode": mode,
        "url": ready_url,
        "http_status": response.status_code,
    }


def _get_vector_count_readonly() -> int:
    """Return the vector count without creating collections in shared Qdrant."""
    mode = getattr(config, "qdrant_mode", "local").lower()
    if mode == "http":
        from qdrant_client import QdrantClient

        qdrant_url = (
            getattr(config, "qdrant_url", "") or "http://127.0.0.1:6333"
        ).rstrip("/")
        collection_name = getattr(config, "qdrant_collection", "file_chunks")
        client = QdrantClient(url=qdrant_url)
        if not client.collection_exists(collection_name):
            return 0
        return int(client.count(collection_name=collection_name, exact=True).count)

    with VectorStore() as vs:
        return int(vs.count())


class SearchResponse(BaseModel):
    results: List[dict]
    query: str
    total_found: int


class DirectoryItem(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: Optional[int] = None
    ext: Optional[str] = None
    category: Optional[str] = None
    confidence: Optional[float] = None
    tier: Optional[str] = None
    mtime: Optional[float] = None


@app.get("/api/search", response_model=SearchResponse)
def api_search(
    q: str = Query(..., description="The search query"),
    k: int = Query(20, description="Top K results"),
    ext: Optional[str] = None,
    cat: Optional[str] = None,
    hyde: bool = False,
    rerank: bool = Query(False, description="Enable cross-encoder reranking"),
):
    """Hybrid search endpoint with FTS and LanceDB Vector support."""
    try:
        with SearchEngine(reranking=rerank) as engine:
            results = engine.search(
                query=q,
                top_k=k,
                file_type=ext,
                category=cat,
                use_hybrid=True,
                use_hyde=hyde,
            )

            # Format results for frontend
            formatted = []
            for r in results:
                formatted.append(
                    {
                        "path": r.file_path,
                        "score": round(r.score, 4),
                        "snippet": r.snippet,
                        "category": r.category,
                        "type": r.file_type,
                        "chunk": r.chunk_index,
                        "mtime": r.mtime,
                        "protected": getattr(r, "is_protected", False),
                    }
                )

            return SearchResponse(
                results=formatted, query=q, total_found=len(formatted)
            )
    except Exception as e:
        logger.error(f"API Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
def api_health():
    """Verify system readiness and name shared Qdrant as the upstream blocker when applicable."""
    qdrant = _probe_qdrant_dependency()
    if qdrant.get("status") == "unavailable":
        return JSONResponse(
            content={
                "status": "degraded",
                "message": "FileMind API degraded: qdrant-shared is unavailable; catalog/exact/BM25 fallback routes may still work.",
                "upstream_dependency": "qdrant-shared",
                "dependency_status": "unavailable",
                "qdrant": qdrant,
                "fallbacks": ["catalog", "exact", "bm25"],
                "recovery": FILEMIND_RECOVERY_COMMAND,
                "runtime": _runtime_metadata(),
            },
            status_code=503,
        )
    try:
        chunks = _get_vector_count_readonly()
        return JSONResponse(
            content={
                "status": "active" if chunks > 0 else "empty",
                "chunks": chunks,
                "upstream_dependency": "qdrant-shared"
                if qdrant.get("status") == "ok"
                else None,
                "dependency_status": qdrant.get("status"),
                "qdrant": qdrant,
                "runtime": _runtime_metadata(),
            },
            status_code=200,
        )
    except Exception as e:
        logger.error("API health failed: %s", e, exc_info=True)
        return JSONResponse(
            content={
                "status": "degraded",
                "message": str(e),
                "upstream_dependency": "qdrant-shared"
                if qdrant.get("status") == "ok"
                else None,
                "dependency_status": qdrant.get("status"),
                "qdrant": qdrant,
                "fallbacks": ["catalog", "exact", "bm25"],
                "recovery": FILEMIND_RECOVERY_COMMAND,
                "runtime": _runtime_metadata(),
            },
            status_code=503,
        )


@app.get("/api/stats")
def api_stats():
    """Retrieve FileMind catalog statistics."""
    try:
        with Catalog() as catalog:
            return catalog.get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/explorer")
def api_explorer(path: str = ""):
    """Virtual directory explorer derived directly from indexed files."""
    try:
        with Catalog() as catalog:
            # We must resolve a virtual tree because we only store full paths
            # To optimize, we'll fetch all files matching the prefix path
            rows = catalog.conn.execute(
                "SELECT path, size, mtime, ext, category, confidence, tier FROM file_index"
            ).fetchall()

            items_map = {}
            for row in rows:
                full_path = row["path"]
                if not full_path:
                    continue

                # Check if it falls under the requested path
                if path and not full_path.startswith(path):
                    continue

                # Strip the prefix to find immediate children
                rel = full_path[len(path) :].lstrip("/")
                if not rel:
                    continue  # It is the exact file

                parts = rel.split("/")
                child_name = parts[0]
                is_file = len(parts) == 1

                if child_name not in items_map:
                    items_map[child_name] = {
                        "name": child_name,
                        "path": f"{path}/{child_name}".strip("/"),
                        "is_dir": not is_file,
                    }
                    if is_file:
                        items_map[child_name].update(
                            {
                                "size": row["size"],
                                "mtime": row["mtime"],
                                "ext": row["ext"],
                                "category": row["category"],
                                "confidence": row["confidence"],
                                "tier": row["tier"],
                            }
                        )
                else:
                    items_map[child_name]["is_dir"] = True  # It has sub-items

            return list(items_map.values())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
def api_chat(prompt: str = Query(...)):
    """LLM Proxy that intercepts the frontend query, performs RAG, and talks to Gemma."""
    import requests

    # 1. Fetch FileMind Context
    try:
        with SearchEngine() as engine:
            top_results = engine.search(query=prompt, top_k=5, use_hybrid=True)
            context = "\n".join(
                [f"FILE: {r.file_path}\nCONTENT: {r.snippet}" for r in top_results]
            )
    except Exception:
        context = ""

    system_prompt = f"You are FileMind, a local AI assistant. Use the following personal files to accurately and directly answer the user. Do not explain your process.\n\n[LOCAL REPOSITORY CONTEXT]\n{context}"

    # 2. Proxy to Ollama
    payload = {
        "model": config.classification_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }

    try:
        res = requests.post(
            f"{config.ollama_api_url}/api/chat", json=payload, timeout=60
        )
        res.raise_for_status()
        return {"response": res.json().get("message", {}).get("content", "")}
    except Exception as e:
        logger.error(f"Chat failed: {e}")
        raise HTTPException(status_code=500, detail="Local LLM failed to respond.")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="127.0.0.1", port=DEFAULT_API_PORT, reload=True)
