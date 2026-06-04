import struct
import unittest

from menagerie.mqtt import (
    build_publish_packet,
    decode_remaining_length_from_bytes,
    encode_remaining_length,
    parse_publish_packet,
)


class MqttEncodingTests(unittest.TestCase):
    def test_remaining_length_round_trip(self):
        for value in [0, 1, 42, 127, 128, 321, 16384, 2097151]:
            encoded = encode_remaining_length(value)
            decoded, consumed = decode_remaining_length_from_bytes(encoded)
            self.assertEqual(decoded, value)
            self.assertEqual(consumed, len(encoded))

    def test_publish_packet_parse(self):
        packet = build_publish_packet(
            topic="menagerie/v1/events/ws/session",
            payload=b'{"ok":true}',
            packet_id=7,
            qos=1,
            retain=False,
        )
        remaining, consumed = decode_remaining_length_from_bytes(packet[1:])
        body = packet[1 + consumed : 1 + consumed + remaining]
        message = parse_publish_packet(packet[0], body)
        self.assertEqual(message.topic, "menagerie/v1/events/ws/session")
        self.assertEqual(message.payload, b'{"ok":true}')
        self.assertEqual(message.qos, 1)
        self.assertEqual(message.packet_id, 7)

    def test_publish_qos1_contains_packet_id(self):
        packet = build_publish_packet(
            topic="topic",
            payload=b"payload",
            packet_id=515,
            qos=1,
            retain=True,
        )
        remaining, consumed = decode_remaining_length_from_bytes(packet[1:])
        body = packet[1 + consumed : 1 + consumed + remaining]
        topic_length = struct.unpack("!H", body[:2])[0]
        packet_id_start = 2 + topic_length
        self.assertEqual(struct.unpack("!H", body[packet_id_start : packet_id_start + 2])[0], 515)
        self.assertEqual(packet[0] & 0x01, 1)


if __name__ == "__main__":
    unittest.main()
