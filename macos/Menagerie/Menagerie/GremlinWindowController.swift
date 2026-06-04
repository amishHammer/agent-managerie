// SPDX-License-Identifier: AGPL-3.0-only
import AppKit
import SwiftUI

final class GremlinWindowController {
    private let model: MenagerieModel
    private var panel: NSPanel?

    init(model: MenagerieModel) {
        self.model = model
    }

    func show() {
        if panel == nil {
            let panel = NSPanel(
                contentRect: NSRect(x: model.settings.windowX, y: model.settings.windowY, width: 240, height: 260),
                styleMask: [.borderless, .nonactivatingPanel],
                backing: .buffered,
                defer: false
            )
            panel.level = .floating
            panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
            panel.isOpaque = false
            panel.backgroundColor = .clear
            panel.hasShadow = false
            panel.ignoresMouseEvents = false
            panel.contentView = NSHostingView(rootView: GremlinOverlayView(model: model))
            self.panel = panel
        }
        panel?.makeKeyAndOrderFront(nil)
    }

    func hide() {
        savePosition()
        panel?.orderOut(nil)
    }

    private func savePosition() {
        guard let frame = panel?.frame else { return }
        model.settings.windowX = frame.origin.x
        model.settings.windowY = frame.origin.y
        model.saveSettings()
    }
}
