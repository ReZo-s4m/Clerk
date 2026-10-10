"""Separate the product from the cases, skins, and cables around it."""

from __future__ import annotations

from app.evidence import Listing

_ACCESSORY_TERMS = (
    "soft case",
    "carrying case",
    "travel case",
    "skin",
    "skins",
    "decal",
    "cover",
    "cushion",
    "ear tip",
    "ear tips",
    "earpad",
    "earpads",
    "cable",
    "pouch",
    "headband",
)


def focus_listings(product: str, listings: list[Listing]) -> tuple[list[Listing], int]:
    """Keep listings of the product itself. Return those listings and how many were set aside."""

    if any(term in product.lower() for term in ("case", "skin", "cover", "cable")):
        return listings, 0
    kept = [item for item in listings if not _is_accessory(item.title)]
    if not kept:
        return listings, 0
    return kept, len(listings) - len(kept)


def _is_accessory(title: str) -> bool:
    text = title.lower()
    return any(term in text for term in _ACCESSORY_TERMS)
