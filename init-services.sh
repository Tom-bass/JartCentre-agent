#!/bin/bash
# Reads config on container startup and starts only the enabled audio services.
# Runs once via supervisord, then exits.
set -uo pipefail
CONFIG_FILE="${CONFIG_FILE:-/data/config.json}"
CTL="supervisorctl -c /etc/supervisor/supervisord.conf"

start_if_enabled() {
    local name="$1"
    local key="${name}_enabled"
    local enabled
    enabled=$(python3 -c "import json; d=json.load(open('$CONFIG_FILE')); print(d.get('$key', True))" 2>/dev/null || echo "True")
    if [ "$enabled" = "True" ]; then
        $CTL start "$name" || echo "Warning: could not start $name"
    fi
}

start_if_enabled librespot
start_if_enabled snapclient
