"""The Clerk desk: plan, search, compare, veto, and act."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import asdict

from serpapi_search_tools import (
    SearchResultFormat,
    SearchResultMode,
    SerpApiSearchError,
    maps_search,
    news_search,
    shopping_search,
    web_search,
)

from app.decide import Verdict, decide
from app.followup import choose_followup
from app.market import focus_listings
from app.evidence import (
    Article,
    Listing,
    Page,
    Place,
    articles_from,
    listings_from,
    loads,
    pages_from,
    places_from,
)
from app.money import format_money

INDIA = {"gl": "in", "hl": "en", "google_domain": "google.co.in"}


def key_configured() -> bool:
    return bool(os.getenv("SERPAPI_API_KEY") or os.getenv("SERPAPI_KEY"))


def build_plan(product: str, city: str) -> list[dict[str, str]]:
    """Write the four searches. Each specialist gets one tool and one question."""

    return [
        {
            "agent": "Market",
            "tool": "shopping_search",
            "engine": "google_shopping",
            "query": product,
            "why": f"Who is selling {product}, and at what live price?",
        },
        {
            "agent": "Street",
            "tool": "maps_search",
            "engine": "google_maps",
            "query": f"{product} shop",
            "why": f"Is there a place in {city} where you can see it?",
        },
        {
            "agent": "Wire",
            "tool": "news_search",
            "engine": "google_news",
            "query": f"{product} (recall OR launch OR price OR discontinued)",
            "why": "Is this week's news a reason to wait?",
        },
        {
            "agent": "Record",
            "tool": "web_search",
            "engine": "google",
            "query": f"{product} review",
            "why": "What do durable pages say before you trust the price?",
        },
    ]


def _tools(city: str) -> dict:
    common = {
        "provider": "function",
        "include_examples": False,
        "response_format": SearchResultFormat.JSON,
        "mode": SearchResultMode.COMPACT,
        "timeout": 35,
    }
    located = {**INDIA, "location": city}
    return {
        "shopping_search": shopping_search(
            allowed_engines=["google_shopping"],
            default_engine="google_shopping",
            default_params=located,
            result_limit=8,
            **common,
        ),
        "maps_search": maps_search(
            default_params=INDIA,
            result_limit=5,
            **common,
        ),
        "news_search": news_search(
            default_params=INDIA,
            result_limit=6,
            **common,
        ),
        "web_search": web_search(
            allowed_engines=["google"],
            default_engine="google",
            default_params=INDIA,
            result_limit=6,
            **common,
        ),
    }


def _public_listing(item: Listing) -> dict:
    return {
        "title": item.title,
        "meta": _join(
            item.seller,
            (
                ("from " if item.price_floor else "") + format_money(item.price, item.currency)
                if item.price is not None
                else item.price_label
            ),
            f"{item.reviews} reviews" if item.reviews else None,
        ),
        "url": item.url,
    }


def _public_place(item: Place) -> dict:
    rating = f"{item.rating:.1f}" if item.rating is not None else None
    return {"title": item.title, "meta": _join(rating, item.address), "url": item.url}


def _public_article(item: Article) -> dict:
    return {"title": item.title, "meta": _join(item.source, item.date), "url": item.url}


def _public_page(item: Page) -> dict:
    return {"title": item.title, "meta": item.snippet, "url": item.url}


def _join(*parts: str | None) -> str | None:
    kept = [part for part in parts if part]
    return " · ".join(kept) if kept else None


def _summary_market(listings: list[Listing]) -> str:
    priced = [item for item in listings if item.price is not None and item.currency == "INR"]
    if not priced:
        priced = [item for item in listings if item.price is not None]
    noun = "listing" if len(listings) == 1 else "listings"
    if not priced:
        return f"{len(listings)} {noun}, no readable price"
    currency = priced[0].currency
    low = min(item.price or 0 for item in priced)
    high = max(item.price or 0 for item in priced)
    if low == high:
        prefix = "from " if all(item.price_floor for item in priced) else ""
        return f"{len(listings)} {noun} · {prefix}{format_money(low, currency)}"
    return f"{len(listings)} {noun} · {format_money(low, currency)} to {format_money(high, currency)}"


def _verdict_payload(verdict: Verdict) -> dict:
    payload = asdict(verdict)
    payload["reasons"] = [asdict(reason) for reason in verdict.reasons]
    return payload


def run_case(product: str, city: str, budget: int | None) -> Iterator[dict]:
    """Yield desk events. Four SerpApi searches, then a call."""

    product = product.strip()
    city = city.strip()
    plan = build_plan(product, city)
    yield {
        "type": "plan",
        "question": f"Should you buy {product} in {city} this week?",
        "steps": plan,
        "searches": 4,
    }
    if not key_configured():
        yield {
            "type": "error",
            "message": "Add SERPAPI_API_KEY to the .env file in the project folder, then start the desk again.",
        }
        return

    tools = _tools(city)
    listings: list[Listing] = []
    places: list[Place] = []
    articles: list[Article] = []
    pages: list[Page] = []
    live = 0

    for step in plan:
        yield {
            "type": "agent",
            "name": step["agent"],
            "status": "running",
            "tool": step["tool"],
            "engine": step["engine"],
            "query": step["query"],
            "why": step["why"],
        }
        try:
            if step["tool"] == "maps_search":
                raw = tools["maps_search"](query=step["query"], location=city, zoom=13)
            else:
                raw = tools[step["tool"]](query=step["query"])
            payload = loads(raw)
        except (SerpApiSearchError, ValueError, OSError) as exc:
            yield {
                "type": "agent",
                "name": step["agent"],
                "status": "error",
                "tool": step["tool"],
                "engine": step["engine"],
                "summary": str(exc),
                "items": [],
            }
            continue

        if step["agent"] == "Market":
            listings, set_aside = focus_listings(product, listings_from(payload))
            items = [_public_listing(item) for item in listings[:4]]
            summary = _summary_market(listings)
            if set_aside:
                summary += f" · {set_aside} accessories set aside"
        elif step["agent"] == "Street":
            places = places_from(payload)
            items = [_public_place(item) for item in places[:4]]
            summary = f"{len(places)} places" if places else "No places returned"
        elif step["agent"] == "Wire":
            articles = articles_from(payload)
            items = [_public_article(item) for item in articles[:4]]
            summary = f"{len(articles)} articles" if articles else "No articles returned"
        else:
            pages = pages_from(payload)
            items = [_public_page(item) for item in pages[:4]]
            summary = f"{len(pages)} pages" if pages else "No pages returned"

        if items:
            live += 1
        yield {
            "type": "agent",
            "name": step["agent"],
            "status": "done",
            "tool": step["tool"],
            "engine": step["engine"],
            "summary": summary,
            "items": items,
        }

    follow = choose_followup(product, listings, articles)
    followup_articles: list[Article] = []
    followup_status = "skipped"
    if not follow.needed:
        yield {
            "type": "agent",
            "name": "Second",
            "status": "skipped",
            "summary": follow.why,
            "why": follow.why,
            "items": [],
        }
    else:
        yield {
            "type": "agent",
            "name": "Second",
            "status": "running",
            "tool": follow.tool,
            "engine": follow.engine,
            "query": follow.query,
            "why": follow.why,
        }
        try:
            raw = tools[follow.tool](query=follow.query)
            payload = loads(raw)
        except (SerpApiSearchError, ValueError, OSError) as exc:
            followup_status = "error"
            yield {
                "type": "agent",
                "name": "Second",
                "status": "error",
                "tool": follow.tool,
                "engine": follow.engine,
                "summary": str(exc),
                "items": [],
            }
        else:
            followup_status = "done"
            if follow.kind == "india-price":
                tighter, set_aside = focus_listings(product, listings_from(payload))
                if any(item.price is not None and item.currency == "INR" for item in tighter):
                    listings = tighter
                items = [_public_listing(item) for item in listings[:4]]
                summary = _summary_market(listings)
                if set_aside:
                    summary += f" · {set_aside} accessories set aside"
            else:
                followup_articles = articles_from(payload)
                items = [_public_article(item) for item in followup_articles[:4]]
                summary = (
                    f"{len(followup_articles)} articles on the successor question"
                    if followup_articles
                    else "No successor headline"
                )
            yield {
                "type": "agent",
                "name": "Second",
                "status": "done",
                "tool": follow.tool,
                "engine": follow.engine,
                "query": follow.query,
                "summary": summary,
                "items": items,
            }

    yield {"type": "agent", "name": "Critic", "status": "running", "summary": "Reading the piles, including any follow-up, for a veto."}
    verdict = decide(
        product=product,
        city=city,
        budget=budget,
        listings=listings,
        places=places,
        articles=articles,
        pages=pages,
        live_agents=live,
        followup_articles=followup_articles,
        followup_status=followup_status,
        followup_kind=follow.kind,
    )
    yield {
        "type": "agent",
        "name": "Critic",
        "status": "done",
        "summary": verdict.dissent or "No veto. The evidence can carry this call.",
        "dissent": verdict.dissent,
    }
    yield {"type": "verdict", **_verdict_payload(verdict)}
