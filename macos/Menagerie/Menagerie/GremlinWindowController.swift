// SPDX-License-Identifier: AGPL-3.0-only
import AppKit
import SwiftUI

@MainActor
final class GremlinWindowController {
    private let model: MenagerieModel
    private let initialOrigin: NSPoint?
    private let persistsPosition: Bool
    private let onHide: () -> Void
    private let onSetName: () -> Void
    private let onKill: () -> Void
    private var panel: NSPanel?

    init(
        model: MenagerieModel,
        initialOrigin: NSPoint? = nil,
        persistsPosition: Bool = true,
        onHide: @escaping () -> Void = {},
        onSetName: @escaping () -> Void = {},
        onKill: @escaping () -> Void = {}
    ) {
        self.model = model
        self.initialOrigin = initialOrigin
        self.persistsPosition = persistsPosition
        self.onHide = onHide
        self.onSetName = onSetName
        self.onKill = onKill
    }

    func show() {
        if panel == nil {
            let origin = initialOrigin ?? NSPoint(x: model.settings.windowX, y: model.settings.windowY)
            let panel = NSPanel(
                contentRect: NSRect(x: origin.x, y: origin.y, width: 420, height: 280),
                styleMask: [.borderless, .nonactivatingPanel],
                backing: .buffered,
                defer: false
            )
            panel.level = .floating
            panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
            panel.isMovable = true
            panel.isMovableByWindowBackground = true
            panel.isOpaque = false
            panel.backgroundColor = .clear
            panel.hasShadow = false
            panel.ignoresMouseEvents = false
            panel.contentView = DraggableHostingView(
                rootView: GremlinOverlayView(model: model, onHide: onHide, onSetName: onSetName, onKill: onKill)
            )
            self.panel = panel
        }
        panel?.makeKeyAndOrderFront(nil)
    }

    func hide() {
        savePosition()
        panel?.orderOut(nil)
    }

    func close() {
        savePosition()
        panel?.orderOut(nil)
        panel?.close()
        panel = nil
    }

    private func savePosition() {
        guard persistsPosition, let frame = panel?.frame else { return }
        model.settings.windowX = frame.origin.x
        model.settings.windowY = frame.origin.y
        model.saveSettings()
    }
}

private final class DraggableHostingView<Content: View>: NSHostingView<Content> {
    override var mouseDownCanMoveWindow: Bool {
        true
    }
}
