-- Ollie's SQLite schema. Transcribed from docs/m1-spec.html's data
-- model section, plus the indexes it names explicitly and one
-- constraint the spec describes as an application-logic rule but that
-- belongs at the database level instead (see the note above
-- idx_order_open_payable_amount below).
--
-- Applied once, in full, by ollie.db.migrate when a fresh database's
-- PRAGMA user_version is 0. Never edited in place after release --
-- schema changes are new migration steps (see migrate.py).

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- Catalog
-- ---------------------------------------------------------------------
CREATE TABLE product (
    id INTEGER PRIMARY KEY,
    category_id INTEGER,
    kind TEXT NOT NULL CHECK (kind IN ('digital', 'physical')),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    photo_file_id TEXT,
    price INTEGER NOT NULL,
    cost_price INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE variant (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES product (id),
    label TEXT NOT NULL,
    price_delta INTEGER NOT NULL DEFAULT 0,
    stock INTEGER NOT NULL DEFAULT 0,
    reserved INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_variant_product ON variant (product_id);

CREATE TABLE credential (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES product (id),
    payload TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('available', 'reserved', 'delivered')),
    order_id INTEGER REFERENCES "order" (id),
    delivered_at INTEGER
);
CREATE INDEX idx_credential_product_status ON credential (product_id, status);

-- ---------------------------------------------------------------------
-- Customers and orders
-- ---------------------------------------------------------------------
CREATE TABLE customer (
    id INTEGER PRIMARY KEY,
    telegram_id INTEGER NOT NULL UNIQUE,
    full_name TEXT,
    phone TEXT,
    address TEXT,
    postal_code TEXT,
    is_blocked INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE "order" (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL REFERENCES customer (id),
    state TEXT NOT NULL,
    subtotal INTEGER NOT NULL,
    shipping_cost INTEGER NOT NULL,
    amount_tail INTEGER NOT NULL,
    payable_amount INTEGER NOT NULL,
    is_physical INTEGER NOT NULL,
    ship_name TEXT,
    ship_phone TEXT,
    ship_address TEXT,
    tracking_number TEXT,
    carrier TEXT,
    reject_count INTEGER NOT NULL DEFAULT 0,
    invoice_message_id INTEGER,
    expires_at INTEGER,
    created_at INTEGER NOT NULL,
    approved_at INTEGER,
    fulfilled_at INTEGER
);
CREATE INDEX idx_order_state_expires ON "order" (state, expires_at);
CREATE INDEX idx_order_customer_created ON "order" (customer_id, created_at);

-- The spec calls this an application-logic rule ("enforce uniqueness
-- at insert, not in application logic that races" — its own "Traps"
-- section agrees). A partial unique index is what actually delivers
-- that: it's enforced by SQLite itself inside the same transaction
-- that inserts the row, so two concurrent inserts can't both succeed
-- with the same amount no matter what the application code does.
-- Scope matches ollie.domain.validate._RESERVABLE_STATES exactly:
-- awaiting_receipt, receipt_submitted, and rejected (still retryable
-- back to awaiting_receipt) all hold a live claim on their amount;
-- cancelled/expired/fulfilled orders release theirs.
CREATE UNIQUE INDEX idx_order_open_payable_amount
    ON "order" (payable_amount)
    WHERE state IN ('awaiting_receipt', 'receipt_submitted', 'rejected');

CREATE TABLE order_item (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES "order" (id),
    product_id INTEGER NOT NULL,
    variant_id INTEGER,
    kind TEXT NOT NULL CHECK (kind IN ('digital', 'physical')),
    name_snapshot TEXT NOT NULL,
    unit_price INTEGER NOT NULL,
    cost_price_snapshot INTEGER NOT NULL,
    quantity INTEGER NOT NULL
);
CREATE INDEX idx_order_item_order ON order_item (order_id);

-- ---------------------------------------------------------------------
-- Evidence
-- ---------------------------------------------------------------------
CREATE TABLE receipt (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES "order" (id),
    file_id TEXT NOT NULL,
    file_unique_id TEXT NOT NULL,
    image_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    verdict TEXT,
    reject_reason TEXT,
    submitted_at INTEGER NOT NULL,
    reviewed_at INTEGER
);
CREATE INDEX idx_receipt_hash ON receipt (image_hash);
CREATE INDEX idx_receipt_order ON receipt (order_id);

CREATE TABLE event_log (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES "order" (id),
    from_state TEXT,
    to_state TEXT NOT NULL,
    actor TEXT NOT NULL CHECK (actor IN ('customer', 'owner', 'system')),
    detail TEXT,
    at INTEGER NOT NULL
);
CREATE INDEX idx_event_log_order ON event_log (order_id);

-- Cart persistence (C5: "lives in the DB keyed by customer_id, not in
-- memory"). No repository module in Phase 5 — the bot layer (Phase 6)
-- owns cart reads/writes directly; the table exists now so Phase 6
-- doesn't need its own migration.
CREATE TABLE cart_item (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customer (id),
    product_id INTEGER NOT NULL REFERENCES product (id),
    variant_id INTEGER,
    quantity INTEGER NOT NULL
);
CREATE INDEX idx_cart_item_customer ON cart_item (customer_id);
