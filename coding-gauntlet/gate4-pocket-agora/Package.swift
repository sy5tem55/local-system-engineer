// swift-tools-version:5.9
import PackageDescription

// The PocketAgora LIBRARY (contract + transport + store) builds and unit-tests cross-platform
// with `swift test` — that's the verifiable Gate 4 acceptance. The SwiftUI APP lives in
// Sources/PocketAgoraApp and is added to an Xcode iOS App target (see README) for iPhone/iPad.
let package = Package(
    name: "PocketAgora",
    platforms: [.iOS(.v16), .macOS(.v13)],
    products: [ .library(name: "PocketAgora", targets: ["PocketAgora"]) ],
    targets: [
        .target(name: "PocketAgora"),
        .testTarget(name: "PocketAgoraTests", dependencies: ["PocketAgora"]),
    ]
)
