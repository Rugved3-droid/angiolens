"""Check reference metadata against Crossref (DOI lookups and bibliographic searches); polite, with pauses and retries.

    .venv\\Scripts\\python paper\\scripts\\verify_refs.py

Sends only DOIs / titles (no personal data). Writes paper/results/refs_crossref.json (raw Crossref fields per reference key).
"""
import json
import time
import urllib.parse
import urllib.request

from common import RESULTS

UA = {"User-Agent": "angiolens-reference-check/1.0"}
DOIS = {
    "green2016": "10.5837/bjc.2016.028",
    "sabbak2022": "10.1016/S0735-1097(22)02816-9",
    "samtani2024": "10.1016/S0735-1097(24)04471-1",
    "sadler1998": "10.1002/(SICI)1098-2736(199803)35:3<265::AID-TEA3>3.0.CO;2-P",
    "dumay1994": "10.1109/42.276141",
}
SEARCH = {
    "hestenes1992": "Hestenes Wells Swackhamer Force Concept Inventory The Physics Teacher 1992",
    "chen2000": "Chen Carroll 3-D reconstruction of coronary arterial tree to optimize angiographic visualization",
    "jensen2016": "Jensen virtual reality training in coronary angiography transfer effect real-life catheterisation lab",
    "voelker2016": "Voelker simulation-based training improve procedural skills beginners interventional cardiology",
    "wang2004": "Wang Bovik Sheikh Simoncelli image quality assessment error visibility structural similarity",
}


def get(url):
    for k in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.load(r)["message"]
        except Exception as e:  # noqa: BLE001
            time.sleep(3 * (k + 1))
            err = e
    raise RuntimeError(f"{url}: {err}")


def slim(m):
    return {"DOI": m.get("DOI"), "title": (m.get("title") or [""])[0],
            "authors": [f"{a.get('family', '')} {a.get('given', '')}".strip() for a in m.get("author", [])],
            "journal": (m.get("container-title") or [""])[0], "short_journal": (m.get("short-container-title") or [""])[0],
            "volume": m.get("volume"), "issue": m.get("issue"), "page": m.get("page"),
            "year": (m.get("issued", {}).get("date-parts") or [[None]])[0][0], "type": m.get("type")}


out = {}
for key, doi in DOIS.items():
    out[key] = {"query": doi, "match": slim(get("https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")))}
    time.sleep(1.5)
for key, q in SEARCH.items():
    items = get("https://api.crossref.org/works?rows=3&query.bibliographic=" + urllib.parse.quote(q))["items"]
    out[key] = {"query": q, "candidates": [slim(m) for m in items]}
    time.sleep(1.5)
(RESULTS / "refs_crossref.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
for k, v in out.items():
    for m in ([v["match"]] if "match" in v else v["candidates"]):
        print(k, "|", m["DOI"], "|", m["title"][:90], "|", m["authors"][:4], "|", m["journal"][:40], m["volume"], m["issue"], m["page"], m["year"])
