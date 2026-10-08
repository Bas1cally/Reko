# Checks

Before any paid step:

- [ ] Scenario project confirmed with the user; models picked with `recommend` and `search`, schemas read.
- [ ] Every distinct request priced with `model_run` and `dry_run=true`; the total told to the user and agreed.
- [ ] Their files uploaded with `upload_asset`; `model_run` gets asset ids only.

First frames:

- [ ] Each figure faces the way its slot says, on a flat key-colour background, same baseline.
- [ ] Figure at about 58% of the frame height with room above the head for a raised weapon (`reframe.py`).
- [ ] `reframe.py` key check under 1% for the chosen key, and `key` set in `cast.json` before the prompts.
- [ ] S and N symmetric against a vertical centre line: head and chest or spine on the line, shoulders level, both arms equally visible.
- [ ] Props on the same side of the image as in the diagonals (`turn_notes`); a prop the body hides is not reinvented.
- [ ] Their own art: turnarounds shown next to it; nothing changed in design, palette or pixel size.

Clips (one hero first, a contact sheet of frames):

- [ ] Every clip holds its facing for the whole clip: diagonals never go side-on, E/W stay in profile, S and N stay straight on.
- [ ] The N walk steps away from us, not backwards.
- [ ] The character stays centred; no camera move; no glow or light on the backdrop around a glowing prop.
- [ ] Aimed attacks aim along the facing (at the camera for S, up the screen for N).

Sheets:

- [ ] Seam scores read: walk and run under 0.8, or widened and re-run; idles checked in the GIF.
- [ ] Widest-stride frames twice per walk or run row, evenly spaced (no 1.5-stride loop).
- [ ] No pop at the loop point, no key-colour fringe, no weapon clipped at the cell edge.
- [ ] Identity the same across facings; mirrored rows read as the same hero.
- [ ] 8 directions: `compass_gif.py` preview shows every row the same height and a believable speed; `size_bias` or `fps_scale` only as nudges.
- [ ] Hand-over: sheets plus `meta.json` (cell, pivot, rows, per-facing fps) and the engine import notes from [sprite-sheets.md](sprite-sheets.md).
