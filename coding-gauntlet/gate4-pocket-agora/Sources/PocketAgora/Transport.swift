// Transport.swift — AGENT IMPLEMENTS. REST (URLSession) + WebSocket (URLSessionWebSocketTask)
// against the inherited contract. Foundation-only so it builds + unit-tests cross-platform.
import Foundation

public protocol Transport {
    func register(handle: String, password: String) async throws -> AuthResult
    func login(handle: String, password: String) async throws -> AuthResult
    func rooms() async throws -> [Room]
    func createRoom(name: String) async throws -> Room
    func join(roomId: String) async throws
    func messages(roomId: String) async throws -> [Message]
    func addAgent(roomId: String, _ req: AddAgentReq) async throws -> Account
    // WS: connect, then receive frames via the handler; subscribe/send over the socket.
    func connect(token: String, onFrame: @escaping (ServerFrame) -> Void) throws
    func subscribe(roomId: String)
    func send(roomId: String, content: String)
    func close()
}

/// AGENT IMPLEMENTS: a concrete Transport over `base` (e.g. http://node4090.home.arpa:55).
public final class URLSessionTransport: Transport {
    public let base: String
    public private(set) var token: String?
    public init(base: String) { self.base = base }

    public func register(handle: String, password: String) async throws -> AuthResult {
        fatalError("NOT IMPLEMENTED: register — POST \(API.register) (see SPEC §Transport)")
    }
    public func login(handle: String, password: String) async throws -> AuthResult {
        fatalError("NOT IMPLEMENTED: login — POST \(API.login)")
    }
    public func rooms() async throws -> [Room] { fatalError("NOT IMPLEMENTED: GET \(API.rooms)") }
    public func createRoom(name: String) async throws -> Room { fatalError("NOT IMPLEMENTED: POST \(API.rooms)") }
    public func join(roomId: String) async throws { fatalError("NOT IMPLEMENTED: POST \(API.roomJoin(roomId))") }
    public func messages(roomId: String) async throws -> [Message] { fatalError("NOT IMPLEMENTED: GET \(API.roomMessages(roomId))") }
    public func addAgent(roomId: String, _ req: AddAgentReq) async throws -> Account { fatalError("NOT IMPLEMENTED: POST \(API.roomAgents(roomId))") }
    public func connect(token: String, onFrame: @escaping (ServerFrame) -> Void) throws { fatalError("NOT IMPLEMENTED: open URLSessionWebSocketTask to API.ws(base, token:)") }
    public func subscribe(roomId: String) { fatalError("NOT IMPLEMENTED: send ClientFrame.subscribe") }
    public func send(roomId: String, content: String) { fatalError("NOT IMPLEMENTED: send ClientFrame.send") }
    public func close() {}
}
