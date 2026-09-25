"""Solo character shots: reference tile -> pixel-art background + separate character layer (for parallax)."""
import sys, os; sys.path.insert(0, os.path.dirname(__file__))
from pixlib import *
import cv2
from scipy import ndimage
PAL = [tuple(c) for c in json.load(open(os.path.join(ROOT, '.tesseract-work', 'palette.json')))]
W = 192  # 12 art px wider than the frame -> room for a slow drift

def clean_mask(m, min_px=25):
    lab, n = ndimage.label(m)
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    keep = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s >= min_px])
    return ndimage.binary_fill_holes(keep)

def solo(name, cut=True):
    tile, mask = load_tile(name, 'isnet-general-use')
    H = round(tile.height * W / tile.width)
    px = pixelate(tile, (W, H))
    out = {}
    if cut:
        m = mask.resize((W, H), Image.BOX)
        mb = clean_mask(np.asarray(m) > 140)
        # background: remove the figure (dilated) and inpaint from the surroundings
        hole = ndimage.binary_dilation(mb, iterations=3).astype(np.uint8) * 255
        bg = cv2.inpaint(np.asarray(px)[:, :, ::-1].copy(), hole, 6, cv2.INPAINT_TELEA)[:, :, ::-1]
        bgq = quantize(Image.fromarray(bg), PAL)
        chq = quantize(px, PAL).convert('RGBA')
        a = np.asarray(chq).copy(); a[:, :, 3] = np.where(mb, 255, 0)
        ch = Image.fromarray(a, 'RGBA')
        out['bg'] = save(bgq, f'{name}-bg.png'); out['char'] = save(ch, f'{name}-char.png')
        comp = bgq.convert('RGBA'); comp.alpha_composite(ch)
    else:
        comp = quantize(px, PAL).convert('RGBA'); out['bg'] = save(comp.convert('RGB'), f'{name}-bg.png')
    out['artSize'] = [W, H]
    return comp, out

def main():
    info = {}
    comps = []
    for n, cut in [('nemmy', True), ('yumi', True), ('aiko', True), ('baer', False)]:
        comp, o = solo(n, cut); info[n] = o; comps.append(comp)
    json.dump(info, open(os.path.join(ROOT, '.tesseract-work', 'solo-art.json'), 'w'), indent=1)
    sheet = Image.new('RGB', (4 * 196 * 2, 340 * 2), (20, 20, 20))
    for i, c in enumerate(comps):
        sheet.paste(c.convert('RGB').resize((c.width * 2, c.height * 2), Image.NEAREST), (i * 196 * 2, 0))
    sheet.save(os.path.join(ROOT, '.tesseract-work', 'checks', 'solo-v1.png'))
    print(json.dumps(info, indent=1))


if __name__ == '__main__':
    main()
