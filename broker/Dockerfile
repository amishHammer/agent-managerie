FROM eclipse-mosquitto:2

USER root

COPY mosquitto.conf /mosquitto/config/mosquitto.conf
COPY entrypoint.sh /usr/local/bin/menagerie-mosquitto-entrypoint

RUN chmod +x /usr/local/bin/menagerie-mosquitto-entrypoint

ENTRYPOINT ["/usr/local/bin/menagerie-mosquitto-entrypoint"]
CMD ["mosquitto", "-c", "/mosquitto/config/mosquitto.conf"]
