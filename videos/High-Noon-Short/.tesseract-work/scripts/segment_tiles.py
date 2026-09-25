"""Figure masks for the four styled full-body tiles with rembg (models from github.com/danielgatis/rembg releases;
set U2NET_HOME to the model folder). isnet-general-use is used for Nemmy/Yumi/Aiko; Baer combines both masks."""
import os
from PIL import Image
from rembg import remove, new_session
SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'art-src'))
for model in ('isnet-general-use', 'u2net_human_seg'):
    s = new_session(model)
    for n in ('nemmy', 'yumi', 'aiko', 'baer'):
        im = Image.open(os.path.join(SRC, f'{n}-styled-full.png')).convert('RGB')
        big = im.resize((im.width * 3, im.height * 3), Image.LANCZOS)
        remove(big, session=s, only_mask=True).resize(im.size, Image.LANCZOS).save(os.path.join(SRC, f'{n}-styled-full.mask-{model}.png'))
