# SY5 Home Network Map

**Last updated:** 2026-06-08

## Node Nomenclature
| Node Label | Hostname | IP | Notes |
|------------|----------|----|-------|
| NODE1 | node5090.home.arpa | 192.168.1.55 | X870E, 64GB RAM, 9800X3D, 5090. Windows hostname: 1BL15, part of SY5L4N workgroup |
| NODE2 | node4090.home.arpa | 192.168.1.57 | ROG MAXIMUS Z790 APEX, 14900K, 64GB RAM, 4090. Also: lucifer.home.arpa |
| NODE3 | node3090.home.arpa | 192.168.5.41 | Ubuntu 22.04, 9900K, 32GB RAM, 3090 24GB |

## pfSense Host Overrides (home.arpa)
| Hostname | IP | Description |
|----------|----|-------------|
| lucifer | 192.168.1.57 | Primary DNS alias, 14900K 64GB RAM 4090 |
| node4090 | 192.168.1.57 | LUCIFER GPU alias |
| node5090 | 192.168.1.55 | X870E 64GB RAM 9800X3D 5090 |

Note: node3090 resolves via DHCP static mapping DNS registration (no explicit host override needed).

## WAKE ON LAN — node3090 (192.168.5.41)
**Configured:** 2026-06-06

| Field | Value |
|---|---|
| **Hostname** | `node3090.home.arpa` |
| **IP** | `192.168.5.41` |
| **MAC** | `0c:9d:92:84:6e:6a` |
| **Interface** | `eno2` (Intel I219-V) |
| **WoL Mode** | `magic` (g — magic packet only) |
| **Persistence** | NetworkManager: `802-3-ethernet.wake-on-lan: magic` |
| **BIOS** | APM → Wake on PCIe device: **Enabled** |
| **TLP** | Not installed (no WoL interference) |
| **PCIe PM** | `on` (not aggressive) |

### How to Wake node3090

**From LUCIFER (WSL2) the `-i` flag is REQUIRED.** Measured 2026-07-31:

| Command | Result |
|---|---|
| `wakeonlan 0c:9d:92:84:6e:6a` | **DOES NOT WAKE** — no boot after 5 min |
| `wakeonlan -i 192.168.5.255 0c:9d:92:84:6e:6a` | **WAKES** — booted ~20s later |

Why: bare `wakeonlan` sends to `255.255.255.255`, a *global* broadcast, which
routers do not forward. LUCIFER is on `192.168.1.0/24`; node3090 is on
`192.168.5.0/24`. The packet dies at the boundary. `-i 192.168.5.255` sends a
*directed* broadcast that routes to node3090's own segment (via
`192.168.1.50` = pfsense.home.arpa) where the RUTX50 (`192.168.5.3`) sits.

```bash
wakeonlan -i 192.168.5.255 0c:9d:92:84:6e:6a
```

**Preferred: use the LSE tool**, which has always worked and needs no flags —
it POSTs to pfSense `/api/v2/services/wake_on_lan/send` with `interface: opt1`,
i.e. pfSense emits the packet *on the 5.x segment directly*:

```
wake_node("node3090")
```

**Boot timing (measured 2026-07-31):** packet → boot ≈ 20s; boot → pingable is
quick; **boot → llama-server `/health` = 200 takes >2 min** (model load). Poll
`/health`, never ping, before treating the node as usable.

> The bare-`wakeonlan` form above was documented here until 2026-07-31 and is
> what an agent following this KB would have run. It fails silently — the
> command prints "Sending magic packet" and exits 0 regardless.

### Verification Commands (on node3090)
```bash
sudo ethtool eno2 | grep -i wake    # Should show: Wake-on: g
nmcli connection show "Wired connection 1" | grep wake-on-lan    # Should show: magic
```

### Troubleshooting Checklist
- [x] BIOS Wake on PCIe device enabled
- [x] `ethtool` shows `Wake-on: g`
- [x] NetworkManager WoL persistence set to `magic`
- [x] TLP not installed (would disable WoL on shutdown)
- [x] PCIe power control is `on`
- [ ] **Shutdown test pending** — verify WoL survives `sudo poweroff`

## LAN (192.168.1.x) DHCP Static Mappings
| IP | Hostname | MAC | Description |
|----|----------|-----|-------------|
| 192.168.1.1 | GT-BE19000 | 10:7c:61:eb:02:30 | Asus GT-BE19000 router |
| 192.168.1.5 | sy5berry | d8:3a:dd:0e:1c:38 | PiHole DNS server (temporarily retired) |
| 192.168.1.55 | 1BL15 | a0:ad:9f:84:d5:bf | NODE1 / node5090 (X870E) |
| 192.168.1.57 | LUCIFER | 58:11:22:bf:80:02 | NODE2 / node4090 (Z790 APEX 14900K) |
| 192.168.1.65 | philipshue | 00:17:88:62:58:bc | Philips Hue |
| 192.168.1.70 | roborock-vacuum-a70 | b0:4a:39:4f:c8:39 | Roborock Vacuum |
| 192.168.1.75 | ipad | cc:44:63:e8:00:3d | SY5TEM75 iPad Pro 12.9" |
| 192.168.1.76 | fedeiphone | 36:89:34:c5:0e:57 | Fede iPhone |
| 192.168.1.80 | homeassistant | d8:3a:dd:2e:fc:1b | Home Assistant Supervised OS |
| 192.168.1.88 | x1 | b8:13:32:8e:07:aa | Bambu Lab X1 Carbon on wifi network "X" |
| 192.168.1.90 | samsungtv | 1c:af:4a:04:5f:b6 | Samsung S90C |
| 192.168.1.95 | lgtv | f8:b9:5a:ec:e1:d0 | LG OLED55CX |
| 192.168.1.115 | spider | d8:3a:dd:2e:fc:1c | Spider Robot |
| 192.168.1.125 | homebridge | 02:42:c0:a8:01:7d | Homebridge (Docker container) |
| 192.168.1.210 | p10w | 00:09:b0:13:ae:ab | Pioneer SC-LX801 AV receiver (WiFi) |
| 192.168.1.211 | p10 | 00:09:b0:4f:69:8d | Pioneer SC-LX801 AV receiver (Ethernet) |
| 192.168.1.220 | P100 | d8:44:89:4b:ef:34 | JVC Subwoofer Amplifier Smart Plug |
| 192.168.1.221 | P100tvsam | d8:44:89:4b:ef:32 | Samsung TV plug |
| 192.168.1.222 | goveeledstrip01 | d4:ad:fc:93:52:9c | Govee LED strip 01 |

## Asus GT-BE19000 WiFi Client List
**Source:** ClientList.csv export from Asus WebGUI
**Captured:** 2026-06-08
**All clients:** Internet access state = "Allow Internet access"

### Active Clients (18 online)

| IP | MAC | Manufacturer | Interface | Access Time | Notes |
|----|-----|--------------|-----------|-------------|-------|
| 192.168.1.65 | 00:17:88:62:58:BC | Philips Lighting BV | Wired | - | Philips Hue bridge |
| 192.168.1.50 | DE:AD:BE:EF:55:5A | (Spoofed MAC) | Wired | - | pfSense LAN interface |
| 192.168.1.70 | B0:4A:39:4F:C8:39 | Beijing Roborock Technology | 2.4 GHz | 15:08:25 | Roborock Vacuum |
| 192.168.1.80 | D8:3A:DD:2E:FC:1B | Raspberry Pi Trading Ltd | Wired | - | Home Assistant |
| 192.168.1.221 | D8:44:89:4B:EF:32 | (Unknown) | 2.4 GHz | 500:46:22 | Samsung TV plug |
| 192.168.1.220 | D8:44:89:4B:EF:34 | (Unknown) | 2.4 GHz | 500:46:21 | JVC Subwoofer plug |
| 192.168.1.57 | 58:11:22:BF:80:02 | ASUS | Wired | - | LUCIFER / node4090 |
| 192.168.1.90 | 1C:AF:4A:04:5F:B6 | Samsung Electronics | 5 GHz | 259:52:38 | Samsung S90C TV |
| 192.168.1.211 | 00:09:B0:4F:69:8D | Onkyo Technology K.K. | Wired | - | Pioneer SC-LX801 (Ethernet) |
| 192.168.1.35 | D0:C9:07:24:47:16 | Private | 2.4 GHz | 500:45:32 | **Unknown device** |
| 192.168.1.19 | 0E:6B:BE:41:0A:F0 | (Unknown) | 5 GHz | 04:39:03 | **Unknown device** |
| 192.168.1.38 | DA:30:92:C5:BB:7F | (Unknown) | 5 GHz | 166:20:26 | **Unknown device** |
| 192.168.1.33 | 4E:2F:D7:8D:C1:B7 | (Unknown) | 5 GHz | 04:39:04 | **Unknown device** |
| 192.168.1.45 | 48:E1:E9:6A:F3:4B | Chengdu Meross Technology | 2.4 GHz | 00:14:53 | **Meross Smart Bulb (recently reconnected)** |
| 192.168.1.32 | B2:68:EF:0B:F2:5C | (Unknown) | 6 GHz | 02:05:26 | **Unknown device** |
| 192.168.1.23 | D0:C9:07:7B:E1:14 | Private | 2.4 GHz | 500:45:32 | **Unknown device** |
| 192.168.1.20 | D0:C9:07:8C:AC:F8 | Private | 2.4 GHz | 500:45:30 | **Unknown device** |
| 192.168.1.222 | D4:AD:FC:93:52:9C | Shenzhen Intellirocks Tech. | 2.4 GHz | 08:04:58 | Govee LED strip 01 |

### Offline Clients (55 registered, all static IP reservations)

Key offline devices (identified by manufacturer):

| MAC | Manufacturer | Notes |
|-----|-------------|-------|
| 48:E1:E9:6A:DA:F9 | Chengdu Meross Technology | Second Meross device (offline) |
| 0C:9D:92:84:6E:6A | ASUS | node3090 |
| A0:AD:9F:84:D5:BF | (Unknown) | Likely node5090 / 1BL15 |
| F8:B9:5A:EC:E1:D0 | LG Innotek | LG OLED55CX |
| B8:13:32:8E:07:AA | AMPAK Technology | Bambu Lab X1 Carbon |
| 10:7C:61:EB:02:30 | (Unknown) | GT-BE19000 itself |
| A8:8F:D9:E5:4D:5A | Apple Inc. | Apple device |
| 10:96:93:37:17:A5 | Amazon Technologies Inc. | Amazon device |

Full list of 55 offline clients available in source CSV.

### WiFi Network Summary
| Band | Active Clients | Devices |
|------|---------------|---------|
| **2.4 GHz** | 8 | Roborock, TV plug, JVC plug, Meross Bulb, Govee LED, 3× Private |
| **5 GHz** | 4 | Samsung TV, 3× Unknown |
| **6 GHz** | 1 | 1× Unknown |
| **Wired (through Asus)** | 5 | Hue, pfSense, HA, Pioneer, LUCIFER |

### Key Findings
1. **Meross Smart Bulb (48:E1:E9:6A:F3:4B) is on main 2.4 GHz WiFi, NOT Y_IoT** — IP 192.168.1.45, recently reconnected (15 min access time). Note: pfSense static mapping says .16, but live DHCP assignment is .45 — the .16 entry may be stale.
2. **Y_IoT SSID has zero connected clients** — Meross is on the primary WiFi SSID.
3. **All clients have "Allow Internet access"** — no client-level internet restrictions configured on the Asus.
4. **8 unidentified active devices** — 3 Private, 5 unknown manufacturer. The D0:C9:07 MAC prefix appears 3 times (likely same vendor, different devices).
5. **55 offline static reservations** — many registered but not currently connected.

## OPT1 (192.168.5.x) DHCP Static Mappings
| IP | Hostname | MAC | Description |
|----|----------|-----|-------------|
| 192.168.5.2 | netgear | 94:18:65:7b:e8:27 | Netgear GS308E Switch |
| 192.168.5.3 | teltonika | 00:1e:42:61:75:c0 | Teltonika RUTX50 |
| 192.168.5.6 | x1Carbon | b8:13:32:8e:07:aa | Bambu Lab X1 Carbon on wifi network "Z" |
| 192.168.5.41 | node3090 | 0c:9d:92:84:6e:6a | NODE3 / node3090 (Ubuntu 22.04, 9900K, 32GB, 3090 24GB) |
| 192.168.5.44 | n45 | 00:08:9b:cd:1c:43 | QNAP TS-419P II |
| 192.168.5.45 | n45 | 00:08:9b:cd:1c:42 | QNAP TS-419P II |
| 192.168.5.55 | mercedes | 64:e2:20:1f:d4:80 | Mercedes Benz C Class W206 |
| 192.168.5.75 | ipad | da:41:bd:bd:d4:34 | iPad Pro 12.9" |
| 192.168.5.88 | roofTop | 10:2c:b1:13:8d:22 | eufy security camera |
| 192.168.5.95 | x1plug | d8:44:89:4b:f0:76 | Smart Plug (X1 Carbon printer) |
| 192.168.5.100 | goechargerhouse | c4:5b:be:81:33:c4 | go-eCharger_061592-HOUSE |
| 192.168.5.101 | goechargershed | e0:e2:e6:7e:a0:64 | go-eCharger_061519-SHED |
| 192.168.5.155 | developer | c8:60:00:02:13:ed | 1080Ti dev machine |
| 192.168.5.205 | hp | 84:2a:fd:a5:46:e9 | HP Laserjet M118 |

## OPT2 (192.168.10.x) DHCP Static Mappings
| IP | Hostname | MAC | Description |
|----|----------|-----|-------------|
| 192.168.10.2 | ksem | 00:d0:93:55:33:43 | Kostal Smart Energy Meter KSEM-75321957 |
| 192.168.10.3 | helios | a4:06:e9:25:ae:3a | Kostal Solar Power Inverter |

## pfSense Interface Summary
| Interface | Description | IP | Notes |
|-----------|-------------|----|-------|
| WAN (pppoe1) | WAN | PPPoE | Internet uplink |
| LAN (igc1) | LAN | 192.168.1.50/24 | Main LAN, spoofmac de:ad:be:ef:55:5a |
| OPT4 (igc2) | Studio | 192.168.5.1/24 | OPT1 equivalent |
| OPT2 (igc3) | Solar_Inverter | 192.168.10.1/24 | Solar inverter network |
| OPT6 (igc1.55) | IoT (VLAN 55) | 192.168.55.1/24 | **Disabled** — IoT VLAN, pre-configured but inactive |
| OPT3 (run0_wlan0) | WLAN | 10.0.0.1/24 | **Disabled** |
| OPT8 (igc0) | WANPHY | (none) | Physical WAN pass-through |

## Notes
- Bambu Lab X1 Carbon has the same MAC (b8:13:32:8e:07:aa) on both networks — same printer, two wifi SSIDs (X and Z), two static mappings
- PiHole (sy5berry, 192.168.1.5) temporarily retired; DNS handled directly by pfSense resolver
- LUCIFER pending add to SY5L4N workgroup (requires reboot)
- node5090 reverse DNS shows 1BL15 (Windows hostname) — cosmetic, forward DNS correct
- Meross smart bulb IP conflict: pfSense static mapping says .16, live Asus assignment is .45 (2026-06-08)
- IoT VLAN (VLAN 55 on igc1) exists but is disabled — firewall rules pre-configured but mostly disabled
