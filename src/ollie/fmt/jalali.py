"""
Gregorian <-> Jalali (Iranian solar Hijri) date conversion.

This is a standard, widely-reproduced public-domain algorithm (the
family used by jalaali-js, PHP's jdf, and others), reimplemented here
stdlib-only rather than taken as a dependency. It is not trusted on
memory alone: both directions were checked, before being written down
here, against the `jdatetime` library as an independent oracle across
569 sampled dates spanning 1970-01-01 through 2120-12-31 (roughly every
97 days) with zero mismatches — see docs/roadmap.md's Phase 4 note.
Had that check failed, the plan was to depend on `persiantools`
instead of debugging calendar math by hand; it didn't come to that.

Valid for Gregorian years from 622 onward (i.e. all dates the product
will ever encounter); the algorithm's own 1600-year offset trick is
what keeps the arithmetic in a comfortable range on both sides.
"""

from __future__ import annotations

from ollie.fmt.digits import to_persian_digits

_GREGORIAN_CUMULATIVE_DAYS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
_GREGORIAN_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """Convert a Gregorian (year, month, day) to Jalali (year, month, day)."""
    if not (1 <= gm <= 12):
        raise ValueError(f"gregorian month out of range: {gm}")
    if not (1 <= gd <= 31):
        raise ValueError(f"gregorian day out of range: {gd}")

    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621

    gy2 = gy + 1 if gm > 2 else gy
    days = (
        (365 * gy)
        + ((gy2 + 3) // 4)
        - ((gy2 + 99) // 100)
        + ((gy2 + 399) // 400)
        - 80
        + gd
        + _GREGORIAN_CUMULATIVE_DAYS[gm - 1]
    )

    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365

    if days < 186:
        jm = 1 + days // 31
        jd = 1 + (days % 31)
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + ((days - 186) % 30)

    return jy, jm, jd


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    """Convert a Jalali (year, month, day) to Gregorian (year, month, day)."""
    if not (1 <= jm <= 12):
        raise ValueError(f"jalali month out of range: {jm}")
    if not (1 <= jd <= 31):
        raise ValueError(f"jalali day out of range: {jd}")

    if jy > 979:
        gy = 1600
        jy -= 979
    else:
        gy = 621

    days = (jm - 1) * 31 if jm < 7 else ((jm - 7) * 30) + 186
    days += (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + 78 + jd

    gy += 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1

    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365

    gd = days + 1
    days_in_month = list(_GREGORIAN_DAYS_IN_MONTH)
    if (gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0):
        days_in_month[1] = 29

    gm = 0
    while gm < 12 and gd > days_in_month[gm]:
        gd -= days_in_month[gm]
        gm += 1
    gm += 1

    return gy, gm, gd


def format_jalali(jy: int, jm: int, jd: int) -> str:
    """The spec's display form, e.g. '۱۴۰۵/۰۶/۲۲' — Persian digits, per docs/m1-spec.html."""
    return to_persian_digits(f"{jy:04d}/{jm:02d}/{jd:02d}")
