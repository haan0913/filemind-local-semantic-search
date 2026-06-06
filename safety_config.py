"""
FileMind Safety Configuration

Defines three tiers of file/directory safety for migration operations:
  IMMUTABLES  — NEVER move, delete, or modify. Breaking these breaks programs.
  PROTECTED   — Move only with explicit user approval. Contains code/configs that may be referenced.
  MOVABLES    — Safe to reorganize. Duplicates, backups, generated noise, logs.

Phase 1 (current): Only MOVABLES are candidates. IMMUTABLES/PROTECTED are read-only.
Phase 2 (future): PROTECTED can be migrated with dependency resolution.
Phase 3 (future): Full intelligent migration with reference scanning.
"""

from pathlib import Path

try:
    from .config import config
except ImportError:
    from config import config

# ═══════════════════════════════════════════════════════════════════════════
# IMMUTABLES — NEVER TOUCH
# ═══════════════════════════════════════════════════════════════════════════
# These contain executables, binaries, active dependencies, or critical state.
# Moving any of these WILL break programs.
#
# Rule: These are INVISIBLE to migration. They don't appear as candidates.
# ═══════════════════════════════════════════════════════════════════════════
IMMUTABLES: list[str] = [
    # ── Python Environments (breaks all Python programs) ──
    r"C:\Users\amirk\.kimi\owl-agent\.venv",
    r"C:\AI_STATION\filemind\.venv",
    r"**/.venv/**",
    r"**/venv/**",
    r"**/site-packages/**",
    r"**/Lib/**",
    r"**/__pycache__/**",

    # ── Ollama (breaks all local AI models) ──
    r"C:\Users\amirk\AppData\Local\Programs\Ollama",
    r"**/.ollama/**",

    # ── Node.js / npm (breaks JS tools) ──
    r"**/node_modules/**",

    # ── Git repositories (breaks version control) ──
    r"**/.git/**",

    # ── Windows system (obviously) ──
    r"C:\Windows",
    r"C:\Program Files",
    r"C:\Program Files (x86)",
    r"C:\ProgramData",

    # ── Active agent configs (agents reference these by path) ──
    r"C:\Users\amirk\.claude\settings.local.json",
    r"C:\Users\amirk\.kimi\config.toml",
    r"C:\Users\amirk\.kimi\kimi.json",
    r"C:\Users\amirk\.kimi\device_id",
    r"C:\Users\amirk\.kimi\credentials",

    # ── Claude config backups found during scan ──
    r"C:\AI_STATION\claude_config\.claude\projects",  # Claude project configs

    # ── FileMind own infrastructure ──
    str(config.index_dir),             # Qdrant vector DB + SQLite
    r"C:\AI_STATION\filemind\run.py",   # CLI entry point
    r"C:\AI_STATION\filemind\config.py", # Central config
    r"C:\AI_STATION\filemind\vector_store.py",
    r"C:\AI_STATION\filemind\embedder.py",
    r"C:\AI_STATION\filemind\catalog.py",
    r"C:\AI_STATION\filemind\safety_config.py",  # This file itself

    # ── API Keys & Credentials (paths hardcoded in other tools) ──
    r"C:\AI_HUB\.env",
    r"C:\AI_STATION\hub\.env",
    r"C:\AI_STATION\config\.env",
    r"C:\AI_STATION\security\keys",
]

# ═══════════════════════════════════════════════════════════════════════════
# PROTECTED — REQUIRE EXPLICIT APPROVAL
# ═══════════════════════════════════════════════════════════════════════════
# These are active code, research, project files. Moving them is safe IF
# no other program references them by absolute path. Phase 2 will scan for
# references before allowing migration.
#
# Rule: These appear as candidates but REQUIRE user confirmation before move.
# ═══════════════════════════════════════════════════════════════════════════
PROTECTED: list[str] = [
    # ── Active Project Code ──
    r"C:\AI_STATION\filemind",           # FileMind itself (excluding immutables above)
    r"C:\AI_STATION\owl-agent",          # OWL framework source
    r"C:\Users\amirk\pc-focus",          # Personal project
    # Note: Obsidian Vault not found at C:/Users/amirk/Obsidian Vault — check actual path

    # ── User Home Directory Config (scan roots) ──
    r"C:\Users\amirk\.kimi",             # Kimi agent (active configs, not runtime)
    r"C:\Users\amirk\.cline",            # Cline agent configs
    r"C:\Users\amirk\.claude",           # Claude agent configs
    r"C:\Users\amirk\.openclaw",         # OpenClaw agent configs
    r"C:\Users\amirk\.agents",           # Agent specifications

    # ── Project Work ──
    r"C:\AI_STATION\projects",           # Various project folders
    r"C:\AI_STATION\hub",                # AI Hub project
    r"C:\AI_STATION\agents",             # Agent specifications
    r"C:\AI_STATION\commands",           # Command specifications
    r"C:\AI_STATION\plugins",            # Plugin marketplace

    # ── Research ──
    r"C:\AI_STATION\filemind_research",
    r"C:\AI_STATION\filemind\docs",

    # ── Source Code ──
    r"C:\AI_STATION\source",             # MemMachine and other source

    # ── Config & Security ──
    r"C:\AI_STATION\config",             # API keys and configs
    r"C:\AI_STATION\security",           # Security keys

    # ── User Config Files ──
    r"C:\Users\amirk\.bashrc",
    r"C:\Users\amirk\.bash_profile",
    r"C:\Users\amirk\.zshrc",
    r"C:\Users\amirk\.gitconfig",
    r"C:\Users\amirk\.claude.json",
]

# ═══════════════════════════════════════════════════════════════════════════
# MOVABLES — SAFE TO REORGANIZE
# ═══════════════════════════════════════════════════════════════════════════
# These are duplicates, backups, generated noise, or archived content.
# Moving them has no impact on running programs.
#
# Rule: These are primary migration candidates. Can be moved/archive/delete
# with minimal risk. Log everything for audit trail.
# ═══════════════════════════════════════════════════════════════════════════
MOVABLES: list[str] = [
    # ── Vault Backups (confirmed duplicates) ──
    r"C:\AI_STATION\filemind\vault",
    r"C:\AI_STATION\filemind\vault\**",

    # ── Session Backup Snapshots (timestamped vault copies) ──
    # These are from the smart chunking rebuild session
    r"C:\AI_STATION\filemind\vault\filemind_2026-04-08_FINAL-session-complete",
    r"C:\AI_STATION\filemind\vault\filemind_2026-04-08_phase0-dense-only",
    r"C:\AI_STATION\filemind\vault\filemind_2026-04-08_sessionA-agent-loop",
    r"C:\AI_STATION\filemind\vault\filemind_2026-04-08_sessionB-kpi-swarm",
    r"C:\AI_STATION\filemind\vault\filemind_2026-04-08_sessionB-learning-system",
    r"C:\AI_STATION\filemind\vault\filemind_code_backup_20260408_103500",
    r"C:\AI_STATION\filemind\vault\docs_backup_20260408_103500",

    # ── Code Backup Copies ──
    r"**/code_backup_*",

    # ── Nested Duplicate Directories (triple-nested copies) ──
    r"C:\AI_STATION\plugins\plugins\**",
    r"C:\AI_STATION\commands\commands\**",
    r"C:\AI_STATION\agents\agents\**",

    # ── Log Files (generated output, safe to archive) ──
    r"**/*.log",

    # ── Temporary / Generated Files ──
    r"**/.aider.tags.cache.v3",
    r"**/.aider.chat.history.md",
    r"**/.aider.input.history",

    # ── Old Scan Root Artifacts ──
    r"C:\AI_STATION\AI STAION",          # Typo directory (note the missing space position)

    # ── Subagent Tool Results (noisy JSON) ──
    r"**/tool-results/*.txt",
    r"**/subagents/agent-*.meta.json",

    # ── Claude config backups (copies, not active) ──
    r"C:\AI_STATION\claude_config",

    # ── Git History Dumps / Large Generated Files ──
    r"**/*.bak",
    r"**/*.tmp",
    r"**/*.swp",
]


def is_immutable(path: str) -> bool:
    """Check if a path is in the IMMUTABLES list (must NEVER be moved)."""
    path_lower = path.lower().replace("\\", "/")
    for pattern in IMMUTABLES:
        pattern_lower = pattern.lower().replace("\\", "/")
        # Exact match or glob match
        if path_lower == pattern_lower or path_lower.startswith(pattern_lower.rstrip("*")):
            if "**" in pattern_lower:
                import fnmatch
                if fnmatch.fnmatch(path_lower, pattern_lower):
                    return True
            else:
                return True
    return False


def is_protected(path: str) -> bool:
    """Check if a path is in the PROTECTED list (requires approval)."""
    path_lower = path.lower().replace("\\", "/")
    for pattern in PROTECTED:
        pattern_lower = pattern.lower().replace("\\", "/")
        if path_lower == pattern_lower or path_lower.startswith(pattern_lower.rstrip("*")):
            if "**" in pattern_lower:
                import fnmatch
                if fnmatch.fnmatch(path_lower, pattern_lower):
                    return True
            else:
                return True
    return False


def is_movable(path: str) -> bool:
    """Check if a path matches MOVABLES patterns (safe to reorganize)."""
    path_lower = path.lower().replace("\\", "/")
    for pattern in MOVABLES:
        pattern_lower = pattern.lower().replace("\\", "/")
        if "**" in pattern_lower:
            import fnmatch
            if fnmatch.fnmatch(path_lower, pattern_lower):
                return True
        else:
            if path_lower == pattern_lower or path_lower.startswith(pattern_lower.rstrip("*")):
                return True
    return False


def classify_safety(path: str) -> str:
    """Return safety classification: 'IMMUTABLE', 'PROTECTED', 'MOVABLE', or 'UNCLASSIFIED'."""
    if is_immutable(path):
        return "IMMUTABLE"
    if is_protected(path):
        return "PROTECTED"
    if is_movable(path):
        return "MOVABLE"
    return "UNCLASSIFIED"
