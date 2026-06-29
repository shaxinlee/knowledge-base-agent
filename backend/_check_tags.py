import httpx, json, re

client = httpx.Client(timeout=60)
resp = client.post(
    'http://host.docker.internal:7010/v1/chat/completions',
    json={
        'model': 'Qwen3.6-35B-A3B-AWQ-4bit',
        'messages': [{'role': 'user', 'content': '你好'}],
        'stream': False,
        'enable_thinking': True,
    }
)
content = resp.json()['choices'][0]['message']['content']

# Find all think-related tags
for m in re.finditer(r'<[^>]*think[^>]*>', content):
    print(f"Position {m.start()}: {m.group()!r}")

# Print first 50 chars as repr
print(f"\nFirst 80 chars: {content[:80]!r}")
print(f"\nLast 80 chars: {content[-80:]!r}")
