# SPDX-License-Identifier: AGPL-3.0-only
"""Shared MQTT publishing helpers."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

from .events import (
    dumps,
    env_bool,
    env_value,
    health_document,
    health_topic,
    session_health_document,
    session_health_topic,
    session_profile_topic,
    state_document,
    topics_for,
)
from .mqtt import MqttClient


@dataclass(frozen=True)
class MqttSettings:
    host: str
    port: int
    username: str | None
    password: str | None
    use_tls: bool
    insecure_tls: bool
    client_id: str


def _legacy_prefix(prefix: str) -> str | None:
    return "CODEX_PET_MQTT" if prefix == "MENAGERIE_MQTT" else None


def _prefixed_env(prefix: str, suffix: str) -> str | None:
    legacy = _legacy_prefix(prefix)
    legacy_name = f"{legacy}_{suffix}" if legacy else None
    return env_value(f"{prefix}_{suffix}", legacy_name)


def mqtt_settings(prefix: str = "MENAGERIE_MQTT") -> MqttSettings:
    host = _prefixed_env(prefix, "HOST") or os.environ.get("MQTT_HOST") or "localhost"
    use_tls = env_bool(f"{prefix}_TLS", f"{_legacy_prefix(prefix)}_TLS" if _legacy_prefix(prefix) else None)
    mqtt_tls = env_bool("MQTT_TLS")
    default_port = 8883 if use_tls or mqtt_tls else 1883
    port = int(_prefixed_env(prefix, "PORT") or os.environ.get("MQTT_PORT") or default_port)
    username = _prefixed_env(prefix, "USERNAME") or os.environ.get("MQTT_USERNAME")
    password = _prefixed_env(prefix, "PASSWORD") or os.environ.get("MQTT_PASSWORD")
    use_tls = use_tls or mqtt_tls
    insecure_tls = env_bool(
        f"{prefix}_TLS_INSECURE",
        f"{_legacy_prefix(prefix)}_TLS_INSECURE" if _legacy_prefix(prefix) else None,
    ) or env_bool("MQTT_TLS_INSECURE")
    client_id = _prefixed_env(prefix, "CLIENT_ID") or f"menagerie-{uuid.uuid4()}"
    return MqttSettings(
        host=host,
        port=port,
        username=username,
        password=password,
        use_tls=use_tls,
        insecure_tls=insecure_tls,
        client_id=client_id,
    )


def client_from_settings(settings: MqttSettings) -> MqttClient:
    return MqttClient(
        host=settings.host,
        port=settings.port,
        username=settings.username,
        password=settings.password,
        client_id=settings.client_id,
        use_tls=settings.use_tls,
        insecure_tls=settings.insecure_tls,
    )


def publish_event(event: dict) -> None:
    settings = mqtt_settings()
    client = client_from_settings(settings)
    client.connect()
    try:
        event_topic, state_topic = topics_for(event)
        client.publish(event_topic, dumps(event), qos=1, retain=False)
        if event.get("state"):
            client.publish(state_topic, dumps(state_document(event)), qos=1, retain=True)
            client.publish(
                session_health_topic(event),
                dumps(session_health_document(event)),
                qos=1,
                retain=True,
            )
        client.publish(
            health_topic(settings.client_id),
            dumps(health_document(settings.client_id)),
            qos=1,
            retain=True,
        )
    finally:
        client.disconnect()


def publish_session_profile(profile: dict) -> None:
    settings = mqtt_settings()
    client = client_from_settings(settings)
    client.connect()
    try:
        client.publish(
            session_profile_topic(profile["workspaceId"], profile["sessionId"]),
            dumps(profile),
            qos=1,
            retain=True,
        )
        client.publish(
            health_topic(settings.client_id),
            dumps(health_document(settings.client_id)),
            qos=1,
            retain=True,
        )
    finally:
        client.disconnect()
