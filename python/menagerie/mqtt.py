"""Small MQTT 3.1.1 client used by the Menagerie emitters.

The project intentionally avoids Python package dependencies so hooks can run
from a checked-out plugin or a bundled binary without an install step.
"""

from __future__ import annotations

import socket
import ssl
import struct
from dataclasses import dataclass
from typing import Callable, Iterable


class MqttError(RuntimeError):
    """Raised when the broker rejects or closes an MQTT connection."""


@dataclass(frozen=True)
class PublishMessage:
    topic: str
    payload: bytes
    qos: int
    retain: bool
    packet_id: int | None


def encode_remaining_length(value: int) -> bytes:
    if value < 0:
        raise ValueError("remaining length cannot be negative")
    out = bytearray()
    while True:
        encoded = value % 128
        value //= 128
        if value > 0:
            encoded |= 128
        out.append(encoded)
        if value == 0:
            return bytes(out)


def decode_remaining_length_from_bytes(data: bytes) -> tuple[int, int]:
    multiplier = 1
    value = 0
    for index, encoded in enumerate(data[:4]):
        value += (encoded & 127) * multiplier
        if encoded & 128 == 0:
            return value, index + 1
        multiplier *= 128
    raise MqttError("malformed MQTT remaining length")


def _decode_remaining_length(sock: socket.socket) -> int:
    multiplier = 1
    value = 0
    for _ in range(4):
        encoded = _read_exact(sock, 1)[0]
        value += (encoded & 127) * multiplier
        if encoded & 128 == 0:
            return value
        multiplier *= 128
    raise MqttError("malformed MQTT remaining length")


def pack_utf8(value: str) -> bytes:
    encoded = value.encode("utf-8")
    if len(encoded) > 65535:
        raise ValueError("MQTT UTF-8 field exceeds 65535 bytes")
    return struct.pack("!H", len(encoded)) + encoded


def unpack_utf8(data: bytes, offset: int = 0) -> tuple[str, int]:
    if offset + 2 > len(data):
        raise MqttError("truncated MQTT string length")
    length = struct.unpack("!H", data[offset : offset + 2])[0]
    start = offset + 2
    end = start + length
    if end > len(data):
        raise MqttError("truncated MQTT string payload")
    return data[start:end].decode("utf-8"), end


def _read_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise MqttError("MQTT connection closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _packet(packet_type_and_flags: int, variable_and_payload: bytes) -> bytes:
    return (
        bytes([packet_type_and_flags])
        + encode_remaining_length(len(variable_and_payload))
        + variable_and_payload
    )


def build_connect_packet(
    *,
    client_id: str,
    username: str | None,
    password: str | None,
    keepalive: int,
    clean_session: bool = True,
) -> bytes:
    flags = 0
    if username:
        flags |= 0x80
    if password:
        flags |= 0x40
    if clean_session:
        flags |= 0x02

    variable_header = pack_utf8("MQTT") + bytes([4, flags]) + struct.pack("!H", keepalive)
    payload = pack_utf8(client_id)
    if username:
        payload += pack_utf8(username)
    if password:
        payload += pack_utf8(password)
    return _packet(0x10, variable_header + payload)


def build_publish_packet(
    *,
    topic: str,
    payload: bytes,
    packet_id: int | None,
    qos: int,
    retain: bool,
) -> bytes:
    if qos not in (0, 1):
        raise ValueError("only MQTT QoS 0 and QoS 1 are supported")
    fixed = 0x30 | (qos << 1) | (1 if retain else 0)
    variable_header = pack_utf8(topic)
    if qos == 1:
        if packet_id is None:
            raise ValueError("QoS 1 publish requires a packet id")
        variable_header += struct.pack("!H", packet_id)
    return _packet(fixed, variable_header + payload)


def build_subscribe_packet(packet_id: int, topics: Iterable[tuple[str, int]]) -> bytes:
    payload = bytearray()
    for topic, qos in topics:
        if qos not in (0, 1):
            raise ValueError("only MQTT QoS 0 and QoS 1 are supported")
        payload += pack_utf8(topic) + bytes([qos])
    return _packet(0x82, struct.pack("!H", packet_id) + bytes(payload))


def parse_publish_packet(packet_type_and_flags: int, body: bytes) -> PublishMessage:
    qos = (packet_type_and_flags & 0x06) >> 1
    retain = bool(packet_type_and_flags & 0x01)
    topic, offset = unpack_utf8(body, 0)
    packet_id: int | None = None
    if qos > 0:
        if offset + 2 > len(body):
            raise MqttError("truncated MQTT publish packet id")
        packet_id = struct.unpack("!H", body[offset : offset + 2])[0]
        offset += 2
    return PublishMessage(
        topic=topic,
        payload=body[offset:],
        qos=qos,
        retain=retain,
        packet_id=packet_id,
    )


class MqttClient:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        client_id: str,
        use_tls: bool = False,
        insecure_tls: bool = False,
        keepalive: int = 30,
        timeout: float = 10.0,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client_id = client_id
        self.use_tls = use_tls
        self.insecure_tls = insecure_tls
        self.keepalive = keepalive
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._next_packet_id = 1

    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        if self.use_tls:
            context = ssl.create_default_context()
            if self.insecure_tls:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            sock = context.wrap_socket(sock, server_hostname=self.host)
        sock.settimeout(self.timeout)
        self._sock = sock
        self._send(
            build_connect_packet(
                client_id=self.client_id,
                username=self.username,
                password=self.password,
                keepalive=self.keepalive,
            )
        )
        packet_type, body = self._read_packet()
        if packet_type >> 4 != 2 or len(body) < 2:
            raise MqttError("broker did not return CONNACK")
        return_code = body[1]
        if return_code != 0:
            raise MqttError(f"broker rejected connection with CONNACK code {return_code}")
        sock.settimeout(max(1, self.keepalive))

    def disconnect(self) -> None:
        sock = self._sock
        if sock is None:
            return
        try:
            self._send(bytes([0xE0, 0x00]))
        finally:
            sock.close()
            self._sock = None

    def publish(self, topic: str, payload: bytes | str, *, qos: int = 1, retain: bool = False) -> None:
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        packet_id = self._allocate_packet_id() if qos == 1 else None
        self._send(
            build_publish_packet(
                topic=topic,
                payload=payload,
                packet_id=packet_id,
                qos=qos,
                retain=retain,
            )
        )
        if qos == 1 and packet_id is not None:
            while True:
                packet_type, body = self._read_packet()
                if packet_type >> 4 == 4 and body == struct.pack("!H", packet_id):
                    return
                if packet_type >> 4 == 13:
                    continue
                raise MqttError(f"unexpected MQTT packet while waiting for PUBACK: {packet_type >> 4}")

    def subscribe(self, topics: Iterable[tuple[str, int]]) -> None:
        packet_id = self._allocate_packet_id()
        self._send(build_subscribe_packet(packet_id, topics))
        packet_type, body = self._read_packet()
        if packet_type >> 4 != 9:
            raise MqttError("broker did not return SUBACK")
        if len(body) < 3 or struct.unpack("!H", body[:2])[0] != packet_id:
            raise MqttError("SUBACK packet id mismatch")
        if any(code == 0x80 for code in body[2:]):
            raise MqttError("broker rejected at least one subscription")

    def loop_forever(self, on_message: Callable[[PublishMessage], None]) -> None:
        while True:
            try:
                packet_type, body = self._read_packet()
            except socket.timeout:
                self._send(bytes([0xC0, 0x00]))
                continue
            message_type = packet_type >> 4
            if message_type == 3:
                message = parse_publish_packet(packet_type, body)
                on_message(message)
                if message.qos == 1 and message.packet_id is not None:
                    self._send(bytes([0x40, 0x02]) + struct.pack("!H", message.packet_id))
            elif message_type == 13:
                continue
            elif message_type == 14:
                return

    def _allocate_packet_id(self) -> int:
        packet_id = self._next_packet_id
        self._next_packet_id += 1
        if self._next_packet_id > 65535:
            self._next_packet_id = 1
        return packet_id

    def _send(self, data: bytes) -> None:
        if self._sock is None:
            raise MqttError("MQTT client is not connected")
        self._sock.sendall(data)

    def _read_packet(self) -> tuple[int, bytes]:
        if self._sock is None:
            raise MqttError("MQTT client is not connected")
        packet_type = _read_exact(self._sock, 1)[0]
        remaining_length = _decode_remaining_length(self._sock)
        return packet_type, _read_exact(self._sock, remaining_length)
