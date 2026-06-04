// swift-tools-version: 5.10
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
