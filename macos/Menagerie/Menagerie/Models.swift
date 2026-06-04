import Foundation
import SwiftUI

enum SessionRuntimeState: String, Codable {
    case idle
    case starting
    case thinking
    case runningTool
    case waitingForPermission
    case compacting
    case readyForReview
    case error

    var tint: Color {
        switch self {
        case .idle: return .gray
        case .starting: return .teal
        case .thinking: return .blue
        case .runningTool: return .orange
        case .waitingForPermission: return .red
        case .compacting: return .purple
        case .readyForReview: return .green
        case .error: return .pink
        }
    }
}

struct SessionEvent: Codable, Identifiable {
    let id: String
    let ts: String
    let source: String
    let kind: String
    let severity: String?
    let workspaceId: String
    let sessionId: String
    let turnId: String?
    let cwdHash: String?
    let model: String?
    let state: SessionRuntimeState?
    let summary: String
}

struct SessionStateDocument: Codable {
    let id: String
    let ts: String
    let source: String
    let workspaceId: String
    let sessionId: String
    let turnId: String?
    let state: SessionRuntimeState
    let severity: String?
    let summary: String
    let lastEventKind: String?
}

struct MenagerieSettings: Codable, Equatable {
    var host: String = "localhost"
    var port: UInt16 = 1883
    var username: String = "menagerie-app"
    var workspaceId: String = "#"
    var useTLS: Bool = false
    var insecureTLS: Bool = false
    var showGremlin: Bool = true
    var verboseLocalDetails: Bool = false
    var windowX: Double = 120
    var windowY: Double = 120

    static let defaultsKey = "Menagerie.Settings.v1"

    static func load() -> MenagerieSettings {
        guard let data = UserDefaults.standard.data(forKey: defaultsKey),
              let decoded = try? JSONDecoder().decode(MenagerieSettings.self, from: data) else {
            return MenagerieSettings()
        }
        return decoded
    }

    func save() {
        if let data = try? JSONEncoder().encode(self) {
            UserDefaults.standard.set(data, forKey: MenagerieSettings.defaultsKey)
        }
    }
}

@MainActor
final class MenagerieModel: ObservableObject {
    @Published var settings: MenagerieSettings = .load()
    @Published var runtimeState: SessionRuntimeState = .idle
    @Published var summary: String = "Waiting for a gremlin"
    @Published var connected: Bool = false
    @Published var recentEvents: [SessionEvent] = []

    func apply(event: SessionEvent) {
        if let state = event.state {
            runtimeState = state
        }
        summary = event.summary
        recentEvents.insert(event, at: 0)
        recentEvents = Array(recentEvents.prefix(20))
    }

    func apply(state: SessionStateDocument) {
        runtimeState = state.state
        summary = state.summary
    }

    func saveSettings() {
        settings.save()
    }
}
