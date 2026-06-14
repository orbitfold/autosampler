from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import click

from .audio import normalize_peak, record_hardware_note, simulate_note, trim_audio, wav_frame_count, write_wav
from .models import BuildConfig, SampleConfig, Zone
from .multisample import make_multisample_xml, package_multisample
from .notes import centered_ranges, midi_to_note, note_to_midi, parse_int_list, parse_run_layers, safe_name, sampled_notes


def keyword_list(text: str) -> list[str]:
    return [keyword.strip() for keyword in text.split(",") if keyword.strip()]


def record_samples(config: SampleConfig, *, run_name: str | None = None) -> tuple[list[Zone], dict[str, object]]:
    start = note_to_midi(config.start)
    end = note_to_midi(config.end)
    roots = sampled_notes(start, end, config.step)
    velocities = parse_int_list(config.velocities, low=1, high=127, label="velocity")
    if config.repeats < 1:
        raise ValueError("repeats must be >= 1")

    key_ranges = centered_ranges(roots, start, end)
    vel_ranges = centered_ranges(velocities, 1, 127)
    total = len(roots) * len(velocities) * config.repeats

    display_run = f" run '{run_name}'" if run_name else ""
    click.echo(f"Instrument{display_run}: {config.name}")
    click.echo(
        f"Range: {midi_to_note(start)}..{midi_to_note(end)} ({start}..{end}), "
        f"roots every {config.step} semitones"
    )
    click.echo(f"Root notes: {', '.join(midi_to_note(note) for note in roots)}")
    click.echo(f"MIDI trigger velocities: {velocities}; repeats: {config.repeats}; total WAVs: {total}")

    if config.dry_run:
        for root in roots:
            key_low, key_high = key_ranges[root]
            click.echo(f"  {midi_to_note(root):>4} root {root:3d}: key range {midi_to_note(key_low)}..{midi_to_note(key_high)}")
        return [], {}

    if not config.simulate and not config.midi_out:
        raise ValueError("--midi-out is required unless --simulate is used. Run `python -m autosampler list-devices` first.")

    if run_name:
        target_dir = config.runs_root.expanduser().resolve() / safe_name(run_name)
        samples_dir = target_dir / "Samples"
        if target_dir.exists():
            shutil.rmtree(target_dir)
        samples_dir.mkdir(parents=True, exist_ok=True)
    else:
        target_dir = config.workdir.expanduser().resolve()
        samples_dir = target_dir / "Samples"
        if target_dir.exists():
            shutil.rmtree(target_dir)
        samples_dir.mkdir(parents=True, exist_ok=True)

    zones: list[Zone] = []
    index = 0
    prefix = safe_name(run_name or config.name)

    try:
        for velocity in velocities:
            vel_low, vel_high = vel_ranges[velocity]
            for root in roots:
                key_low, key_high = key_ranges[root]
                for repeat in range(1, config.repeats + 1):
                    index += 1
                    note_label = midi_to_note(root).replace("#", "s")
                    filename = f"{prefix}_{note_label}_v{velocity:03d}_rr{repeat:02d}.wav"
                    click.echo(
                        f"[{index:03d}/{total:03d}] Sampling {midi_to_note(root)} "
                        f"vel {velocity} rr {repeat} -> {filename}"
                    )

                    if config.simulate:
                        data = simulate_note(root, velocity, config.note_length, config.tail, config.sample_rate, config.channels)
                    else:
                        data = record_hardware_note(
                            midi_out_name=config.midi_out or "",
                            channel=config.midi_channel,
                            note=root,
                            velocity=velocity,
                            note_length=config.note_length,
                            tail=config.tail,
                            pre_roll=config.pre_roll,
                            sample_rate=config.sample_rate,
                            channels=config.channels,
                            audio_device=config.audio_device,
                            monitor=config.monitor,
                            monitor_device=config.monitor_device,
                            monitor_gain=config.monitor_gain,
                        )

                    data = trim_audio(data, config.trim_threshold_db, config.trim_padding_ms, config.sample_rate)
                    data = normalize_peak(data, config.normalize_dbfs)
                    frames = write_wav(samples_dir / filename, data, config.sample_rate)
                    zones.append(
                        Zone(
                            root=root,
                            key_low=key_low,
                            key_high=key_high,
                            vel_sample=velocity,
                            vel_low=vel_low,
                            vel_high=vel_high,
                            repeat=repeat,
                            filename=filename,
                            frames=frames,
                            layer_name=run_name or "",
                        )
                    )
    except KeyboardInterrupt:
        click.echo(f"\nInterrupted. Partial WAVs remain in: {samples_dir}", err=True)
        raise click.Abort()

    manifest: dict[str, object] = {
        "schema_version": 3,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_name": run_name or "",
        "name": config.name,
        "creator": config.creator,
        "category": config.category,
        "description": config.description,
        "keywords": keyword_list(config.keywords),
        "start": start,
        "end": end,
        "step": config.step,
        "roots": roots,
        "midi_trigger_velocities": velocities,
        "repeats": config.repeats,
        "sample_rate": config.sample_rate,
        "channels": config.channels,
        "note_length": config.note_length,
        "tail": config.tail,
        "samples": [asdict(zone) for zone in zones],
    }

    if run_name:
        (target_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        click.echo(f"\nRecorded run '{run_name}' into: {target_dir}")
        click.echo("Adjust the synth, record another run, then combine runs with `python -m autosampler build-runs ...`.")
    return zones, manifest


def write_one_shot_multisample(config: SampleConfig, zones: list[Zone]) -> int:
    workdir = config.workdir.expanduser().resolve()
    xml_bytes = make_multisample_xml(
        name=config.name,
        creator=config.creator,
        description=config.description,
        category=config.category,
        keywords=keyword_list(config.keywords),
        zones=zones,
        round_robin=config.repeats > 1,
    )
    (workdir / "multisample.xml").write_bytes(xml_bytes)

    out_path = config.out.expanduser().resolve()
    package_multisample(workdir, out_path)

    click.echo(f"\nCreated: {out_path}")
    click.echo("Drag the .multisample file onto Bitwig Sampler, or import it from Bitwig's browser.")
    if config.keep_workdir:
        click.echo(f"Kept working folder: {workdir}")
    else:
        shutil.rmtree(workdir, ignore_errors=True)
    return 0


def load_run_manifest(runs_root: Path, run_name: str) -> tuple[Path, dict[str, object]]:
    run_dir = runs_root / safe_name(run_name)
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Run '{run_name}' not found: expected {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if int(manifest.get("schema_version", 0)) < 2:
        raise ValueError(f"Run '{run_name}' uses an old/unsupported manifest format. Re-record it with this version.")
    return run_dir, manifest


def build_from_runs(config: BuildConfig) -> int:
    layers = parse_run_layers(config.build_runs)
    runs_root = config.runs_root.expanduser().resolve()
    build_dir = config.workdir.expanduser().resolve()
    samples_out = build_dir / "Samples"

    click.echo(f"Building layered multisample: {config.name}")
    click.echo(f"Runs root: {runs_root}")
    for run_name, low, high in layers:
        click.echo(f"  {run_name}: velocity {low}-{high}")

    if config.dry_run:
        return 0

    if build_dir.exists():
        shutil.rmtree(build_dir)
    samples_out.mkdir(parents=True, exist_ok=True)

    zones: list[Zone] = []
    repeats_seen: set[int] = set()
    sample_rates: set[int] = set()
    channels_seen: set[int] = set()

    for run_name, vel_low, vel_high in layers:
        run_dir, manifest = load_run_manifest(runs_root, run_name)
        sample_rates.add(int(manifest.get("sample_rate", 0)))
        channels_seen.add(int(manifest.get("channels", 0)))
        samples = manifest.get("samples")
        if not isinstance(samples, list) or not samples:
            raise ValueError(f"Run '{run_name}' contains no samples in manifest.json")

        for sample in samples:
            if not isinstance(sample, dict):
                raise ValueError(f"Run '{run_name}' contains an invalid sample entry")
            source_name = str(sample["filename"])
            source_wav = run_dir / "Samples" / source_name
            if not source_wav.exists():
                raise FileNotFoundError(f"Missing WAV for run '{run_name}': {source_wav}")
            dest_name = f"{safe_name(run_name)}__{source_name}"
            shutil.copy2(source_wav, samples_out / dest_name)
            repeat = int(sample.get("repeat", 1))
            repeats_seen.add(repeat)
            frames = int(sample.get("frames") or wav_frame_count(source_wav))
            zones.append(
                Zone(
                    root=int(sample["root"]),
                    key_low=int(sample["key_low"]),
                    key_high=int(sample["key_high"]),
                    vel_sample=int(sample.get("vel_sample", vel_high)),
                    vel_low=vel_low,
                    vel_high=vel_high,
                    repeat=repeat,
                    filename=dest_name,
                    frames=frames,
                    layer_name=f"{run_name} {vel_low}-{vel_high}",
                )
            )

    if len(sample_rates - {0}) > 1:
        click.echo(f"WARNING: runs have mixed sample rates: {sorted(sample_rates)}", err=True)
    if len(channels_seen - {0}) > 1:
        click.echo(f"WARNING: runs have mixed channel counts: {sorted(channels_seen)}", err=True)

    xml_bytes = make_multisample_xml(
        name=config.name,
        creator=config.creator,
        description=config.description,
        category=config.category,
        keywords=keyword_list(config.keywords),
        zones=zones,
        round_robin=max(repeats_seen or {1}) > 1,
    )
    (build_dir / "multisample.xml").write_bytes(xml_bytes)

    out_path = config.out.expanduser().resolve()
    package_multisample(build_dir, out_path)

    click.echo(f"\nCreated layered multisample: {out_path}")
    click.echo("Each recorded run is now mapped to its requested velocity range.")
    if config.keep_workdir:
        click.echo(f"Kept build folder: {build_dir}")
    else:
        shutil.rmtree(build_dir, ignore_errors=True)
    return 0
