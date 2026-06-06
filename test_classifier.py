import sys, time, logging
sys.path.insert(0, 'C:/AI_STATION/filemind')
from classifier import Classifier

logging.basicConfig(level=logging.INFO)

# Test with gemma4-e4b-json (current config)
print('=== Testing gemma4-e4b-json ===')
c = Classifier()
c.primary_model = 'gemma4-e4b-json'
start = time.time()
results = c.classify([
    {'path': 'test.py', 'ext': '.py', 'content_summary': 'def hello(): pass'},
    {'path': 'README.md', 'ext': '.md', 'content_summary': '# Project README'},
    {'path': 'config.json', 'ext': '.json', 'content_summary': '{"key": "value"}'},
    {'path': 'notes.txt', 'ext': '.txt', 'content_summary': 'Meeting notes from Tuesday'},
    {'path': 'data.csv', 'ext': '.csv', 'content_summary': 'id,name,value'},
])
elapsed = time.time() - start
for r in results:
    print(f'  {r["path"]:20} -> {r["category"]:20} ({r["confidence"]:.2f})')
classified = sum(1 for r in results if r["category"] != "unknown")
print(f'Time: {elapsed:.2f}s, Classified: {classified}/{len(results)}')

# Test with gemma3:4b
print('\n=== Testing gemma3:4b ===')
c2 = Classifier()
c2.primary_model = 'gemma3:4b'
start = time.time()
results2 = c2.classify([
    {'path': 'test.py', 'ext': '.py', 'content_summary': 'def hello(): pass'},
    {'path': 'README.md', 'ext': '.md', 'content_summary': '# Project README'},
    {'path': 'config.json', 'ext': '.json', 'content_summary': '{"key": "value"}'},
    {'path': 'notes.txt', 'ext': '.txt', 'content_summary': 'Meeting notes from Tuesday'},
    {'path': 'data.csv', 'ext': '.csv', 'content_summary': 'id,name,value'},
])
elapsed2 = time.time() - start
for r in results2:
    print(f'  {r["path"]:20} -> {r["category"]:20} ({r["confidence"]:.2f})')
classified2 = sum(1 for r in results2 if r["category"] != "unknown")
print(f'Time: {elapsed2:.2f}s, Classified: {classified2}/{len(results2)}')

print(f'\nKPI: gemma4={elapsed:.2f}s, gemma3={elapsed2:.2f}s')
if elapsed2 > 0:
    print(f'gemma3 speedup vs gemma4: {elapsed/elapsed2:.2f}x')
print(f'gemma4 accuracy: {classified}/{len(results)} = {classified/len(results)*100:.0f}%')
print(f'gemma3 accuracy: {classified2}/{len(results2)} = {classified2/len(results2)*100:.0f}%')
