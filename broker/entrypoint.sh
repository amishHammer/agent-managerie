#!/usr/bin/env sh
set -eu

: "${MQTT_HOOK_USERNAME:=codex-hook}"
: "${MQTT_HOOK_PASSWORD:=dev-hook-password}"
MQTT_APP_USERNAME="${MQTT_APP_USERNAME:-${MQTT_PET_USERNAME:-menagerie-app}}"
MQTT_APP_PASSWORD="${MQTT_APP_PASSWORD:-${MQTT_PET_PASSWORD:-dev-menagerie-password}}"
: "${MQTT_COLLECTOR_USERNAME:=codex-collector}"
: "${MQTT_COLLECTOR_PASSWORD:=dev-collector-password}"
: "${MQTT_TOPIC_ROOT:=menagerie/v1}"

mkdir -p /mosquitto/config /mosquitto/data /mosquitto/log

mosquitto_passwd -b -c /mosquitto/config/passwords "${MQTT_HOOK_USERNAME}" "${MQTT_HOOK_PASSWORD}"
mosquitto_passwd -b /mosquitto/config/passwords "${MQTT_APP_USERNAME}" "${MQTT_APP_PASSWORD}"
mosquitto_passwd -b /mosquitto/config/passwords "${MQTT_COLLECTOR_USERNAME}" "${MQTT_COLLECTOR_PASSWORD}"

cat > /mosquitto/config/acl <<EOF
user ${MQTT_HOOK_USERNAME}
topic write ${MQTT_TOPIC_ROOT}/events/#
topic write ${MQTT_TOPIC_ROOT}/state/#
topic write ${MQTT_TOPIC_ROOT}/health/#

user ${MQTT_APP_USERNAME}
topic read ${MQTT_TOPIC_ROOT}/events/#
topic read ${MQTT_TOPIC_ROOT}/state/#
topic read ${MQTT_TOPIC_ROOT}/health/#

user ${MQTT_COLLECTOR_USERNAME}
topic read ${MQTT_TOPIC_ROOT}/events/#
topic read ${MQTT_TOPIC_ROOT}/state/#
topic read ${MQTT_TOPIC_ROOT}/health/#
EOF

chmod 0640 /mosquitto/config/passwords /mosquitto/config/acl
chown mosquitto:mosquitto /mosquitto/config/passwords /mosquitto/config/acl
chown -R mosquitto:mosquitto /mosquitto/data /mosquitto/log

exec "$@"
