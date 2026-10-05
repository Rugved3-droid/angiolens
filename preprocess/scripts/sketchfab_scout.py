"""Sketchfab scouting for a photoreal heart (v1.1 item 4; report only, nothing is integrated).

    .venv\\Scripts\\python preprocess\\scripts\\sketchfab_scout.py search            # search + filter + thumbnails + contact sheet
    .venv\\Scripts\\python preprocess\\scripts\\sketchfab_scout.py download UID ...  # needs SKETCHFAB_TOKEN in the environment

Official Sketchfab Data API v3 only (no HTML scraping, no login bypass), gentle with the rate limit (>= 1.1 s between calls).
The token is read from the SKETCHFAB_TOKEN environment variable and sent only in the Authorization header of the download
call; it is never printed, logged or written to disk.
Writes (git-ignored): assets/candidates/_scout/search.json, thumbs/<uid>.jpg, contact_sheet.png;
assets/candidates/<uid>/model.glb (or the glTF zip) and LICENSE.txt.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
C = ROOT / "assets" / "candidates"
S = C / "_scout"
API = "https://api.sketchfab.com/v3"
QUERIES = ["human heart", "heart anatomy", "realistic heart", "heart coronary arteries", "anatomical heart", "cardiac anatomy"]
SORTS = ["-likeCount", "-viewCount"]
ALLOWED = {  # Sketchfab license label -> (short name, URL)
    "CC Attribution": ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"),
    "CC Attribution-ShareAlike": ("CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/"),
    "CC Attribution-NonCommercial": ("CC BY-NC 4.0", "https://creativecommons.org/licenses/by-nc/4.0/"),
    "CC Attribution-NonCommercial-ShareAlike": ("CC BY-NC-SA 4.0", "https://creativecommons.org/licenses/by-nc-sa/4.0/"),
    "CC0 Public Domain": ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/"),
}
EXCLUDE = ["stylized", "stylised", "cartoon", "toon", "low poly", "lowpoly", "low-poly", "game", "icon", "emoji", "valentine",
           "love", "chibi", "symbol", "logo", "sticker", "balloon", "candy", "cake", "pixel", "voxel", "plush", "keychain"]
_last = [0.0]


def get(url, headers=None, raw=False, timeout=60):
    wait = 1.1 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "cpt-scout/1.0", **(headers or {})})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            return data if raw else json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code == 429:                                    # rate limited: back off
                time.sleep(10 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"rate limited: {url.split('?')[0]}")


def search():
    S.mkdir(parents=True, exist_ok=True)
    (S / "thumbs").mkdir(exist_ok=True)
    seen = {}
    for q in QUERIES:
        for sort in SORTS:
            url = f"{API}/search?" + urllib.parse.urlencode({"type": "models", "q": q, "downloadable": "true", "sort_by": sort, "count": 24})
            d = get(url)
            for r in d.get("results", []):
                m = seen.setdefault(r["uid"], {"uid": r["uid"], "hits": []})
                m["hits"].append(f"{q} ({sort[1:]})")
                lic = (r.get("license") or {}).get("label", "")
                thumbs = sorted(r["thumbnails"]["images"], key=lambda t: -t["width"])
                m.update({"name": r["name"], "author": r["user"]["displayName"], "author_url": r["user"].get("profileUrl", ""),
                          "url": r["viewerUrl"], "license": lic, "likes": r["likeCount"], "views": r["viewCount"],
                          "faces": r["faceCount"], "vertices": r["vertexCount"], "tags": [t["name"] for t in r.get("tags", [])],
                          "thumb": thumbs[0]["url"], "thumb_wh": [thumbs[0]["width"], thumbs[0]["height"]],
                          "archives": {k: {kk: v.get(kk) for kk in ("size", "faceCount", "textureCount", "textureMaxResolution")}
                                       for k, v in (r.get("archives") or {}).items() if v},
                          "age_restricted": r.get("isAgeRestricted", False), "description": (r.get("description") or "")[:300]})
            print(f"  {q!r:28} {sort:12} -> {len(d.get('results', []))} results, {len(seen)} unique so far")
    allm = list(seen.values())
    keep = []
    for m in allm:
        text = " ".join([m["name"], " ".join(m["tags"]), m["description"]]).lower()
        m["license_ok"] = m["license"] in ALLOWED
        m["excluded_by"] = [w for w in EXCLUDE if w in text]
        # relevance: some results of "cardiac anatomy" are a museum's skull scans; the name or a tag must name the heart
        named = " ".join([m["name"], " ".join(m["tags"])]).lower()
        m["relevant"] = any(w in named for w in ("heart", "cardiac", "coronar", "cardio"))
        if m["license_ok"] and not m["excluded_by"] and not m["age_restricted"] and m["relevant"]:
            keep.append(m)
    keep.sort(key=lambda m: -(m["likes"] * 4 + m["views"] / 200))
    shortlist = keep[:30]
    for m in shortlist:                                          # the largest thumbnail, to LOOK at
        p = S / "thumbs" / f"{m['uid']}.jpg"
        if not p.exists():
            p.write_bytes(get(m["thumb"], raw=True))
    (S / "search.json").write_text(json.dumps({"date": date.today().isoformat(), "queries": QUERIES, "sorts": SORTS,
                                               "unique": len(allm), "filters_pass": len(keep),
                                               "shortlist": shortlist, "all": allm}, indent=1))
    contact(shortlist, S / "contact_sheet.png")
    print(f"{len(allm)} unique models; {len(keep)} pass license + keyword + relevance filters; shortlist {len(shortlist)} with thumbnails")


def contact(models, out, cols=5, w=384):
    from PIL import Image, ImageDraw, ImageFont
    h = w * 9 // 16
    rows = (len(models) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * (h + 46)), (16, 21, 29))
    g = ImageDraw.Draw(sheet)
    try:
        f = ImageFont.truetype("segoeui.ttf", 15)
    except OSError:
        f = ImageFont.load_default()
    for i, m in enumerate(models):
        im = Image.open(S / "thumbs" / f"{m['uid']}.jpg").convert("RGB")
        im.thumbnail((w, h))
        x, y = (i % cols) * w, (i // cols) * (h + 46)
        sheet.paste(im, (x + (w - im.width) // 2, y + (h - im.height) // 2))
        g.text((x + 6, y + h + 3), f"{i + 1}. {m['name'][:38]}", fill=(233, 237, 242), font=f)
        g.text((x + 6, y + h + 22), f"{m['license'].replace('CC Attribution', 'CC BY')[:24]} · {m['likes']} likes · {m['faces'] // 1000}k tris",
               fill=(154, 166, 180), font=f)
    sheet.save(out)


def download(uids):
    token = os.environ.get("SKETCHFAB_TOKEN", "").strip()
    if not token:
        sys.exit("SKETCHFAB_TOKEN is not set: search and shortlist only (see contact_sheet.png); downloads stopped.")
    meta = {m["uid"]: m for m in json.loads((S / "search.json").read_text())["all"]}
    for uid in uids:
        m = meta[uid]
        d = C / uid
        d.mkdir(parents=True, exist_ok=True)
        info = get(f"{API}/models/{uid}/download", headers={"Authorization": f"Token {token}"})
        fmt = "glb" if "glb" in info else "gltf"
        url, size = info[fmt]["url"], info[fmt].get("size")
        name = "model.glb" if fmt == "glb" else "model_gltf.zip"
        data = get(url, raw=True, timeout=600)                  # a pre-signed URL: no token sent to the storage host
        (d / name).write_bytes(data)
        if fmt == "gltf":
            import zipfile
            with zipfile.ZipFile(d / name) as z:
                z.extractall(d / "gltf")
        lic, lic_url = ALLOWED[m["license"]]
        (d / "LICENSE.txt").write_text(
            f"Title: {m['name']}\nAuthor: {m['author']} ({m['author_url']})\nURL: {m['url']}\n"
            f"License: {lic} ({m['license']})\nLicense URL: {lic_url}\n"
            f"Attribution: \"{m['name']}\" by {m['author']} ({m['url']}), licensed under {lic}.\n"
            f"Downloaded: {date.today().isoformat()} via the Sketchfab Data API v3 ({fmt}, {len(data)} bytes; listed size {size}).\n"
            "Scouting only (v1.1 item 4): not integrated into the app.\n", encoding="utf-8")
        print(f"  {uid}: {name} {len(data) / 1e6:.1f} MB, {lic}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["search"]:
        search()
    elif sys.argv[1:2] == ["download"]:
        download(sys.argv[2:])
    else:
        sys.exit(__doc__)
