# cast.json

One file drives the prompts (`make_prompts.py`) and the processing (`process.py`). Start from
[examples/cast.json](../examples/cast.json) (the five Iso Cycles heroes in 8 directions) and edit.
Fields starting with `_` are ignored.

## Top-level settings (all optional)

| setting            | default                 | change it when                                                                                                                                                                                            |
| ------------------ | ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `facings`          | `["se", "ne"]`          | 8 directions: `["se", "ne", "e", "s", "n"]`; side-scroller: `["e"]`; top-down 4-way: `["s", "n", "e"]`; an asymmetric character: add `"sw"`, `"nw"` (and `"w"`) so they are generated instead of mirrored |
| `camera`           | `"isometric"`           | `"side"` or `"topdown"`, or any camera sentence                                                                                                                                                           |
| `key`              | `"magenta"`             | the character contains the key colour: `"green"` or `"blue"`. `reframe.py` measures it and recommends one; follow it before making prompts, because the key colour is written into every prompt           |
| `cycles`           | walk, run, idle, attack | fewer, or new ones (add a template to `CYCLE` in `make_prompts.py`)                                                                                                                                       |
| `fig_frac`         | `0.58`                  | `"auto"` when the clips were not made from `reframe.py` frames, or for their own pixel art (the whole-number scale does not land exactly on 58%)                                                          |
| `style`            | a 16-bit pixel art line | heroes described in text in another style; for painted heroes describe their art                                                                                                                          |
| `size_ref`         | the first facing        | the facing every other facing's walk, run and idle is size-matched to; `null` turns size matching off                                                                                                     |
| `canvas`, `frames` | `960`, `8`              | rarely; `frames` is the number of columns per sheet                                                                                                                                                       |

Sheet rows: each facing, then its mirror unless the mirror was generated itself. For
`["se", "ne", "e", "s", "n"]` that is `se sw ne nw e w s n`.

## Per hero

| field            | used for                                                                                                                                                             |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `character`      | heroes described in text: silhouette, palette, props, where the weapon is held. Also added to turnaround prompts                                                     |
| `back`           | what the back view shows in the still ("we see the back and the shield")                                                                                             |
| `who`, `pronoun` | clip prompts ("stone golem", "It"). Defaults read "character", "It"                                                                                                  |
| `extra`          | motion detail appended to walk and run (", red plume bounces")                                                                                                       |
| `idle`           | the one small secondary motion in the idle ("the green flame flickers")                                                                                              |
| `attack`         | one named move, start to rest ("overhead axe chop: lifts ... slams it down ...")                                                                                     |
| `attack_facing`  | attack text per facing, e.g. `{"s": "...aimed straight at the camera...", "n": "..."}`: an aimed or thrust move written once gets animated side-on in every facing   |
| `back_view`      | the back-view run and walk: what must stay visible ("its mossy back and the glowing runes on its spine")                                                             |
| `notes`          | what must survive a redraw ("He holds the sword in his right hand."); turnaround prompts add where that hand sits on screen for the facing                           |
| `turn_notes`     | per facing, appended to that turnaround prompt: which side of the image each prop sits on, or the visible part of a prop the body hides                              |
| `height`         | sprite height in px. Generated frames read well from about 64 px; 32 to 48 px works but wants a touch-up pass. Their own pixel art: its native height                |
| `palette`        | colours per hero: 24 to 28 for generated heroes; their own pixel art: its own colour count (`reframe.py` prints it)                                                  |
| `pixel`          | `false` for painted or HD characters: prompts stop saying "pixel art", processing keeps a clean downscale with soft edges, no palette or outline                     |
| `ranges`         | loop-period search per cycle in 24 fps frames, e.g. `{"walk": [12, 48]}` for slow, heavy strides; defaults walk 12 to 34, run 8 to 24, idle 24 to 66                 |
| `size_bias`      | scale nudge per facing on top of size matching, all cycles including attack, e.g. `{"e": 1.05}` for a slim side profile, `{"s": 1.06, "n": 1.06}` for front and back |
| `fps_scale`      | playback speed per clip, e.g. `{"s_run": 1.3, "n_run": 1.3}` for foreshortened front and back runs; capped at 16 fps                                                 |
| `reverse`        | loops to play backwards, e.g. `["n_walk"]`: a free first try for a moonwalking back walk (usually not enough)                                                        |
| `stills`         | uploaded first-frame asset ids per facing, filled in as you upload                                                                                                   |
| `reference`      | uploaded asset id of their art when it is not one of the facings (3/4 art for a side-scroller, a portrait); turnarounds are drawn from it                            |

## What the processing reads

`process.py` uses `canvas`, `frames`, `key`, `fig_frac`, `cycles`, `facings`, `size_ref`, and per hero
`height`, `palette`, `pixel`, `ranges`, `size_bias`, `fps_scale` and `reverse`. Changing only those
needs no new generation: re-run `process.py` with `--force` (or `--report` to look first).
