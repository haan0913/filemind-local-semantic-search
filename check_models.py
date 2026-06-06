import requests, json
r = requests.get('http://localhost:11434/api/tags')
models = r.json().get('models', [])
for m in models:
    name = m.get('name', 'unknown')
    size = m.get('size', 0) / 1e9
    print(f'{name} ({size:.1f}GB)')