import ctypes
import http.client
import logging
import os
import re
import socket
import threading
import time
import xmlrpc.client
from functools import wraps

import metrics as _metrics
import psutil
import requests
from audio import get_alsa_volume, list_alsa_devices, set_alsa_volume
from config import get_api_key, get_snapcast_host, read_config, write_config
from flask import Flask, jsonify, render_template, request
from snapcast import get_snapcast_volume, set_snapcast_volume

try:
    import docker as _docker_sdk

    _DOCKER_AVAILABLE = True
except ImportError:
    _docker_sdk = None
    _DOCKER_AVAILABLE = False

app = Flask(__name__)

IMAGE_NAME = os.environ.get("IMAGE_NAME", "ghcr.io/tom-bass/jartcentre-agent:latest")
IMAGE_SHA = os.environ.get("IMAGE_SHA", "unknown")
CONTAINER_NAME = os.environ.get("CONTAINER_NAME", "jartcentre-agent")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "Tom-bass/jartcentre-agent")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
SUPERVISOR_SOCK = "/run/supervisor.sock"
SERVICES = ("librespot", "snapclient")

_log = logging.getLogger(__name__)


# ── Auth ──────────────────────────────────────────────────────────────────────


def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = get_api_key()
        if key and request.headers.get("X-API-Key", "") != key:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)

    return decorated


# ── Supervisord XML-RPC over Unix socket ──────────────────────────────────────


class _UnixSocketConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.host)


class _UnixSocketTransport(xmlrpc.client.Transport):
    def make_connection(self, host):
        return _UnixSocketConnection(SUPERVISOR_SOCK)


def _supervisor():
    return xmlrpc.client.ServerProxy("http://localhost", transport=_UnixSocketTransport())


def _process_info(sv, name: str) -> dict:
    try:
        info = sv.supervisor.getProcessInfo(name)
        return {"running": info["statename"] == "RUNNING", "state": info["statename"]}
    except Exception:
        return {"running": False, "state": "UNKNOWN"}


def _set_running(sv, name: str, should_run: bool) -> None:
    info = _process_info(sv, name)
    if should_run and not info["running"]:
        sv.supervisor.startProcess(name)
    elif not should_run and info["running"]:
        sv.supervisor.stopProcess(name)


def _restart_if_running(sv, name: str) -> None:
    try:
        if _process_info(sv, name)["running"]:
            sv.supervisor.stopProcess(name)
            sv.supervisor.startProcess(name)
    except Exception:
        _log.debug("supervisor restart failed for %s", name, exc_info=True)


def _force_restart(sv, name: str) -> None:
    try:
        if _process_info(sv, name)["running"]:
            sv.supervisor.stopProcess(name)
        sv.supervisor.startProcess(name)
    except Exception:
        _log.debug("supervisor force-restart failed for %s", name, exc_info=True)


# ── Update helpers ────────────────────────────────────────────────────────────


def check_for_update() -> dict:
    short = IMAGE_SHA[:7] if len(IMAGE_SHA) > 7 else IMAGE_SHA
    try:
        headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/commits/main",
            headers=headers,
            timeout=5,
        )
        latest_sha = resp.json().get("sha", "")
        return {
            "running_sha": short,
            "latest_sha": latest_sha[:7] if latest_sha else None,
            "update_available": bool(latest_sha) and IMAGE_SHA not in ("unknown", latest_sha),
        }
    except Exception:
        return {"running_sha": short, "latest_sha": None, "update_available": None}


def _do_update() -> None:
    time.sleep(0.5)
    if not _DOCKER_AVAILABLE:
        app.logger.warning("Docker SDK not available — cannot perform update")
        return
    try:
        client = _docker_sdk.from_env()
        client.images.pull(IMAGE_NAME)
        client.containers.get(CONTAINER_NAME).stop()
    except Exception as e:
        app.logger.error("Container update failed: %s", e)


# ── Routes: UI ────────────────────────────────────────────────────────────────


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/status")
def status():
    config = read_config()
    sv = _supervisor()
    device = config.get("audio_device", "default")
    short = IMAGE_SHA[:7] if len(IMAGE_SHA) > 7 else IMAGE_SHA
    return jsonify(
        {
            "device_name": config.get("device_name", ""),
            "audio_device": device,
            "snapcast_host": get_snapcast_host(),
            "api_key_set": bool(get_api_key()),
            "services": {name: _process_info(sv, name) for name in SERVICES},
            "snapcast_volume": get_snapcast_volume(),
            "alsa_volume": get_alsa_volume(device),
            "image_sha": short,
        }
    )


@app.get("/api/system")
def system_info():
    return jsonify(
        {
            "cpu_percent": psutil.cpu_percent(interval=0.3),
            "ram_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage("/").percent,
            "temperature_c": _metrics.cpu_temp(),
            "uptime_seconds": _metrics.uptime_seconds(),
        }
    )


@app.post("/api/config")
def update_config():
    data = request.get_json(force=True)
    config = read_config()
    sv = _supervisor()

    name_changed = "device_name" in data and data["device_name"].strip() != config.get(
        "device_name", ""
    )
    device_changed = "audio_device" in data and data["audio_device"] != config.get(
        "audio_device", "default"
    )
    snapcast_changed = "snapcast_host" in data and data["snapcast_host"].strip() != config.get(
        "snapcast_host", ""
    )

    if "device_name" in data:
        config["device_name"] = data["device_name"].strip()
    if "audio_device" in data:
        config["audio_device"] = data["audio_device"]
    if "snapcast_host" in data:
        config["snapcast_host"] = data["snapcast_host"].strip()
    if "agent_api_key" in data:
        config["agent_api_key"] = data["agent_api_key"].strip()
    for key in ("librespot_enabled", "snapclient_enabled"):
        if key in data:
            config[key] = bool(data[key])

    write_config(config)

    for name in SERVICES:
        if f"{name}_enabled" in data:
            _set_running(sv, name, config[f"{name}_enabled"])

    if name_changed or device_changed:
        for name in SERVICES:
            _restart_if_running(sv, name)
    if snapcast_changed:
        _restart_if_running(sv, "snapclient")

    return jsonify({"ok": True, "config": config})


@app.get("/api/audio/devices")
def audio_devices():
    return jsonify(list_alsa_devices())


@app.get("/api/audio/volume")
def audio_volume_get():
    config = read_config()
    return jsonify(get_alsa_volume(config.get("audio_device", "default")))


@app.post("/api/audio/volume")
def audio_volume_set():
    data = request.get_json(force=True)
    config = read_config()
    ok = set_alsa_volume(
        config.get("audio_device", "default"),
        percent=data.get("percent"),
        muted=data.get("muted"),
    )
    return jsonify({"ok": ok})


@app.get("/api/snapcast/volume")
def snapcast_volume_get():
    return jsonify(get_snapcast_volume())


@app.post("/api/snapcast/volume")
def snapcast_volume_set():
    data = request.get_json(force=True)
    ok = set_snapcast_volume(percent=data.get("percent"), muted=data.get("muted"))
    return jsonify({"ok": ok})


@app.post("/api/services/<name>/restart")
def restart_service(name):
    if name not in SERVICES:
        return jsonify({"error": "unknown service"}), 400
    _force_restart(_supervisor(), name)
    return jsonify({"ok": True})


@app.get("/api/update/check")
def update_check():
    return jsonify(check_for_update())


@app.post("/api/update")
def trigger_update():
    threading.Thread(target=_do_update, daemon=True).start()
    return jsonify({"ok": True, "message": "Update started — container will restart shortly"})


# ── Routes: machine-facing (JartCentre dashboard) ────────────────────────────


@app.get("/metrics")
@require_api_key
def get_metrics():
    return jsonify(_metrics.collect())


@app.get("/docker/logs")
@require_api_key
def docker_logs():
    if not _DOCKER_AVAILABLE:
        return "Docker SDK not available", 503, {"Content-Type": "text/plain"}
    try:
        client = _docker_sdk.from_env()
        name = request.args.get("container", "")
        tail = min(int(request.args.get("tail", 100)), 500)
        raw = client.containers.get(name).logs(tail=tail).decode("utf-8", errors="replace")
        return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", raw), 200, {"Content-Type": "text/plain"}
    except Exception as e:
        return str(e), 500, {"Content-Type": "text/plain"}


@app.post("/docker/restart")
@require_api_key
def docker_restart():
    if not _DOCKER_AVAILABLE:
        return jsonify({"ok": False, "error": "Docker SDK not available"})
    try:
        name = request.args.get("container", "")
        _docker_sdk.from_env().containers.get(name).restart(timeout=10)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.post("/system/reboot")
@require_api_key
def system_reboot():
    def _reboot():
        time.sleep(1.5)
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.reboot(0xFEE1DEAD, 0x28121969, 0x01234567, None)

    threading.Thread(target=_reboot, daemon=True).start()
    return jsonify({"ok": True, "message": "Reboot scheduled"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
