from __future__ import annotations

import time
import wave
import threading
from contextlib import suppress
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf


def _safe_note_off(out, *, channel: int, note: int) -> None:
    import mido

    with suppress(Exception):
        out.send(
            mido.Message(
                "note_off",
                note=int(note),
                velocity=0,
                channel=int(channel) - 1,
            )
        )


def _safe_midi_panic(out, *, channel: int) -> None:
    """
    Send redundant cleanup messages on one MIDI channel.

    CC 123 = all notes off
    CC 120 = all sound off

    We also send explicit note_off for all 128 notes because some MIDI/CV
    interfaces and older synth workflows do not reliably honor panic CCs.
    """
    import mido

    midi_channel = int(channel) - 1

    with suppress(Exception):
        out.send(mido.Message("control_change", control=123, value=0, channel=midi_channel))

    with suppress(Exception):
        out.send(mido.Message("control_change", control=120, value=0, channel=midi_channel))

    for note in range(128):
        with suppress(Exception):
            out.send(
                mido.Message(
                    "note_off",
                    note=note,
                    velocity=0,
                    channel=midi_channel,
                )
            )


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


def _parse_sounddevice_id(value: Optional[str]) -> int | str | None:
    if value is None or value == "":
        return None
    return int(value) if str(value).isdigit() else value


def _record_with_software_monitor(
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
    input_device: int | str | None,
    output_device: int | str | None,
    monitor_gain: float,
) -> np.ndarray:
    import mido
    import sounddevice as sd

    duration = max(0.01, pre_roll + note_length + tail)
    frames = int(round(duration * sample_rate))
    rec = np.zeros((frames, channels), dtype=np.float32)
    finished = threading.Event()
    write_pos = 0
    gain = float(monitor_gain)

    def callback(indata: np.ndarray, outdata: np.ndarray, frame_count: int, _time, status) -> None:
        nonlocal write_pos

        remaining = frames - write_pos
        take = min(frame_count, max(0, remaining))

        outdata.fill(0.0)

        if take > 0:
            rec[write_pos : write_pos + take, :] = indata[:take, :channels]

            monitored = indata[:take, : min(indata.shape[1], outdata.shape[1])] * gain
            outdata[:take, : monitored.shape[1]] = monitored

            write_pos += take

        if write_pos >= frames:
            finished.set()
            raise sd.CallbackStop

    with mido.open_output(midi_out_name) as out:
        note_is_on = False

        try:
            with sd.Stream(
                samplerate=sample_rate,
                dtype="float32",
                device=(input_device, output_device),
                channels=(channels, channels),
                callback=callback,
            ):
                time.sleep(pre_roll)

                out.send(
                    mido.Message(
                        "note_on",
                        note=note,
                        velocity=velocity,
                        channel=channel - 1,
                    )
                )
                note_is_on = True

                time.sleep(note_length)

                out.send(
                    mido.Message(
                        "note_off",
                        note=note,
                        velocity=0,
                        channel=channel - 1,
                    )
                )
                note_is_on = False

                time.sleep(tail)
                finished.wait(timeout=duration + 2.0)

        finally:
            if note_is_on:
                _safe_note_off(out, channel=channel, note=note)
                _safe_midi_panic(out, channel=channel)

            with suppress(Exception):
                import sounddevice as sd

                sd.stop()

    return rec
    

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
    monitor: bool = False,
    monitor_device: Optional[str] = None,
    monitor_gain: float = 1.0,
) -> np.ndarray:
    import mido
    import sounddevice as sd

    duration = max(0.01, pre_roll + note_length + tail)
    frames = int(round(duration * sample_rate))


    input_device = _parse_sounddevice_id(audio_device)
    output_device = _parse_sounddevice_id(monitor_device)

    if monitor and output_device is None:
        output_device = input_device

    if monitor:
        return _record_with_software_monitor(
            midi_out_name=midi_out_name,
            channel=channel,
            note=note,
            velocity=velocity,
            note_length=note_length,
            tail=tail,
            pre_roll=pre_roll,
            sample_rate=sample_rate,
            channels=channels,
            input_device=input_device,
            output_device=output_device,
            monitor_gain=monitor_gain,
        )

    with mido.open_output(midi_out_name) as out:
        note_is_on = False

        try:
            rec = sd.rec(
                frames,
                samplerate=sample_rate,
                channels=channels,
                dtype="float32",
                device=input_device,
            )

            time.sleep(pre_roll)

            out.send(
                mido.Message(
                    "note_on",
                    note=note,
                    velocity=velocity,
                    channel=channel - 1,
                )
            )
            note_is_on = True

            time.sleep(note_length)

            out.send(
                mido.Message(
                    "note_off",
                    note=note,
                    velocity=0,
                    channel=channel - 1,
                )
            )
            note_is_on = False

            time.sleep(tail)
            sd.wait()

        finally:
            if note_is_on:
                _safe_note_off(out, channel=channel, note=note)
                _safe_midi_panic(out, channel=channel)

            with suppress(Exception):
                sd.stop()

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
