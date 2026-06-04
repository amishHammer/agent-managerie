import Foundation
import Network

final class MQTTClient {
    private let settings: MenagerieSettings
    private var connection: NWConnection?
    private var packetId: UInt16 = 1
    private var onMessage: ((String, String) -> Void)?
    private var onState: ((Bool) -> Void)?

    init(settings: MenagerieSettings) {
        self.settings = settings
    }

    func connect(onState: @escaping (Bool) -> Void, onMessage: @escaping (String, String) -> Void) {
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
            case .failed, .cancelled:
                self?.onState?(false)
            default:
                break
            }
        }
        connection.start(queue: DispatchQueue(label: "dev.menagerie.mqtt"))
    }

    func disconnect() {
        send(bytes: [0xE0, 0x00])
        connection?.cancel()
        connection = nil
        onState?(false)
    }

    private func sendConnect() {
        var variable = packString("MQTT")
        variable.append(4)
        var flags: UInt8 = 0x02
        if !settings.username.isEmpty { flags |= 0x80 }
        let password = KeychainPasswordStore.read()
        if !password.isEmpty { flags |= 0x40 }
        variable.append(flags)
        variable.append(contentsOf: [0x00, 0x1E])

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
            self?.onState?(true)
            self?.subscribe()
        }
    }

    private func subscribe() {
        let workspace = settings.workspaceId.isEmpty ? "#" : settings.workspaceId
        let stateTopic = "menagerie/v1/state/\(workspace == "#" ? "#" : "\(workspace)/#")"
        let eventTopic = "menagerie/v1/events/\(workspace == "#" ? "#" : "\(workspace)/#")"
        let id = nextPacketId()
        var body = [UInt8(UInt16(id) >> 8), UInt8(UInt16(id) & 0xFF)]
        body.append(contentsOf: packString(stateTopic))
        body.append(1)
        body.append(contentsOf: packString(eventTopic))
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
                self.onMessage?(message.topic, message.payload)
            }
            self.receiveLoop()
        }
    }

    private func parsePublish(type: UInt8, body: [UInt8]) -> (topic: String, payload: String)? {
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
        return (topic, payload)
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
                self.onState?(false)
                return
            }
            completion(Array(data ?? Data()))
        }
    }

    private func sendPacket(typeAndFlags: UInt8, body: [UInt8]) {
        send(bytes: [typeAndFlags] + encodeRemainingLength(body.count) + body)
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
