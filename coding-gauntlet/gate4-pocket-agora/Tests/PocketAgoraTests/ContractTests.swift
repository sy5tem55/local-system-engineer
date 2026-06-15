// ContractTests.swift — Gate 4 acceptance (the verifiable part). Proves the inherited Swift
// contract decodes EXACTLY what the Gate 2/3 server emits and encodes what it accepts. Runs with
// `swift test` (macOS) or in Xcode — this is the iOS analogue of the node:test harnesses.
import XCTest
@testable import PocketAgora

final class ContractTests: XCTestCase {
    // A server `message` frame, byte-shaped like the Node server's WS output.
    func testDecodeServerMessageFrame() throws {
        let json = """
        {"type":"message","message":{"id":"m1","room":"r1","author":{"id":"m:qwen","kind":"model","name":"qwen"},"role":"assistant","content":"hi **there**","ts":1700000000000}}
        """.data(using: .utf8)!
        let frame = try JSONDecoder().decode(ServerFrame.self, from: json)
        guard case let .message(m) = frame else { return XCTFail("expected .message") }
        XCTAssertEqual(m.id, "m1")
        XCTAssertEqual(m.author.kind, .model)
        XCTAssertEqual(m.role, .assistant)
        XCTAssertEqual(m.content, "hi **there**")
        XCTAssertEqual(m.ts, 1700000000000)
    }

    func testDecodeErrorFrame() throws {
        let json = #"{"type":"error","error":"not a member","code":403}"#.data(using: .utf8)!
        guard case let .error(e, c) = try JSONDecoder().decode(ServerFrame.self, from: json) else { return XCTFail() }
        XCTAssertEqual(e, "not a member"); XCTAssertEqual(c, 403)
    }

    func testEncodeClientSendFrame() throws {
        let data = try JSONEncoder().encode(ClientFrame.send(roomId: "r1", content: "@qwen hi"))
        let obj = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        XCTAssertEqual(obj["type"] as? String, "send")
        XCTAssertEqual(obj["roomId"] as? String, "r1")
        XCTAssertEqual(obj["content"] as? String, "@qwen hi")
    }

    func testAuthResultDecodes() throws {
        let json = #"{"accountId":"u:joe","handle":"joe","token":"abc.def"}"#.data(using: .utf8)!
        let r = try JSONDecoder().decode(AuthResult.self, from: json)
        XCTAssertEqual(r.accountId, "u:joe"); XCTAssertEqual(r.token, "abc.def")
    }

    func testEndpointConstruction() {
        XCTAssertEqual(API.ws("http://h:55", token: "t k").absoluteString, "ws://h:55/ws?token=t%20k")
        XCTAssertEqual(API.roomAgents("r1"), "/rooms/r1/agents")
    }
}
