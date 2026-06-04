// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import SwiftUI

enum SessionRuntimeState: String, Codable {
    case idle
    case dead
    case exited
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
        case .dead: return .black
        case .exited: return .brown
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

struct SessionLifecycle: Codable {
    let schema: String?
    let status: String?
    let lastSeenAt: String?
    let idleAfter: String?
    let deadAfter: String?
    let exitedAfter: String?
    let idleState: String?
    let deadState: String?
    let exitedState: String?
    let inference: String?
    let reason: String?

    func inferredState(reportedState: SessionRuntimeState?, now: Date = Date()) -> SessionRuntimeState {
        if let exitedAt = MenagerieDateParser.date(from: exitedAfter), now >= exitedAt {
            return .exited
        }
        if let deadAt = MenagerieDateParser.date(from: deadAfter), now >= deadAt {
            return .dead
        }
        if let idleAt = MenagerieDateParser.date(from: idleAfter), now >= idleAt {
            return idleDisplayState(reportedState: reportedState)
        }

        switch status {
        case "idle":
            return idleDisplayState(reportedState: reportedState)
        case "dead": return .dead
        case "exited": return .exited
        default: return reportedState ?? .idle
        }
    }

    private func idleDisplayState(reportedState: SessionRuntimeState?) -> SessionRuntimeState {
        switch reportedState {
        case .readyForReview:
            return .readyForReview
        case .waitingForPermission:
            return .waitingForPermission
        default:
            return .idle
        }
    }
}

struct SessionStreamItem: Codable {
    let schema: String?
    let kind: String?
    let role: String?
    let state: SessionRuntimeState?
    let severity: String?
    let tone: String?
    let icon: String?
    let title: String?
    let body: String?
    let subject: String?
    let preview: String?
    let contentRedacted: Bool?

    var displayTitle: String? {
        title ?? subject ?? kind
    }

    var displayBody: String? {
        preview ?? body
    }
}

struct SessionThoughtItem {
    let title: String?
    let body: String
    let isRedacted: Bool
}

struct SessionEventPayload: Codable {
    let promptPreview: String?
    let lastAssistantMessagePreview: String?
    let toolInputPreview: JSONValue?

    var previewText: String? {
        if let promptPreview {
            return promptPreview
        }
        if let lastAssistantMessagePreview {
            return lastAssistantMessagePreview
        }
        if case .object(let values) = toolInputPreview {
            if let command = values["command"]?.stringValue {
                return command
            }
            let keys = values.keys.sorted().joined(separator: ", ")
            return keys.isEmpty ? nil : "Tool input: \(keys)"
        }
        return toolInputPreview?.displayString
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
    let lifecycle: SessionLifecycle?
    let streamItem: SessionStreamItem?
    let payload: SessionEventPayload?
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
    let lastStreamItem: SessionStreamItem?
    let lifecycle: SessionLifecycle?
}

struct SessionHealthDocument: Codable {
    let id: String
    let ts: String
    let source: String
    let schema: String?
    let kind: String?
    let workspaceId: String
    let sessionId: String
    let turnId: String?
    let sessionState: SessionRuntimeState?
    let summary: String?
    let lastEventKind: String?
    let lifecycle: SessionLifecycle?
}

struct SessionProfileDocument: Codable {
    let id: String
    let ts: String
    let source: String
    let schema: String?
    let kind: String
    let workspaceId: String
    let sessionId: String
    let displayName: String?
    let summary: String?

    private enum CodingKeys: String, CodingKey {
        case id
        case ts
        case source
        case schema
        case kind
        case workspaceId
        case sessionId
        case displayName
        case summary
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(ts, forKey: .ts)
        try container.encode(source, forKey: .source)
        try container.encodeIfPresent(schema, forKey: .schema)
        try container.encode(kind, forKey: .kind)
        try container.encode(workspaceId, forKey: .workspaceId)
        try container.encode(sessionId, forKey: .sessionId)
        try container.encode(displayName, forKey: .displayName)
        try container.encodeIfPresent(summary, forKey: .summary)
    }
}

enum JSONValue: Codable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else {
            self = .array(try container.decode([JSONValue].self))
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value): try container.encode(value)
        case .number(let value): try container.encode(value)
        case .bool(let value): try container.encode(value)
        case .object(let value): try container.encode(value)
        case .array(let value): try container.encode(value)
        case .null: try container.encodeNil()
        }
    }

    var stringValue: String? {
        if case .string(let value) = self { return value }
        return nil
    }

    var displayString: String? {
        switch self {
        case .string(let value): return value
        case .number(let value): return String(value)
        case .bool(let value): return value ? "true" : "false"
        case .object(let value):
            let keys = value.keys.sorted().joined(separator: ", ")
            return keys.isEmpty ? nil : "Tool input: \(keys)"
        case .array(let value): return value.isEmpty ? nil : "\(value.count) items"
        case .null: return nil
        }
    }
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
    @Published var sessionId: String?
    @Published var sessionWorkspaceId: String?
    @Published var sessionName: String?
    @Published var currentStreamItem: SessionStreamItem?
    @Published var lifecycle: SessionLifecycle?
    @Published var recentEvents: [SessionEvent] = []

    var lastStateTopic: String?
    var lastEventTopic: String?
    var lastHealthTopic: String?
    var lastProfileTopic: String?

    private var reportedRuntimeState: SessionRuntimeState = .idle

    var sessionDisplayName: String {
        if let sessionName = normalizedSessionName {
            return sessionName
        }
        guard let sessionId, !sessionId.isEmpty else { return "Broker" }
        return "Session \(String(sessionId.prefix(8)))"
    }

    private var normalizedSessionName: String? {
        guard let name = sessionName?.trimmingCharacters(in: .whitespacesAndNewlines), !name.isEmpty else {
            return nil
        }
        return name
    }

    var activityTitle: String? {
        currentStreamItem?.displayTitle
    }

    var displaySummary: String {
        if runtimeState == .error || runtimeState == .starting {
            return summary
        }
        return currentStreamItem?.displayBody ?? summary
    }

    var thoughtItems: [SessionThoughtItem] {
        var items: [SessionThoughtItem] = []
        if let item = thoughtItem(streamItem: currentStreamItem, payload: nil) {
            items.append(item)
        }
        for event in recentEvents {
            guard let item = thoughtItem(streamItem: event.streamItem, payload: event.payload) else { continue }
            if !items.contains(where: { $0.title == item.title && $0.body == item.body }) {
                items.append(item)
            }
            if items.count == 3 { break }
        }
        return items
    }

    var thoughtFallback: String {
        if currentStreamItem?.contentRedacted == true || recentEvents.contains(where: { $0.streamItem?.contentRedacted == true }) {
            return "Text preview redacted"
        }
        return "Waiting for activity text"
    }

    private func thoughtItem(streamItem: SessionStreamItem?, payload: SessionEventPayload?) -> SessionThoughtItem? {
        let preview = payload?.previewText ?? streamItem?.preview
        if let preview, !preview.isEmpty {
            return SessionThoughtItem(title: streamItem?.subject ?? streamItem?.displayTitle, body: preview, isRedacted: false)
        }
        guard streamItem?.contentRedacted == true else { return nil }
        return SessionThoughtItem(title: streamItem?.subject ?? streamItem?.displayTitle, body: "Text preview redacted", isRedacted: true)
    }

    func apply(event: SessionEvent) {
        sessionId = event.sessionId
        sessionWorkspaceId = event.workspaceId
        if let state = event.state ?? event.streamItem?.state {
            reportedRuntimeState = state
        }
        lifecycle = event.lifecycle
        currentStreamItem = event.streamItem
        summary = event.summary
        recentEvents.insert(event, at: 0)
        recentEvents = Array(recentEvents.prefix(20))
        refreshLifecycle()
    }

    func apply(state: SessionStateDocument) {
        sessionId = state.sessionId
        sessionWorkspaceId = state.workspaceId
        reportedRuntimeState = state.lastStreamItem?.state ?? state.state
        lifecycle = state.lifecycle
        currentStreamItem = state.lastStreamItem
        summary = state.summary
        refreshLifecycle()
    }

    func apply(health: SessionHealthDocument) {
        sessionId = health.sessionId
        sessionWorkspaceId = health.workspaceId
        if let sessionState = health.sessionState {
            reportedRuntimeState = sessionState
        }
        if let lifecycle = health.lifecycle {
            self.lifecycle = lifecycle
        }
        if let summary = health.summary, !summary.isEmpty {
            self.summary = summary
        }
        refreshLifecycle()
    }

    func apply(profile: SessionProfileDocument) {
        sessionId = profile.sessionId
        sessionWorkspaceId = profile.workspaceId
        sessionName = profile.displayName
    }

    func refreshLifecycle(now: Date = Date()) {
        runtimeState = lifecycle?.inferredState(reportedState: reportedRuntimeState, now: now) ?? reportedRuntimeState
    }

    func saveSettings() {
        settings.save()
    }
}

private enum MenagerieDateParser {
    private static let fractionalFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static let standardFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    static func date(from value: String?) -> Date? {
        guard let value else { return nil }
        return fractionalFormatter.date(from: value) ?? standardFormatter.date(from: value)
    }
}
