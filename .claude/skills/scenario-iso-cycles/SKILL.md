---
name: scenario-iso-cycles
description: 'Use when making engine-ready character sprite sheets with the Scenario MCP: walk, run, idle and attack cycles of 8 frames in 8 isometric directions (or the 4 diagonals, side-view or top-down facings), pixel art or HD, from a text description or character art the user already has. Draws every facing from one design, animates each facing and cycle with an image-to-video model on a key-colour backdrop, then locally keys it, finds a seamless loop, matches size and speed across directions, pixelates to one palette per character and mirrors SW, NW and W. Also processes clips the user already has, or just advises. Triggers include "sprite sheet for my game character", "8-direction walk cycle", "isometric sprites", "animate my OC for a game", "walk run idle attack", and fixes for a back view that turns side-on, a side walk that turns to the camera, a back walk that moonwalks, a loop that hitches, or directions that differ in size or speed.'
---

# Iso Cycles: 8-direction sprite cycles

## Overview

From a few stills to a sprite sheet: draw, animate, loop, pixelate, mirror. This keeps what each
tool is good at and replaces what it is bad at. An image model keeps the **look**: the character is
drawn once per facing from one design (both diagonals in one image, every other facing as a
turnaround from those), and the user's own art, when they have it, is the master that nothing
restyles. An image-to-video model gives the **motion**: real strides, airborne run frames,
follow-through, which no pose sheet or pixel animation model gave. Deterministic local code does
**everything else**: keys the backdrop, cuts the seamless loop out of each clip, matches size and
speed across directions, pixelates to one palette per character and mirrors SE, NE and E into SW, NW
and W. Tuning happens in the local step, which is free and repeatable.

Reference result: five fantasy heroes (64 to 96 px tall) in 8 isometric directions with walk, run,
idle and attack, 100 generated clips (SE, NE, E, S, N per hero) into 20 sheets of 8 rows by 8 frames.

## Models: none hard-coded

**In this repo the paid steps run on Venice.ai, not the Scenario MCP**: read
[references/venice.md](references/venice.md) first. It maps every Scenario call below to
`tools/venice.py`; `stills` in `cast.json` then hold local file paths, not asset ids.

This skill names no model on purpose; availability and the best pick change month to month. Pick each
at run time with the Scenario MCP: `recommend` for the job in plain words, plus `search` with
`sort_by: ["createdAt:desc"]` (newest first), then read every candidate with `model_schema_get`.

- **Stills and turnarounds**: an image model with strong layout adherence (two figures, named facings,
  a flat background) that takes several reference images. In the production a GPT Image model at a
  high quality setting worked.
- **Clips**: an image-to-video model with a first frame **and a last frame**, square output, 3 and 5 s
  durations and audio off. In the production a Kling image-to-video model at its standard tier
  worked; a Seedance model kept the facing but jogged instead of running, at a higher price.

`make_prompts.py` writes the requests with the field names of those families (`referenceImages`,
`startImage`, `endImage`, `duration`); rename them to the schema of the model you picked
([references/prompts.md](references/prompts.md)). Price every distinct request with `model_run` and
`dry_run=true` (a 5 s clip prices higher than a 3 s one), tell the user the total, and run nothing
paid until they agree.

## Related skills

Connection, scope and the generation loop: `scenario`. Related: `scenario-gpt-image` (stills and
turnarounds), `scenario-kling` and `scenario-video` (clips), `scenario-image-editing` (removing a busy
background from their art), `scenario-sprite-animation` (hosted frame tools, GIFs, slicing for an
engine). If one is missing, ask the user to install it
(`npx skills add scenario-labs/skills --skill <name>`); unattended, proceed from the tool schemas and
flag the gap.

Locally: Python 3 with numpy and Pillow, and ffmpeg / ffprobe on the PATH. Every script prints its
usage when run without arguments and refuses to overwrite an existing output unless given `--force`.

## Quick reference

| Step           | How                                                                                                                    |
| -------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Situation      | Advice only, idea, their art, their clips, other view, existing sheet (step 1)                                         |
| Scope          | `memory_recall`; confirm the team and project with the user; pass them on every call                                   |
| Cast           | `cast.json` from [examples/cast.json](examples/cast.json); fields in [references/cast.md](references/cast.md)          |
| Pick models    | `recommend` + `search` newest first, `model_schema_get`; first + last frame, 3 and 5 s, square                         |
| Requests       | `python3 scripts/make_prompts.py cast.json --still-model ID --clip-model ID`                                           |
| Price          | `model_run` with `dry_run=true`, one per distinct request; tell the user the total                                     |
| Upload         | `upload_asset` (with `file_size`), PUT the parts, `upload_asset_complete`; ids into `stills`                           |
| First frames   | `scripts/reframe.py`: figure 58% of a 960 square, feet at 82%, key check                                               |
| S and N check  | Vertical centre line over the frame before any clip; redraw that facing alone if turned                                |
| Clips          | One hero first; `jobs_wait` (32 ids max per call), `asset_download` to `clips/<hero>_<facing>_<cycle>.mp4`             |
| Loops          | `scripts/process.py cast.json <hero> --report`, then without `--report`, with `--gif`                                  |
| 8-direction QA | `scripts/compass_gif.py <hero> walk run`: same height and believable speed in every row                                |
| Deliver        | `sprites/<hero>_<cycle>.png` + `meta.json`; engine notes in [references/sprite-sheets.md](references/sprite-sheets.md) |

## Steps

1. **Work out the situation** from the request; ask only what you cannot tell.

   | The user...                                            | Do                                                                                                                                                                                                                                              |
   | ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
   | wants advice ("how do I make sprite sheets")           | Answer from [references/sprite-sheets.md](references/sprite-sheets.md), fitted to their engine, camera and size. Spend nothing; offer the route afterwards.                                                                                     |
   | has an idea, no art                                    | Full route, from a `character` description (step 4A).                                                                                                                                                                                           |
   | has their own character art                            | Their art becomes the first frame of the facing it shows; only missing facings are drawn (step 4B).                                                                                                                                             |
   | already has clips (another tool, a 3D render)          | Name them `<hero>_<facing>_<cycle>.mp4` on a flat magenta, green or blue backdrop, set `"fig_frac": "auto"`, go to step 8. Other backdrops need background removal first.                                                                       |
   | has art in another view (3/4 art, side-scroller game)  | Step 4B with `reframe.py --facing ref`, upload it as `reference`; every facing becomes a turnaround from it. For a side-scroller ask: flat profile (`"camera": "side"`) or a slightly turned 3/4 side view (write it as the `camera` sentence). |
   | has a sprite sheet and wants more cycles or directions | One clean frame of it is their art (4B); set `height` to its pixel height so new sheets match.                                                                                                                                                  |

2. **Scope.** Load the `scenario` skill if the MCP is not connected. Call `memory_recall`, then
   `teams_list` / `projects_list`, and confirm with the user which project to work in.

3. **Cast and models.** Write `cast.json` with the user (start from
   [examples/cast.json](examples/cast.json); every field in [references/cast.md](references/cast.md)).
   For 8 directions: `"facings": ["se", "ne", "e", "s", "n"]`. Fill `who`, `pronoun`, `idle`,
   `attack`, `back_view` per hero, and for anything held or worn on one side, `notes` and `turn_notes`
   (which side of the image each prop sits on, and what part of a prop shows from behind). Pick the two
   models (above), read their schemas, then:

   ```
   python3 scripts/make_prompts.py cast.json --still-model <image model id> --clip-model <video model id>
   ```

   It prints how many still requests and 3 s and 5 s clips the cast needs. Price one of each kind with
   `dry_run=true`, add about a quarter for redraws and re-runs (each of the five reference heroes
   needed one or two in the 8-direction pass), and get the user's go-ahead.

4. **First frames.**

   A. _From a description_: run the `stills` entry with `model_run` (2 outputs), `jobs_wait`, show both
   with `asset_display`, and let the user pick. The sheet draws the diagonals only (SE left, NE right);
   straight-on facings drawn in a sheet come out turned. Check each figure faces its slot on a flat key
   backdrop on one baseline, or regenerate: everything downstream inherits the still.

   B. _Their art_: look first (facing, backdrop, pixel or painted, size, key colours in it); remove a
   busy background before anything else. Then
   `python3 scripts/reframe.py <hero> their_art.png --facing se --out raw` (name the facing the art
   really shows; isometric art facing straight down is `s`). For pixel art use the printed native
   height and colour count for `height` and `palette` and set `"fig_frac": "auto"`. If the key check
   warns, re-run with the key it recommends and set `key` in `cast.json` before any prompt.

5. **Reframe and upload.** For a 2A pick: `python3 scripts/reframe.py <hero> raw/<hero>_pick.png
--facings se,ne --out raw` (one 960x960 frame per facing). `upload_asset` each frame (with its
   `file_size`), PUT the parts from the instructions, `upload_asset_complete`, and put the asset ids in
   `stills`. Re-run `make_prompts.py ... --force`: it now emits one single-pose turnaround per missing
   facing, drawn from every first frame already uploaded. Show the options next to the existing frames
   (and next to their art) and pick; reject anything that changed the design, palette, pixel size or
   which side a prop is on. Reframe the pick with `--facing e` (or `s`, `n`), upload, add to `stills`.

6. **Check S and N before any clip.** Draw a vertical centre line over the S and N frames: head and
   chest (S) or spine (N) on the line, shoulders level and the same size, both arms equally visible. A
   few degrees of turn fails: the pinned idle inherits it and the walk exaggerates it. Redraw that one
   facing rather than animating it.

7. **Clips.** Re-run `make_prompts.py ... --force` once every facing has an asset id; every entry in
   `cycles` is ready for `model_run` after renaming fields to your model's schema. The recipes per
   facing (treadmill wording, facing sentence, which clips pin the end frame and run 5 s) are in
   [references/prompts.md](references/prompts.md). Submit **one hero** first with `wait=false`, record
   job ids in `jobs.json`, `jobs_wait`, `asset_download` each clip to
   `clips/<hero>_<facing>_<cycle>.mp4`, and look at a contact sheet of frames: diagonals never side-on,
   E/W in profile throughout, S and N straight on, the N walk stepping away from us, no glow on the
   backdrop. Fix the recipe before submitting the other heroes.

8. **Process.** `python3 scripts/process.py cast.json <hero> --clips clips --out sprites --report`
   prints each clip's loop window, seam score (seam over motion), fps and size fix without writing.
   Widen a hero's `ranges` for a weak walk or run seam (over 0.8, flagged), narrow it for a hitching
   1.5-stride loop, then run it for real with `--gif` (add `--force` when replacing earlier sheets).
   Reading the scores and what each processing step does: [references/pipeline.md](references/pipeline.md).

9. **Size and speed across directions.** `python3 scripts/compass_gif.py <hero> walk run` writes
   `qa/<hero>_8dir_preview.gif`. Every row should read the same height and speed. Size matching to SE
   is automatic; a slim side profile or a front or back view that still reads small gets `size_bias`
   (`{"e": 1.05}`, `{"s": 1.06, "n": 1.06}`), a front or back run that reads slow gets `fps_scale`
   (`{"s_run": 1.3, "n_run": 1.3}`). Re-process with `--force`; no new generation needed.

10. **Hand over.** The sheets, `meta.json` (cell, pivot at the feet, row order, and fps **per facing**:
    one shared fps makes some directions play slow), the preview GIFs, and import notes for their
    engine from [references/sprite-sheets.md](references/sprite-sheets.md). Keep a session log
    (models, asset ids, job ids, prices, mistakes with why and fix): it is how the next session resumes.

## Checks before delivery

See [references/checks.md](references/checks.md). Short version: every facing holds its angle for the
whole clip; S and N symmetric; walk and run seams under 0.8 with the widest-stride frames evenly
spaced; no pop at the loop point, no key fringe, no clipped weapon; identity the same in every row;
every direction the same height and a believable speed in the compass preview; per-facing fps in the
hand-over.

## Common mistakes

- Asking a pixel-art animation model for isometric walks: its walking mode is 4 cardinal directions,
  4 frames, whatever the prompt says.
- Asking an image model for a sheet of run poses: identity holds, the legs barely move.
- Figures that fill the frame: raised weapons get cut off in the attack. Reframe to 58% first.
- Pinning the end frame on a 3 s walk or run: the model starts and stops the gait inside the clip.
- A back-view run with the plain prompt: it drifts to a side-on profile. Use the away-from-viewer run,
  end frame pinned, 5 s.
- E and W walks and runs with the plain prompt: they turn toward the camera for part of every stride.
  Use the side recipe.
- Drawing S and N in one turnaround sheet: they come out a few degrees turned, and every clip inherits
  it. One pose per request, checked against a centre line.
- The plain N walk: it reads as walking backwards, and playing it in reverse is not enough. Use the
  back-walk recipe.
- The plain S walk or run: it can turn three-quarter or sideways. Use the front recipe; if it still
  turns, describe the run head-on and name what is in the hands.
- A prop the body hides from behind (an axe, a quiver): the model reinvents it. Say exactly which
  part shows and where, in `turn_notes` and `back_view`.
- A glowing prop: it lights the backdrop and the key leaves a halo. The prompts forbid glow on the
  background; regenerate if it still happens.
- One attack text for every facing: an aimed move (bow, spear, beam) gets animated side-on in S and N.
  Write `attack_facing` head-on.
- Trusting a low seam score: a side-view walk can loop on 1.5 strides and hitch. Check the wide poses
  are evenly spaced; narrow `ranges` around the other facings' period.
- A heavy character's loop flagged as weak: widen `ranges` and re-process before regenerating.
- Playing every direction at one fps: the N run played about 1.6x slow. Use each facing's fps.
- Judging the result as "low quality" when the sprite is just small: re-process at a larger `height`
  before regenerating anything.
- Mirroring an asymmetric character: the sword changes hands. Generate SW, NW and W if it matters.
- Passing a local path or URL to `model_run`, hard-coding model ids or prices, more than 32 ids per
  `jobs_wait`, or submitting every hero before looking at one hero's clips.

## Files

| File                          | Role                                                                                                         |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `references/cast.md`          | Every `cast.json` setting and per-hero field, and what the processing reads                                  |
| `references/prompts.md`       | Field mapping, still and turnaround wording, the clip recipe per facing and cycle, new cycles                |
| `references/pipeline.md`      | Why the route is shaped this way, first frames, mirroring, what `process.py` does, seam scores, 8 directions |
| `references/venice.md`        | Venice.ai instead of the Scenario MCP: key, model picks, command per step                                    |
| `references/lessons.md`       | What failed in the production, why, and the fix now built in                                                 |
| `references/checks.md`        | The review checklist                                                                                         |
| `references/sprite-sheets.md` | Sprite-sheet fundamentals and engine import (Unity, Godot, GameMaker, Phaser, Aseprite); advice-only answers |
| `scripts/make_prompts.py`     | `cast.json` to every still, turnaround and clip request, with counts to price                                |
| `scripts/reframe.py`          | Pose sheet or their art to 960x960 first frames with headroom; key check, pixel-art scale                    |
| `scripts/process.py`          | Clips to sheets: key, loop search, size match, shared canvas, pixelate, mirror, `meta.json`, GIFs            |
| `scripts/compass_gif.py`      | 8-direction compass preview of a hero's sheets                                                               |
| `examples/cast.json`          | The five Iso Cycles heroes in 8 directions, with every tuning the production needed                          |
