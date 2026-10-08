#!/usr/bin/env python3
"""Build every generation request for a cast: the stills each hero still needs
and one image-to-video clip per hero x facing x cycle.

Usage:
  python3 make_prompts.py cast.json [-o prompts.json] [--still-model ID]
                          [--clip-model ID] [--force]

Output: {"stills": [...], "cycles": [...]}. Each entry has "id", "model" and
"params" for model_run. No model is built in: pick them with recommend and
search, pass their ids with --still-model and --clip-model (otherwise "model"
is a placeholder), and read each schema with model_schema_get. The params use
the field names of the families the production ran (an image model with
referenceImages / numOutputs; an image-to-video model with startImage /
endImage / duration / aspectRatio / generateAudio): rename them to the schema
of the model you picked. Stills:
  - hero described in text, no art: one multi-pose still with every facing
    side by side (identity matches between facings). Straight-on facings
    (E, W, S, N) are left out of that sheet (in a sheet they come out a few
    degrees turned): it draws the diagonals, or the first facing alone, and a
    re-run after uploading those gives turnarounds for the rest;
  - hero with first frames already uploaded for some facings (their own art):
    one single-pose "turnaround" request per missing facing, drawn from every
    first frame it already has (and "reference" first when set, max 4 images);
  - hero with every facing uploaded: nothing.
Missing asset ids become "<upload ...>" placeholders; fill cast.json and re-run
with --force (an existing prompts.json is kept otherwise).
"""
import argparse, json, sys
from pathlib import Path

STILL_MODEL = "<image model id: pick with recommend, pass --still-model>"
CLIP_MODEL = "<image-to-video model id: pick with recommend, pass --clip-model>"
KEY = {"magenta": "magenta (#FF00FF)", "green": "green (#00FF00)", "blue": "blue (#0000FF)"}
MIRROR = {"se": "sw", "ne": "nw", "e": "w"}   # facings the sheet gets by flipping, unless listed explicitly
BACK = {"ne", "nw", "n"}                      # back views: need the away-from-viewer run recipe
CAMERA = {
 "isometric": "classic isometric RPG view, seen from about 30 degrees above",
 "topdown": "top-down RPG view, seen from about 45 degrees above",
 "side": "straight side-on view, camera at the character's height, like a 2D platformer",
}

# the Iso Cycles two-pose still, kept verbatim for the default isometric SE + NE cast
STILL_SE_NE = ("{medium} game sprite sheet, two poses of the same character side by side, standing neutral, full body, "
               "on a perfectly flat solid {key} background, no shadows on the ground, no text.\n\n"
               "Character: {character}\n\n"
               "Camera: {camera}.\n"
               "Left pose: body turned three-quarters toward the viewer, facing down and to the right (south-east).\n"
               "Right pose: body turned three-quarters away from the viewer, facing up and to the right (north-east), {back}.\n\n"
               "Style: {style}, each figure about 60% of the image height, both figures the same size and aligned on the "
               "same baseline, generous empty space around each.")
STILL_MULTI = ("{medium} game sprite sheet, {lead}, standing neutral, "
               "full body, on a perfectly flat solid {key} background, no shadows on the ground, no text.\n\n"
               "Character: {character}\n\nCamera: {camera}.\n{poses}\n\n"
               "Style: {style}, each figure about 60% of the image height, all figures the same size and aligned on the "
               "same baseline, generous empty space around each.")
TURNAROUND = ("Redraw the exact same character as in the {refs}: same design, proportions, colours, outfit, "
              "props and art style (if it is pixel art, keep the same pixel size, outline and palette). One single "
              "full-body figure standing neutral, {pose}. Camera: {camera}.{about} The figure is centred, about 60% of "
              "the image height, on a perfectly flat solid {key} background, no ground shadow, no text, nothing else.")
# where a character's right hand appears on screen per facing (for "notes" such as weapon hand): the right
# hand points 90 degrees clockwise from the facing seen from above; screen-down is toward the viewer
RIGHT_SIDE = {"se": "on the left side of the image, nearer to us", "sw": "on the left side of the image, farther from us",
              "ne": "on the right side of the image, nearer to us", "nw": "on the right side of the image, farther from us",
              "e": "nearer to us", "w": "farther from us", "s": "on the left side of the image", "n": "on the right side of the image"}
POSE = {
 "se": "body turned three-quarters toward the viewer, facing down and to the right (south-east)",
 "sw": "body turned three-quarters toward the viewer, facing down and to the left (south-west)",
 "ne": "body turned three-quarters away from the viewer, facing up and to the right (north-east), {back}",
 "nw": "body turned three-quarters away from the viewer, facing up and to the left (north-west), {back}",
 "e":  "full side profile facing right (east), {poss} face pointing at the right edge of the image, seen from the same camera height as the references",
 "w":  "full side profile facing left (west), {poss} face pointing at the left edge of the image, seen from the same camera height as the references",
 "s":  "seen exactly from the front, facing straight toward the viewer (south). Not turned at all: a perfectly symmetrical front view, {poss} head and chest in the exact horizontal centre of the body, both shoulders level and the same size, both arms equally visible on either side of the body, feet side by side",
 "n":  "seen exactly from behind, facing straight away from the viewer (north), {back}. Not turned at all: a perfectly symmetrical back view, the spine in the exact horizontal centre of the body, both shoulders level and the same size, both arms equally visible on either side of the body, feet side by side",
}
NO_REF = ", seen from the same camera height as the references"   # dropped when there are no references
STRAIGHT = {"e", "w", "s", "n"}               # never drawn inside a multi-pose sheet (they come out turned)
DIAGONAL = ["se", "sw", "ne", "nw"]
STILL_PARAMS = {"width": 1536, "height": 1024, "quality": "high", "background": "opaque", "numOutputs": 2}
TURN_PARAMS = {"width": 1024, "height": 1024, "quality": "high", "background": "opaque", "numOutputs": 2}

FACING = {
 "se": "{he} always faces diagonally toward the bottom-right corner of the frame (isometric three-quarter front view from above, the same angle as the first frame), never turning to a side view.",
 "sw": "{he} always faces diagonally toward the bottom-left corner of the frame (isometric three-quarter front view from above, the same angle as the first frame), never turning to a side view.",
 "ne": "{he} always faces diagonally toward the top-right corner of the frame, seen three-quarters from behind (isometric view from above, the same angle as the first frame), never turning around.",
 "nw": "{he} always faces diagonally toward the top-left corner of the frame, seen three-quarters from behind (isometric view from above, the same angle as the first frame), never turning around.",
 "e":  "{he} always faces right in a flat side-on profile, the same angle as the first frame, never turning toward the camera.",
 "w":  "{he} always faces left in a flat side-on profile, the same angle as the first frame, never turning toward the camera.",
 "s":  "{he} always faces straight toward the viewer, seen exactly from the front with {poss} face and chest in the centre of {poss} body (the same angle as the first frame), never turning to either side.",
 "n":  "{he} always faces straight away from the viewer, seen exactly from behind with {poss} spine in the centre of {poss} body (the same angle as the first frame), never turning to either side.",
}
CYCLE = {
 "walk":   "{medium} game sprite animation, like a treadmill: the {who} immediately starts walking in place and keeps walking for the whole clip, a steady repeating walk cycle at a relaxed pace (heel-to-toe steps, arms swing opposite the legs, slight up-and-down bob{extra}).",
 "run":    "{medium} game sprite animation, like a treadmill: the {who} immediately starts running in place and keeps running for the whole clip, a steady repeating run cycle (knees high, arms pumping, torso leaning forward, both feet leave the ground between steps{extra}).",
 "idle":   "{medium} game sprite animation: the {who} stands idle in place, a subtle breathing loop: chest rises and falls, a slight weight shift, {idle}. Feet stay planted. Calm, small motion.",
 "attack": "{medium} game sprite animation: the {who} performs one {attack}, then returns to the starting ready pose. Snappy anticipation, fast strike, short follow-through.",
}
TAIL = " {he} stays centred and does not travel across the frame. Locked static camera, flat solid {keyname} background with no glow or light on it, no ground shadow, {crisp}, same character design as the first frame."
# what "wrong angle" means depends on the facing: a profile is the goal for E/W, the failure for diagonals
WRONG_ANGLE = {"e": "front view, back view, three-quarter view, facing the camera, turning around",
               "s": "side view, profile view, back view, turning around",
               "n": "side view, profile view, facing the camera, turning around"}
WRONG_ANGLE["w"] = WRONG_ANGLE["e"]
NEG_REST = "glowing halo around the character, light spill on the background, camera movement, zoom, travelling across the frame, ground shadow, drop shadow, background change, extra characters, blur, 3D render"
NEG_LOCO = ", slowing down, stopping, standing still"

# Back-view run: a fast run from a back three-quarter frame drifts into a side-on
# profile. Describing it as running *away* from the viewer, naming what stays
# visible, pinning the end frame and giving it 5 s holds the angle; the loop
# search then takes the middle of the clip.
AWAY = {"ne": ("toward the top-right corner of the screen", "{poss} left shoulder is closer to us than {poss} right"),
        "nw": ("toward the top-left corner of the screen", "{poss} right shoulder is closer to us than {poss} left"),
        "n":  ("straight up the screen", "both shoulders stay level and {poss} spine stays in the centre of {poss} body")}
BACK_RUN = ("{medium} game sprite animation seen from behind. The {who} runs away from the viewer, {toward}, on a "
            "treadmill so {it} stays in place. We keep seeing {back_view} at the same {angle} as the first frame for "
            "the whole clip: {shoulders}. Steady repeating run cycle, knees high, arms pumping, both feet leave the "
            "ground briefly between steps{extra}. Locked static camera, flat solid {keyname} background, no ground "
            "shadow, {crisp}.")
BACK_RUN_NEG = ("glowing halo around the character, light spill on the background, side view, profile view, facing right, facing the camera, turning, rotating, camera movement, zoom, "
                "travelling across the frame, ground shadow, background change, blur, 3D render, slowing down, stopping")

# Side-view walk/run (isometric E/W): with the plain treadmill prompt the figure turns
# toward the camera for part of every stride (Iso Cycles v2, golem E). Same cure as
# the back-view run: say where it's heading, name what stays visible, pin the end
# frame and give it 5 s.
SIDE = {"e": ("right", "right"), "w": ("left", "left")}   # heading edge, side of the body we see
GAIT = {"walk": ("walks", "Steady repeating walk cycle at a relaxed pace, heel-to-toe steps, arms swing opposite "
                          "the legs, slight up-and-down bob"),
        "run": ("runs", "Steady repeating run cycle, knees high, arms pumping, torso leaning forward, both feet "
                        "leave the ground briefly between steps")}
SIDE_LOCO = ("{medium} game sprite animation in side profile. The {who} {verb} toward the {edge} edge of the screen, "
             "on a treadmill so {it} stays in place. We keep seeing {poss} {side} side in profile at the same angle as "
             "the first frame for the whole clip: {poss} face points at the {edge} edge of the frame and we never see "
             "{poss} chest or {poss} back. {gait}{extra}. Locked static camera, flat solid {keyname} background, no "
             "ground shadow, {crisp}.")
SIDE_NEG = ("glowing halo around the character, light spill on the background, front view, three-quarter view, facing the camera, turning toward the camera, back view, turning, "
            "rotating, camera movement, zoom, travelling across the frame, ground shadow, background change, blur, "
            "3D render, slowing down, stopping")

# Straight-behind walk (N): with the plain treadmill prompt the legs read as walking
# backwards (Iso Cycles v2, golem; playing the loop in reverse wasn't enough). The
# away-from-viewer recipe with the stride spelled out fixes it.
BACK_WALK = ("{medium} game sprite animation seen from behind. The {who} walks away from the viewer, straight up the "
             "screen, on a treadmill so {it} stays in place. We keep seeing {back_view} at the same angle as the first "
             "frame for the whole clip: both shoulders stay level and {poss} spine stays in the centre of {poss} body. "
             "Each step pushes forward, away from us: the back foot lifts its heel toward us, swings forward and plants "
             "farther from the camera. Steady repeating walk cycle at a relaxed pace, arms swing opposite the legs, slight "
             "up-and-down bob{extra}. Locked static camera, flat solid {keyname} background with no glow or light on it, no ground shadow, {crisp}.")

# S walk and run: the plain treadmill prompt turned three-quarter (necro S walk, knight S run, v2)
FRONT_LOCO = ("{medium} game sprite animation seen from the front. The {who} {verb} straight at the camera, toward the viewer and straight down the "
              "screen, on a treadmill so {it} stays in place. {he} never turns sideways: we keep seeing {poss} face and chest straight on at the same "
              "angle as the first frame for the whole clip: both shoulders stay level and {poss} face stays in the centre of "
              "{poss} body, never turning to either side. {gait}{extra}. Locked static camera, flat solid {keyname} background with no glow or "
              "light on it, no ground shadow, {crisp}.")
FRONT_NEG = ("glowing halo around the character, light spill on the background, side view, profile view, running sideways, "
             "walking sideways, moving to the right, moving to the left, three-quarter "
             "view, turning, rotating, back view, camera movement, zoom, travelling across the frame, ground shadow, "
             "background change, blur, 3D render, slowing down, stopping")

POSS = {"he": "his", "she": "her", "it": "its", "they": "their"}


def words(h, hid, keyname):
    d = dict(h)
    d.setdefault("who", "character")
    d["he"] = h.get("pronoun", "It")
    d["it"] = d["he"].lower()
    d["poss"] = POSS.get(d["it"], "its")
    d.setdefault("extra", "")
    d.setdefault("idle", "a gentle sway")
    d.setdefault("attack", f"quick strike with {d['poss']} weapon, or a punch if {d['it']} has none")
    d.setdefault("back", "we see the back")
    d.setdefault("back_view", f"{d['poss']} back")
    d["keyname"] = keyname
    # painted / HD heroes ("pixel": false) must not be pushed toward pixel art by the prompts
    pixel = h.get("pixel", True)
    d["medium"] = "Pixel art" if pixel else "2D"
    d["crisp"] = "crisp pixel art" if pixel else "the exact art style, detail and sharpness of the first frame"
    return d


def cycle_request(hid, d, facing, cy, still):
    # "attack_facing": {"s": "...", "n": "..."}: a move written for one facing. A bow shot or a thrust described once
    # gets animated side-on in every facing (the model's default view of it); front and back need it said head-on.
    if cy == "attack" and d.get("attack_facing", {}).get(facing):
        d = dict(d, attack=d["attack_facing"][facing])
    if facing in BACK and cy == "run":
        toward, shoulders = AWAY[facing]
        params = {"prompt": BACK_RUN.format(toward=toward, shoulders=shoulders.format(**d),
                                            angle="angle" if facing == "n" else "diagonal angle", **d),
                  "negativePrompt": BACK_RUN_NEG, "startImage": still, "endImage": still, "duration": "5"}
    elif facing == "s" and cy in GAIT:
        verb, gait = GAIT[cy]
        params = {"prompt": FRONT_LOCO.format(verb=verb, gait=gait, **d), "negativePrompt": FRONT_NEG,
                  "startImage": still, "endImage": still, "duration": "5"}
    elif facing == "n" and cy == "walk":
        params = {"prompt": BACK_WALK.format(**d),
                  "negativePrompt": BACK_RUN_NEG + ", walking backwards, walking toward the camera",
                  "startImage": still, "endImage": still, "duration": "5"}
    elif facing in SIDE and cy in GAIT:
        edge, side = SIDE[facing]
        verb, gait = GAIT[cy]
        params = {"prompt": SIDE_LOCO.format(verb=verb, edge=edge, side=side, gait=gait, **d),
                  "negativePrompt": SIDE_NEG, "startImage": still, "endImage": still, "duration": "5"}
    else:
        params = {"prompt": (CYCLE[cy] + " " + FACING[facing] + TAIL).format(**d),
                  "negativePrompt": WRONG_ANGLE.get(facing, "side view, profile view, turning around") + ", " + NEG_REST
                                    + (NEG_LOCO if cy in ("walk", "run") else ""),
                  "startImage": still, "duration": "3"}
        # loops that come back to rest pin the end frame; a pinned end on a 3 s
        # walk/run makes the model start and stop the gait inside the clip
        if cy not in ("walk", "run"):
            params["endImage"] = still
    params.update(aspectRatio="1:1", generateAudio=False)
    return {"id": f"{hid}_{facing}_{cy}", "model": CLIP_MODEL, "params": params}


def main():
    global STILL_MODEL, CLIP_MODEL
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cast", help="cast.json")
    ap.add_argument("-o", "--out", default="prompts.json", help="where to write the requests")
    ap.add_argument("--still-model", help="model id for stills and turnarounds (from recommend / search)")
    ap.add_argument("--clip-model", help="model id for the image-to-video clips (from recommend / search)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing output file")
    if len(sys.argv) == 1:
        ap.print_help(sys.stderr)
        sys.exit(2)
    a = ap.parse_args()
    if not Path(a.cast).is_file():
        ap.error(f"cast file not found: {a.cast}")
    if Path(a.out).resolve() == Path(a.cast).resolve():
        ap.error("the output would replace the cast file")
    if Path(a.out).exists() and not a.force:
        sys.exit(f"error: would overwrite {a.out} (pass --force to replace it, e.g. after adding asset ids)")
    STILL_MODEL = a.still_model or STILL_MODEL
    CLIP_MODEL = a.clip_model or CLIP_MODEL
    cast = json.loads(Path(a.cast).read_text())
    style = cast.get("style", "crisp hand-placed pixel art, 1px dark outline, limited palette of about 24 colours")
    # (per-hero "pixel": false switches the prompt wording; give such casts their own "style" too)
    facings = cast.get("facings", ["se", "ne"])
    camera = CAMERA.get(cast.get("camera", "isometric"), cast.get("camera"))
    key = KEY[cast.get("key", "magenta")]
    keyname = cast.get("key", "magenta")
    out = {"stills": [], "cycles": []}
    for hid, h in cast["heroes"].items():
        d = words(h, hid, keyname)
        stills = h.get("stills", {})
        missing = [f for f in facings if f not in stills]
        reference = h.get("reference")        # their art when it isn't one of the facings (e.g. 3/4 art, side-scroller)
        if missing and not stills and not reference:
            if "character" not in h:
                raise SystemExit(f"{hid}: needs a 'character' description or at least one uploaded first frame in 'stills'")
            # straight-on facings (E/W/S/N) drawn inside a multi-pose sheet come out a few degrees
            # turned (Iso Cycles v2): the sheet draws the diagonals (or the first facing alone),
            # and a re-run after uploading those gives single-pose turnarounds for the rest
            sheet = facings
            later = []
            if STRAIGHT & set(facings):
                if "se" in facings and "ne" in facings:
                    sheet = ["se", "ne"]
                else:
                    sheet = [f for f in facings if f in DIAGONAL] or facings[:1]
                later = [f for f in facings if f not in sheet]
            if later:
                print(f"note: {hid}: the still draws {', '.join(sheet).upper()} only. After reframing and uploading "
                      f"{'those first frames' if len(sheet) > 1 else 'that first frame'}, re-run make_prompts.py: it "
                      f"emits single-pose turnarounds for {', '.join(later).upper()} (straight-on poses in a sheet come "
                      f"out turned).")
            if sheet == ["se", "ne"]:
                prompt = STILL_SE_NE.format(key=key, camera=camera, style=style, **d)
            else:
                if len(sheet) == 1:
                    lead, poses = "one pose of the character", "Pose: " + POSE[sheet[0]].format(**d).replace(NO_REF, "") + "."
                else:
                    lead = f"{len(sheet)} poses of the same character side by side in one row"
                    poses = "Poses from left to right:\n" + "\n".join(
                        f"{i + 1}. {POSE[f].format(**d).replace(NO_REF, '')}" for i, f in enumerate(sheet))
                prompt = STILL_MULTI.format(lead=lead, key=key, camera=camera, style=style, poses=poses, **d)
            out["stills"].append({"id": f"{hid}_still", "model": STILL_MODEL, "split": sheet,
                                  "params": {"prompt": prompt, **(TURN_PARAMS if len(sheet) == 1 else STILL_PARAMS)}})
        elif missing:
            # the user's own art is the master; every facing already drawn helps the model see the whole character
            refs = ([reference] if reference else []) + list(stills.values())[:4 - bool(reference)]
            for f in missing:
                about = ""
                if h.get("character"):
                    about += f" The character: {h['character']}"
                # "turn_notes": {"n": "only the axe head shows past his left hip"}: what this facing must show,
                # e.g. which side of the image a prop sits on, or the visible part of a prop the body hides
                if h.get("turn_notes", {}).get(f):
                    about += " " + h["turn_notes"][f]
                if h.get("notes"):
                    about += (f" Important: {h['notes']} Do not mirror the character: in this pose "
                              f"{d['poss']} right hand is {RIGHT_SIDE[f]}.")
                out["stills"].append({"id": f"{hid}_{f}_turnaround", "model": STILL_MODEL, "facing": f,
                                      "params": {"prompt": TURNAROUND.format(
                                                     refs="reference images" if len(refs) > 1 else "reference image",
                                                     pose=POSE[f].format(**d), camera=camera, key=key, about=about),
                                                 "referenceImages": refs, **TURN_PARAMS}})
        for f in facings:
            for cy in cast.get("cycles", list(CYCLE)):
                if cy not in CYCLE:
                    raise SystemExit(f"no prompt template for cycle '{cy}': add one to CYCLE in make_prompts.py")
                out["cycles"].append(cycle_request(hid, d, f, cy, stills.get(f, f"<upload {hid}_{f}_still.png>")))
    Path(a.out).write_text(json.dumps(out, indent=1))
    long_clips = sum(c["params"]["duration"] == "5" for c in out["cycles"])
    print(f"{len(out['stills'])} still requests (2 outputs each), {len(out['cycles'])} clips "
          f"({len(out['cycles']) - long_clips} at 3 s, {long_clips} at 5 s) -> {a.out}. Price one of each kind "
          f"with model_run dry_run=true and tell the user the total before running anything.")
    if not (a.still_model and a.clip_model):
        print("note: no --still-model / --clip-model given: the \"model\" fields are placeholders.")
    for f in facings:
        if f in MIRROR and MIRROR[f] not in facings:
            print(f"note: {MIRROR[f].upper()} will be a mirror of {f.upper()}. If the character is asymmetric "
                  f"(weapon hand, eyepatch, one pauldron), add '{MIRROR[f]}' to facings to generate it instead.")


if __name__ == "__main__":
    main()
