"""Find creators for a new scout: scan hashtags' reels, list accounts whose reels keep getting views.

  python discover.py <scout-dir> --hashtags shayari,hindipoetry [--per 40] [--max-usd 0.8] [--raw FILE] [--dry-run]
  python discover.py <scout-dir> --check handle1,handle2,... [--max-usd 0.1] [--raw FILE] [--dry-run]

1. --hashtags: writes <scout-dir>/candidates.json (and hashtags.raw.json).
   Cost ≈ $0.002 per reel scanned: 8 hashtags × 40 reels ≈ $0.60.
2. --check: looks up a shortlist's profiles (followers, posts in the last 14 days, usual likes, bio, repost hints)
   so only active, original creators go into the scout. Writes profiles.json. Cost ≈ $0.0026 per profile.
Needs APIFY_TOKEN (see scout.py).
"""
from __future__ import annotations

import argparse, datetime as dt, json, pathlib, re, statistics, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from scout import apify_run, norm_handle, owner, utf8_console, views_of  # noqa: E402

HASHTAG_ACTOR = "apify~instagram-hashtag-scraper"
PROFILE_ACTOR = "apify~instagram-profile-scraper"
USD_PER_ITEM = 0.0026     # cap math; measured ≈ $0.0019
USD_PER_PROFILE = 0.0026
ACTIVE_POSTS_14D = 3      # the scout needs 3+ reels to know a creator's usual views
# bio phrases that usually mean a page reposts other people's work (any language page may still write these in English)
REPOST = re.compile(r"credit|repost|dm for (removal|remove)|no copyright|not (the )?owner|all rights.*owners|fan ?page", re.I)


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


def profile_rows(items, today):
    """One row per looked-up profile: reach, recent activity, usual views, repost hint."""
    since = (today - dt.timedelta(days=14)).isoformat()
    rows = []
    for it in items:
        who = norm_handle(it.get("username") or "")
        if not who:
            continue
        if it.get("error"):
            rows.append({"handle": who, "error": it["error"]})
            continue
        posts = it.get("latestPosts") or []
        likes = [p["likesCount"] for p in posts if (p.get("likesCount") or 0) > 0]   # profile posts carry no view counts
        n14 = sum((p.get("timestamp") or "")[:10] >= since for p in posts)
        bio = (it.get("biography") or "").replace("\n", " ")
        rows.append({"handle": who, "name": it.get("fullName") or "", "followers": it.get("followersCount"),
                     "posts_14d": n14, "usual_likes": int(statistics.median(likes)) if likes else None,
                     "active": n14 >= ACTIVE_POSTS_14D, "repost_hint": bool(REPOST.search(bio)),
                     "private": bool(it.get("private")), "verified": bool(it.get("verified")), "bio": bio[:200]})
    return rows


def check(d, handles, a):
    if a.raw:
        items = json.loads(pathlib.Path(a.raw).read_text(encoding="utf-8"))
    else:
        est = min(len(handles) * USD_PER_PROFILE, a.max_usd)
        if a.dry_run:
            print(f"Dry run: look up {len(handles)} profiles ≈ ${est:.2f} (cap ${a.max_usd:.2f})")
            return
        items, usd = apify_run(PROFILE_ACTOR, {"usernames": handles}, a.max_usd, USD_PER_PROFILE)
        print(f"  apify: {len(items)} profiles, ${usd:.2f}")
        (d / "profiles.raw.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    rows = profile_rows(items, dt.date.today())
    (d / "profiles.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in rows:
        if r.get("error"):
            print(f"  @{r['handle']:<24} not found ({r['error']})")
            continue
        flags = [f for f, on in (("QUIET", not r["active"]), ("REPOST?", r["repost_hint"]), ("PRIVATE", r["private"])) if on]
        print(f"  @{r['handle']:<24} {r['followers'] or 0:>10,} followers  {r['posts_14d']} posts/14d  "
              f"usual likes {r['usual_likes'] or 0:>8,}  {' '.join(flags) or 'ok'}  {r['bio'][:50]!r}")
    print(f"  QUIET = fewer than {ACTIVE_POSTS_14D} posts in 14 days (the scout can't score them). "
          f"REPOST? = bio suggests reposted content. → {d / 'profiles.json'}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("scout_dir")
    p.add_argument("--hashtags", default="")
    p.add_argument("--per", type=int, default=40)
    p.add_argument("--check", default="", help="comma-separated handles to look up")
    p.add_argument("--max-usd", type=float, default=None)
    p.add_argument("--raw")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    utf8_console()
    d = pathlib.Path(a.scout_dir)
    d.mkdir(parents=True, exist_ok=True)
    if a.check:
        a.max_usd = 0.1 if a.max_usd is None else a.max_usd
        handles = [h for h in map(norm_handle, a.check.split(",")) if h]
        return check(d, handles, a)
    a.max_usd = 0.8 if a.max_usd is None else a.max_usd
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
