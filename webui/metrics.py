"""System metrics collection via psutil — ported from jartcentre-agent."""

from __future__ import annotations

import datetime
import logging
import os
import platform
import re
import socket
import subprocess
import time

import psutil

try:
    import docker as _docker_sdk
except ImportError:
    _docker_sdk = None

_BOOT_TIME = psutil.boot_time()
psutil.cpu_percent(interval=None)  # prime the counter; first call returns 0.0

DISK_ROOT = os.environ.get("DISK_ROOT", "/")

_log = logging.getLogger(__name__)

_SKIP_FSTYPES = frozenset(
    {
        "overlay",
        "overlayfs",
        "squashfs",
        "tmpfs",
        "devtmpfs",
        "proc",
        "sysfs",
        "cgroup",
        "cgroup2",
        "pstore",
        "bpf",
        "tracefs",
        "debugfs",
        "securityfs",
        "fusectl",
    }
)
_ANSI = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def cpu_temp() -> float | None:
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return None
        for key in ("cpu_thermal", "cpu-thermal", "coretemp", "k10temp", "acpitz"):
            if key in temps and temps[key]:
                return round(temps[key][0].current, 1)
        for sensors in temps.values():
            if sensors:
                return round(sensors[0].current, 1)
    except Exception:
        pass
    return None


def uptime_seconds() -> int:
    return int(time.time() - _BOOT_TIME)


def _primary_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "unknown"
    finally:
        s.close()


def _collect_throttle() -> dict | None:
    try:
        r = subprocess.run(
            ["vcgencmd", "get_throttled"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if r.returncode != 0:
            return None
        val = int(r.stdout.strip().split("=")[1], 16)
        return {
            "raw_hex": hex(val),
            "undervoltage": bool(val & (1 << 0)),
            "freq_capped": bool(val & (1 << 1)),
            "throttled": bool(val & (1 << 2)),
            "undervoltage_ever": bool(val & (1 << 16)),
            "throttled_ever": bool(val & (1 << 18)),
        }
    except Exception:
        return None


def _collect_disks() -> list[dict]:
    results, seen = [], set()
    for part in psutil.disk_partitions(all=False):
        if part.fstype in _SKIP_FSTYPES:
            continue
        if part.device and part.device in seen:
            continue
        if part.device:
            seen.add(part.device)
        try:
            u = psutil.disk_usage(part.mountpoint)
            results.append(
                {
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "used_gb": round(u.used / 1024**3, 1),
                    "total_gb": round(u.total / 1024**3, 1),
                    "percent": round(u.percent, 1),
                    "warning": u.percent >= 90,
                }
            )
        except (PermissionError, OSError):
            continue
    return results


def _docker_client():
    if _docker_sdk is None:
        return None
    try:
        return _docker_sdk.DockerClient(base_url="unix:///var/run/docker.sock", timeout=5)
    except Exception:
        _log.debug("docker client unavailable", exc_info=True)
        return None


def _collect_docker() -> dict:
    client = _docker_client()
    if client is None:
        return {"available": False, "containers": []}
    try:
        containers = []
        for c in client.containers.list(all=True):
            image_tag = (c.image.tags or [None])[0] or c.image.short_id
            containers.append(
                {
                    "name": c.name,
                    "image": image_tag,
                    "state": c.status,
                    "running": c.status == "running",
                    "restart_count": c.attrs.get("RestartCount", 0),
                }
            )
        return {"available": True, "containers": containers}
    except Exception as e:
        return {"available": False, "error": str(e)[:120], "containers": []}
    finally:
        client.close()


def collect() -> dict:
    """Full metrics snapshot — consumed by the /metrics endpoint for JartCentre."""
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(DISK_ROOT)
    one, five, fifteen = os.getloadavg()
    boot_ts = _BOOT_TIME

    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    ifaces = []
    for name, addr_list in addrs.items():
        if name in ("lo", "localhost"):
            continue
        stat = stats.get(name)
        if not stat or not stat.isup:
            continue
        ip = next(
            (
                a.address
                for a in addr_list
                if a.family == socket.AF_INET and not a.address.startswith("127.")
            ),
            None,
        )
        ifaces.append(
            {
                "name": name,
                "type": "wifi" if name.startswith("w") else "ethernet",
                "ip": ip,
                "speed_mbps": stat.speed if stat.speed > 0 else None,
            }
        )

    return {
        "cpu": round(psutil.cpu_percent(interval=0.5), 1),
        "ram": {"used": mem.used, "total": mem.total, "percent": round(mem.percent, 1)},
        "disk": {"used": disk.used, "total": disk.total, "percent": round(disk.percent, 1)},
        "load_avg": {"1m": round(one, 2), "5m": round(five, 2), "15m": round(fifteen, 2)},
        "swap": {
            "used": psutil.swap_memory().used,
            "total": psutil.swap_memory().total,
            "percent": round(psutil.swap_memory().percent, 1),
        },
        "disks": _collect_disks(),
        "throttle": _collect_throttle(),
        "cpu_governor": _try_read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
        "system": {
            "hostname": socket.gethostname(),
            "os": f"{platform.system()} {platform.release()} {platform.machine()}".strip(),  # noqa: E501
            "uptime_seconds": uptime_seconds(),
            "boot_time": datetime.datetime.fromtimestamp(boot_ts).strftime("%Y-%m-%dT%H:%M:%S"),  # noqa: E501
            "cpu_cores": psutil.cpu_count(logical=True),
        },
        "temps": {"cpu": cpu_temp()},
        "network": {"primary": ifaces[0]["name"] if ifaces else None, "interfaces": ifaces},
        "docker": _collect_docker(),
    }


def _try_read(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None
