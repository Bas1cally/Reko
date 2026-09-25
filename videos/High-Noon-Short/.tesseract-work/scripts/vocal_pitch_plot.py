"""Plot foreground-estimate spectrogram + pYIN pitch with lyric windows for manual word-timing review."""
import librosa, numpy as np, json, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
y, sr = librosa.load('.tesseract-work/audio/foreground-estimate.wav', sr=22050)
f0, vflag, vprob = librosa.pyin(y, fmin=90, fmax=900, sr=sr, frame_length=2048, hop_length=256)
t = librosa.times_like(f0, sr=sr, hop_length=256)
np.save('.tesseract-work/audio/pyin.npy', np.vstack([t, np.nan_to_num(f0), vprob]))
S = librosa.amplitude_to_db(np.abs(librosa.stft(y, n_fft=2048, hop_length=256)), ref=np.max)
lines=[(1.45,4.65,'High noon, high noon, / meet me there'),(5.15,8.90,"Twelve o'clock, if you dare"),
       (8.90,12.55,'Hands up, here it comes'),(12.60,14.22,'No place to run'),(14.30,19.55,'High noon, high noon, / here I come')]
beats=np.arange(-0.286, 21.2, 0.534)
fig, axes = plt.subplots(4,1, figsize=(22,16))
spans=[(0,5.5),(5,10.5),(10,15.5),(14,21.17)]
for ax,(a,b) in zip(axes,spans):
    fr=(t>=a)&(t<=b)
    ax.imshow(S[:180, fr], origin='lower', aspect='auto', extent=[t[fr][0], t[fr][-1], 0, 180*sr/2048], cmap='magma', vmin=-60)
    ax2=ax.twinx(); ax2.plot(t[fr], np.where(vprob[fr]>0.3, f0[fr], np.nan), 'c-', lw=2.5); ax2.set_ylim(80,700); ax2.set_yscale('log')
    for bt in beats:
        if a<=bt<=b: ax.axvline(bt, color='w', lw=0.6, alpha=0.5)
    for la,lb,txt in lines:
        if lb>a and la<b: ax.axvspan(max(la,a),min(lb,b), color='lime', alpha=0.08); ax.text(max(la,a)+0.02, 1850, txt, color='lime', fontsize=11)
    ax.set_xlim(a,b); ax.set_xticks(np.arange(np.ceil(a*10)/10, b, 0.1), minor=True); ax.set_xticks(np.arange(np.ceil(a*2)/2, b, 0.5)); ax.grid(which='minor', axis='x', alpha=0.15)
plt.tight_layout(); plt.savefig('.tesseract-work/checks/vocal-pitch.png', dpi=70)
# voiced segments
seg=[]; on=None
for i,(tt,v,f) in enumerate(zip(t,vprob,f0)):
    voiced = v>0.3 and not np.isnan(f)
    if voiced and on is None: on=i
    if (not voiced or i==len(t)-1) and on is not None:
        if t[i]-t[on]>0.06: seg.append((round(float(t[on]),3), round(float(t[i]),3), round(float(np.nanmedian(f0[on:i])),1)))
        on=None
print('voiced segments (start,end,f0):'); print(seg)
