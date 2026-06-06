"""
Dashboard — Gradio web UI for FileMind.

Provides:
- Search interface (keyword, semantic, hybrid)
- File browser by category/type
- Statistics dashboard
- Duplicate detection report
"""

import logging
import time

import gradio as gr
from gradio.themes import Soft

try:
    from .config import config
    from .catalog import Catalog
    from .search import SearchEngine
    from .duplicates import DuplicateDetector
except ImportError:
    from config import config
    from catalog import Catalog
    from search import SearchEngine
    from duplicates import DuplicateDetector

logger = logging.getLogger(__name__)

# Global instances (lazy loaded)
_catalog = None
_search_engine = None
_dup_detector = None


def _get_catalog():
    global _catalog
    if _catalog is None:
        _catalog = Catalog()
        _catalog.init_db()
    return _catalog


def _get_search_engine():
    global _search_engine
    if _search_engine is None:
        _search_engine = SearchEngine()
    return _search_engine


def _get_dup_detector():
    global _dup_detector
    if _dup_detector is None:
        _dup_detector = DuplicateDetector()
    return _dup_detector


# ── Search ──────────────────────────────────────────────────────────────

def search_files(query: str, search_type: str, file_type: str,
                 top_k: int) -> list[list]:
    """Execute search and format results."""
    if not query.strip():
        return []

    engine = _get_search_engine()
    ft = file_type if file_type != "All" else None

    if search_type == "Keyword (FTS5)":
        results = engine.keyword_search(query, top_k)
    elif search_type == "Semantic (Vector)":
        results = engine.semantic_search(query, top_k)
    else:  # Hybrid
        results = engine.search(query, top_k, file_type=ft)

    rows = []
    for r in results:
        rows.append([
            r.file_path,
            r.file_type,
            r.category,
            f"{r.score:.4f}",
            f"K:{r.keyword_rank} S:{r.semantic_rank}",
            time.strftime("%Y-%m-%d", time.localtime(r.mtime)) if r.mtime > 0 else "N/A",
            r.snippet[:300] if r.snippet else "(no content)",
        ])
    return rows


# ── Browse ──────────────────────────────────────────────────────────────

def browse_files(category: str, ext: str) -> list[list]:
    """Browse files by category and extension."""
    catalog = _get_catalog()
    cat = category if category != "All" else None
    ext_filter = ext if ext != "All" else None

    if cat:
        files = catalog.get_files_by_category(cat)
    else:
        files = []
        stats = catalog.get_stats()
        for c in stats.get("categories", {}).keys():
            files.extend(catalog.get_files_by_category(c))

    if ext_filter:
        files = [f for f in files if f.get("ext", "").lower() == ext_filter.lower()]

    rows = []
    for f in files[:200]:  # Limit display
        rows.append([
            f["path"],
            f.get("ext", ""),
            f.get("category", ""),
            f.get("size", 0) / 1024,  # KB
            f.get("chunk_count", 0),
            f.get("content_hash", "")[:12],
            "Yes" if f.get("is_duplicate") else "No",
        ])
    return rows


# ── Statistics ──────────────────────────────────────────────────────────

def get_stats() -> str:
    """Get formatted statistics."""
    catalog = _get_catalog()
    stats = catalog.get_stats()

    lines = [
        f"**Total Files:** {stats['total_files']}",
        f"**Total Size:** {stats['total_size_mb']:.1f} MB",
        f"**Duplicates:** {stats['duplicates']}",
        "",
        "**Categories:**",
    ]
    for cat, cnt in sorted(stats.get("categories", {}).items()):
        lines.append(f"  - {cat}: {cnt}")

    lines.append("")
    lines.append("**Top Extensions:**")
    for ext, cnt in stats.get("top_extensions", {}).items():
        lines.append(f"  - {ext}: {cnt}")

    return "\n".join(lines)


# ── Duplicates ──────────────────────────────────────────────────────────

def find_duplicates() -> str:
    """Find and format duplicate report."""
    detector = _get_dup_detector()
    report = detector.report()

    lines = [
        f"### Duplicate Report",
        f"",
        f"- **Exact duplicate groups:** {report['exact_groups']}",
        f"- **Exact duplicate files:** {report['exact_files']}",
        f"- **Semantic duplicate pairs:** {report['semantic_pairs']}",
        f"- **Nested duplicate patterns:** {report['nested_patterns']}",
        f"- **Estimated savings:** {report['estimated_savings']}",
        f"",
    ]

    if report["details"]["exact"]:
        lines.append("#### Exact Duplicates (sample)")
        lines.append("```")
        for h, paths in list(report["details"]["exact"].items())[:10]:
            lines.append(f"Hash: {h[:16]}...")
            for p in paths[:3]:
                lines.append(f"  {p}")
        lines.append("```")

    if report["details"]["semantic"]:
        lines.append("")
        lines.append("#### Semantic Duplicates (sample)")
        lines.append("```")
        for dup in report["details"]["semantic"][:10]:
            lines.append(
                f"{dup['similarity']:.3f}: {dup['file_a']} ≈ {dup['file_b']}"
            )
        lines.append("```")

    return "\n".join(lines)


# ── Health ──────────────────────────────────────────────────────────────

def health_check() -> str:
    """Health check display."""
    try:
        from .nightly import NightlyOrchestrator
    except ImportError:
        from nightly import NightlyOrchestrator

    orchestrator = NightlyOrchestrator()
    checks = orchestrator.health_check()

    lines = ["### System Health", ""]
    for component, status in checks.items():
        emoji = "✅" if status.get("status") == "ok" else "❌"
        lines.append(f"{emoji} **{component}**: {status.get('status', 'unknown')}")
        if "error" in status:
            lines.append(f"   Error: {status['error']}")
        if "device" in status:
            lines.append(f"   Device: {status['device']}")
        if "vram_total_gb" in status:
            lines.append(
                f"   VRAM: {status['vram_used_gb']:.1f} / {status['vram_total_gb']:.1f} GB"
            )

    return "\n".join(lines)


# ── Launch ──────────────────────────────────────────────────────────────

def build_ui() -> gr.Blocks:
    """Build the Gradio UI."""
    with gr.Blocks(title="FileMind Dashboard", theme=Soft()) as ui:
        gr.Markdown("# FileMind Dashboard")
        gr.Markdown("PC-Wide Semantic File Indexing & Search System")

        with gr.Tab("Search"):
            with gr.Row():
                query_input = gr.Textbox(
                    label="Search Query",
                    placeholder="e.g., Python script that handles Telegram bots",
                    lines=2,
                )
            with gr.Row():
                search_type = gr.Radio(
                    ["Hybrid", "Keyword (FTS5)", "Semantic (Vector)"],
                    value="Hybrid",
                    label="Search Type",
                )
                file_type = gr.Dropdown(
                    ["All", ".py", ".md", ".js", ".ts", ".json", ".txt",
                     ".yaml", ".yml", ".toml", ".pdf", ".docx", ".csv"],
                    value="All",
                    label="File Type Filter",
                )
                top_k = gr.Slider(5, 50, value=20, step=5, label="Max Results")
            search_btn = gr.Button("Search", variant="primary")
            search_output = gr.Dataframe(
                headers=["Path", "Type", "Category", "Score", "Ranks", "Modified", "Snippet"],
                wrap=True,
            )
            search_btn.click(
                search_files,
                [query_input, search_type, file_type, top_k],
                search_output,
            )

        with gr.Tab("Browse"):
            with gr.Row():
                cat_filter = gr.Dropdown(
                    ["All", "code", "documentation", "research", "ai_project",
                     "personal", "config", "data", "archive", "unknown"],
                    value="All",
                    label="Category",
                )
                ext_filter = gr.Dropdown(
                    ["All", ".py", ".md", ".js", ".ts", ".json", ".txt",
                     ".yaml", ".yml", ".toml", ".pdf", ".docx"],
                    value="All",
                    label="Extension",
                )
                browse_btn = gr.Button("Browse")
            browse_output = gr.Dataframe(
                headers=["Path", "Extension", "Category", "Size (KB)",
                         "Chunks", "Hash", "Duplicate"],
                wrap=True,
            )
            browse_btn.click(
                browse_files,
                [cat_filter, ext_filter],
                browse_output,
            )

        with gr.Tab("Statistics"):
            stats_output = gr.Markdown()
            stats_btn = gr.Button("Refresh Stats")
            stats_btn.click(get_stats, outputs=stats_output)

        with gr.Tab("Duplicates"):
            dup_output = gr.Markdown()
            dup_btn = gr.Button("Find Duplicates")
            dup_btn.click(find_duplicates, outputs=dup_output)

        with gr.Tab("Health"):
            health_output = gr.Markdown()
            health_btn = gr.Button("Check Health")
            health_btn.click(health_check, outputs=health_output)

    return ui


def launch_dashboard(host: str | None = None, port: int | None = None,
                     share: bool = False):
    """Launch the Gradio dashboard."""
    h = host or config.dashboard_host
    p = port or config.dashboard_port

    ui = build_ui()
    ui.launch(server_name=h, server_port=p, share=share)
