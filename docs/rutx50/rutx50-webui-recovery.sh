#!/bin/sh
# RUTX50 WebUI Login-Failure Recovery Script
# Firmware: RUTX_R_00.07.23.4
# Symptom: WebUI serves login page but rejects valid credentials; SSH works
# Root cause suspect: LuaJIT 2.1 session/backend wedge in api_dispatcher.lua or 2FA module
#
# USAGE: Run via SSH when webui login fails:
#   ssh root@192.168.5.3 "sh -s" < /tmp/lse/rutx50-webui-recovery.sh
#
# This script does NOT reboot the router. It restarts only the web-stack services.
# The router will remain online and SSH will stay active.

echo "=== RUTX50 WebUI Recovery ==="
echo "Date: $(date)"

# Pre-restart state capture
echo "--- Pre-restart process state ---"
ps www | grep -E 'uhttpd|event_server|subscribe' | grep -v grep

echo "--- Pre-restart logread tail (last 10 lines) ---"
logread | tail -10

# Restart uhttpd — this will restart the main web server and its LuaJIT children
# event_server is managed separately by procd and will be respawned if killed
echo "--- Restarting uhttpd (web server + LuaJIT dispatcher) ---"
/etc/init.d/uhttpd restart

# Brief pause for services to come up
sleep 3

# Verify uhttpd is running
echo "--- Post-restart process state ---"
ps www | grep -E 'uhttpd|event_server|subscribe' | grep -v grep

# Verify HTTPS endpoint responds
echo "--- HTTPS endpoint check ---"
wget -q -O /dev/null --no-check-certificate --timeout=5 https://127.0.0.1/ 2>&1 && echo "HTTPS OK" || echo "HTTPS FAILED"

# Verify /api endpoint responds (LuaJIT dispatcher)
echo "--- API endpoint check ---"
wget -q -O /dev/null --no-check-certificate --timeout=5 https://127.0.0.1/api/unauthorized/status 2>&1 && echo "API OK" || echo "API FAILED"

echo "--- Post-restart logread tail (last 10 lines) ---"
logread | tail -10

echo "=== Recovery complete ==="
echo "Test webui login at https://192.168.5.3"
