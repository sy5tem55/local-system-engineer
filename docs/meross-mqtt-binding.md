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
- Runtime: Node 18, tsx (ESM transformer) — NOT node dist/
- Build: cd /home/sy5/Meross && npm install && npm run build
- All commands: cd /home/sy5/Meross/packages/cli && npx tsx src/meross-setup.ts [options]
- CRITICAL: --key is REQUIRED on ALL commands — signs HTTP requests
- CRITICAL: --mqtt requires full URL scheme: mqtt://192.168.1.80:1883 (not just the IP)

## Scenario A: Device online on LAN
  cd /home/sy5/Meross/packages/cli && npx tsx src/meross-setup.ts \
    --ip 192.168.1.254 \
    --key b919a21cea7809182de3fd80db34bc30 \
    --mqtt mqtt://192.168.1.80:1883

## Scenario B: Device in ad-hoc WiFi (Meross_LB_F34B)
Step 1: Connect Windows to Meross_LB_F34B (open, no password). Device at 10.10.10.1
  Verify: ping -c 3 10.10.10.1

Step 2: Push MQTT config:
  cd /home/sy5/Meross/packages/cli && npx tsx src/meross-setup.ts \
    --ip 10.10.10.1 --key b919a21cea7809182de3fd80db34bc30 \
    --mqtt mqtt://192.168.1.80:1883
  Device reboots.

Step 3: Push WiFi credentials:
  cd /home/sy5/Meross/packages/cli && npx tsx src/meross-setup.ts \
    --ip 10.10.10.1 --key b919a21cea7809182de3fd80db34bc30 \
    --wifi-ssid 'Y_IoT' --wifi-pass '@bocmap-cobDuh-7qenhy!'
  Device reboots and joins home WiFi (~2 min).

Step 4: Verify: ping -c 3 192.168.1.254

## Scenario C: Enter pairing mode manually
- Cycle power ON-OFF 3-4 times rapidly → rapid flash = pairing mode (~2-3 min)
- Timeout → full power cycle (unplug 5s, replug) → then Scenario B

## Post-Binding: HA meross_lan integration
HA → Settings → Devices → Add Integration → Meross LAN → Add Hub → Manually configure
  Device host: 192.168.1.254
  Device key: b919a21cea7809182de3fd80db34bc30
meross_lan auto-detects MQTT and switches from HTTP polling to MQTT push.
Verify: integration shows MQTT (not HTTP). pfSense: no outbound from 192.168.1.254.

## Known Issue: Spontaneous Turn-On
Firmware turns bulb on randomly. Cloud block irrelevant — key is local, behaviour is hardcoded.
HA distinguishes:
  Spontaneous (firmware): context.user_id = null AND context.parent_id = null
  User/automation:         context.user_id set OR context.parent_id set
Fix: automation triggered on turn-on with context null check → turn off.
