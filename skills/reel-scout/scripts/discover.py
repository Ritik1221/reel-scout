"""Find creators for a new scout: scan hashtags' reels, list accounts whose reels keep getting views.

  python discover.py <scout-dir> --hashtags shayari,hindipoetry [--per 40] [--max-usd 0.8] [--raw FILE] [--dry-run]

Writes <scout-dir>/candidates.json (and hashtags.raw.json). Needs APIFY_TOKEN (see scout.py).
Cost ≈ $0.002 per reel scanned: 8 hashtags × 40 reels ≈ $0.60.
"""
from __future__ import annotations

import argparse, json, pathlib, statistics, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from scout import apify_run, norm_handle, owner, utf8_console, views_of  # noqa: E402

HASHTAG_ACTOR = "apify~instagram-hashtag-scraper"
USD_PER_ITEM = 0.0026     # cap math; measured ≈ $0.0019


def clean_tags(s):
    return [t for t in (x.strip().lstrip("#").replace(" ", "").lower() for x in s.split(",")) if t]


def group(items):
    """One row per account; accounts seen more than once first, then by median views."""
    by, seen = {}, set()
    for it in items:
        code, who = it.get("shortCode"), norm_handle(owner(it))
        if not who or not code or not views_of(it) or code in seen:
            continue
        seen.add(code)
        by.setdefault(who, []).append(it)
    rows = []
    for who, its in by.items():
        views = [views_of(i) for i in its]
        best = max(its, key=views_of)
        tags = {i.get("inputUrl", "").rstrip("/").rsplit("/", 1)[-1].lower() for i in its if i.get("inputUrl")}
        rows.append({"handle": who, "name": its[0].get("ownerFullName") or "", "reels": len(its),
                     "median": int(statistics.median(views)), "best": views_of(best), "best_url": best.get("url"),
                     "last_post": max((i.get("timestamp") or "")[:10] for i in its), "hashtags": sorted(tags),
                     "sample": (best.get("caption") or "").replace("\n", " ")[:150]})
    return sorted(rows, key=lambda r: (r["reels"] >= 2, r["median"]), reverse=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("scout_dir")
    p.add_argument("--hashtags", default="")
    p.add_argument("--per", type=int, default=40)
    p.add_argument("--max-usd", type=float, default=0.8)
    p.add_argument("--raw")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    utf8_console()
    d = pathlib.Path(a.scout_dir)
    d.mkdir(parents=True, exist_ok=True)
    tags = clean_tags(a.hashtags)
    if a.raw:
        items = json.loads(pathlib.Path(a.raw).read_text(encoding="utf-8"))
    else:
        if not tags:
            raise SystemExit("Give --hashtags, e.g. --hashtags shayari,hindipoetry")
        est = min(len(tags) * a.per * USD_PER_ITEM, a.max_usd)
        if a.dry_run:
            print(f"Dry run: {len(tags)} hashtags × {a.per} reels ≈ ${est:.2f} (cap ${a.max_usd:.2f})")
            return
        items, usd = apify_run(HASHTAG_ACTOR, {"hashtags": tags, "resultsType": "reels", "resultsLimit": a.per},
                               a.max_usd, USD_PER_ITEM)
        print(f"  apify: {len(items)} reels, ${usd:.2f}")
        (d / "hashtags.raw.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    rows = group(items)
    (d / "candidates.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("  Views below are of the hashtag reels found, not their usual views. Accounts found once may be one-off hits.")
    for r in rows[:25]:
        print(f"  @{r['handle']:<24} {r['reels']} tag reels  views {r['median']:>9,}  best {r['best']:>9,}  "
              f"last {r['last_post']}  {r['sample'][:60]!r}")
    print(f"  {len(rows)} accounts → {d / 'candidates.json'}")


if __name__ == "__main__":
    main()
