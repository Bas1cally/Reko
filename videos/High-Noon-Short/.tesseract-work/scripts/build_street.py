"""Main Street (side view) as separate parallax layers, drawn procedurally at art resolution.
World: 240 x 440 art px. S1 frames world y 120..440; S7 tilts from y 0 to y 120."""
import sys, os, random, math; sys.path.insert(0, os.path.dirname(__file__))
from pixlib import *
from PIL import ImageFont
random.seed(12)
W, H = 240, 440
# world placement of each layer (art px, top-left) - shared by preview and Tesseract assembly
LAYOUT = {'street-sky': (0, 0), 'street-far': (0, 182), 'street-mesas': (0, 206), 'street-facades': (0, 0),
          'street-ground': (0, 350), 'street-fg': (-10, 0), 'street-sun-s7': (80, 14), 'street-sun-s1': (86, 118)}
BASE = 340          # boardwalk top / facade base
STREET = 350        # street starts
PS2P = os.path.join(ROOT, 'Sources', 'fonts', 'PressStart2P-Regular.ttf')
FONT8 = ImageFont.truetype(PS2P, 8)
BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0

def rgba(c, a=255): return tuple(c) + (a,)

def new(w=W, h=H): return Image.new('RGBA', (w, h), (0, 0, 0, 0))

def pixtext(d, xy, text, fill):
    """Crisp 8px Press Start 2P (1 font pixel = 1 art pixel), no anti-aliasing."""
    d.fontmode = '1'; d.text(xy, text, font=FONT8, fill=fill)

def gradient(img, y0, y1, stops, x0=0, x1=None):
    """Vertical dithered gradient through colour stops."""
    x1 = img.width if x1 is None else x1
    px = img.load()
    for y in range(y0, y1):
        t = (y - y0) / max(1, (y1 - y0 - 1)) * (len(stops) - 1)
        i = min(int(t), len(stops) - 2); f = t - i
        for x in range(x0, x1):
            px[x, y] = rgba(stops[i + 1] if f > BAYER[y % 4, x % 4] else stops[i])

# ---------------------------------------------------------------- sky
def sky():
    im = new(W, H); gradient(im, 0, H, [C['sky0'], C['sky1'], C['sky2'], C['sky3'], C['sky4']])
    d = ImageDraw.Draw(im)
    # a few flat high-noon cloud wisps
    for cx, cy, w in [(30, 70, 34), (170, 128, 44), (95, 190, 26), (205, 36, 22)]:
        d.rectangle([cx, cy, cx + w, cy + 1], fill=rgba(C['sky4']))
        d.rectangle([cx + 5, cy - 1, cx + w - 8, cy - 1], fill=rgba(C['sky4']))
        d.rectangle([cx + 8, cy + 2, cx + w - 4, cy + 2], fill=rgba(C['sky3']))
    return im

def sun():
    S = 80; im = new(S, S); px = im.load(); c = S / 2 - 0.5
    for y in range(S):
        for x in range(S):
            r = math.hypot(x - c, y - c)
            if r <= 11: col = C['sunW']
            elif r <= 13: col = C['sun1']
            elif r <= 16: col = C['sun1'] if BAYER[y % 4, x % 4] < 0.5 else C['sun2']
            elif r <= 20: col = C['sun2'] if BAYER[y % 4, x % 4] < 0.35 else None
            elif r <= 25: col = C['sun1'] if BAYER[y % 4, x % 4] < 0.12 else None
            else: col = None
            if col: px[x, y] = rgba(col)
    d = ImageDraw.Draw(im)
    for k in range(12):   # short pixel rays
        a = k * math.pi / 6; r0, r1 = (22, 34) if k % 2 == 0 else (22, 28)
        for r in range(r0, r1):
            x, y = int(round(c + r * math.cos(a))), int(round(c + r * math.sin(a)))
            if (r - r0) % 3 != 2: px[x, y] = rgba(C['sun1'])
    return im

# ---------------------------------------------------------------- distance
def mesas():
    im = new(W, 70); d = ImageDraw.Draw(im)
    def butte(x0, x1, top, col, cap):
        pts = [(x0, 70), (x0 + 5, top + 6), (x0 + 9, top), (x1 - 9, top), (x1 - 4, top + 7), (x1, 70)]
        d.polygon(pts, fill=rgba(col)); d.line([(x0 + 9, top), (x1 - 9, top)], fill=rgba(cap))
        for yy in range(top + 4, 70, 5): d.line([(x0 + 7, yy), (x1 - 6, yy)], fill=rgba(C['mesa1']))
    butte(-10, 70, 22, C['mesa2'], C['sand4'])
    butte(58, 120, 34, C['mesa0'], C['mesa2'])
    butte(150, 250, 16, C['mesa2'], C['sand4'])
    butte(118, 170, 40, C['mesa0'], C['mesa2'])
    return im

def far():
    im = new(W, 120); d = ImageDraw.Draw(im); f0, f1 = rgba(C['far0']), rgba(C['far1'])
    # water tower
    x = 44; d.rectangle([x, 18, x + 26, 46], fill=f1); d.polygon([(x - 3, 18), (x + 13, 6), (x + 29, 18)], fill=f0)
    for yy in range(22, 46, 6): d.line([(x, yy), (x + 26, yy)], fill=f0)
    for lx in (x + 2, x + 10, x + 16, x + 24): d.line([(lx, 46), (lx - (3 if lx < x + 13 else -3), 120)], fill=f0)
    d.line([(x + 2, 70), (x + 24, 90)], fill=f0); d.line([(x + 24, 70), (x + 2, 90)], fill=f0)
    # windmill
    x = 196; d.line([(x, 30), (x - 8, 120)], fill=f0); d.line([(x, 30), (x + 8, 120)], fill=f0)
    for k in range(8):
        a = k * math.pi / 4; d.line([(x, 30), (x + 13 * math.cos(a), 30 + 13 * math.sin(a))], fill=f1)
    d.rectangle([x - 2, 28, x + 2, 32], fill=f0); d.polygon([(x + 2, 30), (x + 14, 26), (x + 14, 34)], fill=f1)
    # church steeple
    x = 128; d.rectangle([x, 50, x + 12, 120], fill=f1); d.polygon([(x - 1, 50), (x + 6, 26), (x + 13, 50)], fill=f0)
    d.line([(x + 6, 18), (x + 6, 26)], fill=f0); d.line([(x + 3, 21), (x + 9, 21)], fill=f0)
    return im

# ---------------------------------------------------------------- facades
def planks(d, x0, y0, x1, y1, c_lo, c_hi, c_dk, vertical=True, step=3):
    d.rectangle([x0, y0, x1, y1], fill=rgba(c_hi))
    if vertical:
        for x in range(x0, x1 + 1, step): d.line([(x, y0), (x, y1)], fill=rgba(c_lo))
    else:
        for y in range(y0, y1 + 1, step): d.line([(x0, y), (x1, y)], fill=rgba(c_lo))
    for _ in range(int((x1 - x0) * (y1 - y0) / 40)):   # weathering specks
        x, y = random.randint(x0, x1), random.randint(y0, y1); d.point((x, y), fill=rgba(c_dk))

def window(d, x, y, w=9, h=13, frame=None, arch=False):
    frame = frame or C['wood5']
    d.rectangle([x - 1, y - 1, x + w, y + h], fill=rgba(OUT))
    d.rectangle([x, y, x + w - 1, y + h - 1], fill=rgba(C['win']))
    d.line([(x + w // 2, y), (x + w // 2, y + h - 1)], fill=rgba(frame)); d.line([(x, y + h // 2), (x + w - 1, y + h // 2)], fill=rgba(frame))
    d.line([(x + 1, y + 1), (x + 2, y + 1)], fill=rgba(C['glass'])); d.point((x + w // 2 + 2, y + h // 2 + 2), fill=rgba(C['glass']))
    d.rectangle([x - 2, y + h, x + w + 1, y + h + 1], fill=rgba(frame))
    if arch: d.rectangle([x, y - 3, x + w - 1, y - 2], fill=rgba(frame))

def sign(d, x, y, text, bg=CREAM, fg=OUT, pad=3):
    w = len(text) * 8 + pad * 2 - 1; h = 8 + pad * 2 - 1
    d.rectangle([x - 1, y - 1, x + w + 1, y + h + 1], fill=rgba(OUT))
    d.rectangle([x, y, x + w, y + h], fill=rgba(bg))
    d.line([(x, y + h), (x + w, y + h)], fill=rgba(C['sand2']))
    pixtext(d, (x + pad, y + pad), text, rgba(fg))
    return w

def awning(d, x0, x1, y, col_lo, col_hi):
    d.polygon([(x0 - 2, y + 7), (x1 + 2, y + 7), (x1 + 2, y + 4), (x0 - 2, y)], fill=rgba(col_hi))
    d.rectangle([x0 - 2, y + 0, x1 + 2, y + 1], fill=rgba(col_hi))
    d.rectangle([x0 - 2, y + 6, x1 + 2, y + 7], fill=rgba(col_lo))
    for x in range(x0, x1 + 1, 4): d.line([(x, y + 1), (x, y + 6)], fill=rgba(col_lo))
    d.line([(x0 - 2, y + 8), (x1 + 2, y + 8)], fill=rgba(OUT))

def posts(d, x0, x1, ytop, n):
    xs = [round(x0 + i * (x1 - x0) / (n - 1)) for i in range(n)]
    for x in xs:
        d.rectangle([x - 1, ytop, x + 1, BASE], fill=rgba(C['wood2'])); d.line([(x - 1, ytop), (x - 1, BASE)], fill=rgba(C['wood4']))
        d.line([(x + 1, ytop), (x + 1, BASE)], fill=rgba(C['wood0']))
    return xs

def facades():
    im = new(W, H); d = ImageDraw.Draw(im)
    # --- BANK (stone) x 0..48
    x0, x1, top = -2, 46, 232
    d.rectangle([x0, top, x1, BASE], fill=rgba(C['stone1']))
    for y in range(top + 3, BASE, 4):
        off = 0 if (y // 4) % 2 else 3
        d.line([(x0, y), (x1, y)], fill=rgba(C['stone0']))
        for x in range(x0 + off, x1, 7): d.point((x, y + 1), fill=rgba(C['stone0'])); d.point((x, y + 2), fill=rgba(C['stone0']))
    d.rectangle([x0, top - 4, x1 + 2, top], fill=rgba(C['stone2'])); d.line([(x0, top - 5), (x1 + 2, top - 5)], fill=rgba(OUT))
    d.rectangle([x0, top + 1, x1, top + 2], fill=rgba(C['stone0']))
    sign(d, 7, top + 7, 'BANK')
    for wx in (4, 20, 34): window(d, wx, 272, 8, 13, C['stone2'], arch=True)
    d.rectangle([17, 318, 29, BASE], fill=rgba(OUT)); d.rectangle([18, 319, 28, BASE], fill=rgba(C['wood1']))
    d.line([(23, 319), (23, BASE)], fill=rgba(C['wood0'])); d.point((21, 330), fill=rgba(GOLD)); d.point((25, 330), fill=rgba(GOLD))
    # --- SALOON (red paint) x 54..128
    x0, x1, top = 54, 128, 216
    d.rectangle([x0 - 1, top - 1, x1 + 1, BASE], fill=rgba(OUT))
    planks(d, x0, top, x1, BASE, C['paintR'], C['paintR2'], C['wood1'], vertical=False, step=3)
    d.rectangle([x0 - 2, top - 3, x1 + 2, top], fill=rgba(C['wood4'])); d.line([(x0 - 2, top - 4), (x1 + 2, top - 4)], fill=rgba(OUT))
    sign(d, 66, top + 6, 'SALOON', bg=GOLD, fg=OUT)
    for wx in (60, 76, 98, 114): window(d, wx, 246, 8, 12)
    # balcony
    d.rectangle([x0 - 3, 266, x1 + 3, 268], fill=rgba(C['wood3'])); d.line([(x0 - 3, 269), (x1 + 3, 269)], fill=rgba(OUT))
    d.line([(x0 - 3, 262), (x1 + 3, 262)], fill=rgba(C['wood4']))
    for x in range(x0 - 3, x1 + 4, 3): d.line([(x, 262), (x, 266)], fill=rgba(C['wood2']))
    awning(d, x0, x1, 294, C['wood1'], C['wood3'])
    # batwing doors + lanterns
    d.rectangle([83, 312, 99, BASE], fill=rgba(C['win']))
    for dx in (84, 92):
        d.rectangle([dx, 318, dx + 6, 331], fill=rgba(C['wood4'])); d.rectangle([dx, 318, dx + 6, 318], fill=rgba(OUT))
        for yy in range(320, 331, 2): d.line([(dx + 1, yy), (dx + 5, yy)], fill=rgba(C['wood2']))
    for lx in (76, 106):
        d.rectangle([lx, 306, lx + 3, 311], fill=rgba(OUT)); d.rectangle([lx + 1, 307, lx + 2, 310], fill=rgba(GOLD))
    window(d, 62, 312, 11, 14); window(d, 108, 312, 11, 14)
    # --- HOTEL (blue paint) x 134..190
    x0, x1, top = 134, 190, 238
    d.rectangle([x0 - 1, top - 1, x1 + 1, BASE], fill=rgba(OUT))
    planks(d, x0, top, x1, BASE, C['paintB'], C['paintB2'], C['wood1'], vertical=True, step=3)
    d.polygon([(x0 - 1, top), (x0 + 10, top - 8), (x1 - 10, top - 8), (x1 + 1, top)], fill=rgba(C['paintB']))
    d.line([(x0 + 10, top - 9), (x1 - 10, top - 9)], fill=rgba(OUT))
    sign(d, 141, top + 4, 'HOTEL')
    for wx in (139, 155, 171): window(d, wx, 262, 8, 12, C['sky4'])
    awning(d, x0, x1, 296, C['paintB'], C['paintB2'])
    d.rectangle([156, 312, 168, BASE], fill=rgba(OUT)); d.rectangle([157, 313, 167, BASE], fill=rgba(C['wood2']))
    d.point((165, 327), fill=rgba(GOLD)); window(d, 140, 314, 10, 13, C['sky4']); window(d, 174, 314, 10, 13, C['sky4'])
    # --- JAIL (natural wood) x 196..242
    x0, x1, top = 196, 242, 258
    d.rectangle([x0 - 1, top - 1, x1 + 1, BASE], fill=rgba(OUT))
    planks(d, x0, top, x1, BASE, C['wood2'], C['wood3'], C['wood1'], vertical=True, step=4)
    d.rectangle([x0 - 2, top - 3, x1 + 2, top], fill=rgba(C['wood4']))
    sign(d, 203, top + 5, 'JAIL', bg=C['wood5'])
    # barred window + sheriff star
    d.rectangle([203, 286, 219, 300], fill=rgba(OUT)); d.rectangle([204, 287, 218, 299], fill=rgba(C['win']))
    for bx in range(206, 218, 3): d.line([(bx, 287), (bx, 299)], fill=rgba(C['metal1']))
    star = [(230, 284), (231, 287), (234, 287), (232, 289), (233, 292), (230, 290), (227, 292), (228, 289), (226, 287), (229, 287)]
    d.polygon(star, fill=rgba(GOLD), outline=rgba(DGOLD))
    awning(d, x0, x1, 302, C['wood1'], C['wood3'])
    d.rectangle([222, 314, 234, BASE], fill=rgba(OUT)); d.rectangle([223, 315, 233, BASE], fill=rgba(C['wood1']))
    # --- awning posts + noon shadow band under each awning
    for (a, b, y) in [(54, 128, 294), (134, 190, 296), (196, 242, 302)]:
        sh = Image.new('RGBA', im.size, (0, 0, 0, 0)); sd = ImageDraw.Draw(sh)
        sd.rectangle([a, y + 9, b, y + 14], fill=(36, 18, 9, 70)); im.alpha_composite(sh)
    d = ImageDraw.Draw(im)
    posts(d, 55, 127, 302, 4); posts(d, 135, 189, 304, 3); posts(d, 197, 241, 310, 3)
    # --- boardwalk
    d.rectangle([0, BASE, W, BASE + 9], fill=rgba(C['wood3']))
    for x in range(0, W, 5): d.line([(x, BASE), (x, BASE + 7)], fill=rgba(C['wood2']))
    d.line([(0, BASE), (W, BASE)], fill=rgba(C['wood4'])); d.rectangle([0, BASE + 8, W, BASE + 9], fill=rgba(C['wood0']))
    d.line([(0, BASE + 10), (W, BASE + 10)], fill=rgba(OUT))
    # props on the boardwalk
    def barrel(x, y):
        d.rectangle([x, y, x + 8, y + 11], fill=rgba(OUT)); d.rectangle([x + 1, y + 1, x + 7, y + 10], fill=rgba(C['wood3']))
        d.line([(x + 1, y + 3), (x + 7, y + 3)], fill=rgba(C['metal0'])); d.line([(x + 1, y + 8), (x + 7, y + 8)], fill=rgba(C['metal0']))
        d.line([(x + 2, y + 1), (x + 2, y + 10)], fill=rgba(C['wood4']))
    barrel(44, BASE - 11); barrel(130, BASE - 11); barrel(139, BASE - 11)
    # hitching rail + water trough in front of saloon
    d.rectangle([60, BASE - 7, 124, BASE - 6], fill=rgba(C['wood2'])); d.line([(62, BASE - 6), (62, BASE)], fill=rgba(C['wood1'])); d.line([(122, BASE - 6), (122, BASE)], fill=rgba(C['wood1']))
    return im

# ---------------------------------------------------------------- street + foreground
def street():
    h = H - STREET; im = new(W, h)
    gradient(im, 0, h, [C['sand1'], C['sand2'], C['sand3'], C['sand2']])
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 2], fill=rgba(C['sand0']))                       # boardwalk shadow at noon
    for ry, col in [(22, C['sand1']), (25, C['sand1']), (58, C['sand1']), (62, C['sand1'])]:   # wagon ruts
        for x in range(0, W):
            if random.random() < 0.8: d.point((x, ry + (1 if (x // 17) % 3 == 0 else 0)), fill=rgba(col))
    for _ in range(90):
        x, y = random.randint(0, W - 1), random.randint(4, h - 1)
        d.point((x, y), fill=rgba(random.choice([C['sand0'], C['sand4'], C['sand1']])))
    for _ in range(9):   # pebbles
        x, y = random.randint(0, W - 3), random.randint(6, h - 3)
        d.rectangle([x, y, x + 1, y], fill=rgba(C['stone1'])); d.point((x, y + 1), fill=rgba(C['stone0']))
    return im

def foreground():
    im = new(W + 60, H); d = ImageDraw.Draw(im)
    # saguaro at the left edge and a rock + dry grass at the right (move faster than the street)
    x = 4; col, hi, dk = C['paintG'], hexrgb('9A9A5C'), hexrgb('55532F')
    d.rounded_rectangle([x, 362, x + 11, 440], 5, fill=rgba(OUT)); d.rounded_rectangle([x + 1, 363, x + 10, 440], 4, fill=rgba(col))
    d.rounded_rectangle([x - 11, 388, x - 2, 420], 4, fill=rgba(OUT)); d.rounded_rectangle([x - 10, 389, x - 3, 419], 3, fill=rgba(col))
    d.rectangle([x - 5, 414, x + 1, 419], fill=rgba(col))
    d.rounded_rectangle([x + 14, 378, x + 22, 404], 4, fill=rgba(OUT)); d.rounded_rectangle([x + 15, 379, x + 21, 403], 3, fill=rgba(col))
    d.rectangle([x + 10, 398, x + 16, 403], fill=rgba(col))
    for yy in range(366, 440, 3): d.point((x + 3, yy), fill=rgba(hi)); d.point((x + 8, yy + 1), fill=rgba(dk))
    rx = 262
    d.polygon([(rx, 440), (rx + 4, 426), (rx + 14, 420), (rx + 26, 424), (rx + 32, 440)], fill=rgba(C['stone0']), outline=rgba(OUT))
    d.line([(rx + 6, 427), (rx + 14, 423)], fill=rgba(C['stone2']))
    for gx in range(rx - 16, rx + 40, 3):
        hgt = random.randint(4, 10); d.line([(gx, 440), (gx + random.choice([-1, 1]), 440 - hgt)], fill=rgba(random.choice([C['wood4'], DGOLD, C['sand0']])))
    return im

def tumbleweed_frames(n=8, S=28):
    """Procedural tumbleweed: 3D branch loops projected per rotation angle, rasterised without AA."""
    rnd = random.Random(5)
    loops = []
    for _ in range(26):
        ax = [rnd.uniform(-1, 1) for _ in range(3)]; nrm = math.sqrt(sum(a * a for a in ax)) or 1
        ax = [a / nrm for a in ax]; r = rnd.uniform(0.55, 1.0); ph = rnd.uniform(0, math.tau)
        loops.append((ax, r, ph))
    frames = []
    for f in range(n):
        th = f / n * math.tau / 2   # half-turn cycle (visually symmetric)
        im = new(S, S); d = ImageDraw.Draw(im)
        for (ax, r, ph) in loops:
            # circle in the plane perpendicular to ax
            u = [ax[1], -ax[0], 0] if abs(ax[2]) < 0.9 else [0, ax[2], -ax[1]]
            nu = math.sqrt(sum(a * a for a in u)); u = [a / nu for a in u]
            v = [ax[1] * u[2] - ax[2] * u[1], ax[2] * u[0] - ax[0] * u[2], ax[0] * u[1] - ax[1] * u[0]]
            pts = []
            for k in range(0, 25):
                a = ph + k / 24 * math.tau * 0.7
                p = [r * (math.cos(a) * u[i] + math.sin(a) * v[i]) for i in range(3)]
                # rotate about z (rolling)
                x = p[0] * math.cos(th) - p[1] * math.sin(th); y = p[0] * math.sin(th) + p[1] * math.cos(th)
                pts.append((S / 2 - 0.5 + x * (S / 2 - 2), S / 2 - 0.5 + y * (S / 2 - 2), p[2]))
            for (x0, y0, z0), (x1, y1, z1) in zip(pts, pts[1:]):
                col = C['wood4'] if (z0 + z1) > 0.3 else (C['wood3'] if (z0 + z1) > -0.4 else C['wood1'])
                d.line([(x0, y0), (x1, y1)], fill=rgba(col))
        frames.append(im)
    return frames

def dust_puff_frames():
    fr = []
    for k, r in enumerate([3, 5, 7, 8]):
        im = new(20, 12); d = ImageDraw.Draw(im); a = [230, 190, 130, 70][k]
        d.ellipse([10 - r, 11 - r * 0.9, 10 + r, 12], fill=rgba(C['sand4'], a)); fr.append(im)
    return fr

if __name__ == '__main__':
    out = {}
    for name, fn in [('street-sky', sky), ('street-sun', sun), ('street-mesas', mesas), ('street-far', far),
                     ('street-facades', facades), ('street-ground', street), ('street-fg', foreground)]:
        im = fn(); save(im, name + '.png'); out[name] = [im.width, im.height]
    for i, f in enumerate(tumbleweed_frames()): save(f, f'tumbleweed-{i}.png')
    out['tumbleweed'] = [28, 28, 8]; out['layout'] = LAYOUT
    json.dump(out, open(os.path.join(ROOT, '.tesseract-work', 'street-art.json'), 'w'), indent=1)
    # composite preview of the S1 frame (world y 120..440, x 30..210)
    comp = new(W, H)
    comp.alpha_composite(sky(), LAYOUT['street-sky'])
    comp.alpha_composite(sun(), (86, 128))
    comp.alpha_composite(mesas(), LAYOUT['street-mesas']); comp.alpha_composite(far(), LAYOUT['street-far'])
    comp.alpha_composite(facades(), LAYOUT['street-facades']); comp.alpha_composite(street(), LAYOUT['street-ground'])
    comp.alpha_composite(tumbleweed_frames()[0], (80, 395))
    fg = foreground(); fgc = new(W, H); fgc.alpha_composite(fg.crop((10, 0, 10 + W, H))); comp.alpha_composite(fgc)
    frame = comp.crop((30, 120, 210, 440))
    up(frame).save(os.path.join(ROOT, '.tesseract-work', 'checks', 'street-s1-frame.png'))
    full = comp.copy(); up(full, 3).save(os.path.join(ROOT, '.tesseract-work', 'checks', 'street-world.png'))
    print(json.dumps(out))
