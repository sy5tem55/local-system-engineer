# Shodan API Facts — verified against official docs (2026-09-28)

Sources: https://developer.shodan.io/api (REST reference, fetched 2026-09-28),
https://developer.shodan.io/api/requirements, https://developer.shodan.io/api/introduction.
Key claims re-checked with verify_source_claims (all FOUND) on 2026-09-28.

## Base URL & auth
- Base URL for all REST methods: `https://api.shodan.io`
- Auth: query param `key={YOUR_API_KEY}` on every endpoint, e.g.
  `https://api.shodan.io/shodan/host/8.8.8.8?key={YOUR_API_KEY}`
- API key is free: "To use the API you need to have an API key, which you can get
  for free by creating a Shodan account" (/api/requirements).

## REST endpoints documented on the reference page
- `GET /shodan/host/search` — search with the website's query syntax + facets
- `GET /shodan/host/count` — same query, no results; returns total + facets
- `GET /shodan/host/{ip}` — all services (banners) found on a host
- Also listed: `/shodan/host/search/facets`, `/shodan/host/search/filters`,
  `/shodan/host/search/tokens`, `/shodan/ports`, `/shodan/protocols`,
  `/shodan/query/search`, `/shodan/query/tags`, `/shodan/scan`,
  `/shodan/scan/{id}`, `/shodan/scans`, `/shodan/scan/internet`,
  `/shodan/collection/`, `/shodan/data`, `/shodan/data/raw`, `/shodan/data/{dataset}`,
  `/shodan/alert...`
- NOTE: `GET /shodan/info` (account/quota lookup) is NOT present in the current
  REST reference (verified against the full path list). Do not assume a quota
  endpoint; credit balance is only visible in account.shodan.io.

## GET /shodan/host/search parameters (verbatim from docs)
- `query`: [String] Shodan search query; "filter:value" syntax inside the query,
  e.g. `apache country:DE`.
- `facets` (optional): [String] comma-separated properties for summary info;
  `property:count` form allowed (e.g. `country:100`).
- `page` (optional): [Integer] "The page number to page through results
  100 at a time (default: 1)" — i.e. 100 matches/page.
- `minify` (optional): [Boolean] "whether or not to truncate some of the larger
  fields (default: True)".
- `fields` (optional): [String] "Comma-separated list of fields to return in the
  search results. Example: tags,http.title,http.favicon.hash"

## Credit rules (verbatim)
"This method may use API query credits depending on usage. If any of the
following criteria are met, your account will be deducted 1 query credit:
The search query contains a filter. Accessing results past the 1st page using
the 'page'. For every 100 results past the 1st page 1 query credit is deducted."
- `/shodan/host/count`: "this method does not consume query credits."

## Response shape (from documented example responses)
Top level: `matches[]` (host matches), `facets{}`, `total` (int).

Each match in `matches[]` is a (ip, port, banner) triple — one service, not a
whole host. Fields observed in the documented examples:
- `ip` (int), `ip_str` (string)
- `port` (int), `transport` ("tcp"/"udp")
- `product` (string|null), `version` (string), `os` (string|null)
- `hostnames` (array of str), `domains` (array of str)
- `location` { `city`, `region_code`, `area_code`, `longitude`, `latitude`,
  `postal_code`, `dma_code`, `country_code`, `country_name` }
- `org`, `isp`, `asn`, `timestamp`, `data` (raw banner), `hash`,
  `cpe` (array), `http` { `title`, `server`, `html`, `host`, `location`, ... }

## Device-column derivation (design note for shodan_mcp_server.py)
- Search results have NO single "device" field. A host appears multiple times
  (once per service/port banner).
- Planned Device derivation priority: `product` → `http.title` →
  `hostnames[0]` → `os` → `unknown`.
- Per-host open-PORTS list: aggregate matches by `ip_str` in the search response,
  or call `GET /shodan/host/{ip}` (top-level `ports[]` array is only available
  from the host-info endpoint, not from search).

## Rate limits / free tier
- The official pages fetched (/api, /api/requirements, /api/introduction)
  contain NO numeric rate limits and NO free-tier credit quota.
  → UNVERIFIED against official docs; do not assert numbers from memory.
- Design consequence: client-side conservative throttling (small QPS cap,
  back off on HTTP 429), and treat 429/5xx as retryable.

## Client choice
- Docs page examples use the official `shodan` Python package, but it is NOT
  installed in /home/sy5/miniforge3 (checked 2026-09-28). Plan: plain `httpx`
  (0.28.1 installed) to avoid adding a dependency.
