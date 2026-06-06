#!/usr/bin/env python3
"""Test classifier with improved JSON parsing."""
import sys
sys.path.insert(0, 'C:/AI_STATION/filemind')
from classifier import Classifier

# Test with a few sample files
test_files = [
    {"path": "hub/docs/FILEMIND_MASTER_PLAN.md", "ext": ".md", "content_summary": "Master plan for FileMind project with architecture design"},
    {"path": "hub/bridge/cline_bridge/bot.py", "ext": ".py", "content_summary": "Telegram bot implementation for Cline bridge"},
    {"path": "config.toml", "ext": ".toml", "content_summary": "Configuration file for kimi"},
]

c = Classifier()
c.batch_size = 3  # Small batch for testing
results = c.classify(test_files)

print(f"Classified {len(results)} files:")
for r in results:
    print(f"  {r['path'][:60]} -> {r['category']} ({r['confidence']:.2f})")