# A2A Operations Runbook — node4090 ⇄ node3090 web-research delegation

Version 1.0 · 2026-09-16 · Built from task 58fffd80 (17/18 verified E2E).

## Topology

| Node | Component | Port | Notes |
|---|---|---|---|
| node4090 | goethe_mcp gateway (goethe_web.py) | 9700 | Delegates `search_reddit`/`fetch_url` to node3090 via A2A; local SearxNG/curl fallback |
| node4090 | A2A client | — | `/opt/local-se/a2a/a2a_client.py`; pins CA, Ed25519 JWT sign |
| node3090 | lse-a2a-web-research.service | 9701 (HTTPS) | a2a-sdk 1.1.2 venv; public `/health`, `/agent-card`; JWT verify (node4090 pub key) |
| node3090 | camofox-browser (docker) | — | Reddit/old.reddit.com route |
| node3090 | firecrawl-api-1 (docker) | 3002 (LAN) | All other URLs |

Audit logs: node4090 `/opt/local-se/a2a/logs/fetch-audit.jsonl` · node3090 `/opt/local-se/a2a/logs/a2a-audit.jsonl`
Review both: `bash /opt/local-se/a2a/review_audit.sh -n 20` (includes df disk check; nonzero exit on disk full).

## Failure modes

### 1. node3090 down
Symptom: node4090 audit shows `routing: "local"` fallback lines; `ping node3090.home.arpa` fails.
Delegation fails open — MCP tools keep working via SearxNG/curl. No user-visible breakage.
Recovery:
```
ping -c1 -W2 node3090.home.arpa          # confirm down
# wake via Goethe MCP: wake_node("node3090")  (WoL via pfSense, polls up to 120s)
ssh_run node3090.home.arpa "systemctl is-active lse-a2a-web-research"   # expect active
```
If unit not active: `systemctl restart lse-a2a-web-research`, then verify `curl -k https://127.0.0.1:9701/health`.

### 2. firecrawl down (non-reddit URLs)
Symptom: node3090 audit `routing: "firecrawl"` + `status: "failed"` / ConnectError; non-reddit A2A tasks TASK_STATE_FAILED.
Recovery (on node3090):
```
docker ps --filter name=firecrawl-api-1 --format '{{.Names}} {{.Status}}'
docker start firecrawl-api-1            # plus supporting containers if down:
docker start firecrawl-rabbitmq-1 firecrawl-redis-1 firecrawl-nuq-postgres-1 firecrawl-foundationdb-1 firecrawl-playwright-service-1
curl -s http://localhost:3002/api/v2/scrape -o /dev/null -w '%{http_code}\n'  # 200/4xx = up
```
Then re-send one A2A task (`python3 /opt/local-se/a2a/a2a_client.py send "https://example.com"`) to confirm.

### 3. camoufox down (reddit URLs)
Symptom: node3090 audit `routing: "camoufox"` + ConnectError; reddit A2A tasks fail while firecrawl works.
Recovery (on node3090):
```
docker ps --filter name=camofox-browser --format '{{.Names}} {{.Status}}'
docker start camofox-browser
```
Re-test with a reddit A2A task (expect ~10s latency, `status: completed`).

### 4. JWT clock skew
Symptom: A2A calls fail with 401/expired/nbf errors even though both nodes reachable. Ed25519 JWT enforces exp/nbf; skew > tolerance rejects.
Recovery:
```
# node4090 (WSL2):
timedatectl status                       # check NTP synchronized: yes
sudo timedatectl set-ntp true            # delegation block required
# node3090:
ssh_run node3090.home.arpa "timedatectl status | grep -i ntp"
```
Goethe `time_check()` verifies node4090 clock vs NTP + TLS date (report-only — never auto-fix).
Verify: re-run one A2A task; audit `status: completed` with no 401.

### 5. Audit disk full
Symptom: `review_audit.sh` exits nonzero with df warning; audit JSONL stops growing.
Recovery:
```
df -h /opt/local-se
# rotate: keep last 10k lines
tail -10000 /opt/local-se/a2a/logs/fetch-audit.jsonl > /tmp/f.jsonl && mv /tmp/f.jsonl /opt/local-se/a2a/logs/fetch-audit.jsonl
```
(same for node3090 `a2a-audit.jsonl` via ssh_script). Audit is append-only by design — never edit in place, truncate/rotate only.

### 6. Port conflict 9700/9701
Symptom: gateway or A2A service fails to bind; log shows "Address already in use".
Diagnose:
```
ss -tlnp | grep -E ':(9700|9701)'       # on each node — identify the squatting pid
```
Recovery: stop the unowned process first (confirm identity!), then
- node4090: `bash ~/projects/local-system-engineer/tools/start-goethe.sh` (gateway :9700)
- node3090: `systemctl restart lse-a2a-web-research` (:9701)
Verify both: `ss -tlnp | grep -E ':(9700|9701)'` shows python3 on both ports.

## Key rotation / TLS pinning recovery
- Keys: node4090 `/opt/local-se/a2a/keys/node4090.ed25519.key` (600); pub in `agent-cards/`. node3090 keys NEVER leave node3090.
- Rotate node4090 key: regenerate → update `agent-cards/node4090.pub` on node3090 → restart `lse-a2a-web-research` → test task.
- Rotate CA: regenerate CA+server certs → distribute CA to both nodes → update CA pin config on both → restart both services.
- After any key/cert change: run one full A2A task and confirm audit `completed` on both sides.

## Standing verification (all green = healthy)
```
# node4090
ss -tlnp | grep -E ':(9700|9701)'
bash /opt/local-se/a2a/review_audit.sh -n 5
# node3090 (ssh)
systemctl is-active lse-a2a-web-research
curl -k https://127.0.0.1:9701/health
docker ps --format '{{.Names}} {{.Status}}' | grep -Ei 'camofox|firecrawl-api'
```
