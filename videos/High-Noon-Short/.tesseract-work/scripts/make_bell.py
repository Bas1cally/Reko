"""Synthesize a tower-bell strike (additive, inharmonic church-bell partials) for 'Twelve' at 5.38 s.
Prime A3 (220 Hz) to sit in the song's A-minor/C-major key. Strike transient at t=5 ms."""
import numpy as np, soundfile as sf, os
sr = 48000; dur = 3.6; t = np.arange(int(sr * dur)) / sr
f = 220.0
# (ratio to prime, amplitude, decay seconds, beat Hz)
partials = [(0.5, 0.55, 3.2, 0.4), (1.0, 0.70, 2.6, 0.7), (1.2, 0.45, 2.0, 0.9), (1.5, 0.30, 1.4, 0.0),
            (2.0, 0.85, 1.8, 1.1), (2.5, 0.30, 0.9, 0.0), (2.67, 0.35, 0.8, 1.6), (3.0, 0.25, 0.6, 0.0),
            (4.0, 0.22, 0.45, 2.0), (5.33, 0.12, 0.3, 0.0), (6.4, 0.08, 0.2, 0.0)]
y = np.zeros_like(t); t0 = 0.005
env_on = np.clip((t - t0) / 0.002, 0, 1)
rng = np.random.default_rng(12)
for r, a, dcy, beat in partials:
    ph = rng.uniform(0, 2 * np.pi)
    w = np.sin(2 * np.pi * f * r * t + ph)
    if beat: w = 0.5 * w + 0.5 * np.sin(2 * np.pi * (f * r + beat) * t + ph * 1.3)
    y += a * w * np.exp(-np.maximum(t - t0, 0) / dcy)
# clapper strike: short band-passed noise click
n = rng.standard_normal(len(t)) * np.exp(-np.maximum(t - t0, 0) / 0.008) * (t >= t0)
spec = np.fft.rfft(n); fr = np.fft.rfftfreq(len(n), 1 / sr); spec[(fr < 1500) | (fr > 7000)] = 0
y += 0.35 * np.fft.irfft(spec, len(n))
y *= env_on
y *= 10 ** (-12 / 20) / np.max(np.abs(y))            # -12 dBFS peak, like the skill's helper
fade = int(0.3 * sr); y[-fade:] *= np.linspace(1, 0, fade)
st = np.stack([y, y * 0.97], axis=1)
out = os.path.join(os.path.dirname(__file__), '..', '..', 'Sources', 'sfx', 'bell-strike-A3.wav')
sf.write(out, st.astype(np.float32), sr, subtype='PCM_24')
print('wrote', os.path.abspath(out), 'peak dBFS', round(20 * np.log10(np.max(np.abs(st))), 2))
