# Sprite-sheet guidance

For advice-only requests, and for the hand-over at the end of a run. Fit the answer to the
user's game: ask (or infer) the engine, the camera and the size of their tiles or
characters, then give them the few numbers that matter, not this whole page.

## Contents

- What a sprite sheet is (the anatomy)
- Frames and speed per cycle
- Directions and mirroring
- Size
- Layout, pivot, consistency
- Importing into an engine
- If they want to draw it by hand

## What a sprite sheet is

One image holding every frame of an animation in a grid of equal cells. Engines slice it
by cell size and play one row (or range of frames) as an animation. The things that make
it usable:

- **Every cell the same size**, the character registered in the same place in each, feet
  on the same baseline. If cells are cropped tight per frame, the character jitters.
- **One row per direction** (this skill's layout) or one sheet per cycle and direction.
- **A pivot** at the feet, so the character stands on the ground rather than hanging from
  the top-left corner.
- **Seamless loops** for walk, run and idle: the last frame must lead back into the first.

## Frames and speed per cycle

| cycle  | frames                       | fps     | note                                                      |
| ------ | ---------------------------- | ------- | --------------------------------------------------------- |
| walk   | 8 (6 is fine at small sizes) | 7 to 10 | 2 steps: contact, down, passing, up, per leg              |
| run    | 6 to 8                       | 9 to 12 | include airborne frames; lean forward                     |
| idle   | 4 to 8                       | 4 to 6  | breathing and one secondary motion; must be subtle        |
| attack | 6 to 10                      | 8 to 12 | anticipation, strike, follow-through, recover; plays once |
| hurt   | 2 to 4                       | 8 to 10 | plays once                                                |
| death  | 6 to 10                      | 8 to 10 | plays once, holds the last frame                          |

Which cycles depends on the genre: action / ARPG and platformers need walk, run, idle,
attack (+ jump, hurt); tactics and turn-based games move tile to tile, so skip run and
spend the effort on idle, walk, attack, cast, hurt and death; top-down farming / adventure
games need walk and idle most, plus tool or interaction cycles.

This route samples 8 frames per cycle and sets the fps of each cycle and facing from the
length of the loop it found, so walk and run speeds match the motion (they're in
`meta.json`; directions of one cycle can differ, so play each at its own fps).

## Directions and mirroring

| game                                         | facings to make | the rest by mirroring |
| -------------------------------------------- | --------------- | --------------------- |
| side-scroller                                | E (right)       | W                     |
| top-down 4-way                               | S, N, E         | W                     |
| isometric 4-way (most iso games, Iso Cycles) | SE, NE          | SW, NW                |
| isometric / top-down 8-way                   | SE, NE, E, S, N | SW, NW, W             |

Engines mirror around the cell centre (Godot `flip_h`, Unity `flipX`, Phaser `setFlipX`), so
the character must be centred horizontally in its cell; this skill's sheets are. Mirroring
at runtime instead of storing the mirrored rows is fine too.

Mirroring halves the work but swaps sides: sword hand, shield arm, eyepatch, one pauldron,
lettering. If that matters, make the mirrored facings as real facings too.

In an isometric game, map movement to the diagonal facings: screen-down-right = SE,
down-left = SW, up-right = NE, up-left = NW. Straight up/down/left/right input picks the
nearest diagonal (or the last one used), unless they have 8 facings.

## Size

- **Pixel art**: choose the character height from the tile size. Common: 32 px tall
  characters on 16/32 px tiles; 48 to 64 px for detailed characters; 96 px for big units or
  bosses. Isometric tiles are usually 2:1 (64×32, 32×16); a character is typically 1.5 to 3
  tile-heights tall. Hand-drawn art works at any size. Generated-then-downscaled frames
  (this skill's route) read well from ~64 px up; at 32 to 48 px they come out usable but rough
  and want a touch-up pass in Aseprite, so say that when quoting the route for small sprites.
- **Mixed sizes in one cast** are fine and read well (Iso Cycles: 64, 80 and 96 px).
- **HD / painted**: pick the size it will display at on the target screen (often 128 to 256 px
  tall) and keep the source larger for crisp downscaling. Use `"pixel": false`.
- Always display pixel art at whole-number zoom (2×, 3×, 4×) with nearest-neighbour filtering.

## Layout, pivot, consistency

This skill's sheets: `<hero>_<cycle>.png`, 8 columns, one row per entry in `meta.json`
`rows` (`se, sw, ne, nw` for 4 directions; `se, sw, ne, nw, e, w, s, n` for 8), every cell `cell` = [w, h] pixels. `pivot` = [x, y] in
the cell: horizontal centre, y at the feet. All cycles of one hero share the same cell size
and registration, so switching from walk to attack doesn't jump.

## Importing into an engine

Numbers come from `meta.json`: cell w×h, rows, fps, pivot. Set the fps per direction, not
once per cycle: each facing's loop has its own length (`cycles[cycle][facing].fps`), and one
shared fps makes some directions play visibly slow or fast. Put the pivot at the feet (or
another natural spot the character turns around, like the centre of a mount's hooves) so
switching direction doesn't make the sprite jump.

**Unity (2D)**: select the PNG → Texture Type _Sprite (2D and UI)_, Sprite Mode _Multiple_,
Filter Mode _Point (no filter)_ for pixel art or _Bilinear_ for HD art, Compression _None_, Pixels Per Unit = the tile size.
Sprite Editor → Slice → _Grid By Cell Size_ = cell w×h, Pivot _Custom_ = pivot ÷ cell
(normalised; y measured from the bottom, so y = 1 − pivot_y / cell_h). Drag one row's 8
sprites into the scene to make an Animation clip; set its Samples to the cycle fps; untick
Loop Time for attack.

**Godot 4**: (pixel art; HD art keeps the default Linear filter) to stop blur, three settings (turn on Advanced Settings in Project Settings):
Rendering → Textures → Canvas Textures → Default Texture Filter _Nearest_; Display →
Window → Stretch → Mode _viewport_ (or _canvas_items_) with Scale Mode _integer_ (4.2+) and
the base resolution set to the game's pixel resolution; Rendering → 2D → Snap → Snap 2D
Transforms to Pixel (and Vertices) on.
AnimatedSprite2D → SpriteFrames → new animation per cycle and direction (e.g. `walk_se`) →
_Add frames from a sprite sheet_ → Horizontal 8, Vertical = number of rows → select one row.
Set the animation's FPS; turn Loop off for attack. Offset the sprite so the pivot sits on
the node origin (offset.y = cell_h/2 − pivot_y with Centered on). For mirrored directions,
either use the stored SW/NW rows or play the SE/NE animation with `flip_h = true`.

**GameMaker**: Sprite Editor → Image → _Import Strip Image_: frame width/height = cell,
frames per row 8, number of frames 8, vertical cell offset = row × cell_h (one sprite per
direction). Origin _Custom_ = pivot. Set the sprite speed to the fps.

**Phaser 3**: `pixelArt: true` in the game config.
`this.load.spritesheet('knight_walk', 'knight_walk.png', { frameWidth: w, frameHeight: h })`, then
`this.anims.create({ key: 'walk_se', frames: this.anims.generateFrameNumbers('knight_walk', { start: row * 8, end: row * 8 + 7 }), frameRate: fps, repeat: -1 })`
(`repeat: 0` for attack); `sprite.setOrigin(pivot_x / w, pivot_y / h)`.

**Aseprite**: to touch up generated frames, File → Import Sprite Sheet → Type _By Rows_,
width/height = cell. To export hand-drawn animation as a sheet: keep one fixed canvas size
for every animation with the feet on the same baseline, one tag per animation and direction
(`walk_se`), then File → Export Sprite Sheet → Layout _By Rows_ (Split Tags puts each tag on
its own row), Trim _off_ (trimming breaks registration), optionally JSON data. Godot users
can skip the export with the Aseprite Wizard plugin, which imports .aseprite files and tags
directly into SpriteFrames.

**Loose frames**: run `process.py … --frames-dir frames` for one PNG per frame
(`<hero>/<cycle>/<direction>_<k>.png`), for engines or packers that prefer them (TexturePacker, Spine).

## If they want to draw it by hand

The same structure applies without AI: design one front three-quarter and one back
three-quarter pose, draw the walk's key poses first (contact, passing) then in-betweens,
keep the head bob to 1 to 2 px at small sizes, and mirror for the other diagonals. The route in
this skill is a shortcut to those frames; offering it, with the credit cost, is fair, but
answer the question they asked first.
