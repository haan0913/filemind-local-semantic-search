import sys, time
sys.path.insert(0, 'C:/AI_STATION/filemind')
from classifier import Classifier

# Test files that BYPASS rule-based classifier (unknown extensions)
test_files = [
    {'path': 'src/main.rkt', 'ext': '.rkt', 'content_summary': '(define (factorial n) (if (= n 0) 1 (* n (factorial (- n 1)))))'},
    {'path': 'docs/tutorial.asciidoc', 'ext': '.asciidoc', 'content_summary': '= Tutorial\n\nThis is a step-by-step guide to using the framework.'},
    {'path': 'settings.prf', 'ext': '.prf', 'content_summary': 'database.host=localhost\ndatabase.port=5432'},
    {'path': 'diary_2026', 'ext': '', 'content_summary': 'Today I reflected on the progress of the AI Station project.'},
    {'path': 'trades_q1', 'ext': '', 'content_summary': 'AAPL,BUY,100,150.00\nMSFT,SELL,50,300.00'},
]

print('=== Testing gemma4-e4b-json (unknown extensions) ===')
c = Classifier()
c.primary_model = 'gemma4-e4b-json'
start = time.time()
results = c.classify(test_files)
elapsed = time.time() - start
for r in results:
    print(f'  {r["path"]:30} -> {r["category"]:20} ({r["confidence"]:.2f})')
classified = sum(1 for r in results if r["category"] != "unknown")
print(f'Time: {elapsed:.2f}s, LLM Classified: {classified}/{len(results)}')

print('\n=== Testing gemma3:4b (unknown extensions) ===')
c2 = Classifier()
c2.primary_model = 'gemma3:4b'
start = time.time()
results2 = c2.classify(test_files)
elapsed2 = time.time() - start
for r in results2:
    print(f'  {r["path"]:30} -> {r["category"]:20} ({r["confidence"]:.2f})')
classified2 = sum(1 for r in results2 if r["category"] != "unknown")
print(f'Time: {elapsed2:.2f}s, LLM Classified: {classified2}/{len(results2)}')

print(f'\n{"="*60}')
print(f'KPI: gemma4-e4b-json vs gemma3:4b (LLM classification)')
print(f'{"="*60}')
print(f'  gemma4-e4b-json: {elapsed:.2f}s, {classified}/{len(results)} classified')
print(f'  gemma3:4b:       {elapsed2:.2f}s, {classified2}/{len(results2)} classified')
if elapsed > 0 and elapsed2 > 0:
    print(f'  Speedup factor:    {elapsed/elapsed2:.2f}x')
    print(f'  Time difference:   {elapsed - elapsed2:+.2f}s')
print(f'  gemma4 accuracy: {classified/len(results)*100:.0f}%')
print(f'  gemma3 accuracy: {classified2/len(results2)*100:.0f}%')

# Note: The rule-based classifier handles known extensions instantly (0.00s)
# These times reflect actual LLM calls for unknown extensions
print(f'\nNote: Known extensions (.py, .md, .json) are handled by rule-based')
print(f'classifier at 0.00s. Times above are for LLM calls on unknown extensions.')
