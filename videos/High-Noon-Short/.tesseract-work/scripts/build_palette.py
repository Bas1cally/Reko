"""Global 64-colour palette: k-means over the four styled tiles plus the scene colours."""
import sys, os; sys.path.insert(0, os.path.dirname(__file__))
from pixlib import *
tiles = [Image.open(os.path.join(SRC, f'{n}-styled-full.png')).convert('RGB').resize((114, 200), Image.BOX) for n in ['nemmy', 'yumi', 'aiko', 'baer']]
por = [Image.open(os.path.join(SRC, f'{n}-styled-portrait.png')).convert('RGB').resize((100, 100), Image.BOX) for n in ['nemmy', 'yumi', 'aiko', 'baer']]
W = sum(t.width for t in tiles) + sum(p.width for p in por) + 40
big = Image.new('RGB', (W, 200), CREAM); x = 0
for t in tiles: big.paste(t, (x, 0)); x += t.width
for p in por: big.paste(p, (x, 0)); x += p.width
q = big.quantize(colors=52, method=Image.Quantize.MAXCOVERAGE, kmeans=4, dither=Image.Dither.NONE)
pal = q.getpalette()[:52 * 3]
colors = [tuple(pal[i:i + 3]) for i in range(0, len(pal), 3)]
fixed = [OUT, CREAM, GOLD, DGOLD] + list(C.values())
allc = []
for c in fixed + colors:
    if c not in allc: allc.append(c)
json.dump(allc, open(os.path.join(ROOT, '.tesseract-work', 'palette.json'), 'w'))
sw = Image.new('RGB', (len(allc), 1))
for i, c in enumerate(allc): sw.putpixel((i, 0), c)
sw.resize((len(allc) * 12, 24), Image.NEAREST).save(os.path.join(ROOT, '.tesseract-work', 'checks', 'palette.png'))
print(len(allc), 'colours')
