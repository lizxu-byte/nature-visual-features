"""Download example images from Wikimedia Commons with licence metadata.

Only files licensed CC0, CC BY or CC BY-SA (any version) are kept; files
with additional restrictions (e.g. personality rights) are skipped. Images
are saved as thumbnails (default 1280 px wide) under data/examples/<category>/
(git-ignored); title, author, licence and source URL are recorded in
examples/ATTRIBUTION.csv, which is committed.

Two modes:

  python scripts/fetch_examples.py                  # search Commons, write ATTRIBUTION.csv
  python scripts/fetch_examples.py --from-attribution examples/ATTRIBUTION.csv
                                                    # re-download exactly the recorded files

Search results on Commons change over time, so the attribution file (not the
search) is the reproducible record of which images were used.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = ("nature-visual-features/0.1 (research demo; "
              "https://github.com/lizxu-byte/nature-visual-features)")
ROOT = Path(__file__).resolve().parents[1]

CATEGORIES = {
    "forest": "forest trees",
    "park_garden": "park garden lawn",
    "water": "lake shore",
    "urban_street": "city street",
    "building_facade": "building facade",
    "window_view": "view through window",
}

FIELDS = ["category", "file", "title", "author", "licence", "licence_url", "source_url",
          "thumb_url", "width", "height"]


def is_allowed_licence(short_name: str) -> bool:
    """True for CC0, CC BY x.y and CC BY-SA x.y (optionally with a jurisdiction port).

    Accepts the spaced form shown on Commons ("CC BY-SA 4.0") and the dashed
    form ("cc-by-sa-4.0"); anything with NC or ND, and non-CC licences, fail.
    """
    tokens = [t for t in re.split(r"[ -]+", (short_name or "").strip().lower()) if t]
    if tokens[:1] == ["cc0"]:
        rest = tokens[1:]
    elif tokens[:2] == ["cc", "by"]:
        rest = tokens[2:]
        if rest[:1] == ["sa"]:
            rest = rest[1:]
    else:
        return False
    if rest and re.fullmatch(r"\d\.\d", rest[0]):
        rest = rest[1:]
    return len(rest) == 0 or (len(rest) == 1 and rest[0].isalpha() and rest[0] not in {"nc", "nd"})


def strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", text or ""))).strip()


def parse_page(page: dict, category: str) -> dict | None:
    """Turn one API page (with imageinfo + extmetadata) into an attribution row, or None."""
    info = (page.get("imageinfo") or [{}])[0]
    meta = info.get("extmetadata", {})

    def value(key):
        return meta.get(key, {}).get("value", "")

    licence = strip_html(value("LicenseShortName"))
    if not is_allowed_licence(licence):
        return None
    if strip_html(value("Restrictions")):
        return None
    if info.get("mime") not in {"image/jpeg", "image/png"}:
        return None
    thumb = info.get("thumburl") or info.get("url")
    if not thumb:
        return None
    title = page["title"]
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", title.removeprefix("File:"))[:80]
    suffix = ".png" if info.get("mime") == "image/png" else ".jpg"
    return {
        "category": category,
        "file": f"{category}/{Path(stem).stem}{suffix}",
        "title": title,
        "author": strip_html(value("Artist")) or "unknown",
        "licence": licence,
        "licence_url": strip_html(value("LicenseUrl")),
        "source_url": info.get("descriptionurl", ""),
        "thumb_url": thumb,
        "width": info.get("thumbwidth") or info.get("width"),
        "height": info.get("thumbheight") or info.get("height"),
    }


def api_get(params: dict) -> dict:
    query = urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})
    req = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def search(query: str, width: int, limit: int = 50) -> list[dict]:
    data = api_get({
        "action": "query", "generator": "search", "gsrnamespace": 6, "gsrlimit": limit,
        "gsrsearch": f"{query} filetype:bitmap",
        "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime",
        "iiurlwidth": width,
    })
    return data.get("query", {}).get("pages", [])


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())


def from_search(per_category: int, width: int, out_dir: Path) -> list[dict]:
    rows = []
    for category, query in CATEGORIES.items():
        kept = 0
        for page in search(query, width):
            row = parse_page(page, category)
            if row is None:
                continue
            download(row["thumb_url"], out_dir / row["file"])
            rows.append(row)
            kept += 1
            print(f"{category}: {row['title']} ({row['licence']})", file=sys.stderr)
            time.sleep(0.5)
            if kept >= per_category:
                break
        if kept < per_category:
            print(f"warning: only {kept} usable images for {category}", file=sys.stderr)
    return rows


def from_attribution(path: Path, out_dir: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        dest = out_dir / row["file"]
        if not dest.exists():
            download(row["thumb_url"], dest)
            time.sleep(0.5)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--per-category", type=int, default=5)
    parser.add_argument("--width", type=int, default=1280, help="thumbnail width in pixels")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data" / "examples")
    parser.add_argument("--attribution", type=Path, default=ROOT / "examples" / "ATTRIBUTION.csv")
    parser.add_argument("--from-attribution", type=Path,
                        help="re-download the files listed in this attribution CSV")
    args = parser.parse_args(argv)

    if args.from_attribution:
        rows = from_attribution(args.from_attribution, args.out_dir)
        print(f"{len(rows)} images in {args.out_dir}", file=sys.stderr)
        return 0
    rows = from_search(args.per_category, args.width, args.out_dir)
    args.attribution.parent.mkdir(parents=True, exist_ok=True)
    with open(args.attribution, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {args.attribution}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
