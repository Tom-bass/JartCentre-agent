# Security

## Threat model

JartCentre Agent is designed for a **trusted home LAN** — not a public internet-facing server. The
typical deployment is a Raspberry Pi behind a home router with no port forwarding.

## What is exposed on port 8080

| Path | Auth required | Risk if open |
|---|---|---|
| `GET /` and UI endpoints | None | Device rename, service toggle, volume change |
| `POST /api/update` | None | Pulls latest image and restarts the container |
| `GET /metrics` | `X-API-Key` if `AGENT_API_KEY` set | System telemetry leak |
| `POST /docker/restart` | `X-API-Key` if `AGENT_API_KEY` set | Restart any container on the host |
| `POST /system/reboot` | `X-API-Key` if `AGENT_API_KEY` set | Reboot the Pi |

## Elevated privileges

The container requires capabilities beyond a typical application container:

| Capability / mount | Reason | Risk |
|---|---|---|
| `/dev/snd` device | Audio output | None beyond audio access |
| `/var/run/docker.sock` | Update Now + container metrics | Root-equivalent host access via Docker API |
| `SYS_BOOT` capability | Remote reboot endpoint | Can reboot the host |
| Root user inside container | supervisord, audio, reboot | Standard for this class of embedded service |

The Docker socket mount is the most significant privilege. Any caller who can reach the
authenticated endpoints (`/docker/restart`, `/api/update`) can effectively run arbitrary commands
on the host. **Always set `AGENT_API_KEY`** and restrict LAN access appropriately.

## Recommended configuration

**Minimum for a home network:**
```yaml
# docker-compose.yml
environment:
  - AGENT_API_KEY=<output of: openssl rand -hex 32>
```

The agent prints a warning on startup if `AGENT_API_KEY` is not set.

**For access beyond a trusted LAN** (e.g. remote monitoring via JartCentre):
- Use [Tailscale](https://tailscale.com/) to restrict which devices can reach port 8080
- Or put the service behind a reverse proxy (nginx, Caddy) with HTTPS and IP allowlisting

**Not recommended:**
- Exposing port 8080 directly to the public internet without additional auth

## Reporting a vulnerability

Open a [GitHub issue](../../issues). This is a home project; there is no formal SLA, but
security reports will be addressed promptly.
