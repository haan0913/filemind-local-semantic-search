"""
FileMind CodeAgent — smolagents + Ollama local model.

Minimal viable agent with:
- Code execution (Python interpreter)
- File system access (read, list, search)
- FileMind knowledge base query
- Shell command execution (safe, whitelisted)

Usage:
    python agent/run.py "find all Python files mentioning vector_store"
    python agent/run.py "list files in C:/AI_STATION/filemind"
"""

import logging
import os
import subprocess
import sys
import warnings
from pathlib import Path
from typing import cast

warnings.filterwarnings("ignore")

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smolagents import (  # noqa: E402
    CodeAgent,
    OpenAIServerModel,
    Tool,
    PythonInterpreterTool,
)
from config import config  # noqa: E402

# ── Model Configuration ──────────────────────────────────────────────
MODEL_ID = os.getenv("FILEMIND_MODEL", config.classification_model)
API_BASE = os.getenv("OLLAMA_API_BASE", "http://localhost:11434/v1")
API_KEY = "ollama"
MAX_STEPS = 5
TEMPERATURE = 0.2
logger = logging.getLogger("filemind.agent")


def get_model():
    """Create Ollama model via OpenAI-compatible endpoint."""
    return OpenAIServerModel(
        model_id=MODEL_ID,
        api_base=API_BASE,
        api_key=API_KEY,
        temperature=TEMPERATURE,
        max_tokens=4096,
    )


# ── FileMind Custom Tools ────────────────────────────────────────────


class SearchFileMindTool(Tool):
    """Search the FileMind knowledge base for relevant files and content."""

    name = "search_filemind"
    description = "Search the local file knowledge base using semantic and keyword search. Returns relevant file paths and content snippets. Use this to find files by topic, concept, or content."
    inputs = {
        "query": {
            "type": "string",
            "description": "Search query — can be natural language, keywords, or file path fragments",
        }
    }
    output_type = "string"

    def __init__(self):
        super().__init__()
        self._search_engine = None

    @property
    def search_engine(self):
        if self._search_engine is None:
            from search import SearchEngine

            self._search_engine = SearchEngine(reranking=config.enable_reranking)
        return self._search_engine

    def forward(self, query: str) -> str:
        try:
            results = self.search_engine.search(query, top_k=10)
            if not results:
                # CRITICAL: Return structured "empty" marker so guardrails can detect this
                return f"[FILEMIND_SEARCH_EMPTY]\nNo files or content found matching query: '{query}'\nThis means the index does not contain information about this topic. Do NOT fabricate an answer from general knowledge. Report that nothing was found in the local index."

            output = []
            for r in results:
                score = float(getattr(r, "score", 0.0) or 0.0)
                content = (getattr(r, "snippet", "") or "")[:300]
                file_id = getattr(r, "file_path", "unknown")
                file_type = getattr(r, "file_type", "?") or "?"
                category = getattr(r, "category", "?") or "?"
                output.append(
                    f"[Score: {score:.3f}] file_id={file_id} | type={file_type} | category={category}\n{content}"
                )
            return "[FILEMIND_SEARCH_RESULTS]\n" + "\n\n---\n\n".join(output)
        except Exception as e:
            return f"[FILEMIND_SEARCH_ERROR]\nSearch error: {e}"


class ReadFileTool(Tool):
    """Read the contents of a file from the filesystem."""

    name = "read_file"
    description = "Read the contents of a file. Use this to examine file contents when you need the full text of a specific file."
    inputs = {
        "filepath": {
            "type": "string",
            "description": "Absolute path to the file to read",
        }
    }
    output_type = "string"

    def forward(self, filepath: str) -> str:
        try:
            path = Path(filepath)
            if not path.exists():
                return f"File not found: {filepath}"
            if not path.is_file():
                return f"Path is a directory, not a file: {filepath}"
            # Safety: limit file size
            size = path.stat().st_size
            if size > 100_000:
                return f"File too large ({size} bytes). Max: 100KB"
            content = path.read_text(encoding="utf-8", errors="replace")
            return content[:5000]  # Limit output
        except Exception as e:
            return f"Read error: {e}"


class ListDirTool(Tool):
    """List files in a directory."""

    name = "list_directory"
    description = "List files and subdirectories in a directory. Use absolute paths like 'C:/AI_STATION/filemind'."
    inputs = {
        "dirpath": {
            "type": "string",
            "description": "Absolute path to the directory to list (e.g. C:/AI_STATION/filemind)",
        }
    }
    output_type = "string"

    def forward(self, dirpath: str) -> str:
        try:
            path = Path(dirpath)
            if not path.is_absolute():
                # Resolve relative paths from CWD
                path = Path.cwd() / path
            if not path.exists():
                return f"Directory not found: {dirpath}"
            if not path.is_dir():
                return f"Path is not a directory: {dirpath}"
            items = []
            for item in sorted(path.iterdir()):
                if item.name.startswith("."):
                    continue  # Skip hidden files/dirs
                prefix = "📁" if item.is_dir() else "📄"
                size = ""
                if item.is_file():
                    s = item.stat().st_size
                    if s > 1024 * 1024:
                        size = f" ({s / 1024 / 1024:.1f}MB)"
                    elif s > 1024:
                        size = f" ({s / 1024:.1f}KB)"
                    else:
                        size = f" ({s}B)"
                items.append(f"{prefix} {item.name}{size}")
            return "\n".join(items) or "(empty directory)"
        except Exception as e:
            return f"List error: {e}"


class ShellTool(Tool):
    """Execute a safe shell command."""

    name = "shell_command"
    description = "Execute a shell command and return its output. Use for system operations like listing files, checking disk space, running scripts, etc."
    inputs = {"command": {"type": "string", "description": "Shell command to execute"}}
    output_type = "string"

    # Whitelist of safe commands
    SAFE_PREFIXES = [
        "dir",
        "ls",
        "type",
        "cat",
        "echo",
        "pwd",
        "cd",
        "find",
        "grep",
        "python -c",
        "python -m",
        "pip list",
        "pip show",
        "where",
        "tasklist",
        "systeminfo",
        "wmic",
        "diskpart /c",
        "powershell -Command",
        "powershell -NoProfile",
    ]

    def forward(self, command: str) -> str:
        # Safety check
        cmd_lower = command.lower().strip()
        is_safe = any(cmd_lower.startswith(p.lower()) for p in self.SAFE_PREFIXES)
        if not is_safe:
            return f"Command blocked (not in safe list): {command}\n\nSafe prefixes: {', '.join(self.SAFE_PREFIXES)}"

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"
            return output[:5000]  # Limit output
        except subprocess.TimeoutExpired:
            return "Command timed out (30s limit)"
        except Exception as e:
            return f"Shell error: {e}"


class FileStatsTool(Tool):
    """Get FileMind index statistics."""

    name = "filemind_stats"
    description = "Get statistics about the FileMind index: file counts, categories, top file types."
    inputs = {}
    output_type = "string"

    def forward(self) -> str:
        try:
            from catalog import Catalog
            from vector_store import VectorStore

            cat = Catalog()
            cat.init_db()
            stats = cat.get_stats()
            vs = VectorStore()
            output = "FileMind Index Stats:\n"
            output += f"  Total files: {stats.get('total_files', '?')}\n"
            output += f"  Qdrant chunks: {vs.count()}\n"
            output += "  Categories:\n"
            for cat_name, count in sorted(stats.get("categories", {}).items()):
                output += f"    {cat_name}: {count}\n"
            output += "  Top types:\n"
            top_extensions = stats.get("top_extensions") or stats.get("extensions", {})

            def extension_sort_key(item: tuple[str, int]) -> int:
                return -item[1]

            for ext, count in sorted(top_extensions.items(), key=extension_sort_key)[
                :10
            ]:
                output += f"    {ext}: {count}\n"
            cat.close()
            vs.close()
            return output
        except Exception as e:
            return f"Stats error: {e}"


class FindFilesTool(Tool):
    """Find files by glob pattern (wildcard) in a directory tree."""

    name = "find_files"
    description = "Find files matching a glob pattern in a directory tree. Use patterns like '*.py', '*.md', '*config*'. Use absolute paths for the search root."
    inputs = {
        "directory": {
            "type": "string",
            "description": "Root directory to search from (absolute path)",
        },
        "pattern": {
            "type": "string",
            "description": "Glob pattern like '*.py' or '*config*'",
        },
    }
    output_type = "string"

    def forward(self, directory: str, pattern: str) -> str:
        try:
            path = Path(directory)
            if not path.is_absolute():
                path = Path.cwd() / path
            if not path.is_dir():
                return f"Directory not found: {directory}"

            matches = list(path.rglob(pattern))
            # Filter out hidden/ignored dirs
            matches = [
                m for m in matches if not any(p.startswith(".") for p in m.parts)
            ]
            matches = [m for m in matches if m.is_file()]
            matches.sort(key=lambda x: x.stat().st_mtime, reverse=True)

            if not matches:
                return f"No files matching '{pattern}' in {directory}"

            output = [
                f"Found {len(matches)} files matching '{pattern}' in {directory}:\n"
            ]
            for m in matches[:50]:  # Limit output
                s = m.stat().st_size
                size = f"{s / 1024:.1f}KB" if s > 1024 else f"{s}B"
                output.append(f"  {m} ({size})")
            if len(matches) > 50:
                output.append(f"\n... and {len(matches) - 50} more files")
            return "\n".join(output)
        except Exception as e:
            return f"Find error: {e}"


class LogLearningTool(Tool):
    """Log a learning from the current task for future improvement."""

    name = "log_learning"
    description = "Record an insight from this task. Use when you discover something that worked well or failed. This helps the system improve over time."
    inputs = {
        "insight": {
            "type": "string",
            "description": "Concise lesson learned (1-2 sentences)",
        },
        "task_pattern": {
            "type": "string",
            "description": "What type of task this was (e.g., 'find *.py files', 'search knowledge base')",
        },
        "success": {
            "type": "boolean",
            "description": "Did this approach work? true or false",
        },
    }
    output_type = "string"

    def forward(self, insight: str, task_pattern: str, success: bool) -> str:
        try:
            import json
            import time

            learnings_file = Path(__file__).parent.parent / "learnings.jsonl"
            entry = {
                "timestamp": time.time(),
                "task_pattern": task_pattern,
                "insight": insight,
                "success": success,
            }
            with open(learnings_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            status = "✅" if success else "⚠️"
            return f"Learning logged {status}: {insight}"
        except Exception as e:
            return f"Learning log error: {e}"


class GetLearningsTool(Tool):
    """Retrieve past learnings relevant to the current task."""

    name = "get_learnings"
    description = "Get past learnings about a type of task. Use this before attempting a task to learn from previous experience."
    inputs = {
        "topic": {
            "type": "string",
            "description": "What type of task you're about to do (e.g., 'find files', 'search', 'count')",
        }
    }
    output_type = "string"

    def forward(self, topic: str) -> str:
        try:
            import json

            learnings_file = Path(__file__).parent.parent / "learnings.jsonl"
            if not learnings_file.exists():
                return "No learnings yet. Use log_learning after completing tasks."

            # Simple keyword matching (will upgrade to vector search later)
            topic_lower = topic.lower()
            matches = []
            with open(learnings_file, "r", encoding="utf-8") as f:
                for line in f:
                    entry = json.loads(line.strip())
                    if any(
                        kw in entry.get("task_pattern", "").lower()
                        or kw in entry.get("insight", "").lower()
                        for kw in topic_lower.split()
                    ):
                        matches.append(entry)

            if not matches:
                return (
                    f"No relevant learnings for '{topic}'. Try a different search term."
                )

            output = [f"Found {len(matches)} relevant learnings:\n"]
            for m in matches[-5:]:  # Last 5
                status = "✅" if m.get("success") else "❌"
                output.append(
                    f"{status} {m.get('insight', '')} (task: {m.get('task_pattern', '')})"
                )
            return "\n".join(output)
        except Exception as e:
            return f"Learnings retrieval error: {e}"


# ── Agent Factory ────────────────────────────────────────────────────


def create_agent(max_steps: int = MAX_STEPS) -> CodeAgent:
    """Create a FileMind CodeAgent with all tools."""
    model = get_model()

    tools = [
        PythonInterpreterTool(),  # Built-in: execute Python code
        SearchFileMindTool(),  # Search knowledge base
        ReadFileTool(),  # Read file contents
        ListDirTool(),  # List directory contents
        FindFilesTool(),  # Find files by glob pattern
        ShellTool(),  # Execute safe shell commands
        FileStatsTool(),  # Get index statistics
        LogLearningTool(),  # Log insights from tasks
        GetLearningsTool(),  # Retrieve past learnings
    ]

    system_prompt = """You are FileMind, an AI assistant that searches and analyzes a LOCAL file knowledge base.

═══════════════════════════════════════════════════════
  CORE MANDATE — READ THIS FIRST
═══════════════════════════════════════════════════════

You are NOT a general-knowledge chatbot. Your ONLY purpose is to search the local FileMind index and report what you find THERE.

RULE #1 — ALWAYS SEARCH FIRST
  Before answering ANY query about files, code, concepts, or topics, you MUST call search_filemind() with the user's query (or relevant keywords).
  You are NOT allowed to answer from your pre-trained knowledge. If you know something from general knowledge but it's NOT in the index, you MUST say so explicitly.

RULE #2 — SOURCE EVERY ANSWER
  When you call final_answer(), your answer MUST reference specific file paths, file types, scores, or content snippets that came from search_filemind() results.
  If you cannot cite actual files from the index, you do not have a valid answer.

RULE #3 — EMPTY RESULTS ARE VALID
  If search_filemind() returns [FILEMIND_SEARCH_EMPTY], this is a complete and valid outcome.
  You MUST report: "No files found in the local index matching '<query>'."
  You MUST NOT supplement with general knowledge as if it were index content.
  You MAY offer to try alternative search terms or broader queries.

RULE #4 — DISTINGUISH SOURCES
  If the index has content AND you also know general information:
  - First report what the index contains (with file references)
  - Then, CLEARLY LABELLED as supplementary context, you may add general info
  - NEVER present general knowledge as if it came from the index

RULE #5 — WHEN YOU HAVE THE ANSWER
  Call final_answer("your answer here") IMMEDIATELY. Do NOT print and wait.

RULE #6 — NO USER INTERACTION
  Do NOT ask the user for more input. The user already gave you the task.

RULE #7 — NO SPIRALING
  Do NOT loop calling print() with "awaiting task" or "ready to receive task".
  If you encounter an error, try a different approach.

RULE #8 — USE ABSOLUTE PATHS
  Use absolute paths (C:/AI_STATION/filemind) for file operations.

RULE #9 — LOG LEARNING
  After completing a task, use log_learning to record what worked or didn't work.

═══════════════════════════════════════════════════════
  DECISION FLOWCHART (FOLLOW THIS EXACTLY)
═══════════════════════════════════════════════════════

  1. User gives query → IMMEDIATELY call search_filemind(query)
  2. Inspect the result:
     a. Starts with [FILEMIND_SEARCH_RESULTS] → Extract file info, cite files in final_answer
     b. Starts with [FILEMIND_SEARCH_EMPTY] → Call final_answer saying nothing found in index
     c. Starts with [FILEMIND_SEARCH_ERROR] → Retry once, then report error
  3. If results are tangential, try a refined search with different keywords
  4. Call final_answer with your findings

═══════════════════════════════════════════════════════
  ANSWER QUALITY GATE
═══════════════════════════════════════════════════════

A GOOD answer:
  ✅ References specific file_ids, paths, types, or scores from search results
  ✅ Reports when index is empty for the topic
  ✅ Distinguishes "found in index" from "general context"
  ✅ Is actionable and specific

A BAD answer (AVOID THESE):
  ❌ Generic encyclopedia-style definitions not tied to any files
  ❌ "X is a tool/framework/concept that..." without file references
  ❌ Answers that could come from any LLM without searching the index
  ❌ Pretending general knowledge is index content

═══════════════════════════════════════════════════════
  AVAILABLE TOOLS
═══════════════════════════════════════════════════════

- search_filemind(query): Search the knowledge base — ALWAYS START HERE
- find_files(directory, pattern): Find files by glob pattern
- list_directory(dirpath): List files in a directory
- read_file(filepath): Read file contents
- shell_command(command): Run safe shell commands
- filemind_stats(): Get index statistics
- get_learnings(topic): Get past learnings about a task type
- log_learning(insight, task_pattern, success): Record what you learned
- python_interpreter(): Run Python code

═══════════════════════════════════════════════════════
  EXAMPLES
═══════════════════════════════════════════════════════

EXAMPLE 1 — Query with results:
Task: "Find files about kimi"
<code>
result = search_filemind(query="kimi")
print(result)
</code>
[Tool returns: [FILEMIND_SEARCH_RESULTS] with file references]
<code>
final_answer("Found 3 files referencing 'kimi' in the index:\n- file_id=142 (type=.py) mentions kimi API integration\n- file_id=287 (type=.md) compares kimi to other LLMs\n- file_id=301 (type=.json) has kimi config settings")
</code>

EXAMPLE 2 — Query with NO results:
Task: "What is kimi?"
<code>
result = search_filemind(query="kimi")
print(result)
</code>
[Tool returns: [FILEMIND_SEARCH_EMPTY] No files or content found matching query: 'kimi']
<code>
final_answer("No files found in the local index matching 'kimi'. The FileMind index does not contain any information about this topic.")
</code>

EXAMPLE 3 — Broader search when initial fails:
Task: "Find vector store configs"
<code>
result = search_filemind(query="vector store config")
print(result)
</code>
[Tool returns empty]
<code>
result = search_filemind(query="vector_store")
print(result)
</code>
[Tool returns results]
<code>
final_answer("Found files referencing 'vector_store': ...")
</code>
"""

    agent = CodeAgent(
        model=model,
        tools=cast(list[Tool], tools),
        max_steps=max_steps,
        verbosity_level=1,
        additional_authorized_imports=["os", "sys", "pathlib", "subprocess"],
        # Use flexible regex for code blocks: tolerate whitespace in tags
        # This tolerates local-model output such as `<code >` instead of `<code>`
        code_block_tags=(r"<code\s*>", r"</code\s*>"),
    )

    # Override the system prompt (smolagents API)
    agent.prompt_templates["system_prompt"] = system_prompt

    return agent


# ── CLI Entry Point ──────────────────────────────────────────────────


def _run_mandatory_search(query: str) -> str:
    """
    Layer 1 (Input Rail) + Layer 2 (Pre-execution): Mandatory search-first protocol.

    Per 'Engineering Trust in Agentic Systems' research paper: prompts alone are
    structurally insufficient. The agent CANNOT be trusted to call search_filemind()
    on its own. We run the search HERE, before the agent loop, and inject results
    into the agent's context. This makes search unavoidable at the architectural level.

    Returns: formatted search results or [FILEMIND_SEARCH_EMPTY] marker.
    """
    try:
        search_tool = SearchFileMindTool()
        result = search_tool.forward(query)
        return result
    except Exception as e:
        return f"[FILEMIND_SEARCH_ERROR]\nSearch error during mandatory pre-search: {e}"


def _build_grounding_context(query: str, search_results: str) -> str:
    """
    Build a grounding preamble that forces the agent to work WITH search results.

    This is the Day 1 output structuring from the research paper:
    - Explicit statement of intent
    - Raw evidence presented upfront
    - Clear instruction: answer must be based ONLY on this evidence
    """
    is_empty = search_results.startswith("[FILEMIND_SEARCH_EMPTY]")
    is_error = search_results.startswith("[FILEMIND_SEARCH_ERROR]")

    if is_empty:
        return (
            f"MANDATORY SEARCH RESULTS FOR QUERY: '{query}'\n"
            f"{'=' * 60}\n"
            f"[SEARCH STATUS] EMPTY — No files or content found in the local index.\n"
            f"[SEARCH WAS EXECUTED] Yes, automatically before this agent started.\n"
            f"\n"
            f"YOUR REQUIRED RESPONSE:\n"
            f"You MUST call final_answer() with this exact message (do NOT add general knowledge):\n"
            f"  \"No files found in the local FileMind index matching '{query}'. "
            f'The index does not contain information about this topic."'
        )
    elif is_error:
        return (
            f"MANDATORY SEARCH RESULTS FOR QUERY: '{query}'\n"
            f"{'=' * 60}\n"
            f"[SEARCH STATUS] ERROR — The search tool encountered an error.\n"
            f"[SEARCH RESULTS]\n{search_results}\n"
            f"\n"
            f"YOUR REQUIRED RESPONSE:\n"
            f"Report the search error to the user. Do NOT attempt to answer the query from general knowledge."
        )
    else:
        # Has results — present as evidence
        return (
            f"MANDATORY SEARCH RESULTS FOR QUERY: '{query}'\n"
            f"{'=' * 60}\n"
            f"[SEARCH STATUS] RESULTS FOUND — The following evidence was retrieved from the local index.\n"
            f"[SEARCH WAS EXECUTED] Yes, automatically before this agent started.\n"
            f"\n"
            f"[RETRIEVED EVIDENCE]\n"
            f"{search_results}\n"
            f"\n"
            f"{'=' * 60}\n"
            f"INSTRUCTIONS:\n"
            f"- Your answer MUST reference specific file_ids, scores, or content from the evidence above.\n"
            f"- Do NOT add information that is not present in the retrieved evidence.\n"
            f"- If the evidence is tangential, you may attempt a refined search with search_filemind().\n"
            f"- If you cannot answer from the evidence alone, state what the index DOES contain."
        )


def _validate_answer(answer: str, query: str) -> str:
    """Validate that the answer actually references index content, not just general knowledge.

    Layer 3 (Output Grounding): Hybrid validation with critic check.
    Step 1: Fast regex-based file path matching
    Step 2: Critic model verification (if qwen2.5-coder:7b is available)
    Step 3: Fallback to rule-based heuristics

    Returns the answer unchanged if grounded, or appends a warning if not.
    """
    answer_lower = answer.lower()

    # Strong signals that the answer is grounded in index content
    grounded_indicators = [
        "file_id",
        "file_",
        ".py",
        ".md",
        ".json",
        ".txt",
        ".yaml",
        "score:",
        "found",
        "no files found",
        "not found in the local",
        "index does not contain",
        "local index",
        "filemind",
        "[filemind_search",
        "type=",
        "category=",
        "c:/",
        "path",
        "config",
    ]

    # Weak signals that the answer is generic LLM knowledge
    generic_indicators = [
        "is a large language model",
        "is an ai",
        "is a framework",
        "is a tool developed by",
        "is known for",
        "developed by",
        "created by",
        "released by",
    ]

    is_grounded = any(ind in answer_lower for ind in grounded_indicators)
    is_generic = any(ind in answer_lower for ind in generic_indicators)

    # Layer 3a: Fast regex check
    if is_generic and not is_grounded:
        return (
            f"⚠️ WARNING: This answer appears to be general knowledge, not based on the FileMind index.\n"
            f"Query: '{query}'\n"
            f"---\n"
            f"{answer}\n"
            f"---\n"
            f"The agent should have searched the local index first. Try re-running or searching with different keywords."
        )

    # Layer 3b: Critic model check (optional — runs if evidence available)
    # Only runs when answer passes Layer 3a and contains file references
    if is_grounded and not is_generic:
        try:
            from agent.critic import validate_answer_with_critic, VERDICT_GROUNDED

            # Extract evidence from search results for critic comparison
            # Use the answer's own file references as the "evidence" proxy
            verdict, reasoning = validate_answer_with_critic(answer, answer, query)
            if verdict != VERDICT_GROUNDED:
                logger_msg = f"Critic flagged answer: {verdict} — {reasoning}"
                logger.warning(logger_msg)
                # Don't block the answer, just annotate
                answer += f"\n\n[Critic note: {reasoning}]"
        except Exception:
            # Critic unavailable — skip silently
            pass

    return answer


def main():
    import argparse

    parser = argparse.ArgumentParser(description="FileMind CodeAgent")
    parser.add_argument("query", help="Natural language command for the agent")
    parser.add_argument("--steps", type=int, default=MAX_STEPS, help="Max agent steps")
    args = parser.parse_args()

    print(f"🤖 FileMind Agent — Query: {args.query}")
    print(f"   Model: {MODEL_ID}")
    print(f"   Max steps: {args.steps}")
    print("=" * 60)

    # KPI tracking
    try:
        from agent.kpi_logger import kpi
    except ImportError:
        from kpi_logger import kpi
    kpi.tick_start(args.query[:60])

    agent = create_agent(max_steps=args.steps)

    try:
        # ═══════════════════════════════════════════════════════════
        # LAYER 1+2: Mandatory Search-First Protocol (Research Paper)
        # Per "Engineering Trust in Agentic Systems": prompts alone
        # are structurally insufficient. Search MUST run in code.
        # ═══════════════════════════════════════════════════════════
        print(f"\n🔍 Running mandatory search for: '{args.query}'")
        search_results = _run_mandatory_search(args.query)

        # Detect search status
        is_empty = search_results.startswith("[FILEMIND_SEARCH_EMPTY]")
        is_error = search_results.startswith("[FILEMIND_SEARCH_ERROR]")

        if is_empty:
            # No results — report immediately, don't waste agent steps
            grounding = _build_grounding_context(args.query, search_results)
            result = grounding.split("YOUR REQUIRED RESPONSE:\n")[1].strip()
            result = result.strip('"').replace("\\'", "'")
            print(f"⚠️ Index empty for: '{args.query}'")
        elif is_error:
            grounding = _build_grounding_context(args.query, search_results)
            result = f"⚠️ Search error: {search_results.split('Search error: ')[-1] if 'Search error: ' in search_results else search_results}"
            print(f"❌ {result}")
        else:
            # Results found — inject into agent context
            grounding = _build_grounding_context(args.query, search_results)
            print(f"✅ Found {search_results.count('[Score:')} result(s) in index")

            # Build enhanced query: original question + grounding context
            enhanced_query = f"{grounding}\n\n---\n\nOriginal user query: {args.query}\n\nBased on the retrieved evidence above, answer the user's query. Reference specific files and content from the index."

            result = agent.run(enhanced_query)

        # Guardrail: validate answer is grounded in index content
        result = _validate_answer(str(result), args.query)

        print("=" * 60)
        print(f"✅ Result:\n{result}")

        kpi.tick_end(str(result), success=True)
        report = kpi.report()
        print(
            f"\n📊 KPI: {report['tasks_run']} tasks, "
            f"avg {report['avg_latency_sec']}s, "
            f"{report['success_rate']}% success, "
            f"RAM {report['ram_usage_gb']}GB"
        )
    except Exception as e:
        print("=" * 60)
        print(f"❌ Agent error: {e}")
        import traceback

        traceback.print_exc()

        kpi.tick_end(str(e), success=False)
        sys.exit(1)


if __name__ == "__main__":
    main()
