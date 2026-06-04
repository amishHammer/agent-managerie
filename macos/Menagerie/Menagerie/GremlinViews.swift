// SPDX-License-Identifier: AGPL-3.0-only
import SwiftUI

struct GremlinOverlayView: View {
    @ObservedObject var model: MenagerieModel
    @State private var bob = false

    var body: some View {
        VStack(spacing: 8) {
            PixelGremlinView(state: model.runtimeState, bob: bob)
                .frame(width: 128, height: 128)
                .shadow(color: model.runtimeState.tint.opacity(0.45), radius: 18)
            VStack(spacing: 3) {
                HStack(spacing: 5) {
                    Circle()
                        .fill(model.connected ? Color.green : Color.red)
                        .frame(width: 7, height: 7)
                    Text(model.runtimeState.rawValue)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.primary)
                }
                Text(model.summary)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 180)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 8))
        }
        .padding(14)
        .onAppear {
            withAnimation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true)) {
                bob.toggle()
            }
        }
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
            HStack(spacing: 24) {
                EyeView(alert: state == .waitingForPermission || state == .error)
                EyeView(alert: state == .waitingForPermission || state == .error)
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
    let alert: Bool

    var body: some View {
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
                Text(model.summary)
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
