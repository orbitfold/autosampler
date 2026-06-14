from autosampler.notes import centered_ranges, midi_to_note, note_to_midi, parse_run_layers, sampled_notes


def test_bitwig_note_convention():
    assert note_to_midi("C3") == 60
    assert midi_to_note(60) == "C3"
    assert note_to_midi("Bb2") == 58


def test_sampled_notes_includes_final_note():
    assert sampled_notes(60, 67, 3) == [60, 63, 66, 67]


def test_centered_ranges():
    assert centered_ranges([60, 63, 67], 60, 67) == {
        60: (60, 61),
        63: (62, 65),
        67: (66, 67),
    }


def test_parse_run_layers():
    assert parse_run_layers("soft:1-50,hard:51-127") == [("soft", 1, 50), ("hard", 51, 127)]
