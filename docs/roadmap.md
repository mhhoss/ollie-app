# Ollie — Development Roadmap

Reference document for the rebuild from the assistant-prototype dataset
layer to the M1 Telegram storefront. Phases are sequential; each has a
checkpoint that must pass before the next begins. This file is the
permanent record of the plan — update it if the plan changes, don't let
it drift out of sync with what actually happened.

Companion document: `docs/m1-spec.html` — the screen-by-screen Persian
copy, state machine, and data model this roadmap builds against.

Defaults locked in for this rebuild:
- Scraper salvage lives in-repo at `tools/channel_scraper/`.
- Repo directory stays `ollie-app`, package stays `ollie`.

---

## Phase 0 — Baseline and safety

Nothing is deletable until there's a commit to go back to. The repo
currently has zero commits — everything staged, nothing recorded.

**Actions**
- `git add -A` (picks up untracked `assets/`, `docs/`)
- Commit as the assistant-prototype baseline
- `git tag assistant-prototype`
- `rm -rf .venv && uv sync --all-groups` — fixes stale `ollie-bot` shebangs
  left over from a directory rename

**Checkpoint**
- `git log --oneline` shows one commit
- `git status` clean
- `uv run pytest -q` → 46 passed (fails today only due to the stale venv;
  if it still fails after the rebuild, stop — the environment is wrong
  and every later checkpoint is unreliable)

---

## Phase 1 — Salvage the scraper

The channel importer is dead weight for the bot but a working lead-gen
tool: it turns public Telegram shop channels into structured records,
which is exactly the M1 target segment (fixed-catalog sellers already
on Telegram). Move it out before the dataset layer is deleted.

**Create**
- `tools/channel_scraper/telegram_channel.py` — moved from
  `src/ollie/dataset/importers/`, with its three `ollie.dataset.models`
  imports replaced by a local ~20-line `Post` dataclass (channel,
  message_id, permalink, text, posted_at). Loses nothing — the
  `Document` contract existed for the corpus; lead-gen doesn't need it.
- `tools/channel_scraper/posts.jsonl` — from `data/documents.jsonl`,
  the 49 already-scraped posts (also useful as realistic demo content).
- `tools/channel_scraper/README.md` — what it's for now: lead list of
  Telegram-native Iranian shops with fixed catalogs, plus demo-content
  seeding. Lists the three channels already scraped and the re-run
  command.

**Modify**
- `pyproject.toml` — exclude `tools/` from
  `[tool.hatch.build.targets.wheel].packages` and from mypy/ruff, so a
  lead-gen script never gates the product build.

**Checkpoint**
- `python tools/channel_scraper/telegram_channel.py omdehiran --dry-run`
  fetches and parses without importing anything from `ollie`

---

## Phase 2 — Demolition

**Delete**
- `src/ollie/dataset/` (entire)
- `tests/dataset/` (entire)
- `scripts/`
- `data/`

**Rewrite**
- `README.md` — the storefront product, one-time/client-hosted model,
  pointer to `docs/m1-spec.html`, dev commands. Keep it short.

**Checkpoint**
- `grep -ri "dataset\|corpus\|retrieval\|lode\|query" src/ tests/ README.md`
  returns nothing
- `uv run pytest -q` → no tests collected (pytest exit code 5 for this case — expected, not a failure)
- Commit as a separate "remove assistant prototype" commit so the
  deletion is one reviewable diff

**⏸ Stop here for review before continuing to Phase 3.**

---

## Phase 3 — Project configuration

**Modify `pyproject.toml`**
- `description` → the storefront
- `dependencies = ["aiogram>=3.15"]` — the entire runtime dependency
  list; SQLite, tomllib, hashlib are stdlib
- dev group adds `pytest-asyncio`
- ruff/mypy stay strict; add `exclude = ["tools"]`

**Modify `.gitignore`**
- Remove `uv.lock` (an application wants a committed lock, unlike a library)
- Add `*.db`, `*.db-wal`, `*.db-shm`, `config.toml`, `receipts/`

**Create `config.example.toml`**
```toml
[bot]
token = "..."
owner_telegram_id = 0

[store]
name = "..."
card_number = "6037997512345678"
card_holder = "..."
shipping_cost = 0
default_carrier = "پست پیشتاز"

[order]
payment_window_hours = 24
reject_flag_threshold = 3

[runtime]
db_path = "data/ollie.db"
proxy_url = ""   # for Iranian hosts that can't reach api.telegram.org directly
```

**Create `src/ollie/config.py`**
- `tomllib` load into a frozen `Config` dataclass
- Validates at startup: token non-empty, `owner_telegram_id > 0`, card
  number 16 digits, `payment_window_hours` in 1–168
- A bad config fails on boot with a readable message, never at the
  first order

**Checkpoint**
- `uv run python -c "from ollie.config import load; load('config.example.toml')"`
  raises a clear error naming the placeholder token — proving
  validation actually fires

---

## Phase 4 — Domain layer

Stdlib only. No aiogram, no sqlite import. Must be fully unit-testable
with no Telegram and no database in the loop — this is the layer that
carries over the dataset code's discipline (self-validating frozen
dataclasses, deterministic ids, two-tier validation, honest provenance).

**Create**
- `src/ollie/domain/states.py` — `OrderState(StrEnum)` with the eight
  states; `ALLOWED: frozenset[tuple[OrderState, OrderState]]`
  transcribed from the spec's transition table; `TERMINAL: frozenset`;
  `check_transition(frm, to) -> None` raising `IllegalTransition`. The
  transition table lives here and nowhere else.
- `src/ollie/domain/models.py` — frozen, slotted, self-validating
  dataclasses: `Product`, `Variant`, `Credential`, `Customer`, `Order`,
  `OrderItem`, `Receipt`. `Order.__post_init__` asserts
  `payable_amount == subtotal + shipping_cost + amount_tail`,
  `100 <= amount_tail <= 999`, and `expires_at is None` exactly when
  state is `receipt_submitted`.
- `src/ollie/domain/codes.py` — `ALPHABET =
  "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"` (no `0/O/I/1`),
  `generate_code()`, `is_valid_code()`.
- `src/ollie/domain/money.py` — Toman is `int`, always. `amount_tail()`,
  `payable()`. No floats admitted anywhere in the module.
- `src/ollie/domain/validate.py` — cross-record invariants a single
  object can't see: orphaned reservations, credentials `reserved`
  against a terminal order, two open orders sharing a
  `payable_amount`, orders in `awaiting_receipt` with a null
  `expires_at`. Runs as a CLI like the old validator, and inside the
  sweeper (Phase 7).
- `src/ollie/domain/errors.py` — `IllegalTransition`,
  `InsufficientStock`, `DuplicateReceipt`, `AmountCollision`.
- `src/ollie/fmt/digits.py` — ASCII↔Persian digit conversion, plus the
  input normaliser (Persian/Arabic digits → ASCII, strip ZWNJ/spaces/
  dashes, Arabic ي/ك → Persian ی/ک).
- `src/ollie/fmt/jalali.py` — Gregorian↔Jalali conversion (~40 lines,
  standard algorithm), tested against real vectors: Nowruz boundaries,
  both leap kinds, and today (`2026-09-13` → `۱۴۰۵/۰۶/۲۲`). If any
  vector fails, swap in `persiantools` instead of debugging date math.
- `src/ollie/fmt/money.py` — `toman(1450347)` →
  `"۱٬۴۵۰٬۳۴۷ تومان"`.

**Tests**
- `tests/domain/test_states.py`, `test_models.py`, `test_codes.py`
- `tests/fmt/test_jalali.py`, `test_digits.py`, `test_money.py`

**Checkpoint (the important one)**
- A test walks **every** path through the state machine end to end
  using only domain objects — happy digital, happy physical,
  reject→retry→approve, expiry, cancel — and asserts every transition
  *not* in `ALLOWED` raises
- `ALPHABET` contains no `0`, `O`, `I`, or `1`
- mypy strict clean

Getting this green before any Telegram code exists is what keeps the
bot layer thin.

---

## Phase 5 — Persistence

**Create**
- `src/ollie/db/schema.sql` — DDL from the spec, plus indexes:
  `order(state, expires_at)`, `order(customer_id, created_at)`,
  `receipt(image_hash)`, `credential(product_id, status)`. A `UNIQUE`
  constraint on `payable_amount` scoped to open orders, enforced by a
  partial unique index — not by application logic that races.
- `src/ollie/db/conn.py` — connection factory: `journal_mode=WAL`,
  `foreign_keys=ON`, `busy_timeout`, `row_factory`.
- `src/ollie/db/migrate.py` — versioned on `PRAGMA user_version`,
  applied at boot. Needed from day one: clients will be on different
  versions and a forgotten migration corrupts a store.
- `src/ollie/db/repo/{products,customers,orders,credentials,receipts,events}.py`
  — plain functions taking a connection. No ORM.

**The three functions that must be single transactions, with their own tests:**
1. `orders.create()` — insert order + items, reserve stock and
   credentials, allocate a non-colliding `payable_amount`, log the
   event. All or nothing.
2. `orders.transition()` — re-read state, `check_transition`, update,
   write `event_log`, in one transaction. This is the idempotency
   point for duplicate Telegram callbacks.
3. `credentials.deliver()` — mark delivered **only** after the caller
   confirms the send succeeded; takes a callback so the Telegram call
   happens inside the transaction's success path.

**Checkpoint**
- Integration tests against a temp DB file:
  - Concurrent `create()` never issues the same `payable_amount`
  - Double `transition()` from the same source state leaves exactly
    one `event_log` row
  - A failed delivery callback rolls back and leaves the credential
    `reserved`

---

## Phase 6 — `src/ollie/bot/copy_fa.py`

One module, every Persian string, no exceptions.

**Rules (as module docstring)**
1. No Persian literal exists anywhere else in `src/`. Enforced by
   `tests/test_copy_isolation.py`.
2. Constants are named for their spec screen: `C9_INVOICE`,
   `O1_NEW_RECEIPT`, `E1_USE_BUTTONS`. `docs/m1-spec.html` is the
   source of truth for the text.
3. Templates use `str.format` with named fields only — never
   positional, never f-strings, so a caller can't silently reorder them.
4. No number or date formatting happens here. Callers pass strings
   already rendered by `ollie.fmt`.

**Structure**
```python
# ── 1. Fragments ──────────────────────────────────────────────
# Reused clauses: ORDER_CODE_LINE, DATE_LINE, DIVIDER

# ── 2. BTN ────────────────────────────────────────────────────
# Button labels, one flat namespace, prefixed by screen:
#   BTN_PRODUCTS, BTN_MY_ORDERS, BTN_SUPPORT, BTN_ADD_TO_CART,
#   BTN_CHECKOUT, BTN_SEND_RECEIPT, BTN_CANCEL_ORDER,
#   BTN_APPROVE, BTN_REJECT, BTN_MSG_CUSTOMER, BTN_BACK, ...

# ── 3. Customer screens C1–C15 ────────────────────────────────
# ── 4. Owner screens O1–O6 ────────────────────────────────────
# ── 5. Errors E1–E9 ───────────────────────────────────────────

# ── 6. REJECT_REASONS ─────────────────────────────────────────
# tuple of (key, owner_button_label, customer_sentence) — the owner's
# terse chip and the customer's polite sentence are different strings
# and must never be reused for each other.

# ── 7. STATUS_LABELS ──────────────────────────────────────────
# dict[OrderState, str] — the six customer-facing status labels.
```

**Tests**
- `tests/test_copy_fa.py` — every public constant is non-empty; every
  template renders with sample kwargs; no template contains an ASCII
  digit outside a `{placeholder}` (catches a Latin numeral leaking
  into Persian text); every `OrderState` has a `STATUS_LABELS` entry.
- `tests/test_copy_isolation.py` — regex-scans `src/ollie/**/*.py`
  excluding `copy_fa.py` for any character in the Arabic Unicode block.
  Any hit fails the build. This is the guardrail that keeps the whole
  customer-visible surface in one reviewable file.
- `tests/test_copy_coverage.py` — asserts a constant exists for each of
  the 30 spec IDs (C1–C15, O1–O6, E1–E9). A missing screen fails
  loudly instead of being discovered by a customer.

**Checkpoint**
- All three tests green. At that point `copy_fa.py` is printable, and
  "read every string aloud to a native Persian speaker" becomes a
  single reviewable artifact.

---

## Phase 7 — Bot layer

**Create**
- `src/ollie/bot/main.py` — aiogram `Dispatcher`, long polling with a
  persisted offset and explicit `allowed_updates`, optional proxy from
  config, graceful shutdown.
- `src/ollie/bot/keyboards.py` — one builder per screen, labels from
  `copy_fa` only. `callback_data` is always
  `action:entity_id:expected_state`.
- `src/ollie/bot/fsm.py` — aiogram FSM states for the typed-input steps
  (name, phone, address, postal, tracking, support, custom reject
  reason). MemoryStorage is fine: the cart and orders live in SQLite,
  and a restart mid-typing is exactly what E6 is for.
- `src/ollie/bot/middlewares.py` — owner gate (non-owner `/panel`
  returns `None`, never a message), and a catch-all that logs and
  replies E8 rather than dying silently.
- `src/ollie/bot/send.py` — `send_or_alert()`: 3 retries with backoff,
  per-chat rate spacing, `E7` on `bot was blocked`, and — critically —
  never returns success on a failed send, because the credential
  transaction depends on it.
- `src/ollie/bot/handlers/`:
  - `start.py` (C1, deep link)
  - `catalog.py` (C2–C4)
  - `cart.py` (C5)
  - `checkout.py` (C6–C9)
  - `receipt.py` (C10–C11)
  - `history.py` (C15)
  - `support.py` (C16/O6)
  - `owner.py` (O1–O5)
- `src/ollie/bot/sweeper.py` — 5-minute loop: expire `awaiting_receipt`
  past `expires_at`, release reservations, notify, and run
  `domain.validate` invariants, alerting the owner on any violation.
  Also decide and implement the `rejected -> expired` policy added to
  the FSM after the Phase 4 review (`ollie.domain.states`): how long a
  rejected order waits before this fires (reuse
  `payment_window_hours`, or a separate config value), and where the
  clock starts reading from — most likely the `event_log` row for the
  `receipt_submitted -> rejected` transition, rather than a new column
  on `order`.

**Checkpoint per handler group**
- Each maps 1:1 to spec screens and pulls every visible string from
  `copy_fa`. `test_copy_isolation` passing is the mechanical proof.

---

## Phase 8 — Manual acceptance

Against a real test bot and two real Telegram accounts, walking the
spec's done-criteria list. The three that catch the most:

- **Kill the container mid-checkout.** Cart and order state must
  survive; the customer sees E6 and can continue.
- **Tap ✅ twice fast** on an approval. Exactly one delivery, one
  `event_log` row, E2 on the second.
- **Every mixed Persian/Latin string on a real phone** — order codes
  and card numbers inside Persian sentences reorder visually in ways a
  terminal won't show you.

Full done-criteria checklist (from `docs/m1-spec.html`):
- A customer who has never used the bot completes a digital purchase
  and receives credentials in under three minutes, with no typed input
  beyond name and phone.
- The owner approves from a lock-screen notification in two taps,
  without opening the panel.
- A resent receipt image is caught and flagged before the owner sees
  it as new.
- An unpaid order expires after 24 hours, releases its credential, and
  tells the customer.
- A rejected order can be retried with a correct receipt and completes
  normally.
- The container is killed mid-checkout and the customer's cart and
  order state survive the restart.
- A physical order reaches the customer's chat with a tracking number
  pushed, unprompted.
- Every string a customer can see has been read aloud by a native
  Persian speaker who is not the developer.

---

## Sequencing note

Phases 0–3 are mechanical and can run in one pass. **Phase 4's
state-machine test is the real gate** — if the domain layer isn't
provably correct and dependency-free before aiogram enters the
picture, every bug afterwards becomes a Telegram bug to debug through
a chat client instead of a unit test.
