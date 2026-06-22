# JartCentre Agent

[![CI](https://github.com/Tom-bass/jartcentre-agent/actions/workflows/build.yml/badge.svg)](https://github.com/Tom-bass/jartcentre-agent/actions/workflows/build.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Docker image that turns a Raspberry Pi into a managed network audio client. Each Pi runs
[Snapclient](https://github.com/badaix/snapcast) for synchronised multi-room audio,
[Librespot](https://github.com/librespot-org/librespot) for Spotify Connect, and a Flask web UI
for per-device settings and remote management. Deploying to a new Pi is a single
`docker compose up`.

## Architecture

```
Home LAN
 ├── Snapcast server  (192.168.x.x:1704)
 ├── JartCentre dashboard  ──── /metrics (X-API-Key) ───┐
 └── Spotify app (phone / desktop)                       │
      │  mDNS discovery                                  │
      ▼                                                  ▼
 ┌───────────────────────────────────────────────────────────────┐
 │  jartcentre-agent  (--network host, linux/arm64)              │
 │                                                               │
 │  ┌─────────────────┐  ┌──────────────────┐                   │
 │  │  librespot      │  │  snapclient      │──── ALSA ──► 🔊   │
 │  │  Spotify Connect│  │  Snapcast client │                   │
 │  └─────────────────┘  └──────────────────┘                   │
 │  ┌────────────────────────────────────────────────────────┐   │
 │  │  Flask  :8080                                          │   │
 │  │  Web UI: rename, audio select, volume, service toggle  │   │
 │  │  API:    /metrics, /docker/*, /system/reboot           │   │
 │  └────────────────────────────────────────────────────────┘   │
 │  supervisord  ·  dumb-init (PID 1)                            │
 └───────────────────────────────────────────────────────────────┘
      ↑ http://<pi-hostname>:8080
```

## Features

**Audio**
- Snapcast multi-room synchronised playback
- Spotify Connect via Librespot (zeroconf — no login required)
- Audio output selector in the web UI with human-readable device labels (USB / HDMI / AUX)
- Master volume and mute controls per device

**Management**
- Per-device rename (reflected instantly in Snapcast dashboard and Spotify app)
- Service toggle and restart for Spotify and Snapcast independently
- Snapcast volume and mute controls
- One-click update: pulls the latest image and restarts the container

**Monitoring** (for [JartCentre](https://github.com/Tom-bass/jartcentre) dashboard)
- `/metrics` endpoint: CPU, RAM, disk, temperature, load average, throttle flags, Docker state
- `/docker/logs` and `/docker/restart` for container management
- `/system/reboot` for remote reboot (requires `SYS_BOOT` capability)
- All machine-facing endpoints protected by `X-API-Key` when `AGENT_API_KEY` is set

**Reliability**
- ALSA flood detection: if librespot enters a POLLERR spin loop, it is killed and restarted
  with a backoff delay — prevents 100% CPU and multi-GB log files
- Log rotation: Docker json-file driver capped at 10 MB × 3 files per container
- Settings persist across restarts in a named Docker volume (`/data/config.json`)

## Requirements

- Raspberry Pi 3B+ / 4 / 5 running a 64-bit OS (arm64/aarch64)
- Docker and Docker Compose installed on each Pi
- A running [Snapcast](https://github.com/badaix/snapcast) server on the LAN
- Spotify Premium (for Spotify Connect)

## Quick start

### 1. Authenticate each Pi (one-time)

Pull access to the container registry requires a GitHub Personal Access Token with
`read:packages` scope. Create one at **GitHub → Settings → Developer settings →
Personal access tokens**, then on each Pi:

```bash
echo YOUR_PAT | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

Docker saves credentials to `~/.docker/config.json` and they persist across reboots.

### 2. Create a working directory and compose file

```bash
mkdir -p ~/jartcentre-agent && cd ~/jartcentre-agent

curl -fsSL https://raw.githubusercontent.com/Tom-bass/JartCentre-agent/main/docker-compose.yml \
  -o docker-compose.yml
```

Or create it manually:

```yaml
services:
  jartcentre-agent:
    image: ghcr.io/tom-bass/jartcentre-agent:latest
    container_name: jartcentre-agent
    network_mode: host
    devices:
      - /dev/snd:/dev/snd
    volumes:
      - agent_data:/data
      - /:/hostfs:ro
      - /var/run/docker.sock:/var/run/docker.sock
    cap_add:
      - SYS_BOOT
    environment:
      - CONTAINER_NAME=jartcentre-agent
      - IMAGE_NAME=ghcr.io/tom-bass/jartcentre-agent:latest
      - GITHUB_REPO=Tom-bass/jartcentre-agent
      - DISK_ROOT=/hostfs
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  agent_data:
```

### 3. Start

```bash
docker compose up -d
```

The web UI is available at `http://<pi-hostname>:8080` within a few seconds.

### 4. Configure via web UI

Open `http://<pi-hostname>:8080` and set:

| Setting | Where | Notes |
|---------|-------|-------|
| **Snapcast server** | Connection → Snapcast | IP or hostname of your Snapcast server |
| **API key** | Connection → API Key | Protects `/metrics` and management endpoints — click Generate |
| **Device name** | Device → Name | How this Pi appears in Snapcast and Spotify |
| **Audio output** | Device → Output | Select USB/HDMI/AUX from detected devices |

The device appears in the Spotify app and Snapcast dashboard by the Pi's hostname once
snapclient and librespot are running.

## Configuration

Most settings are configured through the web UI at `http://<pi-hostname>:8080`. Environment
variables are optional and override the web UI — useful for fleet deployments where you want
a consistent value across all devices.

| Variable | Default | Description |
|---|---|---|
| `SNAPCAST_HOST` | *(web UI)* | IP or hostname of the Snapcast server |
| `AGENT_API_KEY` | *(web UI)* | Restricts `/metrics`, `/docker/*`, `/system/reboot` to callers with this key |
| `CONTAINER_NAME` | `jartcentre-agent` | Must match `container_name` — used by Update Now |
| `IMAGE_NAME` | `ghcr.io/tom-bass/jartcentre-agent:latest` | Image to pull on update |
| `GITHUB_REPO` | `Tom-bass/jartcentre-agent` | Repo to check for new commits |
| `DISK_ROOT` | `/` | Mount path for host filesystem (use `/hostfs` with the compose above) |
| `GITHUB_TOKEN` | *(unset)* | Raises GitHub API rate limit from 60 to 5000 req/hr for update checks |
| `DEVICE_NAME` | Pi hostname | Override the display name in Snapcast and Spotify |
| `LIBRESPOT_DEVICE` | `default` | Force an ALSA output device (overrides web UI selection) |

See [`.env.example`](.env.example) for a template with descriptions.

## Upgrading

**Via web UI (recommended):** Click **Update Now** in the device's web UI at
`http://<pi-hostname>:8080`. The container pulls the latest image and restarts automatically.

**Via SSH fleet script:**
```bash
# From your development machine
./update.sh                  # update all Pis in the script's PIES list
./update.sh bathroom-pi      # update a single Pi by hostname
```

**Manually on the Pi:**
```bash
cd ~/jartcentre-agent && docker compose pull && docker compose up -d
```

Wait for the GitHub Actions build to finish before pulling — pulling mid-build will silently
give you the previous image.

## Troubleshooting

**Device doesn't appear in Spotify**
The container must use `network_mode: host`. Without it, librespot's mDNS packets are
isolated in Docker's bridge network and never reach the LAN.

**Spotify fails with `NoDeviceAvailable`**
The ALSA default device (card 0) is likely the HDMI output, which fails without an active
display. List ALSA devices inside the container:
```bash
docker exec jartcentre-agent aplay -l
```
If HDMI is card 0, pin `snd_bcm2835` to index 0 permanently:
```bash
echo "options snd-bcm2835 index=0" | sudo tee /etc/modprobe.d/alsa-base.conf
sudo reboot
```
Or select the correct device in the web UI (`http://<pi>:8080`).

**Librespot spins at 100% CPU with ALSA POLLERR errors**
This indicates the USB audio device has entered an error state (intermittent on some Pi 3B+
USB buses). The flood detector in `run-librespot.sh` kills librespot and restarts it with a
15-second delay. If it keeps recurring, check the USB cable and power supply.

**Snapclient can't connect**
Verify `SNAPCAST_HOST` is correct, the Pi can reach it (`ping $SNAPCAST_HOST`), and port 1704
is open (`nc -zv $SNAPCAST_HOST 1704`). The Snapcast server web UI at
`http://$SNAPCAST_HOST:1780` lists all connected clients.

**Check service states inside the container:**
```bash
docker exec jartcentre-agent supervisorctl status
docker logs -f jartcentre-agent
```

## Development

### Run tests

```bash
pip install -r webui/requirements.txt pytest ruff
pytest
```

### Lint

```bash
ruff check .
ruff format --check .
```

### Build the image locally

```bash
docker buildx build --platform linux/arm64 -t jartcentre-agent .
```

The first build takes ~15 minutes (Rust cross-compilation of librespot on a native amd64
runner). Subsequent builds are fast thanks to GitHub Actions layer caching.

## Security

See [SECURITY.md](SECURITY.md) for the threat model, elevated-privilege justifications, and
hardening recommendations. Short version: this is designed for a trusted home LAN. Set
`AGENT_API_KEY` to protect the machine-facing endpoints.

## License

[MIT](LICENSE)
