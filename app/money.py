"""Indian currency parsing and display."""

from __future__ import annotations

import re

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def parse_price(value: object) -> float | None:
    """Return a numeric price from a SerpApi field, or None when it is absent."""

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if not isinstance(value, str):
        return None
    match = _NUMBER.search(value.replace(",", ""))
    if match is None:
        return None
    amount = float(match.group(0))
    return amount if amount > 0 else None


def currency_of(label: object) -> str:
    """Classify a price label. Unmarked amounts are treated as INR."""

    if not isinstance(label, str):
        return "INR"
    text = label.upper()
    if "₹" in label or "INR" in text or "RS" in text:
        return "INR"
    if "$" in label or "USD" in text:
        return "USD"
    return "INR"


def format_inr(amount: float) -> str:
    """Format a rupee amount with Indian grouping."""

    sign = "-" if amount < 0 else ""
    digits = str(abs(int(round(amount))))
    if len(digits) <= 3:
        return f"{sign}₹{digits}"
    last = digits[-3:]
    rest = digits[:-3]
    groups: list[str] = []
    while rest:
        groups.append(rest[-2:])
        rest = rest[:-2]
    return f"{sign}₹{','.join(reversed(groups))},{last}"


def format_money(amount: float, currency: str) -> str:
    if currency == "USD":
        return f"${amount:,.0f}"
    return format_inr(amount)
