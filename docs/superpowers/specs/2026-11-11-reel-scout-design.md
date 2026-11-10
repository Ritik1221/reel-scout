# Reel Scout — design

**Date:** 2026-11-11 · **Status:** draft for review

## Goal

A Claude Code skill anyone can install that sets up **their own** Instagram scout for **their own** niche
(Hindi poetry, a cooking channel, export tips…), then runs it: which reels in their niche are beating their
creator's usual views right now, what's new in the news, and 5 ideas to make this week.

Built from the Export Radar reels scout (`radar-reels/docs/promo/auto/scout.py`), but nothing of that setup is
shared: no creator list, no topics, no keys. Each user brings their own keys and keeps their data on their machine.

**Success:** a non-developer friend installs the plugin, types `/reel-scout`, answers a few questions, and gets a
working scout plus a first "5 ideas" brief in under 15 minutes for about $1 of their own API credit.

## Decisions (agreed 2026-11-11)

- Runs in **Claude Code** (needs Python + network + files). Not claude.ai.
- **Instagram only** for now (YouTube Shorts later if asked).
- Shared as a **public GitHub plugin** (`/plugin install`), separate repo `reel-scout`.
- Same engine as the original: score = views ÷ that creator's median views (kept across runs).

## Repo layout

```
reel-scout/
  .claude-plugin/plugin.json        plugin manifest
  .claude-plugin/marketplace.json   so `/plugin marketplace add <github-user>/reel-scout` works
  skills/reel-scout/
    SKILL.md                        when to use, setup interview, run steps, brief format, rules
    references/interview.md         the setup questions + how to turn answers into hashtags/news queries
    references/brief.md             how to write the weekly "5 ideas" brief
    scripts/scout.py                the engine (generic, config-driven, stdlib + requests)
    scripts/discover.py             hashtag scan → candidate creators
  tests/test_scout.py               scoring/history/pool tests on fixture data (no network)
  tests/fixtures/*.json             small fake Apify items
  README.md                         install, keys, cost, privacy
  LICENSE                           MIT
```

## User data (never in the repo)

```
~/reel-scout/
  .env                              APIFY_TOKEN (required), ELEVENLABS_API_KEY, EXA_API_KEY (optional)
  <scout-name>/                     one folder per scout, e.g. poetry/, channel/
    config.json
    topics.json                     cumulative output (same shape as the original: reels, news, views, pool)
    topics.raw.json                 last raw Apify scrape (re-rank for free with --raw)
    briefs/YYYY-MM-DD.md            the weekly brief Claude writes
```

Root can be changed with env `REEL_SCOUT_HOME`. Keys are also read from the process environment first.

### config.json

```json
{
  "name": "poetry",
  "about": "Hindi/Urdu poetry reels: shayari, spoken word, nazm recitations",
  "language": "Hindi",
  "audience": "18-30, India, likes romantic and sad shayari",
  "own_handle": "her_handle_or_null",
  "goal": "ideas | trends | hooks (free text)",
  "niches": {"main": ["creator1", "creator2"], "inspiration": ["bigaccount"]},
  "slots": {"main": 8, "inspiration": 2},
  "news_queries": ["new Hindi poetry book launch", "..."],
  "hashtags": ["hindipoetry", "shayari"],
  "settings": {"days": 14, "per": 12, "min_ratio": 1.5, "min_views": 5000, "per_creator": 3,
               "scrape_every_days": 13, "max_usd": 1.0}
}
```

Everything the original hardcoded (`MIN_RATIO`, `MIN_VIEWS`, `PER_CREATOR`, `SCRAPE_EVERY_DAYS`, `MAX_USD`,
the "rule" text, Drive path) becomes a setting or is dropped. `min_views` defaults lower (5,000) because small
niches have smaller creators; the interview can tune it.

## Engine — `scripts/scout.py`

Same behaviour as the original, minus Google Drive:

```
python scout.py run <scout-dir> [--force] [--raw FILE] [--no-transcribe] [--no-news] [--dry-run]
python scout.py status <scout-dir>          last scrape, next due date, counts, unused topics
python scout.py mark-used <scout-dir> CODE|URL ...
```

1. **Scrape** (Apify `apify~instagram-reel-scraper`) only when due (`scrape_every_days`) or `--force`;
   hard cost cap `max_usd` passed to Apify (`maxTotalChargeUsd`, `maxItems`). Saves raw items.
2. **Remember** views per creator (90 days) → **rank**: ratio = views ÷ median (stored history if ≥5 reels,
   else this run). Keep `per_creator` best per creator above `min_ratio` and `min_views`; then `slots` per niche.
3. **Transcribe** new winners with ElevenLabs Scribe if a key exists (else caption only; failure keeps the topic).
4. **News** via Exa (last 8 days) if a key exists and `news_queries` is set.
5. **Write** `topics.json` (winners 120 days, news 30 days, view history, slim pool of every scraped reel).
6. Print a short summary + total spend. `--dry-run` prints the plan and estimated cost without calling anything paid.

Missing optional key → that step is skipped with one plain line, never an error. Missing Apify key → clear
message pointing to the README. Any API failure → stop with the status code and message; no silent retries.

## Discovery — `scripts/discover.py`

```
python discover.py <scout-dir> --hashtags shayari,hindipoetry,... [--per 40] [--max-usd 0.5]
```

Apify `apify~instagram-hashtag-scraper` (reels per hashtag) → group by owner → list accounts with reel count,
median views, best reel, last post date, sample captions. Writes `candidates.json` in the scout folder. Claude
shows the top ~25 as a table; the user picks. Cost ≈ $0.60 for 8 hashtags × 40 reels (measured 2026-11-10: $0.62).

## The skill — `SKILL.md` flow

**Trigger:** "/reel-scout", "set up a scout", "find trending reels in my niche", "what should I post", "run my scout".

**A. First time (no `~/reel-scout/<name>/config.json`):**
1. Check Python ≥3.10 and `requests`; offer `pip install requests` if missing.
2. Interview, one question at a time (references/interview.md): what you make · language(s) · who watches ·
   your handle (optional) · creators you already admire (optional) · what you want (ideas / trends / hooks) ·
   short name for this scout.
3. Keys: explain each (what it does, where to get it, free tier/cost); write them to `~/reel-scout/.env`.
   Only Apify is required.
4. Propose 6–8 hashtags + 4–8 news queries from the answers; user edits.
5. **Ask before spending**, then run `discover.py`; show candidates; user picks 10–20 (+ their own list).
   Big general accounts they like for style can go in an `inspiration` niche.
6. Write `config.json`, show it in plain words, run `scout.py run --dry-run`, then (after asking) the first run.
7. Write the first brief.
8. Offer a weekly schedule (Claude Code `/schedule` or a cron line) — optional.

**B. Later runs:** `scout.py status` → if a scrape is due, say the cost and ask → `scout.py run` → brief.
Several scouts per user: ask which one if more than one exists.

**C. Brief (references/brief.md)** saved to `briefs/YYYY-MM-DD.md` and shown in chat:
- 5 ideas max, each: one-line idea in the user's niche and language · why now (which reel beat its creator's
  usual by how much, or which news item) · a hook line to try · link to the source reel.
- Then "what's working" in 3 bullets (formats, lengths, hooks seen across winners).
- Ideas must come from `topics.json` (winners, news, pool); no made-up trends. Mark used ones with `mark-used`.

**Rules written into the skill:**
- Take the topic, angle or format — **never** copy anyone's words, voice, footage or poems. Say so in every brief.
- Ask before every paid call; state the estimated cost.
- Never print or commit keys. Never write user data inside the plugin folder.
- Short, plain answers; the user may not be technical.

## Testing

- `tests/test_scout.py` (pytest, no network): `remember` drops old history; `rank` uses stored median when ≥5,
  respects `min_ratio`/`min_views`/`per_creator`; slots per niche; already-seen reels skipped; pool built;
  config defaults applied; missing optional keys skip steps; `discover` grouping on fixture hashtag items.
- One real end-to-end run on a poetry niche with the author's Apify key (~$0.50, asked first).
- Install test: `/plugin marketplace add` from the local path, then run `/reel-scout` in a clean folder.

## Out of scope (for now)

YouTube/TikTok, Google Drive upload, hosted/web version, auto-posting, comment-to-DM, multi-language UI,
sharing scouts between users.
