# Running the route on Venice.ai

This repo runs the paid steps on Venice.ai instead of the Scenario MCP, with `tools/venice.py` (stdlib
only). Everything local (`reframe.py`, `make_prompts.py`, `process.py`, `compass_gif.py`) is unchanged.

## Key

`VENICE_API_KEY` in the environment, or `VENICE_API_KEY=...` in `.env` at the repo root. `.env` is
git-ignored: never commit a key, never paste it into a prompt, a commit message or a file in the repo.
In a Claude Code cloud session, set it as an environment variable of the environment.

## What replaces what

| Scenario step                             | Venice                                                                 |
| ----------------------------------------- | ---------------------------------------------------------------------- |
| `recommend` / `search` / `model_schema_get` | `python3 tools/venice.py models image\|edit\|video [--grep ...]`       |
| `model_run` with `dry_run=true`           | `python3 tools/venice.py quote prompts.json` (`/video/quote` + model list prices) |
| `upload_asset`, asset ids in `stills`     | none: `stills` hold **local paths** (`raw/<hero>_se.png`), sent as data URLs |
| still / two-pose sheet                    | `tools/venice.py stills prompts.json` → `/image/generate`               |
| turnaround (`referenceImages`)            | the same command → `/image/multi-edit` (use an **edit** model id, up to 6 inputs) |
| clips (`model_run`, `jobs_wait`, `asset_download`) | `tools/venice.py clips prompts.json` → `jobs.json`, then `tools/venice.py wait` → `clips/<id>.mp4` |

Stills without references and turnarounds need different model ids (an image model vs. an edit
model, e.g. `gpt-image-2` and `gpt-image-2-edit`). Run `make_prompts.py` once per kind, or edit the
`model` field of the turnaround entries.

## Model picks (October 2026, check `models` again)

- Stills: a GPT Image model at `quality: high` (as in the production); turnarounds: its `-edit` twin.
- Clips: `kling-v3-standard-image-to-video` has 3 s and 5 s and audio that can be switched off, the
  closest match to the production's Kling. Square output follows the square first frame (the model
  lists no aspect ratios). Whether it honours `end_image_url` is not in the model list: check the
  first 5 s clip with a pinned end frame (back run, side walk) before queueing the rest. If it ignores
  it, try a model built for it (`flux-3-first-last-frame-to-video`, `pixverse-c1-transition`).

## Order of work

1. `models`, pick, `make_prompts.py ... --still-model ID --clip-model ID`.
2. `quote prompts.json`, tell the user the total (+25%), wait for the go-ahead.
3. `stills prompts.json --ids <hero>_still`, pick, `reframe.py`, put the paths into `stills`.
4. `make_prompts.py --force`, `stills --ids <hero>_<facing>_turnaround`, pick, reframe, add path.
5. `clips prompts.json --ids <one hero's clips>`, `wait`, contact sheet, fix the recipe.
6. Then the other heroes, then `process.py` as in SKILL.md.
