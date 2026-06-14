from __future__ import annotations

import time
import wave
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf


def trim_audio(data: np.ndarray, threshold_db: float, padding_ms: float, sample_rate: int) -> np.ndarray:
    if data.size == 0:
        return data
    mono_env = np.max(np.abs(data), axis=1) if data.ndim == 2 else np.abs(data)
    threshold = 10.0 ** (threshold_db / 20.0)
    above = np.flatnonzero(mono_env >= threshold)
    if above.size == 0:
        return data[: max(1, int(sample_rate * 0.05))]
    pad = int(sample_rate * padding_ms / 1000.0)
    start = max(0, int(above[0]) - pad)
    stop = min(data.shape[0], int(above[-1]) + pad + 1)
    return data[start:stop]


def normalize_peak(data: np.ndarray, target_dbfs: Optional[float]) -> np.ndarray:
    if target_dbfs is None:
        return data
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak <= 0.0:
        return data
    target = 10.0 ** (target_dbfs / 20.0)
    return np.clip(data * (target / peak), -1.0, 1.0)


def write_wav(path: Path, data: np.ndarray, sample_rate: int) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, data, sample_rate, subtype="PCM_24")
    return int(data.shape[0])


def wav_frame_count(path: Path) -> int:
    with wave.open(str(path), "rb") as wav_file:
        return int(wav_file.getnframes())


def record_hardware_note(
    *,
    midi_out_name: str,
    channel: int,
    note: int,
    velocity: int,
    note_length: float,
    tail: float,
    pre_roll: float,
    sample_rate: int,
    channels: int,
    audio_device: Optional[str],
) -> np.ndarray:
    import mido
    import sounddevice as sd

    duration = max(0.01, pre_roll + note_length + tail)
    frames = int(round(duration * sample_rate))

    device: int | str | None = None
    if audio_device is not None:
        device = int(audio_device) if str(audio_device).isdigit() else audio_device

    with mido.open_output(midi_out_name) as out:
        rec = sd.rec(frames, samplerate=sample_rate, channels=channels, dtype="float32", device=device)
        time.sleep(pre_roll)
        out.send(mido.Message("note_on", note=note, velocity=velocity, channel=channel - 1))
        time.sleep(note_length)
        out.send(mido.Message("note_off", note=note, velocity=0, channel=channel - 1))
        time.sleep(tail)
        sd.wait()
    return np.asarray(rec, dtype=np.float32)


def simulate_note(note: int, velocity: int, duration: float, tail: float, sample_rate: int, channels: int) -> np.ndarray:
    """Generate a simple test tone so packaging can be tested without MIDI/audio hardware."""
    freq = 440.0 * (2.0 ** ((note - 69) / 12.0))
    length = max(0.1, duration + tail)
    t = np.linspace(0, length, int(sample_rate * length), endpoint=False)
    amp = max(0.02, velocity / 127.0) * 0.35
    env = np.exp(-t / max(0.15, length / 3.0))
    sig = amp * env * (np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(2 * np.pi * freq * 2.01 * t))
    sig = sig.astype(np.float32)
    if channels == 1:
        return sig.reshape(-1, 1)
    return np.stack([sig, sig], axis=1)
