# Channel scraper

A standalone lead-gen and demo-content tool. Not part of the `ollie`
package, not imported by it, and excluded from its build, lint, and
type-check config — this is a side script, not product code.

## Why it exists

Ollie (the M1 storefront bot) targets businesses with a fixed catalog
who are already Telegram-native. Public Telegram channel posts from
wholesale/retail sellers routinely carry exactly the fields needed to
qualify and contact a lead: shop name, manager name, address, phone
number, product line. This script turns a channel into that list.

Second use: `posts.jsonl` is a source of real Persian product copy —
useful for seeding a realistic demo store instead of writing placeholder
text by hand.

## What it does

Fetches `https://t.me/s/<channel>` — Telegram's public, unauthenticated
channel preview (no API credentials needed, the same surface search
engines index) — and parses posts into `Post` records (id, channel,
message_id, permalink, text, collected_at, posted_at).

Known limitation: this only reaches channel *posts*, not comments in a
linked discussion group (that surface isn't exposed publicly and would
need real Telegram API credentials). Irrelevant to this tool's current
purpose.

## Usage

```bash
# Scrape a channel (appends new posts, skips ones already on file)
python tools/channel_scraper/telegram_channel.py <channel>

# Paginate further back in history
python tools/channel_scraper/telegram_channel.py <channel> --before <message_id>

# Fetch and parse without writing anything
python tools/channel_scraper/telegram_channel.py <channel> --dry-run
```

No dependencies beyond the standard library — run with any Python 3.12,
inside or outside the project's venv.

## Already collected

`posts.jsonl` currently holds 49 real posts from three public Iranian
wholesale channels, scraped 2026-09-09:

| Channel | Posts |
|---|---|
| `Sanatekafshirann` | 9 |
| `shoespourreza` | 20 |
| `omdehiran` | 20 |

These are real posts from real public channels — treat contact details
found in them accordingly (this is a personal lead list, not something
to publish or bulk-contact from).
