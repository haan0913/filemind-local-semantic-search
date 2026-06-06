import sys, requests, json
sys.path.insert(0, 'C:/AI_STATION/filemind')

categories = ["code", "documentation", "research", "personal", "finance", "ai_project", "media", "config", "archive", "unknown"]

format_schema = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "category": {"type": "string", "enum": categories},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1}
        },
        "required": ["path", "category", "confidence"],
        "additionalProperties": False
    }
}

prompt = """Files to classify (use directory path context + content to determine category):
• File: "hub/docs/FILEMIND_MASTER_PLAN.md"
  Dir: hub/docs
  Ext: .md
  Content: Master plan for FileMind project

• File: "hub/bridge/cline_bridge/bot.py"
  Dir: hub/bridge/cline_bridge
  Ext: .py
  Content: Telegram bot implementation

Available categories: code, documentation, research, personal, finance, ai_project, media, config, archive, unknown
If you cannot determine the category, use "unknown"."""

system = """You are a file classification system. For each file, determine exactly ONE category.
Return ONLY a JSON array matching the schema. No explanation, no text, no markdown fences."""

payload = {
    "model": "gemma4-e4b-json",
    "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ],
    "stream": False,
    "format": format_schema,
    "options": {
        "temperature": 0.1,
        "num_predict": 4096
    }
}

print("Sending request to /api/chat with format schema...")
r = requests.post("http://localhost:11434/api/chat", json=payload, timeout=120)
r.raise_for_status()
resp = r.json()
content = resp.get("message", {}).get("content", "")
print(f"Raw response:\n{content}")
print(f"\nParsed:")
try:
    data = json.loads(content)
    for item in data:
        print(f"  {item['path']} -> {item['category']} ({item['confidence']})")
except Exception as e:
    print(f"Parse error: {e}")