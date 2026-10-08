#!/usr/bin/env python3
"""Make square first frames for the video model from any character art.

The figure is scaled to fig of the frame height with its feet on base, centred,
on a flat key-colour canvas. The headroom is what lets a raised axe or staff
stay inside the clip.

Input can be a generated multi-pose still (split into one column per facing,
cut at the emptiest column near each equal split) or the user's own art: one
figure on a transparent or flat background.
Small pixel art is scaled up with nearest-neighbour so its pixels stay crisp.
It also prints a key check: how much of the character each key colour
(magenta, green, blue) would erase in the clips.

Usage:
  python3 reframe.py <hero> <image> [--facings se,ne]        # split a pose sheet (default: SE left, NE right)
  python3 reframe.py <hero> <image> --facing se [--flip]      # one figure; --flip if the art faces the other way
  options: --out raw --canvas 960 --fig 0.58 --base 0.82 --key magenta|green|blue
           --nearest/--smooth --force
Writes <out>/<hero>_<facing>_still.png; existing frames are kept unless --force.
Needs Python 3 with numpy and Pillow.
"""
import argparse, sys
from pathlib import Path
import numpy as np
from PIL import Image

KEY_RGB = {"magenta": (255, 0, 255), "green": (0, 255, 0), "blue": (0, 0, 255)}


def keyed(rgb):
    """Per key colour, which pixels process.py's key would erase (same tests)."""
    f = rgb.astype(np.float32) / 255
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    sat = (f.max(-1) - f.min(-1)) / (f.max(-1) + 1e-6)
    return {"magenta": ((np.minimum(r, b) - g) > 0.18) & (sat > 0.28) & (np.abs(r - b) < 0.45),
            "green": ((g - np.maximum(r, b)) > 0.18) & (sat > 0.28),
            "blue": ((b - np.maximum(r, g)) > 0.18) & (sat > 0.28)}



def components(mask):
    """4-connected components of a boolean mask, as (ys, xs) index arrays (no scipy needed)."""
    seen = np.zeros_like(mask)
    h, w = mask.shape
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        seen[y0, x0] = True
        stack, ys, xs = [(y0, x0)], [], []
        while stack:
            y, x = stack.pop()
            ys.append(y)
            xs.append(x)
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        yield np.array(ys), np.array(xs)


def foreground(im):
    """Mask of the character: from alpha when the art is a cut-out, otherwise
    everything that differs from the flat colour around the border."""
    rgba = np.array(im.convert("RGBA")).astype(int)
    if (rgba[..., 3] < 128).mean() > 0.02:
        return rgba[..., 3] >= 128, None
    rgb = rgba[..., :3]
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    bg = np.median(border, 0)
    spread = np.abs(border - bg).max(1)
    tol = max(40, int(np.percentile(spread, 90)) + 25)   # tolerate gradients and JPEG noise in the backdrop
    diff = np.abs(rgb - bg).max(-1)
    near = diff <= tol
    # only backdrop-coloured pixels connected to the border are background, so
    # white armour on a white backdrop or a magenta gem on magenta stays in
    region = np.zeros_like(near)
    region[[0, -1], :] = near[[0, -1], :]
    region[:, [0, -1]] |= near[:, [0, -1]]
    while True:
        grown = region.copy()
        grown[1:] |= region[:-1]; grown[:-1] |= region[1:]
        grown[:, 1:] |= region[:, :-1]; grown[:, :-1] |= region[:, 1:]
        grown &= near
        if (grown == region).all():
            break
        region = grown
    fg = ~region
    # backdrop trapped inside the silhouette (between arm and body, bow and string):
    # flat patches of the exact backdrop colour are background too
    saturated = (bg.max() - bg.min()) > 128
    trapped = fg & (diff <= (12 if saturated else 4))
    min_size, removed = 0.002 * fg.sum(), 0
    for comp in components(trapped):
        if len(comp[0]) > min_size:
            fg[comp] = False
            removed += 1
    if removed:
        print(f"removed {removed} patch(es) of backdrop enclosed by the figure; check the frame")
    return fg, near


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hero", help="hero id, used in the file names")
    ap.add_argument("src", help="the still or the user's art")
    ap.add_argument("--facings", default="se,ne", help="pose order, left to right, when splitting a sheet")
    ap.add_argument("--facing", help="the image holds one figure with this facing")
    ap.add_argument("--flip", action="store_true", help="mirror the figure first (art faces SW but you need SE, etc.)")
    ap.add_argument("--out", default="raw")
    ap.add_argument("--canvas", type=int, default=960)
    ap.add_argument("--fig", type=float, default=0.58)
    ap.add_argument("--base", type=float, default=0.82)
    ap.add_argument("--key", default="magenta", choices=list(KEY_RGB))
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--nearest", action="store_true", help="force nearest-neighbour scaling (pixel art)")
    g.add_argument("--smooth", action="store_true", help="force smooth scaling (painted art)")
    ap.add_argument("--force", action="store_true", help="overwrite existing first frames")
    if len(sys.argv) == 1:
        ap.print_help(sys.stderr)
        sys.exit(2)
    a = ap.parse_args()
    if not Path(a.src).is_file():
        ap.error(f"image not found: {a.src}")
    names = [a.facing] if a.facing else a.facings.split(",")
    targets = [Path(a.out) / f"{a.hero}_{f}_still.png" for f in names]
    if any(t.resolve() == Path(a.src).resolve() for t in targets):
        ap.error("an output would replace the input image; use another --out")
    existing = [str(t) for t in targets if t.exists()]
    if existing and not a.force:
        sys.exit("error: would overwrite " + ", ".join(existing) + " (pass --force to replace)")
    S = a.canvas
    FH, BASE = int(S * a.fig), int(S * a.base)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    im = Image.open(a.src)
    if a.flip:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    rgb_im = im.convert("RGBA")
    fg, near = foreground(im)
    W = im.width
    if a.facing:
        parts = [(a.facing, 0, W)]
    else:
        fs = a.facings.split(",")
        # cut at the emptiest column near each equal split, so a wide pose (arms out) isn't sliced
        occ = fg.sum(0)
        cuts = [0]
        for i in range(1, len(fs)):
            c, r = W * i // len(fs), W // (3 * len(fs))
            cuts.append(c - r + int(np.argmin(occ[c - r:c + r])))
        cuts.append(W)
        parts = [(f, cuts[i], cuts[i + 1]) for i, f in enumerate(fs)]

    # key check: the character must not contain the key colour, or those parts vanish in the clips
    # (art cut from a flat backdrop has a rim of backdrop-tinted pixels that should key out; skip it)
    core = fg.copy()
    cut_out = (np.array(rgb_im)[..., 3] < 128).mean() > 0.02
    for _ in range(0 if cut_out else max(2, im.height // 200)):
        core[1:-1, 1:-1] &= core[:-2, 1:-1] & core[2:, 1:-1] & core[1:-1, :-2] & core[1:-1, 2:]
    if near is not None:
        core &= ~near                        # backdrop-coloured pixels are not the character's colours
    hits = {k: float(v[core].mean()) for k, v in keyed(np.array(rgb_im.convert("RGB"))).items()}
    print("key check, share of the figure each key would erase:",
          ", ".join(f"{k} {v:.1%}" for k, v in hits.items()))
    if hits[a.key] > 0.01:
        best = min(hits, key=hits.get)
        print(f"WARNING: --key {a.key} would erase {hits[a.key]:.1%} of the character. "
              f"Use --key {best} ({hits[best]:.1%}) and set \"key\": \"{best}\" in cast.json.")

    for facing, x0, x1 in parts:
        ys, xs = np.where(fg[:, x0:x1])
        if not len(ys):
            raise SystemExit(f"{facing}: no figure found in columns {x0}-{x1}; check the background or --facing")
        box = (xs.min() + x0, ys.min(), xs.max() + x0 + 1, ys.max() + 1)
        fig = rgb_im.crop(box)
        mask = Image.fromarray((fg[box[1]:box[3], box[0]:box[2]] * 255).astype("uint8"))
        # pixel art (a small figure) keeps hard pixels; painted art resamples smoothly
        nearest = a.nearest or (not a.smooth and fig.height < 256)
        if nearest:
            # whole-number scale only, so every source pixel stays a crisp k×k block; the figure then
            # lands near, not exactly on, fig_frac, so process.py should measure it ("fig_frac": "auto")
            k = max(1, round(FH / fig.height))
            while k > 1 and (fig.height * k > BASE or fig.width * k > S):
                k -= 1
            fig, mask = (x.resize((fig.width * k, fig.height * k), Image.NEAREST) for x in (fig, mask))
            colours = len(np.unique(np.array(rgb_im.crop(box).convert("RGB"))[fg[box[1]:box[3], box[0]:box[2]]], axis=0))
            print(f"{facing}: pixel art {fig.height // k} px tall, {colours} colours, scaled x{k} -> "
                  f"set height {fig.height // k}, palette {min(max(colours, 16), 48)} and \"fig_frac\": \"auto\" in cast.json")
        else:
            size = (round(fig.width * FH / fig.height), FH)
            fig, mask = fig.resize(size, Image.LANCZOS), mask.resize(size, Image.LANCZOS)
        if fig.width > S:
            raise SystemExit(f"{facing}: figure is wider than the canvas at --fig {a.fig}; lower --fig")
        out = Image.new("RGB", (S, S), KEY_RGB[a.key])
        out.paste(fig.convert("RGB"), ((S - fig.width) // 2, BASE - fig.height), mask)
        p = Path(a.out) / f"{a.hero}_{facing}_still.png"
        out.save(p)
        print(p, fig.size, "nearest" if nearest else "smooth")


if __name__ == "__main__":
    main()
