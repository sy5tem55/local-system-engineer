---
description: "Apply when writing, editing, or reviewing LSE tool functions in Cogitator (cogitator-*.py), goethe.py, or vaultwarden_tools*.py. Enforces docstring compliance, protocol discipline, and staging workflow."
applyTo: "tools/cogitator-*.py,tools/goethe*.py,tools/vaultwarden*.py"
---
# LSE Tool Function Standards

## Docstring Compliance (8-Dimension Audit)

Every tool function must pass the 8-dimension audit before staging. Run the `lse-docstring-audit` skill on any new or modified function. The 8 dimensions:

1. **Section headers** — CAPITALISED headers for multi-rule docstrings (STOP PROTOCOL, COMBINE RULE, etc.)
2. **Compliance language** — must/never/always, not should/consider/try
3. **GOOD/BAD examples** — for any rule the model might misapply
4. **Stop protocol** — required on all user-facing output functions; N/A for internal-data functions
5. **Failure prohibitions** — explicitly name and forbid the top failure mode ("Skipping X is a protocol violation")
6. **Output format** — exact format quoted inline for any expected string
7. **Trigger gate** — explicit condition for when to call the function
8. **Verification requirement** — `tail -5` or `read_file` after any write; stated as mandatory

## Staging Workflow

Before committing a new Cogitator version:
1. AST check: `python3 -c "import ast; ast.parse(open('cogitator-vX.Y.Z.py').read()); print('AST OK')"`
2. Black check: `black --check cogitator-vX.Y.Z.py`
3. Line count delta vs previous version: `wc -l cogitator-vX.Y.Z.py`
4. Update CURRENT-STATE.md with version, line count, black-norm hash, and staged status

## Protocol Rules (must appear in relevant docstrings)

**STOP PROTOCOL** (user-facing output functions only):
```
After calling this function, write exactly ONE closing line echoing the command.
Format: "Please run `<command>` in your terminal and paste the output here."
After that single line, output nothing further.
Skipping this is a protocol violation.
```

**COMBINE RULE** (execute_command):
```
Always chain commands with `&&` in a single call.
GOOD: execute_command("cmd1 && cmd2 && cmd3")
BAD:  Three separate execute_command calls
```

**READ-FIRST** (write_file):
```
Always call read_file() on the target path before writing.
Skipping the read when the file is readable is a protocol violation.
```

**VERIFY** (write_file, any state-modifying function):
```
After writing, verify with: execute_command("tail -5 <path>") or read_file.
Skipping verification is a protocol violation.
```

## OWUI-Injected Parameters

These are injected by OpenWebUI and must NEVER be exposed as tool arguments:
`__event_emitter__`, `__event_call__`, `__chat_id__`, `__user__`

Strip them from any MCP-facing method signature.

## Version Numbering

Cogitator: `vMAJOR.MINOR.PATCH` — patch for single-function changes, minor for new tools or rule additions.
goethe.py: bump `__version__` on any public method change.
goethe_mcp.py: bump on transport/CORS/schema changes only.
