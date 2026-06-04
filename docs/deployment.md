# Deployment Notes

## Development

```sh
docker compose up --build
```

This exposes authenticated MQTT on `1883`. Use only on a trusted machine or private network.

## Production Baseline

1. Copy `.env.example` to `.env`.
2. Replace all passwords.
3. Configure DNS for the broker host.
4. Enable MQTT over TLS on `8883` with real certificates.
5. Restrict firewall access to known clients where possible.
6. Keep the collector HTTP API private or put it behind your normal internal auth proxy.

The repository includes `broker/tls-listener.conf.example` as the Mosquitto listener shape for TLS. The default Compose file does not expose TLS because certificate paths differ by deployment environment.

## Scaling

MQTT retained state is the source of truth for current session state. The collector is optional for live delivery and can be restarted without interrupting desktop gremlin updates.

If many workspaces publish to the same broker, use distinct `MENAGERIE_WORKSPACE_ID` values and per-team ACLs that narrow clients to `menagerie/v1/*/{workspaceId}/#`.
