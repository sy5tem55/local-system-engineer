# Local System Engineer — AI Agent Design Kit

A structured engineering reference for building a reliable, safe, and context-aware AI system administrator running on a local inference stack.

## Stack

| Layer | Component |
|---|---|
| Host | Windows 11 → WSL2 → Ubuntu 24.04 |
| Inference engine | llama.cpp server (`llama-server`) |
| Frontend | OpenWebUI |
| Models under eval | `gemma-4-26B-A4B-it-GGUF` (MoE) · `gemma-4-31B-it-GGUF` (dense) |
| Web search | SearxNG (self-hosted, called only on demand) |

---

## Agent Purpose

The Local System Engineer is an AI admin that operates as a careful, step-by-step shell operator inside a defined permission boundary on a WSL/Ubuntu 24.04 machine. It can:

- Read and write files within allowed directories
- Inspect and manage systemd services and running processes
- Install, update, and audit packages via `apt`
- Edit config files and dotfiles
- Delegate any operation requiring `sudo` back to the human user with exact commands
- Search the web via SearxNG only when local knowledge is insufficient
- Monitor and manage its own context budget to stay below hallucination thresholds

---

## Repository Layout

```
local-system-engineer/
├── README.md                          ← this file
│
├── docs/
│   ├── 01-model-evaluation.md         ← Gemma 4 MoE vs dense, eval methodology, recommendation
│   ├── 02-terminal-interaction.md     ← OpenWebUI tool design, safety layer, sudo delegation
│   ├── 03-context-management.md       ← Context bloat observability and remediation
│   └── 04-knowledge-base.md           ← KB design: content, structure, injection strategy
│
├── prompts/
│   ├── CHANGELOG.md                   ← Version history and rationale
│   ├── v0.1-baseline.md               ← Minimal viable system prompt
│   ├── v0.2-structured.md             ← + tool protocol, sudo delegation, step-by-step
│   └── v0.3-context-aware.md          ← + context budget awareness, search policy
│
└── tools/
    └── context_monitor.py             ← Live llama.cpp token usage monitor
```

---

## Key Design Decisions

**Why not sudo?** The agent must never silently escalate privileges. Any command requiring `sudo` produces a `SUDO_REQUIRED` block that the user runs manually. This keeps the trust boundary explicit and auditable.

**Why conditional web search?** Every SearxNG call injects a variable-length payload into context. The agent only calls search when it explicitly cannot answer from its system prompt knowledge or knowledge base — and it announces this decision before doing so.

**Why context limits matter here?** Both Gemma 4 models running under llama.cpp show measurable quality degradation beyond ~30 000 tokens. System engineering tasks generate verbose tool output (file contents, service logs, package lists) that bloats context fast. Context management is therefore a first-class concern, not an afterthought.

---

## Quick Start

1. Start `llama-server` with your chosen model and a 32 768 token context window.
2. Import the latest prompt from `prompts/v0.3-context-aware.md` as the OpenWebUI system prompt for the model.
3. Add the tool functions from `docs/02-terminal-interaction.md` as OpenWebUI Tools.
4. Run `tools/context_monitor.py` in a separate terminal to watch token usage in real time.
5. Load the knowledge base snippet from `docs/04-knowledge-base.md` into the OpenWebUI Knowledge section (or prepend inline to the system prompt for small KBs).

---

## Versioning Convention

Prompt versions follow `vMAJOR.MINOR`:
- **MAJOR** bump: structural change (new tool protocol, new safety model, architectural shift)
- **MINOR** bump: wording tuning, added examples, tightened constraints

Every version lives as its own file. Never overwrite a previous version — the full history is the audit trail.
