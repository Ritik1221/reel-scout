---
name: reel-scout
description: Set up and run your own Instagram reel scout for any niche (poetry, cooking, fitness, business...). Use when someone says "set up a scout", "/reel-scout:reel-scout", "find what's working in my niche", "what should I post this week", "run my scout", or wants trending reel ideas from creators like them. Interviews the user, finds creators to watch, scores reels against each creator's usual views, and writes a weekly 5-idea brief.
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

1. **Interview** — follow `references/interview.md`, one question at a time, in the language the user chats in. Keep
   it friendly and short; the user may not be technical. Then create the scout folder: `mkdir -p ~/reel-scout/<name>`.
2. **Keys** — explain each key in one line (what it does, where to get it, cost; see interview.md). Only Apify is
   required. If `~/reel-scout/.env` doesn't exist, create it with empty lines (`APIFY_TOKEN=`, `ELEVENLABS_API_KEY=`,
   `EXA_API_KEY=`) and `chmod 600` it. Then ask the user to open that file and paste each key after its `=`
   themselves (e.g. `open -e ~/reel-scout/.env` on macOS, `notepad` on Windows). If they paste a key into the chat
   instead, put it in with an Edit of that one line — never with `echo`, a heredoc or any command line, and never
   repeat it back. Keep keys already in the file. Then check: `PY <base>/scripts/scout.py check-keys` (free; never
   prints a key). Apify is checked live; ElevenLabs and Exa show "set" and are checked on first use — the run
   reports if they fail.
3. **Hashtags + news** — propose 6–8 hashtags and 0–8 news searches from the answers (see interview.md). Let the
   user edit.
4. **Find creators** — two paid steps, each with a dry-run first, the cost said, and the user's OK:
   a. **Scan hashtags:** `PY <base>/scripts/discover.py ~/reel-scout/<name> --hashtags a,b,c --dry-run`, then without
      `--dry-run`. Keep the default 40 reels per hashtag: fewer and almost every account shows up only once.
      Read `candidates.json`, drop accounts clearly off the niche or in another language (judge from `sample` and
      `hashtags`), and shortlist up to 25 (the views shown are of the hashtag reels found, not the creator's usual).
      Add the creators the user named in the interview.
   b. **Check the shortlist:** `PY <base>/scripts/discover.py ~/reel-scout/<name> --check h1,h2,... --dry-run` (about
      $0.07 for 25), then without `--dry-run`. It shows followers, posts in the last 14 days, usual likes and flags:
      `QUIET` (under 3 posts in 14 days — the scout can't score them) and `REPOST?` (bio suggests reposted content).
   Show the user one table (handle, followers, posts/14d, usual likes, flags, what it's about) and let them pick
   10–20. Leave out QUIET and private accounts and, unless the user wants them, REPOST? pages. Big general accounts
   they like only for style can go in a separate `inspiration` niche.
5. **Write `~/reel-scout/<name>/config.json`:**
   ```json
   {
     "name": "<name>", "about": "<what they make>", "language": "<language>", "audience": "<who watches>",
     "own_handle": "<handle or null>", "goal": "<ideas / trends / hooks>",
     "niches": {"main": ["handle1", "handle2"], "inspiration": []},
     "slots": {"main": 8, "inspiration": 2},
     "news_queries": ["..."], "hashtags": ["..."],
     "settings": {"days": 14, "per": 12, "min_ratio": 1.5, "min_views": 5000, "per_creator": 3,
                  "scrape_every_days": 13, "max_usd": 1.0, "min_usual_views": 1000}
   }
   ```
   Leave out an empty niche. If most picked creators have under ~20,000 followers or usual likes under ~300 (from
   `profiles.json`), set `min_views` to about 1,000 (small niches have small creators). `min_usual_views`: winners from creators whose
   usual views are below it are marked `fragile` (one lucky hit, not a trend). Explain the config to the user in plain words, not as JSON.
6. **First run** — `PY <base>/scripts/scout.py run ~/reel-scout/<name> --dry-run` → say the estimated cost (scrape,
   transcripts, news) → **ask** → `PY <base>/scripts/scout.py run ~/reel-scout/<name> --force`. Keep transcripts on if
   the budget allows: without them, winners whose caption says nothing ("Follow for more") can't be used. To save
   money, add `--no-transcribe` and say what that costs in quality. The run prints what it actually spent, transcripts
   included; if transcripts failed (bad key), say so and point to the key.
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
