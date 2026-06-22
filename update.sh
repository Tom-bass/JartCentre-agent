#!/bin/bash
# Deploy the latest jartcentre-agent image to all Pis on the network.
#
# Prerequisites:
#   - SSH access to each Pi (key-based auth is easiest; will prompt for
#     password otherwise — run `ssh-copy-id pi@<hostname>` once per Pi to set up keys)
#   - Each Pi has ~/jartcentre-agent/docker-compose.yml configured
#
# Usage:
#   ./update.sh              # update all Pis in the PIES list
#   ./update.sh bathroom-pi  # update a single Pi by name

set -uo pipefail

# ── Configure your Pis here ──────────────────────────────────────────────────
PIES=(
    # "pi@living-room-pi"
    # "pi@bedroom-pi"
    # "pi@kitchen-pi"
)
COMPOSE_DIR="~/jartcentre-agent"
# ─────────────────────────────────────────────────────────────────────────────

SSH_OPTS="-o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new"

# If arguments were passed, update only those hosts
if [ $# -gt 0 ]; then
    targets=()
    for arg in "$@"; do
        # Accept bare hostname (dining-pi) or full user@host form
        if [[ "$arg" == *@* ]]; then
            targets+=("$arg")
        else
            targets+=("pi@$arg")
        fi
    done
else
    targets=("${PIES[@]}")
fi

pass=0
fail=0

for target in "${targets[@]}"; do
    echo
    echo "==> $target"
    if ssh $SSH_OPTS "$target" \
        "cd $COMPOSE_DIR && docker compose pull && docker compose up -d"; then
        echo "    ✓ done"
        pass=$((pass + 1))
    else
        echo "    ✗ failed"
        fail=$((fail + 1))
    fi
done

echo
if [ "$fail" -eq 0 ]; then
    echo "All $pass Pi(s) updated."
else
    echo "$pass updated, $fail failed."
fi
