#!/bin/bash
# Run from WSL: bash /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/tools/save-meross-kb.sh
set -e
KB=/opt/local-se/kb/meross-mqtt-binding.md
cat > "$KB" << 'EOF'
# Meross Local MQTT Binding — Complete Process
> Written: 2026-06-09. Device: MSL120DR Smart Bulb RGB.

## Device
- Model: msl120dr (Meross Smart Bulb RGB)
- MAC: 48:E1:E9:6A:F3:4B
- LAN IP: 192.168.1.254
- MQTT Shared Key: b919a21cea7809182de3fd80db34bc30
- MQTT Broker: Mosquitto on Home Assistant (192.168.1.80:1883)
- pfSense block: rule id=4 (device → internet, cloud blocked)
- HA integration: meross_lan (NOT the Meross cloud integration)

## Tooling
- Repo: bytespider/Meross at /home/sy5/Meross
- Runtime: Node 18, tsx (ESM transformer) — NOT `node dist/`
- Build: `cd /home/sy5/Meross && npm install && npm run build`
- All commands run as: `cd /home/sy5/Meross/packages/cli && npx tsx src/meross-setup.ts [options]`
- CRITICAL: --key <shared-key> is REQUIRED on ALL commands. Signs HTTP requests. Without it device rejects.
- CRITICAL: --mqtt requires full URL scheme: `mqtt://192.168.1.80:1883` — NOT just `192.168.1.80:1883`

## Scenario A: Device online on LAN (192.168.1.254)
```bash
cd /home/sy5/Meross/packages/cli && npx tsx src/meross-setup.ts \
  --ip 192.168.1.254 \
  --key b919a21cea7809182de3fd80db34bc30 \
  --mqtt mqtt://192.168.1.80:1883
```

## Scenario B: Device in ad-hoc WiFi (Meross_LB_F34B)
Triggered when device can't reach its configured broker or needs re-pairing.

Step 1 — Connect Windows to ad-hoc AP:
  ncpa.cpl → connect to Meross_LB_F34B (open, no password)
  Device is at gateway 10.10.10.1
  Verify from WSL: `ping -c 3 10.10.10.1`

Step 2 — Push MQTT config (from ad-hoc network):
```bash
cd /home/sy5/Meross/packages/cli && npx tsx src/meross-setup.ts \
  --ip 10.10.10.1 \
  --key b919a21cea7809182de3fd80db34bc30 \
  --mqtt mqtt://192.168.1.80:1883
```
Device reboots after this.

Step 3 — Push WiFi credentials (after device responds to ping again):
```bash
cd /home/sy5/Meross/packages/cli && npx tsx src/meross-setup.ts \
  --ip 10.10.10.1 \
  --key b919a21cea7809182de3fd80db34bc30 \
  --wifi-ssid 'Y_IoT' \
  --wifi-pass '@bocmap-cobDuh-7qenhy!'
```
Device reboots and joins home WiFi. Unreachable ~2 minutes.

Step 4 — Verify: `ping -c 3 192.168.1.254`

## Scenario C: Enter pairing mode manually
- Rapidly cycle power ON-OFF 3-4 times
- Bulb flashes rapidly = pairing mode (~2-3 min window)
- Timeout → full power cycle (unplug 5s, replug)
- Falls back to ad-hoc WiFi → go to Scenario B

## Post-Binding: HA meross_lan integration
HA → Settings → Devices → Add Integration → Meross LAN → Add Hub → Manually configure
  Device host: 192.168.1.254
  Device key: b919a21cea7809182de3fd80db34bc30
meross_lan auto-detects MQTT capability and switches from HTTP polling to MQTT push.
Verify: integration → device protocol shows MQTT (not HTTP).
pfSense: no outbound traffic from 192.168.1.254 after binding.

## Known Issue: Spontaneous Turn-On
Device firmware turns bulb on randomly despite cloud being blocked.
The MQTT key was generated locally so cloud block does not prevent this — it's hardcoded firmware.
HA logs spontaneous events differently:
  - User/automation-initiated: context.user_id set OR context.parent_id set
  - Firmware spontaneous: context.user_id = null AND context.parent_id = null
Fix: HA automation that detects spontaneous turn-on and turns off immediately.
See: /opt/local-se/kb/meross-spontaneous-turnon-automation.yaml

## meross-setup option reference
--ip <ip>              Device IP (required)
--key <key>            Shared key (required on ALL commands)
--mqtt <url>           MQTT broker URL (must include mqtt:// scheme)
--wifi-ssid <ssid>     WiFi SSID (1-32 chars)
--wifi-pass <pass>     WiFi password (8-64 chars)
--wifi-encryption <n>  Encryption type (from meross-info --include-wifi)
--wifi-cipher <n>      Cipher number
--wifi-bssid <mac>     Router MAC (colon-separated)
--wifi-channel <n>     Channel 1-13
--set-time             Set device time
EOF
chmod 600 "$KB"
echo "Written: $KB"
EOF
chmod +x /sessions/exciting-amazing-bohr/mnt/local-system-engineer/tools/save-meross-kb.sh
echo "Script ready."
