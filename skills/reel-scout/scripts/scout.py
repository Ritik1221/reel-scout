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


def apify_run(actor, payload, max_usd, usd_per_item):
    """Run an Apify actor with a hard spend cap; returns (items, usd)."""
    tok = env("APIFY_TOKEN")
    if not tok:
        raise SystemExit("APIFY_TOKEN is missing: add it to ~/reel-scout/.env (see the README).")
    base = "https://api.apify.com/v2"
    r = requests.post(f"{base}/acts/{actor}/runs", timeout=60, json=payload,
                      params={"token": tok, "maxTotalChargeUsd": max_usd, "maxItems": max(1, int(max_usd / usd_per_item))})
    if r.status_code >= 400:
        raise SystemExit(f"Apify refused the run ({r.status_code}): {r.text[:300]}")
    run = r.json()["data"]
    while run["status"] in ("READY", "RUNNING"):
        time.sleep(10)
        run = requests.get(f"{base}/actor-runs/{run['id']}", params={"token": tok}, timeout=60).json()["data"]
    if run["status"] != "SUCCEEDED":
        raise SystemExit(f"Apify run {run['id']} ended {run['status']}; see https://console.apify.com/actors/runs/{run['id']}")
    items = requests.get(f"{base}/datasets/{run['defaultDatasetId']}/items", params={"token": tok, "clean": "true"},
                         timeout=120).json()
    return items, float(run.get("usageTotalUsd") or 0)


def news_scan(queries, key, today, days=NEWS_LOOKBACK, per=5):
    """Exa news search per query over the last `days` days; returns (items, usd)."""
    since = (today - dt.timedelta(days=days)).isoformat()
    found, usd = {}, 0.0
    for q in queries:
        r = requests.post("https://api.exa.ai/search", headers={"x-api-key": key}, timeout=60, json={
            "query": q, "type": "auto", "category": "news", "numResults": per,
            "startPublishedDate": f"{since}T00:00:00.000Z", "contents": {"text": {"maxCharacters": 1500}}})
        if r.status_code >= 400:
            print(f"  news: {q!r} failed ({r.status_code})")
            continue
        d = r.json()
        usd += (d.get("costDollars") or {}).get("total", 0) or 0
        for h in d.get("results", []):
            if h.get("url") and h["url"] not in found:
                found[h["url"]] = {"query": q, "title": h.get("title"), "url": h["url"],
                                   "published": (h.get("publishedDate") or "")[:10], "text": (h.get("text") or "")[:1500],
                                   "found": today.isoformat(), "used": False}
    return list(found.values()), usd


def transcribe(url, key):
    """ElevenLabs Scribe on the reel's media URL; returns (text, language_code)."""
    api = "https://api.elevenlabs.io/v1/speech-to-text"
    form = {"model_id": "scribe_v2", "tag_audio_events": "false"}
    r = requests.post(api, headers={"xi-api-key": key}, data={**form, "cloud_storage_url": url}, timeout=300)
    if r.status_code >= 400:          # some CDN links refuse remote fetch: send the bytes instead
        media = requests.get(url, timeout=120).content
        r = requests.post(api, headers={"xi-api-key": key}, data=form, files={"file": ("reel.mp4", media)}, timeout=300)
    r.raise_for_status()
    d = r.json()
    return d.get("text", "").strip(), d.get("language_code")


def _load(scout_dir):
    p = pathlib.Path(scout_dir) / "topics.json"
    return json.loads(p.read_text()) if p.exists() else {"reels": [], "news": [], "views": {}, "pool": []}


def _save(scout_dir, pack):
    (pathlib.Path(scout_dir) / "topics.json").write_text(json.dumps(pack, ensure_ascii=False, indent=1))


def _due(last, s, today):
    return not last or (today - dt.date.fromisoformat(last)).days >= s["scrape_every_days"]


def cmd_run(scout_dir, force=False, raw=None, do_transcribe=True, do_news=True, dry_run=False, today=None):
    d, today = pathlib.Path(scout_dir), today or dt.date.today()
    cfg = load_config(d)
    s, niche_of, old = cfg["settings"], niche_map(cfg), _load(d)
    last = old.get("scraped", "")
    scrape_now = not raw and (force or _due(last, s, today))
    eleven = env("ELEVENLABS_API_KEY") if do_transcribe else None
    exa = env("EXA_API_KEY") if do_news and cfg["news_queries"] else None
    if dry_run:
        reels_usd = min(len(niche_of) * s["per"] * USD_PER_REEL, s["max_usd"]) if scrape_now else 0
        news_usd = len(cfg["news_queries"]) * USD_PER_NEWS_QUERY if exa else 0
        print(f"Dry run for '{cfg.get('name', d.name)}':")
        print(f"  creators: {len(niche_of)} — " + (f"scrape up to {s['per']} reels each from the last {s['days']} days, "
              f"≤ ${reels_usd:.2f} (cap ${s['max_usd']:.2f})" if scrape_now else f"not due (last scraped {last})"))
        print(f"  transcripts: {'on (ElevenLabs, a few cents per reel)' if eleven else 'off'}")
        n = len(cfg["news_queries"])
        print(f"  news: " + (f"{n} searches, ≈ ${news_usd:.2f}" if exa else "off"))
        print(f"  estimated total: ≈ ${reels_usd + news_usd:.2f}")
        return None
    spent = 0.0
    if raw:
        items = json.loads(pathlib.Path(raw).read_text())
    elif scrape_now:
        items, usd = apify_run(REEL_ACTOR, {"username": list(niche_of), "resultsLimit": s["per"],
                                            "onlyPostsNewerThan": f"{s['days']} days", "skipPinnedPosts": True},
                               s["max_usd"], USD_PER_REEL)
        spent += usd
        print(f"  apify: {len(items)} reels, ${usd:.2f}")
        (d / "topics.raw.json").write_text(json.dumps(items, ensure_ascii=False))
        last = today.isoformat()
    else:
        print(f"  creators: last scraped {last}; next scrape after {s['scrape_every_days']} days (saves Apify credit). News only.")
        items = []
    history = remember(old.get("views", {}), items, niche_of, today)
    seen = {r["code"] for r in old.get("reels", [])}
    new = pick_new(rank(items, niche_of, history, s), seen, cfg["slots"])
    print(f"  {len(new)} new reels beat their creator's usual views by {s['min_ratio']}x+")
    if do_transcribe and new and not eleven:
        print("  No ELEVENLABS_API_KEY: winners keep captions only (no transcripts).")
    for w in new:
        audio = w.pop("audio", None)
        if eleven and audio:
            try:
                w["transcript"], w["language"] = transcribe(audio, eleven)
            except Exception as e:      # a missing transcript shouldn't lose the topic
                w["transcript"], w["error"] = "", str(e)[:200]
        w["found"], w["used"] = today.isoformat(), False
    news = []
    if do_news and cfg["news_queries"] and not exa:
        print("  No EXA_API_KEY: news skipped.")
    if exa:
        known = {n["url"] for n in old.get("news", [])}
        got, usd = news_scan(cfg["news_queries"], exa, today)
        spent += usd
        news = [n for n in got if n["url"] not in known]
        print(f"  news: {len(news)} new items, ${usd:.3f}")
    cutoff = (today - dt.timedelta(days=KEEP_DAYS)).isoformat()
    ncut = (today - dt.timedelta(days=NEWS_DAYS)).isoformat()
    pool = {r["code"]: r for r in old.get("pool", []) if r.get("posted", "9") >= cutoff}
    for it in items:
        who = owner(it)
        if who in niche_of and it.get("shortCode"):
            med = statistics.median([v for v, _ in history.get(who, {}).values()] or [0])
            pool[it["shortCode"]] = {"creator": who, "niche": niche_of[who], "code": it["shortCode"], "url": it.get("url"),
                                     "posted": (it.get("timestamp") or "")[:10], "views": views_of(it),
                                     "ratio": round(views_of(it) / med, 1) if med else None,
                                     "caption": (it.get("caption") or "")[:400]}
    pack = {"generated": today.isoformat(), "scraped": last, "rule": RULE,
            "reels": new + [r for r in old.get("reels", []) if r.get("found", "9") >= cutoff],
            "news": news + [n for n in old.get("news", []) if n.get("found", "9") >= ncut],
            "views": history,
            "pool": sorted(pool.values(), key=lambda r: r["posted"], reverse=True)}
    _save(d, pack)
    for w in new:
        print(f"  {w['ratio']}x  {w['views']:>9,}  @{w['creator']:<20} {w['caption'][:70]!r}")
    print(f"  spent: ${spent:.2f} (plus ElevenLabs minutes if transcripts ran)")
    return pack


def cmd_status(scout_dir, today=None):
    d, today = pathlib.Path(scout_dir), today or dt.date.today()
    cfg, pack = load_config(d), _load(d)
    s, last = cfg["settings"], pack.get("scraped", "")
    nxt = "due now" if _due(last, s, today) else (dt.date.fromisoformat(last) + dt.timedelta(days=s["scrape_every_days"])).isoformat()
    st = {"name": cfg.get("name", d.name), "creators": len(niche_map(cfg)), "last_scrape": last or "never",
          "next_scrape": nxt, "reels": len(pack["reels"]), "unused_reels": sum(not r.get("used") for r in pack["reels"]),
          "unused_news": sum(not n.get("used") for n in pack["news"]), "pool": len(pack.get("pool", [])),
          "keys": {k: bool(env(k)) for k in ("APIFY_TOKEN", "ELEVENLABS_API_KEY", "EXA_API_KEY")}}
    print(json.dumps(st, indent=1))
    return st


def cmd_mark_used(scout_dir, refs):
    pack, missing = _load(scout_dir), []
    for ref in refs:
        hits = [x for x in pack["reels"] + pack["news"] if ref in (x.get("code"), x.get("url"))]
        for x in hits:
            x["used"] = True
        if not hits:
            missing.append(ref)
    _save(scout_dir, pack)
    if missing:
        print("Not found: " + ", ".join(missing))
    return missing


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("scout_dir")
    r.add_argument("--force", action="store_true")
    r.add_argument("--raw")
    r.add_argument("--no-transcribe", action="store_true")
    r.add_argument("--no-news", action="store_true")
    r.add_argument("--dry-run", action="store_true")
    sub.add_parser("status").add_argument("scout_dir")
    m = sub.add_parser("mark-used")
    m.add_argument("scout_dir")
    m.add_argument("refs", nargs="+")
    a = p.parse_args(argv)
    if a.cmd == "run":
        cmd_run(a.scout_dir, a.force, a.raw, not a.no_transcribe, not a.no_news, a.dry_run)
    elif a.cmd == "status":
        cmd_status(a.scout_dir)
    else:
        cmd_mark_used(a.scout_dir, a.refs)


if __name__ == "__main__":
    main()
