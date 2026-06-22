#!/bin/bash
CONFIG_FILE="${CONFIG_FILE:-/data/config.json}"
DEVICE_NAME=$(read-config "$CONFIG_FILE" device_name "$(hostname)")
# Env var overrides config, config overrides "default"
AUDIO_DEVICE="${LIBRESPOT_DEVICE:-$(read-config "$CONFIG_FILE" audio_device "default")}"

# If the ALSA device enters an error state librespot spins printing POLLERR without
# exiting. Detect the flood and kill it so supervisord can restart after a delay,
# preventing CPU spin and unbounded log growth.
MAX_ERRORS=10
WINDOW_SECS=5
RESTART_DELAY=15

pipe=""
cleanup() { rm -f "$pipe"; kill "$pid" 2>/dev/null; }
trap cleanup EXIT

while true; do
    pipe=$(mktemp -u /tmp/librespot.XXXXXX)
    mkfifo "$pipe"

    librespot \
        --name "$DEVICE_NAME" \
        --backend rodio \
        --device "$AUDIO_DEVICE" \
        --system-cache /data/librespot \
        --zeroconf-port 5354 \
        >"$pipe" 2>&1 &
    pid=$!

    error_count=0
    window_start=$(date +%s)
    killed=false

    while IFS= read -r line; do
        printf '%s\n' "$line"
        if [[ "$line" == *"POLLERR"* ]]; then
            now=$(date +%s)
            if (( now - window_start > WINDOW_SECS )); then
                error_count=1
                window_start=$now
            else
                (( ++error_count ))
                if (( error_count >= MAX_ERRORS )); then
                    printf 'librespot: ALSA error flood detected, restarting in %ds\n' "$RESTART_DELAY"
                    kill "$pid" 2>/dev/null
                    killed=true
                    break
                fi
            fi
        fi
    done < "$pipe"

    rm -f "$pipe"
    wait "$pid" 2>/dev/null || true
    $killed && sleep "$RESTART_DELAY"
done
