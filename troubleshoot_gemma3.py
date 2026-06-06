"""
Troubleshoot gemma3:4b JSON classification.
Test multiple prompt formats, system prompts, and parameters.
"""
import time
import requests

OLLAMA = "http://localhost:11434/api/chat"

test_files = ["test.py", "README.md", "config.json", "notes.txt", "data.csv"]
categories = ["code", "documentation", "config", "personal", "finance", "ai_project", "research", "archive", "unknown"]

expected = {"test.py": "code", "README.md": "documentation", "config.json": "config", "notes.txt": "personal", "data.csv": "unknown"}

def run_test(test_name, model, messages, stream=False, format_opt=None, options=None):
    """Run a single classification test."""
    payload = {"model": model, "messages": messages, "stream": stream}
    if format_opt:
        payload["format"] = format_opt
    if options:
        payload["options"] = options
    
    print(f"\n{'='*60}")
    print(f"TEST: {test_name}")
    print(f"  Model: {model}")
    print(f"  System prompt: {'YES' if any(m.get('role')=='system' for m in messages) else 'NO'}")
    print(f"  Format: {format_opt}")
    print(f"  Options: {options}")
    
    start = time.time()
    try:
        r = requests.post(OLLAMA, json=payload, timeout=120)
        elapsed = time.time() - start
        
        print(f"  Time: {elapsed:.2f}s, Status: {r.status_code}")
        
        if r.status_code == 200:
            resp = r.json()
            content = resp.get("message", {}).get("content", "")
            print(f"  Response length: {len(content)} chars")
            print(f"  Response preview: {content[:300]}")
            
            # Check if valid JSON
            import json
            try:
                data = json.loads(content.strip().strip("```json").strip("```").strip())
                print(f"  Valid JSON: YES")
                # Compare with expected
                matches = sum(1 for k, v in expected.items() if data.get(k) == v)
                print(f"  Accuracy: {matches}/{len(expected)} = {matches/len(expected)*100:.0f}%")
                return elapsed, matches/len(expected)
            except json.JSONDecodeError:
                print(f"  Valid JSON: NO (raw text)")
                return elapsed, 0.0
        else:
            print(f"  Error: {r.text[:200]}")
            return time.time() - start, 0.0
    except Exception as e:
        elapsed = time.time() - start
        print(f"  Exception: {e}")
        return elapsed, 0.0


# ── Test Suite ──
print("Gemma3:4b JSON Classification Troubleshooting")
print("="*60)

# Baseline: gemma4-e4b-json (should work)
run_test(
    "BASELINE: gemma4-e4b-json (control)",
    "gemma4-e4b-json:latest",
    [{"role": "user", "content": f"Classify these files into categories: {', '.join(test_files)}. Categories: {', '.join(categories)}. Return ONLY a JSON object mapping filename to category."}],
    format_opt="json"
)

# Test 1: gemma3:4b with same prompt (replicate failure)
run_test(
    "gemm3:4b same prompt as gemma4 (expect failure)",
    "gemma3:4b",
    [{"role": "user", "content": f"Classify these files into categories: {', '.join(test_files)}. Categories: {', '.join(categories)}. Return ONLY a JSON object mapping filename to category."}],
    format_opt="json"
)

# Test 2: gemma3:4b with explicit system prompt
run_test(
    "gemm3:4b with system prompt enforcing JSON",
    "gemma3:4b",
    [
        {"role": "system", "content": "You are a file classification assistant. You MUST respond with ONLY a valid JSON object mapping each filename to its category. No explanations, no markdown, just pure JSON."},
        {"role": "user", "content": f"Classify these files: {test_files}\nCategories: {categories}\nReturn a JSON object like: {{\"filename.ext\": \"category\", ...}}"}
    ],
    format_opt="json"
)

# Test 3: gemma3:4b with example in prompt
run_test(
    "gemm3:4b with one-shot example",
    "gemma3:4b",
    [
        {"role": "user", "content": f"""Classify files into categories.

Categories: {', '.join(categories)}

Example:
Files: ["hello.py", "notes.txt"]
Response: {{"hello.py": "code", "notes.txt": "personal"}}

Now classify:
Files: {test_files}
Response:"""}
    ],
    format_opt="json"
)

# Test 4: gemma3:4b with temperature=0
run_test(
    "gemm3:4b with temperature=0, deterministic",
    "gemma3:4b",
    [
        {"role": "system", "content": "Return ONLY valid JSON. No other text."},
        {"role": "user", "content": f"Classify: {test_files} → Categories: {categories}. JSON only."}
    ],
    format_opt="json",
    options={"temperature": 0.0, "top_p": 1.0}
)

# Test 5: gemma3:4b with JSON schema format
run_test(
    "gemm3:4b with JSON schema",
    "gemma3:4b",
    [
        {"role": "system", "content": "You must respond with a JSON object mapping filenames to categories."},
        {"role": "user", "content": f"Classify these files: {test_files}\nCategories: {categories}"}
    ],
    format_opt={"type": "object", "properties": {f: {"type": "string", "enum": categories} for f in test_files}, "required": test_files}
)

# Test 6: gemma3:4b with repeat_penalty (prevent empty response)
run_test(
    "gemm3:4b with repeat_penalty=1.2",
    "gemma3:4b",
    [
        {"role": "system", "content": "Return a JSON object. Each key is a filename, each value is a category."},
        {"role": "user", "content": f"Classify: {test_files} into {categories}. Return JSON."}
    ],
    format_opt="json",
    options={"temperature": 0.1, "repeat_penalty": 1.2}
)

# Test 7: gemma3:4b with num_ctx increased
run_test(
    "gemm3:4b with num_ctx=8192",
    "gemma3:4b",
    [
        {"role": "system", "content": "You are a JSON-only classifier. Return a JSON object with no other text."},
        {"role": "user", "content": f"""Task: Classify each file into exactly one category.

Files to classify:
{chr(10).join(f"- {f}" for f in test_files)}

Available categories:
{', '.join(categories)}

Example output format:
{{"file1.py": "code", "file2.md": "documentation"}}

Your response (JSON only):"""}
    ],
    format_opt="json",
    options={"temperature": 0.0, "num_ctx": 8192}
)

# Test 8: gemma3:4b without format=json (let it respond freely, then parse)
run_test(
    "gemm3:4b WITHOUT format=json (natural response)",
    "gemma3:4b",
    [
        {"role": "system", "content": "Classify files into categories. Return your answer as a JSON object."},
        {"role": "user", "content": f"Files: {test_files}\nCategories: {categories}\n\nReturn as JSON:"}
    ],
    # NO format_opt
)

print(f"\n{'='*60}")
print(f"ALL TESTS COMPLETE")
print(f"{'='*60}")
