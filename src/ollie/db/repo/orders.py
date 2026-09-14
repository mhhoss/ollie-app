"""
Orders — the two functions the roadmap calls out as needing to be
single, all-or-nothing transactions: `create()` (checkout: reserve
stock/credentials, allocate a non-colliding payable_amount, insert
everything, log the event) and `transition()` (the idempotency point
for duplicate Telegram callbacks: re-read current state, check it's
still legal, update, log — under a write lock, so a second concurrent
call sees the *result* of the first, not a stale copy).

Every row in "order" is composed back into a full `ollie.domain.Order`
(items included) before it's ever handed to a caller — nothing outside
this module sees a bare `sqlite3.Row` or the surrogate `order.id`
/ `customer.id` columns. That surrogate-id boundary is exactly what
`ollie.domain.models`'s docstring says this layer is responsible for.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from ollie.db.errors import OrderNotFound
from ollie.db.repo import customers, events
from ollie.domain import codes, money
from ollie.domain.errors import AmountCollision, InsufficientStock
from ollie.domain.models import Order, OrderItem, ProductKind
from ollie.domain.states import OrderState

_MAX_CODE_ATTEMPTS = 50
_TAIL_SPAN = money.TAIL_MAX - money.TAIL_MIN + 1


def get(conn: sqlite3.Connection, order_code: str) -> Order | None:
    row = conn.execute('SELECT * FROM "order" WHERE code = ?', (order_code,)).fetchone()
    if row is None:
        return None
    return _compose_order(conn, row)


def set_invoice_message_id(conn: sqlite3.Connection, order_code: str, message_id: int) -> None:
    """Not a state transition (no event_log row, no FSM check) — just
    recording which sent message is the C9 invoice, so it can be
    unpinned/edited later (C12/C13). Known only after create() has
    already sent that message, hence the separate call."""
    conn.execute(
        'UPDATE "order" SET invoice_message_id = ? WHERE code = ?', (message_id, order_code)
    )


def list_for_customer(conn: sqlite3.Connection, telegram_id: int) -> list[Order]:
    rows = conn.execute(
        'SELECT o.* FROM "order" o JOIN customer c ON c.id = o.customer_id '
        "WHERE c.telegram_id = ? ORDER BY o.created_at DESC",
        (telegram_id,),
    ).fetchall()
    return [_compose_order(conn, row) for row in rows]


def list_recent(conn: sqlite3.Connection, *, limit: int = 20) -> list[Order]:
    """O4's "همه سفارش‌ها" panel view — the owner's own cross-customer
    listing, as opposed to list_for_customer's single-customer one."""
    rows = conn.execute(
        'SELECT * FROM "order" ORDER BY created_at DESC LIMIT ?', (limit,)
    ).fetchall()
    return [_compose_order(conn, row) for row in rows]


def count_by_state(conn: sqlite3.Connection, state: OrderState) -> int:
    row = conn.execute(
        'SELECT COUNT(*) AS n FROM "order" WHERE state = ?', (state.value,)
    ).fetchone()
    return int(row["n"])


def list_awaiting_receipt_past_expiry(conn: sqlite3.Connection, now: int) -> list[Order]:
    """Sweeper feed #1: unpaid orders whose 24h window has elapsed."""
    rows = conn.execute(
        'SELECT * FROM "order" WHERE state = ? AND expires_at IS NOT NULL AND expires_at <= ?',
        (OrderState.AWAITING_RECEIPT.value, now),
    ).fetchall()
    return [_compose_order(conn, row) for row in rows]


def list_rejected_past_retry_window(
    conn: sqlite3.Connection, *, window_seconds: int, now: int
) -> list[Order]:
    """
    Sweeper feed #2: rejected orders never resubmitted within
    `window_seconds` of the rejection — the `(rejected -> expired)`
    edge added post-M1-draft (`ollie.domain.states`). The clock reads
    from `event_log`'s own `(receipt_submitted -> rejected)` row, per
    that edge's own note, rather than a column on `order` — an order
    can be rejected more than once, so the *latest* such row per order
    is what actually starts this window.
    """
    rows = conn.execute(
        "SELECT o.code AS code, MAX(e.at) AS rejected_at "
        'FROM "order" o JOIN event_log e ON e.order_id = o.id '
        "WHERE o.state = ? AND e.to_state = ? "
        "GROUP BY o.id",
        (OrderState.REJECTED.value, OrderState.REJECTED.value),
    ).fetchall()
    overdue_codes = [row["code"] for row in rows if now - row["rejected_at"] >= window_seconds]
    return [order for code in overdue_codes if (order := get(conn, code)) is not None]


def create(
    conn: sqlite3.Connection,
    *,
    customer_telegram_id: int,
    items: Sequence[OrderItem],
    shipping_cost: int,
    payment_window_hours: int,
    created_at: int,
    ship_name: str | None = None,
    ship_phone: str | None = None,
    ship_address: str | None = None,
    invoice_message_id: int | None = None,
) -> Order:
    """
    C9 checkout, as one transaction: reserve every item's stock or
    credentials, allocate a code and a non-colliding payable_amount,
    insert the order + its items, log the (draft -> awaiting_receipt)
    event, and only then commit. Any failure along the way — a variant
    out of stock, a product with no available credentials left, no
    free payable_amount — rolls back the entire thing; a customer
    never ends up with a half-reserved cart.

    `items` are fully-snapshotted `OrderItem`s (the caller has already
    read current price/stock from `repo.products` and built the
    snapshot) — this function's job is reservation and persistence,
    not pricing.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        customer_id = customers.customer_id_for(conn, customer_telegram_id)

        for item in items:
            if item.kind == ProductKind.PHYSICAL:
                _reserve_stock(conn, item.variant_id, item.quantity)
            else:
                _reserve_credentials(conn, item.product_id, item.quantity)

        code = _allocate_unique_code(conn)
        subtotal = sum(item.line_total for item in items)
        tail, payable_amount = _allocate_unique_amount(conn, subtotal, shipping_cost)
        expires_at = created_at + payment_window_hours * 3600

        order = Order.create(
            code=code,
            customer_telegram_id=customer_telegram_id,
            items=tuple(items),
            shipping_cost=shipping_cost,
            amount_tail=tail,
            expires_at=expires_at,
            created_at=created_at,
            ship_name=ship_name,
            ship_phone=ship_phone,
            ship_address=ship_address,
            invoice_message_id=invoice_message_id,
        )

        order_id = _insert_order(conn, order, customer_id)
        _insert_order_items(conn, order_id, order.items)
        _link_reserved_credentials_to_order(conn, order_id, order.items)
        events.log_event(
            conn,
            order_id,
            from_state=None,
            to_state=order.state.value,
            actor="customer",
            detail=None,
            at=created_at,
        )
        conn.execute("COMMIT")
        return order
    except Exception:
        conn.execute("ROLLBACK")
        raise


def transition(
    conn: sqlite3.Connection,
    order_code: str,
    to_state: OrderState,
    *,
    actor: str,
    at: int,
    detail: str | None = None,
    **field_overrides: object,
) -> Order:
    """
    Re-read the order's current state, attempt the transition, update,
    and log — all under the write lock `BEGIN IMMEDIATE` acquires up
    front. This is the idempotency point for duplicate Telegram
    callbacks: if two calls race for the same order, the second one
    blocks until the first commits, then re-reads the *new* state. A
    from-state that no longer matches an ALLOWED edge (because the
    first call already moved it) raises `IllegalTransition` from
    `Order.with_state` — caught by neither this function nor the
    caller silently, but surfaced as exactly what it is: a stale,
    already-processed callback, not a defect. Exactly one `event_log`
    row is ever written for a given transition, because only the call
    that wins the race reaches the INSERT before rolling back is even
    possible.

    Landing on `cancelled` or `expired` releases every reservation this
    order held (stock incremented back, credentials returned to
    `available`) as part of the same transaction — the state table's
    own "release reservations" guard on both of those edges, kept here
    rather than left for each caller (a customer's C9 cancel, the
    sweeper's two expiry paths) to remember independently.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute('SELECT * FROM "order" WHERE code = ?', (order_code,)).fetchone()
        if row is None:
            raise OrderNotFound(order_code)

        current = _compose_order(conn, row)
        updated = current.with_state(to_state, **field_overrides)

        _update_order_row(conn, row["id"], updated)
        if to_state in (OrderState.CANCELLED, OrderState.EXPIRED):
            _release_reservations(conn, row["id"], updated.items)
        events.log_event(
            conn,
            row["id"],
            from_state=current.state.value,
            to_state=to_state.value,
            actor=actor,
            detail=detail,
            at=at,
        )
        conn.execute("COMMIT")
        return updated
    except Exception:
        conn.execute("ROLLBACK")
        raise


# ---------------------------------------------------------------------------
# Reservation
# ---------------------------------------------------------------------------
def _reserve_stock(conn: sqlite3.Connection, variant_id: int | None, quantity: int) -> None:
    if variant_id is None:
        raise InsufficientStock("a physical order item must carry a variant_id")
    row = conn.execute("SELECT stock, reserved FROM variant WHERE id = ?", (variant_id,)).fetchone()
    if row is None:
        raise InsufficientStock(f"variant {variant_id} does not exist")
    available = row["stock"] - row["reserved"]
    if available < quantity:
        raise InsufficientStock(f"variant {variant_id}: only {available} in stock, need {quantity}")
    conn.execute("UPDATE variant SET reserved = reserved + ? WHERE id = ?", (quantity, variant_id))


def _reserve_credentials(conn: sqlite3.Connection, product_id: int, quantity: int) -> None:
    rows = conn.execute(
        "SELECT id FROM credential WHERE product_id = ? AND status = 'available' LIMIT ?",
        (product_id, quantity),
    ).fetchall()
    if len(rows) < quantity:
        raise InsufficientStock(
            f"product {product_id}: only {len(rows)} credentials available, need {quantity}"
        )
    ids = [row["id"] for row in rows]
    conn.executemany("UPDATE credential SET status = 'reserved' WHERE id = ?", [(i,) for i in ids])


def _release_reservations(
    conn: sqlite3.Connection, order_id: int, items: Sequence[OrderItem]
) -> None:
    """The inverse of _reserve_stock/_reserve_credentials, called from
    transition() when an order lands on cancelled or expired. Scoped to
    this specific order_id, so releasing one order's credentials never
    touches another order's reservations of the same product."""
    for item in items:
        if item.kind == ProductKind.PHYSICAL:
            conn.execute(
                "UPDATE variant SET reserved = reserved - ? WHERE id = ?",
                (item.quantity, item.variant_id),
            )
        else:
            conn.execute(
                "UPDATE credential SET status = 'available', order_id = NULL "
                "WHERE order_id = ? AND product_id = ? AND status = 'reserved'",
                (order_id, item.product_id),
            )


def _link_reserved_credentials_to_order(
    conn: sqlite3.Connection, order_id: int, items: Sequence[OrderItem]
) -> None:
    """
    Stamp order_id onto the credential rows this order's digital items
    just reserved. Reservation (marking `status = 'reserved'`) happens
    in `_reserve_credentials` before the order row exists, so this
    second pass claims exactly `quantity` still-unlinked reserved rows
    per digital product — the `order_id IS NULL` filter is what makes
    that safe to run after other orders may have reserved credentials
    for the same product in between.
    """
    for item in items:
        if item.kind != ProductKind.PHYSICAL:
            rows = conn.execute(
                "SELECT id FROM credential "
                "WHERE product_id = ? AND status = 'reserved' AND order_id IS NULL "
                "LIMIT ?",
                (item.product_id, item.quantity),
            ).fetchall()
            ids = [row["id"] for row in rows]
            conn.executemany(
                "UPDATE credential SET order_id = ? WHERE id = ?",
                [(order_id, i) for i in ids],
            )


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------
def _allocate_unique_code(conn: sqlite3.Connection) -> str:
    for _ in range(_MAX_CODE_ATTEMPTS):
        code = codes.generate_code()
        exists = conn.execute('SELECT 1 FROM "order" WHERE code = ?', (code,)).fetchone()
        if exists is None:
            return code
    # The code space is 32**6 ≈ 1.07 billion; this branch is defensive,
    # not a path any realistic store ever reaches.
    raise RuntimeError(f"could not allocate a unique order code in {_MAX_CODE_ATTEMPTS} attempts")


def _allocate_unique_amount(
    conn: sqlite3.Connection, subtotal: int, shipping_cost: int
) -> tuple[int, int]:
    """
    Pick a payable_amount unique among currently-open orders — the
    exact scope `idx_order_open_payable_amount` enforces as a database
    constraint, checked here first so a collision is a retry, not a
    thrown IntegrityError.

    Starts from a random tail (the spec's ordinary case) and then
    walks the full 900-value tail ring deterministically via
    money.next_tail, rather than the spec's literal "retry 50 times,
    then total + 1 upward" fallback: that literal fallback would step
    payable_amount outside the domain's amount_tail in [100, 999]
    invariant. Trying every tail before giving up is strictly more
    thorough than 50 attempts and never breaks that invariant — a
    deliberate, documented deviation from the spec's exact wording, not
    an oversight.
    """
    tail = money.random_tail()
    for _ in range(_TAIL_SPAN):
        payable = money.payable(subtotal, shipping_cost, tail)
        if not _payable_amount_open(conn, payable):
            return tail, payable
        tail = money.next_tail(tail)
    raise AmountCollision("no free payable_amount tail (100-999) among currently open orders")


def _payable_amount_open(conn: sqlite3.Connection, payable_amount: int) -> bool:
    row = conn.execute(
        'SELECT 1 FROM "order" WHERE payable_amount = ? '
        "AND state IN ('awaiting_receipt', 'receipt_submitted', 'rejected')",
        (payable_amount,),
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Row <-> domain object
# ---------------------------------------------------------------------------
def _insert_order(conn: sqlite3.Connection, order: Order, customer_id: int) -> int:
    cursor = conn.execute(
        'INSERT INTO "order" ('
        "code, customer_id, state, subtotal, shipping_cost, amount_tail, payable_amount, "
        "is_physical, ship_name, ship_phone, ship_address, tracking_number, carrier, "
        "reject_count, invoice_message_id, expires_at, created_at, approved_at, fulfilled_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            order.code,
            customer_id,
            order.state.value,
            order.subtotal,
            order.shipping_cost,
            order.amount_tail,
            order.payable_amount,
            int(order.is_physical),
            order.ship_name,
            order.ship_phone,
            order.ship_address,
            order.tracking_number,
            order.carrier,
            order.reject_count,
            order.invoice_message_id,
            order.expires_at,
            order.created_at,
            order.approved_at,
            order.fulfilled_at,
        ),
    )
    return int(cursor.lastrowid)  # type: ignore[arg-type]


def _insert_order_items(
    conn: sqlite3.Connection, order_id: int, items: Sequence[OrderItem]
) -> None:
    conn.executemany(
        "INSERT INTO order_item "
        "(order_id, product_id, variant_id, kind, name_snapshot, unit_price, "
        "cost_price_snapshot, quantity) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                order_id,
                item.product_id,
                item.variant_id,
                item.kind.value,
                item.name_snapshot,
                item.unit_price,
                item.cost_price_snapshot,
                item.quantity,
            )
            for item in items
        ],
    )


def _update_order_row(conn: sqlite3.Connection, order_id: int, order: Order) -> None:
    conn.execute(
        'UPDATE "order" SET '
        "state = ?, tracking_number = ?, carrier = ?, reject_count = ?, "
        "expires_at = ?, approved_at = ?, fulfilled_at = ? "
        "WHERE id = ?",
        (
            order.state.value,
            order.tracking_number,
            order.carrier,
            order.reject_count,
            order.expires_at,
            order.approved_at,
            order.fulfilled_at,
            order_id,
        ),
    )


def _compose_order(conn: sqlite3.Connection, row: sqlite3.Row) -> Order:
    item_rows = conn.execute(
        "SELECT * FROM order_item WHERE order_id = ? ORDER BY id", (row["id"],)
    ).fetchall()
    items = tuple(
        OrderItem(
            product_id=item["product_id"],
            variant_id=item["variant_id"],
            kind=ProductKind(item["kind"]),
            name_snapshot=item["name_snapshot"],
            unit_price=item["unit_price"],
            cost_price_snapshot=item["cost_price_snapshot"],
            quantity=item["quantity"],
        )
        for item in item_rows
    )
    customer_row = conn.execute(
        "SELECT telegram_id FROM customer WHERE id = ?", (row["customer_id"],)
    ).fetchone()

    return Order(
        code=row["code"],
        customer_telegram_id=customer_row["telegram_id"],
        state=OrderState(row["state"]),
        items=items,
        subtotal=row["subtotal"],
        shipping_cost=row["shipping_cost"],
        amount_tail=row["amount_tail"],
        payable_amount=row["payable_amount"],
        is_physical=bool(row["is_physical"]),
        ship_name=row["ship_name"],
        ship_phone=row["ship_phone"],
        ship_address=row["ship_address"],
        tracking_number=row["tracking_number"],
        carrier=row["carrier"],
        reject_count=row["reject_count"],
        invoice_message_id=row["invoice_message_id"],
        expires_at=row["expires_at"],
        created_at=row["created_at"],
        approved_at=row["approved_at"],
        fulfilled_at=row["fulfilled_at"],
    )
