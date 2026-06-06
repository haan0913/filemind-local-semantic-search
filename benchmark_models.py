import time
import requests

messages = [{
    'role': 'user',
    'content': 'Classify these files: [test.py, README.md, config.json, notes.txt, data.csv] into categories: code, documentation, config, personal, finance, ai_project, research, archive, unknown. Return JSON.'
}]

# Test gemma3:4b
model = 'gemma3:4b'
print(f"Testing {model}...")
start = time.time()
r = requests.post(
    'http://localhost:11434/api/chat',
    json={'model': model, 'messages': messages, 'stream': False, 'format': 'json'},
    timeout=120
)
elapsed_gemma3 = time.time() - start
print(f"  {model}: {elapsed_gemma3:.2f}s, status={r.status_code}")
if r.status_code == 200:
    resp = r.json()
    content = resp.get("message", {}).get("content", "")
    print(f"  Response: {len(content)} chars")
    print(f"  Content: {content[:200]}")

# Test gemma4-e4b-json
model = 'gemma4-e4b-json:latest'
print(f"\nTesting {model}...")
start = time.time()
r = requests.post(
    'http://localhost:11434/api/chat',
    json={'model': model, 'messages': messages, 'stream': False, 'format': 'json'},
    timeout=180
)
elapsed_gemma4 = time.time() - start
print(f"  {model}: {elapsed_gemma4:.2f}s, status={r.status_code}")
if r.status_code == 200:
    resp = r.json()
    content = resp.get("message", {}).get("content", "")
    print(f"  Response: {len(content)} chars")
    print(f"  Content: {content[:200]}")

print(f"\n{'='*50}")
print(f"KPI: gemma3:4b vs gemma4-e4b-json Classification Speed")
print(f"{'='*50}")
print(f"  gemma3:4b:       {elapsed_gemma3:>8.2f}s")
print(f"  gemma4-e4b-json: {elapsed_gemma4:>8.2f}s")
print(f"  Speedup factor:  {elapsed_gemma4/elapsed_gemma3:>8.1f}x")
print(f"  Time saved/call: {elapsed_gemma4 - elapsed_gemma3:>8.2f}s")
if elapsed_gemma4 > elapsed_gemma3:
    pct = (elapsed_gemma4 - elapsed_gemma3) / elapsed_gemma4 * 100
    print(f"  Time reduction:    {pct:>7.1f}%")
