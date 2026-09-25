"""Shared pixel-art helpers for the High Noon short.
Art is authored at 1 art px = 6 screen px (canvas 180x320 art = 1080x1920)."""
from PIL import Image, ImageDraw, ImageFilter
import numpy as np, os, json

P = 6
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SRC = os.path.join(ROOT, '.tesseract-work', 'art-src')
ART = os.path.join(ROOT, 'Art')

def hexrgb(h): h = h.lstrip('#'); return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

# Brand colours from the brief
OUT, CREAM, GOLD, DGOLD = hexrgb('241209'), hexrgb('FAF0D6'), hexrgb('FFC634'), hexrgb('DE8E1E')
# Scene colours (high-noon western, matched to the reference tiles' sky and sand)
C = dict(
    sky0=hexrgb('3FB3C4'), sky1=hexrgb('5CC8CF'), sky2=hexrgb('7DD8D3'), sky3=hexrgb('A3E5D8'), sky4=hexrgb('C8F0DE'),
    sunW=hexrgb('FFFDF2'), sun1=hexrgb('FFF2C2'), sun2=hexrgb('FFE38A'),
    mesa0=hexrgb('C98E73'), mesa1=hexrgb('B37661'), mesa2=hexrgb('E0B39A'),
    far0=hexrgb('7FA9A6'), far1=hexrgb('97BDB6'),
    wood0=hexrgb('3A2414'), wood1=hexrgb('5C3A22'), wood2=hexrgb('7E5433'), wood3=hexrgb('A07043'), wood4=hexrgb('C69461'), wood5=hexrgb('E0B77F'),
    paintR=hexrgb('8E3B2E'), paintR2=hexrgb('B0503A'), paintB=hexrgb('4E6E78'), paintB2=hexrgb('6C8E94'), paintG=hexrgb('7C7A4A'),
    sand0=hexrgb('9C7446'), sand1=hexrgb('BE9360'), sand2=hexrgb('D6AF7A'), sand3=hexrgb('E6C893'), sand4=hexrgb('F0DAAE'),
    win=hexrgb('2A1B14'), win2=hexrgb('3E2A1F'), glass=hexrgb('6FA3A3'),
    stone0=hexrgb('6E5F55'), stone1=hexrgb('8F7E70'), stone2=hexrgb('B5A08C'),
    red=hexrgb('9E2A2B'), metal0=hexrgb('5B5E61'), metal1=hexrgb('9A9EA0'), metal2=hexrgb('D3D6D3'),
    black=hexrgb('17110F'), crow=hexrgb('1C1718'), crow2=hexrgb('3A3336'),
)

def up(img, s=P):
    """Nearest-neighbour upscale art -> screen pixels (the only scaling pixel art ever gets)."""
    return img.resize((img.width * s, img.height * s), Image.NEAREST)

def save(img, name):
    os.makedirs(ART, exist_ok=True)
    path = os.path.join(ART, name)
    up(img).save(path, optimize=True)
    return path

def palette_image(colors):
    flat = []
    for c in colors: flat += list(c)
    flat += list(colors[-1]) * (256 - len(colors))
    pal = Image.new('P', (1, 1)); pal.putpalette(flat); return pal

def quantize(img_rgb, colors):
    """Map to a fixed palette with no dithering (flat pixel-art clusters)."""
    return img_rgb.convert('RGB').quantize(palette=palette_image(colors), dither=Image.Dither.NONE).convert('RGB')

def pixelate(img_rgb, size, prefilter=True):
    im = img_rgb.convert('RGB')
    if prefilter:
        im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
    return im.resize(size, Image.BOX)

def outline(alpha, color=OUT):
    """1-art-px outer outline around an alpha silhouette (4-neighbour)."""
    a = np.asarray(alpha) > 127
    o = np.zeros_like(a)
    o[1:, :] |= a[:-1, :]; o[:-1, :] |= a[1:, :]; o[:, 1:] |= a[:, :-1]; o[:, :-1] |= a[:, 1:]
    o &= ~a
    return o

# Dark separator strips measured at the edges of each styled full-body tile (left, right), +1px JPEG margin
TILE_INSET = {'nemmy': (3, 3), 'yumi': (2, 3), 'aiko': (8, 4), 'baer': (3, 7)}

def load_tile(name, mask_model=None):
    """Styled full-body tile (and optional segmentation mask) with the sheet's dark edge strips removed."""
    l, r = TILE_INSET[name]
    tile = Image.open(os.path.join(SRC, f'{name}-styled-full.png')).convert('RGB')
    box = (l, 0, tile.width - r, tile.height)
    tile = tile.crop(box)
    if mask_model is None: return tile
    m = Image.open(os.path.join(SRC, f'{name}-styled-full.mask-{mask_model}.png')).convert('L').crop(box)
    return tile, m
