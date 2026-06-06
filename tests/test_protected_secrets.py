from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from filemind.extractor import extract_content
from filemind.scanner import FileScanner
from filemind.protected_secrets import (
    NotebookLMSecretSourceError,
    ProtectedSecretAccessError,
    assert_notebooklm_source_allowed,
    contains_secret_value,
    is_secret_like_path,
    lookup_protected_secrets,
    redact_secret_text,
)
from filemind import search as search_module


FAKE_SECRET = "sk-fake000000000000000000000000"


def test_redact_secret_assignments_and_tokens() -> None:
    text = f"OPENAI_API_KEY={FAKE_SECRET}\nPUBLIC_VALUE=ok\n"

    redacted = redact_secret_text(text)

    assert FAKE_SECRET not in redacted
    assert "OPENAI_API_KEY=[REDACTED_SECRET]" in redacted
    assert "PUBLIC_VALUE=ok" in redacted


def test_redact_human_labeled_bearer_token_and_client_secret() -> None:
    bearer = "AAAAAAAAAAAAAAAAAAAAAGIy8wEAAAAAAxuJeTkUNvlYvr3tjym7VjsW7Y4%3DmJ0BXZc6J3BvUl8uNKXpvPbK6nXiR8K1mm0jk934XwJiG7wz52"
    client_secret = "fiPl48XJHHuQiR3u7Vf7zI9u2xN8qP41"
    text = f"- Bearer token: {bearer}\n- Client secret: {client_secret}\n"

    redacted = redact_secret_text(text)

    assert bearer not in redacted
    assert client_secret not in redacted
    assert "Bearer token: [REDACTED_SECRET]" in redacted
    assert "Client secret: [REDACTED_SECRET]" in redacted
    assert contains_secret_value(text)
    assert not contains_secret_value(redacted)


def test_extractor_redacts_env_values_before_indexing(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"SERVICE_TOKEN={FAKE_SECRET}\n", encoding="utf-8")

    extracted = extract_content(str(env_file))

    assert FAKE_SECRET not in extracted
    assert "SERVICE_TOKEN=[REDACTED_SECRET]" in extracted


def test_scanner_treats_env_dotfiles_as_indexable_config() -> None:
    scanner = FileScanner()

    assert scanner._index_extension(".env") == ".env"
    assert scanner._index_extension(".env.local") == ".env"
    assert ".env" in scanner.cfg.index_extensions


def test_normal_search_redacts_protected_snippets() -> None:
    class DummyCatalog:
        def init_db(self) -> None:
            return None

        def close(self) -> None:
            return None

    class DummyVectorStore:
        def search_hybrid(self, *_args, **_kwargs):
            return [
                {
                    "file_id": ".env",
                    "chunk_index": 0,
                    "content": f"PAYMENT_TOKEN={FAKE_SECRET}",
                    "file_type": ".env",
                    "category": "config",
                    "_relevance_score": 0.95,
                }
            ]

        def close(self) -> None:
            return None

    class DummyEmbedder:
        def encode(self, *_args, **_kwargs):
            return {"dense_vecs": [[0.1]], "lexical_weights": [{}]}

    class DummyBm25:
        is_built = False

    engine = search_module.SearchEngine(
        catalog=cast(Any, DummyCatalog()),
        vector_store=cast(Any, DummyVectorStore()),
        bm25_index=cast(Any, DummyBm25()),
        reranking=False,
    )
    engine._embedder = cast(Any, DummyEmbedder())

    result = engine.search("payment token", top_k=1)[0]

    assert result.is_protected
    assert FAKE_SECRET not in result.snippet
    assert "PROTECTED_SECRET" in result.snippet


def test_protected_lookup_requires_explicit_reveal(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"SERVICE_TOKEN={FAKE_SECRET}\n", encoding="utf-8")

    redacted = lookup_protected_secrets([tmp_path], "SERVICE")

    assert len(redacted) == 1
    assert redacted[0].path.endswith(".env")
    assert FAKE_SECRET not in redacted[0].redacted_snippet
    assert not redacted[0].revealed

    with pytest.raises(ProtectedSecretAccessError):
        lookup_protected_secrets([tmp_path], "SERVICE", reveal=True)

    revealed = lookup_protected_secrets(
        [tmp_path],
        "SERVICE",
        reveal=True,
        explicit_local_disclosure=True,
    )
    assert revealed[0].revealed
    assert FAKE_SECRET in revealed[0].revealed_text


def test_notebooklm_source_guard_rejects_secret_paths_and_content(
    tmp_path: Path,
) -> None:
    assert is_secret_like_path(tmp_path / "service-key.txt")

    with pytest.raises(NotebookLMSecretSourceError):
        assert_notebooklm_source_allowed(tmp_path / ".env")

    with pytest.raises(NotebookLMSecretSourceError):
        assert_notebooklm_source_allowed(tmp_path / "notes.md", f"TOKEN={FAKE_SECRET}")

    assert_notebooklm_source_allowed(
        tmp_path / "architecture.md", "public design notes"
    )
