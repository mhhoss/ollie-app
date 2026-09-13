# Ollie

A Telegram storefront bot for Iranian businesses with a fixed catalog
— products or services the customer already knows they want. Order
placement, a pro-forma invoice with a uniquely-tagged payment amount,
receipt-photo verification with one-tap owner approval, and instant
delivery for digital goods or a pushed tracking number for physical
ones.

Sold as a one-time build + deploy, hosted on a client's own low-cost
VPS — not a subscription SaaS. Each business runs its own bot on its
own bot token; Ollie is the codebase and deployment image, not a
shared multi-tenant service (that's a possible later milestone, not
the current one).

## Status

Pre-implementation. `docs/m1-spec.html` is the complete build
specification for the first milestone — every customer and owner
screen with final Persian copy, the order state machine, and the
SQLite schema. `docs/roadmap.md` is the phased implementation plan
this repo is being built against.

This repo previously held the dataset foundation for a different,
earlier "Ollie" concept (a retrieval-based Telegram customer
assistant). That work is preserved at git tag `assistant-prototype`
if it's ever needed again; it isn't part of this product.

## Development

```bash
uv sync --all-groups
uv run pytest -q
uv run ruff check .
uv run mypy src
```

See `docs/roadmap.md` for the phase-by-phase build plan.

## Repo layout (target shape, filling in phase by phase)

```
src/ollie/
  config.py       — load + validate config.toml
  domain/         — state machine, models, order codes, money — stdlib only
  fmt/            — Jalali dates, Persian digits, Toman formatting
  db/             — schema, migrations, repositories (SQLite)
  bot/            — aiogram handlers, keyboards, copy_fa.py

tools/channel_scraper/  — standalone lead-gen / demo-content scraper,
                           not part of the ollie package
docs/                    — m1-spec.html, roadmap.md
```
