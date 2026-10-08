#!/usr/bin/env python3
"""8-direction preview: every facing of a hero laid out as a compass, one cycle after another.

Usage:
  python3 compass_gif.py <hero> [cycles ...] [--sprites sprites] [--out qa] [--force]

Reads <sprites>/meta.json and <sprites>/<hero>_<cycle>.png (from process.py), default cycles walk and run,
and writes <out>/<hero>_8dir_preview.gif: NW N NE / W . E / SW S SE, the cycle name in the middle.
Every row should read the same height and speed; a facing missing from the sheet stays empty.
An existing GIF is kept unless --force. Needs Python 3 with Pillow.
"""
import argparse, json, sys
from pathlib import Path
from PIL import Image, ImageDraw


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hero")
    ap.add_argument("cycles", nargs="*", default=["walk", "run"])
    ap.add_argument("--sprites", default="sprites", help="folder with meta.json and the sheets")
    ap.add_argument("--out", default="qa")
    ap.add_argument("--force", action="store_true", help="overwrite an existing preview")
    if len(sys.argv) == 1:
        ap.print_help(sys.stderr)
        sys.exit(2)
    a = ap.parse_args()
    meta_path = Path(a.sprites) / "meta.json"
    if not meta_path.is_file():
        ap.error(f"{meta_path} not found: run process.py first")
    meta = json.loads(meta_path.read_text())
    if a.hero not in meta:
        ap.error(f"{a.hero} is not in {meta_path}")
    target = Path(a.out) / f"{a.hero}_8dir_preview.gif"
    if target.exists() and not a.force:
        sys.exit(f"error: would overwrite {target} (pass --force to replace)")
    m = meta[a.hero]
    cw, ch = m["cell"]
    rows = m["rows"]
    order = ["nw", "n", "ne", "w", "", "e", "sw", "s", "se"]
    Z = 2 if m["height"] >= 80 else 3
    frames = []
    for cy in a.cycles:
        sheet = Path(a.sprites) / f"{a.hero}_{cy}.png"
        if not sheet.is_file():
            ap.error(f"{sheet} not found")
        im = Image.open(sheet).convert("RGBA")
        for k in range(16):
            fr = Image.new("RGBA", (cw * 3 * Z, ch * 3 * Z), (29, 31, 41, 255))
            d = ImageDraw.Draw(fr)
            for i, f in enumerate(order):
                x, y = (i % 3) * cw * Z, (i // 3) * ch * Z
                if not f:
                    d.text((x + cw * Z // 2 - 14, y + ch * Z // 2), cy.upper(), fill=(233, 184, 92))
                    continue
                if f not in rows:
                    continue
                r = rows.index(f)
                c = im.crop(((k % 8) * cw, r * ch, (k % 8 + 1) * cw, (r + 1) * ch)).resize((cw * Z, ch * Z), Image.NEAREST)
                fr.alpha_composite(c, (x, y))
                d.text((x + 6, y + 6), f.upper(), fill=(169, 175, 189))
            frames.append(fr.convert("RGB"))
    target.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(target, save_all=True, append_images=frames[1:], duration=140, loop=0)
    print(target)


if __name__ == "__main__":
    main()
