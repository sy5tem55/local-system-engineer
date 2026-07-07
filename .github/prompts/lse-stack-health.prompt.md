---
mode: 'agent'
description: 'Check LSE stack health — llama-server, Open WebUI, SearxNG, Elasticsearch, Prometheus, VRAM. Use when the stack seems slow, a service is unreachable, or at session start.'
tools: ['execute_command']
---

Run the LSE stack health check using the procedure in `.github/skills/lse-stack-health/SKILL.md`.

Check in one combined execute_command:
- llama-server health at localhost:8080
- Open WebUI at localhost:3000
- SearxNG at localhost:8088
- Elasticsearch at localhost:9200 (all 5 indices)
- Prometheus scrape targets
- Playwright at localhost:3001
- VRAM via nvidia-smi

Report the status table in the format specified in the SKILL.md.
If anything is down, provide the exact recovery command immediately.
