"""
FileMind Configuration

Central configuration for the FileMind system.
Override via environment variables or .env file.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field

# ── Base Paths ──────────────────────────────────────────────────────────────
FILEMIND_DIR = Path(__file__).resolve().parent
USER_HOME = Path(os.getenv("USERPROFILE", str(Path.home())))
AI_STATION = Path(os.getenv("AI_STATION_ROOT", str(FILEMIND_DIR.parent))).resolve()
DEFAULT_INDEX_DIR = FILEMIND_DIR / ".index"
LEGACY_INDEX_DIR = AI_STATION / ".index"
INDEX_DIR = Path(
    os.getenv(
        "FILEMIND_INDEX_DIR",
        str(
            DEFAULT_INDEX_DIR
            if DEFAULT_INDEX_DIR.exists() or not LEGACY_INDEX_DIR.exists()
            else LEGACY_INDEX_DIR
        ),
    )
).resolve()
KIMI_DIR = Path(os.getenv("FILEMIND_KIMI_DIR", str(USER_HOME / ".kimi")))
DEFAULT_OBSIDIAN_VAULT_DIR = AI_STATION / "hub" / "notes" / "obsidian-vault"
OBSIDIAN_VAULT_DIR = Path(
    os.getenv(
        "FILEMIND_OBSIDIAN_VAULT_DIR",
        str(
            DEFAULT_OBSIDIAN_VAULT_DIR
            if DEFAULT_OBSIDIAN_VAULT_DIR.exists()
            else USER_HOME / "Obsidian Vault"
        ),
    )
)
DEFAULT_PC_FOCUS_DIR = AI_STATION / "projects" / "pc-focus"
PC_FOCUS_DIR = Path(
    os.getenv(
        "FILEMIND_PC_FOCUS_DIR",
        str(
            DEFAULT_PC_FOCUS_DIR
            if DEFAULT_PC_FOCUS_DIR.exists()
            else USER_HOME / "pc-focus"
        ),
    )
)
CLINE_DIR = Path(os.getenv("FILEMIND_CLINE_DIR", str(USER_HOME / ".cline")))
CLAUDE_DIR = Path(os.getenv("FILEMIND_CLAUDE_DIR", str(USER_HOME / ".claude")))
OPENCLAW_DIR = Path(os.getenv("FILEMIND_OPENCLAW_DIR", str(USER_HOME / ".openclaw")))
AGENTS_DIR = Path(os.getenv("FILEMIND_AGENTS_DIR", str(USER_HOME / ".agents")))
CODEX_DIR = Path(os.getenv("FILEMIND_CODEX_DIR", str(USER_HOME / ".codex")))
WINDSURF_DIR = Path(os.getenv("FILEMIND_WINDSURF_DIR", str(USER_HOME / ".windsurf")))
AIDER_DIR = Path(os.getenv("FILEMIND_AIDER_DIR", str(USER_HOME / ".aider")))
CODEIUM_DIR = Path(os.getenv("FILEMIND_CODEIUM_DIR", str(USER_HOME / ".codeium")))
COPILOT_DIR = Path(os.getenv("FILEMIND_COPILOT_DIR", str(USER_HOME / ".copilot")))
CLAUDE_CODE_DIR = Path(
    os.getenv("FILEMIND_CLAUDE_CODE_DIR", str(USER_HOME / ".claude-code"))
)
GEMINI_DIR = Path(os.getenv("FILEMIND_GEMINI_DIR", str(USER_HOME / ".gemini")))
QWEN_DIR = Path(os.getenv("FILEMIND_QWEN_DIR", str(USER_HOME / ".qwen")))
ANTIGRAVITY_DIR = Path(
    os.getenv("FILEMIND_ANTIGRAVITY_DIR", str(USER_HOME / ".antigravity"))
)
MCPORTER_DIR = Path(os.getenv("FILEMIND_MCPORTER_DIR", str(USER_HOME / ".mcporter")))
N8N_DIR = Path(os.getenv("FILEMIND_N8N_DIR", str(USER_HOME / ".n8n")))
NODE_LLAMA_CPP_DIR = Path(
    os.getenv("FILEMIND_NODE_LLAMA_CPP_DIR", str(USER_HOME / ".node-llama-cpp"))
)
OLLAMA_DIR = Path(os.getenv("FILEMIND_OLLAMA_DIR", str(USER_HOME / ".ollama")))
PLAYWRIGHT_MCP_DIR = Path(
    os.getenv("FILEMIND_PLAYWRIGHT_MCP_DIR", str(USER_HOME / ".playwright-mcp"))
)
PM2_DIR = Path(os.getenv("FILEMIND_PM2_DIR", str(USER_HOME / ".pm2")))
HUGGINGFACE_CACHE_DIR = Path(
    os.getenv(
        "FILEMIND_HUGGINGFACE_CACHE_DIR", str(USER_HOME / ".cache" / "huggingface")
    )
)
ASSISTANT_AGENT_ROOT = AI_STATION / "hub" / "agents" / "assistants"
IDE_AGENT_ROOT = AI_STATION / "hub" / "agents" / "ides"
FRAMEWORK_AGENT_ROOT = AI_STATION / "hub" / "agents" / "frameworks"
TOOLS_ROOT = AI_STATION / "tools"
BM25_INDEX_PATH = Path(
    os.getenv("FILEMIND_BM25_INDEX_PATH", str(INDEX_DIR / "bm25_index.json"))
)
PROGRESS_FILE = Path(
    os.getenv("FILEMIND_PROGRESS_FILE", str(INDEX_DIR / "nightly_progress.json"))
)
USER_GUIDE_PATH = Path(
    os.getenv(
        "FILEMIND_USER_GUIDE_PATH",
        str(FILEMIND_DIR / "docs" / "user" / "FILEMIND_USER_GUIDE.md"),
    )
)


@dataclass(frozen=True)
class AgentWorkingDirSpec:
    """Curated AI-agent working root classification for the clean index."""

    name: str
    lane: str
    paths: tuple[Path, ...]
    aliases: tuple[str, ...] = ()
    note: str = ""


AGENT_WORKING_DIR_LANES: set[str] = {"normal", "protected", "excluded"}

AGENT_WORKING_DIR_INVENTORY: tuple[AgentWorkingDirSpec, ...] = (
    # Assistant homes: useful configs, docs, prompts, skills, and settings are normal.
    AgentWorkingDirSpec(
        "codex", "normal", (CODEX_DIR, ASSISTANT_AGENT_ROOT / ".codex"), (".codex",)
    ),
    AgentWorkingDirSpec(
        "claude", "normal", (CLAUDE_DIR, ASSISTANT_AGENT_ROOT / ".claude"), (".claude",)
    ),
    AgentWorkingDirSpec(
        "kimi", "normal", (KIMI_DIR, ASSISTANT_AGENT_ROOT / ".kimi"), (".kimi",)
    ),
    AgentWorkingDirSpec(
        "openclaw",
        "normal",
        (OPENCLAW_DIR, ASSISTANT_AGENT_ROOT / ".openclaw"),
        (".openclaw",),
    ),
    AgentWorkingDirSpec(
        "agents", "normal", (AGENTS_DIR, ASSISTANT_AGENT_ROOT / ".agents"), (".agents",)
    ),
    AgentWorkingDirSpec(
        "claude-code",
        "normal",
        (CLAUDE_CODE_DIR, ASSISTANT_AGENT_ROOT / ".claude-code"),
        (".claude-code",),
    ),
    AgentWorkingDirSpec(
        "gemini", "normal", (GEMINI_DIR, ASSISTANT_AGENT_ROOT / ".gemini"), (".gemini",)
    ),
    AgentWorkingDirSpec(
        "qwen", "normal", (QWEN_DIR, ASSISTANT_AGENT_ROOT / ".qwen"), (".qwen",)
    ),
    AgentWorkingDirSpec(
        "antigravity",
        "normal",
        (ANTIGRAVITY_DIR, ASSISTANT_AGENT_ROOT / ".antigravity"),
        (".antigravity",),
    ),
    # IDE assistant homes.
    AgentWorkingDirSpec(
        "cline", "normal", (CLINE_DIR, IDE_AGENT_ROOT / ".cline"), (".cline",)
    ),
    AgentWorkingDirSpec(
        "windsurf",
        "normal",
        (WINDSURF_DIR, IDE_AGENT_ROOT / ".windsurf"),
        (".windsurf",),
    ),
    AgentWorkingDirSpec(
        "aider", "normal", (AIDER_DIR, IDE_AGENT_ROOT / ".aider"), (".aider",)
    ),
    AgentWorkingDirSpec(
        "codeium", "normal", (CODEIUM_DIR, IDE_AGENT_ROOT / ".codeium"), (".codeium",)
    ),
    AgentWorkingDirSpec(
        "copilot", "normal", (COPILOT_DIR, IDE_AGENT_ROOT / ".copilot"), (".copilot",)
    ),
    # Framework/config roots. Runtime caches inside these roots are excluded below.
    AgentWorkingDirSpec(
        "opencode",
        "normal",
        (
            USER_HOME / ".opencode",
            AI_STATION / "opencode",
            AI_STATION / "OpenCode",
            TOOLS_ROOT / "OpenCode",
            TOOLS_ROOT / "opencode",
            FRAMEWORK_AGENT_ROOT / ".config" / "opencode",
            FRAMEWORK_AGENT_ROOT / ".local" / "share" / "opencode",
            FRAMEWORK_AGENT_ROOT / ".local" / "state" / "opencode",
        ),
        (".opencode", "opencode", "OpenCode"),
    ),
    AgentWorkingDirSpec(
        "cagent",
        "normal",
        (
            USER_HOME / ".cagent",
            FRAMEWORK_AGENT_ROOT / ".cagent",
            FRAMEWORK_AGENT_ROOT / ".config" / "cagent",
        ),
        (".cagent", "cagent"),
    ),
    AgentWorkingDirSpec(
        "agent-browser",
        "normal",
        (USER_HOME / ".agent-browser", FRAMEWORK_AGENT_ROOT / ".agent-browser"),
        (".agent-browser", "agent-browser"),
    ),
    AgentWorkingDirSpec(
        "mcporter",
        "normal",
        (MCPORTER_DIR, FRAMEWORK_AGENT_ROOT / ".mcporter"),
        (".mcporter", "mcporter"),
    ),
    AgentWorkingDirSpec(
        "n8n", "normal", (N8N_DIR, FRAMEWORK_AGENT_ROOT / ".n8n"), (".n8n", "n8n")
    ),
    AgentWorkingDirSpec(
        "playwright-mcp",
        "normal",
        (
            PLAYWRIGHT_MCP_DIR,
            AI_STATION / ".playwright-mcp",
            FRAMEWORK_AGENT_ROOT / ".playwright-mcp",
        ),
        (".playwright-mcp", "playwright-mcp"),
    ),
    AgentWorkingDirSpec(
        "pm2", "normal", (PM2_DIR, FRAMEWORK_AGENT_ROOT / ".pm2"), (".pm2", "pm2")
    ),
    # Protected future lane: raw sessions and credential stores stay out of normal search.
    AgentWorkingDirSpec(
        "agent-raw-sessions",
        "protected",
        (
            CODEX_DIR / "sessions",
            CODEX_DIR / "archived_sessions",
            ASSISTANT_AGENT_ROOT / ".codex" / "sessions",
            ASSISTANT_AGENT_ROOT / ".codex" / "archived_sessions",
            CLAUDE_DIR / "projects",
            CLAUDE_DIR / "sessions",
            ASSISTANT_AGENT_ROOT / ".claude" / "projects",
            ASSISTANT_AGENT_ROOT / ".claude" / "sessions",
            QWEN_DIR / "projects",
            ASSISTANT_AGENT_ROOT / ".qwen" / "projects",
            GEMINI_DIR / "antigravity" / "brain",
            ANTIGRAVITY_DIR / "brain",
            ASSISTANT_AGENT_ROOT / ".gemini" / "antigravity" / "brain",
            ASSISTANT_AGENT_ROOT / ".antigravity" / "brain",
        ),
        (
            ".codex/sessions",
            ".codex/archived_sessions",
            ".claude/projects",
            ".claude/sessions",
            ".qwen/projects",
            ".gemini/antigravity/brain",
            ".antigravity/brain",
            "agent-sessions",
        ),
    ),
    AgentWorkingDirSpec(
        "agent-credentials",
        "protected",
        (KIMI_DIR / "credentials", ASSISTANT_AGENT_ROOT / ".kimi" / "credentials"),
        (".kimi/credentials", "agent-credentials"),
    ),
    # Model/blob caches are represented, but kept out of the normal clean index.
    AgentWorkingDirSpec(
        "node-llama-cpp",
        "excluded",
        (NODE_LLAMA_CPP_DIR, FRAMEWORK_AGENT_ROOT / ".node-llama-cpp"),
        (".node-llama-cpp", "node-llama-cpp"),
        "model binaries and native build/cache artifacts",
    ),
    AgentWorkingDirSpec(
        "ollama",
        "excluded",
        (OLLAMA_DIR, FRAMEWORK_AGENT_ROOT / ".ollama"),
        (".ollama", "ollama"),
        "model blobs/manifests; query Ollama directly instead of indexing blobs",
    ),
    AgentWorkingDirSpec(
        "u2net",
        "excluded",
        (USER_HOME / ".u2net", FRAMEWORK_AGENT_ROOT / ".u2net"),
        (".u2net", "u2net"),
        "downloaded model weights",
    ),
    AgentWorkingDirSpec(
        "huggingface-cache",
        "excluded",
        (
            HUGGINGFACE_CACHE_DIR,
            USER_HOME / ".huggingface",
            FRAMEWORK_AGENT_ROOT / ".cache" / "huggingface",
        ),
        (".cache/huggingface", ".huggingface", "huggingface", "huggingface-cache"),
        "Hub cache/model blobs; project docs should live outside cache roots",
    ),
)


def _lane_key(value: str | Path) -> str:
    return str(value).replace("\\", "/").strip().strip("/").lower()


def _agent_path_keys(value: str | Path) -> set[str]:
    """Return stable comparison keys for an agent root path or short alias."""
    raw_text = str(value).strip()
    if not raw_text:
        return set()

    keys = {_lane_key(raw_text)}
    alias_key = _lane_key(raw_text).lstrip("./")
    if alias_key:
        keys.add(alias_key)

    raw_path = Path(raw_text).expanduser()
    keys.add(_lane_key(raw_path.name))

    candidates = [raw_path]
    try:
        candidates.append(raw_path.absolute())
    except OSError:
        pass
    try:
        candidates.append(raw_path.resolve(strict=False))
    except OSError:
        pass

    for path in candidates:
        keys.add(_lane_key(path))
        for base in (AI_STATION, USER_HOME):
            try:
                keys.add(_lane_key(path.relative_to(base)))
            except ValueError:
                continue

    return {key for key in keys if key}


def agent_working_dir_lane(path_or_alias: str | Path) -> str | None:
    """Classify a known AI-agent working root or descendant path."""
    target_keys = _agent_path_keys(path_or_alias)
    matching_lanes: set[str] = set()
    for spec in AGENT_WORKING_DIR_INVENTORY:
        spec_keys = {spec.name.lower(), *(_lane_key(alias) for alias in spec.aliases)}
        for path in spec.paths:
            spec_keys.update(_agent_path_keys(path))
        for target_key in target_keys:
            if any(
                target_key == spec_key or target_key.startswith(spec_key + "/")
                for spec_key in spec_keys
            ):
                matching_lanes.add(spec.lane)
                break
    for lane in ("protected", "excluded", "normal"):
        if lane in matching_lanes:
            return lane
    return None


def _dedupe_paths(paths: list[Path]) -> list[str]:
    """Dedupe paths by real filesystem target while preserving configured aliases."""
    seen: set[str] = set()
    result: list[str] = []
    for path in paths:
        key = os.path.normcase(os.path.realpath(str(path)))
        if key in seen:
            continue
        seen.add(key)
        result.append(str(path))
    return result


def _agent_scan_roots() -> list[str]:
    """Return normal-lane AI-agent roots that should participate in the clean index."""
    roots: list[Path] = []
    for spec in AGENT_WORKING_DIR_INVENTORY:
        if spec.lane != "normal":
            continue
        roots.extend(path for path in spec.paths if path.exists())
    return _dedupe_paths(roots)


def _build_scan_roots() -> list[str]:
    """Return configured scan roots, with an opt-in full override for experiments."""
    override = os.getenv("FILEMIND_SCAN_ROOTS", "").strip()
    if override:
        return [
            str(Path(root).expanduser().resolve())
            for root in override.split(os.pathsep)
            if root.strip()
        ]

    base_roots = [
        str(AI_STATION),  # Primary workspace
        str(OBSIDIAN_VAULT_DIR),  # Personal notes
        str(PC_FOCUS_DIR),  # Personal project
    ]
    return _dedupe_paths(
        [Path(root) for root in base_roots]
        + [Path(root) for root in _agent_scan_roots()]
    )


# ── Scan Configuration ─────────────────────────────────────────────────────
SCAN_ROOTS: list[str] = _build_scan_roots()
# Model/cache roots remain represented in AGENT_WORKING_DIR_INVENTORY, but excluded
# from normal scan roots unless a future protected/specialized lane explicitly uses them.

# Directories to skip entirely (global noise patterns)
SKIP_DIRS: set[str] = {
    ".git",
    "__pycache__",
    "node_modules",
    "backups",
    ".telegram_bot",
    "venv",
    "memmachine_data",
    "playwright",
    "tools",
    ".index",
    ".index_shadow",
    ".bench",
    ".shadow_runs",
    ".pytest_cache",
    ".local",
    ".cache",
    ".next",
    ".aider.tags.cache.v3",
    ".node-llama-cpp",
    "node-llama-cpp",
    ".ollama",
    "ollama",
    ".u2net",
    "u2net",
    ".huggingface",
    # Browser/agent noise that pollutes search results.  Top-level Antigravity is
    # the installed app bundle under AI_STATION, not user/project knowledge.
    "antigravity-browser-profile",
    "Antigravity",
    # Vault backups — these are duplicates of current files
    "vault",
}

AGENT_PROTECTED_SUBDIRS: set[str] = {
    # Raw conversations and credential stores are intentionally out of the normal lane.
    ".codex/sessions",
    ".codex/archived_sessions",
    ".claude/projects",
    ".claude/sessions",
    ".kimi/credentials",
    ".qwen/projects",
    ".gemini/antigravity/brain",
    ".antigravity/brain",
}

AGENT_EXCLUDED_SUBDIRS: set[str] = {
    # Generated caches, browser profiles, model blobs, logs, and vendored deps.
    "antigravity-browser-profile",
    "browser-profile",
    "extensions_crx_cache",
    "model_store",
    "optimization_guide_model_store",
    "blob_storage",
    "Code Cache",
    "GrShader Cache",
    "ShaderCache",
    "GPUCache",
    ".antigravity/extensions",
    ".antigravity/browser-profile",
    ".antigravity/browser_recordings",
    ".codex/restore_backup",
    ".codex/.tmp",
    ".codex/tmp",
    ".codex/.sandbox",
    ".codex/ambient-suggestions",
    ".codex/worktrees",
    ".codex/vendor_imports",
    ".codex/plugins/cache",
    ".codex/cache/codex_apps_tools",
    ".qwen/tmp",
    ".gemini/tmp",
    ".gemini/antigravity/browser_recordings",
    ".aider/caches",
    ".claude/shell-snapshots",
    ".indexeddb.leveldb",
    ".windsurf/logs",
    ".windsurf/User/workspaceStorage",
    ".codeium/cache",
    ".copilot/cache",
    ".playwright-mcp/browser-profile",
    ".playwright-mcp/browsers",
    ".agent-browser/browser-profile",
    ".pm2/logs",
    ".pm2/pids",
    ".pm2/modules",
    ".n8n/.cache",
    ".n8n/binaryData",
    ".n8n/logs",
    ".local/share/opencode/storage/session",
    ".local/share/opencode/storage/session_diff",
    ".node-llama-cpp",
    ".ollama",
    ".u2net",
    ".cache/huggingface",
    ".huggingface",
}


def agent_subpath_lane(rel_path: str | Path) -> str:
    """Classify an in-root agent subpath for normal/protected/excluded handling."""
    key = _lane_key(rel_path)
    for pattern in AGENT_PROTECTED_SUBDIRS:
        pattern_key = _lane_key(pattern)
        if (
            key == pattern_key
            or key.startswith(pattern_key + "/")
            or ("/" + pattern_key + "/") in ("/" + key + "/")
        ):
            return "protected"
    for pattern in AGENT_EXCLUDED_SUBDIRS:
        pattern_key = _lane_key(pattern)
        if (
            key == pattern_key
            or key.startswith(pattern_key + "/")
            or ("/" + pattern_key + "/") in ("/" + key + "/")
        ):
            return "excluded"
    return "normal"


# Fine-grained subdirectory skip patterns (applied within scan roots)
# These replace the blanket ".kimi" skip with targeted exclusions
SKIP_SUBDIRS: set[str] = {
    *AGENT_PROTECTED_SUBDIRS,
    *AGENT_EXCLUDED_SUBDIRS,
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    ".git",
    "Lib",
    "site-packages",
    ".index_shadow",
    ".shadow_runs",
    # Agent framework noise patterns (keep configs/conversations, skip runtime data)
    "antigravity-browser-profile",
    "browser-profile",
    "extensions_crx_cache",
    "model_store",
    "optimization_guide_model_store",
    "blob_storage",
    "Code Cache",
    "GrShader Cache",
    "ShaderCache",
    "GPUCache",
    ".antigravity/extensions",
    ".codex/sessions",
    ".codex/archived_sessions",
    ".codex/restore_backup",
    ".codex/.tmp",
    ".codex/tmp",
    ".codex/.sandbox",
    ".codex/ambient-suggestions",
    ".codex/worktrees",
    ".codex/vendor_imports",
    ".codex/plugins/cache",
    ".codex/cache/codex_apps_tools",
    ".qwen/projects",
    ".qwen/tmp",
    ".gemini/tmp",
    ".aider/caches",
    ".claude/projects",
    ".claude/sessions",
    ".claude/shell-snapshots",
    ".indexeddb.leveldb",
    # .kimi internal noise (selective — preserves plans/, sessions/, scripts/, claudedocs/)
    ".kimi/.kimi",  # mirror/symlink of parent — infinite recursion risk
    ".kimi/.claude",  # local settings only
    ".kimi/credentials",  # API keys/secrets
    ".kimi/logs",  # runtime log files
    ".kimi/owl-agent/.git",  # cloned repo internals
    ".kimi/owl-agent/.venv",  # Python virtual environment
    ".kimi/owl-agent/.container",  # container runtime configs
    ".kimi/owl-agent/.github",  # CI config
    ".kimi/owl-agent/licenses",  # license templates
    ".kimi/owl-agent/community_usecase",  # external community examples
    # Also block at non-.kimi paths (owl-agent as standalone scan root)
    "owl-agent/.git",
    "owl-agent/.venv",
    "owl-agent/community_usecase",
    # AI_STATION archive and live-ingest noise
    ".ai_station/lint-tools",
    ".tmp",
    ".runtime/tmp",
    "review/duplicates",
    "hub/agents/assistants/.codex/skills/.system",
    "hub/data/acceptance",
    "hub/data/context/service",
    "hub/data/prompt-ledger/live",
    "hub/data/prompt-ledger/days",
    "hub/data/hook-log",
    "hub/data/context/build",
    "hub/data/context/cache",
    "hub/data/context/logs",
    "hub/data/context/service-host",
    "hub/data/context/tmp",
    "hub/docs/evals/results",
    "hub/scripts/.runtime",
    "hub/memory/experience_traces/raw",
    "hub/notes/_backups",
    "hub/notes/_vault_quarantine",
    "hub/notes/obsidian-vault/.obsidian",
    "hub/notes/obsidian-vault/00_Raw/imports/bookmark_intelligence/manual_tweet_synthesis_",
}

# High-value file patterns that override skip rules (selective rescanning)
# If these patterns are found inside a skipped parent, that subdir gets scanned
HIGH_VALUE_INCLUDE_PATTERNS: set[str] = {
    # .kimi valuable content
    ".kimi/config.toml",
    ".kimi/kimi_inventory.txt",
    ".kimi/kimi.json",
    ".kimi/plans/",
    ".kimi/sessions/",
    ".kimi/scripts/",
    ".kimi/claudedocs/",
    # owl-agent reference material only
    ".kimi/owl-agent/README.md",
    ".kimi/owl-agent/README_zh.md",
    ".kimi/owl-agent/README_ja.md",
    ".kimi/owl-agent/CITATION.cff",
    ".kimi/owl-agent/assets/",
    ".kimi/owl-agent/community_challenges.md",
    ".kimi/owl-agent/owl/",
    ".kimi/owl-agent/examples/",
}

SKIP_FILE_PATTERNS: set[str] = {
    ".codex/.codex-global-state.json",
    ".codex/models_cache.json",
    ".gemini/antigravity/brain/",
    ".gemini/antigravity/browser_recordings/",
    ".kimi/batch",
    "batch1_contents.md",
    "batch1_parser.py",
    "batch5_summary.json",
    ".kimi/extract_summary",
    "extract_summary.py",
    "extract_summary.txt",
    ".kimi/parse_batch",
    "parse_batch",
    ".tempmediaStorage/",
    "obsidian.log",
}

# File extensions to index
INDEX_EXTENSIONS: set[str] = {
    ".md",
    ".json",
    ".jsonl",
    ".py",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".css",
    ".html",
    ".xml",
    ".csv",
    ".sql",
    ".sh",
    ".bat",
    ".ps1",
    ".cfg",
    ".ini",
    ".log",
    ".env",
    ".conf",
    ".rst",
    ".tex",
    ".latex",
    ".pdf",
    ".docx",
    ".xlsx",
    ".pptx",  # extracted content
    ".eml",
    ".msg",
}

MAX_FILE_SIZE = 500_000  # 500KB max for content extraction
MAX_CONTENT_LENGTH = (
    200_000  # 200KB stored per file (up from 50KB — large files need full context)
)

# ── Capacity & Scaling ─────────────────────────────────────────────────────
TIER1_MAX_SIZE = 1 * 1024 * 1024  # 1MB
TIER2_MAX_SIZE = 10 * 1024 * 1024  # 10MB
SYSTEM_DIRS = [".git", "node_modules", "__pycache__", "venv", ".venv", ".vscode"]

CHUNK_SIZE_BY_EXT = {
    ".py": 1000,
    ".js": 1000,
    ".txt": 500,
    ".md": 800,
    ".json": 1200,
}

# ── Extraction & Chunking ──────────────────────────────────────────────────
CHUNK_SIZE = 2048  # tokens per chunk (bge-m3 supports up to 8192 natively)
CHUNK_OVERLAP = 256  # overlap between chunks (smooth out context boundaries)

# ── Embedding Configuration ────────────────────────────────────────────────
EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIM = 1024
EMBEDDING_BATCH_SIZE = 32
EMBEDDING_DEVICE = os.getenv(
    "FILEMIND_EMBEDDING_DEVICE", "cuda"
).lower()  # "cuda" or "cpu"
EMBEDDING_BACKEND = os.getenv("FILEMIND_EMBEDDING_BACKEND", "sentence_transformers")

# ── Database Paths ─────────────────────────────────────────────────────────
SQLITE_DB = INDEX_DIR / "filemind.db"
QDRANT_PATH = INDEX_DIR / "qdrant"


def _build_qdrant_mode() -> str:
    """Return the FileMind vector-store mode.

    AI_STATION's canonical FileMind index lives in shared Qdrant.  Local
    embedded Qdrant is retained as an explicit scratch/legacy mode through
    ``FILEMIND_QDRANT_MODE=local``; the old ``AI_STATION_USE_SHARED_QDRANT=0``
    value no longer silently points normal CLI verification at stale local
    vectors.
    """
    explicit_mode = os.getenv("FILEMIND_QDRANT_MODE", "").strip().lower()
    if explicit_mode:
        return explicit_mode
    return "http"


def _build_qdrant_url(mode: str | None = None) -> str:
    """Return the shared Qdrant URL for HTTP mode."""
    explicit_url = os.getenv("FILEMIND_QDRANT_URL", "").strip()
    if explicit_url:
        return explicit_url
    return "http://127.0.0.1:6333" if (mode or "http").lower() == "http" else ""


QDRANT_MODE = _build_qdrant_mode()
USE_SHARED_QDRANT = QDRANT_MODE == "http"
QDRANT_URL = _build_qdrant_url(QDRANT_MODE)
QDRANT_HOST = os.getenv("FILEMIND_QDRANT_HOST", "127.0.0.1")
QDRANT_PORT = int(os.getenv("FILEMIND_QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("FILEMIND_QDRANT_COLLECTION", "file_chunks")

# ── Classification Configuration ───────────────────────────────────────────
CATEGORIES = [
    "code",
    "documentation",
    "research",
    "personal",
    "finance",
    "ai_project",
    "media",
    "config",
    "archive",
    "unknown",
]

CLASSIFICATION_MODEL = (
    "qwen2.5-coder:7b"  # Default Ollama LLM lane for FileMind non-embedding tasks
)
CLASSIFICATION_BATCH_SIZE = 5  # Small batches for reliable JSON output
# OpenRouter as fallback (used when Ollama is unavailable)
OPENROUTER_AS_PRIMARY = False
CLASSIFICATION_LLM_ENABLED = os.getenv(
    "FILEMIND_CLASSIFICATION_LLM_ENABLED", "true"
).strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
CLASSIFICATION_CONFIDENCE_THRESHOLD = 0.6
RULE_BASED_FALLBACK = True
CLASSIFICATION_CONFIDENCE_FALLBACK_THRESHOLD = 0.70

# ── Retrieval Enhancements ─────────────────────────────────────────────────
ENABLE_RERANKING = (
    True  # Cross-encoder reranking via sentence_transformers (verified working)
)
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
HYDE_ENABLED = False
HYDE_WEIGHT = 0.5
HYDE_MODEL = "qwen2.5-coder:7b"
SEARCH_DEFAULT_TOP_K = int(os.getenv("FILEMIND_SEARCH_DEFAULT_TOP_K", "20"))

# Smart chunking — research-backed, file-type-aware strategy
# Set to False to revert to fixed-size chunking
USE_SMART_CHUNKING = True

# ── Ollama Configuration ───────────────────────────────────────────────────
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434")

# ── OpenRouter Configuration (fallback) ────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "qwen/qwen3.6-plus:free")

# ── MemMachine Configuration (optional) ────────────────────────────────────
MEMMACHINE_API_URL = os.getenv("MEMMACHINE_API_URL", "http://localhost:8080")
MEMMACHINE_ENABLED = os.getenv("MEMMACHINE_ENABLED", "false").lower() == "true"
MEMMACHINE_ORG_ID = os.getenv("MEMMACHINE_ORG_ID", "ai-hub")
MEMMACHINE_PROJECT_ID = os.getenv("MEMMACHINE_PROJECT_ID", "filemind")

# ── Duplicate Detection ────────────────────────────────────────────────────
DUPLICATE_HASH_SIZE = 65536  # First 64KB for MD5
SEMANTIC_SIMILARITY_THRESHOLD = 0.97  # Cosine similarity threshold

# ── Dashboard Configuration ────────────────────────────────────────────────
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "7860"))

# ── Logging ────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = str(INDEX_DIR / "filemind.log")


@dataclass
class SearchConfig:
    """Search behavior configuration."""

    default_top_k: int = SEARCH_DEFAULT_TOP_K


@dataclass
class FileMindConfig:
    """Runtime configuration container."""

    filemind_dir: Path = FILEMIND_DIR
    user_home: Path = USER_HOME
    ai_station_root: Path = AI_STATION
    index_dir: Path = INDEX_DIR
    kimi_dir: Path = KIMI_DIR
    obsidian_vault_dir: Path = OBSIDIAN_VAULT_DIR
    pc_focus_dir: Path = PC_FOCUS_DIR
    cline_dir: Path = CLINE_DIR
    claude_dir: Path = CLAUDE_DIR
    openclaw_dir: Path = OPENCLAW_DIR
    agents_dir: Path = AGENTS_DIR
    codex_dir: Path = CODEX_DIR
    windsurf_dir: Path = WINDSURF_DIR
    aider_dir: Path = AIDER_DIR
    codeium_dir: Path = CODEIUM_DIR
    copilot_dir: Path = COPILOT_DIR
    claude_code_dir: Path = CLAUDE_CODE_DIR
    gemini_dir: Path = GEMINI_DIR
    qwen_dir: Path = QWEN_DIR
    antigravity_dir: Path = ANTIGRAVITY_DIR
    mcporter_dir: Path = MCPORTER_DIR
    n8n_dir: Path = N8N_DIR
    node_llama_cpp_dir: Path = NODE_LLAMA_CPP_DIR
    ollama_dir: Path = OLLAMA_DIR
    playwright_mcp_dir: Path = PLAYWRIGHT_MCP_DIR
    pm2_dir: Path = PM2_DIR
    huggingface_cache_dir: Path = HUGGINGFACE_CACHE_DIR
    bm25_index_path: Path = BM25_INDEX_PATH
    progress_file: Path = PROGRESS_FILE
    user_guide_path: Path = USER_GUIDE_PATH
    agent_working_dir_inventory: tuple[AgentWorkingDirSpec, ...] = field(
        default_factory=lambda: AGENT_WORKING_DIR_INVENTORY
    )
    agent_protected_subdirs: set[str] = field(
        default_factory=lambda: AGENT_PROTECTED_SUBDIRS
    )
    agent_excluded_subdirs: set[str] = field(
        default_factory=lambda: AGENT_EXCLUDED_SUBDIRS
    )
    scan_roots: list[str] = field(default_factory=lambda: SCAN_ROOTS)
    skip_dirs: set[str] = field(default_factory=lambda: SKIP_DIRS)
    skip_subdirs: set[str] = field(default_factory=lambda: SKIP_SUBDIRS)
    skip_file_patterns: set[str] = field(default_factory=lambda: SKIP_FILE_PATTERNS)
    high_value_include_patterns: set[str] = field(
        default_factory=lambda: HIGH_VALUE_INCLUDE_PATTERNS
    )
    index_extensions: set[str] = field(default_factory=lambda: INDEX_EXTENSIONS)
    max_file_size: int = MAX_FILE_SIZE
    max_content_length: int = MAX_CONTENT_LENGTH
    chunk_size: int = CHUNK_SIZE
    chunk_overlap: int = CHUNK_OVERLAP
    embedding_model: str = EMBEDDING_MODEL
    embedding_dim: int = EMBEDDING_DIM
    embedding_batch_size: int = EMBEDDING_BATCH_SIZE
    embedding_device: str = EMBEDDING_DEVICE
    embedding_backend: str = EMBEDDING_BACKEND
    sqlite_db: Path = SQLITE_DB
    qdrant_path: Path = QDRANT_PATH
    qdrant_mode: str = QDRANT_MODE
    qdrant_url: str = QDRANT_URL
    qdrant_host: str = QDRANT_HOST
    qdrant_port: int = QDRANT_PORT
    qdrant_collection: str = QDRANT_COLLECTION
    categories: list[str] = field(default_factory=lambda: CATEGORIES)
    # Capacity limits
    tier1_max_size: int = TIER1_MAX_SIZE
    tier2_max_size: int = TIER2_MAX_SIZE
    system_dirs: list[str] = field(default_factory=lambda: list(SYSTEM_DIRS))
    chunk_size_by_ext: dict[str, int] = field(
        default_factory=lambda: dict(CHUNK_SIZE_BY_EXT)
    )

    # Classification parameters
    classification_model: str = CLASSIFICATION_MODEL
    classification_batch_size: int = CLASSIFICATION_BATCH_SIZE
    classification_llm_enabled: bool = CLASSIFICATION_LLM_ENABLED
    classification_confidence_threshold: float = CLASSIFICATION_CONFIDENCE_THRESHOLD
    rule_based_fallback: bool = RULE_BASED_FALLBACK
    classification_confidence_fallback_threshold: float = (
        CLASSIFICATION_CONFIDENCE_FALLBACK_THRESHOLD
    )
    enable_reranking: bool = ENABLE_RERANKING
    reranker_model: str = RERANKER_MODEL
    hyde_enabled: bool = HYDE_ENABLED
    hyde_weight: float = HYDE_WEIGHT
    hyde_model: str = HYDE_MODEL
    search: SearchConfig = field(default_factory=SearchConfig)
    use_smart_chunking: bool = USE_SMART_CHUNKING
    ollama_api_url: str = OLLAMA_API_URL
    openrouter_api_key: str = OPENROUTER_API_KEY
    openrouter_base_url: str = OPENROUTER_BASE_URL
    openrouter_model: str = OPENROUTER_MODEL
    memmachine_api_url: str = MEMMACHINE_API_URL
    memmachine_enabled: bool = MEMMACHINE_ENABLED
    memmachine_org_id: str = MEMMACHINE_ORG_ID
    memmachine_project_id: str = MEMMACHINE_PROJECT_ID
    duplicate_hash_size: int = DUPLICATE_HASH_SIZE
    semantic_similarity_threshold: float = SEMANTIC_SIMILARITY_THRESHOLD
    dashboard_host: str = DASHBOARD_HOST
    dashboard_port: int = DASHBOARD_PORT
    log_level: str = LOG_LEVEL
    log_file: str = LOG_FILE

    def __post_init__(self):
        self.system_dirs = list(self.system_dirs or SYSTEM_DIRS)
        self.chunk_size_by_ext = dict(self.chunk_size_by_ext or CHUNK_SIZE_BY_EXT)


# Global config instance
config = FileMindConfig()


def ensure_dirs():
    """Create required directories if they don't exist."""
    config.index_dir.mkdir(parents=True, exist_ok=True)
    if config.qdrant_mode == "local":
        config.qdrant_path.mkdir(parents=True, exist_ok=True)
