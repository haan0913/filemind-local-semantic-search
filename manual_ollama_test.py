#!/usr/bin/env python3
"""Manual Ollama-only classification test with DB write.
This completely bypasses OpenRouter and writes results directly."""
import sys
sys.path.insert(0, 'C:/AI_STATION/filemind')

from config import config
from catalog import Catalog
from extractor import extract_content
from classifier import Classifier
from scanner import FileScanner

print("=== Manual Ollama-Only Pipeline Test ===")

# Clear OpenRouter key to force Ollama-only
config.openrouter_api_key = ""
config.classification_batch_size = 3

print(f"\nModel: {config.classification_model} (local Ollama)")
print(f"Batch size: {config.classification_batch_size}")
print(f"Categories: {config.categories}")

# Phase 1: Scan
print("\n1. Scanning filemind directory only (small set)...")
config.scan_roots = ["C:/AI_STATION/filemind"]
scanner = FileScanner(config)
changes, deleted = scanner.scan()
changes = changes[:10]  # Limit to 10 files for test
print(f"   Found {len(changes)} files")

# Phase 2: Extract
print("\n2. Extracting content...")
catalog = Catalog()
catalog.init_db()
file_data = []
for change in changes[:5]:  # Test with 3 files first
    try:
        content = extract_content(change.full_path, max_size=config.max_file_size)
        summary = content[:config.max_content_length]
        file_data.append({
            "path": change.path,
            "full_path": str(change.full_path),
            "size": change.size,
            "mtime": change.mtime,
            "content_hash": change.content_hash,
            "ext": change.ext,
            "content_summary": summary,
            "change_type": change.change_type,
        })
        print(f"   Extracted: {change.path}")
    except Exception as e:
        print(f"   Skip: {change.path} ({e})")

print(f"   Ready for classification: {len(file_data)} files")

# Phase 3: Classify (Ollama only)
print("\n3. Classifying via Ollama ONLY...")
classifier = Classifier()

# Force Ollama-only by clearing API key
classifier_class = classifier.__class__
class OllamaOnlyClassifier(Classifier):
    def _classify_batch(self, files):
        """Only use Ollama, skip OpenRouter entirely."""
        expected_paths = [f["path"] for f in files]
        file_lines = []
        for f in files:
            path = f.get("path", "unknown")
            parent = "/".join(path.rsplit("/", 1)[:-1]) if "/" in path else ""
            snippet = (f.get("content_summary", "") or "").strip()[:150]
            file_lines.append(
                f'File: "{path}"\n'
                f'Dir: {parent if parent else "(root)"}\n'
                f'Ext: {f.get("ext", "")}\n'
                f'Content: {snippet if snippet else "(empty or binary)"}'
            )
        files_text = "\n\n".join(file_lines)
        cats = ", ".join(self.categories)
        prompt = (
            f'You are a file classification system. Return ONLY a JSON array.\n\n'
            f'Files to classify:\n{files_text}\n\n'
            f'Available categories: {cats}\n'
            f'Format: [{{"path":"exact path","category":"category","confidence":0.9}}]'
        )

        import requests
        format_schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "category": {"type": "string", "enum": self.categories},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                },
                "required": ["path", "category", "confidence"],
                "additionalProperties": False
            }
        }
        payload = {
            "model": "gemma4-e4b-json",
            "messages": [
                {"role": "system", "content": "Return ONLY a JSON array. No explanation."},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "format": format_schema,
            "options": {"temperature": 0.1, "num_predict": 4096}
        }
        r = requests.post("http://localhost:11434/api/chat", json=payload, timeout=120)
        r.raise_for_status()
        text = r.json().get("message", {}).get("content", "")
        
        import json, re
        # Strip markdown fences
        text = re.sub(r'```(?:json)?\s*\n(.*?)\n?\s*```', r'\1', text, flags=re.DOTALL).strip()
        data = json.loads(text)
        results = []
        for item in data:
            results.append({
                "path": item["path"],
                "category": item["category"],
                "confidence": item.get("confidence", 0.85)
            })
        return results

ollama = OllamaOnlyClassifier()
classifications = ollama.classify(file_data)

print("\n4. Classification results:")
for c in classifications:
    print(f"   {c['path'][:55]} -> {c['category']} ({c['confidence']:.2f})")

# Phase 4: Write to DB
print("\n5. Writing to database...")
for fd in file_data:
    cls = next((c for c in classifications if c["path"] == fd["path"]), None)
    cat = cls["category"] if cls else "unknown"
    conf = cls["confidence"] if cls else 0.0
    catalog.upsert_file(
        path=fd["path"], full_path=fd["full_path"],
        size=fd["size"], mtime=fd["mtime"],
        content_hash=fd["content_hash"], ext=fd["ext"],
        content_summary=fd["content_summary"],
        category=cat, confidence=conf
    )
    print(f"   Wrote: {fd['path'][:55]} -> {cat} ({conf:.2f})")

# Verify
total = catalog.count()
categorized = catalog.conn.execute('SELECT COUNT(*) FROM file_index WHERE category != "unknown"').fetchone()[0]
print(f"\n6. Database verification:")
print(f"   Total records: {total}")
print(f"   With non-unknown category: {categorized}")

rows = catalog.conn.execute('SELECT path, category, confidence FROM file_index ORDER BY path').fetchall()
for r in rows:
    print(f"   {r['path'][:55]} -> {r['category']} ({r['confidence']:.2f})")

catalog.close()
print("\nTest complete!")