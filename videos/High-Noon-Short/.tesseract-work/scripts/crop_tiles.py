"""Crop the reference sheet into tiles using the measured boxes in art-src/tiles.json
(row/column detection on the sheet's dark separators; Nemmy's row was split by hand)."""
import os, json
from PIL import Image
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SRC = os.path.join(ROOT, '.tesseract-work', 'art-src')
sheet = Image.open(os.path.join(ROOT, 'Sources', 'reference', 'band-reference-sheet.jpg')).convert('RGB')
for k, box in json.load(open(os.path.join(SRC, 'tiles.json'))).items():
    sheet.crop(tuple(box)).save(os.path.join(SRC, f'{k}.png'))
