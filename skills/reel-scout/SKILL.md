---
name: reel-scout
description: Set up and run your own Instagram reel scout for any niche (poetry, cooking, fitness, business...). Use when someone says "set up a scout", "/reel-scout", "find what's working in my niche", "what should I post this week", "run my scout", or wants trending reel ideas from creators like them. Interviews the user, finds creators to watch, scores reels against each creator's usual views, and writes a weekly 5-idea brief.
---

# Reel Scout

Watches the creators in someone's niche, finds the reels doing much better than that creator's usual views,
picks up fresh news, and turns it into 5 ideas for the week. Each person sets up their **own** scout with their
**own** keys; nothing is shared.

The rule, repeated in every brief: **Take the topic, angle or format. Never copy anyone's words, voice, footage or poems.**

## Paths

- Scripts live in this skill's base directory: `<base>/scripts/scout.py` and `<base>/scripts/discover.py`.
- User data lives in `~/reel-scout/` (or `$REEL_SCOUT_HOME`): `.env` for keys, one folder per scout
  (`~/reel-scout/<name>/config.json`, `topics.json`, `candidates.json`, `briefs/`).
  **Never write user data inside the skill folder.**
- Run Python as `uv run --no-project --with requests python <script> ...` when `uv` exists (`--no-project` keeps uv
  away from any project in the current folder); otherwise `python3 <script> ...` after checking
  `python3 -c "import requests"` (if missing, offer `python3 -m pip install --user requests`).
  Below, `PY` means whichever of the two works.

## Pick the mode

List `~/reel-scout/*/config.json`.
- None → **Setup**.
- One → **Run** (unless the user asks for a new scout).
- Several → ask which one, or "a new one".

## Setup (first time)

1. **Interview** — follow `references/interview.md`, one question at a time, in the user's language. Keep it friendly
   and short; the user may not be technical.
2. **Keys** — explain each key in one line (what it does, where to get it, cost; see interview.md). Only Apify is
   required. If `~/reel-scout/.env` doesn't exist, create it with empty lines (`APIFY_TOKEN=`, `ELEVENLABS_API_KEY=`,
   `EXA_API_KEY=`) and `chmod 600` it. Then ask the user to open that file and paste each key after its `=`
   themselves (e.g. `open -e ~/reel-scout/.env` on macOS, `notepad` on Windows). If they paste a key into the chat
   instead, put it in with an Edit of that one line — never with `echo`, a heredoc or any command line, and never
   repeat it back. Keep keys already in the file. Then check: `PY <base>/scripts/scout.py check-keys` (free; prints
   only ok / missing / refused and the Apify username, never a key).
3. **Hashtags + news** — propose 6–8 hashtags and 0–8 news searches from the answers (see interview.md). Let the
   user edit.
4. **Find creators** — `PY <base>/scripts/discover.py ~/reel-scout/<name> --hashtags a,b,c --dry-run` → tell the user the
   cost → **ask** → run it without `--dry-run`. Read `candidates.json` and first drop accounts that are clearly off
   the niche or in another language (judge from `sample` and `hashtags`). Show the rest as a table (handle, tag reels
   found, best views, last post, what it's about in a few words) and let the user pick 10–20. Say plainly: the views
   are of the hashtag reels found, not the creator's usual views; an account found only once may be a one-off hit,
   so prefer accounts found 2+ times, and creators who post at least weekly (a creator needs 3+ reels before the
   scout knows their usual views). Add the creators they named in the interview. Big general accounts they like only
   for style can go in a separate `inspiration` niche.
5. **Write `~/reel-scout/<name>/config.json`:**
   ```json
   {
     "name": "<name>", "about": "<what they make>", "language": "<language>", "audience": "<who watches>",
     "own_handle": "<handle or null>", "goal": "<ideas / trends / hooks>",
     "niches": {"main": ["handle1", "handle2"], "inspiration": []},
     "slots": {"main": 8, "inspiration": 2},
     "news_queries": ["..."], "hashtags": ["..."],
     "settings": {"days": 14, "per": 12, "min_ratio": 1.5, "min_views": 5000, "per_creator": 3,
                  "scrape_every_days": 13, "max_usd": 1.0}
   }
   ```
   Leave out an empty niche. If most picked creators have a median under 5,000 views, set `min_views` to about
   1,000 (small niches have small creators). Explain the config to the user in plain words, not as JSON.
6. **First run** — `PY <base>/scripts/scout.py run ~/reel-scout/<name> --dry-run` → say the estimated cost (scrape,
   transcripts, news) → **ask** → `PY <base>/scripts/scout.py run ~/reel-scout/<name> --force`. Keep transcripts on if
   the budget allows: without them, winners whose caption says nothing ("Follow for more") can't be used. To save
   money, add `--no-transcribe` and say what that costs in quality.
   If the run lists creators with too few reels, tell the user and offer to swap them at the next setup.
7. **Brief** — write it (below).
8. **Optional weekly run** — offer it once, and say plainly that a scheduled run spends up to `max_usd` without
   asking (the only exception to "ask before spending"). macOS/Linux cron line — use absolute paths, cron has no
   PATH: `0 18 * * 0 <abs path from command -v uv> run --no-project --with requests python <base>/scripts/scout.py run
   ~/reel-scout/<name> >> ~/reel-scout/<name>/cron.log 2>&1` (or `<abs python3> <base>/scripts/scout.py ...`).
   Briefs are still written by Claude the next time the user says "run my scout" (it then sees the new data).

## Run (every week)

1. `PY <base>/scripts/scout.py status ~/reel-scout/<name>`.
2. If `next_scrape` is `due now`: `run --dry-run`, say the cost, **ask**, then `run`. If it isn't due, say so and
   `run` anyway (news only, a few cents; skip if there's no Exa key).
3. Write the brief.

If a script stops with a message (missing key, Apify refused, bad config), show the message and the fix in plain
words. Do not retry a paid call on your own.

## Brief

Follow `references/brief.md`. Save it to `~/reel-scout/<name>/briefs/YYYY-MM-DD.md` and show it in chat.
When the user picks ideas to make, run `PY <base>/scripts/scout.py mark-used ~/reel-scout/<name> CODE_OR_URL ...`
so they don't come back next week.

## Rules

- **Ask before every paid call**, with the estimated cost from `--dry-run`.
- Never print, log or commit keys.
- Ideas come only from `topics.json` (`reels`, `news`, `pool`). Never invent trends or numbers; quote numbers exactly.
- Take the topic, angle or format. Never copy anyone's words, voice, footage or poems. Transcripts are for
  understanding the angle, not for lifting lines.
- Short, plain answers in the user's language.
