"""Tests for ALSA device classification and parsing."""

from unittest.mock import MagicMock, patch

from audio import _card_args, _classify_device, list_alsa_devices

_APLAY_OUTPUT = """\
**** List of PLAYBACK Hardware Devices ****
card 0: Headphones [bcm2835 Headphones], device 0: bcm2835 Headphones [bcm2835 Headphones]
card 1: vc4hdmi [vc4-hdmi], device 0: MAI PCM i2s-hifi-0 [MAI PCM i2s-hifi-0]
card 2: Device [USB PnP Sound Device], device 0: USB Audio [USB Audio]
"""


class TestClassifyDevice:
    def test_hdmi_by_name(self):
        assert _classify_device("vc4hdmi", "vc4-hdmi") == "hdmi"

    def test_hdmi_by_keyword(self):
        assert _classify_device("HDMI", "HDMI Output") == "hdmi"

    def test_usb_pnp(self):
        assert _classify_device("Device", "USB PnP Sound Device") == "usb"

    def test_usb_by_id(self):
        assert _classify_device("USB_Adapter", "Generic USB Audio") == "usb"

    def test_aux_bcm2835(self):
        assert _classify_device("Headphones", "bcm2835 Headphones") == "aux"

    def test_aux_headphone_keyword(self):
        assert _classify_device("hw0", "Analogue Output") == "aux"

    def test_bluetooth(self):
        assert _classify_device("btaudio", "Bluetooth Audio") == "bluetooth"

    def test_unknown_falls_back_to_other(self):
        assert _classify_device("SomeCard", "Generic Audio Device") == "other"


class TestCardArgs:
    def test_default_device(self):
        assert _card_args("default") == ["-D", "default"]

    def test_named_card(self):
        assert _card_args("plughw:Device,0") == ["-D", "hw:Device"]

    def test_named_card_headphones(self):
        assert _card_args("plughw:Headphones,0") == ["-D", "hw:Headphones"]

    def test_numeric_card_zero(self):
        assert _card_args("plughw:0,0") == ["-c", "0"]

    def test_numeric_card_two(self):
        assert _card_args("plughw:2,0") == ["-c", "2"]


class TestListAlsaDevices:
    def test_always_includes_default_first(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=_APLAY_OUTPUT, returncode=0)
            devices = list_alsa_devices()

        assert devices[0]["value"] == "default"
        assert devices[0]["type"] == "auto"

    def test_parses_three_hardware_cards(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=_APLAY_OUTPUT, returncode=0)
            devices = list_alsa_devices()

        assert len(devices) == 4  # default + 3 hardware cards

    def test_device_types_correctly_classified(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=_APLAY_OUTPUT, returncode=0)
            devices = list_alsa_devices()

        by_value = {d["value"]: d for d in devices}
        assert by_value["plughw:Headphones,0"]["type"] == "aux"
        assert by_value["plughw:vc4hdmi,0"]["type"] == "hdmi"
        assert by_value["plughw:Device,0"]["type"] == "usb"

    def test_usb_label_is_human_readable(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=_APLAY_OUTPUT, returncode=0)
            devices = list_alsa_devices()

        usb = next(d for d in devices if d["type"] == "usb")
        assert "USB" in usb["label"]
        assert "USB PnP Sound Device" in usb["label"]

    def test_all_devices_have_hint_field(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=_APLAY_OUTPUT, returncode=0)
            devices = list_alsa_devices()

        for device in devices:
            assert "hint" in device

    def test_fallback_to_default_on_subprocess_error(self):
        with patch("subprocess.run", side_effect=OSError("aplay not found")):
            devices = list_alsa_devices()

        assert len(devices) == 1
        assert devices[0]["value"] == "default"
