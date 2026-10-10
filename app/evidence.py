"""Turn compact SerpApi JSON into the evidence the desk can cite."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import quote

from app.money import currency_of, parse_price


@dataclass(frozen=True)
class Listing:
    title: str
    price: float | None
    currency: str
    price_label: str | None
    seller: str | None
    url: str | None
    rating: float | None
    reviews: int | None = None
    multiple_sources: bool = False
    price_floor: bool = False


@dataclass(frozen=True)
class Place:
    title: str
    rating: float | None
    reviews: int | None
    address: str | None
    url: str | None
    kind: str | None


@dataclass(frozen=True)
class Article:
    title: str
    url: str | None
    source: str | None
    date: str | None
    snippet: str | None


@dataclass(frozen=True)
class Page:
    title: str
    url: str | None
    snippet: str | None


def loads(raw: str) -> dict:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("SerpApi returned a response Clerk cannot read.")
    if isinstance(payload.get("error"), str) and payload["error"].strip():
        raise ValueError(payload["error"].strip())
    return payload


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _public_http(value: object) -> str | None:
    found = _text(value)
    if found and found.startswith("http") and "serpapi.com" not in found:
        return found
    return None


def _url(item: dict) -> str | None:
    website = _public_http(item.get("website"))
    if website:
        return website
    for key in ("product_link", "link", "tracking_link"):
        found = _public_http(item.get(key))
        if found:
            return found
    links = item.get("links")
    if isinstance(links, dict):
        for key in ("website", "directions"):
            found = _public_http(links.get(key))
            if found:
                return found
    place_id = _text(item.get("place_id"))
    if place_id:
        return "https://www.google.com/maps/search/?api=1&query_place_id=" + quote(place_id)
    return None


def _rating(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        parsed = parse_price(value)
        if parsed is not None and parsed <= 5:
            return parsed
    return None


def _source_name(value: object) -> str | None:
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, dict):
        return _text(value.get("name")) or _text(value.get("title"))
    return None


def listings_from(payload: dict) -> list[Listing]:
    rows = payload.get("shopping_results")
    if not isinstance(rows, list):
        return []
    listings: list[Listing] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = _text(row.get("title"))
        if title is None:
            continue
        label = _text(row.get("price"))
        amount = parse_price(row.get("extracted_price"))
        if amount is None:
            amount = parse_price(label)
        reviews = row.get("reviews")
        listings.append(
            Listing(
                title=title,
                price=amount,
                currency=currency_of(label),
                price_label=label,
                seller=_source_name(row.get("source")),
                url=_url(row),
                rating=_rating(row.get("rating")),
                reviews=reviews if isinstance(reviews, int) and not isinstance(reviews, bool) else None,
                multiple_sources=row.get("multiple_sources") is True,
                price_floor=bool(label and "+" in label),
            )
        )
    return listings


def places_from(payload: dict) -> list[Place]:
    rows = payload.get("local_results")
    if not isinstance(rows, list):
        rows = payload.get("place_results")
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        return []
    places: list[Place] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = _text(row.get("title"))
        if title is None:
            continue
        reviews = row.get("reviews")
        review_count = reviews if isinstance(reviews, int) and not isinstance(reviews, bool) else None
        places.append(
            Place(
                title=title,
                rating=_rating(row.get("rating")),
                reviews=review_count,
                address=_text(row.get("address")),
                url=_url(row),
                kind=_text(row.get("type")),
            )
        )
    return places


def articles_from(payload: dict) -> list[Article]:
    rows = payload.get("news_results")
    if not isinstance(rows, list):
        return []
    articles: list[Article] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = _text(row.get("title"))
        if title is None:
            continue
        articles.append(
            Article(
                title=title,
                url=_url(row),
                source=_source_name(row.get("source")),
                date=_text(row.get("date")) or _text(row.get("iso_date")),
                snippet=_text(row.get("snippet")),
            )
        )
    return articles


def pages_from(payload: dict) -> list[Page]:
    pages: list[Page] = []
    organic = payload.get("organic_results")
    if isinstance(organic, list):
        for row in organic:
            if not isinstance(row, dict):
                continue
            title = _text(row.get("title"))
            if title is None:
                continue
            pages.append(Page(title=title, url=_url(row), snippet=_text(row.get("snippet"))))
    box = payload.get("answer_box")
    if isinstance(box, dict):
        title = _text(box.get("title")) or "Answer box"
        snippet = _text(box.get("answer")) or _text(box.get("snippet"))
        if snippet or _text(box.get("title")):
            pages.insert(0, Page(title=title, url=_url(box), snippet=snippet))
    return pages
