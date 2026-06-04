#!/usr/bin/env sh
# SPDX-License-Identifier: AGPL-3.0-only
set -eu

: "${MQTT_HOOK_USERNAME:=codex-hook}"
: "${MQTT_HOOK_PASSWORD:=dev-hook-password}"
MQTT_APP_USERNAME="${MQTT_APP_USERNAME:-${MQTT_PET_USERNAME:-menagerie-app}}"
MQTT_APP_PASSWORD="${MQTT_APP_PASSWORD:-${MQTT_PET_PASSWORD:-dev-menagerie-password}}"
: "${MQTT_COLLECTOR_USERNAME:=codex-collector}"
: "${MQTT_COLLECTOR_PASSWORD:=dev-collector-password}"
: "${MQTT_TOPIC_ROOT:=menagerie/v1}"

mkdir -p /mosquitto/config /mosquitto/data /mosquitto/log

PASSWORD_FILE=/mosquitto/config/passwords
ACL_FILE=/mosquitto/config/acl

# These files are generated from environment on every container start. Remove
# stale copies so restarts do not fail when mosquitto_passwd creates the file.
rm -f "${PASSWORD_FILE}" "${ACL_FILE}"

mosquitto_passwd -b -c "${PASSWORD_FILE}" "${MQTT_HOOK_USERNAME}" "${MQTT_HOOK_PASSWORD}"
mosquitto_passwd -b "${PASSWORD_FILE}" "${MQTT_APP_USERNAME}" "${MQTT_APP_PASSWORD}"
mosquitto_passwd -b "${PASSWORD_FILE}" "${MQTT_COLLECTOR_USERNAME}" "${MQTT_COLLECTOR_PASSWORD}"

cat > "${ACL_FILE}" <<EOF
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

chmod 0640 "${PASSWORD_FILE}" "${ACL_FILE}"
chown mosquitto:mosquitto "${PASSWORD_FILE}" "${ACL_FILE}"
chown -R mosquitto:mosquitto /mosquitto/data /mosquitto/log

exec "$@"
