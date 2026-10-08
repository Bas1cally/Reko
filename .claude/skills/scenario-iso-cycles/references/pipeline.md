# Pipeline decisions

Why the route is shaped the way it is, and what each local step does with the numbers that matter.
The failures behind these decisions are in [lessons.md](lessons.md).

## Why three kinds of tool

No single model does it. A pixel-art animation model only does cardinal 4-frame walks. An image model
asked for a pose sheet keeps identity but the legs barely move. A video model gives real motion
(airborne run frames, follow-through) but needs a clean first frame, and its output needs a loop cut
and a pixel finish. So: an image model for the look, an image-to-video model for the motion, and
deterministic local code for everything else (key, loop, size, pixelate, mirror). The local code is
free and repeatable, so tuning happens there, not in new generations.

## First frames

- **One design, many facings.** From text, both diagonals are drawn in one image (SE left, NE right)
  so the identity matches. Every other facing is a single-pose turnaround drawn from every first frame
  already uploaded (up to 4 references). Their own art is always the master: generated facings are
  drawn from it and checked against it, never the other way round.
- **Headroom.** `reframe.py` puts the figure at 58% of a 960x960 key-colour canvas with the feet at
  82%, so a raised weapon stays inside the clip. A pose sheet is cut at the emptiest column near each
  equal split, so a wide pose is not sliced into its neighbour.
- **Their art.** Transparency or a flat backdrop is read automatically; only backdrop colour connected
  to the border is removed (white armour on white survives), plus flat patches of the exact backdrop
  colour enclosed by the figure (between arm and body). Small pixel art is scaled up nearest-neighbour
  at a whole-number factor; the script prints its native height and colour count for `height` and
  `palette`.
- **Key colour.** Magenta by default. `reframe.py` prints how much of the figure each key would erase;
  above 1% it recommends another. Set `key` before making prompts.
- **Upload.** Every first frame goes up with `upload_asset` (then `upload_asset_complete`); its asset
  id goes into `stills`. `model_run` takes asset ids, never local paths or URLs.

## Mirroring

SW, NW and W are horizontal flips of SE, NE and E: standard practice and half the work. A flip swaps
sides (sword hand, eyepatch, one pauldron, lettering); for an asymmetric character list the mirrored
facings in `facings` so they are generated. Their own art: use `--flip` in `reframe.py` only for a
symmetric character.

## Clips

One clip per facing and cycle, square, audio off, on the key colour. The recipes and why each sentence
is there: [prompts.md](prompts.md). Run one hero's clips first and look at them (a contact sheet of
frames is enough) before submitting the rest. Record job ids in `jobs.json` as you submit, wait with
`jobs_wait` (at most 32 ids per call), and `asset_download` each to `clips/<hero>_<facing>_<cycle>.mp4`.

## Processing (`process.py`)

1. **Read.** Each clip's own frame rate and size are probed; non-square clips are padded with the key
   colour (feet kept on the bottom edge), not stretched, then scaled to the 960 canvas.
2. **Key.** The key-colour field, including the ground shadow the video model adds, goes to alpha;
   the remaining tint is pulled out of kept pixels (despill).
3. **Loop window** (walk, run, idle). Every start (from frame 3) and every period P in the cycle's
   range (24 fps frames, rescaled to the clip's rate) is scored: the difference between frame s and
   s+P divided by the mean frame-to-frame motion inside the window. The lowest ratio wins; 8 frames are
   sampled evenly across it. Defaults: walk 12 to 34, run 8 to 24, idle 24 to 66; per hero `ranges`.
4. **Attack window.** The frames that differ from the rest pose, plus two either side, sampled evenly.
5. **fps** = 8 x source fps / P, clamped to 5 to 14 for loops and 8 to 12 for attacks, then
   `fps_scale` (capped at 16). Each facing keeps its own fps in `meta.json`.
6. **Size match.** Each walk, run and idle loop whose median figure height is more than 3% off the
   `size_ref` facing's loop for that cycle is scaled about the feet to match (clamped 0.85 to 1.25),
   times any `size_bias`. It prints `scaled x...` and records `size_fix`.
7. **Shared canvas.** One crop box per hero over every frame of every cycle and facing, centred on the
   frame's middle column, so cycles register and mirrors stay centred. Boxes past the frame edge are
   padded with transparency.
8. **Downscale and finish.** Area-average to `height` / figure height. Pixel art: a small contrast and
   saturation lift, one median-cut palette per hero, alpha thresholded, a 1 px inner outline darkened.
   HD (`"pixel": false`): the smooth downscale with soft alpha, no palette, no outline.
9. **Sheets.** `<hero>_<cycle>.png`, 8 columns, one row per facing and mirror. `meta.json` per hero:
   `cell`, `pivot` (cell centre, feet), `height`, `rows`, `frames`, `palette`, `box`, `scale`, and per
   cycle the first facing's fps plus every facing's loop window, seam score, fps and `size_fix`.
   `--gif` writes a preview per cycle, `--frames-dir` loose PNGs.

## Reading the seam scores

- Under 0.5: a clean loop. 0.5 to 0.8: usually fine, check the GIF.
- Over 0.8 on walk or run (flagged): the stride is probably longer than the search window, common with
  heavy characters. Widen that hero's `ranges` and re-run with `--report`; regenerate only if that does
  not help.
- A good score is not proof: in profile left and right legs look alike, so a 1.5-stride window can
  score well and still hitch. The widest-stride frames should come twice per row, evenly spaced; if a
  side view loops at about 1.3x the other facings' period, narrow its range around theirs.
- Idle often scores about 1.0 or more; the motion is tiny either way, so accept it. "Relaxed the
  search" means very little motion: look at the GIF.

## 8 directions: what changes

- `facings: ["se", "ne", "e", "s", "n"]`, rows `se sw ne nw e w s n`.
- E, S and N first frames are single-pose turnarounds; check S and N against a vertical centre line
  (head and chest or spine on the line, shoulders level, both arms equally visible) before any clip.
  Redraw that facing alone rather than animating a turned frame.
- Five recipes instead of two (table in [prompts.md](prompts.md)).
- Size and speed across directions: size match against SE, then `size_bias` and `fps_scale` as
  art-direction nudges, judged in the compass preview (`compass_gif.py`) next to the diagonals.
- The player must use each direction's own fps from `meta.json`, not one fps per cycle.
