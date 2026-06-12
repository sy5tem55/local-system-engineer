#!/usr/bin/env bash
# provision-node5090.sh v1.0 — runs INSIDE WSL Ubuntu-24.04 as root.
# Invoked by deploy-node5090.ps1. Idempotent — safe to re-run.
# Design: docs/node5090-deployment-design.md
set -euo pipefail

LSE_GID=1900
LLAMA_PORT=8080
MODEL_DIR=/opt/models
LSE_DIR=/opt/local-se
ENV_FILE=/etc/llama/llama-server-5090.env
# LUCIFER public keys — REPLACE with actual pubkeys before first run, or
# drop files into /tmp/authorized_keys.{lse-admin,sy5} prior to invocation.
LSE_ADMIN_PUBKEY_FILE=/tmp/authorized_keys.lse-admin
SY5_PUBKEY_FILE=/tmp/authorized_keys.sy5

step() { printf '\n>> %s\n' "$*"; }
ok()   { printf '   OK: %s\n' "$*"; }

# ── 1. Base packages + CUDA toolkit (WSL flavor) ─────────────────────────────
step "1/8 apt base + build deps"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq build-essential cmake git curl wget acl openssh-server \
    python3 python3-pip libcurl4-openssl-dev pkg-config ccache jq >/dev/null
ok "base packages"

if ! command -v nvcc >/dev/null 2>&1; then
    step "Installing CUDA toolkit (WSL-Ubuntu repo — does NOT touch the Windows driver)"
    wget -q https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-keyring_1.1-1_all.deb -O /tmp/cuda-keyring.deb
    dpkg -i /tmp/cuda-keyring.deb >/dev/null
    apt-get update -qq && apt-get install -y -qq cuda-toolkit >/dev/null
    ok "CUDA toolkit installed"
else
    ok "CUDA toolkit present: $(nvcc --version | grep release)"
fi

# ── 2. Group, users, sudoers, umask ──────────────────────────────────────────
step "2/8 lsestack group + users + scoped sudoers"
getent group lsestack >/dev/null || groupadd -g "$LSE_GID" lsestack
for u in sy5 lse-admin; do
    id "$u" >/dev/null 2>&1 || useradd -m -s /bin/bash "$u"
    usermod -aG lsestack "$u"
done
id llama >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin -G lsestack llama
ok "users: sy5, lse-admin, llama (service) — all in lsestack"

cat > /etc/sudoers.d/lse-admin << 'EOF'
# Scoped NOPASSWD for lse-admin — node5090. No blanket ALL.
lse-admin ALL=(root) NOPASSWD: /usr/bin/systemctl restart llama-server-5090, /usr/bin/systemctl stop llama-server-5090, /usr/bin/systemctl start llama-server-5090, /usr/bin/journalctl *, /usr/sbin/shutdown *
EOF
chmod 440 /etc/sudoers.d/lse-admin && visudo -cf /etc/sudoers.d/lse-admin >/dev/null
ok "sudoers scope installed + validated"

cat > /etc/profile.d/lsestack.sh << 'EOF'
# group-write by default for lsestack members (see node5090-deployment-design.md §4)
if id -nG 2>/dev/null | grep -qw lsestack; then umask 002; fi
EOF
ok "umask 002 for lsestack members"

# ── 3. Directory tree: one canonical model location, setgid + default ACLs ───
step "3/8 /opt tree (root:lsestack 2775 + default ACLs)"
for d in "$MODEL_DIR" "$LSE_DIR" "$LSE_DIR/kb" "$LSE_DIR/logs" "$LSE_DIR/scripts"; do
    mkdir -p "$d"
    chown root:lsestack "$d"
    chmod 2775 "$d"
    setfacl -d -m g:lsestack:rwX "$d"
done
ok "dirs ready — group write works without sudo (the t3-005 lesson)"

# ── 4. SSH ───────────────────────────────────────────────────────────────────
step "4/8 sshd + authorized_keys"
for pair in "lse-admin:$LSE_ADMIN_PUBKEY_FILE" "sy5:$SY5_PUBKEY_FILE"; do
    u="${pair%%:*}"; kf="${pair##*:}"
    if [[ -s "$kf" ]]; then
        install -d -m 700 -o "$u" -g "$u" "/home/$u/.ssh"
        install -m 600 -o "$u" -g "$u" "$kf" "/home/$u/.ssh/authorized_keys"
        ok "authorized_keys installed for $u"
    else
        echo "   WARN: $kf missing — install $u's key manually before LSE can reach this node"
    fi
done
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl enable --now ssh >/dev/null 2>&1 || service ssh start
ok "sshd running, password auth disabled (key-only — infra-t3-002 standard)"

# ── 5. Build llama.cpp (CUDA) ────────────────────────────────────────────────
step "5/8 llama.cpp build"
if [[ ! -x /usr/local/bin/llama-server ]]; then
    git clone --depth 1 https://github.com/ggml-org/llama.cpp /opt/build/llama.cpp 2>/dev/null || \
        (cd /opt/build/llama.cpp && git pull --ff-only)
    cmake -S /opt/build/llama.cpp -B /opt/build/llama.cpp/build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release >/dev/null
    cmake --build /opt/build/llama.cpp/build --target llama-server -j"$(nproc)" >/dev/null
    install -m 755 /opt/build/llama.cpp/build/bin/llama-server /usr/local/bin/llama-server
    ok "llama-server built and installed to /usr/local/bin (canonical path, matches node3090)"
else
    ok "llama-server already at /usr/local/bin"
fi

# ── 6. Canonical launch env (single source of truth) ─────────────────────────
step "6/8 $ENV_FILE"
mkdir -p /etc/llama
if [[ ! -f "$ENV_FILE" ]]; then
cat > "$ENV_FILE" << EOF
# Canonical llama-server parameters for node5090 — edit HERE, then systemctl restart.
# NOTE: --no-mtp is MANDATORY for 35B A3B MoE (MTP fails on this architecture).
LLAMA_MODEL=$MODEL_DIR/Qwopus3.6-35B-A3B-v1-Q4_K_M/Qwopus3.6-35B-A3B-v1-Q4_K_M.gguf
LLAMA_CTX=98304
LLAMA_NGL=999
LLAMA_ARGS=--flash-attn on --cache-type-k q8_0 --no-mtp --jinja --metrics --host 0.0.0.0 --port $LLAMA_PORT --threads 8
EOF
    ok "env written (35B-A3B Q4_K_M @ 96k, q8_0, --no-mtp)"
else
    ok "env exists — not overwritten"
fi

# ── 7. systemd units ─────────────────────────────────────────────────────────
step "7/8 systemd units"
cat > /etc/systemd/system/llama-server-5090.service << EOF
[Unit]
Description=llama-server (node5090 — 35B-A3B coding delegate)
After=network.target
[Service]
User=llama
Group=lsestack
EnvironmentFile=$ENV_FILE
ExecStart=/usr/local/bin/llama-server --model \${LLAMA_MODEL} --ctx-size \${LLAMA_CTX} --n-gpu-layers \${LLAMA_NGL} \$LLAMA_ARGS
Restart=on-failure
RestartSec=10
StandardOutput=append:$LSE_DIR/logs/llama-server.log
StandardError=append:$LSE_DIR/logs/llama-server.log
[Install]
WantedBy=multi-user.target
EOF

if [[ ! -x /usr/local/bin/node_exporter ]]; then
    NE_VER=1.8.2
    wget -q "https://github.com/prometheus/node_exporter/releases/download/v${NE_VER}/node_exporter-${NE_VER}.linux-amd64.tar.gz" -O /tmp/ne.tgz
    tar -xzf /tmp/ne.tgz -C /tmp
    install -m 755 "/tmp/node_exporter-${NE_VER}.linux-amd64/node_exporter" /usr/local/bin/
fi
cat > /etc/systemd/system/node-exporter.service << 'EOF'
[Unit]
Description=Prometheus node_exporter
[Service]
User=llama
ExecStart=/usr/local/bin/node_exporter --web.listen-address=:9100
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF

pip3 install --quiet --break-system-packages nvidia-ml-py prometheus-client 2>/dev/null || true
# nvidia exporter: reuse the LUCIFER exporter script if synced to /opt/local-se/scripts/, else skip
systemctl daemon-reload
systemctl enable --now node-exporter >/dev/null 2>&1
systemctl enable llama-server-5090 >/dev/null 2>&1
ok "units installed (llama-server-5090 enabled — starts once model file exists)"

# ── 8. Model fetch + health ──────────────────────────────────────────────────
step "8/8 model + verify"
# shellcheck disable=SC1090
source "$ENV_FILE"
if [[ -f "$LLAMA_MODEL" ]]; then
    systemctl restart llama-server-5090
    for i in $(seq 1 18); do
        curl -sf "http://localhost:$LLAMA_PORT/health" | grep -q ok && { ok "llama-server healthy"; break; }
        sleep 10
    done
else
    echo "   WARN: model not present at $LLAMA_MODEL"
    echo "   Fetch (pick one):"
    echo "     scp from NAS:  scp -r sy5@n45.home.arpa:/share/models/Qwopus3.6-35B-A3B-v1-Q4_K_M $MODEL_DIR/"
    echo "     then: systemctl start llama-server-5090"
fi

# group-write probe — the t3-005 regression test
sudo -u lse-admin bash -c "touch $MODEL_DIR/.writeprobe && rm $MODEL_DIR/.writeprobe" \
    && ok "GROUP-WRITE PROBE PASSED: lse-admin can manage $MODEL_DIR without sudo" \
    || echo "   FAIL: lse-admin cannot write $MODEL_DIR — fix before any cleanup challenge"

echo
echo "Provision complete. nvidia-smi check:"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo "  (GPU not visible — check Windows driver + WSL restart)"
