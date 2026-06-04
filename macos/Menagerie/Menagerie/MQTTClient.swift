// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Network

final class MQTTClient {
    private let settings: MenagerieSettings
    private let queue = DispatchQueue(label: "dev.menagerie.mqtt")
    private let keepAliveSeconds: UInt16 = 30
    private var connection: NWConnection?
    private var keepAliveTimer: DispatchSourceTimer?
    private var packetId: UInt16 = 1
    private var onMessage: ((String, String, Bool) -> Void)?
    private var onState: ((Bool) -> Void)?

    init(settings: MenagerieSettings) {
        self.settings = settings
    }

    deinit {
        stopKeepAlive()
    }

    func connect(onState: @escaping (Bool) -> Void, onMessage: @escaping (String, String, Bool) -> Void) {
        self.onState = onState
        self.onMessage = onMessage

        let host = NWEndpoint.Host(settings.host)
        guard let port = NWEndpoint.Port(rawValue: settings.port) else { return }
        let parameters: NWParameters
        if settings.useTLS {
            parameters = NWParameters(tls: NWProtocolTLS.Options(), tcp: NWProtocolTCP.Options())
        } else {
            parameters = .tcp
        }

        let connection = NWConnection(host: host, port: port, using: parameters)
        self.connection = connection
        connection.stateUpdateHandler = { [weak self] state in
            switch state {
            case .ready:
                self?.sendConnect()
            case .waiting, .failed, .cancelled:
                self?.stopKeepAlive()
                self?.onState?(false)
            default:
                break
            }
        }
        connection.start(queue: queue)
    }

    func disconnect() {
        stopKeepAlive()
        send(bytes: [0xE0, 0x00])
        connection?.cancel()
        connection = nil
        onState?(false)
    }

    func clearRetainedMessage(topic: String) {
        guard !topic.isEmpty else { return }
        publish(topic: topic, payload: "", retain: true)
    }

    func clearRetainedSessionState(workspaceId: String, sessionId: String) {
        guard !workspaceId.isEmpty, !sessionId.isEmpty else { return }
        clearRetainedMessage(topic: "menagerie/v1/state/\(workspaceId)/\(sessionId)")
    }

    func clearRetainedSessionHealth(workspaceId: String, sessionId: String) {
        guard !workspaceId.isEmpty, !sessionId.isEmpty else { return }
        clearRetainedMessage(topic: "menagerie/v1/health/session/\(workspaceId)/\(sessionId)")
    }

    func publishSessionProfile(workspaceId: String, sessionId: String, displayName: String?) -> SessionProfileDocument? {
        guard !workspaceId.isEmpty, !sessionId.isEmpty else { return nil }
        let trimmedName = displayName?.trimmingCharacters(in: .whitespacesAndNewlines)
        let sanitizedName = trimmedName?.isEmpty == true ? nil : trimmedName.map { String($0.prefix(80)) }
        let summary = sanitizedName.map { "Session named \($0)" } ?? "Session name cleared"
        let profile = SessionProfileDocument(
            id: UUID().uuidString,
            ts: Self.timestamp(),
            source: "menagerie-macos",
            schema: "menagerie.sessionProfile.v1",
            kind: "menagerie.sessionProfile",
            workspaceId: workspaceId,
            sessionId: sessionId,
            displayName: sanitizedName,
            summary: summary
        )
        guard let data = try? JSONEncoder().encode(profile),
              let payload = String(data: data, encoding: .utf8) else {
            return nil
        }
        publish(topic: Self.sessionProfileTopic(workspaceId: workspaceId, sessionId: sessionId), payload: payload, retain: true)
        return profile
    }

    static func sessionProfileTopic(workspaceId: String, sessionId: String) -> String {
        "menagerie/v1/profile/session/\(workspaceId)/\(sessionId)"
    }

    private static func timestamp() -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.string(from: Date())
    }

    private func sendConnect() {
        var variable = packString("MQTT")
        variable.append(4)
        var flags: UInt8 = 0x02
        if !settings.username.isEmpty { flags |= 0x80 }
        let password = KeychainPasswordStore.read()
        if !password.isEmpty { flags |= 0x40 }
        variable.append(flags)
        variable.append(UInt8(keepAliveSeconds >> 8))
        variable.append(UInt8(keepAliveSeconds & 0xFF))

        var payload = packString("menagerie-macos-\(UUID().uuidString)")
        if !settings.username.isEmpty {
            payload.append(contentsOf: packString(settings.username))
        }
        if !password.isEmpty {
            payload.append(contentsOf: packString(password))
        }
        sendPacket(typeAndFlags: 0x10, body: variable + payload)
        receivePacket { [weak self] type, body in
            guard type >> 4 == 2, body.count >= 2, body[1] == 0 else {
                self?.onState?(false)
                return
            }
            self?.startKeepAlive()
            self?.onState?(true)
            self?.subscribe()
        }
    }

    private func subscribe() {
        let workspace = settings.workspaceId.isEmpty ? "#" : settings.workspaceId
        let stateTopic = "menagerie/v1/state/\(workspace == "#" ? "#" : "\(workspace)/#")"
        let eventTopic = "menagerie/v1/events/\(workspace == "#" ? "#" : "\(workspace)/#")"
        let healthTopic = "menagerie/v1/health/\(workspace == "#" ? "#" : "session/\(workspace)/#")"
        let profileTopic = "menagerie/v1/profile/session/\(workspace == "#" ? "#" : "\(workspace)/#")"
        let id = nextPacketId()
        var body = [UInt8(UInt16(id) >> 8), UInt8(UInt16(id) & 0xFF)]
        body.append(contentsOf: packString(stateTopic))
        body.append(1)
        body.append(contentsOf: packString(eventTopic))
        body.append(1)
        body.append(contentsOf: packString(healthTopic))
        body.append(1)
        body.append(contentsOf: packString(profileTopic))
        body.append(1)
        sendPacket(typeAndFlags: 0x82, body: body)
        receivePacket { [weak self] type, _ in
            if type >> 4 == 9 {
                self?.receiveLoop()
            }
        }
    }

    private func receiveLoop() {
        receivePacket { [weak self] type, body in
            guard let self else { return }
            if type >> 4 == 3, let message = self.parsePublish(type: type, body: body) {
                self.onMessage?(message.topic, message.payload, message.retained)
            }
            self.receiveLoop()
        }
    }

    private func parsePublish(type: UInt8, body: [UInt8]) -> (topic: String, payload: String, retained: Bool)? {
        guard body.count >= 2 else { return nil }
        let topicLength = Int(body[0]) << 8 | Int(body[1])
        guard body.count >= 2 + topicLength else { return nil }
        let topicBytes = body[2..<(2 + topicLength)]
        let topic = String(decoding: topicBytes, as: UTF8.self)
        let qos = (type & 0x06) >> 1
        var offset = 2 + topicLength
        var packet: UInt16?
        if qos > 0 {
            guard body.count >= offset + 2 else { return nil }
            packet = UInt16(body[offset]) << 8 | UInt16(body[offset + 1])
            offset += 2
        }
        let payload = String(decoding: body[offset...], as: UTF8.self)
        if qos == 1, let packet {
            send(bytes: [0x40, 0x02, UInt8(packet >> 8), UInt8(packet & 0xFF)])
        }
        return (topic, payload, type & 0x01 != 0)
    }

    private func receivePacket(_ completion: @escaping (UInt8, [UInt8]) -> Void) {
        receiveExactly(1) { [weak self] header in
            guard let self, let headerByte = header.first else { return }
            self.receiveRemainingLength { length in
                self.receiveExactly(length) { body in
                    completion(headerByte, body)
                }
            }
        }
    }

    private func receiveRemainingLength(_ completion: @escaping (Int) -> Void) {
        var multiplier = 1
        var value = 0
        func readByte() {
            receiveExactly(1) { byte in
                guard let encoded = byte.first else { return }
                value += Int(encoded & 127) * multiplier
                if encoded & 128 == 0 {
                    completion(value)
                } else {
                    multiplier *= 128
                    readByte()
                }
            }
        }
        readByte()
    }

    private func receiveExactly(_ count: Int, completion: @escaping ([UInt8]) -> Void) {
        if count == 0 {
            completion([])
            return
        }
        connection?.receive(minimumIncompleteLength: count, maximumLength: count) { data, _, complete, error in
            if complete || error != nil {
                self.stopKeepAlive()
                self.onState?(false)
                return
            }
            completion(Array(data ?? Data()))
        }
    }

    private func publish(topic: String, payload: String, retain: Bool) {
        queue.async { [weak self] in
            guard let self else { return }
            let typeAndFlags: UInt8 = retain ? 0x31 : 0x30
            self.sendPacket(typeAndFlags: typeAndFlags, body: self.packString(topic) + Array(payload.utf8))
        }
    }

    private func sendPacket(typeAndFlags: UInt8, body: [UInt8]) {
        send(bytes: [typeAndFlags] + encodeRemainingLength(body.count) + body)
    }

    private func startKeepAlive() {
        stopKeepAlive()
        let timer = DispatchSource.makeTimerSource(queue: queue)
        let interval = DispatchTimeInterval.seconds(Int(keepAliveSeconds / 2))
        timer.schedule(deadline: .now() + interval, repeating: interval)
        timer.setEventHandler { [weak self] in
            self?.send(bytes: [0xC0, 0x00])
        }
        keepAliveTimer = timer
        timer.resume()
    }

    private func stopKeepAlive() {
        keepAliveTimer?.cancel()
        keepAliveTimer = nil
    }

    private func send(bytes: [UInt8]) {
        connection?.send(content: Data(bytes), completion: .contentProcessed { _ in })
    }

    private func nextPacketId() -> UInt16 {
        let id = packetId
        packetId = packetId == UInt16.max ? 1 : packetId + 1
        return id
    }

    private func packString(_ value: String) -> [UInt8] {
        let bytes = Array(value.utf8)
        return [UInt8(bytes.count >> 8), UInt8(bytes.count & 0xFF)] + bytes
    }

    private func encodeRemainingLength(_ value: Int) -> [UInt8] {
        var value = value
        var encoded: [UInt8] = []
        repeat {
            var byte = UInt8(value % 128)
            value = value / 128
            if value > 0 { byte |= 128 }
            encoded.append(byte)
        } while value > 0
        return encoded
    }
}
