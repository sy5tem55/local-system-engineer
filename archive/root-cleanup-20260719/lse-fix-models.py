"""
Writes chatLanguageModels.json for VS Code Insiders with:
  - LUCIFER  : Qwen3.6-27B  @ localhost:8080
  - node3090 : Gemma-4-31B  @ node3090.home.arpa:8080

Canonical launch parameters (LUCIFER):
  -m /home/sy5/models/unsloth/Qwen3.6-27B-UD-Q4_K_XL.gguf
  --alias Qwen3.6-27B
  --ctx-size 165000
  --reasoning-format none --reasoning-budget 16000
  --cache-type-k q4_0 --cache-type-v q4_0
  maxInputTokens = 165000 - 16000 (reasoning) - 15000 (output) = 134000

Canonical launch parameters (node3090):
  -m /opt/models/unsloth/Gemma-4-31B-it-UD-Q4_K_XL.gguf
  --alias "Gemma-4-31B"
  --ctx-size 160000  --flash-attn on
  --cache-type-k q4_0 --cache-type-v q4_0
  --temp 1.0  --top-p 0.95  --top-k 64   (Google model card recommended)
  --reasoning-format none  --reasoning-budget 8192
  sha256: 5b681a50544e5e58c0d383d09bb7fddc1723f75b747b3cd1b390874aa286b46a
  file: 18 GB
  maxInputTokens = 160000 - 8192 (reasoning) - 8192 (output) = 143616

Run: python lse-fix-models.py
"""

import json, pathlib

TARGET = pathlib.Path.home() / "AppData" / "Roaming" / "Code - Insiders" / "User" / "chatLanguageModels.json"

data = [
    {
        "name": "LUCIFER",
        "vendor": "customendpoint",
        "apiKey": "none",
        "apiType": "chat-completions",
        "models": [
            {
                "id": "Qwen3.6-27B",
                "name": "Qwen3.6-27B (LUCIFER)",
                "url": "http://localhost:8080/v1/chat/completions",
                "toolCalling": True,
                "vision": False,
                "thinking": True,
                "maxInputTokens": 134000,   # 165K ctx - 16K reasoning budget - 15K output
                "maxOutputTokens": 15000,
            }
        ],
    },
    {
        "name": "node3090",
        "vendor": "customendpoint",
        "apiKey": "none",
        "apiType": "chat-completions",
        "models": [
            {
                "id": "Gemma-4-31B",              # matches --alias exactly
                "name": "Gemma-4-31B-IT (node3090)",
                "url": "http://node3090.home.arpa:8080/v1/chat/completions",
                "toolCalling": True,
                "vision": True,                    # Gemma 4 is multimodal
                "thinking": True,
                "maxInputTokens": 143000,   # 160K ctx - 8192 reasoning budget - 8192 output
                "maxOutputTokens": 8192,
            },
            {
                "id": "Qwen3.6-35B-A3B",          # matches --alias exactly
                "name": "Qwen3.6-35B-A3B (node3090)",
                "url": "http://node3090.home.arpa:8080/v1/chat/completions",
                "toolCalling": True,
                "vision": False,
                "thinking": True,
                "maxInputTokens": 94000,    # 110K ctx - 16K output headroom
                "maxOutputTokens": 16000,
            },
        ],
    },
]

TARGET.parent.mkdir(parents=True, exist_ok=True)
TARGET.write_text(json.dumps(data, indent=2), encoding="utf-8")

print(f"Written: {TARGET}")
print()
for provider in data:
    m = provider["models"][0]
    print(f"  {provider['name']:10}  {m['id']:20}  ctx={m['maxInputTokens']}  {m['url']}")
