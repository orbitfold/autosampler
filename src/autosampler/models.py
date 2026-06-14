from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Zone:
    root: int
    key_low: int
    key_high: int
    vel_sample: int
    vel_low: int
    vel_high: int
    repeat: int
    filename: str
    frames: int
    layer_name: str = ""


@dataclass(frozen=True)
class SampleConfig:
    midi_out: Optional[str]
    audio_device: Optional[str]
    monitor: bool
    monitor_device: Optional[str]
    monitor_gain: float
    midi_channel: int
    start: str
    end: str
    step: int
    velocities: str
    repeats: int
    note_length: float
    tail: float
    pre_roll: float
    sample_rate: int
    channels: int
    trim_threshold_db: float
    trim_padding_ms: float
    normalize_dbfs: Optional[float]
    name: str
    creator: str
    category: str
    description: str
    keywords: str
    out: Path
    workdir: Path
    keep_workdir: bool
    simulate: bool
    dry_run: bool
    runs_root: Path


@dataclass(frozen=True)
class BuildConfig:
    build_runs: str
    name: str
    creator: str
    category: str
    description: str
    keywords: str
    out: Path
    workdir: Path
    keep_workdir: bool
    dry_run: bool
    runs_root: Path
