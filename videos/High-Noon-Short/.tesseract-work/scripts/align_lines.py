"""Forced-align known lyric lines with PocketSphinx (bundled en-us model) inside each line window.
Sung vocals over a band: results are candidates for review only."""
import sys, numpy as np, soundfile as sf, librosa
from pocketsphinx import Decoder
src = sys.argv[1]
y, sr = librosa.load(src, sr=16000, mono=True)
lines=[(1.30,4.70,'high noon high noon meet me there'),(5.00,8.95,"twelve o'clock if you dare"),
       (8.80,12.60,'hands up here it comes'),(12.50,14.28,'no place to run'),(14.20,19.70,'high noon high noon here i come')]
for a,b,txt in lines:
    seg = y[int(a*sr):int(b*sr)]
    pcm = (np.clip(seg,-1,1)*32767).astype(np.int16).tobytes()
    d = Decoder(samprate=16000, bestpath=False)
    d.set_align_text(txt)
    d.start_utt(); d.process_raw(pcm, full_utt=True); d.end_utt()
    words=[]
    for s in d.seg():
        if s.word in ('<sil>','[NOISE]','<s>','</s>'): continue
        words.append(f"{s.word}@{a+s.start_frame/100:.2f}-{a+s.end_frame/100:.2f}")
    print(f'{a:.2f}-{b:.2f}: ' + '  '.join(words))
