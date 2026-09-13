"""
The Ollie domain layer: order state machine, business models, order
codes, and money arithmetic.

Design rule, enforced by tests/domain/test_no_external_deps.py, not
just this docstring: everything under ollie.domain imports only the
standard library and other ollie.domain modules. No aiogram, no
sqlite3, no ollie.bot, no ollie.db — and no ollie.fmt either; domain
and fmt are independent stdlib-only siblings, composed together only
by the bot layer, so that neither one accumulates a dependency on the
other's concerns over time.
"""
