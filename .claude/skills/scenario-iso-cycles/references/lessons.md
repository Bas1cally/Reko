# Lessons from Iso Cycles

What was tried and failed in the production (five heroes, first 4 then 8 isometric directions), why,
and what the scripts do now. Read it before changing a model or a prompt rule, and when a result looks
wrong. Model names here are what the production ran in September 2026; pick current ones yourself.

## Routes that did not work

**A pixel-art animation model in its four-angle walking mode** (`recommend`'s top pick for "isometric
pixel walk cycle", a Retro Diffusion model). Locked to 48x48, 4 frames per cycle, and the 4 directions
are cardinal (back, side, front, side), not isometric diagonals. "Isometric" in the prompt does not
change the camera. No run or attack mode. Fine for top-down RPG walkers only.

**An image model asked for a sheet of 8 poses** (the still as reference, a 4x2 grid, each pose named).
Identity and facing perfect, but the legs barely change between poses: it reads as a shuffle.

**A Seedance model** (480p, 4 s, the same prompt as the chosen image-to-video model). Kept the facing
but produced a jog or skip rather than a run, at several times the price.

**A pinned end frame on a 3 s run.** Real run with airborne frames, but standing frames at both ends
and the character turned side-on mid-clip: pinning start = end makes the model start and stop the gait
inside the clip. So 3 s walks and runs pin no end frame.

## Rules that came out of mistakes (4 directions)

**Headroom.** The first stills filled about 90% of the frame height: no room for a raised weapon, and
attacks were clipped. `reframe.py` puts the figure at 58% of a 960 canvas, feet at 82%.

**Back-view runs drift to profile.** All four NE runs turned east (side-on) while the NE walks, idles
and attacks held. From a back three-quarter frame, a fast run prompt pulls the model toward the
profile run it knows best; "faces the top-right corner" was not enough. Test A (away-from-viewer
wording, first frame only, 3 s): better, still drifts. Test B (the same wording, end frame pinned,
5 s): holds the angle; the loop search takes the middle, seams 0.15 to 0.44. B is the back-view run
in `make_prompts.py`. It reverses the "no end frame for locomotion" rule: on 5 s the start and stop
sit at the ends.

**Loop window too short for heavy strides.** The golem's SE run seam was 1.08 and NE walk 1.62 with
the default ranges; its stride is just slower. Widening to run 8 to 40 and walk 12 to 48 frames gave
0.29 and 0.32. Hence per-hero `ranges`, and `process.py` flags seams over 0.8.

**Blank, streaky sheets.** A sword trail reached the frame edge, the shared crop box went negative,
and numpy slicing wrapped around. `crop_padded` pads with transparency.

**Soft sprites.** The roughly 9x area-average downscale erased the 1 px dark outline, so sprites read
soft next to hand-made pixel art. A small contrast and saturation lift before the palette, then every
opaque pixel that touches transparency is darkened (inner outline).

**A "low quality" hero.** The elf had been pixelated at 48 px on purpose (one of four heights).
Re-processing at 80 px with 28 colours fixed it with no new generation. Try a larger `height` before
regenerating anything.

## 8 directions

**E walk and run turn toward the camera.** With the plain treadmill prompt the golem's E walk and run
turned from profile to three-quarter front and back for about 3 of every 8 frames: the same pull as
the NE runs. Side recipe (`SIDE_LOCO`): "walks toward the right edge of the screen ... we keep seeing
its right side in profile ... never see its chest or its back", end frame pinned, 5 s. The head stayed
in profile the whole loop, seams 0.25.

**S and N first frames slightly turned.** In a three-pose turnaround (E, S, N side by side) the model
drew "facing away" and "facing the viewer" as a slight three-quarter: spine left of centre, one arm
showing more; head and chest right of centre, near arm bigger. The pinned idle inherited the turn and
the walk exaggerated it, and the S and N clips were redone. Single-pose turnarounds drawn from every
existing still, asking for "a perfectly symmetrical front/back view, head and chest / spine in the
exact horizontal centre, shoulders level and the same size, both arms equally visible, feet side by
side"; the S and N facing sentences say "centre of its body" too. Check S and N against a centre line
before any clips.

**N walk reads as walking backwards.** The plain treadmill walk from behind looked like a moonwalk.
Playing the loop backwards (free, `reverse: ["n_walk"]`) was tried first: not enough. Back-walk recipe
(`BACK_WALK`): walks away from the viewer, "the back foot lifts its heel toward us, swings forward and
plants farther from the camera", end frame pinned, 5 s. Clean alternating steps, seam 0.45.

**The S walk and run can turn three-quarter too** (necromancer walk, knight run, the golem's and
orc's held). `FRONT_LOCO`, the front mirror of the back walk: "runs straight at the camera, toward the
viewer and straight down the screen ... never turns sideways ... face stays in the centre of his
body", end frame pinned, 5 s, with "running sideways, moving to the right, moving to the left" in the
negative. The elf's S run still turned sideways once; a re-run with the bow named in her hand and
knees lifting toward the camera held head-on.

**N run looked slow.** The player played every direction at the SE fps; the N run loop is 17 source
frames, SE's 28, so N ran about 1.6x slow. Play each direction at its own fps
(`meta.json` `cycles[cycle][facing].fps`).

**Sizes drift between directions.** The N walk recedes as it "walks away" (median height 480 vs SE
542 px), the E run came out 507 vs 551. `process.py` scales each walk, run and idle loop about the
feet to the `size_ref` facing's median height (N walk x1.13, E run x1.09, NE idle x0.955). A side
profile still reads small at equal height (about 25 to 30% less area): per-hero `size_bias: {"e": 1.05}`.
A bias now applies on top of the matched size even when the match was within 3% (an earlier version
skipped the bias there, so a biased row could land 9% big).

**Front and back views read smaller and slower** (orc). After height matching the S and N rows were
as tall as SE yet looked small, and the S and N runs looked slow: seen straight on, the body shows
less depth, and leg swing toward or away from the camera is foreshortened. `size_bias`
`{"s": 1.06, "n": 1.06}` and `fps_scale` `{"s_run": 1.3, "n_run": 1.3}` (1.15 for a hero whose loops
are already short, or it hits the 16 fps cap). Art-direction nudges: judge them next to the diagonals.

**A prop hidden by the body gets reinvented in the back view** (orc). Both N turnarounds were
symmetric but drew the double-bladed axe as a barbell with a blade at each end: from behind it is
mostly hidden, and "double-bladed axe held in front" let the model invent both ends. Say exactly what
part shows and where ("one haft with ONE double-bladed head at the top; from behind only the head
shows past his left hip, on the left of the image") in `turn_notes` and `back_view`.

**Props jump sides between facings.** The necromancer's staff, the knight's scabbard and the elf's
bow and quiver had to stay on the same side of the image they were on in SE and NE. `turn_notes` per
facing names the side for each prop; one elf N option still put the bow on the wrong side, so compare
every turnaround with the notes before picking.

**A glowing prop lights up the backdrop** (necromancer). In the N walk the green-flamed staff turned
into a light source; the video model painted a green-white glow on the magenta around the figure, and
the key left a beige halo in every frame. Every clip prompt says "flat solid magenta background with
no glow or light on it" and every negative has "glowing halo around the character, light spill on the
background". If it still happens, regenerate; the key cannot separate a lit backdrop from the figure.

**A good seam score can hide a 1.5-cycle loop** (knight E walk). The walk hitched: the loop search
picked 32 frames, three steps. In profile the left and right legs look alike, so the seam scored 0.24,
but the wide-stride pose landed unevenly (frames 3, 5 and 8 of 8). Narrow that hero's `ranges` around
the period its other facings found (knight walk [16, 28] gave 26 frames, wide poses at 3 and 7). In a
walk or run row the widest-stride frames should come twice, evenly spaced.

**A half-stride loop** (necromancer E walk). The search took a 19-frame half stride (seam 0.90,
10 fps). With walk [12, 48] it found the 36-frame full stride (seam 0.48).

**A short jitter passes as a run loop** (elf S run). The search locked onto an 8-frame jitter at the
16 fps cap, and a wider range then took two strides (28 frames). Run [14, 22] gave every elf run
15 to 16 frames.

**A directional attack is animated side-on in every facing** (elf). The S and N bow shots aimed
sideways: one "bow shot" text for every facing, and archery is something the model knows side-on.
`attack_facing` per facing, written head-on: S "the arrow tip points directly at the viewer, string
pulled straight back to the chin, shoulders square to the camera"; N "bow tips show above and below
the shoulders from behind, elbow raised behind the head, arrow released straight up the screen". Add
"aiming sideways, arrow pointing left/right" to the negative. The same goes for any aimed or thrust
move (spear, crossbow, gun, spell beam).

**Still to watch** (orc): the E attack impact left a large dust splat in two frames, and the N chop
twisted sideways mid-swing before returning to the back view. Both shipped; regenerate if it matters.

## Things that just worked

- One still with both diagonal facings side by side keeps identity between front and back
  (straight-on poses in a sheet come out turned, see above).
- Mirroring SE, NE and E for SW, NW and W halves the work and is standard sprite practice.
- A magenta backdrop and a chroma key: no video model emits alpha, and magenta rarely appears in
  characters. The key also removes the purple ground shadow the video model adds.
- One shared canvas and palette per hero keeps every cycle registered and consistent.
- Every hero needed one or two redraws or re-runs in the 8-direction pass; plan for them.
