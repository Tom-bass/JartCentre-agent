"""Tests for config.py — read/write, defaults, and env-var override logic."""

import json
from unittest.mock import patch

import config as config_module
import pytest


@pytest.fixture
def config_file(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"device_name": "test-pi", "audio_device": "default"}))
    config_module.CONFIG_FILE = str(p)
    return p


class TestReadConfig:
    def test_returns_stored_values(self, config_file):
        cfg = config_module.read_config()
        assert cfg["device_name"] == "test-pi"

    def test_merges_missing_keys_with_defaults(self, config_file):
        cfg = config_module.read_config()
        # snapcast_host and agent_api_key not in fixture — should come from DEFAULTS
        assert cfg["snapcast_host"] == ""
        assert cfg["agent_api_key"] == ""
        assert cfg["librespot_enabled"] is True

    def test_stored_value_overrides_default(self, config_file):
        config_file.write_text(json.dumps({"snapcast_host": "192.168.1.10"}))
        cfg = config_module.read_config()
        assert cfg["snapcast_host"] == "192.168.1.10"


class TestWriteConfig:
    def test_persists_to_disk(self, config_file):
        cfg = config_module.read_config()
        cfg["device_name"] = "new-name"
        config_module.write_config(cfg)
        saved = json.loads(config_file.read_text())
        assert saved["device_name"] == "new-name"


class TestGetSnapcastHost:
    def test_returns_config_value_when_no_env_override(self, config_file):
        config_file.write_text(json.dumps({"snapcast_host": "192.168.1.50"}))
        with patch.object(config_module, "_ENV_SNAPCAST_HOST", ""):
            assert config_module.get_snapcast_host() == "192.168.1.50"

    def test_env_var_overrides_config(self, config_file):
        config_file.write_text(json.dumps({"snapcast_host": "192.168.1.50"}))
        with patch.object(config_module, "_ENV_SNAPCAST_HOST", "10.0.0.1"):
            assert config_module.get_snapcast_host() == "10.0.0.1"

    def test_returns_empty_string_when_neither_set(self, config_file):
        with patch.object(config_module, "_ENV_SNAPCAST_HOST", ""):
            assert config_module.get_snapcast_host() == ""


class TestGetApiKey:
    def test_returns_config_value_when_no_env_override(self, config_file):
        config_file.write_text(json.dumps({"agent_api_key": "config-key-xyz"}))
        with patch.object(config_module, "_ENV_AGENT_API_KEY", ""):
            assert config_module.get_api_key() == "config-key-xyz"

    def test_env_var_overrides_config(self, config_file):
        config_file.write_text(json.dumps({"agent_api_key": "config-key-xyz"}))
        with patch.object(config_module, "_ENV_AGENT_API_KEY", "env-key-abc"):
            assert config_module.get_api_key() == "env-key-abc"

    def test_returns_empty_string_when_neither_set(self, config_file):
        with patch.object(config_module, "_ENV_AGENT_API_KEY", ""):
            assert config_module.get_api_key() == ""
