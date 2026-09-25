import sys; sys.path.insert(0, '.tesseract-work/scripts')
from pixlib import *
from build_street import sky, mesas, far, facades, street, LAYOUT, new, W, H
from build_band import BAND, ORDER
comp = new(W, H)
comp.alpha_composite(sky(), LAYOUT['street-sky']); comp.alpha_composite(mesas(), LAYOUT['street-mesas']); comp.alpha_composite(far(), LAYOUT['street-far'])
comp.alpha_composite(facades()); comp.alpha_composite(street(), LAYOUT['street-ground'])
cx, cy = 30, 120
for n in ORDER:
    s, x, y = BAND[n]; sp = Image.open(f'Art/band-{n}.png'); sp = sp.resize((sp.width // 6, sp.height // 6), Image.NEAREST)
    comp.alpha_composite(sp, (cx + x, cy + y))
up(comp.crop((cx, cy, cx + 180, cy + 320))).save('.tesseract-work/checks/band-end-frame.png')
