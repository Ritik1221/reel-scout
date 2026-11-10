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
- Run Python as `uv run --with requests python <script> ...` when `uv` exists; otherwise `python3 <script> ...`
  after checking `python3 -c "import requests"` (if missing, offer `python3 -m pip install --user requests`).
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
   required. Write them to `~/reel-scout/.env` as `NAME=value` lines, then `chmod 600 ~/reel-scout/.env`.
   Never echo a key back or put it in a command line. Check Apify with a free call that reads the token from the file:
   `set -a; . ~/reel-scout/.env; set +a; curl -s "https://api.apify.com/v2/users/me?token=$APIFY_TOKEN"` and report
   only the username and plan (or that the token was refused).
3. **Hashtags + news** — propose 6–8 hashtags and 0–8 news searches from the answers (see interview.md). Let the
   user edit.
4. **Find creators** — `PY <base>/scripts/discover.py ~/reel-scout/<name> --hashtags a,b,c --dry-run` → tell the user the
   cost → **ask** → run it without `--dry-run`. Show the top 25 from the output as a table (handle, reels found,
   median views, best, last post, what it's about) and let the user pick 10–20. Add the creators they named in the
   interview. Big general accounts they like only for style can go in a separate `inspiration` niche.
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
6. **First run** — `PY <base>/scripts/scout.py run ~/reel-scout/<name> --dry-run` → say the estimated cost → **ask** →
   `PY <base>/scripts/scout.py run ~/reel-scout/<name> --force`.
7. **Brief** — write it (below).
8. **Optional weekly run** — offer it once. Claude Code's `/schedule` skill, or a cron line such as
   `0 18 * * 0 <PY> <base>/scripts/scout.py run ~/reel-scout/<name>` (the scrape only happens when it's due).

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
