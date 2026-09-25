"""Assemble High-Noon.tsrct from the generated pixel art, the song and the bell.
Everything visual lives on a 6-px grid: positions are whole art pixels * 6 (scripts round before scaling)."""
import json, os, subprocess, sys, random
sys.path.insert(0, os.path.dirname(__file__))
from pixlib import OUT, CREAM, GOLD, DGOLD, C
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
WORK = os.path.join(ROOT, '.tesseract-work')
TSRCT = os.path.expanduser('~/.local/share/Tesseract/bin/tsrct')
PROJECT = os.path.join(ROOT, 'High-Noon.tsrct')
P = 6
DUR = 21170
SHOT = {'S1': (0, 1300), 'S2': (1300, 4530), 'S3': (4530, 7200), 'S4': (7200, 8830), 'S5': (8830, 12570), 'S6': (12570, 14200), 'S7': (14200, 21170)}
street = json.load(open(os.path.join(WORK, 'street-art.json')))
clock = json.load(open(os.path.join(WORK, 'clock-art.json')))
band = json.load(open(os.path.join(WORK, 'band-art.json')))

def rgba(c, a=1.0): return [round(v / 255, 4) for v in c] + [a]

def run(*args):
    r = subprocess.run([TSRCT, *args], capture_output=True, text=True)
    if r.returncode != 0: sys.exit(f'tsrct {args[0]} {args[1] if len(args) > 1 else ""} failed:\n{r.stdout}\n{r.stderr}')
    return r.stdout

# ------------------------------------------------------------------ document model
nid_ = [1]
def nid():
    i = nid_[0]; nid_[0] += 1; return i
DYN = []
def js(layer_id, prop, code):
    DYN.append({'animator': {'type': 'jsScript', 'layerTimeJsCode': code}, 'target': {'kind': 'layer', 'layerId': layer_id, 'propertyType': prop}})
def tf(x, y, op=100): return {'anchorPoint': [0, 0], 'position': [x * P, y * P], 'scale': [100, 100], 'rotation': 0, 'opacity': op}
def image(name, asset, x, y, dur, start=0, op=100):
    return {'type': 'Image', 'id': nid(), 'name': name, 'blendMode': 'normal', 'activeRange': {'start': start, 'duration': dur},
            'transform': tf(x, y, op), 'source': {'assetId': asset, 'fit': 'contain'}}
def group(name, dur, layers, start=0, x=0, y=0):
    return {'type': 'Group', 'id': nid(), 'name': name, 'blendMode': 'normal', 'activeRange': {'start': start, 'duration': dur},
            'transform': tf(x, y), 'layers': layers}
def rect(name, x, y, w, h, color, dur, start=0, op=100):
    return {'type': 'Rect', 'id': nid(), 'name': name, 'blendMode': 'normal', 'activeRange': {'start': start, 'duration': dur},
            'transform': tf(x, y, op), 'rect': {'size': [w * P, h * P], 'fillColor': color, 'fillEnabled': True}}

SNAP = 'function S(v){return Math.round(v)*6;}'
EASE = ('function eio(p){p=Math.max(0,Math.min(1,p));return p<0.5?4*p*p*p:1-Math.pow(-2*p+2,3)/2;}'
        'function eo(p){p=Math.max(0,Math.min(1,p));return 1-(1-p)*(1-p);}')
def shake_js(t0, axis, base):
    """Pixel-snapped decaying shake starting at local time t0 (only used at 5.38 s and 18.92 s)."""
    f, ph = (97.0, 0.0) if axis == 'x' else (83.0, 1.3)
    return (f'{SNAP} var d=input.time.seconds-{t0}; var o=0; if(d>=0&&d<0.5){{o=Math.exp(-d*8)*3*Math.sin(d*{f}+{ph});}} '
            f'return S({base}+o);')

def particles(tag, dur_s, n, seed, y_range=(40, 300), speed=(3, 9), color=C['sand4'], op=(45, 80), wind=False):
    """Drifting dust motes: 1-2 art-px rects, positions scripted and snapped to the grid."""
    rnd = random.Random(seed); out = []
    for i in range(n):
        w = rnd.choice([1, 1, 2]); r = rect(f'{tag} dust {i + 1}', 0, 0, w, 1 if w == 2 else 1, rgba(color), round(dur_s * 1000), op=rnd.randint(*op))
        x0, y0 = rnd.uniform(0, 180), rnd.uniform(*y_range); vx = rnd.uniform(*speed) * (-1 if wind or rnd.random() < 0.5 else 1)
        if wind: vx *= 6
        amp, fr, vy = rnd.uniform(1, 3), rnd.uniform(0.6, 1.4), rnd.uniform(-2, 1)
        js(r['id'], 'positionX', f'{SNAP} var t=input.time.seconds; var x={x0:.1f}+({vx:.2f})*t; x=((x%190)+190)%190-5; return S(x);')
        js(r['id'], 'positionY', f'{SNAP} var t=input.time.seconds; return S({y0:.1f}+{amp:.2f}*Math.sin(t*{fr:.2f}*6.283+{i})+({vy:.2f})*t);')
        out.append(r)
    return out

def tumbleweed(tag, dur_ms, x_expr, y_expr, reverse=False):
    """8 rotation frames in a group; group position = path, frame opacity = roll angle derived from x."""
    frames = []
    for k in range(8):
        f = image(f'{tag} frame {k}', f'tumbleweed-{k}', 0, 0, dur_ms)
        idx = '(7-i)' if reverse else 'i'
        js(f['id'], 'opacity', f'var t=input.time.seconds; var x={x_expr}; var i=Math.floor(Math.abs(x)/14/Math.PI*8)%8; return ({idx}=={k})?100:0;')
        frames.append(f)
    g = group(tag, dur_ms, frames)
    js(g['id'], 'positionX', f'{SNAP} var t=input.time.seconds; return S({x_expr});')
    js(g['id'], 'positionY', f'{SNAP} var t=input.time.seconds; return S({y_expr});')
    return g

# ------------------------------------------------------------------ S1 Main Street + tumbleweed (0 - 1.30)
def s1():
    d_ms = SHOT['S1'][1] - SHOT['S1'][0]
    cam = 'var d=16*eo(input.time.seconds/1.3);'
    def par(name, asset, wx, fy, f):
        im = image(name, asset, 0, fy, d_ms); js(im['id'], 'positionX', f'{SNAP}{EASE}{cam} return S({wx}-30-d*{f});'); return im
    beats = '[-0.286,0.248,0.782,1.316]'
    tw = tumbleweed('S1 tumbleweed', d_ms, '(-30+178*t)',
                    f'(function(){{var L={beats};var k=0;for(var j=0;j<3;j++){{if(t>=L[j])k=j;}}var p=(t-L[k])/(L[k+1]-L[k]);return 272-4*14*p*(1-p);}})()')
    layers = [tw] + particles('S1', 1.3, 8, 11, y_range=(150, 300), wind=True) + [
        par('S1 foreground cactus', 'street-fg', 24, -120, 1.3),
        par('S1 street', 'street-ground', 0, 230, 1.0),
        par('S1 facades', 'street-facades', 0, -120, 1.0),
        par('S1 far town', 'street-far', 0, 62, 0.55),
        par('S1 mesas', 'street-mesas', 0, 86, 0.4),
        par('S1 sun', 'street-sun', 86, 8, 0.1),
        par('S1 sky', 'street-sky', 0, -120, 0.15)]
    return group('S1 Main Street', d_ms, layers, start=SHOT['S1'][0])

# ------------------------------------------------------------------ solo shots
def solo(tag, name, x_from, x_to, char_from=None, char_to=None, y=-18, seed=1):
    s, e = SHOT[tag]; d_ms = e - s; d_s = d_ms / 1000
    layers = particles(tag, d_s, 10, seed, y_range=(20, 300))
    if char_from is not None:
        ch = image(f'{tag} {name} (character)', f'{name}-char', x_from, y, d_ms)
        js(ch['id'], 'positionX', f'{SNAP} var p=input.time.seconds/{d_s}; return S({char_from}+({char_to - char_from})*p);')
        layers.append(ch)
    bg = image(f'{tag} {name} (background)', f'{name}-bg', x_from, y, d_ms)
    js(bg['id'], 'positionX', f'{SNAP} var p=input.time.seconds/{d_s}; return S({x_from}+({x_to - x_from})*p);')
    layers.append(bg)
    return group(f'{tag} {name.capitalize()}', d_ms, layers, start=s)

# ------------------------------------------------------------------ S3 clock tower (4.53 - 7.20), strike at 5.38
def s3():
    s, e = SHOT['S3']; d_ms = e - s; B = clock['bleed']; strike = round(5.38 - s / 1000, 3)
    hs = clock['handSize']; cx, cy = clock['clockCenter']
    layers = []
    # crows: perched until the strike, then fly off (staggered), wings flapping every 80 ms
    paths = [(-1, 34, 58, 0.00), (-1, 22, 70, 0.07), (1, 26, 66, 0.03), (1, 38, 52, 0.10)]
    for i, ((px, py), (dirn, vx, vy, lag)) in enumerate(zip(clock['crows'], paths)):
        side = 'L' if dirn < 0 else 'R'; t0 = strike + lag
        fr = []
        for kind in ('perched', 'up', 'down'):
            im = image(f'S3 crow {i + 1} {kind}', f'crow-{kind}-{side}', 0, 0, d_ms)
            cond = {'perched': 'd<0', 'up': 'd>=0&&Math.floor(d/0.08)%2==0', 'down': 'd>=0&&Math.floor(d/0.08)%2==1'}[kind]
            js(im['id'], 'opacity', f'var d=input.time.seconds-{t0}; return ({cond})?100:0;')
            fr.append(im)
        g = group(f'S3 crow {i + 1}', d_ms, fr)
        js(g['id'], 'positionX', f'{SNAP} var d=Math.max(0,input.time.seconds-{t0}); return S({px}+({dirn})*({vx}*d+70*d*d));')
        js(g['id'], 'positionY', f'{SNAP} var d=Math.max(0,input.time.seconds-{t0}); return S({py}-({vy}*d+40*d*d)+(d>0?Math.sin(d*18+{i})*1.2:0));')
        layers.append(g)
    # hands: hold-state layers
    states = [('second-57', f't<0.27'), ('second-58', 't>=0.27&&t<0.53'), ('second-59', f't>=0.53&&t<{strike}'), ('second-00', f't>={strike}'),
              ('minute-59', f't<{strike}'), ('minute-00', f't>={strike}'), ('hour-12', 'true')]
    for nm, cond in states:
        im = image(f'S3 hand {nm}', f'clock-hand-{nm}', cx - hs // 2, cy - hs // 2, d_ms)
        js(im['id'], 'opacity', f'var t=input.time.seconds; return ({cond})?100:0;'); layers.append(im)
    # bell: swing after the strike, nearest of five pre-drawn angles
    px_, py_ = clock['bellPivot']
    for a in clock['bellAngles']:
        nm = f'bell-{"m" if a < 0 else "p"}{abs(a)}'
        im = image(f'S3 bell {a:+d} deg', nm, px_ - 22, py_ - 4, d_ms)
        js(im['id'], 'opacity', f'var d=input.time.seconds-{strike}; var a=d<0?0:18*Math.exp(-d/1.3)*Math.sin(d*6.283/0.95); '
                                f'var A=[-18,-9,0,9,18]; var b=0; for(var j=1;j<5;j++){{if(Math.abs(A[j]-a)<Math.abs(A[b]-a))b=j;}} return (A[b]=={a})?100:0;')
        layers.append(im)
    layers.append(image('S3 tower', 'clock-tower', 0, 0, d_ms))
    layers.append(image('S3 sun', 'street-sun', 100 - 40, -12, d_ms))
    layers.append(image('S3 sky', 'clock-sky', 0, 0, d_ms))
    camg = group('S3 camera (bell shake)', d_ms, layers)
    js(camg['id'], 'positionX', shake_js(strike, 'x', -B)); js(camg['id'], 'positionY', shake_js(strike, 'y', -B - 4))
    return group('S3 Clock tower', d_ms, [camg], start=s)

# ------------------------------------------------------------------ S7 band line-up (14.20 - 21.17), drums + title at 18.92
def s7():
    s, e = SHOT['S7']; d_ms = e - s; hit = round(18.92 - s / 1000, 3); beat0 = round(18.94 - s / 1000, 3)
    cam = 'var c=120*eio((input.time.seconds-0.4)/3.8);'
    L = street['layout']
    def par(name, asset, wx, wy, f, extra=''):
        im = image(name, asset, wx - 30, wy, d_ms)
        js(im['id'], 'positionY', f'{SNAP}{EASE}{cam}{extra} return S({wy}-c*{f});'); return im
    layers = []
    tw = tumbleweed('S7 tumbleweed', d_ms, '(215-120*(t-2.7))',
                    f'(function(){{var L=[2.559,3.093,3.627,4.161,4.695];var k=0;for(var j=0;j<4;j++){{if(t>=L[j])k=j;}}var p=Math.max(0,Math.min(1,(t-L[k])/(L[k+1]-L[k])));'
                    f'var c=120*eio((t-0.4)/3.8);return 372-c-4*12*p*(1-p);}})()'.replace('eio(', '(function(p){p=Math.max(0,Math.min(1,p));return p<0.5?4*p*p*p:1-Math.pow(-2*p+2,3)/2;})('),
                    reverse=True)
    layers.append(tw)
    layers += particles('S7', d_ms / 1000, 14, 77, y_range=(60, 300), wind=True)
    layers.append(par('S7 foreground', 'street-fg', 0, 0, 1.1))
    for n in ['nemmy', 'aiko', 'yumi', 'baer']:   # front to back
        fx, fy = band[n]['frameXY']; amp = 2 if n == 'baer' else 1
        nod = f'var b=(input.time.seconds-{beat0})/0.534; var nod=(input.time.seconds>={beat0}&&(b-Math.floor(b))<0.25)?{amp}:0;'
        im = image(f'S7 band {n}', f'band-{n}', fx, fy + 120, d_ms)
        js(im['id'], 'positionY', f'{SNAP}{EASE}{cam}{nod} return S({fy + 120}-c+nod);')
        layers.append(im)
    layers.append(par('S7 street', 'street-ground', 0, L['street-ground'][1], 1.0))
    layers.append(par('S7 facades', 'street-facades', 0, 0, 1.0))
    layers.append(par('S7 far town', 'street-far', 0, L['street-far'][1], 0.85))
    layers.append(par('S7 mesas', 'street-mesas', 0, L['street-mesas'][1], 0.85))
    sun = image('S7 sun', 'street-sun', 50, 14, d_ms); js(sun['id'], 'positionY', f'{SNAP}{EASE}{cam} return S(14-c*0.3);'); layers.append(sun)
    layers.append(par('S7 sky', 'street-sky', 0, 0, 0.5))
    # fix x for every parallax layer except the tumbleweed/particles (static camera x = 30)
    for l in layers:
        if l['name'] in ('S7 foreground',): l['transform']['position'][0] = (0 - 30) * P
    camg = group('S7 camera (tilt + drum shake)', d_ms, layers)
    js(camg['id'], 'positionX', shake_js(hit, 'x', 0)); js(camg['id'], 'positionY', shake_js(hit, 'y', 0))
    return group('S7 Band on Main Street', d_ms, [camg], start=s)

# ------------------------------------------------------------------ audio
def audio_layers():
    music = {'type': 'Audio', 'id': nid(), 'name': 'Song: High Noon (2:32.4 - 2:53.57, +23 ms MP3 encoder-delay compensation)', 'windowMs': 0,
             'activeRange': {'start': 0, 'duration': DUR}, 'sourceRange': {'start': 152423, 'duration': DUR},
             'sourceIntrinsicDuration': 190824, 'source': {'assetId': 'song-high-noon'}, 'volume': 1.0, 'captionsEnabled': False}
    js(music['id'], 'volume', 'var t=input.time.seconds; if(t<0.02) return t/0.02; if(t>20.82) return Math.max(0,1-(t-20.82)/0.35); return 1.0;')
    bell = {'type': 'Audio', 'id': nid(), 'name': 'SFX: bell strike on "Twelve" (5.38 s)', 'windowMs': 0,
            'activeRange': {'start': 5375, 'duration': 3600}, 'sourceRange': {'start': 0, 'duration': 3600},
            'sourceIntrinsicDuration': 3600, 'source': {'assetId': 'sfx-bell'}, 'volume': 1.3, 'captionsEnabled': False}
    return [bell, music]

# ------------------------------------------------------------------ text + fade (actions)
LYRICS = [  # (start, end, text, word onsets in song-edit seconds)
    (1.45, 4.65, 'High noon, high noon,\nmeet me there', [1.60, 1.88, 2.72, 2.93, 3.46, 3.73, 3.98]),
    (5.15, 8.90, "Twelve o'clock,\nif you dare", [5.38, 5.61, 7.72, 8.00, 8.28]),
    (8.90, 12.55, 'Hands up,\nhere it comes', [9.13, 9.36, 11.49, 11.75, 12.02]),
    (12.60, 14.22, 'No place to run', [12.70, 13.11, 13.37, 13.65]),
    (14.30, 19.55, 'High noon, high noon,\nhere I come', [14.47, 14.72, 15.57, 16.16, 18.17, 18.47, 18.94]),
]
def text_actions():
    A = []; lid = 900; item = 5000
    def txt(layer_id, name, start, end, text, family, style, size, fill, stroke_w, box, animators, just='center'):
        return {'type': 'createFxTextLayer', 'compositionId': 'main', 'layerId': layer_id, 'name': name, 'insertIndex': 0,
                'activeRange': {'start': round(start * 1000), 'duration': round((end - start) * 1000)},
                'transform': {'anchorPoint': [0, 0], 'position': [0, 0], 'scale': [100, 100], 'rotation': 0, 'opacity': 100},
                'sourceText': {'text': text, 'fontFamily': family, 'fontStyle': style, 'fontSize': size, 'fillColor': fill,
                               'strokeEnabled': True, 'strokeColor': rgba(OUT), 'strokeWidth': stroke_w, 'strokeOverFill': False,
                               'justification': just, 'boxText': True, 'boxPosition': box[:2], 'boxSize': box[2:], 'verticalAlign': 'top'},
                'animators': animators}
    for i, (st, en, text, words) in enumerate(LYRICS):
        lid += 1; item += 2
        A.append(txt(lid, f'Lyrics {i + 1}: {text.replace(chr(10), " / ")}', st, en, text, 'Pixelify Sans', 'Bold', 80, rgba(CREAM), 12,
                     [60, 1300, 960, 300], [{'id': item, 'name': 'Sung words turn gold', 'fillColor': rgba(GOLD),
                      'selectors': [{'id': item + 1, 'start': 0, 'end': 0, 'units': 'index', 'basedOn': 'words', 'mode': 'add', 'amount': 1, 'shape': 'square'}]}]))
        rel = [round(w - st, 3) for w in words]
        A.append({'type': 'setFxLayerStyleAnimator', 'compositionId': 'main', 'layerId': lid, 'itemId': item + 1, 'propertyName': 'end', 'dependencies': [],
                  'animator': {'type': 'jsScript', 'layerTimeJsCode': f'var t=input.time.seconds; var on={json.dumps(rel)}; var n=0; for(var i=0;i<on.length;i++){{if(t>=on[i])n=i+1;}} return n;'}})
        d = round((en - st) * 1000)
        A.append({'type': 'setFxPropertyKeyframes', 'compositionId': 'main', 'property': {'layerId': lid, 'propertyType': 'opacity'}, 'keyframes': [
            {'id': f'lyr{i + 1}-in0', 'layerTime': 0, 'value': {'type': 'float', 'value': 0}, 'easing': {'type': 'linear'}},
            {'id': f'lyr{i + 1}-in1', 'layerTime': 100, 'value': {'type': 'float', 'value': 100}, 'easing': {'type': 'linear'}},
            {'id': f'lyr{i + 1}-out0', 'layerTime': d - 120, 'value': {'type': 'float', 'value': 100}, 'easing': {'type': 'linear'}},
            {'id': f'lyr{i + 1}-out1', 'layerTime': d, 'value': {'type': 'float', 'value': 0}, 'easing': {'type': 'linear'}}]})
    # Title: HIGH NOON (dark-gold extrusion + gold face) and NEMMYSIS, letters snap in from the drum hit
    def reveal(item_id, t0, step):
        return ({'id': item_id, 'name': 'Letter reveal', 'opacity': 0,
                 'selectors': [{'id': item_id + 1, 'start': 0, 'end': 99, 'units': 'index', 'basedOn': 'characters', 'mode': 'add', 'amount': 1, 'shape': 'square'}]},
                f'var t=input.time.seconds; return t<{t0}?0:Math.floor((t-{t0})/{step})+1;')
    specs = [('Title shadow: HIGH NOON', 'HIGH NOON', 96, rgba(DGOLD), 12, [12, 312, 1080, 140], 0.0, 0.035),
             ('Title: HIGH NOON', 'HIGH NOON', 96, rgba(GOLD), 12, [0, 300, 1080, 140], 0.0, 0.035),
             ('Title: NEMMYSIS', 'NEMMYSIS', 48, rgba(CREAM), 10, [0, 450, 1080, 80], 0.62, 0.045)]
    for name, text, size, fill, sw, box, t0, step in specs:
        lid += 1; item += 2
        anim, code = reveal(item, t0, step)
        A.append(txt(lid, name, 18.92, DUR / 1000, text, 'Press Start 2P', 'Regular', size, fill, sw, box, [anim]))
        A.append({'type': 'setFxLayerStyleAnimator', 'compositionId': 'main', 'layerId': lid, 'itemId': item + 1, 'propertyName': 'start',
                  'dependencies': [], 'animator': {'type': 'jsScript', 'layerTimeJsCode': code}})
    # fade to black 20.82 - 21.17
    lid += 1
    A.append({'type': 'createFxRectLayer', 'compositionId': 'main', 'layerId': lid, 'name': 'Fade to black (20.82 - 21.17 s)', 'insertIndex': 0,
              'activeRange': {'start': 20820, 'duration': DUR - 20820},
              'transform': {'anchorPoint': [0, 0], 'position': [0, 0], 'scale': [100, 100], 'rotation': 0, 'opacity': 0},
              'rect': {'size': [1080, 1920], 'fillColor': [0, 0, 0, 1]}})
    A.append({'type': 'setFxPropertyKeyframes', 'compositionId': 'main', 'property': {'layerId': lid, 'propertyType': 'opacity'}, 'keyframes': [
        {'id': 'fade-0', 'layerTime': 0, 'value': {'type': 'float', 'value': 0}, 'easing': {'type': 'linear'}},
        {'id': 'fade-1', 'layerTime': DUR - 20820, 'value': {'type': 'float', 'value': 100}, 'easing': {'type': 'linear'}}]})
    return A

# ------------------------------------------------------------------ build
def main(out=PROJECT):
    if os.path.exists(out): os.remove(out)
    run('project', 'create', '--project', out)
    run('project', 'import-font', '--project', out, '--file', os.path.join(ROOT, 'Sources/fonts/PixelifySans-Bold.ttf'))
    run('project', 'import-font', '--project', out, '--file', os.path.join(ROOT, 'Sources/fonts/PressStart2P-Regular.ttf'))
    run('project', 'import-asset', '--project', out, '--file', os.path.join(ROOT, 'Sources/audio/High_Noon.mp3'), '--asset-id', 'song-high-noon', '--kind', 'audio')
    run('project', 'import-asset', '--project', out, '--file', os.path.join(ROOT, 'Sources/sfx/bell-strike-A3.wav'), '--asset-id', 'sfx-bell', '--kind', 'audio')
    for f in sorted(os.listdir(os.path.join(ROOT, 'Art'))):
        if f.endswith('.png'): run('project', 'import-asset', '--project', out, '--file', os.path.join(ROOT, 'Art', f), '--asset-id', f[:-4], '--kind', 'image')
    ed = os.path.join(WORK, 'editable.json')
    run('project', 'checkout', '--project', out, '--output', ed)
    doc = json.load(open(ed))
    doc['dimensions'] = {'width': 1080, 'height': 1920}; doc['duration'] = DUR / 1000
    shots = [s7(),
             solo('S6', 'baer', -2, -8, y=-18, seed=6),
             solo('S5', 'aiko', -3, -9, -3, -13, y=-20, seed=5),
             solo('S4', 'yumi', -9, -4, -13, -4, y=-18, seed=4),
             s3(),
             solo('S2', 'nemmy', -3, -9, -3, -13, y=-18, seed=2),
             s1()]
    doc['composition']['layers'] = shots + audio_layers()
    doc['composition']['dynamics'] = {'entries': DYN}
    json.dump(doc, open(ed, 'w'), indent=1)
    run('project', 'commit', '--project', out, '--file', ed)
    acts = os.path.join(WORK, 'text-actions.json'); json.dump(text_actions(), open(acts, 'w'), indent=1)
    print(run('project', 'apply', '--project', out, '--actions', acts).strip())
    run('project', 'checkout', '--project', out, '--output', ed)   # keep the working JSON in sync with the saved document
    print('layers', nid_[0] - 1, 'scripts', len(DYN))

if __name__ == '__main__':
    main(*(sys.argv[1:2]))
