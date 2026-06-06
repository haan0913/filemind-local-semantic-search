"""Quick classify test - 5 files only."""
import sys
sys.path.insert(0, "C:/AI_STATION")

from filemind.catalog import Catalog
from filemind.classifier import Classifier

catalog = Catalog()
catalog.init_db()

# Get 5 unknown files
files = catalog.get_files_by_category("unknown")
files = files[:5]
print(f"Got {len(files)} files to classify")
for f in files:
    print(f"  {f['path']} | summary={bool(f.get('content_summary'))}")

file_data = [
    {"path": f["path"], "ext": f.get("ext", ""), "content_summary": f.get("content_summary", "")}
    for f in files
]

classifier = Classifier()
print(f"Using model: {classifier.primary_model}")
results = classifier.classify(file_data)

classified = 0
for r in results:
    if r["category"] != "unknown":
        catalog.update_category(r["path"], r["category"], r["confidence"])
        print(f"  OK: {r['path']} -> {r['category']} ({r['confidence']})")
        classified += 1
    else:
        print(f"  UNKNOWN: {r['path']}")

catalog.conn.commit()
print(f"\nClassified: {classified}/{len(results)}")
catalog.close()