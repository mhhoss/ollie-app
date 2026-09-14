"""One module per aggregate: products, customers, orders, credentials,
receipts, events. Plain functions taking a connection — no ORM, no
session object, no repository classes."""

from __future__ import annotations
