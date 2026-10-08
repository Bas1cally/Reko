#!/usr/bin/env python3
"""Venice.ai client for the iso-cycles pipeline: stills, turnarounds and clips.

Reads the requests that make_prompts.py writes (prompts.json) and runs them on
Venice instead of the Scenario MCP. In cast.json, "stills" hold local file
paths (e.g. "raw/knight_se.png") instead of Scenario asset ids; this client
sends them as data URLs.

API key: in a Claude Code cloud session store it as a network secret for
api.venice.ai (Bearer); the proxy adds the Authorization header, so no key is
needed here. Locally: environment variable VENICE_API_KEY, or a line
VENICE_API_KEY=... in .env at the repo root (.env is git-ignored; never commit it).

Usage:
  venice.py models image|video|edit [--grep TEXT]   list models (no key needed)
  venice.py quote prompts.json [--only stills|cycles] [--ids A,B]
                                                    price every request, no spend
  venice.py stills prompts.json [--ids A,B] [--out raw]
                                                    run still / turnaround requests
  venice.py clips prompts.json [--ids A,B] [--jobs jobs.json]
                                                    queue clips, record queue ids
  venice.py wait [--jobs jobs.json] [--out clips]   poll, download finished clips

Field mapping from prompts.json (Scenario names) to Venice:
  still without referenceImages -> POST /image/generate
  still with referenceImages    -> POST /image/multi-edit (one call per output)
  clip: startImage -> image_url, endImage -> end_image_url, duration "3" -> "3s",
        negativePrompt -> negative_prompt, generateAudio -> audio,
        aspectRatio only when the model lists aspect ratios.
"""
import argparse, base64, json, mimetypes, os, sys, time, urllib.error, urllib.request
from pathlib import Path

API = "https://api.venice.ai/api/v1"
ROOT = Path(__file__).resolve().parent.parent
# resolutions the API accepts where the model list shows none or other spellings (checked with /video/quote)
DEFAULT_RES = {"flux-3-image-to-video": "720p", "flux-3-first-last-frame-to-video": "720p","minimax-h3-max-turbo-image-to-video": "768P", "minimax-h3-max-image-to-video": "768P",
               "minimax-h3-image-to-video": "768P", "minimax-h3-reference-to-video": "768P",
               "wan-3-0-image-to-video": "480p", "wan-3-0-reference-to-video": "480p",
               "pixverse-c1-image-to-video": "540p"}
RESOLUTION = None               # --resolution overrides
MODEL_TYPES = {"image": "image", "video": "video", "edit": "inpaint"}


def api_key(required=True):
    key = os.environ.get("VENICE_API_KEY")
    env = ROOT / ".env"
    if not key and env.is_file():
        for line in env.read_text().splitlines():
            if line.strip().startswith("VENICE_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if required and not key:
        sys.exit("error: no API key. Set VENICE_API_KEY or put VENICE_API_KEY=... in .env")
    return key or None


def call(method, path, body=None, auth=True, raw=False):
    """One API call. Returns (content_type, bytes) when raw, else parsed JSON."""
    headers = {"Content-Type": "application/json"}
    key = api_key(required=False) if auth else None
    if key:                     # otherwise a network secret on the proxy adds it
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(4):    # upstream 502/503s are common and transient: retry with backoff
        req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                ctype, payload = r.headers.get("Content-Type", ""), r.read()
            break
        except urllib.error.HTTPError as e:
            if e.code in (502, 503, 504) and attempt < 3:
                print(f"note: {path} -> HTTP {e.code}, retry in {5 * 2 ** attempt}s", file=sys.stderr)
                time.sleep(5 * 2 ** attempt)
                continue
            detail = e.read().decode(errors="replace")[:2000]
            if e.code == 401:
                detail += " (no key reached Venice: add the network secret for api.venice.ai, or set VENICE_API_KEY)"
            raise SystemExit(f"error: {method} {path} -> HTTP {e.code}: {detail}")
    if raw:
        return ctype, payload
    return json.loads(payload)


_specs = {}
def model_spec(model_id):
    """The model's entry from GET /models (any type), cached per run."""
    if not _specs:
        for t in MODEL_TYPES.values():
            for m in call("GET", f"/models?type={t}", auth=False)["data"]:
                _specs[m["id"]] = m
    if model_id not in _specs:
        sys.exit(f"error: unknown Venice model '{model_id}'. List them with: venice.py models image|video|edit")
    return _specs[model_id]


def data_url(ref, max_side=None):
    """A local file path (relative to the repo root or cwd) or an http(s) URL."""
    if ref.startswith(("http://", "https://", "data:")):
        return ref
    if ref.startswith("<"):
        sys.exit(f"error: placeholder {ref} still in prompts.json: put the file path in cast.json 'stills' and "
                 "re-run make_prompts.py --force")
    p = Path(ref) if Path(ref).is_file() else ROOT / ref
    if not p.is_file():
        sys.exit(f"error: image not found: {ref}")
    if max_side:                # references only: smaller payloads, fewer upstream failures
        from PIL import Image
        import io
        im = Image.open(p).convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=92)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def load(prompts, only=None, ids=None):
    d = json.loads(Path(prompts).read_text())
    out = []
    for kind in ("stills", "cycles"):
        if only and only != kind:
            continue
        for e in d.get(kind, []):
            if ids and e["id"] not in ids:
                continue
            if e["model"].startswith("<"):
                sys.exit(f"error: {e['id']}: no model id. Re-run make_prompts.py with --still-model / --clip-model "
                         "(Venice ids from: venice.py models image|edit|video)")
            out.append((kind, e))
    return out


def aspect(w, h):
    return {(1536, 1024): "3:2", (1024, 1536): "2:3", (1024, 1024): "1:1"}.get((w, h), "1:1")


# ---------- stills ----------
def still_body(e):
    p, spec = e["params"], model_spec(e["model"])
    c = spec["model_spec"].get("constraints", {})
    if p.get("referenceImages"):
        body = {"modelId": e["model"], "prompt": p["prompt"], "output_format": "png",
                "images": [data_url(r, max_side=1024) for r in p["referenceImages"]]}
        if "aspectRatios" in c:
            body["aspect_ratio"] = aspect(p.get("width", 1024), p.get("height", 1024))
        if "quality" in spec["model_spec"].get("pricing", {}) and p.get("quality"):
            body["quality"] = p["quality"]
        return "/image/multi-edit", body
    body = {"model": e["model"], "prompt": p["prompt"], "format": "png", "hide_watermark": True,
            "safe_mode": False, "variants": p.get("numOutputs", 1), "return_binary": False}
    if "aspectRatios" in c:
        body["aspect_ratio"] = aspect(p.get("width", 1024), p.get("height", 1024))
        if c.get("resolutions"):
            body["resolution"] = c.get("defaultResolution", c["resolutions"][0])
    else:
        body["width"], body["height"] = p.get("width", 1024), p.get("height", 1024)
    if "quality" in spec["model_spec"].get("pricing", {}) and p.get("quality"):
        body["quality"] = p["quality"]
    return "/image/generate", body


def still_price(e):
    pr = model_spec(e["model"])["model_spec"].get("pricing", {})
    n = e["params"].get("numOutputs", 1)
    q = e["params"].get("quality")
    if "quality" in pr and q:
        res = next(iter(pr["quality"]))
        if q in pr["quality"][res]:
            return n * pr["quality"][res][q]["usd"]
    if "generation" in pr:
        return n * pr["generation"]["usd"]
    if "resolutions" in pr:
        return n * next(iter(pr["resolutions"].values()))["usd"]
    return None


def run_stills(a):
    out = Path(a.out)
    if a.model:
        global load
        _load = load
        load = lambda *x: [(k, dict(e, model=a.model, id=e["id"] + "_" + a.model.split("-")[0]))
                           for k, e in _load(*x)]
    out.mkdir(parents=True, exist_ok=True)
    for kind, e in load(a.prompts, "stills", a.ids):
        done = sorted(out.glob(f"{e['id']}_[0-9].*"))
        if done and not a.force:
            print(f"{e['id']}: already there ({', '.join(f.name for f in done)}), skip (pass --force to redo)")
            continue
        path, body = still_body(e)
        n = e["params"].get("numOutputs", 1)
        files = []
        if path == "/image/generate":
            r = call("POST", path, body)
            for i, b64 in enumerate(r["images"], 1):
                f = out / f"{e['id']}_{i}.png"
                f.write_bytes(base64.b64decode(b64))
                files.append(f)
        else:                                   # multi-edit returns one image per call
            for i in range(1, n + 1):
                ctype, img = call("POST", path, body, raw=True)
                f = out / f"{e['id']}_{i}{mimetypes.guess_extension(ctype.split(';')[0]) or '.png'}"
                f.write_bytes(img)
                files.append(f)
        print(f"{e['id']}: " + ", ".join(str(f.relative_to(ROOT) if f.is_relative_to(ROOT) else f) for f in files))


# ---------- clips ----------
def clip_body(e, images=True):
    p, spec = e["params"], model_spec(e["model"])
    c = spec["model_spec"].get("constraints", {})
    dur = str(p.get("duration", "5")).rstrip("s") + "s"
    durs = c.get("durations", [])
    if durs and dur not in durs:
        secs = lambda x: float(x.rstrip("s"))
        longer = [x for x in durs if x[0].isdigit() and secs(x) >= secs(dur)]
        alt = min(longer, key=secs) if longer else max((x for x in durs if x[0].isdigit()), key=secs)
        if images:
            print(f"note: {e['id']}: {e['model']} has no {dur}, using {alt}", file=sys.stderr)
        dur = alt
    body = {"model": e["model"], "prompt": p["prompt"], "duration": dur}
    if images:                  # a quote needs no images
        body["image_url"] = data_url(p["startImage"])
    if p.get("negativePrompt"):
        body["negative_prompt"] = p["negativePrompt"]
    if p.get("endImage") and images:
        body["end_image_url"] = data_url(p["endImage"])
    if c.get("aspect_ratios"):
        body["aspect_ratio"] = p.get("aspectRatio", "1:1") if p.get("aspectRatio", "1:1") in c["aspect_ratios"] else c["aspect_ratios"][0]
    res = RESOLUTION or DEFAULT_RES.get(e["model"])
    if not res and c.get("resolutions"):
        res = "720p" if "720p" in c["resolutions"] else c["resolutions"][-1]
    if res:
        body["resolution"] = res
    if c.get("audio_configurable"):
        body["audio"] = bool(p.get("generateAudio", False))
    return body


def clip_quote(body):
    q = {k: body[k] for k in ("model", "duration", "aspect_ratio", "resolution", "audio") if k in body}
    return call("POST", "/video/quote", q)["quote"]


def run_quote(a):
    total, seen = 0.0, {}
    for kind, e in load(a.prompts, a.only, a.ids):
        if kind == "stills":
            price = still_price(e)
            label = f"{e['model']} x{e['params'].get('numOutputs', 1)}"
        else:
            b = clip_body(e, images=False)
            sig = (b["model"], b["duration"], b.get("resolution"), b.get("audio"))
            if sig not in seen:
                seen[sig] = clip_quote(b)
            price, label = seen[sig], f"{b['model']} {b['duration']}"
        total += price or 0
        print(f"{e['id']:<28} {label:<45} {'?' if price is None else f'${price:.3f}'}")
    print(f"total ${total:.2f} (plus about 25% for redraws and re-runs)")


def run_clips(a):
    jobs_path = Path(a.jobs)
    jobs = json.loads(jobs_path.read_text()) if jobs_path.is_file() else {}
    for kind, e in load(a.prompts, "cycles", a.ids):
        if a.model:             # model test: own job id and file, e.g. gunner_se_walk__wan
            m = a.model_end if (a.model_end and e["params"].get("endImage")) else a.model
            e = dict(e, model=m, id=f"{e['id']}__{a.tag or a.model.split('-')[0]}")
        if e["id"] in jobs and not a.force:
            print(f"{e['id']}: already queued ({jobs[e['id']]['queue_id']}), skip (pass --force to re-run)")
            continue
        body = clip_body(e)
        r = call("POST", "/video/queue", body)
        jobs[e["id"]] = {"model": r.get("model", body["model"]), "queue_id": r["queue_id"],
                         "download_url": r.get("download_url"), "duration": body["duration"],
                         "queued_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        jobs_path.write_text(json.dumps(jobs, indent=1))      # write after every job: nothing lost on a crash
        print(f"{e['id']}: queued {r['queue_id']}")


def fetch(url):
    with urllib.request.urlopen(url, timeout=600) as r:
        return r.read()


def run_wait(a):
    jobs_path, out = Path(a.jobs), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = json.loads(jobs_path.read_text())
    todo = {k: j for k, j in jobs.items() if not j.get("file") and not j.get("failed") and (not a.ids or k in a.ids)}
    while todo:
        for cid, j in list(todo.items()):
            try:
                ctype, payload = call("POST", "/video/retrieve", {"model": j["model"], "queue_id": j["queue_id"]}, raw=True)
            except SystemExit as err:   # provider failure: record it, keep polling the rest
                j["failed"] = str(err)[:300]
                jobs_path.write_text(json.dumps(jobs, indent=1))
                print(f"{cid}: FAILED {err}")
                del todo[cid]
                continue
            video = None
            if ctype.startswith("video/"):
                video = payload
            else:
                r = json.loads(payload)
                if r.get("status") == "COMPLETED" and (r.get("download_url") or j.get("download_url")):
                    video = fetch(r.get("download_url") or j["download_url"])
                else:
                    secs = (r.get("execution_duration") or 0) / 1000
                    print(f"{cid}: {r.get('status', '?')} {secs:.0f}s")
            if video:
                f = out / f"{cid}.mp4"
                f.write_bytes(video)
                j["file"] = str(f)
                jobs_path.write_text(json.dumps(jobs, indent=1))
                try:            # cleanup only; some models delete the media themselves
                    call("POST", "/video/complete", {"model": j["model"], "queue_id": j["queue_id"]})
                except SystemExit:
                    pass
                print(f"{cid}: saved {f}")
                del todo[cid]
        if todo:
            time.sleep(a.interval)


def run_models(a):
    for m in call("GET", f"/models?type={MODEL_TYPES[a.type]}", auth=False)["data"]:
        if a.grep and a.grep.lower() not in m["id"].lower():
            continue
        s = m["model_spec"]
        c = s.get("constraints", {})
        if a.type == "video":
            info = f"{c.get('model_type', '')} durations={','.join(c.get('durations', []))} res={','.join(c.get('resolutions', []))}"
        else:
            pr = s.get("pricing", {})
            usd = pr.get("generation", {}).get("usd") or next(iter(pr.get("resolutions", {}).values()), {}).get("usd")
            info = (f"${usd} " if usd else "") + (f"max_in={c['maxInputImages']} " if "maxInputImages" in c else "") \
                   + f"aspect={','.join(c.get('aspectRatios', []))}"
        print(f"{m['id']:<45} {info}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("models"); s.add_argument("type", choices=list(MODEL_TYPES)); s.add_argument("--grep")
    for name in ("quote", "stills", "clips"):
        s = sub.add_parser(name)
        s.add_argument("prompts")
        s.add_argument("--ids", type=lambda v: set(v.split(",")))
        if name == "quote":
            s.add_argument("--only", choices=["stills", "cycles"])
        if name in ("quote", "clips"):
            s.add_argument("--resolution", help="clip resolution, e.g. 480p, 720p, 768P (model specific)")
        if name == "stills":
            s.add_argument("--out", default=str(ROOT / "raw"))
            s.add_argument("--force", action="store_true")
            s.add_argument("--model", help="override the model of every selected request")
        if name == "clips":
            s.add_argument("--jobs", default=str(ROOT / "jobs.json"))
            s.add_argument("--force", action="store_true")
            s.add_argument("--model", help="test another clip model; job ids and files get a __tag suffix")
            s.add_argument("--model-end", help="with --model: the model for clips with a pinned end frame")
            s.add_argument("--tag", help="suffix for --model test runs (default: first word of the model id)")
    s = sub.add_parser("wait")
    s.add_argument("--jobs", default=str(ROOT / "jobs.json"))
    s.add_argument("--out", default=str(ROOT / "clips"))
    s.add_argument("--ids", type=lambda v: set(v.split(",")))
    s.add_argument("--interval", type=int, default=20)
    if len(sys.argv) == 1:
        ap.print_help(sys.stderr)
        sys.exit(2)
    a = ap.parse_args()
    global RESOLUTION
    RESOLUTION = getattr(a, "resolution", None)
    {"models": run_models, "quote": run_quote, "stills": run_stills, "clips": run_clips, "wait": run_wait}[a.cmd](a)


if __name__ == "__main__":
    main()
