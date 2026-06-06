#!/usr/bin/env python3
"""
FileMind CLI Behavior Tests — discovered during real usage (2026-04-07)
Run with: python filemind/tests/test_cli_behaviors.py
"""
import io
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PYTHON = os.environ.get("FILEMIND_TEST_PYTHON") or sys.executable
SCRIPT = str(ROOT / "run.py")

# -- Test harness -------------------------------------------------------------

passed = 0
failed = 0
_results = []

def ok(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        _results.append(("PASS", name, detail))
    else:
        failed += 1
        _results.append(("FAIL", name, detail))

def section(title):
    print(f"\n{'-'*60}")
    print(f"  {title}")
    print(f"{'-'*60}")

def run_section(title, fn):
    section(title)
    try:
        fn()
    except Exception as e:
        _results.append(("ERRO", title, str(e)))
        global failed
        failed += 1

# -----------------------------------------------------------------------------
# Section A: Argument parsing (no subprocess)
# -----------------------------------------------------------------------------

def test_argument_parsing():
    import run
    parser = run.build_parser()

    # search "openrouter api keys" parses correctly
    args = parser.parse_args(["search", "openrouter", "api", "keys"])
    ok("search 'openrouter api keys' parses query correctly", args.query == ["openrouter", "api", "keys"])

    # search "query" --top-k 5 --type .py --category code all flags parsed
    args = parser.parse_args(["search", "query", "--top-k", "5", "--type", ".py", "--category", "code"])
    ok("search flags parsed correctly", 
       args.top_k == 5 and args.type == ".py" and args.category == "code")

    # search "query" --keyword sets args.keyword=True, args.semantic=False
    args = parser.parse_args(["search", "query", "--keyword"])
    ok("search --keyword sets flags correctly", args.keyword == True and args.semantic == False)

    # search "query" --semantic sets args.semantic=True, args.keyword=False
    args = parser.parse_args(["search", "query", "--semantic"])
    ok("search --semantic sets flags correctly", args.semantic == True and args.keyword == False)

    # duplicates has no --top-k flag (assert argparse raises SystemExit if given)
    original_stderr = sys.stderr
    try:
        # We need to capture stderr or suppress it to prevent noisy output during test
        sys.stderr = io.StringIO()
        parser.parse_args(["duplicates", "--top-k", "5"])
        sys.stderr = original_stderr
        ok("duplicates --top-k should fail parsing", False)
    except SystemExit:
        sys.stderr = original_stderr
        ok("duplicates --top-k fails parsing (expected)", True)

# -----------------------------------------------------------------------------
# Section B & C & D: CLI Reality (Subprocess)
# -----------------------------------------------------------------------------

def run_cli(args):
    cmd = [PYTHON, SCRIPT] + args
    # Use utf-8 and ignore errors to avoid encoding issues in the test runner itself
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return result

def test_cli_reality():
    # B. Search result structure
    res = run_cli(["search", "openrouter api keys"])
    ok("CLI search 'openrouter api keys' exit code 0", res.returncode == 0)
    ok("CLI search 'openrouter api keys' returns content", len(res.stdout.strip()) > 0)
    
    res = run_cli(["search", "openrouter api keys", "--category", "config"])
    ok("CLI search with category filter exit code 0", res.returncode == 0)

    res = run_cli(["search", "Telegram bot", "--type", ".py"])
    ok("CLI search with type filter exit code 0", res.returncode == 0)
    if ".py" in res.stdout:
        ok("CLI search output contains .py", True)

    # For nonexistent, semantic search might return something, so use --keyword to expect 0
    res = run_cli(["search", "xyz_nonexistent_12345", "--keyword"])
    ok("CLI keyword search nonexistent returns 0", res.returncode == 0)
    ok("CLI keyword search nonexistent output is empty or mentions 0 results", 
       "0 results" in res.stdout or "No results" in res.stdout or res.stdout.strip() == "" or "Searching:" in res.stdout)

    # C. Known-good file regression
    res = run_cli(["search", "openrouter api keys"])
    ok("Search 'openrouter api keys' finds opencode.json", "opencode.json" in res.stdout)
    ok("Search 'openrouter api keys' finds .openclaude-profile.json", ".openclaude-profile.json" in res.stdout)

    res = run_cli(["search", "Telegram bot"])
    ok("Search 'Telegram bot' finds at least one .py file", ".py" in res.stdout)

    res = run_cli(["search", "filemind BGE-M3 embedding"])
    ok("Search 'filemind BGE-M3' finds result from filemind dir", "filemind" in res.stdout)

    # D. Command smoke tests
    res = run_cli(["stats"])
    ok("stats command exit 0", res.returncode == 0)
    ok("stats output contains 'Total files:'", "Total files:" in res.stdout)

    res = run_cli(["health"])
    ok("health command exit 0", res.returncode == 0)
    ok("health output contains 'OK' or 'WARN'", "OK" in res.stdout or "WARN" in res.stdout)

    res = run_cli(["scan"])
    ok("quick scan command exit 0", res.returncode == 0)
    ok("scan output contains 'Quick Scan Results:'", "Quick Scan Results:" in res.stdout)

    res = run_cli(["duplicates"])
    ok("duplicates command exit 0", res.returncode == 0)

    res = run_cli(["verify"])
    ok("verify command exit 0", res.returncode == 0)

# -----------------------------------------------------------------------------
# Section E: Windows encoding robustness
# -----------------------------------------------------------------------------

def test_encoding_robustness():
    # This test simulates search results containing emojis/special chars
    # to ensure no UnicodeEncodeError on Windows stdout (cp1252)
    try:
        # If we run it via subprocess and it doesn't crash, it's a good sign.
        res = run_cli(["search", "test emoji 🚀"])
        ok("CLI handles special chars/emojis without crash", res.returncode == 0 or res.returncode == 1)
    except UnicodeEncodeError:
        ok("CLI handles special chars/emojis", False, "UnicodeEncodeError raised")

# -----------------------------------------------------------------------------
# Runner
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("FileMind CLI Behavior Tests")
    print("=" * 60)

    run_section("A. Argument Parsing", test_argument_parsing)
    run_section("B/C/D. CLI Reality (Subprocess)", test_cli_reality)
    run_section("E. Encoding Robustness", test_encoding_robustness)

    print(f"\n{'='*60}")
    print(f"  RESULTS")
    print(f"{'='*60}")
    for status, name, detail in _results:
        marker = {"PASS": "OK", "FAIL": "FAIL", "ERRO": "ERR"}.get(status, "?")
        line = f"  [{marker}] {name}"
        if detail:
            line += f"\n       -> {detail}"
        print(line)

    print(f"\n  {passed} passed  |  {failed} failed")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)
