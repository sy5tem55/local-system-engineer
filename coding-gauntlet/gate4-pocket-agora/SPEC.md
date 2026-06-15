# Gate 4 — The Pocket Agora (challenge spec — the pinnacle)

> Native **iOS (SwiftUI)** chat app for iPhone + iPad: human accounts + local-model agent accounts
> in **group chats**, the plugin framework, and the **exact opencode aesthetic**, talking to the
> Gate 2/3 backend. Every lower gate converges here — transport (G1) · backend + accounts + realtime
> + multi-agent (G2) · plugin framework + design system (G3) → native platform.

## What it inherits (frozen, authored)

- **`Protocol.swift`** — the Swift Codable mirror of Gate 2's `protocol.ts` (g2.1): `Message`,
  `Author`, `Account`, `Room`, the `ClientFrame`/`ServerFrame` WS envelopes, the REST DTOs, and the
  `API` endpoint helpers. The app decodes **exactly** what the server emits and encodes what it
  accepts. This is the contract — keep it in lockstep with `protocol.ts`.
- **`Tokens.swift`** — the opencode palette as SwiftUI `Color`s (same `#0a0a0a / #fab283 / #9d7cd8 /
  #5c9cf5`, monospace), so the look is identical from terminal → web → iOS.
- **`Tests/PocketAgoraTests/ContractTests.swift`** — the acceptance grader (below).

## What you build

| File | Contract |
|---|---|
| `Sources/PocketAgora/Transport.swift` | `URLSessionTransport`: REST (register/login/rooms/join/messages/agents) + a `URLSessionWebSocketTask` to `API.ws(base, token:)`; decode `ServerFrame`s to the handler, encode `ClientFrame`s. Foundation-only (unit-testable). |
| `Sources/PocketAgora/Store.swift` | `ChatStore` (`ObservableObject`): login → connect WS → load rooms; open a room (history + subscribe); send; `ingest` frames (append in order, dedupe by id). |
| `Sources/PocketAgoraApp/App.swift` | `@main` app; `WindowGroup { ChatView() }`. |
| `Sources/PocketAgoraApp/ChatView.swift` | The SwiftUI views (opencode aesthetic): rooms (iPad split / iPhone navigation), the message thread rendering markdown + syntax-highlighted code + `@mentions`, a composer, an "add model agent" action, plugin results in-thread. |

## Acceptance — two tiers

**Tier 1 — verifiable (XCTest, runs in Xcode or `swift test`):** `ContractTests.swift` proves the
inherited contract speaks the server's exact wire format:
- decode a server `message` frame → `Message` with correct fields;
- decode an `error` frame; decode `AuthResult`;
- encode `ClientFrame.send` → `{type,roomId,content}`;
- endpoint construction (`API.ws`, room paths).

If these pass, the app and the Gate 2/3 server agree on the wire — the single most failure-prone
seam. **Run these first.**

**Tier 2 — on-device (manual, eye-graded checklist):** the part no automated grader here can judge.
- Builds and launches on **iPhone and iPad** (simulator or device).
- Login (or register) against the running Gate 2/3 server; rooms list and create/join.
- `@mention` a local-model agent → its reply appears in-thread (real model via the Gate 2 server).
- A second human (another device/simulator) sees messages in the same room (realtime fan-out).
- The **opencode aesthetic** matches: `#0a0a0a` ground, amber own-messages, purple agent names,
  blue mentions, monospace, syntax-colored code.
- A Gate 3 plugin result (e.g. `/search`) renders in-thread.

## Honest verification boundary

This is the gate where the Cowork verification loop **stops reaching**: there is no Swift toolchain
in the sandbox, and SwiftUI/iOS builds need **Xcode on a Mac**. So the authored Swift here is
verified by careful authorship + the contract XCTests, **not** by a sandbox run. Run `swift test`
(or Xcode's test action) as the first gate; the on-device behavior is human-verified against the
checklist. Treat Tier-1 green + the Tier-2 checklist as "passed."

## Run

See `README.md`: open in Xcode, add `App.swift` + `ChatView.swift` to an iOS App target that depends
on the `PocketAgora` package, set the server URL (`http://<host>:55`), build to iPhone/iPad. Run the
Gate 2/3 server first (`npm start`); the app is its native client.

## The convergence

G1 gave streaming transport + the schema + the tokens; G2 the backend, accounts, realtime, and
multi-agent orchestration; G3 the plugin framework + the finished design system. Gate 4 is all of it
on the native platform — the chat fabric in your pocket.
