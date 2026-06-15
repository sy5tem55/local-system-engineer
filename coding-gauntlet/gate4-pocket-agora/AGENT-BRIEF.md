# Gate 4 — Build Brief

Unlike Gates 1–3, this gate's toolchain is **Swift + Xcode on a Mac**, not the LSE agent's WSL2/Node
environment — the local agent can't build iOS. So Gate 4 is built by Joe (it's the pinnacle, yours)
or a Swift-capable coding agent. The discipline is the same: make the contract tests pass, then the
on-device checklist.

TASK: Implement the Pocket Agora — a SwiftUI iPhone/iPad client for the Gate 2/3 chat fabric.

INHERITED / FROZEN — do not edit: `Sources/PocketAgora/Protocol.swift` (the wire contract, mirrors
`protocol.ts`), `Tokens.swift` (opencode palette), `Tests/PocketAgoraTests/ContractTests.swift`.

IMPLEMENT (stubs `fatalError`):
1. `Transport.swift` — `URLSessionTransport`: the REST calls (register/login/rooms/join/messages/
   agents) and a `URLSessionWebSocketTask` to `API.ws(base, token:)`; decode `ServerFrame`s to the
   handler, encode `ClientFrame`s. Foundation-only.
2. `Store.swift` — `ChatStore`: login → connect → load rooms; open room (history + subscribe); send;
   `ingest` (append in order, dedupe by id).
3. `App.swift` / `ChatView.swift` — the SwiftUI views in the opencode aesthetic (rooms; message
   thread rendering markdown + syntax-colored code + `@mentions`; composer; add-agent; plugin
   results in-thread). iPad split view / iPhone navigation.

DONE:
- Tier 1: `swift test` green (ContractTests — the wire-format grader). Run this first.
- Tier 2 (on device): builds + launches on iPhone AND iPad; login against the running Gate 2/3
  server; `@mention` a local model → reply in-thread; second device sees the message (fan-out);
  opencode aesthetic matches; a `/search` plugin result renders.

NOTE: no Swift toolchain in Cowork — verification is `swift test` + the device checklist, in Xcode.
Run the Gate 2/3 server (`npm start`) first; this app is its native client. Keep `Protocol.swift` in
lockstep with `protocol.ts` — if the server's wire format changes, both move together.
