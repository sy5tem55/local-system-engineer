#!/bin/bash
# Deploy ha-agent.py to /opt/local-se/ on LUCIFER WSL
# Run from WSL: bash /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/tools/deploy-ha-agent.sh
set -e

SRC=/mnt/c/Users/SY5/Claude/Projects/local-system-engineer
DEST=/opt/local-se

# 1. Deploy agent script
sudo cp "$SRC/ha-agent.py" "$DEST/ha-agent.py"
sudo chmod 755 "$DEST/ha-agent.py"
echo "✓ ha-agent.py deployed"

# 2. Deploy config (only if not already present — preserve live api_key)
CONF="$DEST/ha-agent.conf"
if [ ! -f "$CONF" ]; then
    sudo bash -c "cat > $CONF << 'EOF'
[lmstudio]
url   = http://192.168.5.41:1234
model = qwen/qwen3.6-27b

[openwebui]
url     = http://localhost:3000
api_key = sk-e0d74239d854484b8756e8f2f18d9193
model   = local-system-engineer

[homeassistant]
url     = http://homeassistant.home.arpa:8123
EOF"
    sudo chmod 600 "$CONF"
    sudo chown sy5:sy5 "$CONF"
    echo "✓ ha-agent.conf created (chmod 600)"
else
    echo "  ha-agent.conf already exists — not overwritten"
fi

# 3. Verify
echo ""
echo "--- Verify ---"
python3 -c "import ast; ast.parse(open('$DEST/ha-agent.py').read()); print('Syntax OK')"
ls -la "$DEST/ha-agent.py" "$DEST/ha-agent.conf" 2>/dev/null || true

echo ""
echo "Deploy complete. Test with:"
echo "  python3 $DEST/ha-agent.py --prompt-only 'show all light entity IDs'"
