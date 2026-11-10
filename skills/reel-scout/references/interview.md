# Setup interview

Ask one question at a time. Accept short answers; offer the example if they're stuck.

| # | Question | Why | Example (a poet) |
|---|----------|-----|------------------|
| 1 | What do you make? Topic and format. | Picks hashtags and the kind of creators to watch | "Hindi shayari, read in my voice over rain or city footage" |
| 2 | Which language(s) are your reels in? | Language-specific hashtags; the brief is written in it | "Hindi, some Urdu" |
| 3 | Who watches, or who do you want to reach? | Tells which ideas fit | "18–30, India, likes sad and romantic shayari" |
| 4 | Your Instagram handle? (optional) | Lets later briefs compare with your own style | "@her_handle" |
| 5 | Creators you already watch or admire? (any number, handles or links) | Seeds the creator list | "@rekhta, @poetrybykunal" |
| 6 | What do you want most: ideas to make, trends to ride, or hooks and formats to learn? | Sets the brief's focus | "ideas" |
| 7 | A short name for this scout (lowercase, one word) | Folder name | `poetry` |

## Answers → hashtags (6–8)

- 2 broad tags for the field (`poetry`, `hindipoetry`), 4 niche tags (`shayari`, `sadshayari`, `urdupoetry`,
  `spokenwordpoetry`), 2 language/region tags (`hindishayari`, `rekhta`).
- Include common spelling variants (`shayari` / `shayri`); drop tags so huge they're mostly spam (`love`, `reels`).
- Show the list; the user edits it.

## Answers → news searches (0–8)

Only when news matters to the niche. Poetry: book launches, poet anniversaries, literature festivals, a line that
went viral, award news. Cooking: festival dishes, viral food trends. Evergreen niches (e.g. meditation) may need
none — say so and leave `news_queries` empty. Write each as a plain search sentence
("Hindi poetry book launch this week", "Urdu poet anniversary").

## Keys

| Key | Needed? | What it does | Where | Cost |
|-----|---------|--------------|-------|------|
| `APIFY_TOKEN` | Yes | Reads public reels | apify.com → sign up → Settings → API & Integrations → copy the personal token | Free plan gives $5 credit a month; a scrape is ~$0.40, setup ~$0.70 (hashtag scan + creator check) |
| `ELEVENLABS_API_KEY` | No | Transcribes the winning reels so the brief knows what was said | elevenlabs.io → profile → API keys | Speech-to-text minutes; free tier covers a few runs |
| `EXA_API_KEY` | No | Finds this week's news for the niche | exa.ai → dashboard → API keys | ~$0.01 a search; free credit on sign-up |

Without ElevenLabs the brief works from captions only. Without Exa there's no news section.
