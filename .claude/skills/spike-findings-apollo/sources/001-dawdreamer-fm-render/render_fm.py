"""Spike 001: render a short MIDI 'call' phrase through a Faust FM patch — no Ableton.

Proves: DawDreamer + a Faust 2-operator FM engine can deterministically render
MIDI -> call.wav headlessly on Apple Silicon, with timbre controlled by FM params
(ratio, index). This is the renderer-path replacement for manual Operator bounces.
"""
import sys
import numpy as np
import soundfile as sf
import dawdreamer as dd

SR = 44100
BLOCK = 512
DUR = 1.5  # seconds — Apollo's gesture length (0.5-1.5s)

# Minimal polyphonic 2-op FM. DawDreamer wires MIDI -> freq/gain/gate automatically.
# ratio/index are the timbre knobs (the FM analogue of an Operator preset).
FM_DSP = """
import("stdfaust.lib");
freq  = hslider("freq",  440, 20, 20000, 0.01);
gain  = hslider("gain",  0.5,  0,     1, 0.01);
gate  = button("gate");
ratio = hslider("ratio", 2.0, 0.5,    12, 0.01);
index = hslider("index", 2.0, 0.0,    12, 0.01);
env   = en.adsr(0.005, 0.12, 0.7, 0.2, gate);
mod   = os.osc(freq * ratio) * index * freq;
car   = os.osc(freq + mod);
process = car * env * gain <: _,_;
"""

# A tiny monophonic call: 4 notes, quantized, within the 1.5s window.
CALL = [  # (midi_pitch, velocity, start_s, dur_s)
    (60, 100, 0.00, 0.30),
    (63,  90, 0.35, 0.30),
    (67, 110, 0.70, 0.30),
    (62,  80, 1.05, 0.40),
]


def render(ratio: float, index: float, out_path: str) -> np.ndarray:
    engine = dd.RenderEngine(SR, BLOCK)
    synth = engine.make_faust_processor("fm")
    synth.set_dsp_string(FM_DSP)
    synth.num_voices = 8  # polyphony so overlapping releases don't cut
    # Set the timbre knobs on every voice via the parameter path.
    # Param indices from get_parameters_description(): 0=index, 1=ratio.
    synth.set_parameter(1, ratio)
    synth.set_parameter(0, index)
    for pitch, vel, start, dur in CALL:
        synth.add_midi_note(pitch, vel, start, dur)
    engine.load_graph([(synth, [])])
    engine.render(DUR)
    audio = engine.get_audio()  # shape (channels, samples)
    sf.write(out_path, audio.T, SR)
    return audio


if __name__ == "__main__":
    # Render two contrasting timbres + a determinism check on the first.
    presets = {
        "callA_ratio2_index2.wav":  (2.0, 2.0),   # mellow-ish
        "callB_ratio3_index8.wav":  (3.0, 8.0),   # bright/clangorous
    }
    rendered = {}
    for name, (ratio, index) in presets.items():
        a = render(ratio, index, name)
        rendered[name] = a
        peak = float(np.max(np.abs(a)))
        rms = float(np.sqrt(np.mean(a ** 2)))
        print(f"{name}: shape={a.shape} peak={peak:.4f} rms={rms:.5f}")

    # Determinism: render preset A again, compare bit-for-bit.
    a1 = rendered["callA_ratio2_index2.wav"]
    a2 = render(2.0, 2.0, "_det_check.wav")
    identical = np.array_equal(a1, a2)
    maxdiff = float(np.max(np.abs(a1 - a2)))
    print(f"determinism: identical={identical} maxdiff={maxdiff:.2e}")

    # Timbre actually differs between presets?
    A = rendered["callA_ratio2_index2.wav"]
    B = rendered["callB_ratio3_index8.wav"]
    diff = float(np.max(np.abs(A - B)))
    print(f"A vs B differ: maxdiff={diff:.4f} (should be >> 0)")

    ok = identical and diff > 0.01 and float(np.max(np.abs(A))) > 0.001
    print("VERDICT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
