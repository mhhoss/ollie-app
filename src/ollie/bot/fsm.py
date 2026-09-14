"""
aiogram FSM states for the handful of steps that need typed input:
checkout's name/phone/address/postal capture, the owner's custom
reject reason and tracking-number entry, and the two-way support
relay. Every other screen is button-driven and needs no state at all.

`MemoryStorage` (wired in `main.py`) is deliberately fine here, per the
roadmap: the cart and every order live in SQLite, so a restart mid-
typing just loses the in-progress keystrokes, which is exactly what
copy_fa.E6_STATE_LOST exists to tell the customer — not a data-loss
bug.
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Checkout(StatesGroup):
    name = State()
    phone = State()
    address = State()
    postal_code = State()


class OwnerAction(StatesGroup):
    reject_custom_reason = State()
    tracking_number = State()
    add_credentials = State()


class Support(StatesGroup):
    customer_message = State()
    owner_reply = State()
