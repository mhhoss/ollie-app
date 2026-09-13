"""
Presentation formatting: Persian/ASCII digit conversion, Jalali dates,
Toman display strings.

Design rule, enforced by tests/domain/test_no_external_deps.py, not
just this docstring: everything under ollie.fmt imports only the
standard library and other ollie.fmt modules — never ollie.domain.
Domain and fmt are independent siblings; only the bot layer composes
the two.
"""
