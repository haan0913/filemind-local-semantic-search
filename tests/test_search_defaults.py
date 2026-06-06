"""Regression tests for config-driven search defaults."""

from filemind import search as search_module


class RecordingSearchEngine:
    instances = []

    def __init__(self, reranking=False):
        self.reranking = reranking
        self.calls = []
        self.closed = False
        self.__class__.instances.append(self)

    def search(self, query, top_k, file_type=None, category=None, use_hyde=False):
        self.calls.append(
            {
                "query": query,
                "top_k": top_k,
                "file_type": file_type,
                "category": category,
                "use_hyde": use_hyde,
            }
        )
        return []

    def close(self):
        self.closed = True


def test_hybrid_search_uses_configured_default_top_k(monkeypatch):
    RecordingSearchEngine.instances.clear()
    monkeypatch.setattr(search_module.config.search, "default_top_k", 7)
    monkeypatch.setattr(search_module, "SearchEngine", RecordingSearchEngine)

    search_module.hybrid_search("smoke")

    engine = RecordingSearchEngine.instances[-1]
    assert engine.calls[0]["top_k"] == 7
    assert engine.closed


def test_hybrid_search_top_k_override_wins(monkeypatch):
    RecordingSearchEngine.instances.clear()
    monkeypatch.setattr(search_module.config.search, "default_top_k", 7)
    monkeypatch.setattr(search_module, "SearchEngine", RecordingSearchEngine)

    search_module.hybrid_search("smoke", top_k=3)

    engine = RecordingSearchEngine.instances[-1]
    assert engine.calls[0]["top_k"] == 3
