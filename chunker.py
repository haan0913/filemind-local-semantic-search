"""
Text Chunker — File-type-aware chunking with semantic coherence.

Research-backed strategy (see docs/RESEARCH_NOTES_CHUNKING.md):
- Code (.py): AST-based chunking — functions, classes as units
- Config (.json, .yaml, .toml): Structure-aware — key-value pairs, nested blocks
- Docs (.md, .rst): Header-based hierarchical — sections by headings
- PDF (.pdf): Multi-stage — extract text, infer structure, chunk by paragraphs
- Other: Fixed-size fallback with extension-specific chunk sizes

Controlled by config.USE_SMART_CHUNKING (default True).
Falls back to fixed-size chunking on any error.
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """Represents a single text chunk."""

    file_path: str  # Relative path of parent file
    chunk_index: int  # 0-based index within file
    content: str  # Chunk text
    word_count: int  # Number of words in chunk
    chunk_hash: str  # MD5 hash of this chunk's content


def _make_chunk(file_path: str, index: int, content: str) -> Chunk:
    """Create a chunk with computed hash and word count."""
    text = content.strip()
    word_count = len(text.split())
    c_hash = hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()
    return Chunk(
        file_path=file_path,
        chunk_index=index,
        content=text,
        word_count=word_count,
        chunk_hash=c_hash,
    )


# ── Smart Chunkers (Type-Specific) ─────────────────────────────────────────


def chunk_python_file(source_code: str, file_path: str) -> list[Chunk]:
    """Parse Python file and chunk at function/class definitions using AST."""
    import ast

    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return []

    chunks = []
    lines = source_code.splitlines(keepends=True)

    # Collect top-level nodes (functions, classes, module-level code)
    top_level_nodes = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            top_level_nodes.append(node)

    if not top_level_nodes:
        # No functions/classes — return full file as one chunk
        return [_make_chunk(file_path, 0, source_code)]

    # Extract source ranges for each top-level definition
    def get_source(node) -> str:
        """Extract the full source text for an AST node."""
        start = node.lineno - 1  # 0-indexed
        # End line: find the last line of the node's body
        end = node.end_lineno or (start + 1)
        return "".join(lines[start:end])

    # Also capture module-level imports and docstring before first definition
    first_def = top_level_nodes[0]
    if first_def.lineno > 1:
        preamble = "".join(lines[: first_def.lineno - 1]).strip()
        if preamble:
            chunks.append(_make_chunk(file_path, len(chunks), preamble))

    # Chunk each function/class
    for node in top_level_nodes:
        source = get_source(node).strip()
        if source:
            chunks.append(_make_chunk(file_path, len(chunks), source))

    return chunks


def chunk_json_file(data: str, file_path: str) -> list[Chunk]:
    """Parse JSON and chunk by top-level keys and nested blocks."""
    import json

    try:
        obj = json.loads(data)
    except json.JSONDecodeError:
        return []

    chunks = []

    if isinstance(obj, dict):
        # Group related keys into chunks
        # For small dicts, return entire file as one chunk
        if len(obj) <= 10:
            chunks.append(_make_chunk(file_path, 0, data))
        else:
            # Chunk by top-level keys, grouping related nested blocks
            current_chunk = {}
            current_size = 0
            chunk_idx = 0

            for key, value in obj.items():
                item_str = json.dumps({key: value}, indent=2, ensure_ascii=False)
                item_size = len(item_str.split())

                # If a single nested block is large, chunk it separately
                if isinstance(value, (dict, list)) and item_size > 500:
                    # Flush current chunk
                    if current_chunk:
                        chunks.append(
                            _make_chunk(
                                file_path,
                                chunk_idx,
                                json.dumps(current_chunk, indent=2, ensure_ascii=False),
                            )
                        )
                        chunk_idx += 1
                        current_chunk = {}
                        current_size = 0

                    # Add the large block as its own chunk
                    chunks.append(_make_chunk(file_path, chunk_idx, item_str))
                    chunk_idx += 1
                elif current_size + item_size > 1000:
                    # Flush and start new chunk
                    chunks.append(
                        _make_chunk(
                            file_path,
                            chunk_idx,
                            json.dumps(current_chunk, indent=2, ensure_ascii=False),
                        )
                    )
                    chunk_idx += 1
                    current_chunk = {key: value}
                    current_size = item_size
                else:
                    current_chunk[key] = value
                    current_size += item_size

            # Flush remaining
            if current_chunk:
                chunks.append(
                    _make_chunk(
                        file_path,
                        chunk_idx,
                        json.dumps(current_chunk, indent=2, ensure_ascii=False),
                    )
                )

    elif isinstance(obj, list):
        # For arrays, chunk by groups of items
        items_per_chunk = max(1, 500 // max(1, len(data.split()) // len(obj)))
        for i in range(0, len(obj), items_per_chunk):
            batch = obj[i : i + items_per_chunk]
            chunks.append(
                _make_chunk(
                    file_path,
                    len(chunks),
                    json.dumps(batch, indent=2, ensure_ascii=False),
                )
            )

    return chunks if chunks else [_make_chunk(file_path, 0, data)]


def chunk_yaml_file(data: str, file_path: str) -> list[Chunk]:
    """Parse YAML and chunk by top-level keys and nested sections."""
    try:
        import yaml

        obj = yaml.safe_load(data)
    except Exception:
        return []

    if obj is None or not isinstance(obj, (dict, list)):
        return [_make_chunk(file_path, 0, data)]

    chunks = []

    if isinstance(obj, dict) and len(obj) > 5:
        # Group related top-level keys
        current_section = {}
        current_size = 0
        chunk_idx = 0

        def yaml_dump(value: object) -> str:
            try:
                return str(
                    yaml.dump(
                        value,
                        default_flow_style=False,
                        allow_unicode=True,
                    )
                )
            except Exception:
                return str(value)

        for key, value in obj.items():
            # Serialize just this key-value
            try:
                item_str = yaml_dump({key: value})
            except Exception:
                item_str = f"{key}: {value}"

            item_size = len(item_str.split())

            if isinstance(value, (dict, list)) and item_size > 500:
                # Large nested block — its own chunk
                if current_section:
                    chunks.append(
                        _make_chunk(
                            file_path,
                            chunk_idx,
                            yaml_dump(current_section),
                        )
                    )
                    chunk_idx += 1
                    current_section = {}
                    current_size = 0
                chunks.append(_make_chunk(file_path, chunk_idx, item_str))
                chunk_idx += 1
            elif current_size + item_size > 1000:
                if current_section:
                    chunks.append(
                        _make_chunk(
                            file_path,
                            chunk_idx,
                            yaml_dump(current_section),
                        )
                    )
                    chunk_idx += 1
                current_section = {key: value}
                current_size = item_size
            else:
                current_section[key] = value
                current_size += item_size

        if current_section:
            chunks.append(
                _make_chunk(
                    file_path,
                    chunk_idx,
                    yaml_dump(current_section),
                )
            )
    else:
        chunks.append(_make_chunk(file_path, 0, data))

    return chunks if chunks else [_make_chunk(file_path, 0, data)]


def chunk_toml_file(data: str, file_path: str) -> list[Chunk]:
    """Parse TOML and chunk by sections ([section] blocks)."""
    import tomllib

    try:
        obj = tomllib.loads(data)
    except Exception:
        return []

    if not isinstance(obj, dict):
        return [_make_chunk(file_path, 0, data)]

    chunks = []

    # TOML sections map naturally to nested dicts
    # Split the raw text by section headers to preserve structure
    section_pattern = re.compile(r"^(\[.*?\])\s*$", re.MULTILINE)
    sections = section_pattern.split(data)

    if len(sections) > 3:
        # Has sections — chunk by section
        chunk_idx = 0
        for i in range(1, len(sections), 2):
            header = sections[i]
            content = sections[i + 1] if i + 1 < len(sections) else ""
            section_text = header + content
            if section_text.strip():
                chunks.append(_make_chunk(file_path, chunk_idx, section_text.strip()))
                chunk_idx += 1
    else:
        # No sections — return full file
        chunks.append(_make_chunk(file_path, 0, data))

    return chunks if chunks else [_make_chunk(file_path, 0, data)]


def chunk_markdown_file(
    content: str, file_path: str, max_tokens: int = 1024
) -> list[Chunk]:
    """Split Markdown by headers, then by paragraphs if sections are large."""
    chunks = []

    # Split by headers (# to ######)
    header_pattern = re.compile(r"^(#{1,6}\s+.+)$", re.MULTILINE)
    parts = header_pattern.split(content)

    chunk_idx = 0

    if len(parts) <= 1:
        # No headers found — split by paragraphs
        paragraphs = re.split(r"\n\n+", content)
        current = ""
        for para in paragraphs:
            para_words = len(para.split())
            if len(current.split()) + para_words > max_tokens and current:
                chunks.append(_make_chunk(file_path, chunk_idx, current.strip()))
                chunk_idx += 1
                current = para
            else:
                current = current + "\n\n" + para if current else para
        if current.strip():
            chunks.append(_make_chunk(file_path, chunk_idx, current.strip()))
    else:
        # Has headers — group header + content
        # parts[0] is preamble, then alternating [header, content]
        preamble = parts[0].strip()
        if preamble:
            chunks.append(_make_chunk(file_path, chunk_idx, preamble))
            chunk_idx += 1

        for i in range(1, len(parts), 2):
            header = parts[i]
            body = parts[i + 1] if i + 1 < len(parts) else ""
            section = f"{header}\n{body}".strip()

            section_words = len(section.split())
            if section_words <= max_tokens:
                # Section fits — keep as one chunk
                chunks.append(_make_chunk(file_path, chunk_idx, section))
                chunk_idx += 1
            else:
                # Section too large — split by paragraphs within section
                paragraphs = re.split(r"\n\n+", body)
                current = header + "\n\n"
                for para in paragraphs:
                    para_words = len(para.split())
                    if (
                        len(current.split()) + para_words > max_tokens
                        and current.strip() != header.strip()
                    ):
                        chunks.append(
                            _make_chunk(file_path, chunk_idx, current.strip())
                        )
                        chunk_idx += 1
                        current = para
                    else:
                        current = (
                            current + "\n\n" + para
                            if current.strip() != header.strip()
                            else header + "\n\n" + para
                        )
                if current.strip():
                    chunks.append(_make_chunk(file_path, chunk_idx, current.strip()))
                    chunk_idx += 1

    return chunks if chunks else [_make_chunk(file_path, 0, content)]


def chunk_pdf_file(file_path_str: str, content: str, file_path: str) -> list[Chunk]:
    """Extract text from PDF using PyMuPDF, then chunk by paragraphs."""
    try:
        import pymupdf
    except ImportError:
        logger.warning("PyMuPDF not installed — falling back to fixed-size chunking")
        return []

    try:
        doc = pymupdf.open(file_path_str)
        full_text = ""
        for page in doc:
            page_text = page.get_text()
            full_text += (
                page_text if isinstance(page_text, str) else str(page_text)
            ) + "\n\n"
        doc.close()
    except Exception as e:
        logger.warning(f"PyMuPDF extraction failed: {e}")
        return []

    if not full_text.strip():
        return []

    # Chunk by paragraphs (double newlines as boundary)
    paragraphs = re.split(r"\n\n+", full_text)
    chunks = []
    chunk_idx = 0
    current = ""
    max_words = 1024  # ~512-1024 tokens

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        para_words = len(para.split())

        if len(current.split()) + para_words > max_words and current:
            chunks.append(_make_chunk(file_path, chunk_idx, current))
            chunk_idx += 1
            current = para
        else:
            current = current + "\n\n" + para if current else para

    if current.strip():
        chunks.append(_make_chunk(file_path, chunk_idx, current.strip()))

    return chunks if chunks else [_make_chunk(file_path, 0, full_text)]


# ── Fixed-Size Fallback ────────────────────────────────────────────────────


def fixed_size_chunker(
    text: str, file_path: str, chunk_size: int, overlap: int
) -> list[Chunk]:
    """Original fixed-size word-based chunking."""
    words = text.split()
    if len(words) <= chunk_size:
        return [_make_chunk(file_path, 0, text)]

    chunks = []
    stride = chunk_size - overlap

    for i in range(0, len(words), stride):
        chunk_words = words[i : i + chunk_size]
        if not chunk_words:
            break
        content = " ".join(chunk_words)
        chunks.append(_make_chunk(file_path, len(chunks), content))
        if i + chunk_size >= len(words):
            break

    return chunks


# ── Main Dispatcher ────────────────────────────────────────────────────────


class TextChunker:
    """Configurable text chunking with file-type-aware dispatch."""

    def __init__(self, chunk_size: int = 2048, overlap: int = 256):
        """
        Initialize the chunker.

        Args:
            chunk_size: Target words per chunk (for fixed-size fallback)
            overlap: Overlapping words between consecutive chunks
        """
        self.chunk_size = chunk_size
        self.overlap = min(overlap, chunk_size // 2)

    def chunk(self, text: str, file_path: str = "") -> list[Chunk]:
        """
        Split text into chunks using file-type-aware strategy.

        Dispatches to type-specific chunkers based on file extension.
        Falls back to fixed-size chunking on error or if smart chunking disabled.

        Args:
            text: Text to chunk
            file_path: Path of the parent file

        Returns:
            List of Chunk objects
        """
        if not text or not text.strip():
            return []

        try:
            from .config import config
        except ImportError:
            from config import config

        # Check if smart chunking is enabled
        if not getattr(config, "use_smart_chunking", True):
            return self._fixed_size_fallback(text, file_path, config)

        ext = Path(file_path).suffix.lower()

        try:
            if ext == ".py":
                chunks = chunk_python_file(text, file_path)
                if chunks:
                    return self._normalize_chunks(chunks, file_path, config)

            elif ext == ".json":
                chunks = chunk_json_file(text, file_path)
                if chunks:
                    return self._normalize_chunks(chunks, file_path, config)

            elif ext in (".yaml", ".yml"):
                chunks = chunk_yaml_file(text, file_path)
                if chunks:
                    return self._normalize_chunks(chunks, file_path, config)

            elif ext == ".toml":
                chunks = chunk_toml_file(text, file_path)
                if chunks:
                    return self._normalize_chunks(chunks, file_path, config)

            elif ext in (".md", ".markdown"):
                chunks = chunk_markdown_file(text, file_path)
                if chunks:
                    return self._normalize_chunks(chunks, file_path, config)

            elif ext == ".pdf":
                # For PDF, we need the actual file path on disk
                if Path(file_path).exists():
                    chunks = chunk_pdf_file(str(Path(file_path)), text, file_path)
                    if chunks:
                        return self._normalize_chunks(chunks, file_path, config)

            # Fallback: fixed-size chunking
            return self._fixed_size_fallback(text, file_path, config)

        except Exception as e:
            logger.warning(
                f"Smart chunk failed for {file_path} ({ext}): {e} — falling back to fixed-size"
            )
            return self._fixed_size_fallback(text, file_path, config)

    def _fixed_size_fallback(self, text: str, file_path: str, config) -> list[Chunk]:
        """Fallback to extension-specific fixed-size chunking."""
        ext = Path(file_path).suffix.lower()
        active_chunk_size = config.chunk_size_by_ext.get(ext, self.chunk_size)
        active_overlap = min(self.overlap, active_chunk_size // 2)
        return fixed_size_chunker(text, file_path, active_chunk_size, active_overlap)

    def _normalize_chunks(
        self, chunks: list[Chunk], file_path: str, config
    ) -> list[Chunk]:
        """Split pathological smart chunks before they reach the embedder.

        Header/structure-aware chunking can still produce a single very large
        chunk when source files contain huge paragraphs or generated captures.
        Those chunks make tokenizer/model calls slow and memory-heavy. Keep the
        semantic chunking where it is already bounded, but fall back to the same
        extension-specific fixed-size strategy for oversized chunks.
        """
        if not chunks:
            return []

        ext = Path(file_path).suffix.lower()
        active_chunk_size = config.chunk_size_by_ext.get(ext, self.chunk_size)
        active_overlap = min(self.overlap, active_chunk_size // 2)
        max_words = max(active_chunk_size * 2, active_chunk_size)

        normalized: list[Chunk] = []
        for chunk in chunks:
            if chunk.word_count <= max_words:
                normalized.append(
                    _make_chunk(file_path, len(normalized), chunk.content)
                )
                continue

            for split_chunk in fixed_size_chunker(
                chunk.content,
                file_path,
                active_chunk_size,
                active_overlap,
            ):
                if split_chunk.content:
                    normalized.append(
                        _make_chunk(file_path, len(normalized), split_chunk.content)
                    )

        return normalized

    def set_params(self, chunk_size: int, overlap: int):
        """Update chunking parameters."""
        self.chunk_size = chunk_size
        self.overlap = min(overlap, chunk_size // 2)


# Module-level convenience function
_default_chunker = TextChunker()


def chunk_text(
    text: str, file_path: str = "", chunk_size: int = 512, overlap: int = 64
) -> list[Chunk]:
    """
    Split text into overlapping chunks (convenience function).

    Args:
        text: Text to chunk
        file_path: Parent file path
        chunk_size: Words per chunk
        overlap: Overlap between chunks

    Returns:
        List of Chunk objects
    """
    chunker = TextChunker(chunk_size=chunk_size, overlap=overlap)
    return chunker.chunk(text, file_path)
