"""
Clean sequential benchmark: gemma3:4b vs gemma4-e4b-json for JSON classification.
Best prompt format for each model.
"""
import time
import json
import requests
from typing import Any

OLLAMA = "http://localhost:11434/api/chat"

test_files = ["test.py", "README.md", "config.json", "notes.txt", "data.csv"]
categories = ["code", "documentation", "config", "personal", "finance", "ai_project", "research", "archive", "unknown"]
expected = {"test.py": "code", "README.md": "documentation", "config.json": "config", "notes.txt": "personal", "data.csv": "unknown"}

def classify(
    model: str,
    messages: list[dict[str, str]],
    format_opt: str | dict[str, Any] | None = "json",
    options: dict[str, Any] | None = None,
):
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": format_opt,
    }
    if options:
        payload["options"] = options
    start = time.time()
    r = requests.post(OLLAMA, json=payload, timeout=120)
    elapsed = time.time() - start
    content = r.json().get("message", {}).get("content", "")
    try:
        # Strip markdown code blocks if present
        clean = content.strip().strip("```json").strip("```").strip()
        data = json.loads(clean)
        accuracy = sum(1 for k, v in expected.items() if data.get(k) == v) / len(expected)
    except:
        data = None
        accuracy = 0.0
    return elapsed, accuracy, content[:150]

print("Clean Benchmark: gemma3:4b vs gemma4-e4b-json")
print("="*60)

# gemma4-e4b-json baseline
print("\n--- gemma4-e4b-json ---")
for i in range(3):
    elapsed, acc, preview = classify(
        "gemma4-e4b-json:latest",
        [{"role": "user", "content": f"Classify: {test_files} into {categories}. Return JSON."}],
        format_opt="json"
    )
    print(f"  Run {i+1}: {elapsed:.2f}s, accuracy={acc:.0%}")

# gemma3:4b - best prompt format from troubleshooting
print("\n--- gemma3:4b (with system prompt + format=json) ---")
for i in range(3):
    elapsed, acc, preview = classify(
        "gemma3:4b",
        [
            {"role": "system", "content": "You are a JSON-only file classifier. Return ONLY a JSON object."},
            {"role": "user", "content": f"Classify: {test_files} into {categories}. Return JSON."}
        ],
        format_opt="json",
        options={"temperature": 0.0, "num_ctx": 8192}
    )
    print(f"  Run {i+1}: {elapsed:.2f}s, accuracy={acc:.0%}")
    if acc > 0:
        print(f"  Output: {preview}")

# gemma3:4b - with JSON schema
print("\n--- gemma3:4b (with JSON schema) ---")
schema = {
    "type": "object",
    "properties": {f: {"type": "string", "enum": categories} for f in test_files},
    "required": test_files
}
for i in range(3):
    elapsed, acc, preview = classify(
        "gemma3:4b",
        [
            {"role": "system", "content": "Classify each file into one category."},
            {"role": "user", "content": f"Files: {test_files}, Categories: {categories}"}
        ],
        format_opt=schema
    )
    print(f"  Run {i+1}: {elapsed:.2f}s, accuracy={acc:.0%}")
    if acc > 0:
        print(f"  Output: {preview}")

# gemma3:4b - NO format constraint (natural response)
print("\n--- gemma3:4b (natural response, no format=json) ---")
for i in range(3):
    elapsed, acc, preview = classify(
        "gemma3:4b",
        [
            {"role": "system", "content": "Classify files into categories. Return as JSON."},
            {"role": "user", "content": f"Files: {test_files}\nCategories: {categories}\nJSON:"}
        ],
        format_opt=None
    )
    print(f"  Run {i+1}: {elapsed:.2f}s, accuracy={acc:.0%}")
    if acc > 0:
        print(f"  Output: {preview}")

print("\n" + "="*60)
print("DONE")
