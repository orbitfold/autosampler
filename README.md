# ARP 2600 AutoSampler for Bitwig

A standard Python project for automatically sampling a MIDI-controlled hardware synth, recording one WAV per note/velocity/round-robin take, and exporting a Bitwig/PreSonus `.multisample` file.

It was written for an ARP 2600 controlled over MIDI, but it works with any MIDI synth whose audio is connected to your audio interface.

## Project layout

```text
autosampler/
  __main__.py          # enables python -m autosampler ...
  cli.py              # Click command-line interface
  recorder.py         # sampling/build orchestration
  audio.py            # recording, trimming, normalization, WAV writing
  devices.py          # MIDI/audio device listing
  multisample.py      # Bitwig/PreSonus .multisample XML + ZIP packaging
  notes.py            # note-name parsing and key-range calculation
pyproject.toml
README.md
```

## What it exports

- `Samples/*.wav` inside the package
- `multisample.xml` at the package root
- ZIP container with `.multisample` extension
- Uncompressed ZIP entries, as recommended by the Bitwig/PreSonus multisample spec

Note-name parsing uses the Bitwig convention: **MIDI note 60 is C3**.

## Install

From this folder:

```bash
python3 -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\Activate.ps1     # Windows PowerShell
pip install -e .
```

This installs the package and also creates a console command named `autosampler`.

You can run either form:

```bash
python -m autosampler --help
autosampler --help
```

On Linux you may also need PortAudio/JACK/ALSA development packages for `sounddevice`.

## Find MIDI and audio devices

```bash
python -m autosampler list-devices
```

Copy the exact MIDI output port name that feeds your ARP 2600 MIDI/CV interface or ARP 2600 MIDI input.

## One-shot multisample

This records all requested velocity layers in one pass and immediately writes a `.multisample` file:

```bash
python -m autosampler record \
  --midi-out "Your MIDI Port Name" \
  --audio-device 0 \
  --name "ARP 2600 Bass Patch" \
  --start C1 \
  --end C5 \
  --step 3 \
  --velocities 64,100,127 \
  --repeats 2 \
  --note-length 2.5 \
  --tail 1.0 \
  --channels 2 \
  --out "ARP_2600_Bass.multisample"
```

This records:

- sampled root keys from C1 to C5, three semitones apart
- three MIDI velocity layers
- two round-robin takes per key/velocity
- stereo 48 kHz, 24-bit WAV files
- a final `.multisample` package that Bitwig can load

## Manual synth-setting velocity layers

This workflow lets you run the sampler multiple times, adjust the ARP 2600 settings between runs, and then map each run to a different final velocity layer.

Record the soft layer:

```bash
python -m autosampler record-run soft \
  --midi-out "Your MIDI Port Name" \
  --audio-device 0 \
  --start C1 \
  --end C5 \
  --step 3 \
  --velocities 100
```

Adjust the ARP 2600 panel, then record the medium layer:

```bash
python -m autosampler record-run medium \
  --midi-out "Your MIDI Port Name" \
  --audio-device 0 \
  --start C1 \
  --end C5 \
  --step 3 \
  --velocities 100
```

Adjust the panel again, then record the hard layer:

```bash
python -m autosampler record-run hard \
  --midi-out "Your MIDI Port Name" \
  --audio-device 0 \
  --start C1 \
  --end C5 \
  --step 3 \
  --velocities 100
```

Build one Bitwig multisample from those runs:

```bash
python -m autosampler build-runs soft:1-50,medium:51-95,hard:96-127 \
  --name "ARP 2600 Layered Patch" \
  --out "ARP_2600_Layered.multisample"
```

Important distinction:

- `--velocities 100` in `record-run` is the MIDI trigger velocity during recording.
- `build-runs soft:1-50,medium:51-95,hard:96-127` defines the final sampler velocity zones.

Recorded runs are stored in `autosampler_runs/<run-name>/` with a `manifest.json` and a `Samples/` folder.

## Test without hardware

Use `--simulate` to generate test tones instead of triggering MIDI/recording audio:

```bash
python -m autosampler record \
  --simulate \
  --start C3 \
  --end G3 \
  --step 7 \
  --velocities 80,120 \
  --out test_single.multisample
```

Layered simulated test:

```bash
python -m autosampler record-run soft --simulate --start C3 --end G3 --step 7 --velocities 100
python -m autosampler record-run hard --simulate --start C3 --end G3 --step 7 --velocities 100
python -m autosampler build-runs soft:1-80,hard:81-127 --out test_layered.multisample
```

## Useful options

```text
--start / --end          note range to cover
--step                   gap between sampled root notes, in semitones
--velocities             MIDI note-on velocities to trigger while recording
--repeats                round-robin takes per sampled note
--note-length            sustain time before MIDI note_off
--tail                   release/tail capture time
--pre-roll               recording time before MIDI note_on
--trim-threshold-db      silence trimming threshold
--trim-padding-ms        silence trimming padding
--normalize-dbfs         per-sample peak normalization target
--no-normalize           disable normalization
--simulate               generate test tones without hardware
--dry-run                show the sampling/build plan without recording/building
--runs-root              folder used for manual multi-run layering
```

## Notes and limitations

- The ARP 2600 has no patch memory, so the `record-run` workflow is designed around manual panel changes.
- The script currently does not auto-detect loops. Loop points are possible in the `.multisample` format, but this tool focuses on one-shot sustained samples with release tails.
- If your MIDI/CV interface ignores velocity, that is fine for the manual layering workflow: the velocity difference comes from your panel changes, not from MIDI velocity.
