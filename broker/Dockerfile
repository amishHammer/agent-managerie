# SPDX-License-Identifier: AGPL-3.0-only

FROM eclipse-mosquitto:2

LABEL org.opencontainers.image.licenses="AGPL-3.0-only"

USER root

COPY mosquitto.conf /mosquitto/config/mosquitto.conf
COPY entrypoint.sh /usr/local/bin/menagerie-mosquitto-entrypoint

RUN chmod +x /usr/local/bin/menagerie-mosquitto-entrypoint

ENTRYPOINT ["/usr/local/bin/menagerie-mosquitto-entrypoint"]
CMD ["mosquitto", "-c", "/mosquitto/config/mosquitto.conf"]
