// SPDX-License-Identifier: AGPL-3.0-only
import AppKit
import SwiftUI

@main
struct MenagerieApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        Settings {
            SettingsView(model: appDelegate.model)
                .frame(width: 440)
        }
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    let model = MenagerieModel()
    private let brokerRetryDelay: TimeInterval = 5
    private var statusItem: NSStatusItem?
    private var settingsWindowController: NSWindowController?
    private var sessionModels: [String: MenagerieModel] = [:]
    private var sessionWindows: [String: GremlinWindowController] = [:]
    private var pendingProfiles: [String: (profile: SessionProfileDocument, topic: String)] = [:]
    private var mqttClient: MQTTClient?
    private var brokerRetryWorkItem: DispatchWorkItem?
    private var livenessRefreshTimer: Timer?
    private var hasEstablishedBrokerConnection = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        installStatusItem()
        startLivenessRefreshTimer()
        connect()
    }

    func applicationWillTerminate(_ notification: Notification) {
        cancelBrokerRetry()
        livenessRefreshTimer?.invalidate()
        mqttClient?.disconnect()
    }

    private func installStatusItem() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.image = NSImage(systemSymbolName: "sparkle.magnifyingglass", accessibilityDescription: "Menagerie")
        let menu = NSMenu()
        menu.addItem(menuItem(title: "Wake Gremlin", action: #selector(wakeGremlin)))
        menu.addItem(menuItem(title: "Tuck Away", action: #selector(tuckAway)))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(menuItem(title: "Reconnect", action: #selector(reconnect), keyEquivalent: "r"))
        menu.addItem(menuItem(title: "Settings...", action: #selector(openSettings), keyEquivalent: ","))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(menuItem(title: "Quit", action: #selector(quit), keyEquivalent: "q"))
        item.menu = menu
        statusItem = item
    }

    private func menuItem(title: String, action: Selector, keyEquivalent: String = "") -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: keyEquivalent)
        item.target = self
        return item
    }

    private func connect() {
        cancelBrokerRetry()
        let previousClient = mqttClient
        mqttClient = nil
        previousClient?.disconnect()

        let settings = model.settings
        guard !settings.host.isEmpty else {
            handleBrokerConnectionFailed()
            return
        }

        let client = MQTTClient(settings: settings)
        mqttClient = client
        setBrokerConnected(false)
        model.runtimeState = .starting
        model.summary = hasEstablishedBrokerConnection ? "Reconnecting to broker" : "Connecting to broker"
        updateSessionSummariesForBrokerReconnect()
        client.connect(
            onState: { [weak self, weak client] connected in
                DispatchQueue.main.async {
                    guard let self, let client, self.mqttClient === client else { return }
                    self.setBrokerConnected(connected)
                    if connected {
                        self.hasEstablishedBrokerConnection = true
                        self.cancelBrokerRetry()
                        self.model.runtimeState = .idle
                        self.model.summary = "Waiting for a gremlin"
                        self.updateSessionSummariesForBrokerConnected()
                    } else {
                        self.handleBrokerConnectionFailed()
                    }
                }
            },
            onMessage: { [weak self, weak client] topic, payload, retained in
                guard let data = payload.data(using: .utf8) else { return }
                if topic.hasPrefix("menagerie/v1/profile/session/"),
                   let profile = try? JSONDecoder().decode(SessionProfileDocument.self, from: data),
                   profile.kind == "menagerie.sessionProfile" {
                    DispatchQueue.main.async {
                        guard let self, let client, self.mqttClient === client else { return }
                        self.apply(profile: profile, topic: topic)
                    }
                    return
                }
                if let state = try? JSONDecoder().decode(SessionStateDocument.self, from: data) {
                    DispatchQueue.main.async {
                        guard let self, let client, self.mqttClient === client else { return }
                        let sessionModel = self.sessionModel(for: state.sessionId)
                        sessionModel.lastStateTopic = topic
                        sessionModel.apply(state: state)
                    }
                    return
                }
                if let health = try? JSONDecoder().decode(SessionHealthDocument.self, from: data) {
                    DispatchQueue.main.async {
                        guard let self, let client, self.mqttClient === client else { return }
                        let sessionModel = self.sessionModel(for: health.sessionId)
                        sessionModel.lastHealthTopic = topic
                        sessionModel.apply(health: health)
                    }
                    return
                }
                if let event = try? JSONDecoder().decode(SessionEvent.self, from: data) {
                    DispatchQueue.main.async {
                        guard let self, let client, self.mqttClient === client else { return }
                        guard !retained || self.sessionModels[event.sessionId] != nil else { return }
                        let sessionModel = self.sessionModel(for: event.sessionId)
                        sessionModel.lastEventTopic = topic
                        sessionModel.apply(event: event)
                    }
                }
            }
        )
    }

    private func sessionModel(for sessionId: String) -> MenagerieModel {
        if let existing = sessionModels[sessionId] {
            return existing
        }

        let sessionModel = MenagerieModel()
        sessionModel.settings = model.settings
        sessionModel.connected = model.connected
        sessionModel.sessionId = sessionId
        sessionModels[sessionId] = sessionModel
        if let pending = pendingProfiles.removeValue(forKey: sessionId) {
            sessionModel.lastProfileTopic = pending.topic
            sessionModel.apply(profile: pending.profile)
        }

        let window = GremlinWindowController(
            model: sessionModel,
            initialOrigin: sessionWindowOrigin(index: sessionModels.count - 1),
            persistsPosition: false,
            onHide: { [weak self] in
                self?.hideSession(sessionId)
            },
            onSetName: { [weak self] in
                self?.setSessionName(sessionId)
            },
            onKill: { [weak self] in
                self?.killSession(sessionId)
            }
        )
        sessionWindows[sessionId] = window
        if model.settings.showGremlin {
            window.show()
        }
        return sessionModel
    }

    private func hideSession(_ sessionId: String) {
        sessionWindows[sessionId]?.hide()
    }

    private func apply(profile: SessionProfileDocument, topic: String) {
        if let sessionModel = sessionModels[profile.sessionId] {
            sessionModel.lastProfileTopic = topic
            sessionModel.apply(profile: profile)
        } else {
            pendingProfiles[profile.sessionId] = (profile: profile, topic: topic)
        }
    }

    private func setSessionName(_ sessionId: String) {
        guard let sessionModel = sessionModels[sessionId] else { return }
        guard let workspaceId = workspaceId(for: sessionModel) else {
            showSessionNameError("Unable to determine the workspace for this session.")
            return
        }
        guard let displayName = promptForSessionName(currentName: sessionModel.sessionName) else { return }
        guard let profile = mqttClient?.publishSessionProfile(workspaceId: workspaceId, sessionId: sessionId, displayName: displayName) else {
            showSessionNameError("Unable to publish the session name.")
            return
        }
        sessionModel.lastProfileTopic = MQTTClient.sessionProfileTopic(workspaceId: workspaceId, sessionId: sessionId)
        sessionModel.apply(profile: profile)
    }

    private func workspaceId(for sessionModel: MenagerieModel) -> String? {
        if let workspaceId = sessionModel.sessionWorkspaceId, !workspaceId.isEmpty {
            return workspaceId
        }
        let configuredWorkspaceId = model.settings.workspaceId.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !configuredWorkspaceId.isEmpty, configuredWorkspaceId != "#" else { return nil }
        return configuredWorkspaceId
    }

    private func promptForSessionName(currentName: String?) -> String? {
        NSApp.activate(ignoringOtherApps: true)
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 280, height: 24))
        field.stringValue = currentName ?? ""

        let alert = NSAlert()
        alert.messageText = "Set Session Name"
        alert.informativeText = "Leave the name empty to clear it."
        alert.accessoryView = field
        alert.addButton(withTitle: "Save")
        alert.addButton(withTitle: "Cancel")

        let response = alert.runModal()
        guard response == .alertFirstButtonReturn else { return nil }
        return field.stringValue
    }

    private func showSessionNameError(_ message: String) {
        NSApp.activate(ignoringOtherApps: true)
        let alert = NSAlert()
        alert.messageText = "Session Name Not Set"
        alert.informativeText = message
        alert.alertStyle = .warning
        alert.runModal()
    }

    private func killSession(_ sessionId: String) {
        if let sessionModel = sessionModels[sessionId] {
            if let stateTopic = sessionModel.lastStateTopic {
                mqttClient?.clearRetainedMessage(topic: stateTopic)
            } else if let workspaceId = sessionModel.sessionWorkspaceId {
                mqttClient?.clearRetainedSessionState(workspaceId: workspaceId, sessionId: sessionId)
            }
            if let eventTopic = sessionModel.lastEventTopic {
                mqttClient?.clearRetainedMessage(topic: eventTopic)
            }
            if let healthTopic = sessionModel.lastHealthTopic {
                mqttClient?.clearRetainedMessage(topic: healthTopic)
            } else if let workspaceId = sessionModel.sessionWorkspaceId {
                mqttClient?.clearRetainedSessionHealth(workspaceId: workspaceId, sessionId: sessionId)
            }
            if let profileTopic = sessionModel.lastProfileTopic {
                mqttClient?.clearRetainedMessage(topic: profileTopic)
            } else if let workspaceId = workspaceId(for: sessionModel) {
                mqttClient?.clearRetainedMessage(topic: MQTTClient.sessionProfileTopic(workspaceId: workspaceId, sessionId: sessionId))
            }
        }
        sessionWindows[sessionId]?.close()
        sessionWindows[sessionId] = nil
        sessionModels[sessionId] = nil
    }

    private func sessionWindowOrigin(index: Int) -> NSPoint {
        let offset = CGFloat(index % 8) * 28
        return NSPoint(
            x: CGFloat(model.settings.windowX) + offset,
            y: CGFloat(model.settings.windowY) - offset
        )
    }

    private func setBrokerConnected(_ connected: Bool) {
        model.connected = connected
        for sessionModel in sessionModels.values {
            sessionModel.connected = connected
        }
    }

    private func updateSessionSummariesForBrokerReconnect() {
        guard hasEstablishedBrokerConnection else { return }
        for sessionModel in sessionModels.values {
            sessionModel.runtimeState = .starting
            sessionModel.summary = "Reconnecting to broker"
        }
    }

    private func updateSessionSummariesForBrokerConnected() {
        for sessionModel in sessionModels.values {
            sessionModel.refreshLifecycle()
        }
    }

    private func handleBrokerConnectionFailed() {
        setBrokerConnected(false)
        model.runtimeState = .error
        let summary: String
        if hasEstablishedBrokerConnection {
            summary = "Unable to connect to broker. Retrying in \(Int(brokerRetryDelay)) seconds"
            scheduleBrokerRetry()
        } else {
            summary = "Unable to connect to broker"
        }
        model.summary = summary
        for sessionModel in sessionModels.values {
            sessionModel.runtimeState = .error
            sessionModel.summary = summary
        }
    }

    private func scheduleBrokerRetry() {
        guard brokerRetryWorkItem == nil else { return }
        let workItem = DispatchWorkItem { [weak self] in
            self?.brokerRetryWorkItem = nil
            self?.connect()
        }
        brokerRetryWorkItem = workItem
        DispatchQueue.main.asyncAfter(deadline: .now() + brokerRetryDelay, execute: workItem)
    }

    private func cancelBrokerRetry() {
        brokerRetryWorkItem?.cancel()
        brokerRetryWorkItem = nil
    }

    private func startLivenessRefreshTimer() {
        livenessRefreshTimer?.invalidate()
        livenessRefreshTimer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.refreshSessionLiveness()
            }
        }
    }

    private func refreshSessionLiveness() {
        guard model.connected else { return }
        for sessionModel in sessionModels.values {
            sessionModel.refreshLifecycle()
        }
    }

    @objc private func wakeGremlin() {
        model.settings.showGremlin = true
        model.saveSettings()
        for window in sessionWindows.values {
            window.show()
        }
    }

    @objc private func tuckAway() {
        model.settings.showGremlin = false
        model.saveSettings()
        for window in sessionWindows.values {
            window.hide()
        }
    }

    @objc private func reconnect() {
        connect()
    }

    @objc private func openSettings() {
        if let window = settingsWindowController?.window {
            NSApp.activate(ignoringOtherApps: true)
            window.makeKeyAndOrderFront(nil)
            return
        }

        let hostingController = NSHostingController(
            rootView: SettingsView(model: model)
                .frame(width: 440)
        )
        let window = NSWindow(contentViewController: hostingController)
        window.title = "Menagerie Settings"
        window.styleMask = [.titled, .closable, .miniaturizable]
        window.center()
        window.isReleasedWhenClosed = false

        let windowController = NSWindowController(window: window)
        settingsWindowController = windowController
        NSApp.activate(ignoringOtherApps: true)
        windowController.showWindow(nil)
    }

    @objc private func quit() {
        NSApp.terminate(nil)
    }
}
