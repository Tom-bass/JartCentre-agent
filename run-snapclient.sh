#!/bin/bash
set -e
CONFIG_FILE="${CONFIG_FILE:-/data/config.json}"
DEVICE_NAME=$(read-config "$CONFIG_FILE" device_name "$(hostname)")
AUDIO_DEVICE=$(read-config "$CONFIG_FILE" audio_device "default")

# Env var overrides config — allows fleet-wide setting without web UI
if [[ -z "${SNAPCAST_HOST:-}" ]]; then
    SNAPCAST_HOST=$(read-config "$CONFIG_FILE" snapcast_host "")
fi

if [[ -z "${SNAPCAST_HOST:-}" ]]; then
    echo "snapclient: snapcast_host not configured — set it via the web UI" >&2
    exit 1
fi

if [ "$AUDIO_DEVICE" = "default" ]; then
    exec snapclient -h "${SNAPCAST_HOST}" --hostID "$(hostname)" --player alsa
else
    exec snapclient -h "${SNAPCAST_HOST}" --hostID "$(hostname)" --player alsa -s "${AUDIO_DEVICE}"
fi
