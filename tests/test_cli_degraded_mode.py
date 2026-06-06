from __future__ import annotations

from types import SimpleNamespace

from filemind import run as run_module


def test_cli_health_reports_degraded_qdrant_without_traceback(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        run_module,
        "_probe_qdrant_dependency",
        lambda: {
            "status": "unavailable",
            "mode": "http",
            "url": "http://127.0.0.1:1/readyz",
            "message": "connection refused",
        },
    )
    monkeypatch.setattr(
        run_module, "_get_catalog_health", lambda: {"status": "ok", "count": 42}
    )
    monkeypatch.setattr(
        run_module, "_get_ollama_api_status", lambda: {"status": "ok", "code": 200}
    )
    monkeypatch.setattr(
        run_module, "_get_gpu_status", lambda: {"status": "not available (CPU only)"}
    )
    monkeypatch.setattr(
        run_module,
        "_get_embedding_runtime_status",
        lambda: {"status": "ok", "device": "cpu"},
    )
    monkeypatch.setattr(
        run_module, "_get_ollama_runtime_status", lambda: {"status": "idle"}
    )

    run_module.cmd_health(SimpleNamespace())

    output = capsys.readouterr().out
    assert "[WARN] vector_store: degraded" in output
    assert "qdrant-shared" in output
    assert "catalog/exact/BM25 search fallbacks remain usable" in output
    assert "Traceback" not in output
