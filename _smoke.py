from filemind.classifier import Classifier
c = Classifier()
print(f"Primary model: {c.primary_model}")
print(f"Categories: {c.categories}")
files = [
    {"path": "test.py", "ext": ".py", "content_summary": "import json"},
    {"path": "docs.md", "ext": ".md", "content_summary": "# Title"},
    {"path": ".env", "ext": ".env", "content_summary": "KEY=value"},
]
results = c.classify(files)
for r in results:
    print(r)
any_unknown = any(r["category"] == "unknown" for r in results)
print(f"{'FAIL' if any_unknown else 'PASS'}: {'some' if any_unknown else 'all'} files classified")
