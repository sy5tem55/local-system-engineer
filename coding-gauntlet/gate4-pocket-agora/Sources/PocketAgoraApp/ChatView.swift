// ChatView.swift — AGENT IMPLEMENTS the SwiftUI views (opencode aesthetic, monospace, OC.background
// ground, OC.primary own-messages, OC.accent agent names, OC.secondary mentions). Group chat:
// room list, message thread rendering markdown + syntax-highlighted code via the OC palette, a
// composer, and an "add model agent" action. Mirrors the web client; consumes ChatStore.
#if canImport(SwiftUI)
import SwiftUI
import PocketAgora

struct ChatView: View {
    @EnvironmentObject var store: ChatStore
    var body: some View {
        // TODO(agent): rooms sidebar (iPad: split view; iPhone: navigation), message thread,
        // composer, login sheet, add-agent action. Render messages via MessageView below.
        Text("Pocket Agora — implement ChatView (see SPEC §UI)")
            .font(OC.mono).foregroundColor(OC.muted)
            .frame(maxWidth: .infinity, maxHeight: .infinity).background(OC.background)
    }
}

struct MessageView: View {
    let message: Message
    let myId: String
    var body: some View {
        // TODO(agent): author line (OC.primary if mine / OC.accent if model) + opencode-rendered
        // body (markdown, fenced code with syntax colors, @mentions in OC.secondary).
        VStack(alignment: .leading, spacing: 2) {
            Text(message.author.name ?? message.author.handle ?? message.author.id)
                .font(.system(.caption, design: .monospaced))
                .foregroundColor(message.author.kind == .model ? OC.accent : (message.author.id == myId ? OC.primary : OC.muted))
            Text(message.content).font(OC.mono).foregroundColor(OC.text)
        }
    }
}
#endif
