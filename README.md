# Reel Scout

Your own Instagram scout, for any niche. Tell it what you make. It finds creators like you, spots the reels doing
far better than that creator's usual views, picks up this week's news, and gives you **5 ideas to make this week**.

```
1. Write a "letter to my younger self" shayari over old photos
   Why now: @somepoet's reel got 412,000 views (6.3x their usual) — a letter format, 25 s, text on screen.
   Hook to try: "Tujhe kya pata tha, ek din…"
```

A plugin for [Claude Code](https://claude.com/claude-code). You keep your own keys and your own data. Nothing is shared.

## Install

In Claude Code:

```
/plugin marketplace add Ritik1221/reel-scout
/plugin install reel-scout@reel-scout
```

Then say **"set up my reel scout"** (or type `/reel-scout:reel-scout`). It asks a few questions, helps you add your keys, finds
creators, and runs the first scout.

Every week after that, say **"run my scout"**.

## Keys

| Key | Needed? | What for | Get it |
|-----|---------|----------|--------|
| `APIFY_TOKEN` | Yes | Reads public reels | apify.com → Settings → API & Integrations |
| `ELEVENLABS_API_KEY` | No | Transcribes the winning reels | elevenlabs.io → API keys |
| `EXA_API_KEY` | No | This week's news in your niche | exa.ai → API keys |

You paste them into `~/reel-scout/.env` on your computer; they are never shown in the chat.

## Cost (on your own accounts)

- Setup: one hashtag scan (about $0.60) plus a check of up to 25 shortlisted creators (about $0.07).
- Each scrape: about $0.30–1.00 (capped at $1 by default), plus about $0.01 per transcribed reel. Creators are
  scraped every 2 weeks at most; news runs cost a few cents.
- Apify's free plan gives $5 credit a month, which is plenty.

It always tells you the cost and asks before spending. (If you turn on the optional weekly run, that run spends up to
the cap without asking.)

## Privacy

Everything stays in `~/reel-scout/` on your computer: your keys, the creators you watch, the results, your briefs.
Only Apify, ElevenLabs and Exa are called, with your own keys.

## The rule

Take the topic, angle or format. **Never copy anyone's words, voice, footage or poems.**

## For developers

```bash
uv run pytest                                          # tests, no network
uv run python skills/reel-scout/scripts/scout.py --help
uv run python skills/reel-scout/scripts/discover.py --help
```

How a reel scores: views ÷ that creator's median views over the last 90 days (kept between runs). A reel counts as a
winner at 1.5x or more with at least 5,000 views; both are settings in `config.json`.

MIT licence.
