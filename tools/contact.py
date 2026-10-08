#!/usr/bin/env python3
"""Contact sheet for the continuity check: images side by side, labelled,
optionally with a vertical centre line (S and N symmetry check).

Usage:
  contact.py out.png img1 img2 ... [--size 360] [--cols 4] [--centre]
  contact.py out.png clips/x.mp4 --frames 8      # 8 frames evenly from a clip
"""
import argparse, subprocess, sys, tempfile
from pathlib import Path
from PIL import Image, ImageDraw


def clip_frames(path, n):
    with tempfile.TemporaryDirectory() as d:
        dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                             "-of", "csv=p=0", str(path)]).decode().strip())
        out = []
        for i in range(n):
            t = dur * (i + 0.5) / n
            f = Path(d) / f"{i}.png"
            subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1", str(f)],
                           check=True)
            out.append((f"{Path(path).stem} {t:.1f}s", Image.open(f).convert("RGB").copy()))
        return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("images", nargs="+")
    ap.add_argument("--size", type=int, default=360)
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--frames", type=int, default=0, help="frames per video")
    ap.add_argument("--centre", action="store_true", help="draw a vertical centre line")
    if len(sys.argv) == 1:
        ap.print_help(sys.stderr)
        sys.exit(2)
    a = ap.parse_args()
    tiles = []
    for p in a.images:
        if p.endswith((".mp4", ".mov", ".webm")):
            tiles += clip_frames(p, a.frames or 8)
        else:
            tiles.append((Path(p).stem, Image.open(p).convert("RGB")))
    S, lab = a.size, 22
    cols = min(a.cols, len(tiles))
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * S, rows * (S + lab)), (40, 40, 40))
    dr = ImageDraw.Draw(sheet)
    for i, (name, im) in enumerate(tiles):
        im.thumbnail((S, S))
        x, y = (i % cols) * S, (i // cols) * (S + lab)
        sheet.paste(im, (x + (S - im.width) // 2, y + lab + (S - im.height) // 2))
        dr.text((x + 4, y + 4), name[:48], fill=(255, 255, 255))
        if a.centre:
            dr.line([(x + S // 2, y + lab), (x + S // 2, y + lab + S)], fill=(0, 255, 255), width=1)
    sheet.save(a.out)
    print(a.out, sheet.size)


if __name__ == "__main__":
    main()
