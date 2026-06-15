// Tokens.swift — FROZEN opencode palette (mirrors design-tokens/opencode-tokens.json), the same
// look from terminal (Gate 1) to web (Gate 2/3) to iOS (here). Monospace everywhere.
#if canImport(SwiftUI)
import SwiftUI

public enum OC {
    public static let background = Color(hex: 0x0a0a0a)
    public static let panel      = Color(hex: 0x141414)
    public static let element    = Color(hex: 0x1c1c1c)
    public static let primary    = Color(hex: 0xfab283) // amber — own messages, cursor, primary
    public static let accent     = Color(hex: 0x9d7cd8) // purple — headings, agent names, keywords
    public static let secondary  = Color(hex: 0x5c9cf5) // blue — mentions, selection
    public static let text       = Color(hex: 0xe0e0e0)
    public static let muted      = Color(hex: 0x808080)
    public static let border     = Color(hex: 0x2a2a2a)
    public static let success    = Color(hex: 0x7fd88f)
    public static let error      = Color(hex: 0xe06c75)
    // syntax
    public static let synComment = muted, synKeyword = accent, synFunction = secondary
    public static let synString  = success, synNumber = primary, synType = secondary
    public static let mono = Font.system(.body, design: .monospaced)
}

public extension Color {
    init(hex: UInt32) {
        self.init(.sRGB, red: Double((hex >> 16) & 0xff)/255, green: Double((hex >> 8) & 0xff)/255,
                  blue: Double(hex & 0xff)/255, opacity: 1)
    }
}
#endif
