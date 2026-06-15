// Protocol.swift — FROZEN. The Swift mirror of Gate 2's protocol.ts (g2.1) + Gate 3's plugin
// surface. This is the contract the iOS app INHERITS: it decodes exactly what the Gate 2/3
// server emits and encodes exactly what the server accepts. Keep in lockstep with protocol.ts.
import Foundation

public let PROTOCOL_VERSION = "g2.1"

// ── Canonical message schema (mirrors schema.ts) ──────────────────────────────
public enum AuthorKind: String, Codable { case human, model }
public enum Role: String, Codable { case user, assistant, system }

public struct Author: Codable, Hashable {
    public var id: String
    public var kind: AuthorKind
    public var name: String?
    public var handle: String?
    public init(id: String, kind: AuthorKind, name: String? = nil, handle: String? = nil) {
        self.id = id; self.kind = kind; self.name = name; self.handle = handle
    }
}

public struct Message: Codable, Identifiable, Hashable {
    public var id: String
    public var room: String
    public var author: Author
    public var role: Role
    public var content: String
    public var ts: Double   // epoch ms (JSON number)
    public init(id: String, room: String, author: Author, role: Role, content: String, ts: Double) {
        self.id = id; self.room = room; self.author = author; self.role = role; self.content = content; self.ts = ts
    }
    public var date: Date { Date(timeIntervalSince1970: ts / 1000.0) }
}

// ── Entities ──────────────────────────────────────────────────────────────────
public struct Account: Codable, Identifiable, Hashable {
    public var id: String; public var handle: String; public var kind: AuthorKind; public var createdAt: Double?
}
public struct Room: Codable, Identifiable, Hashable {
    public var id: String; public var name: String; public var createdAt: Double?
}
public struct Membership: Codable, Hashable { public var roomId: String; public var accountId: String; public var joinedAt: Double? }

// ── REST DTOs ─────────────────────────────────────────────────────────────────
public struct AuthRequest: Codable { public var handle: String; public var password: String
    public init(handle: String, password: String){ self.handle = handle; self.password = password } }
public struct AuthResult: Codable { public var accountId: String; public var handle: String; public var token: String }
public struct CreateRoomReq: Codable { public var name: String; public init(name: String){ self.name = name } }
public struct AddAgentReq: Codable {
    public var handle: String; public var endpoint: String; public var model: String?; public var persona: String?
    public init(handle: String, endpoint: String, model: String? = nil, persona: String? = nil){
        self.handle = handle; self.endpoint = endpoint; self.model = model; self.persona = persona }
}
public struct SendReq: Codable { public var content: String; public init(content: String){ self.content = content } }
public struct APIError: Codable, Error { public var error: String; public var code: Int }

// ── WebSocket frames (ws://host/ws?token=…) ───────────────────────────────────
// Client -> server
public enum ClientFrame: Encodable {
    case subscribe(roomId: String)
    case send(roomId: String, content: String)
    case ping
    public func encode(to enc: Encoder) throws {
        var c = enc.container(keyedBy: K.self)
        switch self {
        case .subscribe(let r): try c.encode("subscribe", forKey: .type); try c.encode(r, forKey: .roomId)
        case .send(let r, let content): try c.encode("send", forKey: .type); try c.encode(r, forKey: .roomId); try c.encode(content, forKey: .content)
        case .ping: try c.encode("ping", forKey: .type)
        }
    }
    enum K: String, CodingKey { case type, roomId, content }
}
// Server -> client
public enum ServerFrame: Decodable {
    case message(Message)
    case ack(ref: String)
    case presence(roomId: String, accountId: String, online: Bool)
    case error(error: String, code: Int)
    case pong
    case unknown(String)
    enum K: String, CodingKey { case type, message, ref, roomId, accountId, online, error, code }
    public init(from dec: Decoder) throws {
        let c = try dec.container(keyedBy: K.self)
        switch try c.decode(String.self, forKey: .type) {
        case "message": self = .message(try c.decode(Message.self, forKey: .message))
        case "ack": self = .ack(ref: (try? c.decode(String.self, forKey: .ref)) ?? "")
        case "presence": self = .presence(roomId: try c.decode(String.self, forKey: .roomId),
                                          accountId: try c.decode(String.self, forKey: .accountId),
                                          online: (try? c.decode(Bool.self, forKey: .online)) ?? false)
        case "error": self = .error(error: try c.decode(String.self, forKey: .error), code: (try? c.decode(Int.self, forKey: .code)) ?? 0)
        case "pong": self = .pong
        case let t: self = .unknown(t)
        }
    }
}

// ── Endpoint helpers (the inherited REST/WS surface) ──────────────────────────
public enum API {
    public static func rest(_ base: String, _ path: String) -> URL { URL(string: base.hasSuffix("/") ? base + String(path.dropFirst()) : base + path)! }
    public static func ws(_ base: String, token: String) -> URL {
        let wsBase = base.replacingOccurrences(of: "http", with: "ws")
        return URL(string: wsBase + "/ws?token=" + (token.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? token))!
    }
    public static let register = "/auth/register", login = "/auth/login", rooms = "/rooms"
    public static func roomMessages(_ id: String) -> String { "/rooms/\(id)/messages" }
    public static func roomJoin(_ id: String) -> String { "/rooms/\(id)/join" }
    public static func roomAgents(_ id: String) -> String { "/rooms/\(id)/agents" }
}
