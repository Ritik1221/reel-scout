# Reel Scout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A public Claude Code plugin whose `reel-scout` skill interviews any creator, sets up their own Instagram scout, runs it and writes a weekly "5 ideas" brief.

**Architecture:** Two small Python scripts bundled inside the skill (`scout.py` engine, `discover.py` creator finder), both config-driven and network calls isolated in a few functions. `SKILL.md` drives the conversation and calls the scripts. User data lives outside the plugin in `~/reel-scout/<name>/`.

**Tech Stack:** Python ≥3.10, `requests`; pytest; Apify (`apify~instagram-reel-scraper`, `apify~instagram-hashtag-scraper`), ElevenLabs Scribe, Exa search; Claude Code plugin manifests.

**Spec:** `docs/superpowers/specs/2026-11-11-reel-scout-design.md`

## Global Constraints

- Python ≥3.10; only third-party runtime dependency: `requests`.
- User data never inside the plugin folder: `~/reel-scout/` (override `REEL_SCOUT_HOME`); keys from env first, then `~/reel-scout/.env`.
- Only `APIFY_TOKEN` is required; missing `ELEVENLABS_API_KEY` / `EXA_API_KEY` skip that step with one plain line.
- Rule text everywhere: "Take the topic, angle or format. Never copy anyone's words, voice, footage or poems."
- Ask before every paid call (skill); scripts enforce `max_usd` caps; `--dry-run` spends nothing.
- No Google Drive, no Export Radar creators/topics/keys in this repo.
- Settings defaults: `days 14, per 12, min_ratio 1.5, min_views 5000, per_creator 3, scrape_every_days 13, max_usd 1.0`.

## Review Focus

- Handles typed as `@Name`, uppercase or full profile URLs → normalised to the bare lowercase handle (Task 1 test).
- Apify returns error items (private/missing account, no `ownerUsername`, 0 views) → skipped, no crash (Task 1 test).
- Bad/missing `APIFY_TOKEN` or Apify 401 → one plain message, no traceback (Task 2 test).
- Running twice on the same scrape → no duplicate winners, view history kept (Task 2 test).
- Hindi/Urdu captions → saved as readable UTF-8, not `\u` escapes (Task 2 test).

---

## File map

```
.claude-plugin/plugin.json          plugin manifest
.claude-plugin/marketplace.json     single-plugin marketplace (source "./")
skills/reel-scout/SKILL.md          the conversation: setup, run, brief, rules
skills/reel-scout/references/interview.md
skills/reel-scout/references/brief.md
skills/reel-scout/scripts/scout.py      engine: config, keys, scrape, rank, transcribe, news, pack, CLI
skills/reel-scout/scripts/discover.py   hashtag scan → candidates.json
tests/conftest.py                   puts scripts/ on sys.path, isolates REEL_SCOUT_HOME + keys
tests/test_scout.py
tests/test_discover.py
pyproject.toml                      dev: `uv run pytest`
README.md, LICENSE, .gitignore
```

---

### Task 1: Scaffold + engine core (config, keys, scoring)

**Files:**
- Create: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml`, `.gitignore`, `LICENSE`
- Create: `skills/reel-scout/scripts/scout.py` (core functions only)
- Test: `tests/conftest.py`, `tests/test_scout.py`

**Interfaces — Produces:**
- `home() -> pathlib.Path`, `env(key: str) -> str | None`, `norm_handle(h: str) -> str`
- `load_config(scout_dir) -> dict` (normalised `niches`, `slots`, merged `settings`, `news_queries`)
- `niche_map(cfg) -> dict[str, str]`
- `views_of(item) -> int`, `owner(item) -> str`
- `remember(history: dict, items: list, niche_of: dict, today: date) -> dict`
- `rank(items, niche_of, history, s: dict) -> list[dict]` (winner dicts incl. `audio`)
- `pick_new(winners, seen: set, slots: dict) -> list[dict]`
- constants `RULE`, `DEFAULTS`, `REEL_ACTOR`, `USD_PER_REEL`, `KEEP_DAYS`, `HISTORY_DAYS`, `NEWS_DAYS`, `NEWS_LOOKBACK`

- [ ] **Step 1: Scaffold files**

`.claude-plugin/plugin.json`:
```json
{
  "name": "reel-scout",
  "description": "Set up your own Instagram scout for any niche: finds reels beating their creator's usual views, fresh news, and writes 5 ideas a week.",
  "version": "0.1.0",
  "author": {"name": "Ritik"},
  "license": "MIT",
  "keywords": ["instagram", "reels", "content", "creators", "trends"]
}
```

`.claude-plugin/marketplace.json`:
```json
{
  "name": "reel-scout",
  "owner": {"name": "Ritik"},
  "plugins": [
    {"name": "reel-scout", "source": "./", "description": "Your own Instagram reel scout for any niche."}
  ]
}
```

`pyproject.toml`:
```toml
[project]
name = "reel-scout"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["requests>=2.28"]

[dependency-groups]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.gitignore`:
```
__pycache__/
.venv/
.pytest_cache/
.env
uv.lock
```

`LICENSE`: standard MIT text, `Copyright (c) 2026 Ritik`.

`tests/conftest.py`:
```python
import pathlib, sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills" / "reel-scout" / "scripts"))


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Every test gets an empty ~/reel-scout and no real keys."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("REEL_SCOUT_HOME", str(home))
    for k in ("APIFY_TOKEN", "ELEVENLABS_API_KEY", "EXA_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    return home


def reel(who, code, views, posted="2026-11-05", caption="cap", **extra):
    """A fake Apify reel item."""
    return {"ownerUsername": who, "shortCode": code, "videoPlayCount": views, "timestamp": f"{posted}T10:00:00.000Z",
            "url": f"https://www.instagram.com/p/{code}/", "caption": caption, "likesCount": 1, "commentsCount": 1,
            "videoDuration": 30.0, "audioUrl": f"https://cdn/{code}.mp4", **extra}
```

- [ ] **Step 2: Write the failing tests** — `tests/test_scout.py`:
```python
import datetime as dt, json

import pytest

import scout
from conftest import reel

TODAY = dt.date(2026, 11, 11)
S = dict(scout.DEFAULTS)


def write_cfg(d, **over):
    cfg = {"name": "poetry", "niches": {"main": ["@Alice", "https://www.instagram.com/bob/?hl=en"]}, **over}
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(json.dumps(cfg))
    return d


def test_norm_handle():
    assert scout.norm_handle(" @Foo.Bar ") == "foo.bar"
    assert scout.norm_handle("https://www.instagram.com/foo_1/?hl=en") == "foo_1"
    assert scout.norm_handle("instagram.com/foo/reels/") == "foo"


def test_load_config_normalises_and_fills_defaults(tmp_path):
    cfg = scout.load_config(write_cfg(tmp_path / "s", settings={"min_views": 100}))
    assert cfg["niches"] == {"main": ["alice", "bob"]}
    assert cfg["slots"] == {"main": 10}
    assert cfg["settings"]["min_views"] == 100 and cfg["settings"]["days"] == 14
    assert cfg["news_queries"] == []


def test_load_config_errors(tmp_path):
    with pytest.raises(SystemExit, match="No config"):
        scout.load_config(tmp_path / "missing")
    with pytest.raises(SystemExit, match="no creators"):
        scout.load_config(write_cfg(tmp_path / "e", niches={"main": ["  ", "@"]}))
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "config.json").write_text("{nope")
    with pytest.raises(SystemExit, match="not valid JSON"):
        scout.load_config(tmp_path / "bad")


def test_env_reads_dotfile_and_env_wins(isolated_home, monkeypatch):
    (isolated_home / ".env").write_text('APIFY_TOKEN="from-file"\nEXA_API_KEY=\n')
    assert scout.env("APIFY_TOKEN") == "from-file"
    assert scout.env("EXA_API_KEY") is None
    monkeypatch.setenv("APIFY_TOKEN", "from-env")
    assert scout.env("APIFY_TOKEN") == "from-env"


def test_remember_adds_and_drops_old():
    hist = {"alice": {"OLD": [10, "2026-07-01"], "KEEP": [20, "2026-10-01"]}}
    out = scout.remember(hist, [reel("Alice", "NEW", 30), reel("stranger", "X", 99)], {"alice": "main"}, TODAY)
    assert out == {"alice": {"KEEP": [20, "2026-10-01"], "NEW": [30, "2026-11-05"]}}


def test_rank_uses_stored_median_when_5_or_more():
    hist = {"alice": {f"h{i}": [1000, "2026-11-01"] for i in range(5)}}
    items = [reel("alice", "A", 9000), reel("alice", "B", 1200)]
    w = scout.rank(items, {"alice": "main"}, hist, {**S, "min_views": 0})
    assert [x["code"] for x in w] == ["A"] and w[0]["median"] == 1000 and w[0]["ratio"] == 9.0
    assert w[0]["niche"] == "main" and w[0]["audio"] == "https://cdn/A.mp4"


def test_rank_thresholds_and_junk_items():
    items = [reel("alice", c, v) for c, v in [("a", 100), ("b", 100), ("c", 100), ("d", 900), ("e", 800), ("f", 700), ("g", 600)]]
    items += [{"error": "not_found", "url": "x"}, reel("alice", "z", 0), reel("", "q", 5000)]
    w = scout.rank(items, {"alice": "main"}, {}, {**S, "min_views": 650, "per_creator": 2})
    assert [x["code"] for x in w] == ["d", "e"]          # median 600 from this run; f/g below ratio or views; capped at 2


def test_pick_new_respects_slots_and_seen():
    ws = [{"code": c, "niche": n} for c, n in [("a", "main"), ("b", "main"), ("c", "main"), ("d", "insp")]]
    got = scout.pick_new(ws, {"a"}, {"main": 1, "insp": 5})
    assert [w["code"] for w in got] == ["b", "d"]
```

- [ ] **Step 3: Run to see them fail**

Run: `cd /Users/ritik/Expo/reel-scout && uv run pytest -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scout'`

- [ ] **Step 4: Implement** — `skills/reel-scout/scripts/scout.py`:
```python
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
```

- [ ] **Step 5: Run tests** — `uv run pytest -q` → all pass.

- [ ] **Step 6: Commit**
```bash
git add -A && git commit -m "Engine core: config, keys, scoring"
```

---

### Task 2: Engine run / status / mark-used + network calls

**Files:**
- Modify: `skills/reel-scout/scripts/scout.py` (append)
- Test: `tests/test_scout.py` (append)

**Interfaces — Consumes:** Task 1. **Produces:**
- `apify_run(actor: str, payload: dict, max_usd: float, usd_per_item: float) -> tuple[list, float]`
- `news_scan(queries, key, today, days=NEWS_LOOKBACK, per=5) -> tuple[list, float]`
- `transcribe(url, key) -> tuple[str, str | None]`
- `cmd_run(scout_dir, force=False, raw=None, do_transcribe=True, do_news=True, dry_run=False, today=None) -> dict | None`
- `cmd_status(scout_dir, today=None) -> dict`, `cmd_mark_used(scout_dir, refs) -> list[str]` (refs not found)
- `main(argv=None)`; `topics.json` = `{generated, scraped, rule, reels, news, views, pool}`

- [ ] **Step 1: Failing tests** — append to `tests/test_scout.py`:
```python
def setup_scout(tmp_path, **over):
    d = write_cfg(tmp_path / "poetry", settings={"min_views": 0}, **over)
    hist = {"alice": {f"h{i}": [1000, "2026-11-01"] for i in range(5)}}
    (d / "topics.json").write_text(json.dumps({"scraped": "2026-10-01", "views": hist, "reels": [], "news": [], "pool": []}))
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps([reel("alice", "WIN", 8000, caption="दिल की बात"), reel("alice", "MEH", 900), reel("bob", "B1", 50)]))
    return d, raw


@pytest.fixture
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network call")
    monkeypatch.setattr(scout.requests, "post", boom)
    monkeypatch.setattr(scout.requests, "get", boom)


def test_run_with_raw_writes_pack_and_skips_missing_keys(tmp_path, no_network, capsys):
    d, raw = setup_scout(tmp_path)
    pack = scout.cmd_run(d, raw=raw, today=TODAY)
    out = capsys.readouterr().out
    assert "No ELEVENLABS_API_KEY" in out
    assert [r["code"] for r in pack["reels"]] == ["WIN"]
    assert pack["reels"][0]["used"] is False and "audio" not in pack["reels"][0]
    assert pack["rule"] == scout.RULE and pack["scraped"] == "2026-10-01"
    text = (d / "topics.json").read_text()
    assert "दिल की बात" in text                          # readable UTF-8
    assert {r["code"] for r in pack["pool"]} == {"WIN", "MEH", "B1"}
    again = scout.cmd_run(d, raw=raw, today=TODAY)       # same scrape twice: no duplicates
    assert [r["code"] for r in again["reels"]] == ["WIN"]
    assert "WIN" in again["views"]["alice"]


def test_run_not_due_does_not_scrape(tmp_path, monkeypatch):
    d, _ = setup_scout(tmp_path)
    t = json.loads((d / "topics.json").read_text()); t["scraped"] = "2026-11-05"
    (d / "topics.json").write_text(json.dumps(t))
    monkeypatch.setattr(scout, "apify_run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("scraped")))
    pack = scout.cmd_run(d, today=TODAY, do_news=False)
    assert pack["reels"] == [] and pack["scraped"] == "2026-11-05"


def test_run_due_scrapes_with_caps(tmp_path, monkeypatch):
    d, _ = setup_scout(tmp_path)
    seen = {}
    def fake(actor, payload, max_usd, usd_per_item):
        seen.update(actor=actor, payload=payload, max_usd=max_usd)
        return [reel("alice", "NEW", 5000)], 0.03
    monkeypatch.setattr(scout, "apify_run", fake)
    pack = scout.cmd_run(d, today=TODAY, do_transcribe=False, do_news=False)
    assert seen["actor"] == scout.REEL_ACTOR and seen["max_usd"] == 1.0
    assert seen["payload"]["username"] == ["alice", "bob"] and seen["payload"]["onlyPostsNewerThan"] == "14 days"
    assert pack["scraped"] == "2026-11-11" and (d / "topics.raw.json").exists()


def test_dry_run_spends_and_writes_nothing(tmp_path, no_network, capsys):
    d, _ = setup_scout(tmp_path, news_queries=["a", "b"])
    before = (d / "topics.json").read_text()
    assert scout.cmd_run(d, today=TODAY, dry_run=True) is None
    out = capsys.readouterr().out
    assert "Dry run" in out and "$" in out
    assert (d / "topics.json").read_text() == before


def test_apify_without_token_is_plain_message():
    with pytest.raises(SystemExit, match="APIFY_TOKEN is missing"):
        scout.apify_run(scout.REEL_ACTOR, {}, 1.0, scout.USD_PER_REEL)


def test_apify_rejected_token(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "bad")
    class R:
        status_code, text = 401, '{"error":{"type":"user-or-token-not-found"}}'
    monkeypatch.setattr(scout.requests, "post", lambda *a, **k: R())
    with pytest.raises(SystemExit, match="Apify refused the run \\(401\\)"):
        scout.apify_run(scout.REEL_ACTOR, {}, 1.0, scout.USD_PER_REEL)


def test_status_and_mark_used(tmp_path, no_network):
    d, raw = setup_scout(tmp_path)
    scout.cmd_run(d, raw=raw, today=TODAY)
    st = scout.cmd_status(d, today=TODAY)
    assert st["unused_reels"] == 1 and st["next_scrape"] == "due now"
    missing = scout.cmd_mark_used(d, ["https://www.instagram.com/p/WIN/", "NOPE"])
    assert missing == ["NOPE"]
    assert scout.cmd_status(d, today=TODAY)["unused_reels"] == 0
```

- [ ] **Step 2: Run** `uv run pytest -q` → new tests FAIL (`AttributeError: module 'scout' has no attribute 'cmd_run'`).

- [ ] **Step 3: Implement** — append to `scout.py`:
```python
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
```

- [ ] **Step 4: Run** `uv run pytest -q` → all pass. Also `uv run python skills/reel-scout/scripts/scout.py --help` prints usage.

- [ ] **Step 5: Commit** `git add -A && git commit -m "Engine: run, status, mark-used"`

---

### Task 3: Creator discovery

**Files:** Create `skills/reel-scout/scripts/discover.py`; Test `tests/test_discover.py`

**Interfaces — Consumes:** `scout.apify_run`, `scout.views_of`, `scout.owner`, `scout.norm_handle`. **Produces:**
`clean_tags(s: str) -> list[str]`, `group(items) -> list[dict]` (keys `handle, name, reels, median, best, best_url,
last_post, hashtags, sample`), `main(argv=None)` writing `<scout-dir>/candidates.json` + `hashtags.raw.json`.

- [ ] **Step 1: Failing tests** — `tests/test_discover.py`:
```python
import json

import discover
from conftest import reel


def tagged(who, code, views, tag, posted="2026-11-05"):
    return reel(who, code, views, posted, ownerFullName=who.title(), inputUrl=f"https://www.instagram.com/explore/tags/{tag}")


def test_clean_tags():
    assert discover.clean_tags("#Shayari, hindi poetry ,,#Urdu") == ["shayari", "hindipoetry", "urdu"]


def test_group_prefers_repeat_creators_then_median():
    items = [tagged("one", "a", 900000, "shayari"),
             tagged("steady", "b", 20000, "shayari"), tagged("steady", "c", 30000, "urdu", "2026-11-09"),
             tagged("small", "d", 2000, "shayari"), tagged("small", "e", 3000, "shayari"),
             {"error": "no_items"}, tagged("steady", "b", 20000, "shayari")]          # duplicate row
    g = discover.group(items)
    assert [c["handle"] for c in g] == ["steady", "small", "one"]
    s = g[0]
    assert s["reels"] == 2 and s["median"] == 25000 and s["best"] == 30000
    assert s["last_post"] == "2026-11-09" and s["hashtags"] == ["shayari", "urdu"]
    assert s["best_url"] == "https://www.instagram.com/p/c/"


def test_main_with_raw_writes_candidates(tmp_path, capsys):
    raw = tmp_path / "h.json"
    raw.write_text(json.dumps([tagged("steady", "b", 20000, "shayari"), tagged("steady", "c", 30000, "shayari")]))
    discover.main([str(tmp_path / "poetry"), "--raw", str(raw)])
    got = json.loads((tmp_path / "poetry" / "candidates.json").read_text())
    assert got[0]["handle"] == "steady"
    assert "@steady" in capsys.readouterr().out
```

- [ ] **Step 2: Run** `uv run pytest -q tests/test_discover.py` → FAIL (`No module named 'discover'`).

- [ ] **Step 3: Implement** — `skills/reel-scout/scripts/discover.py`:
```python
"""Find creators for a new scout: scan hashtags' reels, list accounts whose reels keep getting views.

  python discover.py <scout-dir> --hashtags shayari,hindipoetry [--per 40] [--max-usd 0.8] [--raw FILE] [--dry-run]

Writes <scout-dir>/candidates.json (and hashtags.raw.json). Needs APIFY_TOKEN (see scout.py).
Cost ≈ $0.002 per reel scanned: 8 hashtags × 40 reels ≈ $0.60.
"""
from __future__ import annotations

import argparse, json, pathlib, statistics, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from scout import apify_run, norm_handle, owner, views_of  # noqa: E402

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
    d = pathlib.Path(a.scout_dir)
    d.mkdir(parents=True, exist_ok=True)
    tags = clean_tags(a.hashtags)
    if a.raw:
        items = json.loads(pathlib.Path(a.raw).read_text())
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
        (d / "hashtags.raw.json").write_text(json.dumps(items, ensure_ascii=False))
    rows = group(items)
    (d / "candidates.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    for r in rows[:25]:
        print(f"  @{r['handle']:<24} {r['reels']} reels  median {r['median']:>9,}  best {r['best']:>9,}  "
              f"last {r['last_post']}  {r['sample'][:60]!r}")
    print(f"  {len(rows)} accounts → {d / 'candidates.json'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run** `uv run pytest -q` → all pass.
- [ ] **Step 5: Commit** `git add -A && git commit -m "Discovery: hashtag scan to candidate creators"`

---

### Task 4: The skill (SKILL.md + references)

**Files:** Create `skills/reel-scout/SKILL.md`, `skills/reel-scout/references/interview.md`, `skills/reel-scout/references/brief.md`

**Interfaces — Consumes:** CLI of Task 2 (`run|status|mark-used`, flags) and Task 3 (`--hashtags --per --max-usd --dry-run`), files `config.json`, `topics.json`, `candidates.json`, `briefs/`.

- [ ] **Step 1: Write `SKILL.md`** with frontmatter:
```yaml
---
name: reel-scout
description: Set up and run your own Instagram reel scout for any niche (poetry, cooking, fitness, business...). Use when someone says "set up a scout", "/reel-scout", "find what's working in my niche", "what should I post this week", "run my scout", or wants trending reel ideas from creators like them. Interviews the user, finds creators to watch, scores reels against each creator's usual views, and writes a weekly 5-idea brief.
---
```
Body sections (plain, imperative, short):
1. **What this does** (3 lines) + the RULE verbatim.
2. **Paths:** scripts in this skill's base directory (`<base>/scripts/scout.py`, `discover.py`); user data `~/reel-scout/<name>/` (or `$REEL_SCOUT_HOME`); never write user data inside the skill folder. How to run Python: `uv run --with requests python <script>` if `uv` exists, else `python3 <script>` after checking `python3 -c "import requests"` (offer `python3 -m pip install --user requests`).
3. **Pick the mode:** list `~/reel-scout/*/config.json`. None → Setup. One → Run. Several → ask which (or "new").
4. **Setup:** follow `references/interview.md` one question at a time; keys step (write `~/reel-scout/.env`, `chmod 600`, never echo keys back; verify Apify with a free call `curl -s "https://api.apify.com/v2/users/me?token=$APIFY_TOKEN"` reading the token from the file, report only username/plan); propose hashtags + news queries; `discover.py --dry-run` → state cost → ask → run → show top 25 as a table (handle, reels, median, best, last post) → user picks 10–20 + own list; optional `inspiration` niche; write `config.json` (schema from spec, settings defaults; lower `min_views` to ~1,000 if most picked creators' medians are under 5,000); show it in plain words; `scout.py run --dry-run` → cost → ask → `scout.py run --force` → brief → offer weekly schedule (the `/schedule` skill or a cron line: `0 18 * * 0 cd ~ && <python> <base>/scripts/scout.py run ~/reel-scout/<name>`), optional.
5. **Run:** `status` → if `next_scrape` is "due now", `run --dry-run`, state cost, ask, then `run`; else `run` (news only, cents) after saying so → brief.
6. **Brief:** follow `references/brief.md`; save `~/reel-scout/<name>/briefs/YYYY-MM-DD.md`; after the user picks ideas, `mark-used` their codes/urls.
7. **Rules:** ask before every paid call with the estimate; never print/commit keys; ideas only from `topics.json` (reels, news, pool) — never invented trends; take topic/angle/format, never words/voice/footage/poems; short plain answers in the user's language; errors → show the script's message and the fix, don't retry paid calls automatically.

- [ ] **Step 2: Write `references/interview.md`** — questions in order, each with why and an example answer for a poet:
  1. What do you make? (topic + format: e.g. "Hindi shayari read over rain footage")
  2. Language(s) of your reels?
  3. Who watches / who do you want to reach? (age, place, taste)
  4. Your Instagram handle? (optional — lets the brief compare with your own style later)
  5. Creators you already watch or admire? (any number, handles or links)
  6. What do you want most: ideas to make · trends to ride · hooks/formats to learn?
  7. Short name for this scout (folder name, lowercase, e.g. `poetry`).
  Then: turning answers into 6–8 hashtags (mix 2 broad + 4 niche + 2 language-specific; check spelling variants like shayari/shayri) and 4–8 news queries (only if news matters to the niche — poetry: book launches, poet anniversaries, festivals, viral lines; skip for evergreen niches and say so). Keys explainer: Apify (required, apify.com → Settings → API & Integrations; free $5/month credit covers ~4 scrapes), ElevenLabs (optional, transcripts; speech-to-text minutes), Exa (optional, news; ~$0.01/search, free credit on signup).

- [ ] **Step 3: Write `references/brief.md`** — format:
```markdown
# <Scout name> — ideas for the week of <date>

1. **<Idea in one line, in the user's niche and language>**
   Why now: @creator's reel got <views> (<ratio>x their usual) — <what it did, 1 line>. <link>
   Hook to try: "<first line, written fresh>"
   Format: <length, style, what's on screen>
...(max 5; mix winners + news; no two ideas from the same source reel)

**What's working right now**
- <pattern across winners: format/length/hook type>
- <...>
- <...>

_Take the topic, angle or format. Never copy anyone's words, voice, footage or poems._
```
Rules: ideas only from unused `reels` (best ratio first), `news` and, when thin, `pool` reels with ratio ≥1.3; quote numbers exactly from `topics.json`; transcripts are for understanding the angle, never for lifting lines; if nothing new, say so and suggest the pool or waiting for the next scrape.

- [ ] **Step 4: Validate frontmatter** — `uv run python -c "import pathlib,sys; t=pathlib.Path('skills/reel-scout/SKILL.md').read_text(); assert t.startswith('---\nname: reel-scout\n'); print('ok')"`
- [ ] **Step 5: Commit** `git add -A && git commit -m "Skill: setup interview, run, weekly brief"`

---

### Task 5: README + install test + real run

**Files:** Create `README.md`

- [ ] **Step 1: Write `README.md`**: what it does (3 lines + example brief snippet) · install (`/plugin marketplace add <github-user>/reel-scout` then `/plugin install reel-scout@reel-scout`, or local path) · start (`/reel-scout`) · keys table (name, needed?, where, cost) · cost per run (~$0.30–1.00 on your own Apify account, setup scan ~$0.60) · privacy (data + keys only in `~/reel-scout/`, nothing sent anywhere else) · the rule · dev (`uv run pytest`).
- [ ] **Step 2: Full test suite** `uv run pytest -q` → all pass.
- [ ] **Step 3: Local install test** — `claude plugin validate .` (if available) and add the local marketplace: `/plugin marketplace add /Users/ritik/Expo/reel-scout`, `/plugin install reel-scout@reel-scout`; confirm the skill is listed. (User runs the slash commands; report what they see.)
- [ ] **Step 4: Real end-to-end (ASK the user first, ~$0.60 + ~$0.40)** — with the author's Apify key in `~/reel-scout/.env`, scout name `poetry-test`: discover with `shayari,hindipoetry,urdupoetry,poetrycommunity,hindishayari,rekhta` × 30, pick 12, run, write brief. Check numbers in the brief match `topics.json`.
- [ ] **Step 5: Commit** `git add -A && git commit -m "README"`; publishing to GitHub only when the user says so.
