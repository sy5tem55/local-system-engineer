"""
probe_wifi.py — WiFi client metadata enrichment
Queries WiFi routers for connected client details: SSID, band, RSSI, TX/RX rates.
Enriches snapshot devices populated by probe_dhcp and probe_icmp.

Supported router types:
  asus_stock  — ASUS GT-BE19000 (AP mode) via asusrouter Python library
  teltonika   — Teltonika RUTX50 via RutOS JSON-RPC /ubus endpoint (implemented)

ENRICHMENT ONLY. Device discovery is probe_dhcp + probe_icmp.
The ASUS is in AP mode; pfSense handles all DHCP. WiFi clients already appear
in pfSense leases. This probe adds RSSI, band, and tx/rx rate metadata.

RutOS JSON-RPC (Teltonika):
  Endpoint: POST http://<host>/ubus
  Auth:     POST session.login with username+password → ubus_rpc_session token
  Clients:  iwinfo.assoclist {device: "radioX"} → signal, tx_rate, rx_rate per MAC
  Radios:   RUTX50 tri-band: radio0=2.4GHz, radio1=5GHz, radio2=6GHz
  NOTE:     Starting firmware 07.18, JSON-RPC support package must be installed via
            Package Manager (System → Package Manager → json-rpc support → Install).
  Enable:   set wifi_routers[teltonika_rutx50].enabled=true in config.json

PRE-INSTALL RULE: Before running pip install for any dependency, ALWAYS check
whether the package is already installed:
  pip show asusrouter       → check version before installing
  pip show requests         → likely already installed system-wide
Do NOT blindly run pip install — Prometheus, Grafana, networkx, requests,
prometheus_client, zeroconf are ALREADY RUNNING on this host.

Requirements:
  pip install asusrouter --break-system-packages   (ASUS probe)
  pip install requests --break-system-packages      (Teltonika probe — likely already present)

Security: passwords are read from environment variables only. Never hardcoded.
"""

import asyncio
import logging
import os
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

_ASUS_PKG = "asusrouter"

# Teltonika RUTX50 radios to probe. Try all — missing ones return error code, not exception.
_RUTX50_RADIOS = ["radio0", "radio1", "radio2", "radio3"]
_RUTOS_TIMEOUT = 10  # seconds per HTTP request


# ── Utility helpers ────────────────────────────────────────────────────────────

def _check_pkg_installed(pkg: str) -> bool:
    """Return True if a Python package is importable. No install attempted."""
    import importlib.util
    return importlib.util.find_spec(pkg) is not None


def _normalize_mac(mac: str) -> str:
    mac = mac.strip().lower().replace("-", ":").replace(".", ":")
    if len(mac) == 12 and ":" not in mac:
        mac = ":".join(mac[i:i+2] for i in range(0, 12, 2))
    return mac


def _get_attr(obj, *attrs) -> Optional[Any]:
    """Try multiple attribute/key names on obj; return first non-None/non-empty value."""
    for attr in attrs:
        if isinstance(obj, dict):
            val = obj.get(attr)
        else:
            val = getattr(obj, attr, None)
        if val is not None and val != "" and val != 0:
            return val
    return None


def _normalize_band(band_raw) -> Optional[str]:
    """Map asusrouter band values to snapshot schema strings: 2.4GHz / 5GHz / 6GHz."""
    if band_raw is None:
        return None
    s = str(band_raw).lower().strip()
    if any(x in s for x in ("2.4", "2g", "band_2", "24ghz")):
        return "2.4GHz"
    if any(x in s for x in ("6g", "band_6", "6ghz")) and "2" not in s:
        return "6GHz"
    if any(x in s for x in ("5g", "band_5", "5ghz", "5.0")):
        return "5GHz"
    if s == "0":
        return "2.4GHz"
    if s == "1":
        return "5GHz"
    if s == "2":
        return "6GHz"
    log.debug(f"probe_wifi: unrecognized band value '{band_raw}' — passing through")
    return str(band_raw)


def _freq_to_band(freq_mhz: int) -> str:
    """Map 802.11 centre frequency (MHz) to human band label."""
    if freq_mhz <= 0:
        return "unknown"
    if freq_mhz < 3000:
        return "2.4GHz"
    if freq_mhz < 6000:
        return "5GHz"
    return "6GHz"


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


# ── RutOS JSON-RPC helpers ─────────────────────────────────────────────────────

def _rutos_login(host: str, username: str, password: str) -> str:
    """
    Authenticate to RutOS JSON-RPC endpoint and return a session token.

    RutOS endpoint: POST http://<host>/ubus
    Uses the null session token (32 zeros) for the initial login call.
    Returns ubus_rpc_session string on success.

    NOTE: From firmware 07.18+, the 'JSON-RPC support' package must be installed
    via Package Manager before this will work.
    """
    import requests  # checked by caller via _check_pkg_installed

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "call",
        "params": [
            "00000000000000000000000000000000",
            "session", "login",
            {"username": username, "password": password},
        ],
    }
    resp = requests.post(
        f"http://{host}/ubus", json=payload, timeout=_RUTOS_TIMEOUT
    )
    resp.raise_for_status()
    result = resp.json().get("result", [])
    if not result or result[0] != 0:
        code = result[0] if result else "no result"
        raise RuntimeError(
            f"RutOS login failed (code={code}). "
            "Check credentials and that JSON-RPC support package is installed."
        )
    return result[1]["ubus_rpc_session"]


def _rutos_call(
    session: str,
    host: str,
    service: str,
    method: str,
    args: Optional[Dict] = None,
) -> Dict:
    """
    Make an authenticated JSON-RPC call to RutOS /ubus.

    Returns the result dict (result[1]) on success.
    Raises RuntimeError if the router returns a non-zero ubus status code.
    """
    import requests

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "call",
        "params": [session, service, method, args or {}],
    }
    resp = requests.post(
        f"http://{host}/ubus", json=payload, timeout=_RUTOS_TIMEOUT
    )
    resp.raise_for_status()
    result = resp.json().get("result", [])
    if not result or result[0] != 0:
        code = result[0] if result else "no result"
        raise RuntimeError(
            f"RutOS {service}.{method} returned error code {code}"
        )
    return result[1] if len(result) > 1 else {}


# ── ASUS probe (async) ─────────────────────────────────────────────────────────

async def _probe_asus_async(router_cfg: Dict, snapshot: Dict) -> None:
    """
    Connect to ASUS router via asusrouter library and enrich snapshot with WiFi metadata.
    Uses AsusData.CLIENTS which returns all connected clients with WiFi details.
    """
    try:
        from asusrouter import AsusRouter
        from asusrouter.modules.data import AsusData
    except ImportError:
        raise ImportError(
            f"asusrouter package not installed.\n"
            f"  1. Check first:  pip show {_ASUS_PKG}\n"
            f"  2. If missing:   pip install {_ASUS_PKG} --break-system-packages"
        )

    host          = router_cfg["host"]
    username      = router_cfg.get("username", "admin")
    password_env  = router_cfg["password_env"]
    password      = os.environ.get(password_env, "")
    use_ssl       = router_cfg.get("use_ssl", False)
    router_id     = router_cfg["id"]
    serves_subnet = router_cfg.get("serves_subnet", "lan")

    if not password:
        raise EnvironmentError(
            f"probe_wifi: env var '{password_env}' is not set. "
            f"Export it before running: export {password_env}=<router-password>"
        )

    log.info(f"probe_wifi: connecting to ASUS {host} (id={router_id}, ssl={use_ssl})")

    router = AsusRouter(
        hostname=host,
        username=username,
        password=password,
        use_ssl=use_ssl,
    )

    clients_data = None
    try:
        await asyncio.wait_for(router.async_connect(), timeout=15)
        clients_data = await asyncio.wait_for(
            router.async_get_data(AsusData.CLIENTS), timeout=15
        )
        log.info(
            f"probe_wifi: ASUS {host} returned "
            f"{len(clients_data) if clients_data else 0} clients"
        )
    except asyncio.TimeoutError:
        log.error(f"probe_wifi: ASUS {host} timed out after 15s — skipping")
    finally:
        try:
            await router.async_disconnect()
        except Exception:
            pass

    if not clients_data:
        log.warning(f"probe_wifi: ASUS {host} returned no client data")
        return

    devices  = snapshot["devices"]
    enriched = 0

    for raw_mac, client in clients_data.items():
        norm_mac = _normalize_mac(str(raw_mac))
        dev = devices.get(norm_mac)

        if dev is None:
            log.debug(
                f"probe_wifi: {norm_mac} seen on WiFi but not in DHCP snapshot — adding"
            )
            ip = _get_attr(client, "ip_address", "ip", "ipaddress")
            dev = devices.setdefault(norm_mac, {
                "mac":       norm_mac,
                "ip":        ip,
                "status":    "unknown",
                "source":    [],
                "labels":    [],
                "dhcp":      None,
                "wifi":      None,
                "icmp":      None,
                "mdns":      None,
                "interface": serves_subnet,
                "subnet":    None,
            })
        else:
            if not dev.get("ip"):
                ip = _get_attr(client, "ip_address", "ip", "ipaddress")
                if ip:
                    dev["ip"] = ip

        ssid     = _get_attr(client, "ssid", "node", "connection_node")
        band_raw = _get_attr(client, "band", "connection_band", "radio", "frequency")
        rssi     = _get_attr(client, "rssi", "rssi_dbm", "signal", "signal_strength")
        tx_rate  = _get_attr(client, "tx_rate", "tx", "txrate", "tx_speed")
        rx_rate  = _get_attr(client, "rx_rate", "rx", "rxrate", "rx_speed")
        name     = _get_attr(client, "name", "nickname", "hostname", "alias")

        dev["wifi"] = {
            "ssid":     ssid,
            "band":     _normalize_band(band_raw),
            "rssi_dbm": _safe_float(rssi),
            "tx_rate":  _safe_float(tx_rate),
            "rx_rate":  _safe_float(rx_rate),
            "router":   router_id,
        }

        if name and not dev.get("hostname"):
            dev["hostname"] = name

        dev.setdefault("source", [])
        if "probe_wifi" not in dev["source"]:
            dev["source"].append("probe_wifi")

        enriched += 1

    log.info(f"probe_wifi: enriched {enriched} WiFi clients from ASUS {host}")


# ── Teltonika RutOS probe ──────────────────────────────────────────────────────

def _probe_teltonika(router_cfg: Dict, snapshot: Dict) -> None:
    """
    Teltonika RUTX50 WiFi client enrichment via RutOS JSON-RPC /ubus API.

    Flow:
      1. POST session.login  → ubus_rpc_session token
      2. For each radio (radio0..radio3):
         a. iwinfo.info  → ssid, frequency (band)
         b. iwinfo.assoclist → MAC, signal (dBm), tx_rate/rx_rate (kbps)
      3. Match client MACs against snapshot devices (already present from
         pfSense DHCP — RUTX50 bridges WiFi clients to OPT1 so their leases
         appear in pfSense). Add wifi: {ssid, band, rssi_dbm, tx_rate, rx_rate}.

    Prerequisites:
      - From firmware 07.18+: install 'JSON-RPC support' via Package Manager
        (System → Package Manager → search 'json-rpc' → Install)
      - Set RUTX50_PASS env var (and optionally RUTX50_USER, default: admin)
      - Enable probe: wifi_routers[teltonika_rutx50].enabled = true in config.json

    Radio mapping on RUTX50 (tri-band):
      radio0 = 2.4 GHz
      radio1 = 5 GHz
      radio2 = 6 GHz (if present)
    """
    if not _check_pkg_installed("requests"):
        raise ImportError(
            "probe_wifi (Teltonika): 'requests' package not installed.\n"
            "  Check first:  pip show requests\n"
            "  If missing:   pip install requests --break-system-packages"
        )

    host         = router_cfg["host"]
    username_env = router_cfg.get("username_env", "RUTX50_USER")
    password_env = router_cfg["password_env"]
    username     = os.environ.get(username_env, "admin")
    password     = os.environ.get(password_env, "")
    router_id    = router_cfg.get("id", "teltonika_rutx50")
    serves_subnet = router_cfg.get("serves_subnet", "opt1")

    if not password:
        raise EnvironmentError(
            f"probe_wifi: env var '{password_env}' is not set. "
            f"Export it before running: export {password_env}=<rutx50-password>\n"
            f"Username env: export {username_env}=admin  (default: admin)"
        )

    log.info(f"probe_wifi: connecting to Teltonika RUTX50 {host} via RutOS JSON-RPC")

    session = _rutos_login(host, username, password)
    log.debug(f"probe_wifi: RutOS session token obtained for {host}")

    devices  = snapshot["devices"]
    enriched = 0

    for radio in _RUTX50_RADIOS:
        # ── Step a: get radio info (ssid + frequency → band) ───────────────
        try:
            info = _rutos_call(session, host, "iwinfo", "info", {"device": radio})
        except RuntimeError as e:
            # Radio doesn't exist (ubus status 6 = NOT_FOUND) — skip silently
            log.debug(f"probe_wifi: {radio} not found on {host}: {e}")
            continue

        ssid      = info.get("ssid") or None
        freq_mhz  = info.get("frequency", 0)  # e.g. 2437, 5180, 5955
        band      = _freq_to_band(freq_mhz)
        log.info(
            f"probe_wifi: {radio} ssid={ssid!r} freq={freq_mhz}MHz band={band}"
        )

        # ── Step b: get associated clients ─────────────────────────────────
        try:
            assoc = _rutos_call(session, host, "iwinfo", "assoclist", {"device": radio})
        except RuntimeError as e:
            log.warning(f"probe_wifi: assoclist failed for {radio}: {e}")
            continue

        clients = assoc.get("results", [])
        log.info(
            f"probe_wifi: {radio} — {len(clients)} associated client(s)"
        )

        for client in clients:
            raw_mac = client.get("mac", "")
            if not raw_mac:
                continue
            norm_mac = _normalize_mac(raw_mac)

            # Signal level — iwinfo returns dBm (negative integer)
            signal   = _safe_float(client.get("signal"))

            # Rates — iwinfo returns kbps; convert to Mbps for schema consistency
            tx_kbps  = client.get("tx", {}).get("rate") if isinstance(client.get("tx"), dict) else None
            rx_kbps  = client.get("rx", {}).get("rate") if isinstance(client.get("rx"), dict) else None
            tx_mbps  = float(tx_kbps) / 1000 if tx_kbps is not None else None
            rx_mbps  = float(rx_kbps) / 1000 if rx_kbps is not None else None

            dev = devices.get(norm_mac)
            if dev is None:
                # WiFi client not yet in snapshot (missed by DHCP probe) — create stub
                log.debug(
                    f"probe_wifi: {norm_mac} on Teltonika {radio} "
                    f"not in DHCP snapshot — adding stub"
                )
                dev = devices.setdefault(norm_mac, {
                    "mac":       norm_mac,
                    "ip":        None,
                    "status":    "unknown",
                    "source":    [],
                    "labels":    [],
                    "dhcp":      None,
                    "wifi":      None,
                    "icmp":      None,
                    "mdns":      None,
                    "interface": serves_subnet,
                    "subnet":    "192.168.5.0/24",
                })

            dev["wifi"] = {
                "ssid":     ssid,
                "band":     band,
                "rssi_dbm": signal,
                "tx_rate":  tx_mbps,
                "rx_rate":  rx_mbps,
                "router":   router_id,
            }

            dev.setdefault("source", [])
            if "probe_wifi" not in dev["source"]:
                dev["source"].append("probe_wifi")

            enriched += 1

    log.info(
        f"probe_wifi: enriched {enriched} WiFi clients from Teltonika {host} "
        f"({len(_RUTX50_RADIOS)} radios probed)"
    )


# ── Entry point ────────────────────────────────────────────────────────────────

def run(config: Dict[str, Any], snapshot: Dict[str, Any]) -> None:
    """
    Entry point called by discovery_engine.py.
    Mutates snapshot['devices'] in place with WiFi metadata.
    Runs only for enabled routers in config['wifi_routers'].
    """
    wifi_routers = config.get("wifi_routers", [])
    enabled      = [r for r in wifi_routers if r.get("enabled", False)]

    if not enabled:
        log.info("probe_wifi: no enabled WiFi routers in config — skipping")
        return

    for router_cfg in enabled:
        router_type = router_cfg.get("type")
        router_id   = router_cfg.get("id", "unknown")

        log.info(f"probe_wifi: starting {router_id} (type={router_type})")

        try:
            if router_type == "asus_stock":
                if not _check_pkg_installed(_ASUS_PKG):
                    log.error(
                        f"probe_wifi: '{_ASUS_PKG}' not installed.\n"
                        f"  Check first : pip show {_ASUS_PKG}\n"
                        f"  If missing  : pip install {_ASUS_PKG} --break-system-packages\n"
                        f"  DO NOT install if already present — check pip show first."
                    )
                    snapshot.setdefault("meta", {}).setdefault("probes_failed", []).append(
                        f"wifi_{router_id}_pkg_missing"
                    )
                    continue
                asyncio.run(_probe_asus_async(router_cfg, snapshot))

            elif router_type == "teltonika":
                _probe_teltonika(router_cfg, snapshot)

            else:
                log.warning(
                    f"probe_wifi: unknown router type '{router_type}' "
                    f"for {router_id} — skipping"
                )

        except Exception as e:
            log.error(f"probe_wifi: {router_id} failed: {e}", exc_info=True)
            snapshot.setdefault("meta", {}).setdefault("probes_failed", []).append(
                f"wifi_{router_id}"
            )
