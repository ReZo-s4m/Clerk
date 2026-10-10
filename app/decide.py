"""Compare the four evidence piles and write a call the Critic can veto."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlencode

from app.evidence import Article, Listing, Page, Place
from app.money import format_money

RECALL_TERMS = (
    "recall",
    "recalled",
    "safety notice",
    "fire hazard",
    "exploding",
    "banned",
    "ban on",
)
WAIT_TERMS = (
    "successor",
    "discontinued",
    "coming soon",
    "to launch",
    "will launch",
    "new model",
    "now official",
)
PROBLEM_TERMS = (
    "overheating",
    "battery drain",
    "defect",
    "stopped working",
    "do not buy",
    "avoid",
)

BUY = "BUY"
HOLD = "HOLD"
SEE = "SEE"


@dataclass(frozen=True)
class Reason:
    claim: str
    source_title: str
    source_url: str | None
    agent: str


@dataclass(frozen=True)
class Verdict:
    call: str
    provisional: str
    headline: str
    reasons: list[Reason]
    action: str
    action_url: str | None
    dissent: str | None
    confidence: str
    price_low: float | None
    price_high: float | None
    currency: str
    spread: float | None
    rule: str


def _blob(title: str, snippet: str | None) -> str:
    return f"{title} {snippet or ''}".lower()


def _is_review(title: str) -> bool:
    return "review" in title.lower()


def later_model(article: Article, product: str) -> bool:
    """True when a headline names a higher model in the same family, such as XM6 after XM5."""

    text = _blob(article.title, article.snippet)
    for token in re.findall(r"[a-z]*\d+[a-z0-9]*", product.lower()):
        split = re.match(r"^(.*?)(\d+)$", token)
        if split is None:
            continue
        prefix, number = split.group(1), int(split.group(2))
        for other in re.findall(rf"{re.escape(prefix)}(\d+)", text):
            if int(other) > number:
                return True
    return False


def mentions_product(article: Article, product: str) -> bool:
    """True when a headline names this model, not a nearby one."""

    tokens = re.findall(r"[a-z]*\d+[a-z0-9]*", product.lower())
    text = _blob(article.title, article.snippet)
    if tokens:
        return any(token in text for token in tokens)
    return product.lower() in text


def dollar_headline(articles: list[Article]) -> Article | None:
    """Return a retrieved headline that quotes a dollar price."""

    for article in articles:
        if _is_review(article.title):
            continue
        blob = f"{article.title} {article.snippet or ''}"
        if "$" in blob or "usd" in blob.lower():
            return article
    return None


def shopping_url(product: str) -> str:
    query = urlencode({"q": product, "tbm": "shop", "gl": "in", "hl": "en"})
    return f"https://www.google.co.in/search?{query}"


def news_signal(
    articles: list[Article],
    extra_terms: tuple[str, ...] = (),
) -> tuple[str | None, Article | None]:
    """Return the strongest news signal and the article that carries it."""

    wait_terms = WAIT_TERMS + extra_terms
    for article in articles:
        if any(term in _blob(article.title, article.snippet) for term in RECALL_TERMS):
            return "recall", article
    for article in articles:
        if _is_review(article.title):
            continue
        if any(term in _blob(article.title, article.snippet) for term in wait_terms):
            return "wait", article
    return None, None


def problem_pages(pages: list[Page]) -> list[Page]:
    found: list[Page] = []
    for page in pages:
        if any(term in page.title.lower() for term in PROBLEM_TERMS):
            found.append(page)
    return found


def priced(listings: list[Listing], currency: str) -> list[Listing]:
    return [item for item in listings if item.price is not None and item.currency == currency]


def choose_currency(listings: list[Listing]) -> str:
    if any(item.price is not None and item.currency == "INR" for item in listings):
        return "INR"
    if any(item.price is not None and item.currency == "USD" for item in listings):
        return "USD"
    return "INR"


def spread_ratio(amounts: list[float]) -> float | None:
    if len(amounts) < 2:
        return None
    low = min(amounts)
    high = max(amounts)
    if low <= 0:
        return None
    return (high - low) / low


def _cite(item: Listing | Article | Page | Place, agent: str, claim: str) -> Reason:
    return Reason(
        claim=claim,
        source_title=item.title,
        source_url=item.url,
        agent=agent,
    )


def decide(
    *,
    product: str,
    city: str,
    budget: int | None,
    listings: list[Listing],
    places: list[Place],
    articles: list[Article],
    pages: list[Page],
    live_agents: int,
    followup_articles: list[Article] | None = None,
    followup_status: str = "skipped",
    followup_kind: str = "none",
) -> Verdict:
    """Make a call from evidence already retrieved. This function never searches."""

    currency = choose_currency(listings)
    offers = priced(listings, currency)
    amounts = [item.price for item in offers if item.price is not None]
    low = min(amounts) if amounts else None
    high = max(amounts) if amounts else None
    spread = spread_ratio(amounts)
    signal, signal_article = news_signal(articles)
    follow_articles = followup_articles or []
    relevant_follow = [article for article in follow_articles if mentions_product(article, product)]
    follow_signal, follow_article = news_signal(
        relevant_follow,
        extra_terms=("announced", "unveiled"),
    )
    if follow_signal is None:
        newer = next((article for article in follow_articles if later_model(article, product)), None)
        if newer is not None:
            follow_signal, follow_article = "wait", newer
    problems = problem_pages(pages)
    cheapest = min(offers, key=lambda item: item.price or 0) if offers else None
    nearest = places[0] if places else None

    call = SEE
    rule = "thin"
    reasons: list[Reason] = []

    if signal == "recall" and signal_article is not None:
        call = HOLD
        rule = "recall"
        reasons.append(
            _cite(
                signal_article,
                "Wire",
                f"News in hand mentions a safety or recall issue around {product}.",
            )
        )
    elif follow_signal == "wait" and follow_article is not None:
        call = HOLD
        rule = "followup-successor"
        reasons.append(
            _cite(
                follow_article,
                "Second",
                "The follow-up search found a successor or a new model.",
            )
        )
    elif follow_signal == "recall" and follow_article is not None:
        call = HOLD
        rule = "followup-recall"
        reasons.append(
            _cite(
                follow_article,
                "Second",
                "The follow-up search mentions a safety or recall issue.",
            )
        )
    elif signal == "wait" and signal_article is not None:
        call = HOLD
        rule = "wait-news"
        reasons.append(
            _cite(
                signal_article,
                "Wire",
                "A current headline points to a launch, a successor, or a discontinuation.",
            )
        )
    elif low is None:
        call = SEE
        rule = "no-price"
    elif budget is not None and currency == "INR" and low > budget:
        call = HOLD
        rule = "over-budget"
        if cheapest is not None:
            reasons.append(
                _cite(
                    cheapest,
                    "Market",
                    f"The lowest live {currency} listing is {format_money(low, currency)}, above a budget of {format_money(budget, 'INR' if currency == 'INR' else currency)}.",
                )
            )
    elif spread is not None and spread > 0.18 and nearest is not None:
        call = SEE
        rule = "spread-and-street"
        if cheapest is not None:
            reasons.append(
                _cite(
                    cheapest,
                    "Market",
                    f"Live {currency} listings run from {format_money(low, currency)} to {format_money(high or low, currency)}.",
                )
            )
        reasons.append(
            _cite(
                nearest,
                "Street",
                f"Maps returned a place in {city} you can check before paying the high end.",
            )
        )
    elif (
        spread is None
        and cheapest is not None
        and cheapest.multiple_sources
        and low is not None
        and (budget is None or currency != "INR" or low <= budget)
    ):
        call = BUY
        rule = "listed-from"
        verb = "starts at" if cheapest.price_floor else "is listed at"
        reasons.append(
            _cite(
                cheapest,
                "Market",
                f"Google Shopping groups sellers where {product} {verb} {format_money(low, currency)}.",
            )
        )
    elif spread is None:
        call = SEE
        rule = "single-price"
        if cheapest is not None and low is not None:
            reasons.append(
                _cite(
                    cheapest,
                    "Market",
                    f"Only one comparable {currency} price came back: {format_money(low, currency)}.",
                )
            )
    else:
        call = BUY
        rule = "tight-market"
        if cheapest is not None:
            seller = cheapest.seller or "the listing"
            reasons.append(
                _cite(
                    cheapest,
                    "Market",
                    f"{seller} is at {format_money(low, currency)}, and the live range stays within 18%.",
                )
            )

    if (
        followup_status == "done"
        and followup_kind == "successor"
        and follow_signal is None
        and call == BUY
    ):
        if relevant_follow:
            reasons.append(
                _cite(
                    relevant_follow[0],
                    "Second",
                    "The follow-up search did not show a successor, so the India price can stand.",
                )
            )
        elif follow_articles:
            reasons.append(
                _cite(
                    follow_articles[0],
                    "Second",
                    "The follow-up headline names a different model, so it is not a successor.",
                )
            )
        else:
            reasons.append(
                Reason(
                    claim="The follow-up search returned no successor headline, so the India price can stand.",
                    source_title="No successor headline",
                    source_url=None,
                    agent="Second",
                )
            )

    dollar = dollar_headline(articles)
    if dollar is not None and call != HOLD:
        reasons.append(
            _cite(
                dollar,
                "Wire",
                "A headline this week quotes a dollar price. That is not the India listing.",
            )
        )
    elif signal is None and articles:
        reasons.append(
            _cite(
                articles[0],
                "Wire",
                "The news pile has no recall or successor headline.",
            )
        )
    elif not articles and call == BUY:
        reasons.append(
            Reason(
                claim="Wire returned no articles, so the buy rests on price alone.",
                source_title="No news results",
                source_url=None,
                agent="Wire",
            )
        )

    if pages and len(reasons) < 3:
        reasons.append(
            _cite(pages[0], "Record", "Record kept a page you can read before you pay.")
        )

    provisional = call
    dissent = None
    successor_check_open = (
        followup_kind == "successor"
        and followup_status != "done"
        and dollar_headline(articles) is not None
        and any(item.price is not None and item.currency == "INR" for item in listings)
    )
    if successor_check_open and call == BUY:
        call = SEE
        dissent = (
            "A dollar headline disagrees with the India price. "
            "Buy waits until the successor search comes back."
        )
        rule = "followup-required"
    elif live_agents < 3 and call == BUY:
        call = SEE
        dissent = (
            f"Critic overruled a buy. Only {live_agents} of 4 search agents returned evidence, "
            "which is too thin to spend on."
        )
        rule = "critic-thin"
    elif len(problems) >= 2 and call == BUY:
        call = SEE
        dissent = (
            "Critic overruled a buy. Two Record pages put a serious problem in the title, "
            "so the tight price is not enough."
        )
        rule = "critic-problems"
        reasons.insert(0, _cite(problems[0], "Record", "A retrieved page title flags a serious problem."))

    reasons = reasons[:3]
    headline, action, action_url = _slip(
        call=call,
        product=product,
        city=city,
        budget=budget,
        currency=currency,
        low=low,
        cheapest=cheapest,
        nearest=nearest,
        signal_article=follow_article if rule in {"followup-successor", "followup-recall"} else signal_article,
        rule=rule,
    )
    confidence = "high" if live_agents >= 4 and reasons else "medium" if live_agents >= 2 else "low"
    return Verdict(
        call=call,
        provisional=provisional,
        headline=headline,
        reasons=reasons,
        action=action,
        action_url=action_url,
        dissent=dissent,
        confidence=confidence,
        price_low=low,
        price_high=high,
        currency=currency,
        spread=spread,
        rule=rule,
    )


def _slip(
    *,
    call: str,
    product: str,
    city: str,
    budget: int | None,
    currency: str,
    low: float | None,
    cheapest: Listing | None,
    nearest: Place | None,
    signal_article: Article | None,
    rule: str,
) -> tuple[str, str, str | None]:
    if call == BUY and rule == "listed-from" and cheapest is not None and low is not None:
        budget_note = ""
        if budget is not None and currency == "INR":
            budget_note = f" That sits inside your {format_money(budget, currency)} budget."
        return (
            f"{product} starts at {format_money(low, currency)} on the India listings.{budget_note} Dollar sale headlines are a different market.",
            f"Confirm the variant at that price, or hear it in {city} before you pay.",
            cheapest.url or shopping_url(product),
        )
    if call == BUY and cheapest is not None and low is not None:
        seller = cheapest.seller or "the cheapest listing"
        budget_note = ""
        if budget is not None:
            budget_note = f" That sits inside your {format_money(budget, currency)} budget."
        return (
            f"Buy {product} if this listing is the variant you want.{budget_note}",
            f"Open {seller} at {format_money(low, currency)} and confirm the model before you pay.",
            cheapest.url,
        )
    if call == HOLD and rule in {"recall", "followup-recall"}:
        return (
            f"Hold {product}. A retrieved headline raises a safety or recall issue.",
            "Read that article before you spend anything.",
            signal_article.url if signal_article else None,
        )
    if call == HOLD and rule == "followup-successor":
        return (
            f"Hold {product}. The follow-up search found a successor or a new model.",
            "Read that headline before you pay today's price.",
            signal_article.url if signal_article else None,
        )
    if call == HOLD and rule == "wait-news":
        return (
            f"Hold {product} this week. The news pile says the market around it is moving.",
            "Read the headline, then ask the desk again before you pay today's price.",
            signal_article.url if signal_article else None,
        )
    if call == HOLD and rule == "over-budget" and low is not None:
        return (
            f"Hold. The cheapest live listing is still {format_money(low, currency)}.",
            "Wait for a listing under your budget, or raise the number and run the desk again.",
            cheapest.url if cheapest else None,
        )
    if nearest is not None:
        return (
            f"See it in {city} before you pay a listing price for {product}.",
            f"Start with {nearest.title}. Ask what is in stock, then compare it with the live listings.",
            nearest.url,
        )
    if low is not None and cheapest is not None:
        return (
            f"See one more source before you buy {product}.",
            f"The only firm price in hand is {format_money(low, currency)}. Open it and check the variant.",
            cheapest.url,
        )
    return (
        f"See more before you buy {product}. The desk does not have a price it can stand behind.",
        "Try a more specific product name, including the model number.",
        None,
    )
