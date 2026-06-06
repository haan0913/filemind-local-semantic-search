import sys, requests, json
sys.path.insert(0, 'C:/AI_STATION/filemind')

# Test gemma4-e4b-json model
test_files = [
    {"path": "hub/docs/FILEMIND_MASTER_PLAN.md", "ext": ".md", "content_summary": "Master plan for FileMind project"},
    {"path": "hub/bridge/cline_bridge/bot.py", "ext": ".py", "content_summary": "Telegram bot implementation"},
    {"path": "config.toml", "ext": ".toml", "content_summary": "Configuration file"},
    {"path": "scripts/index_ai_station.py", "ext": ".py", "content_summary": "Indexing script"},
    {"path": "README.md", "ext": ".md", "content_summary": "Project readme"},
]

from classifier import Classifier
c = Classifier()
c.batch_size = 5
setattr(c, "classification_model", "gemma4-e4b-json")

print("Testing gemma4-e4b-json with 5 files...")
results = c.classify(test_files)
print(f"\nClassified {len(results)} files:")
for r in results:
    print(f"  {r['path'][:60]} -> {r['category']} ({r['confidence']:.2f})")
