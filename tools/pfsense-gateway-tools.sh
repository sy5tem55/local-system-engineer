#!/bin/bash
# pfSense Log Gateway Tool Wrapper
# Provides on-demand gateway access for LSE tool calls
# Usage: source this or call individual functions

export PFSENSE_URL="https://pfsense.home.arpa"
export OLLAMA_URL="http://localhost:11434"
# PFSENSE_API_KEY is not stored here.
# LSE retrieves it from Vaultwarden and passes it via the PFSENSE_API_KEY env var
# or the OpenWebUI valve. Do not add key storage to this file.

GATEWAY_PORT="${GATEWAY_PORT:-9191}"
GATEWAY_URL="http://localhost:$GATEWAY_PORT"
GATEWAY_SCRIPT="/opt/local-se/pfsense_log_gateway.py"

# Start gateway if not running.
# PFSENSE_API_KEY must be in env before calling this (passed by the LSE tool function).
# The gateway will start without it and return auth errors on pfSense calls — not a crash.
gateway_ensure_running() {
    if ! pgrep -f "pfsense_log_gateway.py" > /dev/null 2>&1; then
        echo "Starting pfSense Log Gateway..."
        mkdir -p /tmp/lse /opt/local-se/logs /opt/local-se/tmp
        nohup env PFSENSE_URL="$PFSENSE_URL" PFSENSE_API_KEY="${PFSENSE_API_KEY:-}" OLLAMA_URL="$OLLAMA_URL" \
            python3 "$GATEWAY_SCRIPT" --port "$GATEWAY_PORT" >> /opt/local-se/logs/gateway.log 2>&1 &
        sleep 2
        curl -sf "$GATEWAY_URL/health" > /dev/null || { echo "Gateway failed to start — check /opt/local-se/logs/gateway.log"; return 1; }
    fi
}

# Gateway summary - replaces raw firewall log fetch
gateway_summary() {
    local hours="${1:-24}"
    local top_n="${2:-10}"
    gateway_ensure_running
    curl -sf "$GATEWAY_URL/summary?hours=$hours&top_n=$top_n" | python3 -m json.tool 2>/dev/null || echo "Gateway error"
}

# Gateway compact - dense audit summary (use for full pfSense reports)
gateway_compact() {
    local hours="${1:-24}"
    gateway_ensure_running
    curl -sf "$GATEWAY_URL/compact?hours=$hours" | python3 -m json.tool 2>/dev/null || echo "Gateway error"
}

# Gateway tail - recent filtered logs
gateway_tail() {
    local lines="${1:-20}"
    local action="${2:-}"
    local source="${3:-}"
    local pattern="${4:-}"
    gateway_ensure_running
    local url="$GATEWAY_URL/tail?lines=$lines"
    [ -n "$action" ] && url="$url&action=$action"
    [ -n "$source" ] && url="$url&source=$source"
    [ -n "$pattern" ] && url="$url&pattern=$pattern"
    curl -sf "$url" | python3 -m json.tool 2>/dev/null || echo "Gateway error"
}

# Gateway events - incremental since cursor
gateway_events() {
    gateway_ensure_running
    curl -sf "$GATEWAY_URL/events" | python3 -m json.tool 2>/dev/null || echo "Gateway error"
}

# Gateway search
gateway_search() {
    local query="$1"
    gateway_ensure_running
    curl -sf "$GATEWAY_URL/search?query=$query" | python3 -m json.tool 2>/dev/null || echo "Gateway error"
}

# Gateway metrics
gateway_metrics() {
    gateway_ensure_running
    curl -sf "$GATEWAY_URL/metrics" | python3 -m json.tool 2>/dev/null || echo "Gateway error"
}

# Gateway health check
gateway_health() {
    curl -sf "$GATEWAY_URL/health" | python3 -m json.tool 2>/dev/null || echo "Gateway not running"
}

# Stop gateway
gateway_stop() {
    pkill -f "pfsense_log_gateway.py" 2>/dev/null && echo "Gateway stopped" || echo "Gateway was not running"
}

# If called directly (not sourced), run the command passed as argument
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    case "${1:-}" in
        summary)  shift; gateway_summary "$@" ;;
        compact)  shift; gateway_compact "$@" ;;
        tail)     shift; gateway_tail "$@" ;;
        events)   gateway_events ;;
        search)   shift; gateway_search "$@" ;;
        metrics)  gateway_metrics ;;
        health)   gateway_health ;;
        stop)     gateway_stop ;;
        restart)  gateway_stop; sleep 1; gateway_ensure_running ;;
        *)        echo "Usage: $0 {summary|compact|tail|events|search|metrics|health|stop|restart}"; exit 1 ;;
    esac
fi
