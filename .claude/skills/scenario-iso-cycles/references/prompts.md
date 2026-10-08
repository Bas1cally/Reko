# Prompt patterns

`scripts/make_prompts.py` writes every request from `cast.json`; the full templates are at the top of
that script. This page explains them, so you can adapt a template to a new cycle, camera or model
without losing what each sentence is for. Put changes in `cast.json` or in the script, not in
`prompts.json` (a re-run with `--force` replaces it).

## Field names

The requests use the field names of the model families the production ran. Map them to the schema
of the model you picked (`model_schema_get`):

| in prompts.json                       | meaning                                                     | look for                               |
| ------------------------------------- | ----------------------------------------------------------- | -------------------------------------- |
| `referenceImages`                     | first frames already drawn (turnarounds), up to 4 asset ids | reference / input images               |
| `numOutputs`, `quality`, `background` | 2 options to pick from, high quality, opaque                | outputs / samples, quality, background |
| `width`, `height`                     | 1536x1024 for a two-pose still, 1024x1024 for one pose      | size or aspect ratio                   |
| `startImage`                          | the uploaded first frame of that facing                     | first frame / image                    |
| `endImage`                            | the same asset id, when the clip must end where it started  | last frame / end image                 |
| `duration`                            | `"3"` or `"5"` seconds                                      | duration                               |
| `aspectRatio`, `generateAudio`        | `"1:1"`, `false`                                            | aspect ratio, audio                    |

If the clip model has no last-frame input, the 5 s recipes lose their anchor: say so to the user and
expect more drift on back, side and front locomotion.

## Stills

**Two-pose still** (a hero described in text, SE + NE): "game sprite sheet, two poses of the same
character side by side, standing neutral, full body, on a perfectly flat solid magenta (#FF00FF)
background, no shadows on the ground, no text", then the `character`, the camera, "Left pose: body
turned three-quarters toward the viewer, facing down and to the right (south-east). Right pose: body
turned three-quarters away from the viewer, facing up and to the right (north-east), {back}", and the
`style` with "each figure about 60% of the image height, both figures the same size and aligned on
the same baseline". Both facings in one image is what keeps the identity matched.

Straight-on facings (E, W, S, N) never go into a multi-pose sheet: there they come out a few degrees
turned. The script draws the diagonals (or the first facing alone) and, once those are uploaded,
emits one turnaround per straight-on facing.

**Turnaround** (every missing facing once at least one first frame exists): "Redraw the exact same
character as in the reference images: same design, proportions, colours, outfit, props and art style
(if it is pixel art, keep the same pixel size, outline and palette). One single full-body figure
standing neutral, {pose}", the camera, the `character`, the facing's `turn_notes`, the `notes` with
where the right hand sits on screen, and "centred, about 60% of the image height, on a perfectly flat
solid {key} background, no ground shadow". The S and N poses ask for "a perfectly symmetrical front
(back) view, head and chest (the spine) in the exact horizontal centre of the body, both shoulders
level and the same size, both arms equally visible on either side of the body, feet side by side".

## Clips: which recipe each facing and cycle gets

| facing | walk                          | run                            | idle                   | attack                 |
| ------ | ----------------------------- | ------------------------------ | ---------------------- | ---------------------- |
| SE, SW | plain, 3 s, no end frame      | plain, 3 s, no end frame       | plain, 3 s, end pinned | plain, 3 s, end pinned |
| NE, NW | plain, 3 s, no end frame      | back-view run, 5 s, end pinned | plain, 3 s, end pinned | plain, 3 s, end pinned |
| E, W   | side recipe, 5 s, end pinned  | side recipe, 5 s, end pinned   | plain, 3 s, end pinned | plain, 3 s, end pinned |
| S      | front recipe, 5 s, end pinned | front recipe, 5 s, end pinned  | plain, 3 s, end pinned | plain, 3 s, end pinned |
| N      | back walk, 5 s, end pinned    | back-view run, 5 s, end pinned | plain, 3 s, end pinned | plain, 3 s, end pinned |

Per 8-direction hero: 20 clips, 7 of them 5 s. Per 4-direction hero (SE, NE): 8 clips, 1 of them 5 s.

**Plain** = cycle sentence + facing sentence + tail.

- Walk: "game sprite animation, like a treadmill: the {who} immediately starts walking in place and
  keeps walking for the whole clip, a steady repeating walk cycle at a relaxed pace (heel-to-toe
  steps, arms swing opposite the legs, slight up-and-down bob{extra})". Run likewise with "knees high,
  arms pumping, torso leaning forward, both feet leave the ground between steps".
- Idle: "stands idle in place, a subtle breathing loop: chest rises and falls, a slight weight shift,
  {idle}. Feet stay planted. Calm, small motion."
- Attack: "performs one {attack}, then returns to the starting ready pose. Snappy anticipation, fast
  strike, short follow-through."
- Facing sentence, e.g. SE: "always faces diagonally toward the bottom-right corner of the frame
  (isometric three-quarter front view from above, the same angle as the first frame), never turning
  to a side view"; S and N add "with its face and chest (its spine) in the centre of its body".
- Tail: "stays centred and does not travel across the frame. Locked static camera, flat solid magenta
  background with no glow or light on it, no ground shadow, crisp pixel art, same character design as
  the first frame."
- Negative: the wrong angle for that facing (side view and profile for diagonals; front, back and
  three-quarter for E/W), plus "glowing halo around the character, light spill on the background,
  camera movement, zoom, travelling across the frame, ground shadow, drop shadow, background change,
  extra characters, blur, 3D render", and for walk and run "slowing down, stopping, standing still".

**Why no end frame on 3 s walks and runs**: a pinned end makes the model start and stop the gait
inside a short clip. Idle and attack return to rest, so they pin it.

**Back-view run** (NE, NW, N): "seen from behind. The {who} runs away from the viewer, toward the
top-right corner of the screen, on a treadmill so it stays in place. We keep seeing {back_view} at
the same diagonal angle as the first frame for the whole clip: its left shoulder is closer to us than
its right." N says "straight up the screen" and "both shoulders stay level and its spine stays in the
centre of its body". Negative adds "side view, profile view, facing right, facing the camera,
turning, rotating".

**Side recipe** (E, W walk and run): "in side profile. The {who} walks toward the right edge of the
screen, on a treadmill so it stays in place. We keep seeing its right side in profile at the same
angle as the first frame for the whole clip: its face points at the right edge of the frame and we
never see its chest or its back." Negative: "front view, three-quarter view, facing the camera,
turning toward the camera, back view".

**Back walk** (N walk): "walks away from the viewer, straight up the screen ... Each step pushes
forward, away from us: the back foot lifts its heel toward us, swings forward and plants farther from
the camera." Negative adds "walking backwards, walking toward the camera".

**Front recipe** (S walk and run): "seen from the front. The {who} runs straight at the camera, toward
the viewer and straight down the screen, on a treadmill so it stays in place. It never turns
sideways: we keep seeing its face and chest straight on ... its face stays in the centre of its body,
never turning to either side." Negative adds "running sideways, walking sideways, moving to the
right, moving to the left, three-quarter view".

**Why 5 s with the end pinned** for these: on a longer clip the model's start and stop land at the
ends, and the anchor holds the angle in between. The loop search takes the middle.

## Writing a new cycle

Add a template to `CYCLE` in `make_prompts.py` and list it in `cycles`. Loops (a cast loop, a hover)
use the walk range in `process.py` unless you add one to `RANGES`. One-shots that return to rest
(hurt, cast) behave like attack: route them through `attack_window` in `pick()` and keep the end frame
pinned. One-shots that do not return (death) need no end frame and should take the tail of the clip.
