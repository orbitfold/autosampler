from __future__ import annotations


def list_midi_outputs() -> list[str]:
    try:
        import mido
    except ImportError:
        return ["mido is not installed"]
    return list(mido.get_output_names())


def audio_devices_text() -> str:
    try:
        import sounddevice as sd
    except ImportError:
        return "sounddevice is not installed"
    return str(sd.query_devices())
