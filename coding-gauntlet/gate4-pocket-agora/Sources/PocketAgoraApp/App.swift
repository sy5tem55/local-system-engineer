// App.swift — AGENT IMPLEMENTS the @main entry. Add this file to an Xcode iOS App target that
// depends on the PocketAgora library. Builds for iPhone + iPad.
#if canImport(SwiftUI)
import SwiftUI
import PocketAgora

@main
struct PocketAgoraApp: App {
    @StateObject private var store = ChatStore(transport: URLSessionTransport(base: "http://node4090.home.arpa:55"))
    var body: some Scene {
        WindowGroup { ChatView().environmentObject(store) }
    }
}
#endif
