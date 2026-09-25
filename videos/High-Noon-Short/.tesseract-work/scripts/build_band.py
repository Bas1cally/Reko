"""Band line-up for the finale (S7): cut-out sprites from the styled tiles, pixelated at their own scale,
with a 1-art-px outline. Baer's drum kit uses a GrabCut refinement seeded by two segmentation masks."""
import sys, os; sys.path.insert(0, os.path.dirname(__file__))
from pixlib import *
import cv2
from scipy import ndimage
from build_solo import clean_mask
PAL = [tuple(c) for c in json.load(open(os.path.join(ROOT, '.tesseract-work', 'palette.json')))]

def baer_mask():
    tile, m1 = load_tile('baer', 'isnet-general-use')
    _, m2 = load_tile('baer', 'u2net_human_seg')
    a1, a2 = np.asarray(m1) > 128, np.asarray(m2) > 128
    img = np.asarray(tile)[:, :, ::-1].copy(); h, w = a1.shape
    gc = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
    kit = np.zeros((h, w), bool); kit[int(h * 0.55):, :] = True          # drum kit zone
    gc[kit] = cv2.GC_PR_FGD
    gc[a1 | a2] = cv2.GC_FGD
    gc[:int(h * 0.12), :] = cv2.GC_BGD                                     # sky strip
    edge = np.zeros((h, w), bool); edge[:, :4] = edge[:, -4:] = True; edge[int(h * 0.55):int(h * 0.62), :] &= False
    gc[edge & ~kit] = cv2.GC_BGD
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(img, gc, None, bgd, fgd, 6, cv2.GC_INIT_WITH_MASK)
    m_gc = (gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD)
    # upper body from the two person/object masks (raised arms, hat); kit from GrabCut only low down,
    # which drops the cymbals that GrabCut turned into blobs beside him
    split = int(h * 0.62)
    m = np.zeros_like(m_gc); m[:split] = (a1 | a2)[:split]; m[split:] = m_gc[split:]
    m = ndimage.binary_opening(m, iterations=1)
    return tile, Image.fromarray((m * 255).astype(np.uint8))

def peel_light_fringe(rgb, mb, iters=3, lum=120, sat=60):
    """Drop pale, unsaturated boundary pixels (sun-halo remnants around Nemmy's hair)."""
    rgb = rgb[:, :, :3].astype(int)
    L = rgb @ np.array([299, 587, 114]) / 1000
    S = rgb.max(axis=2) - rgb.min(axis=2)
    for _ in range(iters):
        edge = mb & ~ndimage.binary_erosion(mb)
        drop = edge & (L > lum) & (S < sat)
        if not drop.any(): break
        mb = mb & ~drop
    return mb

def rim_light(a, strength=0.3, min_lum=70):
    """Warm 1-px top rim on lit pixels whose upper neighbour is transparent (noon sun from above).
    Dark pixels (black hair, leather) are skipped - mixing cream into them reads as a grey fringe."""
    al = a[:, :, 3] > 0
    top = al.copy(); top[1:] &= ~al[:-1]
    rgb = a[:, :, :3].astype(float)
    top &= (rgb @ np.array([0.299, 0.587, 0.114])) >= min_lum
    rgb[top] = rgb[top] * (1 - strength) + np.array(CREAM) * strength
    a[:, :, :3] = rgb.astype(np.uint8)
    return a

def draw_sticks(a, scale):
    """Baer's drumsticks (lost by segmentation): from each raised fist, up and slightly outward."""
    al = a[:, :, 3] > 0; h, w = al.shape
    im = Image.fromarray(a, 'RGBA'); d = ImageDraw.Draw(im)
    L = int(round(48 * scale))
    for side, xr in (('L', (0, int(w * 0.38))), ('R', (int(w * 0.62), w))):
        ys, xs = np.where(al[:int(h * 0.45), xr[0]:xr[1]])
        if len(ys) == 0: continue
        i = np.argmin(ys); fx, fy = xs[i] + xr[0], ys[i]
        dx = -0.4 if side == 'L' else 0.4
        tip = (fx + dx * L, fy - L)
        d.line([(fx, fy + 2), tip], fill=tuple(OUT) + (255,), width=3)
        d.line([(fx, fy + 2), tip], fill=tuple(C['wood5']) + (255,), width=1)
    return np.asarray(im).copy()

def sprite(name, scale):
    if name == 'baer': tile, mask = baer_mask()
    else: tile, mask = load_tile(name, 'isnet-general-use')
    w, h = round(tile.width * scale), round(tile.height * scale)
    px = quantize(pixelate(tile, (w, h)), PAL)
    mb = clean_mask(np.asarray(mask.resize((w, h), Image.BOX)) > 140, min_px=12)
    if name == 'nemmy': mb = peel_light_fringe(np.asarray(px), mb)
    pad = 2
    a = np.zeros((h + 2 * pad, w + 2 * pad, 4), np.uint8)
    a[pad:pad + h, pad:pad + w, :3] = np.asarray(px); a[pad:pad + h, pad:pad + w, 3] = np.where(mb, 255, 0)
    a = rim_light(a)
    if name == 'baer': a = draw_sticks(a, scale)
    ol = outline(Image.fromarray(a[:, :, 3]))
    a[ol] = list(OUT) + [255]
    return Image.fromarray(a, 'RGBA')

# scale and placement in FRAME coords at the end of the tilt (top-left of sprite incl. 2px pad)
BAND = {  # name: (scale, x, y)
    'baer':  (0.36, 48, 100),
    'yumi':  (0.43, -14, 150),
    'aiko':  (0.43, 96, 152),
    'nemmy': (0.50, 36, 144),
}
ORDER = ['baer', 'yumi', 'aiko', 'nemmy']   # back to front

if __name__ == '__main__':
    out = {}
    for n in ORDER:
        s, x, y = BAND[n]; im = sprite(n, s); save(im, f'band-{n}.png'); out[n] = {'scale': s, 'frameXY': [x, y], 'size': [im.width, im.height]}
    json.dump(out, open(os.path.join(ROOT, '.tesseract-work', 'band-art.json'), 'w'), indent=1)
    print(json.dumps(out))
