
- RESTART ORDER (node3090 stack recovery): kill llama-server → poll nvidia-smi until VRAM ~0
  (never a fixed sleep — 3s caused tonight's silent relaunch failure) → canonical launch →
  poll /health up to 3 min → sudo systemctl reset-failed hermes-gateway → start gateway. Backend ALWAYS first.
- hermes-gateway hits systemd start-limit and goes inactive(dead) when its backend is down —
  reset-failed is required before start will work.



# 1. Clean slate + see WHY the relaunch died (the log tail will show OOM vs file error)
ssh lse-admin@192.168.5.41 'pkill -f llama-server; sleep 8; nvidia-smi --query-gpu=memory.used --format=csv,noheader; echo ---; tail -15 /home/lse-admin/llama-server.log'

# 2. Canonical launch (only when step 1 shows VRAM near 0)
ssh lse-admin@192.168.5.41 'nohup llama-server --model /opt/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf --ctx-size 81920 --n-gpu-layers 129 --flash-attn on --cache-type-k q8_0 --cache-type-v q8_0 --parallel 1 --threads 7 --threads-batch 7 --reasoning-budget 3072 --n-predict 8192 --jinja --metrics --host 0.0.0.0 --port 8080 </dev/null > /home/lse-admin/llama-server.log 2>&1 &'

# 3. Poll until healthy (loading 15.4GB from disk takes ~60-120s — don't panic early)
ssh lse-admin@192.168.5.41 'for i in $(seq 1 18); do curl -s http://localhost:8080/health | grep -q ok && { echo READY; break; }; echo waiting-$i; sleep 10; done; pgrep -af llama-server | head -1'

# 4. Only after READY: clear the start-limit and bring the gateway back
ssh lse-admin@192.168.5.41 'sudo systemctl reset-failed hermes-gateway; sudo systemctl start hermes-gateway; sleep 5; systemctl is-active hermes-gateway hermes-socat'



ssh lse-admin@192.168.5.41 'pkill -f "[l]lama-server"; sleep 8; nvidia-smi --query-gpu=memory.used --format=csv,noheader; echo ---; tail -15 /home/lse-admin/llama-server.log'


(base) sy5@LUCIFER:~$ ssh lse-admin@192.168.5.41 'echo CONNECTED; hostname; nvidia-smi --query-gpu=memory.used --format=csv,noheader'; echo "exit=$?"
CONNECTED
node3090
18 MiB
exit=0
(base) sy5@LUCIFER:~$

(base) sy5@LUCIFER:~$ ssh lse-admin@192.168.5.41 'ls -la /home/lse-admin/llama-server.log; echo ---; tail -15 /home/lse-admin/llama-server.log'
-rw-rw-r-- 1 lse-admin lse-admin 34192 Jun 11 23:40 /home/lse-admin/llama-server.log
---
20.37.825.388 I srv  params_from_: Chat format: peg-native
20.37.853.561 I slot get_availabl: id  0 | task -1 | selected slot by LCP similarity, sim_best = 0.986 (> 0.100 thold), f_keep = 0.994
20.37.854.132 I reasoning-budget: activated, budget=3072 tokens
20.37.854.171 I slot launch_slot_: id  0 | task 8804 | processing task, is_child = 0
20.37.854.185 I slot update_slots: id  0 | task 8804 | Checking checkpoint with [16014, 16014] against 16090...
20.37.871.288 W slot update_slots: id  0 | task 8804 | restored context checkpoint (pos_min = 16014, pos_max = 16014, n_tokens = 16015, n_past = 16015, size = 149.626 MiB)
20.38.234.485 I slot create_check: id  0 | task 8804 | created context checkpoint 4 of 32 (pos_min = 16315, pos_max = 16315, n_tokens = 16316, size = 149.626 MiB)
20.38.690.569 I reasoning-budget: deactivated (natural end)
20.39.375.368 I slot print_timing: id  0 | task 8804 | prompt eval time =     431.82 ms /   305 tokens (    1.42 ms per token,   706.30 tokens per second)
20.39.375.370 I slot print_timing: id  0 | task 8804 |        eval time =    1089.36 ms /    39 tokens (   27.93 ms per token,    35.80 tokens per second)
20.39.375.371 I slot print_timing: id  0 | task 8804 |       total time =    1521.18 ms /   344 tokens
20.39.375.372 I slot print_timing: id  0 | task 8804 |    graphs reused =       8724
20.39.375.972 I slot      release: id  0 | task 8804 | stop processing: n_tokens = 16358, truncated = 0
20.39.376.052 I srv  update_slots: all slots are idle
34.39.492.219 I srv    operator(): operator(): cleaning up before exit...


Backend is READY with the correct canonical args (PID 41557). Final step — clear the gateway's start-limit and bring it back:
ssh lse-admin@192.168.5.41 'sudo systemctl reset-failed hermes-gateway; sudo systemctl start hermes-gateway; sleep 5; systemctl is-active hermes-gateway hermes-socat'


Drop-in override (avoids editing the unit file directly) — paste into WSL:
bash ssh lse-admin@192.168.5.41 'sudo mkdir -p /etc/systemd/system/hermes-gateway.service.d && printf "[Service]\nTimeoutStopSec=210s\n" | sudo tee /etc/systemd/system/hermes-gateway.service.d/timeout.conf && sudo systemctl daemon-reload && systemctl show hermes-gateway -p TimeoutStopUSec && systemctl is-active hermes-gateway'
Expected: TimeoutStopSec=210s echoed back, TimeoutStopUSec=3min 30s, active. No restart needed — it applies on the next stop, which is exactly when it matters (210s > 180s drain_timeout, so systemd will let the drain finish instead of SIGKILLing at 90s). Paste the output and I'll update the roadmap.


Glob expanded in the non-root shell, which can't read that dir. Wrap the whole thing in a root shell:
ssh lse-admin@192.168.5.41 "sudo bash -c 'f=\$(ls -t /home/hermes-admin/.hermes/sessions/request_dump_*.json | head -1); echo \$f; grep -o \".\{100\}[Mm]emor.\{200\}\" \$f | head -10'"


(base) sy5@LUCIFER:~$ ssh lse-admin@192.168.5.41 'grep -n "lmstudio\|/opt/models\|--model\|-m " /opt/local-se/scripts/start-llama-server.sh 2>/dev/null; echo ---; ls -la /opt/local-se/scripts/ 2>/dev/null | head; echo ---; wc -l /opt/models/SHA256SUMS 2>/dev/null; tail -3 /opt/models/SHA256SUMS 2>/dev/null'
2:MODEL=/home/sy5/.lmstudio/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf
7:  --model "$MODEL" --ctx-size 96000 --n-gpu-layers 129 --flash-attn on \


ssh lse-admin@192.168.5.41 'sudo sed -i "s|MODEL=/home/sy5/.lmstudio/models/|MODEL=/opt/models/|" /opt/local-se/scripts/start-llama-server.sh && grep -n "MODEL=" /opt/local-se/scripts/start-llama-server.sh'

Node script done. Now apply the immutable bit — safe to do while the sha job runs (+i blocks writes/deletes, not reads):
bashssh lse-admin@192.168.5.41 'sudo find /opt/models -type f -name "*.gguf" -exec chattr +i {} \; && echo IMMUTABLE-SET; sudo lsattr /opt/models/lmstudio-community/Qwen3.6-27B-GGUF/*.gguf; echo ---; wc -l /opt/models/SHA256SUMS; pgrep -f "[s]ha256sum" >/dev/null && echo sha-RUNNING || echo sha-DONE'
Expected: IMMUTABLE-SET, ----i--------- flags on the Qwen files, and the sha job status. While that runs — you can also do the LM Studio repoint on node3090 whenever convenient (My Models → change models directory → /opt/models); it's independent of the restart step.

ssh lse-admin@192.168.5.41 'sudo sed -i "s/--ctx-size 96000/--ctx-size 81920/" /opt/local-se/scripts/start-llama-server.sh && grep -n "ctx-size" /opt/local-se/scripts/start-llama-server.sh'


KB check:

(base) sy5@LUCIFER:~$ curl -s "localhost:9200/_cat/indices/lse-*?v&h=index,health,docs.count,store.size"; cd /mnt/c/Users/SY5/Claude/Projects/local-system-engineer && python3 scripts/rfc_kb.py --status
index            health docs.count store.size
lse-kb           green          53        1mb
lse-rfc-kb       yellow        628     11.9mb
lse-search-cache green           0       249b
lse-errors       green           0       249b

     RFC  Chunks  Tagged  Avg Quality
  ──────  ──────  ──────  ───────────
     792      12      12        0.950  Internet Control Message Protocol
    1034      51      51        0.950  Domain Names — Concepts and Facilit
    1035      49      49        0.950  Domain Names — Implementation and S
    1122       2       2        0.950  Requirements for Internet Hosts — C
    2131      46      46        0.950  Dynamic Host Configuration Protocol
    2132      26      26        0.950  DHCP Options and BOOTP Vendor Exten
    2308      17      17        0.850  Negative Caching of DNS Queries (DN
    2782      10      10        0.850  A DNS RR for specifying the locatio
    4632      24      24        0.850  Classless Inter-domain Routing (CID
    5280     101     101        0.850  Internet X.509 Public Key Infrastru
    8446      84      84        0.850  The Transport Layer Security (TLS)
    9110     133     133        0.950  HTTP Semantics
    9293      73      73        0.950  Transmission Control Protocol (TCP)

(base) sy5@LUCIFER:/mnt/c/Users/SY5/Claude/Projects/local-system-engineer$


(base) sy5@LUCIFER:/mnt/c/Users/SY5/Claude/Projects/local-system-engineer$ curl -X PUT "localhost:9200/lse-rfc-kb/_settings" -H 'Content-Type: application/json' -d '{"index":{"number_of_replicas":0}}'
{"acknowledged":true}(base) sy5@LUCIFER:/mnt/c/Users/SY5/Claude/Projects/local-system-engineer$