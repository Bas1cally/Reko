# High Noon – Short (Nemmysis) · Projektnotizen

Aktuelle Revision: **r2** – `High-Noon.tsrct` ↔ `High-Noon.mp4` (gleicher Stand).
Brief: 21,17 s, 9:16, letzter Refrain (Song 2:32,4–2:53,57), Schnitte auf dem Beat,
Wort-für-Wort-Gold-Lyrics, Titel ab Drum-Einsatz, alles aus MP3 + Referenzblatt in Code gebaut.

## Aufbau (Projekt-Ebenen)
| Shot | Zeit (s) | Inhalt | Bewegung |
| --- | --- | --- | --- |
| S1 Main Street | 0,00–1,30 | gezeichnete Stadt, Sonne im Zenit, Tumbleweed | Parallax-Schwenk, Tumbleweed landet auf den Beats 0,248 / 0,782 |
| S2 Nemmy | 1,30–4,53 | Referenzkachel → Pixel-Art, Figur freigestellt | langsamer Drift, Figur 4 px Parallaxe |
| S3 Uhrturm | 4,53–7,20 | Turm, Zifferblatt, Glocke, 4 Krähen | Zeiger 11:59 → 12:00, Glocke schwingt aus, Krähen fliegen auf, **Shake bei 5,38** |
| S4 Yumi | 7,20–8,83 | wie S2 | Drift gegenläufig |
| S5 Aiko | 8,83–12,57 | wie S2 | Drift |
| S6 Bär (Drums) | 12,57–14,20 | ganze Kachel (Drumkit nicht freistellbar) | Drift |
| S7 Band | 14,20–21,17 | Band auf der Main Street | Tilt Sonne → Band (14,6–18,4), Tumbleweed-Callback, **Shake 18,92**, Kopfnicken auf den Beats danach |
| Titel | 18,92–21,17 | HIGH NOON (Gold + Dunkelgold-Extrusion), NEMMYSIS (Creme) | Buchstaben erscheinen ab 18,92 bzw. 19,54 (nächster Beat) |
| Fade | 20,82–21,17 | Bild auf Schwarz, Song-Lautstärke auf 0 | |

Pixelraster: 1 Kunst-Pixel = 6×6 Bildpixel (180×320). Alle Bilder in 100 % Größe, alle Positionen
per Skript auf ganze Kunst-Pixel gerundet → keine Skalierung, keine Zwischenpixel (geprüft: 100 %
rasterbündige 6×6-Blöcke bei 0,65 / 3,0 / 5,43 / 10,7 / 16,8 / 19,97 s, also auch in Schwenk, Tilt und Shake).

## Lyrics-Wort-Timings (geschätzt – bitte prüfen)
Nicht angehört (keine Audiowiedergabe in dieser Umgebung). Abgeleitet aus Beat-Raster (112,3 BPM,
Takt-Einsen 1,85 + n·2,136 s), Tonhöhen-Segmenten des Gesangs und dem Anker „Twelve“ = 5,38 s.
Änderbar in `scripts/build_project.py` → `LYRICS`, dann Projekt neu bauen.

| Zeile (Fenster) | Wort-Einsätze in s |
| --- | --- |
| High noon, high noon, / meet me there (1,45–4,65) | High 1,60 · noon 1,88 · high 2,72 · noon 2,93 · meet 3,46 · me 3,73 · there 3,98 |
| Twelve o'clock, / if you dare (5,15–8,90) | Twelve 5,38 · o'clock 5,61 · if 7,72 · you 8,00 · dare 8,28 |
| Hands up, / here it comes (8,90–12,55) | Hands 9,13 · up 9,36 · here 11,49 · it 11,75 · comes 12,02 |
| No place to run (12,60–14,22) | No 12,70 · place 13,11 · to 13,37 · run 13,65 |
| High noon, high noon, / here I come (14,30–19,55) | High 14,47 · noon 14,72 · high 15,57 · noon 16,16 · here 18,17 · I 18,47 · come 18,94 |

## Ton
- Song: MP3 ab 152,423 s (152,4 + 23 ms MP3-Encoder-Delay, den Tesseracts Decoder nicht abzieht;
  ohne Korrektur lag die Musik 23 ms zu spät). Unity-Gain, Fade 20,82–21,17. Geprüft per
  Kreuzkorrelation gegen den ffmpeg-Ausschnitt: Versatz ±0,02 ms an drei Stellen.
- Glocke: `Sources/sfx/bell-strike-A3.wav`, synthetisiert (`scripts/make_bell.py`, Kirchenglocken-
  Teiltöne auf A3), Schlag bei 5,380 s (gemessen), ~5 dB unter dem Songpegel. Im Song selbst war
  bei 5,38 s keine Glocke erkennbar (`checks/bell-check.png`).
- Master: −15,13 LUFS integriert, −3,58 dBTP (`checks/loudness-v2.json`). Nicht angehört.

## Geprüft
- ffprobe: H.264 High 1080×1920, 30 fps, 635 Frames, 21,167 s; AAC 48 kHz Stereo; keine Song-Metadaten im MP4.
- Schnitte (`checks/v2-cuts.png`): Wechsel exakt auf 1,30 / 4,53 / 7,20 / 8,83 / 12,57 / 14,20 s.
- Helligkeit pro Frame: Sprünge nur an Schnittframes, keine Schwarz- oder Blitzframes.
- Filmstreifen: `checks/s1-motion.png`, `checks/s3-strike.png`, `checks/s7-finale.png`, `../Previews/Filmstrip.png`.

## Offen / Grenzen
- Wort-Timings und Glockenklang nicht angehört → Tabelle oben vom Nutzer bestätigen lassen.
- Bei Nemmy im Band-Shot bleibt am Haarrand ein dünner hellgrauer Saum (Rest des Sonnen-Halos der Kachel).
- Tesseract CLI 0.2.0: variabler Font (PixelifySans[wght]) macht das Projekt unlesbar → statische
  Bold-Instanz `Sources/fonts/PixelifySans-Bold.ttf` (fontTools, wght 700) wird importiert.

## Neu bauen
```sh
python3 -m venv venv && venv/bin/pip install -r .tesseract-work/scripts/requirements.txt
cd videos/High-Noon-Short
venv/bin/python .tesseract-work/scripts/crop_tiles.py        # Referenzblatt → Kacheln
U2NET_HOME=… venv/bin/python .tesseract-work/scripts/segment_tiles.py   # Masken (bereits in art-src)
venv/bin/python .tesseract-work/scripts/build_palette.py
venv/bin/python .tesseract-work/scripts/build_solo.py
venv/bin/python .tesseract-work/scripts/build_street.py
venv/bin/python .tesseract-work/scripts/build_clock.py
venv/bin/python .tesseract-work/scripts/build_band.py
venv/bin/python .tesseract-work/scripts/make_bell.py
venv/bin/python .tesseract-work/scripts/build_project.py     # → High-Noon.tsrct
tsrct export --project High-Noon.tsrct --output High-Noon.mp4 \
  --encoder-backend external-ffmpeg-command --ffmpeg-path /usr/bin/ffmpeg
```
