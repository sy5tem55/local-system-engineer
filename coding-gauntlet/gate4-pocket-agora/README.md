# Gate 4 — The Pocket Agora (native iOS)

The pinnacle: a SwiftUI iPhone/iPad client for the chat fabric, talking to the Gate 2/3 backend in
the **exact opencode aesthetic**. Full contract in [`SPEC.md`](./SPEC.md).

## Layout

```
Sources/PocketAgora/Protocol.swift   FROZEN — Swift mirror of Gate 2 protocol.ts (the inherited contract)
Sources/PocketAgora/Tokens.swift     FROZEN — opencode palette as SwiftUI Colors
Sources/PocketAgora/Transport.swift  agent — URLSession REST + WebSocket
Sources/PocketAgora/Store.swift      agent — ChatStore (ObservableObject)
Sources/PocketAgoraApp/App.swift     agent — @main app (Xcode iOS App target)
Sources/PocketAgoraApp/ChatView.swift agent — SwiftUI views (opencode aesthetic)
Tests/PocketAgoraTests/ContractTests.swift  the grader (wire-format acceptance)
```

## Verify the contract (Tier 1) — no device needed

On a Mac with the Swift toolchain:

```bash
swift test          # runs ContractTests — proves the app speaks the server's exact wire format
```

(The `PocketAgora` library + tests are Foundation-only and build cross-platform; `Tokens.swift` and
the App sources are guarded by `#if canImport(SwiftUI)` and only compile under Xcode.)

## Build to iPhone / iPad (Tier 2)

1. **Xcode → New → iOS App** (SwiftUI lifecycle), name it `PocketAgora`.
2. Add this folder as a **local Swift Package** (File → Add Package Dependencies → Add Local), or
   drag `Sources/PocketAgora/*.swift` into the app target.
3. Add `Sources/PocketAgoraApp/App.swift` + `ChatView.swift` to the app target (remove Xcode's
   generated `@main` so there's only one).
4. Set the server URL in `App.swift` (`URLSessionTransport(base: "http://<host>:55")`). For a device
   on Wi-Fi, use the LAN host (e.g. `http://node4090.home.arpa:55`); allow the local HTTP host in
   `Info.plist` App Transport Security if not using TLS.
5. Run the **Gate 2/3 server** first (`npm start`), then build to a simulator or device.

## Note

There is no Swift toolchain in the Cowork sandbox, and iOS builds require Xcode/macOS — so this
scaffold is authored, not sandbox-verified. `swift test` (Tier 1) is the automated gate; the device
behavior is the manual checklist in SPEC §Acceptance. Tokens consumed conceptually from
`../design-tokens/opencode-tokens.json` (mirrored in `Tokens.swift`).
