"""Choose one more search when the first piles disagree."""

from __future__ import annotations

from dataclasses import dataclass

from app.decide import dollar_headline
from app.evidence import Article, Listing


@dataclass(frozen=True)
class FollowUp:
    needed: bool
    kind: str
    tool: str
    engine: str
    query: str
    why: str


def choose_followup(product: str, listings: list[Listing], articles: list[Article]) -> FollowUp:
    """Pick a single follow-up search, or none when the piles can carry a call."""

    india_prices = [item for item in listings if item.price is not None and item.currency == "INR"]
    if dollar_headline(articles) is not None and india_prices:
        return FollowUp(
            needed=True,
            kind="successor",
            tool="news_search",
            engine="google_news",
            query=f'{product} (successor OR "new model" OR announced)',
            why=(
                "Wire quotes a dollar price and Market has an India price. "
                "Checking the news for a successor before a buy."
            ),
        )
    if not india_prices:
        return FollowUp(
            needed=True,
            kind="india-price",
            tool="shopping_search",
            engine="google_shopping",
            query=f"{product} price",
            why="Market has no readable India price. Searching Shopping again with a tighter query.",
        )
    return FollowUp(
        needed=False,
        kind="none",
        tool="",
        engine="",
        query="",
        why="The piles agree. No second search.",
    )
