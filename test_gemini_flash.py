#!/usr/bin/env python3
"""Test Gemini 2.0 Flash via OpenRouter."""
import json
import os
import requests

url = 'https://openrouter.ai/api/v1/chat/completions'
api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
if not api_key:
    raise SystemExit("Set OPENROUTER_API_KEY before running this smoke test.")

headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json',
    'HTTP-Referer': 'https://filemind.local',
    'X-Title': 'FileMind',
}

system_msg = 'You are a file classification system. Return ONLY a JSON array of objects with keys: path, category, confidence.'
user_msg = 'Classify: 1) hub/docs/README.md (project readme), 2) bot.py (telegram bot), 3) config.toml (app config). Categories: code, documentation, config.'

payload = {
    'model': 'google/gemma-3-27b-it',
    'messages': [
        {'role': 'system', 'content': system_msg},
        {'role': 'user', 'content': user_msg}
    ],
    'temperature': 0.1,
    'max_tokens': 500
}

print('Testing google/gemini-2.0-flash-exp:free via OpenRouter...')
r = requests.post(url, json=payload, headers=headers, timeout=60)
print(f'Status: {r.status_code}')

try:
    data = r.json()
    content = data['choices'][0]['message']['content']
    print(f'Raw response:\n{content}')
    parsed = json.loads(content)
    print(f'\nParsed {len(parsed)} items successfully!')
    for item in parsed:
        print(f'  {item.get("path","?")} -> {item.get("category","?")} ({item.get("confidence",0)})')
except Exception as e:
    print(f'Error: {e}')
    print(r.text[:500])
