"""Clock tower shot (S3): tower, clock face, hand states, swinging-bell frames and crow frames.
Frame 180x320 art; the tower art has 10 px bleed on every side for the bell-strike shake."""
import sys, os, math, random; sys.path.insert(0, os.path.dirname(__file__))
from pixlib import *
from build_street import sky as street_sky, sun as street_sun, gradient, pixtext, rgba, new, planks, window, BAYER
random.seed(7)
B = 10                    # bleed
FW, FH = 180 + 2 * B, 320 + 2 * B
CX, CY, R = 90 + B, 180 + B, 44      # clock centre/radius in tower-art coords

def tower():
    im = new(FW, FH); d = ImageDraw.Draw(im)
    x0, x1 = 36 + B, 144 + B
    # --- roof + weathervane
    d.polygon([(x0 - 4, 66 + B), (CX, 20 + B), (x1 + 4, 66 + B)], fill=rgba(OUT))
    d.polygon([(x0 - 2, 64 + B), (CX, 23 + B), (x1 + 2, 64 + B)], fill=rgba(C['wood1']))
    for y in range(28 + B, 64 + B, 4):   # shingle rows
        hw = (y - 20 - B) * (x1 - x0 + 4) / (2 * 46)
        for x in range(int(CX - hw) + (y // 4) % 2 * 2, int(CX + hw), 4): d.line([(x, y), (x + 2, y)], fill=rgba(C['wood2']))
        d.line([(CX - hw, y + 1), (CX + hw, y + 1)], fill=rgba(C['wood0']))
    d.line([(CX, 4 + B), (CX, 22 + B)], fill=rgba(OUT))
    d.line([(CX - 9, 10 + B), (CX + 8, 10 + B)], fill=rgba(OUT)); d.polygon([(CX + 8, 7 + B), (CX + 12, 10 + B), (CX + 8, 13 + B)], fill=rgba(OUT))
    d.polygon([(CX - 9, 8 + B), (CX - 12, 6 + B), (CX - 12, 14 + B), (CX - 9, 12 + B)], fill=rgba(OUT))
    # --- belfry (bell frames are separate layers inside the arch)
    d.rectangle([x0 + 6, 64 + B, x1 - 6, 124 + B], fill=rgba(OUT))
    planks(d, x0 + 7, 65 + B, x1 - 7, 123 + B, C['wood2'], C['wood3'], C['wood1'], vertical=True, step=4)
    ax0, ax1, ay0, ay1 = 60 + B, 120 + B, 74 + B, 124 + B
    d.rectangle([ax0, ay0 + 10, ax1, ay1], fill=rgba(OUT)); d.ellipse([ax0, ay0, ax1, ay0 + 22], fill=rgba(OUT))
    d.rectangle([ax0 + 2, ay0 + 11, ax1 - 2, ay1], fill=rgba(C['win'])); d.ellipse([ax0 + 2, ay0 + 2, ax1 - 2, ay0 + 20], fill=rgba(C['win']))
    d.rectangle([ax0 + 4, ay0 + 8, ax1 - 4, ay0 + 10], fill=rgba(C['wood1']))   # yoke beam
    # --- ledge / cornice (crows perch here, top at y=124+B)
    d.rectangle([x0 - 4, 124 + B, x1 + 4, 130 + B], fill=rgba(DGOLD)); d.line([(x0 - 4, 124 + B), (x1 + 4, 124 + B)], fill=rgba(GOLD))
    d.line([(x0 - 4, 131 + B), (x1 + 4, 131 + B)], fill=rgba(OUT))
    for x in range(x0 - 2, x1 + 4, 6): d.point((x, 128 + B), fill=rgba(C['wood1']))
    # --- clock storey: cream plaster with stone corners
    d.rectangle([x0 - 1, 132 + B, x1 + 1, FH], fill=rgba(OUT))
    gradient(im, 132 + B, FH, [C['sand4'], C['sand3'], C['sand2']], x0, x1 + 1)
    d = ImageDraw.Draw(im)
    for y in range(134 + B, FH, 8):
        for cx in (x0, x1 - 5):
            d.rectangle([cx, y, cx + 5, y + 6], fill=rgba(C['stone1'])); d.line([(cx, y + 7), (cx + 5, y + 7)], fill=rgba(C['stone0']))
    # clock face
    px = im.load()
    for y in range(CY - R - 3, CY + R + 4):
        for x in range(CX - R - 3, CX + R + 4):
            r = math.hypot(x - CX, y - CY)
            if r <= R + 3: px[x, y] = rgba(OUT)
            if r <= R + 2: px[x, y] = rgba(DGOLD)
            if r <= R + 1 and (x - CX) + (y - CY) < 0: px[x, y] = rgba(GOLD)
            if r <= R - 1: px[x, y] = rgba(OUT)
            if r <= R - 2: px[x, y] = rgba(CREAM)
    for m in range(60):
        a = m / 60 * math.tau - math.pi / 2
        r0 = R - 5 if m % 5 == 0 else R - 4
        for rr in range(r0, R - 2): px[int(round(CX + rr * math.cos(a))), int(round(CY + rr * math.sin(a)))] = rgba(OUT)
    d = ImageDraw.Draw(im)
    for txt, ang in [('XII', -90), ('III', 0), ('VI', 90), ('IX', 180)]:
        a = math.radians(ang); tx = CX + (R - 14) * math.cos(a) - len(txt) * 4; ty = CY + (R - 14) * math.sin(a) - 4
        pixtext(d, (round(tx), round(ty)), txt, rgba(OUT))
    # lower tower: door + windows, noon shadow under the ledge
    window(d, x0 + 14, 252 + B, 10, 16); window(d, x1 - 24, 252 + B, 10, 16)
    d.rectangle([CX - 9, 280 + B, CX + 9, FH], fill=rgba(OUT)); d.rectangle([CX - 8, 281 + B, CX + 8, FH], fill=rgba(C['wood1']))
    d.ellipse([CX - 9, 274 + B, CX + 9, 290 + B], fill=rgba(OUT)); d.ellipse([CX - 8, 275 + B, CX + 8, 289 + B], fill=rgba(C['wood1']))
    d.line([(CX, 276 + B), (CX, FH)], fill=rgba(C['wood0']))
    sh = new(FW, FH); ImageDraw.Draw(sh).rectangle([x0, 132 + B, x1, 137 + B], fill=(36, 18, 9, 80)); im.alpha_composite(sh)
    # neighbouring rooftops
    d = ImageDraw.Draw(im)
    for (a, b, top, col, hi) in [(-2, x0 - 6, 262 + B, C['paintR'], C['paintR2']), (x1 + 6, FW + 2, 272 + B, C['paintB'], C['paintB2'])]:
        d.rectangle([a, top - 1, b + 1, FH], fill=rgba(OUT)); d.rectangle([a, top, b, FH], fill=rgba(col))
        for y in range(top + 2, FH, 3): d.line([(a, y), (b, y)], fill=rgba(hi))
        d.rectangle([a, top - 3, b + 1, top], fill=rgba(C['wood4']))
    return im

def hand_frame(angle_deg, length, width, color, tail=6):
    S = 2 * (R + 4); im = new(S, S); d = ImageDraw.Draw(im); c = S // 2
    a = math.radians(angle_deg - 90)
    tip = (c + length * math.cos(a), c + length * math.sin(a)); back = (c - tail * math.cos(a), c - tail * math.sin(a))
    d.line([back, tip], fill=rgba(OUT), width=width + 2)
    d.line([back, tip], fill=rgba(color), width=width)
    d.ellipse([c - 3, c - 3, c + 3, c + 3], fill=rgba(OUT)); d.ellipse([c - 2, c - 2, c + 2, c + 2], fill=rgba(GOLD))
    return im

def bell_frame(angle_deg):
    S = 44; im = new(S, S); d = ImageDraw.Draw(im); pivot = (S / 2, 4)
    a = math.radians(angle_deg)
    def rot(p):
        x, y = p[0] - pivot[0], p[1] - pivot[1]
        return (pivot[0] + x * math.cos(a) - y * math.sin(a), pivot[1] + x * math.sin(a) + y * math.cos(a))
    cx = S / 2
    body = [(cx - 5, 6), (cx + 5, 6), (cx + 8, 12), (cx + 9, 22), (cx + 13, 30), (cx + 14, 33), (cx - 14, 33), (cx - 13, 30), (cx - 9, 22), (cx - 8, 12)]
    d.polygon([rot(p) for p in body], fill=rgba(OUT))
    inner = [(cx - 4, 7), (cx + 4, 7), (cx + 7, 12), (cx + 8, 22), (cx + 12, 30), (cx + 12, 32), (cx - 12, 32), (cx - 12, 30), (cx - 8, 22), (cx - 7, 12)]
    d.polygon([rot(p) for p in inner], fill=rgba(DGOLD))
    hi = [(cx - 3, 8), (cx - 1, 8), (cx - 2, 22), (cx - 6, 30), (cx - 9, 30), (cx - 6, 22)]
    d.polygon([rot(p) for p in hi], fill=rgba(GOLD))
    d.line([rot((cx - 12, 31)), rot((cx + 12, 31))], fill=rgba(C['wood1']))
    clap = rot((cx, 34)); d.ellipse([clap[0] - 2, clap[1] - 1, clap[0] + 2, clap[1] + 3], fill=rgba(OUT))
    d.rectangle([pivot[0] - 3, 1, pivot[0] + 3, 5], fill=rgba(C['wood1']))
    return im

def crow_frames():
    """perched, wings-up, wings-down (16x12 art each), facing right."""
    fr = []
    k, k2 = rgba(C['crow']), rgba(C['crow2'])
    im = new(16, 12); d = ImageDraw.Draw(im)
    d.ellipse([3, 4, 11, 10], fill=k); d.ellipse([9, 2, 13, 6], fill=k); d.polygon([(13, 4), (16, 5), (13, 5)], fill=rgba(OUT))
    d.polygon([(3, 7), (0, 10), (4, 9)], fill=k); d.point((11, 3), fill=rgba(GOLD)); d.line([(6, 10), (6, 11)], fill=k2); d.line([(9, 10), (9, 11)], fill=k2)
    d.line([(5, 6), (9, 6)], fill=k2); fr.append(im)
    for up_ in (True, False):
        im = new(16, 12); d = ImageDraw.Draw(im)
        d.ellipse([4, 5, 11, 8], fill=k); d.ellipse([10, 4, 13, 7], fill=k); d.polygon([(13, 5), (16, 6), (13, 6)], fill=rgba(OUT))
        d.polygon([(4, 6), (0, 5), (1, 8)], fill=k); d.point((12, 5), fill=rgba(GOLD))
        if up_: d.polygon([(6, 6), (3, 0), (8, 1), (10, 6)], fill=k); d.line([(4, 1), (7, 2)], fill=k2)
        else: d.polygon([(6, 7), (2, 12), (7, 11), (10, 7)], fill=k); d.line([(4, 11), (7, 10)], fill=k2)
        fr.append(im)
    return fr

HAND_STATES = {  # name: (angle, length, width, colour)
    'hour-12': (0, 26, 4, OUT),
    'minute-59': (-6, 38, 2, OUT), 'minute-00': (0, 38, 2, OUT),
    'second-57': (-18, 40, 1, C['red']), 'second-58': (-12, 40, 1, C['red']), 'second-59': (-6, 40, 1, C['red']), 'second-00': (0, 40, 1, C['red']),
}
BELL_ANGLES = [-18, -9, 0, 9, 18]
def bell_name(a): return f'bell-{"m" if a < 0 else "p"}{abs(a)}.png'
CROWS = [(52 + B, 112 + B), (68 + B, 112 + B), (110 + B, 112 + B), (126 + B, 112 + B)]   # perched top-left positions

if __name__ == '__main__':
    out = {'tower': [FW, FH], 'bleed': B, 'clockCenter': [CX, CY], 'handSize': 2 * (R + 4),
           'bellPivot': [90 + B, 80 + B], 'bellSize': 44, 'bellAngles': BELL_ANGLES, 'crows': CROWS}
    save(tower(), 'clock-tower.png')
    sk = street_sky().crop((0, 0, FW, FH)); save(sk, 'clock-sky.png')
    for n, (a, l, w, c) in HAND_STATES.items(): save(hand_frame(a, l, w, c), f'clock-hand-{n}.png')
    for a in BELL_ANGLES: save(bell_frame(a), bell_name(a))
    for i, f in enumerate(crow_frames()):
        nm = ["perched", "up", "down"][i]
        save(f, f'crow-{nm}-R.png'); save(f.transpose(Image.FLIP_LEFT_RIGHT), f'crow-{nm}-L.png')
    json.dump(out, open(os.path.join(ROOT, '.tesseract-work', 'clock-art.json'), 'w'), indent=1)
    # preview frame at 5.2 s (before the strike) and at 5.5 s (after)
    for tag, hands, bell, crows in [('before', ['hour-12', 'minute-59', 'second-59'], 0, 'perched'), ('after', ['hour-12', 'minute-00', 'second-00'], 18, 'up')]:
        comp = sk.copy(); sn = street_sun(); comp.alpha_composite(sn, (FW // 2 - 40, -22))
        comp.alpha_composite(tower())
        bf = bell_frame(bell); comp.alpha_composite(bf, (90 + B - 22, 80 + B - 4))
        hs = 2 * (R + 4)
        for h in hands: comp.alpha_composite(hand_frame(*HAND_STATES[h]), (CX - hs // 2, CY - hs // 2))
        cf = crow_frames()[0 if crows == 'perched' else 1]
        for i, (x, y) in enumerate(CROWS):
            if crows == 'perched': comp.alpha_composite(cf, (x, y))
            else: comp.alpha_composite(cf, (x - 10 - 8 * i if i < 2 else x + 10 + 8 * i, y - 30 - 6 * i))
        up(comp.crop((B, B, B + 180, B + 320))).save(os.path.join(ROOT, '.tesseract-work', 'checks', f'clock-{tag}.png'))
    print(json.dumps(out))
