"""
E2E Integration Test — Phase 0: Embedder → Vector Store → Search

Tests the full dense-only embedding pipeline:
1. Embed texts via sentence-transformers
2. Upsert chunks into Qdrant (with empty sparse dicts)
3. Search via dense vector
4. Search via hybrid (dense-only, sparse gracefully skipped)
5. Verify ranking scores and payload return
6. Cleanup test chunks

Run: python test_e2e_phase0.py
"""

import sys
import os
import logging
import warnings
import pytest

_SWIG_DEPRECATION_MESSAGES = [
    r"builtin type SwigPyPacked has no __module__ attribute",
    r"builtin type SwigPyObject has no __module__ attribute",
    r"builtin type swigvarlink has no __module__ attribute",
]

for message in _SWIG_DEPRECATION_MESSAGES:
    warnings.filterwarnings("ignore", message=message, category=DeprecationWarning)

pytestmark = [
    pytest.mark.filterwarnings(f"ignore:{message}:DeprecationWarning")
    for message in _SWIG_DEPRECATION_MESSAGES
]

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


def run_e2e_embedding_pipeline():
    """Full pipeline: embed → upsert → search → verify → cleanup."""
    results = {}

    # ── Step 1: Import all modules ──────────────────────────────────
    logger.info("[Step 1] Importing modules...")
    try:
        from embedder import get_embedder
        from vector_store import VectorStore

        print("  ✅ All imports OK")
        results["import"] = True
    except Exception as e:
        print(f"  ❌ Import failed: {e}")
        results["import"] = False
        return results

    # ── Step 2: Initialize embedder ─────────────────────────────────
    logger.info("[Step 2] Initializing embedder...")
    try:
        embedder = get_embedder()
        device_info = embedder.get_device_info()
        print(f"  ✅ Embedder created: {device_info}")
        results["embedder_init"] = True
    except Exception as e:
        print(f"  ❌ Embedder init failed: {e}")
        results["embedder_init"] = False
        return results

    # ── Step 3: Encode test texts ───────────────────────────────────
    logger.info("[Step 3] Encoding test texts...")
    test_texts = [
        "Python is a versatile programming language used for web development and data science.",
        "Machine learning models can be trained on large datasets to make predictions.",
        "The quick brown fox jumps over the lazy dog in the backyard.",
        "FileMind is a semantic file indexing and search system for local files.",
        "Local sidecars provide isolated environments for running applications.",
    ]
    try:
        encoded = embedder.encode(test_texts, return_dense=True, return_sparse=True)
        dense_vecs = encoded["dense_vecs"]
        sparse_weights = encoded["lexical_weights"]

        assert len(dense_vecs) == 5, f"Expected 5 vectors, got {len(dense_vecs)}"
        assert len(dense_vecs[0]) == 1024, (
            f"Expected 1024 dims, got {len(dense_vecs[0])}"
        )
        assert len(sparse_weights) == 5, (
            f"Expected 5 sparse entries, got {len(sparse_weights)}"
        )
        assert all(sw == {} for sw in sparse_weights), "Sparse should be empty dicts"

        print("  ✅ Encoded 5 texts → 5 vectors × 1024 dims")
        print("  ✅ Sparse weights: 5 empty dicts (expected for sentence-transformers)")
        results["encode"] = True
    except Exception as e:
        print(f"  ❌ Encoding failed: {e}")
        results["encode"] = False
        return results

    # ── Step 4: Initialize vector store ─────────────────────────────
    logger.info("[Step 4] Initializing vector store...")
    try:
        vs = VectorStore()
        count_before = vs.count()
        print(f"  ✅ Vector store opened, current chunks: {count_before}")
        results["vector_store_init"] = True
    except Exception as e:
        print(f"  ❌ Vector store init failed: {e}")
        results["vector_store_init"] = False
        return results

    # ── Step 5: Upsert test chunks (with empty sparse dicts) ────────
    logger.info("[Step 5] Upserting test chunks...")
    test_chunks = []
    for i, (text, vec) in enumerate(zip(test_texts, dense_vecs)):
        test_chunks.append(
            {
                "id": f"test_e2e::chunk_{i}",
                "file_id": "test_e2e_file.py",
                "chunk_index": i,
                "chunk_hash": f"hash_{i}",
                "content": text,
                "vector": vec,
                "sparse_vector": {},  # Empty — dense-only
                "file_type": ".py",
                "category": "code",
                "mtime": 1712500000.0,
            }
        )

    try:
        upserted = vs.upsert_chunks(test_chunks)
        assert upserted == 5, f"Expected 5 upserted, got {upserted}"
        count_after = vs.count()
        print(f"  ✅ Upserted 5 chunks (total in store: {count_after})")
        results["upsert"] = True
    except Exception as e:
        print(f"  ❌ Upsert failed: {e}")
        results["upsert"] = False
        # If upsert fails due to empty sparse vector validation,
        # we need to know for future work
        import traceback

        traceback.print_exc()
        return results

    # ── Step 6: Dense vector search ─────────────────────────────────
    logger.info("[Step 6] Testing dense vector search...")
    try:
        # Use FileMind query as search vector
        query_encoded = embedder.encode(
            ["What is FileMind used for?"],
            return_dense=True,
            return_sparse=False,
        )
        query_vec = query_encoded["dense_vecs"][0]

        results_dense = vs.search_dense(query_vec, top_k=3)
        print(f"  ✅ Dense search returned {len(results_dense)} results")

        if len(results_dense) > 0:
            top = results_dense[0]
            print(f"    Top hit: '{top.get('content', '')[:80]}...'")
            print(f"    Score: {top.get('_distance', 'N/A')}")
            print(
                f"    Has payload keys: file_id={top.get('file_id')}, category={top.get('category')}"
            )

            # Verify payload fields are present
            assert "content" in top, "Missing content in result"
            assert "file_id" in top, "Missing file_id in result"
            assert "category" in top, "Missing category in result"
            assert "_distance" in top, "Missing _distance score in result"
            print("  ✅ All payload fields present + distance score")
        results["search_dense"] = True
    except Exception as e:
        print(f"  ❌ Dense search failed: {e}")
        results["search_dense"] = False
        import traceback

        traceback.print_exc()

    # ── Step 7: Hybrid search (dense-only, sparse gracefully skipped)
    logger.info("[Step 7] Testing hybrid search (dense + empty sparse)...")
    try:
        query_encoded = embedder.encode(
            ["Python programming language"],
            return_dense=True,
            return_sparse=True,
        )
        query_vec = query_encoded["dense_vecs"][0]
        query_sparse = query_encoded["lexical_weights"][0]  # Empty dict

        results_hybrid = vs.search_hybrid(
            query_text="Python programming language",
            query_vector=query_vec,
            top_k=3,
            sparse_dict=query_sparse,  # Empty — should be skipped
        )
        print(f"  ✅ Hybrid search returned {len(results_hybrid)} results")

        if len(results_hybrid) > 0:
            top = results_hybrid[0]
            print(f"    Top hit: '{top.get('content', '')[:80]}...'")
            print(f"    RRF score: {top.get('_relevance_score', 'N/A')}")
            assert "_relevance_score" in top, "Missing RRF score"
            print("  ✅ RRF score present, empty sparse handled gracefully")
        results["search_hybrid"] = True
    except Exception as e:
        print(f"  ❌ Hybrid search failed: {e}")
        results["search_hybrid"] = False
        import traceback

        traceback.print_exc()

    # ── Step 8: Cleanup test chunks ─────────────────────────────────
    logger.info("[Step 8] Cleaning up test chunks...")
    try:
        deleted = vs.delete_by_file("test_e2e_file.py")
        count_final = vs.count()
        print(f"  ✅ Deleted {deleted} test chunks (total now: {count_final})")
        assert count_final == count_before, (
            f"Count mismatch: expected {count_before}, got {count_final}"
        )
        print("  ✅ Store count matches pre-test count")
        results["cleanup"] = True
    except Exception as e:
        print(f"  ❌ Cleanup failed: {e}")
        results["cleanup"] = False

    return results


def test_e2e_embedding_pipeline():
    """Pytest wrapper for the E2E pipeline."""
    results = run_e2e_embedding_pipeline()
    failed_steps = [step for step, passed in results.items() if not passed]
    assert not failed_steps, f"E2E pipeline failed steps: {', '.join(failed_steps)}"


def main():
    print("=" * 70)
    print("  FileMind Phase 0 — E2E Integration Test")
    print("  Dense-only embedding pipeline (sentence-transformers)")
    print("=" * 70)
    print()

    results = run_e2e_embedding_pipeline()

    print()
    print("=" * 70)
    print("  RESULTS SUMMARY")
    print("=" * 70)

    all_pass = True
    for step, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {step:30s}  {status}")
        if not passed:
            all_pass = False

    print("=" * 70)
    if all_pass:
        print("  🎉 ALL TESTS PASSED — Dense-only pipeline operational")
    else:
        print("  ⚠️  SOME TESTS FAILED — see details above")
    print("=" * 70)

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
