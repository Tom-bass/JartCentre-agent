import json
import os

CONFIG_FILE: str = os.environ.get("CONFIG_FILE", "/data/config.json")

# Env vars override config.json — lets fleet deployments set values without the UI.
_ENV_SNAPCAST_HOST: str = os.environ.get("SNAPCAST_HOST", "")
_ENV_AGENT_API_KEY: str = os.environ.get("AGENT_API_KEY", "")

DEFAULTS: dict = {
    "device_name": "",
    "librespot_enabled": True,
    "snapclient_enabled": True,
    "audio_device": "default",
    "snapcast_host": "",
    "agent_api_key": "",
}


def read_config() -> dict:
    with open(CONFIG_FILE) as f:
        return {**DEFAULTS, **json.load(f)}


def write_config(config: dict) -> None:
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_snapcast_host() -> str:
    return _ENV_SNAPCAST_HOST or read_config().get("snapcast_host", "")


def get_api_key() -> str:
    return _ENV_AGENT_API_KEY or read_config().get("agent_api_key", "")
