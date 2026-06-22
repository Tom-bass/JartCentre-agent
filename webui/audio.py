import logging
import re
import subprocess

_log = logging.getLogger(__name__)

_DEVICE_HINTS = {
    "auto": (
        "ALSA picks the lowest-numbered card automatically. "
        "If audio plays on the wrong output, select a specific device here."
    ),
    "usb": "USB audio adapter or speaker.",
    "hdmi": "HDMI output — typically a monitor or TV with built-in speakers.",
    "aux": "Built-in 3.5mm headphone / AUX jack.",
    "bluetooth": "Bluetooth audio output.",
    "other": "",
}

_TYPE_LABELS = {
    "hdmi": "HDMI",
    "usb": "USB Audio",
    "aux": "AUX / Headphones",
    "bluetooth": "Bluetooth",
}


def _classify_device(card_id: str, card_name: str) -> str:
    combo = f"{card_id} {card_name}".lower()
    if any(x in combo for x in ("hdmi", "displayport", "dp0")):
        return "hdmi"
    if any(x in combo for x in ("usb", "pnp", "uac", "uac2")):
        return "usb"
    _aux = ("headphone", "headset", "bcm2835", "analogue", "analog", "aux", "ac97")
    if any(x in combo for x in _aux):
        return "aux"
    if any(x in combo for x in ("bluetooth", "btaudio")):
        return "bluetooth"
    return "other"


def list_alsa_devices() -> list[dict]:
    try:
        r = subprocess.run(["aplay", "-l"], capture_output=True, text=True, timeout=5)
        devices = [
            {
                "value": "default",
                "label": "System Default (automatic)",
                "type": "auto",
                "detail": "",
                "hint": _DEVICE_HINTS["auto"],
            }
        ]
        for line in r.stdout.splitlines():
            m = re.match(r"card (\d+): (\S+) \[([^\]]+)\], device (\d+):", line)
            if m:
                card_num, card_id, card_name, dev_num = m.groups()
                dtype = _classify_device(card_id, card_name)
                devices.append(
                    {
                        "value": f"plughw:{card_id},{dev_num}",
                        "label": f"{_TYPE_LABELS.get(dtype, card_name)} — {card_name}",
                        "type": dtype,
                        "detail": card_name,
                        "hint": _DEVICE_HINTS.get(dtype, ""),
                        "card_num": int(card_num),
                        "card_id": card_id,
                    }
                )
        return devices
    except Exception:
        _log.debug("aplay device listing failed", exc_info=True)
        return [
            {
                "value": "default",
                "label": "System Default (automatic)",
                "type": "auto",
                "detail": "",
                "hint": _DEVICE_HINTS["auto"],
            }
        ]


def _card_args(device: str) -> list[str]:
    if device == "default":
        return ["-D", "default"]
    m = re.match(r"plughw:([^,]+)", device)
    if m:
        card = m.group(1)
        return ["-c", card] if card.isdigit() else ["-D", f"hw:{card}"]
    return ["-D", "default"]


def _find_mixer_control(card_args: list[str]) -> str | None:
    for ctrl in ("Master", "PCM", "Speaker", "Headphone", "DAC"):
        try:
            r = subprocess.run(
                ["amixer"] + card_args + ["sget", ctrl],
                capture_output=True,
                timeout=5,
            )
            if r.returncode == 0 and b"%" in r.stdout:
                return ctrl
        except Exception:
            pass
    return None


def get_alsa_volume(device: str) -> dict:
    args = _card_args(device)
    ctrl = _find_mixer_control(args)
    if not ctrl:
        return {"percent": None, "muted": None, "supported": False}
    try:
        r = subprocess.run(
            ["amixer"] + args + ["sget", ctrl], capture_output=True, text=True, timeout=5
        )
        m = re.search(r"\[(\d+)%\].*\[(on|off)\]", r.stdout)
        if m:
            return {
                "percent": int(m.group(1)),
                "muted": m.group(2) == "off",
                "supported": True,
                "control": ctrl,
            }
    except Exception:
        pass
    return {"percent": None, "muted": None, "supported": False}


def set_alsa_volume(device: str, percent: int | None, muted: bool | None) -> bool:
    args = _card_args(device)
    ctrl = _find_mixer_control(args)
    if not ctrl:
        return False
    try:
        if percent is not None:
            subprocess.run(
                ["amixer"] + args + ["sset", ctrl, f"{percent}%"],
                capture_output=True,
                timeout=5,
                check=True,
            )
        if muted is not None:
            subprocess.run(
                ["amixer"] + args + ["sset", ctrl, "mute" if muted else "unmute"],
                capture_output=True,
                timeout=5,
                check=True,
            )
        return True
    except Exception:
        return False
