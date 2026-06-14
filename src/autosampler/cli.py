from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, TypeVar

import click

from .devices import audio_devices_text, list_midi_outputs
from .models import BuildConfig, SampleConfig
from .recorder import build_from_runs, record_samples, write_one_shot_multisample

F = TypeVar("F", bound=Callable[..., object])
DEFAULT_CREATOR = os.environ.get("USER") or os.environ.get("USERNAME") or ""


def sampling_options(func: F) -> F:
    options = [
        click.option("--midi-out", help="MIDI output port name connected to the synth."),
        click.option("--audio-device", help="Audio input device index/name. Omit for default input."),
        click.option("--monitor",
                     is_flag=True,
                     help="Pass the audio input through an output device while sampling.",
        ),
        click.option("--monitor-device",
                     help="Audio output device index/name for software monitoring. Omit for default output.",
        ),
        click.option("--monitor-gain",
                     default=1.0,
                     show_default=True,
                     type=float,
                     help="Software monitor gain multiplier. Does not affect saved WAVs."
        ),
        click.option("--midi-channel", default=1, show_default=True, type=click.IntRange(1, 16), help="MIDI channel."),
        click.option("--start", default="C1", show_default=True, help="Lowest key to cover, e.g. C1 or 36. Bitwig convention: C3 == 60."),
        click.option("--end", default="C5", show_default=True, help="Highest key to cover, e.g. C5 or 84."),
        click.option("--step", default=3, show_default=True, type=click.IntRange(1, 127), help="Gap between sampled root notes in semitones."),
        click.option(
            "--velocities",
            default="100",
            show_default=True,
            help=(
                "Comma-separated MIDI note-on velocities to record. "
                "For manual multi-run layering, usually keep this as one trigger velocity and use build-runs for final velocity zones."
            ),
        ),
        click.option("--repeats", default=1, show_default=True, type=click.IntRange(1, 999), help="Round-robin repetitions per note/velocity."),
        click.option("--note-length", default=2.5, show_default=True, type=float, help="Seconds to hold each MIDI note before note_off."),
        click.option("--tail", default=1.0, show_default=True, type=float, help="Seconds to record after note_off."),
        click.option("--pre-roll", default=0.05, show_default=True, type=float, help="Seconds to record before note_on."),
        click.option("--sample-rate", default=48000, show_default=True, type=int, help="Recording sample rate."),
        click.option("--channels", default=2, show_default=True, type=click.IntRange(1, 2), help="Audio channels to record."),
        click.option("--trim-threshold-db", default=-60.0, show_default=True, type=float, help="Trim leading/trailing audio below this peak threshold."),
        click.option("--trim-padding-ms", default=20.0, show_default=True, type=float, help="Trim padding in milliseconds."),
        click.option("--normalize-dbfs", default=-3.0, show_default=True, type=float, help="Per-sample peak normalization target."),
        click.option("--no-normalize", is_flag=True, help="Disable peak normalization."),
        click.option("--name", default="ARP 2600 Autosample", show_default=True, help="Multisample/instrument name."),
        click.option("--creator", default=DEFAULT_CREATOR, show_default=True, help="Creator metadata."),
        click.option("--category", default="Synth", show_default=True, help="Category metadata."),
        click.option("--description", default="Auto-sampled hardware synth patch", show_default=True, help="Description metadata."),
        click.option("--keywords", default="ARP 2600,Hardware,Synth", show_default=True, help="Comma-separated keyword metadata."),
        click.option("--workdir", default=Path("autosampler_work"), show_default=True, type=click.Path(file_okay=False, path_type=Path), help="Temporary/output working folder for WAVs and XML."),
        click.option("--keep-workdir", is_flag=True, help="Keep the working folder after packaging/building."),
        click.option("--simulate", is_flag=True, help="Generate test tones instead of using MIDI/audio hardware."),
        click.option("--dry-run", is_flag=True, help="Print the sampling/build plan and exit."),
        click.option("--runs-root", default=Path("autosampler_runs"), show_default=True, type=click.Path(file_okay=False, path_type=Path), help="Folder used by record-run and build-runs."),
    ]
    for option in reversed(options):
        func = option(func)  # type: ignore[assignment]
    return func


def make_sample_config(**kwargs: object) -> SampleConfig:
    no_normalize = bool(kwargs.pop("no_normalize"))
    normalize_dbfs = None if no_normalize else float(kwargs.pop("normalize_dbfs"))
    kwargs.setdefault("out", Path("unused.multisample"))
    kwargs["normalize_dbfs"] = normalize_dbfs
    kwargs["channels"] = int(kwargs["channels"])
    kwargs["monitor_gain"] = float(kwargs["monitor_gain"])
    return SampleConfig(**kwargs)  # type: ignore[arg-type]


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option()
def cli() -> None:
    """Auto-sample a MIDI hardware synth and export Bitwig .multisample files."""


@cli.command("list-devices")
def list_devices_command() -> None:
    """List MIDI outputs and audio devices."""
    click.echo("MIDI outputs:")
    for name in list_midi_outputs():
        click.echo(f"  {name}")
    click.echo("\nAudio devices:")
    click.echo(audio_devices_text())


@cli.command()
@click.option("--out", default=Path("ARP2600_Autosample.multisample"), show_default=True, type=click.Path(dir_okay=False, path_type=Path), help="Output .multisample path.")
@sampling_options
def record(**kwargs: object) -> None:
    """Record a complete one-shot multisample and package it immediately."""
    try:
        config = make_sample_config(**kwargs)
        zones, _manifest = record_samples(config)
        if config.dry_run:
            return
        write_one_shot_multisample(config, zones)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command("record-run")
@click.argument("run_name")
@sampling_options
def record_run(run_name: str, **kwargs: object) -> None:
    """Record one pass into autosampler_runs/RUN_NAME for later velocity-layer building."""
    try:
        config = make_sample_config(**kwargs)
        record_samples(config, run_name=run_name)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command("build-runs")
@click.argument("spec")
@click.option("--name", default="ARP 2600 Layered Patch", show_default=True, help="Multisample/instrument name.")
@click.option("--creator", default=DEFAULT_CREATOR, show_default=True, help="Creator metadata.")
@click.option("--category", default="Synth", show_default=True, help="Category metadata.")
@click.option("--description", default="Layered auto-sampled hardware synth patch", show_default=True, help="Description metadata.")
@click.option("--keywords", default="ARP 2600,Hardware,Synth", show_default=True, help="Comma-separated keyword metadata.")
@click.option("--out", default=Path("ARP2600_Layered.multisample"), show_default=True, type=click.Path(dir_okay=False, path_type=Path), help="Output .multisample path.")
@click.option("--workdir", default=Path("autosampler_work"), show_default=True, type=click.Path(file_okay=False, path_type=Path), help="Temporary build folder for WAVs and XML.")
@click.option("--keep-workdir", is_flag=True, help="Keep the temporary build folder after packaging.")
@click.option("--dry-run", is_flag=True, help="Print the build plan and exit.")
@click.option("--runs-root", default=Path("autosampler_runs"), show_default=True, type=click.Path(file_okay=False, path_type=Path), help="Folder containing recorded runs.")
def build_runs_command(**kwargs: object) -> None:
    """Build a layered multisample from recorded runs. SPEC: soft:1-50,medium:51-95,hard:96-127."""
    try:
        config = BuildConfig(build_runs=kwargs.pop("spec"), **kwargs)  # type: ignore[arg-type]
        build_from_runs(config)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
