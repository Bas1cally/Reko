"""Rough vocal/foreground separation (REPET-SIM style) and onset candidates.
Heuristic only: used to propose word timings for review, not a transcription."""
import librosa, numpy as np, soundfile as sf, json, sys
y, sr = librosa.load('.tesseract-work/audio/excerpt.wav', sr=22050, mono=True)
S_full, phase = librosa.magphase(librosa.stft(y, n_fft=2048, hop_length=256))
S_filter = librosa.decompose.nn_filter(S_full, aggregate=np.median, metric='cosine',
                                       width=int(librosa.time_to_frames(2, sr=sr, hop_length=256)))
S_filter = np.minimum(S_full, S_filter)
margin_v, power = 10, 2
mask_v = librosa.util.softmask(S_full - S_filter, margin_v * S_filter, power=power)
S_fg = mask_v * S_full
y_fg = librosa.istft(S_fg * phase, hop_length=256)
sf.write('.tesseract-work/audio/foreground-estimate.wav', y_fg, sr)
# vocal-band onset envelope on the foreground
freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
band = (freqs > 250) & (freqs < 3500)
Sb = S_fg[band]
env = librosa.onset.onset_strength(S=librosa.amplitude_to_db(Sb, ref=np.max), sr=sr, hop_length=256)
on = librosa.onset.onset_detect(onset_envelope=env, sr=sr, hop_length=256, units='time', backtrack=False, delta=0.08, wait=4)
t = librosa.frames_to_time(np.arange(len(env)), sr=sr, hop_length=256)
rms = np.sqrt((Sb**2).mean(axis=0))
json.dump({'onsets': [round(float(x),3) for x in on],
           'env_t': [round(float(x),3) for x in t[::2]], 'env': [round(float(x),3) for x in env[::2]],
           'rms': [round(float(x),5) for x in rms[::2]]}, open('.tesseract-work/audio/vocal-onsets.json','w'))
lines=[(1.45,4.65,'High noon, high noon, / meet me there'),(5.15,8.90,"Twelve o'clock, if you dare"),
       (8.90,12.55,'Hands up, here it comes'),(12.60,14.22,'No place to run'),(14.30,19.55,'High noon, high noon, / here I come')]
for a,b,txt in lines:
    o=[x for x in on if a-0.3<=x<=b]
    strength=[float(env[librosa.time_to_frames(x,sr=sr,hop_length=256)]) for x in o]
    print(f'{a:5.2f}-{b:5.2f} {txt}\n   onsets: '+', '.join(f'{x:.2f}({s:.1f})' for x,s in zip(o,strength)))
