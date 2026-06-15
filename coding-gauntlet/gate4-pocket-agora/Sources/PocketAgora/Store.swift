// Store.swift — AGENT IMPLEMENTS. Observable app state wiring Transport into the UI: login,
// room list, the selected room's messages (deduped by id), send, and live WS frames appended in
// order. SwiftUI-free (ObservableObject) so logic is unit-testable; the views observe it.
import Foundation
#if canImport(Combine)
import Combine

@MainActor
public final class ChatStore: ObservableObject {
    @Published public var account: AuthResult?
    @Published public var rooms: [Room] = []
    @Published public var current: Room?
    @Published public var messages: [Message] = []
    @Published public var status: String = "not connected"

    private let transport: Transport
    public init(transport: Transport) { self.transport = transport }

    public func authenticate(register: Bool, handle: String, password: String) async {
        fatalError("NOT IMPLEMENTED: ChatStore.authenticate — call transport, store token, connect WS, load rooms")
    }
    public func open(_ room: Room) async { fatalError("NOT IMPLEMENTED: ChatStore.open — load history, subscribe") }
    public func send(_ text: String) { fatalError("NOT IMPLEMENTED: ChatStore.send") }
    public func addAgent(handle: String, endpoint: String) async { fatalError("NOT IMPLEMENTED: ChatStore.addAgent") }
    /// Append a frame's message in order, deduped by id (called from the WS handler).
    public func ingest(_ frame: ServerFrame) { fatalError("NOT IMPLEMENTED: ChatStore.ingest") }
}
#endif
