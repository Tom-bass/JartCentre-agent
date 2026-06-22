#!/bin/bash
set -euo pipefail

export DEVICE_NAME="${DEVICE_NAME:-$(hostname)}"
export CONFIG_FILE="${CONFIG_FILE:-/data/config.json}"

if [ ! -f "$CONFIG_FILE" ]; then
    mkdir -p "$(dirname "$CONFIG_FILE")"
    cat > "$CONFIG_FILE" <<EOF
{
  "device_name": "$DEVICE_NAME",
  "librespot_enabled": true,
  "snapclient_enabled": true,
  "audio_device": "default",
  "snapcast_host": "${SNAPCAST_HOST:-}",
  "agent_api_key": "${AGENT_API_KEY:-}"
}
EOF
fi

LAN_IP=$(hostname -I | awk '{print $1}')
echo "Device  : $DEVICE_NAME"
echo "Web UI  : http://${LAN_IP}:8080"

if [[ -z "${SNAPCAST_HOST:-}" ]]; then
    echo "INFO    : SNAPCAST_HOST not set — configure via web UI at http://${LAN_IP}:8080" >&2
fi
if [[ -z "${AGENT_API_KEY:-}" ]]; then
    echo "INFO    : AGENT_API_KEY not set — configure via web UI to restrict machine-facing endpoints" >&2
fi

exec /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf
