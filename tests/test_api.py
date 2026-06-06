from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from filemind import api as api_module


class _DummyEngine:
    instances: list[bool] = []

    def __init__(self, reranking: bool = False):
        self.reranking = reranking
        self.__class__.instances.append(reranking)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def search(self, **_: object):
        return [
            SimpleNamespace(
                file_path="hub/docs/context/CURRENT_CONTEXT_STATUS.md",
                score=0.91,
                snippet="Current context status",
                category="documentation",
                file_type=".md",
                chunk_index=0,
                mtime=0.0,
            )
        ]


class _QdrantReadyResponse:
    status_code = 200


class FileMindApiTests(TestCase):
    def setUp(self) -> None:
        _DummyEngine.instances.clear()
        self.client = TestClient(api_module.app)

    def test_search_defaults_to_no_rerank(self) -> None:
        with patch.object(api_module, "SearchEngine", _DummyEngine):
            response = self.client.get("/api/search", params={"q": "atlas"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(_DummyEngine.instances, [False])

    def test_search_can_opt_in_to_rerank(self) -> None:
        with patch.object(api_module, "SearchEngine", _DummyEngine):
            response = self.client.get(
                "/api/search", params={"q": "atlas", "rerank": "true"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(_DummyEngine.instances, [True])

    def test_health_returns_degraded_when_vector_count_fails(self) -> None:
        with (
            patch.object(
                api_module,
                "_get_vector_count_readonly",
                side_effect=RuntimeError("qdrant unavailable"),
            ),
            patch.object(
                api_module.requests, "get", return_value=_QdrantReadyResponse()
            ),
        ):
            response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "degraded")
        self.assertEqual(response.json()["dependency_status"], "ok")
        self.assertIn("catalog", response.json()["fallbacks"])

    def test_health_returns_ok_payload_when_vector_count_is_available(self) -> None:
        with (
            patch.object(api_module, "_get_vector_count_readonly", return_value=7),
            patch.object(
                api_module.requests, "get", return_value=_QdrantReadyResponse()
            ),
        ):
            response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "active")
        self.assertEqual(payload["chunks"], 7)
        self.assertEqual(payload["upstream_dependency"], "qdrant-shared")
        self.assertEqual(payload["dependency_status"], "ok")
        self.assertIn("runtime", payload)
        self.assertIn("index_dir", payload["runtime"])

    def test_health_names_qdrant_when_upstream_is_unavailable(self) -> None:
        with patch.object(
            api_module.requests,
            "get",
            side_effect=api_module.requests.RequestException("connection refused"),
        ):
            response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["upstream_dependency"], "qdrant-shared")
        self.assertEqual(payload["dependency_status"], "unavailable")
        self.assertIn("bm25", payload["fallbacks"])
        self.assertIn("start_ai_station_session.ps1", payload["recovery"])
        self.assertIn("runtime", payload)
        self.assertIn("log_file", payload["runtime"])
