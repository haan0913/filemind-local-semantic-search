from argparse import Namespace
from pathlib import Path

from filemind.sidecar import configure_sidecar_environment


def test_sidecar_configures_app_owned_paths(tmp_path, monkeypatch):
    monkeypatch.delenv("AI_STATION_ROOT", raising=False)
    args = Namespace(
        app_data=tmp_path / "FileMindAppData",
        ai_station_root=None,
        qdrant_url="http://127.0.0.1:1",
        host="127.0.0.1",
        port=18072,
        log_level="INFO",
    )

    configured = configure_sidecar_environment(args)

    assert Path(configured["FILEMIND_APP_DATA_DIR"]).is_dir()
    assert Path(configured["FILEMIND_INDEX_DIR"]).is_dir()
    assert Path(configured["AI_STATION_ROOT"]).is_dir()
    assert Path(configured["FILEMIND_SIDECAR_LOG_FILE"]).parent.is_dir()
    assert configured["FILEMIND_INDEX_DIR"].startswith(str(args.app_data.resolve()))
    assert configured["FILEMIND_QDRANT_MODE"] == "http"
    assert configured["FILEMIND_QDRANT_URL"] == "http://127.0.0.1:1"
    assert Path(configured["FILEMIND_MODEL_CACHE_DIR"]).is_dir()
    assert Path(configured["HF_HOME"]).is_dir()
    assert Path(configured["HF_HUB_CACHE"]).is_dir()
    assert Path(configured["SENTENCE_TRANSFORMERS_HOME"]).is_dir()
    assert Path(configured["TORCH_HOME"]).is_dir()
    assert configured["FILEMIND_MODEL_CACHE_DIR"].startswith(
        str(args.app_data.resolve())
    )
    assert configured["HF_HOME"].startswith(str(args.app_data.resolve()))
