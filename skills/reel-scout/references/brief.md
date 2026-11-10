# Weekly brief

Read `~/reel-scout/<name>/topics.json` and `config.json` (about, language, audience, goal). Write the brief in the
language the user chats in; write the hooks in the language of their reels (`language` in config). Keep it short.

## Format

```markdown
# <Scout name> — ideas for the week of <date>

1. **<The idea in one line, in the user's niche and voice>**
   Why now: @creator's reel got <views> views (<ratio>x their usual) — <what it did, one line>. <reel link>
   Hook to try: "<a first line written fresh for the user>"
   Format: <length, style, what's on screen>

2. ...   (up to 5)

**What's working right now**
- <a pattern across the winners: format, length, hook type, topic>
- <...>
- <...>

_Take the topic, angle or format. Never copy anyone's words, voice, footage or poems._
```

For a news-based idea, "Why now" names the news item, its date and link instead of a reel.

## Where ideas come from

1. Unused `reels` (`used: false`), best `ratio` first. Mix the niches; at most one idea per source reel.
   **Skip winners that are off the user's niche** (compare with `about` in config.json) — a general business creator's
   viral reel about engine oil is not an idea for an export channel. Say in one line how many you skipped.
   A winner with no transcript and an empty caption can't be judged: skip it too.
   Rank solid winners first. Two flags lower a winner, and the brief must say so in "Why now":
   - `fragile: true` — the creator's usual views are tiny (`median`), so a big ratio is one lucky hit, not a trend.
   - `from_discovery: true` — the setup scan already found this reel (it's why the creator was picked), so it isn't
     new this week. Fine to use on the first brief; say it's a proven past hit.
2. Unused `news` that fits the niche and audience.
3. If that's thin, `pool` reels with `ratio` ≥ 1.3 and on the niche (say they're smaller signals; `median` is the creator's usual).
4. If there's nothing new, say so plainly and when the next scrape is due. Don't pad.

## Checks before showing it

- Every number (views, ratio, dates) matches `topics.json` exactly.
- Every idea has a link to its source.
- No line is lifted from a transcript or caption — hooks are new writing.
- The goal from config shapes the focus: `ideas` → concrete posts; `trends` → what's rising and why; `hooks` → the
  opening lines and formats that worked, rewritten as patterns.
