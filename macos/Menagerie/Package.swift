// swift-tools-version: 5.10
// SPDX-License-Identifier: AGPL-3.0-only
import PackageDescription

let package = Package(
    name: "Menagerie",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "Menagerie", targets: ["Menagerie"])
    ],
    targets: [
        .executableTarget(
            name: "Menagerie",
            path: "Menagerie"
        )
    ]
)
