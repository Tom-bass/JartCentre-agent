import logging
import socket

import requests
from config import get_snapcast_host

_log = logging.getLogger(__name__)


def _snapcast_rpc(method: str, params: dict | None = None) -> dict | None:
    host = get_snapcast_host()
    if not host:
        return None
    try:
        payload: dict = {"id": 1, "jsonrpc": "2.0", "method": method}
        if params:
            payload["params"] = params
        resp = requests.post(f"http://{host}:1780/jsonrpc", json=payload, timeout=3)
        return resp.json()
    except Exception:
        _log.debug("snapcast RPC %s unreachable", method, exc_info=True)
        return None


def _my_snapcast_client() -> dict | None:
    result = _snapcast_rpc("Server.GetStatus")
    if not result:
        return None
    my_host = socket.gethostname()
    for group in result.get("result", {}).get("server", {}).get("groups", []):
        for client in group.get("clients", []):
            if client["host"]["name"] == my_host:
                return client
    return None


def get_snapcast_volume() -> dict:
    client = _my_snapcast_client()
    if not client:
        return {"percent": None, "muted": None, "connected": False}
    vol = client.get("config", {}).get("volume", {})
    return {
        "percent": vol.get("percent", 100),
        "muted": vol.get("muted", False),
        "connected": client.get("connected", False),
    }


def set_snapcast_volume(percent: int | None = None, muted: bool | None = None) -> bool:
    client = _my_snapcast_client()
    if not client:
        return False
    current = client.get("config", {}).get("volume", {})
    new_vol = {
        "percent": percent if percent is not None else current.get("percent", 100),
        "muted": muted if muted is not None else current.get("muted", False),
    }
    return _snapcast_rpc("Client.SetVolume", {"id": client["id"], "volume": new_vol}) is not None
