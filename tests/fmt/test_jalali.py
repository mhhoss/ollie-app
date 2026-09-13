"""
Fixed vectors here were checked, before being written down, against the
`jdatetime` library as an independent oracle across 569 dates sampled
every ~97 days from 1970-01-01 through 2120-12-31 — zero mismatches in
either direction. See ollie.fmt.jalali's module docstring and
docs/roadmap.md's Phase 4 notes. jdatetime itself is never imported
here or anywhere in the shipped code — fmt stays stdlib-only.
"""

from __future__ import annotations

from datetime import date, timedelta

from ollie.fmt.jalali import format_jalali, gregorian_to_jalali, jalali_to_gregorian

# (gregorian, jalali) — each checked against the jdatetime oracle.
_VECTORS: list[tuple[tuple[int, int, int], tuple[int, int, int]]] = [
    ((2026, 9, 13), (1405, 6, 22)),  # today
    ((2024, 3, 20), (1403, 1, 1)),  # Nowruz 1403
    ((2025, 3, 20), (1403, 12, 30)),  # day *before* Nowruz 1404 — a wrong guess I made
    ((2026, 3, 21), (1405, 1, 1)),  # Nowruz 1405
    ((2020, 3, 20), (1399, 1, 1)),  # a Jalali leap year's Nowruz
    ((2016, 3, 20), (1395, 1, 1)),  # another Jalali leap year's Nowruz
    ((2017, 3, 21), (1396, 1, 1)),  # the following (non-leap) year's Nowruz
    ((2000, 1, 1), (1378, 10, 11)),
    ((1979, 2, 11), (1357, 11, 22)),
    ((2100, 6, 15), (1479, 3, 25)),
]


def test_gregorian_to_jalali_fixed_vectors() -> None:
    for (gy, gm, gd), expected in _VECTORS:
        assert gregorian_to_jalali(gy, gm, gd) == expected, f"{gy}-{gm}-{gd}"


def test_jalali_to_gregorian_fixed_vectors() -> None:
    for expected, (jy, jm, jd) in _VECTORS:
        assert jalali_to_gregorian(jy, jm, jd) == expected, f"{jy}-{jm}-{jd}"


def test_round_trip_is_self_consistent_across_a_wide_range() -> None:
    """
    Doesn't need an external oracle — just checks gregorian_to_jalali
    and jalali_to_gregorian are true inverses of each other, sampled
    every 11 days across 1970-01-01 through 2120-12-31 (~5,000 dates).
    """
    start = date(1970, 1, 1)
    end = date(2120, 12, 31)
    d = start
    checked = 0
    while d <= end:
        jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
        back = jalali_to_gregorian(jy, jm, jd)
        assert back == (d.year, d.month, d.day), f"{d} -> {(jy, jm, jd)} -> {back}"
        checked += 1
        d += timedelta(days=11)
    assert checked > 4000  # sanity: the loop actually ran the range


def test_format_jalali_uses_persian_digits_and_slashes() -> None:
    assert format_jalali(1405, 6, 22) == "۱۴۰۵/۰۶/۲۲"


def test_format_jalali_pads_single_digit_month_and_day() -> None:
    assert format_jalali(1405, 1, 1) == "۱۴۰۵/۰۱/۰۱"
