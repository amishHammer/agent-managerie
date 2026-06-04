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

final class AppDelegate: NSObject, NSApplicationDelegate {
    let model = MenagerieModel()
    private var statusItem: NSStatusItem?
    private var gremlinWindow: GremlinWindowController?
    private var mqttClient: MQTTClient?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        installStatusItem()
        gremlinWindow = GremlinWindowController(model: model)
        if model.settings.showGremlin {
            gremlinWindow?.show()
        }
        connect()
    }

    func applicationWillTerminate(_ notification: Notification) {
        mqttClient?.disconnect()
    }

    private func installStatusItem() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.image = NSImage(systemSymbolName: "sparkle.magnifyingglass", accessibilityDescription: "Menagerie")
        let menu = NSMenu()
        menu.addItem(NSMenuItem(title: "Wake Gremlin", action: #selector(wakeGremlin), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Tuck Away", action: #selector(tuckAway), keyEquivalent: ""))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Reconnect", action: #selector(reconnect), keyEquivalent: "r"))
        menu.addItem(NSMenuItem(title: "Settings...", action: #selector(openSettings), keyEquivalent: ","))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Quit", action: #selector(quit), keyEquivalent: "q"))
        item.menu = menu
        statusItem = item
    }

    private func connect() {
        mqttClient?.disconnect()
        let settings = model.settings
        guard !settings.host.isEmpty else { return }
        let client = MQTTClient(settings: settings)
        mqttClient = client
        model.connected = false
        client.connect(
            onState: { [weak self] connected in
                DispatchQueue.main.async {
                    self?.model.connected = connected
                }
            },
            onMessage: { [weak self] topic, payload in
                guard let data = payload.data(using: .utf8) else { return }
                if let state = try? JSONDecoder().decode(SessionStateDocument.self, from: data) {
                    DispatchQueue.main.async {
                        self?.model.apply(state: state)
                    }
                    return
                }
                if let event = try? JSONDecoder().decode(SessionEvent.self, from: data) {
                    DispatchQueue.main.async {
                        self?.model.apply(event: event)
                    }
                }
            }
        )
    }

    @objc private func wakeGremlin() {
        model.settings.showGremlin = true
        model.saveSettings()
        gremlinWindow?.show()
    }

    @objc private func tuckAway() {
        model.settings.showGremlin = false
        model.saveSettings()
        gremlinWindow?.hide()
    }

    @objc private func reconnect() {
        connect()
    }

    @objc private func openSettings() {
        NSApp.activate(ignoringOtherApps: true)
        if !NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil) {
            NSApp.sendAction(Selector(("showPreferencesWindow:")), to: nil, from: nil)
        }
    }

    @objc private func quit() {
        NSApp.terminate(nil)
    }
}
