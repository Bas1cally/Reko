# Running the route on Venice.ai

This repo runs the paid steps on Venice.ai instead of the Scenario MCP, with `tools/venice.py` (stdlib
only). Everything local (`reframe.py`, `make_prompts.py`, `process.py`, `compass_gif.py`) is unchanged.

## Key

In a Claude Code cloud session: a network secret (type Bearer) for `api.venice.ai`; the proxy adds the
`Authorization` header and `tools/venice.py` sends none of its own. Locally: `VENICE_API_KEY` in the
environment, or `VENICE_API_KEY=...` in `.env` at the repo root (git-ignored). Never commit a key,
never paste it into a prompt, a commit message or a file in the repo. `/models` and `/video/quote`
need no key at all.

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

## Model picks (October 2026, check `models` and `quote` again)

- Stills: `gpt-image-2-5-sunburst` at `quality: high` ($0.07 per image at 1K, about a quarter of
  `gpt-image-2`); turnarounds: `gpt-image-2-5-sunburst-edit` ($0.08). Check the first still for
  layout adherence (two figures, flat magenta, one baseline) before drawing the rest with it.
- Clips, quoted per hero (20 clips, 8 directions, audio off):

  | model                                  | per clip            | per hero | note                        |
  | -------------------------------------- | ------------------- | -------- | --------------------------- |
  | `minimax-h3-max-turbo-image-to-video`  | $0.14 (5 s, 768P)   | $2.80    | cheapest; first pick to test |
  | `wan-3-0-image-to-video`               | $0.33 (5 s, 480p)   | $6.60    | 2 s or 5 s only             |
  | `kling-v3-standard-image-to-video`     | $0.28 / $0.46 (3/5 s) | $6.86  | the production's family     |

  MiniMax and Wan have no 3 s: every clip runs 5 s. That is fine for the loop search (it takes the
  middle and ranges are in frames), but the "no end frame on 3 s walks and runs" rule does not exist
  there; leave walk/run end frames unpinned as written and check the first clips. Resolutions the
  model list does not show are in `DEFAULT_RES` in `tools/venice.py` (MiniMax wants `768P`).
- Use **image-to-video**, not reference-to-video, for cycles: the first frame fixes pose, size and
  position, which the loop search, size matching and the shared canvas rely on. R2V keeps identity
  but not the framing.
- Whether a model honours `end_image_url` is not in the model list: check the first 5 s clip with a
  pinned end frame (back run, side walk) before queueing the rest.

## Order of work

1. `models`, pick, `make_prompts.py ... --still-model ID --clip-model ID`.
2. `quote prompts.json`, tell the user the total (+25%), wait for the go-ahead.
3. `stills prompts.json --ids <hero>_still`, pick, `reframe.py`, put the paths into `stills`.
4. `make_prompts.py --force`, `stills --ids <hero>_<facing>_turnaround`, pick, reframe, add path.
5. `clips prompts.json --ids <one hero's clips>`, `wait`, contact sheet, fix the recipe.
6. Then the other heroes, then `process.py` as in SKILL.md.
