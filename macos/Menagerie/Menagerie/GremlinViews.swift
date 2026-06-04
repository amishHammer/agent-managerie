// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import SwiftUI

struct GremlinOverlayView: View {
    @ObservedObject var model: MenagerieModel
    let onHide: () -> Void
    let onSetName: () -> Void
    let onKill: () -> Void
    @State private var bob = false

    var body: some View {
        ZStack(alignment: .topLeading) {
            VStack(spacing: 8) {
                PixelGremlinView(state: model.runtimeState, bob: bob)
                    .frame(width: 128, height: 128)
                    .shadow(color: model.runtimeState.tint.opacity(0.45), radius: 18)

                VStack(spacing: 3) {
                    Text(model.sessionDisplayName)
                        .font(.caption2.weight(.medium))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                    HStack(spacing: 5) {
                        Circle()
                            .fill(model.connected ? Color.green : Color.red)
                            .frame(width: 7, height: 7)
                        Text(model.activityTitle ?? model.runtimeState.rawValue)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.primary)
                            .lineLimit(1)
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 8)
                .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 8))
                .frame(width: 160, alignment: .center)
            }
            .frame(width: 160, alignment: .top)
            .offset(y: 28)

            ThoughtBubbleView(items: model.thoughtItems, fallback: model.thoughtFallback)
                .offset(x: 132, y: 28)
        }
        .frame(width: 392, height: 252, alignment: .topLeading)
        .padding(14)
        .contextMenu {
            Button("Set Session Name...", action: onSetName)
            Button("Hide This Gremlin", action: onHide)
            Button("Kill This Gremlin", role: .destructive, action: onKill)
        }
        .onAppear {
            withAnimation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true)) {
                bob.toggle()
            }
        }
    }
}

struct ThoughtBubbleView: View {
    let items: [SessionThoughtItem]
    let fallback: String

    var body: some View {
        ZStack(alignment: .topLeading) {
            Circle()
                .fill(.white.opacity(0.9))
                .frame(width: 10, height: 10)
                .offset(x: 4, y: 24)
            Circle()
                .fill(.white.opacity(0.92))
                .frame(width: 16, height: 16)
                .offset(x: 18, y: 10)
            VStack(alignment: .leading, spacing: 8) {
                if items.isEmpty {
                    MarkdownBubbleText(
                        text: fallback,
                        font: .caption.weight(.medium),
                        color: Color.black.opacity(0.86),
                        lineLimit: 4
                    )
                } else {
                    ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                        ThoughtBubbleRow(item: item)
                    }
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .frame(width: 220, alignment: .leading)
            .background(.white.opacity(0.92), in: RoundedRectangle(cornerRadius: 22))
            .overlay {
                RoundedRectangle(cornerRadius: 22)
                    .stroke(.white.opacity(0.95), lineWidth: 2)
            }
            .shadow(color: .black.opacity(0.12), radius: 8, y: 3)
            .offset(x: 28)
        }
        .frame(width: 260, height: 190, alignment: .topLeading)
    }
}

struct ThoughtBubbleRow: View {
    let item: SessionThoughtItem

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            if let title = item.title, !title.isEmpty {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Color.black.opacity(0.9))
                    .lineLimit(1)
            }
            MarkdownBubbleText(
                text: item.body,
                font: .caption2,
                color: item.isRedacted ? Color.black.opacity(0.5) : Color.black.opacity(0.72),
                lineLimit: 2,
                italic: item.isRedacted
            )
        }
    }
}

struct MarkdownBubbleText: View {
    let text: String
    let font: Font
    let color: Color
    let lineLimit: Int
    var italic = false

    var body: some View {
        Text(attributedText)
            .font(font)
            .foregroundStyle(color)
            .italic(italic)
            .lineLimit(lineLimit)
    }

    private var attributedText: AttributedString {
        var options = AttributedString.MarkdownParsingOptions()
        options.interpretedSyntax = .inlineOnlyPreservingWhitespace
        return (try? AttributedString(markdown: text, options: options)) ?? AttributedString(text)
    }
}

struct PixelGremlinView: View {
    let state: SessionRuntimeState
    let bob: Bool

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 24)
                .fill(state.tint.gradient)
                .frame(width: 92, height: 98)
                .offset(y: bob ? -5 : 4)
            HStack(spacing: 22) {
                EyeView(isDead: state == .error || state == .dead || state == .exited, alert: state == .waitingForPermission)
                EyeView(isDead: state == .error || state == .dead || state == .exited, alert: state == .waitingForPermission)
            }
            .offset(y: bob ? -13 : -4)
            Capsule()
                .fill(.white.opacity(0.85))
                .frame(width: state == .readyForReview ? 32 : 20, height: 8)
                .offset(y: bob ? 18 : 27)
            if state == .runningTool || state == .compacting {
                ProgressView()
                    .controlSize(.small)
                    .offset(y: 68)
            }
        }
        .drawingGroup()
    }
}

struct EyeView: View {
    let isDead: Bool
    let alert: Bool

    var body: some View {
        if isDead {
            ZStack {
                Capsule()
                    .fill(.white.opacity(0.9))
                    .frame(width: 4, height: 22)
                    .rotationEffect(.degrees(45))
                Capsule()
                    .fill(.white.opacity(0.9))
                    .frame(width: 4, height: 22)
                    .rotationEffect(.degrees(-45))
            }
            .frame(width: 18, height: 20)
        } else {
            RoundedRectangle(cornerRadius: 3)
                .fill(alert ? .yellow : .white)
                .frame(width: 14, height: alert ? 20 : 14)
                .overlay(alignment: .bottom) {
                    Circle()
                        .fill(.black.opacity(0.85))
                        .frame(width: 6, height: 6)
                        .padding(.bottom, 3)
                }
        }
    }
}

struct SettingsView: View {
    @ObservedObject var model: MenagerieModel
    @State private var password = KeychainPasswordStore.read()

    var body: some View {
        Form {
            Section("Broker") {
                TextField("Host", text: $model.settings.host)
                TextField("Port", value: $model.settings.port, format: .number)
                TextField("Username", text: $model.settings.username)
                SecureField("Password", text: $password)
                Toggle("Use TLS", isOn: $model.settings.useTLS)
                Toggle("Allow insecure TLS certificates", isOn: $model.settings.insecureTLS)
            }
            Section("Subscription") {
                TextField("Workspace ID or #", text: $model.settings.workspaceId)
                Toggle("Show gremlin overlay", isOn: $model.settings.showGremlin)
                Toggle("Verbose local details", isOn: $model.settings.verboseLocalDetails)
            }
            Section("Status") {
                LabeledContent("Connection", value: model.connected ? "Connected" : "Disconnected")
                LabeledContent("State", value: model.runtimeState.rawValue)
                Text(model.displaySummary)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Button("Save") {
                KeychainPasswordStore.write(password)
                model.saveSettings()
            }
        }
        .padding()
    }
}
