"""Reel Scout engine: which reels in your niche beat their creator's usual views, plus fresh news.

  python scout.py run <scout-dir> [--force] [--raw FILE] [--no-transcribe] [--no-news] [--dry-run]
  python scout.py status <scout-dir>
  python scout.py mark-used <scout-dir> CODE_OR_URL ...

<scout-dir> holds config.json (written by the reel-scout skill) and the output topics.json.
Keys come from the environment or ~/reel-scout/.env (REEL_SCOUT_HOME changes the folder):
APIFY_TOKEN (needed to scrape), ELEVENLABS_API_KEY (transcripts, optional), EXA_API_KEY (news, optional).
Score = a reel's views / that creator's median views (history kept 90 days in topics.json).
"""
from __future__ import annotations

import argparse, datetime as dt, json, os, pathlib, statistics, sys, time

import requests

REEL_ACTOR = "apify~instagram-reel-scraper"
USD_PER_REEL = 0.0026          # Apify reel scraper, pay per result
USD_PER_NEWS_QUERY = 0.01      # Exa search with page text, roughly
KEEP_DAYS, HISTORY_DAYS, NEWS_DAYS, NEWS_LOOKBACK = 120, 90, 30, 8
RULE = "Take the topic, angle or format. Never copy anyone's words, voice, footage or poems."
DEFAULTS = {"days": 14, "per": 12, "min_ratio": 1.5, "min_views": 5000, "per_creator": 3,
            "scrape_every_days": 13, "max_usd": 1.0}


def home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("REEL_SCOUT_HOME") or pathlib.Path.home() / "reel-scout")


def env(key: str) -> str | None:
    """A key from the environment, else from <home>/.env; None when missing or empty."""
    if os.environ.get(key):
        return os.environ[key]
    f = home() / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            if k.strip() == key and v:
                return v
    return None


def norm_handle(h: str) -> str:
    """'@Name', 'name', 'https://www.instagram.com/name/?hl=en' -> 'name'."""
    h = h.strip()
    if "instagram.com/" in h:
        h = h.split("instagram.com/", 1)[1].split("/")[0].split("?")[0]
    return h.lstrip("@").strip().lower()


def load_config(scout_dir) -> dict:
    p = pathlib.Path(scout_dir) / "config.json"
    if not p.exists():
        raise SystemExit(f"No config at {p}. Run the reel-scout skill to set this scout up.")
    try:
        cfg = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(f"{p} is not valid JSON: {e}")
    niches = {n: [h for h in map(norm_handle, hs) if h] for n, hs in (cfg.get("niches") or {}).items()}
    cfg["niches"] = {n: hs for n, hs in niches.items() if hs}
    if not cfg["niches"]:
        raise SystemExit(f"{p} lists no creators under 'niches'.")
    cfg["slots"] = {n: int((cfg.get("slots") or {}).get(n, 10)) for n in cfg["niches"]}
    cfg["settings"] = {**DEFAULTS, **(cfg.get("settings") or {})}
    cfg["news_queries"] = cfg.get("news_queries") or []
    return cfg


def niche_map(cfg) -> dict:
    return {h: n for n, hs in cfg["niches"].items() for h in hs}


def views_of(it) -> int:
    return it.get("videoPlayCount") or it.get("videoViewCount") or 0


def owner(it) -> str:
    return (it.get("ownerUsername") or "").lower()


def remember(history, items, niche_of, today):
    """history {creator: {code: [views, posted]}}: add this run's reels, drop ones older than HISTORY_DAYS."""
    for it in items:
        if owner(it) in niche_of and views_of(it) and it.get("shortCode"):
            history.setdefault(owner(it), {})[it["shortCode"]] = [views_of(it), (it.get("timestamp") or "")[:10]]
    cutoff = (today - dt.timedelta(days=HISTORY_DAYS)).isoformat()
    kept = {who: {c: v for c, v in codes.items() if v[1] >= cutoff} for who, codes in history.items()}
    return {who: codes for who, codes in kept.items() if codes}


def rank(items, niche_of, history, s):
    """Reels that beat their creator's median (stored history if >= 5 reels, else this run), best first."""
    by = {}
    for it in items:
        if owner(it) in niche_of and views_of(it) and it.get("shortCode"):
            by.setdefault(owner(it), []).append((views_of(it), it))
    winners = []
    for who, rows in by.items():
        past = [v for v, _ in history.get(who, {}).values()]
        med = statistics.median(past if len(past) >= 5 else [v for v, _ in rows])
        best = sorted(((v / med, v, it) for v, it in rows), key=lambda r: r[0], reverse=True)
        for ratio, views, it in best[:s["per_creator"]]:
            if ratio >= s["min_ratio"] and views >= s["min_views"]:
                winners.append({"creator": who, "niche": niche_of[who], "url": it.get("url"), "code": it["shortCode"],
                                "posted": (it.get("timestamp") or "")[:10], "views": views, "median": int(med),
                                "ratio": round(ratio, 1), "likes": it.get("likesCount"), "comments": it.get("commentsCount"),
                                "seconds": it.get("videoDuration"), "caption": (it.get("caption") or "")[:1500],
                                "audio": it.get("audioUrl") or it.get("videoUrl")})
    return sorted(winners, key=lambda w: w["ratio"], reverse=True)


def pick_new(winners, seen, slots):
    """Each niche keeps its own best few, skipping reels already found in earlier runs."""
    return [w for n, k in slots.items() for w in [x for x in winners if x["niche"] == n and x["code"] not in seen][:k]]
