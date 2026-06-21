# Gate 2 — Agent Kickoff Brief

Paste the block below to the LSE agent. Before you do, set up a **native-fs working copy** the same
way Gate 1 worked (the agent cannot write to `/mnt/c`, and native ext4 avoids the 30s-install /
slow-fs traps):

```bash
# you, once, in WSL2 bash:
mkdir -p ~/cg2 && cp -r /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/coding-gauntlet/{gate2-group-server,design-tokens} ~/cg2/
cd ~/cg2/gate2-group-server && rm -rf node_modules && npm install
```

Then paste:

---

TASK: Coding Gauntlet — Gate 2 (The Group Server). Make the acceptance harness green.

ENVIRONMENT (read first):
- Working dir: /home/sy5/cg2/gate2-group-server — cd there. Native Linux fs: write files directly
  with execute_command (shell redirects work, no delegation). Do NOT write to or `find` /mnt/c.
- Dependencies are already installed. Do NOT run `npm install`. Just run `npm test`.
- Keep each command under ~30s; split long ones into separate execute_command calls.

START: cd /home/sy5/cg2/gate2-group-server && cat SPEC.md && npm test
SPEC.md is the contract; the harness in test/ is ground truth. Do NOT edit the harness or any FROZEN
file: src/schema.ts, src/tokens.ts, src/protocol.ts, ../design-tokens. The harness drives your
server end-to-end (REST + WebSocket) with an injected FAKE model, so you implement real behaviour,
not stubs that satisfy a unit.

IMPLEMENT (stubs throw NOT IMPLEMENTED; see SPEC.md for the full contract). Suggested order — get
each green before the next:
1. src/db.ts — openStore(path): SQLite-backed accounts/rooms/memberships/messages; survives restart
   (a fresh Store over the same file returns the same data). Messages via the schema (de)serializers.
2. src/auth.ts — makeAuth(store, secret): register/login (hash the password, no plaintext at rest),
   verifyToken(token)->accountId.
3. src/server.ts — createServer(deps): HTTP (REST routes per protocol.ts) + WebSocket (`ws`). Auth
   gates every room read/write (401 no token, 403 not a member). listen(0) -> ephemeral port;
   fetch(req) for in-process REST; url()/wsUrl(token). On a `send`: persist the message, FAN IT OUT
   to ALL subscribers of the room (not just the sender), then drive runTurn so @mentioned agents reply.
4. src/orchestrator.ts — parseMentions, MentionReplyPolicy (respond only to @mentioned agents, never
   the author, only while budget>0), and runTurn (a human message opens a turn with
   DEFAULT_TURN_BUDGET; each agent reply draws down the SAME budget; model messages never open a new
   turn -> the model<->model chain is provably finite).
5. src/agents.ts — generateAgentReply(agent, roomId, history, model, signal): build messages from
   history + persona, call model.complete, wrap as a canonical assistant Message authored by the agent.
6. src/model_live.ts — makeLiveModelClient(): a ModelClient wrapping Gate 1's SSE transport
   (stream -> string), honouring the abort signal. (Only the [live] test needs this.)
7. src/index.ts — `npm start`: openStore(DB_PATH) + makeLiveModelClient() + createServer().listen(PORT);
   Ctrl-C -> clean close.

LOOP: implement one module -> npm test -> read the failing assertion -> fix. Budget: stop after ~6
tries per module and report the blocker rather than burn compute. Don't edit the harness.

DONE: npm test all green offline (5 [agent] checks: auth, @mention reply, model<->model terminates,
restart persistence, fan-out to all subscribers). Then run:
  GATE2_LIVE=1 LLAMA_URL=http://node4090.home.arpa:8080 npm test
REPORT the actual `npm test` summary verbatim (pass/fail/skip) — not a claim.

---

## What you (Joe) verify after it claims green (same close-out as Gate 1)

1. **Integrity diff** — confirm it didn't edit the grader or frozen contracts:
   ```bash
   cd ~/cg2/gate2-group-server
   REPO=/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/coding-gauntlet
   for f in test/acceptance.test.ts src/schema.ts src/tokens.ts src/protocol.ts; do
     diff -q "$f" "$REPO/gate2-group-server/$f" >/dev/null && echo "UNCHANGED  $f" || echo "MODIFIED   $f  <-- investigate"
   done
   ```
2. **Eye test the harness can't see** — the web client (`web/index.html`) and a real 2-human room.
   Open `npm start`, point two browser tabs / clients at it, confirm a message from one human appears
   for the other and an `@mention` gets a reply. (The backend is graded; the web UI is manual, like
   Gate 1's TUI.)
3. **Copy back + commit** from WSL2/PowerShell once green and verified:
   `cp ~/cg2/gate2-group-server/src/* "$REPO/gate2-group-server/src/"`

## Note on the "without Opus" experiment

Gate 2 is a bigger surface than Gate 1 (a stateful server with auth, persistence, realtime fan-out,
and the termination-guaranteed orchestrator) — a harder test of the local model's ceiling on a
single long-horizon task. The cross-family GLM critic isn't in the loop yet (it needs the node3090
contention resolved + GLM deployed). When it is, re-run a gate with planner+coder+critic and measure
what the critic catches that a human/frontier reviewer would have — that delta is the answer to "how
far without Opus." For now this is the same single-agent loop that cleared Gate 1, on a tougher gate.
