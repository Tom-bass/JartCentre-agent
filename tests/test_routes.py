"""Tests for Flask HTTP routes."""

import json
from unittest.mock import MagicMock, patch

import app as flask_app
import config as config_module
import pytest


@pytest.fixture
def config_file(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(
        json.dumps(
            {
                "device_name": "test-pi",
                "librespot_enabled": True,
                "snapclient_enabled": True,
                "audio_device": "default",
            }
        )
    )
    config_module.CONFIG_FILE = str(p)
    return str(p)


@pytest.fixture
def client(config_file):
    mock_sv = MagicMock()
    mock_sv.supervisor.getProcessInfo.return_value = {"statename": "RUNNING"}

    with (
        patch.object(flask_app, "_supervisor", return_value=mock_sv),
        patch.object(
            flask_app,
            "get_alsa_volume",
            return_value={
                "percent": 80,
                "muted": False,
                "supported": True,
                "control": "PCM",
            },
        ),
        patch.object(
            flask_app,
            "get_snapcast_volume",
            return_value={
                "percent": 100,
                "muted": False,
                "connected": False,
            },
        ),
    ):
        flask_app.app.config["TESTING"] = True
        yield flask_app.app.test_client()


class TestHealth:
    def test_returns_ok(self, client):
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.get_json() == {"status": "ok"}


class TestAuth:
    def test_metrics_without_key_returns_401(self, client):
        res = client.get("/metrics")
        assert res.status_code == 401

    def test_metrics_with_correct_key_returns_200(self, client):
        with patch.object(flask_app._metrics, "collect", return_value={"cpu": 5.0}):
            res = client.get("/metrics", headers={"X-API-Key": "test-key-abc123"})
        assert res.status_code == 200

    def test_metrics_with_wrong_key_returns_401(self, client):
        res = client.get("/metrics", headers={"X-API-Key": "wrong-key"})
        assert res.status_code == 401

    def test_docker_restart_without_key_returns_401(self, client):
        res = client.post("/docker/restart?container=some-container")
        assert res.status_code == 401

    def test_system_reboot_without_key_returns_401(self, client):
        res = client.post("/system/reboot")
        assert res.status_code == 401


class TestConfig:
    def test_update_device_name(self, client, config_file):
        res = client.post("/api/config", json={"device_name": "new-name"})
        assert res.status_code == 200
        data = res.get_json()
        assert data["ok"] is True
        assert data["config"]["device_name"] == "new-name"

    def test_disable_librespot(self, client, config_file):
        res = client.post("/api/config", json={"librespot_enabled": False})
        assert res.status_code == 200
        assert res.get_json()["config"]["librespot_enabled"] is False

    def test_update_audio_device(self, client, config_file):
        res = client.post("/api/config", json={"audio_device": "plughw:Device,0"})
        assert res.status_code == 200
        assert res.get_json()["config"]["audio_device"] == "plughw:Device,0"

    def test_config_persisted_to_disk(self, client, config_file):
        client.post("/api/config", json={"device_name": "persisted-name"})
        with open(config_file) as f:
            saved = json.load(f)
        assert saved["device_name"] == "persisted-name"

    def test_update_snapcast_host(self, client, config_file):
        res = client.post("/api/config", json={"snapcast_host": "192.168.1.10"})
        assert res.status_code == 200
        assert res.get_json()["config"]["snapcast_host"] == "192.168.1.10"

    def test_update_agent_api_key(self, client, config_file):
        res = client.post("/api/config", json={"agent_api_key": "new-secret-key"})
        assert res.status_code == 200
        assert res.get_json()["config"]["agent_api_key"] == "new-secret-key"

    def test_snapcast_host_persisted_to_disk(self, client, config_file):
        client.post("/api/config", json={"snapcast_host": "10.0.0.5"})
        with open(config_file) as f:
            saved = json.load(f)
        assert saved["snapcast_host"] == "10.0.0.5"


class TestServices:
    def test_restart_librespot_returns_ok(self, client):
        res = client.post("/api/services/librespot/restart")
        assert res.status_code == 200
        assert res.get_json()["ok"] is True

    def test_restart_snapclient_returns_ok(self, client):
        res = client.post("/api/services/snapclient/restart")
        assert res.status_code == 200
        assert res.get_json()["ok"] is True

    def test_restart_unknown_service_returns_400(self, client):
        res = client.post("/api/services/unknown-service/restart")
        assert res.status_code == 400

    def test_restart_malicious_name_returns_400(self, client):
        res = client.post("/api/services/../etc/passwd/restart")
        # Flask normalizes path traversal before routing (404); our validator catches
        # other bad names at the route level (400). Both are secure.
        assert res.status_code in (400, 404)


class TestAudioDevices:
    _mock_devices = [
        {
            "value": "default",
            "label": "System Default (automatic)",
            "type": "auto",
            "hint": "ALSA picks automatically.",
            "detail": "",
        },
        {
            "value": "plughw:Headphones,0",
            "label": "AUX / Headphones — bcm2835 Headphones",
            "type": "aux",
            "hint": "3.5mm jack.",
            "detail": "bcm2835 Headphones",
        },
    ]

    def test_returns_list(self, client):
        with patch.object(flask_app, "list_alsa_devices", return_value=self._mock_devices):
            res = client.get("/api/audio/devices")
        assert res.status_code == 200
        assert isinstance(res.get_json(), list)

    def test_default_device_always_present(self, client):
        with patch.object(flask_app, "list_alsa_devices", return_value=self._mock_devices):
            devices = client.get("/api/audio/devices").get_json()
        assert any(d["value"] == "default" for d in devices)

    def test_device_has_required_fields(self, client):
        with patch.object(flask_app, "list_alsa_devices", return_value=self._mock_devices):
            devices = client.get("/api/audio/devices").get_json()
        for device in devices:
            assert "value" in device
            assert "label" in device
            assert "type" in device
            assert "hint" in device


class TestUpdateCheck:
    def test_returns_running_sha(self, client):
        with patch.object(
            flask_app,
            "check_for_update",
            return_value={
                "running_sha": "abc1234",
                "latest_sha": "abc1234",
                "update_available": False,
            },
        ):
            res = client.get("/api/update/check")
        assert res.status_code == 200
        data = res.get_json()
        assert "running_sha" in data
        assert "update_available" in data
