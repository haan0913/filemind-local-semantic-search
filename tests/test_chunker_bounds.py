"""Regression tests for bounded FileMind chunk sizes."""

from filemind.chunker import TextChunker


def test_markdown_single_huge_paragraph_is_split_before_embedding():
    chunker = TextChunker(chunk_size=200, overlap=20)
    text = "# Research capture\n\n" + ("token " * 5000)

    chunks = chunker.chunk(text, "docs/research-capture.md")

    assert len(chunks) > 1
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert max(chunk.word_count for chunk in chunks) <= 1600
