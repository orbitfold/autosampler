from __future__ import annotations

import math
import re

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_TO_SHARP = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
NOTE_RE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d+)$")
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def note_to_midi(value: str | int) -> int:
    """Parse a MIDI integer or Bitwig-style note name, where C3 == MIDI 60."""
    if isinstance(value, int):
        if 0 <= value <= 127:
            return value
        raise ValueError(f"MIDI note out of range: {value}")

    text = str(value).strip()
    if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
        n = int(text)
        if 0 <= n <= 127:
            return n
        raise ValueError(f"MIDI note out of range: {value}")

    match = NOTE_RE.match(text)
    if not match:
        raise ValueError(f"Invalid note '{value}'. Use MIDI number or note name like C2, F#3, Bb1.")

    letter, accidental, octave_text = match.groups()
    name = letter.upper() + accidental
    if accidental == "b":
        name = FLAT_TO_SHARP.get(letter.upper() + "b", name)

    if name not in NOTE_NAMES:
        raise ValueError(f"Invalid note name '{value}'.")

    octave = int(octave_text)
    midi = (octave + 2) * 12 + NOTE_NAMES.index(name)
    if not 0 <= midi <= 127:
        raise ValueError(f"Note '{value}' converts to MIDI {midi}, outside 0..127.")
    return midi


def midi_to_note(note: int) -> str:
    """Return a Bitwig-style note name, where MIDI 60 == C3."""
    if not 0 <= note <= 127:
        raise ValueError(f"MIDI note out of range: {note}")
    octave = note // 12 - 2
    return f"{NOTE_NAMES[note % 12]}{octave}"


def safe_name(text: str) -> str:
    cleaned = SAFE_NAME_RE.sub("_", text.strip())
    return cleaned.strip("_") or "run"


def parse_int_list(text: str, *, low: int = 0, high: int = 127, label: str = "value") -> list[int]:
    values: list[int] = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        value = int(chunk)
        if not low <= value <= high:
            raise ValueError(f"{label} {value} outside {low}..{high}")
        values.append(value)
    if not values:
        raise ValueError(f"No {label}s provided")
    return sorted(set(values))


def parse_run_layers(spec: str) -> list[tuple[str, int, int]]:
    """Parse a build-runs spec like 'soft:1-50,medium:51-95,hard:96-127'."""
    layers: list[tuple[str, int, int]] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            raise ValueError(f"Invalid run layer '{chunk}'. Use RUN:LOW-HIGH, e.g. soft:1-50.")
        run_name, range_text = chunk.split(":", 1)
        run_name = run_name.strip()
        if not run_name:
            raise ValueError(f"Invalid run layer '{chunk}': missing run name.")
        match = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", range_text)
        if not match:
            raise ValueError(f"Invalid velocity range '{range_text}' for run '{run_name}'. Use LOW-HIGH.")
        low, high = int(match.group(1)), int(match.group(2))
        if not 1 <= low <= high <= 127:
            raise ValueError(f"Velocity range for run '{run_name}' must be inside 1..127 and low <= high.")
        layers.append((run_name, low, high))
    if not layers:
        raise ValueError("No run layers supplied")
    return layers


def sampled_notes(start: int, end: int, step: int) -> list[int]:
    if step < 1:
        raise ValueError("step must be >= 1")
    if start > end:
        raise ValueError("start must be <= end")
    roots = list(range(start, end + 1, step))
    if roots[-1] != end:
        roots.append(end)
    return roots


def centered_ranges(roots: list[int], lower_bound: int, upper_bound: int) -> dict[int, tuple[int, int]]:
    ordered = sorted(roots)
    ranges: dict[int, tuple[int, int]] = {}
    for idx, root in enumerate(ordered):
        low = lower_bound if idx == 0 else math.floor((ordered[idx - 1] + root) / 2) + 1
        high = upper_bound if idx == len(ordered) - 1 else math.floor((root + ordered[idx + 1]) / 2)
        ranges[root] = (max(lower_bound, low), min(upper_bound, high))
    return ranges
