# SY5 Home Network Map

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

## Notes
- Bambu Lab X1 Carbon has the same MAC (b8:13:32:8e:07:aa) on both networks — same printer, two wifi SSIDs (X and Z), two static mappings
- PiHole (sy5berry, 192.168.1.5) temporarily retired; DNS handled directly by pfSense resolver
- LUCIFER pending add to SY5L4N workgroup (requires reboot)
- node5090 reverse DNS shows 1BL15 (Windows hostname) — cosmetic, forward DNS correct
